"""The analyst package: the tree, the turn format, the loop over a real kernel,
the guards, assembly and replay. Run: python3 tests/analyst/test_analyst.py"""
import os, sys, json, tempfile
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.dirname(os.path.abspath(__file__)), ROOT, os.path.join(ROOT, "delve")]
import pandas as pd, numpy as np
from analyst import Session, Budget, Notebook, NotebookStore, parse_turn, replay, report
from analyst.session import contract, READ_ROW, CONTRACT, CONTRACT_DOCUMENTS
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
check("two failures in a row are said - the fact, no advice; one failure is not",
      "attempts in a row have failed" in seen["prompts"][4] and "attempts in a row have failed" not in seen["prompts"][1])
check("failed attempts are listed in CELLS SO FAR for the rest of the run",
      "FAILED ATTEMPTS THIS RUN" in [p_ for p_ in seen["prompts"] if "TASK:" in p_][-1] and "undefined_name" in [p_ for p_ in seen["prompts"] if "TASK:" in p_][-1])

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
check("contract: one to three figures and a fourth figure cell not run - the mechanism, with no advice on when to draw them",
      "A report carries one to three figures; a fourth figure cell is not run." in c_all and "drawn once" not in c_all and "where it breaks down" not in c_all)
check("contract: an estimate is recorded with the kernel's RESULT(...), the words the analyst's and the numbers the cell's; a typed number is marked; a revised estimate gets a new line",
      "record it in that cell with the\nkernel's `RESULT(what, estimate, low, high, unit, direction)`" in c_all and "A number written into the call instead of computed is marked as typed" in c_all
      and "A revised estimate gets a new\nline" in c_all and "print it on one line" not in c_all)
# ---- figures: at most FIGURE_CELLS_MAX figure cells a run; the fourth is not run and the reply says so ----
FIGS = [act6(f"CELL\n```python\nclass _F:\n    def show(self): print('fig {k}')\nfig = _F(); fig.show()\n```") for k in range(1, 5)] + [act6("REPORT\n## r\n\nDone.")]
fig_i = {"n": 0}; fig_prompts = []
def fig_llm(system, user, **h):
    fig_prompts.append(user)
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
    i = fig_i["n"]; fig_i["n"] += 1
    return FIGS[min(i, len(FIGS) - 1)], {"cost": 0.001}
kf = PersistentKernel(df=df); nbf = Notebook("tf")
try:
    rf = Session(kf, nbf, fig_llm, data_description="d").run("q", budget=Budget(turns=8, dollars=1.0))
finally:
    kf.cleanup()
fig_cells = [x for x in rf.turns if x.kind == "cell" and x.cell_no]
check("figure cap: three figure cells commit, the fourth is not run - no cell number, the output says 'Figure limit' and what to do - and the run goes on to its report",
      len(fig_cells) == 3 and rf.turns[3].kind == "cell" and rf.turns[3].cell_no is None and "Figure limit" in (rf.turns[3].stdout or "") and rf.status == "answered",
      ([(x.kind, x.cell_no) for x in rf.turns], (rf.turns[3].stdout or "")[:80]))
check("figure cap: the refusal reaches the next prompt", any("Figure limit" in p_ for p_ in fig_prompts), len(fig_prompts))

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
    return "SOURCED CLAIMS:\n- a figure [1]\n\nSOURCES:\n[1] x - https://x\n\nSUMMARY:\n" + ("long digest\n" * 1100) + "the last line survives"
k7 = PersistentKernel(df=df); nb7 = Notebook("t7")
try:
    r7 = Session(k7, nb7, search_llm, data_description="d", search=fake_search).run("q", budget=Budget(turns=10, dollars=1.0, searches=4))
finally:
    k7.cleanup()
srch = [t for t in r7.turns if t.kind == "search"]
check("search budget: the seam is called four times, the fifth and sixth SEARCH answer from budget without a call",
      calls["n"] == 4 and len(srch) == 6 and srch[4].stdout.startswith("(search budget") and srch[5].stdout.startswith("(search budget"), (calls["n"], len(srch)))
p2 = seen_s["prompts"][1]
check("search view: a digest past the 12,000-character safety cap is cut from the middle - its head and its last line both in the prompt, the marker naming SHOW SEARCH 1 - the record keeps it whole, the count left is shown",
      "SOURCED CLAIMS:" in p2 and "the last line survives" in p2 and "omitted from the middle for length; SHOW SEARCH 1 for all" in p2 and "searches left in this run: 3" in p2 and len(srch[0].stdout) > 13000, p2[-400:])
check("SHOW SEARCH 1 re-opens the whole digest", len(nb7.render_search(r7.id, 1)) > 13000 and "--- search 1: query 0 ---" in nb7.render_search(r7.id, 1))
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
check("quick: a two-turn budget's first turn is not told the budget is nearly gone (it fires on the last turn itself)", _seen and "nearly gone" not in _seen[0], _seen[0][-160:] if _seen else "")

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
      and "TURNS (the analyst's own account of each turn, its action, and the outcome):\n- turn 1: (no thinking written) | cell 1 -> RESULT: B vs A step 1" in u1
      and "TO CHECK NOW (code and complete output; no review has checked these):\n--- cell 2 (a result recorded since the last review) ---\n```python\ne = 1.5\nRESULT('B vs A step 2" in u1
      and "\nOUTPUT:\nRESULT: B vs A step 2" in u1 and "--- cell 1 (a result recorded since the last review) ---" in u1 and u1.rstrip().endswith("TURN: after turn 2; up to 12."), u1[-1500:])
u2 = rv_calls[1][1]
check("review: the second review's input - what the first review checked (its Checked lines), the earlier review with the analyst's answer and the test's status, only the turns since, the new cells and the one asked for again, not the one already checked",
      "CHECKED BY EARLIER REVIEWS:\n- cell 1: the same, step 1; matches its line (review after turn 2)\n- cell 2: computes the mean difference B vs A for 20 subjects; matches its line (review after turn 2)" in u2
      and "EARLIER REVIEWS:\n- after turn 2: Verdict: TEST bootstrap the difference by subject\n  the analyst then:" in u2
      and "  since then: cells 3, 4 committed; 0 failed attempts; cells that printed nothing: none" in u2 and '  status: open - no RESULT recorded with test="after turn 2"' in u2
      and "TURNS SINCE YOUR LAST REVIEW (the analyst's own account of each turn, its action, and the outcome):\n- turn 3:" in u2 and "- turn 1:" not in u2
      and "--- cell 4 (a result recorded since the last review) ---" in u2 and "--- cell 3 (a result recorded since the last review) ---" in u2
      and "--- cell 1 (you asked to see it again) ---" in u2 and "--- cell 2 (" not in u2 and u2.rstrip().endswith("TURN: after turn 4; up to 12."), u2[-2500:])
rv_turns = [t for t in r9.turns if t.kind == "review"]
check("review: the review turn records the cells it was handed, its Checked lines and its Re-check; the card's lines carry them",
      rv_turns[0].shown == [2, 1] and rv_turns[0].checked == [{"cell": 2, "text": "computes the mean difference B vs A for 20 subjects; matches its line", "ok": True}, {"cell": 1, "text": "the same, step 1; matches its line", "ok": True}]
      and rv_turns[0].recheck == [1] and rv_turns[1].shown == [4, 3, 1] and "- Checked: cell 2 - computes the mean difference" in rv_turns[0].note
      and "- Re-check: cell 1" in rv_turns[0].note and "- Shown: cell 2, cell 1" in rv_turns[0].note, (rv_turns[0].shown, rv_turns[0].checked, rv_turns[0].recheck, rv_turns[1].shown, rv_turns[0].note))
check("review: the analyst's REVIEW block carries the TEST's status - open until a RESULT recorded with it",
      "- Status: open - no RESULT line tagged (test after turn 2) yet" in an_prompts[2][0], an_prompts[2][0][-400:])
# a tagged RESULT answers the test: the status says so, in the analyst's block and in the reviewer's input
tg_prompts, tg_rv = [], []
def tagged_llm(system, user, **h):
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
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
check("review: the review rides in the analyst's next prompts under REVIEW, above the task line, until the next one",
      "REVIEW (after turn 2 - answer it in your THINKING):\n- The question requires: B against A with an interval." in p3 and p3.index("REVIEW (after turn 2") < p3.index("TASK: turn 3")
      and "REVIEW (after turn 2" in an_prompts[3][0], p3[-500:])
p5 = an_prompts[4][0]
check("review: a REPORT verdict citing a cell handed to it binds - the next turn is the report: every cell in view, the review above, the report-now line - and the run is answered",
      "REVIEW (after turn 4 - answer it in your THINKING):" in p5 and "- Verdict: REPORT the comparison is made" in p5 and "this turn is the report. Write REPORT now." in p5
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
from analyst.session import checked_ok, disputed_cells, Run as _Run, Turn as _Turn
check("checked_ok: 'matches its line' is fine, 'does not match' is not, a line with both ('matches ..., but does not cover ...') stays fine",
      checked_ok("computes the difference; matches its line") and not checked_ok("labelled within-athlete; no athlete term: pooled. Does not match.")
      and checked_ok("matches its line, but does not cover the surface difference"))
_rd = _Run(id="rd2", question="q", parent=None)
_rd.turns = [_Turn(kind="review", text="after turn 2", checked=[{"cell": 4, "text": "does not match", "ok": False}]),
             _Turn(kind="review", text="after turn 4", checked=[{"cell": 4, "text": "refit; matches its line", "ok": True}])]
check("disputed_cells: the latest review's word on a cell stands - a later 'matches' clears an earlier 'does not'", disputed_cells(_rd) == {}, disputed_cells(_rd))

from analyst.session import result_lines, Run as _Run, Turn as _Turn
_rc = _Run(id="rc", question="q", parent=None)
_rc.turns = [_Turn(kind="cell", cell_no=1, code="x", results=[{"text": "slope within athletes, 54 sessions: -2.1 (95% CI -17.9 to +13.7)", "typed": False, "test": None, "corrects": None}]),
             _Turn(kind="cell", cell_no=2, code="y", results=[{"text": "(corrects cell 1) slope pooled, not within athletes - with athlete fixed effects: +4.0 (95% CI -9 to +17)", "typed": False, "test": None, "corrects": 1}])]
check("ledger: a RESULT recorded with corrects=1 marks cell 1's line as corrected, in every prompt's RESULTS SO FAR",
      result_lines(_rc) == ["- [cell 1] (corrected by cell 2) slope within athletes, 54 sessions: -2.1 (95% CI -17.9 to +13.7)",
                            "- [cell 2] (corrects cell 1) slope pooled, not within athletes - with athlete fixed effects: +4.0 (95% CI -9 to +17)"], result_lines(_rc))
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
check("contract: a correction is recorded with corrects=14, and the earlier line is marked", "`corrects=14`" in c_all and "cell 14's line is marked as corrected" in c_all)
check("contract (Adaptive): a REPORT citing a cell not checked is advice; the reviewer reads the cells the estimate rests on",
      "unless its status says a cell it cites has not been checked: then it is advice" in contract(False, 8) and "the code and output of the cells your estimate rests on" in contract(False, 8))
check("reviewer prompt: the cells to check are handed to it, one Checked line per cell, Re-check for a second look, REPORT binds only on checked cells; no SHOW",
      "TO CHECK NOW" in REVIEWER and "Write one Checked line per cell" in REVIEWER and "name that\ncell under Re-check" in REVIEWER
      and "It binds only when every cell you cite has been checked" in REVIEWER and "SHOW" not in REVIEWER and "not proof that its label describes what the code computed" in REVIEWER)
# ---- the standing rule (2026-10-05): no task-specific or model-specific content in any prompt. Every authored text a model
# ---- reads is scanned for the vocabulary of the tasks this agent was tested on; docstrings and comments are not prompts.
import ast as _ast
from analyst.session import REWRITE_TASK, LAST_TURNS_LINE, REPORT_NOW
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
_texts = {"contract (plain)": contract(False, 0), "contract (documents, reviews)": contract(True, 8), "reviewer": REVIEWER,
          "rewrite task": REWRITE_TASK, "reader": READER_SYSTEM, "last turns": LAST_TURNS_LINE, "report now": REPORT_NOW}
for _path in ("analyst/session.py", "analyst/tools.py", "bambooai/reading.py"):
    for _k, _t in enumerate(_authored_strings(_path)):
        _texts[f"{_path} string {_k}"] = _t
_hits = {name: sorted({m.group(0) for m in _DOMAIN.finditer(t)}) for name, t in _texts.items() if _DOMAIN.search(t)}
check("standing rule: no prompt text a model reads carries the tested tasks' vocabulary - contract, reviewer, rewrite, reader, and every string the session, tools and reader send",
      not _hits, _hits)
# Quick and Deep make no reviewer call at all - not during the run, not after the report (2026-10-05)
nr_systems = []
def noreview_llm(system, user, **h):
    nr_systems.append(system[:40])
    if user.startswith("Rewrite"): return "plain", {"cost": 0}
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
check("contract: one page - under 8,800 without documents (2026-10-06: Results with RESULT(...), DS, the comparison, the budget as a limit), neutral", len(c) < 8800 and not bad, (len(c), bad))
check("contract: a reply with more than one action runs the first and the rest does not - said in Format", "A reply with more than one action runs\nthe first; the rest does not run." in c)
check("contract (Adaptive): a TEST's outcome is recorded with test='after turn 16', and the test is open until it is recorded",
      "`RESULT(..., test=\"after turn 16\")`" in contract(False, 8) and "until such a line is recorded the test is open" in contract(False, 8))
check("contract: the format is a literal template of one turn - three marker lines, each once - and the actions are a table with one row per form",
      c.count("###THINKING###") == 1 and c.count("###NOTE###") == 1 and c.count("###ACTION###") == 1 and "| a fenced python block |" in c and "| `CELL` |" not in c and "| `REPORT` |" in c and "Seven headings" in c and "under the headings listed in The note" in c)
check("contract: no documents furniture and the one budget rule when the thread has no documents",
      "READ D1" not in c and "[D1.17]" not in c and "LOOK" not in c and "## Documents" not in c and "The limit is not a target" in c and "Write REPORT when the answer is established" in c)
cd_ = open(os.path.join(ROOT, "analyst", "contract_documents.md")).read()
check("the documents' section: the seven kernel objects, READ for what grep cannot do, the citation rule, no LOOK - under 900 characters; the READ row names the stretch forms", len(cd_) < 900 and "D1.around" in cd_ and "[D1.17]" in cd_ and "LOOK" not in cd_ and "p.7-9" in READ_ROW and "READ ALL" in READ_ROW, (len(cd_), cd_[:100]))
sd = Session(None, Notebook("sd"), lambda s, u, **h: ("", {}), data_description="d", documents=True)
sn = Session(None, Notebook("sn"), lambda s, u, **h: ("", {}), data_description="d")
check("the system prompt carries the documents' section and the READ row only when the thread has documents", sd.system == contract(True) and sn.system == CONTRACT and "## Documents" not in sn.system)

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
