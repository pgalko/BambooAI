import os
import json
import time
from functools import wraps
from flask import request, jsonify, g
from urllib.request import urlopen
try:
    from jose import jwt
except ImportError:                                     # the self-hosted edition (AUTH_MODE=single) verifies no Auth0 tokens
    jwt = None

from logger_config import get_logger
logger = get_logger(__name__)

# Configuration
AUTH_MODE = os.getenv('AUTH_MODE', 'none')
# The self-hosted edition (docs/OSS_DESIGN.md D4, D29): AUTH_MODE=single is one person on their own machine.
# Every request carries the fixed local identity, no token, no Auth0; BAMBOO_USER names the folders under
# storage/, memory/ and config/. 'none' keeps its old meaning - nothing configured - so a box never runs
# open by accident.
BAMBOO_USER = os.getenv('BAMBOO_USER', 'local')
LOCAL_SUB = f"local|{BAMBOO_USER}"


def local_user():
    return {'sub': LOCAL_SUB, 'email': f'{BAMBOO_USER}@local', 'name': BAMBOO_USER, 'nickname': BAMBOO_USER}
AUTH0_DOMAIN = os.getenv('AUTH0_DOMAIN')
AUTH0_API_AUDIENCE = os.getenv('AUTH0_API_AUDIENCE')
ALGORITHMS = ['RS256']

# JWKS cache — avoids hitting Auth0 on every request
_jwks_cache = {'keys': None, 'fetched_at': 0}
JWKS_CACHE_TTL = 3600  # 1 hour


def _get_jwks():
    """Fetch JWKS with caching"""
    now = time.time()
    if _jwks_cache['keys'] and (now - _jwks_cache['fetched_at']) < JWKS_CACHE_TTL:
        return _jwks_cache['keys']

    jsonurl = urlopen(f'https://{AUTH0_DOMAIN}/.well-known/jwks.json')
    jwks = json.loads(jsonurl.read())
    _jwks_cache['keys'] = jwks
    _jwks_cache['fetched_at'] = now
    return jwks


def _find_rsa_key(jwks, kid):
    """Find RSA key matching the token's kid"""
    for key in jwks['keys']:
        if key['kid'] == kid:
            return {k: key[k] for k in ('kty', 'kid', 'use', 'n', 'e')}
    return None


def init_auth(app):
    """Initialize authentication configuration"""
    app.config['AUTH_MODE'] = AUTH_MODE
    app.config['AUTH0_DOMAIN'] = AUTH0_DOMAIN
    app.config['AUTH0_API_AUDIENCE'] = AUTH0_API_AUDIENCE
    
    @app.route('/api/auth/status')
    def auth_status():
        return jsonify({
            'auth_enabled': AUTH_MODE == 'auth0',
            'mode': AUTH_MODE,
            'user': local_user() if AUTH_MODE == 'single' else None,
            'auth0_domain': AUTH0_DOMAIN if AUTH_MODE == 'auth0' else None,
            'auth0_client_id': os.getenv('AUTH0_CLIENT_ID') if AUTH_MODE == 'auth0' else None,
            'auth0_audience': AUTH0_API_AUDIENCE if AUTH_MODE == 'auth0' else None
        })


def requires_auth(f):
    """Decorator to require authentication"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if AUTH_MODE == 'single':                        # the self-hosted edition: the one local identity, no token
            g.current_user_id = LOCAL_SUB
            g.current_user = local_user()
            g.auth_token = None
            return f(*args, **kwargs)
        token = get_token_from_header()
        if not token:
            return jsonify({'message': 'Authorization token required'}), 401
        
        # ONLY token validation lives inside the try. The previous shape
        # wrapped ensure_user_exists AND the entire endpoint call, so any
        # exception in any authenticated endpoint was logged as "Token
        # validation error" and answered 401 Invalid token - observed live
        # when a Save Trajectory failure surfaced as an auth error and cost a
        # confused diagnosis. An endpoint failure must reach Flask as itself:
        # a 500 with its real name in the log.
        try:
            payload = validate_auth0_token(token)
            g.current_user_id = payload['sub']   # a payload without sub IS a bad token
        except Exception as e:
            logger.error(f"Token validation error: {str(e)}")
            return jsonify({'message': 'Invalid token'}), 401

        g.current_user = payload
        g.auth_token = token
        ensure_user_exists(payload)
        return f(*args, **kwargs)
    
    return decorated_function


def get_current_user_id():
    """Get current user ID from Auth0 token"""
    user_id = getattr(g, 'current_user_id', None)
    if not user_id:
        raise RuntimeError("No authenticated user found")
    return user_id


def get_token_from_header():
    """Extract Bearer token from Authorization header"""
    auth_header = request.headers.get('Authorization', None)
    if not auth_header:
        return None
    
    parts = auth_header.split()
    if parts[0].lower() != 'bearer' or len(parts) != 2:
        return None
    
    return parts[1]


def validate_auth0_token(token):
    """Validate Auth0 JWT token"""
    jwks = _get_jwks()
    kid = jwt.get_unverified_header(token)['kid']
    
    rsa_key = _find_rsa_key(jwks, kid)
    
    if not rsa_key:
        # Key not found — cache may be stale after key rotation. Force refresh once.
        _jwks_cache['fetched_at'] = 0
        jwks = _get_jwks()
        rsa_key = _find_rsa_key(jwks, kid)
        
        if not rsa_key:
            raise Exception('Unable to find appropriate key')
    
    return jwt.decode(
        token, rsa_key,
        algorithms=ALGORITHMS,
        audience=AUTH0_API_AUDIENCE,
        issuer=f'https://{AUTH0_DOMAIN}/'
    )


def ensure_user_exists(user_payload):
    """Create user record in Supabase if it doesn't exist"""
    try:
        from .supabase_client import get_service_client
        import requests
        
        auth0_id = user_payload['sub']
        
        service_client = get_service_client()
        result = service_client.table('users').select('auth0_id').eq('auth0_id', auth0_id).execute()
        
        if result.data:
            return
        
        # Fetch user details from Auth0 userinfo
        try:
            userinfo_url = f"https://{AUTH0_DOMAIN}/userinfo"
            token = getattr(g, 'auth_token', '')
            response = requests.get(userinfo_url, headers={'Authorization': f'Bearer {token}'})
            response.raise_for_status()
            
            user_info = response.json()
            bamboo_user_id = auth0_id.split('|')[1]
            
            user_data = {
                'auth0_id': auth0_id,
                'bamboo_user_id': bamboo_user_id,
                'email': user_info.get('email', ''),
                'name': user_info.get('name', ''),
            }
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch user info from Auth0: {str(e)}")
            user_data = {
                'auth0_id': auth0_id,
                'email': user_payload.get('email', ''),
                'name': user_payload.get('name', user_payload.get('nickname', '')),
            }
        
        service_client.table('users').insert(user_data).execute()
        logger.info(f"Created new user: {auth0_id}")
            
    except Exception as e:
        logger.error(f"Error ensuring user exists: {str(e)}")