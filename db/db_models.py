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
    created_at = Column(Date, default=date_cls.today)
    active = Column(Boolean, default=True)  # Whether the model is currently active
    balance = Column(Float, default=1000.0)  # Starting balance for the model
    start_balance = Column(Float, default=1000.0)  # Initial balance when model was created
    weights = Column(String, nullable=True)  # Optional: stores weights file content or path
    tickers = Column(String, nullable=False)  # Optional: stores JSON array of tickers as string


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
