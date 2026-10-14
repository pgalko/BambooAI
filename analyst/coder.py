"""The coder (docs/CONTEXT_DESIGN.md §6): at load, every passage of the context is read once by a model on the
Coder seat - the codes from the codebook that apply, a tone, for each code the words it rests on (verbatim, as
written), the language, and an English rendering of every passage not written in English. Pure: the batches, the
messages, the parse of the reply, the mechanical validation. The template here is read by a model (the C5
scanner covers this file); the codebook and the passages ride as data."""
from __future__ import annotations

import json
import re
from collections import Counter
from typing import Dict, List, Tuple

BATCH_PASSAGES = 40            # one call reads about forty passages (§4 F1)
BATCH_CHARS = 12000            # or fewer, when they are long: the reply carries a rendering of each
TONES = ("positive", "negative", "neutral", "mixed")
MIN_QUOTE_CHARS = 2

CODER_SYSTEM = (
    "You are the Coder. You are given a vocabulary of codes, each with a one-line definition, and numbered passages: "
    "dated notes and messages written beside a set of records by the person the records are about and by those who "
    "work with them. For each passage, return the codes from the vocabulary that apply, the passage's tone, and for "
    "each code the words it rests on, quoted exactly from the passage as written. A passage may take no code. If a "
    "passage needs a code the vocabulary lacks, propose one - a short English name in snake_case and a one-line "
    "English definition - once in the reply, and use it. Every passage not written in English gets a faithful, "
    "complete English rendering in text_en; an English passage gets none.\n\n"
    "Reply with one JSON object per line, one line per passage, in the passages' order, and nothing else:\n"
    '{"id": "C.12", "codes": ["fatigue", "sleep"], "tone": "negative", "quotes": {"fatigue": "...", "sleep": "..."}, '
    '"lang": "da", "text_en": "...", "propose": [{"code": "...", "definition": "..."}]}\n'
    "- codes: names from the vocabulary, or proposed in this reply; [] when none applies\n"
    "- tone: one of positive, negative, neutral, mixed\n"
    "- quotes: for every code, a contiguous stretch of the passage as written - the original words, never the rendering\n"
    "- lang: the passage's language as a two-letter code\n"
    "- text_en: the English rendering when lang is not en; leave it out for English\n"
    "- propose: only when a passage needs a code the vocabulary lacks; leave it out otherwise\n"
    "Codes, definitions, proposals and renderings are in English."
)


def _norm(s: str) -> str:
    s = (s or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip()


def batches(passages: List[dict], max_n: int = None, max_chars: int = None) -> List[List[dict]]:
    """The passages in the order given, cut into batches of at most max_n passages or max_chars of text (the
    module's constants when not given, read at the call so a test can lower them)."""
    max_n = max_n or BATCH_PASSAGES
    max_chars = max_chars or BATCH_CHARS
    out, cur, chars = [], [], 0
    for p in passages:
        n = len(str(p.get("text") or ""))
        if cur and (len(cur) >= max_n or chars + n > max_chars):
            out.append(cur)
            cur, chars = [], 0
        cur.append(p)
        chars += n
    if cur:
        out.append(cur)
    return out


def coder_messages(vocabulary: str, passages: List[dict]) -> Tuple[str, str]:
    """The system text and the user text of one call: the vocabulary, then each passage under its id with its day,
    kind and author."""
    lines = ["VOCABULARY (code: definition):", vocabulary.strip() or "(none)", "", f"PASSAGES ({len(passages)}; id, day, kind, author):"]
    for p in passages:
        who = str(p.get("author_role") or "")
        name = str(p.get("author_name") or "").strip()
        if name and who != "subject":
            who += f" {name}"
        head = " · ".join(x for x in (str(p.get("date") or "")[:10], str(p.get("kind") or ""), who) if x)
        lines.append(f"[{p.get('id')}] {head}")
        lines.append(str(p.get("text") or "").strip())
        lines.append("")
    return CODER_SYSTEM, "\n".join(lines).rstrip() + "\n"


def parse_reply(text: str) -> Tuple[List[dict], bool]:
    """The reply as items with an id: JSON lines, or one JSON array, fences stripped. Returns (items, cut_off) -
    cut_off when the last non-empty line is not JSON (a reply cut at the seat's token limit)."""
    body = (text or "").strip()
    body = re.sub(r"^```(?:json)?\s*|\s*```$", "", body, flags=re.I | re.M).strip()
    items: List[dict] = []
    if not body:
        return items, False
    try:
        whole = json.loads(body)
        if isinstance(whole, list):
            return [x for x in whole if isinstance(x, dict) and x.get("id")], False
        if isinstance(whole, dict) and whole.get("id"):
            return [whole], False
    except ValueError:
        pass
    cut_off = False
    lines = [ln for ln in body.splitlines() if ln.strip()]
    for i, ln in enumerate(lines):
        s = ln.strip().rstrip(",")
        try:
            x = json.loads(s)
        except ValueError:
            if i == len(lines) - 1:
                cut_off = True
            continue
        if isinstance(x, dict) and x.get("id"):
            items.append(x)
    return items, cut_off


def _lang(value) -> str:
    s = str(value or "").strip().lower()
    return s if re.fullmatch(r"[a-z]{2}", s) else ""


def validate(items: List[dict], passages: List[dict], book_codes: set, proposed_codes: set = frozenset()) -> dict:
    """Mechanical checks of a reply against the passages it read (§6): every code in the book or proposed with a
    definition in this reply; every quote verbatim in the passage as written (whitespace normalised); one tone of
    four; a rendering for every passage not in English, its length within a factor of the original's. Returns
    {rows, renderings, proposals, dropped, seen} - rows for the codes table (id, code, tone, quote, status),
    renderings {id: {lang, text_en}}, proposals [{code, definition, example}], dropped a Counter of what was
    refused, seen the ids the reply answered."""
    from analyst.codebook import normalise_code
    by_id = {str(p.get("id")): p for p in passages}
    rows: List[dict] = []
    renderings: Dict[str, dict] = {}
    proposals: List[dict] = []
    dropped: Counter = Counter()
    seen: set = set()
    proposed_now: set = set()
    for item in items:
        uid = str(item.get("id") or "")
        p = by_id.get(uid)
        if p is None:
            dropped["unknown_id"] += 1
            continue
        if uid in seen:
            dropped["duplicate"] += 1
            continue
        seen.add(uid)
        original = str(p.get("text") or "")
        # proposals first: a code proposed here may be used in this reply
        for pr in item.get("propose") or []:
            if not isinstance(pr, dict):
                continue
            code = normalise_code(pr.get("code"))
            definition = str(pr.get("definition") or "").strip()
            if not code or not definition:
                dropped["proposal_without_definition"] += 1
                continue
            if code in book_codes or code in proposed_codes or code in proposed_now:
                continue
            proposed_now.add(code)
            proposals.append({"code": code, "definition": definition, "example": f"{uid}: {_norm(original)[:120]}"})
        tone = str(item.get("tone") or "").strip().lower()
        if tone not in TONES:
            dropped["tone"] += 1
            tone = "neutral"
        lang = _lang(item.get("lang"))
        text_en = _norm(str(item.get("text_en") or ""))
        if not lang:
            lang = "en" if not text_en else ""
        if lang == "en":
            text_en = ""                      # an English passage is its own rendering
        elif not text_en:
            dropped["rendering_missing"] += 1
        else:
            L = len(_norm(original))
            if not (0.25 * L - 10 <= len(text_en) <= 4 * L + 40):
                dropped["rendering_length"] += 1
                text_en = ""
        renderings[uid] = {"lang": lang, "text_en": text_en}
        quotes = item.get("quotes") if isinstance(item.get("quotes"), dict) else {}
        norm_original = _norm(original)
        for raw in item.get("codes") or []:
            code = normalise_code(raw)
            if not code:
                continue
            if code not in book_codes and code not in proposed_codes and code not in proposed_now:
                dropped["unknown_code"] += 1
                continue
            q = _norm(str(quotes.get(raw) or quotes.get(code) or "")).strip('"')
            if len(q) < MIN_QUOTE_CHARS or q not in norm_original:
                dropped["quote"] += 1
                continue
            if any(r["id"] == uid and r["code"] == code for r in rows):
                continue
            status = "proposed" if (code in proposed_now or code in proposed_codes) else "codebook"
            rows.append({"id": uid, "code": code, "tone": tone, "quote": q, "status": status})
    return {"rows": rows, "renderings": renderings, "proposals": proposals, "dropped": dropped, "seen": seen}


def report_line(report: dict) -> str:
    """The sentence of a coding pass for people: the dialog's line and the HANDOVER's record."""
    n = int(report.get("passages") or 0)
    if not n:
        return "nothing to code"
    parts = [f"{report.get('coded', 0)} of {n} coded"]
    if report.get("rendered"):
        parts.append(f"{report['rendered']} rendered into English")
    if report.get("proposed"):
        parts.append(f"{report['proposed']} code{'s' if report['proposed'] != 1 else ''} proposed")
    unanswered = int(report.get("unanswered") or 0)
    if unanswered:
        parts.append(f"{unanswered} not read by the coder")
    if report.get("failed_batches"):
        parts.append(f"{report['failed_batches']} batch{'es' if report['failed_batches'] != 1 else ''} failed")
    return ", ".join(parts)
