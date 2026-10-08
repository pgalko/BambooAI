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


# the kernel's display options (delve/kernel.py sets these at import; a test holds the two lists to the same text)
DISPLAY_OPTIONS = ["pd.set_option('display.max_columns', None)",
                   "pd.set_option('display.width', None)",
                   "pd.set_option('display.max_colwidth', 200)",
                   "pd.set_option('display.max_rows', 2000)",
                   "pd.set_option('display.float_format', lambda v: f'{v:.4g}')"]
# back to the process's defaults: the last lines of the assembled script, and what the app sends on its own when a
# replay stopped before reaching them (the executor's process serves the data views too, with pandas' own formatting)
RESET_OPTIONS = "\n".join(f"pd.reset_option('{ln.split(chr(39))[1]}')" for ln in DISPLAY_OPTIONS)


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
    # up to the last cell the report cites - and to this run's last figure cell when that is later (2026-10-06: a figure
    # drawn after the last cited cell was never replayed, so it never reached the reader), or [fig n] cited after it
    own_fig = [c.cell_no for c in (own if own is not None else cells) if c.cell_no is not None and c.figures]
    fig_cited = [n for n in referenced_figures(report) if n in by_no]
    last = max([max(cited) if cited else 0, max(own_fig) if own_fig else 0, max(fig_cited) if fig_cited else 0]
               or [0]) or (max(own_nos) if own_nos else 0)
    order = [n for n in sorted(by_no) if n <= last]
    # Figures: earlier runs' cells must RUN (the state), but their figures are not this
    # run's plots (2026-09-07: a follow-up that fixed a plot returned both). Capture is
    # on for this run's own cells and for any earlier figure the report cites as [fig n].
    wanted = set(own_nos) | {n for n in referenced_figures(report) if n in by_no}
    parts = ["# Assembled from the analysis notebook: the committed cells in execution order, up to the last cell the report cites or this run's last figure cell.",
             "# `df` is the dataset the analysis ran on.",
             "import pandas as pd", "import numpy as np", "import matplotlib", "matplotlib.use('Agg')", "import matplotlib.pyplot as plt",
             "# the analysis kernel's display options (delve/kernel.py), so the replay prints what the analysis printed (2026-10-08:",
             "# under pandas defaults a 7-column crosstab printed with its middle elided to '...' and 1.49e+04 came out as 14901.6,",
             "# and four cited numbers 'did not reappear' in a replay that had reproduced them); reset at the end, since the",
             "# executor's process goes on serving the data views with its own defaults",
             *DISPLAY_OPTIONS,
             "# DS, as in the analysis kernel - a cell may call DS.load() (2026-10-05: the replay route runs a plain script, and",
             "# a figure cell that began with df = DS.load() stopped the replay before any figure was drawn)",
             "if 'DS' not in globals():",
             "    class _BambooSource:",
             "        def __init__(self, frame):",
             "            self._frame = frame.copy() if frame is not None else None",
             "        def load(self):",
             "            if self._frame is None:",
             "                print('DS: no dataset is attached to this run - nothing to load'); return None",
             "            return self._frame.copy()",
             "        def save(self, frame, name, fmt=None):   # the kernel's DS.save: a dataset for the person, in the generated folder the route passes",
             "            import os, re as _re",
             "            raw = str(name).strip(); m = _re.search(r'\\.([A-Za-z0-9]{1,8})$', raw)",
             "            ext = (fmt or (m.group(1) if m else 'csv')).lower().lstrip('.')",
             "            base = _re.sub(r'[^A-Za-z0-9_\\-]+', '_', raw[:m.start()] if m else raw).strip('_') or 'dataset'",
             "            folder = globals().get('_generated_dir') or 'generated'",
             "            os.makedirs(folder, exist_ok=True)",
             "            path = os.path.join(folder, base + '.' + ext)",
             "            if isinstance(frame, (str, bytes)):",
             "                with open(path, 'wb' if isinstance(frame, bytes) else 'w', encoding=None if isinstance(frame, bytes) else 'utf-8') as fh:",
             "                    fh.write(frame)",
             "                what = f\"{len(frame):,} {'bytes' if isinstance(frame, bytes) else 'characters'}\"",
             "            else:",
             "                if ext == 'json': frame.to_json(path, orient='records', indent=2, date_format='iso')",
             "                elif ext in ('parquet', 'pq'): frame.to_parquet(path, index=False)",
             "                elif ext in ('xlsx', 'xls'): frame.to_excel(path, index=False)",
             "                elif ext in ('txt', 'tsv'): frame.to_csv(path, index=False, sep='\\t')",
             "                else: frame.to_csv(path, index=False)",
             "                rows, cols = (frame.shape if hasattr(frame, 'shape') and len(frame.shape) == 2 else (len(frame), 1))",
             "                what = f'{rows:,} rows x {cols} columns'",
             "            print(f'DATASET: {os.path.basename(path)} - {what}, in the Dataset cache under Generated')",
             "            return path",
             "    DS = _BambooSource(globals().get('df'))",
             "# RESULT, as in the analysis kernel - a cell may call it (2026-10-06: the replay route has no kernel, and a cell",
             "# calling RESULT stopped the replay with a NameError). The same line, so the replay reproduces the cell's numbers;",
             "# no record and no typed mark - the ledger is built from the analysis run, not from the replay",
             "if 'RESULT' not in globals():",
             "    def _bamboo_decimals(values):",
             "        mags = [abs(float(v)) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool) and float(v) != 0.0]",
             "        m = min(mags) if mags else 1.0",
             "        return 0 if m >= 100 else (1 if m >= 10 else (2 if m >= 0.1 else (3 if m >= 0.01 else 5)))",
             "    def _bamboo_fmt(x, decimals=2):",
             "        if x is None or isinstance(x, bool):",
             "            return str(x)",
             "        if isinstance(x, int):",
             "            return f'{x:+,d}'",
             "        try:",
             "            v = float(x)",
             "        except (TypeError, ValueError):",
             "            return str(x)",
             "        return f'{v:+,.{decimals}f}'",
             "    def RESULT(what, estimate, low=None, high=None, unit='', direction='', test=None, corrects=None, ci=95):",
             "        if isinstance(corrects, (list, tuple, set)):",
             "            corr = '(corrects cells ' + ', '.join(str(c) for c in corrects) + ') '",
             "        else:",
             "            corr = f'(corrects cell {corrects}) ' if corrects is not None else ''",
             "        tags = (f'(test {test}) ' if test else '') + corr",
             "        dec = _bamboo_decimals((estimate, low, high))",
             "        interval = f' ({ci}% CI {_bamboo_fmt(low, dec)} to {_bamboo_fmt(high, dec)})' if low is not None and high is not None else ''",
             "        print('RESULT: ' + f\"{tags}{what}: {_bamboo_fmt(estimate, dec)}{interval}{(' ' + unit) if unit else ''}{(', ' + direction) if direction else ''}\")",
             "        return estimate",
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
    parts.append("\n# --- the executor's own display options back ---\n" + RESET_OPTIONS)
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
