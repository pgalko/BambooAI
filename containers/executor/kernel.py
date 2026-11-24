"""
Persistent execution kernel for delv-e's inverted-core loop.

A single long-lived worker process holds ONE namespace. `df` is loaded once;
derived columns and intermediate objects created in step k survive into step
k+1. This is what makes analytical (not line-count) decomposition possible:
each step can stay small because its prerequisites already
live in the namespace.

Crash isolation: the worker is itself a killable subprocess. If a step hangs
(timeout), fails, or the worker dies (OOM/segfault), the parent starts a new
one from the snapshot of the last committed step.

Snapshots: after every committed step the worker saves its whole state - the
names the cells made (data, functions, classes), the random generators, the
settings a cell changed. Each committed step is a state the kernel can go back
to (`last_step`, `goto`): nothing is run again, so what a step computed is
what it holds. A state that could not be saved (an open file in the
namespace), or whose snapshot went at the cap, is reached from the nearest
saved one before it by running the steps between again; determinism of those
steps is then the caller's responsibility (seed your RNG).

Contract:
    kernel = PersistentKernel(df=df, analysis_root="output/exploration")
    stdout, error, plots = kernel.execute(code, analysis_dir=".../01")
    here = kernel.last_step              # the state this step made ...
    kernel.goto(here)                    # ... and the way back to it, after later steps
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
import shutil
import subprocess
import sys
import tempfile
import threading
import uuid

from logger_config import get_logger

# Reuse the security blacklist and temp-file helpers: codeutils in the package, executor.py in the executor image.
from executor import BLACKLIST, _write_temp_text, _cleanup_files, _serialize_dataframe

logger = get_logger(__name__)

# Wall-clock seconds for a single step. The persistent worker means a hang on
# one step must not wedge the whole run, so on timeout we kill and restart.
# Set to give a correctly vectorized simulation comfortable headroom; a scalar
# per-sample loop will still blow past it, which is the intended signal.
STEP_TIMEOUT = 600

# What one kernel's snapshots may take on disk, in megabytes. Over it the oldest
# go; a state whose snapshot went is still reached, from the nearest saved one
# before it.
SNAPSHOT_MB = int(os.getenv("KERNEL_SNAPSHOT_MB", "2048"))

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
import pickle as _pickle, types as _types, hashlib as _hashlib, random as _random, importlib as _importlib
try:
    import cloudpickle as _cloudpickle      # saves the functions and classes a cell defines; without it no state is saved
except Exception:
    _cloudpickle = None
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
# import (2026-09-05): a restore rebuilt G without the names listed in
# _INTERNAL - so a `pd` a cell had imported vanished after the first
# rolled-back attempt and every later cell failed with NameError. They are set
# here, at every worker start, unconditionally.
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
_SOURCE = G.get("df")                                 # the dataset as loaded: a snapshot names it while `df` holds it unchanged
G["DS"] = _Source(_df_path or None, _SOURCE)          # set at every worker start, never saved, like the aliases


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


def RESULT(what, estimate, low=None, high=None, unit="", direction="", test=None, corrects=None, ci=95, interval=None):
    """Record an estimate the cell computed (2026-10-06): the words are the analyst's, the numbers are values the
    cell computed, and the kernel prints the line and keeps a record for the session's ledger. The bounds are a
    confidence interval at `ci` per cent unless `interval` names what they are - "range", "IQR" (2026-11-24: a
    count and a spread over seven people were printed as 95% CIs, and a run recorded them twice more to put the
    label right); without bounds the line has none. A number written
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
    named = str(interval or "").replace("(", "").replace(")", "").strip() or f"{ci}% CI"      # no bracket of its own: the line's readers go by them
    bounds = f" ({named} {_fmt_num(low, dec)} to {_fmt_num(high, dec)})" if low is not None and high is not None else ""
    text = f"{tags}{what}: {_fmt_num(estimate, dec)}{bounds}{(' ' + unit) if unit else ''}{(', ' + direction) if direction else ''}"
    if typed:
        text += " - typed: the numbers were written into the call, not computed"
    print("RESULT: " + text)
    line = None
    try:                                   # the cell's own line the call ran from, through any helper (2026-10-20, the code map)
        fr = sys._getframe(1)
        while fr is not None and not (fr.f_code.co_filename == "<string>" and fr.f_code.co_name == "<module>"):
            fr = fr.f_back
        line = fr.f_lineno if fr is not None else None
    except Exception:
        pass
    G.setdefault("_RESULTS", []).append({"text": text, "typed": bool(typed), "test": test,
                                         "corrects": list(corrects) if isinstance(corrects, (list, tuple, set)) else corrects, "line": line})
    return estimate


G["RESULT"] = RESULT                           # set at every worker start, never saved

# ---- Worker arguments: argv[2] is the package directory (the worker runs from
# a temp file), argv[3] the snapshot this worker starts from ("" for a fresh
# state), argv[5] the kernel's snapshot folder. (The vetted-toolkit preload that
# lived here was retired 2026-09-05: the analyst chooses its own methods.)
_pkg_dir = sys.argv[2] if len(sys.argv) > 2 else ""
_snap_from = sys.argv[3] if len(sys.argv) > 3 else ""
_snap_dir = sys.argv[5] if len(sys.argv) > 5 else ""
_snap_bufs = os.path.join(_snap_dir, "b") if _snap_dir else ""     # the large buffers, each once, under the hash of its content
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

# ---- Reaches: what a cell touched outside the data (2026-10-28) ----------
# Observation, not prevention. The doors a cell can leave through are wrapped
# so the kernel can say, per cell, which hosts it connected to and how many
# bytes went each way, which files it opened or listed outside the data,
# which environment names it read, and which programs it started. The records
# ride back in the step's payload and nothing of them enters a prompt. The
# blacklist still refuses the modules it names before a cell runs; the one
# address refused here is the cloud instance metadata service, which answers
# with the box's own credentials. A record says what the kernel saw: a
# connection made by a C library (libpq, pycurl) does not pass these doors and
# is not seen.
import builtins as _builtins, socket as _socket, tempfile as _tempfile, weakref as _weakref
try:
    import ssl as _ssl
except Exception:
    _ssl = None
try:
    import subprocess as _subprocess
except Exception:
    _subprocess = None

G["_REACHES"] = []
G["_IN_CELL"] = False
_REACH_CAP = 40                                    # records kept per cell; the rest is one count
_REACH_META = ("169.254.169.254", "fd00:ec2::254", "metadata.google.internal", "metadata")
_DNS = {}                                          # ip -> name, from the cell's own lookups
_SOCKS = {}                                        # fd -> the record of the connection on it
_STDLIB = os.path.dirname(os.__file__)
_SELF = __file__                                   # the worker's own frames are not the cell's
_NOISE = ("/etc/localtime", "/etc/timezone", "/etc/ld.so", "/etc/nsswitch.conf", "/etc/ssl", "/etc/pki", "/etc/fonts",
          "/etc/matplotlibrc", "/etc/resolv.conf", "/etc/hosts", "/etc/host.conf", "/etc/gai.conf", "/etc/mime.types",
          "/etc/mailcap", "/etc/os-release", "/etc/lsb-release", "/etc/debian_version", "/etc/alternatives", "/etc/locale",
          "/etc/papersize", "/etc/magic", "/etc/xdg", "/etc/python")        # what libraries read on a box as a matter of course
_SENSITIVE = ("/etc", "/root", "/home", "/run", "/var/run", "/var/lib", "/app", "/srv", "/opt")


def _reach_roots():
    """Where a cell reads and writes as its job: the data, the plots, the generated folder, temp, python's own trees."""
    roots = [_tempfile.gettempdir(), "/tmp", "/dev", "/usr", "/lib", "/lib64", "/bin", "/sbin",
             sys.prefix, sys.base_prefix, getattr(sys, "exec_prefix", "") or sys.prefix,
             "/app/datasets", os.path.join(os.path.expanduser("~"), ".cache"), os.path.join(os.path.expanduser("~"), ".config", "matplotlib"),
             os.path.join(os.path.expanduser("~"), ".local"), os.path.join(os.path.expanduser("~"), ".fonts")]
    for p in (_df_path, G.get("_generated_dir"), G.get("_analysis_dir")):
        if p:
            roots.append(os.path.dirname(p) if p == _df_path else p)
    if G.get("_generated_dir"):
        roots.append(os.path.dirname(os.path.realpath(G["_generated_dir"])))      # the person's own datasets folder: the auxiliary files live there
    try:
        import matplotlib as _m
        roots += [_m.get_configdir(), _m.get_cachedir()]
    except Exception:
        pass
    return tuple(sorted({os.path.realpath(r) for r in roots if r}))


def _under(path, roots):
    return any(path == r or path.startswith(r.rstrip("/") + "/") for r in roots)


def _cell_frames():
    """(nearest, line): whether the nearest frame outside the standard library is the cell's own code, and the cell
    line the call ran from (the top-level statement, through any helper)."""
    nearest, line = None, None
    try:
        fr = sys._getframe(1)
        while fr is not None:
            fn = fr.f_code.co_filename
            if nearest is None and fn != _SELF and not fn.startswith("<frozen ") and not (fn.startswith(_STDLIB) and "-packages" not in fn):
                nearest = fn                           # frozen modules (os, _collections_abc) are the standard library too
            if fn == "<string>" and fr.f_code.co_name == "<module>":
                line = fr.f_lineno
            fr = fr.f_back
    except Exception:
        pass
    return nearest == "<string>", line


def _in_code(*texts):
    code = G.get("_CURRENT_CODE") or ""
    return any(t and len(t) >= 3 and t in code for t in texts)


def _path_in_code(*paths):
    """A folder written in the cell's code as a path of its own: not followed by more path or a word character."""
    code = G.get("_CURRENT_CODE") or ""
    return any(t and len(t) >= 3 and re.search(re.escape(t) + r"(?![\w/])", code) for t in paths)


def _reach_add(rec, key):
    """Keep one record per key in the cell, merged; past the cap, one count."""
    if not G.get("_IN_CELL"):
        return None
    recs = G["_REACHES"]
    for r in recs:
        if r.get("_key") == key:
            return r
    if sum(1 for r in recs if r.get("kind") != "more") >= _REACH_CAP:
        more = next((r for r in recs if r.get("kind") == "more"), None)
        if more is None:
            recs.append({"kind": "more", "n": 0})
            more = recs[-1]
        more["n"] += 1
        return None
    rec["_key"] = key
    recs.append(rec)
    return rec


def _reach_file(path, op, raw=None):
    """A file opened or listed outside the data: recorded when the cell chose the path (its own frame, or the path
    written in its code), always when under a place that holds the box's own things, always when written."""
    try:
        p = os.path.realpath(os.path.expanduser(os.fsdecode(path)))
    except Exception:
        return
    if _under(p, _REACH_ROOTS):
        return
    own, line = _cell_frames()
    parents = [p[:i] for i in range(len(p) - 1, 1, -1) if p[i] == "/" and p[:i].count("/") >= 2]
    # the cell chose the path when its own frame made the call, or the path - or a folder above it - is written in its
    # code as a path of its own (a folder named only as the head of a longer path is not a choice of the folder, 2026-10-28)
    chosen = own or _path_in_code(str(raw) if raw is not None else "", p, *parents)
    if p.startswith(("/proc", "/sys")) and not chosen:
        return
    if op == "list" and not chosen and any(p == os.path.realpath(x or ".") for x in sys.path):
        return                                     # a library scanning the import path for package metadata (2026-10-28: "listed /app" on every cell)
    if not (chosen or op == "write" or (_under(p, _SENSITIVE) and not p.startswith(_NOISE)) or any(seg.startswith(".") for seg in p.split("/"))):
        return
    _reach_add({"kind": "file", "path": p, "op": op, "line": line, "via": "code" if chosen else "library"}, ("file", p, op))


_real_open = _builtins.open
def _open_hook(file, mode="r", *a, **k):
    if G.get("_IN_CELL") and isinstance(file, (str, bytes, os.PathLike)):
        try:
            _reach_file(file, "write" if any(c in str(mode) for c in "wax+") else "read", file)
        except Exception:
            pass
    return _real_open(file, mode, *a, **k)
_builtins.open = _open_hook
io.open = _open_hook

_real_os_open = os.open
def _os_open_hook(path, flags, *a, **k):
    if G.get("_IN_CELL") and isinstance(path, (str, bytes, os.PathLike)):
        try:
            _reach_file(path, "write" if flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC) else "read", path)
        except Exception:
            pass
    return _real_os_open(path, flags, *a, **k)
os.open = _os_open_hook

_real_listdir, _real_scandir = os.listdir, os.scandir
def _listdir_hook(path="."):
    if G.get("_IN_CELL"):
        try:
            _reach_file(path if not isinstance(path, int) else ".", "list", path)
        except Exception:
            pass
    return _real_listdir(path)
def _scandir_hook(path="."):
    if G.get("_IN_CELL"):
        try:
            _reach_file(path if not isinstance(path, int) else ".", "list", path)
        except Exception:
            pass
    return _real_scandir(path)
os.listdir, os.scandir = _listdir_hook, _scandir_hook


class _WatchedEnviron(os._Environ):
    """os.environ with its reads on the record: a name the cell asked for, or '*' when it walked the whole environment."""

    def _note(self, name):
        try:
            own, line = _cell_frames()
            if own or (name != "*" and _in_code(name)):
                if name != "*" and any(r.get("kind") == "env" and r.get("name") == "*" for r in G["_REACHES"]):
                    return
                _reach_add({"kind": "env", "name": name, "line": line}, ("env", name))
        except Exception:
            pass

    def __getitem__(self, key):
        self._note(str(key))
        return os._Environ.__getitem__(self, key)

    def __contains__(self, key):
        self._note(str(key))
        return os._Environ.__contains__(self, key)

    def __iter__(self):
        self._note("*")
        return os._Environ.__iter__(self)

    def copy(self):
        self._note("*")
        return dict(self)


_watched = _WatchedEnviron.__new__(_WatchedEnviron)
_watched.__dict__.update(os.environ.__dict__)
os.environ = _watched


def _reach_process(what, args):
    """A program started by the cell: its own call, or a command its code names. A library starting one on its own
    (matplotlib asks fc-list for the fonts) is not the cell's doing and is not recorded."""
    try:
        own, line = _cell_frames()
        cmd = args if isinstance(args, str) else " ".join(str(a) for a in (args if isinstance(args, (list, tuple)) else [args]))
        if own or _in_code(str(cmd).split()[0] if str(cmd).split() else ""):
            _reach_add({"kind": "process", "command": str(cmd)[:200], "via": what, "line": line}, ("process", str(cmd)[:200]))
    except Exception:
        pass

_real_system, _real_popen = os.system, os.popen
def _system_hook(command):
    _reach_process("os.system", command)
    return _real_system(command)
def _popen_hook(cmd, *a, **k):
    _reach_process("os.popen", cmd)
    return _real_popen(cmd, *a, **k)
os.system, os.popen = _system_hook, _popen_hook
if _subprocess is not None:
    _real_popen_init = _subprocess.Popen.__init__
    def _popen_init_hook(self, args, *a, **k):
        _reach_process("subprocess", args)
        return _real_popen_init(self, args, *a, **k)
    _subprocess.Popen.__init__ = _popen_init_hook


def _addr_parts(address):
    """(host, port) of a socket address: a name or ip and a port, or a unix path."""
    if isinstance(address, (str, bytes)):
        return "unix:" + os.fsdecode(address), None
    if isinstance(address, (tuple, list)) and address:
        return str(address[0]), (address[1] if len(address) > 1 else None)
    return str(address), None


def _reach_connect(sock, address, kind="net"):
    host, port = _addr_parts(address)
    name = _DNS.get(host) or host
    own, line = _cell_frames()
    rec = _reach_add({"kind": kind, "host": name, "ip": host if name != host else "", "port": port, "out": 0, "in": 0, "n": 0,
                      "line": line, "tls": bool(_ssl and isinstance(sock, _ssl.SSLSocket)), "blocked": False, "failed": ""},
                     (kind, name, port))
    if rec is not None:
        rec["n"] += 1
        try:
            _SOCKS[sock.fileno()] = rec
        except Exception:
            pass
    return rec


def _sock_rec(sock):
    """The record of the connection a socket carries; a reused connection gets a record in the cell it is used in."""
    try:
        fd = sock.fileno()
    except Exception:
        return None
    rec = _SOCKS.get(fd)
    if rec is None:
        try:
            peer = sock.getpeername()
        except Exception:
            return None
        rec = _reach_connect(sock, peer)
        return rec
    if not any(r is rec for r in G["_REACHES"]):             # the record belongs to an earlier cell: a reused connection
        fresh = _reach_add({k: v for k, v in rec.items() if k not in ("_key", "out", "in", "n", "line")} | {"out": 0, "in": 0, "n": 0, "line": _cell_frames()[1]},
                           rec["_key"])
        if fresh is not None:
            _SOCKS[fd] = fresh
            rec = fresh
    return rec


def _numeric(host):
    try:
        import ipaddress
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


_real_getaddrinfo = _socket.getaddrinfo
def _getaddrinfo_hook(host, port, *a, **k):
    res = _real_getaddrinfo(host, port, *a, **k)
    try:
        if isinstance(host, (str, bytes)) and host and G.get("_IN_CELL"):
            h = os.fsdecode(host)
            if not _numeric(h):
                for fam, typ, proto, canon, sa in res:
                    if sa and str(sa[0]) != h:
                        _DNS[str(sa[0])] = h
                own, line = _cell_frames()
                _reach_add({"kind": "dns", "host": h, "line": line}, ("dns", h))
    except Exception:
        pass
    return res
_socket.getaddrinfo = _getaddrinfo_hook

_real_connect, _real_connect_ex = _socket.socket.connect, _socket.socket.connect_ex
def _connect_hook(self, address, _ex=False):
    rec = None
    if G.get("_IN_CELL"):
        try:
            rec = _reach_connect(self, address)
            host, _ = _addr_parts(address)
            if host in _REACH_META or _DNS.get(host, "") in _REACH_META:
                if rec is not None:
                    rec["blocked"] = True
                raise OSError("the instance metadata address is not reachable from here")
        except OSError:
            raise
        except Exception:
            pass
    try:
        out = _real_connect_ex(self, address) if _ex else _real_connect(self, address)
    except BlockingIOError:
        raise
    except OSError as exc:
        # a name resolves to several addresses and the first tried may fail (::1 before 127.0.0.1, an IPv6 route the box
        # lacks): the failure stands only until an address answers (2026-10-28)
        if rec is not None and not rec.get("_ok"):
            rec["failed"] = type(exc).__name__ if not str(exc) else f"{type(exc).__name__}: {str(exc)[:80]}"
        raise
    if rec is not None and (not _ex or out == 0):
        try:
            rec["_ok"], rec["failed"] = True, ""
            addr, _ = _addr_parts(address)
            if addr != rec.get("host"):
                rec["ip"] = addr                           # the address that answered
        except Exception:
            pass
    return out
_socket.socket.connect = lambda self, address: _connect_hook(self, address)
_socket.socket.connect_ex = lambda self, address: _connect_hook(self, address, True)


def _count(sock, side, n):
    if n and G.get("_IN_CELL"):
        try:
            rec = _sock_rec(sock)
            if rec is not None:
                rec[side] += int(n)
        except Exception:
            pass


def _plain(sock):
    return not (_ssl and isinstance(sock, _ssl.SSLSocket))

_real_send, _real_sendall, _real_sendto = _socket.socket.send, _socket.socket.sendall, _socket.socket.sendto
_real_recv, _real_recv_into, _real_recvfrom = _socket.socket.recv, _socket.socket.recv_into, _socket.socket.recvfrom
def _send_hook(self, data, *a):
    n = _real_send(self, data, *a)
    if _plain(self):
        _count(self, "out", n)
    return n
def _sendall_hook(self, data, *a):
    r = _real_sendall(self, data, *a)
    if _plain(self):
        _count(self, "out", len(data))
    return r
def _sendto_hook(self, data, *a):
    n = _real_sendto(self, data, *a)
    if G.get("_IN_CELL") and a:
        try:
            if _SOCKS.get(self.fileno()) is None:
                _reach_connect(self, a[-1])
        except Exception:
            pass
    _count(self, "out", n)
    return n
def _recv_hook(self, *a):
    data = _real_recv(self, *a)
    if _plain(self):
        _count(self, "in", len(data))
    return data
def _recv_into_hook(self, *a, **k):
    n = _real_recv_into(self, *a, **k)
    if _plain(self):
        _count(self, "in", n)
    return n
def _recvfrom_hook(self, *a):
    data, addr = _real_recvfrom(self, *a)
    _count(self, "in", len(data))
    return data, addr
_socket.socket.send, _socket.socket.sendall, _socket.socket.sendto = _send_hook, _sendall_hook, _sendto_hook
_socket.socket.recv, _socket.socket.recv_into, _socket.socket.recvfrom = _recv_hook, _recv_into_hook, _recvfrom_hook

_real_listen = _socket.socket.listen
def _listen_hook(self, *a):
    r = _real_listen(self, *a)
    if G.get("_IN_CELL"):
        try:
            host, port = _addr_parts(self.getsockname())
            own, line = _cell_frames()
            _reach_add({"kind": "listen", "host": host, "port": port, "line": line}, ("listen", host, port))
        except Exception:
            pass
    return r
_socket.socket.listen = _listen_hook

if _ssl is not None:
    _real_ssl_send, _real_ssl_read = _ssl.SSLSocket.send, _ssl.SSLSocket.read
    def _ssl_send_hook(self, data, *a):
        n = _real_ssl_send(self, data, *a)
        _count(self, "out", n)
        return n
    def _ssl_read_hook(self, *a, **k):
        r = _real_ssl_read(self, *a, **k)
        _count(self, "in", r if isinstance(r, int) else len(r))
        return r
    _ssl.SSLSocket.send, _ssl.SSLSocket.read = _ssl_send_hook, _ssl_read_hook
    _real_wrap = _ssl.SSLContext.wrap_socket
    def _wrap_hook(self, sock, *a, **k):
        ssock = _real_wrap(self, sock, *a, **k)
        try:
            rec = _SOCKS.get(ssock.fileno())
            if rec is not None:
                rec["tls"] = True
                name = k.get("server_hostname")
                if name and rec.get("host") == rec.get("ip", rec.get("host")):
                    rec["ip"], rec["host"] = rec["host"], str(name)
        except Exception:
            pass
        return ssock
    _ssl.SSLContext.wrap_socket = _wrap_hook

_REACH_ROOTS = _reach_roots()


def _reaches_out():
    """The cell's records for the payload, without the merge keys; the line and the bytes as they stand."""
    recs = G.get("_REACHES") or []
    connected = {r.get("host") for r in recs if r.get("kind") == "net"} | {r.get("ip") for r in recs if r.get("kind") == "net"}
    return [{k: v for k, v in r.items() if not k.startswith("_")} for r in recs if not (r.get("kind") == "dns" and r.get("host") in connected)]


_INTERNAL = {
    "os", "io", "json", "sys", "traceback", "warnings",
    "matplotlib", "plt", "_mpl_figure", "pd", "np", "df", "DS", "RESULT", "_RESULTS", "_CURRENT_CODE", "_generated_dir", "_DATASETS",
    "_real_savefig", "_saved_plots", "_plot_counter", "_analysis_dir",
    "_patched_show", "_patched_savefig", "redirect_stdout",
    "_REACHES", "_IN_CELL",                       # the reach record's state: never in the registry the analyst reads (2026-10-28)
}


# ---- Snapshots: the whole state after a committed step ---------------------
# One per committed step, so the kernel can go back to any of them: a failed
# attempt is rolled back to the last, a follow-up from an earlier chain starts
# from that chain's. A snapshot holds every name the cells made - data,
# functions, classes - and what a later cell would otherwise find changed:
# the modules loaded since the worker started (imported again on restore: a
# submodule reached through its package, an import made for what it
# registers), the random generators, numpy's print options, the pandas options
# and the matplotlib settings a cell set, the working directory. It does not
# hold the files a cell wrote, or what a cell changed inside a library.
#
# A function or a class a cell defined is saved by value (cloudpickle); on
# restore its globals are the live namespace again, so a name a later cell
# rebinds is seen by it as it would have been. What the kernel itself owns -
# G, RESULT, its hooks, the process environment - is named in the snapshot and
# linked on restore, never copied; DS and RESULT are the kernel's own at every
# worker start, whatever a cell bound those names to. A large buffer (an array, a block of a frame) is written once,
# under the hash of its content, and shared by every snapshot that holds it.
# The dataset as loaded is not written at all while `df` holds it unchanged.
#
# A state is saved whole or not at all: one object that cannot be saved (an
# open file, a generator) leaves the step without a snapshot, and the parent
# reaches that state from the nearest saved one before it.
_OWN = globals()
_NOT_SAVED = {_n for _n in _INTERNAL if _n.startswith("_")} | {"DS", "RESULT", "__builtins__"}
_SNAP_INLINE = 1 << 16      # a buffer under this many bytes stays in the snapshot's own file
_failed = {}                # the last save that failed: its error and the names that stood in the way


def _df_fingerprint(_df):
    """A cheap fingerprint of a frame's content. A frame that cannot be hashed gets an object of its own, equal to
    nothing: it is then saved like any other value."""
    try:
        _h = int(pd.util.hash_pandas_object(_df, index=True).sum())
        return (_h, _df.shape, tuple(map(str, _df.columns)), tuple(repr(_t) for _t in _df.dtypes),
                tuple(map(str, _df.index.names)), repr(_df.attrs))
    except Exception:
        return object()


def _source_fingerprint():
    """The fingerprint of the dataset as loaded. The kernel's first worker takes it before its first cell runs and
    leaves it beside the snapshots; the workers that follow read it there."""
    _p = os.path.join(_snap_dir, "source.fp")
    try:
        with open(_p, "rb") as _f:
            return _pickle.load(_f)
    except Exception:
        pass
    _fp = _df_fingerprint(_SOURCE)
    try:
        with open(_p + ".tmp", "wb") as _f:
            _pickle.dump(_fp, _f)
        os.replace(_p + ".tmp", _p)
    except Exception:
        pass
    return _fp


_source_fp = None           # taken before the first cell runs (the serving loop)


def _holds_source():
    """Whether `df` holds the dataset as loaded, unchanged."""
    _df = G.get("df")
    if not isinstance(_source_fp, tuple) or not isinstance(_df, pd.DataFrame) or _df.shape != _source_fp[1]:
        return False
    return _df_fingerprint(_df) == _source_fp


def _owned():
    """id -> what a snapshot writes in place of the object: what the kernel owns is found again by name."""
    _out = {id(G): ("ns",), id(os.environ): ("environ",)}
    for _name, _val in _OWN.items():
        if isinstance(_val, (_types.FunctionType, type)) and getattr(_val, "__module__", None) == "__main__":
            _out[id(_val)] = ("own", _name)
    if _holds_source():
        _out[id(G["df"])] = ("source",)
    return _out


if _cloudpickle is not None:
    class _Saver(_cloudpickle.Pickler):
        def __init__(self, _file, _ids, _keep):
            super().__init__(_file, protocol=5, buffer_callback=_keep)
            self._ids = _ids
            self.globals_ref[id(G)] = G      # a function of the namespace keeps the namespace as its globals

        def persistent_id(self, _obj):
            return self._ids.get(id(_obj))


class _Loader(_pickle.Unpickler):
    def persistent_load(self, _pid):
        _kind = _pid[0]
        if _kind == "ns":
            return G
        if _kind == "own":
            return _OWN[_pid[1]]
        if _kind == "environ":
            return os.environ
        if _kind == "source":
            return _SOURCE
        raise _pickle.UnpicklingError("a snapshot names %r, which this kernel does not have" % (_pid,))


class _Nowhere:
    """A file that keeps nothing: for finding the names that cannot be saved."""
    def write(self, _data):
        return len(_data)


def _pd_options():
    try:
        _keys = list(pd._config.config._registered_options)
    except Exception:
        return {}
    _out = {}
    for _k in _keys:
        try:
            _out[_k] = pd.get_option(_k)
        except Exception:
            pass
    return _out


def _changed(_now, _base):
    """The settings that are not as the worker started with them. One that cannot be compared counts as changed."""
    _out = {}
    for _k, _v in _now.items():
        try:
            if _k not in _base or bool(_v != _base[_k]):
                _out[_k] = _v
        except Exception:
            _out[_k] = _v
    return _out


def _state():
    """What is not a name and a later cell would find changed."""
    return {"np_random": np.random.get_state(), "random": _random.getstate(), "np_print": np.get_printoptions(),
            "pd": _changed(_pd_options(), _PD0), "mpl": _changed(dict(matplotlib.rcParams), _MPL0), "cwd": os.getcwd()}


def _state_set(_s):
    np.random.set_state(_s["np_random"])
    _random.setstate(_s["random"])
    np.set_printoptions(**_s["np_print"])
    for _k, _v in _s["pd"].items():
        try:
            pd.set_option(_k, _v)
        except Exception:
            pass
    for _k, _v in _s["mpl"].items():
        try:
            matplotlib.rcParams[_k] = _v
        except Exception:
            pass
    try:
        os.chdir(_s["cwd"])
    except Exception:
        pass


def _snapshot_save(_path):
    """Save the state to `_path`: its large buffers under the buffers folder, its list of them and of the modules
    loaded beside it. Returns {"ok", "skipped", "bytes", "buffers"}: ok only when every name was saved, skipped the
    names that could not be. A save that fails - an object that cannot be saved, a disk that is full - leaves
    nothing on disk."""
    if _cloudpickle is None:
        return {"ok": False, "skipped": ["<cloudpickle is not installed>"]}
    _names = {_k: _v for _k, _v in G.items() if _k not in _NOT_SAVED}
    _ids, _bufs, _new = _owned(), [], []

    def _keep(_buf):
        _raw = _buf.raw()
        if _raw.nbytes < _SNAP_INLINE:
            return True
        _h = _hashlib.blake2b(_raw, digest_size=16).hexdigest()
        _p = os.path.join(_snap_bufs, _h)
        if not os.path.exists(_p):
            _new.append(_p)
            with open(_p + ".tmp", "wb") as _bf:
                _bf.write(_raw)
            os.replace(_p + ".tmp", _p)
        _bufs.append([_h, _raw.nbytes])
        return False

    try:
        with open(_path + ".tmp", "wb") as _sf:
            _Saver(_sf, _ids, _keep).dump({"names": _names, "state": _state()})
        with open(_path + ".json", "w", encoding="utf-8") as _mf:
            json.dump({"buffers": _bufs, "modules": sorted(set(sys.modules) - _MODS0)}, _mf)
        _size = os.path.getsize(_path + ".tmp")
        os.replace(_path + ".tmp", _path)
    except Exception as _exc:
        for _left in [_path + ".tmp", _path + ".json"] + _new + [_b + ".tmp" for _b in _new]:
            try:
                os.unlink(_left)
            except OSError:
                pass
        _why = "%s: %s" % (type(_exc).__name__, _exc)
        if _failed.get("error") != _why:      # the names are looked for once per error, not at every step it lasts
            _failed.update(error=_why, skipped=[])
            for _k, _v in _names.items():
                try:
                    _Saver(_Nowhere(), _ids, lambda _b: False).dump(_v)
                except Exception:
                    _failed["skipped"].append(_k)
        return {"ok": False, "skipped": sorted(_failed["skipped"]) or ["<%s>" % _why[:120]]}
    _failed.clear()
    return {"ok": True, "skipped": [], "bytes": _size, "buffers": _bufs}


def _snapshot_load(_path):
    """Make the namespace the state saved at `_path`. Raises when it cannot be read whole."""
    with open(_path + ".json", "r", encoding="utf-8") as _mf:
        _meta = json.load(_mf)
    for _m in _meta["modules"]:
        try:
            _importlib.import_module(_m)
        except Exception:
            pass
    _buffers = []
    for _h, _n in _meta["buffers"]:
        with open(os.path.join(_snap_bufs, _h), "rb") as _bf:
            _buffers.append(bytearray(_bf.read()))      # writable, as the arrays were
    _own = {_k: G[_k] for _k in _NOT_SAVED if _k in G}
    with open(_path, "rb") as _sf:
        _snap = _Loader(_sf, buffers=_buffers).load()
    for _k in [_k for _k in G if _k not in _NOT_SAVED and _k not in _snap["names"]]:
        del G[_k]                   # a name the state did not have: `df` after a cell deleted it
    G.update(_snap["names"])
    G.update(_own)                  # the kernel's own names stay its own: a restored function brings the globals it read
    _state_set(_snap["state"])


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
    # extra state has to survive a restore.
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


# ---- Start from a snapshot when given one, then signal ready ----------------
# The settings and the modules as this worker starts with them: a snapshot
# keeps what the cells changed and loaded since. A snapshot that does not load
# ends the worker before it says it is ready: the parent starts from an
# earlier one, never from half a state.
_PD0, _MPL0, _MODS0 = _pd_options(), dict(matplotlib.rcParams), set(sys.modules)
if _snap_from:
    try:
        _snapshot_load(_snap_from)
    except Exception:
        sys.exit(3)

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
    G["_REACHES"] = []
    _DNS.clear()
    if os.path.realpath(G["_analysis_dir"]) not in _REACH_ROOTS:
        _REACH_ROOTS = _reach_roots()              # the plots folder moves with the step

    if _source_fp is None and _SOURCE is not None:
        _source_fp = _source_fingerprint()         # before the first cell can change the frame
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
        G["_IN_CELL"] = True
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
        G["_IN_CELL"] = False
        plt.close("all")

    _snap = {"ok": False, "skipped": []}
    if _error is None and _req.get("snap"):
        try:
            _snap = _snapshot_save(_req["snap"])
        except Exception as _exc:
            _snap = {"ok": False, "skipped": ["<%s>" % type(_exc).__name__]}

    _payload = {
        "stdout": _stdout,
        "error": _error,
        "plots": list(G.get("_saved_plots", [])),
        "results": list(G.get("_RESULTS", [])),
        "datasets": list(G.get("_DATASETS", [])),
        "reaches": _reaches_out(),
        "namespace": _namespace_summary(),
        "columns": _df_columns(),
        "snapshot": _snap,
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


_SANDBOX = None
_CAP_NAMES = {1: "dac_override", 2: "dac_read_search", 7: "setuid", 12: "net_admin", 13: "net_raw", 16: "sys_module",
              17: "sys_rawio", 19: "sys_ptrace", 21: "sys_admin", 27: "mknod"}
_VIRTUAL_FS = {"proc", "sysfs", "tmpfs", "devpts", "mqueue", "cgroup", "cgroup2", "devtmpfs", "securityfs", "pstore",
               "debugfs", "tracefs", "configfs", "fusectl", "hugetlbfs", "binfmt_misc", "autofs", "efivarfs", "bpf",
               "rpc_pipefs", "nsfs", "overlay", "shm", "ramfs", "squashfs"}


def sandbox_facts():
    """What the box the kernel runs on looks like from inside, read once per process (2026-10-28): the user, the
    capabilities, seccomp, the mounts, whether a cloud metadata service answers. Facts the kernel can read, not a
    judgement; a field the box does not expose says so. The reach report prints them beside the reaches."""
    global _SANDBOX
    if _SANDBOX is not None:
        return dict(_SANDBOX)
    f = {"uid": None, "user": "", "root": None, "caps": "", "notable_caps": [], "seccomp": "", "no_new_privs": None,
         "container": "", "pid1": "", "mounts": [], "docker_socket": False, "metadata": "", "platform": sys.platform}
    try:
        f["uid"] = os.getuid()
        f["root"] = f["uid"] == 0
        import pwd
        f["user"] = pwd.getpwuid(f["uid"]).pw_name
    except Exception:
        pass
    try:
        with open("/proc/self/status", encoding="utf-8") as fh:
            for ln in fh:
                key, _, val = ln.partition(":")
                val = val.strip()
                if key == "CapEff":
                    f["caps"] = val
                    bits = int(val, 16)
                    f["notable_caps"] = [n for b, n in sorted(_CAP_NAMES.items()) if bits & (1 << b)]
                elif key == "Seccomp":
                    f["seccomp"] = {"0": "off", "1": "strict", "2": "filter"}.get(val, val)
                elif key == "NoNewPrivs":
                    f["no_new_privs"] = val == "1"
    except Exception:
        pass
    try:
        with open("/proc/1/comm", encoding="utf-8") as fh:
            f["pid1"] = fh.read().strip()
    except Exception:
        pass
    try:
        cg = ""
        if os.path.exists("/proc/1/cgroup"):
            with open("/proc/1/cgroup", encoding="utf-8") as fh:
                cg = fh.read()
        if os.path.exists("/.dockerenv") or "docker" in cg or "containerd" in cg:
            f["container"] = "docker"
        elif "kubepods" in cg:
            f["container"] = "kubernetes"
        elif os.path.exists("/proc/1/cgroup"):
            f["container"] = "none seen"
    except Exception:
        pass
    try:
        with open("/proc/self/mounts", encoding="utf-8") as fh:
            for ln in fh:
                parts = ln.split()
                if len(parts) < 4:
                    continue
                src, point, fstype, opts = parts[:4]
                if fstype in _VIRTUAL_FS or point in ("/", "/etc/hosts", "/etc/hostname", "/etc/resolv.conf") or point.startswith(("/proc", "/sys", "/dev")):
                    continue
                f["mounts"].append(f"{point} ({fstype}, {'ro' if 'ro' in opts.split(',') else 'rw'})")
        f["mounts"] = f["mounts"][:12]
    except Exception:
        pass
    f["docker_socket"] = any(os.path.exists(p) for p in ("/var/run/docker.sock", "/run/docker.sock"))
    try:
        import socket as _sk
        try:
            _sk.create_connection(("169.254.169.254", 80), timeout=0.5).close()
            f["metadata"] = "answered"
        except ConnectionRefusedError:
            f["metadata"] = "refused"
        except (_sk.timeout, TimeoutError):
            f["metadata"] = "timed out"
        except OSError as exc:
            f["metadata"] = f"unreachable ({type(exc).__name__})"
    except Exception:
        pass
    _SANDBOX = f
    return dict(f)


class KernelDead(Exception):
    """Raised internally when the worker process is gone and must be restarted."""


# In the Investigator's default registry view, only this many of the NEWEST
# derived objects carry their full description; every older object is listed
# by NAME only. Names are the reuse contract (reference-by-registry-name) and
# stay complete; descriptions are recognition aids whose value decays with
# age. Measured on a live 40-object run the descriptions were ~75% of the
# volatile tail — the dominant per-turn cost after the audit-4.2 cuts.
REGISTRY_DESC_RECENT = 25


def _fstring_literal_spans(text):
    """The character spans of an f-string token's literal text - everything outside its {expressions} - as offsets
    into the token (python 3.11, where an f-string is one STRING token). The quotes and the prefix count as literal;
    {{ and }} are text; a nested quote inside an expression is part of the expression."""
    import re
    m = re.match(r"[A-Za-z]*(\"\"\"|'''|\"|')", text)
    if not m:
        return [(0, len(text))]
    q = m.group(1)
    body_a = m.end()
    body_b = len(text) - len(q) if text.endswith(q) and len(text) >= body_a + len(q) else len(text)
    spans, depth, i, lit_start = [(0, body_a)], 0, body_a, body_a
    while i < body_b:
        c = text[i]
        if depth == 0:
            if c == "{" and text[i + 1:i + 2] == "{":
                i += 2
                continue
            if c == "{":
                spans.append((lit_start, i))
                depth = 1
            elif c == "}" and text[i + 1:i + 2] == "}":
                i += 2
                continue
        else:
            if c in "\"'":                                  # a string inside the expression is text too
                j = text.find(c, i + 1)
                j = j if j >= 0 else body_b
                spans.append((i, j + 1))
                i = j + 1
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
                if depth == 0:
                    lit_start = i + 1
        i += 1
    if depth == 0:
        spans.append((lit_start, len(text)))
    return spans


def _code_for_security_check(code):
    """The code as the restricted-name check reads it: comments and the text of string literals blanked out, everything
    else verbatim, so a label or a note that mentions a restricted word is not taken for its use (2026-10-05: a
    label '+HR eval@150' was refused as the eval module). An f-string's text is blanked too and its {expressions}
    stay, since those are code (2026-10-28: f"http://{host}/x" had been refused as the http module). Code that
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

    def blank(a, b):
        for i in range(a, min(b, len(chars))):
            if chars[i] != "\n":
                chars[i] = " "

    middle = getattr(tokenize, "FSTRING_MIDDLE", None)          # python 3.12+: an f-string's text is its own token
    for tok in toks:
        a = starts[tok.start[0] - 1] + tok.start[1]
        b = starts[tok.end[0] - 1] + tok.end[1]
        if tok.type == tokenize.COMMENT or (middle is not None and tok.type == middle):
            blank(a, b)
        elif tok.type == tokenize.STRING:
            prefix = re.match(r"[A-Za-z]*", tok.string).group(0).lower()
            if "f" not in prefix:
                blank(a, b)
            else:
                for x, y in _fstring_literal_spans(tok.string):
                    blank(a + x, a + y)
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
        # The code of the committed steps that led to the state the worker holds, in order.
        self._history = []
        # Every committed step is a state the kernel can go back to (goto). A step keeps the step it followed, its
        # code, the registry as it stood, and whether its state is saved: a snapshot file in _snap_dir, written by
        # the worker after the step. A state that is not saved - an object that cannot be, a snapshot that went at
        # the cap - is reached from the nearest saved one before it, by running the steps between again. Step 0 is
        # the state at the start: a fresh worker. A number is given out once, and `uid` tells this kernel's numbers
        # from another's.
        self.uid = uuid.uuid4().hex[:12]
        self._snap_dir = tempfile.mkdtemp(prefix="delve_snap_")
        os.makedirs(os.path.join(self._snap_dir, "b"))
        self._steps = {0: self._step(None, None, {}, {"ok": True})}
        self._at = 0                  # the step whose state the worker holds
        self._seq = 0                 # the last number given out
        self.last_goto = {}           # how the last goto got there: {"step", "from", "replayed": [{"step", "stdout", "error"}]}
        # Latest namespace registry from the worker.
        self.registry = {"namespace": [], "columns": []}
        # Registry as of the last COMMITTED step. Every failed attempt is rolled
        # back to this state (see execute), so the registry shown onward never
        # advertises objects a failed attempt created and then lost.
        self._good_registry = {"namespace": [], "columns": []}
        # True while the live worker holds state from a commit=False execution
        # (chart rendering). Cleared by any restore.
        self._uncommitted = False
        self._proc = None
        self._reader = None
        self._q = None
        self.last_results, self.last_reaches, self.last_refused = [], [], ""
        self.sandbox = sandbox_facts()                 # the box as seen from inside, for the reach report (2026-10-28)
        self._start_worker()

    # ----- worker lifecycle ------------------------------------------------

    def _start_worker(self, snap=None):
        """Start a worker: fresh, or from the snapshot file `snap`. A worker that cannot load its snapshot ends
        before it says it is ready (KernelDead)."""
        self._proc = subprocess.Popen(
            [sys.executable, "-u", self._worker_script_path, self._df_path or "",
             os.path.dirname(os.path.abspath(__file__)),
             snap or "",
             self.generated_dir or "",
             self._snap_dir],
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
        # Wait for the ready token; a large snapshot takes its time to load.
        if not self._await_token(_READY, timeout=max(60, self.step_timeout) if snap else 60):
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

    def _alive(self):
        return self._proc is not None and self._proc.poll() is None

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

    # ----- the states the kernel can go back to ------------------------------

    @staticmethod
    def _step(prev, code, registry, saved):
        """The record of a committed step: the step it followed, its code, the registry as it stood, and what the
        worker said of its snapshot ({"ok", "skipped", "bytes", "buffers"}; skipped: the names that could not be
        saved, when the state was not)."""
        saved = saved or {}
        return {"prev": prev, "code": code, "saved": bool(saved.get("ok")), "bytes": int(saved.get("bytes") or 0),
                "buffers": [list(b) for b in saved.get("buffers") or []], "skipped": list(saved.get("skipped") or []),
                "registry": {"namespace": list(registry.get("namespace") or []),
                             "columns": list(registry.get("columns") or [])}}

    def _snap_path(self, step):
        return os.path.join(self._snap_dir, f"{step}.snap")

    def _chain(self, step):
        """The steps from the start to `step`, in order."""
        out = []
        while step:
            out.append(step)
            step = self._steps[step]["prev"]
        return out[::-1]

    def _commit(self, code, result):
        """A committed step: the next number, the state it made, and the snapshot the worker saved of it, if it
        could. A state that could not be saved is said once, when what stood in the way appears."""
        self._seq += 1
        self.registry = {"namespace": result.get("namespace", []), "columns": result.get("columns", [])}
        self._good_registry = {"namespace": list(self.registry["namespace"]),
                               "columns": list(self.registry["columns"])}
        rec = self._steps[self._seq] = self._step(self._at, code, self.registry, result.get("snapshot"))
        if not rec["saved"] and rec["skipped"] != self._steps[self._at]["skipped"]:
            logger.warning("Persistent kernel: the state after step %d was not saved (%s); the kernel gets back to it "
                           "by running steps again.", self._seq, ", ".join(rec["skipped"][:6]))
        self._at = self._seq
        self._history.append(code)  # only successful committed steps are replayable
        self._prune()

    def _forget(self, step):
        """A step's snapshot goes: its file, and the buffers no other snapshot holds. The step stays a state the
        kernel can reach, from the nearest saved one before it."""
        rec = self._steps[step]
        gone = {h for h, _ in rec["buffers"]}
        rec.update(saved=False, bytes=0, buffers=[], skipped=[])
        held = {h for other in self._steps.values() if other["saved"] for h, _ in other["buffers"]}
        _cleanup_files(self._snap_path(step), self._snap_path(step) + ".json",
                       *[os.path.join(self._snap_dir, "b", h) for h in gone - held])

    def _prune(self):
        """Keep the snapshots under the cap (SNAPSHOT_MB): the oldest go first, the current state's never."""
        def size():
            held = {h: n for rec in self._steps.values() if rec["saved"] for h, n in rec["buffers"]}
            return sum(rec["bytes"] for rec in self._steps.values() if rec["saved"]) + sum(held.values())
        for step in sorted(self._steps):
            if size() <= SNAPSHOT_MB * 1024 * 1024:
                break
            if step and step != self._at and self._steps[step]["saved"]:
                self._forget(step)

    def _restore(self, step, reason=None):
        """Bring the worker to the state after committed step `step`. It starts from the nearest saved state on the
        way there - `step` itself when its state is saved, and then nothing is run again - and runs the steps after
        that one again. A snapshot that does not load sends it one saved state further back. A step that raises,
        hangs or dies when run again sends it to the last resort: a clean worker and the whole history, the
        kernel's behaviour before it kept a snapshot per step, where a step that raises is passed over and the
        namespace may be partial. Where the history hangs or dies even there, the kernel is left without a worker:
        goto says it is not there, and the next step it is given comes here again.

        Rolls back a failed or uncommitted execution and recovers from a timeout or a dead worker (`step` is then
        the step the kernel was at, and `reason` says which; without one it is logged as a WARNING), and serves
        goto. A snapshot is only ever written after an error-free committed step, so it never holds a failed
        attempt's partial changes or uncommitted chart state. On return the history, the registry and the step the
        kernel is at are those of `step`, and last_goto says how it got there."""
        chain = self._chain(step)

        def run_again(steps, pass_over):
            """Run committed steps again: what each printed, and whether the last of them was reached. A step
            that raises ends it, unless it is passed over; a step whose state was not saved is saved now."""
            out = []
            for sid in steps:
                rec = self._steps[sid]
                res = self._run_once(rec["code"], None, snap=None if rec["saved"] else self._snap_path(sid))
                if res is None or res.get("_timeout") or (res.get("error") and not pass_over):
                    return out, False
                if res.get("error"):
                    logger.warning("Step %d raised when run again; passed over.", sid)
                elif not rec["saved"]:
                    rec.update(self._step(rec["prev"], rec["code"], rec["registry"], res.get("snapshot")))
                out.append({"step": sid, "stdout": res.get("stdout"), "error": res.get("error")})
            return out, True

        for covered in [k for k in range(len(chain), 0, -1) if self._steps[chain[k - 1]]["saved"]] + [0]:
            origin, tail = (chain[covered - 1] if covered else 0), chain[covered:]
            (logger.info if reason else logger.warning)(
                "Persistent kernel: %s - from the state after step %d, running %d step(s) again%s.",
                reason or "restarting", origin, len(tail),
                f" (not saved: {', '.join(self._steps[tail[0]]['skipped'][:6])})" if tail and self._steps[tail[0]]["skipped"] else "")
            self._kill_worker()
            try:
                self._start_worker(self._snap_path(origin) if origin else None)
                break
            except (KernelDead, RuntimeError):
                if not origin:
                    raise
                logger.warning("The snapshot of step %d did not load; going further back.", origin)
                self._forget(origin)
        replayed, reached = run_again(tail, pass_over=not origin)
        if not reached and origin:
            logger.warning("The steps after step %d could not be run again; a clean worker runs the whole history.", origin)
            origin = 0
            self._kill_worker()
            self._start_worker()
            replayed, reached = run_again(chain, pass_over=True)
        if not reached:
            logger.error("The kernel could not run its whole history again; it has no worker.")

        self._at = step
        self._history = [self._steps[s]["code"] for s in chain]
        reg = self._steps[step]["registry"]
        self.registry = {"namespace": list(reg["namespace"]), "columns": list(reg["columns"])}
        self._good_registry = {"namespace": list(reg["namespace"]), "columns": list(reg["columns"])}
        self._uncommitted = False
        self.last_goto = {"step": step, "from": origin, "replayed": replayed}
        self._prune()

    def goto(self, step):
        """Bring the kernel to the state after committed step `step` - a number `last_step` gave in this kernel; 0
        is the state at the start. True when the kernel is there. False when it has no such step, or could not
        get there: its history hangs or dies when run again.
        Nothing is run again when that state is saved. Otherwise the steps after the nearest saved state are, and
        last_goto["replayed"] holds what each printed this time, for a caller that compares it with the first."""
        if step not in self._steps:
            return False
        if step == self._at and not self._uncommitted and self._alive():
            self.last_goto = {"step": step, "from": step, "replayed": []}
            return True
        self._restore(step, reason=f"going to step {step}")
        return self._alive()

    # ----- execution -------------------------------------------------------

    @staticmethod
    def _security_word(code):
        """The restricted name the code uses, or None. The check reads the code without its comments and plain
        strings (_code_for_security_check). An entry that names a family (os.exec, os.spawn) matches its members:
        os.execv, os.spawnl (2026-10-28: the word boundary after the entry had matched nothing at all)."""
        import re
        code = _code_for_security_check(code)
        for banned in BLACKLIST:
            pattern = r"\b" + re.escape(banned) + (r"\w*" if banned in ("os.exec", "os.spawn") else "") + r"\b"
            if re.search(pattern, code):
                if banned == "sys" and "sys." not in code:
                    continue
                return banned
        return None

    def _security_refuse(self, code):
        banned = self._security_word(code)
        if banned:
            return (
                "Security notice: code contains restricted module "
                f"({banned}) and was not executed."
            )
        return None

    def _run_once(self, code, analysis_dir, step=None, snap=None):
        """One round-trip to the worker. Returns the result dict, or None if the
        worker died (caller decides whether to restart). Does NOT itself restart.
        `snap` is the file the worker saves its state to after an error-free
        step; without one it saves nothing, so an uncommitted (chart) execution
        can never enter a snapshot."""
        # NOTE: analysis_dir is NOT created here. The folder is made lazily, only
        # when a plot is actually written (see the worker plot patch), so steps
        # that produce no plots — which is all of them, since step cutor is told
        # not to plot — never leave behind an empty NN/ folder.
        if not self._alive():
            return None      # no worker: it died, or a restore could not finish
        code_path = _write_temp_text(code, suffix=".py", prefix="delve_step_")
        fd, result_path = tempfile.mkstemp(suffix=".json", prefix="delve_res_")
        os.close(fd)
        try:
            req = json.dumps({
                "code_path": code_path,
                "result_path": result_path,
                "analysis_dir": analysis_dir or "",
                "step": step,
                "snap": snap or "",
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
                # Hung: kill so the caller can restore the last committed state.
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
        and commit=True; only committed code enters the replayable history, and
        a committed step is a state the kernel can go back to (last_step is its
        number; see goto). Ordinary Python exceptions can mutate objects before
        raising (an in-place df edit on line 1, a raise on line 3), so a failed
        attempt leaves the worker dirty even though nothing was committed — and
        a retry would otherwise see a state the committed record never
        produced. Every failed attempt is therefore ROLLED BACK: the worker is
        brought back to the last committed state (see _restore) before control
        returns, and the error string says so, matching what the next turn's
        traceback context relies on.

        commit=False runs the code against the live namespace WITHOUT
        committing it: no history append, no snapshot, no registry update. Used
        for chart rendering, whose code must see the analytical objects but
        must never become analytical state; call discard_uncommitted()
        afterwards to restore the worker."""
        # what the step touched outside the data and whether it was refused, read by the caller after each step
        # (2026-10-28): a refused step is not run and not an error of the code; a step that reached out and then
        # failed still reached out, so the records stand beside the error
        self.last_reaches, self.last_refused = [], ""
        refusal = self._security_refuse(code)
        if refusal:
            self.last_refused = self._security_word(code) or "restricted"
            return None, refusal, []

        result = self._run_once(code, analysis_dir, step=step,
                                snap=self._snap_path(self._seq + 1) if commit else None)

        # Timeout → roll back to the last committed state, then report.
        if result is not None and result.get("_timeout"):
            self._restore(self._at)
            return None, (
                f"Execution killed: exceeded {self.step_timeout}s time limit. "
                "Simplify the step (fewer iterations, aggregate before fitting, "
                "cap pairwise operations). The attempt was rolled back; the "
                "namespace is exactly as it was before this step."
            ), []

        # Worker died (OOM/segfault) → roll back to the last committed state.
        if result is None:
            self._restore(self._at)
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
        self.last_reaches = list(result.get("reaches") or [])

        if error is not None:
            # TRANSACTIONAL ROLLBACK. The exception may have fired after part of
            # the code already mutated the namespace; bring the worker back to
            # the last committed state so the retry sees exactly the pre-step
            # state. Its snapshot is safe to load: the worker only saves one
            # after an error-free step.
            self._restore(self._at, reason=f"rolling back failed attempt{f' (step {step})' if step else ''}")
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

        self._commit(code, result)
        return stdout, None, plots

    def discard_uncommitted(self, reason="discarding uncommitted state"):
        """Restore the worker to the last committed step if any commit=False
        execution has run since; no-op (returns False) otherwise. Chart
        rendering calls this after its loop so chart-only variables never leak
        into the analytical namespace, the persisted history, or a later
        --resume/--extend replay."""
        if not self._uncommitted:
            return False
        self._restore(self._at, reason=reason)
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
        """Clear the namespace, the history and the snapshots; start a fresh worker (df reloaded)."""
        self._kill_worker()
        shutil.rmtree(os.path.join(self._snap_dir, "b"), ignore_errors=True)
        os.makedirs(os.path.join(self._snap_dir, "b"))
        _cleanup_files(*[p for s in self._steps for p in (self._snap_path(s), self._snap_path(s) + ".json")])
        self._steps = {0: self._steps[0]}
        self._at = 0
        self._history = []
        self.registry = {"namespace": [], "columns": []}
        self._good_registry = {"namespace": [], "columns": []}
        self._uncommitted = False
        self._start_worker()

    @property
    def last_step(self):
        """The state the kernel is at: the number of its last committed step, 0 at the start. What goto takes."""
        return self._at

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
            res = self._run_once(code, None, snap=self._snap_path(self._seq + 1))
            if res is None:                      # worker died mid-replay
                self._restore(self._at)
                res = self._run_once(code, None, snap=self._snap_path(self._seq + 1))
            if res and not res.get("error") and not res.get("_timeout"):
                self._commit(code, res)
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
            _cleanup_files(self._worker_script_path, self._df_path)
            shutil.rmtree(self._snap_dir, ignore_errors=True)
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