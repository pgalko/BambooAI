"""Reading the thread's documents for the analyst (docs/DOCUMENTS_DESIGN.md).

A READ names a scope (one document or ALL) and what the analyst is looking for. The platform selects
candidate units - BM25 over the units' text, each candidate with its neighbours for context - and hands them to the Reader seat
with the question. The Reader answers with passages quoted exactly, each under its unit id, then a
summary. Every passage is checked against the unit's text: one that is not verbatim is dropped and the
digest says how many were. The digest has the search digest's shape and is what the analyst reads,
what SHOW READ k reopens, and what the page's chips show on hover. Nothing here calls a model or
touches the network: the caller passes `call_reader`.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from bambooai import documents as docs

TOP_K = 24                     # candidates before neighbours
CANDIDATE_CHARS = 2400         # a unit's text as shown to the Reader - a safety net: units are at most 1,500 characters since parsing splits long paragraphs (documents.MAX_UNIT_CHARS)
MIN_QUOTE_CHARS = 8
MAX_PASSAGES = 12              # kept passages per read; the Reader is asked for ten at most
MIN_CANDIDATE_WORDS = 4        # a unit shorter than this (a page number, a running head) is not a candidate
READ_TOKENS = 6000             # the text one Reader call reads; a stretch longer than this is read up to here, and the digest says so
CHARS_PER_TOKEN = 4

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")
_PASSAGE_RE = re.compile(r"^\s*[-*]?\s*\[(D\d+\.\d+)\]\s*(?:\([^)]*\)\s*)?[\"“]?(.*?)[\"”]?\s*$")
_UNIT_ID_RE = re.compile(r"\[(D\d+\.\d+)\]")

READER_SYSTEM = (
    "You are the Reader. You are given a question and numbered passages from documents a person "
    "attached to an analysis. Your job is to return the parts that answer the question, quoted exactly as "
    "written - not paraphrased, not shortened inside, not corrected, spelling and spacing as they are - "
    "each on its own line in this form, with the passage's own id:\n"
    "- [D1.17] \"an exact contiguous excerpt of the passage\"\n"
    "Quote the sentence or two that answers, about sixty words at most; the whole passage only when it is "
    "that short. An excerpt must be a contiguous run of the passage's words. Give at most ten lines, the "
    "most relevant first, one or two per passage. After them write SUMMARY: and one or two plain sentences "
    "on what they establish, with the ids in brackets. If nothing answers, write NOTHING ANSWERS and one "
    "sentence on what the passages are about instead. No other text."
)


# ----------------------------------------------------------------------------- tokens and ranking

def tokens(text: str) -> List[str]:
    return _TOKEN_RE.findall((text or "").lower())


class BM25:
    """Okapi BM25 over a list of token lists (k1 = 1.5, b = 0.75)."""

    def __init__(self, docs_tokens: List[List[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = docs_tokens
        self.n = len(docs_tokens)
        self.avgdl = (sum(len(d) for d in docs_tokens) / self.n) if self.n else 0.0
        self.tf = [Counter(d) for d in docs_tokens]
        df: Counter = Counter()
        for d in docs_tokens:
            df.update(set(d))
        self.idf = {t: math.log(1 + (self.n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query_tokens: Iterable[str]) -> List[float]:
        out = []
        q = list(query_tokens)
        for i, d in enumerate(self.docs):
            s = 0.0
            dl = len(d) or 1
            for t in q:
                f = self.tf[i].get(t, 0)
                if not f:
                    continue
                s += self.idf.get(t, 0.0) * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * dl / (self.avgdl or 1)))
            out.append(s)
        return out




def unit_text(u: dict) -> str:
    if u.get("kind") == "table":
        return docs.unit_rank_text(u)
    return u.get("text") or ""


def substantive(u: dict) -> bool:
    """A unit worth reading: not a heading (its paragraph carries the claims), and at least a few words that
    are not numbers - page numbers, running heads and arXiv stamps are units too, but never answers."""
    if u.get("kind") == "heading":
        return False
    words = [w for w in tokens(unit_text(u)) if not w.isdigit()]
    return len(words) >= MIN_CANDIDATE_WORDS


def select(units: List[dict], query: str, top_k: int = TOP_K) -> List[dict]:
    """Candidate units for the Reader: the top_k by BM25 over the units' text, with their neighbours (the unit
    before and after, same document) in document order. Headings and the units too short to answer (page
    numbers) are neither ranked nor neighbours."""
    units = [u for u in units if substantive(u)]
    if not units:
        return []
    texts = [unit_text(u) for u in units]
    bm = BM25([tokens(t) for t in texts])
    lex = bm.scores(tokens(query))
    ranked = [i for i, sc in sorted(enumerate(lex), key=lambda p: -p[1]) if sc > 0]
    if not ranked:                                          # nothing matched a word: the first units
        ranked = list(range(min(top_k, len(units))))
    chosen = set(ranked[:top_k])
    for idx in list(chosen):
        u = units[idx]
        for j in (idx - 1, idx + 1):
            if 0 <= j < len(units) and units[j].get("doc") == u.get("doc"):
                chosen.add(j)
    return [units[i] for i in sorted(chosen)]


# ----------------------------------------------------------------------------- the Reader's turn

def where(u: dict) -> str:
    """Where a unit is, for people: 'paper.pdf p.4' or 'meeting.md §Agenda > Q3 pipeline'."""
    place = f"p.{u['page']}" if u.get("page") else (f"§{u['section']}" if u.get("section") else "")
    return (f"{u.get('file', '')} {place}").strip()


def reader_messages(question: str, candidates: List[dict], scope_label: str) -> Tuple[str, str]:
    lines = [f"QUESTION: {question.strip()}", f"SCOPE: {scope_label}", "", "PASSAGES:"]
    for u in candidates:
        text = unit_text(u)
        if len(text) > CANDIDATE_CHARS:
            text = text[:CANDIDATE_CHARS].rstrip() + " [...]"
        lines.append(f"[{u['id']}] ({where(u)}) {text}")
    return READER_SYSTEM, "\n".join(lines)


def parse_reader(text: str) -> Tuple[List[Tuple[str, str]], str, bool, bool]:
    """(passages as (unit id, quote), summary, nothing_answers, cut_off) from the Reader's reply. A reply
    with passages but no SUMMARY whose last line has no closing quote was cut off by the model's output cap
    (seen 2026-10-03: whole paragraphs quoted twenty times over)."""
    passages: List[Tuple[str, str]] = []
    summary_lines: List[str] = []
    nothing = False
    in_summary = False
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.upper().startswith("SUMMARY:"):
            in_summary = True
            rest = line[len("SUMMARY:"):].strip()
            if rest:
                summary_lines.append(rest)
            continue
        if line.upper().startswith("NOTHING ANSWERS"):
            nothing = True
            in_summary = True
            rest = re.sub(r"(?i)^nothing answers[.:\s-]*", "", line).strip()
            if rest:
                summary_lines.append(rest)
            continue
        if in_summary:
            summary_lines.append(line)
            continue
        m = _PASSAGE_RE.match(line)
        if m and m.group(2).strip():
            passages.append((m.group(1), m.group(2).strip()))
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    cut_off = bool(passages) and not in_summary and not nothing and bool(lines) and not lines[-1].endswith(('"', "\u201d"))
    if cut_off and _PASSAGE_RE.match(lines[-1]):
        passages.pop()                                      # the unfinished excerpt on the cut line is not kept
    return passages, " ".join(summary_lines).strip(), nothing, cut_off


def _norm(s: str) -> str:
    s = (s or "").replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", " ", s).strip()


def verify(passages: List[Tuple[str, str]], units_by_id: Dict[str, dict]) -> Tuple[List[Tuple[str, str]], int]:
    """Keep a passage only if its quote is a contiguous, verbatim part of the unit's text (whitespace
    normalised); returns (kept, dropped)."""
    kept, dropped = [], 0
    seen = set()
    for uid, quote in passages:
        u = units_by_id.get(uid)
        q = _norm(quote).strip('"\u201c\u201d')
        if u is None or len(q) < MIN_QUOTE_CHARS or q not in _norm(unit_text(u)) or (uid, q) in seen:
            dropped += 1
            continue
        seen.add((uid, q))
        kept.append((uid, q))
    return kept[:MAX_PASSAGES], dropped


def compose_digest(kept: List[Tuple[str, str]], dropped: int, summary: str, nothing: bool, units_by_id: Dict[str, dict],
                   cut_off: bool = False, scope_note: str = "", footer: str = "") -> str:
    parts: List[str] = []
    if kept:
        parts.append("PASSAGES (verbatim, each with its locator):")
        for uid, q in kept:
            parts.append(f"- [{uid}] ({where(units_by_id[uid])}) \"{q}\"")
    elif nothing:
        parts.append("PASSAGES: none - nothing in the candidates answers the question.")
    elif dropped:
        parts.append("PASSAGES: none - the reader's quotes could not be verified against the documents.")
    else:
        parts.append("PASSAGES: none - the reader quoted nothing.")
    notes = []
    if scope_note:
        notes.append(scope_note)
    if cut_off:
        notes.append("the reader's reply was cut off by its output cap; the passages after the cut were lost")
    if dropped:
        notes.append(f"{dropped} passage{'s' if dropped != 1 else ''} the reader quoted {'were' if dropped != 1 else 'was'} not verbatim and {'were' if dropped != 1 else 'was'} dropped")
    if notes:
        parts.append("(" + "; ".join(notes) + ")")
    parts.append("SUMMARY:")
    parts.append(summary.strip() or ("Nothing in the documents answers this." if nothing else "(the reader gave no summary)"))
    if footer:
        parts.append(footer)
    return "\n".join(parts)


def digest_footer(kept: List[Tuple[str, str]], scope: str) -> str:
    """The paths from here: the stretch around the first passage, and the kernel object for a grep in a cell."""
    if kept:
        uid = kept[0][0]
        doc, n = uid.split(".")
        n = int(n)
        return (f"(For a stretch whole: READ {doc}.{max(1, n - 2)}-{n + 2} <what you want>; to find where something is: "
                f"print({doc}.grep('...', context=1)) in a cell.)")
    if scope != "ALL" and parse_stretch(scope) is None:
        return f"(To find where something is: print({scope}.grep('...', context=1)) in a cell; for a stretch whole: READ {scope}.35-41 <what you want>.)"
    return ""


def digest_peek(digest: str) -> str:
    """One line for the pane's row: the summary when there is one, else the first passage, else the first line."""
    text = digest or ""
    if "SUMMARY:" in text:
        after = text.split("SUMMARY:", 1)[1].strip()
        if after:
            return after.splitlines()[0].strip()
    for line in text.splitlines():
        if line.startswith("- ["):
            return line.strip()
    return next((ln.strip() for ln in text.splitlines() if ln.strip()), "")


def parse_digest(digest: str) -> List[dict]:
    """The passages back out of a digest, for the pane's row and the chips: [{id, where, quote}]."""
    out = []
    for line in (digest or "").splitlines():
        m = re.match(r"^- \[(D\d+\.\d+)\] \((.*?)\) \"(.*)\"\s*$", line)
        if m:
            out.append({"id": m.group(1), "where": m.group(2), "quote": m.group(3)})
    return out


def parse_scope(arg: str) -> Tuple[str, str]:
    """'D2 the sample size' -> ('D2', 'the sample size'); 'ALL every mention' -> ('ALL', ...); a bare
    question -> ('ALL', question). The stretch forms of D58 - 'D1.35-41 ...', 'D1.36 ...', 'D1 p.7-9 ...',
    'D1 p.7 ...' - come back as the scope text ('D1.35-41', 'D1 p.7-9') for parse_stretch to read."""
    arg = (arg or "").strip()
    m = re.match(r"^(D\d+)\s+(p\.\s*\d+(?:\s*-\s*\d+)?)\b[:\s-]*(.*)$", arg, re.I | re.S)
    if m:
        return f"{m.group(1).upper()} {m.group(2).replace(' ', '')}", m.group(3).strip()
    m = re.match(r"^(D\d+\.\d+(?:\s*-\s*\d+)?)\b[:\s-]*(.*)$", arg, re.I | re.S)
    if m:
        return m.group(1).upper().replace(" ", ""), m.group(2).strip()
    m = re.match(r"^(D\d+|ALL)\b[:\s-]*(.*)$", arg, re.I | re.S)
    if m:
        return m.group(1).upper(), m.group(2).strip()
    return "ALL", arg


def parse_stretch(scope: str) -> Optional[dict]:
    """A stretch scope as data: {'doc': 'D1', 'units': (35, 41)} or {'doc': 'D1', 'pages': (7, 9)}; None for a
    whole-document or ALL scope."""
    m = re.match(r"^(D\d+)\.(\d+)(?:-(\d+))?$", scope or "")
    if m:
        a, b = int(m.group(2)), int(m.group(3) or m.group(2))
        return {"doc": m.group(1), "units": (min(a, b), max(a, b))}
    m = re.match(r"^(D\d+) p\.(\d+)(?:-(\d+))?$", scope or "")
    if m:
        a, b = int(m.group(2)), int(m.group(3) or m.group(2))
        return {"doc": m.group(1), "pages": (min(a, b), max(a, b))}
    return None


def stretch_units(units: List[dict], stretch: dict) -> List[dict]:
    """The units of a stretch, whole and in order."""
    def num(u):
        return int(str(u["id"]).split(".")[-1])
    if "units" in stretch:
        a, b = stretch["units"]
        return [u for u in units if a <= num(u) <= b]
    a, b = stretch["pages"]
    return [u for u in units if u.get("page") and a <= int(u["page"]) <= b]



def span(units: List[dict]) -> str:
    """'D1.35-41' or 'D1.36', with the pages when the units have them."""
    if not units:
        return ""
    a, b = units[0]["id"], units[-1]["id"]
    ids = a if a == b else f"{a}-{b.split('.')[-1]}"
    pages = [u["page"] for u in units if u.get("page")]
    return ids + (f" (p.{pages[0]}" + (f"-{pages[-1]}" if pages[-1] != pages[0] else "") + ")" if pages else "")


# ----------------------------------------------------------------------------- read

def read(tdir: str, arg: str, call_reader: Callable[[str, str], str], top_k: int = TOP_K,
         read_tokens: int = READ_TOKENS) -> Tuple[str, List[dict]]:
    """One READ: one call to the Reader seat (`call_reader(system, user)`), over the BM25 candidates for the
    question in the named document (or all of them), or over exactly the stretch the analyst named - up to
    read_tokens of it, the digest saying where to continue. Returns (digest, passages)."""
    scope, query = parse_scope(arg)
    stretch = parse_stretch(scope)
    manifest = docs.load_manifest(tdir)
    entries = manifest.get("documents") or []
    if not entries:
        return "(no documents are attached to this thread; attach one from the paperclip menu, then READ)", []
    if scope != "ALL":
        doc_id = stretch["doc"] if stretch else scope
        entries = [d for d in entries if d["id"] == doc_id]
        if not entries:
            have = ", ".join(d["id"] for d in manifest.get("documents") or []) or "none"
            return f"(no document {doc_id} in this thread; attached: {have})", []
    if not query and not stretch:
        return "(READ needs what you are looking for: READ D1 <question>, READ D1.35-41 <question>, or READ ALL <question>)", []
    units: List[dict] = []
    for d in entries:
        data = docs.read_units(tdir, d["id"])
        units += [dict(u, doc=d["id"], file=d["file"]) for u in data["units"]]
    units_by_id = {u["id"]: u for u in units}
    scope_note = ""
    if stretch:
        # the analyst chose the stretch: the Reader reads exactly it, no ranking - up to one call's worth
        chosen = stretch_units(units, stretch)
        if not chosen:
            return f"(nothing in {scope}: {entries[0]['id']} has {len(units)} units)", []
        budget, kept_units = read_tokens * CHARS_PER_TOKEN, []
        for u in chosen:
            budget -= len(unit_text(u))
            if budget < 0 and kept_units:
                break
            kept_units.append(u)
        if len(kept_units) < len(chosen):
            scope_note = f"the stretch is longer than one READ reads: {span(chosen[len(kept_units):])} not reached; READ it next"
        question = query or "What do these passages say? Quote the parts that carry the claims, figures and definitions."
        candidates, label = kept_units, f"{scope} ({len(kept_units)} units, read whole)"
    else:
        question = query
        candidates = select(units, query, top_k=top_k)
        label = scope if scope != "ALL" else f"all documents ({', '.join(d['id'] for d in entries)})"
    system, user = reader_messages(question, candidates, label)
    reply = call_reader(system, user) or ""
    passages, summary, nothing, cut_off = parse_reader(reply)
    kept, dropped = verify(passages, units_by_id)
    digest = compose_digest(kept, dropped, summary, nothing, units_by_id, cut_off, scope_note=scope_note,
                            footer=digest_footer(kept, scope))
    return digest, parse_digest(digest)
