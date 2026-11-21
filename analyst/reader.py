"""The reader of the saved analyses (docs/ARCHITECT_DESIGN.md §3.2, §3.6).

A person's saved analyses do not fit in a prompt, so a model reads them with code. The view (analyst/memory.py) is
loaded in a sandbox under SAVED, and each reply of the reader's is one action: a cell of Python over it, a question
put to a second model about the runs it names, or its answer. read() runs that loop under the caps. What it returns
has been checked against the view by code: a quote that does not stand, word for word, in the run it is given for
is dropped, and so is a run in a group that the second model never answered for; where a quote stands is found by
code, not said by a model. Nothing here starts a sandbox or calls a model: the caller passes the sandbox's kernel
and both models.
"""
from __future__ import annotations

import json
import os
import re
import time
from typing import Callable, Optional

from analyst.architect import Unreadable, reply_object
from analyst.notebook import hint_lines
from analyst.tools import exception_line

with open(os.path.join(os.path.dirname(__file__), "reader.md"), encoding="utf-8") as _fh:
    SYSTEM = _fh.read().strip()
with open(os.path.join(os.path.dirname(__file__), "reader_pieces.md"), encoding="utf-8") as _fh:
    PIECES = _fh.read().strip()

# one question: the reader's replies; the second model's calls; the time and the money of both; the effort a reply of
# the reader's is asked at - the first the model accepts, never above the seat's own
CAPS = {"turns": 8, "calls": 60, "seconds": 120, "dollars": 0.50, "effort": ("low", "medium")}
OUT_CHARS = 4000                 # of what a cell printed, as the reader is shown it
INDEX = 150                      # runs listed in the prompt, the newest; code reaches the rest
BATCH_CHARS, PIECE_CHARS = 48_000, 16_000      # what one call of the second model reads, and of one run at most
PARTS = ("brief", "report", "conversation", "code", "results", "printed")
FOUND, QUOTE_MIN = 10, 8         # passages in an answer, at most; a quote shorter than this proves nothing
NOTE_CHARS, ANSWER_CHARS, QUESTION_CHARS, LABEL_CHARS = 300, 200, 600, 120
PRELUDE = "import json\nSAVED = json.loads({view!r})\nJUDGED = []"      # the sandbox's first cell: the view as text, so nothing of it is read as code and no file is left behind
LAST = "This is your last reply: ANSWER now, with what you have."
NO_ANSWER = "The reader gave no answer within its limits: {replies} of {turns} replies, {seconds:.0f} s, ${cost:.2f}."
NO_SANDBOX = "The saved analyses could not be put in the sandbox: {error}"
DECLINED = "The model declined to reply ({category})."
SKIPPED = "The person skipped it."


def _line(value, chars: int) -> str:
    return re.sub(r"\s+", " ", value).strip()[:chars] if isinstance(value, str) else ""


def _under(table: dict, key):
    """What stands under a key a model gave: None where it gave none that is there, or no text at all."""
    return table.get(key) if isinstance(key, str) else None


# ------------------------------------------------------------------ the view, for the sandbox
def sandbox_view(view: dict) -> dict:
    """The view as the sandbox gets it: whose data a run ran on is said by a handle - subject 1, subject 2, by first
    appearance - never by the source's id."""
    handles = {}
    for run in view["runs"]:
        subject = run["data"]["subject"]
        if subject and subject not in handles:
            handles[subject] = f"subject {len(handles) + 1}"
    return {**view, "runs": [{**run, "data": {**run["data"], "subject": handles.get(run["data"]["subject"], "")}} for run in view["runs"]]}


# ------------------------------------------------------------------ what stands in the view
def path_cells(view: dict, run: dict) -> list:
    """The cells a run's kernel was built by: those of the earlier steps it was built on - saved or not - and its own,
    in the path's order."""
    by_id = {r["id"]: r for r in view["runs"]}
    steps = [by_id.get(p) or view["steps"].get(p) or {} for p in run["path"]] + [run]
    return [c for s in steps for c in s.get("cells", [])]


def places(view: dict, run: dict) -> list:
    """The places of a run a quote can stand in, each (its name, its text): `question`, `hint` - what the person said
    where they had it go on another way from one of its turns - `report`, `brief` - what was agreed before it ran,
    where it was framed - `conversation` - what was said while it was - then `cell n` for each of path_cells(): a
    cell's code, its result lines and what it printed."""
    return ([("question", run["question"]), *(("hint", h["text"]) for h in run["hints"]), ("report", run["report"]), ("brief", run["brief"]), ("conversation", run["conversation"])]
            + [(f"cell {c['n']}", "\n".join([c["code"], *c["results"], c["printed"]])) for c in path_cells(view, run)])


def place_of(view: dict, run: dict, quote: str) -> Optional[str]:
    """Where a quote stands in a run word for word, the white space between the words aside: the first of its
    places that holds it. None where none does, or where the quote is too short to prove anything."""
    quote = " ".join(quote.split())
    return next((name for name, text in places(view, run) if quote in " ".join(text.split())), None) if len(quote) >= QUOTE_MIN else None


# ------------------------------------------------------------------ the reader's prompt and reply
def prompt(question: str, view: dict, steps: list, said: str, brief: str = "") -> str:
    """What the reader reads for one reply: the question - with the brief the person is writing for it, where there
    is one - the saved runs in a line each, the steps so far with what each brought, and `said`: where the work
    stands and what is asked now."""
    runs = view["runs"]
    lines = [f"{r['id']} | {r['when'][:10]} | {', '.join(r['marks']) or '-'} | {_line(r['question'] or 'Synthesis: ' + r['title'], 160)}" for r in runs[:INDEX]]
    parts = [f"QUESTION:\n{question.strip()}", *([brief.strip()] if brief.strip() else []),
             f"SAVED RUNS: {len(runs)}" + (f", the newest {INDEX} listed" if len(runs) > INDEX else "") + " (id | day | marks | question)\n" + "\n".join(lines)]
    for k, step in enumerate(steps, 1):
        if step["action"] == "cell":
            parts.append(f"[{k}] CELL\n{step['code']}\nPRINTED:\n{step['out'] or '(nothing)'}")
        elif step["action"] == "judge":
            rows = "\n".join(f"- {row['run']} | {row['where']} | {row['answer']} | \"{row['quote']}\"" for row in step["rows"]) or "(no analysis bears on it)"
            facts = [f"Read: {len(step['read'])} of {step['runs']}.", f"Dropped, the quote does not stand there: {step['dropped']}." if step["dropped"] else "",
                     f"Not saved analyses: {', '.join(step['unknown'])}." if step["unknown"] else ""]
            parts.append(f"[{k}] JUDGE {json.dumps(step['asked'], ensure_ascii=False)}\n{' '.join(f for f in facts if f)}\nANSWERS (run | where | answer | quote):\n{rows}")
        else:
            parts.append(f"[{k}] Your reply could not be read: {step['problem']}.")
    return "\n\n".join(parts + [said])


def parse(reply: str) -> tuple:
    """The action of a reply and what it carries: ("cell", the code), ("judge", {runs, parts, question}) or
    ("answer", the object). The action is the first line that is one of the three words; what stands before it is
    passed over. Raises Unreadable."""
    lines = (reply or "").split("\n")
    words = [line.strip().strip("`*#: ").upper() for line in lines]
    at = next((k for k, word in enumerate(words) if word in ("CELL", "JUDGE", "ANSWER")), None)
    if at is None:
        raise Unreadable("no line of it is CELL, JUDGE or ANSWER")
    word, rest = words[at], "\n".join(lines[at + 1:])
    if word == "CELL":
        fenced = re.search(r"```(?:python|py)?[ \t]*\n(.*?)```", rest, re.S)
        code = (fenced.group(1) if fenced else rest).strip()
        if not code:
            raise Unreadable("the CELL holds no code")
        return "cell", code
    if word == "JUDGE":
        obj = reply_object(rest)
        runs, question = obj.get("runs"), _line(obj.get("question"), QUESTION_CHARS)
        if not question or not (runs == "all" or (isinstance(runs, list) and runs and all(isinstance(r, str) for r in runs))):
            raise Unreadable('JUDGE takes {"runs": a list of ids or "all", "parts": [...], "question": "..."}')
        parts = [p for p in PARTS if p in (obj.get("parts") if isinstance(obj.get("parts"), list) else [])] or ["report"]
        return "judge", {"runs": runs, "parts": parts, "question": question}
    return "answer", reply_object(rest)


# ------------------------------------------------------------------ the second model, on pieces
def before(view: dict, run: dict) -> list:
    """The cells a run is read with besides its own: those of the steps right before it that are not saved analyses
    themselves - a run that stopped to ask, one removed since. A saved one before it is read on its own."""
    steps = []
    for step in reversed(run["path"]):
        if step not in view["steps"]:
            break
        steps.insert(0, view["steps"][step])
    return [cell for step in steps for cell in step["cells"]]


def _laid_out(run: dict, cells: list, parts: list) -> str:
    """A run as text: its id, what was asked, the hints it was made under, the title, and the parts named - the brief
    it ran under, the report, the conversation the brief came from, and of each cell given the code, the result
    lines, what was printed."""
    out = [f"=== {run['id']} ===", f"QUESTION: {run['question']}" if run["question"] else "", *hint_lines(run["hints"]),
           f"TITLE: {run['title']}" if run["title"] else ""]
    if "brief" in parts and run["brief"]:
        out.append(f"BRIEF:\n{run['brief']}")
    if "report" in parts:
        out.append(f"REPORT:\n{run['report']}")
    if "conversation" in parts and run["conversation"]:
        out.append(f"CONVERSATION:\n{run['conversation']}")
    for cell in cells:
        held = [("code", cell["code"]), ("results", "\n".join(cell["results"])), ("printed", cell["printed"])]
        out += [f"CELL {cell['n']}, {part}:\n{text}" for part, text in held if part in parts and text.strip()]
    return "\n".join(x for x in out if x)


def piece(view: dict, run: dict, parts: list) -> str:
    """What the second model reads of a run: the parts named, with the cells of before() and its own. Up to
    PIECE_CHARS, the cut said."""
    text = _laid_out(run, before(view, run) + run["cells"], parts)
    return text if len(text) <= PIECE_CHARS else text[:PIECE_CHARS] + "\n... (cut here: the rest was not read)"


def shown(view: dict, run: dict) -> str:
    """A saved analysis whole, for a reader that opens it by name (the analyst's SHOW SAVED k): what was asked, the
    hints it was made under, the title, the brief it ran under, the report, and the code and result lines of
    path_cells() - a passage can stand in any of them, and a name its own cells use may be made in an earlier one.
    Without its id, and not cut: the one who shows it knows what a prompt takes."""
    return _laid_out(run, path_cells(view, run), ["brief", "report", "code", "results"]).split("\n", 1)[1]


def judge(view: dict, asked: dict, call: Callable, room: Callable, on_read: Optional[Callable] = None) -> dict:
    """The second model's answers to one question about the runs asked for, in few large batches: {"asked", "runs":
    how many were asked about, "unknown": the ids asked for that are no saved analyses, "read": the ids of those it
    read, "rows": [{run, answer, quote, where}], "dropped"}. A row stands only where its run was in the batch and
    its quote stands in that run - `where` is the place code found it in; the others are dropped and counted.
    `call(system, user)` gives the model's text; `room()` says whether the caps leave room for one more call, and
    where they do not, the runs not yet read stay unread. A batch whose reply cannot be read is asked for once
    more. `on_read(read, of)` is told after each batch how many of the runs asked about are read."""
    by_id = {r["id"]: r for r in view["runs"]}
    named = list(by_id) if asked["runs"] == "all" else list(dict.fromkeys(asked["runs"]))
    runs = [by_id[i] for i in named if i in by_id]
    batches, out = [[]], {"asked": asked, "runs": len(runs), "unknown": [i for i in named if i not in by_id], "read": [], "rows": [], "dropped": 0}
    for run in runs:
        text = piece(view, run, asked["parts"])
        if batches[-1] and sum(len(t) for _, t in batches[-1]) + len(text) > BATCH_CHARS:
            batches.append([])
        batches[-1].append((run, text))
    for batch in batches if runs else []:
        user, answers = f"YOUR QUESTION:\n{asked['question']}\n\nANALYSES:\n" + "\n\n".join(t for _, t in batch) + "\n\nReply with the JSON object.", None
        for _ in range(2):
            if answers is not None or not room():
                break
            try:
                answers = reply_object(call(PIECES, user)).get("answers")
                answers = answers if isinstance(answers, list) else None
            except Unreadable:
                answers = None
        if answers is None:
            continue
        out["read"] += [run["id"] for run, _ in batch]
        if on_read:
            on_read(len(out["read"]), len(runs))
        here = {run["id"]: run for run, _ in batch}
        for a in answers:
            a = a if isinstance(a, dict) else {}
            run, quote = _under(here, a.get("run")), " ".join(str(a.get("quote") or "").split())
            where = place_of(view, run, quote) if run is not None else None
            if where and _line(a.get("answer"), ANSWER_CHARS):
                out["rows"].append({"run": run["id"], "answer": _line(a.get("answer"), ANSWER_CHARS), "quote": quote, "where": where})
            else:
                out["dropped"] += 1
    return out


# ------------------------------------------------------------------ the answer, checked
def answer(view: dict, obj: dict, judged: list) -> dict:
    """The reader's answer as it stands against the view: {"found": the passages - each with its run's id, thread,
    when, kind, question, title and marks, the data it ran on (name, period, subject), and where, quote, note - "across": {topic, groups: [{label, runs: [{run,
    answer, quote, where}]}]} or None, "dropped": what did not stand}. A passage stands where its quote stands in
    its run, and `where` is the place code found it in. A run stands in a group where the second model answered for
    it with a quote that stood - `judged` holds those rows, and the latest for a run is the one shown - and it
    stands in one group only; a group left without a run, or without a label, is dropped, and so the counts are
    the code's. The label of a group is the reader's."""
    by_id, found, dropped = {r["id"]: r for r in view["runs"]}, [], 0
    for item in obj.get("found") if isinstance(obj.get("found"), list) else []:
        item = item if isinstance(item, dict) else {}
        run, quote = _under(by_id, item.get("run")), " ".join(str(item.get("quote") or "").split())
        where = place_of(view, run, quote) if run is not None else None
        if not where:
            dropped += 1
        elif (run["id"], quote) not in [(f["id"], f["quote"]) for f in found]:
            found.append({**{k: run[k] for k in ("id", "thread", "run", "when", "kind", "question", "title", "marks")}, "data": {k: run["data"][k] for k in ("name", "period", "subject")},
                          **({"broken": True} if run.get("broken") else {}), "where": where, "quote": quote, "note": _line(item.get("note"), NOTE_CHARS)})
    across, rows, placed = obj.get("across") if isinstance(obj.get("across"), dict) else {}, {}, set()
    for row in judged:
        rows[row["run"]] = row
    groups = []
    for group in across.get("groups") if isinstance(across.get("groups"), list) else []:
        group = group if isinstance(group, dict) else {}
        named = list(dict.fromkeys(i for i in group.get("runs") if isinstance(i, str))) if isinstance(group.get("runs"), list) else []
        label = _line(group.get("label"), LABEL_CHARS)
        stand = [rows[i] for i in named if label and i in rows and i not in placed]
        dropped += len(named) - len(stand)
        placed.update(row["run"] for row in stand)
        if stand:
            groups.append({"label": label, "runs": stand})
    return {"found": found[:FOUND], "across": {"topic": _line(across.get("topic"), LABEL_CHARS), "groups": groups} if groups else None, "dropped": dropped}


# ------------------------------------------------------------------ the loop
def read(question: str, view: dict, kernel, llm: Callable, pieces: Callable, caps: Optional[dict] = None, on_step: Optional[Callable] = None,
         clock: Callable = time.time, brief: str = "", stop: Optional[Callable] = None, on_read: Optional[Callable] = None) -> dict:
    """One question put to the saved analyses. `kernel` is the sandbox - a kernel of its own, which gets the view
    under SAVED here; where nothing is saved it is not used, and no model is called. `llm(system, user, effort=)` is
    the reader's model and `pieces(system, user)` the second one, each returning (text, {"cost", "declined"}).
    Returns {"found", "across", "dropped", "coverage": {runs, judged, not_read}, "steps", "calls": {reader, pieces},
    "cost", "seconds", "failed": why there is no answer, or ""}. The caps bound the reader's replies, the second
    model's calls, and the time and the money of both; when the time or the money is spent, or the last reply is
    due, the reader is told to answer with what it has. `brief` is the brief the person is writing for the question,
    as text; `stop()` says the person no longer waits for it - it is asked before each call, and the work ends there
    with nothing found; `on_read(read, of)` follows the second model through the runs."""
    caps, started = {**CAPS, **(caps or {})}, clock()
    steps, judged, read_runs, spent = [], [], set(), {"reader": 0, "pieces": 0, "cost": 0.0}
    over = lambda: clock() - started >= caps["seconds"] or spent["cost"] >= caps["dollars"]      # noqa: E731
    halted = lambda: bool(stop and stop())                                                       # noqa: E731
    room = lambda: spent["pieces"] < caps["calls"] and not over() and not halted()               # noqa: E731

    def second(system: str, user: str) -> str:
        text, usage = pieces(system, user)
        spent["pieces"], spent["cost"] = spent["pieces"] + 1, spent["cost"] + float((usage or {}).get("cost") or 0.0)
        return text

    def done(result: Optional[dict] = None, failed: str = "") -> dict:
        return {**(result or {"found": [], "across": None, "dropped": 0}), "coverage": {"runs": len(view["runs"]), "judged": len(read_runs), "not_read": dict(view.get("not_read") or {})}, "steps": steps,
                "calls": {"reader": spent["reader"], "pieces": spent["pieces"]}, "cost": round(spent["cost"], 4), "seconds": round(clock() - started, 1), "failed": failed}

    def note(step: dict) -> None:
        steps.append(step)
        if on_step:
            on_step(step)

    if not view["runs"]:
        return done()
    _, error, _ = kernel.execute(PRELUDE.format(view=json.dumps(view, ensure_ascii=False)))
    if error:
        return done(failed=NO_SANDBOX.format(error=exception_line(error)))
    for turn in range(1, caps["turns"] + 1):
        if halted():
            return done(failed=SKIPPED)
        last = turn == caps["turns"] or over()
        said = LAST if last else (f"Reply {turn} of {caps['turns']}. The second model has taken {spent['pieces']} of {caps['calls']} calls; "
                                  f"${caps['dollars'] - spent['cost']:.2f} and {int(caps['seconds'] - (clock() - started))} s are left. Reply with one action.")
        reply, usage = llm(SYSTEM, prompt(question, view, steps, said, brief), effort=caps["effort"])
        spent["reader"], spent["cost"] = spent["reader"] + 1, spent["cost"] + float((usage or {}).get("cost") or 0.0)
        if (usage or {}).get("declined"):
            return done(failed=DECLINED.format(category=usage["declined"]))
        try:
            action, body = parse(reply)
        except Unreadable as exc:
            action, body = "unread", str(exc)
        if action == "answer":
            note({"action": "answer"})
            return done(answer(view, body, judged))
        if last:
            break
        if action == "cell":
            out, err, _ = kernel.execute(body)
            shown = "\n".join(x for x in ((out or "").rstrip(), (err or "").rstrip()) if x)
            note({"action": "cell", "code": body, "out": shown if len(shown) <= OUT_CHARS else shown[:OUT_CHARS] + f"\n... ({len(shown) - OUT_CHARS:,} more characters not shown)"})
        elif action == "judge":
            got = judge(view, body, second, room, on_read)
            read_runs.update(got["read"])
            judged += got["rows"]
            kernel.execute("import json\nJUDGED = json.loads(" + repr(json.dumps(judged)) + ")")
            note({"action": "judge", **got})
        else:
            note({"action": "unread", "problem": body})
    return done(failed=NO_ANSWER.format(replies=spent["reader"], turns=caps["turns"], seconds=clock() - started, cost=spent["cost"]))
