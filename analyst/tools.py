"""The analyst's tools. Each is a plain function over an object the platform
already has: the kernel (PersistentKernel or RemoteKernel - same interface),
the knowledge pack, the search seam, the output channel to the user.

Nothing here decides anything. The analyst chooses; these carry it out and
return text for the next turn's context.
"""
from __future__ import annotations

import logging
import re
from typing import Callable, Optional, Tuple, List

logger = logging.getLogger(__name__)

MAX_OUTPUT_CHARS = 2_000_000  # a disk guard only: the record keeps a cell's output whole; the prompt's VIEW is capped (notebook.render_cells) and SHOW n opens the whole


def run_cell(kernel, code: str) -> Tuple[str, str, List[dict], List[dict]]:
    """Run one cell. Returns (stdout, error, figures, results) - the results being the records the kernel kept
    for each RESULT(...) call (2026-10-06). A failed cell is rolled back by the kernel; nothing of it survives
    except the traceback we show."""
    stdout, error, plots = kernel.execute(code)
    stdout = (stdout or "")
    if len(stdout) > MAX_OUTPUT_CHARS:
        stdout = stdout[:MAX_OUTPUT_CHARS].rstrip() + f"\n... [output truncated at {MAX_OUTPUT_CHARS} characters]"
    return stdout, (error or ""), list(plots or []), list(getattr(kernel, "last_results", []) or [])


PRELUDE = "import pandas as pd\nimport numpy as np\nimport matplotlib\nmatplotlib.use('Agg')\nimport matplotlib.pyplot as plt"


def rebind_aliases(kernel) -> None:
    """Re-import the aliases the contract promises. A kernel from before
    2026-09-05 drops them at every rollback (they are never checkpointed);
    the current kernel binds them at start and this is a harmless no-op.
    Uncommitted: it is not part of the record and not replayed."""
    try:
        kernel.execute(PRELUDE, commit=False)
    except TypeError:                                   # a kernel without the commit flag
        try:
            kernel.execute(PRELUDE)
        except Exception:                               # noqa: BLE001
            pass
    except Exception:                                   # noqa: BLE001
        pass


def run_prelude(kernel, source: str) -> None:
    """Source the host wants in the kernel - the document objects - run as a committed step of the kernel's
    own history (so the kernel recovers it itself after a rollback and lists its names at once; an uncommitted
    step is invisible to the registry until the next commit). It is not a cell of the session's record and the
    session never replays it: the host prefixes it to the replay script."""
    if not source or kernel is None:
        return
    try:
        out = kernel.execute(source)
        err = out[1] if isinstance(out, tuple) and len(out) > 1 else None
        if err:
            logger.warning("kernel prelude raised: %s", str(err).strip().splitlines()[-1][:200])
    except Exception as exc:                            # noqa: BLE001
        logger.warning("kernel prelude failed: %s", exc)




def names(kernel, limit: int = 200) -> str:
    """The kernel's user-defined names and their types - no previews."""
    try:
        reg = kernel.describe_namespace(max_items=limit)
    except TypeError:
        reg = kernel.describe_namespace()
    if isinstance(reg, str):                       # PersistentKernel renders a text registry
        lines = [ln for ln in reg.splitlines() if ln.strip()]
        return "\n".join(lines[:limit]) if lines else "(no user-defined names yet)"
    items = (reg or {}).get("namespace") or []
    lines = []
    for it in items[:limit]:
        if isinstance(it, dict):
            lines.append(f"{it.get('name')}: {it.get('type', '')}".rstrip(": "))
        else:
            lines.append(str(it))
    return "\n".join(lines) if lines else "(no user-defined names yet)"


def recall(pack_retrieve: Optional[Callable[[str], list]], query: str, limit: int = 5) -> str:
    """Methods this workspace has learned, relevant to the query. `pack_retrieve`
    is knowledge_pack.retrieve bound to the user's pack, or None when memory is off."""
    if pack_retrieve is None:
        return "(memory is not enabled in this workspace)"
    try:
        cards = pack_retrieve(query) or []
    except Exception as exc:                          # noqa: BLE001
        logger.warning("recall failed: %s", exc)
        return f"(memory lookup failed: {exc})"
    if not cards:
        return "(nothing relevant in memory)"
    out = []
    for c in cards[:limit]:
        if isinstance(c, dict):
            title = c.get("title") or c.get("name") or "card"
            body = c.get("method") or c.get("body") or c.get("text") or ""
            out.append(f"- {title}: {str(body)[:600]}")
        else:
            out.append(f"- {str(c)[:600]}")
    return "\n".join(out)


def search(search_fn: Optional[Callable[[str], str]], query: str) -> str:
    """Web search through the platform's existing seam (a callable taking the
    query and returning text), or a note that it is off."""
    if search_fn is None:
        return "(web search is not enabled)"
    try:
        return search_fn(query) or "(no results)"
    except Exception as exc:                          # noqa: BLE001
        logger.warning("search failed: %s", exc)
        return f"(search failed: {exc})"


def read(read_fn: Optional[Callable[[str], str]], arg: str) -> str:
    """A document read through the host's seam (a callable taking 'D2 what you are looking for' or
    'ALL ...' and returning the digest), or a note that no documents can be read here."""
    if read_fn is None:
        return "(documents are not available in this workspace)"
    try:
        return read_fn(arg) or "(the read returned nothing)"
    except Exception as exc:                          # noqa: BLE001
        logger.warning("read failed: %s", exc)
        return f"(read failed: {exc})"


def ask_user(emit: Optional[Callable[[dict], None]], question: str) -> None:
    """Hand a question to the person. The run pauses (status 'asked'); the
    person's reply arrives as the next run's question with this run as parent."""
    if emit:
        emit({"type": "question_to_user", "text": question})


_EXC_LINE = re.compile(r"^(?:[A-Za-z_][\w.]*)(?:Error|Exception|Warning|Exit|Interrupt|Fault)\b.*$")
_FRAME = re.compile(r'^\s*File "([^"]+)", line (\d+)')


def condense_error(err: str, max_chars: int = 1400, hint_lines: int = 10, code: str = "") -> str:
    """The part of a traceback a person fixes from: the exception line first,
    then where in the cell it happened, then the message's first lines (the
    'Did you mean' hint, the first valid properties). Verbose tails - Plotly's
    property lists, pandas' hundred-line messages - are cut, never the exception.
    """
    text = (err or "").replace("\r", "")
    lines = [ln.rstrip() for ln in text.strip().splitlines()]
    lines = [ln for ln in lines if not ln.startswith("[delv-e:")]
    if not lines:
        return ""
    exc_idx = None
    for i, ln in enumerate(lines):
        if _EXC_LINE.match(ln):
            exc_idx = i                     # the LAST such line is the raised exception (chained tracebacks)
    if exc_idx is None:
        body = "\n".join(lines)
        return body if len(body) <= max_chars else body[:max_chars] + "\n[... shortened]"
    where = []
    src = (code or "").splitlines()
    for i in range(exc_idx):
        m = _FRAME.match(lines[i])
        if m and m.group(1) == "<string>":
            n = int(m.group(2))
            # exec'd code has no source in the traceback: take the line from the cell itself
            code_line = src[n - 1].strip() if 0 < n <= len(src) else ""
            where.append(f"in your cell, line {n}" + (f":  {code_line[:160]}" if code_line else ""))
    frames = [lines[i].strip() for i in range(max(0, exc_idx - 6), exc_idx)
              if _FRAME.match(lines[i]) and "<string>" not in lines[i] and ", in <module>" not in lines[i]]
    hint = []
    for ln in lines[exc_idx + 1: exc_idx + 1 + 60]:
        if ln.strip() in ("[...truncated]", "^^^^^^"):
            continue
        hint.append(ln)
        if len(hint) >= hint_lines:
            hint.append("[... message shortened]")
            break
    out = [lines[exc_idx]]
    out += where[-2:] or []
    if frames:
        out.append("via " + " > ".join(f.split(", in ")[-1] if ", in " in f else f for f in frames[-3:]))
    out += hint
    text = "\n".join(out)
    return text if len(text) <= max_chars else text[:max_chars] + "\n[... shortened]"


def exception_line(err: str) -> str:
    """The one line that names what went wrong."""
    for ln in reversed((err or "").strip().splitlines()):
        if _EXC_LINE.match(ln.strip()):
            return ln.strip()
    for ln in reversed((err or "").strip().splitlines()):
        if ln.strip() and not ln.startswith("[delv-e:") and ln.strip() not in ("[...truncated]", "^^^^^^"):
            return ln.strip()
    return ""
