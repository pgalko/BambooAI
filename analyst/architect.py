"""The Architect: the model that frames a question with the person before it is analysed (docs/ARCHITECT_DESIGN.md
§2.3, §2.12).

One exchange is one model call. The Architect reads the data's description, the analyses the question follows, the
question, the brief as it stands and the conversation so far (prompt()), and replies with one JSON object: the parts
of the brief it writes, one message for the person, and choices to click where it offers them (parse()). exchange()
makes the call and returns the run's framing with the reply taken in: the brief as a new version when a part changed,
the conversation with the person's message and the Architect's.

Nothing here computes or looks anything up: the brief is words, and the analysis is the analyst's.
"""
from __future__ import annotations

import json
import os
import re
from typing import Callable, Optional

from analyst import brief as briefs
from analyst.notebook import Notebook, Run

with open(os.path.join(os.path.dirname(__file__), "architect.md"), encoding="utf-8") as _fh:
    SYSTEM = _fh.read().strip()

EFFORT = ("low", "medium")       # a short reply over a short prompt: the seat's effort is lowered for it, as for a report turn
TURNS_MAX = 12                   # replies in one brief: three or four frame a question; the bound is for a conversation that will not end
SAY_CHARS = 600                  # the Architect's message, at most
CHOICES, CHOICE_CHARS = 4, 120
EMPTY = "(empty)"
AGAIN = "Your last reply could not be read: {problem}. Reply with the JSON object and nothing else."
CUT = "it was cut off at the token limit"
SPENT = f"The Architect has replied {TURNS_MAX} times in this brief. Change the brief yourself, or start the analysis."
UNREAD = "The Architect's reply could not be read ({problem})."
DECLINED = "The model declined to reply ({category})."


class Unreadable(ValueError):
    """A reply that is not the JSON object asked for; its text says what is wrong with it."""


class Failed(RuntimeError):
    """An exchange that brought no reply to keep: the reason, in words for the person, and the model calls it made."""

    def __init__(self, reason: str, calls: int = 0, cost: float = 0.0):
        super().__init__(reason)
        self.calls, self.cost = calls, cost


def _line(value, chars: int) -> str:
    return re.sub(r"\s+", " ", value).strip()[:chars] if isinstance(value, str) else ""


def parse(text: str) -> dict:
    """The reply's JSON object, fenced or bare: {"brief": the parts it writes, "say": its message, "choices": [...]}.
    Raises Unreadable."""
    t = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", t, re.S)
    if fenced:
        t = fenced.group(1)
    else:
        a, b = t.find("{"), t.rfind("}")
        if a < 0 or b < a:
            raise Unreadable("it holds no JSON object")
        t = t[a:b + 1]
    try:
        obj = json.loads(t)
    except ValueError as exc:
        raise Unreadable(f"its JSON does not parse: {exc}") from exc
    if not isinstance(obj, dict):
        raise Unreadable("it is not a JSON object")
    say = _line(obj.get("say"), SAY_CHARS)
    if not say:
        raise Unreadable('it has no "say"')
    choices = []
    for c in obj.get("choices") if isinstance(obj.get("choices"), list) else []:
        c = _line(c, CHOICE_CHARS)
        if c and c not in choices:
            choices.append(c)
    return {"brief": obj.get("brief") if isinstance(obj.get("brief"), dict) else {}, "say": say, "choices": choices[:CHOICES]}


def block(brief: dict) -> str:
    """The BRIEF block of the Architect's prompt: every part under the name the reply uses for it."""
    lines = [f"BRIEF (version {brief.get('version', 1)}):"]
    for key in ("decision", "thinks"):
        lines.append(f"{key}: {brief.get(key) or EMPTY}")
    lines.append("rests_on:" + ("" if brief.get("rests_on") else f" {EMPTY}"))
    lines += [f"- {a['text']}" for a in brief.get("rests_on", [])]
    for key in ("expects", "would_change"):
        lines.append(f"{key}: {brief.get(key) or EMPTY}")
    lines.append("also_check:" + ("" if brief.get("also_check") else f" {EMPTY}"))
    lines += [f"- {r['text']}" for r in brief.get("also_check", [])]
    lines += [f"fixed.{key}: {brief.get('fixed', {}).get(key) or EMPTY}" for key in briefs.FIXED]
    return "\n".join(lines)


def earlier(nb: Notebook, run_id: str) -> str:
    """The analyses the run's question follows, oldest first: each one's question and what it found - or what the
    analyst stopped and asked - and, where it ran under a brief, how the result stood against it. '' when the
    question follows none."""
    path = nb.path(str(run_id))[:-1]
    if not path:
        return ""
    out = ["EARLIER (the analyses this question follows, oldest first):"]
    for k, run in enumerate(path, 1):
        out.append(f"[{k}] Q: {_line(run.question, 600)}")
        asked = next((t.text for t in reversed(run.turns) if t.kind == "ask"), "") if run.status == "asked" else ""
        out.append(f"    The analyst stopped and asked: {_line(asked, 900)}" if asked else f"    Found: {nb.conclusion(run)}")
        seen = run.brief_outcome                       # empty unless the run was under a brief
        verdicts = [f"{name}: {seen[key]}" for key, name in (("expected", "what they expected"), ("would_change", "what would change their mind")) if seen.get(key)]
        if verdicts:
            out.append("    Against its brief - " + "; ".join(verdicts))
        if seen.get("did_not_fit"):
            out.append("    Did not fit: " + "; ".join(_line(x, 300) for x in seen["did_not_fit"][:4]))
    return "\n".join(out)


def conversation(turns: list) -> str:
    said = [f"{'Architect' if t.get('who') == 'architect' else 'Person'}: {t.get('text', '')}" for t in turns]
    return "CONVERSATION:\n" + ("\n".join(said) if said else "(nothing yet)")


def prompt(question: str, brief: dict, turns: list, data: str = "", before: str = "") -> str:
    """What the Architect reads for one reply. What does not change from one reply to the next comes first."""
    parts = [f"DATA:\n{data}"] if data else []
    parts += [before] if before else []
    parts += [f"QUESTION:\n{question.strip()}", block(brief), conversation(turns), "Reply with the JSON object."]
    return "\n\n".join(parts)


def exchange(llm: Callable, nb: Notebook, run: Run, text: Optional[str] = None, data: str = "") -> dict:
    """One exchange in a framing run: the person's message - none on the Architect's first turn - and its reply. A
    reply that cannot be read is asked for once more. Returns the framing as it then stands: the brief as one more
    version when the reply changed a part (the Architect's, made from the question or from an answer), the
    conversation with both messages, the calls counted. Raises Failed; nothing is kept of an exchange that fails."""
    framing = dict(run.framing or {})
    turns = list(framing.get("turns") or [])
    if sum(1 for t in turns if t.get("who") == "architect") >= TURNS_MAX:
        raise Failed(SPENT)
    first = not turns and not text
    said = text.strip()[:briefs.QUESTION_CHARS] if isinstance(text, str) else ""
    if said:
        turns.append({"who": "person", "text": said})
    brief = briefs.latest(framing) or {"question": run.question}
    user = prompt(run.question, brief, turns, data, earlier(nb, run.id))
    got, problem, calls, cost = None, "", 0, 0.0
    for attempt in range(2):
        reply, usage = llm(SYSTEM, user if not attempt else user + "\n\n" + AGAIN.format(problem=problem), effort=EFFORT)
        usage = usage or {}
        calls, cost = calls + 1, cost + float(usage.get("cost") or 0.0)
        if usage.get("declined"):
            raise Failed(DECLINED.format(category=usage["declined"]), calls, cost)
        try:
            got = parse(reply)
            break
        except Unreadable as exc:
            problem = CUT if usage.get("truncated") else str(exc)
    if got is None:
        raise Failed(UNREAD.format(problem=problem), calls, cost)
    written, changed = briefs.write(brief, got["brief"])
    if changed:
        framing = briefs.version(framing, written, by="architect", changed=changed, why="question" if first else "answer")
    made = int(framing.get("calls") or 0) + calls
    turns.append({"who": "architect", "text": got["say"], **({"choices": got["choices"]} if got["choices"] else {}),
                  "v": len(framing.get("versions") or []), "cost": round(cost, 4), "call": made})
    return {**framing, "turns": turns, "calls": made}
