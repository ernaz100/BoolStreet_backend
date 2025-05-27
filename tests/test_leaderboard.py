"""
Test suite for leaderboard functionality.
Tests leaderboard data retrieval, ranking, and user-specific features.
"""

import pytest
import json
from unittest.mock import patch


@pytest.mark.api
@pytest.mark.integration
class TestLeaderboardAPI:
    """Test class for leaderboard API endpoints."""

    def test_get_leaderboard_with_data(self, client, auth_headers, mock_db_session, sample_trader_performance, sample_user):
        """
        Test getting leaderboard with existing trader data.
        Should return leaderboard and current user data.
        """
        # Add sample data to test database
        mock_db_session.add(sample_user)
        mock_db_session.add(sample_trader_performance)
        mock_db_session.commit()

        with patch('apis.leaderboard.get_session') as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_db_session
            mock_get_session.return_value.__exit__.return_value = None

            response = client.get('/api/leaderboard', headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'leaderboard' in data
            assert 'currentUser' in data
            
            # Check leaderboard data
            assert len(data['leaderboard']) == 1
            trader = data['leaderboard'][0]
            assert trader['rank'] == 1
            assert trader['name'] == 'Test User'  # From related user
            assert trader['model'] == 'Test Model'
            assert trader['accuracy'] == '85%'
            assert trader['profit'] == '+$1,500'
            assert trader['winRate'] == '75%'
            
            # Check current user data
            current_user = data['currentUser']
            assert current_user['isCurrentUser'] is True
            assert current_user['name'] == 'Test User'

    def test_get_leaderboard_empty_creates_initial_data(self, client, auth_headers, mock_db_session):
        """
        Test getting leaderboard when no data exists.
        Should create initial sample data and return it.
        """
        with patch('apis.leaderboard.get_session') as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_db_session
            mock_get_session.return_value.__exit__.return_value = None

            response = client.get('/api/leaderboard', headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'leaderboard' in data
            
            # Should have created 5 initial traders
            assert len(data['leaderboard']) == 5
            
            # Check first trader data
            first_trader = data['leaderboard'][0]
            assert first_trader['rank'] == 1
            assert first_trader['name'] == 'John Doe'
            assert first_trader['model'] == 'Quantum Predictor'
            assert first_trader['accuracy'] == '92%'
            assert first_trader['profit'] == '+$45,678'

    def test_get_leaderboard_no_auth(self, client):
        """
        Test getting leaderboard without authentication.
        Should return 401 Unauthorized.
        """
        response = client.get('/api/leaderboard')
        assert response.status_code == 401

    def test_get_leaderboard_current_user_no_performance(self, client, auth_headers, mock_db_session, sample_user):
        """
        Test leaderboard when current user exists but has no performance data.
        Should return user info with 'Not Ranked' status.
        """
        # Add user but no performance data
        mock_db_session.add(sample_user)
        mock_db_session.commit()

        with patch('apis.leaderboard.get_session') as mock_get_session:
            mock_session = mock_get_session.return_value.__enter__.return_value
            # Mock the performance query to return empty
            mock_session.query.return_value.filter_by.return_value.first.return_value = None
            # Mock the user query to return our sample user
            mock_session.query.return_value.filter_by.return_value.first.return_value = sample_user
            # Mock the initial data creation query
            mock_session.query.return_value.order_by.return_value.all.return_value = []

            response = client.get('/api/leaderboard', headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            
            # Check current user data
            current_user = data['currentUser']
            assert current_user['isCurrentUser'] is True
            assert current_user['name'] == 'Test User'
            assert current_user['model'] == 'Not Ranked'
            assert current_user['accuracy'] == 'N/A'
            assert current_user['profit'] == 'N/A'
            assert current_user['winRate'] == 'N/A'

    def test_get_leaderboard_current_user_not_found(self, client, auth_headers, mock_db_session):
        """
        Test leaderboard when current user doesn't exist in database.
        Should return fallback user data.
        """
        with patch('apis.leaderboard.get_session') as mock_get_session:
            mock_session = mock_get_session.return_value.__enter__.return_value
            # Mock all queries to return None/empty
            mock_session.query.return_value.filter_by.return_value.first.return_value = None
            mock_session.query.return_value.order_by.return_value.all.return_value = []

            response = client.get('/api/leaderboard', headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            
            # Check fallback current user data
            current_user = data['currentUser']
            assert current_user['isCurrentUser'] is True
            assert current_user['name'] == 'You'
            assert current_user['model'] == 'Not Ranked'
            assert current_user['avatar'] is None

    def test_update_ranks_function(self, mock_db_session):
        """
        Test the update_ranks function.
        Should properly rank traders by total profit.
        """
        from apis.leaderboard import update_ranks
        from db.models import TraderPerformance
        
        # Create traders with different profits
        traders = [
            TraderPerformance(
                id=1,
                user_id='user1',
                name='Trader 1',
                model_name='Model 1',
                accuracy=90.0,
                total_profit=1000.0,  # Rank 3
                win_rate=80.0,
                rank=0  # Initial rank
            ),
            TraderPerformance(
                id=2,
                user_id='user2',
                name='Trader 2',
                model_name='Model 2',
                accuracy=85.0,
                total_profit=2000.0,  # Rank 1
                win_rate=75.0,
                rank=0  # Initial rank
            ),
            TraderPerformance(
                id=3,
                user_id='user3',
                name='Trader 3',
                model_name='Model 3',
                accuracy=88.0,
                total_profit=1500.0,  # Rank 2
                win_rate=78.0,
                rank=0  # Initial rank
            )
        ]
        
        for trader in traders:
            mock_db_session.add(trader)
        mock_db_session.commit()

        # Update ranks
        update_ranks(mock_db_session)

        # Check that ranks were assigned correctly
        updated_traders = mock_db_session.query(TraderPerformance).order_by(TraderPerformance.rank).all()
        
        assert updated_traders[0].name == 'Trader 2'  # Highest profit
        assert updated_traders[0].rank == 1
        
        assert updated_traders[1].name == 'Trader 3'  # Second highest
        assert updated_traders[1].rank == 2
        
        assert updated_traders[2].name == 'Trader 1'  # Lowest profit
        assert updated_traders[2].rank == 3

    def test_trader_performance_to_dict(self, sample_trader_performance, sample_user):
        """
        Test the to_dict method of TraderPerformance model.
        Should return properly formatted dictionary.
        """
        # Set up relationship
        sample_trader_performance.user = sample_user
        
        result = sample_trader_performance.to_dict()
        
        assert result['rank'] == 1
        assert result['name'] == 'Test User'  # From user relationship
        assert result['avatar'] == 'https://example.com/avatar.jpg'
        assert result['model'] == 'Test Model'
        assert result['accuracy'] == '85%'
        assert result['profit'] == '+$1,500'
        assert result['winRate'] == '75%'
        assert result['isCurrentUser'] is False

    def test_trader_performance_to_dict_no_user(self, sample_trader_performance):
        """
        Test to_dict method when user relationship is None.
        Should use trader's own name and create avatar from initials.
        """
        # No user relationship
        sample_trader_performance.user = None
        
        result = sample_trader_performance.to_dict()
        
        assert result['name'] == 'Test Trader'  # Trader's own name
        assert result['avatar'] == 'TE'  # First two letters

    def test_leaderboard_error_handling(self, client, auth_headers):
        """
        Test leaderboard error handling when database operation fails.
        Should return 500 error with error message.
        """
        with patch('apis.leaderboard.get_leaderboard_data') as mock_get_data:
            mock_get_data.side_effect = Exception('Database error')
            
            response = client.get('/api/leaderboard', headers=auth_headers)

            assert response.status_code == 500
            data = json.loads(response.data)
            assert 'error' in data
            assert data['error'] == 'Failed to fetch leaderboard data'
            assert 'details' in data

    def test_get_leaderboard_data_function_with_user(self, mock_db_session, sample_trader_performance, sample_user):
        """
        Test get_leaderboard_data function with specific user ID.
        Should return leaderboard and current user data.
        """
        from apis.leaderboard import get_leaderboard_data
        
        # Add sample data
        mock_db_session.add(sample_user)
        mock_db_session.add(sample_trader_performance)
        mock_db_session.commit()

        with patch('apis.leaderboard.get_session') as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_db_session
            mock_get_session.return_value.__exit__.return_value = None

            result = get_leaderboard_data('test_user_123')

            assert 'leaderboard' in result
            assert 'currentUser' in result
            assert len(result['leaderboard']) == 1
            assert result['currentUser']['isCurrentUser'] is True

    def test_get_leaderboard_data_function_no_user(self, mock_db_session):
        """
        Test get_leaderboard_data function without user ID.
        Should return leaderboard without current user data.
        """
        from apis.leaderboard import get_leaderboard_data

        with patch('apis.leaderboard.get_session') as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_db_session
            mock_get_session.return_value.__exit__.return_value = None

            result = get_leaderboard_data()

            assert 'leaderboard' in result
            assert 'currentUser' in result
            assert result['currentUser'] is None 