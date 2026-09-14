import argparse
import re
import os
import time
import gc
import sys
import shutil
import json
import requests
import threading
import uuid
import glob
import pandas as pd
from datetime import datetime, timedelta
from queue import Queue, Empty
from flask import Flask, request, jsonify, Response, render_template, session, send_from_directory, redirect, url_for
import tempfile
from dotenv import load_dotenv
from google.cloud import storage
from werkzeug.datastructures import FileStorage
from werkzeug.exceptions import abort



from auth import requires_auth, get_current_user_id, init_auth
from auth.supabase_client import get_user_llm_config, get_user_subscription, increment_queries_counter, can_execute_chain, get_user_compute_tier, remove_label_from_chain
from llm_config_builder import build_user_config, needs_rebuild
from chain_replay_utils import get_python_code_from_chain, replace_dataset_paths
from cleanup import ensure_user_directories, cleanup_user_on_auth, cleanup_threads_for_user, clear_datasets_folder_for_user, cleanup_old_user_sessions, cleanup_and_remove_bamboo_instance
from container_status_routes import init_container_status_integration
from integrations.sweatstack import init_sweatstack_integration
from integrations.intervals import init_intervals_integration
from integrations.endura import init_endura_integration
from integrations.cache_manager import init_cache_integration

# Add orchestration path
sys.path.append('/home/data/bambooai')
from orchestration import ContainerOrchestrator

# Blueprints
from llm_config_routes import llm_config_bp
from usage_tracking_routes import usage_tracking_bp
from subscription_routes import subscription_bp
from labels_routes import labels_bp
from agent_instructions_routes import agent_instructions_bp
from replay_routes import replay_bp
from dataframe_routes import dataframe_bp

# Logs
from logger_config import setup_logging, get_logger
setup_logging()
logger = get_logger(__name__)

def get_user_id():
    """Get current user ID dynamically based on auth mode - file system safe version"""
    
    try:
        user_id = get_current_user_id()  # This gets the full Auth0 ID
        
        # Extract numeric part after pipe for file system safety
        if '|' in user_id:
            return user_id.split('|')[1]  # Return just "110366262980475577308"
        
        return user_id
        
    except RuntimeError:
        return logger.warning("Failed to get user ID")

def user_path(root, *paths):
    """Helper to build a user-specific path using dynamic user ID."""
    user_id = get_user_id()
    return os.path.join(root, user_id, *paths)


def cleanup_threads(debug_mode=False):
    """Clean up threads for the current user - wrapper for backward compatibility"""
    user_id = get_user_id()
    cleanup_threads_for_user(user_id, debug_mode)

def clear_datasets_folder():
    """Clear datasets folder for the current user - wrapper for backward compatibility"""
    user_id = get_user_id()
    clear_datasets_folder_for_user(user_id)

# Load environment variables from .env file
load_dotenv()

# Try importing bambooai directly (pip installed case)
try:
    from bambooai import BambooAI
    from bambooai import utils
    from bambooai import executor_client
except ImportError:
    # If direct import fails, try adding the local path (cloned repo case)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    bamboo_ai_path = os.path.abspath(os.path.join(current_dir, '..'))
    
    if os.path.exists(bamboo_ai_path):
        sys.path.insert(0, bamboo_ai_path)
        from bambooai import BambooAI
        from bambooai import utils
        from bambooai import executor_client
    else:
        raise ImportError("Could not find bambooai package. Please either install via pip or ensure you're running from the correct directory in the cloned repository.")

# Dynamic orchestration configuration
APP_PORT = int(os.getenv('APP_PORT', 5001))
ORCHESTRATOR_API_URL = os.getenv('ORCHESTRATOR_API_URL', 'http://localhost:8080')
# The compute seam (docs/OSS_DESIGN.md D5, D27; 2026-09-14). EXECUTION_MODE:
#   api   - an executor container: through the orchestrator (the hosted edition), or, with
#           EXECUTOR_API_BASE_URL set, that one executor directly (a `docker run` of the image);
#   local - the kernel in a subprocess on this machine, no executor (the self-hosted default).
GLOBAL_EXECUTION_MODE = os.getenv('EXECUTION_MODE', 'api')
DIRECT_EXECUTOR_URL = (os.getenv('EXECUTOR_API_BASE_URL') or '').rstrip('/') or None

# SSL Configuration
SSL_ENABLED = os.getenv('SSL_ENABLED', 'false').lower() == 'true'
SSL_CERT_PATH = os.getenv('SSL_CERT_PATH')
SSL_KEY_PATH = os.getenv('SSL_KEY_PATH')

# Initialize container orchestrator
container_orchestrator = ContainerOrchestrator(ORCHESTRATOR_API_URL)

def _executor_urls(base_url: str) -> dict:
    return {
        'EXECUTOR_API_BASE_URL': base_url,
        'EXECUTOR_API_UPLOAD_URL': f"{base_url}/upload_dataset",
        'EXECUTOR_API_UPLOAD_AUX_URL': f"{base_url}/file_utils/upload_aux_dataset",
        'EXECUTOR_API_REMOVE_AUX_URL': f"{base_url}/file_utils/remove_aux_dataset",
        'EXECUTOR_API_DOWNLOAD_GENERATED_URL': f"{base_url}/download_generated_dataset"
    }


def executor_base_url(user_id: str):
    """The executor this user's instance talks to: None in local mode (the kernel runs here)."""
    urls = get_dynamic_executor_urls(user_id)
    return urls['EXECUTOR_API_BASE_URL'] if urls else None


def get_dynamic_executor_urls(user_id: str) -> dict:
    """Get dynamic executor URLs for a specific user"""
    if GLOBAL_EXECUTION_MODE == 'local':
        return None                                   # no executor: the kernel runs in a subprocess here
    if DIRECT_EXECUTOR_URL:
        return _executor_urls(DIRECT_EXECUTOR_URL)    # one executor, named in .env, no orchestrator
    try:
        user_compute_tier = get_user_compute_tier(user_id)

        container_info = container_orchestrator.get_or_create_container(user_id, user_compute_tier)
        
        if container_info["status"] == "ready":
            base_url = f"http://{container_info['ip']}:{container_info['port']}"
            return {
                'EXECUTOR_API_BASE_URL': base_url,
                'EXECUTOR_API_UPLOAD_URL': f"{base_url}/upload_dataset",
                'EXECUTOR_API_UPLOAD_AUX_URL': f"{base_url}/file_utils/upload_aux_dataset",
                'EXECUTOR_API_REMOVE_AUX_URL': f"{base_url}/file_utils/remove_aux_dataset",
                'EXECUTOR_API_DOWNLOAD_GENERATED_URL': f"{base_url}/download_generated_dataset"
            }
        else:
            logger.error(f"Failed to get container for user {user_id}")
            return None
    except Exception as e:
        logger.error(f"Error getting dynamic URLs for user {user_id}: {str(e)}")
        return None

# Dynamicaly set the remote executor url
def get_executor_client(user_id: str):
    """Get executor client for specific user"""
    executor_urls = get_dynamic_executor_urls(user_id)
    if executor_urls:
        from bambooai import executor_client
        return executor_client.ExecutorAPIClient(base_url=executor_urls['EXECUTOR_API_BASE_URL'])
    else:
        return None
    
def update_user_activity(user_id: str):
    """Update user activity in orchestrator"""
    try:
        if ORCHESTRATOR_API_URL and GLOBAL_EXECUTION_MODE == 'api' and not DIRECT_EXECUTOR_URL:   # only the orchestrated path has an idle reaper
            response = requests.post(
                f"{ORCHESTRATOR_API_URL}/activity/{user_id}", 
                timeout=3
            )
            if response.status_code == 200:
                logger.debug(f"Updated activity for user {user_id}")
    except Exception as e:
        # Don't break the request if activity tracking fails
        logger.debug(f"Activity tracking failed for user {user_id}: {e}")

# Seconds of silence on a streaming response before a newline is sent. Well
# under nginx's proxy_read_timeout, so a working run never looks like a dead
# one. Purely a keepalive: the client ignores blank lines.
STREAM_HEARTBEAT_SECONDS = float(os.getenv("STREAM_HEARTBEAT_SECONDS", "15"))

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET')
# Two instances on one host (a hosted service and a self-hosted test on another port, 2026-09-14) share a
# browser's cookies, since cookies are per hostname: give each its own session cookie name in .env.
app.config['SESSION_COOKIE_NAME'] = os.getenv('SESSION_COOKIE_NAME', 'session')

# Register the blueprints
app.register_blueprint(llm_config_bp)
app.register_blueprint(usage_tracking_bp)
app.register_blueprint(subscription_bp)
app.register_blueprint(labels_bp)
app.register_blueprint(agent_instructions_bp)
app.register_blueprint(dataframe_bp)
app.register_blueprint(replay_bp)

# Initialize authentication
init_auth(app)

# Dictionary to store BambooAI instances for each session
bamboo_ai_instances = {}

# Dictionary to store user preferences for each session
user_preferences = {}

# Track user sessions
user_session_mapping = {}  # Key: user_id, Value: current_session_id

# BambooAI parameters
EXPLORATORY = True
SEARCH_TOOL = True
WEBUI = True

# Workspace memory is ALWAYS ON at a fixed per-user path - no UI lever, no
# preference, no opt-in. Layout: memory/<user_id>/memory_pack.yaml. An
# absent file is a silent cold start; the pack grows through the write
# path (step 23) or by placing a YAML at the path the startup log names.
#
# Anchoring: the app package directory (dirname(__file__)), NOT the
# process CWD - services chdir wherever their unit says (this deployment
# runs from orchestration/), so CWD is not deterministic, while the app
# dir is. It is often read-only to the service user, so the root needs a
# one-time provisioning exactly like temp/ received:
#     mkdir memory && chown/chmod --reference=temp memory
# or set BAMBOO_MEMORY_DIR to any writable location instead.
MEMORY_DIR = os.environ.get('BAMBOO_MEMORY_DIR') or os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'memory')
try:
    os.makedirs(MEMORY_DIR, exist_ok=True)
    logger.info(f"Memory root: {MEMORY_DIR}")
except Exception as _e:                                        # noqa: BLE001
    logger.error(f"Cannot create memory root {MEMORY_DIR}: {_e}. Memory "
                 f"stays cold until you either pre-provision that directory "
                 f"for the service user or set BAMBOO_MEMORY_DIR.")

def user_memory_path():
    """The canonical memory pack path for the current user:
    MEMORY_DIR/<user_id>/memory_pack.yaml (per-user subdir, house style)."""
    user_dir = os.path.join(MEMORY_DIR, get_user_id())
    try:
        os.makedirs(user_dir, exist_ok=True)
    except Exception:                                          # noqa: BLE001
        pass  # read path cold-starts; the per-run log names the path
    return os.path.join(user_dir, 'memory_pack.yaml')

# Initialize SweatStack integration
init_sweatstack_integration(app, 
    user_preferences=user_preferences,
    bamboo_ai_instances=bamboo_ai_instances,
    get_user_id=get_user_id,
    get_bamboo_ai=lambda session_id: get_bamboo_ai(session_id),
    get_dynamic_executor_urls=lambda user_id: get_dynamic_executor_urls(user_id),
    global_execution_mode=GLOBAL_EXECUTION_MODE,
    logger=logger,
    EXPLORATORY=EXPLORATORY,
    SEARCH_TOOL=SEARCH_TOOL,
    WEBUI=WEBUI,
    utils=utils,
    executor_client=executor_client 
)

# Initialize Intervals.icu integration
init_intervals_integration(app, 
    user_preferences=user_preferences,
    bamboo_ai_instances=bamboo_ai_instances,
    get_user_id=get_user_id,
    get_bamboo_ai=lambda session_id: get_bamboo_ai(session_id),
    get_dynamic_executor_urls=lambda user_id: get_dynamic_executor_urls(user_id),
    global_execution_mode=GLOBAL_EXECUTION_MODE,
    logger=logger,
    EXPLORATORY=EXPLORATORY,
    SEARCH_TOOL=SEARCH_TOOL,
    WEBUI=WEBUI,
    utils=utils,
    executor_client=executor_client 
)

# Initialize Endura integration
init_endura_integration(app, 
    user_preferences=user_preferences,
    bamboo_ai_instances=bamboo_ai_instances,
    get_user_id=get_user_id,
    get_bamboo_ai=lambda session_id: get_bamboo_ai(session_id),
    get_dynamic_executor_urls=lambda user_id: get_dynamic_executor_urls(user_id),
    global_execution_mode=GLOBAL_EXECUTION_MODE,
    logger=logger,
    EXPLORATORY=EXPLORATORY,
    SEARCH_TOOL=SEARCH_TOOL,
    WEBUI=WEBUI,
    utils=utils,
    executor_client=executor_client 
)

# Initialize container status
init_container_status_integration(app,
    user_preferences=user_preferences,
    bamboo_ai_instances=bamboo_ai_instances,
    get_user_id=get_user_id,
    get_bamboo_ai=lambda session_id: get_bamboo_ai(session_id),
    cleanup_and_remove_bamboo_instance=lambda session_id: cleanup_and_remove_bamboo_instance(session_id, bamboo_ai_instances),
    get_dynamic_executor_urls=get_dynamic_executor_urls,
    container_orchestrator=container_orchestrator,
    logger=logger,
    get_user_compute_tier=get_user_compute_tier
)

# Initialize Cache management integration
init_cache_integration(app,
    get_user_id=get_user_id,
    get_dynamic_executor_urls=lambda user_id: get_dynamic_executor_urls(user_id),
    logger=logger,
    user_preferences=user_preferences,
    bamboo_ai_instances=bamboo_ai_instances,
    get_bamboo_ai=lambda session_id: get_bamboo_ai(session_id),
    utils=utils,
    executor_client=executor_client
)

# Function to generate a unique DataFrame ID
def generate_dataframe_id() -> str:
    df_id = str(uuid.uuid4())
    return df_id

def get_bamboo_ai(session_id, df=None):
    """Factory function to create or retrieve BambooAI instances"""
    prefs = user_preferences.get(session_id, {'planning': False, 'auxiliary_datasets': [], 'df_id': None})
    
    # Get API keys for this session
    api_keys = {} # This is a placeholder, for possible future use if we want to pass specific user API keys to BambooAI
    user_id = get_user_id()
    
    # Create new BambooAI instance if it doesn't exist or if executor URL has changed (None in local mode)
    base_url = executor_base_url(user_id)
    if session_id not in bamboo_ai_instances or bamboo_ai_instances[session_id].executor_api_url != base_url:
        logger.info(f"Creating new BambooAI instance for session {session_id}, user {user_id}. Reason: {'new instance' if session_id not in bamboo_ai_instances else 'executor URL changed'}")
        
        # Clean up stale instance if it exists
        if session_id in bamboo_ai_instances:
            cleanup_and_remove_bamboo_instance(session_id, bamboo_ai_instances)

        bamboo_ai_instances[session_id] = BambooAI(
            df=df,
            user_id=get_user_id(),
            exploratory=EXPLORATORY,
            planning=prefs['planning'],
            search_tool=SEARCH_TOOL,
            webui=WEBUI,
            memory_path=user_memory_path(),  # always-on workspace memory
            df_id=prefs['df_id'],
            auxiliary_datasets=prefs['auxiliary_datasets'],
            api_keys=api_keys,
            executor_api_url=base_url,
            execution_mode=GLOBAL_EXECUTION_MODE
        )

    return bamboo_ai_instances[session_id]

def get_user_model_preference_for_session(session_id):
    """Get the user's model preference for the current session"""
    
    try:
        # Get the full Auth0 user ID for database operations
        auth0_user_id = get_current_user_id()
        
        if not auth0_user_id:
            return 'free'
        
        # Get user's model preference from database
        model_preference = get_user_llm_config(auth0_user_id)
        
        return model_preference
        
    except Exception as e:
        logger.error(f"Error retrieving model preference for session {session_id}: {str(e)}")
        return 'free'

def load_csv_with_datetime(file_path):
    # Read the CSV file
    df = pd.read_csv(file_path)

    # Function to parse datetime and remove timezone
    def parse_and_remove_tz(series):
        return pd.to_datetime(series, format='%Y-%m-%d %H:%M:%S%z', utc=True).dt.tz_localize(None)

    # Iterate through columns and apply vectorized parsing where appropriate
    for col in df.columns:
        if df[col].dtype == 'object':
            # Try to parse the column as datetime
            try:
                df[col] = parse_and_remove_tz(df[col])
            except ValueError:
                # If parsing fails, leave the column as is
                pass

    return df

def load_excel_with_datetime(file_path):
    # Read the Excel file (first sheet)
    df = pd.read_excel(file_path, engine='openpyxl')

    # Function to parse datetime and remove timezone
    def parse_and_remove_tz(series):
        return pd.to_datetime(series, format='%Y-%m-%d %H:%M:%S%z', utc=True).dt.tz_localize(None)

    # Iterate through columns and apply parsing where appropriate
    for col in df.columns:
        # Case 1: Already parsed as datetime (Excel often auto-converts)
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            try:
                df[col] = parse_and_remove_tz(df[col])
            except (ValueError, TypeError):
                pass
        # Case 2: String columns that may contain datetime values
        elif df[col].dtype == 'object':
            try:
                df[col] = parse_and_remove_tz(df[col])
            except (ValueError, TypeError):
                pass

    return df

# This is temporary, used for testing of .parquet datasets. Will be replaced with a more robust solution.
def load_parquet_with_datetime(file_path):
    # Read the Parquet file
    df = pd.read_parquet(file_path)

    # Function to parse datetime and remove timezone
    def parse_and_remove_tz(series):
        return pd.to_datetime(series, format='%Y-%m-%d %H:%M:%S%z', utc=True).dt.tz_localize(None)

    # Iterate through columns and apply vectorized parsing where appropriate
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            # Try to parse the column as datetime
            try:
                df[col] = parse_and_remove_tz(df[col])
            except ValueError:
                # If parsing fails, leave the column as is
                pass

    return df

def load_json_with_datetime(file_path):
    # Read the JSON file
    df = pd.read_json(file_path)

    # Function to parse datetime and remove timezone
    def parse_and_remove_tz(series):
        return pd.to_datetime(series, format='%Y-%m-%d %H:%M:%S%z', utc=True).dt.tz_localize(None)

    # Iterate through columns and apply parsing where appropriate
    for col in df.columns:
        # Case 1: Already parsed as datetime (e.g. from epoch timestamps)
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            try:
                df[col] = parse_and_remove_tz(df[col])
            except (ValueError, TypeError):
                pass
        # Case 2: String columns that may contain datetime values
        elif df[col].dtype == 'object':
            try:
                df[col] = parse_and_remove_tz(df[col])
            except (ValueError, TypeError):
                pass

    return df

def load_dataframe_to_bamboo_ai_instance(session_id, df=None, file=None, execution_mode='local'):
    new_df_id = generate_dataframe_id()
    prefs = user_preferences.get(session_id, {'planning': False, 'auxiliary_datasets': []})
    prefs['df_id'] = new_df_id
    user_preferences[session_id] = prefs

    if execution_mode == 'api':
        if not file:
            raise ValueError("File is required for API execution mode")
        try:
            file.seek(0)
            files = {'file': (file.filename, file, file.content_type)}
            executor_response = requests.post(
                get_dynamic_executor_urls(get_user_id())['EXECUTOR_API_UPLOAD_URL'],
                files=files,
                data={'df_id': new_df_id}
            )
            executor_response.raise_for_status()
            df = None
        except requests.RequestException as e:
            raise Exception(f'Error uploading to executor: {str(e)}')
    else:
        if df is None:
            raise ValueError("DataFrame is required for local execution mode")
        
    # Always recreate to ensure all parameters are properly initialized
    #cleanup_and_remove_bamboo_instance(session_id, bamboo_ai_instances)
    
    # Create new BambooAI instance if necessary, otherwise update existing one
    bamboo_ai_instances[session_id] = get_bamboo_ai(session_id, df=df)
    
    # Update the df_id in the BambooAI instance in case it was not recreated
    bamboo_ai_instances[session_id].df_id = prefs.get('df_id')
    if df is not None:                                # local mode: the frame lives in the instance, not in an executor
        bamboo_ai_instances[session_id].df = df
    # the analyst sees the file's name in its DATA header (2026-09-07): identity from the file, not a web search
    try:
        bamboo_ai_instances[session_id].df_name = getattr(file, 'filename', None) or getattr(df, 'attrs', {}).get('name') or ''
    except Exception:                                   # noqa: BLE001
        pass

    # the Data tab (2026-09-07): the first page for the grid; the 100-row HTML preview only if no page could be made
    page = _dataframe_first_page(df, execution_mode, new_df_id, get_executor_client(get_user_id()))
    if page is not None:
        df_json = json.dumps({'type': 'dataframe', 'data': page})
    else:
        df_index = utils.computeDataframeSample(
            df=df,
            execution_mode=execution_mode,
            df_id=new_df_id,
            executor_client=get_executor_client(get_user_id()))
        df_html = df_index.to_html(classes='dataframe', border=0, index=False)
        df_json = json.dumps({'type': 'dataframe', 'data': df_html})

    return df_json, new_df_id

def _dataframe_first_page(df, execution_mode, df_id, executor_client):
    """The Data tab's first page (2026-09-07), from the executor in api mode or the frame locally; None if unavailable."""
    try:
        if execution_mode == 'api' and executor_client is not None and df_id:
            page = executor_client.dataframe_page(df_id, 0, 50)
        elif df is not None:
            page = utils.page_frame(df, 0, 50)
        else:
            page = None
        if page:
            page['df_id'] = df_id
            return page
        if execution_mode == 'api':
            logger.warning("Data tab: the executor returned no page for %s (an image before 2026-09-07 has no /dataframe_page) - showing the 100-row preview", df_id)
    except Exception as exc:                                # noqa: BLE001
        logger.warning("Data tab: page request failed (%s) - showing the 100-row preview", exc)
    return None


def _aux_first_page(path, execution_mode, executor_client):
    """The Data tab's first page of an auxiliary file (2026-09-08): from the executor in api mode, read locally otherwise; None if unavailable."""
    try:
        if execution_mode == 'api' and executor_client is not None:
            page = executor_client.aux_page(path, 0, 50)
            if not page:
                logger.warning("Data tab: the executor returned no page for the auxiliary file %s (an image before 2026-09-08 has no /aux_page) - showing the 100-row preview", path)
            return page or None
        return utils.aux_page(path, 0, 50)
    except Exception as exc:                                # noqa: BLE001
        logger.warning("Data tab: auxiliary page failed (%s) - showing the 100-row preview", exc)
        return None


def start_new_conversation(session_id):
    # Clear the Datasets folder first
    clear_datasets_folder()

    prefs = user_preferences.get(session_id, {
        'planning': False, 
        'auxiliary_datasets': [],
        'df_id': None
    })
    
    # Clear datasets user_preferences for the current session
    prefs['auxiliary_datasets'] = []
    prefs['df_id'] = None
    
    # Workspace memory is untouched here by design: it is always-on at a
    # fixed path (user_memory_path) and survives conversations, dataset
    # switches, and restarts. See memory_pack_design.md.
    
    user_preferences[session_id] = prefs
    
    # Always recreate to ensure all parameters are properly initialized
    cleanup_and_remove_bamboo_instance(session_id, bamboo_ai_instances)

    bamboo_ai_instances[session_id] = get_bamboo_ai(session_id, df=None)

    bamboo_ai_instances[session_id].pd_agent_converse(action='reset')
    logger.info(f"BambooAI instance reset for session {session_id}, auxiliary datasets list cleared and Datasets folder content cleared.")
    
    return jsonify({"message": "New conversation started"}), 200

@app.route('/api/auth/logout', methods=['POST'])
@requires_auth
def logout_user():
    """Clean up server-side state when user logs out"""
    try:
        user_id = get_user_id()
        current_session_id = session.get('session_id')
        
        logger.info(f"User {user_id} logging out, cleaning up session {current_session_id}")
        
        # Clean up all session-based data for current session
        if current_session_id:
            bamboo_ai_instances.pop(current_session_id, None)
            user_preferences.pop(current_session_id, None)
            logger.info(f"Cleaned up session data for {current_session_id}")
        
        # Clean up user mapping
        if user_id in user_session_mapping:
            old_session = user_session_mapping[user_id]
            if old_session == current_session_id:
                del user_session_mapping[user_id]
                logger.info(f"Removed user mapping for {user_id}")
        
        # Clear Flask session
        session.clear()
        
        logger.info(f"Successfully cleaned up logout for user {user_id}")
        return jsonify({'message': 'Logout cleanup successful'}), 200
        
    except Exception as e:
        logger.error(f"Error during logout cleanup: {str(e)}")
        return jsonify({'error': 'Logout cleanup failed'}), 500

@app.route('/api/user/initialize', methods=['POST'])
@requires_auth
def initialize_user_session():
    """Initialize user directories and cleanup when user authenticates"""
    try:
        user_id = get_user_id()
        current_session_id = session.get('session_id')

        # Clean up any old sessions for this user
        if current_session_id:
            cleanup_old_user_sessions(
                user_id, 
                current_session_id, 
                user_session_mapping,
                bamboo_ai_instances, 
                user_preferences, 
            )
        
        # Set preferences for the current session if not already set
        if current_session_id not in user_preferences:
            user_preferences[current_session_id] = {
                'planning': False,
                'auxiliary_datasets': [],
                'df_id': None
            }
        
        # Build user config if needed
        try:
            user_id = get_user_id()
            if user_id and os.path.exists("LLM_CONFIG_template.json") and needs_rebuild(user_id):
                # Try to get auth0_id, but don't fail if unavailable
                try:
                    auth0_id = get_current_user_id()
                except RuntimeError as e:
                    logger.warning(f"Failed to get full auth0_id for user {user_id}: {e}")
                    auth0_id = None
                
                # Get model preference
                model_preference = get_user_model_preference_for_session(current_session_id)
                
                # Get subscription only if we have auth0_id
                subscription_data = {}
                if auth0_id:
                    subscription_result = get_user_subscription(auth0_id)
                    subscription_data = subscription_result.get('data', {}) if subscription_result.get('ok') else {}
                else:
                    logger.info(f"No auth0_id available for user {user_id}, using default free tier config")
                
                # Build config (will use free tier as fallback if subscription_data is empty)
                build_user_config(
                    user_id, 
                    subscription_data=subscription_data, 
                    model_preference=model_preference, 
                    force_rebuild=True
                )
                logger.info(f"Config for user {user_id} built successfully")

        except Exception as e:
            logger.error(f"Config build error: {str(e)}")
        
        # Create all directories
        ensure_user_directories(user_id)
        
        # Run cleanup of user directories
        cleanup_user_on_auth(user_id)
        
        # Get SweatStack status for authenticated user
        sweatstack_payload = {} 
        if hasattr(app, 'get_sweatstack_context'):
            try:
                full_sweatstack_context = app.get_sweatstack_context()

                sweatstack_payload = {
                    'sweatstack_enabled': full_sweatstack_context.get('sweatstack_enabled', False),
                    'sweatstack_authenticated': full_sweatstack_context.get('sweatstack_authenticated', False)
                }
            except Exception as e:
                logger.error(f"Error getting SweatStack context: {str(e)}")
                sweatstack_payload = {
                    'sweatstack_enabled': False,
                    'sweatstack_authenticated': False
                }
        
        # Get Intervals ICU status
        intervals_payload = {}
        if hasattr(app, 'get_intervals_context'):
            try:
                # Import the function here to avoid circular imports
                from auth.supabase_client import get_intervals_integration_status
                
                auth0_id = get_current_user_id()
                
                # Check if user has API key in database
                has_api_key = False
                if auth0_id:
                    bamboo_user_id = auth0_id.split('|')[1] if '|' in auth0_id else auth0_id
                    status = get_intervals_integration_status(bamboo_user_id, auth0_id)
                    has_api_key = status.get('has_api_key', False)
                
                intervals_payload = {
                    'intervals_enabled': has_api_key,  # Only enabled if user has API key
                    'intervals_authenticated': has_api_key
                }
                
            except Exception as e:
                logger.error(f"Error getting Intervals context: {str(e)}")
                intervals_payload = {
                    'intervals_enabled': False,
                    'intervals_authenticated': False
                }
        
        # Get Endura status
        endura_payload = {}
        if hasattr(app, 'get_endura_context'):
            try:
                # Import the function here to avoid circular imports
                from auth.supabase_client import get_endura_integration_status
                
                auth0_id = get_current_user_id()
                
                # Check if user has API key in database
                has_api_key = False
                if auth0_id:
                    bamboo_user_id = auth0_id.split('|')[1] if '|' in auth0_id else auth0_id
                    status = get_endura_integration_status(bamboo_user_id, auth0_id)
                    has_api_key = status.get('has_api_key', False)
                
                endura_payload = {
                    'endura_enabled': has_api_key,  # Only enabled if user has API key
                    'endura_authenticated': has_api_key
                }
                
            except Exception as e:
                logger.error(f"Error getting Endura context: {str(e)}")
                endura_payload = {
                    'endura_enabled': False,
                    'endura_authenticated': False
                }
        
        logger.info(f"User session initialized for: {user_id}")

        return jsonify({
            'status': 'success', 
            'user_id': user_id,
            'sweatstack': sweatstack_payload,
            'intervals': intervals_payload,
            'endura': endura_payload
        }), 200
        
    except Exception as e:
        logger.error(f"Failed to initialize user session: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.before_request
def ensure_session_and_security():
    """Simple session handling and security filtering. KEEP IT LIGHT!"""
    # Session handling (existing code)
    if 'session_id' not in session:
        session_id = str(uuid.uuid4())
        session['session_id'] = session_id
    
    # Security filtering - only check if there's a query string
    if request.query_string:
        qs = request.query_string.decode('utf-8', errors='ignore').lower()
        
        # Quick checks for obvious attacks
        # Using 'in' is faster than regex for simple patterns
        dangerous_patterns = [
            # Command injection (Linux-focused but keep Windows too)
            'wget ', 'curl ', 'bash ', ' sh ', 'chmod ', 'exec(',
            'passwd', 'sudo ', 'eval(', 'perl ', ' nc ', 'netcat',
            '/bin/', '/usr/bin/', 'cmd.exe', 'powershell',  # Keep Windows ones - attackers try them anyway
            
            # SQL Injection (platform-agnostic - keep as is)
            'union select', 'select * from', 'drop table', 'insert into',
            'delete from', 'update ', 'or 1=1', 'or true', "' or '",
            'waitfor delay', 'benchmark(', 'sleep(',
            
            # Path traversal (adjusted for Linux but keep Windows)
            '../', '..\\', '%2e%2e', '%252e', '..%2f', '..%5c',
            '/etc/passwd', '/etc/shadow', '/proc/self',  # Linux-specific
            '/var/log/', '/.ssh/', '/.bash_history',     # Linux-specific
            'c:\\windows', 'c:\\winnt',  # Keep these - doesn't hurt
            
            # XSS (platform-agnostic - keep as is)
            '<script', 'javascript:', 'onerror=', 'onload=', 'onclick=',
            '<iframe', '<embed', '<object', 'data:text/html',
            
            # PHP/File inclusion
            'php://', 'file://', 'expect://', '.php', '.env',
            
            # Common web shells
            'c99', 'r57', 'shell.php'
        ]
        
        for pattern in dangerous_patterns:
            if pattern in qs:
                logger.warning(f"Blocked suspicious request from {request.remote_addr}: {pattern} in query")
                abort(444)
    
    # Check suspicious headers (lightweight check)
    # Only check the most commonly abused headers
    x_orig_url = request.headers.get('X-Original-URL', '').lower()
    x_rewrite_url = request.headers.get('X-Rewrite-URL', '').lower()
    
    if x_orig_url or x_rewrite_url:
        suspicious_paths = ['admin', 'config', '.env', '.git', 'wp-admin']
        for path in suspicious_paths:
            if path in x_orig_url or path in x_rewrite_url:
                logger.warning(f"Blocked suspicious header from {request.remote_addr}")
                abort(444)
    
    # Block known scanner user agents (optional - remove if too aggressive)
    ua = request.headers.get('User-Agent', '').lower()
    if ua:  # Only check if UA exists
        bad_agents = ['sqlmap', 'nikto', 'nmap', 'masscan', 'zmap']
        if any(agent in ua for agent in bad_agents):
            logger.warning(f"Blocked scanner from {request.remote_addr}: {ua[:50]}")
            abort(444)

@app.route('/')
def index():
    # Get integration contexts
    common_context = {}
    
    # Get SweatStack context if integration is available
    if hasattr(app, 'get_sweatstack_context'):
        common_context.update(app.get_sweatstack_context())
    
    # Get Intervals context if integration is available
    if hasattr(app, 'get_intervals_context'):
        common_context.update(app.get_intervals_context())
    
    # Get Endura context if integration is available
    if hasattr(app, 'get_endura_context'):
        common_context.update(app.get_endura_context())
    
    # Add payment status if present
    payment_status = request.args.get('payment')
    common_context['payment_status'] = payment_status
    
    return render_template('index.html', **common_context)

@app.route('/update_planning', methods=['POST'])
@requires_auth
def update_planning():
    session_id = session.get('session_id')
    data = request.json
    planning_enabled = data.get('planning', False)
    
    if not session_id:
        return jsonify({'error': 'No session ID found'}), 400
    
    prefs = user_preferences.get(session_id, {'planning': False})
    prefs['planning'] = planning_enabled
    user_preferences[session_id] = prefs
    
    if session_id in bamboo_ai_instances:
        current_instance = bamboo_ai_instances[session_id]
        try:
            current_instance.planning = planning_enabled
            logger.info(f"Successfully updated BambooAI instance with planning={planning_enabled}")
        except Exception as e:
            logger.error(f"Failed to update BambooAI instance: {str(e)}")
            return jsonify({'error': 'Failed to update BambooAI instance'}), 500
    
    return jsonify({
        'message': f'Planning parameter updated to {planning_enabled}',
        'current_state': prefs['planning']
    }), 200

@app.route('/get_planning_state', methods=['GET'])
@requires_auth
def get_planning_state():
    session_id = session.get('session_id')
    
    if not session_id:
        return jsonify({'error': 'No session ID found'}), 400
    
    current_state = user_preferences.get(session_id, {}).get('planning', False)
    
    return jsonify({'planning_enabled': current_state})

# Upload primary dataset endpoint
@app.route('/upload', methods=['POST'])
@requires_auth
def upload_file():
    session_id = session['session_id']
    
    if 'file' not in request.files:
        return jsonify({'message': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'message': 'No selected file'}), 400
        
    if file and (file.filename.endswith('.csv') or file.filename.endswith('.parquet') or file.filename.endswith('.json') or file.filename.endswith('.xlsx')):
        filepath = os.path.join(user_path('temp'), f"{session_id}_{file.filename}")
        file.save(filepath)

        try:
            if GLOBAL_EXECUTION_MODE == 'local':
                # Only load DataFrame for local mode
                if file.filename.endswith('.csv'):
                    df = load_csv_with_datetime(filepath)
                elif file.filename.endswith('.json'):
                    df = load_json_with_datetime(filepath)
                elif file.filename.endswith('.xlsx'):
                    df = load_excel_with_datetime(filepath)
                else:  # .parquet
                    df = load_parquet_with_datetime(filepath)
                df_json, new_df_id = load_dataframe_to_bamboo_ai_instance(
                    session_id=session_id,
                    df=df,
                    execution_mode=GLOBAL_EXECUTION_MODE
                )
            else:  # API mode
                # Only pass file for API mode
                with open(filepath, 'rb') as f:
                    file = FileStorage(
                        stream=f,
                        filename=file.filename,
                        content_type='application/octet-stream'
                    )
                    df_json, new_df_id = load_dataframe_to_bamboo_ai_instance(
                        session_id=session_id,
                        file=file,
                        execution_mode=GLOBAL_EXECUTION_MODE
                    )

            return jsonify({
                'message': 'File successfully uploaded and processed',
                'dataframe': df_json,
                'df_id': new_df_id
            }), 200

        except Exception as e:
            return jsonify({'message': str(e)}), 500
        finally:
            os.remove(filepath)
    else:
        return jsonify({'message': 'Invalid file type'}), 400
    
# Remove primary dataset endpoint
@app.route('/remove_primary_dataset', methods=['POST'])
@requires_auth
def remove_primary_dataset():
    session_id = session.get('session_id')
    if not session_id:
        return jsonify({'message': 'Session not found.'}), 400

    bamboo_ai_instance = bamboo_ai_instances.get(session_id)
    prefs = user_preferences.get(session_id)

    if not bamboo_ai_instance or bamboo_ai_instance.df_id is None:
        return jsonify({'message': 'No primary dataset is currently loaded.'}), 400
    
    try:     
        bamboo_ai_instance.df = None
        bamboo_ai_instance.df_id = None

        # Also clear df_id from user_preferences if it's stored there for the primary df
        if prefs and 'df_id' in prefs:
             del prefs['df_id']

        user_preferences[session_id] = prefs # Save updated prefs

        logger.info(f"Primary dataset removed and BambooAI instance reset for session {session_id}.")
        return jsonify({'message': 'Primary dataset removed successfully.'}), 200

    except Exception as e:
        logger.error(f"Error removing primary dataset for session {session_id}: {str(e)}")
        return jsonify({'message': f'Error removing primary dataset: {str(e)}'}), 500

@app.route('/upload_auxiliary_dataset', methods=['POST'])
@requires_auth
def upload_auxiliary_dataset():
    session_id = session['session_id']
    
    if 'file' not in request.files:
        return jsonify({'message': 'No file part in request for auxiliary dataset.'}), 400
    file_to_upload = request.files['file'] # Renamed to avoid conflict if passed to another function
    if file_to_upload.filename == '':
        return jsonify({'message': 'No file selected for auxiliary dataset.'}), 400

    prefs = user_preferences.get(session_id)
    if not prefs:
        prefs = {'planning': False, 'auxiliary_datasets': []}
        user_preferences[session_id] = prefs
    
    aux_datasets_list = prefs.get('auxiliary_datasets', [])

    if len(aux_datasets_list) >= 3:
        return jsonify({'message': 'Maximum 3 auxiliary datasets allowed.'}), 400
        
    if file_to_upload and (file_to_upload.filename.endswith('.csv') or file_to_upload.filename.endswith('.parquet') or file_to_upload.filename.endswith('.json') or file_to_upload.filename.endswith('.xlsx')):
        filepath_to_store = "" # This will be the path stored in preferences

        try:
            if GLOBAL_EXECUTION_MODE == 'api':
                # Send file to executor API
                files_for_executor = {'file': (file_to_upload.filename, file_to_upload.stream, file_to_upload.content_type)}
                response = requests.post(
                    get_dynamic_executor_urls(get_user_id())['EXECUTOR_API_UPLOAD_AUX_URL'], 
                    files=files_for_executor,
                    data={'user_id': get_user_id()}
                )
                response.raise_for_status()
                
                api_response_data = response.json()
                if 'filepath' not in api_response_data:
                    return jsonify({'message': 'Executor API did not return filepath for auxiliary dataset.'}), 500
                
                filepath_to_store = api_response_data['filepath']
                message = f'Auxiliary dataset "{file_to_upload.filename}" successfully uploaded to executor.'

            else: # Local mode
                datasets_dir = user_path('datasets')
                os.makedirs(datasets_dir, exist_ok=True)

                local_filepath = os.path.join(datasets_dir, file_to_upload.filename)
                file_to_upload.save(local_filepath)
                filepath_to_store = local_filepath
                message = f'Auxiliary dataset "{file_to_upload.filename}" successfully uploaded locally.'

            # Append to the list and update in user_preferences
            if filepath_to_store not in aux_datasets_list:
                aux_datasets_list.append(filepath_to_store)

            user_preferences[session_id]['auxiliary_datasets'] = aux_datasets_list
            
            # Update BambooAI instance with the new list of auxiliary datasets
            if session_id in bamboo_ai_instances:
                current_instance = bamboo_ai_instances[session_id]
                current_instance.auxiliary_datasets = aux_datasets_list
                logger.info(f"BambooAI instance for session {session_id} updated with new auxiliary dataset list.")
            
            return jsonify({
                'message': message,
                'filepath': filepath_to_store, # This is the path that will be used later (local or remote)
                'aux_dataset_count': len(aux_datasets_list)
            }), 200

        except requests.RequestException as e:
            logger.error(f"Error communicating with executor API for aux upload: {str(e)}", exc_info=True)
            return jsonify({'message': f'API communication error: {str(e)}'}), 500
        except Exception as e:
            logger.error(f"Error processing auxiliary dataset upload: {str(e)}", exc_info=True)
            return jsonify({'message': f'Error processing auxiliary dataset: {str(e)}'}), 500
    else:
        return jsonify({'message': 'Invalid file type for auxiliary dataset. Must be .csv, .parquet, .json, or .xlsx.'}), 400
    
# Remove auxiliary dataset endpoint
@app.route('/remove_auxiliary_dataset', methods=['POST'])
@requires_auth
def remove_auxiliary_dataset():
    session_id = session.get('session_id')
    if not session_id:
        return jsonify({'message': 'Session not found.'}), 400

    data = request.json
    file_path_to_remove = data.get('file_path')

    if not file_path_to_remove:
        return jsonify({'message': 'File path is required to remove auxiliary dataset.'}), 400

    prefs = user_preferences.get(session_id)
    if not (prefs and 'auxiliary_datasets' in prefs and file_path_to_remove in prefs['auxiliary_datasets']):
        return jsonify({'message': 'Dataset not found in session list.'}), 404

    try:
        # Remove from preferences list (common for both modes)
        prefs['auxiliary_datasets'].remove(file_path_to_remove)
        user_preferences[session_id] = prefs

        # Update BambooAI instance if it exists
        if session_id in bamboo_ai_instances:
            current_instance = bamboo_ai_instances[session_id]
            current_instance.auxiliary_datasets = prefs['auxiliary_datasets']
            logger.info(f"BambooAI instance for session {session_id} updated after removing auxiliary dataset.")
        
        return jsonify({'message': f'Auxiliary dataset "{os.path.basename(file_path_to_remove)}" processed for removal.', 
                        'remaining_aux_count': len(prefs['auxiliary_datasets'])}), 200

    except requests.RequestException as e:
        logger.error(f"Error communicating with executor API for aux removal: {str(e)}", exc_info=True)
        return jsonify({'message': f'API communication error during removal: {str(e)}'}), 500
    except Exception as e:
        logger.error(f"Error removing auxiliary dataset '{file_path_to_remove}': {str(e)}", exc_info=True)
        return jsonify({'message': f'Error removing dataset: {str(e)}'}), 500

# This endpoint is specifically for the primary dataset preview  
@app.route('/get_primary_dataset_preview', methods=['POST'])
@requires_auth
def get_primary_dataset_preview():
    session_id = session.get('session_id')
    if not session_id:
        return jsonify({'message': 'Session not found.'}), 400

    bamboo_ai_instance = bamboo_ai_instances.get(session_id)
    if not bamboo_ai_instance or bamboo_ai_instance.df_id is None:
        logger.info(f"Primary dataset preview requested for session {session_id}, but no DataFrame found.")
        error_df = pd.DataFrame([{"Info": "No primary dataset is currently loaded or available."}])
        df_html = error_df.to_html(classes='dataframe', border=0, index=False)
        df_json_str = json.dumps({'type': 'dataframe', 'data': df_html})
        return jsonify({'dataframe_html': df_json_str}), 200

    try:
        current_primary_df = bamboo_ai_instance.df
        df_id = bamboo_ai_instance.df_id if hasattr(bamboo_ai_instance, 'df_id') else None
        
        # Determine execution mode for the preview.
        preview_execution_mode = GLOBAL_EXECUTION_MODE
        current_executor_client = get_executor_client(get_user_id())

        page = _dataframe_first_page(current_primary_df, preview_execution_mode, df_id, current_executor_client)
        if page is not None:
            return jsonify({'dataframe_html': json.dumps({'type': 'dataframe', 'data': page})}), 200
        df_sample_for_preview = utils.computeDataframeSample(
            df=current_primary_df,
            execution_mode=preview_execution_mode,
            df_id=df_id,
            executor_client=current_executor_client
        )
        
        df_html = df_sample_for_preview.to_html(classes='dataframe', border=0, index=False)
        df_json_str = json.dumps({'type': 'dataframe', 'data': df_html})
        return jsonify({'dataframe_html': df_json_str}), 200

    except Exception as e:
        logger.error(f"Error generating primary dataset preview for session {session_id}: {str(e)}")
        error_df = pd.DataFrame([{"Error": f"Could not generate preview for the primary dataset: {str(e)}"}])
        df_html = error_df.to_html(classes='dataframe', border=0, index=False)
        df_json_str = json.dumps({'type': 'dataframe', 'data': df_html})
        return jsonify({'dataframe_html': df_json_str}), 200

# This endpoint is specifically for auxiliary dataset previews
@app.route('/get_dataset_preview', methods=['POST'])
@requires_auth
def get_dataset_preview():
    session_id = session.get('session_id')
    if not session_id:
        return jsonify({'message': 'Session not found.'}), 400

    data = request.json
    file_path_to_preview = data.get('file_path')

    if not file_path_to_preview:
        return jsonify({'message': 'File path is required for auxiliary dataset preview.'}), 400

    # 1. Authorization: Is this file_path a known auxiliary dataset for this session?
    prefs = user_preferences.get(session_id)
    if not (prefs and \
            'auxiliary_datasets' in prefs and \
            file_path_to_preview in prefs['auxiliary_datasets']):
        
        logger.warning(
            f"Preview requested for unauthorized/unknown aux dataset: {file_path_to_preview} by session {session_id}"
        )
        error_df = pd.DataFrame([{"Error": f"File not authorized or not found for preview: {os.path.basename(file_path_to_preview)}"}])
        df_html = error_df.to_html(classes='dataframe', border=0, index=False)
        df_json_str = json.dumps({'type': 'dataframe', 'data': df_html})
        # Return 200 with error in HTML as per existing pattern
        return jsonify({'dataframe_html': df_json_str}), 200

    # 2. Generate Preview (Delegates file existence checks to utils function based on execution_mode)
    try:
        page = _aux_first_page(file_path_to_preview, GLOBAL_EXECUTION_MODE, get_executor_client(get_user_id()))
        if page is not None:
            return jsonify({'dataframe_html': json.dumps({'type': 'dataframe', 'data': page})}), 200
        html_list = utils.compute_aux_dataset_sample(
            file_paths=[file_path_to_preview], # utils function expects a list
            execution_mode=GLOBAL_EXECUTION_MODE,
            executor_client=get_executor_client(get_user_id())
        )
        
        # Check if the result is valid
        if html_list and isinstance(html_list, list) and len(html_list) > 0 and html_list[0]:
            df_html = html_list[0]
        else:
            # This case covers API returning None, or local utils returning empty/None
            logger.warning(
                f"Failed to generate sample for {file_path_to_preview} (mode: {GLOBAL_EXECUTION_MODE}). Result: {html_list}"
            )
            error_message = f"Could not generate preview for {os.path.basename(file_path_to_preview)}. File might be inaccessible or empty."
            if GLOBAL_EXECUTION_MODE == 'api' and html_list is None:
                error_message = f"API failed to generate preview for {os.path.basename(file_path_to_preview)}."
            
            error_df = pd.DataFrame([{"Error": error_message}])
            df_html = error_df.to_html(classes='dataframe', border=0, index=False)
            
        df_json_str = json.dumps({'type': 'dataframe', 'data': df_html})
        return jsonify({'dataframe_html': df_json_str}), 200

    except Exception as e:
        logger.error(
            f"Exception generating aux dataset preview for {file_path_to_preview} (mode: {GLOBAL_EXECUTION_MODE}): {str(e)}",
            exc_info=True
        )
        error_df = pd.DataFrame([{"Error": f"Error generating preview for {os.path.basename(file_path_to_preview)}."}])
        df_html = error_df.to_html(classes='dataframe', border=0, index=False)
        df_json_str = json.dumps({'type': 'dataframe', 'data': df_html})
        return jsonify({'dataframe_html': df_json_str}), 200

@app.route('/query', methods=['POST'])
@requires_auth
def query():
    session_id = session['session_id']
    auth0_user_id = get_current_user_id()
    
    if auth0_user_id:
        # Check authorization only (no charging)
        auth_result = can_execute_chain(auth0_user_id)
        
        if auth_result.get('ok'):

            # TODO: Add logic to check if the current config and container matches the subscription

            auth_data = auth_result.get('data', {})
            if not auth_data.get('allowed'):
                # Build error message (unchanged)
                reason = auth_data.get('reason', 'unknown')
                compute_tier = auth_data.get('compute_tier', 'unknown')
                balance = auth_data.get('balance', 0)
                query_cost = auth_data.get('query_cost', 0)
                
                if reason == 'limit_reached':
                    queries_used = auth_data.get('queries_used', 0)
                    max_queries = auth_data.get('max_queries', 20)
                    message = f"You've used all {queries_used} of your {max_queries} free queries this month. Upgrade to Plus or Pro to continue."
                elif reason == 'insufficient_funds':
                    message = f"You need ${query_cost:.3f} per query but your balance is ${balance:.2f}. Please add funds to continue."
                else:
                    message = "Query not authorized."
                
                return jsonify({
                    'error': 'authorization_failed',
                    'message': message,
                    'reason': reason,
                    'tier': compute_tier,
                    'balance': balance,
                    'query_cost': query_cost
                }), 403
            
            # Just increment counter for free tier tracking
            try:
                increment_queries_counter(auth0_user_id)
            except Exception as e:
                logger.error(f"Failed to increment counter: {e}")
    
    # Continue with query processing
    current_bamboo_ai_instance = get_bamboo_ai(session_id)
    
    user_input = request.json['query']
    thread_id = request.json['thread_id']
    chain_id = request.json['chain_id']
    image = request.json.get('image')
    user_code = request.json.get('user_code')
    branching_cv = request.json.get('branching_cv')
    synthesis = request.json.get('synthesis', False)
    dataset_mappings = request.json.get('dataset_mappings')

    # NEW: Auto-explore parameters
    auto_explore = request.json.get('auto_explore', False)
    mode = request.json.get('mode')          # quick | deep | adaptive (2026-09-05: the brain's menu); None -> legacy flags
    # THE SIMPLIFICATION (2026-08-18): the interface dial now means
    # INVESTIGATIONS - 'up to N investigations, each up to M steps'.
    # None means 'use the tier default'; the tier is also the ceiling.
    # The legacy key is still accepted so an un-refreshed browser tab
    # keeps working.
    max_investigations = request.json.get('max_investigations')
    if max_investigations is None:
        max_investigations = request.json.get('max_iterations')

    replay = None

    update_user_activity(get_user_id())

    if user_code:
        if user_code == "replay_code_execution":
            user_input = "User updated the data in the datasets, adjusted your code accordingly, and requested to run it, and return the result."
            # Get original code
            user_code = get_python_code_from_chain(thread_id, chain_id, user_path)
            replay = chain_id
            
            # Apply dataset mappings if provided
            if user_code and dataset_mappings:
                user_code = replace_dataset_paths(user_code, dataset_mappings)
                # Optional: log the mappings for debugging
                logger.info(f"Applied dataset mappings: {dataset_mappings}")
                
        else:
            user_input = "User manually edited your code, and requested to run it, and return the result."
    elif branching_cv:
        user_input = "User requested variations of the enquiry"      # the seedling: the analyst's ideas path (2026-09-08)
    elif synthesis:
        # The SAME canned request the automatic end-of-run synthesis sends,
        # from one shared constant - so the button is a re-run of exactly
        # what auto_explore already produced, never a second dialect.
        user_input = ("Write the report for the analysis so far on this thread: the answer first, "
                      "then how it was established, its limitations and next steps.")

    current_bamboo_ai_instance.output_manager.add_user_input(user_input)
    
    def run_bamboo_ai():
        result = current_bamboo_ai_instance.pd_agent_converse(
            thread_id=thread_id,
            chain_id=chain_id,
            image=image if image else None,
            user_code=user_code if user_code else None,
            replay=replay,
            auto_explore=auto_explore,
            max_investigations=max_investigations,
            synthesis=synthesis,
            mode=mode,
            ideas=branching_cv,
        )
        
        #if result is not None and getattr(current_bamboo_ai_instance, 'output_manager', None):
            #current_bamboo_ai_instance.output_manager.output_queue.put(json.dumps({"rank_data": result}))

    thread = threading.Thread(target=run_bamboo_ai)
    thread.start()
    
    def generate():
        output_mgr = getattr(current_bamboo_ai_instance, 'output_manager', None)

        if not output_mgr:
            thread.join()
            return

        # A HEARTBEAT KEEPS THE CONNECTION HONEST.
        #
        # An agent that is thinking produces nothing: the Executor is a single
        # non-streaming call and has run for well over 100 seconds. With an
        # empty queue this loop yielded nothing at all, so the response sent
        # zero bytes for as long as the agent took. nginx cannot tell that from
        # a dead upstream, and at proxy_read_timeout it resets the stream - the
        # browser reports ERR_HTTP2_PROTOCOL_ERROR and no server log records a
        # failure, because nothing had failed.
        #
        # A newline every few seconds is enough. The client splits on newlines
        # and skips blank lines, so this needs no handling at the other end.
        last_beat = time.time()
        while thread.is_alive() or not output_mgr.output_queue.empty():
            try:
                output = output_mgr.output_queue.get(timeout=0.1)
                if output:
                    yield output + '\n'
                    last_beat = time.time()
            except Empty:
                if time.time() - last_beat >= STREAM_HEARTBEAT_SECONDS:
                    yield '\n'
                    last_beat = time.time()
            except AttributeError:
                break
                
        thread.join()

    return Response(generate(), mimetype='application/json')

@app.route('/submit_rank', methods=['POST'])
@requires_auth
def submit_rank():
    session_id = session['session_id']
    bamboo_ai_instance = get_bamboo_ai(session_id)
    
    data = request.json
    user_rank = data.get('rank')
    chain_id = data.get('chain_id')
    intent_breakdown = data.get('intent_breakdown')
    data_descr = data.get('data_descr')
    code = data.get('code')
    
    # The rank event credits memory: a high rank reinforces the cards
    # whose findings this chain rested on (the only signal that counts
    # toward promotion). Quick chains reinforce nothing structurally -
    # they carry no evidence entries. Never breaks the rank.
    logger.info(f"Rank event: chain {chain_id} rank {user_rank}")
    try:
        from bambooai.knowledge_pack import reinforce, REINFORCE_RANK_MIN
        if user_rank is not None and int(user_rank) >= REINFORCE_RANK_MIN:
            credited = reinforce(user_memory_path(), str(chain_id),
                                 reason='rank')
            if credited:
                logger.info(f"Memory: reinforcement recorded for "
                            f"{len(credited)} cards ({', '.join(credited)}) "
                            f"via rank on chain {chain_id}")
                bamboo_ai_instance.output_manager.output_queue.put(json.dumps({
                    "system_message": f"Memory: reinforcement recorded for "
                                      f"{', '.join(credited)}"}))
                # Crossing the threshold earns a REVIEW, not an
                # automatic promotion - nudge the user toward it.
                from bambooai.knowledge_pack import promotable
                _promo = [x['name'] for x in
                          promotable(user_memory_path())]
                if _promo:
                    logger.info(f"Memory: ready for promotion review: "
                                f"{', '.join(_promo)}")
                    bamboo_ai_instance.output_manager.output_queue.put(
                        json.dumps({"memory_review": _promo}))
                    bamboo_ai_instance.output_manager.output_queue.put(
                        json.dumps({"system_message":
                                    "Memory: '"
                                    + "', '".join(_promo)
                                    + "' ready for promotion - open "
                                      "Memory Review"}))
            # Consent-on-write (step 26): the keep-signal is where a
            # memory may be BORN. The distill itself - the slow LLM call -
            # runs in the response generator's worker below, so its
            # progress streams into the rank dialog live.
    except Exception as _mem_err:                               # noqa: BLE001
        logger.warning(f"Memory: rank reinforcement failed: {_mem_err}")

    def generate():
        # The memory work above queued its messages synchronously, so
        # historically the client saw them in one burst AFTER the
        # distiller finished - "Saving checkpoint..." sat frozen for the
        # whole LLM call. The distill (the slow part) now runs in a
        # worker while this generator drains the queue LIVE, so the rank
        # dialog narrates the birth as it happens.
        import threading
        _done = threading.Event()

        def _distill_work():
            try:
                bamboo_ai_instance.output_manager.output_queue.put(
                    json.dumps({"system_message":
                                "Distilling this run into memory..."}))
                new_cards = bamboo_ai_instance.distill_kept_chain(
                    str(chain_id))
                if new_cards:
                    bamboo_ai_instance.output_manager.output_queue.put(
                        json.dumps({"system_message":
                                    "Memory: new candidate card"
                                    + ("s " if len(new_cards) > 1 else " ")
                                    + ", ".join(f"'{n}'"
                                                for n in new_cards)}))
                else:
                    bamboo_ai_instance.output_manager.output_queue.put(
                        json.dumps({"system_message":
                                    "Saved. No new memory card from this "
                                    "run."}))
            except Exception as _d_err:                         # noqa: BLE001
                logger.warning(f"Memory: distill worker failed: {_d_err}")
            finally:
                _done.set()

        threading.Thread(target=_distill_work, daemon=True).start()
        while not _done.is_set() or \
                not bamboo_ai_instance.output_manager.output_queue.empty():
            try:
                output = bamboo_ai_instance.output_manager.output_queue.get(
                    timeout=0.2)
                if output:
                    yield output + '\n'
            except Empty:
                pass  # keep draining until the worker finishes

    return Response(generate(), mimetype='application/json')

@app.route('/storage/get_existing_chains/<thread_id>', methods=['GET'])
@requires_auth
def get_existing_chains(thread_id):
    """Return set of chain_ids already saved for this thread."""
    try:
        favourites_dir = user_path('storage', 'favourites', str(thread_id))
        if not os.path.exists(favourites_dir):
            return jsonify({'chain_ids': []}), 200
        
        existing = [f.replace('.json', '') for f in os.listdir(favourites_dir) 
                    if f.endswith('.json')]
        return jsonify({'chain_ids': existing}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/memory/review', methods=['GET'])
@requires_auth
def memory_review():
    """The promotion review's read side: candidates at the threshold,
    with the flags to clear and the similar cards to merge."""
    try:
        from bambooai.knowledge_pack import promotable, governing
        return jsonify({'promotable': promotable(user_memory_path()),
                        'established': governing(user_memory_path())}), 200
    except Exception as e:                                      # noqa: BLE001
        logger.warning(f"Memory review read failed: {e}")
        return jsonify({'promotable': []}), 200


@app.route('/memory/review/action', methods=['POST'])
@requires_auth
def memory_review_action():
    """The review's verbs: promote (with optional hook polish), merge
    (absorb similars; stays a candidate), retire (repudiation)."""
    try:
        from bambooai.knowledge_pack import promote, retire, merge
        data = request.json or {}
        action = data.get('action')
        name = data.get('name')
        if action == 'promote':
            ok, why = promote(user_memory_path(), name,
                              hooks=data.get('hooks'))
        elif action == 'retire':
            ok, why = retire(user_memory_path(), name)
        elif action == 'merge':
            ok, why = merge(user_memory_path(), name,
                            data.get('absorb') or [])
        else:
            return jsonify({'ok': False, 'reason': 'unknown action'}), 400
        if ok:
            logger.info(f"Memory review: {action} '{name}' ok")
        return jsonify({'ok': ok, 'reason': why}), (200 if ok else 400)
    except Exception as e:                                      # noqa: BLE001
        logger.warning(f"Memory review action failed: {e}")
        return jsonify({'ok': False, 'reason': str(e)}), 500


@app.route('/storage/favourites', methods=['POST'])
@requires_auth
def store_favourite():
    """ Store the favourite solution in the storage/favourites directory """
    
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'Missing request data'}), 400
            
        # Extract and validate fields
        thread_id = data.get('thread_id')
        chain_id = data.get('chain_id')
        dataset_name = data.get('dataset_name')
        index = data.get('index')
        rank = data.get('rank')
        content = data.get('content')
        task = data.get('task', '')  # Extract task field with empty default

        # Create directory path for favourites
        favourites_dir = user_path('storage', 'favourites', str(thread_id))
        os.makedirs(favourites_dir, exist_ok=True)

        # Create filename using chain_id
        filename = os.path.join(favourites_dir, f'{chain_id}.json')

        # Add timestamp and task to saved data
        save_data = {
            'thread_id': thread_id,
            'chain_id': chain_id,
            'parentChainId': data.get('parentChainId'),
            'dataset_name': dataset_name,
            'index': index,
            'rank': rank,
            'timestamp': pd.Timestamp.now().isoformat(),
            'task': task,
            'bookmark_type': 'individual',
            **content
        }

        # Write to JSON file, overwriting if it exists
        with open(filename, 'w') as f:
            json.dump(save_data, f, indent=2)

        # Saving a chain is the strongest keep-signal there is: reinforce
        # the cards whose findings it rested on. Never breaks the save.
        try:
            from bambooai.knowledge_pack import reinforce
            credited = reinforce(user_memory_path(), str(chain_id),
                                 reason='save')
            if credited:
                logger.info(f"Memory: reinforcement recorded for "
                            f"{len(credited)} cards ({', '.join(credited)}) "
                            f"via save of chain {chain_id}")
        except Exception as _mem_err:                           # noqa: BLE001
            logger.warning(f"Memory: save reinforcement failed: {_mem_err}")

        return jsonify({
            'message': 'Solution saved to favourites', 
            'filename': filename,
            'task_included': bool(task)  # Let client know if task was included
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500
    
@app.route('/storage/trajectory_favourites', methods=['POST'])
@requires_auth
def store_trajectory_favourites():
    """Store an entire trajectory of chains to favorites."""
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'Missing request data'}), 400
        
        thread_id = data.get('thread_id')
        dataset_name = data.get('dataset_name')
        rank = data.get('rank')
        trajectory = data.get('trajectory', [])
        
        if not thread_id or not trajectory:
            return jsonify({'error': 'Missing required fields'}), 400
        
        # Create directory path for favourites
        favourites_dir = user_path('storage', 'favourites', str(thread_id))
        os.makedirs(favourites_dir, exist_ok=True)
        
        saved_count = 0
        errors = []
        saved_chain_ids = []
        
        for chain_data in trajectory:
            try:
                chain_id = chain_data.get('chain_id')
                content = chain_data.get('content', {})
                task = chain_data.get('task', '')
                index = chain_data.get('index')
                parent_chain_id = chain_data.get('parentChainId')
                
                if not chain_id:
                    continue
                
                filename = os.path.join(favourites_dir, f'{chain_id}.json')
                
                # --- NEW: Determine bookmark type ---
                bookmark_type = chain_data.get('bookmark_type')
                
                # Preserve existing bookmark — individual takes precedence
                if os.path.exists(filename):
                    try:
                        with open(filename, 'r') as f:
                            existing_data = json.load(f)
                            existing_type = existing_data.get('bookmark_type')
                            if existing_type == 'individual':
                                bookmark_type = 'individual'
                            elif existing_type and not bookmark_type:
                                bookmark_type = existing_type
                    except Exception:
                        pass
                # --- END NEW ---
                
                save_data = {
                    'thread_id': thread_id,
                    'chain_id': chain_id,
                    'parentChainId': parent_chain_id,
                    'dataset_name': dataset_name,
                    'index': index,
                    'rank': rank,
                    'timestamp': pd.Timestamp.now().isoformat(),
                    'task': task,
                    'bookmark_type': bookmark_type,  # NEW
                    **content
                }
                
                with open(filename, 'w') as f:
                    json.dump(save_data, f, indent=2)
                
                saved_count += 1
                saved_chain_ids.append((str(chain_id), bookmark_type))
                
            except Exception as chain_error:
                logger.error(f"Error saving chain {chain_data.get('chain_id')}: {chain_error}")
                errors.append(str(chain_error))
                continue
        
        # This is the LIVE save path (the UI's fused rank-then-save gesture
        # lands here; the plain /storage/favourites route is legacy). Every
        # deliberately kept chain reinforces the cards it rested on. With a
        # high rank the rank hook credited first and this is an idempotent
        # no-op; with a low rank the save is the keep-signal that credits.
        # Never breaks the save.
        try:
            from bambooai.knowledge_pack import reinforce
            credited_all = set()
            # The save is a keep-signal too: attempt distillation for each
            # kept chain (idempotent - the rank leg of the fused gesture
            # usually got there first at high ranks; at LOW ranks this is
            # where a memory may be born).
            # Judgment births, archival credits: only chains kept as
            # 'individual' (the deliberate single-chain gesture) are
            # distilled. A bulk Save Trajectory - auto_explore can carry
            # 20+ chains of exploratory scaffolding - reinforces every
            # saved chain but births nothing.
            # The rating bar is the consent dial the UI advertises:
            # below REINFORCE_RANK_MIN the hint reads "Saves to
            # favorites only" - so memory stays untouched, honoring the
            # on-screen contract over any silent cleverness.
            from bambooai.knowledge_pack import REINFORCE_RANK_MIN
            try:
                _qualifies = (rank is not None
                              and int(rank) >= REINFORCE_RANK_MIN)
            except (TypeError, ValueError):
                _qualifies = False
            _sid = session.get('session_id')
            _inst = bamboo_ai_instances.get(_sid) if _sid else None
            for _cid, _btype in saved_chain_ids:
                if not _qualifies:
                    continue
                if _inst is not None and _btype == 'individual':
                    _inst.distill_kept_chain(_cid)
                credited_all.update(reinforce(user_memory_path(), _cid,
                                              reason='save'))
            if credited_all:
                logger.info(f"Memory: reinforcement recorded for "
                            f"{len(credited_all)} cards "
                            f"({', '.join(sorted(credited_all))}) via save "
                            f"of {len(saved_chain_ids)} chains "
                            f"({sum(1 for _c, _b in saved_chain_ids if _b == 'individual')} individual)")
                from bambooai.knowledge_pack import promotable
                _promo = [x['name'] for x in
                          promotable(user_memory_path())]
                if _promo:
                    logger.info(f"Memory: ready for promotion review: "
                                f"{', '.join(_promo)}")
        except Exception as _mem_err:                           # noqa: BLE001
            logger.warning(f"Memory: save reinforcement failed: {_mem_err}")

        return jsonify({
            'message': 'Trajectory saved successfully',
            'saved_count': saved_count,
            'total_count': len(trajectory),
            'errors': errors if errors else None
        }), 200
        
    except Exception as e:
        logger.exception(f"Error storing trajectory: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500
    
@app.route('/get_threads', methods=['GET'])
@requires_auth
def get_threads():
    """Get list of all saved threads with all their chains."""
    try:
        # Get the include_previews parameter
        include_previews = request.args.get('include_previews', 'false').lower() == 'true'
        
        # Get the favorites directory
        favourites_dir = user_path('storage', 'favourites')
        
        if not os.path.exists(favourites_dir):
            logger.warning(f"Favorites directory does not exist: {favourites_dir}")
            return jsonify({'threads': []}), 200
        
        # Get all thread directories
        thread_dirs = [d for d in os.listdir(favourites_dir) 
                      if os.path.isdir(os.path.join(favourites_dir, d))]
        
        if not thread_dirs:
            logger.info("No thread directories found")
            return jsonify({'threads': []}), 200
            
        threads_info = []
        
        # Process each thread directory
        for thread_id in thread_dirs:
            thread_path = os.path.join(favourites_dir, thread_id)
            
            # Get all chain files in this thread
            chain_files = glob.glob(os.path.join(thread_path, '*.json'))
            
            if not chain_files:
                logger.warning(f"No chain files found in thread {thread_id}")
                continue
                
            # Sort files by modification time (newest first)
            chain_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
            
            # Get the newest timestamp for thread sorting
            newest_timestamp = ''
            
            # Create array for all chains in this thread
            thread_chains = []
            
            # Read all chain files for this thread
            for chain_file in chain_files:
                try:
                    with open(chain_file, 'r') as f:
                        chain_data = json.load(f)
                        
                    # Extract chain info
                    chain_id = chain_data.get('chain_id')
                    task = chain_data.get('task', '')
                    timestamp = chain_data.get('timestamp', '')
                    dataset_name = chain_data.get('dataset_name', '')
                    
                    # Update newest timestamp for thread sorting
                    if not newest_timestamp or (timestamp and timestamp > newest_timestamp):
                        newest_timestamp = timestamp
                    
                    # Build chain info
                    chain_info = {
                        'thread_id': thread_id,
                        'chain_id': chain_id,
                        'index': chain_data.get('index'),
                        'task': task,
                        'queryText': chain_data.get('queryText', ''),
                        'timestamp': timestamp,
                        'dataset_name': dataset_name,
                        'label_id': chain_data.get('label_id'),
                        'label_name': chain_data.get('label_name'),
                        'bookmark_type': chain_data.get('bookmark_type')
                    }
                    
                    # Include preview if requested
                    if include_previews:
                        chain_info['plotPreview'] = chain_data.get('plotPreview')
                        chain_info['hasPlotly'] = bool(chain_data.get('plotPreview'))
                        chain_info['synthesisImage'] = chain_data.get('synthesisImage')
                    
                    thread_chains.append(chain_info)
                    
                except (json.JSONDecodeError, KeyError) as e:
                    logger.error(f"Error processing chain file {chain_file}: {str(e)}")
                    continue
            
            # Sort chains by timestamp (newest first)
            thread_chains.sort(key=lambda c: c.get('timestamp', ''), reverse=True)
            
            # Add thread with all its chains
            threads_info.append({
                'thread_id': thread_id,
                'newest_timestamp': newest_timestamp,
                'chains': thread_chains
            })
        
        # Sort threads by newest timestamp (newest first)
        threads_info.sort(key=lambda t: t.get('newest_timestamp', ''), reverse=True)
        
        return jsonify({'threads': threads_info}), 200
        
    except Exception as e:
        logger.exception(f"Error getting threads: {str(e)}")
        return jsonify({'error': f"Server error: {str(e)}"}), 500

@app.route('/load_thread/<thread_id>/<chain_id>', methods=['GET'])
@requires_auth
def load_thread(thread_id, chain_id):
    """Load all content for a specific thread, targeting a specific chain."""
    try:
        logger.info(f"Loading thread {thread_id} with target chain {chain_id}")
        
        thread_path = user_path('storage', 'favourites', thread_id)
            
        # Load ALL chain files in this thread
        chain_files = glob.glob(os.path.join(thread_path, '*.json'))
        
        logger.info(f"Found {len(chain_files)} chain files in thread")
        
        if not chain_files:
            return jsonify({'error': 'No chains found in thread'}), 404
        
        responses = []
        for chain_file in chain_files:
            try:
                with open(chain_file, 'r') as f:
                    chain_data = json.load(f)
                    
                response = {
                    'thread_id': thread_id,
                    'chain_id': chain_data.get('chain_id', ''),
                    'parentChainId': chain_data.get('parentChainId'),
                    'index': chain_data.get('index'),
                    'bookmark_type': chain_data.get('bookmark_type'),
                    'tabContent': chain_data.get('tabContent', ''),
                    'contentOutput': chain_data.get('contentOutput', ''),
                    'streamOutput': chain_data.get('streamOutput', ''),
                    'taskContents': chain_data.get('taskContents', {}),
                    'queryText': chain_data.get('queryText', ''),
                    'compressed': chain_data.get('compressed', False),
                    'plotPreview': chain_data.get('plotPreview'),
                    'technicalAnswer': chain_data.get('technicalAnswer'),
                    'simplifiedAnswer': chain_data.get('simplifiedAnswer'),
                    'summaryViewMode': chain_data.get('summaryViewMode', 'technical'),
                    'synthesisImage': chain_data.get('synthesisImage'),
                }
                
                responses.append(response)
                
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f"Error processing chain file {chain_file}: {str(e)}")
                continue
        
        if not responses:
            return jsonify({'error': 'Failed to load any responses from the thread'}), 500
        
        # Sort by saved index to preserve original exploration order
        responses.sort(key=lambda r: r.get('index') or 0)
        
        logger.info(f"Loaded {len(responses)} responses, target chain: {chain_id}")
        
        return jsonify({
            'message': f"Thread {thread_id} loaded with {len(responses)} chains",
            'responses': responses,
            'target_chain_id': chain_id
        }), 200
        
    except Exception as e:
        logger.exception(f"Error loading thread {thread_id}: {str(e)}")
        return jsonify({'error': f"Server error: {str(e)}"}), 500
    
# Updated get_chain_preview route in backend
@app.route('/get_chain_preview/<thread_id>/<chain_id>', methods=['GET'])
@requires_auth
def get_chain_preview(thread_id, chain_id):
    """Get a preview image for a specific chain."""
    try:
        chain_file = user_path('storage', 'favourites', thread_id, f'{chain_id}.json')
        
        if not os.path.exists(chain_file):
            return jsonify({'error': 'Chain file not found'}), 404
            
        with open(chain_file, 'r') as f:
            chain_data = json.load(f)
        
        # Check for stored plot preview
        plot_preview = chain_data.get('plotPreview')
        
        if plot_preview:
            return jsonify({
                'threadId': thread_id,
                'chainId': chain_id,
                'hasPlotly': True,
                'plotPreview': plot_preview
            }), 200
        else:
            return jsonify({
                'threadId': thread_id,
                'chainId': chain_id,
                'hasPlotly': False
            }), 200
        
    except Exception as e:
        logger.error(f"Error getting chain preview for {thread_id}/{chain_id}: {str(e)}")
        return jsonify({'error': f"Server error: {str(e)}"}), 500
    
@app.route('/delete_thread/<thread_id>', methods=['DELETE'])
@requires_auth
def delete_thread(thread_id):
    """Delete an entire thread and all its chains from favorites and vector db."""
    try:
        session_id = session.get('session_id')
        thread_path = user_path('storage', 'favourites', thread_id)
        
        if not os.path.exists(thread_path):
            return jsonify({'error': 'Thread not found'}), 404
        
        # Collect all chain_ids before deletion (for memory tombstoning)
        chain_files = glob.glob(os.path.join(thread_path, '*.json'))
        chain_ids = []
        for chain_file in chain_files:
            chain_id = os.path.basename(chain_file).replace('.json', '')
            chain_ids.append(chain_id)

        # Deletion is housekeeping, not repudiation: candidate evidence
        # citing these chains is tombstoned; established cards unaffected.
        try:
            from bambooai.knowledge_pack import tombstone
            marked, removed = tombstone(user_memory_path(), chain_ids)
            if marked:
                logger.info(f"Memory: tombstoned {marked} evidence entries "
                            f"(thread delete, {len(chain_ids)} chains)"
                            + (f"; removed {len(removed)} orphaned "
                               f"candidates ({', '.join(removed)})"
                               if removed else ""))
        except Exception as _mem_err:                           # noqa: BLE001
            logger.warning(f"Memory: tombstoning failed: {_mem_err}")

        # Remove labels from all chains
        for chain_id in chain_ids:
            try:
                remove_label_from_chain(chain_id)
            except Exception as label_error:
                logger.warning(f"Label removal failed for chain {chain_id}: {label_error}")
        
        # Delete the entire thread directory
        shutil.rmtree(thread_path)
        logger.info(f"Deleted entire thread directory: {thread_id} ({len(chain_ids)} chains)")
        
        return jsonify({
            'message': f"Thread {thread_id} deleted successfully",
            'thread_id': thread_id,
            'chains_deleted': len(chain_ids)
        }), 200
        
    except Exception as e:
        logger.error(f"Error deleting thread {thread_id}: {str(e)}")
        return jsonify({'error': f"Server error: {str(e)}"}), 500
    
@app.route('/delete_chain/<thread_id>/<chain_id>', methods=['DELETE'])
@requires_auth
def delete_chain(thread_id, chain_id):
    """Delete a chain from the favorites directory and vector db if applicable."""
    try:
        session_id = session.get('session_id')
        
        # Remove label from the chain in database (chain record stays)
        if remove_label_from_chain(chain_id):
            logger.info(f"Removed label from chain {chain_id}")
        else:
            logger.warning(f"Could not remove label from chain {chain_id}")

        # Single-chain deletion tombstones its candidate evidence too.
        try:
            from bambooai.knowledge_pack import tombstone
            marked, removed = tombstone(user_memory_path(), [str(chain_id)])
            if marked:
                logger.info(f"Memory: tombstoned {marked} evidence entries "
                            f"(chain {chain_id} deleted)"
                            + (f"; removed {len(removed)} orphaned "
                               f"candidates ({', '.join(removed)})"
                               if removed else ""))
        except Exception as _mem_err:                           # noqa: BLE001
            logger.warning(f"Memory: tombstoning failed: {_mem_err}")

        # Construct the path to the chain file
        chain_file = user_path('storage', 'favourites', thread_id, f'{chain_id}.json')
        
        # Check if the file exists
        if not os.path.exists(chain_file):
            return jsonify({'error': 'Chain file not found'}), 404
            
        # Delete the file
        os.remove(chain_file)
        
        # Check if the thread directory is now empty
        thread_dir = user_path('storage', 'favourites', thread_id)
        remaining_files = glob.glob(os.path.join(thread_dir, '*.json'))
        
        # If empty, remove the directory too
        if not remaining_files:
            os.rmdir(thread_dir)
            logger.info(f"Removed empty thread directory: {thread_id}")
        
        return jsonify({
            'message': f"Chain {chain_id} deleted successfully",
            'thread_id': thread_id,
            'chain_id': chain_id,
            'thread_empty': len(remaining_files) == 0
        }), 200
        
    except Exception as e:
        logger.error(f"Error deleting chain {chain_id}: {str(e)}")
        return jsonify({'error': f"Server error: {str(e)}"}), 500

@app.route('/new_conversation', methods=['POST'])
@requires_auth
def new_conversation():
    session_id = session['session_id']
    return start_new_conversation(session_id)

@app.route('/stop_exploration', methods=['POST'])
@requires_auth
def stop_exploration():
    session_id = session['session_id']
    if session_id in bamboo_ai_instances:
        bamboo_ai_instances[session_id].kill_signal = True
        bamboo_ai_instances[session_id]._stop_event.set()
        logger.info(f"Stop signal sent for session {session_id}")
        return jsonify({"status": "stopped"}), 200
    return jsonify({"error": "No active session"}), 404

@app.route('/submit_feedback', methods=['POST'])
@requires_auth
def submit_feedback():
    data = request.json
    feedback = data.get('feedback')
    chain_id = data.get('chain_id')
    query_clarification = data.get('query_clarification')
    context_needed = data.get('context_needed')

    if not all([feedback, chain_id, query_clarification, context_needed]):
        logger.error('Missing required fields in feedback request: %s', data)
        return jsonify({'error': 'Missing required fields'}), 400

    # Construct feedback file path
    feedback_file = os.path.join(user_path('temp'), f'feedback_{chain_id}.json')

    # Load existing feedback or initialize empty list
    feedback_list = []
    try:
        if os.path.exists(feedback_file):
            with open(feedback_file, 'r') as f:
                feedback_list = json.load(f)
            logger.debug(f'Loaded existing feedback from {feedback_file}: {len(feedback_list)} entries')
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f'Failed to read {feedback_file}: {str(e)}. Initializing empty list.')

    # Append new feedback
    feedback_list.append({
        'query_clarification': query_clarification,
        'context_needed': context_needed,
        'feedback': feedback,
        'timestamp': pd.Timestamp.now().isoformat()
    })

    # Write back to file
    try:
        with open(feedback_file, 'w') as f:
            json.dump(feedback_list, f, indent=2)
            f.flush()  # Ensure write is committed
        return jsonify({'message': 'Feedback received'}), 200
    except Exception as e:
        logger.error(f'Error writing feedback to {feedback_file}: {str(e)}')
        return jsonify({'error': f'Failed to store feedback: {str(e)}'}), 500
    
@app.route('/download_generated_dataset', methods=['GET'])
@requires_auth
def download_generated_dataset():
    file_path_param = request.args.get('path')

    if not file_path_param:
        logger.error("Download request missing 'path' parameter.")
        return jsonify({'error': "Missing 'path' query parameter."}), 400

    logger.info(f"Attempting to download generated dataset: {file_path_param} in mode: {GLOBAL_EXECUTION_MODE}")

    if GLOBAL_EXECUTION_MODE == 'api':
        executor_download_url = get_dynamic_executor_urls(get_user_id())['EXECUTOR_API_DOWNLOAD_GENERATED_URL']
        if not executor_download_url:
            logger.error("Failed to get container for user.")
            return jsonify({'error': 'Failed to get container for download.'}), 500
        try:
            # Construct the full URL to the executor's download endpoint
            user_id = get_user_id()
            executor_download_url = f"{executor_download_url}?path={requests.utils.quote(file_path_param)}&user_id={user_id}"
            
            logger.info(f"Fetching from executor API: {executor_download_url}")
            
            # Stream the response from the executor API
            api_response = requests.get(executor_download_url, stream=True)
            api_response.raise_for_status() # Raise an exception for HTTP errors

            # Get filename for Content-Disposition
            filename = os.path.basename(file_path_param)

            # Create a streaming Flask response
            def generate_file_stream():
                for chunk in api_response.iter_content(chunk_size=8192):
                    yield chunk
            
            # Try to get content type from executor's response, or default
            content_type = api_response.headers.get('Content-Type', 'application/octet-stream')

            return Response(generate_file_stream(),
                            mimetype=content_type,
                            headers={"Content-Disposition": f"attachment;filename={filename}"})

        except requests.RequestException as e:
            logger.error(f"Error fetching file from executor API: {str(e)}")
            return jsonify({'error': f'Failed to fetch file from remote service: {str(e)}'}), 502 # Bad Gateway
        except Exception as e:
            logger.error(f"Unexpected error during API mode download: {str(e)}")
            return jsonify({'error': f'An unexpected error occurred: {str(e)}'}), 500

    else: # Local mode
        base_download_dir = os.path.abspath(os.getcwd())
        
        requested_file_abs = os.path.abspath(os.path.join(base_download_dir, file_path_param))

        allowed_prefix = os.path.abspath(os.path.join(base_download_dir, user_path("datasets", "generated")))
        
        if not requested_file_abs.startswith(allowed_prefix):
            logger.warning(f"Access denied for local download: {file_path_param}. Resolved path {requested_file_abs} is outside allowed prefix {allowed_prefix}.")
            return jsonify({'error': 'Access denied or invalid file path.'}), 403
        
        if not os.path.exists(requested_file_abs) or not os.path.isfile(requested_file_abs):
            logger.error(f"Local file not found for download: {requested_file_abs}")
            return jsonify({'error': 'File not found.'}), 404

        try:
            # send_from_directory needs directory and filename separately
            directory, filename = os.path.split(requested_file_abs)
            logger.info(f"Serving local file: directory='{directory}', filename='{filename}'")
            return send_from_directory(directory, filename, as_attachment=True)
        except Exception as e:
            logger.error(f"Error serving local file {file_path_param}: {str(e)}")
            return jsonify({'error': f'Error serving file: {str(e)}'}), 500


# Create base directories (always run on import, for both dev and prod)
base_dirs = ['temp', 'iframe_figures', 'logs', 'datasets', 'storage', 'config']
for base_dir in base_dirs:
    os.makedirs(base_dir, exist_ok=True)

# Factory function for Gunicorn
def create_app():
    """Factory function for Gunicorn"""
    return app

# ALWAYS create the application variable for Gunicorn
application = create_app()

if __name__ == '__main__':
    if os.getenv('FLASK_ENV') == 'development':
        # Optional: Keep argparse only for dev runs (overrides env var if provided)
        parser = argparse.ArgumentParser(description='BambooAI Flask App')
        parser.add_argument('--debug', action='store_true', help='Skip thread cleanup')
        args = parser.parse_args()
        
        # SSL context for development server
        ssl_context = (SSL_CERT_PATH, SSL_KEY_PATH) if SSL_ENABLED and SSL_CERT_PATH and SSL_KEY_PATH else None
        app.run(host='0.0.0.0', port=APP_PORT, ssl_context=ssl_context, debug=True)