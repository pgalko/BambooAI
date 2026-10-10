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
2. Where a date literal is the data's own first or last date, make it the data's range (the column's .min() or .max()) so the period chosen at load time is the only period there is. Where it is a boundary inside the data, make it an input.
3. Propose each remaining constant as an input: at most five, each of one type - number, numbers (a short list of numbers), date_window (two dates), choice (one value of a column, or several when "multiple" is true), toggle. Keep a constant a constant when unsure; fewer inputs is better than more.
4. Rewrite the code as find/replace edits, never by retyping it: each edit's "find" is a verbatim fragment that occurs exactly once in the cell it names, and "replace" is the same fragment with the constant replaced by INPUTS["key"]. A label written into a RESULT call that carries a constant (a count, an identifier) may read the input through an f-string. Leave the method, the cell markers, the order of the cells and every RESULT call otherwise untouched. The block INPUTS = {...} is written at the top of the script before each run; do not write it yourself.
5. Reply with exactly this object:
{"name": "a short title for the method, at most 60 characters",
 "inputs": [{"key": "snake_case", "label": "what the person sees", "type": "number | numbers | date_window | choice | toggle", "default": "the value the analysis used, in the type's form", "origin": "one short clause: where the value came from in the analysis", "column": "for a choice: the column its values come from", "multiple": false}],
 "edits": [{"cell": 3, "find": "verbatim fragment", "replace": "the same fragment reading INPUTS[...]"}],
 "kept": ["one clause per constant left as it is, and why"]}
With nothing worth making an input, return "inputs": [] and "edits": [] - the method then runs as it is on data of the same shape.
Keep the object short: each "find" the shortest fragment that still occurs once in its cell, the clauses brief, nothing outside the object."""

PROMOTER_RETRY = "Your reply could not be read ({problem}). Reply again with the JSON object only, as specified."
PROMOTER_CUT = ("Your reply was cut off at the token limit before the object was complete ({got} characters arrived). Reply again, shorter: "
                "the JSON object only, each \"find\" the shortest fragment that still occurs once in its cell, nothing outside the object.")


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
             ("athlete_profiles_race_", "profile"), ("race_turns_race_", "turns"), ("race_climbs_race_", "climbs"),
             ("race_waymarkers_race_", "waymarkers"))
_STRING_RE = re.compile(r"""(?P<q>'|")(?P<body>(?:(?!(?P=q)).)*)(?P=q)""")


def aux_kind(path: str) -> str:
    """The kind of an auxiliary file from its name: a loader's kind (summary, wellness, intervals, profile, turns,
    climbs, waymarkers) or, for a file the person attached, its name."""
    base = os.path.basename(str(path or ""))
    for prefix, kind in AUX_KINDS:
        if base.startswith(prefix):
            return kind
    return "file:" + base


def loader_file_literals(text: str) -> List[str]:
    """The string literals in a fragment that name a loader's file (datasets/<user>/<kind>_..., whole or in part): the
    names are the loader's, bound at each run, so an edit must leave them exactly as they are."""
    out = []
    for m in _STRING_RE.finditer(text or ""):
        body = m.group("body")
        if body.lstrip("./").startswith("datasets/") and not aux_kind(body).startswith("file:"):
            out.append(body)
    return sorted(out)


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


def bind_script(script: str, bindings: Dict[str, str], run_dir: str, datasets_dir: str = "", placeholders: Optional[Dict[str, str]] = None) -> Tuple[str, List[Tuple[str, str]]]:
    """The executed text of a run: every string literal that is a recorded auxiliary path (or its bare name) becomes
    this load's path - or the placeholder written for a file this load lacks -, and any other literal under the
    datasets folder becomes a file in the run's own folder, so a run never writes into the person's cache. Returns the
    text and the substitutions made, for the run's record."""
    subs: List[Tuple[str, str, str]] = []
    table: Dict[str, Tuple[str, str]] = {}
    by_kind: Dict[str, Tuple[str, str]] = {}
    for old, new in (bindings or {}).items():
        table[old] = (new, "bound")
        table[os.path.basename(old)] = (new, "bound")
        by_kind.setdefault(aux_kind(old), (new, "bound"))
    for old, new in (placeholders or {}).items():
        table.setdefault(old, (new, "placeholder"))
        table.setdefault(os.path.basename(old), (new, "placeholder"))
        by_kind.setdefault(aux_kind(old), (new, "placeholder"))
    ddir = (datasets_dir or "").rstrip("/")
    seen = set()

    def repl(m):
        body = m.group("body")
        q = m.group("q")
        new, kind = None, ""
        name_kind = aux_kind(body) if (ddir and body.startswith(ddir + "/")) or body.startswith(("datasets/", "./datasets/")) else ""
        if body in table:
            new, kind = table[body]
        elif name_kind and not name_kind.startswith("file:") and name_kind in by_kind:
            # a loader's file named with something other than the recorded dates - an f-string built from an input, a
            # variable, another window (2026-10-10: a promoter wrote the window into the name) - is this load's file of
            # that kind, whatever the rest of the name says
            new, kind = by_kind[name_kind]
        elif ddir and body.startswith(ddir + "/") and run_dir:
            new, kind = run_dir.rstrip("/") + "/" + os.path.basename(body), "cache"
        if new is None or new == body:
            return m.group(0)
        if (body, new) not in seen:
            seen.add((body, new))
            subs.append((body, new, kind))
        return q + new + q
    return _STRING_RE.sub(repl, script or ""), subs


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
if 'df' in globals() and df is not None:
    df = _routine_conform(df, _ROUTINE_COLUMNS)
    if '_BambooSource' in globals():
        DS = _BambooSource(df)
# every file the executed text names is there before the cells run: a stand-in that was not written gets written now
# (an empty table with the recorded columns), a bound file that is not there is said and stood in for, a cache file the
# method reads under its run-folder name is copied there
def _routine_materialise(files):
    import os as _os, pandas as _pd
    for _new, _old, _cols, _kind in files:
        if not _new or _os.path.exists(_new):
            continue
        _d = _os.path.dirname(_new)
        if _d:
            _os.makedirs(_d, exist_ok=True)
        if _kind == 'cache' and _old and _os.path.exists(_old):
            with open(_old, 'rb') as _s, open(_new, 'wb') as _t:
                _t.write(_s.read())
            continue
        _pd.DataFrame(columns=list(_cols or [])).to_csv(_new, index=False)
        if _kind == 'bound':
            print('ROUTINE: ' + _os.path.basename(_old or _new) + ' was not where this load left it; an empty table stood in for it')
_routine_materialise(_ROUTINE_FILES)
"""


def conform_prelude(columns: Iterable[dict], files: Optional[Iterable[Tuple[str, str, List[str], str]]] = None) -> str:
    """The block a run executes after its inputs: the recorded columns of `df` and the files the executed text names
    (each as [this run's path, the recorded path, the recorded columns, bound | placeholder | cache]), then the conform
    of the frame and the files made sure of."""
    cols = [[str(c.get("name")), str(c.get("dtype") or "")] for c in (columns or []) if c.get("name") is not None]
    fl = [[str(n), str(o or ""), [str(c) for c in (cs or [])], str(k or "")] for n, o, cs, k in (files or [])]
    return "_ROUTINE_COLUMNS = " + json.dumps(cols) + "\n_ROUTINE_FILES = " + json.dumps(fl) + "\n" + CONFORM_PRELUDE


SHAPE_MARK = "SHAPE:"


def shape_script(bindings: Dict[str, str], aux_columns: Dict[str, List[str]], run_dir: str, absent: Iterable[str] = ()) -> str:
    """A script, run before the method, that makes this load's auxiliary files fit the recorded ones: for each binding
    a copy in the run's folder with the recorded columns it lacks added empty; for a recorded file this load lacks an
    empty table with its columns; and prints what it found - rows, the columns added - as JSON after SHAPE:."""
    spec = {"bindings": dict(bindings or {}), "columns": {k: list(v) for k, v in (aux_columns or {}).items()},
            "run_dir": run_dir, "absent": list(absent or [])}
    return ("import json as _j, os as _os\n"
            "import pandas as _pd\n"
            "_spec = _j.loads(" + repr(json.dumps(spec)) + ")\n"
            "_os.makedirs(_spec['run_dir'], exist_ok=True)\n"
            "_out = {'files': {}, 'placeholders': {}}\n"
            "for _old, _new in _spec['bindings'].items():\n"
            "    _rec = _spec['columns'].get(_old) or []\n"
            "    try:\n"
            "        _fr = _pd.read_csv(_new) if _new.lower().endswith('.csv') else _pd.read_parquet(_new)\n"
            "    except Exception as _exc:\n"
            "        _out['files'][_old] = {'path': _new, 'error': str(_exc)[:200]}\n"
            "        continue\n"
            "    _missing = [c for c in _rec if c not in _fr.columns]\n"
            "    _empty = [c for c in _fr.columns if _fr[c].isna().all()]\n"
            "    _target = _new\n"
            "    if _missing:\n"
            "        for c in _missing: _fr[c] = _pd.NA\n"
            "        _target = _os.path.join(_spec['run_dir'], _os.path.basename(_new))\n"
            "        _fr.to_csv(_target, index=False)\n"
            "    _out['files'][_old] = {'path': _target, 'rows': int(len(_fr)), 'missing': _missing, 'empty': _empty, 'columns': [str(c) for c in _fr.columns]}\n"
            "for _old in _spec['absent']:\n"
            "    _rec = _spec['columns'].get(_old) or []\n"
            "    _target = _os.path.join(_spec['run_dir'], _os.path.basename(_old))\n"
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


PRECHECK_MARK = "PRECHECK:"


def precheck_script(checks: Dict[str, List[str]]) -> str:
    """A script that reports, for each column named by a choice input, which of its chosen values the frame holds."""
    spec = json.dumps({str(k): [str(x) for x in v] for k, v in (checks or {}).items()})
    return ("import json as _j\n"
            "_spec = _j.loads(" + repr(spec) + ")\n"
            "_out = {'rows': int(len(df)), 'columns': [str(c) for c in df.columns], 'values': {}}\n"
            "for _col, _vals in _spec.items():\n"
            "    if _col in df.columns:\n"
            "        _have = set(df[_col].dropna().astype(str).unique().tolist())\n"
            "        _out['values'][_col] = {v: (v in _have) for v in _vals}\n"
            "    else:\n"
            "        _out['values'][_col] = None\n"
            "print(" + repr(PRECHECK_MARK + " ") + " + _j.dumps(_out))\n")


def read_precheck(stdout: str) -> Optional[dict]:
    for ln in reversed((stdout or "").splitlines()):
        if ln.strip().startswith(PRECHECK_MARK):
            try:
                return json.loads(ln.strip()[len(PRECHECK_MARK):].strip())
            except ValueError:
                return None
    return None


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
    """What the precheck did not find: 'x is not in column c'; a column the frame lacks counts for every value."""
    out = []
    vals = (found or {}).get("values") or {}
    for col, wanted in (checks or {}).items():
        have = vals.get(col)
        for v in wanted:
            if have is None or not have.get(str(v)):
                out.append(f"'{v}' is not in column {col}" if have is not None else f"column {col} is not in this data (for '{v}')")
    return out


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


def compare_runs(manifest_results: List[dict], now: List[dict], before: Optional[List[dict]]) -> dict:
    """This run's lines against a reference run's, by position: the change, whether the intervals overlap, what is
    missing on either side. Dropped lines are printed but not compared. Marks: up / down when the intervals do not
    overlap (or, without intervals, when the estimate changed), same when they do, missing when a side lacks the line."""
    rows = []
    moved = within = missing = changed = 0
    for i, m in enumerate(manifest_results or []):
        if m.get("dropped") or m.get("estimate") is None:
            continue
        a = now[i] if i < len(now or []) else None
        b = before[i] if before is not None and i < len(before) else None
        row = {"cell": m.get("cell"), "index": m.get("index"), "label": m.get("label", ""), "unit": m.get("unit", ""), "direction": m.get("direction", ""), "typed": bool(m.get("typed")),
               "now": {"estimate": a.get("estimate"), "low": a.get("low"), "high": a.get("high")} if a else None,
               "before": {"estimate": b.get("estimate"), "low": b.get("low"), "high": b.get("high")} if b else None,
               "change": None, "overlap": None, "mark": "missing"}
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
