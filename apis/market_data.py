from flask import Blueprint, jsonify
from db.models import MarketData
from db.database import get_session
from datetime import datetime, timedelta

# Create a Blueprint for market data routes
market_data_bp = Blueprint('market_data', __name__)

@market_data_bp.route('/api/market/overview', methods=['GET'])
def get_market_overview():
    """
    Get market overview data including major indices
    Returns the latest market data for major indices
    """
    try:
        db_session = get_session()
        # Get the latest market data for each index
        latest_data = db_session.query(MarketData)\
            .order_by(MarketData.timestamp.desc())\
            .limit(4)\
            .all()
        
        if not latest_data:
            return jsonify({
                'error': 'No market data available'
            }), 404

        # Format the response
        market_overview = []
        for data in latest_data:
            market_overview.append({
                'name': data.index_name or data.symbol,  # Use symbol if index_name is not available
                'value': f"${data.current_value:.2f}",
                'change': f"{'+' if data.percentage_change >= 0 else ''}{data.percentage_change:.1f}%",
                'trend': 'up' if data.percentage_change >= 0 else 'down'
            })

        return jsonify(market_overview)

    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500

@market_data_bp.route('/api/market/top-movers', methods=['GET'])
def get_top_movers():
    """
    Get top moving stocks
    Returns the stocks with the highest percentage changes
    """
    try:
        db_session = get_session()
        # Get the latest stock data
        latest_data = db_session.query(MarketData)\
            .order_by(MarketData.timestamp.desc())\
            .limit(5)\
            .all()
        
        if not latest_data:
            return jsonify({
                'error': 'No stock data available'
            }), 404

        # Format the response
        top_movers = []
        for data in latest_data:
            top_movers.append({
                'symbol': data.symbol,
                'name': data.company_name or data.symbol,  # Use symbol if company_name is not available
                'price': f"${data.current_value:.2f}",
                'change': f"{'+' if data.percentage_change >= 0 else ''}{data.percentage_change:.1f}%",
                'volume': f"{data.volume/1000000:.1f}M" if data.volume else "N/A"
            })

        return jsonify(top_movers)

    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500 