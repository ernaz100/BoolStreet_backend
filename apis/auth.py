from flask import Blueprint, request, jsonify
from google.oauth2 import id_token
from google.auth.transport import requests
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Create blueprint
auth_bp = Blueprint('auth', __name__)

# Google OAuth configuration
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')

@auth_bp.route('/auth/google', methods=['POST'])
def google_auth():
    """
    Handle Google OAuth authentication
    Expects a POST request with the Google ID token
    Returns a JWT token if authentication is successful
    """
    try:
        # Get the token from the request
        token = request.json.get('token')
        if not token:
            return jsonify({'error': 'No token provided'}), 400

        # Verify the token
        idinfo = id_token.verify_oauth2_token(
            token, requests.Request(), GOOGLE_CLIENT_ID)

        # Get user info from the token
        user_id = idinfo['sub']
        email = idinfo['email']
        name = idinfo.get('name', '')
        picture = idinfo.get('picture', '')

        # Create a JWT token with user_id as the identity
        access_token = create_access_token(identity=str(user_id))

        return jsonify({
            'access_token': access_token,
            'user': {
                'email': email,
                'name': name,
                'picture': picture
            }
        }), 200

    except ValueError as e:
        # Invalid token
        return jsonify({'error': 'Invalid token'}), 401
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@auth_bp.route('/auth/me', methods=['GET'])
@jwt_required()
def get_current_user():
    """
    Get the current user's information from the JWT token
    Protected route that requires a valid JWT token
    Returns the user's information if the token is valid
    """
    try:
        # Get the user ID from the JWT token
        user_id = get_jwt_identity()
        
        # TODO: Fetch user data from database using user_id
        # For now, return a placeholder response
        return jsonify({
            'user_id': user_id,
            'email': 'user@example.com',  # This should come from your database
            'name': 'User',  # This should come from your database
            'picture': ''  # This should come from your database
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 401 