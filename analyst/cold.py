"""The cold read: a question read as the analyst will read it, before its analysis starts
(docs/ARCHITECT_DESIGN.md §2.22).

The Pathfinder words the question inside a conversation. What was said there, a saved analysis of another day, "as
before" - all of it reads plainly to the Pathfinder, and to nobody who was not there. So what the analyst will be
given of a framed question (given()) is given to a model that has nothing else either, and it is asked which words
of the question point to something it was not given (read()). ready() is the step before an analysis starts: the
read, and where it names something the Pathfinder's next reply.

Two things are held in code. A phrase counts only where it stands in the question, word for word (named()): one
the model makes up starts nothing. And a version of the brief is read once, the Pathfinder's wording after a read
not at all: a read holds a start up once.
"""
from __future__ import annotations

import os
import re
import time
from typing import Callable, Optional

from analyst import architect
from analyst import brief as briefs
from analyst import steps
from analyst.notebook import Notebook, Run

with open(os.path.join(os.path.dirname(__file__), "cold.md"), encoding="utf-8") as _fh:
    SYSTEM = _fh.read().strip()

EFFORT = ("low",)                # a short text read once: the seat's effort is lowered to this; a seat set lower stays lower
PHRASES = 3                      # what one read names, at most
ASK = "Reply with the JSON object."


def given(question: str, brief: dict, data: bool = True, described: str = "", earlier: str = "") -> str:
    """What the analyst is given of a question framed with the Pathfinder, in the order its prompt has it
    (analyst/session.py): the analyses the question follows (`earlier`: the notebook's ledger of them), the data as
    described (`described`), the question, and the BRIEF block - of the brief as agreed, without what the person did
    not accept (analyst/brief.py agreed(), render()). `data`: whether the run has data to run on."""
    parts = [earlier, f"DATA:\n{described}" if described else "", f"QUESTION:\n{(question or '').strip()}", briefs.render(briefs.agreed(brief), data=data)]
    return "\n\n".join(p for p in parts if p)


def named(reply: str, question: str) -> list:
    """The phrases a reply names, each as the question has it: found there whatever the case and the spaces between
    its words, once each, PHRASES at most. A reply that is not the object asked for names none."""
    try:
        said = architect.reply_object(reply).get("cannot_place")
    except architect.Unreadable:
        return []
    found = []
    for phrase in said if isinstance(said, list) else []:
        words = phrase.split() if isinstance(phrase, str) else []
        there = re.search(r"\s+".join(re.escape(w) for w in words), question or "", re.I) if words else None
        if there and " ".join(there.group(0).split()) not in found:
            found.append(" ".join(there.group(0).split()))
    return found[:PHRASES]


def read(reader: Callable, question: str, text: str) -> tuple:
    """One cold read of `text`, what the analyst is given (given()): (the phrases of `question` the reader could not
    place, what the call cost). A reply that was declined, cut off or is not the object asked for names nothing: a
    read never holds an analysis up by failing."""
    reply, usage = reader(SYSTEM, text + "\n\n" + ASK, effort=EFFORT)
    return named(reply, question), float((usage or {}).get("cost") or 0.0)


def ready(llm: Callable, reader: Callable, nb: Notebook, run: Run, step: Optional[int] = None, data: str = "", **more) -> tuple:
    """Before the analysis of a framed question starts: (the framing as it then stands, whether it can start).

    The question to run under - that of the step on the person's screen, `step` (analyst/steps.py) - is read cold
    by `reader`, once: a version of the brief the framing lists as read (`read`) is not read again. The step read
    is the one in use from then: its analysis is what was asked for. The read is a step of the conversation. One
    that names nothing lets the analysis start. One that names something has the Pathfinder go on at once - `llm`,
    one exchange with no message, whose CONVERSATION ends on what could not be placed; `data`, the data as
    described, and `more` are the exchange's (analyst/architect.py exchange()). The analysis does not start then:
    the person sees what the Pathfinder made of it, and starts again. The version the Pathfinder leaves is listed
    as read without a read: a read holds a start up once.

    A read is one call of its own kind: its turn numbers it among the reads of the whole brief - those of the
    steps set aside too - and the Pathfinder's calls are counted apart. Raises architect.Failed where the
    Pathfinder's reply fails: the read stands, the calls of the failed reply are counted, and the version is not
    read again."""
    framing = steps.go(run.framing or {}, step) if step is not None else run.framing or {}
    brief = briefs.latest(framing) or {"question": run.question}
    at, done = brief.get("version"), list(framing.get("read") or [])
    if at in done:
        return run.framing, True
    began, question = time.time(), brief.get("question") or run.question
    missing, cost = read(reader, question, given(question, brief, framing.get("data") is not False, data, nb.render_ancestry(str(run.id))))
    turn = {"who": "reader", "missing": missing, "v": at, "cost": round(cost, 4), "call": 1 + sum(1 for t in steps.said(framing) if t.get("who") == "reader"),
            "secs": round(time.time() - began, 1)}
    run.framing = steps.take({**framing, "turns": list(framing.get("turns") or []) + [turn], "read": done + [at]})
    if not missing:
        return run.framing, True
    try:
        after = architect.exchange(llm, nb, run, None, data=data, **more)
    except architect.Failed as exc:
        run.framing = {**run.framing, "calls": int(framing.get("calls") or 0) + exc.calls}
        raise
    left = briefs.latest(after).get("version")
    run.framing = {**after, "read": done + [at] + [v for v in (left,) if v != at]}
    return run.framing, False
