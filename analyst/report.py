"""Reports: the analyst writes them; this module checks and prepares them.

Two guards the model never sees:
  1. every number in the technical report exists in a cell output on the path;
  2. every number in the simplified rewrite exists in the technical report.
A mismatch is a visible disclosure, never a silent edit.

Also: cell and figure references ([cell 7], [fig 7]), and a repair that makes
every markdown table render.
"""
from __future__ import annotations

import re
from typing import Iterable, List, Set

CELL_REF_RE = re.compile(r"\[cell\s+(\d+)\]", re.I)
FIG_REF_RE = re.compile(r"\[fig\s+(\d+)\]", re.I)
_NUM_RE = re.compile(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?(?![\w.])")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def cited_cells(text: str) -> List[int]:
    return sorted({int(m.group(1)) for m in CELL_REF_RE.finditer(text or "")})


def referenced_figures(text: str) -> List[int]:
    return sorted({int(m.group(1)) for m in FIG_REF_RE.finditer(text or "")})


def _numbers(text: str, min_len: int = 2) -> Set[str]:
    """Numeric literals worth checking: at least `min_len` significant digits
    (so '2', '10' and years-as-labels do not trip the guard), thousands
    separators removed, sign dropped."""
    out = set()
    for m in _NUM_RE.finditer(text or ""):
        tok = m.group(0).lstrip("+-").replace(",", "")
        digits = re.sub(r"[^\d]", "", tok.split("e")[0].split("E")[0])
        if len(digits) >= min_len and not re.fullmatch(r"(19|20)\d\d", tok):
            out.add(tok)
    return out


def _present(tok: str, blob: str) -> bool:
    """Exact text, or the same value at the stated precision (1.699e4 ~ 16991.6;
    1018 ~ 1017.71)."""
    if tok in blob:
        return True
    try:
        v = float(tok)
    except ValueError:
        return False
    dec = len(tok.split(".")[1]) if "." in tok and "e" not in tok.lower() else 0
    for m in _NUM_RE.finditer(blob):
        try:
            w = float(m.group(0).replace(",", ""))
        except ValueError:
            continue
        if abs(w - v) <= 0.5 * 10 ** (-dec) + 1e-12:
            return True
    return False


def numbers_missing(text: str, sources: Iterable[str]) -> List[str]:
    """Numbers in `text` that appear in none of `sources`."""
    blob = "\n".join(s or "" for s in sources)
    return sorted(t for t in _numbers(text) if not _present(t, blob))


def guard_technical(report: str, cell_outputs: Iterable[str]) -> str:
    """Disclosure line for the technical report, or '' when clean."""
    missing = numbers_missing(report, cell_outputs)
    if not missing:
        return ""
    shown = ", ".join(missing[:8]) + (" ..." if len(missing) > 8 else "")
    return (f"CHECK: {len(missing)} number(s) in this report were not printed by any cell "
            f"({shown}). Treat them as unverified.")


def guard_rewrite(rewrite: str, report: str) -> str:
    missing = numbers_missing(rewrite, [report])
    if not missing:
        return ""
    shown = ", ".join(missing[:8]) + (" ..." if len(missing) > 8 else "")
    return (f"CHECK: {len(missing)} number(s) in the plain-language version do not appear in the "
            f"technical report ({shown}).")


def repair_markdown_tables(text: str) -> str:
    """Rebuild every separator row to the header's cell count so the table
    renders; consistent tables and prose pass through byte-identical."""
    if not text or "|" not in text:
        return text or ""
    lines = text.split("\n")

    def cells(line):
        s = line.strip()
        s = s[1:] if s.startswith("|") else s
        s = s[:-1] if s.endswith("|") else s
        return [c.strip() for c in s.split("|")]

    out, i, in_code = [], 0, False
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("```"):
            in_code = not in_code
        if (not in_code and line.lstrip().startswith("|") and i + 1 < len(lines)
                and _TABLE_SEP_RE.match(lines[i + 1])):
            n = len(cells(line))
            out.append(line)
            out.append("|" + "|".join(["---"] * n) + "|")
            i += 2
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                out.append(lines[i])
                i += 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def resolve_figures(text: str, figures_by_cell: dict) -> List[dict]:
    """The figure payloads a report references, in order of first mention.
    `figures_by_cell` maps cell number -> list of plot payloads."""
    out, seen = [], set()
    for m in FIG_REF_RE.finditer(text or ""):
        n = int(m.group(1))
        if n in seen:
            continue
        seen.add(n)
        for k, fig in enumerate(figures_by_cell.get(n) or []):
            out.append({"cell": n, "index": k, "figure": fig})
    return out
