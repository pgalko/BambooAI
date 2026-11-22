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
from analyst import profile as profile_mod
from analyst import reach as reach_mod
from analyst import tools
from analyst.notebook import branch_points, has_data, kept_turns, same_load
from analyst.replay import rehydrate, went_back, again as cells_again
from logger_config import get_logger

logger = get_logger(__name__)

# The cell of a draft as an executor runs it (2026-11-18). The executor runs a script in a thread and, past the
# time it gives it, answers and leaves the thread running: a cell that never ends would run on there. The guard
# raises in that thread shortly before, so the cell ends; where it never comes back from compiled code, it cannot.
# The cell is compiled under a name of its own, so that an error tells its lines from the guard's (_run_draft).
DRAFT_GUARD = """import ctypes as _guard_c, threading as _guard_t
class _OutOfTime(BaseException):
    pass
_guard = _guard_t.Timer({seconds}, lambda ident=_guard_t.get_ident(): _guard_c.pythonapi.PyThreadState_SetAsyncExc(_guard_c.c_ulong(ident), _guard_c.py_object(_OutOfTime)))
_guard.daemon = True
_guard.start()
try:
    exec(compile({code!r}, "<draft>", "exec"), globals())
except _OutOfTime:
    raise TimeoutError("the cell took longer than {seconds} seconds") from None
finally:
    _guard.cancel()
"""


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
        self._framed = set()             # the chains the Pathfinder talked in whose analysis has not run: their calls are not charged yet
        self._skip_saved = threading.Event()      # the person no longer waits for the saved analyses to be read (the Pathfinder's row, Skip)

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

    def _architect_seat(self):
        """The seat the Pathfinder runs on (docs/ARCHITECT_DESIGN.md, decision 28): 'Pathfinder' when the config carries
        one; 'Architect' - its name until 2.9 - where a config written before carries that; else the analyst seat.
        Whichever it is, its calls are logged as the Pathfinder's (_llm's `label`)."""
        agents = {a.get('agent') for a in (getattr(self.models, "config", {}) or {}).get('agent_configs', [])}
        for seat in ('Pathfinder', 'Architect'):
            if seat in agents:
                return seat
        return self._seat()

    def _memory_seats(self):
        """The seats the reader of the saved analyses runs on (docs/ARCHITECT_DESIGN.md, decision 28): the reader on
        'Memory Reader' when the config carries one, else the analyst's seat; its second model on 'Memory Pieces',
        else the 'Reader' seat - the fast model that reads the documents - else the analyst's. Either way the calls
        are logged under those two names (_llm's `label`)."""
        agents = {a.get('agent') for a in (getattr(self.models, "config", {}) or {}).get('agent_configs', [])}
        return ('Memory Reader' if 'Memory Reader' in agents else self._seat(),
                'Memory Pieces' if 'Memory Pieces' in agents else 'Reader' if 'Reader' in agents else self._seat())

    def _promoter_seat(self):
        """The seat Save as routine's one model call runs on (2026-10-10): 'Promoter' when the config carries one -
        its own model, effort and token allowance, since the reply is a JSON object of edits that a seat tuned for
        long reasoning can cut short - else the analyst seat."""
        agents = {a.get('agent') for a in (getattr(self.models, "config", {}) or {}).get('agent_configs', [])}
        return 'Promoter' if 'Promoter' in agents else self._seat()

    def _llm(self, system: str, user: str, review: bool = False, rewrite: bool = False, figures: bool = False, seat: str = None, image: str = None,
             effort=None, label: str = None, chain=None, **hints):
        """The model call the session uses: the app's model layer (streaming,
        telemetry, retries), returning (text, {'cost': delta}). A self-review
        turn (review=True) runs on the Reviewer seat; its cost is accounted to
        that seat and counts against the run's budget like any other call. The
        rewrite and the figures request have seats of their own when the config
        carries them. `seat` names the seat outright (the routines' promoter).
        `image` (a PNG, base64) rides with the user message as an image part in
        the OpenAI form - the OpenAI-compatible adapters pass it through, the
        Anthropic and Gemini adapters convert it (2026-10-13: the plot's Ask AI
        had sent the picture since v1 and the analyst never received it).
        `effort` lowers the seat's effort for this call - a word, or words in
        order of preference, the first the model accepts (the analyst's report
        turn and its second attempts, 2026-10-18); the usage says the effort the
        call was asked at. `label` is the name the call is logged under when
        it is not the seat's (the Pathfinder on the analyst's seat). `chain` is
        the chain the call is logged and counted under when it is not the
        instance's own: a call made beside the analyses (next questions),
        which leaves the instance's chain alone."""
        if self.kill_signal or self._stop_event.is_set():
            raise ExecutionInterrupted("stopped by the user")
        chain = self.chain_id if chain is None else chain
        before = self._chain_cost(chain)
        content = user if not image else [{"type": "text", "text": user}, {"type": "image_url", "image_url": {"url": "data:image/png;base64," + image}}]
        messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]
        text = self.llm_stream(self.prompts, self.log_and_call_manager, self.output_manager, messages,
                               agent=seat or (self._review_seat() if review else (self._rewrite_seat() if rewrite else (self._figures_seat() if figures else self._seat()))), chain_id=chain,
                               reasoning_models=self.reasoning_models, **({"reasoning_effort": effort} if effort else {}),
                               **({"label": label} if label else {}))
        if isinstance(text, tuple):
            text = text[0]
        # whether the reply was cut at the seat's max_tokens (the model layer records it per request; 2026-10-06: a turn
        # spent its whole 16,000 tokens reasoning and the 887 characters that arrived had no action - the analyst was told
        # "no valid action", which is true but not what happened)
        from bambooai.models import prompt_cache
        meta = prompt_cache.last_meta()
        # a request the provider's classifier declined before any text (2026-10-08: the Claude 5.5 family's stop_reason
        # "refusal"; the adapter records the category so the session can say what happened rather than "no valid action")
        return text or "", {"cost": max(0.0, self._chain_cost(chain) - before), "truncated": bool(meta.get("truncated")),
                            "declined": meta.get("declined") or "", "effort": meta.get("seat_effort") or ""}

    def _chain_cost(self, chain=None):
        """What the calls logged under a chain have cost so far: the instance's own chain, or the one given."""
        chain = self.chain_id if chain is None else chain
        ts = self.log_and_call_manager.token_summary
        summary = ts.get(chain) or ts.get(str(chain)) or {}
        return float(summary.get('total_cost', 0.0) or 0.0)

    # ---------------------------------------------------------------- kernel
    def _new_kernel(self, frame=True):
        """A fresh kernel: with the data loaded now, or - `frame=False` - without any, for the reader of the saved
        analyses. On an executor it takes the place of the kernel there (force): the executor holds one."""
        if self.execution_mode == 'api' and self.executor_api_url:
            from bambooai.kernel_client import RemoteKernel
            try:
                logger.info("Executor at %s: build %s", self.executor_api_url, (self.api_client.executor_build() if self.api_client else None) or "unknown (image before 2026-09-07)")
            except Exception:                                  # noqa: BLE001
                pass
            return RemoteKernel(base_url=self.executor_api_url, df_id=self.df_id if frame else None, session_id=None, force=True,
                                generated_dir=self._generated_dir() if frame else None)
        import sys
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if os.path.join(here, 'delve') not in sys.path:
            sys.path.insert(0, os.path.join(here, 'delve'))
        from kernel import PersistentKernel
        return PersistentKernel(df=self.df if frame else None, generated_dir=self._generated_dir() if frame else None)

    def _generated_dir(self):
        """The user's generated-datasets folder - the one /cache/inspect lists under Generated and the download route
        serves (2026-10-06): where DS.save puts a dataset the analyst makes for the person, in the kernel during the
        analysis and in the replay. The same expression the replay has always passed to the executor."""
        return os.path.join('datasets', self.user_id or '', 'generated')

    def _kernel_for(self, parent_run_id, data_record=None):
        """The kernel the run works in. Continuing from the tip the kernel already
        holds, with the frame it holds still the one loaded: reuse it. Continuing
        from an earlier chain whose state the kernel still holds (2.9: it keeps a
        snapshot of every cell's): the kernel goes back to it, and nothing runs
        again. Anything else (a new thread, a dead kernel, the frame replaced
        since, a chain from before the kernel kept its states): a
        fresh kernel rehydrated from the cells of the parent's path that ran on
        the same data as `data_record`, the record of the data loaded now - the
        same frame, or the same data loaded again under a new id (2026-10-12: a
        routine's run had loaded another window, and the follow-up went on in the
        warm kernel with `df` and the names of the earlier window, while the DATA
        block described the new one; a favourite continued in a new session with
        its file uploaded again is the same data and is rehydrated as before)."""
        cells = self.notebook.computed_cells(parent_run_id, data=data_record if data_record is not None else {"df_id": self.df_id}) if parent_run_id is not None else []
        if self._kernel is not None and parent_run_id is not None:
            if not self._same_frame(parent_run_id):
                logger.info("The frame loaded is not the one the chain in the kernel ran on; a fresh kernel for the follow-up")
            else:
                try:
                    if parent_run_id == self._kernel_tip:
                        _, err, _ = self._kernel.execute("pass")      # is the warm kernel still alive (the executor reaps idle sessions)?
                        if not err:
                            return self._kernel
                        logger.info("Warm kernel unusable (%s); rehydrating from the parent's path", err.strip()[:80])
                    elif tools.goto(self._kernel, cells[-1].snap if cells else tools.snap(self._kernel, 0)):
                        # the state that chain ended in: after the last cell computed on its path, or - a path that
                        # computed nothing - the kernel's state at the start
                        logger.info("The kernel went back to the state chain %s ended in", parent_run_id)
                        return self._kernel
                except Exception as exc:                           # noqa: BLE001
                    logger.info("Warm kernel gone (%s); rehydrating from the parent's path", exc)
        self._drop_kernel()
        self._kernel = self._new_kernel()
        if cells:
            n, err = rehydrate(self._kernel, cells)
            if err:
                self.output_manager.display_system_messages(
                    f"Restoring the earlier analysis stopped after {n} of {len(cells)} cells: {err}", chain_id=self.chain_id)
        return self._kernel

    def _kernel_at(self, src, turn, data_record):
        """The kernel for a branch that goes on from turn `turn` of run `src` (docs/BRANCH_DESIGN.md), at the state the
        kept turns left: (kernel, reran, error). Where the kernel still holds that state it goes back to it - nothing
        runs again, or the kept cells that had to printed what their records show - and `reran` is empty. Otherwise
        a fresh kernel: the earlier chains' cells are run again as for any follow-up, then the cells the branch
        keeps, and `reran` says what each of those printed this time (the session marks a cell that printed
        something else). A cell that fails when run again leaves no state to go on from: the error says which."""
        kept = [t for t in kept_turns(src, turn) if t.kind == "cell" and t.cell_no is not None]
        before = self.notebook.computed_cells(src.parent, data=data_record) if src.parent is not None else []
        cells = before + kept
        self._kernel_tip = None                                # the kernel leaves the chain's end it stood at
        if self._kernel is not None and self._same_frame(src.id):
            try:
                if tools.goto(self._kernel, cells[-1].snap if cells else tools.snap(self._kernel, 0)) and went_back(self._kernel, kept):
                    logger.info("The kernel went back to the state after turn %s of chain %s", turn, src.id)
                    return self._kernel, {}, ""
                logger.info("The kernel does not hold the state after turn %s of chain %s as the record has it", turn, src.id)
            except Exception as exc:                           # noqa: BLE001
                logger.info("Warm kernel gone (%s)", exc)
        logger.info("A fresh kernel for the branch: the %d cells before chain %s and the %d it keeps of it are run again", len(before), src.id, len(kept))
        self._drop_kernel()
        self._kernel = self._new_kernel()
        if before:
            n, err = rehydrate(self._kernel, before)
            if err:
                return self._kernel, {}, f"restoring the earlier analysis stopped after {n} of {len(before)} cells: {err}"
        reran, err = cells_again(self._kernel, kept)
        return self._kernel, reran, err

    def _closing_card(self, run, budget, rep=None):
        """The pane's closing card for a run that ended or was stopped: its counts, what its replay said, the datasets
        it saved, what its cells reached - and whether it has turns to go on from, for the page's Analysis map."""
        rep = rep or {}
        files = [{'path': f, 'name': str(f).split('/')[-1]} for f in (rep.get('datasets') or [])]
        if files:
            self._pane('pane_datasets', files=files)
        replay_line = ''
        if run.report and '> Replay' in run.report:
            replay_line = run.report.rsplit('> ', 1)[-1].strip().splitlines()[0]
        self._pane('pane_run_end', status=run.status, turns=len([t for t in run.turns if t.kind not in ('rewrite', 'review') and not getattr(t, 'step', '')]),
                   cells_of=budget.turns, cells=len(run.cells()), failed=sum(1 for t in run.turns if t.kind == 'cell' and t.error and not getattr(t, 'refused', '')),
                   refused=sum(1 for t in run.turns if t.kind == 'cell' and getattr(t, 'refused', '')),     # not run, not failed (2026-10-28)
                   cost=round(self._chain_cost(), 3),
                   seconds=round(sum(float((t.usage or {}).get('elapsed') or 0) + float(t.elapsed or 0) for t in run.turns if not t.kept), 1),   # a branch's own turns
                   replay_status=run.replay_status or '', replay_line=replay_line, plots=len(rep.get('plots') or []), files=files,
                   reaches=reach_mod.summary(run),                 # the reach report: what the cells touched outside the data (2026-10-28)
                   turn_map=bool(branch_points(run)) and not run.figure_asked)   # it has turns to go on from: the page offers its Analysis map (2.9)

    def _carry_drafts(self, src):
        """The plots of the drafts of the brief a branch runs under - drawn before the first run of its analysis, and
        kept under that run (analyst/draft.py) - kept under the branch's chain too, before the chain is announced: its
        Brief tab asks for them under it (0331: it showed none)."""
        from analyst import draft
        try:
            draft.Plots(self._user_storage()).carry(self.notebook.thread_id, draft.lineage(self.notebook, src.id), self.chain_id)
        except OSError:
            logger.warning("The drafts of the branch's brief were not kept under it", exc_info=True)

    def _no_branch(self, src, turn, data_now):
        """Why no branch can go on from turn `turn` of run `src` - '' when one can (docs/BRANCH_DESIGN.md §2)."""
        if src is None:
            return "The analysis to go on from is not in this thread."
        if src.status == "running":
            return "This analysis has not ended: stop it, or wait for its report, then go on from one of its turns."
        if src.figure_asked:
            return "An analysis that was asked about a plot cannot be gone on from yet."
        points = branch_points(src)
        if not points:
            return "This analysis cannot be gone on from: it was made before version 2.9, or it is a routine's run."
        if turn not in points:
            return f"Turn {turn} cannot be gone on from: this analysis can go on from turns {points[0]} to {points[-1]}."
        if not same_load(src.data, data_now):
            if not has_data(src.data):
                return "This analysis ran with no data loaded: remove the dataset, then go on from its turn."
            name = (src.data or {}).get("name") or ""
            return "Load the data this analysis ran on first" + (f": {name}." if name else ".")
        return ""

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
        if notes is not None and codes is not None and len(codes):
            # a codes file written before patch 0206 has no `day`: it is filled and the file written back, so the
            # kernel's CTX.codes() and a read by path have what DATA shows; a file the pass wrote is left as it is
            days = context_mod.reading_days(codes, notes)
            if days != codes["day"].tolist():
                filled = codes.assign(day=days)
                if self._put_aux_file(codes_path, filled.to_csv(index=False)):
                    codes = filled
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
        """One script through the executor against the loaded data, as the replay runs (2026-10-10: a routine's proof
        and its runs take the same path; a run passes its own folder, where its files and datasets go). Returns
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
            # the traceback's line numbers back in the caller's text, which the prelude pushed down - in its frames, and in
            # the executor's own head line, which names the line first
            import re as _re
            error = _re.sub(r'(File "<string>", line )(\d+)', lambda m: m.group(1) + str(max(1, int(m.group(2)) - offset)), str(error))
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
        from analyst import routines as rt
        from analyst.routines import aux_kind
        src = str(meta.get("source") or "").lower()
        out = {"source": src if src in ("intervals", "endura", "sweatstack") else "file", "cached": True}
        m = re.match(r"^\s*(\d{4}-\d{2}-\d{2})\s*(?:to|->|-)\s*(\d{4}-\d{2}-\d{2})\s*$", str(meta.get("date_range") or ""))
        kinds = [aux_kind(p) for p in rec.get("aux") or []]
        if src == "intervals":
            out.update(metrics=list(meta.get("metrics") or []), aux_kinds=[k for k in kinds if k in rt.LOAD_KINDS["intervals"] or k in rt.brings("intervals", rt.LOAD_KINDS["intervals"])])
            if m:
                out.update(start_date=m.group(1), end_date=m.group(2))
            if meta.get("key_mark"):
                out["key"] = meta["key_mark"]
            if isinstance(meta.get("subject"), dict) and meta["subject"].get("id"):      # whose data (2026-10-29)
                out["subject"] = {k: meta["subject"].get(k, "") for k in ("source", "id", "name")}
        elif src == "endura":
            out.update(race_id=meta.get("race_id"), race_title=meta.get("race_title") or "", aux_kinds=[k for k in kinds if k in rt.LOAD_KINDS["endura"]])
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
        elif kind == "step":                                     # the Save-as-routine dialog's checklist (§17): never a pane row
            self._pane('routine_step', step=ev.get("step") or '', state=ev.get("state") or 'done', detail=ev.get("detail") or '', again=bool(ev.get("again")))
        elif kind == "lookup_start":
            self._pane('pane_lookup_start', kind=ev.get("kind") or 'routine', query=ev.get("query") or '', model='')
            if (ev.get("kind") or 'routine') in ('routine', 'run'):
                self._pane('pane_cell_start', turn='routine')           # the executor chip on Executing while the method runs
        elif kind == "lookup":
            # a CHECK row's sentences run long (step 4, 2026-10-11): the row shows what fits and carries the whole line on hover.
            # The cap is for a runaway line, not a long one (2026-10-16: at 600 a run with seven files lost its closing sentence -
            # the cut to the window - before the page saw it; a sentence per file, a dozen files, is ~1,500)
            self._pane('pane_lookup', kind=ev.get("kind") or 'routine', query=ev.get("query") or '', peek=(ev.get("peek") or '')[:self.LOOKUP_PEEK_CHARS], sources=[], passages=[])

    def propose_routine(self, thread_id, chain_id, routine_id=None, billing_chain_id=None, instruction=""):
        """Save as routine, step one: the promoter reads the chain and proposes its inputs. The call is accounted to
        `billing_chain_id` (a chain of its own, so the hosted edition charges it as a query). `instruction` is the
        person's line on what the runs should track (docs/ROUTINES_DESIGN.md §15.6). Returns the proposal, kept on the
        instance until create_routine takes it; raises RoutineRefused with a readable reason."""
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
                                             runner=lambda s, t: self.run_script(s, t, what="Shape"), instruction=instruction or "")
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
            elif k in ("store", "subject") and isinstance(v, dict) and all(isinstance(x, (str, int, float, bool)) or x is None for x in v.values()):
                out[k] = dict(v)                              # the store's counts (2026-10-15): window, held, fetched, refresh; whose data (2026-10-30)
        return out

    def run_routine(self, routine_id, values=None, compare_with="previous", aux=None, load=None, interval=None, quiet=False):
        """One run of the routine on the data loaded now (F2): the checks, the script with its INPUTS block through the
        executor a statement at a time, its lines laid against the tracked ones, the comparison with the run before,
        the record stored; then the tabs as an analysis has them (Data, Results, Plots) and the closing card for the
        pane. `interval` (docs/ROUTINES_DESIGN.md §14.1): the calendar unit the window is. `quiet` (a fill's runs):
        the record alone - no rows, tabs or card."""
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
        reads = routines_host.reads_data(routine)                 # a method made without data takes nothing from the Data tab
        if reads:
            logger.info("Routine %s run %d: data %s (%s rows, %d columns, %d auxiliary file(s): %s)", routine_id, number, data.get("source"), data.get("rows"),
                        len(data.get("columns") or []), len(data.get("aux") or []), ", ".join(os.path.basename(str(p)) for p in (data.get("aux") or [])) or "-")
        else:
            logger.info("Routine %s run %d: no data (the method reads none)", routine_id, number)
        out = routines_host.run(routine, values, data, lambda script, timeout, d=None: self.run_script(script, timeout, what=f"Routine {routine_id}", generated_dir=d),
                                self.routine_store(), emit=None if quiet else self._emit_routine, compare_with=compare_with, run_dir=run_dir, interval=interval)
        r, c = out["run"], out["run"]["comparison"]
        if not quiet:
            try:
                shown = (self.df_id, self.df) if reads else (None, None)      # the Data tab is the run's data
                self.output_manager.display_results(chain_id=None, execution_mode=self.execution_mode, df_id=shown[0], df=shown[1], api_client=self.api_client,
                                                    code_exec_results=out["stdout"] or None, plot_jsons=out["figures"] or None)
            except Exception:                                      # noqa: BLE001
                logger.warning("The run's tabs could not be sent", exc_info=True)
            self._pane('pane_routine_end', number=r["number"], name=routine.get("name", ""), version=r["version"], status=r["status"], line=r["line"],
                       results=sum(1 for x in r["results"] if x.get("estimate") is not None), compared=c["compared"], moved=c["moved"], changed=c["changed"], missing=c["missing"], figures=r["figures"],
                       elapsed=r["elapsed"], against=r["against"], comparison_line=c["line"])
        logger.info("Routine %s run %d (v%d%s): %s; %s", routine_id, r["number"], r["version"], f", {interval}" if interval else "", r["line"], c["line"])
        return {k: out[k] for k in ("run", "summary", "routine", "numbers", "name", "subject", "against_data", "inputs")}     # whose, and the reference run's data (2026-10-30)

    def fill_routine(self, routine_id, interval, windows, values=None, aux=None, load=None):
        """A fill (docs/ROUTINES_DESIGN.md §14.3): the routine on each window of a set interval, oldest first, in a
        thread; every window a cut of the span loaded now. One at a time per session; the status is read back."""
        from bambooai import routines_host
        fill = getattr(self, "_fill", None)
        if fill is not None and fill.running:
            raise routines_host.RoutineRefused("a fill is already running: wait for it, or stop it in the Summary")
        routine = self.routine_store().load(routine_id)
        if routine is None:
            raise routines_host.RoutineRefused("no such routine")
        self._fill = routines_host.Fill(self, routine_id, interval, windows, values, aux, load, routine_name=routine.get("name") or "").start()
        return self._fill.status()

    def fill_status(self):
        fill = getattr(self, "_fill", None)
        return fill.status() if fill is not None else {"running": False}

    def fill_stop(self):
        fill = getattr(self, "_fill", None)
        if fill is not None:
            fill.stop()
        return self.fill_status()

    def create_routine(self, proposal_id, choices, routine_id=None):
        """Save as routine, step two: the person's choices applied and the routine stored; the proof on the chain's
        own data - run zero, the shorter run, the trials on smaller pieces (routines_host.prove_method) - runs in a
        thread and lands on the stored version. Raises RoutineRefused when the proposal is gone or cannot be stored."""
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
        # the proof behind the dialog (2026-10-15: run zero re-executes every cell of the chain - nine minutes on a heavy
        # one): the routine is stored at once as verifying, the verdict lands on it from a thread, a run is refused until
        # it has settled, and after a verdict that is not reproduced. The proof is of the data loaded now: it stops when
        # the Data tab holds something else - unless the method reads no data (docs/ROUTINES_DESIGN.md §24)
        frame = self.df_id
        reads = proposal.get("data_state") != "none"

        def runner(script, timeout, folder=None):
            if reads and self.df_id != frame:
                raise RuntimeError("the data on the Data tab changed while the routine was being verified")
            return self.run_script(script, timeout, what="Run zero", generated_dir=folder)
        made = routines_host.create(nb, proposal, choices or {}, runner, self.routine_store(), emit=self._emit_routine, routine_id=routine_id, background=True,
                                    runs_root=os.path.join('datasets', self.user_id or '', 'routines'))
        pending.pop(proposal_id, None)
        verify = made.pop("verify", None)
        logger.info("Routine %s v%d made from chain %s: %s", made["routine"]["id"], made["version"], proposal["chain_id"], made["run_zero"]["line"])
        if verify is not None:
            rid, vnum = made["routine"]["id"], made["version"]

            def work():
                try:
                    proof = verify()
                    logger.info("Routine %s v%d verified: %s (%.0f s); %s; tried: %s", rid, vnum, proof.get("line"), float(proof.get("elapsed") or 0), (proof.get("lean") or {}).get("line") or "-",
                                "; ".join(f"{t['interval']} {t['came']} of {t['of']}" for t in proof.get("tried") or []) or "-")
                except Exception as exc:                            # noqa: BLE001
                    logger.error("Routine %s v%d: the verification failed: %s", rid, vnum, exc)
            threading.Thread(target=work, daemon=True, name=f"routine-verify-{rid}").start()
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
    LOOKUP_PEEK_CHARS = 3000      # a routine's LOAD / CHECK / RUN / COMPARE row text as the page gets it (whole on hover): a cap for a runaway line
    AUX_BLOCK_CHARS = 14000       # the heads of all the files together (2026-10-16): a load brings several files, a person can attach more, and every turn carries the block

    def _aux_columns(self, paths):
        """The column names of these files, from the executor in api mode or read here otherwise (one call for them all):
        what a file's entry shows once the heads' budget is spent. {path: "a, b, c"}; empty when the describer could not
        pair them - the entries then say to read the file."""
        try:
            described = utils.get_aux_datasets_columns(paths, execution_mode=self.execution_mode,
                                                       executor_client=self.api_client if self.execution_mode == 'api' else None) or ""
        except Exception as exc:                              # noqa: BLE001
            logger.warning("auxiliary files: the columns could not be read (%s)", exc)
            return {}
        parts = [p for p in described.split("\n\n") if p.strip()]
        if len(parts) != len(paths):
            return {}
        out = {}
        for path, part in zip(paths, parts):
            lines = part.split("\n")
            if "Columns:" in lines and lines.index("Columns:") + 1 < len(lines):
                out[path] = lines[lines.index("Columns:") + 1]
        return out

    def _map_inputs(self, run):
        """The inputs a chain was offered, for its code trace (analyst/codemap, 2026-10-20): the primary with its columns,
        each auxiliary file with its columns (one executor call for them all), the context when the load carries one,
        and the thread's documents as the kernel names them (D1, D2, ...). Called once, at the chain's end."""
        from analyst.codemap.record import inputs_from_data
        out = inputs_from_data(run, context=bool(self._context_prelude()))
        paths = [i["path"] for i in out if i.get("kind") == "file" and i.get("path")]
        if paths:
            cols = self._aux_columns(paths)
            for i in out:
                if i.get("kind") == "file" and cols.get(i.get("path")):
                    i["columns"] = [c.strip() for c in str(cols[i["path"]]).split(",") if c.strip()]
        if self.thread_id is not None and self._documents_prelude():
            for d in documents.load_manifest(self._documents_dir()).get("documents") or []:
                out.append({"kind": "document", "label": str(d.get("id") or ""), "name": str(d.get("file") or "")})
        return out

    @staticmethod
    def _aux_compact(i, path, cols):
        """A file's entry without its rows (the heads' budget is spent): the path, the column names when the describer
        read them, and a note to read the file."""
        names = [c.strip() for c in str(cols or "").split(",") if c.strip()]
        line = f"Columns ({len(names)}): {', '.join(names)}" if names else "Columns: read the file for them"
        return f"{i}.\nPath: {path}\n{line}\n(the rows are left out to keep the prompt short; read the file for them)"

    def _auxiliary_block(self):
        """The auxiliary files as the analyst reads them: each one's path as the kernel sees it (relative to its working
        directory, the same path in both compute modes) and its first rows, from the executor in api mode or read here
        otherwise - the description the original BambooAI gave; a very wide head is cut with a note. The heads together
        keep to AUX_BLOCK_CHARS: once the budget is spent, the files that follow show their path and columns alone."""
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
        spent, columns = 0, None                           # the heads' budget; the columns, fetched once if it is spent
        for i, (path, part) in enumerate(zip(paths, parts), 1):
            kind = aux_kind(path)
            if kind in ("context", "codes"):               # the rows are passages: the columns and the count, the map below says the rest
                frames[path] = notes_df if path == notes_path else codes_df
                if frames[path] is not None:
                    part = f"{i}.\n" + context_mod.aux_head_for_text_file(path, list(frames[path].columns), len(frames[path]))
            elif kind == "rider":                           # the settings (2026-10-16): the columns, the count and a line from the rows, not a head of five
                prof = self._profile_frame(path)
                if prof is not None:
                    part = f"{i}.\n" + profile_mod.aux_head(path, prof)
            if len(part) > self.AUX_HEAD_CHARS:
                part = part[:self.AUX_HEAD_CHARS].rstrip() + "\n... [the head is cut here; read the file for the rest]"
            if spent + len(part) > self.AUX_BLOCK_CHARS and kind not in ("context", "codes", "rider"):
                if columns is None:
                    columns = self._aux_columns(paths[i - 1:])
                part = self._aux_compact(i, path, columns.get(path))
            spent += len(part)
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

    def _aux_file_text(self, path):
        """An auxiliary file's text: from the executor in api mode (the file lives there), read here otherwise; None when
        it is not there."""
        if self.execution_mode == 'api' and self.api_client is not None:
            return self.api_client.read_aux_dataset(path)
        if not os.path.exists(path):
            return None
        with open(path, encoding='utf-8', errors='replace') as f:
            return f.read()

    def _context_file(self, path):
        """A context or codes file as a frame: from the executor in api mode (the file lives there), read here otherwise;
        None when it cannot be read."""
        from analyst.routines import aux_kind
        try:
            text = self._aux_file_text(path)
            if text is None:
                return None
            return context_mod.read_codes(text) if aux_kind(path) == "codes" else context_mod.read_context(text)
        except Exception as exc:                              # noqa: BLE001
            logger.warning("context: %s could not be read (%s)", path, exc)
            return None

    def _profile_frame(self, path):
        """The rider profile file as a frame, read once per load (the path is the key); None when it cannot be read."""
        cached = getattr(self, '_profile_cache', None)
        if cached and cached[0] == path:
            return cached[1]
        try:
            text = self._aux_file_text(path)
            frame = profile_mod.read_profile(text) if text is not None else None
        except Exception as exc:                              # noqa: BLE001
            logger.warning("profile: %s could not be read (%s)", path, exc)
            frame = None
        self._profile_cache = (path, frame)
        return frame

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
                       quiet=bool(ev.get("quiet")), attempt=ev.get("attempt"), **({"kept": True} if ev.get("kept") else {}))   # kept: a turn a branch keeps
        elif kind == "turn_end":
            th = (ev.get("thinking") or "").strip()
            peek = ev.get("peek") or (th.split(". ")[0][:140] if th else "")     # a step's own line first (the figures step says what it drew)
            self._pane('pane_turn_end', turn=ev.get("turn"), kind=ev.get("kind"), peek=peek, elapsed=ev.get("elapsed"),
                       cost=ev.get("cost"), thinking=th[:4000], note=ev.get("note") or "", code=ev.get("code") or "",
                       **({"kept": True} if ev.get("kept") else {}))
        elif kind == "heartbeat":
            self._pane('pane_heartbeat', turn=ev.get("turn"), of=ev.get("of"), spent=round(float(ev.get("spent") or 0), 3),
                       dollars=ev.get("dollars"), estimate=ev.get("estimate") or "", mode=self._mode_label)
        elif kind == "cell_start":
            self._pane('pane_cell_start', turn=ev.get("turn"))
        elif kind == "cell":
            refused = str(ev.get('refused') or '')                # the executor refused the cell before it ran: its own state, not a failure (2026-10-28)
            ok = not ev.get('error') or bool(refused)
            skipped = ok and ev.get('cell_no') is None and not refused   # a cell the session did not run: a figure cell during the analysis (2026-10-11)
            out = (ev.get('stdout') or '').strip()
            peek = (f'not run: restricted operation ({refused})' if refused else
                    ('not run: figures are drawn after the report' if skipped else next((ln.strip() for ln in out.splitlines() if ln.strip()), ''))) if ok else ''
            from analyst.tools import exception_line
            self._pane('pane_cell', cell_no=ev.get('cell_no'), ok=ok, skipped=skipped, refused=refused, peek=peek[:160], elapsed=(None if skipped or refused else ev.get('elapsed')),
                       chars=len(ev.get('stdout') or ''), figs=len(ev.get('figures') or []),
                       error_line=exception_line(ev.get('error') or '')[:220] if not ok else '',
                       reach=reach_mod.chip(ev.get('reaches') or []),          # the row's tag when the cell reached outside the data
                       **({"kept": ev.get("kept")} if ev.get("kept") else {}))  # kept, or differs: run again, it printed something else
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
        elif kind in ("show", "names", "search", "read"):
            text = ev.get('text') or ''
            query = ev.get('query') or (self._last_search_query if kind == "search" else (getattr(self, '_last_read_query', '') if kind == "read" else ''))
            sources = list(getattr(self, '_last_search_sources', []) or [])[:8] if kind == "search" else []
            passages = reading.parse_digest(text) if kind == "read" else []
            kept = list(getattr(self, '_last_read_passages', None) or [])     # the same passages with the originals of rendered quotes (S2)
            if kind == "read" and [p.get('id') for p in kept] == [p.get('id') for p in passages]:
                passages = kept
            # the first line that says something; a view's own first line without its rule marks ("--- cell 3 (re-opened) ---")
            peek = (reading.digest_peek(text) if kind == "read" else next((re.sub(r"^-{3} | -{3}$", "", ln.strip()) for ln in text.splitlines() if ln.strip()), ''))[:160]
            self._pane('pane_lookup', kind=kind, query=query, peek=peek, sources=sources, passages=passages)
            self._tab('plan', self._notebook_view(run))
        elif kind == "report":
            # the passages the report cites, resolved, for the chips' hover - before the answer renders (S2)
            passages = self._cited_passages(ev.get("text") or "")
            if passages:
                self._pane('pane_passages', passages=passages)
        elif kind == "replay_start":
            # the replay under way: a pending row in the pane, and the executor chip on Executing as for a cell
            secs = float(ev.get("seconds") or 0.0)             # the cells' own time: the replay re-runs them, so about as long again
            about = f" · about {max(1, int(round(secs / 60)))} min" if secs >= 60 else ""
            self._pane('pane_lookup_start', kind='replay', query=f"{ev.get('cells') or 0} cells{about}", model='')
            self._pane('pane_cell_start', turn='replay')
        elif kind == "replay_end":
            self._pane('pane_lookup', kind='replay', query='', peek=(ev.get("line") or ev.get("status") or "")[:160], sources=[], passages=[])
        elif kind == "error":
            self._pane('pane_lookup', kind='lost', query='', peek=(ev.get("text") or "malformed turn")[:160], sources=[])

    # ---------------------------------------------------------- the entry
    # ------------------------------------------------------------- framing (docs/ARCHITECT_DESIGN.md §2.6, §2.9)
    def _thread_notebook(self, thread_id):
        """The thread's notebook without taking the instance to that thread: the one in hand when it is this thread's,
        read from the store otherwise."""
        if self.notebook is not None and self.notebook.thread_id == str(thread_id):
            return self.notebook
        return self.store.load(thread_id)

    def open_framing(self, question, thread_id=None, chain_id=None):
        """A run on the record before any analysis: the question, where it attaches, and the first version of its
        brief. A follow-up to a run that had a brief starts from what that answer was for and what the person thinks:
        the rest belonged to the question before. Where the analyst stopped and asked, the question is the person's
        answer, and it starts from that brief whole. The framing says whether data is loaded: the page lists the
        checks every run on data makes only then. The question is the first step of the brief's conversation
        (analyst/steps.py). No model is called. Returns the ids the page keeps and the framing."""
        from analyst import brief as briefs, steps
        from analyst.notebook import has_data
        thread_id = thread_id if thread_id is not None else utils.next_thread_id()
        nb = self._thread_notebook(thread_id)
        parent = str(chain_id) if chain_id is not None and str(chain_id) in nb.runs else None
        run_id = utils.next_chain_id()
        run = nb.new_run(question, parent, run_id=str(run_id))
        run.status = "framing"
        last = nb.runs[parent] if parent else None
        brief = last.brief if last is not None else {}
        before = brief if last is not None and last.status == "asked" else {k: brief[k] for k in ("decision", "thinks") if k in brief}
        run.framing = steps.take({**briefs.version({}, {**before, "question": question}, changed=["from the last brief"] if before else []),
                                  "data": has_data(self._data_record(light=True))})
        self.store.save(nb)
        return {"thread_id": thread_id, "chain_id": run_id, "parent_chain_id": chain_id if parent is not None else None, "framing": run.framing}

    def save_brief(self, thread_id, run_id, brief, changed=None, question=None, step=None):
        """One more version of a framing run's brief, as the person left it; the question follows when they changed
        it. `step`: the step of the conversation on their screen, where they made the change - the change is a step
        of its own, which follows it (analyst/steps.py). No draft is drawn for it: a figure the change left as it
        was keeps its draft, and one it changed - with the question, every one - has none until the Pathfinder next
        replies. Returns the framing, or None when the run is not one being framed."""
        from analyst import brief as briefs, draft, steps
        nb = self._thread_notebook(thread_id)
        run = nb.runs.get(str(run_id))
        if run is None or run.status != "framing":
            return None
        if question and str(question).strip():
            run.question = str(question).strip()
        at = steps.go(run.framing, step) if step is not None else run.framing
        run.framing = steps.take(draft.keyed(briefs.version(at, {**(brief if isinstance(brief, dict) else {}), "question": run.question}, changed=changed)))
        self.store.save(nb)
        return run.framing

    def architect_say(self, thread_id, run_id, text=None, step=None):
        """One exchange with the Pathfinder in a framing run (analyst/architect.py): the person's message - none on its
        first turn, nor when it goes on after its lookups, a reading or a part it opened - and its reply, taken into the
        brief and the conversation; a part of an earlier analysis it opens comes from the thread's record, in the engine;
        the lookups a reply asks for are answered here (_architect_look), and the saved analyses are read here
        (_architect_recall) where the reply asks for it. `step`: the step of the conversation on the person's screen -
        the exchange goes on from it (analyst/steps.py). After the reply, the figures of the brief that have no draft are drawn one
        (_draft). The calls are the run's own: logged under its chain as the Pathfinder's - the draft's as the
        draft's -, and charged with its analysis - or when the instance is torn down, if no analysis follows
        (cleanup). Returns the framing, or None when the run is not one being framed; raises architect.Failed with
        the reason to show."""
        from analyst import architect, brief as briefs, draft, memory
        from analyst.notebook import has_data
        self.kill_signal = False                     # a run stopped earlier leaves the signal set, and a call would not start
        self._stop_event.clear()
        self._skip_saved.clear()
        self._on_thread(thread_id)
        run = self.notebook.runs.get(str(run_id))
        if run is None or run.status != "framing":
            return None
        seat = self._architect_seat()
        keep, self.chain_id = self.chain_id, (int(run_id) if str(run_id).isdigit() else run_id)      # the cost is counted by chain
        self._framed.add(self.chain_id)
        try:
            framing = architect.exchange(lambda system, user, **kw: self._llm(system, user, seat=seat, label="Pathfinder", **kw),
                                         self.notebook, run, text, data=self._data_description(), look=self._architect_look,
                                         recall=self._architect_recall, saved=len(memory.view(self._user_storage())["runs"]), step=step)
            run.framing = draft.keyed({**framing, "data": has_data(self._data_record(light=True))})      # as it is now: data may have been loaded since the brief opened
            run.question = (briefs.latest(run.framing) or {}).get("question") or run.question      # the question of the version in use is the run's
            self._draft(run)
        except architect.Failed as exc:
            # nothing of the exchange is kept but its calls: the log holds them, and the next reply's number counts them
            run.framing = {**run.framing, "calls": int(run.framing.get("calls") or 0) + exc.calls}
            raise
        finally:
            self.chain_id = keep
            self.store.save(self.notebook)
            try:
                self.store.record(self.notebook, run)           # the usage ledger's line: a brief never run is named there too
            except Exception:                                  # noqa: BLE001
                logger.warning("The framing run's ledger line was not kept", exc_info=True)
        return run.framing

    def architect_ready(self, thread_id, run_id, step=None):
        """Before the analysis of a framed question starts (analyst/cold.py; docs/ARCHITECT_DESIGN.md §2.22): the
        question of the step on the person's screen is read as the analyst will read it - by a model given what
        the analyst is given, and nothing else - once for a version of the brief. Where it could not place something the
        Pathfinder goes on at once, as after a message, and the figures due a draft are drawn one. The calls are the
        run's own: logged under its chain - the read as the question check's - and charged with its analysis.
        Returns {"framing", "clean": whether the analysis can start} - with "error", the reason in words for the
        person, where the Pathfinder's reply after the read failed - or None when the run is not one being framed.
        A read that could not be made holds nothing up: the analysis can start."""
        from analyst import architect, brief as briefs, cold, draft, memory
        from analyst.notebook import has_data
        self.kill_signal = False                     # a run stopped earlier leaves the signal set, and a call would not start
        self._stop_event.clear()
        self._skip_saved.clear()
        self._on_thread(thread_id)
        run = self.notebook.runs.get(str(run_id))
        if run is None or run.status != "framing":
            return None
        seat, out = self._architect_seat(), {"clean": True}
        keep, self.chain_id = self.chain_id, (int(run_id) if str(run_id).isdigit() else run_id)      # the cost is counted by chain
        self._framed.add(self.chain_id)
        try:
            framing, out["clean"] = cold.ready(lambda system, user, **kw: self._llm(system, user, seat=seat, label="Pathfinder", **kw),
                                               lambda system, user, **kw: self._llm(system, user, seat=seat, label="Question check", **kw),
                                               self.notebook, run, step=step, data=self._data_description(), look=self._architect_look,
                                               recall=self._architect_recall, saved=len(memory.view(self._user_storage())["runs"]))
            run.framing = draft.keyed({**framing, "data": has_data(self._data_record(light=True))})
            run.question = (briefs.latest(run.framing) or {}).get("question") or run.question      # the question of the version in use is the run's
            if not out["clean"]:
                self._draft(run)
        except architect.Failed as exc:                        # the read stands, and the Pathfinder made nothing of it: why
            out = {"clean": False, "error": str(exc)}
        except Exception:                                      # noqa: BLE001
            logger.exception("The question could not be read before its analysis")
        finally:
            self.chain_id = keep
            self.store.save(self.notebook)
            try:
                self.store.record(self.notebook, run)           # the usage ledger's line
            except Exception:                                  # noqa: BLE001
                logger.warning("The framing run's ledger line was not kept", exc_info=True)
        return {"framing": run.framing, **out}

    def _draft(self, run):
        """The draft of a framing run's figures (analyst/draft.py; docs/ARCHITECT_DESIGN.md §2.20), after a reply of
        the Pathfinder's. Where figures of the brief in use are due one, the page is first given the framing as it
        stands - it shows the reply while the draft is drawn. Then a model writes the cell on the figures' seat,
        logged as the draft's under the run's chain; the cell runs with no data (_run_draft); each plot is kept
        beside the thread's record; and the round is a turn of the conversation. A round that could not be made is
        a round that drew nothing, said as such: the reply stands either way."""
        from analyst import brief as briefs, draft
        figures = draft.due(run.framing)
        if not figures:
            return
        self.store.save(self.notebook)
        self._pane('architect_draft', framing=run.framing)
        began, seat, replies = time.time(), self._figures_seat(), []

        def llm(system, user, **kw):
            replies.append(self._llm(system, user, seat=seat, label="Draft", **kw))      # counted: the turn names its last call among the draft's
            return replies[-1]
        try:
            made = draft.draw(llm, self._run_draft, run, figures, saved=self._saved_code(briefs.latest(run.framing)))
            plots = draft.Plots(self._user_storage())
            for key, got in made["drawn"].items():
                plots.put(self.notebook.thread_id, run.id, key, got["plot"])
        except Exception as exc:                               # noqa: BLE001
            logger.exception("The draft of the figures could not be drawn")
            made = draft.lost(f"it could not be drawn: {str(exc).strip().splitlines()[-1][:200] if str(exc).strip() else type(exc).__name__}", len(replies))
        draft.settle(run, figures, made, time.time() - began)

    def _run_draft(self, code):
        """The cell of a draft, run where the analysis' cells run and with no data: one script through the executor
        with no frame, none of the thread's names and no folder to write to, for draft.SECONDS at most - on this
        machine the kernel is stopped then; an executor is asked for that long, and the cell carries a guard that
        ends it (DRAFT_GUARD). A cell out of time is the draft's to say, not a message on the page. Returns (its
        plots as the executor gives them, its error - '' where it ran - with the cell's own lines, as a cell's
        traceback names them, and none of the guard's)."""
        from analyst import draft
        guarded = self.executor.mode == 'api'
        script = DRAFT_GUARD.format(seconds=draft.SECONDS - 2, code=code) if guarded else code
        quiet = type("Quiet", (), {"display_system_messages": staticmethod(lambda *a, **k: None)})()
        try:
            _, _, error, plots, _ = self.executor.execute(quiet, self.kill_signal, script, None, None, None, persist_df=False,
                                                          timeout=draft.SECONDS, step_timeout=draft.SECONDS)
        except Exception as exc:                               # noqa: BLE001
            plots, error = [], str(exc) or type(exc).__name__
        error = str(error or "")
        if guarded:
            error = "\n".join(ln for ln in error.splitlines() if 'File "<string>"' not in ln).replace('File "<draft>"', 'File "<string>"')
        return plots or [], error

    def _saved_code(self, brief):
        """The code of the saved analyses a brief builds on, for the model that drafts its figures: of each one that
        is still saved, the cells along its path as the thread's record holds them (draft.saved_code), under its
        day and what was asked then. '' where the brief builds on none."""
        from analyst import brief as briefs, draft, memory
        built = briefs.analyses([s for s in (brief or {}).get("saved", []) if s.get("accepted") and s.get("thread") and s.get("run")])
        if not built:
            return ""
        saved = {(r["thread"], r["run"]) for r in memory.view(self._user_storage())["runs"]}
        out = []
        for s in (group[0] for group in built):
            code = draft.saved_code(self.store.read(s["thread"]), s["run"], draft.SAVED_CHARS // len(built)) if (str(s["thread"]), str(s["run"])) in saved else ""
            out += [f"{s.get('when', '')} \"{s.get('question', '')}\"\n{code}"] if code else []
        return "\n\n".join(out)

    def _architect_recall(self, question, brief):
        """The person's saved analyses read for a brief (memory_read), under the framing run's chain: the calls are
        the run's own, as the Pathfinder's are. The pane is told as it goes - how many are saved, how many the second
        model has read - and the person can skip it (skip_saved). A reading that could not be made is a result that
        says why: the Pathfinder's reply stands either way."""
        seen = lambda read, of: self._pane('architect_saved', read=read, of=of)      # noqa: E731
        try:
            result = self.memory_read(question, chain=self.chain_id, brief=brief, stop=self._skip_saved.is_set, on_read=seen)
            self._whose(result["found"])
            return result
        except ExecutionInterrupted:
            raise
        except Exception as exc:                               # noqa: BLE001
            logger.exception("The saved analyses could not be read for the brief")
            return {"failed": f"The saved analyses could not be read: {str(exc).strip().splitlines()[-1][:200] if str(exc).strip() else type(exc).__name__}"}

    def _whose(self, found):
        """Whose data each passage's run ran on, for the person to read: the name on the run's load, taken from the
        thread's record - the memory view holds no name - and whether that is another person than the one whose
        data is loaded now. Where either load names nobody, neither is said."""
        from analyst.notebook import subject_id_of, subject_name_of
        here, threads = subject_id_of(self._data_record(light=True)), {}
        for f in found:
            if f["thread"] not in threads:
                threads[f["thread"]] = self.store.read(f["thread"])
            run = threads[f["thread"]].runs.get(f["run"])
            data = run.data if run is not None else None
            there = subject_id_of(data)
            f["data"] = {**f["data"], "person": subject_name_of(data), "other": bool(here and there and there != here)}

    def _saved_analysis(self, thread, run):
        """A saved analysis whole, for the analyst to read where its brief names it (SHOW SAVED k): what was asked,
        the brief it ran under, the report, and the code and result lines of the cells along its thread up to its
        own (reader.shown), as memory holds it. None when it is saved no more."""
        from analyst import memory, reader
        view = memory.view(self._user_storage())
        hit = next((r for r in view["runs"] if r["thread"] == str(thread) and r["run"] == str(run)), None)
        return reader.shown(view, hit) if hit else None

    def skip_saved(self):
        """The person no longer waits for the saved analyses: the reading in flight ends before its next call."""
        self._skip_saved.set()

    def memory_read(self, question, on_step=None, chain=None, caps=None, brief="", stop=None, on_read=None):
        """What the person's saved analyses hold that bears on a question (analyst/reader.py; docs/ARCHITECT_DESIGN.md
        §3.6). The view is brought up to date and put in a sandbox of its own - a kernel without a frame - and the
        reader's model reads it there, with a second model on pieces, under the reader's caps (`caps` changes
        some). The calls are logged as the memory's, under `chain` (one of its own where none is given) and, for
        the usage rows, the current thread or one minted here; charging them is the caller's. On an executor the
        sandbox takes the place of the thread's kernel, which the next analysis restores from the record. Where
        nothing is saved, no sandbox starts and no model is called. `brief` is the brief being written for the
        question, as text; `stop()` says the person no longer waits; `on_read(read, of)` is told how many runs are
        saved and, as the second model goes, how many it has read. Returns the reader's result."""
        from analyst import memory, reader
        chain = utils.next_chain_id() if chain is None else chain
        if not self.log_and_call_manager.thread_id:
            self.log_and_call_manager.thread_id = str(self.thread_id or utils.next_thread_id())
        view = reader.sandbox_view(memory.refresh(self._user_storage()))
        if on_read:
            on_read(0, len(view["runs"]))
        seat, second = self._memory_seats()
        kernel = None
        try:
            if view["runs"]:
                if self.execution_mode == 'api' and self.executor_api_url:
                    self._drop_kernel()                        # the executor holds one kernel: the thread's gives way knowingly
                kernel = self._new_kernel(frame=False)
            return reader.read(question, view, kernel,
                               lambda system, user, **kw: self._llm(system, user, seat=seat, label="Memory Reader", chain=chain, **kw),
                               lambda system, user: self._llm(system, user, seat=second, label="Memory Pieces", chain=chain), caps=caps, on_step=on_step,
                               brief=brief, stop=stop, on_read=on_read)
        finally:
            try:
                if kernel is not None:
                    kernel.cleanup()
            except Exception:                                  # noqa: BLE001
                pass

    def next_questions(self, thread_id, run_id, level):
        """One set of next questions for a finished analysis, at a level (analyst/next_questions.py): one model call on
        the Pathfinder's seat, logged as the Pathfinder's under a chain of its own - the analysis' chain is settled - and
        charged when it ends, as Save as routine's proposal is. The set is kept with the run. Returns {"set", "at": its
        place among the run's sets}, or None when the run is not a finished analysis on the record; raises
        architect.Failed with the reason to show."""
        from analyst import next_questions
        self.kill_signal = False                     # a run stopped earlier leaves the signal set, and a call would not start
        self._stop_event.clear()
        self._on_thread(thread_id)
        run = self.notebook.runs.get(str(run_id))
        if run is None or run.status != "answered":
            return None
        seat, chain = self._architect_seat(), utils.next_chain_id()
        try:
            asked = next_questions.propose(lambda system, user, **kw: self._llm(system, user, seat=seat, label="Pathfinder", chain=chain, **kw),
                                           self.notebook, run, level, data=self._data_description())
        finally:
            try:
                self.log_and_call_manager.charge_for_completed_query(chain)
            except Exception:                                  # noqa: BLE001
                logger.warning("The next questions' call was not charged", exc_info=True)
        run.next_questions.append({**asked, "chain": chain})
        self.store.save(self.notebook)
        return {"set": run.next_questions[-1], "at": len(run.next_questions) - 1}

    def _architect_look(self, lookups):
        """A round of the Pathfinder's lookups (analyst/lookup.py), answered where the analysis' cells run: one
        host-written script through the executor, over the frame loaded now and the files beside it. It leaves nothing
        behind: no names in the analysis' kernel, no files. One answer to a lookup; where the script did not run,
        each lookup is refused in words."""
        from analyst import lookup
        files = {os.path.basename(p): p for p in (self.auxiliary_datasets or []) if p}
        try:
            _, out, error, _, _ = self.executor.execute(self.output_manager, self.kill_signal, lookup.script(lookups, files),
                                                        self.df, self.df_id, None, persist_df=False, timeout=60)
        except Exception as exc:                               # noqa: BLE001
            out, error = "", str(exc)
        if error:
            logger.warning("The Pathfinder's lookups did not run: %s", str(error).strip().splitlines()[-1][:300] if str(error).strip() else error)
        return lookup.read(out, len(lookups))

    def _on_thread(self, thread_id):
        """The instance on this thread: its record in hand; a kernel that held another thread's names is dropped."""
        self.thread_id = thread_id
        self.log_and_call_manager.thread_id = self.thread_id
        if self.notebook is None or self.notebook.thread_id != str(self.thread_id):
            self.notebook = self.store.load(self.thread_id)
            self._drop_kernel()

    def pd_agent_converse(self, question=None, action=None, thread_id=None, chain_id=None,
                          image=None, auto_explore=False, max_investigations=None, synthesis=False, mode=None, brief=None,
                          run_id=None, candidate=None, step=None, after=None):
        # after: a branch (docs/BRANCH_DESIGN.md) - go on from turn `after` of chain `chain_id`, another way: the question
        # is the person's hint; the branch is a chain of its own beside that one, under its limits, mode and brief
        # brief: what the person agreed before this run (analyst/brief.py); the analyst is held to it (docs/ARCHITECT_DESIGN.md §2.5)
        # run_id: the framing run the brief was written in (open_framing); the analysis continues it, under its id
        # step: the step of that run's conversation on the person's screen when they started it (analyst/steps.py): the
        # analysis runs under the brief that stands there, and what is kept of the conversation is the way to it
        # candidate: (the set, the question) by their places - the next question of the run this one follows that it was
        # started from (analyst/next_questions.py); it is marked there as run
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
        self._on_thread(thread_id if thread_id is not None else utils.next_thread_id())
        self._sync_documents()                       # the thread's documents into the kernel's folder
        if question is None and self.webui:
            # read before anything below can refuse the request: left waiting, it became the next question's text
            question = self.output_manager.get_user_input()
        parent = str(chain_id) if chain_id is not None and str(chain_id) in self.notebook.runs else None
        parent_for_ui = chain_id if parent is not None else None      # the browser's own value, same type
        src, hint, data_now, reran = None, "", None, {}
        if after is not None:
            run_id = candidate = None                          # a branch starts no brief and no proposed question: it takes the chain, the turn, the hint
            hint = (question or "").strip()                    # what the person typed is the hint; the question is the chain's own
            src, data_now = (self.notebook.runs.get(str(chain_id)) if chain_id is not None else None), self._data_record()
            why = self._no_branch(src, after, data_now) or ("" if hint else f"Say how the analysis should go on from turn {after}: a branch needs a hint.")
            if why:
                self.output_manager.display_error(why, chain_id=chain_id)
                return None
            question = src.question
            parent = src.parent                                # the branch stands beside the chain it goes on from
            parent_for_ui = int(parent) if parent and str(parent).isdigit() else parent
            # the kernel at the state the kept turns left, before the new chain is announced: where it cannot get there,
            # nothing has started
            kernel, reran, lost = self._kernel_at(src, after, data_now)
            if lost:
                self.output_manager.display_error(f"The analysis cannot go on from turn {after}: {lost}.", chain_id=chain_id)
                return None
        framed = self.notebook.runs.get(str(run_id)) if run_id is not None else None
        if run_id is not None and (framed is None or framed.status != "framing"):
            # started before (a second tab): not run again, and no run takes its place without the brief
            self.output_manager.display_error("This brief can no longer be started: its analysis has started.", chain_id=run_id)
            return None
        if framed is not None:
            from analyst import brief as briefs, steps
            self.chain_id = int(run_id) if str(run_id).isdigit() else run_id      # the analysis of a framed run keeps the run's id
            if step is not None:
                framed.framing = steps.go(framed.framing, step)                   # ... the step the person started from is the one in use
            brief = brief or briefs.latest(framed.framing)                         # ... and the run is under that brief
            parent = framed.parent                                                 # ... and attaches where the framing run did
            parent_for_ui = int(parent) if parent and parent.isdigit() else parent
        else:
            self.chain_id = utils.next_chain_id()

        if framed is not None:
            question = (brief or {}).get("question") or question      # a framed run is analysed under the question its brief holds, whatever the page sent
        if synthesis:
            question = ("Write the report for the analysis so far on this thread: the answer first, then how it was established, its limitations and next steps. "
                        "The earlier chains' reports are the record, each verified by its own replay: synthesise them, citing [run k]; "
                        "SHOW RUN k - or SHOW RUN 1 2 3 - re-opens them whole where the ledger's line is not enough. Do not re-derive what they established.")
        if not question:
            return None
        if candidate is not None and parent is not None:
            from analyst import next_questions
            next_questions.ran(self.notebook.runs[parent], candidate, self.chain_id)      # kept with the run's first save

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
        if src is not None:
            budget, mode = Budget(**src.budget), (src.mode or mode).lower()      # the limits and the mode of the run it goes on from
        self._last_budget = budget

        logger.info("Analyst run: thread %s, new chain %s, parent %s (%s), preset %s (%d turns)", self.thread_id, self.chain_id, parent,
                    f"a branch of chain {src.id} after turn {after}: the kernel goes back, or a fresh one" if src is not None
                    else "fresh kernel" if (self._kernel is None or parent is None) else "warm kernel" if parent == self._kernel_tip else "the kernel goes back, or a fresh one",
                    mode, budget.turns)
        self._mode_label = {"quick": "Quick", "deep": "Deep", "adaptive": "Adaptive"}.get(mode, mode)
        own = self.notebook.owner(src, after).id if src is not None else None       # the chain that turn is a turn of its own: the map draws the branch from it
        branch = {"of": int(own) if str(own).isdigit() else own, "turn": after, "hint": hint} if src is not None else None
        if src is not None:
            self._carry_drafts(src)                    # the drafts of the brief it runs under, kept under it before it is announced (0331)
        if self.webui:
            # the browser draws the map from this one record: the new chain and where it attached - and, for a branch, the
            # chain and the turn it goes on from
            self.output_manager.send_chain_id(self.thread_id, self.chain_id, self.df_id, parent_chain_id=parent_for_ui,
                                              **({"branch_of": branch["of"], "branch_turn": after} if branch else {}))
            self._pane('pane_run_start', mode=self._mode_label, of=budget.turns, dollars=budget.dollars, **({"branch": branch} if branch else {}))
            # the Data tab, as before (the Query tab is retired: the question is the chain's own text)
            if self.df is not None or self.df_id:
                try:
                    self.output_manager.display_results(chain_id=self.chain_id, execution_mode=self.execution_mode,
                                                        df_id=self.df_id, df=self.df, api_client=self.api_client)
                except Exception:                              # noqa: BLE001
                    logger.warning("Data preview skipped", exc_info=True)

        data_record = data_now if src is not None else self._data_record()   # what this run runs on, kept on the run (2026-10-10, routines)
        if src is None:
            kernel = self._kernel_for(parent, data_record)   # ... and what decides which earlier cells it continues (2026-10-12)
        self._kernel_tip = None                              # the kernel now holds a run that has not ended: stopped or failed, it leaves the kernel at
                                                             # no chain's end, and the next run goes to the state of its own parent (2.9); a run that
                                                             # ends is the kernel's tip
        figure = self._figure_for_analyst(image) if image else None
        session = Session(kernel, self.notebook, self._llm, store=self.store, emit=self._emit,
                          search=self._search,
                          read=self._read, unit_text=self._unit_text, kernel_prelude=self._kernel_prelude(),
                          documents=bool(self._documents_prelude()), context=bool(self._context_prelude()),
                          data_description=self._data_description(), kernel_factory=self._new_kernel,
                          replay_runner=self._run_replay, map_inputs=self._map_inputs, saved=self._saved_analysis)
        try:
            if src is not None:
                run = session.go_on(src.id, after, hint, run_id=str(self.chain_id), data=data_record, reran=reran)
            else:
                run = session.run(question, parent=parent, budget=budget, run_id=str(self.chain_id), data=data_record, image=figure, mode=self._mode_label, brief=brief)
        except ExecutionInterrupted:
            self.output_manager.display_system_messages("Stopped.", chain_id=self.chain_id)
            run = self.notebook.runs.get(str(self.chain_id))
            if run is not None:
                run.status = "stopped"
                self.store.save(self.notebook)
                self._closing_card(run, budget)                # what it kept, and whether it has turns to go on from (2.9)
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
            self._framed.discard(self.chain_id)                # the Pathfinder's calls in this chain were charged with it
            try:
                _run = self.notebook.runs.get(str(self.chain_id)) if self.notebook else None
                if _run is not None and not _run.data:
                    _run.data = data_record
                    self.store.save(self.notebook)
                if _run is not None:
                    self.store.record(self.notebook, _run)      # the usage ledger's line (2026-10-31): the run's facts outlive its thread file
            except Exception:                                  # noqa: BLE001
                logger.warning("The run's data record was not kept", exc_info=True)
        self._kernel_tip = run.id

        # what the reader sees: the tabs the browser already has
        rep = self._replay.pop(run.id, {})
        self._closing_card(run, budget, rep)
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
                kwargs["report_head"] = self._report_head(run, mode)
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
        return None

    def _report_head(self, run, mode=""):
        """The report's head for the page and its export (2026-10-17): the report's title (its first line, the analyst's;
        the page falls back to the question when there is none), the question as the analyst understood it, what data
        the report stands on, the mode, the replay's verdict and the day - what a reader who has never seen the app
        needs at the top of the page."""
        from analyst.routines import data_line
        try:
            data = data_line(run.data or self._data_record(light=True))
        except Exception as exc:                                  # noqa: BLE001
            logger.warning("the report's data line could not be built (%s)", exc)
            data = ""
        from analyst.session import question_line
        # the question the head carries is the analyst's own statement of what it answered (the note's 'Question as understood'),
        # in context: a follow-up's question as typed says nothing outside the thread, and the thread's earlier questions are the
        # trajectory, not the result (Palo, 2026-10-17); the typed question stands in when the note has no such line
        return {"title": run.title or "", "question": question_line(run.note) or run.question or "", "data": data,
                "mode": str(mode or ""), "replay": run.replay_status or "",
                "cells": len(run.cells()), "prepared": time.strftime("%Y-%m-%d")}

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
        self._drop_kernel()
        for chain in list(self._framed):                       # briefs the Pathfinder talked in and no analysis followed: their calls are charged now
            try:
                self.log_and_call_manager.charge_for_completed_query(chain)
            except Exception:                                  # noqa: BLE001
                pass
        self._framed.clear()
        try:
            self.log_and_call_manager.consolidate_logs()
        except Exception:                                      # noqa: BLE001
            pass
