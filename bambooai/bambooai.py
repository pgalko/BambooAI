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
from analyst import context as context_mod
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
        self.load_params = None          # how the data loaded now was loaded (the integration routes set it; a routine's run repeats it)
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
        self.store = NotebookStore(self._user_storage())
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

    def _multimodal(self, seat):
        """Whether the seat's model takes images, by the config's model_properties (`multimodal`: "true"/"false", read
        nowhere until 2026-10-13); unknown counts as not."""
        try:
            model = self.models.get_model_name(seat)
            model = model[0] if isinstance(model, (tuple, list)) else model
            flag = (self.models.get_model_properties() or {}).get(model, {}).get("multimodal")
        except Exception:                                      # noqa: BLE001
            return False
        return str(flag).strip().lower() == "true"

    def _figure_for_analyst(self, image):
        """The plot the person asks about (the Plots tab's Ask AI, a PNG in base64): for the analyst when its model takes
        images; otherwise the question goes without it and the pane says so."""
        seat = self._seat()
        if self._multimodal(seat):
            return image
        try:
            model = self.models.get_model_name(seat)
            model = model[0] if isinstance(model, (tuple, list)) else model
        except Exception:                                      # noqa: BLE001
            model = "?"
        self.output_manager.display_system_messages(
            f"The analyst's model ({model}) does not take images, so the figure is not sent with the question; the analyst answers from the chain's record and data.", chain_id=self.chain_id)
        return None

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

    def _figures_seat(self):
        """The seat the figures request runs on (2026-10-11): 'Figures' when the config carries one - a one-shot code
        reply where long reasoning only costs (an effort-word model at xhigh spent its whole allowance thinking and
        sent nothing; the adapter has no budget to hold it) - else the analyst seat."""
        agents = {a.get('agent') for a in (getattr(self.models, "config", {}) or {}).get('agent_configs', [])}
        return 'Figures' if 'Figures' in agents else self._seat()

    def _promoter_seat(self):
        """The seat Save as routine's one model call runs on (2026-10-10): 'Promoter' when the config carries one -
        its own model, effort and token allowance, since the reply is a JSON object of edits that a seat tuned for
        long reasoning can cut short - else the analyst seat."""
        agents = {a.get('agent') for a in (getattr(self.models, "config", {}) or {}).get('agent_configs', [])}
        return 'Promoter' if 'Promoter' in agents else self._seat()

    def _llm(self, system: str, user: str, review: bool = False, rewrite: bool = False, figures: bool = False, seat: str = None, image: str = None, **hints):
        """The model call the session uses: the app's model layer (streaming,
        telemetry, retries), returning (text, {'cost': delta}). A self-review
        turn (review=True) runs on the Reviewer seat; its cost is accounted to
        that seat and counts against the run's budget like any other call. The
        rewrite and the figures request have seats of their own when the config
        carries them. `seat` names the seat outright (the routines' promoter).
        `image` (a PNG, base64) rides with the user message as an image part in
        the OpenAI form - the OpenAI-compatible adapters pass it through, the
        Anthropic and Gemini adapters convert it (2026-10-13: the plot's Ask AI
        had sent the picture since v1 and the analyst never received it)."""
        if self.kill_signal or self._stop_event.is_set():
            raise ExecutionInterrupted("stopped by the user")
        before = self._chain_cost()
        content = user if not image else [{"type": "text", "text": user}, {"type": "image_url", "image_url": {"url": "data:image/png;base64," + image}}]
        messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]
        text = self.llm_stream(self.prompts, self.log_and_call_manager, self.output_manager, messages,
                               agent=seat or (self._review_seat() if review else (self._rewrite_seat() if rewrite else (self._figures_seat() if figures else self._seat()))), chain_id=self.chain_id,
                               reasoning_models=self.reasoning_models)
        if isinstance(text, tuple):
            text = text[0]
        # whether the reply was cut at the seat's max_tokens (the model layer records it per request; 2026-10-06: a turn
        # spent its whole 16,000 tokens reasoning and the 887 characters that arrived had no action - the analyst was told
        # "no valid action", which is true but not what happened)
        from bambooai.models import prompt_cache
        meta = prompt_cache.last_meta()
        # a request the provider's classifier declined before any text (2026-10-08: the Claude 5.5 family's stop_reason
        # "refusal"; the adapter records the category so the session can say what happened rather than "no valid action")
        return text or "", {"cost": max(0.0, self._chain_cost() - before), "truncated": bool(meta.get("truncated")),
                            "declined": meta.get("declined") or ""}

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
            return RemoteKernel(base_url=self.executor_api_url, df_id=self.df_id, session_id=None, force=True,
                                generated_dir=self._generated_dir())
        import sys
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if os.path.join(here, 'delve') not in sys.path:
            sys.path.insert(0, os.path.join(here, 'delve'))
        from kernel import PersistentKernel
        return PersistentKernel(df=self.df, generated_dir=self._generated_dir())

    def _generated_dir(self):
        """The user's generated-datasets folder - the one /cache/inspect lists under Generated and the download route
        serves (2026-10-06): where DS.save puts a dataset the analyst makes for the person, in the kernel during the
        analysis and in the replay. The same expression the replay has always passed to the executor."""
        return os.path.join('datasets', self.user_id or '', 'generated')

    def _kernel_for(self, parent_run_id, data_record=None):
        """The kernel the run works in. Continuing from the tip the kernel already
        holds, with the frame it holds still the one loaded: reuse it. Anything
        else (a branch, a new thread, a dead kernel, the frame replaced since): a
        fresh kernel rehydrated from the cells of the parent's path that ran on
        the same data as `data_record`, the record of the data loaded now - the
        same frame, or the same data loaded again under a new id (2026-10-12: a
        routine's run had loaded another window, and the follow-up went on in the
        warm kernel with `df` and the names of the earlier window, while the DATA
        block described the new one; a favourite continued in a new session with
        its file uploaded again is the same data and is rehydrated as before)."""
        if self._kernel is not None and parent_run_id is not None and parent_run_id == self._kernel_tip:
            if not self._same_frame(parent_run_id):
                logger.info("The frame loaded is not the one the chain in the kernel ran on; a fresh kernel for the follow-up")
            else:
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
            cells = self.notebook.computed_cells(parent_run_id, data=data_record if data_record is not None else {"df_id": self.df_id})
            if cells:
                n, err = rehydrate(self._kernel, cells)
                if err:
                    self.output_manager.display_system_messages(
                        f"Restoring the earlier analysis stopped after {n} of {len(cells)} cells: {err}", chain_id=self.chain_id)
        self._kernel_tip = parent_run_id
        return self._kernel

    def _same_frame(self, run_id):
        """Whether the frame loaded now is the frame a run ran on (by its id - the kernel's key: a kernel holds one
        frame object); a run without a record counts as on the same frame."""
        run = self.notebook.runs.get(str(run_id)) if self.notebook else None
        key = self.notebook.data_key(run) if run is not None else ""
        return (not key) or key == str(self.df_id or "")

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

    def _coder_seat(self):
        """The seat the coding pass runs on (docs/CONTEXT_DESIGN.md §6): 'Coder' when the config carries one, else
        the Reader's seat."""
        agents = {a.get('agent') for a in (getattr(self.models, "config", {}) or {}).get('agent_configs', [])}
        return 'Coder' if 'Coder' in agents else self._reader_seat()

    def code_context(self, notes_path, progress=None, billing_chain_id=None, key_mark=None):
        """The coding pass over a loaded context file (bambooai/context_host.py), its calls logged under the billing
        chain as Save as routine's are; the thread for the usage rows is the current one or one minted for the load.
        `key_mark` names the subject's store of coded passages (the load's key mark when not given)."""
        from bambooai import context_host
        if not self.log_and_call_manager.thread_id:
            self.log_and_call_manager.thread_id = str(self.thread_id or utils.next_thread_id())
        mark = key_mark or (getattr(self, 'load_params', None) or {}).get('key') or ''
        return context_host.code_context(self, notes_path, progress=progress, chain_id=billing_chain_id or self.chain_id, key_mark=mark or None)

    def _put_aux_file(self, path, text):
        """Write an auxiliary file's text where the load keeps it: to the executor in api mode, here otherwise."""
        try:
            if self.execution_mode == 'api' and self.api_client is not None:
                return bool(self.api_client.upload_aux_file(path, text))
            d = os.path.dirname(path)
            if d:
                os.makedirs(d, exist_ok=True)
            with open(path, 'w', encoding='utf-8', newline='') as f:
                f.write(text)
            return True
        except Exception as exc:                              # noqa: BLE001
            logger.warning("context: %s could not be written (%s)", path, exc)
            return False

    def _read(self, arg):
        """One READ over the thread's documents: the Reader seat called once over the candidates, every passage
        verified verbatim. Runs on the platform; the kernel never calls a model. The passages are kept for the
        pane's row."""
        def call_reader(system, user):
            if self.kill_signal or self._stop_event.is_set():
                raise ExecutionInterrupted("stopped by the user")
            messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
            return self.models.llm_call(self.log_and_call_manager, messages, agent=self._reader_seat(), chain_id=self.chain_id)

        if context_mod.parse_context_scope(arg) is not None:      # READ CTX ... / READ C.120-160 ...: the words beside the data
            notes, _codes = self._context_frames()
            digest, passages = reading.read_context(notes, arg, call_reader)
        else:
            digest, passages = reading.read(self._documents_dir(), arg, call_reader)
        self._last_read_query = arg
        self._last_read_passages = passages
        return digest

    def _kernel_prelude(self):
        """The source that defines D1, D2, ... and CTX in the kernel: run uncommitted by the session at the start of a
        run and after a rollback, prefixed to the replay script here. Empty without documents (or a kernel copy of
        them) and without a context file."""
        return "\n\n".join(p for p in (self._documents_prelude(), self._context_prelude()) if p)

    def _documents_prelude(self):
        if self.thread_id is None or not getattr(self, '_documents_in_kernel', True):
            return ""
        try:
            return documents.kernel_api_source(self._documents_dir(), self._kernel_documents_root())
        except Exception as exc:                              # noqa: BLE001
            logger.warning("documents: the kernel objects could not be prepared: %s", exc)
            return ""

    def _context_prelude(self):
        """The source that defines CTX (docs/CONTEXT_DESIGN.md §5) over the loaded context file, '' without one."""
        notes_path, codes_path = self._context_paths()
        return context_mod.kernel_api_source(notes_path, codes_path) if notes_path else ""

    @property
    def auxiliary_datasets(self):
        return self._auxiliary_datasets

    @auxiliary_datasets.setter
    def auxiliary_datasets(self, paths):
        """A load assigns the list (the app, the integrations' routes): the context frames read for the previous list
        are dropped, so a file written again under the same name (the coding pass re-uploads it) is read again."""
        self._auxiliary_datasets = paths if paths is not None else []
        self._context_cache = None

    def _context_frames(self):
        """The loaded context and codes files as frames, read once per load (the paths are the key): (notes, codes),
        None for a file that is not there."""
        notes_path, codes_path = self._context_paths()
        key = (notes_path, codes_path)
        cached = getattr(self, '_context_cache', None)
        if cached and cached[0] == key:
            return cached[1], cached[2]
        notes = self._context_file(notes_path) if notes_path else None
        codes = self._context_file(codes_path) if codes_path else None
        self._context_cache = (key, notes, codes)
        return notes, codes

    def _unit_text(self, unit_id):
        """A document passage's text by id, for the report guard; a context passage's (the English rendering when there
        is one) for [C.n]; None when there is no such unit."""
        if re.match(r"^C\.\d+$", unit_id or ""):
            notes, _codes = self._context_frames()
            if notes is None or not len(notes):
                return None
            hit = notes[notes["id"].astype(str) == unit_id]
            return context_mod.passage_text(hit.iloc[0].to_dict()) if len(hit) else None
        u = self._document_unit(unit_id)
        return reading.unit_text(u) if u else None

    def _document_unit(self, unit_id):
        """A document's unit by id (D1.17), or None."""
        m = re.match(r"^(D\d+)\.(\d+)$", unit_id or "")
        if not m or self.thread_id is None:
            return None
        try:
            units = documents.read_units(self._documents_dir(), m.group(1)).get("units", [])
        except (OSError, ValueError, KeyError):
            return None
        return next((x for x in units if x.get("id") == unit_id), None)

    def _cited_passages(self, text):
        """The passages a report cites - [C.417], [D1.17] or the bare ids - resolved for the page's chips
        (docs/CONTEXT_DESIGN.md S2): [{id, where, quote, original?}], the quote clipped. A READ's passages already on
        the page keep their verified quote; this gives the chips of passages a cell read their hover (2026-10-14: the
        first live run named every passage from cells, and no READ ran)."""
        from analyst import report as rep

        def clip(s, n=300):
            s = re.sub(r"\s+", " ", str(s or "")).strip()
            return s if len(s) <= n else s[:n].rstrip() + "\u2026"
        cited = rep.cited_units(text)
        ids = cited + [u for u in rep.named_units(text) if u not in cited]
        out, notes = [], None
        for uid in ids:
            if uid.startswith("C."):
                if notes is None:
                    notes = self._context_frames()[0]
                if notes is None or not len(notes):
                    continue
                hit = notes[notes["id"].astype(str) == uid]
                if not len(hit):
                    continue
                r = hit.iloc[0].to_dict()
                p = {"id": uid, "where": context_mod.where_of(r), "quote": clip(context_mod.passage_text(r))}
                if str(r.get("text_en") or "").strip() and str(r.get("text") or "") != str(r.get("text_en") or ""):
                    p["original"] = clip(r.get("text"))
            else:
                u = self._document_unit(uid)
                if not u:
                    continue
                p = {"id": uid, "where": reading.where(u), "quote": clip(reading.unit_text(u))}
            out.append(p)
        return out

    # ---------------------------------------------------------- the replay
    def run_script(self, script, timeout, what="Replay", generated_dir=None):
        """One script through the executor against the loaded data, as the replay runs (2026-10-10: a routine's run
        zero takes the same path; a routine's run passes its own folder, where its files and datasets go). Returns
        (stdout, error, figures as the tabs' JSON strings, generated datasets)."""
        generated_datasets_path = generated_dir or self._generated_dir()
        self._sync_documents("replay")              # a cited cell may have read a document file
        prelude = self._kernel_prelude()            # ... or used D1.table(2): the objects ride ahead of the cells
        offset = 0
        if prelude:
            offset = prelude.count("\n") + 2
            script = prelude + "\n\n" + script
        new_df, results, error, plot_images, generated = self.executor.execute(
            self.output_manager, self.kill_signal, script, self.df, self.df_id, generated_datasets_path,
            persist_df=False, timeout=timeout)
        if error and offset:
            # the traceback's line numbers back in the caller's text, which the prelude pushed down (a routine's run names
            # the failed cell by them, 2026-10-10)
            import re as _re
            error = _re.sub(r'(File "<string>", line )(\d+)', lambda m: m.group(1) + str(max(1, int(m.group(2)) - offset)), str(error))
            # ... and the executor's own head line, which names the line first and is what failed_cell reads (2026-10-11: with
            # documents in the thread a failure in cell 2 was named at cell 3)
            error = _re.sub(r'^(Error on line )(\d+)(:)', lambda m: m.group(1) + str(max(1, int(m.group(2)) - offset)) + m.group(3), error, flags=_re.M)
        if error:
            logger.warning("%s failed (timeout %ds): %s", what, timeout,
                           str(error).strip().splitlines()[-1][:300] if str(error).strip() else error)
            # the script sets the kernel's display options and resets them on its last lines; stopped before those, the
            # executor's process would go on formatting its data views the kernel's way (2026-10-08)
            try:
                from analyst.replay import RESET_OPTIONS
                self.executor.execute(self.output_manager, self.kill_signal, "import pandas as pd\n" + RESET_OPTIONS,
                                      None, None, None, persist_df=False, timeout=60)
            except Exception as exc:                               # noqa: BLE001
                logger.warning("%s: the display options could not be reset after the failure: %s", what, exc)
        plot_jsons = []
        for i, plot_data in enumerate(plot_images or []):
            plot_jsons.append(json.dumps({'type': 'plot', 'data': plot_data['data'], 'format': plot_data['format'],
                                          'id': f'plot_{i + 1}', 'chain_id': self.chain_id}))
        return results or "", error or "", plot_jsons, generated or None

    def _run_replay(self, run, script):
        """Run the assembled script through the executor. Returns (stdout, error) to the
        session and keeps the figures, results and datasets for the tabs."""
        # the replay re-runs every committed cell: give it twice the time they took, within limits
        path_cells = self.notebook.computed_cells(run.id)       # the cells the script re-runs (2026-10-12)
        took = sum(float(c.elapsed or 0.0) for c in path_cells)
        timeout = int(min(1800, max(300, 2 * took + 120)))
        results, error, plot_jsons, generated = self.run_script(script, timeout, what=f"Replay of run {run.id} (cells took {took:.0f}s)")
        self._replay[run.id] = {"results": results or "", "plots": plot_jsons, "datasets": generated}
        logger.info("Replay of run %s: %d chars of results, %d figure(s), error=%s", run.id, len(results or ""), len(plot_jsons), bool(error))
        return results or "", error or ""

    # ------------------------------------------------------------ the data record
    def _data_record(self, light=False):
        """What a run ran on (2026-10-10, routines): the frame's identity and name, its source as the executor's cache
        knows it, its columns with their types, its size, the loader's details, the auxiliary files. Kept on the run,
        so a routine made from it later knows its data; `light` gives the identity alone."""
        rec = {"df_id": self.df_id, "name": getattr(self, "df_name", "") or "", "source": "", "columns": [], "rows": None,
               "date_range": None, "aux": [p for p in (self.auxiliary_datasets or []) if p], "extra": {}}
        lp = getattr(self, "load_params", None) or {}
        if lp and (not lp.get("df_id") or str(lp.get("df_id")) == str(self.df_id)):
            rec["load"] = {k: v for k, v in lp.items() if k != "df_id"}       # how it was loaded: a routine's run repeats this
        if self.df is None and not self.df_id:
            rec["source"] = "none"
            return rec
        if light:
            return rec
        try:
            if self.api_client is not None and self.df_id:
                pv = self.api_client.cache_preview(self.df_id) or {}
                meta = pv.get("metadata") or {}
                dtypes = pv.get("dtypes") or {}
                rec.update(source=str(meta.get("source") or ("file" if rec["name"] else "")),
                           columns=[{"name": str(c), "dtype": str(dtypes.get(c, ""))} for c in (pv.get("columns") or [])][:400],
                           rows=(pv.get("shape") or [None])[0], date_range=meta.get("date_range"),
                           name=meta.get("original_filename") or rec["name"],
                           extra={k: meta.get(k) for k in ("metrics", "activities_count", "race_id", "race_title", "race_date", "athletes_count") if meta.get(k) is not None})
                if (rec.get("load") or {}).get("source") == "cache":
                    rec["load"] = self._load_of_cached(meta, rec)
            elif self.df is not None:
                rec.update(source="file" if rec["name"] else "frame", rows=int(len(self.df)),
                           columns=[{"name": str(c), "dtype": str(t)} for c, t in self.df.dtypes.items()][:400])
        except Exception as exc:                                   # noqa: BLE001
            logger.warning("The run's data record is partial: %s", exc)
        return rec

    @staticmethod
    def _load_of_cached(meta, rec):
        """The load on record for a frame taken from the Dataset cache - the Data tab's cache, or a routine's run reusing
        a cached window: the cached frame's own load, from the executor's metadata - its source, window, metrics and
        the auxiliary kinds loaded with it - marked cached, never "cache" (2026-10-12: a chain on such a frame made a
        routine whose plan read "file", and its run dialog offered an upload in place of the window)."""
        from analyst.routines import aux_kind
        src = str(meta.get("source") or "").lower()
        out = {"source": src if src in ("intervals", "endura", "sweatstack") else "file", "cached": True}
        m = re.match(r"^\s*(\d{4}-\d{2}-\d{2})\s*(?:to|->|-)\s*(\d{4}-\d{2}-\d{2})\s*$", str(meta.get("date_range") or ""))
        kinds = [aux_kind(p) for p in rec.get("aux") or []]
        if src == "intervals":
            out.update(metrics=list(meta.get("metrics") or []), aux_kinds=[k for k in kinds if k in ("summary", "wellness", "intervals", "context", "codes")])
            if m:
                out.update(start_date=m.group(1), end_date=m.group(2))
            if meta.get("key_mark"):
                out["key"] = meta["key_mark"]
        elif src == "endura":
            out.update(race_id=meta.get("race_id"), race_title=meta.get("race_title") or "", aux_kinds=[k for k in kinds if k in ("profile", "turns", "climbs", "waymarkers")])
        elif src == "sweatstack":
            out.update(sports=list(meta.get("sports") or []), metrics=list(meta.get("metrics") or []))
            if m:
                out.update(start_date=m.group(1), end_date=m.group(2))
        else:
            out["name"] = rec.get("name") or ""
        return out

    # ------------------------------------------------------------ routines (docs/ROUTINES_DESIGN.md)
    def routine_store(self):
        from analyst.routines import RoutineStore
        return RoutineStore(self._user_storage())

    def _user_storage(self):
        """storage/<user> - the notebooks, favourites, routines and the context codebook live under it."""
        return os.path.join(os.getcwd(), 'storage', self.user_id) if self.user_id else os.path.join(os.getcwd(), 'storage')

    def _emit_routine(self, ev):
        """The pane's rows for a routine being made: a quiet card for the promoter's call, a look-up row for run zero."""
        kind = ev.get("type")
        if kind == "turn_start":
            self._pane('pane_turn_start', turn='routine', of=None, seat=ev.get("seat") or self._seat(), model=ev.get("model") or '', quiet=True)
        elif kind == "turn_end":
            self._pane('pane_turn_end', turn='routine', kind='routine', peek=ev.get("peek") or '', elapsed=ev.get("elapsed"), cost=ev.get("cost"), thinking='', note='', code='')
        elif kind == "lookup_start":
            self._pane('pane_lookup_start', kind=ev.get("kind") or 'routine', query=ev.get("query") or '', model='')
            if (ev.get("kind") or 'routine') in ('routine', 'run'):
                self._pane('pane_cell_start', turn='routine')           # the executor chip on Executing while the method runs
        elif kind == "lookup":
            # a CHECK row's sentences run long (step 4, 2026-10-11): the row shows what fits and carries the whole line on hover
            self._pane('pane_lookup', kind=ev.get("kind") or 'routine', query=ev.get("query") or '', peek=(ev.get("peek") or '')[:600], sources=[], passages=[])

    def propose_routine(self, thread_id, chain_id, routine_id=None, billing_chain_id=None):
        """Save as routine, step one: the promoter reads the chain and proposes its inputs. The call is accounted to
        `billing_chain_id` (a chain of its own, so the hosted edition charges it as a query). Returns the proposal,
        kept on the instance until create_routine takes it; raises RoutineRefused with a readable reason."""
        from bambooai import routines_host
        nb = self.notebook if (self.notebook is not None and self.notebook.thread_id == str(thread_id)) else self.store.load(thread_id)
        routine = self.routine_store().load(routine_id) if routine_id else None
        if routine_id and routine is None:
            raise routines_host.RoutineRefused("the routine this version was meant for no longer exists")
        seat = self._promoter_seat()
        try:
            model = self.models.get_model_name(seat)
            model = model[0] if isinstance(model, (tuple, list)) else model
        except Exception:                                          # noqa: BLE001
            model = ''
        if not self.log_and_call_manager.thread_id:
            self.log_and_call_manager.thread_id = str(thread_id)        # the usage rows need a thread (a fresh instance has none yet)
        keep = self.chain_id
        self.chain_id = billing_chain_id or self.chain_id
        try:
            proposal = routines_host.propose(nb, str(chain_id), lambda s, u: self._llm(s, u, seat=seat), current_data=self._data_record(),
                                             emit=self._emit_routine, routine=routine, seat=seat, model=model,
                                             runner=lambda s, t: self.run_script(s, t, what="Shape"))
        finally:
            self.chain_id = keep
        pending = getattr(self, "_proposals", None)
        if pending is None:
            pending = self._proposals = {}
        pending[proposal["proposal_id"]] = proposal
        for old in list(pending)[:-6]:                              # the last few only
            pending.pop(old, None)
        logger.info("Routine proposed for chain %s: %d input(s), %d result line(s), data %s, $%.3f", chain_id, len(proposal["inputs"]),
                    len(proposal["results"]), proposal["data_state"], proposal["cost"])
        return proposal

    def precheck_routine(self, routine_id, values=None, aux=None, load=None):
        """Before a run: is data loaded, does it fit the routine's columns, are the chosen values in it (F2)."""
        from bambooai import routines_host
        routine = self.routine_store().load(routine_id)
        if routine is None:
            raise routines_host.RoutineRefused("no such routine")
        data = self._data_record()
        if aux is not None:
            data["aux"] = [str(p) for p in aux if p]
        if load:
            data["load"] = {**(data.get("load") or {}), **self._load_as_said(load)}   # what the loader route noted (the key's mark) under what the page says
        out = routines_host.precheck(routine, data, lambda script, timeout: self.run_script(script, timeout, what="Precheck"), values)
        out["plan"] = routines_host.load_plan(routine)                 # how the original load asked for its data: the dialog loads the same way
        return out

    @staticmethod
    def _load_as_said(load):
        """The load as the page says it did it (2026-10-11: a cached load goes through the cache routes, whose record would
        say 'cache'; the page passes the window, the kinds and that it came from the cache): plain values only."""
        out = {}
        for k, v in (load or {}).items():
            if k == "df_id" or not isinstance(k, str):
                continue
            if isinstance(v, (str, int, float, bool)) or v is None:
                out[k] = v
            elif isinstance(v, (list, tuple)):
                out[k] = [str(x) for x in v]
        return out

    def run_routine(self, routine_id, values=None, compare_with="previous", aux=None, load=None):
        """One run of the routine on the data loaded now (F2): the checks, the script with its INPUTS block through the
        executor, the lines read by position, the comparison with the run before, the record stored; then the tabs as an
        analysis has them (Data, Results, Plots) and the closing card for the pane."""
        from bambooai import routines_host
        routine = self.routine_store().load(routine_id)
        if routine is None:
            raise routines_host.RoutineRefused("no such routine")
        number = len(routine.get("runs", [])) + 1
        run_dir = os.path.join('datasets', self.user_id or '', 'routines', str(routine_id), routines_host.run_tag(routine.get("current_version") or 1, number))
        data = self._data_record()
        if aux is not None:                                       # the files the dialog's load just produced, as the page saw them - none when it produced none
            data["aux"] = [str(p) for p in aux if p]
        if load:                                                  # the load as the page did it (a cached one would otherwise read 'cache')
            data["load"] = {**(data.get("load") or {}), **self._load_as_said(load)}   # over what the loader route noted (the key's mark)
        logger.info("Routine %s run %d: data %s (%s rows, %d columns, %d auxiliary file(s): %s)", routine_id, number, data.get("source"), data.get("rows"),
                    len(data.get("columns") or []), len(data.get("aux") or []), ", ".join(os.path.basename(str(p)) for p in (data.get("aux") or [])) or "-")
        out = routines_host.run(routine, values, data, lambda script, timeout, d=None: self.run_script(script, timeout, what=f"Routine {routine_id}", generated_dir=d),
                                self.routine_store(), emit=self._emit_routine, compare_with=compare_with, run_dir=run_dir)
        try:
            self.output_manager.display_results(chain_id=None, execution_mode=self.execution_mode, df_id=self.df_id, df=self.df, api_client=self.api_client,
                                                code_exec_results=out["stdout"] or None, plot_jsons=out["figures"] or None)
        except Exception:                                          # noqa: BLE001
            logger.warning("The run's tabs could not be sent", exc_info=True)
        r, c = out["run"], out["run"]["comparison"]
        self._pane('pane_routine_end', number=r["number"], name=routine.get("name", ""), version=r["version"], status=r["status"], line=r["line"],
                   results=len(r["results"]), compared=c["compared"], moved=c["moved"], changed=c["changed"], missing=c["missing"], figures=r["figures"],
                   elapsed=r["elapsed"], against=r["against"], comparison_line=c["line"])
        logger.info("Routine %s run %d (v%d): %s; %s", routine_id, r["number"], r["version"], r["line"], c["line"])
        return {k: out[k] for k in ("run", "summary", "routine", "numbers", "name")}

    def create_routine(self, proposal_id, choices, routine_id=None):
        """Save as routine, step two: the person's choices, run zero on the chain's data through the executor, the
        routine stored. Raises RoutineRefused when run zero does not reproduce the chain's lines."""
        from bambooai import routines_host
        pending = getattr(self, "_proposals", None) or {}
        proposal = pending.get(proposal_id)
        if proposal is None:
            raise routines_host.RoutineRefused("this proposal has expired - open Save as routine again")
        nb = self.notebook if (self.notebook is not None and self.notebook.thread_id == str(proposal["thread_id"])) else self.store.load(proposal["thread_id"])
        # the data may have changed since the proposal: the chain's data still loaded (the same frame, or the same data
        # under a new id - notebook.same_data), or not
        from analyst.notebook import same_data
        now = self._data_record()
        now_loaded = now.get("df_id")
        if proposal.get("data_state") == "same" and not same_data(now, proposal.get("data") or {}):
            proposal["data_state"] = "gone"
        elif proposal.get("data_state") == "assumed":
            proposal["data"] = self._data_record()                  # the chain predates the record: the frame loaded now stands for its data
            if not now_loaded:
                proposal["data_state"] = "gone"
        # the version choice is the request's (2026-10-12): None makes a new routine even when the proposal was drawn for a
        # next version of one - the dialog's "A new routine" means that
        made = routines_host.create(nb, proposal, choices or {}, lambda script, timeout: self.run_script(script, timeout, what="Run zero"),
                                    self.routine_store(), emit=self._emit_routine, routine_id=routine_id)
        pending.pop(proposal_id, None)
        logger.info("Routine %s v%d made from chain %s: %s", made["routine"]["id"], made["version"], proposal["chain_id"], made["run_zero"]["line"])
        return made

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
        """The dataset and the auxiliary files, as the analyst reads them in DATA. With no primary dataset the auxiliary
        files ARE the data, and the block says so (2026-10-07: a run with two auxiliary files and no primary read
        "(no dataset attached)" and nothing else - the auxiliary line came after an early return - and the analyst
        reported having no data; the original BambooAI always described the auxiliary files, with their first rows)."""
        aux = self._auxiliary_block()
        if self.df is None and not self.df_id:
            if not aux:
                return ("(no dataset attached: `df` is not defined and DS has nothing to load; the question stands on its own, "
                        "or on the documents below if any are attached)")
            return ("No primary dataset is attached: `df` is not defined and DS has nothing to load. The data are the\n"
                    "auxiliary files below; read one into a frame yourself, e.g. df = pd.read_csv(path).\n\n" + aux)
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
        return text + ("\n\n" + aux if aux else "")

    AUX_HEAD_CHARS = 3000

    def _auxiliary_block(self):
        """The auxiliary files as the analyst reads them: each one's path as the kernel sees it (relative to its working
        directory, the same path in both compute modes) and its first rows, from the executor in api mode or read here
        otherwise - the description the original BambooAI gave; a very wide head is cut with a note."""
        paths = [p for p in (self.auxiliary_datasets or []) if p]
        if not paths:
            return ""
        try:
            described = utils.aux_datasets_to_string(paths, num_rows=5, execution_mode=self.execution_mode,
                                                     executor_client=self.api_client if self.execution_mode == 'api' else None) or ""
        except Exception as exc:                              # noqa: BLE001
            logger.warning("auxiliary files: description failed (%s) - the paths alone go into DATA", exc)
            described = ""
        parts = [p for p in described.split("\n\n") if p.strip()] if described else []
        if len(parts) != len(paths):                          # the describer could not pair them: paths alone
            parts = [f"{i}.\nPath: {p}" for i, p in enumerate(paths, 1)]
        shown = []
        from analyst.routines import aux_kind
        notes_path, codes_path = self._context_paths()
        notes_df, codes_df = self._context_frames() if notes_path else (None, None)
        frames = {}
        for i, (path, part) in enumerate(zip(paths, parts), 1):
            kind = aux_kind(path)
            if kind in ("context", "codes"):               # the rows are passages: the columns and the count, the map below says the rest
                frames[path] = notes_df if path == notes_path else codes_df
                if frames[path] is not None:
                    part = f"{i}.\n" + context_mod.aux_head_for_text_file(path, list(frames[path].columns), len(frames[path]))
            if len(part) > self.AUX_HEAD_CHARS:
                part = part[:self.AUX_HEAD_CHARS].rstrip() + "\n... [the head is cut here; read the file for the rest]"
            shown.append(part)
        block = ("AUXILIARY FILES (read them with pandas from these paths, which are relative to the kernel's working directory):\n"
                 + "\n\n".join(shown))
        cmap = self._context_map(frames)
        return block + ("\n\n" + cmap if cmap else "")

    def _context_paths(self):
        """The loaded context file and codes file, by their names (docs/CONTEXT_DESIGN.md §3): (notes path, codes path)."""
        from analyst.routines import aux_kind
        notes = codes = ""
        for p in self.auxiliary_datasets or []:
            k = aux_kind(p)
            if k == "context":
                notes = p
            elif k == "codes":
                codes = p
        return notes, codes

    def _context_file(self, path):
        """A context or codes file as a frame: from the executor in api mode (the file lives there), read here otherwise;
        None when it cannot be read."""
        from analyst.routines import aux_kind
        try:
            if self.execution_mode == 'api' and self.api_client is not None:
                text = self.api_client.read_aux_dataset(path)
                if text is None:
                    return None
            else:
                if not os.path.exists(path):
                    return None
                with open(path, encoding='utf-8', errors='replace') as f:
                    text = f.read()
            return context_mod.read_codes(text) if aux_kind(path) == "codes" else context_mod.read_context(text)
        except Exception as exc:                              # noqa: BLE001
            logger.warning("context: %s could not be read (%s)", path, exc)
            return None

    def _context_map(self, frames=None):
        """The map of the context for DATA (§3.4), '' without a context file. `frames` - files already read this call."""
        frames = frames or {}
        notes_path, codes_path = self._context_paths()
        if not notes_path:
            return ""
        notes = frames.get(notes_path) if notes_path in frames else self._context_file(notes_path)
        if notes is None:
            return ""
        codes = (frames.get(codes_path) if codes_path in frames else self._context_file(codes_path)) if codes_path else None
        size = 0
        if codes is not None:                                  # "23 of 36 codes used": the user's codebook, seeded by the pass that wrote the codes file
            try:
                from analyst import codebook as cb
                size = len(cb.active_codes(cb.load(self._user_storage())))
            except Exception:                                  # noqa: BLE001
                size = 0
        text = context_mod.context_map(notes, codes, notes_path=notes_path, codes_path=codes_path, codebook_size=size)
        if (getattr(self, '_context_coding', None) or {}).get('status') == 'running':      # the pass behind the load has not ended
            text += "\n  the coding pass is still running behind the load: the codes and the English renderings arrive when it ends; the words are reachable now as written."
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
            seat = self._review_seat() if ev.get("review") else (self._rewrite_seat() if ev.get("rewrite") else (self._figures_seat() if ev.get("figures") else self._seat()))
            try:
                model = self.models.get_model_name(seat)
                model = model[0] if isinstance(model, (tuple, list)) else model
            except Exception:                                  # noqa: BLE001
                model = ""
            # a quiet card shows nothing while its reply streams (the figures step's code, 2026-10-11); the attempt names a correction
            self._pane('pane_turn_start', turn=ev.get("turn"), of=ev.get("of"), seat=seat, model=model, review=bool(ev.get("review")),
                       quiet=bool(ev.get("quiet")), attempt=ev.get("attempt"))
        elif kind == "turn_end":
            th = (ev.get("thinking") or "").strip()
            peek = ev.get("peek") or (th.split(". ")[0][:140] if th else "")     # a step's own line first (the figures step says what it drew)
            self._pane('pane_turn_end', turn=ev.get("turn"), kind=ev.get("kind"), peek=peek, elapsed=ev.get("elapsed"),
                       cost=ev.get("cost"), thinking=th[:4000], note=ev.get("note") or "", code=ev.get("code") or "")
        elif kind == "heartbeat":
            self._pane('pane_heartbeat', turn=ev.get("turn"), of=ev.get("of"), spent=round(float(ev.get("spent") or 0), 3),
                       dollars=ev.get("dollars"), estimate=ev.get("estimate") or "", mode=self._mode_label)
        elif kind == "cell_start":
            self._pane('pane_cell_start', turn=ev.get("turn"))
        elif kind == "cell":
            ok = not ev.get('error')
            skipped = ok and ev.get('cell_no') is None          # a cell the session did not run: a figure cell during the analysis (2026-10-11)
            out = (ev.get('stdout') or '').strip()
            peek = ('not run: figures are drawn after the report' if skipped else next((ln.strip() for ln in out.splitlines() if ln.strip()), '')) if ok else ''
            from analyst.tools import exception_line
            t = next((x for x in reversed(run.turns) if x.kind == kind), None)
            self._pane('pane_cell', cell_no=ev.get('cell_no'), ok=ok, skipped=skipped, peek=peek[:160], elapsed=(None if skipped else (t.elapsed if t else None)),
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
            kept = list(getattr(self, '_last_read_passages', None) or [])     # the same passages with the originals of rendered quotes (S2)
            if kind == "read" and [p.get('id') for p in kept] == [p.get('id') for p in passages]:
                passages = kept
            peek = (reading.digest_peek(text) if kind == "read" else next((ln.strip() for ln in text.splitlines() if ln.strip()), ''))[:160]
            self._pane('pane_lookup', kind=kind, query=query, peek=peek, sources=sources, passages=passages)
            self._tab('plan', self._notebook_view(run))
        elif kind == "report":
            # the passages the report cites, resolved, for the chips' hover - before the answer renders (S2)
            passages = self._cited_passages(ev.get("text") or "")
            if passages:
                self._pane('pane_passages', passages=passages)
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
                          image=None, auto_explore=False, max_investigations=None, synthesis=False, mode=None, ideas=None):
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

        data_record = self._data_record()                   # what this run runs on, kept on the run (2026-10-10, routines)
        kernel = self._kernel_for(parent, data_record)       # ... and what decides which earlier cells it continues (2026-10-12)
        figure = self._figure_for_analyst(image) if image else None
        session = Session(kernel, self.notebook, self._llm, store=self.store, emit=self._emit,
                          recall=self._recall if self.memory_path else None, search=self._search,
                          read=self._read, unit_text=self._unit_text, kernel_prelude=self._kernel_prelude(),
                          documents=bool(self._documents_prelude()), context=bool(self._context_prelude()),
                          data_description=self._data_description(), kernel_factory=self._new_kernel,
                          replay_runner=self._run_replay)
        try:
            run = session.run(question, parent=parent, budget=budget, run_id=str(self.chain_id), data=data_record, image=figure)
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
            try:
                _run = self.notebook.runs.get(str(self.chain_id)) if self.notebook else None
                if _run is not None and not _run.data:
                    _run.data = data_record
                    self.store.save(self.notebook)
            except Exception:                                  # noqa: BLE001
                logger.warning("The run's data record was not kept", exc_info=True)
        self._kernel_tip = run.id

        # what the reader sees: the tabs the browser already has
        rep = self._replay.pop(run.id, {})
        files = [{'path': f, 'name': str(f).split('/')[-1]} for f in (rep.get('datasets') or [])]
        if files:
            self._pane('pane_datasets', files=files)
        replay_line = ''
        if run.report and '> Replay' in run.report:
            replay_line = run.report.rsplit('> ', 1)[-1].strip().splitlines()[0]
        self._pane('pane_run_end', status=run.status, turns=len([t for t in run.turns if t.kind not in ('rewrite', 'review') and not getattr(t, 'step', '')]),
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
