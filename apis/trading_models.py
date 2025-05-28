from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from db.storage import save_model
from db.db_models import UserModel
from db.database import get_session
from typing import Tuple, Dict, Any, List

# Create blueprint
models_bp = Blueprint('models', __name__)
def run_user_script(model_id: int) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Execute the given user script and return its JSON output."""
    return {
        "started_at": datetime.now().isoformat(),
        "ended_at": datetime.now().isoformat(),
        "duration_secs": 0.0,
        "output": "Dummy execution completed"
    }, []

@models_bp.route('/upload', methods=['POST'])
@jwt_required()
def upload_model():
    """
    Upload a user trading model.

    Expects multipart/form-data with:
    - 'file': the .py source file
    - 'name': user-friendly name (optional, defaults to filename)
    - 'model_type': type of model (optional)
    - 'weights': weights file (optional)
    - 'tickers': tickers as JSON string

    Returns:
        JSON response with model id and status
    """
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    f = request.files['file']
    if f.filename == '':
        return jsonify({"error": "No file selected"}), 400

    name = request.form.get('name', f.filename)
    balance = request.form.get('balance', 10000)
    code = f.read().decode('utf-8')

    # Handle optional weights file
    weights = None
    if 'weights' in request.files:
        weights_file = request.files['weights']
        if weights_file and weights_file.filename:
            weights = weights_file.read().decode('utf-8')  # Store as string

    # Handle optional tickers (JSON string)
    tickers = request.form.get('tickers')

    # quick validation – require a `def run(data):` entry point
    if "def run(" not in code:
        return jsonify({"error": "Model must expose a `run(data)` function"}), 400

    # Get user ID from JWT token
    user_id = get_jwt_identity()
    if not isinstance(user_id, str):
        return jsonify({"error": "Invalid token format"}), 401

    # Save model with new fields
    model_id = save_model(name, code, user_id, weights=weights, tickers=tickers, balance=balance)
    try:
        result, receipts = run_user_script(model_id)
        final = {
            "model_id": model_id,
            "model_name": name,
            "started_at": result["started_at"],
            "ended_at": result["ended_at"],
            "duration_secs": result["duration_secs"],
            "output": result["output"],
            "orders": receipts,
            "success": True
        }
    except Exception as exc:
        final = {
            "model_id": model_id,
            "model_name": name,
            "started_at": datetime.now().isoformat(),
            "ended_at": datetime.now().isoformat(),
            "duration_secs": 0,
            "output": str(exc),
            "success": False
        }
    status = "✅" if final["success"] else "❌"
    print(f"  • Model {final['model_id']} ({final['model_name']}) {status}: {final['output']}")

    return jsonify({
        "status": "success",
        "model_id": model_id
    }), 200

@models_bp.route('/list', methods=['GET'])
@jwt_required()
def get_user_models():
    """
    Fetch all trading models for the currently logged in user.
    
    Returns:
        JSON response with list of user models containing:
        - id: model ID
        - name: model name
        - active: whether model is active
        - created_at: creation date
        - balance: current balance
    """
    user_id = get_jwt_identity()
    if not isinstance(user_id, str):
        return jsonify({"error": "Invalid token format"}), 401

    with get_session() as session:
        models = session.query(UserModel).filter(UserModel.user_id == user_id).all()
        return jsonify({
            "models": [{
                "id": model.id,
                "name": model.name,
                "active": model.active,
                "created_at": model.created_at.isoformat(),
                "balance": model.balance,
                "tickers": model.tickers
            } for model in models]
        }), 200

@models_bp.route('/<int:model_id>/activate', methods=['POST'])
@jwt_required()
def activate_model(model_id):
    """
    Activate or deactivate a user's trading model.
    
    Args:
        model_id: ID of the model to activate/deactivate
        
    Request Body:
        - active: boolean indicating whether to activate or deactivate
        
    Returns:
        JSON response with updated list of user models
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
        # Get the model and verify ownership
        model = session.query(UserModel).filter(
            UserModel.id == model_id,
            UserModel.user_id == user_id
        ).first()
        
        if not model:
            return jsonify({"error": "Model not found"}), 404

        # Update the active state
        model.active = new_active_state
        session.commit()

        # Return updated list of models
        models = session.query(UserModel).filter(UserModel.user_id == user_id).all()
        return jsonify({
            "models": [{
                "id": model.id,
                "name": model.name,
                "active": model.active,
                "created_at": model.created_at.isoformat(),
                "balance": model.balance
            } for model in models]
        }), 200 