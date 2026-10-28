"""The notebook: one tree of runs per thread, each run a sequence of turns.

A RUN is one user question and everything the analyst did to answer it. Runs
have parents, so a thread is a tree; the context for a run is the path from the
root to its parent. A TURN is one action inside a run - a cell, a shown cell, a
search, a recall, a question to the user, the report, the rewrite - together
with the note as the analyst rewrote it that turn.

Cells are numbered along the path (1, 2, 3 ...) so the analyst and the report
can refer to them; the numbering restarts only at the root.

The path is the conversation; the COMPUTATION is the part of it that ran on the
run's data (2026-10-12). The data loaded can change between a chain and its
follow-up - a routine's run loads another window, a file is replaced - and the
earlier chains' cells and names then belong to data that is no longer there:
they stay in the ledger as context, marked as on other data, and the kernel,
the replay, the figures step and a routine are made from the cells computed on
the data the run itself ran on (`computed_cells`).

Persistence is one JSON file per thread, rewritten after every turn.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field, fields, asdict
from typing import Dict, List, Optional


def _now() -> float:
    return time.time()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def step_sentence(thinking: str, width: int = 110) -> str:
    """The analyst's account of the step: its STEP section from the second sentence on - the first, by the contract's
    order, says what the last output showed - cut at a word to `width`. A one-sentence STEP is the step itself."""
    text = " ".join((thinking or "").split())
    if not text:
        return ""
    sents = split_sentences(text)
    body = " ".join(sents[1:]) if len(sents) > 1 else text
    return body if len(body) <= width else body[:width].rsplit(" ", 1)[0].rstrip(",;:") + "..."


_ABBREV_RE = re.compile(r"(?:\b(?:e\.g|i\.e|vs|cf|etc|approx|ca|no|fig|figs|eq|ref|dr|mr|ms|st)|\b[A-Z]|\(\w)\.$", re.I)


def split_sentences(text: str) -> List[str]:
    """Sentences of a prose text: split after . ! ? and whitespace, except after an abbreviation ("i.e.", "e.g.", "vs.",
    an initial) - 2026-10-06: "(e.g. Jan Meda" and "i.e. it is venue" had been read as sentence ends."""
    parts = re.split(r"(?<=[.!?])\s+", text)
    out: List[str] = []
    for p in parts:
        if out and (_ABBREV_RE.search(out[-1]) or len(out[-1]) < 4):
            out[-1] = out[-1] + " " + p
        else:
            out.append(p)
    return out


def data_signature(d: Optional[dict]) -> str:
    """A data record's identity by content, for the same frame loaded again under another id (2026-10-12: an upload
    gets a fresh id every time, so the same file in a new session is a new frame to the cache): the name, the rows,
    the columns' names, the period, the loader's details (metrics, activities, the race, the athletes). "" when
    the record has no rows or columns to go by."""
    d = d or {}
    cols = [str(c.get("name")) for c in (d.get("columns") or []) if isinstance(c, dict)]
    if d.get("rows") is None or not cols:
        return ""
    extra = d.get("extra") or {}
    return "|".join([str(d.get("name") or ""), str(d.get("rows")), ",".join(cols), str(d.get("date_range") or ""),
                     json.dumps({k: extra[k] for k in sorted(extra)}, sort_keys=True, default=str) if extra else ""])


def same_data(a: Optional[dict], b: Optional[dict]) -> bool:
    """Whether two data records are the same data: the same frame (its id), or the same content (data_signature).
    A record without a frame id is never the same as another - the callers decide what no record means."""
    ka, kb = str((a or {}).get("df_id") or ""), str((b or {}).get("df_id") or "")
    if not ka or not kb:
        return False
    if ka == kb:
        return True
    sa = data_signature(a)
    return bool(sa) and sa == data_signature(b)


def purpose_of(turn: "Turn", width: int = 110) -> str:
    """What a cell was for: the analyst's account of the step; without one, the code's first comment, else its first
    working statement (not an import, not an option setting)."""
    what = step_sentence(turn.thinking, width)
    if what:
        return what
    lines = [ln.strip() for ln in (turn.code or "").splitlines() if ln.strip()]
    comment = next((ln.lstrip("# ").strip() for ln in lines if ln.startswith("#") and ln.lstrip("# ").strip()), "")
    if comment:
        return comment[:width]
    boiler = re.compile(r"^(import |from |pd\.set_option|plt\.rcParams|warnings\.|%)")
    return next((ln for ln in lines if not ln.startswith("#") and not boiler.match(ln)), lines[0] if lines else "")[:width]


@dataclass
class Turn:
    kind: str                       # cell | show | names | recall | search | read | ask | report | rewrite | review | error
    note: str = ""                  # the note as rewritten this turn
    thinking: str = ""              # free text before the note, if any
    code: str = ""                  # CELL: the code that ran
    stdout: str = ""                # CELL/SHOW/NAMES/RECALL/SEARCH/READ: what came back
    error: str = ""                 # CELL: traceback, if the cell failed
    figures: List[dict] = field(default_factory=list)   # CELL: plot payloads returned by the kernel
    results: List[dict] = field(default_factory=list)   # CELL: the RESULT(...) records the kernel kept (text, typed, test, corrects, line)
    registry: dict = field(default_factory=dict)   # CELL: the kernel's {name: {type, desc}} for the names this cell made or changed (the code map, 2026-10-20)
    reaches: List[dict] = field(default_factory=list)   # CELL: what the cell touched outside the data, each marked asked (analyst/reach.py, 2026-10-28)
    refused: str = ""               # CELL: the restricted word the executor refused the cell for; it did not run and this is not an error of the code (2026-10-28)
    cell_no: Optional[int] = None   # CELL: its number along the path (only committed cells get one)
    text: str = ""                  # ask/report/rewrite: the analyst's text
    usage: dict = field(default_factory=dict)            # tokens, cost, elapsed for the model call
    shown: List[int] = field(default_factory=list)       # REVIEW: the cells handed to this review, code and output
    checked: List[dict] = field(default_factory=list)    # REVIEW: the verification ledger entries it wrote ({cell, text})
    recheck: List[int] = field(default_factory=list)     # REVIEW: cells it asked to see again at the next review
    elapsed: float = 0.0            # CELL: seconds the kernel took to run it
    step: str = ""                  # "figures" for the cells of the figures step after the report (2026-10-11); "" for a turn of the analysis
    created: float = field(default_factory=_now)


@dataclass
class Run:
    id: str
    parent: Optional[str]
    question: str
    turns: List[Turn] = field(default_factory=list)
    report: str = ""                # the technical report (final)
    rewrite: str = ""               # the simplified rewrite (final)
    title: str = ""                 # the report's title (2026-10-17): its first line, a statement of what was found, for the Answer tab and the export
    replay_status: str = ""         # reproduced | differed | failed | (empty = not run)
    replay_script: str = ""
    status: str = "running"         # running | answered | asked | stopped | failed
    created: float = field(default_factory=_now)
    data: dict = field(default_factory=dict)   # what the run ran on (df_id, name, source, columns, rows, aux): a routine made from it later needs it (2026-10-10)
    mode: str = ""                  # the budget preset the run was asked in: Quick, Deep or Adaptive (2026-10-20, the code map's header)
    code_map: dict = field(default_factory=dict)   # the code map built when the chain ended (analyst/codemap; 2026-10-20), or {"error": ...}
    sandbox: dict = field(default_factory=dict)   # the box the kernel ran on, as it saw itself (kernel.sandbox_facts; 2026-10-28); {} when the executor did not say

    @property
    def note(self) -> str:
        """The analyst's note as it last wrote it. A review turn's note is the review's lines (the pane's card and the
        REVIEW block read it there), never the analyst's: skipped (2026-10-19: after each review the analyst had been
        handed the review as YOUR NOTE, beside the REVIEW block, and lost its own)."""
        for t in reversed(self.turns):
            if t.note and t.kind != "review":
                return t.note
        return ""

    def cells(self) -> List[Turn]:
        return [t for t in self.turns if t.kind == "cell" and t.cell_no is not None]


class Notebook:
    """All runs of one thread, as a tree."""

    def __init__(self, thread_id: str, runs: Optional[Dict[str, Run]] = None):
        self.thread_id = str(thread_id)
        self.runs: Dict[str, Run] = runs or {}

    # ----- structure -----------------------------------------------------
    def new_run(self, question: str, parent: Optional[str] = None, run_id: Optional[str] = None) -> Run:
        if parent is not None and parent not in self.runs:
            raise KeyError(f"parent run {parent!r} not in thread {self.thread_id}")
        run = Run(id=str(run_id) if run_id else new_id(), parent=parent, question=question)
        self.runs[run.id] = run
        return run

    def path(self, run_id: str) -> List[Run]:
        """Root -> run, inclusive. The context of a run is this path."""
        out, cur, seen = [], self.runs.get(run_id), set()
        while cur is not None and cur.id not in seen:
            out.append(cur)
            seen.add(cur.id)
            cur = self.runs.get(cur.parent) if cur.parent else None
        return list(reversed(out))

    def path_cells(self, run_id: str) -> List[Turn]:
        """Every committed cell along the path, in execution order."""
        cells: List[Turn] = []
        for run in self.path(run_id):
            cells.extend(run.cells())
        return cells

    # ----- the computation: the part of the path that ran on the run's data (2026-10-12) -----
    @staticmethod
    def data_key(run: "Run") -> str:
        """The identity of the data a run ran on - its frame's id; "" when the run predates the record (2026-10-10)."""
        return str((run.data or {}).get("df_id") or "")

    def computed_runs(self, run_id: str, data: Optional[dict] = None) -> List["Run"]:
        """The runs of the path whose cells were computed on the run's data: from the last change of data onward -
        the same data being the same frame or the same content (same_data: the same file uploaded again in a new
        session is the same data). An earlier run without a data record counts as on the same data (there was no
        record before 2026-10-10); the run itself without one ran with no data loaded, so the earlier chains that
        had data are on other data. `data` is the record of a run that is not on the record yet - a follow-up about
        to start on the data loaded now."""
        path = self.path(run_id)
        ref = dict(data or {}) if data is not None else dict((path[-1].data or {}) if path else {})
        out: List[Run] = []
        for run in reversed(path):
            if self.data_key(run) and not same_data(run.data, ref):
                break
            out.append(run)
        return list(reversed(out))

    def computed_cells(self, run_id: str, data: Optional[dict] = None) -> List[Turn]:
        """The committed cells computed on the run's data, in execution order: what the kernel holds, what the replay
        re-runs, what a routine is made from. `path_cells` is the whole path - the record, for numbering and SHOW n."""
        cells: List[Turn] = []
        for run in self.computed_runs(run_id, data):
            cells.extend(run.cells())
        return cells

    def earlier_on_other_data(self, run_id: str) -> List["Run"]:
        """The runs of the path before the last change of data: in the ledger, but not in the kernel."""
        computed = {r.id for r in self.computed_runs(run_id)}
        return [r for r in self.path(run_id) if r.id not in computed]

    @staticmethod
    def data_words(run: "Run") -> str:
        """A run's data in a few words, for the ledger: the file or the source, the period, the rows; the frame's id
        when the record has nothing else; "" without a record."""
        d = run.data or {}
        rows = d.get("rows")
        parts = [str(d.get("name") or d.get("source") or "").strip(), str(d.get("date_range") or "").strip(),
                 (f"{int(rows):,} rows" if isinstance(rows, (int, float)) and rows else "")]
        words = ", ".join(p for p in parts if p and p != "none")
        return words or (f"frame {str(d.get('df_id'))[:12]}" if d.get("df_id") else "")

    def other_data_line(self, run: "Run") -> str:
        """The ledger's line under a chain that ran on data no longer loaded: its numbers are that data's; its cells are
        not in the kernel; the record still opens them."""
        what = self.data_words(run)
        nos = [c.cell_no for c in run.cells() if c.cell_no is not None]
        cells = (f"its cells {nos[0]}-{nos[-1]} are" if len(nos) > 1 else f"its cell {nos[0]} is") if nos else ""
        head = f"On other data ({what}): " if what else "On other data (not on record): "
        return head + "its numbers are that data's" + (f"; {cells} not in the kernel (SHOW n re-opens one from the record)" if cells else "")

    def next_cell_no(self, run_id: str) -> int:
        cells = self.path_cells(run_id)
        return (cells[-1].cell_no + 1) if cells else 1

    def cell(self, run_id: str, cell_no: int) -> Optional[Turn]:
        for t in self.path_cells(run_id):
            if t.cell_no == cell_no:
                return t
        return None

    def tree(self) -> List[dict]:
        """The workflow map: one node per run."""
        return [{"id": r.id, "parent": r.parent, "question": r.question, "status": r.status,
                 "cells": len(r.cells()), "created": r.created} for r in self.runs.values()]

    # ----- rendering for the analyst's context ----------------------------
    @staticmethod
    def headline(turn: Turn, width: int = 240) -> str:
        """One line for a collapsed cell: its number, what it was for, and what came out. What it was for is the
        analyst's own account of the step - its STEP section from the second sentence on (the first, by the contract's
        order, is what the last output showed) - and only without one the code's first comment or first working
        statement (2026-10-06: "import pandas as pd" had stood for three cells of five). What came out is a printed
        fact: the first RESULT line the kernel recorded, else the first printed line; for a failed attempt, the error.
        A summary with a handle: SHOW n opens the whole cell."""
        what = purpose_of(turn)
        if turn.error:
            from .tools import exception_line
            out = "ERROR: " + exception_line(turn.error)[:90]
        elif turn.results:
            out = "RESULT: " + turn.results[0].get("text", "")[:110]
        else:
            out = next((ln.strip() for ln in (turn.stdout or "").splitlines() if ln.strip()), "")[:90]
        line = f"[cell {turn.cell_no}] {what}  ->  {out}"
        return line[:width]

    REPORT_VIEW_CHARS = 160_000   # the report turn's total for outputs (~40k tokens); only a pathological print reaches it
    CAP_SLACK = 160               # an earlier recent cell's output within this of its cap is not cut: the cut line itself is some 50 characters

    def render_cells(self, run_id: str, recent: int = 4, full_chars: int = 3000, everything: bool = False) -> str:
        """Recent cells in full, older ones as one line each. The prompt does
        not grow with the run: `recent` bounds the full part. Failed attempts
        of this run are listed too, one line each, so the analyst can see its
        own history of errors.

        everything=True is the report turn (2026-09-10): when the session forces
        the report there is no turn left to SHOW anything, so every cell's output
        rides whole - a result the report cannot see does not exist for the
        reader. No per-cell cap; one total cap, REPORT_VIEW_CHARS, and if a run
        exceeds it the largest outputs lose their middles, marked, never a cell."""
        if everything:
            return self._render_everything(run_id)
        cells = self.computed_cells(run_id)          # the cells in the kernel: the earlier chains' on other data are not (2026-10-12)
        run = self.runs.get(run_id)
        failed_lines = self.failed_attempts(run) if run else ""
        if not cells:
            return "(no cells yet)" + failed_lines
        older, latest = cells[:-recent] if recent else cells, cells[-recent:] if recent else []
        parts = []
        if older:
            parts.append("OLDER CELLS (one line each; SHOW <n> re-opens one):")
            parts.extend(self.headline(t) for t in older)
        for k, t in enumerate(latest):
            is_last = (k == len(latest) - 1)
            out = (t.stdout or "")
            cap = None if is_last else min(full_chars, 1500)      # the newest output rides whole; the decision turns on it
            # an output a line or two over the cap rides whole: the cut line is longer than what it would save (2026-10-16,
            # a live run's prompt read "... [2 more characters; SHOW 1 for all]")
            if cap is not None and len(out) > cap + self.CAP_SLACK:
                out = out[:cap].rstrip() + f"\n... [{len(t.stdout) - cap} more characters; SHOW {t.cell_no} for all]"
            code = t.code.rstrip()
            code_lines = code.splitlines()
            if not is_last and len(code_lines) > 14:                 # earlier recent cells: the head of the code only
                code = "\n".join(code_lines[:14]) + f"\n# ... {len(code_lines) - 14} more lines (SHOW {t.cell_no} for the whole cell)"
            body = f"--- cell {t.cell_no} ---\n```python\n{code}\n```\n"
            body += ("ERROR:\n" + t.error.strip() + "\n") if t.error else ("OUTPUT:\n" + (out if out.strip() else "(no output)") + "\n")
            if t.figures:
                body += f"(saved {len(t.figures)} figure(s): [fig {t.cell_no}])\n"
            parts.append(body)
        return "\n".join(parts) + failed_lines

    @staticmethod
    def failed_attempts(run: "Run", keep: int = 5) -> str:
        """This run's failed cells, one line each, placed in time - the turn, and the last cell committed before it
        (2026-10-11: listed after the cells with no position, a failure at turn 1 read as a failure after cell 2;
        the analyst rebuilt what it had and then spent two turns arguing which attempt had failed). The step's
        sentence says what the attempt was for; the error line what stopped it."""
        from .tools import exception_line
        lines, turn_no, last_cell = [], 0, 0
        for t in run.turns:
            if t.kind in ("review", "rewrite") or getattr(t, "step", ""):
                continue                                    # not a turn of the analysis
            turn_no += 1
            if t.kind == "cell" and t.cell_no:
                last_cell = t.cell_no
            elif t.kind == "cell" and t.error:
                where = f"after cell {last_cell}" if last_cell else "before any cell"
                lines.append(f"- turn {turn_no}, {where}: {purpose_of(t)}  ->  {exception_line(t.error)[:110]}")
        if not lines:
            return ""
        return "\nFAILED ATTEMPTS THIS RUN (rolled back, nothing persisted):\n" + "\n".join(lines[-keep:])

    def _render_everything(self, run_id: str) -> str:
        cells = self.computed_cells(run_id)
        if not cells:
            return "(no cells yet)"
        outs = {t.cell_no: (t.stdout or "") for t in cells}
        over = sum(len(o) for o in outs.values()) - self.REPORT_VIEW_CHARS
        if over > 0:
            # shorten the largest outputs from the middle until the total fits; each keeps its head and tail
            for no, out in sorted(outs.items(), key=lambda kv: -len(kv[1])):
                if over <= 0:
                    break
                cut = min(over, max(0, len(out) - 4000))
                if cut <= 0:
                    continue
                keep = len(out) - cut
                head, tail = out[:keep // 2].rstrip(), out[-(keep - keep // 2):].lstrip()
                outs[no] = head + f"\n... [{cut} characters omitted from the middle of this output for length; the notebook keeps all] ...\n" + tail
                over -= cut
        parts = ["EVERY CELL OF THIS RUN (the report turn: outputs whole, so every number you quote is in view):"]
        for t in cells:
            code_lines = t.code.rstrip().splitlines()
            code = "\n".join(code_lines[:14]) + (f"\n# ... {len(code_lines) - 14} more lines" if len(code_lines) > 14 else "")
            out = outs[t.cell_no]
            body = f"--- cell {t.cell_no} ---\n```python\n{code}\n```\n"
            body += ("ERROR:\n" + t.error.strip() + "\n") if t.error else ("OUTPUT:\n" + (out if out.strip() else "(no output)") + "\n")
            if t.figures:
                body += f"(saved {len(t.figures)} figure(s): [fig {t.cell_no}])\n"
            parts.append(body)
        return "\n".join(parts)

    # ----- the thread: what earlier chains established -------------------
    @staticmethod
    def conclusion(run: "Run") -> str:
        """One or two sentences from the report's opening: the chain's conclusion."""
        text = (run.report or run.rewrite or "").strip()
        if not text:
            return "(no report)" if run.status != "asked" else "(asked the person a question)"
        paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip() and not p.strip().startswith("#")]
        if not paras:
            return "(no report)"
        first = re.sub(r"\s+", " ", paras[0])
        sents = re.split(r"(?<=[.!?])\s+", first)
        out = " ".join(sents[:2])
        return out if len(out) <= 420 else out[:417].rstrip() + "..."

    @staticmethod
    def names_line(run: "Run") -> str:
        for ln in (run.note or "").splitlines():
            t = ln.strip().lstrip("-• ").strip()
            if t.lower().startswith("names"):
                return t.split(":", 1)[1].strip() if ":" in t else ""
        return ""

    def searches(self, run_id: str) -> List[Turn]:
        """Every search on the path, in order (SHOW SEARCH k opens one)."""
        return [t for r in self.path(run_id) for t in r.turns if t.kind == "search"]

    def render_ancestry(self, run_id: str, whole: int = 2) -> str:
        """Earlier chains on the path. The LEDGER never collapses: every chain's
        question, its conclusion, and the kernel names it left. The most recent
        `whole` chains also ride with their final note and the answer's opening
        paragraph. Anything older is opened with SHOW RUN k. No character cut."""
        path = self.path(run_id)[:-1]
        if not path:
            return ""
        parts = ["EARLIER IN THIS THREAD - the ledger (every chain; SHOW RUN k opens one whole):"]
        other = {r.id for r in self.earlier_on_other_data(run_id)}
        for k, run in enumerate(path, 1):
            q = re.sub(r"\s+", " ", run.question.strip())
            parts.append(f"[run {k}] Q: {q}\n        Conclusion: {self.conclusion(run)}")
            if run.id in other:
                parts.append("        " + self.other_data_line(run))     # the data changed since: context, not computation (2026-10-12)
                continue
            nm = self.names_line(run)
            if nm:
                parts.append(f"        Names left in the kernel: {nm}")
        recent = path[-whole:] if whole else []
        if recent:
            parts.append("\nTHE MOST RECENT CHAINS, WHOLE:")
            for run in recent:
                k = path.index(run) + 1
                ans = (run.report or run.rewrite or "").strip()
                paras = [p.strip() for p in re.split(r"\n\s*\n", ans) if p.strip()]
                opening = "\n\n".join(paras[:2]) if paras else "(no report)"
                parts.append(f"--- run {k}: {run.question.strip()} ---\nFINAL NOTE:\n{run.note.strip() or '(none)'}\nANSWER OPENING:\n{opening}\n")
        searches = self.searches(run_id)
        if searches:
            parts.append("SEARCHES SO FAR (SHOW SEARCH k re-opens one): " + "; ".join(
                f"[{i}] {re.sub(chr(10), ' ', (t.text or t.stdout or '').strip())[:60]}" for i, t in enumerate(searches, 1)))
        return "\n".join(parts)

    def render_run(self, run_id: str, k: int) -> str:
        """SHOW RUN k: an earlier chain whole - question, final note, report."""
        path = self.path(run_id)[:-1]
        if not 1 <= k <= len(path):
            return f"(no run {k}; this thread has {len(path)} earlier chain(s))"
        run = path[k - 1]
        return (f"--- run {k} ---\nQUESTION: {run.question.strip()}\nFINAL NOTE:\n{run.note.strip() or '(none)'}\n"
                f"REPORT:\n{(run.report or '(no report)').strip()}")

    def reads(self, run_id: str) -> List[Turn]:
        """Every document read on the path, in order (SHOW READ k opens one) - numbered along the path like searches."""
        return [t for r in self.path(run_id) for t in r.turns if t.kind == "read"]

    def render_read(self, run_id: str, k: int) -> str:
        """SHOW READ k: a read digest whole."""
        reads = self.reads(run_id)
        if not 1 <= k <= len(reads):
            return f"(no read {k}; {len(reads)} so far)"
        t = reads[k - 1]
        return f"--- read {k}: {(t.text or '').strip()} ---\n{(t.stdout or '').strip()}"

    def render_search(self, run_id: str, k: int) -> str:
        """SHOW SEARCH k: a search digest whole."""
        searches = self.searches(run_id)
        if not 1 <= k <= len(searches):
            return f"(no search {k}; {len(searches)} so far)"
        t = searches[k - 1]
        return f"--- search {k}: {(t.text or '').strip()} ---\n{(t.stdout or '').strip()}"

    # ----- persistence ---------------------------------------------------
    def to_dict(self) -> dict:
        d = dict(getattr(self, "extra", {}) or {})
        d.update({"thread_id": self.thread_id,
                  "runs": {rid: {**asdict(r), "turns": [asdict(t) for t in r.turns]} for rid, r in self.runs.items()}})
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Notebook":
        runs = {}
        run_keys = {f.name for f in fields(Run)}
        turn_keys = {f.name for f in fields(Turn)}
        for rid, r in (d.get("runs") or {}).items():
            # a key this version does not know (a record written by another) is left behind, not fatal (2026-10-17)
            turns = [Turn(**{k: v for k, v in t.items() if k in turn_keys}) for t in r.get("turns", [])]
            r2 = {k: v for k, v in r.items() if k != "turns" and k in run_keys}
            runs[rid] = Run(**r2, turns=turns)
        nb = cls(str(d.get("thread_id", "")), runs)
        # a thread file from the previous design (chains, ledger): keep its keys untouched
        nb.extra = {k: v for k, v in d.items() if k not in ("thread_id", "runs")}
        return nb


class NotebookStore:
    """One JSON file per thread under <storage_dir>/threads/."""

    def __init__(self, storage_dir: str):
        self.dir = os.path.join(storage_dir, "threads")
        os.makedirs(self.dir, exist_ok=True)

    def _file(self, thread_id: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9_-]", "", str(thread_id))
        return os.path.join(self.dir, f"{safe}.json")

    def load(self, thread_id: str) -> Notebook:
        f = self._file(thread_id)
        if not os.path.exists(f):
            return Notebook(str(thread_id))
        with open(f, encoding="utf-8") as fh:
            return Notebook.from_dict(json.load(fh))

    def save(self, nb: Notebook) -> None:
        f = self._file(nb.thread_id)
        tmp = f + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(nb.to_dict(), fh, indent=1, ensure_ascii=False)
        os.replace(tmp, f)
