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


def with_inputs(script: str, values: Dict[str, object]) -> str:
    """The script with its INPUTS block in place of the mark (a script without the mark gets the block at the top)."""
    block = inputs_block(values)
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
1. Name the constants written into the code that would have to change for the method to apply to other data of the same shape: period boundaries, identifiers of subjects or groups, thresholds, filters, bin edges, exclusions. Leave alone the constants that belong to the method itself (plausibility bounds, a bootstrap size, a seed, column names) and anything that is the data's own vocabulary.
2. Where a date literal is the data's own first or last date, make it the data's range (the column's .min() or .max()) so the period chosen at load time is the only period there is. Where it is a boundary inside the data, make it an input.
3. Propose each remaining constant as an input: at most five, each of one type - number, numbers (a short list of numbers), date_window (two dates), choice (one value of a column, or several when "multiple" is true), toggle. Keep a constant a constant when unsure; fewer inputs is better than more.
4. Rewrite the code as find/replace edits, never by retyping it: each edit's "find" is a verbatim fragment that occurs exactly once in the cell it names, and "replace" is the same fragment with the constant replaced by INPUTS["key"]. A label written into a RESULT call that carries a constant (a count, an identifier) may read the input through an f-string. Leave the method, the cell markers, the order of the cells and every RESULT call otherwise untouched. The block INPUTS = {...} is written at the top of the script before each run; do not write it yourself.
5. Reply with exactly this object:
{"name": "a short title for the method, at most 60 characters",
 "inputs": [{"key": "snake_case", "label": "what the person sees", "type": "number | numbers | date_window | choice | toggle", "default": "the value the analysis used, in the type's form", "origin": "one short clause: where the value came from in the analysis", "column": "for a choice: the column its values come from", "multiple": false}],
 "edits": [{"cell": 3, "find": "verbatim fragment", "replace": "the same fragment reading INPUTS[...]"}],
 "kept": ["one clause per constant left as it is, and why"]}
With nothing worth making an input, return "inputs": [] and "edits": [] - the method then runs as it is on data of the same shape."""

PROMOTER_RETRY = "Your reply could not be read ({problem}). Reply again with the JSON object only, as specified."


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
    if s in ("csv", "file", "parquet", "json", "xlsx", "upload"):
        return "file"
    if s in ("intervals", "endura", "sweatstack"):
        return s
    return "file" if (data or {}).get("name") else (s or "none")
