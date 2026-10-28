"""The Investigation tab as a notebook.

The browser renders this tab through its markdown pipeline, which passes raw
HTML blocks through untouched *until a blank line*. So the whole notebook is
one HTML block with no blank line inside it: empty lines in code and output
become a non-breaking space. Highlighting and LaTeX are applied by the page
(``pre code`` blocks, KaTeX delimiters), so the HTML only has to be well formed.
"""
from __future__ import annotations

import html
import re
from typing import List

from .notebook import Run, Turn

_BLANK = re.compile(r"\n[ \t]*(?=\n)")


def _pre(text: str, limit: int = 20000) -> str:
    """Escaped text for a <pre>, with no blank lines (they would end the HTML block)."""
    text = (text or "")
    if len(text) > limit:
        text = text[:limit].rstrip() + f"\n… [{len(text) - limit:,} more characters in the stored record]"
    text = html.escape(text, quote=False)
    text = _BLANK.sub("\n\u00a0", text)
    return text.replace("\r", "")


def _first_line(text: str, width: int = 90) -> str:
    for ln in (text or "").splitlines():
        s = ln.strip()
        if s and not s.startswith("#"):
            return html.escape(s[:width], quote=False)
    return ""


def _note_html(note: str) -> str:
    rows = []
    for ln in (note or "").splitlines():
        s = ln.strip().lstrip("-• ").strip()
        if not s:
            continue
        key, sep, val = s.partition(":")
        if sep and len(key) <= 40:
            rows.append(f'<div class="nb-note-row"><span class="nb-note-key">{html.escape(key.strip())}</span>'
                        f'<span class="nb-note-val">{html.escape(val.strip())}</span></div>')
        else:
            rows.append(f'<div class="nb-note-row"><span class="nb-note-val">{html.escape(s)}</span></div>')
    if not rows:
        rows.append('<div class="nb-note-row"><span class="nb-note-val nb-muted">no note yet</span></div>')
    return '<div class="nb-note"><div class="nb-note-title">Working note</div>' + "".join(rows) + "</div>"


# the code map's eye on a committed cell (2026-10-24): the cell's row in the Steps view; the chain is the one on screen, as
# the closing card's link has it; inline, so a saved favourite's cells keep it, and silent on a page without the module
_MAP_EYE = ('<button type="button" class="nb-cell-map" data-cell="{n}" title="This cell in the code map" aria-label="This cell in the code map" '
            'onclick="if(window.CodeMapUI)CodeMapUI.open(null,{{cell:{n}}})">'
            '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"></circle>'
            '<path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7z"></path></svg></button>')


def _cell_html(turn: Turn, index: int) -> str:
    refused = str(getattr(turn, "refused", "") or "")  # a cell the executor refused before it ran (2026-10-28): its own state, not a failure of the code
    failed = bool(turn.error) and not refused
    skipped = not failed and not refused and not turn.cell_no   # a cell the session did not run: a figure cell during the analysis (2026-10-11)
    idx = f"In&nbsp;[{turn.cell_no}]" if turn.cell_no else ("In&nbsp;[&ndash;]" if skipped or refused else "In&nbsp;[&times;]")
    title = _first_line(turn.code)
    lines = len((turn.code or "").splitlines())
    reach = _reach_html(getattr(turn, "reaches", None) or [])
    parts = [f'<div class="nb-cell{" nb-cell--failed" if failed else ""}{" nb-cell--skipped" if skipped else ""}{" nb-cell--restricted" if refused else ""}">']
    parts.append(f'<div class="nb-cell-head"><span class="nb-cell-idx">{idx}</span>'
                 f'<span class="nb-cell-title">{title}</span>'
                 f'<span class="nb-cell-meta">{lines} lines{" · failed, rolled back" if failed else ""}{" · not run" if skipped or refused else ""}'
                 f'{" · figures step" if getattr(turn, "step", "") == "figures" else ""}'
                 f'{" · " + str(len(turn.figures)) + " fig" if turn.figures else ""}</span>' + reach
                 + (_MAP_EYE.format(n=turn.cell_no) if turn.cell_no else "") + '</div>')
    if turn.thinking:
        parts.append(f'<div class="nb-think">{html.escape(turn.thinking.strip()[:1200])}</div>')
    parts.append(f'<pre class="nb-code"><code class="language-python">{_pre(turn.code, 12000)}</code></pre>')
    if refused:
        parts.append(f'<div class="nb-out nb-out--restricted"><span class="nb-out-label">Not run</span>'
                     f'<span class="nb-out-peek">restricted operation ({html.escape(refused, quote=False)}): the executor does not run it</span></div>')
    elif failed:
        from .tools import condense_error, exception_line
        tail = condense_error(turn.error, max_chars=2400, hint_lines=14)
        last = html.escape(exception_line(turn.error)[:140], quote=False)
        parts.append(f'<details class="nb-out nb-out--error"><summary><span class="nb-chevron"></span>'
                     f'<span class="nb-out-label">Error</span><span class="nb-out-peek">{last}</span></summary>'
                     f'<pre class="nb-out-body">{_pre(tail)}</pre></details>')
    else:
        out = turn.stdout or ""
        peek = _first_line(out, 110) or "(no output)"
        n = len(out)
        parts.append(f'<details class="nb-out"><summary><span class="nb-chevron"></span>'
                     f'<span class="nb-out-label">Output</span><span class="nb-out-peek">{peek}</span>'
                     f'<span class="nb-cell-meta">{n:,} chars</span></summary>'
                     f'<pre class="nb-out-body">{_pre(out) if out.strip() else "(no output)"}</pre></details>')
    parts.append("</div>")
    return "".join(parts)


def _reach_html(reaches) -> str:
    """The cell's reaches outside the data as one tag in its header (2026-10-28), in the kernel's colour unless the
    question asked for them; the hover lists them."""
    from . import reach as R
    x = R.chip(reaches)
    if not x:
        return ""
    return (f'<span class="nb-reach{"" if x["tag"] == "asked" else " unasked"}" title="{html.escape(x["title"])}">'
            f'{html.escape(x["text"], quote=False)}</span>')


def _step_html(turn: Turn, index: int) -> str:
    kind = turn.kind
    if kind in ("show", "names", "recall", "search"):
        label = {"show": "Re-opened a cell", "names": "Kernel names", "recall": "Recalled from memory", "search": "Web search"}[kind]
        body = turn.stdout or ""
        return (f'<details class="nb-step"><summary><span class="nb-chevron"></span><span class="nb-out-label">{label}</span>'
                f'<span class="nb-out-peek">{_first_line(body, 110)}</span></summary><pre class="nb-out-body">{_pre(body, 6000)}</pre></details>')
    if kind == "read":
        # a READ's digest, with the ids it quoted on the step (data-units) so a [D1.17] or [C.417] chip in the answer can land
        # here (2026-10-14; READ turns had not been rendered in this view since the documents phase)
        body = turn.stdout or ""
        ids = " ".join(re.findall(r"^- \[(D\d+\.\d+|C\.\d+)\]", body, re.M))
        label = "Read the context" if re.match(r"^\s*(CTX\b|C\.\d)", turn.text or "", re.I) else "Read a document"
        return (f'<details class="nb-step nb-read" data-units="{ids}"><summary><span class="nb-chevron"></span><span class="nb-out-label">{label}</span>'
                f'<span class="nb-out-peek">{html.escape((turn.text or "")[:110], quote=False)}</span></summary><pre class="nb-out-body">{_pre(body, 8000)}</pre></details>')
    if kind == "ask":
        return f'<div class="nb-step nb-step--ask"><span class="nb-out-label">Question to you</span> {html.escape(turn.text or "")}</div>'
    if kind == "report":
        return '<div class="nb-step nb-step--done"><span class="nb-out-label">Report written</span> — see the Answer tab</div>'
    if kind == "rewrite":
        return '<div class="nb-step nb-step--done"><span class="nb-out-label">Plain-language version written</span> — see the Simplified tab</div>'
    if kind == "error":
        return f'<div class="nb-step nb-step--warn"><span class="nb-out-label">Turn lost</span> {html.escape((turn.stdout or "")[:160])}</div>'
    return ""


def notebook_html(run: Run) -> str:
    """The whole run as one HTML block: the working note, then every turn."""
    parts: List[str] = ['<div class="nb">', _note_html(run.note)]
    for i, t in enumerate(run.turns, 1):
        parts.append(_cell_html(t, i) if t.kind == "cell" else _step_html(t, i))
    parts.append("</div>")
    out = "".join(p for p in parts if p)
    # one HTML block: never a blank line inside
    return _BLANK.sub("\n\u00a0", out)
