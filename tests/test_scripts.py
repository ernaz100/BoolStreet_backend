"""
Test suite for script management functionality.
Tests script upload, listing, activation/deactivation, and execution.
"""

import pytest
import json
import io
from unittest.mock import patch, Mock
from datetime import date


@pytest.mark.api
@pytest.mark.integration
class TestScriptsAPI:
    """Test class for scripts API endpoints."""

    def test_upload_script_success(self, client, test_app, auth_headers, mock_script_executor, mock_db_session):
        """
        Test successful script upload.
        Should save script and execute it.
        """
        # Mock the save_script function
        with patch('apis.scripts.save_script') as mock_save:
            mock_save.return_value = 1
            
            # Create a test file
            script_content = '''
def run(data):
    """Test trading strategy."""
    return {"action": "buy", "symbol": "AAPL", "quantity": 10}
            '''
            
            data = {
                'file': (io.BytesIO(script_content.encode()), 'test_strategy.py'),
                'name': 'Test Strategy',
                'model_type': 'ML Model'
            }
            
            response = client.post('/scripts/upload', 
                                 data=data,
                                 headers=auth_headers,
                                 content_type='multipart/form-data')
            
            assert response.status_code == 200
            response_data = json.loads(response.data)
            assert response_data['status'] == 'success'
            assert response_data['script_id'] == 1

    def test_upload_script_no_file(self, client, auth_headers):
        """
        Test script upload without file.
        Should return 400 Bad Request.
        """
        response = client.post('/scripts/upload', 
                             data={},
                             headers=auth_headers,
                             content_type='multipart/form-data')
        
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'error' in data
        assert data['error'] == 'No file part'

    def test_upload_script_empty_filename(self, client, auth_headers):
        """
        Test script upload with empty filename.
        Should return 400 Bad Request.
        """
        data = {
            'file': (io.BytesIO(b''), '')
        }
        
        response = client.post('/scripts/upload', 
                             data=data,
                             headers=auth_headers,
                             content_type='multipart/form-data')
        
        assert response.status_code == 400
        response_data = json.loads(response.data)
        assert 'error' in response_data
        assert response_data['error'] == 'No file selected'

    def test_upload_script_invalid_code(self, client, auth_headers):
        """
        Test script upload with invalid code (missing run function).
        Should return 400 Bad Request.
        """
        script_content = '''
def invalid_function():
    pass
        '''
        
        data = {
            'file': (io.BytesIO(script_content.encode()), 'invalid_script.py'),
            'name': 'Invalid Script'
        }
        
        response = client.post('/scripts/upload', 
                             data=data,
                             headers=auth_headers,
                             content_type='multipart/form-data')
        
        assert response.status_code == 400
        response_data = json.loads(response.data)
        assert 'error' in response_data
        assert 'run(data)' in response_data['error']

    def test_upload_script_execution_error(self, client, auth_headers):
        """
        Test script upload when execution fails.
        Should save script but return execution error.
        """
        with patch('apis.scripts.save_script') as mock_save:
            mock_save.return_value = 1
            
            with patch('apis.scripts.run_user_script') as mock_run:
                mock_run.side_effect = Exception('Execution failed')
                
                script_content = '''
def run(data):
    raise Exception("Test error")
                '''
                
                data = {
                    'file': (io.BytesIO(script_content.encode()), 'error_script.py'),
                    'name': 'Error Script'
                }
                
                response = client.post('/scripts/upload', 
                                     data=data,
                                     headers=auth_headers,
                                     content_type='multipart/form-data')
                
                assert response.status_code == 200
                response_data = json.loads(response.data)
                assert response_data['status'] == 'success'
                assert response_data['script_id'] == 1

    def test_get_user_scripts_success(self, client, auth_headers, mock_db_session, sample_user_script):
        """
        Test getting list of user scripts.
        Should return list of scripts for authenticated user.
        """
        # Add sample script to test database
        mock_db_session.add(sample_user_script)
        mock_db_session.commit()

        with patch('apis.scripts.get_session') as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_db_session
            mock_get_session.return_value.__exit__.return_value = None

            response = client.get('/scripts/list', headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'scripts' in data
            assert len(data['scripts']) == 1
            assert data['scripts'][0]['name'] == 'Test Strategy'
            assert data['scripts'][0]['active'] is True
            assert data['scripts'][0]['balance'] == 1000.0

    def test_get_user_scripts_empty(self, client, auth_headers, mock_db_session):
        """
        Test getting list of user scripts when user has no scripts.
        Should return empty list.
        """
        with patch('apis.scripts.get_session') as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_db_session
            mock_get_session.return_value.__exit__.return_value = None

            response = client.get('/scripts/list', headers=auth_headers)

            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'scripts' in data
            assert len(data['scripts']) == 0

    def test_get_user_scripts_no_auth(self, client):
        """
        Test getting list of user scripts without authentication.
        Should return 401 Unauthorized.
        """
        response = client.get('/scripts/list')
        assert response.status_code == 401

    def test_activate_script_success(self, client, auth_headers, mock_db_session, sample_user_script):
        """
        Test activating/deactivating a script.
        Should update script status and return updated list.
        """
        # Add sample script to test database
        mock_db_session.add(sample_user_script)
        mock_db_session.commit()

        with patch('apis.scripts.get_session') as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_db_session
            mock_get_session.return_value.__exit__.return_value = None

            # Test deactivating script
            response = client.post('/scripts/1/activate', 
                                 json={'active': False},
                                 headers=auth_headers,
                                 content_type='application/json')

            assert response.status_code == 200
            data = json.loads(response.data)
            assert 'scripts' in data
            assert len(data['scripts']) == 1
            assert data['scripts'][0]['active'] is False

    def test_activate_script_not_found(self, client, auth_headers, mock_db_session):
        """
        Test activating a script that doesn't exist.
        Should return 404 Not Found.
        """
        with patch('apis.scripts.get_session') as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_db_session
            mock_get_session.return_value.__exit__.return_value = None

            response = client.post('/scripts/999/activate', 
                                 json={'active': True},
                                 headers=auth_headers,
                                 content_type='application/json')

            assert response.status_code == 404
            data = json.loads(response.data)
            assert 'error' in data
            assert data['error'] == 'Script not found'

    def test_activate_script_missing_active_field(self, client, auth_headers, mock_db_session, sample_user_script):
        """
        Test activating a script without providing 'active' field.
        Should return 400 Bad Request.
        """
        # Add sample script to test database
        mock_db_session.add(sample_user_script)
        mock_db_session.commit()

        with patch('apis.scripts.get_session') as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_db_session
            mock_get_session.return_value.__exit__.return_value = None

            response = client.post('/scripts/1/activate', 
                                 json={},
                                 headers=auth_headers,
                                 content_type='application/json')

            assert response.status_code == 400
            data = json.loads(response.data)
            assert 'error' in data
            assert 'active' in data['error']

    def test_activate_script_no_auth(self, client):
        """
        Test activating a script without authentication.
        Should return 401 Unauthorized.
        """
        response = client.post('/scripts/1/activate', 
                             json={'active': True},
                             content_type='application/json')
        
        assert response.status_code == 401

    def test_activate_script_wrong_user(self, client, auth_headers, mock_db_session):
        """
        Test activating a script belonging to another user.
        Should return 404 Not Found (security measure).
        """
        # Create script for different user
        different_user_script = sample_user_script
        different_user_script.user_id = 'different_user_456'
        
        mock_db_session.add(different_user_script)
        mock_db_session.commit()

        with patch('apis.scripts.get_session') as mock_get_session:
            mock_get_session.return_value.__enter__.return_value = mock_db_session
            mock_get_session.return_value.__exit__.return_value = None

            response = client.post('/scripts/1/activate', 
                                 json={'active': True},
                                 headers=auth_headers,
                                 content_type='application/json')

            assert response.status_code == 404
            data = json.loads(response.data)
            assert 'error' in data
            assert data['error'] == 'Script not found' 