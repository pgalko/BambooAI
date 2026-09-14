"""Replay: the executable record is the reproduction.

assemble()  - the cells a report cites, plus every earlier cell that defines a
              name they use, in execution order, as one script. Dead ends fall
              out because nothing cites them.
rehydrate() - run a list of cells in a fresh kernel (a branch, a continuation
              after a dead kernel, a replay on another dataset). Same code, same
              order; stops at the first failure and says which cell.
verify()    - run the assembled script in a fresh kernel and check that the
              numbers the report took from the cited cells appear again.
"""
from __future__ import annotations

from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple

from .notebook import Turn
from .report import cited_cells as _cited, referenced_figures, _numbers, _present


def cited_cells(report: str):
    """Cells the report cites, as [cell n] or [fig n] - a figure lives in the cell that drew it."""
    return sorted(set(_cited(report)) | set(referenced_figures(report)))

def assemble(cells: List[Turn], report: str, own: Optional[List[Turn]] = None) -> Tuple[str, List[int]]:
    """Return (script, cell numbers included): the committed record, in execution
    order, up to and including the last cell the report cites. Nothing is pruned -
    a cell may depend on an earlier one in ways no static trace sees (a column
    added to df, a module imported, a setting changed), and the record that ran
    is the reproduction. When the report cites nothing, the record up to this
    run's last cell. `cells` is the whole path (earlier runs' cells included)."""
    by_no: Dict[int, Turn] = {c.cell_no: c for c in cells if c.cell_no is not None}
    cited = [n for n in cited_cells(report) if n in by_no]
    own_nos = [c.cell_no for c in (own if own is not None else cells) if c.cell_no is not None]
    last = max(cited) if cited else (max(own_nos) if own_nos else 0)
    order = [n for n in sorted(by_no) if n <= last]
    # Figures: earlier runs' cells must RUN (the state), but their figures are not this
    # run's plots (2026-09-07: a follow-up that fixed a plot returned both). Capture is
    # on for this run's own cells and for any earlier figure the report cites as [fig n].
    wanted = set(own_nos) | {n for n in referenced_figures(report) if n in by_no}
    parts = ["# Assembled from the analysis notebook: the committed cells in execution order, up to the last cell the report cites.",
             "# `df` is the dataset the analysis ran on.",
             "import pandas as pd", "import numpy as np", "import matplotlib", "matplotlib.use('Agg')", "import matplotlib.pyplot as plt",
             "# figures are captured only for this run's cells (and cited earlier figures); earlier runs' cells still run for their state",
             "_bamboo_capture = [True]",
             "try:",
             "    import plotly.io as _bamboo_pio",
             "    _bamboo_show = _bamboo_pio.show",
             "    def _bamboo_gated_show(fig, *a, **k):",
             "        if _bamboo_capture[0]:",
             "            return _bamboo_show(fig, *a, **k)",
             "    _bamboo_pio.show = _bamboo_gated_show",
             "except Exception:",
             "    pass"]
    capturing = True
    for n in order:
        want = n in wanted
        if want != capturing:
            parts.append(f"_bamboo_capture[0] = {want}")
            capturing = want
        parts.append(f"\n# --- cell {n} ---\n{by_no[n].code.rstrip()}")
    return "\n".join(parts) + "\n", order


def rehydrate(kernel, cells: Iterable[Turn]) -> Tuple[int, str]:
    """Run committed cells in order in `kernel`. Returns (cells run, error or '').
    Stops at the first failure so the caller knows exactly where the record broke."""
    n = 0
    for c in cells:
        _, err, _ = kernel.execute(c.code)
        if err:
            return n, f"cell {c.cell_no} failed on replay: {err.strip().splitlines()[-1]}"
        n += 1
    return n, ""


def compare(cells: List[Turn], report: str, stdout: str, err: str = "", n_cells: int = 0) -> Tuple[str, str]:
    """Judge a replay's output against the numbers the report took from the
    cited cells. Returns (status, status line); status: reproduced | differed | failed."""
    if err:
        return "failed", f"Replay failed: the assembled script stopped with an error ({err.strip().splitlines()[-1][:160]})."
    by_no = {c.cell_no: c for c in cells}
    expected = set()
    for n in cited_cells(report):
        if n in by_no:
            expected |= _numbers(by_no[n].stdout or "")
    if not expected:
        return "reproduced", "Replay ran without error (the report cites no numbered cells to compare)."
    missing = sorted(t for t in expected if not _present(t, stdout or ""))
    if missing:
        shown = ", ".join(missing[:6]) + (" ..." if len(missing) > 6 else "")
        return "differed", f"Replay ran but {len(missing)} of {len(expected)} cited numbers did not reappear ({shown})."
    return "reproduced", f"Replay reproduced the cited results in a fresh run ({n_cells} cells, {len(expected)} numbers)."


def verify(kernel_factory: Callable[[], object], cells: List[Turn], report: str) -> Tuple[str, str, str]:
    """Assemble, run in a fresh kernel, compare. Returns (status, status line, script)."""
    script, order = assemble(cells, report)
    kernel = kernel_factory()
    try:
        stdout, err, _ = kernel.execute(script)
    finally:
        try:
            kernel.cleanup()
        except Exception:                                # noqa: BLE001
            pass
    status, line = compare(cells, report, stdout or "", err or "", len(order))
    return status, line, script
