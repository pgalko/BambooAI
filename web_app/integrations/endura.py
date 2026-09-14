# integrations/endura.py

import os
import requests
import json
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from auth import requires_auth, get_current_user_id

# Import Endura functions from supabase_client
from auth.supabase_client import (
    store_endura_api_key,
    get_endura_api_key,
    remove_endura_api_key,
    get_endura_integration_status
)

# Create the blueprint
endura_bp = Blueprint('endura', __name__, url_prefix='/endura')

def get_endura_context():
    """Get Endura context - check if user has API key stored"""
    has_api_key = False
    
    try:
        auth0_id = get_current_user_id()
        
        if auth0_id:
            # Extract bamboo_user_id from auth0_id
            bamboo_user_id = auth0_id.split('|')[1] if '|' in auth0_id else auth0_id
            
            # Check if user has API key in database
            status = get_endura_integration_status(bamboo_user_id, auth0_id)
            has_api_key = status.get('has_api_key', False)
    except Exception as e:
        print(f"Error checking Endura context: {str(e)}")
        has_api_key = False
    
    return {
        'endura_enabled': has_api_key,
        'endura_authenticated': has_api_key
    }

def init_endura_integration(app, **dependencies):
    """Initialize Endura integration with the main app and dependencies"""
    # Store dependencies for use in routes
    endura_bp.user_preferences = dependencies['user_preferences']
    endura_bp.bamboo_ai_instances = dependencies['bamboo_ai_instances']
    endura_bp.get_user_id = dependencies['get_user_id']
    endura_bp.get_bamboo_ai = dependencies['get_bamboo_ai']
    endura_bp.get_dynamic_executor_urls = dependencies['get_dynamic_executor_urls']
    endura_bp.global_execution_mode = dependencies['global_execution_mode']
    endura_bp.logger = dependencies['logger']
    
    # Additional constants from main app
    endura_bp.EXPLORATORY = dependencies['EXPLORATORY']
    endura_bp.SEARCH_TOOL = dependencies['SEARCH_TOOL']
    endura_bp.WEBUI = dependencies['WEBUI']
    endura_bp.utils = dependencies['utils']
    endura_bp.executor_client = dependencies['executor_client']
    
    # Register the blueprint
    app.register_blueprint(endura_bp)

    # Make context function available to main app
    app.get_endura_context = get_endura_context

@endura_bp.route('/store_api_key', methods=['POST'])
@requires_auth
def store_api_key():
    """Store user's Endura API key"""
    data = request.json or {}
    api_key = data.get('api_key')
    
    if not api_key:
        return jsonify({'error': 'API key is required'}), 400
    
    try:
        user_id = endura_bp.get_user_id()
        auth0_id = get_current_user_id()
        
        success = store_endura_api_key(user_id, auth0_id, api_key)
        
        if success:
            endura_bp.logger.info(f'Endura API key stored for user: {user_id}')
            return jsonify({'message': 'API key stored successfully'}), 200
        else:
            return jsonify({'error': 'Failed to store API key'}), 500
            
    except Exception as e:
        endura_bp.logger.error(f'Error storing Endura API key: {str(e)}')
        return jsonify({'error': f'Failed to store API key: {str(e)}'}), 500

@endura_bp.route('/remove_api_key', methods=['POST'])
@requires_auth
def remove_api_key():
    """Remove user's Endura API key"""
    try:
        user_id = endura_bp.get_user_id()
        auth0_id = get_current_user_id()
        
        success = remove_endura_api_key(user_id, auth0_id)
        
        if success:
            endura_bp.logger.info(f'Endura API key removed for user: {user_id}')
            return jsonify({'message': 'API key removed successfully'}), 200
        else:
            return jsonify({'error': 'Failed to remove API key'}), 500
            
    except Exception as e:
        endura_bp.logger.error(f'Error removing Endura API key: {str(e)}')
        return jsonify({'error': f'Failed to remove API key: {str(e)}'}), 500

@endura_bp.route('/get_races', methods=['GET'])
@requires_auth
def get_races():
    """Forward request to container to get races from Endura"""
    try:
        user_id = endura_bp.get_user_id()
        auth0_id = get_current_user_id()
        
        # Check if user has API key configured
        api_key = get_endura_api_key(user_id, auth0_id)
        if not api_key:
            return jsonify({'error': 'No API key configured'}), 401
        
        # Get executor URLs for this user
        executor_urls = endura_bp.get_dynamic_executor_urls(user_id)
        
        # Forward to container with API key
        response = requests.get(
            f"{executor_urls['EXECUTOR_API_BASE_URL']}/endura/get_races",
            headers={'X-API-Key': api_key},  # Pass API key to container
            timeout=10
        )
        
        if response.status_code == 401:
            return jsonify({'error': 'Invalid API key'}), 401
        
        response.raise_for_status()
        data = response.json()
        
        return jsonify(data), 200
        
    except Exception as e:
        endura_bp.logger.error(f'Error getting races: {str(e)}')
        return jsonify({'error': f'Failed to get races: {str(e)}'}), 500

@endura_bp.route('/load_data', methods=['POST'])
@requires_auth
def load_data():
    """Forward race data request to container"""
    data = request.json or {}
    race_id = data.get('race_id')
    aux_datasets = data.get('aux_datasets', ['profile'])
    
    if not race_id:
        return jsonify({'error': 'race_id is required'}), 400
    
    # Ensure profile is always included
    if 'profile' not in aux_datasets:
        aux_datasets.insert(0, 'profile')
    
    # Get user's API key from secure storage
    user_id = endura_bp.get_user_id()
    auth0_id = get_current_user_id()
    
    api_key = get_endura_api_key(user_id, auth0_id)
    
    if not api_key:
        return jsonify({'error': 'No API key configured'}), 401
    
    try:
        session_id = session['session_id']
        
        # Generate new df_id
        import uuid
        new_df_id = str(uuid.uuid4())
        
        # Forward to executor/container
        executor_urls = endura_bp.get_dynamic_executor_urls(user_id)
        
        response = requests.post(
            f"{executor_urls['EXECUTOR_API_BASE_URL']}/endura/load_race_data",
            json={
                'api_key': api_key,  # API key sent securely to container
                'df_id': new_df_id,
                'race_id': race_id,
                'aux_datasets': aux_datasets,
                'user_id': user_id
            },
            timeout=30
        )
        response.raise_for_status()
        
        result = response.json()
        
        # Update user preferences
        prefs = endura_bp.user_preferences.get(session_id, {
            'planning': False, 'ontology_path': None, 'auxiliary_datasets': []
        })
        prefs['df_id'] = new_df_id
        
        if result.get('aux_datasets'):
            prefs['auxiliary_datasets'] = result['aux_datasets']
        
        # Update BambooAI instance
        endura_bp.user_preferences[session_id] = prefs
        endura_bp.bamboo_ai_instances[session_id] = endura_bp.get_bamboo_ai(session_id)
        endura_bp.bamboo_ai_instances[session_id].df_id = prefs.get('df_id')
        endura_bp.bamboo_ai_instances[session_id].auxiliary_datasets = prefs.get('auxiliary_datasets', [])
        
        # Generate DataFrame sample
        executor_client = endura_bp.executor_client.ExecutorAPIClient(
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
            df_sample_for_preview = endura_bp.utils.computeDataframeSample(
                df=None,
                execution_mode='api',
                df_id=new_df_id,
                executor_client=executor_client
            )

            df_html = df_sample_for_preview.to_html(classes='dataframe', border=0, index=False)
        result['dataframe'] = json.dumps({'type': 'dataframe', 'data': df_html})
        
        return jsonify(result), 200
        
    except Exception as e:
        endura_bp.logger.error(f'Error loading Endura data: {str(e)}')
        return jsonify({'error': f'Failed to load data: {str(e)}'}), 500

@endura_bp.route('/remove_data', methods=['POST'])
@requires_auth
def remove_data():
    """Remove PRIMARY Endura data only (not auxiliary datasets)"""
    session_id = session.get('session_id')
    if not session_id:
        return jsonify({'error': 'No session ID found'}), 400

    try:
        bamboo_ai_instance = endura_bp.bamboo_ai_instances.get(session_id)
        prefs = endura_bp.user_preferences.get(session_id)

        if not bamboo_ai_instance or bamboo_ai_instance.df_id is None:
            return jsonify({'message': 'No Endura data is currently loaded.'}), 400

        # Clear main DataFrame
        bamboo_ai_instance.df = None
        bamboo_ai_instance.df_id = None

        # Clear df_id from preferences
        if prefs and 'df_id' in prefs:
            del prefs['df_id']
        
        endura_bp.user_preferences[session_id] = prefs

        endura_bp.logger.info(f"Endura primary data removed for session {session_id}")
        return jsonify({'message': 'Endura data removed successfully.'}), 200

    except Exception as e:
        endura_bp.logger.error(f"Error removing Endura data for session {session_id}: {str(e)}")
        return jsonify({'error': f'Error removing Endura data: {str(e)}'}), 500

@endura_bp.route('/status', methods=['GET'])
@requires_auth
def status():
    """Get Endura integration status"""
    try:
        user_id = endura_bp.get_user_id()
        auth0_id = get_current_user_id()
        
        status = get_endura_integration_status(user_id, auth0_id)
        
        return jsonify({
            'enabled': True,
            'authenticated': status.get('has_api_key', False),
            'has_api_key': status.get('has_api_key', False)
        }), 200
        
    except Exception as e:
        endura_bp.logger.error(f'Error getting Endura status: {str(e)}')
        return jsonify({
            'enabled': True,
            'authenticated': False,
            'has_api_key': False
        }), 200