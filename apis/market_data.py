from flask import Blueprint, jsonify
from sqlalchemy import desc, func
from db.db_models import MarketData
from db.database import get_session
from datetime import datetime, timedelta

# Create a Blueprint for market data routes
market_data_bp = Blueprint('market_data', __name__)

@market_data_bp.route('/api/market/top-movers', methods=['GET'])
def get_top_movers():
    """
    Get top moving stocks
    Returns the 4 stocks with the highest percentage changes
    """
    try:
        db_session = get_session()
        # Get the latest market data for each index
        # Subquery: get the latest timestamp for each symbol
        subq = db_session.query(
            MarketData.symbol,
            func.max(MarketData.timestamp).label('max_timestamp')
        ).group_by(MarketData.symbol).subquery()

        # Join MarketData with the subquery to get the most recent row for each symbol
        latest_per_symbol = db_session.query(MarketData).join(
            subq,
            (MarketData.symbol == subq.c.symbol) &
            (MarketData.timestamp == subq.c.max_timestamp)
        ).order_by(desc(MarketData.percentage_change)).limit(4).all()
        
        if not latest_per_symbol:
            return jsonify({
                'error': 'No market data available'
            }), 404

        # Format the response
        market_overview = []
        for data in latest_per_symbol:
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

@market_data_bp.route('/api/market/overview', methods=['GET'])
def get_market_overview():
    """
    Get market overview data including major indices
    Returns the latest market data for major indices
    """
    try:
        db_session = get_session()
        # Subquery: get the latest timestamp for each symbol
        subq = db_session.query(
            MarketData.symbol,
            func.max(MarketData.timestamp).label('max_timestamp')
        ).group_by(MarketData.symbol).subquery()

        # Join MarketData with the subquery to get the most recent row for each symbol
        latest_per_symbol = db_session.query(MarketData).join(
            subq,
            (MarketData.symbol == subq.c.symbol) &
            (MarketData.timestamp == subq.c.max_timestamp)
        ).order_by(desc(MarketData.percentage_change)).all()
        
        if not latest_per_symbol:
            return jsonify({
                'error': 'No stock data available'
            }), 404

        # Format the response
        top_movers = []
        for data in latest_per_symbol:
            top_movers.append({
                'symbol': data.symbol,
                'name': data.company_name or data.symbol,  # Use symbol if company_name is not available
                'price': f"${data.current_value:.2f}",
                'change': f"{'+' if data.percentage_change >= 0 else ''}{data.percentage_change:.1f}%",
                'volume': f"{data.volume/1000000:.1f}M" if data.volume else "N/A",
                'open': f"${data.open_value:.2f}",
                'high': f"${data.high_value:.2f}",
                'low': f"${data.low_value:.2f}",

            })

        return jsonify(top_movers)

    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500 