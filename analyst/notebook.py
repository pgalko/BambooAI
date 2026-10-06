"""The notebook: one tree of runs per thread, each run a sequence of turns.

A RUN is one user question and everything the analyst did to answer it. Runs
have parents, so a thread is a tree; the context for a run is the path from the
root to its parent. A TURN is one action inside a run - a cell, a shown cell, a
search, a recall, a question to the user, the report, the rewrite - together
with the note as the analyst rewrote it that turn.

Cells are numbered along the path (1, 2, 3 ...) so the analyst and the report
can refer to them; the numbering restarts only at the root.

Persistence is one JSON file per thread, rewritten after every turn.
"""
from __future__ import annotations

import json
import os
import re
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional


def _now() -> float:
    return time.time()


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def step_sentence(thinking: str, width: int = 110) -> str:
    """The analyst's account of the step: its THINKING from the second sentence on - the first, by the contract's
    order, says what the last output showed - cut at a word to `width`. A one-sentence THINKING is the step itself."""
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
    results: List[dict] = field(default_factory=list)   # CELL: the RESULT(...) records the kernel kept (text, typed, test, corrects)
    cell_no: Optional[int] = None   # CELL: its number along the path (only committed cells get one)
    text: str = ""                  # ask/report/rewrite: the analyst's text
    usage: dict = field(default_factory=dict)            # tokens, cost, elapsed for the model call
    elapsed: float = 0.0            # CELL: seconds the kernel took to run it
    created: float = field(default_factory=_now)


@dataclass
class Run:
    id: str
    parent: Optional[str]
    question: str
    turns: List[Turn] = field(default_factory=list)
    report: str = ""                # the technical report (final)
    rewrite: str = ""               # the simplified rewrite (final)
    replay_status: str = ""         # reproduced | differed | failed | (empty = not run)
    replay_script: str = ""
    status: str = "running"         # running | answered | asked | stopped | failed
    created: float = field(default_factory=_now)

    @property
    def note(self) -> str:
        for t in reversed(self.turns):
            if t.note:
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
        analyst's own account of the step - its THINKING from the second sentence on (the first, by the contract's
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
        cells = self.path_cells(run_id)
        run = self.runs.get(run_id)
        failed = [t for t in (run.turns if run else []) if t.kind == "cell" and t.error]
        failed_lines = ""
        if failed:
            from .tools import exception_line
            failed_lines = "\nFAILED ATTEMPTS THIS RUN (rolled back, nothing persisted):\n" + "\n".join(
                f"- {purpose_of(t)}  ->  {exception_line(t.error)[:110]}" for t in failed[-5:])
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
            if cap is not None and len(out) > cap:
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

    def _render_everything(self, run_id: str) -> str:
        cells = self.path_cells(run_id)
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
        for k, run in enumerate(path, 1):
            q = re.sub(r"\s+", " ", run.question.strip())
            parts.append(f"[run {k}] Q: {q}\n        Conclusion: {self.conclusion(run)}")
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
        for rid, r in (d.get("runs") or {}).items():
            turns = [Turn(**t) for t in r.get("turns", [])]
            r2 = {k: v for k, v in r.items() if k != "turns"}
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
