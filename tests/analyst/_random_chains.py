"""Random small chains for the tests of the reading (test_routines.py; docs/ROUTINES_DESIGN.md §19, §22): each is run
as written and as pruned, and the RESULT values must be the same; each is run a statement at a time with one statement
made to stop, and no line that still comes back may differ. The statements are of the kinds the reading claims to see -
assignments, in-place changes, deletions, functions that change or read what is outside them or change what they are
handed, bare calls, draws from numpy's global generator, the standard library's and one made by default_rng, names read
through strings, loops and branches, prints. A second name for one object is left out: the reading does not claim it
(the shorter run is held to run zero for that, and a run checks the objects themselves). Found with it, 2026-11-13: a
call reads what the function's body reads when it is called, not when it was defined; numpy's global generator and the
standard library's are two states, not one."""
import contextlib, io

import numpy as np
import pandas as pd

V, L, D = ["v%d" % i for i in range(5)], ["l%d" % i for i in range(3)], ["d%d" % i for i in range(2)]


def _expr(r):
    k = r.random()
    if k < 0.3:
        return str(r.randint(0, 9))
    if k < 0.6:
        return r.choice(V)
    if k < 0.75:
        return f"{r.choice(V)} + {r.choice(V)}"
    return r.choice([f"len({r.choice(L)})", f"sum({r.choice(L)})", f"len({r.choice(D)})"])


def _statement(r, funcs):
    """One top-level statement; `funcs` are the one-argument functions defined so far."""
    v, w, l, d = r.choice(V), r.choice(V), r.choice(L), r.choice(D)
    name = "f%d" % len(funcs)
    defs = [f"def {name}(x):\n    {l}.append(x)\n    return x + 1", f"def {name}(x):\n    global {v}\n    {v} = {v} + x\n    return {v}", f"def {name}(x):\n    return x * 2 + {w}",
            f"def {name}(x):\n    RESULT('in {name}', float(x))\n    return x", f"def {name}(x):\n    {d}['a'] = x\n    return len({d})"]
    kinds = [f"{v} = {_expr(r)}"] * 8 + [f"print({_expr(r)})"] * 5 + [f"{l}.append({_expr(r)})"] * 3 + [r.choice(defs)] * 3 + [
        f"{l} = [{_expr(r)}, {_expr(r)}]", f"{d}[{r.choice(['a', 'b'])!r}] = {_expr(r)}", f"{d} = dict(a={_expr(r)})", f"if 'a' in {d}:\n    del {d}['a']",
        f"def fill(t, x):\n    t.append(x)\nfill({l}, {_expr(r)})", f"np.random.seed({r.randint(0, 5)})", f"{v} = int(np.random.randint(0, 100))", f"{v} = int(np.random.randint(0, 100))",
        f"rng = np.random.default_rng({r.randint(0, 5)})", f"{v} = int(rng.integers(0, 100))", f"{v} = int(rng.integers(0, 100))",
        f"for i_ in range({r.randint(1, 3)}):\n    {v} = {v} + i_\n    {l}.append(i_)", f"if {w} > {r.randint(0, 9)}:\n    {v} = {_expr(r)}\nelse:\n    {l}.append(1)",
        f"{v} = int(pd.DataFrame({{'q': [1, 2, 3]}}).query('q > @{w}').shape[0])", f"{v} = globals().get({w!r}, 0) + 1", f"{l}.sort()", f"{v} += {_expr(r)}",
        f"assert {v} is not None", f"{v} = eval({(w + ' + 1')!r})", f"np.random.shuffle({l})", f"import random\nrandom.seed({r.randint(0, 3)})", f"import random\n{v} = random.randint(0, 9)",
        f"try:\n    {v} = int({l}[0])\nexcept IndexError:\n    {v} = 0", f"while {v} > 3:\n    {v} = {v} - 2\n    {l}.append({v})", f"{v}, {w} = {w}, {v}", f"{l} += [{v}]",
        f"{v} = (lambda q: q + {w})({r.randint(0, 5)})", f"def draw(g):\n    return int(g.integers(0, 10))\n{v} = draw(rng)", f"def roll():\n    return int(np.random.randint(0, 9))\n{v} = roll()",
        f"{v} = len([{l}.append(q) for q in range({r.randint(0, 2)})])", f"{v} = sum(q for q in {l} if q > {w})", f"{d}.update(b={v})", f"{v} = {d}.pop('a', 0)",
        f"{v} = {l}.pop() if {l} else 0", f"for k_ in list({d}):\n    {l}.append({d}[k_])", f"{v} = max({l} or [0])"]
    if funcs:
        f = r.choice(funcs)
        kinds += [f"{v} = {f}({_expr(r)})", f"{f}({_expr(r)})", f"{v} = sum(map({f}, [1, 2]))", f"{v} = [{f}(q) for q in range(2)][-1]", f"print({f}({r.randint(0, 5)}))",
                  f"def {name}(x):\n    return {f}(x) + 1"] * 2
        defs.append(f"def {name}(x):\n    return {f}(x) + 1")
    pick = r.choice(kinds)
    if pick in defs:
        funcs.append(name)
    return pick


def chain(r) -> str:
    """A chain of three to six cells: every name bound in the first, then statements at random, one to three RESULT
    calls among them."""
    funcs = []
    first = [f"{v} = {r.randint(0, 9)}" for v in V] + [f"{l} = []" for l in L] + [f"{d} = {{}}" for d in D] + ["rng = np.random.default_rng(0)", "np.random.seed(0)"]
    r.shuffle(first)
    cells = [["import random", "random.seed(0)"] + first] + [[_statement(r, funcs) for _ in range(r.randint(2, 7))] for _ in range(r.randint(2, 5))]
    for _ in range(r.randint(1, 3)):
        cell = r.choice(cells[1:])
        cell.insert(r.randint(0, len(cell)), f"RESULT('r', float({_expr(r)}))")
    return "\n" + "\n".join(f"# --- cell {i} ---\n" + "\n".join(c) for i, c in enumerate(cells, 1)) + "\n"


def values(cells: str) -> list:
    """The chain run: the RESULT values it recorded, in order; an error ends the list as ('error', its type)."""
    got = []
    env = {"np": np, "pd": pd, "RESULT": lambda what, value, *a, **k: got.append((what, round(float(value), 9)))}
    with contextlib.redirect_stdout(io.StringIO()):
        try:
            exec(compile(cells, "<chain>", "exec"), env)
        except Exception as exc:                                   # noqa: BLE001
            got.append(("error", type(exc).__name__))
    return got
