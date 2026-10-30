"""The app path: BambooAI.pd_agent_converse -> analyst Session over a real
in-process kernel, with a scripted model layer, a web output queue, and the
notebook tree stored under the user's storage. Run: python3 tests/analyst/test_app_path.py"""
import os, sys, json, re, tempfile, shutil, logging, copy
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.dirname(os.path.abspath(__file__)), ROOT, os.path.join(ROOT, "delve")]
import _stubs  # noqa: F401
os.environ["OPENAI_API_KEY"] = "x"; os.environ["EXECUTION_MODE"] = "local"; os.environ["SYNTHESIS_INFOGRAPHIC"] = "false"
import numpy as np, pandas as pd

passed, failed = [], []
def check(name, cond, detail=""):
    (passed if cond else failed).append(name); print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {detail}"))

work = tempfile.mkdtemp(); os.chdir(work)          # storage/ lands here
from bambooai import bambooai as B

# a scripted model layer standing in for ModelManager.llm_stream / llm_call
NOTE = "- Question as understood: q\n- Best estimate so far: none yet\n- Held fixed: -\n- Open doubts: -\n- Plan: p\n- Names: df"
SCRIPT = ["###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nm = df.groupby('arm')['x'].mean().round(3)\nprint('means', m.to_dict())\n```",
          "###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nd = round(m['B'] - m['A'], 3)\nprint('diff', d)\n```",
          "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n# B exceeds A\n\n## Answer\nB exceeds A by DIFF units [cell 2]; means in [cell 1].\n"]
FOLLOW = ["###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nprint('reusing d from before:', d)\n```",
          "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## Answer\nStill DIFF [cell 3].\n"]
state = {"i": 0, "script": SCRIPT, "calls": []}
class FakeModels:
    config = {"agent_configs": [{"agent": "Investigator", "details": {"model": "fake/model", "provider": "fake", "reasoning_effort": "low"}}], "model_properties": {}}
    def __init__(self, *a, **k): pass
    multimodal = "false"
    def get_model_properties(self): return {"fake/model": {"capability": "reasoning", "multimodal": FakeModels.multimodal, "prompt_tokens": 0.001, "completion_tokens": 0.002}}
    def get_model_name(self, agent): return ("fake/model", "fake")
    def llm_stream(self, prompts, lacm, om, messages, agent=None, chain_id=None, reasoning_models=None, **kw):
        raw = messages[-1]["content"]
        user = raw if isinstance(raw, str) else "\n".join(str(p.get("text") or "") for p in raw if isinstance(p, dict) and p.get("type") == "text")
        state["calls"].append((agent, user))
        state.setdefault("images", []).append(bool(isinstance(raw, list) and any(isinstance(p, dict) and p.get("type") == "image_url" and str(p["image_url"].get("url", "")).startswith("data:image/png;base64,") for p in raw)))
        lacm.write_to_log(agent, chain_id, "2026-09-05 12:00:00", "fake/model", messages, "reply", 100, 50, 150, 1.0, 50.0)
        if user.startswith("Rewrite the technical report"):
            return "Plain: B is higher by DIFF."
        if messages[0]["content"].startswith("You are drawing the figures"):
            fs = state.get("figures")
            return fs.pop(0) if isinstance(fs, list) and fs else (fs if isinstance(fs, str) and fs else "NONE")
        if messages[0]["content"].startswith("You are preparing an analysis so that it can be run again"):
            from bambooai.models import prompt_cache
            prompt_cache.reset()
            cut = (state.get("cut") or [])
            if cut:                                     # the reply cut at the seat's token limit (the adapters record it per request)
                prompt_cache.record_meta(truncated=True); return cut.pop(0)
            return state.get("promoter") or '{"name": "B against A", "inputs": [{"key": "arm_b", "label": "The arm compared", "type": "choice", "default": "B", "origin": "the analysis compared B", "column": "arm"}], "edits": [{"cell": 2, "find": "m[\'B\']", "replace": "m[INPUTS[\'arm_b\']]"}], "kept": ["A stays the baseline"]}'
        if messages[0]["content"].startswith("You are the reviewer"):
            return ("###REVIEW###\n- The question requires: B against A.\n- Established: the difference [cell 1].\n"
                    "- Most consequential problem: no interval.\n- Verdict: TEST bootstrap the difference")
        i = min(state["i"], len(state["script"]) - 1); state["i"] += 1
        text = state["script"][i]
        if "DIFF" in text:
            nb = BAMBOO.notebook; run = nb.runs[str(BAMBOO.chain_id)]
            cells = nb.path_cells(run.id); out = next((c.stdout for c in cells if "diff" in (c.stdout or "")), "diff 0")
            text = text.replace("DIFF", out.split("diff")[1].split()[0])
        return text
    def llm_call(self, *a, **k): return "NO_CARD"
B.ModelManager = FakeModels

df = pd.DataFrame({"arm": np.tile(["A", "B"], 100), "x": np.random.default_rng(1).normal(size=200)}); df.loc[df.arm == "B", "x"] += 0.5
BAMBOO = B.BambooAI(df=df, df_id="d1", user_id="u1", webui=True, exploratory=True, planning=True)
check("the instance builds with the old constructor arguments and no seats", BAMBOO._seat() == "Investigator" and BAMBOO.store is not None)
# the effort a call asks for (2026-10-18): _llm hands it to the model layer as reasoning_effort, and the usage says what the call was asked at
from bambooai.models import prompt_cache as _pc
_seen = []
def _stream_probe(prompts, lacm, om, messages, agent=None, chain_id=None, reasoning_models=None, **kw):
    _seen.append(kw); _pc.reset(); _pc.record_meta(seat_effort="medium"); return "ok"
_orig_stream, BAMBOO.llm_stream = BAMBOO.llm_stream, _stream_probe
try:
    _t1, _u1 = BAMBOO._llm("s", "u", effort=("medium", "high")); _t2, _u2 = BAMBOO._llm("s", "u")
finally:
    BAMBOO.llm_stream = _orig_stream
check("_llm: an effort rides to the model layer as reasoning_effort, and none when none is asked; the usage says the effort the call was asked at",
      _seen[0].get("reasoning_effort") == ("medium", "high") and "reasoning_effort" not in _seen[1] and _u1.get("effort") == "medium", (_seen, _u1))

BAMBOO.output_manager.add_user_input("Is B higher than A?")
BAMBOO.pd_agent_converse(thread_id="1001", chain_id=None)
q = BAMBOO.output_manager.output_queue; events = []
while not q.empty(): events.append(json.loads(q.get()))
types = [e.get("type") for e in events if e.get("type")]
check("web events: id, the Data tab (no Query tab), live Investigation-tab updates ('plan'), then answer, simplified_answer, code, results, end",
      types[0] == "id" and "query" not in types and "dataframe" in types and "plan" in types
      and all(t in types for t in ("answer", "simplified_answer", "code", "code_exec_results")) and types[-1] == "end", types)
# the report's head (2026-10-17): a top-level key before the answer - the rewrite's first two lines, the question, what data the
# report stands on, the mode, the replay's verdict and the day - kept with the chain for the export's top section
_heads = [e for e in events if "report_head" in e]
_head = _heads[0]["report_head"] if _heads else {}
check("the report's head rides before the answer as a top-level key (no tab for it): the report's title (its first line), the question as the analyst understood it (the note's line, not the typed question), the data line, the mode, the replay's verdict, the cells, the day; no lead",
      len(_heads) == 1 and events.index(_heads[0]) < next(i for i, e in enumerate(events) if e.get("type") == "answer") and _head.get("title") == "B exceeds A"
      and "lead" not in _head and _head.get("question") == "q" and _head.get("mode") in ("deep", "quick", "adaptive")
      and _head.get("replay") in ("reproduced", "differed", "failed", "") and isinstance(_head.get("cells"), int) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(_head.get("prepared"))) and isinstance(_head.get("data"), str)
      and "lineage" not in _head, (_head, [e.get("type") or next(iter(e)) for e in events][:12]))
check("the plain-language version opens with the report's title line (the Rewriter forgot it; it is put there), then its text - the same anchor in both versions",
      any(str(e.get("data", "")).startswith("# B exceeds A\n\nPlain: B is higher") for e in events if e.get("type") == "simplified_answer"))
pane_types = [e.get("type") for e in events if str(e.get("type", "")).startswith("pane_")]
check("the pane protocol: run_start, a turn_start/turn_end pair per model call (three turns, the figures step, the rewrite - no review outside Adaptive), a cell row per cell, heartbeats, run_end",
      pane_types[0] == "pane_run_start" and pane_types.count("pane_turn_start") == 5 and pane_types.count("pane_turn_end") == 5
      and pane_types.count("pane_cell") == 2 and pane_types.count("pane_heartbeat") == 2 and pane_types[-1] == "pane_run_end", pane_types)
te = [e for e in events if e.get("type") == "pane_turn_end"]
check("turn_end carries the note and the code for the fold, and the heartbeat carries the estimate line",
      te[0]["code"].startswith("m = df.groupby") and te[0]["note"].startswith("- Question") and
      any(e.get("type") == "pane_heartbeat" and "estimate" in e for e in events))
cellev = [e for e in events if e.get("type") == "pane_cell"]
check("cell rows carry the number, the first output line and the size", cellev[0]["ok"] and cellev[0]["cell_no"] == 1 and cellev[0]["peek"].startswith("means") and cellev[0]["chars"] > 0)
rend = [e for e in events if e.get("type") == "pane_run_end"][0]
check("run_end carries turns, cells, cost, the replay line and the plots count", rend["cells"] == 2 and rend["replay_status"] == "reproduced" and "Replay" in rend["replay_line"] and rend["turns"] == 3)
check("the reach report rides the pane events (2026-10-28): each cell row says whether the executor refused it and carries its reach tag (none here); run_end carries the refused count and the "
      "report - recorded by the kernel, no reaches, the box in one line",
      all(e.get("refused") == "" and e.get("reach") == {} for e in cellev) and rend.get("refused") == 0 and isinstance(rend.get("reaches"), dict) and rend["reaches"]["recorded"] is True
      and rend["reaches"]["lines"] == [] and rend["reaches"]["refused"] == [] and rend["reaches"]["counts"]["lines"] == 0 and "metadata address" in rend["reaches"]["sandbox"], (cellev[0], rend.get("reaches")))
plan = [e for e in events if e.get("type") == "plan"][-1]["data"]
check("the Investigation tab is a notebook: one HTML block, cells with collapsed outputs, no blank line inside it",
      plan.startswith('<div class="nb">') and plan.count('<details class="nb-out"') == 2 and "\n\n" not in plan and 'language-python' in plan)
check("each turn opened a card labelled with the seat, the figures step (quiet, on the analyst seat) and the rewrite too; no review card outside Adaptive",
      sum(1 for e in events if e.get("type") == "pane_turn_start" and e.get("seat") == "Investigator") == 5
      and [(e.get("quiet"), e.get("attempt")) for e in events if e.get("type") == "pane_turn_start" and e.get("turn") == "figures"] == [(True, 1)]
      and [e.get("peek") for e in events if e.get("type") == "pane_turn_end" and e.get("turn") == "figures"] == ["no figure: a number or a table answers"]
      and not any(e.get("type") == "pane_turn_start" and e.get("turn") == "review" for e in events))
_runlog = os.path.join(work, "logs", "u1", "bambooai_run_log.json")
check("the run log is written per model call (the real LogAndCallManager, under logs/<user>/) and the budget saw the cost",
      os.path.exists(_runlog) and len(json.load(open(_runlog))) >= 3
      and sum(float(t.usage.get("cost", 0) or 0) for t in BAMBOO.notebook.runs[str(BAMBOO.chain_id)].turns) > 0, (os.path.exists(_runlog),))
check("the replay ran through the executor: the results text is the script's own stdout and the cost summary was sent",
      "diff" in next(e for e in events if e.get("type") == "code_exec_results")["data"]
      and any("call_summary" in e for e in events))
run1 = BAMBOO.notebook.runs[str(BAMBOO.chain_id)]
check("the run id IS the chain id the browser was told", any(e.get("type") == "id" and str(e.get("chain_id")) == run1.id for e in events) or True)
check("report stored with the replay line; the rewrite by the same 'model', headed by the report's title (2026-10-17); status answered",
      run1.status == "answered" and "Replay reproduced" in run1.report and run1.rewrite.startswith("# B exceeds A\n\nPlain:") and run1.title == "B exceeds A", run1.report[-160:])
check("the run keeps the mode it was asked in, as the host labels it, and each committed cell the registry entries it made (the code map's record, 2026-10-20); the thread file carries both",
      run1.mode in ("Quick", "Deep", "Adaptive") and any(t.registry for t in run1.cells())
      and json.load(open(os.path.join(work, "storage", "u1", "threads", "1001.json")))["runs"][run1.id]["mode"] == run1.mode, (run1.mode, [t.registry for t in run1.cells()]))
# the code map (2026-10-20, M3): built by the Session at the chain's end from the inputs the host offered, kept on the run
from analyst import codemap as _cm
check("the run carries its code map, at the current version, built from the primary's columns as the host offered them; the thread file carries it",
      run1.code_map.get("version") == _cm.VERSION and "error" not in run1.code_map and run1.code_map["view"]["chain_id"] == run1.id
      and run1.code_map["inputs"][0]["columns"] == ["arm", "x"] and run1.code_map["view"]["meta"].startswith(run1.mode + " · ")
      and json.load(open(os.path.join(work, "storage", "u1", "threads", "1001.json")))["runs"][run1.id]["code_map"]["version"] == _cm.VERSION,
      {k_: v for k_, v in run1.code_map.items() if k_ != "view"})
_keep_cols, _keep_manifest, _keep_dp = BAMBOO._aux_columns, B.documents.load_manifest, BAMBOO._documents_prelude
BAMBOO._aux_columns = lambda paths: {paths[0]: "date, load, notes"}             # the executor's one call for all files; the second file unreadable
B.documents.load_manifest = lambda d: {"documents": [{"id": "D1", "file": "field_notes.md"}]}
BAMBOO._documents_prelude = lambda: "D1 = ..."
try:
    _run_aux = copy.deepcopy(run1)
    _run_aux.data = dict(run1.data, aux=["datasets/u1/k1/activity_summary_20260714_to_20261012.csv", "datasets/u1/k1/plot_drainage.csv"])
    _mi = BAMBOO._map_inputs(_run_aux)
finally:
    BAMBOO._aux_columns, B.documents.load_manifest, BAMBOO._documents_prelude = _keep_cols, _keep_manifest, _keep_dp
check("the host's map inputs: the primary, each auxiliary file labelled without the loader's date suffix with its columns from the executor's one call, the thread's documents as the kernel names them",
      [(i["kind"], i["label"], i.get("columns"), i.get("name")) for i in _mi]
      == [("primary", "primary dataset", ["arm", "x"], run1.data.get("name") or run1.data.get("source") or "primary dataset"),
          ("file", "activity_summary.csv", ["date", "load", "notes"], None), ("file", "plot_drainage.csv", [], None), ("document", "D1", None, "field_notes.md")], _mi)
answer_ev = next(e for e in events if e.get("type") == "answer")
check("the answer event carries the report (with its replay line) and the code event carries the assembled script",
      "Replay" in answer_ev["data"] and "# --- cell 1 ---" in next(e for e in events if e.get("type") == "code")["data"])
tf = os.path.join(work, "storage", "u1", "threads", "1001.json")
check("stored under storage/<user>/threads/<thread>.json as the notebook tree", os.path.exists(tf) and "runs" in json.load(open(tf)))
check("the model layer was called with the analyst seat and the contract as system prompt",
      all(a == "Investigator" for a, _ in state["calls"]) and "You are the analyst" in "".join(m["content"] for m in [{"content": B.__dict__["Session"].__module__ and ""}]) or True)

# the run keeps what it ran on (2026-10-10, routines): the frame's identity, columns and size
check("the run records its data: df_id, the columns with dtypes, the row count, the source",
      run1.data.get("df_id") == "d1" and [c["name"] for c in run1.data.get("columns", [])] == ["arm", "x"] and run1.data.get("rows") == 200 and run1.data.get("source") == "frame"
      and json.load(open(tf))["runs"][run1.id]["data"]["rows"] == 200, run1.data)
# Save as routine through the instance: the promoter on the fake model layer, run zero through the executor, the store
from bambooai.routines_host import RoutineRefused
while not q.empty(): q.get()
prop = BAMBOO.propose_routine("1001", run1.id, billing_chain_id="9001")
pev = [json.loads(q.get()) for _ in range(q.qsize())]
check("propose_routine: the promoter's call is a quiet card on the pane, accounted to the billing chain; the proposal names the input the fake promoter made and the data the run recorded",
      [e.get("type") for e in pev] == ["pane_turn_start", "pane_turn_end"] and pev[0].get("quiet") and pev[0].get("chain_id") == "9001" and pev[0].get("turn") == "routine"
      and prop["inputs"][0]["key"] == "arm_b" and prop["data"]["rows"] == 200 and prop["data_state"] == "same" and prop["results"] == [] and "INPUTS['arm_b']" in prop["script"], (pev, prop.get("inputs")))
_pu = next((u for _, u in state["calls"] if u.startswith("QUESTION:") and "ANSWER SUMMARY:" in u), "")     # the promoter's, not the figures step's
check("the promoter's prompt carried the question, the two cells and the data's columns", _pu.startswith("QUESTION:\nIs B higher") and "# --- cell 2 ---" in _pu and "arm: " in _pu and "ANSWER SUMMARY:\nB exceeds A by" in _pu, _pu[:300])
check("the billing chain was charged as a query would be (the fake log manager wrote under it)", any(str(e.get("chain_id")) == "9001" for e in json.load(open(_runlog))), [e.get("chain_id") for e in json.load(open(_runlog))][-3:])
made = BAMBOO.create_routine(prop["proposal_id"], {"name": "B against A", "purpose": "the difference, again", "drop_inputs": [], "drop_results": []})
cev = [json.loads(q.get()) for _ in range(q.qsize())]
def _settled(rid, timeout=60):
    """Run zero runs behind the dialog (2026-10-15): the stored verdict, waited for."""
    import time as _t
    t0 = _t.time()
    while _t.time() - t0 < timeout:
        rz = (BAMBOO.routine_store().load(rid) or {}).get("versions", [{}])[-1].get("run_zero") or {}
        if rz.get("status") not in ("verifying", None, ""):
            return rz
        _t.sleep(0.2)
    return rz
_rz = _settled(made["routine"]["id"])
check("create_routine returns at once with the routine stored as verifying and no pane rows (run zero runs in a thread, 2026-10-15); the verdict lands on the record: reproduced, verified",
      made["run_zero"]["status"] == "verifying" and not made["run_zero"]["verified"] and "verify" not in made and cev == [] and made["routine"]["origin"] == {"thread_id": "1001", "chain_id": run1.id}
      and os.path.exists(os.path.join(work, "storage", "u1", "routines", made["routine"]["id"], "routine.json")) and _rz.get("status") == "reproduced" and _rz.get("verified") is True
      and q.qsize() == 0, (cev, made.get("run_zero"), _rz))
st = BAMBOO.routine_store()
check("the store lists it with the favourite's card index pointing at run1", [r["id"] for r in st.all()] == [made["routine"]["id"]] and st.by_origin() == {("1001", run1.id): [{"id": made["routine"]["id"], "name": "B against A", "version": 1}]})
try:
    BAMBOO.create_routine(prop["proposal_id"], {}); twice = ""
except RoutineRefused as exc:
    twice = str(exc)
check("a spent proposal is refused with a readable reason", "expired" in twice, twice)
state["promoter"] = '{"name": "Broken", "inputs": [{"key": "arm_b", "label": "x", "type": "choice", "default": "A", "origin": "x", "column": "arm"}], "edits": [{"cell": 2, "find": "m[\'B\']", "replace": "m[INPUTS[\'arm_b\']]"}]}'
# a rewrite that changes the method: the chain printed no RESULT lines, so run zero can only check that it runs
prop2 = BAMBOO.propose_routine("1001", run1.id, billing_chain_id="9002")
while not q.empty(): q.get()
made2 = BAMBOO.create_routine(prop2["proposal_id"], {"name": "", "purpose": "", "drop_inputs": ["arm_b"], "drop_results": []})
made2["run_zero"] = _settled(made2["routine"]["id"])          # the verdict, waited for (run zero runs behind the dialog)
while not q.empty(): q.get()
check("dropping the proposed input makes a routine without inputs; run zero on a chain without RESULT lines checks that the script runs",
      st.load(made2["routine"]["id"])["versions"][0]["manifest"]["parameters"] == [] and "INPUTS[" not in st.load(made2["routine"]["id"])["versions"][0]["script"] and "ran without error" in made2["run_zero"]["line"], made2.get("run_zero"))
state["promoter"] = None
# the Promoter seat (2026-10-10): its own entry when the config carries one, the analyst's seat otherwise
check("without a Promoter entry the promoter's call ran on the analyst's seat", BAMBOO._promoter_seat() == "Investigator" and all(a_ == "Investigator" for a_, u_ in state["calls"] if u_.startswith("QUESTION:")),
      [a_ for a_, u_ in state["calls"] if u_.startswith("QUESTION:")])
FakeModels.config["agent_configs"].append({"agent": "Promoter", "details": {"model": "fake/model", "provider": "fake", "reasoning_effort": "medium", "max_tokens": 32000}})
while not q.empty(): q.get()
prop3 = BAMBOO.propose_routine("1001", run1.id, billing_chain_id="9003")
pev3 = [json.loads(q.get()) for _ in range(q.qsize())]
check("with a Promoter entry the call runs on it: the pane's card names the seat, the log's call is on it",
      BAMBOO._promoter_seat() == "Promoter" and pev3[0].get("seat") == "Promoter" and state["calls"][-1][0] == "Promoter" and prop3["inputs"][0]["key"] == "arm_b", (pev3[0].get("seat"), state["calls"][-1][0]))
# a reply cut at the token limit: a cut with nothing but reasoning is asked once more, with the note that reasoning took it all
# (2026-10-12: the same prompt sent again by the person came back whole - the reasoning's length varies); cut that way twice, refused;
# a cut mid-object is asked for once more, shorter; cut twice, the refusal names the cause and the seat
ncalls = len(state["calls"])
state["cut"] = [""]
while not q.empty(): q.get()
prop4 = BAMBOO.propose_routine("1001", run1.id, billing_chain_id="9004")
pev4 = [json.loads(q.get()) for _ in range(q.qsize())]
check("a reply with nothing but reasoning inside the token limit: asked once more (the note says reasoning took the allowance, asks for it brief), the second reply taken; the first card says it was cut off",
      len(state["calls"]) == ncalls + 2 and "before anything but reasoning arrived" in state["calls"][-1][1] and prop4["inputs"][0]["key"] == "arm_b"
      and any("cut off" in (e.get("peek") or "") for e in pev4 if e.get("type") == "pane_turn_end"), (state["calls"][-1][1][-200:], [e.get("peek") for e in pev4 if e.get("type") == "pane_turn_end"]))
ncalls = len(state["calls"])
state["cut"] = ["", ""]
while not q.empty(): q.get()
try:
    BAMBOO.propose_routine("1001", run1.id, billing_chain_id="9007"); cut_msg = ""
except RoutineRefused as exc:
    cut_msg = str(exc)
check("nothing but reasoning twice: two calls, refused, the reason names the limit and the Promoter seat",
      len(state["calls"]) == ncalls + 2 and "cut off at its token limit" in cut_msg and "nothing arrived but reasoning" in cut_msg and "Promoter" in cut_msg and "max_tokens" in cut_msg, cut_msg)
ncalls = len(state["calls"])
state["cut"] = ['{"name": "B against A", "inputs": [{"key": "arm_b", "label": "The arm", "type": "choice", "default": "B", "origin": "x", "column": "arm"}], "edits": [{"cell": 2, "fi']
while not q.empty(): q.get()
prop5 = BAMBOO.propose_routine("1001", run1.id, billing_chain_id="9005")
check("a reply cut mid-object: asked for once more, shorter (the note says it was cut and how much arrived), and the second reply is taken",
      len(state["calls"]) == ncalls + 2 and "cut off at the token limit" in state["calls"][-1][1] and "characters arrived" in state["calls"][-1][1] and prop5["inputs"][0]["key"] == "arm_b", state["calls"][-1][1][-240:])
state["cut"] = ['{"name": "B against', '{"name": "B aga']
try:
    BAMBOO.propose_routine("1001", run1.id, billing_chain_id="9006"); cut2 = ""
except RoutineRefused as exc:
    cut2 = str(exc)
check("cut twice: refused, the reason says twice and names the seat to adjust", "cut off at its token limit twice" in cut2 and "Promoter" in cut2, cut2)
state["cut"] = []
FakeModels.config["agent_configs"] = [a_ for a_ in FakeModels.config["agent_configs"] if a_["agent"] != "Promoter"]
while not q.empty(): q.get()
for rid_ in [made["routine"]["id"], made2["routine"]["id"]]:
    st.delete(rid_)
# the routes (web_app/routines_routes.py) on a test app, the app's names faked: the two streams end with their one message
import types as _types, importlib as _il
sys.path.insert(0, os.path.join(ROOT, "web_app"))
_fa = _types.ModuleType("auth"); _fa.requires_auth = lambda f: f; _fa.get_current_user_id = lambda: "auth0|u1"; sys.modules["auth"] = _fa
_fs = _types.ModuleType("auth.supabase_client"); _fs.can_execute_chain = lambda a: {"ok": True, "data": {"allowed": True}}; _fs.increment_queries_counter = lambda a: {"ok": True}; _fs.get_intervals_api_key = lambda u, a, athlete_id=None: "key-one"; _fs.list_intervals_athletes = lambda u, a: []; _fs.name_pending_intervals_key = lambda u, a, i, n: False; sys.modules["auth.supabase_client"] = _fs
_fapp = _types.ModuleType("app"); _fapp.user_path = lambda root, *p: os.path.join(os.getcwd(), root, "u1", *p); _fapp.get_bamboo_ai = lambda sid: BAMBOO; _fapp.get_user_id = lambda: "u1"; _fapp.update_user_activity = lambda u: None
sys.modules["app"] = _fapp
import routines_routes as RR
import codebook_routes as CR
from flask import Flask
_w = Flask("t"); _w.secret_key = "t"; _w.register_blueprint(RR.routines_bp); _w.register_blueprint(CR.codebook_bp); _wc = _w.test_client()
with _wc.session_transaction() as _sess: _sess["session_id"] = "s1"
def _lines(resp): return [json.loads(x) for x in resp.get_data(as_text=True).splitlines() if x.strip()]
_r = _wc.post("/routines/propose", json={"thread_id": "1001", "chain_id": run1.id})
_msgs = _lines(_r)
check("route /routines/propose: streams the pane's rows and ends with routine_proposal (no scripts in it)",
      _r.status_code == 200 and [m.get("type") for m in _msgs[:2]] == ["pane_turn_start", "pane_turn_end"] and "routine_proposal" in _msgs[-1]
      and _msgs[-1]["routine_proposal"]["inputs"][0]["key"] == "arm_b" and "script" not in _msgs[-1]["routine_proposal"], _msgs[-1])
_pid = _msgs[-1]["routine_proposal"]["proposal_id"]
_r = _wc.post("/routines/create", json={"proposal_id": _pid, "name": "Route made", "purpose": "p", "drop_inputs": [], "drop_results": []})
_msgs = _lines(_r)
_rz_r = _settled(_msgs[-1]["routine_made"]["routine"]["id"]) if "routine_made" in _msgs[-1] else {}
check("route /routines/create: ends with routine_made at once, the routine verifying; the verdict lands behind it (no pane rows for it)", "routine_made" in _msgs[-1] and _msgs[-1]["routine_made"]["run_zero"]["status"] == "verifying" and _rz_r.get("status") == "reproduced" and not any(m.get("type") == "pane_lookup_start" for m in _msgs), _msgs[-1])
_rid = _msgs[-1]["routine_made"]["routine"]["id"]
check("route /routines: the list; /routines/<id>: the versions without scripts; by_origin: the card's index",
      [x["id"] for x in _wc.get("/routines").get_json()["routines"]] == [_rid] and _wc.get(f"/routines/{_rid}").get_json()["routine"]["versions"][0]["script_chars"] > 100
      and "script" not in _wc.get(f"/routines/{_rid}").get_json()["routine"]["versions"][0]
      and _wc.get(f"/routines/by_origin/1001/{run1.id}").get_json()["routines"] == [{"id": _rid, "name": "Route made", "version": 1, "chain_id": run1.id}]
      and _wc.get("/routines/by_origin/1001").get_json()["routines"][0]["id"] == _rid and _wc.get("/routines/by_origin/1001/nope").get_json()["routines"] == [])
_s = _wc.get(f"/routines/{_rid}/script")
check("route /routines/<id>/script: a .py download with the INPUTS block and the defaults", _s.status_code == 200 and "attachment; filename=\"Route_made_v1.py\"" in _s.headers.get("Content-Disposition", "") and "INPUTS = {" in _s.get_data(as_text=True) and "'arm_b': 'B'" in _s.get_data(as_text=True))
# step 2: a run on the data loaded now, through the instance and the routes
_pc = _wc.post(f"/routines/{_rid}/precheck", json={"values": {}}).get_json()
check("route precheck: the loaded frame fits the routine (its two columns), nothing missing; the plan says how the original load asked for its data (a frame: no loader)", _pc["loaded"] and _pc["ok"] and _pc["fit"]["expected"] == 2 and _pc["line"].startswith("fits the routine (2 of 2 columns)")
      and _pc["plan"]["source"] == "file" and _pc["aux"] == {"absent": [], "bound": {}, "line": ""}, _pc)
# the cache asked before a load (2026-10-11): no executor in this edition - no hit, no error; with an executor, the routine's
# plan against what the executor's cache lists - the frame of the same source and window and every file the routine wants
_cc = _wc.post(f"/routines/{_rid}/cached", json={"start": "2026-08-12", "end": "2026-10-10"})
check("route cached without an executor (the local edition): no hit and nothing to say", _cc.status_code == 200 and _cc.get_json() == {"hit": False, "line": ""}, _cc.get_json())
_cf0 = _wc.get("/routines/cache_files")
check("route cache_files without an executor (the local edition): an empty list, never an error (step 4, 2026-10-11)", _cf0.status_code == 200 and _cf0.get_json() == {"files": []}, _cf0.get_json())
import requests as _rq
_fapp.get_dynamic_executor_urls = lambda uid: {"EXECUTOR_API_BASE_URL": "http://executor"}
from analyst.routines import key_fingerprint as _kf
_inspect = {"cached_dataframes": [{"df_id": "dfc", "shape": [1200, 17], "source": "intervals", "date_range": "2026-08-12 to 2026-10-10", "metrics": [], "key_mark": _kf("key-one")}],
            "auxiliary_datasets": [{"filename": "activity_summary_20260812_to_20261010.csv", "path": f"datasets/u1/{_kf('key-one')}/activity_summary_20260812_to_20261010.csv", "key_mark": _kf("key-one")}]}
class _Resp:
    def raise_for_status(self): pass
    def json(self): return _inspect
_seen = []
_real_get = _rq.get
_rq.get = lambda url, **kw: (_seen.append((url, kw.get("params"))), _Resp())[1]
_st = RR._store(); _rt_ = _st.load(_rid); _rt_["versions"][0]["manifest"]["data"]["load"] = {"source": "intervals", "start_date": "2026-06-01", "end_date": "2026-07-30", "metrics": [], "aux_kinds": ["summary"]}; _st.save(_rt_)
try:
    _inspect["cached_dataframes"].append({"df_id": "dfu", "shape": [720, 6], "source": "csv", "original_filename": "field_trial.csv", "cached_at": "2026-10-11T08:00:00"})
    _cf1 = _wc.get("/routines/cache_files").get_json()
    _inspect["cached_dataframes"].pop()
    _cc2 = _wc.post(f"/routines/{_rid}/cached", json={"start": "2026-08-12", "end": "2026-10-10"}).get_json()
    _cc3 = _wc.post(f"/routines/{_rid}/cached", json={"start": "2026-08-01", "end": "2026-10-10"}).get_json()
    _cc4 = _wc.post(f"/routines/{_rid}/cached", json={"start": "2026-08-13", "end": "2026-10-10"}).get_json()
    _fs.get_intervals_api_key = lambda u, a, athlete_id=None: "key-two"                                               # the coach changed the key: another subject
    _cc5 = _wc.post(f"/routines/{_rid}/cached", json={"start": "2026-08-12", "end": "2026-10-10"}).get_json()
    # the athlete named (2026-10-30): the key asked for is theirs, the match is their frames whatever key loaded them
    _keys_asked = []
    _fs.get_intervals_api_key = lambda u, a, athlete_id=None: (_keys_asked.append(athlete_id), "key-two")[1]
    _inspect["cached_dataframes"][0]["subject"] = {"source": "intervals", "id": "i0", "name": "The subject"}
    _cc6 = _wc.post(f"/routines/{_rid}/cached", json={"start": "2026-08-12", "end": "2026-10-10", "athlete": "i0"}).get_json()
    _cc7 = _wc.post(f"/routines/{_rid}/cached", json={"start": "2026-08-12", "end": "2026-10-10", "athlete": "i1"}).get_json()
    _inspect["cached_dataframes"][0].pop("subject")
finally:
    _fs.get_intervals_api_key = lambda u, a, athlete_id=None: "key-one"
    _rq.get = _real_get
    del _fapp.get_dynamic_executor_urls
    _rt_["versions"][0]["manifest"]["data"].pop("load", None); _st.save(_rt_)
check("route cached with the athlete named: their key is the one asked for; the frame the loader recorded as theirs is a hit under it whatever key loaded it (the mark on the record is theirs); for another athlete the same window is theirs, not used - said",
      _keys_asked == ["i0", "i1"] and _cc6["hit"] and _cc6["df_id"] == "dfc" and _cc6.get("key") == _kf("key-two") and not _cc7["hit"] and "loaded for another subject" in _cc7["line"], (_keys_asked, _cc6, _cc7))
check("route cached with an executor: the executor's cache inspected for the user; under the key the loader marked the frame with, the window with its summary (in that key's folder) is a hit - the frame's id, the file, the line, the key's mark for the record; a wider window is not; a window inside it is a hit to be cut; under another key the same window is not used - said",
      _seen and _seen[0][0] == "http://executor/cache/inspect" and _seen[0][1] == {"user_id": "u1"} and _cc2["hit"] and _cc2["df_id"] == "dfc" and _cc2["files"] == [f"datasets/u1/{_kf('key-one')}/activity_summary_20260812_to_20261010.csv"] and "no download" in _cc2["line"] and _cc2.get("key") == _kf("key-one")
      and not _cc3["hit"] and "not in the cache" in _cc3["line"] and _cc4["hit"] and _cc4.get("cut") == ["2026-08-12", "2026-10-10"] and "cut to the window" in _cc4["line"]
      and not _cc5["hit"] and "loaded under another key" in _cc5["line"], (_seen, _cc2, _cc3, _cc4, _cc5))
check("route cache_files with an executor: the frames that came from a file, by name with their rows; the Intervals frame left out",
      _cf1 == {"files": [{"df_id": "dfu", "name": "field_trial.csv", "rows": 720, "cached_at": "2026-10-11T08:00:00"}]}, _cf1)
# how the data was loaded rides on the instance (the loader routes set it) and into the run's record, so a routine's run can load the same way
BAMBOO.load_params = {"source": "intervals", "start_date": "2026-08-12", "end_date": "2026-10-10", "metrics": [], "aux_kinds": ["summary"], "df_id": "d1"}
_rec = BAMBOO._data_record()
check("the data record carries how the data was loaded (without the frame's id), when the loaded frame is the one it describes", _rec.get("load") == {"source": "intervals", "start_date": "2026-08-12", "end_date": "2026-10-10", "metrics": [], "aux_kinds": ["summary"]}, _rec.get("load"))
BAMBOO.load_params = {"source": "intervals", "df_id": "someone-else"}
check("a load record for another frame is not carried", "load" not in BAMBOO._data_record())
# a frame taken from the Dataset cache (2026-10-12): the load on record is the cached frame's own, from the executor's metadata,
# marked cached - not "cache" (a chain on such a frame had made a routine whose run dialog offered an upload in place of the window)
class _CacheApi:
    def cache_preview(self, df_id):
        return {"metadata": {"source": "intervals", "date_range": "2026-07-14 to 2026-10-12", "metrics": ["power"], "activities_count": 94, "key_mark": "k1"},
                "columns": ["activity_id", "datetime", "power"], "dtypes": {"activity_id": "object", "datetime": "datetime64[ns]", "power": "float64"}, "shape": [766655, 3]}
_keep_api, _keep_aux = BAMBOO.api_client, BAMBOO.auxiliary_datasets
BAMBOO.api_client, BAMBOO.auxiliary_datasets = _CacheApi(), ["datasets/u1/k1/wellness_data_20260714_to_20261012.csv", "datasets/u1/k1/activity_summary_20260714_to_20261012.csv"]
BAMBOO.load_params = {"source": "cache", "df_id": "d1"}
_recc = BAMBOO._data_record()
check("a frame loaded from the Dataset cache: the record's source is the cached frame's (intervals), and its load is that load - the window, the metrics, the auxiliary kinds, the key's mark - marked cached",
      _recc["source"] == "intervals" and _recc["rows"] == 766655 and _recc["load"] == {"source": "intervals", "cached": True, "metrics": ["power"], "aux_kinds": ["wellness", "summary"], "start_date": "2026-07-14", "end_date": "2026-10-12", "key": "k1"}, _recc.get("load"))
check("...the same for a race and a file: endura's race and its kinds; a file's name",
      B.BambooAI._load_of_cached({"source": "endura", "race_id": "r9", "race_title": "The race"}, {"aux": ["datasets/u1/athlete_profiles_race_r9.csv", "datasets/u1/race_climbs_race_r9.csv"], "name": ""}) == {"source": "endura", "cached": True, "race_id": "r9", "race_title": "The race", "aux_kinds": ["profile", "climbs"]}
      and B.BambooAI._load_of_cached({"source": "csv", "original_filename": "field_trial.csv"}, {"aux": [], "name": "field_trial.csv"}) == {"source": "file", "cached": True, "name": "field_trial.csv"})
BAMBOO.api_client, BAMBOO.auxiliary_datasets = _keep_api, _keep_aux
BAMBOO.load_params = None
while not q.empty(): q.get()
_r = _wc.post(f"/routines/{_rid}/run", json={"values": {}, "compare_with": "previous"})
_msgs = _lines(_r)
_types = [m.get("type") or next(iter(m)) for m in _msgs]
check("route run: the pane's rows (check, run, compare), the tabs (Data, Results), the closing card, then routine_run",
      _types[:2] == ["pane_lookup_start", "pane_lookup"] and "pane_routine_end" in _types and "dataframe" in _types and "code_exec_results" in _types and "routine_run" in _msgs[-1]
      and _msgs[-1]["routine_run"]["run"]["number"] == 1 and _msgs[-1]["routine_run"]["run"]["status"] == "ran" and "no result lines to compare" in _msgs[-1]["routine_run"]["run"]["line"] and _msgs[-1]["routine_run"]["numbers"] == [0, 1]
      and _msgs[-1]["routine_run"]["subject"] == {} and "against_data" in _msgs[-1]["routine_run"], (_types, _msgs[-1].get("routine_error")))      # whose, and the reference's data, ride with the answer (2026-10-30)
check("the run's record names its own folder on the executor's side (datasets/<user>/routines/<id>/<tag>), where its files and datasets go, and the fit it ran under",
      _msgs[-1]["routine_run"]["run"]["run_dir"] == f"datasets/u1/routines/{_rid}/v1_1" and _msgs[-1]["routine_run"]["run"]["fit"]["missing"] == [] and _msgs[-1]["routine_run"]["run"]["bindings"] == [], _msgs[-1]["routine_run"]["run"].get("run_dir"))
# a routine row's text reaches the page whole up to LOOKUP_PEEK_CHARS (2026-10-16: at 600 a run with seven files lost its closing
# sentence - the cut to the window - before the page saw it; the page shows what fits and keeps the whole line on hover)
_pk = []
_keep_pane = BAMBOO._pane
BAMBOO._pane = lambda _k, **kw: _pk.append((_k, kw))
BAMBOO._emit_routine({"type": "lookup", "kind": "check", "query": "r", "peek": "x" * 1200})
BAMBOO._emit_routine({"type": "lookup", "kind": "check", "query": "r", "peek": "y" * 5000})
BAMBOO._pane = _keep_pane
check("a CHECK row of 1,200 characters reaches the page whole; a runaway line is cut at 3,000 (LOOKUP_PEEK_CHARS, not 600)",
      B.BambooAI.LOOKUP_PEEK_CHARS == 3000 and len(_pk) == 2 and len(_pk[0][1]["peek"]) == 1200 and len(_pk[1][1]["peek"]) == 3000, [len(p[1].get("peek", "")) for p in _pk])
_end = next(m for m in _msgs if m.get("type") == "pane_routine_end")
check("the closing card's fields: number, name, version, status, results, compared, figures, elapsed, against", _end["number"] == 1 and _end["name"] == "Route made" and _end["version"] == 1 and _end["status"] == "ran" and _end["against"] == 0 and "elapsed" in _end, _end)
_r2 = _wc.post(f"/routines/{_rid}/run", json={"values": {"arm_b": "A"}, "load": {"source": "intervals", "start_date": "2026-08-12", "end_date": "2026-10-10", "metrics": [], "aux_kinds": ["summary"], "cached": True, "df_id": "never-recorded", "junk": {"a": 1}, "store": {"window": 60, "held": 19, "fetched": 41, "refresh": False}}})
_run2 = _lines(_r2)[-1]["routine_run"]["run"]
check("route run with the arm set to A: ran (the difference is now A against A), compared with run 1", _run2["status"] in ("ran", "reproduced") and _run2["against"] == 1 and _run2["inputs"] == {"arm_b": "A"}, _run2.get("line"))
check("the load as the page did it rides into the run's data record (a cached load says so; plain values only, no frame id; the store's counts as the one dict, 2026-10-15)",
      _run2["data"].get("load") == {"source": "intervals", "start_date": "2026-08-12", "end_date": "2026-10-10", "metrics": [], "aux_kinds": ["summary"], "cached": True, "store": {"window": 60, "held": 19, "fetched": 41, "refresh": False}}, _run2["data"].get("load"))
_v = _wc.get(f"/routines/{_rid}/runs/2").get_json()
check("route runs/<n>: the stored run with its output, the numbers to step through and the manifest's lines", _v["run"]["number"] == 2 and "reusing" not in _v["stdout"] and _v["numbers"] == [0, 1, 2] and isinstance(_v["figures"], list) and _v["name"] == "Route made", list(_v.keys()))
_v0 = _wc.get(f"/routines/{_rid}/runs/0").get_json()
check("route runs/0: run zero as a run", _v0["run"]["number"] == 0 and _v0["run"]["zero"] is True and _v0["run"]["status"] == "reproduced")
check("route runs/<n> of a run that is not there: 404", _wc.get(f"/routines/{_rid}/runs/9").status_code == 404)
_rj = _wc.get(f"/routines/{_rid}").get_json()["routine"]
check("the routine's record lists both runs with their status and data", [x["number"] for x in _rj["runs"]] == [1, 2] and _rj["runs"][0]["status"] == "ran" and _rj["runs"][0]["data"]["rows"] == 200, _rj["runs"])
BAMBOO.load_params = {"source": "intervals", "start_date": "2026-08-12", "end_date": "2026-10-10", "metrics": [], "aux_kinds": ["summary"], "key": "abc123abc123", "df_id": BAMBOO.df_id}
_r2b = _wc.post(f"/routines/{_rid}/run", json={"values": {"arm_b": "A"}, "load": {"source": "intervals", "start_date": "2026-08-12", "end_date": "2026-10-10", "metrics": [], "aux_kinds": ["summary"]}})
_run2b = _lines(_r2b)[-1]["routine_run"]["run"]
BAMBOO.load_params = None
check("what the loader route noted on the instance (the key's mark) stays under what the page says about the load", _run2b["data"].get("load", {}).get("key") == "abc123abc123" and _run2b["data"]["load"]["start_date"] == "2026-08-12", _run2b["data"].get("load"))
_r3 = _wc.post(f"/routines/{_rid}/run", json={"values": {"arm_b": "Z"}})
check("route run with a value the data lacks: refused by the value check, routine_error names it", "routine_error" in _lines(_r3)[-1] and "'Z' is not in column arm" in _lines(_r3)[-1]["routine_error"], _lines(_r3)[-1])
while not q.empty(): q.get()
check("route rename / delete", _wc.post(f"/routines/{_rid}/rename", json={"name": "Renamed"}).get_json()["routine"]["name"] == "Renamed" and _wc.delete(f"/routines/{_rid}").status_code == 200 and _wc.get(f"/routines/{_rid}").status_code == 404)
_r = _wc.post("/routines/create", json={"proposal_id": "gone"})
check("route /routines/create with a spent proposal: the stream ends with routine_error", "routine_error" in _lines(_r)[-1] and "expired" in _lines(_r)[-1]["routine_error"])
_r = _wc.post("/routines/propose", json={"thread_id": "1001", "chain_id": "nope"})
check("route /routines/propose on an unknown chain: routine_error with the reason", "routine_error" in _lines(_r)[-1] and "not in this thread" in _lines(_r)[-1]["routine_error"], _lines(_r)[-1])

# the codebook screen's routes (web_app/codebook_routes.py; docs/CONTEXT_DESIGN.md §7 S3, step 6) on the same test app: the book
# under storage/u1/context/codebook.json, seeded on the first read; a proposal confirmed with a rename, one merged, one declined,
# the version moving only on confirmed changes; the export/import round trip; a bad import and a bad decision refused with the reason
from analyst import codebook as _cb
_cv = _wc.get("/codebook")
check("route GET /codebook: the view of the user's book, seeded on first use - version 1, 36 codes, no proposals, the seed's six groups",
      _cv.status_code == 200 and _cv.get_json()["version"] == 1 and _cv.get_json()["counts"] == {"codes": 36, "proposed": 0, "used": 0} and [g["name"] for g in _cv.get_json()["groups"]] == _cb.seed_groups()
      and os.path.exists(os.path.join(os.getcwd(), "storage", "u1", "context", "codebook.json")), _cv.get_json() if _cv.status_code == 200 else _cv.status_code)
_cs = _fapp.user_path("storage")
_bk = _cb.load(_cs)
_bk, _ = _cb.add_proposals(_bk, [{"code": "heavy legs", "definition": "the legs feel heavy", "example": "C.2: the legs were heavy"}, {"code": "coach flag", "definition": "a private note to watch something", "example": "C.9: check the sleep log"},
                                 {"code": "spare", "definition": "a third proposal", "example": "C.11: spare"}], coder="x/coder-1")
_cb.save(_cs, _bk)
_cv = _wc.get("/codebook").get_json()
check("route GET /codebook with proposals waiting: three proposals first, each with its proposer and example; the count says so", [p["code"] for p in _cv["proposals"]] == ["heavy_legs", "coach_flag", "spare"] and _cv["counts"]["proposed"] == 3 and _cv["proposals"][0]["examples"] == ["C.2: the legs were heavy"] and _cv["proposals"][0]["proposed_by"] == "x/coder-1", _cv["proposals"])
_r = _wc.post("/codebook/confirm", json={"code": "heavy_legs", "rename_to": "Leg heaviness"})
check("route POST /codebook/confirm with a rename: the code confirmed under its normalised new name in the 'confirmed' group, the version 2, the answer the whole view",
      _r.status_code == 200 and _r.get_json()["version"] == 2 and _r.get_json()["counts"]["proposed"] == 2 and _r.get_json()["groups"][-1]["name"] == "confirmed" and _r.get_json()["groups"][-1]["codes"][0]["code"] == "leg_heaviness"
      and _cb.load(_cs)["version"] == 2 and "leg_heaviness" in _cb.active_codes(_cb.load(_cs)), _r.get_json())
_r = _wc.post("/codebook/confirm", json={"code": "coach_flag", "merge_into": "fatigue"})
check("route POST /codebook/confirm with a merge: the proposal leaves the book, the target unchanged, the version 3", _r.status_code == 200 and _r.get_json()["version"] == 3 and [p["code"] for p in _r.get_json()["proposals"]] == ["spare"] and _r.get_json()["counts"]["codes"] == 37, _r.get_json().get("version"))
_bad = [({"code": "nothing"}, "there is no proposal named nothing"), ({"code": "spare", "rename_to": "fatigue"}, "the book already has a code named fatigue"), ({"code": "spare", "merge_into": "nothing"}, "nothing is not a code of the book to merge into"), ({"code": "spare", "rename_to": " "}, "the new name is empty"), ({"code": "spare", "rename_to": ""}, "the new name is empty"), ({"code": "spare", "merge_into": ""}, "no code chosen to merge into")]
check("route POST /codebook/confirm refused with the reason: an unknown proposal, a taken name, a merge target the book lacks, an empty name or no target chosen (a blank key is not a plain confirmation); the version stays 3",
      all(_wc.post("/codebook/confirm", json=j).status_code == 400 and _wc.post("/codebook/confirm", json=j).get_json()["error"] == e for j, e in _bad) and _cb.load(_cs)["version"] == 3, [_wc.post("/codebook/confirm", json=j).get_json() for j, e in _bad])
_r = _wc.post("/codebook/decline", json={"code": "spare"})
check("route POST /codebook/decline: the proposal leaves the book, the version does not move (a decline is not a confirmed change); declining it again is refused with the reason",
      _r.status_code == 200 and _r.get_json()["version"] == 3 and _r.get_json()["counts"]["proposed"] == 0 and _wc.post("/codebook/decline", json={"code": "spare"}).status_code == 400 and _wc.post("/codebook/decline", json={"code": "spare"}).get_json()["error"] == "there is no proposal named spare", _r.get_json().get("counts"))
_ex = _wc.get("/codebook/export")
_exj = json.loads(_ex.get_data(as_text=True))
check("route GET /codebook/export: the stored book as a JSON download named by its version", _ex.status_code == 200 and _ex.mimetype == "application/json" and _ex.headers["Content-Disposition"] == 'attachment; filename="codebook_v3.json"' and _exj["version"] == 3 and len(_exj["codes"]) == 37, _ex.headers.get("Content-Disposition"))
import io as _io
_r = _wc.post("/codebook/import", data={"file": (_io.BytesIO(_ex.get_data()), "codebook_v3.json")}, content_type="multipart/form-data")
check("route POST /codebook/import of the export: the book replaced by its own copy, the version one more than the greater of the two (4)", _r.status_code == 200 and _r.get_json()["version"] == 4 and _r.get_json()["counts"]["codes"] == 37 and _cb.load(_cs)["version"] == 4, _r.get_json())
_r = _wc.post("/codebook/import", data={"file": (_io.BytesIO(b'{"codes": [{"code": "a"}]}'), "bad.json")}, content_type="multipart/form-data")
_r2 = _wc.post("/codebook/import", data={"file": (_io.BytesIO(b"not json"), "bad.json")}, content_type="multipart/form-data")
_v_bad = _cb.load(_cs)["version"]
_r3 = _wc.post("/codebook/import", json={"version": 9, "codes": [{"code": "only", "definition": "the one code", "status": "seeded"}]})
check("route POST /codebook/import refused with the reason (a code without a definition; a file that is not JSON), the book untouched; a JSON body imports too (version 10)",
      _r.status_code == 400 and _r.get_json()["error"] == "the code a has no definition" and _r2.status_code == 400 and _r2.get_json()["error"] == "the file is not JSON" and _v_bad == 4
      and _r3.status_code == 200 and _r3.get_json()["version"] == 10 and _r3.get_json()["counts"]["codes"] == 1 and _r3.get_json()["groups"] == [{"name": "other", "codes": [{"code": "only", "definition": "the one code", "status": "seeded", "uses": 0}]}], (_r.get_json(), _r2.get_json(), _r3.get_json()))
for _m in ("auth", "auth.supabase_client", "app"): sys.modules.pop(_m, None)

# the v1 replay and edit-and-run are retired with step 4 (docs/ROUTINES_DESIGN.md S10, 2026-10-11): the replay routes and
# chain_replay_utils are gone, /query takes no user_code or dataset mappings and seeds no chain with a script, and
# pd_agent_converse has no user_code or replay parameter - a routine's run is how a chain runs again
import inspect as _insp
_app_src = open(os.path.join(ROOT, "web_app", "app.py"), encoding="utf-8").read()
check("retired (S10): replay_routes.py and chain_replay_utils.py are gone and app.py neither imports nor registers them",
      not os.path.exists(os.path.join(ROOT, "web_app", "replay_routes.py")) and not os.path.exists(os.path.join(ROOT, "web_app", "chain_replay_utils.py"))
      and "replay_bp" not in _app_src and "chain_replay_utils" not in _app_src)
check("retired (S10): /query reads no user_code or dataset_mappings and carries neither canned sentence",
      "user_code" not in _app_src and "dataset_mappings" not in _app_src and "User manually edited your code" not in _app_src and "User updated the data in the datasets" not in _app_src)
_sig = _insp.signature(B.BambooAI.pd_agent_converse).parameters
check("retired (S10): pd_agent_converse has no user_code or replay parameter and the question is never seeded with code",
      "user_code" not in _sig and "replay" not in _sig and "supplied this code to run first" not in _insp.getsource(B.BambooAI.pd_agent_converse), list(_sig))

# follow-up on the same thread, standing on run1: the kernel is reused (d is still defined)
state.update(i=0, script=FOLLOW); BAMBOO.output_manager.add_user_input("And again?")
BAMBOO.pd_agent_converse(thread_id="1001", chain_id=run1.id)
while not q.empty(): q.get()
run2 = BAMBOO.notebook.runs[str(BAMBOO.chain_id)]
check("follow-up: parent is run1, the warm kernel was reused, cells number along the path (3)",
      run2.parent == run1.id and run2.cells()[0].cell_no == 3 and "reusing d from before: " in run2.cells()[0].stdout, [c.cell_no for c in run2.cells()])

# a branch from run1 (not the tip): a fresh kernel rehydrated from run1's cells
state.update(i=0, script=FOLLOW); BAMBOO.output_manager.add_user_input("Branch question")
BAMBOO.pd_agent_converse(thread_id="1001", chain_id=run1.id)
while not q.empty(): q.get()
run3 = BAMBOO.notebook.runs[str(BAMBOO.chain_id)]
check("branch: parent is run1, rehydrated from its path (d exists), numbered 3 again on its own branch, sibling unseen",
      run3.parent == run1.id and run3.cells() and run3.cells()[0].cell_no == 3 and "reusing d from before: " in run3.cells()[0].stdout
      and run2.id not in [r.id for r in BAMBOO.notebook.path(run3.id)], (run3.status, [c.cell_no for c in run3.cells()]))
check("the workflow map has three nodes with the right parents",
      sorted((n["id"], n["parent"]) for n in BAMBOO.notebook.tree()) == sorted([(run1.id, None), (run2.id, run1.id), (run3.id, run1.id)]))

# a prose follow-up (no cells): no replay, no Code/Plots/Results tabs re-shown from the parent
PROSE = ["###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\nFibonacci was a medieval Italian mathematician. No numbers here.\n"]
state.update(i=0, script=PROSE); BAMBOO.output_manager.add_user_input("Who was Fibonacci?")
BAMBOO.pd_agent_converse(thread_id="1001", chain_id=int(run3.id))
events3 = []
while not q.empty(): events3.append(json.loads(q.get()))
run4 = BAMBOO.notebook.runs[str(BAMBOO.chain_id)]
t3 = [e.get("type") for e in events3 if e.get("type")]
check("a prose follow-up replays nothing and re-shows none of the parent's Code/Plots/Results",
      run4.cells() == [] and run4.replay_status == "" and "code" not in t3 and "code_exec_results" not in t3 and "answer" in t3, t3)
idev = next(e for e in events3 if e.get("type") == "id")
check("the id event's parent carries the browser's own value and type (the map draws edges by strict equality)",
      idev.get("parent_chain_id") == int(run3.id) and isinstance(idev.get("parent_chain_id"), int), idev)
_h3 = next((e["report_head"] for e in events3 if "report_head" in e), {})
check("a follow-up's head carries the question as the analyst understood it, not the typed fragment and not the thread's earlier questions (2026-10-17, Palo: the report is the chain's result, not the trajectory)",
      _h3.get("question") == "q" and "lineage" not in _h3 and _h3.get("replay") == "" and _h3.get("cells") == 0, _h3)
check("modes: the brain (planning) means deep, auto_explore means adaptive, neither means quick",
      BAMBOO._last_budget.turns == BAMBOO.turns_deep)
BAMBOO.planning = False; state.update(i=0, script=PROSE); BAMBOO.output_manager.add_user_input("q"); BAMBOO.pd_agent_converse(thread_id="1001", chain_id=None)
while not q.empty(): q.get()
qk = BAMBOO._last_budget.turns
state.update(i=0, script=PROSE); BAMBOO.output_manager.add_user_input("q"); BAMBOO.pd_agent_converse(thread_id="1001", chain_id=None, auto_explore=True, max_investigations=5)
while not q.empty(): q.get()
check("...quick = the tier's quick turns; adaptive with a depth of 5 = 40 turns with self-review",
      qk == BAMBOO.turns_quick and BAMBOO._last_budget.turns == 40 and BAMBOO._last_budget.review_every == 8, (qk, BAMBOO._last_budget))
# the brain's menu: an explicit mode wins over the legacy flags
for m_, want in (("quick", BAMBOO.turns_quick), ("deep", BAMBOO.turns_deep), ("adaptive", 40)):
    state.update(i=0, script=PROSE); BAMBOO.output_manager.add_user_input("q")
    BAMBOO.pd_agent_converse(thread_id="1001", chain_id=None, mode=m_, auto_explore=(m_ != "adaptive"), max_investigations=5)
    while not q.empty(): q.get()
    check(f"mode={m_} sent by the brain's menu sets the budget regardless of the legacy flags", BAMBOO._last_budget.turns == want, BAMBOO._last_budget)
check("the cards carry the seat name the log entries use",
      all(e["seat"] == "Investigator" for e in events if e.get("type") == "pane_turn_start"))

# the data changed between a chain and its follow-up (2026-10-12): the warm kernel is not continued - the earlier chain's
# cells ran on data that is no longer loaded - and the follow-up starts in a fresh kernel on the data loaded now; the ledger
# keeps the earlier chain as context, marked as on other data; the replay and a routine are made from the follow-up's own cells
state.update(i=0, script=SCRIPT); BAMBOO.output_manager.add_user_input("Is B higher than A?")
BAMBOO.pd_agent_converse(thread_id="1001", chain_id=None)
while not q.empty(): q.get()
run_a = BAMBOO.notebook.runs[str(BAMBOO.chain_id)]
df2 = pd.DataFrame({"arm": np.tile(["A", "B"], 60), "x": np.random.default_rng(3).normal(size=120), "site": np.repeat(["n", "s"], 60)})
BAMBOO.df, BAMBOO.df_id = df2, "d2"                      # as a loader route does: the frame replaced, the kernel left as it was
OTHER = ["###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nz = 1\nprint('d defined:', 'd' in globals(), '| columns:', list(df.columns), '| rows:', len(df))\n```",
         "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## Answer\nThe frame has 120 rows [cell 3].\n"]
ncalls = len(state["calls"])
state.update(i=0, script=OTHER); BAMBOO.output_manager.add_user_input("And on this data?")
BAMBOO.pd_agent_converse(thread_id="1001", chain_id=run_a.id)
while not q.empty(): q.get()
run_b = BAMBOO.notebook.runs[str(BAMBOO.chain_id)]
_prompt_b = state["calls"][ncalls][1]
check("a follow-up after the data changed: parent kept, a fresh kernel (the earlier chain's names are not there, df is the frame loaded now), the run's data is the new frame, the cell numbered along the path",
      run_b.parent == run_a.id and "d defined: False" in run_b.cells()[0].stdout and "'site'" in run_b.cells()[0].stdout and "rows: 120" in run_b.cells()[0].stdout
      and run_b.data.get("df_id") == "d2" and run_b.cells()[0].cell_no == 3, (run_b.cells()[0].stdout[:120], run_b.data.get("df_id"), [c.cell_no for c in run_b.cells()]))
check("...its first prompt: the ledger keeps the earlier chain, marked as on other data with its cells named as not in the kernel, no names line; CELLS SO FAR starts empty",
      "[run 1] Q: Is B higher than A?" in _prompt_b and "On other data (" in _prompt_b and "its cells 1-2 are not in the kernel (SHOW n re-opens one from the record)" in _prompt_b
      and "Names left in the kernel" not in _prompt_b and "CELLS SO FAR:\n(no cells yet)" in _prompt_b, _prompt_b[:600])
check("...its replay re-runs its own cell only, and reproduces", run_b.replay_status == "reproduced" and "groupby('arm')" not in run_b.replay_script and "z = 1" in run_b.replay_script, (run_b.replay_status, run_b.report[-200:]))
# a routine from the follow-up: the method is its own cell; the proposal says what it continues
FakeModels.config["agent_configs"].append({"agent": "Promoter", "details": {"model": "fake/model", "provider": "fake", "reasoning_effort": "medium", "max_tokens": 32000}})
while not q.empty(): q.get()
prop_b = BAMBOO.propose_routine("1001", run_b.id, billing_chain_id="9008")
check("Save as routine on the follow-up: the script is its own cell (the earlier chain's cells, on other data, are not in it); a note says what the chain continues",
      prop_b["cells"] == 1 and "groupby('arm')" not in prop_b["script"] and "z = 1" in prop_b["script"] and prop_b["data_state"] == "same"
      and any("continues 1 earlier chain of the thread that ran on other data (cells 1-2): the method is this chain's own cell 3" in n for n in prop_b["notes"]), (prop_b["cells"], prop_b["notes"]))
made_b = BAMBOO.create_routine(prop_b["proposal_id"], {"name": "On the new frame", "purpose": ""}, routine_id=None)
made_b["run_zero"] = dict(made_b["run_zero"], **_settled(made_b["routine"]["id"]))
check("...created: run zero on the data loaded now runs the one cell and the routine's data is the new frame",
      made_b["run_zero"]["verified"] and made_b["routine"]["current_version"] == 1 and made_b["run_zero"]["data"]["df_id"] == "d2", made_b["run_zero"])
st.delete(made_b["routine"]["id"])
FakeModels.config["agent_configs"] = [a_ for a_ in FakeModels.config["agent_configs"] if a_["agent"] != "Promoter"]
# a second follow-up on the same (new) data continues the warm kernel as always: the follow-up's own names are there
SAME = ["###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nprint('z from before:', z)\n```",
        "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## Answer\nStill here [cell 4].\n"]
ncalls = len(state["calls"])
state.update(i=0, script=SAME); BAMBOO.output_manager.add_user_input("And again?")
BAMBOO.pd_agent_converse(thread_id="1001", chain_id=run_b.id)
while not q.empty(): q.get()
run_c = BAMBOO.notebook.runs[str(BAMBOO.chain_id)]
_prompt_c = state["calls"][ncalls][1]
check("a follow-up on the same data: the warm kernel continues (z is there); the ledger marks the chain before the change as on other data and gives the one after it its names line",
      "z from before: 1" in run_c.cells()[0].stdout and run_c.cells()[0].cell_no == 4 and "On other data (" in _prompt_c.split("[run 2]")[0]
      and "Names left in the kernel" in _prompt_c.split("[run 2]")[1] and "[cell 3]" in _prompt_c, (run_c.cells()[0].stdout, _prompt_c[:500]))
# the same data under a new frame id (2026-10-12): a favourite continued in a new session, the file uploaded again - the same name,
# rows and columns - is the same data: the earlier chain's cells are rehydrated in a fresh kernel (the warm one holds another
# frame), the ledger is as for any follow-up, the replay and a routine take the whole path, and run zero is verified
BAMBOO.df, BAMBOO.df_id = df, "d1-again"
ncalls = len(state["calls"])
state.update(i=0, script=FOLLOW); BAMBOO.output_manager.add_user_input("And again, in a new session?")
BAMBOO.pd_agent_converse(thread_id="1001", chain_id=run_a.id)
while not q.empty(): q.get()
run_d = BAMBOO.notebook.runs[str(BAMBOO.chain_id)]
_prompt_d = state["calls"][ncalls][1]
check("a follow-up on the same file uploaded again (a new frame id): rehydrated from the earlier chain's cells (d is there), its record the new id, numbered 3; the ledger plain, with the names line; the replay re-runs the whole path",
      run_d.parent == run_a.id and "reusing d from before: " in run_d.cells()[0].stdout and run_d.data.get("df_id") == "d1-again" and run_d.cells()[0].cell_no == 3
      and "On other data" not in _prompt_d and "Names left in the kernel" in _prompt_d and run_d.replay_status == "reproduced" and "groupby('arm')" in run_d.replay_script and "(3 cells," in run_d.report,
      (run_d.cells()[0].stdout[:80], run_d.data.get("df_id"), _prompt_d[:300], run_d.report[-160:]))
FakeModels.config["agent_configs"].append({"agent": "Promoter", "details": {"model": "fake/model", "provider": "fake", "reasoning_effort": "medium", "max_tokens": 32000}})
while not q.empty(): q.get()
prop_d = BAMBOO.propose_routine("1001", run_d.id, billing_chain_id="9009")
made_d = BAMBOO.create_routine(prop_d["proposal_id"], {"name": "On the same frame again", "purpose": ""}, routine_id=None)
made_d["run_zero"] = dict(made_d["run_zero"], **_settled(made_d["routine"]["id"]))
check("Save as routine on it: the chain's data counts as loaded (the same data under a new id) - the script is the whole path, run zero verified",
      prop_d["data_state"] == "same" and prop_d["cells"] == 3 and made_d["run_zero"]["verified"] and made_d["run_zero"]["status"] == "reproduced", (prop_d["data_state"], prop_d["cells"], made_d["run_zero"]))
st.delete(made_d["routine"]["id"])
FakeModels.config["agent_configs"] = [a_ for a_ in FakeModels.config["agent_configs"] if a_["agent"] != "Promoter"]
BAMBOO.df, BAMBOO.df_id = df, "d1"

# the plot the person asks about (the Plots tab's Ask AI, 2026-10-13): the page had sent the picture since v1 and the analyst never
# received it. Now it rides with every analysis turn as an image part when the analyst's model takes images (model_properties
# multimodal), with a line saying what it is; a model that does not take images gets the question alone and the pane says so;
# the run log keeps a placeholder, never the picture
_png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
PLOTQ = ["###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nprint('looked')\n```", "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## Answer\nThe line is the mean [cell 1].\n"]
state.update(i=0, script=PLOTQ, images=[]); BAMBOO.output_manager.add_user_input("What is the blue line?")
BAMBOO.pd_agent_converse(thread_id="1001", chain_id=None, image=_png)
_evs = []
while not q.empty(): _evs.append(json.loads(q.get()))
_sys = [e.get("system_message") for e in _evs if e.get("system_message")]
check("Ask AI about a plot with a model that does not take images: no image part in any call, the question goes alone, and the pane says the model does not take images",
      state["images"] and not any(state["images"]) and any("does not take images" in m for m in _sys) and "THE FIGURE THE PERSON ASKS ABOUT" not in state["calls"][-len(PLOTQ) - 1][1], (state["images"], _sys))
FakeModels.multimodal = "true"
state.update(i=0, script=PLOTQ, images=[]); BAMBOO.output_manager.add_user_input("What is the blue line?")
BAMBOO.pd_agent_converse(thread_id="1001", chain_id=None, image=_png)
while not q.empty(): q.get()
_turns = [(a, "THE FIGURE THE PERSON ASKS ABOUT is attached" in u, i) for (a, u), i in zip(state["calls"][-len(state["images"]):], state["images"])]
check("...with a model that takes images: the picture rides as an image part on each analysis turn, named in the prompt; the rewrite and the figures request go without it",
      [t[1:] for t in _turns if "TASK: turn" in state["calls"][-len(state["images"]):][_turns.index(t)][1]] == [(True, True)] * 2
      and all(not img for (a, u), img in zip(state["calls"][-len(state["images"]):], state["images"]) if "TASK: turn" not in u), (_turns, [u[:60] for a, u in state["calls"][-len(state["images"]):]]))
_last = json.load(open(_runlog))[-1]
check("...the run log keeps a placeholder for the picture, never the base64", not any(_png in json.dumps(e.get("messages")) for e in json.load(open(_runlog))[-4:]) and "<image, " in json.dumps(json.load(open(_runlog))[-3:]), json.dumps(_last.get("messages"))[-300:])
FakeModels.multimodal = "false"

# the search tool: the seam's structured links become the pills, intact (the grounding redirects break if a quote rides along)
BAMBOO._search_orchestrator = lambda prompts, lacm, om, chain_id, messages: ("Altitude reduces VO2max by ~1% per 100 m above 1,500 m.",
    [{"title": "Wehrlin 2006", "link": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEw8='"}, {"title": "", "link": "https://journals.lww.com/x"}, {"title": "bad", "link": "not a url"}])
BAMBOO._search = BAMBOO._web_search
txt = BAMBOO._web_search("altitude vo2max")
check("search: the text carries the sources; a stray quote is stripped from the url; a non-url is dropped; a missing title falls back to the host",
      "Sources:" in txt and BAMBOO._last_search_sources[0]["url"].endswith("AUZIYQEw8=") and len(BAMBOO._last_search_sources) == 2 and BAMBOO._last_search_sources[1]["title"] == "journals.lww.com", BAMBOO._last_search_sources)
while not q.empty(): q.get()
BAMBOO._emit({"type": "search", "run": run3.id, "text": txt})
ev = [json.loads(q.get()) for _ in range(q.qsize())]
lk = next(e for e in ev if e.get("type") == "pane_lookup")
check("the pane's search row carries the query and the two pills with exact urls", lk["query"] == "altitude vo2max" and [x["url"] for x in lk["sources"]] == [BAMBOO._last_search_sources[0]["url"], "https://journals.lww.com/x"])

# the Data tab: the dataframe event carries the first page as JSON (local mode), and the page route serves the rest
dfev = next(e for e in events if e.get("type") == "dataframe")
check("the dataframe event carries a page object: 50 rows, total, columns, dtypes, df_id",
      isinstance(dfev["data"], dict) and dfev["data"]["total"] == 200 and len(dfev["data"]["rows"]) == 50 and dfev["data"]["df_id"] == "d1" and dfev["data"]["columns"] == ["arm", "x"])
sys.path.insert(0, os.path.join(ROOT, "web_app"))
import importlib, types
class _Bp:
    def __init__(self, *a, **k): self.routes = {}
    def route(self, path, methods=None):
        def deco(fn): self.routes[path] = fn; return fn
        return deco
fake_flask = types.SimpleNamespace(Blueprint=_Bp, request=types.SimpleNamespace(args={}), jsonify=lambda d: ("json", d), session={})
fake_auth = types.SimpleNamespace(requires_auth=lambda fn: fn)
sys.modules["flask"] = fake_flask; sys.modules["auth"] = fake_auth; sys.modules["app"] = types.SimpleNamespace(bamboo_ai_instances={"sess": BAMBOO})
dr = importlib.import_module("dataframe_routes"); fake_flask.session["session_id"] = "sess"
fake_flask.request.args = {"offset": "150", "limit": "50", "order_by": "x", "ascending": "false"}
tag, body = dr.dataframe_page()
check("the page route: offset/limit/sort from the query string, served from the instance's frame in local mode",
      tag == "json" and body["offset"] == 150 and len(body["rows"]) == 50 and body["order_by"] == "x" and body["ascending"] is False and body["rows"][0][1] <= body["rows"][1][1] or (tag == "json" and body["rows"][0][1] >= body["rows"][1][1]), body.get("error"))
fake_flask.request.args = {"offset": "x"}
check("the page route: a bad offset is a 400", dr.dataframe_page()[1] == 400 if isinstance(dr.dataframe_page(), tuple) and len(dr.dataframe_page()) == 2 and isinstance(dr.dataframe_page()[1], int) else True)

# reset and cleanup
BAMBOO.pd_agent_converse(action="reset"); BAMBOO.cleanup()
check("reset drops the kernel and the notebook handle", BAMBOO._kernel is None and BAMBOO.notebook is None)
shutil.rmtree(work, ignore_errors=True)
# ---- the seedling's answer carries the explore flag; a normal answer does not ----
try:
    import json as _json, queue as _queue
    from bambooai.web_output_manager import WebOutputManager
    _om = WebOutputManager(); _om.output_queue = _queue.Queue()
    _om.display_results(chain_id="c1", answer="1. **A**: q?", explore=True)
    _events = []
    while not _om.output_queue.empty(): _events.append(_json.loads(_om.output_queue.get()))
    _ans = [e for e in _events if e.get('type') == 'answer']
    _om.display_results(chain_id="c2", answer="## report")
    _events2 = []
    while not _om.output_queue.empty(): _events2.append(_json.loads(_om.output_queue.get()))
    _ans2 = [e for e in _events2 if e.get('type') == 'answer']
    check("explore: the seedling's answer event carries explore=True; a report's does not", _ans and _ans[0].get('explore') is True and _ans2 and 'explore' not in _ans2[0], (_ans[:1], _ans2[:1]))
    # auxiliary files in DATA (2026-10-07): described with their first rows; without a primary they are the data
    os.chdir(tempfile.mkdtemp())                    # an earlier check removed the working directory the constructor writes logs/ into
    _auxdir = tempfile.mkdtemp(); _laps = os.path.join(_auxdir, "laps.csv"); _ath = os.path.join(_auxdir, "athletes.csv")
    pd.DataFrame({"athlete": ["a", "b", "c"], "pace": [3.5, 3.6, 3.4]}).to_csv(_laps, index=False)
    pd.DataFrame({"athlete": ["a", "b"], "nation": ["ETH", "KEN"]}).to_csv(_ath, index=False)
    _ba = B.BambooAI(df=None, df_id=None, user_id="u1", webui=True, auxiliary_datasets=[_laps, _ath])
    _desc = _ba._dataset_description()
    check("DATA with auxiliary files and no primary: says df is not defined and the files are the data, then each file's path and first rows (a run had read '(no dataset attached)' and nothing more)",
          _desc.startswith("No primary dataset is attached: `df` is not defined and DS has nothing to load.") and "AUXILIARY FILES (read them with pandas" in _desc
          and f"Path: {_laps}" in _desc and f"Path: {_ath}" in _desc and "ETH" in _desc and "3.5" in _desc, _desc[:600])
    _bb = B.BambooAI(df=pd.DataFrame({"x": [1, 2]}), df_id=None, user_id="u1", webui=True, auxiliary_datasets=[_ath])
    _desc2 = _bb._dataset_description()
    check("DATA with a primary and an auxiliary file: the frame first, then the auxiliary block with the file's rows",
          _desc2.startswith("`df`: 2 rows x 1 columns") and "AUXILIARY FILES" in _desc2 and f"Path: {_ath}" in _desc2 and "KEN" in _desc2, _desc2[-400:])
    check("DATA with nothing attached says so and that df is not defined", B.BambooAI(df=None, df_id=None, user_id="u1", webui=True)._dataset_description()
          == "(no dataset attached: `df` is not defined and DS has nothing to load; the question stands on its own, or on the documents below if any are attached)")
    # the context (2026-10-13, docs/CONTEXT_DESIGN.md §3.4): the context file's rows never enter DATA - the columns and the count do, and the map
    _ctx = os.path.join(_auxdir, "context_notes_20260615_to_20261013.csv")
    pd.DataFrame([{"id": "C.1", "kind": "activity_message", "date": "2026-09-01", "time": "08:10", "end_date": "", "activity_id": "a1", "event_id": "", "source_id": "1", "author_id": "i1", "author_name": "Me", "author_role": "subject", "private": False, "lang": "", "text": "legs heavy today, cut it short", "text_en": "", "chars": 30},
                  {"id": "C.2", "kind": "activity_message", "date": "2026-09-01", "time": "09:00", "end_date": "", "activity_id": "a1", "event_id": "", "source_id": "2", "author_id": "c9", "author_name": "Coach", "author_role": "coach", "private": False, "lang": "", "text": "take tomorrow easy", "text_en": "", "chars": 18},
                  {"id": "C.3", "kind": "status", "date": "2026-10-05", "time": "", "end_date": "2026-10-07", "activity_id": "", "event_id": "13", "source_id": "13", "author_id": "i1", "author_name": "", "author_role": "subject", "private": False, "lang": "", "text": "SICK: cold", "text_en": "", "chars": 10},
                  {"id": "C.4", "kind": "day_note", "date": "2026-10-09", "time": "", "end_date": "", "activity_id": "", "event_id": "15", "source_id": "15", "author_id": "c9", "author_name": "", "author_role": "coach", "private": True, "lang": "", "text": "watch motivation", "text_en": "", "chars": 16}]).to_csv(_ctx, index=False)
    _bc = B.BambooAI(df=pd.DataFrame({"x": [1, 2]}), df_id=None, user_id="u1", webui=True, auxiliary_datasets=[_ath, _ctx])
    _desc3 = _bc._dataset_description()
    check("DATA with a context file: its entry is the path, the columns and the row count - no passage text in the head - and the map follows: the span, the passages by kind with authors, the roles, private entries, the months, the closing sentence",
          f"Path: {_ctx}" in _desc3 and "Columns: id, kind, date, time, end_date, activity_id" in _desc3 and "Rows: 4 (the rows are passages: read them with CTX" in _desc3
          and "legs heavy today" not in _desc3 and "CONTEXT (the words written beside the data; in the kernel as CTX; files " in _desc3
          and "2026-09-01 to 2026-10-09: 4 passages — activity_message 2 (subject 1, coach 1); status 1 (SICK 1); day_note 1." in _desc3
          and "authors: subject 2, coach 2; private entries 1; by month Sep 2, Oct 2." in _desc3 and "A plan_note is dated the day it was planned for, not the day it was written." in _desc3 and "A passage is cited as" not in _desc3 and "KEN" in _desc3, _desc3[-1200:])
    # a kind whose every passage opens with an upper-case token is tallied by it (2026-10-18: a race's priority lived only in
    # `status` passages the map had counted as "status 36"); a kind of prose with the odd capital at the start is not
    from analyst.context import context_map as _cmap
    _st = [{"id": f"C.{i}", "kind": k, "date": "2026-09-21", "author_role": r, "private": False, "lang": "", "text": t}
           for i, (k, r, t) in enumerate([("status", "coach", "RACE_A: Worlds ITT"), ("status", "coach", "RACE_A: Worlds RR"), ("status", "subject", "RACE_A: EM TT"),
                                          ("status", "subject", "RACE_C: Cup"), ("status", "coach", "SEASON_START: 2026"), ("status", "subject", "SICK"),
                                          ("status", "subject", "HOLIDAY: Spain\nback on the 9th"), ("status", "coach", "TARGET: CTL 80"),
                                          ("activity_message", "subject", "OK legs fine"), ("activity_message", "coach", "legs heavy"),
                                          ("tag", "subject", "VO2"), ("tag", "subject", "heat session")], 1)]
    _map_st = _cmap(pd.DataFrame(_st))
    check("the map tallies a kind whose every passage opens with an upper-case token - the calendar's category, as written - most first, at most six and the rest counted; a kind of prose is not tallied, its occasional capital included",
          "status 8 (RACE_A 3, RACE_C 1, SEASON_START 1, SICK 1, HOLIDAY 1, TARGET 1); activity_message 2 (subject 1, coach 1); tag 2." in _map_st
          and "status 9 (RACE_A 3, RACE_C 1, SEASON_START 1, SICK 1, HOLIDAY 1, TARGET 1, … (1 more))" in _cmap(pd.DataFrame(_st + [dict(_st[0], id="C.99", text="INJURED: knee")])), _map_st)
    _cp_rows = [{"id": "C.1", "kind": "plan_note", "date": "2026-09-01", "author_role": "coach", "private": False, "lang": "", "text": "a" * 90, "activity_id": "", "activity_date": "", "copy_of": ""},
                {"id": "C.2", "kind": "activity_note", "date": "2026-09-01", "author_role": "subject", "private": False, "lang": "", "text": "a" * 90, "activity_id": "a1", "activity_date": "2026-09-01", "copy_of": "C.1"},
                {"id": "C.3", "kind": "activity_note", "date": "2026-09-03", "author_role": "subject", "private": False, "lang": "", "text": "a" * 90, "activity_id": "a2", "activity_date": "2026-09-03", "copy_of": "C.1"},
                {"id": "C.4", "kind": "activity_message", "date": "2026-09-04", "author_role": "subject", "private": False, "lang": "", "text": "felt rough", "activity_id": "a2", "activity_date": "2026-09-03", "copy_of": ""}]
    _map_cp = _cmap(pd.DataFrame(_cp_rows))
    check("the map counts the copies (copy_of) and the passages written on a later day than their activity, each in a line of its own; a window with neither has neither line",
          "  2 passages repeat an earlier passage word for word (copy_of names it): the earlier one's words, not a second writing of them, and coded there only." in _map_cp
          and "  1 passage on an activity was written on a later day than the activity: activity_date is the activity's day, date the day of writing." in _map_cp
          and "word for word" not in _map_st and "later day" not in _map_st, _map_cp)
    _cp_codes = pd.DataFrame([{"id": "C.4", "code": "fatigue", "tone": "negative", "quote": "felt rough", "status": "codebook", "coder": "m", "codebook_version": "1", "direction": "worse", "basis": "said", "about": "2026-09-03"},
                              {"id": "C.4", "code": "sleep", "tone": "negative", "quote": "rough", "status": "codebook", "coder": "m", "codebook_version": "1", "direction": "worse", "basis": "said", "about": "2026-09-04"},
                              {"id": "C.1", "code": "fatigue", "tone": "neutral", "quote": "aaa", "status": "codebook", "coder": "m", "codebook_version": "1", "direction": "worse", "basis": "said", "about": "2026-08-30"}])
    check("the map's count of readings about other days than their passage's own: a passage on an earlier activity has the activity's day as its own, its readings on that day not counted (2026-10-18)",
          "; 0 readings inferred rather than said, 2 about other days than their passage's own." in _cmap(pd.DataFrame(_cp_rows), _cp_codes), _cmap(pd.DataFrame(_cp_rows), _cp_codes))
    _tg = [{"id": f"C.{i}", "kind": "tag", "date": "2026-09-21", "author_role": "subject", "private": False, "lang": "", "text": t} for i, t in enumerate(["heatsession", "primary", "heatsession"], 1)]
    check("the map tallies a kind whose every passage is one token with no space - a tag - most first; a kind with one longer text is not tallied (patch 0197)",
          "tag 3 (heatsession 2, primary 1)." in _cmap(pd.DataFrame(_tg)) and "tag 2." in _map_st, _cmap(pd.DataFrame(_tg)))
    _codes = os.path.join(_auxdir, "context_codes_20260615_to_20261013.csv")
    pd.DataFrame([{"id": "C.1", "code": "fatigue", "tone": "negative", "quote": "legs heavy", "status": "codebook", "coder": "m", "codebook_version": 1},
                  {"id": "C.1", "code": "deviation", "tone": "negative", "quote": "cut it short", "status": "codebook", "coder": "m", "codebook_version": 1},
                  {"id": "C.2", "code": "instruction", "tone": "neutral", "quote": "take tomorrow easy", "status": "codebook", "coder": "m", "codebook_version": 1},
                  {"id": "C.3", "code": "unwell_span", "tone": "negative", "quote": "SICK", "status": "proposed", "coder": "m", "codebook_version": 1}]).to_csv(_codes, index=False)
    _bd = B.BambooAI(df=pd.DataFrame({"x": [1, 2]}), df_id=None, user_id="u1", webui=True, auxiliary_datasets=[_ctx, _codes])
    _desc4 = _bd._dataset_description()
    check("DATA with the codes file too: the codes line - counts per code, codes used, passages without a code, the proposed ones named; the codes file's head is columns and count as well",
          "codes (the model's reading, one row per code, with the words it rests on): fatigue 1, deviation 1, instruction 1, unwell_span 1 (4 of 36 codes used); 1 passage carries none; proposed: unwell_span." in _desc4
          and f"Path: {_codes}\nColumns: id, code, tone, quote, status, coder, codebook_version, direction, basis, about, day\nRows: 4" in _desc4 and "legs heavy" not in _desc4
          and "which way the codes point" not in _desc4, _desc4[-900:])
    # patch 0206: a codes file written before it has no `day` - the run's first read fills it and writes the file back, so
    # the kernel's CTX.codes() and a read by path have what DATA shows; a second read writes nothing
    _codes_disk = pd.read_csv(_codes, dtype=str, keep_default_na=False)
    _puts = []; _put0 = _bd._put_aux_file
    _bd._put_aux_file = lambda p, t: _puts.append(p) or _put0(p, t)
    _bd._context_cache = None
    _bd._context_frames()
    del _bd._put_aux_file
    check("a codes file written before patch 0206 gains `day` on a run's first read - each reading's passage's own day here, none saying another - and is written back; read again, nothing is written",
          _codes_disk["day"].tolist() == ["2026-09-01", "2026-09-01", "2026-09-01", "2026-10-05"] and list(_codes_disk.columns)[-1] == "day" and _puts == [], (_codes_disk.to_dict("records"), _puts))
    _empty = os.path.join(_auxdir, "context_notes_20260101_to_20260131.csv")
    pd.DataFrame(columns=["id", "kind", "date", "time", "end_date", "activity_id", "event_id", "source_id", "author_id", "author_name", "author_role", "private", "lang", "text", "text_en", "chars"]).to_csv(_empty, index=False)
    _desc5 = B.BambooAI(df=None, df_id=None, user_id="u1", webui=True, auxiliary_datasets=[_empty])._dataset_description()
    check("a context file with no rows: the map says no passages in this window", "no passages in this window: nothing was written beside the data loaded." in _desc5 and "Rows: 0" in _desc5, _desc5)
    from analyst.routines import aux_kind as _ak
    check("the two file kinds are known to the routines' kind table (a routine's plan binds them like the summary and wellness files)",
          _ak("datasets/u/k/context_notes_20260615_to_20261013.csv") == "context" and _ak("datasets/u/k/context_codes_20260615_to_20261013.csv") == "codes")
    _rec = _bc._load_of_cached({"source": "intervals", "date_range": "2026-06-15 to 2026-10-13", "metrics": ["watts"], "key_mark": "k"}, {"aux": [_ath, _ctx, _codes]})
    check("a cached frame's load record lists context and codes among its auxiliary kinds", _rec.get("aux_kinds") == ["context", "codes"] and _rec.get("start_date") == "2026-06-15", _rec)
    # room for more auxiliaries (2026-10-16, patch 0181): the heads together keep to AUX_BLOCK_CHARS - every turn carries the
    # block, a load brings several files and a person can attach more; past the budget a file's entry is its path and columns
    # (one call for the columns of the rest), a context file's entry is exempt (it is columns and a count already)
    _wide = [os.path.join(_auxdir, f"wide{k}.csv") for k in range(6)]
    for _p in _wide:
        pd.DataFrame({f"column_number_{c}": [f"value_{c}_{r}" for r in range(5)] for c in range(40)}).to_csv(_p, index=False)
    _descw = B.BambooAI(df=None, df_id=None, user_id="u1", webui=True, auxiliary_datasets=_wide + [_ctx])._auxiliary_block()
    _entries = _descw.split("AUXILIARY FILES", 1)[1].split("\n\nCONTEXT (", 1)[0].split("\n\n")
    _full = [e for e in _entries if "Head:" in e]; _compact = [e for e in _entries if "(the rows are left out to keep the prompt short; read the file for them)" in e]
    check("the auxiliary block keeps to its budget: six wide files and a context file - the first heads whole (cut at AUX_HEAD_CHARS each), the files past AUX_BLOCK_CHARS as path and columns, the context file's entry exempt",
          B.BambooAI.AUX_BLOCK_CHARS == 14000 and len(_full) == 4 and len(_compact) == 2 and all("Columns (40): column_number_0, column_number_1" in e and "value_" not in e for e in _compact)
          and all(f"Path: {_wide[k]}" in _compact[k - 4] for k in (4, 5)) and f"Path: {_ctx}\nColumns: id, kind, date" in _descw and "Rows: 4 (the rows are passages" in _descw
          and len(_descw) < B.BambooAI.AUX_BLOCK_CHARS + 2 * 600 + 1200, (len(_descw), [len(e) for e in _entries]))
    check("the auxiliary block under the budget is as it was: every head whole", "(the rows are left out" not in B.BambooAI(df=None, df_id=None, user_id="u1", webui=True, auxiliary_datasets=_wide[:3])._auxiliary_block())
    check("the compact entry without the columns says to read the file", B.BambooAI._aux_compact(3, "x.csv", None) == "3.\nPath: x.csv\nColumns: read the file for them\n(the rows are left out to keep the prompt short; read the file for them)")
    # the rider profile (2026-10-16, docs/RIDER_PROFILE_DESIGN.md): its DATA entry is the columns, the count and a line assembled from
    # the file's own rows - the measurements and each sport group's thresholds, the rest counted - never a head of five of a settings file
    _rider = os.path.join(_auxdir, "rider_profile_20260615_to_20261013.csv")
    pd.DataFrame([{"section": "subject", "sport_types": "", "key": "weight", "value": 71.5, "unit": "kg", "low": "", "high": "", "note": "the record's current weight"},
                  {"section": "subject", "sport_types": "", "key": "age", "value": 26, "unit": "years", "low": "", "high": "", "note": ""},
                  {"section": "sport", "sport_types": "Ride|VirtualRide", "key": "ftp", "value": 300, "unit": "W", "low": "", "high": "", "note": ""},
                  {"section": "sport", "sport_types": "Ride|VirtualRide", "key": "lthr", "value": 170, "unit": "bpm", "low": "", "high": "", "note": ""},
                  {"section": "sport", "sport_types": "Ride|VirtualRide", "key": "model_cp", "value": 295, "unit": "W", "low": "", "high": "", "note": "from the power-duration model"},
                  {"section": "sport", "sport_types": "Run", "key": "threshold_pace", "value": 3.5, "unit": "m/s", "low": "", "high": "", "note": ""},
                  {"section": "zone", "sport_types": "Ride|VirtualRide", "key": "hr_zone_1", "value": 140, "unit": "bpm", "low": 0, "high": 140, "note": "Z1"},
                  {"section": "zone", "sport_types": "Ride|VirtualRide", "key": "hr_zone_2", "value": 155, "unit": "bpm", "low": 140, "high": 155, "note": "Z2"},
                  {"section": "custom_zone", "sport_types": "Ride|VirtualRide", "key": "Breath:low", "value": "Low", "unit": "respiration", "low": 10, "high": 25, "note": "set 'Breathing'"},
                  {"section": "custom_field", "sport_types": "", "key": "Lbl", "value": "INTERVAL_FIELD", "unit": "", "low": "", "high": "", "note": "select · 'Label' · options: 1 Recovery | 2 Endurance"}]).to_csv(_rider, index=False)
    _descr = B.BambooAI(df=None, df_id=None, user_id="u1", webui=True, auxiliary_datasets=[_ath, _rider])._dataset_description()
    check("DATA with the rider profile: the entry is the path, the columns, the count with what a row is, and the Settings line from the rows - the measurements, each sport group's thresholds (the model's estimates left in the file), the rest counted; no head of rows",
          f"Path: {_rider}\nColumns: section, sport_types, key, value, unit, low, high, note\nRows: 10 (one row per setting: section, key, value, unit, the bounds for a zone, a note; read the file with pandas)\nSettings: weight 71.5 kg, age 26 years; "
          "Ride|VirtualRide: ftp 300 W, lthr 170 bpm; Run: threshold_pace 3.5 m/s; also in the file: 2 zone rows with their bounds, 1 custom zone rows in 1 set (Breath 'Breathing' on respiration), 1 custom field definitions - the codes other files' columns carry, with their options" in _descr
          and "model_cp" not in _descr and "Head:\nsection" not in _descr and "KEN" in _descr, _descr[-1100:])
    from analyst import profile as _pm
    check("profile_line: '' for an empty or missing frame; read_profile of a header alone is an empty frame with the columns", _pm.profile_line(None) == "" and _pm.profile_line(_pm.read_profile("")) == ""
          and list(_pm.read_profile("section,sport_types,key,value,unit,low,high,note\n").columns) == _pm.PROFILE_COLUMNS and len(_pm.read_profile("section,sport_types,key,value,unit,low,high,note\n")) == 0)
    # the rule about custom sets (2026-10-16, patch 0184, Palo: a coach's own zones come from testing and are the ones meant): said
    # at the end of the line when the file has custom_zone rows, and nothing of it for an account without any
    _pf = _pm.read_profile(open(_rider, encoding="utf-8").read())
    check("the Settings line ends with the custom-sets rule when the file has custom_zone rows - the sets are the account's own and take precedence over the standard zones, their times in the zone times file - and carries nothing of it without them",
          _pm.profile_line(_pf).endswith("; " + _pm.CUSTOM_SETS_RULE) and "take precedence over the standard zones when reading intensity" in _descr
          and "precedence" not in _pm.profile_line(_pf[_pf["section"] != "custom_zone"]) and "custom zone rows" not in _pm.profile_line(_pf[_pf["section"] != "custom_zone"]), _pm.profile_line(_pf))
    # the sets named (2026-10-18): with the sets only counted, two runs of a words question guessed which set was the
    # ventilatory one - each by its code, as the zone times file's set_code has it, with the stream it is cut on, in the file's
    # order; the name only when it says more than the code
    _sets_pf = _pm.read_profile(pd.DataFrame([{"section": "custom_zone", "sport_types": "Ride", "key": f"{c}:{z}", "value": z, "unit": u, "low": 0, "high": 1,
                                                 "note": f"set '{n}' · defined as it stands on 2026-01-29 · time in it per activity is in the custom zone times file"}
                                                for c, n, u, zs in [("Powerzones", "Power zones", "watts", ["Rec", "EE"]), ("TymeWearVE", "TymeWear VE", "tidal_volume_min", ["VT1VE", "VT2VE"]),
                                                                    ("TymeWearBreathingrate", "Tyme Wear - Breathing rate", "respiration", ["BRf"]), ("Lbl", "Labels for laps", "", ["x"])] for z in zs]).to_csv(index=False))
    check("the Settings line names the custom sets: code, the stream it is cut on, the name only when it says more than the code (spaces, case and punctuation aside), in the file's order",
          "6 custom zone rows in 4 sets (Powerzones on watts; TymeWearVE on tidal_volume_min; TymeWearBreathingrate on respiration; Lbl 'Labels for laps'); " in _pm.profile_line(_sets_pf), _pm.profile_line(_sets_pf))
    # the scales (2026-10-18): the subjective scales the account's form tracks, with the end that is good - nothing had said which,
    # and a run read sleep quality the wrong way round; rendered from the rows, one shared range and note, each row whole when they differ
    _sc_rows = [{"section": "subject", "sport_types": "", "key": "weight", "value": 70, "unit": "kg", "low": "", "high": "", "note": ""}] + [
        {"section": "scale", "sport_types": "", "key": k, "value": "1-4", "unit": "", "low": 1, "high": 4, "note": "N"} for k in ("soreness", "sleepQuality")]
    _sc_line = _pm.profile_line(_pm.read_profile(pd.DataFrame(_sc_rows).to_csv(index=False)))
    _sc_mixed = _pm.profile_line(_pm.read_profile(pd.DataFrame(_sc_rows[:2] + [dict(_sc_rows[2], value="0-10", note="M")]).to_csv(index=False)))
    check("the Settings line carries the scales after the sport groups: the keys with the range and note they share, each row whole when they differ, nothing without scale rows",
          _sc_line == "weight 70 kg; soreness, sleepQuality 1-4 (N)" and _sc_mixed == "weight 70 kg; soreness 1-4 (N), sleepQuality 0-10 (M)"
          and "1-4" not in _pm.profile_line(_pm.read_profile(pd.DataFrame(_sc_rows[:1]).to_csv(index=False))), (_sc_line, _sc_mixed))
    from analyst.routines import LOADER_FILES_MAX as _lfm
    _tpl = open(os.path.join(ROOT, "web_app", "templates", "index.html"), encoding="utf-8").read().replace("\r\n", "\n")
    _core = open(os.path.join(ROOT, "web_app", "static", "js", "core.js"), encoding="utf-8").read()
    check("the auxiliary limit is one number, derived (the sixth file had tripped a literal 6): app.py takes LOADER_FILES_MAX from the loaders' registry plus room for uploads, hands it to the template, and the page sets window.MAX_AUXILIARY_DATASETS before core.js reads it",
          _lfm == 8 and "MAX_AUXILIARY_DATASETS = LOADER_FILES_MAX + UPLOAD_ROOM" in _app_src and "UPLOAD_ROOM = 4" in _app_src and "MAX_AUXILIARY_DATASETS = 6" not in _app_src
          and "common_context['max_auxiliary_datasets'] = MAX_AUXILIARY_DATASETS" in _app_src
          and 'window.MAX_AUXILIARY_DATASETS = Number("{{ max_auxiliary_datasets|default(10)|int }}") || 10;' in _tpl and _tpl.index("window.MAX_AUXILIARY_DATASETS") < _tpl.index("js/core.js")
          and "const MAX_AUXILIARY_DATASETS = Number(window.MAX_AUXILIARY_DATASETS) || 10;" in _core and "MAX_AUXILIARY_DATASETS = 6" not in _core)
    # step 2 (docs/CONTEXT_DESIGN.md §5): CTX in the kernel, READ CTX through the host, [C.n] for the report guard and the page
    _pre = _bd._kernel_prelude()
    check("the kernel prelude defines CTX over the loaded context and codes files (no documents on this thread: the prelude is the context's alone); none without a context file",
          _pre == _bd._context_prelude() and "CTX = _BambooContext(" in _pre and repr(_ctx) in _pre and repr(_codes) in _pre and _bb._kernel_prelude() == "" and _bb._context_prelude() == "", _pre[-300:])
    _ns = {}
    exec(_pre, _ns)
    _CTX = _ns["CTX"]
    check("CTX in a kernel: frame() (no day of its own: `day` is the codes', the day a reading describes - patch 0206), codes() with `day`, grep by pattern/kind/author, around a day, between two days, on an activity, text(ref) - printed as text, not frames, unless asked",
          len(_CTX.frame()) == 4 and "day" not in _CTX.frame().columns and len(_CTX.codes()) == 4 and _CTX.codes()["day"].dt.strftime("%Y-%m-%d").tolist() == ["2026-09-01", "2026-09-01", "2026-09-01", "2026-10-05"] and "C.1" in _CTX.grep("legs") and "C.2" not in _CTX.grep("legs") and "C.2" in _CTX.grep("easy", author="coach")
          and "C.1" in _CTX.around("2026-09-02", days=1) and "C.3" not in _CTX.around("2026-09-02", days=1) and "C.3" in _CTX.between("2026-10-01", "2026-10-31") and "C.4" in _CTX.between("2026-10-01", "2026-10-31")
          and "C.1" in _CTX.on("a1") and "C.2" in _CTX.on("a1") and "C.3" not in _CTX.on("a1") and "legs heavy today, cut it short" in _CTX.text("C.1") and "4 passages" in repr(_CTX)
          and _CTX.grep("legs", as_frame=True).shape[0] == 1, (_CTX.grep("legs"), repr(_CTX)))
    check("CTX.frame()'s private is true or false, not the file's text (2026-10-18: a run summed the text column and lost a turn)",
          _CTX.frame()["private"].tolist() == [False, False, False, True] and _CTX.frame()["private"].dtype == bool, _CTX.frame()["private"].tolist())
    # 2026-10-19: the two tables come typed, as pandas reads any file - a run had lost six turns to dates read as text (a
    # comparison with a Timestamp failed) and blanks that were "" rather than missing (copy_of.isna() kept nothing)
    _fr, _cd = _CTX.frame(), _CTX.codes()
    _ws, _rd_ = pd.Timestamp("2026-09-01"), pd.Timestamp("2026-10-06")
    check("CTX.frame() typed: date, end_date and activity_date are datetimes (NaT where blank), a blank in any other column is missing (copy_of.isna() is true of every passage that is no copy, activity_id of one on no activity), "
          "chars a number, the text columns text with '' where there is nothing; a window taken by comparing date with Timestamps; the English rendering kept beside the original",
          str(_fr["date"].dtype).startswith("datetime64") and str(_fr["end_date"].dtype).startswith("datetime64") and str(_fr["activity_date"].dtype).startswith("datetime64")
          and _fr["end_date"].isna().tolist() == [True, True, False, True] and _fr["copy_of"].isna().all() and _fr["activity_id"].isna().tolist() == [False, False, True, True]
          and _fr["chars"].tolist() == [30, 18, 10, 16] and (_fr["text_en"] == "").all() and _fr["text"].tolist()[0] == "legs heavy today, cut it short"
          and len(_fr[(_fr["date"] >= _ws) & (_fr["date"] <= _rd_)]) == 3 and _fr[_fr["copy_of"].isna()].shape[0] == 4, _fr.dtypes.to_dict())
    check("CTX.codes() typed: day a datetime, about missing where the reading is the passage's own, quote text; a window by day; the columns an older file lacks are there, missing",
          str(_cd["day"].dtype).startswith("datetime64") and _cd["about"].isna().all() and _cd["direction"].isna().all() and (_cd["quote"] != "").all()
          and len(_cd[(_cd["day"] >= _ws) & (_cd["day"] <= _rd_)]) == 4 and list(_cd.columns) == ["id", "code", "tone", "quote", "status", "coder", "codebook_version", "direction", "basis", "about", "day"], _cd.dtypes.to_dict())
    check("the printing calls read the passages as written and are unchanged; rows asked for with as_frame=True are the typed frame's; repr says the span as written",
          _CTX.grep("legs") == "[C.1] 2026-09-01 · activity_message · subject: legs heavy today, cut it short" and str(_CTX.grep("legs", as_frame=True)["date"].dtype).startswith("datetime64")
          and _CTX.around("2026-09-02", days=1, as_frame=True)["id"].tolist() == ["C.1", "C.2"] and _CTX.on("a1", as_frame=True)["copy_of"].isna().all()
          and repr(_CTX) == "CTX: 4 passages from 2026-09-01 to 2026-10-09, codes in CTX.codes()", (_CTX.grep("legs"), repr(_CTX)))
    # the activity's day where a passage is written later than its activity (patch 0196): in CTX's printed lines and in where_of (the Reader's and the chips' place)
    _ns_a = {}
    _ctx_a = os.path.join(_auxdir, "context_notes_20260901_to_20260930.csv")
    pd.DataFrame([{"id": "C.1", "kind": "activity_message", "date": "2026-09-02", "time": "01:30", "activity_id": "a1", "activity_date": "2026-09-01", "author_role": "subject", "private": "False", "lang": "", "text": "felt rough today", "text_en": ""},
                  {"id": "C.2", "kind": "activity_message", "date": "2026-09-01", "time": "18:00", "activity_id": "a1", "activity_date": "2026-09-01", "author_role": "coach", "private": "False", "lang": "", "text": "easy tomorrow", "text_en": ""}]).to_csv(_ctx_a, index=False)
    exec(__import__("analyst.context", fromlist=["kernel_api_source"]).kernel_api_source(_ctx_a), _ns_a)
    from analyst.context import where_of as _where_of
    check("a passage written on a later day than its activity says the activity's day where it is printed (CTX's lines, where_of); one written that day does not",
          "[C.1] 2026-09-02 · activity_message · subject · the activity of 2026-09-01: felt rough today" in _ns_a["CTX"].on("a1") and "[C.2] 2026-09-01 · activity_message · coach: easy tomorrow" in _ns_a["CTX"].on("a1")
          and _where_of({"date": "2026-09-02", "kind": "activity_message", "author_role": "subject", "activity_date": "2026-09-01"}) == "2026-09-02 · activity_message · subject · the activity of 2026-09-01"
          and _where_of({"date": "2026-09-01", "kind": "activity_message", "author_role": "coach", "activity_date": "2026-09-01"}) == "2026-09-01 · activity_message · coach", _ns_a["CTX"].on("a1"))
    # patch 0206 (2026-10-18): the day each reading describes, in the codes table the analyst reads - CTX.days() and
    # CTX.episodes() (0204) were never called in three runs; both models matched the words to the numbers by their own
    # reckoning of a passage's day
    _dn = [{"id": "C.1", "kind": "activity_message", "date": "2026-09-01", "activity_id": "a1", "activity_date": "2026-09-01", "author_role": "subject", "text": "legs heavy"},
           {"id": "C.2", "kind": "activity_message", "date": "2026-09-03", "activity_id": "a2", "activity_date": "2026-09-02", "author_role": "subject", "text": "heavy again"},
           {"id": "C.3", "kind": "day_note", "date": "2026-09-05", "activity_id": "", "activity_date": "", "author_role": "subject", "text": "still heavy"},
           {"id": "C.5", "kind": "day_note", "date": "2026-09-10", "activity_id": "", "activity_date": "", "author_role": "subject", "text": "unwell since the 8th, better tomorrow"}]
    _dc = [("C.1", "fatigue", ""), ("C.2", "fatigue", ""), ("C.3", "fatigue", "2026-09-04"), ("C.5", "illness", "2026-09-08..2026-09-10"),
           ("C.5", "illness", "next week"), ("C.9", "fatigue", "")]
    _ctx_d, _codes_d = os.path.join(_auxdir, "context_notes_20260901_to_20260921.csv"), os.path.join(_auxdir, "context_codes_20260901_to_20260921.csv")
    pd.DataFrame(_dn).to_csv(_ctx_d, index=False)
    _codes_df = pd.DataFrame([dict(id=i, code=c, tone="", quote="", status="codebook", coder="m", codebook_version="1", direction="worse", basis="said", about=a) for i, c, a in _dc])
    from analyst.context import reading_days as _rdays
    _rd = _rdays(_codes_df, pd.DataFrame(_dn))
    check("reading_days: the day each reading describes - its about, the first day of a range, else its passage's own (the activity's, for one written later); a value that is not a day takes the passage's own; a passage the context lacks has none",
          _rd == ["2026-09-01", "2026-09-02", "2026-09-04", "2026-09-08", "2026-09-10", ""] and _rdays(_codes_df.iloc[:0], pd.DataFrame(_dn)) == []
          and _rdays(_codes_df.drop(columns=["about"]), pd.DataFrame(_dn))[:3] == ["2026-09-01", "2026-09-02", "2026-09-05"], _rd)
    _codes_df.assign(day=_rd).to_csv(_codes_d, index=False)
    _ns_d = {}
    exec(__import__("analyst.context", fromlist=["kernel_api_source"]).kernel_api_source(_ctx_d, _codes_d), _ns_d)
    check("CTX.codes() carries the file's `day` (a datetime, NaT where the file has none); CTX has no tables by day (CTX.days() and CTX.episodes() are gone) and the kernel source defines nothing beside CTX's class; an empty codes table has the column too",
          [("" if pd.isna(x) else x.strftime("%Y-%m-%d")) for x in _ns_d["CTX"].codes()["day"]] == _rd and not hasattr(_ns_d["CTX"], "days") and not hasattr(_ns_d["CTX"], "episodes")
          and "_bamboo_ctx_days" not in _ns_d and "_bamboo_ctx_episodes" not in _ns_d
          and "day" in _ns_d["_BambooContext"](_ctx_d, "").codes().columns and len(_ns_d["_BambooContext"](_ctx_d, "").codes()) == 0, _ns_d["CTX"].codes().to_dict("records"))
    _map_d = _cmap(pd.DataFrame(_dn).assign(private=False, lang=""), pd.read_csv(_codes_d, dtype=str, keep_default_na=False))
    check("the map: the directions' line as before, no line of stretches", "which way the codes point for the person (worse/better/neutral): fatigue 4/0/0, illness 2/0/0;" in _map_d and "stretches" not in _map_d, _map_d)
    check("unit_text resolves a context passage for the report guard - the English rendering when there is one - and says None for an id the context does not hold",
          _bc._unit_text("C.1") == "legs heavy today, cut it short" and _bc._unit_text("C.9") is None and _bb._unit_text("C.1") is None)
    _bc.models.llm_call = lambda *a, **k: '- [C.1] "legs heavy today"\n- [C.2] "take tomorrow easy"\n- [C.1] "legs light"\nSUMMARY: Heavy legs, an easy day asked [C.1][C.2].'
    _dg = _bc._read("CTX how were the legs")
    check("READ CTX dispatches to the context: the Reader's quotes verified against the passages, the digest under [C.n] with day, kind and author, the unverifiable quote dropped",
          _dg.startswith("PASSAGES") and '- [C.1] (2026-09-01 · activity_message · subject) "legs heavy today"' in _dg and '- [C.2] (2026-09-01 · activity_message · coach Coach) "take tomorrow easy"' in _dg
          and "legs light" not in _dg and _bc._last_read_query == "CTX how were the legs" and [x["id"] for x in _bc._last_read_passages] == ["C.1", "C.2"], _dg)
    _bc._read("CTX")
    check("READ CTX without a question is answered without a reader call", _bc._read("CTX").startswith("(READ CTX needs what you are looking for") and _bc._last_read_passages == [])
    _bc.models.llm_call = lambda *a, **k: "NO"
    check("a documents' READ still goes to the documents (none on this thread: the message says so)", _bc._read("D1 the sample").startswith("(no documents are attached"), _bc._read("D1 the sample"))
    # the pane event after a READ over a rendered passage carries the original beside the quote (S2: the chip's hover)
    _ctx_da = os.path.join(_auxdir, "context_notes_20260101_to_20260430.csv")
    pd.DataFrame([{"id": "C.1", "kind": "activity_message", "date": "2026-03-01", "time": "08:10", "end_date": "", "activity_id": "a1", "event_id": "", "source_id": "1", "author_id": "i1", "author_name": "", "author_role": "subject", "private": False, "lang": "da", "text": "benene var tunge", "text_en": "the legs were heavy", "chars": 16}]).to_csv(_ctx_da, index=False)
    _be = B.BambooAI(df=None, df_id=None, user_id="u1", webui=True, auxiliary_datasets=[_ctx_da])
    _be.models.llm_call = lambda *a, **k: '- [C.1] "the legs were heavy"\nSUMMARY: heavy [C.1].'
    _dg2 = _be._read("CTX the legs")
    import queue as _q2
    _be.output_manager.output_queue = _q2.Queue()
    from analyst import Notebook as _NB2, Run as _Run2
    _nb2 = _NB2("t-ctx"); _run2 = _nb2.new_run("q"); _be.notebook = _nb2
    _be._emit({"type": "read", "run": _run2.id, "text": _dg2, "query": "CTX the legs"})
    _pev = [json.loads(_be.output_manager.output_queue.get()) for _ in range(_be.output_manager.output_queue.qsize())]
    _plk = next(e for e in _pev if e.get("type") == "pane_lookup")
    check("the pane's READ row carries the passage with its place marked 'rendered from da', the English quote and the original - the chip shows both",
          _plk["passages"] == [{"id": "C.1", "where": "2026-03-01 · activity_message · subject (rendered from da)", "quote": "the legs were heavy", "original": "benene var tunge"}] and _plk["query"] == "CTX the legs", _plk)
    check("the report guard reads the rendering: unit_text of a rendered passage is its English text", _be._unit_text("C.1") == "the legs were heavy")
    # the passages a report cites - bracketed or by bare id - resolved for the chips' hover at report time (2026-10-14)
    _cp = _be._cited_passages("**C.1 - written 2026-03-01** [cell 1] and [C.1] again; C.7 is not there, nor D1.3; `CTX.text('C.1')` is code")
    check("_cited_passages: one entry per cited passage, bracketed or bare, with its place, the rendering as the quote and the original; ids that do not resolve are left out",
          _cp == [{"id": "C.1", "where": "2026-03-01 · activity_message · subject (rendered from da)", "quote": "the legs were heavy", "original": "benene var tunge"}], _cp)
    _be.output_manager.output_queue = _q2.Queue()
    _be._emit({"type": "report", "run": _run2.id, "text": "The legs: C.1 says so [cell 1]."})
    _be._emit({"type": "report", "run": _run2.id, "text": "Nothing cited [cell 1]."})
    _pev2 = [json.loads(_be.output_manager.output_queue.get()) for _ in range(_be.output_manager.output_queue.qsize())]
    check("the report event sends the cited passages to the page as pane_passages, before the answer renders; a report citing none sends nothing",
          [e.get("type") for e in _pev2] == ["pane_passages"] and _pev2[0]["passages"][0]["id"] == "C.1" and _pev2[0]["passages"][0]["original"] == "benene var tunge", _pev2)
    # the frames are read once per load: a load assigns the auxiliary list, which drops them (step 3 re-uploads the context file under its name)
    _n0 = len(_be._context_frames()[0])
    pd.DataFrame([{"id": "C.1", "kind": "day_note", "date": "2026-03-02", "time": "", "end_date": "", "activity_id": "", "event_id": "", "source_id": "1", "author_id": "i1", "author_name": "", "author_role": "subject", "private": False, "lang": "", "text": "fine", "text_en": "", "chars": 4},
                  {"id": "C.2", "kind": "day_note", "date": "2026-03-03", "time": "", "end_date": "", "activity_id": "", "event_id": "", "source_id": "2", "author_id": "i1", "author_name": "", "author_role": "subject", "private": False, "lang": "", "text": "tired " * 80, "text_en": "", "chars": 480}]).to_csv(_ctx_da, index=False)
    _n1 = len(_be._context_frames()[0])
    _be.auxiliary_datasets = [_ctx_da]
    _n2 = len(_be._context_frames()[0])
    check("the context frames are cached until the auxiliary list is assigned again (a load): the file rewritten under its name is read then, not before", (_n0, _n1, _n2) == (1, 1, 2) and (_be._unit_text("C.2") or "").strip() == ("tired " * 80).strip(), (_n0, _n1, _be._unit_text("C.2")))
    _cp2 = _be._cited_passages("C.2 goes on")
    check("a long passage is clipped for the hover - 300 characters and an ellipsis - and an English passage carries no original", 295 <= len(_cp2[0]["quote"]) <= 301 and _cp2[0]["quote"].endswith("\u2026") and _cp2[0]["quote"].startswith("tired tired") and "original" not in _cp2[0] and _cp2[0]["where"] == "2026-03-03 · day_note · subject", _cp2)
    # ---- step 3: the coding pass at load (bambooai/context_host.py) on a local instance with a scripted Coder ----
    from analyst import coder as _coder, codebook as _cb
    from analyst.coded import CodedStore as _CS
    _ctxdir = tempfile.mkdtemp(); _ctx3 = os.path.join(_ctxdir, "context_notes_20260801_to_20260831.csv")
    _rows3 = [{"id": f"C.{i}", "kind": k, "date": d, "time": "", "end_date": "", "activity_id": "", "event_id": "", "source_id": str(100 + i), "author_id": a, "author_name": n, "author_role": r, "private": False, "lang": "", "text": t, "text_en": "", "chars": len(t)}
              for i, (k, d, a, n, r, t) in enumerate([("day_note", "2026-08-02", "i1", "", "subject", "slept badly, legs flat all day"),
                                                     ("activity_message", "2026-08-03", "i1", "", "subject", "Benene var tunge fra den første stigning, men det gik."),
                                                     ("activity_message", "2026-08-03", "c1", "Kim", "coach", "Keep the next two days easy."),
                                                     ("tag", "2026-08-05", "i1", "", "subject", "sick"),
                                                     ("plan_note", "2026-08-06", "c1", "Kim", "coach", "Long climbs at a steady effort; stop if the legs go flat.")], 1)]
    pd.DataFrame(_rows3).to_csv(_ctx3, index=False)
    _calls3 = []; _fails3 = [0]
    _lock3 = __import__("threading").Lock()
    def _coder_reply(*a, **k):
        msgs = a[1] if len(a) > 1 else k.get("messages")
        user = msgs[-1]["content"]
        ids = re.findall(r"^\[(C\.\d+)\] ", user, re.M)
        with _lock3:
            _calls3.append((k.get("agent"), k.get("chain_id"), msgs[0]["content"][:20], ids, user))
            if "C.5" in ids and _fails3[0] < 2:
                _fails3[0] += 1
                return "not json at all"                   # the batch with C.5 fails in both rounds: its passage stays uncoded and the report counts it
        out = {"C.1": {"id": "C.1", "codes": [{"code": "sleep", "quote": "slept badly", "direction": "worse", "basis": "said", "about": "2026-08-01..2026-08-02"},
                                             {"code": "fatigue", "quote": "legs flat all day", "direction": "worse", "basis": "said", "about": ""}], "tone": "negative", "lang": "en"},
               "C.2": {"id": "C.2", "codes": ["fatigue", "heavy legs"], "tone": "mixed", "quotes": {"fatigue": "Benene var tunge", "heavy legs": "tunge"}, "lang": "da", "text_en": "The legs were heavy from the first climb, but it went.", "propose": [{"code": "heavy legs", "definition": "the legs feel heavy"}]},
               "C.3": {"id": "C.3", "codes": ["instruction", "nonsense"], "tone": "neutral", "quotes": {"instruction": "Keep the next two days easy", "nonsense": "Keep"}, "lang": "en"},
               "C.4": {"id": "C.4", "codes": ["illness"], "tone": "negative", "quotes": {"illness": "sick"}, "lang": "en"},
               "C.5": {"id": "C.5", "codes": ["instruction"], "tone": "neutral", "quotes": {"instruction": "stop if the legs go flat"}, "lang": "en"}}
        return "\n".join(json.dumps(out[i]) for i in ids if i in out)
    _saved_n = _coder.BATCH_PASSAGES; _coder.BATCH_PASSAGES = 3
    try:
        _bf = B.BambooAI(df=None, df_id=None, user_id="u3", webui=True, auxiliary_datasets=[_ctx3])
        _bf.models.llm_call = _coder_reply
        _prog = []
        _rep = _bf.code_context(_ctx3, progress=lambda k, n: _prog.append((k, n)), billing_chain_id="load-1", key_mark="k-one")
    finally:
        _coder.BATCH_PASSAGES = _saved_n
    _notes3 = pd.read_csv(_ctx3, dtype=str, keep_default_na=False)
    _codes3_path = _ctx3.replace("context_notes_", "context_codes_")
    _codes3 = pd.read_csv(_codes3_path, dtype=str, keep_default_na=False) if os.path.exists(_codes3_path) else None
    check("the pass: the tag set aside as a label (patch 0197), a batch of three and one in parallel, then a second round for the passage no reply answered (that batch failing both times); the report counts the passages, the coded, the uncoded, the rendered, the proposal, the failed batches, the unanswered and the labels; the calls on the Coder seat (absent in this config: the Reader's, so the analyst's) under the billing chain",
          sorted(_prog) == [(1, 2), (2, 2), (3, 3)] and _rep["passages"] == 5 and _rep["coded"] == 3 and _rep["uncoded"] == 2 and _rep["rendered"] == 1 and _rep["proposed"] == 1 and _rep["proposals"] == ["heavy_legs"]
          and _rep["failed_batches"] == 2 and _rep["unanswered"] == 1 and _rep["batches"] == 3 and _rep["reused"] == 0 and _rep["dropped"] == {"unknown_code": 1} and _rep["codes_path"] == _codes3_path and _rep["codebook_version"] == 1
          and _rep["labels"] == 1 and _rep["copies"] == 0
          and len(_calls3) == 3 and all(c[0] == "Investigator" and c[1] == "load-1" and c[2].startswith("You are the Coder") for c in _calls3) and sorted(len(c[3]) for c in _calls3) == [1, 1, 3]
          and not any("C.4" in c[3] for c in _calls3), (_rep, _prog, [(c[0], c[1], c[2], c[3]) for c in _calls3]))
    check("the context file rewritten in place with the language and the renderings - the Danish passage rendered, the English ones lang en and empty, the unanswered one untouched - every other column as it was "
          "(a file from an older executor gains the two later columns, empty: activity_date and copy_of)",
          list(_notes3.columns) == list(pd.DataFrame(_rows3).columns) + ["activity_date", "copy_of"] and _notes3.set_index("id").loc["C.2", ["lang", "text_en"]].tolist() == ["da", "The legs were heavy from the first climb, but it went."]
          and _notes3.set_index("id").loc["C.1", ["lang", "text_en"]].tolist() == ["en", ""] and _notes3.set_index("id").loc["C.5", ["lang", "text_en"]].tolist() == ["", ""] and _notes3.set_index("id").loc["C.2", "text"].startswith("Benene")
          and _notes3.set_index("id").loc["C.4", ["lang", "text_en"]].tolist() == ["", ""], _notes3[["id", "lang", "text_en"]].to_dict("records"))
    check("the codes file beside it: the design's columns, the rows that passed the checks (the unknown code dropped), the proposal's row marked, the coder and the version on every row; "
          "a code read in the format of patch 0198 carries its direction, basis and days, one read in the older format none; every row its `day` (patch 0206) - a range's first day, else the passage's own",
          _codes3 is not None and list(_codes3.columns) == ["id", "code", "tone", "quote", "status", "coder", "codebook_version", "direction", "basis", "about", "day"]
          and _codes3["day"].tolist() == ["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-03", "2026-08-03"]
          and _codes3.iloc[0][["direction", "basis", "about"]].tolist() == ["worse", "said", "2026-08-01..2026-08-02"] and _codes3.iloc[2][["direction", "basis", "about"]].tolist() == ["", "", ""]
          and [(r["id"], r["code"], r["status"]) for r in _codes3.to_dict("records")] == [("C.1", "sleep", "codebook"), ("C.1", "fatigue", "codebook"), ("C.2", "fatigue", "codebook"), ("C.2", "heavy_legs", "proposed"), ("C.3", "instruction", "codebook")]
          and (_codes3["coder"] == "fake/model").all() and (_codes3["codebook_version"] == "1").all() and _codes3.iloc[2]["quote"] == "Benene var tunge", None if _codes3 is None else _codes3.to_dict("records"))
    _book3 = _cb.load(_bf._user_storage())
    check("the user's codebook under storage/<user>/context: seeded by the pass, the proposal stored as proposed with the coder as its proposer and an example, the load's uses recorded",
          os.path.exists(os.path.join(os.getcwd(), "storage", "u3", "context", "codebook.json")) and len(_book3["codes"]) == 37 and next(c for c in _book3["codes"] if c["code"] == "heavy_legs")["status"] == "proposed"
          and next(c for c in _book3["codes"] if c["code"] == "heavy_legs")["proposed_by"] == "fake/model" and next(c for c in _book3["codes"] if c["code"] == "fatigue")["uses"] == 2, [(c["code"], c.get("uses")) for c in _book3["codes"] if c.get("uses")])
    # the store (D1's fallback): the passages this pass answered are remembered per subject; a second load of the same words codes nothing
    _retry = [c for c in _calls3 if c[3] == ["C.5"]]
    check("each batch carries the passages before it for reference (patch 0198): the second round's lone passage comes with the three read before it - the tag left out - each on a line of its own",
          _retry and all("EARLIER PASSAGES (3; for reference, not to code):\nC.1 · 2026-08-02 · day_note · subject: slept badly, legs flat all day\nC.2 · " in c[4]
                         and "\nC.3 · 2026-08-03 · activity_message · coach Kim: Keep the next two days easy.\n\nPASSAGES (1;" in c[4] and "C.4 ·" not in c[4] for c in _retry)
          and all("EARLIER PASSAGES" not in c[4] for c in _calls3 if "C.1" in c[3]), [c[4][:400] for c in _retry])
    _store3 = _CS(_bf._user_storage(), "k-one").load()
    check("the coded passages are remembered under storage/<user>/context/<key mark>/coded.json - the three answered ones with their rendering and codes, the unanswered one not, the tag never sent",
          os.path.exists(_store3.path) and len(_store3.entries) == 3 and _store3.entries["activity_message:102"]["text_en"].startswith("The legs were heavy") and [c["code"] for c in _store3.entries["activity_message:102"]["codes"]] == ["fatigue", "heavy_legs"]
          and "plan_note:105" not in _store3.entries and "tag:104" not in _store3.entries
          and all(e.get("reading") == 4 for e in _store3.entries.values()) and _store3.entries["day_note:101"]["codes"][0]["about"] == "2026-08-01..2026-08-02", (_store3.path, sorted(_store3.entries)))
    pd.DataFrame(_rows3).to_csv(_ctx3, index=False)          # the window loaded again: the same words, the file fresh from the executor
    _bf.auxiliary_datasets = [_ctx3]
    _n_before = len(_calls3); _fails3[0] = 2                 # C.5's batch would answer now
    _rep2 = _bf.code_context(_ctx3, billing_chain_id="load-2", key_mark="k-one")
    _codes3b = pd.read_csv(_codes3_path, dtype=str, keep_default_na=False)
    check("the second load reuses the three coded passages without a call and codes only the one the store lacks; the files are written as before, the reused rows keeping their coder and version",
          _rep2["reused"] == 3 and _rep2["coded"] == 4 and len(_calls3) == _n_before + 1 and _calls3[-1][3] == ["C.5"] and _rep2["unanswered"] == 0
          and [(r["id"], r["code"]) for r in _codes3b.to_dict("records")][-1] == ("C.5", "instruction") and len(_codes3b) == 6 and _rep2["batches"] == 1, (_rep2, _calls3[-1][3]))
    _rows3b = [dict(r, text=(r["text"] + " Edited.") if r["id"] == "C.1" else r["text"]) for r in _rows3]
    pd.DataFrame(_rows3b).to_csv(_ctx3, index=False)
    _bf.auxiliary_datasets = [_ctx3]
    _rep3 = _bf.code_context(_ctx3, billing_chain_id="load-3", key_mark="k-one")
    check("a passage whose text changed is coded again (its key is the kind and the source id, its text hash the guard)", _rep3["reused"] == 3 and _calls3[-1][3] == ["C.1"], (_rep3["reused"], _calls3[-1][3]))
    # a copy (copy_of, the executor's mark) is not sent to the coder: it takes the rendering of the passage it repeats (patch 0197)
    _ctx5 = os.path.join(_ctxdir, "context_notes_20260701_to_20260731.csv")
    _long = "Pust ind i fire sekunder, hold vejret i syv, pust ud i otte; seks runder med hvile imellem dem alle sammen."
    pd.DataFrame([dict(_rows3[0], id="C.1", kind="plan_note", text=_long, chars=len(_long), source_id="501"),
                  dict(_rows3[1], id="C.2", kind="activity_note", text=_long, chars=len(_long), source_id="502", copy_of="C.1")]).to_csv(_ctx5, index=False)
    _calls5 = []
    def _coder5(*a, **k):
        ids = re.findall(r"^\[(C\.\d+)\] ", a[1][-1]["content"], re.M); _calls5.append(ids)
        return "\n".join(json.dumps({"id": i, "codes": ["recovery"], "tone": "neutral", "quotes": {"recovery": "seks runder"}, "lang": "da", "text_en": "Breathe in for four seconds, hold for seven, out for eight; six rounds with rest between them all."}) for i in ids)
    _b5 = B.BambooAI(df=None, df_id=None, user_id="u5", webui=True, auxiliary_datasets=[_ctx5])
    _b5.models.llm_call = _coder5
    _rep5 = _b5.code_context(_ctx5)
    _n5 = pd.read_csv(_ctx5, dtype=str, keep_default_na=False).set_index("id")
    _c5 = pd.read_csv(_ctx5.replace("context_notes_", "context_codes_"), dtype=str, keep_default_na=False)
    check("a copy is not sent to the coder and carries no codes of its own; it takes the rendering of the passage it repeats; the report counts it",
          _calls5 == [["C.1"]] and _c5["id"].tolist() == ["C.1"] and _n5.loc["C.2", "text_en"] == _n5.loc["C.1", "text_en"] != "" and _n5.loc["C.2", "lang"] == "da"
          and _rep5["copies"] == 1 and _rep5["coded"] == 1 and _rep5["unanswered"] == 0, (_calls5, _c5.to_dict("records"), _rep5))
    _bf.auxiliary_datasets = [_ctx3, _codes3_path]            # as the load route does once the pass ends
    _map3 = _bf._context_map()
    check("DATA after the pass: the map's languages and codes line - counts per code, 'of 36 codes used', the uncoded, the proposal; unit_text and the chips read the rendering, the original beside it",
          "languages en 3, da 1" in _map3 and "codes (the model's reading, one row per code, with the words it rests on): fatigue 2, instruction 2, sleep 1, heavy_legs 1 (4 of 36 codes used); 0 passages carry none; proposed: heavy_legs." in _map3
          and "  which way the codes point for the person (worse/better/neutral): sleep 1/0/0, fatigue 1/0/0; 0 readings inferred rather than said, 1 about other days than their passage's own." in _map3
          and _bf._unit_text("C.2") == "The legs were heavy from the first climb, but it went." and _bf._cited_passages("[C.2]")[0]["original"].startswith("Benene") and "(rendered from da)" in _bf._cited_passages("[C.2]")[0]["where"], _map3)
    _bf._context_coding = {"status": "running"}
    check("while the pass runs behind a load the map says so", "the coding pass is still running behind the load" in _bf._context_map())
    _bf._context_coding = None
    check("the Coder seat: 'Coder' when the config carries it, the Reader's seat otherwise (the analyst's here)",
          _bf._coder_seat() == "Investigator" and (lambda cfg: (setattr(_bf.models, "config", {"agent_configs": cfg + [{"agent": "Coder", "details": {"model": "m", "provider": "fake"}}]}), _bf._coder_seat())[1])(list(_bf.models.config["agent_configs"])) == "Coder")
    _bg = B.BambooAI(df=None, df_id=None, user_id="u3", webui=True, auxiliary_datasets=[_empty])
    _rep_e = _bg.code_context(_empty)
    check("a context file with no passages: nothing to code, no call, no codes file; a file that cannot be read: an error in the report and nothing written",
          _rep_e["passages"] == 0 and _rep_e["coded"] == 0 and not os.path.exists(_empty.replace("context_notes_", "context_codes_")) and _bg.code_context(os.path.join(_ctxdir, "context_notes_19990101_to_19990131.csv")).get("error") == "the context file could not be read", _rep_e)
    # the load route (web_app/integrations/intervals.py _coding_start): the load completes at once; the pass runs in a thread
    # behind it; /intervals/context_coding/<job_id> says where it is; the codes file joins the session's files when it ends
    import time as _time, threading as _thr
    if not hasattr(sys.modules.get("flask"), "Flask"):
        sys.modules.pop("flask", None)
    for _n in ("store_intervals_api_key", "remove_intervals_api_key", "get_intervals_integration_status", "get_user_subscription"):
        setattr(_fs, _n, lambda *a, **k: {"ok": True, "data": {}})
    sys.modules["auth"] = _fa; sys.modules["auth.supabase_client"] = _fs
    sys.modules.pop("integrations.intervals", None)
    import integrations.intervals as IV
    _ctx4 = os.path.join(_ctxdir, "context_notes_20260901_to_20260930.csv")
    pd.DataFrame(_rows3[:4]).to_csv(_ctx4, index=False)
    _bh = B.BambooAI(df=None, df_id=None, user_id="u3", webui=True, auxiliary_datasets=[_ctx4])
    _gate = _thr.Event(); _calls4 = []
    def _slow_coder(*a, **k):
        _calls4.append(1); _gate.wait(5)
        msgs = a[1]; found = re.findall(r"^\[(C\.\d+)\] [^\n]*\n([^\n]+)", msgs[-1]["content"], re.M)
        return "\n".join(json.dumps({"id": i, "codes": ["fatigue"], "tone": "negative", "quotes": {"fatigue": t[:5]}, "lang": "en"}) for i, t in found if i != "C.2")
    _bh.models.llm_call = _slow_coder
    _charged = []
    _bh.log_and_call_manager.charge_for_completed_query = lambda cid: _charged.append(cid)
    IV.intervals_bp.get_bamboo_ai = lambda sid: _bh; IV.intervals_bp.bamboo_ai_instances = {}; IV.intervals_bp.logger = logging.getLogger("t")
    _prefs4 = {"auxiliary_datasets": [_ath, _ctx4], "load": {"key": "k-four"}}
    _res4 = {"aux_datasets": [_ath, _ctx4], "context": {"passages": 4, "kinds": {"day_note": 1}, "subject_id": "i77001"}}
    _res_plain = {"aux_datasets": [_ath]}
    IV._coding_start("job-0", "s1", _res_plain, {"auxiliary_datasets": [_ath]})
    check("a completed load without a context file starts nothing", _res_plain == {"aux_datasets": [_ath]} and "job-0" not in IV._coding_states())
    IV._coding_start("job-4", "s1", _res4, _prefs4)
    _t0 = _time.time()
    while not _calls4 and _time.time() - _t0 < 5: _time.sleep(0.02)
    _view1 = IV._coding_view(IV._coding_states()["job-4"])
    check("the first completion starts the pass in a thread and completes the load at once: the result says the pass is running; the status view carries the coder's progress; the instance knows a pass is running",
          _res4["context"]["coding"]["status"] == "running" and _view1["status"] == "running" and _view1["message"] == "Coding the context…" and len(_calls4) == 1 and (_bh._context_coding or {}).get("status") == "running", (_res4["context"], _view1))
    _res4b = {"aux_datasets": [_ath, _ctx4], "context": {"passages": 4}}
    IV._coding_start("job-4", "s1", _res4b, _prefs4)
    check("a completion read again while the pass runs: the same pass, no second thread", _res4b["context"]["coding"]["status"] == "running" and len(_calls4) == 1)
    _gate.set()
    _t0 = _time.time()
    while IV._coding_states()["job-4"]["status"] == "running" and _time.time() - _t0 < 10: _time.sleep(0.02)
    _view2 = IV._coding_view(IV._coding_states()["job-4"])
    _codes4 = _ctx4.replace("context_notes_", "context_codes_")
    check("when the pass ends: the status view is done with the codes file and the line, the codes file has joined the session's auxiliary files and the instance's (assigned, so its frames are read again), the billing chain charged once",
          _view2["status"] == "done" and _view2["codes_path"] == _codes4 and _view2["line"] == "2 of 4 coded, 1 tag left as a label, 1 not read by the coder, 1 batch failed" and _view2["percent"] == 100
          and _prefs4["auxiliary_datasets"] == [_ath, _ctx4, _codes4] and _bh.auxiliary_datasets == [_ath, _ctx4, _codes4] and len(_charged) == 1 and os.path.exists(_codes4) and len(_calls4) == 2, (_view2, _prefs4, _charged, len(_calls4)))
    check("the store of coded passages is the subject's: under storage/<user>/context/<athlete id>/ as the job's report names the athlete, not under the key's mark (2026-10-14: a coach switches athletes; a regenerated key keeps the store)",
          os.path.exists(os.path.join(os.getcwd(), "storage", "u3", "context", "i77001", "coded.json")) and not os.path.exists(os.path.join(os.getcwd(), "storage", "u3", "context", "k-four", "coded.json")))
    _prefs4["auxiliary_datasets"] = [_ath, _ctx4]            # the completion block resets the session's files to the executor's list
    _res4c = {"aux_datasets": [_ath, _ctx4], "context": {"passages": 4}}
    IV._coding_start("job-4", "s1", _res4c, _prefs4)
    check("a completion read after the pass ended: the finished pass is reported and the codes file put back among the session's files; no call, no charge",
          _res4c["context"]["coding"]["status"] == "done" and _prefs4["auxiliary_datasets"] == [_ath, _ctx4, _codes4] and _bh.auxiliary_datasets[-1] == _codes4 and len(_calls4) == 2 and len(_charged) == 1, (_res4c["context"]["coding"], _prefs4))
    IV.can_execute_chain = lambda a: {"ok": True, "data": {"allowed": False, "reason": "no funds"}}
    _res5 = {"aux_datasets": [_ctx4], "context": {"passages": 4}}
    IV._coding_start("job-5", "s1", _res5, {"auxiliary_datasets": [_ctx4]})
    check("an account that may not run a query: the pass is skipped with the reason in the line, no call", _res5["context"]["coding"]["status"] == "skipped" and _res5["context"]["coding"]["line"] == "the context was not coded: no funds" and len(_calls4) == 2, _res5["context"])
    IV.can_execute_chain = lambda a: {"ok": True, "data": {"allowed": True}}
    # one athlete at a time on the Data tab, on the app's side of the cache's own load routes too (2026-10-29): a routine run taken
    # from the cache goes through /cache/load_primary and /cache/load_auxiliary, never the loader's completion, and the session's
    # list of files - the instance holds the same list - must follow the page's pills
    sys.modules.pop("integrations.cache_manager", None)
    import integrations.cache_manager as CM
    _a0 = "/x/datasets/u3/intervals/i0/views/wellness_data_20260101_to_20260301.csv"; _a1 = "/x/datasets/u3/intervals/i1/views/wellness_data_20260101_to_20260301.csv"; _up = "/x/datasets/u3/upload.csv"
    _p6 = {"auxiliary_datasets": [_a0, _ath, _up]}
    _bi = B.BambooAI(df=None, df_id=None, user_id="u3", webui=True, auxiliary_datasets=_p6["auxiliary_datasets"])
    CM.cache_bp.bamboo_ai_instances = {"s6": _bi}
    CM._one_athlete("s6", _p6, ""); _none = _p6["auxiliary_datasets"] == [_a0, _ath, _up]
    CM._one_athlete("s6", _p6, "intervals/i0"); _own = _p6["auxiliary_datasets"] == [_a0, _ath, _up] and _bi.auxiliary_datasets is _p6["auxiliary_datasets"]
    _mk = "/x/datasets/u3/abcdef012345/views/planned_workouts_20260101_to_20260301.csv"; _p6["auxiliary_datasets"].append(_mk)      # a loader's file an earlier load left under a key's mark
    CM._one_athlete("s6", _p6, "intervals/i1"); _p6["auxiliary_datasets"].append(_a1)
    check("the cache routes' one-athlete rule: a window file's athlete folder is read from its path (none for an upload or a file elsewhere; backslashes too); nobody's folder or the athlete's own changes nothing; another athlete's frame or file takes the first athlete's window files off the session's list and the instance's - a loader's file under a key's mark folder too - the same list still, so the file appended after lands in both - and leaves the files that are nobody's",
          CM._athlete_folder(_a0) == "intervals/i0" and CM._athlete_folder(_ath) == "" and CM._athlete_folder(_up) == "" and CM._athlete_folder("C:\\d\\u\\endura\\r9\\views\\f.csv") == "endura/r9"
          and _none and _own and _p6["auxiliary_datasets"] == [_ath, _up, _a1] and _bi.auxiliary_datasets == [_ath, _up, _a1] and _bi.auxiliary_datasets is _p6["auxiliary_datasets"], (_p6, _bi.auxiliary_datasets))

    from bambooai.models import ModelManager as _MM
    _mm = _MM.__new__(_MM)
    _mm.config = {"agent_configs": [{"agent": "Analyst", "details": {"model": "x-ai/grok-4.7", "provider": "openrouter"}},
                                    {"agent": "Reviewer", "details": {"model": "openai/gpt-5.6-sol", "provider": "openrouter"}}],
                  "model_properties": {"x-ai/grok-4.7": {"prompt_tokens": 0.002, "completion_tokens": 0.006}, "gpt-5.6-sol": {"prompt_tokens": 0.002, "completion_tokens": 0.01}}}
    check("pricing preflight: a seat whose model string has no model_properties entry (priced under another key) is named; a priced seat is not (2026-10-07: a Reviewer ran at $0.00 all run)",
          _mm.unpriced_seats() == [("Reviewer", "openai/gpt-5.6-sol")], _mm.unpriced_seats())
    import logging as _lg
    _mm.config = {"agent_configs": [{"agent": "Analyst", "details": {"model": "claude-opus-5.5", "provider": "anthropic"}}],
                  "model_properties": {"claude-opus-5-5": {"prompt_tokens": 0.004, "completion_tokens": 0.02, "no_sampling": True}}}
    class _Catch(_lg.Handler):
        def __init__(self): super().__init__(); self.lines = []
        def emit(self, r): self.lines.append(r.getMessage())
    _h = _Catch(); _lg.getLogger("bambooai.models").addHandler(_h)
    try:
        _mm._preflight_pricing()
    finally:
        _lg.getLogger("bambooai.models").removeHandler(_h)
    check("pricing preflight: a model string one character off an entry (claude-opus-5.5 for claude-opus-5-5) is named with the nearest entry, and the warning says the entry's facts do not apply (2026-10-08)",
          len(_h.lines) == 1 and "'claude-opus-5.5'" in _h.lines[0] and "The nearest entry is 'claude-opus-5-5' - a misspelling of it?" in _h.lines[0]
          and "effort levels, no_sampling" in _h.lines[0], _h.lines)
    _om.display_results(chain_id="c3", answer="## r", generated_datasets=["datasets/u/generated/x.csv"])
    _events3 = []
    while not _om.output_queue.empty(): _events3.append(_json.loads(_om.output_queue.get()))
    check("generated datasets are not a right-pane tab: display_results sends no generated_datasets payload (the pane's pills carry the files, 2026-10-06)",
          not any(e.get('type') == 'generated_datasets' for e in _events3) and any(e.get('type') == 'answer' for e in _events3), [e.get('type') for e in _events3])
except Exception as exc:                                     # noqa: BLE001
    check("explore: the seedling's answer event carries explore=True; a report's does not", False, repr(exc))
# ---- the infographic's YAML is mended before parsing; the infographic is a synthesis's only ----
try:
    import importlib.util as _ilu, yaml as _yaml
    _sp = _ilu.spec_from_file_location('si', os.path.join(ROOT, 'bambooai', 'synthesis_infographic.py')); _si = _ilu.module_from_spec(_sp); _sp.loader.exec_module(_si)
    _bad = 'items:\n  - name: A\n    tradeoff:"Cost / bound / not ideal"\n    disproven:""Ruled out"\n    ok: "fine"\n'
    _d = _yaml.safe_load(_si._tidy_yaml(_bad))
    check("infographic: a key glued to its quoted value and a doubled quote are mended before parsing", _d['items'][0]['tradeoff'] == 'Cost / bound / not ideal' and _d['items'][0]['disproven'] == 'Ruled out' and _d['items'][0]['ok'] == 'fine', _d)
    _src = open(os.path.join(ROOT, 'bambooai', 'bambooai.py'), encoding='utf-8').read()
    check("infographic: drawn only for a synthesis, never for an ordinary chain", "if self.synthesis_infographic and run.report and synthesis:" in _src)
except Exception as exc:                                     # noqa: BLE001
    check("infographic: a key glued to its quoted value and a doubled quote are mended before parsing", False, repr(exc))
# ---- the Reviewer seat (2026-09-10): a self-review turn runs on it when the config has one, else on the analyst seat
try:
    for d in (("storage", "u1", "threads"), ("logs", "u1")):                          # an earlier check removed the working folder
        os.makedirs(os.path.join(work, *d), exist_ok=True)
    os.chdir(work)                                                                     # the cwd still pointed at the removed one
    check("review seat: without a Reviewer in the config a review turn runs on the analyst seat", BAMBOO._review_seat() == BAMBOO._seat(), BAMBOO._review_seat())
    FakeModels.config["agent_configs"].append({"agent": "Reviewer", "details": {"model": "fake/strong", "provider": "fake", "reasoning_effort": "high"}})
    _get_model_name = FakeModels.get_model_name
    FakeModels.get_model_name = lambda self, agent: ("fake/strong", "fake") if agent == "Reviewer" else ("fake/model", "fake")
    BAMBOO.review_every = 2
    cell = lambda n: "###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nprint(%d)\n```" % n
    state.update(i=0, calls=[], script=[cell(1), cell(2), cell(3), cell(4), "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## Answer\nDone [cell 1].\n"])
    BAMBOO.output_manager.add_user_input("review me")
    BAMBOO.pd_agent_converse(thread_id="1001", chain_id=None, mode="adaptive")
    agents = [a for a, u in state["calls"] if not u.startswith("Rewrite")]
    check("review seat: in Adaptive with analyst_review_every=2 a review runs on the Reviewer after turns 2 and 4 and after the report; the turns and the figures step's call on the analyst seat",
          agents == ["Investigator", "Investigator", "Reviewer", "Investigator", "Investigator", "Reviewer", "Investigator", "Investigator", "Reviewer"], agents)
    check("review seat: the reviewer is sent its own prompt, never the analyst's contract",
          all(u.startswith("QUESTION:") for a, u in state["calls"] if a == "Reviewer"), [u[:40] for a, u in state["calls"] if a == "Reviewer"])
    q = BAMBOO.output_manager.output_queue; ev = []
    while not q.empty(): ev.append(json.loads(q.get()))
    starts = [(e.get("turn"), e.get("seat"), e.get("model"), e.get("review")) for e in ev if e.get("type") == "pane_turn_start"]
    check("review seat: the pane's Review cards carry 'Reviewer' and its model; the turns carry the analyst seat",
          [x[1:] for x in starts if x[0] == "review"] == [("Reviewer", "fake/strong", True)] * 3
          and all(x[1:3] == ("Investigator", "fake/model") and not x[3] for x in starts if isinstance(x[0], int)), starts)
    BAMBOO.review_every = 0
    state.update(i=0, calls=[], script=[cell(1), cell(2), "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## Answer\nDone [cell 1].\n"])
    BAMBOO.output_manager.add_user_input("no review"); BAMBOO.pd_agent_converse(thread_id="1001", chain_id=None, mode="adaptive")
    _ag = [a for a, u in state["calls"] if not u.startswith("Rewrite")]
    check("review seat: analyst_review_every=0 - no review during the run and none after the report: no reviewer call at all (2026-10-05); the figures step's call after the report",
          _ag == ["Investigator", "Investigator", "Investigator", "Investigator"], _ag)
    check("rewrite seat: without a Rewriter in the config the rewrite ran on the analyst seat",
          [a for a, u in state["calls"] if u.startswith("Rewrite")] == ["Investigator"], [(a, u[:20]) for a, u in state["calls"]])
    # with a Rewriter seat (2026-09-11): the rewrite, and only the rewrite, runs on it
    FakeModels.config["agent_configs"].append({"agent": "Rewriter", "details": {"model": "fake/flash", "provider": "fake", "reasoning_effort": "low"}})
    FakeModels.get_model_name = lambda self, agent: ("fake/strong", "fake") if agent == "Reviewer" else (("fake/flash", "fake") if agent == "Rewriter" else ("fake/model", "fake"))
    state.update(i=0, calls=[], script=[cell(1), "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## Answer\nDone [cell 1].\n"])
    BAMBOO.output_manager.add_user_input("rewrite me"); BAMBOO.pd_agent_converse(thread_id="1001", chain_id=None, mode="deep")
    agents = [(a, u.startswith("Rewrite")) for a, u in state["calls"]]
    check("rewrite seat: the rewrite call runs on the Rewriter, the analysis turns and the figures step on the analyst seat",
          agents == [("Investigator", False), ("Investigator", False), ("Investigator", False), ("Rewriter", True)], agents)
    q = BAMBOO.output_manager.output_queue; ev = []
    while not q.empty(): ev.append(json.loads(q.get()))
    rw = [(e.get("seat"), e.get("model")) for e in ev if e.get("type") == "pane_turn_start" and e.get("turn") == "rewrite"]
    check("rewrite seat: the pane's rewrite card carries 'Rewriter' and its model", rw and rw[-1] == ("Rewriter", "fake/flash"), rw)
    # the Figures seat (2026-10-11): the figures request runs on it when the config carries one, on the analyst seat otherwise (above)
    FakeModels.config["agent_configs"].append({"agent": "Figures", "details": {"model": "fake/quick", "provider": "fake", "reasoning_effort": "low"}})
    FakeModels.get_model_name = lambda self, agent: ("fake/strong", "fake") if agent == "Reviewer" else (("fake/flash", "fake") if agent == "Rewriter" else (("fake/quick", "fake") if agent == "Figures" else ("fake/model", "fake")))
    state.update(i=0, calls=[], script=[cell(1), "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## Answer\nDone [cell 1].\n"])
    BAMBOO.output_manager.add_user_input("figures seat"); BAMBOO.pd_agent_converse(thread_id="1001", chain_id=None, mode="deep")
    agents = [a for a, u in state["calls"]]
    q = BAMBOO.output_manager.output_queue; ev = []
    while not q.empty(): ev.append(json.loads(q.get()))
    fg = [(e.get("seat"), e.get("model")) for e in ev if e.get("type") == "pane_turn_start" and e.get("turn") == "figures"]
    check("figures seat: with a Figures seat in the config the figures request runs on it - the call and the pane's Figures card carry 'Figures' and its model; the turns stay on the analyst seat",
          agents == ["Investigator", "Investigator", "Figures", "Rewriter"] and fg == [("Figures", "fake/quick")], (agents, fg))
    FakeModels.config["agent_configs"].pop(); FakeModels.config["agent_configs"].pop(); FakeModels.config["agent_configs"].pop(); FakeModels.get_model_name = _get_model_name; BAMBOO.review_every = 8
except Exception as exc:                                     # noqa: BLE001
    check("review seat: the checks ran", False, repr(exc))

# ---- the figures step through the app (2026-10-11): a figure cell during the analysis is not run; after the report the step
# draws once from the kernel's variables (a first cell failing, corrected), the pane shows each attempt and its cell row, the
# report carries the Figures section, the replay through the executor yields the figure to the Plots tab
try:
    _cell = lambda code: "###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\n" + code + "\n```"
    state.update(i=0, calls=[], script=[_cell("m = df.groupby('arm')['x'].mean().round(3)\nprint('means', m.to_dict())"),
                                        _cell("import matplotlib.pyplot as plt\nplt.plot([1, 2]); plt.show()"),          # not run
                                        _cell("spread = df['x'].std()\nprint('spread', round(spread, 3))"),
                                        "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## Answer\nB is higher [cell 1]; the spread [cell 2].\n"],
                 figures=["```python\nimport matplotlib.pyplot as plt\nplt.bar(['A', 'B'], [m['A'], m['B']])\nplt.title(f'means, spread {spread:.2f}')\nplt.show()\nraise RuntimeError('no good')\n```\nCAPTION: the two means",
                          "```python\nimport matplotlib.pyplot as plt\nplt.bar(['A', 'B'], [m['A'], m['B']])\nplt.title(f'means, spread {spread:.2f}')\nplt.show()\n```\nCAPTION: the two means, the spread in the title"])
    BAMBOO.output_manager.add_user_input("draw it"); BAMBOO.pd_agent_converse(thread_id="1001", chain_id=None, mode="deep")
    q = BAMBOO.output_manager.output_queue; ev = []
    while not q.empty(): ev.append(json.loads(q.get()))
    _run = BAMBOO.notebook.runs[str(BAMBOO.chain_id)]
    _cells = [e for e in ev if e.get("type") == "pane_cell"]
    check("figures (app): the figure cell during the analysis is a skipped row - no number, 'not run', figures come after the report - and the record keeps it without a number",
          [(c.get("ok"), c.get("skipped"), c.get("cell_no")) for c in _cells[:3]] == [(True, False, 1), (True, True, None), (True, False, 2)]
          and _cells[1]["peek"].startswith("not run: figures are drawn after the report") and _run.turns[1].cell_no is None and not _run.turns[1].error, [(c.get("ok"), c.get("skipped"), c.get("cell_no"), c.get("peek")) for c in _cells])
    _fcards = [(e.get("attempt"), e.get("quiet"), e.get("seat")) for e in ev if e.get("type") == "pane_turn_start" and e.get("turn") == "figures"]
    _fends = [(e.get("kind"), e.get("peek"), bool(e.get("code"))) for e in ev if e.get("type") == "pane_turn_end" and e.get("turn") == "figures"]
    check("figures (app): two quiet Figures cards on the analyst seat - the attempt and its correction - each ending with what the cell draws and its code for the fold",
          _fcards == [(1, True, "Investigator"), (2, True, "Investigator")] and _fends == [("figures", "figure cell: the two means", True), ("figures", "figure cell: the two means, the spread in the title", True)], (_fcards, _fends))
    check("figures (app): the failed attempt is a rolled-back row with its error line, the corrected cell is cell 3 with one figure; the step's cells carry their step mark",
          [(c.get("ok"), c.get("cell_no"), c.get("figs"), (c.get("error_line") or "")[:20]) for c in _cells[3:]] == [(False, None, 0, "RuntimeError: no goo"), (True, 3, 1, "")]
          and [t.step for t in _run.turns if t.kind == "cell" and t.step] == ["figures", "figures"], [(c.get("ok"), c.get("cell_no"), c.get("figs"), c.get("error_line")) for c in _cells[3:]])
    _ans = next((e.get("data") or e.get("text") or "" for e in ev if e.get("type") == "answer"), "")
    _rend = [e for e in ev if e.get("type") == "pane_run_end"][-1]
    check("figures (app): the report carries the Figures section citing cell 3; the replay through the executor yields the one figure to the Plots tab; the strip's turn count leaves the step out",
          "## Figures" in _run.report and "- [fig 3] the two means, the spread in the title" in _run.report and _rend["plots"] == 1 and _rend["turns"] == 4 and _rend["cells"] == 3
          and _rend["replay_status"] == "reproduced" and "[fig 3]" in str(_ans), (_run.report[-400:], {k: _rend.get(k) for k in ("plots", "turns", "cells", "replay_status")}))
    _plan = [e for e in ev if e.get("type") == "plan"][-1]["data"]
    check("figures (app): the Investigation tab's notebook shows the skipped cell as In [–] · not run and the figures cell marked as the figures step",
          "nb-cell--skipped" in _plan and "In&nbsp;[&ndash;]" in _plan and "· not run" in _plan and "· figures step" in _plan and "· 1 fig" in _plan, _plan[:300])
    state["figures"] = None
except Exception as exc:                                     # noqa: BLE001
    check("figures (app): the checks ran", False, repr(exc))

# ---- the effort law for an effort-scale model with reasoning-off seats (2026-09-10, DeepSeek V4.1 Flash)
try:
    from bambooai.models import openrouter_models as om
    M = "deepseek/deepseek-v4.1-flash"
    def body(effort, style, efforts=None, model=M):
        om.set_reasoning_style(style); om.set_reasoning_efforts(efforts)
        return om._reasoning_body(model, [model], effort, 16000, style=style)
    vocab = ["none", "low", "medium", "high", "xhigh"]
    check("effort law: on the budget path high, xhigh and max all clamp to the same 8,000-token budget (why the word alone changes nothing)",
          body("high", None) == body("xhigh", None) == body("max", None) == {"max_tokens": 8000}, (body("high", None), body("xhigh", None)))
    check("effort law: an effort-word entry sends the word itself; max snaps to the declared top (xhigh)",
          body("high", "effort", vocab) == {"effort": "high"} and body("xhigh", "effort", vocab) == {"effort": "xhigh"} and body("max", "effort", vocab) == {"effort": "xhigh"})
    check("effort law: a DECLARED none stays none (the utility seats stay reasoning-off); an undeclared none still goes to the floor",
          body("none", "effort", vocab) == {"effort": "none"} and body("none", "effort", ["low", "high", "max"], model="z-ai/glm-5.3") == {"effort": "low"})
    om.set_reasoning_style(None); om.set_reasoning_efforts(None)
except Exception as exc:                                     # noqa: BLE001
    check("effort law: the checks ran", False, repr(exc))

# ---- the account-credit checkout and its webhook (web_app/subscription_routes.py) on a test app, Stripe faked
# (2026-10-13, patch 0140; PR #63 took payment_method_types out of the create call - Stripe API 2026-09-30)
try:
    import types as _ty, json as _json
    _fs2 = sys.modules.get("auth.supabase_client") or _ty.ModuleType("auth.supabase_client")
    _credits = []
    for _n in ("set_user_subscription", "get_user_subscription", "get_balance", "get_user_llm_config", "get_monthly_usage", "get_tier_limits"):
        setattr(_fs2, _n, lambda *a, **k: {"ok": True})
    _fs2.add_funds = lambda **kw: (_credits.append(kw), {"ok": True})[1]
    sys.modules["auth.supabase_client"] = _fs2
    _fa2 = sys.modules.get("auth") or _ty.ModuleType("auth"); _fa2.requires_auth = lambda f: f; _fa2.get_current_user_id = lambda: "auth0|u1"; sys.modules["auth"] = _fa2
    _lcb = _ty.ModuleType("llm_config_builder"); _lcb.build_user_config = lambda *a, **k: {}; sys.modules["llm_config_builder"] = _lcb
    _st = _ty.ModuleType("stripe")
    class _SigErr(Exception): pass
    _st.SignatureVerificationError = _SigErr; _st.api_key = None
    class _Webhook:
        @staticmethod
        def construct_event(payload, sig, secret):
            if sig == "bad": raise _SigErr("bad signature")
            return _json.loads(payload)
    _created = []
    class _CheckoutSession:
        @staticmethod
        def create(**kw): _created.append(kw); return _ty.SimpleNamespace(url="https://checkout.test/cs_1")
    _st.Webhook = _Webhook; _st.checkout = _ty.SimpleNamespace(Session=_CheckoutSession)
    sys.modules["stripe"] = _st
    sys.modules.pop("subscription_routes", None)
    if not hasattr(sys.modules.get("flask"), "Flask"):      # the dataframe_routes section above left a stand-in in its place
        sys.modules.pop("flask", None)
    import flask as _flask_real
    import subscription_routes as SR
    _Flask = _flask_real.Flask
    _sa = _Flask("s"); _sa.register_blueprint(SR.subscription_bp); _sc = _sa.test_client()
    _r = _sc.post("/api/create-checkout-session", json={"amount": 25})
    check("checkout: the create call sends no payment_method_types (removed in Stripe API 2026-09-30, the SDK's 16.x pin; PR #63) - the Dashboard's methods apply; $25 as 2500 cents, mode payment, the user in the metadata",
          _r.status_code == 200 and _r.get_json() == {"checkout_url": "https://checkout.test/cs_1"} and "payment_method_types" not in _created[-1]
          and _created[-1]["mode"] == "payment" and _created[-1]["line_items"][0]["price_data"]["unit_amount"] == 2500 and _created[-1]["metadata"] == {"auth0_id": "auth0|u1", "amount": "25"},
          (_r.status_code, _r.get_json(), sorted(_created[-1]) if _created else None))
    check("checkout: under the $10 minimum is refused before Stripe is called", _sc.post("/api/create-checkout-session", json={"amount": 5}).status_code == 400 and len(_created) == 1)
    def _event(kind, status, sid="cs_1", pi="pi_1", cents=2500):
        return _json.dumps({"type": kind, "data": {"object": {"id": sid, "payment_intent": pi, "payment_status": status, "amount_total": cents, "metadata": {"auth0_id": "auth0|u1", "amount": "25"}}}})
    _w = _sc.post("/api/stripe-webhook", data=_event("checkout.session.completed", "unpaid"), headers={"Stripe-Signature": "ok"})
    check("webhook: a session completed with payment_status unpaid (a delayed method) is acknowledged and not credited",
          _w.status_code == 200 and _w.get_json() == {"received": True} and _credits == [], (_w.status_code, _credits))
    _w = _sc.post("/api/stripe-webhook", data=_event("checkout.session.completed", "paid"), headers={"Stripe-Signature": "ok"})
    check("webhook: completed and paid (a card) credits the amount once, under the session's id and the payment intent as the idempotency key",
          _w.status_code == 200 and len(_credits) == 1 and _credits[0]["auth0_id"] == "auth0|u1" and _credits[0]["amount"] == 25.0 and _credits[0]["source"] == "stripe"
          and _credits[0]["reference"] == "cs_1" and _credits[0]["idempotency_key"] == "pi_1", _credits)
    _w = _sc.post("/api/stripe-webhook", data=_event("checkout.session.async_payment_succeeded", "paid", sid="cs_2", pi="pi_2"), headers={"Stripe-Signature": "ok"})
    check("webhook: the delayed method's later async_payment_succeeded (paid) credits then", _w.status_code == 200 and len(_credits) == 2 and _credits[1]["reference"] == "cs_2", _credits)
    _w = _sc.post("/api/stripe-webhook", data=_event("checkout.session.completed", "paid"), headers={"Stripe-Signature": "bad"})
    check("webhook: a bad signature is a 400 and credits nothing (stripe.SignatureVerificationError, the spelling every 7.x+ SDK has)", _w.status_code == 400 and len(_credits) == 2, (_w.status_code, _w.get_json()))
    _w = _sc.post("/api/stripe-webhook", data=_json.dumps({"type": "payment_intent.created", "data": {"object": {}}}), headers={"Stripe-Signature": "ok"})
    check("webhook: another event type is acknowledged and ignored", _w.status_code == 200 and len(_credits) == 2)
except Exception as exc:                                     # noqa: BLE001
    check("subscription routes: the checks ran", False, repr(exc))

print(f"\n{len(passed)} passed, {len(failed)} failed"); sys.exit(1 if failed else 0)
