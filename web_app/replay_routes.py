from flask import Blueprint, request, jsonify
from auth import requires_auth
import os
import json
import pandas as pd

from logger_config import get_logger
logger = get_logger(__name__)

replay_bp = Blueprint('replay', __name__)

def user_path(root, *paths):
    """Helper to build user-specific path - import from main app"""
    from app import user_path as app_user_path
    return app_user_path(root, *paths)

@replay_bp.route('/storage/replay_favourites', methods=['POST'])
@requires_auth
def store_replay_favourite():
    """Store replay solution with parent chain hierarchy in storage/replays directory"""
    
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'Missing request data'}), 400
            
        # Extract and validate fields
        thread_id = data.get('thread_id')
        chain_id = data.get('chain_id')
        parent_chain_id = data.get('parent_chain_id')
        dataset_name = data.get('dataset_name')
        index = data.get('index')
        content = data.get('content')

        # Validate required fields
        if not all([thread_id, chain_id, parent_chain_id, dataset_name is not None, content]):
            return jsonify({'error': 'Missing required fields'}), 400

        # Create directory hierarchy: storage/user_id/replays/thread_id/parent_chain_id/
        replays_dir = user_path('storage', 'replays', str(thread_id), str(parent_chain_id))
        os.makedirs(replays_dir, exist_ok=True)

        # Create filename using chain_id
        filename = os.path.join(replays_dir, f'{chain_id}.json')

        # Prepare save data (no rank or task fields for replays)
        save_data = {
            'thread_id': thread_id,
            'chain_id': chain_id,
            'parent_chain_id': parent_chain_id,
            'dataset_name': dataset_name,
            'index': index,
            'timestamp': pd.Timestamp.now().isoformat(),
            **content  # Merge with content data
        }

        # Write to JSON file, overwriting if it exists
        with open(filename, 'w') as f:
            json.dump(save_data, f, indent=2)
            
        return jsonify({
            'message': 'Replay solution saved successfully', 
            'filename': filename,
            'parent_chain_id': parent_chain_id
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@replay_bp.route('/storage/replay_favourites/<thread_id>/<parent_chain_id>', methods=['GET'])
@requires_auth
def get_replay_favourites(thread_id, parent_chain_id):
    """Get all replay solutions for a specific parent chain"""
    
    try:
        replays_dir = user_path('storage', 'replays', str(thread_id), str(parent_chain_id))
        
        if not os.path.exists(replays_dir):
            return jsonify({'replays': []}), 200
        
        replays = []
        for filename in os.listdir(replays_dir):
            if filename.endswith('.json'):
                filepath = os.path.join(replays_dir, filename)
                try:
                    with open(filepath, 'r') as f:
                        replay_data = json.load(f)
                        replays.append(replay_data)
                except Exception as e:
                    logger.error(f"Error reading replay file {filename}: {str(e)}")
                    continue
        
        # Sort by timestamp descending (newest first)
        replays.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        return jsonify({'replays': replays}), 200
        
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@replay_bp.route('/storage/replay_favourites/<thread_id>/<parent_chain_id>/<chain_id>', methods=['DELETE'])
@requires_auth
def delete_replay_favourite(thread_id, parent_chain_id, chain_id):
    """Delete a specific replay"""
    
    try:
        replay_file = user_path('storage', 'replays', str(thread_id), str(parent_chain_id), f'{chain_id}.json')
        
        if not os.path.exists(replay_file):
            return jsonify({'error': 'Replay not found'}), 404
        
        os.remove(replay_file)
        
        # Check if parent directory is empty and remove it
        parent_dir = os.path.dirname(replay_file)
        if os.path.isdir(parent_dir) and not os.listdir(parent_dir):
            os.rmdir(parent_dir)
            
            # Check if thread directory is empty and remove it
            thread_dir = os.path.dirname(parent_dir)
            if os.path.isdir(thread_dir) and not os.listdir(thread_dir):
                os.rmdir(thread_dir)
        
        return jsonify({'message': 'Replay deleted successfully'}), 200
        
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@replay_bp.route('/load_replay/<thread_id>/<parent_chain_id>/<chain_id>', methods=['GET'])
@requires_auth
def load_replay_content(thread_id, parent_chain_id, chain_id):
    """Load replay content and return parent chain info for global state"""
    
    try:
        # Load the replay file
        replay_file = user_path('storage', 'replays', str(thread_id), str(parent_chain_id), f'{chain_id}.json')
        
        if not os.path.exists(replay_file):
            return jsonify({'error': 'Replay not found'}), 404
        
        with open(replay_file, 'r') as f:
            replay_data = json.load(f)
        
        # IMPORTANT: Replace the replay's chain_id with parent_chain_id in the content
        # This ensures LLM context restoration uses the parent chain
        replay_data['chain_id'] = int(parent_chain_id)
        replay_data['thread_id'] = thread_id
        
        # Return replay content with parent chain IDs embedded
        return jsonify({
            'content': replay_data,
            'parent_chain_id': int(parent_chain_id),
            'parent_thread_id': thread_id,
            'replay_chain_id': int(chain_id)  # Keep original for reference
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500