"""Execution layer for invoking active traders and executing trades.

This module:
1. Retrieves all active traders from the database
2. Fetches market data and account information
3. Formats prompts with placeholders replaced
4. Calls LLM API to get trading decisions
5. Executes trades using the testnet client
"""

import os
import json
import logging
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
from config.trading_config import (
    DEFAULT_UNCERTAINTY_THRESHOLD,
    DEFAULT_LEVERAGE,
    DEFAULT_MAX_POSITION_SIZE_PCT,
)
from openai import OpenAI
from dotenv import load_dotenv

from db.database import get_session
from db.db_models import UserModel, BrokerConnection, Trade, APICallLog
from layers.encryption import decrypt
from layers.ingestion import EXCHANGE, SYMBOLS, fetch_ohlcv, build_indicators
from layers.broker_factory import create_broker
from layers.broker_interface import BrokerInterface
import pandas_ta as ta
import pandas as pd
import time

load_dotenv()

logger = logging.getLogger(__name__)

# OpenAI API configuration
openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY')) if os.getenv('OPENAI_API_KEY') else None


@dataclass
class TraderDecision:
    """Structured decision from LLM trader."""
    coin: str  # e.g., "BTC", "ETH", "DOGE"
    decision: str  # "long", "short", "hold", "close"
    uncertainty: float  # 0.0 to 1.0 (0 = confident, 1 = very uncertain)
    quantity: float  # Amount to trade (positive number)
    
    # Optional enhanced fields
    position_pct: Optional[float] = None  # Alternative: position as % of portfolio (0.0-1.0)
    leverage: Optional[float] = None  # Leverage to use (1.0-50.0)
    stop_loss_pct: Optional[float] = None  # Stop-loss percentage (e.g., 0.05 = 5%)
    take_profit_pct: Optional[float] = None  # Take-profit percentage (e.g., 0.10 = 10%)
    reasoning: Optional[str] = None  # LLM's reasoning for the trade


def get_active_traders() -> List[UserModel]:
    """Get all active traders from the database."""
    with get_session() as session:
        traders = session.query(UserModel).filter(UserModel.active == True).all()
        return traders


def get_broker_connection(user_id: str) -> Optional[BrokerConnection]:
    """Get the most recent broker connection for a user."""
    with get_session() as session:
        connection = session.query(BrokerConnection).filter_by(
            user_id=user_id,
            is_connected=True
        ).order_by(BrokerConnection.created_at.desc()).first()
        return connection


def format_market_data_for_prompt(tickers: List[str]) -> str:
    """Format market data for the prompt, matching the expected format.
    
    Args:
        tickers: List of coin tickers (e.g., ["BTC", "ETH", "DOGE"])
        
    Returns:
        Formatted market data string
    """
    market_data_parts = []
    
    for ticker in tickers:
        symbol = f"{ticker}/USDT"
        if symbol not in SYMBOLS:
            logger.warning(f"Symbol {symbol} not in supported symbols, skipping")
            continue
        
        try:
            # Fetch intraday data (3m timeframe)
            intraday_df = fetch_ohlcv(symbol, "3m", 50)
            intraday_df = build_indicators(intraday_df)
            
            # Fetch 4-hour data
            fourhour_df = fetch_ohlcv(symbol, "4h", 50)
            fourhour_df = build_indicators(fourhour_df)
            
            # Get open interest and funding rate (using futures testnet)
            # Note: This might require futures API access
            open_interest_latest = 0.0
            open_interest_avg = 0.0
            funding_rate = 0.0
            
            try:
                # Try to get futures data if available
                futures_client = EXCHANGE
                if hasattr(futures_client, 'fetch_open_interest'):
                    oi_data = futures_client.fetch_open_interest(symbol)
                    open_interest_latest = float(oi_data.get('openInterestAmount', 0))
                if hasattr(futures_client, 'fetch_funding_rate'):
                    fr_data = futures_client.fetch_funding_rate(symbol)
                    funding_rate = float(fr_data.get('fundingRate', 0))
            except Exception as e:
                logger.debug(f"Could not fetch futures data for {symbol}: {e}")
            
            # Format the coin data
            coin_data = f"""ALL {ticker} DATA

            current_price = {intraday_df["close"].iloc[-1]:.5f}, current_ema20 = {intraday_df["ema20"].iloc[-1]:.5f}, current_macd = {intraday_df["macd"].iloc[-1]:.5f}, current_rsi (7 period) = {intraday_df["rsi7"].iloc[-1]:.5f}

            In addition, here is the latest {ticker} open interest and funding rate for perps:

            Open Interest: Latest: {open_interest_latest:.2f} Average: {open_interest_avg:.2f}

            Funding Rate: {funding_rate:.2e}

            Intraday series (3-minute intervals, oldest → latest):

            Mid prices: {intraday_df["close"].tail(10).round(4).tolist()}

            EMA indicators (20-period): {intraday_df["ema20"].tail(10).round(4).tolist()}

            MACD indicators: {intraday_df["macd"].tail(10).round(4).tolist()}

            RSI indicators (7-Period): {intraday_df["rsi7"].tail(10).round(4).tolist()}

            RSI indicators (14-Period): {intraday_df["rsi14"].tail(10).round(4).tolist()}

            Longer-term context (4-hour timeframe):

            20-Period EMA: {float(fourhour_df["ema20"].iloc[-1]):.5f} vs. 50-Period EMA: {float(ta.ema(fourhour_df["close"], length=50).iloc[-1]):.5f}

            3-Period ATR: {float(fourhour_df["atr3"].iloc[-1]):.5f} vs. 14-Period ATR: {float(fourhour_df["atr14"].iloc[-1]):.5f}

            Current Volume: {float(fourhour_df["volume"].iloc[-1]):.5f} vs. Average Volume: {float(fourhour_df["volume"].mean()):.5f}

            MACD indicators: {fourhour_df["macd"].tail(10).round(4).tolist()}

            RSI indicators (14-Period): {fourhour_df["rsi14"].tail(10).round(4).tolist()}
            """
            market_data_parts.append(coin_data)
            
        except Exception as e:
            logger.error(f"Error fetching market data for {ticker}: {e}")
            continue
    
    return "\n".join(market_data_parts)


def format_account_data_for_prompt(trader: UserModel, broker: Optional[BrokerInterface] = None) -> str:
    """Format account data for the prompt.
    
    Args:
        trader: The trader model
        broker: Optional broker instance for real account data
        
    Returns:
        Formatted account data string
    """
    account_parts = []
    
    # Get real balance from broker if available
    real_balance = trader.balance
    if broker:
        try:
            real_balance = broker.get_balance()
        except Exception as e:
            logger.debug(f"Could not fetch broker balance: {e}")
    
    # Basic account info from trader model
    account_parts.append(f"Current Total Return (percent): {((real_balance - trader.start_balance) / trader.start_balance * 100):.2f}%")
    account_parts.append(f"Available Cash: {real_balance:.2f}")
    account_parts.append(f"Current Account Value: {real_balance:.2f}")
    
    # Get positions if broker is available
    positions_info = "Current live positions & performance: No positions"
    if broker:
        try:
            positions = broker.get_positions()
            if positions:
                positions_info = f"Current live positions & performance: {json.dumps(positions)}"
        except Exception as e:
            logger.debug(f"Could not fetch account positions: {e}")
    
    account_parts.append(positions_info)
    account_parts.append("Sharpe Ratio: 0.0")  # TODO: Calculate actual Sharpe ratio
    
    return "\n".join(account_parts)


def replace_prompt_placeholders(
    prompt_template: str,
    market_data: str,
    account_data: str,
    minutes_since_start: int,
    current_time: str,
    invocation_count: int
) -> str:
    """Replace placeholders in the prompt template with actual data.
    
    Args:
        prompt_template: The prompt template with placeholders
        market_data: Formatted market data
        account_data: Formatted account data
        minutes_since_start: Minutes since trader started
        current_time: Current timestamp string
        invocation_count: Number of times trader has been invoked
        
    Returns:
        Prompt with all placeholders replaced
    """
    prompt = prompt_template
    prompt = prompt.replace("{minutes_since_start}", str(minutes_since_start))
    prompt = prompt.replace("{current_time}", current_time)
    prompt = prompt.replace("{invocation_count}", str(invocation_count))
    prompt = prompt.replace("{market_data}", market_data)
    prompt = prompt.replace("{account_data}", account_data)
    
    return prompt


def call_llm_api(
    prompt: str, 
    model: str = "gpt-5-mini",
    trader_id: Optional[int] = None,
    user_id: Optional[str] = None,
    save_log: bool = True
) -> Tuple[TraderDecision, Dict[str, Any]]:
    """Call LLM API and parse structured TraderDecision response.
    
    Args:
        prompt: The formatted prompt to send to LLM
        model: The LLM model to use
        trader_id: Optional trader ID for logging
        user_id: Optional user ID for logging
        save_log: Whether to save the API call log to database
        
    Returns:
        Tuple of (TraderDecision object, metadata dict)
        
    Raises:
        Exception: If LLM call fails or response is invalid
    """
    if not openai_client:
        raise Exception("OpenAI API key not configured. Set OPENAI_API_KEY environment variable.")
    
    start_time = time.time()
    metadata = {
        "success": False,
        "response": None,
        "tokens_used": None,
        "latency_ms": None,
        "error": None
    }
    
    try:
        # Use OpenAI's structured output feature (JSON mode)
        # System prompt with trading guidance including minimum sizes
        system_prompt = """You are a cryptocurrency perpetual futures trading agent. Analyze the market data and account information provided, and make a trading decision.

You must respond with a JSON object containing these REQUIRED fields:
- coin: string (e.g., 'BTC', 'ETH', 'SOL') - the coin to trade
- decision: string, one of 'long', 'short', 'hold', 'close'
  * 'long' = open or add to a LONG position (profit when price goes UP)
  * 'short' = open or add to a SHORT position (profit when price goes DOWN)
  * 'hold' = do nothing, wait for better opportunity
  * 'close' = close existing position entirely (exit the trade)
- uncertainty: float, 0.0 to 1.0 (0 = very confident, 1 = very uncertain)
  * IMPORTANT: Be honest about uncertainty. High uncertainty trades may be skipped.
  * Consider market volatility, conflicting signals, and your confidence in the analysis.
- quantity: float, the amount of coins to trade (ignored for 'hold' and 'close')

OPTIONAL fields (include if relevant):
- position_pct: float, 0.0 to 1.0 - alternative to quantity, specify as % of portfolio
- leverage: float, 1.0 to 50.0 - leverage to use for this trade (default: 1.0)
- stop_loss_pct: float, e.g., 0.05 = 5% stop-loss from entry
- take_profit_pct: float, e.g., 0.10 = 10% take-profit from entry
- reasoning: string, brief explanation of your decision (for logging)

IMPORTANT - Minimum trade sizes (from Hyperliquid):
- BTC: min 0.00001 (~$1)
- ETH: min 0.0001 (~$0.30)
- SOL: min 0.01 (~$2)
- DOGE: min 1 (~$0.40)
- XRP: min 1 (~$2.50)
- ARB: min 0.1 (~$0.08)
- AVAX: min 0.01 (~$0.45)
- LINK: min 0.1 (~$2)
- MATIC: min 0.1 (~$0.05)
- BNB: min 0.001 (~$0.70)

When deciding quantity/position_pct, consider:
1. The available cash balance shown in account data
2. Risk management - don't overexpose to a single position
3. Your uncertainty level - size smaller when less confident
4. Existing positions - consider if adding or reducing is appropriate
5. The minimum trade sizes above - quantities below these will be rejected"""

        response = openai_client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            response_format={
                "type": "json_object"
            },
        )
        
        latency_ms = int((time.time() - start_time) * 1000)
        
        # Parse the JSON response
        content = response.choices[0].message.content
        decision_dict = json.loads(content)
        
        # Get token usage if available
        tokens_used = None
        if hasattr(response, 'usage'):
            tokens_used = response.usage.total_tokens if response.usage else None
        
        # Validate and create TraderDecision
        coin = decision_dict.get("coin", "").upper()
        decision = decision_dict.get("decision", "hold").lower()
        uncertainty = float(decision_dict.get("uncertainty", 0.5))
        quantity = float(decision_dict.get("quantity", 0.0))
        
        # Parse optional fields
        position_pct = decision_dict.get("position_pct")
        if position_pct is not None:
            position_pct = float(position_pct)
            position_pct = max(0.0, min(1.0, position_pct))  # Clamp to [0, 1]
        
        leverage = decision_dict.get("leverage")
        if leverage is not None:
            leverage = float(leverage)
            leverage = max(1.0, min(50.0, leverage))  # Clamp to [1, 50]
        
        stop_loss_pct = decision_dict.get("stop_loss_pct")
        if stop_loss_pct is not None:
            stop_loss_pct = float(stop_loss_pct)
            stop_loss_pct = max(0.001, min(0.5, stop_loss_pct))  # Clamp to [0.1%, 50%]
        
        take_profit_pct = decision_dict.get("take_profit_pct")
        if take_profit_pct is not None:
            take_profit_pct = float(take_profit_pct)
            take_profit_pct = max(0.001, min(2.0, take_profit_pct))  # Clamp to [0.1%, 200%]
        
        reasoning = decision_dict.get("reasoning", "")
        
        # Validate decision
        if decision not in ["long", "short", "hold", "close"]:
            decision = "hold"
        
        # Clamp uncertainty to [0, 1]
        uncertainty = max(0.0, min(1.0, uncertainty))
        
        # Ensure quantity is positive
        quantity = abs(quantity)
        
        trader_decision = TraderDecision(
            coin=coin,
            decision=decision,
            uncertainty=uncertainty,
            quantity=quantity,
            position_pct=position_pct,
            leverage=leverage,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            reasoning=reasoning
        )
        
        metadata.update({
            "success": True,
            "response": content,
            "tokens_used": tokens_used,
            "latency_ms": latency_ms
        })
        
        # Save API call log
        if save_log and trader_id and user_id:
            try:
                with get_session() as session:
                    api_log = APICallLog(
                        trader_id=trader_id,
                        user_id=user_id,
                        model_name=model,
                        prompt=prompt,
                        prompt_length=len(prompt),
                        response=content,
                        decision_coin=coin,
                        decision_action=decision,
                        decision_uncertainty=uncertainty,
                        decision_quantity=quantity,
                        tokens_used=tokens_used,
                        latency_ms=latency_ms,
                        success=True
                    )
                    session.add(api_log)
                    session.commit()
            except Exception as e:
                logger.warning(f"Failed to save API call log: {e}")
        
        return trader_decision, metadata
        
    except json.JSONDecodeError as e:
        latency_ms = int((time.time() - start_time) * 1000)
        error_msg = f"Invalid LLM response format: {e}"
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        
        metadata.update({
            "success": False,
            "error": error_msg,
            "latency_ms": latency_ms
        })
        
        # Save error log
        if save_log and trader_id and user_id:
            try:
                with get_session() as session:
                    api_log = APICallLog(
                        trader_id=trader_id,
                        user_id=user_id,
                        model_name=model,
                        prompt=prompt[:10000] if len(prompt) > 10000 else prompt,
                        prompt_length=len(prompt),
                        response="",
                        success=False,
                        error_message=error_msg,
                        latency_ms=latency_ms
                    )
                    session.add(api_log)
                    session.commit()
            except Exception as log_error:
                logger.warning(f"Failed to save API error log: {log_error}")
        
        raise Exception(error_msg)
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        error_msg = str(e)
        logger.error(f"LLM API call failed: {e}")
        
        metadata.update({
            "success": False,
            "error": error_msg,
            "latency_ms": latency_ms
        })
        
        # Save error log
        if save_log and trader_id and user_id:
            try:
                with get_session() as session:
                    api_log = APICallLog(
                        trader_id=trader_id,
                        user_id=user_id,
                        model_name=model,
                        prompt=prompt[:10000] if len(prompt) > 10000 else prompt,
                        prompt_length=len(prompt),
                        response="",
                        success=False,
                        error_message=error_msg,
                        latency_ms=latency_ms
                    )
                    session.add(api_log)
                    session.commit()
            except Exception as log_error:
                logger.warning(f"Failed to save API error log: {log_error}")
        
        raise


def execute_trade(
    broker: BrokerInterface,
    decision: TraderDecision,
    trader: UserModel,
    save_trade: bool = True,
    uncertainty_threshold: float = DEFAULT_UNCERTAINTY_THRESHOLD,
    user_stop_loss_pct: Optional[float] = None,
    user_take_profit_pct: Optional[float] = None
) -> Dict[str, Any]:
    """Execute a trade using the broker, with optional stop loss and take profit.
    
    Args:
        broker: Broker interface instance
        decision: The trading decision
        trader: The trader model
        save_trade: Whether to save the trade to database
        uncertainty_threshold: Skip trade if uncertainty > this value
        user_stop_loss_pct: User-configured stop loss % (takes precedence over LLM)
        user_take_profit_pct: User-configured take profit % (takes precedence over LLM)
        
    Returns:
        Dictionary with trade execution result
    """
    symbol = decision.coin  # Use coin directly, broker will format it
    
    try:
        # Check uncertainty threshold - skip trade if too uncertain
        if decision.uncertainty > uncertainty_threshold and decision.decision not in ["hold"]:
            skip_reason = f"Uncertainty {decision.uncertainty:.2f} exceeds threshold {uncertainty_threshold:.2f}"
            logger.info(f"Skipping trade due to high uncertainty: {skip_reason}")
            
            result = {
                "success": True,
                "action": "skipped",
                "message": f"Trade skipped: {skip_reason}",
                "original_decision": decision.decision,
                "symbol": symbol,
                "coin": decision.coin,
                "quantity": decision.quantity,
                "uncertainty": decision.uncertainty,
                "threshold": uncertainty_threshold,
                "price": 0.0
            }
            
            # Save skipped trade for tracking
            if save_trade:
                try:
                    with get_session() as session:
                        trade = Trade(
                            trader_id=trader.id,
                            user_id=trader.user_id,
                            symbol=f"{symbol}USDT",
                            coin=decision.coin,
                            side="skipped",  # Mark as skipped
                            quantity=decision.quantity,
                            price=0.0,
                            uncertainty=decision.uncertainty,
                            success=True,
                            error_message=skip_reason
                        )
                        session.add(trade)
                        session.commit()
                except Exception as e:
                    logger.warning(f"Failed to save skipped trade: {e}")
            
            return result
        
        if decision.decision == "hold":
            result = {
                "success": True,
                "action": "hold",
                "message": "No trade executed (hold decision)",
                "symbol": symbol,
                "coin": decision.coin,
                "quantity": 0.0,
                "price": 0.0
            }
            
            # Save hold decision as trade
            if save_trade:
                try:
                    with get_session() as session:
                        trade = Trade(
                            trader_id=trader.id,
                            user_id=trader.user_id,
                            symbol=f"{symbol}USDT",  # Format for database
                            coin=decision.coin,
                            side="hold",
                            quantity=0.0,
                            price=0.0,
                            uncertainty=decision.uncertainty,
                            success=True
                        )
                        session.add(trade)
                        session.commit()
                except Exception as e:
                    logger.warning(f"Failed to save hold trade: {e}")
            
            return result
        
        # Handle close decision - close entire position
        if decision.decision == "close":
            try:
                positions = broker.get_positions()
                position_to_close = None
                for pos in positions:
                    if pos.get("symbol", "").upper() == symbol.upper():
                        position_to_close = pos
                        break
                
                if not position_to_close:
                    result = {
                        "success": True,
                        "action": "close",
                        "message": f"No open position for {symbol} to close",
                        "symbol": symbol,
                        "coin": decision.coin,
                        "quantity": 0.0,
                        "price": 0.0
                    }
                    return result
                
                # Close the position by trading the opposite direction
                close_quantity = position_to_close.get("quantity", 0)
                # Determine if we need to short (close long) or long (close short)
                # If position size is positive, it's a long, so we short to close
                close_side = "short" if close_quantity > 0 else "long"
                
                trade_result = broker.execute_trade(
                    symbol=symbol,
                    side=close_side,
                    quantity=abs(close_quantity)
                )
                
                result = {
                    "success": trade_result.get("success", False),
                    "action": "close",
                    "order": trade_result.get("order"),
                    "symbol": f"{symbol}USDT",
                    "coin": decision.coin,
                    "quantity": abs(close_quantity),
                    "price": trade_result.get("price", 0.0),
                    "order_id": trade_result.get("order_id")
                }
                
                if not trade_result.get("success"):
                    result["error"] = trade_result.get("error", "Unknown error")
                
                # Save trade to database
                if save_trade:
                    try:
                        with get_session() as session:
                            trade = Trade(
                                trader_id=trader.id,
                                user_id=trader.user_id,
                                symbol=f"{symbol}USDT",
                                coin=decision.coin,
                                side="close",
                                quantity=abs(close_quantity),
                                price=result.get("price", 0.0),
                                uncertainty=decision.uncertainty,
                                order_id=str(result.get("order_id")) if result.get("order_id") else None,
                                order_response=json.dumps(trade_result.get("order")) if trade_result.get("order") else None,
                                stop_loss_order=None,  # Close trades don't have SL/TP
                                take_profit_order=None,  # Close trades don't have SL/TP
                                success=result.get("success", False),
                                error_message=result.get("error")
                            )
                            session.add(trade)
                            session.commit()
                    except Exception as e:
                        logger.warning(f"Failed to save close trade: {e}")
                
                return result
                
            except Exception as e:
                logger.error(f"Error closing position: {e}")
                return {
                    "success": False,
                    "action": "close",
                    "error": str(e),
                    "symbol": f"{symbol}USDT",
                    "coin": decision.coin,
                    "quantity": 0.0,
                    "price": 0.0
                }
        
        # Execute trade via broker (uses "long"/"short" notation)
        trade_result = broker.execute_trade(
            symbol=symbol,
            side=decision.decision,
            quantity=decision.quantity
        )
        
        # Format result
        result = {
            "success": trade_result.get("success", False),
            "action": decision.decision,
            "order": trade_result.get("order"),
            "symbol": f"{symbol}USDT",  # Format for response
            "coin": decision.coin,
            "quantity": decision.quantity,
            "price": trade_result.get("price", 0.0),
            "order_id": trade_result.get("order_id")
        }
        
        if not trade_result.get("success"):
            result["error"] = trade_result.get("error", "Unknown error")
        
        # If trade was successful, place stop loss and take profit orders
        if trade_result.get("success") and result.get("price", 0) > 0:
            entry_price = result.get("price", 0.0)
            is_long = decision.decision == "long"
            
            # Determine which SL/TP values to use (user settings take precedence over LLM)
            effective_stop_loss_pct = user_stop_loss_pct or decision.stop_loss_pct
            effective_take_profit_pct = user_take_profit_pct or decision.take_profit_pct
            
            result["stop_loss"] = None
            result["take_profit"] = None
            
            # Cancel any existing trigger orders for this symbol before placing new ones
            if effective_stop_loss_pct or effective_take_profit_pct:
                try:
                    cancel_result = broker.cancel_trigger_orders(symbol)
                    if cancel_result.get("cancelled_count", 0) > 0:
                        logger.info(f"Cancelled {cancel_result['cancelled_count']} existing trigger orders for {symbol}")
                except Exception as e:
                    logger.warning(f"Failed to cancel existing trigger orders: {e}")
            
            # Place stop loss order if configured
            if effective_stop_loss_pct and effective_stop_loss_pct > 0:
                # Calculate stop loss trigger price
                if is_long:
                    # For long: stop loss triggers below entry price
                    sl_trigger_price = entry_price * (1 - effective_stop_loss_pct)
                else:
                    # For short: stop loss triggers above entry price
                    sl_trigger_price = entry_price * (1 + effective_stop_loss_pct)
                
                try:
                    sl_result = broker.place_stop_loss(
                        symbol=symbol,
                        quantity=decision.quantity,
                        trigger_price=sl_trigger_price,
                        is_long=is_long
                    )
                    result["stop_loss"] = {
                        "success": sl_result.get("success", False),
                        "trigger_price": sl_trigger_price,
                        "percentage": effective_stop_loss_pct,
                        "order_id": sl_result.get("order_id"),
                        "error": sl_result.get("error")
                    }
                    if sl_result.get("success"):
                        logger.info(f"Placed stop loss at ${sl_trigger_price:.2f} ({effective_stop_loss_pct*100:.1f}% from entry)")
                    else:
                        logger.warning(f"Failed to place stop loss: {sl_result.get('error')}")
                except Exception as e:
                    logger.error(f"Error placing stop loss: {e}")
                    result["stop_loss"] = {"success": False, "error": str(e)}
            
            # Place take profit order if configured
            if effective_take_profit_pct and effective_take_profit_pct > 0:
                # Calculate take profit trigger price
                if is_long:
                    # For long: take profit triggers above entry price
                    tp_trigger_price = entry_price * (1 + effective_take_profit_pct)
                else:
                    # For short: take profit triggers below entry price
                    tp_trigger_price = entry_price * (1 - effective_take_profit_pct)
                
                try:
                    tp_result = broker.place_take_profit(
                        symbol=symbol,
                        quantity=decision.quantity,
                        trigger_price=tp_trigger_price,
                        is_long=is_long
                    )
                    result["take_profit"] = {
                        "success": tp_result.get("success", False),
                        "trigger_price": tp_trigger_price,
                        "percentage": effective_take_profit_pct,
                        "order_id": tp_result.get("order_id"),
                        "error": tp_result.get("error")
                    }
                    if tp_result.get("success"):
                        logger.info(f"Placed take profit at ${tp_trigger_price:.2f} ({effective_take_profit_pct*100:.1f}% from entry)")
                    else:
                        logger.warning(f"Failed to place take profit: {tp_result.get('error')}")
                except Exception as e:
                    logger.error(f"Error placing take profit: {e}")
                    result["take_profit"] = {"success": False, "error": str(e)}
        
        # Save trade to database
        if save_trade:
            try:
                with get_session() as session:
                    trade = Trade(
                        trader_id=trader.id,
                        user_id=trader.user_id,
                        symbol=f"{symbol}USDT",
                        coin=decision.coin,
                        side=decision.decision,
                        quantity=decision.quantity,
                        price=result.get("price", 0.0),
                        uncertainty=decision.uncertainty,
                        order_id=str(result.get("order_id")) if result.get("order_id") else None,
                        order_response=json.dumps(trade_result.get("order")) if trade_result.get("order") else None,
                        stop_loss_order=json.dumps(result.get("stop_loss")) if result.get("stop_loss") else None,
                        take_profit_order=json.dumps(result.get("take_profit")) if result.get("take_profit") else None,
                        success=result.get("success", False),
                        error_message=result.get("error")
                    )
                    session.add(trade)
                    session.commit()
            except Exception as e:
                logger.warning(f"Failed to save trade: {e}")
        
        return result
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error executing trade: {e}")
        
        result = {
            "success": False,
            "action": decision.decision,
            "error": error_msg,
            "symbol": f"{symbol}USDT",
            "coin": decision.coin,
            "quantity": decision.quantity,
            "price": 0.0
        }
        
        # Save failed trade
        if save_trade:
            try:
                with get_session() as session:
                    trade = Trade(
                        trader_id=trader.id,
                        user_id=trader.user_id,
                        symbol=f"{symbol}USDT",
                        coin=decision.coin,
                        side=decision.decision,
                        quantity=decision.quantity,
                        price=0.0,
                        uncertainty=decision.uncertainty,
                        success=False,
                        error_message=error_msg
                    )
                    session.add(trade)
                    session.commit()
            except Exception as save_error:
                logger.warning(f"Failed to save failed trade: {save_error}")
        
        return result


def execute_trader(trader: UserModel) -> Dict[str, Any]:
    """Execute a single trader: get decision and execute trade.
    
    Args:
        trader: The trader model to execute
        
    Returns:
        Dictionary with execution results
    """
    try:
        # Parse trader configuration
        llm_config = json.loads(trader.weights) if trader.weights else {}
        llm_model = llm_config.get("llm_model", "gpt-4o-mini")
        prompt_template = llm_config.get("prompt", "")
        tickers = json.loads(trader.tickers) if trader.tickers else []
        
        # Get risk management settings from trader model (with defaults)
        uncertainty_threshold = getattr(trader, 'uncertainty_threshold', None)
        if uncertainty_threshold is None:
            uncertainty_threshold = DEFAULT_UNCERTAINTY_THRESHOLD
        
        max_position_size_pct = getattr(trader, 'max_position_size_pct', None)
        if max_position_size_pct is None:
            max_position_size_pct = DEFAULT_MAX_POSITION_SIZE_PCT
        
        default_leverage = getattr(trader, 'default_leverage', None)
        if default_leverage is None:
            default_leverage = DEFAULT_LEVERAGE
        
        # Get stop loss and take profit settings from trader model
        user_stop_loss_pct = getattr(trader, 'stop_loss_pct', None)
        user_take_profit_pct = getattr(trader, 'take_profit_pct', None)
        
        logger.info(f"Trader {trader.id} settings: uncertainty_threshold={uncertainty_threshold}, "
                   f"max_position_size_pct={max_position_size_pct}, default_leverage={default_leverage}, "
                   f"stop_loss_pct={user_stop_loss_pct}, take_profit_pct={user_take_profit_pct}")
        
        if not prompt_template:
            logger.warning(f"Trader {trader.id} has no prompt template")
            return {"success": False, "error": "No prompt template"}
        
        if not tickers:
            logger.warning(f"Trader {trader.id} has no tickers configured")
            return {"success": False, "error": "No tickers configured"}
        
        # Get broker connection
        connection = get_broker_connection(trader.user_id)
        if not connection:
            logger.warning(f"No broker connection found for trader {trader.id}")
            return {"success": False, "error": "No broker connection"}
        
        # Create broker instance
        try:
            broker = create_broker(connection)
        except Exception as e:
            logger.error(f"Error creating broker for trader {trader.id}: {e}")
            return {"success": False, "error": f"Failed to create broker: {str(e)}"}
        
        # Format market data
        market_data = format_market_data_for_prompt(tickers)
        
        # Format account data
        account_data = format_account_data_for_prompt(trader, broker)
        
        # Calculate time since start
        if trader.created_at:
            if isinstance(trader.created_at, datetime):
                created_dt = trader.created_at
            else:
                created_dt = datetime.combine(trader.created_at, datetime.min.time())
            minutes_since_start = int((datetime.now() - created_dt).total_seconds() / 60)
        else:
            minutes_since_start = 0
        
        current_time = datetime.now().isoformat()
        
        # TODO: Track invocation count in database
        invocation_count = 1
        
        # Replace placeholders in prompt
        full_prompt = replace_prompt_placeholders(
            prompt_template,
            market_data,
            account_data,
            minutes_since_start,
            current_time,
            invocation_count
        )
        
        # Call LLM API
        decision, api_metadata = call_llm_api(
            full_prompt, 
            llm_model,
            trader_id=trader.id,
            user_id=trader.user_id,
            save_log=True
        )
        
        # Execute trade with uncertainty threshold check and SL/TP settings
        trade_result = execute_trade(
            broker, 
            decision, 
            trader, 
            save_trade=True,
            uncertainty_threshold=uncertainty_threshold,
            user_stop_loss_pct=user_stop_loss_pct,
            user_take_profit_pct=user_take_profit_pct
        )
        
        return {
            "success": True,
            "trader_id": trader.id,
            "trader_name": trader.name,
            "decision": decision,
            "trade_result": trade_result,
            "settings_used": {
                "uncertainty_threshold": uncertainty_threshold,
                "max_position_size_pct": max_position_size_pct,
                "default_leverage": default_leverage,
                "stop_loss_pct": user_stop_loss_pct,
                "take_profit_pct": user_take_profit_pct
            }
        }
        
    except Exception as e:
        logger.error(f"Error executing trader {trader.id}: {e}")
        return {
            "success": False,
            "trader_id": trader.id,
            "error": str(e)
        }


def execute_all_active_traders() -> List[Dict[str, Any]]:
    """Execute all active traders.
    
    Returns:
        List of execution results for each trader
    """
    traders = get_active_traders()
    results = []
    
    for trader in traders:
        result = execute_trader(trader)
        results.append(result)
    
    return results

