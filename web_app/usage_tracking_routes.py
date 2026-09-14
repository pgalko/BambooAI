from flask import Blueprint, request, jsonify
from auth import requires_auth, get_current_user_id
from auth.supabase_client import get_user_usage_dashboard

usage_tracking_bp = Blueprint('usage_tracking', __name__)

@usage_tracking_bp.route('/usage_tracking', methods=['GET'])
@requires_auth
def get_usage_dashboard():
    """Get usage dashboard data"""
    period = request.args.get('period', '30_days')
    auth0_id = get_current_user_id()
    
    if not auth0_id:
        return jsonify({"error": "Not authenticated"}), 401
    
    data = get_user_usage_dashboard(auth0_id, period)
    
    if "error" in data:
        return jsonify(data), 400
    
    return jsonify(data), 200