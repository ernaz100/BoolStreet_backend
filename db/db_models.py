from datetime import date as date_cls, datetime
from sqlalchemy import Column, DateTime, Enum, String, Float, Integer, BigInteger, Date, Boolean, ForeignKey
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


class ModelPrediction(Base):
    """Tracks predictions and performance metrics for each trading model execution."""

    __tablename__ = "model_predictions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(Integer, nullable=False)  # Reference to UserModel
    timestamp = Column(Date, default=date_cls.today)
    prediction = Column(String, nullable=False)  # The prediction made by the model
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
    open_value = Column(Float)  # Open price/value
    high_value = Column(Float)  # High price/value
    low_value = Column(Float)  # Low price/value
    percentage_change = Column(Float)  # Percentage change
    volume = Column(Integer)  # Trading volume (for stocks)
    timestamp = Column(DateTime, default=datetime.now(), nullable=False)  # When the data was recorded

    def __repr__(self):
        return f"<MarketData(symbol='{self.symbol}', type='{self.type}', value={self.current_value})>" 

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
    performance = relationship("TraderPerformance", back_populates="user", uselist=False)

    def __repr__(self):
        return f"<User(id='{self.id}', name='{self.name}')>"

class TraderPerformance(Base):
    """
    Tracks trader performance metrics for the leaderboard.
    This includes their trading model, accuracy, profit, and win rate.
    """
    __tablename__ = 'trader_performance'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(255), ForeignKey('users.id'), nullable=False)  # Google OAuth user ID
    name = Column(String(255), nullable=False)
    model_name = Column(String(255), nullable=False)  # Name of their trading model
    accuracy = Column(Float, nullable=False)  # Prediction accuracy as percentage
    total_profit = Column(Float, nullable=False)  # Total profit/loss
    win_rate = Column(Float, nullable=False)  # Win rate as percentage
    last_updated = Column(DateTime, default=datetime.now(), onupdate=datetime.now)
    rank = Column(Integer)  # Current rank in the leaderboard

    # Relationships
    user = relationship("User", back_populates="performance")

    def __repr__(self):
        return f"<TraderPerformance(name='{self.name}', model='{self.model_name}', profit={self.total_profit})>"

    def to_dict(self):
        """Convert the model instance to a dictionary matching the frontend structure."""
        return {
            "rank": self.rank,
            "name": self.user.name if self.user else self.name,
            "avatar": self.user.picture if self.user else self.name[:2].upper(),
            "model": self.model_name,
            "accuracy": f"{self.accuracy:.0f}%",
            "profit": f"+${self.total_profit:,.0f}",
            "winRate": f"{self.win_rate:.0f}%",
            "isCurrentUser": False
        } 