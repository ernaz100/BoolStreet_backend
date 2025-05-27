"""
Test suite for authentication functionality.
Tests Google OAuth integration, JWT token handling, and user management.
"""

import pytest
import json
from unittest.mock import patch, Mock
from flask_jwt_extended import create_access_token


@pytest.mark.auth
@pytest.mark.api
class TestAuthAPI:
    """Test class for authentication API endpoints."""

    def test_google_auth_success(self, client, test_app, mock_google_auth, mock_db_session, sample_user):
        """
        Test successful Google OAuth authentication.
        Should create/update user and return JWT token.
        """
        # Add sample user to test database
        mock_db_session.add(sample_user)
        mock_db_session.commit()

        # Mock the database session
        with patch('apis.auth.get_session') as mock_get_session:
            mock_get_session.return_value = mock_db_session

            # Make request to Google auth endpoint
            response = client.post('/auth/google', 
                                 json={'token': 'valid_google_token'},
                                 content_type='application/json')

            # Verify response
            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'access_token' in data
            assert 'user' in data
            assert data['user']['email'] == 'test@example.com'
            assert data['user']['name'] == 'Test User'

    def test_google_auth_no_token(self, client):
        """
        Test Google auth without providing token.
        Should return 400 Bad Request.
        """
        response = client.post('/auth/google', 
                             json={},
                             content_type='application/json')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert data['error'] == 'No token provided'

    def test_google_auth_invalid_token(self, client):
        """
        Test Google auth with invalid token.
        Should return 401 Unauthorized.
        """
        with patch('google.oauth2.id_token.verify_oauth2_token') as mock_verify:
            mock_verify.side_effect = ValueError('Invalid token')
            
            response = client.post('/auth/google', 
                                 json={'token': 'invalid_token'},
                                 content_type='application/json')
            
            assert response.status_code == 401
            data = json.loads(response.data)
            assert 'error' in data
            assert data['error'] == 'Invalid token'

    def test_google_auth_new_user(self, client, test_app, mock_google_auth, mock_db_session):
        """
        Test Google auth with new user.
        Should create new user in database.
        """
        with patch('apis.auth.get_session') as mock_get_session:
            mock_get_session.return_value = mock_db_session

            response = client.post('/auth/google', 
                                 json={'token': 'valid_google_token'},
                                 content_type='application/json')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'access_token' in data
            assert 'user' in data

    def test_get_current_user_success(self, client, test_app, mock_db_session, sample_user, auth_headers):
        """
        Test getting current user information with valid token.
        Should return user data.
        """
        # Add sample user to test database
        mock_db_session.add(sample_user)
        mock_db_session.commit()

        with patch('apis.auth.get_session') as mock_get_session:
            mock_get_session.return_value = mock_db_session

            response = client.get('/auth/me', headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert data['email'] == 'test@example.com'
            assert data['name'] == 'Test User'
            assert 'created_at' in data
            assert 'last_login' in data

    def test_get_current_user_no_token(self, client):
        """
        Test getting current user without authentication token.
        Should return 401 Unauthorized.
        """
        response = client.get('/auth/me')
        
        assert response.status_code == 401

    def test_get_current_user_invalid_token(self, client):
        """
        Test getting current user with invalid token.
        Should return 401 Unauthorized.
        """
        headers = {'Authorization': 'Bearer invalid_token'}
        response = client.get('/auth/me', headers=headers)
        
        assert response.status_code == 401  # JWT decode error

    def test_get_current_user_not_found(self, client, test_app, mock_db_session, auth_headers):
        """
        Test getting current user when user doesn't exist in database.
        Should return 404 Not Found.
        """
        with patch('apis.auth.get_session') as mock_get_session:
            mock_get_session.return_value = mock_db_session

            response = client.get('/auth/me', headers=auth_headers)

            assert response.status_code == 404
            data = json.loads(response.data)
            assert 'error' in data
            assert data['error'] == 'User not found'

    def test_get_or_create_user_existing(self, mock_db_session, sample_user):
        """
        Test get_or_create_user function with existing user.
        Should update user information and return user data.
        """
        from apis.auth import get_or_create_user
        
        # Add sample user to test database
        mock_db_session.add(sample_user)
        mock_db_session.commit()

        # Call function with updated information
        user_data = get_or_create_user(
            mock_db_session, 
            'test_user_123', 
            'updated@example.com', 
            'Updated Name', 
            'https://example.com/new_avatar.jpg'
        )

        # Verify user was updated
        assert user_data['email'] == 'updated@example.com'
        assert user_data['name'] == 'Updated Name'
        assert user_data['picture'] == 'https://example.com/new_avatar.jpg'

    def test_get_or_create_user_new(self, mock_db_session):
        """
        Test get_or_create_user function with new user.
        Should create new user and return user data.
        """
        from apis.auth import get_or_create_user
        
        # Call function with new user information
        user_data = get_or_create_user(
            mock_db_session, 
            'new_user_456', 
            'new@example.com', 
            'New User', 
            'https://example.com/avatar.jpg'
        )

        # Verify new user was created
        assert user_data['id'] == 'new_user_456'
        assert user_data['email'] == 'new@example.com'
        assert user_data['name'] == 'New User'
        assert user_data['picture'] == 'https://example.com/avatar.jpg' 