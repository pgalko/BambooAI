"""The context (docs/CONTEXT_DESIGN.md): the words written beside the data, as the app reads them - the context
table and the codes table as frames, and the map the analyst sees in DATA (§3.4): the span, passages per kind and
month, authors by role, languages, the codes with their counts. Never the text; that is reached by CTX and READ.
Pure: frames in, text out. The strings here are read by a model (the C5 scanner covers this file)."""
from __future__ import annotations

import io
from collections import Counter
from typing import Optional

import pandas as pd

CONTEXT_COLUMNS = ["id", "kind", "date", "time", "end_date", "activity_id", "event_id", "source_id", "author_id",
                   "author_name", "author_role", "private", "lang", "text", "text_en", "chars"]
CODES_COLUMNS = ["id", "code", "tone", "quote", "status", "coder", "codebook_version"]
MAP_KINDS_MAX = 12
MAP_CODES_MAX = 12


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
        if kind in ("activity_message", "activity_private_note", "day_note", "plan_note") and len(rs) > 1:
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
    if codes is not None and len(codes) > 0:
        cc = Counter(str(c) for c in codes["code"].tolist() if str(c).strip())
        coded = set(str(i) for i in codes["id"].tolist())
        uncoded = sum(1 for i in notes["id"].tolist() if str(i) not in coded)
        proposed = sorted({str(c) for c, s in zip(codes["code"].tolist(), codes["status"].tolist()) if str(s) == "proposed"})
        lines.append(f"  codes (the model's reading, one row per code, with the words it rests on): {_count_line(cc, MAP_CODES_MAX)}"
                     + (f" ({len(cc)} of {codebook_size} codes used)" if codebook_size else f" ({len(cc)} codes used)")
                     + f"; {uncoded} passage{'s' if uncoded != 1 else ''} carr{'y' if uncoded != 1 else 'ies'} none"
                     + (f"; proposed: {', '.join(proposed)}" if proposed else "") + ".")
    elif codes is not None:
        lines.append("  codes: the coding pass produced none for this window.")
    lines.append("  A passage is cited as [C.n]; one not written in English is quoted in its English rendering, marked so, the original kept beside it;"
                 " a code is a reading of a passage, not a statement the writer made; the day of the words and the day of the numbers can differ by days.")
    return "\n".join(lines)


def aux_head_for_text_file(path: str, columns: list, rows: int) -> str:
    """The DATA block's entry for the context and codes files: the path, the columns and the row count, never the
    rows themselves (their cells are text; the map says what is there)."""
    return f"Path: {path}\nColumns: {', '.join(columns)}\nRows: {rows} (the rows are passages: read them with CTX, not from this head)"
