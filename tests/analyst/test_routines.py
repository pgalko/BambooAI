"""Routines (docs/ROUTINES_DESIGN.md): the pure module, the promoter's prompt under the standing rule, the records a
run keeps, the host's propose/create path over a real kernel with a scripted promoter, and the store.
Run: python3 tests/analyst/test_routines.py"""
import os, sys, json, re, tempfile, shutil
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
    host.propose(nb4, run4.id, cut_promoter([""]), current_data={"df_id": "df4"}); got = ""
except host.RoutineRefused as exc:
    got = str(exc)
check("propose: a reply with nothing but reasoning inside the limit is refused after one call, naming the limit and the seat to adjust",
      len(cut_calls) == 1 and "cut off at its token limit" in got and "nothing arrived but reasoning" in got and "Promoter" in got, (len(cut_calls), got))
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
check("a script error: the run is kept with status failed, naming the cell, the comparison all missing", out5["run"]["status"] == "failed" and out5["run"]["line"].startswith("failed at cell 2:") and out5["run"]["comparison"]["missing"] == 1
      and store.load(rid4)["runs"][-1]["status"] == "failed", out5["run"]["line"])
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
plan5 = host.load_plan(store.load(rid5))
check("load_plan: the source, the window's length, the auxiliary kinds and the metrics as the original load asked", plan5["source"] == "intervals" and plan5["window_days"] == 59 and plan5["aux_kinds"] == ["summary"] and plan5["start"] == "2026-08-12", plan5)
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
check("a run on the later window: the method read this window's summary under the recorded name (bound in the executed text, the stored script untouched), its lines moved, the copy in the run's folder carries the column the new file lacked",
      r5["status"] == "ran" and [rt.number(x["estimate"]) for x in r5["results"]] == [6.0, 7.0] and r5["bindings"] and r5["bindings"][0][0] == aux_old and r5["bindings"][0][1].startswith(run_dir5)
      and r5["shape"]["files"][aux_old]["missing"] == ["note"] and r5["shape"]["files"][aux_old]["rows"] == 6 and aux_old in store.load(rid5)["versions"][0]["script"]
      and os.path.exists(os.path.join(run_dir5, "activity_summary_20260910_to_20261010.csv")), (r5["status"], r5["results"], r5.get("bindings"), r5.get("shape")))
# a window whose load produced no summary at all: the method sees an empty table, the CHECK row and the record say so
now5c = dict(now5, aux=[])
pc5c = host.precheck(store.load(rid5), now5c, runner_on(df))
check("precheck with the summary absent: ok (the coach decides), the line says the method will see an empty table", pc5c["ok"] and pc5c["aux"]["absent"] == ["summary"] and "summary absent in this data" in pc5c["line"], pc5c["line"])
ev5c = []
out5c = host.run(store.load(rid5), {}, now5c, runner_on(df), store, emit=ev5c.append, run_dir=os.path.join(aux_dir, "routines", rid5, "v1_2"))
r5c = out5c["run"]
check("a run with the summary absent: an empty table with the recorded columns stood in, the method failed on it (nothing to count), the run is kept and names the cell, the record lists the absent file",
      r5c["status"] == "failed" and r5c["line"].startswith("failed at cell 1") and r5c["aux_absent"] == ["summary"] and any("summary absent" in (e.get("peek") or "") for e in ev5c if e.get("kind") == "check")
      and os.path.exists(os.path.join(aux_dir, "routines", rid5, "v1_2", "activity_summary_20260812_to_20261010.csv")), (r5c["status"], r5c["line"], r5c.get("aux_absent")))
# a loader's file named with something other than the recorded dates (2026-10-10, Palo's second live run: the promoter had
# written the loaded window into the summary's name as an f-string on an input, so the recorded name was gone from the text
# and the run could not bind it): bound by kind, whatever the rest of the name says
fs = "au = pd.read_csv(f\"datasets/local/activity_summary_{str(INPUTS['window'][0]).replace('-','')}_to_{str(INPUTS['window'][1]).replace('-','')}.csv\")\nw = pd.read_csv('datasets/local/wellness_data_20260712_to_20261010.csv')\nx = pd.read_csv('datasets/local/own_notes.csv')"
bt, bsubs = rt.bind_script(fs, {"datasets/local/activity_summary_20260712_to_20261010.csv": "datasets/local/activity_summary_20260112_to_20260710.csv"}, "datasets/local/routines/r/v1_1", "datasets/local",
                           {"datasets/local/wellness_data_20260712_to_20261010.csv": "datasets/local/routines/r/v1_1/wellness_data_20260712_to_20261010.csv"})
check("bind_script: a summary named by an f-string on an input is bound to this load's summary by its kind; the wellness name to its stand-in; a file of the person's own under the datasets folder to the run's folder",
      "pd.read_csv(f\"datasets/local/activity_summary_20260112_to_20260710.csv\")" in bt and [k for _, _, k in bsubs] == ["bound", "placeholder", "cache"] and "routines/r/v1_1/own_notes.csv" in bt, (bt, bsubs))
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
      any("could not be prepared" in (e.get("peek") or "") for e in ev5d if e.get("kind") == "check") and r5d["bindings"] and r5d["bindings"][0][2] == "placeholder" and r5d["bindings"][0][1].endswith("/v1_3/activity_summary_20260812_to_20261010.csv")
      and os.path.exists(os.path.join(aux_dir, "routines", rid5, "v1_3", "activity_summary_20260812_to_20261010.csv")) and "FileNotFoundError" not in (r5d.get("error") or "") and r5d["status"] == "failed",
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
check("a bound file gone before the cells ran: the prelude stood an empty table in for it (the file is there, with the recorded columns); the run failed on the empty table, not on a missing file",
      r5e["bindings"][0][2] == "bound" and os.path.exists(now5e["aux"][0]) and pd.read_csv(now5e["aux"][0]).columns.tolist() == ["hour", "load", "note"] and "FileNotFoundError" not in (r5e.get("error") or "")
      and "empty sequence" in (r5e.get("error") or ""), (r5e.get("bindings"), (r5e.get("error") or "")[-160:]))
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
cm4 = rt.cache_match({"source": "intervals", "aux_kinds": [], "metrics": []}, insp, "2026-07-13", "2026-10-10")
cm5 = rt.cache_match({"source": "endura", "aux_kinds": ["turns"]}, insp, race_id="2")
cm6 = rt.cache_match({"source": "endura", "aux_kinds": ["turns", "climbs"]}, insp, race_id=2)
cm7 = rt.cache_match({"source": "sweatstack", "aux_kinds": []}, insp, "2026-07-12", "2026-10-10")
check("cache_match: the same source, window and metrics with every wanted file is a hit (the frame's id, the files' paths, the rows, a line saying no download); a wanted file missing, other metrics' frame used instead, another window, no hit - each with its reason",
      cm1["hit"] and cm1["df_id"] == "a" and cm1["files"] == ["datasets/u/activity_summary_20260712_to_20261010.csv"] and cm1["rows"] == 1000 and "no download" in cm1["line"] and "with summary" in cm1["line"]
      and not cm2["hit"] and "without wellness" in cm2["line"] and cm3["hit"] and cm3["df_id"] == "b" and not cm4["hit"] and "not in the cache" in cm4["line"], (cm1, cm2, cm3, cm4))
check("cache_match: an Endura event by its id with its files; a file missing is no hit; SweatStack never matches (its entries do not say which subjects they hold); no window or event asked - nothing to say",
      cm5["hit"] and cm5["df_id"] == "e" and cm5["files"] == ["datasets/u/race_turns_race_2.csv"] and not cm6["hit"] and "without climbs" in cm6["line"] and cm7 == {"hit": False, "line": ""}
      and rt.cache_match({"source": "intervals", "aux_kinds": []}, insp) == {"hit": False, "line": ""} and rt.cache_match({"source": "intervals"}, None, "2026-07-12", "2026-10-10")["hit"] is False, (cm5, cm6, cm7))
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
