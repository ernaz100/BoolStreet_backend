from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import jwt_required, get_jwt_identity
from db.db_models import UserModel, BrokerConnection
from db.database import get_session
from layers.encryption import decrypt
from layers.execution import get_broker_connection
from layers.broker_factory import create_broker
from config.trading_config import (
    SUPPORTED_LLM_MODELS,
    SUPPORTED_COINS,
    SUPPORTED_FREQUENCIES,
    DEFAULT_LLM_MODEL,
    DEFAULT_FREQUENCY,
    DEFAULT_UNCERTAINTY_THRESHOLD,
    DEFAULT_MAX_POSITION_SIZE_PCT,
    DEFAULT_LEVERAGE,
    DEFAULT_STOP_LOSS_PCT,
    DEFAULT_TAKE_PROFIT_PCT,
    UNCERTAINTY_PRESETS,
    is_valid_model,
    is_valid_frequency,
    validate_coins,
    validate_uncertainty_threshold,
    validate_leverage,
    validate_position_size_pct,
)
from typing import Tuple, Dict, Any, List, Optional
import json

# Create blueprint
models_bp = Blueprint('models', __name__)


@models_bp.route('/config', methods=['GET'])
def get_trading_config():
    """
    Get available trading configuration options.
    Returns supported LLM models, coins, frequencies, and risk management options for the UI.
    """
    return jsonify({
        "models": [
            {
                "id": model_id,
                "name": config["display_name"],
                "provider": config["provider"],
                "description": config["description"],
                "cost_tier": config["cost_tier"],
            }
            for model_id, config in SUPPORTED_LLM_MODELS.items()
        ],
        "coins": [
            {
                "id": coin_id,
                "name": config["display_name"],
                "symbol": config["symbol"],
                "min_size": config["min_size"],
            }
            for coin_id, config in SUPPORTED_COINS.items()
        ],
        "frequencies": [
            {
                "id": freq_id,
                "name": config["display_name"],
                "description": config["description"],
                "interval_minutes": config["interval_minutes"],
            }
            for freq_id, config in SUPPORTED_FREQUENCIES.items()
        ],
        "uncertainty_presets": [
            {
                "id": preset_id,
                "value": config["value"],
                "name": config["display_name"],
                "description": config["description"],
            }
            for preset_id, config in UNCERTAINTY_PRESETS.items()
        ],
        "defaults": {
            "model": DEFAULT_LLM_MODEL,
            "frequency": DEFAULT_FREQUENCY,
            "uncertainty_threshold": DEFAULT_UNCERTAINTY_THRESHOLD,
            "max_position_size_pct": DEFAULT_MAX_POSITION_SIZE_PCT,
            "leverage": DEFAULT_LEVERAGE,
            "stop_loss_pct": DEFAULT_STOP_LOSS_PCT,
            "take_profit_pct": DEFAULT_TAKE_PROFIT_PCT,
        }
    }), 200

@models_bp.route('/list', methods=['GET'])
@jwt_required()
def list_traders():
    """
    List all trading models for the current user.
    """
    user_id = get_jwt_identity()
    if not isinstance(user_id, str):
        return jsonify({"error": "Invalid token format"}), 401

    with get_session() as session:
        # Query all models for the user
        models = session.query(UserModel).filter(UserModel.user_id == user_id).all()
        
        # Get broker connection for fetching real balances
        connection = get_broker_connection(user_id)
        real_balance = None
        
        if connection:
            try:
                # Create broker instance using factory
                broker = create_broker(connection)
                # Get balance from broker
                real_balance = broker.get_balance()
            except Exception as e:
                # If fetching balance fails, fall back to stored balance
                pass
        
        result_models = []
        for model in models:
            # Use real balance if available, otherwise use stored balance
            balance = real_balance if real_balance is not None else model.balance
            
            model_dict = {
                "id": model.id,
                "name": model.name,
                "active": model.active,
                "created_at": model.created_at.isoformat() if model.created_at else datetime.now().date().isoformat(),
                "balance": balance,
                "tickers": model.tickers,
                # Risk management settings
                "uncertainty_threshold": getattr(model, 'uncertainty_threshold', DEFAULT_UNCERTAINTY_THRESHOLD),
                "max_position_size_pct": getattr(model, 'max_position_size_pct', DEFAULT_MAX_POSITION_SIZE_PCT),
                "default_leverage": getattr(model, 'default_leverage', DEFAULT_LEVERAGE),
                "stop_loss_pct": getattr(model, 'stop_loss_pct', None),
                "take_profit_pct": getattr(model, 'take_profit_pct', None),
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
        
        return jsonify({"models": result_models}), 200
    
@models_bp.route('/create', methods=['POST'])
@jwt_required()
def create_trader():
    """
    Create a new trading agent (LLM-based trader).
    
    Expects JSON with:
    - name: trader name
    - llm_model: LLM model to use (e.g., 'gpt-4o-mini')
    - coins: list of coins to trade (e.g., ['BTC', 'ETH'])
    - trading_frequency: frequency string (e.g., '1hour', '1day')
    - prompt: trading prompt for the LLM
    
    Optional risk management fields:
    - uncertainty_threshold: float 0.0-1.0 (skip trades above this uncertainty)
    - max_position_size_pct: float 0.01-1.0 (max % of portfolio per trade)
    - default_leverage: float 1.0-50.0 (default leverage for trades)
    - stop_loss_pct: float (optional auto stop-loss %)
    - take_profit_pct: float (optional auto take-profit %)
    """
    user_id = get_jwt_identity()
    if not isinstance(user_id, str):
        return jsonify({"error": "Invalid token format"}), 401
    
    data = request.get_json()
    if not data:
        return jsonify({"error": "No data provided"}), 400
    
    name = data.get('name')
    llm_model = data.get('llm_model', DEFAULT_LLM_MODEL)
    coins = data.get('coins')
    trading_frequency = data.get('trading_frequency', DEFAULT_FREQUENCY)
    prompt = data.get('prompt')
    
    # Risk management settings with defaults
    uncertainty_threshold = data.get('uncertainty_threshold', DEFAULT_UNCERTAINTY_THRESHOLD)
    max_position_size_pct = DEFAULT_MAX_POSITION_SIZE_PCT  # Use default value, not from frontend
    default_leverage = data.get('default_leverage', DEFAULT_LEVERAGE)
    stop_loss_pct = data.get('stop_loss_pct', DEFAULT_STOP_LOSS_PCT)
    take_profit_pct = data.get('take_profit_pct', DEFAULT_TAKE_PROFIT_PCT)
    
    # Validate required fields
    if not name or not name.strip():
        return jsonify({"error": "Trader name is required"}), 400
    
    if not coins or not isinstance(coins, list) or len(coins) == 0:
        return jsonify({"error": "At least one coin must be selected"}), 400
    
    if not prompt or not prompt.strip():
        return jsonify({"error": "Trading prompt is required"}), 400
    
    # Validate LLM model
    if not is_valid_model(llm_model):
        supported = list(SUPPORTED_LLM_MODELS.keys())
        return jsonify({
            "error": f"Invalid LLM model '{llm_model}'. Supported models: {supported}"
        }), 400
    
    # Validate coins
    coins_valid, invalid_coins = validate_coins(coins)
    if not coins_valid:
        supported = list(SUPPORTED_COINS.keys())
        return jsonify({
            "error": f"Invalid coins: {invalid_coins}. Supported coins: {supported}"
        }), 400
    
    # Normalize coins to uppercase
    coins = [c.upper() for c in coins]
    
    # Validate trading frequency
    if not is_valid_frequency(trading_frequency):
        supported = list(SUPPORTED_FREQUENCIES.keys())
        return jsonify({
            "error": f"Invalid frequency '{trading_frequency}'. Supported: {supported}"
        }), 400
    
    # Validate risk management settings
    if not validate_uncertainty_threshold(uncertainty_threshold):
        return jsonify({
            "error": f"Invalid uncertainty_threshold '{uncertainty_threshold}'. Must be between 0.0 and 1.0"
        }), 400
    
    if not validate_position_size_pct(max_position_size_pct):
        return jsonify({
            "error": f"Invalid max_position_size_pct '{max_position_size_pct}'. Must be between 0.01 and 1.0"
        }), 400
    
    if not validate_leverage(default_leverage):
        return jsonify({
            "error": f"Invalid default_leverage '{default_leverage}'. Must be between 1.0 and 50.0"
        }), 400
    
    if stop_loss_pct is not None and (stop_loss_pct <= 0 or stop_loss_pct > 0.5):
        return jsonify({
            "error": f"Invalid stop_loss_pct '{stop_loss_pct}'. Must be between 0.001 and 0.5 (0.1% to 50%)"
        }), 400
    
    if take_profit_pct is not None and (take_profit_pct <= 0 or take_profit_pct > 2.0):
        return jsonify({
            "error": f"Invalid take_profit_pct '{take_profit_pct}'. Must be between 0.001 and 2.0 (0.1% to 200%)"
        }), 400
    
    # Store coins as JSON string in tickers field
    coins_json = json.dumps(coins)
    
    # Store LLM config in weights field as JSON (temporary solution)
    llm_config = json.dumps({
        "llm_model": llm_model,
        "trading_frequency": trading_frequency,
        "prompt": prompt
    })
    
    try:
        # Get current broker balance to set as start_balance
        current_balance = 0.0  # Default fallback
        try:
            with get_session() as session:
                broker_conn = get_broker_connection(user_id)
                if broker_conn:
                    broker = create_broker(broker_conn)
                    current_balance = broker.get_balance()
        except Exception as e:
            # Log the error but continue with default balance
            print(f"Could not fetch broker balance for start_balance: {e}")

        # Save model directly to database with risk management settings
        with get_session() as session:
            new_model = UserModel(
                user_id=user_id,
                name=name,
                code="",  # Code field not used for LLM traders
                weights=llm_config,
                tickers=coins_json,
                balance=current_balance,
                start_balance=current_balance,
                active=False,
                created_at=datetime.now(),
                # Risk management settings
                uncertainty_threshold=uncertainty_threshold,
                max_position_size_pct=max_position_size_pct,
                default_leverage=default_leverage,
                stop_loss_pct=stop_loss_pct,
                take_profit_pct=take_profit_pct,
            )
            session.add(new_model)
            session.commit()
            session.refresh(new_model)
            model_id = new_model.id
        
        return jsonify({
            "status": "success",
            "model_id": model_id,
            "name": name,
            "risk_settings": {
                "uncertainty_threshold": uncertainty_threshold,
                "default_leverage": default_leverage,
                "stop_loss_pct": stop_loss_pct,
                "take_profit_pct": take_profit_pct,
            }
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@models_bp.route('/<int:model_id>/activate', methods=['POST'])
@jwt_required()
def activate_trader(model_id):
    """
    Activate or deactivate a user's trading model.
    
    When activated, the trader is added to the scheduler.
    When deactivated, the trader is removed from the scheduler.
    
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

        # Check for broker connection if activating
        if new_active_state:
            connection = get_broker_connection(user_id)
            if not connection:
                return jsonify({"error": "No broker connection. Please connect a broker before activating a trader."}), 400

        # Update the active state
        model.active = new_active_state
        
        # Get trading frequency for scheduler
        trading_frequency = "1hour"  # Default
        if model.weights:
            try:
                llm_config = json.loads(model.weights)
                trading_frequency = llm_config.get("trading_frequency", "1hour")
            except (json.JSONDecodeError, TypeError):
                pass
        
        session.commit()

        # Sync with scheduler
        try:
            from layers.scheduler import trading_scheduler
            if new_active_state:
                # Add to scheduler when activated
                trading_scheduler.add_trader(model_id, trading_frequency)
            else:
                # Remove from scheduler when deactivated
                trading_scheduler.remove_trader(model_id)
        except Exception as e:
            # Log but don't fail - scheduler might not be running
            import logging
            logging.warning(f"Failed to sync trader {model_id} with scheduler: {e}")

        # Return updated list of models with all fields
        models = session.query(UserModel).filter(UserModel.user_id == user_id).all()
        result_models = []
        for m in models:
            model_dict = {
                "id": m.id,
                "name": m.name,
                "active": m.active,
                "created_at": m.created_at.isoformat() if m.created_at else datetime.now().date().isoformat(),
                "balance": m.balance,
                "tickers": m.tickers
            }
            
            # Try to extract LLM config from weights field if present
            if m.weights:
                try:
                    llm_config = json.loads(m.weights)
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


@models_bp.route('/<int:model_id>', methods=['DELETE'])
@jwt_required()
def delete_trader(model_id):
    """
    Delete a trading model.
    
    Args:
        model_id: ID of the model to delete
        
    Returns:
        JSON response confirming deletion
    """
    user_id = get_jwt_identity()
    if not isinstance(user_id, str):
        return jsonify({"error": "Invalid token format"}), 401

    with get_session() as session:
        # Get the model and verify ownership
        model = session.query(UserModel).filter(
            UserModel.id == model_id,
            UserModel.user_id == user_id
        ).first()
        
        if not model:
            return jsonify({"error": "Model not found"}), 404

        # Remove from scheduler if active
        try:
            from layers.scheduler import trading_scheduler
            trading_scheduler.remove_trader(model_id)
        except Exception:
            pass  # Scheduler might not be initialized

        # Delete the model
        model_name = model.name
        session.delete(model)
        session.commit()
        
        return jsonify({
            "message": "Model deleted successfully",
            "deleted_model": {
                "id": model_id,
                "name": model_name
            }
        }), 200


@models_bp.route('/<int:model_id>/run', methods=['POST'])
@jwt_required()
def run_trader_now(model_id):
    """
    Manually trigger a trader execution immediately.
    
    This endpoint allows users to test their trading agent
    without waiting for the scheduled execution.
    
    Args:
        model_id: ID of the model to execute
        
    Returns:
        JSON response with execution result including:
        - LLM decision (coin, action, quantity, uncertainty)
        - Trade execution result
    """
    user_id = get_jwt_identity()
    if not isinstance(user_id, str):
        return jsonify({"error": "Invalid token format"}), 401

    with get_session() as session:
        # Get the model and verify ownership
        model = session.query(UserModel).filter(
            UserModel.id == model_id,
            UserModel.user_id == user_id
        ).first()
        
        if not model:
            return jsonify({"error": "Model not found"}), 404
        
        # Check if user has a broker connection
        connection = get_broker_connection(user_id)
        if not connection:
            return jsonify({"error": "No broker connection. Please connect a broker first."}), 400

    # Execute the trader
    try:
        from layers.scheduler import trading_scheduler
        result = trading_scheduler.trigger_trader_now(model_id)
        
        if result.get("success"):
            decision = result.get("decision")
            trade_result = result.get("trade_result", {})
            
            return jsonify({
                "success": True,
                "trader_id": model_id,
                "trader_name": result.get("trader_name"),
                "decision": {
                    "coin": decision.coin if decision else None,
                    "action": decision.decision if decision else None,
                    "quantity": decision.quantity if decision else 0,
                    "uncertainty": decision.uncertainty if decision else 0,
                },
                "trade_result": {
                    "success": trade_result.get("success", False),
                    "action": trade_result.get("action"),
                    "symbol": trade_result.get("symbol"),
                    "quantity": trade_result.get("quantity"),
                    "price": trade_result.get("price"),
                    "order_id": trade_result.get("order_id"),
                    "error": trade_result.get("error"),
                }
            }), 200
        else:
            return jsonify({
                "success": False,
                "trader_id": model_id,
                "error": result.get("error", "Unknown error")
            }), 400
            
    except Exception as e:
        return jsonify({
            "success": False,
            "trader_id": model_id,
            "error": str(e)
        }), 500