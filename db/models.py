from datetime import date as date_cls, datetime
from sqlalchemy import Column, DateTime, Enum, String, Float, Integer, BigInteger, Date, Boolean
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class DailyBar(Base):
    """OHLCV bar at daily resolution (Polygon `/prev` endpoint)."""

    __tablename__ = "daily_bars"

    ticker: str = Column(String(10), primary_key=True)
    date: date_cls = Column(Date, primary_key=True)  # trading day (UTC)

    open: float = Column(Float)
    high: float = Column(Float)
    low: float = Column(Float)
    close: float = Column(Float)
    volume: int = Column(BigInteger)


class UserScript(Base):
    """Stores uploaded user strategy scripts as raw source."""

    __tablename__ = "user_scripts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), nullable=False)  # Google OAuth user ID
    name = Column(String(255), nullable=False)
    code = Column(String, nullable=False)
    created_at = Column(Date, default=date_cls.today)
    active = Column(Boolean, default=True)  # Whether the script is currently active
    balance = Column(Float, default=1000.0)  # Starting balance for the script
    start_balance = Column(Float, default=1000.0)  # Initial balance when script was created


class ScriptPrediction(Base):
    """Tracks predictions and performance metrics for each script execution."""

    __tablename__ = "script_predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    script_id = Column(Integer, nullable=False)  # Reference to UserScript
    timestamp = Column(Date, default=date_cls.today)
    prediction = Column(String, nullable=False)  # The prediction made by the script
    confidence = Column(Float)  # Confidence score of the prediction (if available)
    actual_result = Column(String)  # The actual result (if available)
    profit_loss = Column(Float)  # Profit/loss from this prediction
    balance_after = Column(Float)  # Balance after this prediction 

class MarketData(Base):
    """
    MarketData model for storing market data including indices and stock information
    """
    __tablename__ = 'market_data'

    id = Column(Integer, primary_key=True)
    symbol = Column(String(10), nullable=False, index=True)  # Stock symbol or index code
    index_name = Column(String(50))  # Full name of the index (for indices)
    company_name = Column(String(100))  # Company name (for stocks)
    type = Column(Enum('stock', 'index', name='market_data_type'), nullable=False)  # Type of data (stock or index)
    current_value = Column(Float, nullable=False)  # Current price/value
    percentage_change = Column(Float)  # Percentage change
    volume = Column(Integer)  # Trading volume (for stocks)
    timestamp = Column(DateTime, default=datetime.now(), nullable=False)  # When the data was recorded

    def __repr__(self):
        return f"<MarketData(symbol='{self.symbol}', type='{self.type}', value={self.current_value})>" 