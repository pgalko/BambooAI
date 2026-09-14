# integrations/cache_manager.py - Cache viewing and management blueprint

import requests
from flask import Blueprint, request, jsonify, session
from auth import requires_auth, get_current_user_id
import json

# Create the blueprint
cache_bp = Blueprint('cache', __name__, url_prefix='/cache')

def init_cache_integration(app, **dependencies):
    """Initialize Cache management integration with the main app and dependencies"""
    # Store essential dependencies
    cache_bp.get_user_id = dependencies['get_user_id']
    cache_bp.get_dynamic_executor_urls = dependencies['get_dynamic_executor_urls']
    cache_bp.logger = dependencies['logger']
    
    # Add session and preference management dependencies
    cache_bp.user_preferences = dependencies['user_preferences']
    cache_bp.bamboo_ai_instances = dependencies['bamboo_ai_instances']
    cache_bp.get_bamboo_ai = dependencies['get_bamboo_ai']
    
    # Add preview generation dependencies
    cache_bp.utils = dependencies['utils']
    cache_bp.executor_client = dependencies['executor_client']
    
    # Register the blueprint
    app.register_blueprint(cache_bp)

@cache_bp.route('/inspect', methods=['GET'])
@requires_auth
def inspect_cache():
    """Get all cached DataFrames and auxiliary datasets from user's container"""
    try:
        user_id = cache_bp.get_user_id()
        executor_urls = cache_bp.get_dynamic_executor_urls(user_id)
        
        # Forward request to executor
        response = requests.get(
            f"{executor_urls['EXECUTOR_API_BASE_URL']}/cache/inspect",
            params={'user_id': user_id},
            timeout=5
        )
        response.raise_for_status()
        
        return jsonify(response.json()), 200
        
    except requests.exceptions.RequestException as e:
        cache_bp.logger.error(f'Error inspecting cache: {str(e)}')
        return jsonify({'error': f'Failed to inspect cache: {str(e)}'}), 500

@cache_bp.route('/preview/<df_id>', methods=['GET'])
@requires_auth
def preview_dataframe(df_id):
    """Get preview of a specific cached DataFrame"""
    try:
        user_id = cache_bp.get_user_id()
        executor_urls = cache_bp.get_dynamic_executor_urls(user_id)
        
        # Forward request to executor
        response = requests.get(
            f"{executor_urls['EXECUTOR_API_BASE_URL']}/cache/preview/{df_id}",
            timeout=5
        )
        
        if response.status_code == 404:
            return jsonify({'error': 'DataFrame not found in cache'}), 404
            
        response.raise_for_status()
        
        return jsonify(response.json()), 200
        
    except requests.exceptions.RequestException as e:
        cache_bp.logger.error(f'Error previewing DataFrame {df_id}: {str(e)}')
        return jsonify({'error': f'Failed to preview DataFrame: {str(e)}'}), 500

@cache_bp.route('/preview_aux', methods=['POST'])
@requires_auth
def preview_aux_dataset():
    """Get preview of an auxiliary dataset file"""
    try:
        user_id = cache_bp.get_user_id()
        executor_urls = cache_bp.get_dynamic_executor_urls(user_id)
        
        data = request.json or {}
        file_path = data.get('file_path')
        
        if not file_path:
            return jsonify({'error': 'file_path is required'}), 400
        
        # Forward request to executor with user_id
        response = requests.post(
            f"{executor_urls['EXECUTOR_API_BASE_URL']}/cache/preview_aux",
            json={
                'file_path': file_path,
                'user_id': user_id
            },
            timeout=5
        )
        
        if response.status_code == 404:
            return jsonify({'error': 'File not found'}), 404
        elif response.status_code == 403:
            return jsonify({'error': 'Access denied'}), 403
            
        response.raise_for_status()
        
        return jsonify(response.json()), 200
        
    except requests.exceptions.RequestException as e:
        cache_bp.logger.error(f'Error previewing aux dataset: {str(e)}')
        return jsonify({'error': f'Failed to preview aux dataset: {str(e)}'}), 500

@cache_bp.route('/status', methods=['GET'])
@requires_auth
def cache_status():
    """Get quick cache status summary"""
    try:
        user_id = cache_bp.get_user_id()
        executor_urls = cache_bp.get_dynamic_executor_urls(user_id)
        
        # Get cache inspection data
        response = requests.get(
            f"{executor_urls['EXECUTOR_API_BASE_URL']}/cache/inspect",
            params={'user_id': user_id},
            timeout=5
        )
        response.raise_for_status()
        
        data = response.json()
        
        # Return simplified status
        return jsonify({
            'cache_count': data['cache_stats']['current_cache_size'],
            'cache_max': data['cache_stats']['max_cache_size'],
            'memory_mb': data['cache_stats']['total_memory_mb'],
            'aux_datasets_count': len(data.get('auxiliary_datasets', []))
        }), 200
        
    except Exception as e:
        cache_bp.logger.error(f'Error getting cache status: {str(e)}')
        # Return empty status on error
        return jsonify({
            'cache_count': 0,
            'cache_max': 3,
            'memory_mb': 0,
            'aux_datasets_count': 0
        }), 200
    
@cache_bp.route('/load_primary', methods=['POST'])
@requires_auth
def load_primary_from_cache():
    """Load a primary dataset from cache"""
    try:
        data = request.json or {}
        df_id = data.get('df_id')
        
        if not df_id:
            return jsonify({'error': 'df_id is required'}), 400
        
        session_id = session.get('session_id')
        if not session_id:
            return jsonify({'error': 'No session found'}), 400
        
        # Get user preferences
        prefs = cache_bp.user_preferences.get(session_id, {
            'planning': False, 'ontology_path': None, 'auxiliary_datasets': []
        })
        
        # Update with new df_id
        prefs['df_id'] = df_id
        cache_bp.user_preferences[session_id] = prefs
        
        # Clean up and create new BambooAI instance
        #cache_bp.cleanup_and_remove_bamboo_instance(session_id)

        cache_bp.bamboo_ai_instances[session_id] = cache_bp.get_bamboo_ai(session_id)

        cache_bp.bamboo_ai_instances[session_id].df_id = prefs.get('df_id')
        
        # Generate DataFrame preview
        user_id = cache_bp.get_user_id()
        executor_urls = cache_bp.get_dynamic_executor_urls(user_id)
        executor_client = cache_bp.executor_client.ExecutorAPIClient(
            base_url=executor_urls['EXECUTOR_API_BASE_URL']
        )
        
        # the Data tab's grid (2026-09-08): the first page; the 100-row preview only if the executor has no page
        page = None
        try:
            page = executor_client.dataframe_page(df_id, 0, 50)
            if page:
                page['df_id'] = df_id
        except Exception as exc:                                # noqa: BLE001
            cache_bp.logger.warning(f"Data tab: page request failed ({exc}); falling back to the 100-row preview")
        if page:
            preview = page
        else:
            df_sample_for_preview = cache_bp.utils.computeDataframeSample(
                df=None,
                execution_mode='api',
                df_id=df_id,
                executor_client=executor_client
            )
            preview = df_sample_for_preview.to_html(classes='dataframe', border=0, index=False)
        cache_bp.logger.info(f'Loaded primary dataset from cache: {df_id}')
        return jsonify({
            'success': True,
            'message': 'Primary dataset loaded from cache',
            'df_id': df_id,
            'dataframe': json.dumps({'type': 'dataframe', 'data': preview})
        }), 200
        
    except Exception as e:
        cache_bp.logger.error(f'Error loading primary from cache: {str(e)}')
        return jsonify({'error': f'Failed to load dataset: {str(e)}'}), 500

@cache_bp.route('/load_auxiliary', methods=['POST'])
@requires_auth
def load_auxiliary_from_cache():
    """Load an auxiliary dataset from cache"""
    try:
        data = request.json or {}
        file_path = data.get('file_path')
        
        if not file_path:
            return jsonify({'error': 'file_path is required'}), 400
        
        session_id = session.get('session_id')
        if not session_id:
            return jsonify({'error': 'No session found'}), 400
        
        # Get user preferences
        prefs = cache_bp.user_preferences.get(session_id, {
            'planning': False, 'ontology_path': None, 'auxiliary_datasets': []
        })
        
        # Check auxiliary dataset limit
        if len(prefs.get('auxiliary_datasets', [])) >= 3:
            return jsonify({'error': 'Maximum 3 auxiliary datasets allowed'}), 400
        
        # Add to auxiliary datasets if not already there
        if file_path not in prefs.get('auxiliary_datasets', []):
            if 'auxiliary_datasets' not in prefs:
                prefs['auxiliary_datasets'] = []
            prefs['auxiliary_datasets'].append(file_path)
            cache_bp.user_preferences[session_id] = prefs
        
        # Generate auxiliary dataset preview: the Data tab's first page (2026-09-08), else the old HTML sample
        _aux_client = cache_bp.executor_client.ExecutorAPIClient(
            base_url=cache_bp.get_dynamic_executor_urls(cache_bp.get_user_id())['EXECUTOR_API_BASE_URL']
        )
        df_html = None
        try:
            df_html = _aux_client.aux_page(file_path, 0, 50) or None
        except Exception as exc:                                # noqa: BLE001
            cache_bp.logger.warning(f"Data tab: auxiliary page failed ({exc}); falling back to the sample")
        if df_html is None:
            html_list = cache_bp.utils.compute_aux_dataset_sample(
                file_paths=[file_path],  # utils function expects a list
                execution_mode='api',
                executor_client=_aux_client
            )
            # Convert the HTML list to a single HTML string
            df_html = html_list[0] if html_list else '<div>No preview available</div>'
        
        cache_bp.logger.info(f'Loaded auxiliary dataset from cache: {file_path}')
        
        return jsonify({
            'success': True,
            'message': 'Auxiliary dataset loaded from cache',
            'file_path': file_path,
            'aux_count': len(prefs['auxiliary_datasets']),
            'dataframe': json.dumps({'type': 'dataframe', 'data': df_html})
        }), 200
        
    except Exception as e:
        cache_bp.logger.error(f'Error loading auxiliary from cache: {str(e)}')
        return jsonify({'error': f'Failed to load dataset: {str(e)}'}), 500
    
@cache_bp.route('/remove_primary', methods=['POST'])
@requires_auth
def remove_primary_from_cache():
    """Remove primary dataset from cache and session"""
    try:
        data = request.json or {}
        df_id = data.get('df_id')
        
        if not df_id:
            return jsonify({'error': 'df_id is required'}), 400
        
        session_id = session.get('session_id')
        if not session_id:
            return jsonify({'error': 'No session found'}), 400
        
        # Remove from container cache
        user_id = cache_bp.get_user_id()
        executor_urls = cache_bp.get_dynamic_executor_urls(user_id)
        
        response = requests.post(
            f"{executor_urls['EXECUTOR_API_BASE_URL']}/cache/remove_primary",
            json={'df_id': df_id},
            timeout=5
        )
        
        # Update session regardless of cache removal result
        bamboo_ai_instance = cache_bp.bamboo_ai_instances.get(session_id)
        prefs = cache_bp.user_preferences.get(session_id, {})
        
        if bamboo_ai_instance:
            bamboo_ai_instance.df = None
            bamboo_ai_instance.df_id = None
        
        if 'df_id' in prefs:
            del prefs['df_id']
        
        cache_bp.user_preferences[session_id] = prefs
        
        return jsonify({'success': True, 'message': 'Primary dataset removed'}), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@cache_bp.route('/remove_auxiliary', methods=['POST'])
@requires_auth  
def remove_auxiliary_from_cache():
    """Remove auxiliary dataset from filesystem and session"""
    try:
        data = request.json or {}
        file_path = data.get('file_path')
        
        if not file_path:
            return jsonify({'error': 'file_path is required'}), 400
        
        session_id = session.get('session_id')
        if not session_id:
            return jsonify({'error': 'No session found'}), 400
        
        # Remove from container filesystem
        user_id = cache_bp.get_user_id()
        executor_urls = cache_bp.get_dynamic_executor_urls(user_id)
        
        response = requests.post(
            f"{executor_urls['EXECUTOR_API_BASE_URL']}/file_utils/remove_aux_dataset",
            json={'file_path': file_path, 'user_id': user_id},
            timeout=5
        )
        
        # Update session
        prefs = cache_bp.user_preferences.get(session_id, {})
        
        if file_path in prefs.get('auxiliary_datasets', []):
            prefs['auxiliary_datasets'].remove(file_path)
            cache_bp.user_preferences[session_id] = prefs
            
            bamboo_ai_instance = cache_bp.bamboo_ai_instances.get(session_id)
            if bamboo_ai_instance:
                bamboo_ai_instance.auxiliary_datasets = prefs['auxiliary_datasets']
        
        return jsonify({
            'success': True, 
            'message': 'Auxiliary dataset removed',
            'aux_count': len(prefs.get('auxiliary_datasets', []))
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500