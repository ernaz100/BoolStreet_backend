"""
Configuration file for pytest with fixtures and test setup.
This file provides common test fixtures used across all test files.
"""

import pytest
import os
import tempfile
from datetime import datetime, date
from unittest.mock import Mock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import app
from db.models import Base, User, UserScript, ScriptPrediction, MarketData, TraderPerformance
from db.database import get_session


@pytest.fixture
def test_app():
    """
    Create a Flask test application with test configuration.
    Uses in-memory SQLite database for isolated testing.
    """
    # Create a temporary database file
    db_fd, db_path = tempfile.mkstemp()
    
    # Configure the app for testing
    app.config['TESTING'] = True
    app.config['JWT_SECRET_KEY'] = 'test-secret-key'
    app.config['SECRET_KEY'] = 'test-secret-key'
    app.config['DATABASE_URL'] = f'sqlite:///{db_path}'
    
    # Override environment variables for testing
    with patch.dict(os.environ, {
        'SECRET_KEY': 'test-secret-key',
        'GOOGLE_CLIENT_ID': 'test-google-client-id',
        'DATABASE_URL': f'sqlite:///{db_path}'
    }):
        yield app
    
    # Cleanup
    os.close(db_fd)
    os.unlink(db_path)


@pytest.fixture
def client(test_app):
    """
    Create a test client for making HTTP requests to the Flask app.
    """
    return test_app.test_client()


@pytest.fixture
def test_db():
    """
    Create an in-memory SQLite database for testing.
    Sets up the database schema and provides a session for tests.
    """
    # Create in-memory SQLite database
    engine = create_engine('sqlite:///:memory:', echo=False)
    
    # Create all tables
    Base.metadata.create_all(engine)
    
    # Create session factory
    Session = sessionmaker(bind=engine)
    session = Session()
    
    yield session
    
    # Cleanup
    session.close()


@pytest.fixture
def mock_db_session(test_db):
    """
    Mock the get_session function to return our test database session.
    """
    # Return the test_db session directly since our mock will replace get_session calls
    yield test_db


@pytest.fixture
def sample_user():
    """
    Create a sample user for testing.
    """
    return User(
        id='test_user_123',
        email='test@example.com',
        name='Test User',
        picture='https://example.com/avatar.jpg',
        created_at=datetime.now(),
        last_login=datetime.now()
    )


@pytest.fixture
def sample_user_script():
    """
    Create a sample user script for testing.
    """
    return UserScript(
        id=1,
        user_id='test_user_123',
        name='Test Strategy',
        code='''
def run(data):
    """Sample trading strategy for testing."""
    return {"action": "buy", "symbol": "AAPL", "quantity": 10}
        ''',
        created_at=date.today(),
        active=True,
        balance=1000.0,
        start_balance=1000.0
    )


@pytest.fixture
def sample_script_prediction():
    """
    Create a sample script prediction for testing.
    """
    return ScriptPrediction(
        id=1,
        script_id=1,
        timestamp=date.today(),
        prediction='BUY AAPL',
        confidence=0.85,
        actual_result='PROFITABLE',
        profit_loss=50.0,
        balance_after=1050.0
    )


@pytest.fixture
def sample_market_data():
    """
    Create sample market data for testing.
    """
    return MarketData(
        id=1,
        symbol='AAPL',
        company_name='Apple Inc.',
        type='stock',
        current_value=150.25,
        percentage_change=2.5,
        volume=1000000,
        timestamp=datetime.now()
    )


@pytest.fixture
def sample_trader_performance():
    """
    Create sample trader performance data for testing.
    """
    return TraderPerformance(
        id=1,
        user_id='test_user_123',
        name='Test Trader',
        model_name='Test Model',
        accuracy=85.0,
        total_profit=1500.0,
        win_rate=75.0,
        rank=1
    )


@pytest.fixture
def mock_google_auth():
    """
    Mock Google OAuth authentication for testing.
    """
    mock_idinfo = {
        'sub': 'test_user_123',
        'email': 'test@example.com',
        'name': 'Test User',
        'picture': 'https://example.com/avatar.jpg'
    }
    
    with patch('google.oauth2.id_token.verify_oauth2_token') as mock_verify:
        mock_verify.return_value = mock_idinfo
        yield mock_verify


@pytest.fixture
def auth_headers(test_app):
    """
    Create authentication headers with a valid JWT token for testing.
    """
    from flask_jwt_extended import create_access_token
    
    with test_app.app_context():
        token = create_access_token(identity='test_user_123')
        return {'Authorization': f'Bearer {token}'}


@pytest.fixture
def mock_yfinance():
    """
    Mock yfinance data for testing market data functionality.
    """
    mock_ticker = Mock()
    mock_ticker.history.return_value = Mock()
    mock_ticker.info = {
        'regularMarketPrice': 150.25,
        'regularMarketChangePercent': 2.5,
        'regularMarketVolume': 1000000,
        'shortName': 'Apple Inc.'
    }
    
    with patch('yfinance.Ticker', return_value=mock_ticker):
        yield mock_ticker


@pytest.fixture
def mock_script_executor():
    """
    Mock the script executor for testing script functionality.
    """
    mock_result = {
        'started_at': datetime.now().isoformat(),
        'ended_at': datetime.now().isoformat(),
        'duration_secs': 1.5,
        'output': 'Script executed successfully'
    }
    
    mock_receipts = [
        {'action': 'buy', 'symbol': 'AAPL', 'quantity': 10, 'price': 150.0}
    ]
    
    # Patch the run_user_script name in the scripts API module so upload_script picks it up
    with patch('apis.scripts.run_user_script') as mock_run:
        mock_run.return_value = (mock_result, mock_receipts)
        yield mock_run 