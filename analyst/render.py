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


def _cell_html(turn: Turn, index: int) -> str:
    failed = bool(turn.error)
    idx = f"In&nbsp;[{turn.cell_no}]" if turn.cell_no else f"In&nbsp;[&times;]"
    title = _first_line(turn.code)
    lines = len((turn.code or "").splitlines())
    parts = [f'<div class="nb-cell{" nb-cell--failed" if failed else ""}">']
    parts.append(f'<div class="nb-cell-head"><span class="nb-cell-idx">{idx}</span>'
                 f'<span class="nb-cell-title">{title}</span>'
                 f'<span class="nb-cell-meta">{lines} lines{" · failed, rolled back" if failed else ""}'
                 f'{" · " + str(len(turn.figures)) + " fig" if turn.figures else ""}</span></div>')
    if turn.thinking:
        parts.append(f'<div class="nb-think">{html.escape(turn.thinking.strip()[:1200])}</div>')
    parts.append(f'<pre class="nb-code"><code class="language-python">{_pre(turn.code, 12000)}</code></pre>')
    if failed:
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


def _step_html(turn: Turn, index: int) -> str:
    kind = turn.kind
    if kind in ("show", "names", "recall", "search"):
        label = {"show": "Re-opened a cell", "names": "Kernel names", "recall": "Recalled from memory", "search": "Web search"}[kind]
        body = turn.stdout or ""
        return (f'<details class="nb-step"><summary><span class="nb-chevron"></span><span class="nb-out-label">{label}</span>'
                f'<span class="nb-out-peek">{_first_line(body, 110)}</span></summary><pre class="nb-out-body">{_pre(body, 6000)}</pre></details>')
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
