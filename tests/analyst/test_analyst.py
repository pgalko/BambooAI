"""The analyst package: the tree, the turn format, the loop over a real kernel,
the guards, assembly and replay. Run: python3 tests/analyst/test_analyst.py"""
import os, sys, json, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.dirname(os.path.abspath(__file__)), ROOT, os.path.join(ROOT, "delve")]
import pandas as pd, numpy as np
from analyst import Session, Budget, Notebook, NotebookStore, parse_turn, replay, report
from kernel import PersistentKernel

passed, failed = [], []
def check(name, cond, detail=""):
    (passed if cond else failed).append(name); print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {detail}"))

# ---- the turn format ----
_, note, act = parse_turn("some thinking\n###NOTE###\n- Question as understood: q\n- Plan: p\n###ACTION###\nCELL\n```python\nprint(1)\n```")
check("parse: note and CELL", note.startswith("- Question") and act.verb == "cell" and act.arg == "print(1)")
check("parse: SHOW / NAMES / RECALL / SEARCH / ASK / REPORT",
      parse_turn("###NOTE###\nn\n###ACTION###\nSHOW 3")[2].arg == "3"
      and parse_turn("###NOTE###\nn\n###ACTION###\nNAMES")[2].verb == "names"
      and parse_turn("###NOTE###\nn\n###ACTION###\nRECALL cluster bootstrap")[2].arg == "cluster bootstrap"
      and parse_turn("###NOTE###\nn\n###ACTION###\nASK Do you mean training pace?")[2].arg.startswith("Do you mean")
      and parse_turn("###NOTE###\nn\n###ACTION###\nREPORT\nThe answer.\n\nMore.")[2].arg == "The answer.\n\nMore.")
check("parse: a reply without an action is 'invalid', not a crash", parse_turn("just prose")[2].verb == "invalid")
th, nt, ac = parse_turn("###THINKING###\nThe last output shows 9 athletes overlap.\n###NOTE###\n- Question as understood: q\n###ACTION###\nNAMES")
check("parse: the THINKING slot is captured as thinking, not as the note", th == "The last output shows 9 athletes overlap." and nt.startswith("- Question") and ac.verb == "names")
check("parse: an empty reply is reported as 'empty reply', distinct from a malformed one", parse_turn("")[2].arg == "empty reply" and parse_turn("prose")[2].arg == "no ###ACTION### block")

# ---- the tree ----
nb = Notebook("t1"); r1 = nb.new_run("q1"); r2 = nb.new_run("q2", parent=r1.id); r3 = nb.new_run("q3 (branch from q1)", parent=r1.id)
check("tree: paths follow parents, a branch does not see its sibling",
      [r.id for r in nb.path(r2.id)] == [r1.id, r2.id] and [r.id for r in nb.path(r3.id)] == [r1.id, r3.id])
d = Notebook.from_dict(json.loads(json.dumps(nb.to_dict())))
check("tree: round-trips through JSON", set(d.runs) == set(nb.runs) and d.runs[r3.id].parent == r1.id)

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
 "###NOTE###\n" + NOTE.replace("none yet", "B-A = see cell 2") + "\n###ACTION###\nREPORT\n## Answer\nB exceeds A by {DIFF} units on average across 4 units [cell 2]; the group means are in [cell 1]. The spread 0.999 is a made-up number.\n\n| arm | mean |\n|---|---|---|\n| A | 1 |\n",
]
calls = {"n": 0, "prompts": []}
def fake_llm(system, user, **hints):
    calls["prompts"].append(user)
    if user.startswith("Rewrite the technical report"):
        return "B is higher than A by about {DIFF} units; and 7.777 is invented.", {"cost": 0.01}
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
cells = run.cells()
check("loop: only committed cells get numbers (the syntax error did not), numbering along the path",
      [c.cell_no for c in cells] == [1, 2] and run.turns[1].error and run.turns[1].cell_no is None)
check("loop: the kernel state persisted across cells (cell 2 used g from cell 1)", "n units 4" in cells[1].stdout)
check("loop: SHOW re-opened cell 1 into the next prompt", any("SHOWN:" in p and "means" in p for p in calls["prompts"]))
check("loop: the prompt carries the contract's six-heading note and collapses nothing while under the recent window",
      all("YOUR NOTE" in p for p in calls["prompts"][1:6]))
check("report: the technical guard flagged the invented 0.999 and nothing else",
      "CHECK: 1 number(s)" in run.report and "0.999" in run.report.split("CHECK")[1])
check("report: the table separator was repaired to the header's width", "|---|---|\n" in run.report and "|---|---|---|" not in run.report)
check("rewrite: same analyst, the guard flagged the invented 7.777", run.rewrite and "7.777" in run.rewrite.split("CHECK")[-1])
check("replay: assembled the two cited cells and reproduced them in a fresh kernel",
      run.replay_status == "reproduced" and "# --- cell 1 ---" in run.replay_script and "# --- cell 2 ---" in run.replay_script, run.replay_status)
check("emit: cells, show, names, report, rewrite, replay_status all streamed",
      {e["type"] for e in events} >= {"cell", "names", "show", "report", "rewrite", "replay_status"})
saved = store.load("t2"); rr = saved.runs[run.id]
check("store: the run is on disk with its turns, reports and replay", rr.report == run.report and rr.replay_status == "reproduced" and len(rr.turns) == 7)

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
check("two failures in a row add the look-before-computing nudge; one does not",
      "attempts in a row have failed" in seen["prompts"][4] and "attempts in a row have failed" not in seen["prompts"][1])
check("failed attempts are listed in CELLS SO FAR for the rest of the run",
      "FAILED ATTEMPTS THIS RUN" in seen["prompts"][-2] and "undefined_name" in seen["prompts"][-2])

# ---- error condensing: the exception line first, verbose tails cut ----
from analyst.tools import condense_error, exception_line
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
    if "STOP:" in user and "could not get past this error" in user:
        seen_loop["halt_seen"] = True
        return "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## Answer\nCould not get past the error; nothing established.\n", {"cost": 0.01}
    i = seen_loop["n"]; seen_loop["n"] += 1
    return LOOP[min(i, len(LOOP) - 1)], {"cost": 0.01}
k4 = PersistentKernel(df=df); nb4 = Notebook("t4")
try:
    r4 = Session(k4, nb4, loop_llm, data_description="d").run("q", budget=Budget(turns=15, dollars=1.0))
finally:
    k4.cleanup()
fails_in_row = sum(1 for t in r4.turns if t.kind == "cell" and t.error)
check("ceiling: after five consecutive failed cells the session stops trying and forces the report (not fifteen attempts)",
      fails_in_row == 5 and seen_loop["halt_seen"] and r4.status == "answered" and "Could not get past" in r4.report, (fails_in_row, seen_loop["halt_seen"], r4.status))

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

# ---- search: a per-run budget, the view capped with a handle, the record whole ----
SEARCHES = ["###NOTE###\n" + NOTE + "\n###ACTION###\nSEARCH query %d" % i for i in range(6)] + ["###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## r\n\nDone."]
seen_s = {"prompts": []}
def search_llm(system, user, **hints):
    seen_s["prompts"].append(user)
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    i = len([p for p in seen_s["prompts"] if not p.startswith("Rewrite")]) - 1
    return SEARCHES[min(i, len(SEARCHES) - 1)], {"cost": 0.001}
calls = {"n": 0}
def fake_search(q):
    calls["n"] += 1
    return "SOURCED CLAIMS:\n- a figure [1]\n\nSOURCES:\n[1] x - https://x\n\nSUMMARY:\n" + ("long digest " * 600)
k7 = PersistentKernel(df=df); nb7 = Notebook("t7")
try:
    r7 = Session(k7, nb7, search_llm, data_description="d", search=fake_search).run("q", budget=Budget(turns=8, dollars=1.0, searches=4))
finally:
    k7.cleanup()
srch = [t for t in r7.turns if t.kind == "search"]
check("search budget: the seam is called four times, the fifth and sixth SEARCH answer from budget without a call",
      calls["n"] == 4 and len(srch) == 6 and srch[4].stdout.startswith("(search budget") and srch[5].stdout.startswith("(search budget"), (calls["n"], len(srch)))
p2 = seen_s["prompts"][1]
check("search view: the digest is capped in the prompt with 'SHOW SEARCH 1 for all', the record keeps it whole, the count left is shown",
      "SHOW SEARCH 1 for all" in p2 and "searches left in this run: 3" in p2 and len(srch[0].stdout) > 7000)
check("SHOW SEARCH 1 re-opens the whole digest", len(nb7.render_search(r7.id, 1)) > 7000 and "--- search 1: query 0 ---" in nb7.render_search(r7.id, 1))

# ---- ideas: five next questions from one call, no cells, recorded as a chain ----
IDEAS_REPLY = ("###THINKING###\nfive questions\n###NOTE###\n- Plan: REPORT\n###ACTION###\nREPORT\nThe thread has two pieces so far.\n\n1. **Split by port**: How many survivors boarded at each port?\n2. **First departure**: Does boarding at the first port change survival?\n"
               "3. **Missing ports**: Did the two passengers without a port survive?\n4. **Mix inside survivors**: Is the port mix among survivors the table's mix?\n5. **A useful grouping?**: Does port separate outcomes more than chance?\n\nThese stay close to the count.")
IDEAS_LIST = ("1. **Split by port**: How many survivors boarded at each port?\n2. **First departure**: Does boarding at the first port change survival?\n"
              "3. **Missing ports**: Did the two passengers without a port survive?\n4. **Mix inside survivors**: Is the port mix among survivors the table's mix?\n5. **A useful grouping?**: Does port separate outcomes more than chance?")
ideas_seen = {}
def ideas_llm(system, user, **hints):
    ideas_seen['user'] = user; return IDEAS_REPLY, {"cost": 0.004}
k9 = PersistentKernel(df=df); nb9 = Notebook("t9")
try:
    base = Session(k9, nb9, thread_llm_factory(["###NOTE###\n" + NOTE5 + "\n###ACTION###\nREPORT\n## r\n\nOf 891 rows, 342 survived."]), data_description="File: titanic.csv").run("How many survived?", budget=Budget(turns=2, dollars=1.0))
    sess9 = Session(k9, nb9, ideas_llm, data_description="File: titanic.csv")
    r9 = sess9.ideas(4, parent=base.id, run_id="ideas1")
    check("ideas: one model call with its own system prompt, over the thread's ledger and the data, at the asked level; no cells; the report is the five items and nothing else",
          r9.status == "answered" and r9.report == IDEAS_LIST and not r9.cells() and [t.kind for t in r9.turns] == ["ideas"] and "variation level 4" in ideas_seen['user'] and "How many survived?" in ideas_seen['user'] and "File: titanic.csv" in ideas_seen['user'] and nb9.runs["ideas1"].parent == base.id, (r9.status, [t.kind for t in r9.turns]))
    check("ideas: a later chain's ledger names the ideas chain with its conclusion", "[run 2] Q: User requested variations of the enquiry (level 4)" in nb9.render_ancestry(Session(k9, nb9, ideas_llm, data_description="d").nb.new_run("next", parent="ideas1").id))
finally:
    k9.cleanup()

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
_seen = []
def _spy_llm(system, user, **hints): _seen.append(user); return "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## r\n\nOne.", {"cost": 0.001}
k11 = PersistentKernel(df=df); nb11 = Notebook("t11")
try:
    Session(k11, nb11, _spy_llm, data_description="d").run("q", budget=Budget(turns=2, dollars=1.0))
finally:
    k11.cleanup()
check("quick: a two-turn budget's first turn is not told the budget is nearly gone", _seen and "nearly gone" not in _seen[0], _seen[0][-160:] if _seen else "")

# ---- plain statement over metaphor: in the report's contract and in the rewrite task (2026-09-08) ----
from analyst.session import REWRITE_TASK as _RW
check("prose: the contract and the rewrite both ask for direct statements, never metaphor", "never metaphor" in open(os.path.join(ROOT, "analyst", "contract.md")).read() and "never let a metaphor" in _RW)

# ---- the prompt window: newest cell whole, earlier recent cells collapsed ----
nbw = Notebook("tw"); rw = nbw.new_run("q")
for i in range(5):
    nbw.runs[rw.id].turns.append(Turn(kind="cell", code="\n".join(f"line{j} = {j}" for j in range(30)), stdout=("out%d " % i) * 900, cell_no=i + 1))
view = nbw.render_cells(rw.id)
check("window: the newest cell's code and output ride whole; the two before it show 14 code lines and 1500 chars of output; older cells one line",
      view.count("--- cell") == 4 and "SHOW 5 for all" not in view and view.count("more lines (SHOW") == 3
      and "[cell 1]" in view and view.count("more characters; SHOW") == 3, (view.count("--- cell"), view.count("more lines (SHOW")))
check("guard: a constant that appears in a cell's code (a filter bound) is not flagged as unverified",
      report.numbers_missing("laps with pace 2.8-8 min/km gave 1.069 [cell 1]", ["ratio 1.069"] + ["q = df[(df.pace >= 2.8) & (df.pace <= 8)]"]) == [])

# ---- guards edge cases ----
check("guard: years and small integers are not policed; rounding is tolerated",
      report.numbers_missing("In 2024 we saw 3 groups and a mean of 1.70", ["mean 1.699"]) == [])
check("guard: a real missing number is reported", report.numbers_missing("the estimate is 42.5", ["nothing"]) == ["42.5"])

# ---- the contract has no benchmark vocabulary ----
import re
c = open(os.path.join(ROOT, "analyst", "contract.md")).read()
# ---- the self-review turn (2026-09-10): marked for the caller, never the first turn, every review_every after it
hints_seen, starts = [], []
def review_llm(system, user, **hints):
    hints_seen.append(dict(hints))
    n = len(hints_seen)
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    if n >= 5: return "###THINKING###\nt\n###NOTE###\n- Question as understood: q\n###ACTION###\nREPORT\nDone.", {"cost": 0.001}
    return "###THINKING###\nt\n###NOTE###\n- Question as understood: q\n###ACTION###\nCELL\n```python\nprint(%d)\n```" % n, {"cost": 0.001}
k9 = PersistentKernel(df=df); nb9 = Notebook("t9")
s9 = Session(k9, nb9, review_llm, emit=lambda ev: starts.append(ev) if ev.get("type") == "turn_start" else None, data_description="d")
try:
    s9.run("q", budget=Budget(turns=6, dollars=1.0, review_every=2))
finally:
    k9.cleanup()
flags = [h.get("review") for h in hints_seen if "review" in h]
check("review: turns 3 and 5 are review turns (every 2 after the first), passed as review=True; the others False",
      flags == [False, False, True, False, True], flags)
check("rewrite: the plain-language rewrite call carries rewrite=True and no other call does",
      [h.get("rewrite") for h in hints_seen] == [None] * 5 + [True] or hints_seen[-1].get("rewrite") is True and not any(h.get("rewrite") for h in hints_seen[:-1]), hints_seen)
turn_flags = [e.get("review") for e in starts if isinstance(e.get("turn"), int)]         # the rewrite's own start carries no flag
check("review: the turn_start event carries the flag for the pane", turn_flags == [False, False, True, False, True], turn_flags)
check("review: the review line is in the prompt on review turns only", Session.is_review(Budget(turns=50, review_every=8), 9) and not Session.is_review(Budget(turns=50, review_every=8), 8)
      and not Session.is_review(Budget(turns=50, review_every=0), 9) and not Session.is_review(Budget(turns=50, review_every=8), 1))

# ---- the report turn sees everything; SHOW takes several cells (2026-09-10, from a run whose report could not quote cell 9)
seen_prompts = []
def view_llm(system, user, **hints):
    seen_prompts.append(user)
    n = len(seen_prompts)
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
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
check("contract: one page, neutral", len(c) < 6500 and not bad, (len(c), bad))

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
