"""Hyperliquid broker implementation using official SDK."""

import logging
import json
import requests
from typing import Dict, List, Any, Optional
from eth_account import Account

# Import Hyperliquid SDK
from hyperliquid.info import Info
from hyperliquid.exchange import Exchange
from hyperliquid.utils import constants

from layers.broker_interface import BrokerInterface

logger = logging.getLogger(__name__)


class HyperliquidBroker(BrokerInterface):
    """Hyperliquid broker implementation using official SDK."""
    
    BASE_URL_MAINNET = "https://api.hyperliquid.xyz"
    BASE_URL_TESTNET = "https://api.hyperliquid-testnet.xyz"
    
    def __init__(
        self,
        main_wallet_address: str,
        agent_wallet_private_key: str,
        testnet: bool = False
    ):
        """Initialize Hyperliquid broker.
        
        Args:
            main_wallet_address: Main wallet address for balance queries
            agent_wallet_private_key: Agent wallet private key for trade execution
            testnet: Whether to use testnet (default: False)
        """
        self.main_wallet_address = main_wallet_address
        self.agent_wallet_private_key = agent_wallet_private_key
        self.testnet = testnet
        self.base_url = self.BASE_URL_TESTNET if testnet else self.BASE_URL_MAINNET
        
        # Initialize agent account from private key
        try:
            self.agent_account = Account.from_key(agent_wallet_private_key)
            self.agent_address = self.agent_account.address
        except Exception as e:
            logger.error(f"Error initializing agent account: {e}")
            raise
        
        # Lazy initialization - SDK components created on first use
        self._info = None
        self._exchange = None
    
    @property
    def info(self) -> Info:
        """Lazily initialize Info SDK (avoids API calls during __init__)."""
        if self._info is None:
            self._info = Info(self.base_url, skip_ws=True)
        return self._info
    
    @property
    def exchange(self) -> Exchange:
        """Lazily initialize Exchange SDK (avoids API calls during __init__)."""
        if self._exchange is None:
            self._exchange = Exchange(
                self.agent_account,
                self.base_url,
                vault_address=None,
                account_address=self.main_wallet_address  # Trade on behalf of main wallet
            )
        return self._exchange
    
    def _make_request(self, endpoint: str, method: str = "GET", data: Optional[dict] = None) -> dict:
        """Make a request to Hyperliquid API.
        
        Args:
            endpoint: API endpoint path
            method: HTTP method (GET, POST)
            data: Optional request data
            
        Returns:
            Response dictionary
        """
        url = f"{self.base_url}{endpoint}"
        
        try:
            if method == "GET":
                response = requests.get(url, params=data)
            elif method == "POST":
                response = requests.post(url, json=data)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Hyperliquid API request error: {e}")
            raise
    
    def get_balance(self) -> float:
        """Get account balance in USDC."""
        try:
            # Get user state which includes balance
            endpoint = "/info"
            data = {"type": "clearinghouseState", "user": self.main_wallet_address}
            response = self._make_request(endpoint, method="POST", data=data)
            
            # Parse balance from response
            # Hyperliquid returns marginSummary at the top level (not nested under "data")
            if "marginSummary" in response:
                margin_summary = response["marginSummary"]
                # Account value in USDC
                account_value = float(margin_summary.get("accountValue", 0))
                return account_value
            
            # If no marginSummary, this might be a new/empty account
            return 0.0
        except Exception as e:
            logger.error(f"Error fetching Hyperliquid balance: {e}")
            # Return 0.0 on error to prevent crashes
            return 0.0
    
    def get_all_balances(self) -> Dict[str, Any]:
        """Get all coin balances including spot and perp positions.
        
        Returns:
            Dictionary containing:
            - total_value: Total account value in USDC
            - available_balance: Available USDC balance
            - perps_margin: USDC balance in perps account (collateral)
            - spot_balances: List of spot token balances
            - perp_positions: List of perpetual positions
        """
        try:
            result = {
                "total_value": 0.0,
                "available_balance": 0.0,
                "perps_margin": 0.0,
                "spot_balances": [],
                "perp_positions": []
            }
            
            # Get perp clearinghouse state (includes margin summary)
            endpoint = "/info"
            perp_data = {"type": "clearinghouseState", "user": self.main_wallet_address}
            perp_response = self._make_request(endpoint, method="POST", data=perp_data)
            
            if "marginSummary" in perp_response:
                margin = perp_response["marginSummary"]
                result["total_value"] = float(margin.get("accountValue", 0))
                # This is the USDC collateral in the perps account
                result["perps_margin"] = float(margin.get("accountValue", 0))
            
            # withdrawable is at the root level, not inside marginSummary
            if "withdrawable" in perp_response:
                result["available_balance"] = float(perp_response.get("withdrawable", 0))
            
            # Get perp positions
            if "assetPositions" in perp_response:
                for pos in perp_response["assetPositions"]:
                    position = pos.get("position", {})
                    coin = position.get("coin", "")
                    size = float(position.get("szi", 0))
                    entry_price = float(position.get("entryPx", 0))
                    unrealized_pnl = float(position.get("unrealizedPnl", 0))
                    
                    if size != 0:
                        current_price = self._get_current_price(coin)
                        result["perp_positions"].append({
                            "coin": coin,
                            "size": size,
                            "side": "long" if size > 0 else "short",
                            "entry_price": entry_price,
                            "current_price": current_price,
                            "unrealized_pnl": unrealized_pnl,
                            "value": abs(size) * current_price
                        })
            
            # Get spot balances
            try:
                spot_data = {"type": "spotClearinghouseState", "user": self.main_wallet_address}
                spot_response = self._make_request(endpoint, method="POST", data=spot_data)
                
                if "balances" in spot_response:
                    for balance in spot_response["balances"]:
                        coin = balance.get("coin", "")
                        hold = float(balance.get("hold", 0))
                        total = float(balance.get("total", 0))
                        
                        if total > 0:
                            # Get current price for non-USDC coins
                            if coin == "USDC":
                                price = 1.0
                                value = total
                            else:
                                price = self._get_current_price(coin)
                                value = total * price if price > 0 else 0
                            
                            result["spot_balances"].append({
                                "coin": coin,
                                "total": total,
                                "available": total - hold,
                                "hold": hold,
                                "price": price,
                                "value": value
                            })
            except Exception as e:
                logger.warning(f"Could not fetch spot balances: {e}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error fetching all Hyperliquid balances: {e}")
            return {
                "total_value": 0.0,
                "available_balance": 0.0,
                "perps_margin": 0.0,
                "spot_balances": [],
                "perp_positions": [],
                "error": str(e)
            }
    
    def execute_trade(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: Optional[float] = None
    ) -> Dict[str, Any]:
        """Execute a trade on Hyperliquid using the official SDK.
        
        Args:
            symbol: Coin symbol (e.g., "BTC", "ETH")
            side: Trade direction - "long" or "short"
            quantity: Amount to trade
            price: Optional limit price (None for market order)
        """
        try:
            if side == "hold":
                return {
                    "success": True,
                    "action": "hold",
                    "order_id": None,
                    "price": 0.0,
                    "quantity": 0.0
                }
            
            # Map symbol to Hyperliquid format (e.g., "BTC" -> "BTC")
            coin = symbol.upper()
            
            # Determine if this is a long (buy) or short (sell) position
            is_long = side.lower() == "long"
            
            # Get asset metadata for size validation
            sz_decimals = self._get_size_decimals(coin)
            min_size = self._get_min_size(coin)
            
            # Round quantity to valid decimals
            quantity = round(quantity, sz_decimals)
            
            # Enforce minimum size
            if quantity < min_size:
                logger.warning(f"Quantity {quantity} below minimum {min_size} for {coin}, using minimum")
                quantity = min_size
            
            # Get current market price if not provided
            if price is None:
                current_price = self._get_current_price(coin)
                if current_price <= 0:
                    return {
                        "success": False,
                        "action": side,
                        "order_id": None,
                        "price": 0.0,
                        "quantity": quantity,
                        "error": f"Could not get current price for {coin}"
                    }
                # Use a slight slippage for market-like orders
                # Long: buy slightly higher, Short: sell slightly lower
                slippage = 0.002  # 0.2% slippage for market orders
                price = current_price * (1 + slippage) if is_long else current_price * (1 - slippage)
            
            # Round price appropriately (depends on coin)
            price = self._round_price(coin, price)
            
            logger.info(f"Executing {side} order: {quantity} {coin} @ ${price} (min_size={min_size}, decimals={sz_decimals})")
            
            # Use SDK to place market order (IOC = Immediate or Cancel)
            # The SDK handles all the EIP-712 signing properly
            # SDK uses is_buy: True for long, False for short
            order_result = self.exchange.market_open(
                name=coin,  # SDK uses 'name' for the coin symbol
                is_buy=is_long,
                sz=quantity,
                px=price,
                slippage=0.01  # 1% max slippage
            )
            
            logger.info(f"Order result: {order_result}")
            
            # Parse SDK response
            if order_result.get("status") == "ok":
                response_data = order_result.get("response", {}).get("data", {})
                statuses = response_data.get("statuses", [{}])
                
                if statuses and len(statuses) > 0:
                    status = statuses[0]
                    
                    # Check for errors in the status
                    if "error" in status:
                        return {
                            "success": False,
                            "action": side,
                            "order_id": None,
                            "price": price,
                            "quantity": quantity,
                            "error": status["error"]
                        }
                    
                    # Get order ID from filled or resting
                    order_id = None
                    if "filled" in status:
                        order_id = status["filled"].get("oid")
                    elif "resting" in status:
                        order_id = status["resting"].get("oid")
                    
                    return {
                        "success": True,
                        "action": side,
                        "order_id": order_id,
                        "price": price,
                        "quantity": quantity,
                        "response": order_result
                    }
            
            # Handle error response
            error_msg = "Unknown error"
            if "response" in order_result:
                resp = order_result["response"]
                if isinstance(resp, str):
                    error_msg = resp
                elif isinstance(resp, dict):
                    statuses = resp.get("data", {}).get("statuses", [])
                    if statuses and "error" in statuses[0]:
                        error_msg = statuses[0]["error"]
            
            return {
                "success": False,
                "action": side,
                "order_id": None,
                "price": price,
                "quantity": quantity,
                "error": error_msg
            }
            
        except Exception as e:
            logger.error(f"Error executing Hyperliquid trade: {e}")
            return {
                "success": False,
                "action": side,
                "order_id": None,
                "price": 0.0,
                "quantity": quantity,
                "error": str(e)
            }
    
    
    def get_positions(self) -> List[Dict[str, Any]]:
        """Get current positions from Hyperliquid."""
        try:
            endpoint = "/info"
            data = {"type": "clearinghouseState", "user": self.main_wallet_address}
            response = self._make_request(endpoint, method="POST", data=data)
            
            positions = []
            # Hyperliquid returns assetPositions at the top level (not nested under "data")
            if "assetPositions" in response:
                asset_positions = response["assetPositions"]
                
                for pos in asset_positions:
                    position = pos.get("position", {})
                    coin = position.get("coin", "")
                    size = float(position.get("szi", 0))  # Size
                    entry_price = float(position.get("entryPx", 0))  # Entry price
                    
                    if size != 0:
                        # Get current price
                        current_price = self._get_current_price(coin)
                        
                        positions.append({
                            "symbol": coin,
                            "quantity": abs(size),
                            "entry_price": entry_price,
                            "current_price": current_price,
                            "unrealized_pnl": (current_price - entry_price) * size if size > 0 else (entry_price - current_price) * abs(size)
                        })
            
            return positions
        except Exception as e:
            logger.error(f"Error fetching Hyperliquid positions: {e}")
            return []
    
    def _get_current_price(self, coin: str) -> float:
        """Get current price for a coin using SDK."""
        try:
            # Use SDK's info class to get all mid prices
            all_mids = self.info.all_mids()
            
            # Response is a dict mapping coin names to mid prices
            if isinstance(all_mids, dict) and coin in all_mids:
                return float(all_mids[coin])
            
            return 0.0
        except Exception as e:
            logger.error(f"Error fetching current price for {coin}: {e}")
            return 0.0
    
    def _get_size_decimals(self, coin: str) -> int:
        """Get the number of decimal places for size based on coin.
        
        Fetched from Hyperliquid API meta endpoint.
        """
        # Size decimals by coin (from Hyperliquid API)
        size_decimals = {
            "BTC": 5,     # 0.00001 BTC
            "ETH": 4,     # 0.0001 ETH
            "SOL": 2,     # 0.01 SOL
            "DOGE": 0,    # 1 DOGE (whole numbers)
            "XRP": 0,     # 1 XRP
            "ARB": 1,     # 0.1 ARB
            "AVAX": 2,    # 0.01 AVAX
            "LINK": 1,    # 0.1 LINK
            "MATIC": 1,   # 0.1 MATIC
            "BNB": 3,     # 0.001 BNB
            "OP": 1,      # 0.1 OP
            "SUI": 1,     # 0.1 SUI
        }
        return size_decimals.get(coin.upper(), 2)
    
    def _get_min_size(self, coin: str) -> float:
        """Get minimum trade size for a coin on Hyperliquid.
        
        These are the actual Hyperliquid minimums (10^-szDecimals).
        """
        # Minimum sizes from Hyperliquid API (very small!)
        min_sizes = {
            "BTC": 0.00001,  # ~$1 at $100k
            "ETH": 0.0001,   # ~$0.30 at $3k
            "SOL": 0.01,     # ~$2 at $200
            "DOGE": 1,       # ~$0.40
            "XRP": 1,        # ~$2.50
            "ARB": 0.1,      # ~$0.08
            "AVAX": 0.01,    # ~$0.45
            "LINK": 0.1,     # ~$2
            "MATIC": 0.1,    # ~$0.05
            "BNB": 0.001,    # ~$0.70
            "OP": 0.1,       # ~$0.20
            "SUI": 0.1,      # ~$0.40
        }
        return min_sizes.get(coin.upper(), 0.01)
    
    def _round_price(self, coin: str, price: float) -> float:
        """Round price to appropriate decimal places for Hyperliquid.
        
        Uses the SDK's logic to ensure prices are divisible by tick size.
        Formula: round to (6 - sz_decimals) decimals for perps, (8 - sz_decimals) for spot.
        This matches the SDK's _slippage_price method.
        """
        try:
            # Use SDK's name_to_coin mapping (same as SDK does)
            coin_name = self.info.name_to_coin.get(coin.upper())
            if coin_name is None:
                logger.warning(f"Could not find coin mapping for {coin}, using fallback rounding")
                return round(price, 2)
            
            # Get asset ID from coin name
            asset = self.info.coin_to_asset.get(coin_name)
            if asset is None:
                logger.warning(f"Could not find asset for {coin_name}, using fallback rounding")
                return round(price, 2)
            
            # Check if it's spot (spot assets start at 10000)
            is_spot = asset >= 10_000
            
            # Get sz_decimals for this asset
            sz_decimals = self.info.asset_to_sz_decimals.get(asset, 0)
            
            # Use SDK's rounding formula: round to (6 - sz_decimals) for perps, (8 - sz_decimals) for spot
            # First round to 5 significant figures, then to the appropriate decimal places
            # This matches: round(float(f"{px:.5g}"), (6 if not is_spot else 8) - self.info.asset_to_sz_decimals[asset])
            price_5sig = float(f"{price:.5g}")
            decimals = (6 if not is_spot else 8) - sz_decimals
            return round(price_5sig, decimals)
            
        except Exception as e:
            logger.warning(f"Error rounding price for {coin}: {e}, using fallback")
            # Fallback to simple rounding
            return round(price, 2)
    
    def get_account_info(self) -> Dict[str, Any]:
        """Get account information from Hyperliquid."""
        try:
            balance = self.get_balance()
            positions = self.get_positions()
            
            return {
                "balance": balance,
                "positions": positions,
                "wallet_address": self.main_wallet_address
            }
        except Exception as e:
            logger.error(f"Error fetching Hyperliquid account info: {e}")
            raise
    
    def is_paper_trading(self) -> bool:
        """Check if using testnet (paper trading)."""
        return self.testnet
    
    def place_stop_loss(
        self,
        symbol: str,
        quantity: float,
        trigger_price: float,
        is_long: bool = True
    ) -> Dict[str, Any]:
        """Place a stop loss order on Hyperliquid.
        
        For a long position: stop loss triggers when price falls below trigger_price
        For a short position: stop loss triggers when price rises above trigger_price
        
        Args:
            symbol: Coin symbol (e.g., "BTC", "ETH")
            quantity: Quantity to close when triggered
            trigger_price: Price at which to trigger the stop loss
            is_long: True if closing a long position, False for short
            
        Returns:
            Dictionary with order result
        """
        try:
            coin = symbol.upper()
            
            # For stop loss:
            # - Long position: sell when price drops to trigger (trigger below current)
            # - Short position: buy when price rises to trigger (trigger above current)
            is_buy = not is_long
            
            # Round quantity and price
            sz_decimals = self._get_size_decimals(coin)
            quantity = round(quantity, sz_decimals)
            trigger_price = self._round_price(coin, trigger_price)
            
            # Get current price to validate trigger price
            current_price = self._get_current_price(coin)
            
            # Validate that we have a valid current price
            if current_price <= 0:
                return {
                    "success": False,
                    "order_id": None,
                    "trigger_price": float(trigger_price),
                    "error": f"Could not get current price for {coin}"
                }
            
            # Validate trigger price is positive
            if trigger_price <= 0:
                return {
                    "success": False,
                    "order_id": None,
                    "trigger_price": 0.0,
                    "error": f"Invalid trigger price: {trigger_price}"
                }
            
            # Hyperliquid validation: SL trigger must be on correct side of current price
            # For long: trigger must be BELOW current price
            # For short: trigger must be ABOVE current price
            if is_long and trigger_price >= current_price:
                # Adjust trigger to be slightly below current price (0.5% below)
                adjusted_trigger = current_price * 0.995
                logger.warning(f"SL trigger {trigger_price} >= current {current_price} for long, adjusting to {adjusted_trigger}")
                trigger_price = self._round_price(coin, adjusted_trigger)
            elif not is_long and trigger_price <= current_price:
                # Adjust trigger to be slightly above current price (0.5% above)
                adjusted_trigger = current_price * 1.005
                logger.warning(f"SL trigger {trigger_price} <= current {current_price} for short, adjusting to {adjusted_trigger}")
                trigger_price = self._round_price(coin, adjusted_trigger)
            
            logger.info(f"Placing stop loss: {coin} qty={quantity} trigger={trigger_price} current={current_price} is_long={is_long}")
            
            # For market stop loss orders, set limit price with slippage to ensure fill
            # When selling (closing long), use lower limit; when buying (closing short), use higher limit
            slippage = 0.03  # 3% slippage for stop loss to ensure fill in volatile markets
            if is_long:
                # Closing long = selling, accept lower price
                limit_price = trigger_price * (1 - slippage)
            else:
                # Closing short = buying, accept higher price
                limit_price = trigger_price * (1 + slippage)
            limit_price = self._round_price(coin, limit_price)
            
            # Use the SDK's order method with trigger
            # Hyperliquid uses "trigger" orders with tpsl flag
            # Note: triggerPx must be a float (SDK's float_to_wire function expects float)
            # Ensure trigger_price is explicitly a float to avoid type issues
            trigger_price_float = float(trigger_price)
            order_result = self.exchange.order(
                name=coin,
                is_buy=is_buy,
                sz=quantity,
                limit_px=limit_price,
                order_type={"trigger": {"triggerPx": trigger_price_float, "isMarket": True, "tpsl": "sl"}},
                reduce_only=True
            )
            
            logger.info(f"Stop loss order result: {order_result}")
            
            if order_result.get("status") == "ok":
                response_data = order_result.get("response", {}).get("data", {})
                statuses = response_data.get("statuses", [{}])
                
                if statuses and len(statuses) > 0:
                    status = statuses[0]
                    
                    if "error" in status:
                        return {
                            "success": False,
                            "order_id": None,
                            "trigger_price": float(trigger_price),
                            "error": status["error"]
                        }
                    
                    order_id = None
                    if "resting" in status:
                        order_id = status["resting"].get("oid")
                    
                    return {
                        "success": True,
                        "order_id": order_id,
                        "trigger_price": float(trigger_price),
                        "quantity": quantity,
                        "order_type": "stop_loss"
                    }
            
            return {
                "success": False,
                "order_id": None,
                "trigger_price": float(trigger_price),
                "error": "Unknown error placing stop loss"
            }
            
        except Exception as e:
            logger.error(f"Error placing stop loss order: {e}")
            trigger_price_val = float(trigger_price) if 'trigger_price' in locals() else 0.0
            return {
                "success": False,
                "order_id": None,
                "trigger_price": trigger_price_val,
                "error": str(e)
            }
    
    def place_take_profit(
        self,
        symbol: str,
        quantity: float,
        trigger_price: float,
        is_long: bool = True
    ) -> Dict[str, Any]:
        """Place a take profit order on Hyperliquid.
        
        For a long position: take profit triggers when price rises above trigger_price
        For a short position: take profit triggers when price falls below trigger_price
        
        Args:
            symbol: Coin symbol (e.g., "BTC", "ETH")
            quantity: Quantity to close when triggered
            trigger_price: Price at which to trigger the take profit
            is_long: True if closing a long position, False for short
            
        Returns:
            Dictionary with order result
        """
        try:
            coin = symbol.upper()
            
            # For take profit:
            # - Long position: sell when price rises to trigger (trigger above current)
            # - Short position: buy when price drops to trigger (trigger below current)
            is_buy = not is_long
            
            # Round quantity and price
            sz_decimals = self._get_size_decimals(coin)
            quantity = round(quantity, sz_decimals)
            trigger_price = self._round_price(coin, trigger_price)
            
            # Get current price to validate trigger price
            current_price = self._get_current_price(coin)
            
            # Validate that we have a valid current price
            if current_price <= 0:
                return {
                    "success": False,
                    "order_id": None,
                    "trigger_price": float(trigger_price),
                    "error": f"Could not get current price for {coin}"
                }
            
            # Validate trigger price is positive
            if trigger_price <= 0:
                return {
                    "success": False,
                    "order_id": None,
                    "trigger_price": 0.0,
                    "error": f"Invalid trigger price: {trigger_price}"
                }
            
            # Hyperliquid validation: TP trigger must be on correct side of current price
            # For long: trigger must be ABOVE current price
            # For short: trigger must be BELOW current price
            if is_long and trigger_price <= current_price:
                # Adjust trigger to be slightly above current price (0.5% above)
                adjusted_trigger = current_price * 1.005
                logger.warning(f"TP trigger {trigger_price} <= current {current_price} for long, adjusting to {adjusted_trigger}")
                trigger_price = self._round_price(coin, adjusted_trigger)
            elif not is_long and trigger_price >= current_price:
                # Adjust trigger to be slightly below current price (0.5% below)
                adjusted_trigger = current_price * 0.995
                logger.warning(f"TP trigger {trigger_price} >= current {current_price} for short, adjusting to {adjusted_trigger}")
                trigger_price = self._round_price(coin, adjusted_trigger)
            
            logger.info(f"Placing take profit: {coin} qty={quantity} trigger={trigger_price} current={current_price} is_long={is_long}")
            
            # For market take profit orders, set limit price with slippage to ensure fill
            # When selling (closing long), accept slightly lower; when buying (closing short), accept slightly higher
            slippage = 0.01  # 1% slippage for take profit (less aggressive since price is favorable)
            if is_long:
                # Closing long = selling, accept slightly lower price
                limit_price = trigger_price * (1 - slippage)
            else:
                # Closing short = buying, accept slightly higher price
                limit_price = trigger_price * (1 + slippage)
            limit_price = self._round_price(coin, limit_price)
            
            # Use the SDK's order method with trigger for take profit
            # Note: triggerPx must be a float (SDK's float_to_wire function expects float)
            # Ensure trigger_price is explicitly a float to avoid type issues
            trigger_price_float = float(trigger_price)
            order_result = self.exchange.order(
                name=coin,
                is_buy=is_buy,
                sz=quantity,
                limit_px=limit_price,
                order_type={"trigger": {"triggerPx": trigger_price_float, "isMarket": True, "tpsl": "tp"}},
                reduce_only=True
            )
            
            logger.info(f"Take profit order result: {order_result}")
            
            if order_result.get("status") == "ok":
                response_data = order_result.get("response", {}).get("data", {})
                statuses = response_data.get("statuses", [{}])
                
                if statuses and len(statuses) > 0:
                    status = statuses[0]
                    
                    if "error" in status:
                        return {
                            "success": False,
                            "order_id": None,
                            "trigger_price": float(trigger_price),
                            "error": status["error"]
                        }
                    
                    order_id = None
                    if "resting" in status:
                        order_id = status["resting"].get("oid")
                    
                    return {
                        "success": True,
                        "order_id": order_id,
                        "trigger_price": float(trigger_price),
                        "quantity": quantity,
                        "order_type": "take_profit"
                    }
            
            return {
                "success": False,
                "order_id": None,
                "trigger_price": float(trigger_price),
                "error": "Unknown error placing take profit"
            }
            
        except Exception as e:
            logger.error(f"Error placing take profit order: {e}")
            trigger_price_val = float(trigger_price) if 'trigger_price' in locals() else 0.0
            return {
                "success": False,
                "order_id": None,
                "trigger_price": trigger_price_val,
                "error": str(e)
            }
    
    def get_open_trigger_orders(
        self,
        symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get open trigger orders (stop loss and take profit) from Hyperliquid.
        
        Args:
            symbol: Optional symbol to filter by (None for all symbols)
            
        Returns:
            List of trigger order dictionaries
        """
        try:
            endpoint = "/info"
            data = {"type": "openOrders", "user": self.main_wallet_address}
            response = self._make_request(endpoint, method="POST", data=data)
            
            trigger_orders = []
            
            for order in response:
                # Check if this is a trigger order
                order_type = order.get("orderType", "")
                
                # Hyperliquid marks trigger orders differently
                if "trigger" in str(order_type).lower() or order.get("triggerCondition"):
                    coin = order.get("coin", "")
                    
                    # Filter by symbol if specified
                    if symbol and coin.upper() != symbol.upper():
                        continue
                    
                    trigger_orders.append({
                        "order_id": order.get("oid"),
                        "symbol": coin,
                        "trigger_price": float(order.get("triggerPx", 0)),
                        "quantity": float(order.get("sz", 0)),
                        "side": "buy" if order.get("side") == "B" else "sell",
                        "order_type": "stop_loss" if "sl" in str(order_type).lower() else "take_profit"
                    })
            
            return trigger_orders
            
        except Exception as e:
            logger.error(f"Error fetching open trigger orders: {e}")
            return []
    
    def cancel_trigger_orders(
        self,
        symbol: str
    ) -> Dict[str, Any]:
        """Cancel all trigger orders (stop loss and take profit) for a symbol.
        
        Args:
            symbol: Trading symbol (e.g., "BTC", "ETH")
            
        Returns:
            Dictionary with cancellation result
        """
        try:
            coin = symbol.upper()
            
            # Get all open trigger orders for this symbol
            trigger_orders = self.get_open_trigger_orders(symbol=coin)
            
            if not trigger_orders:
                return {
                    "success": True,
                    "cancelled_count": 0,
                    "message": f"No trigger orders found for {coin}"
                }
            
            cancelled_count = 0
            errors = []
            
            for order in trigger_orders:
                order_id = order.get("order_id")
                if order_id:
                    try:
                        # Cancel the order using the SDK
                        cancel_result = self.exchange.cancel(coin, order_id)
                        
                        if cancel_result.get("status") == "ok":
                            cancelled_count += 1
                            logger.info(f"Cancelled trigger order {order_id} for {coin}")
                        else:
                            errors.append(f"Failed to cancel order {order_id}")
                    except Exception as e:
                        errors.append(f"Error cancelling order {order_id}: {str(e)}")
            
            return {
                "success": cancelled_count > 0 or len(errors) == 0,
                "cancelled_count": cancelled_count,
                "errors": errors if errors else None
            }
            
        except Exception as e:
            logger.error(f"Error cancelling trigger orders: {e}")
            return {
                "success": False,
                "cancelled_count": 0,
                "error": str(e)
            }

