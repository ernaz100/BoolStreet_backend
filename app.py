from datetime import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
from dotenv import load_dotenv
import os
import yfinance as yf
from ingestion import start_scheduler
from executor import run_user_script
from storage import save_script, init_db, drop_all

# Load environment variables
load_dotenv()

# Initialize Flask app
app = Flask(__name__)

# Configure CORS
CORS(app)

# Basic configuration
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-please-change-in-production')


@app.route('/scripts', methods=['POST'])
def upload_script():
    """
    Upload a user strategy script.

    Expects multipart/form-data with:
    - 'file': the .py source file
    - 'name': user-friendly name (optional, defaults to filename)

    Returns:
        JSON response with script id and status
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    f = request.files['file']
    if f.filename == '':
        return jsonify({"error": "No file selected"}), 400

    name = request.form.get('name', f.filename)
    code = f.read().decode('utf-8')

    # quick validation – require a `def run(data):` entry point
    if "def run(" not in code:
        return jsonify({"error": "Script must expose a `run(data)` function"}), 400

    script_id = save_script(name, code)

    try:
        result, receipts = run_user_script(script_id)
        final = {
            "script_id": script_id,
            "script_name": name,
            "started_at": result["started_at"],
            "ended_at": result["ended_at"],
            "duration_secs": result["duration_secs"],
            "output": result["output"],
            "orders": receipts,
            "success": True
        }
    except Exception as exc:
        final = {
            "script_id": script_id,
            "script_name": name,
            "started_at": datetime.now().isoformat(),
            "ended_at": datetime.now().isoformat(),
            "duration_secs": 0,
            "output": str(exc),
            "success": False
        }
    status = "✅" if final["success"] else "❌"
    print(f"  • Script {final['script_id']} ({final['script_name']}) {status}: {final['output']}")
    return jsonify({"id": script_id, "status": "stored"}), 201

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