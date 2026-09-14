# Updated integrations/sweatstack.py - using supabase_client functions

import os
import requests
import uuid
import json
import pandas as pd
import sweatstack as ss
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, session, redirect, url_for
from auth import requires_auth, get_current_user_id

# Import SweatStack functions from supabase_client
from auth.supabase_client import (
    store_sweatstack_token,
    get_sweatstack_token, 
    remove_sweatstack_token,
    get_sweatstack_integration_status,
    is_sweatstack_token_expired,
    get_user_subscription
)

# Create the blueprint
sweatstack_bp = Blueprint('sweatstack', __name__, url_prefix='/sweatstack')

# SweatStack OAuth configuration
SWEATSTACK_CLIENT_ID = os.getenv('SWEATSTACK_CLIENT_ID')
SWEATSTACK_CLIENT_SECRET = os.getenv('SWEATSTACK_CLIENT_SECRET')
AUTH_MODE = os.getenv('AUTH_MODE', 'none')

def get_sweatstack_context():
    """Get SweatStack context - check both enabled and authenticated"""
    is_authenticated = False
    
    # Check session first
    if session.get('sweatstack_access_token') or session.get('sweatstack_token_data'):
        is_authenticated = True
    # Check database if authenticated
    elif AUTH_MODE == 'auth0':
        try:
            auth0_id = get_current_user_id()
            if auth0_id:
                bamboo_user_id = auth0_id.split('|')[1] if '|' in auth0_id else auth0_id
                status = get_sweatstack_integration_status(bamboo_user_id, auth0_id)
                is_authenticated = status.get('authenticated', False)
        except:
            pass
    
    return {
        'sweatstack_enabled': bool(SWEATSTACK_CLIENT_ID and SWEATSTACK_CLIENT_SECRET),
        'sweatstack_authenticated': is_authenticated,
        'sweatstack_metrics': [m for m in ss.Metric if m not in [ss.Metric.duration, ss.Metric.lactate, ss.Metric.rpe, ss.Metric.notes]],
        'sweatstack_default_metrics': [ss.Metric.power, ss.Metric.speed, ss.Metric.heart_rate]
    }

@sweatstack_bp.route('/get_data_limits', methods=['GET'])
@requires_auth
def get_data_limits():
    """Get data access limits based on subscription AND integration config"""
    try:
        auth0_id = get_current_user_id()
        if not auth0_id:
            return jsonify({'max_days': 14}), 200
        
        # Get user's subscription with integration config
        result = get_user_subscription(auth0_id)
        
        if not result.get('ok'):
            return jsonify({'max_days': 14}), 200
        
        subscription = result.get('data', {})
        compute_tier = subscription.get('compute_tier', 'free')
        integration_config = subscription.get('integration_config', {})
        
        # For SweatStack: Check if user is paying for extended access
        sweatstack_extended = integration_config.get('sweatstack_extended', False)
        
        if not sweatstack_extended:
            # Not paying $1 = limited to 14 days regardless of tier
            max_days = 14
            message = "Limited to 14 days. Enable SweatStack Extended for more history ($1/month)."
        else:
            # Paying $1 = access based on compute tier
            max_days_map = {
                'free': 14,    # Shouldn't happen (free can't have extended)
                'plus': 182,   # 6 months
                'pro': 365     # 1 year
            }
            max_days = max_days_map.get(compute_tier, 14)
            message = f"SweatStack Extended enabled. Access up to {max_days} days with {compute_tier} tier."
        
        return jsonify({
            'max_days': max_days,
            'compute_tier': compute_tier,
            'sweatstack_extended': sweatstack_extended,
            'message': message
        }), 200
        
    except Exception as e:
        sweatstack_bp.logger.error(f'Error getting data limits: {str(e)}')
        return jsonify({'max_days': 14}), 200

def get_or_migrate_sweatstack_token():
    """
    Get SweatStack token, migrating from session to DB if needed.
    Returns: access_token or None
    """
    user_id = sweatstack_bp.get_user_id()
    auth0_id = get_current_user_id()
    
    # Check if token exists in session (temporary storage)
    session_token_data = session.get('sweatstack_token_data')
    session_access_token = session.get('sweatstack_access_token')
    
    # Handle both old format (just access_token) and new format (full token data)
    if session_token_data:
        # New format: full token data stored in session
        sweatstack_bp.logger.info(f'Migrating complete SweatStack token from session to DB for user: {user_id}')
        
        try:
            success = store_sweatstack_token(user_id, auth0_id, session_token_data)
            if success:
                # Clear from session after successful storage
                session.pop('sweatstack_token_data', None)
                session.pop('sweatstack_access_token', None)  # Clean up old format too
                return session_token_data['access_token']
            else:
                # Return session token anyway, will retry migration next time
                return session_token_data['access_token']
        except Exception as e:
            sweatstack_bp.logger.error(f'Failed to migrate token to DB for user {user_id}: {str(e)}')
            return session_token_data['access_token']
    
    elif session_access_token:
        # Old format: just access_token in session
        sweatstack_bp.logger.info(f'Found legacy SweatStack token in session for user: {user_id}')
        # Clear it and force re-authentication to get full token data
        session.pop('sweatstack_access_token', None)
        return None
    
    # No session token, try to get from database
    try:
        return get_sweatstack_token(user_id, auth0_id)
    except Exception as e:
        sweatstack_bp.logger.error(f'Failed to retrieve token from DB for user {user_id}: {str(e)}')
        return None

def transform_sweatstack_longitudinal_data(df):
    """Transform SweatStack longitudinal data to the required format"""
    # 1. Convert timestamp column to local time and rename to "datetime"
    df["datetime"] = pd.to_datetime(df.index).tz_localize(None)  # Remove timezone info to convert to local time
    df = df.reset_index(drop=True)  # Remove the original timestamp index

    # 2. Convert activity_id column to integers (incrementing from oldest to newest activity per athlete)
    df = df.sort_values('datetime')

    # Check if we have athlete_id column (multi-user scenario)
    if 'athlete_id' in df.columns:
        # Create unique activity IDs per athlete
        unique_activities = df.groupby(['athlete_id', 'activity_id'])['datetime'].min().sort_values()
        activity_mapping = {}

        for athlete_id in df['athlete_id'].unique():
            athlete_activities = unique_activities[athlete_id]
            for new_id, (old_id, _) in enumerate(athlete_activities.items(), 1):
                activity_mapping[(athlete_id, old_id)] = new_id

        # Apply mapping using both athlete_id and activity_id
        df['activity_id'] = df.apply(lambda row: activity_mapping.get((row['athlete_id'], row['activity_id']), row['activity_id']), axis=1)

        # Convert athlete_id to integers (incrementing from first appearance)
        unique_athletes = sorted(df['athlete_id'].unique())
        athlete_mapping = {old_id: new_id for new_id, old_id in enumerate(unique_athletes, 1)}
        df['athlete_id'] = df['athlete_id'].map(athlete_mapping)
    else:
        # Single user scenario
        unique_activities = df.groupby('activity_id')['datetime'].min().sort_values()
        activity_mapping = {old_id: new_id for new_id, old_id in enumerate(unique_activities.index, 1)}
        df['activity_id'] = df['activity_id'].map(activity_mapping)

    # 3. Add cumulative distance column calculated from duration × speed
    if 'duration' in df.columns and 'speed' in df.columns:
        df['distance_increment'] = df['duration'].dt.total_seconds() * df['speed']

        # Calculate cumulative distance per activity (and per athlete if multi-user)
        if 'athlete_id' in df.columns:
            df['distance'] = df.groupby(['athlete_id', 'activity_id'])['distance_increment'].cumsum()
        else:
            df['distance'] = df.groupby('activity_id')['distance_increment'].cumsum()

        df = df.drop('distance_increment', axis=1)

    # 4. Remove duration column
    df = df.drop('duration', axis=1)

    # 5. Convert semicircles to degrees for GPS coordinates
    for col in ['longitude', 'latitude']:
        if col in df.columns:
            df[col] = df[col].where(df[col].isna(), df[col] * (180 / 2**31))

    # 6. Sort columns by athlete_id, datetime, activity_id, sport, then other columns
    priority_columns = ['athlete_id', 'datetime', 'activity_id', 'sport']
    existing_priority_columns = [col for col in priority_columns if col in df.columns]
    other_columns = [col for col in df.columns if col not in priority_columns]
    df = df[existing_priority_columns + sorted(other_columns)]
    
    return df

def init_sweatstack_integration(app, **dependencies):
    """Initialize SweatStack integration with the main app and dependencies"""
    # Store dependencies for use in routes
    sweatstack_bp.user_preferences = dependencies['user_preferences']
    sweatstack_bp.bamboo_ai_instances = dependencies['bamboo_ai_instances']
    sweatstack_bp.get_user_id = dependencies['get_user_id']
    sweatstack_bp.get_bamboo_ai = dependencies['get_bamboo_ai']
    sweatstack_bp.get_dynamic_executor_urls = dependencies['get_dynamic_executor_urls']
    sweatstack_bp.global_execution_mode = dependencies['global_execution_mode']
    sweatstack_bp.logger = dependencies['logger']
    
    # Additional constants from main app
    sweatstack_bp.EXPLORATORY = dependencies['EXPLORATORY']
    sweatstack_bp.SEARCH_TOOL = dependencies['SEARCH_TOOL']
    sweatstack_bp.WEBUI = dependencies['WEBUI']
    sweatstack_bp.utils = dependencies['utils']
    sweatstack_bp.executor_client = dependencies['executor_client']
    
    # Register the blueprint
    app.register_blueprint(sweatstack_bp)

    # Make context function available to main app
    app.get_sweatstack_context = get_sweatstack_context

@sweatstack_bp.route('/authorize', methods=['GET'])
def authorize():
    """Redirect to SweatStack OAuth authorization"""
    return redirect(f'https://app.sweatstack.no/oauth/authorize?client_id={SWEATSTACK_CLIENT_ID}&scope=data:read,profile&redirect_uri={request.url_root}sweatstack/oauth-callback&prompt=none')

@sweatstack_bp.route('/oauth-callback', methods=['GET'])
def oauth_callback():
    """Handle SweatStack OAuth callback - stores complete token data in session"""
    # Check auth mode and validate accordingly
    if AUTH_MODE == 'auth0':
        # In Auth0 mode, validate that this is a legitimate callback
        if not session.get('session_id'):
            sweatstack_bp.logger.warning('SweatStack callback attempted without session')
            return redirect(url_for('index'))
    
    # Process the OAuth callback
    code = request.args.get('code')
    if not code:
        sweatstack_bp.logger.error('SweatStack callback missing authorization code')
        return redirect(url_for('index') + '?error=sweatstack_callback_failed')

    try:
        response = requests.post(
            'https://app.sweatstack.no/api/v1/oauth/token',
            data={
                'grant_type': 'authorization_code',
                'code': code,
                'client_id': SWEATSTACK_CLIENT_ID,
                'client_secret': SWEATSTACK_CLIENT_SECRET,
            },
        )
        response.raise_for_status()

        token_data = response.json()

        # Store complete token data in session (temporary)
        session['sweatstack_token_data'] = token_data
        # Keep legacy format for backward compatibility during transition
        session['sweatstack_access_token'] = token_data.get('access_token')
        
        sweatstack_bp.logger.info('SweatStack OAuth completed successfully')
        
        # Redirect back to main app
        return redirect(url_for('index'))

    except requests.exceptions.RequestException as e:
        sweatstack_bp.logger.error(f'Error exchanging SweatStack code for token: {str(e)}')
        return redirect(url_for('index') + '?error=sweatstack_token_exchange_failed')

@sweatstack_bp.route('/get_users', methods=['GET'])
@requires_auth
def get_users():
    """Get available SweatStack users"""
    access_token = get_or_migrate_sweatstack_token()  # Only change: use utility function
    if not access_token:
        return jsonify({'error': 'Not authenticated with SweatStack'}), 401

    try:
        sweatstack_client = ss.Client(api_key=access_token)

        accessible_users = sweatstack_client.get_users()
        current_user = sweatstack_client.get_userinfo()

        formatted_users = []
        for user in accessible_users:
            formatted_users.append({
                'id': user.id,
                'name': user.display_name,
                'is_current': user.id == current_user.sub
            })

        return jsonify({'users': formatted_users}), 200

    except Exception as e:
        sweatstack_bp.logger.error(f'Error fetching SweatStack users: {str(e)}')
        return jsonify({'error': f'Failed to fetch users: {str(e)}'}), 500

@sweatstack_bp.route('/load_data', methods=['POST'])
@requires_auth
def load_data():
    """Load SweatStack data with automatic date range adjustment based on subscription"""
    access_token = get_or_migrate_sweatstack_token()
    if not access_token:
        return jsonify({'error': 'Not authenticated with SweatStack'}), 401
    
    data = request.json or {}
    
    # If no data provided, just return auth status
    if not data or not data.get('sports'):
        return jsonify({'authenticated': True, 'message': 'Ready to load data'}), 200

    # Initialize variables outside the if block
    adjusted = False
    max_days = None
    
    # Auto-adjust date range based on subscription and payment status
    if data.get('start_date') and data.get('end_date'):
        auth0_id = get_current_user_id()
        
        # Get subscription with integration config (already imported at top)
        sub_result = get_user_subscription(auth0_id)
        
        compute_tier = 'free'
        sweatstack_extended = False
        
        if sub_result.get('ok') and sub_result.get('data'):
            subscription = sub_result['data']
            compute_tier = subscription.get('compute_tier', 'free')
            integration_config = subscription.get('integration_config', {})
            sweatstack_extended = integration_config.get('sweatstack_extended', False)
        
        # Determine max days based on payment status
        if not sweatstack_extended:
            max_days = 14  # Not paying = 14 days max regardless of tier
            adjustment_reason = "Limited to 14 days (SweatStack Extended not enabled)"
        else:
            # Paying = based on compute tier
            max_days_map = {'free': 14, 'plus': 182, 'pro': 365}
            max_days = max_days_map.get(compute_tier, 14)
            adjustment_reason = f"Limited to {max_days} days ({compute_tier} tier)"
        
        # Parse dates
        requested_start = datetime.strptime(data['start_date'], '%Y-%m-%d')
        requested_end = datetime.strptime(data['end_date'], '%Y-%m-%d')
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Calculate the allowed date range
        earliest_allowed = today - timedelta(days=max_days)
        
        # End date can't be in the future
        if requested_end > today:
            requested_end = today
            adjusted = True
        
        # Start date can't be earlier than max_days ago
        if requested_start < earliest_allowed:
            requested_start = earliest_allowed
            adjusted = True
        
        # Ensure start is before end
        if requested_start >= requested_end:
            requested_start = requested_end - timedelta(days=1)
            adjusted = True
        
        # Update the data with adjusted dates
        data['start_date'] = requested_start.strftime('%Y-%m-%d')
        data['end_date'] = requested_end.strftime('%Y-%m-%d')
        
        if adjusted:
            sweatstack_bp.logger.info(
                f'Auto-adjusted date range to {data["start_date"]} - {data["end_date"]} ({adjustment_reason})'
            )

    try:
        session_id = session['session_id']
        
        # Check execution mode
        if sweatstack_bp.global_execution_mode == 'api':
            result = _load_data_via_executor(session_id, access_token, data)
        
        # Add info about date adjustment to response
        if result[0].status_code == 200:
            response_data = result[0].get_json()
            response_data['date_range'] = {
                'start': data['start_date'],
                'end': data['end_date'],
                'auto_adjusted': adjusted,
                'max_days_allowed': max_days
            }
            return jsonify(response_data), 200
        
        return result
            
    except Exception as e:
        sweatstack_bp.logger.error(f'Error loading SweatStack data: {str(e)}')
        return jsonify({'error': f'Failed to load SweatStack data: {str(e)}'}), 500


def _load_data_via_executor(session_id, access_token, data):
    """Load SweatStack data via remote executor"""
    user_id = sweatstack_bp.get_user_id()
    sweatstack_bp.logger.info(f'Loading SweatStack data via executor for user: {user_id}')
    
    # Generate new df_id
    new_df_id = str(uuid.uuid4())
    
    # Prepare fetch parameters
    fetch_params = {
        'sports': data['sports'],
        'metrics': data['metrics'],
        'users': data['users'],
        'start_date': data['start_date'],
        'end_date': data['end_date']
    }
    
    # Call remote executor to fetch data
    executor_urls = sweatstack_bp.get_dynamic_executor_urls(user_id)
    
    response = requests.post(
        f"{executor_urls['EXECUTOR_API_BASE_URL']}/fetch_sweatstack_data",
        json={
            'access_token': access_token,
            'df_id': new_df_id,
            'fetch_params': fetch_params
        },
        timeout=30
    )
    response.raise_for_status()
    
    # Update user preferences and BambooAI instance
    prefs = sweatstack_bp.user_preferences.get(session_id, {
        'planning': False, 'ontology_path': None, 'auxiliary_datasets': []
    })
    prefs['df_id'] = new_df_id

    #sweatstack_bp.cleanup_and_remove_bamboo_instance(session_id)
    
    # Always recreate to ensure all parameters are properly initialized
    sweatstack_bp.user_preferences[session_id] = prefs
 
    sweatstack_bp.bamboo_ai_instances[session_id] = sweatstack_bp.get_bamboo_ai(session_id) # Update Preferences

    sweatstack_bp.bamboo_ai_instances[session_id].df_id = prefs.get('df_id')
    
    executor_client = sweatstack_bp.executor_client.ExecutorAPIClient(
        base_url=executor_urls['EXECUTOR_API_BASE_URL']
    )
    
    # the Data tab's grid (2026-09-08): the first page from the executor; the 100-row preview only if it has no page
    df_html = None
    try:
        _page = executor_client.dataframe_page(new_df_id, 0, 50)
        if _page:
            _page['df_id'] = new_df_id
            df_html = _page
    except Exception:                                # noqa: BLE001
        df_html = None
    if df_html is None:
        df_sample_for_preview = sweatstack_bp.utils.computeDataframeSample(
            df=None,
            execution_mode='api',
            df_id=new_df_id,
            executor_client=executor_client
        )

        df_html = df_sample_for_preview.to_html(classes='dataframe', border=0, index=False)
    df_json_str = json.dumps({'type': 'dataframe', 'data': df_html})
    
    sweatstack_bp.logger.info(f'SweatStack data loaded via executor successfully for user: {user_id}')
    return jsonify({
        'message': 'SweatStack data loaded successfully via remote executor',
        'dataframe': df_json_str,
        'df_id': new_df_id
    }), 200

@sweatstack_bp.route('/logout', methods=['POST'])
@requires_auth
def logout():
    """Logout from SweatStack by removing access token"""
    user_id = sweatstack_bp.get_user_id()
    auth0_id = get_current_user_id()
    
    # Clear from session
    session.pop('sweatstack_access_token', None)
    session.pop('sweatstack_token_data', None)
    
    # Remove from database
    try:
        remove_sweatstack_token(user_id, auth0_id)
    except Exception as e:
        sweatstack_bp.logger.error(f'Error removing SweatStack token from DB for user {user_id}: {str(e)}')
    
    sweatstack_bp.logger.info(f'SweatStack logout completed for user: {user_id}')
    return jsonify({'message': 'Logged out from SweatStack successfully'}), 200

@sweatstack_bp.route('/remove_data', methods=['POST'])
@requires_auth
def remove_data():
    """Remove SweatStack data (which is loaded as primary dataset)"""
    session_id = session.get('session_id')
    if not session_id:
        return jsonify({'error': 'No session ID found'}), 400

    try:
        bamboo_ai_instance = sweatstack_bp.bamboo_ai_instances.get(session_id)
        prefs = sweatstack_bp.user_preferences.get(session_id)

        if not bamboo_ai_instance or bamboo_ai_instance.df_id is None:
            return jsonify({'message': 'No SweatStack data is currently loaded.'}), 400

        bamboo_ai_instance.df = None
        bamboo_ai_instance.df_id = None

        # Also clear df_id from user_preferences if it's stored there
        if prefs and 'df_id' in prefs:
             del prefs['df_id']

        sweatstack_bp.user_preferences[session_id] = prefs # Save updated prefs

        sweatstack_bp.logger.info(f"SweatStack data removed and BambooAI instance reset for session {session_id}.")
        return jsonify({'message': 'SweatStack data removed successfully.'}), 200

    except Exception as e:
        sweatstack_bp.logger.error(f"Error removing SweatStack data for session {session_id}: {str(e)}")
        return jsonify({'error': f'Error removing SweatStack data: {str(e)}'}), 500