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

# a citation of one or several cells: [cell 7], [cells 6, 7, 9], [cell 5, cell 6], [cells 6-9] (2026-10-05: reports cite
# several at once, and the replay read only the single form)
CELL_REF_RE = re.compile(r"\[cells?\s+(\d+(?:\s*(?:,|;|and|&|-|\u2013)\s*(?:cells?\s*)?\d+)*)\]", re.I)
UNIT_REF_RE = re.compile(r"\[(D\d+\.\d+)\]")                 # a document passage, [D1.17] (docs/DOCUMENTS_DESIGN.md D45)
FIG_REF_RE = re.compile(r"\[figs?\s+(\d+(?:\s*(?:,|;|and|&|-|\u2013)\s*(?:figs?\s*)?\d+)*)\]", re.I)


def _ref_numbers(group: str) -> Set[int]:
    """The numbers of one citation, with a range a-b read whole."""
    out: Set[int] = set()
    for part in re.split(r"\s*(?:,|;|and|&)\s*", group):
        nums = [int(n) for n in re.findall(r"\d+", part)]
        if len(nums) == 2 and re.search(r"\d\s*[-\u2013]\s*\d", part) and nums[0] <= nums[1] <= nums[0] + 200:
            out |= set(range(nums[0], nums[1] + 1))
        else:
            out |= set(nums)
    return out
_NUM_RE = re.compile(r"(?<![\w.])[-+]?\d[\d,]*(?:\.\d+)?(?:[eE][-+]?\d+)?(?![\w.])")
_TABLE_SEP_RE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def cited_cells(text: str) -> List[int]:
    return sorted({n for m in CELL_REF_RE.finditer(text or "") for n in _ref_numbers(m.group(1))})


def cited_units(text: str) -> List[str]:
    """Document passages the report cites, as [D1.17], in order of first appearance."""
    seen, out = set(), []
    for m in UNIT_REF_RE.finditer(text or ""):
        if m.group(1) not in seen:
            seen.add(m.group(1)); out.append(m.group(1))
    return out


def guard_units(missing: Iterable[str]) -> str:
    """Cited passages that are not in the thread's documents, disclosed as the number check discloses."""
    missing = list(missing)
    if not missing:
        return ""
    shown = ", ".join(f"[{u}]" for u in missing[:8]) + (" ..." if len(missing) > 8 else "")
    return (f"CHECK: {len(missing)} cited passage(s) {'are' if len(missing) != 1 else 'is'} not in this thread's documents: {shown}. "
            f"A passage is evidence only when a READ returned it or a cell read it; treat these citations as unverified.")


def referenced_figures(text: str) -> List[int]:
    return sorted({n for m in FIG_REF_RE.finditer(text or "") for n in _ref_numbers(m.group(1))})


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
    1018 ~ 1017.71; 1.49e+04 ~ 14901.6 - a mantissa's decimals less the exponent,
    so a number printed at four significant digits matches its full value)."""
    if tok in blob:
        return True
    try:
        v = float(tok)
    except ValueError:
        return False
    mant, _, exp = tok.lower().partition("e")
    dec = (len(mant.split(".")[1]) if "." in mant else 0) - (int(exp) if exp else 0)
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
