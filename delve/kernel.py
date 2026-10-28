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
from codeutils import BLACKLIST, _write_temp_text, _cleanup_files, _serialize_dataframe

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
    G["_REACHES"] = []
    _DNS.clear()
    if os.path.realpath(G["_analysis_dir"]) not in _REACH_ROOTS:
        _REACH_ROOTS = _reach_roots()              # the plots folder moves with the step

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
        "reaches": _reaches_out(),
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
        self.last_results, self.last_reaches, self.last_refused = [], [], ""
        self.sandbox = sandbox_facts()                 # the box as seen from inside, for the reach report (2026-10-28)
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
        # what the step touched outside the data and whether it was refused, read by the caller after each step
        # (2026-10-28): a refused step is not run and not an error of the code; a step that reached out and then
        # failed still reached out, so the records stand beside the error
        self.last_reaches, self.last_refused = [], ""
        refusal = self._security_refuse(code)
        if refusal:
            self.last_refused = self._security_word(code) or "restricted"
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
        self.last_reaches = list(result.get("reaches") or [])

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