from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from typing import Tuple, Optional
import logging
from db.database import get_session
from db.db_models import BrokerConnection
from layers.encryption import encrypt, decrypt, mask_secret

logger = logging.getLogger(__name__)

# Create blueprint
brokers_bp = Blueprint('brokers', __name__)

# Supported exchanges
SUPPORTED_EXCHANGES = ['hyperliquid']


def validate_exchange(exchange: str) -> bool:
    """
    Validate that an exchange is supported.
    
    Args:
        exchange: Exchange name (case-insensitive)
        
    Returns:
        True if supported, False otherwise
    """
    return exchange.lower() in SUPPORTED_EXCHANGES


def validate_api_key_format(exchange: str, api_key: str = None, api_secret: str = None, 
                            main_wallet_address: str = None, agent_wallet_private_key: str = None) -> Tuple[bool, Optional[str]]:
    """
    Validate API key format for a given exchange.
    
    Args:
        exchange: Exchange name
        api_key: API key to validate (unused, kept for compatibility)
        api_secret: API secret to validate (unused, kept for compatibility)
        main_wallet_address: Main wallet address (for Hyperliquid)
        agent_wallet_private_key: Agent wallet private key (for Hyperliquid)
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    exchange = exchange.lower()
    
    if exchange == 'hyperliquid':
        if not main_wallet_address or not agent_wallet_private_key:
            return False, "Hyperliquid requires main wallet address and agent wallet private key"
        # Validate wallet address format (should be a valid Ethereum address)
        if not main_wallet_address.startswith('0x') or len(main_wallet_address) != 42:
            return False, "Invalid main wallet address format (should be a valid Ethereum address)"
        # Validate private key format (should be 64 hex characters, optionally with 0x prefix)
        key = agent_wallet_private_key
        if key.startswith('0x'):
            key = key[2:]
        if len(key) != 64:
            return False, "Invalid agent wallet private key format (should be 64 hex characters)"
        try:
            int(key, 16)  # Validate it's hex
        except ValueError:
            return False, "Agent wallet private key must be hexadecimal"
        return True, None
    
    # Default validation for unknown exchanges
    if api_key and len(api_key) < 10:
        return False, "API key is too short"
    if api_secret and len(api_secret) < 10:
        return False, "API secret is too short"
    return True, None


def test_connection(exchange: str, api_key: str = None, api_secret: str = None,
                   main_wallet_address: str = None, agent_wallet_private_key: str = None,
                   is_testnet: bool = False) -> Tuple[bool, Optional[str]]:
    """
    Test connection to an exchange using API credentials.
    
    Args:
        exchange: Exchange name
        api_key: API key (unused, kept for compatibility)
        api_secret: API secret (unused, kept for compatibility)
        main_wallet_address: Main wallet address (for Hyperliquid)
        agent_wallet_private_key: Agent wallet private key (for Hyperliquid)
        is_testnet: Whether using testnet (for Hyperliquid)
        
    Returns:
        Tuple of (success, error_message)
    """
    exchange = exchange.lower()
    
    if exchange == 'hyperliquid':
        if not main_wallet_address or not agent_wallet_private_key:
            return False, "Hyperliquid requires main wallet address and agent wallet private key"
        return _test_hyperliquid_connection(main_wallet_address, agent_wallet_private_key, is_testnet)
    
    return False, f"Exchange '{exchange}' is not yet implemented for connection testing"


def _test_hyperliquid_connection(main_wallet_address: str, agent_wallet_private_key: str, is_testnet: bool) -> Tuple[bool, Optional[str]]:
    """
    Test Hyperliquid connection.
    
    Args:
        main_wallet_address: Main wallet address
        agent_wallet_private_key: Agent wallet private key
        is_testnet: Whether using testnet
        
    Returns:
        Tuple of (success, error_message)
    """
    try:
        from layers.brokers.hyperliquid_broker import HyperliquidBroker
        
        # Create broker instance
        broker = HyperliquidBroker(main_wallet_address, agent_wallet_private_key, testnet=is_testnet)
        
        # Test connection by getting balance
        balance = broker.get_balance()
        
        # If we got here without exception, connection is valid
        return True, None
        
    except ImportError:
        return False, "Required libraries for Hyperliquid are not installed"
        
    except Exception as e:
        error_msg = str(e)
        logger.error(f"Error testing Hyperliquid connection: {error_msg}")
        return False, f"Connection test failed: {error_msg}"


@brokers_bp.route('/brokers/connections', methods=['GET'])
@jwt_required()
def get_connections():
    """
    Get all broker connections for the current user.
    Returns a list of connections with masked API keys/secrets.
    """
    session = None
    try:
        user_id = get_jwt_identity()
        session = get_session()
        
        # Query BrokerConnection table filtered by user_id, ordered by created_at DESC
        connections = session.query(BrokerConnection).filter_by(
            user_id=user_id
        ).order_by(BrokerConnection.created_at.desc()).all()
        
        # Format response with masked secrets
        result = []
        for conn in connections:
                # Format connection data based on exchange type
            conn_data = {
                'id': conn.id,
                'exchange': conn.exchange,
                'is_connected': conn.is_connected,
                'connection_status': conn.connection_status,
                'created_at': conn.created_at.isoformat() if conn.created_at else None,
                'last_verified': conn.last_verified.isoformat() if conn.last_verified else None,
            }
            
            if conn.exchange == 'hyperliquid':
                if conn.main_wallet_address:
                    conn_data['main_wallet_address'] = conn.main_wallet_address[:10] + '...' + conn.main_wallet_address[-8:]
                conn_data['is_testnet'] = getattr(conn, 'is_testnet', False)
            
            result.append(conn_data)
        
        return jsonify({
            'connections': result
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if session:
            session.close()


@brokers_bp.route('/brokers/connections', methods=['POST'])
@jwt_required()
def create_connection():
    """
    Create a new broker connection.
    Validates API keys, encrypts and stores them.
    """
    session = None
    try:
        user_id = get_jwt_identity()
        data = request.json
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        exchange = data.get('exchange')
        exchange = exchange.lower().strip() if exchange else None
        
        if not exchange:
            return jsonify({'error': 'Missing required field: exchange'}), 400
        
        # Validate exchange is supported
        if not validate_exchange(exchange):
            return jsonify({
                'error': f'Unsupported exchange: {exchange}. Supported: {", ".join(SUPPORTED_EXCHANGES)}'
            }), 400
        
        # Get exchange-specific fields
        if exchange == 'hyperliquid':
            main_wallet_address = data.get('main_wallet_address')
            agent_wallet_private_key = data.get('agent_wallet_private_key')
            is_testnet = data.get('is_testnet', False)
            
            if not main_wallet_address or not agent_wallet_private_key:
                return jsonify({'error': 'Missing required fields: main_wallet_address, agent_wallet_private_key'}), 400
            
            # Validate format
            is_valid, error_msg = validate_api_key_format(
                exchange,
                main_wallet_address=main_wallet_address,
                agent_wallet_private_key=agent_wallet_private_key
            )
            if not is_valid:
                return jsonify({'error': error_msg}), 400
            
            # Test connection
            test_passed, test_error = test_connection(
                exchange,
                main_wallet_address=main_wallet_address,
                agent_wallet_private_key=agent_wallet_private_key,
                is_testnet=is_testnet
            )
            if not test_passed:
                return jsonify({
                    'error': f'Failed to verify credentials with exchange: {test_error}'
                }), 400
        
        session = get_session()
        
        # Check if user already has a connection for this exchange
        existing = session.query(BrokerConnection).filter_by(
            user_id=user_id,
            exchange=exchange
        ).first()
        
        if existing:
            # Update existing connection instead of creating a new one
            if exchange == 'hyperliquid':
                existing.main_wallet_address = main_wallet_address
                existing.encrypted_agent_wallet_private_key = encrypt(agent_wallet_private_key)
                existing.is_testnet = is_testnet
            
            existing.is_connected = True
            existing.connection_status = 'connected'
            existing.last_verified = datetime.now()
            session.commit()
            
            # Return updated connection details
            connection_data = {
                'id': existing.id,
                'exchange': existing.exchange,
                'is_connected': existing.is_connected,
                'connection_status': existing.connection_status,
                'created_at': existing.created_at.isoformat() if existing.created_at else None,
                'last_verified': existing.last_verified.isoformat() if existing.last_verified else None,
            }
            
            if exchange == 'hyperliquid':
                connection_data['main_wallet_address'] = main_wallet_address[:10] + '...' + main_wallet_address[-8:]  # Mask address
                connection_data['is_testnet'] = is_testnet
            
            return jsonify({'connection': connection_data}), 200
        
        # Create new connection record
        if exchange == 'hyperliquid':
            encrypted_agent_key = encrypt(agent_wallet_private_key)
            new_connection = BrokerConnection(
                user_id=user_id,
                exchange=exchange,
                main_wallet_address=main_wallet_address,
                encrypted_agent_wallet_private_key=encrypted_agent_key,
                is_testnet=is_testnet,
                is_connected=True,
                connection_status='connected',
                created_at=datetime.now(),
                last_verified=datetime.now()
            )
        
        session.add(new_connection)
        session.commit()
        session.refresh(new_connection)
        
        # Return connection details with masked secrets
        connection_data = {
            'id': new_connection.id,
            'exchange': new_connection.exchange,
            'is_connected': new_connection.is_connected,
            'connection_status': new_connection.connection_status,
            'created_at': new_connection.created_at.isoformat() if new_connection.created_at else None,
            'last_verified': new_connection.last_verified.isoformat() if new_connection.last_verified else None,
        }
        
        if exchange == 'hyperliquid':
            connection_data['main_wallet_address'] = main_wallet_address[:10] + '...' + main_wallet_address[-8:]
            connection_data['is_testnet'] = is_testnet
        
        return jsonify({'connection': connection_data}), 201
        
    except IntegrityError as e:
        if session:
            session.rollback()
        return jsonify({'error': 'Database error: Connection may already exist'}), 400
    except ValueError as e:
        # Encryption/decryption errors
        if session:
            session.rollback()
        return jsonify({'error': f'Encryption error: {str(e)}'}), 500
    except Exception as e:
        if session:
            session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if session:
            session.close()


@brokers_bp.route('/brokers/connections/<int:connection_id>/test', methods=['POST'])
@jwt_required()
def test_connection_endpoint(connection_id):
    """
    Test an existing broker connection by verifying API credentials.
    """
    session = None
    try:
        user_id = get_jwt_identity()
        session = get_session()
        
        # Query database for connection
        connection = session.query(BrokerConnection).filter_by(
            id=connection_id,
            user_id=user_id
        ).first()
        
        if not connection:
            return jsonify({'error': 'Connection not found'}), 404
        
        # Test connection with exchange API
        test_passed = False
        test_error = None
        
        if connection.exchange == 'hyperliquid':
            try:
                main_wallet = connection.main_wallet_address
                agent_key = decrypt(connection.encrypted_agent_wallet_private_key) if connection.encrypted_agent_wallet_private_key else None
                is_testnet = getattr(connection, 'is_testnet', False)
                if not main_wallet or not agent_key:
                    return jsonify({'error': 'Missing wallet credentials'}), 400
                test_passed, test_error = test_connection(
                    connection.exchange,
                    main_wallet_address=main_wallet,
                    agent_wallet_private_key=agent_key,
                    is_testnet=is_testnet
                )
            except Exception as e:
                return jsonify({
                    'error': f'Failed to decrypt credentials: {str(e)}'
                }), 500
        
        # Update connection status and last_verified timestamp
        connection.last_verified = datetime.now()
        
        if test_passed:
            connection.connection_status = 'connected'
            connection.is_connected = True
            session.commit()
            
            return jsonify({
                'valid': True,
                'exchange': connection.exchange,
                'message': 'Connection verified successfully',
                'last_verified': connection.last_verified.isoformat() if connection.last_verified else None,
            }), 200
        else:
            connection.connection_status = 'error'
            connection.is_connected = False
            session.commit()
            
            return jsonify({
                'valid': False,
                'exchange': connection.exchange,
                'message': f'Connection test failed: {test_error}',
            }), 200
            
    except Exception as e:
        if session:
            session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if session:
            session.close()


@brokers_bp.route('/brokers/connections/<int:connection_id>', methods=['DELETE'])
@jwt_required()
def delete_connection(connection_id):
    """
    Delete a broker connection.
    """
    session = None
    try:
        user_id = get_jwt_identity()
        session = get_session()
        
        # Query and delete from database
        connection = session.query(BrokerConnection).filter_by(
            id=connection_id,
            user_id=user_id
        ).first()
        
        if not connection:
            return jsonify({'error': 'Connection not found'}), 404
        
        deleted_exchange = connection.exchange
        session.delete(connection)
        session.commit()
        
        return jsonify({
            'message': 'Connection deleted successfully',
            'deleted_connection': {
                'id': connection_id,
                'exchange': deleted_exchange,
            }
        }), 200
        
    except Exception as e:
        if session:
            session.rollback()
        return jsonify({'error': str(e)}), 500
    finally:
        if session:
            session.close()


@brokers_bp.route('/brokers/exchanges', methods=['GET'])
@jwt_required()
def get_supported_exchanges():
    """
    Get list of supported exchanges.
    """
    try:
        exchanges = [
            {
                'name': 'hyperliquid',
                'display_name': 'Hyperliquid',
                'supported': True,
                'features': ['perpetuals_trading', 'testnet'],
            }
        ]
        
        return jsonify({
            'exchanges': exchanges
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@brokers_bp.route('/brokers/balances', methods=['GET'])
@jwt_required()
def get_broker_balances():
    """
    Get balances for all connected brokers.
    Returns detailed balance information including all coins for each connected broker.
    """
    session = None
    try:
        user_id = get_jwt_identity()
        session = get_session()
        
        # Get all connected broker connections for the user
        connections = session.query(BrokerConnection).filter_by(
            user_id=user_id,
            is_connected=True
        ).all()
        
        result = []
        for conn in connections:
            broker_data = {
                'id': conn.id,
                'exchange': conn.exchange,
                'is_testnet': getattr(conn, 'is_testnet', False),
                'total_value': None,
                'available_balance': None,
                'perps_margin': None,
                'spot_balances': [],
                'perp_positions': [],
                'error': None
            }
            
            if conn.exchange == 'hyperliquid':
                try:
                    from layers.brokers.hyperliquid_broker import HyperliquidBroker
                    
                    main_wallet = conn.main_wallet_address
                    agent_key = decrypt(conn.encrypted_agent_wallet_private_key) if conn.encrypted_agent_wallet_private_key else None
                    is_testnet = getattr(conn, 'is_testnet', False)
                    
                    if main_wallet and agent_key:
                        broker = HyperliquidBroker(main_wallet, agent_key, testnet=is_testnet)
                        balances = broker.get_all_balances()
                        broker_data['total_value'] = balances.get('total_value', 0)
                        broker_data['available_balance'] = balances.get('available_balance', 0)
                        broker_data['perps_margin'] = balances.get('perps_margin', 0)
                        broker_data['spot_balances'] = balances.get('spot_balances', [])
                        broker_data['perp_positions'] = balances.get('perp_positions', [])
                        broker_data['main_wallet_address'] = main_wallet[:10] + '...' + main_wallet[-8:]
                        if 'error' in balances:
                            broker_data['error'] = balances['error']
                except Exception as e:
                    broker_data['error'] = str(e)
                    logger.error(f"Error fetching balance for broker {conn.id}: {e}")
            
            result.append(broker_data)
        
        return jsonify({
            'brokers': result
        }), 200
        
    except Exception as e:
        logger.error(f"Error in get_broker_balances: {e}")
        return jsonify({'error': str(e)}), 500
    finally:
        if session:
            session.close()
