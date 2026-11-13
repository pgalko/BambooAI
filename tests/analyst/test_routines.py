"""Routines (docs/ROUTINES_DESIGN.md): the pure module, the promoter's prompt under the standing rule, the records a
run keeps, the host's propose/create path over a real kernel with a scripted promoter, and the store.
Run: python3 tests/analyst/test_routines.py"""
import os, sys, json, re, tempfile, shutil, glob, time
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.dirname(os.path.abspath(__file__)), ROOT, os.path.join(ROOT, "delve")]
import _stubs  # noqa: F401
import pandas as pd, numpy as np
from analyst import routines as rt
from analyst.notebook import Notebook, Turn, Run
from analyst.replay import assemble
from kernel import PersistentKernel

os.chdir(tempfile.mkdtemp())                           # a routine's run folders are named from where the kernel runs: this file's land in a folder of their own
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
lines = [ln for _s, _k, ln in rt.read_run("noise\nRESULT: a: +1 (95% CI +0 to +2) u, up\nmore\nRESULT: b: +2.50\n")["lines"]]
check("read_run: every RESULT line of a printed output, in order", [x["what"] for x in lines] == ["a", "b"] and lines[1]["estimate"] == "+2.50")

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
check("key_column: id, *_id, *_ids, id_*, uuid read as keys; other names do not (§18)",
      all(rt.key_column(n) for n in ("id", "activity_id", "ride_ids", "id_session", "uuid", "Session_ID")) and not any(rt.key_column(n) for n in ("humidity", "grid", "name", "power", "date", "idle_time", "")))
check("key_inputs: the inputs that read as identifiers - a choice over a key column ('key over column'), a list named *_ids (the key alone); a band of numbers, a choice over names and a toggle are not",
      rt.key_inputs([{"key": "rides", "type": "choice", "column": "activity_id"}, {"key": "band", "type": "numbers"}, {"key": "who", "type": "choice", "column": "name"},
                     {"key": "heat_ride_ids", "type": "numbers", "column": "none"}, {"key": "drop_id", "type": "toggle"}]) == ["rides over activity_id", "heat_ride_ids"])
check("unfit_line: the literals as the refusal reads them, cells named, capped", rt.unfit_line([{"cell": 10, "what": "three sessions named by identifier; no rule picks them"}, {"what": "a date"}, "a bare clause", 7, {}]) == "cell 10: three sessions named by identifier; no rule picks them; a date; a bare clause")
check("parse_promoter: 'recomputed' and 'unfit' are read as lists and default to empty ones", rt.parse_promoter('{"unfit": [{"cell": 2, "what": "x"}], "recomputed": ["y"]}')["unfit"] == [{"cell": 2, "what": "x"}] and rt.parse_promoter('{}')["recomputed"] == [] and rt.parse_promoter('{}')["unfit"] == [])
check("parse_promoter: 'compare' is read as a list and defaults to an empty one",
      rt.parse_promoter('{"compare": [{"line": 2, "name": "x"}]}')["compare"] == [{"line": 2, "name": "x"}] and rt.parse_promoter('{"inputs": []}')["compare"] == [])
try:
    rt.parse_promoter('{"compare": 3}'); _cmp_bad = False
except ValueError as exc:
    _cmp_bad = "not a list" in str(exc)
check("parse_promoter: a 'compare' that is not a list is refused", _cmp_bad)
# ---- the promoter's pick (§15.1): the lines a run compares, named; every other line dropped; no usable pick keeps all ----
_exp_pick = [{"cell": 2, "index": 0, "label": "a, first form", "estimate": "1", "dropped": False}, {"cell": 3, "index": 0, "label": "a, second form", "estimate": "2", "dropped": False},
             {"cell": 3, "index": 1, "label": "a check", "estimate": "3", "dropped": False}, {"cell": 4, "index": 0, "label": "a, final form, 21 rows", "estimate": "4", "dropped": False}]
_picked = rt.pick_results(_exp_pick, [{"line": 4, "name": "  a  "}, {"line": "3", "name": "the check"}, {"line": 9, "name": "none"}, {"line": "x"}, "junk", {"line": 4, "name": "again"}])
check("pick_results: the lines named are kept with their names (whitespace folded, the first entry of a line standing), the rest dropped; a number out of range, a non-number and a non-object are ignored",
      [(r["dropped"], r.get("name")) for r in _picked] == [(True, None), (True, None), (False, "the check"), (False, "a")] and [r["label"] for r in _picked] == [r["label"] for r in _exp_pick], _picked)
check("pick_results: a name longer than 60 characters is cut; an empty name leaves the line kept without one",
      len(rt.pick_results(_exp_pick, [{"line": 1, "name": "n" * 80}])[0]["name"]) == 60 and "name" not in rt.pick_results(_exp_pick, [{"line": 1, "name": "   "}])[0] and not rt.pick_results(_exp_pick, [{"line": 1, "name": "   "}])[0]["dropped"])
check("pick_results: no usable pick (absent, empty, nothing valid) keeps every line, without names",
      all(not r["dropped"] and "name" not in r for c in (None, [], [{"line": 0}, {"line": 99}], ["x"]) for r in rt.pick_results(_exp_pick, c)))
check("pick_results: the input rows are not changed", all(not r["dropped"] and "name" not in r for r in _exp_pick))
# the person's instruction answered (§15.6): the lines it reached, named; the quantities it reached no line for
_tl, _tm = rt.tracked_lines(_exp_pick, [{"asked": " a,  final ", "lines": [{"line": 4, "name": " a  final "}]}, {"asked": "the check", "lines": [3, {"line": "x"}]},
                                       {"asked": "nothing gives it", "lines": []}, {"asked": "a, final again", "lines": [{"line": 4, "name": "again"}]}, {"asked": "out of range", "lines": [{"line": 9}]}, "junk", {"lines": []}])
check("tracked_lines: a line given is kept under its name (whitespace folded; a bare number keeps the line unnamed); a quantity with no valid line is missing - none given, out of range, or a line already given for an earlier quantity; junk and a nameless entry are ignored",
      _tl == {4: "a final", 3: ""} and _tm == ["nothing gives it", "a, final again", "out of range"], (_tl, _tm))
check("tracked_lines: nothing answered, nothing kept or missing", rt.tracked_lines(_exp_pick, None) == ({}, []) and rt.tracked_lines(_exp_pick, []) == ({}, []))
_pe = rt.pick_results(_exp_pick, [{"line": 1, "name": "first"}, {"line": 3, "name": ""}], {3: "the check", 4: "final", 1: "other"})
check("pick_results with the instruction's lines: they are kept whatever the pick says, the pick's name standing where it has one, the instruction's filling an empty one; a pick of nothing plus the instruction's lines keeps those alone",
      [(r["dropped"], r.get("name")) for r in _pe] == [(False, "first"), (True, None), (False, "the check"), (False, "final")]
      and [r["dropped"] for r in rt.pick_results(_exp_pick, [], {2: "n"})] == [True, False, True, True], _pe)
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
_e3, _a3, _f3 = rt.apply_edits(body, [{"cell": 1, "find": "threshold = 155", "replace": "threshold = INPUTS['t']\nRESULT('rows', float(len(df)), None, None, 'rows', 'n/a')"}])
check("apply_edits (§15.6): an edit that adds or removes a RESULT call is refused with the reason - the method's outputs are not the promoter's to change; one that only reads an input inside a RESULT call applies",
      _e3 == body and not _a3 and _f3 and _f3[0]["keys"] == ["t"] and "adds or removes a RESULT call" in _f3[0]["reason"]
      and not rt.apply_edits("\n# --- cell 1 ---\nRESULT('a', 5, None, None, 'n', 'n/a')\n", [{"cell": 1, "find": "RESULT('a', 5,", "replace": "RESULT('a', INPUTS['a'],"}])[2], _f3)
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
check("promoter_user: the cells the report cites, as a section after the ledger, sorted and once each; none cited, no section (§15.5)",
      "THE REPORT CITES" not in u and rt.promoter_user("Q?", "A.", "d", "c", [], cited=[5, 2, 5]).endswith("THE REPORT CITES (the cells the answer was read from): cells 2, 5")
      and rt.promoter_user("Q?", "A.", "d", "c", [], cited=[3]).endswith("THE REPORT CITES (the cells the answer was read from): cell 3"))
check("PROMOTER_SYSTEM: asks for edits, not a retyped script; the five types; at most five; the reply's shape", all(s in rt.PROMOTER_SYSTEM for s in ("find/replace edits", "never by retyping", "at most five", "date_window", "toggle", '"edits"', "INPUTS = {...}")))
check("PROMOTER_SYSTEM: the pick (§15.5) - the cited cells hold the final forms, a quantity recomputed on part of the data is a check, a series is compared whole or not at all",
      all(s in rt.PROMOTER_SYSTEM for s in ("the cells the report cites, when it cites any", "Where the report cites cells, those are the cells the answer was read from",
                                              "with part of the data left out, under another cut or a what-if, is a check", "are compared whole: every line of the series, from the cell that printed it last, or none of them")))
check("PROMOTER_SYSTEM (§15.6): the person's instruction is received, is no request to compute - the method fixed, no input made for it - and is answered line by line under \"tracked\" from the ledger, a match being that quantity and not the nearest, a quantity no line gives an empty list and nothing more; every line given is compared",
      all(s in rt.PROMOTER_SYSTEM for s in ("their instruction on what the runs should track", "is not a request to compute anything: the method is fixed, nothing is computed, added or rewritten for what it names, and no input is made for it",
                                              "a line is a match when it is that quantity, not the nearest one", "answered with an empty list and nothing more: no reason, no substitute",
                                              "Every line given here is compared, whether or not step 5 picked it", '"tracked": [{"asked":', '"tracked" is empty when there is no instruction')))
_ui = rt.promoter_user("Q?", "A.", "d", "c", ["1. [cell 1] a: +1"], None, [1], "  track a,\n and b ")
check("promoter_user (§15.6): the instruction as a section right after the ledger, before the cited cells; none given, no section",
      "RESULT LINES THE CELLS RECORDED (numbered; the method's outputs, which must still be produced, in this order):\n1. [cell 1] a: +1\n\nTHE PERSON'S INSTRUCTION (what the runs should track; answer it under \"tracked\", from the ledger alone):\ntrack a,\n and b\n\nTHE REPORT CITES" in _ui
      and "INSTRUCTION" not in rt.promoter_user("Q?", "A.", "d", "c", [], None, [], "   "), _ui)
try:
    rt.parse_promoter('{"tracked": {}}'); _tr_bad = False
except ValueError as exc:
    _tr_bad = "'tracked' is not a list" in str(exc)
check("parse_promoter: 'tracked' is read as a list when given and refused otherwise; absent, it is left absent (the host asks again about that)",
      _tr_bad and rt.parse_promoter('{"tracked": [{"asked": "a", "lines": []}]}')["tracked"] == [{"asked": "a", "lines": []}] and "tracked" not in rt.parse_promoter('{}'))

# ---- run zero's verdict: the chain's lines, printed again on its own data ----
exp = [{"cell": 1, "index": 0, "label": "a", "estimate": "+1.0", "low": "+0.5", "high": "+1.5"}, {"cell": 2, "index": 0, "label": "b", "estimate": "+2", "low": None, "high": None}]
got_same = [{"estimate": "+1.0", "low": "+0.5", "high": "+1.5"}, {"estimate": "+2", "low": None, "high": None}]
_printed = lambda lines: {"lines": [(None, k, ln) for k, ln in enumerate(lines)]}
check("check_zero: identical numbers reproduce", rt.check_zero(exp, _printed(got_same)) == ("reproduced", "reproduced: 2 result line(s) identical"))
check("check_zero: a different estimate differs, naming the line", rt.check_zero(exp, _printed([{"estimate": "+1.1", "low": "+0.5", "high": "+1.5"}, got_same[1]])) == ("differed", "1 of 2 result lines differ ([cell 1] a: +1.0 -> +1.1)"))
check("check_zero: a missing line differs by count; an error fails with its line; nothing expected reproduces when it ran",
      rt.check_zero(exp, _printed(got_same[:1])) == ("differed", "1 result line(s) came back, 2 expected")
      and rt.check_zero(exp, _printed([]), "Traceback\nKeyError: 'x'") == ("failed", "the script stopped with an error (KeyError: 'x')") and rt.check_zero([], _printed([]))[0] == "reproduced")
check("same_numbers: the same value written with separators is the same; equal as printed is the same (a line without a number against itself); two different words are not",
      rt.check_zero([{"estimate": "+1,234", "low": None, "high": None, "cell": 1, "index": 0, "label": "x"}], _printed([{"estimate": "+1234", "low": None, "high": None}]))[0] == "reproduced"
      and rt.same_numbers({"estimate": "nan"}, {"estimate": "nan"}) and not rt.same_numbers({"estimate": "linear"}, {"estimate": "cubic"}) and not rt.same_numbers({"estimate": "+1", "low": "+0"}, {"estimate": "+1", "low": None}))

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
check("RoutineStore.by_origin: the versions born from a chain, for the favourite's card, with the routine's instruction (none here)", store.by_origin() == {("T", "C"): [{"id": rid, "name": "Rows above a line", "version": 1, "instruction": ""}]})
check("script_with_defaults: the download carries the INPUTS block with the defaults", "INPUTS = {\n    'threshold': 155\n}" in rt.script_with_defaults(loaded["versions"][0]))
check("RoutineStore.delete: the folder goes; a second delete is False", store.delete(rid) and not store.load(rid) and not store.delete(rid) and store.all() == [])
check("source_kind: the executor's names map to the four kinds", rt.source_kind({"source": "csv"}) == "file" and rt.source_kind({"source": "intervals"}) == "intervals" and rt.source_kind({"name": "x.parquet"}) == "file" and rt.source_kind({}) == "none")

# ---- the host's path: propose and create over a real kernel with a scripted promoter ----
from bambooai import routines_host as host
host.RETRY_PAUSE = 0.0                                  # a script that could not be carried out is tried once more at once here
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
check("propose: the promoter is called with the question, the cells, the ledger and the cell the report cites; the proposal carries the inputs, the results, the figures and the edited script",
      prompts and prompts[0][0] == rt.PROMOTER_SYSTEM and "How many rows" in prompts[0][1] and "1. [cell 2] rows above the line: +3" in prompts[0][1]
      and "THE REPORT CITES (the cells the answer was read from): cell 2" in prompts[0][1]
      and p["name"] == "Rows above a line" and p["inputs"][0]["key"] == "threshold" and p["results"][0]["label"] == "rows above the line" and "INPUTS['threshold']" in p["cells_text"] and "script" not in p and p["data"]["name"] == "small.csv" and p["data_state"] == "same", (p.get("inputs"), p.get("data_state"), [e.get("type") for e in events]))
check("propose: the pane saw a quiet turn start and its end; the dialog's checklist (§17) saw the steps - the chain read with its facts, the data checked (running, then its facts), the model running then done around the turn, the proposal running",
      [e.get("type") for e in events if e.get("type") != "step"] == ["turn_start", "turn_end"] and [e for e in events if e.get("type") == "turn_start"][0].get("quiet")
      and [(e["step"], e.get("state", "done"), e.get("detail", "")) for e in events if e.get("type") == "step"] == [("chain", "done", "2 cells · 1 result · 0 figures"), ("data", "running", ""), ("data", "done", "5 rows · 2 columns"), ("model", "running", ""), ("model", "done", ""), ("proposal", "running", "")]
      and [e.get("type") for e in events] == ["step", "step", "step", "turn_start", "step", "turn_end", "step", "step"], events)
_ev_steps = [e for e in events if e.get("type") == "step"]
events[:] = [e for e in events if e.get("type") != "step"]      # the create test below reads the pane's events by position
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

# ---- the reading of the chain (docs/ROUTINES_DESIGN.md §19): what each statement reads and writes, from the code alone. It gives the
# promoter's view - the chain without its exploration - and the statements a run needs; two runs' figures are compared as pictures
import base64 as _b64
def _fig(y, fmt="json", chain="c1"):
    return json.dumps({"type": "plot", "data": json.dumps({"data": [{"type": "bar", "y": y}], "layout": {"title": {"text": "t"}}}) if fmt == "json" else y, "format": fmt, "id": "plot_1", "chain_id": chain})
_arr = lambda xs: {"dtype": "f8", "bdata": _b64.b64encode(np.array(xs, dtype="f8").tobytes()).decode()}
check("same_figures: the same picture under another chain id and wrapper is the same; a number moved past 1e-9 is not; a typed array within 1e-12 is; nan as nan; a PNG byte for byte; the count must match",
      rt.same_figures([_fig([1, 2, 3])], [_fig([1, 2, 3.0000000000001], chain="c2")]) == (True, "1 figure identical")
      and rt.same_figures([_fig([1, 2, 3])], [_fig([1, 2, 3.1])]) == (False, "figure 1 differs")
      and rt.same_figures([{"type": "plot", "data": {"data": [{"y": _arr([1.0, 2.0])}], "layout": {}}, "format": "json"}], [{"type": "plot", "data": {"data": [{"y": _arr([1.0, 2.0 + 1e-13])}], "layout": {}}, "format": "json"}])[0]
      and not rt.same_figures([{"data": {"data": [{"y": _arr([1.0, 2.0])}]}, "format": "json"}], [{"data": {"data": [{"y": _arr([1.0, 2.5])}]}, "format": "json"}])[0]
      and rt.same_figures([_fig([float("nan"), 1])], [_fig([float("nan"), 1])])[0] and rt.same_figures([_fig("iVBOR...", "png")], [_fig("iVBOR...", "png")])[0] and not rt.same_figures([_fig("iVBOR...", "png")], [_fig("iVBOQ...", "png")])[0]
      and rt.same_figures([_fig([1])], []) == (False, "0 figures came back, 1 expected") and rt.same_figures([], []) == (True, "no figures"))
# prune_cells over a made-up script (§19.3: by statement): a statement stays when a RESULT line, a figure, a file written or the only read
# of an input rests on it, or when a later kept statement reads what it makes; everything else goes - the prints, a check nothing reads, a
# loop that only prints, a list filled through a function that nothing reads - with the cells left empty; imports and the capture switches
# stay wherever they are; a cell that does not parse prunes nothing
_script = """
# --- cell 1 ---
import numpy as np, pandas as pd
print("rows", df.shape)
print(df.dtypes.to_string())
g = df.groupby("a").size()
print(g.to_string())

# --- cell 2 ---
d = df[df.power > 0].copy()
d["x"] = d.power * INPUTS['scale']
print("kept", len(d))

# --- cell 3 ---
tab = d.groupby("a")["x"].mean()
print(tab.to_string(),
      "two lines")
for a_ in tab.index:
    print(a_)
RESULT('mean x', float(tab.mean()), None, None, 'W', 'n/a')
_bamboo_capture[0] = False

# --- cell 4 ---
check = d.x.describe()
print(check)
_bamboo_capture[0] = True

# --- cell 5 ---
names = []
def note(v):
    names.append(v)

# --- cell 6 ---
note('x')
tab.to_csv('out.csv')

# --- cell 7 ---
import plotly.graph_objects as go
fig = go.Figure(go.Bar(x=list(tab.index), y=list(tab.values)))
fig.show()

# --- cell 8 ---
lbl = INPUTS['label']
print(lbl)
"""
_pruned, _dropped, _cut, _problem = rt.prune_cells(_script, [7])
check("prune_cells: cells 1 and 4 go (nothing reads what they make) and cell 5 with the call that used it (a list nothing reads); cell 2 stays (d, read later), 3 (RESULT), 6 (a file written), 7 (the figure), 8 (the only read of an input); every "
      "print goes, the loop that only prints with them - 16 lines in all; cell 1's import and the switches between cells stay; the markers keep their numbers",
      _problem == "" and _dropped == [1, 4, 5] and _cut == 16
      and [ln for ln in _pruned.splitlines() if ln.startswith("# --- cell")] == ["# --- cell %d ---" % n for n in (2, 3, 6, 7, 8)]
      and "print(" not in _pruned and "for a_" not in _pruned and "note(" not in _pruned and "names" not in _pruned and "_bamboo_capture[0] = False" in _pruned and "_bamboo_capture[0] = True" in _pruned
      and _pruned.startswith("\nimport numpy as np, pandas as pd\n# --- cell 2 ---\n") and "INPUTS['scale']" in _pruned and "lbl = INPUTS['label']" in _pruned and "tab.to_csv('out.csv')" in _pruned
      and "\n\n\n" not in _pruned, (_dropped, _cut, _pruned))
check("prune_cells: pruning the pruned changes nothing; a script with nothing to cut comes back as it is; a cell that does not parse prunes nothing and says which",
      rt.prune_cells(_pruned, [7]) == (_pruned, [], 0, "")
      and rt.prune_cells("\n# --- cell 1 ---\nx = 1\nRESULT('x', float(x), None, None, '', 'n/a')\n", []) == ("\n# --- cell 1 ---\nx = 1\nRESULT('x', float(x), None, None, '', 'n/a')\n", [], 0, "")
      and rt.prune_cells("\n# --- cell 1 ---\nx = (\n# --- cell 2 ---\nprint(1)\n", []) == ("\n# --- cell 1 ---\nx = (\n# --- cell 2 ---\nprint(1)\n", [], 0, "cell 1 could not be parsed ('(' was never closed)"))
_defs = rt.prune_cells("\n# --- cell 1 ---\nlst = []\n# --- cell 2 ---\nlst.append(1)\n# --- cell 3 ---\nd = df.copy()\n# --- cell 4 ---\nd.sort_values('v', inplace=True)\n# --- cell 5 ---\nd.attrs['k'] = 1\n# --- cell 6 ---\nimport math\n# --- cell 7 ---\ndef f():\n    return math.pi * len(lst) * len(d)\n# --- cell 8 ---\nRESULT('r', f(), None, None, '', 'n/a')\n", [])
check("prune_cells: what counts as a definition - an in-place call (append, inplace=True) and a subscript or attribute assignment keep the statement for a later reader; a name read only in a function body is a read; an import cell goes but its import line stays",
      _defs[1] == [6] and "import math\n# --- cell 7 ---" in _defs[0] and [ln for ln in _defs[0].splitlines() if ln.startswith("# --- cell")] == ["# --- cell %d ---" % n for n in (1, 2, 3, 4, 5, 7, 8)]
      and rt.prune_cells("\n# --- cell 1 ---\nlst = []\n# --- cell 2 ---\nother = [1]\n# --- cell 3 ---\nother.append(2)\n# --- cell 4 ---\nRESULT('r', float(len(lst)), None, None, '', 'n/a')\n", [])[1] == [2, 3], _defs)
# reads are what a statement takes from before it: a loop variable or a temporary bound again is no link to earlier code that used the same
# name; a comprehension's and a lambda's own names neither; a frame read before it is rebound is
check("prune_cells: a later cell that binds g, s and n itself before reading them does not keep the earlier cell that used those names; one that reads d before rebinding it does; comprehension and lambda names are their own",
      rt.prune_cells("\n# --- cell 1 ---\nfor g in range(3):\n    s = g * 2\nn = 5\nprint(n)\n# --- cell 2 ---\nn = 0\nfor g in df.v:\n    s = g + 1\n    n += s\nRESULT('n', float(n), None, None, '', 'n/a')\n", [])[1] == [1]
      and rt.prune_cells("\n# --- cell 1 ---\nd = df.copy()\n# --- cell 2 ---\nd = d[d.v > 1]\nRESULT('n', float(len(d)), None, None, '', 'n/a')\n", [])[1] == []
      and rt.prune_cells("\n# --- cell 1 ---\nk = 3\nx = 1\n# --- cell 2 ---\nys = [k for k in range(4)]\nf = lambda k: k + 1\nRESULT('n', float(f(len(ys))), None, None, '', 'n/a')\n", [])[1] == [1]
      and rt.prune_cells("\n# --- cell 1 ---\nk = 3\n# --- cell 2 ---\nys = [k * k for k_ in range(4)]\nRESULT('n', float(sum(ys)), None, None, '', 'n/a')\n", [])[0].count("k = 3") == 1)
_R = "RESULT('n', float(%s), None, None, '', 'n/a')"
def _left(code, figs=()):
    """The statements prune_cells leaves of one cell's code."""
    return [ln for ln in rt.prune_cells("\n# --- cell 1 ---\n" + code + "\n", list(figs))[0].strip("\n").split("\n")[1:] if ln.strip()]
# the case 0283 missed (2026-11-13, Palo's power-curve chain): every cell loads the frame again, so a cell that only looked was held by the
# next reader of df; a name bound whole again cuts that link, and a check written inside a cell the method needs goes with its comment
_looked = rt.prune_cells("\n# --- cell 1 ---\ndf = DS.load()\nlook = df[df.g == 'b']\nprint(len(look))\n# --- cell 2 ---\ndf = DS.load()\n" + _R % "len(df)" + "\n# --- cell 3 ---\nfig = draw(df)\nfig.show()\n", [3])
check("prune_cells (§19.3): a cell that only looked goes although it loaded the frame a later cell reads - the cell between loads it whole again; a check inside a cell the method needs goes, the comment standing on it too, the comment on a kept "
      "statement stays; a statement over two lines goes whole; statements sharing a line stay or go together",
      _looked[1] == [1] and "df.g == 'b'" not in _looked[0] and _looked[0].count("df = DS.load()") == 1
      and _left("kept = df[df.v > 155]\n# a look at group b\none = df[df.g == 'b']\nprint(len(one), 'rows of b')\n# the count\n" + _R % "len(kept)") == ["kept = df[df.v > 155]", "# the count", _R % "len(kept)"]
      and _left("x = (1 +\n     2)\nprint(x)\ny = 3\n" + _R % "y") == ["y = 3", _R % "y"]
      and _left("a = 1; b = 2\nc = 3; print(c)\n" + _R % "b") == ["a = 1; b = 2", _R % "b"], _looked)
check("prune_cells (§19.3): a call does what the function's body does - a loop that fills a list through a function stays, a function that changes what it is handed keeps the statement that hands it over, a call of a function that records a RESULT "
      "line stays; a function nothing kept calls goes; what the reading cannot see is an alias (the shorter run is held to run zero for that)",
      _left("flags = []\ndef flag(v):\n    flags.append(v)\nfor v in df.v:\n    if v > 150:\n        flag(v)\nprint(len(flags))\n" + _R % "len(flags)")
      == ["flags = []", "def flag(v):", "    flags.append(v)", "for v in df.v:", "    if v > 150:", "        flag(v)", _R % "len(flags)"]
      and _left("def mark(t):\n    t['seen'] = True\ntab = {}\nok = mark(tab)\nshown = mark({})\n" + _R % "len(tab)") == ["def mark(t):", "    t['seen'] = True", "tab = {}", "ok = mark(tab)", _R % "len(tab)"]
      and _left("def record(x):\n    RESULT('x', float(x), None, None, '', 'n/a')\ndef unused(x):\n    return x\nrecord(3)") == ["def record(x):", "    RESULT('x', float(x), None, None, '', 'n/a')", "record(3)"]
      and _left("flags = []\nalso = flags\nalso.append(1)\n" + _R % "len(flags)") == ["flags = []", _R % "len(flags)"])
check("prune_cells (§19.3): a bare call is there for its effect - on the object it is called on (kept when that object is read later), on a module (a setting, a seed: kept); a check that can stop the run is the method's, with what it reads; a del "
      "of a column changes the frame; a figure cell is kept whole, its prints too",
      _left("fig = make()\nfig.update_layout(title='t')\nother = make()\nother.update_layout(title='u')\nfig.show()") == ["fig = make()", "fig.update_layout(title='t')", "fig.show()"]
      and _left("import warnings\nwarnings.filterwarnings('ignore')\npd.set_option('display.width', 200)\nx = 1\n" + _R % "x") == ["import warnings", "warnings.filterwarnings('ignore')", "pd.set_option('display.width', 200)", "x = 1", _R % "x"]
      and _left("chk = df.v.sum()\nspare = df.v.max()\nassert chk > 0\n" + _R % "len(df)") == ["chk = df.v.sum()", "assert chk > 0", _R % "len(df)"]
      and _left("tmp = df.copy()\ndel tmp['g']\nprint(tmp.shape)\n" + _R % "tmp.shape[1]") == ["tmp = df.copy()", "del tmp['g']", _R % "tmp.shape[1]"]
      and _left("print('drawing')\nfig = 1", figs=[1]) == ["print('drawing')", "fig = 1"])
check("prune_cells (§19.3): a draw reads the generator's state and moves it on, so a draw nothing else reads stays when a later draw is kept - the global generators and one made by default_rng alike; a seed set again cuts the link; without a later "
      "draw the look goes",
      _left("np.random.seed(1)\nlook = np.random.rand(3)\nprint(look)\nx = np.random.rand()\n" + _R % "x") == ["np.random.seed(1)", "look = np.random.rand(3)", "x = np.random.rand()", _R % "x"]
      and _left("rng = np.random.default_rng(0)\npeek = rng.normal(size=2)\nprint(peek)\nx = rng.normal()\n" + _R % "x") == ["rng = np.random.default_rng(0)", "peek = rng.normal(size=2)", "x = rng.normal()", _R % "x"]
      and _left("np.random.seed(1)\nlook = np.random.rand(3)\nnp.random.seed(2)\nx = np.random.rand()\n" + _R % "x") == ["np.random.seed(1)", "np.random.seed(2)", "x = np.random.rand()", _R % "x"]
      and _left("rng = np.random.default_rng(0)\npeek = rng.normal(size=2)\nx = 2\n" + _R % "x") == ["x = 2", _R % "x"]
      and _left("def boot(a, gen):\n    return gen.choice(a).mean()\nrng = np.random.default_rng(0)\ntrial = boot(df.v, rng)\nx = boot(df.v, gen=rng)\n" + _R % "x")
      == ["def boot(a, gen):", "    return gen.choice(a).mean()", "rng = np.random.default_rng(0)", "trial = boot(df.v, rng)", "x = boot(df.v, gen=rng)", _R % "x"])
check("prune_cells (§19.3): what the code does not show on its face - a name read inside a query or eval string is read; a function handed to a call may be called by it; a function's global is the chain's own name; a print by another name "
      "(pprint) only shows",
      _left("thr = 150\nspare = 3\nsub = df.query('v > @thr')\n" + _R % "len(sub)") == ["thr = 150", "sub = df.query('v > @thr')", _R % "len(sub)"]
      and _left("a = df.v\nb = 2\nspare = 9\nz = pd.eval('a * b')\n" + _R % "z.sum()") == ["a = df.v", "b = 2", "z = pd.eval('a * b')", _R % "z.sum()"]
      and _left("seen = []\ndef keep(v):\n    seen.append(v)\n    return v\ndoubled = df.v.apply(keep)\n" + _R % "len(seen)") == ["seen = []", "def keep(v):", "    seen.append(v)", "    return v", "doubled = df.v.apply(keep)", _R % "len(seen)"]
      and _left("n = 0\ndef bump():\n    global n\n    n += 1\nbump()\nspare = 5\n" + _R % "n") == ["n = 0", "def bump():", "    global n", "    n += 1", "bump()", _R % "n"]
      and _left("import pprint\nlook = df[df.g == 'b']\npprint.pprint(look)\nx = 1\n" + _R % "x") == ["import pprint", "x = 1", _R % "x"])
check("prune_cells (§19.3): names read through globals() are the names whose strings the kept code holds - spelled where they are read, or kept in a table the reader goes through; a string only dropped code holds keeps nothing (so pruning the "
      "pruned changes nothing); a write through globals() stays; eval may read any name and keeps what came before it",
      _left("well = 1\nwell2 = 2\nspare = 3\nw = globals().get('well2', globals().get('well'))\n" + _R % "w") == ["well = 1", "well2 = 2", "w = globals().get('well2', globals().get('well'))", _R % "w"]
      and _left("fat_b = 1\nsor_b = 2\nspare = 3\nstored = {'f': ['fat_b'], 's': ['sor_b']}\ntot = sum(globals().get(nm) for k in stored for nm in stored[k])\n" + _R % "tot")
      == ["fat_b = 1", "sor_b = 2", "stored = {'f': ['fat_b'], 's': ['sor_b']}", "tot = sum(globals().get(nm) for k in stored for nm in stored[k])", _R % "tot"]
      and _left("tired = 1\nif 'tired' in globals():\n    print('have it')\nfresh = 2\nw = globals().get('fresh')\n" + _R % "w") == ["fresh = 2", "w = globals().get('fresh')", _R % "w"]
      and (lambda once: rt.prune_cells(once, [])[0] == once)(rt.prune_cells("\n# --- cell 1 ---\ntired = 1\nif 'tired' in globals():\n    print('have it')\nfresh = 2\nw = globals().get('fresh')\n" + _R % "w" + "\n", [])[0])
      and _left("globals()['made'] = 5\nspare = 1\n" + _R % "made") == ["globals()['made'] = 5", _R % "made"]
      and _left("x = 1\ny = 2\nz = eval('x + 1')\nlate = 4\n" + _R % "z") == ["x = 1", "y = 2", "z = eval('x + 1')", _R % "z"])
check("prune_cells (§19.3): a call reads what the function's body reads when it is called - a change made between the definition and the call stays; numpy's global generator and the standard library's are two states - a seed of one does not "
      "cut the draws of the other",
      _left("d = {}\ndef size(x):\n    d['a'] = x\n    return len(d)\nd['b'] = 1\nn = size(3)\n" + _R % "n") == ["d = {}", "def size(x):", "    d['a'] = x", "    return len(d)", "d['b'] = 1", "n = size(3)", _R % "n"]
      and _left("np.random.seed(0)\nlook = np.random.rand()\nimport random\nrandom.seed(1)\nx = np.random.rand()\n" + _R % "x")
      == ["np.random.seed(0)", "look = np.random.rand()", "import random", "random.seed(1)", "x = np.random.rand()", _R % "x"])
# random small chains (tests/analyst/_random_chains.py), each run as written and as pruned: the same RESULT values - the reading holds for
# what it claims to see; the two cases above are the two it found
import random as _random
from _random_chains import chain as _random_chain, values as _chain_values
_rnd, _np_state, _py_state, _tried, _differ = _random.Random(20261113), np.random.get_state(), _random.getstate(), 0, []
for _ in range(400):
    _rc = _random_chain(_rnd)
    _as_written = _chain_values(_rc)
    if _as_written and _as_written[-1][0] == "error":          # a chain that stops as written is no chain an analysis ends on
        continue
    _tried += 1
    _rp = rt.prune_cells(_rc, [])
    if _rp[3] or _chain_values(_rp[0]) != _as_written or rt.prune_cells(_rp[0], []) != (_rp[0], [], 0, ""):
        _differ.append(_rc)
np.random.set_state(_np_state); _random.setstate(_py_state)
check("prune_cells over 400 random chains (§19.3): each gives the same RESULT values as written and as pruned, and pruning the pruned changes nothing", _tried > 350 and not _differ, (_tried, _differ[:1]))
# the chain as written with the same edits (what a version stores): an edit was found in the promoter's view, where its fragment occurs once; in
# the chain the fragment may occur again in a line that was dropped - held out, that line cannot take the edit
_chain_e = "\n# --- cell 1 ---\nthreshold = 155\nprint('threshold = 155 is the line')\nkept = df[df.v > threshold]\n# --- cell 2 ---\nprint(df.shape)\n# --- cell 3 ---\n" + _R % "len(kept)" + "\n"
_held_e, _lines_e = rt.held_out(_chain_e, [])
_edit_e = [{"cell": 1, "find": "threshold = 155", "replace": "threshold = INPUTS['threshold']"}]
check("held_out / put_back (§19.3): the chain with the pruning's lines held out has the pruned method's cells and nothing of the dropped lines; put back, it is the chain; an edit whose fragment the chain repeats in a dropped line fails on the chain "
      "as it is and lands on the kept line of the chain held out, the dropped line back untouched; a chain with nothing to hold out comes back as it is",
      [n for n, _a, _b in rt.cell_blocks(_held_e)] == [1, 3] and _held_e.split("\n").count(rt.HELD) == 3 and _lines_e == ["print('threshold = 155 is the line')", "# --- cell 2 ---", "print(df.shape)"]
      and rt.put_back(_held_e, _lines_e) == _chain_e and rt.apply_edits(_chain_e, _edit_e)[2] and rt.apply_edits(_held_e, _edit_e)[2] == []
      and rt.put_back(rt.apply_edits(_held_e, _edit_e)[0], _lines_e) == _chain_e.replace("\nthreshold = 155\n", "\nthreshold = INPUTS['threshold']\n")
      and rt.held_out("\n# --- cell 1 ---\nx = 1\n" + _R % "x" + "\n", []) == ("\n# --- cell 1 ---\nx = 1\n" + _R % "x" + "\n", []), (_held_e, _lines_e))
# ---- a run, a statement at a time (docs/ROUTINES_DESIGN.md §22): the script laid out with each statement under a try of its own, as
# plain code; a statement that stops costs what rests on it, not the run; the output read back by statement
import ast as _ast2, contextlib as _ctx, io as _io
_HEAD = "def RESULT(what, value, *a, **k):\n    print('RESULT: %s: %+.2f' % (what, float(value)))\n    return value\n"
_TAIL = "\n# --- the executor's own display options back ---\npass\n"
def _laid(cells, only=None, watch=None):
    return rt.stepwise(rt.with_inputs(rt.join_script(_HEAD, cells, _TAIL), {}), only, watch)
def _exec(text, **names):
    """A script run here, its printed output read back (rt.read_run); an error outside the statements is the test's."""
    buf = _io.StringIO()
    with _ctx.redirect_stdout(buf):
        exec(compile(text, "<string>", "exec"), dict(names))
    return rt.read_run(buf.getvalue())
_SW = """
# --- cell 1 ---
x = [1, 2, 3]
text = '''two
  lines'''
note = f\"\"\"{len(x)} values,
  said\"\"\"
print(note)

# --- cell 2 ---
total = sum(x)
RESULT('total', total)
half = (total /
        zero)
RESULT('half', half)
RESULT('half again', half / 2)

# --- cell 3 ---
RESULT('count', len(x)); RESULT('text', len(text) + len(note))
"""
_sw = _laid(_SW)
_steps_sw = rt.read_steps(_SW)[0]
check("read_steps: the cells' top-level statements in order, each with its cell, its lines in it and its text; statements sharing a line are one; a cell that does not parse leaves nothing read and says which",
      [(f.cell, f.first, f.last) for f in _steps_sw] == [(1, 1, 1), (1, 2, 3), (1, 4, 5), (1, 6, 6), (2, 1, 1), (2, 2, 2), (2, 3, 4), (2, 5, 5), (2, 6, 6), (3, 1, 1)]
      and _steps_sw[6].source == "half = (total /\n        zero)" and _steps_sw[9].source.count("RESULT") == 2 and len(_steps_sw) == 10
      and rt.read_steps("\n# --- cell 1 ---\nx = (\n") == ([], [], "cell 1 could not be parsed ('(' was never closed)"), [(f.cell, f.first, f.last) for f in _steps_sw])
check("steps_key: a mark of the statements a script reads into - the same for the same statements whatever stands around them, another when one changes; none when there are none to read",
      re.fullmatch(r"[0-9a-f]{12}", rt.steps_key(rt.join_script(_HEAD, _SW, _TAIL))) and rt.steps_key(rt.join_script(_HEAD, _SW, _TAIL)) == rt.steps_key(rt.join_script("import os\n", _SW.replace("\n# --- cell 2", "\n# a note\n# --- cell 2"), _TAIL))
      and rt.steps_key(rt.join_script(_HEAD, _SW, _TAIL)) != rt.steps_key(rt.join_script(_HEAD, _SW.replace("total = sum(x)", "total = sum(x) "), _TAIL)) and rt.steps_key("x = 1\n") == "" and rt.steps_key("\n# --- cell 1 ---\nx = (\n") == "")
check("stepwise: the script as plain code - every statement once, under a try of its own, nothing held as text and nothing the local kernel's check refuses; a string that runs over lines keeps its text (its lines are not moved in); a "
      "script whose cells cannot be read comes back as it is; `only` leaves the other statements out",
      _sw.count("if _routine_go(") == 10 and _sw.count("_routine_close()\n") == 1 and _sw.index("_routine_close()\n") > _sw.index("if _routine_go(9):") and _ast2.parse(_sw) is not None and "        half = (total /\n                zero)\n" in _sw and "        text = '''two\n  lines'''\n" in _sw
      and not re.search(r"\b(exec|eval|__import__|sys|shutil)\b", _sw) and PersistentKernel._security_word(_sw) is None
      and rt.stepwise("x = 1\n") == "x = 1\n" and _laid("\n# --- cell 1 ---\nx = (\n") == rt.with_inputs(rt.join_script(_HEAD, "\n# --- cell 1 ---\nx = (\n", _TAIL), {})
      and _laid(_SW, only=[0, 9]).count("if _routine_go(") == 2, _sw[-900:])
_part, _all = _exec(_sw), _exec(_sw, zero=2)
check("a run with one statement that stops: the statements before it ran, the two that rest on it were not run, the one after ran; the report names the statement by its cell and the line in it, with the error; the output is free of the "
      "marks; a whole run reports nothing",
      [(s, k, ln["what"], ln["estimate"]) for s, k, ln in _part["lines"]] == [(5, 0, "total", "+6.00"), (9, 0, "count", "+3.00"), (9, 1, "text", "+27.00")]
      and _part["stopped"] == [{"step": 6, "cell": 2, "line": 4, "error": "NameError: name 'zero' is not defined"}] and _part["skipped"] == [[7, 2, 6], [8, 2, 6]] and _part["stepwise"] and not _part["empty"]
      and _part["stdout"].split("\n")[:2] == ["3 values,", "  said"] and "ROUTINE_" not in _part["stdout"]
      and [ln["what"] for s, k, ln in _all["lines"]] == ["total", "half", "half again", "count", "text"] and _all["stopped"] == [] and _all["skipped"] == [], (_part["lines"], _part["stopped"], _part["skipped"]))
_exp_sw = [{"cell": c, "index": i, "label": w, "estimate": "+1", "low": None, "high": None} for c, i, w in ((2, 0, "total"), (2, 1, "half"), (2, 2, "half again"), (3, 0, "count"), (3, 1, "text"))]
_placed_all = rt.place_lines(_exp_sw, _all)
_exp_at = [dict(e, at=at) for e, at in zip(_exp_sw, _placed_all["at"])]
_placed = rt.place_lines(_exp_at, _part)
_by_pos = rt.place_lines(_exp_sw, _part)
_why_sw = "cell 2 stopped: NameError: name 'zero' is not defined"
check("place_lines: a whole run teaches each expected line its place - the statement that printed it and its order there; with the places known, a run that lost a statement gives every other line, and a blank that names the statement "
      "that stopped for the line it printed and for those resting on it; without them the lines are read by position, sure only up to the first statement that did not run",
      _placed_all["at"] == [[5, 0], [7, 0], [8, 0], [9, 0], [9, 1]] and [r["estimate"] for r in _placed_all["results"]] == ["+6.00", "+3.00", "+1.50", "+3.00", "+27.00"]
      and [r["estimate"] for r in _placed["results"]] == ["+6.00", None, None, "+3.00", "+27.00"] and [r.get("why") for r in _placed["results"]] == [None, _why_sw, _why_sw, None, None] and _placed["at"] is None
      and [r["estimate"] for r in _by_pos["results"]] == ["+6.00", None, None, None, None] and {r.get("why") for r in _by_pos["results"][1:]} == {_why_sw}, (_placed, _by_pos))
_nan = {"lines": [(0, 0, {"what": "a", "estimate": "+nan", "low": None, "high": None})], "stopped": [], "skipped": [], "stepwise": True}
check("place_lines: a line printed without a number is a blank that says so; a frame with no rows leaves every line blank for that reason; a line that was no number in the analysis is never looked for",
      rt.place_lines([dict(_exp_sw[0], at=[0, 0])], _nan)["results"][0]["why"] == rt.NO_NUMBER == "no number on this data" and rt.place_lines([dict(_exp_sw[0], at=[0, 0])], _nan)["results"][0]["estimate"] is None
      and rt.place_lines(_exp_at, {"empty": True})["results"] == [{"estimate": None, "low": None, "high": None, "why": "no data in this window"}] * 5
      and rt.place_lines([dict(_exp_sw[0], estimate=None), _exp_sw[1]], _all)["results"][0]["why"] == "not a number in the analysis")
check("needed_steps: what a tracked line's statement reads, back to where it begins - the count's statement with x, text and note, nothing of cell 2; a check that can stop the run and a cell that draws stay; none when a cell cannot be read",
      rt.needed_steps(_SW, {9}, []) == [0, 1, 2, 9] and rt.needed_steps(_SW, {5}, []) == [0, 4, 5]
      and rt.needed_steps("\n# --- cell 1 ---\na = 1\nb = 2\nassert a > 0\nprint(b)\n# --- cell 2 ---\nc = 3\nprint(c)\n", set(), [2]) == [0, 2, 4, 5] and rt.needed_steps("\n# --- cell 1 ---\nx = (\n", {0}, []) is None)
_lean = _exec(_laid(_SW, only=[0, 1, 2, 9]), zero=2)
check("a run of the needed statements alone prints the tracked lines at the places the whole run taught", [(s, k, ln["estimate"]) for s, k, ln in _lean["lines"]] == [(9, 0, "+3.00"), (9, 1, "+27.00")] and _lean["stopped"] == [])
_HALT = "\n# --- cell 1 ---\na = 1\nassert a > 5, 'too few'\nRESULT('a', a)\n# --- cell 2 ---\nb = 2\nRESULT('b', b)\n"
_halt, _quit = _exec(_laid(_HALT)), _exec(_laid(_HALT.replace("assert a > 5, 'too few'", "raise SystemExit('enough')")))
check("a check of the method's own that stops - an assert, a raise, an exit - stops everything after it: nothing later runs, whatever it reads",
      _halt["stopped"][0]["error"] == "AssertionError: too few" and [j for j, _c, o in _halt["skipped"]] == [2, 3, 4] and _halt["lines"] == []
      and _quit["stopped"][0]["error"] == "SystemExit: enough" and [j for j, _c, o in _quit["skipped"]] == [2, 3, 4], (_halt["stopped"], _halt["skipped"]))
_ALIAS = "\n# --- cell 1 ---\nbox = {}\nsame = box\n# --- cell 2 ---\nbox['n'] = 1 / zero\n# --- cell 3 ---\nRESULT('n', len(same))\nRESULT('one', 1)\n"
_alias = _exec(_laid(_ALIAS))
check("a statement that stops while changing an object spoils the object, not only the name: a line read through a second name for it is not printed either", [ln["what"] for _s, _k, ln in _alias["lines"]] == ["one"] and [j for j, _c, _o in _alias["skipped"]] == [3], (_alias["lines"], _alias["skipped"]))
_FRAME = "\n# --- cell 1 ---\nn = len(df)\nRESULT('rows', n)\n"
_g = pd.DataFrame({"sid": ["a", "a", "b", "c"], "v": [1.0, None, None, 3.0], "w": [1, 2, 3, 4]})
_empty = _exec(_laid(_FRAME, watch={"columns": ["v"], "by": ""}), df=_g.iloc[0:0])
_gaps = _exec(_laid(_FRAME, watch={"columns": ["v", "w", "gone"], "by": "sid"}), df=_g)
check("a frame with no rows, when the statements read the frame: none of them runs, and the run says so; the columns watched are counted - rows empty of rows, and with a column to group by, groups wholly empty of groups",
      _empty["empty"] and _empty["lines"] == [] and _empty["stopped"] == [] and _empty["gaps"] == {"v": [0, 0]} and not _exec(_laid("\n# --- cell 1 ---\nRESULT('one', 1)\n"), df=_g.iloc[0:0])["empty"]
      and _gaps["gaps"] == {"v": [2, 4, 1, 3], "w": [0, 4, 0, 3]} and [ln["estimate"] for _s, _k, ln in _gaps["lines"]] == ["+4.00"], (_empty, _gaps["gaps"]))
check("read_run: output without the marks - a script run as one piece - gives its lines with no statement, and says it was not read by statement",
      rt.read_run("noise\nRESULT: a: +1\nRESULT: b: +2\n") == {"lines": [(None, 0, rt.parse_result_line("RESULT: a: +1")), (None, 1, rt.parse_result_line("RESULT: b: +2"))], "stopped": [], "skipped": [], "empty": False, "gaps": {},
                                                             "stdout": "noise\nRESULT: a: +1\nRESULT: b: +2\n", "stepwise": False})
check("gap_sentences: a watched column emptier than it was in the analysis by ten points or more is said - by the groups of the key column when the run counted them, else by rows; less than that, or no share on record, nothing",
      rt.gap_sentences({"v": [0, 100, 0, 6], "w": [0, 100, 0, 6]}, {"v": [50, 100, 3, 6], "w": [5, 100, 0, 6]}, "sid") == ["v is empty for 3 of 6 sid values"]
      and rt.gap_sentences({"v": [10, 100]}, {"v": [70, 100]}) == ["v is empty in 70% of the rows"] and rt.gap_sentences({"v": [65, 100]}, {"v": [70, 100]}) == []
      and rt.gap_sentences(None, {"v": [70, 100]}) == [] and rt.gap_sentences({}, {"v": [70, 100, 3, 6]}, "sid") == ["v is empty for 3 of 6 sid values"])
# random small chains, each run a statement at a time with one statement made to stop: every line that still came back is the line the whole
# run printed at that place, no other statement stopped, and the run of the needed statements alone prints the tracked lines the same
_rnd2, _np_state, _py_state = _random.Random(20261114), np.random.get_state(), _random.getstate()
_tested = _wrong = _back = _lines_all = _lean_bad = 0
_SLOW = "def RESULT(what, value, *a, **k):\n    print('RESULT: %s: %+.9f' % (what, float(value)))\n    return value\nimport numpy as np, pandas as pd\n"
for _ in range(300):
    _rc = _random_chain(_rnd2)
    _plain = rt.with_inputs(rt.join_script(_SLOW, _rc, _TAIL), {})
    _txt = rt.stepwise(_plain)
    _full = _exec(_txt)
    if _full["stopped"] or not _full["stepwise"]:
        continue
    _n1 = sum(1 for f in rt.read_steps(_rc)[0] if f.cell == 1)
    _j = _rnd2.randrange(_n1, len(rt.read_steps(_rc)[0]))
    _at = _txt.index("if _routine_go(%d):\n    try:\n" % _j) + len("if _routine_go(%d):\n    try:\n" % _j)
    _end = _txt.index("    except (Exception, SystemExit) as _routine_exc:\n", _at)
    _boom = "        raise RuntimeError('made to stop')\n"
    _got = _exec(_txt[:_at] + _boom + _txt[_at:] if _rnd2.random() < 0.5 else _txt[:_end] + _boom + _txt[_end:])
    _tested += 1
    _whole_lines = {(s, k): ln["estimate"] for s, k, ln in _full["lines"]}
    _came = {(s, k): ln["estimate"] for s, k, ln in _got["lines"]}
    _wrong += any(_whole_lines.get(key) != v for key, v in _came.items()) or [s["step"] for s in _got["stopped"]] != [_j]
    _back += len(_came); _lines_all += len(_whole_lines)
    _tracked = [key for key in _whole_lines if _rnd2.random() < 0.5] or list(_whole_lines)[:1]
    _short = _exec(rt.stepwise(_plain, rt.needed_steps(_rc, {s for s, _k in _tracked}, [])))
    _short_lines = {(s, k): ln["estimate"] for s, k, ln in _short["lines"]}
    _lean_bad += bool(_short["stopped"]) or bool(_short["skipped"]) or any(_short_lines.get(key) != _whole_lines[key] for key in _tracked)
np.random.set_state(_np_state); _random.setstate(_py_state)
check("300 random chains run a statement at a time with one statement made to stop: no line that came back differs from the whole run's and no other statement stopped; most lines still come back; the needed statements alone print the "
      "tracked lines as the whole run did",
      _tested > 250 and _wrong == 0 and _back > 0.8 * _lines_all and _lean_bad == 0, (_tested, _wrong, _back, _lines_all, _lean_bad))

# ---- a version stores one text - the chain as written, with the promoter's edits - and Save proves it on the chain's own data: run zero
# (every statement), then the shorter run (only what the tracked lines and the figures rest on), held to run zero's lines and pictures
_pc1 = host.propose(nb4, run4.id, promoter_llm, current_data={"df_id": "df4"})
_runs = {"n": 0}
def _counting_runner(script, timeout):
    _runs["n"] += 1
    return runner(script, timeout)
def _drawing(figs_of):
    """A runner that also returns figures: figs_of(script, the run's number) gives them."""
    def run_(script, timeout):
        _runs["n"] += 1
        out, err, _f, gen = runner(script, timeout)
        return out, err, figs_of(script, _runs["n"]), gen
    return run_
def _made_with(run_, nb_=nb4, pc=None, **kw):
    """create in the foreground on a fresh proposal: (the made record, the stored version, the runs it took)."""
    _runs["n"] = 0
    made_ = host.create(nb_, pc or host.propose(nb4, run4.id, promoter_llm, current_data={"df_id": "df4"}), {"name": "Proved", "purpose": "", "drop_inputs": [], "drop_results": []}, run_, store, **kw)
    return made_, store.load(made_["routine"]["id"])["versions"][0], _runs["n"]
_whole = lambda script: "print(len(kept))" in script          # every statement of run4's chain is in the executed text; the shorter run leaves the print out
check("propose: the print is left out of what the promoter reads - no cell goes, one line does - and the proposal carries the chain as written beside that view; it says the chain's cells and holds no script",
      _pc1["pruned_lines"] == 1 and _pc1["cells"] == 2 and "print(len(kept))" not in _pc1["cells_text"] and "print(len(kept))" in _pc1["cells_chain"]
      and "print(len(kept))" not in prompts[-1][1] and "kept = df[df.v > threshold]" in prompts[-1][1] and not {"script", "pruned", "chain_cells"} & set(_pc1), (_pc1.get("pruned_lines"), sorted(_pc1)))
_made_c, _vc, _n_c = _made_with(_counting_runner, pc=_pc1)
check("create: the version stores one text - the chain as written with the edit, the print included; two runs prove it: run zero, every statement, and the shorter run without the print, which stands - its statements and what there are on "
      "the version, each line's place on the manifest, its time as what a run takes; run zero's output is every statement's; no trials on a file",
      _n_c == 2 and "print(len(kept))" in _vc["script"] and "INPUTS['threshold']" in _vc["script"] and not {"script_written", "condensed", "consolidated"} & set(_vc)
      and _vc["lean"]["steps"] == [0, 1, 3] and _vc["lean"]["line"] == "runs 3 of 4 statements" and _vc["manifest"]["results"][0]["at"] == [3, 0] and _vc["steps"] == rt.steps_key(_vc["script"]) and host.places_hold(_vc)
      and _vc["run_zero"]["status"] == "reproduced" and _vc["run_zero"]["verified"] and _vc["run_zero"]["results"][0]["estimate"] == "+3.00" and _vc["run_zero"]["elapsed"] == _vc["lean"]["elapsed"][1]
      and _vc["tried"] == [] and _made_c["tried"] == [] and host.run_steps(_vc) == [0, 1, 3] and host.run_steps(dict(_vc, script=_vc["script"].replace("print(len(kept))", "pass\npass"))) is None
      and open(os.path.join(store.path(_made_c["routine"]["id"]), "runs", "v1_0", "stdout.txt")).read().split() == ["3", "RESULT:", "rows", "above", "the", "line:", "+3.00", "rows,", "n/a"]
      and host.zero_holds(_vc) == "", (_n_c, _vc.get("lean"), _vc["run_zero"]))
# a method that draws is held to its pictures: the shorter run must draw what run zero drew
_made_f, _vf, _n_f = _made_with(_drawing(lambda script, n: [_fig([1, 2, 3])]))
_made_d, _vd, _n_d = _made_with(_drawing(lambda script, n: [_fig([1, 2, 3] if _whole(script) else [9])]))
_made_j, _vj, _n_j = _made_with(_drawing(lambda script, n: [_fig([n])]))
def _short_stops(script, timeout):
    _runs["n"] += 1
    out, err, _f, gen = runner(script, timeout)
    return (out, err, [], gen) if _whole(script) else (out, 'Traceback (most recent call last):\n  File "<string>", line 3, in <module>\nNameError: name \'gone\' is not defined', [], gen)
_made_w, _vw, _n_w = _made_with(_short_stops)
check("the shorter run of a method that draws: the same pictures and it stands (two runs); another picture, while a second run of every statement draws run zero's again, and every statement runs from then on, the version saying why (three "
      "runs); pictures that differ from one run of every statement to the next hold it to nothing, and it stands (three runs); a shorter run that stops is not taken (two runs)",
      _n_f == 2 and _vf["lean"]["steps"] == [0, 1, 3] and _vf["run_zero"]["figures"] == 1
      and _n_d == 3 and _vd["lean"]["steps"] is None and _vd["lean"]["line"] == "every statement runs: the shorter run did not hold - the figures differ (figure 1 differs)" and host.run_steps(_vd) is None
      and _vd["run_zero"]["status"] == "reproduced" and _vd["lean"]["elapsed"][1] is None
      and _n_j == 3 and _vj["lean"]["steps"] == [0, 1, 3]
      and _n_w == 2 and _vw["lean"]["steps"] is None and _vw["lean"]["line"].startswith("every statement runs: the shorter run did not hold - it stopped (NameError") and _vw["run_zero"]["status"] == "reproduced",
      (_n_f, _n_d, _n_j, _n_w, _vd.get("lean"), _vw.get("lean")))
# a chain whose shorter run would drop something that mattered - a list filled through another name for it, which the reading cannot see
nb5 = Notebook("t5")
run5c = nb5.new_run("How many flags?")
run5c.turns = [Turn(kind="cell", cell_no=1, code="print(df.shape)\nprint(df.dtypes.to_string())", results=[], stdout="(5, 2)"),
               Turn(kind="cell", cell_no=2, code="flags = []\nalso = flags", results=[], stdout=""),
               Turn(kind="cell", cell_no=3, code="for v in df.v:\n    if v > 150:\n        also.append(v)\nprint(len(flags))", results=[], stdout="3"),
               Turn(kind="cell", cell_no=4, code="RESULT('flags', float(len(flags)), None, None, 'rows', 'n/a')", results=[{"text": "flags: +3", "typed": False}], stdout="RESULT: flags: +3")]
run5c.report = "## Three\n\nThree rows are flagged [cell 4]."
run5c.status = "answered"
run5c.data = dict(run4.data)
run5c.replay_script, _ = assemble(run5c.cells(), run5c.report)
nb5.runs[run5c.id] = run5c
_flags_prompts = []
def flags_promoter(s_, u_):
    _flags_prompts.append(u_)
    return '{"name": "Flags", "inputs": [], "edits": [], "kept": []}', {"cost": 0.0}
_flags_events = []
_pc5 = host.propose(nb5, run5c.id, flags_promoter, current_data={"df_id": "df4"}, emit=_flags_events.append)
check("propose: the exploration is left out of what the promoter reads - cells 1 and 3 (cell 3 fills the list through another name for it, which the code does not show), the second name with them; the promoter sees cells 2 and 4; the "
      "checklist says the chain's four cells, and the proposal carries the lines left out and the chain as written",
      _pc5["pruned_lines"] == 7 and _pc5["cells"] == 4 and "# --- cell 3 ---" not in _pc5["cells_text"] and "also" not in _pc5["cells_text"]
      and "# --- cell 3 ---" in _pc5["cells_chain"] and "also.append(v)" in _pc5["cells_chain"] and "# --- cell 3 ---" not in _flags_prompts[0] and "# --- cell 2 ---" in _flags_prompts[0] and "print(df.shape)" not in _flags_prompts[0]
      and [e.get("detail") for e in _flags_events if e.get("type") == "step" and e.get("step") == "chain"] == ["4 cells · 1 result · 0 figures"], (_pc5.get("pruned_lines"), _pc5.get("cells_text")))
_runs["n"] = 0
made5 = host.create(nb5, _pc5, {"name": "Flags"}, _counting_runner, store)
_v5 = store.load(made5["routine"]["id"])["versions"][0]
check("create: the stored text is the chain with all four cells, and run zero reproduces on it; the shorter run leaves the loop out, prints a count of nought and is not taken - every statement runs, the version saying which line differed",
      _runs["n"] == 2 and made5["run_zero"]["status"] == "reproduced" and [ln for ln in _v5["script"].splitlines() if ln.startswith("# --- cell")] == ["# --- cell %d ---" % n for n in (1, 2, 3, 4)]
      and "also.append(v)" in _v5["script"] and _v5["lean"]["steps"] is None and _v5["lean"]["line"] == "every statement runs: the shorter run did not hold - a tracked line differs ([cell 4] flags: +3.00 -> +0.00)"
      and host.run_steps(_v5) is None, (_runs, made5.get("run_zero"), _v5.get("lean")))
# the case that brought the pruning forward (2026-11-08) and the one that brought it down to statements (2026-11-13): a row named by its
# identifier, picked by looking, and only printed about - in a cell of its own, or inside the cell that holds the method; the promoter never
# sees it, so the identifier rule has nothing to refuse; the version keeps it, and the shorter run does not run it
def _literal_chain(thread, cells):
    nb_ = Notebook(thread)
    run_ = nb_.new_run("How many rows are above 155?")
    run_.turns = [Turn(kind="cell", cell_no=i, code=code, results=res, stdout="") for i, (code, res) in enumerate(cells, 1)]
    run_.report = f"## Three\n\nThree rows [cell {len(cells)}]."
    run_.status = "answered"
    run_.data = dict(run4.data)
    run_.replay_script, _ = assemble(run_.cells(), run_.report)
    nb_.runs[run_.id] = run_
    return nb_, run_
_ROWS = [{"text": "rows above the line: +3", "typed": False}]
def literal_promoter(s_, u_):
    if "df.g == 'b'" in u_:
        return '{"name": "Rows", "inputs": [], "edits": [], "kept": [], "unfit": [{"cell": 1, "what": "a group of this data named by looking"}]}', {"cost": 0.0}
    return '{"name": "Rows", "inputs": [], "edits": [], "kept": []}', {"cost": 0.0}
nb5b, run5d = _literal_chain("t5b", [("one = df[df.g == 'b']\nprint(len(one), 'rows in group b, the first looked at')", []),
                                     ("kept = df[df.v > 155]\nRESULT('rows above the line', float(len(kept)), None, None, 'rows', 'n/a')", _ROWS)])
nb5m, run5m = _literal_chain("t5m", [("kept = df[df.v > 155]\n# the first of group b, looked at\none = df[df.g == 'b']\nprint(len(one), 'rows in group b')\nRESULT('rows above the line', float(len(kept)), None, None, 'rows', 'n/a')", _ROWS)])
_pc5d = host.propose(nb5b, run5d.id, literal_promoter, current_data={"df_id": "df4"})
_pc5m = host.propose(nb5m, run5m.id, literal_promoter, current_data={"df_id": "df4"})
made5d = host.create(nb5b, _pc5d, {"name": "Rows"}, runner, store)
made5m = host.create(nb5m, _pc5m, {"name": "Rows"}, runner, store)
_v5d, _v5m = store.load(made5d["routine"]["id"])["versions"][0], store.load(made5m["routine"]["id"])["versions"][0]
check("propose: the literal never reaches the promoter - in a cell of its own, or inside the cell that holds the method (the check and its comment left out) - so a promoter that would refuse on it proposes instead; create: the stored text is "
      "the chain as written, the literal included, and the shorter run leaves its statements out",
      _pc5d["pruned_lines"] == 2 and _pc5d["cells"] == 2 and "df.g == 'b'" not in _pc5d["cells_text"] and _pc5m["pruned_lines"] == 3 and _pc5m["cells"] == 1 and "df.g == 'b'" not in _pc5m["cells_text"]
      and made5d["run_zero"]["status"] == "reproduced" and made5m["run_zero"]["status"] == "reproduced"
      and "# --- cell 1 ---" in _v5d["script"] and "df.g == 'b'" in _v5d["script"] and _v5d["lean"]["steps"] == [2, 3] and _v5d["lean"]["line"] == "runs 2 of 4 statements"
      and "df.g == 'b'" in _v5m["script"] and "looked at" in _v5m["script"] and _v5m["lean"]["steps"] == [0, 3] and _v5m["lean"]["line"] == "runs 2 of 4 statements", (_pc5d.get("pruned_lines"), _pc5m.get("pruned_lines"), _v5d.get("lean"), _v5m.get("lean")))
# an edit found in the promoter's view lands on the same line of the chain as written, although the chain repeats its fragment in a print the view left out
nb5e, run5x = _literal_chain("t5e", [("threshold = 155\nprint('threshold = 155 is the line')\nkept = df[df.v > threshold]", []),
                                     ("RESULT('rows above the line', float(len(kept)), None, None, 'rows', 'n/a')", _ROWS)])
_pc5x = host.propose(nb5e, run5x.id, promoter_llm, current_data={"df_id": "df4"})
made5x = host.create(nb5e, _pc5x, {"name": "Edit"}, runner, store)
_v5x = store.load(made5x["routine"]["id"])["versions"][0]
check("create: the edit that made the input, found in the promoter's view, is on the same line of the stored chain; the print that repeats its fragment is untouched",
      [p_["key"] for p_ in _pc5x["inputs"]] == ["threshold"] and "threshold = INPUTS['threshold']\nprint('threshold = 155 is the line')\nkept = df[df.v > threshold]" in _v5x["script"]
      and made5x["run_zero"]["status"] == "reproduced", (_pc5x.get("inputs"), _v5x.get("script", "")[-400:]))
# a chain with nothing for the reading to rest on - no RESULT line, no figure (its printed output is what a run keeps): the whole chain is the method
nb5c = Notebook("t5c")
run5e = nb5c.new_run("Just the means?")
run5e.turns = [Turn(kind="cell", cell_no=1, code="m = df.groupby('g')['v'].mean()\nprint(m.to_dict())", results=[], stdout="{}"),
               Turn(kind="cell", cell_no=2, code="print('spread', float(m.max() - m.min()))", results=[], stdout="spread 1")]
run5e.report = "## Means\n\nThe means [cell 1], their spread [cell 2]."
run5e.status = "answered"
run5e.data = dict(run4.data)
run5e.replay_script, _ = assemble(run5e.cells(), run5e.report)
nb5c.runs[run5e.id] = run5e
_pc5e = host.propose(nb5c, run5e.id, lambda s_, u_: ('{"name": "Means", "inputs": [], "edits": [], "kept": []}', {"cost": 0.0}), current_data={"df_id": "df4"})
_made_n, _vn, _n_n = _made_with(_counting_runner, nb_=nb5c, pc=_pc5e)
check("a chain without a RESULT line or a figure: the promoter reads all of it, and one run proves it - there is nothing to leave out, so every statement runs",
      _pc5e["pruned_lines"] == 0 and _pc5e["cells"] == 2 and "print(m.to_dict())" in _pc5e["cells_text"] and "# --- cell 2 ---" in _pc5e["cells_text"]
      and _n_n == 1 and _vn["lean"] == {"steps": None, "line": "every statement runs: nothing to leave out", "elapsed": [_vn["run_zero"]["elapsed"], None]}, (_pc5e.get("pruned_lines"), _vn.get("lean")))
# behind the dialog: stored at once as verifying; the proof - run zero and the shorter run, both under verifying - lands on the stored version
_seen_status = []
def _watching_runner(script, timeout):
    if _made_bg.get("routine"):
        _seen_status.append(store.load(_made_bg["routine"]["id"])["versions"][0]["run_zero"]["status"])
    out, err, _f, gen = runner(script, timeout)
    return out, err, [_fig([1, 2])], gen
_made_bg = {}
_pc2 = host.propose(nb4, run4.id, promoter_llm, current_data={"df_id": "df4"})
_made_bg.update(host.create(nb4, _pc2, {"name": "Proved behind", "purpose": "", "drop_inputs": [], "drop_results": []}, _watching_runner, store, background=True))
_v_before = store.load(_made_bg["routine"]["id"])["versions"][0]
_proof_bg = _made_bg["verify"]()
_v_after = store.load(_made_bg["routine"]["id"])["versions"][0]
check("create behind the dialog: stored verifying with its one text and nothing proved yet (a run held, saying so); both runs of the proof run under verifying; then reproduced, the shorter run and the lines' places on the stored "
      "version; the proof handed back carries them",
      _v_before["run_zero"]["status"] == "verifying" and "lean" not in _v_before and "print(len(kept))" in _v_before["script"] and "at" not in _v_before["manifest"]["results"][0]
      and host.zero_holds(_v_before) == "the routine is still being verified on its chain's own data - run it when it has settled" and _seen_status == ["verifying", "verifying"]
      and _v_after["run_zero"]["status"] == "reproduced" and _v_after["run_zero"]["line"].startswith("reproduced") and _v_after["lean"]["steps"] == [0, 1, 3] and _v_after["manifest"]["results"][0]["at"] == [3, 0]
      and _v_after["run_zero"]["figures"] == 1 and _proof_bg["lean"]["steps"] == [0, 1, 3] and _proof_bg["tried"] == [] and _proof_bg["results"][0]["estimate"] == "+3.00",
      (_v_before.get("run_zero"), _seen_status, _v_after.get("lean")))
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
      p4b["cells"] == 1 and "# --- cell 3 ---" in p4b["cells_text"] and "# --- cell 1 ---" not in p4b["cells_text"] and "threshold = 155" not in p4b["cells_text"]
      and [r["cell"] for r in p4b["results"]] == [3] and any("continues 1 earlier chain of the thread that ran on other data (cells 1-2): the method is this chain's own cell 3" in n for n in p4b["notes"]), (p4b["cells"], p4b["notes"], p4b["cells_text"][-400:]))
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
_gone_events = []
p6 = host.propose(nb4, run4.id, promoter_llm, current_data={"df_id": "other"}, emit=_gone_events.append)
made6 = host.create(nb4, p6, {"name": "Unverified", "purpose": "", "drop_inputs": [], "drop_results": []}, None, store)
# the floor under the promoter (§18): identifiers of this data are not inputs - the prompt names the key columns, a reply that makes one an
# input is asked again once with the reason, a second such reply is refused; literals the promoter reports as unfit refuse; what it recomputed is a note
_cols_before = run4.data["columns"]
run4.data["columns"] = _cols_before + [{"name": "session_id", "dtype": "object"}]
_keyed = reply.replace('"inputs": [', '"inputs": [{"key": "rides", "label": "Rides", "type": "choice", "default": ["s1", "s2"], "origin": "typed", "column": "session_id", "multiple": true}, ')
_turns = {"n": 0}
def keyed_then_clean(system, user):
    _turns["n"] += 1
    prompts.append((system, user))
    return (_keyed if _turns["n"] == 1 else reply.replace('"kept": ["nothing else"]', '"kept": ["nothing else"], "recomputed": ["cell 1: the rows above the line are found by the threshold, not listed"]')), {"cost": 0.0}
_key_events = []
p8 = host.propose(nb4, run4.id, keyed_then_clean, current_data={"df_id": "other"}, emit=_key_events.append)
check("propose (§18): the data description names the key column; a reply with a choice over it is asked again once with the reason (the input named), the model step marked as asked again and why, the pane's peek saying identifiers were among the inputs; the clean reply makes the proposal, its recomputed clause a note",
      "Key columns (they identify rows, sessions or groups of this data; other data has its own values): session_id" in prompts[-2][1] and _turns["n"] == 2
      and prompts[-1][1].endswith(rt.PROMOTER_KEYS.format(inputs="rides over session_id"))
      and [(e.get("again"), e.get("detail")) for e in _key_events if e.get("type") == "step" and e.get("step") == "model" and e.get("state") == "running"] == [(False, ""), (True, "identifiers were proposed as inputs")]
      and [e.get("peek") for e in _key_events if e.get("type") == "turn_end"] == ["2 input(s) proposed, 1 edit(s) - identifiers among them (rides over session_id)", "1 input(s) proposed, 1 edit(s)"]
      and [q["key"] for q in p8["inputs"]] == ["threshold"] and any(n_ == "recomputed from the data, not typed: cell 1: the rows above the line are found by the threshold, not listed" for n_ in p8["notes"]), (prompts[-1][1][-300:], p8.get("inputs"), p8.get("notes")))
def keyed_twice(system, user):
    return _keyed, {"cost": 0.0}
try:
    host.propose(nb4, run4.id, keyed_twice, current_data={"df_id": "other"}); _twice = ""
except host.RoutineRefused as exc:
    _twice = str(exc)
def unfit_promoter(system, user):
    return reply.replace('"kept": ["nothing else"]', '"kept": ["nothing else"], "unfit": [{"cell": 2, "what": "two rows named by identifier; no rule in the chain picks them"}]'), {"cost": 0.0}
try:
    host.propose(nb4, run4.id, unfit_promoter, current_data={"df_id": "other"}); _unfit = ""
except host.RoutineRefused as exc:
    _unfit = str(exc)
check("propose (§18): a second reply still picking rows by identifier is refused naming the input; a reply reporting a literal no rule picks is refused naming the cell and what it names - both say to ask the analyst for a rule",
      "picks rows of this data by their identifiers (rides over session_id)" in _twice and "ask the analyst to pick them by a rule, then save again" in _twice
      and "names rows of this data that other data will not have (cell 2: two rows named by identifier; no rule in the chain picks them)" in _unfit and "ask the analyst" in _unfit, (_twice, _unfit))
run4.data["columns"] = _cols_before
check("the checklist with the data gone: no probe (the data step lands done at once), its line says the data is no longer loaded and the routine will be made unverified",
      [(e["step"], e.get("state", "done"), e.get("detail", "")) for e in _gone_events if e.get("type") == "step" and e["step"] == "data"] == [("data", "done", "no longer loaded — the routine will be made unverified")], _gone_events)
check("the analysis's data gone: the proposal says 'gone', run zero is skipped and the routine is created unverified, saying so",
      p6["data_state"] == "gone" and made6["run_zero"]["status"] == "unverified" and not made6["run_zero"]["verified"] and "not verified" in made6["run_zero"]["line"], (p6.get("data_state"), made6.get("run_zero")))
# the promoter's pick (§15): the proposal carries it; create without the page's set takes it, with the set takes the set
def picking_promoter(system, user):
    return reply.replace('"kept": ["nothing else"]', '"kept": ["nothing else"], "compare": [{"line": 1, "name": "rows above"}]'), {"cost": 0.0}
p7 = host.propose(nb4, run4.id, picking_promoter, current_data={"df_id": "other"})
p7["results"].append({"cell": p7["results"][0]["cell"], "index": 1, "label": "a draft the chain superseded", "estimate": "9", "dropped": True})     # as a second ledger line the pick left out
made7 = host.create(nb4, p7, {"name": "Picked"}, None, store)
_m7 = store.load(made7["routine"]["id"])["versions"][0]["manifest"]["results"]
check("propose: the ledger is numbered and the pick lands on the proposal - the line named is kept with its name",
      p7["results"][0].get("name") == "rows above" and not p7["results"][0]["dropped"], p7["results"])
check("create without 'drop_results': the proposal's pick stands (the second line dropped, the first named)",
      [(r["dropped"], r.get("name")) for r in _m7] == [(False, "rows above"), (True, None)], _m7)
made7b = host.create(nb4, p7, {"name": "Picked, all kept", "drop_results": []}, None, store)
_m7b = store.load(made7b["routine"]["id"])["versions"][0]["manifest"]["results"]
check("create with the page's set: it is the whole set left out - an empty one keeps every line, the names staying",
      [(r["dropped"], r.get("name")) for r in _m7b] == [(False, "rows above"), (False, None)], _m7b)
made7c = host.create(nb4, p7, {"name": "Picked, the first dropped", "drop_results": [[p7["results"][0]["cell"], 0]]}, None, store)
check("create with the page's set: a line the person dropped is dropped, one they kept is kept",
      [r["dropped"] for r in store.load(made7c["routine"]["id"])["versions"][0]["manifest"]["results"]] == [True, False])
# the person's instruction (§15.6): a section after the ledger; a reply without "tracked" is asked again once; the lines it gives
# are compared whatever the pick says; a quantity it gives no line for is a note; the line is kept on the routine
_tr_turns = {"n": 0}
def tracked_promoter(system, user):
    _tr_turns["n"] += 1
    prompts.append((system, user))
    if _tr_turns["n"] == 1:
        return reply, {"cost": 0.0}
    return reply.replace('"kept": ["nothing else"]', '"kept": ["nothing else"], "compare": [], "tracked": [{"asked": "the rows above the line", "lines": [{"line": 1, "name": "Rows above"}]}, '
                         '{"asked": "the median", "lines": []}, {"asked": "the rows, again", "lines": [{"line": 1, "name": "x"}]}]'), {"cost": 0.0}
_tr_events = []
p9 = host.propose(nb4, run4.id, tracked_promoter, current_data={"df_id": "other"}, emit=_tr_events.append, instruction="  track the rows above the line,\n the median ")
check("propose (§15.6): the instruction, whitespace folded, is a section after the ledger; a reply without \"tracked\" is asked again once with the reason, the model step saying why; the line the answer gives is kept and named though the pick names nothing; a quantity with no line, and a second quantity on the same line, are notes; the proposal carries the instruction",
      _tr_turns["n"] == 2 and "THE PERSON'S INSTRUCTION (what the runs should track; answer it under \"tracked\", from the ledger alone):\ntrack the rows above the line, the median" in prompts[-2][1]
      and prompts[-1][1].endswith(rt.PROMOTER_TRACKED) and "THE PERSON'S INSTRUCTION" in prompts[-1][1]
      and [(e.get("again"), e.get("detail")) for e in _tr_events if e.get("type") == "step" and e.get("step") == "model" and e.get("state") == "running"] == [(False, ""), (True, "the instruction was not answered")]
      and p9["results"][0].get("name") == "Rows above" and not p9["results"][0]["dropped"] and p9["instruction"] == "track the rows above the line, the median"
      and [n_ for n_ in p9["notes"] if "tracked" in n_] == ["Not computed in this analysis, so it can’t be tracked: the median", "Not computed in this analysis, so it can’t be tracked: the rows, again"]
      and not any("not applied" in n_ for n_ in p9["notes"]), (prompts[-1][1][-200:], p9.get("results"), p9.get("notes")))
_plain = {"n": 0}
def plain_promoter(system, user):
    _plain["n"] += 1
    return reply, {"cost": 0.0}
p9b = host.propose(nb4, run4.id, plain_promoter, current_data={"df_id": "other"}, instruction="track the rows")
check("propose (§15.6): \"tracked\" left out twice - the proposal stands on the pick with a note that the instructions were not applied; without an instruction a reply without \"tracked\" is not asked again (the earlier proposals above ran once)",
      _plain["n"] == 2 and not p9b["results"][0]["dropped"] and any(n_ == "The custom instructions were not applied this time; try Update the list again." for n_ in p9b["notes"]), (_plain, p9b.get("notes")))
def adding_promoter(system, user):
    return reply.replace("threshold = INPUTS['threshold']", "threshold = INPUTS['threshold']\\nRESULT('rows', float(len(df)), None, None, 'rows', 'n/a')"), {"cost": 0.0}
p9c = host.propose(nb4, run4.id, adding_promoter, current_data={"df_id": "other"}, instruction="track the row count too")
check("propose (§15.6): an edit that writes a RESULT call into the method is refused as a whole - the input goes with the reason in a note, the script stays as written",
      "RESULT('rows'" not in p9c["cells_text"] and p9c["inputs"] == [] and any("adds or removes a RESULT call" in n_ for n_ in p9c["notes"]), (p9c.get("inputs"), p9c.get("notes")))
made9 = host.create(nb4, p9, {"name": "Tracked", "instruction": "  track the rows above   the line "}, None, store)
_r9 = store.load(made9["routine"]["id"])
check("create (§15.6): the instruction is kept on the routine, whitespace folded; the summary and the by-origin index carry it",
      _r9["instruction"] == "track the rows above the line" and rt.RoutineStore.summary(_r9)["instruction"] == "track the rows above the line"
      and all(x["instruction"] == "track the rows above the line" for x in store.by_origin()[("t4", run4.id)] if x["id"] == _r9["id"]), _r9.get("instruction"))
host.create(nb4, host.propose(nb4, run4.id, plain_promoter, current_data={"df_id": "other"}), {"name": "Tracked", "change_note": "no key sent"}, None, store, routine_id=_r9["id"])
_kept9 = store.load(_r9["id"])["instruction"]
host.create(nb4, host.propose(nb4, run4.id, plain_promoter, current_data={"df_id": "other"}), {"name": "Tracked", "change_note": "emptied", "instruction": ""}, None, store, routine_id=_r9["id"])
check("create (§15.6): a next version without the key leaves the instruction; one with the box emptied clears it; a new routine without the key has an empty one",
      _kept9 == "track the rows above the line" and store.load(_r9["id"])["instruction"] == "" and store.load(made7["routine"]["id"])["instruction"] == "", _kept9)
# a promoter whose reply cannot be read: one retry, then refusal
calls = {"n": 0}
def mute_promoter(system, user):
    calls["n"] += 1
    return "I cannot do that.", {"cost": 0.0}
_mute_events = []
try:
    host.propose(nb4, run4.id, mute_promoter, current_data={"df_id": "df4"}, emit=_mute_events.append); got = ""
except host.RoutineRefused as exc:
    got = str(exc)
check("propose: an unreadable reply is asked for once more, then refused as 'not understood'; the checklist saw the model step running twice, the second time marked as asked again, and no step after",
      calls["n"] == 2 and "not understood" in got and [(e["step"], e.get("again")) for e in _mute_events if e.get("type") == "step" and e["step"] == "model"] == [("model", False), ("model", True)]
      and not any(e.get("step") == "proposal" for e in _mute_events), (calls, got, _mute_events))
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
check("propose: no inputs is a valid proposal - the method runs as it is", p7["inputs"] == [] and p7["cells_chain"].count("# --- cell") == 2)

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
      out_drop["run"]["status"] in ("ran", "reproduced") and out_drop["run"]["fit"]["missing"] == ["g"] and any(e.get("kind") == "check" and "empty in this data: g" in (e.get("peek") or "") for e in ev_drop)
      and "_ROUTINE_COLUMNS" in rt.with_inputs(host.prepare(host.version_of(store.load(rid4)), {"columns": []}, None, "r")["script"], {}, host.prepare(host.version_of(store.load(rid4)), {"columns": []}, None, "r")["prelude"]),
      (out_drop["run"]["status"], out_drop["run"]["line"], [e.get("peek") for e in ev_drop if e.get("kind") == "check"]))
def broken_runner(script, timeout):
    return "", 'Traceback (most recent call last):\n  File "<string>", line 999, in <module>\nKeyError: \'v\'', [], []
out5 = host.run(store.load(rid4), {}, data_now, broken_runner, store)
check("a script that could not be carried through: the run is kept with status failed and the error's line, every line blank for that reason, the comparison's row missing with it; no statement is named - none was reached",
      out5["run"]["status"] == "failed" and out5["run"]["line"] == "failed: KeyError: 'v'" and out5["run"]["results"] == [{"estimate": None, "low": None, "high": None, "why": "failed: KeyError: 'v'"}]
      and out5["run"]["comparison"]["rows"][0]["mark"] == "missing" and out5["run"]["comparison"]["rows"][0]["why"] == "failed: KeyError: 'v'" and out5["run"]["comparison"]["missing"] == 1 and "unreached" not in out5["run"]["comparison"]
      and out5["run"]["stopped"] == [] and "KeyError" in out5["run"]["error"] and store.load(rid4)["runs"][-1]["status"] == "failed" and store.load(rid4)["runs"][-1]["gaps"] == [], (out5["run"]["line"], out5["run"]["comparison"]))
out6 = host.run(store.load(rid4), {}, data_now, lambda s, t: ("", "TIMEOUT: Code execution exceeded 300 seconds.", [], []), store)
check("a timeout: status timed_out", out6["run"]["status"] == "timed_out" and out6["run"]["line"].startswith("timed out"))
R6 = store.load(rid4)
ref_after_failures = host.reference_run(R6, host.version_of(R6), "previous")
check("the reference skips failed and timed-out runs: the last run that ran", ref_after_failures[0] == 5, ref_after_failures[0])
# the status of a run and its comparison, from the lines laid against the expected ones
_res_all, _res_part = _placed_all["results"], _placed["results"]
check("run_status: every tracked line back - ran, or reproduced when each is the reference run's; some missing - ran, saying how many came and why the first did not; the frame without rows - empty; a script that could not be carried "
      "through - failed, or timed out; a dropped line is not counted; nothing tracked - ran, naming a statement that stopped",
      rt.run_status(_exp_at, _res_all, _all, "", None) == ("ran", "ran: 5 result lines") and rt.run_status(_exp_at, _res_all, _all, "", _res_all) == ("reproduced", "reproduced: every result line as the run before (5 lines)")
      and rt.run_status(_exp_at, _res_part, _part, "", _res_all) == ("ran", "ran: 3 of 5 result lines; 2 not computed (cell 2 stopped: NameError: name 'zero' is not defined)")
      and rt.run_status(_exp_at, [rt._blank(rt.NO_DATA)] * 5, {"empty": True}, "", None) == ("empty", "no data in this window")
      and rt.run_status(_exp_at, [], {}, "HTTPConnectionPool(host='executor'): Max retries exceeded", None) == ("failed", "failed: HTTPConnectionPool(host='executor'): Max retries exceeded")
      and rt.run_status(_exp_at, [], {}, "TIMEOUT: Code execution exceeded 300 seconds.", None)[0] == "timed_out"
      and rt.run_status([dict(e, dropped=(i in (1, 2))) for i, e in enumerate(_exp_at)], _res_part, _part, "", None) == ("ran", "ran: 3 result lines")
      and rt.run_status([], [], _all, "", None) == ("ran", "ran without error") and rt.run_status([], [], _part, "", None) == ("ran", "ran; 1 statement stopped (cell 2: NameError: name 'zero' is not defined)"))
check("check_zero: the chain's lines printed whole and the same - reproduced; a statement that stopped on the chain's own data, or the script - failed, saying which; another number, or another count - differed",
      rt.check_zero([dict(e, estimate=x) for e, x in zip(_exp_sw, ("6", "3", "1.5", "3", "27"))], _all) == ("reproduced", "reproduced: 5 result line(s) identical")
      and rt.check_zero(_exp_sw, _part) == ("failed", "the script stopped with an error (cell 2 stopped on the chain's own data: NameError: name 'zero' is not defined)")
      and rt.check_zero(_exp_sw, {"lines": []}, "Traceback\nKeyError: 'x'") == ("failed", "the script stopped with an error (KeyError: 'x')")
      and rt.check_zero(_exp_sw, _all)[0] == "differed" and rt.check_zero(_exp_sw[:2], _all) == ("differed", "5 result line(s) came back, 2 expected"))
_m4 = store.load(rid4)
_exp4 = host.version_of(_m4)["manifest"]["results"]
_two = _exp4 + [dict(_exp4[0], index=1, label="a second line", estimate="4")]
_cmp_part = rt.compare_runs(_two, [{"estimate": "3", "low": None, "high": None}, rt._blank("cell 2 stopped: KeyError: 'b'")], [{"estimate": "3", "low": None, "high": None}, {"estimate": "4", "low": None, "high": None}])
check("compare_runs: a row carries the manifest's name for the line (empty without one); a line this run has no number for is missing and the row says why; one the reference lacks is missing without a reason; the line counts them",
      rt.compare_runs([dict(_exp4[0], name="the count")], [{"estimate": "3"}], None)["rows"][0]["name"] == "the count" and rt.compare_runs(_exp4, [{"estimate": "3"}], None)["rows"][0]["name"] == ""
      and [(r["mark"], r["why"]) for r in _cmp_part["rows"]] == [("same", ""), ("missing", "cell 2 stopped: KeyError: 'b'")] and _cmp_part["compared"] == 1 and _cmp_part["missing"] == 1
      and _cmp_part["line"] == "0 of 1 changed, 1 missing" and set(_cmp_part) == {"rows", "moved", "within", "changed", "missing", "compared", "line"}
      and rt.compare_runs(_exp4, [{"estimate": "3"}], [rt._blank("x")])["rows"][0] ["mark"] == "missing" and rt.compare_runs(_exp4, [{"estimate": "3"}], [rt._blank("x")])["rows"][0]["why"] == "", _cmp_part)
# ---- a run on data the method cannot be computed whole on (docs/ROUTINES_DESIGN.md §22): one statement stops and costs its own numbers; a
# window with no rows is a blank; a column emptier than in the analysis is said; a script that could not be carried out is tried once more
nb6 = Notebook("t6")
run6 = nb6.new_run("How do the groups compare?")
run6.turns = [Turn(kind="cell", cell_no=1, code="per = df.groupby('g')['v'].mean()\nprint(per.to_dict())", results=[], stdout=""),
              Turn(kind="cell", cell_no=2, code="RESULT('mean of the group means', float(per.mean()), None, None, 'u', 'n/a')\nb = float(per['b'])\nRESULT('group b', b, None, None, 'u', 'n/a')\n"
                                                "RESULT('b over a', b / float(per['a']), None, None, '', 'n/a')", results=[], stdout=""),
              Turn(kind="cell", cell_no=3, code="RESULT('rows', float(len(df)), None, None, 'rows', 'n/a')", results=[], stdout="")]
run6.report = "## Groups\n\nGroup b is higher [cell 2], over five rows [cell 3]."
run6.status = "answered"
run6.data = dict(run4.data)
_printed6 = iter(ln for _s, _k, ln in rt.read_run(runner(assemble(run6.cells(), run6.report)[0], 60)[0])["lines"])
for _turn, _n in ((run6.turns[1], 3), (run6.turns[2], 1)):
    _turn.results = [{"text": "{what}: {estimate}".format(**next(_printed6)), "typed": False} for _ in range(_n)]
nb6.runs[run6.id] = run6
made6 = host.create(nb6, host.propose(nb6, run6.id, as_is_promoter, current_data={"df_id": "df4"}), {"name": "Groups"}, runner, store)
rid6 = made6["routine"]["id"]
_v6 = store.load(rid6)["versions"][0]
_why_b = "cell 2 stopped: KeyError: 'b'"
out_a = host.run(store.load(rid6), {}, dict(data_now, rows=2), runner_on(df[df.g == "a"]), store)
ra = out_a["run"]
check("the routine over two groups made: every line knows its place, the columns the code names are counted on the chain's own data, and the print is left out of a run",
      made6["run_zero"]["status"] == "reproduced" and [e["at"] for e in _v6["manifest"]["results"]] == [[2, 0], [4, 0], [5, 0], [6, 0]] and _v6["manifest"]["data"]["gaps"] == {"v": [0, 5], "g": [0, 5]}
      and _v6["lean"]["steps"] == [0, 2, 3, 4, 5, 6] and host.watch_of(_v6) == {"columns": ["v", "g"], "by": ""}, (made6["run_zero"], _v6.get("lean"), _v6["manifest"]["data"].get("gaps")))
check("a run on data without one of the groups: ran - the two numbers that do not rest on the statement that stopped, a blank with the reason for the two that do; the record names that statement (its cell, the line in it, its code, the "
      "error, the later statements not run for it) and no error of the run; the comparison's rows carry the reason; the routine's line of the run too",
      ra["status"] == "ran" and ra["line"] == "ran: 2 of 4 result lines; 2 not computed (" + _why_b + ")" and [r["estimate"] is not None for r in ra["results"]] == [True, False, False, True]
      and ra["results"][1] == {"estimate": None, "low": None, "high": None, "why": _why_b} and ra["results"][2]["why"] == _why_b
      and ra["stopped"] == [{"cell": 2, "line": 2, "code": "b = float(per['b'])", "error": "KeyError: 'b'", "skipped": 2}] and ra["error"] == "" and ra["against"] == 0
      and [(x["mark"], x["why"]) for x in ra["comparison"]["rows"]] == [("down", ""), ("missing", _why_b), ("missing", _why_b), ("down", "")] and ra["comparison"]["missing"] == 2
      and store.load(rid6)["runs"][-1]["results"][1]["why"] == _why_b and store.load(rid6)["runs"][-1]["status"] == "ran", (ra["status"], ra["line"], ra["stopped"], ra["comparison"]["rows"]))
out_e = host.run(store.load(rid6), {}, dict(data_now, rows=0), runner_on(df.iloc[0:0]), store)
re_ = out_e["run"]
check("a run on a frame with no rows: empty - nothing was run, every line a blank that says there was no data, no statement stopped; it is no reference for a later run",
      re_["status"] == "empty" and re_["line"] == "no data in this window" and re_["results"] == [{"estimate": None, "low": None, "high": None, "why": "no data in this window"}] * 4 and re_["stopped"] == []
      and re_["comparison"]["missing"] == 4 and host.reference_run(store.load(rid6), _v6, "previous")[0] == 1, (re_["status"], re_["line"], re_["results"]))
_holes = df.astype({"v": "float64"}); _holes.loc[[0, 3], "v"] = np.nan
out_g = host.run(store.load(rid6), {}, data_now, runner_on(_holes), store)
check("a run on data where a column the method reads is partly empty: the run says which column and how much, on the record and on the routine's line of the run; the same data as the analysis's says nothing",
      out_g["run"]["gaps"] == ["v is empty in 40% of the rows"] and store.load(rid6)["runs"][-1]["gaps"] == ["v is empty in 40% of the rows"] and out_g["run"]["status"] == "ran" and ra["gaps"] == [], out_g["run"]["gaps"])
_calls = {"n": 0}
def _once_lost(script, timeout):
    _calls["n"] += 1
    return ("", "HTTPConnectionPool(host='executor', port=5000): Max retries exceeded (Connection refused)", [], None) if _calls["n"] == 1 else runner_on(df)(script, timeout)
out_r = host.run(store.load(rid6), {}, data_now, _once_lost, store)
out_l = host.run(store.load(rid6), {}, data_now, lambda s, t: ("", "Connection aborted", [], None), store)
check("a script that could not be carried out - the executor not reached - is tried once more: the run goes through on the second try; lost both times, the run is failed with that line, every number blank for it",
      _calls["n"] == 2 and out_r["run"]["status"] in ("ran", "reproduced") and out_r["run"]["comparison"]["missing"] == 0
      and out_l["run"]["status"] == "failed" and out_l["run"]["line"] == "failed: Connection aborted" and {r["why"] for r in out_l["run"]["results"]} == {"failed: Connection aborted"}
      and not host._transport("Traceback (most recent call last):\n  File \"<string>\", line 3\nKeyError: 'v'") and not host._transport("TIMEOUT: Code execution exceeded 300 seconds.") and not host._transport(""),
      (_calls, out_r["run"]["line"], out_l["run"]["line"]))
def half_runner(script, timeout):
    return "RESULT: mean of the group means: +151\n", 'Traceback (most recent call last):\n  File "<string>", line 999, in <module>\nKeyError: \'v\'', [], []
out_h = host.run(store.load(rid6), {}, data_now, half_runner, store)
check("a script that died after printing a line: failed, and the line printed before stands - read by position, the rest blank with the run's line",
      out_h["run"]["status"] == "failed" and [r["estimate"] for r in out_h["run"]["results"]] == ["+151", None, None, None] and out_h["run"]["results"][1]["why"] == "failed: KeyError: 'v'", out_h["run"]["results"])
# a version made before the lines knew their places reads a run by position, and learns the places at its first whole run
_old6 = store.load(rid6); _old6["id"] = "r6old"; _old6["runs"] = []
for _e in _old6["versions"][0]["manifest"]["results"]:
    _e.pop("at")
_old6["versions"][0]["manifest"]["data"].pop("gaps"); _old6["versions"][0].pop("lean"); _old6["versions"][0].pop("steps")
store.save(_old6)
_o6_first = host.run(store.load("r6old"), {}, dict(data_now, rows=2), runner_on(df[df.g == "a"]), store)
_o6_mid = json.loads(json.dumps(host.version_of(store.load("r6old"))))
out_o2 = host.run(store.load("r6old"), {}, data_now, runner_on(_holes), store)
_o6_last = host.version_of(store.load("r6old"))
out_o3 = host.run(store.load("r6old"), {}, dict(data_now, rows=2), runner_on(df[df.g == "a"]), store)
_ed6 = store.load(rid6); _ed6["id"] = "r6edit"; _ed6["runs"] = []      # a script changed after its shorter run was proven
_v_ed = _ed6["versions"][0]
_v_ed["script"] = _v_ed["script"].replace("b = float(per['b'])", "b = float(per.get('b'))")
_v_ed["lean"]["elapsed"], _v_ed["run_zero"]["elapsed"] = [400.0, 5.0], 5.0
store.save(_ed6)
host.run(store.load("r6edit"), {}, data_now, runner, store)
_v_after = host.version_of(store.load("r6edit"))
check("a version without the places: a run that lost a statement is read by position up to it - the first line, then blanks - and teaches nothing; a whole run teaches every line its place, with the mark of the statements they are among; "
      "from then on a run that loses a statement keeps the lines after it; with no shares on record nothing is said of an emptier column; every statement runs; a script changed since is read by position again, every statement "
      "under what run zero took with every one, and its first whole run puts the shorter run aside",
      [r["estimate"] is not None for r in _o6_first["run"]["results"]] == [True, False, False, False] and "at" not in _o6_mid["manifest"]["results"][0] and "steps" not in _o6_mid
      and [e.get("at") for e in _o6_last["manifest"]["results"]] == [[2, 0], [4, 0], [5, 0], [6, 0]] and _o6_last["steps"] == rt.steps_key(_o6_last["script"]) and _o6_last["lean"] is None
      and [r["estimate"] is not None for r in out_o3["run"]["results"]] == [True, False, False, True] and out_o2["run"]["gaps"] == [] and host.run_steps(_o6_last) is None
      and not host.places_hold(dict(_o6_last, script=_o6_last["script"].replace("b = float(per['b'])", "b = float(per.get('b'))")))
      and _v_ed["lean"]["steps"] and (host.run_steps(_v_ed), host.run_timeout(_v_ed)) == (None, host.time_allowed(400.0)) and host.run_timeout({"run_zero": {"elapsed": 5.0}}) == 300 and host.run_timeout({"run_zero": {}}) == 600
      and _v_after["lean"] is None and host.places_hold(_v_after) and _v_after["run_zero"]["elapsed"] == 400.0,
      ([r["estimate"] for r in _o6_first["run"]["results"]], _o6_last["manifest"]["results"], [r["estimate"] for r in out_o3["run"]["results"]]))
# ---- whose runs (2026-10-30, docs/DATASETS_DESIGN.md §17 step 3): the comparison and the history stay within one subject's runs ----
check("subject_of_record: the load's subject by id and name; {} without one (an upload, a race, a record from before the subject was kept)",
      rt.subject_of_record({"load": {"source": "intervals", "subject": {"source": "intervals", "id": "i0", "name": "The subject"}}}) == {"id": "i0", "name": "The subject"}
      and rt.subject_of_record({"load": {"source": "file"}}) == {} and rt.subject_of_record(None) == {} and rt.subject_of_record({"load": {"subject": "i0"}}) == {})
_sub = lambda sid, name: {"source": "intervals", "id": sid, "name": name}
_r = lambda n, sid, est, status="ran": {"number": n, "version": 1, "status": status, "data": {"subject": ({"id": sid, "name": "x"} if sid else {})}, "results": [{"estimate": est}]}
RS = {"runs": [_r(1, "i0", "+1"), _r(2, "i1", "+2"), _r(3, "i0", "+3"), _r(4, "i1", "+4", "failed")],
      "versions": [{"number": 1, "run_zero": {"verified": True, "results": [{"estimate": "+0"}]}, "manifest": {"data": {"load": {"source": "intervals", "subject": _sub("i0", "x")}}}}]}
V1 = RS["versions"][0]
check("zero_subject / same_subject: run zero's subject from the version's data record; a run matches by id, a run without one matches '' alone",
      host.zero_subject(V1) == "i0" and host.zero_subject({"manifest": {"data": {}}}) == "" and host.same_subject(_r(1, "i0", "+1"), "i0") and not host.same_subject(_r(1, "i0", "+1"), "i1")
      and host.same_subject(_r(1, "", "+1"), "") and not host.same_subject(_r(1, "", "+1"), "i0"))
check("reference_run by subject: 'previous' is the last run that ran on that subject (3 for the first, 2 for the second - the failed one skipped); run 0 stands in for the first subject (its own), not for the second; a third subject has nothing; without a subject, as before",
      host.reference_run(RS, V1, "previous", subject_id="i0")[0] == 3 and host.reference_run(RS, V1, "previous", subject_id="i1")[0] == 2
      and host.reference_run({"runs": [_r(2, "i1", "+2")], "versions": RS["versions"]}, V1, "previous", subject_id="i0") == (0, [{"estimate": "+0"}])
      and host.reference_run({"runs": [_r(1, "i0", "+1")], "versions": RS["versions"]}, V1, "previous", subject_id="i1") == (None, None)
      and host.reference_run(RS, V1, "previous", subject_id="i2") == (None, None) and host.reference_run(RS, V1, "previous")[0] == 3,
      [host.reference_run(RS, V1, "previous", subject_id=s_)[0] for s_ in ("i0", "i1", "i2", None)])
V0 = {"number": 1, "run_zero": {"verified": True, "results": [{"estimate": "+0"}]}, "manifest": {"data": {}}}
check("reference_run: a run zero that names no subject (from before the subject was kept) is nobody's - nothing for a subject, run 0 for the subject-less (an upload's runs); 'zero' asked outright is run 0 for its own subject and nothing for another",
      host.reference_run({"runs": [], "versions": [V0]}, V0, "previous", subject_id="i1") == (None, None) and host.reference_run({"runs": [], "versions": [V0]}, V0, "previous", subject_id="") == (0, [{"estimate": "+0"}])
      and host.reference_run(RS, V1, "zero", subject_id="i0") == (0, [{"estimate": "+0"}]) and host.reference_run(RS, V1, "zero", subject_id="i1") == (None, None) and host.reference_run(RS, V1, "zero") == (0, [{"estimate": "+0"}]))
check("run_numbers by subject: run 0 when it is theirs, then their runs (the failed one too - it opens); a subject with no runs has none; a run zero naming none is the subject-less group's; without a subject, every run",
      host.run_numbers(RS, subject_id="i0") == [0, 1, 3] and host.run_numbers(RS, subject_id="i1") == [2, 4] and host.run_numbers(RS, subject_id="i2") == [] and host.run_numbers({"runs": [], "versions": [V0], "current_version": 1}, subject_id="") == [0]
      and host.run_numbers({"runs": [], "versions": [V0], "current_version": 1}, subject_id="i0") == [] and host.run_numbers(RS) == [0, 1, 2, 3, 4])
check("window_text: the summary's window first, else the load's dates, else the date range, else the race or the file; reference_data: run 0's is the version's own data (light), a run's its summary's, none without a reference",
      host.window_text({"window": ["2026-01-01", "2026-02-01"], "date_range": "2025-01-01 to 2025-06-01"}) == "2026-01-01 → 2026-02-01" and host.window_text({"load": {"start_date": "2026-01-01", "end_date": "2026-02-01"}}) == "2026-01-01 → 2026-02-01"
      and host.window_text({"date_range": "2026-01-01 to 2026-02-01"}) == "2026-01-01 → 2026-02-01" and host.window_text({"extra": {"race_title": "Spring classic"}}) == "Spring classic" and host.window_text({"name": "a.csv"}) == "a.csv" and host.window_text(None) == ""
      and host.reference_data(RS, V1, 0)["subject"] == {"id": "i0", "name": "x"} and host.reference_data(RS, V1, 2)["subject"] == {"id": "i1", "name": "x"} and host.reference_data(RS, V1, None) is None and host.reference_data(RS, V1, 99) is None)
check("light_data carries the window the run asked for (a cut run's, not the cached load's), from the load's dates else the date range; none without either",
      host.light_data({"df_id": "d", "load": {"source": "intervals", "start_date": "2026-02-01", "end_date": "2026-05-31", "cached_from": ["2026-01-13", "2026-06-11"]}, "date_range": "2026-01-13 to 2026-06-11"})["window"] == ["2026-02-01", "2026-05-31"]
      and host.light_data({"df_id": "d", "date_range": "2026-01-13 to 2026-06-11"})["window"] == ["2026-01-13", "2026-06-11"] and host.light_data({"df_id": "d", "name": "a.csv"})["window"] is None)
check("light_data and load_plan carry the subject: the summary of a run on a subject's load names them; the plan of a routine made on one names them for the run dialog; neither for an upload",
      host.light_data({"df_id": "d", "load": {"source": "intervals", "subject": _sub("i1", "The other subject")}})["subject"] == {"id": "i1", "name": "The other subject"} and host.light_data({"df_id": "d", "load": {"source": "file"}})["subject"] == {}
      and host.load_plan({"current_version": 1, "versions": [{"number": 1, "manifest": {"data": {"source": "intervals", "load": {"source": "intervals", "start_date": "2026-08-12", "end_date": "2026-10-10", "subject": _sub("i0", "The subject")}}}}]})["subject"] == {"id": "i0", "name": "The subject"}
      and host.load_plan({"current_version": 1, "versions": [{"number": 1, "manifest": {"data": {"source": "csv", "name": "a.csv"}}}]})["subject"] == {})
# a run through the host on a subject's data: the summary names them; against the run before on them, else run zero when it is theirs
# (or names none), else nothing - the line then says it is the first run on this subject, not of the version
_R7 = store.load(rid4); _R7["id"] = "r7sub"; host.version_of(_R7)["manifest"]["data"]["load"] = {"source": "intervals", "subject": _sub("i0", "The subject")}; store.save(_R7)
_on = lambda sid, name: dict(data_now, load={"source": "intervals", "subject": _sub(sid, name)})
_o7a = host.run(store.load("r7sub"), {}, _on("i1", "The other subject"), runner_on(df), store)
_o7b = host.run(store.load("r7sub"), {}, _on("i0", "The subject"), runner_on(df), store)
_ev7 = []
_o7c = host.run(store.load("r7sub"), {}, _on("i1", "The other subject"), runner_on(df), store, emit=_ev7.append)
check("host.run by subject: the other subject's first run has no reference (run zero is the first subject's) and says it is the first run on this subject; the first subject's run is against run 0 (theirs; the other's run skipped); the other's second run is against their first",
      _o7a["run"]["against"] is None and _o7a["run"]["comparison"]["line"] == "nothing to compare with: the first run on this subject" and _o7a["summary"]["data"]["subject"] == {"id": "i1", "name": "The other subject"}
      and _o7b["run"]["against"] == 0 and _o7c["run"]["against"] == _o7a["run"]["number"] and _o7c["run"]["status"] in ("ran", "reproduced"), (_o7a["run"]["against"], _o7a["run"]["comparison"]["line"], _o7b["run"]["against"], _o7c["run"]["against"], _o7c["run"]["line"]))
_cmp7 = next((e for e in _ev7 if e.get("kind") == "compare"), {})
check("the run's answer carries whose it is, the numbers the arrows step through (that subject's alone) and the reference run's data for the Comparison tab; the COMPARE row names the reference run with its date (no window on an upload's record)",
      _o7c["subject"] == {"id": "i1", "name": "The other subject"} and _o7c["numbers"] == [_o7a["run"]["number"], _o7c["run"]["number"]] and _o7c["against_data"]["subject"] == {"id": "i1", "name": "The other subject"}
      and _o7a["against_data"] is None and _o7b["against_data"]["subject"] == {"id": "i0", "name": "The subject"} and _cmp7.get("query", "").startswith(f"with run {_o7a['run']['number']} (") and _cmp7.get("peek") == _o7c["run"]["comparison"]["line"], (_o7c.get("numbers"), _cmp7))
# a routine stored in an earlier shape is brought to today's when it is loaded, once, its runs' records with it (RoutineStore._upgrade): one
# script per version, every run's lines laid against the version's expected lines, the statuses and the words of today
_tmp_s = tempfile.mkdtemp(); _st2 = rt.RoutineStore(_tmp_s)
_two_lines = {"data": {}, "results": [{"cell": 1, "index": 0, "label": "a", "estimate": "+0"}, {"cell": 2, "index": 0, "label": "b", "estimate": "+0"}]}
_fail_line = "failed at cell 2: ZeroDivisionError: division by zero"
_st2.save({"id": "rold", "name": "n", "current_version": 2,
           "versions": [dict(V0, script="# shortened", script_written="# as written", condensed={"status": "condensed"}, run_zero={"verified": True, "status": "condensing", "results": [{"estimate": "+0"}]}, manifest=_two_lines),
                        {"number": 2, "script": "# rewritten", "script_fallback": "# before the rewrite", "consolidated": {"status": "consolidated", "provisional": True}, "run_zero": {"verified": True, "status": "reproduced"}, "manifest": _two_lines}],
           "runs": [{"number": 1, "version": 1, "status": "differed", "line": "1 of 2 result lines did not come back", "results": [{"estimate": "+1"}], "data": {"name": "", "source": "intervals"}, "comparison": {"moved": 0, "missing": 1, "unreached": 0}},
                    {"number": 2, "version": 1, "status": "failed", "line": _fail_line, "results": [{"estimate": "+1"}], "data": {"name": "", "source": "intervals"}, "comparison": {"moved": 0, "missing": 0, "unreached": 1}},
                    {"number": 3, "version": 2, "status": "ran", "line": "ran: 2 result lines", "results": [{"estimate": "+1"}, {"estimate": "+nan"}], "data": {"subject": {"id": "i9"}}, "comparison": {}}]})
_st2.save_run("rold", "v1_1", {"number": 1, "version": 1, "status": "differed", "line": "1 of 2 result lines did not come back", "results": [{"estimate": "+1"}], "data": {"load": {"source": "intervals", "subject": _sub("i0", "The subject")}}, "failed_cell": None})
_st2.save_run("rold", "v1_2", {"number": 2, "version": 1, "status": "failed", "line": _fail_line, "results": [{"estimate": "+1"}], "data": {}, "error": "Traceback (most recent call last):\n  File \"<string>\", line 9, in <module>\nZeroDivisionError: division by zero",
                               "failed_cell": {"number": 2, "code": "x = 1\nb = 1 / 0", "statement": "b = 1 / 0"}, "consolidation": None,
                               "comparison": {"rows": [{"mark": "same", "now": {"estimate": "+1"}}, {"mark": "unreached", "now": None}], "missing": 0, "unreached": 1}})
with open(_st2.file("rold"), encoding="utf-8") as _fh:
    _raw = json.load(_fh)
_raw.pop("shape", None)
with open(_st2.file("rold"), "w", encoding="utf-8") as _fh:
    json.dump(_raw, _fh)
_got = _st2.load("rold")
with open(_st2.file("rold"), encoding="utf-8") as _fh:
    _saved = json.load(_fh)
_rec2, _rec1 = _st2.load_run("rold", "v1_2"), _st2.load_run("rold", "v1_1")
_twice = {"status": "ran", "line": "ran", "results": [{"estimate": "+1"}, {"estimate": "+2"}]}      # a run of a method with a line that was no number in the analysis
_exp_twice = [{"estimate": "+0"}, {"estimate": None}, {"estimate": "+0"}]
rt._as_now(_twice, _exp_twice)
_once = json.loads(json.dumps(_twice))
rt._as_now(_twice, _exp_twice)
check("an earlier routine as it is loaded: each version keeps one script - the one that ran, or, for a rewrite never confirmed, the one it replaced - and nothing of the passes; a verdict cut short while a pass ran is the verdict; the file "
      "carries today's shape after, and a second load changes nothing - nor does a run taken through the upgrade twice (an upgrade cut short is taken up again)",
      _got["shape"] == rt.SHAPE == _saved["shape"] and [v["script"] for v in _got["versions"]] == ["# shortened", "# before the rewrite"]
      and not {"script_written", "condensed", "consolidated", "script_fallback"} & (set(_got["versions"][0]) | set(_got["versions"][1])) and _got["versions"][0]["run_zero"]["status"] == "reproduced"
      and _st2.load("rold") == _got and [r["estimate"] for r in _once["results"]] == ["+1", None, "+2"] and _twice == _once, ([sorted(v) for v in _got["versions"]], _once, _twice))
check("an earlier routine's runs: one that printed fewer lines `ran`; every run's lines laid against the expected ones - a blank where none came back, with the run's line when it failed, and a line without a number a blank that says so; "
      "the lines a failed run did not reach are missing; each summary names whose data it ran on, from the run's record ({} when the record names none, or is gone)",
      [x["status"] for x in _got["runs"]] == ["ran", "failed", "ran"] and [[r["estimate"] for r in x["results"]] for x in _got["runs"]] == [["+1", None], ["+1", None], ["+1", None]]
      and [x["results"][1]["why"] for x in _got["runs"]] == ["not printed on this data", _fail_line, "no number on this data"] and all(x["gaps"] == [] for x in _got["runs"])
      and _got["runs"][0]["comparison"] == {"moved": 0, "missing": 1} and _got["runs"][1]["comparison"] == {"moved": 0, "missing": 1}
      and [x["data"].get("subject") for x in _got["runs"]] == [{"id": "i0", "name": "The subject"}, {}, {"id": "i9"}], _got["runs"])
check("an earlier run's own record: the cell it failed at is the statement that stopped, with its code and the error's line; the lines it did not reach are missing, with the run's line as the reason; nothing of the rewrite's check",
      _rec2["stopped"] == [{"cell": 2, "line": None, "code": "b = 1 / 0", "error": "ZeroDivisionError: division by zero", "skipped": 0}] and not {"failed_cell", "consolidation"} & set(_rec2) and _rec2["status"] == "failed"
      and _rec2["comparison"] == {"rows": [{"mark": "same", "now": {"estimate": "+1"}, "why": ""}, {"mark": "missing", "now": None, "why": _fail_line}], "missing": 1} and _rec2["results"][1]["why"] == _fail_line
      and _rec1["status"] == "ran" and _rec1["stopped"] == [] and store.load(rid6)["shape"] == rt.SHAPE, (_rec2, _rec1))
# ---- the interval (2026-11-06, docs/ROUTINES_DESIGN.md §14): a run's calendar unit on the record, the reference the one before it, the fill ----
_w = lambda n, sid, kind, win, status="ran", est="+1": {"number": n, "version": 1, "status": status, "interval": kind, "data": {"subject": ({"id": sid, "name": "x"} if sid else {}), "window": win}, "results": [{"estimate": est}]}
RI = {"versions": RS["versions"], "runs": [_w(1, "i0", None, ["2026-01-01", "2026-06-30"], est="+5"), _w(2, "i0", "week", ["2026-10-12", "2026-10-18"], est="+6"), _w(3, "i0", "week", ["2026-10-19", "2026-10-25"], "failed"),
                                          _w(4, "i1", "week", ["2026-10-19", "2026-10-25"], est="+9"), _w(5, "i0", "month", ["2026-09-01", "2026-09-30"], est="+7")]}
check("reference_run by interval: a week is compared with the latest earlier week on the same subject by its window's end (run 2: the failed week skipped, the other subject's and the month ignored); the first week has nothing - not run 0, not a custom run; a custom run's 'previous' skips the set intervals (run 1); a number asked outright is that run",
      host.reference_run(RI, V1, "previous", subject_id="i0", interval="week", window=("2026-10-26", "2026-11-01")) == (2, [{"estimate": "+6"}])
      and host.reference_run(RI, V1, "previous", subject_id="i0", interval="week", window=("2026-10-05", "2026-10-11")) == (None, None) and host.reference_run(RI, V1, "previous", subject_id="i1", interval="week", window=("2026-10-26", "2026-11-01")) == (4, [{"estimate": "+9"}])
      and host.reference_run(RI, V1, "previous", subject_id="i0") == (1, [{"estimate": "+5"}]) and host.reference_run(RI, V1, "previous", subject_id="i1") == (None, None)
      and host.reference_run(RI, V1, "previous", subject_id="i0", interval="month", window=("2026-10-01", "2026-10-31")) == (5, [{"estimate": "+7"}]) and host.reference_run(RI, V1, 2, subject_id="i0", interval="week", window=("2026-10-26", "2026-11-01")) == (2, [{"estimate": "+6"}]),
      [host.reference_run(RI, V1, "previous", subject_id="i0", interval=k, window=("2026-10-26", "2026-11-01"))[0] for k in ("week", "month", None)])
# a run through the host with an interval: the record and the summary carry it, the window is the load's dates, the reference the week before
_R8 = store.load(rid4); _R8["id"] = "r8int"; host.version_of(_R8)["manifest"]["data"]["load"] = {"source": "intervals", "subject": _sub("i0", "The subject")}; store.save(_R8)
_wk = lambda a, b_: dict(data_now, load={"source": "intervals", "subject": _sub("i0", "The subject"), "start_date": a, "end_date": b_, "cached": True, "cached_from": ["2026-10-05", "2026-11-01"]})
_o8a = host.run(store.load("r8int"), {}, _wk("2026-10-19", "2026-10-25"), runner_on(df), store, interval="week")
_o8b = host.run(store.load("r8int"), {}, _wk("2026-10-26", "2026-11-01"), runner_on(df), store, interval="week")
_o8c = host.run(store.load("r8int"), {}, dict(data_now, load={"source": "intervals", "subject": _sub("i0", "The subject")}), runner_on(df), store)
_o8d = host.run(store.load("r8int"), {}, dict(data_now, load={"source": "intervals", "subject": _sub("i0", "The subject")}), runner_on(df), store, interval="week")
_o8e = host.run(store.load("r8int"), {}, _wk("2026-10-12", "2026-10-18"), runner_on(df), store, interval="fortnight")
check("host.run with an interval: the first week on the subject has no reference and the line says no earlier week is on record; the next week is against it; both records and summaries carry interval='week' and the window; a custom run after them is against run 0 (theirs), never a week; an interval without a window, or one not of the four, is custom",
      _o8a["run"]["interval"] == "week" and _o8a["summary"]["interval"] == "week" and _o8a["run"]["against"] is None and _o8a["run"]["comparison"]["line"] == "nothing to compare with: no earlier week on record for this subject"
      and _o8a["summary"]["data"]["window"] == ["2026-10-19", "2026-10-25"] and _o8b["run"]["against"] == _o8a["run"]["number"] and _o8b["run"]["status"] in ("ran", "reproduced")
      and _o8c["run"]["against"] == 0 and _o8c["run"]["interval"] is None and _o8d["run"]["interval"] is None and _o8e["run"]["interval"] is None and _o8e["summary"]["interval"] is None,
      (_o8a["run"].get("interval"), _o8a["run"]["against"], _o8a["run"]["comparison"]["line"], _o8b["run"]["against"], _o8c["run"]["against"], _o8d["run"].get("interval")))
# the fill: a thread over the instance's run_routine, oldest first, every window cut from the span, quiet; refusals counted; stopped when asked or when the frame changed
class _Inst:
    df_id = "span-1"
    def __init__(self): self.calls = []
    def run_routine(self, rid, values, aux=None, load=None, interval=None, quiet=False, compare_with="previous"):
        self.calls.append((load["start_date"], load["end_date"], load.get("cached_from"), load.get("cached"), interval, quiet, values, aux))
        time.sleep(0.03)
        if load["start_date"] == "2026-10-12":
            raise host.RoutineRefused("'x' is not in column c")
        return {"run": {"status": "failed" if load["start_date"] == "2026-10-19" else "ran", "line": "ran: 1 line"}}
_inst = _Inst()
_fill = host.Fill(_inst, "r1", "week", [["2026-10-05", "2026-10-11"], ["2026-10-12", "2026-10-18"], ["2026-10-19", "2026-10-25"], ["2026-10-26", "2026-11-01"]], {"a": 1}, ["f.csv"], {"source": "intervals", "start_date": "2026-10-05", "end_date": "2026-11-01", "subject": _sub("i0", "x")})
_st0 = _fill.status(); _fill.start(); time.sleep(0.05); _st1 = _fill.status(); _fill._thread.join(5); _st2 = _fill.status()
check("Fill: not started - nothing done; running - the window under way and the count; ended - 4 of 4 done, 2 failed (a failed run and a refused window), the last line; every window ran oldest first over the span's load with its own dates, cached_from the span (the load not called cached: the span may have been downloaded), quiet, with the values and the files",
      _st0 == dict(_st0, running=False, done=0, total=4, current=None) and _st1["running"] and _st1["current"] in (["2026-10-05", "2026-10-11"], ["2026-10-12", "2026-10-18"], ["2026-10-19", "2026-10-25"])
      and not _st2["running"] and _st2["done"] == 4 and _st2["failed"] == 2 and not _st2["stopped"] and _st2["left"] is None and _st2["interval"] == "week" and _st2["routine_id"] == "r1"
      and [c[0] for c in _inst.calls] == ["2026-10-05", "2026-10-12", "2026-10-19", "2026-10-26"] and all(c[2] == ["2026-10-05", "2026-11-01"] and c[3] is None and c[4] == "week" and c[5] is True and c[6] == {"a": 1} and c[7] == ["f.csv"] for c in _inst.calls), (_st1, _st2, _inst.calls))
_bad = []
for _args in (("fortnight", [["2026-10-05", "2026-10-11"]]), ("week", []), ("week", [["2026-10-12", "2026-10-11"]]), ("week", [["2026-10-5", "2026-10-11"]]), ("week", [["2026-10-05"]])):
    try:
        host.Fill(_inst, "r1", *_args)
        _bad.append("made")
    except host.RoutineRefused as exc:
        _bad.append(str(exc).split(" must be")[0])
check("Fill refuses an interval not of the four and windows that are not dated [start, end] pairs in order", _bad == ["the interval", "the windows", "the windows", "the windows", "the windows"], _bad)
class _Inst2(_Inst):
    def run_routine(self, *a, **k):
        self.df_id = "other"
        return super().run_routine(*a, **k)
_f2 = host.Fill(_Inst2(), "r1", "day", [["2026-11-01", "2026-11-01"], ["2026-11-02", "2026-11-02"], ["2026-11-03", "2026-11-03"]]).start(); _f2._thread.join(5)
class _Inst3(_Inst):
    def run_routine(self, *a, **k):
        time.sleep(0.2)
        return super().run_routine(*a, **k)
_f3 = host.Fill(_Inst3(), "r1", "day", [["2026-11-01", "2026-11-01"], ["2026-11-02", "2026-11-02"], ["2026-11-03", "2026-11-03"]]).start(); time.sleep(0.05); _f3.stop(); _f3._thread.join(5)
_f4 = host.Fill(_Inst(), "r1", "week", [["2026-10-05", "2026-10-11"]], load={"cached_from": ["2026-09-01", "2026-11-01"]}).start(); _f4._thread.join(5)
check("Fill stops when the Data tab's frame is no longer the span (after the window under way, with the reason) and when asked (the window under way finishes); the span is the load's cached_from when the page loaded a wider frame",
      _f2.status()["stopped"] and _f2.status()["done"] == 1 and _f2.status()["error"] == "the data on the Data tab changed" and _f3.status()["stopped"] and _f3.status()["done"] == 1 and _f3.status()["error"] == ""
      and _f4.instance.calls[0][2] == ["2026-09-01", "2026-11-01"], (_f2.status(), _f3.status()))
check("Fill's status names its routine (the Summary greys Run on another routine with the name); empty when none was given",
      host.Fill(_Inst(), "r1", "day", [["2026-11-01", "2026-11-01"]], routine_name="Start hours").status()["routine_name"] == "Start hours" and _f4.status()["routine_name"] == "")
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
check("a run with the summary absent: an empty table with the recorded columns stood in, the statement that needs its rows stopped on it (nothing to count) and cost its own line, the record names it and lists the absent file",
      r5c["status"] == "ran" and r5c["line"].startswith("ran: 1 of 2 result lines; 1 not computed (cell 1 stopped: ValueError") and r5c["stopped"][0]["cell"] == 1 and r5c["aux_absent"] == ["summary"]
      and any("summary absent" in (e.get("peek") or "") for e in ev5c if e.get("kind") == "check")
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
check("the probe failed and the summary is absent: the CHECK row says the files could not be prepared, the stand-in path is still what the executed text names (never a cache path), the prelude wrote it, and the statement that stopped did so on the empty table - not on a missing file",
      any("could not be prepared" in (e.get("peek") or "") for e in ev5d if e.get("kind") == "check") and r5d["bindings"] and r5d["bindings"][0][2] == "placeholder" and r5d["bindings"][0][1] == rt.mirror_path(os.path.join(aux_dir, "routines", rid5, "v1_3"), aux_old)
      and os.path.exists(rt.mirror_path(os.path.join(aux_dir, "routines", rid5, "v1_3"), aux_old)) and r5d["status"] == "ran" and [s["error"].split(":")[0] for s in r5d["stopped"]] == ["ValueError"],
      (r5d.get("bindings"), r5d.get("status"), r5d.get("stopped")))
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
# the rider profile and the custom zone times (2026-10-16, docs/RIDER_PROFILE_DESIGN.md): two kinds of their own - the profile taken
# whole by a cut run (the load's settings, not rows of the window), the zone times cut by the activity's day like the summary; a
# routine that wants the profile is no hit without it beside the cached load; the zone times file, written only when the account
# defines custom zone sets, is taken when there and is no miss when not
cmr1 = rt.cache_match({"source": "intervals", "aux_kinds": ["summary", "rider"], "metrics": []}, insp_c, "2026-07-12", "2026-10-10")
insp_c["auxiliary_datasets"].append({"filename": "rider_profile_20260712_to_20261010.csv", "path": "datasets/u/rider_profile_20260712_to_20261010.csv", "size_mb": 0.004})
cmr2 = rt.cache_match({"source": "intervals", "aux_kinds": ["summary", "rider"], "metrics": []}, insp_c, "2026-07-12", "2026-10-10")
insp_c["auxiliary_datasets"].append({"filename": "custom_zone_times_20260712_to_20261010.csv", "path": "datasets/u/custom_zone_times_20260712_to_20261010.csv", "size_mb": 0.02})
cmr3 = rt.cache_match({"source": "intervals", "aux_kinds": ["summary", "rider"], "metrics": []}, insp_c, "2026-07-12", "2026-10-10")
check("the rider profile and the zone times: their kinds, prefixes and cut rules (whole; by the activity's day); no hit without the profile beside the cached load, a hit with it and no zone times file (none defined), the zone times taken when there",
      rt.aux_kind("datasets/u/k/rider_profile_20260712_to_20261010.csv") == "rider" and rt.aux_kind("custom_zone_times_20260712_to_20261010.csv") == "zones" and rt.kind_prefix("rider") == "rider_profile_" and rt.kind_prefix("zones") == "custom_zone_times_"
      and rt.cut_rule("rider_profile_x.csv") == ("whole", "") and rt.cut_rule("custom_zone_times_x.csv") == ("date", "start_date_local")
      and not cmr1["hit"] and "without rider" in cmr1["line"] and cmr2["hit"] and cmr2["files"] == ["datasets/u/activity_summary_20260712_to_20261010.csv", "datasets/u/rider_profile_20260712_to_20261010.csv"]
      and cmr3["hit"] and cmr3["files"][-1] == "datasets/u/custom_zone_times_20260712_to_20261010.csv" and "with summary, rider, zones" in cmr3["line"], (cmr1, cmr2, cmr3))
# whose file (2026-10-29, one subject at a time on the Data tab): a loader's file - every kind the Intervals loader writes, by its name -
# that is not under the subject's views/ is another subject's, whatever path an earlier load gave it; uploads and race files are nobody's
check("loader_file and other_subjects_file: the Intervals kinds are LOAD_KINDS['intervals'] and what those bring; a loader's file under another subject's views/, under a key's mark folder or at a subject's folder itself is another subject's; the subject's own, an upload and a race file are not; backslashes read as slashes; no folder, nobody's",
      set(rt.INTERVALS_KINDS) == set(rt.LOAD_KINDS["intervals"]) | set(rt.brings("intervals", rt.LOAD_KINDS["intervals"])) and rt.loader_file("x/context_codes_20260101_to_20260201.csv") and not rt.loader_file("x/athlete_profiles_race_9.csv") and not rt.loader_file("x/wellness.csv")
      and rt.other_subjects_file("datasets/u/intervals/i0/views/wellness_data_20260101_to_20260201.csv", "intervals/i1") and rt.other_subjects_file("datasets/u/abcdef012345/views/planned_workouts_20260101_to_20260201.csv", "intervals/i1")
      and rt.other_subjects_file("datasets/u/intervals/i1/rider_profile_20260101_to_20260201.csv", "intervals/i1") and not rt.other_subjects_file("datasets/u/intervals/i1/views/rider_profile_20260101_to_20260201.csv", "intervals/i1")
      and not rt.other_subjects_file("datasets/u/upload.csv", "intervals/i1") and not rt.other_subjects_file("datasets/u/athlete_profiles_race_9.csv", "intervals/i1") and not rt.other_subjects_file("C:\\d\\u\\intervals\\i1\\views\\custom_zone_times_20260101_to_20260201.csv", "intervals/i1")
      and not rt.other_subjects_file("datasets/u/intervals/i0/views/wellness_data_20260101_to_20260201.csv", ""))
check("load_plan keeps the rider profile among a run's kinds and never the zone times (brought, not asked)",
      host.load_plan({"versions": [{"number": 1, "manifest": {"data": {"source": "intervals", "load": {"source": "intervals", "aux_kinds": ["summary", "rider", "zones"], "start_date": "2026-07-12", "end_date": "2026-10-10"}}}}]})["aux_kinds"] == ["summary", "rider"])
# the report's head (2026-10-17): one line saying what data a report stands on, from the run's data record - the source and its
# window or event, the activity count, the auxiliary files by their names (the codes ride under the context); a file by its
# name and rows; nothing but files when there is no frame
check("data_line: Intervals with its window, count and files by name; Endura by its event; SweatStack with its sports; a file with its rows and an attached file; a bare frame; no dataset",
      rt.data_line({"load": {"source": "intervals", "start_date": "2025-10-18", "end_date": "2026-10-16"}, "extra": {"activities_count": 307},
                    "aux": ["d/activity_summary_x.csv", "d/context_notes_x.csv", "d/context_codes_x.csv", "d/planned_workouts_x.csv", "d/rider_profile_x.csv", "d/custom_zone_times_x.csv"]})
      == "Intervals.icu · 2025-10-18 to 2026-10-16 · 307 activities · activity summary, context, planned workouts, rider profile, custom zone times"
      and rt.data_line({"load": {"source": "endura", "race_title": "Spring classic"}, "aux": ["athlete_profiles_race_1.csv", "race_turns_race_1.csv"]}) == "Endura · Spring classic · profiles, turns"
      and rt.data_line({"load": {"source": "sweatstack", "start_date": "2026-01-01", "end_date": "2026-02-01", "sports": ["cycling"]}}) == "SweatStack · 2026-01-01 to 2026-02-01 · cycling"
      and rt.data_line({"source": "file", "name": "field_trial.csv", "rows": 12000, "aux": ["laps.csv"]}) == "field_trial.csv · 12,000 rows · laps.csv"
      and rt.data_line({"source": "frame", "rows": 200, "df_id": "d1"}) == "a dataset of 200 rows" and rt.data_line({"source": "none", "aux": ["a.csv"]}) == "a.csv" and rt.data_line({"source": "none"}) == "no dataset"
      and rt.data_line({"source": "intervals", "date_range": "2026-01-01 to 2026-01-31", "df_id": "x"}) == "Intervals.icu · 2026-01-01 to 2026-01-31" and rt.data_line(None) == "no dataset"
      and all(rt.KIND_NAMES.get(k) for src in rt.LOAD_KINDS for k in rt.LOAD_KINDS[src]), rt.data_line({"source": "frame", "rows": 200, "df_id": "d1"}))
# room for more auxiliaries (2026-10-16, patch 0181): one registry of what a load can be asked for (LOAD_KINDS) and what it brings
# beside without being asked (LOAD_BRINGS); load_plan, cache_match and the app's auxiliary limit read it, so a new kind is added
# once - the sixth file of a load had tripped a limit written as a literal
check("the loaders' registry: every kind a load can be asked for, and every kind it brings, has a file prefix; the windowed source's kinds all have a cut rule; the most files one load brings is eight (six kinds, the codes beside the context, the zone times beside the profile); brings() says what rides beside the kinds asked",
      all(rt.kind_prefix(k) for src in rt.LOAD_KINDS for k in rt.LOAD_KINDS[src]) and all(rt.kind_prefix(b) for src in rt.LOAD_BRINGS for v in rt.LOAD_BRINGS[src].values() for b in v)
      and all(k in rt.CUT_RULES for k in rt.LOAD_KINDS["intervals"] + tuple(rt.brings("intervals", rt.LOAD_KINDS["intervals"])))
      and rt.LOADER_FILES_MAX == 8 and rt.brings("intervals", ["summary", "context"]) == ["codes"] and rt.brings("intervals", ["summary"]) == [] and rt.brings("endura", ["profile"]) == [] and rt.brings("x", ["context"]) == []
      and rt.brings("intervals", ["rider", "context"]) == ["zones", "codes"] and rt.BRINGS_IF_DEFINED == ("zones",)
      and set(rt.LOAD_KINDS["intervals"]) == {"summary", "wellness", "intervals", "context", "plan", "rider"} and set(rt.LOAD_KINDS["endura"]) == {"profile", "turns", "climbs", "waymarkers"},
      (rt.LOADER_FILES_MAX, rt.LOAD_KINDS, rt.LOAD_BRINGS))
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
# whose data a key loads (2026-10-29, docs/DATASETS_DESIGN.md): the executor's records (`subjects`, one per subject with the marks
# of the keys that loaded it) say; a frame then counts by the subject's id, whatever key loaded it, and lives in the subject's folder
k3 = rt.key_fingerprint("key-three")
insp_s = {"cached_dataframes": [{"df_id": "a", "shape": [1000, 17], "source": "intervals", "date_range": "2026-01-13 to 2026-06-11", "metrics": [], "key_mark": k1, "subject": {"source": "intervals", "id": "i0", "name": "One"}, "folder": "intervals/i0"},
                                {"df_id": "b", "shape": [900, 17], "source": "intervals", "date_range": "2026-01-13 to 2026-06-11", "metrics": [], "key_mark": k3, "subject": {"source": "intervals", "id": "i1", "name": "Two"}, "folder": "intervals/i1"},
                                {"df_id": "c", "shape": [300, 17], "source": "intervals", "date_range": "2026-07-01 to 2026-07-31", "metrics": [], "key_mark": k1}],
          "auxiliary_datasets": [{"path": "datasets/u/intervals/i0/activity_summary_20260113_to_20260611.csv", "key_mark": "", "folder": "intervals/i0"}, {"path": "datasets/u/intervals/i1/activity_summary_20260113_to_20260611.csv", "key_mark": "", "folder": "intervals/i1"},
                                 {"path": f"datasets/u/{k1}/activity_summary_20260701_to_20260731.csv", "key_mark": k1}],
          "subjects": [{"source": "intervals", "id": "i0", "name": "One", "folder": "intervals/i0", "marks": [k1, k2]}, {"source": "intervals", "id": "i1", "name": "Two", "folder": "intervals/i1", "marks": [k3]}]}
cs1 = rt.cache_match(plan_k, insp_s, "2026-01-13", "2026-06-11", key=k2)        # the rotated key: the records say it is i0's
cs2 = rt.cache_match(plan_k, insp_s, "2026-01-13", "2026-06-11", key=k3)        # the other subject's key
cs3 = rt.cache_match(plan_k, insp_s, "2026-01-13", "2026-06-11", key=rt.key_fingerprint("key-four"))     # a key that has not loaded yet
cs4 = rt.cache_match(plan_k, insp_s, "2026-07-01", "2026-07-31", key=k2)        # an older frame marked with the first key, no subject on it
cs5 = rt.cache_match(plan_k, insp_s, "2026-07-01", "2026-07-31", key=k3)
cs6 = rt.cache_match(plan_k, insp_s, "2026-01-13", "2026-06-11", key=k2, subject="i1")                   # the subject named outright outranks the key
check("cache_match by subject: a rotated key is served its subject's window loaded under the first key, the file in the subject's folder; the other subject's key gets its own frame; a key that never loaded gets neither, said as another key's; "
      "a frame from before subjects were recorded still counts by its mark alone, so the rotated key is told it is another key's; the subject named outright decides",
      cs1["hit"] and cs1["df_id"] == "a" and cs1["files"] == ["datasets/u/intervals/i0/activity_summary_20260113_to_20260611.csv"] and cs2["hit"] and cs2["df_id"] == "b" and cs2["files"][0].startswith("datasets/u/intervals/i1/")
      and not cs3["hit"] and "loaded under another key" in cs3["line"] and not cs4["hit"] and "loaded under another key" in cs4["line"] and not cs5["hit"] and "loaded under another key" in cs5["line"]
      and cs6["hit"] and cs6["df_id"] == "b" and rt.subject_of_key(insp_s, k2) == "i0" and rt.subject_of_key(insp_s, "") == "" and rt.subject_of_key(insp_k, k1) == "",
      (cs1, cs2, cs3["line"], cs4["line"], cs5["line"], cs6))
cs7 = rt.cache_match(plan_k, {**insp_s, "cached_dataframes": insp_s["cached_dataframes"][:1]}, "2026-01-13", "2026-06-11", key=k3)    # only i0's frame cached, i1's key in use
check("a window the cache holds for another subject only is said so - loaded for another subject, to be downloaded", not cs7["hit"] and "loaded for another subject" in cs7["line"], cs7)
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
p9["cells_text"], p9["applied"], _f9 = rt.apply_edits(p9["cells_original"], [{"cell": 2, "find": "RESULT('sessions in the frame', float(n)", "replace": "RESULT(f\"sessions in the frame {INPUTS['span'][0]} to {INPUTS['span'][1]}\", float(n)"}])
assert not _f9, _f9
made9 = host.create(nb9, p9, {"name": "Cut", "purpose": "", "drop_inputs": [], "drop_results": []}, runner_on(df9), store)
rid9 = made9["routine"]["id"]
check("the routine on three loader files and a frame made (run zero reproduced)", made9["run_zero"]["status"] == "reproduced", made9["run_zero"])
# Save tries the method on smaller pieces of the analysis's own data (docs/ROUTINES_DESIGN.md §22): the latest day, week and month in its
# window that hold rows, each cut as a fill cuts a unit from its span; nothing is recorded as a run, and the trials' folder goes
_v9 = store.load(rid9)["versions"][0]
check("the trials of the routine on three loader files: its frame holds rows on one day, so the pieces are that day, its week and its month; on each, every tracked line came back; no run is on record and the trials' folder is gone",
      [(t["interval"], t["window"], t["status"], t["came"], t["of"]) for t in _v9["tried"]]
      == [("day", ["2026-08-01", "2026-08-01"], "ran", 4, 4), ("week", ["2026-07-27", "2026-08-02"], "ran", 4, 4), ("month", ["2026-08-01", "2026-08-31"], "ran", 4, 4)]
      and made9["tried"] == _v9["tried"] and _v9["tried"][0]["line"] == "ran: 4 result lines" and store.load(rid9)["runs"] == []
      and os.path.isdir(os.path.join("routines", rid9)) and not os.path.exists(os.path.join("routines", rid9, "v1_0_trial")), _v9.get("tried"))
_tw = {"source": "intervals", "load": {"start_date": "2026-09-01", "end_date": "2026-10-26"}}
check("trial_windows: the latest complete day, week (Monday to Sunday) and month inside the window - with the days that hold rows known, the latest of each that holds any (a week that begins before the window is none); a piece as long as the window is no trial; nothing without a "
      "window, from a source whose runs have no intervals, or when no day holds rows",
      host.trial_windows(_tw) == [("day", "2026-10-25", "2026-10-25"), ("week", "2026-10-19", "2026-10-25"), ("month", "2026-09-01", "2026-09-30")]
      and host.trial_windows(_tw, ["2026-09-03", "2026-10-24"]) == [("day", "2026-10-24", "2026-10-24"), ("week", "2026-10-19", "2026-10-25"), ("month", "2026-09-01", "2026-09-30")]
      and host.trial_windows(_tw, ["2026-09-03"]) == [("day", "2026-09-03", "2026-09-03"), ("month", "2026-09-01", "2026-09-30")]
      and host.trial_windows({"source": "intervals", "load": {"start_date": "2026-10-20", "end_date": "2026-10-26"}}) == [("day", "2026-10-25", "2026-10-25")]
      and host.trial_windows({"source": "intervals", "load": {"start_date": "2025-10-27", "end_date": "2026-10-31"}})[2] == ("month", "2026-10-01", "2026-10-31")
      and host.trial_windows(_tw, []) == [] and host.trial_windows(dict(_tw, source="csv")) == [] and host.trial_windows({"source": "intervals"}) == [], host.trial_windows(_tw, ["2026-09-03"]))
_days9 = host.read_marked(runner_on(df9)(host.days_script("datetime"), 60)[0], host.DAYS_MARK)
_gone = os.path.join(tempfile.mkdtemp(), "trial"); os.makedirs(os.path.join(_gone, "a", "b")); open(os.path.join(_gone, "a", "b", "f.csv"), "w").write("x\n1\n")
_rm = runner_on(df)(rt.remove_script(_gone), 60)
check("the scripts beside the trials pass the local kernel's check and do what they say: the days a frame holds rows on, by its date column; a folder removed with what is in it, and nothing said when it is not there",
      _days9 == {"days": ["2026-08-01"]} and _rm[1] == "" and not os.path.exists(_gone) and runner_on(df)(rt.remove_script(_gone), 60)[1] == "", (_days9, _rm))
check("try_method: nothing without a date column to cut by; a piece the method cannot be tried on says so and the others go on",
      host.try_method({"manifest": {"data": dict(_tw, columns=[{"name": "v", "dtype": "int64"}])}}, runner_on(df), 60, "x") == [] and host.date_column_of({"columns": [{"name": "t", "dtype": "datetime64[ns]"}]}) == "t"
      and host.date_column_of({"span": {"column": "day"}, "columns": [{"name": "t", "dtype": "datetime64[ns]"}]}) == "day" and host.date_column_of(None) == "")
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
      r9["status"] == "ran" and got9.get("rows in the summary") == "+2.00" and got9.get("rows in the wellness file") == "+1.00" and got9.get("rows in the intervals file") == "+2.00"
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
# the same cached load, a window no row falls in (a fill's week without a session): the cut leaves nothing, nothing is run, the run is a blank on record
_e9 = store.load(rid9); _e9["id"] = "r9empty"; _e9["runs"] = []
store.save(_e9)
out9e = host.run(store.load("r9empty"), {}, dict(now9, load=dict(now9["load"], start_date="2026-03-01", end_date="2026-03-31")), runner_on(df9c), store,
                 run_dir=os.path.join(aux_dir, "routines", "r9empty", "v1_1"), interval="month")
r9e = out9e["run"]
check("a window of the cached load that holds no rows: nothing is run and the run is kept as one with no data - every line blank for that reason, nothing stopped, no error, the interval and the window on it; it is no reference for a later run",
      r9e["status"] == "empty" and r9e["line"] == "no data in this window" and {x["why"] for x in r9e["results"]} == {"no data in this window"} and all(x["estimate"] is None for x in r9e["results"]) and r9e["stopped"] == []
      and not r9e["error"] and r9e["interval"] == "month" and out9e["summary"]["data"]["window"] == ["2026-03-01", "2026-03-31"] and r9e["data"]["rows"] == 0
      and host.reference_run(store.load("r9empty"), host.version_of(store.load("r9empty")), interval="month", window=("2026-04-01", "2026-04-30"), subject_id="") == (None, None),
      (r9e["status"], r9e["line"], (r9e.get("error") or "")[-300:], r9e["data"].get("rows"), out9e["summary"]["data"]))
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
      r10["status"] == "ran" and got10.get("passages") == "+3.00" and got10.get("codes on them") == "+4.00"
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
check("with no codes file in this load: CTX.codes() in the run is the empty stand-in at the recorded path, the passages still the window's", out10b["run"]["status"] == "ran" and got10b.get("passages") == "+3.00" and got10b.get("codes on them") == "+0.00" and out10b["run"]["aux_absent"] == ["codes"], (got10b, out10b["run"].get("aux_absent"), (out10b["run"].get("error") or "")[-200:]))
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
check("the run with one of the chosen values absent goes ahead and the CHECK row carries the note", out8n["run"]["status"] in ("ran", "reproduced") and any(e.get("kind") == "check" and "keeps the other value" in (e.get("peek") or "") for e in ev8), [e.get("peek") for e in ev8 if e.get("kind") == "check"])
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
check("...and the run goes ahead with the words as given", out8d["run"]["status"] in ("ran", "reproduced") and out8d["run"].get("inputs", {}).get("kw") == ["VT1", "hill"], (out8d["run"]["status"], out8d["run"].get("inputs")))
v8b["manifest"]["parameters"].pop(); store.save(R8b)
ok7 = host.precheck(store.load(rid4), data_now, runner_on(df), values={"grp": "a"})
check("a choice value in the data passes", ok7["ok"], ok7["line"])
view0 = host.run_view(store.load(rid4), store, 0)
view2 = host.run_view(store.load(rid4), store, 2)
check("run_view: run zero from the version's record with its files; run 2 from its record with the comparison, the output and the numbers to step through",
      view0["run"]["number"] == 0 and view0["run"]["zero"] and view0["run"]["results"][0]["estimate"] == "+3.00" and "RESULT:" in view0["stdout"]
      and view2["run"]["number"] == 2 and view2["run"]["comparison"]["rows"][0]["mark"] == "down" and "RESULT: rows above the line: +2.00" in view2["stdout"] and view2["numbers"][:3] == [0, 1, 2] and "manifest_results" not in view2, (view0["run"].get("results"), view2.get("numbers")))
check("run_view says whose the run is (none for an upload's) and carries the reference run's data: run 2's reference is run 1's summary, run zero has none",
      view2["subject"] == {} and view0["subject"] == {} and view2["against_data"] is not None and view2["against_data"].get("name") == "small.csv" and view0["against_data"] is None, (view2.get("subject"), view2.get("against_data")))
try:
    host.run_view(store.load(rid4), store, 99); nope = ""
except host.RoutineRefused as exc:
    nope = str(exc)
check("run_view of a run that does not exist is refused", "no run 99" in nope)
shutil.rmtree(tmp, ignore_errors=True)

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
