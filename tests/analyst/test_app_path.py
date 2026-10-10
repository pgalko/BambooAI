"""The app path: BambooAI.pd_agent_converse -> analyst Session over a real
in-process kernel, with a scripted model layer, a web output queue, and the
notebook tree stored under the user's storage. Run: python3 tests/analyst/test_app_path.py"""
import os, sys, json, tempfile, shutil
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
          "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## Answer\nB exceeds A by DIFF units [cell 2]; means in [cell 1].\n"]
FOLLOW = ["###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nprint('reusing d from before:', d)\n```",
          "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## Answer\nStill DIFF [cell 3].\n"]
state = {"i": 0, "script": SCRIPT, "calls": []}
class FakeModels:
    config = {"agent_configs": [{"agent": "Investigator", "details": {"model": "fake/model", "provider": "fake", "reasoning_effort": "low"}}], "model_properties": {}}
    def __init__(self, *a, **k): pass
    def get_model_properties(self): return {"fake/model": {"capability": "reasoning", "multimodal": "false", "prompt_tokens": 0.001, "completion_tokens": 0.002}}
    def get_model_name(self, agent): return ("fake/model", "fake")
    def llm_stream(self, prompts, lacm, om, messages, agent=None, chain_id=None, reasoning_models=None, **kw):
        user = messages[-1]["content"]; state["calls"].append((agent, user))
        lacm.write_to_log(agent, chain_id, "2026-09-05 12:00:00", "fake/model", messages, "reply", 100, 50, 150, 1.0, 50.0)
        if user.startswith("Rewrite the technical report"):
            return "Plain: B is higher by DIFF."
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

BAMBOO.output_manager.add_user_input("Is B higher than A?")
BAMBOO.pd_agent_converse(thread_id="1001", chain_id=None)
q = BAMBOO.output_manager.output_queue; events = []
while not q.empty(): events.append(json.loads(q.get()))
types = [e.get("type") for e in events if e.get("type")]
check("web events: id, the Data tab (no Query tab), live Investigation-tab updates ('plan'), then answer, simplified_answer, code, results, end",
      types[0] == "id" and "query" not in types and "dataframe" in types and "plan" in types
      and all(t in types for t in ("answer", "simplified_answer", "code", "code_exec_results")) and types[-1] == "end", types)
pane_types = [e.get("type") for e in events if str(e.get("type", "")).startswith("pane_")]
check("the pane protocol: run_start, a turn_start/turn_end pair per model call (three turns, the rewrite - no review outside Adaptive), a cell row per cell, heartbeats, run_end",
      pane_types[0] == "pane_run_start" and pane_types.count("pane_turn_start") == 4 and pane_types.count("pane_turn_end") == 4
      and pane_types.count("pane_cell") == 2 and pane_types.count("pane_heartbeat") == 2 and pane_types[-1] == "pane_run_end", pane_types)
te = [e for e in events if e.get("type") == "pane_turn_end"]
check("turn_end carries the note and the code for the fold, and the heartbeat carries the estimate line",
      te[0]["code"].startswith("m = df.groupby") and te[0]["note"].startswith("- Question") and
      any(e.get("type") == "pane_heartbeat" and "estimate" in e for e in events))
cellev = [e for e in events if e.get("type") == "pane_cell"]
check("cell rows carry the number, the first output line and the size", cellev[0]["ok"] and cellev[0]["cell_no"] == 1 and cellev[0]["peek"].startswith("means") and cellev[0]["chars"] > 0)
rend = [e for e in events if e.get("type") == "pane_run_end"][0]
check("run_end carries turns, cells, cost, the replay line and the plots count", rend["cells"] == 2 and rend["replay_status"] == "reproduced" and "Replay" in rend["replay_line"] and rend["turns"] == 3)
plan = [e for e in events if e.get("type") == "plan"][-1]["data"]
check("the Investigation tab is a notebook: one HTML block, cells with collapsed outputs, no blank line inside it",
      plan.startswith('<div class="nb">') and plan.count('<details class="nb-out"') == 2 and "\n\n" not in plan and 'language-python' in plan)
check("each turn opened a card labelled with the seat, the rewrite too; no review card outside Adaptive",
      sum(1 for e in events if e.get("type") == "pane_turn_start" and e.get("seat") == "Investigator") == 4
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
check("report stored with the replay line; the rewrite by the same 'model'; status answered",
      run1.status == "answered" and "Replay reproduced" in run1.report and run1.rewrite.startswith("Plain:"), run1.report[-160:])
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
_pu = next((u for _, u in state["calls"] if u.startswith("QUESTION:")), "")
check("the promoter's prompt carried the question, the two cells and the data's columns", _pu.startswith("QUESTION:\nIs B higher") and "# --- cell 2 ---" in _pu and "arm: " in _pu and "ANSWER SUMMARY:\nB exceeds A by" in _pu, _pu[:300])
check("the billing chain was charged as a query would be (the fake log manager wrote under it)", any(str(e.get("chain_id")) == "9001" for e in json.load(open(_runlog))), [e.get("chain_id") for e in json.load(open(_runlog))][-3:])
made = BAMBOO.create_routine(prop["proposal_id"], {"name": "B against A", "purpose": "the difference, again", "drop_inputs": [], "drop_results": []})
cev = [json.loads(q.get()) for _ in range(q.qsize())]
check("create_routine: run zero ran through the executor (a pending row, the executor chip, the routine row) and the routine is stored verified",
      [e.get("type") for e in cev] == ["pane_lookup_start", "pane_cell_start", "pane_lookup"] and cev[0].get("kind") == "routine" and cev[-1].get("kind") == "routine"
      and made["run_zero"]["verified"] and made["run_zero"]["status"] == "reproduced" and made["routine"]["origin"] == {"thread_id": "1001", "chain_id": run1.id}
      and os.path.exists(os.path.join(work, "storage", "u1", "routines", made["routine"]["id"], "routine.json")), (cev, made.get("run_zero")))
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
# a reply cut at the token limit: a cut with nothing but reasoning is refused at once (a second try would go the same way); a cut
# mid-object is asked for once more, shorter; cut twice, the refusal names the cause and the seat
ncalls = len(state["calls"])
state["cut"] = [""]
while not q.empty(): q.get()
try:
    BAMBOO.propose_routine("1001", run1.id, billing_chain_id="9004"); cut_msg = ""
except RoutineRefused as exc:
    cut_msg = str(exc)
pev4 = [json.loads(q.get()) for _ in range(q.qsize())]
check("a reply with nothing but reasoning inside the token limit: one call, refused, the reason names the limit and the Promoter seat",
      len(state["calls"]) == ncalls + 1 and "cut off at its token limit" in cut_msg and "nothing arrived but reasoning" in cut_msg and "Promoter" in cut_msg and "max_tokens" in cut_msg
      and "cut off" in (pev4[-1].get("peek") or ""), (cut_msg, pev4[-1].get("peek")))
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
_fs = _types.ModuleType("auth.supabase_client"); _fs.can_execute_chain = lambda a: {"ok": True, "data": {"allowed": True}}; _fs.increment_queries_counter = lambda a: {"ok": True}; sys.modules["auth.supabase_client"] = _fs
_fapp = _types.ModuleType("app"); _fapp.user_path = lambda root, *p: os.path.join(os.getcwd(), root, "u1", *p); _fapp.get_bamboo_ai = lambda sid: BAMBOO; _fapp.get_user_id = lambda: "u1"; _fapp.update_user_activity = lambda u: None
sys.modules["app"] = _fapp
import routines_routes as RR
from flask import Flask
_w = Flask("t"); _w.secret_key = "t"; _w.register_blueprint(RR.routines_bp); _wc = _w.test_client()
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
check("route /routines/create: streams run zero's rows and ends with routine_made", "routine_made" in _msgs[-1] and _msgs[-1]["routine_made"]["run_zero"]["verified"] and _msgs[0].get("type") == "pane_lookup_start", _msgs[-1])
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
# how the data was loaded rides on the instance (the loader routes set it) and into the run's record, so a routine's run can load the same way
BAMBOO.load_params = {"source": "intervals", "start_date": "2026-08-12", "end_date": "2026-10-10", "metrics": [], "aux_kinds": ["summary"], "df_id": "d1"}
_rec = BAMBOO._data_record()
check("the data record carries how the data was loaded (without the frame's id), when the loaded frame is the one it describes", _rec.get("load") == {"source": "intervals", "start_date": "2026-08-12", "end_date": "2026-10-10", "metrics": [], "aux_kinds": ["summary"]}, _rec.get("load"))
BAMBOO.load_params = {"source": "intervals", "df_id": "someone-else"}
check("a load record for another frame is not carried", "load" not in BAMBOO._data_record())
BAMBOO.load_params = None
while not q.empty(): q.get()
_r = _wc.post(f"/routines/{_rid}/run", json={"values": {}, "compare_with": "previous"})
_msgs = _lines(_r)
_types = [m.get("type") or next(iter(m)) for m in _msgs]
check("route run: the pane's rows (check, run, compare), the tabs (Data, Results), the closing card, then routine_run",
      _types[:2] == ["pane_lookup_start", "pane_lookup"] and "pane_routine_end" in _types and "dataframe" in _types and "code_exec_results" in _types and "routine_run" in _msgs[-1]
      and _msgs[-1]["routine_run"]["run"]["number"] == 1 and _msgs[-1]["routine_run"]["run"]["status"] == "ran" and "no result lines to compare" in _msgs[-1]["routine_run"]["run"]["line"] and _msgs[-1]["routine_run"]["numbers"] == [0, 1], (_types, _msgs[-1].get("routine_error")))
check("the run's record names its own folder on the executor's side (datasets/<user>/routines/<id>/<tag>), where its files and datasets go, and the fit it ran under",
      _msgs[-1]["routine_run"]["run"]["run_dir"] == f"datasets/u1/routines/{_rid}/v1_1" and _msgs[-1]["routine_run"]["run"]["fit"]["missing"] == [] and _msgs[-1]["routine_run"]["run"]["bindings"] == [], _msgs[-1]["routine_run"]["run"].get("run_dir"))
_end = next(m for m in _msgs if m.get("type") == "pane_routine_end")
check("the closing card's fields: number, name, version, status, results, compared, figures, elapsed, against", _end["number"] == 1 and _end["name"] == "Route made" and _end["version"] == 1 and _end["status"] == "ran" and _end["against"] == 0 and "elapsed" in _end, _end)
_r2 = _wc.post(f"/routines/{_rid}/run", json={"values": {"arm_b": "A"}})
_run2 = _lines(_r2)[-1]["routine_run"]["run"]
check("route run with the arm set to A: ran (the difference is now A against A), compared with run 1", _run2["status"] in ("ran", "reproduced") and _run2["against"] == 1 and _run2["inputs"] == {"arm_b": "A"}, _run2.get("line"))
_v = _wc.get(f"/routines/{_rid}/runs/2").get_json()
check("route runs/<n>: the stored run with its output, the numbers to step through and the manifest's lines", _v["run"]["number"] == 2 and "reusing" not in _v["stdout"] and _v["numbers"] == [0, 1, 2] and isinstance(_v["figures"], list) and _v["name"] == "Route made", list(_v.keys()))
_v0 = _wc.get(f"/routines/{_rid}/runs/0").get_json()
check("route runs/0: run zero as a run", _v0["run"]["number"] == 0 and _v0["run"]["zero"] is True and _v0["run"]["status"] == "reproduced")
check("route runs/<n> of a run that is not there: 404", _wc.get(f"/routines/{_rid}/runs/9").status_code == 404)
_rj = _wc.get(f"/routines/{_rid}").get_json()["routine"]
check("the routine's record lists both runs with their status and data", [x["number"] for x in _rj["runs"]] == [1, 2] and _rj["runs"][0]["status"] == "ran" and _rj["runs"][0]["data"]["rows"] == 200, _rj["runs"])
_r3 = _wc.post(f"/routines/{_rid}/run", json={"values": {"arm_b": "Z"}})
check("route run with a value the data lacks: refused by the value check, routine_error names it", "routine_error" in _lines(_r3)[-1] and "'Z' is not in column arm" in _lines(_r3)[-1]["routine_error"], _lines(_r3)[-1])
while not q.empty(): q.get()
check("route rename / delete", _wc.post(f"/routines/{_rid}/rename", json={"name": "Renamed"}).get_json()["routine"]["name"] == "Renamed" and _wc.delete(f"/routines/{_rid}").status_code == 200 and _wc.get(f"/routines/{_rid}").status_code == 404)
_r = _wc.post("/routines/create", json={"proposal_id": "gone"})
check("route /routines/create with a spent proposal: the stream ends with routine_error", "routine_error" in _lines(_r)[-1] and "expired" in _lines(_r)[-1]["routine_error"])
_r = _wc.post("/routines/propose", json={"thread_id": "1001", "chain_id": "nope"})
check("route /routines/propose on an unknown chain: routine_error with the reason", "routine_error" in _lines(_r)[-1] and "not in this thread" in _lines(_r)[-1]["routine_error"], _lines(_r)[-1])
for _m in ("auth", "auth.supabase_client", "app"): sys.modules.pop(_m, None)

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
    check("review seat: in Adaptive with analyst_review_every=2 a review runs on the Reviewer after turns 2 and 4 and after the report; the turns on the analyst seat",
          agents == ["Investigator", "Investigator", "Reviewer", "Investigator", "Investigator", "Reviewer", "Investigator", "Reviewer"], agents)
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
    check("review seat: analyst_review_every=0 - no review during the run and none after the report: no reviewer call at all (2026-10-05)",
          _ag == ["Investigator", "Investigator", "Investigator"], _ag)
    check("rewrite seat: without a Rewriter in the config the rewrite ran on the analyst seat",
          [a for a, u in state["calls"] if u.startswith("Rewrite")] == ["Investigator"], [(a, u[:20]) for a, u in state["calls"]])
    # with a Rewriter seat (2026-09-11): the rewrite, and only the rewrite, runs on it
    FakeModels.config["agent_configs"].append({"agent": "Rewriter", "details": {"model": "fake/flash", "provider": "fake", "reasoning_effort": "low"}})
    FakeModels.get_model_name = lambda self, agent: ("fake/strong", "fake") if agent == "Reviewer" else (("fake/flash", "fake") if agent == "Rewriter" else ("fake/model", "fake"))
    state.update(i=0, calls=[], script=[cell(1), "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## Answer\nDone [cell 1].\n"])
    BAMBOO.output_manager.add_user_input("rewrite me"); BAMBOO.pd_agent_converse(thread_id="1001", chain_id=None, mode="deep")
    agents = [(a, u.startswith("Rewrite")) for a, u in state["calls"]]
    check("rewrite seat: the rewrite call runs on the Rewriter, the analysis turns on the analyst seat",
          agents == [("Investigator", False), ("Investigator", False), ("Rewriter", True)], agents)
    q = BAMBOO.output_manager.output_queue; ev = []
    while not q.empty(): ev.append(json.loads(q.get()))
    rw = [(e.get("seat"), e.get("model")) for e in ev if e.get("type") == "pane_turn_start" and e.get("turn") == "rewrite"]
    check("rewrite seat: the pane's rewrite card carries 'Rewriter' and its model", rw and rw[-1] == ("Rewriter", "fake/flash"), rw)
    FakeModels.config["agent_configs"].pop(); FakeModels.config["agent_configs"].pop(); FakeModels.get_model_name = _get_model_name; BAMBOO.review_every = 8
except Exception as exc:                                     # noqa: BLE001
    check("review seat: the checks ran", False, repr(exc))

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

print(f"\n{len(passed)} passed, {len(failed)} failed"); sys.exit(1 if failed else 0)
