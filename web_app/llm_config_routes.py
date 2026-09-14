# Updated llm_config_routes.py with subscription tier support
import json
import os

from flask import Blueprint, request, jsonify
from auth import requires_auth, get_current_user_id
from auth.supabase_client import (
    get_user_llm_config, 
    save_user_llm_config, 
    delete_user_llm_config,
    get_user_subscription  # Add this import
)
from llm_config_builder import build_user_config  # Import the builder

from logger_config import get_logger
logger = get_logger(__name__)

# Create Blueprint
llm_config_bp = Blueprint('llm_config', __name__, url_prefix='/api/llm-config')

def _adaptive_dial_default(user_id, preference):
    """The tier's adaptive_max_investigations, for the interface dial.

    THE SIMPLIFICATION (2026-08-18): the dial must open at the tier's
    real budget. Prefer the user's BUILT config (the runner's own
    source of truth); fall back to the template's tier row; fall back
    to the module default. Never raises - the dial is cosmetic here,
    the server clamps at run time regardless."""
    try:
        path = os.path.join('config', str(user_id), 'LLM_CONFIG.json')
        with open(path, encoding='utf-8') as f:
            v = json.load(f).get('adaptive_max_investigations')
        if v:
            return int(v)
    except Exception:
        pass
    try:
        with open('LLM_CONFIG_template.json', encoding='utf-8') as f:
            tier = json.load(f).get('tier_properties', {}).get(
                preference or 'cost', {})
        v = tier.get('adaptive_max_investigations')
        if v:
            return int(v)
    except Exception:
        pass
    return 9


@llm_config_bp.route('', methods=['GET'])
@requires_auth
def get_config():
    """Get user's model preference configuration"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'config': {}}), 200
        
        # Get subscription to determine tier
        subscription_result = get_user_subscription(user_id)
        subscription_data = subscription_result.get('data', {}) if subscription_result.get('ok') else {}
        model_tier = subscription_data.get('model_tier', 'free')
        
        if model_tier == 'free':
            # Free tier always uses Groq
            return jsonify({
                'config': {
                    'model_preference': 'cost',
                    'tier': 'free',
                    'adaptive_max_investigations':
                        _adaptive_dial_default(user_id, 'free')
                }
            }), 200
        
        # Get preference for managed tier
        preference = get_user_llm_config(user_id)
        
        return jsonify({
            'config': {
                'model_preference': preference,
                'tier': model_tier,
                'adaptive_max_investigations':
                    _adaptive_dial_default(user_id, preference)
            }
        }), 200
        
    except Exception as e:
        return jsonify({'error': f'Error getting config: {str(e)}'}), 500


@llm_config_bp.route('', methods=['POST'])
@requires_auth
def save_config():
    """Save user's model preference"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Not available in demo mode'}), 400
        
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        # Get subscription
        subscription_result = get_user_subscription(user_id)
        subscription_data = subscription_result.get('data', {}) if subscription_result.get('ok') else {}
        model_tier = subscription_data.get('model_tier', 'free')
        
        # Determine preference
        if model_tier == 'free':
            preference = 'free'
        else:
            preference = data.get('model_preference', 'cost')
        
        # Save preference
        success = save_user_llm_config(user_id, {'model_preference': preference})
        
        if not success:
            return jsonify({'error': 'Failed to save preference'}), 500
        
        config_built = build_user_config(
            user_id=user_id,
            subscription_data=subscription_data,
            model_preference=preference,
            force_rebuild=True
        )
        
        if config_built:
            return jsonify({'message': f'Configuration updated to {preference} mode'}), 200
        else:
            return jsonify({'error': 'Preference saved but config rebuild failed'}), 500
            
    except Exception as e:
        return jsonify({'error': f'Error saving config: {str(e)}'}), 500


@llm_config_bp.route('', methods=['DELETE'])
@requires_auth
def delete_config():
    """Delete user's LLM configuration"""
    try:
        user_id = get_current_user_id()
        if not user_id:
            return jsonify({'error': 'Not available in demo mode'}), 400
        
        success = delete_user_llm_config(user_id)
        
        if success:
            # Rebuild config with free tier (Groq) after deletion
            subscription_result = get_user_subscription(user_id)
            subscription_data = subscription_result.get('data', {}) if subscription_result.get('ok') else {}
            
            build_user_config(
                user_id=user_id,
                subscription_data=subscription_data,
                force_rebuild=True
            )
            
            return jsonify({'message': 'Configuration deleted, reverted to free tier'}), 200
        else:
            return jsonify({'error': 'Failed to delete configuration'}), 500
            
    except Exception as e:
        return jsonify({'error': f'Error deleting config: {str(e)}'}), 500