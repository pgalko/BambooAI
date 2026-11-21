"""The analyst session: one model, one kernel, one notebook, one report.

    session = Session(kernel, notebook, llm, store, emit=..., search=...)
    run = session.run(question, parent=None, budget=Budget(turns=15, dollars=1.0))
    branch = session.go_on(run.id, 3, "the person's hint")     # from turn 3 of that run, another way (docs/BRANCH_DESIGN.md)

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

import json
import logging
import os
import re
import time
from dataclasses import asdict, dataclass
from typing import Callable, Dict, List, Optional

from . import tools, report as rep, reach, brief as briefs, draft as drafts
from .notebook import Notebook, NotebookStore, Run, Turn, has_data, hint_block
from .replay import verify

logger = logging.getLogger(__name__)

_HERE = os.path.dirname(os.path.abspath(__file__))
_CONTRACT_TEMPLATE = open(os.path.join(_HERE, "contract.md"), encoding="utf-8").read()
# the documents' section and the READ row of the actions table ride only when the thread has documents
CONTRACT_DOCUMENTS = open(os.path.join(_HERE, "contract_documents.md"), encoding="utf-8").read()
# the Context section rides only when the load carries the words written beside the data (docs/CONTEXT_DESIGN.md §5)
CONTRACT_CONTEXT = open(os.path.join(_HERE, "contract_context.md"), encoding="utf-8").read()
# the Reviews section rides only when a reviewer runs during the run (Adaptive), naming the cadence; the reviewer has its
# own prompt and never sees the analyst's (2026-10-05)
CONTRACT_REVIEWS = open(os.path.join(_HERE, "contract_reviews.md"), encoding="utf-8").read()
# the brief's section and its parts of the report ride only when the run has a brief (docs/ARCHITECT_DESIGN.md §2.5): how
# the result stands against it where the brief gives something to hold it against (brief.held), what did not fit always
CONTRACT_BRIEF = open(os.path.join(_HERE, "contract_brief.md"), encoding="utf-8").read()
# the hint's section rides only in a branch (docs/BRANCH_DESIGN.md): the person went back to a turn and said how to go on.
# Under a brief it says which of the two holds where they part: the hint, the person's later word (decision 15)
_HINT_TEMPLATE = open(os.path.join(_HERE, "contract_hint.md"), encoding="utf-8").read()
HINT_OVER_BRIEF = ("- It outranks the brief too: where it departs from what BRIEF fixes, the hint is what you compute, and the\n"
                   "  report says where it departs.\n")
CONTRACT_HINT = _HINT_TEMPLATE.replace("{OVER_BRIEF}", "")
BRIEF_AGAINST = ("- against the brief, under the heading `## Against the brief`: for what the person expects to see, a line\n"
                 "  `Expected:` with `met`, `not met` or `cannot tell` and the number that says so; for what would change their\n"
                 "  mind, a line `Would change their mind:` with `seen`, `not seen` or `cannot tell`; then one line for each Also\n"
                 "  check line, with what it showed - or `cannot tell` and why. A part the brief does not give has no line\n")
BRIEF_MISFIT = ("- what did not fit, under the heading `## Did not fit`: each result the person's frame does not explain, one\n"
                "  to a line - or `Nothing.`\n")
_REVIEWER_TEMPLATE = open(os.path.join(_HERE, "reviewer.md"), encoding="utf-8").read()
# the reviewer's sixth lens, present only when the load carries the words written beside the data (docs/CONTEXT_DESIGN.md
# §6): the explanation of a number by the words, and what it rests on; the days compared with a window, not matched
REVIEWER_WORDS_LENS = ("- Words: where a number is explained by what was written - whether that rests on passages quoted,\n"
                       "  on counts of codes, or on the analyst's reading, and is reported as what it is; and whether the\n"
                       "  days of the words and of the numbers were compared with a window rather than matched by day.\n")
REVIEWER_WORDS_LINE = "- Words: ...\n"
# the brief among what the reviewer receives, present only when the run has one: the analysis is judged against what the
# person fixed, and a TEST stays inside it
REVIEWER_BRIEF_ITEM = ("- BRIEF: what the person fixed with the question before the run - the comparison, the measure, the period,\n"
                       "  what they expect and what else to check. The analyst is held to it: judge the analysis against it, and\n"
                       "  recommend no TEST that puts something else in the place of what it fixes\n")
# the hint among what the reviewer receives, present only in a branch: the turns since it are judged against it
REVIEWER_HINT_ITEM = ("- HINT: what the person said when they went back to a turn of this analysis and had it go on from there.\n"
                      "  The analyst is held to it from that turn on: judge the turns since against it\n")
REVIEWER_HINT_OVER_BRIEF = "  - and where it departs from what BRIEF fixes, the hint holds\n"      # under a brief: the person's later word


def reviewer(context: bool = False, brief: bool = False, hint: bool = False) -> str:
    """The reviewer's prompt; with context, the Words lens among the perspectives and its line in the format; with a
    brief, the brief among what it receives; in a branch, the person's hint - which, under a brief, holds where the
    two part."""
    return (_REVIEWER_TEMPLATE.replace("{LENSES}", "six" if context else "five")
                              .replace("{WORDS_LENS}", REVIEWER_WORDS_LENS if context else "")
                              .replace("{WORDS_LINE}", REVIEWER_WORDS_LINE if context else "")
                              .replace("{BRIEF_ITEM}", REVIEWER_BRIEF_ITEM if brief else "")
                              .replace("{HINT_ITEM}", REVIEWER_HINT_ITEM + (REVIEWER_HINT_OVER_BRIEF if brief else "") if hint else ""))


REVIEWER = reviewer(False)
REPORT_NOW = "The review found the answer established: this turn is the report. Write REPORT now."
REVIEW_EVIDENCE_CHARS = 20_000   # the cells handed to one review, code and output, up to this (2026-10-06: one call a
                                 # review; the session picks the cells, the reviewer asks for nothing)
REVIEW_OPEN_CHARS = 6_000        # a cell's output as the reviewer sees it, whole up to this
READ_ROW = ("| `READ D1 <what>` | Quote the passages of document 1 that answer. `READ ALL <what>`: every document. "
            "`READ D1.35-41 <what>` or `READ D1 p.7-9 <what>`: that stretch. |\n")
READ_ROW_CONTEXT = ("| `READ CTX <what>` | Quote the passages written beside the data that answer. "
                    "`READ CTX 2026-08-01..2026-08-31 <what>`: those days. `READ C.120-160 <what>`: that stretch. |\n")


def _ordinal(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def contract(documents: bool = False, review_every: int = 0, context: bool = False, brief: bool = False, held: bool = True,
             hint: bool = False) -> str:
    """The contract as the model reads it: one page, each rule once; with documents, the Documents section before
    Format and the READ row in the actions table; with context (the words written beside the data), the Context
    section after it and the READ CTX row; with reviews during the run, the Reviews section after Results; with a
    brief, The brief after How you work and its parts among the report's - how the result stands against it only
    where the report is `held` to something (brief.held); in a branch, A hint from the person after those - which
    says, under a brief, that the hint outranks it."""
    sections = ("\n" + CONTRACT_DOCUMENTS if documents else "") + ("\n" + CONTRACT_CONTEXT if context else "")
    rows = (READ_ROW if documents else "") + (READ_ROW_CONTEXT if context else "")
    return (_CONTRACT_TEMPLATE.replace("{DOCUMENTS}", sections)
                              .replace("{READ_ROW}", rows)
                              .replace("{REVIEWS}", "\n" + CONTRACT_REVIEWS.replace("{ordinal}", _ordinal(review_every))
                                       if review_every else "")
                              .replace("{BRIEF}", "\n" + CONTRACT_BRIEF if brief else "")
                              .replace("{HINT}", "\n" + _HINT_TEMPLATE.replace("{OVER_BRIEF}", HINT_OVER_BRIEF if brief else "") if hint else "")
                              .replace("{BRIEF_PARTS}", ((BRIEF_AGAINST if held else "") + BRIEF_MISFIT) if brief else ""))

CONTRACT = contract(False)

FIGURE_ASKED_LINE = ("THE FIGURE THE PERSON ASKS ABOUT is attached to this message as a picture: a plot of the chain in view, drawn by "
                     "its cells (SHOW n re-opens the cell that drew it; what it plotted is in the kernel when this chain's cells are). "
                     "Read the picture for what it shows; compute from the data for any number you state.")
LAST_TURNS_LINE = "The budget is nearly gone: write REPORT with what you have, and say what was not established."
TOOL_CALL_TAKEN = ("(Your last reply wrote its action as a tool call, and the action was taken from it. There are no tools: "
                   "reply in the turn format, as plain text.)")     # names no markup (2026-10-18)
# the report turn's effort (2026-10-18): the analysis is done and every number is in view - the report is writing. At the
# seat's xhigh a Claude 5.5 analyst thought through its whole 32,000-token allowance on the report turn and sent nothing,
# and the re-ask, the same call again, did the same. Medium, high for a model without it; a seat set lower stays lower
REPORT_EFFORT = ("medium", "high")
EFFORT_LEVELS = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
SHOW_VIEW_CHARS = 40_000     # a SHOW of several cells at once rides whole up to this; beyond it the middle goes, as for a digest
                             # (2026-10-03: an 87,000-character view of several cells was sent whole to a 64k-token server)
SAVED_VIEW_CHARS = 60_000    # a saved analysis SHOW SAVED opens rides whole up to this, its report and the code of some twenty cells;
                             # beyond it the middle goes. One a turn, for that turn: at this size it does not stay in the prompt
SHOWN_RUNS_CHARS = 60_000    # the runs SHOW RUN re-opened stay in the prompt for the rest of the run, whole, while together they fit
                             # this; beyond it the oldest collapse to a line each (2026-10-03: a count of three kept a five-chain
                             # synthesis cycling - ten of its fourteen turns re-opened runs it had already shown)
FIGURES_LATER = ("(Figures come after the report, from a request of their own, not from a cell of the analysis: this cell "
                 "was not run. Write the computation without the figure.)")     # 2026-10-11: cells compute; the figures request draws
FIGURES_ATTEMPTS = 4         # the figures step's cell: one try and up to three corrections of a cell that fails
# the figures cell runs wrapped (the record keeps the analyst's code alone): the analysis kernel's Plotly show is silent,
# so the wrap collects the figures shown and prints their titles after FIGURES: for the step to read. The collector
# closes over its own list, so a show left patched by a failed attempt (no rollback restores a class attribute) is harmless
FIGURES_MARK = "FIGURES:"
FIGURES_WRAP_HEAD = ("try:\n    import plotly.graph_objects as _bamboo_go\nexcept Exception:\n    _bamboo_go = None\n"
                     "_bamboo_figs = []\n"
                     "if _bamboo_go is not None:\n    _bamboo_go.Figure.show = (lambda L: (lambda self, *a, **k: L.append(self)))(_bamboo_figs)\n")
FIGURES_WRAP_TAIL = ("\nif _bamboo_go is not None:\n    _bamboo_go.Figure.show = lambda self, *a, **k: None\n"
                     "import json as _bamboo_json\n"
                     "print(" + repr(FIGURES_MARK + " ") + " + _bamboo_json.dumps([(lambda t: t if isinstance(t, str) else str(getattr(t, 'text', None) or ''))(getattr(getattr(f, 'layout', None), 'title', None)) for f in _bamboo_figs]))\n"
                     "del _bamboo_figs, _bamboo_go, _bamboo_json\n")
FIGURES_WRAP_LINES = FIGURES_WRAP_HEAD.count("\n")     # a traceback's line numbers back in the analyst's own code


def unwrap_lines(records: list) -> list:
    """The RESULT records of the figures cell with their lines in the analyst's own code (the wrap's head is subtracted,
    as unwrap_error does for a traceback); a record without a line, or with one inside the head, keeps none."""
    out = []
    for r in records or []:
        r = dict(r)
        ln = r.get("line")
        r["line"] = (ln - FIGURES_WRAP_LINES) if isinstance(ln, int) and ln > FIGURES_WRAP_LINES else None
        out.append(r)
    return out


def registry_delta(before: dict, after: dict) -> dict:
    """The registry entries a cell made or changed: the names whose description after the cell differs from before
    (a name re-bound to the same description is not kept again). The map takes a name's description at cell n from its
    latest entry at or before n."""
    return {n: e for n, e in (after or {}).items() if (before or {}).get(n) != e}


def unwrap_error(err: str) -> str:
    """A figures cell's traceback with its line numbers counted from the analyst's code, not the wrap's head."""
    return re.sub(r'(File "<string>", line )(\d+)', lambda m: m.group(1) + str(max(1, int(m.group(2)) - FIGURES_WRAP_LINES)), err or "")


FIGURES_SYSTEM = """You are drawing the figures for a finished analysis. The report is written, the kernel still holds every object the cells defined, and nothing is drawn yet.

Reply with one of two things and nothing else:
- the single word NONE, when a number, a table or a definition answers the question and a figure would add nothing;
- one Python cell, as a ```python block, that draws the one to three figures the report's reader needs - the figure the question asks for, or the estimate and its uncertainty, first; each further figure shows something the others do not; nothing the report does not say - from what the kernel holds, with Plotly and one fig.show() per figure; then, after the block, one line per figure in the order drawn: CAPTION: what the figure shows, in the reader's words.

Where the prompt lists THE FIGURES AGREED WITH THE PERSON, NONE is no reply: draw each of them first, in the order given, as it is described - its kind, what is on each axis, what it holds - and under its title, word for word; add a figure of your own only where the report needs one the list does not have, two at most. Where the prompt gives THE DRAFT THE PERSON SAW, it is the cell that drew those figures before the run, where no data was: draw each as the draft drew it - the same traces, panels, axes, colours and names - from what the kernel holds. No number comes from the draft, and where the draft prints `?` the figure prints the value.

The drawing's own arithmetic - bins, positions, a smoothed line - is the cell's to compute; the numbers the report states are not recomputed but read from the objects that hold them. Every number drawn or written - a point, a bar, an interval, a title (an f-string) - comes from a variable, never typed: a figure of typed numbers is a picture of this run alone, wrong the day the method runs on other data. The kernel has no display: you see nothing; the cell's figures are captured and shown to the reader with the report. A cell that fails comes back to you with its error for a corrected cell, three times at most; then the report stands without figures."""
FIGURES_CUT = ("YOUR LAST REPLY WAS CUT OFF at the length limit before a cell arrived (attempt {k} of {n}). Write the cell now, "
               "shorter: one figure, the one the reader needs most, and its CAPTION line.")
FIGURES_NO_BLOCK = ("YOUR LAST REPLY carried no python block and was not NONE (attempt {k} of {n}). Reply with one ```python block "
                    "and its CAPTION lines, or the word NONE.")
FIGURES_FAILED = ("YOUR LAST CELL FAILED - it was rolled back (attempt {k} of {n}); write a corrected cell:\n```python\n{code}\n```\nERROR:\n{error}")
# the figures the person agreed in the brief (docs/ARCHITECT_DESIGN.md §2.19, §2.20): the step is given them - and the
# cell that drew their draft, where one was drawn -, a reply that leaves one out is asked again once - before anything
# runs - and the report says where one was not drawn
FIGURES_AGREED = "THE FIGURES AGREED WITH THE PERSON (draw these first, in this order, each as described and under its title, word for word):"
# in a branch the hint is the person's later word: it holds where it asks for another drawing, and a figure it takes out is
# not asked for again (docs/BRANCH_DESIGN.md, decision 15)
FIGURES_AGREED_HINT = FIGURES_AGREED[:-2] + "; where the hint asks for another drawing, of these or of their draft, the hint holds):"
FIGURES_LEFT_OUT_HINT = " A figure the hint takes out stays out."
FIGURES_DRAFT = "THE DRAFT THE PERSON SAW"
FIGURES_LEFT_OUT = ("YOUR LAST REPLY LEFT OUT a figure agreed with the person (attempt {k} of {n}): {titles}. Nothing was run. Write the "
                    "cell again with every agreed figure in it, each under its title, word for word.")
DIGEST_VIEW_CHARS = 12_000   # a search or read digest rides into the next prompt whole, like the newest cell's output; a longer one
                             # is cut from the middle at line ends so its top and its SUMMARY both survive. The record keeps all.

REWRITE_TASK = ("Rewrite the technical report below for an intelligent reader who has never studied statistics and "
                "does not know this dataset: the answer first in everyday words, then what it depends on and what it "
                "does not mean, then how it was checked, then what to do next. Explain each idea the first time it "
                "appears. No column names, no method jargon, no bracketed intervals - give ranges in words "
                "('somewhere between 2 and 5'). Where the report cites a figure as [fig n], keep that citation at the end of "
                "the sentence that says what the figure shows. Where the report quotes a passage and cites it as [C.n] or [Dn.m], "
                "keep the citation and the quoted words exactly as the report has them, with the *rendered* mark where it stands - "
                "the quote is the evidence, not jargon; a [cell n] citation is dropped. Keep every number that matters and change none; drop the rest. Use short markdown "
                "headings and short paragraphs; about two-thirds the length of the original. Say what you mean in "
                "direct statements: when a literal phrase is available, use it, and never let a metaphor or a flourish "
                "stand in for a statement ('this still matters', not 'this earns its keep'; 'a parameter worth varying', "
                "not 'a dial worth turning'). The report's first line is its title (`# ...`): keep it, unchanged, as your own first "
                "line. Then the text, and nothing else.\n\n")

# with a brief, the parts the report gained stay findable in the plain-language version
REWRITE_BRIEF = ("Where the report has a part `## Against the brief` or `## Did not fit`, keep it under that heading, each line "
                 "opening as the report's does, the rest in everyday words.\n\n")
BRIEF_UNANSWERED = "CHECK: this report does not say how the result stands against the brief."

# the report's title (2026-10-17): the report's first line, `# ...` - a statement of what was found, written by the analyst
# at REPORT time, the one party that knows the whole investigation - heads the report in the Answer tab and the page's export.
# (A first cut had the rewrite's reply open with TITLE and LEAD lines; the Rewriter wrote them behind its scaffold, where no
# parser looked, and a lead that was told to mention a follow-up invented one.)
_TITLE_LINE_RE = re.compile(r"^\s*#(?!#)\s*(.+?)\s*#*\s*$")


def report_title(text: str) -> str:
    """The title of a report: its first non-blank line when that is a level-one heading, without the marks, a closing full
    stop or wrapping quotes; '' when the report opens otherwise."""
    first = next((ln for ln in (text or "").splitlines() if ln.strip()), "")
    m = _TITLE_LINE_RE.match(first)
    if not m:
        return ""
    return " ".join(re.sub(r"^[*\"'`\s]+|[*\"'`.\s]+$", "", m.group(1)).split())


def with_title(text: str, title: str) -> str:
    """The text headed by the title: its own first line replaced when that is a level-one heading, the title prepended
    otherwise; the text as it is without a title."""
    t = (text or "").strip()
    if not title:
        return t
    lines = t.splitlines()
    k = next((i for i, ln in enumerate(lines) if ln.strip()), None)
    if k is not None and _TITLE_LINE_RE.match(lines[k]):
        lines[k] = f"# {title}"
        return "\n".join(lines).strip()
    return f"# {title}\n\n{t}".strip()


def strip_scaffold(text: str) -> str:
    """A reply's text without the analyst's three-section form a seat may wrap it in: the text after the last ###ACTION###
    when there is one, a leading REPORT line and a stray ###MARK### dropped (2026-10-17: the Rewriter's reply opened with
    ###STEP### ... ###NOTE### ... ###ACTION### REPORT, and the plain-language text began with its working note)."""
    t = (text or "").strip()
    if "###ACTION###" in t:
        t = t.rsplit("###ACTION###", 1)[1]
    t = re.sub(r"^\s*REPORT\b[ \t]*\n?", "", t.strip())
    t = re.sub(r"^\s*###[A-Z]+###\s*", "", t)
    return t.strip()


_CELL_TOKEN_RE = re.compile(r"\s*\[?\bcells?\s+\d+(?:\s*(?:,|and|&)\s*\d+)*\]?")


def strip_cell_tokens(text: str) -> str:
    """The plain-language text without cell citations in any dress - [cell 7], [cells 9, 10], or the bare 'cell 14' a
    Rewriter leaves when it drops the brackets and not the citation (2026-10-17) - and the punctuation tidied after them."""
    t = _CELL_TOKEN_RE.sub("", text or "")
    t = re.sub(r"\(\s*\)", "", t)                       # an emptied parenthesis
    t = re.sub(r"\s+([.,;:])", r"\1", t)                 # a space left before punctuation
    t = re.sub(r"([.,;:])\1+", r"\1", t)                 # doubled punctuation
    return t


_NOTE_RE = re.compile(r"###NOTE###\s*\n(.*?)\n###ACTION###", re.S)
_STEP_MARK_RE = re.compile(r"###(?:STEP|THINKING)###[ \t]*\n?")       # the step's marker, and the one it replaced


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
                  ("measurement", "Measurement"), ("frame", "The question's frame"),
                  ("words", "Words"))   # the perspectives (2026-10-06), one line each; Words only with context (2026-10-14)


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


_MATCH_RE = re.compile(r"\bmatch(?:es|ed|ing)?\b", re.I)
# "does not match", "do not match", "doesn't match", "does not fully match", "not matching", and the brief's elliptical
# "does not:" or "does not." (2026-10-19: "those two lines match. The disagreement line does not: ..." had been read as a
# verdict on every line of the cell, since the test looked for the word "matches" alone)
_NO_MATCH_RE = re.compile(r"\b(?:(?:does|do|did)\s*n(?:o|')t|not)(?:\s+(?:fully|quite|entirely|all|always|yet))?\s*(?::|\.|;|$|match(?:es|ed|ing)?\b|describe\b)", re.I | re.M)
_NOT_RE = re.compile(r"\b(?:does|do|did)\s*n(?:o|')t\b", re.I)


def checked_verdict(text: str) -> str:
    """A reviewer's Checked line read as a verdict on the cell's RESULT lines (the brief's form: "matches its line | does
    not: how"): "ok" - the line says they match and no line does not; "no" - it says a line does not match, or says
    "does not" and never that anything matches; "partly" - it says both, so some of the cell's lines match and one does
    not. The word is read by its stem, in any form."""
    t = text or ""
    negated = bool(_NO_MATCH_RE.search(t))
    positive = len(_MATCH_RE.findall(t)) > len(re.findall(r"\bmatch(?:es|ed|ing)?\b", " ".join(_NO_MATCH_RE.findall(t)), re.I))
    if positive and negated:
        return "partly"
    if positive:
        return "ok"
    return "no" if (negated or _NOT_RE.search(t)) else "ok"


def checked_ok(text: str) -> bool:
    """True when the Checked line finds every RESULT line of the cell describes its code."""
    return checked_verdict(text) == "ok"


def disputed_cells(run) -> Dict[int, dict]:
    """Cells an earlier review found not to describe their code - cell -> {"review": the review's label, "partly": whether
    the finding was on one of the cell's lines, not all} - from the Checked lines on the review turns (the latest review's
    word on a cell stands). A line of such a cell is marked in the ledger, and a report that cites the cell is flagged
    (2026-10-06: a review had caught a typed line and the report quoted it anyway)."""
    out: Dict[int, dict] = {}
    for x in run.turns:
        if x.kind == "review":
            for rec in x.checked or []:
                c = int(rec["cell"])
                if rec.get("ok", True):
                    out.pop(c, None)
                else:
                    out[c] = {"review": x.text, "partly": bool(rec.get("partly"))}
    return out


def disputed_mark(d: dict) -> str:
    """The ledger's mark on a RESULT line of a disputed cell."""
    return (f"(the review {d['review']} found a line of this cell does not describe its code) " if d.get("partly")
            else f"(the review {d['review']} found this line does not describe its code) ")


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
            + (disputed_mark(disputed[c]) if c in disputed else "") + r["text"]
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


def _note_heading_line(ln: str) -> str:
    """A note line with its dressing off - a bullet, a number, bold marks around the heading or the line - so a heading is read
    whether it is written '- Heading:', '**Heading:**', '**Heading**:' or '1. Heading:' (2026-10-17)."""
    s = re.sub(r"^\s*(?:[-•*]+|\d+[.)])?\s*", "", ln or "")
    return s.replace("**", "").replace("__", "").strip()


def question_line(note: str) -> str:
    """The note's 'Question as understood' content - the analyst's own statement of what it answered, in context, which the
    report's head carries as the question (2026-10-17: a follow-up's question as typed, 'Extend to 45 terms', says nothing
    to a reader outside the thread, and the thread's earlier questions are the trajectory, not the result). The content
    runs on over following lines until the next heading; '' when the note has no such line."""
    out, on = [], False
    for ln in (note or "").splitlines():
        s = _note_heading_line(ln)
        if on and re.match(r"^(Best estimate so far|Held fixed|Open doubts|Plan|Names|Standing instructions from the person|Re-check|Shown)\s*[:\u2014\u2013-]", s, re.I):
            break
        if on:
            out.append(s)
        elif re.match(r"^question as understood\s*[:\u2014\u2013-]\s*", s, re.I):
            out.append(re.sub(r"^question as understood\s*[:\u2014\u2013-]\s*", "", s, flags=re.I))
            on = True
    return " ".join(" ".join(out).split())


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
    verb: str          # cell | show | names | search | read | ask | report | invalid
    arg: str = ""      # code, cell number, query, question or the report text
    more: tuple = ()   # the further actions a reply carried after this one, which did not run (2026-10-03)
    tool_call: bool = False    # read from a tool call the reply wrote in place of its marker lines (2026-10-18)


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


def attempt_effort(report: bool, lost_at: str = "") -> Optional[tuple]:
    """The effort a call asks for, as words in order of preference: the model layer takes the first the model accepts and
    never goes above the seat's own. The report turn asks for REPORT_EFFORT; the call after a reply that came back empty
    or cut at the length limit asks for the levels under the one that reply was asked at, nearest first (2026-10-18); when
    both hold, the lower. Neither: None - the seat's own."""
    asks = [REPORT_EFFORT] if report else []
    if lost_at in EFFORT_LEVELS[1:]:
        i = EFFORT_LEVELS.index(lost_at)
        asks.append(EFFORT_LEVELS[i - 1::-1] + (lost_at,))
    return min(asks, key=lambda a: EFFORT_LEVELS.index(a[0])) if asks else None


def parse_turn(text: str) -> tuple[str, str, Action]:
    """(thinking, note, action). A reply carries one action. Every action in every ###ACTION### block is found; the first
    runs, and any different ones after it are recorded in `more` so the next prompt can say they did not run (2026-10-05:
    the rule 'the last complete action' had run a four-line restart of imports in place of a 69-line cell; refusing the
    whole reply then cost a turn each time). The same action written twice runs once; a bare marker, or one with an
    unfinished action under it, carries none. The note and the step are the last written before the action taken. The
    step's marker is ###STEP###; ###THINKING###, the marker until 0104, is read the same way (2026-10-08: a section named
    THINKING, filled before the action, is the pattern the Claude 5.5 classifiers decline as reasoning extraction).
    A reply with no valid action that writes one as a tool call, in the model's own markup, is read from the call on as the
    action block (2026-10-18: Sonnet 5.5, though there are no tools, began about one turn in five with a call - and stopped,
    or wrote the code after it, or filled the marker lines after it with filler)."""
    thinking, note, action = _parse_marked(text)
    call = _TOOL_CALL_RE.search(text or "") if action.verb == "invalid" and action.arg != "empty reply" else None
    if call:
        th, nt, act = _parse_marked(text[:call.start()] + "###ACTION###\n" + _untagged(text[call.start():]))
        if act.verb != "invalid":
            return th, nt, Action(act.verb, act.arg, act.more, tool_call=True)
    return thinking, note, action


def _parse_marked(text: str) -> tuple[str, str, Action]:
    """parse_turn by the marker lines alone."""
    text = text or ""
    if not text.strip():
        return "", "", Action("invalid", "empty reply")
    marks = [m.start() for m in re.finditer(r"###ACTION###", text)]
    if not marks:
        m_note = _NOTE_RE.search(text)
        note = clean_note(m_note.group(1).strip()) if m_note else ""
        thinking = text[:text.find("###NOTE###")].strip() if "###NOTE###" in text else ""
        thinking = re.sub(r"^\s*###(?:STEP|THINKING)###\s*", "", thinking).strip()
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
    last_think = max((m.end() for m in _STEP_MARK_RE.finditer(head, 0, think_end)), default=-1)
    thinking = head[last_think:think_end].strip() if last_think >= 0 else head[:think_end].strip()
    return thinking, note, action


_FIG_BLOCK_RE = re.compile(r"```(?:python|py)?[ \t]*\n(.*?)```", re.S)
_CAPTION_RE = re.compile(r"^\s*(?:[-*]\s*)?\**CAPTION(?:\s*\d+)?\**\s*:\**\s*(.+?)\s*$", re.M | re.I)


def figures_outcome(reasons: list) -> str:
    """Why the figures were not drawn, in one clause: the one reason, or the count with the last reason."""
    if len(reasons) == 1:
        return reasons[0]
    kinds = {r.split(" (")[0] for r in reasons}
    if len(kinds) == 1:
        return f"{reasons[0].split(' (')[0]} {len(reasons)} times" + (f" (last: {reasons[-1].split(' (', 1)[1].rstrip(')')})" if " (" in reasons[-1] else "")
    return f"after {len(reasons)} attempts (last: {reasons[-1]})"


def answers_none(text: str) -> bool:
    """The figures reply that declines: its first line is the word NONE (bare, or dressed in markdown or a full stop)."""
    first = next((ln for ln in (text or "").splitlines() if ln.strip()), "")
    return re.sub(r"[^a-z]", "", first.lower()) == "none"


def parse_figures_reply(text: str) -> tuple:
    """(code, captions) from the figures step's reply: the code of its python block(s), joined in order, and the
    CAPTION: lines in the order written; (None, []) when it answers NONE or carries no code."""
    t = (text or "").strip()
    blocks = [b.strip("\n") for b in _FIG_BLOCK_RE.findall(t)] if t else []
    blocks = [b for b in blocks if b.strip()]
    if not blocks:
        return None, []
    code = "\n\n".join(blocks)
    captions = [c.strip().rstrip("*").strip() for c in _CAPTION_RE.findall(_FIG_BLOCK_RE.sub("", t))]
    return code, [c for c in captions if c]


def _reads_like_report(text: str) -> bool:
    """A reply with no action that is shaped like the report: markdown headings or cell citations, no code fence."""
    t = text or ""
    return "```" not in t and bool(re.search(r"^#{1,3} \S", t, re.M) or re.search(r"\[cell \d+\]", t))


def _unmarked_report(text: str) -> str:
    """The report in a reply that wrote it without its marker lines: from its first heading on, any step or note before
    it left out; the whole reply when it has no heading."""
    m = re.search(r"^#{1,3} \S", text or "", re.M)
    return (text[m.start():] if m else text or "").strip()


REPORT_EMPTY = "REPORT with nothing under it"
_ACTION_WORD_RE = re.compile(r"^\s*(CELL|SHOW|NAMES|SEARCH|READ|ASK|REPORT)\b[ \t]*(.*)$")          # as the contract writes them
_ACTION_WORD_ANY_CASE_RE = re.compile(r"^\s*(cell|show|names|search|read|ask|report)\b[ \t]*(.*)$", re.I)
_TOOL_CALL_RE = re.compile(r"<(?:invoke|function_calls)\b")                # a tool call, in the markup models are trained on
_INVOKE_RE = re.compile(r"<invoke\s+name\s*=\s*[\"']([^\"']*)[\"']\s*>(.*?)</invoke>", re.S)
_TAG_LINE_RE = re.compile(r"^[ \t]*</?(?:invoke|parameter|function_calls|code)\b[^>\n]*>[ \t]*(?:\n|\Z)", re.M)


def _compiles(code: str) -> bool:
    """Whether the text is Python the kernel can run: compiled, never executed."""
    try:
        compile(code, "<reply>", "exec")
        return True
    except Exception:                                    # noqa: BLE001 - SyntaxError, and the odd ValueError
        return False


def _untagged(text: str) -> str:
    """A tool call's text as an action block: code passed as the call's argument is a cell; a call named for an action
    is that action, its contents the argument (SHOW and 2: SHOW 2); any other call is its contents; the parameter and
    wrapper tags go."""
    def one(m):
        name, body = m.group(1).strip().upper(), m.group(2).strip()
        if (name == "CELL" or not _ACTION_WORD_RE.fullmatch(name)) and body and "```" not in body and _compiles(body):
            return "\n```python\n" + body + "\n```\n"
        if not _ACTION_WORD_RE.fullmatch(name):
            return "\n" + body + "\n"
        return "\n" + name + (" " if "\n" not in body else "\n") + body + "\n"
    text = re.sub(r"<parameter\b[^>]*>|</parameter>|</?function_calls>", "", text)
    return re.sub(r"</?invoke\b[^>]*>", "", _INVOKE_RE.sub(one, text))


def _cell_code(code: str) -> str:
    """A cell's code as it runs: without the lines that are a stray tag and nothing else, when they are all that keeps it
    from compiling (2026-10-18: a `</code>` and a `</parameter>` line, each failing its turn); otherwise as written."""
    if _compiles(code):
        return code
    bare = _TAG_LINE_RE.sub("", code).rstrip()
    return bare if bare != code.rstrip() and _compiles(bare) else code


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
                acts.append(Action("cell", _cell_code(code)))
            i, first = j + 1, False
            continue
        m = _ACTION_WORD_RE.match(ln) or (_ACTION_WORD_ANY_CASE_RE.match(ln) if first else None)
        if m:
            verb, arg = m.group(1).lower(), m.group(2).strip()
            first = False
            if verb == "cell":
                cell_word = True                                     # its fence follows
            elif verb == "report":
                # the report is what follows REPORT - the rest of its line, if any, and the lines under it. REPORT with
                # nothing under it is not a report (2026-10-11: a reply announced "this turn = REPORT", wrote the word and
                # stopped; the empty text went through as the answer, and the reader saw the figures section alone)
                text_r = "\n".join(([arg] if arg else []) + lines[i + 1:]).strip()
                if text_r:
                    acts.append(Action("report", text_r))
                    return acts, ""
                return acts, REPORT_EMPTY
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
            else:                                                    # search, read: the query is its one line
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
                 emit: Optional[Callable[[dict], None]] = None,
                 search: Optional[Callable] = None, data_description: str = "",
                 kernel_factory: Optional[Callable[[], object]] = None,
                 replay_runner: Optional[Callable] = None, read: Optional[Callable] = None,
                 unit_text: Optional[Callable[[str], Optional[str]]] = None, kernel_prelude: str = "", documents: bool = False,
                 context: bool = False, map_inputs: Optional[Callable[[Run], list]] = None, saved: Optional[Callable] = None):
        self.kernel = kernel
        self.nb = notebook
        self.llm = llm            # llm(system, user, **hints) -> (text, usage); hints: review=True on a self-review turn, rewrite=True on the plain-language rewrite
        self.store = store
        self.emit = emit or (lambda ev: None)
        self.search = search
        self.data_description = data_description or "(no dataset attached)"
        self.kernel_factory = kernel_factory
        self.replay_runner = replay_runner      # (run, script) -> (stdout, error); the host may also collect figures
        self._image = None                      # a figure the person asks about, set by run() (2026-10-13)
        self.read = read                        # read(arg) -> digest text over the thread's documents, or None when the host has none
        self.saved = saved                      # saved(thread, run) -> a saved analysis whole, or None when it is saved no more (SHOW SAVED k)
        self.unit_text = unit_text              # unit_text("D1.17") -> the unit's text, for the report guard; None when unknown
        self.kernel_prelude = kernel_prelude    # source the host wants in the kernel (the document objects): run committed at the
                                                # start of a run and again after a rollback, never a cell of the record
        self.documents = documents
        self.context = context                  # the load carries the words written beside the data (CTX, READ CTX)
        self.map_inputs = map_inputs            # map_inputs(run) -> the inputs the chain was offered, for the code map (2026-10-20);
                                                # None: the map is drawn from run.data alone
        self.system = contract(documents, context=context)      # the documents' and the context's sections and READ rows only when present

    # ----- the prompt --------------------------------------------------------
    @staticmethod
    def is_review(budget: Budget, turn_no: int) -> bool:
        """A review comes before this turn: never before the first; after every review_every turns (before turns 9, 17,
        25... for 8)."""
        return bool(budget.review_every) and turn_no > 1 and (turn_no - 1) % budget.review_every == 0

    def _saved_view(self, named: list, k: int) -> str:
        """SHOW SAVED k: the k-th saved analysis the brief names (brief.analyses), as the host holds it - under a line
        that says which it is, and that it ran on another person's data where the brief says so."""
        if not 1 <= k <= len(named):
            return f"(no saved analysis {k}; the brief names {len(named)})"
        s = named[k - 1][0]
        text = self.saved(s.get("thread"), s.get("run")) if self.saved else None
        if not text:
            return f"(saved analysis {k} is no longer among the saved analyses)"
        asked = " ".join(x for x in (s.get("when"), f"\"{s['question']}\"" if s.get("question") else "") if x)
        return f"--- saved analysis {k}: {asked}" + (" (another person's data)" if s.get("other") else "") + f" ---\n{text}"

    @staticmethod
    def _brief(run: Run) -> str:
        """The run's brief as a prompt carries it: with the checks every run on data makes where the run has data."""
        return briefs.render(run.brief, data=has_data(run.data))

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

    @staticmethod
    def _last_turn(budget: Budget, turn_no: int, spent: float) -> bool:
        """The report turn: the last turn itself (2026-10-06: at one turn left the model reported a turn early, every run,
        and Deep had 14 working turns of 15), never the first - even a tiny budget gets one cell - or the turn that finds
        nine tenths of the dollars spent. The forced report after the loop is the safety net if the model does not report."""
        return (budget.turns - turn_no <= 0 and turn_no > 1) or spent >= 0.9 * budget.dollars

    def _user_prompt(self, run: Run, budget: Budget, turn_no: int, spent: float, extra: str = "",
                     everything: bool = False, tail: str = "") -> str:
        last = self._last_turn(budget, turn_no, spent)
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
        if run.brief:
            parts.append(self._brief(run))
        if getattr(self, "_image", None):
            parts.append(FIGURE_ASKED_LINE)
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
            parts.append("PASSAGES THIS RUN'S READS RETURNED (verbatim, each with its id - cite one as [D1.17] or [C.417]):\n" + "\n".join(passages))
        if extra:
            parts.append(extra)
        hint = hint_block(run)
        if hint:
            parts.append(hint)                      # the person's hint stands above the task line from its turn to the report
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
    def run(self, question: str, parent: Optional[str] = None, budget: Budget = Budget(),
            run_id: Optional[str] = None, data: Optional[dict] = None, image: Optional[str] = None, mode: str = "",
            brief: Optional[dict] = None) -> Run:
        framed = self.nb.runs.get(str(run_id)) if run_id else None
        if framed is not None and framed.status == "framing":
            run = framed                                  # the brief was written in this run: its analysis is the same run (one box on the map)
            run.question, run.status = question, "running"
            run.created = time.time()                     # the analysis starts now: its time on the usage record leaves the framing out
        else:
            run = self.nb.new_run(question, parent, run_id=run_id)
        # the brief the person agreed for this run; an answer to the analyst's question runs under the brief it was asked in
        run.brief = briefs.agreed(brief) or briefs.carried(self.nb.runs.get(parent) if parent else None)
        run.mode = mode or ""                         # the preset the run was asked in, for the code map's header (2026-10-20)
        run.budget = asdict(budget)                   # its limits: a branch of this run runs under them (2.9)
        run.figure_asked = bool(image)
        run.sandbox = tools.sandbox(self.kernel)      # the box the cells run on, for the reach report (2026-10-28)
        if data:
            run.data = dict(data)                     # what this run runs on, on the record from the start: the computation
                                                      # path (notebook.computed_cells) is drawn from it during the run (2026-10-12)
        self._image = image or None                   # a figure the person asks about (the Plots tab's Ask AI): with every turn
                                                      # of the analysis, as a picture beside the prompt (2026-10-13)
        self._save()
        return self._loop(run, budget)

    def go_on(self, of: str, turn: int, hint: str, run_id: Optional[str] = None, data: Optional[dict] = None,
              reran: Optional[Dict[int, dict]] = None) -> Run:
        """A branch (docs/BRANCH_DESIGN.md): go on from turn `turn` of run `of`, another way. The branch is a run of its
        own that keeps that run's turns up to there, its question, brief, limits and mode; the loop takes up after the
        kept turn with what that turn carried, and the person's hint stands in every prompt from there to the report.
        The kernel is already at the state the kept turns left (the host's work). `reran`: where it got there by
        running the kept cells again, what each printed this time, by cell number ({stdout, results, snap}) - a cell
        that printed something else is marked, and its record here holds the new output and results."""
        run = self.nb.branch(of, turn, hint, run_id=run_id)
        if data:
            run.data = dict(data)
        run.sandbox = tools.sandbox(self.kernel)
        self._image = None                            # no figure rides with a branch: a run asked about one cannot be gone on from
        for t in run.cells():
            again = (reran or {}).get(t.cell_no)
            if again:
                t.snap = again.get("snap") or ""
                if (again.get("stdout") or "") != (t.stdout or ""):
                    t.kept, t.stdout, t.results = "differs", again.get("stdout") or "", list(again.get("results") or [])
        self._save()
        budget = Budget(**run.budget)
        self._emit_kept(run, budget)
        return self._loop(run, budget, carry=run.turns[-1].carry)

    def _emit_kept(self, run: Run, budget: Budget) -> None:
        """The turns a branch keeps, to the pane, as they were emitted the first time - each marked kept."""
        for t in run.turns:
            if t.kind == "review":
                self.emit({"type": "turn_start", "run": run.id, "turn": "review", "of": budget.turns, "review": True, "kept": True})
                self.emit({"type": "turn_end", "run": run.id, "turn": "review", "kind": "review", "thinking": t.thinking, "note": t.note,
                           "code": "", "elapsed": (t.usage or {}).get("elapsed"), "cost": (t.usage or {}).get("cost", 0.0), "kept": True})
                continue
            no = t.carry["turn"]
            self.emit({"type": "turn_start", "run": run.id, "turn": no, "of": budget.turns, "kept": True})
            self.emit({"type": "turn_end", "run": run.id, "turn": no, "kind": t.kind, "thinking": t.thinking, "note": t.note,
                       "code": t.code if t.kind == "cell" else "", "elapsed": (t.usage or {}).get("elapsed"),
                       "cost": (t.usage or {}).get("cost", 0.0), "estimate": _estimate_line(t.note), "kept": True})
            self._emit_turn(run, t)
        last = run.turns[-1].carry
        self.emit({"type": "heartbeat", "run": run.id, "turn": last["turn"], "of": budget.turns, "spent": last["spent"],
                   "dollars": budget.dollars, "estimate": _estimate_line(run.note)})

    def _loop(self, run: Run, budget: Budget, carry: Optional[dict] = None) -> Run:
        """The turns of a run to its report: from the first - or, in a branch, from the turn after the one whose `carry`
        is given: what was spent by then, what that turn handed to the next prompt, the failed cells in a row."""
        carry = carry or {}
        spent, extra, failures = float(carry.get("spent") or 0.0), carry.get("extra") or "", int(carry.get("failures") or 0)
        lost_at = carry.get("lost_at") or ""           # the effort a reply that came back empty or cut short was asked at
        self.system = contract(self.documents, budget.review_every, context=self.context, brief=bool(run.brief),    # the Reviews section only when a reviewer runs, The brief only with one
                               held=briefs.held(run.brief, has_data(run.data)), hint=bool(run.hints))                # ... the hint's only in a branch
        final_turn, final_extra, forced_by_review = budget.turns, LAST_TURNS_LINE + "\nWrite REPORT now.", False
        tools.run_prelude(self.kernel, self.kernel_prelude)        # the document objects, when the thread has documents
        for turn_no in range(int(carry.get("turn") or 0) + 1, budget.turns + 1):
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
            report_turn = self._last_turn(budget, turn_no, spent)
            effort, lost_at = attempt_effort(report_turn, lost_at), ""
            text, usage = self.llm(self.system, self._user_prompt(run, budget, turn_no, spent, extra), **({"image": self._image} if self._image else {}),
                                   **({"effort": effort} if effort else {}))
            usage = dict(usage or {})
            usage["elapsed"] = round(time.time() - t0, 1)
            spent += float(usage.get("cost", 0.0) or 0.0)
            thinking, note, action = parse_turn(text)
            if report_turn and action.arg == "no ###ACTION### block" and _reads_like_report(text) and not usage.get("truncated"):
                # the report turn's report written without its marker lines is the report: no turn is left to ask again,
                # and asking had the report written twice (2026-10-18, a Sonnet 5.5 run)
                action = Action("report", _unmarked_report(text))
            note = note or run.note
            extra = ""
            turn = Turn(kind=action.verb, note=note, thinking=thinking, usage=usage)
            held = (f"(Your reply held {len(action.more) + 1} actions - {action.verb.upper()} then "
                    f"{', '.join(v.upper() for v in action.more)}; only the first ran. A reply carries one action.)") if action.more and action.verb != "report" else ""
            if action.tool_call:                       # the reply's form, said with what it held (2026-10-18)
                logger.warning("Analyst turn %d: the action came as a tool call, without the marker lines; taken (%s)", turn_no, action.verb)
                held = (held + "\n" if held else "") + TOOL_CALL_TAKEN
            self.emit({"type": "turn_end", "run": run.id, "turn": turn_no, "kind": action.verb,
                       "thinking": thinking, "note": note, "code": action.arg if action.verb == "cell" else "",
                       "elapsed": usage.get("elapsed"), "cost": usage.get("cost", 0.0),
                       "estimate": _estimate_line(note)})

            if action.verb == "cell" and _draws_figure(action.arg):
                # cells compute, the figures step draws (2026-10-11: a run drew the same chart in three cells as it refined
                # the numbers, and the reader saw all three; before that a cap of three figure cells was the only brake).
                # The cell is not run, and the reply says why and what to do instead
                turn.code = action.arg
                turn.stdout = FIGURES_LATER
                extra = turn.stdout
            elif action.verb == "cell":
                turn.code = action.arg
                t_cell = time.time()
                self.emit({"type": "cell_start", "run": run.id, "turn": turn_no})   # the executor is busy from here (2026-09-08)
                before = tools.namespace(self.kernel)
                out, err, figs, recs, rc = tools.run_cell(self.kernel, action.arg)
                turn.elapsed = round(time.time() - t_cell, 1)
                turn.stdout, turn.error, turn.figures, turn.results = out, err, figs, recs
                turn.reaches, turn.refused = reach.mark(rc["reaches"], self._questions(run)), rc["refused"]   # 2026-10-28
                if not err:
                    turn.cell_no = self.nb.next_cell_no(run.id)
                    turn.snap = tools.snap(self.kernel)        # the state the kernel can come back to (2.9)
                    turn.registry = registry_delta(before, tools.namespace(self.kernel))   # what the cell made or changed (the code map, 2026-10-20)
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
                        turn.carry = dict(turn=turn_no, extra=extra, spent=spent, failures=failures, lost_at=lost_at)
                        run.turns.append(turn)
                        self._emit_turn(run, turn)
                        self.emit({"type": "heartbeat", "run": run.id, "turn": turn_no, "of": budget.turns, "spent": spent,
                                   "dollars": budget.dollars, "estimate": _estimate_line(run.note)})
                        self._save()
                        halt = (f"STOP: {failures} cells in a row have failed and the analysis could not get past this error. "
                                "Write REPORT now with what stands: what was established before the failures, what the failing "
                                "step was meant to add, and what remains unestablished.")
                        self.emit({"type": "turn_start", "run": run.id, "turn": turn_no + 1, "of": budget.turns})   # a card for the report (2026-10-08)
                        text, usage = self.llm(self.system, self._user_prompt(run, budget, turn_no, spent, halt + "\n\n" + extra, everything=True),
                                               effort=REPORT_EFFORT)
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
                m_saved = re.match(r"(?i)^saved((?:\s+\d+)+)$", arg)
                named = briefs.analyses((run.brief or {}).get("saved") or [])      # the saved analyses the brief names: SHOW SAVED k opens one
                cap, rest = SHOW_VIEW_CHARS, "the notebook keeps it whole"         # what the next prompt takes of the view, and what a longer one says of the rest
                nums = lambda m: [int(x) for x in m.group(1).split()]
                if m_run:
                    ks = nums(m_run)
                    turn.stdout = "\n\n".join(self.nb.render_run(run.id, k) for k in ks)
                    turn.text = " ".join(str(k) for k in ks)        # the runs this SHOW opened, for the prompt's standing block
                elif m_srch:
                    turn.stdout = "\n\n".join(self.nb.render_search(run.id, k) for k in nums(m_srch))
                elif m_read:
                    turn.stdout = "\n\n".join(self.nb.render_read(run.id, k) for k in nums(m_read))
                elif m_saved and named:
                    k, *more = nums(m_saved)
                    turn.stdout = self._saved_view(named, k) + (f"\n(one saved analysis at a time: SHOW SAVED {more[0]} opens the next)" if more else "")
                    cap, rest = SAVED_VIEW_CHARS, "that part is not in view"
                elif re.match(r"(?i)^[a-z]", arg):
                    # a word the forms above do not know (2026-10-03: "SHOW SEARCH 1 2 3 4" had been read as cells 1-4): say so
                    turn.stdout = (f"(SHOW did not understand '{arg}'. SHOW takes cell numbers, or RUN k, SEARCH k, READ k - several numbers allowed"
                                   + (" - or SAVED k" if named else "") + ".)")
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
                         else "SHOWN:\n" + view_digest(turn.stdout, rest, cap=cap))
            elif action.verb == "names":
                turn.stdout = tools.names(self.kernel)
                extra = "NAMES IN THE KERNEL:\n" + turn.stdout
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
                                   f"(D1.grep, D1.page, D1.units) or the context (CTX.grep, CTX.around), or state plainly what was not found.)")
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
                if usage.get("declined"):
                    # the provider's classifier declined the request before any text (2026-10-08: four turns of a Claude
                    # Sonnet 5.5 run, told "no valid action", re-sent the same SHOW three times)
                    logger.warning("Analyst turn %d: the provider declined the request before any reply (%s)", turn_no, usage["declined"])
                    turn.stdout = (f"Your last reply did not arrive: the provider declined the request before any text "
                                   f"({usage['declined']}). Nothing ran; reply again.")
                elif action.arg == "empty reply":
                    logger.warning("Analyst turn %d: the model returned an empty reply (%s completion tokens billed) - re-asking",
                                   turn_no, usage.get("completion_tokens", "?"))
                    turn.stdout = "Your last reply arrived empty - no text reached the workspace. Reply again, in the turn format."
                    lost_at = usage.get("effort") or ""
                elif (usage or {}).get("truncated"):
                    logger.warning("Analyst turn %d: the reply was cut at the length limit before a valid action (%s)", turn_no, action.arg)
                    turn.stdout = "Your last reply was cut off at the length limit before it reached an action; nothing ran."
                    lost_at = usage.get("effort") or ""
                elif action.arg == REPORT_EMPTY:
                    # the word without the report (2026-10-11): say what a report is, so the next reply carries it
                    logger.warning("Analyst turn %d: REPORT with nothing under it", turn_no)
                    turn.stdout = ("Your last reply ended at REPORT with no report under it, so nothing ran: the report is the "
                                   "text under REPORT, in the same reply. Write it now - ###ACTION### on its own line, REPORT "
                                   "on the next, then the report.")
                elif action.arg == "no ###ACTION### block" and _reads_like_report(text):
                    # the answer written without the scaffold (2026-10-08: a Sonnet 5.5 run wrote its report three times with
                    # no marker lines, once with a bare REPORT line, and was told "no valid action" each time)
                    logger.warning("Analyst turn %d: a report-shaped reply with no ###ACTION### block: %r", turn_no, (text or "")[:200])
                    turn.stdout = ("Your last reply read like the report but had no ###ACTION### block, so it was not taken as one; "
                                   "nothing ran. A report is: ###ACTION### on its own line, REPORT on the next, then the report.")
                else:
                    logger.warning("Analyst turn %d: malformed reply (%s): %r", turn_no, action.arg, (text or "")[:200])
                    turn.stdout = f"Your last reply had no valid action ({action.arg}). Reply in the exact turn format."
                extra = turn.stdout
            if held:
                extra = (extra + "\n\n" + held) if extra else held

            # what the loop carries out of this turn: a branch that goes on from it takes up exactly here (2.9)
            turn.carry = dict(turn=turn_no, extra=extra, spent=spent, failures=failures, lost_at=lost_at)
            run.turns.append(turn)
            self._emit_turn(run, turn)
            self.emit({"type": "heartbeat", "run": run.id, "turn": turn_no, "of": budget.turns, "spent": spent,
                       "dollars": budget.dollars, "estimate": _estimate_line(run.note)})
            self._save()

        # the report, forced: by a REPORT verdict (this turn is the report), or by the budget exhausted (ask for it once).
        # Either way the call is a turn with a card (2026-10-08: the exhausted-budget call had a turn_end and no turn_start,
        # so the report streamed into no card and the pane printed it raw under the closing card)
        report_turn = final_turn if forced_by_review else budget.turns + 1
        if not forced_by_review and extra:
            final_extra = extra + "\n\n" + final_extra      # what the last turn produced rides with the ask: a failure's traceback, a lost reply's note
        self.emit({"type": "turn_start", "run": run.id, "turn": report_turn, "of": budget.turns})
        text, usage = self.llm(self.system, self._user_prompt(run, budget, final_turn, spent, final_extra, everything=True,
                                                              tail=REPORT_NOW if forced_by_review else ""),
                               effort=attempt_effort(True, lost_at))
        spent += float((usage or {}).get("cost", 0.0) or 0.0)
        _, note, action = parse_turn(text)
        body = action.arg if action.verb == "report" else (text or "")
        self.emit({"type": "turn_end", "run": run.id, "turn": report_turn, "kind": "report", "thinking": "",
                   "note": note or run.note, "code": "", "elapsed": (usage or {}).get("elapsed"), "cost": (usage or {}).get("cost", 0.0)})
        turn = Turn(kind="report", note=note or run.note, text=body, usage=dict(usage or {}))
        run.turns.append(turn)
        self._emit_turn(run, turn)
        self._finish(run, body, budget, spent)
        return run

    # ----- the ending: rewrite, guards, replay ------------------------------
    def _finish(self, run: Run, report_text: str, budget: Budget, spent: float) -> None:
        report_text = rep.repair_markdown_tables(report_text)
        run.title = report_title(report_text)         # the report's first line, the analyst's own title (2026-10-17); '' when it opens otherwise
        run.report = report_text                      # as written, on the record from here (a stop during the steps below keeps it)
        # the figures, drawn once, after the report, from the variables the cells left in the kernel (2026-10-11): the
        # report gains a Figures section that cites them, and from here on the section is part of the report - the
        # guards, the rewrite, the replay and a routine read it as such
        figures_section, figures_note = self._figures(run, report_text)
        report_text += figures_section
        cells = self.nb.path_cells(run.id)            # the record: what any cell of the path printed verifies a number
        computed = self.nb.computed_cells(run.id)     # the computation: what the replay re-runs (2026-10-12: the earlier
                                                      # chains' cells on other data are context, not part of this chain's script)
        # a number is verified if a cell printed it - or if it is a constant of the analysis
        # itself (a filter bound, a bin edge) that appears in a cell's code
        # a number is also verified if a cited document passage carries it
        cited = rep.cited_units(report_text)
        unit_texts, missing = [], []
        for uid in cited:
            text_u = self.unit_text(uid) if self.unit_text else None
            (unit_texts if text_u is not None else missing).append(text_u if text_u is not None else uid)
        for uid in rep.named_units(report_text):       # a passage named by its bare id: a citation where it resolves, nothing otherwise (2026-10-14)
            text_u = self.unit_text(uid) if uid not in cited and self.unit_text else None
            if text_u is not None:
                unit_texts.append(text_u)
        # a number the brief states is the person's own, and one in a saved analysis the run opened is history it may state
        stated = ([self._brief(run)] if run.brief else []) + [t.stdout for t in run.turns if t.kind == "show" and (t.stdout or "").startswith("--- saved analysis ")]
        check = rep.guard_technical(report_text, [evidence_text(c) for c in cells] + [evidence_code(c) for c in cells] + unit_texts + stated)
        check_u = rep.guard_units(missing)
        disputed = disputed_cells(run)
        quoted = [c for c in cited_cells(report_text) if c in disputed]
        check_d = ("CHECK: this report cites " + ", ".join((f"cell {c}, of whose RESULT lines the review {disputed[c]['review']} found one does not describe its code" if disputed[c]["partly"]
                                                           else f"cell {c}, whose RESULT line the review {disputed[c]['review']} found does not describe its code") for c in quoted)
                   + ". Treat what it quotes from there as unverified.") if quoted else ""
        check_b = ""
        if run.brief:
            run.brief_outcome = briefs.outcome(report_text)
            # unanswered: the brief gives something to hold the result against, and the part is missing - or the person
            # said what they expect and the report gives no verdict on it
            answered = run.brief_outcome["stated"] and (run.brief_outcome["expected"] or not run.brief.get("expects"))
            check_b = BRIEF_UNANSWERED if briefs.held(run.brief, has_data(run.data)) and not answered else ""
        run.report = report_text + "".join(f"\n\n> {x}" for x in (check, check_u, check_d, check_b, figures_note) if x)
        # the plain-language rewrite by the same analyst
        self.emit({"type": "turn_start", "run": run.id, "turn": "rewrite", "of": budget.turns, "rewrite": True})
        t_rw = time.time()
        text, usage = self.llm(self.system, REWRITE_TASK + (REWRITE_BRIEF if run.brief else "") + report_text, rewrite=True)   # the app runs it on the Rewriter seat when the config has one (2026-09-11)
        self.emit({"type": "turn_end", "run": run.id, "turn": "rewrite", "kind": "rewrite", "thinking": "", "note": "", "code": "",
                   "elapsed": round(time.time() - t_rw, 1), "cost": (usage or {}).get("cost", 0.0)})
        # the plain-language text: the seat's scaffold off, the cell citations out in any dress, the report's title as its
        # first line - the same anchor in both versions of the Answer tab and at the top of the export (2026-10-17)
        rewrite = with_title(strip_cell_tokens(strip_scaffold(text)), run.title)
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
            self.emit({"type": "replay_start", "run": run.id, "cells": len(run.cells()),
                       "seconds": round(sum(float(c.elapsed or 0.0) for c in computed), 1)})   # what the cells took: the replay re-runs them, so about as long again (2026-10-15)
            try:
                if self.replay_runner is not None:
                    from .replay import assemble, compare
                    script, order = assemble(computed, report_text, own=run.cells())
                    stdout, err = self.replay_runner(run, script)
                    status, line = compare(computed, report_text, stdout or "", err or "", len(order))
                else:
                    status, line, script = verify(self.kernel_factory, computed, report_text)
            except Exception as exc:                          # noqa: BLE001
                status, line, script = "failed", f"Replay could not run: {exc}", ""
            run.replay_status, run.replay_script = status, script
            run.report += f"\n\n> {line}"
            self.emit({"type": "replay_end", "run": run.id, "status": status, "line": line})
        # the code map (2026-10-20, analyst/codemap): built once from the record, mechanically, and kept with the run;
        # nothing of it reaches a prompt, and a failure is recorded on the run, never raised
        try:
            from . import codemap
            run.code_map = codemap.build(self.nb, run, self.map_inputs(run) if self.map_inputs else None, context=self.context)
        except Exception as exc:                              # noqa: BLE001
            logger.warning("code map for run %s: %s", run.id, exc)
            run.code_map = {"error": " ".join(str(exc).split())[:300]}
        run.status = "answered"
        self.emit({"type": "report", "run": run.id, "text": run.report})
        self.emit({"type": "rewrite", "run": run.id, "text": run.rewrite})
        if run.replay_status:
            self.emit({"type": "replay_status", "run": run.id, "status": run.replay_status, "script": run.replay_script})
        self._save()

    # ----- the figures step ------------------------------------------------------
    def _figures(self, run: Run, report_text: str) -> tuple:
        """The figures, drawn once after the report (2026-10-11): the analyst sees the report and the cells' code and
        writes one cell that draws from what the kernel holds, or answers NONE. Every other outcome is an attempt that
        is asked again, up to FIGURES_ATTEMPTS in all: a cell that fails comes back with its error; a reply cut at
        the length limit before a cell arrived, or one with no python block, is said as such and asked for a shorter
        cell (2026-10-11: a reply of 16,000 reasoning tokens and no text had been taken for NONE and the reader told a
        number answered). Each attempt is a card in the pane and a turn of the record (step "figures"; the committed
        cell gets a number like any cell). Returns (the report's Figures section - "## Figures" with one "[fig n]
        caption" line per figure, or "" - and a line for the report when the figures were not drawn, or ""). Outside
        the turn budget, like the rewrite.

        Where the brief holds figures the person agreed (2026-11-18), the step is given them. A reply that leaves one
        out - NONE, or a cell whose code does not name its title - is an attempt too, asked again once before
        anything runs; after that the cell runs as it is, and the line for the report names each agreed figure that
        no figure drawn carries the title of (a plot the kernel saved itself has no title to read: the cell's code
        stands for it)."""
        if not run.cells() or not (report_text or "").strip():      # nothing computed, or no report to draw for
            return "", ""
        user = self._figures_prompt(run, report_text)
        agreed = [f["title"] for f in run.brief.get("figures", [])]
        error_note, section, reasons, drawn, again = "", "", [], [], bool(agreed)
        for attempt in range(1, FIGURES_ATTEMPTS + 1):
            self.emit({"type": "turn_start", "run": run.id, "turn": "figures", "figures": True, "quiet": True, "attempt": attempt})
            t0 = time.time()
            text, usage = self.llm(FIGURES_SYSTEM, user + error_note, figures=True)
            usage = usage or {}
            code, captions = parse_figures_reply(text)
            declined = code is None and answers_none(text)
            left_out = [t for t in agreed if declined or (code is not None and not briefs.carries(code, t))] if again and attempt < FIGURES_ATTEMPTS else []
            if left_out:
                again = False
                why = peek = "the reply left out a figure agreed with the person: " + "; ".join(f'"{t}"' for t in left_out)
            elif code is None and not declined:
                # nothing usable: cut at the length limit (a reasoning model can spend the whole allowance thinking), empty,
                # or prose without a block - an attempt, said as such, and asked again
                why = ("the reply was cut off at the length limit before a cell arrived" if usage.get("truncated") else
                       "the reply arrived empty" if not (text or "").strip() else "the reply carried no python block and was not NONE")
                peek = why
            else:
                peek = ("no figure: a number or a table answers" if declined else
                        ("figure cell: " + "; ".join(captions)) if captions else "a figure cell")
            self.emit({"type": "turn_end", "run": run.id, "turn": "figures", "kind": "figures", "thinking": "", "note": "", "code": code or "",
                       "elapsed": round(time.time() - t0, 1), "cost": float(usage.get("cost", 0.0) or 0.0), "peek": peek[:200]})
            if declined and not left_out:
                break                                           # the report stands as written
            if code is None or left_out:
                turn = Turn(kind="error", note=run.note, stdout=why, usage=dict(usage), step="figures")
                run.turns.append(turn)
                self._emit_turn(run, turn)
                reasons.append(why)
                error_note = "\n\n" + (FIGURES_LEFT_OUT.format(k=attempt, n=FIGURES_ATTEMPTS, titles="; ".join(f'"{t}"' for t in left_out))
                                       + (FIGURES_LEFT_OUT_HINT if run.hints else "") if left_out else
                                       (FIGURES_CUT if usage.get("truncated") else FIGURES_NO_BLOCK).format(k=attempt, n=FIGURES_ATTEMPTS))
                continue
            turn = Turn(kind="cell", note=run.note, code=code, usage=dict(usage), step="figures")
            t_cell = time.time()
            self.emit({"type": "cell_start", "run": run.id, "turn": "figures"})
            before = tools.namespace(self.kernel)
            try:
                out, err, figs, recs, rc = tools.run_cell(self.kernel, FIGURES_WRAP_HEAD + code.rstrip("\n") + FIGURES_WRAP_TAIL)
                lost = False
                head = len(FIGURES_WRAP_HEAD.splitlines())
                turn.reaches = reach.mark([{**r, "line": (r["line"] - head if isinstance(r.get("line"), int) and r["line"] > head else r.get("line"))}
                                           for r in rc["reaches"]], self._questions(run))
                turn.refused = rc["refused"]
            except Exception as exc:                              # noqa: BLE001 - the kernel itself, not the cell
                out, err, figs, recs, lost = "", f"the kernel could not run the cell: {exc}", [], [], True
            turn.elapsed = round(time.time() - t_cell, 1)
            titles = []
            if not err:
                lines = (out or "").splitlines()
                marks = [ln for ln in lines if ln.strip().startswith(FIGURES_MARK)]
                if marks:
                    try:
                        titles = [str(t) for t in json.loads(marks[-1].strip()[len(FIGURES_MARK):].strip())]
                    except ValueError:
                        titles = []
                    out = "\n".join(ln for ln in lines if not ln.strip().startswith(FIGURES_MARK))
            turn.stdout, turn.error, turn.results = out, unwrap_error(err), unwrap_lines(recs)
            err = turn.error
            if not err:
                turn.registry = registry_delta(before, tools.namespace(self.kernel))
            # the kernel's saved plots, then the Plotly figures shown; a rolled-back cell drew nothing that counts
            turn.figures = [] if err else list(figs or []) + [{"plotly": True, "title": t} for t in titles]
            if err:
                run.turns.append(turn)
                self._emit_turn(run, turn)
                reasons.append("the kernel could not run the cell" if lost else f"the figure cell failed ({tools.exception_line(err)[:120]})")
                if lost:
                    break
                tools.rebind_aliases(self.kernel)               # a rollback on an older kernel loses pd/np/plt
                tools.run_prelude(self.kernel, self.kernel_prelude)      # ... and the document objects
                error_note = "\n\n" + FIGURES_FAILED.format(k=attempt, n=FIGURES_ATTEMPTS, code=code.rstrip(), error=tools.condense_error(err, code=code))
                continue
            turn.cell_no = self.nb.next_cell_no(run.id)
            run.turns.append(turn)
            self._emit_turn(run, turn)
            drawn = titles + ([code] if figs else [])            # a plot the kernel saved itself comes without its title: the cell's code stands for it
            n = len(turn.figures)
            if n:
                caps = [c for c in captions if c][:n]
                while len(caps) < n:                            # a figure without a caption line is named by its title, else counted
                    k = len(caps)
                    caps.append((titles[k - len(figs or [])] if 0 <= k - len(figs or []) < len(titles) else "") or f"figure {k + 1}")
                section = "\n\n## Figures\n\n" + "\n".join(f"- [fig {turn.cell_no}] {c}" for c in caps)
            else:
                reasons.append("the figure cell ran but drew nothing")
            break
        self._save()
        note = "" if section or not reasons else "The figures were not drawn: " + figures_outcome(reasons) + "."
        missing = [f'"{t}"' for t in agreed if section and not any(briefs.carries(d, t) for d in drawn)]
        if missing:
            note = ("A figure agreed in the brief was not drawn: " if len(missing) == 1 else "Figures agreed in the brief were not drawn: ") + "; ".join(missing) + "."
        return section, note

    def _figures_prompt(self, run: Run, report_text: str) -> str:
        cells = self.nb.computed_cells(run.id)        # the cells whose variables are in the kernel (2026-10-12)
        code = "\n\n".join(f"--- cell {t.cell_no} ---\n```python\n{t.code.rstrip()}\n```" for t in cells)
        results = result_lines(run)
        agreed = [f"{k}. {line}" for k, line in enumerate(briefs.figure_lines(run.brief), 1)]
        parts = ([f"QUESTION:\n{run.question.strip()}"] + ([hint_block(run)] if run.hints else [])      # a hint may be about the drawing
                 + ([(FIGURES_AGREED_HINT if run.hints else FIGURES_AGREED) + "\n" + "\n".join(agreed)] if agreed else []))
        for d in drafts.agreed(run):                  # the cell that drew them before the run: the figure follows its draft
            drew = ", ".join(f'"{t}"' for t in d["titles"]) + (" - on made-up numbers: " + ", ".join(f'"{t}"' for t in d["made_up"]) if d["made_up"] else "")
            parts.append(f"{FIGURES_DRAFT} (it drew {drew}):\n```python\n{d['code'].rstrip()}\n```")
        parts += ["THE REPORT, AS WRITTEN:\n" + (report_text or "").strip(),
                  "THE CELLS (their code; the variables they define are in the kernel):\n" + code]
        if results:
            parts.append("RESULTS (the lines the cells printed; the report quotes these):\n" + "\n".join(results))
        if run.note:
            parts.append("YOUR NOTE (as you last wrote it):\n" + run.note)
        return "\n\n".join(parts)

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
        block = f"REVIEW ({latest.text} - answer it in your STEP):\n" + own
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
        parts = ([f"QUESTION:\n{run.question.strip()}"] + ([self._brief(run)] if run.brief else []) + ([hint_block(run)] if run.hints else [])
                 + [f"DATA:\n{self.data_description}"])
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
        """Each analyst turn in order, one entry: its own account (the STEP), its action, the outcome - the first
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
            lines.append(f"- turn {k}: {th or '(no step written)'} | {what}")
        return lines

    def _review(self, run: Run, budget: Budget, after_turn: Optional[int] = None, report: Optional[str] = None):
        """One call on the Reviewer seat with the reviewer's own prompt; the session hands it the cells to check (2026-10-06,
        replacing the SHOW rounds). Returns (review or None, cost). A review that names no verdict is not used: the run
        goes on as if none had been asked for. Its Checked lines join the verification ledger; a REPORT binds only when
        every cell it cites has been checked, in this review or an earlier one."""
        self.emit({"type": "turn_start", "run": run.id, "turn": "review", "of": budget.turns, "review": True})
        t0 = time.time()
        user, sent = self._review_input(run, budget, after_turn, report)
        text, usage_r = self.llm(reviewer(self.context, brief=bool(run.brief), hint=bool(run.hints)), user, review=True)    # the Words lens only with context, the brief only with one, the hint only in a branch
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
                    checked=[{"cell": c, "text": t, "ok": checked_ok(t), "partly": checked_verdict(t) == "partly"} for c, t in rv["checked"]], recheck=list(rv["recheck"]))
        if report is None and rv["verdict"] == "REPORT" and not rv["binding"]:
            missing = [c for c in rv["cited"] if c not in rv["checked_cells"]]
            turn.stdout = "not binding: " + ("the reviewer cites no cell" if not rv["cited"] else
                                             "no review has checked " + ", ".join(f"cell {c}" for c in missing) + ", which it cites")
        run.turns.append(turn)
        self._save()
        return rv, cost

    def _questions(self, run: Run) -> List[str]:
        """The question and the earlier questions of the thread, and the hints given on the way: what the person asked
        for, as the reach record reads it."""
        path = self.nb.path(run.id)
        return [r.question for r in path] + [h["text"] for r in path for h in r.hints or []]

    def _emit_turn(self, run: Run, turn: Turn) -> None:
        ev = {"type": turn.kind, "run": run.id, "note": turn.note}
        if turn.kind == "cell":
            ev.update(code=turn.code, stdout=turn.stdout, error=turn.error, cell_no=turn.cell_no, figures=turn.figures,
                      reaches=list(turn.reaches or []), refused=turn.refused or "",       # the reach record (2026-10-28)
                      elapsed=turn.elapsed, kept=turn.kept)
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
