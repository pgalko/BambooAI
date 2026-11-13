"""Routines (docs/ROUTINES_DESIGN.md): an analysis kept as a method and run again, without a model, on new data.

The pure part lives here - nothing in this module talks to a model, an executor or the web app:
  - a RESULT line read back (parse_result_line) and the lines a chain recorded (expected_results);
  - the script with its cells and its INPUTS block (split_script, join_script, with_inputs);
  - the promoter's prompt, the reading of its reply, its pick and its edits (PROMOTER_SYSTEM, promoter_user,
    parse_promoter, pick_results, apply_edits, finish_inputs);
  - the reading of the code, a statement at a time - what each reads and writes (read_steps) - which gives the
    promoter's view of a chain (prune_cells, held_out, put_back) and the statements a run needs (needed_steps);
  - a run, a statement at a time: the script as a run executes it (stepwise), its output read back (read_run),
    its lines laid against the expected ones (place_lines);
  - a run's data made to fit the recorded shape (fit_check, bind_aux, bind_script, conform_prelude, shape_script,
    cache_match, the value checks);
  - a run's status, run zero's verdict and two runs compared (run_status, check_zero, compare_runs, same_figures,
    gap_sentences);
  - the store: one folder per routine under <storage>/routines/, and the one upgrade of earlier records
    (RoutineStore).

The standing rule (DESIGN_CHECKLIST C5) holds for every string here: nothing a model reads names a task.
"""
from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import re
import shutil
import time
import tokenize
import uuid
from typing import Dict, Iterable, List, Optional, Tuple

INPUT_TYPES = ("number", "numbers", "date_window", "choice", "toggle")
MAX_INPUTS = 5
INPUTS_MARK = "# --- INPUTS ---"
INPUTS_MARK_OUT = "ROUTINE_INPUTS:"          # printed by a run's prelude: the inputs it wrote from the data (date windows that follow it)
_CELL_MARK_RE = re.compile(r"^# --- cell (\d+) ---$", re.M)
_TAIL_MARK = "\n# --- the executor's own display options back ---"
_NUM = r"[-+][\d,]*\.?\d+(?:[eE][-+]?\d+)?"
_TAGS_RE = re.compile(r"^(?P<tags>(?:\((?:test [^)]*|corrects cells? [^)]*)\) )*)(?P<rest>.*)$", re.S)
_LINE_NUM_RE = re.compile(r"^(?P<what>.*?): (?P<est>" + _NUM + r")(?: \((?P<ci>\d+)% CI (?P<lo>" + _NUM + r") to (?P<hi>" + _NUM + r")\))?"
                          r"(?: (?P<unit>[^,]*?))?(?:, (?P<dir>.*?))?(?P<typed> - typed: .*)?$", re.S)
_LINE_ANY_RE = re.compile(r"^(?P<what>.*?): (?P<est>[^\s(,]+)(?: \((?P<ci>\d+)% CI (?P<lo>\S+) to (?P<hi>\S+)\))?"
                          r"(?: (?P<unit>[^,]*?))?(?:, (?P<dir>.*?))?(?P<typed> - typed: .*)?$", re.S)
_KEY_REF_RE = re.compile(r"INPUTS\[\s*['\"]([A-Za-z_]\w*)['\"]\s*\]")
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def new_id() -> str:
    return uuid.uuid4().hex[:12]


# ----------------------------------------------------------------------------- the RESULT line, read back
def parse_result_line(line: str) -> Optional[dict]:
    """One printed RESULT line (with or without its 'RESULT: ' prefix) as a record: tags, what, estimate, low, high
    (as the strings the kernel printed), unit, direction, typed. None when the line is not a RESULT line."""
    s = (line or "").strip()
    if s.startswith("RESULT:"):
        s = s[len("RESULT:"):].strip()
    elif not s:
        return None
    m = _TAGS_RE.match(s)
    tags, rest = (m.group("tags") or "").strip(), m.group("rest")
    mm = _LINE_NUM_RE.match(rest) or _LINE_ANY_RE.match(rest)
    if not mm:
        return None
    test = re.search(r"\(test ([^)]*)\)", tags)
    corr = re.search(r"\(corrects cells? ([^)]*)\)", tags)
    return {"tags": tags, "what": mm.group("what").strip(), "estimate": mm.group("est"), "low": mm.group("lo"), "high": mm.group("hi"),
            "ci": int(mm.group("ci")) if mm.group("ci") else None, "unit": (mm.group("unit") or "").strip(),
            "direction": (mm.group("dir") or "").strip(), "typed": bool(mm.group("typed")),
            "test": test.group(1) if test else None, "corrects": corr.group(1) if corr else None}


def number(s: Optional[str]) -> Optional[float]:
    try:
        return float(str(s).replace(",", "")) if s is not None else None
    except ValueError:
        return None


def expected_results(cells: Iterable, order: Iterable[int]) -> List[dict]:
    """The RESULT lines the script prints, in order, from the kernel's records of the cells it contains: the identity of
    a line is (cell, index) - its position - never its label. `typed` comes from the record (the replay's stub prints
    no typed mark). Cells not in `order` are not in the script and print nothing."""
    wanted = set(order)
    out = []
    for c in cells:
        if c.cell_no is None or c.cell_no not in wanted:
            continue
        for i, r in enumerate(c.results or []):
            p = parse_result_line("RESULT: " + str(r.get("text") or "")) or {"what": str(r.get("text") or "")[:120], "estimate": None, "low": None, "high": None, "unit": "", "direction": ""}
            out.append({"cell": c.cell_no, "index": i, "label": p["what"], "typed": bool(r.get("typed")) or bool(p.get("typed")),
                        "estimate": p["estimate"], "low": p["low"], "high": p["high"], "unit": p["unit"], "direction": p["direction"], "dropped": False})
    return out


# ----------------------------------------------------------------------------- the script and its cells
def split_script(script: str) -> Tuple[str, str, str, List[int]]:
    """(header, cells, tail, cell numbers): the assembled script's preamble (imports, options, the DS and RESULT stubs),
    the cells with their markers (and the capture switches between them), and the closing reset block."""
    text = script or ""
    m = _CELL_MARK_RE.search(text)
    if not m:
        return text, "", "", []
    start = m.start()
    if start and text[start - 1] == "\n":
        start -= 1
    end = text.find(_TAIL_MARK, start)
    if end < 0:
        end = len(text)
    header, cells, tail = text[:start], text[start:end], text[end:]
    return header, cells, tail, [int(n) for n in _CELL_MARK_RE.findall(cells)]


def join_script(header: str, cells: str, tail: str) -> str:
    """The routine's script: the INPUTS mark sits between the preamble and the first cell; with_inputs fills it."""
    return header + ("" if header.endswith("\n") else "\n") + INPUTS_MARK + "\n" + cells + tail


def cell_blocks(cells: str) -> List[Tuple[int, int, int]]:
    """(cell number, start, end) of every cell's text in the cells region, marker included."""
    marks = list(_CELL_MARK_RE.finditer(cells))
    return [(int(m.group(1)), m.start(), marks[i + 1].start() if i + 1 < len(marks) else len(cells)) for i, m in enumerate(marks)]


def _literal(v, depth=0):
    """A Python literal for an input value: str, int, float, bool, None, or a list of those."""
    if depth > 3:
        raise ValueError("an input value nests too deep")
    if v is None or isinstance(v, (bool, int, float, str)):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_literal(x, depth + 1) for x in v) + "]"
    raise ValueError(f"an input value of type {type(v).__name__} cannot be written into the script")


def inputs_block(values: Dict[str, object]) -> str:
    rows = ",\n".join(f"    {k!r}: {_literal(v)}" for k, v in (values or {}).items())
    return "# the inputs of this run, written before it starts; the cells read INPUTS[...]\nINPUTS = {\n" + rows + ("\n" if rows else "") + "}"


def with_inputs(script: str, values: Dict[str, object], prelude: str = "") -> str:
    """The script with its INPUTS block in place of the mark (a script without the mark gets the block at the top);
    `prelude` - the run's conform block (conform_prelude) - goes after the inputs, before the first cell."""
    block = inputs_block(values) + (("\n" + prelude.rstrip("\n")) if prelude else "")
    if INPUTS_MARK in script:
        return script.replace(INPUTS_MARK, block, 1)
    return block + "\n" + script


def keys_read(script: str) -> List[str]:
    """The input keys the script reads, in order of first use."""
    seen, out = set(), []
    for k in _KEY_REF_RE.findall(script or ""):
        if k not in seen:
            seen.add(k); out.append(k)
    return out


# ----------------------------------------------------------------------------- the promoter
PROMOTER_SYSTEM = """You are preparing an analysis so that it can be run again, unchanged in method, on other data of the same shape - a later period, another subject's data, an updated file - by a person who will only set a few inputs before each run and will never edit the code.

What the result is for. The analysis becomes a routine: the method kept with its few inputs. A person opens it later, picks the data - usually a new window of the same source, often another subject's - sets the inputs in a dialog and runs it, and the result lines are compared with the run before. The data of a run is loaded fresh each time: nothing of this window is there - not its rows, not the identifiers of its sessions or groups, not the dates inside it - only data of the same shape, the same columns and the same files. Before the routine is kept it is run once more on this very data and must reproduce the result lines the chain recorded; a rewrite that changes a number is refused.

The test of an input: could the person set it before the data is loaded, without looking at it? A threshold, a band, a number of days, a switch, a choice among values a person knows by name - yes. An identifier of a row, a session or a group of this data, a list of them, a date or a name found by looking at this data - no: such a value is the data's own, and the next data has its own. A literal of that kind is replaced by the rule that produced it - the expression the chain used to find it, where a cell has one - and is never made an input. Where the chain has no such rule, report the literal under "unfit" and leave it as it is; the routine is not made until the analysis picks by a rule.

You receive the question the analysis answered, the summary of its answer, a description of the data it ran on (its key columns named), the cells of the script in execution order, the ledger of RESULT lines the cells recorded, the cells the report cites, when it cites any, and - when the person gave one - their instruction on what the runs should track. Reply with one JSON object and nothing else.

What to do:
1. Name the constants written into the code that would have to change for the method to apply to other data of the same shape: period boundaries inside the data, thresholds, filters, bin edges, exclusions. Leave alone the constants that belong to the method itself (plausibility bounds, a bootstrap size, a seed, column names) and anything that is the data's own vocabulary. A file name under the datasets folder is the loader's, written for the period it loaded: leave it exactly as it is, dates included - each run binds it to the file that run loads - and never make the loaded period itself an input; the period is chosen when the data is loaded, before the method runs.
2. Where a date literal is the data's own first or last date, make it the data's range (the column's .min() or .max()) so the period chosen at load time is the only period there is. Where it is a boundary inside the data, make it an input. Where a number is a count the data determines - the rows of a table, the periods in it, the groups - and the code uses it as a loop bound, an index or a divisor, make it that count (len(...)), not an input: the next data has its own. Where a literal names rows, sessions or groups of this data - identifiers, a list of them - replace it with the rule that found them, as the test of an input says.
3. Propose each remaining constant as an input: at most five, each of one type - number, numbers (a short list of numbers), date_window (two dates), choice (one value of a column, or several when "multiple" is true), toggle. A choice is a pick among the values of a column the person can read by name; never over a key column. Keep a constant a constant when unsure; fewer inputs is better than more.
4. Rewrite the code as find/replace edits, never by retyping it: each edit's "find" is a verbatim fragment that occurs exactly once in the cell it names, and "replace" is the same fragment with the constant replaced by INPUTS["key"] - or, for a literal the chain read off the data, by the expression that computes it. A label written into a RESULT call that carries a constant (a count, an identifier) may read the input through an f-string. Leave the method, the cell markers, the order of the cells and every RESULT call otherwise untouched. The block INPUTS = {...} is written at the top of the script before each run; do not write it yourself.
5. Say which RESULT lines a run should compare with the runs before it, by their numbers in the ledger, and name each. A line is compared when it is the final form of a quantity the answer rests on. Where the report cites cells, those are the cells the answer was read from: the final forms are among their lines. Not compared: an earlier cell's version of a quantity that a later cell computed again, re-specified or extended; a check or a trial the answer does not rest on - a quantity computed again with part of the data left out, under another cut or a what-if, is a check when another line gives it on all the data. Lines that form a series - one quantity over durations, bands, groups or periods - are compared whole: every line of the series, from the cell that printed it last, or none of them. Every line is still printed and checked; only the comparison leaves the others out. A name reads as a table head: the quantity and what tells it from the other compared lines, at most 40 characters, without the counts, periods and dates that vary with the data.
6. The person's instruction, when there is one, is not a request to compute anything: the method is fixed, nothing is computed, added or rewritten for what it names, and no input is made for it. For each quantity it names, give the ledger lines that are that quantity - its final form, from the cell that printed it last - with a name for each; a line is a match when it is that quantity, not the nearest one. A quantity no line gives is answered with an empty list and nothing more: no reason, no substitute. Every line given here is compared, whether or not step 5 picked it.
7. Reply with exactly this object:
{"name": "a short title for the method, at most 60 characters",
 "inputs": [{"key": "snake_case", "label": "what the person sees", "type": "number | numbers | date_window | choice | toggle", "default": "the value the analysis used, in the type's form", "origin": "one short clause: where the value came from in the analysis", "column": "for a choice over values of a column the data has (the frame or a loaded file): that column; none for words the script matches or computes", "multiple": false}],
 "edits": [{"cell": 3, "find": "verbatim fragment", "replace": "the same fragment reading INPUTS[...]"}],
 "kept": ["one clause per constant left as it is, and why"],
 "recomputed": ["one clause per literal replaced by the rule that produced it, naming the cell"],
 "unfit": [{"cell": 10, "what": "what the literal names and why no rule in the chain picks them"}],
 "compare": [{"line": 7, "name": "the quantity, as a table head"}],
 "tracked": [{"asked": "a quantity the instruction names, in its words", "lines": [{"line": 5, "name": "the quantity, as a table head"}]}]}
With nothing worth making an input, return "inputs": [] and "edits": [] - the method then runs as it is on data of the same shape. "recomputed" and "unfit" are empty when nothing applies; "tracked" is empty when there is no instruction.
Keep the object short: each "find" the shortest fragment that still occurs once in its cell, the clauses brief, nothing outside the object."""

PROMOTER_RETRY = "Your reply could not be read ({problem}). Reply again with the JSON object only, as specified."
PROMOTER_KEYS = ("Your reply made an input of identifiers of this data ({inputs}): a person cannot set those before the data is loaded, and the next "
                 "data has its own. Replace each such literal with the rule the chain used to find it, or report it under \"unfit\" when the chain has "
                 "no such rule. Reply again with the JSON object only.")
PROMOTER_CUT = ("Your reply was cut off at the token limit before the object was complete ({got} characters arrived). Reply again, shorter: "
                "the JSON object only, each \"find\" the shortest fragment that still occurs once in its cell, nothing outside the object.")
PROMOTER_CUT_EMPTY = ("Your reply was cut off at the token limit before anything but reasoning arrived. Decide briefly - the constants that "
                      "would change for other data of the same shape, and the shortest fragment for each - and reply with the JSON object only.")
PROMOTER_TRACKED = ("Your reply left out \"tracked\" though the person gave an instruction. Reply again with the JSON object only, \"tracked\" "
                    "answered from the ledger: for each quantity the instruction names, the lines that are it, or an empty list.")
MAX_INSTRUCTION = 300


def promoter_user(question: str, summary: str, data_text: str, cells: str, ledger: Iterable[str], manifest: Optional[dict] = None,
                  cited: Iterable[int] = (), instruction: str = "") -> str:
    parts = [f"QUESTION:\n{(question or '').strip()}", f"ANSWER SUMMARY:\n{(summary or '(none)').strip()}",
             f"DATA (the frame `df` the script ran on):\n{(data_text or '(no description)').strip()}",
             "THE SCRIPT (the cells in execution order; `df` is loaded before the first cell):\n" + (cells or "").strip(),
             "RESULT LINES THE CELLS RECORDED (numbered; the method's outputs, which must still be produced, in this order):\n" + ("\n".join(ledger) or "(none)")]
    if (instruction or "").strip():                           # the person's instruction (§15.6): answered under "tracked", from the ledger alone
        parts.append("THE PERSON'S INSTRUCTION (what the runs should track; answer it under \"tracked\", from the ledger alone):\n" + instruction.strip())
    cited = sorted({int(n) for n in cited})
    if cited:                                                  # the report's citations steady the pick (§15.5): where the answer was read from
        parts.append("THE REPORT CITES (the cells the answer was read from): " + ("cell " if len(cited) == 1 else "cells ") + ", ".join(map(str, cited)))
    if manifest and manifest.get("parameters"):
        parts.append("THE CURRENT VERSION'S INPUTS (keep the keys, labels and defaults that still apply):\n" + json.dumps(manifest["parameters"], indent=1))
    return "\n\n".join(parts)


def parse_promoter(text: str) -> dict:
    """The promoter's JSON object, fenced or bare; raises ValueError with a readable reason."""
    t = (text or "").strip()
    t = re.sub(r"^###\w+###\s*", "", t)
    m = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, re.S)
    if m:
        t = m.group(1)
    else:
        a, b = t.find("{"), t.rfind("}")
        if a < 0 or b < a:
            raise ValueError("no JSON object in the reply")
        t = t[a:b + 1]
    try:
        obj = json.loads(t)
    except ValueError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise ValueError("the reply is not a JSON object")
    for k, typ in (("inputs", list), ("edits", list), ("compare", list), ("recomputed", list), ("unfit", list), ("tracked", list)):
        if k in obj and not isinstance(obj[k], typ):
            raise ValueError(f"'{k}' is not a list")
    for k in ("inputs", "edits", "kept", "compare", "recomputed", "unfit"):
        obj.setdefault(k, [])                                  # "tracked" is not defaulted: its absence is what the host asks again about (§15.6)
    return obj


_KEY_COLUMN_RE = re.compile(r"id|.+_ids?|id_.+|uuid|.+_uuid", re.I)


def key_column(name) -> bool:
    """Whether a column name reads as a key - one that identifies rows, sessions or groups of this data, whose values other
    data will not have (docs/ROUTINES_DESIGN.md §18): id, *_id, *_ids, id_*, uuid."""
    return bool(_KEY_COLUMN_RE.fullmatch(str(name or "").strip()))


def key_inputs(inputs: Iterable[dict]) -> List[str]:
    """The proposed inputs that read as identifiers of the data - a choice over a key column, or an input named as one (*_id, *_ids) -
    which a person cannot set before the data is loaded: 'key over column', or the key alone."""
    out = []
    for p in inputs or []:
        if not isinstance(p, dict) or p.get("type") == "toggle":
            continue
        if key_column(p.get("column")):
            out.append(f"{p.get('key')} over {p.get('column')}")
        elif key_column(p.get("key")):
            out.append(str(p.get("key")))
    return out


def unfit_line(unfit: Iterable) -> str:
    """The literals the promoter could not express as a rule, as the refusal reads them: 'cell 10: three sessions named by identifier'."""
    parts = []
    for u in unfit or []:
        if isinstance(u, dict) and (u.get("what") or u.get("cell") is not None):
            parts.append((f"cell {u['cell']}: " if u.get("cell") is not None else "") + str(u.get("what") or "a literal of this data")[:160])
        elif isinstance(u, str) and u.strip():
            parts.append(u.strip()[:160])
    return "; ".join(parts)


MAX_NAME = 60


def tracked_lines(expected: List[dict], tracked: Optional[Iterable]) -> Tuple[Dict[int, str], List[str]]:
    """The promoter's answer to the person's instruction (§15.6): ({line number: name} of the lines it gave, the
    quantities it gave no line for). A number outside the ledger is dropped; a line already given for an earlier
    quantity is not given again, so one line never stands for two quantities - the second is said as not found."""
    picked: Dict[int, str] = {}
    missing: List[str] = []
    for e in tracked or []:
        if not isinstance(e, dict):
            continue
        asked = " ".join(str(e.get("asked") or "").split())[:120]
        got = False
        for item in (e.get("lines") or []):
            raw, name = (item.get("line"), item.get("name")) if isinstance(item, dict) else (item, "")
            try:
                n = int(raw)
            except (TypeError, ValueError):
                continue
            if 1 <= n <= len(expected) and n not in picked:
                picked[n] = " ".join(str(name or "").split())[:MAX_NAME]
                got = True
        if not got and asked and asked not in missing:
            missing.append(asked)
    return picked, missing


def pick_results(expected: List[dict], compare: Optional[Iterable], extra: Optional[Dict[int, str]] = None) -> List[dict]:
    """The promoter's pick applied to the expected lines (docs/ROUTINES_DESIGN.md §15.1): each entry of `compare` names a
    ledger line by its 1-based number and gives it a short name; the lines named are compared, every other line is
    dropped - kept on the manifest, left out of the comparison. `extra` (§15.6) are the lines the
    person's instruction reached, compared whatever `compare` says. A pick with no valid line keeps every line, without
    names: the pick is a proposal, never a refusal."""
    picked = {}
    for e in compare or []:
        if not isinstance(e, dict):
            continue
        try:
            n = int(e.get("line"))
        except (TypeError, ValueError):
            continue
        if 1 <= n <= len(expected):
            picked.setdefault(n, " ".join(str(e.get("name") or "").split())[:MAX_NAME])
    for n, name in (extra or {}).items():
        if not picked.get(n):
            picked[n] = name
    if not picked:
        return [dict(r, dropped=False) for r in expected]
    out = []
    for i, r in enumerate(expected, 1):
        row = dict(r, dropped=i not in picked)
        if picked.get(i):
            row["name"] = picked[i]
        out.append(row)
    return out


def _coerce_default(typ: str, v, multiple: bool):
    """The default in the type's form, or None when it cannot be read."""
    def num(x):
        if isinstance(x, bool):
            return None
        if isinstance(x, (int, float)):
            return x
        try:
            f = float(str(x).replace(",", "").strip())
        except ValueError:
            return None
        return int(f) if f.is_integer() and "." not in str(x) else f
    if typ == "number":
        return num(v)
    if typ == "numbers":
        if isinstance(v, str) and len(v.strip()) > 1 and v.strip()[0] in "[(" and v.strip()[-1] in "])":
            v = v.strip()[1:-1]                        # a list written as text, "[18, 26]" (2026-10-12: a promoter's reply)
        items = v if isinstance(v, (list, tuple)) else re.split(r"[,\s]+", str(v).strip())
        out = [num(x) for x in items if str(x).strip() != ""]
        return out if out and all(x is not None for x in out) and len(out) <= 40 else None
    if typ == "date_window":
        items = v if isinstance(v, (list, tuple)) else re.split(r"\s*(?:,|to|->|→)\s*", str(v).strip())
        items = [str(x).strip()[:10] for x in items]
        return items if len(items) == 2 and all(_DATE_RE.match(x) for x in items) else None
    if typ == "choice":
        if multiple:
            items = v if isinstance(v, (list, tuple)) else [x.strip() for x in str(v).split(",")]
            items = [str(x) for x in items if str(x).strip() != ""]
            return items if items else None
        return str(v[0]) if isinstance(v, (list, tuple)) and v else (str(v) if v is not None and not isinstance(v, (list, tuple)) else None)
    if typ == "toggle":
        if isinstance(v, bool):
            return v
        return {"true": True, "false": False, "yes": True, "no": False, "1": True, "0": False}.get(str(v).strip().lower())
    return None


def apply_edits(cells: str, edits: List[dict]) -> Tuple[str, List[dict], List[dict]]:
    """Apply the promoter's edits to the cells region, grouped by the input keys their replacements read: a group
    applies whole or not at all, so an input is never half made. Returns (cells, applied edits, failed groups
    [{keys, reason}]). An edit that reads no input (a date made the data's range) is its own group."""
    groups: Dict[tuple, List[dict]] = {}
    for e in edits or []:
        if not isinstance(e, dict):
            continue
        keys = tuple(sorted(set(_KEY_REF_RE.findall(str(e.get("replace") or "")))))
        groups.setdefault(keys or (f"edit {len(groups)}",), []).append(e)
    text, applied, failed = cells, [], []
    for keys, group in groups.items():
        work = text
        ok = True
        for e in group:
            find, rep = str(e.get("find") or ""), str(e.get("replace") or "")
            try:
                cell = int(e.get("cell"))
            except (TypeError, ValueError):
                cell = None
            if not find or find == rep:
                ok = False; failed.append({"keys": list(keys), "reason": "an edit has no fragment to find, or changes nothing"}); break
            if find.count("RESULT(") != rep.count("RESULT("):
                # the method's outputs are not the promoter's to change (§15.6): an edit that adds or removes a RESULT call
                # - computing something the person asked to track, say - is refused as a whole
                ok = False; failed.append({"keys": list(keys), "reason": "an edit adds or removes a RESULT call - the method's outputs are not changed"}); break
            if loader_file_literals(find) != loader_file_literals(rep):
                # the loaded period written into the loader's file name (2026-10-10): the name is the loader's, and a run
                # binds it to the file this load produced - an input there, or any change to the name, would only break
                # the binding
                ok = False; failed.append({"keys": list(keys), "reason": "the period or the file name is the loader's, not an input - each run binds the name to the file it loaded"}); break
            block = next(((s, t) for n, s, t in cell_blocks(work) if n == cell), None)
            region = work[block[0]:block[1]] if block else ""
            n_in_cell = region.count(find) if block else 0
            if n_in_cell == 1:
                work = work[:block[0]] + region.replace(find, rep, 1) + work[block[1]:]
            elif n_in_cell == 0 and work.count(find) == 1:
                work = work.replace(find, rep, 1)
            else:
                ok = False
                failed.append({"keys": list(keys), "reason": (f"the fragment {find[:60]!r} occurs {n_in_cell} times in cell {cell}" if block else f"the script has no cell {cell}")
                               + ("" if n_in_cell else f" and {work.count(find)} times in the script")})
                break
        if ok:
            text = work
            applied.extend(group)
    return text, applied, failed


def finish_inputs(inputs: List[dict], cells: str, failed: List[dict]) -> Tuple[List[dict], List[str]]:
    """The inputs that survive: readable key, a known type, a default in the type's form, every edit that serves
    them applied, and read by the script. At most MAX_INPUTS. Returns (inputs, notes for the person)."""
    notes = []
    lost = {k for f in failed for k in f.get("keys", []) if not str(k).startswith("edit ")}
    read = set(keys_read(cells))
    out, seen = [], set()
    for p in inputs or []:
        if not isinstance(p, dict):
            continue
        key = str(p.get("key") or "").strip()
        label = str(p.get("label") or key).strip()
        typ = str(p.get("type") or "").strip()
        multiple = bool(p.get("multiple"))
        if not _KEY_RE.match(key) or key in seen:
            notes.append(f"an input with an unusable or repeated key was left out ({key or '?'})"); continue
        if typ not in INPUT_TYPES:
            notes.append(f"{label}: unknown type {typ!r}, left out"); continue
        if key in lost:
            notes.append(f"{label}: could not be made an input (" + "; ".join(f["reason"] for f in failed if key in f.get("keys", [])) + ")"); continue
        if key not in read:
            notes.append(f"{label}: the script never reads it, left out"); continue
        default = _coerce_default(typ, p.get("default"), multiple)
        if default is None:
            notes.append(f"{label}: its value could not be read as a {typ}, left out"); continue
        seen.add(key)
        item = {"key": key, "label": label[:80], "type": typ, "default": default, "origin": str(p.get("origin") or "")[:160]}
        if typ == "choice":
            item["multiple"] = multiple
            if p.get("column"):
                item["column"] = str(p.get("column"))[:80]
        out.append(item)
    if len(out) > MAX_INPUTS:
        notes.append(f"{len(out)} inputs were proposed; the first {MAX_INPUTS} are kept")
        out = out[:MAX_INPUTS]
    return out, notes


def unknown_keys(cells: str, inputs: List[dict]) -> List[str]:
    """Keys the script reads that no input declares: such a script would stop on the first run."""
    declared = {p["key"] for p in inputs}
    return [k for k in keys_read(cells) if k not in declared]


def strip_keys(cells: str, original: str, applied: List[dict], keys: Iterable[str]) -> str:
    """The cells with the edits of the given keys reverted: re-apply, on the original text, only the edits that read
    none of them (used when the person drops an input, or an input was left out after its edits applied)."""
    drop = set(keys)
    keep = [e for e in applied if not (set(_KEY_REF_RE.findall(str(e.get("replace") or ""))) & drop)]
    text, _, _ = apply_edits(original, keep)
    return text


def defaults_of(inputs: List[dict]) -> Dict[str, object]:
    return {p["key"]: p["default"] for p in inputs or []}


# ----------------------------------------------------------------------------- the reading: what each statement reads and writes
_CAPTURE_LINE_RE = re.compile(r"^_bamboo_capture\[0\] = (True|False)$")
_KEEP_ATTRS = {"show", "save", "savefig", "write", "writelines", "to_csv", "to_parquet", "to_excel", "to_json", "to_pickle", "to_hdf", "to_sql", "to_feather",
               "to_html", "to_latex", "to_markdown"}                 # a call by one of these names, or by a write_* name, is an effect the routine keeps
_MUTATORS = {"append", "extend", "insert", "pop", "remove", "clear", "update", "setdefault", "sort", "reverse", "add", "discard", "popitem"}
_QUIET = {"print", "pprint", "display"}                              # a call that only shows: nothing rests on it
_OPAQUE = {"eval", "exec"}                                           # a call that may read or bind any name: it stays, and everything before it
_NAMESPACE = {"globals", "locals", "vars"}                           # a call that reads names by their strings - the strings the chain's code holds
_ANY = "*"                                                           # every name, as a read
_MODULES = {"pd", "np", "plt", "matplotlib"}                         # bound before the first cell: the script's preamble, the kernel's start
_RANDOM, _NP_RANDOM = "<random>", "<numpy.random>"                   # the state of a global generator, as a name: a draw reads it and moves it on
_GENERATORS = {"default_rng", "RandomState", "Generator", "Random"}  # a call by one of these names makes a generator of its own
HELD = "\x00"                                                        # a line of the chain held out of the promoter's view (held_out): no fragment of code matches it


def _root(node):
    """The name an expression hangs on: df in df['x'], df.loc[...], fig.update_layout(...)."""
    while isinstance(node, (ast.Attribute, ast.Subscript, ast.Call)):
        node = node.func if isinstance(node, ast.Call) else node.value
    return node.id if isinstance(node, ast.Name) else None


def _dotted(node) -> List[str]:
    """A dotted name as its parts - np.random.seed is [np, random, seed]; nothing when it hangs on a call or a subscript."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    return [node.id] + parts[::-1] if isinstance(node, ast.Name) else []


def _state(name: List[str]) -> Optional[str]:
    """The global generator a dotted call draws from or seeds, as a name - random.x is the standard library's,
    np.random.x numpy's; none for a call that makes a generator of its own, or has nothing to do with one."""
    if "random" in name[:-1] and name[-1] not in _GENERATORS:
        return _RANDOM if name[:-1] == ["random"] else _NP_RANDOM
    return None


def _whole(target) -> set:
    """The names a target binds whole: x, and both in x, y = ...; none in x[k] = ... or x.a = ..., which change what x holds."""
    if isinstance(target, ast.Name):
        return {target.id}
    if isinstance(target, (ast.Tuple, ast.List)):
        return {n for t in target.elts for n in _whole(t)}
    return _whole(target.value) if isinstance(target, ast.Starred) else set()


class _Facts:
    """What a run of top-level statements does, from the code alone: the names it binds or changes in place (`defines`),
    the names it reads before binding them - what earlier code must give (`reads`), the names it binds whole, so that
    what they held before is not read after it (`kills`), and whether something rests on it, by its reason: it prints
    a RESULT line (`prints`); it is a check of the method's own that can stop the run - assert, raise (`checks`); it
    has an effect outside the names - a figure shown, a file saved or written, a bare call on a module such as a
    setting, a seed or a folder made (`anchored`). `fixed` marks an import, which stays wherever it is. The reads follow
    Python's scopes: a name bound by an earlier statement, a loop or with target, a function's parameters and locals, a
    comprehension's or lambda's own names, is not read from outside. Names the code reads without spelling them are
    read too: those inside a query or eval string; `namespace` marks a read through globals(), whose names are
    settled from the strings the code holds; eval and exec read every name (_ANY) and stay.

    `known` is what the chain's earlier statements established, and takes what these add: the functions defined - a
    call does what the body does: something may rest on it, it may change names outside itself and the objects it is
    handed - the names holding a random generator, the names bound by an import. A draw reads its generator's state and
    moves it on, so the draws before it are part of it; a bare call, whose value nobody takes, is there for its effect
    on the object it is called on and on the objects it is handed."""

    def __init__(self, stmts, known: Optional[dict] = None):
        self.defines, self.reads, self.kills, self.fixed, self.namespace = set(), set(), set(), False, False
        self.prints, self.checks, self.anchored = False, False, False
        self.known = known if known is not None else _known()
        self._bound, self._inside, self._params, self._handed = set(), 0, set(), set()
        for st in stmts:
            self._stmt(st, frozenset())
            self._top(st)

    # -- a top-level statement: what it binds whole, and what a bare call is there for
    def _top(self, st):
        if isinstance(st, ast.Assign):
            self.kills |= {n for t in st.targets for n in _whole(t)}
        elif isinstance(st, ast.AnnAssign) and st.value is not None:
            self.kills |= _whole(st.target)
        elif isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            self.kills.add(st.name)
        elif isinstance(st, (ast.Import, ast.ImportFrom)):
            names = {(a.asname or a.name).split(".")[0] for a in st.names}
            self.kills |= names
            self.known["modules"] |= names
            self.fixed = True
        elif isinstance(st, ast.Expr) and isinstance(st.value, ast.Call):
            call, name = st.value, _dotted(st.value.func)
            if name and name[-1] in _QUIET or isinstance(call.func, ast.Name) and call.func.id in self.known["functions"]:
                return                                           # a call that only shows; a function of the chain's, whose body says what it does
            if name and name[0] in self.known["modules"]:
                self.anchored = True
                if name[-1] == "seed" and _state(name):
                    self.kills.add(_state(name))
            handed = ([call.func.value] if isinstance(call.func, ast.Attribute) else []) + list(call.args) + [k.value for k in call.keywords]
            self.defines |= {n[0] for n in map(_dotted, handed) if n and n[0] not in self.known["modules"]}

    # -- binding
    def _change(self, root, local: frozenset):
        """A name changed in place: one from outside holds something else from here on; a parameter marks its function
        as changing what it is handed; a write through the namespace binds a name the code does not show, and stays."""
        if root in _NAMESPACE:
            self.anchored = True
        elif root and root not in local:
            self.defines.add(root)
        elif root in self._params:
            self._handed.add(root)

    def _bind(self, target, local: frozenset):
        if isinstance(target, ast.Name):
            if target.id not in local:                         # the chain's own name: also a function's global, bound when the function is called
                self.defines.add(target.id)
                if not self._inside:
                    self._bound.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for t in target.elts:
                self._bind(t, local)
        elif isinstance(target, ast.Starred):
            self._bind(target.value, local)
        elif isinstance(target, (ast.Attribute, ast.Subscript)):   # a mutation: the root is read, and redefined for what follows
            self._expr(target, local)
            self._change(_root(target), local)

    def _draw(self, state: str, seed: bool = False):
        """A global generator's state: a seed sets it, a draw reads it and moves it on."""
        if seed:
            self._bound.add(state)
        elif state not in self._bound:
            self.reads.add(state)
        self.defines.add(state)

    def _body(self, stmts, local: frozenset, positional: List[str], params: set) -> dict:
        """A function's body read apart from the code around it: what a call of it does - whether something rests on
        it, the outside names it changes and those it reads (as they are when it is called), whether it reads names
        through the namespace, its positional parameters and the parameters it changes in place. Defining it changes
        nothing; what its body reads is read where it is defined as well, the function being a value from there on."""
        held = (self.anchored, self.defines, self.reads, self.namespace, self._params, self._handed, self.prints)
        self.anchored, self.defines, self.reads, self.namespace, self._params, self._handed, self.prints = False, set(), set(), False, params, set(), False
        self._inside += 1
        for s2 in stmts:
            self._stmt(s2, local)
        self._inside -= 1
        does = {"anchored": self.anchored, "prints": self.prints, "changes": frozenset(self.defines), "reads": frozenset(self.reads),
                "namespace": self.namespace, "positional": tuple(positional), "handed": frozenset(self._handed)}
        self.anchored, self.defines, self._params, self._handed, self.prints = held[0], held[1], held[4], held[5], held[6]
        self.reads, self.namespace = held[2] | self.reads, held[3] or self.namespace
        return does

    def _call(self, node, does: dict, local: frozenset):
        """A call of a function the chain defined: what its body does, done here."""
        self.anchored = self.anchored or does["anchored"]
        self.prints = self.prints or does["prints"]
        self.namespace = self.namespace or does["namespace"]
        self.reads |= does["reads"] - self._bound - local - {_RANDOM, _NP_RANDOM}
        for name in does["changes"]:
            if name in (_RANDOM, _NP_RANDOM):
                self._draw(name)
            else:
                self._change(name, local)
        for arg in [a for p, a in zip(does["positional"], node.args) if p in does["handed"]] + [k.value for k in node.keywords if k.arg in does["handed"]]:
            self._change(_root(arg), local)

    def _stmt(self, st, local: frozenset):
        if isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in st.decorator_list + st.args.defaults + [d for d in st.args.kw_defaults if d is not None]:
                self._expr(d, local)
            args = st.args
            positional = [a.arg for a in args.posonlyargs + args.args]
            params = set(positional) | {a.arg for a in args.kwonlyargs} | ({args.vararg.arg} if args.vararg else set()) | ({args.kwarg.arg} if args.kwarg else set())
            inner = params | {n.id for n in ast.walk(st) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
            inner -= {name for g in ast.walk(st) if isinstance(g, ast.Global) for name in g.names}
            self.known["functions"][st.name] = self._body(st.body, local | frozenset(inner), positional, params)
            self._bind(ast.Name(id=st.name, ctx=ast.Store()), local)
        elif isinstance(st, ast.ClassDef):
            for d in st.decorator_list + st.bases:
                self._expr(d, local)
            inner = {n.id for n in ast.walk(st) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
            for s2 in st.body:
                self._stmt(s2, local | frozenset(inner))
            self._bind(ast.Name(id=st.name, ctx=ast.Store()), local)
        elif isinstance(st, (ast.For, ast.AsyncFor)):
            self._expr(st.iter, local)
            self._bind(st.target, local)
            self._block(st.body + st.orelse, local)
        elif isinstance(st, (ast.With, ast.AsyncWith)):
            for item in st.items:
                self._expr(item.context_expr, local)
                if item.optional_vars is not None:
                    self._bind(item.optional_vars, local)
            self._block(st.body, local)
        elif isinstance(st, (ast.Import, ast.ImportFrom)):
            for a in st.names:
                self._bound.add((a.asname or a.name).split(".")[0])      # bound, but not a definition: a dropped cell's imports are kept
        elif isinstance(st, ast.Assign):
            self._expr(st.value, local)
            if not local and isinstance(st.value, ast.Call) and (_dotted(st.value.func) or [""])[-1] in _GENERATORS:
                self.known["generators"] |= {n for t in st.targets for n in _whole(t)}
            for t in st.targets:
                self._bind(t, local)
        elif isinstance(st, ast.AugAssign):
            self._expr(st.value, local)
            self._expr(ast.Name(id=st.target.id, ctx=ast.Load()) if isinstance(st.target, ast.Name) else st.target, local)
            self._bind(st.target, local)
        elif isinstance(st, ast.AnnAssign):
            if st.value is not None:
                self._expr(st.value, local)
            self._bind(st.target, local)
        elif isinstance(st, (ast.If, ast.While)):
            self._expr(st.test, local)
            self._block(st.body + st.orelse, local)
        elif isinstance(st, ast.Try):
            self._block(st.body, local)
            for h in st.handlers:
                if h.type is not None:
                    self._expr(h.type, local)
                if h.name:
                    self._bind(ast.Name(id=h.name, ctx=ast.Store()), local)
                self._block(h.body, local)
            self._block(st.orelse + st.finalbody, local)
        elif isinstance(st, ast.Match):
            self._expr(st.subject, local)
            for case in st.cases:
                for n in ast.walk(case.pattern):
                    if isinstance(n, (ast.MatchAs, ast.MatchStar)) and n.name:
                        self._bind(ast.Name(id=n.name, ctx=ast.Store()), local)
                if case.guard is not None:
                    self._expr(case.guard, local)
                self._block(case.body, local)
        elif isinstance(st, ast.Delete):
            for t in st.targets:
                if isinstance(t, (ast.Attribute, ast.Subscript)):  # del d[k]: d holds something else from here on
                    self._bind(t, local)
        else:                                                  # Expr, Return, Raise, Assert, Global, Nonlocal, Pass, Break, Continue
            if isinstance(st, (ast.Assert, ast.Raise)) and not self._inside:
                self.checks = True                             # a check that can stop the run is the method's
            for child in ast.iter_child_nodes(st):
                if isinstance(child, ast.expr):
                    self._expr(child, local)

    def _block(self, stmts, local: frozenset):
        for s2 in stmts:
            self._stmt(s2, local)

    def _expr(self, node, local: frozenset):
        if isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load) and node.id not in self._bound and node.id not in local:
                self.reads.add(node.id)
            return
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp)):
            inner = set(local)
            for i, gen in enumerate(node.generators):
                self._expr(gen.iter, frozenset(inner) if i else local)
                inner |= {n.id for n in ast.walk(gen.target) if isinstance(n, ast.Name)}
                for cond in gen.ifs:
                    self._expr(cond, frozenset(inner))
            for elt in ([node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]):
                self._expr(elt, frozenset(inner))
            return
        if isinstance(node, ast.Lambda):
            args = node.args
            inner = {a.arg for a in args.args + args.posonlyargs + args.kwonlyargs} | ({args.vararg.arg} if args.vararg else set()) | ({args.kwarg.arg} if args.kwarg else set())
            for d in args.defaults + [d for d in args.kw_defaults if d is not None]:
                self._expr(d, local)
            self._expr(node.body, local | frozenset(inner))
            return
        if isinstance(node, ast.NamedExpr):
            self._expr(node.value, local)
            self._bind(node.target, local)
            return
        if isinstance(node, ast.Call):
            f, name = node.func, _dotted(node.func)
            if isinstance(f, ast.Name) and f.id == "RESULT":
                self.prints = True
            elif isinstance(f, ast.Name) and f.id in self.known["functions"] and f.id not in local:
                self._call(node, self.known["functions"][f.id], local)
            elif isinstance(f, ast.Attribute):
                if f.attr in _KEEP_ATTRS or f.attr.startswith("write_"):
                    self.anchored = True
                if f.attr in _MUTATORS or any(k.arg == "inplace" for k in node.keywords):
                    self._change(_root(f.value), local)
            if isinstance(f, ast.Name) and f.id in _OPAQUE and f.id not in local:
                self.anchored = True
                self.reads.add(_ANY)
            if isinstance(f, ast.Name) and f.id in _NAMESPACE and f.id not in local:
                self.namespace = True
            if isinstance(f, ast.Attribute) and f.attr in ("query", "eval"):      # an expression in a string reads names the code does not show
                texts = [c.value for c in ast.walk(node) if isinstance(c, ast.Constant) and isinstance(c.value, str)]
                self.reads |= {w for t in texts for w in re.findall(r"[A-Za-z_]\w*", t)} - self._bound - local
            for arg in list(node.args) + [k.value for k in node.keywords]:      # a function handed to a call may be called by it
                if isinstance(arg, ast.Name) and arg.id in self.known["functions"] and arg.id not in local:
                    self._call(ast.Call(func=arg, args=[], keywords=[]), self.known["functions"][arg.id], local)
            if _state(name):
                self._draw(_state(name), seed=name[-1] == "seed")
            for held in [name[:1]] + [[a.id] for a in list(node.args) + [k.value for k in node.keywords] if isinstance(a, ast.Name)]:
                if held and held[0] in self.known["generators"] and held[0] not in local:
                    self.defines.add(held[0])                  # a draw moves the generator it is made on, or handed
        for child in ast.iter_child_nodes(node):
            self._expr(child, local)


def _known() -> dict:
    """What the chain's statements establish as they are read in order (_Facts): the functions defined and what a call
    of each does, the names holding a random generator, the names bound by an import."""
    return {"functions": {}, "generators": set(), "modules": set(_MODULES)}


def _units(body) -> List[Tuple[int, int, list]]:
    """A cell's top-level statements as the pieces that are kept, dropped or run one at a time: (first line, last
    line, statements). Statements that share a line (a = 1; b = 2) are one piece."""
    units: List[Tuple[int, int, list]] = []
    for st in body:
        a = min([st.lineno] + [d.lineno for d in getattr(st, "decorator_list", [])])
        b = st.end_lineno or st.lineno
        if units and a <= units[-1][1]:
            units[-1] = (units[-1][0], max(units[-1][1], b), units[-1][2] + [st])
        else:
            units.append((a, b, [st]))
    return units


def read_steps(cells: str) -> Tuple[List[_Facts], List[Tuple[int, List[str]]], str]:
    """The cells read a statement at a time: (steps, blocks, problem). A step is a top-level statement's _Facts, which
    also knows where it stands - `cell` (the cell's number), `block` (which of the cells, by position), `first` and
    `last` (its lines within the cell, the marker being line 0), `source` (its text), `keys` (the inputs it reads),
    `strings` (the names its code holds as strings) - and `fixed` covers the capture switches between cells beside the
    imports. A block is a cell's (number, lines). A cell that does not parse leaves nothing read, and the problem
    says which."""
    known, steps, blocks = _known(), [], []
    for n, start, end in cell_blocks(cells):
        lines = cells[start:end].removesuffix("\n").split("\n")
        try:
            body = ast.parse("\n".join(lines[1:])).body
        except SyntaxError as exc:
            return [], [], f"cell {n} could not be parsed ({exc.msg})"
        for a, b, stmts in _units(body):
            f = _Facts(stmts, known)
            f.cell, f.block, f.first, f.last = n, len(blocks), a, b
            f.source = "\n".join(lines[a:b + 1])
            f.keys = set(_KEY_REF_RE.findall(f.source))
            f.strings = {c.value for st in stmts for c in ast.walk(st) if isinstance(c, ast.Constant) and isinstance(c.value, str) and c.value.isidentifier()}
            f.fixed = f.fixed or all(_CAPTURE_LINE_RE.match(ln) for ln in lines[a:b + 1])
            steps.append(f)
        blocks.append((n, lines))
    return steps, blocks, ""


def _stay(steps: List[_Facts], wanted: Iterable[int], inputs: bool = False) -> set:
    """The steps that stay when only `wanted` are asked for: those, the fixed ones, and every step a later staying step
    reads a name from - read from the last step to the first, a name bound whole ending the reading of what defined
    it before. A step that reads names through globals() reads the strings the staying code holds, so the answer is
    taken down to what holds itself up. With `inputs`, an input no staying step reads keeps its first reader."""
    wanted = set(wanted)

    def sweep(strings: set) -> set:
        live, kept = set(), set()
        for j in range(len(steps) - 1, -1, -1):
            f = steps[j]
            if f.fixed or j in wanted or (f.defines & live) or (f.defines and _ANY in live):
                kept.add(j)
                live = (live - f.kills) | f.reads | (strings if f.namespace else set())
        return kept
    kept = set(range(len(steps)))
    while True:
        was, kept = kept, sweep({w for j in kept for w in steps[j].strings})
        unread = ({k for f in steps for k in f.keys} - {k for j in kept for k in steps[j].keys}) if inputs else set()
        if unread:
            wanted |= {next(j for j, f in enumerate(steps) if k in f.keys) for k in unread}
            kept = set(range(len(steps)))
        elif kept == was:
            return kept


# ----------------------------------------------------------------------------- the promoter's view: the chain without its exploration
def _pruning(cells: str, figure_cells: Iterable[int]) -> Tuple[List[Tuple[int, List[str], set, bool]], str]:
    """What prune_cells and held_out share: for each cell (its number, its lines with the marker first, the lines that
    go, whether the whole cell goes), and the problem - a cell that does not parse prunes nothing. A statement stays
    when something rests on it - a RESULT line, a figure (its cell named, or a show / save / write call), a check
    that can stop the run, an input no other kept statement reads - or when a later kept statement reads a name it
    defines or changes; every other statement goes, with the comment lines standing on it. Imports and the capture
    switches stay wherever they are; a cell left with nothing else goes, marker included."""
    figs = {int(c) for c in figure_cells or []}
    steps, blocks, problem = read_steps(cells)
    if problem:
        return [], problem
    kept = _stay(steps, {j for j, f in enumerate(steps) if f.anchored or f.prints or f.checks or f.cell in figs}, inputs=True)
    plan = [(n, lines, set(), False) for n, lines in blocks]
    stays = {steps[j].block for j in kept if not steps[j].fixed}
    for i, (n, lines, gone, _) in enumerate(plan):
        if i not in stays:                                         # nothing of the cell is kept but what stays wherever it is
            plan[i] = (n, lines, set(range(len(lines))) - {x for f in steps if f.fixed and f.block == i for x in range(f.first, f.last + 1)}, True)
    for j, f in enumerate(steps):
        if f.block in stays and j not in kept:
            gone, lines, a = plan[f.block][2], plan[f.block][1], f.first
            gone.update(range(a, f.last + 1))
            while a > 1 and lines[a - 1].lstrip().startswith("#"):   # the comment lines standing on it
                a -= 1
                gone.add(a)
    return plan, ""


def prune_cells(cells: str, figure_cells: Iterable[int]) -> Tuple[str, List[int], int, str]:
    """The cells as the promoter reads them: without the exploration - a check on one row picked by eye, a table
    printed to look at, a second way of computing set beside the first - by the reading of _pruning. Markers keep
    their numbers. Returns (cells, the cells dropped, the lines dropped, problem); cells that need no pruning, or
    cannot be read, come back as they are."""
    plan, problem = _pruning(cells, figure_cells)
    if problem or not any(gone for _, _, gone, _ in plan):
        return cells, [], 0, problem
    out = [ln for _, lines, gone, _ in plan for x, ln in enumerate(lines) if x not in gone]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip("\n")
    return "\n" + text + "\n", [n for n, _, _, whole in plan if whole], sum(1 for _, lines, gone, _ in plan for x in gone if x and lines[x].strip()), ""


def held_out(cells: str, figure_cells: Iterable[int]) -> Tuple[str, List[str]]:
    """The whole chain with the lines prune_cells drops held out: each replaced by a HELD line, and those lines in
    order. The promoter's edits were found in the pruned view; applied to this text they land exactly where they
    landed there - a fragment cannot match in a line that is held out, however often the chain repeats it - and
    put_back returns the lines: the chain as written, with the same edits."""
    plan, _problem = _pruning(cells, figure_cells)
    if not plan:
        return cells, []
    blocks = cell_blocks(cells)
    text = cells[:blocks[0][1]] + "".join("\n".join(HELD if x in gone else ln for x, ln in enumerate(lines)) + ("\n" if cells[start:end].endswith("\n") else "")
                                          for (_, start, end), (_, lines, gone, _) in zip(blocks, plan))
    return text, [lines[x] for _, lines, gone, _ in plan for x in sorted(gone)]


def put_back(cells: str, lines: List[str]) -> str:
    """held_out undone: the HELD lines of the text replaced by the lines they stood for, in order."""
    it = iter(lines)
    return "\n".join(next(it, "") if ln == HELD else ln for ln in cells.split("\n"))


# ----------------------------------------------------------------------------- a run, a statement at a time
STEP_MARK = "ROUTINE_AT:"                   # printed before each statement runs: the output that follows is that statement's
RUN_MARK = "ROUTINE_RUN:"                   # printed last: the statements that stopped and those skipped for resting on them

STEPWISE = """# --- the cells, a statement at a time: one that stops costs what rests on it, not the run
def _routine_steps(steps, frame, watch):
    import inspect, json
    g, missing, say = globals(), object(), print
    plain = (int, float, complex, str, bytes, bool, type(None))
    names, objects, stopped, skipped, now = {}, {}, [], [], {"halted": None}
    df, gaps = g.get("df"), {}
    try:                                    # how much of each watched column is empty: [rows empty, rows, groups empty, groups]
        by = (watch or {}).get("by")
        columns = [c for c in (watch or {}).get("columns") or [] if c in df]
        filled = df.groupby(by)[columns].count() if by and columns else []
        for c in columns:
            gaps[c] = [int(df[c].isna().sum()), int(len(df))] + ([int((filled[c] == 0).sum()), int(len(filled))] if len(filled) else [])
    except Exception:
        gaps = {}
    try:
        empty = bool(frame) and len(df) == 0
    except Exception:
        empty = False

    def spoil(written, origin):
        for w in written:
            names[w] = origin
            v = g.get(w, missing)
            if v is not missing and not isinstance(v, plain):
                objects[id(v)] = origin

    def rests_on(reads):
        if now["halted"] is not None:
            return now["halted"]
        for r in reads:
            if r in names:
                return names[r]
        if "*" in reads and names:
            return next(iter(names.values()))
        for r in reads:
            v = g.get(r, missing)
            if v is not missing and not isinstance(v, plain) and id(v) in objects:
                return objects[id(v)]
        return None

    def go(j):
        if empty:                           # nothing to run on: the statements are left alone
            return False
        cell, first, reads, writes, binds, check = steps[j]
        origin = rests_on(reads)
        if origin is not None:
            skipped.append([j, cell, origin])
            spoil(writes, origin)
            return False
        say("__AT__ %d" % j)
        now.update(step=j, line=inspect.currentframe().f_back.f_lineno + 2, held=[id(g[w]) for w in writes if w in g and not isinstance(g[w], plain)])
        return True

    def end(exc=None):
        j = now["step"]
        cell, first, reads, writes, binds, check = steps[j]
        if exc is None:
            for w in binds:
                names.pop(w, None)
            return
        stopped.append({"step": j, "cell": cell, "line": first + exc.__traceback__.tb_lineno - now["line"], "error": ("%s: %s" % (type(exc).__name__, exc))[:300]})
        for i in now["held"]:
            objects[i] = j
        spoil(writes, j)
        if check or isinstance(exc, SystemExit):
            now["halted"] = j

    def close():
        say("__RUN__ " + json.dumps({"empty": empty, "stopped": stopped, "skipped": skipped, "gaps": gaps}))
    return go, end, close


_routine_go, _routine_end, _routine_close = _routine_steps(__STEPS__, __FRAME__, __WATCH__)
""".replace("__AT__", STEP_MARK).replace("__RUN__", RUN_MARK)

STEP = """if _routine_go({j}):
    try:
{code}
    except (Exception, SystemExit) as _routine_exc:
        _routine_end(_routine_exc)
    else:
        _routine_end()
"""


def needed_steps(cells: str, tracked: Iterable[int], figure_cells: Iterable[int]) -> Optional[List[int]]:
    """The statements a run needs for the lines it tracks and the figures it draws: the steps that printed a tracked
    line (`tracked`, by their place among the steps), every statement of a figure cell, a file saved or written, a
    check that can stop the run, and what those read - by the same reading that prunes the promoter's view. The
    rest of the chain - the lines nobody tracks and what only they needed - is not run. None when a cell cannot be
    read."""
    steps, _blocks, problem = read_steps(cells)
    if problem:
        return None
    figs, tracked = {int(c) for c in figure_cells or []}, set(tracked or [])
    return sorted(_stay(steps, {j for j, f in enumerate(steps) if f.anchored or f.checks or j in tracked or f.cell in figs}))


def _moved_in(source: str, by: str = "        ") -> Optional[str]:
    """A statement's lines moved in under a `try:` - every line but those that begin inside a string, whose text is
    the string's own. None when the statement cannot be read as tokens."""
    inside, opened = set(), []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source + "\n").readline):
            kind = tokenize.tok_name[tok.type]
            if kind.endswith("STRING_START"):                      # an f-string's parts are tokens of their own (python 3.12)
                opened.append(tok.start[0])
            elif kind.endswith("STRING_END") and opened:
                first = opened.pop()
                if not opened:
                    inside.update(range(first + 1, tok.end[0] + 1))
            elif tok.type == tokenize.STRING and not opened:
                inside.update(range(tok.start[0] + 1, tok.end[0] + 1))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return None
    return "\n".join(ln if n in inside or not ln.strip() else by + ln for n, ln in enumerate(source.split("\n"), 1))


def stepwise(script: str, only: Optional[Iterable[int]] = None, watch: Optional[dict] = None) -> str:
    """The script as a run executes it: everything before the first cell as it is, then each of the cells' statements
    under a try of its own, in the script's own namespace. A statement that stops with an error spoils the names it
    writes; a later statement that reads a spoiled name - or, at that moment, an object a spoiled name is bound to -
    is skipped and spoils what it writes in turn; everything else runs. A check of the method's own that stops
    (assert, raise) stops what follows it. `only` names the statements to run (needed_steps), by their place among
    the steps; the others are left out. A frame with no rows, when the statements read the frame, runs none of them.
    `watch` ({columns, by}) names the frame's columns whose empty share the run reports, by rows and, with `by`, by
    the groups of that column. Each statement's output follows a STEP_MARK line, and a RUN_MARK line closes the run
    with what stopped, what was skipped and the empty shares (read_run). A script whose cells cannot be read, or
    whose statements cannot be laid out so, comes back as it is and runs as one piece."""
    header, cells, tail, order = split_script(script)
    steps, _blocks, problem = read_steps(cells) if order else ([], [], "")
    want = None if only is None else set(only)
    taken = [(j, f, _moved_in(f.source)) for j, f in enumerate(steps) if want is None or j in want]
    if problem or not taken or any(code is None for _j, _f, code in taken):
        return script
    table = {j: [f.cell, f.first, sorted(f.reads | (f.strings if f.namespace else set())), sorted(f.defines), sorted(f.kills), bool(f.checks)] for j, f, _code in taken}
    frame = any(f.reads & {"df", "DS"} for _j, f, _code in taken)
    text = (header + "\n" + STEPWISE.replace("__STEPS__", repr(table)).replace("__FRAME__", repr(frame)).replace("__WATCH__", repr(dict(watch or {})))
            + "".join(STEP.format(j=j, code=code) for j, _f, code in taken) + "_routine_close()\n" + tail.lstrip("\n"))
    try:
        ast.parse(text)
    except SyntaxError:
        return script
    return text


def names_in(cells: str) -> set:
    """The names the cells' code spells as strings or as attributes: df['x'], df.x, by='x' all give x. Empty when a
    cell cannot be read."""
    out = set()
    for _n, start, end in cell_blocks(cells):
        try:
            tree = ast.parse(cells[start:end].split("\n", 1)[1] if "\n" in cells[start:end] else "")
        except SyntaxError:
            return set()
        out |= {c.value for c in ast.walk(tree) if isinstance(c, ast.Constant) and isinstance(c.value, str)} | {a.attr for a in ast.walk(tree) if isinstance(a, ast.Attribute)}
    return out


def steps_key(script: str) -> str:
    """A mark of the statements the script's cells read into, in order. A place among them - a line's `at`, the
    statements of the shorter run - holds while the mark is the same; '' when the cells cannot be read."""
    _header, cells, _tail, order = split_script(script)
    steps = read_steps(cells)[0] if order else []
    return hashlib.sha256("\x00".join(f.source for f in steps).encode("utf-8")).hexdigest()[:12] if steps else ""


def read_run(stdout: str) -> dict:
    """A stepwise run's output read back: {lines: the RESULT lines in order, each (step, k, line) - the statement that
    printed it and its place among that statement's lines; stopped: the statements that stopped ({step, cell, line,
    error}); skipped: those skipped ([step, cell, the step that stopped]); empty: the frame had no rows and
    nothing was run; gaps: the watched columns' empty shares; stdout: the output without the marks; stepwise: whether
    the run closed with its RUN_MARK}. Output with no marks (a script run as one piece) gives its lines with no step."""
    lines, kept, step, count, report = [], [], None, {}, None
    for ln in (stdout or "").splitlines():
        s = ln.strip()
        if s.startswith(STEP_MARK):
            try:
                step = int(s[len(STEP_MARK):])
            except ValueError:
                step = None
            continue
        if s.startswith(RUN_MARK):
            try:
                report = json.loads(s[len(RUN_MARK):])
            except ValueError:
                report = None
            continue
        kept.append(ln)
        if s.startswith("RESULT:"):
            r = parse_result_line(ln)
            if r is not None:
                lines.append((step, count.get(step, 0), r))
                count[step] = count.get(step, 0) + 1
    report = report if isinstance(report, dict) else None
    return {"lines": lines, "stopped": list((report or {}).get("stopped") or []), "skipped": [list(x) for x in (report or {}).get("skipped") or []],
            "empty": bool((report or {}).get("empty")), "gaps": dict((report or {}).get("gaps") or {}),
            "stdout": "\n".join(kept) + ("\n" if kept and (stdout or "").endswith("\n") else ""), "stepwise": report is not None}


NO_NUMBER = "no number on this data"           # the reasons a line has no number: it printed nan,
NO_DATA = "no data in this window"             # the frame had no rows,
NO_LINE = "not printed on this data"           # nothing printed it and nothing stopped,
NO_ESTIMATE = "not a number in the analysis"   # the analysis itself had none


def _blank(why: str, line: Optional[dict] = None) -> dict:
    """An expected line that did not come back with a number, and why."""
    return dict(line or {}, estimate=None, low=None, high=None, why=why)


def place_lines(expected: List[dict], run: dict) -> dict:
    """A run's lines laid against the expected ones: {results, at}. `results` has one entry per expected line,
    in their order - the line as printed, or a blank that says why it is missing ({estimate: None, why}): the
    statement that should have printed it stopped, or rests on one that stopped (the reason names that one), or the
    line came without a number. Lines are known by the statement that printed them and their place among its lines
    (`at` on the expected line: [step, k]); a version that does not know them yet is read by position, up to the
    first statement that did not run. `at` is what a complete run teaches: each expected line's [step, k] (None
    when the run was not complete, or was not stepwise)."""
    exp = list(expected or [])
    if run.get("empty"):
        return {"results": [_blank(NO_DATA) for _e in exp], "at": None}
    lines = run.get("lines") or []
    stopped = {int(s["step"]): s for s in run.get("stopped") or [] if s.get("step") is not None}
    skipped = {int(j): (cell, origin) for j, cell, origin in run.get("skipped") or []}

    def why(step) -> str:                                          # the statement that stopped: the line's own, or the one it rests on
        origin = stopped.get(step) or stopped.get(skipped.get(step, (None, None))[1])
        return f"cell {origin['cell']} stopped: {origin['error']}" if origin else NO_LINE

    def read(line: dict) -> dict:
        v = number(line.get("estimate"))
        return _blank(NO_NUMBER, line) if v is not None and v != v else dict(line)
    counted = [e for e in exp if e.get("estimate") is not None]
    known = bool(counted) and all(isinstance(e.get("at"), (list, tuple)) and len(e["at"]) == 2 for e in counted)
    results = []
    if known and run.get("stepwise"):
        by_place = {(s, k): ln for s, k, ln in lines}
        for e in exp:
            at = tuple(e["at"]) if e.get("estimate") is not None else None
            if at is None:
                results.append(_blank(NO_ESTIMATE))
            elif at in by_place:
                results.append(read(by_place[at]))
            else:
                results.append(_blank(why(at[0])))
    else:                                                          # by position: sure only up to the first statement that did not run
        troubled = min(list(stopped) + list(skipped), default=None)
        sure = [ln for s, k, ln in lines if troubled is None or (s is not None and s < troubled)]
        it = iter(sure)
        for e in exp:
            ln = next(it, None) if e.get("estimate") is not None else None
            if ln is not None:
                results.append(read(ln))
            elif e.get("estimate") is None:
                results.append(_blank(NO_ESTIMATE))
            else:
                results.append(_blank(why(troubled)))
    complete = run.get("stepwise") and not stopped and not skipped and len(lines) == len(counted)
    places = iter(lines)
    at = [list(next(places)[:2]) if e.get("estimate") is not None else None for e in exp] if complete else None
    return {"results": results, "at": at}


# ----------------------------------------------------------------------------- two runs' figures, compared
def _fig_payload(fig):
    """The figure under the tabs' wrapper ({type, data, format, id, chain_id}): the Plotly object when the data is JSON,
    else the data as it is (a PNG's base64)."""
    o = fig
    if isinstance(o, str):
        try:
            o = json.loads(o)
        except ValueError:
            return o
    if isinstance(o, dict) and "data" in o and ("format" in o or "type" in o):
        o = o["data"]
    if isinstance(o, str):
        try:
            o = json.loads(o)
        except ValueError:
            pass
    return o


def _same_typed(a: dict, b: dict) -> bool:
    """Plotly's typed arrays ({dtype, bdata, shape}) compared as numbers."""
    if a.get("dtype") != b.get("dtype") or a.get("shape") != b.get("shape"):
        return False
    try:
        import base64
        import numpy as np
        x = np.frombuffer(base64.b64decode(a.get("bdata") or ""), dtype=np.dtype(a["dtype"]))
        y = np.frombuffer(base64.b64decode(b.get("bdata") or ""), dtype=np.dtype(b["dtype"]))
        if x.shape != y.shape:
            return False
        return bool(np.allclose(x, y, rtol=1e-9, atol=1e-12, equal_nan=True)) if x.dtype.kind in "fc" else bool(np.array_equal(x, y))
    except Exception:                                          # noqa: BLE001 - no numpy, or bytes that are not the dtype's
        return a == b


def _close(a, b) -> bool:
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if a != a and b != b:
            return True
        return a == b or abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            return False
        if "bdata" in a and "dtype" in a:
            return _same_typed(a, b)
        return all(_close(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_close(x, y) for x, y in zip(a, b))
    return a == b


def same_figures(expected: Iterable, got: Iterable) -> Tuple[bool, str]:
    """The figures of a run against run zero's: the same count, each the same picture - a Plotly figure by its data and
    layout (numbers within a relative 1e-9, nan as nan), a PNG byte for byte. (ok, why)."""
    exp, now = list(expected or []), list(got or [])
    if len(exp) != len(now):
        return False, f"{len(now)} figure{'s' if len(now) != 1 else ''} came back, {len(exp)} expected"
    for i, (x, y) in enumerate(zip(exp, now), 1):
        if not _close(_fig_payload(x), _fig_payload(y)):
            return False, f"figure {i} differs"
    return True, (f"{len(exp)} figure{'s' if len(exp) != 1 else ''} identical" if exp else "no figures")


# ----------------------------------------------------------------------------- a run: the checks before it
def fit_check(expected: Iterable[dict], now: Iterable[dict]) -> dict:
    """The data loaded now against the routine's schema (the columns the analysis ran on): a run needs every
    expected column; extra columns are fine; a column whose dtype changed is noted, not refused."""
    exp = {str(c.get("name")): str(c.get("dtype") or "") for c in (expected or []) if c.get("name") is not None}
    cur = {str(c.get("name")): str(c.get("dtype") or "") for c in (now or []) if c.get("name") is not None}
    missing = [n for n in exp if n not in cur]
    extra = [n for n in cur if n not in exp]
    retyped = [(n, exp[n], cur[n]) for n in exp if n in cur and exp[n] and cur[n] and dtype_family(exp[n]) != dtype_family(cur[n])]
    present = len(exp) - len(missing)
    # a column this data lacks is added empty before the method runs (conform_prelude): said here, refused only when
    # none of the recorded columns is in this data - nothing of the method's data to run on (2026-10-10)
    fits = (present > 0) if exp else bool(cur)
    if exp and not present:
        line = f"none of the routine's {len(exp)} columns is in this data - nothing to run on"
    elif missing:
        shown = ", ".join(missing[:6]) + (" ..." if len(missing) > 6 else "")
        line = f"{len(missing)} of {len(exp)} columns empty in this data: {shown}" + (f"; {len(extra)} more" if extra else "")
    elif not exp:
        line = "the routine recorded no columns to check against; it will run as it is"
    else:
        line = f"fits the routine ({len(exp)} of {len(exp)} columns" + (f", {len(extra)} more" if extra else "") + ")"
    if retyped and present:
        line += "; " + ", ".join(f"{n} is now {dtype_family(b)} (was {dtype_family(a)})" for n, a, b in retyped[:3]) + " - read back as it was"
    return {"fits": fits, "missing": missing, "extra": extra, "retyped": retyped, "expected": len(exp), "now": len(cur), "line": line}


# ----------------------------------------------------------------------------- the data's shape, and a run's data made to fit it
# The loaders name their auxiliary files after the window or the race (activity_summary_<start>_to_<end>.csv,
# athlete_profiles_race_<id>.csv); a method reads them by those names. A run binds each recorded file, by kind, to the
# file this load produced, and the executed text carries this load's names; the stored method is not changed.
AUX_KINDS = (("activity_summary_", "summary"), ("wellness_data_", "wellness"), ("activity_intervals_", "intervals"),
             ("context_notes_", "context"), ("context_codes_", "codes"),        # the words beside the data and the model's reading of them (2026-10-13)
             ("planned_workouts_", "plan"),                                       # the prescription: the calendar's planned workouts with their numbers and steps (2026-10-15)
             ("athlete_profiles_race_", "profile"), ("race_turns_race_", "turns"), ("race_climbs_race_", "climbs"),
             ("race_waymarkers_race_", "waymarkers"),
             ("rider_profile_", "rider"), ("custom_zone_times_", "zones"))     # the rider profile and the custom zone times (2026-10-16, docs/RIDER_PROFILE_DESIGN.md)
_STRING_RE = re.compile(r"""(?P<q>'|")(?P<body>(?:(?!(?P=q)).)*)(?P=q)""")
# What a load can be asked for, per source (2026-10-16: one registry, where load_plan and the limits read it). The kinds a
# load *brings without being asked* ride beside the kind that asks for them: the codes with the context (the pass behind the
# load writes them), the planned workouts with the context (the page asks for both). LOADER_FILES_MAX is the most files one
# load can bring - the app's auxiliary limit is derived from it, so a new kind never trips the limit again (the sixth did).
LOAD_KINDS = {"intervals": ("summary", "wellness", "intervals", "context", "plan", "rider"), "endura": ("profile", "turns", "climbs", "waymarkers")}
LOAD_BRINGS = {"intervals": {"context": ("codes",), "rider": ("zones",)}, "endura": {}}
# a brought kind the loader writes only when the account defines what it holds (the custom zone times, when the account has
# custom zone sets): its absence beside a cached load is not a miss, and a run binds an empty table for it
BRINGS_IF_DEFINED = ("zones",)
LOADER_FILES_MAX = max(len(kinds) + sum(len(v) for v in LOAD_BRINGS.get(src, {}).values()) for src, kinds in LOAD_KINDS.items())


# the kinds' names for a reader (2026-10-17: the report's head says what data a report stands on); a kind without a name
# reads as its kind, a brought kind named None rides under the kind that brought it (the codes under the context)
KIND_NAMES = {"summary": "activity summary", "wellness": "wellness", "intervals": "activity intervals", "context": "context", "codes": None,
              "plan": "planned workouts", "rider": "rider profile", "zones": "custom zone times",
              "profile": "profiles", "turns": "turns", "climbs": "climbs", "waymarkers": "waymarkers"}
SOURCE_NAMES = {"intervals": "Intervals.icu", "endura": "Endura", "sweatstack": "SweatStack"}


def data_line(rec: dict) -> str:
    """One line saying what data a report stands on, from a run's data record: the source and its window or event, then
    the auxiliary files by their names - 'Intervals.icu · 2026-01-01 to 2026-03-31 · activity summary, wellness, context,
    planned workouts'; an attached file by its name; 'no dataset' with the files alone when there is no frame."""
    rec = rec or {}
    load = rec.get("load") or {}
    src = str(load.get("source") or rec.get("source") or "")
    kinds = []
    for p in rec.get("aux") or []:
        k = aux_kind(str(p))
        if k not in kinds:
            kinds.append(k)
    names = [KIND_NAMES.get(k, k[5:] if k.startswith("file:") else k) for k in kinds]
    names = [n for n in names if n]
    start, end = load.get("start_date") or "", load.get("end_date") or ""
    if not (start and end) and rec.get("date_range"):
        m = _RANGE_RE.match(str(rec["date_range"]))
        if m:
            start, end = m.group(1), m.group(2)
    extra = rec.get("extra") or {}
    rows = rec.get("rows")
    count = (f" · {int(extra['activities_count']):,} activities" if isinstance(extra.get("activities_count"), (int, float)) and extra["activities_count"] else "")
    if src == "intervals":
        who = str((load.get("subject") or {}).get("name") or "")      # whose data (2026-10-29): the page's head, never a prompt
        head = SOURCE_NAMES[src] + (f" · {who}" if who else "") + (f" · {start} to {end}" if start and end else "") + count
    elif src == "endura":
        head = SOURCE_NAMES[src] + (f" · {load.get('race_title') or load.get('race_id')}" if (load.get('race_title') or load.get('race_id')) else "")
    elif src == "sweatstack":
        head = SOURCE_NAMES[src] + (f" · {start} to {end}" if start and end else "") + (" · " + ", ".join(str(s) for s in load.get("sports") or []) if load.get("sports") else "")
    elif src == "none" or (not rec.get("name") and rows is None and not rec.get("df_id")):
        head = "no dataset" if not names else ""
    else:
        name = str(rec.get("name") or load.get("name") or "")
        size = f"{int(rows):,} rows" if isinstance(rows, (int, float)) and rows is not None else ""
        head = (name + (f" · {size}" if size else "")) if name else (f"a dataset of {size}" if size else "an attached dataset")
    return head + ((" · " if head else "") + ", ".join(names) if names else "")


def brings(src: str, kinds: Iterable[str]) -> List[str]:
    """The kinds a load of these kinds brings without being asked (LOAD_BRINGS), in order, each once: the codes beside
    the context."""
    out: List[str] = []
    for k in kinds:
        for b in LOAD_BRINGS.get(str(src), {}).get(str(k), ()):
            if b not in out:
                out.append(b)
    return out


CONTEXT_HEADER_BYTES = 300     # a context file of its header alone (sixteen column names) is well under this; any passage takes it past


def context_empty(binding: dict, shape: Optional[dict]) -> bool:
    """Whether the context file this load has holds no passages, from the run's shape probe (rows of each bound file):
    a window without words (2026-10-14)."""
    files = (shape or {}).get("files") or {}
    for old in (binding or {}).get("map") or {}:
        if aux_kind(old) == "context":
            info = files.get(old)
            return isinstance(info, dict) and info.get("rows") == 0
    return False


def aux_kind(path: str) -> str:
    """The kind of an auxiliary file from its name: a loader's kind (summary, wellness, intervals, profile, turns,
    climbs, waymarkers) or, for a file the person attached, its name."""
    base = os.path.basename(str(path or ""))
    for prefix, kind in AUX_KINDS:
        if base.startswith(prefix):
            return kind
    return "file:" + base


def kind_prefix(kind: str) -> str:
    """The loader's file-name prefix for an auxiliary kind (summary -> activity_summary_)."""
    return next((p for p, k in AUX_KINDS if k == kind), "")


# the kinds the Intervals loader writes for a subject - LOAD_KINDS["intervals"] and what those bring (2026-10-29)
INTERVALS_KINDS = ("summary", "wellness", "intervals", "context", "plan", "rider", "codes", "zones")


def subject_of_record(data: Optional[dict]) -> dict:
    """Whose data a record is (2026-10-30): {id, name} from its load's subject; {} when the load names none (an upload,
    a race, a record from before the subject was kept)."""
    load = (data or {}).get("load") or {}
    sub = load.get("subject") if isinstance(load.get("subject"), dict) else {}
    return {"id": str(sub.get("id") or ""), "name": str(sub.get("name") or "")} if sub.get("id") else {}


def loader_file(path: str) -> bool:
    """Whether a file is one the Intervals loader writes for a subject, by its name; an upload or a race file is not."""
    return aux_kind(path) in INTERVALS_KINDS


def other_subjects_file(path: str, folder: str) -> bool:
    """Whether a session file is another subject's than `folder` (intervals/<id>): a loader's file not under that subject's
    views/ - whatever path an earlier load gave it (2026-10-29: one subject at a time on the Data tab; the page's
    intervalsOtherAthletePills reads the pills the same way)."""
    p = str(path or "").replace("\\", "/")
    return bool(folder) and loader_file(p) and ("/" + str(folder) + "/views/") not in p


_RANGE_RE = re.compile(r"^\s*(\d{4}-\d{2}-\d{2})\s*(?:to|->|-|→)\s*(\d{4}-\d{2}-\d{2})\s*$")


def key_fingerprint(key) -> str:
    """A short, one-way mark of an API key (2026-10-11): which credential loaded, without the key itself. The executor's
    loader writes the same mark on each frame it caches (`key_mark` there, the same formula) and on the subject's
    record beside the files (the marks that have loaded that subject, since 2026-10-29; before that the mark named
    the folder), so a coach who changes the key to look at another subject is never served the first one's cached
    windows (`cache_match`)."""
    import hashlib
    k = str(key or "").strip()
    return hashlib.sha256(k.encode("utf-8")).hexdigest()[:12] if k else ""


def folder_of(entry: dict) -> str:
    """The load folder a cached frame or a listed file is under, relative to the user's: the subject's (`folder`, since
    2026-10-29) or the key's mark (older loads); "" for an upload at the top."""
    return str((entry or {}).get("folder") or (entry or {}).get("key_mark") or "")


def subject_of_key(inspect: Optional[dict], key: Optional[str]) -> str:
    """The id of the subject a key loads, by the executor's records: the subject whose marks include the key's mark
    (`subjects` in the inspection, since 2026-10-29); "" when the key has not loaded yet, or the records predate them."""
    k = str(key or "")
    if not k:
        return ""
    for rec in (inspect or {}).get("subjects") or []:
        if isinstance(rec, dict) and k in [str(m) for m in rec.get("marks") or []]:
            return str(rec.get("id") or "")
    return ""


def cache_match(plan: dict, inspect: Optional[dict], start: Optional[str] = None, end: Optional[str] = None, race_id=None,
                key: Optional[str] = None, subject: Optional[str] = None) -> dict:
    """Whether the load a run dialog asks for is already in the executor's cache (2026-10-11: a run re-downloaded a
    window the Data tab had loaded minutes before): a cached frame of the same source with the same window (Intervals:
    date_range, and the same metrics) or the same race (Endura), and every auxiliary file of the kinds the routine
    wants there beside it under the loader's name for that load. A cached window that *contains* the one asked is a
    hit too (the same day: a window inside a cached load was downloaded again) - the run then cuts the frame and the
    files to the window before the method runs (`cut`: the cached load's window). SweatStack's entries do not say
    which subjects they hold, so they never match. With `key` (the mark of the key in use), an Intervals frame counts
    only when the loader marked it with the same key, and its files are looked for in that key's folder; a frame
    without a mark (cached before the loader marked them) is downloaded this once. Since 2026-10-29 (docs/DATASETS_DESIGN.md)
    a load is the subject's, not the key's: the executor's records (`subjects` in the inspection, one per subject with
    the marks of the keys that loaded it) say whose data the key in use loads, and when they do, a cached frame counts
    when it carries that subject's id, whatever key loaded it (a rotated key serves its subject's cached windows once
    it has loaded once); `subject` names the subject outright (the next phase's dropdown) and outranks the key. The
    files are looked for in the frame's folder (`folder`: the subject's, or the mark's for an older load). Returns
    {hit, df_id, files, rows, cut?, line}; `line` says why when there is no hit."""
    src = str((plan or {}).get("source") or "")
    frames = [f for f in ((inspect or {}).get("cached_dataframes") or []) if isinstance(f, dict)]
    have: Dict[Tuple[str, str], str] = {}                       # (the load's folder, the file's name) -> its path
    for f in (inspect or {}).get("auxiliary_datasets") or []:
        p = str((f or {}).get("path") or (f or {}).get("filename") or "")
        if p:
            have[(folder_of(f), os.path.basename(p))] = p
    kinds = [str(k) for k in (plan or {}).get("aux_kinds") or []]
    sizes: Dict[Tuple[str, str], float] = {}                     # (the load's folder, the file's name) -> its size in bytes, when listed
    for f in (inspect or {}).get("auxiliary_datasets") or []:
        p = str((f or {}).get("path") or (f or {}).get("filename") or "")
        if p and isinstance((f or {}).get("size_mb"), (int, float)):
            sizes[(folder_of(f), os.path.basename(p))] = float(f["size_mb"]) * 1024 * 1024
    who = str(subject or "") or subject_of_key(inspect, key)       # whose data the run would load, when known
    if src == "intervals":
        if not (start and end):
            return {"hit": False, "line": ""}
        metrics = sorted(str(m) for m in (plan or {}).get("metrics") or [])
        same = [f for f in frames if str(f.get("source")) == "intervals" and sorted(str(m) for m in (f.get("metrics") or [])) == metrics]
        what = f"this window ({start} → {end})"
        exact, around = [], []
        for f in same:
            m = _RANGE_RE.match(str(f.get("date_range") or ""))
            if not m:
                continue
            cs, ce = m.group(1), m.group(2)
            if (cs, ce) == (str(start), str(end)):
                exact.append((f, cs, ce))
            elif cs <= str(start) and ce >= str(end):
                around.append((f, cs, ce))
        if not exact and not around:
            return {"hit": False, "line": f"{what} is not in the cache - it will be downloaded"}
        if key is not None or who:
            # whose: the subject's frames when the records say whose data the key in use loads (2026-10-29), else only
            # the frames the loader marked with that key; a frame of another subject, or marked with another key, is
            # another subject's window; an unmarked one is from before the loader marked them
            def mine(f):
                fs = str(((f or {}).get("subject") or {}).get("id") or "")
                if who and fs:
                    return fs == who
                return key is not None and str((f or {}).get("key_mark") or "") == str(key)
            covering = exact + around
            exact = [t for t in exact if mine(t[0])]
            around = [t for t in around if mine(t[0])]
            if not exact and not around:
                if who and any(str(((t[0] or {}).get("subject") or {}).get("id") or "") for t in covering):
                    return {"hit": False, "line": f"{what} is in the cache but was loaded for another subject - it will be downloaded"}
                if any(str(t[0].get("key_mark") or "") for t in covering):
                    return {"hit": False, "line": f"{what} is in the cache but was loaded under another key - it will be downloaded"}
                return {"hit": False, "line": f"{what} is in the cache from before loads were marked with their key - it will be downloaded this once"}
        # the exact window first, the newest of them; else the smallest cached load around it (the least to cut)
        exact.reverse()
        around.sort(key=lambda t: ((t[0].get("shape") or [0])[0] or 0))
        candidates = exact + around
        for f, cs, ce in candidates:
            tag = f"{cs.replace('-', '')}_to_{ce.replace('-', '')}"
            folder = folder_of(f)
            names = {k: f"{kind_prefix(k)}{tag}.csv" for k in kinds if kind_prefix(k)}
            # the files a load brings beside the kinds asked (LOAD_BRINGS) are wanted too: the codes the pass wrote beside
            # the context (2026-10-14) - unless the cached context file is its header alone, a window without words, for
            # which no pass runs and no codes file exists
            for b in brings(src, kinds):
                if b == "codes" and sizes.get((folder, names.get("context", "")), CONTEXT_HEADER_BYTES + 1) <= CONTEXT_HEADER_BYTES:
                    continue
                if b in BRINGS_IF_DEFINED and (folder, f"{kind_prefix(b)}{tag}.csv") not in have:
                    continue                                        # the account defines none: no file, no miss
                if kind_prefix(b):
                    names[b] = f"{kind_prefix(b)}{tag}.csv"
            missing = [k for k, n in names.items() if (folder, n) not in have]
            if missing:
                continue
            rows = (f.get("shape") or [None])[0]
            size = (f" ({int(rows):,} rows" + (", with " + ", ".join(names) if names else "") + ")") if rows is not None else ""
            out = {"hit": True, "df_id": str(f.get("df_id") or ""), "files": [have[(folder, n)] for n in names.values()], "rows": rows, "date_range": f"{cs} to {ce}", "folder": folder}   # whose folder (2026-10-29): on the pill's record, for the cache dialog's dots
            if (cs, ce) == (str(start), str(end)):
                out["line"] = f"{what} is in the cache{size} - no download"
            else:
                out["cut"] = [cs, ce]
                out["line"] = f"{what} is inside the cached load {cs} → {ce}{size} - it will be cut to the window, no download"
            return out
        f, cs, ce = candidates[0]
        tag = f"{cs.replace('-', '')}_to_{ce.replace('-', '')}"
        folder = folder_of(f)
        missing = [k for k in kinds + [b for b in brings(src, kinds) if b not in BRINGS_IF_DEFINED] if kind_prefix(k) and (folder, f"{kind_prefix(k)}{tag}.csv") not in have]
        held = what if exact else f"the cached load around {what}"
        return {"hit": False, "line": f"{held} is in the cache without {', '.join(missing)} - it will be downloaded"}
    elif src == "endura":
        if race_id in (None, ""):
            return {"hit": False, "line": ""}
        names = {k: f"{kind_prefix(k)}{race_id}.csv" for k in kinds if kind_prefix(k)}
        hits = [f for f in frames if str(f.get("source")) == "endura" and str(f.get("race_id")) == str(race_id)]
        what = "this event"
    else:
        return {"hit": False, "line": ""}
    if not hits:
        return {"hit": False, "line": f"{what} is not in the cache - it will be downloaded"}
    missing = [k for k, n in names.items() if ("", n) not in have]
    if missing:
        return {"hit": False, "line": f"{what} is in the cache without {', '.join(missing)} - it will be downloaded"}
    hit = hits[-1]
    rows = (hit.get("shape") or [None])[0]
    return {"hit": True, "df_id": str(hit.get("df_id") or ""), "files": [have[("", n)] for n in names.values()], "rows": rows, "date_range": hit.get("date_range"),
            "line": f"{what} is in the cache" + (f" ({int(rows):,} rows" + (", with " + ", ".join(names) if names else "") + ")" if rows is not None else "") + " - no download"}


def loader_file_literals(text: str) -> List[str]:
    """The string literals in a fragment that name a loader's file (datasets/<user>/<kind>_..., whole or in part): the
    names are the loader's, bound at each run, so an edit must leave them exactly as they are."""
    out = []
    for m in _STRING_RE.finditer(text or ""):
        body = m.group("body")
        if body.lstrip("./").startswith("datasets/") and not aux_kind(body).startswith("file:"):
            out.append(body)
    return sorted(out)


def mirror_path(run_dir: str, path: str) -> str:
    """Where a run keeps its copy of a file the method names (2026-10-15): the recorded path under the run's folder, so
    the recorded script runs against a mirror of the layout it was written for - a folder literal, a full path and a
    path built as folder + name all resolve there. A trailing slash (a folder literal) is kept."""
    body = str(path or "").replace("\\", "/")
    while body.startswith("./"):
        body = body[2:]
    return (run_dir or "").rstrip("/") + "/" + body.lstrip("/")


def datasets_dir_of(paths: Iterable[str]) -> str:
    """The datasets folder the recorded paths live in (datasets/<user>), from the first path that has one."""
    for p in paths or []:
        m = re.match(r"^(datasets/[^/]+)/", str(p).replace("\\", "/"))
        if m:
            return m.group(1)
    return ""


def bind_aux(recorded: Iterable[str], now: Iterable[str]) -> dict:
    """Each recorded auxiliary file against this load's: `map` recorded path -> this load's path (by kind; an attached
    file by its name), `absent` the recorded files this load lacks, `extra` this load's files the record did not have."""
    rec = [str(p) for p in (recorded or []) if p]
    cur = [str(p) for p in (now or []) if p]
    by_kind: Dict[str, str] = {}
    for p in cur:
        by_kind.setdefault(aux_kind(p), p)
    out: Dict[str, str] = {}
    absent: List[str] = []
    for p in rec:
        k = aux_kind(p)
        if k in by_kind:
            out[p] = by_kind[k]
        else:
            absent.append(p)
    used = set(out.values())
    return {"map": out, "absent": absent, "extra": [p for p in cur if p not in used]}


def bind_script(script: str, bindings: Dict[str, str], run_dir: str, datasets_dir: str = "", placeholders: Optional[Dict[str, str]] = None) -> Tuple[str, List[Tuple[str, str, str]]]:
    """The executed text of a run: every string literal under the datasets folder is moved under the run's folder, where
    the run keeps a mirror of the recorded layout (2026-10-15) - a recorded auxiliary path, a folder literal, a path the
    method builds as folder + name, a file of the person's own, a write target all resolve there; a loader's file named
    with other dates than the recorded ones (an f-string on an input, another window) is this load's file of that kind,
    under the recorded name. A bare file name is left as it is: it meets a mirrored folder. `bindings` and `placeholders`
    map recorded paths to their mirror paths (the host makes them; a recorded file this load lacks is an empty table
    there). Returns the text and the substitutions made, for the run's record: (literal, mirror path, bound |
    placeholder | cache)."""
    table: Dict[str, Tuple[str, str]] = {}
    by_kind: Dict[str, Tuple[str, str]] = {}
    for old, new in (bindings or {}).items():
        table[old] = (new, "bound")
        by_kind.setdefault(aux_kind(old), (new, "bound"))
    for old, new in (placeholders or {}).items():
        table.setdefault(old, (new, "placeholder"))
        by_kind.setdefault(aux_kind(old), (new, "placeholder"))
    ddir = (datasets_dir or "").rstrip("/")
    seen = set()

    def repl(m):
        body = m.group("body")
        q = m.group("q")
        new, kind = None, ""
        under = (ddir and (body == ddir or body.startswith(ddir + "/"))) or body.startswith(("datasets/", "./datasets/"))
        if body in table:
            new, kind = table[body]
        elif under:
            name_kind = aux_kind(body)
            if not name_kind.startswith("file:") and name_kind in by_kind and os.path.basename(body):
                new, kind = by_kind[name_kind]                 # the loader's file of that kind, whatever the rest of the name says
            elif run_dir:
                new, kind = mirror_path(run_dir, body), "cache"
        if new is None or new == body:
            return m.group(0)
        if (body, new) not in seen:
            seen.add((body, new))
            subs.append((body, new, kind))
        return q + new + q
    subs: List[Tuple[str, str, str]] = []
    return _STRING_RE.sub(repl, script or ""), subs


def date_column(columns: Iterable[dict]) -> str:
    """The first recorded column of the frame that holds dates: the one a window that follows the data is read off."""
    for c in columns or []:
        if dtype_family(str(c.get("dtype") or "")) == "datetime" and c.get("name") is not None:
            return str(c["name"])
    return ""


def dtype_family(dtype: str) -> str:
    d = str(dtype or "").lower()
    if not d:
        return ""
    if d.startswith(("int", "uint", "float", "number")):
        return "number"
    if d.startswith("datetime"):
        return "datetime"
    if d.startswith("bool"):
        return "bool"
    return "text"


# how a cached load is cut to the window a run asks for (2026-10-11): the frame by its date column; each auxiliary file
# by the column the loader keyed it on, or by the rides kept when it has none; a file with neither is taken whole and said.
# The context file by its day and the codes file by the passages the cut context keeps (2026-10-16: taken whole, a code
# count over CTX.codes() would have been the cached load's); a code goes with its passage, whatever its `day` (0206)
CUT_RULES = {"summary": ("date", "start_date_local"), "wellness": ("date", "date"), "intervals": ("ids", "activity_id"), "plan": ("date", "date"),
             "context": ("date", "date"), "codes": ("passages", "id"),
             "rider": ("whole", ""), "zones": ("date", "start_date_local")}    # the profile is the load's settings, taken as it is; the zone times are per activity (2026-10-16)
DATA_MARK_OUT = "ROUTINE_DATA:"             # printed by a run's prelude after a cut: the rows the method saw


def cut_rule(path: str) -> Tuple[str, str]:
    """(by, column) for cutting an auxiliary file to a window: a loader's file by its known column; any other by what
    the script finds in it ('auto': a column of dates by name, else the frame's ids, else whole)."""
    return CUT_RULES.get(aux_kind(path), ("auto", ""))


CUT_SNIPPET = """def _routine_cut_frame(frame, col, start, end):
    import pandas as _pd
    if frame is None or not col or col not in frame.columns:
        return frame
    _t = _pd.to_datetime(frame[col], errors='coerce')
    return frame[(_t >= _pd.Timestamp(start)) & (_t < _pd.Timestamp(end) + _pd.Timedelta(days=1))].copy()
def _routine_cut_table(table, by, col, start, end, ids, passages=None):
    import pandas as _pd
    if by == 'passages':
        return (table[table[col].astype(str).isin(passages)].copy(), 'passages') if col in table.columns and passages is not None else (table, 'whole')
    if by == 'auto':
        _named = [c for c in table.columns if any(k in str(c).lower() for k in ('date', 'start', 'time'))]
        for c in _named + [c for c in table.columns if c not in _named]:
            if table[c].dtype != object and not str(table[c].dtype).startswith('datetime'):
                continue
            _t = _pd.to_datetime(table[c], errors='coerce')
            if len(table) and _t.notna().mean() >= 0.9:
                by, col = 'date', c
                break
        else:
            by, col = ('ids', 'activity_id') if 'activity_id' in table.columns else ('whole', '')
    if by == 'date' and col in table.columns:
        return _routine_cut_frame(table, col, start, end), 'date'
    if by == 'ids' and col in table.columns and ids is not None:
        return table[table[col].astype(str).isin(ids)].copy(), 'ids'
    return table, 'whole'
"""

CONFORM_PRELUDE = """# --- the data as the method saw it: a column this load lacks is added empty, a column whose type changed is read back
def _routine_family(d):
    d = str(d or '').lower()
    return 'number' if d.startswith(('int', 'uint', 'float')) else ('datetime' if d.startswith('datetime') else ('bool' if d.startswith('bool') else ('text' if d else '')))
def _routine_conform(frame, columns):
    import pandas as _pd, numpy as _np
    if frame is None or not hasattr(frame, 'columns'):
        return frame
    for _name, _dtype in columns:
        _fam = _routine_family(_dtype)
        if _name not in frame.columns:
            frame[_name] = _pd.Series([_pd.NaT if _fam == 'datetime' else _np.nan] * len(frame), index=frame.index, dtype=('datetime64[ns]' if _fam == 'datetime' else ('float64' if _fam == 'number' else 'object')))
            continue
        _have = _routine_family(frame[_name].dtype)
        if _fam and _have != _fam:
            try:
                if _fam == 'number': frame[_name] = _pd.to_numeric(frame[_name], errors='coerce')
                elif _fam == 'datetime': frame[_name] = _pd.to_datetime(frame[_name], errors='coerce')
                elif _fam == 'text': frame[_name] = frame[_name].where(frame[_name].isna(), frame[_name].astype(str))
            except Exception:
                pass
    return frame
# a cached load cut to the window this run asked for: the frame first, then the files it names - each written under the
# loader's name for the window, with the recorded columns it lacks added - so the method sees what a fresh load would give it
""" + CUT_SNIPPET + """if _ROUTINE_CUT and 'df' in globals() and df is not None:
    import os as _os, json as _j, numpy as _np, pandas as _pd
    df = _routine_cut_frame(df, _ROUTINE_CUT['column'], _ROUTINE_CUT['start'], _ROUTINE_CUT['end'])
    _ids = set(df['activity_id'].astype(str)) if 'activity_id' in df.columns else set()
    _passages = set()                                     # the ids of the context table's rows kept, for the codes file
    _later = []
    for _new, _spec in _ROUTINE_CUT['files'].items():
        if _spec.get('by') in ('ids', 'passages'):
            _later.append((_new, _spec)); continue
        _later.insert(0, (_new, _spec))
    for _new, _spec in _later:
        _d = _os.path.dirname(_new)
        if _d:
            _os.makedirs(_d, exist_ok=True)
        try:
            _t = _pd.read_csv(_spec['source'])
        except Exception:
            _t = _pd.DataFrame(columns=list(_spec.get('columns') or []))
            print('ROUTINE: ' + _os.path.basename(_spec['source']) + ' could not be read from the cached load; an empty table stood in for it')
        _t, _how = _routine_cut_table(_t, _spec.get('by') or 'auto', _spec.get('column') or '', _ROUTINE_CUT['start'], _ROUTINE_CUT['end'], _ids or None, _passages)
        if _how == 'date' and 'activity_id' in _t.columns:
            _ids |= set(_t['activity_id'].astype(str))
        if _how == 'date' and 'id' in _t.columns and 'kind' in _t.columns:
            _passages |= set(_t['id'].astype(str))
        for _c in _spec.get('columns') or []:
            if _c not in _t.columns:
                _t[_c] = _np.nan
        _t.to_csv(_new, index=False)
        if _how == 'whole':
            print('ROUTINE: ' + _os.path.basename(_new) + ' was taken whole from the cached load - ' + ('a settings file, not rows of the window' if _spec.get('by') == 'whole' else 'nothing in it to cut by the window'))
    print('ROUTINE_DATA: ' + _j.dumps({'rows': int(len(df)), 'window': [_ROUTINE_CUT['start'], _ROUTINE_CUT['end']]}))
if 'df' in globals() and df is not None:
    df = _routine_conform(df, _ROUTINE_COLUMNS)
    if '_BambooSource' in globals():
        DS = _BambooSource(df)
# every file the method may name is in the run's mirror before the cells run (2026-10-15): a recorded file the probe did
# not copy is copied from this load's file now, a stand-in that was not written gets written (an empty table with the
# recorded columns), a bound file that is nowhere is said and stood in for, a cache file the method reads is copied
def _routine_materialise(files):
    import os as _os, pandas as _pd
    for _new, _old, _cols, _kind in files:
        if not _new or _new.endswith('/') or _os.path.exists(_new):
            if _new and _new.endswith('/'):
                _os.makedirs(_new, exist_ok=True)
            continue
        _d = _os.path.dirname(_new)
        if _d:
            _os.makedirs(_d, exist_ok=True)
        if _kind in ('cache', 'bound', 'cut') and _old and _os.path.isfile(_old):
            with open(_old, 'rb') as _s, open(_new, 'wb') as _t:
                _t.write(_s.read())
            continue
        if _kind == 'cache':
            continue                                          # a write target, or a folder: nothing to copy
        _pd.DataFrame(columns=list(_cols or [])).to_csv(_new, index=False)
        if _kind in ('bound', 'cut'):
            print('ROUTINE: ' + _os.path.basename(_old or _new) + ' was not where this load left it; an empty table stood in for it')
_routine_materialise(_ROUTINE_FILES)
# an input that is the data's own period is written from the frame, first and last dates of its date column
def _routine_span(frame, items):
    import pandas as _pd
    _out = {}
    for _key, _col in items:
        try:
            if frame is not None and _col in frame.columns:
                _s = _pd.to_datetime(frame[_col], errors='coerce').dropna()
                if len(_s):
                    _out[_key] = [str(_s.min().date()), str(_s.max().date())]
        except Exception:
            pass
    return _out
if _ROUTINE_SPAN and 'df' in globals() and df is not None:
    _written = _routine_span(df, _ROUTINE_SPAN)
    if _written:
        import json as _j
        INPUTS.update(_written)
        print('ROUTINE_INPUTS: ' + _j.dumps(_written))
"""


def conform_prelude(columns: Iterable[dict], files: Optional[Iterable[Tuple[str, str, List[str], str]]] = None,
                    span: Optional[Iterable[Tuple[str, str]]] = None, cut: Optional[dict] = None,
                    context: Optional[Tuple[str, str]] = None) -> str:
    """The block a run executes after its inputs: the recorded columns of `df`, the files the executed text names
    (each as [this run's path, the recorded path, the recorded columns, bound | placeholder | cache | cut]), the inputs
    that follow the frame's own dates (each as [key, date column]) and, for a run on a cached load, the cut to its
    window ({start, end, column, files: {this run's path: {source, columns, by, column}}}); then the cut, the conform
    of the frame, the files made sure of, and those inputs written from the frame and printed after ROUTINE_INPUTS:
    for the record. With `context` (the run's own context and codes files, 2026-10-16) CTX is defined over them last
    of all - the host's prelude points it at the files loaded now, which on a cached load are the whole load's, not
    the window's (Palo's routine, cut to four months, read seventeen months of words against four months of rides)."""
    cols = [[str(c.get("name")), str(c.get("dtype") or "")] for c in (columns or []) if c.get("name") is not None]
    fl = [[str(n), str(o or ""), [str(c) for c in (cs or [])], str(k or "")] for n, o, cs, k in (files or [])]
    sp = [[str(k), str(c)] for k, c in (span or []) if k and c]
    ct = None
    if cut and cut.get("start") and cut.get("end"):
        ct = {"start": str(cut["start"]), "end": str(cut["end"]), "column": str(cut.get("column") or ""),
              "files": {str(n): {"source": str(v.get("source") or ""), "columns": [str(c) for c in (v.get("columns") or [])], "by": str(v.get("by") or "auto"), "column": str(v.get("column") or "")}
                        for n, v in (cut.get("files") or {}).items()}}
    ctx = ""
    if context and context[0]:
        from analyst.context import kernel_api_source
        ctx = "\n# the words the method reads: CTX over this run's own context and codes files\n" + kernel_api_source(str(context[0]), str(context[1] or ""))
    return ("_ROUTINE_COLUMNS = " + json.dumps(cols) + "\n_ROUTINE_FILES = " + json.dumps(fl) + "\n_ROUTINE_SPAN = " + json.dumps(sp)
            + "\n_ROUTINE_CUT = " + ("None" if ct is None else json.dumps(ct)) + "\n" + CONFORM_PRELUDE + ctx)


def remove_script(folder: str) -> str:
    """A script that removes a folder a run made, with what is in it."""
    return ("import pathlib as _pl\n"
            "_root = _pl.Path(" + json.dumps(str(folder)) + ")\n"
            "for _p in sorted(_root.rglob('*'), reverse=True) if _root.is_dir() else []:\n"
            "    _p.rmdir() if _p.is_dir() and not _p.is_symlink() else _p.unlink()\n"
            "if _root.is_dir():\n"
            "    _root.rmdir()\n")


SHAPE_MARK = "SHAPE:"


def shape_script(bindings: Dict[str, str], aux_columns: Dict[str, List[str]], run_dir: str, absent: Iterable[str] = (), cut: Optional[dict] = None) -> str:
    """A script, run before the method, that makes this load's auxiliary files fit the recorded ones and lays them out as
    the method expects (2026-10-15): for each binding a copy under the recorded path in the run's folder - the bytes as
    they are, or with the recorded columns it lacks added empty; for a recorded file this load lacks an empty table with
    its columns, at its recorded path; and prints what it found - rows, the columns added, the source - as JSON after
    SHAPE:. On a cached load around the window (`cut`: {start, end, column}, 2026-10-16) each copy is cut to the window
    as the run's prelude cuts it, so the rows reported - and the frame's, as `frame_rows` - are the ones the method
    sees (the CHECK row had said the cached load's: 517 wellness rows for a four-month window)."""
    ct = {"start": str(cut["start"]), "end": str(cut["end"]), "column": str(cut.get("column") or "")} if cut and cut.get("start") and cut.get("end") else None
    spec = {"bindings": dict(bindings or {}), "columns": {k: list(v) for k, v in (aux_columns or {}).items()},
            "run_dir": run_dir, "absent": list(absent or []), "cut": ct,
            "rules": {old: list(cut_rule(str(new))) for old, new in (bindings or {}).items()},
            "mirror": {old: mirror_path(run_dir, old) for old in list((bindings or {}).keys()) + list(absent or [])}}
    return ("import json as _j, os as _os\n"
            "import pandas as _pd\n"
            "_spec = _j.loads(" + repr(json.dumps(spec)) + ")\n"
            "_os.makedirs(_spec['run_dir'], exist_ok=True)\n"
            "_out = {'files': {}, 'placeholders': {}}\n"
            + CUT_SNIPPET +
            "_cut = _spec['cut']\n"
            "_ids, _passages = set(), set()\n"
            "if _cut and 'df' in globals() and df is not None:\n"
            "    _dfc = _routine_cut_frame(df, _cut['column'], _cut['start'], _cut['end'])\n"
            "    _out['frame_rows'] = int(len(_dfc))\n"
            "    _ids = set(_dfc['activity_id'].astype(str)) if 'activity_id' in _dfc.columns else set()\n"
            "_order = sorted(_spec['bindings'].items(), key=lambda kv: _spec['rules'].get(kv[0], ['auto'])[0] in ('ids', 'passages'))\n"
            "for _old, _new in _order:\n"
            "    _rec = _spec['columns'].get(_old) or []\n"
            "    try:\n"
            "        _fr = _pd.read_csv(_new) if _new.lower().endswith('.csv') else _pd.read_parquet(_new)\n"
            "    except Exception as _exc:\n"
            "        _out['files'][_old] = {'path': _new, 'error': str(_exc)[:200]}\n"
            "        continue\n"
            "    _how = ''\n"
            "    if _cut:\n"
            "        _by, _c = _spec['rules'].get(_old, ['auto', ''])\n"
            "        _fr, _how = _routine_cut_table(_fr, _by, _c, _cut['start'], _cut['end'], _ids or None, _passages)\n"
            "        if _how == 'date' and 'activity_id' in _fr.columns: _ids |= set(_fr['activity_id'].astype(str))\n"
            "        if _how == 'date' and 'id' in _fr.columns and 'kind' in _fr.columns: _passages |= set(_fr['id'].astype(str))\n"
            "    _missing = [c for c in _rec if c not in _fr.columns]\n"
            "    _empty = [c for c in _fr.columns if _fr[c].isna().all()]\n"
            "    _target = _spec['mirror'][_old]\n"
            "    _os.makedirs(_os.path.dirname(_target) or '.', exist_ok=True)\n"
            "    if _missing or _cut:\n"
            "        for c in _missing: _fr[c] = _pd.NA\n"
            "        _fr.to_csv(_target, index=False)\n"
            "    else:\n"
            "        with open(_new, 'rb') as _s, open(_target, 'wb') as _t: _t.write(_s.read())\n"
            "    _out['files'][_old] = {'path': _target, 'source': _new, 'rows': int(len(_fr)), 'missing': _missing, 'empty': _empty, 'columns': [str(c) for c in _fr.columns]}\n"
            "for _old in _spec['absent']:\n"
            "    _rec = _spec['columns'].get(_old) or []\n"
            "    _target = _spec['mirror'][_old]\n"
            "    _os.makedirs(_os.path.dirname(_target) or '.', exist_ok=True)\n"
            "    _pd.DataFrame(columns=_rec).to_csv(_target, index=False)\n"
            "    _out['placeholders'][_old] = _target\n"
            "print(" + repr(SHAPE_MARK + " ") + " + _j.dumps(_out))\n")


def read_shape(stdout: str) -> Optional[dict]:
    for ln in reversed((stdout or "").splitlines()):
        if ln.strip().startswith(SHAPE_MARK):
            try:
                return json.loads(ln.strip()[len(SHAPE_MARK):].strip())
            except ValueError:
                return None
    return None


def _kind_word(path: str) -> str:
    k = aux_kind(path)
    return k[5:] if k.startswith("file:") else k + " file"


def shape_sentences(record: dict, data: dict, shape: Optional[dict], binding: dict) -> List[str]:
    """What differs between this run's data and the original's, in sentences the coach can read (2026-10-11, step 4):
    the frame's rows against the original's; each bound auxiliary file's rows against the original's, the columns
    added empty and the columns the file has but left empty; a file written with no rows; a file that could not be
    read. From the promotion's record (`rows`, `aux_shape`) and the run's shape probe (`shape.files`); nothing said
    where nothing is known. A file this load lacks is said by `aux_line` beside these."""
    out: List[str] = []
    rec, d = record or {}, data or {}
    r_now, r_rec = d.get("rows"), rec.get("rows")
    if isinstance(r_now, (int, float)) and isinstance(r_rec, (int, float)):
        out.append(f"the same {int(r_now):,} rows as the original" if int(r_now) == int(r_rec) else f"{int(r_now):,} rows where the original had {int(r_rec):,}")
    elif isinstance(r_now, (int, float)):
        out.append(f"{int(r_now):,} rows")
    files = (shape or {}).get("files") or {}
    aux_rec = rec.get("aux_shape") or {}
    for old in (binding or {}).get("map") or {}:
        info = files.get(old)
        if not isinstance(info, dict):
            continue
        word = _kind_word(old)
        if info.get("error"):
            out.append(f"the {word} could not be read ({str(info['error'])[:120]})")
            continue
        rows = info.get("rows")
        if rows == 0:
            # a window without words (docs/CONTEXT_DESIGN.md F3, 2026-10-14): the context file is its header, the pass wrote no
            # codes, the method sees two empty tables and prints its zeros
            out.append("no passages in this window (the context and codes tables are empty)" if aux_kind(old) == "context" else f"the {word} is empty in this data (0 rows)")
            continue
        orig = (aux_rec.get(old) or {}).get("rows") if isinstance(aux_rec.get(old), dict) else None
        s_ = f"the {word}: {int(rows):,} row{'s' if int(rows) != 1 else ''}" if isinstance(rows, (int, float)) else f"the {word}"
        if isinstance(rows, (int, float)) and isinstance(orig, (int, float)):
            s_ += " as the original" if int(rows) == int(orig) else f" where the original had {int(orig):,}"
        missing = [str(c) for c in (info.get("missing") or [])]
        empty = [str(c) for c in (info.get("empty") or []) if str(c) not in missing]
        if missing:
            s_ += f", {len(missing)} column{'s' if len(missing) != 1 else ''} added empty ({', '.join(missing[:6])}{', ...' if len(missing) > 6 else ''})"
        if empty:
            s_ += f", {len(empty)} column{'s' if len(empty) != 1 else ''} empty ({', '.join(empty[:6])}{', ...' if len(empty) > 6 else ''})"
        out.append(s_)
    return out


def cached_files(inspect: dict) -> List[dict]:
    """The frames in the executor's cache that came from a file, for a file routine's run dialog (step 4, 2026-10-11):
    [{df_id, name, rows, cached_at}], newest first. A loader's frame (Intervals.icu, Endura, SweatStack) is not a
    file; a frame with no file name is listed by its id."""
    out = []
    for f in (inspect or {}).get("cached_dataframes") or []:
        if not isinstance(f, dict) or not f.get("df_id"):
            continue
        src = str(f.get("source") or "").lower()
        if src in ("intervals", "endura", "sweatstack"):
            continue
        name = str(f.get("original_filename") or "").strip() or f"frame {str(f['df_id'])[:8]}"
        shape = f.get("shape") or []
        out.append({"df_id": str(f["df_id"]), "name": name, "rows": int(shape[0]) if shape and isinstance(shape[0], (int, float)) else None,
                    "cached_at": str(f.get("cached_at") or "")})
    return sorted(out, key=lambda x: x["cached_at"], reverse=True)


PRECHECK_MARK = "PRECHECK:"


def precheck_script(checks: Dict[str, List[str]], files: Optional[Iterable[str]] = None, cut: Optional[dict] = None) -> str:
    """A script that reports, for each column named by a choice input, which of its chosen values the data holds: the
    frame first, then the auxiliary files loaded now (2026-10-11: a choice column that lives in the summary file,
    not in the frame, was reported as not in the data). `where` says which table answered. For a run on a cached
    load, the frame and the files are cut to the window first (`cut`: {start, end, column}), as the run will cut them."""
    spec = json.dumps({str(k): [str(x) for x in v] for k, v in (checks or {}).items()})
    paths = json.dumps([str(p) for p in (files or []) if p])
    ct = {"start": str(cut["start"]), "end": str(cut["end"]), "column": str(cut.get("column") or "")} if cut and cut.get("start") and cut.get("end") else None
    rules = json.dumps({str(p): list(cut_rule(str(p))) for p in (files or []) if p})
    return ("import json as _j, os as _os\n"
            "import pandas as _pd\n"
            "_spec = _j.loads(" + repr(spec) + ")\n"
            "_files = " + paths + "\n"
            "_cut = " + ("None" if ct is None else json.dumps(ct)) + "\n"
            "_rules = " + rules + "\n"
            + CUT_SNIPPET +
            "_frame = df\n"
            "_ids = None\n"
            "if _cut:\n"
            "    _frame = _routine_cut_frame(df, _cut['column'], _cut['start'], _cut['end'])\n"
            "    _ids = set(_frame['activity_id'].astype(str)) if 'activity_id' in _frame.columns else set()\n"
            "_out = {'rows': int(len(_frame)), 'columns': [str(c) for c in _frame.columns], 'values': {}, 'where': {}}\n"
            "def _column_of(_p, _col):\n"
            "    try:\n"
            "        _head = _pd.read_csv(_p, nrows=0) if _p.lower().endswith('.csv') else _pd.read_parquet(_p)\n"
            "        if _col not in _head.columns:\n"
            "            return None\n"
            "        if _cut:\n"
            "            _t = _pd.read_csv(_p) if _p.lower().endswith('.csv') else _head\n"
            "            _by, _c = _rules.get(_p, ['auto', ''])\n"
            "            _t, _how = _routine_cut_table(_t, _by, _c, _cut['start'], _cut['end'], _ids or None)\n"
            "            return _t[_col]\n"
            "        return (_pd.read_csv(_p, usecols=[_col]) if _p.lower().endswith('.csv') else _head)[_col]\n"
            "    except Exception:\n"
            "        return None\n"
            "for _col, _vals in _spec.items():\n"
            "    _series, _where = None, None\n"
            "    if _col in _frame.columns:\n"
            "        _series, _where = _frame[_col], 'the frame'\n"
            "    else:\n"
            "        for _p in _files:\n"
            "            _series = _column_of(_p, _col)\n"
            "            if _series is not None:\n"
            "                _where = _os.path.basename(_p)\n"
            "                break\n"
            "    if _series is None:\n"
            "        _out['values'][_col] = None\n"
            "        continue\n"
            "    _have = set(_series.dropna().astype(str).unique().tolist())\n"
            "    _out['values'][_col] = {v: (v in _have) for v in _vals}\n"
            "    _out['where'][_col] = _where\n"
            "print(" + repr(PRECHECK_MARK + " ") + " + _j.dumps(_out))\n")


def read_precheck(stdout: str) -> Optional[dict]:
    for ln in reversed((stdout or "").splitlines()):
        if ln.strip().startswith(PRECHECK_MARK):
            try:
                return json.loads(ln.strip()[len(PRECHECK_MARK):].strip())
            except ValueError:
                return None
    return None


def known_columns(record: Optional[dict]) -> Optional[set]:
    """The columns the data had at promotion - the frame's and every recorded file's - or None when the record cannot
    say (no columns recorded, or a recorded file whose columns were never probed)."""
    d = record or {}
    cols = {str(c.get("name")) for c in (d.get("columns") or []) if isinstance(c, dict) and c.get("name")}
    if not cols:
        return None
    shapes = d.get("aux_shape") or {}
    for path in d.get("aux") or []:
        shape = shapes.get(str(path))
        if not isinstance(shape, dict) or "columns" not in shape:
            return None
        cols |= {str(c.get("name")) for c in (shape.get("columns") or []) if isinstance(c, dict) and c.get("name")}
    return cols


def own_columns(parameters: List[dict], record: Optional[dict]) -> Tuple[List[dict], List[str]]:
    """A choice over a column the data never had is a choice over the method's own words - a column the script
    computes (2026-10-15: a routine's keyword list was declared over `head`, a column the script derives from the plan
    notes, and every run was refused with 'column head is not in this data'). Its column is dropped: the values go to
    the method as given and are not looked for in the data; a note says so. A record that cannot say what columns the
    data had leaves the inputs as they are."""
    known = known_columns(record)
    if known is None:
        return list(parameters or []), []
    out, notes = [], []
    for p in parameters or []:
        q = dict(p)
        col = str(q.get("column") or "")
        if q.get("type") == "choice" and col and col not in known:
            q.pop("column", None)
            notes.append(f"{q.get('label') or q.get('key')}: the values go to the method as given - {col} is a column the script computes, not one of the data's, so they are not looked for in the data")
        out.append(q)
    return out, notes


def value_checks(parameters: List[dict], values: Dict[str, object]) -> Dict[str, List[str]]:
    """column -> the chosen values to look for: the choice inputs that name a column."""
    out: Dict[str, List[str]] = {}
    for p in parameters or []:
        if p.get("type") == "choice" and p.get("column"):
            v = values.get(p["key"], p.get("default"))
            vals = v if isinstance(v, (list, tuple)) else [v]
            out.setdefault(str(p["column"]), []).extend(str(x) for x in vals if x is not None and str(x) != "")
    return out


def value_verdict(parameters: List[dict], values: Dict[str, object], found: Optional[dict]) -> Tuple[List[str], List[str]]:
    """What the precheck found for each choice input, as (refusals, notes): a column in neither the frame nor the files
    loaded, or a single value absent, or every chosen value absent, refuses - nothing to run on for that input; one of
    several chosen values absent is a note (2026-10-11: the method keeps what is there), said before the run."""
    refusals, notes = [], []
    vals = (found or {}).get("values") or {}
    where = (found or {}).get("where") or {}
    for p in parameters or []:
        if p.get("type") != "choice" or not p.get("column"):
            continue
        col = str(p["column"])
        v = values.get(p["key"], p.get("default"))
        wanted = [str(x) for x in (v if isinstance(v, (list, tuple)) else [v]) if x is not None and str(x) != ""]
        if not wanted:
            continue
        have = vals.get(col)
        if have is None:
            refusals.extend(f"column {col} is not in this data (for '{x}')" for x in wanted)
            continue
        table = str(where.get(col) or "")
        kind = aux_kind(table) if table and table != "the frame" else ""
        of = "" if not table or table == "the frame" else (f" of the {kind} file" if kind and not kind.startswith("file:") else f" of {table}")
        absent = [x for x in wanted if not have.get(x)]
        if not absent:
            continue
        if len(absent) < len(wanted):
            notes.append(("'" + "', '".join(absent) + "'") + (" is" if len(absent) == 1 else " are") + f" not in column {col}{of} - the method keeps the other" + (" value" if len(wanted) - len(absent) == 1 else " values"))
        else:
            refusals.extend(f"'{x}' is not in column {col}{of}" for x in absent)
    return refusals, notes


def coerce_values(parameters: List[dict], values: Optional[Dict[str, object]]) -> Tuple[Dict[str, object], List[str]]:
    """The values a run uses, each in its input's form; an input not given keeps its default; an unreadable value is
    a problem named for the person."""
    out, problems = {}, []
    given = values or {}
    for p in parameters or []:
        key = p["key"]
        raw = given.get(key, p.get("default"))
        v = _coerce_default(p["type"], raw, bool(p.get("multiple")))
        if v is None:
            problems.append(f"{p.get('label', key)}: {raw!r} could not be read as a {p['type']}")
            v = p.get("default")
        out[key] = v
    return out, problems


# ----------------------------------------------------------------------------- a run: its status and the comparison
_EXC_LINE_RE = re.compile(r"^[A-Za-z_][\w.]*(?:Error|Exception|Warning|Interrupt|Exit)\b")


def error_line(err: str) -> str:
    """The one line that names what went wrong: the exception line, else the last line that is not the kernel's
    rollback notice (the local edition's kernel appends one after the traceback)."""
    lines = [ln.strip() for ln in (err or "").strip().splitlines() if ln.strip()]
    for ln in reversed(lines):
        if _EXC_LINE_RE.match(ln):
            return ln
    for ln in reversed(lines):
        if not ln.startswith("[delv-e:") and ln not in ("[...truncated]", "^^^^^^"):
            return ln
    return ""


def same_numbers(a: dict, b: dict) -> bool:
    """Whether two lines carry the same estimate and interval: equal as printed, or equal as numbers (+1,234 is +1234)."""
    def same(k):
        x, y = number(a.get(k)), number(b.get(k))
        return a.get(k) == b.get(k) or (x is not None and y is not None and x == y)
    return all(same(k) for k in ("estimate", "low", "high"))


def run_status(expected: List[dict], results: List[dict], run: dict, error: str, reference: Optional[List[dict]]) -> Tuple[str, str]:
    """A run's status and the line that says it. `results` are the run's lines laid against the expected ones
    (place_lines), `run` what read_run read, `error` what the runner gave back when the script could not be carried
    through. failed: the run could not be carried out (the error is not a statement's - those cost their own lines);
    timed_out; empty: the frame had no rows and nothing was run; reproduced: every tracked number as the reference
    run's; ran: the statements ran - the line says how many tracked lines came back with a number, and why the first
    missing one did not."""
    if error:
        text = str(error).strip()
        last = (error_line(text) or "unknown error")[:200]
        if "TIMEOUT" in text.upper() or "timed out" in text.lower():
            return "timed_out", "timed out: " + last
        return "failed", "failed: " + last
    if run.get("empty"):
        return "empty", NO_DATA
    tracked = [(i, e) for i, e in enumerate(expected or []) if not e.get("dropped") and e.get("estimate") is not None]
    stopped = run.get("stopped") or []
    if not tracked:
        return "ran", ("ran without error" if not stopped else f"ran; {len(stopped)} statement{'s' if len(stopped) != 1 else ''} stopped (cell {stopped[0]['cell']}: {stopped[0]['error']})")
    got = [(i, results[i] if i < len(results) else _blank(NO_LINE)) for i, _e in tracked]
    blank = [r for _i, r in got if r.get("estimate") is None]
    n = len(tracked)
    if blank:
        return "ran", f"ran: {n - len(blank)} of {n} result line{'s' if n != 1 else ''}; {len(blank)} not computed ({str(blank[0].get('why') or '')[:160]})"
    if reference is not None and all(i < len(reference) and same_numbers(r, reference[i]) for i, r in got):
        return "reproduced", f"reproduced: every result line as the run before ({n} line{'s' if n != 1 else ''})"
    return "ran", f"ran: {n} result line{'s' if n != 1 else ''}"


def check_zero(expected: List[dict], run: dict, error: str = "") -> Tuple[str, str]:
    """Run zero's verdict, (status, line): reproduced when the method ran whole on the chain's own data and printed
    the chain's lines, in order, with the same numbers; differed when another count came back, or a line differs -
    the line names the first four; failed when the script, or a statement of it, stopped."""
    stopped = run.get("stopped") or []
    if not error and stopped:
        error = f"cell {stopped[0]['cell']} stopped on the chain's own data: {stopped[0]['error']}"
    if error:
        return "failed", f"the script stopped with an error ({(error_line(error) or 'unknown error')[:200]})"
    exp = [e for e in expected if e.get("estimate") is not None]
    got = [ln for _s, _k, ln in run.get("lines") or []]
    if not exp:
        return "reproduced", "ran without error" + (f"; {len(got)} result line(s) printed" if got else " (no result lines to compare)")
    if len(got) != len(exp):
        return "differed", f"{len(got)} result line(s) came back, {len(exp)} expected"
    off = [(e, g) for e, g in zip(exp, got) if not same_numbers(e, g)]
    if off:
        shown = "; ".join(f"[cell {e.get('cell')}] {str(e.get('label') or '')[:50]}: {e.get('estimate')} -> {g.get('estimate')}" for e, g in off[:4])
        return "differed", f"{len(off)} of {len(exp)} result lines differ ({shown}{'; ...' if len(off) > 4 else ''})"
    return "reproduced", f"reproduced: {len(exp)} result line(s) identical"


def _ivl(r: Optional[dict]) -> Optional[Tuple[float, float]]:
    if not r:
        return None
    lo, hi = number(r.get("low")), number(r.get("high"))
    return (lo, hi) if lo is not None and hi is not None else None


def compare_runs(manifest_results: List[dict], now: List[dict], before: Optional[List[dict]]) -> dict:
    """This run's lines against a reference run's, both laid against the manifest's lines: the change, whether the
    intervals overlap, what is missing on either side. Dropped lines are not compared. Marks: up / down when the
    intervals do not overlap (or, without intervals, when the estimate changed), same when they do, missing when a
    side has no number for the line - the row then says why this run has none (`why`)."""
    rows = []
    moved = within = missing = changed = 0
    for i, m in enumerate(manifest_results or []):
        if m.get("dropped") or m.get("estimate") is None:
            continue
        a = now[i] if i < len(now or []) else None
        b = before[i] if before is not None and i < len(before) else None
        why = str((a or {}).get("why") or "")
        a = a if a and a.get("estimate") is not None else None
        b = b if b and b.get("estimate") is not None else None
        row = {"cell": m.get("cell"), "index": m.get("index"), "label": m.get("label", ""), "name": m.get("name", ""), "unit": m.get("unit", ""), "direction": m.get("direction", ""), "typed": bool(m.get("typed")),
               "now": {"estimate": a.get("estimate"), "low": a.get("low"), "high": a.get("high")} if a else None,
               "before": {"estimate": b.get("estimate"), "low": b.get("low"), "high": b.get("high")} if b else None,
               "change": None, "overlap": None, "mark": "missing", "why": why}
        if a and b:
            ea, eb = number(a.get("estimate")), number(b.get("estimate"))
            ia, ib = _ivl(a), _ivl(b)
            if ea is not None and eb is not None:
                row["change"] = ea - eb
            if ia and ib:
                row["overlap"] = not (ia[0] > ib[1] or ia[1] < ib[0])
                if row["overlap"]:
                    row["mark"] = "same"; within += 1
                else:
                    row["mark"] = "up" if (row["change"] or 0) > 0 else "down"; moved += 1
            elif ea is not None and eb is not None:
                if ea == eb:
                    row["mark"] = "same"; within += 1
                else:
                    row["mark"] = "up" if ea > eb else "down"; changed += 1
            else:
                row["mark"] = "same" if a.get("estimate") == b.get("estimate") else "changed"; within += 1
        else:
            missing += 1
        rows.append(row)
    compared = len(rows) - missing
    if before is None:
        line = "nothing to compare with: the first run of this version"
    elif compared == 0:
        line = "no result line to compare"
    else:
        parts = [f"{moved} of {compared} moved beyond their intervals" if any(r["overlap"] is not None for r in rows) else f"{changed} of {compared} changed"]
        if missing:
            parts.append(f"{missing} missing")
        line = ", ".join(parts)
    return {"rows": rows, "moved": moved, "within": within, "changed": changed, "missing": missing, "compared": compared, "line": line}


def gap_sentences(recorded: Optional[dict], now: Optional[dict], by: str = "") -> List[str]:
    """Where this run's data is emptier than the data the analysis was made on, in sentences: a watched column whose
    share of empty values - by the groups of `by` when the run counted them, else by rows - is at least ten points
    above the recorded one. Both sides are the driver's counts per column: [rows empty, rows, groups empty, groups].
    Nothing when no shares were recorded: there is nothing to hold the run to."""
    def share(c):
        if not c:
            return None, None, None
        if len(c) >= 4 and c[3]:
            return c[2] / c[3], c[2], c[3]
        return (c[0] / c[1], None, None) if len(c) >= 2 and c[1] else (None, None, None)
    out = []
    for col, counts in (now or {}).items() if recorded is not None else []:
        here, k, n = share(counts)
        there = share(recorded.get(col))[0] or 0.0
        if here is None or here < there + 0.10:
            continue
        out.append(f"{col} is empty for {k} of {n} {by} values" if n and by else f"{col} is empty in {round(100 * here)}% of the rows")
    return out


# ----------------------------------------------------------------------------- the store
SHAPE = 2                                   # the shape of a stored routine; one stored in an earlier shape is brought to this one when it is loaded


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", str(s or ""))


def _as_now(run: dict, expected: List[dict]) -> None:
    """One stored run - its summary, or its record - from an earlier shape to today's (RoutineStore._upgrade): its
    lines laid against the expected ones, a blank with its reason where none came back; a run that printed fewer
    lines `ran`; a line the run failed before, missing; the cell it failed at, the statement that stopped. One
    already in today's shape is left as it is (an upgrade cut short is taken up again)."""
    if "gaps" in run:
        return
    if run.get("status") == "differed":
        run["status"] = "ran"
    line, lost = str(run.get("line") or ""), run.get("status") in ("failed", "timed_out")
    laid = place_lines(expected, {"lines": [(None, k, r) for k, r in enumerate(run.get("results") or [])]})["results"]
    run["results"] = [dict(r, why=line) if lost and r.get("estimate") is None else r for r in laid]
    run["gaps"] = []
    cmp = run.get("comparison") or {}
    if "unreached" in cmp:
        cmp["missing"] = int(cmp.get("missing") or 0) + int(cmp.pop("unreached") or 0)
    for row in cmp.get("rows") or []:
        row.update({"mark": "missing" if row.get("mark") == "unreached" else row.get("mark"), "why": "" if row.get("now") else line})
    if "failed_cell" in run:
        cell = run.pop("failed_cell") or {}
        run["stopped"] = [{"cell": cell["number"], "line": None, "code": cell.get("statement") or cell.get("code") or "", "error": error_line(run.get("error") or ""),
                           "skipped": 0}] if cell.get("number") else []
    run.pop("consolidation", None)


class RoutineStore:
    """One folder per routine under <storage>/routines/<id>/: routine.json (the routine, its versions, run zero),
    runs/ (the files of each run: the printed output, the figures). The self-hosted and the hosted editions keep
    favourites this way too."""

    def __init__(self, storage_dir: str):
        self.dir = os.path.join(storage_dir, "routines")

    def path(self, rid: str) -> str:
        return os.path.join(self.dir, _safe(rid))

    def file(self, rid: str) -> str:
        return os.path.join(self.path(rid), "routine.json")

    def load(self, rid: str) -> Optional[dict]:
        f = self.file(rid)
        if not os.path.exists(f):
            return None
        with open(f, encoding="utf-8") as fh:
            routine = json.load(fh)
        if routine.get("shape") != SHAPE:
            self._upgrade(routine)
            self.save(routine)
        return routine

    def _upgrade(self, routine: dict) -> None:
        """A routine stored in an earlier shape, brought to today's, its runs' records with it - the one place that
        knows the earlier shapes. A version keeps one script: a rewrite that was never confirmed gives way to the
        method it replaced, and the records of the passes that shortened or rewrote it go. Every run is as _as_now
        leaves it, and its summary names whose data it ran on (the load's subject, from the run's record)."""
        expected = {}
        for v in routine.get("versions") or []:
            if "script_fallback" in v:
                v["script"] = v.pop("script_fallback")
            for k in ("script_written", "condensed", "consolidated"):
                v.pop(k, None)
            if (v.get("run_zero") or {}).get("status") == "condensing":      # the pass after a verdict of reproduced, cut short
                v["run_zero"]["status"] = "reproduced"
            expected[v.get("number")] = (v.get("manifest") or {}).get("results") or []
        for run in routine.get("runs") or []:
            tag = f"v{run.get('version', 1)}_{run.get('number')}"
            record = self.load_run(routine.get("id", ""), tag)
            for r in (run, record) if record else (run,):
                _as_now(r, expected.get(run.get("version")) or [])
            if record:
                self.save_run(routine["id"], tag, record)
            if isinstance(run.get("data"), dict):
                run["data"].setdefault("subject", subject_of_record((record or {}).get("data")))
        routine["shape"] = SHAPE

    def save(self, routine: dict) -> dict:
        rid = routine["id"]
        os.makedirs(self.path(rid), exist_ok=True)
        routine["updated"] = time.time()
        tmp = self.file(rid) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(routine, fh, indent=1, ensure_ascii=False)
        os.replace(tmp, self.file(rid))
        return routine

    def delete(self, rid: str) -> bool:
        p = self.path(rid)
        if not os.path.isdir(p):
            return False
        shutil.rmtree(p, ignore_errors=True)
        return True

    def ids(self) -> List[str]:
        if not os.path.isdir(self.dir):
            return []
        return [d for d in os.listdir(self.dir) if os.path.exists(self.file(d))]

    def all(self) -> List[dict]:
        out = []
        for rid in self.ids():
            r = self.load(rid)
            if r:
                out.append(r)
        out.sort(key=lambda r: r.get("updated") or r.get("created") or 0, reverse=True)
        return out

    @staticmethod
    def summary(r: dict) -> dict:
        """The routine without its scripts and outputs: what a list or a card needs."""
        cur = next((v for v in r.get("versions", []) if v.get("number") == r.get("current_version")), None) or (r.get("versions") or [{}])[-1]
        rz = (cur or {}).get("run_zero") or {}
        return {"id": r["id"], "name": r.get("name", ""), "created": r.get("created"), "updated": r.get("updated"), "source": r.get("source", ""),
                "purpose": r.get("purpose", ""), "question": r.get("question", ""), "origin": r.get("origin", {}), "instruction": r.get("instruction", ""),
                "current_version": r.get("current_version", 1), "versions": len(r.get("versions", [])), "runs": len(r.get("runs", [])),
                "verified": bool(rz.get("verified")), "run_zero_status": rz.get("status", ""), "run_zero_line": rz.get("line", ""),
                "inputs": len((cur or {}).get("manifest", {}).get("parameters", [])),
                "results": sum(1 for x in (cur or {}).get("manifest", {}).get("results", []) if not x.get("dropped")),
                "figures": ((cur or {}).get("manifest", {}).get("figures") or {}).get("count", 0),
                "data": ((cur or {}).get("manifest", {}).get("data") or {})}

    def by_origin(self) -> Dict[Tuple[str, str], List[dict]]:
        """(thread id, chain id) -> the routine versions promoted from that chain: what a favourite's card shows, and the
        routine's instruction (§15.6), which the Save-as-routine dialog offers again for a next version."""
        out: Dict[Tuple[str, str], List[dict]] = {}
        for r in self.all():
            for v in r.get("versions", []):
                pf = v.get("promoted_from") or r.get("origin") or {}
                key = (str(pf.get("thread_id", "")), str(pf.get("chain_id", "")))
                out.setdefault(key, []).append({"id": r["id"], "name": r.get("name", ""), "version": v.get("number", 1), "instruction": r.get("instruction", "")})
        return out

    def run_dir(self, rid: str, tag: str) -> str:
        return os.path.join(self.path(rid), "runs", _safe(tag))

    def save_run(self, rid: str, tag: str, record: dict) -> None:
        folder = self.run_dir(rid, tag)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "run.json"), "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=1, ensure_ascii=False)

    def load_run(self, rid: str, tag: str) -> Optional[dict]:
        f = os.path.join(self.run_dir(rid, tag), "run.json")
        if not os.path.exists(f):
            return None
        with open(f, encoding="utf-8") as fh:
            return json.load(fh)

    def run_files(self, rid: str, tag: str) -> Tuple[str, List[str]]:
        """(the printed output, the figures as their JSON strings) of a run, from its folder."""
        folder = self.run_dir(rid, tag)
        out, figs = "", []
        p = os.path.join(folder, "stdout.txt")
        if os.path.exists(p):
            with open(p, encoding="utf-8", errors="replace") as fh:
                out = fh.read()
        for name in sorted(f for f in (os.listdir(folder) if os.path.isdir(folder) else []) if f.startswith("fig_") and f.endswith(".json")):
            with open(os.path.join(folder, name), encoding="utf-8", errors="replace") as fh:
                figs.append(fh.read())
        return out, figs

    def save_run_files(self, rid: str, tag: str, stdout: str, figures: List[str]) -> dict:
        folder = os.path.join(self.path(rid), "runs", _safe(tag))
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "stdout.txt"), "w", encoding="utf-8") as fh:
            fh.write(stdout or "")
        paths = []
        for i, fig in enumerate(figures or [], 1):
            p = os.path.join(folder, f"fig_{i}.json")
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(fig if isinstance(fig, str) else json.dumps(fig))
            paths.append(p)
        return {"folder": folder, "figures": paths}


def script_with_defaults(version: dict) -> str:
    """The version's script as a file for a notebook: the INPUTS block at the top with the defaults."""
    return with_inputs(version.get("script") or "", defaults_of((version.get("manifest") or {}).get("parameters") or []))


def source_kind(data: Optional[dict]) -> str:
    s = str((data or {}).get("source") or "").lower()
    if s in ("csv", "file", "parquet", "json", "xlsx", "upload", "cache", "frame"):
        return "file"
    if s in ("intervals", "endura", "sweatstack"):
        return s
    return "file" if (data or {}).get("name") else (s or "none")
