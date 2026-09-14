# labels_routes.py
"""
Flask blueprint for managing labels functionality
"""

import logging
from flask import Blueprint, request, jsonify
from auth import requires_auth, get_current_user_id
from auth.supabase_client import get_service_client
import os
import json
import glob

from logger_config import get_logger
logger = get_logger(__name__)

# Create blueprint
labels_bp = Blueprint('labels', __name__)


def get_user_bamboo_id():
    """Extract bamboo_user_id from auth0_id"""
    try:
        auth0_id = get_current_user_id()
        if '|' in auth0_id:
            return auth0_id.split('|')[1]
        return auth0_id
    except Exception as e:
        logger.error(f"Error getting bamboo_user_id: {str(e)}")
        return None


@labels_bp.route('/api/labels', methods=['GET'])
@requires_auth
def get_user_labels():
    """Get all labels for the current user"""
    try:
        bamboo_user_id = get_user_bamboo_id()
        if not bamboo_user_id:
            return jsonify({'error': 'User identification failed'}), 401
        
        service_client = get_service_client()
        
        # Fetch user's labels
        result = service_client.table('labels').select(
            'id, label, created_at'
        ).eq('bamboo_user_id', bamboo_user_id).order('label').execute()
        
        labels = result.data if result.data else []
        
        return jsonify({
            'success': True,
            'labels': labels
        }), 200
        
    except Exception as e:
        logger.error(f"Error fetching labels: {str(e)}")
        return jsonify({'error': 'Failed to fetch labels'}), 500


@labels_bp.route('/api/labels', methods=['POST'])
@requires_auth
def create_label():
    """Create a new label for the current user"""
    try:
        bamboo_user_id = get_user_bamboo_id()
        if not bamboo_user_id:
            return jsonify({'error': 'User identification failed'}), 401
        
        data = request.json
        label_name = data.get('label', '').strip()
        
        # Validate label name
        if not label_name:
            return jsonify({'error': 'Label name is required'}), 400
        
        if len(label_name) > 50:  # Reasonable limit
            return jsonify({'error': 'Label name too long (max 50 characters)'}), 400
        
        service_client = get_service_client()
        
        # Check if label already exists for this user
        existing = service_client.table('labels').select('id').eq(
            'bamboo_user_id', bamboo_user_id
        ).eq('label', label_name).execute()
        
        if existing.data:
            return jsonify({'error': 'Label already exists'}), 409
        
        # Create new label
        result = service_client.table('labels').insert({
            'bamboo_user_id': bamboo_user_id,
            'label': label_name
        }).execute()
        
        if result.data:
            new_label = result.data[0]
            return jsonify({
                'success': True,
                'label': {
                    'id': new_label['id'],
                    'label': new_label['label'],
                    'created_at': new_label.get('created_at')
                }
            }), 201
        else:
            return jsonify({'error': 'Failed to create label'}), 500
            
    except Exception as e:
        logger.error(f"Error creating label: {str(e)}")
        return jsonify({'error': 'Failed to create label'}), 500


@labels_bp.route('/api/labels/<int:label_id>', methods=['DELETE'])
@requires_auth
def delete_label(label_id):
    """Delete a label and clean up JSON files"""
    try:
        bamboo_user_id = get_user_bamboo_id()
        if not bamboo_user_id:
            return jsonify({'error': 'User identification failed'}), 401
        
        service_client = get_service_client()
        
        # Call the database function to delete label and get affected chains
        result = service_client.rpc('delete_label_and_get_chains', {
            'p_label_id': label_id,
            'p_bamboo_user_id': bamboo_user_id
        }).execute()
        
        if not result.data or not result.data.get('success'):
            error_msg = result.data.get('error') if result.data else 'Failed to delete label'
            return jsonify({'error': error_msg}), 404
        
        # Extract affected chain IDs
        affected_chains = result.data.get('affected_chains', [])
        label_name = result.data.get('label_name')
        
        cleaned_count = 0
        for chain_id in affected_chains:
            # Find the JSON file for this chain
            chain_file_pattern = os.path.join('storage', bamboo_user_id, 'favourites', '*', f'{chain_id}.json')
            chain_files = glob.glob(chain_file_pattern)
            
            for chain_file in chain_files:
                try:
                    # Read the JSON file
                    with open(chain_file, 'r') as f:
                        chain_data = json.load(f)
                    
                    # Remove label fields
                    if 'label_id' in chain_data:
                        del chain_data['label_id']
                    if 'label_name' in chain_data:
                        del chain_data['label_name']
                    
                    # Write back
                    with open(chain_file, 'w') as f:
                        json.dump(chain_data, f, indent=2)
                    
                    cleaned_count += 1
                    logger.info(f"Removed label from JSON file: {chain_file}")
                    
                except Exception as e:
                    logger.warning(f"Could not update JSON file {chain_file}: {str(e)}")
        
        logger.info(f"Label '{label_name}' deleted, cleaned {cleaned_count} JSON files")
        
        return jsonify({
            'success': True,
            'message': f'Label deleted and removed from {cleaned_count} chains',
            'affected_chains': len(affected_chains)
        }), 200
        
    except Exception as e:
        logger.error(f"Error deleting label: {str(e)}")
        return jsonify({'error': 'Failed to delete label'}), 500


@labels_bp.route('/api/chains/<chain_id>/label', methods=['PUT'])
@requires_auth
def assign_label_to_chain(chain_id):
    """Assign a label to a chain"""
    try:
        bamboo_user_id = get_user_bamboo_id()
        if not bamboo_user_id:
            return jsonify({'error': 'User identification failed'}), 401
        
        data = request.json
        label_id = data.get('label_id')  # Can be None to remove label
        
        service_client = get_service_client()
        
        # Get thread_id for this chain
        chain_check = service_client.table('chains').select('id, thread_id, threads(thread_id)').eq(
            'chain_id', chain_id
        ).eq('bamboo_user_id', bamboo_user_id).execute()
        
        if not chain_check.data:
            return jsonify({'error': 'Chain not found or access denied'}), 404
        
        # Extract the actual thread_id string from the relationship
        thread_id_str = chain_check.data[0]['threads']['thread_id']
        
        # If label_id provided, verify ownership and get label name
        label_name = None
        if label_id is not None:
            label_check = service_client.table('labels').select('id, label').eq(
                'id', label_id
            ).eq('bamboo_user_id', bamboo_user_id).execute()
            
            if not label_check.data:
                return jsonify({'error': 'Label not found or access denied'}), 404
            label_name = label_check.data[0]['label']
        
        # Update chain with label in DB
        result = service_client.table('chains').update({
            'label_id': label_id
        }).eq('chain_id', chain_id).eq('bamboo_user_id', bamboo_user_id).execute()
        
        if not result.data:
            return jsonify({'error': 'Failed to update chain'}), 500
        
        # Get user_id from bamboo_user_id (already extracted at top of function)
        # Path structure: storage/user_id/favourites/thread_id/chain_id.json
        chain_file = os.path.join('storage', bamboo_user_id, 'favourites', thread_id_str, f'{chain_id}.json')
        
        if os.path.exists(chain_file):
            try:
                # Read existing JSON
                with open(chain_file, 'r') as f:
                    chain_data = json.load(f)
                
                # Update label fields
                chain_data['label_id'] = label_id
                chain_data['label_name'] = label_name
                
                # Write back
                with open(chain_file, 'w') as f:
                    json.dump(chain_data, f, indent=2)
                    
                logger.info(f"Updated JSON file with label: {chain_file}")
            except Exception as e:
                logger.error(f"Error updating JSON file: {str(e)}")
                # Don't fail the request if JSON update fails, DB is source of truth
        else:
            logger.warning(f"JSON file not found: {chain_file}")
        
        return jsonify({
            'success': True,
            'label_id': label_id,
            'label_name': label_name
        }), 200
            
    except Exception as e:
        logger.error(f"Error assigning label to chain: {str(e)}")
        return jsonify({'error': 'Failed to assign label'}), 500


@labels_bp.route('/api/chains/<chain_id>/label', methods=['GET'])
@requires_auth
def get_chain_label(chain_id):
    """Get the label assigned to a chain"""
    try:
        bamboo_user_id = get_user_bamboo_id()
        if not bamboo_user_id:
            return jsonify({'error': 'User identification failed'}), 401
        
        service_client = get_service_client()
        
        # Get chain with its label
        result = service_client.table('chains').select(
            'label_id, labels(id, label)'
        ).eq('chain_id', chain_id).eq('bamboo_user_id', bamboo_user_id).execute()
        
        if result.data:
            chain_data = result.data[0]
            label_info = chain_data.get('labels')
            
            return jsonify({
                'success': True,
                'label': label_info
            }), 200
        else:
            return jsonify({'error': 'Chain not found'}), 404
            
    except Exception as e:
        logger.error(f"Error getting chain label: {str(e)}")
        return jsonify({'error': 'Failed to get chain label'}), 500
    
@labels_bp.route('/api/labels/<int:label_id>/chains', methods=['GET'])
@requires_auth
def get_chains_by_label(label_id):
    """Get all chains associated with a specific label"""
    try:
        bamboo_user_id = get_user_bamboo_id()
        if not bamboo_user_id:
            return jsonify({'error': 'User identification failed'}), 401
        
        service_client = get_service_client()
        
        # Verify label ownership
        label_check = service_client.table('labels').select('label').eq(
            'id', label_id
        ).eq('bamboo_user_id', bamboo_user_id).execute()
        
        if not label_check.data:
            return jsonify({'error': 'Label not found or access denied'}), 404
        
        label_name = label_check.data[0]['label']
        
        # Get chains with this label
        chains_result = service_client.table('chains').select(
            'chain_id, thread_id, threads(thread_id)'
        ).eq('bamboo_user_id', bamboo_user_id).eq('label_id', label_id).execute()
        
        chain_ids = [chain['chain_id'] for chain in chains_result.data] if chains_result.data else []
        
        # Include thread_ids in response
        chains = [{'chain_id': chain['chain_id'], 'thread_id': chain['thread_id']} 
                  for chain in chains_result.data] if chains_result.data else []
        
        return jsonify({
            'success': True,
            'label_name': label_name,
            'chain_ids': chain_ids,
            'chains': chains,  # Added this with full chain info
            'count': len(chain_ids)
        }), 200
        
    except Exception as e:
        logger.error(f"Error fetching chains by label: {str(e)}")
        return jsonify({'error': 'Failed to fetch chains'}), 500
    
# Endpoint to get dataset metadata for a specific chain
@labels_bp.route('/api/chains/<string:chain_id>/datasets', methods=['GET'])
@requires_auth
def get_chain_datasets(chain_id):
    """Get dataset metadata for a specific chain"""
    try:
        bamboo_user_id = get_user_bamboo_id()
        if not bamboo_user_id:
            return jsonify({'error': 'User identification failed'}), 401
        
        service_client = get_service_client()
        
        # First, get the internal id from chains table using the text chain_id
        chain_result = service_client.table('chains').select('id').eq(
            'chain_id', chain_id  # text chain_id
        ).eq('bamboo_user_id', bamboo_user_id).execute()
        
        if not chain_result.data:
            return jsonify({'error': 'Chain not found or access denied'}), 404
        
        # Get the internal integer id
        chain_internal_id = chain_result.data[0]['id']
        
        # Get dataset metadata using the integer id
        datasets = service_client.table('dataset_metadata').select('*').eq(
            'chain_id', chain_internal_id  # integer chain_id (foreign key)
        ).eq('bamboo_user_id', bamboo_user_id).execute()
        
        # Separate primary and auxiliary datasets
        primary = None
        auxiliary = []
        
        for dataset in datasets.data:
            if dataset['type'] == 'Primary':
                primary = dataset
            else:
                auxiliary.append(dataset)
        
        return jsonify({
            'success': True,
            'primary': primary,
            'auxiliary': auxiliary
        }), 200
        
    except Exception as e:
        logger.error(f"Error fetching datasets for chain {chain_id}: {str(e)}")
        return jsonify({'error': 'Failed to fetch datasets'}), 500