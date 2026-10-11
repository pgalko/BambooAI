"""Routines (docs/ROUTINES_DESIGN.md): the routes behind Save as routine, the Routines manager and the favourites'
cards. The routines live as files beside the favourites (storage/<user>/routines/<id>/); the two slow routes -
propose (the promoter's call) and create (run zero) - stream the pane's rows while they work, as /submit_rank does,
and end with one message the dialog reads (routine_proposal, routine_made, or routine_error)."""
import json
import threading
import time
from queue import Empty

from flask import Blueprint, Response, jsonify, request, session

from auth import requires_auth, get_current_user_id
from auth.supabase_client import can_execute_chain, increment_queries_counter
from logger_config import get_logger

logger = get_logger(__name__)
routines_bp = Blueprint('routines', __name__)


def _app():
    import app as webapp                                     # the main module: the instances, the paths
    return webapp


def _store():
    from analyst.routines import RoutineStore
    return RoutineStore(_app().user_path('storage'))


def _view(proposal):
    """The proposal as the dialog shows it: no scripts, no edit lists."""
    keys = ("proposal_id", "thread_id", "chain_id", "name", "purpose", "question", "summary", "data", "data_state", "source", "inputs", "notes",
            "kept", "results", "figures", "cells", "cost", "routine_id", "routine_name", "next_version")
    return {k: proposal.get(k) for k in keys}


def _version_view(v):
    return {k: v.get(k) for k in ("number", "created", "promoted_from", "change_note", "manifest", "run_zero")} | {"script_chars": len(v.get("script") or "")}


def _stream(instance, work):
    """Run `work` in a worker while the pane's queue drains into the response; `work` returns the closing message."""
    def generate():
        q = instance.output_manager.output_queue
        done = threading.Event()
        closing = {}

        def run():
            try:
                closing.update(work())
            except Exception as exc:                            # noqa: BLE001
                from bambooai.routines_host import RoutineRefused
                if isinstance(exc, RoutineRefused):
                    closing["routine_error"] = str(exc)
                else:
                    logger.exception("routine route failed")
                    closing["routine_error"] = f"something went wrong: {str(exc)[:300]}"
            finally:
                done.set()
        threading.Thread(target=run, daemon=True).start()
        last = time.time()
        while not done.is_set() or not q.empty():
            try:
                out = q.get(timeout=0.2)
                if out:
                    yield out + '\n'
                    last = time.time()
            except Empty:
                if time.time() - last > 5:                       # a heartbeat keeps the proxy from closing a quiet stream
                    yield '\n'
                    last = time.time()
        yield json.dumps(closing) + '\n'
    return Response(generate(), mimetype='application/json')


@routines_bp.route('/routines', methods=['GET'])
@requires_auth
def list_routines():
    try:
        st = _store()
        return jsonify({'routines': [st.summary(r) for r in st.all()]}), 200
    except Exception as exc:                                    # noqa: BLE001
        logger.exception("routines: list failed")
        return jsonify({'error': str(exc)}), 500


@routines_bp.route('/routines/by_origin/<thread_id>', methods=['GET'])
@routines_bp.route('/routines/by_origin/<thread_id>/<chain_id>', methods=['GET'])
@requires_auth
def routines_by_origin(thread_id, chain_id=None):
    """The routine versions born from a chain (the Save menu's state) or from any chain of a thread (the next-version
    offer): [{id, name, version, chain_id}]."""
    try:
        idx = _store().by_origin()
        out = []
        for (t, c), items in idx.items():
            if t == str(thread_id) and (chain_id is None or c == str(chain_id)):
                out.extend(dict(x, chain_id=c) for x in items)
        return jsonify({'routines': out}), 200
    except Exception as exc:                                    # noqa: BLE001
        return jsonify({'error': str(exc)}), 500


@routines_bp.route('/routines/<rid>', methods=['GET'])
@requires_auth
def get_routine(rid):
    r = _store().load(rid)
    if not r:
        return jsonify({'error': 'no such routine'}), 404
    out = {k: r.get(k) for k in ("id", "name", "created", "updated", "purpose", "question", "summary", "origin", "source", "current_version", "runs")}
    out["versions"] = [_version_view(v) for v in r.get("versions", [])]
    out["summary_card"] = _store().summary(r)
    try:
        import os
        a = _app()
        out["origin_available"] = os.path.exists(a.user_path('storage', 'favourites', str(r["origin"]["thread_id"]), f"{r['origin']['chain_id']}.json"))
    except Exception:                                           # noqa: BLE001
        out["origin_available"] = False
    return jsonify({'routine': out}), 200


@routines_bp.route('/routines/<rid>', methods=['DELETE'])
@requires_auth
def delete_routine(rid):
    if not _store().delete(rid):
        return jsonify({'error': 'no such routine'}), 404
    return jsonify({'message': 'routine deleted', 'id': rid}), 200


@routines_bp.route('/routines/<rid>/rename', methods=['POST'])
@requires_auth
def rename_routine(rid):
    st = _store()
    r = st.load(rid)
    if not r:
        return jsonify({'error': 'no such routine'}), 404
    name = str((request.json or {}).get('name') or '').strip()[:80]
    if not name:
        return jsonify({'error': 'a name is needed'}), 400
    r['name'] = name
    st.save(r)
    return jsonify({'message': 'renamed', 'routine': st.summary(r)}), 200


@routines_bp.route('/routines/<rid>/script', methods=['GET'])
@requires_auth
def routine_script(rid):
    """The current version's script as a file, the INPUTS block at the top with the defaults."""
    from analyst.routines import script_with_defaults
    import re
    r = _store().load(rid)
    if not r:
        return jsonify({'error': 'no such routine'}), 404
    try:
        number = int(request.args.get('version') or r.get('current_version') or 1)
    except ValueError:
        number = r.get('current_version') or 1
    v = next((x for x in r.get('versions', []) if x.get('number') == number), None)
    if not v:
        return jsonify({'error': 'no such version'}), 404
    name = re.sub(r'[^A-Za-z0-9_-]+', '_', r.get('name') or 'routine').strip('_') or 'routine'
    body = f"# {r.get('name')} - v{number} - made with BambooAI from the analysis of {r.get('origin', {}).get('chain_id')}\n" + script_with_defaults(v)
    return Response(body, mimetype='text/x-python', headers={'Content-Disposition': f'attachment; filename="{name}_v{number}.py"'})


@routines_bp.route('/routines/<rid>/cached', methods=['POST'])
@requires_auth
def routine_cached(rid):
    """Whether the load the run dialog asks for (the window, or the event) is already in the executor's cache with every
    auxiliary file the routine wants: the dialog says so under the window and uses it instead of downloading
    (2026-10-11). No executor (the local edition), or nothing matching: no hit, with the reason."""
    import requests as _requests
    from bambooai import routines_host
    from analyst.routines import cache_match
    a = _app()
    body = request.json or {}
    r = _store().load(rid)
    if r is None:
        return jsonify({'error': 'no such routine'}), 404
    plan = routines_host.load_plan(r)
    urls = None
    try:
        urls = a.get_dynamic_executor_urls(a.get_user_id())
    except Exception:                                              # noqa: BLE001
        urls = None
    if not urls:
        return jsonify({'hit': False, 'line': ''}), 200
    try:
        resp = _requests.get(f"{urls['EXECUTOR_API_BASE_URL']}/cache/inspect", params={'user_id': a.get_user_id()}, timeout=5)
        resp.raise_for_status()
        inspect = resp.json()
    except Exception as exc:                                       # noqa: BLE001
        logger.warning("routines: the cache could not be inspected (%s)", exc)
        return jsonify({'hit': False, 'line': ''}), 200
    out = cache_match(plan, inspect, start=body.get('start'), end=body.get('end'), race_id=body.get('race_id'))
    logger.info("routines: the cache asked for %s (%s %s | %s): %s", rid, body.get('start'), body.get('end'), body.get('race_id'), out.get('line') or 'nothing to ask')
    return jsonify(out), 200


@routines_bp.route('/routines/<rid>/precheck', methods=['POST'])
@requires_auth
def precheck_routine(rid):
    """Before a run: whether the data loaded now fits the routine and the chosen values are in it (the run dialog's line)."""
    a = _app()
    instance = a.get_bamboo_ai(session['session_id'])
    try:
        return jsonify(instance.precheck_routine(rid, (request.json or {}).get('values') or {}, aux=(request.json or {}).get('aux'), load=(request.json or {}).get('load'))), 200
    except Exception as exc:                                    # noqa: BLE001
        from bambooai.routines_host import RoutineRefused
        if isinstance(exc, RoutineRefused):
            return jsonify({'error': str(exc)}), 404
        logger.exception("routines: precheck failed")
        return jsonify({'error': str(exc)}), 500


@routines_bp.route('/routines/<rid>/run', methods=['POST'])
@requires_auth
def run_routine(rid):
    """A run on the data loaded now: the pane's rows and the tabs stream as an analysis's do; the closing message is
    routine_run (the record, the comparison, the numbers to step through) or routine_error."""
    a = _app()
    data = request.json or {}
    instance = a.get_bamboo_ai(session['session_id'])
    a.update_user_activity(a.get_user_id())

    def work():
        return {"routine_run": instance.run_routine(rid, data.get('values') or {}, data.get('compare_with') or 'previous', aux=data.get('aux'), load=data.get('load'))}
    return _stream(instance, work)


@routines_bp.route('/routines/<rid>/runs/<int:number>', methods=['GET'])
@requires_auth
def routine_run_view(rid, number):
    """A stored run as the main panes show it: the record, its printed output, its figures as the pane's plot messages."""
    from bambooai.routines_host import run_view, RoutineRefused
    st = _store()
    r = st.load(rid)
    if not r:
        return jsonify({'error': 'no such routine'}), 404
    try:
        view = run_view(r, st, number)
    except RoutineRefused as exc:
        return jsonify({'error': str(exc)}), 404
    figs = []
    for i, f in enumerate(view.pop('figures', []) or [], 1):
        try:
            obj = json.loads(f)
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get('type') == 'plot':
            obj['id'] = obj.get('id') or f'plot_{i}'
            figs.append(obj)
        else:
            figs.append({'type': 'plot', 'data': f, 'format': 'json', 'id': f'plot_{i}'})
    view['figures'] = figs
    return jsonify(view), 200


@routines_bp.route('/routines/propose', methods=['POST'])
@requires_auth
def propose_routine():
    """Save as routine, step one: the promoter reads the chain. A query for the account's purposes - the same
    authorisation as /query, charged as one when it completes."""
    a = _app()
    data = request.json or {}
    thread_id, chain_id = data.get('thread_id'), data.get('chain_id')
    if not thread_id or not chain_id:
        return jsonify({'error': 'thread_id and chain_id are needed'}), 400
    auth0_user_id = get_current_user_id()
    if auth0_user_id:
        auth_result = can_execute_chain(auth0_user_id)
        if auth_result.get('ok') and not (auth_result.get('data') or {}).get('allowed'):
            d = auth_result.get('data') or {}
            return jsonify({'error': 'authorization_failed', 'message': d.get('reason', 'not authorised'), 'reason': d.get('reason')}), 403
        try:
            increment_queries_counter(auth0_user_id)
        except Exception as exc:                                # noqa: BLE001
            logger.error(f"Failed to increment counter: {exc}")
    instance = a.get_bamboo_ai(session['session_id'])
    from bambooai import utils
    billing_chain = utils.next_chain_id()
    a.update_user_activity(a.get_user_id())

    def work():
        try:
            proposal = instance.propose_routine(str(thread_id), str(chain_id), routine_id=data.get('routine_id'), billing_chain_id=billing_chain)
        finally:
            try:
                instance.log_and_call_manager.charge_for_completed_query(billing_chain)
            except Exception:                                   # noqa: BLE001
                pass
        return {"routine_proposal": _view(proposal)}
    return _stream(instance, work)


@routines_bp.route('/routines/create', methods=['POST'])
@requires_auth
def create_routine():
    """Save as routine, step two: the choices, run zero, the record."""
    a = _app()
    data = request.json or {}
    proposal_id = data.get('proposal_id')
    if not proposal_id:
        return jsonify({'error': 'proposal_id is needed'}), 400
    instance = a.get_bamboo_ai(session['session_id'])
    choices = {k: data.get(k) for k in ("name", "purpose", "drop_inputs", "drop_results", "change_note")}

    def work():
        made = instance.create_routine(proposal_id, choices, routine_id=data.get('routine_id'))
        return {"routine_made": made}
    return _stream(instance, work)
