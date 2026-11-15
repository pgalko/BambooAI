"""The brief: what the person agreed before a run, as the analyst receives it (docs/ARCHITECT_DESIGN.md §2.2, §2.5).

A brief is a plain dict, kept with its run. Every part is optional: one left empty is left to the analyst, and the
prompt says so.

    {"version": 2,
     "question": "...",          the person's words (the run's question)
     "decision": "...",          what they will do differently depending on the answer
     "thinks": "...",            what they think is going on
     "rests_on": [{"text": "...", "source": "person", "mark": "", "note": ""}],     what the frame rests on
     "expects": "...",           what they expect to see
     "would_change": "...",      what would change their mind
     "also_check": [{"text": "...", "shows": "..."}],                               other explanations, and what each would show
     "fixed": {"comparison": "...", "measure": "...", "period": "..."},             fixed before the run
     "saved": [{"when": "...", "question": "...", "passage": "...", "data": "...", "period": "..."}],
     "set_aside": ["..."]}       considered and dropped

A line's source is who it comes from (SOURCES); its mark is what a check against the data found (MARKS), or '' when
nothing checked it. normalise() brings what a caller sends into this shape, render() writes the BRIEF block of the
prompt, and outcome() reads back what a report says against the brief.
"""
from __future__ import annotations

import re
from typing import Optional

SOURCES = ("person", "architect", "data", "saved", "result")      # who a line comes from; an earlier result is a claim, not a fact
MARKS = ("holds", "does not hold", "cannot be checked")
FIXED = ("comparison", "measure", "period")
SAVED = ("when", "question", "passage", "data", "period", "thread", "run")
TEXT_CHARS = 600                 # one line of a brief, at most
MAX = {"rests_on": 6, "also_check": 4, "saved": 6, "set_aside": 8}      # bounds on what a prompt carries, not the design's counts
LEFT = "left to you"             # a part of what is fixed that the person did not fix: the analyst chooses it
UNSAID = "not said"              # a part of the frame the person did not state
ALWAYS = ("chance", "measurement error", "how the cases compared came to be chosen")      # checked in every briefed run
VERDICTS = ("not met", "cannot tell", "met")                     # read in this order: "not met" holds "met"
SEEN = ("not seen", "cannot tell", "seen")


def _text(value) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()[:TEXT_CHARS] if isinstance(value, (str, int, float)) and not isinstance(value, bool) else ""


def normalise(brief) -> dict:
    """The brief in its known shape: the parts with content, text on one line and bounded, a line given as a bare
    string made a line of the person's. {} when nothing in it frames the question."""
    if not isinstance(brief, dict):
        return {}
    out = {}
    for key in ("decision", "thinks", "expects", "would_change"):
        if _text(brief.get(key)):
            out[key] = _text(brief.get(key))
    anchors = []
    for a in brief.get("rests_on") if isinstance(brief.get("rests_on"), list) else []:
        a = a if isinstance(a, dict) else {"text": a}
        if _text(a.get("text")):
            line = {"text": _text(a.get("text")), "source": a.get("source") if a.get("source") in SOURCES else "person",
                    "mark": a.get("mark") if a.get("mark") in MARKS else ""}
            if _text(a.get("note")):
                line["note"] = _text(a.get("note"))
            anchors.append(line)
    rivals = []
    for r in brief.get("also_check") if isinstance(brief.get("also_check"), list) else []:
        r = r if isinstance(r, dict) else {"text": r}
        if _text(r.get("text")):
            rivals.append({"text": _text(r.get("text")), **({"shows": _text(r.get("shows"))} if _text(r.get("shows")) else {})})
    fixed = {k: _text(v) for k, v in (brief.get("fixed") if isinstance(brief.get("fixed"), dict) else {}).items() if k in FIXED and _text(v)}
    saved = []
    for s in brief.get("saved") if isinstance(brief.get("saved"), list) else []:
        s = {k: _text(v) for k, v in s.items() if k in SAVED and _text(v)} if isinstance(s, dict) else {}
        if s.get("passage") or s.get("question"):
            saved.append(s)
    aside = [_text(x) for x in (brief.get("set_aside") if isinstance(brief.get("set_aside"), list) else []) if _text(x)]
    for key, value in (("rests_on", anchors), ("also_check", rivals), ("fixed", fixed), ("saved", saved), ("set_aside", aside)):
        if value:
            out[key] = value[:MAX[key]] if key in MAX else value
    if not out:
        return {}
    version = brief.get("version")
    out["version"] = int(version) if isinstance(version, int) and not isinstance(version, bool) and version > 0 else 1
    if _text(brief.get("question")):
        out["question"] = _text(brief.get("question"))
    return out


def carried(parent) -> dict:
    """The brief a run takes over from the run it answers: the analyst asked, the person replied, and what was
    agreed still stands. {} when the parent did not end on a question or had no brief."""
    if parent is None or getattr(parent, "status", "") != "asked" or not getattr(parent, "brief", None):
        return {}
    return {**{k: v for k, v in parent.brief.items() if k != "carried_from"}, "carried_from": parent.id}


def _standing(anchor: dict) -> str:
    """What a line the frame rests on is worth, as the analyst reads it."""
    note = f" - {anchor['note']}" if anchor.get("note") else ""
    if anchor.get("mark") == "cannot be checked":
        return "cannot be checked" + note
    if anchor.get("mark"):
        return f"checked against the data: {anchor['mark']}{note}"
    if anchor.get("source") in ("saved", "result"):
        return "from an earlier result: a claim to test" + note
    return "the person's word, not checked" + note


def render(brief: dict) -> str:
    """The BRIEF block of the analyst's prompt: every part on its line; an empty part of the frame is not said, an
    empty part of what is fixed is left to the analyst."""
    if not brief:
        return ""
    head = ("BRIEF (agreed before your question; the QUESTION above is the person's answer, and it stands where the two differ):"
            if brief.get("carried_from") else "BRIEF (agreed with the person before this run):")
    lines = [head, f"Decision: {brief.get('decision') or UNSAID}", f"What the person thinks: {brief.get('thinks') or UNSAID}"]
    lines.append("What it rests on:" + ("" if brief.get("rests_on") else f" {UNSAID}"))
    lines += [f"- {a['text']} [{_standing(a)}]" for a in brief.get("rests_on", [])]
    lines.append(f"What they expect to see: {brief.get('expects') or UNSAID}")
    lines.append(f"What would change their mind: {brief.get('would_change') or UNSAID}")
    lines.append("Also check:")
    lines += [f"- {r['text']}" + (f": it would show {r['shows']}" if r.get("shows") else "") for r in brief.get("also_check", [])]
    lines += [f"- {x} [always]" for x in ALWAYS]
    fixed = brief.get("fixed", {})
    lines.append("Fixed before the run:")
    lines += [f"- {k}: {fixed.get(k) or LEFT}" for k in FIXED]
    if brief.get("saved"):
        lines.append("Saved analyses the person chose (earlier results: claims to test, not evidence):")
        for s in brief["saved"]:
            where = ", ".join(x for x in (s.get("data"), s.get("period")) if x)
            lines.append("- " + " ".join(x for x in (s.get("when"), f"\"{s['question']}\"" if s.get("question") else "") if x)
                         + (f": \"{s['passage']}\"" if s.get("passage") else "") + (f" ({where})" if where else ""))
    if brief.get("set_aside"):
        lines.append("Set aside (considered and dropped): " + "; ".join(brief["set_aside"]))
    return "\n".join(lines)


def _section(report: str, name: str) -> Optional[str]:
    """The text under a heading of the report, up to the next heading; None when the report has no such heading."""
    m = re.search(rf"(?im)^#{{1,6}}[ \t]*{re.escape(name)}[ \t]*:?[ \t]*$", report or "")
    if not m:
        return None
    rest = report[m.end():]
    end = re.search(r"(?m)^(#{1,6}[ \t]+\S|> CHECK:)", rest)
    return rest[:end.start()] if end else rest


def _items(section: str) -> list:
    """The lines of a part, each without its list mark or emphasis."""
    out = []
    for line in (section or "").splitlines():
        line = re.sub(r"^[ \t]*(?:[-*+]|\d+[.)])[ \t]+", "", line).replace("**", "").replace("`", "").strip()
        if line:
            out.append(line)
    return out


def _verdict(items: list, label: str, words: tuple) -> tuple:
    """(the verdict word, the line) of the line that opens with the label (a pattern) and a colon; ('', '') when
    there is none."""
    for line in items:
        m = re.match(rf"(?i)(?:{label})[ \t]*[:\-][ \t]*(.*)$", line)
        if m:
            rest = m.group(1).lower()
            first = re.match(r"\W*(" + "|".join(words) + r")\b", rest)
            return (first.group(1) if first else next((w for w in words if re.search(rf"\b{w}\b", rest)), "")), line
    return "", ""


def outcome(report: str) -> dict:
    """What a report says against its brief: whether it says it at all (stated), the verdict on what was expected
    (met, not met, cannot tell) and on what would change the person's mind (seen, not seen, cannot tell), the
    other lines of the part (the checks), and what did not fit."""
    against, misfit = _section(report, "Against the brief"), _section(report, "Did not fit")
    items = _items(against)
    expected, line_e = _verdict(items, r"expected|expectation", VERDICTS)
    changed, line_c = _verdict(items, r"(?:what )?would change their mind", SEEN)
    return {"stated": against is not None and bool(expected),
            "expected": expected, "would_change": changed,
            "checks": [x for x in items if x not in (line_e, line_c)],
            "did_not_fit": [x for x in _items(misfit) if not re.fullmatch(r"(?i)(nothing|none)\W*", x)]}
