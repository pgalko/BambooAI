"""The host's side of a routine (docs/ROUTINES_DESIGN.md):
  - propose (F1): the chain read, the promoter called once, its edits applied, the proposal for the dialog;
  - create (F1): the person's choices applied, the routine stored with its first (or next) version, and the proof on
    the chain's own data - run zero, the shorter run, the trials on smaller pieces (prove_method, §22);
  - run (F2): the data loaded now made to fit, the method run a statement at a time, its lines laid against the
    tracked ones, the comparison, the record (§22);
  - Fill (§14.3): the routine run on each window of a set interval.
Pure over its arguments: the model call, the runner and the store are handed in, so the path runs in a test with a
scripted promoter and a local kernel.

The standing rule (DESIGN_CHECKLIST C5) holds for every string here that a model may read.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from analyst import routines as rt
from analyst.notebook import Notebook, Run, split_sentences
from analyst.replay import assemble
from analyst.report import cited_cells

logger = logging.getLogger(__name__)

INTERVALS = ("day", "week", "month", "year")      # a run's calendar unit; none recorded is custom
DONE = ("ran", "reproduced")                      # the statuses of a run whose lines count: in the history, and as a reference


class RoutineRefused(Exception):
    """A reason the person can read: why no routine was made from this chain."""


# ----------------------------------------------------------------------------- what the promoter and the dialogs read of a chain and its data
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
    keys = [str(c.get("name")) for c in cols if rt.key_column(c.get("name"))]
    if keys:                                                   # §18: what identifies rows, sessions or groups of this data - other data has its own
        lines.append("Key columns (they identify rows, sessions or groups of this data; other data has its own values): " + ", ".join(keys))
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


def _ledger(expected: List[dict]) -> List[str]:
    """The expected lines as the promoter reads them, numbered from 1: its pick names a line by this number (§15.1)."""
    out = []
    for n, e in enumerate(expected, 1):
        line = e.get("label", "")
        if e.get("estimate") is not None:
            line += f": {e['estimate']}"
            if e.get("low") is not None and e.get("high") is not None:
                line += f" (95% CI {e['low']} to {e['high']})"
            if e.get("unit"):
                line += f" {e['unit']}"
            if e.get("direction"):
                line += f", {e['direction']}"
        out.append(f"{n}. [cell {e['cell']}] " + line + (" - typed, not computed" if e.get("typed") else ""))
    return out


def data_facts(data: Optional[dict]) -> str:
    """The data in a few words for the Save-as-routine dialog's checklist (§17): rows, columns, the auxiliary kinds by name."""
    d = data or {}
    parts = []
    if d.get("rows") is not None:
        parts.append(f"{int(d['rows']):,} rows")
    if d.get("columns"):
        parts.append(f"{len(d['columns'])} columns")
    kinds: List[str] = []
    for path in d.get("aux") or []:
        name = rt.KIND_NAMES.get(rt.aux_kind(str(path)))
        if name and name not in kinds:
            kinds.append(name)
    if kinds:
        parts.append(", ".join(kinds))
    return " · ".join(parts)


def data_state(run_data: Optional[dict], current: Optional[dict]) -> str:
    """same: the chain's data is the data loaded now - the same frame, or the same content loaded again (the same file
    uploaded in a new session; notebook.same_data, 2026-10-12); gone: other data, or none, is loaded; assumed: the
    chain predates the record, so the frame loaded now is taken for its data."""
    from analyst.notebook import same_data
    cur = (current or {}).get("df_id")
    if not run_data or not run_data.get("df_id"):
        return "assumed" if cur else "gone"
    return "same" if cur and same_data(run_data, current) else "gone"


def _dates_of(d: dict) -> Tuple[Optional[str], Optional[str]]:
    load = d.get("load") or {}
    if load.get("start_date") and load.get("end_date"):
        return str(load["start_date"]), str(load["end_date"])
    m = re.match(r"^\s*(\d{4}-\d{2}-\d{2})\s*(?:to|->|-|→)\s*(\d{4}-\d{2}-\d{2})\s*$", str(d.get("date_range") or ""))
    return (m.group(1), m.group(2)) if m else (None, None)


def date_column_of(data: Optional[dict]) -> str:
    """The frame's date column, from a data record: the one recorded at promotion, else the first date column on
    record; '' without one."""
    return str(((data or {}).get("span") or {}).get("column") or "") or rt.date_column((data or {}).get("columns") or [])


AUXSHAPE_MARK = "AUXSHAPE:"
SPAN_MARK = "SPAN:"
DAYS_MARK = "DAYS:"


def shape_probe_script(paths: List[str], date_column: str = "") -> str:
    """A script, run at promotion on the chain's data, that prints after AUXSHAPE: each auxiliary file's columns with
    their types and its row count - the shape a run is later made to fit - and after SPAN: the first and last dates
    of the frame's date column, the period the data itself covers (an input that equals it follows the data). The
    rows are the table's, read whole (2026-10-16: a line count had put a passage's every line on the CHECK row -
    "the context file: 1,499 rows where the original had 2,080" of 978 passages)."""
    return ("import json as _j, os as _os\n"
            "import pandas as _pd\n"
            "_out = {}\n"
            "for _p in " + json.dumps([str(p) for p in paths]) + ":\n"
            "    try:\n"
            "        _fr = _pd.read_csv(_p) if _p.lower().endswith('.csv') else _pd.read_parquet(_p)\n"
            "        _out[_p] = {'columns': [{'name': str(c), 'dtype': str(_fr[c].dtype)} for c in _fr.columns], 'rows': int(len(_fr))}\n"
            "    except Exception as _exc:\n"
            "        _out[_p] = {'error': str(_exc)[:200]}\n"
            "print(" + repr(AUXSHAPE_MARK + " ") + " + _j.dumps(_out))\n"
            "_col = " + json.dumps(str(date_column or "")) + "\n"
            "if _col and 'df' in globals() and df is not None and _col in df.columns:\n"
            "    try:\n"
            "        _s = _pd.to_datetime(df[_col], errors='coerce').dropna()\n"
            "        if len(_s):\n"
            "            print(" + repr(SPAN_MARK + " ") + " + _j.dumps({'column': _col, 'first': str(_s.min().date()), 'last': str(_s.max().date())}))\n"
            "    except Exception:\n"
            "        pass\n")


def days_script(column: str) -> str:
    """A script that prints after DAYS: the days the frame has rows on, by its date column."""
    return ("import json as _j\nimport pandas as _pd\n"
            "_s = _pd.to_datetime(df[" + json.dumps(str(column)) + "], errors='coerce').dropna()\n"
            "print(" + repr(DAYS_MARK + " ") + " + _j.dumps({'days': sorted(_s.dt.normalize().drop_duplicates().dt.strftime('%Y-%m-%d'))}))\n")


def read_marked(stdout: str, mark: str) -> Optional[dict]:
    """The JSON object printed after `mark` on its own line (the last such line)."""
    for ln in reversed((stdout or "").splitlines()):
        if ln.strip().startswith(mark):
            try:
                found = json.loads(ln.strip()[len(mark):].strip())
                return found if isinstance(found, dict) else None
            except ValueError:
                return None
    return None


def record_data_shape(data: dict, runner: Optional[Callable]) -> dict:
    """The data record with each auxiliary file's columns (`aux_shape`) and the period the frame covers (`span`: the
    date column, its first and last dates), read through the runner; left as it is when nothing can be read now (the
    record then binds by name alone, and no input follows the data)."""
    paths = [str(p) for p in (data or {}).get("aux") or [] if p]
    col = rt.date_column((data or {}).get("columns") or [])
    if runner is None or (not paths and not col) or (data.get("aux_shape") and data.get("span")):
        return data
    try:
        stdout, err, _f, _g = runner(shape_probe_script(paths if not data.get("aux_shape") else [], col if not data.get("span") else ""), 120)
        found = read_marked(stdout or "", AUXSHAPE_MARK)
        span = read_marked(stdout or "", SPAN_MARK)
    except Exception as exc:                                           # noqa: BLE001
        logger.warning("the data's shape could not be read: %s", exc)
        found, span = None, None
    if found or span:
        data = dict(data)
        if found:
            data["aux_shape"] = {p: v for p, v in found.items() if isinstance(v, dict) and "columns" in v}
        if span and span.get("first") and span.get("last"):
            data["span"] = {"column": str(span.get("column") or col), "first": str(span["first"]), "last": str(span["last"])}
    return data


def derive_inputs(inputs: List[dict], data: Optional[dict]) -> List[dict]:
    """The inputs with the ones that only restate the period the data covers marked `derived` (2026-10-11: the first
    run that completed on a new window carried the original window in its labels and titles, typed, and the promoter
    had made it an input the person had to retype beside the load window). A date window whose default is the
    frame's first and last dates follows the data (`span`: written from the frame at each run); one whose default is
    the load window follows the load (`window`: written from the run's data record). Nothing else is derived."""
    d = data or {}
    span = d.get("span") or {}
    first_last = [str(span.get("first") or ""), str(span.get("last") or "")] if span.get("first") and span.get("last") else None
    start, end = _dates_of(d)
    window = [start, end] if start and end else None
    out = []
    for p in inputs or []:
        q = dict(p)
        q.pop("derived", None)
        if q.get("type") == "date_window" and isinstance(q.get("default"), (list, tuple)) and len(q["default"]) == 2:
            default = [str(x) for x in q["default"]]
            if first_last and default == first_last:
                q["derived"] = "span"
            elif window and default == window:
                q["derived"] = "window"
        out.append(q)
    return out


def derived_window_values(params: List[dict], data: Optional[dict]) -> Dict[str, object]:
    """The values of the inputs that follow the load window, from this run's data record."""
    start, end = _dates_of(data or {})
    if not (start and end):
        return {}
    return {p["key"]: [start, end] for p in params or [] if p.get("derived") == "window"}


def span_inputs(params: List[dict], data: Optional[dict]) -> List[Tuple[str, str]]:
    """(key, date column) for the inputs that follow the frame's own dates."""
    col = date_column_of(data)
    return [(p["key"], col) for p in params or [] if p.get("derived") == "span" and col]


# ----------------------------------------------------------------------------- Save as routine: the proposal (F1)
def time_allowed(took: float) -> int:
    """What a script may take when it is run again, in seconds, from what it took: twice that plus two minutes, within
    five and thirty minutes."""
    return int(min(1800, max(300, 2 * float(took) + 120)))


def propose(nb: Notebook, run_id: str, llm: Callable, current_data: Optional[dict] = None, emit: Optional[Callable] = None,
            routine: Optional[dict] = None, seat: str = "", model: str = "", runner: Optional[Callable] = None, instruction: str = "") -> dict:
    """Read the chain, call the promoter once (twice when its reply cannot be read), apply its edits, and return the
    proposal the dialog shows. `instruction` (§15.6) is the person's line on what the runs should track: the promoter
    answers it line by line under "tracked", the lines it gives are compared whatever its pick says, and a quantity it
    gives no line for is said in a note. Raises RoutineRefused with a readable reason."""
    instruction = " ".join((instruction or "").split())[:rt.MAX_INSTRUCTION]
    run: Optional[Run] = nb.runs.get(str(run_id))
    if run is None:
        raise RoutineRefused("this chain is not in this thread's record")
    if run.status != "answered":
        raise RoutineRefused({"asked": "this chain ended with a question to you, not an answer", "failed": "this chain failed",
                              "stopped": "this chain was stopped", "running": "this chain is still running"}.get(run.status, f"this chain's status is {run.status!r}"))
    if not run.cells():
        raise RoutineRefused("this chain has no cells to run again (nothing was computed)")
    # the method is the cells computed on this chain's data (2026-10-12): a follow-up asked after the data changed stands
    # on earlier chains whose cells ran on other data - context in its ledger, not part of its computation, and not
    # reproducible on this data (the first live case: an hour-of-day chain on one window, the window replaced by a
    # routine's run, a temperature follow-up; run zero re-ran the hour-of-day cells on the new window and refused)
    path = nb.computed_cells(run.id)
    earlier = nb.earlier_on_other_data(run.id)
    script, _order = assemble(path, run.report or "", own=run.cells())     # today's assembly, not the stored one: a chain from before the RESULT stub (2026-10-06) would stop on NameError
    header, chain, tail, chain_order = rt.split_script(script)
    if not chain_order:
        raise RoutineRefused("this chain has no cells to run again (nothing was computed)")
    figures = [c.cell_no for c in run.cells() if c.figures and c.cell_no in chain_order]
    nfig = sum(len(c.figures) for c in run.cells() if c.cell_no in figures)
    # the promoter reads the chain without its exploration - a row named by its identifier and printed about, a check by
    # hand, a table shown: the statements no result line or figure rests on. The version stores the chain as written
    # with the edits made here (method_cells)
    body, pruned, lines_cut, problem = rt.prune_cells(chain, figures)
    if problem or len(pruned) == len(chain_order):        # a cell that cannot be read, or nothing to rest on (no RESULT line, no figure): the chain as it is
        body, pruned, lines_cut = chain, [], 0
    order = [n for n in chain_order if n not in pruned]
    expected = rt.expected_results(path, order)
    step = emit or (lambda ev: None)                      # the dialog's checklist (§17): a line as each step passes
    step({"type": "step", "step": "chain", "detail": f"{len(chain_order)} cell{'s' if len(chain_order) != 1 else ''} · {len(expected)} result{'s' if len(expected) != 1 else ''} · {nfig} figure{'s' if nfig != 1 else ''}"})
    state = data_state(run.data, current_data)
    data = dict(run.data or {}) if state != "assumed" else dict(current_data or {})
    if state in ("same", "assumed"):
        step({"type": "step", "step": "data", "state": "running"})
        data = record_data_shape(data, runner)            # the data is still there: the auxiliary files' columns and the frame's period go on record
    step({"type": "step", "step": "data", "detail": data_facts(data) if state != "gone" else "no longer loaded — the routine will be made unverified"})
    manifest = None
    if routine:
        cur = next((v for v in routine.get("versions", []) if v.get("number") == routine.get("current_version")), None)
        manifest = (cur or {}).get("manifest")
    summary = summary_of(run)
    cited = [n for n in cited_cells(run.report or "") if n in order]     # the cells the report read the answer from (§15.5)
    user = rt.promoter_user(run.question, summary, describe_data(data), body, _ledger(expected), manifest, cited, instruction)
    obj, usage, cost = None, {}, 0.0
    problem, note, cut, cuts = "", "", False, 0
    why = ""                                                   # why the model is asked again, when it is: unreadable (§17), identifiers (§18) or the instruction unanswered (§15.6)
    for attempt in range(2):
        if emit:
            emit({"type": "turn_start", "turn": "routine", "quiet": True, "seat": seat, "model": model})
        step({"type": "step", "step": "model", "state": "running", "again": bool(attempt), "detail": why if attempt else ""})
        t0 = time.time()
        text, usage = llm(rt.PROMOTER_SYSTEM, user if not attempt else user + "\n\n" + note)
        cost += float((usage or {}).get("cost") or 0.0)
        cut = bool((usage or {}).get("truncated"))
        cuts += int(cut)
        try:
            obj = rt.parse_promoter(text)
        except ValueError as exc:
            # a reply cut at the seat's token allowance is said as such (2026-10-10: a seat tuned for long reasoning spent the
            # allowance thinking, twice; "invalid JSON" was true but not what happened)
            problem = ("the reply was cut off at the token limit" + (f" ({len(text.strip())} characters arrived)" if (text or "").strip() else " (nothing arrived but reasoning)")) if cut else str(exc)
            obj = None
        keyed = rt.key_inputs(obj.get("inputs")) if obj is not None else []
        if emit:
            emit({"type": "turn_end", "turn": "routine", "kind": "routine", "elapsed": round(time.time() - t0, 1), "cost": float((usage or {}).get("cost") or 0.0),
                  "peek": (f"{len(obj.get('inputs') or [])} input(s) proposed, {len(obj.get('edits') or [])} edit(s)" + (f" - identifiers among them ({', '.join(keyed)})" if keyed else "")
                           if obj else f"the reply could not be read ({problem})")})
        if obj is not None and keyed and attempt == 0:        # the floor (§18): identifiers of this data are not inputs - asked again once, with the reason
            note, obj, why = rt.PROMOTER_KEYS.format(inputs=", ".join(keyed)), None, "identifiers were proposed as inputs"
            continue
        if obj is not None and instruction and obj.get("tracked") is None and attempt == 0:     # the instruction unanswered (§15.6): asked again once
            note, obj, why = rt.PROMOTER_TRACKED, None, "the instruction was not answered"
            continue
        if obj is not None:
            step({"type": "step", "step": "model"})
            step({"type": "step", "step": "proposal", "state": "running"})
            break
        # a reply cut with nothing but reasoning is asked again too (2026-10-12: the same prompt, sent again by the person's
        # Try again, came back whole - the reasoning's length varies from call to call; the note asks for it brief)
        note = (rt.PROMOTER_CUT_EMPTY if cut and not (text or "").strip() else
                rt.PROMOTER_CUT.format(got=len((text or "").strip())) if cut else rt.PROMOTER_RETRY.format(problem=problem))
    if obj is not None and keyed:                             # the second reply still picks by identifier
        raise RoutineRefused("could not make a routine from this chain - the method picks rows of this data by their identifiers ("
                             + ", ".join(keyed) + "), which other data will not have; ask the analyst to pick them by a rule, then save again")
    if obj is not None and obj.get("unfit"):
        raise RoutineRefused("could not make a routine from this chain - the method names rows of this data that other data will not have ("
                             + (rt.unfit_line(obj["unfit"]) or "see the cells") + "); ask the analyst to pick them by a rule, then save again")
    if obj is None:
        if cut:
            raise RoutineRefused("could not make a routine from this chain - the model's reply was cut off at its token limit"
                                 + (" (nothing arrived but reasoning)" if not (text or "").strip() else (" twice" if cuts == 2 else ""))
                                 + "; the seat that proposes routines (Promoter in the model config) needs a larger max_tokens or a lower reasoning effort")
        raise RoutineRefused(f"could not make a routine from this chain - the script was not understood ({problem})")
    edited, applied, failed = rt.apply_edits(body, obj.get("edits") or [])
    inputs, notes = rt.finish_inputs(obj.get("inputs") or [], edited, failed)
    notes.extend("recomputed from the data, not typed: " + str(c)[:200] for c in (obj.get("recomputed") or [])[:6] if str(c).strip())      # §18: the dialog says it
    if earlier:
        nos = [c.cell_no for r in earlier for c in r.cells() if c.cell_no is not None]
        theirs = f" (cells {nos[0]}-{nos[-1]})" if len(nos) > 1 else (f" (cell {nos[0]})" if nos else "")
        own_cells = f"cells {order[0]}-{order[-1]}" if len(order) > 1 else f"cell {order[0]}"
        notes.append(f"this chain continues {len(earlier)} earlier chain{'s' if len(earlier) > 1 else ''} of the thread that ran on other data{theirs}: "
                     f"the method is this chain's own {own_cells}, computed on the data it ran on")
    inputs = derive_inputs(inputs, data)                  # a window that is the data's own period follows the data from now on
    inputs, own_notes = rt.own_columns(inputs, data)      # a choice over a column the script computes is not looked for in the data
    notes.extend(own_notes)
    kept_keys = {p["key"] for p in inputs}
    stray = {k for e in applied for k in rt._KEY_REF_RE.findall(str(e.get("replace") or ""))} - kept_keys
    if stray:                                           # an input left out after its edits applied: its edits go too
        edited = rt.strip_keys(edited, body, applied, stray)
        applied = [e for e in applied if not (set(rt._KEY_REF_RE.findall(str(e.get("replace") or ""))) & stray)]
    unknown = rt.unknown_keys(edited, inputs)
    if unknown:
        raise RoutineRefused("could not make a routine from this chain - the script reads an input that was not declared (" + ", ".join(unknown) + ")")
    name = str(obj.get("name") or "").strip()[:60] or (run.question or "").strip()[:60]
    # the lines the instruction reached are compared whatever the pick says (§15.6); a quantity it reached no line for is said
    tracked, missing = rt.tracked_lines(expected, obj.get("tracked")) if instruction else ({}, [])
    results = rt.pick_results(expected, obj.get("compare"), tracked)      # the lines a run compares, named (§15.1); every line without a usable pick
    notes.extend(f"Not computed in this analysis, so it can’t be tracked: {q}" for q in missing)
    if instruction and obj.get("tracked") is None:
        notes.append("The custom instructions were not applied this time; try Update the list again.")
    return {"proposal_id": rt.new_id(), "thread_id": nb.thread_id, "chain_id": run.id, "name": name, "purpose": "", "question": run.question, "instruction": instruction,
            "summary": summary, "data": data, "data_state": state, "source": rt.source_kind(data), "inputs": inputs, "notes": notes,
            "kept": [str(k) for k in (obj.get("kept") or [])][:12], "results": results, "figures": {"count": nfig, "cells": figures},
            "cells": len(chain_order), "header": header, "tail": tail,
            "cells_text": edited, "cells_original": body, "pruned_lines": lines_cut, "cells_chain": chain,      # the promoter's view after and before its edits; the chain as written (method_cells)
            "applied": applied, "timeout": time_allowed(sum(float(getattr(c, "elapsed", 0.0) or 0.0) for c in path)), "cost": round(cost, 4), "routine_id": routine.get("id") if routine else None,
            "routine_name": routine.get("name") if routine else None, "next_version": (routine.get("current_version", 1) + 1) if routine else None}


# ----------------------------------------------------------------------------- Save as routine: the routine stored (F1)
UNVERIFIED_LINE = "not verified: the analysis's data is no longer loaded, so the method was not checked - the first run will show whether it still runs"
VERIFYING_LINE = "verifying: the method is being run on the chain's own data"


def method_cells(proposal: dict, drop_inputs: set) -> str:
    """The cells a version stores: the chain as written, with the promoter's edits. The edits were found in the
    promoter's view - the chain without its exploration - so they are applied to the chain with the view's dropped
    lines held out (each lands where it landed there, however often the chain repeats the fragment) and the lines
    are put back. Where the view dropped nothing, or an edit does not land on the chain, the view is the text."""
    view = rt.strip_keys(proposal["cells_text"], proposal["cells_original"], proposal["applied"], drop_inputs) if drop_inputs else proposal["cells_text"]
    if not (proposal.get("pruned_lines") and proposal.get("cells_chain")):
        return view
    held, lines = rt.held_out(proposal["cells_chain"], (proposal.get("figures") or {}).get("cells") or [])
    text, applied, failed = rt.apply_edits(held, proposal.get("applied") or [])
    if failed:
        return view
    return rt.put_back(rt.strip_keys(text, held, applied, drop_inputs) if drop_inputs else text, lines)


def create(nb: Notebook, proposal: dict, choices: dict, runner: Optional[Callable], store: rt.RoutineStore, emit: Optional[Callable] = None,
           routine_id: Optional[str] = None, background: bool = False, runs_root: str = "routines") -> dict:
    """Apply the person's choices (name, purpose, inputs dropped, results dropped) and store the routine (a new one, or
    the next version of `routine_id`); then prove the method on the chain's own data (prove_method): run zero, the
    shorter run, the trials. In the foreground (the default, as the tests and the library use it) a method whose run
    zero does not reproduce is refused and not kept. In the background the routine is stored at once as *verifying*,
    the result carries `verify`, a callable the host runs in a thread, and the outcome lands on the record when it is
    in; a run is refused until it has settled, and after a verdict that is not reproduced. With the chain's data gone
    the routine is created unverified and says so. `runs_root` is the folder the runs' own folders live under on the
    runner's side; the trials write theirs there and remove it."""
    name = (choices.get("name") or proposal.get("name") or "").strip()[:80] or "Routine"
    purpose = (choices.get("purpose") or "").strip()[:300]
    instruction = " ".join(str(choices.get("instruction") or "").split())[:rt.MAX_INSTRUCTION]       # the person's line on what to track, kept for the next version
    drop_inputs = {str(k) for k in (choices.get("drop_inputs") or [])}
    # the lines left out of the comparison: the whole set as the page sends it (the promoter's pick with the person's
    # changes); without the key, the proposal's pick stands
    drop_results = ({(int(r[0]), int(r[1])) for r in choices["drop_results"] if isinstance(r, (list, tuple)) and len(r) == 2}
                    if isinstance(choices.get("drop_results"), (list, tuple)) else {(r["cell"], r["index"]) for r in proposal["results"] if r.get("dropped")})
    inputs = [p for p in proposal["inputs"] if p["key"] not in drop_inputs]
    cells = method_cells(proposal, drop_inputs)
    unknown = rt.unknown_keys(cells, inputs)
    if unknown:
        raise RoutineRefused("the script still reads an input that was dropped (" + ", ".join(unknown) + ")")
    results = [dict(r, dropped=((r["cell"], r["index"]) in drop_results)) for r in proposal["results"]]
    manifest = {"data": proposal["data"], "parameters": inputs, "results": results, "figures": proposal.get("figures") or {"count": 0, "cells": []}, "notes": proposal.get("notes") or []}
    now = time.time()
    run_zero = {"created": now, "status": "unverified", "line": UNVERIFIED_LINE, "verified": False, "results": [], "figures": 0, "data": proposal["data"], "inputs": rt.defaults_of(inputs)}
    verifying = runner is not None and proposal.get("data_state") != "gone"
    timeout = int(proposal.get("timeout") or 300)
    routine = store.load(routine_id) if routine_id else None
    if routine_id and routine is None:
        raise RoutineRefused("the routine this version was meant for no longer exists")
    if routine is None:
        routine = {"id": rt.new_id(), "shape": rt.SHAPE, "name": name, "created": now, "purpose": purpose, "question": proposal.get("question", ""), "summary": proposal.get("summary", ""),
                   "origin": {"thread_id": str(nb.thread_id), "chain_id": str(proposal["chain_id"])}, "source": proposal.get("source", "file"), "current_version": 0, "versions": [], "runs": [],
                   "instruction": instruction}
        change_note = "first version"
    else:
        change_note = (choices.get("change_note") or "").strip()[:200] or "a new version"
        if choices.get("name") and name != routine["name"]:           # renamed only when the person typed another name
            routine["name"] = name
        if purpose:
            routine["purpose"] = purpose
        if "instruction" in choices:                                   # the dialog's box as it stood, emptied included; a caller without the key leaves it
            routine["instruction"] = instruction
    number = len(routine["versions"]) + 1
    version = {"number": number, "created": now, "promoted_from": {"thread_id": str(nb.thread_id), "chain_id": str(proposal["chain_id"])},
               "script": rt.join_script(proposal["header"], cells, proposal["tail"]), "manifest": manifest, "change_note": change_note, "run_zero": run_zero}
    trial_dir = f"{runs_root.rstrip('/')}/{routine['id']}/{run_tag(number, 0)}_trial"

    def prove(emit_: Optional[Callable]) -> dict:
        return prove_method(name, version, runner, timeout, trial_dir, emit_)
    files = {"stdout": "", "figs": []}
    if verifying and not background:
        proof = prove(emit)
        if proof["status"] != "reproduced":
            raise RoutineRefused(f"run zero on this chain's own data did not reproduce the analysis: {proof['line']}")
        files = settle_proof(version, proof)
    elif verifying:
        run_zero.update({"status": "verifying", "line": VERIFYING_LINE})
    routine["versions"].append(version)
    routine["current_version"] = number
    store.save(routine)
    try:
        store.save_run_files(routine["id"], run_tag(number, 0), files["stdout"], files["figs"])
    except OSError:
        pass
    made = {"routine": rt.RoutineStore.summary(routine), "version": number, "run_zero": run_zero, "name": routine["name"], "tried": version.get("tried") or []}
    if verifying and background:
        rid = routine["id"]

        def verify() -> dict:
            """The proof behind the dialog, written on the stored version when it is in. No pane rows - nobody is
            watching a pane for it (a row emitted after the dialog's stream closed would land in the next request's);
            the toast and the manager's chip say what happened. Nothing is written when the routine was deleted
            meanwhile."""
            proof = prove(None)
            r = store.load(rid)
            v = next((x for x in (r or {}).get("versions", []) if x.get("number") == number), None) if r else None
            if v is not None:
                kept = settle_proof(v, proof)
                store.save(r)
                try:
                    store.save_run_files(rid, run_tag(number, 0), kept["stdout"], kept["figs"])
                except OSError:
                    pass
            return proof
        made["verify"] = verify
    return made


# ----------------------------------------------------------------------------- the method through the runner, a statement at a time (§22)
RETRY_PAUSE = 2.0                                  # seconds before a script that could not be carried out is tried once more
WATCH_MAX = 12                                     # the most columns a run reports the empty share of


def _call_runner(runner: Callable, script: str, timeout: int, run_dir: str = ""):
    """The runner with the run's folder when it takes one (the instance's run_script does; a test's may not)."""
    try:
        import inspect
        takes_dir = len(inspect.signature(runner).parameters) >= 3
    except (TypeError, ValueError):
        takes_dir = False
    return runner(script, timeout, run_dir) if takes_dir and run_dir else runner(script, timeout)


def _transport(err: str) -> bool:
    """Whether a runner's error says the script could not be carried out - the executor not reached, a connection
    dropped - rather than that it stopped: nothing of a traceback in it, and no time limit hit."""
    text = str(err or "")
    return bool(text.strip()) and not ("TIMEOUT" in text.upper() or "timed out" in text.lower()) and "Traceback" not in text and "Error on line" not in text and 'File "<' not in text


def carry_out(runner: Callable, script: str, timeout: int, run_dir: str = "") -> Tuple[str, str, list, Optional[list]]:
    """One script through the runner: (the printed output, the error, the figures, the files written). A script that
    could not be carried out (_transport) is tried once more after RETRY_PAUSE."""
    stdout, err, figs, generated = "", "", [], None
    for attempt in range(2):
        try:
            stdout, err, figs, generated = _call_runner(runner, script, timeout, run_dir)
        except Exception as exc:                                       # noqa: BLE001
            stdout, err, figs, generated = "", f"the run could not start: {exc}", [], None
        if attempt or not _transport(err):
            break
        logger.info("routine: a script could not be carried out (%s) - once more", str(err).strip().splitlines()[-1][:200])
        time.sleep(RETRY_PAUSE)
    return stdout or "", str(err or ""), list(figs or []), generated


def run_method(script: str, runner: Callable, timeout: int, run_dir: str = "", only: Optional[List[int]] = None, watch: Optional[dict] = None) -> dict:
    """The executed text through the runner a statement at a time (rt.stepwise) and read back (rt.read_run), with what
    the runner returned beside it: error, figs, generated, elapsed."""
    t0 = time.time()
    stdout, err, figs, generated = carry_out(runner, rt.stepwise(script, only, watch), timeout, run_dir)
    out = rt.read_run(stdout)
    out.update({"error": err, "figs": figs, "generated": generated, "elapsed": round(time.time() - t0, 1)})
    return out


def watch_of(version: dict) -> dict:
    """The frame's columns whose empty share a run of this version reports: those the method's code names, the first
    WATCH_MAX of them, counted by the groups of the frame's key column when it has one ({columns, by})."""
    columns = [str(c.get("name")) for c in ((version.get("manifest") or {}).get("data") or {}).get("columns") or [] if c.get("name") is not None]
    by = next((c for c in columns if rt.key_column(c)), "")
    named = rt.names_in(rt.split_script(version.get("script") or "")[1])
    return {"columns": [c for c in columns if c in named and c != by][:WATCH_MAX], "by": by}


def places_hold(version: dict) -> bool:
    """Whether the places the version keeps - each line's `at`, the shorter run's statements - are places in the
    script as it reads now: the mark taken when they were learnt (`steps`) is still the script's."""
    return bool(version.get("steps")) and version["steps"] == rt.steps_key(version.get("script") or "")


def run_steps(version: dict) -> Optional[List[int]]:
    """The statements a run of this version executes: the shorter run that stood at Save (`lean.steps`) while its
    places hold; else every statement (None)."""
    steps = (version.get("lean") or {}).get("steps")
    return [int(j) for j in steps] if steps and places_hold(version) else None


# ----------------------------------------------------------------------------- the proof at Save: run zero, the shorter run, the trials (§22.7)
TRIAL_UNITS = ("day", "week", "month")             # the calendar units Save tries a method on, inside the analysis's own window


def verify_zero(name: str, version: dict, runner: Callable, timeout: int, emit: Optional[Callable] = None) -> dict:
    """Run zero: the method once on the chain's own data, every statement, its inputs at their defaults; its lines
    against the chain's. Returns {status, line, verified, results (laid against the manifest's lines), at (each
    line's place, when reproduced), figures, elapsed, stdout, figs, gaps}: reproduced (verified), or differed / failed
    with the line that says how."""
    manifest = version.get("manifest") or {}
    expected = manifest.get("results") or []
    if emit:
        emit({"type": "lookup_start", "kind": "routine", "query": name})
    run = run_method(rt.with_inputs(version["script"], (version.get("run_zero") or {}).get("inputs") or {}), runner, timeout, watch=watch_of(version))
    status, line = rt.check_zero(expected, run, run["error"])
    placed = rt.place_lines([{k: v for k, v in e.items() if k != "at"} for e in expected], run)
    if emit:
        emit({"type": "lookup", "kind": "routine", "query": name, "peek": line, "elapsed": run["elapsed"]})
    return {"status": status, "line": line, "verified": status == "reproduced", "results": placed["results"], "at": placed["at"] if status == "reproduced" else None,
            "figures": len(run["figs"]), "elapsed": run["elapsed"], "stdout": run["stdout"], "figs": run["figs"], "gaps": run["gaps"]}


def check_lean(version: dict, zero: dict, runner: Callable, timeout: int) -> dict:
    """The shorter run, held to run zero: only the statements the tracked lines and the figures rest on
    (rt.needed_steps) are run, and the run stands when nothing stops, every tracked line comes back as run zero
    printed it and the figures are the same pictures - or run zero's own figures differ from one run to the next,
    which no code can be held to. Returns {steps: the statements to run (None: every one), line, elapsed: [every
    statement's, the shorter run's]}."""
    manifest = version.get("manifest") or {}
    expected = [dict(e, at=at) for e, at in zip(manifest.get("results") or [], zero["at"] or [])]
    script = rt.with_inputs(version["script"], (version.get("run_zero") or {}).get("inputs") or {})
    cells = rt.split_script(version["script"])[1]
    figure_cells = (manifest.get("figures") or {}).get("cells") or []
    tracked = {i for i, e in enumerate(expected) if not e.get("dropped") and e.get("at")}
    of = len(rt.read_steps(cells)[0])
    out = {"steps": None, "line": "every statement runs: nothing to leave out", "elapsed": [zero.get("elapsed"), None]}
    only = rt.needed_steps(cells, {expected[i]["at"][0] for i in tracked}, figure_cells) if (tracked or figure_cells) else None
    if only is None or len(only) >= of:
        return out
    run = run_method(script, runner, timeout, only=only)
    why = ""
    if run["error"] or run["stopped"] or run["skipped"] or not run["stepwise"]:
        why = "it stopped (" + (rt.error_line(run["error"]) or (run["stopped"][0]["error"] if run["stopped"] else "a statement was skipped"))[:160] + ")"
    else:
        got = rt.place_lines(expected, run)["results"]
        off = next((i for i in sorted(tracked) if not rt.same_numbers(got[i], zero["results"][i])), None)
        if off is not None:
            why = f"a tracked line differs ([cell {expected[off].get('cell')}] {str(expected[off].get('label') or '')[:50]}: {zero['results'][off].get('estimate')} -> {got[off].get('estimate')})"
        else:
            same, how = rt.same_figures(zero["figs"], run["figs"])
            if not same and rt.same_figures(zero["figs"], run_method(script, runner, timeout)["figs"])[0]:
                why = "the figures differ (" + how + ")"
    if why:
        out["line"] = "every statement runs: the shorter run did not hold - " + why
        return out
    out.update({"steps": only, "line": f"runs {len(only)} of {of} statements", "elapsed": [zero.get("elapsed"), run["elapsed"]]})
    return out


def trial_windows(data: Optional[dict], days: Optional[List[str]] = None) -> List[Tuple[str, str, str]]:
    """The pieces Save tries a method on: the latest complete day, week (Monday to Sunday) and month inside the
    window the analysis was made on that hold rows (`days`: the days the frame has rows on; not known, the latest
    complete ones) - [(unit, start, end)] as ISO days - each only when it is shorter than the window. Nothing for
    data without a window, or from a source whose runs have no intervals."""
    import datetime as _dt
    d = data or {}
    start, end = _dates_of(d)
    if rt.source_kind(d) != "intervals" or not (start and end):
        return []
    try:
        s, e = _dt.date.fromisoformat(start), _dt.date.fromisoformat(end)
    except ValueError:
        return []
    one = _dt.timedelta(days=1)

    def units(unit):                                                   # the complete units inside the window, the latest first
        if unit == "day":
            b = e - one
            while b >= s:
                yield b, b
                b -= one
        elif unit == "week":
            b = e - (e.weekday() + 1) % 7 * one                        # the last Sunday on or before the window's end
            while b - 6 * one >= s:
                yield b - 6 * one, b
                b -= 7 * one
        else:
            b = e if (e + one).day == 1 else e.replace(day=1) - one    # the last month that ends inside the window
            while b.replace(day=1) >= s:
                yield b.replace(day=1), b
                b = b.replace(day=1) - one
    out = []
    for unit in TRIAL_UNITS:
        for a, b in units(unit):
            if (b - a) < (e - s) and (days is None or any(a.isoformat() <= x <= b.isoformat() for x in days)):
                out.append((unit, a.isoformat(), b.isoformat()))
                break
    return out


def try_method(version: dict, runner: Callable, timeout: int, run_dir: str) -> List[dict]:
    """The trials: the method run on each piece of trial_windows, cut from the chain's own data as a fill cuts a unit
    from its span, with the inputs at their defaults. Nothing is recorded as a run. Returns one entry per piece:
    {interval, window, status, line, came, of} - how many of the tracked lines came back with a number. Nothing
    without a date column to cut by."""
    manifest = version.get("manifest") or {}
    data = manifest.get("data") or {}
    column, span = date_column_of(data), _dates_of(data)
    if not column or not trial_windows(data):
        return []
    days = (read_marked(carry_out(runner, days_script(column), 120)[0], DAYS_MARK) or {}).get("days")
    out = []
    for unit, start, end in trial_windows(data, days):
        d = dict(data, load=dict(data.get("load") or {}, start_date=start, end_date=end, cached_from=list(span)), date_range=f"{start} to {end}")
        vals = dict((version.get("run_zero") or {}).get("inputs") or {})
        vals.update(derived_window_values(manifest.get("parameters") or [], d))
        try:
            got = attempt(version, d, vals, runner, run_dir, timeout)
            status, line = rt.run_status(manifest.get("results") or [], got["results"], got["run"], got["run"]["error"], None)
        except Exception as exc:                                       # noqa: BLE001 - a trial that cannot be made says so and the others go on
            got, status, line = {"results": []}, "failed", f"could not be tried: {exc}"
        tracked = [i for i, e in enumerate(manifest.get("results") or []) if not e.get("dropped") and e.get("estimate") is not None]
        came = sum(1 for i in tracked if i < len(got["results"]) and got["results"][i].get("estimate") is not None)
        out.append({"interval": unit, "window": [start, end], "status": status, "line": line, "came": came, "of": len(tracked)})
    if out:                                                            # the trials' files are no run's: their folder goes
        try:
            _call_runner(runner, rt.remove_script(run_dir), 60)
        except Exception:                                              # noqa: BLE001
            pass
    return out


def prove_method(name: str, version: dict, runner: Callable, timeout: int, trial_dir: str, emit: Optional[Callable] = None) -> dict:
    """What Save proves about a method, on the chain's own data: run zero (every statement; the chain's lines
    reproduced), then - when it reproduced - the shorter run (check_lean) and the trials on smaller pieces
    (try_method). Returns run zero's verdict with `steps` (the mark of the statements the places are among), `lean`
    and `tried` beside it; settle_proof writes it on the version."""
    proof = verify_zero(name, version, runner, timeout, emit)
    proof.update({"steps": "", "lean": None, "tried": []})
    if proof["status"] != "reproduced":
        return proof
    proof["steps"] = rt.steps_key(version["script"])
    proof["lean"] = check_lean(version, proof, runner, timeout)
    manifest = version.get("manifest") or {}
    settled = dict(version, steps=proof["steps"], lean=proof["lean"], manifest=dict(manifest, results=[dict(e, at=at) for e, at in zip(manifest.get("results") or [], proof["at"] or [])]))
    proof["tried"] = try_method(settled, runner, timeout, trial_dir)
    return proof


def settle_proof(version: dict, proof: dict) -> dict:
    """The proof on the version: run zero's verdict and lines; when it reproduced, each line's place and the mark of
    the statements they are among, the empty shares of the chain's own data, the shorter run (and its time as what
    a run takes), the trials. Returns the printed output and the figures to keep as run zero's ({stdout, figs})."""
    rz = version["run_zero"]
    rz.update({k: proof[k] for k in ("status", "line", "verified", "results", "figures", "elapsed")})
    if proof["status"] == "reproduced":
        manifest = version["manifest"]
        for e, at in zip(manifest.get("results") or [], proof["at"] or []):
            e["at"] = at
        manifest["data"] = dict(manifest.get("data") or {}, gaps=proof.get("gaps") or {})
        version.update({k: proof[k] for k in ("steps", "lean", "tried")})
        if (proof["lean"] or {}).get("steps") and proof["lean"]["elapsed"][1] is not None:
            rz["elapsed"] = proof["lean"]["elapsed"][1]
    return {"stdout": proof.get("stdout") or "", "figs": proof.get("figs") or []}


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
    start, end = _dates_of(d)
    return {"df_id": d.get("df_id"), "name": d.get("name", ""), "source": d.get("source", ""), "rows": d.get("rows"), "columns": len(d.get("columns") or []),
            "date_range": d.get("date_range"), "aux": [str(a).split("/")[-1] for a in (d.get("aux") or [])], "extra": d.get("extra") or {},
            "subject": rt.subject_of_record(d),          # whose data (2026-10-30): the history and the comparisons stay within one subject's runs
            "window": [start, end] if start and end else None}      # and when: the window the run asked for (a cut run's, not the cached load's)


def load_plan(routine: dict, version_number: Optional[int] = None) -> dict:
    """How a run loads its data, from the version's data record: the source and, per source, what the original load
    asked for - the window's length, the metrics and auxiliary kinds; the race; the sports and subjects; the file."""
    d = (version_of(routine, version_number).get("manifest") or {}).get("data") or {}
    load = d.get("load") or {}
    extra = d.get("extra") or {}
    # a record whose load says "cache" (from before 2026-10-12, when a frame taken from the Dataset cache was recorded so) is
    # the cached frame's own source: the loader's details then come from the data record and its extra
    src = rt.source_kind(dict(d, source=(load.get("source") if load.get("source") != "cache" else None) or d.get("source")))
    aux = [str(p) for p in d.get("aux") or []]
    plan = {"source": src, "name": d.get("name") or "", "aux": aux, "aux_kinds": [rt.aux_kind(p) for p in aux], "rows": d.get("rows"),
            "columns": len(d.get("columns") or []), "date_range": d.get("date_range")}
    start, end = _dates_of(d)
    if start and end:
        try:
            days = (time.mktime(time.strptime(end, "%Y-%m-%d")) - time.mktime(time.strptime(start, "%Y-%m-%d"))) / 86400.0
            plan["window_days"] = int(round(days))
        except ValueError:
            pass
        plan["start"], plan["end"] = start, end
    plan["subject"] = rt.subject_of_record(d)             # the origin's subject (2026-10-30): the run dialog's default athlete
    if src == "intervals":
        plan["metrics"] = list(load.get("metrics") or extra.get("metrics") or [])
        # the kinds a load can be asked for: the codes are never asked, the pass behind a load with context makes them
        # (docs/CONTEXT_DESIGN.md F3, 2026-10-14: a routine made from a chain that read the words loads them again)
        plan["aux_kinds"] = [k for k in (load.get("aux_kinds") or plan["aux_kinds"]) if k in rt.LOAD_KINDS["intervals"]]
    elif src == "endura":
        plan["race_id"] = load.get("race_id") or extra.get("race_id")
        plan["race_title"] = load.get("race_title") or extra.get("race_title") or ""
        plan["aux_kinds"] = [k for k in (load.get("aux_kinds") or plan["aux_kinds"]) if k in rt.LOAD_KINDS["endura"]]
    elif src == "sweatstack":
        plan["sports"] = list(load.get("sports") or extra.get("sports") or [])
        plan["metrics"] = list(load.get("metrics") or extra.get("metrics") or [])
        plan["users"] = list(load.get("users") or [])
    return plan


def cut_window(ver: dict, current_data: Optional[dict]) -> Optional[dict]:
    """The window a run on a cached load is cut to (2026-10-11): when the page says the load came from a cached load
    around it (`load.cached_from`), {start, end, column} - the window asked and the frame's date column; None when
    nothing is to be cut."""
    d = current_data or {}
    load = d.get("load") or {}
    if not load.get("cached_from") or not (load.get("start_date") and load.get("end_date")):
        return None
    col = date_column_of((ver.get("manifest") or {}).get("data")) or rt.date_column(d.get("columns") or [])
    return {"start": str(load["start_date"]), "end": str(load["end_date"]), "column": col}


def prepare(ver: dict, current_data: Optional[dict], runner: Optional[Callable], run_dir: str) -> dict:
    """A run's data made to fit the recorded shape, laid out as the method expects (2026-10-15): every recorded auxiliary
    path exists under the run's folder - a mirror of the recorded layout - holding this load's file of that kind (a copy;
    with the missing columns added when one lacks columns; cut to the window on a cached load around it; an empty table
    for one this load lacks), the executed text with every path under the datasets folder moved under the run's folder,
    and the prelude that conforms `df`, makes sure of the files and writes the inputs that follow the frame's own dates."""
    rec = (ver.get("manifest") or {}).get("data") or {}
    d = current_data or {}
    binding = rt.bind_aux(rec.get("aux") or [], d.get("aux") or [])
    shape_rec = rec.get("aux_shape") or {}
    columns = {p: [c.get("name") for c in (shape_rec.get(p) or {}).get("columns") or []] for p in (rec.get("aux") or [])}
    shape, note = None, ""
    cut = cut_window(ver, d)
    if runner is not None and (binding["map"] or binding["absent"]):
        try:
            stdout, err, _f, _g = runner(rt.shape_script(binding["map"], columns, run_dir, binding["absent"], cut), 180)
            shape = rt.read_shape(stdout or "")
            if shape is None and err:
                note = f"the auxiliary files could not be prepared ({str(err).strip().splitlines()[-1][:160]})"
        except Exception as exc:                                       # noqa: BLE001
            note = f"the auxiliary files could not be prepared ({exc})"
    # the mirror: each recorded path under the run's folder, whether or not the probe wrote it (the prelude makes sure of
    # what is not there), so a recorded name is never rewritten as a cache path and folder + name resolves
    bound = {old: rt.mirror_path(run_dir, old) for old in binding["map"]}
    placeholders = {old: rt.mirror_path(run_dir, old) for old in binding["absent"]}
    sources = dict(binding["map"])                                    # recorded path -> this load's file, for the record
    # a run on a cached load around the window asked: each bound file is cut to the window - by the probe above, whose rows
    # the CHECK row reports (2026-10-16), and again by the prelude - and written at its mirror path; the executed text
    # names the mirror, never the cached file
    cut_files: Dict[str, dict] = {}
    if cut:
        for old, src_path in binding["map"].items():
            new = bound[old]
            by, col = rt.cut_rule(src_path)
            cut_files[new] = {"source": src_path, "columns": columns.get(old) or [], "by": by, "column": col}
        cut["files"] = cut_files
    # the folder the method's paths live under: the datasets folder of the recorded files, else the folder of the first of them
    ddir = rt.datasets_dir_of(rec.get("aux") or []) or rt.datasets_dir_of(d.get("aux") or []) or os.path.dirname(str((rec.get("aux") or [""])[0]).replace("\\", "/"))
    script, subs = rt.bind_script(ver.get("script") or "", bound, run_dir, ddir, placeholders)
    subs = [(old, new, ("cut" if new in cut_files else kind)) for old, new, kind in subs]
    # what the prelude makes sure of: every recorded file at its mirror path (from this load's file, or an empty table),
    # and any other cache file the text reads, copied under the run's folder
    files = [(bound[old], sources[old], columns.get(old) or [], "cut" if bound[old] in cut_files else "bound") for old in binding["map"]]
    files += [(placeholders[old], "", columns.get(old) or [], "placeholder") for old in binding["absent"]]
    files += [(new, old, [], "cache") for old, new, kind in subs if kind == "cache"]
    # the words the method reads (2026-10-16): CTX over the run's own context and codes files - the mirror copies, cut
    # to the window on a cached load, an empty table for one this load lacks - never the files loaded now
    by_kind = {rt.aux_kind(old): new for old, new in list(bound.items()) + list(placeholders.items())}
    context = (by_kind.get("context") or "", by_kind.get("codes") or "")
    logger.info("routine run: %d file(s) bound, %d absent (%s), %d substitution(s) in the executed text%s%s%s", len(binding["map"]), len(binding["absent"]),
                ", ".join(rt.aux_kind(p) for p in binding["absent"]) or "-", len(subs), ("; " + note) if note else "",
                (f"; cut to {cut['start']} → {cut['end']} by {cut['column'] or '?'}, {len(cut_files)} file(s)") if cut else "",
                "; CTX over the run's context file" if context[0] else "")
    return {"binding": binding, "bound": bound, "placeholders": placeholders, "sources": sources, "shape": shape, "script": script, "subs": subs, "note": note, "cut": cut, "datasets_dir": ddir,
            "prelude": rt.conform_prelude(rec.get("columns") or [], files, span_inputs((ver.get("manifest") or {}).get("parameters") or [], rec), cut, context)}


def aux_line(binding: dict, shape: Optional[dict] = None) -> str:
    """The auxiliary files in a sentence: which recorded ones this load lacks (the method will see empty tables). The
    codes file is not said absent when the context file this load has holds no passages (the pass writes no codes for a
    window without words; shape_sentences says "no passages in this window" there), 2026-10-14."""
    absent = [rt.aux_kind(p) for p in (binding or {}).get("absent") or []]
    if "codes" in absent and rt.context_empty(binding, shape):
        absent = [k for k in absent if k != "codes"]
    if not absent:
        return ""
    names = ", ".join(k[5:] if k.startswith("file:") else k for k in absent)
    return f"{names} absent in this data - the method will see {'an empty table' if len(absent) == 1 else 'empty tables'} there"


def zero_subject(version: dict) -> str:
    """Whose data run zero ran on: the version's own data record's subject id ('' when it names none)."""
    return str(rt.subject_of_record((version.get("manifest") or {}).get("data")).get("id") or "")


def same_subject(run: dict, subject_id: str) -> bool:
    """Whether a run's summary is on this subject's data: by id; a run without a subject matches no subject and the
    subject-less (an upload's runs compare among themselves)."""
    return str(((run.get("data") or {}).get("subject") or {}).get("id") or "") == str(subject_id or "")


def reference_run(routine: dict, version: dict, compare_with="previous", subject_id: Optional[str] = None,
                  interval: Optional[str] = None, window: Optional[Tuple[str, str]] = None) -> Tuple[Optional[int], Optional[List[dict]]]:
    """(run number, its result lines) this run is compared with: the preceding run of the version, else run zero;
    'zero' for run zero; a number for that run. None when there is nothing to compare with. With `subject_id` (2026-10-30:
    a coach's athletes), 'previous' is the preceding run on that subject's data, and run zero stands in only when it
    ran on that subject's - the trend never crosses athletes, and a run zero whose subject was not recorded (before
    the subject was kept) is nobody's but the subject-less runs' (an upload's, a race's). A run on a set interval
    (§14.1) is compared with the one before it: the latest earlier run of the same interval on the same subject, by
    its window's end - never a custom run, nor run zero; the first on a subject has nothing before it."""
    runs = [r for r in routine.get("runs", []) if r.get("version") == version.get("number")]
    if interval:
        before = [r for r in runs if r.get("status") in DONE and r.get("interval") == interval and same_subject(r, subject_id or "")
                  and (((r.get("data") or {}).get("window") or [None, None])[1] or "") < (window or ("", ""))[0]]
        if not before:
            return None, None
        last = max(before, key=lambda r: (((r.get("data") or {}).get("window") or ["", ""])[1], int(r.get("number") or 0)))
        return last["number"], last.get("results") or []
    rz = version.get("run_zero") or {}
    zero = (0, rz.get("results") or []) if rz.get("verified") else None
    zero_own = zero if subject_id is None or zero_subject(version) == str(subject_id) else None
    if compare_with == "zero":
        return zero_own if zero_own else (None, None)
    if isinstance(compare_with, int) or (isinstance(compare_with, str) and compare_with.isdigit()):
        want = int(compare_with)
        if want == 0:
            return zero if zero else (None, None)
        r = next((x for x in routine.get("runs", []) if x.get("number") == want), None)
        return (r["number"], r.get("results") or []) if r else (None, None)
    done = [r for r in runs if r.get("status") in DONE and not r.get("interval") and (subject_id is None or same_subject(r, subject_id))]
    if done:
        return done[-1]["number"], done[-1].get("results") or []
    return zero_own if zero_own else (None, None)


def zero_holds(ver: dict) -> str:
    """Why a version may not run yet, or at all (2026-10-15): run zero still verifying behind the dialog, or a verdict
    that the method did not reproduce the chain's lines on its own data - the refusal creation used to give, kept at
    the run instead; '' when the version may run (reproduced, or unverified because the data was gone)."""
    rz = ver.get("run_zero") or {}
    status = str(rz.get("status") or "")
    if status == "verifying":
        return "the routine is still being verified on its chain's own data - run it when it has settled"
    if status in ("differed", "failed"):
        return f"run zero on this chain's own data did not reproduce the analysis ({rz.get('line') or status}) - the method is not run on other data; delete the routine, or make it again from the chain"
    return ""


def precheck(routine: dict, current_data: Optional[dict], runner: Optional[Callable], values: Optional[dict] = None, version_number: Optional[int] = None) -> dict:
    """What the run dialog shows before Run: whether data is loaded, whether it fits the routine's columns, and
    whether every chosen value of a choice input is in the data."""
    ver = version_of(routine, version_number)
    manifest = ver.get("manifest") or {}
    params = rt.own_columns(manifest.get("parameters") or [], manifest.get("data"))[0]   # a routine made before 2026-10-15 may still declare one
    d = current_data or {}
    loaded = bool(d.get("df_id")) or bool(d.get("columns"))
    out = {"loaded": loaded, "data": light_data(d), "fit": None, "values_missing": [], "values_notes": [], "problems": [], "ok": False, "line": ""}
    held = zero_holds(ver)
    if held:
        out["line"] = held
        return out
    if not loaded:
        out["line"] = "no data is loaded: load the data on the Data tab, then run"
        return out
    fit = rt.fit_check((manifest.get("data") or {}).get("columns") or [], d.get("columns") or [])
    out["fit"] = fit
    binding = rt.bind_aux((manifest.get("data") or {}).get("aux") or [], d.get("aux") or [])
    out["aux"] = {"absent": [rt.aux_kind(p) for p in binding["absent"]], "bound": {rt.aux_kind(k): str(v).split("/")[-1] for k, v in binding["map"].items()}, "line": aux_line(binding)}
    out["differences"] = rt.shape_sentences(manifest.get("data") or {}, d, None, binding)      # the frame's rows against the original's; the files' at the run
    vals, problems = rt.coerce_values(params, values)
    out["problems"] = problems
    if fit["fits"] and runner is not None:
        checks = rt.value_checks(params, vals)
        if checks:
            try:
                stdout, err, _f, _g = runner(rt.precheck_script(checks, d.get("aux") or [], cut_window(ver, d)), 120)
            except Exception as exc:                                   # noqa: BLE001
                stdout, err = "", str(exc)
            found = rt.read_precheck(stdout or "")
            if found is not None:
                out["values_missing"], out["values_notes"] = rt.value_verdict(params, vals, found)
            else:
                out["values_missing"] = [f"the values could not be checked ({str(err).strip().splitlines()[-1][:120]})"] if err else []
    out["ok"] = bool(fit["fits"]) and not out["values_missing"] and not problems
    out["line"] = fit["line"] + (("; " + "; ".join(out["differences"])) if out["differences"] and fit["fits"] else "") + (("; " + out["aux"]["line"]) if out["aux"]["line"] else "") + (("; " + "; ".join(out["values_missing"])) if out["values_missing"] else "") \
        + (("; " + "; ".join(out["values_notes"])) if out["values_notes"] else "") + (("; " + "; ".join(problems)) if problems else "")
    return out


def attempt(ver: dict, d: dict, vals: Dict[str, object], runner: Callable, run_dir: str, timeout: int, prep: Optional[dict] = None) -> dict:
    """The method once on data `d`: the data made to fit (prepare, unless `prep` is handed in), the executed text run
    a statement at a time - the version's shorter run when it has one - and its lines laid against the manifest's,
    by their places while those hold, else by position. Returns {prep, script, run (rt.read_run with the runner's
    error, figs, generated, elapsed), results, at}."""
    prep = prep or prepare(ver, d, runner, run_dir)
    script = rt.with_inputs(prep["script"], vals, prep["prelude"])
    run_ = run_method(script, runner, timeout, run_dir, only=run_steps(ver), watch=watch_of(ver))
    expected = (ver.get("manifest") or {}).get("results") or []
    placed = rt.place_lines(expected if places_hold(ver) else [{k: v for k, v in e.items() if k != "at"} for e in expected], run_)
    return {"prep": prep, "script": script, "run": run_, "results": placed["results"], "at": placed["at"]}


def run_timeout(ver: dict) -> int:
    """What a run of this version may take (time_allowed), from what run zero took with every statement - a version
    whose places no longer hold runs them all; ten minutes when run zero did not run."""
    took = ((ver.get("lean") or {}).get("elapsed") or [None])[0] or (ver.get("run_zero") or {}).get("elapsed")
    return time_allowed(took) if took else 600


def stopped_of(got: dict) -> List[dict]:
    """The statements that stopped in a run, as its record keeps them: the cell, the line in it, the statement's code,
    the error, and how many later statements were not run for resting on it."""
    stopped = got["run"]["stopped"]
    if not stopped:
        return []
    steps = rt.read_steps(rt.split_script(got["script"])[1])[0]
    skipped = [origin for _j, _cell, origin in got["run"]["skipped"]]
    return [{"cell": s["cell"], "line": s.get("line"), "code": (steps[s["step"]].source if s["step"] < len(steps) else "")[:4000], "error": s["error"],
             "skipped": skipped.count(s["step"])} for s in stopped]


def run(routine: dict, values: Optional[dict], current_data: Optional[dict], runner: Callable, store: rt.RoutineStore, emit: Optional[Callable] = None,
        compare_with="previous", version_number: Optional[int] = None, run_dir: str = "", interval: Optional[str] = None) -> dict:
    """One run of the routine's version on the data loaded now: the checks (refused before anything runs), the method
    a statement at a time (attempt), the status, the comparison with the reference run, the record stored. Returns
    the record with the printed output and the figures for the tabs. `interval`: the calendar unit the window is -
    the record keeps it and the reference is the one before."""
    ver = version_of(routine, version_number)
    held = zero_holds(ver)
    if held:
        raise RoutineRefused(held)
    vnum = ver.get("number", 1)
    manifest = ver.get("manifest") or {}
    params = rt.own_columns(manifest.get("parameters") or [], manifest.get("data"))[0]
    expected = manifest.get("results") or []
    d = current_data or {}
    if not (d.get("df_id") or d.get("columns")):
        raise RoutineRefused("no data is loaded: load the data on the Data tab, then run")
    vals, problems = rt.coerce_values(params, values)
    if problems:
        raise RoutineRefused("; ".join(problems))
    vals.update(derived_window_values(params, d))         # an input that follows the load window takes this run's
    name = d.get("name") or d.get("source") or "the data loaded now"
    if emit:
        emit({"type": "lookup_start", "kind": "check", "query": name})
    fit = rt.fit_check((manifest.get("data") or {}).get("columns") or [], d.get("columns") or [])
    if not fit["fits"]:
        if emit:
            emit({"type": "lookup", "kind": "check", "query": name, "peek": fit["line"]})
        raise RoutineRefused("the data does not fit the routine: " + fit["line"])
    cut = cut_window(ver, d)
    if cut:                                                    # the record says the window the method saw, not the cached load's
        d = dict(d, date_range=f"{cut['start']} to {cut['end']}")
    checks = rt.value_checks(params, vals)
    value_notes: List[str] = []
    if checks:
        stdout, err, _f, _g = runner(rt.precheck_script(checks, d.get("aux") or [], cut), 120)
        found = rt.read_precheck(stdout or "")
        miss, value_notes = rt.value_verdict(params, vals, found) if found is not None else ([], [])
        if miss:
            if emit:
                emit({"type": "lookup", "kind": "check", "query": name, "peek": "; ".join(miss)})
            raise RoutineRefused("; ".join(miss))
    number = len(routine.get("runs", [])) + 1
    # the data made to fit the recorded shape: the auxiliary files bound by kind (copies with the missing columns added,
    # empty tables for the absent ones) in the run's own folder, the executed text with this load's names, `df` conformed
    run_dir = run_dir or f"routines/{routine.get('id', 'routine')}/{run_tag(vnum, number)}"
    prep = prepare(ver, d, runner, run_dir)
    if (prep.get("shape") or {}).get("frame_rows") is not None:                     # a cut run: the frame's rows as the method sees them (2026-10-16)
        d = dict(d, rows=int(prep["shape"]["frame_rows"]))
    # what differs from the original, in sentences (step 4, 2026-10-11): the rows of the frame and of each bound file against
    # the original's, columns added or empty, a file empty or unreadable; the CHECK row says it, the record keeps it
    differences = rt.shape_sentences(manifest.get("data") or {}, d, prep["shape"], prep["binding"])
    check_line = fit["line"] + (("; " + "; ".join(differences)) if differences else "") + (("; " + aux_line(prep["binding"], prep["shape"])) if aux_line(prep["binding"], prep["shape"]) else "") \
        + (("; " + "; ".join(value_notes)) if value_notes else ("; the chosen values are in the data" if checks else ""))
    if prep.get("cut"):
        check_line += f"; cut to {prep['cut']['start']} → {prep['cut']['end']} from the cached load" + (f" {(d.get('load') or {}).get('cached_from')[0]} → {(d.get('load') or {}).get('cached_from')[1]}" if len((d.get("load") or {}).get("cached_from") or []) == 2 else "")
    if prep["note"]:
        check_line += "; " + prep["note"]
    if emit:
        emit({"type": "lookup", "kind": "check", "query": name, "peek": check_line})
    subject_id = str(rt.subject_of_record(d).get("id") or "")
    dates = _dates_of(d)
    interval = interval if interval in INTERVALS and all(dates) else None        # a set interval is a window; without one the run is custom
    ref_number, ref_results = reference_run(routine, ver, compare_with, subject_id=subject_id, interval=interval, window=dates)     # within this subject's runs (2026-10-30)
    n_cells = len(rt.split_script(ver.get("script") or "")[3])
    rz = ver.get("run_zero") or {}
    if emit:
        emit({"type": "lookup_start", "kind": "run", "query": f"run {number} · v{vnum} · {n_cells} cell{'s' if n_cells != 1 else ''}"})
    t0 = time.time()
    got = attempt(ver, d, vals, runner, run_dir, run_timeout(ver), prep)
    run_, results = got["run"], got["results"]
    stdout, err, figs = run_["stdout"], run_["error"], run_["figs"]
    # the inputs that follow the frame's own dates were written by the prelude: the values go on the record, the line off the output
    written = read_marked(stdout, rt.INPUTS_MARK_OUT)
    if written:
        vals.update({k: v for k, v in written.items() if k in vals})
    seen = read_marked(stdout, rt.DATA_MARK_OUT)               # a cut run: the rows the method saw
    if seen and seen.get("rows") is not None:
        d = dict(d, rows=int(seen["rows"]))
    if written or seen:
        stdout = "\n".join(ln for ln in stdout.splitlines() if not ln.strip().startswith((rt.INPUTS_MARK_OUT, rt.DATA_MARK_OUT)))
    status, line = rt.run_status(expected, results, run_, err, ref_results)
    if status in ("failed", "timed_out"):                      # the run was not carried through: every line it lacks, for that reason
        results = [r if r.get("estimate") is not None else dict(r, why=line) for r in results]
    if got["at"] and not places_hold(ver):                     # a version whose lines do not know their places learns them at its first whole run;
        for e, at in zip(expected, got["at"]):                 # a shorter run proven on the script as it read before goes, its time with it
            e["at"] = at
        rz["elapsed"] = ((ver.get("lean") or {}).get("elapsed") or [rz.get("elapsed")])[0]
        ver.update(steps=rt.steps_key(ver["script"]), lean=None)
    gaps = rt.gap_sentences((manifest.get("data") or {}).get("gaps"), run_["gaps"], watch_of(ver)["by"])
    elapsed = run_["elapsed"]
    if emit:
        emit({"type": "lookup", "kind": "run", "query": f"run {number} · v{vnum} · {n_cells} cell{'s' if n_cells != 1 else ''}",
              "peek": f"{line} · {len(figs)} figure{'s' if len(figs) != 1 else ''} · {elapsed} s"})
    cmp = rt.compare_runs(expected, results, ref_results)
    if ref_results is None and interval:
        cmp["line"] = f"nothing to compare with: no earlier {interval} on record" + (" for this subject" if subject_id else "")
    elif ref_results is None and subject_id and any(x.get("version") == vnum and x.get("status") in DONE for x in routine.get("runs", [])):
        cmp["line"] = cmp["line"].replace("the first run of this version", "the first run on this subject")       # the version's other runs are other subjects'
    if emit and ref_results is not None:
        ref_run = next((x for x in routine.get("runs", []) if x.get("number") == ref_number), None)
        when = _when(ref_run.get("created") if ref_run else rz.get("created"))
        window = window_text(ref_run.get("data") if ref_run else manifest.get("data"))      # and its window, so the coach sees what is compared
        emit({"type": "lookup", "kind": "compare", "query": f"with run {ref_number}" + (f" ({', '.join(x for x in (when, window) if x)})" if when or window else ""), "peek": cmp["line"]})
    now = time.time()
    generated = run_["generated"]
    record = {"number": number, "version": vnum, "created": t0, "finished": now, "elapsed": elapsed, "status": status, "line": line, "interval": interval,
              "data": d, "inputs": vals, "results": results, "figures": len(figs), "cells": n_cells,
              "against": ref_number, "comparison": cmp, "narrative": "", "error": (err.strip()[-2000:] if err else ""), "stopped": stopped_of(got), "gaps": gaps,
              "fit": {k: fit[k] for k in ("missing", "extra", "retyped", "line")}, "bindings": prep["subs"], "sources": prep["sources"], "aux_absent": [rt.aux_kind(p) for p in prep["binding"]["absent"]],
              "differences": differences, "check": check_line,
              "shape": prep["shape"], "run_dir": run_dir, "generated": list(generated or []) if isinstance(generated, (list, tuple)) else []}
    summary = {k: record[k] for k in ("number", "version", "created", "finished", "elapsed", "status", "line", "interval", "inputs", "results", "figures", "against", "cells", "gaps")}
    summary["data"] = light_data(d)
    summary["comparison"] = {k: cmp[k] for k in ("moved", "within", "changed", "missing", "compared", "line")}
    routine.setdefault("runs", []).append(summary)
    store.save(routine)
    tag = run_tag(vnum, number)
    store.save_run(routine["id"], tag, record)
    try:
        store.save_run_files(routine["id"], tag, stdout, figs)
    except OSError:
        pass
    return {"run": record, "summary": summary, "routine": rt.RoutineStore.summary(routine), "numbers": run_numbers(routine, vnum, subject_id), "subject": rt.subject_of_record(d),
            "against_data": reference_data(routine, ver, ref_number), "stdout": stdout, "figures": figs, "name": routine.get("name")}


# ----------------------------------------------------------------------------- the runs on record
def _when(ts) -> str:
    try:
        return time.strftime("%d %b", time.localtime(float(ts))) if ts else ""
    except (TypeError, ValueError, OverflowError):
        return ""


def window_text(data: Optional[dict]) -> str:
    """When a run's data is from: its window (`start → end`), else the file or the race it was; '' when nothing says."""
    d = data or {}
    if d.get("window") and len(d["window"]) == 2 and all(d["window"]):
        start, end = d["window"]
    else:
        start, end = _dates_of(d)
    if start and end:
        return f"{start} → {end}"
    extra = d.get("extra") or {}
    return str(extra.get("race_title") or (d.get("load") or {}).get("race_title") or d.get("name") or "")


def run_numbers(routine: dict, version: Optional[int] = None, subject_id: Optional[str] = None) -> List[int]:
    """The runs a person can step through with the arrows: run zero of the current version, then every run - with
    `subject_id` (2026-10-30), only that subject's: run zero when it is theirs, the runs on their data."""
    ver = version or routine.get("current_version") or 1
    v = next((x for x in routine.get("versions", []) if x.get("number") == ver), None)
    own = subject_id is None or (v is not None and zero_subject(v) == str(subject_id))
    out = [0] if v and (v.get("run_zero") or {}).get("verified") and own else []
    return out + [r["number"] for r in routine.get("runs", []) if subject_id is None or same_subject(r, subject_id)]


def reference_data(routine: dict, version: dict, number) -> Optional[dict]:
    """The light data record of the run a run was compared with (`against`): run zero's is the version's own, a run's
    its summary's - so the Comparison tab can say whose and when both sides are. None without a reference."""
    if number is None:
        return None
    if int(number) == 0:
        return light_data((version.get("manifest") or {}).get("data"))
    ref = next((x for x in routine.get("runs", []) if x.get("number") == int(number)), None)
    return dict(ref.get("data") or {}) if ref else None


def delete_run(routine: dict, store: rt.RoutineStore, number: int) -> dict:
    """Delete a run from the routine's history (2026-11-08, docs/ROUTINES_DESIGN.md §21): its line off the record and its
    files off the disk. Run zero is the check on the original data and stays; a run another run was compared against
    stays named by its number on that run's record. Returns the line deleted."""
    n = int(number)
    if n == 0:
        raise RoutineRefused("run 0 is the check on the original data; it stays")
    runs = routine.get("runs", [])
    summary = next((x for x in runs if x.get("number") == n), None)
    if summary is None:
        raise RoutineRefused(f"no run {n} on this routine")
    routine["runs"] = [x for x in runs if x.get("number") != n]
    store.save(routine)
    folder = os.path.join(store.path(routine["id"]), "runs", run_tag(int(summary.get("version") or 1), n))
    shutil.rmtree(folder, ignore_errors=True)
    return summary


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
                  "inputs": rz.get("inputs") or {}, "results": rz.get("results") or [], "figures": rz.get("figures", 0), "cells": len(rt.split_script(ver.get("script") or "")[3]),
                  "against": None, "comparison": rt.compare_runs((ver.get("manifest") or {}).get("results") or [], rz.get("results") or [], None), "narrative": "", "zero": True,
                  "stopped": [], "gaps": []}
        tag = run_tag(ver.get("number", 1), 0)
    else:
        summary = next((x for x in routine.get("runs", []) if x.get("number") == int(number)), None)
        if summary is None:
            raise RoutineRefused(f"this routine has no run {number}")
        tag = run_tag(summary.get("version", 1), summary["number"])
        record = store.load_run(routine["id"], tag) or dict(summary)
    stdout, figs = store.run_files(routine["id"], tag)
    subject = rt.subject_of_record(record.get("data"))                   # whose run: the arrows step through this subject's runs alone (2026-10-30)
    ver = version_of(routine, record.get("version"))
    return {"run": record, "stdout": stdout, "figures": figs, "routine": rt.RoutineStore.summary(routine), "numbers": run_numbers(routine, subject_id=str(subject.get("id") or "")),
            "subject": subject, "against_data": reference_data(routine, ver, record.get("against")), "name": routine.get("name")}


# ----------------------------------------------------------------------------- the fill (§14.3)
class Fill:
    """A fill (docs/ROUTINES_DESIGN.md §14.3): the routine run on each window of a set interval, oldest first, in a
    thread on the session's instance - every window a cut of the span the page loaded once (the load's dates become
    the window's, `cached_from` the span: what cut_window cuts by), each run recorded as it completes, quiet (nothing
    on the pane's queue).
    It stops when asked (the window under way finishes) and when the Data tab no longer holds the span."""

    def __init__(self, instance, routine_id: str, interval: str, windows: List, values: Optional[dict] = None, aux: Optional[List[str]] = None, load: Optional[dict] = None,
                 routine_name: str = ""):
        if interval not in INTERVALS:
            raise RoutineRefused(f"the interval must be one of {', '.join(INTERVALS)}")
        self.windows = [(str(w[0]), str(w[1])) for w in (windows or []) if isinstance(w, (list, tuple)) and len(w) == 2]
        if not self.windows or len(self.windows) != len(windows) or any(not re.fullmatch(r"\d{4}-\d{2}-\d{2}", x) for w in self.windows for x in w) or any(a > b for a, b in self.windows):
            raise RoutineRefused("the windows must be [start, end] pairs of dates, the start not after the end")
        self.instance, self.routine_id, self.interval = instance, str(routine_id), str(interval)
        self.routine_name = str(routine_name or "")                    # on the status: the Summary names the routine under a fill when another is shown
        self.values, self.aux, self.load = dict(values or {}), aux, dict(load or {})
        self.df_id = getattr(instance, "df_id", None)                  # the span: the fill stops when the Data tab holds something else
        span = self.load.get("cached_from")
        self.span = [str(span[0]), str(span[1])] if isinstance(span, (list, tuple)) and len(span) == 2 else [self.windows[0][0], self.windows[-1][1]]
        self.done = self.failed = 0
        self.current: Optional[Tuple[str, str]] = None
        self.started, self.finished = time.time(), None
        self.stopped, self.error, self.last = False, "", ""
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> "Fill":
        self._thread = threading.Thread(target=self._work, name=f"fill-{self.routine_id}", daemon=True)
        self._thread.start()
        return self

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict:
        now = self.finished or time.time()
        return {"running": self.running, "routine_id": self.routine_id, "routine_name": self.routine_name, "interval": self.interval, "total": len(self.windows), "done": self.done, "failed": self.failed,
                "current": list(self.current) if self.current else None, "stopped": self.stopped, "error": self.error, "last": self.last,
                "started": self.started, "finished": self.finished, "elapsed": round(now - self.started, 1),
                "left": round((now - self.started) / self.done * (len(self.windows) - self.done), 0) if self.done and self.running else None}

    def _work(self) -> None:
        logger.info("fill of routine %s: %d %s window(s), the span %s → %s", self.routine_id, len(self.windows), self.interval, self.span[0], self.span[1])
        for start, end in self.windows:
            if self._stop.is_set():
                self.stopped = True
                break
            if str(getattr(self.instance, "df_id", None)) != str(self.df_id):
                self.stopped, self.error = True, "the data on the Data tab changed"
                break
            self.current = (start, end)
            load = dict(self.load, start_date=start, end_date=end, cached_from=list(self.span))
            try:
                out = self.instance.run_routine(self.routine_id, self.values, aux=self.aux, load=load, interval=self.interval, quiet=True)
                self.last = str((out.get("run") or {}).get("line") or "")
                if (out.get("run") or {}).get("status") in ("failed", "timed_out"):
                    self.failed += 1
            except RoutineRefused as exc:                                  # a window the checks refuse (a value not in it): counted, the fill goes on
                self.failed += 1
                self.last = str(exc)
                logger.info("fill of routine %s: %s → %s refused: %s", self.routine_id, start, end, exc)
            except Exception as exc:                                       # noqa: BLE001
                self.failed += 1
                self.last = f"the run could not start: {exc}"
                logger.exception("fill of routine %s: %s → %s failed", self.routine_id, start, end)
            self.done += 1
        self.current, self.finished = None, time.time()
        logger.info("fill of routine %s %s: %d of %d done, %d failed, %.0f s", self.routine_id, "stopped" if self.stopped else "finished", self.done, len(self.windows), self.failed, self.finished - self.started)
