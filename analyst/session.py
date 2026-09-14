"""The analyst session: one model, one kernel, one notebook, one report.

    session = Session(kernel, notebook, llm, store, emit=..., recall=..., search=...)
    run = session.run(question, parent=None, budget=Budget(turns=15, dollars=1.0))

Each turn: build the prompt (contract + data + question + note + cells + task),
call the model, parse ONE action, carry it out, store the turn, emit it to the
UI. On long budgets a self-review is asked for at intervals - the same turn, the same
prompt, marked review=True for the caller (the app runs it on the Reviewer seat when the
config has one, a stronger model at the run's decision points). When the analyst
writes REPORT the session asks for the plain-language REWRITE, runs the two
guards, verifies the assembled script in a fresh kernel, and stores the lot.

`llm(system, user) -> (text, usage)` is whatever model layer the host provides.
"""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Callable, Optional

from . import tools, report as rep
from .notebook import Notebook, NotebookStore, Run, Turn
from .replay import verify

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
CONTRACT = open(os.path.join(_HERE, "contract.md"), encoding="utf-8").read()

REVIEW_LINE = ("SELF-REVIEW TURN: re-read your note against the original question. Say what is "
               "established, what would change the answer, and whether to continue, redirect or REPORT.")
LAST_TURNS_LINE = "The budget is nearly gone: write REPORT with what you have, and say what was not established."
SEARCH_VIEW_CHARS = 4000     # the prompt shows this much of a search digest; the record keeps all (SHOW SEARCH k)

IDEAS_SYSTEM = ("You propose the next questions for a data analysis thread. You know the dataset and the chains so far from the "
                "message. You do not run code and you do not analyse; you write five follow-up questions at the variation level asked, "
                "as a numbered list, each item a short bold title, a colon, and the question - and nothing else around the list.")

REWRITE_TASK = ("Rewrite the technical report below for an intelligent reader who has never studied statistics and "
                "does not know this dataset: the answer first in everyday words, then what it depends on and what it "
                "does not mean, then how it was checked, then what to do next. Explain each idea the first time it "
                "appears. No column names, no method jargon (say 'compared the same person at the same heart rate', "
                "not 'within-subject HR-matched'), no bracketed intervals - give ranges in words ('somewhere between "
                "4% and 11%'). Keep every number that matters and change none; drop the rest. Use short markdown "
                "headings and short paragraphs; about two-thirds the length of the original. Say what you mean in "
                "direct statements: when a literal phrase is available, use it, and never let a metaphor or a flourish "
                "stand in for a statement ('this still matters', not 'this earns its keep'; 'a parameter worth varying', "
                "not 'a dial worth turning'). Reply with the text only.\n\n")

_ACTION_RE = re.compile(r"###ACTION###\s*\n(.*)\Z", re.S)
_NOTE_RE = re.compile(r"###NOTE###\s*\n(.*?)\n###ACTION###", re.S)
_CODE_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.S)


def _estimate_line(note: str) -> str:
    """The note's 'Best estimate so far' content, for the pane's strip."""
    for ln in (note or "").splitlines():
        s = ln.strip().lstrip("-• ").strip()
        if s.lower().startswith("best estimate so far"):
            return s.split(":", 1)[1].strip() if ":" in s else ""
    return ""


@dataclass
class Budget:
    turns: int = 15
    dollars: float = 2.0
    review_every: int = 0       # 0 = no self-review turns; long budgets use 8
    max_failures: int = 5       # consecutive failed cells before the session forces the report
    searches: int = 4           # web searches per run; beyond it SEARCH answers with what is already on hand

    @staticmethod
    def preset(name: str) -> "Budget":
        return {"quick": Budget(turns=5, dollars=0.3),
                "deep": Budget(turns=15, dollars=1.5),
                "adaptive": Budget(turns=50, dollars=4.0, review_every=8)}[name]


@dataclass
class Action:
    verb: str          # cell | show | names | recall | search | ask | report | invalid
    arg: str = ""      # code, cell number, query, question or the report text


def parse_turn(text: str) -> tuple[str, str, Action]:
    """(thinking, note, action). Tolerant: a missing NOTE keeps the previous
    note; a missing or unknown ACTION is 'invalid' and the model is told so."""
    text = text or ""
    if not text.strip():
        return "", "", Action("invalid", "empty reply")
    m_note = _NOTE_RE.search(text)
    note = m_note.group(1).strip() if m_note else ""
    thinking = text[:text.find("###NOTE###")].strip() if "###NOTE###" in text else ""
    thinking = re.sub(r"^###THINKING###\s*", "", thinking).strip()
    m_act = _ACTION_RE.search(text)
    if not m_act:
        return thinking, note, Action("invalid", "no ###ACTION### block")
    body = m_act.group(1).strip()
    head, _, rest = body.partition("\n")
    verb = head.strip().split()[0].lower() if head.strip() else ""
    arg = head.strip()[len(verb):].strip()
    if verb == "cell":
        m = _CODE_RE.search(body)
        return thinking, note, Action("cell", m.group(1).rstrip() if m else "") if m else Action("invalid", "CELL without a python block")
    if verb == "show":
        return thinking, note, Action("show", arg or rest.strip().split()[0] if rest.strip() else arg)
    if verb in ("names",):
        return thinking, note, Action("names")
    if verb in ("recall", "search", "ask"):
        return thinking, note, Action(verb, (arg + "\n" + rest).strip() if rest.strip() else arg)
    if verb == "report":
        return thinking, note, Action("report", rest.strip())
    return thinking, note, Action("invalid", f"unknown action {head.strip()[:40]!r}")


class Session:
    def __init__(self, kernel, notebook: Notebook, llm: Callable, store: Optional[NotebookStore] = None,
                 emit: Optional[Callable[[dict], None]] = None, recall: Optional[Callable] = None,
                 search: Optional[Callable] = None, data_description: str = "",
                 kernel_factory: Optional[Callable[[], object]] = None,
                 replay_runner: Optional[Callable] = None):
        self.kernel = kernel
        self.nb = notebook
        self.llm = llm            # llm(system, user, **hints) -> (text, usage); hints: review=True on a self-review turn, rewrite=True on the plain-language rewrite
        self.store = store
        self.emit = emit or (lambda ev: None)
        self.recall = recall
        self.search = search
        self.data_description = data_description or "(no dataset attached)"
        self.kernel_factory = kernel_factory
        self.replay_runner = replay_runner      # (run, script) -> (stdout, error); the host may also collect figures

    # ----- the prompt --------------------------------------------------------
    @staticmethod
    def is_review(budget: Budget, turn_no: int) -> bool:
        """A self-review turn: never the first; every review_every turns after it (turns 9, 17, 25... for 8)."""
        return bool(budget.review_every) and turn_no > 1 and (turn_no - 1) % budget.review_every == 0

    def _user_prompt(self, run: Run, budget: Budget, turn_no: int, spent: float, extra: str = "", review: bool = False,
                     everything: bool = False) -> str:
        left = budget.turns - turn_no
        last = (left <= 1 and turn_no > 1) or spent >= 0.9 * budget.dollars      # never on the first turn: even a tiny budget gets one cell
        # the report turn sees everything (2026-09-10): once the session forces the report there is no turn left to
        # SHOW a cell, and a result the report cannot see does not exist for the reader
        everything = everything or last
        parts = []
        anc = self.nb.render_ancestry(run.id)
        if anc:
            parts.append(anc)
        parts.append(f"DATA:\n{self.data_description}")
        parts.append(f"QUESTION:\n{run.question.strip()}")
        parts.append(f"YOUR NOTE (as you last wrote it):\n{run.note or '(none yet - write it this turn)'}")
        parts.append("CELLS SO FAR:\n" + self.nb.render_cells(run.id, everything=everything))
        if extra:
            parts.append(extra)
        task = f"TASK: turn {turn_no} of {budget.turns} ({left} left); spent ${spent:.2f} of ${budget.dollars:.2f}."
        if review:
            task += "\n" + REVIEW_LINE
        if last:
            task += "\n" + LAST_TURNS_LINE
        parts.append(task)
        return "\n\n".join(parts)

    # ----- the loop ----------------------------------------------------------
    # ---- ideas: five next questions, one model call, no cells (2026-09-08) ----
    IDEAS_LEVELS = {1: "refine the focus - scope, granularity or a parameter within the same enquiry",
                    2: "shift the angle - the same subject from a different perspective or framework",
                    3: "test the boundaries - what happens at the edges of the current assumptions",
                    4: "blend two elements already in the thread in a new way",
                    5: "follow what emerged unexpectedly in the investigation"}

    @staticmethod
    def _ideas_list(text: str) -> str:
        """The five items and nothing else: whatever the model wrapped around them (a reply in the
        contract's three-section form, an opening paragraph, a closing remark) is dropped."""
        text = text or ""
        if "###ACTION###" in text:                                  # the analyst's format slipped in
            text = text.split("###ACTION###", 1)[1]
            text = re.sub(r"^\s*REPORT\s*", "", text)
        items, cur = [], None
        for line in text.splitlines():
            m = re.match(r"^\s*(\d+)[.)]\s+(.*)$", line)
            if m:
                if cur: items.append(cur)
                cur = m.group(2).strip()
            elif cur is not None and line.strip():
                cur += " " + line.strip()
            elif cur is not None and not line.strip():
                items.append(cur); cur = None
        if cur: items.append(cur)
        items = [i for i in items if i][:5]
        return "\n".join(f"{n}. {i}" for n, i in enumerate(items, 1))

    def ideas(self, level: int, parent: Optional[str] = None, run_id: Optional[str] = None, question: str = "") -> Run:
        """Five follow-up questions one step from the thread, at the asked variation level.
        A single model call over the thread's ledger and the data description: no cells,
        no replay, no rewrite. The run is recorded like any other, so the map shows it."""
        level = max(1, min(5, int(level or 3)))
        run = self.nb.new_run(question or f"User requested variations of the enquiry (level {level})", parent, run_id=run_id)
        self._save()
        self.emit({"type": "turn_start", "run": run.id, "turn": 1, "of": 1})
        t0 = time.time()
        ledger = self.nb.render_ancestry(run.id) if parent else ""
        prompt = (f"DATA:\n{self.data_description}\n\n" + (ledger + "\n\n" if ledger else "") +
                  "TASK: Propose five follow-up questions for this thread, all at variation level " + str(level) + ": " + self.IDEAS_LEVELS[level] + ".\n"
                  "Each is ONE step from where the thread is now: built from elements already present in the chains and the data, "
                  "answerable with this dataset, specific enough to run as the next chain. Prefer subtle over dramatic; small shifts reveal large insights.\n"
                  "Reply with the five as a numbered list and NOTHING else - no introduction, no closing remark, no headings, no notes. "
                  "Each item: **a short title** then a colon and the question in one or two sentences. Plain text; no LaTeX.")
        text, usage = self.llm(IDEAS_SYSTEM, prompt)
        text = self._ideas_list(text)
        cost = (usage or {}).get("cost", 0.0)
        self.emit({"type": "turn_end", "run": run.id, "turn": 1, "kind": "ideas", "thinking": "", "note": "", "code": "",
                   "elapsed": round(time.time() - t0, 1), "cost": cost})
        run.turns.append(Turn(kind="ideas", text=text, usage=dict(usage or {}),
                              note="- Question as understood: five next questions for the thread\n- Names: (no cells; the kernel is untouched)"))
        run.report = text if text else "(no ideas returned)"
        run.status = "answered" if text else "failed"
        self._save()
        self.emit({"type": "run_end", "run": run.id, "status": run.status})
        return run

    def run(self, question: str, parent: Optional[str] = None, budget: Budget = Budget(),
            run_id: Optional[str] = None) -> Run:
        run = self.nb.new_run(question, parent, run_id=run_id)
        self._save()
        spent, extra, failures = 0.0, "", 0
        for turn_no in range(1, budget.turns + 1):
            review = self.is_review(budget, turn_no)
            self.emit({"type": "turn_start", "run": run.id, "turn": turn_no, "of": budget.turns, "review": review})
            t0 = time.time()
            text, usage = self.llm(CONTRACT, self._user_prompt(run, budget, turn_no, spent, extra, review=review), review=review)
            usage = dict(usage or {})
            usage["elapsed"] = round(time.time() - t0, 1)
            spent += float(usage.get("cost", 0.0) or 0.0)
            thinking, note, action = parse_turn(text)
            note = note or run.note
            extra = ""
            turn = Turn(kind=action.verb, note=note, thinking=thinking, usage=usage)
            self.emit({"type": "turn_end", "run": run.id, "turn": turn_no, "kind": action.verb,
                       "thinking": thinking, "note": note, "code": action.arg if action.verb == "cell" else "",
                       "elapsed": usage.get("elapsed"), "cost": usage.get("cost", 0.0),
                       "estimate": _estimate_line(note)})

            if action.verb == "cell":
                turn.code = action.arg
                t_cell = time.time()
                self.emit({"type": "cell_start", "run": run.id, "turn": turn_no})   # the executor is busy from here (2026-09-08)
                out, err, figs = tools.run_cell(self.kernel, action.arg)
                turn.elapsed = round(time.time() - t_cell, 1)
                turn.stdout, turn.error, turn.figures = out, err, figs
                if not err:
                    turn.cell_no = self.nb.next_cell_no(run.id)
                    failures = 0
                else:
                    failures += 1
                    tools.rebind_aliases(self.kernel)          # a rollback on an older kernel loses pd/np/plt
                    extra = ("YOUR LAST CELL FAILED - it was rolled back, nothing it defined persists:\n"
                             f"```python\n{action.arg.rstrip()}\n```\nERROR:\n{tools.condense_error(err, code=action.arg)}")
                    if failures >= 2:
                        extra += (f"\n\n{failures} attempts in a row have failed. Before another full attempt, look "
                                  "before computing: NAMES, SHOW an earlier cell, or a small cell that prints the "
                                  "type and shape of what you are about to use.")
                    if budget.max_failures and failures >= budget.max_failures:
                        # five in a row is a model looping, not analysing: close with what stands
                        logger.warning("Analyst: %d consecutive failed cells; forcing the report", failures)
                        run.turns.append(turn)
                        self._emit_turn(run, turn)
                        self.emit({"type": "heartbeat", "run": run.id, "turn": turn_no, "of": budget.turns, "spent": spent,
                                   "dollars": budget.dollars, "estimate": _estimate_line(run.note)})
                        self._save()
                        halt = (f"STOP: {failures} cells in a row have failed and the analysis could not get past this error. "
                                "Write REPORT now with what stands: what was established before the failures, what the failing "
                                "step was meant to add, and what remains unestablished.")
                        text, usage = self.llm(CONTRACT, self._user_prompt(run, budget, turn_no, spent, halt + "\n\n" + extra, everything=True))
                        spent += float((usage or {}).get("cost", 0.0) or 0.0)
                        _, note, action = parse_turn(text)
                        body = action.arg if action.verb == "report" else (text or "")
                        self.emit({"type": "turn_end", "run": run.id, "turn": turn_no + 1, "kind": "report", "thinking": "",
                                   "note": note or run.note, "code": "", "elapsed": (usage or {}).get("elapsed"), "cost": (usage or {}).get("cost", 0.0)})
                        rturn = Turn(kind="report", note=note or run.note, text=body, usage=dict(usage or {}))
                        run.turns.append(rturn)
                        self._emit_turn(run, rturn)
                        self._finish(run, body, budget, spent)
                        return run
            elif action.verb == "show":
                arg = str(action.arg).strip()
                m_run = re.match(r"(?i)^run\s+(\d+)$", arg)
                m_srch = re.match(r"(?i)^search\s+(\d+)$", arg)
                if m_run:
                    turn.stdout = self.nb.render_run(run.id, int(m_run.group(1)))
                elif m_srch:
                    turn.stdout = self.nb.render_search(run.id, int(m_srch.group(1)))
                else:
                    # several cells at once (2026-09-10): SHOW 8 9 - a report needs its numbers in view in one turn
                    views = []
                    for num in (re.findall(r"\d+", arg) or [arg]):
                        try:
                            cell = self.nb.cell(run.id, int(num))
                        except ValueError:
                            cell = None
                        views.append(f"--- cell {cell.cell_no} (re-opened) ---\n```python\n{cell.code}\n```\nOUTPUT:\n{cell.stdout}"
                                     if cell else f"(no cell {num}; SHOW takes cell numbers, RUN k or SEARCH k)")
                    turn.stdout = "\n\n".join(views)
                extra = "SHOWN:\n" + turn.stdout
            elif action.verb == "names":
                turn.stdout = tools.names(self.kernel)
                extra = "NAMES IN THE KERNEL:\n" + turn.stdout
            elif action.verb == "recall":
                turn.stdout = tools.recall(self.recall, action.arg)
                extra = f"RECALLED ({action.arg}):\n" + turn.stdout
            elif action.verb == "search":
                turn.text = action.arg                          # the query, so SHOW SEARCH k can name it
                done = sum(1 for t in run.turns if t.kind == "search" and t.stdout and not t.stdout.startswith("(search budget"))
                if budget.searches and done >= budget.searches:
                    turn.stdout = (f"(search budget for this run used: {done} of {budget.searches}. Work with what the earlier "
                                   f"searches returned - SHOW SEARCH k re-opens any of them whole - or state plainly what was not found.)")
                    extra = f"SEARCH ({action.arg}):\n" + turn.stdout
                else:
                    turn.stdout = tools.search(self.search, action.arg)
                    shown = turn.stdout
                    k = len(self.nb.searches(run.id)) + 1          # this search's number once recorded
                    if len(shown) > SEARCH_VIEW_CHARS:
                        shown = shown[:SEARCH_VIEW_CHARS].rstrip() + f"\n... [{len(turn.stdout) - SEARCH_VIEW_CHARS} more characters; SHOW SEARCH {k} for all]"
                    left = budget.searches - done - 1 if budget.searches else None
                    extra = f"SEARCH ({action.arg}):\n" + shown + (f"\n(searches left in this run: {left})" if left is not None else "")
            elif action.verb == "ask":
                turn.text = action.arg
                run.turns.append(turn)
                run.status = "asked"
                tools.ask_user(self.emit, action.arg)
                self._emit_turn(run, turn)
                self._save()
                return run
            elif action.verb == "report":
                turn.text = action.arg
                run.turns.append(turn)
                self._emit_turn(run, turn)
                self._finish(run, action.arg, budget, spent)
                return run
            else:
                turn.kind = "error"
                if action.arg == "empty reply":
                    logger.warning("Analyst turn %d: the model returned an empty reply (%s completion tokens billed) - re-asking",
                                   turn_no, usage.get("completion_tokens", "?"))
                    turn.stdout = "Your last reply arrived empty - no text reached the workspace. Reply again, in the turn format."
                else:
                    logger.warning("Analyst turn %d: malformed reply (%s): %r", turn_no, action.arg, (text or "")[:200])
                    turn.stdout = f"Your last reply had no valid action ({action.arg}). Reply in the exact turn format."
                extra = turn.stdout

            run.turns.append(turn)
            self._emit_turn(run, turn)
            self.emit({"type": "heartbeat", "run": run.id, "turn": turn_no, "of": budget.turns, "spent": spent,
                       "dollars": budget.dollars, "estimate": _estimate_line(run.note)})
            self._save()

        # budget exhausted without a report: ask for it once
        text, usage = self.llm(CONTRACT, self._user_prompt(run, budget, budget.turns, spent, LAST_TURNS_LINE + "\nWrite REPORT now.", everything=True))
        spent += float((usage or {}).get("cost", 0.0) or 0.0)
        _, note, action = parse_turn(text)
        body = action.arg if action.verb == "report" else (text or "")
        self.emit({"type": "turn_end", "run": run.id, "turn": budget.turns + 1, "kind": "report", "thinking": "",
                   "note": note or run.note, "code": "", "elapsed": (usage or {}).get("elapsed"), "cost": (usage or {}).get("cost", 0.0)})
        turn = Turn(kind="report", note=note or run.note, text=body, usage=dict(usage or {}))
        run.turns.append(turn)
        self._emit_turn(run, turn)
        self._finish(run, body, budget, spent)
        return run

    # ----- the ending: rewrite, guards, replay ------------------------------
    def _finish(self, run: Run, report_text: str, budget: Budget, spent: float) -> None:
        cells = self.nb.path_cells(run.id)
        report_text = rep.repair_markdown_tables(report_text)
        # a number is verified if a cell printed it - or if it is a constant of the analysis
        # itself (a filter bound, a bin edge) that appears in a cell's code
        check = rep.guard_technical(report_text, [c.stdout for c in cells] + [c.code for c in cells])
        run.report = report_text + (f"\n\n> {check}" if check else "")
        # the plain-language rewrite by the same analyst
        self.emit({"type": "turn_start", "run": run.id, "turn": "rewrite", "of": budget.turns, "rewrite": True})
        t_rw = time.time()
        text, usage = self.llm(CONTRACT, REWRITE_TASK + report_text, rewrite=True)   # the app runs it on the Rewriter seat when the config has one (2026-09-11)
        self.emit({"type": "turn_end", "run": run.id, "turn": "rewrite", "kind": "rewrite", "thinking": "", "note": "", "code": "",
                   "elapsed": round(time.time() - t_rw, 1), "cost": (usage or {}).get("cost", 0.0)})
        rewrite = (text or "").strip()
        rewrite = re.sub(r"^###.*?###\s*", "", rewrite, flags=re.S).strip()
        check2 = rep.guard_rewrite(rewrite, report_text)
        run.rewrite = rewrite + (f"\n\n> {check2}" if check2 else "")
        run.turns.append(Turn(kind="rewrite", note=run.note, text=run.rewrite, usage=dict(usage or {})))
        # the replay: the host's runner when it has one (the app's executor, which also
        # yields the figures and the results text), else a fresh kernel
        if run.cells() and (self.replay_runner is not None or self.kernel_factory is not None):
            try:
                if self.replay_runner is not None:
                    from .replay import assemble, compare
                    script, order = assemble(cells, report_text, own=run.cells())
                    stdout, err = self.replay_runner(run, script)
                    status, line = compare(cells, report_text, stdout or "", err or "", len(order))
                else:
                    status, line, script = verify(self.kernel_factory, cells, report_text)
            except Exception as exc:                          # noqa: BLE001
                status, line, script = "failed", f"Replay could not run: {exc}", ""
            run.replay_status, run.replay_script = status, script
            run.report += f"\n\n> {line}"
        run.status = "answered"
        self.emit({"type": "report", "run": run.id, "text": run.report})
        self.emit({"type": "rewrite", "run": run.id, "text": run.rewrite})
        if run.replay_status:
            self.emit({"type": "replay_status", "run": run.id, "status": run.replay_status, "script": run.replay_script})
        self._save()

    # ----- plumbing ------------------------------------------------------------
    def _emit_turn(self, run: Run, turn: Turn) -> None:
        ev = {"type": turn.kind, "run": run.id, "note": turn.note}
        if turn.kind == "cell":
            ev.update(code=turn.code, stdout=turn.stdout, error=turn.error, cell_no=turn.cell_no, figures=turn.figures)
        elif turn.text:
            ev["text"] = turn.text
        elif turn.stdout:
            ev["text"] = turn.stdout
        self.emit(ev)

    def _save(self) -> None:
        if self.store is not None:
            self.store.save(self.nb)
