from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity
from dotenv import load_dotenv
import os
import yfinance as yf
from layers.ingestion import start_scheduler
from db.storage import init_db, drop_all
from apis.auth import auth_bp
from apis.scripts import scripts_bp
from apis.dashboard import dashboard_bp
from apis.market_data import market_data_bp

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Configure CORS
CORS(app, resources={r"/*": {"origins": "*"}})

# Basic configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-please-change-in-production')
app.config['JWT_TOKEN_LOCATION'] = ['headers']
app.config['JWT_HEADER_NAME'] = 'Authorization'
app.config['JWT_HEADER_TYPE'] = 'Bearer'
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=24)  # Set token expiration to 24 hours
app.config['JWT_ERROR_MESSAGE_KEY'] = 'message'  # Customize error message key

# Initialize JWT
jwt = JWTManager(app)

# Error handler for JWT errors
@jwt.invalid_token_loader
def invalid_token_callback(error_string):
    return jsonify({
        'message': 'Invalid token. Please log in again.',
        'error': error_string
    }), 401

@jwt.unauthorized_loader
def unauthorized_callback(error_string):
    return jsonify({
        'message': 'Missing token. Please log in.',
        'error': error_string
    }), 401

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(scripts_bp, url_prefix='/scripts')
app.register_blueprint(dashboard_bp, url_prefix='/dashboard')
app.register_blueprint(market_data_bp)

@app.route('/reset-db', methods=['POST'])
def reset_db():
    """Drop all tables and recreate them. Use with caution."""
    drop_all()
    init_db()
    return jsonify({"status": "Database reset complete"}), 200

if __name__ == '__main__':
    # Run the app in debug mode if in development
    drop_all()
    init_db()
    start_scheduler()
    debug = os.getenv('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=5005, debug=debug)