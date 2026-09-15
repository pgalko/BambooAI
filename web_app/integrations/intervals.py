# integrations/intervals.py - Updated with database storage

import os
import requests
import uuid
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from auth import requires_auth, get_current_user_id

# Import Intervals functions from supabase_client
from auth.supabase_client import (
    store_intervals_api_key,
    get_intervals_api_key,
    remove_intervals_api_key,
    get_intervals_integration_status,
    get_user_subscription
)

# Create the blueprint
intervals_bp = Blueprint('intervals', __name__, url_prefix='/intervals')

def get_intervals_context():
    """Get Intervals context - check if user has API key stored"""
    has_api_key = False
    
    try:
        auth0_id = get_current_user_id()
        
        if auth0_id:
            # Extract bamboo_user_id from auth0_id
            bamboo_user_id = auth0_id.split('|')[1] if '|' in auth0_id else auth0_id
            
            # Check if user has API key in database
            status = get_intervals_integration_status(bamboo_user_id, auth0_id)
            has_api_key = status.get('has_api_key', False)
    except Exception as e:
        print(f"Error checking Intervals context: {str(e)}")
        has_api_key = False
    
    return {
        'intervals_enabled': has_api_key,  # Only enabled if user has API key
        'intervals_authenticated': has_api_key
    }

def init_intervals_integration(app, **dependencies):
    """Initialize Intervals integration with the main app and dependencies"""
    # Store dependencies for use in routes
    intervals_bp.user_preferences = dependencies['user_preferences']
    intervals_bp.bamboo_ai_instances = dependencies['bamboo_ai_instances']
    intervals_bp.get_user_id = dependencies['get_user_id']
    intervals_bp.get_bamboo_ai = dependencies['get_bamboo_ai']
    intervals_bp.get_dynamic_executor_urls = dependencies['get_dynamic_executor_urls']
    intervals_bp.global_execution_mode = dependencies['global_execution_mode']
    intervals_bp.logger = dependencies['logger']
    
    # Additional constants from main app
    intervals_bp.EXPLORATORY = dependencies['EXPLORATORY']
    intervals_bp.SEARCH_TOOL = dependencies['SEARCH_TOOL']
    intervals_bp.WEBUI = dependencies['WEBUI']
    intervals_bp.utils = dependencies['utils']
    intervals_bp.executor_client = dependencies['executor_client']
    
    # Register the blueprint
    app.register_blueprint(intervals_bp)

    # Make context function available to main app
    app.get_intervals_context = get_intervals_context

@intervals_bp.route('/store_api_key', methods=['POST'])
@requires_auth
def store_api_key():
    """Store user's Intervals API key"""
    data = request.json or {}
    api_key = data.get('api_key')
    
    if not api_key:
        return jsonify({'error': 'API key is required'}), 400
    
    try:
        user_id = intervals_bp.get_user_id()
        auth0_id = get_current_user_id()
        
        success = store_intervals_api_key(user_id, auth0_id, api_key)
        
        if success:
            intervals_bp.logger.info(f'Intervals API key stored for user: {user_id}')
            return jsonify({'message': 'API key stored successfully'}), 200
        else:
            return jsonify({'error': 'Failed to store API key'}), 500
            
    except Exception as e:
        intervals_bp.logger.error(f'Error storing Intervals API key: {str(e)}')
        return jsonify({'error': f'Failed to store API key: {str(e)}'}), 500

@intervals_bp.route('/remove_api_key', methods=['POST'])
@requires_auth
def remove_api_key():
    """Remove user's Intervals API key"""
    try:
        user_id = intervals_bp.get_user_id()
        auth0_id = get_current_user_id()
        
        success = remove_intervals_api_key(user_id, auth0_id)
        
        if success:
            intervals_bp.logger.info(f'Intervals API key removed for user: {user_id}')
            return jsonify({'message': 'API key removed successfully'}), 200
        else:
            return jsonify({'error': 'Failed to remove API key'}), 500
            
    except Exception as e:
        intervals_bp.logger.error(f'Error removing Intervals API key: {str(e)}')
        return jsonify({'error': f'Failed to remove API key: {str(e)}'}), 500
    
@intervals_bp.route('/get_data_limits', methods=['GET'])
@requires_auth
def get_data_limits():
    """Get data limits based purely on compute tier for Intervals"""
    try:
        auth0_id = get_current_user_id()
        if not auth0_id:
            return jsonify({'max_days': 14}), 200

        result = get_user_subscription(auth0_id)
        
        compute_tier = 'free'
        if result.get('ok') and result.get('data'):
            compute_tier = result['data'].get('compute_tier', 'free')
        
        # Intervals: Always based on compute tier (no payment required)
        max_days_map = {
            'free': 14,
            'plus': 182,  # 6 months
            'pro': 365,    # 1 year
            'local': 3650  # your own machine: no limit that matters
        }
        max_days = max_days_map.get(compute_tier, 14)
        
        return jsonify({
            'max_days': max_days,
            'compute_tier': compute_tier
        }), 200
        
    except Exception as e:
        intervals_bp.logger.error(f'Error getting data limits: {str(e)}')
        return jsonify({'max_days': 14}), 200

@intervals_bp.route('/load_data', methods=['POST'])
@requires_auth
def load_data():
    """Start Intervals.icu data load job with tier-based date restrictions"""
    data = request.json or {}
    
    # Get user's API key from database
    user_id = intervals_bp.get_user_id()
    auth0_id = get_current_user_id()
    
    api_key = get_intervals_api_key(user_id, auth0_id)
    
    if not api_key:
        return jsonify({'error': 'No API key configured. Please add your Intervals.icu API key.'}), 401
    
    # Validate and auto-adjust date range based on compute tier
    if data.get('start_date') and data.get('end_date'):
        from datetime import datetime, timedelta
        
        sub_result = get_user_subscription(auth0_id)
        compute_tier = 'free'
        
        if sub_result.get('ok') and sub_result.get('data'):
            compute_tier = sub_result['data'].get('compute_tier', 'free')
        
        # Max days based on compute tier
        max_days_map = {'free': 14, 'plus': 182, 'pro': 365, 'local': 3650}
        max_days = max_days_map.get(compute_tier, 14)
        
        # Parse and adjust dates
        requested_start = datetime.strptime(data['start_date'], '%Y-%m-%d')
        requested_end = datetime.strptime(data['end_date'], '%Y-%m-%d')
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Calculate the allowed date range
        earliest_allowed = today - timedelta(days=max_days)
        
        # Auto-adjust if needed
        if requested_end > today:
            requested_end = today
        
        if requested_start < earliest_allowed:
            requested_start = earliest_allowed
        
        if requested_start >= requested_end:
            requested_start = requested_end - timedelta(days=1)
        
        # Update with adjusted dates
        data['start_date'] = requested_start.strftime('%Y-%m-%d')
        data['end_date'] = requested_end.strftime('%Y-%m-%d')
        
        intervals_bp.logger.info(f'Date range adjusted to {max_days} days limit ({compute_tier} tier)')
    
    try:
        session_id = session['session_id']
        
        # Generate new df_id
        new_df_id = str(uuid.uuid4())
        
        # Start job on executor
        executor_urls = intervals_bp.get_dynamic_executor_urls(user_id)
        if not executor_urls:                      # the self-hosted edition on the local kernel (docs/OSS_DESIGN.md D5)
            return jsonify({'error': 'Loading from Intervals needs an executor in this edition for now: run the executor image in Docker and set EXECUTION_MODE=api and EXECUTOR_API_BASE_URL in .env'}), 409
        
        response = requests.post(
            f"{executor_urls['EXECUTOR_API_BASE_URL']}/fetch_intervals_data",
            json={
                'api_key': api_key,
                'df_id': new_df_id,
                'start_date': data['start_date'],
                'end_date': data['end_date'],
                'metrics': data.get('metrics', []),
                'aux_datasets': data.get('aux_datasets', []),
                'user_id': user_id
            },
            timeout=10
        )
        response.raise_for_status()
        
        job_data = response.json()
        
        # Store df_id in session for later
        session['intervals_df_id'] = new_df_id
        session['intervals_job_id'] = job_data['job_id']
        
        return jsonify({'job_id': job_data['job_id']}), 202
        
    except Exception as e:
        intervals_bp.logger.error(f'Error starting Intervals load: {str(e)}')
        return jsonify({'error': f'Failed to start data load: {str(e)}'}), 500

@intervals_bp.route('/job/<job_id>', methods=['GET'])
@requires_auth
def get_job_status(job_id):
    """Get status of Intervals data loading job"""
    try:
        user_id = intervals_bp.get_user_id()
        executor_urls = intervals_bp.get_dynamic_executor_urls(user_id)
        if not executor_urls:                      # the self-hosted edition on the local kernel (docs/OSS_DESIGN.md D5)
            return jsonify({'error': 'Loading from Intervals needs an executor in this edition for now: run the executor image in Docker and set EXECUTION_MODE=api and EXECUTOR_API_BASE_URL in .env'}), 409
        
        # Forward request to executor
        response = requests.get(
            f"{executor_urls['EXECUTOR_API_BASE_URL']}/intervals_job/{job_id}",
            timeout=5
        )
        
        if response.status_code == 404:
            return jsonify({'status': 'not_found'}), 404
        
        response.raise_for_status()
        job_data = response.json()
        
        # If completed successfully, set up the BambooAI instance
        if job_data['status'] == 'completed' and 'result' in job_data:
            session_id = session['session_id']
            result = job_data['result']
            
            # Update user preferences
            prefs = intervals_bp.user_preferences.get(session_id, {
                'planning': False, 'ontology_path': None, 'auxiliary_datasets': []
            })
            prefs['df_id'] = result['df_id']
            
            if result.get('aux_datasets'):
                prefs['auxiliary_datasets'] = result['aux_datasets']
            
            # Clean up and create new instance
            #intervals_bp.cleanup_and_remove_bamboo_instance(session_id)

            # 1. Update user preferences FIRST
            intervals_bp.user_preferences[session_id] = prefs

            # 2. Get the BambooAI instance (creates new or returns existing)
            intervals_bp.bamboo_ai_instances[session_id] = intervals_bp.get_bamboo_ai(session_id)

            # 3. Always update the properties (in case it was an existing instance)
            intervals_bp.bamboo_ai_instances[session_id].df_id = prefs.get('df_id')
            intervals_bp.bamboo_ai_instances[session_id].auxiliary_datasets = prefs.get('auxiliary_datasets', [])
            
            # Generate DataFrame sample
            executor_client = intervals_bp.executor_client.ExecutorAPIClient(
                base_url=executor_urls['EXECUTOR_API_BASE_URL']
            )
            
            # the Data tab's grid (2026-09-08): the first page from the executor; the 100-row preview only if it has no page
            df_html = None
            try:
                _page = executor_client.dataframe_page(result['df_id'], 0, 50)
                if _page:
                    _page['df_id'] = result['df_id']
                    df_html = _page
            except Exception:                                # noqa: BLE001
                df_html = None
            if df_html is None:
                df_sample_for_preview = intervals_bp.utils.computeDataframeSample(
                    df=None,
                    execution_mode='api',
                    df_id=result['df_id'],
                    executor_client=executor_client
                )

                df_html = df_sample_for_preview.to_html(classes='dataframe', border=0, index=False)
            job_data['dataframe'] = json.dumps({'type': 'dataframe', 'data': df_html})
        
        return jsonify(job_data), 200
        
    except Exception as e:
        intervals_bp.logger.error(f'Error getting job status: {str(e)}')
        return jsonify({'status': 'error', 'error': str(e)}), 500

@intervals_bp.route('/remove_data', methods=['POST'])
@requires_auth
def remove_data():
    """Remove PRIMARY Intervals.icu data only (not auxiliary datasets)"""
    session_id = session.get('session_id')
    if not session_id:
        return jsonify({'error': 'No session ID found'}), 400

    try:
        bamboo_ai_instance = intervals_bp.bamboo_ai_instances.get(session_id)
        prefs = intervals_bp.user_preferences.get(session_id)

        if not bamboo_ai_instance or bamboo_ai_instance.df_id is None:
            return jsonify({'message': 'No Intervals.icu data is currently loaded.'}), 400

        # Clear main DataFrame
        bamboo_ai_instance.df = None
        bamboo_ai_instance.df_id = None

        # Clear df_id from preferences
        if prefs and 'df_id' in prefs:
            del prefs['df_id']
        
        # NOTE: Do NOT remove auxiliary datasets here - they have their own pills
        # Users can remove them individually if needed
        
        intervals_bp.user_preferences[session_id] = prefs

        intervals_bp.logger.info(f"Intervals.icu primary data removed for session {session_id}")
        return jsonify({'message': 'Intervals.icu data removed successfully.'}), 200

    except Exception as e:
        intervals_bp.logger.error(f"Error removing Intervals.icu data for session {session_id}: {str(e)}")
        return jsonify({'error': f'Error removing Intervals.icu data: {str(e)}'}), 500

@intervals_bp.route('/status', methods=['GET'])
@requires_auth
def status():
    """Get Intervals.icu integration status"""
    try:
        user_id = intervals_bp.get_user_id()
        auth0_id = get_current_user_id()
        
        status = get_intervals_integration_status(user_id, auth0_id)
        
        return jsonify({
            'enabled': True,
            'authenticated': status.get('has_api_key', False),
            'has_api_key': status.get('has_api_key', False)
        }), 200
        
    except Exception as e:
        intervals_bp.logger.error(f'Error getting Intervals status: {str(e)}')
        return jsonify({
            'enabled': True,
            'authenticated': False,
            'has_api_key': False
        }), 200