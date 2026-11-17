"""Memory: the saved analyses as one read-only view (docs/ARCHITECT_DESIGN.md §3.1, §3.5).

A run is memory when it is saved - its favourite file stands under <storage>/favourites/<thread>/ - and the thread's
record holds it in the current format, with a report. The view is made from the record alone, never from the saved
copy of the page: of each run the question, the report, the code and the results, with how it was saved and the
earlier steps it was built on - and, where its question was framed first, the brief and the conversation the brief
came from. It is kept in a file and brought up to date in the background (refresh_soon), never built for a reader:
view() gives what is kept, less what was removed since. search() is plain keyword search over the view. No model is
called here.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import threading
import time

from analyst import brief as briefs
from analyst.notebook import NotebookStore, Run, subject_id_of
from analyst.routines import RoutineStore

logger = logging.getLogger(__name__)

FORMAT = 4                       # of the kept file: one kept in another format is built again (2: a run's brief and how the report stood against it; 3: the conversation the brief came from; 4: the brief's parts by their plain names)
PRINTED = 3000                   # characters kept of what a cell printed: what the analyst is shown of a recent cell
SAID = 40_000                    # characters kept of the conversation a brief came from
HEAD = 65536                     # bytes of a favourite file read for its mark: the page's copy, megabytes of it, follows
MARKS = {"individual": "picked", "trajectory": "alongside"}      # how a chain was saved, as the view says it
SYNTHESIS = "Write the report for the analysis so far on this thread"      # how a synthesis is asked for (bambooai.py): not the person's words
FIELDS = (("question", 3), ("title", 3), ("report", 2), ("brief", 2), ("conversation", 2), ("results", 2), ("code", 1), ("earlier", 1))      # where a word is looked for, and what it counts for there
MOST, PASSAGES, PASSAGE_CHARS = 10, 3, 320
WEAK = 0.25                      # a hit that scores under this part of the best one is left out

_again = {}                      # storage folder -> whether the refresh at work there is to go round once more
_guard = threading.Lock()


# ------------------------------------------------------------------ the sources
def _favourite(storage_dir: str, thread: str, chain: str) -> str:
    return os.path.join(storage_dir, "favourites", thread, f"{chain}.json")


def _saved(storage_dir: str) -> dict:
    """thread -> the chains saved in it."""
    root, out = os.path.join(storage_dir, "favourites"), {}
    for thread in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        folder = os.path.join(root, thread)
        chains = sorted(f[:-5] for f in os.listdir(folder) if f.endswith(".json")) if os.path.isdir(folder) else []
        if chains:
            out[thread] = chains
    return out


def _stat(path: str):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return [st.st_mtime_ns, st.st_size]


def _mark(path: str) -> str:
    """How a chain was saved - picked, alongside, or '' for one saved before the marks - from the head of its
    favourite file, where the route writes it; the file is read whole only where the head does not hold it."""
    with open(path, "rb") as fh:
        head = fh.read(HEAD)
        m = re.search(rb'\n  "bookmark_type": (?:null|"(\w*)")', head)
        if m is None and len(head) == HEAD:
            fh.seek(0)
            return MARKS.get(json.load(fh).get("bookmark_type"), "")
    return MARKS.get((m.group(1) or b"").decode(), "") if m else ""


# ------------------------------------------------------------------ what a run gives
def _cells(run: Run) -> list:
    """The cells of the analysis - not the ones that drew its figures afterwards: the code, the RESULT lines, and what
    was printed up to PRINTED characters, the cut said."""
    cut = lambda text: text if len(text) <= PRINTED else text[:PRINTED] + f"\n... ({len(text) - PRINTED:,} more characters not kept)"      # noqa: E731
    return [{"n": t.cell_no, "code": t.code, "results": [r["text"] for r in t.results if r.get("text")], "printed": cut(t.stdout)}
            for t in run.cells() if t.step != "figures"]


def _conversation(run: Run) -> str:
    """What the person and the Architect said while the run's question was framed (brief.said); "" where it was not
    framed. Up to SAID characters, the cut said. What was looked up or read meanwhile is no part of it: the brief
    holds the marks, and a passage of another analysis stands in its own."""
    text = briefs.said(run.framing, run.question)
    return text if len(text) <= SAID else text[:SAID] + f"\n... ({len(text) - SAID:,} more characters not kept)"


def _step(run: Run) -> dict:
    """A run as an earlier step of a saved one: what was asked and the cells - never its report - and, where the
    analyst stopped to ask, what it asked: the next run's question is the person's answer."""
    asked = next((t.text.strip() for t in run.turns if t.kind == "ask"), "")
    return {"question": run.question.strip(), **({"analyst_asked": asked} if asked else {}), "cells": _cells(run)}


def _thread(store: NotebookStore, storage_dir: str, thread: str, chains: list) -> dict:
    """What a saved thread gives the view: its saved runs that are read, the earlier steps they were built on that are
    not among them, and the saved chains that are not read - older (not on record in the current format), questions
    (a list of candidate questions from before 2.8), no_report (it ended without one)."""
    nb, runs, steps, not_read = store.read(thread), [], {}, {}
    for chain in chains:
        run = nb.runs.get(chain)
        why = "older" if run is None else "questions" if any(t.kind == "ideas" for t in run.turns) else "" if run.report else "no_report"
        if why:
            not_read.setdefault(why, []).append(chain)
            continue
        path, data, synthesis = nb.path(run.id), run.data or {}, run.question.startswith(SYNTHESIS)
        mark = _mark(_favourite(storage_dir, thread, chain))
        runs.append({"id": f"{thread}/{run.id}", "thread": thread, "run": run.id, "kind": "synthesis" if synthesis else "analysis",
                     "when": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(run.created)), "marks": [mark] if mark else [],
                     "question": "" if synthesis else run.question.strip(), "title": run.title, "report": run.report.strip(), "replay": run.replay_status,
                     "brief": briefs.render(run.brief, record=True),                  # what was agreed before the run, "" where it was not framed
                     "conversation": _conversation(run),
                     "outcome": {k: run.brief_outcome.get(k, "") for k in ("expected", "would_change")} if run.brief else {},
                     "data": {"name": data.get("name") or "", "rows": data.get("rows"), "period": str(data.get("date_range") or ""),
                              "columns": [c.get("name") for c in data.get("columns") or [] if isinstance(c, dict)], "subject": subject_id_of(data)},
                     "cells": _cells(run), "path": [f"{thread}/{r.id}" for r in path[:-1]],
                     **({"broken": True} if path[0].parent else {})})        # the walk up stopped at a run whose parent is not on record
    read = {r["run"] for r in runs}
    for r in runs:
        steps.update({f"{thread}/{e.id}": _step(e) for e in nb.path(r["run"])[:-1] if e.id not in read})
    return {"runs": runs, "steps": steps, "not_read": not_read}


# ------------------------------------------------------------------ the kept file
def _file(storage_dir: str) -> str:
    return os.path.join(storage_dir, "memory", "view.json")


def _kept(storage_dir: str) -> dict:
    """The file as kept: {format, built, threads: {thread: {sig, runs, steps, not_read}}}; an empty one where there is
    none, or one in another format."""
    try:
        with open(_file(storage_dir), encoding="utf-8") as fh:
            kept = json.load(fh)
        if isinstance(kept, dict) and kept.get("format") == FORMAT:
            return kept
    except (OSError, ValueError):
        pass
    return {"format": FORMAT, "built": None, "threads": {}}


def _sigs(store: NotebookStore, storage_dir: str) -> dict:
    """thread -> what the files of a saved thread look like now: the size and time of its record and of each
    favourite file."""
    return {thread: {"record": _stat(store._file(thread)), "saved": {c: _stat(_favourite(storage_dir, thread, c)) for c in chains}}
            for thread, chains in _saved(storage_dir).items()}


def refresh(storage_dir: str, keep: bool = True) -> dict:
    """Brings the kept view up to date with what is saved now, and returns the view. A thread whose files stand as
    they did when it was last read is not read again; where something was saved or removed while the threads were
    read, they are gone through once more, so what is written was true when it was written. With keep=False nothing
    is written: the view as it would be kept, `built` still saying when the file was last written."""
    kept, store, sigs = _kept(storage_dir), NotebookStore(storage_dir), None
    threads = kept["threads"]
    while (now := _sigs(store, storage_dir)) != sigs:
        sigs = now
        threads = {thread: threads[thread] if thread in threads and threads[thread]["sig"] == sig else {"sig": sig, **_thread(store, storage_dir, thread, list(sig["saved"]))}
                   for thread, sig in sigs.items()}
    if keep and (threads != kept["threads"] or kept["built"] is None):
        kept = {"format": FORMAT, "built": time.time(), "threads": threads}
        path = _file(storage_dir)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = f"{path}.{os.getpid()}.{threading.get_ident()}.tmp"            # a name of its own: another worker may be writing too
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(kept, fh, ensure_ascii=False)
        os.replace(tmp, path)
    return _view(storage_dir, {**kept, "threads": threads})


def refresh_soon(storage_dir: str) -> None:
    """refresh() behind the request that changed what is saved. One is at work on a storage folder at a time; asked
    for again meanwhile, it goes round once more when it ends."""
    with _guard:
        if storage_dir in _again:
            _again[storage_dir] = True
            return
        _again[storage_dir] = False

    def work():
        while True:
            try:
                refresh(storage_dir)
            except Exception:                                          # noqa: BLE001
                logger.warning("The memory view was not brought up to date", exc_info=True)
            with _guard:
                if not _again[storage_dir]:
                    del _again[storage_dir]
                    return
                _again[storage_dir] = False

    try:
        threading.Thread(target=work, name="memory-view", daemon=True).start()
    except RuntimeError:                                               # no thread to be had: the request goes on, and the next one asks again
        with _guard:
            del _again[storage_dir]
        logger.warning("The memory view was not brought up to date", exc_info=True)


def view(storage_dir: str) -> dict:
    """The view as it is kept (see _view). Nothing is built here: before the first refresh the view is empty."""
    return _view(storage_dir, _kept(storage_dir))


def _view(storage_dir: str, kept: dict) -> dict:
    """The view, for a reader: {format, built, runs, steps, not_read}. `runs` are the saved runs, the newest first,
    each {id, thread, run, kind, when, marks, question, title, report, replay, brief, outcome, conversation, data,
    cells, path} - `marks` of picked, alongside and routine; `path` the ids of the earlier steps it was built on,
    the first one first; `broken` where one of them is not on record. `steps` holds the earlier steps that are not
    saved runs themselves, by id: {question, cells}. `not_read` counts the saved chains left out, by reason. What
    was removed since the file was written is left out: a run whose favourite file is gone is no memory, and stays
    only as a step of the saved runs built on it."""
    routines = RoutineStore(storage_dir).by_origin()
    runs, steps, not_read = [], {}, {}
    for thread, part in kept["threads"].items():
        saved = lambda chain: os.path.exists(_favourite(storage_dir, thread, chain))      # noqa: E731
        removed = {r["id"]: r for r in part["runs"] if not saved(r["run"])}
        for r in part["runs"]:
            if r["id"] in removed:
                continue
            runs.append({**r, "marks": r["marks"] + (["routine"] if (thread, r["run"]) in routines else [])})
            for p in r["path"]:
                if p in part["steps"]:
                    steps[p] = part["steps"][p]
                elif p in removed:
                    steps[p] = {"question": removed[p]["question"], "cells": removed[p]["cells"]}
        for why, chains in part["not_read"].items():
            n = sum(1 for c in chains if saved(c))
            if n:
                not_read[why] = not_read.get(why, 0) + n
    runs.sort(key=lambda r: r["when"], reverse=True)
    return {"format": FORMAT, "built": kept["built"], "runs": runs, "steps": steps, "not_read": not_read}


# ------------------------------------------------------------------ plain keyword search
def _around(text: str, at: int) -> str:
    """A text up to PASSAGE_CHARS whole; of a longer one the passage around a place in it, cut at words, the cuts
    marked."""
    start = max(0, min(at - PASSAGE_CHARS // 3, len(text) - PASSAGE_CHARS))
    piece = text[start:start + PASSAGE_CHARS]
    if start:
        piece = "..." + piece.split(" ", 1)[-1]
    if start + PASSAGE_CHARS < len(text):
        piece = piece.rsplit(" ", 1)[0] + "..."
    return piece


def _passages(run: dict, finds: dict, rare: dict) -> list:
    """The places of a run that hold the words - a paragraph of the report, a line of the brief or of the
    conversation it came from, a RESULT line, a line of code - the best first, PASSAGES at most, each {where, text};
    a long one is cut around its rarest word."""
    weight, places = dict(FIELDS), []                    # places: (what it counts for, where, the text, where its rarest word stands)

    def place(text, where, counts):
        at = {w: m.start() for w, find in finds.items() for m in [find.search(text.lower())] if m}
        if at and text not in [p[2] for p in places]:
            places.append((counts * sum(rare[w] for w in at), where, text, at[max(at, key=rare.get)]))

    for para in re.split(r"\n\s*\n", re.sub(r"(?m)^#.*$", "", run["report"])):          # a heading is no passage
        place(" ".join(para.split()), "report", weight["report"])
    for where in ("brief", "conversation"):
        for line in run[where].splitlines():
            place(line.strip(), where, weight[where])
    for cell in run["cells"]:
        for line in cell["results"]:
            place(" ".join(line.split()), f"cell {cell['n']}", weight["results"])
        for line in cell["code"].splitlines():
            place(line.strip(), f"cell {cell['n']}, code", weight["code"])
    return [{"where": where, "text": _around(text, at)} for _, where, text, at in sorted(places, key=lambda p: -p[0])[:PASSAGES]]


def search(view: dict, query: str, most: int = MOST) -> list:
    """Plain keyword search over a view: the saved runs that hold a word of the query, the best first, each {id,
    thread, run, kind, when, question, title, marks, words, score, passages}. A word is held where a word of the run
    starts with it, whatever the case. It counts for more in the question or the title than in the report, the
    brief or the conversation, and least in the code or in an earlier step's question (FIELDS); a word most runs
    hold counts for little. A hit far weaker than the best is left out (WEAK). `passages` are the places that hold
    the words (_passages). No match returns nothing."""
    words = list(dict.fromkeys(w for w in re.findall(r"[^\W_]+", (query or "").lower()) if len(w) > 1))
    runs = view["runs"]
    finds = {w: re.compile(r"(?<![^\W_])" + re.escape(w)) for w in words}
    by_id = {r["id"]: r for r in runs}
    asked = lambda step: (by_id.get(step) or view["steps"].get(step) or {}).get("question", "")      # noqa: E731
    texts = [{"question": r["question"], "title": r["title"], "report": r["report"], "brief": r["brief"], "conversation": r["conversation"], "results": "\n".join(x for c in r["cells"] for x in c["results"]),
              "code": "\n".join(c["code"] for c in r["cells"]), "earlier": "\n".join(asked(p) for p in r["path"])} for r in runs]
    # for each run, what each word counts for where it stands best; 0 where the run does not hold it
    held = [{w: max((weight for field, weight in FIELDS if finds[w].search(low[field])), default=0) for w in words}
            for low in ({field: text.lower() for field, text in t.items()} for t in texts)]
    rare = {w: math.log(1 + (len(runs) - n + 0.5) / (n + 0.5)) for w in words for n in [sum(1 for h in held if h[w])]}
    scored = [(sum(rare[w] * h[w] for w in words), run, [w for w in words if h[w]]) for run, h in zip(runs, held) if any(h.values())]
    best = max((score for score, _, _ in scored), default=0)
    scored = sorted((s for s in scored if s[0] >= WEAK * best), key=lambda s: -s[0])      # equal scores stay newest first
    return [{**{k: run[k] for k in ("id", "thread", "run", "kind", "when", "question", "title", "marks")}, "words": got, "score": round(score, 2),
             "passages": _passages(run, finds, rare)} for score, run, got in scored[:most]]
