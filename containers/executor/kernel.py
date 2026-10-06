"""
Persistent execution kernel for delv-e's inverted-core loop.

A single long-lived worker process holds ONE namespace. `df` is loaded once;
derived columns and intermediate objects created in step k survive into step
k+1. This is what makes analytical (not line-count) decomposition possible:
each step can stay small because its prerequisites already
live in the namespace.

Crash isolation: the worker is itself a killable subprocess. If a step hangs
(timeout) or the worker dies (OOM/segfault), the parent kills/restarts it and
replays the history of previously-successful steps to reconstruct the
namespace. Determinism of the replayed steps is the caller's responsibility
(seed your RNG).

Contract:
    kernel = PersistentKernel(df=df, analysis_root="output/exploration")
    stdout, error, plots = kernel.execute(code, analysis_dir=".../01")
    print(kernel.describe_namespace())   # registry for prompts
    kernel.cleanup()

`execute` returns the familiar (stdout, error, plots) triple so it can slot in
as the single execution surface. The namespace registry is exposed
separately via `registry` / `describe_namespace()`.
"""

import json
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading

from logger_config import get_logger

# Reuse the security blacklist and temp-file helpers: codeutils in the package, executor.py in the executor image.
from executor import BLACKLIST, _write_temp_text, _cleanup_files, _serialize_dataframe

logger = get_logger(__name__)

# Wall-clock seconds for a single step. The persistent worker means a hang on
# one step must not wedge the whole run, so on timeout we kill and restart.
# Set to give a correctly vectorized simulation comfortable headroom; a scalar
# per-sample loop will still blow past it, which is the intended signal.
STEP_TIMEOUT = 600

# Token the worker prints on its real stdout after each step completes. User
# code output is captured in-worker and written to a result file, so the only
# thing on the worker's real stdout is this control token (and the startup
# ready token). That keeps the control channel clean.
_DONE = "__DELVE_KERNEL_DONE__"
_READY = "__DELVE_KERNEL_READY__"

# Names that are part of the kernel's own plumbing and must never be surfaced
# in the namespace registry shown to the Investigator.
_INTERNAL_NAMES = {
    "df",  # handled explicitly (we show its columns, not as a generic object)
    "os", "io", "json", "sys", "traceback", "warnings",
    "matplotlib", "plt", "_mpl_figure", "pd",
    "_real_savefig", "_saved_plots", "_plot_counter", "_analysis_dir",
    "_patched_show", "_patched_savefig",
    "redirect_stdout",
}


# The worker script. Runs in a fresh interpreter; holds the persistent
# namespace in the module globals `G`. Reads one control-JSON line per step
# from stdin, execs the step's code into G (so state persists), writes a result
# JSON, then prints the done token.
_WORKER_SCRIPT = r'''
import ast, inspect, io, json, os, re, sys, traceback, warnings
import pickle as _pickle, types as _types, importlib as _importlib
warnings.filterwarnings("ignore")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.figure as _mpl_figure
import pandas as pd
import numpy as np

# Prevent pandas from SILENTLY truncating printed results. pandas defaults
# (max_rows=60, limited columns/width) insert "..." into the MIDDLE of a table,
# which would hand the Investigator/Synthesizer numbers with gaps they cannot see.
# Show all columns and full width; cap rows/cell-width only at levels no normal
# summarized result reaches (so a pathological raw dump is still bounded).
pd.set_option("display.max_columns", None)
pd.set_option("display.width", None)
pd.set_option("display.max_colwidth", 200)
pd.set_option("display.max_rows", 2000)
# Floats print at 4 significant digits: display-only, stored values keep full
# precision. Measured on a live heavy run, digits past the 4th were ~6% of the
# Investigator's prompt mass for zero decision value.
pd.set_option("display.float_format", lambda v: f"{v:.4g}")

_DONE = "__DELVE_KERNEL_DONE__"
_READY = "__DELVE_KERNEL_READY__"

_df_path = sys.argv[1] if len(sys.argv) > 1 else ""
_generated_dir = sys.argv[4] if len(sys.argv) > 4 else ""     # where DS.save puts a dataset for the person (2026-10-06)

# ---- Persistent namespace -------------------------------------------------
# Everything user code defines lands in G and survives across steps.
G = {}
G["os"] = os
# The standard aliases are part of the namespace, not something a cell must
# import (2026-09-05): a checkpoint restore rebuilds G, and names listed in
# _INTERNAL are never checkpointed - so a `pd` a cell had imported vanished
# after the first rolled-back attempt and every later cell failed with
# NameError. They are set here, at every worker start, unconditionally.
G["pd"] = pd
G["np"] = np
G["plt"] = plt

def _load_df(path):
    if path.endswith(".pkl"):
        return pd.read_pickle(path)
    if path.endswith(".parquet"):
        return pd.read_parquet(path)
    return pd.read_csv(path, low_memory=False)


class _Source:
    """DS: the dataset as attached, always recoverable (2026-10-05). `df` is the analyst's working frame and may be
    filtered, rebound or lost - a cell of the Adaptive run of 2026-10-05 reused `df` as a loop variable and the
    rest of the run paid for it. DS.load() returns a fresh copy from the file the kernel loaded; DS._check(G) is
    the line the worker appends to a step's output when `df` no longer carries the dataset's columns."""

    def __init__(self, path, frame):
        # DS exists in every run (2026-10-06): with no dataset attached it has nothing to load but it still saves - a
        # run without a dataset had spent twelve turns hunting for DS.save, which the contract promised and the
        # kernel had only defined beside a dataset
        self.path = path
        self.columns = list(frame.columns) if frame is not None else []
        self.shape = tuple(frame.shape) if frame is not None else (0, 0)

    def load(self):
        if not self.path:
            print("DS: no dataset is attached to this run - nothing to load")
            return None
        return _load_df(self.path)

    def __repr__(self):
        if not self.path:
            return "DS: no dataset attached to this run; DS.save(frame, 'name') still saves a file for the person"
        return (f"DS: the dataset as attached, {self.shape[0]} rows x {self.shape[1]} columns; "
                f"df = DS.load() restores it")

    def save(self, frame, name, fmt=None):
        """Save a dataset for the person (2026-10-06): written under the generated-datasets folder the kernel was given,
        which the Dataset cache lists under Generated and serves for download; one printed line says so. The format
        follows the name's extension (csv, json, parquet, xlsx, txt as tab-separated) or `fmt`; CSV when neither says.
        A string is written as a text file whatever the extension. The original BambooAI told the agent where to save
        in its prompt; the rebuilt analyst had no such place, so a merged dataset it 'returned' landed in the worker's
        working directory where nothing listed it."""
        import re as _re
        raw = str(name).strip()
        m = _re.search(r"\.([A-Za-z0-9]{1,8})$", raw)
        ext = (fmt or (m.group(1) if m else "csv")).lower().lstrip(".")
        base = _re.sub(r"[^A-Za-z0-9_\-]+", "_", raw[:m.start()] if m else raw).strip("_") or "dataset"
        folder = G.get("_generated_dir") or "generated"
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"{base}.{ext}")
        if isinstance(frame, (str, bytes)):
            with open(path, "wb" if isinstance(frame, bytes) else "w", encoding=None if isinstance(frame, bytes) else "utf-8") as fh:
                fh.write(frame)
            what = f"{len(frame):,} {'bytes' if isinstance(frame, bytes) else 'characters'}"
        else:
            if ext == "json":
                frame.to_json(path, orient="records", indent=2, date_format="iso")
            elif ext in ("parquet", "pq"):
                frame.to_parquet(path, index=False)
            elif ext in ("xlsx", "xls"):
                frame.to_excel(path, index=False)
            elif ext in ("txt", "tsv"):
                frame.to_csv(path, index=False, sep="\t")
            else:
                frame.to_csv(path, index=False)
            rows, cols = (frame.shape if hasattr(frame, "shape") and len(frame.shape) == 2 else (len(frame), 1))
            what = f"{rows:,} rows x {cols} columns"
        print(f"DATASET: {os.path.basename(path)} - {what}, in the Dataset cache under Generated")
        G.setdefault("_DATASETS", []).append(path)
        return path

    def _check(self, ns):
        """A one-line warning when df is gone, not a frame, or has lost columns of the dataset; '' otherwise.
        Rows are the analyst's to filter; columns dropped are the sign of a rebinding gone wrong."""
        if not self.path:
            return ""                          # no dataset attached: nothing to lose
        if "df" not in ns:
            return "(df is not defined any more; df = DS.load() restores the dataset)"
        f = ns["df"]
        if not isinstance(f, pd.DataFrame):
            return f"(df is now a {type(f).__name__}, not the dataset; df = DS.load() restores it)"
        lost = [c for c in self.columns if c not in f.columns]
        if lost:
            return (f"(df now has {f.shape[1]} of the dataset's {len(self.columns)} columns and {f.shape[0]:,} of "
                    f"{self.shape[0]:,} rows - {', '.join(lost[:4])}{'...' if len(lost) > 4 else ''} gone; "
                    f"df = DS.load() restores the dataset)")
        return ""


G["_generated_dir"] = _generated_dir or None
if _df_path:
    G["df"] = _load_df(_df_path)
G["DS"] = _Source(_df_path or None, G.get("df"))      # set at every worker start, never checkpointed, like the aliases


def _decimals_for(values):
    """The decimals a RESULT line uses for its estimate and interval: set by the smallest of them, shared by all."""
    mags = [abs(float(v)) for v in values if isinstance(v, (int, float)) and not isinstance(v, bool) and float(v) != 0.0]
    m = min(mags) if mags else 1.0
    return 0 if m >= 100 else (1 if m >= 10 else (2 if m >= 0.1 else (3 if m >= 0.01 else 5)))


def _fmt_num(x, decimals=2):
    """A number as a RESULT line shows it: signed, with the decimals the line shares."""
    if x is None or isinstance(x, bool):
        return str(x)
    if isinstance(x, int):
        return f"{x:+,d}"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    return f"{v:+,.{decimals}f}"


def _literal_number(node):
    """A number written into the code: a numeric constant, or an expression of numeric constants only. A string
    constant is not a typed number here (a unit or a direction may sit in a numeric position when an earlier
    argument is starred; the runtime check catches a text estimate)."""
    import ast
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (int, float, complex)) and not isinstance(node.value, bool)
    if isinstance(node, ast.UnaryOp):
        return _literal_number(node.operand)
    if isinstance(node, ast.BinOp):
        return _literal_number(node.left) and _literal_number(node.right)
    return False


def RESULT(what, estimate, low=None, high=None, unit="", direction="", test=None, corrects=None, ci=95):
    """Record an estimate the cell computed (2026-10-06): the words are the analyst's, the numbers are values the
    cell computed, and the kernel prints the line and keeps a record for the session's ledger. A number written
    into the call instead of computed - a literal, or an expression of literals - is marked on the line and in
    the record: it is a claim, not a result (an analyst had typed +6.1 into a line whose own regression printed
    -0.19, and the report quoted it)."""
    import ast
    import sys
    typed = isinstance(estimate, str)
    try:
        fr = sys._getframe(1)
        code = G.get("_CURRENT_CODE") or ""
        if fr.f_code.co_filename == "<string>" and code:
            for node in ast.walk(ast.parse(code)):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "RESULT"
                        and node.lineno <= fr.f_lineno <= getattr(node, "end_lineno", node.lineno)):
                    # a starred argument (*fit(...)[:3]) leaves the positions unknown (2026-10-06: the unit and the
                    # direction had landed in the numeric slots and thirteen computed lines were marked typed)
                    positional = [] if any(isinstance(a, ast.Starred) for a in node.args[:4]) else list(node.args[1:4])
                    numeric = positional + [kw.value for kw in node.keywords if kw.arg in ("estimate", "low", "high")]
                    typed = typed or any(_literal_number(a) for a in numeric)
                    break
    except Exception:
        pass
    if isinstance(corrects, (list, tuple, set)):
        corr = f"(corrects cells {', '.join(str(c) for c in corrects)}) "
    else:
        corr = f"(corrects cell {corrects}) " if corrects is not None else ""
    tags = (f"(test {test}) " if test else "") + corr
    dec = _decimals_for((estimate, low, high))
    interval = f" ({ci}% CI {_fmt_num(low, dec)} to {_fmt_num(high, dec)})" if low is not None and high is not None else ""
    text = f"{tags}{what}: {_fmt_num(estimate, dec)}{interval}{(' ' + unit) if unit else ''}{(', ' + direction) if direction else ''}"
    if typed:
        text += " - typed: the numbers were written into the call, not computed"
    print("RESULT: " + text)
    G.setdefault("_RESULTS", []).append({"text": text, "typed": bool(typed), "test": test,
                                         "corrects": list(corrects) if isinstance(corrects, (list, tuple, set)) else corrects})
    return estimate


G["RESULT"] = RESULT                           # set at every worker start, never checkpointed

# ---- Worker arguments: argv[2] is the package directory (the worker runs from
# a temp file), argv[3] the checkpoint path. (The vetted-toolkit preload that
# lived here was retired 2026-09-05: the analyst chooses its own methods.)
_pkg_dir = sys.argv[2] if len(sys.argv) > 2 else ""
_ckpt_path = sys.argv[3] if len(sys.argv) > 3 else ""
if _pkg_dir and _pkg_dir not in sys.path:
    sys.path.insert(0, _pkg_dir)

# ---- Plot capture (patched once; reads _analysis_dir from G per step) ------
_real_savefig = _mpl_figure.Figure.savefig
G["_real_savefig"] = _real_savefig
G["_saved_plots"] = []
G["_plot_counter"] = [0]
G["_analysis_dir"] = "/tmp"

def _patched_show(*args, **kwargs):
    for fig_num in plt.get_fignums():
        fig = plt.figure(fig_num)
        G["_plot_counter"][0] += 1
        os.makedirs(G["_analysis_dir"], exist_ok=True)  # lazy: only when a plot exists
        path = os.path.join(G["_analysis_dir"], "plot_%03d.png" % G["_plot_counter"][0])
        _real_savefig(fig, path, dpi=150, bbox_inches="tight", facecolor="white", edgecolor="none")
        G["_saved_plots"].append(path)
    plt.close("all")

def _patched_savefig(self, fname, *args, **kwargs):
    G["_plot_counter"][0] += 1
    if isinstance(fname, str):
        basename = os.path.basename(fname)
    else:
        basename = "plot_%03d.png" % G["_plot_counter"][0]
    os.makedirs(G["_analysis_dir"], exist_ok=True)  # lazy: only when a plot exists
    path = os.path.join(G["_analysis_dir"], basename)
    kwargs.setdefault("dpi", 150)
    kwargs.setdefault("bbox_inches", "tight")
    kwargs.setdefault("facecolor", "white")
    _real_savefig(self, path, *args, **kwargs)
    G["_saved_plots"].append(path)

plt.show = _patched_show
_mpl_figure.Figure.savefig = _patched_savefig

# Plotly figures: fig.show() has no display here and must not try to open a
# browser. It is silent in the analysis kernel; the reproduction run through
# the executor captures fig.show() and that is how a figure reaches the reader.
try:
    import plotly.graph_objects as _go
    _go.Figure.show = lambda self, *a, **k: None
except Exception:
    pass


_INTERNAL = {
    "os", "io", "json", "sys", "traceback", "warnings",
    "matplotlib", "plt", "_mpl_figure", "pd", "np", "df", "DS", "RESULT", "_RESULTS", "_CURRENT_CODE", "_generated_dir", "_DATASETS",
    "_real_savefig", "_saved_plots", "_plot_counter", "_analysis_dir",
    "_patched_show", "_patched_savefig", "redirect_stdout",
}


_df_fp_cache = None      # fingerprint of df at the last checkpointed state
_df_blob_cache = None    # pickled df bytes matching _df_fp_cache


def _df_fingerprint():
    """A cheap content fingerprint of df, used to avoid re-pickling it on every
    checkpoint when nothing changed (the common case: steps mostly create
    derived objects). Any failure returns a unique object — 'always changed' —
    which is safe: the blob is simply rebuilt."""
    _df = G.get("df")
    if _df is None:
        return None
    try:
        _h = int(pd.util.hash_pandas_object(_df, index=True).sum())
        return (_h, _df.shape, tuple(map(str, _df.columns)),
                tuple(str(_t) for _t in _df.dtypes))
    except Exception:
        return object()


def _checkpoint_save(path):
    """Pickle the derived DATA objects in G to `path` atomically. Modules are
    recorded by import name (re-imported on load) and do not count against
    completeness. Returns (ok, skipped): ok is True only when every non-module
    derived object serialized. If anything is skipped (a function, lambda, or
    otherwise unpicklable object), the previous complete checkpoint is left
    untouched and the caller replays the tail from it instead.

    df IS included, despite being 'internal': step code mutates it in place
    (new columns, dropped rows), and those mutations belong to committed
    steps. A checkpoint restore skips replaying the steps it covers, so if df
    were left to the startup parquet reload — the ORIGINAL data — every
    committed in-place edit inside the covered range would silently vanish
    from any restore (crash recovery, timeout recovery, and the transactional
    rollback of failed attempts). Its blob is rebuilt only when the content
    fingerprint changes; on unpicklable df the checkpoint reports incomplete
    and the caller falls back to full replay, which reapplies the mutations."""
    blobs, modules, skipped = {}, {}, []
    for _name, _val in list(G.items()):
        if _name in _INTERNAL or _name.startswith("_"):
            continue
        if isinstance(_val, _types.ModuleType):
            modules[_name] = getattr(_val, "__name__", None)
            continue
        try:
            blobs[_name] = _pickle.dumps(_val, protocol=_pickle.HIGHEST_PROTOCOL)
        except Exception:
            skipped.append(_name)
    global _df_fp_cache, _df_blob_cache
    if G.get("df") is not None:
        _fp = _df_fingerprint()
        if _df_blob_cache is None or _fp != _df_fp_cache:
            try:
                _df_blob_cache = _pickle.dumps(G["df"],
                                               protocol=_pickle.HIGHEST_PROTOCOL)
                _df_fp_cache = _fp
            except Exception:
                _df_blob_cache = None
                _df_fp_cache = None
                skipped.append("df")
        if _df_blob_cache is not None:
            blobs["df"] = _df_blob_cache
    if skipped:
        return False, skipped
    _tmp = path + ".tmp"
    try:
        with open(_tmp, "wb") as _cf:
            _pickle.dump({"blobs": blobs, "modules": modules}, _cf,
                         protocol=_pickle.HIGHEST_PROTOCOL)
        os.replace(_tmp, path)
    except Exception:
        try:
            os.remove(_tmp)
        except Exception:
            pass
        return False, ["<write-failed>"]
    return True, []


def _checkpoint_load(path):
    """Restore a checkpoint into G: re-import recorded modules, unpickle data.
    Best-effort and silent; a missing or unreadable checkpoint leaves G empty."""
    if not (path and os.path.exists(path) and os.path.getsize(path) > 0):
        return
    try:
        with open(path, "rb") as _cf:
            _snap = _pickle.load(_cf)
    except Exception:
        return
    for _name, _modpath in (_snap.get("modules") or {}).items():
        if _modpath:
            try:
                G[_name] = _importlib.import_module(_modpath)
            except Exception:
                pass
    for _name, _blob in (_snap.get("blobs") or {}).items():
        try:
            G[_name] = _pickle.loads(_blob)
        except Exception:
            pass


_ALIAS_RE = re.compile(r"^([A-Za-z_]\w*)__s(\d+)$")


def _shape_of(val, depth=0):
    """What a value IS: element shape and length, not just its type name.

    The registry is the namespace summary the Investigator reads each turn, the ONLY
    thing that tells it what a persisted object contains. "list len=60" does not,
    and a wrong guess about a return contract is a silent, type-correct error."""
    t = type(val).__name__
    try:
        if t == "DataFrame":
            return "DataFrame %dx%d" % (val.shape[0], val.shape[1])
        if t == "Series":
            return "Series len=%d dtype=%s" % (len(val), val.dtype)
        if t == "ndarray":
            return "ndarray shape=%s dtype=%s" % (val.shape, val.dtype)
        if t in ("int", "float", "bool", "str", "NoneType", "int64", "float64"):
            return t
        if depth >= 3:
            return t
        if t == "tuple":
            if not val:
                return "tuple()"
            return "tuple(%s)" % ",".join(_shape_of(x, depth + 1) for x in val[:8])
        if t in ("list", "set"):
            if not val:
                return "%s len=0" % t
            first = next(iter(val))
            return "%s[%s] len=%d" % (t, _shape_of(first, depth + 1), len(val))
        if t == "dict":
            if not val:
                return "dict len=0"
            key = next(iter(val))
            return "dict[%s -> %s] len=%d" % (
                _shape_of(key, depth + 1), _shape_of(val[key], depth + 1), len(val))
    except Exception:
        pass
    return t


def _post_exec(_user_code, _before, _step_no):
    """After a clean exec: pin an immutable alias on everything this step bound,
    and record what each function it called actually returned.

    Both exist so a turn can reference prior objects by NAME instead of code while
    every step writes into one shared dict. Aliases make a rebound name
    recoverable by a name a later step can actually type; return contracts mean the next step never has to guess."""
    if _step_no:
        for _k in [_k for _k in list(G)
                   if not _k.startswith("_") and not _ALIAS_RE.match(_k)]:
            if _before.get(_k) != id(G[_k]):
                G["%s__s%s" % (_k, _step_no)] = G[_k]
    # Return contracts, observed from real calls in this step's code.
    try:
        _rets = G.setdefault("_returns", {})
        for _node in ast.walk(ast.parse(_user_code)):
            if not isinstance(_node, ast.Assign) or not isinstance(_node.value, ast.Call):
                continue
            _f = _node.value.func
            _fname = _f.id if isinstance(_f, ast.Name) else None
            if not _fname or not callable(G.get(_fname)):
                continue
            for _t in _node.targets:
                if isinstance(_t, ast.Name) and _t.id in G:
                    _rets[_fname] = _shape_of(G[_t.id])
    except Exception:
        pass


def _namespace_summary():
    """Compact description of user-defined names currently in G."""
    internal = _INTERNAL
    # Which steps bound each name? Derived from the aliases themselves, so no
    # extra state has to survive a checkpoint restore.
    bound_by = {}
    for name in G:
        m = _ALIAS_RE.match(name)
        if m:
            bound_by.setdefault(m.group(1), []).append(int(m.group(2)))

    out = []
    for name, val in list(G.items()):
        if name in internal or name.startswith("__") or _ALIAS_RE.match(name):
            continue
        t = type(val).__name__
        try:
            if t == "DataFrame":
                cols = list(map(str, val.columns))
                shown = ",".join(cols[:60])
                more = "" if len(cols) <= 60 else (" ...(+%d more cols)" % (len(cols) - 60))
                desc = "DataFrame %dx%d cols=%s%s" % (val.shape[0], val.shape[1], shown, more)
            elif t == "Series":
                desc = "Series len=%d name=%s dtype=%s" % (len(val), val.name, val.dtype)
            elif t in ("int", "float", "bool", "str"):
                r = repr(val)
                desc = r if len(r) <= 80 else r[:77] + "..."
            elif t in ("list", "tuple", "set", "dict"):
                desc = _shape_of(val)
            elif t in ("ndarray",):
                desc = "ndarray shape=%s dtype=%s" % (getattr(val, "shape", "?"), getattr(val, "dtype", "?"))
            elif t == "function":
                try:
                    sig = name + str(inspect.signature(val))
                except Exception:
                    sig = name + "(...)"
                doc = (inspect.getdoc(val) or "").strip().splitlines()
                ret = G.get("_returns", {}).get(name)
                desc = ("function " + sig + (" -> " + ret if ret else "")
                        + ((": " + doc[0][:80]) if doc else ""))
            elif t in ("type", "module"):
                continue  # imported modules and class definitions are not reusable derived state
            else:
                desc = t
        except Exception:
            desc = t
        steps = sorted(bound_by.get(name, []))
        if len(steps) > 1:
            # The collision is now impossible to miss, and pinnable.
            desc += ("  [AMBIGUOUS: rebound by steps %s. Use %s to pin one.]"
                     % (", ".join(str(s) for s in steps),
                        " or ".join("%s__s%d" % (name, s) for s in steps)))
        out.append({"name": name, "type": t, "desc": desc})
    return out


def _df_columns():
    df = G.get("df")
    if df is None:
        return []
    try:
        return list(map(str, df.columns))
    except Exception:
        return []


# ---- Restore checkpoint (only non-empty on a restart), then signal ready ----
_checkpoint_load(_ckpt_path)

# ---- Signal ready, then serve steps ---------------------------------------
sys.stdout.write(_READY + "\n")
sys.stdout.flush()

from contextlib import redirect_stdout

for _line in sys.stdin:
    _line = _line.strip()
    if not _line:
        continue
    try:
        _req = json.loads(_line)
    except Exception:
        continue
    if _req.get("cmd") == "shutdown":
        break

    _code_path = _req.get("code_path")
    _result_path = _req.get("result_path")
    G["_analysis_dir"] = _req.get("analysis_dir") or "/tmp"
    G["_saved_plots"] = []
    G["_RESULTS"] = []
    G["_DATASETS"] = []

    _stdout = None
    _error = None
    _step_no = _req.get("step")
    _before = {_k: id(_v) for _k, _v in G.items()
               if not _k.startswith("_") and not _ALIAS_RE.match(_k)}
    try:
        with open(_code_path, "r", encoding="utf-8") as _f:
            _user_code = _f.read()
        G["_CURRENT_CODE"] = _user_code
        _buf = io.StringIO()
        plt.close("all")
        with redirect_stdout(_buf):
            exec(_user_code, G)   # exec into G so derived state persists
        _stdout = _buf.getvalue()
        _post_exec(_user_code, _before, _step_no)
        if isinstance(G.get("DS"), _Source):
            _warn = G["DS"]._check(G)
            if _warn:
                _stdout = (_stdout.rstrip("\n") + "\n" if _stdout else "") + _warn + "\n"
    except Exception:
        _error = traceback.format_exc()
    finally:
        plt.close("all")

    _ckpt_ok, _ckpt_skipped = False, []
    if _error is None and _ckpt_path and not _req.get("no_ckpt"):
        try:
            _ckpt_ok, _ckpt_skipped = _checkpoint_save(_ckpt_path)
        except Exception:
            _ckpt_ok, _ckpt_skipped = False, ["<checkpoint-exception>"]

    _payload = {
        "stdout": _stdout,
        "error": _error,
        "plots": list(G.get("_saved_plots", [])),
        "results": list(G.get("_RESULTS", [])),
        "datasets": list(G.get("_DATASETS", [])),
        "namespace": _namespace_summary(),
        "columns": _df_columns(),
        "checkpoint_ok": _ckpt_ok,
        "checkpoint_skipped": _ckpt_skipped,
    }
    try:
        with open(_result_path, "w", encoding="utf-8") as _f:
            json.dump(_payload, _f)
    except Exception:
        pass

    sys.stdout.write(_DONE + "\n")
    sys.stdout.flush()
'''


def _truncate_traceback(tb, limit=6000):
    """Keep the traceback readable without losing the exception line. A long
    message (Plotly's valid-property lists run to thousands of characters)
    is cut AFTER the exception line and its first hint lines, never before
    it (2026-09-06: the old 1,500-char cap kept the head and the last line,
    and the analyst saw a fragment of a property list instead of the error)."""
    if not tb or len(tb) <= limit:
        return tb
    lines = tb.rstrip().splitlines()
    exc = None
    for i, ln in enumerate(lines):
        if re.match(r"^(?:[A-Za-z_][\w.]*)(?:Error|Exception|Warning|Exit|Interrupt|Fault)\b", ln):
            exc = i
    if exc is None:
        last = lines[-1] if lines else ""
        return tb[: limit - 100] + "\n[...truncated]\n" + last
    head = "\n".join(lines[:exc + 1])
    if len(head) > limit - 600:                      # a very deep stack: keep the user-code frames and the last few
        keep = [ln for ln in lines[:exc] if '"<string>"' in ln or ln.startswith("Traceback")]
        keep += lines[max(0, exc - 6):exc + 1]
        head = "\n".join(keep)
    rest = lines[exc + 1:]
    tail, size = [], 0
    for ln in rest:
        if size + len(ln) > 500 or len(tail) >= 12:
            tail.append(f"[... {len(rest) - len(tail)} more lines of the message truncated]")
            break
        tail.append(ln); size += len(ln) + 1
    return head + ("\n" + "\n".join(tail) if tail else "")


class KernelDead(Exception):
    """Raised internally when the worker process is gone and must be restarted."""


# In the Investigator's default registry view, only this many of the NEWEST
# derived objects carry their full description; every older object is listed
# by NAME only. Names are the reuse contract (reference-by-registry-name) and
# stay complete; descriptions are recognition aids whose value decays with
# age. Measured on a live 40-object run the descriptions were ~75% of the
# volatile tail — the dominant per-turn cost after the audit-4.2 cuts.
REGISTRY_DESC_RECENT = 25


def _code_for_security_check(code):
    """The code as the restricted-name check reads it: comments and plain string literals blanked out, everything
    else verbatim, so a label or a note that mentions a restricted word is not taken for its use (2026-10-05: a
    label '+HR eval@150' was refused as the eval module). f-strings stay: their expressions are code. Code that
    does not tokenize is checked whole."""
    import io
    import re
    import tokenize
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(code).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return code
    starts, pos = [0], 0
    for line in code.splitlines(keepends=True):
        pos += len(line)
        starts.append(pos)
    chars = list(code)
    for tok in toks:
        prefix = re.match(r"[A-Za-z]*", tok.string).group(0).lower() if tok.type == tokenize.STRING else ""
        if tok.type == tokenize.COMMENT or (tok.type == tokenize.STRING and "f" not in prefix):
            a = starts[tok.start[0] - 1] + tok.start[1]
            b = starts[tok.end[0] - 1] + tok.end[1]
            for i in range(a, min(b, len(chars))):
                if chars[i] != "\n":
                    chars[i] = " "
    return "".join(chars)


class PersistentKernel:
    """A long-lived worker process holding one persistent analysis namespace."""

    def __init__(self, df=None, analysis_root=None, step_timeout=STEP_TIMEOUT, generated_dir=None):
        self.step_timeout = step_timeout
        self.generated_dir = generated_dir            # where DS.save puts a dataset for the person (2026-10-06)
        self._df_path = _serialize_dataframe(df) if df is not None else None
        self._worker_script_path = _write_temp_text(
            _WORKER_SCRIPT, suffix=".py", prefix="delve_kernel_"
        )
        # Ordered list of code blocks that previously executed without error.
        # On a restart the namespace is restored from a checkpoint and only the
        # tail not covered by it is replayed (see _restart_and_replay).
        # _snapshot_through is the number of history steps the last COMPLETE
        # checkpoint covers; 0 means no usable checkpoint yet (full replay).
        self._history = []
        _cfd, self._ckpt_path = tempfile.mkstemp(suffix=".pkl", prefix="delve_ckpt_")
        os.close(_cfd)  # leaves a 0-byte file; the worker skips an empty checkpoint
        self._snapshot_through = 0
        # Latest namespace registry from the worker.
        self.registry = {"namespace": [], "columns": []}
        # Registry as of the last COMMITTED step. Every failed attempt is rolled
        # back to this state (see execute), so the registry shown onward never
        # advertises objects a failed attempt created and then lost.
        self._good_registry = {"namespace": [], "columns": []}
        # True while the live worker holds state from a commit=False execution
        # (chart rendering). Cleared by any rollback/replay.
        self._uncommitted = False
        self._proc = None
        self._reader = None
        self._q = None
        self._start_worker()

    # ----- worker lifecycle ------------------------------------------------

    def _start_worker(self, load_ckpt=True):
        self._proc = subprocess.Popen(
            [sys.executable, "-u", self._worker_script_path, self._df_path or "",
             os.path.dirname(os.path.abspath(__file__)),
             self._ckpt_path if load_ckpt else "",
             self.generated_dir or ""],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self._q = queue.Queue()
        # Bind this worker's proc and queue into the thread so a dying OLD worker
        # can never drop a stale sentinel into a NEW worker's queue after restart.
        self._reader = threading.Thread(
            target=self._read_stdout, args=(self._proc, self._q), daemon=True
        )
        self._reader.start()
        # Wait for the ready token.
        if not self._await_token(_READY, timeout=60):
            raise RuntimeError("Persistent kernel worker failed to start.")

    @staticmethod
    def _read_stdout(proc, q):
        try:
            for line in proc.stdout:
                q.put(line.strip())
        except Exception:
            pass
        finally:
            q.put(None)  # sentinel: this worker's stdout closed (worker died)

    def _await_token(self, token, timeout):
        """Block until `token` appears on the worker's stdout, or timeout/death."""
        import time
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            try:
                item = self._q.get(timeout=remaining)
            except queue.Empty:
                return False
            if item is None:
                raise KernelDead()
            if item == token:
                return True
            # Any other stray line is ignored (shouldn't happen; user output is
            # captured in-worker).

    def _kill_worker(self):
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.kill()
            except Exception:
                pass
        try:
            if self._proc:
                self._proc.wait(timeout=5)
        except Exception:
            pass
        self._proc = None

    def _restart_and_replay(self, reason=None):
        """Rebuild the namespace to the last COMMITTED state. Restore the last
        complete checkpoint (loaded by the fresh worker on startup), then replay
        only the committed steps after it. If that tail fails (a step errors or
        the worker dies), fall back to a full replay from a clean worker, which
        is the original O(n) behavior.

        Used both for crash/timeout recovery (no `reason`, logged as a WARNING)
        and as the TRANSACTIONAL ROLLBACK after a failed or uncommitted
        execution (`reason` given, logged as INFO — routine, not alarming).
        Either way the worker ends at the last committed step: the checkpoint
        file is only ever written after a successful committed step, so it can
        never contain a failed attempt's partial mutations or uncommitted chart
        state. On exit the visible registry is restored to the committed one
        and any uncommitted-state flag is cleared."""
        n = self._snapshot_through
        tail = self._history[n:]
        if reason:
            logger.info("Persistent kernel: %s — restoring checkpoint through "
                        "step %d, replaying %d tail step(s).", reason, n, len(tail))
        else:
            logger.warning(
                "Persistent kernel restarting; restoring checkpoint through step %d, "
                "replaying %d tail step(s).", n, len(tail))
        self._kill_worker()
        self._start_worker(load_ckpt=(n > 0))
        replayed = False
        for i, code in enumerate(tail):
            res = self._run_once(code, analysis_dir=None)
            if res is None or res.get("_timeout") or res.get("error"):
                logger.warning("Checkpoint tail replay failed at tail step %d; "
                               "falling back to full replay.", i)
                break
        else:
            replayed = True  # tail replayed cleanly: namespace is whole

        if not replayed:
            # Fallback: clean worker, ignore the checkpoint, replay the whole history.
            self._kill_worker()
            self._start_worker(load_ckpt=False)
            for j, code in enumerate(self._history):
                res = self._run_once(code, analysis_dir=None)
                if res is None or (res and res.get("_timeout")):
                    logger.error("Kernel could not complete full replay at step %d; "
                                 "namespace partial.", j)
                    break

        self.registry = {"namespace": list(self._good_registry.get("namespace", [])),
                         "columns": list(self._good_registry.get("columns", []))}
        self._uncommitted = False

    # ----- execution -------------------------------------------------------

    def _security_refuse(self, code):
        import re
        code = _code_for_security_check(code)
        for banned in BLACKLIST:
            pattern = r"\b" + re.escape(banned) + r"\b"
            if re.search(pattern, code):
                if banned == "sys" and "sys." not in code:
                    continue
                return (
                    "Security notice: code contains restricted module "
                    f"({banned}) and was not executed."
                )
        return None

    def _run_once(self, code, analysis_dir, step=None, no_ckpt=False):
        """One round-trip to the worker. Returns the result dict, or None if the
        worker died (caller decides whether to restart). Does NOT itself restart.
        With no_ckpt=True the worker skips its post-step checkpoint save, so an
        uncommitted (chart) execution can never enter the checkpoint file."""
        # NOTE: analysis_dir is NOT created here. The folder is made lazily, only
        # when a plot is actually written (see the worker plot patch), so steps
        # that produce no plots — which is all of them, since step cutor is told
        # not to plot — never leave behind an empty NN/ folder.
        code_path = _write_temp_text(code, suffix=".py", prefix="delve_step_")
        fd, result_path = tempfile.mkstemp(suffix=".json", prefix="delve_res_")
        os.close(fd)
        try:
            req = json.dumps({
                "code_path": code_path,
                "result_path": result_path,
                "analysis_dir": analysis_dir or "",
                "step": step,
                "no_ckpt": bool(no_ckpt),
            })
            try:
                self._proc.stdin.write(req + "\n")
                self._proc.stdin.flush()
            except (BrokenPipeError, OSError):
                return None  # worker already gone

            try:
                alive = self._await_token(_DONE, timeout=self.step_timeout)
            except KernelDead:
                return None
            if not alive:
                # Hung: kill so the caller can restart+replay.
                self._kill_worker()
                return {"_timeout": True}

            try:
                with open(result_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                return {"stdout": None, "error": f"Failed to read result: {exc}",
                        "plots": [], "namespace": [], "columns": []}
        finally:
            _cleanup_files(code_path, result_path)

    def execute(self, code, analysis_dir=None, step=None, commit=True):
        """Execute one step in the persistent namespace, TRANSACTIONALLY.

        Returns (stdout, error, plots), the historical CodeExecutor.execute
        (minus the df argument — df lives in the kernel).

        Commit semantics: a step is COMMITTED only when it runs without error
        and commit=True; only committed code enters the replayable history.
        Ordinary Python exceptions can mutate objects before raising (an
        in-place df edit on line 1, a raise on line 3), so a failed attempt
        leaves the worker dirty even though nothing was committed — and a
        retry, or a later --resume/--extend replay of the committed history,
        would otherwise see a state the committed record never produced. Every
        failed attempt is therefore ROLLED BACK: the worker is rebuilt from the
        last committed checkpoint + tail (see _restart_and_replay) before
        control returns, and the error string says so, matching what the
        next turn's traceback context relies on.

        commit=False runs the code against the live namespace WITHOUT
        committing it: no history append, no checkpoint (the worker is told to
        skip its save), no registry update. Used for chart rendering, whose
        code must see the analytical objects but must never become analytical
        state; call discard_uncommitted() afterwards to restore the worker."""
        refusal = self._security_refuse(code)
        if refusal:
            return None, refusal, []

        result = self._run_once(code, analysis_dir, step=step, no_ckpt=not commit)

        # Timeout → roll back to the last committed state, then report.
        if result is not None and result.get("_timeout"):
            self._restart_and_replay()
            return None, (
                f"Execution killed: exceeded {self.step_timeout}s time limit. "
                "Simplify the step (fewer iterations, aggregate before fitting, "
                "cap pairwise operations). The attempt was rolled back; the "
                "namespace is exactly as it was before this step."
            ), []

        # Worker died (OOM/segfault) → roll back to the last committed state.
        if result is None:
            self._restart_and_replay()
            return None, (
                "Execution killed by the OS (likely out of memory) or the worker "
                "crashed. Reduce memory use (sample/aggregate first, avoid large "
                "intermediate frames). The attempt was rolled back; the namespace "
                "is exactly as it was before this step."
            ), []

        stdout = result.get("stdout")
        error = _truncate_traceback(result.get("error"))
        plots = result.get("plots", []) or []
        self.last_results = list(result.get("results") or []) if error is None else []   # RESULT(...) records of this step

        if error is not None:
            # TRANSACTIONAL ROLLBACK. The exception may have fired after part of
            # the code already mutated the namespace; rebuild the worker from
            # the committed record so the retry (and any later replay) sees
            # exactly the pre-step state. The checkpoint file is safe to load:
            # the worker only saves it after error-free steps.
            self._restart_and_replay(
                reason=f"rolling back failed attempt{f' (step {step})' if step else ''}")
            return stdout, (error + "\n[delv-e: the failed attempt was rolled "
                            "back — the namespace is exactly as it was before "
                            "this attempt]"), plots

        if not commit:
            # Success, but deliberately uncommitted (chart rendering): the live
            # worker now holds state the committed record does not. Leave the
            # registry/history untouched and flag the worker dirty so
            # discard_uncommitted() knows a restore is needed.
            self._uncommitted = True
            return stdout, None, plots

        self.registry = {
            "namespace": result.get("namespace", []),
            "columns": result.get("columns", []),
        }
        self._good_registry = {"namespace": list(self.registry["namespace"]),
                               "columns": list(self.registry["columns"])}
        self._history.append(code)  # only successful committed steps are replayable
        if result.get("checkpoint_ok"):
            # The checkpoint now captures state through this step, so a future
            # restart restores from here and skips replaying everything before.
            self._snapshot_through = len(self._history)
        return stdout, None, plots

    def discard_uncommitted(self, reason="discarding uncommitted state"):
        """Restore the worker to the last committed step if any commit=False
        execution has run since; no-op (returns False) otherwise. Chart
        rendering calls this after its loop so chart-only variables never leak
        into the analytical namespace, the persisted history, or a later
        --resume/--extend replay."""
        if not self._uncommitted:
            return False
        self._restart_and_replay(reason=reason)
        return True

    # ----- introspection / lifecycle --------------------------------------

    def describe_namespace(self, max_items=120, names=None):
        """Human/LLM-readable registry of current derived state and df columns.
        ALL df column names are shown — step code is written against these, so
        a truncated list could make it reference a column it cannot see.

        When `names` is given, only those derived objects are listed (plus a count
        of the rest); callers use this to show the Investigator just the objects its
        spec references — those always carry their FULL descriptions.

        When `names` is None (the Investigator's per-turn view), the NEWEST
        REGISTRY_DESC_RECENT objects carry descriptions and every older object
        is listed by NAME only, one compact line. Every name is always present
        — reuse-by-name never depends on recency — but stale descriptions no
        longer ride the uncached tail every turn (they were ~75% of it on a
        measured 40-object run). `max_items` caps the described portion."""
        cols = self.registry.get("columns", [])
        ns = self.registry.get("namespace", [])
        lines = []
        if cols:
            lines.append(f"df columns ({len(cols)}): {', '.join(cols)}")
        if not ns:
            lines.append("Derived objects in namespace: (none yet)")
            return "\n".join(lines)
        if names is not None:
            shown = [it for it in ns if it["name"] in names]
            lines.append("Derived objects in scope:" if shown
                         else "Derived objects in scope: (none referenced)")
            for item in shown:
                lines.append(f"  - {item['name']}: {item['desc']}")
            hidden = len(ns) - len(shown)
            if hidden > 0:
                lines.append(f"  ... (+{hidden} other derived objects exist; "
                             f"reference one by its exact name to use it)")
        else:
            desc_n = min(REGISTRY_DESC_RECENT, max_items)
            shown = ns[-desc_n:]            # keep the NEWEST, never the reverse
            older = ns[:-desc_n] if desc_n < len(ns) else []
            lines.append("Derived objects in namespace (most recent, with descriptions):")
            for item in shown:
                lines.append(f"  - {item['name']}: {item['desc']}")
            if older:
                cap = 300
                names_line = ", ".join(it["name"] for it in older[-cap:])
                extra = len(older) - cap
                lines.append("Earlier derived objects, by NAME only (all remain "
                             "live; reference one by its exact name to use it): "
                             + names_line
                             + (f" (+{extra} more)" if extra > 0 else ""))
        return "\n".join(lines)

    def reset(self):
        """Clear the namespace and history; start a fresh worker (df reloaded)."""
        self._kill_worker()
        self._history = []
        self.registry = {"namespace": [], "columns": []}
        self._good_registry = {"namespace": [], "columns": []}
        self._uncommitted = False
        self._snapshot_through = 0
        try:
            open(self._ckpt_path, "wb").close()  # truncate so no stale state loads
        except Exception:
            pass
        self._start_worker(load_ckpt=False)

    @property
    def history(self):
        """The ordered code blocks that executed successfully — persist this to
        resume a run later (see restore_history)."""
        return list(self._history)

    def restore_history(self, history):
        """Replay an external history (from a prior run) to rebuild the namespace
        on a fresh worker. Used by --resume and --extend. Best-effort: a step that
        fails to replay is logged and skipped."""
        for code in history or []:
            res = self._run_once(code, analysis_dir=None)
            if res is None:                      # worker died mid-replay
                self._restart_and_replay()
                res = self._run_once(code, analysis_dir=None)
            if res and not res.get("error") and not res.get("_timeout"):
                self._history.append(code)
                if res.get("checkpoint_ok"):
                    self._snapshot_through = len(self._history)
                self.registry = {"namespace": res.get("namespace", []),
                                 "columns": res.get("columns", [])}
                self._good_registry = {"namespace": list(self.registry["namespace"]),
                                       "columns": list(self.registry["columns"])}
            else:
                logger.warning("restore_history: a step failed to replay; namespace may be partial.")

    def cleanup(self):
        try:
            if self._proc and self._proc.poll() is None:
                try:
                    self._proc.stdin.write(json.dumps({"cmd": "shutdown"}) + "\n")
                    self._proc.stdin.flush()
                    self._proc.wait(timeout=5)
                except Exception:
                    self._kill_worker()
        finally:
            self._kill_worker()
            _cleanup_files(self._worker_script_path, self._df_path, self._ckpt_path)
            self._worker_script_path = None
            self._df_path = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.cleanup()
        return False

    def __del__(self):
        try:
            self.cleanup()
        except Exception:
            pass