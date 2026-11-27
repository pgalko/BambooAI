"""A passage of a finished analysis explained (analyst/explain.py): the person selects text in the Answer, Code or
Results tab of an analysis and asks about it. The answer is kept with the analysis, at the passage; no analysis starts.

  POST /explain                          {thread_id, chain_id, tab, view, passage, at, quote, question} as a stream: the
                                         answer as it is written, then {"explain": {"asked": [...]}} - everything
                                         asked about the analysis so far, the new exchange last - or
                                         {"explain": {"error": ...}} when none was made
  GET  /explain/<thread_id>/<chain_id>   {"asked": [...]}: what the page draws when it shows the analysis again

An explanation is a query for the account's purposes, as a set of next questions is: authorised, counted towards the
month's free queries and charged like one (bambooai.py, explain)."""
from flask import Blueprint, jsonify, request, session

from analyst import explain
from analyst.architect import Failed
from analyst.notebook import NotebookStore
from auth import requires_auth
from logger_config import get_logger
from routines_routes import _app, _stream

logger = get_logger(__name__)
explain_bp = Blueprint('explain', __name__)


@explain_bp.route('/explain', methods=['POST'])
@requires_auth
def explain_ask():
    """One question about a passage of a finished analysis, answered and kept with it."""
    data = request.json or {}
    if data.get('thread_id') is None or data.get('chain_id') is None:
        return jsonify({'error': 'The thread and the chain are needed.'}), 400
    try:
        asked = explain.taken(data)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 400
    refused = _app().query_refusal()
    if refused is not None:
        return refused
    instance = _app().get_bamboo_ai(session['session_id'])

    def work():
        try:
            kept = instance.explain(data['thread_id'], data['chain_id'], asked)
        except Failed as exc:
            return {'explain': {'error': str(exc)}}
        except Exception as exc:                             # noqa: BLE001
            logger.exception("explain: no explanation was written")
            return {'explain': {'error': f'No explanation was written: {str(exc)[:300]}'}}
        return {'explain': {'asked': kept} if kept is not None else {'error': 'This analysis is no longer on record: nothing can be asked about it.'}}
    return _stream(instance, work)


@explain_bp.route('/explain/<thread_id>/<chain_id>', methods=['GET'])
@requires_auth
def explain_kept(thread_id, chain_id):
    """What was asked about an analysis, in the order asked: read from the thread's record, which the instance writes
    after every exchange. None where the record does not hold the analysis."""
    run = NotebookStore(_app().user_path('storage')).read(thread_id).runs.get(str(chain_id))
    return jsonify({'asked': run.explained if run is not None else []}), 200
