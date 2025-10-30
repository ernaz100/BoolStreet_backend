from flask import Blueprint
from flask_jwt_extended import jwt_required, get_jwt_identity

# Create blueprint for leaderboard routes
leaderboard_bp = Blueprint('leaderboard', __name__)

