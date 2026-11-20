"""The kernel keeps its whole state after every committed step, and goes back to any of them (2.9).

A failed cell is rolled back to the state before it, a follow-up asked from an earlier chain starts from the state
that chain ended in, and nothing is run again to get there - so a step that drew random numbers, or took a minute,
holds what it held. These checks run the real kernel: on its own, through the executor's kernel service, and through
the client the app reaches that service with.

    python3 tests/analyst/test_kernel_snapshots.py
"""
import importlib.util
import json
import logging
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
sys.path[:0] = [HERE, ROOT, os.path.join(ROOT, "delve"), os.path.join(ROOT, "containers", "executor"), os.path.join(ROOT, "tools", "stack", "fakepkgs")]
import _stubs  # noqa: E402,F401
import pandas as pd  # noqa: E402
import kernel as K  # noqa: E402
from kernel import PersistentKernel  # noqa: E402
from analyst import tools  # noqa: E402
from analyst.notebook import Turn  # noqa: E402
from analyst.replay import rehydrate  # noqa: E402

results = []


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("  ok   " if cond else "  FAIL ") + name + ("" if cond else f"  <- {str(detail)[:400]}"))


def frame(rows=400):
    return pd.DataFrame({"plot": range(rows), "yield_t": [x * 0.5 for x in range(rows)], "regime": ["A" if x % 2 else "C" for x in range(rows)]})


def out(kernel, code):
    """What a cell prints - or its error."""
    stdout, err, _ = kernel.execute(code)
    return (err if err else (stdout or "")).strip()


def files(kernel):
    return sorted(f for f in os.listdir(kernel._snap_dir) if f.endswith(".snap"))


def buffers(kernel):
    return sorted(os.listdir(os.path.join(kernel._snap_dir, "b")))


class _Heard(logging.Handler):
    """What the kernel warns of."""
    def __init__(self):
        super().__init__(logging.WARNING)
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


heard = _Heard()
K.logger.addHandler(heard)


# ---- a state is saved after every committed step: data, functions, classes, the random generators, the settings
k = PersistentKernel(df=frame())
check("a kernel starts at step 0, with a name of its own", k.last_step == 0 and len(k.uid) == 12 and k.uid != PersistentKernel.__init__.__name__, (k.last_step, k.uid))
first = out(k, "mean = df['yield_t'].mean()\nbig = np.arange(40000.0)\nprint(mean)")
check("a committed step gets the next number, and its state is saved", first == "99.75" and k.last_step == 1 and k._steps[1]["saved"] and files(k) == ["1.snap"], (first, k.last_step, k._steps[1], files(k)))
out(k, "SCALE = 2\ndef rate(x):\n    return x * SCALE\nplus = lambda v: rate(v) + 1\ndef outer(n):\n    def inner(v):\n        return v + n + SCALE\n    return inner\nadd3 = outer(3)")
out(k, "class Fit:\n    def __init__(self, s):\n        self.s = s\n    def twice(self):\n        return rate(self.s)\nfit = Fit(5)\nsame = big\n_kept = 7")
drawn = out(k, "import random\nr = np.random.rand(3)\nq = random.random()\ngen = np.random.default_rng()\nd = gen.random(2)\nprint(r.round(6), round(q, 6), d.round(6))")
out(k, "pd.set_option('display.max_rows', 7)\nplt.rcParams['figure.figsize'] = (9, 3)\nnp.set_printoptions(precision=2)")
check("a step that defines functions, a lambda, a closure, a class and its instance is saved - the kernel before 2.9 saved nothing from the first function on",
      all(k._steps[n]["saved"] for n in range(1, 6)) and k.last_step == 5, {n: (s["saved"], s["skipped"]) for n, s in k._steps.items()})
pid = k._proc.pid
failed = out(k, "big[0] = -1\ndf['x'] = 1\nraise ValueError('half done')")
check("a failed cell leaves the kernel at the step before it, from that step's snapshot: no step is run again",
      "ValueError" in failed and k.last_step == 5 and k.last_goto == {"step": 5, "from": 5, "replayed": []} and k._proc.pid != pid and len(k.history) == 5, (failed, k.last_goto))
check("... and nothing of the failed cell is there: the array and the frame are as the last committed step left them",
      out(k, "print(big[0], 'x' in df.columns, df.shape)") == "0.0 False (400, 3)")
check("... the settings a cell changed are as it left them: a pandas option, a matplotlib setting, numpy's print options",
      out(k, "print(pd.get_option('display.max_rows'), list(plt.rcParams['figure.figsize']), np.array([1.23456]))") == "7 [9.0, 3.0] [1.23]")
check("... the random numbers drawn without a seed are the ones drawn - numpy's, Python's, a generator's (run again, each would have been drawn anew)",
      out(k, "np.set_printoptions(precision=8)\nprint(r.round(6), round(q, 6), d.round(6))") == drawn, drawn)
check("... the functions work, the closure keeps its cell, the instance is of the class as restored",
      out(k, "print(rate(3), plus(3), add3(1), fit.twice(), isinstance(fit, Fit), type(fit).__name__)") == "6 7 6 10 True Fit")
check("... a global a restored function reads, bound again by a later cell, is the one it sees - its globals are the kernel's namespace, not a copy",
      out(k, "SCALE = 10\nprint(rate(3), add3(1), fit.twice(), rate.__globals__ is globals())") == "30 14 50 True")
check("... a function defined again is the one the others call", out(k, "def rate(x):\n    return -x\nprint(plus(3), fit.twice())") == "-2 -5")
check("... two names of one object are still one object, and an array is writable as it was",
      out(k, "same[1] = 5\nprint(big[1], same is big)") == "5.0 True")
check("... a name with a leading underscore a cell made is kept (the kernel before 2.9 lost it at the first rollback)", out(k, "print(_kept)") == "7")
check("... RESULT and DS are the kernel's own, linked and not copied: a restored helper's RESULT is recorded, DS loads the dataset",
      out(k, "def tell(v):\n    return RESULT('mean yield, 400 plots', v, v - 1, v + 1, 't/ha')\ntell(mean)\nprint(DS.load().shape)").endswith("(400, 3)")
      and len(k.last_results) == 1 and "mean yield" in k.last_results[0]["text"], k.last_results)
out(k, "raise ValueError('again')")
check("... and after a second rollback the helper defined after the first is still recorded by the kernel's RESULT", out(k, "tell(1.0)\nprint('told')").endswith("told") and len(k.last_results) == 1, k.last_results)
out(k, "RESULT = None\nDS = None")
out(k, "raise ValueError('x')")
check("... a cell that bound RESULT or DS to something else: after a restore they are the kernel's own again, as at every worker start", out(k, "print(callable(RESULT), type(DS).__name__)") == "True _Source")

# ---- going back to a step, and on from it another way
at = {"functions": 2, "random": 4, "settings": 5, "end": k.last_step}
check("goto an earlier step: True, the history is that step's, nothing is run again", k.goto(at["random"]) is True and k.last_step == 4 and len(k.history) == 4 and k.last_goto["replayed"] == [], (k.last_step, k.last_goto))
names = [it["name"] for it in k.registry["namespace"]]
check("... the registry is that step's: the names that stood then, none made later", all(n in names for n in ("rate", "fit", "r")) and "tell" not in names, names)
check("... what later steps made is not there, and the settings are the kernel's own again",
      out(k, "np.set_printoptions(precision=8)\nprint('tell' in globals(), SCALE, rate(3), pd.get_option('display.max_rows'), list(plt.rcParams['figure.figsize']), r.round(6), round(q, 6), d.round(6))")
      == "False 2 6 2000 [6.4, 4.8] " + drawn, drawn)
way_b = k.last_step
check("a step taken from an earlier state gets a number never given before: the first way's steps keep theirs", way_b == at["end"] + 1 and k._steps[way_b]["prev"] == at["random"], (way_b, at))
after = out(k, "print(np.random.rand(1).round(6), round(random.random(), 6))")
check("the random stream goes on from a state as it went on the first time: the next draws are the same ones (a fresh worker would draw others)",
      k.goto(way_b) and out(k, "print(np.random.rand(1).round(6), round(random.random(), 6))") == after and k.goto(way_b) and out(k, "print(np.random.rand(2).round(6)[0])") in after, after)
check("goto the end of the first way: its names and its rebound function are there again", k.goto(at["end"]) and out(k, "print(rate(3), 'tell' in globals(), SCALE)") == "-3 True 10")
pid = k._proc.pid
check("goto the step the kernel is at: nothing restarts", k.goto(k.last_step) is True and k._proc.pid == pid and k.last_goto["replayed"] == [])
check("goto the start: no name a cell made, the dataset as loaded", k.goto(0) is True and k.last_step == 0 and k.history == [] and out(k, "print('mean' in globals(), df.shape, pd.get_option('display.max_rows'))") == "False (400, 3) 2000")
check("goto a step the kernel never made: False, and it stays where it is", k.goto(999) is False and k.goto(-1) is False and k.last_step == k._seq, (k.last_step, k._seq))
k.execute("extra = 1", commit=False)
check("an uncommitted execution makes no step and saves nothing; goto the step the kernel is at drops what it made",
      k.last_step == k._seq and len(files(k)) == sum(1 for s in k._steps.values() if s["saved"]) - 1 and k.goto(k.last_step) is True and out(k, "print('extra' in globals())") == "False"
      and k.discard_uncommitted() is False, (k.last_step, k._seq, files(k)))
k.execute("extra = 1", commit=False)
check("... and so does discarding it, once", k.discard_uncommitted() is True and k.discard_uncommitted() is False and out(k, "print('extra' in globals())") == "False")
snap_dir = k._snap_dir
k.cleanup()
check("cleanup removes the kernel's snapshots", not os.path.exists(snap_dir))

# ---- the dataset as loaded is named, not written; a large buffer is written once; the cap
k = PersistentKernel(df=frame(30000))
out(k, "total = float(df['yield_t'].sum())\nsmall = np.arange(100.0)\nprint('counted')")
first = dict(k._steps[1])
check("while df holds the dataset as loaded a snapshot does not carry it, and a small array stays in the snapshot's own file: the file is small, there is no buffer",
      first["saved"] and first["bytes"] < 20000 and first["buffers"] == [] and buffers(k) == [], (first, buffers(k)))
for change, probe, want in (("df.attrs['note'] = 'kept'", "print(df.attrs)", "{'note': 'kept'}"),
                            ("df.index.name = 'plot_id'", "print(df.index.name)", "plot_id"),
                            ("df.loc[0, 'yield_t'] = -5.0", "print(df.loc[0, 'yield_t'], df.shape)", "-5.0 (30000, 3)")):
    out(k, "df = DS.load()\n" + change)
    carried = len(k._steps[k.last_step]["buffers"])
    out(k, "raise ValueError('x')")
    back = out(k, probe)
    check(f"a change to df that leaves its shape alone ({change}): it is no longer the dataset as loaded - the snapshot carries the frame, and it comes back changed", carried >= 1 and back == want, (carried, back))
out(k, "df = DS.load()\ndf['doubled'] = df['yield_t'] * 2")
grown = dict(k._steps[k.last_step])
check("a column added to df in place: the snapshot carries the frame, its large blocks as buffers", grown["saved"] and len(grown["buffers"]) >= 1, grown)
held = buffers(k)
out(k, "note = 'nothing large changed'")
check("a buffer is written once: the next snapshot holds the same ones and adds no file", buffers(k) == held and k._steps[k.last_step]["buffers"] == grown["buffers"], (held, buffers(k)))
out(k, "raise ValueError('x')")
check("the frame changed in place comes back changed, and can be changed again", out(k, "df.loc[0, 'doubled'] = 9.0\nprint(df.shape, df.loc[0, 'doubled'])") == "(30000, 4) 9.0")
out(k, "df = DS.load()")
check("df = DS.load(): the dataset as loaded again, and the snapshot stops carrying a frame", k._steps[k.last_step]["saved"] and k._steps[k.last_step]["buffers"] == [], k._steps[k.last_step])
out(k, "del df")
out(k, "raise ValueError('x')")
check("a cell deleted df: after a rollback there is no df, though a fresh worker loads one", out(k, "print('df' in globals(), DS.load().shape)").startswith("False (30000, 3)"))
out(k, "df = DS.load()\nenv = os.environ\nreader = open\nshow = plt.show")
out(k, "raise ValueError('x')")
check("what a cell took from the kernel's own - the environment, the hooked open, the patched show - is linked on restore, not copied",
      out(k, "print(env is os.environ, reader is open, show is plt.show)") == "True True True")
_there = os.path.realpath(tempfile.mkdtemp(prefix="bamboo_cwd_"))
out(k, f"os.chdir({_there!r})")
out(k, "raise ValueError('x')")
_now = out(k, "print(os.getcwd())")
check("the working directory a cell moved to is where the kernel is after a restore", _now == _there, (_now, _there))
out(k, "wide = np.arange(50000.0)")
out(k, "note2 = 1")
K.SNAPSHOT_MB, _cap = 0, K.SNAPSHOT_MB           # the cap at nothing: only the state the kernel is at keeps its snapshot
out(k, "note3 = 2")
check("over the cap the oldest snapshots go, files and buffers, and the state the kernel is at keeps its own - with the buffer it shares with those that went",
      files(k) == [f"{k.last_step}.snap"] and [n for n, s in k._steps.items() if n and s["saved"]] == [k.last_step] and buffers(k) == [h for h, _ in k._steps[k.last_step]["buffers"]] and len(buffers(k)) == 1,
      (files(k), buffers(k), k._steps[k.last_step]))
out(k, "raise ValueError('x')")
check("... so a rollback still starts from it and runs nothing again", k.last_goto["replayed"] == [] and out(k, "print(wide.shape, note3)") == "(50000,) 2", k.last_goto)
K.SNAPSHOT_MB = 1                                # room for two arrays of 400 KB, not for three
kc = PersistentKernel()
for code in ("w = np.arange(50000.0)", "a = 1", "b = 2"):
    out(kc, code)
check("a buffer three snapshots share is counted once: the three stay under a cap that three arrays would break", [n for n, st in kc._steps.items() if n and st["saved"]] == [1, 2, 3] and len(buffers(kc)) == 1,
      ({n: st["saved"] for n, st in kc._steps.items()}, buffers(kc)))
for i in (1, 2):
    out(kc, f"w = np.arange(50000.0) + {i}")
check("with a third array the oldest snapshots go until the rest fits: the three that held the first array, and the array with them",
      [n for n, st in kc._steps.items() if n and st["saved"]] == [4, 5] and files(kc) == ["4.snap", "5.snap"] and len(buffers(kc)) == 2, ({n: st["saved"] for n, st in kc._steps.items()}, files(kc), buffers(kc)))
kc.cleanup()
K.SNAPSHOT_MB = _cap
check("a state whose snapshot went is still reached: from the start, by running its steps again - goto says which, and what each printed",
      k.goto(2) is True and k.last_goto["from"] == 0 and [s["step"] for s in k.last_goto["replayed"]] == [1, 2] and all(s["error"] is None for s in k.last_goto["replayed"])
      and k.last_goto["replayed"][0]["stdout"].strip() == "counted" and out(k, "print(df.attrs, total, small.shape)") == "{'note': 'kept'} 224992500.0 (100,)", k.last_goto)
check("... and the steps run again on the way are saved again", k._steps[1]["saved"] and k._steps[2]["saved"], {n: s["saved"] for n, s in k._steps.items()})
k.cleanup()

# ---- a state that cannot be saved; a snapshot that does not load; a worker that dies or hangs
k = PersistentKernel(df=frame(), step_timeout=4)
out(k, "kept = [1, 2, 3]")
out(k, "wide = np.arange(50000.0)\nstream = (n * n for n in kept)\nprint('made')")
check("one object that cannot be saved (a generator) leaves the step without a snapshot - nothing of the attempt stays on disk - and the kernel knows which name stood in the way",
      not k._steps[2]["saved"] and k._steps[2]["skipped"] == ["stream"] and files(k) == ["1.snap"] and buffers(k) == [], (k._steps[2], files(k), buffers(k)))
out(k, "later = sum(kept)")
_said = [line for line in heard.lines if "was not saved" in line]
check("... nor the steps after it while the object is there; the kernel warns of it once, at the step the object appeared - where the executor's log shows it",
      not k._steps[3]["saved"] and k._steps[3]["skipped"] == ["stream"] and len(_said) == 1 and "step 2 was not saved (stream)" in _said[0], (k._steps[3], _said))
out(k, "raise ValueError('x')")
check("a rollback then starts from the nearest saved state and runs the steps after it again",
      k.last_goto["from"] == 1 and [s["step"] for s in k.last_goto["replayed"]] == [2, 3] and k.last_goto["replayed"][0]["stdout"].strip() == "made" and out(k, "print(later, next(stream))") == "6 1", k.last_goto)
out(k, "del stream")
check("once the object is gone the state is saved again", k._steps[k.last_step]["saved"] and k._steps[k.last_step]["skipped"] == [], k._steps[k.last_step])
out(k, "flow = (n for n in kept)")
check("another object that cannot be saved: the kernel names that one, not the one before", k._steps[k.last_step]["skipped"] == ["flow"], k._steps[k.last_step])
out(k, "del flow\nimport threading\nlock = threading.Lock()")
check("... and when the next save fails on another kind of object, that one", k._steps[k.last_step]["skipped"] == ["lock"], k._steps[k.last_step])
out(k, "del lock")
_once = os.path.join(tempfile.mkdtemp(prefix="bamboo_once_"), "ran")
out(k, "kept2 = len(kept)")
out(k, f"import pathlib\nmark = pathlib.Path({_once!r})\nassert not mark.exists(), 'ran before'\nmark.touch()\nflow = (n for n in kept)")
_started, _start = [], k._start_worker
k._start_worker = lambda snap=None: (_started.append(bool(snap)), _start(snap))[1]
out(k, "raise ValueError('x')")
del k._start_worker
check("a step that raises when run again sends the kernel to its last resort at once - two workers: one from the nearest saved state, one clean for the whole history, that step passed over - and the kernel says so",
      _started == [True, False] and k.last_goto["from"] == 0 and [s["step"] for s in k.last_goto["replayed"]] == k._chain(k.last_step) and "ran before" in (k.last_goto["replayed"][-1]["error"] or "")
      and all(s["error"] is None for s in k.last_goto["replayed"][:-1]) and out(k, "print(kept2, 'flow' in globals())") == "3 False", (_started, k.last_goto))
good = k.last_step
out(k, "more = 1")
with open(k._snap_path(k.last_step), "wb") as fh:
    fh.write(b"not a snapshot")
out(k, "raise ValueError('x')")
check("a snapshot that does not load is dropped: the kernel starts from the one before and runs the step again",
      k.last_goto["from"] == good and [s["step"] for s in k.last_goto["replayed"]] == [good + 1] and out(k, "print(more, later)") == "1 6", k.last_goto)
check("... and the step run again was saved again: the kernel goes back to it with nothing run", k.goto(good + 1) is True and k.last_goto == {"step": good + 1, "from": good + 1, "replayed": []}, k.last_goto)
here = k.last_step
died = out(k, "import os as _o\n_o.kill(_o.getpid(), 9)")
check("a worker that dies is replaced from the last snapshot: the state is whole and no step is run again",
      "crashed" in died and k.last_step == here and k.last_goto["replayed"] == [] and out(k, "print(more, later)") == "1 6", (died, k.last_goto))
k._proc.kill(); k._proc.wait()
check("goto the step the kernel is at, its worker dead: a new worker from that step's snapshot", k.goto(k.last_step) is True and k.last_goto["replayed"] == [] and out(k, "print(more)") == "1", k.last_goto)
here = k.last_step
hung = out(k, "import time\ntime.sleep(30)")
check("a step over the time limit is killed and the kernel is back at the last snapshot", "time limit" in hung and k.last_step == here and k.last_goto["replayed"] == [] and out(k, "print(more)") == "1", (hung, k.last_goto))
_slow = _once + ".slow"
out(k, f"import time, pathlib\ntime.sleep(30 if pathlib.Path({_slow!r}).exists() else 0)\nflow = (n for n in kept)")
open(_slow, "w").close()
k._proc.kill(); k._proc.wait()
check("a step that hangs when run again - from the nearest saved state, then from the start: the kernel cannot get there, goto says so, and it is left without a worker",
      k.goto(k.last_step) is False and not k._alive() and k.last_goto["from"] == 0 and k.last_goto["replayed"][-1]["step"] == k._steps[k.last_step]["prev"], k.last_goto)
os.remove(_slow)
crashed = out(k, "after = 1")
check("... the next cell it is given starts one: that cell is answered as a crash, and the kernel is whole again", "crashed" in crashed and out(k, "print(more, next(flow))") == "1 1", crashed)
out(k, "del flow")
here = k.last_step
k.restore_history(["a = 1", "b = a + 1", "raise ValueError('skipped')", "c = b + 1"])
check("a history replayed into the kernel makes a step for each code that ran, each with its snapshot",
      k.last_step == here + 3 and all(k._steps[n]["saved"] for n in range(here + 1, here + 4)) and k.history[-3:] == ["a = 1", "b = a + 1", "c = b + 1"] and out(k, "print(a, b, c)") == "1 2 3", (here, k.last_step, k.history[-3:]))
k.reset()
check("reset: the start again - no step, no snapshot, no name", k.last_step == 0 and list(k._steps) == [0] and files(k) == [] and buffers(k) == [] and out(k, "print('a' in globals(), df.shape)") == "False (400, 3)", (k._steps, files(k)))
k.cleanup()

k = PersistentKernel()
out(k, "import resource\nresource.setrlimit(resource.RLIMIT_FSIZE, (200000, resource.getrlimit(resource.RLIMIT_FSIZE)[1]))")
out(k, "wide = np.arange(50000.0)")
check("a save the disk does not take (here a file may grow to 200 KB, and the array is 400 KB) leaves nothing behind - no snapshot, no list, no buffer cut short - and the step says why",
      not k._steps[2]["saved"] and "File too large" in k._steps[2]["skipped"][0] and sorted(os.listdir(k._snap_dir)) == ["1.snap", "1.snap.json", "b"] and buffers(k) == [],
      (k._steps[2], os.listdir(k._snap_dir), buffers(k)))
out(k, "raise ValueError('x')")
check("... and in the worker that takes over, the step run again is saved", k.last_goto["from"] == 1 and k._steps[2]["saved"] and len(buffers(k)) == 1, (k.last_goto, k._steps[2]))
k.cleanup()

# ---- what a cell imported is imported again in the worker that takes over
_kit = tempfile.mkdtemp(prefix="bamboo_fieldkit_")
os.makedirs(os.path.join(_kit, "fieldkit"))
for _file, _text in (("__init__.py", ""), ("soil.py", "def grade(x):\n    return x * 2\n"),
                     ("marks.py", "import pandas as pd\n\n\n@pd.api.extensions.register_dataframe_accessor('trial')\nclass Trial:\n    def __init__(self, frame):\n        self.frame = frame\n\n    def plots(self):\n        return len(self.frame)\n")):
    with open(os.path.join(_kit, "fieldkit", _file), "w", encoding="utf-8") as fh:
        fh.write(_text)
_path = os.environ.get("PYTHONPATH")
os.environ["PYTHONPATH"] = _kit + (os.pathsep + _path if _path else "")
try:
    k = PersistentKernel(df=frame())
    out(k, "import fieldkit.soil\nimport fieldkit.marks")
    with open(k._snap_path(1) + ".json", encoding="utf-8") as fh:
        loaded = json.load(fh)["modules"]
    check("a snapshot lists the modules loaded since the worker started, and none of the worker's own", {"fieldkit", "fieldkit.soil", "fieldkit.marks"} <= set(loaded) and "pandas" not in loaded, loaded)
    out(k, "raise ValueError('x')")
    check("... and the worker that takes over imports them again: a submodule is reached through its package, and an import made for what it registers has registered it",
          k.last_goto["replayed"] == [] and out(k, "print(fieldkit.soil.grade(3), df.trial.plots())") == "6 400", k.last_goto)
    k.cleanup()
finally:
    if _path is None:
        del os.environ["PYTHONPATH"]
    else:
        os.environ["PYTHONPATH"] = _path

# ---- without the library that saves functions, nothing is saved and the kernel works as it did before 2.9
_no = tempfile.mkdtemp(prefix="bamboo_no_cloudpickle_")
with open(os.path.join(_no, "cloudpickle.py"), "w", encoding="utf-8") as fh:
    fh.write("raise ImportError('not installed')\n")
_path = os.environ.get("PYTHONPATH")
os.environ["PYTHONPATH"] = _no + (os.pathsep + _path if _path else "")
try:
    k = PersistentKernel(df=frame())
    out(k, "def half(x):\n    return x / 2\nv = half(8)")
    out(k, "raise ValueError('x')")
    check("without cloudpickle no state is saved and a rollback runs the whole history again, as the kernel did before 2.9",
          not k._steps[1]["saved"] and "cloudpickle" in k._steps[1]["skipped"][0] and k.last_goto["from"] == 0 and [s["step"] for s in k.last_goto["replayed"]] == [1] and out(k, "print(v, half(2))") == "4.0 1.0", (k._steps[1], k.last_goto))
    k.cleanup()
finally:
    if _path is None:
        del os.environ["PYTHONPATH"]
    else:
        os.environ["PYTHONPATH"] = _path

# ---- through the executor's kernel service, and through the client the app reaches it with
os.chdir(tempfile.mkdtemp(prefix="bamboo_exec_snapshots_"))
import code_executor_api as E  # noqa: E402
# the client's own file, not the package around it: the suite then needs nothing the executor image lacks, and runs
# inside it - docker run --rm -v "$PWD":/src:ro -w /src <image> python tests/analyst/test_kernel_snapshots.py
_spec = importlib.util.spec_from_file_location("kernel_client", os.path.join(ROOT, "bambooai", "kernel_client.py"))
_client = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_client)
RemoteKernel, KernelUnavailable = _client.RemoteKernel, _client.KernelUnavailable

c = E.app.test_client()
E.df_cache.put("s1", frame())
started = c.post("/kernel/start", json={"df_id": "s1"}).get_json() or {}
sid = started.get("session_id")
try:
    one = c.post("/kernel/execute", json={"session_id": sid, "code": "def area(w, h):\n    return w * h\nfield = area(3, 4)"}).get_json() or {}
    two = c.post("/kernel/execute", json={"session_id": sid, "code": "field = area(5, 5)\nprint(field)"}).get_json() or {}
    bad = c.post("/kernel/execute", json={"session_id": sid, "code": "field = None\nraise ValueError('x')"}).get_json() or {}
    check("executor: /kernel/execute says the step the kernel is at - the next number after a committed step, the same one after a failed cell - and /kernel/start says a new kernel is at step 0",
          (started.get("step"), one.get("step"), two.get("step"), bad.get("step")) == (0, 1, 2, 2) and bad.get("error"), (started.get("step"), one.get("step"), two.get("step"), bad.get("step")))
    back = c.post("/kernel/goto", json={"session_id": sid, "step": 1}).get_json() or {}
    seen = c.post("/kernel/execute", json={"session_id": sid, "code": "print(field, area(2, 2))"}).get_json() or {}
    check("executor: /kernel/goto brings the kernel to a step's state, with nothing run again, and says so",
          back.get("reached") is True and back.get("step") == 1 and back.get("from") == 1 and back.get("replayed") == [] and back.get("history_len") == 1 and (seen.get("stdout") or "").strip() == "12 4" and seen.get("step") == 3, (back, seen))
    none = c.post("/kernel/goto", json={"session_id": sid, "step": 77})
    check("executor: /kernel/goto to a step the kernel never made is not reached; without a step it is refused; a session that is gone is 410",
          none.status_code == 200 and none.get_json().get("reached") is False and none.get_json().get("step") == 3
          and c.post("/kernel/goto", json={"session_id": sid}).status_code == 400 and c.post("/kernel/goto", json={"session_id": "gone", "step": 1}).status_code == 410, none.get_data(as_text=True)[:200])
    c.post("/kernel/execute", json={"session_id": sid, "code": "stream = (n for n in range(3))\nprint('made')"})
    c.post("/kernel/execute", json={"session_id": sid, "code": "after = 1"})
    again = c.post("/kernel/goto", json={"session_id": sid, "step": 4}).get_json() or {}
    check("executor: /kernel/goto to a state that was not saved says where it started from and which steps it ran again, with what each printed",
          again.get("reached") is True and again.get("step") == 4 and again.get("from") == 3 and again.get("replayed") == [{"step": 4, "stdout": "made\n", "error": None}], again)
finally:
    c.post("/kernel/stop", json={"session_id": sid})


class _Reply:
    def __init__(self, r):
        self.status_code, self.headers, self.text, self._r = r.status_code, r.headers, r.get_data(as_text=True), r

    def json(self):
        return self._r.get_json()

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)


class _Http:
    """The executor's routes in the place of the client's HTTP session."""
    def post(self, url, json=None, timeout=None):
        return _Reply(c.post(url.split("//executor", 1)[1], json=json))

    def get(self, url, timeout=None):
        return _Reply(c.get(url.split("//executor", 1)[1]))


rk = RemoteKernel("http://executor", df_id="s1", session=_Http(), force=True)
try:
    check("client: a kernel in the executor is named by its session and starts at step 0", rk.uid == rk.session_id and rk.last_step == 0 and tools.snap(rk) == f"{rk.session_id}:0")
    rk.execute("def area(w, h):\n    return w * h\nfield = area(3, 4)")
    first_state = tools.snap(rk)
    rk.execute("field = area(5, 5)")
    check("client: after an execution it knows the step the kernel is at, and a record keeps it as <kernel>:<step>", rk.last_step == 2 and first_state == f"{rk.session_id}:1" and tools.snap(rk) == f"{rk.session_id}:2" and tools.snap(rk, 0) == f"{rk.session_id}:0", (rk.last_step, first_state))
    check("client: goto a state a record names - the kernel is there, the history is that state's", tools.goto(rk, first_state) is True and rk.last_step == 1 and rk.history == ["def area(w, h):\n    return w * h\nfield = area(3, 4)"]
          and rk.last_goto == {"step": 1, "from": 1, "replayed": []} and (rk.execute("print(field)")[0] or "").strip() == "12", (rk.last_step, rk.history, rk.last_goto))
    again = RemoteKernel("http://executor", session_id=rk.session_id, session=_Http())
    check("client: a second client of the same session knows the step the kernel is at", again.last_step == rk.last_step == 3 and again.uid == rk.uid, (again.last_step, rk.last_step))
    again.detach()
    check("client: a state of another kernel, a state it never had, a record without one: not gone to",
          tools.goto(rk, "another:1") is False and tools.goto(rk, f"{rk.session_id}:55") is False and tools.goto(rk, "") is False and tools.goto(rk, f"{rk.session_id}:x") is False and rk.last_step == 3, rk.last_step)
    c.post("/kernel/stop", json={"session_id": rk.session_id})
    try:
        rk.goto(1)
        gone = None
    except KernelUnavailable as exc:
        gone = exc.gone
    check("client: goto in a session the executor no longer has says the kernel is gone, as an execution does", gone is True, gone)
finally:
    rk.cleanup()

# ---- the record: a kernel that keeps no step names none; rehydrating names each cell's state in the new kernel
class _Plain:
    """A kernel from before 2.9: no name, no step, no goto."""
    def execute(self, code):
        return "", None, []


class _Old(_Plain):
    """The client of an executor image before v75: its session for a name, and no step."""
    uid, last_step = "session", None


check("a kernel that keeps no step - one from before 2.9, or the client of an executor image before v75, which has a session and no step: a record gets no state from it, and it is not asked to go anywhere",
      [tools.snap(old, at) for old in (_Plain(), _Old()) for at in (None, 0)] == ["", "", "", ""] and tools.goto(_Plain(), "k:1") is False)
k = PersistentKernel(df=frame())
cells = [Turn(kind="cell", code="a = 1", cell_no=1, snap="gone:1"), Turn(kind="cell", code="b = a + 1", cell_no=2, snap="gone:2"), Turn(kind="cell", code="c = b + 1", cell_no=3)]
n, err = rehydrate(k, cells)
check("rehydrate: each cell's record names its state in the kernel it was run again in", (n, err) == (3, "") and [t.snap for t in cells] == [f"{k.uid}:1", f"{k.uid}:2", f"{k.uid}:3"], [t.snap for t in cells])
check("... so that kernel goes back to any of them", tools.goto(k, cells[1].snap) and out(k, "print(b, 'c' in globals())") == "2 False")
more = [Turn(kind="cell", code="d = 1", cell_no=4), Turn(kind="cell", code="d = 1 / 0", cell_no=5, snap="old:5"), Turn(kind="cell", code="e = 1", cell_no=6)]
n, err = rehydrate(k, more)
check("rehydrate: it stops at the cell that fails, whose record keeps the state it named before; the cells after it are not run",
      n == 1 and "cell 5 failed on replay" in err and [t.snap for t in more] == [f"{k.uid}:{k.last_step}", "old:5", ""], [t.snap for t in more])
k.cleanup()

n_fail = sum(1 for _, ok in results if not ok)
print(f"\n{len(results) - n_fail} passed, {n_fail} failed")
sys.exit(1 if n_fail else 0)
