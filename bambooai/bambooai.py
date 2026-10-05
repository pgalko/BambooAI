"""BambooAI - one analyst, one kernel, one notebook, one report.

The instance the web app holds per user. A question arrives; the analyst
session answers it in a persistent kernel, keeps the notebook, writes the
technical report and its plain-language rewrite; the assembled script is
replayed in a fresh kernel; everything is stored as a tree of runs per thread
and streamed to the browser as it lands.

Modes are budget presets of the same session: quick / deep / adaptive.
"""
import json
import os
import shutil
import re
import threading
import time

import pandas as pd

from bambooai import log_manager, output_manager, web_output_manager, utils, executor_client, code_executor, documents, reading
from bambooai.messages.prompts import PromptManager
from bambooai.models import ModelManager
from bambooai import synthesis_infographic
from analyst import Session, Budget, Notebook, NotebookStore
from analyst.replay import rehydrate
from logger_config import get_logger

logger = get_logger(__name__)


class ExecutionInterrupted(Exception):
    """The user stopped the run."""


def _cfg_int(cfg, key, default):
    try:
        return int((cfg or {}).get(key, default))
    except (TypeError, ValueError):
        return default


class BambooAI:
    def __init__(self, df: pd.DataFrame = None,
                 user_id: str = None,
                 api_keys: dict = None,
                 auxiliary_datasets: list = None,
                 max_conversations: int = 4,
                 search_tool: bool = False,
                 exploratory: bool = True,
                 memory_path: str = None,
                 planning: bool = False,
                 webui: bool = False,
                 df_id: str = None,
                 custom_prompt_file: str = None,
                 executor_api_url: str = None, execution_mode: str = None):
        self.user_id = user_id
        self.api_keys = api_keys if api_keys is not None else {}
        self.thread_id = None
        self.chain_id = None
        self.webui = webui
        self.output_manager = web_output_manager.WebOutputManager() if webui else output_manager.OutputManager()
        self.execution_mode = execution_mode or os.getenv('EXECUTION_MODE', 'local')   # the app passes its own (2026-09-14)
        self.executor_api_url = executor_api_url
        self.api_client = executor_client.ExecutorAPIClient(base_url=self.executor_api_url) if self.executor_api_url else None
        # the executor runs the reproduction script exactly as the old pipeline ran its
        # consolidated script: it returns the results text, the Plotly figures and any
        # generated datasets, in local or api mode
        self.executor = code_executor.CodeExecutor(webui=self.webui, mode=self.execution_mode,
                                                   api_client=self.api_client, user_id=self.user_id)
        self._replay = {}                 # run id -> {"results", "plots", "datasets"} from the replay
        self._mode_label = 'Deep'
        self.df_name = ''
        self._last_search_query = ''
        self._last_search_sources = []
        self.df = df
        self.df_id = df_id
        self.auxiliary_datasets = auxiliary_datasets or []
        self.memory_path = memory_path
        self.search_tool = bool(search_tool)
        self.exploratory = exploratory
        self.planning = planning            # the UI's dial: True -> the adaptive preset
        self.kill_signal = False
        self._stop_event = threading.Event()
        self.synthesis_infographic = os.getenv('SYNTHESIS_INFOGRAPHIC', 'true').lower() in ('1', 'true', 'yes')

        # Models, prompts, logging - unchanged seams.
        self.models = ModelManager(user_id=self.user_id, api_keys=self.api_keys)
        self.llm_stream = self.models.llm_stream
        self.model_dict = self.models.get_model_properties()
        self.reasoning_models = [m for m, info in self.model_dict.items() if info.get('capability') == 'reasoning']
        self.prompts = PromptManager(custom_prompt_file_path=custom_prompt_file)
        self.log_and_call_manager = log_manager.LogAndCallManager(self.model_dict, user_id=self.user_id, thread_id=self.thread_id)
        logger.info("Run log: %s | consolidated: %s (cwd %s)", os.path.abspath(self.log_and_call_manager.run_log_file_path),
                    os.path.abspath(self.log_and_call_manager.consolidated_log_file_path), os.getcwd())

        # Budgets: the tier's turn ceilings, if the config carries them.
        cfg = getattr(self.models, "config", {}) or {}
        self.turns_quick = _cfg_int(cfg, "analyst_turns_quick", 5)      # five since 2026-09-09: two left no room to compute before the report
        self.turns_deep = _cfg_int(cfg, "analyst_turns_deep", 15)
        self.turns_adaptive = _cfg_int(cfg, "analyst_turns_adaptive", 50)
        self.review_every = _cfg_int(cfg, "analyst_review_every", 8)      # Adaptive's self-review interval; 0 = none (2026-09-10)

        # Storage: the notebook tree, one file per thread, under the user's storage.
        base = os.path.join(os.getcwd(), 'storage', self.user_id) if self.user_id else os.path.join(os.getcwd(), 'storage')
        self.store = NotebookStore(base)
        self.notebook = None

        # The kernel: one per thread, kept warm between runs; rehydrated on a branch.
        self._kernel = None
        self._kernel_tip = None          # the run id whose state the kernel holds
        self._search = None
        if self.search_tool:
            try:
                from bambooai.google_search import SmartSearchOrchestrator
                self._search_orchestrator = SmartSearchOrchestrator(
                    prompt_manager=self.prompts, log_and_call_manager=self.log_and_call_manager,
                    output_manager=self.output_manager, api_keys=self.api_keys)
                self._search = self._web_search
            except Exception as exc:                          # noqa: BLE001
                logger.warning("Web search unavailable: %s", exc)

    # ------------------------------------------------------------------ seats
    def _seat(self):
        """The analyst seat: 'Analyst' when the config has it, else the
        'Investigator' seat every existing config carries."""
        agents = {a.get('agent') for a in (getattr(self.models, "config", {}) or {}).get('agent_configs', [])}
        return 'Analyst' if 'Analyst' in agents else 'Investigator'

    def _review_seat(self):
        """The seat a self-review turn runs on (2026-09-10): 'Reviewer' when the config carries one -
        a stronger model at the run's decision points - else the analyst seat itself."""
        agents = {a.get('agent') for a in (getattr(self.models, "config", {}) or {}).get('agent_configs', [])}
        return 'Reviewer' if 'Reviewer' in agents else self._seat()

    def _rewrite_seat(self):
        """The seat the plain-language rewrite runs on (2026-09-11): 'Rewriter' when the config carries one -
        a fast, cheap model at low effort for a prose task whose numbers the guard checks - else the analyst seat."""
        agents = {a.get('agent') for a in (getattr(self.models, "config", {}) or {}).get('agent_configs', [])}
        return 'Rewriter' if 'Rewriter' in agents else self._seat()

    def _llm(self, system: str, user: str, review: bool = False, rewrite: bool = False, **hints):
        """The model call the session uses: the app's model layer (streaming,
        telemetry, retries), returning (text, {'cost': delta}). A self-review
        turn (review=True) runs on the Reviewer seat; its cost is accounted to
        that seat and counts against the run's budget like any other call."""
        if self.kill_signal or self._stop_event.is_set():
            raise ExecutionInterrupted("stopped by the user")
        before = self._chain_cost()
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        text = self.llm_stream(self.prompts, self.log_and_call_manager, self.output_manager, messages,
                               agent=self._review_seat() if review else (self._rewrite_seat() if rewrite else self._seat()), chain_id=self.chain_id,
                               reasoning_models=self.reasoning_models)
        if isinstance(text, tuple):
            text = text[0]
        return text or "", {"cost": max(0.0, self._chain_cost() - before)}

    def _chain_cost(self):
        ts = self.log_and_call_manager.token_summary
        summary = ts.get(self.chain_id) or ts.get(str(self.chain_id)) or {}
        return float(summary.get('total_cost', 0.0) or 0.0)

    # ---------------------------------------------------------------- kernel
    def _new_kernel(self):
        if self.execution_mode == 'api' and self.executor_api_url:
            from bambooai.kernel_client import RemoteKernel
            try:
                logger.info("Executor at %s: build %s", self.executor_api_url, (self.api_client.executor_build() if self.api_client else None) or "unknown (image before 2026-09-07)")
            except Exception:                                  # noqa: BLE001
                pass
            return RemoteKernel(base_url=self.executor_api_url, df_id=self.df_id, session_id=None, force=True)
        import sys
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if os.path.join(here, 'delve') not in sys.path:
            sys.path.insert(0, os.path.join(here, 'delve'))
        from kernel import PersistentKernel
        return PersistentKernel(df=self.df)

    def _kernel_for(self, parent_run_id):
        """The kernel the run works in. Continuing from the tip the kernel already
        holds: reuse it. Anything else (a branch, a new thread, a dead kernel):
        a fresh kernel rehydrated from the parent's path."""
        if self._kernel is not None and parent_run_id is not None and parent_run_id == self._kernel_tip:
            try:
                _, err, _ = self._kernel.execute("pass")          # is the warm kernel still alive (the executor reaps idle sessions)?
                if not err:
                    return self._kernel
                logger.info("Warm kernel unusable (%s); rehydrating from the parent's path", err.strip()[:80])
            except Exception as exc:                           # noqa: BLE001
                logger.info("Warm kernel gone (%s); rehydrating from the parent's path", exc)
        self._drop_kernel()
        self._kernel = self._new_kernel()
        if parent_run_id is not None:
            cells = self.notebook.path_cells(parent_run_id)
            if cells:
                n, err = rehydrate(self._kernel, cells)
                if err:
                    self.output_manager.display_system_messages(
                        f"Restoring the earlier analysis stopped after {n} of {len(cells)} cells: {err}", chain_id=self.chain_id)
        self._kernel_tip = parent_run_id
        return self._kernel

    def _drop_kernel(self):
        if self._kernel is not None:
            try:
                self._kernel.cleanup()
            except Exception:                                  # noqa: BLE001
                pass
        self._kernel = None
        self._kernel_tip = None

    # ------------------------------------------------------------ the tools
    def _web_search(self, query):
        self._last_search_query = query
        result, links = self._search_orchestrator(self.prompts, self.log_and_call_manager, self.output_manager,
                                                  self.chain_id, [{"role": "user", "content": query}])
        text = str(result or "")
        sources = []
        for l in list(links or [])[:10]:
            if isinstance(l, dict):
                url, title = str(l.get("link") or l.get("url") or "").strip(), str(l.get("title") or "").strip()
            else:
                url, title = str(l).strip(), ""
            url = url.strip("'\"<>()[]{},;")
            if not url.startswith("http"):
                continue
            host = re.sub(r'^https?://(www\.)?', '', url).split('/')[0]
            sources.append({"url": url, "title": title or host, "host": host})
        self._last_search_sources = sources
        if sources:
            text += "\nSources:\n" + "\n".join(f"- {x['title']}: {x['url']}" for x in sources)
        return text

    def _recall(self, query):
        if not self.memory_path:
            return []
        from bambooai.knowledge_pack import memory_lookup
        text = memory_lookup(self.memory_path, [query])
        return [text] if text else []

    # ------------------------------------------------------------- the READ
    def _reader_seat(self):
        """The seat a READ's reader call runs on (docs/DOCUMENTS_DESIGN.md): 'Reader' when the config
        carries one - a cheaper model for selection and faithful quotation - else the analyst seat."""
        agents = {a.get('agent') for a in (getattr(self.models, "config", {}) or {}).get('agent_configs', [])}
        return 'Reader' if 'Reader' in agents else self._seat()

    def _read(self, arg):
        """One READ over the thread's documents: the Reader seat called once over the candidates, every passage
        verified verbatim. Runs on the platform; the kernel never calls a model. The passages are kept for the
        pane's row."""
        def call_reader(system, user):
            if self.kill_signal or self._stop_event.is_set():
                raise ExecutionInterrupted("stopped by the user")
            messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
            return self.models.llm_call(self.log_and_call_manager, messages, agent=self._reader_seat(), chain_id=self.chain_id)

        digest, passages = reading.read(self._documents_dir(), arg, call_reader)
        self._last_read_query = arg
        self._last_read_passages = passages
        return digest

    def _kernel_prelude(self):
        """The source that defines D1, D2, ... in the kernel: run uncommitted by the session at the start of a
        run and after a rollback, prefixed to the replay script here. Empty without documents or a kernel copy."""
        if self.thread_id is None or not getattr(self, '_documents_in_kernel', True):
            return ""
        try:
            return documents.kernel_api_source(self._documents_dir(), self._kernel_documents_root())
        except Exception as exc:                              # noqa: BLE001
            logger.warning("documents: the kernel objects could not be prepared: %s", exc)
            return ""

    def _unit_text(self, unit_id):
        """A document passage's text by id, for the report guard; None when the thread has no such unit."""
        m = re.match(r"^(D\d+)\.(\d+)$", unit_id or "")
        if not m or self.thread_id is None:
            return None
        try:
            units = documents.read_units(self._documents_dir(), m.group(1)).get("units", [])
        except (OSError, ValueError, KeyError):
            return None
        u = next((x for x in units if x.get("id") == unit_id), None)
        return reading.unit_text(u) if u else None

    # ---------------------------------------------------------- the replay
    def _run_replay(self, run, script):
        """Run the assembled script through the executor. Returns (stdout, error) to the
        session and keeps the figures, results and datasets for the tabs."""
        generated_datasets_path = os.path.join('datasets', self.user_id or '', 'generated')
        # the replay re-runs every committed cell: give it twice the time they took, within limits
        path_cells = self.notebook.path_cells(run.id)
        took = sum(float(c.elapsed or 0.0) for c in path_cells)
        timeout = int(min(1800, max(300, 2 * took + 120)))
        self._sync_documents("replay")              # a cited cell may have read a document file
        prelude = self._kernel_prelude()            # ... or used D1.table(2): the objects ride ahead of the cells
        if prelude:
            script = prelude + "\n\n" + script
        new_df, results, error, plot_images, generated = self.executor.execute(
            self.output_manager, self.kill_signal, script, self.df, self.df_id, generated_datasets_path,
            persist_df=False, timeout=timeout)
        if error:
            logger.warning("Replay of run %s failed (timeout %ds, cells took %.0fs): %s", run.id, timeout, took,
                           str(error).strip().splitlines()[-1][:300] if str(error).strip() else error)
        plot_jsons = []
        for i, plot_data in enumerate(plot_images or []):
            plot_jsons.append(json.dumps({'type': 'plot', 'data': plot_data['data'], 'format': plot_data['format'],
                                          'id': f'plot_{i + 1}', 'chain_id': self.chain_id}))
        self._replay[run.id] = {"results": results or "", "plots": plot_jsons, "datasets": generated or None}
        logger.info("Replay of run %s: %d chars of results, %d figure(s), error=%s", run.id, len(results or ""), len(plot_jsons), bool(error))
        return results or "", error or ""

    # -------------------------------------------------------- the data view
    def _data_description(self):
        """The DATA block: the dataframe, the auxiliary files, then the thread's documents (their maps and
        where their text is in the kernel - docs/DOCUMENTS_DESIGN.md); documents count even with no dataset."""
        text = self._dataset_description()
        block = self._documents_block()
        return text + ("\n\n" + block if block else "")

    # ------------------------------------------------------- the documents
    def _documents_dir(self, thread_id=None):
        """The thread's documents folder on this machine: storage/<user>/documents/<thread_id>/."""
        return os.path.join(os.getcwd(), 'storage', self.user_id or '', 'documents', str(thread_id if thread_id is not None else self.thread_id))

    def _kernel_documents_root(self):
        """Where the kernel sees them, relative to its working directory - the same in both compute modes."""
        return os.path.join('datasets', self.user_id or '', 'documents').replace(os.sep, '/')

    def _documents_block(self):
        if self.thread_id is None:
            return ""
        try:
            return documents.prompt_block(self._documents_dir(), self._kernel_documents_root(),
                                          in_kernel=getattr(self, '_documents_in_kernel', True))
        except Exception as exc:                              # noqa: BLE001
            logger.warning("documents: the prompt block could not be built: %s", exc)
            return ""

    def _sync_documents(self, why="chain start"):
        """The kernel's documents folder mirrors the thread's: a copy on this machine for local compute,
        the executor's file routes in api mode; by content, so a second call sends nothing. A thread without
        documents clears what an earlier thread left. Never fatal: the chain runs without the files."""
        if self.thread_id is None:
            return
        tdir = self._documents_dir()
        try:
            if self.execution_mode == 'api':
                if self.api_client is None:
                    logger.info("documents: no executor client yet, the kernel's copy is not synced (%s)", why)
                    self._documents_in_kernel = False
                    return
                result = self.api_client.sync_documents(self.user_id or 'default', tdir)
                if result is None:                            # an executor image from before documents: no route, no copy
                    if getattr(self, '_documents_in_kernel', True):
                        logger.warning("documents: the executor (build %s) has no documents route - the kernel has no copy of the "
                                       "thread's documents; READ still works. Rebuild the executor image (bambooai serve builds it).",
                                       self.api_client.executor_build() or "unknown")
                    self._documents_in_kernel = False
                    return
                sent, removed = result
            else:
                sent, removed = documents.sync_local(tdir, self._kernel_documents_root())
            self._documents_in_kernel = True
            if sent or removed:
                logger.info("documents: thread %s, %d file(s) sent to the kernel, %d removed (%s)", self.thread_id, sent, removed, why)
        except Exception as exc:                              # noqa: BLE001
            self._documents_in_kernel = False
            logger.warning("documents: the kernel's copy could not be synced (%s): %s", why, exc)

    def remove_document_from_kernel(self, doc_id):
        """A document the person removed from the thread: drop the kernel's copy now; the next sync is the backstop."""
        try:
            if self.execution_mode == 'api':
                if self.api_client is not None:
                    self.api_client.remove_document(self.user_id or 'default', doc_id)
            else:
                shutil.rmtree(os.path.join(self._kernel_documents_root(), doc_id), ignore_errors=True)
        except Exception as exc:                              # noqa: BLE001
            logger.warning("documents: %s could not be removed from the kernel: %s", doc_id, exc)

    def _dataset_description(self):
        if self.df is None and not self.df_id:
            return "(no dataset attached)"
        head = f"File: {self.df_name}\n" if getattr(self, "df_name", "") else ""
        try:
            if self.api_client is not None and self.df_id:
                summary = self.api_client.dataframe_summary_to_string(self.df_id) or ""
                cols = self.api_client.get_dataframe_columns(self.df_id) or {}
                text = head + f"`df`: {summary}\nColumns: {json.dumps(cols)[:6000]}"
            else:
                df = self.df
                lines = [f"`df`: {len(df):,} rows x {df.shape[1]} columns. Columns (name: dtype, non-null, example):"]
                for c in list(df.columns)[:80]:
                    s = df[c]
                    ex = s.dropna().iloc[0] if s.notna().any() else ""
                    lines.append(f"  {c}: {s.dtype}, {int(s.notna().sum()):,} non-null, e.g. {str(ex)[:40]}")
                text = head + "\n".join(lines)
        except Exception as exc:                              # noqa: BLE001
            text = f"`df` is attached (description unavailable: {exc})"
        if self.auxiliary_datasets:
            text += f"\nAuxiliary files available in the kernel's working directory: {self.auxiliary_datasets}"
        return text

    # ------------------------------------------------------------- the UI
    def _tab(self, kind, data):
        """Update a right-pane tab live ('plan' is the Investigation tab)."""
        q = getattr(self.output_manager, 'output_queue', None)
        if q is not None and data:
            q.put(json.dumps({'type': kind, 'data': data, 'chain_id': self.chain_id}))

    def _ideas_run(self, question, level, parent, parent_for_ui):
        """The seedling (2026-09-08): five next questions from one model call - no cells, no replay,
        no rewrite, no infographic - shown in the Explore tab, and recorded as a chain so the map shows the fork."""
        self._mode_label = "Ideas"
        if self.webui:
            self.output_manager.send_chain_id(self.thread_id, self.chain_id, self.df_id, parent_chain_id=parent_for_ui)
            self._pane('pane_run_start', mode="Ideas", of=1, dollars=0.1)
        session = Session(None, self.notebook, self._llm, store=self.store, emit=self._emit, recall=None, search=None,
                          data_description=self._data_description())
        run = session.ideas(int(level), parent=parent, run_id=str(self.chain_id), question=question or "")
        self._pane('pane_run_end', status=run.status, turns=1, of=1, cells=0, failed=0, cost=self._chain_cost(), seconds=0,
                   replay_status='', replay_line='', plots=0, files=[])
        self.output_manager.display_results(chain_id=self.chain_id, answer=run.report, explore=True)
        logger.info("Ideas run %s finished: level %s, status=%s, cost=$%.3f", run.id, level, run.status, self._chain_cost())
        return None

    def _notebook_view(self, run):
        """The Investigation tab: the run as a notebook (analyst/render.py)."""
        from analyst.render import notebook_html
        return notebook_html(run)

    def _pane(self, event_type, **payload):
        """One event for the left pane (stream-pane.js)."""
        q = getattr(self.output_manager, 'output_queue', None)
        if q is not None:
            payload.update({'type': event_type, 'chain_id': self.chain_id})
            q.put(json.dumps(payload))

    def _emit(self, ev):
        """The artifact stream: the Investigation tab live, and the left pane's cards."""
        run = self.notebook.runs.get(ev.get("run")) if self.notebook else None
        if run is None:
            return
        kind = ev.get("type")
        if kind == "turn_start":
            seat = self._review_seat() if ev.get("review") else (self._rewrite_seat() if ev.get("rewrite") else self._seat())
            try:
                model = self.models.get_model_name(seat)
                model = model[0] if isinstance(model, (tuple, list)) else model
            except Exception:                                  # noqa: BLE001
                model = ""
            self._pane('pane_turn_start', turn=ev.get("turn"), of=ev.get("of"), seat=seat, model=model, review=bool(ev.get("review")))
        elif kind == "turn_end":
            th = (ev.get("thinking") or "").strip()
            peek = th.split(". ")[0][:140] if th else ""
            self._pane('pane_turn_end', turn=ev.get("turn"), kind=ev.get("kind"), peek=peek, elapsed=ev.get("elapsed"),
                       cost=ev.get("cost"), thinking=th[:4000], note=ev.get("note") or "", code=ev.get("code") or "")
        elif kind == "heartbeat":
            self._pane('pane_heartbeat', turn=ev.get("turn"), of=ev.get("of"), spent=round(float(ev.get("spent") or 0), 3),
                       dollars=ev.get("dollars"), estimate=ev.get("estimate") or "", mode=self._mode_label)
        elif kind == "cell_start":
            self._pane('pane_cell_start', turn=ev.get("turn"))
        elif kind == "cell":
            ok = not ev.get('error')
            out = (ev.get('stdout') or '').strip()
            peek = next((ln.strip() for ln in out.splitlines() if ln.strip()), '') if ok else ''
            from analyst.tools import exception_line
            t = next((x for x in reversed(run.turns) if x.kind == kind), None)
            self._pane('pane_cell', cell_no=ev.get('cell_no'), ok=ok, peek=peek[:160], elapsed=(t.elapsed if t else None),
                       chars=len(ev.get('stdout') or ''), figs=len(ev.get('figures') or []),
                       error_line=exception_line(ev.get('error') or '')[:220] if not ok else '')
            self._tab('plan', self._notebook_view(run))
        elif kind == "lookup_start":
            # a READ or SEARCH is under way: the pane shows a pending row until the digest replaces it (2026-10-03,
            # the Reader took a minute on a real paper and the page showed nothing meanwhile)
            model = ''
            if ev.get("kind") == "read":
                try:
                    model = self.models.get_model_name(self._reader_seat())
                    model = model[0] if isinstance(model, (tuple, list)) else model
                except Exception:                              # noqa: BLE001
                    model = ''
            self._pane('pane_lookup_start', kind=ev.get("kind"), query=ev.get("query") or '', model=model or '')
        elif kind in ("show", "names", "recall", "search", "read"):
            text = ev.get('text') or ''
            query = ev.get('query') or (self._last_search_query if kind == "search" else (getattr(self, '_last_read_query', '') if kind == "read" else ''))
            sources = list(getattr(self, '_last_search_sources', []) or [])[:8] if kind == "search" else []
            passages = reading.parse_digest(text) if kind == "read" else []
            peek = (reading.digest_peek(text) if kind == "read" else next((ln.strip() for ln in text.splitlines() if ln.strip()), ''))[:160]
            self._pane('pane_lookup', kind=kind, query=query, peek=peek, sources=sources, passages=passages)
            self._tab('plan', self._notebook_view(run))
        elif kind == "replay_start":
            # the replay under way: a pending row in the pane, and the executor chip on Executing as for a cell
            self._pane('pane_lookup_start', kind='replay', query=f"{ev.get('cells') or 0} cells", model='')
            self._pane('pane_cell_start', turn='replay')
        elif kind == "replay_end":
            self._pane('pane_lookup', kind='replay', query='', peek=(ev.get("line") or ev.get("status") or "")[:160], sources=[], passages=[])
        elif kind == "error":
            self._pane('pane_lookup', kind='lost', query='', peek=(ev.get("text") or "malformed turn")[:160], sources=[])

    # ---------------------------------------------------------- the entry
    def pd_agent_converse(self, question=None, action=None, thread_id=None, chain_id=None,
                          image=None, user_code=None, replay=None,
                          auto_explore=False, max_investigations=None, synthesis=False, mode=None, ideas=None):
        self.kill_signal = False
        self._stop_event.clear()

        if action == 'reset':
            try:
                self.log_and_call_manager.consolidate_logs()
                self.log_and_call_manager.clear_run_logs()
            except Exception:                                  # noqa: BLE001
                logger.warning("log consolidation failed on reset", exc_info=True)
            self._drop_kernel()
            self.thread_id = None
            self.notebook = None
            return

        # thread and position
        self.thread_id = thread_id if thread_id is not None else utils.next_thread_id()
        self.log_and_call_manager.thread_id = self.thread_id
        if self.notebook is None or self.notebook.thread_id != str(self.thread_id):
            self.notebook = self.store.load(self.thread_id)
            self._drop_kernel()
        self._sync_documents()                       # the thread's documents into the kernel's folder
        parent = str(chain_id) if chain_id is not None and str(chain_id) in self.notebook.runs else None
        parent_for_ui = chain_id if parent is not None else None      # the browser's own value, same type
        self.chain_id = utils.next_chain_id()

        if question is None and self.webui:
            question = self.output_manager.get_user_input()
        if user_code:
            question = (question or "Run this code and report what it shows.") + \
                       "\n\nThe person supplied this code to run first, as your first cell:\n```python\n" + user_code + "\n```"
        if synthesis:
            question = ("Write the report for the analysis so far on this thread: the answer first, then how it was established, its limitations and next steps. "
                        "The earlier chains' reports are the record, each verified by its own replay: synthesise them, citing [run k]; "
                        "SHOW RUN k - or SHOW RUN 1 2 3 - re-opens them whole where the ledger's line is not enough. Do not re-derive what they established.")
        if not question:
            return None

        if ideas:
            return self._ideas_run(question, ideas, parent, parent_for_ui)

        # budget preset. The brain's menu sends mode = quick | deep | adaptive (2026-09-05);
        # without it the legacy flags decide (auto_explore -> adaptive, planning -> deep).
        if mode not in ("quick", "deep", "adaptive"):
            mode = "adaptive" if auto_explore else ("deep" if self.planning else "quick")
        if mode == "adaptive":
            # the Depth dial: each step is about eight analyst turns (2026-09-06: x4 gave an
            # "adaptive" run of eight turns); never fewer than 16, never above the tier's ceiling
            budget = Budget(turns=self.turns_adaptive, dollars=4.0, review_every=self.review_every)
            if max_investigations:
                budget.turns = max(16, min(self.turns_adaptive, int(max_investigations) * 8))
        elif mode == "deep":
            budget = Budget(turns=self.turns_deep, dollars=1.5)
        else:
            budget = Budget(turns=self.turns_quick, dollars=0.3)
        self._last_budget = budget

        logger.info("Analyst run: thread %s, new chain %s, parent %s (%s), preset %s (%d turns)", self.thread_id, self.chain_id,
                    parent, "warm kernel" if (self._kernel is not None and parent == self._kernel_tip) else "fresh kernel",
                    mode, budget.turns)
        self._mode_label = {"quick": "Quick", "deep": "Deep", "adaptive": "Adaptive"}.get(mode, mode)
        if self.webui:
            # the browser draws the map from this one record: the new chain and where it attached
            self.output_manager.send_chain_id(self.thread_id, self.chain_id, self.df_id, parent_chain_id=parent_for_ui)
            self._pane('pane_run_start', mode=self._mode_label, of=budget.turns, dollars=budget.dollars)
            # the Data tab, as before (the Query tab is retired: the question is the chain's own text)
            if self.df is not None or self.df_id:
                try:
                    self.output_manager.display_results(chain_id=self.chain_id, execution_mode=self.execution_mode,
                                                        df_id=self.df_id, df=self.df, api_client=self.api_client)
                except Exception:                              # noqa: BLE001
                    logger.warning("Data preview skipped", exc_info=True)

        kernel = self._kernel_for(parent)
        session = Session(kernel, self.notebook, self._llm, store=self.store, emit=self._emit,
                          recall=self._recall if self.memory_path else None, search=self._search,
                          read=self._read, unit_text=self._unit_text, kernel_prelude=self._kernel_prelude(),
                          documents=bool(self._kernel_prelude()),
                          data_description=self._data_description(), kernel_factory=self._new_kernel,
                          replay_runner=self._run_replay)
        try:
            run = session.run(question, parent=parent, budget=budget, run_id=str(self.chain_id))
        except ExecutionInterrupted:
            self.output_manager.display_system_messages("Stopped.", chain_id=self.chain_id)
            run = self.notebook.runs.get(str(self.chain_id))
            if run is not None:
                run.status = "stopped"
                self.store.save(self.notebook)
            return None
        except Exception as exc:                               # noqa: BLE001
            logger.exception("Analyst session failed")
            status = getattr(exc, "status_code", None)
            if status == 402:
                self.output_manager.display_error("The model provider account is out of credit (HTTP 402). Top up the OpenRouter balance and ask again.", chain_id=self.chain_id)
            else:
                self.output_manager.display_error(str(exc)[:600], chain_id=self.chain_id)
            run = self.notebook.runs.get(str(self.chain_id))
            if run is not None:
                run.status = "failed"
                self.store.save(self.notebook)
            return None
        finally:
            try:
                if self._chain_cost() > 0 or self.log_and_call_manager.token_summary.get(self.chain_id):
                    self.log_and_call_manager.charge_for_completed_query(self.chain_id)
            except Exception:                                  # noqa: BLE001
                pass
        self._kernel_tip = run.id

        # what the reader sees: the tabs the browser already has
        rep = self._replay.pop(run.id, {})
        files = [{'path': f, 'name': str(f).split('/')[-1]} for f in (rep.get('datasets') or [])]
        if files:
            self._pane('pane_datasets', files=files)
        replay_line = ''
        if run.report and '> Replay' in run.report:
            replay_line = run.report.rsplit('> ', 1)[-1].strip().splitlines()[0]
        self._pane('pane_run_end', status=run.status, turns=len([t for t in run.turns if t.kind not in ('rewrite', 'review')]),
                   cells_of=budget.turns, cells=len(run.cells()), failed=sum(1 for t in run.turns if t.kind == 'cell' and t.error),
                   cost=round(self._chain_cost(), 3),
                   seconds=round(sum(float((t.usage or {}).get('elapsed') or 0) + float(t.elapsed or 0) for t in run.turns), 1),
                   replay_status=run.replay_status or '', replay_line=replay_line, plots=len(rep.get('plots') or []), files=files)
        if run.status == "asked":
            asked = next((t.text for t in reversed(run.turns) if t.kind == "ask"), "")
            self.output_manager.display_results(chain_id=self.chain_id, answer=asked, plan=self._notebook_view(run))
        else:
            if self.synthesis_infographic and run.report and synthesis:      # the infographic is a synthesis's (2026-09-08): ordinary chains skip the call
                self._generate_synthesis_image(run.report)
            kwargs = dict(chain_id=self.chain_id, answer=run.report or "(no report)",
                          code=run.replay_script or None, plot_jsons=rep.get("plots") or None,
                          code_exec_results=rep.get("results") or None, generated_datasets=rep.get("datasets"),
                          plan=self._notebook_view(run))
            if self.webui:
                kwargs["simplified_answer"] = run.rewrite or None
            self.output_manager.display_results(**kwargs)
        try:
            self.log_and_call_manager.print_summary_to_terminal(self.output_manager)
        except Exception:                                      # noqa: BLE001
            pass
        try:
            _p = self.log_and_call_manager.run_log_file_path
            _n = len(json.load(open(_p))) if os.path.exists(_p) else 0
        except Exception:                                      # noqa: BLE001
            _n = -1
        logger.info("Analyst run %s finished: status=%s, cells=%d, replay=%s, cost=$%.3f, run log entries=%s",
                    run.id, run.status, len(run.cells()), run.replay_status or "-", self._chain_cost(), _n)
        self._stage_memory_source(run)
        return None

    # ------------------------------------------------------------- memory
    def _stage_memory_source(self, run):
        """Stage what a later keep-signal may distill: the report and the script."""
        if not self.memory_path or not run.report:
            return
        try:
            from bambooai.knowledge_pack import stage_distill_source
            stage_distill_source(self.memory_path, str(run.id), {
                "question": run.question, "technical": run.report, "code": run.replay_script or ""})
            self._staged_chain_ids = getattr(self, "_staged_chain_ids", set()) | {str(run.id)}
        except Exception:                                      # noqa: BLE001
            logger.warning("Memory: staging failed", exc_info=True)

    def distill_kept_chain(self, chain_id):
        """The write pass at the keep-signal: the person ranked or saved this
        run, so distill at most one candidate method card from its report."""
        if not self.memory_path:
            return None
        chain_id = str(chain_id)
        done = getattr(self, "_distilled_chains", None)
        if done is None:
            done = self._distilled_chains = set()
        if chain_id in done:
            return None
        try:
            from bambooai.knowledge_pack import (pop_distill_source, append_card, cards_from_distiller_output,
                                                 load_pack, reinforce)
            src = pop_distill_source(self.memory_path, chain_id)
            if src is None:
                return None
            pack, _ = load_pack(self.memory_path)
            index_lines = "\n".join(f"- {c['name']} - {(c.get('hooks') or {}).get('answers_question', '')}"
                                    for c in pack.get("cards", []) if not c.get("_decayed")) or "(empty)"
            agents = {a.get('agent') for a in (getattr(self.models, "config", {}) or {}).get('agent_configs', [])}
            agent = 'Knowledge Distiller' if 'Knowledge Distiller' in agents else self._seat()
            messages = [{"role": "system", "content": self.prompts.knowledge_distiller_system},
                        {"role": "user", "content": self.prompts.knowledge_distiller_user.format(
                            index_lines, "(none)", src.get("question", ""),
                            (src.get("technical") or "")[:8000], (src.get("code") or "")[:6000])}]
            draft = self.models.llm_call(self.log_and_call_manager, messages, agent=agent, chain_id=chain_id)
            done.add(chain_id)
            cards, reason = cards_from_distiller_output(draft or "", chain_id=chain_id, question=src.get("question", ""),
                                                        existing_cards=pack.get("cards", []))
            if not cards:
                logger.info("Memory: distiller declined - %s", reason)
                return None
            written = []
            for card in cards:
                ok, why = append_card(self.memory_path, card)
                if ok:
                    written.append(card['name'])
                else:
                    logger.info("Memory: card '%s' not written - %s", card['name'], why)
            if not written:
                return None
            reinforce(self.memory_path, chain_id, reason='birth-keep')
            self.output_manager.display_system_messages(
                "Memory: method distilled into new candidate card" + ("s " if len(written) > 1 else " ")
                + ", ".join(f"'{n}'" for n in written))
            return written[0]
        except Exception:                                      # noqa: BLE001
            logger.warning("Memory: distillation failed", exc_info=True)
            return None

    # --------------------------------------------------------- infographic
    def _generate_synthesis_image(self, report_text):
        """Extract the infographic YAML from the report and render it (unchanged seam)."""
        t0 = time.time()
        agents = {a.get('agent') for a in (getattr(self.models, "config", {}) or {}).get('agent_configs', [])}
        agent = 'Image Generator' if 'Image Generator' in agents else self._seat()
        # the extractor's YAML streams into a quiet card, not into the pane's prose
        self._pane('pane_turn_start', turn='infographic', of=None, seat=agent, model='', quiet=True)
        drawn = False
        try:
            messages = [{"role": "user", "content": self.prompts.synthesis_infographic_template.format(synthesis=report_text)}]
            text = self.llm_stream(self.prompts, self.log_and_call_manager, self.output_manager, messages,
                                   agent=agent, chain_id=self.chain_id, reasoning_models=self.reasoning_models)
            if isinstance(text, tuple):
                text = text[0]
            svg = synthesis_infographic.render_from_yaml_string(text or "")
            if svg:
                import base64 as b64
                self.output_manager.send_synthesis_image(b64.b64encode(svg.encode('utf-8')).decode('ascii'),
                                                         'image/svg+xml', chain_id=self.chain_id)
                drawn = True
        except Exception:                                      # noqa: BLE001
            logger.warning("Infographic skipped", exc_info=True)
        self._pane('pane_turn_end', turn='infographic', kind='infographic', peek='infographic drawn' if drawn else 'no infographic',
                   elapsed=round(time.time() - t0, 1), cost=None, thinking='', note='', code='')

    # -------------------------------------------------------------- lifecycle
    def stop(self):
        self.kill_signal = True
        self._stop_event.set()

    def cleanup(self):
        try:
            ids = getattr(self, "_staged_chain_ids", None)
            if ids and self.memory_path:
                from bambooai.knowledge_pack import discard_staged
                discard_staged(self.memory_path, ids)
        except Exception:                                      # noqa: BLE001
            pass
        self._drop_kernel()
        try:
            self.log_and_call_manager.consolidate_logs()
        except Exception:                                      # noqa: BLE001
            pass
