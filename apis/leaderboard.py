from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from sqlalchemy import func, desc
from db.db_models import UserModel, Trade, User
from db.database import get_session
from typing import Dict, Any, List, Optional
import logging

logger = logging.getLogger(__name__)

# Create blueprint for leaderboard routes
leaderboard_bp = Blueprint('leaderboard', __name__)


def calculate_trader_performance(trader: UserModel, trades: List[Trade]) -> Dict[str, Any]:
    """
    Calculate performance metrics for a trader based on their trades.
    
    Returns:
        Dict with profit_pct, net_gain, total_volume, total_trades, profitable_trades
    """
    total_trades = len(trades)
    
    if total_trades == 0:
        return {
            "profit_pct": 0.0,
            "net_gain": 0.0,
            "total_volume": 0.0,
            "total_trades": 0,
            "profitable_trades": 0,
            "total_closed_positions": 0
        }
    
    # Calculate net gain (actual dollar P&L)
    net_gain = trader.balance - trader.start_balance
    
    # Calculate profit percentage
    profit_pct = 0.0
    if trader.start_balance > 0:
        profit_pct = (net_gain / trader.start_balance) * 100
    
    # Calculate total volume (sum of all trade values)
    successful_trades = [t for t in trades if t.success]
    total_volume = sum(t.quantity * t.price for t in successful_trades)
    
    # For tracking profitable closed positions
    profitable_trades = 0
    total_closed_positions = 0
    
    # Track positions: {coin: [(quantity, entry_price)]}
    positions: Dict[str, List[tuple]] = {}
    
    for trade in sorted(successful_trades, key=lambda t: t.executed_at if t.executed_at else t.id):
        coin = trade.coin
        
        if trade.side == "buy":
            # Opening or adding to position
            if coin not in positions:
                positions[coin] = []
            positions[coin].append((trade.quantity, trade.price))
        
        elif trade.side == "sell":
            # Closing position - calculate P&L
            if coin in positions and positions[coin]:
                # FIFO: close oldest positions first
                remaining_qty = trade.quantity
                sell_value = trade.quantity * trade.price
                cost_basis = 0.0
                
                while remaining_qty > 0 and positions[coin]:
                    entry_qty, entry_price = positions[coin][0]
                    
                    if entry_qty <= remaining_qty:
                        # Close entire position
                        cost_basis += entry_qty * entry_price
                        remaining_qty -= entry_qty
                        positions[coin].pop(0)
                    else:
                        # Partial close
                        cost_basis += remaining_qty * entry_price
                        positions[coin][0] = (entry_qty - remaining_qty, entry_price)
                        remaining_qty = 0
                
                # Calculate P&L for this sale
                actual_sold_qty = trade.quantity - remaining_qty
                if actual_sold_qty > 0:
                    actual_sell_value = (actual_sold_qty / trade.quantity) * sell_value
                    pnl = actual_sell_value - cost_basis
                    total_closed_positions += 1
                    if pnl > 0:
                        profitable_trades += 1
    
    return {
        "profit_pct": round(profit_pct, 2),
        "net_gain": round(net_gain, 2),
        "total_volume": round(total_volume, 2),
        "total_trades": total_trades,
        "profitable_trades": profitable_trades,
        "total_closed_positions": total_closed_positions
    }


def get_avatar_initials(name: str) -> str:
    """Get initials from a name for avatar display."""
    if not name:
        return "?"
    
    parts = name.strip().split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[-1][0]).upper()
    elif len(parts) == 1 and len(parts[0]) >= 2:
        return parts[0][:2].upper()
    elif len(parts) == 1:
        return parts[0][0].upper()
    return "?"


@leaderboard_bp.route('/api/leaderboard', methods=['GET'])
@jwt_required()
def get_leaderboard():
    """
    Get the global leaderboard of all traders ranked by performance.
    
    Returns:
        JSON response containing:
        - leaderboard: List of top traders with their performance metrics
        - currentUser: The current user's best performing trader (if any)
    """
    current_user_id = get_jwt_identity()
    if not isinstance(current_user_id, str):
        return jsonify({"error": "Invalid token format"}), 401
    
    try:
        with get_session() as session:
            # Fetch all traders with at least some trading activity
            all_traders = session.query(UserModel).all()
            
            if not all_traders:
                return jsonify({
                    "leaderboard": [],
                    "currentUser": None
                }), 200
            
            # Calculate performance for each trader
            leaderboard_entries = []
            
            for trader in all_traders:
                # Get trades for this trader
                trades = session.query(Trade).filter(
                    Trade.trader_id == trader.id
                ).order_by(Trade.executed_at).all()
                
                # Calculate performance metrics
                performance = calculate_trader_performance(trader, trades)
                
                # Get user info for the trader's owner
                user = session.query(User).filter(User.id == trader.user_id).first()
                
                # Determine avatar (user picture or initials)
                avatar = None
                owner_name = "Unknown"
                if user:
                    if user.picture:
                        avatar = user.picture
                    else:
                        avatar = get_avatar_initials(user.name)
                    owner_name = user.name
                else:
                    avatar = get_avatar_initials(trader.name)
                
                # Parse tickers/coins being traded
                tickers_str = trader.tickers if trader.tickers else "[]"
                tickers_list = []
                try:
                    import json
                    tickers_list = json.loads(tickers_str) if tickers_str else []
                except:
                    tickers_list = [tickers_str] if tickers_str else []
                
                # Extract LLM model and other config from the trader code
                llm_model = None
                trading_frequency = None
                prompt = None
                
                if trader.code:
                    try:
                        import json
                        code_config = json.loads(trader.code)
                        llm_model = code_config.get('llm_model')
                        trading_frequency = code_config.get('trading_frequency')
                        prompt = code_config.get('prompt')
                    except:
                        pass
                
                # Format net gain
                net_gain = performance['net_gain']
                net_gain_formatted = f"${'+' if net_gain >= 0 else ''}{net_gain:,.2f}"
                
                # Format volume
                volume = performance['total_volume']
                volume_formatted = f"${volume:,.2f}"
                
                entry = {
                    "trader_id": trader.id,
                    "name": trader.name,
                    "owner_name": owner_name,
                    "avatar": avatar,
                    "coins": tickers_list,
                    "profit": f"{'+' if performance['profit_pct'] >= 0 else ''}{performance['profit_pct']:.2f}%",
                    "profit_value": performance['profit_pct'],
                    "netGain": net_gain_formatted,
                    "net_gain_value": net_gain,
                    "volume": volume_formatted,
                    "volume_value": volume,
                    "total_trades": performance['total_trades'],
                    "isCurrentUser": trader.user_id == current_user_id,
                    "active": trader.active,
                    "balance": trader.balance,
                    "start_balance": trader.start_balance,
                    "created_at": trader.created_at.isoformat() if trader.created_at else None,
                    "llm_model": llm_model,
                    "trading_frequency": trading_frequency,
                    "prompt": prompt
                }
                
                leaderboard_entries.append(entry)
            
            # Sort by profit percentage (descending), then by netGain
            leaderboard_entries.sort(
                key=lambda x: (x['profit_value'], x['netGain']),
                reverse=True
            )
            
            # Assign ranks
            for i, entry in enumerate(leaderboard_entries):
                entry['rank'] = i + 1
            
            # Find current user's best trader
            current_user_traders = [e for e in leaderboard_entries if e['isCurrentUser']]
            current_user_best = None
            if current_user_traders:
                current_user_best = current_user_traders[0]  # Best ranked
            
            # Format for frontend (remove internal fields)
            formatted_leaderboard = []
            for entry in leaderboard_entries:
                formatted_leaderboard.append({
                    "rank": entry['rank'],
                    "name": entry['name'],
                    "avatar": entry['avatar'],
                    "coins": entry['coins'],
                    "profit": entry['profit'],
                    "netGain": entry['netGain'],
                    "volume": entry['volume'],
                    "isCurrentUser": entry['isCurrentUser'],
                    "totalTrades": entry['total_trades'],
                    "active": entry['active'],
                    "balance": entry['balance'],
                    "start_balance": entry['start_balance'],
                    "created_at": entry['created_at'],
                    "llm_model": entry['llm_model'],
                    "trading_frequency": entry['trading_frequency'],
                    "prompt": entry['prompt'],
                    "trader_id": entry['trader_id']
                })
            
            formatted_current_user = None
            if current_user_best:
                formatted_current_user = {
                    "rank": current_user_best['rank'],
                    "name": current_user_best['name'],
                    "avatar": current_user_best['avatar'],
                    "coins": current_user_best['coins'],
                    "profit": current_user_best['profit'],
                    "netGain": current_user_best['netGain'],
                    "volume": current_user_best['volume'],
                    "isCurrentUser": True,
                    "totalTrades": current_user_best['total_trades'],
                    "active": current_user_best['active'],
                    "balance": current_user_best['balance'],
                    "start_balance": current_user_best['start_balance'],
                    "created_at": current_user_best['created_at'],
                    "llm_model": current_user_best['llm_model'],
                    "trading_frequency": current_user_best['trading_frequency'],
                    "prompt": current_user_best['prompt'],
                    "trader_id": current_user_best['trader_id']
                }
            
            return jsonify({
                "leaderboard": formatted_leaderboard,
                "currentUser": formatted_current_user
            }), 200
            
    except Exception as e:
        logger.error(f"Error fetching leaderboard: {e}")
        return jsonify({"error": str(e)}), 500


@leaderboard_bp.route('/api/leaderboard/stats', methods=['GET'])
@jwt_required()
def get_leaderboard_stats():
    """
    Get aggregate statistics for the leaderboard.
    
    Returns:
        JSON response containing:
        - total_traders: Total number of traders
        - active_traders: Number of active traders
        - total_trades: Total trades executed across all traders
        - avg_profit: Average profit percentage
    """
    current_user_id = get_jwt_identity()
    if not isinstance(current_user_id, str):
        return jsonify({"error": "Invalid token format"}), 401
    
    try:
        with get_session() as session:
            # Get trader stats
            total_traders = session.query(UserModel).count()
            active_traders = session.query(UserModel).filter(UserModel.active == True).count()
            
            # Get trade stats
            total_trades = session.query(Trade).count()
            
            # Calculate average profit
            traders = session.query(UserModel).filter(UserModel.start_balance > 0).all()
            if traders:
                profits = [((t.balance - t.start_balance) / t.start_balance) * 100 for t in traders]
                avg_profit = sum(profits) / len(profits)
            else:
                avg_profit = 0.0
            
            return jsonify({
                "total_traders": total_traders,
                "active_traders": active_traders,
                "total_trades": total_trades,
                "avg_profit": round(avg_profit, 2)
            }), 200
            
    except Exception as e:
        logger.error(f"Error fetching leaderboard stats: {e}")
        return jsonify({"error": str(e)}), 500
