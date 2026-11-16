"""Memory: the saved analyses as one read-only view (analyst/memory.py; docs/ARCHITECT_DESIGN.md §3.1, §3.5) - what
counts as memory and what does not, the marks, the earlier steps, what leaves when a workflow or a chain is removed,
how the view is kept and brought up to date, and plain keyword search over it. No model, no kernel.

    python3 tests/analyst/test_memory.py
"""
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

from analyst import memory                                     # noqa: E402
from analyst.notebook import Notebook, NotebookStore, Turn     # noqa: E402
from analyst.routines import SHAPE                             # noqa: E402

passed, failed = [], []
unbuilt = lambda view: {k: v for k, v in view.items() if k != "built"}        # noqa: E731  a view, whenever its file was written


def check(name, cond, detail=""):
    (passed if cond else failed).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:700]}"))


# ---- a storage folder as the app leaves one ----
def add(nb, rid, question, parent=None, report="", cells=(), status="answered", at=0.0, **more):
    """A run on the record: its cells numbered along the path, each (code, printed, [result lines])."""
    run = nb.new_run(question, parent=parent, run_id=rid)
    n = nb.next_cell_no(rid)
    for k, (code, printed, results) in enumerate(cells):
        run.turns.append(Turn(kind="cell", code=code, stdout=printed, results=[{"text": r, "line": 1, "typed": False} for r in results], cell_no=n + k))
    run.report, run.status, run.created = report, status, 1_790_000_000.0 + at
    run.title = report.splitlines()[0].lstrip("# ").strip() if report.startswith("#") else ""
    for key, value in more.items():
        setattr(run, key, value)
    return run


def favourite(storage, thread, chain, mark="individual", task="a question", pane=1000, keyed=True):
    """A favourite file as the route writes it (web_app/app.py store_trajectory_favourites): the mark, then the page's copy."""
    folder = os.path.join(storage, "favourites", str(thread))
    os.makedirs(folder, exist_ok=True)
    data = {"thread_id": thread, "chain_id": chain, "parentChainId": None, "dataset_name": None, "index": 0, "timestamp": "2026-11-16T10:00:00", "task": task}
    if keyed:
        data["bookmark_type"] = mark
    data.update({"tabContent": "", "contentOutput": "x" * pane, "streamOutput": "y" * pane, "queryText": task})
    path = os.path.join(folder, f"{chain}.json")
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)
    return path


def routine(storage, rid, thread, chain):
    folder = os.path.join(storage, "routines", rid)
    os.makedirs(folder, exist_ok=True)
    origin = {"thread_id": str(thread), "chain_id": str(chain)}
    with open(os.path.join(folder, "routine.json"), "w") as fh:
        json.dump({"id": rid, "name": "Drift over the block", "shape": SHAPE, "origin": origin, "current_version": 1,
                   "versions": [{"number": 1, "promoted_from": origin}], "runs": []}, fh)


HELPER = "def drift(df):\n    # the slope of hr against power, per session\n    return df.groupby('session').apply(slope)\nper_session = drift(df)\nprint(len(per_session))"
S = tempfile.mkdtemp(prefix="bamboo_memory_")
store = NotebookStore(S)

# thread 100: 101 -> 102 -> 103 -> 105 (asked) -> 106, and 104 beside 102
nb = Notebook("100")
add(nb, "101", "How is the drift computed per session? ", report="# Drift is a slope per session\n\nDrift is the slope of hr against power in a session [cell 1].",
    cells=[(HELPER, "40\n", ["sessions with a drift: 40"])], at=1)
add(nb, "102", "Does the drift grow over the block?\n", parent="101", at=2,
    report="# The drift grows over the block\n\nThe drift rises by 0.8 points a week over the block [cell 2].\n\n## How it was established\n\nA line through the weekly medians of the per-session drift [cell 2].\n\n",
    cells=[("weekly = per_session.resample('W').median()\nRESULT('rise per week', fit(weekly).slope)", "0.8\n", ["rise per week: +0.8 points"])])
add(nb, "103", "And in the last four weeks?", parent="102", at=3,
    report="# The last four weeks are flat\n\nNo rise in the last four weeks: +0.1 points a week, interval through zero [cell 3].",
    cells=[("late = weekly.tail(4)\nRESULT('late rise', fit(late).slope)", "0.1\n", ["late rise: +0.1 points", ""])])
add(nb, "104", "Is the drift the same on the turbo?", parent="101", at=4,
    report="# Turbo sessions drift more\n\nOn the turbo the drift is higher [cell 2].", cells=[("turbo_only = per_session[indoor]", "", ["turbo drift: 3.1"])])
asked = add(nb, "105", "Which weeks count as the taper?", parent="103", status="asked", at=5, cells=[("print(weekly.index[-6:])", "six weeks\n", [])])
asked.turns.append(Turn(kind="ask", text="The plan names no taper. Is it the last two weeks or the last three?\n"))
add(nb, "106", "The last two.", parent="105", at=6, report="# The taper weeks drift less\n\nIn the last two weeks the drift is 1.2 points lower [cell 5].",
    cells=[("taper = weekly.tail(2)\nRESULT('taper', taper.mean() - weekly.mean())", "-1.2\n", ["taper: -1.2 points"])])
store.save(nb)
favourite(S, 100, 102, "individual")
favourite(S, 100, 103, "trajectory")
favourite(S, 100, 105, "trajectory")
favourite(S, 100, 106, "trajectory")
routine(S, "r1", 100, 102)

# thread 200: the design before the runs, written as it wrote it
with open(store._file("200"), "w") as fh:
    json.dump({"thread_id": "200", "chains": {"201": {"messages": ["old"]}, "202": {"messages": ["old"]}}}, fh, indent=2)
favourite(S, 200, 201, keyed=False)
favourite(S, 200, 202, keyed=False)
favourite(S, 250, 251, "individual")                           # a saved chain whose thread has no record at all
os.makedirs(os.path.join(S, "favourites", "150"))              # a folder with no chain in it
for stray in (("notes.txt",), ("200", ".DS_Store")):           # files that are no chains
    open(os.path.join(S, "favourites", *stray), "w").close()

# thread 300: begun in the old design and continued; a list of questions, a synthesis, a run whose parent is gone, a run with everything
nb3 = Notebook("300")
nb3.extra = {"chains": {"299": {"messages": ["old " * 50]}}, "ledger": [{"runs": {"not": "these"}}]}
ideas = add(nb3, "301", "User requested variations of the question", report="1. One?\n2. Two?", at=7)
ideas.turns.append(Turn(kind="ideas", text="1. One?\n2. Two?"))
add(nb3, "302", memory.SYNTHESIS + ": the answer first, then how it was established.", at=8, report="# Sleep and load together explain the drift\n\nAcross the thread: sleep matters most [run 1].")
add(nb3, "303", "Does sleep explain the drift?", at=9, report="# Sleep explains a third\n\nA third of the drift goes with sleep [cell 1].", cells=[("m = ols(drift ~ sleep)", "r2 0.33\n", ["r2: 0.33"])],
    data=None)                                                # as a record from before the data was kept has it
nb3.runs["303"].parent = "999"                                # its parent is no longer on record
full = add(nb3, "304", "How much does the weekly load vary?", at=10, report="# Load varies by a quarter\n\nThe weekly load varies by 25% [cell 1].", replay_status="reproduced",
           cells=[("print(load.describe())", "line\n" * 2000, ["cv: 0.25"])],
           data={"df_id": "f1", "name": "sessions.csv", "rows": 412, "date_range": "2026-01-01 to 2026-06-30", "columns": [{"name": "session", "dtype": "str"}, "not a column", {"name": "load", "dtype": "float64"}],
                 "load": {"subject": {"source": "s", "id": "p-7", "name": "First Person"}}})
full.turns.append(Turn(kind="cell", code="plt.plot(load)", cell_no=2, step="figures"))
full.turns.append(Turn(kind="cell", code="broken(", error="SyntaxError"))                     # an attempt that failed: no number
store.save(nb3)
for chain in (299, 301, 302, 303):
    favourite(S, 300, chain, "trajectory")
favourite(S, 300, 304, None)

# ---- the record's runs, read without what an earlier design left in the file ----
raw = open(store._file("300")).read()
with open(store._file("390"), "w") as fh:
    fh.write('{\n "chains": {{{ not json,\n "thread_id": "390",' + raw[raw.rindex('\n "runs": {'):])
check("read(): a thread begun in the old design gives its runs; the chains before them are never parsed (the same file with its head made unreadable gives the same runs)",
      raw.index('"chains"') < raw.index('\n "runs": {') and list(store.read("300").runs) == ["301", "302", "303", "304"] and list(store.read("390").runs) == ["301", "302", "303", "304"]
      and store.read("300").thread_id == "300",
      (list(store.read("300").runs), list(store.read("390").runs)))
json.dump(json.load(open(store._file("300"))), open(store._file("391"), "w"), indent=2)
store.save(Notebook("392"))
open(store._file("393"), "w").close()
for name, of in (("395", "300"), ("396", "391")):                # the same two files with the line ends another system writes
    with open(store._file(name), "wb") as fh:
        fh.write(open(store._file(of), "rb").read().replace(b"\n", b"\r\n"))
check("read(): the file as the sign-in cleanup rewrites it (two spaces) reads the same, and so do both with other line ends; a file of the old design alone, one with no runs, an empty one and none at "
      "all hold no run",
      all(list(store.read(t).runs) == ["301", "302", "303", "304"] for t in ("391", "395", "396")) and store.read("391").runs["304"].turns[0].code == "print(load.describe())"
      and [list(store.read(t).runs) for t in ("200", "392", "393", "394")] == [[], [], [], []], [list(store.read(t).runs) for t in ("391", "395", "396")])
for t in ("390", "391", "392", "393", "395", "396"):
    os.remove(store._file(t))

# ---- before the first refresh, and the first refresh ----
check("view() builds nothing: before the first refresh it is empty and says it was never built", memory.view(S) == {"format": memory.FORMAT, "built": None, "runs": [], "steps": {}, "not_read": {}}, memory.view(S))
v = memory.refresh(S)
by = {r["id"]: r for r in v["runs"]}
check("what is memory: the saved runs on record with a report, the newest first - not an unsaved run, not a branch beside, not the run that stopped to ask, not a list of questions, not a chain of the old design",
      [r["id"] for r in v["runs"]] == ["300/304", "300/303", "300/302", "100/106", "100/103", "100/102"], [r["id"] for r in v["runs"]])
check("what is not read is counted by reason: two chains of the old design, one in a thread continued since and one whose thread has no record; a list of questions; a run without a report",
      v["not_read"] == {"older": 4, "questions": 1, "no_report": 1}, v["not_read"])
check("the marks: picked, alongside, none for a chain saved before the marks - and routine where one was made from the run",
      [by[i]["marks"] for i in ("100/102", "100/103", "300/304")] == [["picked", "routine"], ["alongside"], []], {i: r["marks"] for i, r in by.items()})
check("a run's record: the question, the title, the report whole, when it was asked, its replay, and nothing of the page's copy",
      (by["100/102"]["question"], by["100/102"]["title"], by["100/102"]["kind"], by["100/102"]["thread"], by["100/102"]["run"]) == ("Does the drift grow over the block?", "The drift grows over the block", "analysis", "100", "102")
      and by["100/102"]["report"].endswith("the per-session drift [cell 2].") and by["100/102"]["when"] == "2026-09-21T14:13:22Z"
      and by["300/304"]["replay"] == "reproduced" and "xxxx" not in json.dumps(v), by["100/102"])
check("the cells: the code, the RESULT lines and what was printed, numbered along the path",
      by["100/103"]["cells"] == [{"n": 3, "code": "late = weekly.tail(4)\nRESULT('late rise', fit(late).slope)", "results": ["late rise: +0.1 points"], "printed": "0.1\n"}], by["100/103"]["cells"])
check("a long printout is cut at PRINTED characters and the cut is said; the cell that drew the figures and an attempt that failed are not there",
      [c["n"] for c in by["300/304"]["cells"]] == [1] and by["300/304"]["cells"][0]["printed"].startswith("line\n" * 600)
      and by["300/304"]["cells"][0]["printed"].endswith("\n... (7,000 more characters not kept)") and len(by["300/304"]["cells"][0]["printed"]) < memory.PRINTED + 60,
      by["300/304"]["cells"][0]["printed"][-80:])
check("the data a run ran on: the file, the rows, the period, the columns' names, and whose it is by the source's id - never a name",
      by["300/304"]["data"] == {"name": "sessions.csv", "rows": 412, "period": "2026-01-01 to 2026-06-30", "columns": ["session", "load"], "subject": "p-7"}
      and by["100/102"]["data"] == by["300/303"]["data"] == {"name": "", "rows": None, "period": "", "columns": [], "subject": ""} and "First Person" not in json.dumps(v), by["300/304"]["data"])
check("the earlier steps: a run's path names them, the first one first; one that is memory itself is not repeated among the steps; an unsaved one is a step - its question and its cells, with the helper it defined, never its report",
      by["100/102"]["path"] == ["100/101"] and by["100/103"]["path"] == ["100/101", "100/102"] and "100/102" not in v["steps"]
      and v["steps"]["100/101"] == {"question": "How is the drift computed per session?", "cells": [{"n": 1, "code": HELPER, "results": ["sessions with a drift: 40"], "printed": "40\n"}]}
      and "Drift is a slope" not in json.dumps(v), v["steps"].get("100/101"))
check("the run that stopped to ask is a step of the run that answered it, with what the analyst asked",
      by["100/106"]["path"] == ["100/101", "100/102", "100/103", "100/105"]
      and v["steps"]["100/105"] == {"question": "Which weeks count as the taper?", "analyst_asked": "The plan names no taper. Is it the last two weeks or the last three?",
                                    "cells": [{"n": 4, "code": "print(weekly.index[-6:])", "results": [], "printed": "six weeks\n"}]}, v["steps"].get("100/105"))
check("a branch beside a saved run is nowhere in the view: not a run, not a step, none of its words", "100/104" not in by and "100/104" not in v["steps"] and "turbo" not in json.dumps(v).lower())
check("a parent that is not on record: the path stops there and the run says its chain is broken; a whole chain says nothing",
      by["300/303"]["path"] == [] and by["300/303"].get("broken") is True and all("broken" not in by[i] for i in by if i != "300/303"), by["300/303"])
check("a synthesis is memory, marked as one, and its question - the app's request, not the person's - is left empty",
      (by["300/302"]["kind"], by["300/302"]["question"], by["300/302"]["title"]) == ("synthesis", "", "Sleep and load together explain the drift")
      and memory.SYNTHESIS in open(os.path.join(ROOT, "bambooai", "bambooai.py"), encoding="utf-8").read(), by["300/302"])

# ---- how it is kept ----
kept_path = os.path.join(S, "memory", "view.json")
kept = json.load(open(kept_path))
check("the view is kept in one file under the user's storage, by thread, with what each thread's files looked like when they were read; view() gives what refresh() gave",
      kept["format"] == memory.FORMAT and sorted(kept["threads"]) == ["100", "200", "250", "300"] and sorted(kept["threads"]["100"]["sig"]["saved"]) == ["102", "103", "105", "106"]
      and kept["threads"]["250"]["sig"]["record"] is None
      and kept["threads"]["200"] == {"sig": kept["threads"]["200"]["sig"], "runs": [], "steps": {}, "not_read": {"older": ["201", "202"]}}
      and memory.view(S) == v and not [f for f in os.listdir(os.path.dirname(kept_path)) if f != "view.json"], sorted(kept["threads"]))

reads = []
_read = NotebookStore.read
NotebookStore.read = lambda self, thread: reads.append(thread) or _read(self, thread)
stamp = os.stat(kept_path).st_mtime_ns
again = memory.refresh(S)
check("a refresh with nothing changed reads no thread and writes nothing", reads == [] and again == v and os.stat(kept_path).st_mtime_ns == stamp, reads)
time.sleep(0.01)
favourite(S, 300, 304, "individual", pane=1200)
again = memory.refresh(S)
check("a favourite saved again: its thread alone is read again, and the mark follows", reads == ["300"] and {r["id"]: r["marks"] for r in again["runs"]}["300/304"] == ["picked"], reads)
path304 = os.path.join(S, "favourites", "300", "304.json")
size, stamp304 = os.path.getsize(path304), os.stat(path304)
time.sleep(0.01)
favourite(S, 300, 304, "trajectory", pane=1200)               # the same size, written later
later = (os.path.getsize(path304) == size, {r["id"]: r["marks"] for r in memory.refresh(S)["runs"]}["300/304"])
stamp304 = os.stat(path304)
favourite(S, 300, 304, "individual", pane=1300)               # another size, and the file's time put back
os.utime(path304, ns=(stamp304.st_atime_ns, stamp304.st_mtime_ns))
check("a file has changed when its time or its size has: a favourite written again at the same size is read again, and so is one of another size whose time was put back",
      later == (True, ["alongside"]) and os.stat(path304).st_mtime_ns == stamp304.st_mtime_ns and {r["id"]: r["marks"] for r in memory.refresh(S)["runs"]}["300/304"] == ["picked"], later)
E = tempfile.mkdtemp(prefix="bamboo_memory_empty_")
check("a storage with nothing saved: the refresh keeps an empty view, which says when it was built",
      memory.refresh(E)["built"] is not None and os.path.exists(os.path.join(E, "memory", "view.json")) and memory.view(E)["runs"] == [] and memory.view(E)["built"] is not None)
del reads[:]
nb4 = Notebook("400")
add(nb4, "401", "Is the cadence lower on climbs?", report="# Cadence drops on climbs\n\nCadence is 8 rpm lower on climbs [cell 1].", cells=[("c = df.groupby('climb').cadence.mean()", "", ["gap: -8 rpm"])], at=11)
store.save(nb4)
favourite(S, 400, 401)
again = memory.refresh(S)
check("a workflow saved since: its thread is read, the others are not, and its run is the newest", reads == ["400"] and [r["id"] for r in again["runs"]][0] == "400/401", reads)
del reads[:]
add(nb4, "402", "And on the flat?", parent="401", report="# Flat is the same\n\nNo gap on the flat [cell 2].", at=12)
store.save(nb4)
again = memory.refresh(S)
check("a run added to a saved thread is no memory until it is saved: the record changed, so the thread is read again - and the view has the same runs",
      reads == ["400"] and "400/402" not in {r["id"] for r in again["runs"]} and len(again["runs"]) == 7, reads)
NotebookStore.read = _read

# the mark is read from the head of the favourite file
_load = json.load
json.load = lambda fh, *a, **k: (_ for _ in ()).throw(AssertionError("the favourite was read whole"))
try:
    big = favourite(S, 900, 901, "trajectory", pane=3_000_000)
    marks = [memory._mark(big), memory._mark(favourite(S, 900, 902, None)), memory._mark(favourite(S, 900, 903, keyed=False))]
finally:
    json.load = _load
long_task = memory._mark(favourite(S, 900, 904, "individual", task="why " * 20_000))
check("a favourite's mark is read from the head of its file, megabytes of the page's copy unread; a file whose head does not reach the mark is read whole; no mark, or none written, reads as none",
      marks == ["alongside", "", ""] and long_task == "picked" and os.path.getsize(big) > 6_000_000, (marks, long_task))
shutil.rmtree(os.path.join(S, "favourites", "900"))

# ---- what leaves ----
os.remove(os.path.join(S, "favourites", "100", "103.json"))
gone = memory.view(S)
gby = {r["id"]: r for r in gone["runs"]}
check("a chain removed from a saved workflow leaves memory at once, before any refresh: it is no run, and stays only as a step of the saved run built on it - its question and cells, not its report",
      "100/103" not in gby and gby["100/106"]["path"] == ["100/101", "100/102", "100/103", "100/105"]
      and gone["steps"]["100/103"] == {"question": "And in the last four weeks?", "cells": by["100/103"]["cells"]} and "last four weeks are flat" not in json.dumps(gone), gone["steps"].get("100/103"))
after = memory.refresh(S)
check("... and the refresh after it writes the same view", unbuilt(after) == unbuilt(gone) and "103" not in json.load(open(kept_path))["threads"]["100"]["sig"]["saved"], [r["id"] for r in after["runs"]])
os.remove(os.path.join(S, "favourites", "200", "201.json"))
check("a removed chain that was not read leaves the count", memory.view(S)["not_read"] == {"older": 3, "questions": 1, "no_report": 1}, memory.view(S)["not_read"])
shutil.rmtree(os.path.join(S, "favourites", "100"))
gone = memory.view(S)
check("a workflow removed leaves memory at once, with its thread: no run of it, no step of it, nothing of it counted",
      not [r for r in gone["runs"] if r["thread"] == "100"] and not [s for s in gone["steps"] if s.startswith("100/")] and gone["not_read"] == {"older": 3, "questions": 1}
      and "drift grows" not in json.dumps(gone), [r["id"] for r in gone["runs"]])
after = memory.refresh(S)
check("... and after the refresh the kept file holds nothing of it", unbuilt(after) == unbuilt(gone) and "100" not in json.load(open(kept_path))["threads"] and "drift grows" not in open(kept_path).read())

# ---- a kept file that cannot be used, another user ----
good = open(kept_path).read()
open(kept_path, "w").write(json.dumps({"format": memory.FORMAT + 1, "threads": {"100": {"runs": [{"id": "100/102"}]}}}))
other_format = memory.view(S)
unreadable = []
for text in ("{ not json", "[]", ""):
    open(kept_path, "w").write(text)
    unreadable.append(memory.view(S))
check("a kept file in another format, or one that cannot be read, is an empty view - and the next refresh builds it again",
      other_format["runs"] == [] and other_format["built"] is None and all(v["runs"] == [] and v["built"] is None for v in unreadable) and unbuilt(memory.refresh(S)) == unbuilt(after) and json.loads(open(kept_path).read())["threads"] == json.loads(good)["threads"])
S2 = tempfile.mkdtemp(prefix="bamboo_memory_other_")
nb5 = Notebook("500")
add(nb5, "501", "What is the other coach asking?", report="# Theirs\n\nTheirs alone [cell 1].", at=13)
NotebookStore(S2).save(nb5)
favourite(S2, 500, 501)
check("a view is one user's: another storage folder gives its own runs and none of these", [r["id"] for r in memory.refresh(S2)["runs"]] == ["500/501"] and "500/501" not in {r["id"] for r in memory.refresh(S)["runs"]})

# ---- without writing: the command line's way ----
S4 = tempfile.mkdtemp(prefix="bamboo_memory_dry_")
nb7 = Notebook("700")
add(nb7, "701", "Does the taper help?", report="# The taper helps\n\nIt helps [cell 1].", at=14)
add(nb7, "702", "By how much?", parent="701", report="# By two percent\n\nTwo percent [cell 1].", at=15)
NotebookStore(S4).save(nb7)
favourite(S4, 700, 701)
dry = memory.refresh(S4, keep=False)
no_folder = not os.path.exists(os.path.join(S4, "memory"))
first = memory.refresh(S4)
stamp = os.stat(os.path.join(S4, "memory", "view.json")).st_mtime_ns
favourite(S4, 700, 702, "trajectory")
dry2 = memory.refresh(S4, keep=False)
check("refresh(keep=False) gives the view as it would be kept and writes nothing: no file before the first kept refresh, and the kept file untouched after it - `built` still its own time",
      [r["id"] for r in dry["runs"]] == ["700/701"] and dry["built"] is None and no_folder and unbuilt(dry) == unbuilt(first) and first["built"] is not None
      and [r["id"] for r in dry2["runs"]] == ["700/702", "700/701"] and dry2["built"] == first["built"] and os.stat(os.path.join(S4, "memory", "view.json")).st_mtime_ns == stamp
      and [r["id"] for r in memory.view(S4)["runs"]] == ["700/701"] and os.listdir(os.path.join(S4, "memory")) == ["view.json"], (dry["built"], [r["id"] for r in dry2["runs"]]))

# ---- something is saved while the threads are read ----
_thread, rounds = memory._thread, []


def meanwhile(store_, storage, thread, chains):
    rounds.append((thread, list(chains)))
    if len(rounds) == 1:
        favourite(S4, 700, 702, "individual")                 # saved while the first pass reads
    return _thread(store_, storage, thread, chains)


os.remove(os.path.join(S4, "favourites", "700", "702.json"))
memory.refresh(S4)
favourite(S4, 700, 701, "trajectory")
memory._thread = meanwhile
caught_up = memory.refresh(S4)
memory._thread = _thread
check("what is saved while a refresh reads is not missed: the threads are gone through once more, and what is written was true when it was written",
      rounds == [("700", ["701"]), ("700", ["701", "702"])] and {r["id"]: r["marks"] for r in caught_up["runs"]} == {"700/701": ["alongside"], "700/702": ["picked"]} and memory.view(S4) == caught_up, rounds)

# ---- behind the request ----
logged = []
quiet = logging.Handler()
quiet.emit = lambda record: logged.append(record.getMessage())
logging.getLogger("analyst.memory").addHandler(quiet)
logging.getLogger("analyst.memory").propagate = False
calls, release = [], threading.Event()
_refresh = memory.refresh


def slow(storage):
    calls.append(storage)
    release.wait(5)
    if len(calls) == 1:
        raise RuntimeError("the first pass fails")
    return _refresh(storage)


memory.refresh = slow
favourite(S, 400, 402, "trajectory")
t0 = time.time()
for _ in range(5):
    memory.refresh_soon(S)
asked_in = time.time() - t0
release.set()
deadline = time.time() + 5
while (S in memory._again or len(calls) < 2) and time.time() < deadline:
    time.sleep(0.01)
_start = threading.Thread.start
threading.Thread.start = lambda self: (_ for _ in ()).throw(RuntimeError("can't start new thread"))
try:
    refused = memory.refresh_soon(S)
finally:
    threading.Thread.start = _start
no_thread = (refused, S in memory._again)
memory.refresh = _refresh
check("refresh_soon() with no thread to be had does not fail the request, and leaves the folder free for the next one to ask; it is logged, as the pass that failed was",
      no_thread == (None, False) and logged == ["The memory view was not brought up to date"] * 2, (no_thread, logged))
check("refresh_soon() returns at once and works behind: asked five times while one pass is at work, it goes round once more and no further; a pass that fails is logged, not raised, and the next one stands",
      asked_in < 0.5 and calls == [S, S] and S not in memory._again and "400/402" in {r["id"] for r in memory.view(S)["runs"]}, (asked_in, calls))

# ---- plain keyword search ----
S3 = tempfile.mkdtemp(prefix="bamboo_memory_search_")
nb6 = Notebook("600")
add(nb6, "601", "How is the drift computed per session?", cells=[(HELPER, "40\n", ["sessions with a drift: 40"])], at=1,
    report="# Drift is a slope per session\n\nThe drift is the slope of hr against power in a session [cell 1]. The analysis uses every session of the block.")
add(nb6, "602", "Does it grow over the block?", parent="601", at=2, cells=[("weekly = per_session.resample('W').median()\nif len(weekly):\n    hr_drift_fit = fit(weekly)", "0.8\n", ["rise per week: +0.8 points"])],
    report="# The decoupling grows over the block\n\nThe analysis finds a rise of 0.8 points a week [cell 2].\n\n## How it was established\n\n" + "The analysis fits a line through the weekly medians. " * 9
           + "The threshold for a session to count was twenty minutes of steady riding. " + "The line was fitted by least squares. " * 12)
add(nb6, "603", "Is the cadence lower on climbs?", at=3, cells=[("c = df.groupby('climb').cadence.mean()\nrpm_delta_uphill = c.diff()", "", ["gap on climbs: -8 rpm"])],
    report="# Cadence drops on climbs\n\nThe analysis shows cadence 8 rpm\nlower on climbs [cell 1].")
add(nb6, "604", "Does sleep explain the Größe of the gap?", at=4, report="# Sleep explains a third\n\nThe analysis gives sleep a third of it [cell 1].",
    cells=[("m = ols(gap ~ sleep)", "", ["r2: 0.33"]), ("m = ols(gap ~ sleep)\nprint(m.params)", "", ["slope of nights: 0.4"])])
add(nb6, "605", "Is the drift the same on the turbo?", parent="601", at=5, report="# Turbo sessions drift more\n\nUnsaved [cell 2].", cells=[("turbo_only = 1", "", [])])
NotebookStore(S3).save(nb6)
for chain in (602, 603, 604):
    favourite(S3, 600, chain, "trajectory")
sv = memory.refresh(S3)
ids = lambda q, **k: [h["id"] for h in memory.search(sv, q, **k)]             # noqa: E731
hit = memory.search(sv, "cadence on climbs")[0]
check("search(): a hit carries the run's id, when, question, title and marks, the words it holds and its score",
      {k: hit[k] for k in ("id", "thread", "run", "kind", "when", "question", "title", "marks", "words")}
      == {"id": "600/603", "thread": "600", "run": "603", "kind": "analysis", "when": "2026-09-21T14:13:23Z", "question": "Is the cadence lower on climbs?", "title": "Cadence drops on climbs",
          "marks": ["alongside"], "words": ["cadence", "on", "climbs"]} and hit["score"] > 0, hit)
check("search(): a word is found in the question, the title, the report, a result line and the code - whatever the case, and where a word of the run starts with it",
      ids("SLEEP") == ["600/604"] and ids("decoupling") == ["600/602"] and ids("squares") == ["600/602"] and ids("rpm") == ["600/603"] and ids("resample") == ["600/602"]
      and ids("climb") == ["600/603"] and ids("größe") == ["600/604"], [ids(q) for q in ("SLEEP", "decoupling", "squares", "rpm", "resample", "climb", "größe")])
check("search(): a name in the code is found by its parts, wherever in the name they stand, and a name asked for is asked for by its parts; a word inside another word is not found",
      ids("drift fit") == ["600/602"] and ids("delta") == ids("uphill") == ["600/603"] and ids("fit_drift") == ["600/602"] and ids("eep") == [] and ids("limbs") == [],
      (ids("drift fit"), ids("delta"), ids("uphill"), ids("fit_drift"), ids("eep")))
check("search(): a word of an earlier step's question finds the run built on it, though the run never says it - the step itself, unsaved, is no hit",
      ids("computed") == ["600/602"] and "600/601" not in ids("drift session computed slope"), ids("computed"))
check("search(): an unsaved branch is never found, nor a word no run holds; an empty query, or one of single letters, finds nothing",
      ids("turbo") == [] and ids("zebra") == [] and ids("") == [] and ids("a b ?") == [] and memory.search({"runs": [], "steps": {}}, "drift") == [])
scores = {h["id"]: h["score"] for h in memory.search(sv, "analysis climbs")}
check("search(): a word every run holds counts for little: 'analysis' alone ranks nothing above the rest, and beside a rare word the runs that hold only it are left out as far weaker",
      len(set(h["score"] for h in memory.search(sv, "analysis"))) == 1 and ids("analysis") == ["600/604", "600/603", "600/602"] and list(scores) == ["600/603"], scores)
order = memory.search(sv, "gap")
check("search(): the best first - a word in the question counts for more than the same word in a result line; `most` bounds the list",
      [h["id"] for h in order] == ["600/604", "600/603"] and abs(order[0]["score"] / order[1]["score"] - 1.5) < 0.02 and ids("gap sleep block") == ["600/604", "600/602"]
      and ids("gap sleep block", most=1) == ["600/604"], [(h["id"], h["score"]) for h in order])
p = memory.search(sv, "resample rise")[0]["passages"]
check("search(): the passages say where the words stand - the report, a cell's result line, a cell's code - the best first",
      p == [{"where": "report", "text": "The analysis finds a rise of 0.8 points a week [cell 2]."}, {"where": "cell 2", "text": "rise per week: +0.8 points"},
            {"where": "cell 2, code", "text": "weekly = per_session.resample('W').median()"}], p)
p = memory.search(sv, "analysis threshold")[0]["passages"]
check("search(): a long paragraph is cut around its rarest word - not the first one found - at words, the cuts marked",
      p[0]["where"] == "report" and p[0]["text"].startswith("...") and p[0]["text"].endswith("...") and "threshold for a session to count" in p[0]["text"]
      and len(p[0]["text"]) <= memory.PASSAGE_CHARS + 6, p)
p = memory.search(sv, "analysis threshold weekly rise")[0]["passages"]
check("search(): three passages at most, the weakest place left out", [x["where"] for x in p] == ["report", "report", "cell 2"], p)
p = memory.search(sv, "ols nights")[0]["passages"]
check("search(): a result line counts for more than a line of code, whichever comes first; the same line in two cells is one passage",
      p == [{"where": "cell 2", "text": "slope of nights: 0.4"}, {"where": "cell 1, code", "text": "m = ols(gap ~ sleep)"}], p)
check("search(): a line of code is given without its indent, and a paragraph that runs over lines as one line",
      memory.search(sv, "hr")[0]["passages"] == [{"where": "cell 2, code", "text": "hr_drift_fit = fit(weekly)"}]
      and memory.search(sv, "lower")[0]["passages"][0] == {"where": "report", "text": "The analysis shows cadence 8 rpm lower on climbs [cell 1]."}, memory.search(sv, "hr")[0]["passages"])
few = {"runs": [{"id": f"8/{k}", "thread": "8", "run": str(k), "kind": "analysis", "when": f"2026-02-0{k}T00:00:00Z", "question": "", "title": "", "marks": [], "cells": [], "path": [],
                 "report": report} for k, report in ((3, "The analysis is short.\n\nZebra crossings matter."), (2, "An analysis of load."), (1, "Another analysis."))], "steps": {}}
check("search(): of two places with a word each, the one with the rarer word comes first; a place is found whatever its case",
      memory.search(few, "analysis zebra")[0]["passages"] == [{"where": "report", "text": "Zebra crossings matter."}, {"where": "report", "text": "The analysis is short."}],
      memory.search(few, "analysis zebra")[0]["passages"])
unit = memory.search(sv, "resample")[0]["score"]
by_field = [round(memory.search(sv, word)[0]["score"] / unit, 2) for word in ("größe", "decoupling", "squares", "r2", "resample", "computed")]
check("search(): what a word counts for by where it stands - the question 3, the title 3, the report 2, a result line 2, the code 1, an earlier step's question 1 - and a word asked twice counts once",
      by_field == [3, 3, 2, 2, 1, 1] and memory.search(sv, "gap gap")[0]["score"] == memory.search(sv, "gap")[0]["score"], by_field)
check("search(): the question of an earlier step that is a saved run itself counts the same way: the run it was asked in first, then the run built on it",
      [h["id"] for h in memory.search(memory.refresh(S4), "taper")] == ["700/701", "700/702"] and memory.search(memory.view(S4), "taper")[1]["words"] == ["taper"], memory.search(memory.view(S4), "taper"))
many = {"runs": [{"id": f"9/{k}", "thread": "9", "run": str(k), "kind": "analysis", "when": f"2026-01-{k:02d}T00:00:00Z", "question": f"Is the tempo right in block {k}?", "title": "", "marks": [],
                  "report": "", "cells": [], "path": []} for k in range(12, 0, -1)], "steps": {}}
check("search(): ten hits unless asked for more or fewer", [len(memory.search(many, "tempo", **k)) for k in ({}, {"most": 12}, {"most": 3})] == [memory.MOST, 12, 3] and memory.MOST == 10)
words = " ".join(f"w{k}" for k in range(300))
cut = [memory._around(words, words.index(w)) for w in ("w0", "w150", "w299")]
check("a passage of a long text: at its start the cut is marked at the end only, at its end at the start only, between them at both - the place about a third in, whole words only - and a short text is given whole",
      not cut[0].startswith("...") and cut[0].endswith("...") and words.startswith(cut[0][:-3] + " ") and cut[2].startswith("...") and not cut[2].endswith("...") and words.endswith(" " + cut[2][3:])
      and cut[1].startswith("...") and cut[1].endswith("...") and f" {cut[1][3:-3]} " in words and 80 < cut[1].index("w150") < 130
      and all(memory.PASSAGE_CHARS - 12 < len(c) <= memory.PASSAGE_CHARS + 6 for c in cut) and memory._around("short enough", 6) == "short enough", [len(c) for c in cut])
p = memory.search(sv, "cadence")[0]["passages"]
check("search(): a heading is no passage, and a short paragraph is given whole", [x["text"] for x in p][0] == "The analysis shows cadence 8 rpm lower on climbs [cell 1]." and not [x for x in p if x["text"].startswith("#")], p)
os.remove(os.path.join(S3, "favourites", "600", "603.json"))
check("search(): a run removed since is not found", [h["id"] for h in memory.search(memory.view(S3), "cadence climbs")] == [])

# ---- from the command line ----
R = tempfile.mkdtemp(prefix="bamboo_memory_root_")
for user, storage in (("coach", S), ("other", S2), ("searcher", S3)):
    shutil.copytree(storage, os.path.join(R, "storage", user))
os.makedirs(os.path.join(R, "storage", "nobody", "threads"))
shutil.rmtree(os.path.join(R, "storage", "other", "memory"))    # a user whose view the app has not built yet
favourite(os.path.join(R, "storage", "searcher"), 600, 605)     # ... and one whose view the app has not brought up to date with a save
tool = lambda *args: subprocess.run([sys.executable, os.path.join(ROOT, "tools", "memory_view.py"), "--root", R, *args], capture_output=True, text=True)      # noqa: E731
files = lambda: sorted((os.path.join(d, f), os.stat(os.path.join(d, f)).st_mtime_ns) for d, _, fs in os.walk(R) for f in fs)                                   # noqa: E731
before = files()
built = time.strftime("built %Y-%m-%d %H:%M UTC", time.gmtime(json.load(open(os.path.join(R, "storage", "coach", "memory", "view.json")))["built"]))
everyone, one, found, nothing = tool(), tool("--user", "sea"), tool("--user", "sea", "block", "sleep"), tool("--user", "other", "zebra")
check("the tool lists every user with saved work: what is saved, what of it is memory, what is not read and why, and whether the view the app keeps is up to date",
      everyone.returncode == 0 and "user nobody" not in everyone.stdout
      and f"user coach\n  saved: 4 workflows, 9 runs\n  in memory: 5 runs of 2 workflows · not read: 3 in the old record format, 1 of questions only\n  the view the app keeps: {built}, up to date\n" in everyone.stdout
      and "user other\n  saved: 1 workflow, 1 run\n  in memory: 1 run of 1 workflow\n  the view the app keeps: not built yet\n" in everyone.stdout
      and "user searcher\n  saved: 1 workflow, 3 runs\n  in memory: 3 runs of 1 workflow\n  the view the app keeps: built " in everyone.stdout
      and everyone.stdout.count(", up to date\n") == 1 and everyone.stdout.count(", behind what is saved now\n") == 1, everyone.stdout + everyone.stderr)
check("the tool with a user (how the id begins is enough) lists the runs in memory, the newest first: the day, the question - of a synthesis, what it found - the marks, the id",
      one.returncode == 0 and one.stdout.rstrip().endswith("2026-09-21  Does sleep explain the Größe of the gap?  (alongside)  [600/604]\n2026-09-21  Does it grow over the block?  (alongside)  [600/602]")
      and "\n2026-09-21  Synthesis: Sleep and load together explain the drift  (alongside)  [300/302]\n" in tool("--user", "coa").stdout, one.stdout + one.stderr)
check("the tool with words searches that user's memory: the hits in order, each with its passages and where they stand; no match is said",
      found.returncode == 0 and "2 of 3 runs hold 'block sleep':" in found.stdout and found.stdout.index("1. 2026-09-21  Does sleep explain") < found.stdout.index("2. 2026-09-21  Does it grow over the block?")
      and "   report: The analysis gives sleep a third of it [cell 1]." in found.stdout and "   cell 1, code: m = ols(gap ~ sleep)" in found.stdout
      and "0 of 1 run hold 'zebra'." in nothing.stdout and "\n2. " not in tool("--user", "sea", "--most", "1", "block", "sleep").stdout, found.stdout + nothing.stdout)
check("the tool refuses what it cannot answer - no such user, a search without a user, no storage - and writes nothing anywhere",
      [(r.returncode, r.stderr.strip()) for r in (tool("--user", "zz"), tool("drift"))] == [(1, "0 users with saved work begin with 'zz'."), (1, "A search needs --user.")]
      and subprocess.run([sys.executable, os.path.join(ROOT, "tools", "memory_view.py"), "--root", os.path.join(R, "storage", "nobody")], capture_output=True, text=True).stderr.startswith("No storage/ under ")
      and files() == before, [f for f in files() if f not in before])

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
