"""The report of a finished analysis in plain language, written when the person asks for it (the Answer tab's
Simplify; 2026-11-28 - until then every analysis ended with it, read or not).

  POST /simplify   {thread_id, chain_id} - as a stream: the call's own traffic, then {"simplify": {"text": the plain
                   version, "card": what the pane's card of the call says - seat, model, elapsed, cost, chain_id}},
                   or {"simplify": {"error": ...}} when none was written

The plain version is kept with the analysis and written once: asked for again, it comes back as kept. It is part of
the analysis the person was authorised for and that was counted as a query: this is no query of its own, and its call
is logged under the analysis' chain (bambooai.py, simplify)."""
from flask import Blueprint, jsonify, request, session

from auth import requires_auth
from logger_config import get_logger
from routines_routes import _app, _stream

logger = get_logger(__name__)
simplify_bp = Blueprint('simplify', __name__)


@simplify_bp.route('/simplify', methods=['POST'])
@requires_auth
def simplify():
    """The plain version of a finished analysis' report: as kept, or written now and kept."""
    data = request.json or {}
    if data.get('thread_id') is None or data.get('chain_id') is None:
        return jsonify({'error': 'The thread and the chain are needed.'}), 400
    instance = _app().get_bamboo_ai(session['session_id'])

    def work():
        try:
            made = instance.simplify(data['thread_id'], data['chain_id'])
        except Exception as exc:                             # noqa: BLE001
            logger.exception("simplify: no plain version was written")
            return {'simplify': {'error': f'No plain-language version was written: {str(exc)[:300]}'}}
        return {'simplify': made if made is not None else {'error': 'This analysis is no longer on record: its report cannot be rewritten.'}}
    return _stream(instance, work)
