"""The brief before an analysis (docs/ARCHITECT_DESIGN.md §2.6, §2.9, §2.12, §2.13): a question asked with the
Pathfinder on opens a framing run on the thread's record; the Pathfinder then fills its brief from the question, asks
for what is missing and checks what the brief rests on against the data, one exchange a call; every change to the
brief is kept as a version. The analysis then continues that run through /query, which names it as run_id.

What the person says or changes, with the reply, is a step of the conversation (§2.25; analyst/steps.py). They may
go back to an earlier step and go on from there: each request that goes on - /architect/say, /architect/brief,
/architect/ready, /query - names the step on their screen (`step`), and what it adds follows that step.

An exchange may have the person's saved analyses read (§3.7): the stream then carries how far the reading is, the
person can skip it (/architect/skip), and a saved analysis the brief names can be read whole (/architect/saved).
Where the brief holds figures, a draft of them is drawn after the reply (§2.20): the stream carries the framing as
the reply left it, and the page then asks for each figure's plot (/architect/draft). Before the analysis starts, the
question is read as the analyst will read it (/architect/ready, §2.22): where something in it cannot be placed, the
Pathfinder goes on and the analysis waits for the person to start it again.

A framed question is a query for the account's purposes: authorised like one at each step, counted towards the
month's free queries once, when its brief opens, and charged once, with its analysis (bambooai.py, architect_say).

After a finished analysis the person may ask for the questions that could follow it, at one of five levels (§2.7,
§2.15): one call of the Pathfinder's, which is a query of its own - authorised, counted and charged like one."""
from flask import Blueprint, Response, jsonify, request, session

from analyst.architect import Failed
from analyst.brief import QUESTION_CHARS
from analyst.next_questions import LEVELS
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


def _step(data):
    """The step of the conversation on the person's screen, as a request names it: a whole number, or none."""
    step = data.get('step')
    return step if isinstance(step, int) and not isinstance(step, bool) else None


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
    """One exchange with the Pathfinder: {thread_id, chain_id, text, step} - no text on its first turn, nor when it
    goes on after a round of lookups, a reading of the saved analyses or a part of an earlier analysis it opened;
    `step`: the step of the conversation on the person's screen, which the exchange goes on from - as a stream that
    ends on {"architect": {"framing": ...}}, or {"architect": {"error": ...}} when no reply was kept. While the saved
    analyses are read the stream carries {"type": "architect_saved", "read", "of"}; where a draft of the figures
    follows the reply, {"type": "architect_draft", "framing": the framing with the reply} before it is drawn."""
    data = request.json or {}
    if data.get('thread_id') is None or data.get('chain_id') is None:
        return jsonify({'error': 'The thread and the chain are needed.'}), 400
    refused = _app().query_refusal(count=False)
    if refused is not None:
        return refused
    instance = _instance()
    text = str(data.get('text') or '').strip()[:QUESTION_CHARS] or None
    step = _step(data)

    def work():
        try:
            framing = instance.architect_say(data['thread_id'], data['chain_id'], text, step=step)
        except Failed as exc:
            return {'architect': {'error': str(exc)}}
        except Exception as exc:                             # noqa: BLE001
            logger.exception("architect: the exchange failed")
            return {'architect': {'error': f'The Pathfinder could not reply: {str(exc)[:300]}'}}
        if framing is None:
            return {'architect': {'error': 'This brief can no longer be changed: its analysis has started.'}}
        return {'architect': {'framing': framing}}
    return _stream(instance, work)


@architect_bp.route('/architect/ready', methods=['POST'])
@requires_auth
def architect_ready():
    """Before a framed question's analysis starts (§2.22): {thread_id, chain_id, step} - the step of the conversation
    on the person's screen. Its question is read as the analyst will read it; the stream ends on {"architect":
    {"framing": ..., "clean": whether the analysis can start}}. Where it cannot, the Pathfinder has gone on: the
    framing holds what the reader could not place and the Pathfinder's reply - or "error" says why there is none -
    and the stream carried {"type": "architect_draft", "framing"} before a draft of the figures was drawn, as
    after any reply. {"architect": {"error": ...}} alone where no read was made: the analysis can start."""
    data = request.json or {}
    if data.get('thread_id') is None or data.get('chain_id') is None:
        return jsonify({'error': 'The thread and the chain are needed.'}), 400
    refused = _app().query_refusal(count=False)
    if refused is not None:
        return refused
    instance = _instance()
    step = _step(data)

    def work():
        try:
            got = instance.architect_ready(data['thread_id'], data['chain_id'], step=step)
        except Exception as exc:                             # noqa: BLE001
            logger.exception("architect: the question could not be read before its analysis")
            return {'architect': {'error': f'The question could not be checked: {str(exc)[:300]}'}}
        return {'architect': got or {'error': 'This brief can no longer be changed: its analysis has started.'}}
    return _stream(instance, work)


@architect_bp.route('/architect/skip', methods=['POST'])
@requires_auth
def architect_skip():
    """The person no longer waits for the saved analyses: the reading in flight ends before its next call, and the
    exchange goes on without it."""
    _instance().skip_saved()
    return jsonify({'skipped': True}), 200


@architect_bp.route('/architect/saved/<thread_id>/<run_id>', methods=['GET'])
@requires_auth
def architect_saved(thread_id, run_id):
    """A saved analysis as memory holds it, to read beside a brief that names it: {id, when, kind, question, hints,
    title, brief, conversation, report, marks, data: {name, period, person}, cells: [{n, code}]} - the cells along its
    thread up to its own, as a passage's place counts them; whose data it ran on is from the thread's record, the
    view holding no name. 404 when it is no longer saved."""
    from analyst import memory, reader
    from analyst.notebook import NotebookStore, subject_name_of
    storage = _app().user_path('storage')
    view = memory.view(storage)
    run = next((r for r in view['runs'] if r['thread'] == str(thread_id) and r['run'] == str(run_id)), None)
    if run is None:
        return jsonify({'error': 'This analysis is no longer among your saved ones.'}), 404
    record = NotebookStore(storage).read(run['thread']).runs.get(run['run'])
    return jsonify({**{k: run[k] for k in ("id", "when", "kind", "question", "hints", "title", "brief", "conversation", "report", "marks")},
                    "data": {"name": run["data"]["name"], "period": run["data"]["period"], "person": subject_name_of(record.data if record else None)},
                    "cells": [{"n": c["n"], "code": c["code"]} for c in reader.path_cells(view, run)]}), 200


@architect_bp.route('/architect/draft/<thread_id>/<run_id>/<key>', methods=['GET'])
@requires_auth
def architect_draft(thread_id, run_id, key):
    """The plot of a figure's draft, for the page to draw: {"plot": the figure as Plotly takes it}, under the key the
    framing gives the figure (analyst/draft.py). A branch's drafts are those of the chains it went on from: one made
    before 0331 has none kept under it, and they are found there. 404 where none is kept."""
    from analyst.draft import Plots, lineage
    from analyst.notebook import NotebookStore
    storage = _app().user_path('storage')
    plots = Plots(storage)
    plot = plots.get(thread_id, run_id, key)
    if plot is None:
        plot = next((p for p in (plots.get(thread_id, r, key) for r in lineage(NotebookStore(storage).read(thread_id), run_id)[1:]) if p is not None), None)
    if plot is None:
        return jsonify({'error': 'No draft is kept for this figure.'}), 404
    return Response('{"plot": ' + plot + '}', mimetype='application/json')      # as it was kept: read() took it only where it parses


@architect_bp.route('/architect/next', methods=['POST'])
@requires_auth
def architect_next():
    """A set of next questions for a finished analysis: {thread_id, chain_id, level} as a stream that ends on
    {"next": {"set": ..., "at": its place among the analysis' sets}}, or {"next": {"error": ...}} when none was made."""
    data = request.json or {}
    if data.get('thread_id') is None or data.get('chain_id') is None or not isinstance(data.get('level'), str) or data['level'] not in LEVELS:
        return jsonify({'error': 'The thread, the chain and one of the five levels are needed.'}), 400
    refused = _app().query_refusal()
    if refused is not None:
        return refused
    instance = _instance()

    def work():
        try:
            asked = instance.next_questions(data['thread_id'], data['chain_id'], data['level'])
        except Failed as exc:
            return {'next': {'error': str(exc)}}
        except Exception as exc:                             # noqa: BLE001
            logger.exception("architect: next questions failed")
            return {'next': {'error': f'The questions could not be written: {str(exc)[:300]}'}}
        return {'next': asked or {'error': 'This analysis is no longer on record: nothing can follow from it.'}}
    return _stream(instance, work)


@architect_bp.route('/architect/brief', methods=['POST'])
@requires_auth
def architect_brief():
    """Keep one more version of a framing run's brief: {thread_id, chain_id, brief, changed, step} -> {framing}. The
    brief is the one on the person's screen with their change; `step`: the step of the conversation it was made
    at - the change is a step that follows it."""
    data = request.json or {}
    if data.get('thread_id') is None or data.get('chain_id') is None or not isinstance(data.get('brief'), dict):
        return jsonify({'error': 'The thread, the chain and the brief are needed.'}), 400
    try:
        framing = _instance().save_brief(data['thread_id'], data['chain_id'], data['brief'],
                                         changed=data.get('changed') if isinstance(data.get('changed'), list) else None,
                                         question=str(data['brief'].get('question') or '')[:QUESTION_CHARS], step=_step(data))
    except Exception as exc:                                 # noqa: BLE001
        logger.exception("architect: the brief was not kept")
        return jsonify({'error': f'The change was not kept: {str(exc)[:200]}'}), 500
    if framing is None:
        return jsonify({'error': 'This brief can no longer be changed: its analysis has started.'}), 409
    return jsonify({'framing': framing}), 200
