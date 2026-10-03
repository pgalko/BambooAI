"""
Cleanup utilities for BambooAI
Handles cleanup of threads, datasets, and temporary files for users
"""

import os
import glob
import shutil
import gc
import time
import json

from logger_config import get_logger

logger = get_logger(__name__)


def get_user_path(user_id, root, *paths):
    """Helper to build user-specific paths"""
    return os.path.join(root, user_id, *paths)

def cleanup_and_remove_bamboo_instance(session_id, bamboo_ai_instances):
    """
    Safely cleans up and removes a BambooAI instance for a given session.
    It calls the instance's cleanup method to stop threads before deletion.
    """
    if session_id in bamboo_ai_instances:
        logger.info(f"Starting cleanup for BambooAI instance with session_id: {session_id}")
        instance = bamboo_ai_instances.get(session_id)
        
        # 1. Call the explicit cleanup method on the instance.
        # This will signal threads to stop and release resources.
        if instance and hasattr(instance, 'cleanup'):
            try:
                instance.cleanup()
            except Exception as e:
                logger.error(f"Error during BambooAI instance cleanup for session {session_id}: {str(e)}")
        
        # 2. Now that the instance is idle, remove the reference from our dictionary.
        del bamboo_ai_instances[session_id]
        
        # 3. Suggest to the garbage collector that now is a good time to run.
        gc.collect()
        
        logger.info(f"Successfully cleaned and removed BambooAI instance for session_id: {session_id}")

def cleanup_old_user_sessions(user_id, current_session_id, user_session_mapping, 
                             bamboo_ai_instances, user_preferences):
    """Clean up old sessions for a user, keeping only the current one"""
    
    # Get the previously stored session for this user
    old_session_id = user_session_mapping.get(user_id)
    
    if old_session_id and old_session_id != current_session_id:
        logger.info(f"Cleaning up old session {old_session_id} for user {user_id}, keeping current session {current_session_id}")
        
        # Clean up old session from all dictionaries
        if old_session_id in bamboo_ai_instances:
            cleanup_and_remove_bamboo_instance(old_session_id, bamboo_ai_instances)
            logger.info(f"Removed old BambooAI instance for session {old_session_id}")
        
        if old_session_id in user_preferences:
            del user_preferences[old_session_id]
            logger.info(f"Removed old preferences for session {old_session_id}")
        
        # Force garbage collection to free memory immediately
        gc.collect()
        
        logger.info(f"Successfully cleaned up old session {old_session_id} for user {user_id}")
    
    # Update the mapping with the current session
    user_session_mapping[user_id] = current_session_id

def _remove_documents(user_id, thread_id):
    """A thread's documents folder goes with the thread (docs/DOCUMENTS_DESIGN.md)."""
    folder = get_user_path(user_id, 'storage', 'documents', str(thread_id))
    if os.path.isdir(folder):
        shutil.rmtree(folder, ignore_errors=True)


def cleanup_orphan_documents(user_id, max_age_seconds=24 * 3600):
    """Documents folders whose thread never got a question - the upload minted the thread and
    nothing followed - are removed once they are a day old; a thread with a JSON or a favourite is kept."""
    root = get_user_path(user_id, 'storage', 'documents')
    if not os.path.isdir(root):
        return 0
    threads_dir = get_user_path(user_id, 'storage', 'threads')
    favourites_dir = get_user_path(user_id, 'storage', 'favourites')
    removed = 0
    for thread_id in os.listdir(root):
        folder = os.path.join(root, thread_id)
        if not os.path.isdir(folder):
            continue
        has_thread = os.path.exists(os.path.join(threads_dir, f"{thread_id}.json")) or os.path.isdir(os.path.join(favourites_dir, thread_id))
        if has_thread:
            continue
        try:
            age = time.time() - os.path.getmtime(folder)
        except OSError:
            continue
        if age > max_age_seconds:
            shutil.rmtree(folder, ignore_errors=True)
            removed += 1
    return removed


def cleanup_threads_for_user(user_id, debug_mode=False):
    """Clean up thread files for a specific user that don't have matching IDs in favorites
    Also cleans up iframe figures
    """
    if debug_mode:
        return
    
    start_time = time.time()
    
    # Clean up threads that are not in favorites
    favorites_dir = get_user_path(user_id, 'storage', 'favourites')
    favorite_thread_ids = set()
    
    if os.path.exists(favorites_dir):
        favorite_thread_ids = {d for d in os.listdir(favorites_dir) 
                             if os.path.isdir(os.path.join(favorites_dir, d))}
    
    threads_dir = get_user_path(user_id, 'storage', 'threads')
    threads_deleted = 0
    chains_cleaned = 0
    
    if os.path.exists(threads_dir):
        thread_files = glob.glob(os.path.join(threads_dir, '*.json'))
        for thread_file in thread_files:
            thread_id = os.path.basename(thread_file).split('.')[0]
            
            if thread_id not in favorite_thread_ids:
                # Delete entire thread if not in favorites
                try:
                    os.remove(thread_file)
                    threads_deleted += 1
                except Exception as e:
                    logger.error(f"Failed to delete {thread_id}: {str(e)}")
                _remove_documents(user_id, thread_id)
            else:
                # Thread exists in favorites - clean unfavorited chains
                try:
                    # Get favorited chain IDs for this thread
                    thread_favorites_dir = os.path.join(favorites_dir, thread_id)
                    favorite_chain_ids = set()
                    
                    if os.path.exists(thread_favorites_dir):
                        favorite_chain_ids = {
                            f.split('.')[0] 
                            for f in os.listdir(thread_favorites_dir)
                            if f.endswith('.json')
                        }
                    
                    # Load the thread JSON
                    with open(thread_file, 'r') as f:
                        thread_data = json.load(f)
                    
                    # Check if there are chains to clean
                    if 'chains' in thread_data:
                        original_chain_count = len(thread_data['chains'])
                        
                        # Filter chains to keep only favorited ones
                        filtered_chains = {
                            chain_id: chain_data 
                            for chain_id, chain_data in thread_data['chains'].items()
                            if chain_id in favorite_chain_ids
                        }
                        
                        # Only write back if we actually removed chains
                        if len(filtered_chains) < original_chain_count:
                            thread_data['chains'] = filtered_chains
                            
                            with open(thread_file, 'w') as f:
                                json.dump(thread_data, f, indent=2)
                            
                            chains_cleaned += original_chain_count - len(filtered_chains)
                
                except Exception as e:
                    logger.error(f"Failed to clean chains in {thread_id}: {str(e)}")

    orphans = cleanup_orphan_documents(user_id)
    elapsed_time = time.time() - start_time
    logger.info(f"Thread cleanup: {threads_deleted} deleted, {chains_cleaned} chains cleaned, {orphans} orphan documents folder(s) removed in {elapsed_time:.3f}s")


    # Clean up iframe figures
    iframe_dir = get_user_path(user_id, 'iframe_figures')
    if os.path.exists(iframe_dir):
        iframe_files = glob.glob(os.path.join(iframe_dir, '*'))
        for iframe_file in iframe_files:
            try:
                if os.path.isfile(iframe_file):
                    os.remove(iframe_file)
                elif os.path.isdir(iframe_file):
                    import shutil
                    shutil.rmtree(iframe_file)
            except Exception as e:
                logger.error(f"Failed to delete iframe {os.path.basename(iframe_file)}: {str(e)}")


def clear_datasets_folder_for_user(user_id):
    """Clear datasets folder for a specific user"""
    datasets_dir = get_user_path(user_id, 'datasets')
    generated_datasets_base_dir = os.path.join(datasets_dir, 'generated')
    favorites_base_dir = get_user_path(user_id, 'storage', 'favourites')

    # Get favorite thread IDs
    favorite_thread_ids = set()
    if os.path.exists(favorites_base_dir):
        try:
            favorite_thread_ids = {
                d for d in os.listdir(favorites_base_dir)
                if os.path.isdir(os.path.join(favorites_base_dir, d))
            }
            logger.info(f"Favorite thread IDs for user {user_id} dataset cleanup: {list(favorite_thread_ids)}")
        except Exception as e:
            logger.error(f"Error reading favorites directory {favorites_base_dir}: {e}")

    if not os.path.exists(datasets_dir):
        logger.info(f"'{datasets_dir}' folder does not exist for user {user_id}, no need to clear.")
        return

    # Clean up datasets directory
    try:
        for item_name in os.listdir(datasets_dir):
            item_path = os.path.join(datasets_dir, item_name)
            try:
                if os.path.isfile(item_path) or os.path.islink(item_path):
                    os.unlink(item_path)
                    logger.info(f"Deleted file for user {user_id}: {item_path}")
                elif os.path.isdir(item_path):
                    if item_name == 'generated' and os.path.exists(generated_datasets_base_dir):
                        logger.info(f"Processing 'generated' subdirectory for user {user_id}: {generated_datasets_base_dir}")
                        for generated_thread_id_dir_name in os.listdir(generated_datasets_base_dir):
                            thread_specific_dir_path = os.path.join(generated_datasets_base_dir, generated_thread_id_dir_name)
                            if os.path.isdir(thread_specific_dir_path):
                                if generated_thread_id_dir_name not in favorite_thread_ids:
                                    shutil.rmtree(thread_specific_dir_path)
                                    logger.info(f"Deleted non-favorited generated dataset directory for user {user_id}: {thread_specific_dir_path}")
                                else:
                                    logger.info(f"Kept favorited generated dataset directory for user {user_id}: {thread_specific_dir_path}")
                    elif item_name != 'generated':
                        logger.warning(f"Skipping deletion of non-'generated' subdirectory for user {user_id}: {item_path}")
            except Exception as e:
                logger.error(f'Failed to process item {item_path} for user {user_id}. Reason: {e}')
        logger.info(f"Selective cleanup of '{datasets_dir}' folder completed for user {user_id}.")
    except Exception as e:
        logger.error(f"Error listing contents of '{datasets_dir}' for user {user_id}: {str(e)}")


def ensure_user_directories(user_id):
    """Ensure all necessary directories exist for a specific user"""
    # Base directories that each user needs
    base_dirs = ['temp', 'iframe_figures', 'logs', 'datasets', 'storage']
    
    for base in base_dirs:
        dir_path = os.path.join(base, user_id)
        os.makedirs(dir_path, exist_ok=True)
    
    # Specific subdirectories
    specific_dirs = [
        get_user_path(user_id, 'storage', 'favourites'),
        get_user_path(user_id, 'storage', 'threads')
    ]
    
    for dir_path in specific_dirs:
        os.makedirs(dir_path, exist_ok=True)


def cleanup_user_on_auth(user_id, debug_mode=False):
    """Complete cleanup for a user when they authenticate"""
    cleanup_threads_for_user(user_id, debug_mode)
    clear_datasets_folder_for_user(user_id)