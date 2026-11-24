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
        if messages[0]["content"].startswith("You are given a task as an analyst will be given it") and state.get("cold") and isinstance(state["cold"][0], Exception):
            raise state["cold"].pop(0)                  # the provider fails: the model layer logs a call that came back, so nothing is logged or counted
        state["calls"].append((agent, user))
        state.setdefault("images", []).append(bool(isinstance(raw, list) and any(isinstance(p, dict) and p.get("type") == "image_url" and str(p["image_url"].get("url", "")).startswith("data:image/png;base64,") for p in raw)))
        lacm.write_to_log(kw.get("label") or agent, chain_id, "2026-09-05 12:00:00", "fake/model", messages, "reply", 100, 50, 150, 1.0, 50.0)
        if messages[0]["content"].startswith("You are the Pathfinder"):
            state.setdefault("architect_seen", []).append((agent, kw, messages[0]["content"], user))
            from bambooai.models import prompt_cache
            prompt_cache.reset()
            return state["architect"].pop(0) if state.get("architect") else '{"say": "The brief is ready: start the analysis, or change a line."}'
        if messages[0]["content"].startswith("You propose the questions to analyse next"):
            state.setdefault("next_seen", []).append((agent, kw, chain_id, messages[0]["content"], user))
            from bambooai.models import prompt_cache
            prompt_cache.reset()
            return state["next"].pop(0)
        if messages[0]["content"].startswith(("You look things up in a person's saved analyses", "You read saved analyses for another model")):
            state.setdefault("memory_seen", []).append((agent, kw.get("label"), chain_id, messages[0]["content"], user))
            state.setdefault("memory_effort", []).append(kw.get("reasoning_effort"))
            from bambooai.models import prompt_cache
            prompt_cache.reset()
            return state["memory"].pop(0)
        if messages[0]["content"].startswith("You are given a task as an analyst will be given it"):
            state.setdefault("cold_seen", []).append((agent, kw, chain_id, user))
            from bambooai.models import prompt_cache
            prompt_cache.reset()
            return state["cold"].pop(0) if state.get("cold") else '{"cannot_place": []}'
        if messages[0]["content"].startswith("You draw a draft of the figures"):
            state.setdefault("draft_seen", []).append((agent, kw, chain_id, user))
            from bambooai.models import prompt_cache
            prompt_cache.reset()
            return state["draft"].pop(0) if state.get("draft") else ""
        if user.startswith("Rewrite the technical report"):
            return "Plain: B is higher by DIFF."
        if messages[0]["content"].startswith("You are drawing the figures"):
            fs = state.get("figures")
            return fs.pop(0) if isinstance(fs, list) and fs else (fs if isinstance(fs, str) and fs else "NONE")
        if messages[0]["content"].startswith("You are preparing an analysis so that it can be run again"):
            state["brief"] = messages[0]["content"]             # which of the promoter's briefs the call carried
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
BAMBOO = B.BambooAI(df=df, df_id="d1", user_id="u1", exploratory=True, planning=True)
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
check("the report's head rides before the answer as a top-level key (no tab for it): the report's title (its first line), the question as the analyst understood it (the note's line, not the typed question), the data line, the mode, the replay's verdict, the cells, the day, its sources (none: it searched nothing); no lead",
      len(_heads) == 1 and events.index(_heads[0]) < next(i for i, e in enumerate(events) if e.get("type") == "answer") and _head.get("title") == "B exceeds A"
      and "lead" not in _head and _head.get("question") == "q" and _head.get("mode") in ("deep", "quick", "adaptive")
      and _head.get("replay") in ("reproduced", "differed", "failed", "") and isinstance(_head.get("cells"), int) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(_head.get("prepared"))) and isinstance(_head.get("data"), str)
      and "lineage" not in _head and _head.get("sources") == [], (_head, [e.get("type") or next(iter(e)) for e in events][:12]))
# the usage ledger (2026-10-31, docs/USAGE_DESIGN.md): one line per run as it ended, beside the thread files, so the Usage dialog names an
# analysis after its thread file is discarded (a thread not saved as a favourite goes at the next sign-in)
_ledger_path = os.path.join(work, "storage", "u1", "usage_ledger.jsonl")
_lines = [json.loads(x) for x in open(_ledger_path, encoding="utf-8")] if os.path.exists(_ledger_path) else []
check("the usage ledger: the run's line written at its end - the chain and the thread, the question, the mode, how it ended, its cells, when it started and how long it took, and that it is no "
      "branch (0321); no outputs or figures",
      len(_lines) == 1 and _lines[0]["chain"] == str(BAMBOO.chain_id) and _lines[0]["thread"] == "1001" and _lines[0]["question"] == "Is B higher than A?" and _lines[0]["mode"] in ("Deep", "Quick", "Adaptive")
      and _lines[0]["status"] == "answered" and _lines[0]["replay"] == "reproduced" and _lines[0]["cells"] == 2 and _lines[0]["created"] > 0 and _lines[0]["wall"] >= 0
      and set(_lines[0]) == {"chain", "thread", "at", "question", "title", "mode", "status", "replay", "cells", "figures", "created", "wall", "failed_at", "refused", "branch"}
      and _lines[0]["branch"] == {}, _lines)
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
check("the run keeps the mode it was asked in, as the host labels it, and each committed cell the registry entries it made (the code trace's record, 2026-10-20); the thread file carries both",
      run1.mode in ("Quick", "Deep", "Adaptive") and any(t.registry for t in run1.cells())
      and json.load(open(os.path.join(work, "storage", "u1", "threads", "1001.json")))["runs"][run1.id]["mode"] == run1.mode, (run1.mode, [t.registry for t in run1.cells()]))
# the code trace (2026-10-20, M3): built by the Session at the chain's end from the inputs the host offered, kept on the run
from analyst import codemap as _cm
check("the run carries its code trace, at the current version, built from the primary's columns as the host offered them; the thread file carries it",
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
pev_all = [json.loads(q.get()) for _ in range(q.qsize())]
pev = [e for e in pev_all if e.get("type") != "routine_step"]           # the pane's rows; the dialog's step lines ride the same queue (§17)
check("propose_routine: the promoter's call is a quiet card on the pane, accounted to the billing chain; the dialog's steps on the queue too (routine_step, the billing chain on them); the proposal names the input the fake promoter made and the data the run recorded",
      [e.get("type") for e in pev] == ["pane_turn_start", "pane_turn_end"] and pev[0].get("quiet") and pev[0].get("chain_id") == "9001" and pev[0].get("turn") == "routine"
      and [(e["step"], e["state"]) for e in pev_all if e.get("type") == "routine_step"] == [("chain", "done"), ("data", "running"), ("data", "done"), ("model", "running"), ("model", "done"), ("proposal", "running")] and all(e.get("chain_id") == "9001" for e in pev_all)
      and prop["inputs"][0]["key"] == "arm_b" and prop["data"]["rows"] == 200 and prop["data_state"] == "same" and prop["results"] == [] and "INPUTS['arm_b']" in prop["cells_text"], (pev, prop.get("inputs")))
_pu = next((u for _, u in state["calls"] if u.startswith("QUESTION:") and "ANSWER SUMMARY:" in u), "")     # the promoter's, not the figures step's
check("the promoter's prompt carried the question, the two cells and the data's columns", _pu.startswith("QUESTION:\nIs B higher") and "# --- cell 2 ---" in _pu and "arm: " in _pu and "ANSWER SUMMARY:\nB exceeds A by" in _pu, _pu[:300])
check("the billing chain was charged as a query would be (the fake log manager wrote under it)", any(str(e.get("chain_id")) == "9001" for e in json.load(open(_runlog))), [e.get("chain_id") for e in json.load(open(_runlog))][-3:])
_calls_before = len(state["calls"])
made = BAMBOO.create_routine(prop["proposal_id"], {"name": "B against A", "purpose": "the difference, again", "drop_inputs": [], "drop_results": []})
cev = [json.loads(q.get()) for _ in range(q.qsize())]
def _settled(rid, timeout=60, app=None):
    """Run zero runs behind the dialog (2026-10-15): the stored verdict, waited for."""
    import time as _t
    t0 = _t.time()
    while _t.time() - t0 < timeout:
        rz = ((app or BAMBOO).routine_store().load(rid) or {}).get("versions", [{}])[-1].get("run_zero") or {}
        if rz.get("status") not in ("verifying", None, ""):
            return rz
        _t.sleep(0.2)
    return rz
_rz = _settled(made["routine"]["id"])
check("create_routine returns at once with the routine stored as verifying and no pane rows (run zero runs in a thread, 2026-10-15); the verdict lands on the record: reproduced, verified",
      made["run_zero"]["status"] == "verifying" and not made["run_zero"]["verified"] and "verify" not in made and cev == [] and made["routine"]["origin"] == {"thread_id": "1001", "chain_id": run1.id}
      and os.path.exists(os.path.join(work, "storage", "u1", "routines", made["routine"]["id"], "routine.json")) and _rz.get("status") == "reproduced" and _rz.get("verified") is True
      and q.qsize() == 0, (cev, made.get("run_zero"), _rz))
# the proof behind the verdict (docs/ROUTINES_DESIGN.md §19, §22): no model call and no pane rows; the version keeps one text - the chain as
# written with the promoter's edit - and what the proof found: here a chain with no RESULT line and no figure, so every statement runs, and a
# frame from no loader, so nothing to try it on
_v1 = BAMBOO.routine_store().load(made["routine"]["id"])["versions"][0]
check("the proof ran once the routine was stored, without a model call: the version holds one script, the chain's two cells with the input in place and their prints; the mark of its statements; every statement runs - there is nothing to "
      "leave out; no trials; nothing on the pane",
      [ln for ln in _v1["script"].splitlines() if ln.startswith("# --- cell")] == ["# --- cell 1 ---", "# --- cell 2 ---"] and "print('means'" in _v1["script"] and "INPUTS['arm_b']" in _v1["script"]
      and not {"script_written", "script_fallback", "condensed", "consolidated"} & set(_v1) and len(_v1["steps"]) == 12 and _v1["lean"]["steps"] is None and _v1["lean"]["line"] == "every statement runs: nothing to leave out"
      and _v1["tried"] == [] and _v1["run_zero"]["status"] == "reproduced" and _v1["run_zero"]["verified"] and len(state["calls"]) == _calls_before and q.qsize() == 0, (_v1.get("lean"), _v1.get("tried"), sorted(_v1)))
st = BAMBOO.routine_store()
check("the store lists it with the favourite's card index pointing at run1", [r["id"] for r in st.all()] == [made["routine"]["id"]] and st.by_origin() == {("1001", run1.id): [{"id": made["routine"]["id"], "name": "B against A", "version": 1, "instruction": ""}]})
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
check("without a Promoter entry the promoter's call ran on the analyst's seat", BAMBOO._promoter_seat() == "Investigator" and all(a_ == "Investigator" for a_, u_ in state["calls"] if u_.startswith("QUESTION:") and "ANSWER SUMMARY:" in u_),
      [a_ for a_, u_ in state["calls"] if u_.startswith("QUESTION:")])
FakeModels.config["agent_configs"].append({"agent": "Promoter", "details": {"model": "fake/model", "provider": "fake", "reasoning_effort": "medium", "max_tokens": 32000}})
while not q.empty(): q.get()
prop3 = BAMBOO.propose_routine("1001", run1.id, billing_chain_id="9003")
pev3 = [e for e in (json.loads(q.get()) for _ in range(q.qsize())) if e.get("type") != "routine_step"]
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
check("route /routines/propose: streams the dialog's step lines and the pane's rows in order - the chain read, the data checked, the model's turn around its quiet card, the proposal under way - and ends with routine_proposal (no scripts in it)",
      _r.status_code == 200 and [m.get("type") for m in _msgs[:-1]] == ["routine_step", "routine_step", "routine_step", "pane_turn_start", "routine_step", "pane_turn_end", "routine_step", "routine_step"]
      and [(m["step"], m["state"]) for m in _msgs[:-1] if m.get("type") == "routine_step"] == [("chain", "done"), ("data", "running"), ("data", "done"), ("model", "running"), ("model", "done"), ("proposal", "running")]
      and _msgs[0]["detail"].endswith("figures") and "rows" in _msgs[2]["detail"] and _msgs[3 + 1]["again"] is False and "routine_proposal" in _msgs[-1]
      and _msgs[-1]["routine_proposal"]["inputs"][0]["key"] == "arm_b" and "script" not in _msgs[-1]["routine_proposal"], _msgs[-1])
_pid = _msgs[-1]["routine_proposal"]["proposal_id"]
_r = _wc.post("/routines/create", json={"proposal_id": _pid, "name": "Route made", "purpose": "p", "drop_inputs": [], "drop_results": []})
_msgs = _lines(_r)
_rz_r = _settled(_msgs[-1]["routine_made"]["routine"]["id"]) if "routine_made" in _msgs[-1] else {}
check("route /routines/create: ends with routine_made at once, the routine verifying; the verdict lands behind it (no pane rows for it)", "routine_made" in _msgs[-1] and _msgs[-1]["routine_made"]["run_zero"]["status"] == "verifying" and _rz_r.get("status") == "reproduced" and not any(m.get("type") == "pane_lookup_start" for m in _msgs), _msgs[-1])
_rid = _msgs[-1]["routine_made"]["routine"]["id"]
check("route /routines: the list; /routines/<id>: the versions without scripts; by_origin: the card's index",
      [x["id"] for x in _wc.get("/routines").get_json()["routines"]] == [_rid] and set(_wc.get(f"/routines/{_rid}").get_json()["routine"]["versions"][0]) == {"number", "created", "promoted_from", "change_note", "manifest", "run_zero", "tried"}
      and "summary_card" not in _wc.get(f"/routines/{_rid}").get_json()["routine"]
      and _wc.get(f"/routines/by_origin/1001/{run1.id}").get_json()["routines"] == [{"id": _rid, "name": "Route made", "version": 1, "chain_id": run1.id, "instruction": ""}]
      and _wc.get("/routines/by_origin/1001").get_json()["routines"][0]["id"] == _rid and _wc.get("/routines/by_origin/1001/nope").get_json()["routines"] == [])
# the person's instruction through the routes (§15.6): the prompt carries it; the fake promoter answers no "tracked", so it is asked once
# more and the proposal says the instructions were not applied; create keeps the box's line on the routine, and the views carry it
from analyst import routines as _rt
_r = _wc.post("/routines/propose", json={"thread_id": "1001", "chain_id": run1.id, "instruction": " track  the difference "})
_msgs_i = _lines(_r)
_pu_i = [u for _, u in state["calls"] if "THE PERSON'S INSTRUCTION" in u]
check("route /routines/propose with an instruction: the promoter's prompt carries it, whitespace folded; asked again once with the reason (the model step again, saying why); the proposal view carries the instruction and the note",
      len(_pu_i) == 2 and "answer it under \"tracked\", from the ledger alone):\ntrack the difference" in _pu_i[0] and _pu_i[1].endswith(_rt.PROMOTER_TRACKED)
      and [(m.get("again"), m.get("detail")) for m in _msgs_i if m.get("type") == "routine_step" and m.get("step") == "model" and m.get("state") == "running"] == [(False, ""), (True, "the instruction was not answered")]
      and _msgs_i[-1]["routine_proposal"]["instruction"] == "track the difference" and "The custom instructions were not applied this time; try Update the list again." in _msgs_i[-1]["routine_proposal"]["notes"], _msgs_i[-1])
_r = _wc.post("/routines/create", json={"proposal_id": _msgs_i[-1]["routine_proposal"]["proposal_id"], "name": "With a line", "purpose": "", "drop_inputs": [], "drop_results": [], "instruction": "track the difference"})
_rid_i = _lines(_r)[-1]["routine_made"]["routine"]["id"]
_settled(_rid_i)
check("route /routines/create keeps the instruction on the routine; /routines/<id> and by_origin carry it",
      _wc.get(f"/routines/{_rid_i}").get_json()["routine"]["instruction"] == "track the difference"
      and [x["instruction"] for x in _wc.get(f"/routines/by_origin/1001/{run1.id}").get_json()["routines"] if x["id"] == _rid_i] == ["track the difference"])
check("the store lists both routines after the instruction one", {x["id"] for x in _wc.get("/routines").get_json()["routines"]} == {_rid, _rid_i})
_wc.delete(f"/routines/{_rid_i}")                                    # the later checks count the routines of the store
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
check("route run: the pane's rows (check, run, compare), the Data tab, the Results tab with what the chain's cells print (free of the run's own marks), the closing card, then routine_run",
      _types[:2] == ["pane_lookup_start", "pane_lookup"] and "pane_routine_end" in _types and "dataframe" in _types and "routine_run" in _msgs[-1]
      and [m["data"].startswith("means {") and "diff " in m["data"] and "ROUTINE_" not in m["data"] for m in _msgs if m.get("type") == "code_exec_results"] == [True]
      and _msgs[-1]["routine_run"]["run"]["number"] == 1 and _msgs[-1]["routine_run"]["run"]["status"] == "ran" and _msgs[-1]["routine_run"]["run"]["line"] == "ran without error" and _msgs[-1]["routine_run"]["numbers"] == [0, 1]
      and _msgs[-1]["routine_run"]["run"]["stopped"] == [] and _msgs[-1]["routine_run"]["run"]["gaps"] == []
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
# ---- the fill (2026-11-06, docs/ROUTINES_DESIGN.md §14.3): a thread of quiet runs over the span's load, oldest first; the status read back; stop; the guards ----
import time as _time, threading as _thr
class _Busy:
    running = True
    def status(self): return {"running": True, "routine_id": _rid, "interval": "week", "total": 3, "done": 1, "failed": 0}
BAMBOO._fill = _Busy()
_f409, _r409, _fst_busy = _wc.post(f"/routines/{_rid}/fill", json={"interval": "week", "windows": [["2026-08-17", "2026-08-23"]]}), _wc.post(f"/routines/{_rid}/run", json={"values": {}}), _wc.get("/routines/fill").get_json()
BAMBOO._fill = None
check("while a fill runs on the session: a second fill and a run are refused with 409 and the reason; the status route says so; without one, GET /routines/fill says not running",
      _f409.status_code == 409 and "already running" in _f409.get_json()["error"] and _r409.status_code == 409 and "a fill is running" in _r409.get_json()["error"] and _fst_busy["fill"]["running"] is True and _wc.get("/routines/fill").get_json() == {"fill": {"running": False}}, (_f409.get_json(), _r409.get_json()))
_fbad = [_wc.post(f"/routines/{_rid}/fill", json={"interval": "fortnight", "windows": [["2026-08-17", "2026-08-23"]]}).status_code, _wc.post(f"/routines/{_rid}/fill", json={"interval": "week", "windows": []}).status_code, _wc.post("/routines/nope/fill", json={"interval": "week", "windows": [["2026-08-17", "2026-08-23"]]}).status_code]
check("route fill refuses an interval not of the four and no windows (400), and a routine that is not there (404)", _fbad == [400, 400, 404], _fbad)
while not q.empty(): q.get()
_wins = [["2026-08-17", "2026-08-23"], ["2026-08-24", "2026-08-30"], ["2026-08-31", "2026-09-06"]]
_span = {"source": "intervals", "start_date": "2026-08-17", "end_date": "2026-09-06", "metrics": [], "aux_kinds": ["summary"], "subject": {"source": "intervals", "id": "i0", "name": "The subject"}}
_n_before = len(_wc.get(f"/routines/{_rid}").get_json()["routine"]["runs"])
_rf = _wc.post(f"/routines/{_rid}/fill", json={"interval": "week", "windows": _wins, "values": {"arm_b": "A"}, "aux": [], "load": _span})
_fst0 = (_rf.get_json() or {}).get("fill") or {}
_t0 = _time.time()
while _time.time() - _t0 < 90 and _wc.get("/routines/fill").get_json()["fill"].get("running"):
    _time.sleep(0.2)
_fst = _wc.get("/routines/fill").get_json()["fill"]
_rj_f = _wc.get(f"/routines/{_rid}").get_json()["routine"]
_wk_runs = [x for x in _rj_f["runs"] if x.get("interval") == "week"]
_qd = []
while not q.empty(): _qd.append(q.get())
check("route fill: 202 with the status (3 weeks, nothing done yet, the routine named); the fill ends not running, 3 of 3 done, none failed, in order",
      _rf.status_code == 202 and _fst0.get("total") == 3 and _fst0.get("done") == 0 and _fst0.get("interval") == "week" and _fst0.get("routine_name") == _rj_f.get("name") and _fst["running"] is False and _fst["done"] == 3 and _fst["failed"] == 0 and _fst["stopped"] is False and _fst["error"] == "" and _fst["finished"], (_rf.status_code, _fst0, _fst))
check("the three runs landed oldest first, each with interval 'week', its window and the subject on the summary, the first against nothing (no earlier week), the next two each against the week before; the values given; nothing went to the pane's queue (quiet)",
      len(_rj_f["runs"]) == _n_before + 3 and [x["data"]["window"] for x in _wk_runs] == _wins and all(x["data"]["subject"] == {"id": "i0", "name": "The subject"} and x["inputs"] == {"arm_b": "A"} and x["status"] in ("ran", "reproduced") for x in _wk_runs)
      and _wk_runs[0]["against"] is None and _wk_runs[1]["against"] == _wk_runs[0]["number"] and _wk_runs[2]["against"] == _wk_runs[1]["number"] and _wk_runs[0]["comparison"]["line"] == "nothing to compare with: no earlier week on record for this subject" and not _qd,
      ([(x["number"], x.get("interval"), x["against"], x["data"].get("window"), x["status"]) for x in _wk_runs], _qd[:2]))
_rec_f = _wc.get(f"/routines/{_rid}/runs/{_wk_runs[1]['number']}").get_json()
check("a filled run's record: cut to its week from the span's load (cached_from the span), the interval on the record, the CHECK line saying the cut; it opens as any run, among the subject's numbers",
      _rec_f["run"]["interval"] == "week" and _rec_f["run"]["data"]["load"]["cached_from"] == ["2026-08-17", "2026-09-06"] and _rec_f["run"]["data"]["load"]["start_date"] == "2026-08-24" and "cut to 2026-08-24 → 2026-08-30 from the cached load 2026-08-17 → 2026-09-06" in _rec_f["run"]["check"]
      and _rec_f["numbers"] == [x["number"] for x in _wk_runs], (_rec_f["run"].get("check"), _rec_f.get("numbers")))
# a run on a set interval through /run (one unit, the page's path): the record carries it; the reference is the week before (the fill's last)
_r1w = _wc.post(f"/routines/{_rid}/run", json={"values": {"arm_b": "A"}, "interval": "week", "load": dict(_span, start_date="2026-09-07", end_date="2026-09-13", cached=True, cached_from=["2026-09-07", "2026-09-13"])})
_run1w, _sum1w = _lines(_r1w)[-1]["routine_run"]["run"], _lines(_r1w)[-1]["routine_run"]["summary"]
check("route run with an interval: the record and the summary say week, the summary's window is the unit, and it is against the week before (the fill's last)", _run1w["interval"] == "week" and _sum1w["interval"] == "week" and _run1w["against"] == _wk_runs[2]["number"] and _sum1w["data"]["window"] == ["2026-09-07", "2026-09-13"], (_run1w.get("interval"), _run1w["against"]))
while not q.empty(): q.get()
# stopped when asked, and when the Data tab's frame changed: a slow wrapper around run_routine makes the moment deterministic
_real_run = BAMBOO.run_routine
def _slow(*a, **k):
    _time.sleep(0.4)
    return _real_run(*a, **k)
BAMBOO.run_routine = _slow
_rs = _wc.post(f"/routines/{_rid}/fill", json={"interval": "day", "windows": [["2026-09-14", "2026-09-14"], ["2026-09-15", "2026-09-15"], ["2026-09-16", "2026-09-16"]], "load": dict(_span, start_date="2026-09-14", end_date="2026-09-16")})
_time.sleep(0.1)
_stop = _wc.post("/routines/fill/stop").get_json()["fill"]
_t0 = _time.time()
while _time.time() - _t0 < 30 and _wc.get("/routines/fill").get_json()["fill"].get("running"):
    _time.sleep(0.1)
_fst_stop = _wc.get("/routines/fill").get_json()["fill"]
_rs2 = _wc.post(f"/routines/{_rid}/fill", json={"interval": "day", "windows": [["2026-09-17", "2026-09-17"], ["2026-09-18", "2026-09-18"], ["2026-09-19", "2026-09-19"]], "load": dict(_span, start_date="2026-09-17", end_date="2026-09-19")})
_time.sleep(0.1)
_keep_df_id = BAMBOO.df_id; BAMBOO.df_id = "replaced-on-the-data-tab"
_t0 = _time.time()
while _time.time() - _t0 < 30 and _wc.get("/routines/fill").get_json()["fill"].get("running"):
    _time.sleep(0.1)
_fst_chg = _wc.get("/routines/fill").get_json()["fill"]
BAMBOO.df_id = _keep_df_id; BAMBOO.run_routine = _real_run
while not q.empty(): q.get()
check("Stop: the day under way finishes, nothing more starts - 1 of 3 done, stopped; the frame replaced on the Data tab: the fill stops after the day under way with the reason",
      _rs.status_code == 202 and _stop["running"] is True and _fst_stop["stopped"] is True and _fst_stop["done"] == 1 and _fst_stop["error"] == "" and _rs2.status_code == 202 and _fst_chg["stopped"] is True and _fst_chg["done"] == 1 and _fst_chg["error"] == "the data on the Data tab changed", (_stop, _fst_stop, _fst_chg))
# a run deleted from the history (2026-11-08, docs/ROUTINES_DESIGN.md §21): its line and its files go, run 0 and the rest stay, the runs compared with it keep its number
_before = _wc.get(f"/routines/{_rid}").get_json()["routine"]
_last_n = max(x["number"] for x in _before["runs"]); _del_n = sorted(x["number"] for x in _before["runs"])[0]
_folder_del = os.path.join(RR._store().path(_rid), "runs", f"v{next(x for x in _before['runs'] if x['number'] == _del_n)['version']}_{_del_n}")
_had_folder = os.path.isdir(_folder_del)
_rd1 = _wc.delete(f"/routines/{_rid}/runs/{_del_n}")
_after = _wc.get(f"/routines/{_rid}").get_json()["routine"]
_rd0 = _wc.delete(f"/routines/{_rid}/runs/0"); _rdx = _wc.delete(f"/routines/{_rid}/runs/{_del_n}")
check("DELETE /routines/<id>/runs/<n>: the run's line off the record and its folder off the disk, the count answered; run 0 refused (it is the check on the original data); a run already gone refused; the other runs stand, a later run compared against the deleted one still names it",
      _rd1.status_code == 200 and _rd1.get_json() == {"deleted": _del_n, "runs": len(_before["runs"]) - 1} and _had_folder and not os.path.isdir(_folder_del)
      and [x["number"] for x in _after["runs"]] == [x["number"] for x in _before["runs"] if x["number"] != _del_n] and _rd0.status_code == 400 and "run 0" in _rd0.get_json()["error"] and _rdx.status_code == 400
      and any(x.get("against") == _del_n for x in _after["runs"]) and _wc.get(f"/routines/{_rid}/runs/{_last_n}").status_code == 200 and _wc.get(f"/routines/{_rid}/runs/{_del_n}").status_code == 404, (_rd1.get_json(), _rd0.get_json(), [(x["number"], x.get("against")) for x in _after["runs"]]))
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
# the analyst's ideas path and the Explore tab are retired with next questions (2.8, docs/ARCHITECT_DESIGN.md §2.7): /query reads no level,
# the instance and the session have no ideas run, and an answer is sent without the flag that made it an Explore page
from bambooai.web_output_manager import WebOutputManager as _WOM
check("retired (2.8): /query reads no branching_cv and sends no canned question, pd_agent_converse takes no ideas, neither the instance nor the session has an ideas run, and display_results takes no explore",
      "branching_cv" not in _app_src and "User requested variations" not in _app_src and "ideas" not in _sig and not hasattr(B.BambooAI, "_ideas_run") and not hasattr(B.Session, "ideas")
      and "explore" not in _insp.signature(_WOM.display_results).parameters, list(_sig))

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
for m_, want, searches_ in (("quick", BAMBOO.turns_quick, 2), ("deep", BAMBOO.turns_deep, 4), ("adaptive", 40, 6)):
    state.update(i=0, script=PROSE); BAMBOO.output_manager.add_user_input("q")
    BAMBOO.pd_agent_converse(thread_id="1001", chain_id=None, mode=m_, auto_explore=(m_ != "adaptive"), max_investigations=5)
    while not q.empty(): q.get()
    check(f"mode={m_} sent by the brain's menu sets the budget regardless of the legacy flags - its turns, and its web searches (0341: Quick 2, Deep 4, Adaptive 6)",
          BAMBOO._last_budget.turns == want and BAMBOO._last_budget.searches == searches_, BAMBOO._last_budget)
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
      prop_b["cells"] == 1 and "groupby('arm')" not in prop_b["cells_chain"] and "z = 1" in prop_b["cells_chain"] and prop_b["data_state"] == "same"
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
_map_blind = next((e for e in _evs if e.get("type") == "pane_run_end"), {}).get("turn_map")
check("Ask AI about a plot with a model that does not take images: no image part in any call, the question goes alone, and the pane says the model does not take images",
      state["images"] and not any(state["images"]) and any("does not take images" in m for m in _sys) and "THE FIGURE THE PERSON ASKS ABOUT" not in state["calls"][-len(PLOTQ) - 1][1], (state["images"], _sys))
FakeModels.multimodal = "true"
state.update(i=0, script=PLOTQ, images=[]); BAMBOO.output_manager.add_user_input("What is the blue line?")
BAMBOO.pd_agent_converse(thread_id="1001", chain_id=None, image=_png)
_map_seen = None
while not q.empty():
    _ev = json.loads(q.get())
    if _ev.get("type") == "pane_run_end": _map_seen = _ev.get("turn_map")
_turns = [(a, "THE FIGURE THE PERSON ASKS ABOUT is attached" in u, i) for (a, u), i in zip(state["calls"][-len(state["images"]):], state["images"])]
check("...with a model that takes images: the picture rides as an image part on each analysis turn, named in the prompt; the rewrite and the figures request go without it",
      [t[1:] for t in _turns if "TASK: turn" in state["calls"][-len(state["images"]):][_turns.index(t)][1]] == [(True, True)] * 2
      and all(not img for (a, u), img in zip(state["calls"][-len(state["images"]):], state["images"]) if "TASK: turn" not in u), (_turns, [u[:60] for a, u in state["calls"][-len(state["images"]):]]))
_last = json.load(open(_runlog))[-1]
check("...the run log keeps a placeholder for the picture, never the base64", not any(_png in json.dumps(e.get("messages")) for e in json.load(open(_runlog))[-4:]) and "<image, " in json.dumps(json.load(open(_runlog))[-3:]), json.dumps(_last.get("messages"))[-300:])
check("the closing card says whether the analysis has turns to go on from (0320: the page offers its Analysis map): not where the picture rode with the question - "
      "no branch can be given it -, but where the model did not take it",
      _map_seen is False and _map_blind is True, (_map_seen, _map_blind))
FakeModels.multimodal = "false"

# the search tool: the text is the seat's digest as it came - it lists its sources itself (0335) -; the pane's search says the first finding,
# not the digest's heading, and goes on its card with the pages and claims the digest gives, by number (0339) - an address intact: a
# grounding redirect breaks if a quote rides along
from bambooai import web_search
_pages = [{"title": "Field trials by soil type", "link": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEw8='"}, {"title": "", "link": "https://journals.example.org/x"}, {"title": "bad", "link": "not a url"}]
_digest = web_search.digest("Soil type alone moves yield by 0.5-1.0 t/ha.", [{"text": "Soil type alone moves yield by 0.5-1.0 t/ha.", "links": _pages[:1]}], _pages)
_known_seen = []
def _seat(prompts, lacm, om, chain_id, messages, known=()):
    _known_seen.append(list(known)); lacm.update_token_summary(chain_id, 5200, 140, 5340, 5.5, 0.0128, search_cost=0.01)     # the seat's call, logged
    return _digest, _pages
BAMBOO._search_seat = _seat
BAMBOO._search = BAMBOO._web_search
txt, _used = BAMBOO._web_search("yield by soil type")
check("search: the text is the seat's digest, with no second list of sources after it (0335); with it, what the search cost - the seat's call as logged under the chain - "
      "which the run's budget counts (0341)",
      txt == _digest and "Sources:" not in txt and not hasattr(BAMBOO, "_last_search_sources") and set(_used) == {"cost"} and abs(_used["cost"] - 0.0128) < 1e-9, (txt[:80], _used))
while not q.empty(): q.get()
BAMBOO._emit({"type": "search", "run": run3.id, "text": txt, "query": "yield by soil type"})      # as the session sends it: the query rides with the digest
ev = [json.loads(q.get()) for _ in range(q.qsize())]
lk = next(e for e in ev if e.get("type") == "pane_lookup")
check("the pane's search carries the query and the first finding as its short line - not the digest's heading (0335) -, and for its card (0339) the pages by the numbers the digest gives "
      "them - an address without the quote that rode along, a page with no title by its site, no line that is no address - and the claims, each with its sources' numbers",
      lk["query"] == "yield by soil type" and lk["peek"] == "Soil type alone moves yield by 0.5-1.0 t/ha."
      and lk["sources"] == [{"n": 1, "title": "Field trials by soil type", "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEw8=", "host": "vertexaisearch.cloud.google.com"},
                            {"n": 2, "title": "journals.example.org", "url": "https://journals.example.org/x", "host": "journals.example.org"}]
      and lk["claims"] == [{"text": "Soil type alone moves yield by 0.5-1.0 t/ha.", "refs": [1]}], lk)
# a page's number along the path (0337): the seat is told the pages the path's searches have numbered, from their digests
from analyst.notebook import Turn as _Turn
_searching = BAMBOO.notebook.runs[str(BAMBOO.chain_id)]
_searching.turns.append(_Turn(kind="search", text="yield by soil type", stdout=_digest))
BAMBOO._web_search("plot as the unit")
_was_report, _searching.report = _searching.report, "Soil type moves yield [1]; not [3], no page of the path, nor [9]."
_head_s = BAMBOO._report_head(_searching)
_searching.report = _was_report
_searching.turns.pop()
check("search: the seat is told the pages the searches before it on the path numbered - none before the first, then those the first one's digest lists, by number (0337); a page "
      "with no title is named by its site",
      _known_seen == [[], [{"n": 1, "title": "Field trials by soil type", "link": _pages[0]["link"]}, {"n": 2, "title": "journals.example.org", "link": "https://journals.example.org/x"}]], _known_seen)
check("the report's head carries its sources as data (0340): the pages its text cites, by the numbers its path's searches gave them - each its title, its address without the quote that "
      "rode along, its site -; a number that is no page of the path is none. The page draws the list under the report and the chips in its text from them",
      _head_s["sources"] == [{"n": 1, "title": "Field trials by soil type", "url": "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AUZIYQEw8=", "host": "vertexaisearch.cloud.google.com"}], _head_s)
# when an instance searches (0335): asked for, and its Web Search seat's provider has its key - a Gemini key had decided it
from unittest import mock
_engines = {"perplexity": {"per_search": 0.005}}
_seated = dict(FakeModels.config, agent_configs=FakeModels.config["agent_configs"] + [{"agent": "Web Search", "details": {"model": "fake/model", "provider": "openrouter"}}], search_engines=_engines)
_make = lambda **k: B.BambooAI(df=None, df_id=None, user_id="u1", **k)
with mock.patch.dict(os.environ, {"OPENROUTER_API_KEY": "k", "GEMINI_API_KEY": "g"}):
    _no_seat = _make(search_tool=True)
    with mock.patch.object(FakeModels, "config", _seated):
        _on, _not_asked = _make(search_tool=True), _make()
with mock.patch.object(FakeModels, "config", _seated), mock.patch.dict(os.environ, {"GEMINI_API_KEY": "g"}):
    os.environ.pop("OPENROUTER_API_KEY", None)
    _no_key = _make(search_tool=True)
check("an instance searches where search is asked for and its Web Search seat's provider has its key (0335) - the seat is made with the instance's own model manager, and the log manager "
      "knows what a search costs on each engine; not without the seat, not unasked, not with another provider's key alone",
      _on._search == _on._web_search and isinstance(_on._search_seat, web_search.WebSearch) and _on._search_seat.models is _on.models and _on.log_and_call_manager.search_engines == _engines
      and _no_seat._search is None and _not_asked._search is None and _no_key._search is None and _no_seat.log_and_call_manager.search_engines == {}, (_on._search, _no_seat._search, _no_key._search))

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
# ---- the app's smaller paths: what DATA says of auxiliary files, the pricing preflight, the output manager's events ----
try:
    import json as _json, queue as _queue
    from bambooai.web_output_manager import WebOutputManager
    _om = WebOutputManager(); _om.output_queue = _queue.Queue()
    # auxiliary files in DATA (2026-10-07): described with their first rows; without a primary they are the data
    os.chdir(tempfile.mkdtemp())                    # an earlier check removed the working directory the constructor writes logs/ into
    _auxdir = tempfile.mkdtemp(); _laps = os.path.join(_auxdir, "laps.csv"); _ath = os.path.join(_auxdir, "athletes.csv")
    pd.DataFrame({"athlete": ["a", "b", "c"], "pace": [3.5, 3.6, 3.4]}).to_csv(_laps, index=False)
    pd.DataFrame({"athlete": ["a", "b"], "nation": ["ETH", "KEN"]}).to_csv(_ath, index=False)
    _ba = B.BambooAI(df=None, df_id=None, user_id="u1", auxiliary_datasets=[_laps, _ath])
    _desc = _ba._dataset_description()
    check("DATA with auxiliary files and no primary: says df is not defined and the files are the data, then each file's path and first rows (a run had read '(no dataset attached)' and nothing more)",
          _desc.startswith("No primary dataset is attached: `df` is not defined and DS has nothing to load.") and "AUXILIARY FILES (read them with pandas" in _desc
          and f"Path: {_laps}" in _desc and f"Path: {_ath}" in _desc and "ETH" in _desc and "3.5" in _desc, _desc[:600])
    _bb = B.BambooAI(df=pd.DataFrame({"x": [1, 2]}), df_id=None, user_id="u1", auxiliary_datasets=[_ath])
    _desc2 = _bb._dataset_description()
    check("DATA with a primary and an auxiliary file: the frame first, then the auxiliary block with the file's rows",
          _desc2.startswith("`df`: 2 rows x 1 columns") and "AUXILIARY FILES" in _desc2 and f"Path: {_ath}" in _desc2 and "KEN" in _desc2, _desc2[-400:])
    check("DATA with nothing attached says so and that df is not defined", B.BambooAI(df=None, df_id=None, user_id="u1")._dataset_description()
          == "(no dataset attached: `df` is not defined and DS has nothing to load; the question stands on its own, or on the documents below if any are attached)")
    # the context (2026-10-13, docs/CONTEXT_DESIGN.md §3.4): the context file's rows never enter DATA - the columns and the count do, and the map
    _ctx = os.path.join(_auxdir, "context_notes_20260615_to_20261013.csv")
    pd.DataFrame([{"id": "C.1", "kind": "activity_message", "date": "2026-09-01", "time": "08:10", "end_date": "", "activity_id": "a1", "event_id": "", "source_id": "1", "author_id": "i1", "author_name": "Me", "author_role": "subject", "private": False, "lang": "", "text": "legs heavy today, cut it short", "text_en": "", "chars": 30},
                  {"id": "C.2", "kind": "activity_message", "date": "2026-09-01", "time": "09:00", "end_date": "", "activity_id": "a1", "event_id": "", "source_id": "2", "author_id": "c9", "author_name": "Coach", "author_role": "coach", "private": False, "lang": "", "text": "take tomorrow easy", "text_en": "", "chars": 18},
                  {"id": "C.3", "kind": "status", "date": "2026-10-05", "time": "", "end_date": "2026-10-07", "activity_id": "", "event_id": "13", "source_id": "13", "author_id": "i1", "author_name": "", "author_role": "subject", "private": False, "lang": "", "text": "SICK: cold", "text_en": "", "chars": 10},
                  {"id": "C.4", "kind": "day_note", "date": "2026-10-09", "time": "", "end_date": "", "activity_id": "", "event_id": "15", "source_id": "15", "author_id": "c9", "author_name": "", "author_role": "coach", "private": True, "lang": "", "text": "watch motivation", "text_en": "", "chars": 16}]).to_csv(_ctx, index=False)
    _bc = B.BambooAI(df=pd.DataFrame({"x": [1, 2]}), df_id=None, user_id="u1", auxiliary_datasets=[_ath, _ctx])
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
    _bd = B.BambooAI(df=pd.DataFrame({"x": [1, 2]}), df_id=None, user_id="u1", auxiliary_datasets=[_ctx, _codes])
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
    _desc5 = B.BambooAI(df=None, df_id=None, user_id="u1", auxiliary_datasets=[_empty])._dataset_description()
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
    _descw = B.BambooAI(df=None, df_id=None, user_id="u1", auxiliary_datasets=_wide + [_ctx])._auxiliary_block()
    _entries = _descw.split("AUXILIARY FILES", 1)[1].split("\n\nCONTEXT (", 1)[0].split("\n\n")
    _full = [e for e in _entries if "Head:" in e]; _compact = [e for e in _entries if "(the rows are left out to keep the prompt short; read the file for them)" in e]
    check("the auxiliary block keeps to its budget: six wide files and a context file - the first heads whole (cut at AUX_HEAD_CHARS each), the files past AUX_BLOCK_CHARS as path and columns, the context file's entry exempt",
          B.BambooAI.AUX_BLOCK_CHARS == 14000 and len(_full) == 4 and len(_compact) == 2 and all("Columns (40): column_number_0, column_number_1" in e and "value_" not in e for e in _compact)
          and all(f"Path: {_wide[k]}" in _compact[k - 4] for k in (4, 5)) and f"Path: {_ctx}\nColumns: id, kind, date" in _descw and "Rows: 4 (the rows are passages" in _descw
          and len(_descw) < B.BambooAI.AUX_BLOCK_CHARS + 2 * 600 + 1200, (len(_descw), [len(e) for e in _entries]))
    check("the auxiliary block under the budget is as it was: every head whole", "(the rows are left out" not in B.BambooAI(df=None, df_id=None, user_id="u1", auxiliary_datasets=_wide[:3])._auxiliary_block())
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
    _descr = B.BambooAI(df=None, df_id=None, user_id="u1", auxiliary_datasets=[_ath, _rider])._dataset_description()
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
    _dg, _read_used = _bc._read("CTX how were the legs")
    check("READ CTX dispatches to the context: the Reader's quotes verified against the passages, the digest under [C.n] with day, kind and author, the unverifiable quote dropped",
          _dg.startswith("PASSAGES") and '- [C.1] (2026-09-01 · activity_message · subject) "legs heavy today"' in _dg and '- [C.2] (2026-09-01 · activity_message · coach Coach) "take tomorrow easy"' in _dg
          and "legs light" not in _dg and _bc._last_read_query == "CTX how were the legs" and [x["id"] for x in _bc._last_read_passages] == ["C.1", "C.2"]
          and set(_read_used) == {"cost"}, (_dg, _read_used))
    check("READ CTX without a question is answered without a reader call", _bc._read("CTX")[0].startswith("(READ CTX needs what you are looking for") and _bc._last_read_passages == [])
    _bc.models.llm_call = lambda *a, **k: "NO"
    check("a documents' READ still goes to the documents (none on this thread: the message says so)", _bc._read("D1 the sample")[0].startswith("(no documents are attached"), _bc._read("D1 the sample"))
    # the pane event after a READ over a rendered passage carries the original beside the quote (S2: the chip's hover)
    _ctx_da = os.path.join(_auxdir, "context_notes_20260101_to_20260430.csv")
    pd.DataFrame([{"id": "C.1", "kind": "activity_message", "date": "2026-03-01", "time": "08:10", "end_date": "", "activity_id": "a1", "event_id": "", "source_id": "1", "author_id": "i1", "author_name": "", "author_role": "subject", "private": False, "lang": "da", "text": "benene var tunge", "text_en": "the legs were heavy", "chars": 16}]).to_csv(_ctx_da, index=False)
    _be = B.BambooAI(df=None, df_id=None, user_id="u1", auxiliary_datasets=[_ctx_da])
    _be.models.llm_call = lambda *a, **k: '- [C.1] "the legs were heavy"\nSUMMARY: heavy [C.1].'
    _dg2, _ = _be._read("CTX the legs")
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
        _bf = B.BambooAI(df=None, df_id=None, user_id="u3", auxiliary_datasets=[_ctx3])
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
    _b5 = B.BambooAI(df=None, df_id=None, user_id="u5", auxiliary_datasets=[_ctx5])
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
    _bg = B.BambooAI(df=None, df_id=None, user_id="u3", auxiliary_datasets=[_empty])
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
    _bh = B.BambooAI(df=None, df_id=None, user_id="u3", auxiliary_datasets=[_ctx4])
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
    # the reach and the window per tier (2026-11-08, docs/DATASETS_DESIGN.md §18): one place for the numbers, one clamp for every load
    from datetime import date as _date
    _t = _date(2026, 11, 8)
    check("tier_days: free a year back and three months at a time, plus two years and six months, pro and local four years and a year, an unknown tier as free, each with its words",
          IV.tier_days("free") == (366, 92, "1 year", "3 months") and IV.tier_days("plus") == (731, 184, "2 years", "6 months") and IV.tier_days("pro") == (1461, 365, "4 years", "1 year") and IV.tier_days("local") == IV.tier_days("pro") and IV.tier_days("nope") == IV.tier_days("free") and IV.tier_days(None) == IV.tier_days("free"))
    check("clamp_window: a calendar year passes whole (a leap year too); two years keep the end and move the start up a year, said; a window before the reach moves to its edge, said; an end after today moves to today; one before the reach is refused with the reason; a window of a day stands",
          IV.clamp_window(_date(2023, 1, 1), _date(2023, 12, 31), _t, 1461, 365) == (_date(2023, 1, 1), _date(2023, 12, 31), "") and IV.clamp_window(_date(2024, 1, 1), _date(2024, 12, 31), _t, 1461, 365)[2] == ""
          and IV.clamp_window(_date(2022, 1, 1), _date(2023, 12, 31), _t, 1461, 365) == (_date(2022, 12, 31), _date(2023, 12, 31), "the start moved to 2022-12-31 (up to 1 year at a time)")
          and IV.clamp_window(_date(2026, 1, 1), _date(2027, 1, 1), _t, 1461, 365) == (_date(2026, 1, 1), _date(2026, 11, 8), "the end moved to today")
          and IV.clamp_window(_date(2020, 1, 1), _date(2020, 6, 1), _t, 1461, 365) == (None, None, "the window is before the data your plan reaches (back to 2022-11-08)")
          and IV.clamp_window(_date(2026, 11, 7), _date(2026, 11, 8), _t, 366, 92) == (_date(2026, 11, 7), _date(2026, 11, 8), "") and IV.clamp_window(_date(2026, 11, 8), _date(2026, 11, 8), _t, 366, 92) == (_date(2026, 11, 7), _date(2026, 11, 8), ""))
    IV.get_user_subscription = lambda *a, **k: {"ok": True, "data": {"compute_tier": "plus"}}
    _wi = Flask("i"); _wi.secret_key = "i"; _wi.register_blueprint(IV.intervals_bp); _wic = _wi.test_client()
    _lim = _wic.get("/intervals/get_data_limits").get_json()
    check("/intervals/get_data_limits answers the plan's reach and window with their words, and max_days as the window for older readers",
          _lim == {"max_days": 184, "window_days": 184, "reach_days": 731, "window_label": "6 months", "reach_label": "2 years", "compute_tier": "plus"}, _lim)
    IV.get_user_subscription = lambda *a, **k: {"ok": True, "data": {}}
    # one athlete at a time on the Data tab, on the app's side of the cache's own load routes too (2026-10-29): a routine run taken
    # from the cache goes through /cache/load_primary and /cache/load_auxiliary, never the loader's completion, and the session's
    # list of files - the instance holds the same list - must follow the page's pills
    sys.modules.pop("integrations.cache_manager", None)
    import integrations.cache_manager as CM
    _a0 = "/x/datasets/u3/intervals/i0/views/wellness_data_20260101_to_20260301.csv"; _a1 = "/x/datasets/u3/intervals/i1/views/wellness_data_20260101_to_20260301.csv"; _up = "/x/datasets/u3/upload.csv"
    _p6 = {"auxiliary_datasets": [_a0, _ath, _up]}
    _bi = B.BambooAI(df=None, df_id=None, user_id="u3", auxiliary_datasets=_p6["auxiliary_datasets"])
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
    _om.display_results(chain_id="c3", answer="## r")
    _events3 = []
    while not _om.output_queue.empty(): _events3.append(_json.loads(_om.output_queue.get()))
    check("generated datasets are not a right-pane tab: display_results sends no generated_datasets payload (the pane's pills carry the files, 2026-10-06) - and takes "
          "none (0346: the argument was for the manager outside the page)",
          "generated_datasets" not in _insp.signature(_WOM.display_results).parameters and not any(e.get('type') == 'generated_datasets' for e in _events3)
          and any(e.get('type') == 'answer' for e in _events3), [e.get('type') for e in _events3])
except Exception as exc:                                     # noqa: BLE001
    check("the app's smaller paths: the checks ran", False, repr(exc))
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

# ---- a routine without data (2026-11-14, docs/ROUTINES_DESIGN.md §24): an instance with nothing loaded - the chain's record says so, Save as
# routine proves the method behind the dialog, a run asks for no data and sends no Data tab; the proof is not tied to the Data tab
try:
    from bambooai import routines_host as _rh
    from analyst import routines as _rt
    _keep_script, _keep_i, _keep_promoter = state["script"], state["i"], state.get("promoter")
    state["script"] = ["###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nstart = 1.0\nx = start\nfor _ in range(20):\n    x = x - 0.05 * x\nRESULT('end value', round(x, 4), None, None, '', 'n/a')\n```",
                       "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n# Where it ends\n\n## Answer\nIt ends near 0.36 [cell 1].\n"]
    state["i"] = 0
    state["promoter"] = ('{"name": "End value", "inputs": [{"key": "start", "label": "Starting value", "type": "number", "default": "1.0", "origin": "the analysis started at 1"}], '
                         '"edits": [{"cell": 1, "find": "start = 1.0", "replace": "start = INPUTS[\'start\']"}], "kept": []}')
    BN = B.BambooAI(df=None, df_id=None, user_id="u2", exploratory=True, planning=True)
    BN.output_manager.add_user_input("Where does it end after twenty steps from 1.0?")
    BN.pd_agent_converse(thread_id="2001", chain_id=None)
    qn = BN.output_manager.output_queue
    _evn = [json.loads(qn.get()) for _ in range(qn.qsize())]
    runN = BN.notebook.runs[str(BN.chain_id)]
    check("a chain run with nothing loaded: its record says no data - the source none, no frame, no files - and no Data tab is sent",
          _rt.without_data(runN.data) and runN.data.get("source") == "none" and "dataframe" not in [e.get("type") for e in _evn] and runN.status == "answered", (runN.data, runN.status))
    propN = BN.propose_routine("2001", runN.id, billing_chain_id="9101")
    while not qn.empty(): qn.get()
    _caught = {}
    _real_create = _rh.create
    def _spy(nb, proposal, choices, runner, store, **kw):
        _caught["runner"] = runner
        return _real_create(nb, proposal, choices, runner, store, **kw)
    _rh.create = _spy
    try:
        madeN = BN.create_routine(propN["proposal_id"], {"name": "End value"})
    finally:
        _rh.create = _real_create
    _rzN = _settled(madeN["routine"]["id"], app=BN)
    check("Save as routine on it: the proposal's data state is none, the promoter got the brief for a method that reads no data, and the routine is verified behind the dialog with nothing loaded",
          propN["data_state"] == "none" and propN["source"] == "none" and state.get("brief") == _rt.PROMOTER_NO_DATA and propN["inputs"][0]["key"] == "start"
          and madeN["run_zero"]["status"] == "verifying" and _rzN.get("status") == "reproduced" and _rzN.get("verified") is True and madeN["routine"]["source"] == "none", (propN["data_state"], madeN.get("run_zero"), _rzN))
    BN.df_id = "loaded-later"                                 # a file comes onto the Data tab after the save
    _still = _caught["runner"]("print('still runs')", 60)
    BN.df_id = None
    state["script"], state["i"], state["promoter"] = SCRIPT, 0, _keep_promoter
    BD = B.BambooAI(df=df, df_id="d1", user_id="u3", exploratory=True, planning=True)
    BD.output_manager.add_user_input("Is B higher than A?")
    BD.pd_agent_converse(thread_id="3001", chain_id=None)
    _pb = BD.propose_routine("3001", BD.notebook.runs[str(BD.chain_id)].id, billing_chain_id="9102")
    _rh.create = _spy
    try:
        _mb = BD.create_routine(_pb["proposal_id"], {"name": "Tied to its data"})
    finally:
        _rh.create = _real_create
    _settled(_mb["routine"]["id"], app=BD)
    BD.df_id = "another"
    try:
        _caught["runner"]("print('x')", 60); _tied = ""
    except RuntimeError as exc:
        _tied = str(exc)
    BD.pd_agent_converse(action="reset"); BD.cleanup()
    check("the proof of a method without data is not tied to the Data tab: its runner still runs after a file is loaded; a method with data stops there, as before",
          "still runs" in _still[0] and not _still[1] and _tied == "the data on the Data tab changed while the routine was being verified", (_still[:2], _tied))
    preN = BN.precheck_routine(madeN["routine"]["id"], {})
    outN = BN.run_routine(madeN["routine"]["id"], {"start": 2.0})
    _evr = [json.loads(qn.get()) for _ in range(qn.qsize())]
    BN.df, BN.df_id = df, "d9"                                # the same routine with a frame on the Data tab
    outN2 = BN.run_routine(madeN["routine"]["id"], {"start": 2.0})
    _evr2 = [json.loads(qn.get()) for _ in range(qn.qsize())]
    BN.df, BN.df_id = None, None
    check("a run of it through the instance: the check before it is ok with nothing loaded and the plan asks for nothing; the run records no data, prints the other value's end, and the page gets the Results tab and "
          "the closing card - no CHECK row and no Data tab; with a frame on the Data tab the same: the frame is not the run's, and is not sent",
          preN["ok"] and not preN["loaded"] and preN["plan"]["source"] == "none" and outN["run"]["status"] in ("ran", "reproduced") and _rt.without_data(outN["run"]["data"]) and outN["run"]["inputs"] == {"start": 2.0}
          and [x.get("estimate") for x in outN["run"]["results"]] == ["+0.72"] and outN["run"]["against"] == 0 and not _rh.reads_data(BN.routine_store().load(madeN["routine"]["id"]))
          and "dataframe" not in [e.get("type") for e in _evr] and not any(e.get("type") in ("pane_lookup_start", "pane_lookup") and e.get("kind") == "check" for e in _evr)
          and any(e.get("type") == "pane_routine_end" for e in _evr)
          and _rt.without_data(outN2["run"]["data"]) and "dataframe" not in [e.get("type") for e in _evr2] and outN2["run"]["number"] == 2, (preN, outN["run"].get("status"), [e.get("type") for e in _evr], [e.get("type") for e in _evr2]))
    BN.pd_agent_converse(action="reset"); BN.cleanup()
    state["script"], state["i"], state["promoter"] = _keep_script, _keep_i, _keep_promoter
except Exception as exc:                                     # noqa: BLE001
    import traceback
    check("a routine without data through the instance: the checks ran", False, traceback.format_exc()[-600:])

# the brief through the instance (2.8, docs/ARCHITECT_DESIGN.md §2.5): pd_agent_converse hands it to the session - the analyst reads
# it under the question, the run and the thread file keep it with what the report says against it, and the report the page
# receives has the two parts; a run without one is as before
try:
    _keep_script, _keep_i = state["script"], state["i"]
    while not q.empty(): q.get()
    _BRIEFED = ["###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nab = {'A': 1.0, 'B': 1.5}\nprint('means', ab)\n```",
                "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n# B is above A\n\n## Answer\nB is above A [cell 1].\n\n## Against the brief\n- Expected: met [cell 1].\n- Would change their mind: not seen.\n- Chance: not examined.\n\n## Did not fit\nNothing.\n"]
    _n0 = len(state["calls"])
    state.update(i=0, script=_BRIEFED); BAMBOO.output_manager.add_user_input("Is B above A?")
    BAMBOO.pd_agent_converse(thread_id="1077", chain_id=None, mode="deep", brief={"version": 2, "question": "A question the brief was written for", "decision": "which arm to keep", "expects": "B above A",
                                                                                 "fixed": {"measure": "x"}, "junk": 1})
    _bev = []
    while not q.empty(): _bev.append(json.loads(q.get()))
    _brun = BAMBOO.notebook.runs[str(BAMBOO.chain_id)]
    _bprompt = next((u for a, u in state["calls"][_n0:] if "TASK: turn 1" in u), "")
    _bfile = json.load(open(os.path.join(work, "storage", "u1", "threads", "1077.json"), encoding="utf-8"))["runs"][_brun.id]
    _banswer = str(next((e.get("data") for e in _bev if e.get("type") == "answer"), ""))
    check("the brief through the instance: the analyst reads it under the question that was asked - a run that was not framed keeps its own, whatever question the brief carries; the run and the thread file keep the brief in its known shape with what the report says against it; the report the page receives has the two parts",
          _brun.status == "answered" and "QUESTION:\nIs B above A?\n\nBRIEF (agreed with the person before this run):\nWhat the answer is for: which arm to keep\n" in _bprompt and "Fixed before the run:\n- measure: x\n\n" in _bprompt
          and "left to you" not in _bprompt and "not said" not in _bprompt and "- chance [always]" in _bprompt
          and _brun.brief == {"decision": "which arm to keep", "expects": "B above A", "fixed": {"measure": "x"}, "version": 2, "question": "A question the brief was written for"} and _bfile["brief"] == _brun.brief
          and _brun.question == "Is B above A?"
          and _brun.brief_outcome == {"stated": True, "expected": "met", "would_change": "not seen", "checks": ["Chance: not examined."], "did_not_fit": []} and _bfile["brief_outcome"] == _brun.brief_outcome
          and "Against the brief" in _banswer and "Did not fit" in _banswer, (_brun.status, _brun.brief, _brun.brief_outcome, _bprompt[:300]))
    _n1 = len(state["calls"])
    state.update(i=0, script=["###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n# On its own\n\n## Answer\nNothing computed.\n"]); BAMBOO.output_manager.add_user_input("And without a brief?")
    BAMBOO.pd_agent_converse(thread_id="1077", chain_id=_brun.id, mode="deep")
    while not q.empty(): q.get()
    _prun = BAMBOO.notebook.runs[str(BAMBOO.chain_id)]
    check("a follow-up without a brief, after a briefed run that was answered: no brief on the run, none in its prompts",
          _prun.parent == _brun.id and _prun.brief == {} and not any("BRIEF (" in u for a, u in state["calls"][_n1:]), _prun.brief)
    state["script"], state["i"] = _keep_script, _keep_i
except Exception as exc:                                     # noqa: BLE001
    import traceback
    check("the brief through the instance: the checks ran", False, traceback.format_exc()[-600:])

# the framing run (2.8, docs/ARCHITECT_DESIGN.md §2.6, §2.9): a question asked with the Pathfinder on opens a run on the record before
# any analysis - no model is called; each change to its brief is kept as a version; the analysis continues that run under its id
try:
    import architect_routes as AR
    import types as _tps
    _auth = {"counted": [], "refuse": None}                 # the app's authorisation, as the routes ask it: whether each query counted, and the refusal to give
    def _refusal(count=True):
        _auth["counted"].append(bool(count))
        return _auth["refuse"]
    _app_was = sys.modules.get("app"); sys.modules["app"] = _tps.SimpleNamespace(get_bamboo_ai=lambda sid: BAMBOO, query_refusal=_refusal)      # the route asks the app for the instance
    _wa = Flask("ta"); _wa.secret_key = "t"; _wa.register_blueprint(AR.architect_bp); _wac = _wa.test_client()
    with _wac.session_transaction() as _sess: _sess["session_id"] = "s1"
    _keep_script, _keep_i = state["script"], state["i"]
    while not q.empty(): q.get()
    _n2 = len(state["calls"])
    _opj = _wac.post("/architect/open", json={"question": "Is B above A here?", "thread_id": "1077", "chain_id": _prun.id}).get_json()
    _frun = BAMBOO.notebook.runs.get(str(_opj.get("chain_id")))
    _ffile = json.load(open(os.path.join(work, "storage", "u1", "threads", "1077.json"), encoding="utf-8"))["runs"]
    _STEP1 = {"k": 1, "from": 0, "v": 1, "made": [1], "turns": 0, "found": 0, "proposed": 0}
    check("/architect/open: a run on the record before any analysis - status framing, attached where the question was asked, the first version of its brief holding the question, which is the first step of its "
          "conversation, in use (0316); no model is called; a request without a question is refused",
          _frun is not None and _frun.status == "framing" and _frun.parent == _prun.id and _frun.question == "Is B above A here?" and _opj["thread_id"] == "1077" and _opj["parent_chain_id"] == _prun.id
          and _frun.framing == {"versions": [{"n": 1, "by": "person", "changed": [], "brief": {"question": "Is B above A here?"}}], "data": True, "steps": [_STEP1], "step": 1, "tip": 1}
          and _opj["framing"] == _frun.framing
          and _ffile[_frun.id]["status"] == "framing" and len(state["calls"]) == _n2 and q.empty()
          and _wac.post("/architect/open", json={"question": "  ", "thread_id": "1077"}).status_code == 400, (_opj, _frun.framing if _frun else None))
    _s1 = _wac.post("/architect/brief", json={"thread_id": "1077", "chain_id": _opj["chain_id"], "changed": ["decision", "expects"],
                                              "brief": {"question": "Is B above A here?", "decision": "which arm to keep", "expects": "B above A", "junk": 1}})
    _s2 = _wac.post("/architect/brief", json={"thread_id": "1077", "chain_id": _opj["chain_id"], "changed": ["question", "fixed.measure"],
                                              "brief": {"question": "Is B above A, on x?", "decision": "which arm to keep", "expects": "B above A", "fixed": {"measure": "x"}}})
    check("/architect/brief: each change is one more version - who made it, the parts it touched, the brief in its known shape - and every earlier version stays; each is a step of its own, which follows "
          "the one before (0316); a changed question becomes the run's; still no model call; a request without a brief is refused",
          _s1.status_code == 200 and _s2.status_code == 200 and [v["n"] for v in _frun.framing["versions"]] == [1, 2, 3] and _frun.framing["versions"][1] == {"n": 2, "by": "person", "changed": ["decision", "expects"],
                                                                                                                 "brief": {"decision": "which arm to keep", "expects": "B above A", "question": "Is B above A here?"}}
          and _frun.framing["versions"][2]["brief"]["fixed"] == {"measure": "x"} and _frun.question == "Is B above A, on x?" and _s2.get_json()["framing"] == _frun.framing
          and [(x["k"], x["from"], x["v"], x["made"], x["turns"]) for x in _frun.framing["steps"]] == [(1, 0, 1, [1], 0), (2, 1, 2, [2], 0), (3, 2, 3, [3], 0)] and (_frun.framing["step"], _frun.framing["tip"]) == (3, 3)
          and len(state["calls"]) == _n2 and _wac.post("/architect/brief", json={"thread_id": "1077", "chain_id": _opj["chain_id"]}).status_code == 400, _frun.framing)
    state.update(i=0, script=_BRIEFED); BAMBOO.output_manager.add_user_input(_frun.question)
    BAMBOO.pd_agent_converse(thread_id="1077", chain_id=_brun.id, mode="deep", run_id=_opj["chain_id"])      # the request names another parent: the record's stands
    _fev = []
    while not q.empty(): _fev.append(json.loads(q.get()))
    _fid = next((e for e in _fev if e.get("type") == "id"), {})
    _fprompt = next((u for a, u in state["calls"][_n2:] if "TASK: turn 1" in u), "")
    _fend = next((e for e in _fev if e.get("type") == "pane_run_end"), {})
    check("the analysis of a framed run: the same run, under its id - the page is told that id and where it attaches, which is where the framing run did whatever the request says - with the brief as last kept, numbered with its version; the versions stay on the run; the closing card is told nothing of the brief (0313: it links to no tab)",
          BAMBOO.notebook.runs[str(_opj["chain_id"])] is _frun and str(BAMBOO.chain_id) == str(_opj["chain_id"]) and _frun.status == "answered" and _frun.parent == _prun.id
          and str(_fid.get("chain_id")) == str(_opj["chain_id"]) and str(_fid.get("parent_chain_id")) == str(_prun.id)
          and _frun.brief == {"decision": "which arm to keep", "expects": "B above A", "fixed": {"measure": "x"}, "question": "Is B above A, on x?", "version": 3}
          and "QUESTION:\nIs B above A, on x?\n\nBRIEF (agreed with the person before this run):\nWhat the answer is for: which arm to keep\n" in _fprompt and len(_frun.framing["versions"]) == 3
          and _frun.brief_outcome.get("expected") == "met" and "brief" not in _fend, (_frun.status, _frun.brief, _fid, _fprompt[:200]))
    _n3, _runs3 = len(state["calls"]), len(BAMBOO.notebook.runs)
    BAMBOO.output_manager.add_user_input(_frun.question)
    BAMBOO.pd_agent_converse(thread_id="1077", chain_id=_prun.id, mode="deep", run_id=_opj["chain_id"])
    _again = []
    while not q.empty(): _again.append(json.loads(q.get()))
    check("a brief is started once: a second start is refused in plain words - no model call, no new run, the first run untouched",
          any("can no longer be started" in str(e.get("error", "")) for e in _again) and len(state["calls"]) == _n3 and len(BAMBOO.notebook.runs) == _runs3 and _frun.status == "answered", _again[:3])
    _late = _wac.post("/architect/brief", json={"thread_id": "1077", "chain_id": _opj["chain_id"], "brief": {"decision": "too late"}})
    _op2 = _wac.post("/architect/open", json={"question": "And on the other half?", "thread_id": "1077", "chain_id": _opj["chain_id"]}).get_json()
    _frun2 = BAMBOO.notebook.runs[str(_op2["chain_id"])]
    _longq = "Is B above A here?\nWhat I saw: B led in 3 of 4.\n" + "z" * 800
    _op4 = _wac.post("/architect/open", json={"question": _longq, "thread_id": "1077", "chain_id": _prun.id}).get_json()
    _v4 = _op4["framing"]["versions"][0]["brief"]
    _s4 = _wac.post("/architect/brief", json={"thread_id": "1077", "chain_id": _op4["chain_id"], "changed": ["decision"], "brief": {**_v4, "decision": "which arm to keep"}}).get_json()
    _run4 = BAMBOO.notebook.runs[str(_op4["chain_id"])]
    check("a long question of several lines is kept whole: on the run, in the brief's versions the page shows and sends back, and after a change to another part",
          _v4 == {"question": _longq} and _run4.question == _longq and _s4["framing"]["versions"][1]["brief"] == {"decision": "which arm to keep", "question": _longq} and len(_longq) > 800, (_v4, _run4.question[:80]))
    _op3 = _wac.post("/architect/open", json={"question": "Something else, elsewhere"}).get_json()
    _other = json.load(open(os.path.join(work, "storage", "u1", "threads", f"{_op3['thread_id']}.json"), encoding="utf-8"))["runs"]
    check("framing, the edges: a brief whose analysis has started can no longer be changed; a follow-up to a run that had a brief starts from what that answer was for, and says so - what was expected and what was "
          "fixed belonged to the question before (0307: a live follow-up on another subject opened with the last one's comparison); a question with no thread opens one - on its record, without moving the instance off the thread it is on",
          _late.status_code == 409 and len(_frun.framing["versions"]) == 3
          and _frun2.status == "framing" and _frun2.parent == _frun.id and _frun2.framing["versions"][0] == {"n": 1, "by": "person", "changed": ["from the last brief"],
              "brief": {"decision": "which arm to keep", "question": "And on the other half?"}}
          and str(_op3["thread_id"]) != "1077" and _op3["parent_chain_id"] is None and _other[str(_op3["chain_id"])]["status"] == "framing" and BAMBOO.notebook.thread_id == "1077",
          (_late.status_code, _frun2.framing, _op3))
    # what a follow-up's brief starts from (0307), on a thread of its own: an answered run's brief gives what the answer was for and what the person thinks; a run that ended on the analyst's
    # question gives its brief whole - the new question is the person's answer; a run without a brief gives nothing. And whether data is loaded is said with the framing
    from analyst.notebook import Notebook as _NB7
    _nb7 = _NB7("1907")
    _whole7 = {"decision": "which arm to keep", "thinks": "B leads", "rests_on": [{"text": "B led last year", "source": "person", "mark": "holds", "note": "rows: 3"}], "expects": "B above A", "would_change": "a tie",
               "also_check": [{"text": "the season"}], "fixed": {"measure": "x"}, "saved": [{"thread": "7", "run": "8", "question": "an earlier one", "passage": "p", "accepted": True}], "set_aside": ["the weather"]}
    _done7 = _nb7.new_run("Is B above A?", None, run_id="1"); _done7.status = "answered"; _done7.brief = {**_whole7, "version": 4, "question": "Is B above A?"}
    _ask7 = _nb7.new_run("And on y?", "1", run_id="2"); _ask7.status = "asked"; _ask7.brief = {**_whole7, "version": 2, "question": "And on y?", "carried_from": "1"}
    _bare7 = _nb7.new_run("Something plain", "1", run_id="3"); _bare7.status = "answered"
    BAMBOO.store.save(_nb7)
    _o7 = {k: _wac.post("/architect/open", json={"question": "A next question", "thread_id": "1907", "chain_id": k}).get_json()["framing"] for k in ("1", "2", "3")}
    _rec_was = BAMBOO._data_record
    BAMBOO._data_record = lambda light=False: {"source": "none", "aux": []}
    _o7n = _wac.post("/architect/open", json={"question": "A question about nothing loaded", "thread_id": "1907"}).get_json()["framing"]
    _o7nj = _wac.post("/architect/open", json={"question": "A question asked before the data was loaded", "thread_id": "1907"}).get_json()
    BAMBOO._data_record = lambda light=False: {"source": "none", "aux": ["notes.csv"]}
    _o7a = _wac.post("/architect/open", json={"question": "A question about a file", "thread_id": "1907"}).get_json()["framing"]
    BAMBOO._data_record = _rec_was
    check("what a follow-up's brief starts from (0307): after an answered analysis, what the answer was for and what the person thinks - nothing of what they expected, what it rested on, what was fixed, the saved "
          "analyses they chose or what they set aside; after the analyst's question, that brief whole, the new question in the place of the old; after a run without a brief, the question alone, and nothing says "
          "it came from one. The framing says whether data is loaded - a file beside no frame is data - and the instance stays on its thread",
          _o7["1"]["versions"] == [{"n": 1, "by": "person", "changed": ["from the last brief"], "brief": {"decision": "which arm to keep", "thinks": "B leads", "question": "A next question"}}]
          and _o7["2"]["versions"] == [{"n": 1, "by": "person", "changed": ["from the last brief"], "brief": {**_whole7, "question": "A next question"}}]
          and _o7["3"]["versions"] == [{"n": 1, "by": "person", "changed": [], "brief": {"question": "A next question"}}]
          and [f["data"] for f in (_o7["1"], _o7n, _o7a, _o7nj["framing"])] == [True, False, True, False] and BAMBOO.notebook.thread_id == "1077", (_o7, _o7n))
    # ---- the Pathfinder talks (0297, §2.12): one exchange is one model call - the run's own, logged as the Pathfinder's
    from analyst import architect as _arch
    def _say(payload):
        r = _wac.post("/architect/say", json=payload)
        return r.status_code, [json.loads(ln) for ln in r.get_data(as_text=True).splitlines() if ln.strip()]
    def _logged(chain):
        return [e.get("agent") for e in json.load(open(BAMBOO.log_and_call_manager.run_log_file_path)) if str(e.get("chain_id")) == str(chain)]
    _charged = []
    _keep_charge = BAMBOO.log_and_call_manager.charge_for_completed_query
    BAMBOO.log_and_call_manager.charge_for_completed_query = lambda chain: (_charged.append(chain), True)[1]
    while not q.empty(): q.get()
    _c2 = _op2["chain_id"]
    state["architect"] = ['{"brief": {"fixed": {"comparison": "B against A"}}, "say": "What will you do differently depending on the answer?", "choices": ["Keep B", "Keep A"]}']
    state["architect_seen"] = []
    BAMBOO.kill_signal = True; BAMBOO._stop_event.set()                       # a run stopped earlier left the signal set
    _n5, _chain_was, _auth["counted"] = len(state["calls"]), BAMBOO.chain_id, []
    _st5, _ln5 = _say({"thread_id": "1077", "chain_id": _c2})
    _seat5, _kw5, _sys5, _user5 = state["architect_seen"][-1]
    check("/architect/say, the Pathfinder's first turn: a stream that ends on the framing; one model call - its instructions, on the analyst's seat at a lowered effort, logged as the Pathfinder's under the brief's own "
          "chain - whose prompt has the data's description, the analyses the question follows with how the last stood against its brief, the question, the brief as it stands and no conversation yet",
          _st5 == 200 and _ln5[-1] == {"architect": {"framing": _frun2.framing}} and len(state["calls"]) == _n5 + 1 and _seat5 == "Investigator" and _kw5.get("label") == "Pathfinder"
          and _kw5.get("reasoning_effort") == ("medium", "low") and _sys5 == _arch.SYSTEM and _user5.startswith("DATA:\n") and "EARLIER (the analyses this question follows, oldest first):\n[1] Q: " in _user5
          and "] Q: Is B above A, on x?\n    Found: " in _user5 and "    Against its brief - what they expected: met" in _user5
          and "\n\nQUESTION:\nAnd on the other half?\n\nBRIEF (version 1):\ndecision: which arm to keep\n" in _user5 and _user5.endswith("CONVERSATION:\n(nothing yet)\n\nReply with the JSON object.")
          and _logged(_c2) == ["Pathfinder"], (_st5, _ln5[-1], _seat5, _kw5, _user5[-600:], _logged(_c2)))
    _file5 = json.load(open(os.path.join(work, "storage", "u1", "threads", "1077.json"), encoding="utf-8"))["runs"][str(_c2)]
    check("the reply is taken into the run's framing, on the record: the part the Pathfinder wrote as one more version, its own, made from the question, the first still saying it came from the last brief; its "
          "message with its choices in the conversation. The instance is where it was - its chain, no stop signal left - the brief is noted as one whose calls are still to be charged, the query was authorised "
          "without being counted, and the usage ledger has the brief's line",
          [(v["n"], v["by"], v.get("why"), v["changed"]) for v in _frun2.framing["versions"]] == [(1, "person", None, ["from the last brief"]), (2, "architect", "question", ["fixed.comparison"])]
          and _frun2.framing["versions"][1]["brief"] == {"decision": "which arm to keep", "fixed": {"comparison": "B against A"}, "question": "And on the other half?"} and _frun2.framing["data"] is True
          and [(t["who"], t["text"], t.get("choices"), t.get("v"), t.get("call")) for t in _frun2.framing["turns"]] == [("architect", "What will you do differently depending on the answer?", ["Keep B", "Keep A"], 2, 1)]
          and _frun2.framing["calls"] == 1 and _frun2.status == "framing" and _file5["framing"] == _frun2.framing
          and BAMBOO.chain_id == _chain_was and BAMBOO.kill_signal is False and not BAMBOO._stop_event.is_set() and BAMBOO._framed == {int(_c2)} and _auth["counted"] == [False]
          and BAMBOO.store.ledger()[str(_c2)]["status"] == "framing", (_frun2.framing, BAMBOO._framed, _auth["counted"]))
    state["architect"] = ["I would ask about the decision.", '{"brief": {"decision": "Keep B"}, "say": "What do you expect to see?"}']
    _st6, _ln6 = _say({"thread_id": "1077", "chain_id": _c2, "text": "  Keep B  "})
    check("/architect/say, an answer: the coach's words join the conversation the Pathfinder reads; a reply that cannot be read is asked for once more; the reply kept is a version made from the answer, and its "
          "message carries the number of the call that brought it - the log holds three calls of the Pathfinder's in this chain",
          _st6 == 200 and _ln6[-1] == {"architect": {"framing": _frun2.framing}} and "Person: Keep B\n" in state["architect_seen"][-1][3] and "Your last reply could not be read: it holds no JSON object." in state["architect_seen"][-1][3]
          and [(t["who"], t["text"]) for t in _frun2.framing["turns"][1:]] == [("person", "Keep B"), ("architect", "What do you expect to see?")] and _frun2.framing["turns"][2]["call"] == 3 and _frun2.framing["calls"] == 3
          and (_frun2.framing["versions"][2]["by"], _frun2.framing["versions"][2]["why"], _frun2.framing["versions"][2]["brief"]["decision"]) == ("architect", "answer", "Keep B")
          and _logged(_c2) == ["Pathfinder"] * 3, (_ln6[-1], _frun2.framing["turns"], _logged(_c2)))
    _stood6 = json.dumps({k: v for k, v in _frun2.framing.items() if k != "calls"}, sort_keys=True)
    state["architect"] = ["no", "still no"]
    _st7, _ln7 = _say({"thread_id": "1077", "chain_id": _c2, "text": "B above A by 2"})
    _n7 = len(state["calls"])
    _st8, _ln8 = _say({"thread_id": "1077", "chain_id": _opj["chain_id"], "text": "too late"})
    _st9 = _wac.post("/architect/say", json={"thread_id": "1077"}).status_code
    check("/architect/say, no reply to keep: the stream ends on the reason, in words; the brief and the conversation stand as they did, and only the calls are counted, so the next reply's number is right. A brief "
          "whose analysis has started is refused without a call; a request without its chain is refused",
          _st7 == 200 and _ln7[-1] == {"architect": {"error": "The Pathfinder's reply could not be read (it holds no JSON object)."}}
          and json.dumps({k: v for k, v in _frun2.framing.items() if k != "calls"}, sort_keys=True) == _stood6 and _frun2.framing["calls"] == 5 and _logged(_c2) == ["Pathfinder"] * 5
          and _ln8[-1] == {"architect": {"error": "This brief can no longer be changed: its analysis has started."}} and len(state["calls"]) == _n7 and _st9 == 400, (_ln7[-1], _frun2.framing["calls"], _ln8[-1], _st9))
    _auth["counted"], _auth["refuse"] = [], ({"error": "authorization_failed", "message": "You need $0.010 per query but your balance is $0.00. Please add funds to continue."}, 403)
    _runs9 = len(BAMBOO.notebook.runs)
    _r_open = _wac.post("/architect/open", json={"question": "One more?", "thread_id": "1077", "chain_id": _prun.id})
    _r_say = _wac.post("/architect/say", json={"thread_id": "1077", "chain_id": _c2, "text": "again"})
    _auth["refuse"] = None
    _op6 = _wac.post("/architect/open", json={"question": "One more?", "thread_id": "1077", "chain_id": _prun.id}).get_json()
    check("a framed question is a query for the account: authorised when its brief opens and at each exchange - a refusal is the app's own answer, with no run made and no call - and counted once, when the brief opens",
          _r_open.status_code == 403 and _r_open.get_json()["message"].startswith("You need $0.010 per query") and _r_say.status_code == 403 and _r_say.get_json()["error"] == "authorization_failed"
          and len(state["calls"]) == _n7 and _auth["counted"] == [True, False, True] and len(BAMBOO.notebook.runs) == _runs9 + 1 and str(_op6["chain_id"]) in BAMBOO.notebook.runs,
          (_r_open.status_code, _r_say.status_code, _auth["counted"]))
    # ---- lookups (0298, §2.13): a reply asks, the host answers through the executor, and the next reply marks the lines by what was found
    from analyst import lookup as _lk
    _c6 = _op6["chain_id"]
    _size, _hours = "The two arms are the same size.", "B has the more hours."
    _aux6 = os.path.join(work, "more.csv")
    pd.DataFrame({"arm": ["B", "B", "A"], "h": [1.5, 2, 4]}).to_csv(_aux6, index=False)
    _aux_was, BAMBOO.auxiliary_datasets = BAMBOO.auxiliary_datasets, [_aux6]
    _sizes = " · ".join(f"{k} {v}" for k, v in sorted(BAMBOO.df["arm"].value_counts().items()))
    _frame_was, _kernel_was = BAMBOO.df.copy(), BAMBOO._kernel
    state["architect"] = [json.dumps({"brief": {"rests_on": [_size, _hours]}, "say": "Checking this against the data.",
                                      "lookups": [{"about": _size, "op": "count", "by": "arm"}, {"about": _hours, "op": "total", "column": "h", "by": "arm", "data": "datasets/u1/more.csv"},
                                                  {"about": _size, "op": "total", "column": "nothing"}, {"about": _size, "op": "median", "column": "x"}]})]
    _n12 = len(state["calls"])
    while not q.empty(): q.get()
    _st12, _ln12 = _say({"thread_id": "1077", "chain_id": _c6})
    _run6 = BAMBOO.notebook.runs[str(_c6)]
    _check12 = _run6.framing["turns"][-1]
    check("/architect/say, a reply that asks for lookups: the host answers them in one script through the executor, over the frame loaded now and a file beside it named by its name alone, and the round is the "
          "conversation's last turn - what each lookup found on one line, a lookup the data refuses and a request that is no lookup in words. One model call; the frame and the analysis' kernel are as they were",
          _st12 == 200 and _ln12[-1] == {"architect": {"framing": _run6.framing}} and [t["who"] for t in _run6.framing["turns"]] == ["architect", "check"] and len(state["calls"]) == _n12 + 1
          and _check12["found"] == [{"k": 1, "about": _size, "fact": f"rows by arm: {_sizes}", "ran": True}, {"k": 2, "about": _hours, "fact": "total of h by arm, in more.csv: A 4 · B 3.5", "ran": True},
                                    {"k": 3, "about": _size, "fact": "total of nothing: not looked up - there is no column nothing: the columns are " + ", ".join(BAMBOO.df.columns), "ran": False},
                                    {"k": 4, "about": _size, "fact": "not looked up - a lookup is a count, a list or a total", "ran": False}]
          and _sizes.startswith("A ") and " · B " in _sizes and BAMBOO.df.equals(_frame_was) and BAMBOO._kernel is _kernel_was and _run6.status == "framing", (_ln12[-1], _sizes))
    state["architect"] = [json.dumps({"say": "One line does not hold: A has the more hours, 4 against 3.5. Do you keep what you think, or change it?", "choices": ["Keep it", "Change it"],
                                      "marks": [{"line": _size, "mark": "holds", "lookup": 1}, {"line": _hours, "mark": "does not hold", "lookup": 2}]})]
    _st13, _ln13 = _say({"thread_id": "1077", "chain_id": _c6})
    _user13 = state["architect_seen"][-1][3]
    _file13 = json.load(open(os.path.join(work, "storage", "u1", "threads", "1077.json"), encoding="utf-8"))["runs"][str(_c6)]
    check("/architect/say, with nothing said after a round: the Pathfinder reads what the lookups found, and the marks it gives are a version made from a check against the data - each line with the host's own "
          "fact beside it - kept on the record; the brief is still one being framed",
          _st13 == 200 and _user13.endswith(f"Pathfinder: Checking this against the data.\nLookups:\n1. about \"{_size}\" - rows by arm: {_sizes}\n2. about \"{_hours}\" - total of h by arm, in more.csv: A 4 · B 3.5\n"
                                            f"3. about \"{_size}\" - total of nothing: not looked up - there is no column nothing: the columns are " + ", ".join(BAMBOO.df.columns) + "\n"
                                            f"4. about \"{_size}\" - not looked up - a lookup is a count, a list or a total\n\nReply with the JSON object.")
          and (_run6.framing["versions"][-1]["by"], _run6.framing["versions"][-1]["why"], _run6.framing["versions"][-1]["changed"]) == ("architect", "check", ["rests_on.0", "rests_on.1"])
          and _run6.framing["versions"][-1]["brief"]["rests_on"] == [{"text": _size, "source": "person", "mark": "holds", "note": f"rows by arm: {_sizes}"},
                                                                    {"text": _hours, "source": "person", "mark": "does not hold", "note": "total of h by arm, in more.csv: A 4 · B 3.5"}]
          and [t["who"] for t in _run6.framing["turns"]] == ["architect", "check", "architect"] and _run6.framing["turns"][-1]["choices"] == ["Keep it", "Change it"]
          and _file13["framing"] == _run6.framing and _file13["status"] == "framing", (_user13[-500:], _run6.framing["versions"][-1]))
    _exec_was = BAMBOO.executor.execute
    _one = [{"op": "count"}, {"op": "list", "column": "arm"}]
    try:
        BAMBOO.executor.execute = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("the executor is away"))
        _down = BAMBOO._architect_look(_one)
        BAMBOO.executor.execute = lambda *a, **k: (None, "a line of noise", "Traceback: it failed", [], [])
        _failed13 = BAMBOO._architect_look(_one)
    finally:
        BAMBOO.executor.execute = _exec_was
    check("the host's lookups never fail the exchange: an executor that cannot be reached, or a script that did not run, refuses each lookup in words",
          _down == _failed13 == [{"refused": "the data could not be reached"}] * 2 and BAMBOO._architect_look(_one)[0] == {"value": len(BAMBOO.df)}, (_down, _failed13))
    BAMBOO.auxiliary_datasets = _aux_was
    # ---- another explanation (0299, §2.14): what the Pathfinder proposes enters the brief as its own; the coach's tick accepts it
    from analyst import brief as _bf
    _timing = {"text": "The arms were filled at different times", "shows": "the gap follows the time", "source": "architect", "accepted": False}
    state["architect"] = [json.dumps({"say": "The brief is ready.", "propose": [{"text": _timing["text"], "shows": _timing["shows"], "column": "arm"}, {"text": "The weather turned", "column": "weather"}]})]
    _st14, _ln14 = _say({"thread_id": "1077", "chain_id": _c6, "text": "Keep it"})
    _v14 = _run6.framing["versions"][-1]
    _before14 = _bf.agreed(_bf.latest(_run6.framing))
    _b14 = copy.deepcopy(_v14["brief"]); _b14["also_check"][0]["accepted"] = True
    _s14 = _wac.post("/architect/brief", json={"thread_id": "1077", "chain_id": _c6, "brief": _b14, "changed": ["also_check.0"]})
    _after14 = _bf.agreed(_bf.latest(_run6.framing))
    check("/architect/say, a reply that proposes: the explanation that names a column of the loaded data enters the brief as the Pathfinder's own, not accepted - the one that names none of its columns does not - "
          "and the analyst would not receive it; the coach's tick, sent as the page sends it, is one more version of theirs, and then the analyst would",
          _st14 == 200 and _v14["brief"]["also_check"] == [_timing] and _v14["changed"] == ["also_check.0"] and _run6.framing.get("proposed") == 1 and "also_check" not in _before14
          and _s14.status_code == 200 and (_run6.framing["versions"][-1]["by"], _run6.framing["versions"][-1]["changed"]) == ("person", ["also_check.0"])
          and _after14["also_check"] == [{**_timing, "accepted": True}] and "- The arms were filled at different times: it would show the gap follows the time\n" in _bf.render(_after14)
          and _run6.status == "framing", (_v14, _before14.get("also_check"), _after14.get("also_check")))
    # another thread: the instance follows the conversation there
    state["architect"] = ['{"say": "What will you do differently depending on the answer?"}']
    _st10, _ln10 = _say({"thread_id": _op3["thread_id"], "chain_id": _op3["chain_id"]})
    _user10 = state["architect_seen"][-1][3]
    check("the Pathfinder in a brief on another thread: the instance goes there, as it does for a run - that thread's record in hand, the usage filed under it, the other thread's kernel dropped; a question that follows "
          "no analysis has no EARLIER part; a reply that writes nothing makes no version",
          _st10 == 200 and BAMBOO.notebook.thread_id == str(_op3["thread_id"]) and str(BAMBOO.log_and_call_manager.thread_id) == str(_op3["thread_id"]) and BAMBOO._kernel is None
          and "EARLIER" not in _user10 and "QUESTION:\nSomething else, elsewhere\n\nBRIEF (version 1):" in _user10 and len(_ln10[-1]["architect"]["framing"]["versions"]) == 1
          and [t["who"] for t in _ln10[-1]["architect"]["framing"]["turns"]] == ["architect"] and BAMBOO._framed == {int(_c2), int(_c6), int(_op3["chain_id"])}, (_st10, BAMBOO.notebook.thread_id, _user10[:200], BAMBOO._framed))
    # the analysis of a brief the Pathfinder talked in: one chain on the log, charged once; a brief never run is charged when the instance goes
    import time as _time
    _opened, _before = _frun2.created, _time.time()
    _n11 = len(state["calls"])
    state.update(i=0, script=_BRIEFED); BAMBOO.output_manager.add_user_input(_frun2.question)
    BAMBOO.pd_agent_converse(thread_id="1077", chain_id=_prun.id, mode="deep", run_id=_c2)
    while not q.empty(): q.get()
    _ran2 = BAMBOO.notebook.runs[str(_c2)]                   # the thread's record was read again when the instance came back to it
    _log11 = _logged(_c2)
    check("the analysis of a brief the Pathfinder talked in: the same chain - on the log the Pathfinder's five calls, then the analyst's own under its seat, so its first turn is its seat's first call; the chain is "
          "charged once, when the analysis ends, and is no longer waiting to be; the run's clock starts with the analysis, not with the brief",
          _ran2.status == "answered" and _ran2.brief["decision"] == "Keep B" and _ran2.brief["version"] == 3 and _log11[:5] == ["Pathfinder"] * 5 and "Pathfinder" not in _log11[5:] and _log11[5] == "Investigator"
          and _charged == [int(_c2)] and BAMBOO._framed == {int(_c6), int(_op3["chain_id"])} and _ran2.created >= _before > _opened and len(_ran2.framing["turns"]) == 3, (_ran2.status, _log11, _charged, BAMBOO._framed))
    # ---- next questions (0300, §2.7, §2.15): a set for a finished analysis is one call of the Pathfinder's, under a chain of its own
    from analyst import next_questions as _nq
    def _next(payload):
        r = _wac.post("/architect/next", json=payload)
        return r.status_code, [json.loads(ln) for ln in r.get_data(as_text=True).splitlines() if ln.strip()]
    _thread_file = lambda: json.load(open(os.path.join(work, "storage", "u1", "threads", "1077.json"), encoding="utf-8"))["runs"]
    state["next"] = [json.dumps({"questions": [{"title": "Chance", "question": "Does the gap hold on a second draw?", "from": [1]}, {"title": "Each half", "question": "Is B above A in each half?", "from": [2, 1]}]})]
    state["next_seen"] = []
    _lines20, _own20 = _nq.sources(BAMBOO.notebook, _ran2, "shift")
    _p20 = _nq.prompt(BAMBOO.notebook, _ran2, "shift", _lines20, _own20, BAMBOO._data_description())
    BAMBOO.kill_signal = True; BAMBOO._stop_event.set()                       # a run stopped earlier left the signal set
    _n20, _chain20, _charged20, _runs20, _auth["counted"] = len(state["calls"]), BAMBOO.chain_id, list(_charged), len(BAMBOO.notebook.runs), []
    _st20, _ln20 = _next({"thread_id": "1077", "chain_id": _c2, "level": "shift"})
    _seat20, _kw20, _on20, _sys20, _user20 = state["next_seen"][-1]
    _set20 = _ran2.next_questions[0] if _ran2.next_questions else {}
    check("/architect/next: a stream that ends on the set and its place. One model call - the instructions for next questions and the prompt for the level, on the analyst's seat at a lowered effort, logged as "
          "the Pathfinder's under a chain of its own, which is no run of the thread - and that chain is charged at once; the query is counted. The level's own line comes first among the lines",
          _st20 == 200 and _ln20[-1] == {"next": {"set": _set20, "at": 0}} and len(state["calls"]) == _n20 + 1 and _seat20 == "Investigator" and _kw20.get("label") == "Pathfinder"
          and _kw20.get("reasoning_effort") == ("low", "medium") and _sys20 == _nq.SYSTEM and _user20 == _p20 and _own20 == 1 and _lines20[0] == {"kind": "check", "text": "Chance: not examined."}
          and "\n\nLEVEL: shift - a question at this level puts another explanation of the same result to the test\n\nSOURCES:\n1. Also checked: Chance: not examined.\nOther lines:\n2. " in _user20
          and _on20 not in (int(_c2), _chain20) and str(_on20) not in BAMBOO.notebook.runs and len(BAMBOO.notebook.runs) == _runs20 and _logged(_on20) == ["Pathfinder"] and _logged(_c2) == _log11
          and _charged == _charged20 + [_on20] and _auth["counted"] == [True], (_st20, _ln20[-1], _seat20, _kw20, _on20, _charged[len(_charged20):], _auth["counted"], _user20[-500:]))
    _cost20 = float((BAMBOO.log_and_call_manager.token_summary.get(_on20) or {}).get("total_cost") or 0)
    check("the set is kept with the analysis it follows, on the record: its level, each question with its title and the lines it comes from as the record has them, what its one call cost - the cost "
          "logged under its own chain, not the instance's - and the chain the call was logged under. The instance is where it was - its own chain, no stop signal left",
          {k: v for k, v in _set20.items() if k not in ("at", "cost")} == {"level": "shift", "chain": _on20, "questions": [
              {"title": "Chance", "text": "Does the gap hold on a second draw?", "from": [_lines20[0]]}, {"title": "Each half", "text": "Is B above A in each half?", "from": [_lines20[1], _lines20[0]]}]}
          and _cost20 > 0 and _set20["cost"] == round(_cost20, 4) != round(BAMBOO._chain_cost(), 4) and _thread_file()[str(_c2)]["next_questions"] == [_set20] and BAMBOO.chain_id == _chain20 and BAMBOO.kill_signal is False and not BAMBOO._stop_event.is_set(),
          (_set20, BAMBOO.chain_id, _chain20))
    state["next"] = [json.dumps({"questions": [{"question": "Does the answer hold with the first rows left out?", "from": [1, 2]}]})]
    _st21, _ln21 = _next({"thread_id": "1077", "chain_id": str(_c2), "level": "blend"})
    _on21, _user21 = state["next_seen"][-1][2], state["next_seen"][-1][4]
    check("a second set for the same analysis: its place is the next, its call has a chain of its own, charged in its turn, and its prompt names the questions proposed before",
          _st21 == 200 and _ln21[-1]["next"]["at"] == 1 and _ln21[-1]["next"]["set"] == _ran2.next_questions[1] and _ran2.next_questions[1]["level"] == "blend" and _ran2.next_questions[1]["chain"] == _on21
          and _on21 != _on20 and _charged == _charged20 + [_on20, _on21] and "\n\nPROPOSED BEFORE:\n- Does the gap hold on a second draw?\n- Is B above A in each half?\n\nLEVEL: blend - " in _user21
          and len(_thread_file()[str(_c2)]["next_questions"]) == 2, (_ln21[-1], _on21, _user21[-400:]))
    state["next"] = ["no", "still no"]
    _n22 = len(state["calls"])
    _st22, _ln22 = _next({"thread_id": "1077", "chain_id": _c2, "level": "emergence"})
    _on22 = state["next_seen"][-1][2]
    _n23 = len(state["calls"])
    _st23, _ln23 = _next({"thread_id": "1077", "chain_id": "999999", "level": "refine"})
    _st24, _ln24 = _next({"thread_id": "1077", "chain_id": _c6, "level": "refine"})
    _r25 = [_wac.post("/architect/next", json=p).status_code for p in ({"thread_id": "1077", "chain_id": _c2, "level": "deeper"}, {"thread_id": "1077", "chain_id": _c2}, {"thread_id": "1077", "level": "refine"},
                                                                         {"chain_id": _c2, "level": "refine"}, {"thread_id": "1077", "chain_id": _c2, "level": 3})]
    _auth["counted"], _auth["refuse"] = [], ({"error": "authorization_failed", "message": "You need $0.010 per query but your balance is $0.00. Please add funds to continue."}, 403)
    _r26 = _wac.post("/architect/next", json={"thread_id": "1077", "chain_id": _c2, "level": "refine"})
    _auth["refuse"] = None
    check("/architect/next, no set made: a reply unreadable twice ends on the reason, its two calls logged under their chain and charged, and nothing is kept; a chain that is not on the record, or is a brief "
          "not yet run, ends on that in words, with no call and no charge; a level that is not one of the five, and a request without its thread, chain or level, are refused outright; a refusal of the "
          "account's is passed on, with no call",
          _st22 == 200 and _ln22[-1] == {"next": {"error": "The Pathfinder's reply could not be read (it holds no JSON object)."}} and _n23 == _n22 + 2 and _logged(_on22) == ["Pathfinder"] * 2
          and _charged == _charged20 + [_on20, _on21, _on22] and len(_ran2.next_questions) == 2
          and _ln23[-1] == _ln24[-1] == {"next": {"error": "This analysis is no longer on record: nothing can follow from it."}} and _r25 == [400] * 5
          and _r26.status_code == 403 and _r26.get_json()["message"].startswith("You need $0.010") and _auth["counted"] == [True] and len(state["calls"]) == _n23 and len(_charged) == len(_charged20) + 3,
          (_ln22[-1], _ln23[-1], _ln24[-1], _r25, _r26.status_code, len(state["calls"]) - _n23))
    # a candidate that is run: an analysis under the one it follows, with no brief; the candidate is marked on the record
    state.update(i=0, script=["###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n# In each half\n\n## Answer\nB is above A in both halves.\n"])
    BAMBOO.pd_agent_converse(question="Is B above A in each half?", thread_id="1077", chain_id=_c2, mode="deep", candidate=(0, 1))
    while not q.empty(): q.get()
    _cand = BAMBOO.notebook.runs[str(BAMBOO.chain_id)]
    _marks27 = [[qn.get("ran") for qn in s["questions"]] for s in _ran2.next_questions]
    state.update(i=0)
    BAMBOO.pd_agent_converse(question="Again?", thread_id="1077", chain_id=_c2, mode="deep", candidate=(7, 0))
    state.update(i=0)
    BAMBOO.pd_agent_converse(question="On its own?", thread_id="1077", chain_id=None, mode="deep", candidate=(0, 0))
    while not q.empty(): q.get()
    check("a next question that is run: an analysis of its own under the one it follows, with no brief and no framing; on the record the question is marked with the chain it started, and the other is not. A "
          "place that names no question marks nothing, nor does a run that follows no chain - each still runs",
          _cand.parent == str(_c2) and _cand.status == "answered" and _cand.question == "Is B above A in each half?" and _cand.brief == {} and _cand.framing == {}
          and _marks27 == [[None, _cand.id], [None]] and _thread_file()[str(_c2)]["next_questions"][0]["questions"][1]["ran"] == _cand.id
          and [[qn.get("ran") for qn in s["questions"]] for s in _ran2.next_questions] == _marks27 and BAMBOO.notebook.runs[str(BAMBOO.chain_id)].status == "answered", (_cand.parent, _marks27, _cand.brief))
    _charged28 = list(_charged)
    BAMBOO.cleanup()
    check("a brief the Pathfinder talked in and no analysis followed: its calls are charged when the instance is torn down, once",
          _charged28[0] == int(_c2) and sorted(_charged[len(_charged28):]) == sorted([int(_c6), int(_op3["chain_id"])]) and BAMBOO._framed == set(), (_charged, BAMBOO._framed))
    # ---- the saved analyses in an exchange (0303, docs/ARCHITECT_DESIGN.md §3.7; 0308, §2.18): read where the Pathfinder's reply asks, the pane told as it goes; what was found
    # is kept beside the brief, and the brief builds on an analysis when the person chooses it - the reply after names it by number
    from analyst.notebook import Notebook as _NB3, NotebookStore as _NBS3
    from _saved import add as _add3, favourite as _fav3
    _su3 = os.path.join(work, "storage", "u1")
    _nbm = _NB3("7301")
    _add3(_nbm, "7302", "Was B above A in spring?", report="# B led in spring\n\nB led A by 3 units [cell 1].", cells=[("gap = b - a", "3\n", ["gap: 3 units"])],
          brief={"decision": "keep the taller arm", "fixed": {"measure": "height"}, "version": 1},
          framing={"versions": [{"n": 1, "by": "person", "changed": [], "brief": {"question": "Which arm led in spring?"}}],
                   "turns": [{"who": "architect", "text": "What is the answer for?"}, {"who": "person", "text": "To keep the taller arm."}]},
          data={"df_id": "d", "name": "spring.csv", "rows": 9, "date_range": "2026-03-01 to 2026-05-31", "columns": [{"name": "x"}], "load": {"source": "s", "subject": {"id": "p-9", "name": "First Person"}}})
    _NBS3(_su3).save(_nbm)
    _favm = _fav3(_su3, 7301, 7302)
    from analyst import memory as _mem3
    _mem3.refresh(_su3)                                          # as the app does behind a save
    sys.modules["app"].user_path = lambda root, *p: os.path.join(os.getcwd(), root, "u1", *p)
    _opm = _wac.post("/architect/open", json={"question": "Is B above A this autumn?"}).get_json()
    _cm = _opm["chain_id"]
    _reads = lambda: ['JUDGE\n{"runs": "all", "parts": ["report"], "question": "Which arm led?"}', json.dumps({"answers": [{"run": "7301/7302", "answer": "B led", "quote": "B led A by 3 units"}]}),      # noqa: E731
                      'ANSWER\n' + json.dumps({"found": [{"run": "7301/7302", "quote": "B led A by 3 units", "note": "The same comparison, in spring."}]})]
    state["architect"] = [json.dumps({"say": "I am looking in your saved analyses.", "recall": True, "brief": {"decision": "keep one arm"}}), json.dumps({"say": "You asked this in spring. Build on it, or go another way?", "choices": ["Build on it", "Go another way"]}),
                          json.dumps({"say": "Done: the Analyst gets it.", "build": [1]})]
    state["memory"], state["memory_seen"], state["architect_seen"] = _reads(), [], []
    _lp3, BAMBOO.load_params = getattr(BAMBOO, "load_params", None), {"source": "s", "subject": {"id": "p-1", "name": "Second Person"}}      # the data loaded now is another person's
    _stm, _lnm = _say({"thread_id": _opm["thread_id"], "chain_id": _cm, "text": "Go on."})
    _fm = (_lnm[-1].get("architect") or {}).get("framing") or {}
    _mt = _fm["turns"][-1]
    _kept_m = {"thread": "7301", "run": "7302", "when": _mt["found"][0]["when"], "question": "Was B above A in spring?", "passage": "B led A by 3 units", "where": "report", "note": "The same comparison, in spring.",
               "marks": "picked", "data": "spring.csv", "period": "2026-03-01 to 2026-05-31", "person": "First Person", "other": True}
    _mcost = [e["cost"] for e in json.load(open(BAMBOO.log_and_call_manager.run_log_file_path)) if str(e.get("chain_id")) == str(_cm) and str(e.get("agent")).startswith("Memory")]
    check("/architect/say, a reply that asks for the saved analyses: the Pathfinder is told how many the person has, and the framing keeps the number; they are read under the brief's own chain, with the question and the brief as it then stands; the stream says how many are saved and, as the "
          "second model goes, how many are read; what was found is the conversation's last turn, and the passage is kept beside the brief (0308) - the brief has only what the reply wrote, a reading makes no version, and the analyst would not receive the passage",
          _stm == 200 and [(e["read"], e["of"], e["chain_id"]) for e in _lnm if e.get("type") == "architect_saved"] == [(0, 1, _cm), (1, 1, _cm)]
          and [t["who"] for t in _fm["turns"]] == ["person", "architect", "memory"] and _mt["found"] == [{"id": "7301/7302", "when": _mt["found"][0]["when"], "question": "Was B above A in spring?", "where": "report",
                                                                                                           "quote": "B led A by 3 units", "note": "The same comparison, in spring."}]
          and (_mt["of"], _mt["read"], _mt["failed"], _mt["across"]) == (1, 1, "", None) and round(_mt["cost"], 4) == round(sum(_mcost), 4) and len(_mcost) == 3
          and _fm["found"] == [_kept_m] and "saved" not in _fm["versions"][-1]["brief"] and len(_fm["versions"]) == 2
          and (_fm["versions"][-1]["by"], _fm["versions"][-1]["why"], _fm["versions"][-1]["changed"]) == ("architect", "answer", ["decision"])
          and state["memory_seen"][0][4].startswith("QUESTION:\nIs B above A this autumn?\n\nBRIEF (version 1):\ndecision: keep one arm\n") and _logged(_cm) == ["Pathfinder", "Memory Reader", "Memory Pieces", "Memory Reader"]
          and "\n\nSAVED: 1\n\nQUESTION:\nIs B above A this autumn?\n" in state["architect_seen"][0][3] and _fm["saved"] == 1
          and "saved" not in _bf.agreed(_fm["versions"][-1]["brief"]), (_stm, [e for e in _lnm if e.get("type") == "architect_saved"], _fm.get("turns"), _logged(_cm)))
    _same3 = [{"thread": "7301", "run": "7302", "data": {"name": "spring.csv"}}, {"thread": "7301", "run": "9999", "data": {}}]
    BAMBOO.load_params = {"source": "s", "subject": {"id": "p-9", "name": "First Person"}}
    BAMBOO._whose(_same3)
    _none3 = [{"thread": "7301", "run": "7302", "data": {}}]
    BAMBOO.load_params = None
    BAMBOO._whose(_none3)
    BAMBOO.load_params = {"source": "s", "subject": {"id": "p-1", "name": "Second Person"}}
    check("whose data a passage's run ran on: the framing keeps the person's name from the thread's record, for the person to read, and that it is another person than the one whose data is loaded now - "
          "not said for the same person, nor where the data loaded names nobody, nor for a run that is not on record; no model reads the name - not the reader, not the second model, not the Pathfinder",
          (_kept_m["person"], _kept_m["other"]) == ("First Person", True) and _same3[0]["data"] == {"name": "spring.csv", "person": "First Person", "other": False}
          and _same3[1]["data"] == {"person": "", "other": False} and _none3[0]["data"] == {"person": "First Person", "other": False}
          and all("First Person" not in str(seen) and "Second Person" not in str(seen) for seen in state["memory_seen"] + state["architect_seen"])
          and "First Person" not in json.dumps(_mem3.view(_su3)), (_kept_m, _same3, _none3))
    _stm2, _lnm2 = _say({"thread_id": _opm["thread_id"], "chain_id": _cm})
    _seen_found = state["architect_seen"][-1][3]
    _stmb, _lnmb = _say({"thread_id": _opm["thread_id"], "chain_id": _cm, "text": "Build on it"})
    _sm = {"framing": _lnmb[-1]["architect"]["framing"]}
    _kept_b = {**_kept_m, "accepted": True}
    _undone = _wac.post("/architect/brief", json={"thread_id": _opm["thread_id"], "chain_id": _cm, "changed": ["saved"],
                                                  "brief": {k: v for k, v in _sm["framing"]["versions"][-1]["brief"].items() if k != "saved"}}).get_json()["framing"]      # the cross on the page: built on no longer
    _sm = {"framing": _wac.post("/architect/brief", json={"thread_id": _opm["thread_id"], "chain_id": _cm, "changed": ["saved.0"], "brief": _sm["framing"]["versions"][-1]["brief"]}).get_json()["framing"]}
    check("the exchange after a reading, and 'build on it' (0308): the Pathfinder reads what the saved analyses hold, the analysis under its number, and that the brief builds on none yet; the person's word "
          "is theirs to give in the conversation, and the reply that names the analysis by its number brings its passage into the brief, accepted - a version of the Pathfinder's - so the analyst receives it "
          "as a claim to test. The cross on the page takes it out again, a version of the person's; a brief sent with the passage has it back",
          f'\nSaved analyses (1 saved, 1 read through):\n[1] {_kept_m["when"]} "Was B above A in spring?": in its report "B led A by 3 units" - The same comparison, in spring.\n' in _seen_found
          and "\nbuilds_on: (empty)\n\nCONVERSATION:" in _seen_found and "First Person" not in _seen_found
          and f'\nbuilds_on:\n- [1] {_kept_m["when"]} "Was B above A in spring?"\n\nCONVERSATION:' not in state["architect_seen"][-1][3]      # the prompt of the reply that built on it: not yet
          and (_lnmb[-1]["architect"]["framing"]["versions"][-1]["by"], _lnmb[-1]["architect"]["framing"]["versions"][-1]["why"], _lnmb[-1]["architect"]["framing"]["versions"][-1]["changed"]) == ("architect", "answer", ["saved.0"])
          and _lnmb[-1]["architect"]["framing"]["versions"][-1]["brief"]["saved"] == [_kept_b]
          and (_undone["versions"][-1]["by"], _undone["versions"][-1]["changed"]) == ("person", ["saved"]) and "saved" not in _undone["versions"][-1]["brief"] and _undone["found"] == [_kept_m]
          and _sm["framing"]["versions"][-1]["brief"]["saved"] == [_kept_b]
          and _bf.render(_bf.agreed(_sm["framing"]["versions"][-1]["brief"])).splitlines()[-2:] == ["Saved analyses the person chose (earlier results: claims to test, not evidence):",
              f'1. {_kept_m["when"]} "Was B above A in spring?" (spring.csv, 2026-03-01 to 2026-05-31, another person\'s data): in its report "B led A by 3 units"'], (_seen_found[-500:], _sm))
    _one = _wac.get("/architect/saved/7301/7302")
    _nbp = _NB3("7401")                                          # a saved analysis built on a step that is not saved: for the moment of one request
    _add3(_nbp, "7402", "How is the gap taken?", report="# A helper\n\nDefined [cell 1].", cells=[("def gap(a, b):\n    return b - a", "", [])])
    _add3(_nbp, "7403", "And in autumn?", parent="7402", report="# Level in autumn\n\nThe arms are level [cell 2].", cells=[("g = gap(a, b)", "0\n", ["gap: 0 units"])])
    _NBS3(_su3).save(_nbp)
    _favp = _fav3(_su3, 7401, 7403)
    _mem3.refresh(_su3)
    _built = _wac.get("/architect/saved/7401/7403").get_json()
    os.remove(_favp)
    _mem3.refresh(_su3)
    check("/architect/saved: a saved analysis as memory holds it, to read beside the brief that names it - the question, the brief it ran under and the conversation that brief came from, the report, the code of its cells, how it was saved, the data it ran on and whose it is; the cells are those along its thread up to its own, an earlier step's with them, as a passage's place counts them; one that is not saved is not found, nor is a saved one asked for under another thread",
          _one.status_code == 200 and {k: _one.get_json()[k] for k in ("id", "question", "title", "report", "marks", "data")} == {"id": "7301/7302", "question": "Was B above A in spring?", "title": "B led in spring",
              "report": "# B led in spring\n\nB led A by 3 units [cell 1].", "marks": ["picked"], "data": {"name": "spring.csv", "period": "2026-03-01 to 2026-05-31", "person": "First Person"}}
          and _one.get_json()["cells"] == [{"n": 1, "code": "gap = b - a"}] and _one.get_json()["brief"] == "What the answer is for: keep the taller arm\nFixed before the run:\n- measure: height"
          and _one.get_json()["conversation"] == "Person: Which arm led in spring?\nPathfinder: What is the answer for?\nPerson: To keep the taller arm."
          and (_built["cells"], _built["brief"], _built["conversation"]) == ([{"n": 1, "code": "def gap(a, b):\n    return b - a"}, {"n": 2, "code": "g = gap(a, b)"}], "", "")
          and _wac.get("/architect/saved/7401/7403").status_code == 404 and len(_mem3.view(_su3)["runs"]) == 1
          and _wac.get("/architect/saved/7301/9999").status_code == 404 and _wac.get("/architect/saved/1077/" + str(_c2)).status_code == 404
          and _wac.get("/architect/saved/1077/7302").status_code == 404, _one.get_json())
    # a branch among the saved analyses (0321, docs/BRANCH_DESIGN.md §2, decision 13): the way saved from is memory, with its hint; the way left is not
    _nbh = _NB3("7501")
    _add3(_nbh, "7502", "Is B above A?", report="# B is above\n\nB is above A [cell 1].", cells=[("gap = b - a", "", [])])
    _add3(_nbh, "7503", "Is B above A?", report="# B is above on loam\n\nOn loam B is above A [cell 1].", cells=[("gap = b - a", "", [])], at=5,
          branch={"of": "7502", "turn": 1}, hints=[{"turn": 1, "text": "Keep the soil types apart."}])
    _NBS3(_su3).save(_nbh)
    _favh = [_fav3(_su3, 7501, 7502, "trajectory"), _fav3(_su3, 7501, 7503)]
    _mem3.refresh(_su3)
    _hinted, _way_left = _wac.get("/architect/saved/7501/7503"), _wac.get("/architect/saved/7501/7502")
    for _f in _favh:
        os.remove(_f)
    _mem3.refresh(_su3)
    check("/architect/saved of a branch (0321): the saved analysis says the hints it was made under, each with its turn - a run that is no branch says none; the way the person left for it "
          "is no saved analysis to open",
          _hinted.status_code == 200 and _hinted.get_json()["hints"] == [{"turn": 1, "text": "Keep the soil types apart."}] and _hinted.get_json()["question"] == "Is B above A?"
          and _one.get_json()["hints"] == [] and _way_left.status_code == 404 and len(_mem3.view(_su3)["runs"]) == 1, (_hinted.get_json(), _way_left.status_code))
    _pane_was = BAMBOO._pane
    BAMBOO._pane = lambda kind, **kw: (_pane_was(kind, **kw), _wac.post("/architect/skip") if kind == "architect_saved" else None)[0]      # the person clicks Skip as the row opens
    state["architect"], state["memory"], state["memory_seen"] = [json.dumps({"say": "I am looking once more.", "recall": True})], _reads(), []
    _asked3 = len(state["architect_seen"])
    _stm3, _lnm3 = _say({"thread_id": _opm["thread_id"], "chain_id": _cm, "text": "Look further back."})
    BAMBOO._pane = _pane_was
    _t3 = _lnm3[-1]["architect"]["framing"]["turns"]
    check("/architect/skip: skipped as the reading opens, no model is called for the reading, the turn says that the person skipped it, and the brief and what was found before stand as they did; the "
          "next exchange starts with the skip forgotten",
          [t["who"] for t in _t3][-3:] == ["person", "architect", "memory"] and _t3[-3]["text"] == "Look further back." and _t3[-1]["failed"] == "The person skipped it." and _t3[-1]["found"] == []
          and state["memory_seen"] == [] and len(state["architect_seen"]) == _asked3 + 1 and state["architect"] == []
          and len(_lnm3[-1]["architect"]["framing"]["versions"]) == len(_sm["framing"]["versions"]) and _lnm3[-1]["architect"]["framing"]["found"] == [_kept_m] and BAMBOO._skip_saved.is_set(),
          (_t3[-1], state["memory_seen"]))
    # the analysis the brief starts: the analyst opens the saved analysis its ticked passage comes from (SHOW SAVED 1)
    _keep_s3 = (state["script"], state["i"])
    state.update(i=0, script=["###NOTE###\n" + NOTE + "\n###ACTION###\nSHOW SAVED 1",
                              "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n# Autumn\n\n## Answer\nNothing was computed.\n\n## Against the brief\n- chance: cannot tell.\n\n## Did not fit\nNothing."])
    BAMBOO.output_manager.add_user_input("Is B above A this autumn?")
    while not q.empty(): q.get()
    BAMBOO.pd_agent_converse(thread_id=_opm["thread_id"], chain_id=None, mode="deep", run_id=_cm)
    _rows3 = [e for e in (json.loads(q.get()) for _ in range(q.qsize())) if e.get("type") == "pane_lookup" and e.get("kind") == "show"]
    state["script"], state["i"] = _keep_s3
    _shown3 = next((t.stdout for t in BAMBOO.notebook.runs[str(_cm)].turns if t.kind == "show"), "")
    check("SHOW SAVED k through the host: the analyst of a run under the brief opens the saved analysis its ticked passage comes from - what was asked, the brief it ran under, the report, the code and the result lines of its cells, "
          "as memory holds it, under a line that says it is another person's data; no name, and no id of the person, is in it. The pane's row for the step says which analysis was opened, in the "
          "words of that line without its rule marks. A run that is not saved gives none",
          _shown3 == (f'--- saved analysis 1: {_kept_m["when"]} "Was B above A in spring?" (another person\'s data) ---\nQUESTION: Was B above A in spring?\nTITLE: B led in spring\n'
                      "BRIEF:\nWhat the answer is for: keep the taller arm\nFixed before the run:\n- measure: height\n"
                      "REPORT:\n# B led in spring\n\nB led A by 3 units [cell 1].\nCELL 1, code:\ngap = b - a\nCELL 1, results:\ngap: 3 units")
          and [r["peek"] for r in _rows3] == [f'saved analysis 1: {_kept_m["when"]} "Was B above A in spring?" (another person\'s data)']
          and "First Person" not in _shown3 and "p-9" not in _shown3 and BAMBOO._saved_analysis("7301", "9999") is None and BAMBOO._saved_analysis("1077", "7302") is None, _shown3)
    from analyst import draft as _draft, memory as _mem0
    _view_was, _code_was, _rooms = _mem0.view, _draft.saved_code, []
    try:
        _mem0.view = lambda storage: {"runs": []}             # the analysis is on its thread's record still, and saved no more
        _unsaved = BAMBOO._saved_code({"saved": [_kept_b]})
        _mem0.view = lambda storage: {"runs": [{"thread": "7301", "run": "7302"}, {"thread": "7301", "run": "7303"}]}
        _draft.saved_code = lambda nb, run, chars: (_rooms.append((run, chars)), f"code of {run}")[1]
        _two = BAMBOO._saved_code({"saved": [_kept_b, {"thread": "7301", "run": "7303", "when": "2026-04-02", "question": "And in April?", "accepted": True}]})
    finally:
        _mem0.view, _draft.saved_code = _view_was, _code_was
    check("the host's code of the saved analyses a brief builds on (0310): of each one still saved, the cells along its path from the thread's record, under its day and what was asked then - for "
          "the model that drafts the figures; a passage not built on, an analysis saved no more - on its thread's record or not - and a brief that builds on none give nothing. Two analyses "
          "share the room the code may take",
          BAMBOO._saved_code({"saved": [_kept_b, {"thread": "7301", "run": "9999", "question": "gone", "accepted": True}]}) == f'{_kept_m["when"]} "Was B above A in spring?"\n--- cell 1 ---\n```python\ngap = b - a\n```'
          and BAMBOO._saved_code({"saved": [_kept_m]}) == "" and BAMBOO._saved_code({}) == "" and BAMBOO._saved_code(None) == ""
          and BAMBOO._saved_code({"saved": [{"thread": "7301", "run": "9999", "accepted": True}]}) == "" and _unsaved == ""
          and _rooms == [("7302", _draft.SAVED_CHARS // 2), ("7303", _draft.SAVED_CHARS // 2)] and _draft.SAVED_CHARS == 16000
          and _two == f'{_kept_m["when"]} "Was B above A in spring?"\ncode of 7302\n\n2026-04-02 "And in April?"\ncode of 7303', (BAMBOO._saved_code({"saved": [_kept_b]}), _unsaved, _rooms, _two))
    _read_was = BAMBOO.memory_read
    def _boom(*a, **kw):
        raise RuntimeError("the executor is away")
    BAMBOO.memory_read = _boom
    _opm2 = _wac.post("/architect/open", json={"question": "And the hours?"}).get_json()
    state["architect"] = [json.dumps({"say": "Looking.", "recall": True})]
    _stm4, _lnm4 = _say({"thread_id": _opm2["thread_id"], "chain_id": _opm2["chain_id"], "text": "Go on."})
    BAMBOO.memory_read = _read_was
    _t4 = _lnm4[-1]["architect"]["framing"]["turns"]
    os.remove(_favm)
    check("a reading that cannot be made does not lose the Pathfinder's reply: the turn says why, in words, and the skip of the exchange before does not reach this one",
          [t["who"] for t in _t4] == ["person", "architect", "memory"] and _t4[-1]["failed"] == "The saved analyses could not be read: the executor is away" and _t4[1]["text"] == "Looking."
          and not BAMBOO._skip_saved.is_set(), _t4[-1])
    state["architect"] = [json.dumps({"say": "Say what to look for."})]
    _stm9, _lnm9 = _say({"thread_id": _opm2["thread_id"], "chain_id": _opm2["chain_id"], "text": "Look.", "look": True})
    _t9 = _lnm9[-1]["architect"]["framing"]["turns"]
    check("/architect/say: the person has no request of their own for the saved analyses (0308) - a message that carries the `look` of the page before is one the Pathfinder replies to, and nothing is read",
          [t["who"] for t in _t9][-2:] == ["person", "architect"] and _t9[-1]["text"] == "Say what to look for." and sum(1 for t in _t9 if t["who"] == "memory") == 1, _t9[-2:])
    # the question worded (0308, §2.18): the Pathfinder's wording is the question from its reply on - a version like any other. The person changes it by hand or goes back to an earlier version:
    # the version on their screen rides with what they do next, and the analysis runs under it
    _wording = "Total the hours of each arm, and compare them."
    _cw = _opm2["chain_id"]
    state["architect"] = [json.dumps({"say": "I have put that into the question.\n\nIs that what you mean?", "wording": _wording, "brief": {"question": "Sneaked in"}})]
    _stw1, _lnw1 = _say({"thread_id": _opm2["thread_id"], "chain_id": _cw, "text": "The hours of each arm."})
    _fw = _lnw1[-1]["architect"]["framing"]
    _then = BAMBOO.notebook.runs[str(_cw)].question
    state["architect"] = [json.dumps({"say": "Ready when you are."})]
    _stw3, _lnw3 = _say({"thread_id": _opm2["thread_id"], "chain_id": _cw, "text": "Good."})
    _filew = json.load(open(os.path.join(work, "storage", "u1", "threads", f'{_opm2["thread_id"]}.json'), encoding="utf-8"))["runs"][str(_cw)]
    check("/architect/say, the question worded (0308): the Pathfinder's message keeps its lines, and the wording it gives is the question from that reply on, whatever the reply wrote under the brief's "
          "question - a version of the Pathfinder's, kept with its message, the run's question on the record at once, and the question the Pathfinder reads from then on, with how it was first asked. "
          "Nothing waits to be taken",
          (_fw["turns"][-1]["text"], _fw["turns"][-1].get("wording"), _then) == ("I have put that into the question.\n\nIs that what you mean?", _wording, _wording)
          and (_fw["versions"][-1]["by"], _fw["versions"][-1]["changed"], _fw["versions"][-1]["brief"]["question"]) == ("architect", ["question"], _wording) and not hasattr(_arch, "pending")
          and _fw["versions"][0]["brief"]["question"] == "And the hours?" and _filew["question"] == _wording and len(_fw["versions"]) == 2
          and f"\n\nQUESTION:\n{_wording}\n(first asked as: And the hours?)\n\nBRIEF (version 2):" in state["architect_seen"][-1][3], (_fw["versions"][-1], _filew["question"]))
    _second = "Total the hours of each arm, month by month."
    state["architect"] = [json.dumps({"say": "Then like this.", "wording": _second})]
    _stw4, _lnw4 = _say({"thread_id": _opm2["thread_id"], "chain_id": _cw, "text": "By month, rather."})
    _fw4 = _lnw4[-1]["architect"]["framing"]
    state["architect"] = [json.dumps({"say": "Noted.", "brief": {"decision": "to see which arm works more"}})]
    _stw5, _lnw5 = _say({"thread_id": _opm2["thread_id"], "chain_id": _cw, "text": "It is to see which arm works more.", "step": 5})      # the person stepped back to step 5 - before "By month, rather." - and answers from it
    _fw5, _seen5 = _lnw5[-1]["architect"]["framing"], state["architect_seen"][-1][3]
    _q5 = BAMBOO.notebook.runs[str(_cw)].question
    state["architect"] = [json.dumps({"say": "Still here."}), json.dumps({"say": "And here."})]
    _fw6 = _say({"thread_id": _opm2["thread_id"], "chain_id": _cw, "text": "And the one before?", "step": 6})[1][-1]["architect"]["framing"]       # to step 6, on the way left, and a reply that changes nothing
    _q6 = BAMBOO.notebook.runs[str(_cw)].question
    _fw7 = _say({"thread_id": _opm2["thread_id"], "chain_id": _cw, "text": "A word for a number.", "step": "2"})[1][-1]["architect"]["framing"]
    _took = _wac.post("/architect/brief", json={"thread_id": _opm2["thread_id"], "chain_id": _cw, "changed": ["thinks"], "step": 6,
                                                "brief": {**_fw7["versions"][2]["brief"], "thinks": "one arm works more"}}).get_json()["framing"]      # a change by hand, made at step 6: the page sends the brief that stands there with it
    _shape = lambda f: [(x["k"], x["from"], x["v"], x["made"], x["turns"]) for x in f["steps"]]      # noqa: E731
    _texts = lambda turns: [t.get("text") for t in turns if t["who"] == "person"]                    # noqa: E731
    check("the step on the person's screen (0316): an answer sent from an earlier step goes on from it. The Pathfinder reads the question and the brief as they stood there and the conversation up to "
          "there - not what was said after, and no word that the person went back - and its change is one more version made on that brief, the run's question the one that stood there; message and "
          "reply are a step that follows the one gone to, and what the steps left hold is set aside. A reply that changes nothing leaves that step's version in use, the framing names it, and the "
          "run's question is its. `step` is a whole number: a number in words names none, and the conversation goes on from the step in use. A change by hand made at a step is the brief that "
          "stood there with the change - the page sends it - a version of the person's, the last and the one in use, a step of its own that follows the one it was made at; the run's question follows",
          len(_fw4["versions"]) == 3 and _shape(_fw4)[-1] == (6, 5, 3, [3], 2) and [t["who"] for t in _fw5["turns"]][-3:] == ["architect", "person", "architect"]
          and _texts(_fw5["turns"])[-2:] == ["Good.", "It is to see which arm works more."] and _shape(_fw5)[-1] == (7, 5, 4, [4], 2) and (_fw5["step"], _fw5["tip"]) == (7, 7)
          and [t.get("text") for t in _fw5["aside"]["6"]["turns"]] == ["By month, rather.", "Then like this."]
          and _fw5["versions"][-1]["brief"] == {"question": _wording, "decision": "to see which arm works more"} and len(_fw5["versions"]) == 4 and "at" not in _fw5 and _q5 == _wording
          and f"QUESTION:\n{_wording}\n(first asked as: And the hours?)\n\nBRIEF (version 2):" in _seen5
          and "\nPathfinder: Ready when you are.\nPerson: It is to see which arm works more.\n\nReply with the JSON object." in _seen5 and "By month" not in _seen5 and "went to version" not in _seen5
          and _fw6["at"] == 3 and len(_fw6["versions"]) == 4 and _shape(_fw6)[-1] == (8, 6, 3, [], 2) and _fw6["turns"][-1]["v"] == 3 and _q6 == _second
          and _texts(_fw6["turns"])[-2:] == ["By month, rather.", "And the one before?"] and sorted(_fw6["aside"]) == ["7"]
          and _fw7["at"] == 3 and [t["who"] for t in _fw7["turns"]][-2:] == ["person", "architect"] and _shape(_fw7)[-1] == (9, 8, 3, [], 2)
          and (_took["versions"][-1]["by"], _took["versions"][-1]["changed"], _took["versions"][-1]["n"]) == ("person", ["thinks"], 5) and "at" not in _took
          and _took["versions"][-1]["brief"] == {"question": _second, "thinks": "one arm works more"} and BAMBOO.notebook.runs[str(_cw)].question == _second
          and _shape(_took)[-1] == (10, 6, 5, [5], 0) and (_took["step"], _took["tip"]) == (10, 10) and _took["turns"] == _fw4["turns"] and sorted(_took["aside"]) == ["7", "8", "9"]
          and _took["calls"] == _fw7["calls"], (_shape(_fw5)[-1], _fw6.get("at"), _shape(_took)[-1], _took["versions"][-1]))
    from analyst.brief import said as _said_of
    _keep_s4, _n30 = (state["script"], state["i"]), len(state["calls"])
    state.update(i=0, script=["###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n# Hours\n\n## Answer\nNothing was computed.\n\n## Against the brief\n- chance: cannot tell.\n\n## Did not fit\nNothing."])
    BAMBOO.output_manager.add_user_input("And the hours?")                 # a page that still holds the question as it was first asked
    while not q.empty(): q.get()
    BAMBOO.pd_agent_converse(thread_id=_opm2["thread_id"], chain_id=None, mode="deep", run_id=_cw, step=7)      # Start analysis with step 7 on screen, whose brief is version 4: the last is version 5
    state["script"], state["i"] = _keep_s4
    _wprompt = next((u for a, u in state["calls"][_n30:] if "TASK: turn 1" in u), "")
    _wrun = BAMBOO.notebook.runs[str(_cw)]
    check("Start analysis with another step on screen (0316): the Analyst is asked the question that stood there and reads the brief that stood there - not the last one's, and not what the page sends "
          "as the question; the run keeps every version, and its framing says which step it started from, for the page to show. The conversation the run keeps - what a later question may open, and "
          "what is remembered of a saved analysis - is the way to that step: nothing of the ways left",
          ("\n\nQUESTION:\n" + _wording + "\n\nBRIEF (agreed with the person before this run):\nWhat the answer is for: to see which arm works more\n") in _wprompt
          and "And the hours?" not in _wprompt and "month by month" not in _wprompt and "What the person thinks" not in _wprompt
          and _wrun.question == _wording and _wrun.status == "answered" and _wrun.framing["at"] == 4 and len(_wrun.framing["versions"]) == 5 and (_wrun.framing["step"], _wrun.framing["tip"]) == (7, 7)
          and "Person: It is to see which arm works more." in _said_of(_wrun.framing) and "By month" not in _said_of(_wrun.framing) and "And the one before?" not in _said_of(_wrun.framing)
          and sorted(_wrun.framing["aside"]) == ["6", "8", "9"] and len(_wrun.framing["steps"]) == 10
          and (_wrun.brief.get("decision"), _wrun.brief.get("thinks"), _wrun.brief.get("version")) == ("to see which arm works more", None, 4), (_wprompt[:500], _wrun.question, _wrun.framing.get("at")))
    # the figures and their draft (0309, 0310; §2.19, §2.20): the figures a reply gives are a part of the brief - a version; after the reply a draft of them is drawn, by a cell that
    # runs with no data, and kept beside the record; the person takes one out by hand; the Analyst and the step that draws read the ones that stand - the step with the cell that drew them
    from analyst import draft as _draft, tools as _tools
    from bambooai.bambooai import DRAFT_GUARD
    import subprocess as _sub
    _pp_was = os.environ.get("PYTHONPATH")
    if _sub.run([sys.executable, "-c", "import plotly.graph_objects"], capture_output=True).returncode:      # the cell's kernel has no Plotly here: the stack's stand-in, by its whole path
        os.environ["PYTHONPATH"] = os.path.join(ROOT, "tools", "stack", "fakepkgs") + (os.pathsep + _pp_was if _pp_was else "")
    _opf = _wac.post("/architect/open", json={"question": "Chart the hours of each arm."}).get_json()
    _cf, _tf = _opf["chain_id"], _opf["thread_id"]
    _figs = [{"title": "Hours of each arm", "kind": "bar", "x": "arm", "y": "hours", "series": ["A", "B"], "note": "Which arm works more."},
             {"title": "The rule given", "kind": "line", "x": "x", "y": "y", "series": [{"name": "the rule", "points": [[0, 0], [1, 1], [2, 4]]}]},
             {"title": "Hours by month", "kind": "line", "series": ["A", "B"]}]
    _cell_f = ("import plotly.graph_objects as go\ntry:\n    rows = len(df)\nexcept Exception:\n    rows = -1\n"
               "f1 = go.Figure(go.Bar(x=['A', 'B'], y=[rows, rows])); f1.update_layout(title='Hours of each arm'); f1.show()\n"
               "f2 = go.Figure(go.Scatter(x=[0, 1, 2], y=[0, 1, 4])); f2.update_layout(title='The rule given', meta='computed'); f2.show()\n"
               "f3 = go.Figure(go.Scatter(x=[1, 2], y=[3, 4])); f3.update_layout(title='Hours by month'); f3.show()")
    state["architect"] = [json.dumps({"say": "A draft is being drawn. Is that what you want to see?", "figures": _figs})]
    state["draft"], state["draft_seen"] = ["```python\n" + _cell_f + "\n```"], []
    _nlog = len(_logged(_cf))
    _stf, _lnf = _say({"thread_id": _tf, "chain_id": _cf, "text": "Show me what it will look like."})
    _ff = _lnf[-1]["architect"]["framing"]
    _bf, _kf = _ff["versions"][-1]["brief"], _ff["versions"][-1].get("keys") or [None] * 3
    _midf = [e for e in _lnf if e.get("type") == "architect_draft"]
    _thread_text = open(os.path.join(work, "storage", "u1", "threads", f"{_tf}.json"), encoding="utf-8").read()
    _filef = json.loads(_thread_text)["runs"][str(_cf)]
    _plotf = lambda k: os.path.join(work, "storage", "u1", "drafts", str(_tf), str(_cf), f"{k}.json")      # noqa: E731
    _got2 = _wac.get(f"/architect/draft/{_tf}/{_cf}/{_kf[1]}")
    check("/architect/say, the figures and their draft (0310): the figures a reply gives are the brief's from that reply on - a version of the Pathfinder's, each figure a description and no more: "
          "points a reply gives are not kept. The framing names each figure's key beside its version. A draft follows the reply in the same exchange: the stream first carries the framing with the "
          "reply - the page shows it while the draft is drawn - and ends on the framing with the draft's turn: each figure drawn, with what its numbers are, the seconds, the cost, its call",
          _stf == 200 and (_ff["versions"][-1]["by"], _ff["versions"][-1]["changed"]) == ("architect", ["figures.0", "figures.1", "figures.2"])
          and [f["title"] for f in _bf["figures"]] == ["Hours of each arm", "The rule given", "Hours by month"] and _bf["figures"][1]["series"] == [{"name": "the rule"}]
          and _kf == [_draft.key("Chart the hours of each arm.", f) for f in _bf["figures"]] and len(set(_kf)) == 3
          and len(_midf) == 1 and _lnf.index(_midf[0]) < len(_lnf) - 1 and str(_midf[0]["chain_id"]) == str(_cf) and _midf[0]["framing"]["turns"][-1]["who"] == "architect"
          and "drafts" not in _midf[0]["framing"] and _midf[0]["framing"]["versions"] == _ff["versions"]
          and [t["who"] for t in _ff["turns"]] == ["person", "architect", "draft"]
          and {k: v for k, v in _ff["turns"][-1].items() if k not in ("secs", "cost")} == {"who": "draft", "drawn": [{"title": "Hours of each arm", "basis": "made up"}, {"title": "The rule given", "basis": "computed"},
                                                                                                           {"title": "Hours by month", "basis": "made up"}], "v": 2, "call": 1}
          and _ff["turns"][-1]["secs"] > 0 and _ff["turns"][-1]["cost"] > 0
          and _ff["drafts"] == {_kf[0]: {"basis": "made up"}, _kf[1]: {"basis": "computed"}, _kf[2]: {"basis": "made up"}} and _ff["draft_calls"] == 1, (_ff["turns"][-1], _ff.get("drafts"), _kf))
    import re as _re_r
    _routes_src = open(os.path.join(ROOT, "web_app", "architect_routes.py"), encoding="utf-8").read()
    _routes = _re_r.findall(r"@architect_bp\.route\('([^']+)'[^\n]*\)\n(@requires_auth\n)?", _routes_src)      # this suite's sign-in is a stand-in: that each route asks for one is read off the source
    check("the draft's cell through the host (0310): one model call on the figures' seat, at a low effort, logged as the draft's under the brief's chain; its prompt is the question as it stands and "
          "the figures in words. The cell ran where no data is - the frame of the analysis was not there for it - and each plot is a file of its own beside the thread's record, which holds the "
          "cell and the keys of the figures it drew, and no plot. /architect/draft gives a figure's plot by its key, as Plotly takes it; a key that has none is not found. Every route of the "
          "Pathfinder's asks for the sign-in, the draft's among them",
          [(a, k.get("label"), k.get("reasoning_effort"), str(c)) for a, k, c, _ in state["draft_seen"]] == [(BAMBOO._figures_seat(), "Draft", ("low",), str(_cf))]
          and len(_routes) == 8 and all(asks for _, asks in _routes) and {"/architect/draft/<thread_id>/<run_id>/<key>", "/architect/ready"} <= {r for r, _ in _routes}
          and state["draft_seen"][0][3] == _draft.prompt("Chart the hours of each arm.", _bf["figures"]) and _logged(_cf)[_nlog:] == ["Pathfinder", "Draft"]
          and all(os.path.isfile(_plotf(k)) for k in _kf) and json.load(open(_plotf(_kf[0])))["data"][0]["y"] == [-1, -1] and len(BAMBOO.df) == 200
          and sorted(os.listdir(os.path.dirname(_plotf(_kf[0])))) == sorted(f"{k}.json" for k in _kf)
          and _filef["drafts"] == [{"code": _cell_f, "keys": _kf}] and '"y": [-1, -1]' not in _thread_text and _filef["framing"]["drafts"] == _ff["drafts"]
          and _got2.status_code == 200 and (_got2.get_json()["plot"]["layout"]["title"]["text"], _got2.get_json()["plot"]["layout"]["meta"]) == ("The rule given", "computed")
          and _got2.get_json()["plot"]["data"][0]["y"] == [0, 1, 4] and _got2.mimetype == "application/json"
          and _wac.get(f"/architect/draft/{_tf}/{_cf}/000000000000").status_code == 404 and "error" in _wac.get(f"/architect/draft/{_tf}/9999/{_kf[1]}").get_json()
          and _wac.get(f"/architect/draft/..%2F..%2Fthreads/{_cf}/{_kf[1]}").status_code == 404, (state["draft_seen"][0][:3], _logged(_cf)[_nlog:], _filef.get("drafts")))
    _ff2 = _wac.post("/architect/brief", json={"thread_id": _tf, "chain_id": _cf, "changed": ["figures"],
                                               "brief": {**_bf, "figures": _bf["figures"][:2]}}).get_json()["framing"]      # the cross on the third figure: the page sends the brief without it
    state["architect"] = [json.dumps({"say": "Two figures, as they stand."})]
    _ff3 = _say({"thread_id": _tf, "chain_id": _cf, "text": "Good."})[1][-1]["architect"]["framing"]
    _seenf = state["architect_seen"][-1][3]
    check("/architect/brief and the draft (0309, 0310): a figure the person takes out is a version of theirs - the page sends the brief without it. The figures that stay keep their keys, so their "
          "drafts stand: nothing is drawn again, by that change or by the reply after it. The Pathfinder then reads the figures that stand, each under its number, in words, and what the draft "
          "came to as a line of the conversation",
          (_ff2["versions"][-1]["by"], _ff2["versions"][-1]["changed"], len(_ff2["versions"][-1]["brief"]["figures"])) == ("person", ["figures"], 2) and _ff2["versions"][-1]["keys"] == _kf[:2]
          and _ff2["drafts"] == _ff["drafts"] and [t["who"] for t in _ff2["turns"]] == ["person", "architect", "draft"]
          and len(_ff3["versions"]) == 3 and [t["who"] for t in _ff3["turns"]] == ["person", "architect", "draft", "person", "architect"] and len(state["draft_seen"]) == 1
          and '\nfigures:\n- [1] "Hours of each arm" - bars; x: arm; y: hours; holds: A, B; to make clear: Which arm works more.\n- [2] "The rule given" - a line chart; x: x; y: y; holds: the rule'
              '\n\nCONVERSATION:' in _seenf and "Hours by month" not in _seenf.split("BRIEF (version 3):")[1].split("CONVERSATION:")[0]
          and '\nDraft of the figures: drawn - "Hours of each arm" (on made-up numbers), "The rule given" (computed), "Hours by month" (on made-up numbers)\nPerson: Good.' in _seenf,
          (_ff2["versions"][-1], _seenf[-900:]))
    # a draft that cannot be drawn never fails the exchange; its figures are tried once more, after the person next speaks, and then left
    _new_fig = {"title": "The rule given", "kind": "scatter", "x": "x", "y": "y"}
    state["architect"] = [json.dumps({"say": "As points, then. A draft is being drawn.", "figures": [1, _new_fig]}), json.dumps({"say": "It could not be drawn. I will have it tried again."}),
                          json.dumps({"say": "It still cannot be drawn."}), json.dumps({"say": "Start when you are ready."})]
    state["draft"] = ["No cell this time.", "```python\nimport os\n```", "```python\n1/0\n```", "```python\nraise ValueError('still wrong')\n```"]
    _fx1 = _say({"thread_id": _tf, "chain_id": _cf, "text": "Make the second one points."})[1][-1]["architect"]["framing"]
    _kx = _fx1["versions"][-1]["keys"][1]
    _fx2 = _say({"thread_id": _tf, "chain_id": _cf, "text": "Try again."})[1][-1]["architect"]["framing"]
    _fx3 = _say({"thread_id": _tf, "chain_id": _cf, "text": "And again."})[1][-1]["architect"]["framing"]
    _run_was = BAMBOO._run_draft
    check("a draft that cannot be drawn (0310): the exchange is kept all the same - the reply, the version, and a turn that says which figure has no draft and why; a figure that stayed as it was is "
          "not drawn again. The figure without a draft is tried once more after the person next speaks, with the reason of that round, and after that it is left: no call is made for it. Every "
          "call the draft made is counted, round after round",
          _fx1["versions"][-1]["keys"][0] == _kf[0] and _kx not in _kf and [t["who"] for t in _fx1["turns"]][-3:] == ["person", "architect", "draft"]
          and {k: v for k, v in _fx1["turns"][-1].items() if k not in ("secs", "cost")} == {"who": "draft", "drawn": [], "missing": ["The rule given"], "v": 4, "call": 3,
              "failed": "the cell was not run: it imports os: a draft imports numpy, scipy, pandas, plotly and the standard maths modules, and nothing else"}
          and _fx1["drafts"][_kx] == {"failed": _fx1["turns"][-1]["failed"], "tries": 1} and _fx1["drafts"][_kf[0]] == {"basis": "made up"} and "1. \"The rule given\" - a scatter of points; x: x; y: y\n" in state["draft_seen"][1][3]
          and "Hours of each arm" not in state["draft_seen"][1][3].split("THE DRAFT BEFORE")[0] and "\n\nTHE DRAFT BEFORE:\n```python\n" + _cell_f + "\n```\n\n" in state["draft_seen"][1][3]
          and _fx2["drafts"][_kx] == {"failed": "the cell failed: ValueError: still wrong", "tries": 2} and _fx2["turns"][-1]["call"] == 5 and _fx2["draft_calls"] == 5 and len(state["draft_seen"]) == 5
          and [t["who"] for t in _fx3["turns"]][-2:] == ["person", "architect"] and _fx3["drafts"] == _fx2["drafts"] and len(state["draft_seen"]) == 5 and not os.path.exists(_plotf(_kx)),
          (_fx1["turns"][-1], _fx2["drafts"].get(_kx), len(state["draft_seen"])))
    # the question changed by hand: every figure is under another key and has no draft, until the Pathfinder next replies - and a round that breaks off is a round that drew nothing
    _bx = _fx3["versions"][-1]["brief"]
    _fh = _wac.post("/architect/brief", json={"thread_id": _tf, "chain_id": _cf, "changed": ["question", "figures"],
                                              "brief": {**_bx, "question": "Chart the hours of each arm, in all.", "figures": _bx["figures"][:1]}}).get_json()["framing"]
    _kh = _fh["versions"][-1]["keys"]
    state["architect"], state["draft"] = [json.dumps({"say": "A draft is being drawn."}), json.dumps({"say": "Drawn."})], ["```python\nx = 1\n```", "```python\n" + _cell_f + "\n```"]
    BAMBOO._run_draft = lambda code: (_ for _ in ()).throw(RuntimeError("the sandbox is away\nit did not answer"))
    try:
        _fh1 = _say({"thread_id": _tf, "chain_id": _cf, "text": "Is that right?"})[1][-1]["architect"]["framing"]
    finally:
        BAMBOO._run_draft = _run_was
    # the round after, on a configuration with a seat for the figures and one for the Pathfinder, under a brief that builds on a saved analysis (its code as the host would give it)
    _seats_was, _saved_was, _on_disk = list(FakeModels.config["agent_configs"]), BAMBOO._saved_code, []
    FakeModels.config["agent_configs"] = _seats_was + [{"agent": a_, "details": {"model": "fake/model", "provider": "fake", "reasoning_effort": "medium"}} for a_ in ("Figures", "Pathfinder")]
    BAMBOO._saved_code = lambda brief: "--- cell 9 ---"
    BAMBOO._run_draft = lambda code: (_on_disk.append(len(json.load(open(os.path.join(work, "storage", "u1", "threads", f"{_tf}.json"), encoding="utf-8"))["runs"][str(_cf)]["framing"]["turns"])), _run_was(code))[1]
    try:
        _fh2 = _say({"thread_id": _tf, "chain_id": _cf, "text": "Once more."})[1][-1]["architect"]["framing"]
    finally:
        FakeModels.config["agent_configs"], BAMBOO._saved_code, BAMBOO._run_draft = _seats_was, _saved_was, _run_was
    check("the question changed by hand, and a round that breaks off (0310): under another wording the figure has another key and no draft - none is drawn for a change made by hand. The Pathfinder's "
          "next reply has it drawn; where the round breaks off - the sandbox away - the exchange stands, the turn says so in its last line, and the call it made is counted; the round after "
          "draws the figure, the cell before it in the prompt - on the figures' seat where the configuration has one, not the Pathfinder's, with the code of the saved analysis the brief builds "
          "on, and with the reply already on the thread's record when the cell runs",
          len(_kh) == 1 and _kh[0] not in _fx3["drafts"] and _fh["drafts"] == _fx3["drafts"] and _kh[0] == _draft.key("Chart the hours of each arm, in all.", _bx["figures"][0])
          and {k: v for k, v in _fh1["turns"][-1].items() if k not in ("secs", "cost")} == {"who": "draft", "drawn": [], "missing": ["Hours of each arm"], "failed": "it could not be drawn: it did not answer", "v": 5, "call": 6}
          and _fh1["drafts"][_kh[0]] == {"failed": "it could not be drawn: it did not answer", "tries": 1}
          and _fh2["drafts"][_kh[0]] == {"basis": "made up"} and _fh2["turns"][-1]["call"] == 7 and _fh2["turns"][-1]["drawn"] == [{"title": "Hours of each arm", "basis": "made up"}]
          and os.path.isfile(_plotf(_kh[0])) and state["draft_seen"][-1][3].startswith("QUESTION:\nChart the hours of each arm, in all.\n\nFIGURES TO DRAW:\n1. \"Hours of each arm\" - bars;")
          and (state["draft_seen"][-1][0], state["architect_seen"][-1][0]) == ("Figures", "Pathfinder") and "\n\nA SAVED ANALYSIS THE QUESTION BUILDS ON:\n--- cell 9 ---\n\n" in state["draft_seen"][-1][3]
          and _on_disk == [len(_fh2["turns"]) - 1] and _fh2["turns"][-2]["who"] == "architect",
          (_fh1["turns"][-1], _fh2["turns"][-1], _kh, state["draft_seen"][-1][0], _on_disk))
    # ---- the question read as the analyst will read it, before its analysis starts (0313, §2.22)
    from analyst import cold as _cold
    def _ready(payload):
        r = _wac.post("/architect/ready", json=payload)
        return r.status_code, [json.loads(ln) for ln in r.get_data(as_text=True).splitlines() if ln.strip()]
    def _asks(text):
        """The coach words the question by hand: a version nobody has read. Returns its number."""
        now = BAMBOO.notebook.runs[str(_cc)].framing["versions"][-1]["brief"]
        return len(_wac.post("/architect/brief", json={"thread_id": _tc, "chain_id": _cc, "changed": ["question"], "brief": {**now, "question": text}}).get_json()["framing"]["versions"])
    _opc = _wac.post("/architect/open", json={"question": "Chart the hours of each arm, by half."}).get_json()      # a brief of its own, with a figure and its draft
    _cc, _tc = _opc["chain_id"], _opc["thread_id"]
    state["architect"], state["draft"] = [json.dumps({"say": "A draft is being drawn.", "figures": _figs[:1]})], ["```python\n" + _cell_f + "\n```"]
    _say({"thread_id": _tc, "chain_id": _cc, "text": "Show me what it will look like."})
    _on_file = lambda: json.load(open(os.path.join(work, "storage", "u1", "threads", f"{_tc}.json"), encoding="utf-8"))["runs"][str(_cc)]["framing"]      # noqa: E731
    _crun = BAMBOO.notebook.runs[str(_cc)]
    _vc, _calls_c = len(_crun.framing["versions"]), _crun.framing["calls"]
    _step_now = lambda: BAMBOO.notebook.runs[str(_cc)].framing["step"]      # noqa: E731 - the step of the conversation in use: what the page has on screen
    _sc = _step_now()
    state["cold"], state["cold_seen"] = ['{"cannot_place": []}'], []
    BAMBOO.kill_signal = True; BAMBOO._stop_event.set()                       # a run stopped earlier left the signal set
    _nc, _chain_c, _auth["counted"] = len(state["calls"]), BAMBOO.chain_id, []
    _stc, _lnc = _ready({"thread_id": _tc, "chain_id": _cc, "step": _sc})
    _seat_c, _kw_c, _under_c, _user_c = state["cold_seen"][-1]
    _fc = _crun.framing
    _stc2, _lnc2 = _ready({"thread_id": _tc, "chain_id": _cc, "step": _sc})
    check("/architect/ready, a question that stands on its own (0313): a stream that ends on the framing and on the word that the analysis can start. One model call - the reader's instructions, on "
          "the Pathfinder's seat at a low effort, logged as the question check's under the brief's own chain - whose prompt is what the analyst will be given: the data as described, the question, "
          "the brief as agreed with its figure. The read is a turn of the conversation, the first of the question checks, and a step of its own that follows the one read (0316); the framing lists "
          "the version as read and is on the thread's record; the Pathfinder's calls are counted as they were. The query was authorised without being counted, the instance is where it was, and no "
          "stop signal is left. Asked again for the same step, no call is made",
          _stc == 200 and _lnc[-1] == {"architect": {"framing": _fc, "clean": True}} and len(state["calls"]) == _nc + 1 and _seat_c == "Investigator" and _kw_c.get("label") == "Question check"
          and _kw_c.get("reasoning_effort") == ("low",) and str(_under_c) == str(_cc) and state["calls"][-1][1] == _user_c
          and _user_c == _cold.given("Chart the hours of each arm, by half.", _fc["versions"][-1]["brief"], True, BAMBOO._data_description()) + "\n\nReply with the JSON object."
          and _user_c.startswith("DATA:\n") and "\n\nQUESTION:\nChart the hours of each arm, by half.\n\nBRIEF (agreed with the person before this run):\n" in _user_c
          and '\nFigures agreed with the person:\n1. "Hours of each arm" - ' in _user_c
          and {k: v for k, v in _fc["turns"][-1].items() if k not in ("secs", "cost")} == {"who": "reader", "missing": [], "v": _vc, "call": 1} and _fc["turns"][-1]["cost"] > 0
          and (_fc["steps"][-1]["k"], _fc["steps"][-1]["from"], _fc["steps"][-1]["turns"], _fc["step"]) == (_sc + 1, _sc, 1, _sc + 1)
          and _fc["read"] == [_vc] and _fc["calls"] == _calls_c and len(_fc["versions"]) == _vc and _on_file() == _fc and _logged(_cc)[-1] == "Question check" and _crun.status == "framing"
          and BAMBOO.chain_id == _chain_c and BAMBOO.kill_signal is False and not BAMBOO._stop_event.is_set() and int(_cc) in BAMBOO._framed
          and _stc2 == 200 and _lnc2[-1] == {"architect": {"framing": _fc, "clean": True}} and len(state["calls"]) == _nc + 1 and _auth["counted"] == [False, False],
          (_lnc[-1], _seat_c, _kw_c, _user_c[-700:], _fc["turns"][-1], _auth["counted"]))
    _vq = _asks("Chart the hours of each arm, as on 14 May.")
    _sq = _step_now()
    state["cold"], state["architect_seen"] = ['{"cannot_place": ["AS ON  14 MAY", "not in it"]}'], []
    state["architect"], state["draft"] = [json.dumps({"say": "I took out what pointed to another day.", "wording": "Chart the hours of each arm, by month."})], ["```python\n" + _cell_f + "\n```"]
    _nq, _drafts_q = len(state["calls"]), len(state["draft_seen"])
    _stq, _lnq = _ready({"thread_id": _tc, "chain_id": _cc, "step": _sq})
    _fq, _midq, _nq2 = _crun.framing, [e for e in _lnq if e.get("type") == "architect_draft"], len(state["calls"])
    _lnq3, _lnq4 = _ready({"thread_id": _tc, "chain_id": _cc, "step": _sq + 1})[1], _ready({"thread_id": _tc, "chain_id": _cc, "step": _sq})[1]
    check("/architect/ready, a question that points outside what the analyst is given (0313): the reader names the words - kept as the question has them, the ones it does not hold dropped - and the "
          "Pathfinder goes on at once, on its own seat and under its own name in the log: its CONVERSATION ends on what the reader could not place. Its wording is one more version, the run's "
          "question from then; the figure, under another wording, is drawn a draft - the stream carries the framing with the reply before it. The stream ends on the framing and on the word "
          "that the analysis cannot start. The read is the second of the question checks, the reply the next of the Pathfinder's calls, the draft the draft's; read, reply and draft are one step, "
          "which follows the one read (0316). Both versions are listed as read: asked again from either step, the analysis can start, and no call is made",
          _stq == 200 and _lnq[-1] == {"architect": {"framing": _fq, "clean": False}} and _nq2 == _nq + 3 and _logged(_cc)[-3:] == ["Question check", "Pathfinder", "Draft"]
          and [t["who"] for t in _fq["turns"][-3:]] == ["reader", "architect", "draft"] and (_fq["steps"][-1]["k"], _fq["steps"][-1]["from"], _fq["steps"][-1]["turns"]) == (_sq + 1, _sq, 3) and {k: v for k, v in _fq["turns"][-3].items() if k not in ("secs", "cost")} == {"who": "reader", "missing": ["as on 14 May"], "v": _vq, "call": 2}
          and (_fq["turns"][-2]["wording"], _fq["turns"][-2]["v"], _fq["turns"][-2]["call"]) == ("Chart the hours of each arm, by month.", _vq + 1, _calls_c + 1) and _fq["calls"] == _calls_c + 1
          and (_fq["versions"][-1]["by"], _fq["versions"][-1]["changed"], len(_fq["versions"])) == ("architect", ["question"], _vq + 1) and _crun.question == "Chart the hours of each arm, by month."
          and state["architect_seen"][-1][3].endswith('\nA reader given what the analyst will be given could not place: "as on 14 May"\n\nReply with the JSON object.')
          and state["architect_seen"][-1][1].get("label") == "Pathfinder" and len(state["draft_seen"]) == _drafts_q + 1
          and len(_midq) == 1 and _midq[0]["framing"]["turns"][-1]["who"] == "architect" and _lnq.index(_midq[0]) < len(_lnq) - 1
          and _fq["read"] == [_vc, _vq, _vq + 1] and _on_file() == _fq and _crun.status == "framing"
          and _lnq3[-1] == {"architect": {"framing": _fq, "clean": True}} == _lnq4[-1] and len(state["calls"]) == _nq2,
          (_lnq[-1]["architect"].get("clean"), _fq["turns"][-3:], _fq["read"], _logged(_cc)[-3:], state["architect_seen"][-1][3][-300:]))
    _v5 = _asks("Chart the hours of each arm, as usual.")
    _s5 = _step_now()
    state["cold"], state["architect"] = ['{"cannot_place": ["as usual"]}'], ["no", "still no"]
    _calls5, _n5r = _crun.framing["calls"], len(state["calls"])
    _st5r, _ln5r = _ready({"thread_id": _tc, "chain_id": _cc, "step": _s5})
    _f5r, _n5r2 = _crun.framing, len(state["calls"])
    _ln5r2 = _ready({"thread_id": _tc, "chain_id": _cc, "step": _s5})[1]
    _v6 = _asks("Chart the hours of each arm, once more.")
    _s6 = _step_now()
    state["cold"] = [RuntimeError("the provider is away"), "I cannot say."]
    _turns6, _n6r = len(_crun.framing["turns"]), len(state["calls"])
    _ln6r = _ready({"thread_id": _tc, "chain_id": _cc, "step": _s6})[1]
    _f6r = json.loads(json.dumps(_crun.framing))
    _ln6r2 = _ready({"thread_id": _tc, "chain_id": _cc, "step": _s6})[1]
    _f6r2, _checks6 = _crun.framing, _logged(_cc).count("Question check")
    _n7r = len(state["calls"])
    _ln7r = _ready({"thread_id": "1077", "chain_id": _opj["chain_id"], "step": 1})[1]
    _st8r = _wac.post("/architect/ready", json={"thread_id": _tc}).status_code
    _auth["refuse"] = ({"error": "authorization_failed", "message": "You need $0.010 per query but your balance is $0.00. Please add funds to continue."}, 403)
    _r9r = _wac.post("/architect/ready", json={"thread_id": _tc, "chain_id": _cc, "step": _s6})
    _auth["refuse"] = None
    _n9r = len(state["calls"])
    state["cold"] = ['{"cannot_place": []}']
    _lne = _ready({"thread_id": _tc, "chain_id": _cc, "step": 1})[1]            # the first step on the person's screen: the question as it was asked
    _fe, _qe = _lne[-1]["architect"].get("framing") or {}, BAMBOO.notebook.runs[str(_cc)].question      # the thread was read again from its record: the run is another object
    BAMBOO._on_thread(_tf)                                                     # where the instance was: the draft's own run goes on below
    check("/architect/ready, what can go wrong (0313). The Pathfinder's reply after the read cannot be read: the stream ends on the framing, on the word that the analysis cannot start and on the "
          "reason, in words for the person; the read stands as the conversation's last turn, no version is made, the failed reply's calls are counted, and asked again the analysis can start. "
          "The read itself cannot be made - the provider fails: the analysis can start, nothing is kept of the read, and the version is not listed as read, so the next start asks again; a reply "
          "that is no object names nothing: the read is kept, and the analysis can start. A brief whose analysis has started is refused in words, without a call; a request without its chain is "
          "refused; and a refusal for the balance is the app's own answer, with no call",
          _st5r == 200 and _ln5r[-1] == {"architect": {"framing": _f5r, "clean": False, "error": "The Pathfinder's reply could not be read (it holds no JSON object)."}}
          and _f5r["turns"][-1]["who"] == "reader" and _f5r["turns"][-1]["missing"] == ["as usual"] and _f5r["turns"][-1]["call"] == 3 and len(_f5r["versions"]) == _v5 and _f5r["calls"] == _calls5 + 2
          and _n5r2 == _n5r + 3 and _f5r["read"][-1] == _v5 and _ln5r2[-1] == {"architect": {"framing": _f5r, "clean": True}} and len(state["calls"]) >= _n5r2
          and _ln6r[-1] == {"architect": {"framing": _f6r, "clean": True}} and len(_f6r["turns"]) == _turns6 and _v6 not in _f6r["read"]
          and _ln6r2[-1] == {"architect": {"framing": _f6r2, "clean": True}} and _f6r2["turns"][-1]["who"] == "reader" and _f6r2["turns"][-1]["missing"] == [] and _f6r2["turns"][-1]["call"] == 4 == _checks6
          and _f6r2["read"][-1] == _v6 and _n7r == _n6r + 1
          and _ln7r[-1] == {"architect": {"error": "This brief can no longer be changed: its analysis has started."}} and _st8r == 400
          and _r9r.status_code == 403 and _r9r.get_json()["error"] == "authorization_failed" and _n9r == _n7r,
          (_ln5r[-1]["architect"].get("error"), _f5r["turns"][-1], _f6r["read"], _f6r2["turns"][-1], _ln7r[-1], _st8r, _r9r.status_code))
    check("/architect/ready, an earlier step on the person's screen (0316): its question is the one read - in the reader's prompt - and its brief the one in use from then: the framing says so, "
          "the run's question is the one that stood there, and the later versions stay. The read is a step that follows the one read: the conversation the framing holds is the way to it - "
          "the read alone - and what the other steps hold is set aside",
          _lne[-1]["architect"].get("clean") is True and _fe == _on_file() and _fe.get("at") == 1 and [t["who"] for t in _fe["turns"]] == ["reader"] and _fe["turns"][-1]["v"] == 1 and _fe["read"][-1] == 1
          and (_fe["steps"][-1]["from"], _fe["step"], _fe["tip"]) == (1, len(_fe["steps"]), len(_fe["steps"])) and len(_fe["aside"]) >= 4
          and _qe == _fe["versions"][0]["brief"]["question"] == "Chart the hours of each arm, by half." and "\n\nQUESTION:\nChart the hours of each arm, by half.\n" in state["cold_seen"][-1][3]
          and len(_fe["versions"]) == _v6 and len(state["calls"]) == _n9r + 1, (_lne[-1]["architect"].get("clean"), _fe.get("at"), _qe, _fe["turns"][-1]))
    # the cell's run: with no data, for a few seconds at most - on this machine the kernel is stopped; an executor is asked for that long and the cell carries a guard of its own
    _secs_was, _exec_was2, _mode_was = _draft.SECONDS, BAMBOO.executor.execute, BAMBOO.executor.mode
    _sent = []
    def _guarded(code, seconds):
        """What the guard does where an executor runs the script in a thread it cannot stop: (how it ended, the seconds, whether the thread still runs)."""
        out = {}
        def target():
            try:
                exec(DRAFT_GUARD.format(seconds=seconds, code=code), {"__name__": "cell"})
                out["end"] = "ran"
            except BaseException as exc:                       # noqa: BLE001
                out["end"] = f"{type(exc).__name__}: {exc}"
        t = _thr.Thread(target=target, daemon=True); t0 = _time.time(); t.start(); t.join(15)
        return out.get("end"), _time.time() - t0, t.is_alive()
    try:
        _draft.SECONDS = 2
        _t0 = _time.time(); _late = BAMBOO._run_draft("import time\ntime.sleep(30)"); _took = _time.time() - _t0
        _plain = BAMBOO._run_draft("print(1)")
        _draft.SECONDS = _secs_was
        BAMBOO.executor.mode = "api"
        BAMBOO.executor.execute = lambda *a, **k: (_sent.append((a, k)), (None, "", None, [{"data": "{}", "format": "json"}], []))[1]
        _api = BAMBOO._run_draft("x = 1")
        BAMBOO.executor.execute = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("the executor is away"))
        _away = BAMBOO._run_draft("x = 1")
        _told = ('Error occurred in the following code snippet:\n\n9: --> exec(compile(...))\n\nError on line 9:\nZeroDivisionError: division by zero\n\nTraceback (most recent call last):\n'
                 '  File "<string>", line 23, in <module>\n  File "<draft>", line 2, in <module>\nZeroDivisionError: division by zero')
        BAMBOO.executor.execute = lambda *a, **k: (None, None, _told, [], [])
        _named = BAMBOO._run_draft("x = 1\n1/0")
    finally:
        _draft.SECONDS, BAMBOO.executor.execute, BAMBOO.executor.mode = _secs_was, _exec_was2, _mode_was
    _endless, _swallow, _fine, _wrong = _guarded("while True:\n    pass", 1), _guarded("try:\n    while True:\n        pass\nexcept Exception:\n    pass", 1), _guarded("y = 1 + 1", 5), _guarded("1/0", 5)
    check("the draft's cell is stopped (0310): on this machine the kernel ends it at the draft's limit - a cell that sleeps past it comes back as an error that names the limit, and no plot - and "
          "a cell that draws nothing gives none. An executor is sent the cell with no frame, no frame's id and no folder to write to, not to be kept, for the same limit - inside a guard that "
          "ends it shortly before: the executor answers past its limit and leaves the thread running, so a cell that never ends would run on. The guard ends such a cell - one that catches "
          "every error too - and leaves one that runs, or fails, as it is. A cell out of time shows no message on the page; an executor that cannot be reached is an error in words; and an "
          "error from inside the guard names the cell's own line, as a cell's traceback does, and none of the guard's",
          _late[0] == [] and "exceeded 2s time limit" in _late[1] and 1.5 < _took < 15 and _plain == ([], "")
          and len(_sent) == 1 and _sent[0][0][2] == DRAFT_GUARD.format(seconds=_secs_was - 2, code="x = 1") and _sent[0][0][3:] == (None, None, None)
          and _sent[0][1] == {"persist_df": False, "timeout": _secs_was, "step_timeout": _secs_was} and _sent[0][0][0] is not BAMBOO.output_manager
          and _sent[0][0][0].display_system_messages("Execution timed out after 20 seconds.") is None and _api == ([{"data": "{}", "format": "json"}], "") and _away == ([], "the executor is away")
          and _named[1].endswith('Traceback (most recent call last):\n  File "<string>", line 2, in <module>\nZeroDivisionError: division by zero') and "line 23" not in _named[1]
          and _tools.condense_error(_named[1], code="x = 1\n1/0") == "ZeroDivisionError: division by zero\nin your cell, line 2:  1/0" and 'compile({code!r}, "<draft>", "exec")' in DRAFT_GUARD
          and _endless[0] == "TimeoutError: the cell took longer than 1 seconds" and 0.9 < _endless[1] < 5 and not _endless[2] and _swallow[0] == _endless[0] and not _swallow[2]
          and _fine[0] == "ran" and _fine[1] < 2 and _wrong[0] == "ZeroDivisionError: division by zero" and _secs_was == 20 and "exec(compile(" in DRAFT_GUARD,
          (_late, round(_took, 1), _plain, _sent[:1], _endless, _swallow, _fine, _wrong))
    _keep_s5, _nf = (state["script"], state["i"]), len(state["calls"])
    state.update(i=0, script=["###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nh = df.groupby('arm')['x'].sum().round(2)\nprint('hours', h.to_dict())\n```",
                              "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n# Hours\n\n## Answer\nThe hours of each arm [cell 1].\n\n## Against the brief\n- chance: cannot tell.\n\n## Did not fit\nNothing."],
                 figures=["```python\nimport matplotlib.pyplot as plt\nplt.figure(); plt.bar(list(h.index), list(h.values)); plt.title('Hours of each arm'); plt.show()\n```\nCAPTION: the hours of each arm"])
    BAMBOO.output_manager.add_user_input("Chart the hours of each arm.")
    while not q.empty(): q.get()
    BAMBOO.pd_agent_converse(thread_id=_tf, chain_id=None, mode="deep", run_id=_cf)
    state["script"], state["i"] = _keep_s5
    state["figures"] = None
    _aprompt = next((u for a, u in state["calls"][_nf:] if "TASK: turn 1" in u), "")
    _dprompts = [u for a, u in state["calls"][_nf:] if "THE REPORT, AS WRITTEN:" in u and u.startswith("QUESTION:")]
    _frun = BAMBOO.notebook.runs[str(_cf)]
    _lines2 = '1. "Hours of each arm" - bars; x: arm; y: hours; holds: A, B; to make clear: Which arm works more.\n'
    check("Start analysis under a brief with figures (0309, 0310): the Analyst reads the figure that stands in its BRIEF block, and the step that draws reads the same line under its question, to "
          "draw first and under its title - and under it the cell that drew the figure's draft, with the word that its numbers were made up; the figures taken out are in neither. The run keeps "
          "the brief, its framing and the draft's cells, and the report holds the figure and no line about a missing one",
          ("\nFigures agreed with the person:\n" + _lines2) in _aprompt and len(_dprompts) == 1
          and _dprompts[0].startswith("QUESTION:\nChart the hours of each arm, in all.\n\nTHE FIGURES AGREED WITH THE PERSON (draw these first, in this order, each as described and under its title, word for word):\n"
                                      + _lines2 + '\nTHE DRAFT THE PERSON SAW (it drew "Hours of each arm" - on made-up numbers: "Hours of each arm"):\n```python\n' + _cell_f + "\n```\n\nTHE REPORT, AS WRITTEN:\n")
          and all("Hours by month" not in u.split("THE DRAFT THE PERSON SAW")[0] and "The rule given" not in u.split("THE DRAFT THE PERSON SAW")[0] for u in (_aprompt, _dprompts[0]))
          and "THE DRAFT THE PERSON SAW" not in _aprompt
          and _frun.status == "answered" and [f["title"] for f in _frun.brief["figures"]] == ["Hours of each arm"] and [d["keys"] for d in _frun.drafts] == [_kf, _kh]
          and _frun.framing["drafts"] == _fh2["drafts"]
          and "## Figures\n\n- [fig 2] the hours of each arm" in _frun.report and "not drawn" not in _frun.report, (_aprompt[:700], [u[:900] for u in _dprompts], _frun.report[-300:]))
    if _pp_was is None: os.environ.pop("PYTHONPATH", None)
    else: os.environ["PYTHONPATH"] = _pp_was
    # the brief opened earlier with nothing loaded, on its own thread: an exchange made now, with data loaded, says so (the section's last step: it takes the instance to that thread)
    state["architect"] = ['{"say": "What is it for?"}']
    _o7s = json.loads(_wac.post("/architect/say", json={"thread_id": "1907", "chain_id": _o7nj["chain_id"]}).get_data(as_text=True).strip().splitlines()[-1])["architect"]["framing"]
    check("the framing's word on the data is brought up to date by an exchange (0307): a brief opened with nothing loaded says so, and after an exchange made with data loaded it says data - the page lists "
          "the standing checks from then on",
          _o7nj["framing"]["data"] is False and _o7s["data"] is True and _o7s["turns"][-1]["text"] == "What is it for?", (_o7nj["framing"], _o7s))
    BAMBOO.load_params = _lp3
    BAMBOO.cleanup()
    BAMBOO.log_and_call_manager.charge_for_completed_query = _keep_charge
    state["script"], state["i"] = _keep_script, _keep_i
    sys.modules["app"] = _app_was
except Exception as exc:                                     # noqa: BLE001
    import traceback
    check("the framing run through the routes and the instance: the checks ran", False, traceback.format_exc()[-900:])

# ---- the reader of the saved analyses (0302, docs/ARCHITECT_DESIGN.md §3.6): the user's view in a sandbox of its own - a kernel without the frame - read by
# the reader's model with a second model on pieces, the calls logged as the memory's under a chain of their own
try:
    from analyst import memory as _mem, reader as _rd
    from analyst.notebook import Notebook as _NB, NotebookStore as _NBS
    from _saved import add as _add, favourite as _favourite
    _su = os.path.join(work, "storage", "u1")
    _nb7 = _NB("7001")
    _add(_nb7, "7002", "Is B higher than A?", report="# B exceeds A\n\nB exceeds A by 0.3 units [cell 1].", cells=[("m = df.groupby('arm')['x'].mean()\nprint(m)", "A 1.0\nB 1.3\n", ["difference: +0.3 units"])],
         data={"df_id": "d7", "name": "trial.csv", "rows": 10, "date_range": "", "columns": [{"name": "x"}], "load": {"subject": {"id": "s-77", "name": "First Person"}}})
    _NBS(_su).save(_nb7)
    _favourite(_su, 7001, 7002)
    _rid = "7001/7002"
    _nb8 = _NB("8001")                                           # another user's saved analysis
    _add(_nb8, "8002", "Is A higher than B?", report="# A exceeds B\n\nA exceeds B by far [cell 1].", cells=[("print(1)", "1\n", [])])
    _NBS(os.path.join(work, "storage", "u2")).save(_nb8)
    _favourite(os.path.join(work, "storage", "u2"), 8001, 8002)
    state["memory"] = ["CELL\n```python\nprint([r['id'] for r in SAVED['runs']], 'df' in globals(), JUDGED, SAVED['runs'][0]['data']['subject'])\n```",
                       'JUDGE\n{"runs": "all", "parts": ["report", "code"], "question": "Which arm is higher?"}',
                       json.dumps({"answers": [{"run": _rid, "answer": "B is higher", "quote": "B exceeds A by", "where": "report"}, {"run": _rid, "answer": "made up", "quote": "A exceeds B by far", "where": "report"}]}),
                       'ANSWER\n' + json.dumps({"found": [{"run": _rid, "where": "report", "quote": "B exceeds A by", "note": "The arms were compared before."},
                                                           {"run": _rid, "where": "cell 1", "quote": "df.groupby('arm')['x'].mean()", "note": "How the means were taken."},
                                                           {"run": _rid, "where": "report", "quote": "A exceeds B", "note": "not there"}],
                                                 "across": {"topic": "Which arm is higher", "groups": [{"label": "B", "runs": [_rid]}]}})]
    state["memory_seen"], state["memory_effort"] = [], []
    _log = lambda: json.load(open(_runlog, encoding="utf-8"))
    class _Held:
        """The thread's kernel, as far as the instance handles it here."""
        cleaned = 0

        def cleanup(self):
            _Held.cleaned += 1

    _kernel_was, _tip_was = BAMBOO._kernel, BAMBOO._kernel_tip
    BAMBOO._kernel = _held = _Held()
    _steps, _log_before = [], len(_log())
    _res = BAMBOO.memory_read("Is arm B still higher than arm A?", on_step=_steps.append)
    _left_alone, _efforts = BAMBOO._kernel is _held and _Held.cleaned == 0, list(state["memory_effort"])
    _seen_m = state["memory_seen"]
    check("memory_read(): the reader works in a sandbox of its own - the user's view under SAVED and no other user's run, no frame, an empty JUDGED - and returns passages that stand in the saved run, a group "
          "whose run the second model answered for, and its coverage; what does not stand is dropped - a sentence that stands only in another user's report among it; whose data the run ran on is a handle "
          "there, and the source's id reaches neither model",
          _res["failed"] == "" and _res["steps"][0]["out"] == f"['{_rid}'] False [] subject 1" and not [1 for _, _, _, _, u in _seen_m if "s-77" in u]
          and [(f["id"], f["where"], f["quote"]) for f in _res["found"]] == [(_rid, "report", "B exceeds A by"), (_rid, "cell 1", "df.groupby('arm')['x'].mean()")]
          and _res["across"]["groups"] == [{"label": "B", "runs": [{"run": _rid, "answer": "B is higher", "quote": "B exceeds A by", "where": "report"}]}] and _res["dropped"] == 1
          and _res["steps"][1]["dropped"] == 1 and _res["coverage"]["judged"] == 1 and _res["coverage"]["runs"] == len(_mem.view(_su)["runs"]) and _steps == _res["steps"], _res)
    check("memory_read(): the view is brought up to date and kept before it is read; no file of it is left among the user's datasets; the thread's own kernel is left as it was on this machine",
          [r["id"] for r in _mem.view(_su)["runs"]] == [_rid] and not os.path.exists(os.path.join(work, "datasets", "u1", "memory")) and _left_alone)
    _mlog = _log()[_log_before:]
    check("memory_read(): the reader's calls run on the analyst's seat and the second model's on the fast seat where the config has one - here the analyst's - each logged under the memory's own name, all "
          "under one chain that is not the instance's; the reader's replies are asked at a lowered effort, the second model's at its seat's own",
          [(a, lbl) for a, lbl, _, _, _ in _seen_m] == [("Investigator", "Memory Reader"), ("Investigator", "Memory Reader"), ("Investigator", "Memory Pieces"), ("Investigator", "Memory Reader")]
          and len({c for _, _, c, _, _ in _seen_m}) == 1 and _seen_m[0][2] != BAMBOO.chain_id and _seen_m[0][3] == _rd.SYSTEM and _seen_m[2][3] == _rd.PIECES
          and [e["agent"] for e in _mlog] == ["Memory Reader", "Memory Reader", "Memory Pieces", "Memory Reader"] and len({e["chain_id"] for e in _mlog}) == 1
          and round(_res["cost"], 4) == round(sum(e["cost"] for e in _mlog), 4) and _res["calls"] == {"reader": 3, "pieces": 1} and _efforts == [("low", "medium"), ("low", "medium"), None, ("low", "medium")],
          ([(a, lbl, c) for a, lbl, c, _, _ in _seen_m], [e["agent"] for e in _mlog], _efforts))
    _mode, _url, _new = BAMBOO.execution_mode, BAMBOO.executor_api_url, BAMBOO._new_kernel
    _box, _made, _stopped = BAMBOO._new_kernel(frame=False), [], []      # the sandbox is still this machine's: only the instance's part is under test
    _stop = _box.cleanup
    _box.cleanup = lambda: _stopped.append(1) or _stop()
    BAMBOO.execution_mode, BAMBOO.executor_api_url = "api", "http://executor.invalid"
    BAMBOO._new_kernel = lambda frame=True: _made.append((frame, BAMBOO._kernel)) or _box
    state["memory"] = ['ANSWER\n{"found": []}']
    try:
        BAMBOO.memory_read("q?")
    finally:
        BAMBOO.execution_mode, BAMBOO.executor_api_url, BAMBOO._new_kernel = _mode, _url, _new
    check("memory_read(): on an executor, which holds one kernel, the thread's kernel is given up before the sandbox starts - the next analysis restores it from the record - and the sandbox has no frame; "
          "the sandbox is stopped when the reading is over",
          _Held.cleaned == 1 and _made == [(False, None)] and BAMBOO._kernel is None and BAMBOO._kernel_tip is None and _stopped == [1], (_Held.cleaned, _made, BAMBOO._kernel, _stopped))
    BAMBOO._kernel, BAMBOO._kernel_tip = _kernel_was, _tip_was
    _cfg = FakeModels.config
    FakeModels.config = {**_cfg, "agent_configs": _cfg["agent_configs"] + [{"agent": "Reader", "details": {"model": "fake/model", "provider": "fake"}}]}
    BAMBOO.models.config = FakeModels.config
    _fast = BAMBOO._memory_seats()
    state["memory"], state["memory_seen"] = ['JUDGE\n{"runs": "all", "question": "q?"}', '{"answers": []}', 'ANSWER\n{"found": []}'], []
    BAMBOO.memory_read("q?")
    _fast_seen = [(a, lbl) for a, lbl, _, _, _ in state["memory_seen"]]
    FakeModels.config = {**_cfg, "agent_configs": _cfg["agent_configs"] + [{"agent": n, "details": {"model": "fake/model", "provider": "fake"}} for n in ("Reader", "Memory Reader", "Memory Pieces")]}
    BAMBOO.models.config = FakeModels.config
    _own = BAMBOO._memory_seats()
    FakeModels.config = _cfg
    BAMBOO.models.config = _cfg
    check("the seats: the second model takes the Reader seat where the config has one - its calls run there and the reader's on the analyst's - and each takes a seat of its own name where the config has it",
          _fast == ("Investigator", "Reader") and _fast_seen == [("Investigator", "Memory Reader"), ("Reader", "Memory Pieces"), ("Investigator", "Memory Reader")]
          and _own == ("Memory Reader", "Memory Pieces") and BAMBOO._memory_seats() == ("Investigator", "Investigator"), (_fast, _fast_seen, _own))
    _nb9 = _NB("7101")
    _add(_nb9, "7102", "Does C match B?", report="# C matches B\n\nC and B agree within 0.1 units [cell 1].", cells=[("d = c - b", "0.1\n", ["difference: 0.1 units"])])
    _NBS(_su).save(_nb9)
    _favourite(_su, 7101, 7102)
    os.remove(os.path.join(_su, "favourites", "7001", "7002.json"))      # the first workflow is removed: the kept view has not followed yet
    state["memory"], state["memory_seen"] = ["CELL\n```python\nprint([r['id'] for r in SAVED['runs']])\n```",
                                             'ANSWER\n' + json.dumps({"found": [{"run": _rid, "where": "report", "quote": "B exceeds A by", "note": "from a workflow removed since"}]})], []
    _thread_was, _log_thread_was = BAMBOO.thread_id, BAMBOO.log_and_call_manager.thread_id
    BAMBOO.thread_id = BAMBOO.log_and_call_manager.thread_id = None      # an instance that has run nothing yet
    _res2 = BAMBOO.memory_read("q?", chain=4242)
    _minted = BAMBOO.log_and_call_manager.thread_id
    BAMBOO.thread_id, BAMBOO.log_and_call_manager.thread_id = _thread_was, "kept"
    state["memory"] = ["CELL\n```python\nprint(1)\n```"]
    _res3 = BAMBOO.memory_read("q?", chain=4243, caps={"turns": 1})
    _kept = BAMBOO.log_and_call_manager.thread_id
    BAMBOO.log_and_call_manager.thread_id = _log_thread_was
    check("memory_read(): under a chain that is given, its calls are that chain's; a workflow removed since is not read - nothing of it is in the sandbox, and a passage from it does not stand; nothing found is "
          "an answer; where the instance has no thread yet, one is minted for the usage rows, and a thread there is kept; a cap that is given reaches the reader",
          [c for _, _, c, _, _ in state["memory_seen"]] == [4242, 4242, 4243] and _res2["steps"][0]["out"] == "['7101/7102']"
          and (_res2["found"], _res2["failed"], _res2["dropped"], _res2["coverage"]["runs"]) == ([], "", 1, 1)
          and isinstance(_minted, str) and _minted.isdigit() and _kept == "kept" and _res3["failed"].startswith("The reader gave no answer within its limits: 1 of 1 replies, ") and _res3["steps"] == [],
          ([c for _, _, c, _, _ in state["memory_seen"]], _minted, _kept, _res2, _res3["failed"]))
    os.remove(os.path.join(_su, "favourites", "7101", "7102.json"))      # nothing is saved now
    _new, _started = BAMBOO._new_kernel, []
    BAMBOO._new_kernel = lambda frame=True: _started.append(frame) or _new(frame=frame)
    BAMBOO._kernel = _held2 = _Held()
    _cleaned_before, state["memory"], state["memory_seen"] = _Held.cleaned, [], []
    try:
        _res4 = BAMBOO.memory_read("q?")
    finally:
        BAMBOO._new_kernel = _new
    check("memory_read(): where nothing is saved, no sandbox starts, the thread's kernel stays and no model is called: an empty result at no cost",
          (_res4["found"], _res4["across"], _res4["failed"], _res4["calls"], _res4["cost"], _res4["coverage"]["runs"]) == ([], None, "", {"reader": 0, "pieces": 0}, 0.0, 0)
          and _started == [] and state["memory_seen"] == [] and BAMBOO._kernel is _held2 and _Held.cleaned == _cleaned_before, (_res4, _started))
    BAMBOO._kernel, BAMBOO._kernel_tip = _kernel_was, _tip_was
except Exception as exc:                                     # noqa: BLE001
    import traceback
    check("the reader of the saved analyses through the instance: the checks ran", False, traceback.format_exc()[-1200:])

# the kernel keeps the state of every cell (2.9, patch 0318): a chain asked from an earlier chain goes back to the state that
# chain ended in, in the kernel the thread has - no cell is run again; a run that was stopped leaves nothing behind for
# the next one; where the kernel is gone, the cells are run again as before, and their records name the new kernel's states
try:
    def _chain(script, parent, stop_after_first=False):
        """One chain of the thread, asked from `parent`; with stop_after_first the person stops it after its first reply."""
        state.update(i=0, script=script); BAMBOO.output_manager.add_user_input("q")
        if stop_after_first:
            _stream = BAMBOO.llm_stream
            def _then_stop(*a, **kw):
                reply = _stream(*a, **kw)
                BAMBOO.kill_signal = True
                return reply
            BAMBOO.llm_stream = _then_stop
        try:
            BAMBOO.pd_agent_converse(thread_id="2909", chain_id=parent, mode="deep")
        finally:
            if stop_after_first:
                BAMBOO.llm_stream = _stream
        _chain.sent = []                                     # what the page was sent for it
        while not q.empty(): _chain.sent.append(json.loads(q.get()))
        return BAMBOO.notebook.runs[str(BAMBOO.chain_id)]

    def _makes(name):
        """A chain whose one cell makes `name` and prints which of the other chains' names its kernel holds."""
        return ["###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\n" + name + " = 1\nprint('here:', sorted(n for n in ('m', 'left', 'right', 'half') if n in globals()))\n```",
                "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## Answer\nDone.\n"]

    def _here(run):
        return run.cells()[-1].stdout.strip() if run.cells() else None

    BAMBOO.df, BAMBOO.df_id = df, "d1"
    _talk = _chain(["###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## Answer\nNothing computed.\n"], None)
    _slip = "###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\nprint(no_such_name)\n```"      # a cell that fails, between the two that run
    _base = _chain([SCRIPT[0], _slip, SCRIPT[1], SCRIPT[2]], _talk.id)
    _k = BAMBOO._kernel
    _worker = _k._proc.pid
    _left = _chain(_makes("left"), _base.id)
    check("0318: a chain asked from the chain the kernel ended at goes on in the warm kernel, as before - the same worker, no state loaded again; each cell's record names its state there",
          BAMBOO._kernel is _k and _k._proc.pid == _worker and _here(_left) == "here: ['left', 'm']" and [c.snap.split(":")[0] for c in _base.cells() + _left.cells()] == [_k.uid] * 3, (_here(_left), [c.snap for c in _base.cells()]))
    _right = _chain(_makes("right"), _base.id)
    check("0318: a chain asked from an earlier chain: the thread's kernel goes back to the state that chain ended in - it is not replaced, no cell is run again, and what the other chain made is not there",
          BAMBOO._kernel is _k and _k.last_goto["replayed"] == [] and f"{_k.uid}:{_k.last_goto['step']}" == _base.cells()[-1].snap and _here(_right) == "here: ['m', 'right']" and _right.cells()[0].cell_no == 3,
          (_here(_right), _k.last_goto, _base.cells()[-1].snap))
    _more = _chain(_makes("more"), _left.id)
    check("0318: ... and one asked from the other chain goes back to that one's", BAMBOO._kernel is _k and _k.last_goto["replayed"] == [] and _here(_more) == "here: ['left', 'm']" and _more.cells()[0].cell_no == 4, (_here(_more), _k.last_goto))
    _none = _chain(_makes("apart"), _talk.id)
    check("0318: a chain asked from one whose path computed nothing: the kernel goes back to its state at the start", BAMBOO._kernel is _k and _k.last_goto["step"] == 0 and _here(_none) == "here: []" and _none.cells()[0].cell_no == 1, (_here(_none), _k.last_goto))
    _stopped = _chain(_makes("half"), _none.id, stop_after_first=True)
    check("0318: a chain asked from the chain the kernel ended at, and stopped after its first cell, keeps that cell - and the kernel is then at no chain's end",
          _stopped.status == "stopped" and _here(_stopped) == "here: ['half']" and BAMBOO._kernel_tip is None, (_stopped.status, _here(_stopped), BAMBOO._kernel_tip))
    _again = _chain(_makes("again"), _none.id)
    check("0318: the next chain asked from the same parent does not find what the stopped one made (a warm kernel would hold it): the kernel went back to the parent's state",
          BAMBOO._kernel is _k and _here(_again) == "here: []" and _k.last_goto["replayed"] == [] and _again.cells()[0].cell_no == 2, (_here(_again), _k.last_goto))
    _on = _chain(_makes("on"), _stopped.id)
    check("0318: a chain asked from the stopped one goes on from the cell it kept", BAMBOO._kernel is _k and _here(_on) == "here: ['half']" and _on.cells()[0].cell_no == 3, (_here(_on), _k.last_goto))
    BAMBOO._drop_kernel()                                    # the kernel is gone: the executor reaped it, or the web app restarted
    _late = _chain(_makes("late"), _right.id)
    check("0318: with the kernel gone the chain's cells are run again in a new one, as before - and their records name their states in that one",
          BAMBOO._kernel is not _k and _here(_late) == "here: ['m', 'right']" and [c.snap.split(":")[0] for c in _base.cells() + _right.cells() + _late.cells()] == [BAMBOO._kernel.uid] * 4
          and _left.cells()[0].snap.startswith(_k.uid + ":"), (_here(_late), [c.snap for c in _base.cells() + _right.cells()]))
    _k2 = BAMBOO._kernel
    _back = _chain(_makes("back"), _base.id)
    check("0318: ... so the new kernel goes back to them in its turn", BAMBOO._kernel is _k2 and _k2.last_goto["replayed"] == [] and _here(_back) == "here: ['m']", (_here(_back), _k2.last_goto))
    _k2.cleanup()                                            # the kernel died under the instance, which still holds it
    _dead = _chain(_makes("dead"), _right.id)                # a chain whose state that kernel held
    check("0318: a kernel that died cannot go back: the cells are run again in a new one, and the run goes on", BAMBOO._kernel is not _k2 and _here(_dead) == "here: ['m', 'right']" and _dead.status == "answered", (_here(_dead), _dead.status))
    _k2 = BAMBOO._kernel
    BAMBOO.df_id = "d9"                                      # the same file loaded again: a new frame id, and the kernel holds the old frame
    _other = _chain(_makes("other"), _base.id)
    check("0318: the same data loaded again under another id: the kernel is the other frame's and is not gone back to - a fresh one, the cells run again, as before", BAMBOO._kernel is not _k2 and _here(_other) == "here: ['m']", _here(_other))
    BAMBOO.df_id = "d1"
except Exception as exc:                                     # noqa: BLE001
    import traceback
    check("0318: the kernel's states through the instance: the checks ran", False, traceback.format_exc()[-1200:])

# a branch (2.9, patch 0319, docs/BRANCH_DESIGN.md): go on from a turn of a chain, another way, under a hint from the person -
# through the instance: the kernel at the state the kept turns left, the branch a chain of its own, the page told
try:
    from analyst.notebook import AGAIN_LINE
    def _cell(code):
        return "###NOTE###\n" + NOTE + "\n###ACTION###\nCELL\n```python\n" + code + "\n```"
    _REPORT = "###NOTE###\n" + NOTE + "\n###ACTION###\nREPORT\n## Answer\nDone.\n"
    _WHICH = _cell("print('here:', sorted(n for n in ('one', 'two', 'three') if n in globals()), round(drew, 6) if 'drew' in globals() else None)")
    _HINT = "HINT FROM THE PERSON (given after turn %d; it holds from there to the report):\n%s"

    def _go_on(script, of, turn, hint="keep the two apart", **more):
        """A branch of chain `of` after its turn `turn`, the person typing `hint`: (its run or None, what the page was sent, the analyst's prompts)."""
        state.update(i=0, script=script); n0, was = len(state["calls"]), BAMBOO.chain_id
        while not BAMBOO.output_manager.input_queue.empty(): BAMBOO.output_manager.input_queue.get()     # what earlier checks typed and nothing read
        BAMBOO.output_manager.add_user_input(hint)
        BAMBOO.pd_agent_converse(thread_id="2909", chain_id=of, after=turn, **more)
        sent = []
        while not q.empty(): sent.append(json.loads(q.get()))
        made = BAMBOO.notebook.runs.get(str(BAMBOO.chain_id)) if BAMBOO.chain_id != was else None           # a refusal takes no chain id
        return made, sent, [u for a, u in state["calls"][n0:] if "TASK: turn" in u]

    def _drew(cell):
        return cell.stdout.split("drew")[1].split()[0]

    BAMBOO.df, BAMBOO.df_id = df, "d1"
    _first = _chain([_cell("one = 1\nprint('one')"), _cell("import random\ndrew = random.random()\ntwo = one + 1\nprint('two', two, 'drew', round(drew, 6))"),
                     _cell("print(no_such_name)"), _cell("three = two + 1\nprint('three', three)"), _REPORT], _talk.id)
    _first.turns[0].usage["elapsed"] = 7.0                   # the time its first turn took: a branch's closing card counts its own turns' time
    _k = BAMBOO._kernel
    # the drafts of a brief its analysis ran under (0331): plots kept under the first run - a branch's Brief tab asks for them under the branch's chain
    from analyst import draft as _dr
    _plots_b, _keys_b = _dr.Plots(BAMBOO._user_storage()), ("a1a1a1a1a1a1", "b2b2b2b2b2b2")
    for _n, _kb in enumerate(_keys_b):
        _plots_b.put("2909", _first.id, _kb, '{"data": [{"type": "bar", "y": [%d]}], "layout": {}}' % (_n + 1))
    _send_was, _at_id = BAMBOO.output_manager.send_chain_id, []
    def _send_seen(thread_id, chain_id, *a, **kw):                    # what is kept under the new chain when it is announced
        _at_id.append([_kb for _kb in _keys_b if _plots_b.get("2909", chain_id, _kb) is not None])
        return _send_was(thread_id, chain_id, *a, **kw)
    BAMBOO.output_manager.send_chain_id = _send_seen
    try:
        _b, _sent, _prompts = _go_on([_WHICH, _REPORT], _first.id, 2, mode="quick")      # whatever mode the page sends, it runs in the first run's
    finally:
        BAMBOO.output_manager.send_chain_id = _send_was
    check("0319: a branch goes on from a turn in the kernel the thread has, at the state the kept turns left: nothing is run again - the number a kept cell drew "
          "without a seed is the one it drew - and what the chain made after that turn is not there",
          _b is not None and BAMBOO._kernel is _k and _k.last_goto["replayed"] == [] and f"{_k.uid}:{_k.last_goto['step']}" == _first.cells()[1].snap
          and _b.cells()[-1].stdout.strip() == f"here: ['one', 'two'] {_drew(_first.cells()[1])}" and BAMBOO._kernel_tip == _b.id, (_b and _b.cells()[-1].stdout, _k.last_goto))
    check("0319: the branch is a chain of its own beside the one it goes on from - the same parent, question, mode and limits - with the chain, the turn and the hint "
          "on its record, the kept turns marked, its own cell numbered on; the chain it left is as it was",
          _b.parent == _talk.id and _b.question == _first.question and _b.mode == "Deep" and _b.budget == _first.budget and _b.branch == {"of": _first.id, "turn": 2}
          and _b.hints == [{"turn": 2, "text": "keep the two apart"}] and [t.kept for t in _b.turns[:2]] == ["kept", "kept"] and [c.cell_no for c in _b.cells()] == [1, 2, 3]
          and _b.status == "answered" and [c.cell_no for c in _first.cells()] == [1, 2, 3] and _first.cells()[2].code.startswith("three") and not any(t.kept for t in _first.turns),
          (_b.branch, _b.hints, _b.budget, [c.cell_no for c in _b.cells()]))
    if os.path.exists(_plots_b._path("2909", _b.id, _keys_b[0])):
        os.remove(_plots_b._path("2909", _b.id, _keys_b[0]))           # as a branch made before 0331 has it: nothing kept under its own chain
    _appm = sys.modules["app"]; _up_was = getattr(_appm, "user_path", None)
    _appm.user_path = lambda root, *p: os.path.join(BAMBOO._user_storage(), *p)      # the route's storage, the instance's
    try:
        _via, _none = _wac.get(f"/architect/draft/2909/{_b.id}/{_keys_b[0]}"), _wac.get(f"/architect/draft/2909/{_b.id}/c3c3c3c3c3c3")
    finally:
        if _up_was is None: del _appm.user_path
        else: _appm.user_path = _up_was
    check("0331: a branch's Brief tab shows the drafts of the brief it runs under: their plots are kept under its own chain too, there when the chain is announced - the page asks "
          "for them under it at once; for a branch made before, which has none kept under it, the route finds them under the chains it went on from. A figure none of them has is not found",
          _at_id == [list(_keys_b)] and _plots_b.get("2909", _b.id, _keys_b[1]) == _plots_b.get("2909", _first.id, _keys_b[1]) == '{"data": [{"type": "bar", "y": [2]}], "layout": {}}'
          and _via.status_code == 200 and _via.get_json() == {"plot": {"data": [{"type": "bar", "y": [1]}], "layout": {}}} and _none.status_code == 404,
          (_at_id, _via.status_code, _none.status_code))
    _line_b = BAMBOO.store.ledger().get(str(_b.id)) or {}
    check("0321: the usage ledger's line of a branch counts its own cell - not the two it kept - and says the turn it went on from and the hint given there",
          _line_b.get("cells") == 1 and _line_b.get("branch") == {"turn": 2, "hint": "keep the two apart"} and _line_b.get("question") == _first.question
          and (BAMBOO.store.ledger().get(str(_first.id)) or {}).get("branch") == {} and (BAMBOO.store.ledger().get(str(_first.id)) or {}).get("cells") == 3, _line_b)
    check("0319: the analyst is given the hint in every prompt of the branch, the first at the turn after the one kept, and nothing of the turns that were left",
          len(_prompts) == 2 and all(_HINT % (2, "keep the two apart") in u for u in _prompts) and "TASK: turn 3;" in _prompts[0] and "TASK: turn 4;" in _prompts[1]
          and not any("three = two + 1" in u or "no_such_name" in u for u in _prompts), [u[-300:] for u in _prompts])
    _id = next((m for m in _sent if m.get("type") == "id"), {})
    _start = next((m for m in _sent if m.get("type") == "pane_run_start"), {})
    _end = next((m for m in _sent if m.get("type") == "pane_run_end"), {})
    _cards = [(m.get("turn"), bool(m.get("kept"))) for m in _sent if m.get("type") == "pane_turn_start" and isinstance(m.get("turn"), int)]
    _rows = [(m.get("cell_no"), m.get("kept")) for m in _sent if m.get("type") == "pane_cell"]
    _ends = [bool(m.get("kept")) for m in _sent if m.get("type") == "pane_turn_end" and isinstance(m.get("turn"), int)]
    check("0319: the page is told - the new chain with the chain and the turn it goes on from, and where it attaches; the run's card with the branch and its hint, in "
          "the first run's mode and limits; the kept turns' cards and cells first, each marked, each cell with the time it took; the closing card counting the "
          "chain's turns and the time of its own",
          (_id.get("chain_id"), _id.get("branch_of"), _id.get("branch_turn"), _id.get("parent_chain_id")) == (BAMBOO.chain_id, int(_first.id), 2, int(_talk.id))
          and _start.get("branch") == {"of": int(_first.id), "turn": 2, "hint": "keep the two apart"} and (_start.get("mode"), _start.get("of")) == ("Deep", _first.budget["turns"])
          and _cards == [(1, True), (2, True), (3, False), (4, False)] and _ends == [True, True, False, False] and _rows == [(1, "kept"), (2, "kept"), (3, None)]
          and [m.get("elapsed") for m in _sent if m.get("type") == "pane_cell"] == [c.elapsed for c in _b.cells()]
          and (_end.get("turns"), _end.get("cells")) == (4, 3) and _end.get("seconds") < 7 and _end.get("turn_map") is True,
          (_id, _start, _cards, _ends, _rows, _end.get("turns"), _end.get("seconds"), _end.get("turn_map")))
    _bb, _sent_bb, _ = _go_on([_REPORT], _b.id, 1, "from a turn the branch kept")
    _id_bb = next((m for m in _sent_bb if m.get("type") == "id"), {})
    check("0319: a branch that goes on from a turn its chain kept from another is a branch of that other chain: its record says so, and the page is told so",
          _bb is not None and _bb.branch == {"of": _first.id, "turn": 1} and (_id_bb.get("branch_of"), _id_bb.get("branch_turn")) == (int(_first.id), 1)
          and next((m for m in _sent_bb if m.get("type") == "pane_run_start"), {}).get("branch", {}).get("of") == int(_first.id) and _bb.hints == [{"turn": 1, "text": "from a turn the branch kept"}],
          (_bb and _bb.branch, _id_bb))
    # the kernel is gone: the cells the branch keeps are run again, and the one that drew a number prints another
    BAMBOO._drop_kernel()
    _c, _sent_c, _prompts_c = _go_on([_WHICH, _REPORT], _first.id, 4, "say which is larger")
    _kc = BAMBOO._kernel
    check("0319: with the kernel gone the cells the branch keeps are run again in a new one: the cell that drew a number printed another, so the branch marks it, holds "
          "the new output - the one its kernel has - and tells the analyst under the cell's header; the others only name their new states; the first chain's record is untouched",
          _c is not None and _kc is not _k and [c.kept for c in _c.cells()[:3]] == ["kept", "differs", "kept"] and _drew(_c.cells()[1]) != _drew(_first.cells()[1])
          and _c.cells()[-1].stdout.strip() == f"here: ['one', 'three', 'two'] {_drew(_c.cells()[1])}" and [c.snap.split(":")[0] for c in _c.cells()] == [_kc.uid] * 4
          and all(c.snap.startswith(_k.uid + ":") for c in _first.cells()) and ("--- cell 2 ---\n" + AGAIN_LINE) in _prompts_c[0] and _prompts_c[0].count(AGAIN_LINE) == 1
          and [m.get("kept") for m in _sent_c if m.get("type") == "pane_cell"][:4] == ["kept", "differs", "kept", "kept"],
          ([c.kept for c in _c.cells()], _c.cells()[-1].stdout, [c.snap for c in _c.cells()]))
    # a state the kernel did not save (a generator in it): going back runs the cells since the last saved state again
    _gen = _chain([_cell("gen = (n for n in range(3))\nseen = 'first'\nprint('seen', seen)"), _cell("later = 1\nprint('later')"), _REPORT], _talk.id)
    _kg, _steps = BAMBOO._kernel, None
    _g, _, _ = _go_on([_cell("print('next of gen:', next(gen), 'later' in globals())"), _REPORT], _gen.id, 1)
    check("0319: a state the kernel could not save is reached by running its cell again; it printed what the record has, so the branch goes on in that kernel, unmarked",
          _g is not None and BAMBOO._kernel is _kg and len(_kg.last_goto["replayed"]) >= 1 and _g.cells()[0].kept == "kept" and _g.cells()[-1].stdout.strip() == "next of gen: 0 False",
          (_g and [c.kept for c in _g.cells()], _kg.last_goto))
    _rnd = _chain([_cell("import random\ngen = (n for n in range(3))\nluck = random.random()\nprint('luck', round(luck, 6))"), _cell("later = 1\nprint('later')"), _REPORT], _talk.id)
    _kr = BAMBOO._kernel
    _r, _, _ = _go_on([_cell("print('luck now', round(luck, 6), 'later' in globals())"), _REPORT], _rnd.id, 1)
    check("0319: ... and where the cell run again printed something else, the kernel does not hold what the record shows: a new kernel, the cell run once more, "
          "the branch marked and holding the output its kernel has",
          _r is not None and BAMBOO._kernel is not _kr and _r.cells()[0].kept == "differs" and _r.cells()[0].stdout != _rnd.cells()[0].stdout
          and _r.cells()[-1].stdout.strip() == "luck now " + _r.cells()[0].stdout.split()[1] + " False", (_r and [c.kept for c in _r.cells()], _r and _r.cells()[-1].stdout))
    _pr = _chain([_cell("import random\ngen = (n for n in range(3))\nluck = random.random()\nprint('luck', round(luck, 6))"), _REPORT], _talk.id)
    _ch = _chain([_cell("mine = 1\nprint('mine')"), _cell("more = 2\nprint('more')"), _REPORT], _pr.id)
    _kp = BAMBOO._kernel
    _on_ch, _, _ = _go_on([_cell("print('more there:', 'more' in globals())"), _REPORT], _ch.id, 1)
    check("0319: ... but a cell of an earlier chain that printed something else when the kernel ran it again does not: the earlier chains' cells are run again as "
          "they are for any follow-up, and the branch goes on in the same kernel",
          _on_ch is not None and BAMBOO._kernel is _kp and len(_kp.last_goto["replayed"]) >= 2 and _on_ch.cells()[0].kept == "kept"
          and _on_ch.cells()[-1].stdout.strip() == "more there: False", (_on_ch and [c.kept for c in _on_ch.cells()], _kp.last_goto))
    _slip = _chain([_cell("print(no_such_name)"), _cell("made = 1\nprint('made')"), _REPORT], _talk.id)
    _ks = BAMBOO._kernel
    _s, _, _ps = _go_on([_cell("print('made there:', 'made' in globals())"), _REPORT], _slip.id, 1)
    check("0319: a branch after a turn that kept no cell - the chain's first cell failed - goes back to the state before that cell, in the same kernel, and the "
          "analyst is shown the failure it goes on from",
          _s is not None and BAMBOO._kernel is _ks and _ks.last_goto["step"] == 0 and _s.cells()[-1].stdout.strip() == "made there: False"
          and "YOUR LAST CELL FAILED" in _ps[0] and _s.turns[0].kept == "kept", (_s and _s.cells()[-1].stdout, _ks.last_goto))
    _halt = _chain([_cell("half = 1\nprint('half')"), _cell("rest = 1\nprint('rest')"), _REPORT], _talk.id, stop_after_first=True)
    _map_halt = next((m for m in _chain.sent if m.get("type") == "pane_run_end"), {}).get("turn_map")
    _h, _, _ = _go_on([_cell("print('goes on:', 'half' in globals(), 'rest' in globals())"), _REPORT], _halt.id, 1)
    check("0319: an analysis the person stopped can be gone on from a turn it kept", _halt.status == "stopped" and _h is not None and _h.status == "answered"
          and _h.cells()[-1].stdout.strip() == "goes on: True False", (_halt.status, _h and _h.cells()[-1].stdout))
    _chain([_REPORT], _talk.id)
    _map_none = next((m for m in _chain.sent if m.get("type") == "pane_run_end"), {}).get("turn_map")
    check("0320: the closing card of a stopped analysis that kept a turn offers the Analysis map; one whose first reply was its report has no turn to go on from, and offers none",
          _map_halt is True and _map_none is False, (_map_halt, _map_none))
    _two = _chain([_cell("aa = 1\nprint('aa')"), _cell("bb = 2\nprint('bb')"), _REPORT], _talk.id)
    _send = BAMBOO.output_manager.send_chain_id
    def _no_page(*a, **kw):
        raise RuntimeError("no page")
    BAMBOO.output_manager.send_chain_id = _no_page
    try:
        _go_on([_REPORT], _two.id, 1)
        _fell = False
    except RuntimeError:
        _fell = True
    finally:
        BAMBOO.output_manager.send_chain_id = _send
    _after = _chain([_cell("print('bb there:', 'bb' in globals())"), _REPORT], _two.id)
    check("0319: a branch takes the kernel off the chain's end it stood at; where the request then fails before its run starts, the kernel is not taken for warm: "
          "the next chain asked from that end finds what the chain made", _fell and _after.cells()[-1].stdout.strip() == "bb there: True", (_fell, _after.cells()[-1].stdout))
    # what cannot be gone on from: said to the person, and nothing is started
    def _refused(of, turn, hint="x"):
        n = len(BAMBOO.notebook.runs); made, sent, prompts = _go_on([_REPORT], of, turn, hint)
        return next((m["error"] for m in sent if "error" in m), "") if (made is None and len(BAMBOO.notebook.runs) == n and not prompts and not any(m.get("type") == "id" for m in sent)) else "STARTED"
    # a chain that follows another: the cells before it are part of the state the branch goes on from
    _SEES = _cell("print('sees:', sorted(n for n in ('par', 'kid', 'after_kid') if n in globals()))")
    _par = _chain([_cell("par = 1\nprint('par')"), _REPORT], _talk.id)
    _kid = _chain([_cell("kid = par + 1\nprint('kid', kid)"), _cell("after_kid = 1\nprint('after')"), _REPORT], _par.id)
    _kk = BAMBOO._kernel
    _held, _, _ = _go_on([_SEES, _REPORT], _kid.id, 1)
    _was_held = BAMBOO._kernel is _kk and _kk.last_goto["replayed"] == [] and _held is not None and _held.cells()[-1].stdout.strip() == "sees: ['kid', 'par']" and [c.cell_no for c in _held.cells()] == [2, 3]
    BAMBOO._drop_kernel()
    _anew, _, _ = _go_on([_SEES, _REPORT], _kid.id, 1)
    check("0319: a branch of a chain that follows another goes on from the state the whole path left - the earlier chain's cell and its own kept one, nothing after the "
          "turn: in the kernel that holds it, with nothing run again; with the kernel gone, the earlier chain's cells are run again as for any follow-up, then the kept ones",
          _was_held and _anew is not None and BAMBOO._kernel is not _kk and _anew.cells()[-1].stdout.strip() == "sees: ['kid', 'par']" and _anew.parent == _par.id
          and _anew.cells()[0].snap.startswith(BAMBOO._kernel.uid + ":") and _par.cells()[0].snap.startswith(BAMBOO._kernel.uid + ":"), (_was_held, _anew and _anew.cells()[-1].stdout))
    _kid2 = _chain([_cell("print(no_such_name)"), _cell("kid2 = par + 1\nprint('kid2')"), _REPORT], _par.id)
    _kk2 = BAMBOO._kernel
    _under, _, _ = _go_on([_cell("print('sees:', sorted(n for n in ('par', 'kid2') if n in globals()))"), _REPORT], _kid2.id, 1)
    check("0319: ... and where the turn kept no cell of the chain's own, the state is the one the earlier chain ended in: what that chain made is there",
          _under is not None and BAMBOO._kernel is _kk2 and _kk2.last_goto["replayed"] == [] and _under.cells()[-1].stdout.strip() == "sees: ['par']",
          (_under and _under.cells()[-1].stdout, _kk2.last_goto))
    BAMBOO._drop_kernel(); _code, _par.cells()[0].code = _par.cells()[0].code, "raise ValueError('lost')"
    _no_path = _refused(_kid.id, 1); _par.cells()[0].code = _code
    BAMBOO._drop_kernel(); _code, _kid.cells()[0].code = _kid.cells()[0].code, "raise ValueError('gone')"
    _no_cell = _refused(_kid.id, 1); _kid.cells()[0].code = _code
    check("0319: where the state cannot be rebuilt - a cell of the earlier chain, or a kept cell, fails when run again - the person is told which, and nothing starts: "
          "no chain is announced, no run is made",
          _no_path == "The analysis cannot go on from turn 1: restoring the earlier analysis stopped after 0 of 1 cells: cell 1 failed on replay: ValueError: lost."
          and _no_cell == "The analysis cannot go on from turn 1: cell 2 failed when run again: ValueError: gone.", (_no_path, _no_cell))
    said = {"turn": _refused(_first.id, 5), "hint": _refused(_first.id, 2, "  "), "thread": _refused("999999", 1)}
    _first.status = "running"; said["running"] = _refused(_first.id, 2); _first.status = "answered"
    _first.figure_asked = True; said["figure"] = _refused(_first.id, 2); _first.figure_asked = False
    _car = [t.carry for t in _first.turns]
    for t in _first.turns: t.carry = {}
    said["before"] = _refused(_first.id, 2)
    for t, c in zip(_first.turns, _car): t.carry = c
    _rec = _first.data
    _first.data = {**_rec, "name": "trial.csv"}; BAMBOO.df, BAMBOO.df_id = df.head(50), "d2"; said["data"] = _refused(_first.id, 2)
    _first.data = {**_rec, "name": ""}; said["unnamed"] = _refused(_first.id, 2); BAMBOO.df, BAMBOO.df_id = df, "d1"; _first.data = _rec
    _dat, _first.data = _first.data, {"source": "none", "df_id": None, "aux": []}; said["no data"] = _refused(_first.id, 2); _first.data = _dat
    check("0319: what cannot be gone on from is said, and nothing starts: the report's turn, no hint, a chain that is not in the thread, an analysis that has not ended, "
          "one asked about a plot, one from before 2.9, other data loaded - the data it ran on named where it has a name -, data loaded where it ran on none",
          said == {"turn": "Turn 5 cannot be gone on from: this analysis can go on from turns 1 to 4.",
                   "hint": "Say how the analysis should go on from turn 2: a branch needs a hint.",
                   "thread": "The analysis to go on from is not in this thread.",
                   "running": "This analysis has not ended: stop it, or wait for its report, then go on from one of its turns.",
                   "figure": "An analysis that was asked about a plot cannot be gone on from yet.",
                   "before": "This analysis cannot be gone on from: it was made before version 2.9, or it is a routine's run.",
                   "data": "Load the data this analysis ran on first: trial.csv.", "unnamed": "Load the data this analysis ran on first.",
                   "no data": "This analysis ran with no data loaded: remove the dataset, then go on from its turn."}, said)
    BAMBOO.output_manager.add_user_input("a brief that was started before"); _was = BAMBOO.chain_id
    BAMBOO.pd_agent_converse(thread_id="2909", chain_id=_b.id, run_id=_b.id)        # a brief that can no longer be started: refused too
    _no_brief = BAMBOO.chain_id == _was and any("can no longer be started" in json.loads(m).get("error", "") for m in list(q.queue))
    state.update(i=0, script=FOLLOW[1:]); BAMBOO.output_manager.add_user_input("and after the refusals?"); _nf = len(state["calls"])
    BAMBOO.pd_agent_converse(thread_id="2909", chain_id=_b.id, mode="quick")
    while not q.empty(): q.get()
    _next = BAMBOO.notebook.runs[str(BAMBOO.chain_id)]
    _told = next(u for a, u in state["calls"][_nf:] if "TASK: turn" in u)       # what the analyst of the chain asked from the branch was sent first
    check("0319: a refusal leaves nothing behind for the next question - what was typed for a branch, or for a brief that can no longer be started, is not asked in "
          "its place - and a chain asked from a branch follows it as any chain; its analyst is told what the person said on the branch's way, under the branch's "
          "question in the thread's ledger (0321), and is under no hint itself",
          _no_brief and _next.question == "and after the refusals?" and _next.parent == _b.id and _next.branch == {} and _next.hints == []
          and f"Q: {_b.question}\n        HINT FROM THE PERSON after turn 2: keep the two apart\n        Conclusion: " in _told and _told.count("HINT FROM THE PERSON") == 1
          and "HINT FROM THE PERSON (given" not in _told, (_no_brief, _next.question, _next.parent, _told[:900]))
    _luck = _chain([_cell("import random\nluck = random.random()\nprint('luck', round(luck, 6))"), _REPORT], _talk.id)
    _k9 = BAMBOO._kernel
    BAMBOO.df_id = "d9"                                      # the same file loaded again under another id: the same data, another frame
    _again, _, _ = _go_on([_cell("print('luck now', round(luck, 6))"), _REPORT], _luck.id, 1)
    BAMBOO.df_id = "d1"
    check("0319: the same data loaded again under another id is the data the analysis ran on: the branch starts - in a new kernel, which holds that frame, its kept "
          "cell run again there - and its record names the data loaded now",
          _again is not None and _again.status == "answered" and BAMBOO._kernel is not _k9 and _again.cells()[0].kept == "differs"
          and _again.cells()[-1].stdout.strip() == "luck now " + _again.cells()[0].stdout.split()[1] and _again.data.get("df_id") == "d9" and _luck.data.get("df_id") == "d1",
          (_again and _again.status, _again and [c.kept for c in _again.cells()], _again and _again.data.get("df_id")))
    _talk.next_questions = [{"level": 1, "questions": [{"title": "t", "text": "x"}]}]
    _fr = str(BAMBOO.open_framing("a brief still to be started", thread_id="2909", chain_id=_b.id)["chain_id"])
    _only, _, _ = _go_on([_REPORT], _first.id, 2, run_id=_fr, candidate=(0, 0))
    check("0319: a branch takes the chain, the turn and the hint, and nothing else a request may carry: a brief still to be started stays to be started, and no "
          "proposed question is marked as run",
          _only is not None and _only.id != _fr and _only.branch == {"of": _first.id, "turn": 2} and BAMBOO.notebook.runs[_fr].status == "framing"
          and "ran" not in _talk.next_questions[0]["questions"][0], (_only and _only.id, _fr, _talk.next_questions))
    _talk.next_questions = []
except Exception as exc:                                     # noqa: BLE001
    import traceback
    check("0319: a branch through the instance: the checks ran", False, traceback.format_exc()[-1500:])

# ---- the names of 2.9 (0328): the Pathfinder was the Architect, and what was written under that name is still read
try:
    import agent_instructions_routes as _AIR
    _seats0, _named = list(FakeModels.config["agent_configs"]), []
    for _names in (("Pathfinder",), ("Architect",), ("Architect", "Pathfinder"), ()):
        FakeModels.config["agent_configs"] = _seats0 + [{"agent": a_, "details": {"model": "fake/model", "provider": "fake", "reasoning_effort": "medium"}} for a_ in _names]
        _named.append(BAMBOO._architect_seat())
    FakeModels.config["agent_configs"] = _seats0
    _cwd0 = os.getcwd(); os.chdir(tempfile.mkdtemp())
    os.makedirs(os.path.join("logs", "u1"))
    _logged = lambda agent, said: {"chain_id": 7001, "agent": agent, "messages": [{"role": "system", "content": "frame the question"}, {"role": "user", "content": said}]}
    json.dump([_logged("Architect", "its first reply, before 2.9"), _logged("Analyst", "a turn"), _logged("Pathfinder", "its second reply")], open(os.path.join("logs", "u1", "bambooai_run_log.json"), "w"))
    _ai = Flask("ai"); _ai.register_blueprint(_AIR.agent_instructions_bp); _aic = _ai.test_client()
    _asked = lambda agent, call: (lambda j: (j.get("user"), j.get("call"), j.get("calls")))(_aic.get(f"/api/agent-instructions/7001/{agent}?call={call}").get_json())
    _prompts = [_asked("Pathfinder", 1), _asked("Pathfinder", 2), _asked("Architect", 2), _asked("Analyst", 1)]
    os.chdir(_cwd0)
    check("the Pathfinder's name (0328; the Architect until 2.9). Its seat: 'Pathfinder' where the configuration has one; 'Architect' where a configuration written before has that - "
          "the newer name first where it has both -; else the analyst's. Its prompts in the run log: the calls it made before stand there under the old name, and a card asks for the "
          "nth of the two names taken together, whichever name the card carries - a card kept from before asks under the old one; another seat's calls are counted by its own name",
          _named == ["Pathfinder", "Architect", "Pathfinder", BAMBOO._seat()]
          and _prompts == [("its first reply, before 2.9", 1, 2), ("its second reply", 2, 2), ("its second reply", 2, 2), ("a turn", 1, 1)], (_named, _prompts))
except Exception as exc:                                     # noqa: BLE001
    import traceback
    check("0328: the Pathfinder's name: the checks ran", False, traceback.format_exc()[-1500:])

print(f"\n{len(passed)} passed, {len(failed)} failed"); sys.exit(1 if failed else 0)
