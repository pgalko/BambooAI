"""The context (docs/CONTEXT_DESIGN.md): the words written beside the data, as the app reads them - the context
table and the codes table as frames, and the map the analyst sees in DATA (§3.4): the span, passages per kind and
month, authors by role, languages, the codes with their counts. Never the text; that is reached by CTX and READ.
Pure: frames in, text out. The strings here are read by a model (the C5 scanner covers this file)."""
from __future__ import annotations

import io
import re
from collections import Counter
from typing import Optional

import pandas as pd

CONTEXT_COLUMNS = ["id", "kind", "date", "time", "end_date", "activity_id", "event_id", "source_id", "author_id",
                   "author_name", "author_role", "private", "lang", "text", "text_en", "chars", "activity_date", "copy_of"]
CODES_COLUMNS = ["id", "code", "tone", "quote", "status", "coder", "codebook_version", "direction", "basis", "about"]
MAP_KINDS_MAX = 12
MAP_CODES_MAX = 12
MAP_TOKENS_MAX = 6
# A passage kind whose every text opens with an upper-case token - the calendar's own category, written by the
# executor as `CATEGORY: name` - is tallied by that token on the map (2026-10-18): both runs of the bio-psycho-social
# question spent five or six turns finding that a race's priority lived only in `status` passages, which the map had
# counted as "status 36" and no more. The tokens are the data's own; nothing here names one.
_LEADING_TOKEN_RE = re.compile(r"^\s*([A-Z][A-Z0-9_]{1,40})(?=:|\s|$)")


def read_frame(text: str, columns: list) -> pd.DataFrame:
    """A context or codes file's text as a frame with the expected columns (missing ones added empty, the rest in
    order); an empty text is an empty frame."""
    if not (text or "").strip():
        return pd.DataFrame(columns=columns)
    df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    for c in columns:
        if c not in df.columns:
            df[c] = ""
    return df[columns + [c for c in df.columns if c not in columns]]


def read_context(text: str) -> pd.DataFrame:
    return read_frame(text, CONTEXT_COLUMNS)


def read_codes(text: str) -> pd.DataFrame:
    return read_frame(text, CODES_COLUMNS)


def _cell(v) -> str:
    """A cell as text: '' for an empty one (None, NaN, blank) - a frame built without a column has NaN there."""
    if v is None or (isinstance(v, float) and v != v):
        return ""
    return str(v).strip()


def _month(d: str) -> str:
    try:
        return pd.Timestamp(str(d)[:10]).strftime("%b")
    except Exception:                                   # noqa: BLE001
        return "?"


def _count_line(counter: Counter, limit: int, total: Optional[int] = None) -> str:
    items = counter.most_common()
    shown = ", ".join(f"{k} {v}" for k, v in items[:limit])
    more = len(items) - limit
    return shown + (f", … ({more} more)" if more > 0 else "")


def leading_tokens(texts) -> Optional[Counter]:
    """The tally of the upper-case token every text opens with (`RACE_A: …`, `SICK`), or None when any text opens
    otherwise - then the kind is prose, and a tally of its occasional capitals would mislead."""
    tally = Counter()
    for t in texts:
        m = _LEADING_TOKEN_RE.match(str(t or ""))
        if not m:
            return None
        tally[m.group(1)] += 1
    return tally or None


def single_tokens(texts) -> Optional[Counter]:
    """The tally of texts that are each one token with no space in it (a tag: `heatsession`, `primary`), or None when
    any text is longer - a label is tallied, a sentence never."""
    tally = Counter()
    for t in texts:
        t = str(t or "").strip()
        if not t or any(ch.isspace() for ch in t):
            return None
        tally[t] += 1
    return tally or None


def context_map(notes: pd.DataFrame, codes: Optional[pd.DataFrame] = None, notes_path: str = "", codes_path: str = "",
                codebook_size: int = 0) -> str:
    """The lines of docs/CONTEXT_DESIGN.md §3.4 for the DATA block. `notes` is the context table; `codes` the codes
    table when the coding pass has run (None before it)."""
    files = ", ".join(p for p in (notes_path, codes_path) if p)
    head = "CONTEXT (the words written beside the data; in the kernel as CTX" + (f"; files {files}" if files else "") + "):"
    if notes is None or len(notes) == 0:
        return head + "\n  no passages in this window: nothing was written beside the data loaded."
    n = len(notes)
    days = [str(d)[:10] for d in notes["date"].tolist() if str(d).strip()]
    span = f"{min(days)} to {max(days)}" if days else "undated"
    kinds = Counter(str(k) for k in notes["kind"].tolist())
    roles = Counter(str(r) for r in notes["author_role"].tolist() if str(r).strip())
    by_kind = []
    for kind, c in kinds.most_common(MAP_KINDS_MAX):
        sub = notes[notes["kind"] == kind]
        rs = Counter(str(r) for r in sub["author_role"].tolist() if str(r).strip())
        tokens = (leading_tokens(sub["text"].tolist()) or single_tokens(sub["text"].tolist())) if "text" in sub.columns else None
        if tokens:
            by_kind.append(f"{kind} {c} ({_count_line(tokens, MAP_TOKENS_MAX)})")
        elif kind in ("activity_message", "activity_private_note", "day_note", "plan_note") and len(rs) > 1:
            by_kind.append(f"{kind} {c} ({', '.join(f'{r} {v}' for r, v in rs.most_common())})")
        else:
            by_kind.append(f"{kind} {c}")
    months = Counter(_month(d) for d in days)
    month_order = sorted(months, key=lambda m: pd.Timestamp(f"2000-{m}-01") if m != "?" else pd.Timestamp("2000-01-01"))
    private = int(sum(1 for p in notes["private"].tolist() if str(p).strip().lower() in ("true", "1")))
    langs = Counter(str(l) for l in notes["lang"].tolist() if str(l).strip())
    lines = [head,
             f"  {span}: {n} passage{'s' if n != 1 else ''} — " + "; ".join(by_kind) + ("" if len(kinds) <= MAP_KINDS_MAX else f"; {len(kinds) - MAP_KINDS_MAX} more kinds") + ".",
             f"  authors: {', '.join(f'{r} {v}' for r, v in roles.most_common())}" + (f"; private entries {private}" if private else "")
             + f"; by month {', '.join(f'{m} {months[m]}' for m in month_order)}"
             + (f"; languages {', '.join(f'{k} {v}' for k, v in langs.most_common())}" if langs else "") + "."]
    copies = [c for c in map(_cell, notes["copy_of"].tolist()) if c] if "copy_of" in notes.columns else []
    if copies:
        lines.append(f"  {len(copies)} passage{'s' if len(copies) != 1 else ''} repeat{'s' if len(copies) == 1 else ''} an earlier passage word for word (copy_of names it): "
                     "the earlier one's words, not a second writing of them, and coded there only.")
    if "activity_date" in notes.columns:
        later = sum(1 for d, a in zip(notes["date"].tolist(), notes["activity_date"].tolist()) if _cell(a) and _cell(d)[:10] > _cell(a)[:10])
        if later:
            lines.append(f"  {later} passage{'s' if later != 1 else ''} on an activity {'were' if later != 1 else 'was'} written on a later day than the activity: "
                         "activity_date is the activity's day, date the day of writing.")
    if codes is not None and len(codes) > 0:
        cc = Counter(str(c) for c in codes["code"].tolist() if str(c).strip())
        coded = set(str(i) for i in codes["id"].tolist())
        # a tag and a copy carry no codes by design (patch 0197): the count is of the passages read and left without one
        aside = {str(i) for i, k, c in zip(notes["id"].tolist(), notes["kind"].tolist(), notes["copy_of"].tolist() if "copy_of" in notes.columns else [""] * len(notes))
                 if str(k) == "tag" or _cell(c)}
        uncoded = sum(1 for i in notes["id"].tolist() if str(i) not in coded and str(i) not in aside)
        proposed = sorted({str(c) for c, s in zip(codes["code"].tolist(), codes["status"].tolist()) if str(s) == "proposed"})
        lines.append(f"  codes (the model's reading, one row per code, with the words it rests on): {_count_line(cc, MAP_CODES_MAX)}"
                     + (f" ({len(cc)} of {codebook_size} codes used)" if codebook_size else f" ({len(cc)} codes used)")
                     + f"; {uncoded} passage{'s' if uncoded != 1 else ''} carr{'y' if uncoded != 1 else 'ies'} none"
                     + (f"; proposed: {', '.join(proposed)}" if proposed else "") + ".")
        # which way each code points for the person, when the reading says (patch 0198): the codes that point at all,
        # most pointed first, with the readings inferred rather than said and those about other days than their passage's
        if "direction" in codes.columns:
            dirs = {}
            for c, d in zip(codes["code"].tolist(), codes["direction"].tolist()):
                d = _cell(d)
                if d in ("worse", "better", "neutral"):
                    dirs.setdefault(str(c), Counter())[d] += 1
            pointed = sorted(((c, k) for c, k in dirs.items() if k["worse"] or k["better"]), key=lambda x: -(x[1]["worse"] + x[1]["better"]))
            if pointed:
                inferred = sum(1 for b in codes["basis"].tolist() if _cell(b) == "inferred") if "basis" in codes.columns else 0
                # a passage on an activity of another day has that day as its own: its readings carry it (patch 0201), and
                # only a reading of other days than that counts here (2026-10-18: the line had counted 433, 52 of them so)
                acts = notes["activity_date"].tolist() if "activity_date" in notes.columns else [""] * len(notes)
                own = {str(i): _cell(a) or _cell(d) for i, a, d in zip(notes["id"].tolist(), acts, notes["date"].tolist())}
                other_days = (sum(1 for i, a in zip(codes["id"].tolist(), codes["about"].tolist()) if _cell(a) and _cell(a) != own.get(str(i), ""))
                              if "about" in codes.columns else 0)
                shown = ", ".join(f"{c} {k['worse']}/{k['better']}/{k['neutral']}" for c, k in pointed[:MAP_CODES_MAX])
                more = len(pointed) - MAP_CODES_MAX
                lines.append(f"  which way the codes point for the person (worse/better/neutral): {shown}" + (f", … ({more} more)" if more > 0 else "")
                             + f"; {inferred} reading{'s' if inferred != 1 else ''} inferred rather than said, {other_days} about other days than their passage's own.")
    elif codes is not None:
        lines.append("  codes: the coding pass produced none for this window.")
    # what is true of this data and nowhere else (the rules of citing, rendering, reading a code and the days apart are the
    # contract's Context section, once; 2026-10-14)
    lines.append("  A plan_note is dated the day it was planned for, not the day it was written.")
    return "\n".join(lines)


def where_of(row) -> str:
    """Where a passage is, for people and for the Reader: '2026-08-14 · activity_message · subject', the author's
    name when the row carries one, '(rendered from da)' when the text shown is an English rendering."""
    day = str(row.get("date") or "")[:10]
    kind = str(row.get("kind") or "")
    role = str(row.get("author_role") or "")
    name = str(row.get("author_name") or "").strip()
    who = role + (f" {name}" if name and role != "subject" else "")
    place = " · ".join(x for x in (day, kind, who) if x)
    aday = _cell(row.get("activity_date"))[:10]
    if aday and aday != day:
        place += f" · the activity of {aday}"
    lang = str(row.get("lang") or "").strip()
    if str(row.get("text_en") or "").strip() and lang and lang != "en":
        place += f" (rendered from {lang})"
    return place


def passage_text(row) -> str:
    """The text the analyst reads and the Reader quotes: the English rendering when the coding pass wrote one,
    else the passage as written."""
    en = str(row.get("text_en") or "").strip()
    return en if en else str(row.get("text") or "")


def passage_units(notes: pd.DataFrame) -> list:
    """The context table as units the READ machinery reads (bambooai/reading.py): id, text (the rendering or the
    original), kind 'paragraph', section = where it is, doc 'CTX', plus the row's date, kind and role."""
    units = []
    for _, row in notes.iterrows():
        r = row.to_dict()
        units.append({"id": str(r.get("id") or ""), "kind": "paragraph", "text": passage_text(r), "section": where_of(r), "doc": "CTX",
                      "file": "context", "date": str(r.get("date") or "")[:10], "pkind": str(r.get("kind") or ""), "role": str(r.get("author_role") or ""),
                      "original": str(r.get("text") or ""), "lang": str(r.get("lang") or "")})
    return units


_CTX_RANGE = r"(\d{4}-\d{2}-\d{2})\s*(?:\.\.|to|->|→|-)\s*(\d{4}-\d{2}-\d{2})"


def parse_context_scope(arg: str) -> Optional[dict]:
    """A READ argument that names the context, or None for a documents' read:
    'CTX what' -> {'all': True, 'query': 'what'}; 'CTX 2026-08-01..2026-08-31 what' -> {'range': (a, b), 'query'};
    'C.120-160 what' / 'C.417 what' -> {'ids': (120, 160), 'query'}."""
    import re
    a = (arg or "").strip()
    m = re.match(r"^C\.(\d+)(?:\s*-\s*(\d+))?\b[:\s-]*(.*)$", a, re.I | re.S)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2) or m.group(1))
        return {"ids": (min(lo, hi), max(lo, hi)), "query": m.group(3).strip()}
    m = re.match(r"^CTX\b[:\s-]*(.*)$", a, re.I | re.S)
    if not m:
        return None
    rest = m.group(1).strip()
    r = re.match(r"^" + _CTX_RANGE + r"\b[:\s-]*(.*)$", rest, re.S)
    if r:
        return {"range": (r.group(1), r.group(2)), "query": r.group(3).strip()}
    return {"all": True, "query": rest}


KERNEL_API_SOURCE = r'''
import re as _bamboo_ctx_re

class _BambooContext:
    """The words written beside the data, as an object in the kernel (docs/CONTEXT_DESIGN.md §5)."""
    def __init__(self, notes_path, codes_path):
        self.notes_path, self.codes_path = notes_path, codes_path
        self._notes = self._codes = None
    def __repr__(self):
        n = self.frame()
        return "CTX: %d passages%s%s" % (len(n), (" from %s to %s" % (n["date"].min(), n["date"].max())) if len(n) else "", (", codes in CTX.codes()" if self.codes_path else ""))
    def frame(self):
        """The context table: one row per passage (id, kind, date, time, end_date, activity_id, activity_date - the activity's own day - event_id, author_role, private, lang, text, text_en, copy_of - the passage whose words it repeats)."""
        import pandas as _pd
        if self._notes is None:
            self._notes = _pd.read_csv(self.notes_path, dtype=str, keep_default_na=False)
            if "date" in self._notes.columns:
                self._notes["day"] = _pd.to_datetime(self._notes["date"], errors="coerce")
            if "private" in self._notes.columns:
                self._notes["private"] = self._notes["private"].str.strip().str.lower().isin(["true", "1"])
        return self._notes
    def codes(self):
        """The codes table: one row per code on a passage (id, code, tone, quote, status, direction - worse, better or neutral for the person -, basis - said or inferred -, about - the days the reading describes, empty for the passage's own), empty before the coding pass."""
        import pandas as _pd
        if self._codes is None:
            self._codes = _pd.read_csv(self.codes_path, dtype=str, keep_default_na=False) if self.codes_path else _pd.DataFrame(columns=["id", "code", "tone", "quote", "status", "coder", "codebook_version", "direction", "basis", "about"])
        return self._codes
    def _shown(self, r):
        en = (r.get("text_en") or "").strip()
        return en if en else (r.get("text") or "")
    def _fmt(self, r):
        who = r.get("author_role") or ""
        if r.get("author_name") and who != "subject":
            who += " " + r["author_name"]
        head = " · ".join(x for x in ((r.get("date") or "")[:10], r.get("kind") or "", who) if x)
        aday = (r.get("activity_date") or "")[:10]
        if aday and aday != (r.get("date") or "")[:10]:
            head += " · the activity of %s" % aday
        tail = (" (rendered from %s)" % r["lang"]) if (r.get("text_en") or "").strip() and r.get("lang") and r.get("lang") != "en" else ""
        return "[%s] %s%s: %s" % (r.get("id"), head, tail, self._shown(r).replace("\n", " / "))
    def _lines(self, sub, as_frame, limit):
        if as_frame:
            return sub
        rows = [self._fmt(r) for r in sub.to_dict("records")[:limit]]
        more = len(sub) - limit
        return ("\n".join(rows) if rows else "(no passages)") + (("\n(%d more; raise limit or narrow)" % more) if more > 0 else "")
    def _filter(self, sub, kind=None, author=None):
        if kind:
            sub = sub[sub["kind"] == kind]
        if author:
            sub = sub[sub["author_role"] == author]
        return sub
    def grep(self, pattern, kind=None, author=None, original=False, as_frame=False, limit=40, flags=_bamboo_ctx_re.I):
        """The passages whose English rendering (or, with original=True, the text as written) matches the pattern."""
        n = self.frame()
        col = n["text"] if original else n.apply(self._shown, axis=1) if len(n) else n["text"]
        hit = n[col.str.contains(pattern, flags=flags, regex=True, na=False)] if len(n) else n
        return self._lines(self._filter(hit, kind, author), as_frame, limit)
    def around(self, date, days=3, kind=None, author=None, as_frame=False, limit=60):
        """The passages within `days` of a date (the words lead or lag the numbers: a window, not a day)."""
        import pandas as _pd
        n = self.frame()
        d = _pd.to_datetime(date)
        sub = n[(n["day"] >= d - _pd.Timedelta(days=days)) & (n["day"] <= d + _pd.Timedelta(days=days))] if len(n) else n
        return self._lines(self._filter(sub, kind, author), as_frame, limit)
    def between(self, a, b, kind=None, author=None, as_frame=False, limit=200):
        """The passages from day a to day b inclusive."""
        import pandas as _pd
        n = self.frame()
        sub = n[(n["day"] >= _pd.to_datetime(a)) & (n["day"] <= _pd.to_datetime(b))] if len(n) else n
        return self._lines(self._filter(sub, kind, author), as_frame, limit)
    def on(self, activity_id, as_frame=False, limit=60):
        """The passages of one activity: its messages, note, tags, tick, the plan it fulfilled."""
        n = self.frame()
        sub = n[n["activity_id"].astype(str) == str(activity_id)] if len(n) else n
        return self._lines(sub, as_frame, limit)
    def text(self, ref):
        """One passage whole, with its date, kind and author, the rendering and - when it differs - the original."""
        n = self.frame()
        key = str(ref) if str(ref).startswith("C.") else "C.%s" % ref
        sub = n[n["id"] == key]
        if not len(sub):
            return "(no passage %s)" % key
        r = sub.iloc[0].to_dict()
        out = self._fmt(r)
        if (r.get("text_en") or "").strip() and r.get("text_en") != r.get("text"):
            out += "\n  original: " + (r.get("text") or "").replace("\n", " / ")
        return out

CTX = _BambooContext(__NOTES__, __CODES__)
'''


def kernel_api_source(notes_path: str, codes_path: str = "") -> str:
    """The source that defines CTX in the kernel for the loaded context; '' without a context file. Run by the host
    at kernel start and after a rollback, prefixed to the replay script; never a cell of the record."""
    if not notes_path:
        return ""
    return KERNEL_API_SOURCE.replace("__NOTES__", repr(str(notes_path))).replace("__CODES__", repr(str(codes_path or "")))


def aux_head_for_text_file(path: str, columns: list, rows: int) -> str:
    """The DATA block's entry for the context and codes files: the path, the columns and the row count, never the
    rows themselves (their cells are text; the map says what is there)."""
    return f"Path: {path}\nColumns: {', '.join(columns)}\nRows: {rows} (the rows are passages: read them with CTX, not from this head)"
