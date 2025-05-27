"""
Test suite for dashboard functionality.
Tests dashboard statistics and predictions retrieval.
"""

import pytest
import json
from unittest.mock import patch
from datetime import date
from collections import namedtuple


@pytest.mark.api
@pytest.mark.integration
class TestDashboardAPI:
    """Test class for dashboard API endpoints."""

    def test_get_dashboard_stats_success(self, client, auth_headers, mock_db_session, sample_user_script):
        """
        Test getting dashboard statistics with existing models.
        Should return correct statistics for user's models.
        """
        # Create multiple models for testing
        script1 = sample_user_script
        script2 = sample_user_script.__class__(
            id=2,
            user_id='test_user_123',
            name='Test Strategy 2',
            code='def run(data): pass',
            created_at=date.today(),
            active=False,
            balance=1200.0,
            start_balance=1000.0
        )
        
        mock_db_session.add(script1)
        mock_db_session.add(script2)
        mock_db_session.commit()

        with patch('apis.dashboard.get_session') as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_db_session
            mock_get_session.return_value.__exit__.return_value = None

            response = client.get('/dashboard/stats', headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['total_models'] == 2
            assert data['active_models'] == 1  # Only script1 is active
            assert data['total_balance'] == 2200.0  # 1000 + 1200
            assert data['net_profit'] == 200.0  # (1000-1000) + (1200-1000)

    def test_get_dashboard_stats_no_scripts(self, client, auth_headers, mock_db_session):
        """
        Test getting dashboard statistics when user has no models.
        Should return default values.
        """
        with patch('apis.dashboard.get_session') as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_db_session
            mock_get_session.return_value.__exit__.return_value = None

            response = client.get('/dashboard/stats', headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['total_models'] == 0
            assert data['active_models'] == 0
            assert data['total_balance'] == 0.0
            assert data['net_profit'] == 0.0

    def test_get_dashboard_stats_no_auth(self, client):
        """
        Test getting dashboard statistics without authentication.
        Should return 401 Unauthorized.
        """
        response = client.get('/dashboard/stats')
        assert response.status_code == 401

    def test_get_recent_predictions_success(self, client, auth_headers, mock_db_session, 
                                          sample_user_script, sample_script_prediction):
        """
        Test getting recent predictions with existing data.
        Should return predictions with model names.
        """
        # Add sample data to test database
        mock_db_session.add(sample_user_script)
        mock_db_session.add(sample_script_prediction)
        mock_db_session.commit()

        # Mock the query to return our test data
        MockPredictionRow = namedtuple('MockPredictionRow', ['prediction', 'model_name', 'confidence', 'timestamp', 'profit_loss'])

        mock_query_result = [
            MockPredictionRow(
                model_name='Test Strategy',
                prediction=sample_script_prediction.prediction,
                confidence=sample_script_prediction.confidence,
                timestamp=sample_script_prediction.timestamp,
                profit_loss=sample_script_prediction.profit_loss
            )
        ]
        
        with patch('apis.dashboard.get_session') as mock_get_session:
            mock_session = mock_get_session.return_value.__enter__.return_value
            mock_session.query.return_value.join.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = mock_query_result

            response = client.get('/dashboard/predictions', headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'predictions' in data
            assert len(data['predictions']) == 1
            
            prediction = data['predictions'][0]
            assert prediction['model_name'] == 'Test Strategy'
            assert prediction['prediction'] == 'BUY AAPL'
            assert prediction['confidence'] == 0.85
            assert prediction['profit_loss'] == 50.0

    def test_get_recent_predictions_empty(self, client, auth_headers, mock_db_session):
        """
        Test getting recent predictions when no predictions exist.
        Should return empty predictions list.
        """
        with patch('apis.dashboard.get_session') as mock_get_session:
            mock_session = mock_get_session.return_value.__enter__.return_value
            mock_session.query.return_value.join.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

            response = client.get('/dashboard/predictions', headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'predictions' in data
            assert len(data['predictions']) == 0

    def test_get_recent_predictions_no_auth(self, client):
        """
        Test getting recent predictions without authentication.
        Should return 401 Unauthorized.
        """
        response = client.get('/dashboard/predictions')
        assert response.status_code == 401

    def test_get_dashboard_stats_mixed_balances(self, client, auth_headers, mock_db_session):
        """
        Test dashboard statistics with models having different profit/loss.
        Should correctly calculate net profit including losses.
        """
        from backend.db.db_models import UserScript
        
        # Create models with different performance
        script1 = UserScript(
            id=1,
            user_id='test_user_123',
            name='Profitable Model',
            code='def run(data): pass',
            created_at=date.today(),
            active=True,
            balance=1500.0,  # +500 profit
            start_balance=1000.0
        )
        
        script2 = UserScript(
            id=2,
            user_id='test_user_123',
            name='Loss Model',
            code='def run(data): pass',
            created_at=date.today(),
            active=True,
            balance=800.0,  # -200 loss
            start_balance=1000.0
        )
        
        mock_db_session.add(script1)
        mock_db_session.add(script2)
        mock_db_session.commit()

        with patch('apis.dashboard.get_session') as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_db_session
            mock_get_session.return_value.__exit__.return_value = None

            response = client.get('/dashboard/stats', headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['total_models'] == 2
            assert data['active_models'] == 2
            assert data['total_balance'] == 2300.0  # 1500 + 800
            assert data['net_profit'] == 300.0  # 500 + (-200)

    def test_get_dashboard_stats_inactive_scripts(self, client, auth_headers, mock_db_session):
        """
        Test dashboard statistics with mix of active and inactive models.
        Should count all models but only active ones in active_models.
        """
        from backend.db.db_models import UserScript
        
        # Create mix of active and inactive models
        script1 = UserScript(
            id=1,
            user_id='test_user_123',
            name='Active Model',
            code='def run(data): pass',
            created_at=date.today(),
            active=True,
            balance=1100.0,
            start_balance=1000.0
        )
        
        script2 = UserScript(
            id=2,
            user_id='test_user_123',
            name='Inactive Model',
            code='def run(data): pass',
            created_at=date.today(),
            active=False,
            balance=1200.0,
            start_balance=1000.0
        )
        
        script3 = UserScript(
            id=3,
            user_id='test_user_123',
            name='Another Inactive Model',
            code='def run(data): pass',
            created_at=date.today(),
            active=False,
            balance=900.0,
            start_balance=1000.0
        )
        
        mock_db_session.add(script1)
        mock_db_session.add(script2)
        mock_db_session.add(script3)
        mock_db_session.commit()

        with patch('apis.dashboard.get_session') as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_db_session
            mock_get_session.return_value.__exit__.return_value = None

            response = client.get('/dashboard/stats', headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['total_models'] == 3
            assert data['active_models'] == 1  # Only script1 is active
            assert data['total_balance'] == 3200.0  # 1100 + 1200 + 900
            assert data['net_profit'] == 200.0  # 100 + 200 + (-100) 