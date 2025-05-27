from flask import Blueprint, jsonify, request
from typing import List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import desc
from db.database import get_session
from db.db_models import TraderPerformance, User
from flask_jwt_extended import jwt_required, get_jwt_identity

# Create blueprint for leaderboard routes
leaderboard_bp = Blueprint('leaderboard', __name__)

def update_ranks(session) -> None:
    """
    Update the ranks of all traders based on their total profit.
    This should be called whenever trader performance data changes.
    """
    # Get all traders ordered by profit
    traders = session.query(TraderPerformance).order_by(desc(TraderPerformance.total_profit)).all()
    
    # Update ranks
    for i, trader in enumerate(traders, 1):
        trader.rank = i
    session.commit()

def get_leaderboard_data(current_user_id: str = None) -> Dict[str, Any]:
    """
    Get leaderboard data from the database.
    Returns a list of top performers with their rankings and statistics,
    and the current user's data if provided.
    """
    session = get_session()
    try:
        # Get all traders ordered by rank
        traders = session.query(TraderPerformance).order_by(TraderPerformance.rank).all()
        
        # If no data exists, create some initial data
        if not traders:
            # Create some initial data
            initial_traders = [
                TraderPerformance(
                    user_id="user1",
                    name="John Doe",
                    model_name="Quantum Predictor",
                    accuracy=92.0,
                    total_profit=45678.0,
                    win_rate=85.0,
                    rank=1
                ),
                TraderPerformance(
                    user_id="user2",
                    name="Jane Smith",
                    model_name="Neural Net Alpha",
                    accuracy=89.0,
                    total_profit=38942.0,
                    win_rate=82.0,
                    rank=2
                ),
                TraderPerformance(
                    user_id="user3",
                    name="Mike Johnson",
                    model_name="AI Trader Pro",
                    accuracy=87.0,
                    total_profit=32156.0,
                    win_rate=79.0,
                    rank=3
                ),
                TraderPerformance(
                    user_id="user4",
                    name="Sarah Wilson",
                    model_name="Market Master",
                    accuracy=85.0,
                    total_profit=28934.0,
                    win_rate=77.0,
                    rank=4
                ),
                TraderPerformance(
                    user_id="user5",
                    name="David Brown",
                    model_name="Smart Predictor",
                    accuracy=83.0,
                    total_profit=25678.0,
                    win_rate=75.0,
                    rank=5
                )
            ]
            
            for trader in initial_traders:
                session.add(trader)
            session.commit()
            
            # Get the newly created data
            traders = session.query(TraderPerformance).order_by(TraderPerformance.rank).all()

        # Get current user's data if user_id is provided
        current_user_data = None
        if current_user_id:
            # First try to get the user's performance data
            current_user = session.query(TraderPerformance).filter_by(user_id=current_user_id).first()
            
            if current_user:
                current_user_data = current_user.to_dict()
                current_user_data["isCurrentUser"] = True
            else:
                # If no performance data exists, get user info and create placeholder
                user = session.query(User).filter_by(id=current_user_id).first()
                if user:
                    current_user_data = {
                        "rank": None,
                        "name": user.name,
                        "avatar": user.picture,
                        "model": "Not Ranked",
                        "accuracy": "N/A",
                        "profit": "N/A",
                        "winRate": "N/A",
                        "isCurrentUser": True
                    }
                else:
                    # Fallback if user doesn't exist
                    current_user_data = {
                        "rank": None,
                        "name": "You",
                        "avatar": None,
                        "model": "Not Ranked",
                        "accuracy": "N/A",
                        "profit": "N/A",
                        "winRate": "N/A",
                        "isCurrentUser": True
                    }
        
        # Convert to dictionary format expected by frontend
        return {
            "leaderboard": [trader.to_dict() for trader in traders],
            "currentUser": current_user_data
        }
    finally:
        session.close()

@leaderboard_bp.route('/api/leaderboard', methods=['GET'])
@jwt_required()
def get_leaderboard():
    """
    Get the current leaderboard data.
    Returns a list of top performers with their rankings and statistics,
    and the current user's data.
    """
    try:
        current_user_id = get_jwt_identity()
        leaderboard_data = get_leaderboard_data(current_user_id)
        return jsonify(leaderboard_data)
    except Exception as e:
        return jsonify({
            "error": "Failed to fetch leaderboard data",
            "details": str(e)
        }), 500 