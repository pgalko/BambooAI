#!/usr/bin/env python3
"""The reach tally: what the analyst's cells touched outside the data, over the thread store, per model (2026-10-28).

Reads every thread under storage/<user>/threads (the notebooks the app keeps) and, for the model names, the run logs under
logs/<user>/bambooai_run_log.json; prints a Markdown report to stdout. Nothing is sent anywhere and nothing is changed.

    python3 tools/reaches_report.py                      # the working directory's storage/ and logs/, the last 14 days
    python3 tools/reaches_report.py --days 30 --root /app
    python3 tools/reaches_report.py --all                # every run on the record

A run's reaches are the records the kernel kept per cell (analyst/reach.py): fetched and sent bytes by host, files
outside the data, environment names, programs; each marked whether the question asked for it. A refused cell is one
the executor did not run (the blacklist). The sandbox line is the box as the kernel saw it. Runs from before the record
(executor image v63 and earlier) count as runs and cells, with no reaches: the tally says how many.
"""
import argparse
import glob
import json
import os
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

from analyst import reach  # noqa: E402
from analyst.notebook import Notebook  # noqa: E402

NOT_ANALYST = {"rewriter", "reader", "reviewer", "coder", "promoter", "planner"}


def models_by_chain(logs_root):
    """chain id -> the model that ran its analysis, from the run logs: the most frequent model among the chain's calls that
    are not the rewrite, the reading or the review seats."""
    out = {}
    votes = defaultdict(Counter)
    for path in glob.glob(os.path.join(logs_root, "*", "bambooai_run_log.json")) + glob.glob(os.path.join(logs_root, "bambooai_run_log.json")):
        try:
            with open(path, encoding="utf-8") as fh:
                entries = json.load(fh)
        except Exception:                                   # noqa: BLE001
            continue
        for e in entries if isinstance(entries, list) else []:
            cid, model, agent = str(e.get("chain_id") or ""), str(e.get("model") or ""), str(e.get("agent") or "").lower()
            if cid and model and agent not in NOT_ANALYST:
                votes[cid][model] += 1
    for cid, c in votes.items():
        out[cid] = c.most_common(1)[0][0]
    return out


def fmt_n(n):
    return f"{n:,}"


def short_thread(tid):
    return tid[:4] + "…" if len(tid) > 6 else tid


def main(argv=None):
    ap = argparse.ArgumentParser(description="the reach tally over the thread store")
    ap.add_argument("--root", default=os.getcwd(), help="the folder holding storage/ and logs/ (default: the working directory)")
    ap.add_argument("--days", type=int, default=14, help="runs started within this many days (default 14)")
    ap.add_argument("--all", action="store_true", help="every run on the record")
    ap.add_argument("--limit", type=int, default=40, help="lines in the 'not asked for' list (default 40)")
    args = ap.parse_args(argv)
    since = 0 if args.all else time.time() - args.days * 86400
    storage = os.path.join(args.root, "storage")
    models = models_by_chain(os.path.join(args.root, "logs"))

    per_model = defaultdict(lambda: dict(runs=0, cells=0, fetched_asked=0, fetched_unasked=0, sent_asked=0, sent_unasked=0,
                                         files=0, env=0, process=0, refused=0, hosts=set(), blocked=0))
    unasked_lines, refused_words, sandboxes = [], Counter(), Counter()
    n_runs = n_cells = n_reaches = n_unasked = n_refused = n_unrecorded = 0
    users = 0
    for user_dir in sorted(glob.glob(os.path.join(storage, "*"))) + ([storage] if os.path.isdir(os.path.join(storage, "threads")) else []):
        tdir = os.path.join(user_dir, "threads")
        if not os.path.isdir(tdir):
            continue
        users += 1
        for path in sorted(glob.glob(os.path.join(tdir, "*.json"))):
            try:
                with open(path, encoding="utf-8") as fh:
                    nb = Notebook.from_dict(json.load(fh))
            except Exception:                               # noqa: BLE001
                continue
            for run in nb.runs.values():
                if float(run.created or 0) < since or not run.cells():
                    continue
                model = models.get(str(run.id), "(model not in the run logs)")
                m = per_model[model]
                n_runs += 1
                m["runs"] += 1
                if not run.sandbox:
                    n_unrecorded += 1
                else:
                    sandboxes[reach.sandbox_line(run.sandbox)] += 1
                for t in run.turns:
                    if t.kind != "cell":
                        continue
                    if t.cell_no is not None:
                        n_cells += 1
                        m["cells"] += 1
                    if getattr(t, "refused", ""):
                        n_refused += 1
                        m["refused"] += 1
                        refused_words[t.refused] += 1
                    for r in getattr(t, "reaches", None) or []:
                        if r.get("kind") == "more":
                            continue
                        n_reaches += 1
                        asked = bool(r.get("asked"))
                        if not asked:
                            n_unasked += 1
                        kind = r.get("kind")
                        if kind == "net":
                            if r.get("blocked"):
                                m["blocked"] += 1
                            sent = int(r.get("out") or 0) >= 4 * int(r.get("in") or 0) and int(r.get("out") or 0) > 0
                            key = ("sent" if sent else "fetched") + ("_asked" if asked else "_unasked")
                            m[key] += 1
                            if not asked:
                                m["hosts"].add(str(r.get("host") or r.get("ip") or "?"))
                        elif kind == "file":
                            m["files"] += 1
                        elif kind == "env":
                            m["env"] += 1
                        elif kind == "process":
                            m["process"] += 1
                        if not asked:
                            when = time.strftime("%Y-%m-%d %H:%M", time.localtime(float(t.created or run.created or 0)))
                            unasked_lines.append((when, model.split("/")[-1], short_thread(nb.thread_id), f"cell {t.cell_no}" if t.cell_no is not None else "attempt",
                                                  reach.line(r), (run.question or "").strip().replace("\n", " ")[:60]))

    span = "every run on the record" if args.all else f"last {args.days} days"
    print(f"# Reaches outside the data — {span} ({users} user folder{'s' if users != 1 else ''})        tools/reaches_report.py, {time.strftime('%Y-%m-%d')}\n")
    share = f" ({n_reaches / n_cells * 100:.1f} % of cells)" if n_cells else ""
    print(f"runs {fmt_n(n_runs)} · cells {fmt_n(n_cells)} · reaches {fmt_n(n_reaches)}{share} · not asked for {fmt_n(n_unasked)} · refused {fmt_n(n_refused)}"
          + (f" · {fmt_n(n_unrecorded)} run{'s' if n_unrecorded != 1 else ''} from before the record" if n_unrecorded else "") + "\n")
    if per_model:
        w = max(len(m) for m in per_model) + 2
        print(f"{'model':<{w}}{'runs':>6}{'cells':>8}   fetched (asked / not)   sent (asked / not)   files   env   programs   refused   hosts not asked for")
        for model, m in sorted(per_model.items(), key=lambda kv: -kv[1]["runs"]):
            hosts = " · ".join(sorted(m["hosts"])[:4]) + (" …" if len(m["hosts"]) > 4 else "")
            print(f"{model:<{w}}{m['runs']:>6}{fmt_n(m['cells']):>8}   {m['fetched_asked']:>3} / {m['fetched_unasked']:<3}               {m['sent_asked']:>3} / {m['sent_unasked']:<3}"
                  f"           {m['files']:>3}   {m['env']:>3}   {m['process']:>4}       {m['refused']:>3}       {hosts}")
    print()
    if unasked_lines:
        print("not asked for, by cell")
        for when, model, tid, cell, text, q in sorted(unasked_lines, reverse=True)[:args.limit]:
            print(f"  {when}  {model:<24} thread {tid:<8} {cell:<9} {text:<52} question: \"{q}\"")
        if len(unasked_lines) > args.limit:
            print(f"  … {len(unasked_lines) - args.limit} more")
        print()
    if refused_words:
        print("refused (the blacklist)\n  " + " · ".join(f"{w} {n}" for w, n in refused_words.most_common()) + "\n")
    if len(sandboxes) == 1:
        print(f"sandbox, every run: {next(iter(sandboxes))}")
    elif sandboxes:
        print("sandbox:")
        for line, n in sandboxes.most_common():
            print(f"  {line}   ({n} run{'s' if n != 1 else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
