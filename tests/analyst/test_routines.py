"""Routines (docs/ROUTINES_DESIGN.md): the pure module, the promoter's prompt under the standing rule, the records a
run keeps, the host's propose/create path over a real kernel with a scripted promoter, and the store.
Run: python3 tests/analyst/test_routines.py"""
import os, sys, json, re, tempfile, shutil, glob
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.dirname(os.path.abspath(__file__)), ROOT, os.path.join(ROOT, "delve")]
import _stubs  # noqa: F401
import pandas as pd, numpy as np
from analyst import routines as rt
from analyst.notebook import Notebook, Turn, Run
from analyst.replay import assemble
from kernel import PersistentKernel

passed, failed = [], []
def check(name, cond, detail=""):
    (passed if cond else failed).append(name); print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {detail}"))

# ---- the RESULT line, read back ----
r = rt.parse_result_line("RESULT: (test H1) (corrects cell 3) log value, group B vs A within type: +0.16 (95% CI +0.14 to +0.18) log units, B higher")
check("parse_result_line: tags, what, the three numbers as printed, unit and direction",
      r and r["test"] == "H1" and r["corrects"] == "3" and r["what"] == "log value, group B vs A within type" and r["estimate"] == "+0.16" and r["low"] == "+0.14"
      and r["high"] == "+0.18" and r["unit"] == "log units" and r["direction"] == "B higher" and r["ci"] == 95 and not r["typed"], r)
r2 = rt.parse_result_line("RESULT: ratio: B over A: +1,234 (95% CI +1,100 to +1,400), up - typed: the numbers were written into the call, not computed")
check("parse_result_line: a colon inside the label, thousands separators, no unit, the typed mark",
      r2 and r2["what"] == "ratio: B over A" and r2["estimate"] == "+1,234" and rt.number(r2["estimate"]) == 1234 and r2["unit"] == "" and r2["direction"] == "up" and r2["typed"], r2)
r3 = rt.parse_result_line("RESULT: share of rows kept: +0.912")
check("parse_result_line: an estimate alone", r3 and r3["estimate"] == "+0.912" and r3["low"] is None and r3["unit"] == "" and r3["direction"] == "", r3)
check("parse_result_line: not a result line -> None; a blank -> None", rt.parse_result_line("hello world") is None and rt.parse_result_line("") is None)
lines = rt.result_lines_in("noise\nRESULT: a: +1 (95% CI +0 to +2) u, up\nmore\nRESULT: b: +2.50\n")
check("result_lines_in: every RESULT line in order", [x["what"] for x in lines] == ["a", "b"] and lines[1]["estimate"] == "+2.50")

# ---- expected lines from the kernel's records, keyed by position ----
cells = [Turn(kind="cell", cell_no=1, code="x", results=[{"text": "first: +1.0 (95% CI +0.5 to +1.5) u, up", "typed": False}]),
         Turn(kind="cell", cell_no=2, code="y", results=[]),
         Turn(kind="cell", cell_no=3, code="z", results=[{"text": "second: +2.0", "typed": True}, {"text": "third: +3.0", "typed": False}])]
exp = rt.expected_results(cells, [1, 3])
check("expected_results: (cell, index) identity, typed from the record, cells outside the script print nothing",
      [(e["cell"], e["index"], e["label"], e["typed"]) for e in exp] == [(1, 0, "first", False), (3, 0, "second", True), (3, 1, "third", False)] and exp[0]["low"] == "+0.5", exp)

# ---- the script: split, the INPUTS mark, the block ----
nb = Notebook("t")
run = nb.new_run("q")
run.turns = [Turn(kind="cell", cell_no=1, code="threshold = 155\nkept = df[df.v > threshold]\nprint(len(kept))", results=[]),
             Turn(kind="cell", cell_no=2, code="RESULT('rows above the line', float(len(kept)), None, None, 'rows', 'n/a')", results=[{"text": "rows above the line: +3", "typed": False}])]
script, order = assemble(run.cells(), "Done [cell 2].")
head, body, tail, nos = rt.split_script(script)
check("split_script: the preamble, the cells region with its markers, the reset tail; the cell numbers in order", nos == [1, 2] and head.startswith("# Assembled") and "RESULT" in head and body.startswith("\n# --- cell 1 ---") and tail.startswith("\n# --- the executor") and head + body + tail == script, (nos, body[:30], tail[:40]))
joined = rt.join_script(head, body, tail)
check("join_script: the INPUTS mark between the preamble and the first cell, nothing else changed", joined.replace(rt.INPUTS_MARK + "\n", "") == script and joined.count(rt.INPUTS_MARK) == 1)
filled = rt.with_inputs(joined, {"threshold": 155, "bands": [130, 145.5], "window": ["2026-01-01", "2026-03-31"], "flag": True, "who": "a'b"})
check("with_inputs: the block replaces the mark and is valid Python with the values intact",
      rt.INPUTS_MARK not in filled and "INPUTS = {" in filled and compile(filled.split("# --- cell 1 ---")[0], "s", "exec") and "'who': \"a'b\"" in filled and "'flag': True" in filled, filled[:600])
ns = {}; exec(rt.inputs_block({"a": [1, 2.5, "x"], "b": None}), ns)
check("inputs_block: round-trips the values", ns["INPUTS"] == {"a": [1, 2.5, "x"], "b": None})
try:
    rt.inputs_block({"a": {"nested": 1}}); bad = False
except ValueError:
    bad = True
check("inputs_block: a value that is not a plain literal is refused", bad)
check("keys_read: the keys a script reads, once each, in order", rt.keys_read("x = INPUTS['b'] + INPUTS[\"a\"] + INPUTS['b']") == ["b", "a"])

# ---- the promoter's reply and the edits ----
reply = """Here it is:
```json
{"name": "Rows above a line", "inputs": [{"key": "threshold", "label": "Threshold", "type": "number", "default": "155", "origin": "the analysis split at 155"}],
 "edits": [{"cell": 1, "find": "threshold = 155", "replace": "threshold = INPUTS['threshold']"}], "kept": ["nothing else"]}
```"""
obj = rt.parse_promoter(reply)
check("parse_promoter: a fenced object is read; defaults keep their text", obj["name"] == "Rows above a line" and obj["inputs"][0]["default"] == "155")
for t, why in (("no object here", "no JSON"), ("{\"inputs\": 3}", "not a list"), ("{\"a\": }", "invalid JSON")):
    try:
        rt.parse_promoter(t); ok = False
    except ValueError as exc:
        ok = why.split()[0].lower() in str(exc).lower()
    check(f"parse_promoter: {t[:12]!r} -> ValueError mentioning {why!r}", ok)
edited, applied, failed_groups = rt.apply_edits(body, obj["edits"])
check("apply_edits: a unique fragment in the named cell is replaced; nothing else moves", "threshold = INPUTS['threshold']" in edited and "threshold = 155" not in edited and len(applied) == 1 and not failed_groups and edited.replace("INPUTS['threshold']", "155") == body)
inputs, notes = rt.finish_inputs(obj["inputs"], edited, failed_groups)
check("finish_inputs: the default coerced to its type, origin kept", inputs == [{"key": "threshold", "label": "Threshold", "type": "number", "default": 155, "origin": "the analysis split at 155"}] and not notes, (inputs, notes))
# a group that fails leaves the script untouched for that input, and the input goes with a note
two = [{"cell": 1, "find": "threshold = 155", "replace": "threshold = INPUTS['t']"}, {"cell": 2, "find": "not in the cell", "replace": "INPUTS['t']"},
       {"cell": 1, "find": "kept = df[df.v > threshold]", "replace": "kept = df[df.v > threshold][INPUTS['cols']]"}]
e2, a2, f2 = rt.apply_edits(body, two)
check("apply_edits: an input's edits apply whole or not at all; an independent input still applies",
      "threshold = 155" in e2 and "INPUTS['t']" not in e2 and "INPUTS['cols']" in e2 and len(a2) == 1 and f2 and f2[0]["keys"] == ["t"] and "0 times in cell 2" in f2[0]["reason"], (e2, f2))
i2, n2 = rt.finish_inputs([{"key": "t", "label": "T", "type": "number", "default": 1}, {"key": "cols", "label": "Columns", "type": "choice", "default": ["v"], "multiple": True, "column": "name"},
                           {"key": "Bad Key", "label": "x", "type": "number", "default": 1}, {"key": "ghost", "label": "Ghost", "type": "number", "default": 2},
                           {"key": "u", "label": "U", "type": "unknown", "default": 1}], e2, f2)
check("finish_inputs: the failed input, the unread one, the bad key and the unknown type are left out with notes; the multiple choice keeps its column",
      [p["key"] for p in i2] == ["cols"] and i2[0]["multiple"] and i2[0]["column"] == "name" and len(n2) == 4 and any("could not be made an input" in n for n in n2) and any("never reads" in n for n in n2), (i2, n2))
check("unknown_keys: a key the script reads but no input declares", rt.unknown_keys("x = INPUTS['a'] + INPUTS['b']", [{"key": "a"}]) == ["b"])
stripped = rt.strip_keys(e2, body, a2, ["cols"])
check("strip_keys: dropping an input reverts its edits", stripped == body)
check("finish_inputs: at most five inputs are kept, with a note",
      (lambda ins, ns: len(ins) == 5 and any("first 5" in n for n in ns))(*rt.finish_inputs([{"key": f"k{i}", "label": f"K{i}", "type": "number", "default": i} for i in range(7)], " ".join(f"INPUTS['k{i}']" for i in range(7)), [])))
coerce = rt._coerce_default
check("defaults coerce to their types: number, numbers from text, a date window from text, a toggle from a word; the unreadable give None",
      coerce("number", "12.5", False) == 12.5 and coerce("number", "7", False) == 7 and coerce("numbers", "130, 145 155", False) == [130, 145, 155]
      and coerce("date_window", "2026-01-01 to 2026-03-31", False) == ["2026-01-01", "2026-03-31"] and coerce("toggle", "yes", False) is True
      and coerce("choice", ["a", "b"], False) == "a" and coerce("choice", "a, b", True) == ["a", "b"] and coerce("number", "abc", False) is None and coerce("date_window", "soon", False) is None)
check("defaults_of: key -> default", rt.defaults_of(inputs) == {"threshold": 155})
check("numbers written as a list in text - \"[18, 26]\", \"(9, 11)\" - read as the numbers (2026-10-12: a promoter wrote the default that way and the input was dropped)",
      coerce("numbers", "[18, 26]", False) == [18, 26] and coerce("numbers", "(9, 11)", False) == [9, 11] and coerce("numbers", "[18.5]", False) == [18.5] and coerce("numbers", "[]", False) is None)

# ---- the promoter's prompt under the standing rule (no task vocabulary), and its shape ----
sys.path.insert(0, os.path.join(ROOT, "tests", "analyst"))
_DOMAIN = re.compile(r"\b(athletes?|altitude|sea.level|heart.rate|HR|HRmax|hr_max|pace|runners?|race|marathon|venues?|surfaces?|terrain|km|laps?|weekly load|gap years|site name|F1|Formula|drivers?)\b", re.I)
import ast as _ast
tree = _ast.parse(open(os.path.join(ROOT, "analyst", "routines.py"), encoding="utf-8").read())
docs = set()
for node in _ast.walk(tree):
    b = getattr(node, "body", None)
    if isinstance(node, (_ast.Module, _ast.FunctionDef, _ast.ClassDef)) and b and isinstance(b[0], _ast.Expr) and isinstance(getattr(b[0], "value", None), _ast.Constant):
        docs.add(id(b[0].value))
strings = [n.value for n in _ast.walk(tree) if isinstance(n, _ast.Constant) and isinstance(n.value, str) and id(n) not in docs]
hits = sorted({m.group(0) for s in strings for m in _DOMAIN.finditer(s)})
check("standing rule: no string in analyst/routines.py (the promoter's prompt included) carries the tested tasks' vocabulary", not hits, hits)
u = rt.promoter_user("Q?", "The answer.", "df: 10 rows", "\n# --- cell 1 ---\nx = 1", ["- [cell 1] a: +1"], {"parameters": [{"key": "k", "default": 1}]})
check("promoter_user: the five sections, and the current inputs on a next version", all(s in u for s in ("QUESTION:\nQ?", "ANSWER SUMMARY:\nThe answer.", "DATA (", "THE SCRIPT (", "RESULT LINES THE CELLS RECORDED", "THE CURRENT VERSION'S INPUTS")) and '"key": "k"' in u)
check("PROMOTER_SYSTEM: asks for edits, not a retyped script; the five types; at most five; the reply's shape", all(s in rt.PROMOTER_SYSTEM for s in ("find/replace edits", "never by retyping", "at most five", "date_window", "toggle", '"edits"', "INPUTS = {...}")))

# ---- the check of a run ----
exp = [{"cell": 1, "index": 0, "label": "a", "estimate": "+1.0", "low": "+0.5", "high": "+1.5"}, {"cell": 2, "index": 0, "label": "b", "estimate": "+2", "low": None, "high": None}]
got_same = [{"estimate": "+1.0", "low": "+0.5", "high": "+1.5"}, {"estimate": "+2", "low": None, "high": None}]
check("check_lines: identical numbers reproduce", rt.check_lines(exp, got_same)[0] == "reproduced" and "2 result line(s) identical" in rt.check_lines(exp, got_same)[1])
check("check_lines: a different estimate differs, naming the line", rt.check_lines(exp, [{"estimate": "+1.1", "low": "+0.5", "high": "+1.5"}, got_same[1]])[0] == "differed" and "[cell 1] a: +1.0 -> +1.1" in rt.check_lines(exp, [{"estimate": "+1.1", "low": "+0.5", "high": "+1.5"}, got_same[1]])[1])
check("check_lines: a missing line differs by count; an error fails; nothing expected reproduces when it ran",
      rt.check_lines(exp, got_same[:1])[0] == "differed" and "1 result line(s) came back, 2 expected" in rt.check_lines(exp, got_same[:1])[1]
      and rt.check_lines(exp, [], "Traceback\nKeyError: 'x'")[0] == "failed" and "KeyError" in rt.check_lines(exp, [], "Traceback\nKeyError: 'x'")[1]
      and rt.check_lines([], [])[0] == "reproduced")
check("check_lines: the same value printed with a different sign of zero or separators still reproduces", rt.check_lines([{"estimate": "+1,234", "low": None, "high": None, "cell": 1, "index": 0, "label": "x"}], [{"estimate": "+1234", "low": None, "high": None}])[0] == "reproduced")

# ---- the records: a run keeps its data; the store ----
nb3 = Notebook.from_dict({"thread_id": "t3", "runs": {"r": {"id": "r", "parent": None, "question": "q", "turns": [], "report": "", "rewrite": "", "replay_status": "", "replay_script": "", "status": "answered", "created": 1.0}}})
check("Run.data: a thread file from before the field loads with an empty record", nb3.runs["r"].data == {})
nb3.runs["r"].data = {"df_id": "x", "source": "csv"}
check("Run.data: round-trips", Notebook.from_dict(json.loads(json.dumps(nb3.to_dict()))).runs["r"].data == {"df_id": "x", "source": "csv"})
tmp = tempfile.mkdtemp()
store = rt.RoutineStore(tmp)
rid = rt.new_id()
routine = {"id": rid, "name": "Rows above a line", "created": 1.0, "purpose": "p", "question": "q", "summary": "s", "origin": {"thread_id": "T", "chain_id": "C"}, "source": "file", "current_version": 1,
           "versions": [{"number": 1, "created": 1.0, "promoted_from": {"thread_id": "T", "chain_id": "C"}, "script": joined, "change_note": "first version",
                         "manifest": {"data": {"kind": "file", "name": "f.csv"}, "parameters": inputs, "results": [{"cell": 2, "index": 0, "label": "rows above the line", "typed": False, "dropped": False}], "figures": {"count": 0, "cells": []}},
                         "run_zero": {"status": "reproduced", "line": "reproduced: 1 result line(s) identical", "verified": True}}], "runs": []}
store.save(routine)
files = store.save_run_files(rid, "v1_0", "RESULT: rows above the line: +3\n", ['{"data": []}'])
loaded = store.load(rid)
check("RoutineStore: save, load, the run's files on disk, the list and its summaries", loaded and loaded["name"] == "Rows above a line" and os.path.exists(os.path.join(files["folder"], "stdout.txt")) and len(files["figures"]) == 1
      and [r["id"] for r in store.all()] == [rid] and store.summary(loaded)["inputs"] == 1 and store.summary(loaded)["results"] == 1 and store.summary(loaded)["verified"] and store.summary(loaded)["source"] == "file")
check("RoutineStore.by_origin: the versions born from a chain, for the favourite's card", store.by_origin() == {("T", "C"): [{"id": rid, "name": "Rows above a line", "version": 1}]})
check("script_with_defaults: the download carries the INPUTS block with the defaults", "INPUTS = {\n    'threshold': 155\n}" in rt.script_with_defaults(loaded["versions"][0]))
check("RoutineStore.delete: the folder goes; a second delete is False", store.delete(rid) and not store.load(rid) and not store.delete(rid) and store.all() == [])
check("source_kind: the executor's names map to the four kinds", rt.source_kind({"source": "csv"}) == "file" and rt.source_kind({"source": "intervals"}) == "intervals" and rt.source_kind({"name": "x.parquet"}) == "file" and rt.source_kind({}) == "none")

# ---- the host's path: propose and create over a real kernel with a scripted promoter ----
from bambooai import routines_host as host
df = pd.DataFrame({"v": [100, 150, 160, 170, 200], "g": ["a", "a", "b", "b", "b"]})
nb4 = Notebook("t4")
run4 = nb4.new_run("How many rows are above 155?")
run4.turns = [Turn(kind="cell", cell_no=1, code="threshold = 155\nkept = df[df.v > threshold]\nprint(len(kept))", results=[], stdout="3"),
              Turn(kind="cell", cell_no=2, code="RESULT('rows above the line', float(len(kept)), None, None, 'rows', 'n/a')", results=[{"text": "rows above the line: +3", "typed": False}], stdout="RESULT: rows above the line: +3")]
run4.report = "## Three rows\n\nThree rows lie above the line [cell 2]."
run4.status = "answered"
run4.data = {"df_id": "df4", "name": "small.csv", "source": "csv", "columns": [{"name": "v", "dtype": "int64"}, {"name": "g", "dtype": "object"}], "rows": 5, "aux": []}
run4.replay_script, _ = assemble(run4.cells(), run4.report)
nb4.runs[run4.id] = run4
prompts = []
def promoter_llm(system, user):
    prompts.append((system, user))
    return reply, {"cost": 0.02}
def runner(script, timeout):
    k = PersistentKernel(df=df)
    try:
        out, err, _ = k.execute(script)
    finally:
        k.cleanup()
    return out or "", err or "", [], []
events = []
p = host.propose(nb4, run4.id, promoter_llm, current_data={"df_id": "df4"}, emit=events.append)
check("propose: the promoter is called with the question, the cells and the ledger; the proposal carries the inputs, the results, the figures and the edited script",
      prompts and prompts[0][0] == rt.PROMOTER_SYSTEM and "How many rows" in prompts[0][1] and "- [cell 2] rows above the line: +3" in prompts[0][1]
      and p["name"] == "Rows above a line" and p["inputs"][0]["key"] == "threshold" and p["results"][0]["label"] == "rows above the line" and "INPUTS['threshold']" in p["script"] and p["data"]["name"] == "small.csv" and p["data_state"] == "same", (p.get("inputs"), p.get("data_state"), [e.get("type") for e in events]))
check("propose: the pane saw a quiet turn start and its end", [e.get("type") for e in events] == ["turn_start", "turn_end"] and events[0].get("quiet"))
made = host.create(nb4, p, {"name": "Rows above a line", "purpose": "count the rows above a line", "drop_inputs": [], "drop_results": []}, runner, store, emit=events.append)
check("create: run zero on the data reproduces the chain's line; the routine is stored with v1, its manifest and run zero; the origin is the chain",
      made["run_zero"]["status"] == "reproduced" and made["routine"]["current_version"] == 1 and made["routine"]["origin"] == {"thread_id": "t4", "chain_id": run4.id}
      and store.load(made["routine"]["id"])["versions"][0]["manifest"]["parameters"][0]["key"] == "threshold" and os.path.exists(os.path.join(store.path(made["routine"]["id"]), "runs", "v1_0", "stdout.txt")), made.get("run_zero"))
check("create: the pane saw the check start and end", [e.get("type") for e in events[2:]] == ["lookup_start", "lookup"] and events[-1].get("kind") == "routine" and "reproduced" in events[-1].get("peek", ""))
# dropping the one input reverts its edit; the script still reproduces
p2 = host.propose(nb4, run4.id, promoter_llm, current_data={"df_id": "df4"})
made2 = host.create(nb4, p2, {"name": "No inputs", "purpose": "", "drop_inputs": ["threshold"], "drop_results": []}, runner, store)
v = store.load(made2["routine"]["id"])["versions"][0]
check("create: a dropped input's edit is reverted and the routine has no inputs", v["manifest"]["parameters"] == [] and "INPUTS[" not in v["script"] and made2["run_zero"]["status"] == "reproduced")
# a rewrite that breaks the method is refused: run zero differs, nothing stored
def bad_promoter(system, user):
    return json.dumps({"name": "Broken", "inputs": [{"key": "threshold", "label": "T", "type": "number", "default": 165, "origin": "x"}],
                       "edits": [{"cell": 1, "find": "threshold = 155", "replace": "threshold = INPUTS['threshold']"}]}), {"cost": 0.0}
before = len(store.all())
p3 = host.propose(nb4, run4.id, bad_promoter, current_data={"df_id": "df4"})
try:
    host.create(nb4, p3, {"name": "Broken", "purpose": "", "drop_inputs": [], "drop_results": []}, runner, store); refused = None
except host.RoutineRefused as exc:
    refused = str(exc)
check("create: a rewrite whose run zero differs is refused, naming the line; nothing is stored", refused and "differ" in refused and "rows above the line" in refused and len(store.all()) == before, refused)
# the next version: the manifest rides to the promoter, the inputs carry over, v1 stays
p4 = host.propose(nb4, run4.id, promoter_llm, current_data={"df_id": "df4"}, routine=store.load(made["routine"]["id"]))
made4 = host.create(nb4, p4, {"name": "", "purpose": "", "drop_inputs": [], "drop_results": [], "change_note": "the same, again"}, runner, store, routine_id=made["routine"]["id"])
r4 = store.load(made["routine"]["id"])
check("next version: the promoter saw the current inputs; v2 is current, v1 stays; the change note is kept", "THE CURRENT VERSION'S INPUTS" in prompts[-1][1] and r4["current_version"] == 2 and len(r4["versions"]) == 2 and r4["versions"][1]["change_note"] == "the same, again" and made4["version"] == 2)
# the name on a next version (2026-10-12): the routine keeps its name unless the person typed another - the dialog used to send
# the promoter's title for the new chain, and a next version silently renamed the routine
made_n = host.create(nb4, host.propose(nb4, run4.id, promoter_llm, current_data={"df_id": "df4"}), {"name": "Rows above a line", "purpose": ""}, runner, store)
rid_n = made_n["routine"]["id"]
host.create(nb4, host.propose(nb4, run4.id, promoter_llm, current_data={"df_id": "df4"}, routine=store.load(rid_n)), {"name": "Rows above a line", "purpose": "", "change_note": "same name sent"}, runner, store, routine_id=rid_n)
same_name = store.load(rid_n)["name"]
host.create(nb4, host.propose(nb4, run4.id, promoter_llm, current_data={"df_id": "df4"}, routine=store.load(rid_n)), {"name": "Rows over a line", "purpose": "", "change_note": "renamed"}, runner, store, routine_id=rid_n)
check("next version: the routine's name stays when the name sent is its own; it is renamed when the person typed another",
      same_name == "Rows above a line" and store.load(rid_n)["name"] == "Rows over a line" and store.load(rid_n)["current_version"] == 3)
store.delete(rid_n)
# a follow-up asked after the data changed (2026-10-12): its parent's cells ran on other data - in its ledger, not in its
# computation - so the routine is made from its own cells, run zero reproduces them, and the proposal says what it continues
run4b = nb4.new_run("And on this data?", parent=run4.id)
run4b.turns = [Turn(kind="cell", cell_no=3, code="n_all = len(df)\nRESULT('rows in the frame', float(n_all), None, None, 'rows', 'n/a')", results=[{"text": "rows in the frame: +5", "typed": False}], stdout="RESULT: rows in the frame: +5")]
run4b.report = "## Five rows\n\nThe frame has five rows [cell 3]."
run4b.status = "answered"
run4b.data = {"df_id": "df4b", "name": "small_again.csv", "source": "csv", "columns": [{"name": "v", "dtype": "int64"}, {"name": "g", "dtype": "object"}], "rows": 5, "aux": []}
nb4.runs[run4b.id] = run4b
def as_is_promoter(system, user):
    return '{"name": "As is", "inputs": [], "edits": []}', {"cost": 0.0}
p4b = host.propose(nb4, run4b.id, as_is_promoter, current_data={"df_id": "df4b"}, runner=runner)
check("propose on a follow-up after a change of data: the script is the follow-up's own cell (the parent's cells, on other data, left out), one result line, and a note saying what the chain continues",
      p4b["cells"] == 1 and "# --- cell 3 ---" in p4b["script"] and "# --- cell 1 ---" not in p4b["script"] and "threshold = 155" not in p4b["script"]
      and [r["cell"] for r in p4b["results"]] == [3] and any("continues 1 earlier chain of the thread that ran on other data (cells 1-2): the method is this chain's own cell 3" in n for n in p4b["notes"]), (p4b["cells"], p4b["notes"], p4b["script"][-400:]))
made4b = host.create(nb4, p4b, {"name": "Rows in the frame", "purpose": ""}, runner, store)
check("...and run zero on the follow-up's data reproduces its line", made4b["run_zero"]["status"] == "reproduced" and made4b["routine"]["origin"]["chain_id"] == run4b.id, made4b["run_zero"])
store.delete(made4b["routine"]["id"])
# refusals before any model call
run5 = nb4.new_run("prose only"); run5.status = "answered"; nb4.runs[run5.id] = run5
for rid_, why in ((run5.id, "no cells"), ("nope", "not in this thread")):
    try:
        host.propose(nb4, rid_, promoter_llm, current_data={}); got = ""
    except host.RoutineRefused as exc:
        got = str(exc)
    check(f"propose: refused before any call - {why}", why in got, got)
# the data gone: the proposal says so, and create makes the routine unverified
p6 = host.propose(nb4, run4.id, promoter_llm, current_data={"df_id": "other"})
made6 = host.create(nb4, p6, {"name": "Unverified", "purpose": "", "drop_inputs": [], "drop_results": []}, None, store)
check("the analysis's data gone: the proposal says 'gone', run zero is skipped and the routine is created unverified, saying so",
      p6["data_state"] == "gone" and made6["run_zero"]["status"] == "unverified" and not made6["run_zero"]["verified"] and "not verified" in made6["run_zero"]["line"], (p6.get("data_state"), made6.get("run_zero")))
# a promoter whose reply cannot be read: one retry, then refusal
calls = {"n": 0}
def mute_promoter(system, user):
    calls["n"] += 1
    return "I cannot do that.", {"cost": 0.0}
try:
    host.propose(nb4, run4.id, mute_promoter, current_data={"df_id": "df4"}); got = ""
except host.RoutineRefused as exc:
    got = str(exc)
check("propose: an unreadable reply is asked for once more, then refused as 'not understood'", calls["n"] == 2 and "not understood" in got, (calls, got))
# a reply cut at the seat's token limit (the model layer's `truncated` flag): nothing but reasoning - refused at once, since a
# second try would go the same way; cut mid-object - asked for once more, shorter; cut twice - refused with the cause
cut_calls = []
def cut_promoter(replies):
    def f(system, user):
        cut_calls.append(user)
        text = replies.pop(0)
        return text, {"cost": 0.0, "truncated": True}
    return f
try:
    host.propose(nb4, run4.id, cut_promoter(["", ""]), current_data={"df_id": "df4"}); got = ""
except host.RoutineRefused as exc:
    got = str(exc)
check("propose: a reply with nothing but reasoning inside the limit is asked once more, with the note that reasoning took it all (2026-10-12); the same twice is refused, naming the limit and the seat to adjust",
      len(cut_calls) == 2 and "before anything but reasoning arrived" in cut_calls[1] and "cut off at its token limit" in got and "nothing arrived but reasoning" in got and "Promoter" in got, (len(cut_calls), got))
cut_calls.clear()
p8e = host.propose(nb4, run4.id, cut_promoter(["", '{"name": "As is", "inputs": [], "edits": []}']), current_data={"df_id": "df4"})
check("propose: nothing but reasoning, then a whole reply: the second is taken", len(cut_calls) == 2 and p8e["inputs"] == [] and p8e["name"] == "As is")
cut_calls.clear()
ok_json = '{"name": "As is", "inputs": [], "edits": []}'
def cut_then_fine(system, user):
    cut_calls.append(user)
    return (ok_json[:20], {"cost": 0.0, "truncated": True}) if len(cut_calls) == 1 else (ok_json, {"cost": 0.0})
p8 = host.propose(nb4, run4.id, cut_then_fine, current_data={"df_id": "df4"})
check("propose: a reply cut mid-object is asked for once more with the note that it was cut (and how much arrived), and the second reply is taken",
      len(cut_calls) == 2 and "cut off at the token limit" in cut_calls[1] and "20 characters arrived" in cut_calls[1] and "shorter" in cut_calls[1] and p8["inputs"] == [], cut_calls[-1][-200:])
cut_calls.clear()
try:
    host.propose(nb4, run4.id, cut_promoter([ok_json[:20], ok_json[:12]]), current_data={"df_id": "df4"}); got = ""
except host.RoutineRefused as exc:
    got = str(exc)
check("propose: cut twice is refused, the reason saying twice", len(cut_calls) == 2 and "cut off at its token limit twice" in got, (len(cut_calls), got))
# a promoter that declares nothing: the routine runs as it is
def empty_promoter(system, user):
    return '{"name": "As is", "inputs": [], "edits": []}', {"cost": 0.0}
p7 = host.propose(nb4, run4.id, empty_promoter, current_data={"df_id": "df4"})
check("propose: no inputs is a valid proposal - the method runs as it is", p7["inputs"] == [] and p7["script"].count("# --- cell") == 2)

# ---- step 2: a run on the data loaded now - the checks, the status, the comparison, the record ----
rid4 = made["routine"]["id"]
R = store.load(rid4)
data_now = {"df_id": "df4", "name": "small.csv", "source": "csv", "columns": [{"name": "v", "dtype": "int64"}, {"name": "g", "dtype": "object"}], "rows": 5, "aux": []}
def runner_on(frame):
    def _r(script, timeout):
        k = PersistentKernel(df=frame)
        try:
            out, err, _ = k.execute(script)
        finally:
            k.cleanup()
        return out or "", err or "", [], []
    return _r
pc = host.precheck(R, data_now, runner_on(df))
check("precheck: data loaded, fits the routine's columns, nothing missing - ok, with the line the dialog shows", pc["loaded"] and pc["ok"] and pc["fit"]["fits"] and pc["line"].startswith("fits the routine (2 of 2 columns)"), pc)
pc2 = host.precheck(R, {"df_id": None, "source": "none", "columns": []}, runner_on(df))
check("precheck with nothing loaded: not ok, says to load the data first", not pc2["loaded"] and not pc2["ok"] and "no data is loaded" in pc2["line"], pc2)
pc3 = host.precheck(R, {"df_id": "x", "columns": [{"name": "v", "dtype": "int64"}], "name": "other.csv"}, runner_on(df))
check("precheck with a column dropped: said, not refused - the run adds it empty (2026-10-10: conform); ok, the column named", pc3["ok"] and pc3["fit"]["fits"] and pc3["fit"]["missing"] == ["g"] and "1 of 2 columns empty in this data: g" in pc3["line"], pc3["line"])
pc3b = host.precheck(R, {"df_id": "x", "columns": [{"name": "q", "dtype": "int64"}], "name": "other.csv"}, runner_on(df))
check("precheck with none of the routine's columns: nothing to run on, refused", not pc3b["ok"] and not pc3b["fit"]["fits"] and "nothing to run on" in pc3b["line"], pc3b["line"])
pc4 = host.precheck(R, data_now, runner_on(df), values={"threshold": "abc"})
check("precheck with an unreadable value: the problem named, not ok", not pc4["ok"] and pc4["problems"] and "could not be read as a number" in pc4["line"], pc4["line"])
events = []
out1 = host.run(R, {}, data_now, runner_on(df), store, emit=events.append)
r1 = out1["run"]
check("run 1 on the same data with the defaults: reproduced against run zero, the record stored with its files, the routine lists it",
      r1["number"] == 1 and r1["status"] == "reproduced" and r1["against"] == 0 and r1["comparison"]["rows"][0]["mark"] == "same" and r1["comparison"]["compared"] == 1
      and store.load(rid4)["runs"][0]["number"] == 1 and os.path.exists(os.path.join(store.run_dir(rid4, "v2_1"), "run.json")) and os.path.exists(os.path.join(store.run_dir(rid4, "v2_1"), "stdout.txt"))
      and out1["numbers"] == [0, 1], (r1["status"], r1["line"], out1["numbers"]))
kinds = [(e.get("type"), e.get("kind")) for e in events]
check("the pane saw the check, the run and the comparison rows", kinds == [("lookup_start", "check"), ("lookup", "check"), ("lookup_start", "run"), ("lookup", "run"), ("lookup", "compare")]
      and events[1]["peek"].startswith("fits the routine") and events[3]["peek"].startswith("reproduced") and "with run 0" in events[4]["query"], (kinds, events[4]))
out2 = host.run(store.load(rid4), {"threshold": 165}, data_now, runner_on(df), store)
r2 = out2["run"]
check("run 2 with the threshold at 165: ran (the count changed), compared with run 1, the line marked down without intervals",
      r2["number"] == 2 and r2["status"] == "ran" and r2["against"] == 1 and r2["inputs"] == {"threshold": 165} and r2["results"][0]["estimate"] == "+2.00"
      and r2["comparison"]["rows"][0]["mark"] == "down" and r2["comparison"]["rows"][0]["change"] == -1.0 and r2["comparison"]["changed"] == 1 and "1 of 1 changed" in r2["comparison"]["line"], (r2["status"], r2["comparison"]))
out3 = host.run(store.load(rid4), {"threshold": 165}, data_now, runner_on(df), store, compare_with="zero")
check("compare with run zero on request: against 0, the same change", out3["run"]["against"] == 0 and out3["run"]["comparison"]["rows"][0]["mark"] == "down" and out3["run"]["status"] == "ran")
out4 = host.run(store.load(rid4), {"threshold": 165}, data_now, runner_on(df), store)
check("the same values on the same data again: reproduced against the run before", out4["run"]["status"] == "reproduced" and out4["run"]["against"] == 3)
before = len(store.load(rid4)["runs"])
try:
    host.run(store.load(rid4), {}, {"df_id": "x", "name": "other.csv", "columns": [{"name": "q", "dtype": "int64"}]}, runner_on(df.rename(columns={"v": "q", "g": "h"})), store); refused = ""
except host.RoutineRefused as exc:
    refused = str(exc)
check("a file with none of the routine's columns: refused before anything runs, no run recorded", "does not fit" in refused and "nothing to run on" in refused and len(store.load(rid4)["runs"]) == before, refused)
# a file with one column dropped: the run adds it empty (the conform prelude) and the method runs; the record says what was missing
ev_drop = []
out_drop = host.run(store.load(rid4), {}, {"df_id": "x", "name": "other.csv", "columns": [{"name": "v", "dtype": "int64"}]}, runner_on(df.drop(columns=["g"])), store, emit=ev_drop.append)
check("a file with a column dropped: the CHECK row says the column is empty in this data, the method runs on the frame with it added empty, the record keeps the fit",
      out_drop["run"]["status"] in ("ran", "reproduced", "differed") and out_drop["run"]["fit"]["missing"] == ["g"] and any(e.get("kind") == "check" and "empty in this data: g" in (e.get("peek") or "") for e in ev_drop)
      and "_ROUTINE_COLUMNS" in rt.with_inputs(host.prepare(host.version_of(store.load(rid4)), {"columns": []}, None, "r")["script"], {}, host.prepare(host.version_of(store.load(rid4)), {"columns": []}, None, "r")["prelude"]),
      (out_drop["run"]["status"], out_drop["run"]["line"], [e.get("peek") for e in ev_drop if e.get("kind") == "check"]))
def broken_runner(script, timeout):
    return "", 'Traceback (most recent call last):\n  File "<string>", line 999, in <module>\nKeyError: \'v\'', [], []
out5 = host.run(store.load(rid4), {}, data_now, broken_runner, store)
check("a script error: the run is kept with status failed, naming the cell; its line not printed is 'not reached', not missing; the failed cell's code is on the record (step 4)",
      out5["run"]["status"] == "failed" and out5["run"]["line"].startswith("failed at cell 2:") and out5["run"]["comparison"]["missing"] == 0 and out5["run"]["comparison"]["unreached"] == 1
      and out5["run"]["comparison"]["rows"][0]["mark"] == "unreached" and "not reached" in out5["run"]["comparison"]["line"]
      and out5["run"]["failed_cell"]["number"] == 2 and "RESULT(" in out5["run"]["failed_cell"]["code"] and "# --- cell" not in out5["run"]["failed_cell"]["code"]
      and store.load(rid4)["runs"][-1]["status"] == "failed" and store.load(rid4)["runs"][-1]["comparison"]["unreached"] == 1, (out5["run"]["line"], out5["run"]["comparison"], out5["run"].get("failed_cell")))
# the lines printed before a failure are compared like any other (step 4, 2026-10-11): a runner that prints the first line and dies
def half_runner(script, timeout):
    return "RESULT: rows above the line: +3\n", 'Traceback (most recent call last):\n  File "<string>", line 999, in <module>\nKeyError: \'v\'', [], []
_m4 = store.load(rid4)
_exp4 = host.version_of(_m4)["manifest"]["results"]
_cmp_half = rt.compare_runs(_exp4 + [dict(_exp4[0], index=1, label="a second line", estimate="4")], [{"estimate": "3", "low": None, "high": None}], [{"estimate": "3", "low": None, "high": None}, {"estimate": "4", "low": None, "high": None}], failed=True)
check("compare_runs of a failed run: the line printed before the failure compared (same), the one after it not reached; the line says so",
      [r["mark"] for r in _cmp_half["rows"]] == ["same", "unreached"] and _cmp_half["compared"] == 1 and _cmp_half["unreached"] == 1 and _cmp_half["missing"] == 0
      and _cmp_half["line"] == "0 of 1 changed before the failure, 1 not reached", _cmp_half)
check("compare_runs: without a reference, a failed run's unreached lines are counted in the line; a completed run's absent line is still 'missing'",
      "1 line not reached" in rt.compare_runs(_exp4, [], None, failed=True)["line"] and rt.compare_runs(_exp4, [], [{"estimate": "3"}], failed=False)["rows"][0]["mark"] == "missing"
      and rt.compare_runs(_exp4, [], [{"estimate": "3"}], failed=True)["line"] == "no result line came before the failure (1 not reached)")
check("cell_text: a cell's code from the script without its marker; nothing for a cell that is not there",
      rt.cell_text("# --- cell 1 ---\na = 1\n\n# --- cell 2 ---\nb = 2\n_bamboo_capture[0] = True\n\n# --- the executor's own display options back ---\npd.reset_option('x')\n", 2) == "b = 2\n_bamboo_capture[0] = True"
      and rt.cell_text("# --- cell 1 ---\na = 1\n", 1) == "a = 1" and rt.cell_text("# --- cell 1 ---\na = 1\n", 3) == "")
out6 = host.run(store.load(rid4), {}, data_now, lambda s, t: ("", "TIMEOUT: Code execution exceeded 300 seconds.", [], []), store)
check("a timeout: status timed_out", out6["run"]["status"] == "timed_out" and out6["run"]["line"].startswith("timed out"))
R6 = store.load(rid4)
ref_after_failures = host.reference_run(R6, host.version_of(R6), "previous")
check("the reference skips failed and timed-out runs: the last run that ran", ref_after_failures[0] == 5, ref_after_failures[0])
# ---- the data made to fit the recorded shape (2026-10-10): a method that reads a loader's auxiliary file by its dated name ----
aux_dir = os.path.join(tempfile.mkdtemp(), "datasets", "local")
os.makedirs(aux_dir)
aux_old = os.path.join(aux_dir, "activity_summary_20260812_to_20261010.csv")
pd.DataFrame({"hour": [6, 6, 7, 18], "load": [1.0, 2.0, 3.0, 4.0], "note": ["a", "b", "c", "d"]}).to_csv(aux_old, index=False)
nb5 = Notebook("t5")
run5 = nb5.new_run("At what hour do most sessions start?")
run5.turns = [Turn(kind="cell", cell_no=1, code=f"summ = pd.read_csv({aux_old!r})\nn = int(len(summ))\npeak = int(summ.hour.value_counts().idxmax())\nprint(n, peak)", results=[], stdout="4 6"),
              Turn(kind="cell", cell_no=2, code="RESULT('sessions in the file', float(n), None, None, 'sessions', 'n/a')\nRESULT('the hour most sessions start', float(peak), None, None, 'hour', 'n/a')",
                   results=[{"text": "sessions in the file: +4", "typed": False}, {"text": "the hour most sessions start: +6", "typed": False}], stdout="RESULT: sessions in the file: +4\nRESULT: the hour most sessions start: +6")]
run5.report = "## Six\n\nMost sessions start at six [cell 2]."
run5.status = "answered"
run5.data = {"df_id": "df5", "name": "sessions.csv", "source": "csv", "columns": [{"name": "v", "dtype": "int64"}], "rows": 5, "aux": [aux_old],
             "load": {"source": "intervals", "start_date": "2026-08-12", "end_date": "2026-10-10", "metrics": [], "aux_kinds": ["summary"]}}
run5.replay_script, _ = assemble(run5.cells(), run5.report)
nb5.runs[run5.id] = run5
p5 = host.propose(nb5, run5.id, empty_promoter, current_data={"df_id": "df5", "aux": [aux_old]}, runner=runner_on(df))
shape5 = p5["data"].get("aux_shape") or {}
check("propose with the data still loaded: the auxiliary files' columns and types go on record (the shape a run is made to fit)",
      aux_old in shape5 and [c["name"] for c in shape5[aux_old]["columns"]] == ["hour", "load", "note"] and shape5[aux_old]["rows"] == 4, shape5)
made5 = host.create(nb5, p5, {"name": "Start hour", "purpose": "p", "drop_inputs": [], "drop_results": []}, runner_on(df), store)
rid5 = made5["routine"]["id"]
check("run zero binds the recorded file to itself and reproduces", made5["run_zero"]["status"] == "reproduced", made5["run_zero"])
# run zero behind the dialog (2026-10-15): created at once as verifying, with a verify callable the host runs in a thread; a run
# and the precheck are held until the verdict; reproduced frees it, a verdict that did not reproduce holds it for good
p5b = host.propose(nb5, run5.id, empty_promoter, current_data={"df_id": "df5", "aux": [aux_old]}, runner=runner_on(df))
made5b = host.create(nb5, p5b, {"name": "Start hour (behind)", "purpose": "p", "drop_inputs": [], "drop_results": []}, runner_on(df), store, background=True)
rid5b = made5b["routine"]["id"]
st5b = store.load(rid5b)
pc5b = host.precheck(st5b, {"df_id": "df5", "name": "sessions.csv", "source": "csv", "columns": [{"name": "v", "dtype": "int64"}], "rows": 5, "aux": [aux_old]}, runner_on(df))
try:
    host.run(st5b, {}, {"df_id": "df5", "aux": [aux_old]}, runner_on(df), store)
    held5b = ""
except host.RoutineRefused as exc:
    held5b = str(exc)
check("create in the background: the routine is stored at once with run zero verifying (not verified, the line says so), the summary card says verifying, the result carries verify; the precheck's line and a run say it is still being verified",
      made5b["run_zero"]["status"] == "verifying" and not made5b["run_zero"]["verified"] and "verifying" in made5b["run_zero"]["line"] and callable(made5b.get("verify"))
      and st5b["versions"][0]["run_zero"]["status"] == "verifying" and made5b["routine"]["run_zero_status"] == "verifying" and not pc5b["ok"] and "still being verified" in pc5b["line"] and "still being verified" in held5b,
      (made5b["run_zero"], pc5b["line"], held5b))
vd5b = made5b["verify"]()
st5b = store.load(rid5b)
check("the verdict lands on the stored version: reproduced, verified, the two lines, the elapsed; run zero's output saved; the precheck is free again",
      vd5b["status"] == "reproduced" and st5b["versions"][0]["run_zero"]["status"] == "reproduced" and st5b["versions"][0]["run_zero"]["verified"] and len(st5b["versions"][0]["run_zero"]["results"]) == 2
      and os.path.exists(os.path.join(store.run_dir(rid5b, "v1_0"), "stdout.txt")) and host.precheck(st5b, {"df_id": "df5", "name": "sessions.csv", "source": "csv", "columns": [{"name": "v", "dtype": "int64"}], "rows": 5, "aux": [aux_old]}, runner_on(df))["ok"],
      (vd5b, st5b["versions"][0]["run_zero"]))
# a verdict that does not reproduce: the routine stays, says so, and is held for good (the refusal creation used to give, at the run)
def runner_off(script, timeout, *rest):
    return "RESULT: sessions in the file: +9.00\nRESULT: the hour most sessions start: +6.00\n", "", [], []
made5c = host.create(nb5, p5b, {"name": "Start hour (differs)", "purpose": "p", "drop_inputs": [], "drop_results": []}, runner_off, store, background=True)
vd5c = made5c["verify"]()
st5c = store.load(made5c["routine"]["id"])
try:
    host.run(st5c, {}, {"df_id": "df5", "aux": [aux_old]}, runner_on(df), store)
    held5c = ""
except host.RoutineRefused as exc:
    held5c = str(exc)
check("a verdict that did not reproduce: the version says differed with the line, the card says so, a run is refused with the old refusal's words and the way out (delete, or make it again)",
      vd5c["status"] == "differed" and st5c["versions"][0]["run_zero"]["status"] == "differed" and not st5c["versions"][0]["run_zero"]["verified"] and rt.RoutineStore.summary(st5c)["run_zero_status"] == "differed"
      and "did not reproduce the analysis" in held5c and "delete the routine, or make it again" in held5c, (vd5c["status"], vd5c["line"], held5c))
# the routine deleted while verifying: the verdict has nothing to write on and says nothing
made5d = host.create(nb5, p5b, {"name": "Start hour (gone)", "purpose": "p", "drop_inputs": [], "drop_results": []}, runner_on(df), store, background=True)
store.delete(made5d["routine"]["id"])
vd5d = made5d["verify"]()
check("deleted while verifying: the verdict is computed and dropped, nothing written", vd5d["status"] == "reproduced" and store.load(made5d["routine"]["id"]) is None)
# in the foreground (the library's default) a method that does not reproduce is still refused, as before
try:
    host.create(nb5, p5b, {"name": "x", "purpose": "p", "drop_inputs": [], "drop_results": []}, runner_off, store)
    fg5 = ""
except host.RoutineRefused as exc:
    fg5 = str(exc)
check("in the foreground a method whose run zero does not reproduce is refused and not kept, as before", "did not reproduce the analysis" in fg5, fg5)
plan5 = host.load_plan(store.load(rid5))
check("load_plan: the source, the window's length, the auxiliary kinds and the metrics as the original load asked", plan5["source"] == "intervals" and plan5["window_days"] == 59 and plan5["aux_kinds"] == ["summary"] and plan5["start"] == "2026-08-12", plan5)
# a record whose load says "cache" (from before 2026-10-12): the plan is the data's own source, the window from its date range
_rc = store.load(rid5); _rc["versions"][0]["manifest"]["data"]["load"] = {"source": "cache"}; _rc["versions"][0]["manifest"]["data"]["source"] = "intervals"
_rc["versions"][0]["manifest"]["data"]["date_range"] = "2026-08-12 to 2026-10-10"
plan5c = host.load_plan(_rc)
check("load_plan on a record whose load says cache: the source is the data's own (intervals), the window its date range, the kinds from the files", plan5c["source"] == "intervals" and plan5c["window_days"] == 59 and plan5c["aux_kinds"] == ["summary"], plan5c)
# a routine made from a chain that read the words beside the data (docs/CONTEXT_DESIGN.md F3, step 5): the run's load asks for
# the context again; the codes are not asked for - the pass behind the load makes them
_rx = store.load(rid5); _rx["versions"][0]["manifest"]["data"]["load"]["aux_kinds"] = ["summary", "wellness", "context"]
_rx["versions"][0]["manifest"]["data"]["aux"] = [aux_old, "datasets/u/k/wellness_data_20260812_to_20261010.csv", "datasets/u/k/context_notes_20260812_to_20261010.csv", "datasets/u/k/context_codes_20260812_to_20261010.csv"]
plan5x = host.load_plan(_rx)
_rx["versions"][0]["manifest"]["data"]["load"] = {"source": "cache"}; _rx["versions"][0]["manifest"]["data"]["source"] = "intervals"
plan5y = host.load_plan(_rx)
check("load_plan keeps the context kind among what a run loads, never the codes (the pass writes them) - from the load's kinds, and from the recorded files when the load says cache",
      plan5x["aux_kinds"] == ["summary", "wellness", "context"] and plan5y["aux_kinds"] == ["summary", "wellness", "context"], (plan5x["aux_kinds"], plan5y["aux_kinds"]))
# a later window: the loader wrote a differently named summary, with one column fewer and more rows
aux_new = os.path.join(aux_dir, "activity_summary_20260910_to_20261010.csv")
pd.DataFrame({"hour": [7, 7, 7, 18, 19, 7], "load": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]}).to_csv(aux_new, index=False)
now5 = {"df_id": "df5b", "name": "sessions.csv", "source": "csv", "columns": [{"name": "v", "dtype": "int64"}], "rows": 5, "aux": [aux_new]}
pc5 = host.precheck(store.load(rid5), now5, runner_on(df))
check("precheck binds the recorded summary to this load's by kind: nothing absent, the line says the data fits", pc5["ok"] and pc5["aux"]["bound"] == {"summary": "activity_summary_20260910_to_20261010.csv"} and not pc5["aux"]["absent"], pc5["aux"])
ev5 = []
run_dir5 = os.path.join(aux_dir, "routines", rid5, "v1_1")
out5b = host.run(store.load(rid5), {}, now5, runner_on(df), store, emit=ev5.append, run_dir=run_dir5)
r5 = out5b["run"]
check("a run on the later window: the method read this window's summary under the recorded name - the executed text names the run's mirror of the recorded path (2026-10-15), the stored script untouched - its lines moved; "
      "the copy at the mirror path carries the column the new file lacked; the record says which file of this load it was",
      r5["status"] == "ran" and [rt.number(x["estimate"]) for x in r5["results"]] == [6.0, 7.0] and r5["bindings"] and r5["bindings"][0][0] == aux_old and r5["bindings"][0][1] == rt.mirror_path(run_dir5, aux_old)
      and r5["shape"]["files"][aux_old]["missing"] == ["note"] and r5["shape"]["files"][aux_old]["rows"] == 6 and r5["shape"]["files"][aux_old]["source"] == aux_new and r5["sources"] == {aux_old: aux_new}
      and aux_old in store.load(rid5)["versions"][0]["script"] and os.path.exists(rt.mirror_path(run_dir5, aux_old)) and pd.read_csv(rt.mirror_path(run_dir5, aux_old)).columns.tolist() == ["hour", "load", "note"]
      and not os.path.exists(os.path.join(run_dir5, "activity_summary_20260910_to_20261010.csv")), (r5["status"], r5["results"], r5.get("bindings"), r5.get("shape")))
# what differs, said in sentences (step 4, 2026-10-11): the rows of the frame and of each bound file against the original's,
# the columns added empty; in the dialog's line (the frame's rows), on the CHECK row and on the record
check("precheck's line says the frame's rows against the original's (no probe needed)", "the same 5 rows as the original" in pc5["line"] and pc5["differences"] == ["the same 5 rows as the original"], pc5["line"])
_chk5 = next((e.get("peek") or "" for e in ev5 if e.get("type") == "lookup" and e.get("kind") == "check"), "")
check("the CHECK row and the record say what differs: the frame's rows, the summary file's rows against the original's and the column added empty",
      r5["differences"] == ["the same 5 rows as the original", "the summary file: 6 rows where the original had 4, 1 column added empty (note)"]
      and "; the same 5 rows as the original; the summary file: 6 rows where the original had 4, 1 column added empty (note)" in _chk5 and r5["check"] == _chk5, (r5.get("differences"), _chk5))
check("shape_sentences: a file empty in this data, one that could not be read, an empty column the file has, and nothing where nothing is known",
      rt.shape_sentences({"rows": 10, "aux_shape": {"/a/wellness_data_x.csv": {"rows": 30, "columns": []}}}, {"rows": 12},
                         {"files": {"/a/wellness_data_x.csv": {"path": "/b/w.csv", "rows": 0}, "/a/activity_intervals_x.csv": {"path": "/b/i.csv", "error": "bad file"}, "/a/own.csv": {"path": "/b/o.csv", "rows": 30, "missing": [], "empty": ["hrv"]}}},
                         {"map": {"/a/wellness_data_x.csv": "/b/w.csv", "/a/activity_intervals_x.csv": "/b/i.csv", "/a/own.csv": "/b/o.csv"}, "absent": []})
      == ["12 rows where the original had 10", "the wellness file is empty in this data (0 rows)", "the intervals file could not be read (bad file)", "the own.csv: 30 rows, 1 column empty (hrv)"]
      and rt.shape_sentences({}, {}, None, {"map": {}}) == [] and rt.shape_sentences({}, {"rows": 3}, None, {"map": {}}) == ["3 rows"])
# a window without words (docs/CONTEXT_DESIGN.md F3, 2026-10-14): the context file this load has is its header alone and the pass
# wrote no codes - the sentence says so, and the codes file is not said absent beside it
_bw = {"map": {"/a/context_notes_x.csv": "/b/c.csv", "/a/activity_summary_x.csv": "/b/s.csv"}, "absent": ["/a/context_codes_x.csv", "/a/wellness_data_x.csv"]}
_sw = {"files": {"/a/context_notes_x.csv": {"path": "/b/c.csv", "rows": 0}, "/a/activity_summary_x.csv": {"path": "/b/s.csv", "rows": 12}}}
_sv = {"files": {"/a/context_notes_x.csv": {"path": "/b/c.csv", "rows": 7}, "/a/activity_summary_x.csv": {"path": "/b/s.csv", "rows": 12}}}
check("a window without words: 'no passages in this window' for the empty context file; aux_line leaves the codes out of the absent files then, and names them when the context has passages (a pass that failed)",
      rt.shape_sentences({}, {}, _sw, _bw) == ["no passages in this window (the context and codes tables are empty)", "the summary file: 12 rows"]
      and rt.context_empty(_bw, _sw) and not rt.context_empty(_bw, _sv) and not rt.context_empty({"map": {}}, _sw)
      and host.aux_line(_bw, _sw) == "wellness absent in this data - the method will see an empty table there"
      and host.aux_line(_bw, _sv) == "codes, wellness absent in this data - the method will see empty tables there" and host.aux_line(_bw) == "codes, wellness absent in this data - the method will see empty tables there",
      (rt.shape_sentences({}, {}, _sw, _bw), host.aux_line(_bw, _sw), host.aux_line(_bw, _sv)))
check("cached_files: the cache's frames that came from a file, newest first, by name with their rows; a loader's frame left out; a nameless frame by its id",
      rt.cached_files({"cached_dataframes": [{"df_id": "a1", "source": "csv", "original_filename": "old.csv", "shape": [720, 6], "cached_at": "2026-10-10T10:00:00"},
                                             {"df_id": "b2", "source": "intervals", "shape": [100, 3], "cached_at": "2026-10-11T10:00:00"},
                                             {"df_id": "c3", "source": "csv", "original_filename": "new.csv", "shape": [12, 2], "cached_at": "2026-10-11T09:00:00"},
                                             {"df_id": "d4e5f6g7h8", "shape": [1, 1]}]})
      == [{"df_id": "c3", "name": "new.csv", "rows": 12, "cached_at": "2026-10-11T09:00:00"}, {"df_id": "a1", "name": "old.csv", "rows": 720, "cached_at": "2026-10-10T10:00:00"}, {"df_id": "d4e5f6g7h8", "name": "frame d4e5f6g7", "rows": 1, "cached_at": ""}]
      and rt.cached_files({}) == [], rt.cached_files({"cached_dataframes": [{"df_id": "a1", "source": "csv", "original_filename": "old.csv", "shape": [720, 6], "cached_at": "2026-10-10T10:00:00"}]}))
# a path built as folder + name, end to end (2026-10-15, Palo's first routine over the words failed here): the same recorded
# file read as base + name; on the later window the run reads this window's file at the mirror - the same answer as the full-path run
R5f = json.loads(json.dumps(store.load(rid5)))
R5f["id"] = "mirror5f"
_base = aux_dir.rstrip("/") + "/"
R5f["versions"][0]["script"] = R5f["versions"][0]["script"].replace(f"pd.read_csv({aux_old!r})", f"base = {_base!r}\nsumm = pd.read_csv(base + {os.path.basename(aux_old)!r})")
assert "base + " in R5f["versions"][0]["script"]
store.save(R5f)
run_dir5f = os.path.join(aux_dir, "routines", "mirror5f", "v1_1")
r5f = host.run(store.load("mirror5f"), {}, now5, runner_on(df), store, run_dir=run_dir5f)["run"]
check("a method that builds the path as folder + name runs on the later window: the folder literal moved under the run's folder, the bare name kept, the file read at the mirror - the same two lines as the full-path method",
      r5f["status"] in ("ran", "reproduced") and [rt.number(x["estimate"]) for x in r5f["results"]] == [6.0, 7.0] and r5f["bindings"] and r5f["bindings"][0][0] == _base and r5f["bindings"][0][2] == "cache"
      and r5f["bindings"][0][1] == rt.mirror_path(run_dir5f, _base) and r5f["sources"] == {aux_old: aux_new} and "FileNotFoundError" not in (r5f.get("error") or ""), (r5f["status"], r5f.get("bindings"), (r5f.get("error") or "")[-200:]))
# a window whose load produced no summary at all: the method sees an empty table, the CHECK row and the record say so
now5c = dict(now5, aux=[])
pc5c = host.precheck(store.load(rid5), now5c, runner_on(df))
check("precheck with the summary absent: ok (the coach decides), the line says the method will see an empty table", pc5c["ok"] and pc5c["aux"]["absent"] == ["summary"] and "summary absent in this data" in pc5c["line"], pc5c["line"])
ev5c = []
out5c = host.run(store.load(rid5), {}, now5c, runner_on(df), store, emit=ev5c.append, run_dir=os.path.join(aux_dir, "routines", rid5, "v1_2"))
r5c = out5c["run"]
check("a run with the summary absent: an empty table with the recorded columns stood in, the method failed on it (nothing to count), the run is kept and names the cell, the record lists the absent file",
      r5c["status"] == "failed" and r5c["line"].startswith("failed at cell 1") and r5c["aux_absent"] == ["summary"] and any("summary absent" in (e.get("peek") or "") for e in ev5c if e.get("kind") == "check")
      and os.path.exists(rt.mirror_path(os.path.join(aux_dir, "routines", rid5, "v1_2"), aux_old)) and r5c["sources"] == {}, (r5c["status"], r5c["line"], r5c.get("aux_absent")))
# a loader's file named with something other than the recorded dates (2026-10-10, Palo's second live run: the promoter had
# written the loaded window into the summary's name as an f-string on an input, so the recorded name was gone from the text
# and the run could not bind it): bound by kind, whatever the rest of the name says
fs = "au = pd.read_csv(f\"datasets/local/activity_summary_{str(INPUTS['window'][0]).replace('-','')}_to_{str(INPUTS['window'][1]).replace('-','')}.csv\")\nw = pd.read_csv('datasets/local/wellness_data_20260712_to_20261010.csv')\nx = pd.read_csv('datasets/local/own_notes.csv')"
_mir = "datasets/local/routines/r/v1_1"
bt, bsubs = rt.bind_script(fs, {"datasets/local/activity_summary_20260712_to_20261010.csv": rt.mirror_path(_mir, "datasets/local/activity_summary_20260712_to_20261010.csv")}, _mir, "datasets/local",
                           {"datasets/local/wellness_data_20260712_to_20261010.csv": rt.mirror_path(_mir, "datasets/local/wellness_data_20260712_to_20261010.csv")})
check("bind_script (the mirror, 2026-10-15): a summary named by an f-string on an input is bound by its kind to the mirror of the recorded summary; the wellness name to its stand-in at its recorded path under the run's folder; "
      "a file of the person's own under the datasets folder to the same place under the run's folder",
      "pd.read_csv(f\"datasets/local/routines/r/v1_1/datasets/local/activity_summary_20260712_to_20261010.csv\")" in bt and [k for _, _, k in bsubs] == ["bound", "placeholder", "cache"]
      and "'datasets/local/routines/r/v1_1/datasets/local/wellness_data_20260712_to_20261010.csv'" in bt and "'datasets/local/routines/r/v1_1/datasets/local/own_notes.csv'" in bt, (bt, bsubs))
# a path built as folder + name (2026-10-15, Palo's first routine over the words: base='datasets/local/<key>/' then base+'activity_summary_...csv'
# came out as run_folder/datasets/local/<key>/... with the name bound to a full path): the folder literal moves under the run's
# folder, the bare name stays, and the two meet at the mirror of the recorded file - on the same window and on another
fb = "base='datasets/local/'\nact=pd.read_csv(base+'activity_summary_20260712_to_20261010.csv')\nwel=pd.read_csv(base+'wellness_data_20260712_to_20261010.csv')\nalso=pd.read_csv('datasets/local/activity_summary_20260712_to_20261010.csv')"
bt2, bsubs2 = rt.bind_script(fb, {"datasets/local/activity_summary_20260712_to_20261010.csv": rt.mirror_path(_mir, "datasets/local/activity_summary_20260712_to_20261010.csv")}, _mir, "datasets/local",
                             {"datasets/local/wellness_data_20260712_to_20261010.csv": rt.mirror_path(_mir, "datasets/local/wellness_data_20260712_to_20261010.csv")})
check("bind_script: a folder literal under the datasets folder moves under the run's folder (its slash kept), a bare file name is left alone, so folder + name resolves to the mirror file; the full path resolves to the same file",
      "base='datasets/local/routines/r/v1_1/datasets/local/'" in bt2 and "base+'activity_summary_20260712_to_20261010.csv'" in bt2 and "base+'wellness_data_20260712_to_20261010.csv'" in bt2
      and "also=pd.read_csv('datasets/local/routines/r/v1_1/datasets/local/activity_summary_20260712_to_20261010.csv')" in bt2
      and [(o, k) for o, _, k in bsubs2] == [("datasets/local/", "cache"), ("datasets/local/activity_summary_20260712_to_20261010.csv", "bound")]
      and rt.mirror_path(_mir, "datasets/local/") == "datasets/local/routines/r/v1_1/datasets/local/" and rt.mirror_path(_mir, "./datasets/local/x.csv") == "datasets/local/routines/r/v1_1/datasets/local/x.csv", (bt2, bsubs2))
# the promoter's edit that writes an input into a loader's file name is refused, and the input dropped with the reason
ed_cells = "# --- cell 1 ---\nau = pd.read_csv(\"datasets/local/activity_summary_20260712_to_20261010.csv\")\nband = [9, 11]\n"
ed_text, ed_applied, ed_failed = rt.apply_edits(ed_cells, [
    {"cell": 1, "find": "pd.read_csv(\"datasets/local/activity_summary_20260712_to_20261010.csv\")", "replace": "pd.read_csv(f\"datasets/local/activity_summary_{INPUTS['window'][0]}_to_{INPUTS['window'][1]}.csv\")"},
    {"cell": 1, "find": "band = [9, 11]", "replace": "band = INPUTS['band']"}])
ed_inputs, ed_notes = rt.finish_inputs([{"key": "window", "label": "The period", "type": "date_window", "default": ["2026-07-12", "2026-10-10"]}, {"key": "band", "label": "Band", "type": "numbers", "default": [9, 11]}], ed_text, ed_failed)
check("apply_edits: an edit that writes an input into a loader's file name is refused (the name is the loader's; a run binds it), the other input's edit applies; finish_inputs drops the window with the reason",
      "activity_summary_20260712_to_20261010.csv\")" in ed_text and "band = INPUTS['band']" in ed_text and [p["key"] for p in ed_inputs] == ["band"] and any("the loader's" in n and "The period" in n for n in ed_notes), (ed_text, ed_failed, ed_notes))
ed2_text, _a, ed2_failed = rt.apply_edits(ed_cells, [
    {"cell": 1, "find": "pd.read_csv(\"datasets/local/activity_summary_20260712_to_20261010.csv\")", "replace": "pd.read_csv(\"datasets/local/activity_summary_\" + INPUTS['start'] + \"_to_\" + INPUTS['end'] + \".csv\")"},
    {"cell": 1, "find": "pd.read_csv(\"datasets/local/activity_summary_20260712_to_20261010.csv\")\nband = [9, 11]", "replace": "pd.read_csv(\"datasets/local/activity_summary_20260712_to_20261010.csv\")\nband = INPUTS['hours']"}])
check("apply_edits: the name built by concatenation is refused the same way (the loader's literal changed); an edit whose fragment merely contains the name unchanged applies",
      [sorted(f["keys"]) for f in ed2_failed] == [["end", "start"]] and "band = INPUTS['hours']" in ed2_text and "activity_summary_20260712_to_20261010.csv\")" in ed2_text, (ed2_text, ed2_failed))
check("the promoter is told: a loader's file name stays as it is, dates included, and the loaded period is never an input", "A file name under the datasets folder is the loader's" in rt.PROMOTER_SYSTEM and "never make the loaded period itself an input" in rt.PROMOTER_SYSTEM)
# the run is self-sufficient (2026-10-10, the first live run on a new window stopped on FileNotFoundError at a stand-in's
# path): the prelude makes sure every path the executed text names is there before the cells run, whether or not the probe
# ran - a stand-in not written is written, a bound file that is not where the load left it is stood in for and said
def probe_fails(script, timeout, *rest):
    if rt.SHAPE_MARK in script:
        return "", "Traceback (most recent call last):\nRuntimeError: the executor dropped the request", [], []
    return runner_on(df)(script, timeout)
ev5d = []
out5d = host.run(store.load(rid5), {}, now5c, probe_fails, store, emit=ev5d.append, run_dir=os.path.join(aux_dir, "routines", rid5, "v1_3"))
r5d = out5d["run"]
check("the probe failed and the summary is absent: the CHECK row says the files could not be prepared, the stand-in path is still what the executed text names (never a cache path), the prelude wrote it, and the method failed on the empty table - not on a missing file",
      any("could not be prepared" in (e.get("peek") or "") for e in ev5d if e.get("kind") == "check") and r5d["bindings"] and r5d["bindings"][0][2] == "placeholder" and r5d["bindings"][0][1] == rt.mirror_path(os.path.join(aux_dir, "routines", rid5, "v1_3"), aux_old)
      and os.path.exists(rt.mirror_path(os.path.join(aux_dir, "routines", rid5, "v1_3"), aux_old)) and "FileNotFoundError" not in (r5d.get("error") or "") and r5d["status"] == "failed",
      (r5d.get("bindings"), r5d.get("status"), (r5d.get("error") or "")[-160:]))
# a bound file that is not there when the cells run (the loader's file gone between the probe and the run): stood in for and said
now5e = dict(now5, aux=[os.path.join(aux_dir, "activity_summary_20260501_to_20260630.csv")])
def probe_then_gone(script, timeout, *rest):
    if rt.SHAPE_MARK in script:
        pd.DataFrame({"hour": [6], "load": [1.0], "note": ["a"]}).to_csv(now5e["aux"][0], index=False)
        out = runner_on(df)(script, timeout)
        os.remove(now5e["aux"][0])
        return out
    return runner_on(df)(script, timeout)
out5e = host.run(store.load(rid5), {}, now5e, probe_then_gone, store, run_dir=os.path.join(aux_dir, "routines", rid5, "v1_4"))
r5e = out5e["run"]
_mir5e = rt.mirror_path(os.path.join(aux_dir, "routines", rid5, "v1_4"), aux_old)
check("a bound file gone after the probe (2026-10-15): the probe's copy in the run's mirror carries the run - the method read its one row, the loader's path stays gone, no stand-in and no FileNotFoundError",
      r5e["bindings"][0][2] == "bound" and r5e["bindings"][0][1] == _mir5e and not os.path.exists(now5e["aux"][0]) and os.path.exists(_mir5e) and pd.read_csv(_mir5e).columns.tolist() == ["hour", "load", "note"]
      and r5e["status"] == "ran" and [rt.number(x["estimate"]) for x in r5e["results"]] == [1.0, 6.0] and "FileNotFoundError" not in (r5e.get("error") or ""), (r5e.get("bindings"), r5e.get("status"), r5e.get("results"), (r5e.get("error") or "")[-160:]))
# ---- an input that only restates the period the data covers follows the data (2026-10-11: the first run that completed on a
# new window carried the original window in its labels and titles, typed, and the promoter had made it an input to retype) ----
df_d = pd.DataFrame({"datetime": pd.to_datetime(["2026-07-13 06:00", "2026-08-01 07:00", "2026-09-10 06:30", "2026-10-07 18:00"]), "v": [1, 2, 3, 4]})
nb8 = Notebook("t8")
run8 = nb8.new_run("How many sessions in the window?")
run8.turns = [Turn(kind="cell", cell_no=1, code="n = int(len(df))\nprint(n)", results=[], stdout="4"),
              Turn(kind="cell", cell_no=2, code="RESULT('sessions, 2026-07-13 to 2026-10-07', float(n), None, None, 'sessions', 'n/a')\nRESULT('rows loaded 2026-07-12 to 2026-10-10', float(n), None, None, 'rows', 'n/a')",
                   results=[{"text": "sessions, 2026-07-13 to 2026-10-07: +4", "typed": False}, {"text": "rows loaded 2026-07-12 to 2026-10-10: +4", "typed": False}],
                   stdout="RESULT: sessions, 2026-07-13 to 2026-10-07: +4\nRESULT: rows loaded 2026-07-12 to 2026-10-10: +4")]
run8.report = "## Four\n\nFour sessions [cell 2]."
run8.status = "answered"
run8.data = {"df_id": "df8", "name": "", "source": "intervals", "columns": [{"name": "datetime", "dtype": "datetime64[ns]"}, {"name": "v", "dtype": "int64"}], "rows": 4, "aux": [],
             "date_range": "2026-07-12 to 2026-10-10", "load": {"source": "intervals", "start_date": "2026-07-12", "end_date": "2026-10-10", "metrics": [], "aux_kinds": []}}
run8.replay_script, _ = assemble(run8.cells(), run8.report)
nb8.runs[run8.id] = run8
def dates_promoter(system, user):
    return json.dumps({"name": "Sessions in the window", "inputs": [
        {"key": "span", "label": "The dates in the label", "type": "date_window", "default": ["2026-07-13", "2026-10-07"], "origin": "the first and last session dates, typed into the label"},
        {"key": "window", "label": "The window loaded", "type": "date_window", "default": ["2026-07-12", "2026-10-10"], "origin": "the load window, typed into a label"},
        {"key": "cut", "label": "A cut inside the data", "type": "date_window", "default": ["2026-08-01", "2026-09-01"], "origin": "a boundary inside the data"}],
        "edits": [{"cell": 2, "find": "'sessions, 2026-07-13 to 2026-10-07'", "replace": "f\"sessions, {INPUTS['span'][0]} to {INPUTS['span'][1]}\""},
                  {"cell": 2, "find": "'rows loaded 2026-07-12 to 2026-10-10'", "replace": "f\"rows loaded {INPUTS['window'][0]} to {INPUTS['window'][1]} ({INPUTS['cut'][0]})\""}]}), {"cost": 0.0}
p8 = host.propose(nb8, run8.id, dates_promoter, current_data={"df_id": "df8"}, runner=runner_on(df_d))
check("propose: the probe recorded the period the frame covers (its date column, first and last dates); the window that is the frame's dates follows the data, the one that is the load window follows the load, a cut inside the data is asked",
      p8["data"].get("span") == {"column": "datetime", "first": "2026-07-13", "last": "2026-10-07"} and [(q["key"], q.get("derived")) for q in p8["inputs"]] == [("span", "span"), ("window", "window"), ("cut", None)], (p8["data"].get("span"), p8["inputs"]))
made8 = host.create(nb8, p8, {"name": "Sessions in the window", "purpose": "", "drop_inputs": [], "drop_results": []}, runner_on(df_d), store)
rid8 = made8["routine"]["id"]
check("create: run zero reproduces (the defaults are the data's own dates); the manifest keeps the marks", made8["run_zero"]["status"] == "reproduced" and [q.get("derived") for q in store.load(rid8)["versions"][0]["manifest"]["parameters"]] == ["span", "window", None], made8["run_zero"])
df_d2 = pd.DataFrame({"datetime": pd.to_datetime(["2026-01-13 06:00", "2026-03-01 07:00", "2026-07-09 06:30"]), "v": [1, 2, 3]})
now8 = {"df_id": "df8b", "name": "", "source": "intervals", "columns": [{"name": "datetime", "dtype": "datetime64[ns]"}, {"name": "v", "dtype": "int64"}], "rows": 3, "aux": [],
        "date_range": "2026-01-12 to 2026-07-10", "load": {"source": "intervals", "start_date": "2026-01-12", "end_date": "2026-07-10", "metrics": [], "aux_kinds": []}}
out8 = host.run(store.load(rid8), {"span": ["2000-01-01", "2000-01-02"], "window": ["2000-01-01", "2000-01-02"], "cut": ["2026-02-01", "2026-03-01"]}, now8, runner_on(df_d2), store)
r8 = out8["run"]
check("run on a later window: the span was written from the frame (first and last dates), the window from this load, the cut as typed; the labels printed carry them; the record keeps the values; the output keeps no marker line",
      r8["inputs"] == {"span": ["2026-01-13", "2026-07-09"], "window": ["2026-01-12", "2026-07-10"], "cut": ["2026-02-01", "2026-03-01"]}
      and r8["results"][0]["what"] == "sessions, 2026-01-13 to 2026-07-09" and r8["results"][1]["what"] == "rows loaded 2026-01-12 to 2026-07-10 (2026-02-01)"
      and rt.INPUTS_MARK_OUT not in out8["stdout"] and rt.INPUTS_MARK_OUT not in open(os.path.join(store.run_dir(rid8, "v1_1"), "stdout.txt"), encoding="utf-8").read(),
      (r8["inputs"], [x.get("what") for x in r8["results"]], out8["stdout"][:200]))
check("derive_inputs on a record without a span (a routine made before): nothing follows the frame; the load window still can", [q.get("derived") for q in host.derive_inputs(p8["inputs"], dict(run8.data, span=None))] == [None, "window", None])
# ---- the cache asked before a load (2026-10-11): the executor's cache listing against the routine's plan ----
insp = {"cached_dataframes": [{"df_id": "a", "shape": [1000, 17], "source": "intervals", "date_range": "2026-07-12 to 2026-10-10", "metrics": []},
                              {"df_id": "b", "shape": [900, 18], "source": "intervals", "date_range": "2026-07-12 to 2026-10-10", "metrics": ["power"]},
                              {"df_id": "e", "shape": [50, 9], "source": "endura", "race_id": 2}, {"df_id": "s", "source": "sweatstack", "date_range": "2026-07-12 to 2026-10-10"}],
        "auxiliary_datasets": [{"filename": "activity_summary_20260712_to_20261010.csv", "path": "datasets/u/activity_summary_20260712_to_20261010.csv"},
                               {"filename": "race_turns_race_2.csv", "path": "datasets/u/race_turns_race_2.csv"}]}
cm1 = rt.cache_match({"source": "intervals", "aux_kinds": ["summary"], "metrics": []}, insp, "2026-07-12", "2026-10-10")
cm2 = rt.cache_match({"source": "intervals", "aux_kinds": ["summary", "wellness"], "metrics": []}, insp, "2026-07-12", "2026-10-10")
cm3 = rt.cache_match({"source": "intervals", "aux_kinds": [], "metrics": ["power"]}, insp, "2026-07-12", "2026-10-10")
cm4 = rt.cache_match({"source": "intervals", "aux_kinds": [], "metrics": []}, insp, "2026-07-01", "2026-10-10")
cm4b = rt.cache_match({"source": "intervals", "aux_kinds": ["summary"], "metrics": []}, insp, "2026-07-20", "2026-09-30")
cm4c = rt.cache_match({"source": "intervals", "aux_kinds": ["summary", "wellness"], "metrics": []}, insp, "2026-07-20", "2026-09-30")
cm5 = rt.cache_match({"source": "endura", "aux_kinds": ["turns"]}, insp, race_id="2")
cm6 = rt.cache_match({"source": "endura", "aux_kinds": ["turns", "climbs"]}, insp, race_id=2)
cm7 = rt.cache_match({"source": "sweatstack", "aux_kinds": []}, insp, "2026-07-12", "2026-10-10")
check("cache_match: the same source, window and metrics with every wanted file is a hit (the frame's id, the files' paths, the rows, a line saying no download); a wanted file missing, other metrics' frame used instead, another window, no hit - each with its reason",
      cm1["hit"] and cm1["df_id"] == "a" and cm1["files"] == ["datasets/u/activity_summary_20260712_to_20261010.csv"] and cm1["rows"] == 1000 and "no download" in cm1["line"] and "with summary" in cm1["line"]
      and not cm2["hit"] and "without wellness" in cm2["line"] and cm3["hit"] and cm3["df_id"] == "b" and not cm4["hit"] and "not in the cache" in cm4["line"], (cm1, cm2, cm3, cm4))
check("cache_match: a window inside a cached load is a hit to be cut (the cached load's window on it, the line says so); without one of the wanted files beside the cached load, no hit, saying so",
      cm4b["hit"] and cm4b["df_id"] == "a" and cm4b["cut"] == ["2026-07-12", "2026-10-10"] and "inside the cached load 2026-07-12 → 2026-10-10" in cm4b["line"] and "cut to the window, no download" in cm4b["line"]
      and not cm4c["hit"] and "around this window" in cm4c["line"] and "without wellness" in cm4c["line"], (cm4b, cm4c))
# a load with context wants the codes the pass wrote beside it (2026-10-14) - unless the cached context file is a header alone
insp_c = {"cached_dataframes": [{"df_id": "a", "shape": [1000, 17], "source": "intervals", "date_range": "2026-07-12 to 2026-10-10", "metrics": []},
                                {"df_id": "q", "shape": [200, 17], "source": "intervals", "date_range": "2026-09-01 to 2026-09-10", "metrics": []}],
          "auxiliary_datasets": [{"filename": "activity_summary_20260712_to_20261010.csv", "path": "datasets/u/activity_summary_20260712_to_20261010.csv", "size_mb": 0.01},
                                 {"filename": "context_notes_20260712_to_20261010.csv", "path": "datasets/u/context_notes_20260712_to_20261010.csv", "size_mb": 0.05},
                                 {"filename": "activity_summary_20260901_to_20260910.csv", "path": "datasets/u/activity_summary_20260901_to_20260910.csv", "size_mb": 0.002},
                                 {"filename": "context_notes_20260901_to_20260910.csv", "path": "datasets/u/context_notes_20260901_to_20260910.csv", "size_mb": 0.00012}]}
cmc1 = rt.cache_match({"source": "intervals", "aux_kinds": ["summary", "context"], "metrics": []}, insp_c, "2026-07-12", "2026-10-10")
insp_c["auxiliary_datasets"].append({"filename": "context_codes_20260712_to_20261010.csv", "path": "datasets/u/context_codes_20260712_to_20261010.csv", "size_mb": 0.02})
cmc2 = rt.cache_match({"source": "intervals", "aux_kinds": ["summary", "context"], "metrics": []}, insp_c, "2026-07-12", "2026-10-10")
cmc3 = rt.cache_match({"source": "intervals", "aux_kinds": ["summary", "context"], "metrics": []}, insp_c, "2026-09-01", "2026-09-10")
check("cache_match with context: no hit without the codes file beside the cached context file (the line names the codes); a hit with both, the files in the plan's order plus the codes; "
      "a cached context file of its header alone (a window without words) is a hit without codes",
      not cmc1["hit"] and "without codes" in cmc1["line"] and cmc2["hit"] and cmc2["files"] == ["datasets/u/activity_summary_20260712_to_20261010.csv", "datasets/u/context_notes_20260712_to_20261010.csv", "datasets/u/context_codes_20260712_to_20261010.csv"]
      and cmc3["hit"] and cmc3["df_id"] == "q" and cmc3["files"] == ["datasets/u/activity_summary_20260901_to_20260910.csv", "datasets/u/context_notes_20260901_to_20260910.csv"], (cmc1, cmc2, cmc3))
# the planned workouts file (2026-10-15): a kind of its own, named by the window, cut by its date column, wanted beside the context
cmp1 = rt.cache_match({"source": "intervals", "aux_kinds": ["summary", "context", "plan"], "metrics": []}, insp_c, "2026-07-12", "2026-10-10")
insp_c["auxiliary_datasets"].append({"filename": "planned_workouts_20260712_to_20261010.csv", "path": "datasets/u/planned_workouts_20260712_to_20261010.csv", "size_mb": 0.03})
cmp2 = rt.cache_match({"source": "intervals", "aux_kinds": ["summary", "context", "plan"], "metrics": []}, insp_c, "2026-07-12", "2026-10-10")
check("the planned workouts file: its kind, prefix and cut rule; a routine that wants it is no hit without it beside the cached load and a hit with it, the file among those taken",
      rt.aux_kind("datasets/u/k/planned_workouts_20260712_to_20261010.csv") == "plan" and rt.kind_prefix("plan") == "planned_workouts_" and rt.cut_rule("planned_workouts_x.csv") == ("date", "date")
      and not cmp1["hit"] and "without plan" in cmp1["line"] and cmp2["hit"] and "datasets/u/planned_workouts_20260712_to_20261010.csv" in cmp2["files"], (cmp1, cmp2))
check("load_plan keeps the plan among a run's kinds", "plan" in host.load_plan({"versions": [{"number": 1, "manifest": {"data": {"source": "intervals", "load": {"source": "intervals", "aux_kinds": ["summary", "context", "plan", "other"], "start_date": "2026-07-12", "end_date": "2026-10-10"}}}}], "current_version": 1})["aux_kinds"]
      and "other" not in host.load_plan({"versions": [{"number": 1, "manifest": {"data": {"source": "intervals", "load": {"source": "intervals", "aux_kinds": ["summary", "context", "plan", "other"], "start_date": "2026-07-12", "end_date": "2026-10-10"}}}}], "current_version": 1})["aux_kinds"])
check("cache_match: an Endura event by its id with its files; a file missing is no hit; SweatStack never matches (its entries do not say which subjects they hold); no window or event asked - nothing to say",
      cm5["hit"] and cm5["df_id"] == "e" and cm5["files"] == ["datasets/u/race_turns_race_2.csv"] and not cm6["hit"] and "without climbs" in cm6["line"] and cm7 == {"hit": False, "line": ""}
      and rt.cache_match({"source": "intervals", "aux_kinds": []}, insp) == {"hit": False, "line": ""} and rt.cache_match({"source": "intervals"}, None, "2026-07-12", "2026-10-10")["hit"] is False, (cm5, cm6, cm7))
# whose data the cache holds (2026-10-11, Palo: a coach who changes the key to look at another subject must not be served the
# first one's windows): the loader marks each frame with the key that loaded it (the same one-way formula as key_fingerprint) and
# keeps that key's files in a folder of that name; a cached window counts only under the same key, in that folder
k1, k2 = rt.key_fingerprint("key-one"), rt.key_fingerprint("key-two")
insp_k = {"cached_dataframes": [{"df_id": "a", "shape": [1000, 17], "source": "intervals", "date_range": "2026-01-13 to 2026-06-11", "metrics": [], "key_mark": k1},
                                {"df_id": "b", "shape": [900, 17], "source": "intervals", "date_range": "2026-01-13 to 2026-06-11", "metrics": [], "key_mark": k2},
                                {"df_id": "old", "shape": [500, 17], "source": "intervals", "date_range": "2026-08-01 to 2026-08-31", "metrics": []}],
          "auxiliary_datasets": [{"path": f"datasets/u/{k1}/activity_summary_20260113_to_20260611.csv", "key_mark": k1}, {"path": f"datasets/u/{k2}/activity_summary_20260113_to_20260611.csv", "key_mark": k2},
                                 {"path": "datasets/u/activity_summary_20260801_to_20260831.csv", "key_mark": ""}]}
plan_k = {"source": "intervals", "aux_kinds": ["summary"], "metrics": []}
ck1 = rt.cache_match(plan_k, insp_k, "2026-01-13", "2026-06-11", key=k1)
ck2 = rt.cache_match(plan_k, insp_k, "2026-01-13", "2026-06-11", key=k2)
ck3 = rt.cache_match(plan_k, insp_k, "2026-01-13", "2026-06-11", key=rt.key_fingerprint("key-three"))
ck4 = rt.cache_match(plan_k, insp_k, "2026-08-01", "2026-08-31", key=k1)
ck5 = rt.cache_match(plan_k, insp_k, "2026-03-01", "2026-03-31", key=k1)
check("cache_match by key: the same window loaded under two keys - each key gets its own frame and the file in its own folder; a third key gets neither, said; a frame from before the loader marked them is not used, said; a window inside this key's load is cut from it",
      ck1["hit"] and ck1["df_id"] == "a" and ck1["files"] == [f"datasets/u/{k1}/activity_summary_20260113_to_20260611.csv"] and ck2["hit"] and ck2["df_id"] == "b" and ck2["files"][0].startswith(f"datasets/u/{k2}/")
      and not ck3["hit"] and "loaded under another key" in ck3["line"] and not ck4["hit"] and "before loads were marked" in ck4["line"] and ck5["hit"] and ck5["df_id"] == "a" and ck5.get("cut") == ["2026-01-13", "2026-06-11"],
      (ck1, ck2, ck3["line"], ck4["line"], ck5))
check("the key's mark is one-way and twelve characters, empty for no key, and the formula is the loader's (sha256 of the key, the first twelve hex characters)",
      len(k1) == 12 and k1 != k2 and rt.key_fingerprint("") == "" and "key-one" not in k1 and k1 == __import__("hashlib").sha256(b"key-one").hexdigest()[:12])
check("without a key the match is as before (the newest exact window); Endura's files are the event's, at the user's folder", rt.cache_match(plan_k, insp_k, "2026-01-13", "2026-06-11")["df_id"] == "b"
      and rt.cache_match({"source": "endura", "aux_kinds": ["turns"]}, {"cached_dataframes": [{"df_id": "e", "source": "endura", "race_id": 2}], "auxiliary_datasets": [{"path": "datasets/u/race_turns_race_2.csv", "key_mark": ""}]}, race_id=2)["hit"])
# ---- a run on a cached load around the window asked (2026-10-11, Palo: Feb-May inside a cached Jan-June was downloaded again,
# and used whole it would have shown the cached window's numbers): the frame and the files are cut to the window first ----
cut_dir = os.path.join(aux_dir, "cut")
os.makedirs(cut_dir, exist_ok=True)
cut_summary = os.path.join(cut_dir, "activity_summary_20260101_to_20260630.csv")
pd.DataFrame({"activity_id": ["a1", "a2", "a3", "a4"], "start_date_local": ["2026-01-20 07:00", "2026-02-10 08:00", "2026-04-01 09:00", "2026-06-20 07:00"], "hour": [7, 8, 9, 7]}).to_csv(cut_summary, index=False)
cut_wellness = os.path.join(cut_dir, "wellness_data_20260101_to_20260630.csv")
pd.DataFrame({"date": ["2026-01-20", "2026-03-01", "2026-06-20"], "ctl": [1.0, 2.0, 3.0]}).to_csv(cut_wellness, index=False)
cut_intervals = os.path.join(cut_dir, "activity_intervals_20260101_to_20260630.csv")
pd.DataFrame({"activity_id": ["a1", "a2", "a2", "a4"], "lap_number": [1, 1, 2, 1]}).to_csv(cut_intervals, index=False)
cut_own = os.path.join(cut_dir, "own_notes.csv")
pd.DataFrame({"k": [1, 2]}).to_csv(cut_own, index=False)
nb9 = Notebook("t9")
run9 = nb9.new_run("How many sessions, and what is in the files?")
orig_s, orig_w, orig_i = [os.path.join(aux_dir, n) for n in ("activity_summary_20260713_to_20261011.csv", "wellness_data_20260713_to_20261011.csv", "activity_intervals_20260713_to_20261011.csv")]
pd.DataFrame({"activity_id": ["z1"], "start_date_local": ["2026-08-01 07:00"], "hour": [7]}).to_csv(orig_s, index=False)
pd.DataFrame({"date": ["2026-08-01"], "ctl": [1.0]}).to_csv(orig_w, index=False)
pd.DataFrame({"activity_id": ["z1"], "lap_number": [1]}).to_csv(orig_i, index=False)
run9.turns = [Turn(kind="cell", cell_no=1, code=f"s = pd.read_csv({orig_s!r}); w = pd.read_csv({orig_w!r}); iv = pd.read_csv({orig_i!r})\nn = int(df['activity_id'].nunique())\nprint(n, len(s), len(w), len(iv))", results=[], stdout="1 1 1 1"),
              Turn(kind="cell", cell_no=2, code="RESULT('sessions in the frame', float(n), None, None, 'sessions', 'n/a')\nRESULT('rows in the summary', float(len(s)), None, None, 'rows', 'n/a')\nRESULT('rows in the wellness file', float(len(w)), None, None, 'rows', 'n/a')\nRESULT('rows in the intervals file', float(len(iv)), None, None, 'rows', 'n/a')",
                   results=[{"text": "sessions in the frame: +1", "typed": False}, {"text": "rows in the summary: +1", "typed": False}, {"text": "rows in the wellness file: +1", "typed": False}, {"text": "rows in the intervals file: +1", "typed": False}],
                   stdout="RESULT: sessions in the frame: +1\nRESULT: rows in the summary: +1\nRESULT: rows in the wellness file: +1\nRESULT: rows in the intervals file: +1")]
run9.report = "## One\n\nOne session [cell 2]."
run9.status = "answered"
df9 = pd.DataFrame({"activity_id": ["z1"] * 3, "datetime": pd.to_datetime(["2026-08-01 07:00", "2026-08-01 07:01", "2026-08-01 07:02"]), "v": [1, 2, 3]})
run9.data = {"df_id": "df9", "name": "", "source": "intervals", "columns": [{"name": "activity_id", "dtype": "object"}, {"name": "datetime", "dtype": "datetime64[ns]"}, {"name": "v", "dtype": "int64"}], "rows": 3,
             "date_range": "2026-07-13 to 2026-10-11", "aux": [orig_s, orig_w, orig_i], "load": {"source": "intervals", "start_date": "2026-07-13", "end_date": "2026-10-11", "metrics": [], "aux_kinds": ["summary", "wellness", "intervals"]}}
run9.replay_script, _ = assemble(run9.cells(), run9.report)
nb9.runs[run9.id] = run9
p9 = host.propose(nb9, run9.id, empty_promoter, current_data={"df_id": "df9", "aux": [orig_s, orig_w, orig_i]}, runner=runner_on(df9))
p9["inputs"] = [{"key": "span", "label": "Span", "type": "date_window", "default": ["2026-08-01", "2026-08-01"], "derived": "span"}]   # follows the frame: the cut frame's dates
p9["cells_text"] = p9["cells_text"].replace("RESULT('sessions in the frame', float(n)", "RESULT(f\"sessions in the frame {INPUTS['span'][0]} to {INPUTS['span'][1]}\", float(n)")
p9["script"] = rt.join_script(p9["header"], p9["cells_text"], p9["tail"])
made9 = host.create(nb9, p9, {"name": "Cut", "purpose": "", "drop_inputs": [], "drop_results": []}, runner_on(df9), store)
rid9 = made9["routine"]["id"]
check("the routine on three loader files and a frame made (run zero reproduced)", made9["run_zero"]["status"] == "reproduced", made9["run_zero"])
# the cached load: Jan-June, five sessions in the frame (one per month), the run asks Feb-May
df9c = pd.DataFrame({"activity_id": ["a1", "a2", "a3", "a4", "a1"], "datetime": pd.to_datetime(["2026-01-20 07:00", "2026-02-10 08:00", "2026-04-01 09:00", "2026-06-20 07:00", "2026-01-20 07:01"]), "v": [1, 2, 3, 4, 5]})
now9 = {"df_id": "df9c", "name": "", "source": "intervals", "columns": run9.data["columns"], "rows": 5, "date_range": "2026-01-01 to 2026-06-30", "aux": [cut_summary, cut_wellness, cut_intervals, cut_own],
        "load": {"source": "intervals", "start_date": "2026-02-01", "end_date": "2026-05-31", "metrics": [], "aux_kinds": ["summary", "wellness", "intervals"], "cached": True, "cached_from": ["2026-01-01", "2026-06-30"]}}
cw = host.cut_window(host.version_of(store.load(rid9)), now9)
check("cut_window: the window asked and the frame's date column, from the load the page says came from a cached load around it; nothing without one", cw == {"start": "2026-02-01", "end": "2026-05-31", "column": "datetime"} and host.cut_window(host.version_of(store.load(rid9)), dict(now9, load=dict(now9["load"], cached_from=None))) is None, cw)
ev9 = []
run9_dir = os.path.join(aux_dir, "routines", rid9, "v1_1")
out9 = host.run(store.load(rid9), {}, now9, runner_on(df9c), store, emit=ev9.append, run_dir=run9_dir)
r9 = out9["run"]
got9 = {x["what"]: x["estimate"] for x in r9["results"]}
check("the run on a cached load around the window: the frame cut to Feb-May (2 of 4 sessions), the summary by its start dates (2 of 4 rows), the wellness file by its date (1 of 3), the intervals file by the sessions kept (3 of 4 rows: a2's two laps and a3's... no, a2's two); the window input written from the cut frame; the CHECK row says the cut",
      r9["status"] in ("ran", "differed") and got9.get("rows in the summary") == "+2.00" and got9.get("rows in the wellness file") == "+1.00" and got9.get("rows in the intervals file") == "+2.00"
      and any(k.startswith("sessions in the frame 2026-02-10 to 2026-04-01") for k in got9) and got9[next(k for k in got9 if k.startswith("sessions in the frame"))] == "+2.00"
      and r9["inputs"] == {"span": ["2026-02-10", "2026-04-01"]} and any(e.get("kind") == "check" and "cut to 2026-02-01 → 2026-05-31 from the cached load 2026-01-01 → 2026-06-30" in (e.get("peek") or "") for e in ev9), (r9["status"], got9, r9["inputs"], [e.get("peek") for e in ev9 if e.get("kind") == "check"], (r9.get("error") or "")[-300:]))
check("the executed text names the cut copies at the mirror of the recorded paths under the run's folder (2026-10-15); the record's bindings say cut and the sources name the cached load's files; the data record says the window and the rows the method saw; the files are there, cut",
      all(k == "cut" for _, _, k in r9["bindings"]) and sorted(n for _, n, _ in r9["bindings"]) == sorted(rt.mirror_path(run9_dir, o) for o in r9["sources"]) and len(r9["sources"]) == 3
      and all(os.path.exists(n) for _, n, _ in r9["bindings"]) and r9["data"]["date_range"] == "2026-02-01 to 2026-05-31" and r9["data"]["rows"] == 2
      and rt.DATA_MARK_OUT not in out9["stdout"] and pd.read_csv(next(n for o, n, _ in r9["bindings"] if rt.aux_kind(o) == "summary"))["activity_id"].tolist() == ["a2", "a3"]
      and not glob.glob(os.path.join(run9_dir, "*.csv")), (r9["bindings"], r9.get("sources"), r9["data"].get("date_range"), r9["data"].get("rows")))
check("the CHECK row of the cut run: the summary's 2 rows and the intervals file's 2 against the original's 1, the wellness file's 1 as the original, the frame's 2 against the original's 3 - what the method sees, said before it runs",
      "2 rows where the original had 3" in r9["check"] and "the summary file: 2 rows where the original had 1" in r9["check"] and "the intervals file: 2 rows where the original had 1" in r9["check"] and "the wellness file: 1 row as the original" in r9["check"]
      and any(e.get("kind") == "check" and "the summary file: 2 rows where the original had 1" in (e.get("peek") or "") for e in ev9), r9["check"])
pc9 = host.precheck(store.load(rid9), now9, runner_on(df9c))
R9 = store.load(rid9); v9 = host.version_of(R9)
v9["manifest"]["parameters"].append({"key": "which", "label": "Which", "type": "choice", "default": ["a1", "a2"], "column": "activity_id", "multiple": True, "origin": "x"})
store.save(R9)
pc9b = host.precheck(store.load(rid9), now9, runner_on(df9c))
check("the precheck of a cut run checks the values in the window: a1 (January) is not in the cut frame - a note, a2 is", pc9["ok"] and pc9b["ok"] and pc9b["values_notes"] == ["'a1' is not in column activity_id - the method keeps the other value"], (pc9["line"], pc9b.get("values_notes"), pc9b["line"]))
v9["manifest"]["parameters"].pop(); store.save(R9)
# ---- the words of a cut run are the window's (2026-10-16, Palo's routine on a four-month window inside a cached seventeen-month
# load: CTX read the whole load's context - the host's prelude points it at the files loaded now - against a summary cut to the
# window, and the method fell over on months with words but no rides): CTX is defined over the run's own context and codes
# files, cut to the window, the codes to the passages the cut context keeps ----
from analyst.context import kernel_api_source as _ctx_src
def runner_ctx(frame, notes, codes):
    """A runner as the host's: CTX over the files loaded now rides ahead of the script (the run's prelude must override it)."""
    def _r(script, timeout, *rest):
        k = PersistentKernel(df=frame)
        try:
            out, err, _ = k.execute(_ctx_src(notes, codes) + "\n\n" + script)
        finally:
            k.cleanup()
        return out or "", err or "", [], []
    return _r
ctx_cols = ["id", "kind", "date", "time", "end_date", "activity_id", "event_id", "source_id", "author_id", "author_name", "author_role", "private", "lang", "text", "text_en", "chars"]
def ctx_rows(days):
    # the first passage's text has a second line (2026-10-16): a row count that counted lines said 3 rows for 2 passages
    return pd.DataFrame([dict(zip(ctx_cols, [f"C.{i + 1}", "activity_message", d, "07:30", "", "", "", "", "", "", "subject", "", "en", f"words {i + 1}" + ("\nand a second line" if i == 0 else ""), "", "7"])) for i, d in enumerate(days)])
orig_c, orig_k = [os.path.join(aux_dir, n) for n in ("context_notes_20260713_to_20261011.csv", "context_codes_20260713_to_20261011.csv")]
ctx_rows(["2026-08-01", "2026-08-02"]).to_csv(orig_c, index=False)
pd.DataFrame({"id": ["C.1", "C.1", "C.2"], "code": ["fatigue", "effort", "fatigue"], "tone": ["negative"] * 3, "quote": ["words 1", "words 1", "words 2"], "status": ["ok"] * 3, "coder": ["m"] * 3, "codebook_version": [1] * 3}).to_csv(orig_k, index=False)
nb10 = Notebook("t10")
run10 = nb10.new_run("How many passages, and how many codes on them?")
run10.turns = [Turn(kind="cell", cell_no=1, code="fr = CTX.frame(); cd = CTX.codes()\nprint(len(fr), len(cd))", results=[], stdout="2 3"),
               Turn(kind="cell", cell_no=2, code="RESULT('passages', float(len(fr)), None, None, 'passages', 'n/a')\nRESULT('codes on them', float(len(cd)), None, None, 'codes', 'n/a')",
                    results=[{"text": "passages: +2", "typed": False}, {"text": "codes on them: +3", "typed": False}], stdout="RESULT: passages: +2\nRESULT: codes on them: +3")]
run10.report = "## Two\n\nTwo passages, three codes [cell 2]."
run10.status = "answered"
run10.data = {"df_id": "df9", "name": "", "source": "intervals", "columns": run9.data["columns"], "rows": 3, "date_range": "2026-07-13 to 2026-10-11", "aux": [orig_s, orig_c, orig_k],
              "load": {"source": "intervals", "start_date": "2026-07-13", "end_date": "2026-10-11", "metrics": [], "aux_kinds": ["summary", "context"]}}
run10.replay_script, _ = assemble(run10.cells(), run10.report)
nb10.runs[run10.id] = run10
p10 = host.propose(nb10, run10.id, empty_promoter, current_data={"df_id": "df9", "aux": [orig_s, orig_c, orig_k]}, runner=runner_ctx(df9, orig_c, orig_k))
made10 = host.create(nb10, p10, {"name": "Words", "purpose": "", "drop_inputs": [], "drop_results": []}, runner_ctx(df9, orig_c, orig_k), store)
rid10 = made10["routine"]["id"]
rec10 = host.version_of(store.load(rid10))["manifest"]["data"]
check("a routine over CTX made: run zero reproduced on the load's own context (the host's prelude defines CTX there); the record's shape counts the context file's rows, not its lines (a passage of two lines is one row)",
      made10["run_zero"]["status"] == "reproduced" and rec10["aux_shape"][orig_c]["rows"] == 2 and rec10["aux_shape"][orig_k]["rows"] == 3 and len(open(orig_c, encoding="utf-8").read().strip().splitlines()) == 4, (made10["run_zero"], {k_: v_.get("rows") for k_, v_ in rec10.get("aux_shape", {}).items()}))
cut_ctx, cut_codes = [os.path.join(cut_dir, n) for n in ("context_notes_20260101_to_20260630.csv", "context_codes_20260101_to_20260630.csv")]
ctx_rows(["2026-01-20", "2026-02-10", "2026-03-01", "2026-04-01", "2026-06-20"]).to_csv(cut_ctx, index=False)
pd.DataFrame({"id": ["C.1", "C.2", "C.2", "C.3", "C.4", "C.5", "C.5"], "code": ["fatigue"] * 7, "tone": ["negative"] * 7, "quote": ["q"] * 7, "status": ["ok"] * 7, "coder": ["m"] * 7, "codebook_version": [1] * 7}).to_csv(cut_codes, index=False)
now10 = dict(now9, aux=[cut_summary, cut_ctx, cut_codes], load=dict(now9["load"], aux_kinds=["summary", "context"]))
run10_dir = os.path.join(aux_dir, "routines", rid10, "v1_1")
out10 = host.run(store.load(rid10), {}, now10, runner_ctx(df9c, cut_ctx, cut_codes), store, run_dir=run10_dir)
r10 = out10["run"]
got10 = {x["what"]: x["estimate"] for x in r10["results"]}
ctx_mirror = rt.mirror_path(run10_dir, orig_c); codes_mirror = rt.mirror_path(run10_dir, orig_k)
check("the cut run's words are the window's: the method's CTX reads the mirror copies cut to Feb-May - 3 of the cached load's 5 passages and the 4 codes on them (not the 7 of the whole load the host's CTX would give); the context file cut by its day, the codes file by the passages kept; the prelude defines CTX last, over the mirror paths",
      r10["status"] in ("ran", "differed") and got10.get("passages") == "+3.00" and got10.get("codes on them") == "+4.00"
      and pd.read_csv(ctx_mirror)["id"].tolist() == ["C.2", "C.3", "C.4"] and pd.read_csv(codes_mirror)["id"].tolist() == ["C.2", "C.2", "C.3", "C.4"]
      and rt.cut_rule(cut_ctx) == ("date", "date") and rt.cut_rule(cut_codes) == ("passages", "id")
      and f"CTX = _BambooContext({ctx_mirror!r}, {codes_mirror!r})" in rt.conform_prelude([], [], [], None, (ctx_mirror, codes_mirror)) and "CTX" not in rt.conform_prelude([], [], [], None, None),
      (r10["status"], got10, (r10.get("error") or "")[-300:], os.path.exists(ctx_mirror) and pd.read_csv(ctx_mirror)["id"].tolist(), os.path.exists(codes_mirror) and pd.read_csv(codes_mirror)["id"].tolist()))
check("the CHECK row of a cut run says the rows the method sees - the frame's and each file's after the cut - against the original's rows (2026-10-16; it said the cached load's: 5 rows, 5 passages, 7 codes)",
      "2 rows where the original had 3" in r10["check"] and "the context file: 3 rows where the original had 2" in r10["check"] and "the codes file: 4 rows where the original had 3" in r10["check"]
      and r10["shape"]["frame_rows"] == 2 and r10["shape"]["files"][orig_c]["rows"] == 3 and r10["data"]["rows"] == 2, (r10["check"], r10["shape"].get("frame_rows")))
# the same routine on a load that lacks the codes file (a window without words wrote none): CTX.codes() is the empty stand-in
now10b = dict(now10, aux=[cut_summary, cut_ctx])
out10b = host.run(store.load(rid10), {}, now10b, runner_ctx(df9c, cut_ctx, ""), store, run_dir=os.path.join(aux_dir, "routines", rid10, "v1_2"))
got10b = {x["what"]: x["estimate"] for x in out10b["run"]["results"]}
check("with no codes file in this load: CTX.codes() in the run is the empty stand-in at the recorded path, the passages still the window's", out10b["run"]["status"] in ("ran", "differed") and got10b.get("passages") == "+3.00" and got10b.get("codes on them") == "+0.00" and out10b["run"]["aux_absent"] == ["codes"], (got10b, out10b["run"].get("aux_absent"), (out10b["run"].get("error") or "")[-200:]))
# a choice input whose value is not in the data: refused by the value check through the kernel
R7 = store.load(rid4); v7 = host.version_of(R7)
v7["manifest"]["parameters"].append({"key": "grp", "label": "Group", "type": "choice", "default": "a", "column": "g", "multiple": False, "origin": "x"})
store.save(R7)
pc7 = host.precheck(store.load(rid4), data_now, runner_on(df), values={"grp": "zzz"})
try:
    host.run(store.load(rid4), {"grp": "zzz"}, data_now, runner_on(df), store); refused7 = ""
except host.RoutineRefused as exc:
    refused7 = str(exc)
check("a choice value not in the data: the precheck and the run both say so", not pc7["ok"] and "'zzz' is not in column g" in pc7["line"] and "'zzz' is not in column g" in refused7, (pc7["line"], refused7))
# a choice column that lives in an auxiliary file, not in the frame (2026-10-11, Palo's routine: the summary's `type` was
# reported as not in this data): the check looks in the frame first, then in the files loaded now, and names the file
aux_notes = os.path.join(aux_dir, "activity_summary_20260601_to_20260630.csv")
pd.DataFrame({"hour": [7, 8], "load": [1.0, 2.0], "note": ["a", "b"]}).to_csv(aux_notes, index=False)
R8 = store.load(rid5); v8 = host.version_of(R8)
v8["manifest"]["parameters"].append({"key": "notes", "label": "Notes", "type": "choice", "default": ["a", "b"], "column": "note", "multiple": True, "origin": "x"})
store.save(R8)
now8n = dict(now5, aux=[aux_notes])
pc8a = host.precheck(store.load(rid5), now8n, runner_on(df))
pc8b = host.precheck(store.load(rid5), now8n, runner_on(df), values={"notes": ["a", "zzz"]})
pc8b2 = host.precheck(store.load(rid5), now8n, runner_on(df), values={"notes": ["zzz"]})
pc8c = host.precheck(store.load(rid5), dict(now5, aux=[]), runner_on(df))
check("a choice column in the summary file: the values found there, ok; one of several chosen values the file lacks is a note naming the file (the method keeps the other), still ok; every chosen value absent refuses; with no file loaded the column is not in this data",
      pc8a["ok"] and pc8a["values_missing"] == [] and pc8b["ok"] and pc8b["values_missing"] == [] and pc8b["values_notes"] == ["'zzz' is not in column note of the summary file - the method keeps the other value"] and "keeps the other value" in pc8b["line"]
      and not pc8b2["ok"] and pc8b2["values_missing"] == ["'zzz' is not in column note of the summary file"]
      and not pc8c["ok"] and pc8c["values_missing"] == ["column note is not in this data (for 'a')", "column note is not in this data (for 'b')"],
      (pc8a["values_missing"], pc8b["values_missing"], pc8b["values_notes"], pc8b2["values_missing"], pc8c["values_missing"]))
ev8 = []
out8n = host.run(store.load(rid5), {"notes": ["a", "zzz"]}, now8n, runner_on(df), store, emit=ev8.append, run_dir=os.path.join(aux_dir, "routines", rid5, "v1_9"))
check("the run with one of the chosen values absent goes ahead and the CHECK row carries the note", out8n["run"]["status"] in ("ran", "reproduced", "differed", "failed") and any(e.get("kind") == "check" and "keeps the other value" in (e.get("peek") or "") for e in ev8), [e.get("peek") for e in ev8 if e.get("kind") == "check"])
ps = rt.precheck_script({"note": ["a"]}, [aux_notes, "datasets/x/own_notes.csv"])
check("precheck_script reads the frame first, then each file's header and only the column it needs; a file that cannot be read is skipped", "_pd.read_csv(_p, nrows=0)" in ps and "usecols=[_col]" in ps and "own_notes.csv" in ps)
v8["manifest"]["parameters"].pop(); store.save(R8)
# a choice over a column the script computes (2026-10-15, Palo's routine: a keyword list declared over `head`, derived from the
# plan notes, refused at every run as 'column head is not in this data'): the record knows the data's columns - the frame's
# and the probed files' - so a column it never had is the method's own; its values go to the method as given
rec5 = store.load(rid5)["versions"][0]["manifest"]["data"]
kc = rt.known_columns(rec5)
check("known_columns: the frame's columns and every recorded file's; None when the record has no columns or a recorded file was never probed",
      kc == {"v", "hour", "load", "note"} and rt.known_columns({}) is None and rt.known_columns({"columns": [{"name": "v"}], "aux": ["x.csv"], "aux_shape": {}}) is None, kc)
own, own_notes = rt.own_columns([{"key": "kw", "label": "Session words", "type": "choice", "default": ["VT1", "Vo2"], "column": "head", "multiple": True},
                                 {"key": "n", "label": "Notes", "type": "choice", "default": ["a"], "column": "note", "multiple": True},
                                 {"key": "t", "label": "Cut", "type": "number", "default": 95}], rec5)
check("own_columns: the choice over the computed column loses its column with a note; the choice over the file's column and the number are untouched; a record that cannot say leaves all as they are",
      "column" not in own[0] and own[1].get("column") == "note" and own[2] == {"key": "t", "label": "Cut", "type": "number", "default": 95}
      and own_notes == ["Session words: the values go to the method as given - head is a column the script computes, not one of the data's, so they are not looked for in the data"]
      and rt.own_columns([{"key": "kw", "type": "choice", "default": ["VT1"], "column": "head"}], {})[0][0].get("column") == "head", (own, own_notes))
R8b = store.load(rid5); v8b = host.version_of(R8b)
v8b["manifest"]["parameters"].append({"key": "kw", "label": "Session words", "type": "choice", "default": ["VT1", "Vo2"], "column": "head", "multiple": True, "origin": "the head regex"})
store.save(R8b)
pc8d = host.precheck(store.load(rid5), now8n, runner_on(df))
check("a routine saved with a choice over a computed column: the precheck no longer refuses it - nothing is looked for, ok", pc8d["ok"] and pc8d["values_missing"] == [] and "is not in this data" not in pc8d["line"], (pc8d["ok"], pc8d["line"]))
ev8d = []
out8d = host.run(store.load(rid5), {"kw": ["VT1", "hill"]}, now8n, runner_on(df), store, emit=ev8d.append, run_dir=os.path.join(aux_dir, "routines", rid5, "v1_10"))
check("...and the run goes ahead with the words as given", out8d["run"]["status"] in ("ran", "reproduced", "differed", "failed") and out8d["run"].get("inputs", {}).get("kw") == ["VT1", "hill"], (out8d["run"]["status"], out8d["run"].get("inputs")))
v8b["manifest"]["parameters"].pop(); store.save(R8b)
ok7 = host.precheck(store.load(rid4), data_now, runner_on(df), values={"grp": "a"})
check("a choice value in the data passes", ok7["ok"], ok7["line"])
view0 = host.run_view(store.load(rid4), store, 0)
view2 = host.run_view(store.load(rid4), store, 2)
check("run_view: run zero from the version's record with its files; run 2 from its record with the comparison, the output and the numbers to step through",
      view0["run"]["number"] == 0 and view0["run"]["zero"] and view0["run"]["results"][0]["estimate"] == "+3.00" and "RESULT:" in view0["stdout"]
      and view2["run"]["number"] == 2 and view2["run"]["comparison"]["rows"][0]["mark"] == "down" and "RESULT: rows above the line: +2.00" in view2["stdout"] and view2["numbers"][:3] == [0, 1, 2] and view2["manifest_results"][0]["label"] == "rows above the line", (view0["run"].get("results"), view2.get("numbers")))
try:
    host.run_view(store.load(rid4), store, 99); nope = ""
except host.RoutineRefused as exc:
    nope = str(exc)
check("run_view of a run that does not exist is refused", "no run 99" in nope)
shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
