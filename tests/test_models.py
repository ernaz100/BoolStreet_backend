"""
Test suite for database models.
Tests model creation, relationships, and methods.
"""

import pytest
from datetime import datetime, date


@pytest.mark.database
@pytest.mark.unit
class TestDatabaseModels:
    """Test class for database model functionality."""

    def test_user_model_creation(self, test_db):
        """
        Test User model creation and basic functionality.
        Should create user with all required fields.
        """
        from db.models import User
        
        user = User(
            id='test_user_123',
            email='test@example.com',
            name='Test User',
            picture='https://example.com/avatar.jpg',
            created_at=datetime.now(),
            last_login=datetime.now()
        )
        
        test_db.add(user)
        test_db.commit()
        
        # Retrieve and verify
        retrieved_user = test_db.query(User).filter_by(id='test_user_123').first()
        assert retrieved_user is not None
        assert retrieved_user.email == 'test@example.com'
        assert retrieved_user.name == 'Test User'
        assert retrieved_user.picture == 'https://example.com/avatar.jpg'
        assert str(retrieved_user) == "<User(id='test_user_123', name='Test User')>"

    def test_user_script_model_creation(self, test_db):
        """
        Test UserScript model creation and fields.
        Should create script with all required fields and defaults.
        """
        from db.models import UserScript
        
        script = UserScript(
            user_id='test_user_123',
            name='Test Strategy',
            code='def run(data): return {"action": "buy"}',
            created_at=date.today(),
            active=True,
            balance=1000.0,
            start_balance=1000.0
        )
        
        test_db.add(script)
        test_db.commit()
        
        # Retrieve and verify
        retrieved_script = test_db.query(UserScript).first()
        assert retrieved_script is not None
        assert retrieved_script.user_id == 'test_user_123'
        assert retrieved_script.name == 'Test Strategy'
        assert retrieved_script.active is True
        assert retrieved_script.balance == 1000.0
        assert retrieved_script.start_balance == 1000.0

    def test_user_script_defaults(self, test_db):
        """
        Test UserScript model default values.
        Should set correct defaults for optional fields.
        """
        from db.models import UserScript
        
        # Create script with minimal required fields
        script = UserScript(
            user_id='test_user_123',
            name='Minimal Script',
            code='def run(data): pass'
        )
        
        test_db.add(script)
        test_db.commit()
        
        # Check defaults
        assert script.created_at == date.today()
        assert script.active is True
        assert script.balance == 1000.0
        assert script.start_balance == 1000.0

    def test_script_prediction_model_creation(self, test_db):
        """
        Test ScriptPrediction model creation.
        Should create prediction with all fields.
        """
        from db.models import ScriptPrediction
        
        prediction = ScriptPrediction(
            script_id=1,
            timestamp=date.today(),
            prediction='BUY AAPL',
            confidence=0.85,
            actual_result='PROFITABLE',
            profit_loss=50.0,
            balance_after=1050.0
        )
        
        test_db.add(prediction)
        test_db.commit()
        
        # Retrieve and verify
        retrieved_prediction = test_db.query(ScriptPrediction).first()
        assert retrieved_prediction is not None
        assert retrieved_prediction.script_id == 1
        assert retrieved_prediction.prediction == 'BUY AAPL'
        assert retrieved_prediction.confidence == 0.85
        assert retrieved_prediction.profit_loss == 50.0

    def test_market_data_model_creation(self, test_db):
        """
        Test MarketData model creation with different types.
        Should create both stock and index data.
        """
        from db.models import MarketData
        
        # Create stock data
        stock_data = MarketData(
            symbol='AAPL',
            company_name='Apple Inc.',
            type='stock',
            current_value=175.25,
            percentage_change=2.5,
            volume=50000000,
            timestamp=datetime.now()
        )
        
        # Create index data
        index_data = MarketData(
            symbol='SPY',
            index_name='S&P 500',
            type='index',
            current_value=450.75,
            percentage_change=1.25,
            timestamp=datetime.now()
        )
        
        test_db.add(stock_data)
        test_db.add(index_data)
        test_db.commit()
        
        # Retrieve and verify
        stock = test_db.query(MarketData).filter_by(symbol='AAPL').first()
        assert stock.type == 'stock'
        assert stock.company_name == 'Apple Inc.'
        assert stock.volume == 50000000
        
        index = test_db.query(MarketData).filter_by(symbol='SPY').first()
        assert index.type == 'index'
        assert index.index_name == 'S&P 500'
        assert index.volume is None

    def test_market_data_repr(self, test_db):
        """
        Test MarketData __repr__ method.
        Should return formatted string representation.
        """
        from db.models import MarketData
        
        market_data = MarketData(
            symbol='AAPL',
            type='stock',
            current_value=175.25,
            timestamp=datetime.now()
        )
        
        test_db.add(market_data)
        test_db.commit()
        
        expected_repr = "<MarketData(symbol='AAPL', type='stock', value=175.25)>"
        assert str(market_data) == expected_repr

    def test_trader_performance_model_creation(self, test_db):
        """
        Test TraderPerformance model creation.
        Should create performance record with all fields.
        """
        from db.models import TraderPerformance
        
        performance = TraderPerformance(
            user_id='test_user_123',
            name='Test Trader',
            model_name='Test Model',
            accuracy=85.0,
            total_profit=1500.0,
            win_rate=75.0,
            rank=1
        )
        
        test_db.add(performance)
        test_db.commit()
        
        # Retrieve and verify
        retrieved_performance = test_db.query(TraderPerformance).first()
        assert retrieved_performance is not None
        assert retrieved_performance.user_id == 'test_user_123'
        assert retrieved_performance.name == 'Test Trader'
        assert retrieved_performance.model_name == 'Test Model'
        assert retrieved_performance.accuracy == 85.0
        assert retrieved_performance.total_profit == 1500.0
        assert retrieved_performance.win_rate == 75.0
        assert retrieved_performance.rank == 1

    def test_trader_performance_repr(self, test_db):
        """
        Test TraderPerformance __repr__ method.
        Should return formatted string representation.
        """
        from db.models import TraderPerformance
        
        performance = TraderPerformance(
            user_id='test_user_123',
            name='Test Trader',
            model_name='Test Model',
            accuracy=85.0,
            total_profit=1500.0,
            win_rate=75.0
        )
        
        test_db.add(performance)
        test_db.commit()
        
        expected_repr = "<TraderPerformance(name='Test Trader', model='Test Model', profit=1500.0)>"
        assert str(performance) == expected_repr

    def test_trader_performance_to_dict_with_user(self, test_db):
        """
        Test TraderPerformance to_dict method with user relationship.
        Should use user data when available.
        """
        from db.models import TraderPerformance, User
        
        # Create user
        user = User(
            id='test_user_123',
            email='test@example.com',
            name='Test User',
            picture='https://example.com/avatar.jpg'
        )
        
        # Create performance with user relationship
        performance = TraderPerformance(
            user_id='test_user_123',
            name='Test Trader',
            model_name='Test Model',
            accuracy=85.0,
            total_profit=1500.0,
            win_rate=75.0,
            rank=1
        )
        performance.user = user
        
        test_db.add(user)
        test_db.add(performance)
        test_db.commit()
        
        result = performance.to_dict()
        
        assert result['rank'] == 1
        assert result['name'] == 'Test User'  # From user relationship
        assert result['avatar'] == 'https://example.com/avatar.jpg'
        assert result['model'] == 'Test Model'
        assert result['accuracy'] == '85%'
        assert result['profit'] == '+$1,500'
        assert result['winRate'] == '75%'
        assert result['isCurrentUser'] is False

    def test_trader_performance_to_dict_without_user(self, test_db):
        """
        Test TraderPerformance to_dict method without user relationship.
        Should use trader's own name and create initials avatar.
        """
        from db.models import TraderPerformance
        
        performance = TraderPerformance(
            user_id='test_user_123',
            name='Test Trader',
            model_name='Test Model',
            accuracy=85.0,
            total_profit=1500.0,
            win_rate=75.0,
            rank=1
        )
        
        test_db.add(performance)
        test_db.commit()
        
        result = performance.to_dict()
        
        assert result['name'] == 'Test Trader'  # Trader's own name
        assert result['avatar'] == 'TE'  # First two letters of name

    def test_user_trader_performance_relationship(self, test_db):
        """
        Test relationship between User and TraderPerformance models.
        Should properly link user and performance records.
        """
        from db.models import User, TraderPerformance
        
        # Create user
        user = User(
            id='test_user_123',
            email='test@example.com',
            name='Test User',
            picture='https://example.com/avatar.jpg'
        )
        
        # Create performance
        performance = TraderPerformance(
            user_id='test_user_123',
            name='Test Trader',
            model_name='Test Model',
            accuracy=85.0,
            total_profit=1500.0,
            win_rate=75.0,
            rank=1
        )
        
        test_db.add(user)
        test_db.add(performance)
        test_db.commit()
        
        # Test relationship access
        retrieved_user = test_db.query(User).filter_by(id='test_user_123').first()
        assert retrieved_user.performance is not None
        assert retrieved_user.performance.model_name == 'Test Model'
        
        retrieved_performance = test_db.query(TraderPerformance).first()
        assert retrieved_performance.user is not None
        assert retrieved_performance.user.name == 'Test User'

    def test_daily_bar_model_creation(self, test_db):
        """
        Test DailyBar model creation.
        Should create OHLCV data with composite primary key.
        """
        from db.models import DailyBar
        
        bar = DailyBar(
            ticker='AAPL',
            date=date.today(),
            open=175.0,
            high=177.5,
            low=174.0,
            close=176.25,
            volume=50000000
        )
        
        test_db.add(bar)
        test_db.commit()
        
        # Retrieve and verify
        retrieved_bar = test_db.query(DailyBar).filter_by(ticker='AAPL').first()
        assert retrieved_bar is not None
        assert retrieved_bar.ticker == 'AAPL'
        assert retrieved_bar.date == date.today()
        assert retrieved_bar.open == 175.0
        assert retrieved_bar.high == 177.5
        assert retrieved_bar.low == 174.0
        assert retrieved_bar.close == 176.25
        assert retrieved_bar.volume == 50000000

    def test_daily_bar_composite_key(self, test_db):
        """
        Test DailyBar composite primary key constraint.
        Should allow same ticker on different dates but not duplicate ticker-date pairs.
        """
        from db.models import DailyBar
        from datetime import timedelta
        
        # Create first bar
        bar1 = DailyBar(
            ticker='AAPL',
            date=date.today(),
            open=175.0,
            high=177.5,
            low=174.0,
            close=176.25,
            volume=50000000
        )
        
        # Create second bar for same ticker, different date
        bar2 = DailyBar(
            ticker='AAPL',
            date=date.today() - timedelta(days=1),
            open=174.0,
            high=176.0,
            low=173.0,
            close=175.0,
            volume=45000000
        )
        
        test_db.add(bar1)
        test_db.add(bar2)
        test_db.commit()
        
        # Should have both bars
        bars = test_db.query(DailyBar).filter_by(ticker='AAPL').all()
        assert len(bars) == 2

    def test_model_defaults_and_nullable_fields(self, test_db):
        """
        Test model field defaults and nullable constraints.
        Should handle optional fields correctly.
        """
        from db.models import MarketData, ScriptPrediction
        
        # Test MarketData with minimal required fields
        market_data = MarketData(
            symbol='TEST',
            type='stock',
            current_value=100.0
        )
        
        test_db.add(market_data)
        test_db.commit()
        
        # Should use default timestamp
        assert market_data.timestamp is not None
        assert market_data.percentage_change is None
        assert market_data.volume is None
        
        # Test ScriptPrediction with minimal fields
        prediction = ScriptPrediction(
            script_id=1,
            prediction='TEST PREDICTION'
        )
        
        test_db.add(prediction)
        test_db.commit()
        
        # Should use default timestamp
        assert prediction.timestamp == date.today()
        assert prediction.confidence is None
        assert prediction.actual_result is None 