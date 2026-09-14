"""
Flask blueprint for agent instructions functionality
"""

import logging
import json
import os
from flask import request, Blueprint, jsonify
from auth import requires_auth, get_current_user_id
from logger_config import get_logger

agent_instructions_bp = Blueprint('agent_instructions', __name__)
logger = get_logger(__name__)

@agent_instructions_bp.route('/api/agent-instructions/<chain_id>/<agent_name>', methods=['GET'])
@requires_auth
def get_agent_instructions(chain_id, agent_name):
    """Get system and user instructions for a specific agent in a chain"""
    try:
        user_id = get_current_user_id()
        if '|' in user_id:
            user_id = user_id.split('|')[1]
        
        # Load the log file
        log_path = os.path.join('logs', user_id, 'bambooai_run_log.json')
        
        if not os.path.exists(log_path):
            return jsonify({'error': 'Log file not found'}), 404
        
        with open(log_path, 'r') as f:
            log_data = json.load(f)
        
        # Find the matching chain and agent - the nth call of that seat in the chain (2026-09-10: ?call=n;
        # the pane's cards are numbered in the same order the log records the calls; default the first)
        try:
            wanted = max(1, int(request.args.get('call', 1)))
        except (TypeError, ValueError):
            wanted = 1
        matches = [e for e in log_data if str(e.get('chain_id')) == str(chain_id) and e.get('agent') == agent_name and e.get('messages')]
        if matches:
            entry = matches[min(wanted, len(matches)) - 1]
            for entry in [entry]:
                messages = entry.get('messages', [])
                
                # Find system message (first message with role='system', or first message if no system role)
                system_prompt = ''
                if messages:
                    if messages[0].get('role') == 'system':
                        system_prompt = messages[0].get('content', '')
                    else:
                        # No system role, first message might be user
                        system_prompt = ''
                
                # Find last user message with string content (searching backwards)
                user_prompt = ''
                for i in range(len(messages) - 1, -1, -1):
                    msg = messages[i]
                    if msg.get('role') == 'user' and isinstance(msg.get('content'), str):
                        user_prompt = msg.get('content')
                        break
                
                return jsonify({
                    'success': True,
                    'agent': agent_name,
                    'system': system_prompt,
                    'user': user_prompt,
                    'timestamp': entry.get('timestamp'),
                    'model': entry.get('model'),
                    'call': min(wanted, len(matches)),
                    'calls': len(matches)
                }), 200
        
        return jsonify({'error': 'Agent instructions not found'}), 404
        
    except Exception as e:
        logger.error(f"Error fetching agent instructions: {str(e)}")
        return jsonify({'error': 'Failed to fetch agent instructions'}), 500