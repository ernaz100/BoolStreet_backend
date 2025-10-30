from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from db.db_models import UserModel
from db.database import get_session
from typing import Tuple, Dict, Any, List
import json

# Create blueprint
models_bp = Blueprint('models', __name__)

@models_bp.route('/list', methods=['GET'])
@jwt_required()
def list_traders():
    """
    List all trading models for the current user.
    """
    user_id = get_jwt_identity()
    if not isinstance(user_id, str):
        return jsonify({"error": "Invalid token format"}), 401

    # Return a mock list of traders for now
    mock_traders = [
        {
            "id": 1,
            "name": "Alpha Bot",
            "active": True,
            "created_at": "2024-06-01T12:00:00Z",
            "balance": 10000.00,
            "tickers": "BTC,ETH"
        },
        {
            "id": 2,
            "name": "Beta Trader",
            "active": False,
            "created_at": "2024-06-03T09:30:00Z",
            "balance": 5200.75,
            "tickers": "DOGE,XRP,MATIC"
        },
        {
            "id": 3,
            "name": "Gamma Guru",
            "active": True,
            "created_at": "2024-06-05T16:44:00Z",
            "balance": 2448.11,
            "tickers": "SOL"
        }
    ]
    return jsonify({"models": mock_traders}), 200
    
@models_bp.route('/create', methods=['POST'])
@jwt_required()
def create_trader():
    """
    Create a new trading agent (LLM-based trader).
    
    Expects JSON with:
    - name: trader name
    - llm_model: LLM model to use (e.g., 'gpt-5-mini')
    - coins: list of coins to trade (e.g., ['DOGE'])
    - trading_frequency: frequency string (e.g., '1hour', '1day')
    - prompt: trading prompt for the LLM
    
    TODO: Implement full functionality:
    1. Validate all required fields
    2. Store trader configuration in database
    3. Create trading agent with specified configuration
    4. Return trader details
    """
    user_id = get_jwt_identity()
    if not isinstance(user_id, str):
        return jsonify({"error": "Invalid token format"}), 401
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    name = data.get('name')
    llm_model = data.get('llm_model')
    coins = data.get('coins')
    trading_frequency = data.get('trading_frequency')
    prompt = data.get('prompt')
    
    if not all([name, llm_model, coins, trading_frequency, prompt]):
        return jsonify({"error": "Missing required fields: name, llm_model, coins, trading_frequency, prompt"}), 400
    
    # TODO: Validate llm_model is supported
    # TODO: Validate coins are supported
    # TODO: Validate trading_frequency format
    
    # TODO: Store trader configuration in database
    # For now, we'll create a minimal model entry and store extra data in the code/weights field as JSON
    # In production, add new columns to UserModel table: llm_model, trading_frequency, prompt
    
    # Mock: Generate a simple code template that will be replaced with LLM execution logic
    mock_code = f"""# Trader: {name}
# LLM Model: {llm_model}
# Trading Frequency: {trading_frequency}
# Prompt: {prompt}
def run(data):
    # LLM-based trading agent
    return {{"action": "hold", "confidence": 0.5}}
"""
    
    # Store coins as JSON string in tickers field
    coins_json = json.dumps(coins) if isinstance(coins, list) else coins
    
    # Store LLM config in weights field as JSON (temporary solution)
    llm_config = json.dumps({
        "llm_model": llm_model,
        "trading_frequency": trading_frequency,
        "prompt": prompt
    })
    
    try:
        # Use existing save_model function
        model_id = save_model(name, mock_code, user_id, weights=llm_config, tickers=coins_json, balance=10000)
        
        return jsonify({
            "status": "success",
            "model_id": model_id,
            "name": name
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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

        # Return updated list of models with all fields
        models = session.query(UserModel).filter(UserModel.user_id == user_id).all()
        result_models = []
        for model in models:
            model_dict = {
                "id": model.id,
                "name": model.name,
                "active": model.active,
                "created_at": model.created_at.isoformat(),
                "balance": model.balance,
                "tickers": model.tickers
            }
            
            # Try to extract LLM config from weights field if present
            if model.weights:
                try:
                    llm_config = json.loads(model.weights)
                    if isinstance(llm_config, dict) and "llm_model" in llm_config:
                        model_dict["llm_model"] = llm_config.get("llm_model")
                        model_dict["trading_frequency"] = llm_config.get("trading_frequency")
                        model_dict["prompt"] = llm_config.get("prompt")
                except (json.JSONDecodeError, TypeError):
                    pass
            
            result_models.append(model_dict)
        
        return jsonify({
            "models": result_models
        }), 200 