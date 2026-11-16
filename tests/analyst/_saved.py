"""A storage folder as the app leaves one, for the tests of the saved analyses (test_memory.py, test_reader.py): a
run on a thread's record, a favourite file as the route writes it, a routine made from a chain."""
import json
import os

from analyst.notebook import Turn
from analyst.routines import SHAPE


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
