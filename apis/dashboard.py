from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from db.storage import _Session, UserScript, ScriptPrediction

# Create blueprint
dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/stats', methods=['GET'])
@jwt_required()
def get_dashboard_stats():
    """
    Get dashboard statistics for the current user.
    
    Returns:
        JSON response containing:
        - total_scripts: Total number of scripts
        - active_scripts: Number of active scripts
        - total_balance: Sum of all script balances
        - net_profit: Total profit/loss across all scripts
    """
    user_id = get_jwt_identity()
    if not isinstance(user_id, str):
        return jsonify({"error": "Invalid token format"}), 401

    with _Session() as session:
        # Get all scripts for the user
        scripts = session.query(UserScript).filter(UserScript.user_id == user_id).all()
        
        # If no scripts found, return default values
        if not scripts:
            return jsonify({
                "total_scripts": 0,
                "active_scripts": 0,
                "total_balance": 0.0,
                "net_profit": 0.0
            }), 200

        total_scripts = len(scripts)
        active_scripts = sum(1 for script in scripts if script.active)
        total_balance = sum(script.balance for script in scripts)
        net_profit = sum(script.balance - script.start_balance for script in scripts)

        return jsonify({
            "total_scripts": total_scripts,
            "active_scripts": active_scripts,
            "total_balance": total_balance,
            "net_profit": net_profit
        }), 200

@dashboard_bp.route('/predictions', methods=['GET'])
@jwt_required()
def get_recent_predictions():
    """
    Get recent predictions for all user scripts.
    
    Returns:
        JSON response containing a list of recent predictions with:
        - script_name: Name of the script
        - prediction: The prediction made
        - confidence: Confidence score
        - timestamp: When the prediction was made
        - profit_loss: Profit/loss from this prediction
    """
    user_id = get_jwt_identity()
    if not isinstance(user_id, str):
        return jsonify({"error": "Invalid token format"}), 401

    with _Session() as session:
        # Get predictions for all user's scripts, ordered by most recent
        predictions = (
            session.query(
                ScriptPrediction,
                UserScript.name.label('script_name')
            )
            .join(UserScript, ScriptPrediction.script_id == UserScript.id)
            .filter(UserScript.user_id == user_id)
            .order_by(ScriptPrediction.timestamp.desc())
            .limit(10)  # Get last 10 predictions
            .all()
        )

        # If no predictions found, return empty list
        if not predictions:
            return jsonify({
                "predictions": []
            }), 200

        return jsonify({
            "predictions": [{
                "script_name": pred.script_name,
                "prediction": pred.prediction,
                "confidence": pred.confidence,
                "timestamp": pred.timestamp.isoformat(),
                "profit_loss": pred.profit_loss
            } for pred in predictions]
        }), 200 