"""The code map of one chain (analyst/codemap, docs/CODEMAP_DESIGN.md): the route the modal calls.

    GET /code_map/<thread_id>/<chain_id>
      400  ids not of the thread's and chain's shapes
      404  no such chain in the thread
      200  {"thread_id", "chain_id", "built": "end" | "now", "map": <view>}   stored at the chain's end, or built now
      200  {"thread_id", "chain_id", "error": "<one line>"}                   the build failed: the modal says so
      200  {"thread_id", "chain_id", "state": "running" | "unfinished"}       no map: the chain is running, or ended
                                                                             without an answer (asked, stopped, failed)

The notebook is the live instance's when it holds the thread, else the thread file. A map is only ever of an
answered chain. A chain without a stored map, or with one of an older version, is built now from the inputs the
stored map kept (else from the run's data record) and cached in this process; it is never written back, because the
live session rewrites the thread file after every turn. An ancestor without exports (an old run) is built once,
root first, from the exports of the ones before it. The route is thin: the map is built and tested in the library."""
import re
from collections import OrderedDict

from flask import Blueprint, jsonify, session
from auth import requires_auth
from logger_config import get_logger
from analyst import codemap
from analyst.notebook import NotebookStore

logger = get_logger(__name__)
code_map_bp = Blueprint('code_map', __name__)

_THREAD_RE = re.compile(r'^\d{1,20}$')
_CHAIN_RE = re.compile(r'^[0-9A-Za-z]{1,24}$')
_CACHE = OrderedDict()          # (storage dir, thread, chain, version) -> the map built now; a few dozen, oldest out
_CACHE_SIZE = 64


def _notebook(thread_id):
    """The live instance's notebook when it holds this thread, else the thread file; the storage dir keys the cache."""
    from app import bamboo_ai_instances, user_path
    storage = user_path('storage')
    session_id = session.get('session_id')
    inst = bamboo_ai_instances.get(session_id) if session_id else None
    nb = getattr(inst, 'notebook', None)
    if nb is not None and str(getattr(nb, 'thread_id', '')) == str(thread_id):
        return nb, storage
    return NotebookStore(storage).load(thread_id), storage


def _stored(run):
    cm = run.code_map if isinstance(getattr(run, 'code_map', None), dict) else {}
    return cm


def _current(cm):
    return bool(cm.get('view')) and cm.get('version') == codemap.VERSION


def _build_now(nb, run, storage):
    """The map of a run without a current one, from the inputs its stored map kept; its ancestors without current
    exports first, root to leaf, each once per process."""
    key = (storage, str(nb.thread_id), str(run.id), codemap.VERSION)
    if key in _CACHE:
        return _CACHE[key]
    ancestors = {}
    for r in nb.computed_runs(run.id)[:-1]:
        cm = _stored(r)
        if cm.get('exports') and cm.get('version') == codemap.VERSION:
            continue                                      # build() reads a current map's exports from the run itself
        akey = (storage, str(nb.thread_id), str(r.id), codemap.VERSION)
        if akey not in _CACHE:
            _remember(akey, codemap.build(nb, r, inputs=cm.get('inputs') or None, ancestors=ancestors))
        ancestors[r.id] = _CACHE[akey].get('exports') or {}
    cm = _stored(run)
    out = codemap.build(nb, run, inputs=cm.get('inputs') or None, ancestors=ancestors)
    if out.get('view'):
        _remember(key, out)                               # a failure is not kept: the next request tries again
    return out


def _remember(key, value):
    _CACHE[key] = value
    while len(_CACHE) > _CACHE_SIZE:
        _CACHE.popitem(last=False)


@code_map_bp.route('/code_map/<thread_id>/<chain_id>', methods=['GET'])
@requires_auth
def code_map(thread_id, chain_id):
    if not _THREAD_RE.match(str(thread_id)) or not _CHAIN_RE.match(str(chain_id)):
        return jsonify({'message': 'Invalid id.'}), 400
    try:
        nb, storage = _notebook(thread_id)
    except Exception as exc:                                  # noqa: BLE001
        logger.warning("code map: thread %s could not be read: %s", thread_id, exc)
        return jsonify({'message': 'No such thread.'}), 404
    run = nb.runs.get(str(chain_id))
    if run is None:
        return jsonify({'message': 'No such chain.'}), 404
    head = {'thread_id': str(thread_id), 'chain_id': str(chain_id)}
    if run.status == 'running':
        return jsonify(dict(head, state='running'))
    if run.status != 'answered':
        return jsonify(dict(head, state='unfinished'))
    cm = _stored(run)
    if _current(cm):
        return jsonify(dict(head, built='end', map=cm['view']))
    built = _build_now(nb, run, storage)
    if built.get('error') or not built.get('view'):
        return jsonify(dict(head, error=str(built.get('error') or 'the map could not be built')))
    return jsonify(dict(head, built='now', map=built['view']))
