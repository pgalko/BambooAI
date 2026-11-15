"""The brief before an analysis (docs/ARCHITECT_DESIGN.md §2.6, §2.9, §2.12, §2.13): a question asked with the
Architect on opens a framing run on the thread's record; the Architect then fills its brief from the question, asks
for what is missing and checks what the brief rests on against the data, one exchange a call; every change to the
brief is kept as a version. The analysis then continues that run through /query, which names it as run_id.

A framed question is a query for the account's purposes: authorised like one at each step, counted towards the
month's free queries once, when its brief opens, and charged once, with its analysis (bambooai.py, architect_say)."""
from flask import Blueprint, jsonify, request, session

from analyst.architect import Failed
from analyst.brief import QUESTION_CHARS
from auth import requires_auth
from logger_config import get_logger
from routines_routes import _stream

logger = get_logger(__name__)
architect_bp = Blueprint('architect', __name__)


def _app():
    import app as webapp                                     # the main module: the instances, the authorisation
    return webapp


def _instance():
    return _app().get_bamboo_ai(session['session_id'])


@architect_bp.route('/architect/open', methods=['POST'])
@requires_auth
def architect_open():
    """Open a framing run for a question: {question, thread_id, chain_id} -> {thread_id, chain_id, parent_chain_id, framing}."""
    data = request.json or {}
    question = str(data.get('question') or '').strip()[:QUESTION_CHARS]
    if not question:
        return jsonify({'error': 'A question is needed.'}), 400
    refused = _app().query_refusal()
    if refused is not None:
        return refused
    try:
        return jsonify(_instance().open_framing(question, thread_id=data.get('thread_id'), chain_id=data.get('chain_id'))), 200
    except Exception as exc:                                 # noqa: BLE001
        logger.exception("architect: the framing run could not be opened")
        return jsonify({'error': f'The brief could not be opened: {str(exc)[:200]}'}), 500


@architect_bp.route('/architect/say', methods=['POST'])
@requires_auth
def architect_say():
    """One exchange with the Architect: {thread_id, chain_id, text} - no text on its first turn, nor when it goes on
    after a round of lookups - as a stream that ends on {"architect": {"framing": ...}}, or {"architect": {"error":
    ...}} when no reply was kept."""
    data = request.json or {}
    if data.get('thread_id') is None or data.get('chain_id') is None:
        return jsonify({'error': 'The thread and the chain are needed.'}), 400
    refused = _app().query_refusal(count=False)
    if refused is not None:
        return refused
    instance = _instance()
    text = str(data.get('text') or '').strip()[:QUESTION_CHARS] or None

    def work():
        try:
            framing = instance.architect_say(data['thread_id'], data['chain_id'], text)
        except Failed as exc:
            return {'architect': {'error': str(exc)}}
        except Exception as exc:                             # noqa: BLE001
            logger.exception("architect: the exchange failed")
            return {'architect': {'error': f'The Architect could not reply: {str(exc)[:300]}'}}
        if framing is None:
            return {'architect': {'error': 'This brief can no longer be changed: its analysis has started.'}}
        return {'architect': {'framing': framing}}
    return _stream(instance, work)


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
