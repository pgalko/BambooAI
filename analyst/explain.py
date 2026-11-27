"""Explanations: what a reader asks about a passage of a finished analysis.

The person reads an analysis - its report in the Answer tab, its script in the Code tab, what the script printed in
the Results tab - selects a passage and asks about it. One model call - the Pathfinder's seat - answers in a few plain
sentences, from what the analysis holds and from what is generally known. Nothing is computed and no analysis
starts: a question that takes one is told so.

Everything asked about one analysis is one conversation, in the order asked, whichever passages it is about: every
call is given all of it (conversation()), so a question builds on the answers before it. An exchange is kept with
the run (Run.explained) together with where its passage stands (taken()): the page marks the passage and shows under
it what was asked there. Exchanges with the same place are one note; the first of them is about the passage itself,
the later ones about words selected there or in the answers under it.
"""
from __future__ import annotations

import os
import re
import time
from typing import Callable

from analyst import architect
from analyst import brief as briefs
from analyst.notebook import Notebook, Run

with open(os.path.join(os.path.dirname(__file__), "explain.md"), encoding="utf-8") as _fh:
    SYSTEM = _fh.read().strip()

# the tabs a passage can stand in, as the page names them, and what the prompt calls each
TABS = {"answer": "the Answer tab", "code": "the Code tab", "code_exec_results": "the Results tab"}
# the two versions of the Answer tab: a passage stands in one of them
VIEWS = {"technical": "the technical report", "simplified": "the report in plain language"}
EFFORT = ("low", "medium")       # a short answer over what is in view: the seat's effort is lowered for it
PASSAGE_CHARS = 8000             # a passage, at most: some hundred lines of code
ANSWER_CHARS = 6000              # an answer as it is kept: the instructions ask for some eighty words, and this bounds a reply that does not end
EXCHANGES = 100                  # exchanges about one analysis: the bound is for a page that will not stop
TEXT_CHARS = 40_000              # the report, its plain version and the code, each whole up to this
CELL_CHARS = 3000                # what one cell printed, as the prompt carries it
CONVERSATION_CHARS = 24_000      # the answers of the conversation ride whole, the newest first, while together they fit this
OPENING_CHARS, LINE_CHARS = 200, 300      # an older answer cut to its opening; a passage and a question on one line
NO_PLACE = "The selection could not be placed: select it again."
TOO_LONG = "The selection is too long to explain: select less."
NO_QUESTION = "A question is needed."
SPENT = f"This analysis was asked about {EXCHANGES} times, and that is the most."
EMPTY = "it is empty"
AGAIN = "Your last reply could not be read: {problem}. Reply with the answer and nothing else."
UNREAD = "No explanation was written: the model's reply could not be used ({problem})."


def _line(value, chars: int) -> str:
    text = re.sub(r"\s+", " ", value).strip() if isinstance(value, str) else ""
    return text if len(text) <= chars else text[:chars].rstrip() + " ..."


def place(asked: dict) -> tuple:
    """Where an exchange's passage stands, as one value: exchanges with the same place are one note."""
    return asked["tab"], asked["view"], asked["at"], asked["passage"]


def taken(data: dict) -> dict:
    """What the page asks, as it is kept: where the passage stands - `tab`, for the Answer tab `view`, which of its two
    versions; `passage`, the text as the page finds it again, and `at`, which of its occurrences there - then `quote`,
    the words selected, and `question`. Raises ValueError with the reason, in words for the person."""
    data = data if isinstance(data, dict) else {}
    tab, view, at = data.get("tab"), data.get("view") or "", data.get("at")
    passage, quote, question = (data.get(key).strip() if isinstance(data.get(key), str) else "" for key in ("passage", "quote", "question"))
    if tab not in TABS or view not in (VIEWS if tab == "answer" else ("",)) or not passage or not isinstance(at, int) or isinstance(at, bool) or at < 0:
        raise ValueError(NO_PLACE)
    if len(passage) > PASSAGE_CHARS or len(quote) > PASSAGE_CHARS:
        raise ValueError(TOO_LONG)
    if not question:
        raise ValueError(NO_QUESTION)
    return {"tab": tab, "view": view, "passage": passage, "at": at, "quote": quote or passage, "question": question[:briefs.QUESTION_CHARS]}


def where(asked: list, k: int) -> str:
    """Where the passage of the k-th exchange stands, in the prompt's words: its tab - or, where an earlier exchange
    has the same place, that one's number."""
    first = next(i for i, x in enumerate(asked) if place(x) == place(asked[k]))
    if first < k:
        return f"at the passage of [{first + 1}] again"
    return f"in {TABS[asked[k]['tab']]}" + (f", {VIEWS[asked[k]['view']]}" if asked[k]["view"] else "")


def conversation(asked: list) -> str:
    """What was asked about the analysis before, oldest first, each under its number: where its passage stands, the
    words selected, the question and the answer. The newest answers whole while together they fit
    CONVERSATION_CHARS; the older ones cut to their opening. '' where nothing was asked."""
    whole, room = len(asked), CONVERSATION_CHARS
    while whole and room >= len(asked[whole - 1]["answer"]):
        whole -= 1
        room -= len(asked[whole]["answer"])
    lines = [f"[{k + 1}] Selected {where(asked, k)}: {_line(x['quote'], LINE_CHARS)}\n    Asked: {_line(x['question'], LINE_CHARS)}\n"
             f"    You answered: {x['answer'] if k >= whole else _line(x['answer'], OPENING_CHARS)}" for k, x in enumerate(asked)]
    return "CONVERSATION (what the person asked about this analysis before, oldest first):\n" + "\n".join(lines) if lines else ""


def analysis(nb: Notebook, run: Run) -> str:
    """The analysis as its reader has it: what it ran on, its question, its report and the report's plain version, the
    script the Code tab shows - the cells' code where no script was kept - and what each cell printed."""
    cells = nb.computed_cells(run.id)
    code = run.replay_script.strip() or "\n\n".join(t.code.rstrip() for t in cells)
    printed = "\n".join(f"--- cell {t.cell_no} ---\n{architect.fit((t.stdout or '').strip(), CELL_CHARS) or '(nothing)'}" for t in cells)
    parts = [("DATA", nb.data_words(run)), ("QUESTION", run.question.strip()), ("REPORT", architect.fit(run.report.strip(), TEXT_CHARS)),
             ("REPORT IN PLAIN LANGUAGE", architect.fit(run.rewrite.strip(), TEXT_CHARS)), ("CODE", architect.fit(code, TEXT_CHARS)),
             ("WHAT THE CELLS PRINTED", printed)]
    return "\n\n".join(f"{name}:\n{text}" for name, text in parts if text)


def prompt(nb: Notebook, run: Run, asked: dict) -> str:
    """What the model reads for one exchange. What does not change from one question to the next comes first."""
    before, now = conversation(run.explained), run.explained + [asked]
    parts = [analysis(nb, run)] + ([before] if before else [])
    parts += [f"WHERE: {where(now, len(now) - 1)}", f"PASSAGE:\n{asked['quote']}", f"ASKED:\n{asked['question']}"]
    return "\n\n".join(parts)


def read(reply: str) -> str:
    """The answer of a reply: its text, bounded. Raises Unreadable where there is none."""
    text = (reply or "").strip()[:ANSWER_CHARS].rstrip()
    if not text:
        raise architect.Unreadable(EMPTY)
    return text


def answer(llm: Callable, nb: Notebook, run: Run, asked: dict) -> dict:
    """One exchange about a finished analysis: `asked` as taken() returns it, answered by one model call - asked once
    more where the reply is empty. Returns the exchange as it is kept with the run - `asked` with "answer", "cost" and
    "when"; raises architect.Failed with the reason, in words for the person."""
    if len(run.explained) >= EXCHANGES:
        raise architect.Failed(SPENT)
    text, _, cost = architect.ask(llm, SYSTEM, prompt(nb, run, asked), read, EFFORT, AGAIN, UNREAD)
    return {**asked, "answer": text, "cost": round(cost, 4), "when": time.time()}
