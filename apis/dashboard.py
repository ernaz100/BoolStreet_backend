from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func
from db.db_models import UserModel, ModelPrediction
from db.database import get_session

# Create blueprint
dashboard_bp = Blueprint('dashboard', __name__)

@dashboard_bp.route('/stats', methods=['GET'])
@jwt_required()
def get_dashboard_stats():
    """
    Get dashboard statistics for the current user.
    
    Returns:
        JSON response containing:
        - total_models: Total number of trading models
        - active_models: Number of active trading models
        - total_balance: Sum of all model balances
        - net_profit: Total profit/loss across all models
    """
    user_id = get_jwt_identity()
    if not isinstance(user_id, str):
        return jsonify({"error": "Invalid token format"}), 401

    with get_session() as session:
        # Get all trading models for the user
        models = session.query(UserModel).filter(UserModel.user_id == user_id).all()
        
        # If no models found, return default values
        if not models:
            return jsonify({
                "total_models": 0,
                "active_models": 0,
                "total_balance": 0.0,
                "net_profit": 0.0
            }), 200

        total_models = len(models)
        active_models = sum(1 for model in models if model.active)
        total_balance = sum(model.balance for model in models)
        net_profit = sum(model.balance - model.start_balance for model in models)

        return jsonify({
            "total_models": total_models,
            "active_models": active_models,
            "total_balance": total_balance,
            "net_profit": net_profit
        }), 200

@dashboard_bp.route('/predictions', methods=['GET'])
@jwt_required()
def get_recent_predictions():
    """
    Get recent predictions for all user trading models.
    
    Returns:
        JSON response containing a list of recent predictions with:
        - model_name: Name of the trading model
        - prediction: The prediction made
        - confidence: Confidence score
        - timestamp: When the prediction was made
        - profit_loss: Profit/loss from this prediction
    """
    user_id = get_jwt_identity()
    if not isinstance(user_id, str):
        return jsonify({"error": "Invalid token format"}), 401

    with get_session() as session:
        # Get predictions for all user's trading models, ordered by most recent
        predictions = (
            session.query(
                ModelPrediction,
                UserModel.name.label('model_name')
            )
            .join(UserModel, ModelPrediction.model_id == UserModel.id)
            .filter(UserModel.user_id == user_id)
            .order_by(ModelPrediction.timestamp.desc())
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
                "model_name": pred.model_name,
                "prediction": pred.prediction,
                "confidence": pred.confidence,
                "timestamp": pred.timestamp.isoformat(),
                "profit_loss": pred.profit_loss
            } for pred in predictions]
        }), 200 