"""
kernel_client.py - a stand-in for delv-e's PersistentKernel that runs the
namespace inside the BambooAI executor container.

Interface-compatible with PersistentKernel, so it drops straight into the seam
delv-e already exposes:

    kernel = RemoteKernel(base_url=executor_url, df_id=df_id)
    log, kernel, nav, briefing = run_investigation(..., kernel=kernel)

What is deliberately NOT here: checkpointing, restart-and-replay, transactional
rollback, the security blacklist, the worker protocol. All of that stays inside
PersistentKernel, in the container, where it already works and where the
checkpoint file lives. This class is transport.

Error model - the distinction matters:

  * Code that fails is NOT an exception. `execute` returns the traceback in the
    error slot exactly as PersistentKernel does, because the Investigator is
    supposed to see it and adapt.

  * The kernel becoming unreachable IS an exception (KernelUnavailable). The
    container died, Flask restarted, or the session was reaped. The driver
    should catch it and force synthesis over the evidence already in the log
    rather than losing the run.
"""

import logging

import requests

logger = logging.getLogger(__name__)

# Must exceed the container's STEP_TIMEOUT (600s) or a legitimately slow step
# looks like a dead kernel. Connect timeout stays short: an unreachable
# container should fail fast.
CONNECT_TIMEOUT = 10
READ_TIMEOUT = 660
RESTORE_READ_TIMEOUT = 1800  # a long replay is one request


class KernelUnavailable(RuntimeError):
    """The kernel session is gone or unreachable. Not a code error - the
    namespace itself is lost, and the run cannot continue against it."""

    def __init__(self, message, gone=False):
        super().__init__(message)
        # True when the container answered and said the session no longer
        # exists (reaped, or Flask restarted). False for transport failures,
        # which may be transient.
        self.gone = gone


class RemoteKernel:
    """PersistentKernel's interface, backed by /kernel/* in the executor."""

    def __init__(self, base_url, df_id=None, session_id=None,
                 evict_cache=False, step_timeout=None, session=None,
                 force=False, generated_dir=None):
        """`force=True` reclaims the least recently used session when the
        executor is at capacity. Use it when starting a NEW investigation for a
        user whose previous run is known to be over - otherwise a driver that
        died mid-run locks them out until the idle reaper fires. Never use it
        for a follow-up that means to extend an existing namespace."""
        self.base_url = base_url.rstrip("/")
        self.df_id = df_id
        self._http = session or requests.Session()
        self._closed = False

        # Mirrors PersistentKernel.registry. investigation.py reads this
        # directly (_live_names, _referenced_names), so it has to stay current
        # without a round trip - every response that can change it returns it.
        self.registry = {"namespace": [], "columns": []}
        self._history = []

        payload = {
            "session_id": session_id,
            "df_id": df_id,
            "generated_dir": generated_dir,      # where DS.save puts a dataset for the person (2026-10-06)
            "evict_cache": evict_cache,
            "step_timeout": step_timeout,
            "force": force,
        }
        try:
            started = self._post("/kernel/start", payload)
        except KernelUnavailable as exc:
            # The session we asked to reattach to is gone - reaped while the
            # run was between chains, most likely. Start a fresh one instead;
            # the driver replays the committed history into it. Retrying with
            # the same id would only be refused again.
            if not (getattr(exc, "gone", False) and session_id):
                raise
            logger.info("Session %s is gone; starting a fresh kernel.", session_id)
            payload["session_id"] = None
            payload["force"] = True
            started = self._post("/kernel/start", payload)
        if (session_id and started.get("session_id") == session_id
                and started.get("reused") is False):
            # An older kernel_service resurrects a reaped named session IN
            # PLACE when a df_id rides along, instead of answering 410. The
            # result is an EMPTY namespace under the OLD id - which defeats
            # both gone-detectors at once: this client's 410 fallback above
            # never fires, and the driver's `kernel.session_id != session_id`
            # test passes, so the committed history is never replayed and
            # every prompt asserts objects the kernel does not hold.
            #
            # The web app and the container deploy separately (the image only
            # rebuilds when containers/ changed), so this skew is a real
            # state, not a hypothetical. Discard the impostor and start an
            # honestly-fresh session, restoring the client's one contract:
            # coming back with a DIFFERENT id means the old namespace is gone.
            logger.warning(
                "Session %s was resurrected empty in place (older "
                "kernel_service); discarding it and starting fresh.", session_id)
            try:
                self._http.post(f"{self.base_url}/kernel/stop",
                                json={"session_id": session_id},
                                timeout=(CONNECT_TIMEOUT, 30))
            except requests.RequestException:
                pass
            payload["session_id"] = None
            payload["force"] = True
            started = self._post("/kernel/start", payload)
        reg = started.get("registry")
        if reg:
            # Warm reattach: adopt the server's live namespace registry so
            # the very first prompt shows what is inherited (evidence
            # audit, 2026-08-14 - an empty registry over a warm kernel is
            # how 'cold' got misdiagnosed, and how a model gets told
            # nothing survived when everything did).
            self.registry = reg

        self.session_id = started["session_id"]
        self.shape = started.get("shape")
        # Built container-side at start, before the cache copy is evicted. The
        # driver runs in the web app process, which never holds the frame, so
        # this is the only place the schema can come from.
        self.schema = started.get("schema")
        self.step_timeout = step_timeout or started.get("step_timeout", 600)

    # ----- transport -------------------------------------------------------

    def _post(self, path, payload, read_timeout=READ_TIMEOUT):
        if self._closed:
            raise KernelUnavailable("kernel already cleaned up", gone=True)
        try:
            r = self._http.post(f"{self.base_url}{path}", json=payload,
                                timeout=(CONNECT_TIMEOUT, read_timeout))
        except requests.Timeout as exc:
            raise KernelUnavailable(
                f"kernel did not respond within {read_timeout}s: {exc}") from exc
        except requests.RequestException as exc:
            raise KernelUnavailable(f"kernel unreachable: {exc}") from exc

        if r.status_code == 404 and "text/html" in r.headers.get("Content-Type", ""):
            # Flask's own 404 page, not our JSON: the /kernel/* blueprint is not
            # registered at all. code_executor_api guards that import so /execute
            # keeps working, which means the container looks healthy and only
            # deep mode fails. Dumping the HTML here told the reader nothing.
            raise KernelUnavailable(
                f"the executor at {self.base_url} has no /kernel endpoints. The "
                f"container is running an image without the kernel modules, or "
                f"their import failed. Check: "
                f"curl -s {self.base_url}/health  -> kernel_service.error, "
                f"then rebuild containers/executor and retire the old containers.")
        if r.status_code == 410:
            raise KernelUnavailable(
                "kernel session no longer exists (reaped, or the executor "
                "restarted); the namespace is gone", gone=True)
        if r.status_code == 429:
            raise KernelUnavailable("executor has no free kernel capacity")
        if r.status_code >= 400:
            detail = ""
            try:
                detail = r.json().get("error", "")
            except ValueError:
                detail = r.text[:200]
            raise KernelUnavailable(f"kernel error {r.status_code}: {detail}")
        return r.json()

    def _sync(self, payload):
        reg = payload.get("registry")
        if reg is not None:
            self.registry = reg
        return payload

    # ----- the PersistentKernel contract -----------------------------------

    def execute(self, code, analysis_dir=None, step=None, commit=True):
        """One step in the persistent namespace. Returns (stdout, error, plots),
        matching PersistentKernel.execute.

        Commit semantics are unchanged and enforced server-side: a failed
        attempt is rolled back to the last committed state before this returns,
        and only committed code enters the replayable history.

        `analysis_dir` is a CONTAINER-side path. delv-e's chart pass passes a
        client path here and then checks the file locally, which cannot work
        remotely - in the planner architecture the Code Generator produces the
        user-facing visuals instead, so nothing depends on it.
        """
        res = self._sync(self._post("/kernel/execute", {
            "session_id": self.session_id,
            "code": code,
            "analysis_dir": analysis_dir,
            "step": step,
            "commit": commit,
        }))
        if res.get("fatal"):
            raise KernelUnavailable(res.get("error") or "kernel failed")
        if commit and not res.get("error"):
            self._history.append(code)
        # Cheap drift detector. The server's history is authoritative; a
        # mismatch means our local copy is wrong, and a wrong history hands the
        # Code Generator code that never ran. Resync rather than guess.
        server_len = res.get("history_len")
        if server_len is not None and server_len != len(self._history):
            self._history = self._fetch_history()
        self.last_results = list(res.get("results") or [])            # RESULT(...) records of this step
        return res.get("stdout"), res.get("error"), res.get("plots") or []

    def _fetch_history(self):
        try:
            r = self._http.get(
                f"{self.base_url}/kernel/history/{self.session_id}",
                timeout=(CONNECT_TIMEOUT, 60))
            r.raise_for_status()
            return list(r.json().get("history") or [])
        except (requests.RequestException, ValueError) as exc:
            raise KernelUnavailable(
                f"could not resync kernel history: {exc}") from exc

    def describe_namespace(self, max_items=120, names=None):
        """Registry text for the prompts. Delegated rather than reimplemented so
        the formatting rules (recency window, name-only tail) live in one
        place. Two calls per turn against ~zero cost relative to an LLM call."""
        res = self._sync(self._post("/kernel/namespace", {
            "session_id": self.session_id,
            "max_items": max_items,
            "names": sorted(names) if names is not None else None,
        }))
        return res.get("text", "")

    def restore_history(self, history):
        """Replay a prior run's history into the namespace (--resume/--extend).
        Best-effort, as upstream: a step that fails to replay is skipped and the
        replay continues.

        Because failures are skipped rather than fatal, what came back is NOT a
        prefix of what went in - a mid-list failure leaves a gap. Adopt the
        server's list verbatim; deriving it from a count here was a real bug,
        and a silent one, since this history is what the Code Generator
        consolidates and what kernel_history.json persists for a later resume.
        """
        res = self._sync(self._post(
            "/kernel/restore",
            {"session_id": self.session_id, "history": list(history or [])},
            read_timeout=RESTORE_READ_TIMEOUT))
        self._history = list(res.get("history") or [])
        return len(self._history)

    def discard_uncommitted(self, reason="discarding uncommitted state"):
        res = self._sync(self._post("/kernel/discard", {
            "session_id": self.session_id, "reason": reason}))
        return bool(res.get("discarded"))

    @property
    def history(self):
        """The ordered code blocks that executed successfully. This is what the
        Code Generator consolidates into the monolithic script, and what
        persists to kernel_history.json for a later resume."""
        return list(self._history)

    def cleanup(self):
        if self._closed:
            return
        self._closed = True
        try:
            self._http.post(f"{self.base_url}/kernel/stop",
                            json={"session_id": self.session_id},
                            timeout=(CONNECT_TIMEOUT, 30))
        except requests.RequestException:
            # The container is already gone, which is the outcome we wanted.
            pass

    def detach(self):
        """Drop the client without stopping the kernel. Use between turns of a
        thread that will extend into the same namespace; the container's idle
        reaper still owns the eventual teardown."""
        self._closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.cleanup()
        return False