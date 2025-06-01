import argparse
import re
import os
import sys
import shutil
import json
import requests
import threading
import uuid
import glob
import pandas as pd
from queue import Queue, Empty
from flask import Flask, request, jsonify, Response, render_template, session, send_from_directory
import tempfile
from dotenv import load_dotenv
from google.cloud import storage
from werkzeug.datastructures import FileStorage

def cleanup_threads(debug_mode=False):
    """
    Clean up thread JSON files and temporary ontology files that don't have matching IDs in favorites.
    If debug_mode is True, no files will be deleted.
    """
    if debug_mode:
        print("Debug mode: Skipping thread and ontology cleanup")
        return
    
    # Get favorite thread IDs from directory names
    favorites_dir = os.path.join('storage', 'favourites')
    favorite_thread_ids = set()
    if os.path.exists(favorites_dir):
        favorite_thread_ids = {d for d in os.listdir(favorites_dir) 
                             if os.path.isdir(os.path.join(favorites_dir, d))}
    
    # Delete thread files that don't match favorite IDs
    threads_dir = os.path.join('storage', 'threads')
    if os.path.exists(threads_dir):
        thread_files = glob.glob(os.path.join(threads_dir, '*.json'))
        for thread_file in thread_files:
            thread_id = os.path.basename(thread_file).split('.')[0]
            if thread_id not in favorite_thread_ids:
                try:
                    os.remove(thread_file)
                    print(f"Deleted thread: {thread_id}")
                except Exception as e:
                    print(f"Failed to delete {thread_id}: {str(e)}")
    
    # Clean up temporary ontology files for non-existent sessions
    temp_dir = 'temp'
    if os.path.exists(temp_dir):
        ontology_files = glob.glob(os.path.join(temp_dir, '*_*.ttl'))
        active_sessions = set(user_preferences.keys())
        for ontology_file in ontology_files:
            session_id = os.path.basename(ontology_file).split('_')[0]
            if session_id not in active_sessions:
                try:
                    os.remove(ontology_file)
                    print(f"Deleted orphaned ontology file: {ontology_file}")
                except Exception as e:
                    print(f"Failed to delete {ontology_file}: {str(e)}")

def clear_datasets_folder():
    datasets_dir = 'datasets'
    generated_datasets_base_dir = os.path.join(datasets_dir, 'generated')
    favorites_base_dir = os.path.join('storage', 'favourites')

    # 1. Get favorite thread IDs
    favorite_thread_ids = set()
    if os.path.exists(favorites_base_dir):
        try:
            favorite_thread_ids = {
                d for d in os.listdir(favorites_base_dir)
                if os.path.isdir(os.path.join(favorites_base_dir, d))
            }
            app.logger.info(f"Favorite thread IDs for dataset cleanup: {list(favorite_thread_ids)}")
        except Exception as e:
            app.logger.error(f"Error reading favorites directory {favorites_base_dir}: {e}")

    if not os.path.exists(datasets_dir):
        app.logger.info(f"'{datasets_dir}' folder does not exist, no need to clear.")
        return

    # 2. Iterate through items in the main 'datasets' directory
    try:
        for item_name in os.listdir(datasets_dir):
            item_path = os.path.join(datasets_dir, item_name)
            try:
                if os.path.isfile(item_path) or os.path.islink(item_path):
                    # Delete all files directly under 'datasets/'
                    os.unlink(item_path)
                    app.logger.info(f"Deleted file: {item_path}")
                elif os.path.isdir(item_path):
                    # If the subdirectory is 'generated', process its contents
                    if item_name == 'generated' and os.path.exists(generated_datasets_base_dir):
                        app.logger.info(f"Processing 'generated' subdirectory: {generated_datasets_base_dir}")
                        for generated_thread_id_dir_name in os.listdir(generated_datasets_base_dir):
                            thread_specific_dir_path = os.path.join(generated_datasets_base_dir, generated_thread_id_dir_name)
                            if os.path.isdir(thread_specific_dir_path):
                                # This directory name is treated as the thread_id
                                if generated_thread_id_dir_name not in favorite_thread_ids:
                                    shutil.rmtree(thread_specific_dir_path)
                                    app.logger.info(f"Deleted non-favorited generated dataset directory: {thread_specific_dir_path}")
                                else:
                                    app.logger.info(f"Kept favorited generated dataset directory: {thread_specific_dir_path}")
                    elif item_name != 'generated':
                        app.logger.warning(f"Skipping deletion of non-'generated' subdirectory: {item_path}. Adjust logic if this should be deleted.")
            except Exception as e:
                app.logger.error(f'Failed to process item {item_path}. Reason: {e}')
        app.logger.info(f"Selective cleanup of '{datasets_dir}' folder completed.")
    except Exception as e:
        app.logger.error(f"Error listing contents of '{datasets_dir}': {str(e)}")

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

# Get API URL from environment variable or use default
EXECUTOR_API_BASE_URL = os.getenv('EXECUTOR_API_BASE_URL')
EXECUTOR_API_UPLOAD_URL = f"{EXECUTOR_API_BASE_URL}/upload_dataset"
EXECUTOR_API_UPLOAD_AUX_URL = f"{EXECUTOR_API_BASE_URL}/file_utils/upload_aux_dataset"
EXECUTOR_API_REMOVE_AUX_URL = f"{EXECUTOR_API_BASE_URL}/file_utils/remove_aux_dataset"
EXECUTOR_API_DOWNLOAD_GENERATED_URL = f"{EXECUTOR_API_BASE_URL}/download_generated_dataset"
# Get execution mode from environment variable or default to 'local'
GLOBAL_EXECUTION_MODE = os.getenv('EXECUTION_MODE', 'local')  # Default to 'local' if not set

# Create an instance of the ExecutorAPIClient
executor_client = executor_client.ExecutorAPIClient(base_url=EXECUTOR_API_BASE_URL)

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET')

# Dictionary to store BambooAI instances for each session
bamboo_ai_instances = {}

# Dictionary to store user preferences for each session
user_preferences = {}

# BambooAI parameters
EXPLORATORY = True
SEARCH_TOOL = True
WEBUI = True
VECTOR_DB = bool(os.getenv('PINECONE_API_KEY'))
DF_ONTOLOGY = None

# Function to generate a unique DataFrame ID
def generate_dataframe_id() -> str:
    df_id = str(uuid.uuid4())
    return df_id

def get_bamboo_ai(session_id, df=None):
    """Factory function to create or retrieve BambooAI instances"""
    prefs = user_preferences.get(session_id, {'planning': False, 'ontology_path': None, 'auxiliary_datasets': []})
    df_id = prefs.get('df_id')
    ontology_path = prefs.get('ontology_path', DF_ONTOLOGY)  # Default to constant if not set
    aux_datasets = prefs.get('auxiliary_datasets', []) # Get auxiliary_datasets

    if session_id not in bamboo_ai_instances:
        bamboo_ai_instances[session_id] = BambooAI(
            df=df,
            exploratory=EXPLORATORY,
            planning=prefs['planning'],
            search_tool=SEARCH_TOOL,
            webui=WEBUI,
            vector_db=VECTOR_DB,
            df_ontology=ontology_path,
            df_id=df_id,
            auxiliary_datasets=aux_datasets
        )
    return bamboo_ai_instances[session_id]

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

def load_dataframe_to_bamboo_ai_instance(session_id, df=None, file=None, execution_mode='local'):
    new_df_id = generate_dataframe_id()
    prefs = user_preferences.get(session_id, {'planning': False, 'ontology_path': None, 'auxiliary_datasets': []})
    prefs['df_id'] = new_df_id
    user_preferences[session_id] = prefs
    ontology_path = prefs.get('ontology_path', DF_ONTOLOGY)
    aux_datasets = prefs.get('auxiliary_datasets', []) # Get auxiliary_datasets

    if execution_mode == 'api':
        if not file:
            raise ValueError("File is required for API execution mode")
        try:
            file.seek(0)
            files = {'file': (file.filename, file, file.content_type)}
            executor_response = requests.post(
                EXECUTOR_API_UPLOAD_URL,
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

    bamboo_ai_instances[session_id] = BambooAI(
        df=df,
        exploratory=EXPLORATORY,
        planning=prefs['planning'],
        search_tool=SEARCH_TOOL,
        webui=WEBUI,
        vector_db=VECTOR_DB,
        df_ontology=ontology_path,
        df_id=new_df_id,
        auxiliary_datasets=aux_datasets
    )

    df_index = utils.computeDataframeSample(
        df=df,
        execution_mode=execution_mode,
        df_id=new_df_id,
        executor_client=executor_client)
    df_html = df_index.to_html(classes='dataframe', border=0, index=False)
    df_json = json.dumps({'type': 'dataframe', 'data': df_html})

    return df_json, new_df_id

def start_new_conversation(session_id):
    # Clear the Datasets folder first
    clear_datasets_folder()

    prefs = user_preferences.get(session_id, {
        'planning': False, 
        'ontology_path': None, # Ensure default structure
        'auxiliary_datasets': []
    })
    
    # Clear auxiliary datasets list in user_preferences for the current session
    prefs['auxiliary_datasets'] = []
    
    # Clear the ontology path in user_preferences
    old_ontology_path = prefs.get('ontology_path')
    if old_ontology_path and os.path.exists(old_ontology_path):
        try:
            os.remove(old_ontology_path)
            app.logger.info(f"Removed old ontology file during new conversation: {old_ontology_path}")
        except Exception as e:
            app.logger.error(f"Failed to remove old ontology file {old_ontology_path} during new conversation: {str(e)}")
    prefs['ontology_path'] = None 
    
    user_preferences[session_id] = prefs # Save updated prefs
    
    aux_datasets = prefs.get('auxiliary_datasets', [])
    current_ontology_path = prefs.get('ontology_path', DF_ONTOLOGY)

    bamboo_ai_instances[session_id] = BambooAI(
        df=None,
        exploratory=EXPLORATORY,
        planning=prefs['planning'],
        search_tool=SEARCH_TOOL,
        webui=WEBUI,
        vector_db=VECTOR_DB,
        df_ontology=current_ontology_path,
        df_id=None,
        auxiliary_datasets=aux_datasets 
    )

    bamboo_ai_instances[session_id].pd_agent_converse(action='reset')
    app.logger.info(f"BambooAI instance reset for session {session_id}, auxiliary datasets list cleared, ontology cleared, and Datasets folder content cleared.")
    
    return jsonify({"message": "New conversation started"}), 200

@app.before_request
def ensure_session():
    if 'session_id' not in session:
        session_id = str(uuid.uuid4())
        session['session_id'] = session_id
    
    # Ensure default preferences are set for the session
    session_id = session['session_id'] # Get it again in case it was just set
    if session_id not in user_preferences:
        user_preferences[session_id] = {
            'planning': False,
            'ontology_path': None,
            'auxiliary_datasets': []
        }

@app.route('/')
def index():
    return render_template('index.html')

# New endpoint to update planning preference
@app.route('/update_planning', methods=['POST'])
def update_planning():
    session_id = session.get('session_id')
    data = request.json
    planning_enabled = data.get('planning', False)
    
    if not session_id:
        return jsonify({'error': 'No session ID found'}), 400
    
    # Get existing preferences or create new dict with defaults
    prefs = user_preferences.get(session_id, {'planning': False})
    
    # Update to new planning state while preserving other preferences
    prefs['planning'] = planning_enabled
    user_preferences[session_id] = prefs
    
    # Update BambooAI instance if it exists
    if session_id in bamboo_ai_instances:
        current_instance = bamboo_ai_instances[session_id]
        try:
            bamboo_ai_instances[session_id] = BambooAI(
                df=current_instance.df if hasattr(current_instance, 'df') else None,
                exploratory=current_instance.exploratory,
                planning=planning_enabled,  # Use the new state
                search_tool=current_instance.search_tool,
                webui=current_instance.webui,
                vector_db=current_instance.vector_db,
                df_ontology=current_instance.df_ontology,
                df_id=current_instance.df_id if hasattr(current_instance, 'df_id') else None,
                auxiliary_datasets=current_instance.auxiliary_datasets if hasattr(current_instance, 'auxiliary_datasets') else []
            )
            print(f"[DEBUG] Successfully updated BambooAI instance with planning={planning_enabled}")
        except Exception as e:
            print(f"[ERROR] Failed to update BambooAI instance: {str(e)}")
            return jsonify({'error': 'Failed to update BambooAI instance'}), 500
    
    return jsonify({
        'message': f'Planning parameter updated to {planning_enabled}',
        'current_state': prefs['planning']
    }), 200

@app.route('/get_planning_state', methods=['GET'])
def get_planning_state():
    session_id = session.get('session_id')
    
    if not session_id:
        return jsonify({'error': 'No session ID found'}), 400
    
    current_state = user_preferences.get(session_id, {}).get('planning', False)
    
    return jsonify({'planning_enabled': current_state})

@app.route('/update_ontology', methods=['POST'])
def update_ontology():
    session_id = session.get('session_id')
    if not session_id:
        return jsonify({'error': 'No session ID found'}), 400

    prefs = user_preferences.get(session_id, {'planning': False, 'ontology_path': None})
    old_ontology_path = prefs.get('ontology_path')

    ontology_path = None
    if 'ontology_file' in request.files:
        file = request.files['ontology_file']
        if file.filename == '':
            return jsonify({'message': 'No selected file'}), 400
        if file and file.filename.endswith('.ttl'):
            # Save file temporarily
            temp_dir = 'temp'
            os.makedirs(temp_dir, exist_ok=True)
            temp_file = os.path.join(temp_dir, f"{session_id}_{file.filename}")
            file.save(temp_file)
            ontology_path = temp_file
        else:
            return jsonify({'message': 'Invalid file type, must be .ttl'}), 400
    elif request.form.get('ontology_path') == '':
        ontology_path = None  # Explicitly clear ontology
    else:
        return jsonify({'message': 'Invalid request, must include ontology_file or clear ontology_path'}), 400

    # Clean up old ontology file if it exists
    if old_ontology_path and os.path.exists(old_ontology_path):
        try:
            os.remove(old_ontology_path)
            print(f"[DEBUG] Removed old ontology file: {old_ontology_path}")
        except Exception as e:
            print(f"[ERROR] Failed to remove old ontology file {old_ontology_path}: {str(e)}")

    # Update preferences
    prefs['ontology_path'] = ontology_path
    user_preferences[session_id] = prefs

    # Update BambooAI instance if it exists
    if session_id in bamboo_ai_instances:
        current_instance = bamboo_ai_instances[session_id]
        try:
            bamboo_ai_instances[session_id] = BambooAI(
                df=current_instance.df if hasattr(current_instance, 'df') else None,
                exploratory=current_instance.exploratory,
                planning=prefs['planning'],
                search_tool=current_instance.search_tool,
                webui=current_instance.webui,
                vector_db=current_instance.vector_db,
                df_ontology=ontology_path if ontology_path else DF_ONTOLOGY,
                df_id=current_instance.df_id if hasattr(current_instance, 'df_id') else None,
                auxiliary_datasets=current_instance.auxiliary_datasets if hasattr(current_instance, 'auxiliary_datasets') else []
            )
            print(f"[DEBUG] Successfully updated BambooAI instance with ontology_path={ontology_path}")
        except Exception as e:
            print(f"[ERROR] Failed to update BambooAI instance: {str(e)}")
            return jsonify({'error': 'Failed to update BambooAI instance'}), 500

    return jsonify({
        'message': f'Ontology path updated to {ontology_path if ontology_path else "None"}',
        'current_state': bool(ontology_path)
    }), 200

# New endpoint to get ontology state
@app.route('/get_ontology_state', methods=['GET'])
def get_ontology_state():
    session_id = session.get('session_id')

    if not session_id:
        return jsonify({'error': 'No session ID found'}), 400

    prefs = user_preferences.get(session_id, {'planning': False, 'ontology_path': None})
    ontology_path = prefs.get('ontology_path')

    return jsonify({
        'ontology_enabled': bool(ontology_path),
        'ontology_path': ontology_path
    })

# Upload primary dataset endpoint
@app.route('/upload', methods=['POST'])
def upload_file():
    session_id = session['session_id']
    
    if 'file' not in request.files:
        return jsonify({'message': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'message': 'No selected file'}), 400
        
    if file and (file.filename.endswith('.csv') or file.filename.endswith('.parquet')):
        filepath = os.path.join('temp', f"{session_id}_{file.filename}")
        file.save(filepath)

        try:
            if GLOBAL_EXECUTION_MODE == 'local':
                # Only load DataFrame for local mode
                if file.filename.endswith('.csv'):
                    df = load_csv_with_datetime(filepath)
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
def remove_primary_dataset():
    session_id = session.get('session_id')
    if not session_id:
        return jsonify({'message': 'Session not found.'}), 400

    bamboo_ai_instance = bamboo_ai_instances.get(session_id)
    prefs = user_preferences.get(session_id)

    if not bamboo_ai_instance or bamboo_ai_instance.df_id is None:
        return jsonify({'message': 'No primary dataset is currently loaded.'}), 400
    
    try:
        # Re-instantiate BambooAI for the session without the primary df
        # Keep auxiliary datasets if they exist
        aux_datasets = prefs.get('auxiliary_datasets', []) if prefs else []
        planning_pref = prefs.get('planning', False) if prefs else False
        ontology_path_pref = prefs.get('ontology_path', DF_ONTOLOGY) if prefs else DF_ONTOLOGY

        bamboo_ai_instances[session_id] = BambooAI(
            df=None, # Explicitly set df to None
            exploratory=EXPLORATORY,
            planning=planning_pref,
            search_tool=SEARCH_TOOL,
            webui=WEBUI,
            vector_db=VECTOR_DB,
            df_ontology=ontology_path_pref,
            df_id=None, # Clear df_id
            auxiliary_datasets=aux_datasets
        )
        # Also clear df_id from user_preferences if it's stored there for the primary df
        if prefs and 'df_id' in prefs:
             del prefs['df_id']

        user_preferences[session_id] = prefs # Save updated prefs

        app.logger.info(f"Primary dataset removed and BambooAI instance reset for session {session_id}.")
        return jsonify({'message': 'Primary dataset removed successfully.'}), 200

    except Exception as e:
        app.logger.error(f"Error removing primary dataset for session {session_id}: {str(e)}")
        return jsonify({'message': f'Error removing primary dataset: {str(e)}'}), 500

@app.route('/upload_auxiliary_dataset', methods=['POST'])
def upload_auxiliary_dataset():
    session_id = session['session_id']
    
    if 'file' not in request.files:
        return jsonify({'message': 'No file part in request for auxiliary dataset.'}), 400
    file_to_upload = request.files['file'] # Renamed to avoid conflict if passed to another function
    if file_to_upload.filename == '':
        return jsonify({'message': 'No file selected for auxiliary dataset.'}), 400

    prefs = user_preferences.get(session_id)
    if not prefs:
        prefs = {'planning': False, 'ontology_path': None, 'auxiliary_datasets': []}
        user_preferences[session_id] = prefs
    
    aux_datasets_list = prefs.get('auxiliary_datasets', [])

    if len(aux_datasets_list) >= 3:
        return jsonify({'message': 'Maximum 3 auxiliary datasets allowed.'}), 400
        
    if file_to_upload and (file_to_upload.filename.endswith('.csv') or file_to_upload.filename.endswith('.parquet')):
        filepath_to_store = "" # This will be the path stored in preferences

        try:
            if GLOBAL_EXECUTION_MODE == 'api':
                if not EXECUTOR_API_UPLOAD_AUX_URL:
                    return jsonify({'message': 'Executor API URL for aux upload not configured.'}), 500
                
                # Send file to executor API
                files_for_executor = {'file': (file_to_upload.filename, file_to_upload.stream, file_to_upload.content_type)}
                response = requests.post(EXECUTOR_API_UPLOAD_AUX_URL, files=files_for_executor)
                response.raise_for_status()
                
                api_response_data = response.json()
                if 'filepath' not in api_response_data:
                    return jsonify({'message': 'Executor API did not return filepath for auxiliary dataset.'}), 500
                
                filepath_to_store = api_response_data['filepath']
                message = f'Auxiliary dataset "{file_to_upload.filename}" successfully uploaded to executor.'

            else: # Local mode
                datasets_dir = 'datasets'
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
                bamboo_ai_instances[session_id] = BambooAI(
                    df=current_instance.df,
                    exploratory=current_instance.exploratory,
                    planning=prefs.get('planning', False),
                    search_tool=current_instance.search_tool,
                    webui=current_instance.webui,
                    vector_db=current_instance.vector_db,
                    df_ontology=prefs.get('ontology_path', DF_ONTOLOGY),
                    df_id=current_instance.df_id,
                    auxiliary_datasets=aux_datasets_list # Pass updated list
                )
                app.logger.info(f"BambooAI instance for session {session_id} updated with new auxiliary dataset list.")
            
            return jsonify({
                'message': message,
                'filepath': filepath_to_store, # This is the path that will be used later (local or remote)
                'aux_dataset_count': len(aux_datasets_list)
            }), 200

        except requests.RequestException as e:
            app.logger.error(f"Error communicating with executor API for aux upload: {str(e)}", exc_info=True)
            return jsonify({'message': f'API communication error: {str(e)}'}), 500
        except Exception as e:
            app.logger.error(f"Error processing auxiliary dataset upload: {str(e)}", exc_info=True)
            return jsonify({'message': f'Error processing auxiliary dataset: {str(e)}'}), 500
    else:
        return jsonify({'message': 'Invalid file type for auxiliary dataset. Must be .csv or .parquet.'}), 400
    
# Remove auxiliary dataset endpoint
@app.route('/remove_auxiliary_dataset', methods=['POST'])
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
        if GLOBAL_EXECUTION_MODE == 'api':
            if not EXECUTOR_API_REMOVE_AUX_URL:
                return jsonify({'message': 'Executor API URL for aux removal not configured.'}), 500
            
            response = requests.post(EXECUTOR_API_REMOVE_AUX_URL, json={'file_path': file_path_to_remove})
            response.raise_for_status() # Will raise an exception for 4xx/5xx errors
            # Executor API handles actual file deletion. We trust its response.
            app.logger.info(f"Request to remove auxiliary dataset '{file_path_to_remove}' sent to executor.")

        else: # Local mode
            # Security check for local mode
            datasets_dir_abs = os.path.abspath('datasets')
            requested_file_abs = os.path.abspath(file_path_to_remove)
            if not requested_file_abs.startswith(datasets_dir_abs):
                app.logger.warning(f"Attempt to remove file outside local datasets directory: {file_path_to_remove}")
                return jsonify({'message': 'Invalid file path for local removal.'}), 403

            if os.path.exists(file_path_to_remove):
                os.remove(file_path_to_remove)
                app.logger.info(f"Locally removed auxiliary dataset file: {file_path_to_remove}")
            else:
                app.logger.warning(f"Local auxiliary dataset file not found for removal, but removing from list: {file_path_to_remove}")

        # Remove from preferences list (common for both modes)
        prefs['auxiliary_datasets'].remove(file_path_to_remove)
        user_preferences[session_id] = prefs

        # Update BambooAI instance if it exists
        if session_id in bamboo_ai_instances:
            current_instance = bamboo_ai_instances[session_id]
            bamboo_ai_instances[session_id] = BambooAI(
                df=current_instance.df,
                exploratory=current_instance.exploratory,
                planning=prefs['planning'],
                search_tool=current_instance.search_tool,
                webui=current_instance.webui,
                vector_db=current_instance.vector_db,
                df_ontology=prefs.get('ontology_path', DF_ONTOLOGY),
                df_id=current_instance.df_id,
                auxiliary_datasets=prefs['auxiliary_datasets']
            )
            app.logger.info(f"BambooAI instance for session {session_id} updated after removing auxiliary dataset.")
        
        return jsonify({'message': f'Auxiliary dataset "{os.path.basename(file_path_to_remove)}" processed for removal.', 
                        'remaining_aux_count': len(prefs['auxiliary_datasets'])}), 200

    except requests.RequestException as e:
        app.logger.error(f"Error communicating with executor API for aux removal: {str(e)}", exc_info=True)
        return jsonify({'message': f'API communication error during removal: {str(e)}'}), 500
    except Exception as e:
        app.logger.error(f"Error removing auxiliary dataset '{file_path_to_remove}': {str(e)}", exc_info=True)
        return jsonify({'message': f'Error removing dataset: {str(e)}'}), 500

# This endpoint is specifically for the primary dataset preview  
@app.route('/get_primary_dataset_preview', methods=['POST'])
def get_primary_dataset_preview():
    session_id = session.get('session_id')
    if not session_id:
        return jsonify({'message': 'Session not found.'}), 400

    bamboo_ai_instance = bamboo_ai_instances.get(session_id)
    if not bamboo_ai_instance or bamboo_ai_instance.df_id is None:
        app.logger.info(f"Primary dataset preview requested for session {session_id}, but no DataFrame found.")
        error_df = pd.DataFrame([{"Info": "No primary dataset is currently loaded or available."}])
        df_html = error_df.to_html(classes='dataframe', border=0, index=False)
        df_json_str = json.dumps({'type': 'dataframe', 'data': df_html})
        return jsonify({'dataframe_html': df_json_str}), 200

    try:
        current_primary_df = bamboo_ai_instance.df
        df_id = bamboo_ai_instance.df_id if hasattr(bamboo_ai_instance, 'df_id') else None
        
        # Determine execution mode for the preview.
        preview_execution_mode = GLOBAL_EXECUTION_MODE
        current_executor_client = executor_client

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
        app.logger.error(f"Error generating primary dataset preview for session {session_id}: {str(e)}")
        error_df = pd.DataFrame([{"Error": f"Could not generate preview for the primary dataset: {str(e)}"}])
        df_html = error_df.to_html(classes='dataframe', border=0, index=False)
        df_json_str = json.dumps({'type': 'dataframe', 'data': df_html})
        return jsonify({'dataframe_html': df_json_str}), 200

# This endpoint is specifically for auxiliary dataset previews
@app.route('/get_dataset_preview', methods=['POST'])
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
        
        app.logger.warning(
            f"Preview requested for unauthorized/unknown aux dataset: {file_path_to_preview} by session {session_id}"
        )
        error_df = pd.DataFrame([{"Error": f"File not authorized or not found for preview: {os.path.basename(file_path_to_preview)}"}])
        df_html = error_df.to_html(classes='dataframe', border=0, index=False)
        df_json_str = json.dumps({'type': 'dataframe', 'data': df_html})
        # Return 200 with error in HTML as per existing pattern
        return jsonify({'dataframe_html': df_json_str}), 200

    # 2. Generate Preview (Delegates file existence checks to utils function based on execution_mode)
    try:
        html_list = utils.compute_aux_dataset_sample(
            file_paths=[file_path_to_preview], # utils function expects a list
            execution_mode=GLOBAL_EXECUTION_MODE,
            executor_client=executor_client
        )
        
        # Check if the result is valid
        if html_list and isinstance(html_list, list) and len(html_list) > 0 and html_list[0]:
            df_html = html_list[0]
        else:
            # This case covers API returning None, or local utils returning empty/None
            app.logger.warning(
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
        app.logger.error(
            f"Exception generating aux dataset preview for {file_path_to_preview} (mode: {GLOBAL_EXECUTION_MODE}): {str(e)}",
            exc_info=True
        )
        error_df = pd.DataFrame([{"Error": f"Error generating preview for {os.path.basename(file_path_to_preview)}."}])
        df_html = error_df.to_html(classes='dataframe', border=0, index=False)
        df_json_str = json.dumps({'type': 'dataframe', 'data': df_html})
        return jsonify({'dataframe_html': df_json_str}), 200

@app.route('/query', methods=['POST'])
def query():
    session_id = session['session_id']
    bamboo_ai_instance = get_bamboo_ai(session_id)
    user_input = request.json['query']
    thread_id = request.json['thread_id']
    chain_id = request.json['chain_id']
    image = request.json.get('image')
    user_code= request.json.get('user_code')

    if user_code:
        user_input = "User manually edited your code, and requested to run it, and return the result."
    
    bamboo_ai_instance.output_manager.enable_web_mode()
    bamboo_ai_instance.output_manager.add_user_input(user_input)
    
    def run_bamboo_ai():
        result = bamboo_ai_instance.pd_agent_converse(
            thread_id=thread_id,
            chain_id=chain_id,
            image=image if image else None,
            user_code=user_code if user_code else None
        )
        
        if result is not None:
            bamboo_ai_instance.output_manager.output_queue.put(json.dumps({"rank_data": result}))

    thread = threading.Thread(target=run_bamboo_ai)
    thread.start()
    
    def generate():
        while thread.is_alive() or not bamboo_ai_instance.output_manager.output_queue.empty():
            try:
                output = bamboo_ai_instance.output_manager.output_queue.get(timeout=0.1)
                if output:
                    yield output + '\n'
            except Empty:
                pass  # Queue is empty, continue waiting

        # Ensure the thread has finished
        thread.join()
        
        # Disable web mode
        bamboo_ai_instance.output_manager.disable_web_mode()

    return Response(generate(), mimetype='application/json')

@app.route('/submit_rank', methods=['POST'])
def submit_rank():
    session_id = session['session_id']
    bamboo_ai_instance = get_bamboo_ai(session_id)

    bamboo_ai_instance.output_manager.enable_web_mode()
    
    data = request.json
    user_rank = data.get('rank')
    chain_id = data.get('chain_id')
    intent_breakdown = data.get('intent_breakdown')
    plan = data.get('plan')
    data_descr = data.get('data_descr')
    data_model = data.get('data_model')
    code = data.get('code')
    
    if bamboo_ai_instance.vector_db:
        bamboo_ai_instance.pinecone_wrapper.add_record(
            chain_id,
            intent_breakdown,
            plan, 
            data_descr,
            data_model, 
            code, 
            user_rank, 
            bamboo_ai_instance.similarity_threshold
        )
    else:
        bamboo_ai_instance.output_manager.output_queue.put(json.dumps({"system_message": "Vector database is not enabled"}))

    def generate():
        while not bamboo_ai_instance.output_manager.output_queue.empty():
            try:
                output = bamboo_ai_instance.output_manager.output_queue.get(timeout=0.1)
                if output:
                    yield output + '\n'
            except Empty:
                pass  # Queue is empty, continue waiting
        
        bamboo_ai_instance.output_manager.disable_web_mode()

    return Response(generate(), mimetype='application/json')

@app.route('/storage/favourites', methods=['POST'])
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
        favourites_dir = os.path.join('storage', 'favourites', str(thread_id))
        os.makedirs(favourites_dir, exist_ok=True)

        # Create filename using chain_id
        filename = os.path.join(favourites_dir, f'{chain_id}.json')

        # Add timestamp and task to saved data
        save_data = {
            'thread_id': thread_id,
            'chain_id': chain_id,
            'dataset_name': dataset_name,
            'index': index,
            'rank': rank,
            'timestamp': pd.Timestamp.now().isoformat(),
            'task': task,  # Include the task field
            **content  # Merge with content data
        }

        # Write to JSON file, overwriting if it exists
        with open(filename, 'w') as f:
            json.dump(save_data, f, indent=2)
            
        return jsonify({
            'message': 'Solution saved to favourites', 
            'filename': filename,
            'task_included': bool(task)  # Let client know if task was included
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500
    
@app.route('/get_threads', methods=['GET'])
def get_threads():
    """Get list of all saved threads with all their chains."""
    try:
        # Get the favorites directory
        favourites_dir = os.path.join('storage', 'favourites')
        
        if not os.path.exists(favourites_dir):
            app.logger.warning(f"Favorites directory does not exist: {favourites_dir}")
            return jsonify({'threads': []}), 200
        
        # Get all thread directories
        thread_dirs = [d for d in os.listdir(favourites_dir) 
                      if os.path.isdir(os.path.join(favourites_dir, d))]
        
        if not thread_dirs:
            app.logger.info("No thread directories found")
            return jsonify({'threads': []}), 200
            
        threads_info = []
        
        # Process each thread directory
        for thread_id in thread_dirs:
            thread_path = os.path.join(favourites_dir, thread_id)
            
            # Get all chain files in this thread
            chain_files = glob.glob(os.path.join(thread_path, '*.json'))
            
            if not chain_files:
                app.logger.warning(f"No chain files found in thread {thread_id}")
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
                    
                    # Add chain info to the list
                    thread_chains.append({
                        'thread_id': thread_id,
                        'chain_id': chain_id,
                        'task': task,
                        'timestamp': timestamp,
                        'dataset_name': dataset_name

                    })
                    
                except (json.JSONDecodeError, KeyError) as e:
                    app.logger.error(f"Error processing chain file {chain_file}: {str(e)}")
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
        app.logger.exception(f"Error getting threads: {str(e)}")
        return jsonify({'error': f"Server error: {str(e)}"}), 500

@app.route('/load_thread/<thread_id>/<chain_id>', methods=['GET'])
def load_thread(thread_id, chain_id):
    """Load all content for a specific thread and chain."""
    try:
        app.logger.info(f"Loading thread {thread_id} with chain {chain_id}")
        
        # Path to the thread directory
        thread_path = os.path.join('storage', 'favourites', thread_id)
            
        # Get a chain file with the specified chain_id
        chain_files = glob.glob(os.path.join(thread_path, f'{chain_id}.json'))
        
        app.logger.info(f"Found {len(chain_files)} chain files: {chain_files}")
        
        # Read all chain files and build responses array
        responses = []
        for chain_file in chain_files:
            try:
                with open(chain_file, 'r') as f:
                    chain_data = json.load(f)
                
                app.logger.info(f"Successfully loaded chain file: {chain_file}")
                    
                # Extract the response data
                response = {
                    'thread_id': thread_id,
                    'chain_id': chain_data.get('chain_id', chain_id),  # Default to URL parameter if missing
                    'tabContent': chain_data.get('tabContent', ''),
                    'contentOutput': chain_data.get('contentOutput', ''),
                    'streamOutput': chain_data.get('streamOutput', ''),
                    'taskContents': chain_data.get('taskContents', {}),
                    'queryText': chain_data.get('queryText', '')
                }
                
                responses.append(response)
                
            except (json.JSONDecodeError, KeyError) as e:
                app.logger.error(f"Error processing chain file {chain_file}: {str(e)}")
                continue
        
        if not responses:
            app.logger.error("Failed to load any responses from the thread")
            return jsonify({'error': "Failed to load any responses from the thread"}), 500
        
        app.logger.info(f"Loaded {len(responses)} responses")
        
        app.logger.info("Sending successful response with content")
        return jsonify({
            'message': f"Thread {thread_id} with chain {chain_id} loaded successfully",
            'responses': responses,
        }), 200
        
    except Exception as e:
        app.logger.exception(f"Error loading thread {thread_id}: {str(e)}")
        return jsonify({
            'error': f"Server error: {str(e)}",
            'traceback': str(e.__traceback__)
        }), 500
    
@app.route('/get_chain_preview/<thread_id>/<chain_id>', methods=['GET'])
def get_chain_preview(thread_id, chain_id):
    """Get a preview image or plotly data for a specific chain."""
    try:
        # Path to the chain file
        chain_file = os.path.join('storage', 'favourites', thread_id, f'{chain_id}.json')
        
        if not os.path.exists(chain_file):
            return jsonify({'error': 'Chain file not found'}), 404
            
        # Read chain data
        with open(chain_file, 'r') as f:
            chain_data = json.load(f)
        
        # Look for plotly data in different possible fields
        plotly_data = None
        content_fields = ['contentOutput', 'streamOutput', 'tabContent']
        
        for field in content_fields:
            if field in chain_data and chain_data[field]:
                content = chain_data[field]
                
                # Pattern 1: Standard format
                plotly_match = re.search(r'data-plotly-json=\\"(.*?)\\"\s', content)
                if plotly_match:
                    plotly_json_escaped = plotly_match.group(1)
                    plotly_data = plotly_json_escaped.replace('&quot;', '"')
                    break
                
                # Pattern 2: Another common format
                plotly_match = re.search(r'data-plotly-json="(.*?)"', content)
                if plotly_match:
                    plotly_json_escaped = plotly_match.group(1)
                    plotly_data = plotly_json_escaped.replace('&quot;', '"')
                    break
                
                # Pattern 3: Look for JSON that might be plotly data
                plotly_match = re.search(r'({[^{]*?"data"[^{]*?"type":"scatter"[^}]*?})', content)
                if plotly_match:
                    plotly_data = plotly_match.group(1)
                    break
        
        if plotly_data:
            return jsonify({
                'threadId': thread_id,
                'chainId': chain_id,
                'hasPlotly': True,
                'plotlyData': plotly_data
            }), 200
        else:
            return jsonify({
                'threadId': thread_id,
                'chainId': chain_id,
                'hasPlotly': False
            }), 200
        
    except Exception as e:
        app.logger.error(f"Error getting chain preview for {thread_id}/{chain_id}: {str(e)}")
        return jsonify({'error': f"Server error: {str(e)}"}), 500
    
@app.route('/delete_chain/<thread_id>/<chain_id>', methods=['DELETE'])
def delete_chain(thread_id, chain_id):
    """Delete a chain from the favorites directory and vector db if applicable."""
    try:
        session_id = session.get('session_id')
        
        # Delete from vector database if enabled
        if session_id and session_id in bamboo_ai_instances:
            bamboo_ai_instance = bamboo_ai_instances[session_id]
            if bamboo_ai_instance.vector_db:           
                bamboo_ai_instance.pinecone_wrapper.delete_record(chain_id)

        # Construct the path to the chain file
        chain_file = os.path.join('storage', 'favourites', thread_id, f'{chain_id}.json')
        
        # Check if the file exists
        if not os.path.exists(chain_file):
            return jsonify({'error': 'Chain file not found'}), 404
            
        # Delete the file
        os.remove(chain_file)
        
        # Check if the thread directory is now empty
        thread_dir = os.path.join('storage', 'favourites', thread_id)
        remaining_files = glob.glob(os.path.join(thread_dir, '*.json'))
        
        # If empty, remove the directory too
        if not remaining_files:
            os.rmdir(thread_dir)
            app.logger.info(f"Removed empty thread directory: {thread_id}")
        
        return jsonify({
            'message': f"Chain {chain_id} deleted successfully",
            'thread_id': thread_id,
            'chain_id': chain_id,
            'thread_empty': len(remaining_files) == 0
        }), 200
        
    except Exception as e:
        app.logger.error(f"Error deleting chain {chain_id}: {str(e)}")
        return jsonify({'error': f"Server error: {str(e)}"}), 500

@app.route('/new_conversation', methods=['POST'])
def new_conversation():
    session_id = session['session_id']
    return start_new_conversation(session_id)

@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    data = request.json
    feedback = data.get('feedback')
    chain_id = data.get('chain_id')
    query_clarification = data.get('query_clarification')
    context_needed = data.get('context_needed')

    if not all([feedback, chain_id, query_clarification, context_needed]):
        app.logger.error('Missing required fields in feedback request: %s', data)
        return jsonify({'error': 'Missing required fields'}), 400

    # Construct feedback file path
    feedback_file = os.path.join('temp', f'feedback_{chain_id}.json')

    # Load existing feedback or initialize empty list
    feedback_list = []
    try:
        if os.path.exists(feedback_file):
            with open(feedback_file, 'r') as f:
                feedback_list = json.load(f)
            app.logger.debug(f'Loaded existing feedback from {feedback_file}: {len(feedback_list)} entries')
    except (json.JSONDecodeError, IOError) as e:
        app.logger.warning(f'Failed to read {feedback_file}: {str(e)}. Initializing empty list.')

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
        app.logger.error(f'Error writing feedback to {feedback_file}: {str(e)}')
        return jsonify({'error': f'Failed to store feedback: {str(e)}'}), 500
    
@app.route('/download_generated_dataset', methods=['GET'])
def download_generated_dataset():
    file_path_param = request.args.get('path')

    if not file_path_param:
        app.logger.error("Download request missing 'path' parameter.")
        return jsonify({'error': "Missing 'path' query parameter."}), 400

    app.logger.info(f"Attempting to download generated dataset: {file_path_param} in mode: {GLOBAL_EXECUTION_MODE}")

    if GLOBAL_EXECUTION_MODE == 'api':
        if not EXECUTOR_API_DOWNLOAD_GENERATED_URL:
            app.logger.error("Executor API URL for generated dataset download not configured.")
            return jsonify({'error': 'Executor API URL for download not configured.'}), 500
        try:
            # Construct the full URL to the executor's download endpoint
            executor_download_url = f"{EXECUTOR_API_DOWNLOAD_GENERATED_URL}?path={requests.utils.quote(file_path_param)}"
            
            app.logger.info(f"Fetching from executor API: {executor_download_url}")
            
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
            app.logger.error(f"Error fetching file from executor API: {str(e)}")
            return jsonify({'error': f'Failed to fetch file from remote service: {str(e)}'}), 502 # Bad Gateway
        except Exception as e:
            app.logger.error(f"Unexpected error during API mode download: {str(e)}")
            return jsonify({'error': f'An unexpected error occurred: {str(e)}'}), 500

    else: # Local mode
        base_download_dir = os.path.abspath(os.getcwd())
        
        requested_file_abs = os.path.abspath(os.path.join(base_download_dir, file_path_param))

        allowed_prefix = os.path.abspath(os.path.join(base_download_dir, "datasets", "generated"))
        
        if not requested_file_abs.startswith(allowed_prefix):
            app.logger.warning(f"Access denied for local download: {file_path_param}. Resolved path {requested_file_abs} is outside allowed prefix {allowed_prefix}.")
            return jsonify({'error': 'Access denied or invalid file path.'}), 403
        
        if not os.path.exists(requested_file_abs) or not os.path.isfile(requested_file_abs):
            app.logger.error(f"Local file not found for download: {requested_file_abs}")
            return jsonify({'error': 'File not found.'}), 404

        try:
            # send_from_directory needs directory and filename separately
            directory, filename = os.path.split(requested_file_abs)
            app.logger.info(f"Serving local file: directory='{directory}', filename='{filename}'")
            return send_from_directory(directory, filename, as_attachment=True)
        except Exception as e:
            app.logger.error(f"Error serving local file {file_path_param}: {str(e)}")
            return jsonify({'error': f'Error serving file: {str(e)}'}), 500

if __name__ == '__main__':
    # Simple command line argument for debug mode
    parser = argparse.ArgumentParser(description='BambooAI Flask App')
    parser.add_argument('--debug', action='store_true', help='Skip thread cleanup')
    args = parser.parse_args()
    
    # Ensure directories exist
    os.makedirs('temp', exist_ok=True)
    os.makedirs(os.path.join('storage', 'favourites'), exist_ok=True)
    os.makedirs(os.path.join('storage', 'threads'), exist_ok=True)
    os.makedirs('datasets', exist_ok=True)
    
    # Run thread cleanup
    cleanup_threads(debug_mode=args.debug)

    # Clear datasets folder
    clear_datasets_folder()
    
    # Start the Flask app
    app.run(host='0.0.0.0', port=5000, debug=False)