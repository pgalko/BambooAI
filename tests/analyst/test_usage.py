"""The usage records (2026-10-31, docs/USAGE_DESIGN.md): each model call's row keeps the cache split, what the cache saved
and the fees inside the cost - written by the logger, kept by the local store and by the stack's Supabase stand-in the
way the hosted function keeps them (docs/sql/usage_cache_fields.sql); rows from before read as not recorded.

    python3 tests/analyst/test_usage.py
"""
import json
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path[:0] = [os.path.dirname(os.path.abspath(__file__)), ROOT, os.path.join(ROOT, "web_app"), os.path.join(ROOT, "tools", "stack")]
import _stubs  # noqa: F401,E402
os.environ["AUTH_MODE"] = "single"
os.environ["BAMBOO_DATA_DIR"] = tempfile.mkdtemp(prefix="bamboo_usage_")
WORK = tempfile.mkdtemp(prefix="bamboo_usage_work_")
os.chdir(WORK)                                                   # the run log goes under logs/<user>/ of the working folder

passed, failed = [], []


def check(name, cond, detail=""):
    (passed if cond else failed).append(name)
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:600]}"))


from bambooai.db import local_store                           # noqa: E402

FIELDS = ("cached_tokens", "cache_write_tokens", "cache_savings", "search_fee", "image_fee")
U, A = "coach", "local|coach"

# ---- the local store: a fresh file, the writer, a file from before ----
st = local_store.LocalStore(os.path.join(os.environ["BAMBOO_DATA_DIR"], "fresh.sqlite"), local_sub=A, bamboo_user_id=U)
cols = st.columns("usage")
check("a fresh file's usage table carries the five columns", all(c in cols for c in FIELDS), cols)
full = {"bamboo_user_id": U, "chain_id": "c1", "agent": "Analyst", "timestamp": "2026-10-31 00:10:00", "model": "m", "prompt_tokens": 1000, "completion_tokens": 100,
        "elapsed_time": 1.5, "tokens_per_second": 66.7, "cost": 0.013, "cached_tokens": 600, "cache_write_tokens": 100, "cache_savings": 0.001545, "search_fee": 0.01, "image_fee": 0.0}
r1 = st.rpc("insert_usage_with_chain", {"p_usage_data": full, "p_thread_id": "t1"}).execute().data
old_payload = {k: v for k, v in full.items() if k not in FIELDS}
r2 = st.rpc("insert_usage_with_chain", {"p_usage_data": dict(old_payload, timestamp="2026-10-31 00:11:00"), "p_thread_id": "t1"}).execute().data
rows = st.table("usage").select("*").eq("bamboo_user_id", U).order("id").execute().data
check("the writer keeps the five fields; a payload without them (an older app) leaves them NULL - not recorded, never zero; the thread and the chain made once",
      r1.get("success") and r2.get("success") and [rows[0][k] for k in FIELDS] == [600, 100, 0.001545, 0.01, 0.0] and all(rows[1][k] is None for k in FIELDS)
      and len(st.table("threads").select("*").execute().data) == 1 and len(st.table("chains").select("*").execute().data) == 1, (r1, r2, rows))

OLD = """CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bamboo_user_id TEXT NOT NULL, agent TEXT, chain_id TEXT, timestamp TEXT, model TEXT,
    prompt_tokens INTEGER, completion_tokens INTEGER, elapsed_time REAL, tokens_per_second REAL, cost REAL,
    created_at TEXT DEFAULT (datetime('now')),
    compute_tier TEXT DEFAULT 'local', query_cost REAL DEFAULT 0, charges_processed INTEGER DEFAULT 1);"""
old_file = os.path.join(os.environ["BAMBOO_DATA_DIR"], "old.sqlite")
c = sqlite3.connect(old_file); c.executescript(OLD)
c.execute("INSERT INTO usage (bamboo_user_id, agent, chain_id, timestamp, model, prompt_tokens, completion_tokens, elapsed_time, tokens_per_second, cost) VALUES (?,?,?,?,?,?,?,?,?,?)",
          (U, "Analyst", "c0", "2026-10-01 10:00:00", "m", 500, 50, 1.0, 50.0, 0.004)); c.commit(); c.close()
st2 = local_store.LocalStore(old_file, local_sub=A, bamboo_user_id=U)
old_rows = st2.table("usage").select("*").eq("bamboo_user_id", U).execute().data
st2.rpc("insert_usage_with_chain", {"p_usage_data": full, "p_thread_id": "t1"}).execute()
new_rows = st2.table("usage").select("*").eq("bamboo_user_id", U).order("id").execute().data
st3 = local_store.LocalStore(old_file, local_sub=A, bamboo_user_id=U)
check("a file from before opens with the five columns added, its rows NULL there (not recorded); a new row carries them; opening again changes nothing",
      all(c_ in st2.columns("usage") for c_ in FIELDS) and all(old_rows[0][k] is None for k in FIELDS) and new_rows[1]["cached_tokens"] == 600 and st3.columns("usage") == st2.columns("usage"), (old_rows, st2.columns("usage")))

# ---- the stack's stand-in: the hosted function's shape ----
import fake_supabase                                          # noqa: E402
fc = fake_supabase.create_client("http://supabase.local", "local")
r3 = fc.rpc("insert_usage_with_chain", {"p_usage_data": full, "p_thread_id": "t9"}).execute().data
r4 = fc.rpc("insert_usage_with_chain", {"p_usage_data": old_payload, "p_thread_id": "t9"}).execute().data
r5 = fc.rpc("insert_usage_with_chain", {"p_usage_data": {"agent": "x"}, "p_thread_id": "t9"}).execute().data
frows = [r for r in fake_supabase.TABLES["usage"] if r.get("chain_id") == "c1"]
check("the stand-in answers as the hosted function does: success with the ids, the thread and the chain made once, the row with the five fields (NULL for an older payload); a payload without the required fields is refused",
      r3.get("success") and r3.get("usage_id") and r4.get("success") and r5 == {"success": False, "error": "missing_required_fields"}
      and len(frows) == 2 and [frows[0][k] for k in FIELDS] == [600, 100, 0.001545, 0.01, 0.0] and all(frows[1][k] is None for k in FIELDS)
      and sum(1 for t in fake_supabase.TABLES["threads"] if t["thread_id"] == "t9") == 1 and sum(1 for ch in fake_supabase.TABLES["chains"] if ch["chain_id"] == "c1") == 1, (r3, r4, r5, frows))

# ---- the logger: what a call computes reaches the row ----
from bambooai.log_manager import LogAndCallManager            # noqa: E402


class _Capture:
    def __init__(self): self.calls = []
    def is_available(self): return True
    def check_grounding_search_quota(self, n): return None     # no quota record: the fee is charged
    def insert_usage_with_chain(self, data, thread_id): self.calls.append((dict(data), thread_id)); return True


costs = {"m": {"prompt_tokens": 0.003, "completion_tokens": 0.015, "grounding_search_request": 0.01}}      # per 1,000 tokens, as the configuration has them
lacm = LogAndCallManager(costs, user_id=U, thread_id="t1")
cap = _Capture(); lacm.supabase_client = cap
messages = [{"role": "system", "content": '__billing_meta__: {"search_billed": 1, "images_generated": 0}'}, {"role": "user", "content": "q"}]
lacm.write_to_log("Google Search Executor", "c7", "2026-10-31 00:20:00", "m", messages, "reply", 1000, 100, 1100, 2.0, 50.0, cached_tokens=600, cache_write_tokens=100)
payload = cap.calls[-1][0] if cap.calls else {}
# uncached 300 at 0.003, cached 600 at a tenth, written 100 at 1.25x, 100 out at 0.015 - per thousand; the search fee on top
expect_cost = (300 * 0.003 + 600 * 0.0003 + 100 * 0.00375 + 100 * 0.015) / 1000 + 0.01
expect_savings = (700 * 0.003) / 1000 - (600 * 0.0003 + 100 * 0.00375) / 1000
check("the logger's row carries the cache split, the savings and the fees as the call computed them: 600 cached, 100 written, the saving against an uncached prompt, the search fee, no image fee; the cost is the tokens' three tranches plus the fee",
      cap.calls and cap.calls[-1][1] == "t1" and payload.get("cached_tokens") == 600 and payload.get("cache_write_tokens") == 100 and abs(payload.get("cache_savings", 0) - expect_savings) < 1e-6
      and payload.get("search_fee") == 0.01 and payload.get("image_fee") == 0.0 and abs(payload.get("cost", 0) - round(expect_cost, 4)) < 1e-6, (payload, expect_cost, expect_savings))
lacm.write_to_log("Analyst", "c7", "2026-10-31 00:21:00", "m", [{"role": "user", "content": "q"}], "reply", 1000, 100, 1100, 2.0, 50.0)
payload2 = cap.calls[-1][0]
check("a call with nothing cached and no fee writes zeros, not NULLs (recorded: nothing cached)", payload2.get("cached_tokens") == 0 and payload2.get("cache_write_tokens") == 0 and payload2.get("cache_savings") == 0.0 and payload2.get("search_fee") == 0.0 and payload2.get("image_fee") == 0.0, payload2)
runlog = json.load(open(os.path.join(WORK, "logs", U, "bambooai_run_log.json")))
check("the JSON run log still carries the same facts per call (the row is the log's subset, not a second account)", runlog[0]["cached_tokens"] == 600 and runlog[0]["grounding_fee"] == 0.01 and abs(runlog[0]["cache_savings"] - expect_savings) < 1e-6, runlog[0].keys())

# ---- the hosted migration's text: the five columns and the function writing them, as the dump will show ----
sql = open(os.path.join(ROOT, "docs", "sql", "usage_cache_fields.sql"), encoding="utf-8").read()
check("docs/sql/usage_cache_fields.sql adds the five columns (if not exists) and replaces insert_usage_with_chain to write them from the payload",
      all(f"add column if not exists {c_}" in sql for c_ in FIELDS) and "create or replace function public.insert_usage_with_chain" in sql
      and all(f"(p_usage_data->>'{c_}')" in sql for c_ in FIELDS) and sql.count("RETURNING * INTO v_usage_record") == 1)

# ---- the route (web_app/usage_routes.py, step 2): the dialog's answer over the local store and a thread store ----
import types                                                  # noqa: E402
from datetime import datetime, timedelta                      # noqa: E402
sys.path.insert(0, os.path.join(ROOT, "web_app"))
STORAGE = os.path.join(WORK, "storage", U)
_fa = types.ModuleType("auth"); _fa.requires_auth = lambda f: f; _fa.get_current_user_id = lambda: A; sys.modules["auth"] = _fa
rt_store = local_store.LocalStore(os.path.join(os.environ["BAMBOO_DATA_DIR"], "route.sqlite"), local_sub=A, bamboo_user_id=U)
_fs = types.ModuleType("auth.supabase_client"); _fs.get_service_client = lambda: rt_store; _fs.supabase_configured = lambda: False
_fs.get_user_subscription = lambda a: {"ok": True, "data": {"compute_tier": "local"}}; sys.modules["auth.supabase_client"] = _fs
_fapp = types.ModuleType("app"); _fapp.user_path = lambda root, *p: os.path.join(WORK, root, U, *p); _fapp.get_user_id = lambda: U; sys.modules["app"] = _fapp
import usage_routes as UR                                      # noqa: E402
NOW = datetime(2026, 10, 31, 12, 0, 0)                        # UTC; the page is at UTC+10 (tz=600): local 22:00 on the 31st
UR._utcnow = lambda: NOW
TZ = 600


def write_calls(chain, thread, when, calls):
    """Rows for one chain: calls = [(seat, model, in, cached, written, out, elapsed, cost, savings, search_fee)]; when = local time of the first, a minute apart."""
    for i, (seat, model, tin, cached, written, tout, el, cost, sav, fee) in enumerate(calls):
        t = (when - timedelta(minutes=TZ) + timedelta(minutes=i)).strftime("%Y-%m-%d %H:%M:%S")
        p = {"bamboo_user_id": U, "chain_id": chain, "agent": seat, "timestamp": t, "model": model, "prompt_tokens": tin, "completion_tokens": tout, "elapsed_time": el,
             "tokens_per_second": round(tout / el, 1) if el else 0, "cost": cost}
        if cached is not None:
            p.update({"cached_tokens": cached, "cache_write_tokens": written, "cache_savings": sav, "search_fee": fee, "image_fee": 0.0})
        r = rt_store.rpc("insert_usage_with_chain", {"p_usage_data": p, "p_thread_id": thread}).execute().data
        assert r.get("success"), r


L = lambda d, h=10, m=0: datetime(2026, 10, d, h, m)            # local time
# this period (30 days to Oct 31 local): three analyses on t1, an ideas run, a Save-as-routine proposal; a row from before 0255 (no cache fields)
write_calls("c1", "t1", L(18, 14), [("Analyst", "m-big", 10000, 6000, 1000, 500, 10.0, 0.05, 0.012, 0.0), ("Analyst", "m-big", 12000, 9000, 0, 400, 8.0, 0.04, 0.02, 0.0),
                                    ("Reviewer", "m-big", 8000, 4000, 0, 200, 5.0, 0.03, 0.009, 0.0), ("Google Search Executor", "m-small", 2000, 0, 0, 100, 2.0, 0.015, 0.0, 0.01)])
write_calls("c2", "t1", L(18, 16), [("Analyst", "m-big", 9000, 3000, 0, 300, 6.0, 0.03, 0.006, 0.0), ("Analyst", "m-big", 9500, 5000, 0, 100, 3.0, 0.02, 0.01, 0.0)])
write_calls("c3", "t1", L(20, 9), [("Analyst", "m-big", 7000, None, None, 300, 4.0, 0.025, None, None), ("Rewriter", "m-small", 3000, None, None, 400, 2.0, 0.004, None, None)])
write_calls("c4", "t1", L(21, 11), [("Analyst", "m-big", 4000, 1000, 0, 600, 5.0, 0.02, 0.002, 0.0)])                     # the ideas run
write_calls("c5", "t1", L(22, 12), [("Promoter", "m-big", 15000, 0, 0, 2000, 20.0, 0.08, 0.0, 0.0)])                       # Save as routine's call
# two analyses whose thread file is gone (not saved as a favourite, discarded at a sign-in): one with the ledger's line the host
# wrote when it ended, one from before the ledger existed
write_calls("c6", "t9", L(24, 10), [("Analyst", "m-big", 5000, 2000, 0, 300, 4.0, 0.02, 0.004, 0.0), ("Rewriter", "m-small", 2000, 0, 0, 300, 2.0, 0.003, 0.0, 0.0)])
write_calls("c7", "t9", L(24, 11), [("Analyst", "m-big", 5000, 0, 0, 300, 4.0, 0.02, 0.0, 0.0)])
# the period before (Sep 2 - Oct 1 local): two chains; and one on Sep 1 before both periods
write_calls("c0", "t0", L(1, 8) - timedelta(days=28), [("Analyst", "m-big", 5000, 2000, 0, 300, 4.0, 0.03, 0.004, 0.0), ("Reviewer", "m-big", 3000, 0, 0, 100, 2.0, 0.01, 0.0, 0.0)])
write_calls("cx", "t0", datetime(2026, 9, 20, 10), [("Analyst", "m-big", 5000, 0, 0, 300, 4.0, 0.02, 0.0, 0.0)])
write_calls("cold", "t0", datetime(2026, 9, 1, 10), [("Analyst", "m-big", 5000, 0, 0, 300, 4.0, 0.99, 0.0, 0.0)])
# the thread store: what the chains were
from analyst.notebook import Notebook, NotebookStore, Turn    # noqa: E402
nbs = NotebookStore(STORAGE)
nb = Notebook("t1")
r1 = nb.new_run("Does the second regime raise the yield?", run_id="c1"); r1.mode, r1.status, r1.replay_status, r1.title = "Deep", "answered", "reproduced", "The second regime raises the yield by 12%"
r1.turns = [Turn(kind="cell", cell_no=1, code="a", elapsed=1.0, figures=[{"x": 1}]), Turn(kind="search", stdout="s"), Turn(kind="cell", cell_no=2, code="b", elapsed=2.0), Turn(kind="report", text="r")]
r1.created = (L(18, 14) - timedelta(minutes=TZ) - datetime(1970, 1, 1)).total_seconds()
for i, t in enumerate(r1.turns): t.created = r1.created + 60 * (i + 1)
r2 = nb.new_run("And the third?", parent="c1", run_id="c2"); r2.mode, r2.status = "Quick", "failed"
r2.turns = [Turn(kind="cell", cell_no=3, code="c", elapsed=1.0), Turn(kind="cell", cell_no=4, code="d", error="boom")]
r3 = nb.new_run("How many rows?", run_id="c3"); r3.mode, r3.status = "Quick", "answered"; r3.turns = [Turn(kind="cell", cell_no=5, code="e"), Turn(kind="report", text="r")]
r4 = nb.new_run("Ideas", run_id="c4"); r4.mode, r4.status = "Ideas", "answered"
nbs.save(nb)
nb9 = Notebook("t9"); r6 = nb9.new_run("Which weeks carried the most load?", run_id="c6"); r6.mode, r6.status, r6.replay_status = "Adaptive", "answered", "differed"
r6.turns = [Turn(kind="cell", cell_no=1, code="a"), Turn(kind="report", text="r")]
nbs.record(nb9, r6)                                            # the line the host writes at the run's end; the thread file itself never saved here
from flask import Flask                                        # noqa: E402
_w = Flask("t"); _w.secret_key = "t"; _w.register_blueprint(UR.usage_bp); wc = _w.test_client()
ans = wc.get(f"/usage?period=30d&compare=1&tz={TZ}")
j = ans.get_json()
per, tot, bef = j["period"], j["totals"], j["before"]
check("route /usage: the window in the person's own time - 30 days to today local (Oct 2 - Oct 31), the day before it the period before; the edition self-hosted",
      ans.status_code == 200 and per["start"] == "2026-10-02T00:00:00" and per["end"] == "2026-11-01T00:00:00" and per["bucket"] == "day" and per["buckets"] == 30 and per["label"] == "2 – 31 Oct"
      and per["before"]["start"] == "2026-09-02T00:00:00" and per["before"]["end"] == "2026-10-02T00:00:00" and per["edition"] == "self-hosted" and per["tier"] == "local", per)
check("route /usage totals: 13 calls in 7 chains, the cost summed, tokens in and out, the model time; the cache over the 11 calls that recorded it (the two rows from before read as not recorded, never zero); the savings; the search fee inside the cost",
      tot["calls"] == 13 and tot["chains"] == 7 and abs(tot["cost"] - 0.357) < 1e-9 and tot["tokens_in"] == 91500 and tot["tokens_out"] == 5800 and abs(tot["time"] - 75.0) < 1e-9
      and tot["recorded_calls"] == 11 and tot["recorded_in"] == 81500 and tot["cached"] == 30000 and tot["written"] == 1000 and abs(tot["cached_share"] - 30000 / 81500) < 1e-9
      and abs(tot["savings"] - 0.063) < 1e-9 and tot["search_fee"] == 0.01 and tot["compute"] == 0 and tot["compute_chains"] == 0, tot)
check("route /usage before: the period before holds the two chains of Sep 2 - Oct 1 and not the one of Sep 1", bef["chains"] == 2 and bef["calls"] == 3 and abs(bef["cost"] - 0.06) < 1e-9, bef)
days = {d["key"]: d for d in j["days"]}
d18 = days["2026-10-18"]
check("route /usage days: one entry per local day in order, each with its totals and its split by seat, model and mode as [cost, tokens, calls, time]; Oct 18 holds c1 and c2 (local 14:00 and 16:00, UTC 04:00 and 06:00)",
      [d["key"] for d in j["days"]][0] == "2026-10-02" and j["days"][-1]["key"] == "2026-10-31" and d18["label"] == "18 Oct" and d18["calls"] == 6 and d18["chains"] == 2 and abs(d18["cost"] - 0.185) < 1e-9
      and d18["seats"]["Analyst"][2] == 4 and abs(d18["seats"]["Analyst"][0] - 0.14) < 1e-9 and d18["seats"]["Reviewer"] == [0.03, 8200, 1, 5.0] and d18["models"]["m-small"][2] == 1
      and abs(d18["modes"]["Deep"][0] - 0.135) < 1e-9 and abs(d18["modes"]["Quick"][0] - 0.05) < 1e-9 and days["2026-10-22"]["modes"] == {"Other": [0.08, 17000, 1, 20.0]}
      and set(days["2026-10-24"]["modes"]) == {"Adaptive", "not recorded"}, d18)
seats = {s["seat"]: s for s in j["seats"]}
check("route /usage seats: by cost, the Analyst first with its calls, tokens, cost, time, tok/s and cached share over the rows that recorded it; the chains it spent on",
      [s["seat"] for s in j["seats"]][:2] == ["Analyst", "Promoter"] and seats["Analyst"]["calls"] == 8 and seats["Analyst"]["tokens_in"] == 61500 and abs(seats["Analyst"]["cost"] - 0.225) < 1e-9
      and seats["Analyst"]["recorded_in"] == 54500 and seats["Analyst"]["cached"] == 26000 and seats["Analyst"]["chains"] == 6 and seats["Analyst"]["tps"] == round(2800 / 44.0, 1)
      and seats["Rewriter"]["cached_share"] == 0.0, seats)
models = {m["model"]: m for m in j["models"]}
check("route /usage models: the calls and tokens per model, and no list price when the configuration has none for it", models["m-big"]["calls"] == 10 and models["m-small"]["calls"] == 3 and models["m-big"]["price_in"] is None and models["m-big"]["provider"] == "", models)
led = {e["chain"]: e for e in j["analyses"]}
check("route /usage analyses: one entry per chain, newest first, joined to the thread store - the question, the title, the mode, the cells, the figures, the outcome, the wall time - with its calls, tokens, cost and seat split",
      [e["chain"] for e in j["analyses"]] == ["c7", "c6", "c5", "c4", "c3", "c2", "c1"] and led["c1"]["question"] == "Does the second regime raise the yield?" and led["c1"]["title"].startswith("The second regime")
      and led["c1"]["mode"] == "Deep" and led["c1"]["cells"] == 2 and led["c1"]["figures"] == 1 and led["c1"]["outcome"] == "reproduced" and led["c1"]["kind"] == "analysis" and led["c1"]["thread"] == "t1"
      and led["c1"]["when"] == "2026-10-18T04:00:00" and led["c1"]["calls"] == 4 and abs(led["c1"]["cost"] - 0.135) < 1e-9 and led["c1"]["seats"] == {"Analyst": 0.09, "Reviewer": 0.03, "Google Search Executor": 0.015}
      and led["c1"]["wall"] == 240.0, led.get("c1"))
os.makedirs(os.path.join(STORAGE, "favourites", "t1"), exist_ok=True); open(os.path.join(STORAGE, "favourites", "t1", "c1.json"), "w").write("{}")      # c1 saved as a favourite, c2 not
j = wc.get(f"/usage?period=30d&compare=1&tz={TZ}").get_json(); led = {e["chain"]: e for e in j["analyses"]}
check("route /usage analyses: a failed run says at which cell; a run from before the cache fields has its cache not recorded; an Ideas run is an ideas entry; the Promoter's chain is named Save as routine with mode Routine in the chart; saved says whether the favourite's file exists (the page opens a chain from it)",
      led["c2"]["outcome"] == "failed at cell 4" and led["c2"]["mode"] == "Quick" and led["c3"]["recorded_in"] == 0 and led["c3"]["cached"] == 0 and led["c3"]["outcome"] == "answered"
      and led["c4"]["kind"] == "ideas" and led["c5"]["kind"] == "routine" and led["c5"]["question"] == "Save as routine: the proposal" and led["c5"]["cells"] is None
      and led["c1"]["saved"] is True and led["c2"]["saved"] is False and led["c5"]["saved"] is False, (led.get("c2"), led.get("c5")))
check("route /usage analyses whose thread file is gone: the one with the ledger's line keeps its question, mode, outcome and cells (the thread from the line, not saved); the one from before the ledger is 'An analysis that was not saved', its mode not recorded",
      led["c6"]["question"] == "Which weeks carried the most load?" and led["c6"]["mode"] == "Adaptive" and led["c6"]["outcome"] == "differed" and led["c6"]["cells"] == 1 and led["c6"]["kind"] == "analysis"
      and led["c6"]["thread"] == "t9" and led["c6"]["saved"] is False and led["c7"]["question"] == "An analysis that was not saved" and led["c7"]["kind"] == "analysis" and led["c7"]["mode"] == "" and led["c7"]["outcome"] == ""
      and UR.mode_label(led["c7"]) == "not recorded" and UR.mode_label(led["c6"]) == "Adaptive" and UR.mode_label(led["c5"]) == "Other", (led.get("c6"), led.get("c7")))
so = j["stands_out"]
check("route /usage what stands out: the heaviest day with its share, its analyses, its top seat and its dearest question; the cache line over the recorded calls with the highest and lowest seat; the failures line",
      len(so) == 3 and so[0]["head"] == "18 Oct" and so[0]["text"].startswith("$0.18, about half of the period, in 2 analyses") and "in 2 analyses" in so[0]["text"] and "the Analyst's calls were $0.14 of it" in so[0]["text"] and "The second regime raises the yield by 12%" in so[0]["text"]
      and so[1]["head"] == "Cache" and so[1]["text"].startswith("37% of the input was served from the cache ($0.06 saved) on the 11 of 13 calls that recorded it") and "the Analyst's share is 48%, the Promoter's 0%" in so[1]["text"]
      and so[2]["head"] == "Failures" and so[2]["text"] == "1 of 5 analyses failed (20%), $0.05 spent on it; 1 was not saved, so how it ended is not on record.", so)
ans2 = wc.get(f"/usage?period=7d&compare=0&tz={TZ}").get_json()
check("route /usage, 7 days without the comparison: the window Oct 25 - 31, no before, the totals of what falls in it (nothing here)", ans2["period"]["start"] == "2026-10-25T00:00:00" and ans2["before"] is None and ans2["period"]["before"] is None and ans2["totals"]["calls"] == 0 and ans2["stands_out"] == [{"head": "Nothing", "text": "No model calls in this period."}], ans2["period"])
ans3 = wc.get(f"/usage?period=24h&tz={TZ}").get_json()
check("route /usage, 24 hours: hourly buckets, 24 of them, to the end of the current local hour", ans3["period"]["bucket"] == "hour" and ans3["period"]["buckets"] == 24 and ans3["period"]["end"] == "2026-10-31T23:00:00" and ans3["days"][0]["label"] == "23:00" and ans3["period"]["label"] == "30 Oct 23:00 – 31 Oct 22:59", ans3["period"])
ans4 = wc.get(f"/usage?period=month&tz={TZ}").get_json(); ans5 = wc.get(f"/usage?period=last_month&tz={TZ}").get_json()
check("route /usage, this month and last month: Oct 1 - 31 (31 days, the 31 before it as the period before) with the five October chains, and Sep 1 - 30 holding the three September chains, the one of Sep 1 among them",
      ans4["period"]["start"] == "2026-10-01T00:00:00" and ans4["period"]["buckets"] == 31 and ans4["period"]["before"]["start"] == "2026-08-31T00:00:00" and ans4["totals"]["chains"] == 7
      and ans5["period"]["start"] == "2026-09-01T00:00:00" and ans5["period"]["end"] == "2026-10-01T00:00:00" and ans5["totals"]["chains"] == 3 and ans5["period"]["label"] == "1 – 30 Sep", (ans4["period"], ans5["period"]))
det = wc.get(f"/usage/analysis/c1?tz={TZ}").get_json()
check("route /usage/analysis/<chain>: the entry as the ledger has it, the totals, the seats ranked, the models, and the calls in time (seconds from the first, the elapsed, the model, the tokens, the cost), the span",
      det["analysis"]["question"] == "Does the second regime raise the yield?" and det["totals"]["calls"] == 4 and [s["seat"] for s in det["seats"]] == ["Analyst", "Reviewer", "Google Search Executor"]
      and [c["at"] for c in det["calls"]] == [0.0, 60.0, 120.0, 180.0] and det["calls"][0]["elapsed"] == 10.0 and det["calls"][3]["search_fee"] == 0.01 and det["calls"][0]["cached"] == 6000 and det["span"] == 182.0
      and [m["model"] for m in det["models"]] == ["m-big", "m-small"], det)
check("route /usage/analysis of an unknown chain: 404", wc.get("/usage/analysis/nope").status_code == 404)
calls1 = wc.get(f"/usage/calls?period=30d&tz={TZ}&page=1&size=10").get_json(); calls2 = wc.get(f"/usage/calls?period=30d&tz={TZ}&page=2&size=10").get_json()
check("route /usage/calls: the rows of the period newest first, a page at a time, 'more' when a page follows", len(calls1["rows"]) == 10 and calls1["rows"][0]["chain"] == "c7" and calls1["rows"][-1]["chain"] == "c1" and calls1["more"] is True
      and len(calls2["rows"]) == 3 and calls2["more"] is False and calls1["rows"][0]["seat"] == "Analyst" and calls2["rows"][-1]["t"] == "2026-10-18T04:00:00", (calls1, calls2))
csvr = wc.get(f"/usage/export.csv?period=30d&tz={TZ}")
lines = csvr.get_data(as_text=True).splitlines()
check("route /usage/export.csv: an attachment of the period's rows as recorded, the five fields empty where not recorded", csvr.status_code == 200 and "attachment; filename=\"usage_30d_20261002-20261031.csv\"" in csvr.headers["Content-Disposition"]
      and lines[0] == ",".join(UR.CSV_COLUMNS) and len(lines) == 14 and any(",m-big,7000,,,300," in ln for ln in lines) and csvr.headers["X-Rows"] == "13", (lines[:3], csvr.headers))
check("the local store takes in_() (the ledger's chains and threads looked up in batches)", [r["chain_id"] for r in rt_store.table("chains").select("chain_id").in_("chain_id", ["c1", "c5", "zz"]).order("chain_id").execute().data] == ["c1", "c5"]
      and rt_store.table("chains").select("chain_id").in_("chain_id", []).execute().data == [])
# the window arithmetic on its own: the period before is the same length immediately before; a month's days are the month's
w = UR.window("30d", datetime(2026, 3, 15, 9)); check("window(): 30 days end today exclusive, the before window the 30 days ahead of it", w[0] == datetime(2026, 2, 14) and w[1] == datetime(2026, 3, 16) and w[4] == (datetime(2026, 1, 15), datetime(2026, 2, 14)), w)
w = UR.window("last_month", datetime(2026, 3, 15, 9)); check("window(): last month is Feb 1 - Mar 1 (28 days) with January before it", w[0] == datetime(2026, 2, 1) and w[1] == datetime(2026, 3, 1) and w[4] == (datetime(2026, 1, 4), datetime(2026, 2, 1)) and w[3] == "1 – 28 Feb", w)
check("outcome(): the words the ledger uses", [UR.outcome(f) for f in ({"status": "answered", "replay": "reproduced"}, {"status": "answered", "replay": ""}, {"status": "answered", "replay": "differed"}, {"status": "answered", "replay": "failed"},
      {"status": "failed", "failed_at": 3}, {"status": "failed", "refused": True}, {"status": "failed"}, {"status": "stopped"}, {"status": "asked"})] == ["reproduced", "answered", "differed", "replay failed", "failed at cell 3", "refused", "failed", "stopped", "asked"])
check("prices(): the configuration's per-thousand prices as per-million, the provider from the seat that uses the model",
      UR.prices({"model_properties": {"m": {"prompt_tokens": 0.003, "completion_tokens": 0.015, "cache_read_tokens": 0.0003}}, "agent_configs": [{"agent": "Analyst", "details": {"model": "m", "provider": "anthropic"}}]})
      == {"m": {"in": 3.0, "out": 15.0, "cache_read": 0.3, "cache_write": None, "provider": "anthropic"}})

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
