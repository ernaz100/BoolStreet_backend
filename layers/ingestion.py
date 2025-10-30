"""Ingestion layer for market data used by BoolStreet.

This module pulls recent OHLCV candles for a fixed list of crypto symbols
from a ccxt exchange (defaulting to Binance), computes a small set of
technical indicators via pandas_ta, and emits a JSON-shaped payload suitable
for dashboards or downstream services.

Limit configuration overview:
- INTRADAY_LIMIT: Number of most-recent candles to fetch for the intraday
  timeframe used in this module ("3m" in main()). With the default value of 50,
  that is 50 × 3 minutes = 150 minutes (~2.5 hours) of history.
- FOUR_HOUR_LIMIT: Number of most-recent candles to fetch for the 4-hour
  timeframe ("4h" in main()). With the default value of 50, that is 50 × 4
  hours = 200 hours (~8.3 days) of history.

Trade-offs: Increasing either limit expands the lookback window, which can make
indicators more stable and provide more context, but it will take longer to
download and may be constrained by the exchange's rate limits or historical
data availability for a given symbol/timeframe.
"""

import ccxt
import pandas as pd
import pandas_ta as ta
import json
from datetime import datetime
from db.database import get_session
from db.db_models import MarketData

# --------------------------
# CONFIG
# --------------------------
EXCHANGE = ccxt.binance()  # ccxt exchange client; swap to another ccxt exchange if needed
SYMBOLS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT", "DOGE/USDT"]

# How many recent candles to request per timeframe used in main():
# - INTRADAY_LIMIT applies to timeframe "3m" (50 × 3m = 150 minutes at default)
# - FOUR_HOUR_LIMIT applies to timeframe "4h" (50 × 4h = 200 hours at default)
# Larger limits increase context/stability but take longer and may hit rate limits.
INTRADAY_LIMIT = 50
FOUR_HOUR_LIMIT = 50


def fetch_ohlcv(symbol: str, timeframe: str, limit: int):
    """Fetch recent OHLCV candles for a symbol/timeframe.

    Parameters
    - symbol: Pair in ccxt format (e.g., "BTC/USDT").
    - timeframe: ccxt timeframe string (e.g., "3m", "1h", "4h").
    - limit: Number of most-recent candles to fetch (exchange-dependent caps may apply).

    Returns
    - pandas.DataFrame with columns [timestamp, open, high, low, close, volume], where
      timestamp is converted to UTC pandas datetime.
    """
    data = EXCHANGE.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
    df = pd.DataFrame(data, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def build_indicators(df):
    """Compute core technical indicators and append them as columns.

    Adds the following columns:
    - ema20: 20-period EMA of close
    - macd: MACD line (12, 26, 9) on close
    - rsi7: 7-period RSI of close
    - rsi14: 14-period RSI of close
    - atr3: 3-period ATR
    - atr14: 14-period ATR
    """
    df["ema20"] = ta.ema(df["close"], length=20)
    macd = ta.macd(df["close"], fast=12, slow=26, signal=9)
    df["macd"] = macd["MACD_12_26_9"]
    df["rsi7"] = ta.rsi(df["close"], length=7)
    df["rsi14"] = ta.rsi(df["close"], length=14)
    df["atr3"] = ta.atr(df["high"], df["low"], df["close"], length=3)
    df["atr14"] = ta.atr(df["high"], df["low"], df["close"], length=14)
    return df


def format_coin(symbol, intraday_df, fourhour_df):
    """Format a single symbol's latest state and context into the output schema.

    Produces a nested dictionary keyed by the coin ticker that includes:
    - current_price, current_ema20, current_macd, current_rsi (7)
    - Intraday series (last 10 values for price/EMA/MACD/RSI on 3m timeframe)
    - Longer-term context on 4h timeframe (EMA20/EMA50, ATR3/ATR14, volume stats,
      MACD series, RSI14 series)
    """
    coin = symbol.split("/")[0]

    return {
        f"ALL {coin} DATA": {
            "current_price": float(intraday_df["close"].iloc[-1]),
            "current_ema20": float(intraday_df["ema20"].iloc[-1]),
            "current_macd": float(intraday_df["macd"].iloc[-1]),
            "current_rsi (7 period)": float(intraday_df["rsi7"].iloc[-1]),
            "Intraday series (by minute, oldest → latest)": {
                "Mid prices": intraday_df["close"].tail(10).round(4).tolist(),
                "EMA indicators (20-period)": intraday_df["ema20"].tail(10).round(4).tolist(),
                "MACD indicators": intraday_df["macd"].tail(10).round(4).tolist(),
                "RSI indicators (7-Period)": intraday_df["rsi7"].tail(10).round(4).tolist(),
                "RSI indicators (14-Period)": intraday_df["rsi14"].tail(10).round(4).tolist(),
            },
            "Longer-term context (4-hour timeframe)": {
                "20-Period EMA": float(fourhour_df["ema20"].iloc[-1]),
                "50-Period EMA": float(ta.ema(fourhour_df["close"], length=50).iloc[-1]),
                "3-Period ATR": float(fourhour_df["atr3"].iloc[-1]),
                "14-Period ATR": float(fourhour_df["atr14"].iloc[-1]),
                "Current Volume": float(fourhour_df["volume"].iloc[-1]),
                "Average Volume": float(fourhour_df["volume"].mean()),
                "MACD indicators": fourhour_df["macd"].tail(10).round(4).tolist(),
                "RSI indicators (14-Period)": fourhour_df["rsi14"].tail(10).round(4).tolist(),
            },
        }
    }


def fetch_and_save_market_data():
    """Fetch latest market data for all symbols and save to database.
    
    This function fetches market data from the exchange API and stores it
    in the database. It should be called periodically (e.g., every hour).
    """
    print(f"[{datetime.now()}] Starting market data sync...")
    
    try:
        with get_session() as session:
            # Fetch data for each symbol
            for symbol in SYMBOLS:
                try:
                    # Fetch intraday data (3m timeframe) for current price
                    intraday_df = fetch_ohlcv(symbol, "3m", INTRADAY_LIMIT)
                    intraday_df = build_indicators(intraday_df)
                    
                    # Fetch 1-hour data to get price from 24 hours ago
                    hourly_df = fetch_ohlcv(symbol, "1h", 24)
                    
                    # Get current price
                    current_price = float(intraday_df["close"].iloc[-1])
                    
                    # Get price from 24 hours ago (first candle in the hourly dataframe)
                    price_24h_ago = float(hourly_df["close"].iloc[0]) if len(hourly_df) > 0 else current_price
                    
                    # Calculate 24-hour percentage change
                    percentage_change = ((current_price - price_24h_ago) / price_24h_ago * 100) if price_24h_ago > 0 else 0.0
                    
                    # Fetch 4-hour data for OHLCV context
                    fourhour_df = fetch_ohlcv(symbol, "4h", FOUR_HOUR_LIMIT)
                    fourhour_df = build_indicators(fourhour_df)
                    
                    # Get OHLCV data from 4-hour timeframe (most recent candle)
                    latest_4h = fourhour_df.iloc[-1]
                    open_price = float(latest_4h["open"])
                    high_price = float(latest_4h["high"])
                    low_price = float(latest_4h["low"])
                    volume = float(latest_4h["volume"])
                    
                    coin_name = symbol.split("/")[0]
                    
                    # Fetch 24h history data (96 candles of 15-minute data)
                    history_df = fetch_ohlcv(symbol, "15m", 96)
                    history_24h = [
                        {
                            "timestamp": row["timestamp"].isoformat() if hasattr(row["timestamp"], 'isoformat') else str(row["timestamp"]),
                            "price": float(row["close"])
                        }
                        for _, row in history_df.iterrows()
                    ]
                    
                    # Delete old entries for this symbol (keep only the latest)
                    session.query(MarketData).filter(MarketData.symbol == symbol).delete()
                    
                    # Create new market data entry
                    market_data_entry = MarketData(
                        symbol=symbol,
                        coin_name=coin_name,
                        current_price=current_price,
                        open_price=open_price,
                        high_price=high_price,
                        low_price=low_price,
                        volume=volume,
                        percentage_change=percentage_change,
                        trend="up" if percentage_change >= 0 else "down",
                        history_24h=json.dumps(history_24h),
                        created_at=datetime.now()
                    )
                    
                    session.add(market_data_entry)
                    print(f"  ✓ Saved market data for {symbol}")
                    
                except Exception as e:
                    print(f"  ✗ Error fetching data for {symbol}: {str(e)}")
                    continue
            
            session.commit()
            print(f"[{datetime.now()}] Market data sync completed successfully.")
        
    except Exception as e:
        print(f"[{datetime.now()}] Error during market data sync: {str(e)}")
        raise


