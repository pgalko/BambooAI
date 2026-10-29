"""Routines (docs/ROUTINES_DESIGN.md): an analysis kept as a method and run again, without a model, on new data.

The pure part lives here - nothing in this module talks to a model, an executor or the web app:
  - a RESULT line read back from printed output (parse_result_line, result_lines_in);
  - the lines a script is expected to print, from the kernel's records (expected_results);
  - the promoter's prompt and the reading of its reply (PROMOTER_SYSTEM, promoter_user, parse_promoter);
  - the edits applied to the cells, grouped by the input they serve (apply_edits, finish_inputs);
  - the script with its INPUTS block (split_script, join_script, with_inputs);
  - the check of a run's lines against the expected ones (check_lines);
  - the store: one folder per routine under <storage>/routines/ (RoutineStore).

The standing rule (DESIGN_CHECKLIST C5) holds for every string here: nothing a model reads names a task.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time
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


def result_lines_in(stdout: str) -> List[dict]:
    """Every RESULT line a run printed, in order."""
    out = []
    for ln in (stdout or "").splitlines():
        if ln.strip().startswith("RESULT:"):
            r = parse_result_line(ln)
            if r is not None:
                out.append(r)
    return out


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

You receive the question the analysis answered, the summary of its answer, a description of the data it ran on, the cells of the script in execution order, and the ledger of RESULT lines the cells recorded. Reply with one JSON object and nothing else.

What to do:
1. Name the constants written into the code that would have to change for the method to apply to other data of the same shape: period boundaries inside the data, identifiers of subjects or groups, thresholds, filters, bin edges, exclusions. Leave alone the constants that belong to the method itself (plausibility bounds, a bootstrap size, a seed, column names) and anything that is the data's own vocabulary. A file name under the datasets folder is the loader's, written for the period it loaded: leave it exactly as it is, dates included - each run binds it to the file that run loads - and never make the loaded period itself an input; the period is chosen when the data is loaded, before the method runs.
2. Where a date literal is the data's own first or last date, make it the data's range (the column's .min() or .max()) so the period chosen at load time is the only period there is. Where it is a boundary inside the data, make it an input. Where a number is a count the data determines - the rows of a table, the periods in it, the groups - and the code uses it as a loop bound, an index or a divisor, make it that count (len(...)), not an input: the next data has its own.
3. Propose each remaining constant as an input: at most five, each of one type - number, numbers (a short list of numbers), date_window (two dates), choice (one value of a column, or several when "multiple" is true), toggle. Keep a constant a constant when unsure; fewer inputs is better than more.
4. Rewrite the code as find/replace edits, never by retyping it: each edit's "find" is a verbatim fragment that occurs exactly once in the cell it names, and "replace" is the same fragment with the constant replaced by INPUTS["key"]. A label written into a RESULT call that carries a constant (a count, an identifier) may read the input through an f-string. Leave the method, the cell markers, the order of the cells and every RESULT call otherwise untouched. The block INPUTS = {...} is written at the top of the script before each run; do not write it yourself.
5. Reply with exactly this object:
{"name": "a short title for the method, at most 60 characters",
 "inputs": [{"key": "snake_case", "label": "what the person sees", "type": "number | numbers | date_window | choice | toggle", "default": "the value the analysis used, in the type's form", "origin": "one short clause: where the value came from in the analysis", "column": "for a choice over values of a column the data has (the frame or a loaded file): that column; none for words the script matches or computes", "multiple": false}],
 "edits": [{"cell": 3, "find": "verbatim fragment", "replace": "the same fragment reading INPUTS[...]"}],
 "kept": ["one clause per constant left as it is, and why"]}
With nothing worth making an input, return "inputs": [] and "edits": [] - the method then runs as it is on data of the same shape.
Keep the object short: each "find" the shortest fragment that still occurs once in its cell, the clauses brief, nothing outside the object."""

PROMOTER_RETRY = "Your reply could not be read ({problem}). Reply again with the JSON object only, as specified."
PROMOTER_CUT = ("Your reply was cut off at the token limit before the object was complete ({got} characters arrived). Reply again, shorter: "
                "the JSON object only, each \"find\" the shortest fragment that still occurs once in its cell, nothing outside the object.")
PROMOTER_CUT_EMPTY = ("Your reply was cut off at the token limit before anything but reasoning arrived. Decide briefly - the constants that "
                      "would change for other data of the same shape, and the shortest fragment for each - and reply with the JSON object only.")


def promoter_user(question: str, summary: str, data_text: str, cells: str, ledger: Iterable[str], manifest: Optional[dict] = None) -> str:
    parts = [f"QUESTION:\n{(question or '').strip()}", f"ANSWER SUMMARY:\n{(summary or '(none)').strip()}",
             f"DATA (the frame `df` the script ran on):\n{(data_text or '(no description)').strip()}",
             "THE SCRIPT (the cells in execution order; `df` is loaded before the first cell):\n" + (cells or "").strip(),
             "RESULT LINES THE CELLS RECORDED (the method's outputs, which must still be produced, in this order):\n" + ("\n".join(ledger) or "(none)")]
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
    for k, typ in (("inputs", list), ("edits", list)):
        if k in obj and not isinstance(obj[k], typ):
            raise ValueError(f"'{k}' is not a list")
    obj.setdefault("inputs", []); obj.setdefault("edits", []); obj.setdefault("kept", [])
    return obj


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


# ----------------------------------------------------------------------------- the check of a run
def check_lines(expected: List[dict], got: List[dict], error: str = "") -> Tuple[str, str, List[dict]]:
    """A run's RESULT lines against the expected ones, by position. Returns (status, line, details):
    reproduced | differed | failed. Identical numbers (as printed) reproduce; a different count, or a different
    estimate or interval at a position, differs; an error fails."""
    if error:
        last = str(error).strip().splitlines()[-1][:200] if str(error).strip() else "unknown error"
        return "failed", f"the script stopped with an error ({last})", []
    exp = [e for e in expected if e.get("estimate") is not None]
    if not exp:
        return "reproduced", "ran without error" + (f"; {len(got)} result line(s) printed" if got else " (no result lines to compare)"), []
    if len(got) != len(exp):
        return "differed", f"{len(got)} result line(s) came back, {len(exp)} expected", []
    diffs = []
    for e, g in zip(exp, got):
        same = all((number(e.get(k)) == number(g.get(k))) or (e.get(k) == g.get(k)) for k in ("estimate", "low", "high"))
        if not same:
            diffs.append({"cell": e.get("cell"), "index": e.get("index"), "label": e.get("label"), "expected": e.get("estimate"), "got": g.get("estimate")})
    if diffs:
        shown = "; ".join(f"[cell {d['cell']}] {d['label'][:50]}: {d['expected']} -> {d['got']}" for d in diffs[:4])
        return "differed", f"{len(diffs)} of {len(exp)} result lines differ ({shown}{'; ...' if len(diffs) > 4 else ''})", diffs
    return "reproduced", f"reproduced: {len(exp)} result line(s) identical", []


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
            out = {"hit": True, "df_id": str(f.get("df_id") or ""), "files": [have[(folder, n)] for n in names.values()], "rows": rows, "date_range": f"{cs} to {ce}"}
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


def cut_name(path: str, start: str, end: str) -> str:
    """The loader's name for this file had it been loaded for the window: the kind's prefix with the window's dates;
    a file of another kind keeps its name."""
    k = aux_kind(path)
    if k in CUT_RULES or kind_prefix(k):
        return f"{kind_prefix(k)}{str(start).replace('-', '')}_to_{str(end).replace('-', '')}.csv"
    return os.path.basename(path)


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


def missing_values(checks: Dict[str, List[str]], found: Optional[dict]) -> List[str]:
    """What the precheck did not find: 'x is not in column c' (naming the file when the column lives in one); a
    column neither the frame nor the files loaded have counts for every value."""
    out = []
    vals = (found or {}).get("values") or {}
    where = (found or {}).get("where") or {}
    for col, wanted in (checks or {}).items():
        have = vals.get(col)
        table = str(where.get(col) or "")
        kind = aux_kind(table) if table and table != "the frame" else ""
        of = "" if not table or table == "the frame" else (f" of the {kind} file" if kind and not kind.startswith("file:") else f" of {table}")
        for v in wanted:
            if have is None or not have.get(str(v)):
                out.append(f"'{v}' is not in column {col}{of}" if have is not None else f"column {col} is not in this data (for '{v}')")
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


def failed_cell(script: str, error: str) -> Optional[int]:
    """The cell a run failed in, from the traceback's line number in the script (the markers count the lines)."""
    nums = [int(n) for n in re.findall(r'File "<string>", line (\d+)', error or "")]
    head = re.search(r"^Error on line (\d+):", error or "", re.M)       # the executor's condensed traceback names the line first (its frames may be cut at 1,000 characters)
    if head:
        nums = [int(head.group(1))] + nums
    if not nums:
        return None
    line_no = nums[0] if head else nums[-1]
    cell = None
    for i, ln in enumerate((script or "").splitlines(), 1):
        if i > line_no:
            break
        m = _CELL_MARK_RE.match(ln)
        if m:
            cell = int(m.group(1))
    return cell


def run_status(expected: List[dict], got: List[dict], error: str, reference: Optional[List[dict]], script: str = "") -> Tuple[str, str]:
    """The run's status: failed (with the cell), timed_out, differed (a line missing), reproduced (every number as the
    reference run's) or ran (the normal case on new data)."""
    if error:
        text = str(error).strip()
        last = (error_line(text) or "unknown error")[:200]
        if "TIMEOUT" in text.upper() or "timed out" in text.lower():
            return "timed_out", "timed out: " + last
        cell = failed_cell(script, text)
        return "failed", (f"failed at cell {cell}: " if cell else "failed: ") + last
    exp = [e for e in expected if e.get("estimate") is not None]
    if not exp:
        return "ran", "ran without error (no result lines to compare)" + (f"; {len(got)} line(s) printed" if got else "")
    if len(got) < len(exp):
        gone = exp[len(got):]
        return "differed", f"{len(exp) - len(got)} of {len(exp)} result lines did not come back (" + "; ".join(f"[cell {e['cell']}] {str(e.get('label', ''))[:50]}" for e in gone[:3]) + ")"
    if len(got) > len(exp):
        return "differed", f"{len(got)} result lines came back, {len(exp)} expected"
    blank = [g for g in got if number(g.get("estimate")) is not None and number(g["estimate"]) != number(g["estimate"])]   # nan: the line printed, no number in it
    if blank:
        return "differed", f"{len(blank)} of {len(got)} result line{'s' if len(got) != 1 else ''} came back without a number (nan)"
    if reference is not None and len(reference) == len(got) and all(
            all((number(a.get(k)) == number(b.get(k))) or (a.get(k) == b.get(k)) for k in ("estimate", "low", "high")) for a, b in zip(got, reference)):
        return "reproduced", f"reproduced: every result line as the run before ({len(got)} line{'s' if len(got) != 1 else ''})"
    return "ran", f"ran: {len(got)} result line{'s' if len(got) != 1 else ''}" + (", 0 to compare" if not exp else "")


def _ivl(r: Optional[dict]) -> Optional[Tuple[float, float]]:
    if not r:
        return None
    lo, hi = number(r.get("low")), number(r.get("high"))
    return (lo, hi) if lo is not None and hi is not None else None


def cell_text(script: str, cell: int) -> str:
    """The code of cell `cell` in a script - from its marker to the next marker or the tail - without the marker."""
    lines = (script or "").splitlines()
    start = next((i for i, ln in enumerate(lines) if _CELL_MARK_RE.match(ln) and int(_CELL_MARK_RE.match(ln).group(1)) == int(cell)), None)
    if start is None:
        return ""
    end = next((i for i in range(start + 1, len(lines)) if _CELL_MARK_RE.match(lines[i]) or lines[i].startswith(_TAIL_MARK.strip("\n"))), len(lines))
    return "\n".join(lines[start + 1:end]).strip("\n")


def compare_runs(manifest_results: List[dict], now: List[dict], before: Optional[List[dict]], failed: bool = False) -> dict:
    """This run's lines against a reference run's, by position: the change, whether the intervals overlap, what is
    missing on either side. Dropped lines are printed but not compared. Marks: up / down when the intervals do not
    overlap (or, without intervals, when the estimate changed), same when they do, missing when a side lacks the line
    - and, in a run that failed (`failed`), unreached for a line the run did not get to: the lines printed before
    the failure are compared like any other (step 4, 2026-10-11), the rest said as not reached, not as missing."""
    rows = []
    moved = within = missing = changed = unreached = 0
    for i, m in enumerate(manifest_results or []):
        if m.get("dropped") or m.get("estimate") is None:
            continue
        a = now[i] if i < len(now or []) else None
        b = before[i] if before is not None and i < len(before) else None
        row = {"cell": m.get("cell"), "index": m.get("index"), "label": m.get("label", ""), "unit": m.get("unit", ""), "direction": m.get("direction", ""), "typed": bool(m.get("typed")),
               "now": {"estimate": a.get("estimate"), "low": a.get("low"), "high": a.get("high")} if a else None,
               "before": {"estimate": b.get("estimate"), "low": b.get("low"), "high": b.get("high")} if b else None,
               "change": None, "overlap": None, "mark": "missing"}
        if failed and a is None:
            row["mark"] = "unreached"; unreached += 1
            rows.append(row)
            continue
        if a and number(a.get("estimate")) is not None and (number(a["estimate"]) != number(a["estimate"])):   # nan: no number came out
            a = None
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
    compared = len(rows) - missing - unreached
    if before is None:
        line = "nothing to compare with: the first run of this version" + (f" ({unreached} line{'s' if unreached != 1 else ''} not reached)" if unreached else "")
    elif compared == 0:
        line = (f"no result line came before the failure ({unreached} not reached)" if unreached else "no result line to compare")
    else:
        parts = [f"{moved} of {compared} moved beyond their intervals" if any(r["overlap"] is not None for r in rows) else f"{changed} of {compared} changed"]
        if unreached:
            parts[0] += " before the failure"
            parts.append(f"{unreached} not reached")
        if missing:
            parts.append(f"{missing} missing")
        line = ", ".join(parts)
    return {"rows": rows, "moved": moved, "within": within, "changed": changed, "missing": missing, "unreached": unreached, "compared": compared, "line": line}


# ----------------------------------------------------------------------------- the store
def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", str(s or ""))


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
            return json.load(fh)

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
                "purpose": r.get("purpose", ""), "question": r.get("question", ""), "origin": r.get("origin", {}),
                "current_version": r.get("current_version", 1), "versions": len(r.get("versions", [])), "runs": len(r.get("runs", [])),
                "verified": bool(rz.get("verified")), "run_zero_status": rz.get("status", ""), "run_zero_line": rz.get("line", ""),
                "inputs": len((cur or {}).get("manifest", {}).get("parameters", [])),
                "results": sum(1 for x in (cur or {}).get("manifest", {}).get("results", []) if not x.get("dropped")),
                "figures": ((cur or {}).get("manifest", {}).get("figures") or {}).get("count", 0),
                "data": ((cur or {}).get("manifest", {}).get("data") or {})}

    def by_origin(self) -> Dict[Tuple[str, str], List[dict]]:
        """(thread id, chain id) -> the routine versions promoted from that chain: what a favourite's card shows."""
        out: Dict[Tuple[str, str], List[dict]] = {}
        for r in self.all():
            for v in r.get("versions", []):
                pf = v.get("promoted_from") or r.get("origin") or {}
                key = (str(pf.get("thread_id", "")), str(pf.get("chain_id", "")))
                out.setdefault(key, []).append({"id": r["id"], "name": r.get("name", ""), "version": v.get("number", 1)})
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
