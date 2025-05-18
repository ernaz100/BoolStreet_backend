from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import os
import yfinance as yf

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Configure CORS
CORS(app)

# Basic configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-please-change-in-production')


@app.route('/', methods=['GET'])
def get_apple_stock():
    """
    Fetch Apple stock data using yfinance
    
    Returns:
        JSON response with Apple stock information
    """
    try:
        # Get Apple stock data
        apple = yf.Ticker("AAPL")
        
        # Get historical market data
        hist = apple.history(period="1mo")
        
        # Get stock info
        info = apple.info
        
        # Extract relevant data
        stock_data = {
            "symbol": "AAPL",
            "company_name": info.get('shortName', 'Apple Inc.'),
            "current_price": info.get('currentPrice', None),
            "market_cap": info.get('marketCap', None),
            "previous_close": info.get('previousClose', None),
            "open": info.get('open', None),
            "day_high": info.get('dayHigh', None),
            "day_low": info.get('dayLow', None),
            "fifty_day_avg": info.get('fiftyDayAverage', None),
            "two_hundred_day_avg": info.get('twoHundredDayAverage', None),
            "historical_data": {
                "dates": hist.index.strftime('%Y-%m-%d').tolist(),
                "closing_prices": hist['Close'].tolist(),
                "volumes": hist['Volume'].tolist()
            }
        }
        
        return jsonify(stock_data), 200
    except Exception as e:
        return jsonify({
            "error": "Failed to fetch Apple stock data",
            "message": str(e)
        }), 500

if __name__ == '__main__':
    # Run the app in debug mode if in development
    debug = os.getenv('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=5005, debug=debug) 