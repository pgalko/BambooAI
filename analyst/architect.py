"""The Architect: the model that frames a question with the person before it is analysed (docs/ARCHITECT_DESIGN.md
§2.3, §2.12-§2.14, §2.16, §2.17).

One exchange is one model call. The Architect reads the data's description, the analyses the question follows, the
question, the brief as it stands and the conversation so far (prompt()), and replies with one JSON object: the parts
of the brief it writes, one message for the person, and choices to click where it offers them (parse()). exchange()
makes the call and returns the run's framing with the reply taken in: the brief as a new version when a part changed,
the conversation with the person's message and the Architect's.

The question is not the Architect's to write. It gives a wording, the person takes it - on the page, or by saying
so, which the reply after reports - and only then is it the question (pending()).

A reply may also ask for lookups, to check what the brief rests on (analyst/lookup.py). The host answers them, and
what they found joins the conversation as a turn of its own; the reply to the next exchange marks the lines by it.
And it may propose another explanation, which enters the brief as the Architect's own, for the person to accept.
A reply may ask to have the person's saved analyses read as well (analyst/reader.py; §3): the host reads them, the
passages found enter the brief for the person to accept, and what was found is a turn of the conversation too. And
it may open a part of an analysis the question follows - its report, a cell, the conversation it was framed in:
the record gives it, for the reply after (opened()). What a reply asks for and cannot be done is said to it at
once, and the reply is asked for again. Nothing here computes: a lookup and a reading are the host's, and the
analysis is the analyst's.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Callable, Optional

from analyst import brief as briefs
from analyst import lookup
from analyst.notebook import Notebook, Run, Turn

with open(os.path.join(os.path.dirname(__file__), "architect.md"), encoding="utf-8") as _fh:
    SYSTEM = _fh.read().strip()

EFFORT = ("medium", "low")       # what to say next takes judgement, not long thought: the seat's effort is lowered to this; a seat set lower stays lower
TURNS_MAX = 200                  # replies in one brief: a person finding their way talks for as long as they like; the bound is for a page that will not stop
ROUNDS = 2                       # rounds of lookups after one message of the person's: the second is for what the first refused
NOT_ABOUT = "a lookup names the line under rests_on it checks, copied exactly"
PROPOSALS = 2                    # explanations the Architect proposes in one brief, in all: one left out is not proposed again and again
READINGS = 4                     # readings of the saved analyses in one brief: one serves one direction of the conversation, and each takes the person's time and money
OPENS = 3                        # parts of earlier analyses opened after one message of the person's: each is read whole by the replies that follow
OPEN_CHARS = 16_000              # of one part opened, as the Architect reads it: a longer one loses its middle
SAY_CHARS = 6000                 # the Architect's message, at most: the instructions ask for a short one, and this bounds a reply that does not end
CHOICES, CHOICE_CHARS = 4, 120
EMPTY = "(empty)"
AGAIN = "Your last reply could not be read: {problem}. Reply with the JSON object and nothing else."
NOT_DONE = ("Your last reply asked for what cannot be done now: {what}. Nothing was started. Reply again without asking for it, "
            "and do not tell the person that it is under way.")
READ_ALL = f"they were read {READINGS} times for this brief, and that is the most"
READ_SINCE = "they were read since the person last spoke"
NO_READER = "nothing here reads them"
OPENED_ALL = f"opening - {OPENS} parts were opened since the person last spoke, and that is the most"
LOOKED_ALL = f"lookups - {ROUNDS} rounds were made since the person last spoke, and that is the most"
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


def _say(value) -> str:
    """The Architect's message as it is kept: its lines, each on one line of text, at most one empty line between two
    paragraphs, bounded."""
    if not isinstance(value, str):
        return ""
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.strip().splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines))[:SAY_CHARS].rstrip()


def _whole(value) -> Optional[int]:
    """A whole number as a reply gives it - a number, or its digits in a string - or None."""
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def reply_object(text: str) -> dict:
    """The JSON object a reply holds, fenced or bare. Raises Unreadable."""
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
        obj = json.loads(t, strict=False)          # a new line inside a string is taken as it is: a message has lines
    except ValueError as exc:
        raise Unreadable(f"its JSON does not parse: {exc}") from exc
    if not isinstance(obj, dict):
        raise Unreadable("it is not a JSON object")
    return obj


def parse(text: str) -> dict:
    """What a reply of the Architect's says: {"brief": the parts it writes, "say": its message, "choices": [...],
    "wording": the question as it would put it to the analyst, "accept": whether the person agreed in words to the
    wording that waits, "lookups": what it asks of the data, "marks": the marks it gives, "propose": the explanations
    it proposes, "recall": whether it asks for the saved analyses to be read, "tick": the passages of saved analyses
    the person chose, by number, "open": the part of an earlier analysis it asks to read}. Raises Unreadable."""
    obj = reply_object(text)
    say = _say(obj.get("say"))
    if not say:
        raise Unreadable('it has no "say"')
    choices = []
    for c in obj.get("choices") if isinstance(obj.get("choices"), list) else []:
        c = _line(c, CHOICE_CHARS)
        if c and c not in choices:
            choices.append(c)
    asked, marks, proposed, ticked = (obj.get(key) if isinstance(obj.get(key), list) else [] for key in ("lookups", "marks", "propose", "tick"))
    return {"brief": obj.get("brief") if isinstance(obj.get("brief"), dict) else {}, "say": say, "choices": choices[:CHOICES],
            "wording": briefs.wording(obj.get("wording")), "accept": obj.get("accept") is True,
            "lookups": asked[:lookup.MAX_LOOKUPS], "marks": marks, "propose": proposed, "recall": obj.get("recall") is True,
            "tick": [n for n in ticked if isinstance(n, int) and not isinstance(n, bool)], "open": obj.get("open") if isinstance(obj.get("open"), dict) else None}


def block(brief: dict) -> str:
    """The BRIEF block of the Architect's prompt: every part under the name the reply uses for it. A line the brief
    rests on shows its mark, with what was found, once it was checked; an explanation the Architect proposed says so,
    and whether the person accepted it; so does a passage of a saved analysis, under the number a reply ticks it by."""
    lines = [f"BRIEF (version {brief.get('version', 1)}):"]
    for key in ("decision", "thinks"):
        lines.append(f"{key}: {brief.get(key) or EMPTY}")
    lines.append("rests_on:" + ("" if brief.get("rests_on") else f" {EMPTY}"))
    lines += [f"- {a['text']}" + (f" [{a['mark']}" + (f" - {a['note']}" if a.get("note") else "") + "]" if a.get("mark") else "")
              for a in brief.get("rests_on", [])]
    for key in ("expects", "would_change"):
        lines.append(f"{key}: {brief.get(key) or EMPTY}")
    lines.append("also_check:" + ("" if brief.get("also_check") else f" {EMPTY}"))
    lines += [f"- {r['text']}" + (f" [proposed by you, {'accepted' if r.get('accepted') else 'not accepted'}]" if r.get("source") == "architect" else "")
              for r in brief.get("also_check", [])]
    lines += [f"fixed.{key}: {brief.get('fixed', {}).get(key) or EMPTY}" for key in briefs.FIXED]
    if brief.get("saved"):
        lines.append("saved:")
        lines += [f"{k}. " + " ".join(x for x in (s.get("when"), f"\"{s.get('question', '')}\"") if x) + f": \"{s.get('passage', '')}\" [{'accepted' if s.get('accepted') else 'not accepted'}]"
                  for k, s in enumerate(brief["saved"], 1)]
    return "\n".join(lines)


def _drew(turn: Turn) -> str:
    """What a cell drew, for its line: the figures by their titles where they have one, else how many."""
    titles = [str(f["title"]) for f in turn.figures if isinstance(f, dict) and f.get("title")]
    if titles:
        return " (drew: " + "; ".join(_line(t, 120) for t in titles) + ")"
    return f" (drew {len(turn.figures)} figure{'s' if len(turn.figures) != 1 else ''})" if turn.figures else ""


def earlier(nb: Notebook, run_id: str, cells: bool = False) -> str:
    """The analyses the run's question follows, oldest first: each one's question and what it found - or what the
    analyst stopped and asked - and, where it ran under a brief, how the result stood against it. `cells`: for the
    Architect, who may open a part of one (opened()): what each has to open, and of the last a line to each cell,
    with what it drew. '' when the question follows none."""
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
        if cells:
            last = k == len(path) and run.cells()
            has = [name for name, there in (("its report", run.report or run.rewrite), ("its conversation", briefs.said(run.framing)), ("its cells:", last)) if there]
            out += ["    To open: " + ", ".join(has)] if has else []
            out += [f"    {nb.headline(t)}{_drew(t)}" for t in run.cells()] if last else []
    return "\n".join(out)


def recalled(turn: dict) -> list:
    """What a reading of the saved analyses found, as lines of the CONVERSATION block: how many runs there are and
    how many the second model read, each passage with its day, what was asked and the reader's note, and what was
    found across them, a count to each way - or why nothing was read."""
    if turn.get("failed"):
        return [f"Saved analyses: not read - {turn['failed']}"]
    found, across = turn.get("found", []), turn.get("across")
    lines = [f"Saved analyses ({turn.get('of', 0)} saved, {turn.get('read', 0)} read through):" + ("" if found or across else " nothing in them bears on it.")]
    lines += [f"- {f['when']} \"{f['question']}\"" + (f", in its {f['where']}" if f.get("where") else "") + f": \"{f['quote']}\"" + (f" - {f['note']}" if f.get("note") else "")
              for f in found]
    if turn.get("left"):
        lines.append(f"{turn['left']} more found: the brief has no room for them.")
    if across:
        lines.append(f"Across them - {across['topic']}: " + "; ".join(f"{len(g['runs'])} x {g['label']}" for g in across["groups"]))
    return lines


def pending(framing: dict) -> Optional[dict]:
    """The Architect's message whose wording of the question waits for the person: the last one that gave a wording,
    while the question has not changed since - taken, or changed by the person's own hand - and does not read so
    already. None when no wording waits."""
    turns, versions = (framing or {}).get("turns") or [], (framing or {}).get("versions") or []
    last = next((t for t in reversed(turns) if t.get("who") == "architect" and t.get("wording")), None)
    if last is None or any(v.get("n", 0) > last.get("v", 0) and "question" in (v.get("changed") or []) for v in versions):
        return None
    return None if last["wording"] == briefs.latest(framing).get("question") else last


def conversation(turns: list, waits: Optional[dict] = None) -> str:
    """The CONVERSATION block: who said what - under a message of the Architect's the wording of the question it
    gave, marked while it is the one that `waits` for the person, and the choices it offered, which the person may
    answer by - what each round of lookups found, a numbered line to a lookup, what a reading of the saved analyses
    found, and what was opened."""
    said = []
    for t in turns:
        if t.get("who") == "check":
            said += ["Lookups:"] + [f"{f['k']}. about \"{f['about']}\" - {f['fact']}" for f in t.get("found", [])]
        elif t.get("who") == "memory":
            said += recalled(t)
        elif t.get("who") == "opened":
            said.append(f"Not opened: {t['missing']}" if t.get("missing") else f"Opened: {t.get('label', '')}")
        else:
            said.append(f"{'Architect' if t.get('who') == 'architect' else 'Person'}: {t.get('text', '')}")
            if t.get("wording"):
                said.append(f"(wording given{', not taken yet' if t is waits else ''}: {t['wording']})")
            if t.get("choices"):
                said.append("(choices offered: " + " | ".join(t["choices"]) + ")")
    return "CONVERSATION:\n" + ("\n".join(said) if said else "(nothing yet)")


def prompt(question: str, brief: dict, turns: list, data: str = "", before: str = "", saved: int = 0, first: str = "",
           unread: str = "", waits: Optional[dict] = None, opened: str = "") -> str:
    """What the Architect reads for one reply. What does not change from one reply to the next comes first. `saved`:
    how many saved analyses the person has, said where there are any, with why they cannot be read now (`unread`)
    where they cannot. `first`: the question as the person first asked it, said where the wording has changed since.
    `waits`: the message whose wording waits for the person. `opened`: the parts of earlier analyses in view."""
    parts = [f"DATA:\n{data}"] if data else []
    parts += [before] if before else []
    parts += [f"SAVED: {saved}" + (f" (no reading can be made now: {unread})" if unread else "")] if saved else []
    asked = f"\n(first asked as: {first.strip()})" if first.strip() and first.strip() != question.strip() else ""
    parts += [f"QUESTION:\n{question.strip()}{asked}", block(brief), conversation(turns, waits)]
    parts += [opened] if opened else []
    return "\n\n".join(parts + ["Reply with the JSON object."])


def _since(turns: list, who: str) -> int:
    """The turns of one kind since the person last spoke."""
    n = 0
    for t in reversed(turns):
        if t.get("who") == "person":
            break
        n += t.get("who") == who
    return n


def _check(requests: list, brief: dict, made: int, look: Callable) -> dict:
    """A round of lookups, as a turn of the conversation. Each request is made a lookup about a line the brief rests
    on, or refused in words; `look` answers the ones that stand, in one go; what each found is one line, numbered on
    from the `made` lookups before it."""
    lines = [a["text"] for a in brief.get("rests_on", [])]
    asked = []
    for request in requests:
        spec, why = lookup.clean(request)
        about = spec.get("about", "") if spec else _line(request.get("about"), lookup.ABOUT_CHARS) if isinstance(request, dict) else ""
        asked.append((spec, why or ("" if about in lines else NOT_ABOUT), about))
    began = time.time()
    stand = [spec for spec, why, _ in asked if not why]
    answers = iter(look(stand) if stand else ())
    found = []
    for k, (spec, why, about) in enumerate(asked, made + 1):
        fact, result = (f"not looked up - {why}", False) if spec is None else lookup.found(spec, {"refused": why} if why else next(answers, None))
        found.append({"k": k, "about": about, "fact": fact, "ran": result})
    return {"who": "check", "found": found, "secs": round(time.time() - began, 1)}


def _recall(result: dict, brief: Optional[dict] = None) -> dict:
    """A reading of the saved analyses, as a turn of the conversation: the passages found - each with its run, its
    day, what was asked, where it stands, the passage and the reader's note - what was found across the analyses,
    how many there are and how many the second model read, what was dropped, why nothing was read where it was not,
    the seconds and the cost. `brief`: the brief after the reading; a passage found that it does not hold is counted
    under `left` and not listed, so what the Architect speaks of is what the person can tick."""
    every = result.get("found") or []
    kept = every if brief is None else [f for f in every if briefs.holds(brief, f)]
    found = [{"id": f["id"], "when": f["when"][:10], "question": f["question"] or f"Synthesis: {f['title']}", "where": f["where"], "quote": f["quote"], "note": f["note"]}
             for f in kept]
    cover = result.get("coverage") or {}
    return {"who": "memory", "found": found, **({"left": len(every) - len(kept)} if len(every) > len(kept) else {}),
            "across": result.get("across"), "of": int(cover.get("runs") or 0), "read": int(cover.get("judged") or 0),
            "dropped": int(result.get("dropped") or 0), "failed": str(result.get("failed") or ""), "secs": round(float(result.get("seconds") or 0.0), 1),
            "cost": round(float(result.get("cost") or 0.0), 4)}


def _read(framing: dict, turns: list, brief: dict, recall: Callable, question: str) -> dict:
    """The framing after a reading of the saved analyses: the passages found enter the brief not accepted, as one
    more version of the Architect's, and the reading is the conversation's last turn, read by the next exchange as a
    round of lookups is."""
    result = recall(question, block(brief))
    written, added = briefs.remember(brief, result.get("found"))
    if added:
        framing = briefs.version(framing, written, by="architect", changed=added, why="memory")
    return {**framing, "turns": turns + [{**_recall(result, written), "v": len(framing.get("versions") or [])}]}


def _unread(recall: Optional[Callable], turns: list) -> str:
    """Why the saved analyses cannot be read now, in words - '' when they can: once after a message of the person's,
    READINGS times in a brief, and only where the host reads them."""
    if recall is None:
        return NO_READER
    if sum(1 for t in turns if t.get("who") == "memory") >= READINGS:
        return READ_ALL
    return READ_SINCE if _since(turns, "memory") else ""


def _fit(text: str) -> str:
    """A part opened, as the Architect reads it: whole, or without its middle where it is longer than OPEN_CHARS,
    the cut said."""
    if len(text) <= OPEN_CHARS:
        return text
    head, tail = text[:OPEN_CHARS * 2 // 3].rstrip(), text[-(OPEN_CHARS // 3):].lstrip()
    return f"{head}\n... ({len(text) - len(head) - len(tail):,} characters left out here) ...\n{tail}"


def _part(nb: Notebook, run_id: str, what, k, n) -> tuple:
    """(what the person reads it as, its text) of a part of the analyses the run's question follows - the report of
    the k-th, the conversation that one was framed in, or the cell numbered n along them; without k, of the last -
    or ('', why there is no such part)."""
    path = nb.path(str(run_id))[:-1]
    if not path:
        return "", "the question follows no analysis"
    if what == "cell":
        cell = nb.cell(str(run_id), n) if n is not None else None
        if cell is None:
            numbers = [t.cell_no for t in nb.path_cells(str(run_id))]
            return "", ("a cell is opened by its number" if n is None else f"there is no cell {n}") + (f": the cells are {numbers[0]} to {numbers[-1]}" if numbers else "")
        out = f"ERROR:\n{cell.error.strip()}" if cell.error else f"OUTPUT:\n{cell.stdout.strip() or '(no output)'}"
        return f"cell {n}", f"```python\n{cell.code.rstrip()}\n```\n{out}" + (f"\n{_drew(cell).strip()}" if cell.figures else "")
    if what not in ("report", "conversation"):
        return "", "what can be opened is a report, a conversation or a cell"
    k = len(path) if k is None else k
    if not 1 <= k <= len(path):
        return "", f"there is no analysis {k}: EARLIER lists {len(path)}"
    run, of = path[k - 1], "" if k == len(path) else f" of analysis {k}"
    text = (run.report or run.rewrite).strip() if what == "report" else briefs.said(run.framing, run.question)
    return (f"the {what}{of}", text) if text else ("", f"analysis {k} has no {what}")


def _opened(nb: Notebook, run_id: str, request: dict) -> dict:
    """What a reply asked to open, as a turn of the conversation: the part it names, what the person reads it as and
    how long it is - or why there is no such part. Its text is not kept: opened() writes it again from the record."""
    what, k, n = request.get("what"), _whole(request.get("run")), _whole(request.get("n"))
    label, text = _part(nb, run_id, what, k, n)
    if not label:
        return {"who": "opened", "missing": text}
    return {"who": "opened", "what": what, **({"n": n} if what == "cell" else {} if k is None else {"run": k}), "label": label, "chars": len(_fit(text))}


def opened(nb: Notebook, run_id: str, turns: list) -> str:
    """The OPENED block: the parts of earlier analyses opened since the person last spoke, each whole, as the record
    holds it. '' when none was: a part is in view until the person speaks again, and no longer."""
    views = []
    for t in reversed(turns):
        if t.get("who") == "person":
            break
        if t.get("who") == "opened" and not t.get("missing"):
            label, text = _part(nb, run_id, t.get("what"), t.get("run"), t.get("n"))
            views.insert(0, f"--- {label} ---\n{_fit(text)}" if label else f"--- {t.get('label', '')} ---\n(no longer on record)")
    return "OPENED (in view until the person next speaks):\n" + "\n\n".join(views) if views else ""


def _grounded(proposal, data: str) -> bool:
    """Whether an explanation the Architect proposes names a column the data's description has: one the data cannot
    tell apart from the person's view is not proposed."""
    column = _line(proposal.get("column"), lookup.NAME_CHARS) if isinstance(proposal, dict) else ""
    return bool(column) and bool(re.search(r"(?<!\w)" + re.escape(column) + r"(?!\w)", data or ""))


def ask(llm: Callable, system: str, user: str, read: Callable, effort: tuple = EFFORT) -> tuple:
    """One reply of the model's, as `read` takes it in, asked at `effort`. A reply that cannot be read is asked for
    once more. Returns what was read, the calls made and what they cost; raises Failed."""
    problem, calls, cost = "", 0, 0.0
    for attempt in range(2):
        reply, usage = llm(system, user if not attempt else user + "\n\n" + AGAIN.format(problem=problem), effort=effort)
        usage = usage or {}
        calls, cost = calls + 1, cost + float(usage.get("cost") or 0.0)
        if usage.get("declined"):
            raise Failed(DECLINED.format(category=usage["declined"]), calls, cost)
        try:
            return read(reply), calls, cost
        except Unreadable as exc:
            problem = CUT if usage.get("truncated") else str(exc)
    raise Failed(UNREAD.format(problem=problem), calls, cost)


def exchange(llm: Callable, nb: Notebook, run: Run, text: Optional[str] = None, data: str = "", look: Optional[Callable] = None,
             recall: Optional[Callable] = None, asked: bool = False, saved: int = 0) -> dict:
    """One exchange in a framing run: the person's message - none on the Architect's first turn, nor when it goes on
    after a round of lookups, a reading or a part opened - and its reply. A reply that cannot be read is asked for
    once more. Returns the framing as it then stands: the brief as one more version when the reply changed a part,
    marked a line or ticked a passage (the Architect's, made from the question, from an answer, or from a check
    against the data), the conversation with both messages, the calls counted. Where the reply asks for lookups,
    `look` answers them - clean lookups in, an answer to each out - and the round is the conversation's last turn:
    the next exchange, with no message, reads it. What the reply proposes enters the brief only where it names a
    column of the data, and a brief takes two proposals in all.

    The question is never written from the reply's brief. A wording the reply gives stands with its message, for
    the person to take; `accept` - the person agreed in words - makes the wording that waited the question, and the
    host makes it the run's.

    The saved analyses are read by `recall(question, the brief as the Architect reads it)`, which gives the reader's
    result: once after a message of the person's, READINGS times in a brief. Where the person asked for it - `asked`,
    their message saying so - they are read at once, and the Architect replies in the next exchange; otherwise where
    the reply asks for it. `saved` is how many there are: the Architect is told, so that it asks only where there
    are some, and the framing keeps the number, so that the page offers a reading only then.

    A part of an analysis the question follows that the reply asks to open is a turn too, OPENS after one message
    of the person's; the next exchange reads the part itself. Where a reply asks for a reading, a part or lookups
    that cannot be had now, it is told so and asked once more, in this exchange: what it then says is kept, and
    what it still asks for is not done.
    Raises Failed; nothing is kept of an exchange that fails."""
    framing = {**(run.framing or {}), "saved": int(saved or 0)}
    turns = list(framing.get("turns") or [])
    if sum(1 for t in turns if t.get("who") == "architect") >= TURNS_MAX:
        raise Failed(SPENT)
    first = not turns and not text
    said = text.strip()[:briefs.QUESTION_CHARS] if isinstance(text, str) else ""
    if said:
        turns.append({"who": "person", "text": said})
    brief = briefs.latest(framing) or {"question": run.question}
    question = brief.get("question") or run.question          # as it stands: the person's own, or a wording of the Architect's they took
    unread = _unread(recall, turns)
    if asked and not unread:
        return _read(framing, turns, brief, recall, question)
    spent = {"open": _since(turns, "opened") >= OPENS, "lookups": _since(turns, "check") >= ROUNDS}
    waits = pending({**framing, "turns": turns})
    as_asked = ((framing.get("versions") or [{}])[0].get("brief") or {}).get("question") or ""
    user = prompt(question, brief, turns, data, earlier(nb, run.id, cells=True), saved, as_asked, unread, waits, opened(nb, run.id, turns))
    got, calls, cost = ask(llm, SYSTEM, user, parse)
    cannot = ([f"a reading of the saved analyses - {unread}"] if got["recall"] and unread else []) \
        + ([OPENED_ALL] if got["open"] and spent["open"] else []) + ([LOOKED_ALL] if got["lookups"] and spent["lookups"] else [])
    if cannot:                                                 # told at once, so that no message says a thing is under way that is not
        try:
            got, more, paid = ask(llm, SYSTEM, user + "\n\n" + NOT_DONE.format(what="; ".join(cannot)), parse)
        except Failed as exc:
            raise Failed(str(exc), calls + exc.calls, cost + exc.cost) from exc
        calls, cost = calls + more, cost + paid
    facts = {f["k"]: (f["about"], f["fact"], f["ran"]) for t in turns if t.get("who") == "check" for f in t.get("found", [])}
    made_before = int(framing.get("proposed") or 0)
    proposals = [p for p in got["propose"] if _grounded(p, data)][:max(0, PROPOSALS - made_before)]
    parts = {**{k: v for k, v in got["brief"].items() if k != "question"}, "propose": proposals}
    if got["accept"] and waits:
        parts["question"] = waits["wording"]                   # the person agreed in words to the wording that waited
    written, changed = briefs.write(brief, parts)
    proposed = sum(1 for c in changed if c.startswith("also_check.") and written["also_check"][int(c.split(".")[1])].get("source") == "architect")
    if proposed:
        framing["proposed"] = made_before + proposed
    written, marked = briefs.mark(written, got["marks"], facts)
    written, ticked = briefs.tick(written, got["tick"])
    if changed or marked or ticked:
        framing = briefs.version(framing, written, by="architect", changed=changed + [c for c in marked + ticked if c not in changed],
                                 why="check" if marked else "question" if first else "answer")
    made = int(framing.get("calls") or 0) + calls
    turns.append({"who": "architect", "text": got["say"], **({"choices": got["choices"]} if got["choices"] else {}),
                  **({"wording": got["wording"]} if got["wording"] else {}),
                  "v": len(framing.get("versions") or []), "cost": round(cost, 4), "call": made})
    if look and got["lookups"] and not spent["lookups"]:
        turns.append(_check(got["lookups"], written, len(facts), look))
    if got["open"] and not spent["open"]:
        turns.append(_opened(nb, run.id, got["open"]))
    framing = {**framing, "turns": turns, "calls": made}
    if got["recall"] and not unread:
        return _read(framing, turns, written, recall, written.get("question") or question)
    return framing
