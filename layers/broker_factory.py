"""Factory for creating broker instances from database connections."""

import logging
from typing import Optional
from db.db_models import BrokerConnection
from layers.encryption import decrypt
from layers.brokers.hyperliquid_broker import HyperliquidBroker

logger = logging.getLogger(__name__)


def create_broker(connection: BrokerConnection):
    """Create a broker instance from a database connection.
    
    Args:
        connection: BrokerConnection database model
        
    Returns:
        BrokerInterface instance
        
    Raises:
        ValueError: If exchange is not supported or connection is invalid
    """
    exchange = connection.exchange.lower()
    
    if exchange == "hyperliquid":
        if not connection.main_wallet_address or not connection.encrypted_agent_wallet_private_key:
            raise ValueError("Hyperliquid connection missing wallet address or agent private key")
        
        main_wallet = connection.main_wallet_address
        agent_key = decrypt(connection.encrypted_agent_wallet_private_key)
        is_testnet = connection.is_testnet if hasattr(connection, 'is_testnet') else False
        
        return HyperliquidBroker(main_wallet, agent_key, testnet=is_testnet)
    
    else:
        raise ValueError(f"Unsupported exchange: {exchange}")

