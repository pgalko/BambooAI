"""Lookups: what the Architect may ask of the data to check a line a brief rests on (docs/ARCHITECT_DESIGN.md §2.4,
§2.13).

A lookup counts, lists or totals what is there, and nothing else: it does not compare, average, model or test. The
vocabulary is closed. clean() takes a request in, or refuses it in words. script() writes the one program that
answers a round of lookups over the loaded data; the host runs it where the analysis' cells run. read() takes the
answers back, and found() says one on a line, as the brief and the analyst show it.

    {"about": "...",                  the line of the brief it checks, word for word
     "op": "count" | "list" | "total",
     "data": "...",                   a file beside the main table, by its name; absent: the main table
     "column": "...",                 count: the rows that have a value in it; list: its values; total: its sum
     "where": [{"column": "...", "is": ...}, {"column": "...", "from": ..., "to": ...}],
     "by": "..." | {"column": "...", "every": "week" | "month" | "year"}}

The request is data from end to end: names and values reach the program inside one JSON text, never as code.
"""
from __future__ import annotations

import json
import re
from typing import Optional

OPS = ("count", "list", "total")
EVERY = ("week", "month", "year")
MAX_LOOKUPS = 6                  # in one round
MAX_WHERE = 4
MAX_GROUPS = 40                  # a split into more is refused: a list cut short would hide the group that matters
MAX_VALUES = 12                  # the values of a text column a list names, the most frequent first
NAME_CHARS = 200
ABOUT_CHARS = 600                # the line a lookup checks: one line of a brief (analyst/brief.py)
FACT_CHARS = 600                 # what a lookup found, on one line of a brief; a longer result is refused, never cut
MARK = "LOOKUPS:"
NOT_RUN = "the data could not be reached"
TOO_LONG = "the result is too long to show: narrow it with a condition, or split it more coarsely"


def _name(value) -> str:
    return value.strip()[:NAME_CHARS] if isinstance(value, str) else ""


def clean(request) -> tuple:
    """(the lookup in its known shape, '') - or (None, why it is refused). Only what the vocabulary names is kept."""
    if not isinstance(request, dict) or request.get("op") not in OPS:
        return None, "a lookup is a count, a list or a total"
    out = {"op": request["op"]}
    if isinstance(request.get("about"), str) and request["about"].strip():
        out["about"] = re.sub(r"\s+", " ", request["about"]).strip()[:ABOUT_CHARS]
    if _name(request.get("column")):
        out["column"] = _name(request["column"])
    if _name(request.get("data")):
        out["data"] = _name(request["data"]).replace("\\", "/").rsplit("/", 1)[-1]      # a file is known by its name
    if out["op"] != "count" and "column" not in out:
        return None, f"a {out['op']} names its column"
    where = []
    for w in request.get("where") if isinstance(request.get("where"), list) else []:
        if not isinstance(w, dict) or not _name(w.get("column")):
            return None, "a condition names its column"
        cond = {"column": _name(w["column"])}
        for key in ("is", "from", "to"):
            if isinstance(w.get(key), (str, int, float)):
                cond[key] = w[key].strip()[:NAME_CHARS] if isinstance(w[key], str) else w[key]
        if len(cond) == 1 or ("is" in cond and len(cond) > 2):
            return None, "a condition says what the column is, or the range it lies in"
        where.append(cond)
    if len(where) > MAX_WHERE:
        return None, f"a lookup takes {MAX_WHERE} conditions at most"
    if where:
        out["where"] = where
    by = request.get("by")
    if isinstance(by, dict):
        if not _name(by.get("column")) or by.get("every") not in EVERY:
            return None, "a split over time names a column of dates and week, month or year"
        out["by"] = {"column": _name(by["column"]), "every": by["every"]}
    elif _name(by):
        out["by"] = _name(by)
    elif by is not None:
        return None, "a split names one column"
    if out["op"] == "list" and "by" in out:
        return None, "a list has no split"
    return out, ""


def said(lookup: dict) -> str:
    """What a lookup asks, in words: the head of its line."""
    column = lookup.get("column", "")
    text = {"count": "rows with a value in " + column if column else "rows", "list": "values of " + column, "total": "total of " + column}[lookup["op"]]
    for i, w in enumerate(lookup.get("where", [])):
        text += (" and " if i else " where ") + w["column"] + " is " + (
            str(w["is"]) if "is" in w else f"from {w['from']} to {w['to']}" if "from" in w and "to" in w
            else f"from {w['from']}" if "from" in w else f"up to {w['to']}")
    by = lookup.get("by")
    if by:
        text += f" by {by['every']} of {by['column']}" if isinstance(by, dict) else f" by {by}"
    return text + (f", in {lookup['data']}" if lookup.get("data") else "")


def _number(x) -> str:
    """A count or a total: thousands apart, two decimals at most."""
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return str(x)
    return f"{x:,.0f}" if float(x) == int(x) else f"{x:,.2f}".rstrip("0").rstrip(".")


def _value(x) -> str:
    """A value of the data itself: as it stands, a number without the thousands' commas."""
    return _number(x).replace(",", "") if isinstance(x, (int, float)) else str(x)


def found(lookup: dict, answer) -> tuple:
    """(one lookup with what it found, on one line; whether that is a result). The line opens with what was asked;
    then the numbers - or, where there is no result, why: the lookup was refused, the data was not reached, or the
    result does not fit on a line."""
    one = lambda text: " ".join(f"{said(lookup)}: {text}".split())      # one line, whatever a name or a value of the data holds
    if not isinstance(answer, dict) or answer.get("refused"):
        return one(f"not looked up - {(answer.get('refused') if isinstance(answer, dict) else '') or NOT_RUN}"), False
    if "value" in answer:
        line = _number(answer["value"])
    elif "groups" in answer:
        line = " · ".join(f"{label} {_number(v)}" for label, v in answer["groups"]) or "none"
    else:
        n, values = answer.get("different", 0), answer.get("range") or answer.get("values") or []
        if n < 2:
            line = _value(values[0]) if values else "none"
        elif "range" in answer:
            line = f"{_number(n)} different, {_value(values[0])} to {_value(values[1])}"
        else:
            line = f"{_number(n)} different: " + ", ".join(str(v) for v in values) + (f", and {_number(n - len(values))} more" if n > len(values) else "")
    return (one(line), True) if len(one(line)) <= FACT_CHARS else (one(f"not looked up - {TOO_LONG}"), False)


# The program. It runs where the data is: `df` is the main table when one is loaded. One answer to a lookup:
#   {"value": number}                             a count or a total
#   {"groups": [[label, number], ...]}            the same, split
#   {"different": n, "range": [low, high]}        a list of numbers or of dates
#   {"different": n, "values": [text, ...]}       a list of text: the most frequent values
#   {"refused": why}
_PROGRAM = r'''
import json as _j
import re as _re
import warnings as _w
import pandas as _pd

_spec = _j.loads(__SPEC__)
_EVERY = {"week": "W", "month": "M", "year": "Y"}
_read = {}

class _No(Exception):
    pass

def _frame(q):
    name = q.get("data")
    if not name:
        if globals().get("df") is None:
            raise _No("no main table is loaded")
        return df
    path = _spec["files"].get(name)
    if path is None:
        raise _No("there is no file " + name + (": the files are " + ", ".join(_spec["files"]) if _spec["files"] else ""))
    if name not in _read:
        kind = str(path).rsplit(".", 1)[-1].lower()
        _read[name] = {"csv": _pd.read_csv, "json": _pd.read_json, "xlsx": _pd.read_excel, "xls": _pd.read_excel}.get(kind, _pd.read_parquet)(path)
    return _read[name]

def _col(f, c):
    if c not in f.columns:
        raise _No("there is no column " + str(c) + ": the columns are " + ", ".join(str(x) for x in list(f.columns)[:60]))
    return f[c]

def _dates(s):
    # The column as dates, each on the clock it was written in; None when it does not hold dates. Text counts as dates
    # only when written year first (2026-03-05, with or without a time): 05/03/2026 could be either day.
    if _pd.api.types.is_numeric_dtype(s):
        return None
    d = s
    if not _pd.api.types.is_datetime64_any_dtype(d):
        text = s.dropna().astype(str)
        if not len(text) or text.head(50).str.match(r"\s*\d{4}-\d{2}(-\d{2}([T ]\d{2}:\d{2}.*)?)?\s*$").mean() < 0.8:
            return None
        text = s.astype(str).str.replace(r"(:\d\d(?:\.\d+)?)\s?(?:Z|[+-]\d\d:?\d\d)\s*$", r"\1", regex=True)      # a zone after the time is dropped
        d = _pd.to_datetime(text, errors="coerce", format="ISO8601")
        if d.notna().sum() < 0.8 * len(s.dropna()):
            return None
    return d.dt.tz_localize(None) if d.dt.tz is not None else d

def _moment(v):
    t = _pd.to_datetime(v)
    return t.tz_localize(None) if t.tzinfo is not None else t

def _is(f, s, v):
    if isinstance(v, str) and _re.match(r"\s*\d{4}-\d{1,2}-\d{1,2}", v):
        d = _dates(s)
        if d is not None:
            day = _moment(v).normalize()
            return f[(d >= day) & (d < day + _pd.Timedelta(days=1))]
    if _pd.api.types.is_numeric_dtype(s) and not _pd.api.types.is_bool_dtype(s):
        try:
            return f[s == float(v)]
        except (TypeError, ValueError):
            pass
    return f[s.astype(str).str.strip().str.lower() == str(v).strip().lower()]

def _where(f, conds):
    for w in conds:
        s = _col(f, w["column"])
        if "is" in w or not s.notna().any():                         # no value left to compare: no row meets the condition
            f = _is(f, s, w["is"]) if "is" in w else f[s.notna()]
            continue
        d = _dates(s)
        v = d if d is not None else _pd.to_numeric(s, errors="coerce")
        if d is None and not v.notna().any():
            raise _No(str(w["column"]) + " holds neither numbers nor dates")
        keep = v.notna()
        try:
            if "from" in w:
                keep &= v >= (_moment(w["from"]) if d is not None else float(w["from"]))
            if "to" in w and d is not None:                           # up to a day is through that day
                top = _moment(w["to"])
                keep &= (v < top + _pd.Timedelta(days=1)) if top == top.normalize() else (v <= top)
            elif "to" in w:
                keep &= v <= float(w["to"])
        except Exception:
            raise _No("the range of " + str(w["column"]) + " could not be read")
        f = f[keep]
    return f

def _num(v):
    x = float(v)
    return int(x) if abs(x) < 1e15 and x == int(x) else round(x, 4)

def _label(k):
    try:
        return str(int(k)) if isinstance(k, float) and k == int(k) else str(k)
    except (ValueError, OverflowError):
        return str(k)

def _groups(f, s, by):
    if isinstance(by, dict):
        c = _col(f, by["column"])
        if not c.notna().any():                                       # nothing to split
            return []
        d = _dates(c)
        if d is None:
            raise _No(str(by["column"]) + " does not hold dates")
        g = s.groupby(d.dt.to_period(_EVERY[by["every"]])).sum()
        if len(g):                                                    # a week with no rows shows, as 0
            g = g.reindex(_pd.period_range(g.index.min(), g.index.max(), freq=_EVERY[by["every"]]), fill_value=0)
        label = (lambda k: str(k.start_time.date())) if by["every"] == "week" else str
    else:
        key = _col(f, by)
        try:
            g = s.groupby(key).sum().sort_index()
        except TypeError:
            g = s.groupby(key.astype(str)).sum().sort_index()
        label = _label
    if len(g) > _spec["groups"]:
        raise _No("the split gives " + str(len(g)) + " groups, more than " + str(_spec["groups"]) + ": narrow it with a condition, or split it more coarsely")
    return [[label(k), _num(v)] for k, v in g.items()]

def _values(s):
    if _pd.api.types.is_numeric_dtype(s) and not _pd.api.types.is_bool_dtype(s):
        s = s.dropna()
        return {"different": int(s.nunique()), "range": [_num(s.min()), _num(s.max())] if len(s) else []}
    d = None if _pd.api.types.is_bool_dtype(s) else _dates(s)
    if d is not None:
        d = d.dropna()
        return {"different": int(d.dt.normalize().nunique()), "range": [str(d.min().date()), str(d.max().date())] if len(d) else []}
    counts = s.dropna().astype(str).value_counts().sort_index().sort_values(ascending=False, kind="stable")
    return {"different": int(len(counts)), "values": [str(k) for k in counts.index[:_spec["values"]]]}

def _answer(q):
    f = _where(_frame(q), q.get("where") or [])
    if q["op"] == "list":
        return _values(_col(f, q["column"]))
    if q["op"] == "count":
        s = _col(f, q["column"]).notna().astype(int) if q.get("column") else _pd.Series(1, index=f.index)
    else:
        c = _col(f, q["column"])
        s = _pd.to_numeric(c, errors="coerce")
        if _pd.api.types.is_datetime64_any_dtype(c) or (len(f) and not s.notna().any()):
            raise _No(str(q["column"]) + " does not hold numbers")
    return {"groups": _groups(f, s, q["by"])} if q.get("by") else {"value": _num(s.sum())}

_out = []
with _w.catch_warnings():
    _w.simplefilter("ignore")
    for _q in _spec["lookups"]:
        try:
            _out.append(_answer(_q))
        except _No as _e:
            _out.append({"refused": str(_e)})
        except Exception as _e:
            _out.append({"refused": "it could not be looked up (" + type(_e).__name__ + ")"})
print(__MARK__ + " " + _j.dumps(_out))
'''


def script(lookups: list, files: Optional[dict] = None) -> str:
    """The program that answers a round of lookups: over `df`, the main table, or over a file beside it (`files`: a
    file's name -> the path the program reads). It prints one line: MARK, then the answers as JSON, one to a lookup."""
    spec = {"lookups": [{k: v for k, v in q.items() if k != "about"} for q in lookups], "files": dict(files or {}),
            "groups": MAX_GROUPS, "values": MAX_VALUES}
    return _PROGRAM.replace("__MARK__", repr(MARK)).replace("__SPEC__", repr(json.dumps(spec)), 1).lstrip()


def read(stdout: str, n: int) -> list:
    """The program's answers, one to a lookup; each lookup refused when the line is not there or does not fit."""
    line = next((ln for ln in reversed((stdout or "").splitlines()) if ln.startswith(MARK)), "")
    try:
        answers = json.loads(line[len(MARK):])
    except ValueError:
        answers = None
    if not isinstance(answers, list) or len(answers) != n or not all(isinstance(a, dict) for a in answers):
        return [{"refused": NOT_RUN} for _ in range(n)]
    return answers
