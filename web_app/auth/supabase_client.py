import os
import base64
import logging
import time
from datetime import datetime, timedelta
from collections import defaultdict
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from supabase import create_client, Client
from flask import g
from typing import Optional, Any, Union

from logger_config import get_logger
logger = get_logger(__name__)

# Configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')


# Global client instances
_supabase_client = None
_service_client = None

# Global encryption instance
_fernet = None

def _get_fernet():
    """Get Fernet encryption instance (cached)"""
    global _fernet
    
    if _fernet is None:
        password = os.getenv('LLM_CONFIG_ENCRYPTION_KEY')
        if not password:
            raise ValueError("LLM_CONFIG_ENCRYPTION_KEY must be set in environment")
        
        # Use fixed salt for consistency
        salt = b'llm_config_salt_2024'
        
        # Generate key from password
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        _fernet = Fernet(key)
    
    return _fernet

def _encrypt_value(value: str) -> str:
    """Encrypt a string value"""
    if not value:
        return ""
    
    try:
        fernet = _get_fernet()
        encrypted = fernet.encrypt(value.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    except Exception as e:
        logger.error(f"Encryption error: {str(e)}")
        return ""

def _decrypt_value(encrypted_value: str) -> str:
    """Decrypt a string value"""
    if not encrypted_value:
        return ""
    
    try:
        fernet = _get_fernet()
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_value.encode())
        decrypted = fernet.decrypt(encrypted_bytes)
        return decrypted.decode()
    except Exception as e:
        logger.error(f"Decryption error: {str(e)}")
        return ""


def get_supabase_client() -> Client:
    """Get Supabase client instance with user context for RLS"""
    global _supabase_client
    
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise Exception("Supabase credentials not configured")
    
    # Always create a fresh client to avoid connection issues
    _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _supabase_client


def get_service_client() -> Client:
    """Get service role client for admin operations (bypasses RLS)"""
    global _service_client
    
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise Exception("Supabase service role credentials not configured")
    
    # Always create a fresh client to avoid connection issues
    _service_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return _service_client

def validate_user_access(auth0_id: str) -> bool:
    """
    Validate that the requested auth0_id matches the authenticated user
    
    Args:
        auth0_id: The auth0_id being requested
        
    Returns:
        bool: True if access is authorized, False otherwise
    """
    
    current_user = getattr(g, 'current_user_id', None)
    return current_user is not None and current_user == auth0_id


def init_supabase_tables():
    """Initialize required tables and RLS policies in Supabase"""
    
    logger.info("🔧 Initializing Supabase tables with RLS...")

# =============================================================================
# LLM CONFIGURATION FUNCTIONS
# =============================================================================

def get_user_llm_config(auth0_id: str) -> dict:
    """Get user's model preference configuration"""
    
    if not validate_user_access(auth0_id):
        return {"error": "Unauthorized access"}
    
    try:
        service_client = get_service_client()
        result = service_client.table('llm_config').select('*').eq('auth0_id', auth0_id).execute()
        
        if not result.data:
            preference = 'free'  # Default to free if no config
            return preference
        
        preference = result.data[0].get('model_preference', 'cost')
        
        # Return boolean flags based on preference
        return preference
        
    except Exception as e:
        logger.error(f"Error getting LLM config: {str(e)}")
        # Default to cost on error
        preference = 'free'
        return preference


def save_user_llm_config(auth0_id: str, config: dict) -> bool:
    """Save user's model preference"""
    
    if not validate_user_access(auth0_id):
        return False
    
    try:
        service_client = get_service_client()
        
        # Get user_id
        user_result = service_client.table('users').select('id').eq('auth0_id', auth0_id).execute()
        if not user_result.data:
            return False
        
        user_id = user_result.data[0]['id']
        
        # Extract preference from config
        preference = config.get('model_preference', 'cost')
        
        # Validate preference
        if preference not in ['cost', 'performance', 'max']:
            preference = 'free'
        
        # Check if record exists
        existing = service_client.table('llm_config').select('*').eq('auth0_id', auth0_id).execute()
        
        if existing.data:
            # Update existing
            result = service_client.table('llm_config').update({
                'model_preference': preference
            }).eq('auth0_id', auth0_id).execute()
        else:
            # Create new
            result = service_client.table('llm_config').insert({
                'user_id': user_id,
                'auth0_id': auth0_id,
                'model_preference': preference
            }).execute()
        
        return bool(result.data)
        
    except Exception as e:
        logger.error(f"Error saving LLM config: {str(e)}")
        return False


def delete_user_llm_config(auth0_id: str) -> bool:
    """Delete user's LLM configuration"""
    
    # Security validation
    if not validate_user_access(auth0_id):
        return {"error": "Unauthorized access"}
    
    try:
        service_client = get_service_client()
        result = service_client.table('llm_config').delete().eq('auth0_id', auth0_id).execute()
        return True
        
    except Exception as e:
        logger.error(f"Error deleting LLM config: {str(e)}")
        return False

# =============================================================================
# SWEATSTACK INTEGRATION FUNCTIONS  
# =============================================================================

def store_sweatstack_token(bamboo_user_id: str, auth0_id: str, token_data: dict) -> bool:
    """Store complete SweatStack token data in database (encrypted)"""
    
    # Security validation
    if not validate_user_access(auth0_id):
        logger.warning(f"Unauthorized access attempt for SweatStack token storage: {auth0_id}")
        return False
    
    try:
        service_client = get_service_client()
        
        # Extract and encrypt sensitive token fields with safety checks
        created_at = datetime.utcnow()
        
        # Calculate expires_at safely
        expires_in = token_data.get('expires_in', 3600)  # Default to 1 hour if missing
        expires_at = created_at + timedelta(seconds=expires_in)
        
        token_record = {
            'bamboo_user_id': bamboo_user_id,
            'auth0_id': auth0_id,
            # Encrypt sensitive tokens - handle missing tokens gracefully
            'access_token': _encrypt_value(token_data.get('access_token', '')),
            'refresh_token': _encrypt_value(token_data.get('refresh_token', '')),
            'id_token': _encrypt_value(token_data.get('id_token', '')),
            # Store non-sensitive metadata in plaintext with safe defaults
            'token_type': token_data.get('token_type', 'Bearer'),
            'expires_in': expires_in,
            'scope': token_data.get('scope', ''),
            'expires_at': expires_at.isoformat(),
            'created_at': created_at.isoformat(),
            'updated_at': created_at.isoformat()
        }
        
        # Validate that we have the essential access_token
        if not token_data.get('access_token'):
            logger.warning(f"Error: Missing access_token for user {bamboo_user_id}")
            return False
        
        result = service_client.table('sweatstack_integration').upsert(token_record).execute()
        
        if result.data:
            logger.info(f'SweatStack token stored in DB for user: {bamboo_user_id}')
            return True
        else:
            logger.error(f'Failed to store SweatStack token for user: {bamboo_user_id}')
            return False
        
    except Exception as e:
        logger.error(f"Error storing SweatStack token for user {bamboo_user_id}: {str(e)}")
        return False


def get_sweatstack_token(bamboo_user_id: str, auth0_id: str) -> str:
    """Retrieve SweatStack access token from database (with expiration check)"""
    
    # Security validation
    if not validate_user_access(auth0_id):
        logger.warning(f"Unauthorized access attempt for SweatStack token retrieval: {auth0_id}")
        return None
    
    try:
        service_client = get_service_client()
        result = service_client.table('sweatstack_integration').select(
            'access_token, refresh_token, expires_at, updated_at'
        ).eq('bamboo_user_id', bamboo_user_id).execute()
        
        if not result.data:
            return None
        
        token_data = result.data[0]
        
        # Check if token is expired (handle missing expires_at gracefully)
        expires_at_str = token_data.get('expires_at')
        if expires_at_str:
            try:
                expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
                if datetime.utcnow().replace(tzinfo=expires_at.tzinfo) >= expires_at:
                    logger.warning(f'SweatStack token expired for user: {bamboo_user_id}')
                    return None
            except (ValueError, TypeError) as e:
                logger.error(f'Error parsing expires_at for user {bamboo_user_id}: {e}')
                # If we can't parse expiration, assume token is still valid but log the issue
        
        # Update last used timestamp
        try:
            service_client.table('sweatstack_integration').update({
                'last_used_at': datetime.utcnow().isoformat()
            }).eq('bamboo_user_id', bamboo_user_id).execute()
        except Exception as e:
            logger.error(f'Warning: Could not update last_used_at for user {bamboo_user_id}: {e}')
            # Don't fail the token retrieval if we can't update the timestamp
        
        # Decrypt and return access token
        access_token_encrypted = token_data.get('access_token')
        if not access_token_encrypted:
            logger.warning(f'No access token found for user: {bamboo_user_id}')
            return None
            
        access_token = _decrypt_value(access_token_encrypted)
        return access_token if access_token else None
        
    except Exception as e:
        logger.error(f"Error retrieving SweatStack token for user {bamboo_user_id}: {str(e)}")
        return None


def get_sweatstack_refresh_token(bamboo_user_id: str, auth0_id: str) -> str:
    """Retrieve SweatStack refresh token from database"""
    
    # Security validation
    if not validate_user_access(auth0_id):
        logger.warning(f"Unauthorized access attempt for SweatStack refresh token: {auth0_id}")
        return None
    
    try:
        service_client = get_service_client()
        result = service_client.table('sweatstack_integration').select(
            'refresh_token'
        ).eq('bamboo_user_id', bamboo_user_id).execute()
        
        if not result.data:
            return None
        
        refresh_token_encrypted = result.data[0].get('refresh_token')
        if not refresh_token_encrypted:
            return None
        
        # Decrypt and return refresh token
        refresh_token = _decrypt_value(refresh_token_encrypted)
        return refresh_token if refresh_token else None
        
    except Exception as e:
        logger.error(f"Error retrieving SweatStack refresh token for user {bamboo_user_id}: {str(e)}")
        return None


def update_sweatstack_tokens(bamboo_user_id: str, auth0_id: str, new_token_data: dict) -> bool:
    """Update SweatStack tokens after refresh"""
    
    # Security validation
    if not validate_user_access(auth0_id):
        logger.warning(f"Unauthorized access attempt for SweatStack token update: {auth0_id}")
        return False
    
    try:
        service_client = get_service_client()
        
        # Prepare update data with encrypted tokens - handle missing fields gracefully
        update_data = {
            'updated_at': datetime.utcnow().isoformat()
        }
        
        # Only update access_token if provided and not empty
        if new_token_data.get('access_token'):
            update_data['access_token'] = _encrypt_value(new_token_data['access_token'])
        
        # Include refresh token if provided
        if 'refresh_token' in new_token_data:
            update_data['refresh_token'] = _encrypt_value(new_token_data.get('refresh_token', ''))
        
        # Include expires_in if provided
        if 'expires_in' in new_token_data:
            expires_in = new_token_data.get('expires_in', 3600)
            update_data['expires_in'] = expires_in
            # Recalculate expires_at if expires_in is updated
            current_time = datetime.utcnow()
            update_data['expires_at'] = (current_time + timedelta(seconds=expires_in)).isoformat()
        
        # Include other optional fields if provided
        if 'token_type' in new_token_data:
            update_data['token_type'] = new_token_data.get('token_type', 'Bearer')
        
        if 'scope' in new_token_data:
            update_data['scope'] = new_token_data.get('scope', '')
        
        if 'id_token' in new_token_data:
            update_data['id_token'] = _encrypt_value(new_token_data.get('id_token', ''))
        
        result = service_client.table('sweatstack_integration').update(update_data).eq('bamboo_user_id', bamboo_user_id).execute()
        
        if result.data:
            logger.info(f'SweatStack tokens updated for user: {bamboo_user_id}')
            return True
        else:
            return False
        
    except Exception as e:
        logger.error(f"Error updating SweatStack tokens for user {bamboo_user_id}: {str(e)}")
        return False


def remove_sweatstack_token(bamboo_user_id: str, auth0_id: str) -> bool:
    """Remove SweatStack integration from database"""
    
    # Security validation
    if not validate_user_access(auth0_id):
        logger.error(f"Unauthorized access attempt for SweatStack token removal: {auth0_id}")
        return False
    
    try:
        service_client = get_service_client()
        result = service_client.table('sweatstack_integration').delete().eq('bamboo_user_id', bamboo_user_id).execute()
        logger.info(f'SweatStack token removed from DB for user: {bamboo_user_id}')
        return True
        
    except Exception as e:
        logger.error(f"Error removing SweatStack token for user {bamboo_user_id}: {str(e)}")
        return False


def is_sweatstack_token_expired(bamboo_user_id: str, auth0_id: str) -> bool:
    """Check if SweatStack token is expired"""
    
    # Security validation
    if not validate_user_access(auth0_id):
        return True
    
    try:
        service_client = get_service_client()
        result = service_client.table('sweatstack_integration').select(
            'expires_at'
        ).eq('bamboo_user_id', bamboo_user_id).execute()
        
        if not result.data:
            return True  # No token found, consider expired
        
        expires_at_str = result.data[0].get('expires_at')
        if not expires_at_str:
            return False  # No expiration time, assume valid
        
        try:
            expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
            return datetime.utcnow().replace(tzinfo=expires_at.tzinfo) >= expires_at
        except (ValueError, TypeError) as e:
            logger.error(f"Error parsing expires_at for user {bamboo_user_id}: {e}")
            return False  # If we can't parse, assume valid but log the issue
        
    except Exception as e:
        logger.error(f"Error checking SweatStack token expiration for user {bamboo_user_id}: {str(e)}")
        return True  # Assume expired on error


def get_sweatstack_integration_status(bamboo_user_id: str, auth0_id: str) -> dict:
    """Get SweatStack integration status for a user"""
    
    # Security validation
    if not validate_user_access(auth0_id):
        return {'authenticated': False, 'reason': 'unauthorized'}
    
    try:
        service_client = get_service_client()
        result = service_client.table('sweatstack_integration').select(
            'expires_at, last_used_at, scope, created_at'
        ).eq('bamboo_user_id', bamboo_user_id).execute()
        
        if not result.data:
            return {'authenticated': False, 'reason': 'no_token'}
        
        integration = result.data[0]
        
        # Check expiration
        is_expired = False
        if integration.get('expires_at'):
            expires_at = datetime.fromisoformat(integration['expires_at'].replace('Z', '+00:00'))
            is_expired = datetime.utcnow().replace(tzinfo=expires_at.tzinfo) >= expires_at
        
        return {
            'authenticated': not is_expired,
            'reason': 'expired' if is_expired else 'active',
            'expires_at': integration.get('expires_at'),
            'last_used_at': integration.get('last_used_at'),
            'scope': integration.get('scope'),
            'created_at': integration.get('created_at')
        }
        
    except Exception as e:
        logger.error(f"Error getting SweatStack integration status for user {bamboo_user_id}: {str(e)}")
        return {'authenticated': False, 'reason': 'error'}
    
# =============================================================================
# INTERVALS INTEGRATION FUNCTIONS  
# =============================================================================

def store_intervals_api_key(bamboo_user_id: str, auth0_id: str, api_key: str) -> bool:
    """Store Intervals API key in database (encrypted)"""
    
    # Security validation
    if not validate_user_access(auth0_id):
        logger.warning(f"Unauthorized access attempt for Intervals API key storage: {auth0_id}")
        return False
    
    try:
        service_client = get_service_client()
        
        # Validate API key is provided
        if not api_key:
            logger.error(f"Error: Missing API key for user {bamboo_user_id}")
            return False
        
        created_at = datetime.utcnow()
        
        key_record = {
            'bamboo_user_id': bamboo_user_id,
            'auth0_id': auth0_id,
            'api_key': _encrypt_value(api_key),  # Encrypt the API key
            'token_type': 'api_key',
            'created_at': created_at.isoformat(),
            'updated_at': created_at.isoformat(),
            'last_used_at': created_at.isoformat()
        }
        
        result = service_client.table('intervals_integration').upsert(key_record).execute()
        
        if result.data:
            logger.info(f'Intervals API key stored in DB for user: {bamboo_user_id}')
            return True
        else:
            logger.warning(f'Failed to store Intervals API key for user: {bamboo_user_id}')
            return False
        
    except Exception as e:
        logger.error(f"Error storing Intervals API key for user {bamboo_user_id}: {str(e)}")
        return False


def get_intervals_api_key(bamboo_user_id: str, auth0_id: str) -> str:
    """Retrieve Intervals API key from database"""
    
    # Security validation
    if not validate_user_access(auth0_id):
        logger.warning(f"Unauthorized access attempt for Intervals API key retrieval: {auth0_id}")
        return None
    
    try:
        service_client = get_service_client()
        result = service_client.table('intervals_integration').select(
            'api_key, updated_at'
        ).eq('bamboo_user_id', bamboo_user_id).execute()
        
        if not result.data:
            return None
        
        key_data = result.data[0]
        
        # Update last used timestamp
        try:
            service_client.table('intervals_integration').update({
                'last_used_at': datetime.utcnow().isoformat()
            }).eq('bamboo_user_id', bamboo_user_id).execute()
        except Exception as e:
            logger.error(f'Warning: Could not update last_used_at for user {bamboo_user_id}: {e}')
        
        # Decrypt and return API key
        api_key_encrypted = key_data.get('api_key')
        if not api_key_encrypted:
            logger.warning(f'No API key found for user: {bamboo_user_id}')
            return None
            
        api_key = _decrypt_value(api_key_encrypted)
        return api_key if api_key else None
        
    except Exception as e:
        logger.error(f"Error retrieving Intervals API key for user {bamboo_user_id}: {str(e)}")
        return None


def remove_intervals_api_key(bamboo_user_id: str, auth0_id: str) -> bool:
    """Remove Intervals integration from database"""
    
    # Security validation
    if not validate_user_access(auth0_id):
        logger.warning(f"Unauthorized access attempt for Intervals API key removal: {auth0_id}")
        return False
    
    try:
        service_client = get_service_client()
        result = service_client.table('intervals_integration').delete().eq('bamboo_user_id', bamboo_user_id).execute()
        logger.info(f'Intervals API key removed from DB for user: {bamboo_user_id}')
        return True
        
    except Exception as e:
        logger.error(f"Error removing Intervals API key for user {bamboo_user_id}: {str(e)}")
        return False


def get_intervals_integration_status(bamboo_user_id: str, auth0_id: str) -> dict:
    """Get Intervals integration status for a user"""
    
    # Security validation
    if not validate_user_access(auth0_id):
        return {'authenticated': False, 'has_api_key': False}
    
    try:
        service_client = get_service_client()
        result = service_client.table('intervals_integration').select(
            'api_key, last_used_at, created_at, updated_at'
        ).eq('bamboo_user_id', bamboo_user_id).execute()
        
        if not result.data or not result.data[0].get('api_key'):
            return {'authenticated': False, 'has_api_key': False}
        
        integration = result.data[0]
        
        return {
            'authenticated': True,  # Has API key
            'has_api_key': True,
            'last_used_at': integration.get('last_used_at'),
            'created_at': integration.get('created_at'),
            'updated_at': integration.get('updated_at')
        }
        
    except Exception as e:
        logger.error(f"Error getting Intervals integration status for user {bamboo_user_id}: {str(e)}")
        return {'authenticated': False, 'has_api_key': False}
    

# =============================================================================
# ENDURA INTEGRATION FUNCTIONS  
# =============================================================================

def store_endura_api_key(bamboo_user_id: str, auth0_id: str, api_key: str) -> bool:
    """Store Endura API key in database (encrypted)"""
    
    # Security validation
    if not validate_user_access(auth0_id):
        logger.warning(f"Unauthorized access attempt for Endura API key storage: {auth0_id}")
        return False
    
    try:
        service_client = get_service_client()
        
        # Validate API key is provided
        if not api_key:
            logger.error(f"Error: Missing API key for user {bamboo_user_id}")
            return False
        
        created_at = datetime.utcnow()
        
        key_record = {
            'bamboo_user_id': bamboo_user_id,
            'auth0_id': auth0_id,
            'api_key': _encrypt_value(api_key),  # Encrypt the API key
            'token_type': 'api_key',
            'created_at': created_at.isoformat(),
            'updated_at': created_at.isoformat(),
            'last_used_at': created_at.isoformat()
        }
        
        result = service_client.table('endura_integration').upsert(key_record).execute()
        
        if result.data:
            logger.info(f'Endura API key stored in DB for user: {bamboo_user_id}')
            return True
        else:
            logger.warning(f'Failed to store Endura API key for user: {bamboo_user_id}')
            return False
        
    except Exception as e:
        logger.error(f"Error storing Endura API key for user {bamboo_user_id}: {str(e)}")
        return False


def get_endura_api_key(bamboo_user_id: str, auth0_id: str) -> str:
    """Retrieve Endura API key from database"""
    
    # Security validation
    if not validate_user_access(auth0_id):
        logger.warning(f"Unauthorized access attempt for Endura API key retrieval: {auth0_id}")
        return None
    
    try:
        service_client = get_service_client()
        result = service_client.table('endura_integration').select(
            'api_key, updated_at'
        ).eq('bamboo_user_id', bamboo_user_id).execute()
        
        if not result.data:
            return None
        
        key_data = result.data[0]
        
        # Update last used timestamp
        try:
            service_client.table('endura_integration').update({
                'last_used_at': datetime.utcnow().isoformat()
            }).eq('bamboo_user_id', bamboo_user_id).execute()
        except Exception as e:
            logger.error(f'Warning: Could not update last_used_at for user {bamboo_user_id}: {e}')
        
        # Decrypt and return API key
        api_key_encrypted = key_data.get('api_key')
        if not api_key_encrypted:
            logger.warning(f'No API key found for user: {bamboo_user_id}')
            return None
            
        api_key = _decrypt_value(api_key_encrypted)
        return api_key if api_key else None
        
    except Exception as e:
        logger.error(f"Error retrieving Endura API key for user {bamboo_user_id}: {str(e)}")
        return None


def remove_endura_api_key(bamboo_user_id: str, auth0_id: str) -> bool:
    """Remove Endura integration from database"""
    
    # Security validation
    if not validate_user_access(auth0_id):
        logger.warning(f"Unauthorized access attempt for Endura API key removal: {auth0_id}")
        return False
    
    try:
        service_client = get_service_client()
        result = service_client.table('endura_integration').delete().eq('bamboo_user_id', bamboo_user_id).execute()
        logger.info(f'Endura API key removed from DB for user: {bamboo_user_id}')
        return True
        
    except Exception as e:
        logger.error(f"Error removing Endura API key for user {bamboo_user_id}: {str(e)}")
        return False


def get_endura_integration_status(bamboo_user_id: str, auth0_id: str) -> dict:
    """Get Endura integration status for a user"""
    
    # Security validation
    if not validate_user_access(auth0_id):
        return {'authenticated': False, 'has_api_key': False}
    
    try:
        service_client = get_service_client()
        result = service_client.table('endura_integration').select(
            'api_key, last_used_at, created_at, updated_at'
        ).eq('bamboo_user_id', bamboo_user_id).execute()
        
        if not result.data or not result.data[0].get('api_key'):
            return {'authenticated': False, 'has_api_key': False}
        
        integration = result.data[0]
        
        return {
            'authenticated': True,
            'has_api_key': True,
            'last_used_at': integration.get('last_used_at'),
            'created_at': integration.get('created_at'),
            'updated_at': integration.get('updated_at')
        }
        
    except Exception as e:
        logger.error(f"Error getting Endura integration status for user {bamboo_user_id}: {str(e)}")
        return {'authenticated': False, 'has_api_key': False}

# =============================================================================
# USAGE TRACKING FUNCTIONS
# =============================================================================

def get_user_usage_dashboard(auth0_id: str, period: str) -> dict:
    """Get usage dashboard data for a user with queries view support"""
    
    if not validate_user_access(auth0_id):
        return {"error": "Unauthorized access"}
    
    # Period configurations
    periods = {
        "1_day": (1, "hour", "Last 24 hours"),
        "7_days": (7, "day", "Last 7 days"), 
        "30_days": (30, "day", "Last 30 days"),
        "90_days": (90, "day", "Last 90 days")
    }
    
    if period not in periods:
        return {"error": "Invalid period"}
    
    days, group_by, description = periods[period]
    
    try:
        # Convert Auth0 ID to bamboo_user_id
        bamboo_user_id = auth0_id.split('|')[1] if '|' in auth0_id else auth0_id
        
        # Calculate date range precisely
        now = datetime.utcnow()
        
        if group_by == "hour":
            # For hourly: from 23 hours ago to current hour
            end_date = now.replace(minute=59, second=59, microsecond=999999)
            start_date = (now - timedelta(hours=23)).replace(minute=0, second=0, microsecond=0)
        else:
            # For daily: from (days-1) days ago at 00:00 to today at 23:59
            end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            start_date = (now - timedelta(days=days-1)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Fetch data with pagination
        all_data = []
        service_client = get_service_client()
        offset = 0
        limit = 1000
        
        while True:
            batch = service_client.table('usage').select(
                'timestamp, cost, prompt_tokens, completion_tokens, chain_id, agent, model, elapsed_time, compute_tier, query_cost'
            ).eq('bamboo_user_id', bamboo_user_id
            ).gte('timestamp', start_date.isoformat()
            ).lte('timestamp', end_date.isoformat()
            ).order('timestamp'
            ).range(offset, offset + limit - 1
            ).execute()
            
            if not batch.data:
                break
                
            all_data.extend(batch.data)
            
            if len(batch.data) < limit:
                break
                
            offset += limit
            
            # Safety limit: stop after 20 iterations (20,000 rows)
            if offset >= 20000:
                logging.warning(f"Reached 20k row limit for user {bamboo_user_id}")
                break
        
        # Generate all required time slots
        labels = []
        if group_by == "hour":
            # Generate exactly 24 hourly slots
            current = (now - timedelta(hours=23)).replace(minute=0, second=0, microsecond=0)
            for _ in range(24):
                labels.append(current.strftime("%Y-%m-%d %H:00"))
                current += timedelta(hours=1)
        else:
            # Generate exactly 'days' daily slots
            current = (now - timedelta(days=days-1)).replace(hour=0, minute=0, second=0, microsecond=0)
            for _ in range(days):
                labels.append(current.strftime("%Y-%m-%d"))
                current += timedelta(days=1)
        
        # Initialize data structures with zeros for all time slots
        data = {label: {"cost": 0, "input": 0, "output": 0} for label in labels}
        agent_data = defaultdict(lambda: {label: 0 for label in labels})
        model_data = defaultdict(lambda: {label: 0 for label in labels})
        
        # Query-specific tracking
        query_data = defaultdict(lambda: {
            "unique_chains": set(),
            "count": 0,
            "total_cost": 0,
            "total_elapsed": 0,
            "chain_elapsed": defaultdict(float),
            "tier_counts": defaultdict(int),  # ADD THIS
            "tier_costs": defaultdict(float)   # ADD THIS
        })
        
        totals = {"cost": 0, "input": 0, "output": 0}
        unique_chain_ids = set()
        
        # Track chains we've already counted for cost
        chain_cost_counted = {}
        
        # Process fetched data
        for record in all_data:
            timestamp_str = record['timestamp']
            try:
                # Parse timestamp
                if 'T' in timestamp_str:
                    timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00').replace('+00:00', ''))
                else:
                    timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                
                # Format key based on grouping
                key = timestamp.strftime("%Y-%m-%d %H:00" if group_by == "hour" else "%Y-%m-%d")
                
                # Skip if outside our expected labels (shouldn't happen but safety check)
                if key not in data:
                    continue
                
                # Extract values
                cost = float(record.get('cost', 0) or 0)
                input_tokens = int(record.get('prompt_tokens', 0) or 0)
                output_tokens = int(record.get('completion_tokens', 0) or 0)
                agent = record.get('agent', 'Unknown')
                model = record.get('model', 'Unknown')
                chain_id = record.get('chain_id')
                elapsed = float(record.get('elapsed_time', 0) or 0)
                query_cost = float(record.get('query_cost', 0.03) or 0.03)  # Default to Pro
                
                # Aggregate data (existing logic)
                data[key]["cost"] += cost
                data[key]["input"] += input_tokens
                data[key]["output"] += output_tokens
                agent_data[agent][key] += cost
                model_data[model][key] += cost
                
                # Track totals
                totals["cost"] += cost
                totals["input"] += input_tokens
                totals["output"] += output_tokens
                
                if chain_id:
                    unique_chain_ids.add(chain_id)
                    
                    # Count unique queries and their costs
                    if chain_id not in query_data[key]["unique_chains"]:
                        query_data[key]["unique_chains"].add(chain_id)
                        query_data[key]["count"] += 1
                        
                        # Track by tier - ADD THIS
                        tier = record.get('compute_tier', 'pro')
                        query_data[key]["tier_counts"][tier] += 1
                        
                        # Only count the query cost once per chain
                        if chain_id not in chain_cost_counted:
                            query_data[key]["total_cost"] += query_cost
                            query_data[key]["tier_costs"][tier] += query_cost  # ADD THIS
                            chain_cost_counted[chain_id] = True
                    
                    # Sum elapsed time for all calls in this chain
                    query_data[key]["chain_elapsed"][chain_id] += elapsed
                    
            except (ValueError, TypeError) as e:
                logging.warning(f"Error processing record: {e}")
                continue
        
        # Calculate total elapsed time per period
        for key in query_data:
            query_data[key]["total_elapsed"] = sum(query_data[key]["chain_elapsed"].values())
        
        # Build response with queries data
        return {
            "cost_chart": {
                "labels": labels,
                "data": [round(data[label]["cost"], 4) for label in labels],
                "agents": {
                    agent: [round(agent_costs[label], 4) for label in labels] 
                    for agent, agent_costs in agent_data.items()
                },
                "models": {
                    model: [round(model_costs[label], 4) for label in labels]
                    for model, model_costs in model_data.items()
                }
            },
            "token_chart": {
                "labels": labels,
                "input_tokens": [data[label]["input"] for label in labels],
                "output_tokens": [data[label]["output"] for label in labels]
            },
            "queries_chart": {
                "labels": labels,
                "counts": [query_data[label]["count"] for label in labels],
                "costs": [round(query_data[label]["total_cost"], 4) for label in labels],
                "elapsed_times": [round(query_data[label]["total_elapsed"], 2) for label in labels],
                "tiers": {
                    "free": [query_data[label]["tier_counts"]["free"] for label in labels],
                    "plus": [query_data[label]["tier_counts"]["plus"] for label in labels],
                    "pro": [query_data[label]["tier_counts"]["pro"] for label in labels]
                },
                "tier_costs": {
                    "free": [round(query_data[label]["tier_costs"]["free"], 4) for label in labels],
                    "plus": [round(query_data[label]["tier_costs"]["plus"], 4) for label in labels],
                    "pro": [round(query_data[label]["tier_costs"]["pro"], 4) for label in labels]
                }
            },
            "summary": {
                "total_cost": round(totals["cost"], 4),
                "total_input_tokens": totals["input"],
                "total_output_tokens": totals["output"],
                "total_queries": len(unique_chain_ids),
                "total_query_cost": round(sum(qd["total_cost"] for qd in query_data.values()), 4),
                "period_description": description
            }
        }
        
    except Exception as e:
        logging.error(f"Failed to get usage data: {str(e)}", exc_info=True)
        return {"error": f"Failed to get usage data: {str(e)}"}

# =============================================================================
# SUBSCRIPTIONS / FUNDS / COUNTERS — RPC-BASED HELPERS (UPDATED)
# =============================================================================

def _normalize_ids(auth0_id: str) -> tuple[str, str]:
    """
    Returns (auth0_full, bamboo_short).
    Example: 'google-oauth2|110...' -> ('google-oauth2|110...', '110...')
    """
    if '|' in auth0_id:
        return auth0_id, auth0_id.split('|', 1)[1]
    return auth0_id, auth0_id


def _rpc(fn_name: str, params: dict, retry_on_disconnect: bool = True) -> Any:
    """
    Enhanced RPC caller with retry logic for connection issues.
    Tries public schema first, then api schema if needed.
    """
    svc = get_service_client()
    max_retries = 3 if retry_on_disconnect else 1
    
    for attempt in range(max_retries):
        try:
            # Try without schema prefix first (public schema)
            if '.' not in fn_name:
                return svc.rpc(fn_name, params).execute()
            else:
                # Already qualified with schema
                return svc.rpc(fn_name, params).execute()
                
        except Exception as e:
            error_str = str(e)
            
            # Handle function not found - try api schema
            if ('PGRST202' in error_str or 'not found' in error_str.lower()) and '.' not in fn_name:
                try:
                    return svc.rpc(f'api.{fn_name}', params).execute()
                except Exception:
                    pass  # Fall through to retry logic
            
            # Handle connection issues with retry
            if retry_on_disconnect and attempt < max_retries - 1:
                if any(err in error_str.lower() for err in ['disconnected', 'connection', 'timeout']):
                    time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                    continue
            
            # On final attempt or non-retryable error, raise
            raise e
    
    raise Exception(f"Failed to execute RPC {fn_name} after {max_retries} attempts")


# -----------------------------------------------------------------------------
# Subscriptions - Enhanced with validation
# -----------------------------------------------------------------------------

def set_user_subscription(auth0_id: str, model_tier: str, compute_tier: str, 
                          integration_config: dict = None) -> dict:
    """
    Upsert subscription with integration config support (PAYG model)
    Note: data_tier is removed - it's always tied to compute_tier
    """
    if not validate_user_access(auth0_id):
        return {"ok": False, "error": "unauthorized"}

    try:
        auth0_full, bamboo_short = _normalize_ids(auth0_id)
        
        # Get user_id for anniversary date
        svc = get_service_client()
        user_result = svc.table('users').select('id').eq('auth0_id', auth0_id).execute()
        if not user_result.data:
            return {"ok": False, "error": "User not found"}
        
        user_id = user_result.data[0]['id']
        
        # Check if this is a new subscription
        existing = svc.table('user_subscription').select('anniversary_date').eq('user_id', user_id).execute()
        
        # Updated params - remove p_data_tier
        params = {
            "p_auth0_id": auth0_full,
            "p_bamboo_user_id": bamboo_short,
            "p_model_tier": model_tier,
            "p_compute_tier": compute_tier,
            "p_integration_config": integration_config or {}
        }
        
        # Call the updated RPC function (without data_tier)
        _rpc("upsert_subscription", params)
        
        # If new subscription, set anniversary date
        if not existing.data:
            anniversary_date = datetime.now().date()
            svc.table('user_subscription').update({
                'anniversary_date': anniversary_date.isoformat()
            }).eq('user_id', user_id).execute()
            
            # Check if query counter exists before creating
            counter_exists = svc.table('usage_counters').select('id').eq(
                'user_id', user_id
            ).eq('anniversary_period', anniversary_date.isoformat()).execute()
            
            # Set up initial usage counter if not exists
            if not counter_exists.data:
                svc.table('usage_counters').insert({
                    'user_id': user_id,
                    'queries_used': 0,
                    'anniversary_period': anniversary_date.isoformat()
                }).execute()
        
        return {"ok": True}
        
    except Exception as e:
        logging.error(f"set_user_subscription failed: {str(e)}", exc_info=True)
        return {"ok": False, "error": str(e)}


def get_user_subscription(auth0_id: str) -> dict:
    """
    Get subscription including integration config and query cost
    """
    if not validate_user_access(auth0_id):
        return {"ok": False, "error": "unauthorized"}

    try:
        svc = get_service_client()
        
        user_row = svc.table('users').select('id').eq('auth0_id', auth0_id).execute()
        if not user_row.data:
            return {"ok": True, "data": None}
        
        user_id = user_row.data[0]['id']

        # Get subscription with tier info
        res = svc.table('user_subscription').select(
            'model_tier,compute_tier,integration_config,anniversary_date,updated_at'
        ).eq('user_id', user_id).execute()

        if res.data and len(res.data) > 0:
            sub_data = res.data[0]
            
            # Get tier pricing info
            tier_res = svc.table('tier_limits').select(
                'variable_rate,max_queries,max_data_days'
            ).eq('category', 'compute').eq('tier', sub_data['compute_tier']).execute()
            
            if tier_res.data:
                tier_info = tier_res.data[0]
                sub_data['per_query_cost'] = float(tier_info.get('variable_rate', 0))
                sub_data['max_queries'] = tier_info.get('max_queries')
                sub_data['max_data_days'] = tier_info.get('max_data_days')
                
                # Add SweatStack cost if enabled
                if sub_data.get('integration_config', {}).get('sweatstack_extended'):
                    sub_data['per_query_cost'] += 0.01
            
            # Remove data_tier from response (deprecated)
            sub_data.pop('data_tier', None)
            
            return {"ok": True, "data": sub_data}
        else:
            return {"ok": True, "data": None}
            
    except Exception as e:
        logging.error(f"get_user_subscription failed: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


def get_tier_limits(category: str = None) -> dict:
    """
    Read tier_limits for UI pickers (static catalog).
    Enhanced with caching potential.
    """

    try:
        svc = get_service_client()
        q = svc.table('tier_limits').select('*')
        
        if category:
            if category not in ['model', 'compute', 'data']:
                return {"ok": False, "error": f"Invalid category '{category}'"}
            q = q.eq('category', category)
        
        res = q.execute()
        return {"ok": True, "data": res.data or []}
    except Exception as e:
        logging.error(f"get_tier_limits failed: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}
    

def get_user_compute_tier(bamboo_user_id: str) -> str:
    """Get user's compute tier"""
    try:
        res = _rpc("get_compute_tier", {"p_bamboo_user_id": bamboo_user_id})
        # res.data is already the string 'free', 'plus', or 'pro'
        return res.data if res.data else 'free'
    except Exception as e:
        logging.error(f"Error getting compute tier: {str(e)}")
        return 'free'


# -----------------------------------------------------------------------------
# Funds & Transactions - With better error handling
# -----------------------------------------------------------------------------

def add_funds(auth0_id: str, amount: float, source: str, reference: str, 
              idempotency_key: str = None, skip_validation: bool = False) -> dict:
    """
    Credit user balance via RPC. Idempotent when idempotency_key is reused.
    Enhanced with amount validation.
    """
    
    if not skip_validation and not validate_user_access(auth0_id):
        return {"ok": False, "error": "unauthorized"}
    
    # Validate amount
    if amount <= 0:
        return {"ok": False, "error": "Amount must be positive"}
    if amount > 1000:  # Reasonable limit
        return {"ok": False, "error": "Amount exceeds maximum limit"}

    try:
        auth0_full, bamboo_short = _normalize_ids(auth0_id)
        res = _rpc("add_funds", {
            "p_auth0_id": auth0_full,
            "p_bamboo_user_id": bamboo_short,
            "p_amount": float(amount),  # Ensure float
            "p_source": source,
            "p_reference": reference,
            "p_idempotency_key": idempotency_key
        })
        return {"ok": True, "data": res.data or {}}
    except Exception as e:
        logging.error(f"add_funds failed: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


def get_balance(auth0_id: str) -> dict:
    """
    Simple balance read for UI.
    Returns: {"ok": True, "data": {"balance": <number>, "last_updated": <ts>}}
    """

    if not validate_user_access(auth0_id):
        return {"ok": False, "error": "unauthorized"}

    try:
        svc = get_service_client()
        user_row = svc.table('users').select('id').eq('auth0_id', auth0_id).execute()
        if not user_row.data:
            return {"ok": True, "data": {"balance": 0.0, "last_updated": None}}
        
        user_id = user_row.data[0]['id']
        
        # Get balance (may not exist for new users)
        res = svc.table('user_funds').select('balance,last_updated').eq('user_id', user_id).execute()
        
        if res.data and len(res.data) > 0:
            # Ensure balance is a float
            data = res.data[0]
            data['balance'] = float(data.get('balance', 0))
            return {"ok": True, "data": data}
        else:
            # No funds record yet - this is normal for new users
            return {"ok": True, "data": {"balance": 0.0, "last_updated": None}}
            
    except Exception as e:
        logging.error(f"get_balance failed: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


# -----------------------------------------------------------------------------
# Usage / Counters - Core functionality unchanged
# -----------------------------------------------------------------------------

def can_execute_chain(auth0_id: str) -> dict:
    """
    Check if user can execute a query (PAYG model)
    Returns: {"ok": True, "data": {"allowed": bool, "reason": str, "query_cost": float, ...}}
    """
    if not validate_user_access(auth0_id):
        return {"ok": False, "error": "unauthorized"}

    try:
        auth0_full, bamboo_short = _normalize_ids(auth0_id)
        res = _rpc("can_execute_chain", {
            "p_auth0_id": auth0_full,
            "p_bamboo_user_id": bamboo_short
        })
        
        data = res.data or {}
        
        # Ensure numeric fields are properly typed - handle None values
        if 'query_cost' in data:
            data['query_cost'] = float(data['query_cost']) if data['query_cost'] is not None else 0.0
        if 'balance' in data:
            data['balance'] = float(data['balance']) if data['balance'] is not None else 0.0
        if 'queries_used' in data:
            data['queries_used'] = int(data['queries_used']) if data['queries_used'] is not None else 0
        if 'max_queries' in data:
            data['max_queries'] = int(data['max_queries']) if data['max_queries'] is not None else None
            
        return {"ok": True, "data": data}
    except Exception as e:
        logging.error(f"can_execute_chain failed: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


def increment_queries_counter(auth0_id: str) -> dict:
    """
    Increment query counter for anniversary-based tracking
    """
    if not validate_user_access(auth0_id):
        return {"ok": False, "error": "unauthorized"}

    try:
        auth0_full, bamboo_short = _normalize_ids(auth0_id)
        _rpc("increment_queries_counter", {
            "p_auth0_id": auth0_full,
            "p_bamboo_user_id": bamboo_short
        })
        return {"ok": True}
    except Exception as e:
        logging.error(f"increment_queries_counter failed: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}


def get_monthly_usage(auth0_id: str) -> dict:
    """
    Get usage for current anniversary period
    Returns: {"ok": True, "data": {"period_start": date, "period_end": date, "queries_used": int, "max_queries": int}}
    """
    if not validate_user_access(auth0_id):
        return {"ok": False, "error": "unauthorized"}

    try:
        auth0_full, bamboo_short = _normalize_ids(auth0_id)
        res = _rpc("get_monthly_usage", {
            "p_auth0_id": auth0_full,
            "p_bamboo_user_id": bamboo_short
        })
        
        data = res.data or {}
        
        # Ensure queries_used is an integer
        if 'queries_used' in data:
            data['queries_used'] = int(data['queries_used'])
        if 'max_queries' in data and data['max_queries'] is not None:
            data['max_queries'] = int(data['max_queries'])
            
        return {"ok": True, "data": data}
    except Exception as e:
        logging.error(f"get_monthly_usage failed: {e}", exc_info=True)
        return {"ok": False, "error": str(e)}
    
# -----------------------------------------------------------------------------
# Labels Maintenance
# -----------------------------------------------------------------------------

def remove_label_from_chain(chain_id: str) -> bool:
    """Remove label from a chain (set label_id to NULL)
    
    Args:
        chain_id: The chain ID to remove the label from
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        service_client = get_service_client()
        
        # Update chain to remove label (set to NULL)
        result = service_client.table('chains').update({
            'label_id': None
        }).eq('chain_id', chain_id).execute()
        
        if result.data:
            logger.info(f"Successfully removed label from chain: {chain_id}")
            return True
        else:
            logger.warning(f"No chain found with ID: {chain_id}")
            return False
            
    except Exception as e:
        logger.error(f"Error removing label from chain: {str(e)}")
        return False