import os
import time
import requests
from datetime import datetime
from flask import Blueprint, request, jsonify, session
from auth import requires_auth
import gc

# Create the blueprint
container_status_bp = Blueprint('container_status', __name__)

def init_container_status_integration(app, **dependencies):
    """Initialize container status integration with the main app and dependencies"""
    # Store dependencies for use in routes
    container_status_bp.user_preferences = dependencies['user_preferences']
    container_status_bp.bamboo_ai_instances = dependencies['bamboo_ai_instances']
    container_status_bp.get_user_id = dependencies['get_user_id']
    container_status_bp.get_bamboo_ai = dependencies['get_bamboo_ai']
    container_status_bp.cleanup_and_remove_bamboo_instance = dependencies['cleanup_and_remove_bamboo_instance']
    container_status_bp.get_dynamic_executor_urls = dependencies['get_dynamic_executor_urls']
    container_status_bp.logger = dependencies['logger']
    container_status_bp.container_orchestrator = dependencies['container_orchestrator']
    container_status_bp.get_user_compute_tier = dependencies['get_user_compute_tier']
    
    # Register the blueprint
    app.register_blueprint(container_status_bp)

def _managed_container():
    """The executor container `bambooai serve` started, if any (its name), else None."""
    return os.getenv('BAMBOO_EXECUTOR_CONTAINER') or None


def _container_started_at(name: str):
    """Docker's start time of the container: changes on every restart, which is what the page waits for."""
    try:
        import subprocess
        r = subprocess.run(['docker', 'inspect', '-f', '{{.State.StartedAt}}', name], capture_output=True, text=True, timeout=10)
        return r.stdout.strip() or None if r.returncode == 0 else None
    except Exception:                                            # noqa: BLE001
        return None


def _direct_executor_status(base_url: str) -> dict:
    """One executor named in .env (a docker run of the image): its own /health is the status."""
    try:
        import requests
        r = requests.get(f"{base_url}/health", timeout=3)
        if r.ok:
            info = r.json() if r.headers.get('content-type', '').startswith('application/json') else {}
            out = {'status': 'ready', 'tier': 'docker', 'url': base_url, 'build': info.get('build')}
            managed = _managed_container()
            if managed:
                out['job_id'] = _container_started_at(managed)    # a new value after a restart, as the orchestrator's job id would be
                out['managed'] = True
            return out
        return {'status': 'failed', 'tier': 'docker', 'url': base_url, 'error': f"health {r.status_code}"}
    except Exception as e:                                       # noqa: BLE001
        return {'status': 'failed', 'tier': 'docker', 'url': base_url, 'error': str(e)}


@container_status_bp.route('/api/container/status', methods=['GET'])
@requires_auth
def get_container_status():
    """Get container status for current user via orchestrator"""
    try:
        user_id = container_status_bp.get_user_id()

        # the compute seam (docs/OSS_DESIGN.md D5): no executor in local mode; a direct executor answers for itself
        mode = os.getenv('EXECUTION_MODE', 'api')
        direct = (os.getenv('EXECUTOR_API_BASE_URL') or '').rstrip('/')
        if mode == 'local':
            return jsonify({'status': 'ready', 'tier': 'local', 'user_id': user_id}), 200
        if direct:
            return jsonify(dict(_direct_executor_status(direct), user_id=user_id)), 200
        if container_status_bp.container_orchestrator is None:
            return jsonify({'status': 'offline', 'tier': 'none', 'user_id': user_id, 'error': 'no executor: set EXECUTION_MODE=local or EXECUTOR_API_BASE_URL'}), 200
        
        # Use the centralized orchestrator client
        status_data = container_status_bp.container_orchestrator.get_container_status(user_id)
        
        return jsonify(status_data), 200
            
    except Exception as e:
        container_status_bp.logger.error(f"Container status check failed: {str(e)}")
        return jsonify({
            'status': 'offline', 
            'error': str(e)
        }), 200

def _restart_managed_container(name: str):
    """The container `bambooai serve` started: docker restart, the session's uploads forgotten (they lived in
    the container), the instance removed so the next request builds a fresh one against the fresh executor."""
    import subprocess
    session_id = session.get('session_id')
    if session_id in container_status_bp.bamboo_ai_instances:
        container_status_bp.bamboo_ai_instances[session_id].kill_signal = True
        time.sleep(0.5)
    r = subprocess.run(['docker', 'restart', '-t', '10', name], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        return jsonify({'success': False, 'message': f'docker restart failed: {r.stderr.strip()[-300:]}'}), 200
    prefs = container_status_bp.user_preferences.get(session_id)
    if prefs:
        prefs['auxiliary_datasets'] = []
        prefs['ontology_path'] = None
        prefs['df_id'] = None
    try:
        container_status_bp.cleanup_and_remove_bamboo_instance(session_id)
    except Exception as e:                                        # noqa: BLE001
        container_status_bp.logger.warning(f"instance cleanup after the executor restart: {e}")
    container_status_bp.logger.info(f"Executor container {name} restarted for session {session_id}")
    return jsonify({'success': True, 'status': 'success', 'message': 'Executor restarted'}), 200


@container_status_bp.route('/api/container/restart', methods=['POST'])
@requires_auth
def restart_container():
    """Restart container for current user via orchestrator"""
    try:
        managed = _managed_container()
        if managed and os.getenv('EXECUTOR_API_BASE_URL'):
            return _restart_managed_container(managed)
        if os.getenv('EXECUTION_MODE', 'api') == 'local' or os.getenv('EXECUTOR_API_BASE_URL'):
            return jsonify({'success': False, 'message': 'No container to restart in this edition: the kernel runs here, or the executor is the one named in .env'}), 200
        session_id = session.get('session_id')
        user_id = container_status_bp.get_user_id()

        user_compute_tier = container_status_bp.get_user_compute_tier(user_id)
        
        # Step 1: Send kill signal to the BambooAI instance
        if session_id in container_status_bp.bamboo_ai_instances:
            instance = container_status_bp.bamboo_ai_instances[session_id]
            instance.kill_signal = True
            
            # Optional: Log the kill signal
            container_status_bp.logger.info(f"Kill signal sent to BambooAI instance for session {session_id}")
            
            # Give the instance a moment to recognize the kill signal
            # This is crucial to allow running threads to exit cleanly
            import time
            time.sleep(0.5)  # 500ms should be enough for most operations to check the flag
        
        # Step 2: Restart the container via orchestrator
        result = container_status_bp.container_orchestrator.restart_container(user_id, user_compute_tier)
        
        # Step 3: Handle session cleanup only if restart was successful
        if result.get('status') == 'success':
            # Clear any uploads from user preferences
            prefs = container_status_bp.user_preferences.get(session_id)
            if prefs:
                prefs['auxiliary_datasets'] = []
                prefs['ontology_path'] = None
                prefs['df_id'] = None
                
                # Cleanup with timeout protection
                try:
                    # Set a timeout for cleanup operation
                    import threading
                    cleanup_complete = threading.Event()
                    cleanup_error = [None]  # Use list to store error in thread
                    
                    def cleanup_with_timeout():
                        try:
                            container_status_bp.cleanup_and_remove_bamboo_instance(session_id)
                            cleanup_complete.set()
                        except Exception as e:
                            cleanup_error[0] = e
                            cleanup_complete.set()
                    
                    cleanup_thread = threading.Thread(target=cleanup_with_timeout)
                    cleanup_thread.start()
                    
                    # Wait max 3 seconds for cleanup
                    if not cleanup_complete.wait(timeout=3.0):
                        container_status_bp.logger.warning(
                            f"Cleanup timeout for session {session_id}, proceeding anyway"
                        )
                    elif cleanup_error[0]:
                        container_status_bp.logger.error(
                            f"Error during cleanup for session {session_id}: {cleanup_error[0]}"
                        )
                    
                except Exception as e:
                    container_status_bp.logger.error(
                        f"Failed to cleanup BambooAI instance for session {session_id}: {e}"
                    )
                    # Continue anyway - don't fail the restart because of cleanup issues

                # Update preferences
                container_status_bp.user_preferences[session_id] = prefs
                
                # Create new instance
                try:
                    container_status_bp.bamboo_ai_instances[session_id] = container_status_bp.get_bamboo_ai(session_id)
                    container_status_bp.logger.info(
                        f"New BambooAI instance created for session {session_id}"
                    )
                except Exception as e:
                    container_status_bp.logger.error(
                        f"Failed to create new BambooAI instance: {e}"
                    )
                    # Return partial success - container restarted but instance creation failed
                    return jsonify({
                        'status': 'partial_success',
                        'message': 'Container restarted but instance creation failed',
                        'error': str(e)
                    }), 207  # 207 Multi-Status

            return jsonify(result), 200
        else:
            # Return error response
            status_code = 500 if result.get('status') == 'error' else 200
            return jsonify(result), status_code
            
    except Exception as e:
        container_status_bp.logger.error(f"Container restart failed for user {user_id}: {str(e)}")
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500