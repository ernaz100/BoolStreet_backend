"""Broker abstraction layer for trading operations.

This module defines the BrokerInterface abstract base class that all broker
implementations must follow, ensuring a consistent API across different exchanges.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Any, Optional


class BrokerInterface(ABC):
    """Abstract base class for broker implementations."""
    
    @abstractmethod
    def get_balance(self) -> float:
        """Get account balance in USDT.
        
        Returns:
            Account balance as a float in USDT
        """
        pass
    
    @abstractmethod
    def execute_trade(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: Optional[float] = None
    ) -> Dict[str, Any]:
        """Execute a trade.
        
        Args:
            symbol: Trading symbol (e.g., "BTC", "ETH")
            side: Trade direction - "long" or "short"
            quantity: Quantity to trade
            price: Optional price for limit orders (None for market orders)
            
        Returns:
            Dictionary with trade execution result containing:
            - success: bool
            - order_id: Optional[str]
            - price: float
            - quantity: float
            - error: Optional[str]
        """
        pass
    
    @abstractmethod
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get current positions.
        
        Returns:
            List of position dictionaries, each containing:
            - symbol: str
            - quantity: float
            - entry_price: float
            - current_price: float
            - unrealized_pnl: float
        """
        pass
    
    @abstractmethod
    def get_account_info(self) -> Dict[str, Any]:
        """Get account information.
        
        Returns:
            Dictionary with account information including balance, positions, etc.
        """
        pass
    
    @abstractmethod
    def is_paper_trading(self) -> bool:
        """Check if this is a paper trading account.
        
        Returns:
            True if paper trading, False otherwise
        """
        pass
    
    def place_stop_loss(
        self,
        symbol: str,
        quantity: float,
        trigger_price: float,
        is_long: bool = True
    ) -> Dict[str, Any]:
        """Place a stop loss order.
        
        Args:
            symbol: Trading symbol (e.g., "BTC", "ETH")
            quantity: Quantity to close when triggered
            trigger_price: Price at which to trigger the stop loss
            is_long: True if closing a long position, False for short
            
        Returns:
            Dictionary with order result containing:
            - success: bool
            - order_id: Optional[str]
            - trigger_price: float
            - error: Optional[str]
        """
        # Default implementation - override in subclasses that support it
        return {
            "success": False,
            "error": "Stop loss orders not supported by this broker"
        }
    
    def place_take_profit(
        self,
        symbol: str,
        quantity: float,
        trigger_price: float,
        is_long: bool = True
    ) -> Dict[str, Any]:
        """Place a take profit order.
        
        Args:
            symbol: Trading symbol (e.g., "BTC", "ETH")
            quantity: Quantity to close when triggered
            trigger_price: Price at which to trigger the take profit
            is_long: True if closing a long position, False for short
            
        Returns:
            Dictionary with order result containing:
            - success: bool
            - order_id: Optional[str]
            - trigger_price: float
            - error: Optional[str]
        """
        # Default implementation - override in subclasses that support it
        return {
            "success": False,
            "error": "Take profit orders not supported by this broker"
        }
    
    def cancel_trigger_orders(
        self,
        symbol: str
    ) -> Dict[str, Any]:
        """Cancel all trigger orders (stop loss and take profit) for a symbol.
        
        Args:
            symbol: Trading symbol (e.g., "BTC", "ETH")
            
        Returns:
            Dictionary with cancellation result containing:
            - success: bool
            - cancelled_count: int
            - error: Optional[str]
        """
        # Default implementation - override in subclasses that support it
        return {
            "success": False,
            "cancelled_count": 0,
            "error": "Trigger order cancellation not supported by this broker"
        }
    
    def get_open_trigger_orders(
        self,
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get open trigger orders (stop loss and take profit).
        
        Args:
            symbol: Optional symbol to filter by (None for all symbols)
            
        Returns:
            List of trigger order dictionaries, each containing:
            - order_id: str
            - symbol: str
            - trigger_price: float
            - quantity: float
            - side: str
            - order_type: str ("stop_loss" or "take_profit")
        """
        # Default implementation - override in subclasses that support it
        return []

