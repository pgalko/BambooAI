"""Usage (docs/USAGE_DESIGN.md §3, 2026-10-31): what the analyses cost and where the money and the time went, computed
from the call records (the usage table: one row per model call) and the thread store, for the dialog usage.js draws.
Nothing here is written by a model.

  GET /usage?period=30d&compare=1&tz=600   the tiles, the period before (the deltas), the days (the chart's columns
                                           split by seat, model and mode), the seats, the models, the analyses (the
                                           ledger), what stands out
  GET /usage/analysis/<chain>              one analysis: its calls in time, its seats ranked, its models
  GET /usage/calls?period=..&page=1        the raw rows of the period, newest first, a page at a time
  GET /usage/export.csv?period=..          the rows of the period, one per call, as recorded

Periods: 24h, 7d, 30d, 90d, month (this month so far), last_month - days in the person's own time (tz: minutes east
of UTC, as the page sends it); the rows' timestamps are UTC. The period before is the same length immediately before.
Rows from before patch 0255 have the cache split, the savings and the fees NULL: not recorded, never zero - the cached
share and the savings are computed over the rows that carry them, and the answer says how many do.
"""
import csv
import io
import json
import os
import re
from collections import Counter
from datetime import datetime, timedelta

from flask import Blueprint, Response, jsonify, request

from auth import requires_auth, get_current_user_id
from auth.supabase_client import get_service_client, get_user_subscription, supabase_configured
from logger_config import get_logger

logger = get_logger(__name__)
usage_bp = Blueprint('usage', __name__)

PERIODS = ("24h", "7d", "30d", "90d", "month", "last_month")
PAGE = 1000                  # rows per fetch
MAX_ROWS = 50000             # the most rows one answer aggregates (the answer says when it stopped there)
_FACTS = {}                  # thread file -> (mtime, {run id: the facts the ledger shows}); re-read when the file changes

# a chain the thread store does not know, named by the seat that spent on it
_OTHER = {"Promoter": ("routine", "Save as routine: the proposal"), "Coder": ("context", "The context coded"), "Reader": ("reading", "A document read"),
          "Knowledge Distiller": ("memory", "Memory: the distillation"), "Embedder": ("memory", "Memory: the embeddings")}


def _app():
    import app as webapp                                     # the main module: the paths, the user
    return webapp


def _utcnow():
    return datetime.utcnow()


def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _ts(s):
    """A row's timestamp as a naive UTC datetime: SQLite keeps the logger's 'YYYY-MM-DD HH:MM:SS', PostgREST answers ISO."""
    s = str(s or "")[:19].replace("T", " ")
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return datetime.strptime(s[:10], "%Y-%m-%d")


def _tz():
    try:
        return max(-840, min(840, int(request.args.get("tz", "0"))))
    except ValueError:
        return 0


def _period():
    p = request.args.get("period", "30d")
    return p if p in PERIODS else "30d"


def window(period, now_local):
    """The period's window in local time, its end exclusive: (start, end, bucket, label, the window before)."""
    day0 = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "24h":
        end = now_local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        start, bucket = end - timedelta(hours=24), "hour"
    elif period == "month":
        start, end, bucket = day0.replace(day=1), day0 + timedelta(days=1), "day"
    elif period == "last_month":
        end = day0.replace(day=1)
        start, bucket = (end - timedelta(days=1)).replace(day=1), "day"
    else:
        n = int(period[:-1])
        start, end, bucket = day0 - timedelta(days=n - 1), day0 + timedelta(days=1), "day"      # today and the n-1 days before it
    length = end - start
    before = (start - length, start)
    return start, end, bucket, _label(start, end, bucket), before


def _label(start, end, bucket):
    last = end - timedelta(seconds=1)
    if bucket == "hour":
        return f"{start.strftime('%-d %b %H:%M')} – {last.strftime('%-d %b %H:%M')}"
    if start.month == last.month and start.year == last.year:
        return f"{start.day} – {last.strftime('%-d %b')}" if start.day != last.day else last.strftime('%-d %b')
    return f"{start.strftime('%-d %b')} – {last.strftime('%-d %b')}"


def _buckets(start, end, bucket):
    out, t = [], start
    step = timedelta(hours=1) if bucket == "hour" else timedelta(days=1)
    while t < end:
        out.append((t.strftime("%Y-%m-%d %H:00") if bucket == "hour" else t.strftime("%Y-%m-%d"), t.strftime("%H:%M") if bucket == "hour" else t.strftime("%-d %b")))
        t += step
    return out


def _bucket_of(t_local, bucket):
    return t_local.strftime("%Y-%m-%d %H:00") if bucket == "hour" else t_local.strftime("%Y-%m-%d")


# ---------------------------------------------------------------- the rows
def _call(r):
    """A row as the route reads it; the five fields of 0255 None when the row predates them (not recorded)."""
    cached, written, sav = r.get("cached_tokens"), r.get("cache_write_tokens"), r.get("cache_savings")
    return {"id": r.get("id"), "t": _ts(r.get("timestamp")), "seat": r.get("agent") or "Unknown", "model": r.get("model") or "Unknown", "chain": str(r.get("chain_id") or ""),
            "tokens_in": int(r.get("prompt_tokens") or 0), "tokens_out": int(r.get("completion_tokens") or 0), "elapsed": float(r.get("elapsed_time") or 0),
            "tps": float(r.get("tokens_per_second") or 0), "cost": float(r.get("cost") or 0),
            "cached": None if cached is None else int(cached), "written": None if written is None else int(written), "savings": None if sav is None else float(sav),
            "search_fee": float(r.get("search_fee") or 0), "image_fee": float(r.get("image_fee") or 0),
            "tier": r.get("compute_tier") or "", "query_cost": float(r.get("query_cost") or 0)}


def _fetch(client, user, start_utc, end_utc, newest_first=False, offset=0, limit=None):
    """The user's rows between two UTC instants, in pages; [rows, truncated]."""
    out, off, truncated = [], offset, False
    while True:
        size = PAGE if limit is None else min(PAGE, limit - len(out))
        if size <= 0:
            break
        q = client.table("usage").select("*").eq("bamboo_user_id", user).gte("timestamp", _fmt(start_utc)).lt("timestamp", _fmt(end_utc))
        q = q.order("timestamp", desc=newest_first).order("id", desc=newest_first).range(off, off + size - 1)
        batch = q.execute().data or []
        out.extend(batch)
        if len(batch) < size:
            break
        off += size
        if limit is None and len(out) >= MAX_ROWS:
            truncated = True
            break
    return out, truncated


def _totals(calls):
    a = {"cost": 0.0, "calls": 0, "chains": 0, "tokens_in": 0, "tokens_out": 0, "time": 0.0, "cached": 0, "written": 0, "recorded_in": 0, "recorded_calls": 0,
         "savings": 0.0, "search_fee": 0.0, "image_fee": 0.0, "compute": 0.0, "compute_chains": 0}
    chains = {}
    for c in calls:
        a["cost"] += c["cost"]; a["calls"] += 1; a["tokens_in"] += c["tokens_in"]; a["tokens_out"] += c["tokens_out"]; a["time"] += c["elapsed"]
        a["search_fee"] += c["search_fee"]; a["image_fee"] += c["image_fee"]
        if c["cached"] is not None:
            a["cached"] += c["cached"]; a["written"] += c["written"] or 0; a["recorded_in"] += c["tokens_in"]; a["recorded_calls"] += 1; a["savings"] += c["savings"] or 0.0
        if c["chain"] and c["chain"] not in chains:
            chains[c["chain"]] = c["query_cost"]               # the compute charge is per chain, written on each of its rows
    a["chains"] = len(chains)
    a["compute"] = sum(chains.values())
    a["compute_chains"] = sum(1 for v in chains.values() if v > 0)
    a["cached_share"] = (a["cached"] / a["recorded_in"]) if a["recorded_in"] else None
    for k in ("cost", "time", "savings", "search_fee", "image_fee", "compute"):
        a[k] = round(a[k], 6)
    return a


def _group(calls, key):
    """Per key: calls, tokens, cost, time, the cache over the rows that recorded it, the chains."""
    out = {}
    for c in calls:
        g = out.setdefault(c[key], {"calls": 0, "tokens_in": 0, "tokens_out": 0, "cost": 0.0, "time": 0.0, "cached": 0, "recorded_in": 0, "chains": set()})
        g["calls"] += 1; g["tokens_in"] += c["tokens_in"]; g["tokens_out"] += c["tokens_out"]; g["cost"] += c["cost"]; g["time"] += c["elapsed"]
        if c["cached"] is not None:
            g["cached"] += c["cached"]; g["recorded_in"] += c["tokens_in"]
        if c["chain"]:
            g["chains"].add(c["chain"])
    rows = []
    for k, g in out.items():
        rows.append({key: k, "calls": g["calls"], "tokens_in": g["tokens_in"], "tokens_out": g["tokens_out"], "cost": round(g["cost"], 6), "time": round(g["time"], 3),
                     "cached": g["cached"], "recorded_in": g["recorded_in"], "cached_share": (g["cached"] / g["recorded_in"]) if g["recorded_in"] else None,
                     "chains": len(g["chains"]), "tps": round(g["tokens_out"] / g["time"], 1) if g["time"] > 0 else None})
    rows.sort(key=lambda r: -r["cost"])
    return rows


# ---------------------------------------------------------------- the thread store: what the chain was
def _thread_of(client, user, chain_ids):
    """chain id -> thread id, through the chains and threads tables (two plain selects: no embed, so the self-hosted
    file, the hosted service and the stack's stand-in answer alike)."""
    ids = sorted(c for c in set(chain_ids) if c)
    chains, out = {}, {}
    for i in range(0, len(ids), 200):
        for r in client.table("chains").select("chain_id, thread_id").eq("bamboo_user_id", user).in_("chain_id", ids[i:i + 200]).execute().data or []:
            chains[str(r.get("chain_id"))] = r.get("thread_id")
    tids = sorted({t for t in chains.values() if t is not None})
    names = {}
    for i in range(0, len(tids), 200):
        for r in client.table("threads").select("id, thread_id").in_("id", tids[i:i + 200]).execute().data or []:
            names[r.get("id")] = str(r.get("thread_id"))
    for c, t in chains.items():
        if t in names:
            out[c] = names[t]
    return out


def _facts_of(store_dir, thread_id):
    """The runs of one thread as the ledger needs them, from the thread's file (read once per change)."""
    from analyst.notebook import run_facts
    f = os.path.join(store_dir, "threads", re.sub(r"[^A-Za-z0-9_-]", "", str(thread_id)) + ".json")
    try:
        m = os.path.getmtime(f)
    except OSError:
        return {}
    hit = _FACTS.get(f)
    if hit and hit[0] == m:
        return hit[1]
    try:
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
    except Exception:                                          # noqa: BLE001
        logger.warning("usage: thread file unreadable: %s", f)
        return {}
    out = {str(rid): run_facts(r) for rid, r in (d.get("runs") or {}).items()}
    _FACTS[f] = (m, out)
    return out


def _ledger_lines(store_dir):
    """The usage ledger the host writes at every run's end (analyst/notebook.py NotebookStore.record): the facts of a run
    whose thread file was discarded - a thread not saved as a favourite goes at the next sign-in (web_app/cleanup.py)."""
    from analyst.notebook import NotebookStore
    path = os.path.join(store_dir, "usage_ledger.jsonl")
    try:
        m = os.path.getmtime(path)
    except OSError:
        return {}
    hit = _FACTS.get(path)
    if hit and hit[0] == m:
        return hit[1]
    out = NotebookStore(store_dir).ledger()
    _FACTS[path] = (m, out)
    return out


def outcome(f):
    """One word for how the run ended: answered | reproduced | differed | replay failed | failed at cell n | refused | stopped | asked | running."""
    s = f.get("status") or ""
    if s == "failed":
        return "refused" if f.get("refused") else (f"failed at cell {f['failed_at']}" if f.get("failed_at") else "failed")
    if s in ("stopped", "asked", "running"):
        return s
    rp = f.get("replay") or ""
    if rp in ("reproduced", "differed"):
        return rp
    if rp == "failed":
        return "replay failed"
    return "answered" if s == "answered" else s


def mode_label(entry):
    """The mode the chart and the filter group a chain under: the run's own; "not recorded" for an analysis without one
    (from before 2026-10-20, or one whose thread was discarded before the ledger kept it); Other for a chain that is
    not an analysis (the Promoter's, the Coder's…)."""
    if entry.get("mode"):
        return entry["mode"]
    return "not recorded" if entry.get("kind") in ("analysis", "ideas") else "Other"


def _ledger(calls, threads, store_dir):
    """One entry per chain of the period: what it was (the thread file, else the usage ledger's line), what it cost (the rows)."""
    by_chain = {}
    for c in calls:
        by_chain.setdefault(c["chain"], []).append(c)
    lines = _ledger_lines(store_dir)
    out = []
    for chain, rows in by_chain.items():
        t = _totals(rows)
        seats = Counter()
        for c in rows:
            seats[c["seat"]] += c["cost"]
        first = min(c["t"] for c in rows)
        entry = {"chain": chain, "thread": threads.get(chain), "when": first.strftime("%Y-%m-%dT%H:%M:%S"), "kind": "", "question": "", "title": "", "mode": "", "cells": None, "figures": 0,
                 "outcome": "", "wall": None, "saved": False, "calls": t["calls"], "tokens_in": t["tokens_in"], "cached": t["cached"], "recorded_in": t["recorded_in"], "tokens_out": t["tokens_out"],
                 "time": t["time"], "cost": t["cost"], "savings": t["savings"], "compute": t["compute"], "seats": {k: round(v, 6) for k, v in seats.most_common()}}
        f = _facts_of(store_dir, threads[chain]).get(chain) if threads.get(chain) else None
        if f is None and chain in lines:                       # the thread file is gone: the line the host wrote when the run ended
            f = lines[chain]
            entry["thread"] = entry["thread"] or f.get("thread")
        if f:
            entry.update({"kind": "ideas" if f["mode"] == "Ideas" else "analysis", "question": f["question"], "title": f["title"], "mode": f["mode"], "cells": f["cells"],
                          "figures": f["figures"], "outcome": outcome(f), "wall": f["wall"],
                          "saved": bool(entry["thread"]) and os.path.exists(os.path.join(store_dir, "favourites", str(entry["thread"]), f"{chain}.json"))})   # the page opens a saved chain only
        else:
            top = seats.most_common(1)[0][0] if seats else ""
            kind, name = _OTHER.get(top, ("", ""))
            if kind:
                entry.update({"kind": kind, "question": name})
            elif threads.get(chain):
                entry.update({"kind": "analysis", "question": "An analysis that was not saved"})       # its thread was discarded before the ledger kept the facts (2026-10-31)
            else:
                entry.update({"kind": "other", "question": f"{top} calls" if top else "Calls"})
        out.append(entry)
    out.sort(key=lambda e: e["when"], reverse=True)
    return out


# ---------------------------------------------------------------- the configuration: list prices
def _config():
    """LLM_CONFIG.json as the model layer reads it: the user's own, else the box's."""
    for path in (os.path.join("config", _app().get_user_id() or "", "LLM_CONFIG.json"), "LLM_CONFIG.json"):
        try:
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    return json.load(fh)
        except Exception:                                      # noqa: BLE001
            logger.warning("usage: the configuration could not be read: %s", path)
    return {}


def prices(cfg):
    """Per model: the list price per million tokens (the configuration keeps it per thousand), and the provider."""
    out = {}
    for model, p in (cfg.get("model_properties") or {}).items():
        def per_m(k):
            v = p.get(k)
            return round(float(v) * 1000, 4) if isinstance(v, (int, float)) else None
        out[model] = {"in": per_m("prompt_tokens"), "out": per_m("completion_tokens"), "cache_read": per_m("cache_read_tokens"), "cache_write": per_m("cache_write_tokens"), "provider": ""}
    for a in cfg.get("agent_configs") or []:
        d = a.get("details") or {}
        if d.get("model") and d.get("provider"):
            out.setdefault(d["model"], {"in": None, "out": None, "cache_read": None, "cache_write": None, "provider": ""})["provider"] = d["provider"]
    return out


# ---------------------------------------------------------------- what stands out
def stands_out(totals, days, ledger, seats, bucket, tz=0):
    """Three computed lines: the heaviest day and what made it, the cache, the failures."""
    if not totals["calls"]:
        return [{"head": "Nothing", "text": "No model calls in this period."}]
    out = []
    top = max(days, key=lambda d: d["cost"])
    if top["cost"] > 0:
        share = top["cost"] / totals["cost"] if totals["cost"] else 0
        seat, seat_cost = max(top["seats"].items(), key=lambda kv: kv[1][0]) if top["seats"] else ("", [0])
        dear = [e for e in ledger if _bucket_of(datetime.strptime(e["when"], "%Y-%m-%dT%H:%M:%S") + timedelta(minutes=tz), bucket) == top["key"]]
        dear.sort(key=lambda e: -e["cost"])
        line = f"${top['cost']:.2f}, {_share(share)} of the period, in {top['chains']} {'analysis' if top['chains'] == 1 else 'analyses'}"
        if seat:
            line += f" — the {seat}'s calls were ${seat_cost[0]:.2f} of it"
        if dear and dear[0]["kind"] in ("analysis", "ideas") and not dear[0]["mode"] and dear[0]["question"].startswith("An analysis that was not saved"):
            line += f"; the dearest (${dear[0]['cost']:.2f}) was not saved, so its question is not on record"
        elif dear:
            q = dear[0]["title"] or dear[0]["question"]
            line += f"; the dearest: “{q[:90]}{'…' if len(q) > 90 else ''}” (${dear[0]['cost']:.2f})"
        out.append({"head": top["label"], "text": line + "."})
    if totals["recorded_in"]:
        pct = round(100 * (totals["cached_share"] or 0))
        line = f"{pct}% of the input was served from the cache (${totals['savings']:.2f} {'saved' if totals['savings'] >= 0 else 'spent: the writes outweighed the reads'})"
        if totals["recorded_calls"] < totals["calls"]:
            line += f" on the {totals['recorded_calls']} of {totals['calls']} calls that recorded it"
        rec = [s for s in seats if s["recorded_in"] >= 10000 and s["cached_share"] is not None]
        if len(rec) >= 2:
            hi, lo = max(rec, key=lambda s: s["cached_share"]), min(rec, key=lambda s: s["cached_share"])
            line += f"; the {hi['seat']}'s share is {round(100 * hi['cached_share'])}%, the {lo['seat']}'s {round(100 * lo['cached_share'])}%"
        out.append({"head": "Cache", "text": line + "."})
    else:
        out.append({"head": "Cache", "text": "The cache split is recorded per call since this dialog's release: no call of this period carries it yet."})
    analyses = [e for e in ledger if e["kind"] in ("analysis", "ideas")]
    runs = [e for e in analyses if e["outcome"]]                        # those whose ending is on record
    unknown = len(analyses) - len(runs)
    bad = [e for e in runs if e["outcome"].startswith("failed") or e["outcome"] == "refused"]
    stopped = [e for e in runs if e["outcome"] == "stopped"]
    if analyses:
        if bad:
            line = f"{len(bad)} of {len(runs)} {'analysis' if len(runs) == 1 else 'analyses'} failed ({round(100 * len(bad) / len(runs))}%), ${sum(e['cost'] for e in bad):.2f} {'between them' if len(bad) > 1 else 'spent on it'}"
            refused = sum(1 for e in bad if e["outcome"] == "refused")
            if refused:
                line += f"; {refused} {'was' if refused == 1 else 'were'} refused by the executor at a restricted operation"
        elif runs:
            line = "The one analysis did not fail" if len(runs) == 1 else f"None of the {len(runs)} analyses failed"
        else:
            line = "No analysis of this period has its ending on record"
        if stopped:
            line += f"; {len(stopped)} {'was' if len(stopped) == 1 else 'were'} stopped"
        if unknown:
            line += f"; {unknown} {'was' if unknown == 1 else 'were'} not saved, so how {'it' if unknown == 1 else 'they'} ended is not on record"
        out.append({"head": "Failures", "text": line + "."})
    return out[:3]


def _share(x):
    if x >= 0.45: return "about half"
    if x >= 0.3: return "a third"
    if x >= 0.22: return "a quarter"
    if x >= 0.17: return "a fifth"
    return f"{round(100 * x)}%"


# ---------------------------------------------------------------- the routes
def _who():
    auth0_id = get_current_user_id()
    user = auth0_id.split('|', 1)[1] if auth0_id and '|' in auth0_id else auth0_id
    return auth0_id, user


def _edition(auth0_id, calls):
    if not supabase_configured():
        return {"edition": "self-hosted", "tier": "local"}
    tier = ""
    try:
        sub = get_user_subscription(auth0_id)
        tier = ((sub or {}).get("data") or {}).get("compute_tier") or ""
    except Exception:                                          # noqa: BLE001
        pass
    if not tier and calls:
        tier = Counter(c["tier"] for c in calls if c["tier"]).most_common(1)[0][0] if any(c["tier"] for c in calls) else ""
    return {"edition": "hosted", "tier": tier}


@usage_bp.route('/usage', methods=['GET'])
@requires_auth
def usage():
    period, tz = _period(), _tz()
    compare = request.args.get("compare", "1") not in ("0", "false", "")
    auth0_id, user = _who()
    if not user:
        return jsonify({"error": "Not authenticated"}), 401
    now_local = _utcnow() + timedelta(minutes=tz)
    start, end, bucket, label, before = window(period, now_local)
    off = timedelta(minutes=tz)
    try:
        client = get_service_client()
        rows, truncated = _fetch(client, user, (before[0] if compare else start) - off, end - off)
        calls = [_call(r) for r in rows]
        for c in calls:
            c["local"] = c["t"] + off
        now_calls = [c for c in calls if c["local"] >= start]
        before_calls = [c for c in calls if c["local"] < start] if compare else []
        totals = _totals(now_calls)
        threads = _thread_of(client, user, [c["chain"] for c in now_calls])
        store_dir = _app().user_path('storage')
        ledger = _ledger(now_calls, threads, store_dir)
        modes = {e["chain"]: mode_label(e) for e in ledger}
        # the days: each with its totals and its split by seat, model and mode as [cost, tokens, calls, time]
        keys = _buckets(start, end, bucket)
        days = {k: {"key": k, "label": lb, "cost": 0.0, "tokens_in": 0, "tokens_out": 0, "calls": 0, "time": 0.0, "chains": set(), "seats": {}, "models": {}, "modes": {}} for k, lb in keys}
        for c in now_calls:
            d = days.get(_bucket_of(c["local"], bucket))
            if d is None:
                continue
            d["cost"] += c["cost"]; d["tokens_in"] += c["tokens_in"]; d["tokens_out"] += c["tokens_out"]; d["calls"] += 1; d["time"] += c["elapsed"]
            if c["chain"]:
                d["chains"].add(c["chain"])
            for split, k in (("seats", c["seat"]), ("models", c["model"]), ("modes", modes.get(c["chain"], "Other"))):
                g = d[split].setdefault(k, [0.0, 0, 0, 0.0])
                g[0] += c["cost"]; g[1] += c["tokens_in"] + c["tokens_out"]; g[2] += 1; g[3] += c["elapsed"]
        day_list = []
        for k, _ in keys:
            d = days[k]
            d["chains"] = len(d["chains"]); d["cost"] = round(d["cost"], 6); d["time"] = round(d["time"], 3)
            for split in ("seats", "models", "modes"):
                d[split] = {name: [round(v[0], 6), v[1], v[2], round(v[3], 3)] for name, v in d[split].items()}
            day_list.append(d)
        seats = _group(now_calls, "seat")
        models = _group(now_calls, "model")
        price = prices(_config())
        for m in models:
            p = price.get(m["model"]) or {}
            m.update({"provider": p.get("provider", ""), "price_in": p.get("in"), "price_out": p.get("out"), "price_cache_read": p.get("cache_read"), "price_cache_write": p.get("cache_write")})
        lines = stands_out(totals, day_list, ledger, seats, bucket, tz)
        ed = _edition(auth0_id, now_calls)
        return jsonify({
            "period": {"key": period, "label": label, "start": start.strftime("%Y-%m-%dT%H:%M:%S"), "end": end.strftime("%Y-%m-%dT%H:%M:%S"), "bucket": bucket, "buckets": len(keys),
                       "tz": tz, "before": {"start": before[0].strftime("%Y-%m-%dT%H:%M:%S"), "end": before[1].strftime("%Y-%m-%dT%H:%M:%S"), "label": _label(before[0], before[1], bucket)} if compare else None,
                       "edition": ed["edition"], "tier": ed["tier"], "truncated": truncated, "rows": len(now_calls)},
            "totals": totals, "before": _totals(before_calls) if compare else None, "days": day_list, "seats": seats, "models": models,
            "analyses": ledger, "stands_out": lines})
    except Exception as exc:                                   # noqa: BLE001
        logger.exception("usage: the answer failed")
        return jsonify({"error": f"usage could not be read: {str(exc)[:300]}"}), 500


@usage_bp.route('/usage/analysis/<chain>', methods=['GET'])
@requires_auth
def usage_analysis(chain):
    auth0_id, user = _who()
    if not user:
        return jsonify({"error": "Not authenticated"}), 401
    try:
        client = get_service_client()
        rows = client.table("usage").select("*").eq("bamboo_user_id", user).eq("chain_id", str(chain)).order("timestamp").order("id").range(0, PAGE - 1).execute().data or []
        calls = [_call(r) for r in rows]
        if not calls:
            return jsonify({"error": "no calls recorded for this chain"}), 404
        threads = _thread_of(client, user, [str(chain)])
        entry = _ledger(calls, threads, _app().user_path('storage'))[0]
        t0 = min(c["t"] for c in calls)
        out_calls = [{"id": c["id"], "at": (c["t"] - t0).total_seconds(), "t": c["t"].strftime("%Y-%m-%dT%H:%M:%S"), "seat": c["seat"], "model": c["model"], "tokens_in": c["tokens_in"],
                      "cached": c["cached"], "written": c["written"], "tokens_out": c["tokens_out"], "elapsed": c["elapsed"], "tps": c["tps"], "cost": round(c["cost"], 6),
                      "savings": c["savings"], "search_fee": c["search_fee"], "image_fee": c["image_fee"]} for c in calls]
        span = max((c["at"] + c["elapsed"]) for c in out_calls)
        return jsonify({"analysis": entry, "totals": _totals(calls), "seats": _group(calls, "seat"), "models": _group(calls, "model"), "calls": out_calls, "span": round(span, 1)})
    except Exception as exc:                                   # noqa: BLE001
        logger.exception("usage: the analysis could not be read")
        return jsonify({"error": f"the analysis could not be read: {str(exc)[:300]}"}), 500


@usage_bp.route('/usage/calls', methods=['GET'])
@requires_auth
def usage_calls():
    period, tz = _period(), _tz()
    auth0_id, user = _who()
    if not user:
        return jsonify({"error": "Not authenticated"}), 401
    try:
        page = max(1, int(request.args.get("page", "1")))
        size = max(10, min(500, int(request.args.get("size", "100"))))
    except ValueError:
        page, size = 1, 100
    now_local = _utcnow() + timedelta(minutes=tz)
    start, end, bucket, label, before = window(period, now_local)
    off = timedelta(minutes=tz)
    try:
        rows, _ = _fetch(get_service_client(), user, start - off, end - off, newest_first=True, offset=(page - 1) * size, limit=size + 1)
        calls = [_call(r) for r in rows[:size]]
        return jsonify({"page": page, "size": size, "more": len(rows) > size,
                        "rows": [{"id": c["id"], "t": c["t"].strftime("%Y-%m-%dT%H:%M:%S"), "chain": c["chain"], "seat": c["seat"], "model": c["model"], "tokens_in": c["tokens_in"], "cached": c["cached"],
                                  "written": c["written"], "tokens_out": c["tokens_out"], "elapsed": c["elapsed"], "tps": c["tps"], "cost": round(c["cost"], 6), "savings": c["savings"],
                                  "search_fee": c["search_fee"], "image_fee": c["image_fee"], "tier": c["tier"], "query_cost": c["query_cost"]} for c in calls]})
    except Exception as exc:                                   # noqa: BLE001
        logger.exception("usage: the calls could not be read")
        return jsonify({"error": f"the calls could not be read: {str(exc)[:300]}"}), 500


CSV_COLUMNS = ("id", "timestamp", "chain_id", "agent", "model", "prompt_tokens", "cached_tokens", "cache_write_tokens", "completion_tokens", "elapsed_time",
               "tokens_per_second", "cost", "cache_savings", "search_fee", "image_fee", "compute_tier", "query_cost")


@usage_bp.route('/usage/export.csv', methods=['GET'])
@requires_auth
def usage_export():
    period, tz = _period(), _tz()
    auth0_id, user = _who()
    if not user:
        return jsonify({"error": "Not authenticated"}), 401
    now_local = _utcnow() + timedelta(minutes=tz)
    start, end, bucket, label, before = window(period, now_local)
    off = timedelta(minutes=tz)
    try:
        rows, truncated = _fetch(get_service_client(), user, start - off, end - off)
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(CSV_COLUMNS)
        for r in rows:
            w.writerow([("" if r.get(c) is None else r.get(c)) for c in CSV_COLUMNS])
        name = f"usage_{period}_{start.strftime('%Y%m%d')}-{(end - timedelta(seconds=1)).strftime('%Y%m%d')}.csv"
        return Response(buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"', "X-Rows": str(len(rows)), "X-Truncated": "1" if truncated else "0"})
    except Exception as exc:                                   # noqa: BLE001
        logger.exception("usage: the export failed")
        return jsonify({"error": f"the export failed: {str(exc)[:300]}"}), 500
