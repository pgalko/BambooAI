"""The draft of the figures: what the person will get, drawn before their question is analysed
(docs/ARCHITECT_DESIGN.md §2.20).

A brief may hold figures the person asked to see (analyst/brief.py). After a reply of the Pathfinder's, each figure
of the brief in use that has no draft is due one (due()): a model writes one cell that draws them (prompt(),
cell()), the host runs it where no data is, and what it drew is read, a plot to a figure (read()). draw() is that
round - the cell asked for once more where it was not run or left a figure without a plot - and settle() takes it into
the run: what the page shows of each draft, found by the keys beside the brief's versions (keyed(), the framing's
`drafts`); the round as a turn of the conversation (line()); and the cell on the run's record, where the step that
draws the figures of the analysis finds it (agreed()).

Two things are held in code. The cell is screened before it runs (screen()): it imports nothing a draft has no use
for and reads no file - a draft is computed from a rule or drawn on made-up numbers, and the host gives its cell
no data. And a figure counts as computed only where its cell said so: every other draft is shown as made up.

The plots are files beside the thread's record (Plots), a figure's under its key: the record and the framing hold
none of them. A branch runs under the brief of the chains it went on from (lineage()), and their plots are kept under
it too (Plots.carry; 0331).
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from typing import Callable, Optional

from analyst import brief as briefs
from analyst import steps
from analyst import tools
from analyst.notebook import Notebook, Run

with open(os.path.join(os.path.dirname(__file__), "draft.md"), encoding="utf-8") as _fh:
    SYSTEM = _fh.read().strip()

EFFORT = ("low",)                # a short cell from a plain description: the seat's effort is lowered to this; a seat set lower stays lower
ATTEMPTS = 2                     # the cell, and one correction
TRIES = 2                        # rounds a figure gets: one that could not be drawn is tried once more, after the person next speaks
SECONDS = 20                     # what the cell may take: a draft is a look ahead, not the analysis
PLOT_CHARS = 1_500_000           # of one plot, as text: a longer one is not kept
SAVED_CHARS = 16_000             # of a saved analysis' code, as the model that writes the cell reads it
COMPUTED, MADE_UP = "computed", "made up"      # what a draft's numbers are: the first only where the cell said so (the figure's `meta`)
MODULES = ("numpy", "scipy", "pandas", "plotly", "math", "cmath", "random", "statistics", "itertools", "functools", "collections", "datetime",
           "calendar", "fractions", "decimal", "string")      # what a draft's cell may import
NAMES = ("open", "exec", "eval", "compile", "breakpoint", "globals", "locals", "getattr", "setattr", "delattr")      # names that lead out of the cell - none a cell is likely to give a variable of its own
FILES = re.compile(r"(open|read_\w+|load\w*|save\w*|write_\w+|to_(csv|excel|parquet|pickle|feather|hdf|sql|stata|clipboard)|fromfile|tofile|genfromtxt|memmap)")
NO_CELL = "the reply held no python block"
CUT = "the reply was cut off at the token limit before a cell arrived"
DECLINED = "the model declined to reply ({category})"
LEFT_OUT = "the cell drew no figure under {titles}"
TOO_LONG = "a figure the cell drew is too large to keep: it takes fewer points"
AGAIN = "YOUR LAST REPLY DID NOT GIVE THE DRAFT: {why}.{shown}\nReply with the whole cell again, corrected."


def key(question: str, figure: dict) -> str:
    """The name a figure's draft is kept under: one figure of one question - as it is described, under the question
    as it stands. Either changed, it is another draft."""
    text = json.dumps([briefs.wording(question), figure], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def keyed(framing: dict) -> dict:
    """The framing with the key of each figure beside the brief of its version (`keys`, in the figures' order): the
    page finds a figure's draft by it."""
    versions = []
    for v in (framing or {}).get("versions") or []:
        brief = v.get("brief") or {}
        v = {k: x for k, x in v.items() if k != "keys"}
        versions.append({**v, "keys": [key(brief.get("question", ""), f) for f in brief["figures"]]} if brief.get("figures") else v)
    return {**(framing or {}), "versions": versions}


def due(framing: dict) -> list:
    """The figures of the brief in use that are to be drawn now, each (its key, the figure): one without a draft, and
    one whose draft could not be drawn, until it was tried TRIES times. None while the Pathfinder goes on by itself -
    after its lookups, a reading, a part it opened: the reply the person reads is the one after."""
    turns = (framing or {}).get("turns") or []
    if turns and turns[-1].get("who") in ("check", "memory", "opened"):
        return []
    brief, kept = briefs.latest(framing), (framing or {}).get("drafts") or {}
    out = []
    for f in brief.get("figures", []):
        k = key(brief.get("question", ""), f)
        if k not in kept or (kept[k].get("failed") and int(kept[k].get("tries") or 1) < TRIES):
            out.append((k, f))
    return out


def prompt(question: str, figures: list, before: str = "", saved: str = "") -> str:
    """What the model that writes the cell reads: the question as it stands, the figures in words (analyst/brief.py
    figure_lines()), the cell that last drew figures for the question, and the code of the saved analyses the brief
    builds on - each where there is one."""
    parts = [f"QUESTION:\n{question.strip()}", "FIGURES TO DRAW:\n" + "\n".join(f"{k}. {ln}" for k, ln in enumerate(briefs.figure_lines({"figures": figures}), 1))]
    parts += [f"THE DRAFT BEFORE:\n```python\n{before.strip()}\n```"] if before.strip() else []
    parts += [f"A SAVED ANALYSIS THE QUESTION BUILDS ON:\n{saved.strip()}"] if saved.strip() else []
    return "\n\n".join(parts + ["Reply with the cell."])


def cell(reply: str) -> str:
    """The cell a reply holds: the code of its python block - of each, in order, where it holds more than one; ''
    where it holds none."""
    blocks = re.findall(r"```(?:python|py)?[ \t]*\n(.*?)```", reply or "", re.S)
    return "\n\n".join(b.strip("\n") for b in blocks if b.strip())


def screen(code: str) -> str:
    """Why a cell is not run - '' where it may be: it does not parse, it imports a module a draft has no use for, it
    calls what reads or writes a file, or it uses a name that leads out of the cell. This is no sandbox - the
    executor is one: it keeps a cell that means well from the person's data."""
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return f"it does not parse - {exc.msg}, line {exc.lineno}"
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [a.name for a in node.names] if isinstance(node, ast.Import) else [("." * node.level) + (node.module or "")]
            other = next((m for m in modules if m.split(".")[0] not in MODULES), None)
            if other is not None:
                return f"it imports {other}: a draft imports {', '.join(MODULES[:4])} and the standard maths modules, and nothing else"
        called = ([a.name for a in node.names] if isinstance(node, ast.ImportFrom)
                  else [node.func.attr] if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) else [])
        name = next((n for n in called if FILES.fullmatch(n)), None)
        if name:
            return f"it reads or writes a file ({name}): a draft has no data and loads none"
        name = node.id if isinstance(node, ast.Name) else node.attr if isinstance(node, ast.Attribute) else ""
        if name in NAMES or name.startswith("__"):
            return f"it uses {name}: a draft computes and draws, and nothing else"
    return ""


def _title(layout: dict) -> str:
    """The title a plot was drawn under, as its layout holds it: a text, or an object with one."""
    title = layout.get("title")
    return str(title.get("text") or "") if isinstance(title, dict) else title if isinstance(title, str) else ""


def read(plots: list, figures: list) -> tuple:
    """What a cell drew, a plot to a figure: {a figure's place among `figures`: {"plot": the plot as the executor
    gave it, "basis": COMPUTED where the cell said so, else MADE_UP}}, and how many plots were too long to keep.
    `plots`: the cell's, in the order shown ({"data", "format"}); only what parses as a Plotly figure with something
    drawn counts - a picture does not.
    A plot stands for the figure whose title it carries; where as many plots as figures were drawn, one under
    another title stands for the figure that is left, in order."""
    drawn, long = [], 0
    for p in plots or []:
        text = p.get("data") if isinstance(p, dict) else None
        if not isinstance(text, str):
            continue
        if len(text) > PLOT_CHARS:
            long += 1
            continue
        try:
            plot = json.loads(text)
        except ValueError:
            continue
        if isinstance(plot, dict) and isinstance(plot.get("data"), list) and plot["data"]:
            layout = plot.get("layout") if isinstance(plot.get("layout"), dict) else {}
            drawn.append((_title(layout), {"plot": text, "basis": COMPUTED if layout.get("meta") == COMPUTED else MADE_UP}))
    out, other = {}, []
    for title, got in drawn:
        at = next((i for i, f in enumerate(figures) if i not in out and briefs.carries(title, f["title"])), None)
        if at is None:
            other.append(got)
        else:
            out[at] = got
    if len(drawn) == len(figures):
        out.update(zip([i for i in range(len(figures)) if i not in out], other))
    return out, long


def draw(llm: Callable, run_cell: Callable, run: Run, figures: list, saved: str = "") -> dict:
    """One round: the cell that draws `figures` ([(key, figure)], as due() gives them) written, run and read - and
    asked for once more, with what went wrong, where it was not run or left a figure without a plot: it failed
    before it drew it, or drew none under its title. `run_cell(code)` runs a cell where no data is and gives (its
    plots, its error). What a cell drew before it failed counts, and a figure keeps the last plot drawn for it.
    Returns {"drawn": {key: {"plot", "basis"}}, "cells": [{"code", "keys": the figures whose plot is this cell's}],
    "failed": why a figure is without a draft - '' where each has one -, "calls", "cost"}."""
    question = briefs.latest(run.framing).get("question") or run.question
    user = prompt(question, [f for _, f in figures], run.drafts[-1]["code"] if run.drafts else "", saved)
    drawn, by, note, why, calls, cost = {}, {}, "", "", 0, 0.0
    for _ in range(ATTEMPTS):
        reply, usage = llm(SYSTEM, user + note, effort=EFFORT)
        usage = usage or {}
        calls, cost = calls + 1, cost + float(usage.get("cost") or 0.0)
        code, got, error = cell(reply), {}, ""
        if usage.get("declined"):
            why = DECLINED.format(category=usage["declined"])
            break
        if not code:
            why = CUT if usage.get("truncated") else NO_CELL
        else:
            refused = screen(code)
            why = f"the cell was not run: {refused}" if refused else ""
            if not refused:
                plots, error = run_cell(code)
                error = tools.condense_error(str(error), code=code) if error else ""
                got, long = read(plots, [f for _, f in figures])
                left = [f'"{f["title"]}"' for i, (_, f) in enumerate(figures) if i not in got]
                why = "" if not left else f"the cell failed: {tools.exception_line(error)[:200]}" if error else TOO_LONG if long else LEFT_OUT.format(titles=", ".join(left))
            for i, plot in got.items():
                drawn[figures[i][0]], by[figures[i][0]] = plot, code
        if not why:
            break
        shown = (f"\n```python\n{code.rstrip()}\n```" if code else "") + (f"\nERROR:\n{error}" if error else "")
        note = "\n\n" + AGAIN.format(why=why, shown=shown)
    cells = [{"code": code, "keys": [k for k, _ in figures if by.get(k) == code]} for code in dict.fromkeys(by.values())]
    return {"drawn": drawn, "cells": cells, "failed": why if len(drawn) < len(figures) else "", "calls": calls, "cost": cost}


def lost(why: str, calls: int = 0) -> dict:
    """A round that broke off, as draw() gives one: nothing drawn, why, and the calls it had made."""
    return {"drawn": {}, "cells": [], "failed": why, "calls": calls, "cost": 0.0}


def settle(run: Run, figures: list, made: dict, secs: float = 0.0) -> None:
    """A round taken into its run. The framing says of each figure what its draft is (`drafts`, by key: its basis -
    or why there is none, and how often it was tried), and the round is the conversation's last turn: the figures
    drawn, each with its basis, the ones left without a draft and why, the seconds, the cost and the number of its
    last call among the draft's. The cells that drew stand on the run's record."""
    framing, kept = run.framing or {}, dict((run.framing or {}).get("drafts") or {})
    for k, _ in figures:
        kept[k] = {"basis": made["drawn"][k]["basis"]} if k in made["drawn"] else {"failed": made["failed"], "tries": int((kept.get(k) or {}).get("tries") or 0) + 1}
    calls = int(framing.get("draft_calls") or 0) + made["calls"]
    missing = [f["title"] for k, f in figures if k not in made["drawn"]]
    turn = {"who": "draft", "drawn": [{"title": f["title"], "basis": made["drawn"][k]["basis"]} for k, f in figures if k in made["drawn"]],
            **({"missing": missing, "failed": made["failed"]} if missing else {}),
            "v": briefs.latest(framing).get("version") or len(framing.get("versions") or []), "secs": round(secs, 1), "cost": round(made["cost"], 4),
            **({"call": calls} if made["calls"] else {})}
    run.drafts = list(run.drafts) + made["cells"]
    run.framing = steps.take({**framing, "drafts": kept, "draft_calls": calls, "turns": list(framing.get("turns") or []) + [turn]})


def line(turn: dict) -> str:
    """A round as a line of the Pathfinder's CONVERSATION block: the figures drawn, each by its title with what its
    numbers are, and the ones without a draft, with why."""
    drawn = [f"\"{d['title']}\" ({'computed' if d.get('basis') == COMPUTED else 'on made-up numbers'})" for d in turn.get("drawn", [])]
    missing = ", ".join(f'"{t}"' for t in turn.get("missing", []))
    return "Draft of the figures: " + "; ".join((["drawn - " + ", ".join(drawn)] if drawn else []) + ([f"not drawn - {missing}: {turn.get('failed', '')}"] if missing else []))


def agreed(run: Run) -> list:
    """The drafts of the figures a run's brief holds, for the step that draws them after the report: [{"code": the
    cell, "titles": the figures it drew, "made_up": those of them drawn on made-up numbers}], a cell once, in the
    figures' order. [] where none was drawn."""
    kept, out = (run.framing or {}).get("drafts") or {}, []
    for f in (run.brief or {}).get("figures", []):
        k = key(run.brief.get("question") or run.question, f)
        code = next((r["code"] for r in reversed(run.drafts) if k in r["keys"]), "")
        if not code:
            continue
        entry = next((e for e in out if e["code"] == code), None)
        if entry is None:
            entry = {"code": code, "titles": [], "made_up": []}
            out.append(entry)
        entry["titles"].append(f["title"])
        entry["made_up"] += [f["title"]] if kept.get(k, {}).get("basis") != COMPUTED else []
    return out


def saved_code(nb: Notebook, run_id: str, chars: int = SAVED_CHARS) -> str:
    """The code of an analysis a brief builds on, for the model that writes the cell: the cells along its path, in
    the order they ran, each under its number, the ones that drew figures said so. Where they are longer than
    `chars` together, the ones that fit stay: the cells that drew first, then the others, the last ones before the
    earlier - and how many were left out is said."""
    cells = nb.path_cells(str(run_id))
    block = lambda t: f"--- cell {t.cell_no}{' (drew its figures)' if t.figures else ''} ---\n```python\n{t.code.rstrip()}\n```"      # noqa: E731
    room, keep = chars, set()
    for t in [t for t in reversed(cells) if t.figures] + [t for t in reversed(cells) if not t.figures]:      # the last cell that drew, whatever its length
        room -= len(block(t))
        if room < 0 and keep:
            break
        keep.add(t.cell_no)
    left = len(cells) - len(keep)
    return "\n\n".join(([f"({left} cell{'s' if left != 1 else ''} left out)"] if left else []) + [block(t) for t in cells if t.cell_no in keep])


class Plots:
    """The plots of the drafts, a file each: <storage>/drafts/<thread>/<run>/<key>.json, the plot as the executor
    gave it. They go with the thread (web_app/cleanup.py)."""

    def __init__(self, storage_dir: str):
        self.dir = os.path.join(storage_dir, "drafts")

    def _path(self, thread, run, key) -> str:
        """Where a plot is kept: under the letters, digits, dashes and underscores of its thread, its run and its
        key - '' where one of them has none, which is no file."""
        parts = [re.sub(r"[^A-Za-z0-9_-]", "", str(s)) for s in (thread, run, key)]
        return os.path.join(self.dir, parts[0], parts[1], parts[2] + ".json") if all(parts) else ""

    def put(self, thread, run, key, plot: str) -> None:
        path = self._path(thread, run, key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path + ".part", "w", encoding="utf-8") as fh:
            fh.write(plot)
        os.replace(path + ".part", path)

    def get(self, thread, run, key) -> Optional[str]:
        try:
            with open(self._path(thread, run, key), encoding="utf-8") as fh:
                return fh.read()
        except OSError:
            return None

    def carry(self, thread, runs, run) -> int:
        """The plots kept under `runs` kept under `run` too - of a figure two of them have, the first's; one `run` has
        already stays as it is. A branch's, from the chains it went on from (lineage()). Returns how many it kept."""
        if not self._path(thread, run, "k"):
            return 0
        kept = 0
        for src in runs:
            folder = os.path.dirname(self._path(thread, src, "k"))
            for name in sorted(os.listdir(folder)) if folder and os.path.isdir(folder) else []:
                key = name[:-len(".json")] if name.endswith(".json") else ""
                plot = self.get(thread, src, key) if key and self.get(thread, run, key) is None else None
                if plot is not None:
                    self.put(thread, run, key, plot)
                    kept += 1
        return kept


def lineage(notebook: Optional[Notebook], run_id) -> list:
    """A run and the chains it went on from, nearest first: a branch's `branch["of"]`, that one's, and so on to a run that
    is no branch, or one the record no longer has (2.9). A branch runs under their brief, whose figures were drafted
    before the first of them ran: their drafts are its drafts (0331)."""
    out, run = [str(run_id)], notebook.runs.get(str(run_id)) if notebook is not None else None
    while run is not None and run.branch and str(run.branch.get("of")) not in out:
        out.append(str(run.branch["of"]))
        run = notebook.runs.get(out[-1])
    return out
