import json
from flask import Blueprint, jsonify
from layers.ingestion import SYMBOLS
from db.database import get_session
from db.db_models import MarketData

# Create a Blueprint for market data routes
market_data_bp = Blueprint('market_data', __name__)


def get_latest_market_data():
    """Get latest market data for all symbols from the database.
    
    Returns a dictionary with symbol as key and data dict as value.
    """
    market_data = {}
    
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
                    "trend": entry.trend
                }
    except Exception as e:
        print(f"Error fetching market data from database: {str(e)}")
    
    return market_data


@market_data_bp.route('/top-movers', methods=['GET'])
def get_top_movers():
    """Get market overview/top movers.
    
    Returns an array of market overview items with name, value, change, and trend.
    """
    try:
        market_data = get_latest_market_data()
        
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
        market_data = get_latest_market_data()
        
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

