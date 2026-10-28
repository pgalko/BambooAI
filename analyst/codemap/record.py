"""The ChainRecord (blueprint section 3): everything the extractor needs about one chain, as one JSON-able dict, built
from the Run and its thread. Tests build it from the fixtures instead. The host supplies the inputs the chain was
offered (`map_inputs`, 7.6); without them the record is drawn from `run.data` alone."""
import re

from .. import tools
from ..notebook import purpose_of
from .extract import file_label
from .words import CONTEXT_LABEL, PRIMARY_LABEL

_VERDICT_RE = re.compile(r"Verdict:\s*(TEST|NARROW|REPORT)", re.I)
_PROBLEM_RE = re.compile(r"^- Most consequential problem:\s*(.*)$", re.M)


def turn_numbers(run):
    """Each turn's number as the analysis counts (Notebook.failed_attempts): a review, a rewrite and the figures step
    are not turns; None for those."""
    out, n = [], 0
    for t in run.turns:
        if t.kind in ("review", "rewrite") or getattr(t, "step", ""):
            out.append(None)
        else:
            n += 1
            out.append(n)
    return out


def inputs_from_data(run, context=False):
    """The inputs as `run.data` alone gives them: the primary with its columns, each auxiliary file with none."""
    data = run.data or {}
    out = []
    if data.get("df_id") or data.get("columns"):
        cols = [c.get("name") if isinstance(c, dict) else str(c) for c in data.get("columns") or []]
        out.append(dict(kind="primary", label=PRIMARY_LABEL, name=data.get("name") or data.get("source") or PRIMARY_LABEL, columns=[c for c in cols if c],
                        detail=(f"{data['rows']} rows x {len(cols)} columns" if data.get("rows") and cols else "")))
    for p in data.get("aux") or []:
        out.append(dict(kind="file", label=file_label(str(p)), path=str(p), columns=[]))
    if context:
        out.append(dict(kind="context", label=CONTEXT_LABEL))
    return out


def chain_record(nb, run, inputs=None, context=False, earlier=None, registry_start=None):
    """The record of one run. `inputs` is the host's list (7.6) or None; `earlier` the merged exports of the computed
    path's earlier runs; `registry_start` what the kernel held when the chain began."""
    nums = turn_numbers(run)
    cells, failed, events = [], [], []
    last_cell = 0
    path = nb.path(run.id) if nb is not None else [run]
    for r in path[:-1]:
        for t in r.cells():
            last_cell = t.cell_no or last_cell
    captions = {}
    for n, cap in re.findall(r"^- \[fig (\d+)\] (.*)$", run.report or "", re.M):
        captions.setdefault(int(n), []).append(cap.strip())
    for t, num in zip(run.turns, nums):
        if t.kind == "cell" and t.cell_no:
            figures = bool(getattr(t, "step", "") == "figures")
            caps = captions.get(t.cell_no, [])
            cells.append(dict(cell=t.cell_no, turn=None if figures else num, kind="figures" if figures else "analysis",
                              step=("Figures: " + " | ".join(caps)) if figures else (t.thinking or ""), code=t.code or "", output=t.stdout or "",
                              registry=dict(getattr(t, "registry", {}) or {}), results=[dict(k) for k in (t.results or [])],
                              figures=len(t.figures or []), captions=caps,
                              reaches=[dict(r) for r in (getattr(t, "reaches", None) or [])]))     # what the cell touched outside the data (2026-10-28)
            last_cell = t.cell_no
        elif t.kind == "cell" and t.error:
            # a cell the executor refused before it ran rides with the failed attempts, with its restricted word: the view shows
            # it as its own state, not a failure of the code (2026-10-28)
            failed.append(dict(turn=num, after_cell=last_cell, step=purpose_of(t), error=tools.exception_line(t.error),
                               refused=str(getattr(t, "refused", "") or "")))
        elif t.kind == "review":
            m = _VERDICT_RE.search(t.thinking or "")
            p = _PROBLEM_RE.search(t.note or "")
            if (t.text or "") == "after the report":
                events.append(dict(type="final", verdict=m.group(1).upper() if m else "", text=(p.group(1) if p else "")[:220]))
            else:
                after = re.search(r"after turn (\d+)", t.text or "")
                events.append(dict(type="review", turn=int(after.group(1)) if after else num, verdict=m.group(1).upper() if m else "",
                                   text=(p.group(1) if p else "")[:220]))
        elif t.kind == "report":
            events.append(dict(type="report", turn=num))
    path_ids = [r.id for r in path]
    path_cells = {}
    for r in path:
        for t in r.cells():
            path_cells[str(t.cell_no)] = r.id
    titles = {r.id: (r.question or "") for r in path}
    return dict(chain_id=run.id, question=run.question or "", title=run.title or "", mode=getattr(run, "mode", "") or "",
                inputs=list(inputs) if inputs is not None else inputs_from_data(run, context),
                cells=cells, failed=failed, events=events, report=run.report or "", turns=sum(1 for n in nums if n),
                searches=sum(1 for t in run.turns if t.kind == "search"), reads=sum(1 for t in run.turns if t.kind == "read"),
                ideas=any(t.kind == "ideas" for t in run.turns),
                path=path_ids, path_cells=path_cells, titles=titles,
                registry_start=dict(registry_start or {}), earlier=earlier or dict(names={}, funcs={}),
                sandbox=dict(getattr(run, "sandbox", None) or {}))              # the box the cells ran on, for the reach report (2026-10-28)
