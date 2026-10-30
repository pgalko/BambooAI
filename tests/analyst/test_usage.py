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

print(f"\n{len(passed)} passed, {len(failed)} failed")
sys.exit(1 if failed else 0)
