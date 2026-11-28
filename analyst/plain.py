"""The steps of a finished analysis in plain words (2026-11-28, Palo).

The code trace's Steps view (analyst/codemap) had each step in the analyst's own sentence - written for itself, in its
technical words - and what a step found was not said in its row at all: the analyst says that in the first sentence
of its next turn, which the trace leaves out. One model call when the run ends - the Rewriter's seat - puts every
step of the trace into two plain lines: what the step did, and what it showed.

A step is given to the model as the record has it (steps()): what the analyst set out to do, the beginning of what
the code printed, the results it recorded, the error of an attempt that failed, the captions of the figures, and what
the analyst wrote about the output once it had seen it. Not the code. The reply is read by step (read()), and a
step's lines are kept only where they hold (holds()): both are there, and every number in them stands in what the
model was given of that step - at the precision stated, as the report's guard reads a number. A step without lines
keeps the analyst's own sentence in the trace.

The lines are kept with the run (Run.plain), beside its code trace and not in it: the trace is built mechanically,
without a model, and the same chain always gives the same trace. A step's name - "cell 3", or "turn 5" for an attempt
that did not run through - is what the trace's row finds its lines by (web_app/static/js/code-map.js).
"""
from __future__ import annotations

import os
import re
import time
from typing import Callable, List, Tuple

from . import report as rep
from . import tools
from .codemap.record import captions_of, turn_numbers
from .notebook import Run, Turn, purpose_of, split_sentences

with open(os.path.join(os.path.dirname(__file__), "plain.md"), encoding="utf-8") as _fh:
    SYSTEM = _fh.read().strip()

PRINTED_CHARS = 1_500            # the beginning of what one step printed, as the prompt carries it
STEPS_CHARS = 60_000             # what the steps printed, together: beyond it each step's share is shortened alike
SHARE_CHARS = 300                # ... to this at the least
SET_OUT_CHARS, READ_AS_CHARS = 700, 400      # the analyst's account of the step, and its first sentence after it
DID_CHARS, SHOWED_CHARS = 320, 480           # a line as it is kept: the sentences that fit - the instructions ask for one or two, and one to three
GOES_ON = "(the print goes on)"
NOT_WRITTEN = "not written"
_NAME_RE = re.compile(r"^[\s=*#\[\-]*(cell|turn)\s+(\d+)\s*(?:\([^)\n]*\))?[\s=*#\]:\-]*$", re.I)     # a step's name on a line of its own, in any dress
_LINE_RE = re.compile(r"^[\s*_\-]*(DID|SHOWED)[\s*_]*:[\s*_]*(.*)$", re.I)
_FULL_STOP_RE = re.compile(r"\.(?=\s|$)")      # the full stop that ends a sentence


def _read_as(run: Run, i: int) -> str:
    """What the analyst wrote about turn i's output once it had seen it: the first sentence of its next turn - by the
    contract's order that sentence says what the last output showed. A review between the two is not the analyst's."""
    for t in run.turns[i + 1:]:
        if t.kind == "review" or t.step:
            continue
        said = split_sentences(" ".join((t.thinking or "").split()))
        return said[0][:READ_AS_CHARS] if said and said[0] else ""
    return ""


def steps(run: Run) -> List[dict]:
    """The steps of the run's code trace, in the order they ran, each as the record has it: {name, given}. `name` is
    "cell n" for a cell that ran - the figures cell among them - and "turn n" for an attempt that failed or was not
    run; `given` is what the prompt says of it. A figures attempt that failed is no row of the trace with a turn of
    its own, and none here."""
    captions = captions_of(run.report)
    rows = []                                                # (name, the lines before the print, the print, the lines after it)
    for i, (t, num) in enumerate(zip(run.turns, turn_numbers(run))):
        if t.kind != "cell":
            continue
        set_out = f"SET OUT TO: {purpose_of(t, SET_OUT_CHARS)}"
        read_as = [f"THEN READ AS: {said}" for said in [_read_as(run, i)] if said]
        if t.cell_no and t.step == "figures":
            drew = captions.get(t.cell_no) or [f"{len(t.figures or [])} figure(s), without a caption"]
            rows.append((f"cell {t.cell_no}", ["DREW:"] + [f"- {c}" for c in drew], "", []))
        elif t.cell_no:
            recorded = [f"- {r['text']}" for r in t.results or [] if r.get("text")]
            rows.append((f"cell {t.cell_no}", [set_out], (t.stdout or "").strip(), (["RECORDED:"] + recorded if recorded else []) + read_as))
        elif t.error and num:
            stopped = f"NOT RUN: a restricted operation ({t.refused})" if t.refused else f"FAILED WITH: {tools.exception_line(t.error)}"
            rows.append((f"turn {num}", [set_out, stopped], "", read_as))
    printed = [p for _, _, p, _ in rows if p]
    share = PRINTED_CHARS if sum(min(len(p), PRINTED_CHARS) for p in printed) <= STEPS_CHARS else max(SHARE_CHARS, STEPS_CHARS // len(printed))
    cut = lambda p: ["PRINTED:", p if len(p) <= share else p[:share].rstrip() + "\n" + GOES_ON] if p else []     # noqa: E731
    return [dict(name=name, given="\n".join(before + cut(p) + after)) for name, before, p, after in rows]


def prompt(run: Run) -> Tuple[str, List[dict]]:
    """The call's user message, and the steps it asks about; no steps, no call."""
    found = steps(run)
    body = "\n\n".join(f"=== {s['name']} ===\n{s['given']}" for s in found)
    return f"QUESTION:\n{(run.question or '').strip()}\n\nSTEPS:\n\n{body}", found


def _fit(text: str, chars: int) -> str:
    """A line as it is kept: without the marks a model dresses it in, and its whole sentences while they fit `chars`."""
    out = ""
    for s in split_sentences(" ".join(text.replace("`", "").replace("**", "").split())):
        if len(out) + len(s) + 1 > chars:
            break
        out = (out + " " + s).strip()
    return out


def holds(did: str, showed: str, given: str) -> bool:
    """Whether a step's two lines are kept: both are there, and no number in them is one the step's own record lacks.
    The report's guard does not take a number that stands right before a full stop for one: here the full stops that
    end sentences are taken out first, on both sides, so the last number of a sentence is read like any other."""
    stops_out = lambda text: _FULL_STOP_RE.sub(" ", text)                                            # noqa: E731
    return bool(did and showed) and not rep.numbers_missing(stops_out(did + "\n" + showed), [stops_out(given)])


def read(reply: str, found: List[dict]) -> dict:
    """The reply by step: {name: {did, showed}} for each step asked about whose lines hold. A name the reply writes a
    second time is not read again, and what stands before the first name is nobody's."""
    given = {s["name"]: s["given"] for s in found}
    said, name, part = {}, None, None
    for ln in (reply or "").splitlines():
        m = _NAME_RE.match(ln)
        if m:
            name, part = f"{m.group(1).lower()} {int(m.group(2))}", None
            name = None if name in said else name
            if name:
                said[name] = {"did": [], "showed": []}
            continue
        m = _LINE_RE.match(ln)
        if m and name:
            part = m.group(1).lower()
            said[name][part].append(m.group(2))
        elif name and part and ln.strip():
            said[name][part].append(ln)
    out = {}
    for name, parts in said.items():
        did, showed = _fit(" ".join(parts["did"]), DID_CHARS), _fit(" ".join(parts["showed"]), SHOWED_CHARS)
        if name in given and holds(did, showed, given[name]):
            out[name] = {"did": did, "showed": showed}
    return out


def write(llm: Callable, run: Run, user: str, found: List[dict]) -> Turn:
    """The call: `llm(system, user, plain=True)` -> (text, usage). The lines that hold are kept as the run's `plain`,
    and the call is a turn of the record - step "plain", no turn of the analysis - that says how many of the steps
    have their lines, and what the call cost and took."""
    t0 = time.time()
    text, usage = llm(SYSTEM, user, plain=True)
    run.plain = read(text, found)
    turn = Turn(kind="plain", step="plain", note=run.note, text=f"{len(run.plain)} of {len(found)} steps",
                usage={**(usage or {}), "elapsed": round(time.time() - t0, 1)})
    run.turns.append(turn)
    return turn
