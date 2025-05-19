from flask import Blueprint, request, jsonify
from google.oauth2 import id_token
from google.auth.transport import requests
from flask_jwt_extended import create_access_token
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

        # Create a JWT token
        access_token = create_access_token(identity={
            'user_id': user_id,
            'email': email,
            'name': name,
            'picture': picture
        })

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