import json
import pandas as pd
import pandas_ta as ta
from datetime import datetime, timedelta
from flask import Blueprint, jsonify, request
from layers.ingestion import SYMBOLS, fetch_ohlcv, build_indicators, fetch_and_save_market_data
from db.database import get_session
from db.db_models import MarketData, BTCHistoryCache
import threading

# Create a Blueprint for market data routes
market_data_bp = Blueprint('market_data', __name__)

# Supported coins for live data fetching
SUPPORTED_COINS = {
    "BTC": "BTC/USDT",
    "ETH": "ETH/USDT",
    "SOL": "SOL/USDT",
    "DOGE": "DOGE/USDT",
    "XRP": "XRP/USDT",
    "BNB": "BNB/USDT",
    "ARB": "ARB/USDT",
    "AVAX": "AVAX/USDT",
    "LINK": "LINK/USDT",
    "MATIC": "MATIC/USDT",
}

# Lock to prevent concurrent refreshes
_refresh_lock = threading.Lock()
_last_refresh_time = None


def get_latest_market_data():
    """Get latest market data for all symbols from the database.
    
    Returns a dictionary with symbol as key and data dict as value.
    """
    market_data = {}
    updated_at = None
    
    try:
        with get_session() as session:
            # Fetch all market data entries from database
            db_entries = session.query(MarketData).all()
            
            for entry in db_entries:
                market_data[entry.symbol] = {
                    "symbol": entry.coin_name,
                    "name": entry.coin_name,
                    "current_price": entry.current_price,
                    "open_price": entry.open_price,
                    "high_price": entry.high_price,
                    "low_price": entry.low_price,
                    "volume": entry.volume,
                    "percentage_change": entry.percentage_change,
                    "trend": entry.trend,
                    "history_24h": entry.history_24h
                }
                # Track the most recent update time
                if entry.created_at:
                    if updated_at is None or entry.created_at > updated_at:
                        updated_at = entry.created_at
    except Exception as e:
        print(f"Error fetching market data from database: {str(e)}")
    
    return market_data, updated_at


@market_data_bp.route('/cached', methods=['GET'])
def get_cached_market_data():
    """Get cached market data for instant loading.
    
    Returns cached market overview and 24h history data from the database.
    This is fast as it doesn't make external API calls.
    """
    try:
        market_data, updated_at = get_latest_market_data()
        
        # Convert to frontend format (overview)
        overview = []
        history_data = {}
        
        for symbol, data in market_data.items():
            overview.append({
                "name": data["name"],
                "value": f"${data['current_price']:,.2f}",
                "change": f"{data['percentage_change']:+.2f}%",
                "trend": data["trend"]
            })
            
            # Parse history
            if data.get("history_24h"):
                try:
                    history_data[data["name"]] = json.loads(data["history_24h"])
                except:
                    history_data[data["name"]] = []
            else:
                history_data[data["name"]] = []
        
        # Sort by absolute percentage change
        overview.sort(key=lambda x: abs(float(x["change"].replace("%", "").replace("+", ""))), reverse=True)
        
        return jsonify({
            "cached": True,
            "overview": overview,
            "history": history_data,
            "updated_at": updated_at.isoformat() if updated_at else None
        }), 200
        
    except Exception as e:
        return jsonify({"error": f"Failed to fetch cached data: {str(e)}"}), 500


@market_data_bp.route('/refresh', methods=['POST'])
def refresh_market_data():
    """Refresh market data from external APIs.
    
    This endpoint triggers a fresh fetch from the exchange APIs and updates the cache.
    Returns the fresh data once complete.
    
    Rate limited: only allows refresh if last refresh was > 30 seconds ago.
    """
    global _last_refresh_time
    
    try:
        # Rate limiting - prevent too frequent refreshes
        now = datetime.now()
        if _last_refresh_time:
            time_since_refresh = (now - _last_refresh_time).total_seconds()
            if time_since_refresh < 30:
                # Return cached data instead
                market_data, updated_at = get_latest_market_data()
                overview = []
                history_data = {}
                
                for symbol, data in market_data.items():
                    overview.append({
                        "name": data["name"],
                        "value": f"${data['current_price']:,.2f}",
                        "change": f"{data['percentage_change']:+.2f}%",
                        "trend": data["trend"]
                    })
                    if data.get("history_24h"):
                        try:
                            history_data[data["name"]] = json.loads(data["history_24h"])
                        except:
                            history_data[data["name"]] = []
                
                overview.sort(key=lambda x: abs(float(x["change"].replace("%", "").replace("+", ""))), reverse=True)
                
                return jsonify({
                    "cached": True,
                    "rate_limited": True,
                    "overview": overview,
                    "history": history_data,
                    "updated_at": updated_at.isoformat() if updated_at else None,
                    "next_refresh_in": int(30 - time_since_refresh)
                }), 200
        
        # Try to acquire lock (non-blocking)
        if not _refresh_lock.acquire(blocking=False):
            # Another refresh is in progress, return cached data
            market_data, updated_at = get_latest_market_data()
            overview = []
            history_data = {}
            
            for symbol, data in market_data.items():
                overview.append({
                    "name": data["name"],
                    "value": f"${data['current_price']:,.2f}",
                    "change": f"{data['percentage_change']:+.2f}%",
                    "trend": data["trend"]
                })
                if data.get("history_24h"):
                    try:
                        history_data[data["name"]] = json.loads(data["history_24h"])
                    except:
                        history_data[data["name"]] = []
            
            overview.sort(key=lambda x: abs(float(x["change"].replace("%", "").replace("+", ""))), reverse=True)
            
            return jsonify({
                "cached": True,
                "refresh_in_progress": True,
                "overview": overview,
                "history": history_data,
                "updated_at": updated_at.isoformat() if updated_at else None
            }), 200
        
        try:
            # Fetch fresh data from exchange
            fetch_and_save_market_data()
            _last_refresh_time = datetime.now()
            
            # Get the fresh data
            market_data, updated_at = get_latest_market_data()
            
            # Convert to frontend format
            overview = []
            history_data = {}
            
            for symbol, data in market_data.items():
                overview.append({
                    "name": data["name"],
                    "value": f"${data['current_price']:,.2f}",
                    "change": f"{data['percentage_change']:+.2f}%",
                    "trend": data["trend"]
                })
                if data.get("history_24h"):
                    try:
                        history_data[data["name"]] = json.loads(data["history_24h"])
                    except:
                        history_data[data["name"]] = []
            
            overview.sort(key=lambda x: abs(float(x["change"].replace("%", "").replace("+", ""))), reverse=True)
            
            return jsonify({
                "cached": False,
                "overview": overview,
                "history": history_data,
                "updated_at": updated_at.isoformat() if updated_at else datetime.now().isoformat()
            }), 200
            
        finally:
            _refresh_lock.release()
            
    except Exception as e:
        print(f"Error refreshing market data: {str(e)}")
        return jsonify({"error": f"Failed to refresh data: {str(e)}"}), 500


@market_data_bp.route('/top-movers', methods=['GET'])
def get_top_movers():
    """Get market overview/top movers.
    
    Returns an array of market overview items with name, value, change, and trend.
    """
    try:
        market_data, _ = get_latest_market_data()
        
        # Convert to frontend format
        overview = []
        for symbol, data in market_data.items():
            overview.append({
                "name": data["name"],
                "value": f"${data['current_price']:,.2f}",
                "change": f"{data['percentage_change']:+.2f}%",
                "trend": data["trend"]
            })
        
        # Sort by absolute percentage change (descending) to show top movers
        overview.sort(key=lambda x: abs(float(x["change"].replace("%", "").replace("+", ""))), reverse=True)
        
        return jsonify(overview), 200
    except Exception as e:
        return jsonify({"error": f"Failed to fetch market data: {str(e)}"}), 500


@market_data_bp.route('/overview', methods=['GET'])
def get_market_overview():
    """Get detailed market data overview.
    
    Returns an array of market data items with symbol, name, price, change, volume, open, high, low.
    """
    try:
        market_data, _ = get_latest_market_data()
        
        # Convert to frontend format
        overview = []
        for symbol, data in market_data.items():
            overview.append({
                "symbol": data["symbol"],
                "name": data["name"],
                "price": f"${data['current_price']:,.2f}",
                "change": f"{data['percentage_change']:+.2f}%",
                "volume": f"{data['volume']:,.0f}",
                "open": f"${data['open_price']:,.2f}",
                "high": f"${data['high_price']:,.2f}",
                "low": f"${data['low_price']:,.2f}"
            })
        
        return jsonify(overview), 200
    except Exception as e:
        return jsonify({"error": f"Failed to fetch market data: {str(e)}"}), 500


@market_data_bp.route('/history/24h', methods=['GET'])
def get_24h_history():
    """Get 24-hour historical price data with 15-minute intervals for all symbols.
    
    Returns a dictionary with symbol as key and array of {timestamp, price} objects as value.
    Reads from cached database entries.
    """
    try:
        history_data = {}
        
        try:
            with get_session() as session:
                # Fetch all market data entries from database
                db_entries = session.query(MarketData).all()
                
                for entry in db_entries:
                    coin_name = entry.coin_name
                    # Parse the stored JSON history
                    if entry.history_24h:
                        history_data[coin_name] = json.loads(entry.history_24h)
                    else:
                        history_data[coin_name] = []
        except Exception as e:
            print(f"Error fetching 24h history from database: {str(e)}")
            return jsonify({"error": f"Failed to fetch 24h history: {str(e)}"}), 500
        
        return jsonify(history_data), 200
    except Exception as e:
        return jsonify({"error": f"Failed to fetch 24h history: {str(e)}"}), 500


@market_data_bp.route('/coin/<coin>/live', methods=['GET'])
def get_coin_live_data(coin: str):
    """Get live market data with indicators for a specific coin.
    
    This fetches real-time data from the exchange and calculates technical indicators.
    Used for LLM prompts and preview.
    
    Args:
        coin: Coin ticker (e.g., 'BTC', 'ETH', 'DOGE')
        
    Returns:
        JSON object with:
        - current_price, ema20, macd, rsi7, rsi14
        - intraday_series: Recent 3m candle data with indicators
        - fourhour_context: 4h timeframe data for longer-term context
        - formatted_prompt: Pre-formatted string for LLM prompt
    """
    try:
        coin_upper = coin.upper()
        
        if coin_upper not in SUPPORTED_COINS:
            return jsonify({
                "error": f"Unsupported coin: {coin}. Supported: {list(SUPPORTED_COINS.keys())}"
            }), 400
        
        symbol = SUPPORTED_COINS[coin_upper]
        
        # Fetch intraday data (3-minute candles)
        intraday_df = fetch_ohlcv(symbol, "3m", 50)
        intraday_df = build_indicators(intraday_df)
        
        # Fetch 4-hour data for longer-term context
        fourhour_df = fetch_ohlcv(symbol, "4h", 50)
        fourhour_df = build_indicators(fourhour_df)
        
        # Calculate 50-period EMA for 4h data
        ema50_4h = ta.ema(fourhour_df["close"], length=50)
        
        # Get latest values
        latest_intraday = intraday_df.iloc[-1]
        latest_4h = fourhour_df.iloc[-1]
        
        # Build response
        response_data = {
            "coin": coin_upper,
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "current": {
                "price": float(latest_intraday["close"]),
                "ema20": float(latest_intraday["ema20"]) if not pd.isna(latest_intraday["ema20"]) else None,
                "macd": float(latest_intraday["macd"]) if not pd.isna(latest_intraday["macd"]) else None,
                "rsi7": float(latest_intraday["rsi7"]) if not pd.isna(latest_intraday["rsi7"]) else None,
                "rsi14": float(latest_intraday["rsi14"]) if not pd.isna(latest_intraday["rsi14"]) else None,
            },
            "intraday_series": {
                "timeframe": "3m",
                "prices": intraday_df["close"].tail(10).round(4).tolist(),
                "ema20": intraday_df["ema20"].tail(10).round(4).tolist(),
                "macd": intraday_df["macd"].tail(10).round(4).tolist(),
                "rsi7": intraday_df["rsi7"].tail(10).round(4).tolist(),
                "rsi14": intraday_df["rsi14"].tail(10).round(4).tolist(),
            },
            "fourhour_context": {
                "timeframe": "4h",
                "ema20": float(latest_4h["ema20"]) if not pd.isna(latest_4h["ema20"]) else None,
                "ema50": float(ema50_4h.iloc[-1]) if not pd.isna(ema50_4h.iloc[-1]) else None,
                "atr3": float(latest_4h["atr3"]) if not pd.isna(latest_4h["atr3"]) else None,
                "atr14": float(latest_4h["atr14"]) if not pd.isna(latest_4h["atr14"]) else None,
                "current_volume": float(latest_4h["volume"]),
                "avg_volume": float(fourhour_df["volume"].mean()),
                "macd_series": fourhour_df["macd"].tail(10).round(4).tolist(),
                "rsi14_series": fourhour_df["rsi14"].tail(10).round(4).tolist(),
            },
            # Pre-formatted string for LLM prompt
            "formatted_prompt": _format_coin_for_prompt(
                coin_upper, intraday_df, fourhour_df, ema50_4h
            )
        }
        
        return jsonify(response_data), 200
        
    except Exception as e:
        print(f"Error fetching live data for {coin}: {str(e)}")
        return jsonify({"error": f"Failed to fetch live data: {str(e)}"}), 500


@market_data_bp.route('/coins/live', methods=['GET'])
def get_multiple_coins_live():
    """Get live market data for multiple coins at once.
    
    Query parameters:
        coins: Comma-separated list of coin tickers (e.g., 'BTC,ETH,DOGE')
        
    Returns:
        JSON object with data for each requested coin
    """
    try:
        coins_param = request.args.get('coins', '')
        if not coins_param:
            return jsonify({"error": "Missing 'coins' parameter"}), 400
        
        coins = [c.strip().upper() for c in coins_param.split(',')]
        
        # Validate coins
        invalid_coins = [c for c in coins if c not in SUPPORTED_COINS]
        if invalid_coins:
            return jsonify({
                "error": f"Unsupported coins: {invalid_coins}. Supported: {list(SUPPORTED_COINS.keys())}"
            }), 400
        
        results = {}
        formatted_prompts = []
        
        for coin in coins:
            symbol = SUPPORTED_COINS[coin]
            
            try:
                # Fetch data
                intraday_df = fetch_ohlcv(symbol, "3m", 50)
                intraday_df = build_indicators(intraday_df)
                
                fourhour_df = fetch_ohlcv(symbol, "4h", 50)
                fourhour_df = build_indicators(fourhour_df)
                
                ema50_4h = ta.ema(fourhour_df["close"], length=50)
                
                latest_intraday = intraday_df.iloc[-1]
                latest_4h = fourhour_df.iloc[-1]
                
                results[coin] = {
                    "symbol": symbol,
                    "current": {
                        "price": float(latest_intraday["close"]),
                        "ema20": float(latest_intraday["ema20"]) if not pd.isna(latest_intraday["ema20"]) else None,
                        "macd": float(latest_intraday["macd"]) if not pd.isna(latest_intraday["macd"]) else None,
                        "rsi7": float(latest_intraday["rsi7"]) if not pd.isna(latest_intraday["rsi7"]) else None,
                    },
                    "intraday_prices": intraday_df["close"].tail(10).round(2).tolist(),
                }
                
                # Add formatted prompt
                formatted_prompts.append(_format_coin_for_prompt(
                    coin, intraday_df, fourhour_df, ema50_4h
                ))
                
            except Exception as e:
                results[coin] = {"error": str(e)}
        
        return jsonify({
            "timestamp": datetime.now().isoformat(),
            "coins": results,
            "formatted_prompt": "\n\n".join(formatted_prompts)
        }), 200
        
    except Exception as e:
        print(f"Error fetching multiple coins: {str(e)}")
        return jsonify({"error": f"Failed to fetch data: {str(e)}"}), 500


def _format_coin_for_prompt(coin: str, intraday_df, fourhour_df, ema50_4h) -> str:
    """Format coin data as a string suitable for LLM prompts.
    
    This matches the format expected by the execution layer's prompt template.
    """
    latest = intraday_df.iloc[-1]
    latest_4h = fourhour_df.iloc[-1]
    
    # Handle NaN values
    def safe_float(val, decimals=5):
        if pd.isna(val):
            return "N/A"
        return f"{float(val):.{decimals}f}"
    
    return f"""ALL {coin} DATA

current_price = {safe_float(latest['close'])}, current_ema20 = {safe_float(latest['ema20'])}, current_macd = {safe_float(latest['macd'])}, current_rsi (7 period) = {safe_float(latest['rsi7'])}

Intraday series (3-minute intervals, oldest → latest):

Mid prices: {intraday_df['close'].tail(10).round(4).tolist()}

EMA indicators (20-period): {intraday_df['ema20'].tail(10).round(4).tolist()}

MACD indicators: {intraday_df['macd'].tail(10).round(4).tolist()}

RSI indicators (7-Period): {intraday_df['rsi7'].tail(10).round(4).tolist()}

RSI indicators (14-Period): {intraday_df['rsi14'].tail(10).round(4).tolist()}

Longer-term context (4-hour timeframe):

20-Period EMA: {safe_float(latest_4h['ema20'])} vs. 50-Period EMA: {safe_float(ema50_4h.iloc[-1])}

3-Period ATR: {safe_float(latest_4h['atr3'])} vs. 14-Period ATR: {safe_float(latest_4h['atr14'])}

Current Volume: {safe_float(latest_4h['volume'], 2)} vs. Average Volume: {safe_float(fourhour_df['volume'].mean(), 2)}

MACD indicators: {fourhour_df['macd'].tail(10).round(4).tolist()}

RSI indicators (14-Period): {fourhour_df['rsi14'].tail(10).round(4).tolist()}"""


@market_data_bp.route('/btc/history', methods=['GET'])
def get_btc_history():
    """Get BTC historical price data for different timeframes.
    
    Query parameters:
    - timeframe: '1W' (1 week), '1M' (1 month), or '3M' (3 months). Defaults to '1M'.
    
    Returns an array of {date, price} objects.
    Caches data in database and only fetches from exchange if data is older than 24 hours.
    """
    try:
        timeframe_param = request.args.get('timeframe', '1M').upper()
        
        # Map timeframe to exchange timeframe and limit
        timeframe_map = {
            '1W': ('1h', 168),  # 1 week = 168 hours, fetch hourly data
            '1M': ('4h', 180),  # 1 month ≈ 30 days = 720 hours, fetch 4h data (180 candles)
            '3M': ('1d', 90),   # 3 months ≈ 90 days, fetch daily data
        }
        
        if timeframe_param not in timeframe_map:
            return jsonify({"error": f"Invalid timeframe. Must be one of: 1W, 1M, 3M"}), 400
        
        exchange_timeframe, limit = timeframe_map[timeframe_param]
        
        # Check database first
        with get_session() as session:
            cache_entry = session.query(BTCHistoryCache).filter_by(timeframe=timeframe_param).first()
            
            # Check if we have cached data and if it's less than 24 hours old
            if cache_entry:
                age = datetime.now() - cache_entry.updated_at
                if age < timedelta(hours=24):
                    # Use cached data
                    history_data = json.loads(cache_entry.history_data)
                    return jsonify(history_data), 200
            
            # Fetch from exchange if cache is missing or stale
            btc_symbol = "BTC/USDT"
            df = fetch_ohlcv(btc_symbol, exchange_timeframe, limit)
            
            # Convert to frontend format: array of {date, price}
            history_data = []
            for _, row in df.iterrows():
                history_data.append({
                    "date": row["timestamp"].strftime("%m/%d/%Y"),
                    "price": float(row["close"])
                })
            
            # Save or update cache with proper upsert logic
            history_data_json = json.dumps(history_data)

            # Check again in case another request inserted while we were fetching
            existing = session.query(BTCHistoryCache).filter_by(timeframe=timeframe_param).first()

            if existing:
                # Update existing
                existing.history_data = history_data_json
                existing.updated_at = datetime.now()
            else:
                # Create new - but check one more time to handle race conditions
                try:
                    new_cache = BTCHistoryCache(
                        timeframe=timeframe_param,
                        history_data=history_data_json,
                        created_at=datetime.now(),
                        updated_at=datetime.now()
                    )
                    session.add(new_cache)
                except Exception as insert_error:
                    # If insert fails due to unique constraint, try update instead
                    if "UNIQUE constraint failed" in str(insert_error):
                        session.rollback()
                        existing = session.query(BTCHistoryCache).filter_by(timeframe=timeframe_param).first()
                        if existing:
                            existing.history_data = history_data_json
                            existing.updated_at = datetime.now()
                        else:
                            raise insert_error  # Re-raise if still no entry
                    else:
                        raise insert_error

            return jsonify(history_data), 200
            
    except Exception as e:
        print(f"Error fetching BTC history: {str(e)}")
        return jsonify({"error": f"Failed to fetch BTC history: {str(e)}"}), 500

