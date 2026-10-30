"""The Usage dialog's gallery fixture (docs/USAGE_DESIGN.md, 2026-10-31): a synthetic month of model calls and the
thread store beside them, run through the real route, saved as the page's fixture - tools/fixtures/usage.json, the
{url_substring: answer} shape tools/render_page.py serves. Generic questions, invented names; nothing from any
person. Deterministic (seed 11); the file is made when the gallery misses it and is not tracked.

  python3 tools/usage_fixture.py [out.json]
"""
import json
import os
import random
import sys
import tempfile
import types
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("-") else os.path.join(ROOT, "tools", "fixtures", "usage.json")
sys.path[:0] = [os.path.join(ROOT, "tests", "analyst"), ROOT, os.path.join(ROOT, "web_app"), os.path.join(ROOT, "tools", "stack")]
import _stubs  # noqa: F401,E402
os.environ["AUTH_MODE"] = "single"
os.environ["BAMBOO_DATA_DIR"] = tempfile.mkdtemp(prefix="usage_fx_")
WORK = tempfile.mkdtemp(prefix="usage_fx_work_")
os.chdir(WORK)
random.seed(11)
from bambooai.db import local_store                           # noqa: E402

U, A = "coach", "local|coach"
st = local_store.LocalStore(os.path.join(os.environ["BAMBOO_DATA_DIR"], "fx.sqlite"), local_sub=A, bamboo_user_id=U)
_fa = types.ModuleType("auth"); _fa.requires_auth = lambda f: f; _fa.get_current_user_id = lambda: A; sys.modules["auth"] = _fa
_fs = types.ModuleType("auth.supabase_client"); _fs.get_service_client = lambda: st; _fs.supabase_configured = lambda: True
_fs.get_user_subscription = lambda a: {"ok": True, "data": {"compute_tier": "pro"}}; sys.modules["auth.supabase_client"] = _fs
_fapp = types.ModuleType("app"); _fapp.user_path = lambda root, *p: os.path.join(WORK, root, U, *p); _fapp.get_user_id = lambda: U; sys.modules["app"] = _fapp
import usage_routes as UR                                     # noqa: E402

NOW = datetime(2026, 10, 31, 3, 0, 0)                         # UTC; the page at UTC+10 (tz=600): Oct 31, 13:00 local
UR._utcnow = lambda: NOW
TZ = 600
os.makedirs("config/coach", exist_ok=True)
json.dump({"model_properties": {"claude-sonnet-5.5": {"prompt_tokens": 0.003, "completion_tokens": 0.015, "cache_read_tokens": 0.0003, "cache_write_tokens": 0.00375},
                                "gpt-6.1-sol": {"prompt_tokens": 0.00125, "completion_tokens": 0.01, "cache_read_tokens": 0.000125},
                                "gemini-3-flash": {"prompt_tokens": 0.0003, "completion_tokens": 0.0025, "cache_read_tokens": 0.000075, "grounding_search_request": 0.014}},
           "agent_configs": [{"agent": "Analyst", "details": {"model": "claude-sonnet-5.5", "provider": "anthropic"}}, {"agent": "Reviewer", "details": {"model": "gpt-6.1-sol", "provider": "openai"}},
                             {"agent": "Reader", "details": {"model": "gemini-3-flash", "provider": "google"}}]}, open("config/coach/LLM_CONFIG.json", "w"))

QUESTIONS = ["Does the cadence–power relationship within rides differ between heat sessions and the rest, and by how much?",
             "Which weeks had the biggest gap between planned and completed load, and what happened on those days?",
             "At what local hour does training usually start, and what share of sessions start between 9 and 12?",
             "Summarise last week's wellness log against the plan.", "How did the time in zones shift across the block, by ride type?",
             "Which rides carried notes mentioning fatigue, and what did their power look like?", "What share of rides had a within-ride cadence–power correlation under 0.3?",
             "Compare the two blocks' weekly load.", "Which custom zones carried the most time in the climbs?", "Plot the heart-rate drift per ride against the temperature.",
             "How many rows does this file have?", "Is the resting heart rate trending down over the block?", "Where did the long rides fall in the week, and did sleep follow?",
             "What was the average session length by month?", "Which days had both a hard session and a poor sleep score?"]
TITLES = ["The second block carried 18% more load than the first", "Sessions start at 9:40 on average; 62% between 9 and 12", "No difference once the hot days are set apart", ""]
MODELS = {"Analyst": ("claude-sonnet-5.5", 0.003, 0.015, 0.0003), "Reviewer": ("gpt-6.1-sol", 0.00125, 0.01, 0.000125), "Reader": ("gemini-3-flash", 0.0003, 0.0025, 0.000075),
          "Rewriter": ("gemini-3-flash", 0.0003, 0.0025, 0.000075), "Promoter": ("claude-sonnet-5.5", 0.003, 0.015, 0.0003), "Figures": ("gemini-3-flash", 0.0003, 0.0025, 0.000075),
          "Google Search Executor": ("gemini-3-flash", 0.0003, 0.0025, 0.000075), "Knowledge Distiller": ("gemini-3-flash", 0.0003, 0.0025, 0.000075)}
from analyst.notebook import Notebook, NotebookStore, Turn    # noqa: E402

nbs = NotebookStore(os.path.join(WORK, "storage", U))
threads = {}
chain_no = [1793300000]


def call(chain, thread, t, seat, tin, cached, tout, el, fee=0.0):
    model, pin, pout, pc = MODELS[seat]
    cost = ((tin - cached) * pin + cached * pc + tout * pout) / 1000 + fee
    sav = (tin * pin) / 1000 - ((tin - cached) * pin + cached * pc) / 1000
    p = {"bamboo_user_id": U, "chain_id": chain, "agent": seat, "timestamp": (t - timedelta(minutes=TZ)).strftime("%Y-%m-%d %H:%M:%S"), "model": model, "prompt_tokens": tin,
         "completion_tokens": tout, "elapsed_time": round(el, 1), "tokens_per_second": round(tout / el, 1), "cost": round(cost, 6), "cached_tokens": cached, "cache_write_tokens": 0,
         "cache_savings": round(sav, 6), "search_fee": fee, "image_fee": 0.0}
    r = st.rpc("insert_usage_with_chain", {"p_usage_data": p, "p_thread_id": thread}).execute().data
    assert r.get("success"), r


def analysis(day, hour, thread, mode, fail=False, q=None):
    """One analysis: its analyst turns with a reader, reviews and a rewrite among them, as rows and as a run."""
    chain_no[0] += random.randint(30, 900)
    chain = str(chain_no[0])
    t0 = datetime(2026, 10, day, hour, random.randint(0, 59))
    turns_n = {"Quick": random.randint(2, 4), "Deep": random.randint(5, 12), "Adaptive": random.randint(4, 9)}[mode]
    t, cells, turns = t0, 0, []
    created = (t0 - timedelta(minutes=TZ) - datetime(1970, 1, 1)).total_seconds()
    for i in range(turns_n):
        tin = random.randint(6000, 40000); cached = int(tin * random.uniform(0.2, 0.7)) if i else 0
        el = random.uniform(4, 25)
        call(chain, thread, t, "Analyst", tin, cached, random.randint(200, 1500), el)
        t += timedelta(seconds=el + random.uniform(2, 20))
        if i < turns_n - 1:
            cells += 1
            tu = Turn(kind="cell", cell_no=cells, code="x = df.describe()", elapsed=random.uniform(0.3, 4), created=created + (t - t0).total_seconds())
            if fail and i == turns_n - 2:
                tu.error = "KeyError: 'power'"
            turns.append(tu)
            if i == 1 and random.random() < 0.5:
                el2 = random.uniform(2, 6); call(chain, thread, t, "Reader", random.randint(5000, 20000), random.randint(0, 4000), random.randint(300, 900), el2); t += timedelta(seconds=el2)
                turns.append(Turn(kind="read", stdout="…", created=created + (t - t0).total_seconds()))
            if mode != "Quick" and i % 3 == 2:
                el3 = random.uniform(3, 9); call(chain, thread, t, "Reviewer", random.randint(10000, 30000), random.randint(5000, 15000), random.randint(200, 600), el3); t += timedelta(seconds=el3)
                turns.append(Turn(kind="review", note="…", created=created + (t - t0).total_seconds()))
        else:
            turns.append(Turn(kind="report", text="# Found", created=created + (t - t0).total_seconds()))
            if not fail:
                el4 = random.uniform(2, 5); call(chain, thread, t, "Rewriter", random.randint(2000, 5000), 0, random.randint(300, 800), el4); t += timedelta(seconds=el4)
                turns.append(Turn(kind="rewrite", text="plain", created=created + (t - t0).total_seconds()))
                if random.random() < 0.4:
                    el5 = random.uniform(2, 6); call(chain, thread, t, "Figures", random.randint(3000, 8000), 0, random.randint(300, 900), el5); t += timedelta(seconds=el5)
    if random.random() < 0.15:
        call(chain, thread, t0 + timedelta(seconds=30), "Google Search Executor", 2000, 0, 300, 3.0, fee=0.014)
    nb = threads.setdefault(thread, Notebook(thread))
    run = nb.new_run(q or random.choice(QUESTIONS), run_id=chain); run.mode = mode; run.created = created; run.turns = turns
    run.status = "failed" if fail else "answered"
    run.replay_status = "" if fail else random.choice(["reproduced", "reproduced", "reproduced", "differed", ""])
    run.title = "" if fail else random.choice(TITLES)
    return chain


for day in range(2, 32):
    n = 14 if day == 18 else random.choice([2, 3, 4, 6, 8, 1, 0, 5, 9, 3])
    if day in (3, 10, 17, 24, 31):
        n = max(0, n - 3)
    for k in range(n):
        analysis(day, random.randint(7, 21), f"t{day}", random.choice(["Deep", "Deep", "Quick", "Adaptive", "Quick"]), fail=random.random() < 0.06)
# a Save-as-routine proposal, an ideas run, the memory's distillation
call("1793399001", "t18", datetime(2026, 10, 18, 17, 5), "Promoter", 14000, 0, 2200, 18.0)
ideas = analysis(20, 9, "t20", "Quick", q="Ideas")
threads["t20"].runs[ideas].mode = "Ideas"
call("1793399002", "t22", datetime(2026, 10, 22, 11, 0), "Knowledge Distiller", 6000, 0, 400, 3.0)
# the period before: a lighter month
for day in range(2, 30):
    for k in range(random.choice([0, 1, 2, 3])):
        chain_no[0] += 100; c = str(chain_no[0])
        call(c, "s" + str(day), datetime(2026, 9, day, 10) + timedelta(minutes=k * 40), "Analyst", 15000, 5000, 600, 9.0)
        call(c, "s" + str(day), datetime(2026, 9, day, 10, 1) + timedelta(minutes=k * 40), "Rewriter", 3000, 0, 500, 3.0)
for nb in threads.values():
    nbs.save(nb)
# the hosted edition's rows carry the tier and the compute charge (a trigger on the hosted table does it)
st.conn.execute("UPDATE usage SET compute_tier = 'pro', query_cost = 0.03 WHERE timestamp >= '2026-10-01'"); st.conn.commit()

from flask import Flask                                       # noqa: E402
w = Flask("t"); w.secret_key = "t"; w.register_blueprint(UR.usage_bp); wc = w.test_client()
ans = wc.get(f"/usage?period=30d&compare=1&tz={TZ}").get_json()
top = max(ans["analyses"], key=lambda e: e["cost"] if e["kind"] == "analysis" else 0)
det = wc.get(f"/usage/analysis/{top['chain']}?tz={TZ}").get_json()
calls = wc.get(f"/usage/calls?period=30d&tz={TZ}&page=1&size=100").get_json()
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump({"/usage?": ans, "/usage/analysis/": det, "/usage/calls": calls}, open(OUT, "w"))
print(f"wrote {OUT}: {ans['totals']['chains']} chains, {ans['totals']['calls']} calls, ${ans['totals']['cost']:.2f}; the detail of {top['chain']}")
