"""The brief before an analysis (docs/ARCHITECT_DESIGN.md §2.6, §2.9): a question asked with the Architect on opens a
framing run on the thread's record - no model is called - and every change to its brief is kept as a version. The
analysis then continues that run through /query, which names it as run_id."""
from flask import Blueprint, jsonify, request, session

from analyst.brief import QUESTION_CHARS
from auth import requires_auth
from logger_config import get_logger

logger = get_logger(__name__)
architect_bp = Blueprint('architect', __name__)


def _instance():
    import app as webapp                                     # the main module: the instances
    return webapp.get_bamboo_ai(session['session_id'])


@architect_bp.route('/architect/open', methods=['POST'])
@requires_auth
def architect_open():
    """Open a framing run for a question: {question, thread_id, chain_id} -> {thread_id, chain_id, parent_chain_id, framing}."""
    data = request.json or {}
    question = str(data.get('question') or '').strip()[:QUESTION_CHARS]
    if not question:
        return jsonify({'error': 'A question is needed.'}), 400
    try:
        return jsonify(_instance().open_framing(question, thread_id=data.get('thread_id'), chain_id=data.get('chain_id'))), 200
    except Exception as exc:                                 # noqa: BLE001
        logger.exception("architect: the framing run could not be opened")
        return jsonify({'error': f'The brief could not be opened: {str(exc)[:200]}'}), 500


@architect_bp.route('/architect/brief', methods=['POST'])
@requires_auth
def architect_brief():
    """Keep one more version of a framing run's brief: {thread_id, chain_id, brief, changed} -> {framing}."""
    data = request.json or {}
    if data.get('thread_id') is None or data.get('chain_id') is None or not isinstance(data.get('brief'), dict):
        return jsonify({'error': 'The thread, the chain and the brief are needed.'}), 400
    try:
        framing = _instance().save_brief(data['thread_id'], data['chain_id'], data['brief'],
                                         changed=data.get('changed') if isinstance(data.get('changed'), list) else None,
                                         question=str(data['brief'].get('question') or '')[:QUESTION_CHARS])
    except Exception as exc:                                 # noqa: BLE001
        logger.exception("architect: the brief was not kept")
        return jsonify({'error': f'The change was not kept: {str(exc)[:200]}'}), 500
    if framing is None:
        return jsonify({'error': 'This brief can no longer be changed: its analysis has started.'}), 409
    return jsonify({'framing': framing}), 200
