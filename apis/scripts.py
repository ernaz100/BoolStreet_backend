from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from db.storage import save_script
from db.models import UserScript
from layers.executor import run_user_script
from db.database import get_session

# Create blueprint
scripts_bp = Blueprint('scripts', __name__)

@scripts_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_script():
    """
    Upload a user strategy script.

    Expects multipart/form-data with:
    - 'file': the .py source file
    - 'name': user-friendly name (optional, defaults to filename)
    - 'model_type': type of model (optional)

    Returns:
        JSON response with script id and status
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    f = request.files['file']
    if f.filename == '':
        return jsonify({"error": "No file selected"}), 400

    name = request.form.get('name', f.filename)
    model_type = request.form.get('model_type', '')
    code = f.read().decode('utf-8')

    # quick validation – require a `def run(data):` entry point
    if "def run(" not in code:
        return jsonify({"error": "Script must expose a `run(data)` function"}), 400

    # Get user ID from JWT token
    user_id = get_jwt_identity()
    if not isinstance(user_id, str):
        return jsonify({"error": "Invalid token format"}), 401

    script_id = save_script(name, code, user_id)
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

    return jsonify({
        "status": "success",
        "script_id": script_id
    }), 200

@scripts_bp.route('/list', methods=['GET'])
@jwt_required()
def get_user_scripts():
    """
    Fetch all scripts for the currently logged in user.
    
    Returns:
        JSON response with list of user scripts containing:
        - id: script ID
        - name: script name
        - active: whether script is active
        - created_at: creation date
        - balance: current balance
    """
    user_id = get_jwt_identity()
    if not isinstance(user_id, str):
        return jsonify({"error": "Invalid token format"}), 401

    with get_session() as session:
        scripts = session.query(UserScript).filter(UserScript.user_id == user_id).all()
        return jsonify({
            "scripts": [{
                "id": script.id,
                "name": script.name,
                "active": script.active,
                "created_at": script.created_at.isoformat(),
                "balance": script.balance
            } for script in scripts]
        }), 200

@scripts_bp.route('/<int:script_id>/activate', methods=['POST'])
@jwt_required()
def activate_script(script_id):
    """
    Activate or deactivate a user's script.
    
    Args:
        script_id: ID of the script to activate/deactivate
        
    Request Body:
        - active: boolean indicating whether to activate or deactivate
        
    Returns:
        JSON response with updated list of user scripts
    """
    user_id = get_jwt_identity()
    if not isinstance(user_id, str):
        return jsonify({"error": "Invalid token format"}), 401

    # Get the new active state from request
    data = request.get_json()
    if not data or 'active' not in data:
        return jsonify({"error": "Missing 'active' field in request"}), 400
    
    new_active_state = data['active']

    with get_session() as session:
        # Get the script and verify ownership
        script = session.query(UserScript).filter(
            UserScript.id == script_id,
            UserScript.user_id == user_id
        ).first()
        
        if not script:
            return jsonify({"error": "Script not found"}), 404

        # Update the active state
        script.active = new_active_state
        session.commit()

        # Return updated list of scripts
        scripts = session.query(UserScript).filter(UserScript.user_id == user_id).all()
        return jsonify({
            "scripts": [{
                "id": script.id,
                "name": script.name,
                "active": script.active,
                "created_at": script.created_at.isoformat(),
                "balance": script.balance
            } for script in scripts]
        }), 200 