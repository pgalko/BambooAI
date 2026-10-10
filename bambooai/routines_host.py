"""The host's side of a routine (docs/ROUTINES_DESIGN.md, F1): propose - the chain read, the promoter called once,
its edits applied, the proposal for the dialog; create - the person's choices applied, run zero on the chain's data,
the routine stored with its first (or next) version. Pure over its arguments: the model call, the runner and the
store are handed in, so the path runs in a test with a scripted promoter and a local kernel.

The standing rule (DESIGN_CHECKLIST C5) holds for every string here that a model may read.
"""
from __future__ import annotations

import re
import time
from typing import Callable, Dict, List, Optional

from analyst import routines as rt
from analyst.notebook import Notebook, Run, split_sentences
from analyst.replay import assemble


class RoutineRefused(Exception):
    """A reason the person can read: why no routine was made from this chain."""


def describe_data(data: Optional[dict]) -> str:
    """The data as the promoter reads it: name, size, columns with their types, the range, the auxiliary files."""
    d = data or {}
    lines = []
    if d.get("name"):
        lines.append(f"File: {d['name']}")
    if d.get("source"):
        lines.append(f"Source: {d['source']}")
    cols = d.get("columns") or []
    size = f"{d['rows']:,} rows x {len(cols)} columns" if d.get("rows") is not None and cols else (f"{len(cols)} columns" if cols else "")
    if size:
        lines.append(f"`df`: {size}")
    if cols:
        lines.append("Columns (name: dtype): " + ", ".join(f"{c.get('name')}: {c.get('dtype', '')}" for c in cols[:200]))
    if d.get("date_range"):
        lines.append(f"Date range: {d['date_range']}")
    extra = d.get("extra") or {}
    if extra:
        lines.append("Load details: " + ", ".join(f"{k}: {v}" for k, v in extra.items()))
    if d.get("aux"):
        lines.append("Auxiliary files: " + ", ".join(str(a).split("/")[-1] for a in d["aux"]))
    return "\n".join(lines) or "(no description of the data is on record)"


def summary_of(run: Run) -> str:
    """The report's opening, one or two sentences: the first paragraph's prose, headings, quoted guard lines and
    tables left out (Notebook.conclusion skips a paragraph that opens with a heading line, and the replay's guard
    line stood for the answer)."""
    text = run.report or run.rewrite or ""
    for p in re.split(r"\n\s*\n", text):
        lines = [ln.strip() for ln in p.splitlines() if ln.strip() and not ln.strip().startswith(("#", ">", "|"))]
        if lines:
            out = " ".join(split_sentences(re.sub(r"\s+", " ", " ".join(lines)))[:2])
            return out if len(out) <= 420 else out[:417].rstrip() + "..."
    return ""


def _timeout(cells) -> int:
    took = sum(float(getattr(c, "elapsed", 0.0) or 0.0) for c in cells)
    return int(min(1800, max(300, 2 * took + 120)))


def _ledger(expected: List[dict]) -> List[str]:
    out = []
    for e in expected:
        line = e.get("label", "")
        if e.get("estimate") is not None:
            line += f": {e['estimate']}"
            if e.get("low") is not None and e.get("high") is not None:
                line += f" (95% CI {e['low']} to {e['high']})"
            if e.get("unit"):
                line += f" {e['unit']}"
            if e.get("direction"):
                line += f", {e['direction']}"
        out.append(f"- [cell {e['cell']}] " + line + (" - typed, not computed" if e.get("typed") else ""))
    return out


def data_state(run_data: Optional[dict], current: Optional[dict]) -> str:
    """same: the chain's frame is the one loaded now; gone: another frame, or none, is loaded; assumed: the chain
    predates the record, so the frame loaded now is taken for its data."""
    cur = (current or {}).get("df_id")
    if not run_data or not run_data.get("df_id"):
        return "assumed" if cur else "gone"
    return "same" if cur and str(cur) == str(run_data.get("df_id")) else "gone"


def propose(nb: Notebook, run_id: str, llm: Callable, current_data: Optional[dict] = None, emit: Optional[Callable] = None,
            routine: Optional[dict] = None, seat: str = "", model: str = "") -> dict:
    """Read the chain, call the promoter once (twice when its reply cannot be read), apply its edits, and return the
    proposal the dialog shows. Raises RoutineRefused with a readable reason."""
    run: Optional[Run] = nb.runs.get(str(run_id))
    if run is None:
        raise RoutineRefused("this chain is not in this thread's record")
    if run.status != "answered":
        raise RoutineRefused({"asked": "this chain ended with a question to you, not an answer", "failed": "this chain failed",
                              "stopped": "this chain was stopped", "running": "this chain is still running"}.get(run.status, f"this chain's status is {run.status!r}"))
    if not run.cells():
        raise RoutineRefused("this chain has no cells to run again (nothing was computed)")
    path = nb.path_cells(run.id)
    script, _order = assemble(path, run.report or "", own=run.cells())     # today's assembly, not the stored one: a chain from before the RESULT stub (2026-10-06) would stop on NameError
    header, body, tail, order = rt.split_script(script)
    if not order:
        raise RoutineRefused("this chain has no cells to run again (nothing was computed)")
    expected = rt.expected_results(path, order)
    figures = [c.cell_no for c in run.cells() if c.figures and c.cell_no in order]
    state = data_state(run.data, current_data)
    data = dict(run.data or {}) if state != "assumed" else dict(current_data or {})
    manifest = None
    if routine:
        cur = next((v for v in routine.get("versions", []) if v.get("number") == routine.get("current_version")), None)
        manifest = (cur or {}).get("manifest")
    summary = summary_of(run)
    user = rt.promoter_user(run.question, summary, describe_data(data), body, _ledger(expected), manifest)
    obj, usage, cost = None, {}, 0.0
    problem = ""
    for attempt in range(2):
        if emit:
            emit({"type": "turn_start", "turn": "routine", "quiet": True, "seat": seat, "model": model})
        t0 = time.time()
        text, usage = llm(rt.PROMOTER_SYSTEM, user if not attempt else user + "\n\n" + rt.PROMOTER_RETRY.format(problem=problem))
        cost += float((usage or {}).get("cost") or 0.0)
        try:
            obj = rt.parse_promoter(text)
        except ValueError as exc:
            problem = str(exc)
            obj = None
        if emit:
            emit({"type": "turn_end", "turn": "routine", "kind": "routine", "elapsed": round(time.time() - t0, 1), "cost": float((usage or {}).get("cost") or 0.0),
                  "peek": (f"{len(obj.get('inputs') or [])} input(s) proposed, {len(obj.get('edits') or [])} edit(s)" if obj else f"the reply could not be read ({problem})")})
        if obj is not None:
            break
    if obj is None:
        raise RoutineRefused(f"could not make a routine from this chain - the script was not understood ({problem})")
    edited, applied, failed = rt.apply_edits(body, obj.get("edits") or [])
    inputs, notes = rt.finish_inputs(obj.get("inputs") or [], edited, failed)
    kept_keys = {p["key"] for p in inputs}
    stray = {k for e in applied for k in rt._KEY_REF_RE.findall(str(e.get("replace") or ""))} - kept_keys
    if stray:                                           # an input left out after its edits applied: its edits go too
        edited = rt.strip_keys(edited, body, applied, stray)
        applied = [e for e in applied if not (set(rt._KEY_REF_RE.findall(str(e.get("replace") or ""))) & stray)]
    unknown = rt.unknown_keys(edited, inputs)
    if unknown:
        raise RoutineRefused("could not make a routine from this chain - the script reads an input that was not declared (" + ", ".join(unknown) + ")")
    name = str(obj.get("name") or "").strip()[:60] or (run.question or "").strip()[:60]
    return {"proposal_id": rt.new_id(), "thread_id": nb.thread_id, "chain_id": run.id, "name": name, "purpose": "", "question": run.question,
            "summary": summary, "data": data, "data_state": state, "source": rt.source_kind(data), "inputs": inputs, "notes": notes,
            "kept": [str(k) for k in (obj.get("kept") or [])][:12], "results": expected, "figures": {"count": sum(len(c.figures) for c in run.cells() if c.cell_no in figures), "cells": figures},
            "cells": len(order), "script": rt.join_script(header, edited, tail), "header": header, "tail": tail, "cells_text": edited, "cells_original": body,
            "applied": applied, "timeout": _timeout(path), "cost": round(cost, 4), "routine_id": routine.get("id") if routine else None,
            "routine_name": routine.get("name") if routine else None, "next_version": (routine.get("current_version", 1) + 1) if routine else None}


UNVERIFIED_LINE = "not verified: the analysis's data is no longer loaded, so the method was not checked - the first run will show whether it still runs"


def create(nb: Notebook, proposal: dict, choices: dict, runner: Optional[Callable], store: rt.RoutineStore, emit: Optional[Callable] = None,
           routine_id: Optional[str] = None) -> dict:
    """Apply the person's choices (name, purpose, inputs dropped, results dropped), run the method once on the chain's
    data, and store the routine (a new one, or the next version of `routine_id`). A method whose run zero does not
    reproduce the chain's lines is refused; with the data gone the routine is created unverified and says so."""
    name = (choices.get("name") or proposal.get("name") or "").strip()[:80] or "Routine"
    purpose = (choices.get("purpose") or "").strip()[:300]
    drop_inputs = {str(k) for k in (choices.get("drop_inputs") or [])}
    drop_results = {(int(r[0]), int(r[1])) for r in (choices.get("drop_results") or []) if isinstance(r, (list, tuple)) and len(r) == 2}
    inputs = [p for p in proposal["inputs"] if p["key"] not in drop_inputs]
    cells = rt.strip_keys(proposal["cells_text"], proposal["cells_original"], proposal["applied"], drop_inputs) if drop_inputs else proposal["cells_text"]
    unknown = rt.unknown_keys(cells, inputs)
    if unknown:
        raise RoutineRefused("the script still reads an input that was dropped (" + ", ".join(unknown) + ")")
    script = rt.join_script(proposal["header"], cells, proposal["tail"])
    results = [dict(r, dropped=((r["cell"], r["index"]) in drop_results)) for r in proposal["results"]]
    manifest = {"data": proposal["data"], "parameters": inputs, "results": results, "figures": proposal.get("figures") or {"count": 0, "cells": []}, "notes": proposal.get("notes") or []}
    now = time.time()
    run_zero = {"created": now, "status": "unverified", "line": UNVERIFIED_LINE, "verified": False, "results": [], "figures": 0, "data": proposal["data"], "inputs": rt.defaults_of(inputs)}
    stdout, figs = "", []
    if runner is not None and proposal.get("data_state") != "gone":
        if emit:
            emit({"type": "lookup_start", "kind": "routine", "query": name})
        t0 = time.time()
        try:
            stdout, err, figs, _generated = runner(rt.with_inputs(script, rt.defaults_of(inputs)), int(proposal.get("timeout") or 300))
        except Exception as exc:                                   # noqa: BLE001
            stdout, err, figs = "", f"the run could not start: {exc}", []
        got = rt.result_lines_in(stdout or "")
        status, line, diffs = rt.check_lines(results, got, err or "")
        if emit:
            emit({"type": "lookup", "kind": "routine", "query": name, "peek": line, "elapsed": round(time.time() - t0, 1)})
        if status != "reproduced":
            raise RoutineRefused(f"run zero on this chain's own data did not reproduce the analysis: {line}")
        run_zero.update({"status": status, "line": line, "verified": True, "results": got, "figures": len(figs or []), "elapsed": round(time.time() - t0, 1)})
    routine = store.load(routine_id) if routine_id else None
    if routine_id and routine is None:
        raise RoutineRefused("the routine this version was meant for no longer exists")
    if routine is None:
        routine = {"id": rt.new_id(), "name": name, "created": now, "purpose": purpose, "question": proposal.get("question", ""), "summary": proposal.get("summary", ""),
                   "origin": {"thread_id": str(nb.thread_id), "chain_id": str(proposal["chain_id"])}, "source": proposal.get("source", "file"), "current_version": 0, "versions": [], "runs": []}
        change_note = "first version"
    else:
        change_note = (choices.get("change_note") or "").strip()[:200] or "a new version"
        if choices.get("name"):
            routine["name"] = name
        if purpose:
            routine["purpose"] = purpose
    number = len(routine["versions"]) + 1
    routine["versions"].append({"number": number, "created": now, "promoted_from": {"thread_id": str(nb.thread_id), "chain_id": str(proposal["chain_id"])},
                                "script": script, "manifest": manifest, "change_note": change_note, "run_zero": run_zero})
    routine["current_version"] = number
    store.save(routine)
    try:
        store.save_run_files(routine["id"], f"v{number}_0", stdout or "", figs or [])
    except OSError:
        pass
    return {"routine": rt.RoutineStore.summary(routine), "version": number, "run_zero": run_zero, "name": routine["name"]}


# ----------------------------------------------------------------------------- a run on the data loaded now (F2)
def version_of(routine: dict, number: Optional[int] = None) -> dict:
    n = number or routine.get("current_version") or 1
    v = next((x for x in routine.get("versions", []) if x.get("number") == n), None)
    if v is None:
        raise RoutineRefused(f"this routine has no version {n}")
    return v


def run_tag(version: int, number: int) -> str:
    return f"v{version}_{number}"


def light_data(data: Optional[dict]) -> dict:
    d = data or {}
    return {"df_id": d.get("df_id"), "name": d.get("name", ""), "source": d.get("source", ""), "rows": d.get("rows"), "columns": len(d.get("columns") or []),
            "date_range": d.get("date_range"), "aux": [str(a).split("/")[-1] for a in (d.get("aux") or [])], "extra": d.get("extra") or {}}


def reference_run(routine: dict, version: dict, compare_with="previous") -> Tuple[Optional[int], Optional[List[dict]]]:
    """(run number, its result lines) this run is compared with: the preceding run of the version, else run zero;
    'zero' for run zero; a number for that run. None when there is nothing to compare with."""
    runs = [r for r in routine.get("runs", []) if r.get("version") == version.get("number")]
    rz = version.get("run_zero") or {}
    zero = (0, rz.get("results") or []) if rz.get("verified") else None
    if compare_with == "zero":
        return zero if zero else (None, None)
    if isinstance(compare_with, int) or (isinstance(compare_with, str) and compare_with.isdigit()):
        want = int(compare_with)
        if want == 0:
            return zero if zero else (None, None)
        r = next((x for x in routine.get("runs", []) if x.get("number") == want), None)
        return (r["number"], r.get("results") or []) if r else (None, None)
    done = [r for r in runs if r.get("status") in ("ran", "reproduced", "differed")]
    if done:
        return done[-1]["number"], done[-1].get("results") or []
    return zero if zero else (None, None)


def precheck(routine: dict, current_data: Optional[dict], runner: Optional[Callable], values: Optional[dict] = None, version_number: Optional[int] = None) -> dict:
    """What the run dialog shows before Run: whether data is loaded, whether it fits the routine's columns, and
    whether every chosen value of a choice input is in the data."""
    ver = version_of(routine, version_number)
    manifest = ver.get("manifest") or {}
    params = manifest.get("parameters") or []
    d = current_data or {}
    loaded = bool(d.get("df_id")) or bool(d.get("columns"))
    out = {"loaded": loaded, "data": light_data(d), "fit": None, "values_missing": [], "problems": [], "ok": False, "line": ""}
    if not loaded:
        out["line"] = "no data is loaded: load the data on the Data tab, then run"
        return out
    fit = rt.fit_check((manifest.get("data") or {}).get("columns") or [], d.get("columns") or [])
    out["fit"] = fit
    vals, problems = rt.coerce_values(params, values)
    out["problems"] = problems
    if fit["fits"] and runner is not None:
        checks = rt.value_checks(params, vals)
        if checks:
            try:
                stdout, err, _f, _g = runner(rt.precheck_script(checks), 120)
            except Exception as exc:                                   # noqa: BLE001
                stdout, err = "", str(exc)
            found = rt.read_precheck(stdout or "")
            out["values_missing"] = rt.missing_values(checks, found) if found is not None else ([f"the values could not be checked ({str(err).strip().splitlines()[-1][:120]})"] if err else [])
    out["ok"] = bool(fit["fits"]) and not out["values_missing"] and not problems
    out["line"] = fit["line"] + (("; " + "; ".join(out["values_missing"])) if out["values_missing"] else "") + (("; " + "; ".join(problems)) if problems else "")
    return out


def run(routine: dict, values: Optional[dict], current_data: Optional[dict], runner: Callable, store: rt.RoutineStore, emit: Optional[Callable] = None,
        compare_with="previous", version_number: Optional[int] = None) -> dict:
    """One run of the routine's version on the data loaded now: the checks (refused before anything runs), the
    script with the INPUTS block, the lines read by position, the status against the reference run, the comparison,
    the record stored (a failed run too). Returns the record with the printed output and the figures for the tabs."""
    ver = version_of(routine, version_number)
    vnum = ver.get("number", 1)
    manifest = ver.get("manifest") or {}
    params = manifest.get("parameters") or []
    expected = manifest.get("results") or []
    d = current_data or {}
    if not (d.get("df_id") or d.get("columns")):
        raise RoutineRefused("no data is loaded: load the data on the Data tab, then run")
    vals, problems = rt.coerce_values(params, values)
    if problems:
        raise RoutineRefused("; ".join(problems))
    name = d.get("name") or d.get("source") or "the data loaded now"
    if emit:
        emit({"type": "lookup_start", "kind": "check", "query": name})
    fit = rt.fit_check((manifest.get("data") or {}).get("columns") or [], d.get("columns") or [])
    if not fit["fits"]:
        if emit:
            emit({"type": "lookup", "kind": "check", "query": name, "peek": fit["line"]})
        raise RoutineRefused("the data does not fit the routine: " + fit["line"])
    checks = rt.value_checks(params, vals)
    if checks:
        stdout, err, _f, _g = runner(rt.precheck_script(checks), 120)
        found = rt.read_precheck(stdout or "")
        miss = rt.missing_values(checks, found) if found is not None else []
        if miss:
            if emit:
                emit({"type": "lookup", "kind": "check", "query": name, "peek": "; ".join(miss)})
            raise RoutineRefused("; ".join(miss))
    if emit:
        emit({"type": "lookup", "kind": "check", "query": name, "peek": fit["line"] + ("; the chosen values are in the data" if checks else "")})
    number = len(routine.get("runs", [])) + 1
    ref_number, ref_results = reference_run(routine, ver, compare_with)
    cells = (manifest.get("figures") or {}).get("cells")
    n_cells = len(re.findall(r"^# --- cell \d+ ---$", ver.get("script") or "", re.M))
    rz = ver.get("run_zero") or {}
    timeout = int(min(1800, max(300, 2 * float(rz.get("elapsed") or 0) + 120))) if rz.get("elapsed") else 600
    if emit:
        emit({"type": "lookup_start", "kind": "run", "query": f"run {number} · v{vnum} · {n_cells} cell{'s' if n_cells != 1 else ''}"})
    t0 = time.time()
    script = rt.with_inputs(ver.get("script") or "", vals)
    try:
        stdout, err, figs, generated = runner(script, timeout)
    except Exception as exc:                                           # noqa: BLE001
        stdout, err, figs, generated = "", f"the run could not start: {exc}", [], None
    elapsed = round(time.time() - t0, 1)
    got = rt.result_lines_in(stdout or "")
    status, line = rt.run_status(expected, got, err or "", ref_results, script)
    if emit:
        emit({"type": "lookup", "kind": "run", "query": f"run {number} · v{vnum} · {n_cells} cell{'s' if n_cells != 1 else ''}",
              "peek": f"{line} · {len(figs or [])} figure{'s' if len(figs or []) != 1 else ''} · {elapsed} s"})
    cmp = rt.compare_runs(expected, got, ref_results)
    if emit and ref_results is not None:
        ref_run = next((x for x in routine.get("runs", []) if x.get("number") == ref_number), None)
        when = _when(ref_run.get("created") if ref_run else rz.get("created"))
        emit({"type": "lookup", "kind": "compare", "query": f"with run {ref_number}" + (f" ({when})" if when else ""), "peek": cmp["line"]})
    now = time.time()
    record = {"number": number, "version": vnum, "created": t0, "finished": now, "elapsed": elapsed, "status": status, "line": line,
              "data": d, "inputs": vals, "results": got, "figures": len(figs or []), "stdout_chars": len(stdout or ""), "cells": n_cells,
              "against": ref_number, "comparison": cmp, "narrative": "", "error": (str(err).strip()[-2000:] if err else "")}
    summary = {k: record[k] for k in ("number", "version", "created", "finished", "elapsed", "status", "line", "inputs", "results", "figures", "against", "cells")}
    summary["data"] = light_data(d)
    summary["comparison"] = {k: cmp[k] for k in ("moved", "within", "changed", "missing", "compared", "line")}
    routine.setdefault("runs", []).append(summary)
    store.save(routine)
    tag = run_tag(vnum, number)
    store.save_run(routine["id"], tag, record)
    try:
        store.save_run_files(routine["id"], tag, stdout or "", figs or [])
    except OSError:
        pass
    return {"run": record, "summary": summary, "routine": rt.RoutineStore.summary(routine), "numbers": run_numbers(routine, vnum), "stdout": stdout or "", "figures": figs or [], "name": routine.get("name")}


def _when(ts) -> str:
    try:
        return time.strftime("%d %b", time.localtime(float(ts))) if ts else ""
    except (TypeError, ValueError, OverflowError):
        return ""


def run_numbers(routine: dict, version: Optional[int] = None) -> List[int]:
    """The runs a person can step through with the arrows: run zero of the current version, then every run."""
    ver = version or routine.get("current_version") or 1
    v = next((x for x in routine.get("versions", []) if x.get("number") == ver), None)
    out = [0] if v and (v.get("run_zero") or {}).get("verified") else []
    return out + [r["number"] for r in routine.get("runs", [])]


def run_view(routine: dict, store: rt.RoutineStore, number: int) -> dict:
    """A stored run as the main panes show it: the record, its printed output and figures, the routine's summary,
    the numbers to step through. Run zero is the current version's."""
    if int(number) == 0:
        ver = version_of(routine)
        rz = ver.get("run_zero") or {}
        if not rz.get("verified"):
            raise RoutineRefused("this version has no run zero (it was created unverified)")
        record = {"number": 0, "version": ver.get("number", 1), "created": rz.get("created"), "finished": rz.get("created"), "elapsed": rz.get("elapsed"),
                  "status": rz.get("status", "reproduced"), "line": rz.get("line", ""), "data": rz.get("data") or (ver.get("manifest") or {}).get("data") or {},
                  "inputs": rz.get("inputs") or {}, "results": rz.get("results") or [], "figures": rz.get("figures", 0), "cells": len(re.findall(r"^# --- cell \d+ ---$", ver.get("script") or "", re.M)),
                  "against": None, "comparison": rt.compare_runs((ver.get("manifest") or {}).get("results") or [], rz.get("results") or [], None), "narrative": "", "zero": True}
        tag = run_tag(ver.get("number", 1), 0)
    else:
        summary = next((x for x in routine.get("runs", []) if x.get("number") == int(number)), None)
        if summary is None:
            raise RoutineRefused(f"this routine has no run {number}")
        tag = run_tag(summary.get("version", 1), summary["number"])
        record = store.load_run(routine["id"], tag) or dict(summary)
    stdout, figs = store.run_files(routine["id"], tag)
    return {"run": record, "stdout": stdout, "figures": figs, "routine": rt.RoutineStore.summary(routine), "numbers": run_numbers(routine), "name": routine.get("name"),
            "manifest_results": [x for x in (version_of(routine, record.get("version")).get("manifest") or {}).get("results", []) if not x.get("dropped")]}
