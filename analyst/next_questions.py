"""Next questions: what could be analysed after a finished analysis (docs/ARCHITECT_DESIGN.md §2.7, §2.15).

The person picks one of five levels, and one model call - the Architect's seat - returns up to five questions at
that level. Each comes from a line the analysis left on record: a part of its brief, a line of its report, what was
asked and found (record()). A level reads its own lines first (OWN), and where it has any, one question at least
comes from them. A question says which line it comes from by number, so what the person is shown as its origin is
the record's own text. The questions are kept with the run they follow (Run.next_questions); one that is run is
marked there (ran()). Nothing here computes, and nothing writes a brief: a question that is run is analysed as it
stands.
"""
from __future__ import annotations

import os
import re
import time
from typing import Callable

from analyst import architect
from analyst import brief as briefs
from analyst.notebook import Notebook, Run, has_data

with open(os.path.join(os.path.dirname(__file__), "next_questions.md"), encoding="utf-8") as _fh:
    SYSTEM = _fh.read().strip()

# what a question at each level does, as the prompt says it
LEVELS = {"refine": "keeps the question and narrows it: a finer split, a part of the data, a stricter measure",
          "shift": "puts another explanation of the same result to the test",
          "test": "tests what the result rests on, or where it stops holding",
          "blend": "joins two findings in one question",
          "emergence": "follows what the analysis did not explain"}
# the kinds of line each level reads first
OWN = {"refine": ("comparison", "measure", "period", "asked"), "shift": ("check", "proposal"), "test": ("anchor", "would_change"),
       "blend": ("found", "earlier"), "emergence": ("misfit",)}
# a line's kind, as the prompt names it
SAID = {"comparison": "Fixed, what was compared", "measure": "Fixed, the measure", "period": "Fixed, the period", "check": "Also checked",
        "proposal": "Proposed, not tested", "anchor": "Rests on", "would_change": "Would change their mind", "misfit": "Did not fit",
        "asked": "Asked", "found": "Found", "earlier": "Found earlier"}
QUESTIONS = 5                    # questions in one set, at most
EFFORT = ("low", "medium")       # one short reply over a short prompt: the seat's effort is lowered for it
MOST = 6                         # lines of one kind, at most
BEFORE = 25                      # questions proposed before that the prompt carries, the newest
LINE_CHARS, QUESTION_CHARS, TITLE_CHARS = 400, 600, 60
NO_LINE = "it holds no question that names its line under SOURCES"
NOT_OWN = "no question comes from the lines the level reads"


def _line(value, chars: int) -> str:
    return re.sub(r"\s+", " ", value).strip()[:chars] if isinstance(value, str) else ""


def record(nb: Notebook, run: Run) -> list:
    """The lines an analysis leaves that a question can come from, each {"kind", "text"}: what its brief fixed, what
    was also checked and what the Architect proposed and the person did not accept, what the brief rests on that was
    not found to hold, what would change the person's mind, what did not fit, what was asked and what was found -
    and what the analyses before it found, the newest first."""
    brief, seen = run.brief or {}, run.brief_outcome or {}
    fixed = brief.get("fixed") or {}
    out = [(key, fixed.get(key)) for key in briefs.FIXED]
    out += [("check", x) for x in (seen.get("checks") or [])[:MOST]]
    out += [("proposal", r["text"]) for r in briefs.latest(run.framing).get("also_check", []) if r.get("source") == "architect" and not r.get("accepted")]
    out += [("anchor", f"{a['text']} ({a.get('mark') or 'not checked'}" + (f": {a['note']})" if a.get("note") else ")"))
            for a in brief.get("rests_on", []) if a.get("mark") != "holds"]
    if brief.get("would_change"):
        out.append(("would_change", brief["would_change"] + (f" ({seen['would_change']})" if seen.get("would_change") else "")))
    out += [("misfit", x) for x in (seen.get("did_not_fit") or [])[:MOST]]
    out += [("asked", run.question), ("found", nb.conclusion(run))]
    before = [r for r in nb.path(run.id)[:-1] if r.report and not any(t.kind == "ideas" for t in r.turns)]
    out += [("earlier", nb.conclusion(r)) for r in reversed(before[-MOST:])]
    return [{"kind": kind, "text": _line(text, LINE_CHARS)} for kind, text in out if _line(text, LINE_CHARS)]


def sources(nb: Notebook, run: Run, level: str) -> tuple:
    """The lines a level's questions may come from - the ones the level reads first, then the others - and how many
    are the level's own."""
    lines = record(nb, run)
    own = [line for line in lines if line["kind"] in OWN[level]]
    return own + [line for line in lines if line["kind"] not in OWN[level]], len(own)


def prompt(nb: Notebook, run: Run, level: str, lines: list, own: int, data: str = "") -> str:
    """What the model reads for one set. What does not change from one level to the next comes first."""
    parts = [f"DATA:\n{data}"] if data else []
    before = architect.earlier(nb, run.id)
    parts += [before] if before else []
    parts += [f"QUESTION:\n{run.question.strip()}", f"REPORT:\n{run.report.strip()}"]
    parts += [briefs.render(run.brief, data=has_data(run.data))] if run.brief else []
    proposed = [q["text"] for asked in run.next_questions for q in asked["questions"]][-BEFORE:]
    parts += ["PROPOSED BEFORE:\n" + "\n".join(f"- {text}" for text in proposed)] if proposed else []
    numbered = [f"{k}. {SAID[line['kind']]}: {line['text']}" for k, line in enumerate(lines, 1)]
    parts += [f"LEVEL: {level} - a question at this level {LEVELS[level]}",
              "SOURCES:\n" + "\n".join(numbered[:own] + (["Other lines:"] if 0 < own < len(numbered) else []) + numbered[own:]),
              "Reply with the JSON object."]
    return "\n\n".join(parts)


def parse(text: str, lines: int, own: int, pair: bool = False) -> list:
    """The questions of a reply, each {"title", "text", "from": the numbers of the lines it comes from}: one line of
    the `lines` given, or two - and two it must be where `pair` says so. A question that names no such line is left
    out, as is one given twice; five at most. Raises Unreadable when no question stands, or when the level has lines
    of its own - the first `own` - and no question comes from one."""
    obj = architect.reply_object(text)
    out = []
    for item in obj.get("questions") if isinstance(obj.get("questions"), list) else []:
        item = item if isinstance(item, dict) else {}
        question = _line(item.get("question"), QUESTION_CHARS)
        numbers = []
        for n in item.get("from") if isinstance(item.get("from"), list) else [item.get("from")]:
            if isinstance(n, int) and not isinstance(n, bool) and 1 <= n <= lines and n not in numbers:
                numbers.append(n)
        if question and len(numbers) >= (2 if pair else 1) and question not in [q["text"] for q in out]:
            out.append({"title": _line(item.get("title"), TITLE_CHARS), "text": question, "from": numbers[:2]})
    out = out[:QUESTIONS]
    if not out:
        raise architect.Unreadable(NO_LINE)
    if own and not any(n <= own for q in out for n in q["from"]):
        raise architect.Unreadable(NOT_OWN)
    return out


def propose(llm: Callable, nb: Notebook, run: Run, level: str, data: str = "") -> dict:
    """One set of next questions for a finished analysis, at a level: one model call, asked once more where its
    reply cannot be read. Returns the set as it is kept with the run - {"level", "questions": [{"title", "text",
    "from": [the lines it comes from, each {"kind", "text"}]}], "cost", "at"}; raises architect.Failed."""
    lines, own = sources(nb, run, level)
    got, _, cost = architect.ask(llm, SYSTEM, prompt(nb, run, level, lines, own, data), lambda reply: parse(reply, len(lines), own, level == "blend"), EFFORT)
    return {"level": level, "questions": [{**q, "from": [lines[n - 1] for n in q["from"]]} for q in got], "cost": round(cost, 4), "at": time.time()}


def ran(run: Run, at, chain) -> bool:
    """A question of a run's sets was run: `at` is (the set, the question) by their places, `chain` the analysis it
    started. Marked on the question; False where `at` names none."""
    place = lambda i, of: isinstance(i, int) and not isinstance(i, bool) and 0 <= i < len(of)      # noqa: E731
    s, k = at if isinstance(at, (list, tuple)) and len(at) == 2 else (None, None)
    if not place(s, run.next_questions) or not place(k, run.next_questions[s]["questions"]):
        return False
    run.next_questions[s]["questions"][k]["ran"] = str(chain)
    return True
