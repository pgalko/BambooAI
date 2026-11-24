"""The analyst package: the tree, the turn format, the loop over a real kernel,
the guards, assembly and replay. Run: python3 tests/analyst/test_analyst.py"""
import os, sys, json, tempfile, re
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.dirname(os.path.abspath(__file__)), ROOT, os.path.join(ROOT, "delve")]
import pandas as pd, numpy as np
from analyst import Session, Budget, Notebook, NotebookStore, parse_turn, replay, report
from analyst.notebook import Turn
from analyst.session import contract, READ_ROW, CONTRACT, CONTRACT_DOCUMENTS
from kernel import PersistentKernel

passed, failed = [], []
def check(name, cond, detail=""):
    (passed if cond else failed).append(name); print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {detail}"))

# ---- the turn format ----
_, note, act = parse_turn("some thinking\n###NOTE###\n- Question as understood: q\n- Plan: p\n###ACTION###\nCELL\n```python\nprint(1)\n```")
check("parse: note and CELL", note.startswith("- Question") and act.verb == "cell" and act.arg == "print(1)")
check("parse: SHOW / NAMES / ASK / REPORT",
      parse_turn("###NOTE###\nn\n###ACTION###\nSHOW 3")[2].arg == "3"
      and parse_turn("###NOTE###\nn\n###ACTION###\nNAMES")[2].verb == "names"
      and parse_turn("###NOTE###\nn\n###ACTION###\nASK Do you mean training pace?")[2].arg.startswith("Do you mean")
      and parse_turn("###NOTE###\nn\n###ACTION###\nREPORT\nThe answer.\n\nMore.")[2].arg == "The answer.\n\nMore.")
check("parse: a reply without an action is 'invalid', not a crash", parse_turn("just prose")[2].verb == "invalid")
recall_reply = parse_turn("###NOTE###\nn\n###ACTION###\nRECALL cluster bootstrap")[2]
check("parse: RECALL is no action (the old memory is retired, 2.8): the reply is told so, and the contract does not offer it",
      recall_reply.verb == "invalid" and "unknown action" in recall_reply.arg and "RECALL" not in CONTRACT, recall_reply)
th, nt, ac = parse_turn("###THINKING###\nThe last output shows 9 athletes overlap.\n###NOTE###\n- Question as understood: q\n###ACTION###\nNAMES")
check("parse: the THINKING slot is captured as thinking, not as the note", th == "The last output shows 9 athletes overlap." and nt.startswith("- Question") and ac.verb == "names")
check("parse: an empty reply is reported as 'empty reply', distinct from a malformed one", parse_turn("")[2].arg == "empty reply" and parse_turn("prose")[2].arg == "no ###ACTION### block")

# ---- the tree ----
nb = Notebook("t1"); r1 = nb.new_run("q1"); r2 = nb.new_run("q2", parent=r1.id); r3 = nb.new_run("q3 (branch from q1)", parent=r1.id)
check("tree: paths follow parents, a branch does not see its sibling",
      [r.id for r in nb.path(r2.id)] == [r1.id, r2.id] and [r.id for r in nb.path(r3.id)] == [r1.id, r3.id])
d = Notebook.from_dict(json.loads(json.dumps(nb.to_dict())))
check("tree: round-trips through JSON", set(d.runs) == set(nb.runs) and d.runs[r3.id].parent == r1.id)

# ---- the computation path (2026-10-12): the part of the path that ran on the run's data ----
nbd = Notebook("td")
ra = nbd.new_run("first"); ra.data = {"df_id": "A", "name": "summer.csv", "date_range": "2026-07-13 to 2026-10-11", "rows": 92, "columns": [{"name": "t", "dtype": "int64"}, {"name": "v", "dtype": "float64"}]}
ra.turns = [Turn(kind="cell", cell_no=1, code="a = 1"), Turn(kind="cell", cell_no=2, code="b = a + 1")]
rb = nbd.new_run("second", parent=ra.id); rb.data = {"df_id": "A"}
rb.turns = [Turn(kind="cell", cell_no=3, code="c = b + 1")]
rc = nbd.new_run("third, after the data changed", parent=rb.id); rc.data = {"df_id": "B", "name": "winter.csv", "rows": 94}
rc.turns = [Turn(kind="cell", cell_no=4, code="d = 1")]
rd = nbd.new_run("fourth, same data as the third", parent=rc.id); rd.data = {"df_id": "B"}
rd.turns = [Turn(kind="cell", cell_no=5, code="e = d + 1")]
for r in (ra, rb, rc, rd): r.status = "answered"; r.report = "## r\n\nDone."
check("computed_cells: on the same data the whole path (cells 1-3 for the second run); after a change of data only the cells since it (4 for the third, 4-5 for the fourth); path_cells stays the whole record",
      [c.cell_no for c in nbd.computed_cells(rb.id)] == [1, 2, 3] and [c.cell_no for c in nbd.computed_cells(rc.id)] == [4] and [c.cell_no for c in nbd.computed_cells(rd.id)] == [4, 5]
      and [c.cell_no for c in nbd.path_cells(rd.id)] == [1, 2, 3, 4, 5] and nbd.next_cell_no(rd.id) == 6)
check("computed_cells for a follow-up about to start (the data loaded now given): on the frame of the tip, the tip's cells; on another frame, nothing to rehydrate",
      [c.cell_no for c in nbd.computed_cells(rd.id, data={"df_id": "B"})] == [4, 5] and nbd.computed_cells(rd.id, data={"df_id": "C"}) == [] and [c.cell_no for c in nbd.computed_cells(rb.id, data={"df_id": "A"})] == [1, 2, 3])
# the same data under a new frame id (2026-10-12): a favourite continued in a new session, the file uploaded again - the same
# name, rows and columns - is the same data; a window of other rows, or another file of the same shape, is not
again = {"df_id": "A-again", "name": "summer.csv", "date_range": "2026-07-13 to 2026-10-11", "rows": 92, "columns": [{"name": "t", "dtype": "int64"}, {"name": "v", "dtype": "float64"}]}
from analyst.notebook import same_data, data_signature
check("same_data: the same frame id; or the same name, rows, columns and period under another id; not another file of the same shape, not other rows, not a record without rows or columns",
      same_data({"df_id": "A"}, {"df_id": "A"}) and same_data(ra.data, again) and not same_data(ra.data, dict(again, name="winter.csv")) and not same_data(ra.data, dict(again, rows=93))
      and not same_data(ra.data, {"df_id": "A-light", "name": "summer.csv"}) and not same_data({}, ra.data) and data_signature({"df_id": "x"}) == "")
check("computed_cells for a follow-up on the same file uploaded again: the earlier chain's cells are rehydrated (1-2, before the change to B stands)",
      [c.cell_no for c in nbd.computed_cells(ra.id, data=again)] == [1, 2] and [c.cell_no for c in nbd.computed_cells(rd.id, data=again)] == [])
check("earlier_on_other_data: the runs before the last change (the first two for the fourth); none on an unchanged path",
      [r.id for r in nbd.earlier_on_other_data(rd.id)] == [ra.id, rb.id] and nbd.earlier_on_other_data(rb.id) == [])
nbo = Notebook("to")                                     # an earlier run without a data record (before 2026-10-10) counts as on the same data
ro0 = nbo.new_run("old root, no record"); ro0.turns = [Turn(kind="cell", cell_no=1, code="x = 1")]
ro1 = nbo.new_run("newer, on A", parent=ro0.id); ro1.data = {"df_id": "A"}; ro1.turns = [Turn(kind="cell", cell_no=2, code="y = x + 1")]
re_ = nbd.new_run("asked with no data loaded", parent=ra.id)     # the run itself without a record: nothing loaded now, so a chain that had data is on other data
re_.turns = [Turn(kind="cell", cell_no=3, code="x = 1")]
check("an earlier run without a data record counts as on the same data; a run asked with no data loaded stands on nothing of the earlier chain's",
      [c.cell_no for c in nbo.computed_cells(ro1.id)] == [1, 2] and [c.cell_no for c in nbd.computed_cells(re_.id)] == [3] and [r.id for r in nbd.earlier_on_other_data(re_.id)] == [ra.id])
ancd = nbd.render_ancestry(rd.id)
check("the ledger marks the chains before the change as on other data - the file, the period, the rows; the frame's id when the record has nothing else; their cells named as not in the kernel - and keeps the later one plain",
      "[run 1] Q: first\n" in ancd and "On other data (summer.csv, 2026-07-13 to 2026-10-11, 92 rows): its numbers are that data's; its cells 1-2 are not in the kernel (SHOW n re-opens one from the record)" in ancd
      and "On other data (frame A): its numbers are that data's; its cell 3 is not in the kernel" in ancd and ancd.count("On other data") == 2 and "[run 3] Q: third" in ancd and "On other data" not in ancd.split("[run 3]")[1], ancd)
check("the cells view after the change shows the computed cells only (4 as older, 5 whole), never the earlier chains' cells",
      "cell 4" in nbd.render_cells(rd.id) and "cell 5" in nbd.render_cells(rd.id) and "cell 1" not in nbd.render_cells(rd.id) and "--- cell 1" not in nbd.render_cells(rd.id, everything=True), nbd.render_cells(rd.id))
check("other_data_line: one cell says 'its cell n is'; no data on record says so", "its cell 4 is not in the kernel" in nbd.other_data_line(rc) and nbd.other_data_line(ro0).startswith("On other data (not on record): its numbers are that data's"))
# whose data (2026-10-29): the Data tab holds one athlete at a time and a thread may go from one to the next, so the subject's id on
# the load is part of the data's identity, and the ledger says a chain ran on another subject's data - never a name
from analyst.notebook import subject_id_of
one = {"df_id": "S1", "name": "window.csv", "date_range": "2026-01-01 to 2026-03-01", "rows": 60, "columns": [{"name": "t", "dtype": "int64"}],
       "load": {"source": "intervals", "subject": {"source": "intervals", "id": "i0", "name": "The subject"}}}
two = dict(one, df_id="S2", load={"source": "intervals", "subject": {"source": "intervals", "id": "i1", "name": "The other subject"}})
check("subject_id_of reads the load's subject id ('' without one, or with a record that is no record); the same window under two subjects is not the same data; the same subject's window again is; records without a subject still match by the rest",
      subject_id_of(one) == "i0" and subject_id_of({"load": {"subject": "x"}}) == "" and subject_id_of(None) == "" and not same_data(one, two) and same_data(one, dict(one, df_id="S1-again"))
      and data_signature(dict(one, load=None)) == data_signature(dict(two, load=None)) and data_signature(one) != data_signature(two))
nbs = Notebook("subjects")
rs1 = nbs.new_run("the first chain"); rs1.data = one; rs1.turns = [Turn(kind="cell", cell_no=1, code="a = 1")]
rs2 = nbs.new_run("the next, on the other", parent=rs1.id); rs2.data = two; rs2.turns = [Turn(kind="cell", cell_no=2, code="b = 1")]
rs3 = nbs.new_run("then an upload", parent=rs2.id); rs3.data = {"df_id": "U", "name": "u.csv", "rows": 3, "columns": [{"name": "t", "dtype": "int64"}]}
for r in (rs1, rs2, rs3): r.status = "answered"; r.report = "## r\n\nDone."
anc2, anc3 = nbs.render_ancestry(rs2.id), nbs.render_ancestry(rs3.id)
check("the ledger under a chain on another subject's data says so - the window's words, no name; after an upload (no subject on its record) the earlier chains are on 'other data'; the kernel is fresh either way (nothing of the first chain's rehydrated for the second)",
      "On another subject's data (window.csv, 2026-01-01 to 2026-03-01, 60 rows): its numbers are that data's; its cell 1 is not in the kernel" in anc2 and "The subject" not in anc2 and "The other subject" not in anc2
      and "another subject" not in anc3 and anc3.count("On other data (window.csv") == 2 and [c.cell_no for c in nbs.computed_cells(rs2.id)] == [2], (anc2, anc3))

# ---- the loop over a real kernel, with a scripted analyst ----
df = pd.DataFrame({"unit": np.repeat(["a", "b", "c", "d"], 50), "arm": np.tile(["A", "B"], 100),
                   "x": np.random.default_rng(0).normal(size=200)})
df.loc[df.arm == "B", "x"] += 0.5
NOTE = "- Question as understood: is B higher than A\n- Best estimate so far: none yet\n- Held fixed: nothing\n- Open doubts: unit clustering\n- Plan: compute\n- Names: df"
SCRIPT = [
 "###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\ng = df.groupby('arm')['x'].mean()\nprint('means', g.round(3).to_dict())\n```",
 "###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nbad_syntax(\n```",
 "###NOTE###\n" + NOTE + "\n###ACTION###\nNAMES",
 "###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\ndiff = round(g['B'] - g['A'], 3)\nper_unit = df.groupby(['unit','arm'])['x'].mean().unstack()\nprint('diff', diff)\nprint('n units', per_unit.shape[0])\n```",
 "###NOTE###\n" + NOTE + "\n###ACTION###\nSHOW 1",
 "###NOTE###\n" + NOTE.replace("none yet", "B-A = see cell 2") + "\n###ACTION###\nREPORT\n# B is higher than A by a small margin.\n\n## Answer\nB exceeds A by {DIFF} units on average across 4 units [cell 2]; the group means are in [cell 1]. The spread 0.999 is a made-up number.\n\n| arm | mean |\n|---|---|---|\n| A | 1 |\n",
]
calls = {"n": 0, "prompts": []}
def fake_llm(system, user, **hints):
    calls["prompts"].append(user)
    if user.startswith("Rewrite the technical report"):      # the seat's scaffold around the text, the title line forgotten, a cell citation left bare (2026-10-17: as a live Rewriter wrote)
        return "###STEP###\nI will rewrite.\n###NOTE###\n**Question as understood:** rewrite\n###ACTION###\nREPORT\n\nB is higher than A by about {DIFF} units, see cell 2 and [cells 1, 2]; and 7.777 is invented.", {"cost": 0.01}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    i = min(calls["n"], len(SCRIPT) - 1); calls["n"] += 1
    return SCRIPT[i], {"cost": 0.05, "prompt_tokens": 100, "completion_tokens": 50}
kernel = PersistentKernel(df=df); store = NotebookStore(tempfile.mkdtemp()); nb2 = Notebook("t2")
events = []
s = Session(kernel, nb2, fake_llm, store=store, emit=events.append, data_description="200 rows", kernel_factory=lambda: PersistentKernel(df=df))
# make the report's {DIFF} concrete after cell 2 runs: patch SCRIPT lazily via a closure
diff_value = {}
orig_run_cell = s.kernel.execute
run = None
try:
    # first two cells run; capture diff from cell 2's stdout then substitute in the report text
    class LLM:
        def __call__(self, system, user, **hints):
            text, usage = fake_llm(system, user)
            if "{DIFF}" in text:
                cells = nb2.path_cells(list(nb2.runs)[0])
                out = next((c.stdout for c in cells if "diff" in (c.stdout or "")), "diff 0.0")
                val = out.split("diff")[1].split()[0]
                text = text.replace("{DIFF}", val)
            return text, usage
    s.llm = LLM()
    run = s.run("Is B higher than A?", budget=Budget(turns=10, dollars=1.0))
finally:
    kernel.cleanup()
kinds = [t.kind for t in run.turns]
check("loop: every action kind ran and was recorded, in order",
      kinds == ["cell", "cell", "names", "cell", "show", "report", "rewrite"], kinds)
check("the report's title (2026-10-17): the report's first line, read without its marks or full stop, kept on the run and left in the report; the plain-language text has the seat's scaffold off, its cell citations out in any dress, and the same title as its first line",
      run.title == "B is higher than A by a small margin" and run.report.startswith("# B is higher than A by a small margin.\n") and run.rewrite.startswith("# B is higher than A by a small margin\n\nB is higher than A by about ")
      and "cell" not in run.rewrite.split("CHECK")[0] and "###" not in run.rewrite and "I will rewrite" not in run.rewrite and ", see; and 7.777" not in run.rewrite and run.turns[-1].text == run.rewrite, (run.title, run.rewrite[:160]))
cells = run.cells()
check("loop: only committed cells get numbers (the syntax error did not), numbering along the path",
      [c.cell_no for c in cells] == [1, 2] and run.turns[1].error and run.turns[1].cell_no is None)
check("loop: the kernel state persisted across cells (cell 2 used g from cell 1)", "n units 4" in cells[1].stdout)
check("loop: a committed cell's record names the kernel's state after it - which kernel, which step (2.9: the kernel goes back to it) - and a cell that failed, or a turn that ran none, names no state",
      [c.snap for c in cells] == [f"{kernel.uid}:1", f"{kernel.uid}:2"] and [t.snap for t in run.turns if t.cell_no is None] == [""] * 5, [t.snap for t in run.turns])
check("loop: SHOW re-opened cell 1 into the next prompt", any("SHOWN:" in p and "means" in p for p in calls["prompts"]))
check("loop: the prompt carries the contract's seven-heading note and collapses nothing while under the recent window",
      all("YOUR NOTE" in p for p in calls["prompts"][1:6]))
check("report: the technical guard flagged the invented 0.999 and nothing else",
      "CHECK: 1 number(s)" in run.report and "0.999" in run.report.split("CHECK")[1])
check("report: the table separator was repaired to the header's width", "|---|---|\n" in run.report and "|---|---|---|" not in run.report)
check("rewrite: same analyst, the guard flagged the invented 7.777", run.rewrite and "7.777" in run.rewrite.split("CHECK")[-1])
check("replay: assembled the two cited cells and reproduced them in a fresh kernel",
      run.replay_status == "reproduced" and "# --- cell 1 ---" in run.replay_script and "# --- cell 2 ---" in run.replay_script, run.replay_status)
kinds_seen = [e.get("type") for e in events]
check("emit: the replay announces itself before it runs and reports when done (replay_start with the cell count, then replay_end with the line), in that order and before replay_status",
      "replay_start" in kinds_seen and "replay_end" in kinds_seen and kinds_seen.index("replay_start") < kinds_seen.index("replay_end") < kinds_seen.index("replay_status")
      and next(e for e in events if e.get("type") == "replay_start").get("cells") == 2 and "reproduced" in (next(e for e in events if e.get("type") == "replay_end").get("line") or ""),
      [k for k in kinds_seen if "replay" in str(k)])
check("emit: cells, show, names, report, rewrite, replay_status all streamed",
      {e["type"] for e in events} >= {"cell", "names", "show", "report", "rewrite", "replay_status"})
saved = store.load("t2"); rr = saved.runs[run.id]
check("store: the run is on disk with its turns, reports, replay and title; a record carrying a key this version does not know loads all the same", rr.report == run.report and rr.replay_status == "reproduced" and len(rr.turns) == 7 and rr.title == run.title
      and Notebook.from_dict({"thread_id": "x", "runs": {"r": {"id": "r", "parent": None, "question": "q", "lead": "an old key", "turns": [{"kind": "cell", "stranger": 1}]}}}).runs["r"].question == "q")

# ---- error correction: the analyst SEES its failures; the namespace keeps pd/np/plt through a rollback ----
FAILS = ["###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nx = 1.5\nprint(x.round(2))\n```",           # fails: float has no round
         "###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nprint(pd.__version__ is not None, np.pi > 3)\n```",   # pd/np survive the rollback
         "###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nundefined_name + 1\n```",
         "###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nundefined_name + 2\n```",
         "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## Answer\nDone [cell 1].\n"]
seen = {"prompts": []}
def fail_llm(system, user, **hints):
    seen["prompts"].append(user)
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    i = min(len(seen["prompts"]) - 1, len(FAILS) - 1); return FAILS[i], {"cost": 0.01}
k2 = PersistentKernel(df=df); nb3 = Notebook("t3")
s3 = Session(k2, nb3, fail_llm, data_description="d")
try:
    r3 = s3.run("q", budget=Budget(turns=8, dollars=1.0))
finally:
    k2.cleanup()
kinds3 = [(t.kind, bool(t.error)) for t in r3.turns]
check("kernel: pd/np/plt are in the namespace without an import, and survive the rollback of a failed cell",
      kinds3[0] == ("cell", True) and kinds3[1] == ("cell", False) and "True True" in r3.turns[1].stdout, (kinds3, r3.turns[1].stdout, r3.turns[1].error[-120:]))
check("a failed cell is fed back to the analyst with its code and traceback, marked rolled back",
      "YOUR LAST CELL FAILED" in seen["prompts"][1] and "has no attribute 'round'" in seen["prompts"][1] and "x.round(2)" in seen["prompts"][1])
check("two failures in a row are said - the fact, no advice; one failure is not",
      "attempts in a row have failed" in seen["prompts"][4] and "attempts in a row have failed" not in seen["prompts"][1])
check("failed attempts are listed in CELLS SO FAR for the rest of the run",
      "FAILED ATTEMPTS THIS RUN" in [p_ for p_ in seen["prompts"] if "TASK:" in p_][-1] and "undefined_name" in [p_ for p_ in seen["prompts"] if "TASK:" in p_][-1])
_fa = [p_ for p_ in seen["prompts"] if "TASK:" in p_][-1]
_fa = _fa[_fa.find("FAILED ATTEMPTS THIS RUN"):]
check("failed attempts are placed in time - the turn, and the last cell committed before it (2026-10-11: a failure at turn 1 listed after cell 2 read as a failure after cell 2)",
      "- turn 1, before any cell:" in _fa and "has no attribute 'round'" in _fa.split("- turn 3")[0] and "- turn 3, after cell 1:" in _fa and "- turn 4, after cell 1:" in _fa
      and _fa.index("turn 1,") < _fa.index("turn 3,") < _fa.index("turn 4,"), _fa)

# ---- error condensing: the exception line first, verbose tails cut ----
from analyst.tools import condense_error, exception_line
from analyst import tools
long_err = ("Traceback (most recent call last):\n  File \"/tmp/k.py\", line 378, in <module>\n    exec(_user_code, G)\n  File \"<string>\", line 153, in <module>\n"
            "  File \"/site/plotly/_box.py\", line 3638, in __init__\n    self._process_kwargs(**dict(arg, **kwargs))\n"
            "ValueError: Invalid property specified for object of type plotly.graph_objs.Box: 'points'\n\nDid you mean \"pointpos\"?\n\n    Valid properties:\n"
            + "".join(f"        prop{i}\n            a long description of prop{i}\n" for i in range(200)) + "\n[delv-e: the failed attempt was rolled back]")
c = condense_error(long_err)
check("condense: the exception line comes first, the cell line and the hint follow, the property list is cut",
      c.startswith("ValueError: Invalid property") and "in your cell, line 153" in c and 'Did you mean "pointpos"' in c and len(c) < 1500 and "prop150" not in c, c[:200])
check("exception_line: names the error, never the rollback notice", exception_line(long_err).startswith("ValueError:"))

# ---- assembly dependencies ----
from analyst.notebook import Turn
cs = [Turn(kind="cell", code="import numpy as np\nbase = 3", cell_no=1, stdout="3"),
      Turn(kind="cell", code="junk = 99\nprint(junk)", cell_no=2, stdout="99"),
      Turn(kind="cell", code="y = base * 2\nprint('y', y)", cell_no=3, stdout="y 6")]
script, order = replay.assemble(cs, "the answer is 6 [cell 3]")
check("assemble: the committed record up to the last cited cell, unpruned (hidden dependencies survive)", order == [1, 2, 3], order)
check("assemble: citing only an early cell stops the record there", replay.assemble(cs, "see [cell 1]")[1] == [1])
check("assemble: a figure reference counts as a citation", replay.assemble(cs, "see [fig 2]")[1] == [1, 2])
# figures of earlier runs are not this run's plots: the parent's cells run for state, their fig.show() is muted
parent = [Turn(kind="cell", cell_no=1, code="import plotly.graph_objects as go\nfig = go.Figure(); fig.show()", stdout="x"),
          Turn(kind="cell", cell_no=2, code="y = 2", stdout="x")]
child = [Turn(kind="cell", cell_no=3, code="fig2 = go.Figure(); fig2.show()\nprint(y)", stdout="2")]
script, order = replay.assemble(parent + child, "fixed: [cell 3] [fig 3]", own=child)
shown = []
import types, sys
fake_pio = types.SimpleNamespace(show=lambda fig, *a, **k: shown.append(fig))
class _Fig:
    def show(self): import plotly.io as pio; pio.show(self)
fake_go = types.SimpleNamespace(Figure=_Fig)
sys.modules['plotly'] = types.SimpleNamespace(io=fake_pio, graph_objects=fake_go); sys.modules['plotly.io'] = fake_pio; sys.modules['plotly.graph_objects'] = fake_go
ns = {}; exec(script, ns)
check("assemble: the parent's figure is not captured, the child's is; the parent's state (y) still reaches the child",
      order == [1, 2, 3] and len(shown) == 1 and ns.get("y") == 2, (order, len(shown)))
shown.clear(); script2, _ = replay.assemble(parent + child, "see the earlier [fig 1] and [cell 3]", own=child); exec(script2, {})
check("assemble: an earlier figure the report cites as [fig n] is captured again on request", len(shown) == 2)
for k in ('plotly', 'plotly.io', 'plotly.graph_objects'): sys.modules.pop(k, None)

# ---- the failure ceiling: five failed cells in a row force the report ----
LOOP = ["###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nundefined_thing + %d\n```" % i for i in range(9)]
seen_loop = {"n": 0, "halt_seen": False, "prompts": []}
def loop_llm(system, user, **hints):
    seen_loop["prompts"].append(user)
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    if "STOP:" in user and "could not get past this error" in user:
        seen_loop["halt_seen"] = True
        return "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## Answer\nCould not get past the error; nothing established.\n", {"cost": 0.01}
    i = seen_loop["n"]; seen_loop["n"] += 1
    return LOOP[min(i, len(LOOP) - 1)], {"cost": 0.01}
k4 = PersistentKernel(df=df); nb4 = Notebook("t4"); ev4 = []
try:
    r4 = Session(k4, nb4, loop_llm, data_description="d", emit=ev4.append).run("q", budget=Budget(turns=15, dollars=1.0))
finally:
    k4.cleanup()
fails_in_row = sum(1 for t in r4.turns if t.kind == "cell" and t.error)
check("ceiling: after five consecutive failed cells the session stops trying and forces the report (not fifteen attempts)",
      fails_in_row == 5 and seen_loop["halt_seen"] and r4.status == "answered" and "Could not get past" in r4.report, (fails_in_row, seen_loop["halt_seen"], r4.status))
_t4 = [(e["type"], e.get("turn")) for e in ev4 if e["type"] in ("turn_start", "turn_end")]
check("ceiling: the forced report is a turn with a card - turn_start then turn_end, both numbered after the last attempt (2026-10-08)",
      ("turn_start", 6) in _t4 and ("turn_end", 6) in _t4 and _t4.index(("turn_start", 6)) < _t4.index(("turn_end", 6)), _t4)

# the budget exhausted without a report (2026-10-08): the forced call has a card too - a turn_start before the stream,
# numbered as its turn_end is - and a reply shaped like the report but without the marker lines, before the report turn,
# is told what was missing
ex_prompts, ex_events = [], []
def exhausted_llm(system, user, **h):
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    ex_prompts.append(user)
    if len(ex_prompts) in (1, 3):
        return "###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nprint('RESULT: x, 5 units: +1 (95% CI 0 to 2), up')\n```", {"cost": 0.001}
    if len(ex_prompts) == 2:   # the report written without the scaffold: a lead paragraph, a bare REPORT line, headings
        return "The data do not identify a stable correction.\n\nREPORT\n\n# Title\n\n## Summary\nNothing [cell 1].", {"cost": 0.001}
    return "## Summary\n\nTaken whole at the forced call [cell 1].", {"cost": 0.001}
kex = PersistentKernel(df=df); nbex = Notebook("tex")
try:
    rex = Session(kex, nbex, exhausted_llm, data_description="d", emit=ex_events.append).run("q", budget=Budget(turns=3, dollars=1.0, review_every=0))
finally:
    kex.cleanup()
_tex = [(e["type"], e.get("turn"), e.get("kind")) for e in ex_events if e["type"] in ("turn_start", "turn_end")]
check("a report-shaped reply with no ###ACTION### block loses the turn and is told so precisely - not 'no valid action'",
      "Your last reply read like the report but had no ###ACTION### block, so it was not taken as one; nothing ran. A report is: ###ACTION### on its own line, REPORT on the next, then the report." in ex_prompts[2]
      and "no valid action" not in ex_prompts[2] and rex.turns[1].kind == "error", (ex_prompts[2][-400:], [t.kind for t in rex.turns]))
check("the budget exhausted: the forced report call is turn 4 of 3 with a turn_start before its turn_end, and its text is the report",
      ("turn_start", 4, None) in _tex and ("turn_end", 4, "report") in _tex and _tex.index(("turn_start", 4, None)) < _tex.index(("turn_end", 4, "report"))
      and len(ex_prompts) == 4 and "Write REPORT now." in ex_prompts[3] and rex.report.startswith("## Summary") and rex.status == "answered", (_tex, rex.report[:80]))
# on the report turn itself (2026-10-18, a Sonnet 5.5 run wrote the report there without its marker lines and the forced
# call had it written again): a reply shaped like the report is the report, from its first heading; a reply cut at the
# length limit is not, and the forced call asks for it
def _report_turn_run(cut, name):
    prompts = []
    def llm(system, user, **h):
        if user.startswith("Rewrite"): return "plain", {"cost": 0}
        if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
        prompts.append(user)
        if len(prompts) == 1:
            return "###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nprint('RESULT: x, 5 units: +1 (95% CI 0 to 2), up')\n```", {"cost": 0.001}
        if len(prompts) == 2:
            return ("###STEP###\nThe budget is spent; this turn writes the report.\n###NOTE###\n" + NOTE + "\n\n# Title\n\n## Summary\nUp by 1 [cell 1].",
                    {"cost": 0.001, "truncated": cut})
        return "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## Summary\n\nFrom the forced call [cell 1].", {"cost": 0.001}
    kk = PersistentKernel(df=df)
    try:
        rr = Session(kk, Notebook(name), llm, data_description="d").run("q", budget=Budget(turns=2, dollars=1.0, review_every=0))
    finally:
        kk.cleanup()
    return rr, prompts
_rt, _rt_p = _report_turn_run(False, "trt")
_rc, _rc_p = _report_turn_run(True, "trc")
check("the report turn: a reply shaped like the report without its marker lines is the report, from its first heading - no second call; cut at the length limit it is not, and the forced call writes it",
      len(_rt_p) == 2 and _rt.status == "answered" and _rt.report.startswith("# Title\n\n## Summary\nUp by 1 [cell 1].") and "###" not in _rt.report.split("> ")[0]
      and [t.kind for t in _rt.turns][:2] == ["cell", "report"]
      and len(_rc_p) == 3 and _rc.report.startswith("## Summary\n\nFrom the forced call"), (len(_rt_p), _rt.report[:120], len(_rc_p), _rc.report[:80]))
_chat = parse_turn("I think the next step should be a within-athlete fit, let me set that up.")
check("a chatty reply with no headings, citations or fence is not report-shaped: it still reads 'no valid action'",
      _chat[2].verb == "invalid" and not __import__("analyst.session", fromlist=["_reads_like_report"])._reads_like_report("I think the next step should be a within-athlete fit."))

# an action written as a tool call, in the model's own markup, with no marker lines (2026-10-18: Sonnet 5.5 began three
# turns of a Deep run so and stopped; there are no tools): read from the call on as the action block
from analyst.session import TOOL_CALL_TAKEN
_tc1 = parse_turn('\n<invoke name="SHOW">\n2\n</invoke>\n</invoke>')
_tc2 = parse_turn('\n<invoke name="x">\n</invoke>\n```python\nprint(1)\n```')
_tc3 = parse_turn('<invoke name="cell_placeholder">\n</invoke>\n```python\na = 1\n```\n\nWait - that was a tool call. Let me redo it.\n\n###STEP###\n...')
_tc4 = parse_turn('<function_calls>\n<invoke name="search">\n<parameter name="query">median split</parameter>\n</invoke>\n</function_calls>')
_tc5 = parse_turn('<invoke name="x">\n</invoke>\n```python\nprint(1)\n')
_tc6 = parse_turn('<invoke name="x">\n</invoke>\nI will look at the table next.')
_tc7 = parse_turn('\n<invoke name="cell">\n</invoke>\n```\n\nThe turn itself.\n\n###STEP###\ns\n###NOTE###\nn\n###ACTION###\n```python\nprint(2)\n```')
check("parse_turn: an action written as a tool call with no marker lines is read from the call on - a call named for an action is that action (SHOW 2), any other gives way to the block after it, parameters and wrappers go; an unclosed block or no action is lost as before; with the marker lines present they rule",
      (_tc1[2].verb, _tc1[2].arg, _tc1[2].tool_call, _tc1[0], _tc1[1]) == ("show", "2", True, "", "")
      and (_tc2[2].verb, _tc2[2].arg, _tc2[2].tool_call) == ("cell", "print(1)", True)
      and (_tc3[2].verb, _tc3[2].arg, _tc3[2].more) == ("cell", "a = 1", ())
      and (_tc4[2].verb, _tc4[2].arg) == ("search", "median split")
      and (_tc5[2].verb, _tc5[2].arg) == (_tc6[2].verb, _tc6[2].arg) == ("invalid", "no ###ACTION### block")
      and (_tc7[2].verb, _tc7[2].arg, _tc7[2].tool_call, _tc7[1]) == ("cell", "print(2)", False, "n"),
      [_tc1, _tc2[2], _tc3[2], _tc4[2], _tc5[2], _tc6[2], _tc7])
def _tool_call_run():
    prompts = []
    def llm(system, user, **h):
        if user.startswith("Rewrite"): return "plain", {"cost": 0}
        if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
        prompts.append((system, user))
        if len(prompts) == 1:
            return "\n<invoke name=\"x\">\n</invoke>\n```python\nprint('RESULT: x, 5 units: +1 (95% CI 0 to 2), up')\n```", {"cost": 0.001}
        return "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## Summary\n\nUp by 1 [cell 1].", {"cost": 0.001}
    kk = PersistentKernel(df=df)
    try:
        rr = Session(kk, Notebook("ttc"), llm, data_description="d").run("q", budget=Budget(turns=3, dollars=1.0, review_every=0))
    finally:
        kk.cleanup()
    return rr, prompts
_trc, _trc_p = _tool_call_run()
check("a run: the cell written as a tool call runs as cell 1, and the next prompt says so without naming any markup; the contract says there are no tools where it sets the reply's form, and carries no markup either",
      [t.kind for t in _trc.turns][:2] == ["cell", "report"] and _trc.turns[0].cell_no == 1 and _trc.status == "answered"
      and TOOL_CALL_TAKEN in _trc_p[1][1] and not re.search(r"</?(invoke|parameter|function_calls)\b", _trc_p[1][1] + TOOL_CALL_TAKEN + contract(False, 8))
      and "## Format\n\nThere are no tools: every reply is plain text with these three sections" in _trc_p[0][0],
      ([t.kind for t in _trc.turns], _trc_p[1][1][-300:]))
# the fallback completed (2026-10-18, the next Sonnet 5.5 run): code passed as the call's argument, a call before marker lines
# filled with filler, and a stray tag line inside a cell followed by a corrected copy
_tc8 = parse_turn('\n<invoke name="python">\n<parameter name="code">\nx = 1\n# the total\nprint(x)\n</parameter>\n</invoke>\n')
_tc9 = parse_turn('\n<invoke name="python">\n```python\nprint(3)\n```\n###STEP###\nplaceholder\n###NOTE###\nplaceholder\n###ACTION###\nplaceholder')
_tc10 = parse_turn("###STEP###\ns\n###NOTE###\nn\n###ACTION###\n```python\na = 1\nprint(a)\n</code>\n```\n\nThe block above has a stray tag; the corrected one:\n\n```python\na = 1\nprint(a)\n```")
_tc11 = parse_turn("###NOTE###\nn\n###ACTION###\n```python\ns = '''\n</code>\n'''\nprint(s)\n```")
_tc12 = parse_turn("###NOTE###\nn\n###ACTION###\n```python\nprint(1\n</code>\n```")
_tc13 = parse_turn('<invoke name="x">\n<parameter name="text">I will look at the table next.</parameter>\n</invoke>')
check("parse_turn: code passed as a call's argument is the cell; a call before marker lines filled with filler gives its cell, the filler no note; a cell broken only by a stray tag line runs without it (its corrected copy the same action); a tag line in code that compiles stays, and one in code broken anyway is left; prose in a call is no action",
      (_tc8[2].verb, _tc8[2].arg, _tc8[2].tool_call) == ("cell", "x = 1\n# the total\nprint(x)", True)
      and (_tc9[2].verb, _tc9[2].arg, _tc9[2].tool_call, _tc9[1]) == ("cell", "print(3)", True, "")
      and (_tc10[2].verb, _tc10[2].arg, _tc10[2].more, _tc10[2].tool_call) == ("cell", "a = 1\nprint(a)", (), False)
      and _tc11[2].arg == "s = '''\n</code>\n'''\nprint(s)" and _tc12[2].arg == "print(1\n</code>" and _tc13[2].verb == "invalid",
      [_tc8[2], _tc9, _tc10[2], _tc11[2], _tc12[2], _tc13[2]])

# REPORT with nothing under it (2026-10-11, from a deepseek-v4.1-flash run log: "this turn = REPORT", the word written and the
# reply ended; the empty text went through as the answer and the reader saw the figures section alone): not a report - the
# turn is told what a report is, and the next reply's report is taken whole
from analyst.session import REPORT_EMPTY
_er = parse_turn("###STEP###\nThe analysis is complete; I will now write the report.\n###NOTE###\n- Plan: this turn = REPORT\n###ACTION###\nREPORT")
check("parse_turn: REPORT with nothing under it is not a report - an invalid action naming the reason; the text on the REPORT line counts as the report's first line",
      _er[2].verb == "invalid" and _er[2].arg == REPORT_EMPTY and parse_turn("###NOTE###\nn\n###ACTION###\nREPORT The answer [cell 1].\n\nMore.")[2].arg == "The answer [cell 1].\n\nMore."
      and parse_turn("###NOTE###\nn\n###ACTION###\nREPORT\n\n## Answer\n\nx")[2].arg == "## Answer\n\nx", (_er[2], _er[1]))
em_prompts = []
def empty_report_llm(system, user, **h):
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    em_prompts.append(user)
    if len(em_prompts) == 1:
        return "###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nprint('RESULT: x, 5 units: +1 (95% CI 0 to 2), up')\n```", {"cost": 0.001}
    if len(em_prompts) == 2:
        return "###STEP###\nThe analysis is complete; I will now write the report.\n###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT", {"cost": 0.001}
    return "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## Answer\n\nThe answer is +1 [cell 1].", {"cost": 0.001}
kem = PersistentKernel(df=df); nbem = Notebook("tem")
try:
    rem = Session(kem, nbem, empty_report_llm, data_description="d").run("q", budget=Budget(turns=6, dollars=1.0))
finally:
    kem.cleanup()
check("the loop: an empty REPORT loses its turn and is told the report is the text under REPORT, in the same reply; the next reply's report is the answer, whole",
      rem.turns[1].kind == "error" and "Your last reply ended at REPORT with no report under it" in em_prompts[2] and "no valid action" not in em_prompts[2]
      and rem.report.startswith("## Answer\n\nThe answer is +1 [cell 1].") and rem.status == "answered" and len(em_prompts) == 3, (em_prompts[2][-300:], rem.report[:100]))

# ---- the Data tab's page function ----
import _stubs  # noqa: F401  (the package import pulls the console output manager; the sandbox lacks termcolor)
from bambooai.utils import page_frame
import pandas as pd, numpy as np
pf = pd.DataFrame({"id": [f"s{i:03d}" for i in range(120)], "v": np.arange(120, dtype=float), "cat": pd.Categorical(["a", "b"] * 60),
                   "when": pd.date_range("2025-01-01", periods=120, freq="h"), "flag": [True, False] * 60})
pf.loc[5, "v"] = np.nan
pg = page_frame(pf, 50, 50)
check("page_frame: a page of 50 at offset 50, the total, columns and dtypes, JSON-safe values (NaN -> None, Timestamp -> text)",
      pg["total"] == 120 and len(pg["rows"]) == 50 and pg["rows"][0][0] == "s050" and pg["columns"] == ["id", "v", "cat", "when", "flag"]
      and pg["dtypes"][3].startswith("datetime") and isinstance(pg["rows"][0][3], str) and page_frame(pf, 5, 1)["rows"][0][1] is None)
last = page_frame(pf, 119, 50); srt = page_frame(pf, 0, 3, order_by="v", ascending=False)
check("page_frame: the last row is reachable; sorting is server-side on the whole frame; a bad column is ignored",
      len(last["rows"]) == 1 and last["rows"][0][0] == "s119" and srt["rows"][0][1] == 119.0 and page_frame(pf, 0, 2, order_by="nope")["order_by"] is None)
check("page_frame: the executor's copy is byte-identical to the app's",
      (lambda a, b: a[a.index('def page_frame('):a.index("# ---- the Data tab's grid for auxiliary files")].strip() == b[b.index('def page_frame('):b.index("_AUX_FRAMES = {}")].strip())(
          open(os.path.join(ROOT, 'bambooai', 'utils.py'), 'rb').read().decode('utf-8').replace('\r\n', '\n'),
          open(os.path.join(ROOT, 'containers', 'executor', 'code_executor_api.py'), 'rb').read().decode('utf-8').replace('\r\n', '\n')))

# ---- the thread: the ledger never collapses; the newest chains ride whole; corrections carry; SHOW RUN opens any chain ----
# five chains in the shape of the Mt Buller thread: an identity guess, a chart, two corrections, a re-draw
NOTE5 = ("- Question as understood: q\n- Best estimate so far: none yet\n- Held fixed: nothing yet\n- Open doubts: none\n"
         "- Plan: report\n- Names: df, yearly\n- Standing instructions from the person: no site name in answers; show the 1991-2001 gap years, do not drop them")
def thread_llm_factory(script):
    calls = {"i": 0}
    def llm(system, user, **hints):
        if user.startswith("Rewrite"): return "plain", {"cost": 0}
        if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
        i = calls["i"]; calls["i"] += 1
        return script[min(i, len(script) - 1)], {"cost": 0.001}
    return llm
k5 = PersistentKernel(df=df); nb5 = Notebook("t5")
qs = ["What is this dataset ?", "Plot annual precipitation and the snow share", "Why are 1991-2001 missing? They should be in the data",
      "Why Craigieburn? All we need is in the dataset", "Re-draw the stacked chart with snow in a different colour"]
reports = ["## What this dataset is\n\nA daily record for one ski field, 1988-2025, Craigieburn (NZ) by fingerprint search. Each row is one day.",
           "## Annual precipitation\n\nAcross 25 well-covered years precipitation averaged 1631 mm, of which 16% fell as snow. The gap years were dropped.",
           "## Why 1991-2001 look missing\n\nEvery day 1991-2001 is in the table; the station gauge is 62% complete. The earlier chart's 90% rule hid them.",
           "## Why Craigieburn\n\nThe name is not in the file. Location is unidentified in-file; earlier answers inferred it from a search.",
           "## The chart\n\nRedrawn with all years shown, no site name."]
parent = None; runs5 = []
try:
    for q, rep in zip(qs, reports):
        script = ["###NOTE###\n" + NOTE5 + "\n###ACTION###\nCELL\n```python\n# a marker cell for this chain\nprint('chain ok')\n```",
                  "###NOTE###\n" + NOTE5 + "\n###ACTION###\nREPORT\n" + rep]
        sess5 = Session(k5, nb5, thread_llm_factory(script), data_description="File: mtbuller_climate.csv\n`df`: 200 rows")
        r = sess5.run(q, parent=parent, budget=Budget(turns=4, dollars=1.0)); runs5.append(r); parent = r.id
    # what chain 5's prompt would contain (its ancestry + cells view), built exactly as _user_prompt does
    anc = nb5.render_ancestry(runs5[4].id)
    check("thread: the ledger lists every earlier chain's question whole, in order",
          all(f"[run {k}] Q: {qs[k-1]}" in anc for k in range(1, 5)) and anc.index("[run 1]") < anc.index("[run 4]"), anc[:400])
    check("thread: each ledger line carries the chain's conclusion (the report's opening) and the names it left",
          "The name is not in the file." in anc and "Every day 1991-2001 is in the table" in anc and "Names left in the kernel: df, yearly" in anc)
    check("thread: the two most recent chains ride whole (final note + answer opening); chain 4 - the correction - is among them",
          "--- run 4: Why Craigieburn?" in anc and "--- run 3: Why are 1991-2001" in anc and "--- run 2:" not in anc.split("THE MOST RECENT CHAINS")[1])
    check("thread: the standing instructions travel in the note verbatim",
          "Standing instructions from the person: no site name in answers; show the 1991-2001 gap years" in anc)
    check("thread: no character cut anywhere in the ancestry (no 'collapsed' marker, a 5-chain ledger is a few KB)",
          "collapsed" not in anc and 1500 < len(anc) < 8000, len(anc))
    check("SHOW RUN 1 opens the first chain whole: question, note, report", "Craigieburn (NZ) by fingerprint" in nb5.render_run(runs5[4].id, 1) and "QUESTION: What is this dataset ?" in nb5.render_run(runs5[4].id, 1))
    check("SHOW RUN 9 on a 4-chain history says so", "no run 9" in nb5.render_run(runs5[4].id, 9))
    # a 30-chain thread: every question is still in the ledger
    parent = runs5[4].id
    for i in range(30):
        sess = Session(k5, nb5, thread_llm_factory(["###NOTE###\n" + NOTE5 + "\n###ACTION###\nREPORT\n## r\n\nConclusion number %d." % i]), data_description="d")
        r = sess.run("question number %d" % i, parent=parent, budget=Budget(turns=2, dollars=1.0)); parent = r.id
    anc30 = nb5.render_ancestry(parent)
    check("thread: from the 35th chain, the ledger names all 34 earlier questions, the newest two whole (33 and 34), 32 only in the ledger",
          all(f"question number {i}" in anc30 for i in range(29)) and anc30.count("[run ") == 34 and "--- run 34:" in anc30 and "--- run 33:" in anc30 and "--- run 32:" not in anc30, (anc30.count("[run "), len(anc30)))
    # cell headlines carry the cell's purpose (its first comment)
    cells_view = nb5.render_cells(parent)
    check("headline: a collapsed cell shows its first comment and its first output line", "a marker cell for this chain  ->  chain ok" in cells_view)
finally:
    k5.cleanup()
# the record is not cut: a cell printing 50,000 characters is stored whole; the VIEW is capped with its handle
k6 = PersistentKernel(df=df); nb6 = Notebook("t6")
big = ["###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nprint('x' * 50000)\n```",
       "###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nprint('second')\n```",
       "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## r\n\nDone."]
try:
    r6 = Session(k6, nb6, thread_llm_factory(big), data_description="d").run("q", budget=Budget(turns=4, dollars=1.0))
    c1 = r6.cells()[0]
    check("record: a 50,000-character output is stored whole (no 20K cut); the view shows a capped copy with SHOW n as the handle",
          len(c1.stdout) >= 50000 and "SHOW 1 for all" in nb6.render_cells(r6.id) and "more characters" in nb6.render_cells(r6.id), len(c1.stdout))
finally:
    k6.cleanup()

# ---- the synthesis of a thread (2026-10-03): shown runs stay in view, SHOW RUN takes several, the report comes in a handful of turns ----
# five reported chains like the log's (reports of about a thousand words), then the synthesis question
def act6(line): return "###NOTE###\n" + NOTE5 + "\n###ACTION###\n" + line
k6 = PersistentKernel(df=df); nb6 = Notebook("t6")
parent6 = None; runs6 = []
long_para = " ".join(f"Sentence {i} of the chain's report states a finding with the number {100 + i}." for i in range(1, 60))
for n in range(1, 6):
    rep_n = f"## Chain {n}\n\nThe best estimate of chain {n} is {n * 11} units (interval {n * 11 - 2} to {n * 11 + 2}).\n\n{long_para}\n\nLimitations of chain {n}: few sites."
    script6 = [act6("CELL\n```python\nprint('chain %d: %d')\n```" % (n, n * 11)), act6("REPORT\n" + rep_n)]
    r6 = Session(k6, nb6, thread_llm_factory(script6), data_description="d").run(f"Question {n}?", parent=parent6, budget=Budget(turns=4, dollars=1.0)); runs6.append(r6); parent6 = r6.id
syn_prompts = []
SYN = [act6("SHOW RUN 1 2 3"), act6("SHOW RUN 4"), act6("REPORT\n## The thread\n\nChain 1 found 11 units [run 1], chain 2 22 [run 2], chain 3 33 [run 3], chain 4 44 [run 4], chain 5 55 [run 5].")]
syn_i = {"n": 0}
def syn_llm(system, user, **h):
    syn_prompts.append(user)
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    i = syn_i["n"]; syn_i["n"] += 1
    return SYN[min(i, len(SYN) - 1)], {"cost": 0.001}
try:
    syn = Session(k6, nb6, syn_llm, data_description="d").run("Write the report for the analysis so far on this thread.", parent=parent6, budget=Budget(turns=15, dollars=1.5))
finally:
    k6.cleanup()
p2 = syn_prompts[1]; p3 = syn_prompts[2]
check("synthesis: SHOW RUN 1 2 3 opens three chains in one turn, and they stand in the next prompt under RUNS SHOWN THIS RUN, whole",
      "RUNS SHOWN THIS RUN" in p2 and all(f"--- run {k} ---" in p2.split("RUNS SHOWN THIS RUN")[1] for k in (1, 2, 3)) and "Sentence 59 of the chain's report" in p2.split("RUNS SHOWN THIS RUN")[1]
      and p2.count("SHOWN: run 1 2 3 - whole, under RUNS SHOWN THIS RUN above") == 1, [ln for ln in p2.splitlines() if ln.startswith("---") or ln.startswith("SHOWN") or ln.startswith("RUNS")])
check("synthesis: after SHOW RUN 4 all four shown runs stand whole - they fit the budget together (2026-10-03: a count of three had kept a five-chain synthesis cycling)",
      all(f"--- run {k} ---" in p3 for k in (1, 2, 3, 4)) and "was shown at turn" not in p3, [ln for ln in p3.splitlines() if ln.startswith("---") or ln.startswith("(run")])
from analyst import session as _sess
_saved_chars = _sess.SHOWN_RUNS_CHARS; _sess.SHOWN_RUNS_CHARS = 10500     # room for two of these reports, not three
try:
    small = Session(None, nb6, lambda s_, u, **h: ("", {}), data_description="d")
    block = small._shown_runs(syn)
finally:
    _sess.SHOWN_RUNS_CHARS = _saved_chars
check("synthesis: past the character budget the oldest shown runs collapse to a line each, the newest stay whole",
      "(run 1 was shown at turn 1; SHOW RUN 1 brings it back whole)" in block and "(run 2 was shown at turn 1; SHOW RUN 2 brings it back whole)" in block
      and "--- run 4 ---" in block and "--- run 3 ---" in block and block.count("--- run 1 ---") == 0, [ln for ln in block.splitlines() if ln.startswith("---") or ln.startswith("(run")])
pm = parse_turn("###NOTE###\nn\n###ACTION###\nCELL\n```python\na = 1\n```\nCELL\n```python\nprint(a + 1)\n```")[2]
check("parse_turn: two different cells in one reply - the first runs, the second is recorded as not run (2026-10-06)", pm.verb == "cell" and pm.arg == "a = 1" and pm.more == ("cell",), (pm.verb, pm.arg, pm.more))
pr = parse_turn("###THINKING###\nfirst idea\n###NOTE###\nn1\n###ACTION###\nCELL\n```python\nprint('draft')\n```\n\nWait - one action per turn. Let me redo it.\n\n###THINKING###\nsecond idea\n###NOTE###\nn2\n###ACTION###\nCELL\n```python\nprint('meant')\n```")
check("parse_turn: a reply that starts over with a different cell runs the first and keeps the note written before it; the restart is recorded",
      pr[2].verb == "cell" and pr[2].arg == "print('draft')" and pr[2].more == ("cell",) and pr[1] == "n1", (pr[2].verb, pr[2].arg, pr[2].more, pr[1]))
pr2 = parse_turn("###THINKING###\nidea\n###NOTE###\nn\n###ACTION###\nCELL\n```python\nprint('a')\n```\n###THINKING###\ntrailing thoughts with no action")
check("parse_turn: a trailing THINKING without an ACTION is not a restart - the turn stands", pr2[2].verb == "cell" and pr2[2].arg == "print('a')", (pr2[2].verb, pr2[2].arg))
pr3 = parse_turn("###THINKING###\nidea\n###NOTE###\nn1\n###ACTION###\nCELL\n```python\nprint('draft')\n```\n(That is the cell.)\n\nWait - one action per turn.\n###ACTION###\nSHOW 11")
check("parse_turn: a restart from ###ACTION### alone with another action - the first runs, the other recorded", pr3[2].verb == "cell" and pr3[2].more == ("show",), (pr3[2].verb, pr3[2].more))
pr4 = parse_turn("###THINKING###\nidea\n###NOTE###\nn\n###ACTION###\nCELL\n```python\nprint('a')\n```\n###ACTION###")
check("parse_turn: a bare ###ACTION### after a complete turn (seen in real logs) is not a turn - the one before it stands", pr4[2].verb == "cell" and pr4[2].arg == "print('a')" and pr4[1] == "n", (pr4[2].verb, pr4[2].arg, pr4[1]))
pr5 = parse_turn("###THINKING###\nidea\n###NOTE###\nn\n###ACTION###\nCELL\n```python\nprint('a')\n```\n###ACTION###\nCELL")
check("parse_turn: a restart given up after one word ('CELL' and nothing) is no action either - the complete one before it stands (seen in a real log)", pr5[2].verb == "cell" and pr5[2].arg == "print('a')", (pr5[2].verb, pr5[2].arg))
c_all = open(os.path.join(ROOT, "analyst", "contract.md")).read()
check("contract: the turn is one action and its result reaches the model next turn - said once, under How a turn works, and never an invitation to restart in the reply", "nothing in this reply can depend on it" in c_all and "write the turn once" not in c_all and "Begin again" not in c_all and "###END###" not in c_all)
from analyst.session import clean_note
pn = parse_turn("###NOTE###\n- **Question as understood:** q\n- **Best estimate so far:** 7.4% [D1.7]\n- *Plan*: next\n###ACTION###\nNAMES")
check("parse_turn: a model's bold or italic markers around the note's headings are removed at the source - every reader sees 'Heading: content' (2026-10-04: '**' reached the pane)",
      pn[1] == "- Question as understood: q\n- Best estimate so far: 7.4% [D1.7]\n- Plan: next", repr(pn[1]))
check("clean_note: a plain note is unchanged, and a line with no heading is left alone", clean_note("- Names: df\nfree text line") == "- Names: df\nfree text line")
check("contract: the note's headings are shown plainly, not in bold", "- Question as understood: what you take" in c_all and "**Question" not in c_all)
pb = parse_turn("###NOTE###\nn\n###ACTION###\n```python\nprint(1)\n```")
check("parse_turn: a fenced block directly under ###ACTION### is a cell - no CELL word needed (2026-10-05: six turns of a run were refused for its absence)", pb[2].verb == "cell" and pb[2].arg == "print(1)", (pb[2].verb, pb[2].arg))
pb2 = parse_turn("###NOTE###\nn\n###ACTION###\n```\nCELL\n```\n```python\nprint(2)\n```")
check("parse_turn: a fenced CELL word followed by the block is the cell", pb2[2].verb == "cell" and pb2[2].arg == "print(2)", (pb2[2].verb, pb2[2].arg))
pm2 = parse_turn("###NOTE###\nn\n###ACTION###\nCELL\n```python\na = 1\n```\nSHOW 3")[2]
check("parse_turn: a CELL followed by another kind of action runs the cell and records the other", pm2.verb == "cell" and pm2.more == ("show",), (pm2.verb, pm2.more))
check("synthesis: the report comes at the third exchange and is answered; the numbers it cites are the chains' and pass the guard through the path's cells",
      syn.status == "answered" and len([x for x in syn.turns if x.kind != "rewrite"]) == 3 and "CHECK:" not in syn.report, (syn.status, [x.kind for x in syn.turns], syn.report[-200:]))
check("synthesis: the prompt with three chains whole stays well inside a 64k context (chars/4)", len(p2) // 4 < 20000, len(p2) // 4)
check("the contract: SHOW RUN takes several and the chains stay in view; shown cells are for the next prompt", "`SHOW RUN <run numbers>`" in c_all and "stay in view for the rest of the run" in c_all and "Those cells, whole, in your next prompt" in c_all)
# a SHOW of several cells at once is capped from the middle, with the marker; the record keeps it whole
kc = PersistentKernel(df=df); nbc = Notebook("tc")
big_cells = [act6("CELL\n```python\nprint('x' * 30000)\n```"), act6("CELL\n```python\nprint('y' * 30000)\n```"), act6("SHOW 1 2"), act6("REPORT\n## r\n\nDone.")]
cap_prompts = []
cap_i = {"n": 0}
def cap_llm(system, user, **h):
    cap_prompts.append(user)
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    i = cap_i["n"]; cap_i["n"] += 1
    return big_cells[min(i, len(big_cells) - 1)], {"cost": 0.001}
try:
    rc = Session(kc, nbc, cap_llm, data_description="d").run("q", budget=Budget(turns=5, dollars=1.0))
finally:
    kc.cleanup()
shown_view = cap_prompts[3].split("SHOWN:")[1].split("\n\nTASK:")[0] if "SHOWN:" in cap_prompts[3] else ""
check("SHOW 1 2 of two 30,000-character outputs: the view is cut from the middle at 40,000 with the marker, the record keeps both whole",
      0 < len(shown_view) <= 40_200 and "characters omitted from the middle for length; the notebook keeps it whole" in shown_view and len(rc.turns[2].stdout) > 60_000, (len(shown_view), len(rc.turns[2].stdout)))

# ---- without documents the run is the original run: every exchange is a turn (2026-10-03) ----
plain_prompts = []
PLAIN = [act6("SHOW 1"), act6("NAMES"), act6("CELL\n```python\nprint('one')\n```"), act6("REPORT\n## r\n\nDone.")]
pl_i = {"n": 0}
def plain_llm(system, user, **h):
    plain_prompts.append(user)
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    i = pl_i["n"]; pl_i["n"] += 1
    return PLAIN[min(i, len(PLAIN) - 1)], {"cost": 0.001}
kp = PersistentKernel(df=df); nbp = Notebook("tp")
try:
    rp = Session(kp, nbp, plain_llm, data_description="d").run("q", budget=Budget(turns=4, dollars=1.0))
finally:
    kp.cleanup()
tl_p = [ln for q in plain_prompts for ln in q.splitlines() if ln.startswith("TASK:")]
check("without documents, a SHOW and a NAMES cost a turn each, as in the original: the task line counts every exchange",
      tl_p[:4] == ["TASK: turn 1; up to 4 turns and $1.00 (spent $0.00).", "TASK: turn 2; up to 4 turns and $1.00 (spent $0.00).", "TASK: turn 3; up to 4 turns and $1.00 (spent $0.00).", "TASK: turn 4; up to 4 turns and $1.00 (spent $0.00)."], tl_p[:4])
check("without documents the system prompt is the base contract: no READ, no documents' part",
      "READ <D1" not in Session(None, Notebook("x"), plain_llm, data_description="d").system and "DOCUMENTS." not in Session(None, Notebook("x"), plain_llm, data_description="d").system)
check("with documents the system prompt gains the Documents section before Format and the READ row in the actions table", "## Documents" in contract(True) and contract(True).index("## Documents") < contract(True).index("## Format") and "`READ D1 <what>`" in contract(True) and "[D1.17]" in contract(True) and "LOOK" not in contract(True))

# a reply that carries two actions: the first runs and the next prompt says so; pure reads before a REPORT are skipped
def act(line): return "###NOTE###\n" + NOTE5 + "\n###ACTION###\n" + line
two_prompts = []
TWO = [act("CELL\n```python\nprint('one')\n```\nCELL\n```python\nprint('two')\n```"),          # two different cells: nothing runs
       act("CELL\n```python\nprint('single')\n```"),
       act("SHOW 1\n###THINKING###\nmore\n###NOTE###\n" + NOTE5 + "\n###ACTION###\nREPORT\n## r\n\nDone [cell 1]."),  # SHOW then REPORT: nothing runs
       act("REPORT\n## r\n\nDone [cell 1].")]
two_i = {"n": 0}
def two_llm(system, user, **h):
    two_prompts.append(user)
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    i = two_i["n"]; two_i["n"] += 1
    return TWO[min(i, len(TWO) - 1)], {"cost": 0.001}
k2 = PersistentKernel(df=df); nb2_ = Notebook("t2")
try:
    r2 = Session(k2, nb2_, two_llm, data_description="d").run("q", budget=Budget(turns=5, dollars=1.0))
finally:
    k2.cleanup()
check("a reply with two different actions runs the first; the next prompt names the other and says only the first ran",
      r2.turns[0].kind == "cell" and r2.turns[0].cell_no == 1 and "(Your reply held 2 actions - CELL then CELL; only the first ran. A reply carries one action.)" in two_prompts[1]
      and "one" in (r2.turns[0].stdout or "") and "two" not in (r2.turns[0].stdout or ""), ([(x.kind, x.cell_no) for x in r2.turns], two_prompts[1][-300:]))
check("a SHOW written with a REPORT runs the SHOW alone, and the plain REPORT then ends the run",
      [x.kind for x in r2.turns if x.kind != "rewrite"][:4] == ["cell", "cell", "show", "report"] and r2.status == "answered" and "Done [cell 1]" in r2.report
      and "(Your reply held 2 actions - SHOW then REPORT; only the first ran." in two_prompts[3], ([x.kind for x in r2.turns], r2.status, two_prompts[3][-300:]))
pt = parse_turn("###NOTE###\nn\n###ACTION###\nSHOW 1 2\nNAMES\nREPORT\n## r\n\nx")[2]
check("parse_turn: SHOW and NAMES before a REPORT - the SHOW runs, the rest recorded (a report written beside other actions does not run)", pt.verb == "show" and pt.more == ("names", "report"), (pt.verb, pt.more))
pt2 = parse_turn("###NOTE###\nn\n###ACTION###\nSEARCH x\nREPORT\n## r")[2]
check("parse_turn: a SEARCH before a REPORT runs the search and records the report as not run", pt2.verb == "search" and pt2.more == ("report",), (pt2.verb, pt2.more))
pd_ = parse_turn("###NOTE###\nn\n###ACTION###\nCELL\n```python\nprint(1)\n```\n###ACTION###\nCELL\n```python\nprint(1)\n```\n###ACTION###\n```python\nprint(1)\n```")[2]
check("parse_turn: the same cell written three times (seen in a real log) runs once", pd_.verb == "cell" and pd_.arg == "print(1)", (pd_.verb, pd_.arg))
prp = parse_turn("###NOTE###\nn\n###ACTION###\nREPORT\n## Answer\n\nRead as a correction, this implies +53 s/km.\nShow this to the coach.\n\nSHOW 3 is not an action here.\n```python\nprint('quoted code')\n```")[2]
check("parse_turn: after REPORT the rest of the block is the report - prose or code in it is not another action", prp.verb == "report" and "Read as a correction" in prp.arg and "SHOW 3 is not an action here." in prp.arg and "quoted code" in prp.arg, (prp.verb, prp.more))
puf = parse_turn("###NOTE###\nn\n###ACTION###\n```python\nimport pandas as pd\nx = 1")[2]
check("parse_turn: a python block without its closing fence is not run - unfinished code does not run", puf.verb == "invalid" and "closing fence" in puf.arg, (puf.verb, puf.arg))
# the prelude: source the host wants in the kernel is there at the start of the run and again after a rollback
PRE_SCRIPT = [act("CELL\n```python\nprint(D9.name)\n```"), act("CELL\n```python\nraise ValueError('boom')\n```"), act("CELL\n```python\nprint(D9.name)\n```"), act("REPORT\n## r\n\nDone.")]
pre_n = {"n": 0}
def pre_llm(system, user, **hints):
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    i = pre_n["n"]; pre_n["n"] += 1
    return PRE_SCRIPT[min(i, len(PRE_SCRIPT) - 1)], {"cost": 0.001}
kp = PersistentKernel(df=df); nbp = Notebook("tp")
try:
    rp = Session(kp, nbp, pre_llm, data_description="d", kernel_prelude="class _D:\n    name = 'the prelude object'\nD9 = _D()").run("q", budget=Budget(turns=4, dollars=1.0))
finally:
    kp.cleanup()
lp = [x for x in rp.turns if x.kind == "cell" and not x.error]
check("kernel prelude: the host's object is in the kernel for the first cell and still there after a cell's rollback",
      len(lp) == 2 and "the prelude object" in lp[0].stdout and "the prelude object" in lp[1].stdout, [x.stdout for x in rp.turns if x.kind == "cell"])

# ---- results: RESULT: lines printed by committed cells ride in every later prompt with their cell numbers ----
RES = [act6("CELL\n```python\ne = 1.5\nRESULT('B vs A mean, 20 subjects', e, e - 1.3, e + 1.3, 'units', 'B higher')\nprint('other output')\n```"),
       act6("CELL\n```python\nprint('no result here')\n```"),
       act6("CELL\n```python\nRESULT('this one must not count - the cell fails', 1, 0, 2)\nraise ValueError('x')\n```"),
       act6("CELL\n```python\nRESULT('C vs A, 20 subjects', 6.1, 4.4, 7.7, 'bpm', 'higher')\n```"),
       act6("REPORT\n## r\n\nB is higher by +1.50 [cell 1]; C by +6.10 [cell 3].")]
res_i = {"n": 0}; res_prompts = []
def res_llm(system, user, **h):
    res_prompts.append(user)
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    i = res_i["n"]; res_i["n"] += 1
    return RES[min(i, len(RES) - 1)], {"cost": 0.001}
kr = PersistentKernel(df=df); nbr = Notebook("tr")
try:
    rr = Session(kr, nbr, res_llm, data_description="d").run("q", budget=Budget(turns=8, dollars=1.0))
finally:
    kr.cleanup()
from analyst.session import result_lines
check("results ledger: the kernel's records of committed cells, with their cell numbers, in order; a failed cell's record does not count; a number typed into the call is marked",
      result_lines(rr) == ["- [cell 1] B vs A mean, 20 subjects: +1.50 (95% CI +0.20 to +2.80) units, B higher",
                           "- [cell 3] C vs A, 20 subjects: +6.10 (95% CI +4.40 to +7.70) bpm, higher - typed: the numbers were written into the call, not computed"], result_lines(rr))
check("report guard: a number only a typed RESULT line carries is flagged as not traced to an output; a computed one is not",
      "6.1" in (rr.report[rr.report.find("CHECK"):] if "CHECK" in rr.report else "") and "1.5" not in (rr.report[rr.report.find("CHECK"):] if "CHECK" in rr.report else "x1.5"), rr.report[-500:])
check("ledger: a printed line that merely begins with RESULT: is not a record - only RESULT(...) is",
      result_lines(rn) == [] if "rn" in dir() else True)
check("results ledger: while the newest cell's output is in view whole its lines are not repeated in the ledger; they appear once that cell has aged out of the whole view, and on the report turn (2026-10-06)",
      "RESULTS SO FAR" not in res_prompts[1] and "RESULTS SO FAR (printed by your cells; the report quotes these):\n- [cell 1] B vs A mean" in res_prompts[2]
      and "- [cell 1] B vs A mean" in [p_ for p_ in res_prompts if "TASK:" in p_][-1] and "- [cell 3] C vs A" not in [p_ for p_ in res_prompts if "TASK:" in p_][-1], [p_[-250:] for p_ in res_prompts[1:3]])
check("contract: names DS and the comparison part of the report, and shows the RESULT: line with a neutral example",
      "`df = DS.load()`" in c_all and "- the comparison: what the question asks to compare, and what you compared" in c_all and "RESULT: outcome Y, group B vs group A at matched age" in c_all and "## Results" in c_all)
from analyst.session import FIGURES_LATER as FIGURES_LATER_
check("contract: cells compute and draw nothing - a figure cell is not run; the figures come after the report from one more request, one to three, or NONE - the mechanism, no advice on when; "
      "the REPORT row says the report is in the same reply; no 'step' beside the reply's STEP (2026-10-11: 'in a step of their own' had two runs end at the word REPORT)",
      "draw nothing and prepare nothing for a figure - a cell that calls `fig.show()`,\n`plt.show()` or `savefig` is not run" in c_all and "once it is written, one more\nrequest shows it to you" in c_all
      and "or NONE when a number or a table answers" in c_all and "[fig 7]" not in c_all and "where it breaks down" not in c_all
      and "| `REPORT` | The report, on the lines after it in this reply" in c_all and "step of their own" not in c_all and "step of their own" not in FIGURES_LATER_
      and "from what the\nkernel holds - the figure the question asks for, or the estimate and its uncertainty, first" in c_all and "variables your cells defined" not in c_all
      and "a request for a figure is a short report - what is drawn, from what, what it shows -\nand the figure follows" in c_all and "settles a number" in c_all and "settles a figure" not in c_all)
check("contract: the report's next steps are the person's - drawing the figures is not one (0321: two live reports began their next steps with 'Draw the figure', which the step after "
      "the report then drew)", "- two or three next steps; drawing the figures is not one\n" in c_all)
check("contract: an estimate is recorded with the kernel's RESULT(...), the words the analyst's and the numbers the cell's; a typed number is marked; a revised estimate gets a new line",
      "record it in that cell with the\nkernel's `RESULT(what, estimate, low, high, unit, direction)`" in c_all and "A number written into the call instead of computed is marked as typed" in c_all
      and "A revised estimate gets a new\nline" in c_all and "print it on one line" not in c_all)
# ---- figures (2026-10-11): a figure cell during the analysis is not run; after the report the figures step draws once from the
# kernel's variables - a failed cell corrected with its error, the section in the report, each attempt a card, the record ----
from analyst.session import parse_figures_reply, FIGURES_SYSTEM, FIGURES_ATTEMPTS, unwrap_error
from analyst.session import report_title, with_title, strip_scaffold, strip_cell_tokens, question_line, REWRITE_TASK as _RW
check("question_line: the note's 'Question as understood' content in any dressing - bulleted, bold around the heading or the line, numbered, a dash for the colon - running on to the next heading; '' without the line",
      question_line("- **Question as understood:** extend the earlier plot\n  to 45 terms\n- Best estimate so far: none yet\n- Plan: p") == "extend the earlier plot to 45 terms"
      and question_line("**Question as understood**: q2\n**Best estimate so far:** x") == "q2" and question_line("1. Question as understood: q3\n2. Best estimate so far: x") == "q3"
      and question_line("Question as understood \u2014 q5\nBest estimate so far: x") == "q5"
      and question_line(NOTE) == "is B higher than A" and question_line("- Best estimate so far: 3\n- Plan: p") == "" and question_line("") == "")
check("report_title: the report's first non-blank line when it is a level-one heading, without marks, quotes or a full stop; '' when the report opens with a lower heading or prose",
      report_title("# Two hard weeks then a taper went to plan.\n\n## What this answers") == "Two hard weeks then a taper went to plan" and report_title("\n#   **Quoted title**  ##\nbody") == "Quoted title"
      and report_title("## What this answers\n# later") == "" and report_title("Prose first\n# then") == "" and report_title("") == "")
check("with_title: the title replaces the text's own first heading or is prepended; a text without a title stays; strip_scaffold: the text after the last ###ACTION###, a leading REPORT and a stray marker dropped; strip_cell_tokens: cell citations out in any dress, the punctuation tidied",
      with_title("# Old\n\nBody", "New") == "# New\n\nBody" and with_title("Body", "New") == "# New\n\nBody" and with_title("Body", "") == "Body"
      and strip_scaffold("###STEP###\nI will rewrite.\n###NOTE###\nx\n###ACTION###\nREPORT\n\n# T\nBody") == "# T\nBody" and strip_scaffold("# T\nBody") == "# T\nBody" and strip_scaffold("###STEP###\nText only") == "Text only"
      and strip_cell_tokens("one athlete cell 14; the window is set cell 5. Shape [cells 9, 10] moved (cell 3). Fine [cell 7], ok.") == "one athlete; the window is set. Shape moved. Fine, ok."
      and strip_cell_tokens("a cell phone and cellar 7") == "a cell phone and cellar 7")
check("the contract makes the report's first line its title - a statement of what was found, twelve words at most, for a reader outside the thread - and the rewrite task keeps it as its own first line, nothing of its own before the text",
      "Its first line is its title: `# ` and what was found, twelve words at most, clear\noutside this thread; then markdown headings for its parts:" in contract(False, 0) and "The report's first line is its title (`# ...`): keep it, unchanged, as your own first line. Then the text, and nothing else." in _RW
      and "TITLE:" not in _RW and "LEAD:" not in _RW)
check("parse_figures_reply: NONE or prose is no cell; python blocks are joined in order; CAPTION lines - plain, bold, numbered, bulleted - in order",
      parse_figures_reply("NONE") == (None, []) and parse_figures_reply("no block here\nCAPTION: x") == (None, [])
      and parse_figures_reply("```python\na = 1\n```\ntext\n```py\nb = 2\n```\n**CAPTION 1:** first\n- Caption 2: second\nCAPTION: third") == ("a = 1\n\nb = 2", ["first", "second", "third"]),
      parse_figures_reply("```python\na = 1\n```\ntext\n```py\nb = 2\n```\n**CAPTION 1:** first\n- Caption 2: second\nCAPTION: third"))
check("unwrap_error: a figures cell's traceback line numbers are counted from the analyst's code, not the wrap's head",
      unwrap_error('  File "<string>", line 12, in <module>\nValueError: x') == '  File "<string>", line 5, in <module>\nValueError: x' and unwrap_error("") == "")
FIG_CELL = "import plotly.graph_objects as go\nfig = go.Figure(go.Bar(x=[1], y=[m]))\nfig.update_layout(title=f'the mean, {m:.2f}')\nfig.show()"
FIGS = [act6("CELL\n```python\nm = df['x'].mean()\nprint('mean', round(m, 3))\n```"),
        act6("CELL\n```python\nimport matplotlib.pyplot as plt\nplt.plot([1, 2]); plt.show()\n```"),          # a figure cell: not run
        act6("CELL\n```python\nprint('no figure here')\n```"),
        act6("REPORT\n## r\n\nThe mean [cell 1].")]
FIG_STEP = ["```python\n" + FIG_CELL + "\nraise ValueError('bad trace')\n```\nCAPTION: the mean",                      # fails: comes back with its error
            "Here it is.\n```python\n" + FIG_CELL + "\nfig2 = go.Figure(go.Bar(x=[2], y=[m])); fig2.update_layout(title='again'); fig2.show()\nRESULT('drawn mean', float(m), None, None)\nprint('drawn')\n```\n**CAPTION 1:** the mean with its interval"]
fig_i = {"n": 0, "f": 0}; fig_prompts = []; fig_events = []
def fig_llm(system, user, **h):
    fig_prompts.append((system, user))
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"):
        k = fig_i["f"]; fig_i["f"] += 1
        return FIG_STEP[min(k, len(FIG_STEP) - 1)], {"cost": 0.002}
    i = fig_i["n"]; fig_i["n"] += 1
    return FIGS[min(i, len(FIGS) - 1)], {"cost": 0.001}
_pp = os.environ.get("PYTHONPATH")
if "plotly" in _stubs.FAKE:                  # the kernel's worker imports plotly: the stack's stand-in where the real one is absent
    os.environ["PYTHONPATH"] = os.path.join(ROOT, "tools", "stack", "fakepkgs") + (os.pathsep + _pp if _pp else "")
kf = PersistentKernel(df=df); nbf = Notebook("tf")
try:
    rf = Session(kf, nbf, fig_llm, data_description="d", emit=fig_events.append, kernel_factory=lambda: PersistentKernel(df=df)).run("q", budget=Budget(turns=8, dollars=1.0), mode="Deep")
finally:
    kf.cleanup()
    if _pp is None: os.environ.pop("PYTHONPATH", None)
    else: os.environ["PYTHONPATH"] = _pp
analysis_prompts = [u for s_, u in fig_prompts if not s_.startswith("You are drawing") and not u.startswith("Rewrite")]
step_prompts = [u for s_, u in fig_prompts if s_.startswith("You are drawing")]
check("figures: a cell that draws during the analysis is not run - no cell number, its output says figures come after the report, the refusal reaches the next prompt - and the run goes on",
      rf.turns[1].kind == "cell" and rf.turns[1].cell_no is None and not rf.turns[1].error and "Figures come after the report" in rf.turns[1].stdout
      and any("Figures come after the report" in u for u in analysis_prompts) and [x.cell_no for x in rf.cells() if not x.step] == [1, 2] and rf.status == "answered",
      [(x.kind, x.cell_no, x.step) for x in rf.turns])
step_turns = [x for x in rf.turns if x.step == "figures"]
check("figures: the step after the report - its first cell failed and is on the record with its error and no number; the corrected cell committed as cell 3 with the two Plotly figures it showed",
      len(step_turns) == 2 and step_turns[0].error and step_turns[0].cell_no is None and step_turns[1].cell_no == 3 and not step_turns[1].error
      and step_turns[1].figures == [{"plotly": True, "title": f"the mean, {df['x'].mean():.2f}"}, {"plotly": True, "title": "again"}] and step_turns[1].stdout.strip().endswith("drawn")
      and "FIGURES:" not in step_turns[1].stdout, [(x.cell_no, x.error[-80:], x.figures, x.stdout) for x in step_turns])
check("figures: the failed cell came back with its error, the attempt counted, the traceback's line in the analyst's own code (line 5, not the wrap's)",
      len(step_prompts) == 2 and "YOUR LAST CELL FAILED" in step_prompts[1] and f"attempt 1 of {FIGURES_ATTEMPTS}" in step_prompts[1] and "ValueError: bad trace" in step_prompts[1]
      and "in your cell, line 5:  raise ValueError" in step_prompts[1] and "YOUR LAST CELL FAILED" not in step_prompts[0], step_prompts[1][-500:])
check("figures: the step's prompt carries the question, the report as written, every cell's code, the RESULT lines and the note",
      "QUESTION:\nq" in step_prompts[0] and "THE REPORT, AS WRITTEN:\n## r" in step_prompts[0] and "--- cell 1 ---" in step_prompts[0] and "--- cell 2 ---" in step_prompts[0]
      and "YOUR NOTE" in step_prompts[0] and "THE CELLS (their code" in step_prompts[0], step_prompts[0][:600])
check("figures: the report gains a Figures section citing the figures cell - a caption written for the first, the second named by its title - and the rewrite saw it",
      rf.report.split("\n\n> ")[0].endswith("## Figures\n\n- [fig 3] the mean with its interval\n- [fig 3] again")
      and "## Figures" in [u for s_, u in fig_prompts if u.startswith("Rewrite")][0], rf.report)
fig_cards = [(e["type"], e.get("attempt"), e.get("peek"), e.get("quiet")) for e in fig_events if e.get("turn") == "figures" and e["type"] in ("turn_start", "turn_end")]
check("figures: each attempt is a quiet card - 'figures' with its attempt number - whose end line says what the cell draws; then its cell row",
      fig_cards == [("turn_start", 1, None, True), ("turn_end", None, "figure cell: the mean", None), ("turn_start", 2, None, True), ("turn_end", None, "figure cell: the mean with its interval", None)]
      and [e["type"] for e in fig_events if e.get("turn") == "figures"] == ["turn_start", "turn_end", "cell_start", "turn_start", "turn_end", "cell_start"], fig_cards)
check("figures: the replay ran the figures cell and reproduced the report; the step's turns round-trip through JSON with their step",
      rf.replay_status == "reproduced" and "# --- cell 3 ---" in rf.replay_script and "fig.show()" in rf.replay_script
      and Notebook.from_dict(json.loads(json.dumps(nbf.to_dict()))).runs[rf.id].turns[-2].step == "figures", (rf.replay_status, rf.replay_script[-300:]))
# the record for the code trace (2026-10-20): each committed cell keeps the registry entries it made or changed, a RESULT record
# its cell line (the figures cell's counted from the analyst's own code, not the wrap's), the run its mode; an older record
# without these loads with their defaults
_c1, _c2, _c3 = rf.cells()[0], rf.cells()[1], step_turns[1]
check("record: a committed cell keeps the kernel's registry entries for the names it made - type and description (a numpy number shows its type: the registry's text is what the analyst reads through NAMES and is not changed) - "
      "and nothing for a cell that bound no name; the figures cell keeps its figures' names; a name unchanged by a later cell is not kept again",
      set(_c1.registry) == {"m"} and _c1.registry["m"]["type"] == "float64" and _c2.registry == {} and set(_c3.registry) == {"fig", "fig2"} and "m" not in _c3.registry
      and _c3.registry["fig"]["type"] == "Figure", (_c1.registry, _c2.registry, sorted(_c3.registry)))
check("record: the figures cell's RESULT record carries its line in the analyst's own code - line 6 of the cell, not line 13 of the wrapped one; a failed cell keeps no registry; the run keeps the mode it was asked in; the map was built at the end (M3)",
      [r.get("line") for r in _c3.results] == [6] and step_turns[0].registry == {} and rf.mode == "Deep" and rf.code_map.get("view", {}).get("chain_id") == rf.id and "error" not in rf.code_map,
      (_c3.results, rf.mode, {k_: v for k_, v in rf.code_map.items() if k_ != "view"}))
_old = json.loads(json.dumps(nbf.to_dict()))
for _r in _old["runs"].values():
    _r.pop("mode", None); _r.pop("code_map", None)
    for _t in _r["turns"]:
        _t.pop("registry", None)
        for _k in _t.get("results") or []: _k.pop("line", None)
_nb_old = Notebook.from_dict(_old)
check("record: a thread file from before the code trace loads - no registry on its turns, no line on its records, no mode and no map on its runs - with the defaults",
      _nb_old.runs[rf.id].turns[0].registry == {} and _nb_old.runs[rf.id].mode == "" and _nb_old.runs[rf.id].code_map == {} and "line" not in (_nb_old.runs[rf.id].cells()[0].results or [{}])[0] if _nb_old.runs[rf.id].cells()[0].results else True)
check("figures: a run whose step answers NONE has no Figures section and no figures turn; a cell count excludes the step's cells only by their step mark",
      "## Figures" not in rr.report and not [x for x in rr.turns if x.step] and len([x for x in rf.turns if x.kind == "cell" and not x.step]) == 3, rr.report[-200:])
# every other outcome of the figures request (2026-10-11, from a run whose request spent 16,000 reasoning tokens and sent nothing,
# taken for NONE): a cut reply, an empty one, prose without a block, a cell that fails every time - each an attempt that is
# asked again, on the record, and the report says the figures were not drawn and why; NONE in markdown still declines
from analyst.session import FIGURES_CUT, FIGURES_NO_BLOCK, answers_none, figures_outcome
def _fig_run(replies, name):
    """A two-cell analysis whose figures request answers from `replies` in order (text, usage)."""
    seqs = {"n": 0, "f": 0}; prompts = []
    def llm(system, user, **h):
        if user.startswith("Rewrite"): return "plain", {"cost": 0}
        if system.startswith("You are drawing the figures"):
            prompts.append(user); k = seqs["f"]; seqs["f"] += 1
            return replies[min(k, len(replies) - 1)]
        k = seqs["n"]; seqs["n"] += 1
        return [act6("CELL\n```python\nm = df['x'].mean()\nprint('mean', round(m, 3))\n```"), act6("REPORT\n## r\n\nThe mean [cell 1].")][min(k, 1)], {"cost": 0.001}
    kk = PersistentKernel(df=df); nn = Notebook(name); evs = []
    try:
        rr_ = Session(kk, nn, llm, data_description="d", emit=evs.append).run("q", budget=Budget(turns=6, dollars=1.0))
    finally:
        kk.cleanup()
    return rr_, prompts, evs
_r_cut, _p_cut, _e_cut = _fig_run([("", {"cost": 0.02, "truncated": True})], "tfc")
check("figures: a reply cut at the length limit with no cell is an attempt - asked again for a shorter cell, four times in all, each on the record as a lost turn of the step; the report says the figures were not drawn and why; the pane never says a number answered",
      len(_p_cut) == 4 and all("YOUR LAST REPLY WAS CUT OFF" in p_ for p_ in _p_cut[1:]) and "attempt 1 of 4" in _p_cut[1] and "attempt 3 of 4" in _p_cut[3]
      and [t.kind for t in _r_cut.turns if t.step == "figures"] == ["error"] * 4 and "cut off at the length limit" in [t.stdout for t in _r_cut.turns if t.step == "figures"][0]
      and "> The figures were not drawn: the reply was cut off at the length limit before a cell arrived 4 times." in _r_cut.report and "## Figures" not in _r_cut.report
      and [e.get("peek") for e in _e_cut if e.get("turn") == "figures" and e["type"] == "turn_end"] == ["the reply was cut off at the length limit before a cell arrived"] * 4
      and _r_cut.status == "answered", (_r_cut.report[-300:], [e.get("peek") for e in _e_cut if e.get("turn") == "figures" and e["type"] == "turn_end"]))
_r_prose, _p_prose, _e_prose = _fig_run([("Here is a figure: fig = go.Figure(); fig.show()", {"cost": 0.01}),
                                         ("```python\nimport matplotlib.pyplot as plt\nplt.bar(['a'], [m]); plt.title(f'the mean, {m:.2f}'); plt.show()\n```\nCAPTION: the mean", {"cost": 0.01})], "tfp")
check("figures: prose without a block is an attempt - told to reply with a block or NONE - and the next reply's cell is drawn",
      len(_p_prose) == 2 and "carried no python block and was not NONE" in _p_prose[1] and FIGURES_NO_BLOCK.split(" (")[0] in _p_prose[1]
      and [t.kind for t in _r_prose.turns if t.step == "figures"] == ["error", "cell"] and "## Figures\n\n- [fig 2] the mean" in _r_prose.report and "not drawn" not in _r_prose.report, (_r_prose.report[-200:], [(t.kind, t.cell_no) for t in _r_prose.turns if t.step == "figures"]))
# the data changed between a chain and its follow-up (2026-10-12): the follow-up's figures request sees its own cells only (the
# earlier chain's variables are not in its kernel), its replay re-runs its own cells only, and the ledger says the earlier chain is on other data
_bp = []
def _bllm(system, user, **h):
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"):
        _bp.append(user); return "NONE", {"cost": 0}
    _bp.append(user)
    return [act6("CELL\n```python\nw = len(df)\nprint('rows', w)\n```"), act6("REPORT\n## r\n\nThe rows [cell 2].")][min(sum(1 for x in _bp if "TASK: turn" in x) - 1, 1)], {"cost": 0.001}
_nbb = Notebook("tb"); _kb1 = PersistentKernel(df=df)
try:
    _rb1 = Session(_kb1, _nbb, thread_llm_factory(["###NOTE###\n" + NOTE5 + "\n###ACTION###\nCELL\n```python\nm = df['x'].mean()\nprint('mean', round(m, 3))\n```", "###NOTE###\n" + NOTE5 + "\n###ACTION###\nREPORT\n## r\n\nThe mean [cell 1]."]),
                   data_description="d", kernel_factory=lambda: PersistentKernel(df=df)).run("first", budget=Budget(turns=4, dollars=1.0), data={"df_id": "A", "name": "a.csv", "rows": 200})
finally:
    _kb1.cleanup()
_df_b = df.head(50).copy(); _kb2 = PersistentKernel(df=_df_b)        # the data replaced: a fresh kernel, as the app gives a follow-up after a change
try:
    _rb2 = Session(_kb2, _nbb, _bllm, data_description="d2", kernel_factory=lambda: PersistentKernel(df=_df_b)).run("second, on other data", parent=_rb1.id, budget=Budget(turns=4, dollars=1.0), data={"df_id": "B", "name": "b.csv", "rows": 50})
finally:
    _kb2.cleanup()
_fig_prompt = next(x for x in _bp if x.startswith("QUESTION:") and "THE CELLS" in x)
check("a follow-up on other data: its cell is numbered along the path (2), the ledger marks the first chain as on other data, the figures request lists its own cell only, the replay re-runs its own cell only and reproduces",
      _rb2.cells()[0].cell_no == 2 and "rows 50" in _rb2.cells()[0].stdout and "On other data (a.csv, 200 rows)" in _bp[0] and "its cell 1 is not in the kernel" in _bp[0]
      and "--- cell 2 ---" in _fig_prompt and "--- cell 1 ---" not in _fig_prompt and "df['x'].mean()" not in _rb2.replay_script and "w = len(df)" in _rb2.replay_script
      and _rb2.replay_status == "reproduced" and "(1 cells, " in _rb2.report, (_rb2.replay_status, _rb2.report[-200:], _fig_prompt[:300]))
_r_none, _p_none, _e_none = _fig_run([("**NONE.**\n\nA single number answers.", {"cost": 0.01})], "tfn")
check("figures: NONE in markdown declines - one call, no turn of the step, no Figures section and no 'not drawn' line",
      len(_p_none) == 1 and not [t for t in _r_none.turns if t.step == "figures"] and "## Figures" not in _r_none.report and "not drawn" not in _r_none.report
      and [e.get("peek") for e in _e_none if e.get("turn") == "figures" and e["type"] == "turn_end"] == ["no figure: a number or a table answers"], _r_none.report[-200:])
_r_bad, _p_bad, _e_bad = _fig_run([("```python\nraise KeyError('col')\n```\nCAPTION: x", {"cost": 0.01})], "tfb")
check("figures: a cell that fails every time - four attempts, each with the error, the report says the figures were not drawn and names the last error",
      len(_p_bad) == 4 and "attempt 3 of 4" in _p_bad[3] and "KeyError" in _p_bad[1] and [t.kind for t in _r_bad.turns if t.step == "figures"] == ["cell"] * 4
      and all(t.error and t.cell_no is None for t in _r_bad.turns if t.step == "figures")
      and "> The figures were not drawn: the figure cell failed 4 times (last: KeyError: 'col')." in _r_bad.report, _r_bad.report[-300:])
check("figures_outcome / answers_none: one reason as it is; the same reason counted with the last detail; mixed reasons by their count; NONE bare or dressed, not a sentence starting with none",
      figures_outcome(["a"]) == "a" and figures_outcome(["the figure cell failed (E1)", "the figure cell failed (E2)"]) == "the figure cell failed 2 times (last: E2)"
      and figures_outcome(["x", "y (z)"]) == "after 2 attempts (last: y (z))" and answers_none("none") and answers_none("- NONE -") and not answers_none("None of these") and not answers_none(""))
check("figures: the system prompt names the two replies, the f-string rule and the three corrections; nothing task-specific",
      "the single word NONE" in FIGURES_SYSTEM and "one Python cell" in FIGURES_SYSTEM and "CAPTION:" in FIGURES_SYSTEM and "f-string" in FIGURES_SYSTEM
      and "three times at most" in FIGURES_SYSTEM and not re.findall(r"\b(athlete|driver|altitude|sea level|hr_max|race|F1|Formula)\b", FIGURES_SYSTEM, re.I))

# ---- the kernel's DS: the dataset recoverable, the df check in a step's output ----
kd = PersistentKernel(df=df)
try:
    o1 = kd.execute("print(DS)\nprint(DS.load().shape)")[0]
    o2 = kd.execute("df = df.head(5)\nprint(df.shape)")[0]
    o3 = kd.execute("for nm, df, t in [('x', df[[df.columns[0]]], 1)]:\n    pass\nprint('done')")[0]
    o4 = kd.execute("df = DS.load()\nprint(df.shape)")[0]
finally:
    kd.cleanup()
check("DS: the kernel holds the dataset as attached - DS.load() returns a fresh frame of the original shape", "DS: the dataset as attached" in o1 and f"({len(df)}, {df.shape[1]})" in o1, o1[:120])
kk = PersistentKernel(df=df)
try:
    o_star = kk.execute("def est(): return (0.5, 0.1, 0.9)\nRESULT('starred', *est()[:3], 'units', 'up')\nRESULT('kw', estimate=1, low=0, high=2)")[0]
finally:
    kk.cleanup()
check("RESULT: a starred argument of computed values is not marked typed - the unit and direction strings in the numeric slots do not count (2026-10-06: thirteen lines wrongly marked); a literal keyword estimate is",
      "RESULT: starred: +0.50 (95% CI +0.10 to +0.90) units, up" in o_star and "typed" not in o_star.splitlines()[0] and "RESULT: kw: +1 (95% CI +0 to +2) - typed" in o_star, o_star)
check("DS: a row filter of df raises no warning; columns lost raise the one-line warning naming DS.load(); the restore is clean",
      "DS.load()" not in o2 and "of the dataset's" in o3 and "DS.load() restores" in o3 and "DS.load()" not in o4 and f"({len(df)}, {df.shape[1]})" in o4, (o2, o3, o4))

# ---- the replay (2026-10-05): DS exists in the replayed script; combined citations and [fig n] are read
from analyst.replay import assemble as _assemble
from analyst.report import cited_cells as _rep_cited, referenced_figures as _rep_figs
_cells = [Turn(kind="cell", cell_no=1, code="a = 1\nprint('one', a)", stdout="one 1"), Turn(kind="cell", cell_no=2, code="b = 2\nprint('two', b)", stdout="two 2"),
          Turn(kind="cell", cell_no=3, code="df = DS.load()\nprint('rows', len(df))", stdout="rows 5"), Turn(kind="cell", cell_no=4, code="print('four')", stdout="four")]
_script, _order = _assemble(_cells, "Found it [cell 1, cell 2] and drew it [fig 3].")
check("replay: a figure cited as [fig 3] and cells cited together as [cell 1, cell 2] decide how far the replay runs - cells 1 to 3, not 4",
      "print('rows', len(df))" in _script and "print('four')" not in _script and _rep_cited("[cell 1, cell 2] [cells 6-8] [cells 9, 11]") == [1, 2, 6, 7, 8, 9, 11]
      and _rep_figs("[fig 3] [figs 4, 5]") == [3, 4, 5], (_order, _rep_cited("[cell 1, cell 2] [cells 6-8] [cells 9, 11]")))
_g = {"df": pd.DataFrame({"x": range(5)})}
try:
    import contextlib as _cl, io as _io
    with _cl.redirect_stdout(_io.StringIO()) as _out:
        exec(_script, _g)
    _ran = _out.getvalue()
except Exception as _exc:                                                   # noqa: BLE001
    _ran = f"FAILED: {_exc!r}"
check("replay: the assembled script defines DS, so a cell that calls DS.load() runs in a plain script as in the kernel (2026-10-05: it had stopped the replay before the figures)",
      "rows 5" in _ran, _ran[-300:])

# the replayed script defines RESULT when the runtime has none, printing the kernel's line exactly (2026-10-06: a replay
# had stopped with NameError: name 'RESULT' is not defined)
_rcode = ("e = float(len(df)) / 10\nRESULT('a, rows', e, e - 1.3, e + 1.3, 'units', 'up')\nRESULT('slope', -0.051, -0.143, 0.040, 'min/km', test='after turn 8')\n"
          "x = 0.0023\nRESULT('tiny', x, x / 2, x * 2, corrects=[1, 2])\nRESULT('big', 15156.7, 14000.2, 16300.9, 's')\nRESULT('text', '+6.1')")
_krn = PersistentKernel(df=df)
try:
    _kout = _krn.execute(_rcode)[0]
finally:
    _krn.cleanup()
_rscript, _ = _assemble([Turn(kind="cell", cell_no=1, code=_rcode, stdout=_kout)], "see [cell 1]")
_rg = {"df": df.copy()}
with _cl.redirect_stdout(_io.StringIO()) as _rout:
    exec(_rscript, _rg)
_lines = lambda t: [ln.split(" - typed:")[0] for ln in t.splitlines() if ln.startswith("RESULT:")]
check("replay: a replayed cell's RESULT(...) runs where the runtime has no kernel, and prints the kernel's line to the character (the typed mark aside, which the ledger does not take from the replay)",
      _lines(_kout) == _lines(_rout.getvalue()) and len(_lines(_kout)) == 5, (_lines(_kout), _lines(_rout.getvalue())))

# the replay prints what the kernel printed (2026-10-08): the assembled script sets the kernel's display options, so a
# wide frame is not elided and floats keep the kernel's four significant digits; the numbers check reads e-notation at
# its own precision. The Sonnet 5.5 run's "4 of 235 cited numbers did not reappear" was exactly this: 2532 lost to an
# elided crosstab, 1.49e+04 printed as 14901.6 by the plain executor
from analyst.replay import compare as _compare
from analyst.report import _present as _rp
_wcode = ("ct = pd.DataFrame([[4096, 1873, 2655, 2468, 2532, 2145, 1450], [64, 813, 0, 0, 0, 0, 0]], index=pd.Index([0, 1], name='abroad'),"
          " columns=['NA', 'asphalt', 'dirt_trail', 'grass_xc', 'mixed_asphalt_gravel', 'mixed_track_gravel', 'synthetic_track'])\n"
          "med = pd.DataFrame({'spd': [3.63, 4.165], 'session_distance_m': [14901.6, 14011.2]})\nprint(ct); print(med)")
_wk = PersistentKernel(df=df)
try:
    _wout = _wk.execute(_wcode)[0]
finally:
    _wk.cleanup()
_wcell = [Turn(kind="cell", cell_no=1, code=_wcode, stdout=_wout)]
_wscript, _ = _assemble(_wcell, "see [cell 1]")
_defaults = {"display.max_columns": 0, "display.width": 80, "display.max_colwidth": 50, "display.max_rows": 60, "display.float_format": None}
_after = {}
def _run_plain(script):
    # as the executor route runs it: pandas at its defaults (max_columns 0 - fit the console width by eliding columns, as the
    # executor's print of the crosstab did), the script free to set options (undone after, for the next test)
    with pd.option_context(*[x for kv in _defaults.items() for x in kv]):
        with _cl.redirect_stdout(_io.StringIO()) as _b:
            exec(script, {"df": df.copy()})
        _after.clear(); _after.update({k: pd.get_option(k) for k in _defaults})
        return _b.getvalue()
_bare = _run_plain("\n".join(ln for ln in _wscript.splitlines() if not ln.startswith("pd.set_option(")))
_same = _run_plain(_wscript)
from analyst.replay import RESET_OPTIONS as _reset
check("replay: the script's last lines reset the five options, so the executor's process keeps its own formatting for the data views; the app sends the same reset when a replay stopped early",
      _wscript.rstrip().endswith(_reset) and _after["display.float_format"] is None and _after["display.max_rows"] == 60 and _after["display.max_columns"] is not None
      and _reset.count("pd.reset_option(") == 5 and "display.float_format" in _reset, (_after, _wscript[-300:]))
check("replay: without the kernel's display options the plain executor elides the crosstab and prints 14901.6 for 1.49e+04 - the check would say numbers did not reappear",
      "1.49e+04" in _wout and "2532" in _wout and "..." in _bare and "14901.6" in _bare and _compare(_wcell, "see [cell 1]", _bare)[0] == "differed", (_wout, _bare))
check("replay: the assembled script sets the kernel's display options, so the replay's output is the kernel's and the check says reproduced",
      _same == _wout and _compare(_wcell, "see [cell 1]", _same)[0] == "reproduced", (_wout, _same))
import ast as _ast_k
_kopts = sorted(ln.strip() for ln in open(os.path.join(ROOT, "delve", "kernel.py")).read().splitlines() if ln.strip().startswith('pd.set_option("display.'))   # the ones the worker starts with, by name
_ropts = sorted(ln.strip() for ln in _wscript.splitlines() if ln.strip().startswith("pd.set_option("))
check("replay: the script's display options are the kernel's, option for option (delve/kernel.py is the one source)",
      len(_kopts) == 5 and [x.replace("'", '"') for x in _ropts] == [x.replace("'", '"') for x in _kopts], (_kopts, _ropts))
check("numbers: a value printed in e-notation matches its full value at the mantissa's precision (1.49e+04 ~ 14901.6, 1.401e+04 ~ 14011.2), and not a different one",
      _rp("1.49e+04", "x 14901.6 y") and _rp("1.401e+04", "14011.2") and _rp("2.5e-3", "0.0025") and not _rp("1.49e+04", "15001.0") and not _rp("2.5e-3", "0.0031") and _rp("1018", "1017.71"))

# the one-liners (2026-10-06): what a cell was for comes from the analyst's account of the step, what came out from a
# printed fact; a failed attempt the same way; code is read only when there is no account
from analyst.notebook import step_sentence, purpose_of, Notebook as _NB
_t_ok = Turn(kind="cell", cell_no=7, thinking="Cell 6 printed the venue table. Now I fit the within-athlete regression of pace on altitude, clustered by session.",
             code="import pandas as pd\nm = fit(u)", stdout="laps for model: 14946\nRESULT: slope, pooled: +0.59 (95% CI +0.49 to +0.69) min/km",
             results=[{"text": "slope, pooled: +0.59 (95% CI +0.49 to +0.69) min/km", "typed": False, "test": None, "corrects": None}])
_t_fail = Turn(kind="cell", thinking="The last cell gave the table. Now I refit with surface held fixed.", code="import numpy as np\nx = 1/0", error="Traceback...\nZeroDivisionError: division by zero")
_t_bare = Turn(kind="cell", cell_no=2, thinking="", code="import pandas as pd\npd.set_option('display.width', 200)\nprint(df.groupby('arm').size())", stdout="arm\nA 100\nB 100")
check("one-liner: a collapsed cell is described by the step the analyst wrote (second sentence on) and by its first RESULT line",
      _NB.headline(_t_ok) == "[cell 7] Now I fit the within-athlete regression of pace on altitude, clustered by session.  ->  RESULT: slope, pooled: +0.59 (95% CI +0.49 to +0.69) min/km", _NB.headline(_t_ok))
check("one-liner: a failed attempt - the step it tried, then the error", purpose_of(_t_fail) == "Now I refit with surface held fixed." and _NB.headline(_t_fail).endswith("->  ERROR: ZeroDivisionError: division by zero"), _NB.headline(_t_fail))
check("one-liner: without an account the code's first working statement stands, never an import or an option line",
      purpose_of(_t_bare) == "print(df.groupby('arm').size())" and _NB.headline(_t_bare).endswith("->  arm"), (purpose_of(_t_bare), _NB.headline(_t_bare)))
check("step_sentence: an abbreviation is not a sentence end - (e.g. X), i.e., vs. - and the step stays whole",
      step_sentence("The ladder (e.g. Jan Meda at 4.5 vs. Kality at 3.8) says it is venue, i.e. not altitude. This turn I test the Ethiopia slope.") == "This turn I test the Ethiopia slope.",
      step_sentence("The ladder (e.g. Jan Meda at 4.5 vs. Kality at 3.8) says it is venue, i.e. not altitude. This turn I test the Ethiopia slope."))
check("step_sentence: a one-sentence account is the step itself; a long one is cut at a word", step_sentence("Just this one sentence.") == "Just this one sentence." and step_sentence("First. " + "word " * 60).endswith("...") and len(step_sentence("First. " + "word " * 60)) <= 114)

# the replay runs to the run's last figure cell too (2026-10-06): a figure drawn after the last cell the report cites
_fig_turns = [Turn(kind="cell", cell_no=1, code="x = 1\nprint('RESULT: x')", stdout="RESULT: x"),
              Turn(kind="cell", cell_no=2, code="print('estimate', x)", stdout="estimate 1"),
              Turn(kind="cell", cell_no=3, code="import matplotlib.pyplot as plt\nplt.plot([1, 2])\nplt.show()", stdout="", figures=[{"name": "f"}])]
_scr_a, _ = _assemble(_fig_turns, "The estimate is 1 [cell 2].")
_scr_b, _ = _assemble(_fig_turns[:2], "The estimate is 1 [cell 2].")
check("replay: the assembled script runs to the run's last figure cell when the report cites only earlier cells; without a later figure it stops at the last cited cell",
      "plt.plot([1, 2])" in _scr_a and "# --- cell 3" in _scr_a and "# --- cell 3" not in _scr_b and "or this run's last figure cell" in _scr_a, (_scr_a[-300:], _scr_b[-200:]))

# a reply cut at the length limit (2026-10-06): the usage says truncated, and the next prompt says cut off, not "no valid action"
tr_prompts = []
def truncated_llm(system, user, **h):
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    tr_prompts.append(user)
    if len(tr_prompts) == 1:
        return "###THINKING###\nA long think.\n###NOTE###\n- Question as understood: q\n- Best estimate so far: none", {"cost": 0.01, "truncated": True}
    return act6("REPORT\n## r\n\nDone."), {"cost": 0.001}
ktr = PersistentKernel(df=df); nbtr = Notebook("ttr")
try:
    rtr = Session(ktr, nbtr, truncated_llm, data_description="d").run("q", budget=Budget(turns=4, dollars=1.0, review_every=0))
finally:
    ktr.cleanup()
check("a reply cut at the length limit: the next prompt says so, and nothing ran",
      "Your last reply was cut off at the length limit before it reached an action; nothing ran." in tr_prompts[1] and "no valid action" not in tr_prompts[1] and rtr.status == "answered", tr_prompts[1][-300:])

# a request the provider's classifier declined before any text (2026-10-08, Claude Sonnet 5.5): the usage names the
# category, the next prompt says what happened - not "no valid action", which had the analyst re-send the same SHOW three
# times - the turn is a lost one in the record, and the run goes on
dc_prompts = []
def declined_llm(system, user, **h):
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    dc_prompts.append(user)
    if len(dc_prompts) == 1:
        return "[claude-x declined this request: stop_reason refusal, reasoning_extraction]", {"cost": 0.01, "declined": "reasoning_extraction"}
    return act6("REPORT\n## r\n\nDone."), {"cost": 0.001}
kdc = PersistentKernel(df=df); nbdc = Notebook("tdc")
try:
    rdc = Session(kdc, nbdc, declined_llm, data_description="d").run("q", budget=Budget(turns=4, dollars=1.0, review_every=0))
finally:
    kdc.cleanup()
check("a request the provider declined: the next prompt names it and its category, nothing ran, the turn is recorded as lost, and the run goes on",
      "Your last reply did not arrive: the provider declined the request before any text (reasoning_extraction). Nothing ran; reply again." in dc_prompts[1]
      and "no valid action" not in dc_prompts[1] and rdc.turns[0].kind == "error" and rdc.status == "answered", (dc_prompts[1][-300:], [t.kind for t in rdc.turns]))

# the effort of the report turn and of a second attempt (2026-10-18: at the seat's xhigh a Claude 5.5 analyst thought through
# its whole allowance on the report turn and sent nothing, and the re-ask, the same call again, did the same)
from analyst.session import attempt_effort, REPORT_EFFORT
check("attempt_effort: the report turn asks for medium, else high; the call after a lost reply asks for the levels under the one it was asked at, nearest first, that one last; both - the lower; neither - the seat's own",
      attempt_effort(True) == ("medium", "high") == REPORT_EFFORT and attempt_effort(False, "xhigh") == ("high", "medium", "low", "minimal", "none", "xhigh")
      and attempt_effort(True, "medium") == ("low", "minimal", "none", "medium") and attempt_effort(True, "xhigh") == REPORT_EFFORT
      and attempt_effort(False) is None and attempt_effort(False, "none") is None and attempt_effort(False, "?") is None)
ef_asks = []
def effort_llm(system, user, **h):
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    ef_asks.append(h.get("effort"))
    return [("", {"cost": 0.01, "truncated": True, "effort": "xhigh"}),                     # turn 1: thought away its allowance
            (act6("CELL\n```python\nprint('n', len(df))\n```"), {"cost": 0.01, "effort": "high"}),
            ("", {"cost": 0.01, "truncated": True, "effort": "medium"}),                    # turn 3, the report turn: lost too
            (act6("REPORT\n## r\n\nThe rows [cell 1]."), {"cost": 0.01, "effort": "low"})][min(len(ef_asks) - 1, 3)]
hf_asks = []
def halt_llm(system, user, **h):
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    hf_asks.append(h.get("effort"))
    return (act6("CELL\n```python\nraise ValueError('no')\n```") if len(hf_asks) <= 2 else act6("REPORT\n## r\n\nNothing stood.")), {"cost": 0.01}
kef = PersistentKernel(df=df); nbef = Notebook("tef")
try:
    ref = Session(kef, nbef, effort_llm, data_description="d").run("q", budget=Budget(turns=3, dollars=1.0, review_every=0))
    rhf = Session(kef, Notebook("thf"), halt_llm, data_description="d").run("q", budget=Budget(turns=6, dollars=1.0, review_every=0, max_failures=2))
finally:
    kef.cleanup()
check("the effort asked turn by turn: the seat's own; after the lost reply, the levels under xhigh; the report turn medium; the forced report after its lost reply, the levels under medium - and the report stands; the report forced by failed cells asks for medium",
      ef_asks == [None, attempt_effort(False, "xhigh"), REPORT_EFFORT, attempt_effort(True, "medium")] and ref.status == "answered" and "The rows" in ref.report
      and hf_asks == [None, None, REPORT_EFFORT] and "Nothing stood" in rhf.report, (ef_asks, ref.status, hf_asks))

# DS.save (2026-10-06): a dataset for the person lands in the generated-datasets folder the kernel was given, with one
# printed line; the replayed script's stub does the same into the folder the route passes
_gtmp = tempfile.mkdtemp(); _gdir = os.path.join(_gtmp, "datasets", "u1", "generated")
_gk = PersistentKernel(df=df, generated_dir=_gdir)
try:
    _gout, _gerr, _ = _gk.execute("m = df.head(7)\np = DS.save(m, 'Merged laps.csv')\nprint(p)")
finally:
    _gk.cleanup()
check("DS.save: the file is written under the kernel's generated folder with a safe name, the line says rows, columns and where it is, the path is returned",
      not _gerr and os.path.isfile(os.path.join(_gdir, "Merged_laps.csv")) and "DATASET: Merged_laps.csv - 7 rows x " in _gout and "in the Dataset cache under Generated" in _gout
      and _gout.strip().endswith(os.path.join(_gdir, "Merged_laps.csv")), (_gerr, _gout))
_gscript, _ = _assemble([Turn(kind="cell", cell_no=1, code="m = df.head(7)\nDS.save(m, 'Merged laps.csv')", stdout="x")], "see [cell 1]")
_gg = {"df": df.copy(), "_generated_dir": os.path.join(_gtmp, "replay")}
with _cl.redirect_stdout(_io.StringIO()) as _gbuf:
    exec(_gscript, _gg)
_fk = PersistentKernel(df=df, generated_dir=os.path.join(_gtmp, "fmt"))
try:
    _fout, _ferr, _ = _fk.execute("DS.save(df.head(4), 'm.json')\nDS.save(df.head(4), 'm.txt')\nDS.save(df.head(4), 'tab', fmt='tsv')\nDS.save('a note', 'notes.txt')\nDS.save(df.head(4), 'Up Case.CSV')")
finally:
    _fk.cleanup()
check("DS.save: the format follows the name's extension (json as records, txt/tsv tab-separated, csv by default), a string is a text file, and the extension's case is kept lower",
      not _ferr and sorted(os.listdir(os.path.join(_gtmp, "fmt"))) == ["Up_Case.csv", "m.json", "m.txt", "notes.txt", "tab.tsv"]
      and open(os.path.join(_gtmp, "fmt", "m.json")).read().lstrip().startswith("[") and "\t" in open(os.path.join(_gtmp, "fmt", "m.txt")).readline()
      and open(os.path.join(_gtmp, "fmt", "notes.txt")).read() == "a note" and "DATASET: notes.txt - 6 characters" in _fout, (_ferr, _fout, os.listdir(os.path.join(_gtmp, "fmt"))))
_nk = PersistentKernel(df=None, generated_dir=os.path.join(_gtmp, "nodf"))
try:
    _nout, _nerr, _ = _nk.execute("print(DS)\nx = DS.load()\nprint('load ->', x)\nimport pandas as pd\nDS.save(pd.DataFrame({'n': range(3)}), 'seq.json')\nDS.save('0 1 1', 'seq.txt')")
finally:
    _nk.cleanup()
check("DS exists in a run with no dataset attached (2026-10-06: a dataset-less run spent twelve turns hunting for DS.save): load says there is nothing to load, save still saves",
      not _nerr and "DS: no dataset attached to this run" in _nout and "nothing to load" in _nout and "load -> None" in _nout
      and sorted(os.listdir(os.path.join(_gtmp, "nodf"))) == ["seq.json", "seq.txt"], (_nerr, _nout))
check("DS.save in the replayed script: the stub writes into the folder the route passes and prints the kernel's line",
      os.path.isfile(os.path.join(_gtmp, "replay", "Merged_laps.csv")) and "DATASET: Merged_laps.csv - 7 rows x " in _gbuf.getvalue(), (_gbuf.getvalue()[-200:], os.listdir(_gtmp)))
_nscript, _ = _assemble([Turn(kind="cell", cell_no=1, code="x = DS.load()\nprint('load ->', x)\nDS.save('0 1 1', 'seq.txt')", stdout="x")], "see [cell 1]")
_ng = {"df": None, "_generated_dir": os.path.join(_gtmp, "replay_nodf")}
with _cl.redirect_stdout(_io.StringIO()) as _nbuf:
    exec(_nscript, _ng)
check("the replayed script's DS without a dataset: load says there is nothing to load, save works", "nothing to load" in _nbuf.getvalue() and "load -> None" in _nbuf.getvalue()
      and os.path.isfile(os.path.join(_gtmp, "replay_nodf", "seq.txt")), _nbuf.getvalue()[-300:])

# ---- search: a per-run budget, the view capped with a handle, the record whole ----
SEARCHES = ["###NOTE###\n" + NOTE + "\n###ACTION###\nSEARCH query %d" % i for i in range(6)] + ["###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## r\n\nDone."]
seen_s = {"prompts": []}
def search_llm(system, user, **hints):
    seen_s["prompts"].append(user)
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    i = len([p for p in seen_s["prompts"] if not p.startswith("Rewrite")]) - 1
    return SEARCHES[min(i, len(SEARCHES) - 1)], {"cost": 0.001}
calls = {"n": 0}
def fake_search(q):
    calls["n"] += 1
    return "SOURCED CLAIMS:\n- a figure [1]\n\nSOURCES:\n[1] x - https://x\n\nSUMMARY:\n" + ("long digest\n" * 1100) + "the last line survives", {"cost": 0.052}
k7 = PersistentKernel(df=df); nb7 = Notebook("t7")
try:
    r7 = Session(k7, nb7, search_llm, data_description="d", search=fake_search).run("q", budget=Budget(turns=10, dollars=1.0, searches=4))
finally:
    k7.cleanup()
srch = [t for t in r7.turns if t.kind == "search"]
check("search budget: the seam is called four times, the fifth and sixth SEARCH answer from budget without a call",
      calls["n"] == 4 and len(srch) == 6 and srch[4].stdout.startswith("(search budget") and srch[5].stdout.startswith("(search budget"), (calls["n"], len(srch)))
p2 = seen_s["prompts"][1]
check("search view: a digest past the 12,000-character safety cap is cut from the middle - its head and its last line both in the prompt, the marker naming SHOW SEARCH 1 - the record keeps it whole",
      "SOURCED CLAIMS:" in p2 and "the last line survives" in p2 and "omitted from the middle for length; SHOW SEARCH 1 for all" in p2 and len(srch[0].stdout) > 13000, p2[-400:])
_ps = seen_s["prompts"]
check("what a search cost counts in what the run has spent, as a model call does (0341: a run's four searches cost more than its thirteen turns, and its task line counted none of "
      "them); once the run has searched, every turn's task line says how many searches are left - the first turn's says nothing of them - and a search the budget answered costs nothing",
      "searches left" not in _ps[0].lower()
      and "TASK: turn 2; up to 10 turns and $1.00 (spent $0.05). Web searches left in this run: 3." in _ps[1]
      and "TASK: turn 3; up to 10 turns and $1.00 (spent $0.11). Web searches left in this run: 2." in _ps[2]
      and "TASK: turn 5; up to 10 turns and $1.00 (spent $0.21). Web searches left in this run: 0." in _ps[4]
      and "TASK: turn 6; up to 10 turns and $1.00 (spent $0.21). Web searches left in this run: 0." in _ps[5]
      and "(searches left in this run" not in "".join(_ps), [p[-150:] for p in _ps[:6]])
check("SHOW SEARCH 1 re-opens the whole digest", len(nb7.render_search(r7.id, 1)) > 13000 and "--- search 1: query 0 ---" in nb7.render_search(r7.id, 1))
# ---- a cell_start event precedes every cell run (the executor chip shows Executing) ----
events10 = []
k10 = PersistentKernel(df=df); nb10 = Notebook("t10")
try:
    Session(k10, nb10, thread_llm_factory(["###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nprint(1)\n```", "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## r\n\nOne."]), data_description="d", emit=events10.append).run("q", budget=Budget(turns=3, dollars=1.0))
finally:
    k10.cleanup()
kinds10 = [e.get("type") for e in events10]
check("events: cell_start is emitted right before the cell's result", "cell_start" in kinds10 and kinds10.index("cell_start") < kinds10.index("cell"), kinds10)

# ---- Quick is five turns; the last-turns line never lands on the first turn (2026-09-09) ----
check("quick: five turns at thirty cents", Budget.preset("quick").turns == 5 and abs(Budget.preset("quick").dollars - 0.3) < 1e-9)
check("web searches by mode (0341, the product owner's numbers): Quick 2, Deep 4, Adaptive 6",
      [Budget.preset(m).searches for m in ("quick", "deep", "adaptive")] == [2, 4, 6], [Budget.preset(m).searches for m in ("quick", "deep", "adaptive")])
_seen = []
def _spy_llm(system, user, **hints): _seen.append(user); return "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## r\n\nOne.", {"cost": 0.001}
k11 = PersistentKernel(df=df); nb11 = Notebook("t11")
try:
    Session(k11, nb11, _spy_llm, data_description="d").run("q", budget=Budget(turns=2, dollars=1.0))
finally:
    k11.cleanup()
check("quick: a two-turn budget's first turn is not told the budget is nearly gone (it fires on the last turn itself)", _seen and "nearly gone" not in _seen[0], _seen[0][-160:] if _seen else "")

# ---- plain statement over metaphor: in the report's contract and in the rewrite task (2026-09-08) ----
from analyst.session import REWRITE_TASK as _RW
check("prose: the contract and the rewrite both ask for direct statements, never metaphor", "never metaphor" in open(os.path.join(ROOT, "analyst", "contract.md")).read() and "never let a metaphor" in _RW)
check("rewrite task: the figure citations stay, at the end of the sentence that says what the figure shows (2026-10-11); a [fig n] in the rewrite is no unverified number for the guard",
      "keep that citation at the end of the sentence that says what the figure shows" in _RW and report.guard_rewrite("The spread is in the figure [fig 12].", "x [fig 12]") == "")
# a passage's quote and citation survive the rewrite (2026-10-16: a live rewrite paraphrased every quote and dropped every [C.n] -
# the Simplified view had no chips); the guard says so when one is dropped, as it says of a number the report never had
_rep_q = 'He wrote *"Benene var tunge"* - "the legs were heavy" (*rendered*) [C.807]; the day before [C.806]; the plan [D1.2]; count 3 [cell 4].'
check("rewrite task: a passage cited as [C.n] or [Dn.m] keeps its citation and its quoted words verbatim, with the rendered mark; [cell n] is dropped",
      "keep the citation and the quoted words exactly as the report has them, with the *rendered* mark" in _RW and "a [cell n] citation is dropped" in _RW)
check("rewrite guard: the cited passages kept (bracketed or named bare) pass; a dropped one is disclosed by id; a dropped number and a dropped passage both, in one line",
      report.guard_rewrite('He wrote "Benene var tunge" [C.807], the day before C.806, the plan [D1.2]; count 3.', _rep_q) == ""
      and report.guard_rewrite('He wrote that the legs were heavy; the plan [D1.2]; count 3.', _rep_q) == "CHECK: the plain-language version dropped 2 cited passage(s) the report quotes (C.807, C.806); the quotes and their citations are in the technical report."
      and report.guard_rewrite('He wrote that the legs were heavy, 7.777 on average; the plan [D1.2].', _rep_q).startswith("CHECK: 1 number(s) in the plain-language version do not appear in the technical report (7.777). CHECK: the plain-language version dropped 2 cited passage(s)"),
      report.guard_rewrite('He wrote that the legs were heavy, 7.777 on average; the plan [D1.2].', _rep_q))

# ---- the prompt window: newest cell whole, earlier recent cells collapsed ----
nbw = Notebook("tw"); rw = nbw.new_run("q")
for i in range(5):
    nbw.runs[rw.id].turns.append(Turn(kind="cell", code="\n".join(f"line{j} = {j}" for j in range(30)), stdout=("out%d " % i) * 900, cell_no=i + 1))
view = nbw.render_cells(rw.id)
check("window: the newest cell's code and output ride whole; the two before it show 14 code lines and 1500 chars of output; older cells one line",
      view.count("--- cell") == 4 and "SHOW 5 for all" not in view and view.count("more lines (SHOW") == 3
      and "[cell 1]" in view and view.count("more characters; SHOW") == 3, (view.count("--- cell"), view.count("more lines (SHOW")))
# the cap's slack (2026-10-16): an output a line or two over 1500 rides whole - a live prompt read "[2 more characters; SHOW 1 for all]"
nbs = Notebook("ts"); rs = nbs.new_run("q")
for i, n in enumerate((1502, 1650, 1700, 40)):
    nbs.runs[rs.id].turns.append(Turn(kind="cell", code="x = 1", stdout="o" * n, cell_no=i + 1))
views = nbs.render_cells(rs.id)
check("window: an earlier cell's output within the slack of the cap (1502, 1650 chars) rides whole; one beyond it (1700) is cut at the cap with the count of what follows",
      "SHOW 1 for all" not in views and "SHOW 2 for all" not in views and "... [200 more characters; SHOW 3 for all]" in views
      and re.search(r"^o{1502}$", views, re.M) and re.search(r"^o{1650}$", views, re.M) and re.search(r"^o{1500}$", views, re.M) and not re.search(r"^o{1700}$", views, re.M),
      [l for l in views.splitlines() if "SHOW" in l])
check("guard: a constant that appears in a cell's code (a filter bound) is not flagged as unverified",
      report.numbers_missing("laps with pace 2.8-8 min/km gave 1.069 [cell 1]", ["ratio 1.069"] + ["q = df[(df.pace >= 2.8) & (df.pace <= 8)]"]) == [])

# ---- guards edge cases ----
check("guard: years and small integers are not policed; rounding is tolerated",
      report.numbers_missing("In 2024 we saw 3 groups and a mean of 1.70", ["mean 1.699"]) == [])
check("guard: a real missing number is reported", report.numbers_missing("the estimate is 42.5", ["nothing"]) == ["42.5"])

# ---- the contract has no benchmark vocabulary ----
import re
c = open(os.path.join(ROOT, "analyst", "contract.md")).read()
# ---- the reviewer (2026-10-05): its own prompt and input, no actions; its review rides in the analyst's next prompts; a REPORT
# ---- verdict binds; and once after every report, its note added for the reader
from analyst.session import REVIEWER, parse_review, review_note
REVIEWS_SCRIPT = ["###REVIEW###\n- The question requires: B against A with an interval.\n- Established: the means [cell 1].\n- Checked: cell 2 - computes the mean difference B vs A for 20 subjects; matches its line\n- Checked: cell 1 - the same, step 1; matches its line\n- Most consequential problem: no interval yet.\n- Verdict: TEST bootstrap the difference by subject\n- Re-check: cell 1",
                  "###REVIEW###\n- **The question requires:** B against A with an interval.\n- **Established:** the difference and its interval [cell 3].\n- **Checked:** cell 4 - computes the step-4 difference; matches its line\n- **Checked:** cell 3 - computes the difference with its interval; matches its line\n- **Most consequential problem:** none\n- **Verdict:** **REPORT** the comparison is made and its uncertainty stated",
                  "###REVIEW###\n- The question requires: B against A with an interval.\n- Established: +1.5 (CI 0.2 to 2.8) [cell 3].\n- Most consequential problem: the difference by sex was not examined.\n- Verdict: TEST the difference by sex"]
rv_calls, an_prompts, rv_starts, rv_ends, hints_seen = [], [], [], [], []
rv_i = {"n": 0}
def review_llm(system, user, **hints):
    hints_seen.append(dict(hints))
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    if system.startswith("You are the reviewer"):
        rv_calls.append((system, user, dict(hints))); i_ = rv_i["n"]; rv_i["n"] += 1
        return REVIEWS_SCRIPT[min(i_, len(REVIEWS_SCRIPT) - 1)], {"cost": 0.002}
    an_prompts.append((user, dict(hints)))
    if "this turn is the report" in user:
        return act6("REPORT\n## r\n\nB is higher [cell 3]."), {"cost": 0.001}
    return act6(f"CELL\n```python\ne = 1.5\nRESULT('B vs A step {len(an_prompts)}, 20 subjects', e, e - 1.3, e + 1.3, 'units', 'B higher')\n```"), {"cost": 0.001}
k9 = PersistentKernel(df=df); nb9 = Notebook("t9")
s9 = Session(k9, nb9, review_llm, emit=lambda ev: rv_starts.append(ev) if ev.get("type") == "turn_start" else (rv_ends.append(ev) if ev.get("type") == "turn_end" else None), data_description="d")
try:
    r9 = s9.run("is B higher than A", budget=Budget(turns=12, dollars=1.0, review_every=2))
finally:
    k9.cleanup()
an_tasks = [ln for u, _ in an_prompts for ln in u.splitlines() if ln.startswith("TASK:")]
check("review: one call per review (2026-10-06: no SHOW rounds), on the reviewer's own prompt as review=True; no analyst turn is review=True",
      len(rv_calls) == 3 and all(sy == REVIEWER and h.get("review") is True for sy, _, h in rv_calls) and not any(h.get("review") for _, h in an_prompts),
      ([h for _, _, h in rv_calls], [h for _, h in an_prompts]))
check("review: reviews come after every 2nd turn and are not turns - the analyst's task lines run 1 to 5 without a gap",
      [t.split(";")[0] for t in an_tasks] == [f"TASK: turn {k}" for k in (1, 2, 3, 4, 5)], an_tasks)
u1 = rv_calls[0][1]
check("review: the first review's input - the question, the ledger, no earlier checks, all turns so far, and the cells to check: the results recorded so far, newest first, code and complete output",
      "QUESTION:\nis B higher than A" in u1 and "RESULTS SO FAR:\n- [cell 1] B vs A step 1" in u1 and "CHECKED BY EARLIER REVIEWS:\n(none yet)" in u1
      and "TURNS (the analyst's own account of each turn, its action, and the outcome):\n- turn 1: (no step written) | cell 1 -> RESULT: B vs A step 1" in u1
      and "TO CHECK NOW (code and complete output; no review has checked these):\n--- cell 2 (a result recorded since the last review) ---\n```python\ne = 1.5\nRESULT('B vs A step 2" in u1
      and "\nOUTPUT:\nRESULT: B vs A step 2" in u1 and "--- cell 1 (a result recorded since the last review) ---" in u1 and u1.rstrip().endswith("TURN: after turn 2; up to 12."), u1[-1500:])
u2 = rv_calls[1][1]
check("review: the second review's input - what the first review checked (its Checked lines), the earlier review with the analyst's answer and the test's status, only the turns since, the new cells and the one asked for again, not the one already checked",
      "CHECKED BY EARLIER REVIEWS:\n- cell 1: the same, step 1; matches its line (review after turn 2)\n- cell 2: computes the mean difference B vs A for 20 subjects; matches its line (review after turn 2)" in u2
      and "EARLIER REVIEWS:\n- after turn 2: Verdict: TEST bootstrap the difference by subject\n  the analyst then:" in u2
      and "  since then: cells 3, 4 committed; 0 failed attempts; cells that printed nothing: none" in u2 and '  status: open - no RESULT recorded with test="after turn 2"' in u2
      and "TURNS SINCE YOUR LAST REVIEW (the analyst's own account of each turn, its action, and the outcome):\n- turn 3:" in u2 and "- turn 1:" not in u2
      and "--- cell 4 (a result recorded since the last review) ---" in u2 and "--- cell 3 (a result recorded since the last review) ---" in u2
      and "--- cell 1 (you asked to see it again) ---" in u2 and "--- cell 2 (" not in u2 and u2.rstrip().endswith("TURN: after turn 4; up to 12.")
      and u2.index("--- cell 1 (you asked to see it again) ---") < u2.index("--- cell 4 (a result recorded since the last review) ---"), u2[-2500:])
rv_turns = [t for t in r9.turns if t.kind == "review"]
check("review: the review turn records the cells it was handed, its Checked lines and its Re-check; the card's lines carry them",
      rv_turns[0].shown == [2, 1] and rv_turns[0].checked == [{"cell": 2, "text": "computes the mean difference B vs A for 20 subjects; matches its line", "ok": True, "partly": False}, {"cell": 1, "text": "the same, step 1; matches its line", "ok": True, "partly": False}]
      and rv_turns[0].recheck == [1] and rv_turns[1].shown == [1, 4, 3] and "- Checked: cell 2 - computes the mean difference" in rv_turns[0].note
      and "- Re-check: cell 1" in rv_turns[0].note and "- Shown: cell 2, cell 1" in rv_turns[0].note, (rv_turns[0].shown, rv_turns[0].checked, rv_turns[0].recheck, rv_turns[1].shown, rv_turns[0].note))
check("review: the analyst's REVIEW block carries the TEST's status - open until a RESULT recorded with it",
      "- Status: open - no RESULT line tagged (test after turn 2) yet" in an_prompts[2][0], an_prompts[2][0][-400:])
# 2026-10-19: on the turn after a review the analyst had been handed the review's lines as YOUR NOTE (the review turn's note is
# the review, and Run.note took the newest note of any turn), beside the REVIEW block - its own note lost, the review read twice
check("after a review, YOUR NOTE is the analyst's note as it last wrote it, not the review's lines; the review is in the prompt once, under REVIEW; the run's note never is a review",
      all(f"YOUR NOTE (as you last wrote it):\n{NOTE5}" in u and u.count("- The question requires: B against A with an interval.") == 1 for u, _ in an_prompts[2:])
      and all("The question requires" not in (r9.note or "") for _ in [0]) and r9.note == NOTE5, [u[u.find("YOUR NOTE"):u.find("YOUR NOTE") + 160] for u, _ in an_prompts[2:4]])
# a tagged RESULT answers the test: the status says so, in the analyst's block and in the reviewer's input
tg_prompts, tg_rv = [], []
def tagged_llm(system, user, **h):
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    if system.startswith("You are the reviewer"):
        tg_rv.append(user)
        return ("###REVIEW###\n- The question requires: B against A.\n- Established: the difference [cell 1] +1.5.\n- Most consequential problem: no interval.\n- Verdict: TEST bootstrap the difference" if len(tg_rv) == 1
                else "###REVIEW###\n- The question requires: B against A.\n- Established: +1.5 (0.2 to 2.8) [cell 2].\n- Most consequential problem: none\n- Verdict: REPORT the test is answered [cell 2]"), {"cost": 0.001}
    tg_prompts.append(user)
    if "this turn is the report" in user: return act6("REPORT\n## r\n\nDone [cell 2]."), {"cost": 0.001}
    if len(tg_prompts) == 3:
        return act6("CELL\n```python\ne = 1.5\nRESULT('bootstrap of B vs A, 20 subjects', e, e - 1.3, e + 1.3, 'units', 'B higher', test='after turn 2')\n```"), {"cost": 0.001}
    return act6("CELL\n```python\ne = 1.5\nRESULT('B vs A, 20 subjects', e, None, None, 'units', 'B higher')\n```"), {"cost": 0.001}
kt = PersistentKernel(df=df); nbt = Notebook("tt")
try:
    rt = Session(kt, nbt, tagged_llm, data_description="d").run("q", budget=Budget(turns=8, dollars=1.0, review_every=2))
finally:
    kt.cleanup()
check("review: a RESULT recorded with test='after turn 2' answers the test - the analyst's next block and the reviewer's next input say 'answered by [cell 3]', the tagged cell is handed over, and the REPORT verdict ends the run",
      "- Status: answered by [cell 3]" in tg_prompts[3] and "  status: answered by [cell 3]" in tg_rv[1] and "--- cell 3 (tagged as answering the TEST after turn 2) ---" in tg_rv[1] and rt.status == "answered",
      (tg_prompts[3][-300:], tg_rv[1][-900:] if len(tg_rv) > 1 else ""))
p3 = an_prompts[2][0]
check("review: the review rides in the analyst's next prompts under REVIEW, above the task line, until the next one - without the Re-check and Shown lines, which are the session's",
      "REVIEW (after turn 2 - answer it in your STEP):\n- The question requires: B against A with an interval." in p3 and p3.index("REVIEW (after turn 2") < p3.index("TASK: turn 3")
      and "REVIEW (after turn 2" in an_prompts[3][0] and "- Re-check:" not in p3[p3.index("REVIEW (after turn 2"):] and "- Shown:" not in p3[p3.index("REVIEW (after turn 2"):]
      and "- Checked: cell 2" in p3[p3.index("REVIEW (after turn 2"):], p3[-700:])
p5 = an_prompts[4][0]
check("review: a REPORT verdict citing a cell handed to it binds - the next turn is the report: every cell in view, the review above, the report-now line - and the run is answered",
      "REVIEW (after turn 4 - answer it in your STEP):" in p5 and "- Verdict: REPORT the comparison is made" in p5 and "this turn is the report. Write REPORT now." in p5
      and "TASK: turn 5;" in p5 and r9.status == "answered" and len(an_prompts) == 5, (r9.status, len(an_prompts), p5[-400:]))
u3 = rv_calls[2][1]
check("review after the report: the report is read instead of the note, the input says the analysis is over, the cells it cites that were checked are not sent again, and the note names the cells checked",
      "THE REPORT:\n## r" in u3 and "THE ANALYST'S NOTE" not in u3 and "The analysis is over; this review is added to the report." in u3
      and "TO CHECK NOW (code and complete output; no review has checked these):\n(nothing new to check" in u3
      and r9.report.rstrip().endswith("> **Reviewer's note.** The question requires: B against A with an interval. Not established: the difference by sex was not examined. The analysis that would settle it: the difference by sex. Checked against the code of cell 3."),
      (u3[-700:], r9.report[-300:]))
check("review: recorded as turns of kind review with their verdict and lines; the pane gets a Review card for each",
      [t.text for t in rv_turns] == ["after turn 2", "after turn 4", "after the report"] and rv_turns[1].thinking.startswith("Verdict: REPORT")
      and sum(1 for e in rv_starts if e.get("turn") == "review" and e.get("review")) == 3 and sum(1 for e in rv_ends if e.get("kind") == "review") == 3
      and "- Established: the means [cell 1]." in rv_turns[0].note, [(t.text, t.thinking[:30]) for t in rv_turns])
check("review: the analyst's contract for the run carries the Reviews section, naming the cadence", "## Reviews" in s9.system and "After every 2nd turn a reviewer" in s9.system)
check("contract: the Reviews section only when a reviewer runs - none, and no reviewer at all, in Quick and Deep",
      "After every 8th turn a reviewer" in contract(False, 8) and "## Reviews" not in contract(False, 0) and "reviewer" not in contract(False, 0).lower()
      and "## Reviews" not in CONTRACT and contract(True, 8).index("## Reviews") < contract(True, 8).index("## The note"))
check("rewrite: the plain-language rewrite call carries rewrite=True and no other call does",
      sum(1 for h in hints_seen if h.get("rewrite")) == 1, hints_seen)
# a REPORT citing a cell no review has checked is advice: the run goes on, and the analyst's block says why
ad_prompts, ad_rv = [], []
def advice_llm(system, user, **h):
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    if system.startswith("You are the reviewer"):
        ad_rv.append(user)
        return "###REVIEW###\n- The question requires: X.\n- Established: X is +1 [cell 1].\n- Most consequential problem: none\n- Verdict: REPORT X is established [cell 1]", {"cost": 0.001}
    ad_prompts.append(user)
    return (act6("REPORT\n## r\n\nX is +1 [cell 1].") if len(ad_prompts) >= 4 else act6("CELL\n```python\nprint('RESULT: X, 10 units: +1 (95% CI 0 to 2), up')\n```")), {"cost": 0.001}
ka = PersistentKernel(df=df); nba = Notebook("ta")
try:
    ra = Session(ka, nba, advice_llm, data_description="d").run("q", budget=Budget(turns=8, dollars=1.0, review_every=2))
finally:
    ka.cleanup()
check("review: a REPORT citing a cell no review has checked (its cells recorded nothing, so nothing was handed over) does not bind - the run goes on, and the analyst's block says it is advice and why",
      len(ad_prompts) == 4 and "- Status: advice, not binding - no review has checked cell 1, which it cites." in ad_prompts[2] and ra.status == "answered"
      and "TO CHECK NOW (code and complete output; no review has checked these):\n(nothing new to check" in ad_rv[0],
      (len(ad_prompts), ad_prompts[2][-400:] if len(ad_prompts) > 2 else "", ad_rv[0][-400:]))
# a Checked line that says "does not" (2026-10-06): the cell's ledger lines are marked for the analyst and the reviewer, a
# report citing the cell is flagged, and a later review's "matches" clears the mark
dp_prompts, dp_rv = [], []
def disputed_llm(system, user, **h):
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    if system.startswith("You are the reviewer"):
        dp_rv.append(user)
        return ("###REVIEW###\n- The question requires: X.\n- Established: +1.5 [cell 1].\n- Checked: cell 1 - labelled within-subject; no subject term in the fit: pooled. Does not match.\n"
                "- Most consequential problem: cell 1's label\n- Verdict: TEST refit with the subject term" if len(dp_rv) == 1 else
                "###REVIEW###\n- The question requires: X.\n- Established: +1.5 [cell 1].\n- Most consequential problem: none\n- Verdict: NARROW pooled only"), {"cost": 0.001}
    dp_prompts.append(user)
    if "this turn is the report" in user or len(dp_prompts) >= 4:
        return act6("REPORT\n## r\n\nWithin subjects, +1.50 [cell 1]."), {"cost": 0.001}
    return act6("CELL\n```python\ne = 1.5\nRESULT('X within subjects, 20 subjects', e, e - 1.3, e + 1.3, 'units', 'up')\n```"), {"cost": 0.001}
kd = PersistentKernel(df=df); nbd = Notebook("td")
try:
    rd = Session(kd, nbd, disputed_llm, data_description="d").run("q", budget=Budget(turns=8, dollars=1.0, review_every=2))
finally:
    kd.cleanup()
check("disputed: a Checked line saying the cell's line does not describe its code marks that cell's ledger lines, in the analyst's prompt and the reviewer's input",
      "- [cell 1] (the review after turn 2 found this line does not describe its code) X within subjects" in dp_prompts[3] and "found this line does not describe its code) X within subjects" in dp_rv[1],
      (dp_prompts[3][-600:], dp_rv[1][-900:] if len(dp_rv) > 1 else ""))
check("disputed: a report citing the disputed cell is flagged for the reader",
      "> CHECK: this report cites cell 1, whose RESULT line the review after turn 2 found does not describe its code. Treat what it quotes from there as unverified." in rd.report, rd.report[-400:])
check("reviewer's note: a REPORT verdict whose problem is not 'none' carries it to the reader as a caution",
      review_note({"verdict": "REPORT", "requires": "X", "arg": "established", "problem": "the summary understates the lower bound", "established": "", "checked_cells": [3], "cited": [3]})
      == "**Reviewer's note.** The question requires: X. The report answers it as asked: established. One caution: the summary understates the lower bound. Checked against the code of cell 3."
      and " One caution" not in review_note({"verdict": "REPORT", "requires": "X", "arg": "ok", "problem": "none", "established": "", "checked_cells": [], "cited": []}))
prs = parse_review("###REVIEW###\n- The question requires: X\n- Established: +1 [cell 3]\n- Most consequential problem: none\n- Verdict: REPORT done [cell 3]\n- Re-check: cell 21\n###REVIEW###")
check("parse_review: a stray marker after a complete review does not lose it (2026-10-06: the review after a report ended with ###REVIEW### and was dropped)",
      prs and prs["verdict"] == "REPORT" and prs["arg"] == "done [cell 3]" and prs["recheck"] == [21], prs)
prs2 = parse_review("###REVIEW###\n- Verdict: pending\n###REVIEW###\n- The question requires: X\n- Established: y\n- Most consequential problem: none\n- Verdict: NARROW only y")
check("parse_review: with several markers, the review is the text after the last one that carries a verdict", prs2 and prs2["verdict"] == "NARROW" and prs2["requires"] == "X", prs2)
check("reviewer prompt: checking is the reviewer's own work - it does not ask the analyst to verify or re-open cells", "do not ask the analyst to\nverify or re-open cells - ask it for analysis" in REVIEWER)
from analyst.session import checked_ok, checked_verdict, disputed_cells, disputed_mark, Run as _Run, Turn as _Turn
check("checked_ok: 'matches its line' is fine, 'does not match' is not, a line with both ('matches ..., but does not cover ...') stays fine",
      checked_ok("computes the difference; matches its line") and not checked_ok("labelled within-athlete; no athlete term: pooled. Does not match.")
      and checked_ok("matches its line, but does not cover the surface difference"))
# 2026-10-19: a review wrote "those two lines match. The disagreement line does not: ..." and every line of the cell was marked,
# the two it accepted included - the test had looked for the word "matches" alone. The word is read by its stem, and a line
# that says both is a finding on one of the cell's lines, not all
_cv = {"those two lines match, including the unplanned numerator. The third line does not fully: it is set seconds over set seconds": "partly",
       "Spearman +0.49, n=65; those two lines match. The disagreement line does not: the bootstrap resamples only the flagged days": "partly",
       "sums time and the flag, means the rating; matches those printed figures; does not: the flag sum is not distinct days": "partly",
       "weekly minutes and share; matches the printed shares; does not report coverage against ride time": "ok",
       "the counts and the tone table match the print. It does not support the claim that 13 passages touch the theme": "ok",
       "the line says pooled; the code does not pool": "no", "matched its line": "ok", "the lines are matching": "ok",
       "not matching its line": "no", "doesn't match": "no", "do not match the code": "no", "": "ok"}
check("checked_verdict: match/matched/matching read alike; 'does not' with a match elsewhere is partly (elliptical 'does not:' and 'does not fully:' included); "
      "'does not <something else>' beside a match is fine; 'does not' with no match anywhere is no",
      all(checked_verdict(t) == v for t, v in _cv.items()) and not checked_ok(next(iter(_cv))), {t[:40]: checked_verdict(t) for t, v in _cv.items() if checked_verdict(t) != v})
_rd = _Run(id="rd2", question="q", parent=None)
_rd.turns = [_Turn(kind="review", text="after turn 2", checked=[{"cell": 4, "text": "does not match", "ok": False}]),
             _Turn(kind="review", text="after turn 4", checked=[{"cell": 4, "text": "refit; matches its line", "ok": True}])]
check("disputed_cells: the latest review's word on a cell stands - a later 'matches' clears an earlier 'does not'", disputed_cells(_rd) == {}, disputed_cells(_rd))
_rd.turns.append(_Turn(kind="review", text="after turn 6", checked=[{"cell": 4, "text": "two lines match; the third does not:", "ok": False, "partly": True}, {"cell": 5, "text": "does not match", "ok": False}]))
check("disputed_cells carries whether the finding was on one line of the cell; the ledger's mark says so (a line of this cell), and the whole-cell mark reads as before; a record without the field (an older run) is whole",
      disputed_cells(_rd) == {4: {"review": "after turn 6", "partly": True}, 5: {"review": "after turn 6", "partly": False}}
      and disputed_mark(disputed_cells(_rd)[4]) == "(the review after turn 6 found a line of this cell does not describe its code) "
      and disputed_mark(disputed_cells(_rd)[5]) == "(the review after turn 6 found this line does not describe its code) ", disputed_cells(_rd))

from analyst.session import result_lines, Run as _Run, Turn as _Turn
_rc = _Run(id="rc", question="q", parent=None)
_rc.turns = [_Turn(kind="cell", cell_no=1, code="x", results=[{"text": "slope within athletes, 54 sessions: -2.1 (95% CI -17.9 to +13.7)", "typed": False, "test": None, "corrects": None}]),
             _Turn(kind="cell", cell_no=2, code="y", results=[{"text": "(corrects cell 1) slope pooled, not within athletes - with athlete fixed effects: +4.0 (95% CI -9 to +17)", "typed": False, "test": None, "corrects": 1}])]
check("ledger: a RESULT recorded with corrects=1 marks cell 1's line as corrected, in every prompt's RESULTS SO FAR",
      result_lines(_rc) == ["- [cell 1] (corrected by cell 2) slope within athletes, 54 sessions: -2.1 (95% CI -17.9 to +13.7)",
                            "- [cell 2] (corrects cell 1) slope pooled, not within athletes - with athlete fixed effects: +4.0 (95% CI -9 to +17)"], result_lines(_rc))
# 0326: a correction marks the line it replaced, not every line of its cell (routines.corrected_by; its rule in test_routines.py, the code trace in test_code_map.py)
_B = "yield, regime B minus A, plots pooled: +0.62 (95% CI +0.37 to +0.84) t/ha, B higher"
_C = "yield, regime C minus A, plots pooled: +0.30 (95% CI +0.05 to +0.55) t/ha, C higher"
_N = "plots compared: +36"
_by_words = "(corrects cell 2) yield, regime B minus A, plots pooled: +0.41 (95% CI +0.20 to +0.63) t/ha, B higher"
_by_number = "(corrects cell 2) yield, regime C minus A, plot means: +0.30 (95% CI +0.05 to +0.55) t/ha, C higher"
_kept = lambda text, corrects=None: {"text": text, "typed": False, "test": None, "corrects": corrects}
_rl = _Run(id="rl", question="q", parent=None)
_rl.turns = [_Turn(kind="cell", cell_no=2, code="a", results=[_kept(_B), _kept(_C), _kept(_N)]), _Turn(kind="cell", cell_no=5, code="b", results=[_kept(_by_words, 2)]),
             _Turn(kind="cell", cell_no=6, code="c", results=[_kept(_by_number, 2)])]
_marked = ["- [cell 2] (corrected by cell 5) " + _B, "- [cell 2] (corrected by cell 6) " + _C, "- [cell 2] " + _N]
check("ledger: a correction marks the line it replaced - one by its words, one by its number - and the line recorded beside them stands; so too while the correcting "
      "cells' own lines are left out, their output being in view",
      result_lines(_rl) == _marked + ["- [cell 5] " + _by_words, "- [cell 6] " + _by_number] and result_lines(_rl, omit=(5, 6)) == _marked, result_lines(_rl))
_rl.turns.append(_Turn(kind="cell", cell_no=7, code="d", results=[_kept("(corrects cell two) soil types compared: +3", "two")]))
check("ledger: a correction that names no cell by its number marks nothing and the ledger is still made (reading it as a number had raised)",
      result_lines(_rl) == _marked + ["- [cell 5] " + _by_words, "- [cell 6] " + _by_number, "- [cell 7] (corrects cell two) soil types compared: +3"], result_lines(_rl))
_log = Session._turn_log(r3) + Session._turn_log(r2)
check("the reviewer's turn log: a failed attempt with its error, and a committed cell with its first line",
      any("cell failed, rolled back -> " in x for x in _log) and any(re.search(r"\| cell \d+ -> ", x) for x in _log), _log[:6])
from analyst.session import cited_cells
prc = parse_review("###REVIEW###\n- The question requires: X\n- Established: +1 [cell 3]\n- Checked: cell 3 - computes X for 20 subjects; matches its line\n- Checked: cell 7 - labelled within-athlete; no athlete term: pooled.\n  Does not match.\n- Most consequential problem: cell 7's label\n- Verdict: TEST refit with the athlete term\n- Re-check: cells 7, 9")
check("parse_review: several Checked lines are kept, one per cell, a run-on line joined; Re-check names cells; the lines carry them in order",
      prc and prc["checked"] == [(3, "computes X for 20 subjects; matches its line"), (7, "labelled within-athlete; no athlete term: pooled. Does not match.")] and prc["recheck"] == [7, 9]
      and prc["lines"].splitlines()[2:4] == ["- Checked: cell 3 - computes X for 20 subjects; matches its line", "- Checked: cell 7 - labelled within-athlete; no athlete term: pooled. Does not match."]
      and prc["lines"].splitlines()[-1] == "- Re-check: cell 7, cell 9", prc)
check("cited_cells: [cell 11], [cells 11, 13], [cell 11, cell 13] all read", cited_cells("x [cell 11] y [cells 12, 13] z [cell 14, cell 15]") == [11, 12, 13, 14, 15], cited_cells("x [cell 11] y [cells 12, 13] z [cell 14, cell 15]"))
check("contract: a correction is recorded with corrects=14, and the earlier line with its words or its number is marked - every line of the cell when none has either",
      "record the corrected estimate with `corrects=14`: cell 14's line with the same words or number is marked as corrected, else all its lines." in " ".join(c_all.split()))
check("contract (Adaptive): a REPORT citing a cell not checked is advice; the reviewer reads the cells the estimate rests on",
      "unless its status says a cell it cites has not been checked: then it is advice" in contract(False, 8) and "the code and output of the cells your estimate rests on" in contract(False, 8))
check("reviewer prompt: the cells to check are handed to it, one Checked line per cell, Re-check for a second look, REPORT binds only on checked cells; no SHOW",
      "TO CHECK NOW" in REVIEWER and "Write one Checked line per cell" in REVIEWER and "name that\ncell under Re-check" in REVIEWER
      and "It binds only when every cell you cite has been checked" in REVIEWER and "SHOW" not in REVIEWER and "not proof that its label describes what the code computed" in REVIEWER)
check("reviewer prompt: five perspectives before the verdict - identification, alternative explanation, heterogeneity (each thing held fixed a candidate), measurement, the question's frame - and a TEST comes from one (2026-10-06)",
      "## Perspectives" in REVIEWER and all(h in REVIEWER for h in ("- Identification:", "- Alternative explanation:", "- Heterogeneity:", "- Measurement:", "- The question's frame:"))
      and "Each thing the\n  analyst holds fixed is also a candidate" in REVIEWER and "A TEST you recommend comes from one of these lines." in REVIEWER and REVIEWER.index("## Perspectives") < REVIEWER.index("## What you do"))
prl = parse_review("###REVIEW###\n- The question requires: X\n- Established: +1 [cell 3]\n- Identification: between-group variation only\n- Alternative explanation: nothing\n- Heterogeneity: may differ by the condition held fixed; unchecked\n- Measurement: none\n- The question's frame: the effect within each condition\n- Most consequential problem: the effect within conditions never estimated\n- Verdict: TEST estimate it within each level")
check("parse_review: the five lens lines are read; those answered 'nothing' or 'none' are dropped; the rest ride in the lines between Checked and the problem, so the analyst sees the perspectives that found something",
      prl and prl["lenses"] == [("Identification", "between-group variation only"), ("Heterogeneity", "may differ by the condition held fixed; unchecked"), ("The question's frame", "the effect within each condition")]
      and prl["lines"].splitlines()[2:5] == ["- Identification: between-group variation only", "- Heterogeneity: may differ by the condition held fixed; unchecked", "- The question's frame: the effect within each condition"]
      and prl["requires"] == "X", prl)
# ---- the standing rule (2026-10-05): no task-specific or model-specific content in any prompt. Every authored text a model
# ---- reads is scanned for the vocabulary of the tasks this agent was tested on; docstrings and comments are not prompts.
import ast as _ast
from analyst.session import REWRITE_TASK, LAST_TURNS_LINE, REPORT_NOW, reviewer as reviewer_text, REVIEWER_WORDS_LENS
from bambooai.reading import READER_SYSTEM
_DOMAIN = re.compile(r"\b(athletes?|altitude|sea.level|heart.rate|HR|HRmax|hr_max|pace|runners?|race|marathon|venues?|surfaces?|terrain|km|laps?|weekly load|gap years|site name|F1|Formula|drivers?)\b", re.I)
def _authored_strings(path):
    tree = _ast.parse(open(os.path.join(ROOT, path), encoding="utf-8").read())
    docs = set()
    for node in _ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (_ast.Module, _ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)) and body and isinstance(body[0], _ast.Expr) and isinstance(getattr(body[0], "value", None), _ast.Constant):
            docs.add(id(body[0].value))
    return [n.value for n in _ast.walk(tree) if isinstance(n, _ast.Constant) and isinstance(n.value, str) and id(n) not in docs]
_texts = {"contract (plain)": contract(False, 0), "contract (documents, reviews)": contract(True, 8), "contract (context)": contract(False, 0, context=True),
          "reviewer": REVIEWER, "reviewer (context)": reviewer_text(True), "rewrite task": REWRITE_TASK, "reader": READER_SYSTEM, "last turns": LAST_TURNS_LINE, "report now": REPORT_NOW}
for _path in ("analyst/session.py", "analyst/tools.py", "bambooai/reading.py", "analyst/routines.py", "bambooai/routines_host.py", "analyst/context.py", "analyst/coder.py", "analyst/codebook.py", "analyst/coded.py", "analyst/profile.py"):
    for _k, _t in enumerate(_authored_strings(_path)):
        _texts[f"{_path} string {_k}"] = _t
_hits = {name: sorted({m.group(0) for m in _DOMAIN.finditer(t)}) for name, t in _texts.items() if _DOMAIN.search(t)}
check("standing rule: no prompt text a model reads carries the tested tasks' vocabulary - contract (plain, documents, context), reviewer (five lenses and six), rewrite, reader, the routines' promoter, the context map, the coder, and every string the session, tools, reader, routines, context, coder and codebook send (the seed codebook is data, not scanned)",
      not _hits, _hits)
# Quick and Deep make no reviewer call at all - not during the run, not after the report (2026-10-05)
nr_systems = []
def noreview_llm(system, user, **h):
    nr_systems.append(system[:40])
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    if system.startswith("You are the reviewer"): return "###REVIEW###\n- The question requires: x\n- Established: y\n- Most consequential problem: none\n- Verdict: REPORT done", {"cost": 0.01}
    return (act6("REPORT\n## r\n\nDone [cell 1].") if sum(1 for x in nr_systems if x.startswith("You are the analyst")) >= 2 else act6("CELL\n```python\nprint('RESULT: x, 5 units: +1 (95% CI 0 to 2), up')\n```")), {"cost": 0.001}
kn = PersistentKernel(df=df); nbn = Notebook("tn")
try:
    rn = Session(kn, nbn, noreview_llm, data_description="d").run("q", budget=Budget(turns=6, dollars=1.0, review_every=0))
finally:
    kn.cleanup()
check("no reviews outside Adaptive: a run without reviews during it makes no reviewer call after its report either, and its report carries no reviewer's note",
      rn.status == "answered" and not any(x.startswith("You are the reviewer") for x in nr_systems) and "Reviewer's note" not in rn.report
      and not any(t.kind == "review" for t in rn.turns), (rn.status, nr_systems))

# a review with no verdict is not used: no REVIEW block, no review turn, no note; the run goes on
nv_prompts = []
def noverdict_llm(system, user, **hints):
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    if system.startswith("You are the reviewer"): return "It looks fine to me.", {"cost": 0.001}
    nv_prompts.append(user)
    return (act6("REPORT\n## r\n\nDone [cell 1].") if len(nv_prompts) >= 3 else act6("CELL\n```python\nprint(1)\n```")), {"cost": 0.001}
kv = PersistentKernel(df=df); nbv = Notebook("tv")
try:
    rvv = Session(kv, nbv, noverdict_llm, data_description="d").run("q", budget=Budget(turns=6, dollars=1.0, review_every=1))
finally:
    kv.cleanup()
check("review: a reply that names no verdict is not used - no REVIEW block, no review turn, no note - and the run goes on to its report",
      rvv.status == "answered" and not any("REVIEW (" in u for u in nv_prompts) and not any(t.kind == "review" for t in rvv.turns) and "Reviewer's note" not in rvv.report,
      (rvv.status, [t.kind for t in rvv.turns]))
pr_ = parse_review("Some preamble\n###REVIEW###\n- The question requires: X by group\n  and its interval.\n- Established: nothing yet\n- Most consequential problem: none\n- Verdict: NARROW only the pooled X is supported")
check("parse_review: a field running on to the next line is joined; NARROW parsed with its conclusion", pr_ and pr_["requires"] == "X by group and its interval." and pr_["verdict"] == "NARROW" and pr_["arg"] == "only the pooled X is supported", pr_)
check("review timing: before turns 9, 17... for 8; never before the first; none without reviews",
      Session.is_review(Budget(turns=50, review_every=8), 9) and not Session.is_review(Budget(turns=50, review_every=8), 8)
      and not Session.is_review(Budget(turns=50, review_every=0), 9) and not Session.is_review(Budget(turns=50, review_every=8), 1))

# ---- the report turn sees everything; SHOW takes several cells (2026-09-10, from a run whose report could not quote cell 9)
seen_prompts = []
def view_llm(system, user, **hints):
    seen_prompts.append(user)
    n = len(seen_prompts)
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    note = "- Question as understood: q"
    if n == 1: return "###THINKING###\nt\n###NOTE###\n" + note + "\n###ACTION###\nCELL\n```python\nprint('A' * 2400 + '\\nZTAIL=42')\n```", {"cost": 0.001}
    if n in (2, 3, 5): return "###THINKING###\nt\n###NOTE###\n" + note + "\n###ACTION###\nCELL\n```python\nprint(%d)\n```" % n, {"cost": 0.001}
    if n == 4: return "###THINKING###\nt\n###NOTE###\n" + note + "\n###ACTION###\nSHOW 1 2", {"cost": 0.001}
    return "###THINKING###\nt\n###NOTE###\n" + note + "\n###ACTION###\nREPORT\nZTAIL=42 stands [cell 1].", {"cost": 0.001}
k10 = PersistentKernel(df=df); nb10 = Notebook("t10")
s10 = Session(k10, nb10, view_llm, data_description="d")
try:
    s10.run("q", budget=Budget(turns=6, dollars=1.0, review_every=0))
finally:
    k10.cleanup()
p5 = seen_prompts[4]          # after SHOW 1 2
check("SHOW 1 2: the next prompt re-opens both cells", "--- cell 1 (re-opened) ---" in p5 and "--- cell 2 (re-opened) ---" in p5 and "ZTAIL=42" in p5)
p3 = seen_prompts[2]          # cell 1 is an earlier recent cell here: capped, its tail out of view
c1 = p3[p3.index("--- cell 1 ---"):p3.index("--- cell 2 ---")]
check("the normal window caps an earlier recent cell (the tail of cell 1 is out of view)", "more characters; SHOW 1 for all" in c1 and "ZTAIL=42" not in c1.split("OUTPUT:")[-1], c1[-200:])
p6 = seen_prompts[5]          # the last turn: the forced report sees everything
check("the report turn sees every cell's output whole (cell 1's tail is in view; no cap marker)",
      "EVERY CELL OF THIS RUN" in p6 and "ZTAIL=42" in p6 and "more characters; SHOW" not in p6 and "The budget is nearly gone" in p6, p6[-300:])
# the halt path and the after-loop call use the same view
pe = s10._user_prompt(nb10.runs[list(nb10.runs)[0]], Budget(turns=6, review_every=0), 3, 0.0, "STOP: x", everything=True)
check("the halt prompt sees everything too", "EVERY CELL OF THIS RUN" in pe and "ZTAIL=42" in pe)
# the total safety cap: an output far beyond it loses its middle, keeps head and tail, never the cell
from analyst.notebook import Notebook as _NB, Run as _Run, Turn as _Turn
nb11 = _NB("t11"); r = _Run(id="r1", parent=None, question="q"); nb11.runs["r1"] = r
big = "HEAD-" + "x" * 200_000 + "-TAIL"
r.turns = [_Turn(kind="cell", code="print(1)", stdout="small one", cell_no=1), _Turn(kind="cell", code="print(2)", stdout=big, cell_no=2)]
view = nb11.render_cells("r1", everything=True)
check("the total cap: a pathological output is shortened from the middle with a marker; the small cell is untouched",
      "HEAD-" in view and "-TAIL" in view and "omitted from the middle" in view and "small one" in view and len(view) < 170_000, len(view))

bad = re.findall(r"\b(athlete|driver|altitude|sea level|hr_max|race|F1|Formula)\b", c, re.I)
check("contract: one page - under 9,000 without documents (2026-10-06: Results with RESULT(...), DS with save, the comparison, the budget as a limit), neutral", len(c) < 9000 and not bad, (len(c), bad))
check("contract: DS.save(frame, name) saves a dataset for the person - CSV by default, json/parquet/xlsx/txt by the name, a string as text - listed in the Dataset cache under Generated",
      "`DS.save(frame,\n\"name\")` saves a dataset for the person as CSV - `\"name.json\"`, `\"name.parquet\"`, `\"name.xlsx\"` or\n`\"name.txt\"` in that format, and a string as a text file: it appears in their Dataset cache under\nGenerated." in c)
check("contract: a reply with more than one action runs the first and the rest does not - said in Format", "A reply\nwith more than one action runs the first; the rest does not run." in c)
check("contract (Adaptive): a TEST's outcome is recorded with test='after turn 16', and the test is open until it is recorded",
      "`RESULT(..., test=\"after turn 16\")`" in contract(False, 8) and "until such a line is recorded the test is open" in contract(False, 8))
check("contract: the format is a literal template of one turn - three marker lines, each once - and the actions are a table with one row per form",
      c.count("###STEP###") == 1 and c.count("###NOTE###") == 1 and c.count("###ACTION###") == 1 and "| a fenced python block |" in c and "| `CELL` |" not in c and "| `REPORT` |" in c and "Seven headings" in c and "under the headings listed in The note" in c)
# the step's section is STEP, framed for the person following the run; THINKING, filled before the action, and a note
# called "your memory" were the pattern the Claude 5.5 classifiers decline as reasoning extraction (2026-10-08: four
# refused turns in one Sonnet 5.5 run, and the answer written without the scaffold)
import re as _re_c
_scan = {name: sorted({m.group(0).lower() for m in _re_c.finditer(r"(?i)\b(thinking|reasoning|scratchpad|memory|private)\b", t)})
         for name, t in {"plain": c, "documents, reviews": contract(True, 8), "context": contract(False, 0, context=True), "reviewer": REVIEWER, "reviewer (context)": reviewer_text(True)}.items()}
check("contract: the step is a STEP section written for the person following the run, the note is the standing state - no section "
      "named for thinking or reasoning, no memory or private notes, in any prompt a model reads",
      "###THINKING###" not in c and "###STEP###\nTwo or three sentences for the person following the run: what the last output showed, what this\nturn does and why." in c
      and "the standing state of the analysis, for the person\nand for your next turn" in c and "your memory" not in c
      and not any(v for v in _scan.values()), _scan)
_st = parse_turn("###STEP###\nThe last output showed 9 overlap. Now the within-athlete fit.\n###NOTE###\n- Question as understood: q\n###ACTION###\nCELL\n```python\nprint(1)\n```")
_sr = parse_turn("###STEP###\nDone.\n###NOTE###\n- Plan: report\n###ACTION###\nREPORT\n## r\n\nx [cell 1].")
_so = parse_turn("###THINKING###\nold marker\n###NOTE###\n- Question as understood: q\n###ACTION###\nSHOW 3")
_sn = parse_turn("###STEP###\nno action here\n###NOTE###\n- Question as understood: q")
check("parse_turn: the STEP marker is read as the step - for a cell and a report - and the THINKING marker of earlier runs still is; without an action the step is still captured",
      _st[0] == "The last output showed 9 overlap. Now the within-athlete fit." and _st[2].verb == "cell" and _st[2].arg == "print(1)"
      and _sr[0] == "Done." and _sr[2].verb == "report" and _sr[2].arg.startswith("## r")
      and _so[0] == "old marker" and _so[2].verb == "show" and _so[2].arg == "3"
      and _sn[0] == "no action here" and _sn[2].verb == "invalid", (_st, _sr, _so, _sn))
check("contract: no documents furniture and the one budget rule when the thread has no documents",
      "READ D1" not in c and "[D1.17]" not in c and "LOOK" not in c and "## Documents" not in c and "The limit is not a target" in c and "Write REPORT when the answer is established" in c)
cd_ = open(os.path.join(ROOT, "analyst", "contract_documents.md")).read()
check("the documents' section: the seven kernel objects, READ for what grep cannot do, the citation rule, no LOOK - under 900 characters; the READ row names the stretch forms", len(cd_) < 900 and "D1.around" in cd_ and "[D1.17]" in cd_ and "LOOK" not in cd_ and "p.7-9" in READ_ROW and "READ ALL" in READ_ROW, (len(cd_), cd_[:100]))
sd = Session(None, Notebook("sd"), lambda s, u, **h: ("", {}), data_description="d", documents=True)
sn = Session(None, Notebook("sn"), lambda s, u, **h: ("", {}), data_description="d")
check("the system prompt carries the documents' section and the READ row only when the thread has documents", sd.system == contract(True) and sn.system == CONTRACT and "## Documents" not in sn.system)
# the context's section (docs/CONTEXT_DESIGN.md step 2): joined only when a context file is loaded, after Documents when both are
cc_ = open(os.path.join(ROOT, "analyst", "contract_context.md")).read()
sc_ = Session(None, Notebook("sc"), lambda s, u, **h: ("", {}), data_description="d", context=True)
sb_ = Session(None, Notebook("sb"), lambda s, u, **h: ("", {}), data_description="d", documents=True, context=True)
cc1_ = " ".join(cc_.split())
cd_ = open(os.path.join(ROOT, "analyst", "contract_documents.md")).read()
check("the context's section (step 4's trim, 2026-10-14; 0155 put the two frames' descriptions back - without them the analyst read the codes file by path and never glanced at the codes on a words question): "
      "CTX, the two frames said to be what they are, a code's day, the four calls, READ CTX, the [C.417] citation, the rendered marker, a code as a reading, the words and the numbers days apart - matched by a code's day, "
      "say what rests on what - under 1,000 characters (the Documents section is 578; 1,050 while CTX.days() and CTX.episodes() were in it, 0204-0205, never called in three runs - "
      "patch 0206 put the day each code describes in the codes and the sentence to match by it in their place; 900 until step 5, 2026-10-18: two runs had "
      "matched the words to the numbers by the day of writing; 760 until 2026-10-18, when the calls' return - text to print, rows "
      "with as_frame=True - joined it: both runs of a words question lost two turns treating grep's text as records; 800 until patch 0198, when the codes' direction, "
      "basis and days joined CTX.codes()'s description: a run counted codes on denials as the state denied); what did not change what the model does is out (counts are numbers, English); "
      "joined only with context, after Documents when both are, with the READ CTX row",
      len(cc_) < 1000 and all(x in cc1_ for x in ("`CTX.frame()` (the passages, dated, with author and kind), `CTX.codes()` (the codes on them, with the words they rest on, which way each points against the person's usual state, said or inferred, and `day`, the day it describes); `CTX.grep('pattern')`, `CTX.around('2026-08-14', days=3)` and `CTX.on(activity_id)` return text to print (rows with `as_frame=True`), `CTX.text('C.417')` one passage whole.",
                                                                              "READ CTX quotes passages under ids like [C.417]; the report cites one as [C.417] beside [cell 7], as written or in its English rendering, marked *rendered*.",
                                                                              "A code is a model's reading of a passage, not the writer's words; the words and the numbers can be days apart: match a code to them by its `day`, not its passage's date.",
                                                                              "Where the report explains a number by what was written, it says what that rests on - passages quoted, counts of codes, or your reading."))
      and not any(x in cc1_ for x in ("a number like any other", "English.", "mapped in DATA", "CTX.days()", "CTX.episodes()"))
      and sc_.system == contract(False, context=True) and "## Context" in sc_.system and "## Documents" not in sc_.system and "`READ CTX <what>`" in sc_.system and "`READ D1 <what>`" not in sc_.system
      and sb_.system == contract(True, context=True) and sb_.system.index("## Documents") < sb_.system.index("## Context") < sb_.system.index("## Format")
      and "## Context" not in sn.system and "READ CTX" not in sd.system, (len(cc_), len(cd_), sc_.system[-700:]))
# the reviewer's sixth lens (docs/CONTEXT_DESIGN.md §6, step 4): Words, only with context - the brief without it byte-identical
rvc_ = reviewer_text(True)
check("the reviewer's brief with context: six lenses, the Words bullet after the question's frame among the perspectives and its line in the format; without context the five, byte-identical to REVIEWER, "
      "no placeholder left in either",
      reviewer_text(False) == REVIEWER and "five lenses" in REVIEWER and "Words" not in REVIEWER and "{" not in REVIEWER and "{" not in rvc_
      and "six lenses" in rvc_ and rvc_.count("- Words:") == 2 and REVIEWER_WORDS_LENS in rvc_
      and rvc_.index("- The question's frame: what the person asked") < rvc_.index(REVIEWER_WORDS_LENS) < rvc_.index("A TEST you recommend comes from one of these lines.")
      and "- The question's frame: ...\n- Words: ...\n- Most consequential problem:" in rvc_
      and "whether that rests on passages quoted,\n  on counts of codes, or on the analyst's reading, and is reported as what it is" in rvc_ and "compared with a window rather than matched by day" in rvc_
      and rvc_.replace(REVIEWER_WORDS_LENS, "").replace("- Words: ...\n", "").replace("six lenses", "five lenses") == REVIEWER, (len(REVIEWER), len(rvc_)))
prw = parse_review("###REVIEW###\n- The question requires: X\n- Established: +1 [cell 3]\n- Identification: nothing\n- Alternative explanation: nothing\n- Heterogeneity: nothing\n- Measurement: nothing\n- The question's frame: nothing\n- Words: the fatigue count is the model's reading, reported as the rider's words; the days matched, not windowed\n- Most consequential problem: the count read as what was said\n- Verdict: TEST compare with a 3-day window")
check("parse_review: the Words line is a lens like the five - read, kept when it found something, riding to the analyst after the others",
      prw and prw["lenses"] == [("Words", "the fatigue count is the model's reading, reported as the rider's words; the days matched, not windowed")]
      and prw["lines"].splitlines()[2] == "- Words: the fatigue count is the model's reading, reported as the rider's words; the days matched, not windowed" and prw["verdict"] == "TEST", prw)
# a session with context hands the reviewer the six-lens brief; without, the five (the same scripted reviewer)
rvx_systems = []
def review_ctx_llm(system, user, **h):
    if system.startswith("You are the reviewer"):
        rvx_systems.append(system)
        return "###REVIEW###\n- The question requires: x\n- Established: y [cell 1]\n- Checked: cell 1 - prints; matches its line\n- Words: nothing\n- Most consequential problem: none\n- Verdict: REPORT done", {"cost": 0.01}
    return review_llm(system, user, **h)
kx_ = PersistentKernel(df=df); nbx_ = Notebook("tx")
try:
    rx_ = Session(kx_, nbx_, review_ctx_llm, data_description="d", context=True).run("q", budget=Budget(turns=8, dollars=1.0, review_every=2))
finally:
    kx_.cleanup()
check("a run with context calls the reviewer on the six-lens brief (reviewer(True)); the run completes", rvx_systems and all(sy == rvc_ for sy in rvx_systems) and rx_.report, (len(rvx_systems), rx_.report[:80] if rx_.report else rx_))

# every file of the analyst package that is not Python must be in the wheel (2026-10-14: contract_context.md had been
# left out of pyproject's package-data by 0146; an installed edition would have failed at import)
import re as _re_p
_pp = open(os.path.join(ROOT, "pyproject.toml"), encoding="utf-8").read()
_listed = set(_re_p.findall(r'"([^"]+)"', _re_p.search(r"^analyst = \[(.*?)\]", _pp, _re_p.M).group(1)))
_present = {f for f in os.listdir(os.path.join(ROOT, "analyst")) if not f.endswith(".py") and f != "__pycache__" and not f.startswith(".")
            and not os.path.isdir(os.path.join(ROOT, "analyst", f))}        # a subpackage (codemap) is listed under packages
check("packaging: every non-Python file of analyst/ is listed in pyproject's package-data, and nothing listed is missing", _listed == _present, (sorted(_listed ^ _present)))
_pkgs = set(_re_p.findall(r'"([^"]+)"', _re_p.search(r"^packages = \[(.*?)\]", _pp, _re_p.M | _re_p.S).group(1)))
# ---- the reach record (2026-10-28): what a cell touched outside the data rides on its Turn, marked asked or not; a
# refused cell is a Turn with the restricted word, not an error of the code; the run keeps the box's facts ----
import threading, http.server, socketserver  # noqa: E402
from analyst import reach  # noqa: E402
from analyst.notebook import Run  # noqa: E402


class _RH(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"y" * 3000
        self.send_response(200); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def log_message(self, *a):
        pass


_rsrv = socketserver.TCPServer(("127.0.0.1", 0), _RH); _rport = _rsrv.server_address[1]
threading.Thread(target=_rsrv.serve_forever, daemon=True).start()
reach_script = [act6(f"CELL\n```python\nimport requests\nr = requests.get('http://127.0.0.1:{_rport}/x')\nprint(len(r.content))\n```"),
                act6("CELL\n```python\nprint(open('/etc/hostname').read().strip() != '')\n```"),
                act6("CELL\n```python\nimport subprocess\nprint(subprocess.run(['ls']).returncode)\n```"),
                act6("REPORT\n## r\n\nDone.")]
kr = PersistentKernel(df=df); nbr = Notebook("tr"); evr = []
try:
    rr = Session(kr, nbr, thread_llm_factory(reach_script), data_description="d", emit=evr.append).run(
        f"Fetch the file from 127.0.0.1:{_rport} and count its bytes", budget=Budget(turns=6, dollars=1.0, review_every=0))
finally:
    _rsrv.shutdown()
    try:
        kr.close()
    except Exception:
        pass
cells_r = [t for t in rr.turns if t.kind == "cell"]
check("reach: the cell that fetched carries the record on its Turn, marked asked because the question named the host",
      len(cells_r) == 3 and len(cells_r[0].reaches) == 1 and cells_r[0].reaches[0]["kind"] == "net" and cells_r[0].reaches[0]["asked"] is True
      and cells_r[0].reaches[0]["in"] > 3000 and cells_r[0].reaches[0]["line"] == 2 and cells_r[0].refused == "", [(t.reaches, t.refused) for t in cells_r])
check("reach: a file read the question did not name is on its Turn marked not asked",
      cells_r[1].reaches and cells_r[1].reaches[0]["kind"] == "file" and cells_r[1].reaches[0]["path"] == "/etc/hostname" and cells_r[1].reaches[0]["asked"] is False, cells_r[1].reaches)
check("reach: the refused cell is a Turn with the restricted word, no cell number, the notice as its error and no reaches",
      cells_r[2].refused == "subprocess" and cells_r[2].cell_no is None and "Security notice" in cells_r[2].error and cells_r[2].reaches == [], (cells_r[2].refused, cells_r[2].cell_no, cells_r[2].error[:80]))
check("reach: the run keeps the box's facts from the kernel", isinstance(rr.sandbox, dict) and "uid" in rr.sandbox and "metadata" in rr.sandbox, rr.sandbox)
cell_events = [e for e in evr if e.get("type") == "cell"]
check("reach: the cell events carry the records and the refusal for the pane",
      len(cell_events) == 3 and cell_events[0]["reaches"][0]["kind"] == "net" and cell_events[0]["refused"] == "" and cell_events[2]["refused"] == "subprocess" and cell_events[2]["reaches"] == [],
      [(e.get("reaches"), e.get("refused")) for e in cell_events])
sm = reach.summary(rr)
check("reach: the summary lists each reach with its cell and tag, the refused attempt after the cell it followed, the counts and the box in one line",
      [(x["where"], x["kind"], x["tag"]) for x in sm["lines"]] == [("cell 1", "net", "asked"), ("cell 2", "file", "unasked")]
      and sm["refused"] == [{"where": "attempt after cell 2", "word": "subprocess", "text": "not run: restricted operation (subprocess)"}]
      and sm["counts"] == {"lines": 2, "unasked": 1, "asked": 1, "blocked": 0, "refused": 1, "net": 1} and sm["recorded"] is True
      and sm["lines"][0]["text"].startswith("fetched 3.") and "127.0.0.1" in sm["lines"][0]["text"] and sm["lines"][1]["text"] == "read /etc/hostname"
      and sm["sandbox"] and ("root" in sm["sandbox"]) and "metadata address" in sm["sandbox"], sm)
check("reach: a run without the record says so", reach.summary(Run(id="x", parent=None, question="q"))["recorded"] is False and reach.sandbox_line({}) == "", reach.summary(Run(id="x", parent=None, question="q")))
nbr2 = Notebook.from_dict(json.loads(json.dumps(nbr.to_dict())))
check("reach: the record survives the store's round trip", [t.reaches for t in nbr2.runs[rr.id].turns] == [t.reaches for t in rr.turns] and nbr2.runs[rr.id].sandbox == rr.sandbox
      and [t.refused for t in nbr2.runs[rr.id].turns] == [t.refused for t in rr.turns], [t.reaches for t in nbr2.runs[rr.id].turns])
# the tally (tools/reaches_report.py): the thread store and the run logs of a root folder, per model, the lines not asked for
import subprocess  # noqa: E402
_troot = tempfile.mkdtemp(prefix="bamboo_tally_")
NotebookStore(os.path.join(_troot, "storage", "u1")).save(nbr)
os.makedirs(os.path.join(_troot, "logs", "u1"))
json.dump([{"agent": "Investigator", "chain_id": rr.id, "model": "vendor/model-x", "cost": 0.01}, {"agent": "Rewriter", "chain_id": rr.id, "model": "vendor/small", "cost": 0.001}],
          open(os.path.join(_troot, "logs", "u1", "bambooai_run_log.json"), "w"))
_tally = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "reaches_report.py"), "--root", _troot, "--all"], capture_output=True, text=True, timeout=120)
check("the tally: runs, cells, reaches and refusals counted; the analyst's model from the run logs (not the rewriter's); the line not asked for with its cell and question; the refused word; the sandbox line",
      _tally.returncode == 0 and "runs 1 · cells 2 · reaches 2 (100.0 % of cells) · not asked for 1 · refused 1" in _tally.stdout
      and "vendor/model-x" in _tally.stdout and "vendor/small" not in _tally.stdout and "read /etc/hostname" in _tally.stdout and "question: \"Fetch the file from 127.0.0.1" in _tally.stdout
      and "refused (the blacklist)\n  subprocess 1" in _tally.stdout and "sandbox, every run: " in _tally.stdout and "metadata address" in _tally.stdout, (_tally.stdout[-1500:], _tally.stderr[-800:]))
check("reach: asked_for reads the host, its domain, the file's name and the environment name in the questions - a substring, nothing cleverer",
      reach.asked_for({"kind": "net", "host": "api.github.com"}, ["pull it from github.com please"]) is True
      and reach.asked_for({"kind": "net", "host": "api.github.com"}, ["fetch it from GitHub"]) is False
      and reach.asked_for({"kind": "file", "path": "/etc/passwd"}, ["show me passwd"]) is True
      and reach.asked_for({"kind": "env", "name": "HOME"}, ["use the home folder"]) is True
      and reach.asked_for({"kind": "env", "name": "*"}, ["*"]) is False
      and reach.asked_for({"kind": "net", "host": "10.0.0.5", "ip": ""}, ["connect to 10.0.0.5"]) is True, None)
check("reach: the record's lines in words",
      reach.line({"kind": "net", "host": "api.x.io", "port": 443, "in": 20480, "out": 812, "n": 1, "tls": True}) == "fetched 20.5 KB from api.x.io:443, sent 812 B over TLS"
      and reach.line({"kind": "net", "host": "h", "port": 80, "in": 0, "out": 0, "n": 2}) == "connected to h:80, nothing exchanged (2 connections)"
      and reach.line({"kind": "net", "host": "169.254.169.254", "port": 80, "blocked": True}) == "tried 169.254.169.254:80: the instance metadata address, refused by the kernel"
      and reach.line({"kind": "net", "host": "h", "port": 9, "failed": "ConnectionRefusedError: [Errno 111]"}) == "tried h:9: no connection (ConnectionRefusedError)"
      and reach.line({"kind": "net", "host": "h", "port": 80, "in": 5115, "out": 147, "n": 2, "failed": "ConnectionRefusedError: [Errno 111]"}) == "fetched 5.1 KB from h:80, sent 147 B (2 connections)"   # bytes outrank a first attempt's refusal (a v65 record)
      and reach.line({"kind": "file", "path": "/etc/passwd", "op": "read", "via": "library"}) == "read /etc/passwd (through a library)"
      and reach.line({"kind": "env", "name": "*"}) == "read the whole environment" and reach.line({"kind": "process", "command": "echo hi"}) == "started a program: echo hi"
      and reach.line({"kind": "listen", "host": "0.0.0.0", "port": 8080}) == "opened a listening port (0.0.0.0:8080)" and reach.line({"kind": "more", "n": 3}) == "3 more, not kept", None)

_subs = {"analyst." + f for f in os.listdir(os.path.join(ROOT, "analyst")) if os.path.isdir(os.path.join(ROOT, "analyst", f)) and f != "__pycache__"}
check("packaging: every subpackage of analyst/ is listed in pyproject's packages", _subs <= _pkgs, sorted(_subs - _pkgs))

# ---- the brief (2.8, docs/ARCHITECT_DESIGN.md §2.2, §2.5): what the person agreed before a run is handed to the analyst, kept
# ---- with the run, shown under the question every turn, and read back from the report; without one nothing changes
from analyst import brief as briefs
from analyst.session import REWRITE_BRIEF, BRIEF_UNANSWERED, BRIEF_AGAINST, BRIEF_MISFIT, CONTRACT_BRIEF
from analyst.notebook import has_data
_cb = contract(False, 0, brief=True)
check("brief: without one the contract and the reviewer's prompt are what they were; with one the contract gains The brief between How you work and Results and the two report parts between the answer and its conditions, and the reviewer the brief among what it receives; no placeholder is left in any variant",
      contract(False, 0) == CONTRACT and "brief" not in CONTRACT.lower() and reviewer_text(False) == REVIEWER and "BRIEF" not in REVIEWER
      and _cb.replace("\n" + CONTRACT_BRIEF, "", 1).replace(BRIEF_AGAINST + BRIEF_MISFIT, "", 1) == CONTRACT
      and _cb.index("## How you work") < _cb.index("## The brief") < _cb.index("## Results")
      and _cb.index("- the answer: the estimate") < _cb.index("- against the brief, under the heading `## Against the brief`") < _cb.index("- what did not fit, under the heading `## Did not fit`") < _cb.index("- the conditions it depends on")
      and "- the person's question, verbatim\n- BRIEF: what the person fixed" in reviewer_text(False, brief=True)
      and not any("{" + p in t for p in ("BRIEF", "REVIEWS", "DOCUMENTS", "READ_ROW", "WORDS", "LENSES") for t in (_cb, contract(True, 8, context=True, brief=True), reviewer_text(True, brief=True))))
check("brief, 0307: a brief that gives nothing to hold the result against asks for no part Against the brief - the contract then has what did not fit and not that part; held() says which: what the person expects, what would change their mind, "
      "a check of theirs - or data, whose three standing checks are lines of the part; no brief is never held",
      contract(False, 0, brief=True, held=False) == _cb.replace(BRIEF_AGAINST, "", 1) != _cb and BRIEF_MISFIT in contract(False, 0, brief=True, held=False) and contract(False, 0, held=False) == CONTRACT
      and [briefs.held(b, d) for b, d in (({"decision": "d"}, False), ({"decision": "d"}, True), ({"expects": "e"}, False), ({"would_change": "w"}, False), ({"also_check": [{"text": "c"}]}, False),
                                           ({"thinks": "t", "fixed": {"measure": "m"}, "rests_on": [{"text": "r"}]}, False), ({}, True), (None, True))]
      == [False, True, True, True, True, False, False, False] and briefs.held({"decision": "d"}) is True)
check("has_data: a run has data unless its record says nothing is loaded - no frame and no file beside one; a record that does not say, or none, is taken to have",
      [has_data(d) for d in ({"source": "none", "aux": []}, {"source": "none"}, {"source": "none", "aux": ["notes.csv"]}, {"source": "file"}, {"source": ""}, {}, None)] == [False, False, True, True, True, True, True])
check("brief: the report's part names its verdict words - met, not met, cannot tell; seen, not seen, cannot tell - and a check that could not be made is written with the same words (the page marks the line)",
      all(w in " ".join(BRIEF_AGAINST.split()) for w in ("a line `Expected:` with `met`, `not met` or `cannot tell` and the number that says so", "a line `Would change their mind:` with `seen`, `not seen` or `cannot tell`",
                                                       "then one line for each Also check line, with what it showed - or `cannot tell` and why.")))
check("brief: the contract's section says the six things the analyst does with it - the decision is what the answer is for, what is fixed is what is computed, what it rests on is a frame and not evidence, every Also check line is tested, a line under Saved analyses is an earlier analysis, which SHOW SAVED opens in the next prompt - its method may carry over, its numbers are history - and where the data cannot give what is fixed it asks",
      all(s in CONTRACT_BRIEF for s in ("What the answer is for: the report's opening paragraph says what the result means for it", "What is fixed before the run - the comparison, the measure, the period - is what you compute", "A part the brief\n  does not fix is yours to choose",
                                        "is the person's frame, not evidence", "Every line under Also check is tested", "put nothing else in its place: ASK, saying what is missing and what the data would\n  allow",
                                        "A line under Saved analyses is an earlier analysis with the passages the person chose from it. `SHOW SAVED <k>`\n  opens it in your next prompt: its report and the code of its cells. Its method may carry over: write it anew,\n"
                                        "  its names are not in your kernel. Its numbers are history about the data it ran on - another person's where the\n  line says so - and no result of this run.")))
_b_in = {"version": 3, "question": " Did  it work? ", "decision": "repeat it or not", "thinks": "it worked",
         "rests_on": ["the two were measured the same way", {"text": "the first was larger", "source": "data", "mark": "does not hold", "note": "41 against 44"},
                      {"text": "nothing else changed", "source": "nobody", "mark": "maybe"}, {"text": "  "}, {"text": "an earlier finding", "source": "result"}, {"text": "the logs are whole", "mark": "cannot be checked"}],
         "expects": "up by about 6.5 percent", "would_change": "no change in the second half",
         "also_check": [{"text": "the season", "shows": "the same change in both"}, "a new device", {"shows": "no text"}],
         "fixed": {"comparison": "after against before", "measure": "", "junk": "x"},
         "saved": [{"when": "March", "question": "an earlier question", "passage": "it was 3.1", "data": "the spring file", "odd": 1, "accepted": True}, {"data": "only data"}],
         "set_aside": ["a change of place", "", None], "unknown": {"a": 1}}
_b = briefs.normalise(_b_in)
check("brief.normalise: the parts with content in a known shape - text on one line, a bare string a line of the person's, an unknown source the person's and an unknown mark none, empty lines and unknown keys dropped, the version and the question kept",
      _b == {"decision": "repeat it or not", "thinks": "it worked", "expects": "up by about 6.5 percent", "would_change": "no change in the second half",
             "rests_on": [{"text": "the two were measured the same way", "source": "person", "mark": ""}, {"text": "the first was larger", "source": "data", "mark": "does not hold", "note": "41 against 44"},
                          {"text": "nothing else changed", "source": "person", "mark": ""}, {"text": "an earlier finding", "source": "result", "mark": ""}, {"text": "the logs are whole", "source": "person", "mark": "cannot be checked"}],
             "also_check": [{"text": "the season", "shows": "the same change in both"}, {"text": "a new device"}], "fixed": {"comparison": "after against before"},
             "saved": [{"when": "March", "question": "an earlier question", "passage": "it was 3.1", "data": "the spring file", "accepted": True}], "set_aside": ["a change of place"], "version": 3,
             "question": "Did it work?"}, _b)
_big = briefs.normalise({"rests_on": [f"line {i}" for i in range(20)], "also_check": [f"other {i}" for i in range(20)], "decision": "x" * 2000, "version": True})
check("brief.normalise: bounded - a line at most 600 characters, six lines to rest on and four to check also; a version that is no count is 1; nothing that frames the question is no brief (a bare question, an empty dict, a string)",
      len(_big["decision"]) == 600 and len(_big["rests_on"]) == 6 and len(_big["also_check"]) == 4 and _big["version"] == 1
      and briefs.normalise({"question": "only a question"}) == {} and briefs.normalise({}) == {} and briefs.normalise("a string") == {} and briefs.normalise({"fixed": {"junk": 1}, "rests_on": [" "]}) == {}, _big)
_long_q = "Did  it work?\n   What I saw:\t3 of 4.\n" + "x" * 700
check("brief: the question is the person's words, not a line of the brief - its lines kept, runs of spaces folded, bounded at 4,000 characters; so a brief's versions hold it whole (0296: cut at 600, a change to any part cut the run's question)",
      briefs.normalise({"decision": "d", "question": _long_q})["question"] == "Did it work?\nWhat I saw: 3 of 4.\n" + "x" * 700
      and briefs.working({"question": _long_q}) == {"question": "Did it work?\nWhat I saw: 3 of 4.\n" + "x" * 700}
      and len(briefs.normalise({"decision": "d", "question": "y" * 5000})["question"]) == briefs.QUESTION_CHARS == 4000
      and briefs.version({}, {"question": _long_q})["versions"][0]["brief"]["question"].count("\n") == 2 and "question" not in briefs.normalise({"decision": "d", "question": 7}))
# the thread record has one writer at a time (0296): a brief is changed by a request while a chain of its thread runs
import threading as _thr
_cs = NotebookStore(tempfile.mkdtemp()); _cn = Notebook("tc"); _cr = _cn.new_run("q"); _cr.report = "x" * 400000
_cerr = []
def _csave():
    try:
        for _ in range(25): _cs.save(_cn)
    except Exception as exc:                                  # noqa: BLE001
        _cerr.append(repr(exc))
_cts = [_thr.Thread(target=_csave) for _ in range(8)]
for _t in _cts: _t.start()
for _t in _cts: _t.join()
check("the thread record has one writer at a time: saves from several threads at once leave the file whole, and none fails",
      not _cerr and _cs.load("tc").runs[_cr.id].report == _cr.report, _cerr[:2])
_block = briefs.render(_b)
check("brief.render: the BRIEF block as the analyst reads it - every part that holds something on its line, each line it rests on with what it is worth (checked and what the check found, cannot be checked, an earlier result as a claim to test, the person's word), "
      "the three standing checks after the person's, of what is fixed the parts the person fixed and no other, the saved analyses as claims, what was set aside",
      _block == ("BRIEF (agreed with the person before this run):\n"
                 "What the answer is for: repeat it or not\n"
                 "What the person thinks: it worked\n"
                 "What it rests on:\n"
                 "- the two were measured the same way [the person's word, not checked]\n"
                 "- the first was larger [checked against the data: does not hold - 41 against 44]\n"
                 "- nothing else changed [the person's word, not checked]\n"
                 "- an earlier finding [from an earlier result: a claim to test]\n"
                 "- the logs are whole [cannot be checked]\n"
                 "What they expect to see: up by about 6.5 percent\n"
                 "What would change their mind: no change in the second half\n"
                 "Also check:\n"
                 "- the season: it would show the same change in both\n"
                 "- a new device\n"
                 "- chance [always]\n"
                 "- measurement error [always]\n"
                 "- how the cases compared came to be chosen [always]\n"
                 "Fixed before the run:\n"
                 "- comparison: after against before\n"
                 "Saved analyses the person chose (earlier results: claims to test, not evidence):\n"
                 "1. March \"an earlier question\" (the spring file): \"it was 3.1\"\n"
                 "Set aside (considered and dropped): a change of place"), _block)
_thin = briefs.render(briefs.normalise({"fixed": {"period": "the last year"}}))
check("brief.render, 0307: a part the person did not state is not there - no line says 'not said' or 'left to you' (a live run's analyst read five such lines under a brief of two); the three standing checks are listed "
      "for a run on data and for no other; no brief renders nothing",
      _thin == ("BRIEF (agreed with the person before this run):\nAlso check:\n- chance [always]\n- measurement error [always]\n- how the cases compared came to be chosen [always]\n"
                "Fixed before the run:\n- period: the last year") and briefs.render({}) == "" and briefs.render({}, data=False) == ""
      and briefs.render(briefs.normalise({"fixed": {"period": "the last year"}}), data=False) == "BRIEF (agreed with the person before this run):\nFixed before the run:\n- period: the last year"
      and briefs.render(briefs.normalise({"decision": "to see it", "thinks": "it holds", "also_check": ["the season"]}), data=False)
      == "BRIEF (agreed with the person before this run):\nWhat the answer is for: to see it\nWhat the person thinks: it holds\nAlso check:\n- the season"
      and briefs.render(_b, data=False) == _block.replace("- chance [always]\n- measurement error [always]\n- how the cases compared came to be chosen [always]\n", "")
      and not any(w in briefs.render(b, data=d) for w in ("not said", "left to you") for b in (_b, briefs.normalise({"decision": "d"})) for d in (True, False)), _thin)
check("brief.render, as a record keeps it: the parts that hold something, a line each - no heading, none of the checks every run on data makes, with data or without",
      briefs.render(_b, record=True) == _block.split("\n", 1)[1].replace("- chance [always]\n- measurement error [always]\n- how the cases compared came to be chosen [always]\n", "") == briefs.render(_b, record=True, data=False)
      and briefs.render(briefs.normalise({"fixed": {"period": "the last year"}}), record=True) == "Fixed before the run:\n- period: the last year"
      and briefs.render(briefs.normalise({"expects": "a rise", "also_check": ["the season"]}), record=True) == "What they expect to see: a rise\nAlso check:\n- the season"
      and briefs.render(briefs.normalise({"thinks": "it worked"}), record=True) == "What the person thinks: it worked" and briefs.render({}, record=True) == "",
      briefs.render(_b, record=True))
_rep = ("# Title\n\n## Answer\nx\n\n## Against the brief\n- **Expected:** not met - the rise was 1.2 percent [cell 3].\n- Would change their mind: seen - no rise in the second half.\n"
        "- The season: the same change in both [cell 4].\n* Chance: the interval includes zero.\n\n## Did not fit\n- The smaller one came first [cell 4].\n1. A second thing.\n\n## Limitations\ny\n\n> CHECK: something")
_o = briefs.outcome(_rep)
check("brief.outcome: what the report says against the brief - the verdict on what was expected ('not met' is not read as 'met'), on what would change the person's mind, the other lines as the checks, what did not fit; each part ends at the next heading",
      _o == {"stated": True, "expected": "not met", "would_change": "seen", "checks": ["The season: the same change in both [cell 4].", "Chance: the interval includes zero."],
             "did_not_fit": ["The smaller one came first [cell 4].", "A second thing."]}, _o)
check("brief.outcome: the verdict words each read - met, cannot tell; not seen; a part that says Nothing holds nothing; a report without the part has not stated it, one whose part gives no verdict has - with the verdict empty; a CHECK line under the part is not one of its lines",
      briefs.outcome("## Against the brief\nExpected: met, as said\nWould change their mind: not seen\n## Did not fit\nNothing.\n") == {"stated": True, "expected": "met", "would_change": "not seen", "checks": [], "did_not_fit": []}
      and briefs.outcome("### against the brief:\n- Expectation - cannot tell: no data for it\n")["expected"] == "cannot tell"
      and briefs.outcome("# t\n\n## Answer\nmet\n")["stated"] is False
      and briefs.outcome("## Against the brief\n- The season: nothing.\n") == {"stated": True, "expected": "", "would_change": "", "checks": ["The season: nothing."], "did_not_fit": []}
      and briefs.outcome("## Did not fit\n- One thing.\n\n> CHECK: 1 number(s) in this report were not printed by any cell (7.7).")["did_not_fit"] == ["One thing."])
# a scripted run under the brief, over a real kernel
_bdf = pd.DataFrame({"part": np.repeat(["before", "after"], 30), "y": np.r_[np.full(30, 100.0), np.full(30, 101.2)]})
_bseen = {"system": [], "user": [], "rewrite": []}
def _bact(a): return "###STEP###\ns.\n###NOTE###\n" + NOTE5 + "\n###ACTION###\n" + a
_BREPORT = ("REPORT\n# After was 1.2 percent higher than before\n\nA small rise.\n\n## Answer\nAfter was 1.2 percent higher [cell 1].\n\n## Against the brief\n- Expected: not met - 1.2 percent, not about 6.5 percent [cell 1].\n"
            "- Would change their mind: cannot tell.\n- The season: not separable here, and 77.7 is invented.\n- Chance: none, the values are constant [cell 1].\n\n## Did not fit\n- The first was larger and the rise still came [cell 1].\n\n## Limitations\nSixty rows.")
def _brief_llm(script):
    state = {"i": 0}
    def llm(system, user, **h):
        if user.startswith("Rewrite the technical report"):
            _bseen["rewrite"].append(user); return "# After was 1.2 percent higher than before\n\nplain", {"cost": 0}
        if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
        _bseen["system"].append(system); _bseen["user"].append(user)
        t = script[min(state["i"], len(script) - 1)]; state["i"] += 1
        return t, {"cost": 0.001}
    return llm
_CELL = _bact("```python\nm = df.groupby('part')['y'].mean()\npct = round(100 * (m['after'] / m['before'] - 1), 1)\nRESULT('y, after vs before, 30 rows each', pct, pct, pct, 'percent', 'after higher')\n```")
kb = PersistentKernel(df=_bdf); store_b = NotebookStore(tempfile.mkdtemp()); nb_b = Notebook("tb")
try:
    sb = Session(kb, nb_b, _brief_llm([_CELL, _bact(_BREPORT)]), store=store_b, data_description="60 rows: part, y", kernel_factory=lambda: PersistentKernel(df=_bdf))
    rb = sb.run("Did it work?", budget=Budget(turns=6, dollars=1.0), brief=_b_in)
finally:
    kb.cleanup()
check("brief in a run: every turn's prompt carries the BRIEF block under the question, and the contract of the run has The brief and the two report parts",
      rb.status == "answered" and len(_bseen["user"]) == 2 and all(("QUESTION:\nDid it work?\n\n" + _block + "\n\nYOUR NOTE") in u for u in _bseen["user"]) and all(sy == _cb for sy in _bseen["system"]),
      (rb.status, _bseen["user"][0][:600]))
check("brief in a run: the run keeps the brief as it was handed over and what the report says against it; a number the brief states is the person's own, so the report may repeat it, and an invented one is still said",
      rb.brief == _b and rb.brief_outcome == {"stated": True, "expected": "not met", "would_change": "cannot tell",
                                               "checks": ["The season: not separable here, and 77.7 is invented.", "Chance: none, the values are constant [cell 1]."],
                                               "did_not_fit": ["The first was larger and the rise still came [cell 1]."]}
      and "> CHECK: 1 number(s) in this report were not printed by any cell (77.7). Treat them as unverified." in rb.report and BRIEF_UNANSWERED not in rb.report, (rb.brief_outcome, rb.report[-300:]))
check("brief in a run: the plain-language version is asked to keep the two parts under their headings; the record on disk holds the brief and its outcome",
      len(_bseen["rewrite"]) == 1 and _bseen["rewrite"][0].startswith(REWRITE_TASK + REWRITE_BRIEF + "# After was 1.2 percent higher than before")
      and store_b.load("tb").runs[rb.id].brief == _b and store_b.load("tb").runs[rb.id].brief_outcome == rb.brief_outcome, _bseen["rewrite"][0][-400:])
# without a brief: nothing of it anywhere
_bseen = {"system": [], "user": [], "rewrite": []}
kb = PersistentKernel(df=_bdf); nb_p = Notebook("tp")
try:
    rp = Session(kb, nb_p, _brief_llm([_bact("REPORT\n# A title\n\n## Answer\nNothing was computed.")]), data_description="60 rows: part, y", kernel_factory=lambda: PersistentKernel(df=_bdf)).run("Did it work?", budget=Budget(turns=4, dollars=1.0))
finally:
    kb.cleanup()
check("no brief: the run has none, its prompts carry no BRIEF block, its contract is the plain one, its rewrite task the plain one, and its report is asked nothing about a brief",
      rp.brief == {} and rp.brief_outcome == {} and not any("BRIEF" in u for u in _bseen["user"]) and _bseen["system"] == [CONTRACT]
      and _bseen["rewrite"][0].startswith(REWRITE_TASK + "# A title") and BRIEF_UNANSWERED not in rp.report, (rp.brief, _bseen["system"][0][:80]))
# the analyst stops and asks; the person's answer runs under the same brief
_bseen = {"system": [], "user": [], "rewrite": []}
kb = PersistentKernel(df=_bdf); nb_a = Notebook("ta")
try:
    sa = Session(kb, nb_a, _brief_llm([_bact("ASK The brief fixes a measure the data does not record. The data would allow y instead: use it?"),
                                       _bact("REPORT\n# With y, after was higher\n\n## Answer\nUsing y.\n\n## Against the brief\n- Expected: cannot tell - the measure was changed.\n\n## Did not fit\nNothing."),
                                       _bact("REPORT\n# A follow-up\n\n## Answer\nOn its own.")]),
                 data_description="60 rows: part, y", kernel_factory=lambda: PersistentKernel(df=_bdf))
    ra = sa.run("Did it work?", budget=Budget(turns=4, dollars=1.0), brief=_b_in)
    ra2 = sa.run("Yes, use y.", parent=ra.id, budget=Budget(turns=4, dollars=1.0))
    ra3 = sa.run("And the first half alone?", parent=ra2.id, budget=Budget(turns=4, dollars=1.0))
finally:
    kb.cleanup()
check("brief, stop and ask: a run that ends on the analyst's question keeps its brief and has no outcome; the person's answer runs under the same brief without it being sent again - the block says it was agreed before the question and that the answer stands where "
      "the two differ - and its report is read against it; a follow-up to an answered run has no brief of its own unless one is given",
      ra.status == "asked" and ra.brief == _b and ra.brief_outcome == {} and ra2.brief == {**_b, "carried_from": ra.id}
      and "QUESTION:\nYes, use y.\n\nBRIEF (agreed before your question; the QUESTION above is the person's answer, and it stands where the two differ):\nWhat the answer is for: repeat it or not\n" in _bseen["user"][1]
      and _bseen["system"][1] == _cb and ra2.brief_outcome["expected"] == "cannot tell" and ra2.brief_outcome["did_not_fit"] == []
      and ra3.brief == {} and "BRIEF" not in _bseen["user"][2] and _bseen["system"][2] == CONTRACT, (ra.status, ra2.brief.get("carried_from"), _bseen["user"][1][:300]))
# a briefed report that does not say how the result stands against the brief
kb = PersistentKernel(df=_bdf); nb_u = Notebook("tu")
try:
    ru = Session(kb, nb_u, _brief_llm([_bact("REPORT\n# A title\n\n## Answer\nNo part for the brief here.")]), data_description="60 rows: part, y", kernel_factory=lambda: PersistentKernel(df=_bdf)).run("Did it work?", budget=Budget(turns=4, dollars=1.0), brief={"expects": "a rise"})
finally:
    kb.cleanup()
check("brief: a report that does not say how the result stands against the brief carries a line saying so, and the outcome is not stated",
      ru.report.rstrip().endswith("> " + BRIEF_UNANSWERED) and ru.brief_outcome["stated"] is False and ru.brief_outcome["expected"] == "", ru.report[-200:])
# a brief written by hand has parts left empty (0296): a part not said asks for no line, and its absence is no fault
_PART = "REPORT\n# A title\n\n## Answer\nDone.\n\n## Against the brief\n- chance: fine.\n\n## Did not fit\nNothing."
def _part_run(brief, report=_PART, data=None):
    k = PersistentKernel(df=_bdf)
    try:
        return Session(k, Notebook("tp"), _brief_llm([_bact(report)]), data_description="60 rows: part, y", kernel_factory=lambda: PersistentKernel(df=_bdf)).run("Did it work?", budget=Budget(turns=4, dollars=1.0), brief=brief, data=data)
    finally:
        k.cleanup()
_rn, _re = _part_run({"decision": "keep it or not"}), _part_run({"decision": "keep it or not", "expects": "a rise"})
_rm = _part_run({"decision": "keep it or not"}, "REPORT\n# A title\n\n## Answer\nNo part for the brief here.")
check("brief: a part the person left unsaid asks for no verdict line - the contract says so in the block's own word - and a report without that line is answered; where they said what they expect, a part with no verdict on it is not; "
      "a report with no part at all is not, whatever the brief left unsaid",
      "A part the brief does not give has no line" in BRIEF_AGAINST and "What they expect to see" not in briefs.render(briefs.normalise({"decision": "d"}))
      and BRIEF_UNANSWERED not in _rn.report and _rn.brief_outcome == {"stated": True, "expected": "", "would_change": "", "checks": ["chance: fine."], "did_not_fit": []}
      and _re.report.rstrip().endswith("> " + BRIEF_UNANSWERED) and _re.brief_outcome["stated"] is True and _re.brief_outcome["expected"] == ""
      and _rm.report.rstrip().endswith("> " + BRIEF_UNANSWERED) and _rm.brief_outcome["stated"] is False, (_rn.report[-160:], _re.report[-160:], _rm.report[-160:]))
# a run without data (0307): the three standing checks have nothing to run on, so a brief that states no expectation and no check of the
# person's own gives nothing to hold the result against
_NONE, _BARE = {"source": "none", "aux": []}, "REPORT\n# A title\n\n## Answer\nDrawn.\n\n## Did not fit\nNothing."
_bseen = {"system": [], "user": [], "rewrite": []}
_nd1, _nd2, _nd3 = _part_run({"decision": "to see it", "thinks": "it holds"}, _BARE, _NONE), _part_run({"decision": "to see it", "expects": "a rise"}, _BARE, _NONE), _part_run({"decision": "to see it"}, _BARE, {"source": "none", "aux": ["notes.csv"]})
check("brief, a run without data: its BRIEF block lists no standing check, its contract asks for what did not fit and for no part Against the brief, and a report without that part is not said to leave the brief unanswered - the rewrite is asked "
      "to keep the parts the report has; where the person said what they expect the part is asked for and its absence said, without data too; a run on files beside no frame is a run on data",
      _bseen["system"][0] == contract(False, 0, brief=True, held=False) and "QUESTION:\nDid it work?\n\nBRIEF (agreed with the person before this run):\nWhat the answer is for: to see it\nWhat the person thinks: it holds\n\nYOUR NOTE" in _bseen["user"][0]
      and BRIEF_UNANSWERED not in _nd1.report and _nd1.brief_outcome["stated"] is False and _nd1.brief_outcome["did_not_fit"] == []
      and _bseen["rewrite"][0].startswith(REWRITE_TASK + REWRITE_BRIEF) and REWRITE_BRIEF.startswith("Where the report has a part `## Against the brief` or `## Did not fit`, keep it under that heading")
      and _bseen["system"][1] == _cb and "[always]" not in _bseen["user"][1] and _nd2.report.rstrip().endswith("> " + BRIEF_UNANSWERED)
      and _bseen["system"][2] == _cb and "- chance [always]" in _bseen["user"][2] and _nd3.report.rstrip().endswith("> " + BRIEF_UNANSWERED), (_bseen["user"][0][:400], _nd1.report[-200:]))
# the reviewer reads the brief (Adaptive)
_rvb = {"system": [], "user": []}
def _rvb_llm(system, user, **h):
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    if system.startswith("You are the reviewer"):
        _rvb["system"].append(system); _rvb["user"].append(user)
        return "###REVIEW###\n- The question requires: x\n- Established: y [cell 1]\n- Checked: cell 1 - computes it; matches its line\n- Most consequential problem: none\n- Verdict: REPORT done [cell 1]", {"cost": 0.001}
    return (_bact("REPORT\n# T\n\n## Answer\nDone [cell 1].\n\n## Against the brief\n- Expected: met [cell 1].\n\n## Did not fit\nNothing.") if "this turn is the report" in user else _CELL), {"cost": 0.001}
kb = PersistentKernel(df=_bdf); nb_r = Notebook("tr")
try:
    rr = Session(kb, nb_r, _rvb_llm, data_description="60 rows: part, y", kernel_factory=lambda: PersistentKernel(df=_bdf)).run("Did it work?", budget=Budget(turns=8, dollars=1.0, review_every=2), brief=_b_in)
finally:
    kb.cleanup()
check("brief, the reviewer: with a brief its prompt names the brief among what it receives and its input carries the BRIEF block under the question, before the data - during the run and after the report",
      len(_rvb["user"]) >= 2 and all(sy == reviewer_text(False, brief=True) for sy in _rvb["system"]) and all(u.startswith("QUESTION:\nDid it work?\n\n" + _block + "\n\nDATA:\n") for u in _rvb["user"])
      and rr.brief_outcome["expected"] == "met", (len(_rvb["user"]), _rvb["user"][0][:200] if _rvb["user"] else None))
_btexts = {"contract (brief)": _cb, "reviewer (brief)": reviewer_text(True, brief=True), "the block": _thin, "rewrite, brief": REWRITE_BRIEF, "unanswered": BRIEF_UNANSWERED}
for _k, _t in enumerate(_authored_strings("analyst/brief.py")):
    _btexts[f"analyst/brief.py string {_k}"] = _t
check("brief: the standing rules hold for its texts too - none of the tested tasks' vocabulary, and no section named for thinking or reasoning, in the contract with a brief, the reviewer's prompt with one, the block's own words, the rewrite's sentence and every string of analyst/brief.py",
      not {n: sorted({m.group(0) for m in _DOMAIN.finditer(t)}) for n, t in _btexts.items() if _DOMAIN.search(t)}
      and not any(_re_c.search(r"(?i)\b(thinking|reasoning|scratchpad|memory|private)\b", t) for t in (_cb, reviewer_text(True, brief=True), _thin)),
      {n: sorted({m.group(0) for m in _DOMAIN.finditer(t)}) for n, t in _btexts.items() if _DOMAIN.search(t)})

# ---- the Pathfinder (0297, docs/ARCHITECT_DESIGN.md §2.12): one exchange is one model call, and its reply is written into the brief
from analyst import architect as arch
from analyst import lookup
_wb = {"question": "Is B above A?", "decision": "keep one arm", "rests_on": [{"text": "B looked better", "source": "person", "mark": "holds", "note": "seen in 9 of 12"}, {"text": "a count from the data", "source": "data", "mark": "holds"}],
       "also_check": [{"text": "the two halves differ", "shows": "a gap in one half only"}], "fixed": {"measure": "x"}, "saved": [{"question": "Was B above A before?", "passage": "B led by 3.", "accepted": False}], "set_aside": ["the weather"], "version": 4}
_wb_before = json.dumps(_wb, sort_keys=True)
_w1, _c1 = briefs.write(_wb, {"decision": "  keep   both arms ", "thinks": "B is better", "expects": "", "fixed": {"period": "the first half", "measure": "x"}})
_w2, _c2 = briefs.write(_wb, {"decision": "", "fixed": {"measure": ""}})
_wq, _cq = briefs.write(_wb, {"question": "  Is B above A,\n on   x? ", "decision": "keep one arm"})
check("brief.write: the parts a reply names are written in - a text part on one line, an empty string emptying it, what is fixed part by part - and each part that changed is named as the page names it; a part given as it "
      "stands changes nothing; the rest of the brief - its lists, the saved analyses, what was set aside, the question - is untouched, the version number left to the caller, the brief passed in not altered. "
      "The question is written as a wording, its lines kept - named first among what changed - and is never emptied",
      _w1["decision"] == "keep both arms" and _w1["thinks"] == "B is better" and "expects" not in _w1 and _w1["fixed"] == {"measure": "x", "period": "the first half"} and _c1 == ["decision", "thinks", "fixed.period"]
      and all(_w1[k] == _wb[k] for k in ("rests_on", "also_check", "saved", "set_aside", "question")) and "version" not in _w1
      and "decision" not in _w2 and "fixed" not in _w2 and _c2 == ["decision", "fixed.measure"] and briefs.write(_wb, {"decision": "keep one arm", "fixed": {"measure": " x "}})[1] == []
      and briefs.write(_wb, {})[1] == [] and briefs.write(_wb, None)[0] == briefs.working(_wb)
      and (_wq["question"], _cq) == ("Is B above A,\non x?", ["question"]) and briefs.write(_wb, {"question": "", "decision": ""}) == (briefs.working({**_wb, "decision": ""}), ["decision"])
      and briefs.write(_wb, {"question": " Is B above A? "})[1] == [] and briefs.write(_wb, {"question": ["no"]})[1] == []
      and json.dumps(_wb, sort_keys=True) == _wb_before, (_w1, _c1, _w2, _c2, _wq, _cq))
_w3, _c3 = briefs.write(_wb, {"rests_on": [" B looked   better ", "a third thing", {"text": "a fourth"}, "a fifth", "a third thing"], "also_check": ["luck", "the two halves differ", "a third rival"]})
_w4, _c4 = briefs.write(_wb, {"drop": [" B looked   better ", "the two halves differ", "not there"], "rests_on": ["B looked best"]})
check("brief.write, the lists: a line given under a list's name is added when it is not there yet - a line of the person's with no mark, named by its place - and the lines the reply does not name stay as they "
      "are, with their source, their mark and what the check found; a line given twice is one; the lists stop at the design's counts, four and two. A line given under drop is taken out of either list when it is "
      "there word for word, and the list is named as changed; a list emptied goes",
      _w3["rests_on"] == _wb["rests_on"] + [{"text": "a third thing", "source": "person", "mark": ""}, {"text": "a fourth", "source": "person", "mark": ""}]
      and _w3["also_check"] == [_wb["also_check"][0], {"text": "luck"}] and _c3 == ["rests_on.2", "rests_on.3", "also_check.1"]
      and _w4["rests_on"] == [_wb["rests_on"][1], {"text": "B looked best", "source": "person", "mark": ""}] and "also_check" not in _w4 and _c4 == ["rests_on", "rests_on.1", "also_check"]
      and briefs.write(_wb, {"rests_on": ["B looked better", "a count from the data"]})[1] == [] and briefs.write(_wb, {"drop": ["nothing like it"], "rests_on": "a string", "also_check": {"text": "x"}})[1] == []
      and briefs.write(_wb, {"drop": ["a count from the data"]})[0]["rests_on"] == [_wb["rests_on"][0]] and briefs.write(_wb, {"drop": "B looked better"})[1] == []
      and briefs.COUNTS == {"rests_on": 4, "also_check": 2}, (_w3, _c3, _w4, _c4))
_fv = briefs.version(briefs.version({}, {"question": "q"}), {"question": "q", "decision": "d"}, by="architect", changed=["decision"], why="question")
check("brief.version: a version of the Pathfinder's says what it was made from; a version without a reason carries none",
      _fv["versions"][1] == {"n": 2, "by": "architect", "changed": ["decision"], "brief": {"decision": "d", "question": "q"}, "why": "question"} and "why" not in _fv["versions"][0], _fv)

_reply = {"brief": {"decision": "keep one arm"}, "say": "  Two things could be   looked at. \n\n\n\n- the gap \n-\tthe trend\n\nWhich one?  \n", "choices": ["  Keep one arm ", "Keep both", "Keep one arm", "", 7, "c", "d", "e"]}
_parsed = arch.parse("Here it is:\n```json\n" + json.dumps(_reply) + "\n```\nAnything else?")
def _unreadable(text):
    try:
        arch.parse(text)
    except arch.Unreadable as exc:
        return str(exc)
    return None
_none = {"wording": "", "lookups": [], "marks": [], "propose": [], "recall": False, "build": None, "figures": None, "open": None}
_asks = arch.parse(json.dumps({"say": "Checking.", "lookups": [{"op": "count"}, "count", 3, {"op": "x"}, {}, {}, {}, {}], "marks": [{"line": "l", "mark": "holds"}, "no"]}))
check("architect.parse: the reply's JSON object, bare or fenced, with words around it: the parts it writes, its message with its lines - each on one line of text, one empty line at most between two "
      "paragraphs, bounded - its choices cleaned - none twice, none empty, four at most; a reply without a brief writes nothing. The lookups it asks for and the marks it gives come through as given - the "
      "lookups six at most - and a reply without them has none. A new line that stands inside a string as it is does not make the reply unreadable",
      _parsed == {"brief": {"decision": "keep one arm"}, "say": "Two things could be looked at.\n\n- the gap\n- the trend\n\nWhich one?", "choices": ["Keep one arm", "Keep both", "c", "d"], **_none}
      and arch.parse('{"say": "Ready."}') == {"brief": {}, "say": "Ready.", "choices": [], **_none}
      and arch.parse('note {"say": "x", "brief": ["no"], "choices": "no", "lookups": {"op": "count"}, "marks": "holds"} end') == {"brief": {}, "say": "x", "choices": [], **_none}
      and _asks["lookups"] == [{"op": "count"}, "count", 3, {"op": "x"}, {}, {}] and len(_asks["lookups"]) == lookup.MAX_LOOKUPS and _asks["marks"] == [{"line": "l", "mark": "holds"}, "no"]
      and arch.parse('I could write {this}:\n```json\n{"say": "x"}\n```')["say"] == "x"
      and len(arch.parse(json.dumps({"say": "y" * 7000}))["say"]) == arch.SAY_CHARS == 6000 and arch.parse(json.dumps({"say": "y" * 5999 + " \n z"}))["say"] == "y" * 5999
      and arch.parse(json.dumps({"say": "word " * 320}))["say"] == ("word " * 320).strip()               # 0307: a message of 1,600 characters is kept whole (a live one of 1,559 lost its last sentence at 1,500)
      and arch.parse('{"say": "One line.\nAnother."}')["say"] == "One line.\nAnother." and arch._say(7) == "", _parsed)
_p7 = arch.parse(json.dumps({"say": "x", "wording": "  Plot   x against z.\n  Two starts. ", "build": [2, "3", True, 1.0, 4], "open": {"what": "cell", "n": 3}}))
check("architect.parse, 0308: a wording of the question comes through with its lines, as a question is kept; the saved analyses to build on as whole numbers and nothing else - an empty list is a "
      "list, to build on none, and a reply that does not say gives None, which changes nothing; what to open as the object given - and none of the three where the reply gives something else in "
      "their place. A reply's `accept` and `tick` (0307) are read no longer",
      (_p7["wording"], _p7["build"], _p7["open"]) == ("Plot x against z.\nTwo starts.", [2, 4], {"what": "cell", "n": 3})
      and [arch.parse(json.dumps({"say": "x", "build": b}))["build"] for b in ([], [1], 1, "1", None, {"1": 1})] == [[], [1], None, None, None, None]
      and arch.parse(json.dumps({"say": "x", "wording": ["no"], "build": 2, "open": "report", "accept": True, "tick": [1]})) == {"brief": {}, "say": "x", "choices": [], **_none}
      and len(arch.parse(json.dumps({"say": "x", "wording": "w" * 5000}))["wording"]) == briefs.QUESTION_CHARS, _p7)
check("architect.parse: a reply that is not the object asked for says what is wrong with it - no object, JSON that does not parse, not an object, no message",
      _unreadable("I would ask about the decision.") == "it holds no JSON object" and _unreadable("") == "it holds no JSON object" and _unreadable('{"say": "x",}').startswith("its JSON does not parse: ")
      and _unreadable('{"brief": {}}') == 'it has no "say"' and _unreadable('{"say": "  "}') == 'it has no "say"' and _unreadable("[1, 2]") == "it holds no JSON object",
      [_unreadable(t) for t in ("x", '{"say": "x",}', '{"brief": {}}', "[1, 2]")])
_ab = arch.block({**_wb, "thinks": "B is better"})
_bf = [{"thread": "7", "run": "8", "when": "2026-03-02", "question": "q1", "passage": "p1"}, {"thread": "7", "run": "9", "when": "2026-03-03", "question": "q2", "passage": "p2"},
       {"thread": "7", "run": "9", "when": "2026-03-03", "question": "q2", "passage": "p3"}]
check("architect.block: the brief as the Pathfinder reads it - every part under the name its reply uses, the lists a line each, an empty part said to be empty, with the version that stands; a line the brief "
      "rests on shows its mark in brackets, with what was found when there is any, and a line not checked shows none. The saved analyses the brief builds on (0308) stand under builds_on, an analysis "
      "to a line under the number the readings gave it - the one a reply builds on it by: said to be empty where readings found some and none is built on, absent where nothing was read; a passage "
      "the person did not accept (a brief of 0307) is not one built on",
      _ab == ("BRIEF (version 4):\ndecision: keep one arm\nthinks: B is better\nrests_on:\n- B looked better [holds - seen in 9 of 12]\n- a count from the data [holds]\nexpects: (empty)\nwould_change: (empty)\n"
              "also_check:\n- the two halves differ\nfixed.comparison: (empty)\nfixed.measure: x\nfixed.period: (empty)")
      and arch.block({"question": "q", "rests_on": [{"text": "said, not checked", "source": "person", "mark": ""}]}).splitlines()[3:5] == ["rests_on:", "- said, not checked"]
      and arch.block({"question": "q"}).splitlines()[:4] == ["BRIEF (version 1):", "decision: (empty)", "thinks: (empty)", "rests_on: (empty)"] and "builds_on" not in arch.block({"question": "q"})
      and arch.block({"question": "q"}, _bf).splitlines()[-1] == "builds_on: (empty)"
      and arch.block({"saved": [{**_bf[1], "accepted": True}, {**_bf[2], "accepted": True}]}, _bf).splitlines()[-2:] == ["builds_on:", '- [2] 2026-03-03 "q2"']
      and arch.block({"saved": [{**_bf[0], "accepted": True}, {**_bf[1], "accepted": True}]}, _bf).splitlines()[-3:] == ["builds_on:", '- [1] 2026-03-02 "q1"', '- [2] 2026-03-03 "q2"']
      and arch.block({"saved": [{**_bf[0], "accepted": True}]}).splitlines()[-2:] == ["builds_on:", '- [-] 2026-03-02 "q1"']
      and arch.block({"saved": [{**_bf[0], "accepted": False}]}, _bf).splitlines()[-1] == "builds_on: (empty)" and arch._numbers(_bf) == {"7/8": 1, "7/9": 2} and arch._numbers(None) == {}, _ab)
_anb = Notebook("arch")
_a0 = _anb.new_run("Does B beat A?"); _a0.status = "answered"; _a0.brief = {"decision": "d", "version": 2}
_a0.report = "B beats A by 3 units. It holds in both halves.\n\n## Against the brief\n- Expected: not met - the gap is 3\n- Would change their mind: seen\n\n## Did not fit\n- The late rows lag.\n- One site reverses."
_a0.brief_outcome = briefs.outcome(_a0.report)
_a1 = _anb.new_run("And on x?", _a0.id); _a1.status = "asked"; _a1.turns.append(Turn(kind="cell", code="1")); _a1.turns.append(Turn(kind="ask", text="The data has no x.\nShall I use y?"))
_a2 = _anb.new_run("Use y.", _a1.id); _a2.status = "framing"; _a2.framing = briefs.version({}, {"question": "Use y.", "decision": "d"}, changed=["from the last brief"])
_ae = arch.earlier(_anb, _a2.id)
check("architect.earlier: the analyses the question follows, oldest first - each one's question and what it found, how the result stood against its brief and what did not fit; where the analyst stopped and "
      "asked, what it asked, on one line; nothing for a question that follows none",
      _ae == ("EARLIER (the analyses this question follows, oldest first):\n[1] Q: Does B beat A?\n    Found: B beats A by 3 units. It holds in both halves.\n"
              "    Against its brief - what they expected: not met; what would change their mind: seen\n    Did not fit: The late rows lag.; One site reverses.\n"
              "[2] Q: And on x?\n    The analyst stopped and asked: The data has no x. Shall I use y?")
      and arch.earlier(_anb, _a0.id) == "" and arch.earlier(_anb, "nowhere") == "", _ae)
_ap = arch.prompt("Use y.", briefs.latest(_a2.framing), [{"who": "architect", "text": "Ready?"}, {"who": "person", "text": "yes"}], data="`df`: 3 rows", before=_ae)
check("architect.prompt: what does not change from one reply to the next comes first - the data's description, the analyses the question follows - then the question, the brief, the conversation under who "
      "said what, and one line asking for the object; without data or earlier analyses those parts are not there, and a conversation not yet begun says so",
      _ap == "DATA:\n`df`: 3 rows\n\n" + _ae + "\n\nQUESTION:\nUse y.\n\n" + arch.block(briefs.latest(_a2.framing)) + "\n\nCONVERSATION:\nPathfinder: Ready?\nPerson: yes\n\nReply with the JSON object."
      and arch.prompt("q", {"question": "q"}, []) == "QUESTION:\nq\n\n" + arch.block({"question": "q"}) + "\n\nCONVERSATION:\n(nothing yet)\n\nReply with the JSON object.", _ap)

def _arch_llm(replies, usage=None):
    seen = []
    def llm(system, user, **kw):
        seen.append((system, user, kw))
        return replies.pop(0), dict(usage or {"cost": 0.004})
    return llm, seen
_xn = Notebook("x"); _xr = _xn.new_run("Is B above A?"); _xr.status = "framing"; _xr.framing = briefs.version({}, {"question": _xr.question})
_llm1, _seen1 = _arch_llm([json.dumps({"brief": {"fixed": {"comparison": "B against A"}}, "say": "What will you do differently depending on the answer?", "choices": ["Keep B", "Keep A"]})])
_f1 = arch.exchange(_llm1, _xn, _xr, None, data="`df`: 3 rows")
check("architect.exchange, its first turn: one call - its instructions, the prompt with the brief as it stands and no conversation, the lowered effort - and the reply taken in: the part it wrote as one more "
      "version, the Pathfinder's, made from the question; its message with its choices in the conversation, with the version that then stands, what the call cost and the call's number; the run's own framing not touched",
      len(_seen1) == 1 and _seen1[0][0] == arch.SYSTEM and _seen1[0][1] == arch.prompt(_xr.question, briefs.latest(_xr.framing), [], "`df`: 3 rows") and _seen1[0][2] == {"effort": ("medium", "low")} == {"effort": arch.EFFORT}
      and [(v["n"], v["by"], v.get("why"), v["changed"]) for v in _f1["versions"]] == [(1, "person", None, []), (2, "architect", "question", ["fixed.comparison"])]
      and _f1["versions"][1]["brief"] == {"fixed": {"comparison": "B against A"}, "question": "Is B above A?"}
      and _f1["turns"] == [{"who": "architect", "text": "What will you do differently depending on the answer?", "choices": ["Keep B", "Keep A"], "v": 2, "cost": 0.004, "call": 1}] and _f1["calls"] == 1
      and len(_xr.framing["versions"]) == 1 and "turns" not in _xr.framing, _f1)
_xr.framing = _f1
_llm2, _seen2 = _arch_llm(["I think the decision is clear.", json.dumps({"brief": {"decision": "Keep B"}, "say": "What do you expect to see?"})])
_f2 = arch.exchange(_llm2, _xn, _xr, "  Keep B  ", data="`df`: 3 rows")
check("architect.exchange, an answer: the person's message joins the conversation the Pathfinder reads, under its own message and the choices it offered; a reply that cannot be read is asked for once "
      "more, with what was wrong with it; the reply kept is written in as a version made from the answer, and its message carries the cost of both calls and the number of the second",
      len(_seen2) == 2 and "CONVERSATION:\nPathfinder: What will you do differently depending on the answer?\n(choices offered: Keep B | Keep A)\nPerson: Keep B\n\nReply with the JSON object." in _seen2[0][1]
      and arch.conversation([{"who": "architect", "text": "One?\n\nOr two?", "choices": []}, {"who": "person", "text": "Two"}]) == "CONVERSATION:\nPathfinder: One?\n\nOr two?\nPerson: Two"
      and _seen2[1][1] == _seen2[0][1] + "\n\nYour last reply could not be read: it holds no JSON object. Reply with the JSON object and nothing else."
      and (_f2["versions"][2]["by"], _f2["versions"][2]["why"], _f2["versions"][2]["changed"], _f2["versions"][2]["brief"]["decision"]) == ("architect", "answer", ["decision"], "Keep B")
      and _f2["turns"][1:] == [{"who": "person", "text": "Keep B"}, {"who": "architect", "text": "What do you expect to see?", "v": 3, "cost": 0.008, "call": 3}] and _f2["calls"] == 3, (_f2["turns"], [u[-120:] for _, u, _ in _seen2]))
_xr.framing = _f2
_llm3, _seen3 = _arch_llm([json.dumps({"say": "The brief is ready: start the analysis, or change a line."})])
_f3 = arch.exchange(_llm3, _xn, _xr, "skip", data="")
check("architect.exchange: a reply that writes nothing makes no version - the message alone joins the conversation, with the version that stands; without a data description the prompt has no DATA part",
      len(_f3["versions"]) == 3 and _f3["turns"][-2:] == [{"who": "person", "text": "skip"}, {"who": "architect", "text": "The brief is ready: start the analysis, or change a line.", "v": 3, "cost": 0.004, "call": 4}]
      and _seen3[0][1].startswith("QUESTION:\nIs B above A?\n\nBRIEF (version 3):\ndecision: Keep B\n"), (_f3["turns"][-2:], _seen3[0][1][:80]))
def _failed(replies, usage=None, run=_xr, text="B above A by 2"):
    llm, seen = _arch_llm(list(replies), usage)
    try:
        arch.exchange(llm, _xn, run, text)
    except arch.Failed as exc:
        return str(exc), exc.calls, round(exc.cost, 4), len(seen)
    return None
_stood = json.dumps(_xr.framing, sort_keys=True)
_xfull = _xn.new_run("q"); _xfull.status = "framing"
_xfull.framing = {"versions": briefs.version({}, {"question": "q"})["versions"], "turns": [{"who": "architect", "text": "?"}] * arch.TURNS_MAX}
_xnear = _xn.new_run("q"); _xnear.status = "framing"
_xnear.framing = {"versions": briefs.version({}, {"question": "q"})["versions"], "turns": [{"who": "architect", "text": "?"}] * (arch.TURNS_MAX - 1) + [{"who": "check", "found": [], "secs": 0.1}] * 3}
check("architect.exchange, no reply to keep: unreadable twice, the reason in words with the two calls and their cost; a reply cut at the token limit says so; a request the model declined is not asked again; a brief "
      "the Pathfinder has replied to two hundred times gets no further call - a round of lookups is not a reply. Nothing of a failed exchange is kept",
      _failed(["no", "still no"]) == ("The Pathfinder's reply could not be read (it holds no JSON object).", 2, 0.008, 2)
      and _failed(['{"say": "x', '{"say": "x'], {"cost": 0.01, "truncated": True}) == ("The Pathfinder's reply could not be read (it was cut off at the token limit).", 2, 0.02, 2)
      and _failed([""], {"cost": 0.0, "declined": "policy"}) == ("The model declined to reply (policy).", 1, 0.0, 1)
      and _failed(["x"], run=_xfull) == ("The Pathfinder has replied 200 times in this brief. Change the brief yourself, or start the analysis.", 0, 0.0, 0) and arch.TURNS_MAX == 200
      and _failed(['{"say": "one more"}'], run=_xnear) is None
      and json.dumps(_xr.framing, sort_keys=True) == _stood, (_failed(["no", "still no"]), _failed([""], {"cost": 0.0, "declined": "policy"}), _failed(["x"], run=_xfull)))
_llm4, _seen4 = _arch_llm([json.dumps({"say": "ok"})])
_f4 = arch.exchange(_llm4, _anb, _a2, "y" * 5000, data="d")
check("architect.exchange: a follow-up's prompt carries the analyses it follows; the person's message is bounded as a question is; a brief that starts from the last one reads it as it stands",
      "\n\n" + arch.earlier(_anb, _a2.id, cells=True) + "\n\nQUESTION:\nUse y.\n\nBRIEF (version 1):\ndecision: d\n" in _seen4[0][1] and arch.earlier(_anb, _a2.id, cells=True) == _ae.replace("One site reverses.\n", "One site reverses.\n    To open: its report\n")
      and len(_f4["turns"][0]["text"]) == briefs.QUESTION_CHARS and _f4["versions"] == _a2.framing["versions"], _seen4[0][1][:300])
# ---- the saved analyses in the brief and in an exchange (0303, docs/ARCHITECT_DESIGN.md §3.3, §3.7) ----
_FOUND = [{"id": "7/8", "thread": "7", "run": "8", "when": "2026-03-02T10:00:00Z", "kind": "analysis", "question": "Was B above A in spring?", "title": "B led", "marks": ["picked", "routine"],
           "data": {"name": "spring.csv", "period": "2026-03-01 to 2026-05-31", "subject": "subject 1", "person": "First Person", "other": True}, "where": "report", "quote": "B led A by 3 units",
           "note": "The same comparison, a season earlier."},
          {"id": "7/9", "thread": "7", "run": "9", "when": "2026-04-02T10:00:00Z", "kind": "synthesis", "question": "", "title": "Two arms", "marks": [], "data": {"name": "", "period": "", "subject": ""},
           "where": "cell 2", "quote": "gap = b - a", "note": ""}]
_KEPT = [{"thread": "7", "run": "8", "when": "2026-03-02", "question": "Was B above A in spring?", "passage": "B led A by 3 units", "where": "report", "note": "The same comparison, a season earlier.",
          "marks": "picked, routine", "data": "spring.csv", "period": "2026-03-01 to 2026-05-31", "person": "First Person", "other": True},
         {"thread": "7", "run": "9", "when": "2026-04-02", "question": "Synthesis: Two arms", "passage": "gap = b - a", "where": "cell 2"}]
_gf = briefs.gather(None, _FOUND)
_gf2 = briefs.gather(_gf, _FOUND + [dict(_FOUND[0], quote="another passage"), dict(_FOUND[0], thread="9", run="1", id="9/1")])
check("brief.gather (0308): the passages the readings found are kept beside the brief, as the reader found them - each with its run, the day, what was asked - a synthesis by its title - the passage and "
      "where it stands, the reader's note, the run's marks and the data it ran on, with whose it is, and that it is another person's where the host said so. None says it is accepted: the brief builds "
      "on an analysis when the person chooses it. A passage that is there is not added again - the same words from another run are another passage - and the order they were found in stays: the "
      "analyses are numbered by it. What was kept before is not altered",
      _gf == _KEPT and _gf2[:2] == _KEPT and [(x["thread"], x["run"], x["passage"]) for x in _gf2[2:]] == [("7", "8", "another passage"), ("9", "1", "B led A by 3 units")]
      and [[x["passage"] for x in g] for g in briefs.analyses(_gf2)] == [["B led A by 3 units", "another passage"], ["gap = b - a"], ["B led A by 3 units"]]
      and briefs.gather(_gf, [dict(_FOUND[0], note="Said another way.")]) == _gf and briefs.gather(_gf, None) == _gf and briefs.gather("x", []) == [] and briefs.gather(_gf, [])[0] is not _gf[0]
      and "other" not in briefs.gather([], [dict(_FOUND[0], data={**_FOUND[0]["data"], "other": False})])[0] and "other" not in briefs.gather([], [dict(_FOUND[0], data={**_FOUND[0]["data"], "other": "yes"})])[0]
      and "person" not in _gf[1] and all("accepted" not in x for x in _gf2) and len(_gf) == 2, (_gf, _gf2))
_bb = {"question": "q", "decision": "d"}
_b1, _c1 = briefs.build_on(_bb, _gf2, [2])
_b2, _c2 = briefs.build_on(_b1, _gf2, [1, 2, 9, 0, -1, True, "1", 2])
_b3, _c3 = briefs.build_on(_b2, _gf2, [3])
_b4, _c4 = briefs.build_on(_b3, _gf2, [])
check("brief.build_on (0308): the brief builds on the saved analyses a reply names by number - the numbers the readings gave them, from 1 - and on no other: their passages stand under saved, accepted, in "
      "the readings' order, and an analysis named before and not now is built on no longer. Each passage that came is named as the page names it, and `saved` where one went. A number the readings do "
      "not have, a number given twice, a yes given for a number and a number in words are passed over; naming none builds on none; naming what stands changes nothing; the brief passed in is not "
      "altered; what a brief has no room for is left out; a passage a brief of 0307 held unticked is not one built on, and comes as new",
      [(x["run"], x["passage"], x["accepted"]) for x in _b1["saved"]] == [("9", "gap = b - a", True)] and _c1 == ["saved.0"] and _b1["decision"] == "d" and "saved" not in _bb
      and [(x["run"], x["passage"]) for x in _b2["saved"]] == [("8", "B led A by 3 units"), ("8", "another passage"), ("9", "gap = b - a")] and _c2 == ["saved.0", "saved.1"]
      and [(x["thread"], x["run"]) for x in _b3["saved"]] == [("9", "1")] and _c3 == ["saved.0", "saved"]
      and "saved" not in _b4 and _c4 == ["saved"] and briefs.build_on(_bb, _gf2, []) == (_bb, []) and briefs.build_on(_b1, _gf2, [2]) == (_b1, [])
      and briefs.build_on(_bb, None, [1]) == (_bb, []) and briefs.build_on(_bb, _gf2, None) == (_bb, []) and briefs.build_on(_bb, _gf2, [4]) == (_bb, [])
      and briefs.build_on(_bb, _gf2, [True]) == (_bb, []) and briefs.build_on(_bb, _gf2, [0]) == (_bb, []) and briefs.build_on(_bb, _gf2, ["1"]) == (_bb, [])
      and len(briefs.build_on(_bb, [dict(_KEPT[0], passage=f"p{k}") for k in range(14)], [1])[0]["saved"]) == briefs.MAX["saved"] == 10
      and briefs.build_on(_bb, [dict(_KEPT[0], passage=f"p{k}") for k in range(14)], [1])[1] == [f"saved.{k}" for k in range(10)]
      and briefs.build_on({"question": "q", "saved": [dict(_KEPT[0], accepted=False)]}, _gf2, [1])[1] == ["saved.0", "saved.1"], (_b1.get("saved"), _c1, _c2, _c3, _c4))
_f3 = briefs.version(briefs.version(briefs.version({"calls": 2}, {"question": "q0"}), {"question": "q1", "decision": "d1"}, by="architect", changed=["question", "decision"], why="answer"),
                     {"question": "q2", "decision": "d1", "thinks": "t2"}, by="architect", changed=["question", "thinks"], why="answer")
check("brief.latest (0308): the version in use is the last one, or the one the framing names (`at`: the step in use ends on it, analyst/steps.py) - latest() gives its brief under its own number; a "
      "version added is the one in use from then, numbered on from the last; a framing that names a version it does not have - nought, one too many, a yes, a number in words - is read as naming "
      "none. Nothing else puts a version in use: brief.use() is gone",
      briefs.latest({**_f3, "at": 2}) == {"question": "q1", "decision": "d1", "version": 2} and briefs.latest({**_f3, "at": 1}) == {"question": "q0", "version": 1} and briefs.latest(_f3)["version"] == 3
      and "at" not in briefs.version({**_f3, "at": 1}, {"question": "q9"}) and briefs.latest(briefs.version({**_f3, "at": 1}, {"question": "q9"})) == {"question": "q9", "version": 4}
      and all(briefs.latest({**_f3, "at": n}) == briefs.latest(_f3) for n in (7, 0, "2", True, None)) and briefs.latest({}) == {} and briefs.latest(None) == {} and not hasattr(briefs, "use"),
      briefs.latest({**_f3, "at": 2}))
# ---- the steps of a brief's conversation (0316, docs/ARCHITECT_DESIGN.md §2.25): what was said or changed, with the reply, is a step; steps branch; a framing holds one way
from analyst import steps
_person = lambda text: {"who": "person", "text": text}                 # noqa: E731
_reply = lambda text, v: {"who": "architect", "text": text, "v": v}    # noqa: E731


def _more(framing, turns=(), brief=None, **also):
    """A framing as the engine leaves it before its steps are counted: turns added, and one more version where a brief is given."""
    out = {**framing, "turns": list(framing.get("turns") or []) + list(turns), **also}
    return briefs.version(out, brief, by="architect", changed=["decision"]) if brief else out


_shape = lambda f: [(x["k"], x["from"], x["v"], x["made"], x["turns"]) for x in f["steps"]]      # noqa: E731
_said = lambda f: [t.get("text") or t["who"] for t in f.get("turns") or []]                    # noqa: E731
_aside = lambda f: {k: [t.get("text") or t["who"] for t in v.get("turns", [])] for k, v in (f.get("aside") or {}).items()}      # noqa: E731
_s1 = steps.take(briefs.version({}, {"question": "q"}))                                                        # a brief just opened
_s2 = steps.take(_more(_s1, [_reply("a1", 2)], {"question": "q", "decision": "d"}))                            # the Pathfinder's first reply, which wrote a part
_s3 = steps.take(_more(_s2, [_person("p2"), _reply("a2", 2), {"who": "check", "found": []}]))                  # the person spoke; a reply that changed nothing and had the data looked up
_s4 = steps.take(_more(_s3, [_reply("a2b", 3)], {"question": "q", "decision": "d", "expects": "e"}))           # the Pathfinder goes on by itself, and writes a part
_s5 = steps.take(briefs.version(_s4, {"question": "q", "decision": "by hand", "expects": "e"}, changed=["decision"]))      # the person changed a line by hand
_s6 = steps.take(_more(_s5, [{"who": "reader", "missing": ["x"], "v": 4}]))                                    # the question read before its analysis
_s7 = steps.take(_more(_s6, [_reply("a4", 5)], {"question": "q2", "decision": "by hand", "expects": "e"}))    # and the Pathfinder's reply to what the reader could not place
check("steps.take (0316): what is added to a framing is counted into a step. A brief just opened is one step, in use, the end of its way; the Pathfinder's first reply is that step's, with the "
      "version it made. Where the person speaks a step follows - their message, the reply, the lookups the reply asked for - and the reply the Pathfinder gives by itself after them is the same "
      "step's: its turns counted on, the version it made listed, the version in use at its end the step's. A line changed by hand - a version, and nothing said - is a step of its own; so is the "
      "question's read, and the Pathfinder's reply to it joins it. A framing with nothing added is left as it is, and the one passed in is never altered",
      (_shape(_s1), _s1["step"], _s1["tip"]) == ([(1, 0, 1, [1], 0)], 1, 1) and _shape(_s2) == [(1, 0, 2, [1, 2], 1)] and (_s2["step"], _s2["tip"]) == (1, 1)
      and _shape(_s3) == [(1, 0, 2, [1, 2], 1), (2, 1, 2, [], 3)] and (_s3["step"], _s3["tip"]) == (2, 2) and _shape(_s4)[-1] == (2, 1, 3, [3], 4) and len(_s4["steps"]) == 2
      and _shape(_s5)[-1] == (3, 2, 4, [4], 0) and _shape(_s6)[-1] == (4, 3, 4, [], 1) and _shape(_s7)[-1] == (4, 3, 5, [5], 2) and (_s7["step"], _s7["tip"], len(_s7["steps"])) == (4, 4, 4)
      and steps.take(_s7) == _s7 and _shape(_s1) == [(1, 0, 1, [1], 0)] and _shape(_s3)[-1] == (2, 1, 2, [], 3) and "aside" not in _s7 and "at" not in _s7,
      (_shape(_s7), _s7["step"], _s7["tip"]))
_b2 = steps.go(_s7, 2)                                                                                         # back to step 2
_b3 = steps.take(_more(_b2, [_person("p5"), _reply("a5", 6)], {"question": "q", "decision": "another way"}))  # the person speaks from there: another way
_b4 = steps.go(_b3, 4)                                                                                         # to the end of the way left
_b5 = steps.go(_b4, 1)                                                                                         # to the first step
_b6 = steps.take(_more(steps.go(_b3, 1), [_person("p6"), _reply("a6", 2)]))                                    # and the person speaks from the first step: a third way, which leaves the step where the other two part
check("steps.go (0316): the framing with another step in use. It holds that step's way and nothing of the others: the turns up to the step's end, and the version of the brief that stood there "
      "as the one in use; what the steps off the way hold is set aside, by step. What is said from there is a step that follows the one gone to - the steps that followed it before stay, set "
      "aside - and the next version is counted on from the last. Going to a step on the other way brings its turns back and sets the new ones aside. The way being walked ends where it did "
      "while the step gone to is on it, so the page's arrow forward finds the steps left; a step off that way has its own end, where the newest steps after it lead - from the step where "
      "two ways part, the one made last. Going there and back "
      "leaves the framing as it was; a step the framing does not have - nought, one too many, a yes, a number in words - changes nothing, nor does the one in use",
      (_b2["step"], _b2["tip"], _b2["at"], _said(_b2), _aside(_b2)) == (2, 4, 3, ["a1", "p2", "a2", "check", "a2b"], {"4": ["reader", "a4"]}) and briefs.latest(_b2)["version"] == 3
      and _shape(_b3)[-1] == (5, 2, 6, [6], 2) and (_b3["step"], _b3["tip"]) == (5, 5) and "at" not in _b3 and _said(_b3) == ["a1", "p2", "a2", "check", "a2b", "p5", "a5"]
      and _aside(_b3) == {"4": ["reader", "a4"]} and [x["n"] for x in _b3["versions"]] == [1, 2, 3, 4, 5, 6]
      and (_b4["step"], _b4["tip"], _b4["at"], _said(_b4), _aside(_b4)) == (4, 4, 5, ["a1", "p2", "a2", "check", "a2b", "reader", "a4"], {"5": ["p5", "a5"]})
      and (_b5["step"], _b5["tip"], _b5["at"], _said(_b5)) == (1, 4, 2, ["a1"]) and sorted(_b5["aside"]) == ["2", "4", "5"]
      and [steps.go(_b5, n)["tip"] for n in (2, 3, 4)] == [4, 4, 4] and steps.go(_b5, 5)["tip"] == 5 and steps.go(steps.go(_b5, 5), 2)["tip"] == 5
      and _shape(_b6)[-1] == (6, 1, 2, [], 2) and (_b6["step"], _b6["tip"]) == (6, 6) and [steps.go(_b6, n)["tip"] for n in (1, 2, 3, 4, 5)] == [6, 5, 4, 4, 5]
      and steps.go(steps.go(_b3, 1), 5) == _b3 and steps.go(steps.go(steps.go(_b3, 4), 3), 5) == _b3
      and all(steps.go(_b3, n) == _b3 for n in (0, 6, -1, True, "2", None, 2.0, 5)) and _shape(steps.go(_b3, 1)) == _shape(_b3),
      (_said(_b2), _aside(_b2), _b3.get("tip"), _b4.get("at"), _said(_b5)))
_m1 = steps.take({**_more(_s3, [{"who": "memory", "found": []}]), "found": [{"passage": "p1"}, {"passage": "p2"}], "proposed": 1})      # a reading in step 2: two passages; and a proposal made by then
_m2 = steps.take({**_more(_m1, [_person("p3"), {"who": "memory", "found": []}]), "found": _m1["found"] + [{"passage": "p3"}], "proposed": 2})
_m3 = steps.go(_m2, 2)
_d1 = steps.take(_more(steps.go(_s7, 2), [{"who": "draft", "drawn": []}]))      # at a step that has steps after it, something is added and nobody spoke: a draft drawn again
check("steps (0316), what else belongs to a way: the passages its readings found and the count of what the Pathfinder had proposed. A step holds the passages found in it; going back before a "
      "reading sets its passages aside with its turns, and the count is the one that stood then - going forward again brings them back. And what was is not changed: where the step in use has "
      "a step after it, what is added - a draft drawn again, nobody having spoken - is a step of its own, which follows it",
      [(x["found"], x["proposed"]) for x in _m2["steps"]] == [(0, 0), (2, 1), (1, 2)] and (_m3["found"], _m3["proposed"]) == ([{"passage": "p1"}, {"passage": "p2"}], 1)
      and _m3["aside"]["3"]["found"] == [{"passage": "p3"}] and (steps.go(_m3, 1)["found"], steps.go(_m3, 1)["proposed"]) == ([], 0)
      and steps.go(_m3, 1)["aside"]["2"]["found"] == _m3["found"] and steps.go(steps.go(_m3, 1), 3) == _m2
      and _shape(_d1)[-1] == (5, 2, 3, [], 1) and (_d1["step"], _d1["tip"]) == (5, 5) and _said(_d1)[-2:] == ["a2b", "draft"] and _aside(_d1) == {"4": ["reader", "a4"]},
      ([(x["found"], x["proposed"]) for x in _m2["steps"]], _m3.get("aside"), _shape(_d1)[-1]))
_legacy = {"versions": [{"n": n, "brief": {"question": "q"}} for n in (1, 2, 3)], "at": 2, "found": [{"passage": "p"}], "proposed": 1,
        "turns": [_reply("a", 2), _person("p"), _reply("b", 2), {"who": "version", "v": 1}, _person("p2"), {"who": "memory", "found": [], "v": 1}, _reply("c", 3),
                   _person("p3"), {"who": "check", "found": []}]}
check("steps, a framing kept before them (0316): one way, a step to a version. An exchange - the person's message with what followed it, the word that they went to another version before "
      "it - stands whole in one step: that of the last version made by then - an exchange that names no version too - so the conversation keeps its order; the passages found stand with "
      "the first reading. The step in use is the version the framing names - the last, where it names one it does not have - the way ends on the last, and going back sets the later "
      "steps aside as in any other framing. A framing that holds nothing is one step. way() is the steps "
      "from the first to one, in order - none for a step that is not there; said() is every turn, those set aside after those of the way",
      [(x["k"], x["from"], x["v"], x["made"], x["turns"], x["found"], x["proposed"]) for x in steps.take(_legacy)["steps"]] == [(1, 0, 1, [1], 0, 0, 1), (2, 1, 2, [2], 3, 0, 1), (3, 2, 3, [3], 6, 1, 1)]
      and (steps.take(_legacy)["step"], steps.take(_legacy)["tip"]) == (2, 3) and "steps" not in _legacy
      and (_said(steps.go(_legacy, 1)), steps.go(_legacy, 1)["at"], _aside(steps.go(_legacy, 1))) == ([], 1, {"2": ["a", "p", "b"], "3": ["version", "p2", "memory", "c", "p3", "check"]})
      and steps.go(_legacy, 1)["aside"]["3"]["found"] == [{"passage": "p"}] and "found" not in steps.go(_legacy, 1)["aside"]["2"] and steps.go(_legacy, 1)["found"] == []
      and steps.take({})["steps"] == steps.take(None)["steps"] == [{"k": 1, "from": 0, "v": 1, "made": [1], "turns": 0, "found": 0, "proposed": 0}]
      and [(steps.take({**_legacy, "at": at})["step"], "at" in steps.take({**_legacy, "at": at})) for at in (9, 0, True, "2", 3)] == [(3, False)] * 5
      and [x["k"] for x in steps.way(_b3["steps"], 5)] == [1, 2, 5] and steps.way(_b3["steps"], 9) == [] and steps.way(_b3["steps"], 0) == []
      and [t.get("text") or t["who"] for t in steps.said(_b3)] == ["a1", "p2", "a2", "check", "a2b", "p5", "a5", "reader", "a4"] and steps.said({}) == [] and steps.said(None) == [],
      ([(x["k"], x["turns"], x["found"]) for x in steps.take(_legacy)["steps"]], _aside(steps.go(_legacy, 1))))
import random as _rnd
_rnd.seed(316)
_walk, _mine, _n, _held_true = steps.take(briefs.version({}, {"question": "q"})), {}, 0, True
for _ in range(400):                                   # a long walk: steps taken and gone to at random
    if _rnd.random() < 0.4:
        _walk = steps.go(_walk, _rnd.randint(1, len(_walk["steps"])))
    else:
        _n, _before, _kind = _n + 1, len(_walk["steps"]), _rnd.choice(["say", "say", "hand", "goes on"])
        _new = [_person(f"p{_n}"), _reply(f"a{_n}", 0)] if _kind == "say" else [_reply(f"g{_n}", 0)] if _kind == "goes on" else []
        _walk = steps.take(briefs.version(_walk, {"question": f"q{_n}"}, changed=["question"]) if _kind == "hand" else _more(_walk, _new))
        _mine.setdefault(len(_walk["steps"]) if len(_walk["steps"]) > _before else _walk["step"], []).extend(t["text"] for t in _new)
    _way = steps.way(_walk["steps"], _walk["step"])
    _held_true = (_held_true and sum(x["turns"] for x in _way) == len(_walk.get("turns") or []) and _said(_walk) == [t for x in _way for t in _mine.get(x["k"], [])]
                  and briefs.latest(_walk)["version"] == _way[-1]["v"] and _walk["step"] in [x["k"] for x in steps.way(_walk["steps"], _walk["tip"])]
                  and sorted(t["text"] for t in steps.said(_walk)) == sorted(t for texts in _mine.values() for t in texts))
check("steps, a long walk (0316): four hundred moves at random - the person speaks, changes a line by hand, the Pathfinder goes on by itself, the person goes to any step. After every one the "
      "framing holds the turns of the way to the step in use, each step's own in order, and the version that stood at its end; every turn ever said is held once, on the way or set aside; and "
      "the step in use is on the way being walked. At the end every step's way is as it was said",
      _held_true and len(_walk["steps"]) > 100 and len({x["from"] for x in _walk["steps"]}) < len(_walk["steps"]) - 20
      and all(_said(steps.go(_walk, x["k"])) == [t for y in steps.way(_walk["steps"], x["k"]) for t in _mine.get(y["k"], [])] for x in _walk["steps"]),
      (len(_walk["steps"]), _walk["step"], _walk["tip"]))
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "steps.json"), encoding="utf-8") as _fh:
    _fx = json.load(_fh)
_MOVED = ("step", "tip", "at", "turns", "aside")      # what differs in a framing with another step in use
_rest = lambda f: {key: value for key, value in f.items() if key not in _MOVED}      # noqa: E731
_th = _fx["then"]
_from = steps.go(_fx["framing"], _th["from"])
_after = steps.take(briefs.version({**_from, "turns": _from["turns"] + _th["turns"], "calls": _from["calls"] + 1}, _th["brief"], by="architect", changed=_th["changed"], why="answer"))
check("steps, the fixture the page's suite shares (0316; tests/analyst/fixtures/steps.json): a conversation that went one way, came back and went another. The framing is one the engine leaves "
      "as it is, and with each of its steps in use it is what the file says - the step, the end of its way, the version in use, the turns of its way and what is set aside - with nothing else "
      "changed. The person speaking once more from the step they had gone back to is one more step that follows it: the framing after is the file's too. The page is held to the same file "
      "(test_architect.js): the two say the same of a step gone to",
      steps.take(_fx["framing"]) == _fx["framing"] and sorted(_fx["go"]) == [str(x["k"]) for x in _fx["framing"]["steps"]] and len({x["from"] for x in _fx["framing"]["steps"]}) < len(_fx["framing"]["steps"])
      and all({key: got[key] for key in _MOVED if key in got} == _fx["go"][k] and _rest(got) == _rest(_fx["framing"]) for k, got in ((k, steps.go(_fx["framing"], int(k))) for k in _fx["go"]))
      and _after == _th["framing"] and _shape(_after)[-1] == (7, 2, 6, [6], 2) and (_after["step"], _after["tip"], sorted(_after["aside"])) == (7, 7, ["3", "4", "6"]),
      ([k for k in _fx["go"] if {key: value for key, value in steps.go(_fx["framing"], int(k)).items() if key in _MOVED} != _fx["go"][k]], _after == _th["framing"]))
_rb = {"question": "q", "decision": "d", "saved": [dict(x, accepted=False) for x in _KEPT]}
_ticked = {**_rb, "saved": [dict(_KEPT[0], accepted=True), dict(_KEPT[1], accepted=False)]}
_wpass = [dict(_KEPT[0], accepted=True), dict(_KEPT[1], accepted=True), dict(_KEPT[0], passage="gap = b - a", where="cell 1", accepted=True),
          {"thread": "7", "run": "10", "when": "2026-05-02", "question": "And the third arm?", "accepted": True}]      # three analyses: the first with two passages, the last with none
check("brief.agreed: the analyst receives the passages the person accepted and no other - accepted only where that is said outright; its BRIEF block gives a numbered line for each analysis they come from, "
      "with its day, what was asked and the data - and that it is another person's data, never whose - then each passage with where it stands there. Two passages of one analysis are one line, wherever "
      "they stand in the brief; an analysis named without a passage is a line too; a passage that names no run stands alone",
      briefs.agreed(_ticked)["saved"] == [dict(_KEPT[0], accepted=True)] and "saved" not in briefs.agreed(_rb) and "saved" not in briefs.agreed({**_rb, "saved": [dict(_KEPT[0], accepted="yes"), dict(_KEPT[1], accepted=1)]})
      and [x["accepted"] for x in briefs.normalise({"question": "q", "saved": [dict(_KEPT[0], accepted="yes"), {"passage": "p"}]})["saved"]] == [False, False]
      and briefs.render(briefs.agreed(_ticked)).splitlines()[-2:] == ["Saved analyses the person chose (earlier results: claims to test, not evidence):",
                                                                       '1. 2026-03-02 "Was B above A in spring?" (spring.csv, 2026-03-01 to 2026-05-31, another person\'s data): in its report "B led A by 3 units"']
      and briefs.render(briefs.agreed({**_rb, "saved": _wpass})).splitlines()[-3:] == [
          '1. 2026-03-02 "Was B above A in spring?" (spring.csv, 2026-03-01 to 2026-05-31, another person\'s data): in its report "B led A by 3 units"; in its cell 1 "gap = b - a"', '2. 2026-04-02 "Synthesis: Two arms": in its cell 2 "gap = b - a"',
          '3. 2026-05-02 "And the third arm?"']
      and [[x["passage"] for x in a] for a in briefs.analyses([{"passage": "p1"}, {"passage": "p2", "thread": "7"}, {"thread": "7", "run": "8", "passage": "p3"}, {"thread": "7", "run": "9", "passage": "p4"},
                                                               {"thread": "7", "run": "8", "passage": "p5"}, {"thread": "6", "run": "8", "passage": "p6"}])] == [["p1"], ["p2"], ["p3", "p5"], ["p4"], ["p6"]]
      and "First Person" not in briefs.render(briefs.agreed(_ticked)) and "another person" not in briefs.render(briefs.agreed({**_rb, "saved": [dict(_KEPT[1], accepted=True)]}))
      and "other" not in briefs.normalise({"question": "q", "saved": [dict(_KEPT[0], other="yes")]})["saved"][0]
      and briefs.agreed(briefs.build_on(_bb, _gf, [1])[0])["saved"] == [dict(_KEPT[0], accepted=True)],      # what a reply builds on is what the analyst receives
      briefs.render(briefs.agreed(_ticked)).splitlines()[-2:])
_RESULT = {"found": _FOUND, "across": {"topic": "How the gap was taken", "groups": [{"label": "B minus A", "runs": [{"run": "7/8"}, {"run": "7/9"}]}, {"label": "the ratio", "runs": [{"run": "5/6"}]}]},
           "dropped": 1, "coverage": {"runs": 12, "judged": 9, "not_read": {"older": 3}}, "steps": [], "calls": {"reader": 3, "pieces": 2}, "cost": 0.07123, "seconds": 41.26, "failed": ""}
_asked_of = []


def _recall_of(result):
    def recall(question, brief_text):
        _asked_of.append((question, brief_text))
        return result
    return recall


_mn = Notebook("m"); _mr = _mn.new_run("Is B above A?"); _mr.status = "framing"; _mr.framing = briefs.version({}, {"question": _mr.question, "decision": "keep one arm"})
_llm5, _seen5 = _arch_llm([json.dumps({"say": "I am looking in your saved analyses.", "recall": True, "brief": {"thinks": "B is better"}}), json.dumps({"say": "I am looking once more.", "recall": True}),
                           json.dumps({"say": "You looked at this twice."})])
_mr.framing = arch.exchange(_llm5, _mn, _mr, "Go on.", data="d", recall=_recall_of(_RESULT), saved=12)
_t5, _n5 = _mr.framing["turns"], _mr.framing["saved"]
check("architect.exchange, the saved analyses: the Pathfinder is told how many there are, where there are any, and the framing keeps the number; where the reply asks, they are read with the question and "
      "the brief as the Pathfinder reads it; what was found is the conversation's last turn - the passages, what was found across, how many runs there are and how many were read, what was dropped, "
      "the seconds and the cost - and is kept beside the brief (0308): the brief itself does not change, and a reading makes no version",
      [t["who"] for t in _t5] == ["person", "architect", "memory"] and _n5 == 12 and _asked_of == [("Is B above A?", "BRIEF (version 1):\ndecision: keep one arm\nthinks: B is better\nrests_on: (empty)\nexpects: (empty)\n"
                                                                                                      "would_change: (empty)\nalso_check: (empty)\nfixed.comparison: (empty)\nfixed.measure: (empty)\nfixed.period: (empty)")]
      and _t5[2] == {"who": "memory", "found": [{"id": "7/8", "when": "2026-03-02", "question": "Was B above A in spring?", "where": "report", "quote": "B led A by 3 units", "note": "The same comparison, a season earlier."},
                                                 {"id": "7/9", "when": "2026-04-02", "question": "Synthesis: Two arms", "where": "cell 2", "quote": "gap = b - a", "note": ""}],
                     "across": _RESULT["across"], "of": 12, "read": 9, "dropped": 1, "failed": "", "secs": 41.3, "cost": 0.0712, "v": 2}
      and [(v["n"], v["by"], v.get("why"), v["changed"]) for v in _mr.framing["versions"][1:]] == [(2, "architect", "answer", ["thinks"])]
      and _mr.framing["found"] == _KEPT and "saved" not in briefs.latest(_mr.framing) and _t5[1]["v"] == 2 and _seen5[0][1].startswith("DATA:\nd\n\nSAVED: 12\n\nQUESTION:\nIs B above A?\n\nBRIEF (version 1):"), (_t5, _asked_of))
_mr.framing = arch.exchange(_llm5, _mn, _mr, None, data="d", recall=_recall_of(_RESULT))
check("architect.exchange: the next exchange reads what was found - an analysis to a line under its number, with its day, what was asked and its passages, each with where it stands; then the count to "
      "each way across them - and under the brief that it builds on none of them yet; whose data an analysis ran on is not said, which the framing keeps for the person. A reply that asks again before "
      "the person has spoken gets no second reading: it is told so at once and asked again, and what it then says is the message kept, with both calls counted; with nothing saved the Pathfinder is "
      "told nothing of it, and the framing says none",
      "\n\nCONVERSATION:\nPerson: Go on.\nPathfinder: I am looking in your saved analyses.\nSaved analyses (12 saved, 9 read through):\n"
      '[1] 2026-03-02 "Was B above A in spring?": in its report "B led A by 3 units" - The same comparison, a season earlier.\n[2] 2026-04-02 "Synthesis: Two arms": in its cell 2 "gap = b - a"\n'
      "Across them - How the gap was taken: 2 x B minus A; 1 x the ratio\n\nReply with the JSON object." in _seen5[1][1]
      and "\nfixed.period: (empty)\nbuilds_on: (empty)\n\nCONVERSATION:" in _seen5[1][1]
      and len(_asked_of) == 1 and [t["who"] for t in _mr.framing["turns"]] == ["person", "architect", "memory", "architect"] and "SAVED" not in _seen5[1][1] and _mr.framing["saved"] == 0
      and len(_seen5) == 3 and _seen5[2][1] == _seen5[1][1] + "\n\nYour last reply asked for what cannot be done now: a reading of the saved analyses - they were read since the person last spoke. Nothing was started. "
                                                                 "Reply again without asking for it, and do not tell the person that it is under way."
      and _mr.framing["turns"][-1] == {"who": "architect", "text": "You looked at this twice.", "v": 2, "cost": 0.008, "call": 3} and _mr.framing["calls"] == 3
      and "First Person" not in _seen5[1][1] and _mr.framing["found"][0]["person"] == "First Person"
      and "SAVED: 3" in arch.prompt("q", {}, [], data="d", before="EARLIER (x)", saved=3).split("\n\n")[2], _seen5[1][1][-900:])
_llm6, _seen6r = _arch_llm([json.dumps({"say": "Looking again.", "recall": True})] * 5)
_mr.framing = arch.exchange(_llm6, _mn, _mr, "Look again.", data="d", recall=_recall_of({**_RESULT, "found": _FOUND[:1] + [dict(_FOUND[0], quote="one more passage")], "across": None}))
_again = ([t["who"] for t in _mr.framing["turns"]][-3:], len(_asked_of), len(_mr.framing["versions"]), [x["passage"] for x in _mr.framing["found"]])
for _said in ("And once more.", "And again."):
    _mr.framing = arch.exchange(_llm6, _mn, _mr, _said, data="d", recall=_recall_of(_RESULT))
_fourth = ([t["who"] for t in _mr.framing["turns"]][-3:], len(_asked_of))
_mr.framing = arch.exchange(_llm6, _mn, _mr, "A fifth time.", data="d", recall=_recall_of(_RESULT))
check("architect.exchange, the bounds of reading: after the person's next message the saved analyses are read once more - what a reading finds again is kept once, what it finds new joins what was "
      "found, and still no version is made - and a brief gets four readings in all: a fifth is not made. From then on the Pathfinder is told with every prompt that no reading can be made, and why; a "
      "reply that asks all the same is told again and asked once more, and what it still asks for is not done. Nothing but a reply asks for a reading: the person's own button is gone (0308). "
      "From the second reading on the reader's brief says what the brief builds on - nothing yet",
      _again == (["person", "architect", "memory"], 2, 2, ["B led A by 3 units", "gap = b - a", "one more passage"]) and _fourth == (["person", "architect", "memory"], 4)
      and "builds_on" not in _asked_of[0][1] and all(b.endswith("\nfixed.period: (empty)\nbuilds_on: (empty)") for _, b in _asked_of[1:])
      and [t["who"] for t in _mr.framing["turns"]][-2:] == ["person", "architect"] and len(_asked_of) == 4 and arch.READINGS == 4 and len(_seen6r) == 5
      and all("SAVED" not in u for _, u, _ in _seen6r)                       # these exchanges name no saved analyses: the line is the next check's
      and _seen6r[4][1] == _seen6r[3][1] + "\n\n" + arch.NOT_DONE.format(what="a reading of the saved analyses - they were read 4 times for this brief, and that is the most")
      and arch._unread(None, []) == "nothing here reads them" and arch._unread(len, [{"who": "memory"}] * 4 + [{"who": "person"}]) == arch.READ_ALL
      and arch._unread(len, [{"who": "memory"}, {"who": "architect"}]) == arch.READ_SINCE and arch._unread(len, [{"who": "memory"}, {"who": "person"}, {"who": "architect"}]) == ""
      and arch.prompt("q", {}, [], saved=3, unread=arch.READ_ALL).startswith("SAVED: 3 (no reading can be made now: they were read 4 times for this brief, and that is the most)\n\nQUESTION:")
      and arch.prompt("q", {}, [], saved=0, unread=arch.READ_ALL).startswith("QUESTION:") and "asked" not in arch.exchange.__code__.co_varnames[:arch.exchange.__code__.co_argcount],
      (_again, _fourth, len(_asked_of), len(_seen6r)))
del _asked_of[:]
_fn = Notebook("f"); _f0 = _fn.new_run("Is B above A?"); _f0.status = "answered"; _f0.report = "# B is above A\n\nBy 3."
_f1 = _fn.new_run("And C?", _f0.id); _f1.status = "framing"; _f1.framing = briefs.version({}, {"question": _f1.question})
_llm7, _seen7 = _arch_llm([json.dumps({"say": "Ready.", "recall": True}), json.dumps({"say": "You asked this in spring."}), json.dumps({"say": "Ready."})])
_f1.framing = _g1 = arch.exchange(_llm7, _fn, _f1, "Go on.", data="d", recall=_recall_of(_RESULT))
_f1.framing = _g2 = arch.exchange(_llm7, _fn, _f1, None, data="d", recall=_recall_of(_RESULT))
_g5 = arch.exchange(_llm7, _mn, _mn.new_run("q"), "Go on.", data="d")
check("architect.exchange, a question that follows an analysis (0307): the Pathfinder's own request for a reading is carried out as on any other question - in a live run it had been passed over without a word, "
      "and the Pathfinder went on saying it was looking; the next exchange, with nothing said, reads what was found and replies. With nothing to read them, a reply is a reply like any other",
      [t["who"] for t in _g1["turns"]] == ["person", "architect", "memory"] and _asked_of[0][0] == "And C?" and _g1["found"] == _KEPT and len(_g1["versions"]) == 1 and _g1["turns"][-1]["v"] == 1
      and "\n    Found: By 3.\n    To open: its report\n\nQUESTION:\nAnd C?" in _seen7[0][1]
      and [t["who"] for t in _g2["turns"]][-2:] == ["memory", "architect"] and _g2["calls"] == 2 and "Pathfinder: Ready.\nSaved analyses (12 saved, 9 read through):\n[1] 2026-03-02" in _seen7[1][1]
      and len(_asked_of) == 1 and [t["who"] for t in _g5["turns"]] == ["person", "architect"],
      ([t["who"] for t in _g1["turns"]], [t["who"] for t in _g2["turns"]], len(_asked_of)))
_none_found = arch.recalled({"who": "memory", "found": [], "across": None, "of": 12, "read": 0, "failed": ""}, {})
check("architect.recalled: nothing found is said in a line, and a reading that was not made says why; a reply asks for the saved analyses only by saying so outright. Two passages of one analysis are "
      "one line under its number (0308); an analysis the numbers do not name stands under a dash",
      _none_found == ["Saved analyses (12 saved, 0 read through): nothing in them bears on it."]
      and [arch.parse(json.dumps({"say": "x", "recall": r}))["recall"] for r in (True, "true", 1, "yes", None, False)] == [True, False, False, False, False, False]
      and arch.recalled({"who": "memory", "found": [], "failed": "The person skipped it."}, {}) == ["Saved analyses: not read - The person skipped it."]
      and arch._recall({"failed": "The person skipped it."}) == {"who": "memory", "found": [], "across": None, "of": 0, "read": 0, "dropped": 0, "failed": "The person skipped it.", "secs": 0.0, "cost": 0.0}
      and arch.recalled(arch._recall(_RESULT), {})[1] == '[-] 2026-03-02 "Was B above A in spring?": in its report "B led A by 3 units" - The same comparison, a season earlier.'
      and arch.recalled(arch._recall({**_RESULT, "found": [_FOUND[0], _FOUND[1], dict(_FOUND[0], quote="and more", where="cell 3", note="")]}), {"7/8": 4, "7/9": 5})[1:3] == [
          '[4] 2026-03-02 "Was B above A in spring?": in its report "B led A by 3 units" - The same comparison, a season earlier.; in its cell 3 "and more"', '[5] 2026-04-02 "Synthesis: Two arms": in its cell 2 "gap = b - a"']
      and "left" not in arch._recall(_RESULT) and len(arch._recall(_RESULT)["found"]) == 2, _none_found)
del _asked_of[:]
# ---- 0308 (docs/ARCHITECT_DESIGN.md §2.18): the question evolves. A wording the Pathfinder gives is written at once, as one more version: the person sees the question change, changes it by hand or
# ---- goes back to an earlier version. Nothing the reply writes under the brief's own question is kept, and nothing waits to be taken
_WORDING = "Plot x against z for two starts, a small step apart.\nShow where they part."
_sbn = Notebook("q"); _sbr = _sbn.new_run("Plot the thing"); _sbr.status = "framing"; _sbr.framing = briefs.version({}, {"question": _sbr.question})
_llm8, _seen8 = _arch_llm([json.dumps({"say": "I have put that into the question. Is that what you mean?", "wording": "  Plot x   against z for two starts, a small step apart.\n Show where they part.  ",
                                       "choices": ["Yes, that is it", "Change something"], "brief": {"question": "Sneaked in", "thinks": "it parts"}}),
                           json.dumps({"say": "Good.", "brief": {"question": "Sneaked in again", "expects": "they part"}}), json.dumps({"say": "The same again.", "wording": _WORDING}),
                           json.dumps({"say": "Then like this.", "wording": "Plot x against y.", "recall": True}), json.dumps({"say": "Noted."})])
_sbr.framing = _sb1 = arch.exchange(_llm8, _sbn, _sbr, "The one with two starts")
_sbr.framing = _sb2 = arch.exchange(_llm8, _sbn, _sbr, "Yes, that is it")
_sbr.framing = _sb3 = arch.exchange(_llm8, _sbn, _sbr, "Say it again")
_sbr.framing = _sb4 = arch.exchange(_llm8, _sbn, _sbr, "Rather against y", recall=_recall_of(_RESULT))
check("architect.exchange, the wording (0308): a wording the reply gives is the question from that reply on - one more version of the Pathfinder's, with the reply's other parts - its lines kept as a "
      "question's are, and the message that worded it keeps the wording. What the reply writes under the brief's own question is never kept. A reply without a wording leaves the question; a wording "
      "that says what the question says changes nothing, and its message keeps none. The saved analyses are read with the question as it then stands. Nothing waits for the person: a reply's "
      "`accept` is read no longer, and the engine has no pending()",
      briefs.latest(_sb1)["question"] == _WORDING and briefs.latest(_sb1)["thinks"] == "it parts" and sorted(_sb1["versions"][-1]["changed"]) == ["question", "thinks"]
      and (_sb1["versions"][-1]["by"], _sb1["versions"][-1]["n"]) == ("architect", 2) and _sb1["turns"][-1]["wording"] == _WORDING and _sb1["turns"][-1]["v"] == 2
      and briefs.latest(_sb2)["question"] == _WORDING and briefs.latest(_sb2)["expects"] == "they part" and _sb2["versions"][-1]["changed"] == ["expects"] and "wording" not in _sb2["turns"][-1]
      and len(_sb3["versions"]) == 3 and "wording" not in _sb3["turns"][-1] and briefs.latest(_sb3)["question"] == _WORDING
      and briefs.latest(_sb4)["question"] == "Plot x against y." and _sb4["turns"][-2]["wording"] == "Plot x against y." and _asked_of[0][0] == "Plot x against y."
      and [t["who"] for t in _sb4["turns"]][-2:] == ["architect", "memory"] and _sb4["versions"][-1]["changed"] == ["question"]
      and not hasattr(arch, "pending") and "accept" not in arch.parse('{"say": "x", "accept": true}'),
      ([v["changed"] for v in _sb4["versions"]], [t.get("wording") for t in _sb4["turns"]]))
_sbr.framing = _sb5 = arch.exchange(_llm8, _sbn, _sbr, None)
check("architect.prompt, the wording: the Pathfinder reads the question as it stands, with how it was first asked where the wording has changed since; under a message of its own that worded the "
      "question, the question as it was written then, above the choices it offered - and under no other message",
      _seen8[4][1].startswith("QUESTION:\nPlot x against y.\n(first asked as: Plot the thing)\n\nBRIEF (version 4):")
      and ("CONVERSATION:\nPerson: The one with two starts\nPathfinder: I have put that into the question. Is that what you mean?\n(the question was written as: " + _WORDING + ")\n(choices offered: Yes, that is it | Change something)\nPerson: Yes, that is it\n"
           "Pathfinder: Good.\nPerson: Say it again\nPathfinder: The same again.\nPerson: Rather against y\nPathfinder: Then like this.\n(the question was written as: Plot x against y.)\nSaved analyses (") in _seen8[4][1]
      and "(first asked as" not in _seen8[0][1] and arch.prompt("q", {}, [], first="q") == arch.prompt("q", {}, []) and "(first asked as: an older one)" in arch.prompt("q", {}, [], first="an older one"),
      _seen8[4][1][-1300:])
_vn = Notebook("v"); _vr = _vn.new_run("q0"); _vr.status = "framing"; _vr.framing = {k: v for k, v in _f3.items() if k != "calls"}
_llm9, _seen9 = _arch_llm([json.dumps({"say": "Noted.", "brief": {"expects": "e"}}), json.dumps({"say": "Yes."}), json.dumps({"say": "Still."}), json.dumps({"say": "On."}), json.dumps({"say": "Up."}),
                           json.dumps({"say": "x"}), json.dumps({"say": "Looking.", "recall": True})])
_vr.framing = _v1 = arch.exchange(_llm9, _vn, _vr, "From the second one", step=2)          # the person went back to step 2 and answers: the reply's change is made to its brief
_vr.framing = _v2 = arch.exchange(_llm9, _vn, _vr, "And the first", step=1)                # back to step 1, a reply that changes nothing
_vr.framing = _v3 = arch.exchange(_llm9, _vn, _vr, "Again", step=5)                        # the step in use, named
_vr.framing = _v4 = arch.exchange(_llm9, _vn, _vr, "No step said")                         # the page says none: the conversation goes on from the one in use
_v5 = arch.exchange(_llm9, _vn, _vr, "The last", step=4)                                   # to the step left, and on from it
_v6 = arch.exchange(_llm9, _vn, _vr, "x", step=99)                                         # a step the framing does not have
_v7 = arch.exchange(_llm9, _vn, _vr, "Look in what I saved", recall=_recall_of(_RESULT), saved=3)      # a reading on this way
check("architect.exchange, the step on screen (0316): where the person's message comes from another step than the one in use, the exchange goes on from that step. The Pathfinder reads the question "
      "and the brief as they stood there and the conversation up to there - nothing of what was said on another way, and no word that the person went back: for the Pathfinder it did not "
      "happen. The reply's changes are made to that brief, as one more version counted on from the last, and message and reply are a step that follows the one gone to; the steps after it "
      "stay, set aside with what they hold. A reply that changes nothing leaves the version of that step in use, and the reply's turn names it. The step in use named again, or none, or one "
      "the framing does not have: the conversation goes on from the one in use. Going to the step left brings its conversation back. A reading is counted into its step, with what it found",
      [t["who"] for t in _v1["turns"]] == ["person", "architect"] and "at" not in _v1 and _v1["turns"][-1]["v"] == 4 and (_v1["step"], _v1["tip"]) == (4, 4)
      and _shape(_v1) == [(1, 0, 1, [1], 0), (2, 1, 2, [2], 0), (3, 2, 3, [3], 0), (4, 2, 4, [4], 2)]
      and briefs.latest(_v1) == {"question": "q1", "decision": "d1", "expects": "e", "version": 4} and [v["n"] for v in _v1["versions"]] == [1, 2, 3, 4] and _v1["versions"][2]["brief"]["question"] == "q2"
      and "QUESTION:\nq1\n(first asked as: q0)\n\nBRIEF (version 2):\ndecision: d1\nthinks: (empty)" in _seen9[0][1]
      and _seen9[0][1].endswith("CONVERSATION:\nPerson: From the second one\n\nReply with the JSON object.") and "went to version" not in _seen9[0][1]
      and _v2["at"] == 1 and briefs.latest(_v2) == {"question": "q0", "version": 1} and [t["who"] for t in _v2["turns"]] == ["person", "architect"] and _v2["turns"][-1]["v"] == 1
      and len(_v2["versions"]) == 4 and _shape(_v2)[-1] == (5, 1, 1, [], 2) and _v2["aside"] == {"4": {"turns": _v1["turns"]}}
      and _seen9[1][1].endswith("CONVERSATION:\nPerson: And the first\n\nReply with the JSON object.") and "From the second one" not in _seen9[1][1] and "BRIEF (version 1):" in _seen9[1][1]
      and _shape(_v3)[-1] == (6, 5, 1, [], 2) and [t["who"] for t in _v3["turns"]] == ["person", "architect"] * 2 and _v3["at"] == 1
      and _shape(_v4)[-1] == (7, 6, 1, [], 2) and len(_v4["turns"]) == 6 and _v4["at"] == 1 and "BRIEF (version 1):" in _seen9[3][1]
      and "at" not in _v5 and _shape(_v5)[-1] == (8, 4, 4, [], 2) and "BRIEF (version 4):" in _seen9[4][1] and sorted(_v5["aside"]) == ["5", "6", "7"]
      and _seen9[4][1].endswith("CONVERSATION:\nPerson: From the second one\nPathfinder: Noted.\nPerson: The last\n\nReply with the JSON object.")
      and _v6["at"] == 1 and _shape(_v6)[-1] == (8, 7, 1, [], 2) and [t["who"] for t in _v6["turns"]][-2:] == ["person", "architect"] and "BRIEF (version 1):" in _seen9[5][1]
      and _v7["turns"][-1]["who"] == "memory" and (_v7["turns"][-1]["v"], _v7["turns"][-2]["v"], _v7["at"], len(_v7["versions"])) == (1, 1, 1, 4)
      and _shape(_v7)[-1] == (8, 7, 1, [], 3) and _v7["steps"][-1]["found"] == len(_v7["found"]) > 0 and not any(t["who"] == "version" for f in (_v1, _v2, _v5, _v7) for t in steps.said(f)),
      ([t["who"] for t in _v1["turns"]], _shape(_v2), _v2.get("at"), _v5.get("at"), _v6.get("at")))
_tn = Notebook("t"); _tr = _tn.new_run("q"); _tr.status = "framing"; _tr.framing = briefs.version({}, {"question": "q"})
_tllm, _tseen = _arch_llm([json.dumps({"say": "Looking.", "recall": True}), json.dumps({"say": "Built.", "build": [2], "brief": {"decision": "to build on it"}}), json.dumps({"say": "Both.", "build": [1, 2]}),
                           json.dumps({"say": "As it was.", "build": [2, 1]}), json.dumps({"say": "A word on something else."}), json.dumps({"say": "None.", "build": []}),
                           json.dumps({"say": "Nothing to build on.", "build": [1]})])
_tr.framing = arch.exchange(_tllm, _tn, _tr, "Go on.", recall=_recall_of(_RESULT), saved=3)
_tr.framing = _tx = arch.exchange(_tllm, _tn, _tr, "Build on the second one")
_tr.framing = _ty = arch.exchange(_tllm, _tn, _tr, "On both")
_tr.framing = _tz = arch.exchange(_tllm, _tn, _tr, "Say it again")
_tr.framing = _tu = arch.exchange(_tllm, _tn, _tr, "Something else")
_tr.framing = _tw = arch.exchange(_tllm, _tn, _tr, "Go another way after all")
_t0 = arch.exchange(_tllm, _mn, _mn.new_run("q"), "Build on the first")
check("architect.exchange, build on it (0308): 'build on it' is the person's word, and the Pathfinder's reply names the analyses the brief builds on by the numbers the readings gave them - their passages "
      "come into the brief, accepted, as one more version of the Pathfinder's, with the reply's other parts. Naming another set makes it that set; naming the same set changes nothing and makes no "
      "version, and neither does a reply that says nothing of it; naming none takes them out. The Pathfinder reads which the brief builds on under builds_on, from the reading on. Where nothing was read there is nothing to build on",
      [(s["run"], s["accepted"]) for s in briefs.latest(_tx)["saved"]] == [("9", True)] and briefs.latest(_tx)["decision"] == "to build on it" and _tx["versions"][-1]["changed"] == ["decision", "saved.0"]
      and (_tx["versions"][-1]["by"], _tx["versions"][-1]["why"]) == ("architect", "answer") and [s["run"] for s in briefs.latest(_ty)["saved"]] == ["8", "9"] and _ty["versions"][-1]["changed"] == ["saved.0"]
      and len(_tu["versions"]) == len(_tz["versions"]) == len(_ty["versions"]) == 3 and [s["run"] for s in briefs.latest(_tu)["saved"]] == ["8", "9"] and "saved" not in briefs.latest(_tw) and _tw["versions"][-1]["changed"] == ["saved"] and len(_tw["found"]) == 2
      and "\nfixed.period: (empty)\nbuilds_on: (empty)\n\nCONVERSATION:" in _tseen[1][1] and '\nbuilds_on:\n- [2] 2026-04-02 "Synthesis: Two arms"\n\nCONVERSATION:' in _tseen[2][1]
      and '\nbuilds_on:\n- [1] 2026-03-02 "Was B above A in spring?"\n- [2] 2026-04-02 "Synthesis: Two arms"\n\nCONVERSATION:' in _tseen[3][1] and "builds_on" not in _tseen[0][1]
      and not _t0.get("versions") and "builds_on" not in _tseen[6][1] and not hasattr(briefs, "tick") and not hasattr(briefs, "remember"),
      ([v["changed"] for v in _tw["versions"]], [s["run"] for s in briefs.latest(_ty).get("saved", [])]))
_sf = {"versions": [{"n": 1, "brief": {"question": "B or A?"}}], "turns": [{"who": "architect", "text": " What is it for? ", "wording": "Does B beat A?\nBy how much?", "choices": ["To pick one"]}, {"who": "check", "found": []},
                                                                           {"who": "person", "text": "To pick one."}, {"who": "memory", "found": []}, {"who": "opened", "label": "cell 1"}, {"who": "architect", "text": "  "}]}
check("brief.said: the conversation a brief came from, as text - the question as it was first asked, then each message under who said it, a wording the Pathfinder gave on a line of its own; the choices, "
      "what was looked up, read or opened and a message without words are no part of it; nothing said gives nothing, and a framing that kept no first version opens on the question handed in",
      briefs.said(_sf, "Does B beat A?") == "Person: B or A?\nPathfinder: What is it for?\nPathfinder's wording of the question: Does B beat A?\nBy how much?\nPerson: To pick one."
      and briefs.said({"turns": [{"who": "person", "text": "yes"}]}, " the question ") == "Person: the question\nPerson: yes" and briefs.said({"turns": [{"who": "person", "text": "yes"}]}) == "Person: yes"
      and briefs.said({"versions": [{"n": 1, "brief": {"question": "q"}}], "turns": [{"who": "check", "found": []}]}, "q") == "" and briefs.said({}, "q") == "" and briefs.said(None) == "", briefs.said(_sf, "x"))
del _asked_of[:]
# ---- 0309, 0310 (docs/ARCHITECT_DESIGN.md §2.19, §2.20): the figures the person asks to see are a part of the brief. The Pathfinder describes each one, a draft of it is drawn before the
# ---- run, the analyst computes for it and the step that draws is given it in words - and the cell that drew its draft
_FIG = {"title": "  Two paths  on the curve ", "kind": "line3d", "x": "x", "y": "y", "z": "z", "note": "They run together, then part.",
        "series": [{"name": "start A", "points": [[0, 50], [7.123456, 66], [14, 38.5]]}, "start B", {"name": "start A"}, {"name": ""}]}
_fb = briefs.normalise({"question": "q", "figures": [_FIG, {"title": "two paths on the CURVE"}, {"kind": "line"}, "no figure", {"title": "Spread", "kind": "violin", "series": ["a", "b", "c", "d", "e"]},
                                                       {"title": "T3", "kind": ["line"]}, {"title": "T4"}]})
_long = briefs.normalise({"figures": [{"title": "t" * 300, "x": "x" * 300, "note": "n" * 700, "series": ["s" * 300, {"name": "many", "points": [[k, k] for k in range(40)]}, {"name": "one"}]}]})["figures"][0]
_layout = "Two panels side by side: on the left the full run with the five paths in five colours; on the right, on the same axes and in the same colours, its first stretch only. " * 2 + "To make clear how soon the paths part."
check("brief.normalise, the figures (0309-0311): a figure is its title - without one it is none, and a title names one figure whatever its case - with its kind where it is one the engine knows, what is on "
      "each axis, the lines it holds by name, four at most and none named twice, and its note; three figures at most, every text bounded - the note as a line of the brief is: one that says how "
      "two panels are laid out and what they are to make clear is kept whole (0311: a live note was cut in the middle of a word at 240 characters). A brief that holds only figures is a brief; "
      "agreed() and working() keep them. A line is its name and nothing else: points a reply gives with it are not kept - a model's numbers draw no figure (0310)",
      _fb["figures"] == [{"title": "Two paths on the curve", "kind": "line3d", "x": "x", "y": "y", "z": "z", "series": [{"name": "start A"}, {"name": "start B"}],
                          "note": "They run together, then part."}, {"title": "Spread", "series": [{"name": "a"}, {"name": "b"}, {"name": "c"}, {"name": "d"}]}, {"title": "T3"}]
      and briefs.MAX["figures"] == 3 and briefs.SERIES == 4 and not hasattr(briefs, "POINTS") and list(briefs.KINDS) == ["line", "scatter", "bar", "histogram", "box", "heatmap", "line3d"]
      and [len(x) for x in (_long["title"], _long["x"], _long["series"][0]["name"], _long["note"])] == [120, 80, 60, 600] and _long["series"][1:] == [{"name": "many"}, {"name": "one"}]
      and 240 < len(_layout) < 600 and briefs.normalise({"figures": [{"title": "T", "note": _layout}]})["figures"][0]["note"] == _layout and briefs.FIGURE_CHARS["note"] == briefs.TEXT_CHARS == 600
      and briefs.normalise({"figures": [{"title": "T"}]}) == {"figures": [{"title": "T"}], "version": 1}
      and briefs.agreed(_fb)["figures"] == _fb["figures"] and briefs.working(_fb)["figures"] == _fb["figures"]
      and briefs.normalise({"figures": "none"}) == {} and briefs.normalise({"figures": [{"title": " "}, 7, None]}) == {} and "points" not in json.dumps(_fb), (_fb, _long))
_s0 = {"question": "q", "decision": "d"}
_s1, _c1s = briefs.sketch(_s0, [_FIG, {"title": "Spread", "kind": "box", "series": ["a", "b"]}])
_s2, _c2s = briefs.sketch(_s1, [2, 1])
_s3, _c3s = briefs.sketch(_s1, [1, 2])
_s4, _c4s = briefs.sketch(_s1, [1])
_s5, _c5s = briefs.sketch(_s1, [])
_s6, _c6s = briefs.sketch(_s1, [1, {"title": "spread", "kind": "bar"}, 7, 0, True, "x", {"title": "New"}, {"title": "One too many"}])
_s7, _c7s = briefs.sketch(_s1, [{"title": "two paths on the curve", "kind": "line", "series": ["start A", {"name": "start B", "points": [[9, 9], [8, 8]]}, "start C"]}, 2])
_s8, _c8s = briefs.sketch(_s1, [{"title": "Two paths on the curve", "series": [{"name": "start A"}]}])
check("brief.sketch (0309): the brief with its figures as a reply gives them - every figure as it is to stand, in order: one that stays by its number among the brief's, a new or changed one in full. "
      "The same set changes nothing; another order, a figure changed, one more or one fewer is said by its place - `figures` where fewer stand; [] takes them all out and the part falls away. A number "
      "the brief does not have, a yes, a word and a figure without a title are passed over, and three are kept. The rest of the brief stays, and the brief passed in is not altered",
      _c1s == ["figures.0", "figures.1"] and [f["title"] for f in _s1["figures"]] == ["Two paths on the curve", "Spread"] and _s1["decision"] == "d" and "figures" not in _s0
      and _c2s == ["figures.0", "figures.1"] and [f["title"] for f in _s2["figures"]] == ["Spread", "Two paths on the curve"] and (_s3, _c3s) == (_s1, [])
      and _c4s == ["figures"] and len(_s4["figures"]) == 1 and _c5s == ["figures"] and _s5 == _s0
      and _c6s == ["figures.1", "figures.2"] and [(f["title"], f.get("kind")) for f in _s6["figures"]] == [("Two paths on the curve", "line3d"), ("spread", "bar"), ("New", None)]
      and _c7s == ["figures.0"] and _s7["figures"][0]["series"] == [{"name": "start A"}, {"name": "start B"}, {"name": "start C"}]
      and _s7["figures"][0]["kind"] == "line" and _s7["figures"][1] == _s1["figures"][1]
      and _s8["figures"] == [{"title": "Two paths on the curve", "series": [{"name": "start A"}]}] and _c8s == ["figures.0", "figures"]
      and briefs.sketch(None, [{"title": "T"}]) == ({"figures": [{"title": "T"}]}, ["figures.0"]) and briefs.sketch(_s1, "all") == (_s0, ["figures"])
      and briefs.sketch(_s1, [0]) == (_s0, ["figures"]) and briefs.sketch(_s1, [True]) == (_s0, ["figures"]) and briefs.sketch(_s1, [3]) == (_s0, ["figures"])
      and len(_s1["figures"]) == 2 and _s1["figures"][0]["series"] == [{"name": "start A"}, {"name": "start B"}], (_c1s, _c2s, _c4s, _c6s, _c7s, _c8s))
_fblock = briefs.render({**_s1, "fixed": {"measure": "m"}, "saved": [dict(_KEPT[0], accepted=True)]})
check("brief.figure_lines and brief.render (0309): a figure in words, a line each - the title, the kind as the analyst reads it, what is on each axis, what it holds by name, what it is to make clear; "
      "a part it does not have is not there. The analyst's BRIEF block lists the figures, numbered, after what is fixed and before the saved analyses; the record of a brief keeps them too",
      briefs.figure_lines(_s1) == ['"Two paths on the curve" - a line in three dimensions; x: x; y: y; z: z; holds: start A, start B; to make clear: They run together, then part.', '"Spread" - box plots; holds: a, b']
      and briefs.figure_lines({"figures": [{"title": "T"}]}) == ['"T"'] and briefs.figure_lines({}) == [] and briefs.figure_lines(None) == []
      and '\nFixed before the run:\n- measure: m\nFigures agreed with the person:\n1. "Two paths on the curve" - a line in three dimensions; x: x; ' in _fblock
      and '\n2. "Spread" - box plots; holds: a, b\nSaved analyses the person chose' in _fblock
      and briefs.render(_s1, record=True) == 'What the answer is for: d\nFigures agreed with the person:\n1. ' + briefs.figure_lines(_s1)[0] + '\n2. "Spread" - box plots; holds: a, b'
      and "Figures agreed" not in briefs.render(_s0), _fblock)
check("architect.parse and architect.block (0309): a reply's `figures` is a list as given - None where the reply does not say, or says it in another shape; the BRIEF block lists the figures the brief "
      "holds, each under the number a reply keeps it by, in words; a brief without figures has no such lines",
      arch.parse('{"say": "x", "figures": [1, {"title": "t"}]}')["figures"] == [1, {"title": "t"}] and arch.parse('{"say": "x"}')["figures"] is None
      and arch.parse('{"say": "x", "figures": "all"}')["figures"] is None and arch.parse('{"say": "x", "figures": []}')["figures"] == []
      and arch.block({**_s1, "version": 3}).endswith('fixed.period: (empty)\nfigures:\n- [1] "Two paths on the curve" - a line in three dimensions; x: x; y: y; z: z; holds: start A, start B; '
                                                       'to make clear: They run together, then part.\n- [2] "Spread" - box plots; holds: a, b')
      and "figures" not in arch.block({"question": "q", "version": 1}), arch.block({**_s1, "version": 3}))
_gn = Notebook("g"); _gr = _gn.new_run("Plot it"); _gr.status = "framing"; _gr.framing = briefs.version({}, {"question": _gr.question})
_gllm, _gseen = _arch_llm([json.dumps({"say": "Sketched.", "figures": [_FIG, {"title": "Spread", "kind": "box", "series": ["a", "b"]}], "brief": {"decision": "to see it"}}),
                           json.dumps({"say": "As they are.", "figures": [1, 2]}), json.dumps({"say": "A word.", "brief": {"expects": "e"}}),
                           json.dumps({"say": "The second first.", "figures": [2, 1]}), json.dumps({"say": "From the first sketch.", "figures": [1, {"title": "New", "kind": "bar"}]}),
                           json.dumps({"say": "None.", "figures": []})])
_gr.framing = _g1 = arch.exchange(_gllm, _gn, _gr, "Show me what it will look like")
_gr.framing = _g2 = arch.exchange(_gllm, _gn, _gr, "Yes")
_gr.framing = _g3 = arch.exchange(_gllm, _gn, _gr, "I expect e")
_gr.framing = _g4 = arch.exchange(_gllm, _gn, _gr, "Swap them")
_gr.framing = _g5 = arch.exchange(_gllm, _gn, _gr, "From the first sketch, with another second", step=2)
_gr.framing = _g6 = arch.exchange(_gllm, _gn, _gr, "No figures after all")
check("architect.exchange, the figures (0309): a reply's `figures` are the brief's from that reply on - one more version of the Pathfinder's, with the reply's other parts, each figure's place named as "
      "changed. Naming the same figures by their numbers changes nothing and makes no version; a reply that says nothing of them leaves them; another order is a version; the numbers are those of the "
      "brief the reply read - that of the step on the person's screen; [] takes them out. The Pathfinder reads the figures under their numbers in BRIEF, from the reply after. Its message says "
      "nothing of them in a field of its own: what the page shows of the figures is the draft's turn (0310)",
      [f["title"] for f in briefs.latest(_g1)["figures"]] == ["Two paths on the curve", "Spread"] and briefs.latest(_g1)["decision"] == "to see it"
      and (_g1["versions"][-1]["by"], _g1["versions"][-1]["why"], _g1["versions"][-1]["changed"]) == ("architect", "answer", ["decision", "figures.0", "figures.1"])
      and len(_g2["versions"]) == 2 and len(_g3["versions"]) == 3 and briefs.latest(_g3)["figures"] == briefs.latest(_g1)["figures"] and _g3["versions"][-1]["changed"] == ["expects"]
      and [f["title"] for f in briefs.latest(_g4)["figures"]] == ["Spread", "Two paths on the curve"] and _g4["versions"][-1]["changed"] == ["figures.0", "figures.1"]
      and [f["title"] for f in briefs.latest(_g5)["figures"]] == ["Two paths on the curve", "New"] and "expects" not in briefs.latest(_g5) and _g5["versions"][-1]["changed"] == ["figures.1"] and len(_g5["versions"]) == 5
      and "figures" not in briefs.latest(_g6) and _g6["versions"][-1]["changed"] == ["figures"]
      and not any("sketched" in t for t in _g6["turns"])
      and "figures:" not in _gseen[0][1] and '\nfigures:\n- [1] "Two paths on the curve" - ' in _gseen[1][1] and '- [2] "Spread" - box plots; holds: a, b\n\nCONVERSATION:' in _gseen[1][1]
      and "BRIEF (version 2):" in _gseen[4][1] and '- [1] "Two paths on the curve" - ' in _gseen[4][1] and '- [2] "Spread" - box plots' in _gseen[4][1] and '- [2] "New" - bars' in _gseen[5][1],
      ([v["changed"] for v in _g6["versions"]], [f["title"] for f in briefs.latest(_g5).get("figures", [])]))
# the step that draws is given the agreed figures; a reply that leaves one out is asked again once, before anything runs; the report says where one was not drawn
from analyst.session import FIGURES_SYSTEM as _FSYS, FIGURES_AGREED as _FAGREED, FIGURES_DRAFT as _FDRAFT
from analyst import draft as drafts, tools
_carries = briefs.carries
_under = lambda *pairs: ("```python\nimport plotly.graph_objects as go\n" + "\n".join(f"t{k} = {agreed!r}\nf{k} = go.Figure(go.Bar(x=[1], y=[float(pct)])); f{k}.update_layout(title={title!r}); f{k}.show()"      # noqa: E731
                                                                                    for k, (agreed, title) in enumerate(pairs)) + "\n```\n" + "\n".join(f"CAPTION: {title}" for _, title in pairs))
_fgb = {"decision": "d", "figures": [{"title": "After against before", "kind": "bar", "x": "part", "y": "y", "series": ["before", "after"], "note": "How far apart the two stand."},
                                     {"title": "The rise in percent", "kind": "line", "series": [{"name": "rise"}]}]}
def _draws(*titles):
    return ("```python\nimport plotly.graph_objects as go\n" + "\n".join(f"f{k} = go.Figure(go.Bar(x=[1], y=[float(pct)])); f{k}.update_layout(title={t!r}); f{k}.show()" for k, t in enumerate(titles))
            + "\n```\n" + "\n".join(f"CAPTION: {t}" for t in titles))
_DRAFT_CELL = "import plotly.graph_objects as go\nfig = go.Figure(go.Bar(x=['before', 'after'], y=[3, 4]))\nfig.update_layout(title='After against before')\nfig.show()"
def _plot(title, meta=None, traces=1, pad=0):
    """A plot as the executor gives one: a Plotly figure's JSON, under a title, computed where its cell said so."""
    return {"data": json.dumps({"data": [{"type": "bar", "y": [1, 2]}] * traces, "layout": {"title": {"text": title}, **({"meta": meta} if meta else {}), "pad": "x" * pad}}), "format": "json"}
def _drafted(brief, question, plots):
    """A framing run whose figures were drafted, as the host leaves it before the analysis starts: one round, its cell _DRAFT_CELL."""
    nb = Notebook("tfg"); r = nb.new_run(question); r.status = "framing"
    r.framing = drafts.keyed(briefs.version({}, {**brief, "question": question}))
    figs = drafts.due(r.framing)
    drafts.settle(r, figs, drafts.draw(lambda system, user, **kw: ("```python\n" + _DRAFT_CELL + "\n```", {"cost": 0.001}), lambda code: (plots, ""), r, figs), 1.5)
    return nb, r
def _fig_run(steps, brief, plots=None):
    seen = {"figures": [], "analyst": []}
    script = [_CELL, _bact(_BREPORT)]
    nb, framed = _drafted(brief, "Did it work?", plots) if plots is not None else (Notebook("tfg"), None)
    def llm(system, user, **h):
        if user.startswith("Rewrite the technical report"): return "# After was 1.2 percent higher than before\n\nplain", {"cost": 0}
        if system.startswith("You are drawing the figures"):
            seen["figures"].append(user); return steps[min(len(seen["figures"]) - 1, len(steps) - 1)], {"cost": 0.002}
        seen["analyst"].append((system, user)); return script[min(len(seen["analyst"]) - 1, len(script) - 1)], {"cost": 0.001}
    k = PersistentKernel(df=_bdf)
    try:
        run = Session(k, nb, llm, data_description="60 rows: part, y", kernel_factory=lambda: PersistentKernel(df=_bdf)).run(
            "Did it work?", budget=Budget(turns=6, dollars=1.0), brief=briefs.latest(framed.framing) if framed else brief, run_id=framed.id if framed else None)
    finally:
        k.cleanup()
    return run, seen
_pp9 = os.environ.get("PYTHONPATH")
if "plotly" in _stubs.FAKE:                  # the kernel's worker imports plotly: the stack's stand-in where the real one is absent
    os.environ["PYTHONPATH"] = os.path.join(ROOT, "tools", "stack", "fakepkgs") + (os.pathsep + _pp9 if _pp9 else "")
try:
    _fa, _fa_seen = _fig_run([_draws("After against before"), _draws("After against before", "The rise in percent")], _fgb)
    _fb2, _fb_seen = _fig_run([_draws("After against before")], _fgb)
    _fc, _fc_seen = _fig_run(["NONE"], _fgb)
    _fd, _fd_seen = _fig_run([_draws("AFTER  against before, 60 rows", "the rise in percent (now)")], _fgb)
    _fe, _fe_seen = _fig_run([_draws("Any title")], {"decision": "d"})
    _plt = lambda *titles: ("```python\nimport matplotlib.pyplot as plt\n" + "\n".join(f"plt.figure(); plt.bar([1], [float(pct)]); plt.title({t!r}); plt.show()" for t in titles)      # noqa: E731
                            + "\n```\n" + "\n".join(f"CAPTION: {t}" for t in titles))
    _fm, _fm_seen = _fig_run([_plt("After against before", "The rise in percent")], _fgb)
    _fn, _fn_seen = _fig_run([_plt("After against before")], _fgb)
    _fq, _fq_seen = _fig_run([_under(("After against before", "After against before"), ("The rise in percent", "Another title"))], _fgb)
    _fp, _fp_seen = _fig_run([_draws("One of its own"), _draws("One of its own", "And another")], _fgb)
    _fr, _fr_seen = _fig_run([_draws("After against before", "The rise in percent")], _fgb, [_plot("After against before", "computed"), _plot("The rise in percent")])
    _ft, _ft_seen = _fig_run([_draws("After against before", "The rise in percent")], _fgb, [_plot("The rise in percent")])
finally:
    if _pp9 is None: os.environ.pop("PYTHONPATH", None)
    else: os.environ["PYTHONPATH"] = _pp9
_fsteps = lambda run: [(x.kind, x.cell_no, x.stdout.strip()[:90], [f.get("title") for f in x.figures]) for x in run.turns if x.step == "figures"]      # noqa: E731
_agreed_block = (_FAGREED + '\n1. "After against before" - bars; x: part; y: y; holds: before, after; to make clear: How far apart the two stand.\n2. "The rise in percent" - a line chart; holds: rise')
check("the figures agreed in the brief (0309), in a run: the analyst reads them in its BRIEF block and its contract says they are drawn after the report from what the kernel holds; the step that "
      "draws is given them under its question, numbered, in words, and its instructions put them first, take NONE for no reply and leave it two figures of its own (0310: there were three in all, "
      "so three agreed figures left the report none of its own). A run without agreed figures reads none of it",
      all("\nFigures agreed with the person:\n1. \"After against before\" - bars; x: part; " in u for _, u in _fa_seen["analyst"])
      and "- The figures agreed with the person are drawn after your report, by a step that sees only what the kernel holds:\n  compute what each one needs, and keep it in a variable.\n" in _fa_seen["analyst"][0][0]
      and _fa_seen["figures"][0].startswith("QUESTION:\nDid it work?\n\n" + _agreed_block + "\n\nTHE REPORT, AS WRITTEN:\n") and _FDRAFT not in _fa_seen["figures"][0]
      and ("\n\nWhere the prompt lists THE FIGURES AGREED WITH THE PERSON, NONE is no reply: draw each of them first, in the order given, as it is described - its kind, what is on each axis, "
           "what it holds - and under its title, word for word; add a figure of your own only where the report needs one the list does not have, two at most. Where the prompt gives ") in _FSYS
      and "three figures in all" not in _FSYS
      and _FAGREED == "THE FIGURES AGREED WITH THE PERSON (draw these first, in this order, each as described and under its title, word for word):"
      and _fe_seen["figures"][0].startswith("QUESTION:\nDid it work?\n\nTHE REPORT, AS WRITTEN:\n") and "Figures agreed" not in _fe_seen["analyst"][0][1] and len(_fe_seen["figures"]) == 1
      and "A figure agreed" not in _fe.report and _fsteps(_fe)[0][3] == ["Any title"], (_fa_seen["figures"][0][:500], _fsteps(_fe)))
check("the figures step, a reply that leaves an agreed figure out (0309): a cell whose code does not name the title is not run - an attempt on the record, said as such - and the step is asked again, "
      "once, with the titles left out; the cell that then names them all runs, and the report's Figures section holds both with no line about a missing one. Asked once only: a second cell that "
      "still leaves one out runs as it is, and the report says which agreed figure was not drawn",
      len(_fa_seen["figures"]) == 2 and _fa_seen["figures"][1] == _fa_seen["figures"][0] + '\n\nYOUR LAST REPLY LEFT OUT a figure agreed with the person (attempt 1 of 4): "The rise in percent". Nothing was run. '
                                                                                         'Write the cell again with every agreed figure in it, each under its title, word for word.'
      and _fsteps(_fa) == [("error", None, 'the reply left out a figure agreed with the person: "The rise in percent"', []), ("cell", 2, "", ["After against before", "The rise in percent"])]
      and "## Figures\n\n- [fig 2] After against before\n- [fig 2] The rise in percent" in _fa.report and "not drawn" not in _fa.report
      and len(_fb_seen["figures"]) == 2 and _fsteps(_fb2)[1][3] == ["After against before"] and '\n\n> A figure agreed in the brief was not drawn: "The rise in percent".' in _fb2.report
      and "## Figures\n\n- [fig 2] After against before" in _fb2.report, (_fsteps(_fa), _fsteps(_fb2), _fb2.report[-200:]))
check("the figures step, NONE where figures were agreed (0309): it is asked again, once, with every agreed title; a second NONE stands, and the report says the figures were not drawn and why. A "
      "title is carried whatever its case and spacing, and with words around it: such a cell is run at once and nothing is said to be missing. A plot the kernel saved itself has no title to "
      "read - the cell's code stands for it: one that names every agreed title draws them and nothing is missing; one that leaves a title out is asked again, and the report names it. A "
      "cell that names an agreed title and draws the figure under another runs at once - the code carries the title - and the report then says that figure was not drawn: what counts is "
      "the title a figure was drawn under. Where two were not drawn, the line names both",
      len(_fc_seen["figures"]) == 2 and '(attempt 1 of 4): "After against before"; "The rise in percent". Nothing was run.' in _fc_seen["figures"][1] and [s[:2] for s in _fsteps(_fc)] == [("error", None)]
      and "## Figures" not in _fc.report
      and '\n\n> The figures were not drawn: the reply left out a figure agreed with the person: "After against before"; "The rise in percent".' in _fc.report
      and len(_fd_seen["figures"]) == 1 and "not drawn" not in _fd.report and _fsteps(_fd) == [("cell", 2, "", ["AFTER  against before, 60 rows", "the rise in percent (now)"])]
      and len(_fm_seen["figures"]) == 1 and "not drawn" not in _fm.report and "- [fig 2] After against before\n- [fig 2] The rise in percent" in _fm.report and [len(x.figures) for x in _fm.turns if x.step == "figures"] == [2]
      and len(_fn_seen["figures"]) == 2 and '\n\n> A figure agreed in the brief was not drawn: "The rise in percent".' in _fn.report and "- [fig 2] After against before" in _fn.report
      and len(_fq_seen["figures"]) == 1 and _fsteps(_fq) == [("cell", 2, "", ["After against before", "Another title"])]
      and '\n\n> A figure agreed in the brief was not drawn: "The rise in percent".' in _fq.report and "- [fig 2] Another title" in _fq.report
      and len(_fp_seen["figures"]) == 2 and _fsteps(_fp)[1][3] == ["One of its own", "And another"]
      and '\n\n> Figures agreed in the brief were not drawn: "After against before"; "The rise in percent".' in _fp.report
      and _carries("fig.update_layout(title='After  AGAINST before')", "after against  before") and not _carries("title='After against'", "After against before") and not _carries("anything", " ")
      and not _carries(None, "t"), (_fsteps(_fc), _fc.report[-200:], _fsteps(_fd)))
check("the figures step and the draft (0310): where the brief's figures were drafted before the run, the step is given the cell that drew them - under the agreed figures, before the report - with "
      "the figures it drew and which of them stand on made-up numbers; its instructions say to draw each as the draft drew it, from what the kernel holds, with no number of the draft's and the "
      "value where the draft prints `?`. A figure whose draft was not drawn is not named there; a run whose figures had no draft is given none",
      _fr_seen["figures"][0].startswith("QUESTION:\nDid it work?\n\n" + _agreed_block + "\n\n" + _FDRAFT + ' (it drew "After against before", "The rise in percent" - on made-up numbers: '
                                        '"The rise in percent"):\n```python\n' + _DRAFT_CELL + "\n```\n\nTHE REPORT, AS WRITTEN:\n")
      and _FDRAFT == "THE DRAFT THE PERSON SAW" and _fr_seen["figures"][0].count(_FDRAFT) == 1 and "- [fig 2] After against before\n- [fig 2] The rise in percent" in _fr.report
      and ("Where the prompt gives THE DRAFT THE PERSON SAW, it is the cell that drew those figures before the run, where no data was: draw each as the draft drew it - the same traces, panels, "
           "axes, colours and names - from what the kernel holds. No number comes from the draft, and where the draft prints `?` the figure prints the value.\n") in _FSYS
      and ('\n\n' + _FDRAFT + ' (it drew "The rise in percent" - on made-up numbers: "The rise in percent"):\n```python\n') in _ft_seen["figures"][0]
      and [d["keys"] for d in _fr.drafts] == [_fr.framing["versions"][0]["keys"]] and _fr.status == "answered" and _fr.framing["turns"][-1]["who"] == "draft"
      and len(_fa.drafts) == 0, (_fr_seen["figures"][0][:900], _ft_seen["figures"][0][:600]))

# ---- 0310 (docs/ARCHITECT_DESIGN.md §2.20): the draft of the figures - a model writes one cell, the host runs it where no data is, and what it drew is kept, a plot to a figure
_dq, (_df1, _df2) = "Did it work?", briefs.normalise(_fgb)["figures"]      # the figures as a brief holds them
_k1, _k2 = drafts.key(_dq, _df1), drafts.key(_dq, _df2)
_dv = briefs.version(briefs.version({}, {"question": _dq, "decision": "d"}), {**_fgb, "question": _dq}, by="architect")      # two versions: the second holds the two figures
_dk = drafts.keyed({**_dv, "versions": [{**_dv["versions"][0], "keys": ["stale"]}, _dv["versions"][1]]})
check("draft.key and draft.keyed (0310): a figure's draft is kept under a key of the question as it stands and the figure as it is described - the same again gives the same key, another wording or "
      "another description another; the framing carries the keys of each version's figures beside its brief, in the figures' order, and none where a version holds no figure; the framing passed "
      "in is not altered",
      bool(re.fullmatch(r"[0-9a-f]{12}", _k1)) and _k1 != _k2 and drafts.key(" Did it  work? ", dict(_df1)) == _k1 and drafts.key("Did it work at all?", _df1) != _k1
      and drafts.key(_dq, {**_df1, "note": "Another."}) != _k1 and drafts.key(_dq, {"title": "T"}) == drafts.key(_dq, {"title": "T"}) != drafts.key(_dq, {"title": "t"})
      and [v.get("keys") for v in _dk["versions"]] == [None, [_k1, _k2]] and _dk["versions"][1]["brief"] == _dv["versions"][1]["brief"] and "keys" not in _dv["versions"][1]
      and drafts.keyed({}) == {"versions": []} and drafts.keyed(None) == {"versions": []} and drafts.keyed({**_dv, "at": 1})["at"] == 1, _dk["versions"])
_due = lambda f: [k for k, _ in drafts.due(f)]      # noqa: E731
_moved = briefs.version({**_dv, "drafts": {_k1: {"basis": "computed"}, _k2: {"basis": "made up"}}}, {**_fgb, "question": "Did it work at all?"})
check("draft.due (0310): the figures of the brief in use that are to be drawn now - each one without a draft, with its key; one drawn is not drawn again; one whose draft could not be drawn is tried "
      "once more and then left; none while the Pathfinder goes on by itself, after its lookups, a reading or a part it opened - the reply after is the one that counts; the version the person went "
      "back to decides; under another wording of the question every figure is due again",
      _due(_dv) == [_k1, _k2] and drafts.due(_dv)[0] == (_k1, _df1) and _due({**_dv, "drafts": {_k1: {"basis": "computed"}}}) == [_k2]
      and _due({**_dv, "drafts": {_k1: {"basis": "made up"}, _k2: {"failed": "x", "tries": 1}}}) == [_k2] and _due({**_dv, "drafts": {_k1: {"basis": "made up"}, _k2: {"failed": "x"}}}) == [_k2]
      and _due({**_dv, "drafts": {_k1: {"basis": "made up"}, _k2: {"failed": "x", "tries": 2}}}) == [] and drafts.TRIES == 2
      and all(_due({**_dv, "turns": [{"who": "architect", "text": "t"}, {"who": w}]}) == [] for w in ("check", "memory", "opened"))
      and _due({**_dv, "turns": [{"who": "check"}, {"who": "architect", "text": "t"}]}) == [_k1, _k2] and _due({**_dv, "turns": [{"who": "draft"}]}) == [_k1, _k2]
      and _due({**_dv, "at": 1}) == [] and _due({}) == [] and _due(None) == []
      and _due(_moved) == [drafts.key("Did it work at all?", f) for f in (_df1, _df2)] and _due({**_moved, "at": 2}) == [], (_due(_dv), _due(_moved)))
_dp = drafts.prompt(" Did it work? ", [_df1, _df2])
check("draft.prompt and draft.cell (0310): the model that writes the cell reads the question as it stands and the figures in words, numbered - and, where there is one, the cell that last drew "
      "figures for the question and the code of the saved analysis the brief builds on; the cell is the code of the reply's python block - of each, in order, where it holds more than one - and "
      "there is none in a reply without a block, with an empty one or with one that never ends",
      _dp == ('QUESTION:\nDid it work?\n\nFIGURES TO DRAW:\n1. "After against before" - bars; x: part; y: y; holds: before, after; to make clear: How far apart the two stand.\n'
              '2. "The rise in percent" - a line chart; holds: rise\n\nReply with the cell.')
      and drafts.prompt("q", [_df2], before=" x = 1\n", saved=" --- cell 1 ---\n") == ('QUESTION:\nq\n\nFIGURES TO DRAW:\n1. "The rise in percent" - a line chart; holds: rise\n\nTHE DRAFT BEFORE:\n'
                                                                                       '```python\nx = 1\n```\n\nA SAVED ANALYSIS THE QUESTION BUILDS ON:\n--- cell 1 ---\n\nReply with the cell.')
      and drafts.prompt("q", [_df2], before=" \n", saved="") == drafts.prompt("q", [_df2])
      and drafts.cell("Here:\n```python\nx = 1\n```\nand\n```py\ny = 2\n\n```\n") == "x = 1\n\ny = 2" and drafts.cell("```\nz = 3\n```") == "z = 3" and drafts.cell("```python  \n  w = 4\n```") == "  w = 4"
      and drafts.cell("x = 1") == "" and drafts.cell("```python\nx = 1") == "" and drafts.cell(None) == "" and drafts.cell("```python\n\n```") == "", _dp)
_ok_cell = ("import numpy as np\nfrom scipy.integrate import solve_ivp\nimport plotly.graph_objects as go\nfrom plotly.subplots import make_subplots\nimport pandas as pd, math, random\n"
            "def load_curve(t):\n    return np.sin(t)\nd = pd.DataFrame({'load': [1, 2]})\nsaved = d.load.mean()\nspread = d.unloaded(0.5)\nvars = d.var()\ninput = vars + 1\n"
            "fig = go.Figure(go.Scatter(y=load_curve(np.arange(3)) + saved))\n"
            "fig.update_layout(title=f'T {1}', meta='computed')\nfig.show()")
_only = "a draft imports numpy, scipy, pandas, plotly and the standard maths modules, and nothing else"
_file = lambda name: f"it reads or writes a file ({name}): a draft has no data and loads none"      # noqa: E731
_uses = lambda name: f"it uses {name}: a draft computes and draws, and nothing else"      # noqa: E731
_refused = {"import os\nx = 1": f"it imports os: {_only}", "from pathlib import Path": f"it imports pathlib: {_only}", "import numpy as np, requests": f"it imports requests: {_only}",
            "from . import x": f"it imports .: {_only}", "from ..mod import x": f"it imports ..mod: {_only}", "import plotly, urllib.request": f"it imports urllib.request: {_only}",
            "import pandas as pd\nd = pd.read_csv('f.csv')": _file("read_csv"), "from numpy import loadtxt": _file("loadtxt"), "import numpy as np\nnp.load('x.npy')": _file("load"),
            "fig.write_html('x.html')": _file("write_html"), "d.to_csv('x.csv')": _file("to_csv"), "np.savetxt('f', a)": _file("savetxt"), "a.tofile('f')": _file("tofile"),
            "x = open('f').read()": _uses("open"), "eval('1')": _uses("eval"), "getattr(pd, 'x')": _uses("getattr"), "().__class__": _uses("__class__"), "__import__('os')": _uses("__import__"),
            "exec('x = 1')": _uses("exec"), "g = globals()": _uses("globals")}
check("draft.screen (0310): a cell is run only where it parses, imports nothing but numpy, scipy, pandas, plotly and the maths modules, calls nothing that reads or writes a file, and uses no "
      "name that leads out of the cell - the reason is said in words the model can act on. What only looks like it is let through: a function of the cell's own named like a loader, a column "
      "read as an attribute, a name that begins like one, a call whose name only holds such a word, a variable named vars or input. The cell is given no data; this keeps one that means "
      "well from reading the person's files",
      drafts.screen(_ok_cell) == "" and drafts.screen("x = 1") == "" and drafts.screen("") == ""
      and not {c: (drafts.screen(c), why) for c, why in _refused.items() if drafts.screen(c) != why}
      and drafts.screen("x = (").startswith("it does not parse - ") and drafts.screen("x = (").endswith(", line 1") and drafts.screen("def f(:\n  pass").startswith("it does not parse - ")
      and drafts.MODULES[:4] == ("numpy", "scipy", "pandas", "plotly") and "os" not in drafts.MODULES and "requests" not in drafts.MODULES,
      {c: (drafts.screen(c), why) for c, why in _refused.items() if drafts.screen(c) != why})
_png = {"data": "iVBOR", "format": "png"}
_pa, _pr = _plot("AFTER against  before", "computed"), _plot("The rise in percent (draft)")
_r1 = drafts.read([_pr, _png, _pa, _plot("One more")], [_df1, _df2])
_plain = {"data": json.dumps({"data": [{"type": "bar"}], "layout": {"title": "After against before", "meta": {"basis": "computed"}}}), "format": "json"}
_plain2 = {"data": json.dumps({"data": [{"type": "scatter"}], "layout": {"title": "The rise in percent"}}), "format": "json"}      # a title as a plain text, as an older Plotly writes one
_nothing = [{"data": json.dumps({"data": [], "layout": {"title": {"text": "After against before"}}}), "format": "json"}, {"data": "{not json", "format": "json"}, {"data": "[1]", "format": "json"},
            {"data": "<div>After against before</div>", "format": "html"}, {"data": json.dumps({"layout": {"title": {"text": "After against before"}}}), "format": "json"}, "x", None]
check("draft.read (0310): what a cell drew, a plot to a figure - a plot stands for the figure whose title it carries, whatever the order they were shown in, the case and the words around it; one "
      "under another title stands for the figure left only where as many plots as figures were drawn - in the order shown; otherwise nothing is guessed - and so does a second plot under a title that has its "
      "figure. A title may be a plain text. Only a Plotly figure with something drawn counts: a picture, "
      "a page, a plot without a trace and what does not parse are passed over, and one too long to keep is counted. A figure is computed only where its cell said so, in so many words: any "
      "other is made up",
      _r1 == ({0: {"plot": _pa["data"], "basis": "computed"}, 1: {"plot": _pr["data"], "basis": "made up"}}, 0)
      and drafts.read([_plot("Something else"), _plot("After against before")], [_df1, _df2])[0] == {0: {"plot": _plot("After against before")["data"], "basis": "made up"},
                                                                                                    1: {"plot": _plot("Something else")["data"], "basis": "made up"}}
      and drafts.read([_plot("Something else")], [_df1, _df2]) == ({}, 0) and drafts.read([_plot("Something else"), _plot("x"), _plot("y")], [_df1, _df2]) == ({}, 0)
      and drafts.read([_plot("Something else")], [_df1])[0] == {0: {"plot": _plot("Something else")["data"], "basis": "made up"}}
      and drafts.read([_plain], [_df1]) == ({0: {"plot": _plain["data"], "basis": "made up"}}, 0) and drafts.read([_plot("After against before", "Computed")], [_df1])[0][0]["basis"] == "made up"
      and drafts.read([_plain2, _plain], [_df1, _df2])[0] == {0: {"plot": _plain["data"], "basis": "made up"}, 1: {"plot": _plain2["data"], "basis": "made up"}}
      and drafts.read([_plot("One thing"), _plot("Another", "computed")], [_df1, _df2])[0] == {0: {"plot": _plot("One thing")["data"], "basis": "made up"},
                                                                                              1: {"plot": _plot("Another", "computed")["data"], "basis": "computed"}}
      and drafts.read([_plot("After against before"), _plot("After against before", "computed")], [_df1, _df2])[0] == {0: {"plot": _plot("After against before")["data"], "basis": "made up"},
                                                                                                                      1: {"plot": _plot("After against before", "computed")["data"], "basis": "computed"}}
      and drafts.read(_nothing, [_df1]) == ({}, 0) and drafts.read([_plot("After against before", pad=drafts.PLOT_CHARS)], [_df1]) == ({}, 1)
      and drafts.read(None, [_df1]) == ({}, 0) and drafts.read([_plot("no figure to stand for")], []) == ({}, 0) and (drafts.COMPUTED, drafts.MADE_UP) == ("computed", "made up")
      and drafts.PLOT_CHARS == 1_500_000, _r1)
_blk = lambda code: "```python\n" + code + "\n```"      # noqa: E731
_both = [_plot("After against before", "computed"), _plot("The rise in percent")]
_boom = 'Traceback (most recent call last):\n  File "<string>", line 1, in <module>\nZeroDivisionError: division by zero'
def _draft_run(replies, runs, usages=None, before=None, saved="", asked=None):
    """One round on a framing run whose brief holds the two figures: the replies and what the cells gave are scripted. Returns the run, the round, what the model was sent and the cells run."""
    nb = Notebook("d"); r = nb.new_run(asked or _dq); r.status = "framing"; r.framing = drafts.keyed(_dv); r.drafts = list(before or [])
    seen, ran = [], []
    def llm(system, user, **kw):
        seen.append((system, user, kw))
        return replies[len(seen) - 1], (usages[len(seen) - 1] if usages else {"cost": 0.002})
    def run_cell(code):
        ran.append(code)
        return runs[len(ran) - 1]
    return r, drafts.draw(llm, run_cell, r, drafts.due(r.framing), saved), seen, ran
_again = lambda why, shown="": "\n\nYOUR LAST REPLY DID NOT GIVE THE DRAFT: " + why + "." + shown + "\nReply with the whole cell again, corrected."      # noqa: E731
_ra, _ma, _sa, _na = _draft_run([_blk("c1")], [(_both, "")], before=[{"code": "an old cell", "keys": ["k"]}, {"code": "the cell before", "keys": ["k"]}], saved="--- cell 1 ---",
                                asked="What the run was first asked")
_rb, _mb, _sb, _nb = _draft_run(["I would rather not.", _blk("c2")], [(_both, "")], usages=[None, {"cost": 0.003}])
_rc, _mc, _sc, _nc = _draft_run([_blk("c1"), _blk("c2")], [([], _boom), (_both, None)])
check("draft.draw (0310): one round is one call where the cell runs and draws every figure - the draft's instructions, the question of the brief in use (whatever the run was first asked) and "
      "the figures, the cell before and the saved analysis' "
      "code where there are any, at a low effort; each figure with its plot and what its numbers are, and the cell with the figures it drew. A reply without a cell, and a cell that fails, "
      "are asked for once more with what went wrong - the cell and its error shown - and the second reply's cell is the round's; what the calls cost is added up",
      _ma == {"drawn": {_k1: {"plot": _both[0]["data"], "basis": "computed"}, _k2: {"plot": _both[1]["data"], "basis": "made up"}}, "cells": [{"code": "c1", "keys": [_k1, _k2]}], "failed": "", "calls": 1, "cost": 0.002}
      and _sa == [(drafts.SYSTEM, drafts.prompt(_dq, [_df1, _df2], "the cell before", "--- cell 1 ---"), {"effort": ("low",)})] and _na == ["c1"] and drafts.EFFORT == ("low",)
      and len(_sb) == 2 and _sb[1][1] == _sb[0][1] + _again("the reply held no python block") and _sb[0][1] == drafts.prompt(_dq, [_df1, _df2]) and _nb == ["c2"]
      and (_mb["cells"], _mb["failed"], _mb["calls"], _mb["cost"]) == ([{"code": "c2", "keys": [_k1, _k2]}], "", 2, 0.003)
      and _sc[1][1] == _sc[0][1] + _again("the cell failed: ZeroDivisionError: division by zero", "\n```python\nc1\n```\nERROR:\n" + tools.condense_error(_boom, code="c1"))
      and _nc == ["c1", "c2"] and _mc["cells"] == [{"code": "c2", "keys": [_k1, _k2]}] and _mc["calls"] == 2 and drafts.ATTEMPTS == 2 and _ra.framing == drafts.keyed(_dv) and len(_ra.drafts) == 2,
      (_ma["cells"], _sb[1][1][-200:], _sc[1][1][-300:]))
_rd, _md, _sd, _nd = _draft_run([_blk("c1"), _blk("c2")], [([_plot("After against before")], ""), ([], "Traceback (most recent call last):\nValueError: bad")])
_re2, _me, _se, _ne = _draft_run([_blk("c1"), _blk("c2")], [([_plot("After against before")], ""), ([_plot("The rise in percent", "computed")], "")])
_rf, _mf, _sf2, _nf = _draft_run([_blk("import os"), _blk("d = pd.read_csv('f')")], [])
_rg, _mg, _sg, _ng = _draft_run(["", _blk("c2")], [(_both, "")], usages=[{"declined": "safety", "cost": 0.001}, {}])
_rh, _mh, _sh, _nh = _draft_run(["```python\nx = 1", "Still nothing."], [], usages=[{"truncated": True}, {}])
_ri, _mi, _si, _ni = _draft_run([_blk("c1"), _blk("c2")], [([_plot("After against before"), _plot("The rise in percent", pad=drafts.PLOT_CHARS)], "")] * 2)
_rj, _mj, _sj, _nj = _draft_run([_blk("c1"), _blk("c2")], [([_plot("After against before")], _boom), ([], "Traceback (most recent call last):\nValueError: bad")])
_rk, _mk, _sk, _nk = _draft_run([_blk("c1"), _blk("c2")], [(_both, _boom)])
_rl, _ml, _sl, _nl = _draft_run([_blk("c1"), _blk("c2")], [(_both + [_plot("One more, too long", pad=drafts.PLOT_CHARS)], "")])
check("draft.draw, what goes wrong (0310): a cell that leaves a figure out is asked for once more, naming it; where the second cell fails, the figure the first drew keeps its plot and the other "
      "has none, with why. Where each cell drew one of two, each figure has its plot and both cells stand, each with its figure. A cell the screen refuses is not run - neither of two: no cell "
      "reached the sandbox. A reply the model declined is not asked for again; one cut off before its cell is said as such; a figure too large to keep is said, with what to do about it. "
      "What a cell drew before it failed counts: the figure it drew keeps that plot where the second cell fails too, and a cell that drew every figure before it failed is not asked for "
      "again - nor is one that drew every figure and one more that is too large",
      _sd[1][1] == _sd[0][1] + _again('the cell drew no figure under "The rise in percent"', "\n```python\nc1\n```") and list(_md["drawn"]) == [_k1] and _md["cells"] == [{"code": "c1", "keys": [_k1]}]
      and (_md["failed"], _md["calls"]) == ("the cell failed: ValueError: bad", 2)
      and list(_me["drawn"]) == [_k1, _k2] and _me["cells"] == [{"code": "c1", "keys": [_k1]}, {"code": "c2", "keys": [_k2]}] and _me["failed"] == "" and _me["drawn"][_k2]["basis"] == "computed"
      and _nf == [] and _mf == {"drawn": {}, "cells": [], "failed": "the cell was not run: " + _file("read_csv"), "calls": 2, "cost": 0.004}
      and _sf2[1][1] == _sf2[0][1] + _again(f"the cell was not run: it imports os: {_only}", "\n```python\nimport os\n```")
      and (_mg["failed"], _mg["calls"], _mg["cost"], _ng) == ("the model declined to reply (safety)", 1, 0.001, [])
      and _sh[1][1] == _sh[0][1] + _again("the reply was cut off at the token limit before a cell arrived") and (_mh["failed"], _mh["calls"]) == ("the reply held no python block", 2)
      and _si[1][1] == _si[0][1] + _again("a figure the cell drew is too large to keep: it takes fewer points", "\n```python\nc1\n```") and list(_mi["drawn"]) == [_k1]
      and _mi["failed"] == "a figure the cell drew is too large to keep: it takes fewer points" and _mi["cells"] == [{"code": "c2", "keys": [_k1]}]
      and _sj[1][1] == _sj[0][1] + _again("the cell failed: ZeroDivisionError: division by zero", "\n```python\nc1\n```\nERROR:\n" + tools.condense_error(_boom, code="c1"))
      and _mj == {"drawn": {_k1: {"plot": _plot("After against before")["data"], "basis": "made up"}}, "cells": [{"code": "c1", "keys": [_k1]}], "failed": "the cell failed: ValueError: bad", "calls": 2, "cost": 0.004}
      and (_nk, len(_sk), _mk["failed"], _mk["calls"], list(_mk["drawn"]), _mk["cells"]) == (["c1"], 1, "", 1, [_k1, _k2], [{"code": "c1", "keys": [_k1, _k2]}])
      and (_nl, _ml["failed"], _ml["calls"], list(_ml["drawn"])) == (["c1"], "", 1, [_k1, _k2]),
      (_md, _me["cells"], _mf, _mg, _mh, _mi["cells"], _mj, _mk["cells"]))
_figs = drafts.due(_rd.framing)
_was = json.dumps(_rd.framing)
drafts.settle(_rd, _figs, _md, 7.26)
_t1 = _rd.framing["turns"][-1]
_due1 = drafts.due(_rd.framing)
drafts.settle(_rd, _due1, drafts.lost("the sandbox did not answer"), 20.04)
_t2 = _rd.framing["turns"][-1]
drafts.settle(_ra, drafts.due(_ra.framing), _ma, 3)
check("draft.settle and draft.line (0310): a round taken into its run - the framing says of each figure what its draft is: its basis, or why there is none and how often it was tried; the round is "
      "the conversation's last turn, with the figures drawn, the ones without a draft and why, the version, the seconds, the cost and the number of its last call; the cells that drew stand on "
      "the run's record, after the ones before. A figure without a draft is due once more, and after a second round that came to nothing - a round that could not be made at all counts - no "
      "longer. The Pathfinder reads a round as one line of CONVERSATION: what was drawn, on what numbers, and what was not, with why",
      _rd.framing["drafts"] == {_k1: {"basis": "made up"}, _k2: {"failed": "the sandbox did not answer", "tries": 2}} and _rd.framing["draft_calls"] == 2 and _rd.drafts == [{"code": "c1", "keys": [_k1]}]
      and _t1 == {"who": "draft", "drawn": [{"title": "After against before", "basis": "made up"}], "missing": ["The rise in percent"], "failed": "the cell failed: ValueError: bad", "v": 2, "secs": 7.3,
                  "cost": 0.004, "call": 2}
      and _due1 == [(_k2, _df2)] and _t2 == {"who": "draft", "drawn": [], "missing": ["The rise in percent"], "failed": "the sandbox did not answer", "v": 2, "secs": 20.0, "cost": 0.0}
      and drafts.due(_rd.framing) == [] and [t["who"] for t in _rd.framing["turns"]] == ["draft", "draft"] and json.loads(_was)["versions"] == _rd.framing["versions"]
      and [(x["k"], x["turns"]) for x in _rd.framing.get("steps", [])] == [(1, 0), (2, 2)] and _rd.framing.get("step") == 2      # each round is counted into the step in use (0316)
      and _ra.framing["drafts"] == {_k1: {"basis": "computed"}, _k2: {"basis": "made up"}} and [d["code"] for d in _ra.drafts] == ["an old cell", "the cell before", "c1"]
      and _ra.framing["turns"][-1] == {"who": "draft", "drawn": [{"title": "After against before", "basis": "computed"}, {"title": "The rise in percent", "basis": "made up"}], "v": 2, "secs": 3, "cost": 0.002, "call": 1}
      and drafts.line(_t1) == 'Draft of the figures: drawn - "After against before" (on made-up numbers); not drawn - "The rise in percent": the cell failed: ValueError: bad'
      and drafts.line(_ra.framing["turns"][-1]) == 'Draft of the figures: drawn - "After against before" (computed), "The rise in percent" (on made-up numbers)'
      and drafts.line(_t2) == 'Draft of the figures: not drawn - "The rise in percent": the sandbox did not answer'
      and arch.conversation([{"who": "architect", "text": "A draft is being drawn."}, _t1]) == "CONVERSATION:\nPathfinder: A draft is being drawn.\n" + drafts.line(_t1)
      and drafts.lost("why") == {"drawn": {}, "cells": [], "failed": "why", "calls": 0, "cost": 0.0} and drafts.lost("why", 2)["calls"] == 2, (_rd.framing["drafts"], _t1, _t2))
_ra.brief = briefs.agreed(briefs.latest(_ra.framing))
drafts.settle(_re2, drafts.due(_re2.framing), _me)
_re2.brief = briefs.agreed(briefs.latest(_re2.framing))
_rd.brief = briefs.agreed(briefs.latest(_rd.framing))
_newer = Notebook("n").new_run(_dq); _newer.framing, _newer.brief, _newer.drafts = _ra.framing, _ra.brief, _ra.drafts + [{"code": "a later cell", "keys": [_k2]}]
_other = Notebook("n").new_run(_dq); _other.framing, _other.drafts, _other.brief = _ra.framing, _ra.drafts, {**_ra.brief, "question": "Did it work at all?"}
_bare = Notebook("n").new_run(_dq); _bare.framing, _bare.drafts, _bare.brief = {**_ra.framing, "drafts": {}}, _ra.drafts, _ra.brief
check("draft.agreed (0310): what the step that draws the figures is given of their drafts - the cell that drew each agreed figure, a cell once, with the figures it drew and which of them stand on "
      "made-up numbers; where two cells drew, both; where a figure was drawn again, its last cell. A figure without a draft is not there, nor is any under another question than the one the "
      "drafts were drawn for, and a run without a brief has none. A figure whose basis is not on record reads as made up",
      drafts.agreed(_ra) == [{"code": "c1", "titles": ["After against before", "The rise in percent"], "made_up": ["The rise in percent"]}]
      and drafts.agreed(_re2) == [{"code": "c1", "titles": ["After against before"], "made_up": ["After against before"]}, {"code": "c2", "titles": ["The rise in percent"], "made_up": []}]
      and drafts.agreed(_rd) == [{"code": "c1", "titles": ["After against before"], "made_up": ["After against before"]}]
      and drafts.agreed(_newer) == [{"code": "c1", "titles": ["After against before"], "made_up": []}, {"code": "a later cell", "titles": ["The rise in percent"], "made_up": ["The rise in percent"]}]
      and drafts.agreed(_other) == [] and drafts.agreed(Notebook("n").new_run("q")) == []
      and drafts.agreed(_bare) == [{"code": "c1", "titles": ["After against before", "The rise in percent"], "made_up": ["After against before", "The rise in percent"]}],
      (drafts.agreed(_ra), drafts.agreed(_re2), drafts.agreed(_newer), drafts.agreed(_bare)))
_cn = Notebook("c"); _c1 = _cn.new_run("q1"); _c1.status = "answered"
_c1.turns = [Turn(kind="cell", code="a = 1\n", cell_no=1), Turn(kind="cell", code="1/0", error="boom"), Turn(kind="cell", code="fig = draw(a)\n", cell_no=2, step="figures", figures=[{"plotly": True, "title": "T"}])]
_c2 = _cn.new_run("q2", _c1.id); _c2.status = "answered"; _c2.turns = [Turn(kind="cell", code="b = a + 1", cell_no=3), Turn(kind="cell", code="c = b * 2", cell_no=4)]
_cb1, _cb2, _cb3, _cb4 = ("--- cell 1 ---\n```python\na = 1\n```", "--- cell 2 (drew its figures) ---\n```python\nfig = draw(a)\n```", "--- cell 3 ---\n```python\nb = a + 1\n```", "--- cell 4 ---\n```python\nc = b * 2\n```")
check("draft.saved_code (0310): the code of an analysis a brief builds on - the cells along its path that ran, in order, each under its number, the one that drew its figures said so; a cell that "
      "failed is not there. Longer than its bound, it keeps what fits - the cell that drew first, then the others from the last back - and says how many it left out; the last cell that drew "
      "stays whatever its length. An analysis that is not on record gives nothing",
      drafts.saved_code(_cn, _c2.id) == "\n\n".join([_cb1, _cb2, _cb3, _cb4]) and drafts.saved_code(_cn, _c1.id) == "\n\n".join([_cb1, _cb2])
      and drafts.saved_code(_cn, _c2.id, len(_cb2) + len(_cb4) + len(_cb3)) == "\n\n".join(["(1 cell left out)", _cb2, _cb3, _cb4])
      and drafts.saved_code(_cn, _c2.id, len(_cb2) + len(_cb4) + len(_cb3) - 1) == "\n\n".join(["(2 cells left out)", _cb2, _cb4])
      and drafts.saved_code(_cn, _c2.id, 1) == "\n\n".join(["(3 cells left out)", _cb2]) and drafts.saved_code(_cn, "none") == "" and drafts.SAVED_CHARS == 16_000, drafts.saved_code(_cn, _c2.id, 1))
_pdir = tempfile.mkdtemp(); _ps = drafts.Plots(_pdir)
_ps.put("7", "8", _k1, '{"data": [0]}'); _ps.put("7", "8", _k1, '{"data": [1]}'); _ps.put("../../x", "8/..", "a.b", "p")
check("draft.Plots (0310): a draft's plot is a file of its own beside the thread's record - <storage>/drafts/<thread>/<run>/<key>.json, the plot as it was given - written whole or not at all, "
      "the last one standing; one that is not there is none. A thread, a run and a key name a file under that folder and nowhere else, whatever they hold - and no file where one of them "
      "holds nothing to name it by",
      _ps.get("7", "8", _k1) == '{"data": [1]}' and os.path.isfile(os.path.join(_pdir, "drafts", "7", "8", _k1 + ".json")) and _ps.get("7", "8", "none") is None and _ps.get("9", "8", _k1) is None
      and _ps.get("x", "8", "ab") == "p" and sorted(os.listdir(os.path.join(_pdir, "drafts"))) == ["7", "x"] and os.listdir(_pdir) == ["drafts"]
      and os.listdir(os.path.join(_pdir, "drafts", "7", "8")) == [_k1 + ".json"]
      and _ps.get("..", "8", _k1) is None and _ps.get("7", "", _k1) is None and _ps.get("7", "8", "../..") is None and _ps._path("..", "8", "k") == "", os.listdir(os.path.join(_pdir, "drafts")))
# a branch's drafts (0331): those of the chains it went on from, kept under it too
_ln = Notebook("tl")
_la, _lb, _lc, _lo, _lx, _ly = (_ln.new_run("q") for _ in range(6))
_lb.branch, _lc.branch, _lo.branch = {"of": _la.id, "turn": 2}, {"of": _lb.id, "turn": 3}, {"of": "gone", "turn": 1}
_lx.branch, _ly.branch = {"of": _ly.id, "turn": 1}, {"of": _lx.id, "turn": 1}
_ps.put("7", _la.id, "k1", "p1"); _ps.put("7", _la.id, "k2", "p2"); _ps.put("7", _lb.id, "k2", "p2b")
open(os.path.join(_pdir, "drafts", "7", _la.id, "k3.json.part"), "w").write("half")      # a plot being written: no plot yet
_carried = _ps.carry("7", drafts.lineage(_ln, _lc.id)[1:], _lc.id)
check("draft.lineage and Plots.carry (0331): a run and the chains it went on from, nearest first, to a run that is no branch or one the record no longer has - a ring of branches is "
      "walked once; under a branch, every plot of those chains it has not - of a figure two of them have, the nearest's -, and how many; nothing where all are there already, "
      "where those chains have none, or where the run names no folder",
      drafts.lineage(_ln, _lc.id) == [_lc.id, _lb.id, _la.id] and drafts.lineage(_ln, _la.id) == [_la.id] and drafts.lineage(_ln, _lo.id) == [_lo.id, "gone"]
      and drafts.lineage(_ln, "none") == ["none"] and drafts.lineage(None, 5) == ["5"] and drafts.lineage(_ln, _lx.id) == [_lx.id, _ly.id]
      and _carried == 2 and _ps.get("7", _lc.id, "k1") == "p1" and _ps.get("7", _lc.id, "k2") == "p2b" and sorted(os.listdir(os.path.join(_pdir, "drafts", "7", _lc.id))) == ["k1.json", "k2.json"]
      and _ps.carry("7", [_la.id, _lb.id], _lc.id) == 0 and _ps.carry("7", ["nothing"], "x9") == 0 and not os.path.exists(os.path.join(_pdir, "drafts", "7", "x9"))
      and _ps.carry("7", [_la.id], "..") == 0, (_carried, drafts.lineage(_ln, _lc.id)))
_dsys = " ".join(drafts.SYSTEM.split())
_dtexts = {"the draft's instructions": drafts.SYSTEM, **{f"analyst/draft.py string {k}": t for k, t in enumerate(_authored_strings("analyst/draft.py"))}}
_dsaid = {"what it is": "You draw a draft of the figures a person asked to see, before their question is analysed.", "no result": "It is not a result.",
          "the reply": "Reply with one Python cell, as a ```python block, and nothing else.",
          "every figure, under its title": "It draws every figure under FIGURES TO DRAW, in the order given, with Plotly: one `fig.show()` for each, under its title, word for word.",
          "no data": "It has no data. Nothing is loaded, and it reads no file and no address.",
          "what it imports": "It imports " + ", ".join(drafts.MODULES[:4]) + " and the standard maths modules, and nothing else.",
          "light": "It ends within a few seconds: a draft takes no more points than its shape needs.",
          "a rule: computed, and said": 'Compute it in full, as the analysis will, and say so on the figure: `fig.update_layout(meta="computed")`.',
          "anything else: made up": "Draw the figure as it will stand - the same kind of traces, the same panels, axes, units and names - on numbers you make up, in ranges that fit what is measured.",
          "no meta": "Give it no `meta`: the person is then told that the numbers are made up.",
          "no value printed": "Where the figure is to print a value - in a label, a legend or its title - print `?` in its place.",
          "in doubt": "When in doubt, it is the second kind.",
          "the draft before": "THE DRAFT BEFORE: the cell that last drew figures for this question. The person asked for a change since: keep what the change does not touch.",
          "the saved analysis": "A SAVED ANALYSIS THE QUESTION BUILDS ON: the code of its cells.",
          "once more": "A cell that fails comes back to you once, with what went wrong."}
check("the draft's instructions (0310): one cell that draws every figure under its title; it has no data and imports what the screen lets through; a figure whose shape follows from a rule alone "
      "is computed and says so - the word the engine reads - and any other is drawn as it will stand on made-up numbers, says nothing, and prints no value; in doubt it is made up; the two things "
      "it may be given are named as the prompt names them. The standing rules hold: none of the tested tasks' vocabulary, no section named for thinking or reasoning - in the instructions and "
      "in every string of analyst/draft.py",
      not [k for k, s in _dsaid.items() if s not in _dsys] and all(h + ":\n" in drafts.prompt("q", [_df1], "x", "y") for h in ("THE DRAFT BEFORE", "A SAVED ANALYSIS THE QUESTION BUILDS ON", "FIGURES TO DRAW"))
      and f'meta="{drafts.COMPUTED}"' in drafts.SYSTEM and len(drafts.SYSTEM) < 2400 and drafts.SECONDS == 20
      and not {n: sorted({m.group(0) for m in _DOMAIN.finditer(t)}) for n, t in _dtexts.items() if _DOMAIN.search(t)}
      and not _re_c.search(r"(?i)\b(thinking|reasoning|scratchpad|memory|private)\b", drafts.SYSTEM),
      ([k for k, s in _dsaid.items() if s not in _dsys], {n: sorted({m.group(0) for m in _DOMAIN.finditer(t)}) for n, t in _dtexts.items() if _DOMAIN.search(t)}, len(drafts.SYSTEM)))
# ---- 0313: the question read cold before its analysis starts (analyst/cold.py; docs/ARCHITECT_DESIGN.md §2.22) - and what the Pathfinder is told of wording it
from analyst import cold
_cq = "Draw the series as bars, following on from the bar version of 14 May. One colour, as  before."
_cb = {"question": _cq, "version": 3, "decision": "I want to see it.", "expects": "It rises.",
       "also_check": [{"text": "It may be the season", "source": "architect", "accepted": False}, {"text": "It may be the soil", "source": "architect", "accepted": True}]}
_cgiven = cold.given(_cq, _cb)
check("cold.given: what the analyst is given of a framed question, in the order its prompt has it - the analyses the question follows, the data as described, the question, and the BRIEF block of "
      "the brief as agreed: a line the Pathfinder proposed and the person did not accept is not there. The checks a run on data makes are there where the run has data, and not where it has none. "
      "A part that is not given is not there, and a brief that holds nothing is the question alone",
      _cgiven == f"QUESTION:\n{_cq}\n\n{briefs.render(briefs.agreed(_cb))}" and "It may be the soil" in _cgiven and "It may be the season" not in _cgiven
      and "[always]" in _cgiven and "[always]" not in cold.given(_cq, _cb, data=False) and "What they expect to see: It rises." in _cgiven
      and cold.given(_cq, _cb, True, "`df`: 3 rows", "EARLIER IN THIS THREAD") == f"EARLIER IN THIS THREAD\n\nDATA:\n`df`: 3 rows\n\n{_cgiven}"
      and cold.given(" Q? ", {}) == "QUESTION:\nQ?" and cold.given(None, None) == "QUESTION:\n")
_cn = lambda reply: cold.named(reply, _cq)      # noqa: E731
check("cold.named: the phrases a reply names, each as the question has it - found whatever the case and the spaces between its words, in the question's own spelling - once each, three at most; a "
      "phrase the question does not hold is dropped, and so is what is no text; a reply that is no such object, fenced or bare, names none",
      _cn('{"cannot_place": ["the bar version of 14 may", "As before", "the usual one", "as before", 5, "", "  "]}') == ["the bar version of 14 May", "as before"]
      and _cn('```json\n{"cannot_place": ["14 May"]}\n```') == ["14 May"] and _cn('{"cannot_place": ["Draw", "the series", "as bars", "One colour"]}') == ["Draw", "the series", "as bars"]
      and _cn("nothing to say") == [] and _cn('{"cannot_place": "14 May"}') == [] and _cn('{"other": ["14 May"]}') == [] and _cn("") == [] and cold.named('{"cannot_place": ["x"]}', None) == []
      and cold.PHRASES == 3)
_crl, _crs = _arch_llm(['{"cannot_place": ["as before"]}', "I cannot say."], usage={"cost": 0.002})
_cr1, _cr2 = cold.read(_crl, _cq, _cgiven), cold.read(_crl, _cq, "QUESTION:\nx")
check("cold.read: one call - the reader's instructions, what the analyst is given and the request for the object, at low effort - and what came of it: the phrases of the question, and what the "
      "call cost; a reply that cannot be read names nothing and costs what it cost; a call that says nothing of its cost cost nothing",
      _cr1 == (["as before"], 0.002) and _cr2 == ([], 0.002) and len(_crs) == 2 and _crs[0][0] == cold.SYSTEM and _crs[0][1] == _cgiven + "\n\nReply with the JSON object."
      and _crs[0][2] == {"effort": ("low",)} == {"effort": cold.EFFORT} and _crs[1][1] == "QUESTION:\nx\n\nReply with the JSON object."
      and cold.read(lambda s, u, **kw: ('{"cannot_place": []}', None), _cq, _cgiven) == ([], 0.0))
_yn = Notebook("y"); _y0 = _yn.new_run("Does B beat A?"); _y0.status = "answered"; _y0.report = "B beats A by 3."
_yr = _yn.new_run(_cq, _y0.id); _yr.status = "framing"
_yr.framing = {**briefs.version({}, {"question": _cq, "expects": "It rises.", "also_check": [{"text": "It may be the season", "source": "architect", "accepted": False}]}), "calls": 4}
_yread, _yseen = _arch_llm(['{"cannot_place": []}'], usage={"cost": 0.002}); _yarch, _yaseen = _arch_llm([])
_y1, _yok1 = cold.ready(_yarch, _yread, _yn, _yr, data="`df`: 3 rows")
_y1b, _yok1b = cold.ready(_yarch, _yread, _yn, _yr)        # the same version again: the reader has no reply left, and is not asked
_ygot = _yseen[0][1][:-len("\n\nReply with the JSON object.")] if _yseen else ""
_yasks = briefs.latest(_yr.framing)["question"]
_yr.question, _yr.brief, _yr.data = _yasks, briefs.agreed(briefs.latest(_yr.framing)), {"rows": 3}      # as the analysis takes them when it starts (the host, Session.run)
_ysees = Session(None, _yn, None, data_description="`df`: 3 rows")._user_prompt(_yr, Budget(), 1, 0.0)
check("cold.ready, a question that stands on its own: one call, the reader's. The reader is given what the analyst will be given, to the letter: the analyst's own first prompt starts with it - the "
      "thread's ledger of the analyses the question follows, the data as described, the question, the brief as agreed, without the line the person did not accept. The read is a turn of the "
      "conversation - nothing missing, the version read, the cost, the seconds, and its number among the reads: the Pathfinder's calls are counted apart, and stay as they were. The framing "
      "lists the version as read, and the analysis can start; the Pathfinder is not called, and is told nothing of it. The same version is not read again: no call at all",
      _yok1 is True and len(_yseen) == 1 and not _yaseen and _y1["read"] == [1] and _y1["calls"] == 4 and _yseen[0][0] == cold.SYSTEM
      and _ygot == cold.given(_yasks, briefs.latest(_y1), True, "`df`: 3 rows", _yn.render_ancestry(_yr.id)) and _ysees.startswith(_ygot + "\n\nYOUR NOTE")
      and _ygot.startswith("EARLIER IN THIS THREAD") and "[run 1] Q: Does B beat A?" in _ygot and "\n\nDATA:\n`df`: 3 rows\n\nQUESTION:\n" in _ygot and "[always]" in _ygot and "the season" not in _ygot
      and {k: v for k, v in _y1["turns"][-1].items() if k != "secs"} == {"who": "reader", "missing": [], "v": 1, "cost": 0.002, "call": 1} and isinstance(_y1["turns"][-1]["secs"], float)
      and _yok1b is True and _y1b is _y1 and len(_yseen) == 1 and arch.conversation(_y1["turns"]) == "CONVERSATION:\n(nothing yet)", (_y1, _yok1, _yok1b, _ygot, _ysees[:len(_ygot) + 40]))
_zn = Notebook("z"); _zr = _zn.new_run(_cq); _zr.status = "framing"; _zr.framing = steps.take({**briefs.version({}, {"question": _cq, "expects": "It rises."}), "data": False, "calls": 2})
_zread, _zseen = _arch_llm(['{"cannot_place": ["the bar version of 14 May", "as before"]}', '{"cannot_place": ["bars"]}'], usage={"cost": 0.002})
_zarch, _zaseen = _arch_llm([json.dumps({"say": "I took out what pointed to earlier work.", "wording": "Draw the series as bars in one colour."})])
_z1, _zok1 = cold.ready(_zarch, _zread, _zn, _zr, data="`df`: 3 rows")
_z2, _zok2 = cold.ready(_zarch, _zread, _zn, _zr)
_zback, _zokb = cold.ready(_zarch, _zread, _zn, _zr, step=1)
_zsaw = _zaseen[0][1] if _zaseen else ""
check("cold.ready, a question that points outside what the analyst gets: the read is a turn with the phrases, and the Pathfinder goes on at once - one exchange with no message of the person's, whose "
      "CONVERSATION ends on what the reader could not place, and which is given what an exchange is given beside it, the data's description. Its wording is one more version; the analysis does "
      "not start; the reply is numbered among the Pathfinder's calls, the read among the reads. The read and the reply to it are one step of the conversation, which follows the one read. Both "
      "versions are listed as read: started again - the Pathfinder's version, or the step before it, which the person went back to - it starts, with no call. The reader was told the run "
      "has no data where it has none",
      _zok1 is False and len(_zseen) == 1 and len(_zaseen) == 1 and "\nWhat they expect to see: It rises." in _zseen[0][1] and "[always]" not in _zseen[0][1] and _zaseen[0][0] == arch.SYSTEM
      and _zsaw.startswith("DATA:\n`df`: 3 rows\n\n")
      and _zsaw.endswith('CONVERSATION:\nA reader given what the analyst will be given could not place: "the bar version of 14 May"; "as before"\n\nReply with the JSON object.')
      and [(v["n"], v["by"], v["changed"]) for v in _z1["versions"]] == [(1, "person", []), (2, "architect", ["question"])] and briefs.latest(_z1)["question"] == "Draw the series as bars in one colour."
      and _z1["read"] == [1, 2] and _z1["calls"] == 3 and [(t["who"], t["call"]) for t in _z1["turns"]] == [("reader", 1), ("architect", 3)]
      and _z1["turns"][0]["missing"] == ["the bar version of 14 May", "as before"] and _z1["turns"][0]["v"] == 1 and _z1["turns"][1]["wording"] == "Draw the series as bars in one colour."
      and _shape(_z1) == [(1, 0, 1, [1], 0), (2, 1, 2, [2], 2)] and (_z1["step"], _z1["tip"]) == (2, 2)
      and _zr.framing is _z1 and _zok2 is True and _z2 is _z1 and _zokb is True and _zback is _z1 and len(_zseen) == 1 and len(_zaseen) == 1, (_z1, _zok1, _zok2, _zokb, _zsaw[-300:]))
_zr.framing = briefs.version(_zr.framing, {**briefs.latest(_zr.framing), "question": "Draw the series as bars, as on 14 May."}, by="person", changed=["question"])
_zbad, _zbseen = _arch_llm(["no object", "none either"])
try:
    cold.ready(_zbad, _zread, _zn, _zr); _zfail = None
except arch.Failed as exc:
    _zfail = exc
_z3 = _zr.framing
_z4, _zok4 = cold.ready(_zbad, _zread, _zn, _zr)
check("cold.ready, a version made since - the person changed the question by hand - is read again. Where the Pathfinder's reply then fails, the failure is raised with its reason, which is for the "
      "person: the read stands as the conversation's last turn - the second of the reads -, the calls of the failed reply are counted among the Pathfinder's, no version is added. Started again, "
      "it starts - a read holds a start up once",
      isinstance(_zfail, arch.Failed) and str(_zfail).startswith("The Pathfinder's reply could not be read") and len(_zseen) == 2 and len(_zbseen) == 2 and _z3["read"] == [1, 2, 3]
      and _z3["turns"][-1]["who"] == "reader" and _z3["turns"][-1]["missing"] == ["bars"] and _z3["turns"][-1]["v"] == 3 and _z3["turns"][-1]["call"] == 2 and _z3["calls"] == 5
      and len(_z3["versions"]) == 3 and _zok4 is True and _z4 is _z3 and len(_zseen) == 2 and len(_zbseen) == 2, (_z3, _zfail, _zok4))
_vn = Notebook("v"); _vr = _vn.new_run("One, as before."); _vr.status = "framing"
_vr.framing = briefs.version(briefs.version({}, {"question": "One, as before."}), {"question": "Two."}, by="architect", changed=["question"])
_vread, _vseen = _arch_llm(['{"cannot_place": []}', '{"cannot_place": []}'])
_v1, _vok = cold.ready(None, _vread, _vn, _vr, step=1)
_v2, _vok2 = cold.ready(None, _vread, _vn, _vr, step=2)
check("cold.ready reads the question of the step on the person's screen - the one the analysis will run under - which need not be the last: step 1 is read, its version listed as read and in "
      "use from then, as the framing says; the read is a step that follows it, and the conversation gains nothing else. The other step, started later, is read in its turn: a step that "
      "follows that one, on a way that holds no other read - and still the second of the brief's reads, by which the run log finds its call",
      _vok is True and _vseen[0][1].startswith("QUESTION:\nOne, as before.") and "Two." not in _vseen[0][1] and _v1["read"] == [1] and _v1.get("at") == 1 and [t["who"] for t in _v1["turns"]] == ["reader"]
      and _v1["turns"][-1]["v"] == 1 and briefs.latest(_v1)["question"] == "One, as before."
      and _shape(_v1) == [(1, 0, 1, [1], 0), (2, 1, 2, [2], 0), (3, 1, 1, [], 1)] and (_v1["step"], _v1["tip"]) == (3, 3)
      and _vok2 is True and len(_vseen) == 2 and _vseen[1][1].startswith("QUESTION:\nTwo.") and _v2["read"] == [1, 2] and "at" not in _v2 and [(t["v"], t["call"]) for t in _v2["turns"]] == [(2, 2)]
      and _shape(_v2)[-1] == (4, 2, 2, [], 1) and [(t["v"], t["call"]) for t in steps.said(_v2)] == [(2, 2), (1, 1)], (_v1, _v2))
_wn = Notebook("w"); _wr = _wn.new_run("One, as before."); _wr.status = "framing"
_wr.framing = briefs.version(briefs.version({}, {"question": "One, as before."}), {"question": "Two."}, by="architect", changed=["question"])
_wread, _wseen = _arch_llm(['{"cannot_place": ["as before"]}'])
_warch, _waseen = _arch_llm([json.dumps({"say": "I said what was before.", "wording": "One, from the start."})])
_w1, _wok = cold.ready(_warch, _wread, _wn, _wr, step=1)
_wsaw = _waseen[0][1] if _waseen else ""
check("cold.ready, an earlier step whose question points outside what the analyst gets: the Pathfinder goes on from that step - it reads its question and its brief, and its CONVERSATION holds "
      "what the reader could not place, and no word that the person went back. The read and the reply are one step, which follows the one read; the reply's wording is a version counted on "
      "from the last; the later step stays; the version read and the Pathfinder's are listed as read, and the Pathfinder's is the one in use",
      _wok is False and [t["who"] for t in _w1["turns"]] == ["reader", "architect"] and _w1["turns"][0]["v"] == 1 and _shape(_w1) == [(1, 0, 1, [1], 0), (2, 1, 2, [2], 0), (3, 1, 3, [3], 2)]
      and _wsaw.startswith("QUESTION:\nOne, as before.\n") and "BRIEF (version 1):" in _wsaw
      and _wsaw.endswith('CONVERSATION:\nA reader given what the analyst will be given could not place: "as before"\n\nReply with the JSON object.')
      and [(v["n"], v["by"], v["brief"]["question"]) for v in _w1["versions"]] == [(1, "person", "One, as before."), (2, "architect", "Two."), (3, "architect", "One, from the start.")]
      and _w1["read"] == [1, 3] and "at" not in _w1 and _w1["turns"][1]["v"] == 3 and (_w1["step"], _w1["tip"]) == (3, 3), (_w1, _wok, _wsaw[-400:]))
_csaid = {"what it is given": "QUESTION, the BRIEF it comes with, DATA where data is loaded,\nand above them the earlier analyses it follows, where it follows any.",
          "it has nothing else": "You have nothing else: not the conversation\nthe question came out of, and no other earlier work.",
          "what to find": "Find what in QUESTION points to something you were not given: an earlier analysis, figure or version that is not\namong those above, whether it is named by "
                          "its day or as \"the last one\"; \"as before\" or \"the usual one\" where\nnothing you were given says which; something said or agreed somewhere else.",
          "not what the data settles": "A day, a name or a value that the\ndata can settle is no such pointer.",
          "not the task": "Do not carry out the task, and do not judge it.",
          "the object": '{"cannot_place": ["<words of QUESTION, copied exactly>"]}',
          "few and short": "Three at most, each the fewest words that hold the pointer.",
          "nothing to name": "An empty list where QUESTION can be worked from what\nyou were given."}
_ctexts = {"the cold reader's instructions": cold.SYSTEM, **{f"analyst/cold.py string {k}": t for k, t in enumerate(_authored_strings("analyst/cold.py"))}}
_said13 = {"what and on what, to the analyst": "give the whole question under `wording`: what is to be done\n  and on what, in two or three sentences addressed to the analyst.",
           "what the analyst is given": "The analyst is given QUESTION, BRIEF, the data and the analyses under EARLIER, and nothing else: not this\n  conversation, and of the saved analyses only "
                                        "those the brief builds on.",
           "nothing outside it": "Point to nothing it is not given: what\n  the question needs from there, say in the wording itself.",
           "the look is the figure's": "How a figure is to look belongs in its description under `figures`, not in the wording.",
           "afresh": "word the whole question afresh from what now stands. Say what is\n  wanted, not what was dropped on the way.",
           "the cold read": "Before the analysis starts, a reader is given what the analyst will be given, and nothing else. What that reader\n  could not place comes back in CONVERSATION: "
                            "word the question again so that it stands without it, and say in a\n  sentence what you changed."}
check("the instructions, 0313 (the product owner's live run: a question that pointed to an analysis of another day, carried how the figure looks, kept a correction as a 'no' and spoke of the "
      "analyst): the Pathfinder words what is to be done and on what, in two or three sentences addressed to the analyst; is told what the analyst is given - the question, the brief, the data, the "
      "analyses the question follows, and of the saved analyses those the brief builds on - points to nothing else, and says in the wording what the question needs from there; leaves how a "
      "figure looks to the figure's description; words the question afresh, as what is wanted; and words it again where a reader could not place something. Nothing is left of 'shown how', nor "
      "of the wording given 'again, as changed'. The cold reader has its own short instructions: what it is given, what to find - and that what the data can settle is no pointer -, the object to "
      "reply with - the key the engine reads. The "
      "standing rules hold for both: none of the tested tasks' vocabulary, no section named for thinking or reasoning",
      not [k for k, s in _said13.items() if s not in arch.SYSTEM] and "shown how" not in arch.SYSTEM and "again, as changed" not in arch.SYSTEM and "does not reach the analyst" not in arch.SYSTEM
      and not [k for k, s in _csaid.items() if s not in cold.SYSTEM] and '"cannot_place"' in cold.SYSTEM and len(cold.SYSTEM) < 1000 and len(arch.SYSTEM) < 17000
      and not {n: sorted({m.group(0) for m in _DOMAIN.finditer(t)}) for n, t in _ctexts.items() if _DOMAIN.search(t)}
      and not _re_c.search(r"(?i)\b(thinking|reasoning|scratchpad|memory|private)\b", cold.SYSTEM),
      ([k for k, s in _said13.items() if s not in arch.SYSTEM], [k for k, s in _csaid.items() if s not in cold.SYSTEM],
       {n: sorted({m.group(0) for m in _DOMAIN.finditer(t)}) for n, t in _ctexts.items() if _DOMAIN.search(t)}, len(cold.SYSTEM), len(arch.SYSTEM)))
# ---- 0307: a part of an analysis the question follows is opened on request - its report, a cell, the conversation it was framed in - and read whole by the replies that follow, until the person speaks
_on = Notebook("o")
_o1 = _on.new_run("Does B beat A?"); _o1.status = "answered"; _o1.report = "# B beats A\n\nB beats A by 3 units.\n\n## How\nSee [cell 2]."
_o1.turns = [Turn(kind="cell", code="import numpy as np\ngap = b - a\n", stdout="RESULT: gap = 3\nthe rest\n", cell_no=1, results=[{"text": "gap = 3"}], thinking="It loaded. Take the gap."),
             Turn(kind="cell", code="1/0", error="Traceback\nZeroDivisionError: division by zero"),                      # an attempt that failed: no number, no line
             Turn(kind="cell", code="fig = draw(gap)", stdout="", cell_no=2, step="figures", figures=[{"plotly": True, "title": "The gap  by month"}, {"plotly": True, "title": "Both arms"}]),
             Turn(kind="cell", code="broken()", error="Traceback (most recent call last):\nNameError: name 'broken' is not defined\n", cell_no=3)]
_o1.framing = _sf
_o2 = _on.new_run("And by month?", _o1.id); _o2.status = "answered"; _o2.report = "By month it holds."
_o2.turns = [Turn(kind="cell", code="m = by_month(gap)", stdout="twelve rows", cell_no=4), Turn(kind="cell", code="plot(m)", stdout="", cell_no=5, figures=[{"path": "a.png"}])]
_o3 = _on.new_run("Make the figure cleaner", _o2.id); _o3.status = "framing"; _o3.framing = briefs.version({}, {"question": _o3.question})
_oe = arch.earlier(_on, _o3.id, cells=True)
check("architect.earlier, for the Pathfinder: under each analysis what it has to open - its report, the conversation it was framed in - and of the last one a line to each cell: its number, what it was for, "
      "what came out, and what it drew - the figures by their titles where they have one, else how many. For another reader of the block none of it is there",
      _oe == ("EARLIER (the analyses this question follows, oldest first):\n[1] Q: Does B beat A?\n    Found: B beats A by 3 units.\n    To open: its report, its conversation\n"
              "[2] Q: And by month?\n    Found: By month it holds.\n    To open: its report, its cells:\n    [cell 4] m = by_month(gap)  ->  twelve rows\n    [cell 5] plot(m)  ->   (drew 1 figure)")
      and arch.earlier(_on, _o3.id) == _oe.replace("    To open: its report, its conversation\n", "").split("\n    To open: its report, its cells:")[0]
      and arch.earlier(_on, _o2.id, cells=True).endswith("    To open: its report, its conversation, its cells:\n    [cell 1] Take the gap.  ->  RESULT: gap = 3\n"
                                                         "    [cell 2] fig = draw(gap)  ->   (drew: The gap by month; Both arms)\n    [cell 3] broken()  ->  ERROR: NameError: name 'broken' is not defined")
      and arch._drew(Turn(kind="cell")) == "" and arch._drew(Turn(kind="cell", figures=[{"path": "a"}, {"path": "b"}])) == " (drew 2 figures)", _oe)
_long = "".join(f"line {k}\n" for k in range(4000))
check("architect._part: what a reply may open, by what the person reads it as - the report of the last analysis, or of another by its number; the conversation one was framed in; a cell by its number "
      "along them, with its code, what it printed or the error it ended on, and what it drew. What is not there is said in words: a cell no analysis has, an analysis the block does not list, a part "
      "of no such kind, a report or a conversation an analysis does not have, a question that follows nothing. A part longer than sixteen thousand characters loses its middle, and says how much",
      arch._part(_on, _o3.id, "report", None, None) == ("the report", "By month it holds.") and arch._part(_on, _o3.id, "report", 1, None) == ("the report of analysis 1", _o1.report)
      and arch._part(_on, _o3.id, "report", 2, None)[0] == "the report" and arch._part(_on, _o3.id, "conversation", 1, None) == ("the conversation of analysis 1", briefs.said(_sf, "Does B beat A?"))
      and arch._part(_on, _o3.id, "cell", None, 1) == ("cell 1", "```python\nimport numpy as np\ngap = b - a\n```\nOUTPUT:\nRESULT: gap = 3\nthe rest")
      and arch._part(_on, _o3.id, "cell", 2, 2) == ("cell 2", "```python\nfig = draw(gap)\n```\nOUTPUT:\n(no output)\n(drew: The gap by month; Both arms)")
      and arch._part(_on, _o3.id, "cell", None, 3) == ("cell 3", "```python\nbroken()\n```\nERROR:\nTraceback (most recent call last):\nNameError: name 'broken' is not defined")
      and [arch._part(_on, _o3.id, w, k, n) for w, k, n in (("cell", None, 9), ("cell", None, None), ("report", 5, None), ("report", 0, None), ("plot", None, None), (None, None, None), ("conversation", None, None))]
      == [("", "there is no cell 9: the cells are 1 to 5"), ("", "a cell is opened by its number: the cells are 1 to 5"), ("", "there is no analysis 5: EARLIER lists 2"), ("", "there is no analysis 0: EARLIER lists 2"),
          ("", "what can be opened is a report, a conversation or a cell"), ("", "what can be opened is a report, a conversation or a cell"), ("", "analysis 2 has no conversation")]
      and arch._part(_on, _o1.id, "report", None, None) == ("", "the question follows no analysis") and arch._part(_tn, _tr.id, "cell", None, 1) == ("", "the question follows no analysis")
      and arch._fit("short") == "short" and arch._fit("x" * arch.OPEN_CHARS) == "x" * arch.OPEN_CHARS == "x" * 16000
      and len(arch._fit(_long)) < 16100 and arch._fit(_long).startswith("line 0\nline 1\n") and arch._fit(_long).endswith("line 3999\n") and re.search(r"\n\.\.\. \(([\d,]+) characters left out here\) \.\.\.\n", arch._fit(_long)) is not None
      and int(re.search(r"\(([\d,]+) characters left out", arch._fit(_long)).group(1).replace(",", "")) == len(_long) - len(arch._fit(_long).split("\n... (")[0]) - len(arch._fit(_long).split(") ...\n")[1]),
      [arch._part(_on, _o3.id, w, k, n) for w, k, n in (("cell", None, 9), ("report", 5, None), ("plot", None, None), ("conversation", None, None))])
_llm9, _seen9 = _arch_llm([json.dumps({"say": "I am opening the cell that drew it.", "open": {"what": "cell", "n": "5"}, "brief": {"decision": "a cleaner figure"}}),
                           json.dumps({"say": "And the report.", "open": {"what": "report"}}), json.dumps({"say": "And what we said then.", "open": {"what": "conversation", "run": 1}}),
                           json.dumps({"say": "One more.", "open": {"what": "cell", "n": 4}}), json.dumps({"say": "It draws one line a month. Thinner lines, or fewer months?", "choices": ["Thinner lines", "Fewer months"]}),
                           json.dumps({"say": "Opening it.", "open": {"what": "cell", "n": 99}}), json.dumps({"say": "There is no such cell."})])
_oq = []
for _text in ("How was the figure drawn?", None, None, None, "Thinner lines", None):
    _o3.framing = arch.exchange(_llm9, _on, _o3, _text)
    _oq.append(_o3.framing)
_view5 = "--- cell 5 ---\n```python\nplot(m)\n```\nOUTPUT:\n(no output)\n(drew 1 figure)"
check("architect.exchange, opening (0307): a reply that asks to open a part gets a turn that names it - what it is, what the person reads it as, how long it is - and never its text; the next exchange, "
      "with nothing said, reads the part itself in a block of its own, after the conversation, as the record holds it. Three parts after one message of the person's: all three stay in view for the "
      "replies that follow; a fourth request is told at once and asked again. When the person has spoken the parts are gone from view - the conversation still says what was opened - and the count "
      "starts again. A part that is not there is a turn that says so. The Pathfinder's prompt names what there is to open",
      [t["who"] for t in _oq[0]["turns"]] == ["person", "architect", "opened"] and _oq[0]["turns"][-1] == {"who": "opened", "what": "cell", "n": 5, "label": "cell 5", "chars": len(_view5) - len("--- cell 5 ---\n")}
      and _oq[0]["versions"][1]["changed"] == ["decision"] and "\n\n" + _oe + "\n\nQUESTION:\nMake the figure cleaner" in "\n\n" + _seen9[0][1] and "OPENED" not in _seen9[0][1]
      and _seen9[1][1].endswith("CONVERSATION:\nPerson: How was the figure drawn?\nPathfinder: I am opening the cell that drew it.\nOpened: cell 5\n\nOPENED (in view until the person next speaks):\n" + _view5 + "\n\nReply with the JSON object.")
      and _oq[1]["turns"][-1] == {"who": "opened", "what": "report", "label": "the report", "chars": 18} and _oq[2]["turns"][-1] == {"who": "opened", "what": "conversation", "run": 1, "label": "the conversation of analysis 1", "chars": len(briefs.said(_sf, "x"))}
      and _seen9[3][1].endswith("Opened: cell 5\nPathfinder: And the report.\nOpened: the report\nPathfinder: And what we said then.\nOpened: the conversation of analysis 1\n\nOPENED (in view until the person next speaks):\n" + _view5
                                + "\n\n--- the report ---\nBy month it holds.\n\n--- the conversation of analysis 1 ---\n" + briefs.said(_sf, "x") + "\n\nReply with the JSON object.")
      and _seen9[4][1] == _seen9[3][1] + "\n\nYour last reply asked for what cannot be done now: opening - 3 parts were opened since the person last spoke, and that is the most. Nothing was started. "
                                         "Reply again without asking for it, and do not tell the person that it is under way."
      and [t["who"] for t in _oq[3]["turns"]][-2:] == ["opened", "architect"] and _oq[3]["turns"][-1]["text"].startswith("It draws one line a month.") and _oq[3]["turns"][-1]["call"] == _oq[3]["calls"] == 5 and arch.OPENS == 3
      and "OPENED" not in _seen9[5][1] and "Opened: cell 5\n" in _seen9[5][1] and _seen9[5][1].endswith("(choices offered: Thinner lines | Fewer months)\nPerson: Thinner lines\n\nReply with the JSON object.")
      and _oq[4]["turns"][-1] == {"who": "opened", "missing": "there is no cell 99: the cells are 1 to 5"} and "OPENED" not in _seen9[6][1]
      and _seen9[6][1].endswith("Pathfinder: Opening it.\nNot opened: there is no cell 99: the cells are 1 to 5\n\nReply with the JSON object.") and [t["who"] for t in _oq[5]["turns"]][-2:] == ["opened", "architect"]
      and arch.opened(_on, _o3.id, [{"who": "opened", "what": "cell", "n": 5, "label": "cell 5"}, {"who": "person", "text": "x"}]) == "" and arch.opened(_on, _o3.id, []) == ""
      and arch.opened(_on, _o3.id, [{"who": "opened", "what": "cell", "n": 77, "label": "cell 77"}]) == "OPENED (in view until the person next speaks):\n--- cell 77 ---\n(no longer on record)",
      ([t["who"] for t in _oq[-1]["turns"]], _oq[0]["turns"][-1], _seen9[1][1][-300:]))
def _twice(replies, **kw):
    n = Notebook("w"); r = n.new_run("q"); r.status = "framing"; r.framing = {**briefs.version({}, {"question": "q"}), "turns": [{"who": "memory", "found": []}]}
    llm, seen = _arch_llm(list(replies), kw.pop("usage", None))
    try:
        return arch.exchange(llm, n, r, None, recall=_recall_of(_RESULT), saved=3, **kw), len(seen)
    except arch.Failed as exc:
        return str(exc), exc.calls, round(exc.cost, 4), len(seen)
_tw = _twice([json.dumps({"say": "Looking.", "recall": True, "brief": {"decision": "from the first reply"}}), json.dumps({"say": "Here is what I found.", "brief": {"thinks": "from the second"}})])
check("architect.exchange, a request that cannot be met: the reply asked for again is the one taken in - its message, its parts of the brief - and nothing of the first; where it still asks, the request is "
      "not carried out and its message stands; where it cannot be read either, the exchange fails with every call counted, and nothing is kept",
      _tw[1] == 2 and _tw[0]["turns"][-1]["text"] == "Here is what I found." and briefs.latest(_tw[0]) == {"thinks": "from the second", "question": "q", "version": 2} and _tw[0]["calls"] == 2 and _tw[0]["turns"][-1]["cost"] == 0.008
      and [t["who"] for t in _twice([json.dumps({"say": "Looking.", "recall": True})] * 2)[0]["turns"]] == ["memory", "architect"]
      and _twice([json.dumps({"say": "Looking.", "recall": True}), "no", "still no"]) == ("The Pathfinder's reply could not be read (it holds no JSON object).", 3, 0.012, 3)
      and _twice([json.dumps({"say": "Looking.", "recall": True}), ""], usage={"cost": 0.01, "declined": "policy"}) == ("The model declined to reply (policy).", 1, 0.01, 1), _tw)
_o4 = _on.new_run("q4", _o2.id); _o4.status = "framing"; _o4.framing = {**briefs.version({}, {"question": "q4", "rests_on": ["a line"]}), "turns": [{"who": "opened", "what": "report", "label": "the report", "chars": 18}] * 3}
_ins = arch.exchange(_arch_llm([json.dumps({"say": "One more.", "open": {"what": "cell", "n": 4}})] * 2)[0], _on, _o4, None)
_o4.framing = {**briefs.version({}, {"question": "q4", "rests_on": ["a line"]}), "turns": [{"who": "check", "found": []}] * 2}
_looked4 = []
_ins2 = arch.exchange(_arch_llm([json.dumps({"say": "Once more.", "lookups": [{"about": "a line", "op": "count"}]})] * 2)[0], _on, _o4, None, look=lambda specs: _looked4.append(specs) or [])
_pn = Notebook("p2"); _p1 = _pn.new_run("Only a plain version"); _p1.status = "answered"; _p1.rewrite = _long; _p1.framing = {"turns": [{"who": "person", "text": "yes"}]}
_p2 = _pn.new_run("next", _p1.id)
_pt = arch._opened(_pn, _p2.id, {"what": "report", "run": "1"})
check("architect, opening, the edges: a reply that asks all the same after it was told is not served - no fourth part, no third round of lookups - and its message stands; a report kept only in plain "
      "words is the report; the conversation of a framing that kept no first version opens on the run's question; a long part is cut for the Pathfinder, and the turn says how much it reads, not how "
      "long the part is",
      [t["who"] for t in _ins["turns"]] == ["opened"] * 3 + ["architect"] and _ins["calls"] == 2 and [t["who"] for t in _ins2["turns"]] == ["check"] * 2 + ["architect"] and _ins2["calls"] == 2 and _looked4 == []
      and arch._part(_pn, _p2.id, "report", None, None) == ("the report", _long.strip()) and arch._part(_pn, _p2.id, "conversation", None, None) == ("the conversation", "Person: Only a plain version\nPerson: yes")
      and _pt == {"who": "opened", "what": "report", "run": 1, "label": "the report", "chars": len(arch._fit(_long.strip()))} and _pt["chars"] < len(_long) - 20000
      and arch.opened(_pn, _p2.id, [_pt]) == "OPENED (in view until the person next speaks):\n--- the report ---\n" + arch._fit(_long.strip()) and "characters left out here" in arch.opened(_pn, _p2.id, [_pt]),
      ([t["who"] for t in _ins["turns"]], [t["who"] for t in _ins2["turns"]], _pt))
del _asked_of[:]
_atexts = {"the Pathfinder's instructions": arch.SYSTEM}
_asys = " ".join(arch.SYSTEM.split())             # the instructions on one line: a sentence is found wherever its lines break
for _path in ("analyst/architect.py", "analyst/lookup.py"):
    for _k, _t in enumerate(_authored_strings(_path)):
        _atexts[f"{_path} string {_k}"] = _t
check("the Pathfinder's instructions: who it is - a patient tutor, who gives before it asks, keeps no order, never asks again what the person could not answer and never hurries them - every part of the "
      "brief under the name its reply uses, the question it words and does not write, the reply's form, the three things a lookup does, the three marks and what a proposal holds; and the standing rules hold for its texts - "
      "none of the tested tasks' vocabulary, no section named for thinking or reasoning - in the instructions and in every string of analyst/architect.py and analyst/lookup.py, whose words reach it",
      arch.SYSTEM.startswith("You are the Pathfinder.") and "`question`" not in arch.SYSTEM and all(f"`{k}`" in arch.SYSTEM for k in ("wording", "build", "open", "decision", "thinks", "rests_on", "expects", "would_change", "also_check", "fixed", "comparison", "measure", "period", "brief", "drop", "say", "choices",
                                                                                                  "lookups", "marks", "count", "list", "total", "where", "by", "data", "holds", "does not hold", "cannot be checked", "propose"))
      and '{"text": "<the explanation, one line>", "shows": "<what the analysis would find if it were so>", "column": "<the column of DATA that tells>"}' in arch.SYSTEM and "two lines at most" in arch.SYSTEM
      and all(f'"{op}"' in arch.SYSTEM for op in lookup.OPS + lookup.EVERY + briefs.MARKS) and "six at most" in arch.SYSTEM and lookup.MAX_LOOKUPS == 6 and "forty groups at most" in arch.SYSTEM and lookup.MAX_GROUPS == 40
      and "One JSON object and nothing else" in arch.SYSTEM and len(arch.SYSTEM) < 17000 and all(f"`{k}`" in arch.SYSTEM for k in ("builds_on", '"recall": true', '"build": [2]', '"build": []'))
      and not any(f"`{k}`" in arch.SYSTEM for k in ("accept", "tick", "saved"))
      and "When EARLIER is given, do not" not in _asys and "an earlier result is a claim for the analysis to test" in _asys
      and all(x in _asys for x in ("You talk with them as a patient tutor would", "Give before you ask.", '"I do not know" and "I am not sure" are answers: never ask that again', "Keep no order.",
                                   "Never hurry the person.", "you do not say what the person's data will show",
                                   "as your message say only that you are having a look", "build on it, or go another way", "Where nothing was found, say so in a few words and go on.",
                                   "A new line is written as \\n."))
      and not {n: sorted({m.group(0) for m in _DOMAIN.finditer(t)}) for n, t in _atexts.items() if _DOMAIN.search(t)}
      and not _re_c.search(r"(?i)\b(thinking|reasoning|scratchpad|memory|private)\b", arch.SYSTEM),
      ({n: sorted({m.group(0) for m in _DOMAIN.finditer(t)}) for n, t in _atexts.items() if _DOMAIN.search(t)}, len(arch.SYSTEM)))
_said08 = {"a short message": "One step a message, and a short one: a few plain sentences, about a hundred words, and at most one question",
           "starting is not a choice": "Starting the analysis is the person's own button: never offer it as a choice.",
           "the question is its to word": "QUESTION is what the analyst will be asked. It starts as the person's own words, and you word it for them: what you give under `wording` is the question from that reply on.",
           "the person sees it change": "The person sees it change, and can change it by hand.",
           "the message says what the question now holds": "In your message say in a sentence what the question now holds, and ask whether it is what they mean.",
           "what a reading found, as it reads it": "the analyses found, each under a number, with its day, what was asked then and its passages",
           "what it receives of the conversation": "what you opened, what came of each draft of the figures, and what a reader could not place.",
           "the whole question, not in the message": "give the whole question under `wording`", "not said twice": "Do not repeat the wording in the message: the person reads it beside the conversation.",
           "kept current": "Whenever what is to be done changes after that, word the whole question afresh from what now stands.",
           "worded again where it is not what they mean": "When the person says the question is not what they mean, word it again from what they say.",
           "an earlier point of the conversation": "The person can go back to an earlier point of this conversation and go on from there. QUESTION, BRIEF and CONVERSATION then show that point, and nothing after it.",
           "what they left behind": "Where they speak of something from this conversation that you cannot see - \"instead\", \"not that one\" - it is what they left behind: do not ask what it was, and go on from what they say now.",
           "the reply's form shows no key that belongs to one reply only": '{"say": "...", "choices": ["...", "..."], "brief": {"decision": "...", "rests_on": ["..."], "fixed": {"measure": "..."}, "drop": ["..."]}} - `say`: your message.',
           "the other keys, each in its reply": "`wording`, `lookups`, `marks`, `propose`, `recall`, `build`, `figures`, `open`: each only in the reply it belongs to, as set out above. Leave them out of every other reply.",
           "no claim the question does not bear out": "Say that the question holds something only where QUESTION shows it.",
           "lines as sentences": "Each line is a full sentence in the first person that reads on its own", "the task is not a part": "What is to be done is no part of the brief: it belongs in the wording.",
           "fixed, for data": "| `fixed` | only where the analysis compares data - ",
           "a reading on a follow-up, where it goes somewhere new": "Where the question only changes the analysis before it - EARLIER is given, and the subject is the same - ask for none.",
           "no reading claimed": "Say that you are having a look only in the reply that gives `recall`: at any other time no reading is under way, and you do not say that one is.",
           "told when none can be made": "Where SAVED says that no reading can be made now, ask for none.",
           "a choice to each analysis": "Where more than one analysis was found, name each in a choice of its own.",
           "build on it names the analyses": 'When they choose, give `build`: the numbers of all the analyses the brief builds on from then - `"build": [2]` - or `"build": []` where it is to build on none.',
           "builds only on what was chosen": "Build only on what the person chose.",
           "the person sees what was found": "The person sees what was found beside the conversation, and can look at each analysis there.",
           "what there is to open": '{"what": "report"} | {"what": "cell", "n": <the cell\'s number>} | {"what": "conversation"}', "one part a reply": "One part a reply, under `open`, and as your message say only what you are opening.",
           "in view until the person speaks": "It stays in view until the person next speaks: open it again when you need it again.",
           "no picture": "You are not shown the picture: where it matters, ask the person what they see in it.",
           "a follow-up starts from little": "The brief then starts with what the last answer was for and what the person thinks: keep what still holds for the new question, and change what does not."}
check("the Pathfinder's instructions, 0308: a short message; starting is the person's button and no choice; the question is the Pathfinder's to word - whole, under its own key, again whenever the task "
      "changes or the person says it is not what they mean - and is the question from that reply on, which the person sees and changes; where they went back to an earlier point of the "
      "conversation (0316) it is shown nothing that came after, and does not ask what was left behind - no word of versions is left; a line of the brief is a sentence of the person's, and the task is no part of it; a reading on a follow-up too, where it goes somewhere new, and never one claimed that is not "
      "made; the person chooses what to build on by answering, and the reply names every analysis built on by its number; a part of an earlier analysis is opened one at a time and stays in view "
      "until the person speaks; no picture is shown. Nothing of the wording that waited (0307) is left: no agreement to report, nothing to take, nothing to tick",
      not [k for k, s in _said08.items() if s not in _asys]
      and not any(x in _asys for x in ("`accept`", '"accept"', "the wording that waits", "not taken yet", "for the person to tick", "under `saved`", "another version", "earlier version")),
      [k for k, s in _said08.items() if s not in _asys])
_said10 = {"when it describes": "When the person asks for a figure, or asks to see what the result will look like, describe it: give `figures`, three at most.",
           "not otherwise": "Describe none where no figure is asked for.",
           "the title": "| `title` | the title the figure will carry, in a few words |",
           "the kinds": "| `kind` | `line`, `scatter`, `bar`, `histogram`, `box`, `heatmap` or `line3d` |",
           "the axes": "| `x`, `y` | what is on each axis; `z` too for `line3d`, and for `heatmap` what the colour shows |",
           "what it holds": '| `series` | the lines, the groups of points, the bars or the boxes it holds, four at most: `[{"name": "..."}]` |',
           "the note: short, the layout and the look, and no result": "| `note` | in a sentence or two: how it is laid out and is to look, where the person said, and what it is to make clear - never what will be found |",
           "a draft follows": "Right after your reply a draft of each figure is drawn from QUESTION and your description, and the person sees it in the brief.",
           "what a draft's numbers are": "A shape that follows from a rule alone is computed. One that only the data can give is drawn on made-up numbers, and marked so.",
           "it does not see the draft": "You do not see the draft: CONVERSATION says what came of it.",
           "every figure, one that stays by its number": '`figures` is every figure as it is to stand, in order. One that stays as it is: its number in BRIEF alone - `"figures": [1, {"title": "...", "kind": "line"}]`.',
           "all out": '`"figures": []` takes every figure out.',
           "the message": "In your message say that a draft is being drawn, and ask whether it is what they want to see. Say nothing of how the draft looks.",
           "another way": "When they want it another way, change the description, or the wording where the change is to what is computed: the draft is drawn again.",
           "drawn as its draft": "The analysis draws each figure after its report, under its title, as its draft drew it. What is to be computed for it belongs in the wording.",
           "what it receives": "`figures` lists the figures described, each under its number."}
check("the Pathfinder's instructions, 0310: it describes a figure when the person asks for one or asks to see the result, and not otherwise; a figure's keys - the kinds the engine knows, the bounds the "
      "engine keeps, the note for how a figure of several panels is laid out; a draft is drawn after its reply, computed where a rule gives the shape and on made-up numbers where only the data "
      "can, and the Pathfinder says so without describing a draft it has not seen; `figures` is every figure as it is to stand, one that stays by its number; a change is made to the description "
      "or the wording; nothing is left of the points a model wrote (0309), nor of the word for them",
      not [k for k, s in _said10.items() if s not in _asys] and all(f"`{k}`" in _said10["the kinds"] for k in briefs.KINDS) and briefs.MAX["figures"] == 3 and briefs.SERIES == 4
      and "`points`" not in arch.SYSTEM and "sketch" not in arch.SYSTEM.lower() and len(arch.SYSTEM) < 17000, ([k for k, s in _said10.items() if s not in _asys], len(arch.SYSTEM)))

# ---- lookups (0298, docs/ARCHITECT_DESIGN.md §2.4, §2.13): what the brief rests on is checked against the data - a count, a list or a
# total, and nothing else - and the lines are marked by what was found
import contextlib as _ctx, io as _io
_lc = lookup.clean
_kept, _kept_why = _lc({"about": " The B  units\nare more ", "op": "total", "column": " x ", "data": "datasets\\u/files/more.csv", "sql": "drop table",
                        "where": [{"column": "arm", "is": " B ", "extra": 1}, {"column": "x", "from": 1, "to": 2.5}], "by": {"column": "day", "every": "month", "x": 1}})
_long = _lc({"op": "list", "column": "c" * 300, "about": "a" * 700, "where": [{"column": "x", "is": "v" * 300}]})[0]
check("lookup.clean: a request is kept in its known shape and nothing else of it - the operation, the line it checks on one line, the column, a file by its name alone, each condition as a value or a range, "
      "the split by a column or over time; a count needs no column; a value may be text, a number or yes/no; names and values are bounded",
      _kept == {"op": "total", "about": "The B units are more", "column": "x", "data": "more.csv", "where": [{"column": "arm", "is": "B"}, {"column": "x", "from": 1, "to": 2.5}], "by": {"column": "day", "every": "month"}}
      and _kept_why == "" and _lc({"op": "count"}) == ({"op": "count"}, "") and _lc({"op": "count", "by": " arm "}) == ({"op": "count", "by": "arm"}, "") and _lc({"op": "list", "column": "arm", "about": " "}) == ({"op": "list", "column": "arm"}, "")
      and _lc({"op": "count", "where": [{"column": "ok", "is": True}, {"column": "x", "to": 3}, {"column": "x", "from": 0.5}]})[0]["where"] == [{"column": "ok", "is": True}, {"column": "x", "to": 3}, {"column": "x", "from": 0.5}]
      and (len(_long["column"]), len(_long["about"]), len(_long["where"][0]["is"])) == (lookup.NAME_CHARS, lookup.ABOUT_CHARS, lookup.NAME_CHARS) == (200, 600, 200), (_kept, _kept_why, _long))
_refused = [{"op": "mean", "column": "x"}, "count the rows", {"column": "x"}, {"op": "list"}, {"op": "total"}, {"op": "count", "where": [{"column": "x"}]}, {"op": "count", "where": [{"is": 1}]}, {"op": "count", "where": ["x is 1"]},
            {"op": "count", "where": [{"column": "x", "is": 1, "from": 0}]}, {"op": "count", "where": [{"column": "x", "is": [1, 2]}]}, {"op": "count", "where": [{"column": "x", "is": 1}] * 5},
            {"op": "count", "by": {"column": "day", "every": "day"}}, {"op": "count", "by": {"every": "week"}}, {"op": "count", "by": 3}, {"op": "count", "by": ""}, {"op": "list", "column": "x", "by": "arm"}]
check("lookup.clean: anything else is refused, in words - an operation that is not a count, a list or a total; a list or a total without its column; a condition without its column or its value, or with both a "
      "value and a range; more than four conditions; a split over time without a column of dates or by anything but week, month or year; a split that is not a column's name; a list with a split",
      [_lc(r) for r in _refused] == [(None, why) for why in
          ["a lookup is a count, a list or a total"] * 3 + ["a list names its column", "a total names its column", "a condition says what the column is, or the range it lies in", "a condition names its column",
           "a condition names its column", "a condition says what the column is, or the range it lies in", "a condition says what the column is, or the range it lies in", "a lookup takes 4 conditions at most",
           "a split over time names a column of dates and week, month or year", "a split over time names a column of dates and week, month or year", "a split names one column", "a split names one column", "a list has no split"]]
      and _lc({"op": "count", "where": [{"column": "x", "is": 1}] * 4})[1] == "", [_lc(r)[1] for r in _refused])
_lf = pd.DataFrame({"arm": ["A", "A", "B", "B", "B", "C"], "x": [1.0, 2.5, 3.0, None, 4.0, 10.0], "n": [1, 2, 2, 3, 3, 3], "day": ["2026-01-05", "2026-01-19", "2026-01-20", "2026-03-02", "2026-03-30", None],
                    "at": ["2026-01-05T08:00:00+11:00", "2026-01-19T23:30:00+11:00", "2026-01-20T06:00:00+10:00", "2026-03-02T07:00:00+10:00", "2026-03-31T07:00:00Z", "2026-03-31T00:30:00+10:00"],
                    "seen": ["05/01/2026", "19/01/2026", "20/01/2026", "02/03/2026", "30/03/2026", "31/03/2026"], "ok": [True, False, True, True, False, True],
                    "code": ["1998", "1998", "2004", "2004", "2004", "2011"]})
_lf["stamp"] = pd.to_datetime(_lf["day"])
_ldir = tempfile.mkdtemp()
pd.DataFrame({"who": ["ann", "bo", "ann"], "h": [1.5, 2, 4]}).to_csv(os.path.join(_ldir, "more.csv"), index=False)
_lfiles = {"more.csv": os.path.join(_ldir, "more.csv")}
def _look(requests, frame=_lf, files=None, seen=None):
    """A round of lookups, run as the executor runs a script: the program over `df`. Returns each lookup's line and whether it is a result."""
    specs = [lookup.clean(r)[0] for r in requests]
    out = _io.StringIO()
    src = lookup.script(specs, files)
    if seen is not None:
        seen.append(src)
    with _ctx.redirect_stdout(out):
        exec(src, {"df": frame})
    return [lookup.found(s, a) for s, a in zip(specs, lookup.read(out.getvalue(), len(specs)))]
_lines = lambda requests, **kw: [line for line, _ in _look(requests, **kw)]
_l1 = _look([{"op": "count"}, {"op": "count", "column": "x"}, {"op": "count", "by": "arm"}, {"op": "total", "column": "x"}, {"op": "total", "column": "x", "by": "arm"}, {"op": "total", "column": "x", "by": "n"},
             {"op": "total", "column": "ok"}, {"op": "total", "column": "h", "by": "who", "data": "more.csv"}, {"op": "count", "data": "more.csv"}, {"op": "count", "by": "x"}], files=_lfiles)
check("lookup, a count and a total: the rows, or the rows that have a value in a column; the sum of a column, an empty cell counting for nothing; split by a column, one number to a group, the groups in their "
      "own order and a whole number without its decimals; over the main table or over a file beside it, named. Each is one line that opens with what was asked",
      _l1 == [(line, True) for line in ["rows: 6", "rows with a value in x: 5", "rows by arm: A 2 · B 3 · C 1", "total of x: 20.5", "total of x by arm: A 3.5 · B 7 · C 10", "total of x by n: 1 1 · 2 5.5 · 3 14",
                                         "total of ok: 4", "total of h by who, in more.csv: ann 5.5 · bo 2", "rows, in more.csv: 3", "rows by x: 1 1 · 2.5 1 · 3 1 · 4 1 · 10 1"]], _l1)
_l2 = _lines([{"op": "list", "column": "arm"}, {"op": "list", "column": "x"}, {"op": "list", "column": "n"}, {"op": "list", "column": "day"}, {"op": "list", "column": "stamp"}, {"op": "list", "column": "at"},
              {"op": "list", "column": "seen"}, {"op": "list", "column": "ok"}, {"op": "list", "column": "arm", "where": [{"column": "n", "is": 1}]}, {"op": "list", "column": "x", "where": [{"column": "arm", "is": "c"}]},
              {"op": "list", "column": "arm", "where": [{"column": "n", "from": 9}]}, {"op": "list", "column": "who", "data": "more.csv"}, {"op": "list", "column": "code"}])
check("lookup, a list: how many different values a column has, and which - numbers and dates from the lowest to the highest, a date counted once however many moments of it there are, text by name with the "
      "most frequent first; one value alone is given as it is, and an empty selection says none. Text is read as dates only when written year first with its month: a day written 05/01/2026 stays text, and "
      "so does a code of four digits",
      _l2 == ["values of arm: 3 different: B, A, C", "values of x: 5 different, 1 to 10", "values of n: 3 different, 1 to 3", "values of day: 5 different, 2026-01-05 to 2026-03-30",
              "values of stamp: 5 different, 2026-01-05 to 2026-03-30", "values of at: 5 different, 2026-01-05 to 2026-03-31",
              "values of seen: 6 different: 02/03/2026, 05/01/2026, 19/01/2026, 20/01/2026, 30/03/2026, 31/03/2026", "values of ok: 2 different: True, False", "values of arm where n is 1: A",
              "values of x where arm is c: 10", "values of arm where n is from 9: none", "values of who, in more.csv: not looked up - there is no file more.csv",
              "values of code: 3 different: 2004, 1998, 2011"], _l2)
_l3 = _lines([{"op": "count", "where": [{"column": "arm", "is": " b "}]}, {"op": "count", "where": [{"column": "n", "is": "2"}]}, {"op": "count", "where": [{"column": "ok", "is": True}]},
              {"op": "count", "where": [{"column": "n", "from": 2, "to": 2}]}, {"op": "count", "where": [{"column": "x", "from": 2.5}]}, {"op": "count", "where": [{"column": "x", "to": 2.5}]},
              {"op": "count", "where": [{"column": "arm", "is": "B"}, {"column": "x", "from": 3.5}]}, {"op": "count", "where": [{"column": "day", "is": "2026-01-19"}]},
              {"op": "count", "where": [{"column": "day", "from": "2026-01-19", "to": "2026-03-02"}]}, {"op": "count", "where": [{"column": "stamp", "to": "2026-01-20"}]},
              {"op": "count", "where": [{"column": "at", "is": "2026-03-31"}]}, {"op": "count", "where": [{"column": "at", "is": "2026-01-20"}]}, {"op": "count", "where": [{"column": "at", "to": "2026-01-19"}]},
              {"op": "count", "where": [{"column": "at", "to": "2026-01-19 12:00"}]}, {"op": "count", "where": [{"column": "seen", "is": "19/01/2026"}]}, {"op": "count", "where": [{"column": "x", "is": "3"}]},
              {"op": "count", "where": [{"column": "x", "is": 2.5}]}])
check("lookup, the conditions: only the rows that meet every one - a value whatever its case and the spaces around it, a number given as text, yes/no, a range with either end or both, ends included; a day "
      "is that whole day, and up to a day is through that day; a time is read on the clock it was written in, whatever zone follows it",
      _l3 == ["rows where arm is b: 3", "rows where n is 2: 2", "rows where ok is True: 4", "rows where n is from 2 to 2: 2", "rows where x is from 2.5: 4", "rows where x is up to 2.5: 2",
              "rows where arm is B and x is from 3.5: 1", "rows where day is 2026-01-19: 1", "rows where day is from 2026-01-19 to 2026-03-02: 3", "rows where stamp is up to 2026-01-20: 3",
              "rows where at is 2026-03-31: 2", "rows where at is 2026-01-20: 1", "rows where at is up to 2026-01-19: 2", "rows where at is up to 2026-01-19 12:00: 1", "rows where seen is 19/01/2026: 1",
              "rows where x is 3: 1", "rows where x is 2.5: 1"], _l3)
_l4 = _lines([{"op": "total", "column": "x", "by": {"column": "day", "every": "month"}}, {"op": "count", "by": {"column": "at", "every": "month"}},
              {"op": "count", "by": {"column": "day", "every": "week"}, "where": [{"column": "day", "to": "2026-01-31"}]}, {"op": "count", "by": {"column": "stamp", "every": "year"}},
              {"op": "count", "by": {"column": "day", "every": "month"}, "where": [{"column": "n", "from": 9}]}, {"op": "count", "by": {"column": "day", "every": "month"}, "where": [{"column": "arm", "is": "C"}]},
              {"op": "count", "where": [{"column": "arm", "is": "C"}, {"column": "day", "from": "2026-01-01"}]}])
check("lookup, a split over time: one number to each week, month or year from the first to the last - a period with no rows shows as 0, so a gap is seen; a week is named by the day it starts, a Monday; "
      "a row without a date is in none, and a selection left without rows or without dates gives none",
      _l4 == ["total of x by month of day: 2026-01 6.5 · 2026-02 0 · 2026-03 4", "rows by month of at: 2026-01 3 · 2026-02 0 · 2026-03 3",
              "rows where day is up to 2026-01-31 by week of day: 2026-01-05 1 · 2026-01-12 0 · 2026-01-19 2", "rows by year of stamp: 2026 5", "rows where n is from 9 by month of day: none",
              "rows where arm is C by month of day: none", "rows where arm is C and day is from 2026-01-01: 0"], _l4)
_many = pd.DataFrame({"g": list(range(41)), "name": [f"group number {i:02d} of the long ones" for i in range(41)], "v": [1] * 41})
_l5 = _look([{"op": "total", "column": "arm"}, {"op": "total", "column": "stamp"}, {"op": "total", "column": "nothing"}, {"op": "count", "by": "nothing"}, {"op": "count", "where": [{"column": "nothing", "is": 1}]},
             {"op": "count", "by": {"column": "seen", "every": "month"}}, {"op": "count", "by": {"column": "x", "every": "month"}}, {"op": "count", "where": [{"column": "arm", "from": 1}]},
             {"op": "count", "where": [{"column": "n", "from": "a lot"}]}, {"op": "count", "where": [{"column": "day", "to": "soon"}]}, {"op": "count", "data": "other.csv"}], files=_lfiles)
_l6 = _look([{"op": "count", "by": "g"}, {"op": "count", "by": "g", "where": [{"column": "g", "to": 39}]}, {"op": "count", "by": "name", "where": [{"column": "g", "to": 39}]},
             {"op": "list", "column": "name"}, {"op": "count", "by": "name", "where": [{"column": "g", "to": 9}]}], frame=_many)
check("lookup, what the data refuses: a column or a file that is not there, with the ones that are; a total of text or of dates; a split over time on a column that holds no dates; a range on a column that "
      "holds neither numbers nor dates, or with an end that cannot be read. None of these is a result",
      _l5 == [(line, False) for line in
              ["total of arm: not looked up - arm does not hold numbers", "total of stamp: not looked up - stamp does not hold numbers",
               "total of nothing: not looked up - there is no column nothing: the columns are arm, x, n, day, at, seen, ok, code, stamp",
               "rows by nothing: not looked up - there is no column nothing: the columns are arm, x, n, day, at, seen, ok, code, stamp",
               "rows where nothing is 1: not looked up - there is no column nothing: the columns are arm, x, n, day, at, seen, ok, code, stamp",
               "rows by month of seen: not looked up - seen does not hold dates", "rows by month of x: not looked up - x does not hold dates",
               "rows where arm is from 1: not looked up - arm holds neither numbers nor dates", "rows where n is from a lot: not looked up - the range of n could not be read",
               "rows where day is up to soon: not looked up - the range of day could not be read", "rows, in other.csv: not looked up - there is no file other.csv: the files are more.csv"]], _l5)
check("lookup, a result that would not fit: a split into more than forty groups is refused, never cut - a list cut short would hide the group that matters - and so is a result longer than a line of the "
      "brief; a list of text names twelve values and says how many more there are",
      _l6[0] == ("rows by g: not looked up - the split gives 41 groups, more than 40: narrow it with a condition, or split it more coarsely", False)
      and _l6[1][1] is True and _l6[1][0].startswith("rows where g is up to 39 by g: 0 1 · 1 1 · ") and _l6[1][0].endswith(" · 39 1") and len(_l6[1][0]) <= lookup.FACT_CHARS
      and _l6[2] == ("rows where g is up to 39 by name: not looked up - the result is too long to show: narrow it with a condition, or split it more coarsely", False)
      and _l6[3] == ("values of name: 41 different: " + ", ".join(f"group number {i:02d} of the long ones" for i in range(12)) + ", and 29 more", True) and _l6[4][1] is True
      and lookup.FACT_CHARS <= briefs.TEXT_CHARS and lookup.MAX_VALUES == 12, _l6)
_odd = 'it\'s "odd"\n__import__("os").system("true") # é'
_odd_said = 'it\'s "odd" __import__("os").system("true") # é'
_of = pd.DataFrame({_odd: ["a", "a", "b"], "v": [1, 2, 3]})
_src = []
_l7 = _look([{"op": "count", "by": _odd, "about": "A LINE OF THE BRIEF"}, {"op": "total", "column": "v", "where": [{"column": _odd, "is": 'b"; raise SystemExit #'}]},
             {"op": "total", "column": "v", "where": [{"column": _odd, "is": "B"}]}], frame=_of, seen=_src)
_l8 = _look([{"op": "count"}], frame=None)
check("lookup, the program: names and values reach it as data inside one text, never as code - a column named with quotes, a line break and a call is a column like any other, and a value written as code "
      "matches nothing; what was found is one line whatever the names hold. The program is plain ASCII, does not carry the line of the brief, and changes nothing in the table it reads; with no table loaded "
      "it says so",
      _l7 == [(f"rows by {_odd_said}: a 2 · b 1", True), (f'total of v where {_odd_said} is b"; raise SystemExit #: 0', True), (f"total of v where {_odd_said} is B: 3", True)]
      and len(_src) == 1 and _src[0].isascii() and "A LINE OF THE BRIEF" not in _src[0] and list(_of.columns) == [_odd, "v"] and _of.shape == (3, 2)
      and _l8 == [("rows: not looked up - no main table is loaded", False)], (_l7, _l8))
_one = {"op": "count"}
check("lookup.read: the answers are the program's last marked line, one to a lookup; a line that is not there, does not parse or does not match the lookups asked refuses every one of them: the data could not be reached",
      lookup.read('noise\nLOOKUPS: [{"value": 1}]\nLOOKUPS: [{"value": 2}]\nmore noise', 1) == [{"value": 2}]
      and [lookup.read(out, 2) for out in ("", None, "LOOKUPS: [{", 'LOOKUPS: [{"value": 1}]', 'LOOKUPS: {"value": 1}', 'LOOKUPS: [1, 2]')] == [[{"refused": "the data could not be reached"}] * 2] * 6
      and lookup.found(_one, {"refused": "the data could not be reached"}) == ("rows: not looked up - the data could not be reached", False) and lookup.found(_one, None) == ("rows: not looked up - the data could not be reached", False)
      and lookup.found(_one, {"value": 1234567.891}) == ("rows: 1,234,567.89", True) and lookup.found({"op": "list", "column": "c"}, {"different": 2, "range": [1500, 20250.5]}) == ("values of c: 2 different, 1500 to 20250.5", True)
      and lookup.found(_lc({"op": "count", "by": "x\ny"})[0], {"refused": "there is no column x\ny"}) == ("rows by x y: not looked up - there is no column x y", False),
      lookup.read('LOOKUPS: [{"value": 2}]', 1))

# the marks
_mb = {"question": "q", "rests_on": [{"text": "B has the most.", "source": "person", "mark": ""}, {"text": "The arms are equal in size.", "source": "person", "mark": "holds", "note": "an old fact"},
                                      {"text": "B looked better.", "source": "person", "mark": ""}, {"text": "It was said.", "source": "person", "mark": ""}], "also_check": [{"text": "B has the most."}]}
_mfacts = {1: ("B has the most.", "total of x by arm: A 3 · B 2", True), 2: ("The arms are equal in size.", "rows by arm: A 2 · B 2", True), 3: ("B looked better.", "rows by look: not looked up - there is no column look", False),
           4: ("B has the most.", "rows: 6", True)}
_mb_before = json.dumps(_mb, sort_keys=True)
_m1, _mc1 = briefs.mark(_mb, [{"line": " B has  the most. ", "mark": "does not hold", "lookup": 1, "why": "the model's own words"}, {"line": "The arms are equal in size.", "mark": "holds", "lookup": 2},
                              {"line": "B looked better.", "mark": "cannot be checked", "lookup": 3}, {"line": "It was said.", "mark": "cannot be checked", "why": " nothing loaded\nrecords it "}], _mfacts)
check("brief.mark: a line the brief rests on is marked as the reply says, named word for word. 'holds' and 'does not hold' stand on a lookup made for that line that gave a result, and the fact beside the line "
      "is the lookup's own line, not the reply's words; a line said to be one that cannot be checked has the reason given beside it, on one line, and none where none was given. The lines that changed "
      "are named as the page names them; the source of a line and the rest of the brief stay, and the brief passed in is not altered",
      _m1["rests_on"] == [{"text": "B has the most.", "source": "person", "mark": "does not hold", "note": "total of x by arm: A 3 · B 2"}, {"text": "The arms are equal in size.", "source": "person", "mark": "holds", "note": "rows by arm: A 2 · B 2"},
                          {"text": "B looked better.", "source": "person", "mark": "cannot be checked"},
                          {"text": "It was said.", "source": "person", "mark": "cannot be checked", "note": "nothing loaded records it"}]
      and _mc1 == ["rests_on.0", "rests_on.1", "rests_on.2", "rests_on.3"] and _m1["also_check"] == [{"text": "B has the most."}] and _m1["question"] == "q" and json.dumps(_mb, sort_keys=True) == _mb_before, (_m1, _mc1))
_m2, _mc2 = briefs.mark(_mb, [{"line": "B has the most.", "mark": "holds", "lookup": 2}, {"line": "B looked better.", "mark": "does not hold"}, {"line": "It was said.", "mark": "holds", "lookup": 9, "why": "it is likely"},
                              {"line": "The arms are equal in size.", "mark": "cannot be checked", "lookup": 2}], _mfacts)
_m3, _mc3 = briefs.mark(_mb, [{"line": "not a line", "mark": "holds", "lookup": 1}, {"line": "B has the most.", "mark": "probably", "lookup": 1}, {"line": "B has the most."}, "B has the most.", None,
                              {"line": "The arms are equal in size.", "mark": "holds", "lookup": 2.0}, {"line": "It was said.", "mark": "holds", "lookup": True}, {"line": "B looked better.", "mark": "holds", "lookup": [1]},
                              {"line": "B has the most.", "mark": "does not hold", "lookup": 4}, {"line": "B has the most.", "mark": "does not hold", "lookup": 1}], _mfacts)
check("brief.mark: 'holds' and 'does not hold' never stand on anything else - a lookup made for another line, a lookup that gave no result, no lookup, one that was never made, one named by anything but "
      "its number: the mark is passed over, and the line stays as it was, checked or not. A line said to be one that cannot be checked loses the fact of the mark it had. A mark for a line that is not there "
      "and a mark that is not one of the three are passed over; of two marks for a line the later stands; a mark given again as it stands, and marks that are not a list, change nothing",
      _m2["rests_on"] == [{"text": "B has the most.", "source": "person", "mark": ""}, {"text": "The arms are equal in size.", "source": "person", "mark": "cannot be checked"},
                          {"text": "B looked better.", "source": "person", "mark": ""}, {"text": "It was said.", "source": "person", "mark": ""}]
      and _mc2 == ["rests_on.1"]
      and _m3["rests_on"] == [{"text": "B has the most.", "source": "person", "mark": "does not hold", "note": "total of x by arm: A 3 · B 2"}, {"text": "The arms are equal in size.", "source": "person", "mark": "holds", "note": "an old fact"},
                              {"text": "B looked better.", "source": "person", "mark": ""}, {"text": "It was said.", "source": "person", "mark": ""}]
      and _mc3 == ["rests_on.0"]
      and briefs.mark(_mb, [{"line": "The arms are equal in size.", "mark": "cannot be checked", "why": "the sizes were never recorded"}], _mfacts)[0]["rests_on"][1] == {"text": "The arms are equal in size.", "source": "person", "mark": "cannot be checked", "note": "the sizes were never recorded"}
      and briefs.mark(_mb, {"line": "B has the most.", "mark": "holds", "lookup": 1}, _mfacts) == (briefs.working(_mb), []) and briefs.mark(_mb, None, {})[1] == []
      and briefs.mark(_mb, [{"line": "B has the most.", "mark": "does not hold", "lookup": True}], _mfacts) == (briefs.working(_mb), [])
      and briefs.mark(_mb, [{"line": "B has the most.", "mark": "probably", "lookup": 1}], _mfacts) == (briefs.working(_mb), [])
      and briefs.mark(_mb, [{"line": "The arms are equal in size.", "mark": "cannot be checked"}], _mfacts)[0]["rests_on"][1] == {"text": "The arms are equal in size.", "source": "person", "mark": "cannot be checked"}
      and briefs.mark(_m1, [{"line": "B has the most.", "mark": "does not hold", "lookup": 1}, {"line": "It was said.", "mark": "cannot be checked", "why": " nothing loaded\nrecords it "}], _mfacts) == (_m1, [])
      and briefs.mark(_mb, [{"line": "B looked better.", "mark": "holds", "lookup": 3}], _mfacts) == (briefs.working(_mb), [])
      and briefs.mark(_mb, [{"line": "B looked better.", "mark": "cannot be checked", "lookup": 3, "why": ["not", "text"]}], _mfacts)[0]["rests_on"][2] == {"text": "B looked better.", "source": "person", "mark": "cannot be checked"}
      and briefs.mark({"question": "q"}, [{"line": "x", "mark": "holds", "lookup": 1}], _mfacts) == ({"question": "q"}, []), (_m2, _mc2, _m3, _mc3))

# the exchange with lookups: a reply asks, the host answers, the round joins the conversation, and the next reply marks the lines by it
_cn = Notebook("c"); _cr = _cn.new_run("Is B above A?"); _cr.status = "framing"
_most, _equal, _looked = "B has the most.", "The arms are equal in size.", "B looked better."
_cr.framing = briefs.version({}, {"question": _cr.question, "thinks": "B is better.", "rests_on": [_most, _equal]})
_cframe = pd.DataFrame({"arm": ["A", "A", "A", "B", "B", "B"], "x": [1.0, 2.0, 3.0, 1.0, 1.5, 2.0]})
_asked = []
def _clook(specs):
    _asked.append(specs)
    out = _io.StringIO()
    with _ctx.redirect_stdout(out):
        exec(lookup.script(specs), {"df": _cframe})
    return lookup.read(out.getvalue(), len(specs))
_llm5, _seen5 = _arch_llm([json.dumps({"brief": {"expects": "B well above A.", "rests_on": [_looked]}, "say": "Checking this against the data.",
                                       "lookups": [{"about": _most, "op": "total", "column": "x", "by": "arm"}, {"about": " The arms  are equal in size. ", "op": "count", "by": "arm"}, {"about": _looked, "op": "mean", "column": "x"},
                                                   {"about": "B well above A.", "op": "count"}, "count the rows", {"op": "count"}, {"about": _most, "op": "count"}]})])
_f5 = arch.exchange(_llm5, _cn, _cr, "B well above A.", data="`df`: 6 rows", look=_clook)
_check5 = _f5["turns"][-1]
check("architect.exchange, a reply that asks for lookups: its parts are written and its message joins the conversation as for any reply; then the round, as a turn of its own after it. Each request is a lookup "
      "about a line the brief rests on as the reply leaves it - or it is refused in words: not a count, a list or a total; not about such a line. The host is asked once, for the ones that stand, and what each "
      "found is one line under its number, with the line it was made for and whether it is a result; six lookups a round at most",
      [t["who"] for t in _f5["turns"]] == ["person", "architect", "check"] and _f5["turns"][1]["text"] == "Checking this against the data." and _f5["versions"][-1]["why"] == "answer"
      and _f5["versions"][-1]["changed"] == ["expects", "rests_on.2"] and _f5["turns"][1]["v"] == 2 and _f5["calls"] == 1 and set(_check5) == {"who", "found", "secs"} and _check5["secs"] >= 0
      and _asked == [[{"op": "total", "about": _most, "column": "x", "by": "arm"}, {"op": "count", "about": _equal, "by": "arm"}]]
      and _check5["found"] == [{"k": 1, "about": _most, "fact": "total of x by arm: A 6 · B 4.5", "ran": True}, {"k": 2, "about": _equal, "fact": "rows by arm: A 3 · B 3", "ran": True},
                               {"k": 3, "about": _looked, "fact": "not looked up - a lookup is a count, a list or a total", "ran": False},
                               {"k": 4, "about": "B well above A.", "fact": "rows: not looked up - a lookup names the line under rests_on it checks, copied exactly", "ran": False},
                               {"k": 5, "about": "", "fact": "not looked up - a lookup is a count, a list or a total", "ran": False},
                               {"k": 6, "about": "", "fact": "rows: not looked up - a lookup names the line under rests_on it checks, copied exactly", "ran": False}], (_f5["turns"], _asked))
# lookups and a reading of the saved analyses, in one exchange and one after the other
def _rlook(specs):
    out = _io.StringIO()
    with _ctx.redirect_stdout(out):
        exec(lookup.script(specs), {"df": _cframe})
    return lookup.read(out.getvalue(), len(specs))
_rn = Notebook("r"); _rr = _rn.new_run("Is B above A?"); _rr.status = "framing"; _rr.framing = briefs.version({}, {"question": _rr.question, "rests_on": [_most]})
_ask_look = {"say": "Checking.", "lookups": [{"about": _most, "op": "total", "column": "x", "by": "arm"}]}
_rr.framing = arch.exchange(_arch_llm([json.dumps(_ask_look)])[0], _rn, _rr, "Go on.", look=_rlook, recall=_recall_of(_RESULT))
_r1 = [t["who"] for t in _rr.framing["turns"]]
_rr.framing = arch.exchange(_arch_llm([json.dumps({"say": "It does not hold. I am looking in your saved analyses.", "marks": [{"line": _most, "mark": "does not hold", "lookup": 1}], "recall": True})])[0],
                            _rn, _rr, None, look=_rlook, recall=_recall_of(_RESULT))
_r2 = [t["who"] for t in _rr.framing["turns"]]
_bn = Notebook("b"); _br = _bn.new_run("Is B above A?"); _br.status = "framing"; _br.framing = briefs.version({}, {"question": _br.question, "rests_on": [_most]})
_both = arch.exchange(_arch_llm([json.dumps({**_ask_look, "recall": True})])[0], _bn, _br, "Go on.", look=_rlook, recall=_recall_of(_RESULT))
check("architect.exchange, lookups and a reading: a reply may ask for both, and the round of lookups stands before the reading; a reading asked for in the reply that follows a round, with nothing said "
      "since, is made too - a round of lookups is no reading - and what it found is kept beside the brief: the marks alone made a version",
      _r1 == ["person", "architect", "check"] and _r2 == ["person", "architect", "check", "architect", "memory"] and [t["who"] for t in _both["turns"]] == ["person", "architect", "check", "memory"]
      and _both["found"] == _KEPT and "saved" not in briefs.latest(_both) and briefs.latest(_rr.framing)["rests_on"][0]["mark"] == "does not hold" and _rr.framing["found"] == _KEPT
      and [(v["by"], v.get("why")) for v in _rr.framing["versions"][1:]] == [("architect", "check")], (_r1, _r2, [t["who"] for t in _both["turns"]]))
_cr.framing = _f5
_llm6, _seen6 = _arch_llm([json.dumps({"say": "One line does not hold: A has the most, 6 against 4.5. Do you keep what you think, or change it?", "choices": ["Keep it", "Change it"],
                                       "marks": [{"line": _most, "mark": "does not hold", "lookup": 1}, {"line": _equal, "mark": "holds", "lookup": 2}, {"line": _looked, "mark": "cannot be checked", "why": "nothing loaded records it"}]})])
_f6 = arch.exchange(_llm6, _cn, _cr, None, data="`df`: 6 rows", look=_clook)
_b6 = briefs.latest(_f6)
check("architect.exchange, after a round: with nothing said, the Pathfinder reads what the lookups found in the conversation - a numbered line to a lookup, under what was said before it - and the lines "
      "already checked with their marks; the marks its reply gives are one more version, made from a check against the data, and the brief the analyst will receive says what each line is worth",
      len(_seen6) == 1 and _seen6[0][1].endswith("CONVERSATION:\nPerson: B well above A.\nPathfinder: Checking this against the data.\nLookups:\n1. about \"B has the most.\" - total of x by arm: A 6 · B 4.5\n"
                                                 "2. about \"The arms are equal in size.\" - rows by arm: A 3 · B 3\n3. about \"B looked better.\" - not looked up - a lookup is a count, a list or a total\n"
                                                 "4. about \"B well above A.\" - rows: not looked up - a lookup names the line under rests_on it checks, copied exactly\n5. about \"\" - not looked up - a lookup is a count, a list or a total\n"
                                                 "6. about \"\" - rows: not looked up - a lookup names the line under rests_on it checks, copied exactly\n\nReply with the JSON object.")
      and [t["who"] for t in _f6["turns"]] == ["person", "architect", "check", "architect"] and _f6["turns"][-1]["choices"] == ["Keep it", "Change it"] and _f6["turns"][-1]["v"] == 3 and len(_asked) == 1
      and (_f6["versions"][-1]["by"], _f6["versions"][-1]["why"], _f6["versions"][-1]["changed"]) == ("architect", "check", ["rests_on.0", "rests_on.1", "rests_on.2"])
      and _b6["rests_on"] == [{"text": _most, "source": "person", "mark": "does not hold", "note": "total of x by arm: A 6 · B 4.5"}, {"text": _equal, "source": "person", "mark": "holds", "note": "rows by arm: A 3 · B 3"},
                              {"text": _looked, "source": "person", "mark": "cannot be checked", "note": "nothing loaded records it"}]
      and "- B has the most. [does not hold - total of x by arm: A 6 · B 4.5]\n- The arms are equal in size. [holds - rows by arm: A 3 · B 3]\n- B looked better. [cannot be checked - nothing loaded records it]" in arch.block(_b6)
      and "- B has the most. [checked against the data: does not hold - total of x by arm: A 6 · B 4.5]\n- The arms are equal in size. [checked against the data: holds - rows by arm: A 3 · B 3]\n"
          "- B looked better. [cannot be checked - nothing loaded records it]" in briefs.render(_b6), (_seen6[0][1][-900:], _f6["versions"][-1], _b6))
_cr.framing = _f6
_again = {"about": _looked, "op": "count"}
_llm7, _seen7 = _arch_llm([json.dumps({"say": "Looking once more.", "lookups": [_again]}), json.dumps({"say": "And once more.", "lookups": [_again]}), json.dumps({"say": "And again.", "lookups": [_again]}),
                           json.dumps({"say": "Ready.", "marks": [{"line": _looked, "mark": "holds", "lookup": 7}]}), json.dumps({"say": "Start when you are ready."}), json.dumps({"say": "Looking.", "lookups": [_again]}),
                           json.dumps({"brief": {"rests_on": ["A new line."]}, "say": "Ready.", "marks": [{"line": "A new line.", "mark": "cannot be checked", "why": "nothing loaded records it"},
                                                                                                                 {"line": _most, "mark": "holds", "lookup": 2}, {"line": _equal, "mark": "does not hold"}]})])
_rounds = []
for _text in ("Change it", None, None, None, "and now?"):
    _cr.framing = arch.exchange(_llm7, _cn, _cr, _text, look=_clook)
    _rounds.append([t["who"] for t in _cr.framing["turns"]][4:])
_k7 = [[f["k"] for f in t["found"]] for t in _cr.framing["turns"] if t["who"] == "check"]
_f8 = arch.exchange(_llm7, _cn, _cr, "one more thing", look=None)
_f9 = arch.exchange(_arch_llm([json.dumps({"say": "Checking.", "lookups": ["count", {"about": "nothing of the brief", "op": "count"}]})])[0], _cn, _cr, "check it", look=lambda specs: _asked.append("called") or [])
_f10 = arch.exchange(_arch_llm([json.dumps({"say": "Checking.", "lookups": [_again]})])[0], _cn, _cr, "check it", look=None)
check("architect.exchange, the bounds: after one message of the person's the data is looked up in two rounds at most - the second is for what the first refused - and a third request is not made, so the "
      "conversation never goes on by itself for long: the Pathfinder is told at once, in the same exchange, and the reply it then gives is the one kept (0307: a message that said a lookup was under way "
      "stood over nothing); the person's next message opens the count again. The lookups are numbered through the whole brief, so a mark names one of any round. A line the reply adds "
      "and marks is named once as changed; a mark that would stand on another line's lookup, or on none, is passed over. Without a host to look the request is dropped; a round in which no lookup stands does "
      "not reach the host",
      _rounds == [["person", "architect", "check"], ["person", "architect", "check", "architect", "check"], ["person", "architect", "check", "architect", "check", "architect"],
                  ["person", "architect", "check", "architect", "check", "architect", "architect"], ["person", "architect", "check", "architect", "check", "architect", "architect", "person", "architect", "check"]]
      and _k7 == [[1, 2, 3, 4, 5, 6], [7], [8], [9]] and len(_asked) == 4
      and _seen7[3][1] == _seen7[2][1] + "\n\nYour last reply asked for what cannot be done now: lookups - 2 rounds were made since the person last spoke, and that is the most. Nothing was started. "
                                         "Reply again without asking for it, and do not tell the person that it is under way."
      and "And again." not in [t.get("text") for t in _cr.framing["turns"]] and [t["text"] for t in _cr.framing["turns"] if t["who"] == "architect"][-3:-1] == ["Ready.", "Start when you are ready."]
      and briefs.latest(_cr.framing)["rests_on"][2] == {"text": _looked, "source": "person", "mark": "holds", "note": "rows: 6"}
      and [t["who"] for t in _f8["turns"]][-2:] == ["person", "architect"] and _f8["versions"][-1]["why"] == "check" and _f8["versions"][-1]["changed"] == ["rests_on.3"]
      and briefs.latest(_f8)["rests_on"][3] == {"text": "A new line.", "source": "person", "mark": "cannot be checked", "note": "nothing loaded records it"}
      and briefs.latest(_f8)["rests_on"][:3] == briefs.latest(_cr.framing)["rests_on"][:3] and [a["mark"] for a in briefs.latest(_f8)["rests_on"][:2]] == ["does not hold", "holds"]
      and [t["who"] for t in _f9["turns"]][-3:] == ["person", "architect", "check"] and [f["ran"] for f in _f9["turns"][-1]["found"]] == [False, False] and "called" not in _asked
      and [(t["who"], t.get("text")) for t in _f10["turns"]][-2:] == [("person", "check it"), ("architect", "Checking.")], (_rounds, _k7, _f8["versions"][-1], _f9["turns"][-1]))

# the planted cases (docs/ARCHITECT_DESIGN.md §4): a question with a false premise - a stage that was not the largest, a period the data does not cover, a tool that changed. Each passes when the brief shows the
# line as one that does not hold, with what was found, before any analysis starts. The lookups run in a kernel, as in the local edition
_pf = pd.DataFrame({"day": pd.date_range("2026-01-05", periods=84, freq="D").strftime("%Y-%m-%d"), "stage": ["first"] * 28 + ["second"] * 28 + ["third"] * 28,
                    "load": [5.0] * 28 + [4.0] * 28 + [4.5] * 28, "tool": ["old"] * 50 + ["new"] * 34})
_planted = [("Why did the result drop after the second stage, the largest of the three?", "The second stage was the largest of the three.", {"op": "total", "column": "load", "by": "stage"},
             "total of load by stage: first 140 · second 112 · third 126"),
            ("How did the result move over the whole of 2026?", "The data covers the whole of 2026.", {"op": "list", "column": "day"}, "values of day: 84 different, 2026-01-05 to 2026-03-29"),
            ("Did the result change, measured with one tool throughout?", "One tool was used throughout.", {"op": "list", "column": "tool"}, "values of tool: 2 different: old, new")]
_pk = PersistentKernel(df=_pf)
def _plook(specs):
    out, err, _ = _pk.execute(lookup.script(specs))
    return lookup.read(out, len(specs))
_cases = []
try:
    for _q, _premise, _ask, _fact in _planted:
        _pn = Notebook("p"); _pr = _pn.new_run(_q); _pr.status = "framing"; _pr.framing = briefs.version({}, {"question": _q})
        _pllm, _ = _arch_llm([json.dumps({"brief": {"rests_on": [_premise]}, "say": "Checking this against the data.", "lookups": [{"about": _premise, **_ask}]}),
                              json.dumps({"say": "One line does not hold. Do you keep what you think, or change it?", "choices": ["Keep it", "Change it"], "marks": [{"line": _premise, "mark": "does not hold", "lookup": 1}]})])
        _pr.framing = arch.exchange(_pllm, _pn, _pr, None, look=_plook)
        _pr.framing = arch.exchange(_pllm, _pn, _pr, None, look=_plook)
        _cases.append((_pr.status, briefs.latest(_pr.framing)["rests_on"], briefs.render(briefs.latest(_pr.framing))))
finally:
    _pk.cleanup()
check("the planted cases: a question with a false premise - a stage that was not the largest, a period the data does not cover, a tool that changed - ends, before any analysis, with the line marked as one "
      "that does not hold and the numbers the data gave beside it, in the brief the analyst will receive",
      [(status, lines) for status, lines, _ in _cases] == [("framing", [{"text": premise, "source": "person", "mark": "does not hold", "note": fact}]) for _, premise, _, fact in _planted]
      and all(f"- {premise} [checked against the data: does not hold - {fact}]" in block for (_, premise, _, fact), (_, _, block) in zip(_planted, _cases)), _cases)

# ---- other explanations (0299, docs/ARCHITECT_DESIGN.md §2.14): what the Pathfinder proposes enters the brief as its own, not accepted, and only what
# the person accepts reaches the analyst
_its = {"text": "The two arms differ in size", "shows": "the gap narrows with size held fixed", "source": "architect", "accepted": False}
_pb = {"question": "Is B above A?", "thinks": "B is better.", "also_check": [{"text": "the season"}, _its]}
_pn = briefs.normalise({**_pb, "also_check": [{"text": "the season", "accepted": True, "source": "person"}, {**_its, "accepted": "yes"}, {"text": "taken", "source": "architect", "accepted": True, "junk": 1}]})
check("brief.normalise: an explanation the Pathfinder proposed says so and whether the person accepted it - accepted only where that is said outright; one of the person's own carries neither word",
      _pn["also_check"] == [{"text": "the season"}, {**_its, "accepted": False}, {"text": "taken", "source": "architect", "accepted": True}], _pn["also_check"])
_taken = {**_its, "accepted": True}
_ag = briefs.agreed({**_pb, "also_check": [_its, _taken | {"text": "Another one."}]})
check("brief.agreed: the brief as the analyst receives it - in its known shape, without what the Pathfinder proposed and the person did not accept; what was accepted stays, and reads in the BRIEF block as "
      "any line with what it would show; a brief that holds nothing else is no brief; the brief passed in is not altered",
      _ag["also_check"] == [{**_taken, "text": "Another one."}] and _ag["thinks"] == "B is better." and briefs.agreed(_pb)["also_check"] == [{"text": "the season"}]
      and "Also check:\n- Another one: it would show the gap narrows with size held fixed\n- chance [always]" in briefs.render(_ag) and "The two arms differ in size" not in briefs.render(_ag)
      and briefs.agreed({"question": "q", "also_check": [_its]}) == {} and briefs.agreed(None) == {} and briefs.agreed({"question": "q", "also_check": "x"}) == {}
      and _pb["also_check"] == [{"text": "the season"}, _its], (_ag, briefs.render(_ag)[-300:]))
_pw, _pc = briefs.write({"question": "q", "also_check": [{"text": "the season"}]},
                        {"propose": [{"text": " The two arms  differ in size ", "shows": " the gap narrows\nwith size held fixed ", "column": "size"}, {"text": "a third"}], "also_check": ["the season"]})
_pw2, _pc2 = briefs.write({"question": "q"}, {"propose": ["Only words", {"shows": "no text"}, {"text": "Only words"}, {"text": "A second", "shows": 7}, {"text": "A third"}], "also_check": ["theirs"]})
_pw3, _pc3 = briefs.write({"question": "q", "also_check": [_taken]}, {"drop": ["The two arms differ in size"], "propose": [{"text": "Something else"}]})
check("brief.write, what the Pathfinder proposes: a line under propose joins the other explanations as the Pathfinder's own, with what it would show, not accepted, and is named as changed by its place; the "
      "list holds two lines in all, the person's included, and a line already there is not added again. A proposal can be taken out by name like any line; a reply never accepts one",
      _pw["also_check"] == [{"text": "the season"}, _its] and _pc == ["also_check.1"]
      and _pw2["also_check"] == [{"text": "theirs"}, {"text": "Only words", "source": "architect", "accepted": False}] and _pc2 == ["also_check.0", "also_check.1"]
      and _pw3["also_check"] == [{"text": "Something else", "source": "architect", "accepted": False}] and _pc3 == ["also_check", "also_check.0"]
      and briefs.write({"question": "q", "also_check": [_its]}, {"propose": [{**_its, "accepted": True}]})[1] == [] and briefs.write({"question": "q"}, {"propose": {"text": "x"}})[1] == [], (_pw, _pc, _pw2, _pc2, _pw3, _pc3))
check("architect.parse and block: what a reply proposes comes through as given, and a reply without it has none; in the BRIEF block a line the Pathfinder proposed says so, and whether the person accepted it",
      arch.parse(json.dumps({"say": "Ready.", "propose": [{"text": "x", "column": "c"}, "y"]}))["propose"] == [{"text": "x", "column": "c"}, "y"] and arch.parse('{"say": "x", "propose": {"text": "x"}}')["propose"] == []
      and "also_check:\n- the season\n- The two arms differ in size [proposed by you, not accepted]\n- Another one. [proposed by you, accepted]\nfixed.comparison"
          in arch.block({"question": "q", "also_check": [{"text": "the season"}, _its, {**_taken, "text": "Another one."}]}), arch.block(_pb))
_qn = Notebook("q"); _qr = _qn.new_run("Is B above A?"); _qr.status = "framing"; _qr.framing = briefs.version({}, {"question": _qr.question})
_qdata = "`df`: 6 rows\nsize: numeric(n=6)\nsize_class: categorical\nseason: categorical(n=6)"
_qllm, _qseen = _arch_llm([json.dumps({"say": "The brief is ready.", "brief": {"propose": [{"text": "Slipped in with the brief", "column": "size"}]},
                                       "propose": [{"text": "No column named"}, {"text": "A column the data lacks", "column": "weather"}, {"text": "Part of a name", "column": "class"}, "only words",
                                                   {"text": "The two arms differ in size", "shows": "the gap narrows with size held fixed", "column": " size "}]}),
                           json.dumps({"say": "Ready.", "propose": [{"text": "The seasons differ", "column": "season"}, {"text": "A third", "column": "size"}]}),
                           json.dumps({"say": "Ready.", "propose": [{"text": "A fourth", "column": "size"}]})])
_q1 = arch.exchange(_qllm, _qn, _qr, None, data=_qdata)
_qr.framing = _q1
_q2 = arch.exchange(_qllm, _qn, _qr, "go on", data=_qdata)
_qr.framing = {**_q2, "versions": _q2["versions"] + [{"n": 4, "by": "person", "changed": ["also_check"], "brief": {"question": _qr.question}}]}      # the person left both out
_q3 = arch.exchange(_qllm, _qn, _qr, "and now?", data=_qdata)
_q4 = arch.exchange(_arch_llm([json.dumps({"say": "Ready.", "propose": [{"text": "The two arms differ in size", "column": "size"}]})])[0], _xn, _xr, "anything else?", data="")
_q5 = arch.exchange(_arch_llm([json.dumps({"say": "Ready.", "brief": {"also_check": ["what the person named"]}})])[0], _xn, _xr, "also check what I named", data=_qdata)
check("architect.exchange, what a reply proposes: it enters the brief only where it names a column the data's description has, whole - not a word of the reply's own, not a part of a column's name - and never "
      "from inside the reply's brief; the version names the line. A brief takes two proposals in all: what the person left out is not proposed again and again; without a description of the data nothing is "
      "proposed, and a line the person named is not counted as one",
      briefs.latest(_q1)["also_check"] == [_its] and _q1["versions"][-1]["changed"] == ["also_check.0"] and _q1["versions"][-1]["why"] == "question" and _q1["proposed"] == 1
      and briefs.latest(_q2)["also_check"] == [_its, {"text": "The seasons differ", "source": "architect", "accepted": False}] and _q2["proposed"] == 2 and _q2["versions"][-1]["changed"] == ["also_check.1"]
      and len(_q3["versions"]) == 4 and "also_check" not in briefs.latest(_q3) and _q3["proposed"] == 2
      and "also_check" not in briefs.latest(_q4) and "proposed" not in _q4
      and briefs.latest(_q5)["also_check"] == [{"text": "what the person named"}] and "proposed" not in _q5, (briefs.latest(_q1), _q2.get("proposed"), briefs.latest(_q3), _q4.get("proposed"), _q5.get("proposed")))
# the analyst receives what was agreed
_sdf = pd.DataFrame({"part": ["a", "a", "b", "b"], "y": [1.0, 2.0, 3.0, 4.0]})
_snote = "- Question as understood: q\n- Best estimate so far: none yet\n- Held fixed: nothing yet\n- Open doubts: none\n- Plan: one cell, then report\n- Names: df"
_sact = lambda a: "###STEP###\ns.\n###NOTE###\n" + _snote + "\n###ACTION###\n" + a
_sseen = []
def _sllm(system, user, **h):
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    _sseen.append(user)
    return (_sact("REPORT\n# T\n\n## Answer\nDone [cell 1].\n\n## Against the brief\n- The seasons differ: no [cell 1].\n\n## Did not fit\nNothing.") if len(_sseen) > 1
            else _sact("```python\nprint(df.groupby('part')['y'].mean().to_dict())\n```")), {"cost": 0.001}
_sk = PersistentKernel(df=_sdf); _sn = Notebook("s")
try:
    _srun = Session(_sk, _sn, _sllm, data_description="4 rows: part, y", kernel_factory=lambda: PersistentKernel(df=_sdf)).run(
        "Is b above a?", budget=Budget(turns=6, dollars=1.0), brief={"question": "Is b above a?", "thinks": "b is above a.", "also_check": [_its, {"text": "The seasons differ.", "shows": "the same gap in each", "source": "architect", "accepted": True}]})
finally:
    _sk.cleanup()
check("a run under a brief with proposals: the analyst is given only what the person accepted - in its prompt, with what it would show, and on the run's own brief; the proposal left unticked is nowhere",
      _srun.status == "answered" and _srun.brief["also_check"] == [{"text": "The seasons differ.", "shows": "the same gap in each", "source": "architect", "accepted": True}]
      and "Also check:\n- The seasons differ: it would show the same gap in each\n- chance [always]" in _sseen[0] and all("The two arms differ in size" not in u for u in _sseen), (_srun.status, _srun.brief, _sseen[0][:600] if _sseen else None))
# SHOW SAVED k: the analyst opens a saved analysis its brief names (0304)
_wseen, _wasked = [], []
_WACTS = ["SHOW SAVED 1 2 3", "SHOW saved 2", "SHOW SAVED 3", "SHOW SAVED 4", "SHOW SAVED 0", "SHOW KEPT 1", "```python\nprint(df.groupby('part')['y'].mean().to_dict())\n```"]
_WREPORT = "REPORT\n# T\n\n## Answer\nDone [cell 1].\n\n## Against the brief\n- chance: no [cell 1].\n\n## Did not fit\nNothing."
def _wllm(system, user, **h):
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if system.startswith("You are drawing the figures"): return "NONE", {"cost": 0}
    _wseen.append(user)
    return _sact(_WACTS[len(_wseen) - 1] if len(_wseen) <= len(_WACTS) else _WREPORT), {"cost": 0.001}
def _wsaved(thread, run):
    _wasked.append((thread, run))
    return {"8": "QUESTION: Was B above A in spring?\nREPORT:\n# B led\n\nB led A by 3 units [cell 1].\nCELL 1, code:\ngap = b - a", "9": "TITLE: Two arms\nREPORT:\n# Two arms\n\nThe gap is b - a."}.get(run)
def _wonce(saved, brief):                                # a run that opens saved analysis 1 and reports: its show turn as recorded, and the prompt after it
    seen = []
    def llm(system, user, **h):
        if user.startswith("Rewrite"): return "plain", {"cost": 0}
        seen.append(user)
        return _sact("SHOW SAVED 1" if len(seen) == 1 else "REPORT\n# T\n\n## Answer\nNothing was computed.\n\n## Against the brief\n- chance: cannot tell.\n\n## Did not fit\nNothing."), {"cost": 0.001}
    run = Session(_wk, _wn, llm, data_description="4 rows: part, y", kernel_factory=lambda: PersistentKernel(df=_sdf), **({"saved": saved} if saved else {})).run(
        "Is b above a?", budget=Budget(turns=4, dollars=1.0), brief=brief)
    return [t.stdout for t in run.turns if t.kind == "show"][0], seen[1]
def _wreport(first, says):                           # the report of a run whose first action is `first` and whose report says `says`
    seen = []
    def llm(system, user, **h):
        if user.startswith("Rewrite"): return "plain", {"cost": 0}
        seen.append(user)
        return _sact(first if len(seen) == 1 else f"REPORT\n# T\n\n## Answer\nNothing was computed. {says}\n\n## Against the brief\n- chance: cannot tell.\n\n## Did not fit\nNothing."), {"cost": 0.001}
    return Session(_wk, _wn, llm, data_description="4 rows: part, y", kernel_factory=lambda: PersistentKernel(df=_sdf), saved=lambda t, r: "REPORT:\n# B led\n\nThe gap was 41.7 units.").run(
        "Is b above a?", budget=Budget(turns=4, dollars=1.0), brief=_wbrief).report
_wbrief = {"question": "Is b above a?", "thinks": "b is above a.", "saved": _wpass}
_wlong = lambda n: "FIRST LINE\n" + "x = 1  # a line of a cell\n" * (n // 25) + "LAST LINE"
_wk = PersistentKernel(df=_sdf); _wn = Notebook("w")
try:
    _wrun = Session(_wk, _wn, _wllm, data_description="4 rows: part, y", kernel_factory=lambda: PersistentKernel(df=_sdf), saved=_wsaved).run("Is b above a?", budget=Budget(turns=10, dollars=1.0), brief=_wbrief)
    _wnone = _wonce(None, _wbrief)                                                       # a host that opens none
    _wplain = _wonce(_wsaved, {"question": "Is b above a?", "thinks": "b is above a."})    # a brief that names none
    _w50 = _wonce(lambda t, r: _wlong(50_000), _wbrief)
    _w70 = _wonce(lambda t, r: _wlong(70_000), _wbrief)
    _wreps = [_wreport("SHOW SAVED 1", "The earlier analysis found a gap of 41.7 units."), _wreport("NAMES", "The earlier analysis found a gap of 41.7 units."),
              _wreport("SHOW SAVED 57", "The earlier analysis found a gap of 57 units.")]
finally:
    _wk.cleanup()
_wshow = [t.stdout for t in _wrun.turns if t.kind == "show"]
_WHEAD = '--- saved analysis 1: 2026-03-02 "Was B above A in spring?" (another person\'s data) ---\n'
check("SHOW SAVED k: the analyst opens the k-th saved analysis its brief names, as the host gives it - under a line that says which it is, and that it ran on another person's data where it did - one "
      "at a time: of several numbers the first is opened and the next is named. One that is saved no more, and a number the brief does not have, say so; another word after SHOW is told, with SAVED k among the forms. "
      "The view lives one turn, as a SHOW of cells does; the host is asked once for each. Where the host opens none the action says the same as for one saved no more; where the brief names none, SAVED "
      "is no form of SHOW",
      _wshow == [_WHEAD + "QUESTION: Was B above A in spring?\nREPORT:\n# B led\n\nB led A by 3 units [cell 1].\nCELL 1, code:\ngap = b - a\n(one saved analysis at a time: SHOW SAVED 2 opens the next)",
                 '--- saved analysis 2: 2026-04-02 "Synthesis: Two arms" ---\nTITLE: Two arms\nREPORT:\n# Two arms\n\nThe gap is b - a.', "(saved analysis 3 is no longer among the saved analyses)",
                 "(no saved analysis 4; the brief names 3)", "(no saved analysis 0; the brief names 3)",
                 "(SHOW did not understand 'KEPT 1'. SHOW takes cell numbers, or RUN k, SEARCH k, READ k - several numbers allowed - or SAVED k.)"]
      and _wasked == [("7", "8"), ("7", "9"), ("7", "10")] and "SHOWN:\n" + _WHEAD in _wseen[1] and "--- saved analysis 1:" not in _wseen[2] and _wrun.status == "answered"
      and _wnone[0] == "(saved analysis 1 is no longer among the saved analyses)"
      and _wplain[0] == "(SHOW did not understand 'SAVED 1'. SHOW takes cell numbers, or RUN k, SEARCH k, READ k - several numbers allowed.)",
      (_wshow, _wasked, _wseen[1][-600:], _wnone[0], _wplain[0]))
check("SHOW SAVED k and the report: a number that stands in a saved analysis the run opened is history the report may state - it is not held against it as one no cell printed; the same number in a "
      "run that opened none is, and so is a number that stands only in what SHOW said of an analysis it could not open",
      "were not printed by any cell" not in _wreps[0] and "> CHECK: 1 number(s) in this report were not printed by any cell (41.7). Treat them as unverified." in _wreps[1]
      and "> CHECK: 1 number(s) in this report were not printed by any cell (57). Treat them as unverified." in _wreps[2], [r[-200:] for r in _wreps])
from analyst.render import notebook_html as _wnbh
check("SHOW SAVED k in the notebook view: the step says a saved analysis was opened, with the line that says which; a SHOW that opened none keeps the label of a cell re-opened",
      _wnbh(_wrun).count('<span class="nb-out-label">Opened a saved analysis</span><span class="nb-out-peek">--- saved analysis 1: 2026-03-02 "Was B above A in spring?" (another person\'s data) ---</span>') == 1
      and _wnbh(_wrun).count('<span class="nb-out-label">Opened a saved analysis</span>') == 2 and _wnbh(_wrun).count('<span class="nb-out-label">Re-opened a cell</span>') == 4, re.findall(r'<span class="nb-out-label">.*?</span><span class="nb-out-peek">.*?</span>', _wnbh(_wrun)))
from analyst.session import SAVED_VIEW_CHARS as _WCAP
check("SHOW SAVED k: a saved analysis rides whole into the next prompt up to 60,000 characters - its report and the code of some twenty cells, more than a view of cells takes; of a longer one the "
      "middle goes, and the prompt says that part is not in view. The record keeps what the host gave",
      _WCAP == 60_000 and _WHEAD + _wlong(50_000) in _w50[1] and "omitted" not in _w50[1].split("SHOWN:\n")[1].split("\n\nTASK:")[0]
      and _w70[0] == _WHEAD + _wlong(70_000) and _WHEAD + "FIRST LINE\n" in _w70[1] and "LAST LINE\n\nTASK:" in _w70[1] and _wlong(70_000) not in _w70[1]
      and re.search(r"\n\.\.\. \[\d+ characters omitted from the middle for length; that part is not in view\] \.\.\.\n", _w70[1]) is not None
      and len(_w70[1].split("SHOWN:\n")[1].split("\n\nTASK:")[0]) <= _WCAP,
      (len(_w50[1]), len(_w70[1]), _w70[1].split("SHOWN:\n")[1][:200]))

# ---- next questions (0300, docs/ARCHITECT_DESIGN.md §2.7, §2.15): after a finished analysis, five questions at a level the person picks - each from
# a line the analysis left on record, the level's own lines first; kept with the run they follow
import time as _time_n
from analyst import next_questions as nq
_nn = Notebook("n")
_n0 = _nn.new_run("What is in the table?"); _n0.status = "answered"; _n0.report = "# T\n\n## Answer\nThe table has two arms of six rows each."
_nold = _nn.new_run("User requested variations of the enquiry (level 3)", parent=_n0.id); _nold.status = "answered"      # the retired ideas path's run, in a thread made before 2.8
_nold.report = "1. **One**: a question?"; _nold.turns = [Turn(kind="ideas", text=_nold.report)]
_nask = _nn.new_run("Is B above A, on protein?", parent=_nold.id); _nask.status = "asked"; _nask.turns = [Turn(kind="ask", text="No column records protein. Use y?")]
_n1 = _nn.new_run("Is B above A?", parent=_nask.id); _n1.status = "answered"
_nlast = {"question": _n1.question, "decision": "Keep B or A", "thinks": "B is better.",
          "rests_on": [{"text": "Both arms have six rows.", "mark": "holds", "note": "rows by arm: A 6 · B 6"}, {"text": "B was run later.", "mark": "does not hold", "note": "values of day: 2 different"},
                       {"text": "The scale was the same.", "mark": "cannot be checked", "note": "nothing loaded records it"}, "Nobody changed the feed."],
          "expects": "B is 0.3 above A.", "would_change": "A gap under 0.1.",
          "also_check": [{"text": "the season"}, {"text": "The two arms differ in size", "shows": "the gap narrows with size held fixed", "source": "architect", "accepted": True},
                         {"text": "Left unticked", "source": "architect", "accepted": False}],
          "fixed": {"measure": "y", "period": "the first half"}}
_n1.framing = briefs.version({}, _nlast)
_n1.brief = briefs.agreed(briefs.latest(_n1.framing))
_n1.report = ("# B is above A\n\n## Answer\nB is 0.4 above A [cell 1]. The gap holds in both halves.\n\n## Against the brief\n- Expected: met - 0.4 [cell 1]\n- Would change their mind: not seen\n"
              "- the season: the same gap in each [cell 2]\n- The two arms differ in size: cannot tell\n- chance: unlikely [cell 1]\n\n## Did not fit\n- The gap is twice as wide in the second half [cell 3]\n"
              "- Two rows have no day\n\n## How it was established\nA difference of means.")
_n1.brief_outcome = briefs.outcome(_n1.report)
_nk = lambda lines: [l["kind"] for l in lines]
_nrec = nq.record(_nn, _n1)
_nmisfit = {"kind": "misfit", "text": "The gap is twice as wide in the second half [cell 3]"}
_nopen = {"kind": "anchor", "text": "The scale was the same. (cannot be checked: nothing loaded records it)"}
check("next_questions.record: the lines an analysis leaves, each with its kind - what its brief fixed, what was also checked, what the Pathfinder proposed and the person left unticked, each line the brief rests "
      "on that was not found to hold with how it stands, what would change the person's mind with the report's verdict, what did not fit, what was asked and found, and what the analyses before it found - the "
      "newest first, an analysis that stopped on a question and a run of the retired ideas path not among them. A line that holds, and an explanation the person accepted, are not lines of their own; "
      "what was found is the report's opening sentences, never a heading, whether or not an empty line follows the heading",
      _nrec == [{"kind": "measure", "text": "y"}, {"kind": "period", "text": "the first half"}, {"kind": "check", "text": "the season: the same gap in each [cell 2]"},
                {"kind": "check", "text": "The two arms differ in size: cannot tell"}, {"kind": "check", "text": "chance: unlikely [cell 1]"}, {"kind": "proposal", "text": "Left unticked"},
                {"kind": "anchor", "text": "B was run later. (does not hold: values of day: 2 different)"}, _nopen, {"kind": "anchor", "text": "Nobody changed the feed. (not checked)"},
                {"kind": "would_change", "text": "A gap under 0.1. (not seen)"}, _nmisfit, {"kind": "misfit", "text": "Two rows have no day"},
                {"kind": "asked", "text": "Is B above A?"}, {"kind": "found", "text": "B is 0.4 above A [cell 1]. The gap holds in both halves."},
                {"kind": "earlier", "text": "The table has two arms of six rows each."}], _nrec)
_nbare = Notebook("b"); _nb0 = _nbare.new_run("  How many   rows?\n"); _nb0.status = "answered"; _nb0.report = "## Answer\nTwelve."
_nmany = Notebook("m"); _nprev = None
for _i in range(8):
    _nprev = _nmany.new_run(f"q{_i}", parent=_nprev.id if _nprev else None); _nprev.status = "answered"; _nprev.report = f"## Answer\nFinding {_i}."
_nprev.brief = {"would_change": "x " * 300}; _nprev.brief_outcome = {"checks": [f"c{_i}" for _i in range(9)], "did_not_fit": [f"m{_i}" for _i in range(9)]}
_nmr = nq.record(_nmany, _nprev)
check("next_questions.record: an analysis without a brief leaves what was asked and what was found, each on one line; a list of the record is read six lines deep and a line 400 characters long, so a long "
      "thread or a long report does not fill the prompt - the six analyses before, the newest first",
      nq.record(_nbare, _nb0) == [{"kind": "asked", "text": "How many rows?"}, {"kind": "found", "text": "Twelve."}]
      and [l["text"] for l in _nmr if l["kind"] == "check"] == [f"c{_i}" for _i in range(6)] and [l["text"] for l in _nmr if l["kind"] == "misfit"] == [f"m{_i}" for _i in range(6)]
      and [l["text"] for l in _nmr if l["kind"] == "earlier"] == [f"Finding {_i}." for _i in (6, 5, 4, 3, 2, 1)] and len(next(l["text"] for l in _nmr if l["kind"] == "would_change")) == 400, _nmr)
_nsrc = {level: nq.sources(_nn, _n1, level) for level in nq.LEVELS}
check("next_questions.sources: a level's own lines come first, as the record has them, and the others follow in the record's order; how many are the level's own is said. Refine focus reads what was fixed "
      "and the question, shift angle what was also checked and what was proposed and not tested, test boundaries what the brief rests on and what would change the person's mind, blend elements the "
      "findings of the thread, follow emergence what did not fit; without a brief only what the thread itself holds is a level's own",
      list(nq.LEVELS) == ["refine", "shift", "test", "blend", "emergence"] == list(nq.OWN)
      and {level: (_nk(lines[:own]), own) for level, (lines, own) in _nsrc.items()}
          == {"refine": (["measure", "period", "asked"], 3), "shift": (["check", "check", "check", "proposal"], 4), "test": (["anchor", "anchor", "anchor", "would_change"], 4),
              "blend": (["found", "earlier"], 2), "emergence": (["misfit", "misfit"], 2)}
      and all(lines[own:] == [l for l in _nrec if l["kind"] not in nq.OWN[level]] and len(lines) == len(_nrec) for level, (lines, own) in _nsrc.items())
      and _nsrc["emergence"][0][0] == _nmisfit and _nsrc["test"][0][1] == _nopen
      and {level: nq.sources(_nbare, _nb0, level)[1] for level in nq.LEVELS} == {"refine": 1, "shift": 0, "test": 0, "blend": 1, "emergence": 0}
      and all(kind in nq.SAID for kinds in nq.OWN.values() for kind in kinds) and set(_nk(_nrec)) <= set(nq.SAID), {level: (_nk(lines), own) for level, (lines, own) in _nsrc.items()})
_n1.next_questions = [{"level": "refine", "questions": [{"title": "t", "text": f"Asked before {_i}?", "from": []} for _i in range(20)], "cost": 0.0, "at": 0.0},
                      {"level": "shift", "questions": [{"title": "t", "text": f"Asked after {_i}?", "from": []} for _i in range(10)], "cost": 0.0, "at": 0.0}]
_nlines, _nown = _nsrc["emergence"]
_np = nq.prompt(_nn, _n1, "emergence", _nlines, _nown, data="`df`: 12 rows\narm: categorical\ny: numeric")
_npb = nq.prompt(_nbare, _nb0, "shift", *nq.sources(_nbare, _nb0, "shift"))
_npr = nq.prompt(_nbare, _nb0, "refine", *nq.sources(_nbare, _nb0, "refine"))
check("next_questions.prompt: what the model reads for a set, what does not change from level to level first - the data, the analyses before, the question, the report whole, the brief as the analyst "
      "received it - then the questions proposed for this analysis before, the newest twenty-five, the level with what a question at it does, and the lines numbered, the level's own first and the others "
      "under a heading of their own. A run without a brief, without earlier analyses or earlier sets has none of those blocks; where no line or every line is the level's own there is no second heading",
      _np.startswith("DATA:\n`df`: 12 rows\narm: categorical\ny: numeric\n\nEARLIER (the analyses this question follows, oldest first):\n[1] Q: What is in the table?\n")
      and "\n\nQUESTION:\nIs B above A?\n\nREPORT:\n" + _n1.report + "\n\n" + briefs.render(_n1.brief) + "\n\nPROPOSED BEFORE:\n- Asked before 5?\n" in _np
      and "- Asked before 4?" not in _np and "- Asked after 9?\n\nLEVEL: emergence - a question at this level follows what the analysis did not explain\n\nSOURCES:\n"
          "1. Did not fit: The gap is twice as wide in the second half [cell 3]\n2. Did not fit: Two rows have no day\nOther lines:\n3. Fixed, the measure: y\n4. Fixed, the period: the first half\n"
          "5. Also checked: the season: the same gap in each [cell 2]\n" in _np
      and _np.endswith("14. Found: B is 0.4 above A [cell 1]. The gap holds in both halves.\n15. Found earlier: The table has two arms of six rows each.\n\nReply with the JSON object.")
      and "Left unticked" not in briefs.render(_n1.brief) and "\n8. Proposed, not tested: Left unticked\n9. Rests on: B was run later. (does not hold: values of day: 2 different)\n" in _np
      and "\n12. Would change their mind: A gap under 0.1. (not seen)\n13. Asked: Is B above A?\n" in _np
      and _npb == "QUESTION:\nHow many   rows?\n\nREPORT:\n## Answer\nTwelve.\n\nLEVEL: shift - a question at this level puts another explanation of the same result to the test\n\nSOURCES:\n1. Asked: How many rows?\n2. Found: Twelve.\n\nReply with the JSON object."
      and "SOURCES:\n1. Asked: How many rows?\nOther lines:\n2. Found: Twelve.\n\n" in _npr and "Other lines:" not in nq.prompt(_nbare, _nb0, "refine", [{"kind": "asked", "text": "q"}], 1), (_np[-1500:], _npb))
_nnd = Notebook("nd"); _nd0 = _nnd.new_run("Draw it"); _nd0.status = "answered"; _nd0.report = "Drawn."; _nd0.brief = {"decision": "to see it", "version": 1}
_nd_data = nq.prompt(_nnd, _nd0, "shift", [], 0)
_nd0.data = {"source": "none", "aux": []}
check("next_questions.prompt, a run without data (0307): the brief is given as its analyst read it - what was agreed, without the checks a run on data makes",
      "\n\nBRIEF (agreed with the person before this run):\nWhat the answer is for: to see it\n\nLEVEL: shift" in nq.prompt(_nnd, _nd0, "shift", [], 0)
      and "\nWhat the answer is for: to see it\nAlso check:\n- chance [always]\n" in _nd_data, nq.prompt(_nnd, _nd0, "shift", [], 0))
_nj = lambda questions: json.dumps({"questions": questions})
_nq1 = nq.parse("Here:\n```json\n" + _nj([{"title": "  The  second half ", "question": " Is the gap wider\n in the second half? ", "from": [1]}, {"question": "From a bare number?", "from": 3},
                                            {"question": "No line named?"}, {"question": "A line that is not there?", "from": [16]}, {"question": "Not a number?", "from": ["1", 1.0, True, 0, -1]},
                                            {"title": "again", "question": "Is the gap wider in the second half?", "from": [2]}, {"title": "x", "from": [1]}, "only words",
                                            {"question": "Two lines, one given twice?", "from": [2, 2, 15, 4]}]) + "\n```", 15, 2)
def _nraises(reply, lines=15, own=2, pair=False):
    try:
        nq.parse(reply, lines, own, pair)
    except arch.Unreadable as exc:
        return str(exc)
check("next_questions.parse: a question with its title, its text on one line and the numbers of the lines it comes from - given as a list or as one number, each a whole number of a line that is there, "
      "named once, two at most. A question that names no such line is left out, as are one without a text and one given twice; a set holds five. A reply with no question that stands cannot be read, nor "
      "one whose questions all come from other lines where the level has lines of its own; where the level has none, any line will do; a reply that holds no JSON object is unreadable as the Pathfinder's is",
      _nq1 == [{"title": "The second half", "text": "Is the gap wider in the second half?", "from": [1]}, {"title": "", "text": "From a bare number?", "from": [3]},
               {"title": "", "text": "Two lines, one given twice?", "from": [2, 15]}]
      and len(nq.parse(_nj([{"question": f"q{_i}", "from": [1]} for _i in range(7)]), 3, 1)) == 5 == nq.QUESTIONS
      and [len(x) for q in nq.parse(_nj([{"title": "t" * 90, "question": "q" * 900, "from": [1]}]), 1, 1) for x in (q["title"], q["text"])] == [60, 600]
      and _nraises(_nj([{"question": "q", "from": [9]}, {"question": "", "from": [1]}]), 3, 1) == nq.NO_LINE == _nraises('{"questions": {"question": "q", "from": [1]}}') == _nraises("{}") == _nraises('{"questions": 5}')
      and _nraises(_nj([{"question": "q", "from": [3]}, {"question": "r", "from": [4, 5]}])) == nq.NOT_OWN and nq.parse(_nj([{"question": "q", "from": [3, 2]}]), 15, 2)[0]["from"] == [3, 2]
      and nq.parse(_nj([{"question": "q", "from": [2]}]), 2, 0) == [{"title": "", "text": "q", "from": [2]}] and _nraises("no object here") == "it holds no JSON object", (_nq1, _nraises("{}")))
check("next_questions.parse, where a question joins two lines: one that names a single line is left out, and a line named twice is one line",
      nq.parse(_nj([{"question": "one line", "from": [1]}, {"question": "the same twice", "from": [2, 2]}, {"question": "two lines", "from": [1, 3]}]), 3, 2, pair=True) == [{"title": "", "text": "two lines", "from": [1, 3]}]
      and _nraises(_nj([{"question": "one line", "from": [1]}]), 3, 2, pair=True) == nq.NO_LINE, None)
_n1.next_questions = []
_nfit = _nj([{"title": "The second half", "question": "Is the gap wider in the second half?", "from": [1]}, {"title": "The answer", "question": "Does the gap hold with the two rows left out?", "from": [14, 2]}])
_nllm, _nseen = _arch_llm([_nfit], {"cost": 0.0123456})
_nset = nq.propose(_nllm, _nn, _n1, "emergence", data="`df`: 12 rows")
_ntest = nq.propose(_arch_llm([_nj([{"question": "Was the same scale used for both arms?", "from": [2]}])])[0], _nn, _n1, "test")
check("next_questions.propose: one call - the instructions, the prompt for the level, the lowered effort - and the set as it is kept: its level, each question with the lines it comes from as the record "
      "has them, what the call cost, when. On a thread with a planted misfit and a line that could not be checked, the level that reads each returns a question from it; the run itself is not touched",
      len(_nseen) == 1 and _nseen[0][0] == nq.SYSTEM and _nseen[0][1] == nq.prompt(_nn, _n1, "emergence", _nlines, _nown, "`df`: 12 rows") and _nseen[0][2] == {"effort": nq.EFFORT} == {"effort": ("low", "medium")}
      and {k: v for k, v in _nset.items() if k != "at"} == {"level": "emergence", "cost": 0.0123, "questions": [
          {"title": "The second half", "text": "Is the gap wider in the second half?", "from": [_nmisfit]},
          {"title": "The answer", "text": "Does the gap hold with the two rows left out?", "from": [{"kind": "found", "text": "B is 0.4 above A [cell 1]. The gap holds in both halves."}, {"kind": "misfit", "text": "Two rows have no day"}]}]}
      and abs(_nset["at"] - _time_n.time()) < 60 and _ntest["level"] == "test" and _ntest["questions"] == [{"title": "", "text": "Was the same scale used for both arms?", "from": [_nopen]}]
      and _n1.next_questions == [], (_nset, _ntest))
_nllm2, _nseen2 = _arch_llm([_nj([{"question": "From another line?", "from": [5]}]), _nfit])
_nset2 = nq.propose(_nllm2, _nn, _n1, "emergence")
_nllm3, _nseen3 = _arch_llm(["no", "still no"])
_nllm4, _nseen4 = _arch_llm(["x"], {"cost": 0.002, "declined": "cyber"})
def _nfails(llm, level="emergence"):
    try:
        nq.propose(llm, _nn, _n1, level)
    except arch.Failed as exc:
        return str(exc), exc.calls, round(exc.cost, 4)
check("next_questions.propose, a reply that cannot be taken: where the level has lines of its own and no question comes from one, the reply is asked for once more, with what was wrong, and the second "
      "reply's cost is counted in; a reply unreadable twice, or one the model declined, fails in words for the person, with the calls it made; a blend that joins no two lines fails the same way",
      len(_nseen2) == 2 and _nseen2[1][1] == _nseen2[0][1] + "\n\n" + arch.AGAIN.format(problem=nq.NOT_OWN) and _nset2["cost"] == 0.008 and len(_nset2["questions"]) == 2
      and _nfails(_nllm3) == (arch.UNREAD.format(problem="it holds no JSON object"), 2, 0.008) and len(_nseen3) == 2
      and _nfails(_nllm4) == (arch.DECLINED.format(category="cyber"), 1, 0.002) and len(_nseen4) == 1
      and _nfails(_arch_llm([_nj([{"question": "One finding only?", "from": [1]}])] * 2)[0], "blend") == (arch.UNREAD.format(problem=nq.NO_LINE), 2, 0.008), (_nfails(_arch_llm(["no", "no"])[0]), _nset2))
_n1.next_questions = [_nset, _ntest]
_nran = [nq.ran(_n1, at, 77) for at in ((0, 1), [1, 0], (2, 0), (0, 2), (-1, 0), (0, -1), (True, 0), ("0", 0), (0,), None, 0)]
_nfile = Notebook.from_dict(json.loads(json.dumps(_nn.to_dict())))
_nolder = Notebook.from_dict({"thread_id": "o", "runs": {"1": {"id": "1", "parent": None, "question": "q"}}})
check("next_questions.ran: a question that was run is marked with the chain it started, by the place of its set and its own place in it; a place that is not there - past the end, before the start, not a "
      "whole number, not a pair - marks nothing. The sets are kept with the run in the thread's file, and a run from before has none",
      _nran == [True, True] + [False] * 9 and _n1.next_questions[0]["questions"][1]["ran"] == "77" and _n1.next_questions[1]["questions"][0]["ran"] == "77" and "ran" not in _n1.next_questions[0]["questions"][0]
      and _nfile.runs[_n1.id].next_questions == _n1.next_questions and _nolder.runs["1"].next_questions == [], (_nran, _nfile.runs[_n1.id].next_questions))
_ntexts = {"the instructions for next questions": nq.SYSTEM}
_nsys = " ".join(nq.SYSTEM.split())
for _k, _t in enumerate(_authored_strings("analyst/next_questions.py")):
    _ntexts[f"analyst/next_questions.py string {_k}"] = _t
check("the instructions for next questions: what the model does and does not, the reply's form, every block its prompt can hold named under what it receives, five questions asked for as a set holds five; "
      "and the standing rules hold for its texts - none of the tested tasks' vocabulary, no section named for thinking or reasoning - in the instructions and in every string of the module",
      _nsys.startswith("You propose the questions to analyse next.") and "You do not analyse, compute or answer." in _nsys and '{"questions": [{"title": "...", "question": "...", "from": [1]}]}' in _nsys
      and all(f"- {block}" in _nsys for block in ("DATA:", "EARLIER:", "QUESTION and REPORT:", "BRIEF:", "PROPOSED BEFORE:", "LEVEL:", "SOURCES:")) and "`Other lines`" in _nsys and "`blend`" in _nsys
      and "five questions" in _nsys and "One JSON object and nothing else" in _nsys and len(nq.SYSTEM) < 2500
      and not {n: sorted({m.group(0) for m in _DOMAIN.finditer(t)}) for n, t in _ntexts.items() if _DOMAIN.search(t)}
      and not _re_c.search(r"(?i)\b(thinking|reasoning|scratchpad|memory|private)\b", nq.SYSTEM),
      ({n: sorted({m.group(0) for m in _DOMAIN.finditer(t)}) for n, t in _ntexts.items() if _DOMAIN.search(t)}, len(nq.SYSTEM)))

# ---- a branch (0319, docs/BRANCH_DESIGN.md): go on from a turn of an analysis, another way, under a hint from the person.
# ---- The first run: a cell, a cell that fails, a cell, NAMES, a cell, the report - so a branch can go on after each kind.
from dataclasses import asdict as _asdict
from analyst import tools as _tools
from analyst.notebook import branch_points, hint_block, AGAIN_LINE
from analyst.session import CONTRACT_HINT, REVIEWER_HINT_ITEM

def _seat(system, user):
    return "rewrite" if user.startswith("Rewrite") else "figures" if system.startswith("You are drawing the figures") else "review" if system.startswith("You are the reviewer") else "analyst"

def _scripted(replies, seen, cost=0.01, review="###REVIEW###\n- The question requires: x\n- Established: nothing yet\n- Most consequential problem: none\n- Verdict: TEST check the second step"):
    """A model that plays `replies` on the analyst's seat, one a call, and keeps what each seat was sent."""
    left = list(replies)
    def llm(system, user, **hints):
        seat = _seat(system, user)
        seen.append((seat, system, user))
        if seat == "rewrite": return "plain", {"cost": 0}
        if seat == "figures": return "NONE", {"cost": 0}
        if seat == "review": return review, {"cost": cost}
        return left.pop(0), {"cost": cost}
    return llm

def _asked(seen, seat="analyst"):
    return [(s, u) for who, s, u in seen if who == seat]

_FIRST = [act6("CELL\n```python\nbase = 10\nprint('base', base)\n```"),
          act6("CELL\n```python\nraise ValueError('slip')\n```"),
          act6("CELL\n```python\npooled = base * 2\nprint('pooled', pooled)\n```"),
          act6("NAMES"),
          act6("CELL\n```python\nzz_after = pooled + 1\nprint('zz_after', zz_after)\n```"),
          act6("REPORT\n## The pooled figure\n\nThe pooled figure is 20 [cell 2].")]
_BUDGET = Budget(turns=8, dollars=1.0)
kb = PersistentKernel(df=df); nbb = Notebook("tb"); seen_a, ev_b = [], []
try:
    root_b = nbb.new_run("an earlier question"); root_b.status, root_b.report = "answered", "## Earlier\n\nDone."
    sb = Session(kb, nbb, _scripted(_FIRST, seen_a), data_description="d", emit=ev_b.append, kernel_factory=lambda: PersistentKernel(df=df))
    ra_ = sb.run("How do the two blocks compare?", parent=root_b.id, budget=_BUDGET, run_id="a", mode="Deep")
    work = [t for t in ra_.turns if t.kind not in ("rewrite", "review") and not t.step]
    check("branch: every working turn of a run keeps what the loop carried out of it - its number, what it handed to the next prompt, what was spent by then, "
          "the failed cells in a row; the report keeps none; the run keeps its limits; the turns to go on from are its working turns",
          [t.carry.get("turn") for t in work] == [1, 2, 3, 4, 5, None] and work[1].carry["extra"].startswith("YOUR LAST CELL FAILED") and work[1].carry["failures"] == 1
          and work[2].carry["failures"] == 0 and work[2].carry["extra"] == "" and work[3].carry["extra"].startswith("NAMES IN THE KERNEL:")
          and [round(t.carry["spent"], 2) for t in work[:5]] == [0.01, 0.02, 0.03, 0.04, 0.05] and ra_.budget == _asdict(_BUDGET) and branch_points(ra_) == [1, 2, 3, 4, 5]
          and ra_.branch == {} and ra_.hints == [] and not ra_.figure_asked, ([t.carry for t in work], ra_.budget))
    first_prompts = _asked(seen_a)
    # the invariant: going on without a hint, the loop is exactly where the first run was
    same = {}
    for k in (2, 3, 4):
        seen_k = []
        Session(kb, nbb, _scripted([act6("REPORT\n## r\n\nDone.")], seen_k), data_description="d").go_on("a", k, "", run_id=f"same{k}")
        same[k] = _asked(seen_k)[0] == first_prompts[k]
    check("branch: going on from a turn without a hint, the first prompt is the very prompt the first run had at the next turn - instructions and all - after a failed "
          "cell (its traceback), after a cell, after a NAMES view: the loop takes up exactly where the kept turn ended", same == {2: True, 3: True, 4: True}, same)
    # the branch: after turn 3 (a cell, the failed one, a cell), the kernel at the state the kept cells left
    seen_h, ev_h = [], []
    went = _tools.goto(kb, ra_.cells()[1].snap)
    sh = Session(kb, nbb, _scripted([act6("CELL\n```python\napart = pooled - base\nprint('apart', apart, 'zz_after' in globals())\n```"),
                                     act6("REPORT\n## Apart\n\nKept apart, the difference is 10 [cell 3].")], seen_h),
                 data_description="d", emit=ev_h.append, kernel_factory=lambda: PersistentKernel(df=df))
    rb_ = sh.go_on("a", 3, "  keep the two blocks apart  ", run_id="b1")
    hp = _asked(seen_h)
    _HINT = "HINT FROM THE PERSON (given after turn 3; it holds from there to the report):\nkeep the two blocks apart"
    check("branch: the hint stands in every prompt of the branch, above the task line, and the instructions gain its section; the first prompt is the first run's "
          "at that turn with the hint added; nothing of the turn that was left is in any of them; the figures step is given the hint too, after the question",
          len(hp) == 2 and all(_HINT + "\n\nTASK: turn " in u for _, u in hp) and all(s == contract(False, 0, hint=True) and "## A hint from the person" in s for s, _ in hp)
          and hp[0][1] == first_prompts[3][1].replace("\n\nTASK: turn 4;", "\n\n" + _HINT + "\n\nTASK: turn 4;") and not any("zz_after = " in u for _, u in hp)
          and contract(False, 0, hint=True).replace("\n" + CONTRACT_HINT, "", 1) == CONTRACT
          and _asked(seen_h, "figures")[0][1].startswith("QUESTION:\nHow do the two blocks compare?\n\n" + _HINT + "\n\nTHE REPORT, AS WRITTEN:\n")
          and not any("HINT FROM THE PERSON" in u for _, u in _asked(seen_a, "figures")), [u[-400:] for _, u in hp])
    check("branch: it is a chain of its own beside the one it left - the same parent, question, limits and mode - that records the chain, the turn and the hint; "
          "its kept turns are copies marked kept, its own follow with the next numbers, and its cell takes the next cell number",
          rb_.id == "b1" and rb_.parent == root_b.id and rb_.question == ra_.question and rb_.budget == ra_.budget and rb_.mode == "Deep" and rb_.branch == {"of": "a", "turn": 3}
          and rb_.hints == [{"turn": 3, "text": "keep the two blocks apart"}] and [t.kept for t in rb_.turns[:3]] == ["kept"] * 3 and not any(t.kept for t in rb_.turns[3:])
          and [t.carry.get("turn") for t in rb_.turns if t.kind not in ("rewrite",)] == [1, 2, 3, 4, None] and [c.cell_no for c in rb_.cells()] == [1, 2, 3]
          and rb_.cells()[2].code.startswith("apart") and rb_.turns[0] is not ra_.turns[0], (rb_.branch, rb_.hints, [t.kept for t in rb_.turns]))
    check("branch: the chain it left is as it was - its turns, its cells, none marked", len(ra_.turns) == len(work) + 1 and [c.cell_no for c in ra_.cells()] == [1, 2, 3]
          and not any(t.kept for t in ra_.turns) and ra_.cells()[2].code.startswith("zz_after") and ra_.status == "answered")
    check("branch: the kernel was at the state the kept turns left - the new cell finds what the kept cells made and nothing of the turn that was left - and the "
          "branch ends as any chain does: its report, its replay over the kept cells and its own, its code trace",
          went and rb_.cells()[2].stdout.strip() == "apart 10 False" and rb_.status == "answered" and rb_.replay_status == "reproduced"
          and all(f"# --- cell {n} ---" in rb_.replay_script for n in (1, 2, 3)) and "zz_after = " not in rb_.replay_script and "error" not in (rb_.code_map or {"error": 1}),
          (went, rb_.cells()[2].stdout, rb_.replay_status))
    starts = [(e.get("turn"), bool(e.get("kept"))) for e in ev_h if e["type"] == "turn_start" and isinstance(e.get("turn"), int)]
    kept_cells = [(e.get("cell_no"), e.get("kept"), bool(e.get("error"))) for e in ev_h if e["type"] == "cell"]
    beat = next(e for e in ev_h if e["type"] == "heartbeat")
    check("branch: the pane is sent the kept turns first, each marked kept - their cards, their cells, the failed one too - then what was spent by then, then the new turns",
          starts == [(1, True), (2, True), (3, True), (4, False), (5, False)] and kept_cells[:3] == [(1, "kept", False), (None, "kept", True), (2, "kept", False)]
          and kept_cells[3][:2] == (3, "") and (beat["turn"], round(beat["spent"], 2)) == (3, 0.03)
          and [e["type"] for e in ev_h[:3]] == ["turn_start", "turn_end", "cell"] and ev_h[1].get("kept") is True, (starts, kept_cells, beat))
    # a branch of a branch carries both hints where it goes on from a turn made under the first; from a turn the first branch kept, only its own
    seen_2, seen_3, seen_s = [], [], []
    rb2 = Session(kb, nbb, _scripted([act6("REPORT\n## r\n\nDone.")], seen_2), data_description="d").go_on("b1", 4, "and say which is larger", run_id="b2")
    rb3 = Session(kb, nbb, _scripted([act6("REPORT\n## r\n\nDone.")], seen_3), data_description="d").go_on("b1", 2, "start over from the slip", run_id="b3")
    rbs = Session(kb, nbb, _scripted([act6("REPORT\n## r\n\nDone.")], seen_s), data_description="d").go_on("b1", 3, "another way from the same turn", run_id="bs")
    rbd = Session(kb, nbb, _scripted([act6("REPORT\n## r\n\nDone.")], []), data_description="d").go_on("b2", 4, "from the second branch's kept turn", run_id="bd")
    check("branch: a branch of a branch carries both hints where it goes on from a turn made under the first one's, each with its turn; from a turn the first "
          "branch itself kept - the very turn it went on from included - its own alone: it is another branch of the chain that turn belongs to, and is recorded "
          "as that chain's",
          rb3.branch == {"of": "a", "turn": 2} and rbs.branch == {"of": "a", "turn": 3} and rbs.hints == [{"turn": 3, "text": "another way from the same turn"}]
          and "keep the two blocks apart" not in _asked(seen_s)[0][1] and rbd.branch == {"of": "b1", "turn": 4}
          and rbd.hints == [{"turn": 3, "text": "keep the two blocks apart"}, {"turn": 4, "text": "from the second branch's kept turn"}] and nbb.owner(rb2, 5) is rb2 and nbb.owner(rbd, 2) is ra_
          and rb2.hints == [{"turn": 3, "text": "keep the two blocks apart"}, {"turn": 4, "text": "and say which is larger"}] and rb2.branch == {"of": "b1", "turn": 4}
          and "HINTS FROM THE PERSON (each given after the turn named; each holds from there to the report):\n- after turn 3: keep the two blocks apart\n- after turn 4: and say which is larger\n\nTASK: turn 5;" in _asked(seen_2)[0][1]
          and rb2.hints[0] is not rb_.hints[0] and rb3.hints == [{"turn": 2, "text": "start over from the slip"}] and "keep the two blocks apart" not in _asked(seen_3)[0][1]
          and "YOUR LAST CELL FAILED" in _asked(seen_3)[0][1] and "TASK: turn 3;" in _asked(seen_3)[0][1], (rb2.hints, rb3.hints))
    # the kept cells run again (the kernel no longer held their states): a cell that printed something else
    seen_r = []
    rr_ = Session(kb, nbb, _scripted([act6("REPORT\n## r\n\nDone.")], seen_r), data_description="d").go_on(
        "a", 3, "keep them apart", run_id="b4", data={"df_id": "loaded now"},
        reran={1: {"stdout": "base 10\n", "results": [], "snap": "new:1"}, 2: {"stdout": "pooled 99\n", "results": [{"text": "pooled, 2 blocks: +99"}], "snap": "new:2"}})
    c1, c2 = rr_.cells()[0], rr_.cells()[1]
    seen_q = []
    rq2 = Session(kb, nbb, _scripted([act6("REPORT\n## r\n\nDone.")], seen_q), data_description="d").go_on("b4", 3, "and once more", run_id="b6")
    check("branch: a kept cell that was run again and printed something else is marked, holds what it printed this time and the results it recorded, and the analyst "
          "is told under its header - in the report turn's view too; one that printed the same only names its new state; the chain it came from keeps its own "
          "output; the branch's data record is that of the data loaded now; a branch of that branch keeps the mark with the turn",
          (c1.kept, c1.snap, c1.stdout) == ("kept", "new:1", "base 10\n") and (c2.kept, c2.snap, c2.stdout) == ("differs", "new:2", "pooled 99\n")
          and c2.results == [{"text": "pooled, 2 blocks: +99"}] and ("--- cell 2 ---\n" + AGAIN_LINE + "```python\npooled = base * 2") in _asked(seen_r)[0][1]
          and AGAIN_LINE not in _asked(seen_r)[0][1].split("--- cell 2 ---")[0] and ra_.cells()[1].stdout == "pooled 20\n" and "(run again: output changed)" in nbb.headline(c2)
          and "(run again" not in nbb.headline(c1) and nbb._render_everything("b4").count("--- cell 2 ---\n" + AGAIN_LINE) == 1 and nbb._render_everything("b4").count(AGAIN_LINE) == 1
          and rr_.data == {"df_id": "loaded now"} and ra_.data == {} and [t.kept for t in rq2.turns[:3]] == ["kept", "kept", "differs"]
          and ("--- cell 2 ---\n" + AGAIN_LINE) in _asked(seen_q)[0][1], (c1.kept, c2.kept, c2.stdout, rr_.data, [t.kept for t in rq2.turns[:3]]))
    # the failed cells in a row go on counting; the effort a lost reply was asked at is carried too
    seen_f = []
    Session(kb, nbb, _scripted([act6("CELL\n```python\nraise ValueError('again')\n```"), act6("REPORT\n## r\n\nDone.")], seen_f), data_description="d").go_on("a", 2, "try once more", run_id="b5")
    asked_l, efforts_l = [], []
    def lost_llm(system, user, **hints):
        if _seat(system, user) != "analyst":
            return ("plain" if _seat(system, user) == "rewrite" else "NONE"), {"cost": 0}
        asked_l.append(user); efforts_l.append(hints.get("effort"))
        return ("" if len(asked_l) == 1 else act6("REPORT\n## r\n\nDone.")), {"cost": 0.01, "effort": "high"}
    rl_ = Session(kb, nbb, lost_llm, data_description="d").run("a reply is lost", budget=Budget(turns=4, dollars=1.0), run_id="l")
    n_l = len(asked_l)
    Session(kb, nbb, lost_llm, data_description="d").go_on("l", 1, "", run_id="l2")
    seen_m, seen_n = [], []
    _SLIP = act6("CELL\n```python\nraise ValueError('slip')\n```")
    rm_ = Session(kb, nbb, _scripted([_SLIP, _SLIP, act6("REPORT\n## r\n\nNothing stands.")], seen_m), data_description="d").run(
        "it gives up", budget=Budget(turns=6, dollars=1.0, max_failures=2), run_id="m")
    Session(kb, nbb, _scripted([act6("REPORT\n## r\n\nDone.")], seen_n), data_description="d").go_on("m", 2, "the name is base", run_id="n")
    check("branch: what else the loop carried goes on with it - a cell that fails right after a kept failed cell is the second in a row, and the call after a kept "
          "turn whose reply was lost asks for the lower effort the first run asked for; the turn at which an analysis gave up - too many failed cells in a row - "
          "can be gone on from like any other",
          branch_points(rm_) == [1, 2] and rm_.turns[1].carry["failures"] == 2 and "TASK: turn 3;" in _asked(seen_n)[0][1]
          and "2 attempts in a row have failed." in _asked(seen_n)[0][1] and "the name is base" in _asked(seen_n)[0][1]
          and "YOUR LAST CELL FAILED" in _asked(seen_f)[1][1] and "2 attempts in a row have failed." in _asked(seen_f)[1][1]
          and rl_.turns[0].kind == "error" and rl_.turns[0].carry["lost_at"] == "high" and efforts_l[1] == ("medium", "low", "minimal", "none", "high")
          and efforts_l[n_l] == efforts_l[1] and asked_l[n_l] == asked_l[1], (efforts_l, _asked(seen_f)[1][1][-200:]))
    # what cannot be gone on from
    refusals = []
    old_ = nbb.new_run("asked before 2.9"); old_.turns = [Turn(kind="cell", cell_no=1, code="x = 1"), Turn(kind="report", text="r")]
    for of, turn in (("a", 6), ("a", 0), ("a", 9), (old_.id, 1)):
        try:
            nbb.branch(of, turn, "x"); refusals.append("made")
        except ValueError as exc:
            refusals.append(str(exc))
    back = Notebook.from_dict(json.loads(json.dumps(nbb.to_dict())))
    check("branch: the report's turn, a turn the run never had and a run whose turns carry nothing (one from before 2.9) cannot be gone on from; the record goes "
          "through the thread's file whole - the carry, the marks, the limits, the branch and its hints",
          refusals == ["run a has no turn 6 to go on from", "run a has no turn 0 to go on from", "run a has no turn 9 to go on from", f"run {old_.id} has no turn 1 to go on from"]
          and branch_points(old_) == [] and back.runs["b2"].hints == rb2.hints and back.runs["b1"].branch == rb_.branch and back.runs["a"].budget == ra_.budget
          and [t.kept for t in back.runs["b4"].turns[:3]] == ["kept", "kept", "differs"] and back.runs["a"].turns[1].carry == ra_.turns[1].carry and branch_points(back.runs["b1"]) == [1, 2, 3, 4],
          refusals)
    # the kept turns count as used: turns, and dollars
    seen_c, seen_d = [], []
    rc_ = Session(kb, nbb, _scripted(_FIRST, seen_c, cost=0.1), data_description="d").run("How do the two blocks compare?", budget=Budget(turns=8, dollars=0.5), run_id="c")
    rd_ = Session(kb, nbb, _scripted([act6("REPORT\n## r\n\nDone [cell 3].")], seen_d, cost=0.1), data_description="d").go_on("c", 5, "write it up", run_id="d")
    from analyst.session import LAST_TURNS_LINE as _LAST
    check("branch: the kept turns count as used - the branch goes on at the next turn number with what was spent by then, so where the money was nearly gone its "
          "first turn is asked for the report, every cell in view",
          "TASK: turn 6; up to 8 turns and $0.50 (spent $0.50).\n" + _LAST in _asked(seen_d)[0][1] and "EVERY CELL OF THIS RUN" in _asked(seen_d)[0][1]
          and rd_.status == "answered" and [t.carry.get("turn") for t in rd_.turns if t.kind != "rewrite"] == [1, 2, 3, 4, 5, None], _asked(seen_d)[0][1][-300:])
finally:
    kb.cleanup()

# the reviewer: a branch that goes on from the turn before a review has it made again, with the hint; from a turn after it, the review is kept
kv = PersistentKernel(df=df); nbv = Notebook("tv"); seen_v = []
try:
    _CELLS = [act6("CELL\n```python\nprint('step %d')\n```" % n) for n in (1, 2, 3)]
    rv_ = Session(kv, nbv, _scripted(_CELLS + [act6("REPORT\n## r\n\nDone [cell 3].")], seen_v), data_description="d").run("q", budget=Budget(turns=6, dollars=1.0, review_every=2), run_id="v")
    seen_w, seen_x = [], []
    rw_ = Session(kv, nbv, _scripted([act6("REPORT\n## r\n\nDone [cell 2].")], seen_w), data_description="d").go_on("v", 2, "look at the second step only", run_id="w")
    ev_x = []
    rx_ = Session(kv, nbv, _scripted([act6("REPORT\n## r\n\nDone [cell 3].")], seen_x), data_description="d", emit=ev_x.append).go_on("v", 3, "look at the third step only", run_id="x")
    kept_x = [(e["type"], e.get("turn"), bool(e.get("review")), bool(e.get("kept"))) for e in ev_x if e["type"] in ("turn_start", "turn_end")][:8]
    rev_w, rev_x = _asked(seen_w, "review"), _asked(seen_x, "review")
    check("branch: going on from the turn before a review, the review is made again and the reviewer is given the hint - after the question, with its line among what "
          "it receives; going on from a turn after it, that review is kept with the turns - sent to the pane as a review, marked kept - and stands in the prompt, "
          "the hint above it",
          [t.kind for t in rv_.turns[:4]] == ["cell", "cell", "review", "cell"] and [t.kind for t in rw_.turns[:3]] == ["cell", "cell", "review"] and rw_.turns[2].kept == ""
          and rev_w[0][1].startswith("QUESTION:\nq\n\nHINT FROM THE PERSON (given after turn 2; it holds from there to the report):\nlook at the second step only\n\nDATA:\n")
          and rev_w[0][0] == reviewer_text(False, hint=True) and REVIEWER_HINT_ITEM in rev_w[0][0] and reviewer_text(False, hint=True).replace(REVIEWER_HINT_ITEM, "", 1) == REVIEWER
          and [t.kind for t in rx_.turns[:4]] == ["cell", "cell", "review", "cell"] and rx_.turns[2].kept == "kept" and "REVIEW (after turn 2 - answer it in your STEP):" in _asked(seen_x)[0][1]
          and _asked(seen_x)[0][1].index("HINT FROM THE PERSON") < _asked(seen_x)[0][1].index("REVIEW (after turn 2") and not any(u.startswith("QUESTION:") and "TURN: after turn 2" in u for _, u in rev_x)
          and kept_x == [("turn_start", 1, False, True), ("turn_end", 1, False, True), ("turn_start", 2, False, True), ("turn_end", 2, False, True),
                         ("turn_start", "review", True, True), ("turn_end", "review", False, True), ("turn_start", 3, False, True), ("turn_end", 3, False, True)],
          ([t.kind for t in rw_.turns], [t.kind for t in rx_.turns], rev_w[0][1][:200] if rev_w else None, kept_x))
finally:
    kv.cleanup()

# a run asked about a figure says so on its record, and the figure rides with that run alone
kq = PersistentKernel(df=df); pics = []
_plain = _scripted([act6("CELL\n```python\nprint('one')\n```")] + [act6("REPORT\n## r\n\nDone.")] * 3, [])
def _pic_llm(system, user, **hints):
    if _seat(system, user) == "analyst":
        pics.append(hints.get("image"))
    return _plain(system, user, **hints)
try:
    sq = Session(kq, Notebook("tq"), _pic_llm, data_description="d")
    sq.run("a question with no plot", budget=Budget(turns=3, dollars=1.0), run_id="p")
    rq_ = sq.run("what does this plot show?", budget=Budget(turns=3, dollars=1.0), image="AAAA")
    sq.go_on("p", 1, "another way")
finally:
    kq.cleanup()
check("branch: a run asked about a figure says so on its record (no branch can be given the picture), and a branch started in the same session is sent none",
      rq_.figure_asked is True and pics == [None, None, "AAAA", None], pics)
from analyst.notebook import same_load, kept_turns
from analyst import draft as _draft_mod
_fig = {"title": "B against A", "kind": "bar", "x": "regime", "y": "yield"}
_nbr = Notebook("tbr"); _src = _nbr.new_run("q"); _src.brief = {"question": "q", "expects": "B above A", "figures": [_fig]}; _src.budget = _asdict(_BUDGET); _src.mode = "Quick"
_src.framing = {"versions": [{"n": 1, "by": "person", "changed": [], "brief": dict(_src.brief)}], "drafts": {_draft_mod.key("q", _fig): {"basis": _draft_mod.COMPUTED}}}
_src.drafts = [{"code": "c1", "keys": [_draft_mod.key("q", _fig)]}]
_src.data = {"df_id": "f1", "name": "trial.csv", "aux": []}
_src.turns = [Turn(kind="cell", cell_no=1, code="x = 1", carry={"turn": 1}), Turn(kind="review", text="after turn 1"), Turn(kind="cell", cell_no=2, code="y = 2", carry={"turn": 2}), Turn(kind="report", text="r")]
_br = _nbr.branch(_src.id, 2, "hint")
check("branch: the brief the person agreed stays - the branch runs under a copy of it, with the conversation that made it and the drafts of its figures, so the "
      "step that draws them follows the same drafts - and so do the mode and the data record; the turns it keeps are those up to the turn, a review between "
      "them included, the report never",
      _br.brief == _src.brief and _br.brief is not _src.brief and _br.framing == _src.framing and _br.framing is not _src.framing and _br.drafts == _src.drafts
      and _br.drafts is not _src.drafts and _draft_mod.agreed(_br) == [{"code": "c1", "titles": ["B against A"], "made_up": []}]
      and _br.mode == "Quick" and _br.data == _src.data and _br.data is not _src.data
      and [t.kind for t in _br.turns] == ["cell", "review", "cell"] and [t.kind for t in kept_turns(_src, 1)] == ["cell"] and len(_src.turns) == 4, [t.kind for t in _br.turns])
_load = {"df_id": "f1", "name": "trial.csv", "rows": 92, "columns": [{"name": "plot"}, {"name": "yield_t"}]}
check("branch: the data a branch needs is the data its turns were computed on - the same frame, or the same content under another id; with no frame, the same files "
      "beside none, none at all included; a frame where there was none, or another one, is not it",
      same_load({"df_id": "f1"}, {"df_id": "f1"}) and same_load(_load, dict(_load, df_id="f1-again")) and same_load({"source": "none", "aux": []}, {"source": "none"})
      and same_load({"aux": ["notes.csv"]}, {"aux": ["notes.csv"]}) and not same_load({"aux": ["notes.csv"]}, {"aux": ["other.csv"]})
      and not same_load({"source": "none"}, {"df_id": "f1"}) and not same_load({"df_id": "f1"}, {"df_id": "f2"}) and not same_load({"df_id": "f1"}, {}))
from analyst.replay import went_back, again as _again
kz = PersistentKernel(df=df)
try:
    _cz = [Turn(kind="cell", cell_no=4, code="zed = 3\nRESULT('zed, doubled', zed * 2)"), Turn(kind="cell", cell_no=5, code="print(zed + 1)"),
           Turn(kind="cell", cell_no=6, code="raise ValueError('gone')"), Turn(kind="cell", cell_no=7, code="print('never')")]
    out_z, err_z = _again(kz, _cz)
    at_z = f"{kz.uid}:{kz.last_step}"
finally:
    kz.cleanup()
check("branch: the cells a branch keeps, run again in a kernel that does not hold their states - what each printed this time, the results it recorded and the "
      "state after it, by cell number; it stops at a cell that fails and says which; the records - the first chain's - are not touched",
      sorted(out_z) == [4, 5] and out_z[4]["stdout"].startswith("RESULT: zed, doubled") and len(out_z[4]["results"]) == 1 and out_z[5]["results"] == []
      and out_z[5]["stdout"] == "4\n" and out_z[5]["snap"] == at_z and out_z[4]["snap"] not in ("", at_z) and sorted(out_z[4]) == ["results", "snap", "stdout"]
      and err_z == "cell 6 failed when run again: ValueError: gone" and not any(t.snap or t.stdout for t in _cz), (out_z, err_z))
class _Kern:
    uid, last_step = "k2", 7
    def __init__(self, replayed): self.last_goto = {"step": 3, "from": 1, "replayed": replayed}
def _ran(out, err="", step=3):
    return [{"step": step, "stdout": out, "error": err}]
_old, _now = Turn(kind="cell", cell_no=1, stdout="one\n", snap="k1:3"), Turn(kind="cell", cell_no=2, stdout="two\n", snap="k2:3")
_much = "x" * (_tools.MAX_OUTPUT_CHARS + 10)
_long = Turn(kind="cell", cell_no=3, stdout=_tools.shown(_much), snap="k2:3")
check("branch: whether the kernel went back to what the record shows is read from what its goto ran again - nothing, or cells that printed what their records "
      "have, an output the record cut short compared as the record keeps it; a cell is known by the state its record names in this kernel, whatever step "
      "another kernel gave another cell; a cell that printed something else, or a step that raised, and it did not",
      went_back(_Kern([]), [_old, _now]) and went_back(_Kern(_ran("two\n")), [_old, _now]) and went_back(_Kern(_ran("two\n")), [_now, _old])
      and went_back(_Kern(_ran(_much)), [_long]) and not went_back(_Kern(_ran("2\n")), [_old, _now]) and not went_back(_Kern(_ran("", "boom", step=5)), [_old, _now])
      and went_back(_Kern(_ran("a step that is no cell's", step=2)), [_old, _now]) and went_back(object(), [_now]))
# a hint outranks the brief (0322; docs/BRANCH_DESIGN.md §2, decision 15): under a brief the hint's section says so, the reviewer is told it with the hint,
# and the step that draws is given the agreed figures with the hint's word over them - a figure the hint takes out is asked for once, with that said
from analyst.session import HINT_OVER_BRIEF, REVIEWER_HINT_OVER_BRIEF, FIGURES_AGREED_HINT, FIGURES_LEFT_OUT_HINT
_cbh = contract(False, 0, brief=True, hint=True)
check("branch: a hint outranks the brief - under a brief the hint's section says that where the hint departs from what the brief fixes the hint is what is computed, and "
      "that the report says where: one line, after the line on the plan, in a run with both and in no other; the reviewer is told the same with the hint, there only",
      HINT_OVER_BRIEF == ("- It outranks the brief too: where it departs from what BRIEF fixes, the hint is what you compute, and the\n  report says where it departs.\n")
      and "- The hint outranks your plan: the next turn acts on it, and every turn after follows it to the report.\n" + HINT_OVER_BRIEF + "- Write it under the note's" in _cbh
      and _cbh.replace(HINT_OVER_BRIEF, "", 1).replace("\n" + CONTRACT_HINT, "", 1) == contract(False, 0, brief=True)
      and not any("outranks the brief" in t or "{OVER_BRIEF}" in t for t in (contract(False, 0, hint=True), contract(False, 0, brief=True), CONTRACT, CONTRACT_HINT))
      and REVIEWER_HINT_ITEM + REVIEWER_HINT_OVER_BRIEF + "- DATA:" in reviewer_text(False, brief=True, hint=True)
      and REVIEWER_HINT_OVER_BRIEF == "  - and where it departs from what BRIEF fixes, the hint holds\n"
      and not any(REVIEWER_HINT_OVER_BRIEF in t for t in (reviewer_text(False, hint=True), reviewer_text(False, brief=True), reviewer_text(False))),
      _cbh[_cbh.index("## A hint from the person"):][:700])


def _fig_branch(steps, hint="One figure is enough: leave the rise in percent out."):
    """The analysis of _fig_run under the brief _fgb, then a branch of it from its turn 1 under `hint`: the branch, and what its seats were sent."""
    seen = {"figures": [], "analyst": [], "first": 0}
    def first(system, user, **h):
        if user.startswith("Rewrite the technical report"): return "# After was 1.2 percent higher than before\n\nplain", {"cost": 0}
        if system.startswith("You are drawing the figures"): return _draws("After against before", "The rise in percent"), {"cost": 0.002}
        seen["first"] += 1; return (_CELL if seen["first"] == 1 else _bact(_BREPORT)), {"cost": 0.001}
    def then(system, user, **h):
        if user.startswith("Rewrite the technical report"): return "# After was 1.2 percent higher than before\n\nplain", {"cost": 0}
        if system.startswith("You are drawing the figures"):
            seen["figures"].append(user); return steps[min(len(seen["figures"]) - 1, len(steps) - 1)], {"cost": 0.002}
        seen["analyst"].append((system, user)); return _bact(_BREPORT), {"cost": 0.001}
    k = PersistentKernel(df=_bdf); nb = Notebook("tfh")
    try:
        src = Session(k, nb, first, data_description="60 rows: part, y", kernel_factory=lambda: PersistentKernel(df=_bdf)).run("Did it work?", budget=Budget(turns=6, dollars=1.0), brief=_fgb)
        _tools.goto(k, src.cells()[0].snap)
        run = Session(k, nb, then, data_description="60 rows: part, y", kernel_factory=lambda: PersistentKernel(df=_bdf)).go_on(src.id, 1, hint)
    finally:
        k.cleanup()
    return src, run, seen


_pp10 = os.environ.get("PYTHONPATH")
if "plotly" in _stubs.FAKE:                  # the kernel's worker imports plotly: the stack's stand-in where the real one is absent
    os.environ["PYTHONPATH"] = os.path.join(ROOT, "tools", "stack", "fakepkgs") + (os.pathsep + _pp10 if _pp10 else "")
try:
    _fh_src, _fh, _fh_seen = _fig_branch([_draws("After against before")])
finally:
    if _pp10 is None: os.environ.pop("PYTHONPATH", None)
    else: os.environ["PYTHONPATH"] = _pp10
_FHINT = "HINT FROM THE PERSON (given after turn 1; it holds from there to the report):\nOne figure is enough: leave the rise in percent out."
check("branch: under a brief with figures, in a run - the analyst's instructions carry the line; the step that draws is given the hint and then the agreed figures, "
      "under a heading that says the hint holds where it asks for another drawing; a reply that leaves an agreed figure out is asked again once, told that a figure the "
      "hint takes out stays out; the cell that leaves it out again runs, and the report says which agreed figure was not drawn",
      _fh.status == "answered" and _fh.branch == {"of": _fh_src.id, "turn": 1} and _fh.brief == _fh_src.brief and HINT_OVER_BRIEF in _fh_seen["analyst"][0][0]
      and FIGURES_AGREED_HINT == ("THE FIGURES AGREED WITH THE PERSON (draw these first, in this order, each as described and under its title, word for word; "
                                  "where the hint asks for another drawing, of these or of their draft, the hint holds):")
      and _fh_seen["figures"][0].startswith("QUESTION:\nDid it work?\n\n" + _FHINT + "\n\n" + FIGURES_AGREED_HINT + '\n1. "After against before" - bars; ')
      and _FAGREED + "\n" not in _fh_seen["figures"][0] and len(_fh_seen["figures"]) == 2
      and _fh_seen["figures"][1] == _fh_seen["figures"][0] + ('\n\nYOUR LAST REPLY LEFT OUT a figure agreed with the person (attempt 1 of 4): "The rise in percent". Nothing was run. '
                                                              'Write the cell again with every agreed figure in it, each under its title, word for word. A figure the hint takes out stays out.')
      and FIGURES_LEFT_OUT_HINT == " A figure the hint takes out stays out."
      and '\n\n> A figure agreed in the brief was not drawn: "The rise in percent".' in _fh.report and "- [fig 2] After against before" in _fh.report
      and "the hint" not in _fa_seen["figures"][1].split("YOUR LAST REPLY LEFT OUT")[1] and _FAGREED + "\n1. " in _fa_seen["figures"][0],
      (_fh.status, _fh_seen["figures"][0][:420], _fh_seen["figures"][-1][-260:], _fh.report[-300:]))

# the Investigation tab of a branch (0322): the notebook view of its whole way - a cell it kept says so, and what the person said stands after the turn they said it after
from analyst.render import notebook_html
_nbh, _nba = notebook_html(rb_), notebook_html(ra_)
_cell_metas = lambda h: [m_ for m_ in re.findall(r'<span class="nb-cell-meta">([^<]*)</span>', h) if " lines" in m_]      # noqa: E731
_nk = Notebook("tk"); _k0 = _nk.new_run("q"); _k0.turns = [Turn(kind="cell", cell_no=1, code="x = 1", carry={"turn": 1}), Turn(kind="show", stdout="--- cell 1 ---", carry={"turn": 2}), Turn(kind="report")]
_k1 = _nk.branch(_k0.id, 2, "Keep the soil  types\napart <now>"); _k1.turns[0].kept = "differs"; _k1.turns.append(Turn(kind="cell", cell_no=2, code="z = 3", carry={"turn": 3}))
_nbk = notebook_html(_k1)
check("branch: the Investigation tab shows its whole way - a cell it kept says kept in its head, a failed one too, a cell of its own says nothing - and the person's hint "
      "stands in a row after the turn it was given after, before the branch's own turns; a kept cell that printed something else when run again says so; the run it "
      "went on from shows neither",
      _cell_metas(_nbh) == ["2 lines · kept", "1 lines · failed, rolled back · kept", "2 lines · kept", "2 lines"]
      and _nbh.count('<div class="nb-step nb-step--hint"><span class="nb-out-label">Your hint</span> keep the two blocks apart</div>') == 1 == _nbh.count("nb-step--hint")
      and _nbh.index("pooled = base * 2") < _nbh.index("nb-step--hint") < _nbh.index("apart = pooled - base")
      and "nb-step--hint" not in _nba and "kept" not in " ".join(_cell_metas(_nba)) and len(_cell_metas(_nba)) == 4
      and _cell_metas(_nbk) == ["1 lines · kept · run again: output changed", "1 lines"]
      and '<div class="nb-step nb-step--hint"><span class="nb-out-label">Your hint</span> Keep the soil types apart &lt;now&gt;</div>' in _nbk
      and _nbk.index("Re-opened a cell") < _nbk.index("nb-step--hint") < _nbk.index("z = 3"), (_cell_metas(_nbh), _cell_metas(_nbk), re.findall(r'<div class="nb-step nb-step--hint">.*?</div>', _nbh + _nbk)))

# a branch read afterwards (0321): its hints are part of what the person asked - a later question's analyst, the Pathfinder and the reach record are told them
from analyst.notebook import hint_lines
_nl = Notebook("tl"); _l0 = _nl.new_run("Does regime B yield more than A?"); _l0.status, _l0.report = "answered", "## B against A\n\nB yields more."
_l0.turns = [Turn(kind="cell", cell_no=1, code="x = 1", carry={"turn": 1}), Turn(kind="cell", cell_no=2, code="y = 2", carry={"turn": 2}), Turn(kind="report")]
_l1 = _nl.branch(_l0.id, 1, "Keep the soil types\n  apart, and write the table to plots_by_soil.csv"); _l1.turns.append(Turn(kind="cell", cell_no=2, code="z = 3", carry={"turn": 2}))
_l2 = _nl.branch(_l1.id, 2, "Leave the sandy plots out"); _l2.status, _l2.report = "answered", "## By soil type\n\nOn loam B yields more."
_l3, _l4 = _nl.new_run("And by plot size?", _l2.id), _nl.new_run("And by plot size?", _l0.id)
_said = ["HINT FROM THE PERSON after turn 1: Keep the soil types apart, and write the table to plots_by_soil.csv", "HINT FROM THE PERSON after turn 2: Leave the sandy plots out"]
check("branch: a question asked from a branch is told what the person said on the branch's way - each hint on a line of its own, in the order given, under the branch's "
      "question: in the ledger of the thread, in the chain opened whole (SHOW RUN) and in what the Pathfinder reads of the thread; a chain that is no branch has no such line",
      hint_lines(_l2.hints) == _said and hint_lines([]) == [] and hint_lines(None) == []
      and _nl.render_ancestry(_l3.id).startswith("EARLIER IN THIS THREAD - the ledger (every chain; SHOW RUN k opens one whole):\n[run 1] Q: Does regime B yield more than A?\n"
                                                 f"        {_said[0]}\n        {_said[1]}\n        Conclusion: On loam B yields more.\n")
      and _nl.render_ancestry(_l3.id).count("HINT FROM THE PERSON") == 2
      and _nl.render_run(_l3.id, 1) == f"--- run 1 ---\nQUESTION: Does regime B yield more than A?\n{_said[0]}\n{_said[1]}\nFINAL NOTE:\n(none)\nREPORT:\n## By soil type\n\nOn loam B yields more."
      and arch.earlier(_nl, _l3.id) == f"EARLIER (the analyses this question follows, oldest first):\n[1] Q: Does regime B yield more than A?\n    {_said[0]}\n    {_said[1]}\n    Found: On loam B yields more."
      and not any("HINT" in t for t in (_nl.render_ancestry(_l4.id), _nl.render_run(_l4.id, 1), arch.earlier(_nl, _l4.id)))
      and _nl.render_run(_l4.id, 1) == "--- run 1 ---\nQUESTION: Does regime B yield more than A?\nFINAL NOTE:\n(none)\nREPORT:\n## B against A\n\nB yields more.",
      (_nl.render_ancestry(_l3.id), _nl.render_run(_l3.id, 1), arch.earlier(_nl, _l3.id)))
_sess = type("S", (), {"nb": _nl})()
_csv = [{"kind": "file", "path": "/work/plots_by_soil.csv"}]
check("branch: what a hint names is asked for - the reach record reads the thread's questions and the hints given on the way, a branch's own and those of a branch the "
      "question was asked from; on a way without the hint the same file is not asked for",
      Session._questions(_sess, _l2) == ["Does regime B yield more than A?", "Keep the soil types\n  apart, and write the table to plots_by_soil.csv", "Leave the sandy plots out"]
      and Session._questions(_sess, _l3) == ["Does regime B yield more than A?", "And by plot size?", "Keep the soil types\n  apart, and write the table to plots_by_soil.csv", "Leave the sandy plots out"]
      and Session._questions(_sess, _l4) == ["Does regime B yield more than A?", "And by plot size?"]
      and [reach.mark(_csv, Session._questions(_sess, r))[0]["asked"] for r in (_l1, _l2, _l3, _l0, _l4)] == [True, True, True, False, False],
      [Session._questions(_sess, r) for r in (_l2, _l3, _l4)])
_hint_run = Notebook("th").new_run("q"); _hint_run.hints = [{"turn": 2, "text": "one"}, {"turn": 5, "text": "two"}]
_htexts = {"contract (hint)": contract(False, 0, hint=True), "reviewer (hint)": reviewer_text(False, hint=True), "the hint's section": CONTRACT_HINT, "the block": hint_block(_hint_run), "the lines": "\n".join(hint_lines(_hint_run.hints)), "over the brief": HINT_OVER_BRIEF + REVIEWER_HINT_OVER_BRIEF + FIGURES_AGREED_HINT + FIGURES_LEFT_OUT_HINT, "run again": AGAIN_LINE}
check("branch: the standing rules hold for its texts too - none of the tested tasks' vocabulary, and no section named for thinking or reasoning, in the contract with "
      "a hint, the reviewer's prompt with one, the block's own words, the lines a later reader is given, what says the hint outranks the brief and the mark of a cell run again; a run without a hint has no block",
      not {n: sorted({m.group(0) for m in _DOMAIN.finditer(t)}) for n, t in _htexts.items() if _DOMAIN.search(t)}
      and not any(_re_c.search(r"(?i)\b(thinking|reasoning|scratchpad|memory|private)\b", t) for t in _htexts.values()) and hint_block(Notebook("tn0").new_run("q")) == "",
      {n: sorted({m.group(0) for m in _DOMAIN.finditer(t)}) for n, t in _htexts.items() if _DOMAIN.search(t)})

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
