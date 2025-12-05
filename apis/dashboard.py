from datetime import datetime, timedelta
import json
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, desc
from db.db_models import UserModel, Trade, APICallLog, DashboardCache, BrokerConnection
from db.database import get_session
from layers.execution import execute_all_active_traders, get_active_traders, execute_trader
from layers.brokers.hyperliquid_broker import HyperliquidBroker
from layers.encryption import decrypt
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Create blueprint
dashboard_bp = Blueprint('dashboard', __name__)


def _get_cached_dashboard(user_id: str) -> Optional[Dict]:
    """Get cached dashboard data for a user."""
    with get_session() as session:
        cache = session.query(DashboardCache).filter(DashboardCache.user_id == user_id).first()
        if not cache:
            return None
        
        return {
            "broker_balances": json.loads(cache.broker_balances) if cache.broker_balances else [],
            "trades": json.loads(cache.trades) if cache.trades else [],
            "api_logs": json.loads(cache.api_logs) if cache.api_logs else [],
            "balance_history": json.loads(cache.balance_history) if cache.balance_history else [],
            "traders": json.loads(cache.traders) if cache.traders else [],
            "updated_at": cache.updated_at.isoformat() if cache.updated_at else None,
        }


def _save_dashboard_cache(user_id: str, data: Dict) -> None:
    """Save dashboard data to cache."""
    with get_session() as session:
        cache = session.query(DashboardCache).filter(DashboardCache.user_id == user_id).first()
        
        if not cache:
            cache = DashboardCache(user_id=user_id)
            session.add(cache)
        
        if "broker_balances" in data:
            cache.broker_balances = json.dumps(data["broker_balances"])
        if "trades" in data:
            cache.trades = json.dumps(data["trades"])
        if "api_logs" in data:
            cache.api_logs = json.dumps(data["api_logs"])
        if "balance_history" in data:
            cache.balance_history = json.dumps(data["balance_history"])
        if "traders" in data:
            cache.traders = json.dumps(data["traders"])
        
        cache.updated_at = datetime.now()
        session.commit()

@dashboard_bp.route('/stats', methods=['GET'])
@jwt_required()
def get_dashboard_stats():
    """
    Get dashboard statistics for the current user.
    
    Returns:
        JSON response containing:
        - total_models: Total number of trading models
        - active_models: Number of active trading models
        - total_balance: Sum of all model balances
        - net_profit: Total profit/loss across all models
    """
    user_id = get_jwt_identity()
    if not isinstance(user_id, str):
        return jsonify({"error": "Invalid token format"}), 401

    with get_session() as session:
        # Get all trading models for the user
        models = session.query(UserModel).filter(UserModel.user_id == user_id).all()
        
        # If no models found, return default values
        if not models:
            return jsonify({
                "total_models": 0,
                "active_models": 0,
                "total_balance": 0.0,
                "net_profit": 0.0
            }), 200

        total_models = len(models)
        active_models = sum(1 for model in models if model.active)
        total_balance = sum(model.balance for model in models)
        net_profit = sum(model.balance - model.start_balance for model in models)

        return jsonify({
            "total_models": total_models,
            "active_models": active_models,
            "total_balance": total_balance,
            "net_profit": net_profit
        }), 200

@dashboard_bp.route('/predictions', methods=['GET'])
@jwt_required()
def get_recent_predictions():
    """
    Get recent predictions for all user trading models.
    Note: This endpoint is kept for backwards compatibility but returns empty.
    Use /trades and /api-logs endpoints instead.
    
    Returns:
        JSON response containing an empty list of predictions
    """
    return jsonify({"predictions": []}), 200


@dashboard_bp.route('/trades', methods=['GET'])
@jwt_required()
def get_trades():
    """
    Get recent trades for all user trading models.
    
    Query params:
        - limit: Number of trades to return (default: 50)
        - trader_id: Optional filter by trader ID
    
    Returns:
        JSON response containing a list of trades
    """
    user_id = get_jwt_identity()
    if not isinstance(user_id, str):
        return jsonify({"error": "Invalid token format"}), 401

    limit = request.args.get('limit', 50, type=int)
    trader_id = request.args.get('trader_id', type=int)
    
    with get_session() as session:
        query = (
            session.query(Trade, UserModel.name.label('trader_name'))
            .join(UserModel, Trade.trader_id == UserModel.id)
            .filter(Trade.user_id == user_id)
        )
        
        if trader_id:
            query = query.filter(Trade.trader_id == trader_id)
        
        trades = (
            query
            .order_by(desc(Trade.executed_at))
            .limit(limit)
            .all()
        )

        result = []
        for trade, trader_name in trades:
            result.append({
                "id": trade.id,
                "trader_id": trade.trader_id,
                "trader_name": trader_name,
                "symbol": trade.symbol,
                "coin": trade.coin,
                "side": trade.side,
                "quantity": trade.quantity,
                "price": trade.price,
                "uncertainty": trade.uncertainty,
                "order_id": trade.order_id,
                "success": trade.success,
                "error_message": trade.error_message,
                "executed_at": trade.executed_at.isoformat() if trade.executed_at else None
            })
        
        return jsonify({"trades": result}), 200


@dashboard_bp.route('/api-logs', methods=['GET'])
@jwt_required()
def get_api_logs():
    """
    Get recent API call logs for all user trading models.
    
    Query params:
        - limit: Number of logs to return (default: 50)
        - trader_id: Optional filter by trader ID
    
    Returns:
        JSON response containing a list of API call logs
    """
    user_id = get_jwt_identity()
    if not isinstance(user_id, str):
        return jsonify({"error": "Invalid token format"}), 401

    limit = request.args.get('limit', 50, type=int)
    trader_id = request.args.get('trader_id', type=int)
    
    with get_session() as session:
        query = (
            session.query(APICallLog, UserModel.name.label('trader_name'))
            .join(UserModel, APICallLog.trader_id == UserModel.id)
            .filter(APICallLog.user_id == user_id)
        )
        
        if trader_id:
            query = query.filter(APICallLog.trader_id == trader_id)
        
        logs = (
            query
            .order_by(desc(APICallLog.created_at))
            .limit(limit)
            .all()
        )

        result = []
        for log, trader_name in logs:
            result.append({
                "id": log.id,
                "trader_id": log.trader_id,
                "trader_name": trader_name,
                "model_name": log.model_name,
                "prompt": log.prompt,
                "prompt_length": log.prompt_length,
                "response": log.response,
                "decision_coin": log.decision_coin,
                "decision_action": log.decision_action,
                "decision_uncertainty": log.decision_uncertainty,
                "decision_quantity": log.decision_quantity,
                "tokens_used": log.tokens_used,
                "latency_ms": log.latency_ms,
                "success": log.success,
                "error_message": log.error_message,
                "created_at": log.created_at.isoformat() if log.created_at else None
            })
        
        return jsonify({"logs": result}), 200


@dashboard_bp.route('/execute', methods=['POST'])
@jwt_required()
def execute_traders():
    """
    Execute all active traders for the current user.
    
    Request Body (optional):
        - trader_id: Optional specific trader ID to execute (if not provided, executes all active traders)
    
    Returns:
        JSON response containing execution results
    """
    user_id = get_jwt_identity()
    if not isinstance(user_id, str):
        return jsonify({"error": "Invalid token format"}), 401
    
    data = request.get_json() or {}
    trader_id = data.get('trader_id')
    
    try:
        with get_session() as session:
            if trader_id:
                # Execute specific trader
                trader = session.query(UserModel).filter(
                    UserModel.id == trader_id,
                    UserModel.user_id == user_id,
                    UserModel.active == True
                ).first()
                
                if not trader:
                    return jsonify({"error": "Trader not found or not active"}), 404
                
                result = execute_trader(trader)
                return jsonify({
                    "success": True,
                    "results": [result]
                }), 200
            else:
                # Execute all active traders for this user
                active_traders = session.query(UserModel).filter(
                    UserModel.user_id == user_id,
                    UserModel.active == True
                ).all()
                
                if not active_traders:
                    return jsonify({
                        "success": True,
                        "message": "No active traders found",
                        "results": []
                    }), 200
                
                results = []
                for trader in active_traders:
                    try:
                        result = execute_trader(trader)
                        results.append(result)
                    except Exception as e:
                        results.append({
                            "success": False,
                            "trader_id": trader.id,
                            "trader_name": trader.name,
                            "error": str(e)
                        })
                
                return jsonify({
                    "success": True,
                    "results": results,
                    "total_executed": len(results)
                }), 200
                
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@dashboard_bp.route('/positions', methods=['GET'])
@jwt_required()
def get_positions():
    """
    Get current positions for all active traders.
    
    Returns:
        JSON response containing position data grouped by coin
    """
    user_id = get_jwt_identity()
    if not isinstance(user_id, str):
        return jsonify({"error": "Invalid token format"}), 401
    
    try:
        with get_session() as session:
            # Get all active traders for the user
            active_traders = session.query(UserModel).filter(
                UserModel.user_id == user_id,
                UserModel.active == True
            ).all()
            
            if not active_traders:
                return jsonify({"positions": []}), 200
            
            # Get all trades for these traders
            trader_ids = [trader.id for trader in active_traders]
            trades = (
                session.query(Trade)
                .filter(Trade.trader_id.in_(trader_ids), Trade.success == True)
                .order_by(Trade.executed_at.desc())
                .all()
            )
            
            # Calculate positions by coin
            positions_by_coin: Dict[str, Dict[str, Any]] = {}
            
            for trade in trades:
                coin = trade.coin
                if coin not in positions_by_coin:
                    positions_by_coin[coin] = {
                        "coin": coin,
                        "total_quantity": 0.0,
                        "total_value": 0.0,
                        "avg_price": 0.0,
                        "buy_count": 0,
                        "sell_count": 0,
                        "hold_count": 0,
                        "last_trade": trade.executed_at.isoformat() if trade.executed_at else None
                    }
                
                pos = positions_by_coin[coin]
                
                if trade.side == "buy":
                    pos["total_quantity"] += trade.quantity
                    pos["total_value"] += trade.quantity * trade.price
                    pos["buy_count"] += 1
                elif trade.side == "sell":
                    pos["total_quantity"] -= trade.quantity
                    pos["total_value"] -= trade.quantity * trade.price
                    pos["sell_count"] += 1
                else:  # hold
                    pos["hold_count"] += 1
                
                # Calculate average price
                if pos["total_quantity"] > 0:
                    pos["avg_price"] = pos["total_value"] / pos["total_quantity"]
                else:
                    pos["avg_price"] = 0.0
            
            # Filter out zero positions and format
            positions = []
            for coin, pos_data in positions_by_coin.items():
                if pos_data["total_quantity"] > 0:
                    positions.append(pos_data)
            
            # Sort by total value descending
            positions.sort(key=lambda x: x["total_value"], reverse=True)
            
            return jsonify({"positions": positions}), 200
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@dashboard_bp.route('/balance-history', methods=['GET'])
@jwt_required()
def get_balance_history():
    """
    Get balance history over time with trade execution markers.
    
    Query params:
        - days: Number of days to look back (default: 7)
    
    Returns:
        JSON response containing balance history data points
    """
    user_id = get_jwt_identity()
    if not isinstance(user_id, str):
        return jsonify({"error": "Invalid token format"}), 401
    
    days = request.args.get('days', 7, type=int)
    
    try:
        with get_session() as session:
            # Get broker connection for current portfolio value
            from layers.execution import get_broker_connection
            from layers.broker_factory import create_broker
            
            connection = get_broker_connection(user_id)
            current_portfolio_value = 0.0
            
            if connection:
                try:
                    broker = create_broker(connection)
                    current_portfolio_value = broker.get_balance()
                except Exception:
                    pass
            
            # Get all traders for the user (active or not, for trade history)
            all_traders = session.query(UserModel).filter(
                UserModel.user_id == user_id
            ).all()
            
            trader_ids = [trader.id for trader in all_traders] if all_traders else []
            
            # Get all successful trades
            trades = []
            if trader_ids:
                trades = (
                    session.query(Trade)
                    .filter(Trade.trader_id.in_(trader_ids), Trade.success == True)
                    .order_by(Trade.executed_at.asc())
                    .all()
                )
            
            # If no trades and no broker, return empty
            if not trades and current_portfolio_value == 0:
                return jsonify({"history": [], "trades": []}), 200
            
            # Get active traders for reference
            active_traders = [t for t in all_traders if t.active]
            current_balance = current_portfolio_value
            
            # Calculate the initial balance by working backwards from current portfolio value
            # First, calculate the net realized P&L from all trades
            net_realized_pnl = 0.0
            for trade in trades:
                if trade.side == "buy":
                    # When we buy, we spend money (negative impact on cash)
                    net_realized_pnl -= trade.quantity * trade.price
                elif trade.side == "sell":
                    # When we sell, we receive money (positive impact on cash)
                    net_realized_pnl += trade.quantity * trade.price
            
            # Initial balance = current balance - net P&L
            # If current_portfolio_value is available, use it; otherwise fall back to trader start balances
            if current_portfolio_value > 0:
                initial_balance = current_portfolio_value - net_realized_pnl
            else:
                initial_balance = sum(trader.start_balance for trader in active_traders) if active_traders else 0
            
            # Ensure initial balance is positive
            initial_balance = max(initial_balance, 0)
            
            # If no trades, just return current portfolio value as a flat line
            if not trades and current_portfolio_value > 0:
                end_date = datetime.now()
                start_date = end_date - timedelta(days=days)
                
                balance_history = []
                for i in range(days + 1):
                    date = start_date + timedelta(days=i)
                    balance_history.append({
                        "date": date.strftime('%Y-%m-%d'),
                        "balance": current_portfolio_value,
                        "timestamp": date.isoformat()
                    })
                
                return jsonify({
                    "history": balance_history,
                    "trades": []
                }), 200
            
            # Get current market prices for position valuation
            from db.db_models import MarketData
            market_prices = {}
            market_data_entries = session.query(MarketData).all()
            for entry in market_data_entries:
                market_prices[entry.coin_name] = entry.current_price
            
            # Build balance history from trades
            # Track positions over time: {coin: quantity}
            positions = {}
            usdt_balance = initial_balance
            
            balance_history = []
            
            # Get date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Create daily data points
            trade_index = 0
            for i in range(days + 1):
                date = start_date + timedelta(days=i)
                date_str = date.strftime('%Y-%m-%d')
                
                # Process all trades up to this date
                while trade_index < len(trades):
                    trade = trades[trade_index]
                    trade_date = trade.executed_at
                    if trade_date and trade_date.date() <= date.date():
                        # Apply trade to balance and positions
                        coin = trade.coin
                        if coin not in positions:
                            positions[coin] = 0.0
                        
                        if trade.side == "buy":
                            # Buying: reduce USDT, increase position
                            usdt_balance -= trade.quantity * trade.price
                            positions[coin] += trade.quantity
                        elif trade.side == "sell":
                            # Selling: increase USDT, decrease position
                            usdt_balance += trade.quantity * trade.price
                            positions[coin] -= trade.quantity
                            if positions[coin] < 0:
                                positions[coin] = 0.0
                        # hold doesn't change balance or positions
                        trade_index += 1
                    else:
                        break
                
                # Calculate total account value: USDT + position values at current market prices
                # This shows how account value evolves based on current positions
                total_value = usdt_balance
                for coin, quantity in positions.items():
                    if quantity > 0:
                        # Use current market price to value positions
                        # This shows account value based on current position valuations
                        current_price = market_prices.get(coin, 0)
                        if current_price > 0:
                            total_value += quantity * current_price
                        else:
                            # Fallback: use last trade price for this coin if market price not available
                            for trade in reversed(trades[:trade_index]):
                                if trade.coin == coin:
                                    total_value += quantity * trade.price
                                    break
                
                balance_history.append({
                    "date": date_str,
                    "balance": max(0, total_value),
                    "timestamp": date.isoformat()
                })
            
            # Use actual broker balance for the most recent (current) data point
            # This ensures the chart ends at the real portfolio value
            if current_portfolio_value > 0 and balance_history:
                # Calculate the adjustment factor to scale historical values correctly
                # This ensures the chart ends at the actual broker balance
                calculated_current = balance_history[-1]["balance"]
                
                if calculated_current > 0:
                    # Scale factor to adjust all historical points so chart ends at actual value
                    scale_factor = current_portfolio_value / calculated_current
                    
                    # Apply scaling to make history consistent with current value
                    for point in balance_history:
                        point["balance"] = point["balance"] * scale_factor
                else:
                    # If calculated was 0, just set current to broker balance
                    balance_history[-1]["balance"] = current_portfolio_value
            
            # Format trades for markers
            trade_markers = []
            for trade in trades:
                if trade.executed_at:
                    trade_markers.append({
                        "id": trade.id,
                        "trader_id": trade.trader_id,
                        "coin": trade.coin,
                        "side": trade.side,
                        "quantity": trade.quantity,
                        "price": trade.price,
                        "timestamp": trade.executed_at.isoformat(),
                        "date": trade.executed_at.strftime('%Y-%m-%d')
                    })
            
            return jsonify({
                "history": balance_history,
                "trades": trade_markers,
                "initial_balance": initial_balance,
                "current_balance": current_balance if current_balance > 0 else balance_history[-1]["balance"] if balance_history else initial_balance
            }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@dashboard_bp.route('/cached', methods=['GET'])
@jwt_required()
def get_cached_dashboard():
    """
    Get cached dashboard data for instant loading.
    Returns cached data if available, otherwise returns empty with needs_refresh=true.
    """
    user_id = get_jwt_identity()
    if not isinstance(user_id, str):
        return jsonify({"error": "Invalid token format"}), 401
    
    cached = _get_cached_dashboard(user_id)
    
    if cached:
        return jsonify({
            "cached": True,
            "data": cached,
            "updated_at": cached.get("updated_at")
        }), 200
    else:
        return jsonify({
            "cached": False,
            "data": None,
            "needs_refresh": True
        }), 200


@dashboard_bp.route('/refresh', methods=['POST'])
@jwt_required()
def refresh_dashboard():
    """
    Fetch fresh dashboard data and update the cache.
    Returns all dashboard data in one response.
    """
    user_id = get_jwt_identity()
    if not isinstance(user_id, str):
        return jsonify({"error": "Invalid token format"}), 401
    
    try:
        result = {
            "broker_balances": [],
            "trades": [],
            "api_logs": [],
            "balance_history": [],
            "traders": [],
        }
        
        with get_session() as session:
            # 1. Fetch broker balances (the slow part - external API calls)
            connections = session.query(BrokerConnection).filter(
                BrokerConnection.user_id == user_id,
                BrokerConnection.is_connected == True
            ).all()
            
            for conn in connections:
                broker_data = {
                    "id": conn.id,
                    "exchange": conn.exchange,
                    "is_testnet": conn.is_testnet,
                    "main_wallet_address": conn.main_wallet_address[:10] + "..." + conn.main_wallet_address[-6:] if conn.main_wallet_address else None,
                    "available_balance": 0.0,
                    "total_value": 0.0,
                    "perps_margin": 0.0,
                    "spot_balances": [],
                    "perp_positions": [],
                    "error": None
                }
                
                try:
                    if conn.exchange == "hyperliquid" and conn.main_wallet_address and conn.encrypted_agent_wallet_private_key:
                        agent_private_key = decrypt(conn.encrypted_agent_wallet_private_key)
                        broker = HyperliquidBroker(
                            conn.main_wallet_address,
                            agent_private_key,
                            testnet=conn.is_testnet
                        )
                        balances = broker.get_all_balances()
                        broker_data["available_balance"] = balances.get("available_balance", 0.0)
                        broker_data["total_value"] = balances.get("total_value", 0.0)
                        broker_data["perps_margin"] = balances.get("perps_margin", 0.0)
                        broker_data["spot_balances"] = balances.get("spot_balances", [])
                        broker_data["perp_positions"] = balances.get("perp_positions", [])
                except Exception as e:
                    logger.error(f"Error fetching broker balance: {e}")
                    broker_data["error"] = str(e)
                
                result["broker_balances"].append(broker_data)
            
            # 2. Fetch recent trades
            trades = (
                session.query(Trade, UserModel.name.label('trader_name'), UserModel.stop_loss_pct, UserModel.take_profit_pct, UserModel.default_leverage)
                .join(UserModel, Trade.trader_id == UserModel.id)
                .filter(Trade.user_id == user_id)
                .order_by(desc(Trade.executed_at))
                .limit(50)
                .all()
            )

            for trade, trader_name, stop_loss_pct, take_profit_pct, leverage in trades:
                result["trades"].append({
                    "id": trade.id,
                    "trader_id": trade.trader_id,
                    "trader_name": trader_name,
                    "symbol": trade.symbol,
                    "coin": trade.coin,
                    "side": trade.side,
                    "quantity": trade.quantity,
                    "price": trade.price,
                    "uncertainty": trade.uncertainty,
                    "order_id": trade.order_id,
                    "success": trade.success,
                    "error_message": trade.error_message,
                    "executed_at": trade.executed_at.isoformat() if trade.executed_at else None,
                    "stop_loss_pct": stop_loss_pct,
                    "take_profit_pct": take_profit_pct,
                    "leverage": leverage,
                    "stop_loss_order": json.loads(trade.stop_loss_order) if trade.stop_loss_order else None,
                    "take_profit_order": json.loads(trade.take_profit_order) if trade.take_profit_order else None
                })
            
            # 3. Fetch API logs
            logs = (
                session.query(APICallLog, UserModel.name.label('trader_name'))
                .join(UserModel, APICallLog.trader_id == UserModel.id)
                .filter(APICallLog.user_id == user_id)
                .order_by(desc(APICallLog.created_at))
                .limit(50)
                .all()
            )
            
            for log, trader_name in logs:
                result["api_logs"].append({
                    "id": log.id,
                    "trader_id": log.trader_id,
                    "trader_name": trader_name,
                    "model_name": log.model_name,
                    "prompt": log.prompt,
                    "prompt_length": log.prompt_length,
                    "response": log.response,
                    "decision_coin": log.decision_coin,
                    "decision_action": log.decision_action,
                    "decision_uncertainty": log.decision_uncertainty,
                    "decision_quantity": log.decision_quantity,
                    "tokens_used": log.tokens_used,
                    "latency_ms": log.latency_ms,
                    "success": log.success,
                    "error_message": log.error_message,
                    "created_at": log.created_at.isoformat() if log.created_at else None
                })
            
            # 4. Fetch traders
            traders = session.query(UserModel).filter(UserModel.user_id == user_id).all()
            for trader in traders:
                result["traders"].append({
                    "id": trader.id,
                    "name": trader.name,
                    "active": trader.active,
                    "balance": trader.balance,
                    "start_balance": trader.start_balance,
                    "tickers": trader.tickers,
                    "created_at": trader.created_at.isoformat() if trader.created_at else None
                })
        
        # 5. Calculate balance history (simplified - use current total value)
        total_portfolio_value = sum(b.get("total_value", 0) for b in result["broker_balances"])
        today = datetime.now().strftime('%Y-%m-%d')
        result["balance_history"] = [{
            "date": today,
            "balance": total_portfolio_value,
            "timestamp": datetime.now().isoformat()
        }]
        
        # Save to cache
        _save_dashboard_cache(user_id, result)
        
        return jsonify({
            "success": True,
            "data": result,
            "updated_at": datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"Error refreshing dashboard: {e}")
        return jsonify({"error": str(e)}), 500