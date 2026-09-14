"""
kernel_service.py - HTTP surface for delv-e's PersistentKernel, hosted inside
the BambooAI executor container.

The kernel is RELOCATED, not rewritten. `kernel.py`, `executor.py`,
`toolkit.py` and `logger_config.py` are vendored from delv-e unchanged; this
module only adds session management and a wire protocol. Crash isolation,
checkpointing, transactional rollback and restart-and-replay all stay where
they already work - inside PersistentKernel, in this process.

Wire in from code_executor_api.py:

    from kernel_service import kernel_bp, init_kernel_service
    init_kernel_service(get_df=df_cache.get, evict_df=df_cache_evict)
    app.register_blueprint(kernel_bp)

Endpoints (all under /kernel):

    POST /kernel/start      {session_id?, df_id?, evict_cache?}
    POST /kernel/execute    {session_id, code, analysis_dir?, step?, commit?}
    POST /kernel/namespace  {session_id, max_items?, names?}
    POST /kernel/restore    {session_id, history}
    POST /kernel/discard    {session_id, reason?}
    POST /kernel/stop       {session_id}
    GET  /kernel/history/<session_id>
    GET  /kernel/status

Sessions are thread-scoped: a follow-up question extends into the same
namespace, which is how delv-e's --extend semantics reach the web app. They are
reaped on their own idle clock, independent of the container's, so a kernel
does not hold a DataFrame for 45 minutes because a browser tab stayed open.
"""

import os
import threading
import time
import uuid

from flask import Blueprint, jsonify, request

from kernel import PersistentKernel, STEP_TIMEOUT

kernel_bp = Blueprint("kernel", __name__, url_prefix="/kernel")

# One kernel per container by default. A second concurrent investigation would
# double the resident DataFrame and every derived object; raise this only with
# measurements in hand.
MAX_SESSIONS = int(os.getenv("KERNEL_MAX_SESSIONS", "1"))
# The kernel sits IDLE through every non-kernel phase. In one auto_explore
# run that was Synthesizer 422s + Editor 142s + Code Generator 541s +
# Solution Summarizer 304s, then four more agents before the next chain's
# first step - and the session was reaped at "idle 1840s". 3600 covers
# that with margin. It only costs memory while a user is mid-thread, and
# a reaped session is now recoverable rather than fatal, so this is
# headroom rather than the fix.
IDLE_TIMEOUT = int(os.getenv("KERNEL_IDLE_TIMEOUT", "3600"))  # seconds
REAP_INTERVAL = int(os.getenv("KERNEL_REAP_INTERVAL", "60"))  # seconds between sweeps

# Injected by init_kernel_service so this module does not import
# code_executor_api (which imports plenty and would be circular).
_get_df = None
_evict_df = None


def init_kernel_service(get_df=None, evict_df=None):
    """Supply the DataFrame cache accessors. `get_df(df_id)` returns a DataFrame
    or None; `evict_df(df_id)` drops it from the Flask process's cache."""
    global _get_df, _evict_df
    _get_df, _evict_df = get_df, evict_df


def log(msg):
    print(f"[KERNEL] {time.strftime('%Y-%m-%d %H:%M:%S')} - {msg}", flush=True)


class _Session:
    """One PersistentKernel plus the bookkeeping needed to reap it."""

    def __init__(self, session_id, kernel, df_id=None):
        self.id = session_id
        self.kernel = kernel
        self.df_id = df_id
        self.created = time.time()
        self.last_used = time.time()
        self.steps = 0
        self.schema = None      # set by start(), returned by info()
        # Serialises access to one kernel. The worker holds a single namespace
        # and a single stdin pipe; two concurrent executes would interleave on
        # both. Callers are expected to be sequential anyway - this is a
        # correctness backstop, not a throughput feature.
        self.lock = threading.Lock()

    def touch(self):
        self.last_used = time.time()

    def info(self):
        return {
            "session_id": self.id,
            "df_id": self.df_id,
            # Carried on the session so a REATTACH returns it too. It used to be
            # built at creation and returned once, so an extending run got no
            # schema and could not tell "reattached successfully" from "started
            # empty" - which is exactly the state the driver now refuses.
            "schema": self.schema,
            "steps": self.steps,
            "age_s": round(time.time() - self.created, 1),
            "idle_s": round(time.time() - self.last_used, 1),
            "history_len": len(self.kernel.history),
        }


_sessions = {}
_sessions_lock = threading.Lock()


def _reaper():
    while True:
        time.sleep(REAP_INTERVAL)
        try:
            now = time.time()
            with _sessions_lock:
                stale = [s for s in _sessions.values()
                         if now - s.last_used > IDLE_TIMEOUT]
                for s in stale:
                    _sessions.pop(s.id, None)
            for s in stale:
                log(f"reaping idle session {s.id} "
                    f"(idle {now - s.last_used:.0f}s)")
                _shutdown(s)
        except Exception as exc:                            # noqa: BLE001
            log(f"reaper error: {exc}")


def _shutdown(session):
    """Tear a session down outside the registry lock - cleanup kills a
    subprocess and waits on it, which must not block other requests."""
    try:
        with session.lock:
            session.kernel.cleanup()
    except Exception as exc:                                # noqa: BLE001
        log(f"cleanup failed for {session.id}: {exc}")


threading.Thread(target=_reaper, daemon=True).start()


def _session_or_404(payload):
    sid = (payload or {}).get("session_id")
    if not sid:
        return None, (jsonify({"error": "session_id required"}), 400)
    with _sessions_lock:
        s = _sessions.get(sid)
    if s is None:
        # A gone session is the signal the driver turns into "synthesize over
        # the evidence we already have", so it must be distinguishable from a
        # transport failure. 410 is deliberate: the resource existed and does
        # not any more.
        return None, (jsonify({"error": "no such kernel session",
                               "session_id": sid, "gone": True}), 410)
    s.touch()
    return s, None


@kernel_bp.route("/start", methods=["POST"])
def start():
    data = request.json or {}
    df_id = data.get("df_id")
    requested_session = data.get("session_id")
    session_id = requested_session or uuid.uuid4().hex
    # Default OFF - see RemoteKernel.__init__. The cached frame is what
    # /df_utils/* serves to the Code Generator after the investigation.
    evict = bool(data.get("evict_cache", False))

    with _sessions_lock:
        if session_id in _sessions:
            s = _sessions[session_id]
            s.touch()
            # A warm reattach carries the live namespace back (evidence
            # audit, 2026-08-14): without it the client's registry stays
            # empty, turn 1 renders a blank registry over a live kernel,
            # and warm is indistinguishable from cold - for the model AND
            # for anyone reading a run log.
            return jsonify({"session_id": s.id, "reused": True, **s.info(),
                            "registry": s.kernel.registry})

        # A NAMED session that is not here is GONE, not a request to create one.
        #
        # The caller asked to reattach because it believes the namespace still
        # holds its objects. Silently starting an empty session under the same
        # id told it "reused" when nothing was reused: it then ran an entire
        # investigation whose every prompt asserted `df` was loaded, against a
        # kernel where it was not. Seen in the field as
        #   reaping idle session c019...  (idle 1840s)
        #   started session c019...       (df_id=None, shape=None)
        # 410 lets the client fall back to a fresh start and replay its
        # committed history, which it already knows how to do.
        #
        # UNCONDITIONALLY - df_id does not soften it. The driver sends df_id
        # with every start (a reaped session needs it to rebuild), so a df_id
        # carve-out here rebuilt the kernel under the SAME id with an empty
        # namespace. That same-id answer is the one shape that defeats both
        # gone-detectors at once: the client's 410 fallback never fires, and
        # the driver's `kernel.session_id != session_id` check passes, so the
        # committed history is never replayed. The frame was there; every
        # derived object was not.
        if requested_session:
            return jsonify({
                "error": "session %s no longer exists (reaped, or the "
                         "executor restarted); start fresh and replay"
                         % requested_session,
                "gone": True,
            }), 410
        stale = None
        if len(_sessions) >= MAX_SESSIONS:
            if not data.get("force"):
                # Report the occupants so the caller can decide. Without this a
                # driver that died mid-run locks the user out until the idle
                # reaper fires - up to IDLE_TIMEOUT of dead time for something
                # that is already known to be abandoned.
                return jsonify({
                    "error": "kernel capacity reached",
                    "active": [s.info() for s in _sessions.values()],
                }), 429
            # force=True: reclaim the least recently used session. The caller is
            # asserting the old run is abandoned; only it can know that.
            stale = min(_sessions.values(), key=lambda s: s.last_used)
            _sessions.pop(stale.id, None)
    if stale is not None:
        log(f"reclaiming session {stale.id} (idle "
            f"{time.time() - stale.last_used:.0f}s) to make room")
        _shutdown(stale)

    df = None
    if df_id is not None:
        if _get_df is None:
            return jsonify({"error": "kernel service not initialised"}), 500
        df = _get_df(df_id)
        if df is None:
            return jsonify({"error": f"df_id {df_id} not in cache"}), 404

    try:
        # PersistentKernel pickles the frame to a temp file for the worker to
        # load. That is the second copy; the cache copy is the one we can drop.
        kernel = PersistentKernel(
            df=df, step_timeout=int(data.get("step_timeout") or STEP_TIMEOUT))
    except Exception as exc:                                # noqa: BLE001
        log(f"kernel start failed: {exc}")
        return jsonify({"error": f"kernel failed to start: {exc}"}), 500

    session = _Session(session_id, kernel, df_id=df_id)
    with _sessions_lock:
        _sessions[session_id] = session

    # Build the schema HERE, while a real DataFrame is still in hand. The
    # driver runs in the web app process, which never sees the frame - and
    # after the eviction below nothing in this process does either. Cheap
    # (one pass over the columns) and it saves shipping the frame anywhere.
    #
    # Stored ON the session so a later reattach returns it as well; an
    # extending run that got no schema back could not tell a live namespace
    # from an empty one.
    schema = None
    if df is not None:
        try:
            from dataio import build_schema
            schema = build_schema(df)
        except Exception as exc:                            # noqa: BLE001
            log(f"schema build failed: {exc}")
    session.schema = schema

    # The kernel's frame diverges from the cached one on the first in-place
    # edit, so they are not two views of one thing and there is nothing to be
    # gained by keeping both. The original stays on disk / re-uploadable; this
    # is the copy that matters now.
    if evict and df_id is not None and _evict_df is not None:
        try:
            _evict_df(df_id)
            log(f"evicted {df_id} from the request cache; kernel owns it now")
        except Exception as exc:                            # noqa: BLE001
            log(f"cache eviction failed for {df_id}: {exc}")

    shape = None if df is None else list(df.shape)
    log(f"started session {session_id} (df_id={df_id}, shape={shape})")
    return jsonify({"session_id": session_id, "reused": False,
                    "shape": shape, "schema": schema,
                    "step_timeout": kernel.step_timeout})


@kernel_bp.route("/execute", methods=["POST"])
def execute():
    data = request.json or {}
    session, err = _session_or_404(data)
    if err:
        return err

    code = data.get("code")
    if not code:
        return jsonify({"error": "code required"}), 400

    with session.lock:
        try:
            stdout, error, plots = session.kernel.execute(
                code,
                analysis_dir=data.get("analysis_dir") or None,
                step=data.get("step"),
                commit=bool(data.get("commit", True)),
            )
        except Exception as exc:                            # noqa: BLE001
            # PersistentKernel handles worker death internally; reaching here
            # means the kernel object itself is unusable.
            log(f"session {session.id} raised: {exc}")
            return jsonify({"error": str(exc), "fatal": True}), 500
        session.steps += 1
        registry = session.kernel.registry

    return jsonify({
        "stdout": stdout,
        "error": error,
        # Container-local paths. Nothing fetches them today: in the planner
        # architecture the Code Generator emits the user-facing visuals. Add a
        # /kernel/plot endpoint if that changes.
        "plots": plots,
        "registry": registry,
        "history_len": len(session.kernel.history),
    })


@kernel_bp.route("/namespace", methods=["POST"])
def namespace():
    data = request.json or {}
    session, err = _session_or_404(data)
    if err:
        return err
    names = data.get("names")
    with session.lock:
        text = session.kernel.describe_namespace(
            max_items=int(data.get("max_items", 120)),
            names=set(names) if names is not None else None,
        )
        registry = session.kernel.registry
    return jsonify({"text": text, "registry": registry})


@kernel_bp.route("/restore", methods=["POST"])
def restore():
    """Replay a prior run's code history into a fresh namespace (--resume /
    --extend). Best-effort by contract: a step that fails to replay is skipped
    and the namespace may be partial."""
    data = request.json or {}
    session, err = _session_or_404(data)
    if err:
        return err
    history = data.get("history") or []
    with session.lock:
        t0 = time.time()
        session.kernel.restore_history(history)
        registry = session.kernel.registry
        # The replayed history is NOT a prefix of the input: restore_history
        # skips a step that fails and keeps going, so a mid-list failure leaves
        # a gap. Return the authoritative list rather than a count, or the
        # client's copy silently diverges - and that copy is what the Code
        # Generator consolidates and what kernel_history.json persists.
        replayed = session.kernel.history
    log(f"session {session.id}: replayed {len(replayed)}/{len(history)} steps "
        f"in {time.time() - t0:.1f}s")
    return jsonify({"restored": len(replayed), "requested": len(history),
                    "history": replayed, "registry": registry})


@kernel_bp.route("/discard", methods=["POST"])
def discard():
    data = request.json or {}
    session, err = _session_or_404(data)
    if err:
        return err
    with session.lock:
        discarded = session.kernel.discard_uncommitted(
            reason=data.get("reason") or "discarding uncommitted state")
        registry = session.kernel.registry
    return jsonify({"discarded": bool(discarded), "registry": registry})


@kernel_bp.route("/history/<session_id>", methods=["GET"])
def history(session_id):
    session, err = _session_or_404({"session_id": session_id})
    if err:
        return err
    with session.lock:
        return jsonify({"history": session.kernel.history})


@kernel_bp.route("/stop", methods=["POST"])
def stop():
    data = request.json or {}
    sid = data.get("session_id")
    with _sessions_lock:
        session = _sessions.pop(sid, None)
    if session is None:
        return jsonify({"stopped": False, "reason": "no such session"}), 404
    _shutdown(session)
    log(f"stopped session {sid}")
    return jsonify({"stopped": True})


@kernel_bp.route("/status", methods=["GET"])
def status():
    with _sessions_lock:
        sessions = [s.info() for s in _sessions.values()]
    return jsonify({"sessions": sessions, "max_sessions": MAX_SESSIONS,
                    "idle_timeout_s": IDLE_TIMEOUT})