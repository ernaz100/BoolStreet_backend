from flask import Blueprint, request, jsonify
from google.oauth2 import id_token
from google.auth.transport import requests
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
import os
from dotenv import load_dotenv
from db.database import get_session
from db.db_models import User
from datetime import datetime

# Load environment variables
load_dotenv()

# Create blueprint
auth_bp = Blueprint('auth', __name__)

# Google OAuth configuration
GOOGLE_CLIENT_ID = os.getenv('GOOGLE_CLIENT_ID')

def get_or_create_user(session, user_id: str, email: str, name: str, picture: str) -> dict:
    """
    Get an existing user or create a new one if they don't exist.
    Updates user information if they already exist.
    Returns a dictionary with user data.
    """
    user = session.query(User).filter_by(id=user_id).first()
    
    if user:
        # Update existing user's information
        user.email = email
        user.name = name
        user.picture = picture
        user.last_login = datetime.now()
    else:
        # Create new user
        user = User(
            id=user_id,
            email=email,
            name=name,
            picture=picture,
            created_at=datetime.now(),
            last_login=datetime.now(),
            balance=100000.0  # Set default balance for new users
        )
        session.add(user)
    
    session.commit()
    
    # Return user data as dictionary before session closes
    return {
        'id': user.id,
        'email': user.email,
        'name': user.name,
        'picture': user.picture
    }

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

        # Create or update user in database
        session = get_session()
        try:
            user_data = get_or_create_user(session, user_id, email, name, picture)
        finally:
            session.close()

        # Create a JWT token with user_id as the identity
        access_token = create_access_token(identity=str(user_id))

        return jsonify({
            'access_token': access_token,
            'user': user_data
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
    Get the current user's information from the database
    Protected route that requires a valid JWT token
    Returns the user's information if the token is valid
    """
    try:
        # Get the user ID from the JWT token
        user_id = get_jwt_identity()
        
        # Fetch user data from database
        session = get_session()
        try:
            user = session.query(User).filter_by(id=user_id).first()
            if not user:
                return jsonify({'error': 'User not found'}), 404

            # Create user data dictionary before session closes
            user_data = {
                'id': user.id,
                'email': user.email,
                'name': user.name,
                'picture': user.picture,
                'created_at': user.created_at.isoformat(),
                'last_login': user.last_login.isoformat(),
                'balance': user.balance
            }
            return jsonify(user_data), 200
        finally:
            session.close()
        
    except Exception as e:
        return jsonify({'error': str(e)}), 401
