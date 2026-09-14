"""Headless runner - the analyst on a CSV, no app, no UI.

    export OPENROUTER_API_KEY=...
    python -m analyst.cli --csv data.csv --question "..." --preset deep \
        --model meta/muse-spark-1.3 --effort medium --out ./analyst_runs

Writes <out>/threads/<thread>.json (the notebook), prints the two reports and
the replay line. `--parent <run_id>` continues or branches an existing thread.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path[:0] = [ROOT, os.path.join(ROOT, "delve")]

from analyst import Session, Budget, NotebookStore          # noqa: E402
from analyst.llm_openrouter import make_llm                  # noqa: E402


def describe(df: pd.DataFrame, max_cols: int = 80) -> str:
    lines = [f"{len(df):,} rows x {df.shape[1]} columns. Columns (name: dtype, non-null, example):"]
    for c in list(df.columns)[:max_cols]:
        s = df[c]
        ex = s.dropna().iloc[0] if s.notna().any() else ""
        lines.append(f"  {c}: {s.dtype}, {int(s.notna().sum()):,} non-null, e.g. {str(ex)[:40]}")
    if df.shape[1] > max_cols:
        lines.append(f"  ... {df.shape[1] - max_cols} more columns")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=False)
    ap.add_argument("--question", required=True)
    ap.add_argument("--preset", default="deep", choices=["quick", "deep", "adaptive"])
    ap.add_argument("--turns", type=int, default=None)
    ap.add_argument("--dollars", type=float, default=None)
    ap.add_argument("--model", default="meta/muse-spark-1.3")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--out", default="./analyst_runs")
    ap.add_argument("--thread", default=None)
    ap.add_argument("--parent", default=None, help="run id to continue or branch from")
    a = ap.parse_args()

    from kernel import PersistentKernel                      # delve/kernel.py, in-process
    df = pd.read_csv(a.csv) if a.csv else None
    kernel = PersistentKernel(df=df)
    factory = (lambda: PersistentKernel(df=df))
    store = NotebookStore(a.out)
    thread = a.thread or f"t{int(time.time())}"
    nb = store.load(thread)
    budget = Budget.preset(a.preset)
    if a.turns: budget.turns = a.turns
    if a.dollars: budget.dollars = a.dollars

    def emit(ev):
        kind = ev.get("type")
        if kind == "cell":
            print(f"\n=== cell {ev.get('cell_no') or '(failed)'} ===\n{ev['code']}\n--- output ---\n{(ev.get('stdout') or ev.get('error') or '')[:1500]}")
        elif kind in ("show", "names", "recall", "search"):
            print(f"\n=== {kind} ===\n{(ev.get('text') or '')[:600]}")
        elif kind == "question_to_user":
            print(f"\n=== QUESTION TO YOU ===\n{ev['text']}")
        elif kind == "report":
            print(f"\n=== TECHNICAL REPORT ===\n{ev['text']}")
        elif kind == "rewrite":
            print(f"\n=== PLAIN-LANGUAGE VERSION ===\n{ev['text']}")
        elif kind == "replay_status":
            print(f"\n=== REPLAY: {ev['status']} ===")
        if ev.get("note") and kind in ("cell", "error"):
            print(f"--- note ---\n{ev['note'][:800]}")

    session = Session(kernel, nb, make_llm(a.model, a.effort), store=store, emit=emit,
                      data_description=describe(df) if df is not None else "(no dataset attached)",
                      kernel_factory=factory)
    try:
        run = session.run(a.question, parent=a.parent, budget=budget)
    finally:
        kernel.cleanup()
    spent = sum(float(t.usage.get("cost", 0) or 0) for t in run.turns)
    print(f"\nrun {run.id} in thread {thread}: status={run.status}, turns={len(run.turns)}, cost=${spent:.2f}, replay={run.replay_status or '-'}")
    print(f"notebook: {store._file(thread)}")


if __name__ == "__main__":
    main()
