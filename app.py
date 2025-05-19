from datetime import datetime, timedelta
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager, jwt_required, get_jwt_identity
from dotenv import load_dotenv
import os
import yfinance as yf
from ingestion import start_scheduler
from storage import init_db, drop_all
from auth import auth_bp
from scripts import scripts_bp

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Configure CORS
CORS(app)

# Basic configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-please-change-in-production')
app.config['JWT_TOKEN_LOCATION'] = ['headers']
app.config['JWT_HEADER_NAME'] = 'Authorization'
app.config['JWT_HEADER_TYPE'] = 'Bearer'
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(hours=24)  # Set token expiration to 24 hours
jwt = JWTManager(app)

# Register blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(scripts_bp, url_prefix='/scripts')

@app.route('/reset-db', methods=['POST'])
def reset_db():
    """Drop all tables and recreate them. Use with caution."""
    drop_all()
    init_db()
    return jsonify({"status": "Database reset complete"}), 200

if __name__ == '__main__':
    # Run the app in debug mode if in development
    #drop_all()
    init_db()
    start_scheduler()
    debug = os.getenv('FLASK_ENV') == 'development'
    app.run(host='0.0.0.0', port=5005, debug=debug)