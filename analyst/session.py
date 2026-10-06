"""The analyst session: one model, one kernel, one notebook, one report.

    session = Session(kernel, notebook, llm, store, emit=..., recall=..., search=...)
    run = session.run(question, parent=None, budget=Budget(turns=15, dollars=1.0))

Each turn: build the prompt (contract + data + question + note + cells + task),
call the model, parse ONE action, carry it out, store the turn, emit it to the
UI. On long budgets a self-review is asked for at intervals - the same turn, the same
prompt, marked review=True for the caller (the app runs it on the Reviewer seat when the
config has one, a stronger model at the run's decision points). When the analyst
writes REPORT the session asks for the plain-language REWRITE, runs the two
guards, verifies the assembled script in a fresh kernel, and stores the lot.

`llm(system, user) -> (text, usage)` is whatever model layer the host provides.
"""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from . import tools, report as rep
from .notebook import Notebook, NotebookStore, Run, Turn
from .replay import verify

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
_CONTRACT_TEMPLATE = open(os.path.join(_HERE, "contract.md"), encoding="utf-8").read()
# the documents' section and the READ row of the actions table ride only when the thread has documents
CONTRACT_DOCUMENTS = open(os.path.join(_HERE, "contract_documents.md"), encoding="utf-8").read()
# the Reviews section rides only when a reviewer runs during the run (Adaptive), naming the cadence; the reviewer has its
# own prompt and never sees the analyst's (2026-10-05)
CONTRACT_REVIEWS = open(os.path.join(_HERE, "contract_reviews.md"), encoding="utf-8").read()
REVIEWER = open(os.path.join(_HERE, "reviewer.md"), encoding="utf-8").read()
REPORT_NOW = "The review found the answer established: this turn is the report. Write REPORT now."
REVIEW_EVIDENCE_CHARS = 20_000   # the cells handed to one review, code and output, up to this (2026-10-06: one call a
                                 # review; the session picks the cells, the reviewer asks for nothing)
REVIEW_OPEN_CHARS = 6_000        # a cell's output as the reviewer sees it, whole up to this
READ_ROW = ("| `READ D1 <what>` | Quote the passages of document 1 that answer. `READ ALL <what>`: every document. "
            "`READ D1.35-41 <what>` or `READ D1 p.7-9 <what>`: that stretch. |\n")


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def contract(documents: bool = False, review_every: int = 0) -> str:
    """The contract as the model reads it: one page, each rule once; with documents, the Documents section before
    Format and the READ row in the actions table; with reviews during the run, the Reviews section after Results."""
    return (_CONTRACT_TEMPLATE.replace("{DOCUMENTS}", "\n" + CONTRACT_DOCUMENTS if documents else "")
                              .replace("{READ_ROW}", READ_ROW if documents else "")
                              .replace("{REVIEWS}", "\n" + CONTRACT_REVIEWS.replace("{ordinal}", _ordinal(review_every))
                                       if review_every else ""))

CONTRACT = contract(False)

LAST_TURNS_LINE = "The budget is nearly gone: write REPORT with what you have, and say what was not established."
SHOW_VIEW_CHARS = 40_000     # a SHOW of several cells at once rides whole up to this; beyond it the middle goes, as for a digest
                             # (2026-10-03: an 87,000-character view of several cells was sent whole to a 64k-token server)
SHOWN_RUNS_CHARS = 60_000    # the runs SHOW RUN re-opened stay in the prompt for the rest of the run, whole, while together they fit
                             # this; beyond it the oldest collapse to a line each (2026-10-03: a count of three kept a five-chain
                             # synthesis cycling - ten of its fourteen turns re-opened runs it had already shown)
FIGURE_CELLS_MAX = 3         # figure cells a run may commit; the contract says one to three figures
DIGEST_VIEW_CHARS = 12_000   # a search or read digest rides into the next prompt whole, like the newest cell's output; a longer one
                             # is cut from the middle at line ends so its top and its SUMMARY both survive. The record keeps all.

IDEAS_SYSTEM = ("You propose the next questions for a data analysis thread. You know the dataset and the chains so far from the "
                "message. You do not run code and you do not analyse; you write five follow-up questions at the variation level asked, "
                "as a numbered list, each item a short bold title, a colon, and the question - and nothing else around the list.")

REWRITE_TASK = ("Rewrite the technical report below for an intelligent reader who has never studied statistics and "
                "does not know this dataset: the answer first in everyday words, then what it depends on and what it "
                "does not mean, then how it was checked, then what to do next. Explain each idea the first time it "
                "appears. No column names, no method jargon, no bracketed intervals - give ranges in words "
                "('somewhere between 2 and 5'). Keep every number that matters and change none; drop the rest. Use short markdown "
                "headings and short paragraphs; about two-thirds the length of the original. Say what you mean in "
                "direct statements: when a literal phrase is available, use it, and never let a metaphor or a flourish "
                "stand in for a statement ('this still matters', not 'this earns its keep'; 'a parameter worth varying', "
                "not 'a dial worth turning'). Reply with the text only.\n\n")

_NOTE_RE = re.compile(r"###NOTE###\s*\n(.*?)\n###ACTION###", re.S)


_NOTE_LINE_RE = re.compile(r"^(\s*[-•]\s*)\**\s*([^:*]{2,60}?)\s*\**\s*:\s*\**\s*(.*?)\s*\**\s*$")


def clean_note(note: str) -> str:
    """The note as every reader expects it - '- Heading: content' - whatever a model wrapped the heading or its
    content in (2026-10-04: '- **Best estimate so far:** ...' reached the pane's table and the strip as written)."""
    out = []
    for ln in (note or "").splitlines():
        m = _NOTE_LINE_RE.match(ln)
        out.append(f"{m.group(1)}{m.group(2)}: {m.group(3)}" if m else ln)
    return "\n".join(out)


_REVIEW_HEADS = (("requires", "The question requires"), ("established", "Established"),
                 ("problem", "Most consequential problem"), ("verdict", "Verdict"))
_REVIEW_LISTS = (("checked", "Checked"), ("recheck", "Re-check"))      # may appear several times; kept as lists
_REVIEW_LENSES = (("identification", "Identification"), ("alternative", "Alternative explanation"), ("heterogeneity", "Heterogeneity"),
                  ("measurement", "Measurement"), ("frame", "The question's frame"))   # the perspectives (2026-10-06), one line each


def parse_review(text: str) -> Optional[dict]:
    """A reviewer's reply to {requires, established, problem, verdict, arg, lines}; None when it names no verdict.
    Tolerant of bold markers, bullets, and a field's text running on to further lines."""
    t = text or ""
    # the review is the text after the last marker that has a verdict after it (2026-10-06: a reply ended with a stray
    # "###REVIEW###" after a complete review, and the text after the last marker was empty)
    if "###REVIEW###" in t:
        starts = [m.end() for m in re.finditer(r"###REVIEW###", t)]
        with_verdict = [i for i in starts if re.search(r"^\s*[-•*]?\s*\**Verdict\**\s*:", t[i:], re.M | re.I)]
        t = t[(with_verdict[-1] if with_verdict else starts[-1]):]
    fields, lists, current = {}, {key: [] for key, _ in _REVIEW_LISTS}, None
    for ln in clean_note(t).splitlines():
        s_ = ln.strip().lstrip("-•* ").strip()
        hit = next((key for key, head in _REVIEW_HEADS + _REVIEW_LISTS + _REVIEW_LENSES
                    if s_.lower().startswith(head.lower()) and ":" in s_[len(head):len(head) + 3]), None)
        if hit in lists:
            current = hit
            lists[hit].append(s_.split(":", 1)[1].strip())
        elif hit:
            current = hit
            fields[hit] = s_.split(":", 1)[1].strip()
        elif current in lists and s_:
            lists[current][-1] = (lists[current][-1] + " " + s_).strip()
        elif current and s_:
            fields[current] = (fields[current] + " " + s_).strip()
    m = re.match(r"(TEST|NARROW|REPORT)\b[\s:.\-\u2013\u2014]*(.*)", fields.get("verdict", "").replace("*", "").strip(), re.I | re.S)
    if not m:
        return None
    rv = {key: fields.get(key, "") for key, _ in _REVIEW_HEADS}
    rv["lenses"] = [(head, fields[key].strip()) for key, head in _REVIEW_LENSES
                    if fields.get(key, "").strip() and fields[key].strip().rstrip(".").lower() not in ("nothing", "none", "-", "n/a")]
    rv["verdict"], rv["arg"] = m.group(1).upper(), m.group(2).strip()
    # Checked lines, one per cell: "cell 12 - what the code computes; matches its line" -> (12, text); Re-check: cells
    rv["checked"] = [(int(mm.group(1)), mm.group(2).strip(" -:")) for c in lists["checked"]
                     for mm in [re.match(r"\s*cells?\s*(\d+)\s*(.*)", c, re.I | re.S)] if mm]
    rv["recheck"] = sorted({int(n) for c in lists["recheck"] for n in re.findall(r"\d+", c)})
    rv["lines"] = "\n".join([f"- The question requires: {rv['requires']}", f"- Established: {rv['established']}"]
                            + [f"- Checked: cell {c} - {t}" for c, t in rv["checked"]]
                            + [f"- {head}: {t}" for head, t in rv["lenses"]]      # the perspectives that found something ride to the analyst
                            + [f"- Most consequential problem: {rv['problem']}", f"- Verdict: {rv['verdict']} {rv['arg']}".rstrip()]
                            + ([f"- Re-check: {', '.join(f'cell {c}' for c in rv['recheck'])}"] if rv["recheck"] else []))
    return rv


def checked_ok(text: str) -> bool:
    """A reviewer's Checked line read as a verdict on the cell: it does not describe its code when the line says "does not"
    and never says "matches" (the brief's form: "matches its line | does not: how")."""
    t = (text or "").lower()
    return not ("does not" in t and "matches" not in t)


def disputed_cells(run) -> Dict[int, str]:
    """Cells an earlier review found not to describe their code - cell -> the review's label - from the Checked lines on
    the review turns (the latest review's word on a cell stands). A line of such a cell is marked in the ledger, and a
    report that cites the cell is flagged (2026-10-06: a review had caught a typed line and the report quoted it anyway)."""
    out: Dict[int, str] = {}
    for x in run.turns:
        if x.kind == "review":
            for rec in x.checked or []:
                c = int(rec["cell"])
                if rec.get("ok", True):
                    out.pop(c, None)
                else:
                    out[c] = x.text
    return out


def cited_cells(text: str) -> List[int]:
    """Cell numbers a review cites: [cell 11], [cells 11, 13], [cell 11, cell 13], cell 11."""
    nums = []
    for m in re.finditer(r"\bcells?\s+(\d+(?:\s*(?:,|and|&|/)\s*(?:cells?\s*)?\d+)*)", text or "", re.I):
        nums += [int(n) for n in re.findall(r"\d+", m.group(1)) if int(n) not in nums]
    return nums


def review_note(rv: dict) -> str:
    """The review after the report, as the note the reader sees under it."""
    req, arg, problem = rv["requires"].rstrip(" ."), rv["arg"].rstrip(" ."), rv["problem"].rstrip(" .")
    checked, cited = rv.get("checked_cells") or [], rv.get("cited") or []
    seen = [c for c in cited if c in checked]
    unseen = [c for c in cited if c not in checked]
    read = (f" Checked against the code of {', '.join(f'cell {c}' for c in seen)}." if seen else "") + (
        f" Not checked: {', '.join(f'cell {c}' for c in unseen)}." if unseen else "")
    if rv["verdict"] == "REPORT":
        caution = "" if problem.lower() in ("", "none", "nothing") else f" One caution: {problem}."   # 2026-10-06: a REPORT verdict had found a misstated bound and the note did not say so
        return f"**Reviewer's note.** The question requires: {req}. The report answers it as asked" + (f": {arg}." if arg else ".") + caution + read
    if rv["verdict"] == "TEST":
        return f"**Reviewer's note.** The question requires: {req}. Not established: {problem}. The analysis that would settle it: {arg}.{read}"
    return f"**Reviewer's note.** The question requires: {req}. {problem}. The evidence supports a narrower conclusion: {arg}.{read}"


def _first_line(text: str, cap: int = 110) -> str:
    ln = next((x.strip() for x in (text or "").splitlines() if x.strip()), "")
    return ln if len(ln) <= cap else ln[:cap - 3] + "..."




def _first_sentence(text: str, cap: int = 160) -> str:
    sent = re.split(r"(?<=[.!?])\s", (text or "").strip(), maxsplit=1)[0]
    return sent if len(sent) <= cap else sent[:cap - 3] + "..."


def result_records(run):
    """(cell number, record) for every RESULT(...) the run's committed cells recorded, in order."""
    return [(x.cell_no, r) for x in run.cells() for r in (x.results or [])]


def result_lines(run, omit=()) -> List[str]:
    """The ledger: one line per RESULT(...) a committed cell recorded, with its cell number - the record of what is
    established, kept whole in every prompt whatever the window does to the cells (2026-10-05: a run spent two cells
    locating the specification behind a number it had printed twenty turns earlier). The lines come from the kernel's
    records, not from printed text (2026-10-06: a printed line can carry numbers nobody computed; the kernel marks
    those). A line a later cell corrected - RESULT(..., corrects=14) - is marked, so a known-wrong line stops reading
    as evidence."""
    rows = result_records(run)
    corrected = {}
    for c, r in rows:
        cs = r.get("corrects")
        for n in (cs if isinstance(cs, (list, tuple)) else ([cs] if cs is not None else [])):
            if int(n) != c:
                corrected.setdefault(int(n), c)
    disputed = disputed_cells(run)
    return [f"- [cell {c}] " + (f"(corrected by cell {corrected[c]}) " if c in corrected else "")
            + (f"(the review {disputed[c]} found this line does not describe its code) " if c in disputed else "") + r["text"]
            for c, r in rows if c not in omit]      # omit: cells whose output is in view whole, so the line is not shown twice


def evidence_text(turn) -> str:
    """A cell's output as evidence for the report guard: without the RESULT lines whose numbers were typed into the
    call (they are claims, printed), so a report that quotes them is flagged as not traced to a computed output."""
    typed = {("RESULT: " + r["text"]).strip() for r in (turn.results or []) if r.get("typed")}
    return "\n".join(ln for ln in (turn.stdout or "").splitlines() if ln.strip() not in typed)


def evidence_code(turn) -> str:
    """A cell's code as evidence for the report guard (its thresholds and parameters are numbers a report may quote):
    without the RESULT(...) calls when any of them typed its numbers in, so those literals are not evidence either."""
    if not any(r.get("typed") for r in (turn.results or [])):
        return turn.code or ""
    return "\n".join(ln for ln in (turn.code or "").splitlines() if "RESULT(" not in ln)


def _estimate_line(note: str) -> str:
    """The note's 'Best estimate so far' content, for the pane's strip."""
    for ln in (note or "").splitlines():
        s = ln.strip().lstrip("-• ").strip()
        if s.lower().startswith("best estimate so far"):
            return s.split(":", 1)[1].strip() if ":" in s else ""
    return ""


@dataclass
class Budget:
    turns: int = 15
    dollars: float = 2.0
    review_every: int = 0       # 0 = no self-review turns; long budgets use 8
    max_failures: int = 5       # consecutive failed cells before the session forces the report
    searches: int = 4           # web searches per run; beyond it SEARCH answers with what is already on hand
    reads: int = 3              # document reads per run, the same way (docs/DOCUMENTS_DESIGN.md)

    @staticmethod
    def preset(name: str) -> "Budget":
        return {"quick": Budget(turns=5, dollars=0.3),
                "deep": Budget(turns=15, dollars=1.5),
                "adaptive": Budget(turns=50, dollars=4.0, review_every=8)}[name]


@dataclass
class Action:
    verb: str          # cell | show | names | recall | search | read | ask | report | invalid
    arg: str = ""      # code, cell number, query, question or the report text
    more: tuple = ()   # the further actions a reply carried after this one, which did not run (2026-10-03)


def _draws_figure(code: str) -> bool:
    """A cell that draws a figure the reader will see: a Plotly fig.show() or a matplotlib show/savefig."""
    return bool(re.search(r"\.show\(|plt\.savefig\(|\.write_image\(|\.write_html\(", code or ""))


def view_digest(text: str, how_to_see_all: str, cap: int = DIGEST_VIEW_CHARS) -> str:
    """A digest as the next prompt shows it: whole, unless it is longer than the safety cap, in which case
    the middle goes - at line ends, keeping the first part (the top claims or passages) and the last (the
    SUMMARY) - with a marker that says how much and how to see it all."""
    text = text or ""
    if len(text) <= cap:
        return text
    head_budget, tail_budget = int(cap * 0.6), int(cap * 0.35)
    head = text[:head_budget]
    head = head[:head.rfind("\n")] if "\n" in head else head
    tail = text[-tail_budget:]
    tail = tail[tail.find("\n") + 1:] if "\n" in tail else tail
    omitted = len(text) - len(head) - len(tail)
    return head.rstrip() + f"\n... [{omitted} characters omitted from the middle for length; {how_to_see_all}] ...\n" + tail.lstrip()


def parse_turn(text: str) -> tuple[str, str, Action]:
    """(thinking, note, action). A reply carries one action. Every action in every ###ACTION### block is found; the first
    runs, and any different ones after it are recorded in `more` so the next prompt can say they did not run (2026-10-05:
    the rule 'the last complete action' had run a four-line restart of imports in place of a 69-line cell; refusing the
    whole reply then cost a turn each time). The same action written twice runs once; a bare marker, or one with an
    unfinished action under it, carries none. The note and the thinking are the last written before the action taken."""
    text = text or ""
    if not text.strip():
        return "", "", Action("invalid", "empty reply")
    marks = [m.start() for m in re.finditer(r"###ACTION###", text)]
    if not marks:
        m_note = _NOTE_RE.search(text)
        note = clean_note(m_note.group(1).strip()) if m_note else ""
        thinking = text[:text.find("###NOTE###")].strip() if "###NOTE###" in text else ""
        thinking = re.sub(r"^###THINKING###\s*", "", thinking).strip()
        return thinking, note, Action("invalid", "no ###ACTION### block")
    found, reasons = [], []
    for k, pos in enumerate(marks):
        body = text[pos + len("###ACTION###"):(marks[k + 1] if k + 1 < len(marks) else len(text))]
        acts, why = _actions_in(body)
        found.extend((k, a) for a in acts)
        if why:
            reasons.append(why)
    distinct = []
    for k, a in found:
        if all((a.verb, a.arg.strip()) != (d.verb, d.arg.strip()) for _, d in distinct):
            distinct.append((k, a))
    if distinct:
        # several different actions: the first runs and the rest are named as not run (2026-10-06, Palo: refusing the
        # reply had cost one or two turns a run - the first two turns of a Deep run, both restarts - and a lost turn is
        # the certain cost, a draft that runs the occasional one)
        chosen, first = distinct[0]
        action = Action(first.verb, first.arg, more=tuple(a.verb for _, a in distinct[1:]))
    else:
        chosen = len(marks) - 1
        action = Action("invalid", reasons[-1] if reasons else "no action under ###ACTION###")
    head = text[:marks[chosen]]
    last_note = head.rfind("###NOTE###")
    note_text = head[last_note + len("###NOTE###"):] if last_note >= 0 else ""
    cut = note_text.find("###ACTION###")                    # the note ends where an earlier action began
    note = clean_note((note_text[:cut] if cut >= 0 else note_text).strip())
    think_end = last_note if last_note >= 0 else len(head)
    last_think = head.rfind("###THINKING###", 0, think_end)
    thinking = head[last_think + len("###THINKING###"):think_end].strip() if last_think >= 0 else head[:think_end].strip()
    return thinking, note, action


_ACTION_WORD_RE = re.compile(r"^\s*(CELL|SHOW|NAMES|RECALL|SEARCH|READ|ASK|REPORT)\b[ \t]*(.*)$")          # as the contract writes them
_ACTION_WORD_ANY_CASE_RE = re.compile(r"^\s*(cell|show|names|recall|search|read|ask|report)\b[ \t]*(.*)$", re.I)


def _actions_in(body: str):
    """The actions one ###ACTION### block carries, in order, and why it carries none. A python fence is a cell, with or
    without the word CELL before it; an action word at the start of a line, outside a fence, is that action (any case on
    the block's first line, upper case after it, so prose is not read as an action); after REPORT the rest of the block
    is the report. A fence without its closing line is not a cell: unfinished code does not run."""
    body = re.sub(r"\A\s*```[ \t]*\n\s*CELL\s*\n```[ \t]*\n", "CELL\n", body or "")    # a fenced CELL word is the word
    lines = body.strip("\n").splitlines()
    acts, i, first, cell_word, unclosed = [], 0, True, False, False
    first_text = next((x.strip() for x in lines if x.strip()), "")
    while i < len(lines):
        ln = lines[i]
        if ln.strip().startswith("```"):
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            if j >= len(lines):
                unclosed = True
                break
            lang, code = ln.strip()[3:].strip().lower(), "\n".join(lines[i + 1:j]).rstrip()
            if lang in ("", "python", "py", "python3") and code.strip():
                acts.append(Action("cell", code))
            i, first = j + 1, False
            continue
        m = _ACTION_WORD_RE.match(ln) or (_ACTION_WORD_ANY_CASE_RE.match(ln) if first else None)
        if m:
            verb, arg = m.group(1).lower(), m.group(2).strip()
            first = False
            if verb == "cell":
                cell_word = True                                     # its fence follows
            elif verb == "report":
                acts.append(Action("report", "\n".join(lines[i + 1:]).strip()))
                return acts, ""
            elif verb == "ask":
                tail = []
                for ln2 in lines[i + 1:]:
                    if not ln2.strip() or _ACTION_WORD_RE.match(ln2) or ln2.strip().startswith(("###", "```")):
                        break
                    tail.append(ln2)
                i += len(tail)
                acts.append(Action("ask", (arg + "\n" + "\n".join(tail)).strip()))
            elif verb == "names":
                acts.append(Action("names"))
            elif verb == "show":
                if not arg:
                    nxt = next((x.strip() for x in lines[i + 1:] if x.strip()), "")
                    arg = nxt.split()[0] if nxt else ""
                acts.append(Action("show", arg))
            else:                                                    # recall, search, read: the query is its one line
                acts.append(Action(verb, arg))
        elif ln.strip():
            first = False
        i += 1
    if acts:
        return acts, ""
    if unclosed:
        return acts, "a python block without its closing fence"
    if cell_word:
        return acts, "CELL without a python block"
    return acts, f"unknown action {first_text[:40]!r}"


class Session:
    def __init__(self, kernel, notebook: Notebook, llm: Callable, store: Optional[NotebookStore] = None,
                 emit: Optional[Callable[[dict], None]] = None, recall: Optional[Callable] = None,
                 search: Optional[Callable] = None, data_description: str = "",
                 kernel_factory: Optional[Callable[[], object]] = None,
                 replay_runner: Optional[Callable] = None, read: Optional[Callable] = None,
                 unit_text: Optional[Callable[[str], Optional[str]]] = None, kernel_prelude: str = "", documents: bool = False):
        self.kernel = kernel
        self.nb = notebook
        self.llm = llm            # llm(system, user, **hints) -> (text, usage); hints: review=True on a self-review turn, rewrite=True on the plain-language rewrite
        self.store = store
        self.emit = emit or (lambda ev: None)
        self.recall = recall
        self.search = search
        self.data_description = data_description or "(no dataset attached)"
        self.kernel_factory = kernel_factory
        self.replay_runner = replay_runner      # (run, script) -> (stdout, error); the host may also collect figures
        self.read = read                        # read(arg) -> digest text over the thread's documents, or None when the host has none
        self.unit_text = unit_text              # unit_text("D1.17") -> the unit's text, for the report guard; None when unknown
        self.kernel_prelude = kernel_prelude    # source the host wants in the kernel (the document objects): run committed at the
                                                # start of a run and again after a rollback, never a cell of the record
        self.documents = documents
        self.system = contract(documents)      # the documents' section and the READ row only when there are documents

    # ----- the prompt --------------------------------------------------------
    @staticmethod
    def is_review(budget: Budget, turn_no: int) -> bool:
        """A review comes before this turn: never before the first; after every review_every turns (before turns 9, 17,
        25... for 8)."""
        return bool(budget.review_every) and turn_no > 1 and (turn_no - 1) % budget.review_every == 0

    def _shown_runs(self, run: Run) -> str:
        """The earlier chains SHOW RUN re-opened in this run, standing in the prompt for the rest of it (2026-10-03: a
        SHOW lived one turn, and a synthesis that needed three chains in view re-opened them twenty-seven times). The
        shown runs whole, in the order they were shown, while together they fit SHOWN_RUNS_CHARS; the oldest beyond that as a line each."""
        order: List[int] = []                                      # run numbers in order of their latest showing
        texts: dict = {}
        for i, x in enumerate(run.turns, 1):
            if x.kind == "show" and x.text and (x.stdout or "").startswith("--- run "):
                for m in re.finditer(r"(?ms)^--- run (\d+) ---\n.*?(?=^--- run \d+ ---|\Z)", x.stdout):
                    k = int(m.group(1))
                    if k in order:
                        order.remove(k)
                    order.append(k); texts[k] = (m.group(0).strip(), i)
        if not order:
            return ""
        whole, older, size = [], [], 0
        for k in reversed(order):                                  # newest first, whole while they fit
            n = len(texts[k][0])
            if not whole or size + n <= SHOWN_RUNS_CHARS:
                whole.insert(0, k); size += n
            else:
                older.insert(0, k)
        parts = ["RUNS SHOWN THIS RUN (they stay here; SHOW RUN k re-opens an older one):"]
        for k in older:
            parts.append(f"(run {k} was shown at turn {texts[k][1]}; SHOW RUN {k} brings it back whole)")
        for k in whole:
            parts.append(view_digest(texts[k][0], "the notebook keeps it whole", cap=SHOW_VIEW_CHARS))
        return "\n".join(parts)

    def _user_prompt(self, run: Run, budget: Budget, turn_no: int, spent: float, extra: str = "",
                     everything: bool = False, tail: str = "") -> str:
        left = budget.turns - turn_no
        # the last turn itself (2026-10-06: at left <= 1 the model reported a turn early, every run, and Deep had 14 working
        # turns of 15); the forced report after the loop is the safety net if the model does not report here
        last = (left <= 0 and turn_no > 1) or spent >= 0.9 * budget.dollars      # never on the first turn: even a tiny budget gets one cell
        # the report turn sees everything (2026-09-10): once the session forces the report there is no turn left to
        # SHOW a cell, and a result the report cannot see does not exist for the reader
        everything = everything or last
        parts = []
        anc = self.nb.render_ancestry(run.id)
        if anc:
            parts.append(anc)
            shown = self._shown_runs(run)
            if shown:
                parts.append(shown)
        parts.append(f"DATA:\n{self.data_description}")
        parts.append(f"QUESTION:\n{run.question.strip()}")
        parts.append(f"YOUR NOTE (as you last wrote it):\n{run.note or '(none yet - write it this turn)'}")
        parts.append("CELLS SO FAR:\n" + self.nb.render_cells(run.id, everything=everything))
        shown_whole = {run.cells()[-1].cell_no} if run.cells() and not everything else set()   # the newest cell rides whole
        results = result_lines(run, omit=shown_whole)
        if results:
            parts.append("RESULTS SO FAR (printed by your cells; the report quotes these):\n" + "\n".join(results))
        # the passages this run's reads returned stay in view for the rest of the run - the lines with their ids, as a
        # cell's output stays as a line: the evidence the report may quote, whenever it is written
        passages = [ln for x in run.turns if x.kind == "read" for ln in (x.stdout or "").splitlines() if ln.startswith("- [")]
        if passages:
            parts.append("PASSAGES THIS RUN'S READS RETURNED (verbatim, each with its id - cite one as [D1.17]):\n" + "\n".join(passages))
        if extra:
            parts.append(extra)
        block = self._review_block(run)
        if block:
            parts.append(block)                     # the latest review stands above the task line until the next one
        if tail:
            parts.append(tail)
        # the limit, not a countdown (2026-10-05: "turn 31 of 48 (17 left)" read as turns to fill, and a run that had its
        # finding at turn 13 reported at 47)
        task = f"TASK: turn {turn_no}; up to {budget.turns} turns and ${budget.dollars:.2f} (spent ${spent:.2f})."
        if last:
            task += "\n" + LAST_TURNS_LINE
        parts.append(task)
        return "\n\n".join(parts)

    # ----- the loop ----------------------------------------------------------
    # ---- ideas: five next questions, one model call, no cells (2026-09-08) ----
    IDEAS_LEVELS = {1: "refine the focus - scope, granularity or a parameter within the same enquiry",
                    2: "shift the angle - the same subject from a different perspective or framework",
                    3: "test the boundaries - what happens at the edges of the current assumptions",
                    4: "blend two elements already in the thread in a new way",
                    5: "follow what emerged unexpectedly in the investigation"}

    @staticmethod
    def _ideas_list(text: str) -> str:
        """The five items and nothing else: whatever the model wrapped around them (a reply in the
        contract's three-section form, an opening paragraph, a closing remark) is dropped."""
        text = text or ""
        if "###ACTION###" in text:                                  # the analyst's format slipped in
            text = text.split("###ACTION###", 1)[1]
            text = re.sub(r"^\s*REPORT\s*", "", text)
        items, cur = [], None
        for line in text.splitlines():
            m = re.match(r"^\s*(\d+)[.)]\s+(.*)$", line)
            if m:
                if cur: items.append(cur)
                cur = m.group(2).strip()
            elif cur is not None and line.strip():
                cur += " " + line.strip()
            elif cur is not None and not line.strip():
                items.append(cur); cur = None
        if cur: items.append(cur)
        items = [i for i in items if i][:5]
        return "\n".join(f"{n}. {i}" for n, i in enumerate(items, 1))

    def ideas(self, level: int, parent: Optional[str] = None, run_id: Optional[str] = None, question: str = "") -> Run:
        """Five follow-up questions one step from the thread, at the asked variation level.
        A single model call over the thread's ledger and the data description: no cells,
        no replay, no rewrite. The run is recorded like any other, so the map shows it."""
        level = max(1, min(5, int(level or 3)))
        run = self.nb.new_run(question or f"User requested variations of the enquiry (level {level})", parent, run_id=run_id)
        self._save()
        self.emit({"type": "turn_start", "run": run.id, "turn": 1, "of": 1})
        t0 = time.time()
        ledger = self.nb.render_ancestry(run.id) if parent else ""
        prompt = (f"DATA:\n{self.data_description}\n\n" + (ledger + "\n\n" if ledger else "") +
                  "TASK: Propose five follow-up questions for this thread, all at variation level " + str(level) + ": " + self.IDEAS_LEVELS[level] + ".\n"
                  "Each is ONE step from where the thread is now: built from elements already present in the chains and the data, "
                  "answerable with this dataset, specific enough to run as the next chain. Prefer subtle over dramatic; small shifts reveal large insights.\n"
                  "Reply with the five as a numbered list and NOTHING else - no introduction, no closing remark, no headings, no notes. "
                  "Each item: **a short title** then a colon and the question in one or two sentences. Plain text; no LaTeX.")
        text, usage = self.llm(IDEAS_SYSTEM, prompt)
        text = self._ideas_list(text)
        cost = (usage or {}).get("cost", 0.0)
        self.emit({"type": "turn_end", "run": run.id, "turn": 1, "kind": "ideas", "thinking": "", "note": "", "code": "",
                   "elapsed": round(time.time() - t0, 1), "cost": cost})
        run.turns.append(Turn(kind="ideas", text=text, usage=dict(usage or {}),
                              note="- Question as understood: five next questions for the thread\n- Names: (no cells; the kernel is untouched)"))
        run.report = text if text else "(no ideas returned)"
        run.status = "answered" if text else "failed"
        self._save()
        self.emit({"type": "run_end", "run": run.id, "status": run.status})
        return run

    def run(self, question: str, parent: Optional[str] = None, budget: Budget = Budget(),
            run_id: Optional[str] = None) -> Run:
        run = self.nb.new_run(question, parent, run_id=run_id)
        self._save()
        spent, extra, failures = 0.0, "", 0
        self.system = contract(self.documents, budget.review_every)    # the Reviews section only when a reviewer runs
        final_turn, final_extra, forced_by_review = budget.turns, LAST_TURNS_LINE + "\nWrite REPORT now.", False
        tools.run_prelude(self.kernel, self.kernel_prelude)        # the document objects, when the thread has documents
        for turn_no in range(1, budget.turns + 1):
            if self.is_review(budget, turn_no):
                # the reviewer: its own prompt and input, no actions; its review rides in the analyst's next prompts, and a
                # REPORT verdict ends the analysis (2026-10-05: the self-review had been the analyst's own turn with one
                # line added, and continued the analysis five times in five)
                rv, cost = self._review(run, budget, after_turn=turn_no - 1)
                spent += cost
                if rv is not None and rv["verdict"] == "REPORT" and rv.get("binding"):
                    final_turn, final_extra, forced_by_review = turn_no, extra, True
                    break
            self.emit({"type": "turn_start", "run": run.id, "turn": turn_no, "of": budget.turns})
            t0 = time.time()
            text, usage = self.llm(self.system, self._user_prompt(run, budget, turn_no, spent, extra))
            usage = dict(usage or {})
            usage["elapsed"] = round(time.time() - t0, 1)
            spent += float(usage.get("cost", 0.0) or 0.0)
            thinking, note, action = parse_turn(text)
            note = note or run.note
            extra = ""
            turn = Turn(kind=action.verb, note=note, thinking=thinking, usage=usage)
            held = (f"(Your reply held {len(action.more) + 1} actions - {action.verb.upper()} then "
                    f"{', '.join(v.upper() for v in action.more)}; only the first ran. A reply carries one action.)") if action.more and action.verb != "report" else ""
            self.emit({"type": "turn_end", "run": run.id, "turn": turn_no, "kind": action.verb,
                       "thinking": thinking, "note": note, "code": action.arg if action.verb == "cell" else "",
                       "elapsed": usage.get("elapsed"), "cost": usage.get("cost", 0.0),
                       "estimate": _estimate_line(note)})

            if action.verb == "cell" and _draws_figure(action.arg) and sum(1 for x in run.cells() if _draws_figure(x.code)) >= FIGURE_CELLS_MAX:
                # the cap on figure cells (2026-10-05: a run drew nine, three of them failing, with its finding in hand
                # since turn 13): the cell is not run, and the reply says why and what to do instead
                turn.code = action.arg
                turn.stdout = (f"(Figure limit: {FIGURE_CELLS_MAX} figure cells a run, and this run has drawn {FIGURE_CELLS_MAX}. "
                               "This cell was not run. Cite the figures already drawn as [fig n]; if the cell also computed "
                               "something the answer needs, write that part again without the figure.)")
                extra = turn.stdout
            elif action.verb == "cell":
                turn.code = action.arg
                t_cell = time.time()
                self.emit({"type": "cell_start", "run": run.id, "turn": turn_no})   # the executor is busy from here (2026-09-08)
                out, err, figs, recs = tools.run_cell(self.kernel, action.arg)
                turn.elapsed = round(time.time() - t_cell, 1)
                turn.stdout, turn.error, turn.figures, turn.results = out, err, figs, recs
                if not err:
                    turn.cell_no = self.nb.next_cell_no(run.id)
                    failures = 0
                else:
                    failures += 1
                    tools.rebind_aliases(self.kernel)          # a rollback on an older kernel loses pd/np/plt
                    tools.run_prelude(self.kernel, self.kernel_prelude)      # ... and the document objects
                    extra = ("YOUR LAST CELL FAILED - it was rolled back, nothing it defined persists:\n"
                             f"```python\n{action.arg.rstrip()}\n```\nERROR:\n{tools.condense_error(err, code=action.arg)}")
                    if failures >= 2:
                        extra += (f"\n\n{failures} attempts in a row have failed.")
                    if budget.max_failures and failures >= budget.max_failures:
                        # five in a row is a model looping, not analysing: close with what stands
                        logger.warning("Analyst: %d consecutive failed cells; forcing the report", failures)
                        run.turns.append(turn)
                        self._emit_turn(run, turn)
                        self.emit({"type": "heartbeat", "run": run.id, "turn": turn_no, "of": budget.turns, "spent": spent,
                                   "dollars": budget.dollars, "estimate": _estimate_line(run.note)})
                        self._save()
                        halt = (f"STOP: {failures} cells in a row have failed and the analysis could not get past this error. "
                                "Write REPORT now with what stands: what was established before the failures, what the failing "
                                "step was meant to add, and what remains unestablished.")
                        text, usage = self.llm(self.system, self._user_prompt(run, budget, turn_no, spent, halt + "\n\n" + extra, everything=True))
                        spent += float((usage or {}).get("cost", 0.0) or 0.0)
                        _, note, action = parse_turn(text)
                        body = action.arg if action.verb == "report" else (text or "")
                        self.emit({"type": "turn_end", "run": run.id, "turn": turn_no + 1, "kind": "report", "thinking": "",
                                   "note": note or run.note, "code": "", "elapsed": (usage or {}).get("elapsed"), "cost": (usage or {}).get("cost", 0.0)})
                        rturn = Turn(kind="report", note=note or run.note, text=body, usage=dict(usage or {}))
                        run.turns.append(rturn)
                        self._emit_turn(run, rturn)
                        self._finish(run, body, budget, spent)
                        return run
            elif action.verb == "show":
                arg = str(action.arg).strip()
                m_run = re.match(r"(?i)^run((?:\s+\d+)+)$", arg)
                m_srch = re.match(r"(?i)^search((?:\s+\d+)+)$", arg)
                m_read = re.match(r"(?i)^read((?:\s+\d+)+)$", arg)
                nums = lambda m: [int(x) for x in m.group(1).split()]
                if m_run:
                    ks = nums(m_run)
                    turn.stdout = "\n\n".join(self.nb.render_run(run.id, k) for k in ks)
                    turn.text = " ".join(str(k) for k in ks)        # the runs this SHOW opened, for the prompt's standing block
                elif m_srch:
                    turn.stdout = "\n\n".join(self.nb.render_search(run.id, k) for k in nums(m_srch))
                elif m_read:
                    turn.stdout = "\n\n".join(self.nb.render_read(run.id, k) for k in nums(m_read))
                elif re.match(r"(?i)^[a-z]", arg):
                    # a word the forms above do not know (2026-10-03: "SHOW SEARCH 1 2 3 4" had been read as cells 1-4): say so
                    turn.stdout = f"(SHOW did not understand '{arg}'. SHOW takes cell numbers, or RUN k, SEARCH k, READ k - several numbers allowed.)"
                else:
                    # several cells at once (2026-09-10): SHOW 8 9 - a report needs its numbers in view in one turn
                    views = []
                    for num in (re.findall(r"\d+", arg) or [arg]):
                        try:
                            cell = self.nb.cell(run.id, int(num))
                        except ValueError:
                            cell = None
                        views.append(f"--- cell {cell.cell_no} (re-opened) ---\n```python\n{cell.code}\n```\nOUTPUT:\n{cell.stdout}"
                                     if cell else f"(no cell {num}; SHOW takes cell numbers, RUN k, SEARCH k or READ k)")
                    turn.stdout = "\n\n".join(views)
                extra = (f"SHOWN: run {turn.text} - whole, under RUNS SHOWN THIS RUN above" if m_run and turn.text
                         else "SHOWN:\n" + view_digest(turn.stdout, "the notebook keeps it whole", cap=SHOW_VIEW_CHARS))
            elif action.verb == "names":
                turn.stdout = tools.names(self.kernel)
                extra = "NAMES IN THE KERNEL:\n" + turn.stdout
            elif action.verb == "recall":
                turn.stdout = tools.recall(self.recall, action.arg)
                extra = f"RECALLED ({action.arg}):\n" + turn.stdout
            elif action.verb == "search":
                turn.text = action.arg                          # the query, so SHOW SEARCH k can name it
                done = sum(1 for t in run.turns if t.kind == "search" and t.stdout and not t.stdout.startswith("(search budget"))
                if budget.searches and done >= budget.searches:
                    turn.stdout = (f"(search budget for this run used: {done} of {budget.searches}. Work with what the earlier "
                                   f"searches returned - SHOW SEARCH k re-opens any of them whole - or state plainly what was not found.)")
                    extra = f"SEARCH ({action.arg}):\n" + turn.stdout
                else:
                    self.emit({"type": "lookup_start", "run": run.id, "kind": "search", "query": action.arg})
                    turn.stdout = tools.search(self.search, action.arg)
                    k = len(self.nb.searches(run.id)) + 1          # this search's number once recorded
                    shown = view_digest(turn.stdout, f"SHOW SEARCH {k} for all")
                    left = budget.searches - done - 1 if budget.searches else None
                    extra = f"SEARCH ({action.arg}):\n" + shown + (f"\n(searches left in this run: {left})" if left is not None else "")
            elif action.verb == "read":
                turn.text = action.arg                          # scope and query, so SHOW READ k can name it
                done = sum(1 for t in run.turns if t.kind == "read" and t.stdout and not t.stdout.startswith("(read budget"))
                if budget.reads and done >= budget.reads:
                    turn.stdout = (f"(read budget for this run used: {done} of {budget.reads}. Work with what the earlier reads "
                                   f"returned - SHOW READ k re-opens any of them whole - read the document in a cell "
                                   f"(D1.grep, D1.page, D1.units), or state plainly what was not found.)")
                    extra = f"READ ({action.arg}):\n" + turn.stdout
                else:
                    self.emit({"type": "lookup_start", "run": run.id, "kind": "read", "query": action.arg})
                    turn.stdout = tools.read(self.read, action.arg)
                    k = len(self.nb.reads(run.id)) + 1              # this read's number once recorded
                    shown = view_digest(turn.stdout, f"SHOW READ {k} for all")
                    left = budget.reads - done - 1 if budget.reads else None
                    extra = f"READ ({action.arg}):\n" + shown + (f"\n(reads left in this run: {left})" if left is not None else "")
            elif action.verb == "ask":
                turn.text = action.arg
                run.turns.append(turn)
                run.status = "asked"
                tools.ask_user(self.emit, action.arg)
                self._emit_turn(run, turn)
                self._save()
                return run
            elif action.verb == "report":
                turn.text = action.arg
                run.turns.append(turn)
                self._emit_turn(run, turn)
                self._finish(run, action.arg, budget, spent)
                return run
            else:
                turn.kind = "error"
                if action.arg == "empty reply":
                    logger.warning("Analyst turn %d: the model returned an empty reply (%s completion tokens billed) - re-asking",
                                   turn_no, usage.get("completion_tokens", "?"))
                    turn.stdout = "Your last reply arrived empty - no text reached the workspace. Reply again, in the turn format."
                elif (usage or {}).get("truncated"):
                    logger.warning("Analyst turn %d: the reply was cut at the length limit before a valid action (%s)", turn_no, action.arg)
                    turn.stdout = "Your last reply was cut off at the length limit before it reached an action; nothing ran."
                else:
                    logger.warning("Analyst turn %d: malformed reply (%s): %r", turn_no, action.arg, (text or "")[:200])
                    turn.stdout = f"Your last reply had no valid action ({action.arg}). Reply in the exact turn format."
                extra = turn.stdout
            if held:
                extra = (extra + "\n\n" + held) if extra else held

            run.turns.append(turn)
            self._emit_turn(run, turn)
            self.emit({"type": "heartbeat", "run": run.id, "turn": turn_no, "of": budget.turns, "spent": spent,
                       "dollars": budget.dollars, "estimate": _estimate_line(run.note)})
            self._save()

        # the report, forced: by a REPORT verdict (this turn is the report), or by the budget exhausted (ask for it once)
        if forced_by_review:
            self.emit({"type": "turn_start", "run": run.id, "turn": final_turn, "of": budget.turns})
        text, usage = self.llm(self.system, self._user_prompt(run, budget, final_turn, spent, final_extra, everything=True,
                                                              tail=REPORT_NOW if forced_by_review else ""))
        spent += float((usage or {}).get("cost", 0.0) or 0.0)
        _, note, action = parse_turn(text)
        body = action.arg if action.verb == "report" else (text or "")
        self.emit({"type": "turn_end", "run": run.id, "turn": final_turn if forced_by_review else budget.turns + 1, "kind": "report", "thinking": "",
                   "note": note or run.note, "code": "", "elapsed": (usage or {}).get("elapsed"), "cost": (usage or {}).get("cost", 0.0)})
        turn = Turn(kind="report", note=note or run.note, text=body, usage=dict(usage or {}))
        run.turns.append(turn)
        self._emit_turn(run, turn)
        self._finish(run, body, budget, spent)
        return run

    # ----- the ending: rewrite, guards, replay ------------------------------
    def _finish(self, run: Run, report_text: str, budget: Budget, spent: float) -> None:
        cells = self.nb.path_cells(run.id)
        report_text = rep.repair_markdown_tables(report_text)
        # a number is verified if a cell printed it - or if it is a constant of the analysis
        # itself (a filter bound, a bin edge) that appears in a cell's code
        # a number is also verified if a cited document passage carries it
        cited = rep.cited_units(report_text)
        unit_texts, missing = [], []
        for uid in cited:
            text_u = self.unit_text(uid) if self.unit_text else None
            (unit_texts if text_u is not None else missing).append(text_u if text_u is not None else uid)
        check = rep.guard_technical(report_text, [evidence_text(c) for c in cells] + [evidence_code(c) for c in cells] + unit_texts)
        check_u = rep.guard_units(missing)
        disputed = disputed_cells(run)
        quoted = [c for c in cited_cells(report_text) if c in disputed]
        check_d = ("CHECK: this report cites " + ", ".join(f"cell {c}, whose RESULT line the review {disputed[c]} found does not describe its code" for c in quoted)
                   + ". Treat what it quotes from there as unverified.") if quoted else ""
        run.report = report_text + "".join(f"\n\n> {x}" for x in (check, check_u, check_d) if x)
        # the plain-language rewrite by the same analyst
        self.emit({"type": "turn_start", "run": run.id, "turn": "rewrite", "of": budget.turns, "rewrite": True})
        t_rw = time.time()
        text, usage = self.llm(self.system, REWRITE_TASK + report_text, rewrite=True)   # the app runs it on the Rewriter seat when the config has one (2026-09-11)
        self.emit({"type": "turn_end", "run": run.id, "turn": "rewrite", "kind": "rewrite", "thinking": "", "note": "", "code": "",
                   "elapsed": round(time.time() - t_rw, 1), "cost": (usage or {}).get("cost", 0.0)})
        rewrite = (text or "").strip()
        rewrite = re.sub(r"^###.*?###\s*", "", rewrite, flags=re.S).strip()
        check2 = rep.guard_rewrite(rewrite, report_text)
        run.rewrite = rewrite + (f"\n\n> {check2}" if check2 else "")
        run.turns.append(Turn(kind="rewrite", note=run.note, text=run.rewrite, usage=dict(usage or {})))
        # the review after the report: only in a run that has reviews during it (Adaptive). Quick and Deep make no reviewer
        # call at all (2026-10-05, Palo: in Deep it cost 35-40% of the run and 20-40 s, before the replay, for no value a
        # reader asked for - who wants a review chooses Adaptive)
        if budget.review_every:
            rv, _ = self._review(run, budget, report=run.report)
            if rv is not None:
                run.report += "\n\n> " + review_note(rv)
        # the replay: the host's runner when it has one (the app's executor, which also
        # yields the figures and the results text), else a fresh kernel
        if run.cells() and (self.replay_runner is not None or self.kernel_factory is not None):
            # the replay can take as long as the analysis did; the pane shows it under way (2026-10-04: between the
            # rewrite and the closing card nothing was shown, and a person took a working run for a stuck one)
            self.emit({"type": "replay_start", "run": run.id, "cells": len(run.cells())})
            try:
                if self.replay_runner is not None:
                    from .replay import assemble, compare
                    script, order = assemble(cells, report_text, own=run.cells())
                    stdout, err = self.replay_runner(run, script)
                    status, line = compare(cells, report_text, stdout or "", err or "", len(order))
                else:
                    status, line, script = verify(self.kernel_factory, cells, report_text)
            except Exception as exc:                          # noqa: BLE001
                status, line, script = "failed", f"Replay could not run: {exc}", ""
            run.replay_status, run.replay_script = status, script
            run.report += f"\n\n> {line}"
            self.emit({"type": "replay_end", "run": run.id, "status": status, "line": line})
        run.status = "answered"
        self.emit({"type": "report", "run": run.id, "text": run.report})
        self.emit({"type": "rewrite", "run": run.id, "text": run.rewrite})
        if run.replay_status:
            self.emit({"type": "replay_status", "run": run.id, "status": run.replay_status, "script": run.replay_script})
        self._save()

    # ----- plumbing ------------------------------------------------------------
    # ----- the reviewer -------------------------------------------------------
    @staticmethod
    def _since_review(run: Run, j: int) -> dict:
        """The evidence after the review at run.turns[j], up to the next review: the cells committed, their RESULT lines,
        the failed attempts, the cells that printed nothing, the replies that ran nothing."""
        ev = {"cells": [], "results": [], "failed": 0, "empty": [], "rejected": 0}
        for x in run.turns[j + 1:]:
            if x.kind == "review":
                break
            if x.kind == "cell" and x.cell_no is not None:
                ev["cells"].append(x.cell_no)
                ev["results"] += [(x.cell_no, r["text"]) for r in (x.results or [])]
                if not (x.stdout or "").strip():
                    ev["empty"].append(x.cell_no)
            elif x.kind == "cell" and x.error:
                ev["failed"] += 1
            elif x.kind == "error":
                ev["rejected"] += 1
        return ev

    @staticmethod
    def _test_answers(run: Run, label: str) -> List[int]:
        """The cells whose RESULT lines are tagged with this test - "(test after turn 16)" - committed after it."""
        tag = re.compile(r"\(\s*test\s+%s\s*\)" % re.escape(label), re.I)
        j = next((k for k, x in enumerate(run.turns) if x.kind == "review" and x.text == label), None)
        if j is None:
            return []
        return sorted({x.cell_no for x in run.turns[j + 1:] if x.kind == "cell" and x.cell_no is not None
                       and any((r.get("test") and tag.search(f"(test {r['test']})")) or tag.search(r.get("text", "")) for r in (x.results or []))})

    def _review_block(self, run: Run) -> str:
        """The latest review during the run, for the analyst's prompt; a TEST carries its status, from the evidence: answered
        by a RESULT line tagged with it, or open (2026-10-05: a test the analyst said it had run never ran)."""
        latest = next((x for x in reversed(run.turns) if x.kind == "review" and x.text != "after the report"), None)
        if latest is None:
            return ""
        # the Re-check and Shown lines are the session's, not the analyst's (2026-10-06: the analyst read "Re-check: cell 17,
        # cell 18" as an instruction to itself and spent six turns re-opening those cells)
        own = "\n".join(ln for ln in latest.note.splitlines() if not ln.startswith(("- Re-check:", "- Shown:")))
        block = f"REVIEW ({latest.text} - answer it in your THINKING):\n" + own
        if latest.thinking.startswith("Verdict: TEST"):
            done = self._test_answers(run, latest.text)
            block += ("\n- Status: answered by " + ", ".join(f"[cell {c}]" for c in done) if done
                      else f"\n- Status: open - no RESULT line tagged (test {latest.text}) yet")
        elif latest.thinking.startswith("Verdict: REPORT") and (latest.stdout or "").startswith("not binding"):
            block += (f"\n- Status: advice, not binding - {latest.stdout[len('not binding: '):]}. Continue, or write REPORT when "
                      "you judge the answer established.")
        return block

    @staticmethod
    def _checked_before(run: Run) -> Dict[int, str]:
        """The verification ledger: cell -> the latest earlier review's finding about it (the cells handed to a review
        count as checked by it, with its Checked line when it wrote one)."""
        out: Dict[int, str] = {}
        for x in run.turns:
            if x.kind == "review":
                for c in x.shown or []:
                    out[c] = f"shown to the review {x.text}; no finding written"
                for rec in x.checked or []:
                    out[int(rec["cell"])] = f"{rec['text']} (review {x.text})"
        return out

    def _evidence_for_review(self, run: Run, report: Optional[str]):
        """The cells handed to this review, code and complete output - chosen by the session, not asked for (2026-10-06:
        the SHOW rounds re-sent the whole input each time, the reviewer drafted before asking and cited cells it had
        not opened). In order: the cells behind the best estimate (those its line cites, and those whose RESULT lines
        carry its numbers); the cells tagged as answering a TEST; the cells that recorded a result since the last
        review; a cell an earlier review asked to see again. After the report: the cells the report cites. A cell an
        earlier review was handed is not sent again unless asked for. Up to REVIEW_EVIDENCE_CHARS; the rest are named.
        Returns (text, cells sent, cells named but not sent)."""
        cells = {c.cell_no: c for c in self.nb.path_cells(run.id) if c.cell_no is not None}
        before = self._checked_before(run)
        last_review = max((k for k, x in enumerate(run.turns) if x.kind == "review"), default=-1)
        recheck = sorted(set(run.turns[last_review].recheck or [])) if last_review >= 0 else []   # the last review's ask, once
        why: Dict[int, str] = {}

        def want(n, reason):
            if n in cells and n not in why and (n not in before or reason == "you asked to see it again"):
                why[n] = reason
        for n in recheck:                     # the last review's explicit ask comes first (2026-10-06: a Re-check had lost to the budget)
            want(n, "you asked to see it again")
        if report is not None:
            for n in cited_cells(report):
                want(n, "cited by the report")
        else:
            # the first cell behind the estimate, then the TEST's answers, then the rest behind the estimate (2026-10-06: an
            # estimate that cites six cells had crowded the reviewer's own test out of the budget), then the new results
            est = _estimate_line(run.note)
            est_nums = {x for x in rep._numbers(est) if "." in x or len(x.lstrip("+-")) >= 3}
            behind = cited_cells(est) + [n for n, r in result_records(run) if est_nums & rep._numbers(r.get("text", ""))]
            for n in behind[:1]:
                want(n, "behind the best estimate")
            for n, r in result_records(run):
                if r.get("test"):
                    want(n, f"tagged as answering the TEST {r['test']}")
            for n in behind[1:]:
                want(n, "behind the best estimate")
            for x in reversed(run.turns[last_review + 1:]):
                if x.kind == "cell" and x.cell_no is not None and x.results:
                    want(x.cell_no, "a result recorded since the last review")
        parts, sent, left, used = [], [], [], 0
        budget_chars = REVIEW_EVIDENCE_CHARS if report is None else REVIEW_EVIDENCE_CHARS * 3 // 5   # the report itself is in view
        for n, reason in why.items():
            c = cells[n]
            out = c.stdout or ""
            out = out if len(out) <= REVIEW_OPEN_CHARS else out[:REVIEW_OPEN_CHARS] + "\n... [output cut for length]"
            block = f"--- cell {n} ({reason}) ---\n```python\n{(c.code or '').rstrip()}\n```\nOUTPUT:\n{out.rstrip() or '(printed nothing)'}"
            if used + len(block) > budget_chars and sent:
                left.append(n)
                continue
            parts.append(block); sent.append(n); used += len(block)
        text = "\n\n".join(parts) if parts else "(nothing new to check: every cell behind the current answer has been checked, or none has recorded a result)"
        if left:
            text += "\n\nNot sent this review, for length (name one under Re-check to see it next time): " + ", ".join(f"cell {c}" for c in left)
        return text, sent, left

    def _review_input(self, run: Run, budget: Budget, after_turn: Optional[int] = None, report: Optional[str] = None):
        """What the reviewer reads, fixed material first: the question, the data, the thread; then the note (or the report),
        the ledger, what earlier reviews checked, the earlier reviews with the analyst's answer to each, the turns since
        the last review, the cells to check now, and where the run stands. Returns (text, cells sent)."""
        parts = [f"QUESTION:\n{run.question.strip()}", f"DATA:\n{self.data_description}"]
        anc = self.nb.render_ancestry(run.id)
        if anc:
            parts.append(anc)
        parts.append(f"THE REPORT:\n{report.strip()}" if report is not None else f"THE ANALYST'S NOTE:\n{run.note or '(none yet)'}")
        res = result_lines(run)
        parts.append("RESULTS SO FAR:\n" + ("\n".join(res) if res else "(no results recorded)"))
        before = self._checked_before(run)
        parts.append("CHECKED BY EARLIER REVIEWS:\n" + ("\n".join(f"- cell {c}: {t}" for c, t in sorted(before.items())) if before else "(none yet)"))
        earlier = []
        for j, x in enumerate(run.turns):
            if x.kind == "review":
                nxt = next((y for y in run.turns[j + 1:] if y.kind not in ("review", "rewrite")), None)
                answer = _first_sentence(nxt.thinking) if nxt is not None and nxt.thinking else "(no turn since)"
                ev = self._since_review(run, j)
                verdict = x.thinking if len(x.thinking) <= 400 else x.thinking[:397].rsplit(" ", 1)[0] + "..."   # the analyst saw it whole
                entry = [f"- {x.text}: {verdict}", f"  the analyst then: {answer}",
                         f"  since then: cells {', '.join(map(str, ev['cells'])) or 'none'} committed; {ev['failed']} failed attempts; "
                         f"cells that printed nothing: {', '.join(map(str, ev['empty'])) or 'none'}"]
                if x.thinking.startswith("Verdict: TEST"):
                    done = self._test_answers(run, x.text)
                    entry.append("  status: " + (f"answered by {', '.join(f'[cell {c}]' for c in done)}" if done
                                                 else f"open - no RESULT recorded with test=\"{x.text}\""))
                earlier.append("\n".join(entry))
        parts.append("EARLIER REVIEWS:\n" + ("\n".join(earlier) if earlier else "(none)"))
        last_review = max((k for k, x in enumerate(run.turns) if x.kind == "review"), default=-1)
        head = "TURNS SINCE YOUR LAST REVIEW" if last_review >= 0 else "TURNS"
        parts.append(f"{head} (the analyst's own account of each turn, its action, and the outcome):\n"
                     + ("\n".join(self._turn_log(run, since=last_review)) or "(none)"))
        evidence, sent, _left = self._evidence_for_review(run, report)
        parts.append("TO CHECK NOW (code and complete output; no review has checked these):\n" + evidence)
        parts.append("The analysis is over; this review is added to the report." if report is not None
                     else f"TURN: after turn {after_turn}; up to {budget.turns}.")
        return "\n\n".join(parts), sent

    @staticmethod
    def _turn_log(run: Run, since: int = -1) -> List[str]:
        """Each analyst turn in order, one entry: its own account (the THINKING), its action, the outcome - the first
        line a cell printed, a failure's error, a refusal (2026-10-05: an admission that a slope labelled within-athlete
        was pooled sat in a turn the reviewer never saw; it saw a cell list and 'FAILED ATTEMPTS: 7')."""
        lines, k = [], 0
        for idx, x in enumerate(run.turns):
            if x.kind == "rewrite":
                continue
            if x.kind == "review":
                if idx > since:
                    lines.append(f"- (review {x.text}: {x.thinking[:140]})")
                continue
            k += 1
            if idx <= since:
                continue
            th = " ".join((x.thinking or "").split())
            th = th if len(th) <= 360 else th[:357] + "..."
            if x.kind == "cell" and x.cell_no is not None:
                what = f"cell {x.cell_no} -> {_first_line(x.stdout) or '(printed nothing)'}"
            elif x.kind == "cell":
                what = f"cell failed, rolled back -> {tools.exception_line(x.error or '')[:160]}"
            elif x.kind == "error":
                what = f"refused -> {_first_sentence(x.stdout or '', 160)}"
            elif x.kind in ("search", "read"):
                what = f"{x.kind.upper()} {(x.text or '')[:80]} -> {_first_line(x.stdout)}"
            else:
                what = f"{x.kind.upper()} {(x.text or '')[:60]}".rstrip()
            lines.append(f"- turn {k}: {th or '(no thinking written)'} | {what}")
        return lines

    def _review(self, run: Run, budget: Budget, after_turn: Optional[int] = None, report: Optional[str] = None):
        """One call on the Reviewer seat with the reviewer's own prompt; the session hands it the cells to check (2026-10-06,
        replacing the SHOW rounds). Returns (review or None, cost). A review that names no verdict is not used: the run
        goes on as if none had been asked for. Its Checked lines join the verification ledger; a REPORT binds only when
        every cell it cites has been checked, in this review or an earlier one."""
        self.emit({"type": "turn_start", "run": run.id, "turn": "review", "of": budget.turns, "review": True})
        t0 = time.time()
        user, sent = self._review_input(run, budget, after_turn, report)
        text, usage_r = self.llm(REVIEWER, user, review=True)
        cost = float((usage_r or {}).get("cost", 0.0) or 0.0)
        usage = {"cost": cost, "elapsed": round(time.time() - t0, 1)}
        rv = parse_review(text)
        label = "after the report" if report is not None else f"after turn {after_turn}"
        if rv is not None:
            before = self._checked_before(run)
            checked_cells = sorted(set(before) | set(sent) | {c for c, _ in rv["checked"]})
            rv["shown"], rv["checked_cells"], rv["cited"] = sent, checked_cells, cited_cells(rv["established"] + " " + rv["arg"])
            rv["binding"] = rv["verdict"] == "REPORT" and bool(rv["cited"]) and set(rv["cited"]) <= set(checked_cells)
            rv["lines"] += "\n- Shown: " + (", ".join(f"cell {c}" for c in sent) if sent else "nothing new")
        verdict = f"Verdict: {rv['verdict']} {rv['arg']}".rstrip() if rv else "(no verdict - the review was not used)"
        self.emit({"type": "turn_end", "run": run.id, "turn": "review", "kind": "review", "thinking": verdict,
                   "note": rv["lines"] if rv else "", "code": "", "elapsed": usage["elapsed"], "cost": cost})
        if rv is None:
            logger.warning("review %s: no verdict in the reply - not used", label)
            return None, cost
        turn = Turn(kind="review", note=rv["lines"], thinking=verdict, text=label, usage=usage, shown=list(sent),
                    checked=[{"cell": c, "text": t, "ok": checked_ok(t)} for c, t in rv["checked"]], recheck=list(rv["recheck"]))
        if report is None and rv["verdict"] == "REPORT" and not rv["binding"]:
            missing = [c for c in rv["cited"] if c not in rv["checked_cells"]]
            turn.stdout = "not binding: " + ("the reviewer cites no cell" if not rv["cited"] else
                                             "no review has checked " + ", ".join(f"cell {c}" for c in missing) + ", which it cites")
        run.turns.append(turn)
        self._save()
        return rv, cost

    def _emit_turn(self, run: Run, turn: Turn) -> None:
        ev = {"type": turn.kind, "run": run.id, "note": turn.note}
        if turn.kind == "cell":
            ev.update(code=turn.code, stdout=turn.stdout, error=turn.error, cell_no=turn.cell_no, figures=turn.figures)
        elif turn.kind in ("read", "search"):
            # the digest is the text; the query rides beside it (2026-10-03: the query had been sent as the text, so the
            # pane's row showed the query twice)
            ev["text"] = turn.stdout or ""
            ev["query"] = turn.text or ""
        elif turn.text:
            ev["text"] = turn.text
        elif turn.stdout:
            ev["text"] = turn.stdout
        self.emit(ev)

    def _save(self) -> None:
        if self.store is not None:
            self.store.save(self.nb)
