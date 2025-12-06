from datetime import date as date_cls, datetime
from sqlalchemy import Column, DateTime, Enum, String, Float, Integer, BigInteger, Date, Boolean, ForeignKey, Text
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class UserModel(Base):
    """Stores uploaded user trading models as raw source."""

    __tablename__ = "user_models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False)  # Google OAuth user ID
    name = Column(String(255), nullable=False)
    code = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    active = Column(Boolean, default=True)  # Whether the model is currently active
    balance = Column(Float, default=1000.0)  # Starting balance for the model
    start_balance = Column(Float, default=1000.0)  # Initial balance when model was created
    weights = Column(String, nullable=True)  # Optional: stores weights file content or path
    tickers = Column(String, nullable=False)  # Optional: stores JSON array of tickers as string
    
    # Risk management settings
    uncertainty_threshold = Column(Float, default=0.7)  # Skip trades if LLM uncertainty > this value (0.0-1.0)
    max_position_size_pct = Column(Float, default=0.25)  # Max % of portfolio for single position (0.0-1.0)
    default_leverage = Column(Float, default=1.0)  # Default leverage for trades (1.0-50.0)
    stop_loss_pct = Column(Float, nullable=True)  # Optional auto stop-loss % (e.g., 0.05 = 5%)
    take_profit_pct = Column(Float, nullable=True)  # Optional auto take-profit % (e.g., 0.10 = 10%)


class User(Base):
    """
    Stores user information from Google OAuth.
    """
    __tablename__ = 'users'

    id = Column(String(255), primary_key=True)  # Google OAuth user ID
    email = Column(String(255), unique=True, nullable=False)
    name = Column(String(255), nullable=False)
    picture = Column(String(512))  # URL to user's profile picture
    created_at = Column(DateTime, default=datetime.now)
    last_login = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    balance = Column(Float, default=100000.0)  # User's account balance
    # TODO: Add TraderPerformance model and relationship when needed
    # performance = relationship("TraderPerformance", back_populates="user", uselist=False)

    def __repr__(self):
        return f"<User(id='{self.id}', name='{self.name}')>"


class MarketData(Base):
    """Stores cached market data fetched from the market data API."""
    
    __tablename__ = "market_data"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(50), nullable=False, index=True)  # e.g., "BTC/USDT"
    coin_name = Column(String(50), nullable=False, index=True)  # e.g., "BTC"
    current_price = Column(Float, nullable=False)
    open_price = Column(Float, nullable=False)
    high_price = Column(Float, nullable=False)
    low_price = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)
    percentage_change = Column(Float, nullable=False)
    trend = Column(String(10), nullable=False)  # "up" or "down"
    # Store 24h history as JSON string for quick access
    history_24h = Column(Text, nullable=True)  # JSON array of {timestamp, price}
    created_at = Column(DateTime, default=datetime.now, nullable=False, index=True)
    
    def __repr__(self):
        return f"<MarketData(symbol='{self.symbol}', price={self.current_price}, created_at='{self.created_at}')>"


class BrokerConnection(Base):
    """Stores encrypted broker/exchange API credentials for users."""
    
    __tablename__ = "broker_connections"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, index=True)  # Foreign key to users table
    exchange = Column(String(50), nullable=False)  # e.g., "hyperliquid"
    encrypted_api_key = Column(Text, nullable=True)  # Encrypted API key (reserved for future exchanges)
    encrypted_api_secret = Column(Text, nullable=True)  # Encrypted API secret (reserved for future exchanges)
    # Hyperliquid-specific fields
    main_wallet_address = Column(String(255), nullable=True)  # Hyperliquid main wallet address (for balance queries)
    encrypted_agent_wallet_private_key = Column(Text, nullable=True)  # Encrypted Hyperliquid agent wallet private key (for trade execution)
    is_testnet = Column(Boolean, default=False)  # Whether using testnet (for Hyperliquid)
    is_connected = Column(Boolean, default=True)  # Connection status flag
    connection_status = Column(String(20), default='disconnected')  # 'connected' | 'disconnected' | 'error'
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    last_verified = Column(DateTime, nullable=True)  # Last time connection was verified
    
    def __repr__(self):
        return f"<BrokerConnection(id={self.id}, user_id='{self.user_id}', exchange='{self.exchange}')>"


class Trade(Base):
    """Stores executed trades from trading agents."""
    
    __tablename__ = "trades"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    trader_id = Column(Integer, ForeignKey('user_models.id'), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)  # For quick user filtering
    symbol = Column(String(20), nullable=False)  # e.g., "BTCUSDT"
    coin = Column(String(10), nullable=False)  # e.g., "BTC"
    side = Column(String(10), nullable=False)  # "buy", "sell", "hold"
    quantity = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    uncertainty = Column(Float, nullable=True)  # Uncertainty from LLM decision
    order_id = Column(String(100), nullable=True)  # Exchange order ID
    order_response = Column(Text, nullable=True)  # Full order response JSON
    stop_loss_order = Column(Text, nullable=True)  # Stop loss order info JSON
    take_profit_order = Column(Text, nullable=True)  # Take profit order info JSON
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    executed_at = Column(DateTime, default=datetime.now, nullable=False, index=True)
    
    def __repr__(self):
        return f"<Trade(id={self.id}, trader_id={self.trader_id}, symbol={self.symbol}, side={self.side})>"


class APICallLog(Base):
    """Stores logs of LLM API calls and responses."""
    
    __tablename__ = "api_call_logs"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    trader_id = Column(Integer, ForeignKey('user_models.id'), nullable=False, index=True)
    user_id = Column(String(255), nullable=False, index=True)  # For quick user filtering
    model_name = Column(String(50), nullable=False)  # LLM model used (e.g., "gpt-4o-mini")
    prompt = Column(Text, nullable=True)  # Full prompt sent (can be large, optional)
    prompt_length = Column(Integer, nullable=True)  # Length of prompt in characters
    response = Column(Text, nullable=False)  # LLM response JSON
    decision_coin = Column(String(10), nullable=True)
    decision_action = Column(String(10), nullable=True)  # "buy", "sell", "hold"
    decision_uncertainty = Column(Float, nullable=True)
    decision_quantity = Column(Float, nullable=True)
    tokens_used = Column(Integer, nullable=True)  # If available from API response
    latency_ms = Column(Integer, nullable=True)  # API call latency in milliseconds
    success = Column(Boolean, default=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False, index=True)
    
    def __repr__(self):
        return f"<APICallLog(id={self.id}, trader_id={self.trader_id}, model={self.model_name})>"


class BTCHistoryCache(Base):
    """Stores cached BTC historical price data for different timeframes."""
    
    __tablename__ = "btc_history_cache"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    timeframe = Column(String(10), nullable=False, unique=True, index=True)  # '1W', '1M', '3M'
    history_data = Column(Text, nullable=False)  # JSON array of {date, price} objects
    created_at = Column(DateTime, default=datetime.now, nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    
    def __repr__(self):
        return f"<BTCHistoryCache(timeframe='{self.timeframe}', updated_at='{self.updated_at}')>"


class DashboardCache(Base):
    """Stores cached dashboard data per user for instant loading."""
    
    __tablename__ = "dashboard_cache"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, unique=True, index=True)
    # Cached data as JSON strings
    broker_balances = Column(Text, nullable=True)  # JSON: broker balances and positions
    trades = Column(Text, nullable=True)  # JSON: recent trades
    api_logs = Column(Text, nullable=True)  # JSON: API call logs
    balance_history = Column(Text, nullable=True)  # JSON: portfolio value history
    traders = Column(Text, nullable=True)  # JSON: user's traders
    # Timestamps
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    
    def __repr__(self):
        return f"<DashboardCache(user_id='{self.user_id}', updated_at='{self.updated_at}')>"


class PortfolioBalanceSnapshot(Base):
    """Stores portfolio balance snapshots over time for historical tracking."""
    
    __tablename__ = "portfolio_balance_snapshots"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False, index=True)
    balance = Column(Float, nullable=False)  # Total portfolio balance at this snapshot
    created_at = Column(DateTime, default=datetime.now, nullable=False, index=True)
    
    def __repr__(self):
        return f"<PortfolioBalanceSnapshot(user_id='{self.user_id}', balance={self.balance}, created_at='{self.created_at}')>"
