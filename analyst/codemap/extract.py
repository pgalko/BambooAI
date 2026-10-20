"""The first stage of the code map (blueprint 4.1-4.5): each committed cell parsed, its top-level statements named for
what they do (a fixed vocabulary of verbs), linked by the names they read and write across cells, the RESULT lines
paired with their calls, the printouts the report cites traced from their print statements, the helpers the chain
defined described from their own code. Pure: a ChainRecord in, statements and results out; no model, no kernel.

Ported from the design package's prototype (2026-10-20); the fixtures under tests/analyst/fixtures/codemap pin it."""
import ast
import builtins
import copy
import os
import re
from collections import defaultdict

from . import vocab as V
from .words import chain_label, CONTEXT_LABEL, PRIMARY_LABEL

BUILTINS = set(dir(builtins))
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}")
SWITCH_NAMES = {"rng", "random_state", "seed", "generator"}        # a helper's parameter that switches its re-draw on
RESULT_NOTE = re.compile(r"^(?:\((?:corrects cells? [\d, ]+|test after turn \d+)\)\s*)+")


def short(s, n=70):
    s = " ".join(str(s).split())
    return s if len(s) <= n else s[:n - 1] + "…"


def dotted(node):
    """'pd.read_csv', 'stats.spearmanr', 'CTX.frame' for a call on a name; None for a method on an expression."""
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        return ".".join([node.id] + parts[::-1])
    return None


def attr_of(func):
    return func.attr if isinstance(func, ast.Attribute) else (func.id if isinstance(func, ast.Name) else None)


def base_name(node):
    while isinstance(node, (ast.Subscript, ast.Attribute, ast.Call)):
        node = node.value if not isinstance(node, ast.Call) else node.func
    return node.id if isinstance(node, ast.Name) else None


def file_label(path):
    """The label a file is known by on the map: its base name without the loaders' window suffix."""
    return re.sub(r"_\d{8}_to_\d{8}", "", os.path.basename(path))


# ---- names a statement reads, binds and mutates (comprehension and lambda scopes respected) --------------------------
class Names(ast.NodeVisitor):
    def __init__(self):
        self.loads, self.stores, self.mutates, self.scopes = set(), set(), set(), [set()]

    def hidden(self, name):
        return any(name in s for s in self.scopes[1:])

    def visit_Name(self, n):
        if self.hidden(n.id):
            return
        (self.loads if isinstance(n.ctx, ast.Load) else self.stores).add(n.id)

    def _comp(self, n, elts):
        local = set()
        for g in n.generators:
            self.visit(g.iter)
            local |= {t.id for t in ast.walk(g.target) if isinstance(t, ast.Name)}
        self.scopes.append(local)
        for g in n.generators:
            for c in g.ifs:
                self.visit(c)
        for e in elts:
            self.visit(e)
        self.scopes.pop()

    def visit_ListComp(self, n): self._comp(n, [n.elt])
    def visit_SetComp(self, n): self._comp(n, [n.elt])
    def visit_GeneratorExp(self, n): self._comp(n, [n.elt])
    def visit_DictComp(self, n): self._comp(n, [n.key, n.value])

    def visit_Lambda(self, n):
        for d in n.args.defaults:
            self.visit(d)
        self.scopes.append({a.arg for a in n.args.args})
        self.visit(n.body)
        self.scopes.pop()

    def visit_FunctionDef(self, n):
        self.stores.add(n.name)
        for d in n.args.defaults:
            self.visit(d)
        inner = Names()
        for s in n.body:
            inner.visit(s)
        params = {a.arg for a in n.args.args} | {a.arg for a in n.args.kwonlyargs}
        self.loads |= {x for x in inner.loads - inner.stores - params if not self.hidden(x)}

    def _store_target(self, n):
        b = base_name(n.value)
        if b and not self.hidden(b):
            self.mutates.add(b)
            self.loads.add(b)

    def visit_Subscript(self, n):
        if isinstance(n.ctx, ast.Store):
            self._store_target(n)
            self.visit(n.slice)
        else:
            self.generic_visit(n)

    def visit_Attribute(self, n):
        if isinstance(n.ctx, ast.Store):
            self._store_target(n)
        else:
            self.generic_visit(n)

    def visit_Call(self, n):
        f = n.func
        if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and not self.hidden(f.value.id):
            if f.attr in V.MUTATORS:
                self.mutates.add(f.value.id)
            if any(k.arg == "inplace" and isinstance(k.value, ast.Constant) and k.value.value is True for k in n.keywords):
                self.mutates.add(f.value.id)
        self.generic_visit(n)


def _names(node):
    nm = Names()
    nm.visit(node)
    return nm


def exposed(node, bound=frozenset()):
    """Names a statement reads before it binds them itself: a loop variable, or a name set earlier in the same block,
    is not a read of an earlier cell's value."""
    bound = set(bound)
    if isinstance(node, (ast.For, ast.AsyncFor)):
        ex = _names(node.iter).loads - bound
        b = bound | {t.id for t in ast.walk(node.target) if isinstance(t, ast.Name)}
        for s in node.body + node.orelse:
            ex |= exposed(s, b)
            b |= _names(s).stores
        return ex
    if isinstance(node, (ast.If, ast.While)):
        ex = _names(node.test).loads - bound
        for block in (node.body, node.orelse):
            b = set(bound)
            for s in block:
                ex |= exposed(s, b)
                b |= _names(s).stores
        return ex
    if isinstance(node, ast.With):
        ex, b = set(), set(bound)
        for it in node.items:
            ex |= _names(it.context_expr).loads - b
            if it.optional_vars is not None:
                b |= {t.id for t in ast.walk(it.optional_vars) if isinstance(t, ast.Name)}
        for s in node.body:
            ex |= exposed(s, b)
            b |= _names(s).stores
        return ex
    if isinstance(node, ast.Try):
        ex, b = set(), set(bound)
        for s in node.body + node.orelse + node.finalbody + [x for h in node.handlers for x in h.body]:
            ex |= exposed(s, b)
            b |= _names(s).stores
        return ex
    return _names(node).loads - bound


# ---- operations in a statement ----------------------------------------------------------------------------------------
class Strip(ast.NodeTransformer):
    """frame.col and frame['col'] -> col, for conditions read on one frame."""
    def __init__(self, base):
        self.base = base

    def visit_Attribute(self, a):
        self.generic_visit(a)
        if isinstance(a.value, ast.Name) and a.value.id == self.base:
            return ast.Name(id=a.attr, ctx=ast.Load())
        return a

    def visit_Subscript(self, s):
        self.generic_visit(s)
        if isinstance(s.value, ast.Name) and s.value.id == self.base and isinstance(s.slice, ast.Constant) and isinstance(s.slice.value, str):
            return ast.Name(id=s.slice.value, ctx=ast.Load())
        return s


def expr_text(n, base=None, width=60):
    try:
        m = Strip(base).visit(copy.deepcopy(n)) if base else n
        return short(ast.unparse(m), width)
    except Exception:                                       # noqa: BLE001
        return "…"


def cond_text(n, base):
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitAnd):
        return f"{cond_text(n.left, base)} and {cond_text(n.right, base)}"
    if isinstance(n, ast.BinOp) and isinstance(n.op, ast.BitOr):
        return f"({cond_text(n.left, base)} or {cond_text(n.right, base)})"
    if isinstance(n, ast.UnaryOp) and isinstance(n.op, ast.Invert):
        return f"not {cond_text(n.operand, base)}"
    if isinstance(n, ast.Compare):
        parts = [expr_text(n.left, base, 40)]
        for op, c in zip(n.ops, n.comparators):
            parts += [V.CMP.get(type(op), "?"), expr_text(c, base, 40)]
        return " ".join(parts)
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
        a, obj = n.func.attr, expr_text(n.func.value, base, 40)
        if a == "isin" and n.args:
            return f"{obj} in {expr_text(n.args[0], base, 40)}"
        if a == "between" and len(n.args) >= 2:
            return f"{obj} between {expr_text(n.args[0], base, 30)} and {expr_text(n.args[1], base, 30)}"
        if a in ("notna", "notnull"):
            return f"{obj} present"
        if a in ("isna", "isnull"):
            return f"{obj} missing"
        if a == "contains" and n.args:
            return f"{obj.removesuffix('.str')} contains {expr_text(n.args[0], None, 30)}"
    return expr_text(n, base)


def is_mask(sl):
    if isinstance(sl, (ast.Compare, ast.BoolOp)):
        return True
    if isinstance(sl, ast.BinOp) and isinstance(sl.op, (ast.BitAnd, ast.BitOr)):
        return True
    if isinstance(sl, ast.UnaryOp) and isinstance(sl.op, ast.Invert):
        return True
    if isinstance(sl, ast.Call) and attr_of(sl.func) in ("isin", "between", "notna", "isna", "notnull", "contains"):
        return True
    if isinstance(sl, ast.Name):        # a mask held in a variable: df[m]
        return None
    return False


def kw(n, name):
    for k in n.keywords:
        if k.arg == name:
            return k.value
    return None


class Ops:
    """Walk an expression in evaluation order and name what it does."""

    def __init__(self, env):
        self.env, self.out, self.choices, self.loads = env, [], [], []
        self.printing = 0

    def emit(self, verb, text, **extra):
        if self.printing and verb != "show":
            extra["shown"] = True
        self.out.append(dict(verb=verb, text=text, **extra))

    def walk(self, n):
        if isinstance(n, ast.Call) and dotted(n.func) in ("print", "display"):
            self.printing += 1
            for a in n.args:
                self.walk(a)
            self.printing -= 1
            return self.emit("show", "print")
        if isinstance(n, (ast.ListComp, ast.GeneratorExp)) and n.generators and isinstance(n.generators[0].iter, ast.Call) \
                and dotted(n.generators[0].iter.func) == "range" and n.generators[0].iter.args:
            return self.repeat(n.generators[0].iter.args[-1], [n.elt])
        if isinstance(n, ast.For) and isinstance(n.iter, ast.Call) and dotted(n.iter.func) == "range" and n.iter.args:
            return self.repeat(n.iter.args[-1], n.body)
        if isinstance(n, (ast.While, ast.For)):
            before = len(self.out)
            for c in ast.iter_child_nodes(n):
                self.walk(c)
            if len(self.out) == before:
                self.emit("compute", "built in a loop")
            return
        if isinstance(n, ast.Call) and dotted(n.func) in ("pd.Series", "pd.DataFrame") and n.args and isinstance(n.args[0], (ast.Name, ast.List, ast.Dict)):
            for a in n.args:
                self.walk(a)
            return self.emit("compute", ("make a table from " + n.args[0].id) if isinstance(n.args[0], ast.Name) else "make a new table")
        if isinstance(n, ast.Call):
            if isinstance(n.func, ast.Attribute):
                self.walk(n.func.value)
            for a in n.args:
                self.walk(a)
            for k in n.keywords:
                self.walk(k.value)
            self.call(n)
        elif isinstance(n, ast.Subscript):
            self.walk(n.value)
            m = is_mask(n.slice)
            base = base_name(n.value)
            if m:
                self.emit("filter", "keep rows where " + cond_text(n.slice, base), on=base)
                self.thresholds(n.slice)
            elif m is None and isinstance(n.slice, ast.Name) and n.slice.id in self.env.get("masks", set()):
                self.emit("filter", f"keep rows where {n.slice.id}", on=base)
            elif isinstance(n.slice, ast.List) and all(isinstance(e, ast.Constant) for e in n.slice.elts):
                self.emit("select", "columns " + ", ".join(str(e.value) for e in n.slice.elts), on=base)
            self.walk(n.slice)
        elif isinstance(n, ast.Lambda):
            self.walk(n.body)
        else:
            for c in ast.iter_child_nodes(n):
                self.walk(c)

    def repeat(self, count, body):
        """A body repeated N times: a bootstrap when what it repeats resamples."""
        before = len(self.out)
        for b in body:
            self.walk(b)
        inner = self.out[before:]
        funcs = self.env["funcs"]
        resamples = any(o["verb"] == "resample" for o in inner) or any(
            o["verb"] == "call" and (funcs.get(o.get("fn"), {}).get("resamples") or (funcs.get(o.get("fn"), {}).get("can_resample") and o.get("seeded")))
            for o in inner)
        n = count.value if isinstance(count, ast.Constant) else expr_text(count, None, 12)
        if resamples:
            ons = [o["on"] for o in inner if o["verb"] == "resample" and o.get("on")]
            self.out[before:] = [o for o in inner if o["verb"] != "resample"]
            self.emit("resample", f"bootstrap, {n} resamples", **({"redraws": ons[0]} if ons else {}))
            if isinstance(count, ast.Constant):
                self.choices.append(dict(kind="resamples", text=f"{n} resamples"))
        elif inner:
            self.emit("compute", f"repeat {n} times")

    def thresholds(self, cond):
        for c in ast.walk(cond):
            if isinstance(c, ast.Compare):
                for comp in [c.left] + list(c.comparators):
                    if isinstance(comp, ast.Constant) and isinstance(comp.value, (int, float)) and not isinstance(comp.value, bool) and comp.value != 0:
                        self.choices.append(dict(kind="threshold", text=cond_text(c, None)))

    def call(self, n):
        full, a = dotted(n.func), attr_of(n.func)
        args = n.args
        if full in ("print", "display") or a in ("to_string",):
            return self.emit("show", "print")
        if isinstance(n.func, ast.Name) and n.func.id in self.env.get("funcs", {}):
            return self.helper_call(n)                 # the chain's own diff() is not pandas' .diff() (2026-10-20)
        if a in V.LOADS:
            path = self.env["resolve"](args[0]) if args else None
            self.loads.append(("file", file_label(path) if path else "a file", path))
            return self.emit("load", "read " + (file_label(path) if path else "a file"), source=file_label(path) if path else None)
        if full and full.startswith("CTX.") and a in V.CTX_CALLS:
            self.loads.append(("context", V.CTX_CALLS[a], None))
            return self.emit("load", f"{V.CTX_CALLS[a]} (CTX.{a})", source=V.CTX_CALLS[a])
        if full == "DS.load":
            self.loads.append(("primary", PRIMARY_LABEL, None))
            return self.emit("load", "primary dataset (DS.load)", source=PRIMARY_LABEL)
        if full == "DS.save" or a in ("to_csv", "to_parquet", "to_excel"):
            return self.emit("save", "save " + (expr_text(args[1], None, 40) if full == "DS.save" and len(args) > 1 else "a file"))
        if full == "RESULT":
            return self.emit("record", "RESULT")
        if full and (full.startswith(V.DRAW_PREFIX)) or a in V.DRAW_M and (full is None or not full.startswith(("pd.", "np."))):
            if a in ("show",) or (full and full.startswith(V.DRAW_PREFIX)) or a in V.DRAW_M:
                return self.emit("draw", a or "figure")
        if full and (full.endswith("default_rng") or full.endswith("random.seed")):
            if args and isinstance(args[0], ast.Constant):
                self.choices.append(dict(kind="seed", text=f"random seed {args[0].value}"))
            return self.emit("setup", "random generator")
        if a == "Timestamp" or a == "to_datetime":
            if args and isinstance(args[0], ast.Constant) and isinstance(args[0].value, str) and DATE_RE.match(args[0].value):
                self.choices.append(dict(kind="typed date", text=f"date {args[0].value} typed"))
                return
        if a in ("Timedelta", "to_timedelta", "DateOffset"):
            k = n.keywords[0] if n.keywords else None
            if k is not None and isinstance(k.value, ast.Constant):
                self.choices.append(dict(kind="offset", text=f"{k.value.value} {k.arg}"))
            elif args and isinstance(args[0], ast.Constant):
                self.choices.append(dict(kind="offset", text=f"{args[0].value} {expr_text(kw(n, 'unit'), None, 10) if kw(n, 'unit') else ''}".strip()))
            return
        if a == "sample" and isinstance(kw(n, "replace"), ast.Constant) and kw(n, "replace").value is True:
            return self.emit("resample", "resample rows with replacement",
                             on=base_name(n.func.value) if isinstance(n.func, ast.Attribute) else None)
        if a in V.RESAMPLE_HINTS and full and full.split(".")[0] in self.env.get("rngs", set()) | {"np"}:
            # rng.choice(x, n) re-draws from x: the helper profile follows x to the parameter whose rows it takes
            return self.emit("resample", "draw random indices", on=base_name(args[0]) if a == "choice" and args and not isinstance(args[0], ast.Constant) else None)
        if a in V.TESTS and (full is None or not full.startswith("pd.")) and a not in ("t", "norm", "sem") or (full and full.split(".")[-1] in V.TESTS and full.split(".")[0] in ("stats", "sm", "smf", "scipy")):
            return self.emit("test", V.TESTS.get(a, a), name=a)
        if a == "join" and ((isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Constant) and isinstance(n.func.value.value, str))
                            or (full or "").startswith("os.path")
                            or (args and isinstance(args[0], (ast.GeneratorExp, ast.ListComp, ast.SetComp)))):
            # '|'.join(...), os.path.join(...): building a string, not joining tables (the args are walked already)
            return
        if a in V.COMBINE_M:
            other = (base_name(args[0]) or expr_text(args[0], None, 30)) if args else ""
            if a == "concat" and args and isinstance(args[0], (ast.List, ast.Tuple)):
                other = ", ".join(base_name(e) or "…" for e in args[0].elts)
            on = kw(n, "on") or kw(n, "left_on")
            how = kw(n, "how")
            txt = f"{a} {other}" + (f" on {expr_text(on, None, 30)}" if on is not None else "") + (f" ({how.value})" if isinstance(how, ast.Constant) else "")
            return self.emit("combine", txt, other=base_name(args[0]) if args else None)
        if a == "map" and args:
            if isinstance(args[0], ast.Dict):
                keys = [k.value for k in args[0].keys if isinstance(k, ast.Constant)]
                self.choices.append(dict(kind="typed mapping", text="mapping " + short(", ".join(f"{k!s}" for k in keys), 50)))
                return self.emit("derive", "recode with a typed mapping")
            if isinstance(args[0], (ast.Name, ast.Attribute, ast.Subscript)) and base_name(args[0]) in self.env.get("data_names", set()):
                return self.emit("combine", f"look up {expr_text(args[0], None, 30)}", other=base_name(args[0]))
            return self.emit("derive", "map values")
        if a in V.RESHAPE_M:
            idx, col, val, agg = kw(n, "index"), kw(n, "columns"), kw(n, "values"), kw(n, "aggfunc")
            det = " × ".join(expr_text(x, None, 25).strip("'") for x in (idx, col) if x is not None)
            vals = expr_text(val, None, 20).strip("'") if isinstance(val, ast.Constant) else ""
            return self.emit("reshape", V.RESHAPE_M[a] + (f" {vals}" if vals else "") + (f" by {det}" if det else "") + (f" ({expr_text(agg, None, 15).strip(chr(39))})" if agg is not None else ""))
        if a in V.SUMMARISE_M and not (full and full.startswith("np.") and a in ("sum", "mean")):
            if a == "groupby":
                by = expr_text(args[0], base_name(n.func.value), 40) if args else expr_text(kw(n, "by"), None, 40)
                return self.emit("summarise", "group by " + re.sub(r"[\[\]']", "", by))
            if a in ("percentile", "quantile") and full and full.startswith("np."):
                return self.emit("summarise", "percentile")
            return self.emit("summarise", V.SUMMARISE_M[a])
        if a in V.FILTER_M:
            sub = kw(n, "subset")
            subtxt = re.sub(r"[\[\]']", "", expr_text(sub, None, 40)) if sub is not None else ""
            txt = ("drop rows missing " + subtxt) if a == "dropna" and subtxt else V.FILTER_M[a] + (f" by {subtxt}" if subtxt else "")
            if a == "query" and args:
                txt = "keep rows where " + expr_text(args[0], None, 50)
            if a in ("nlargest", "nsmallest", "head", "tail") and args:
                txt += f" ({expr_text(args[0], None, 10)})"
            return self.emit("filter", txt, on=base_name(n.func.value) if isinstance(n.func, ast.Attribute) else None)
        if a in V.DERIVE_M:
            return self.emit("derive", V.DERIVE_M[a])
        return self.helper_call(n)

    def helper_call(self, n):
        """A call of a function the chain (or an earlier chain) defined, by its bare name."""
        if isinstance(n.func, ast.Name) and n.func.id in self.env.get("funcs", {}):
            fd = self.env["funcs"][n.func.id]
            params = fd.get("params") or []
            given = lambda v: not (isinstance(v, ast.Constant) and v.value is None)   # noqa: E731
            # what this call passes for each of the helper's parameters, by position or by name
            argmap = {params[i]: base_name(v) for i, v in enumerate(n.args) if i < len(params) and given(v)}
            argmap.update({k.arg: base_name(k.value) for k in n.keywords if k.arg and given(k.value)})
            switches = set(fd.get("guard") or []) | SWITCH_NAMES
            seeded = bool(switches & set(argmap))       # the generator that turns the helper's resampling on
            sargs = [a.value for a in n.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            return self.emit("call", n.func.id, fn=n.func.id, seeded=seeded, args=sargs, argmap=argmap)


# ---- one statement --------------------------------------------------------------------------------------------------
def figure_names(node, env):
    """(bound, drawn): the names this statement binds to a figure or its axes, and the figures it draws on. Drawing on a
    figure changes it, like appending to a list: a call on the figure (add_trace, update_layout, ax.plot), on an axis
    taken from it in a loop (for ax in axes.flat), or a helper of this chain the figure is passed to."""
    figs = set(env["figs"])
    bound = set()

    def makes_figure(v):
        while isinstance(v, ast.Call):
            f = dotted(v.func) or ""
            if f.startswith(V.FIG_MAKERS):
                return True
            if not isinstance(v.func, ast.Attribute):
                return False
            if v.func.attr in V.FIG_PANDAS or (base_name(v.func.value) in figs | bound and v.func.attr not in V.FIG_KEEP):
                return True
            v = v.func.value
        return False

    for x in ast.walk(node):
        if isinstance(x, ast.Assign) and makes_figure(x.value):
            for t in x.targets:
                for e in (t.elts if isinstance(t, ast.Tuple) else [t]):
                    if isinstance(e, ast.Name):
                        bound.add(e.id)
    figs |= bound
    alias = {}
    for x in ast.walk(node):
        if isinstance(x, (ast.For, ast.comprehension)):
            fi = {n.id for n in ast.walk(x.iter) if isinstance(n, ast.Name)} & figs
            if fi:
                for t in ast.walk(x.target):
                    if isinstance(t, ast.Name):
                        alias[t.id] = min(fi)

    def fig_of(name):
        return name if name in figs else alias.get(name)

    drawn = set()
    for x in ast.walk(node):
        if not isinstance(x, ast.Call):
            continue
        f = x.func
        if isinstance(f, ast.Attribute) and f.attr not in V.FIG_KEEP:
            b = fig_of(base_name(f.value))
            if b:
                drawn.add(b)
        if isinstance(f, ast.Name) and f.id in env["funcs"]:
            for a in list(x.args) + [k.value for k in x.keywords]:
                b = fig_of(a.id) if isinstance(a, ast.Name) else None
                if b:
                    drawn.add(b)
    return bound, drawn


def helper_profile(node, env, inner):
    """What a helper of the chain's own does, read from its code: its parameters; the parameter that switches its
    resampling on (if rng is not None: ...); its own steps in order, each marked when only that switch runs it, and,
    for a step that re-draws rows, the parameter whose rows it re-draws (a = g[...], for soil, g in pm.groupby(...));
    and whether the number it returns comes from arithmetic the vocabulary does not name (tot += n * (...);
    return tot / w)."""
    params = [a.arg for a in node.args.args] + [a.arg for a in node.args.kwonlyargs]
    alias = {}
    for x in ast.walk(node):
        if isinstance(x, ast.Assign):
            for t in x.targets:
                if isinstance(t, ast.Tuple) and isinstance(x.value, ast.Tuple) and len(t.elts) == len(x.value.elts):
                    pairs = list(zip(t.elts, x.value.elts))          # ga, gb = g[...], g[...]
                else:
                    pairs = [(e, x.value) for e in (t.elts if isinstance(t, ast.Tuple) else [t])]
                for e, v in pairs:
                    b = base_name(v)
                    if isinstance(e, ast.Name) and b and b != e.id:
                        alias.setdefault(e.id, b)
        if isinstance(x, (ast.For, ast.comprehension)):
            b = base_name(x.iter)
            for e in ast.walk(x.target):
                if isinstance(e, ast.Name) and b and b != e.id:
                    alias.setdefault(e.id, b)

    def to_param(name):
        seen = set()
        while name and name not in params and name in alias and name not in seen:
            seen.add(name)
            name = alias[name]
        return name if name in params else None

    guard, guarded = set(), []
    for iff in [x for x in ast.walk(node) if isinstance(x, ast.If)]:
        sub = Ops(env)
        for b in iff.body + iff.orelse:
            sub.walk(b)
        res = [o for o in sub.out if o["verb"] == "resample"]
        tested = {n.id for n in ast.walk(iff.test) if isinstance(n, ast.Name)} & set(params)
        if res and tested:
            guard |= tested
            guarded += [(o["verb"], o["text"], o.get("on")) for o in res]
    own = []
    for o in inner:
        if o["verb"] in ("show", "setup", "define", "record", "draw", "save"):
            continue
        key = (o["verb"], o["text"], o.get("on"))
        g = key in guarded
        if g:
            guarded.remove(key)
        step = dict(verb=o["verb"], text=o["text"], guarded=g)
        if o["verb"] == "resample":
            step["param"] = to_param(o.get("on") or o.get("redraws"))     # a bootstrap loop inside the helper re-draws `redraws`
        if step not in own:
            own.append(step)
    rets = [x.value for x in ast.walk(node) if isinstance(x, ast.Return) and x.value is not None]
    by_arith = {x.target.id for x in ast.walk(node) if isinstance(x, ast.AugAssign) and isinstance(x.target, ast.Name)}
    by_arith |= {t.id for x in ast.walk(node) if isinstance(x, ast.Assign) and isinstance(x.value, ast.BinOp)
                 for t in x.targets if isinstance(t, ast.Name)}

    def arithmetic(v):
        if isinstance(v, ast.BinOp):
            return True
        if isinstance(v, ast.Name):
            return v.id in by_arith
        if isinstance(v, (ast.Tuple, ast.List)):
            return any(arithmetic(e) for e in v.elts)
        return False
    return dict(params=params, guard=sorted(guard), own=own, untraced=any(arithmetic(r) for r in rets))


def label_prefix(label):
    """The fixed words a RESULT label starts with, before its first filled-in value."""
    if isinstance(label, ast.Constant) and isinstance(label.value, str):
        return label.value
    if isinstance(label, ast.JoinedStr):
        out = ""
        for v in label.values:
            if not isinstance(v, ast.Constant):
                break
            out += str(v.value)
        return out
    if isinstance(label, ast.BinOp) and isinstance(label.left, ast.Constant) and isinstance(label.left.value, str):
        return label.left.value.split("%")[0]
    return ""


def assign_lines(recs, lines):
    """A cell's printed RESULT lines to its RESULT calls, in order (an older run, whose records carry no line). A call in
    a loop prints one line per pass, and each line is its own result: it takes the lines that start with its fixed
    words, leaving one for every later call."""
    out, j = [[] for _ in recs], 0
    for i, r in enumerate(recs):
        later = len(recs) - i - 1
        if j < len(lines):
            out[i].append(lines[j])
            j += 1
        nxt = recs[i + 1]["prefix"] if i + 1 < len(recs) else ""
        while r.get("in_loop") and j < len(lines) and len(lines) - j > later:
            body = RESULT_NOTE.sub("", lines[j])
            pre = r["prefix"].strip()
            if pre and not body.startswith(pre):
                break
            if nxt and len(nxt.strip()) > len(pre) and body.startswith(nxt.strip()):
                break
            out[i].append(lines[j])
            j += 1
    return out


def label_only(node):
    """Names a drawing statement reads only for words on the figure: titles, annotation text, hover text, trace names."""
    lab, dat = set(), set()

    def walk(n, in_label):
        if isinstance(n, ast.JoinedStr):
            in_label = True
        if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load):
            (lab if in_label else dat).add(n.id)
        if isinstance(n, ast.Call):
            f = n.func
            meth = f.attr if isinstance(f, ast.Attribute) else (f.id if isinstance(f, ast.Name) else None)
            walk(f, in_label)
            for i, a in enumerate(n.args):
                walk(a, in_label or meth in V.LABEL_M or (meth == "text" and i == 2) or (meth == "annotate" and i == 0))
            for k in n.keywords:
                walk(k.value, in_label or k.arg in V.LABEL_KW or meth in V.LABEL_M)
            return
        for c in ast.iter_child_nodes(n):
            walk(c, in_label)

    walk(node, False)
    return lab - dat


def analyse(node, env):
    nm = Names()
    nm.visit(node)
    ops = Ops(env)
    st = dict(line=node.lineno, end=getattr(node, "end_lineno", node.lineno), src=ast.get_source_segment(env["code"], node) or "")
    if isinstance(node, (ast.Import, ast.ImportFrom)):
        mods = {(al.asname or al.name).split(".")[0] for al in node.names}
        env["modules"] |= mods
        return dict(st, verbs=[dict(verb="setup", text="import")], reads=set(), writes=set(), mutates=set(), choices=[], loads=[], records=[])
    if isinstance(node, ast.FunctionDef):
        # inside the helper, a parameter named for a generator and a generator it makes itself are random generators
        # too, whatever the chain named outside (a helper defined before `rng = default_rng(...)`, or given `rng` by
        # position); the walk also marks a `can resample` helper by its `if rng is not None` guard (2026-10-20)
        local = {a.arg for a in node.args.args + node.args.kwonlyargs if a.arg in SWITCH_NAMES}
        for x in ast.walk(node):
            if isinstance(x, ast.Assign) and isinstance(x.value, ast.Call) and (dotted(x.value.func) or "").endswith("default_rng"):
                local |= {t.id for t in x.targets if isinstance(t, ast.Name)}
        fenv = dict(env, rngs=set(env.get("rngs", set())) | local) if local else env
        inner = Ops(fenv)
        for s in node.body:
            inner.walk(s)
        # defaults like B=1000 are a choice of the method
        defaults = node.args.defaults
        params = node.args.args[-len(defaults):] if defaults else []
        ch = [dict(kind="resamples" if p.arg.upper() in V.RESAMPLE_PARAMS else "default", text=f"{p.arg}={d.value}")
              for p, d in zip(params, defaults) if isinstance(d, ast.Constant) and not isinstance(d.value, bool)]
        verbs = [o for o in inner.out if o["verb"] in ("test", "resample", "summarise")]
        kinds = sorted({o["text"] for o in verbs if o["verb"] == "test"})
        boot = any(o["verb"] == "resample" for o in inner.out)
        # resampling only under an `if` is a function that can resample, not a bootstrap by itself
        guarded = 0
        for iff in [x for x in ast.walk(node) if isinstance(x, ast.If)]:
            sub = Ops(fenv)
            for b in iff.body + iff.orelse:
                sub.walk(b)
            guarded += sum(1 for o in sub.out if o["verb"] == "resample")
        total = sum(1 for o in inner.out if o["verb"] == "resample")
        conditional = boot and guarded >= total
        label = (", ".join(kinds) + (" with bootstrap" if boot and not conditional else "")) if kinds else ("bootstrap (resamples rows)" if boot and not conditional else "")
        if conditional:
            boot = False
        shape = "estimate" if (boot or kinds) else None
        if not label:
            main = [o for o in inner.out if o["verb"] in ("reshape", "combine", "summarise", "filter", "load")]
            label = main[0]["text"] if main else "a helper"
            shape = "table" if main and main[0]["verb"] in ("reshape", "combine", "filter", "load") or any(o["text"].startswith("group by") for o in main) else None
        ch = [c for c in ch if re.match(r"^\w+=[\d.]+$", c["text"])]
        words = []
        for o in inner.out:
            w = {"filter": "filter", "combine": "join", "reshape": "pivot", "load": "read", "resample": "resample"}.get(o["verb"])
            if o["verb"] == "summarise" and o["text"].startswith("group by"):
                w = "group"
            if o["verb"] == "test":
                w = o["text"]
            if w and w not in words:
                words.append(w)
        if label in ("a helper",) or (not boot and not kinds):
            ws = [w for w in words[:4] if w != "resample"]
            main_ops = [o for o in inner.out if o["verb"] in ("reshape", "combine", "summarise", "filter")]
            label = main_ops[0]["text"] if len(ws) == 1 and main_ops else (", ".join(ws) or "a helper")
            if conditional:
                label += "; can resample"
        env["funcs"][node.name] = dict(label=label, choices=ch + inner.choices, produces=shape, resamples=boot, can_resample=conditional,
                                       **helper_profile(node, fenv, inner.out))
        return dict(st, verbs=[dict(verb="define", text=f"{node.name}(): {label}")], reads=nm.loads, writes={node.name}, mutates=set(),
                    choices=[], loads=inner.loads, records=[], defines=node.name)
    ops.walk(node)
    # derived columns: frame['col'] = ...
    targets = []
    if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    for t in targets:
        for tt in (t.elts if isinstance(t, ast.Tuple) else [t]):
            if isinstance(tt, ast.Subscript) and isinstance(tt.slice, ast.Constant) and isinstance(tt.slice.value, str):
                ops.emit("derive", f"{tt.slice.value} = " + expr_text(node.value, base_name(tt.value), 50), on=base_name(tt.value), column=tt.slice.value)
    if isinstance(node, ast.For) and isinstance(node.iter, (ast.List, ast.Tuple)) and node.iter.elts and all(isinstance(e, ast.Constant) for e in node.iter.elts):
        ops.out = [dict(o, text=o["text"] + f" (for {', '.join(str(e.value) for e in node.iter.elts)[:60]})") if o["verb"] == "derive" else o for o in ops.out]
    # a value typed into a name: race_day = pd.Timestamp('2026-10-07'), cut = 0.5
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        v = node.value
        if isinstance(v, ast.Constant) and isinstance(v.value, (int, float)) and not isinstance(v.value, bool):
            ops.choices.append(dict(kind="typed value", text=f"{node.targets[0].id} = {v.value}"))
        if isinstance(v, ast.Constant) and isinstance(v.value, str):
            env["consts"][node.targets[0].id] = v.value
    # the same values under a new type: P5 = np.asarray(P5, float), x = x.astype(float), xs = list(xs)
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.Call):
        tn, v = node.targets[0].id, node.value
        if (dotted(v.func) in V.CONVERT_F and v.args and isinstance(v.args[0], ast.Name) and v.args[0].id == tn) or \
                (isinstance(v.func, ast.Attribute) and v.func.attr in V.CONVERT_M and isinstance(v.func.value, ast.Name) and v.func.value.id == tn):
            ops.out.append(dict(verb="derive", text="change type"))
    for c in ops.choices:
        c.setdefault("line", node.lineno)
    # RESULT calls: label, and whether a number was typed into it
    records = []
    looped = {id(y) for x in ast.walk(node) if isinstance(x, (ast.For, ast.AsyncFor, ast.While, ast.ListComp, ast.GeneratorExp))
              for y in ast.walk(x) if isinstance(y, ast.Call)}
    for c in ast.walk(node):
        if isinstance(c, ast.Call) and dotted(c.func) == "RESULT":
            label = c.args[0] if c.args else None
            text = label.value if isinstance(label, ast.Constant) else (ast.unparse(label.left) if isinstance(label, ast.BinOp) else (ast.unparse(label) if label is not None else ""))
            text = str(text).strip("'\"")
            corr = kw(c, "corrects")
            test = kw(c, "test")
            records.append(dict(label=short(text, 400), corrects=(corr.value if isinstance(corr, ast.Constant) else None),
                                test=(test.value if isinstance(test, ast.Constant) else None),
                                typed=bool(len(c.args) > 1 and isinstance(c.args[1], ast.Constant)),
                                prefix=label_prefix(label), templated=not isinstance(label, ast.Constant), in_loop=id(c) in looped,
                                lineno=c.lineno, end=getattr(c, "end_lineno", c.lineno)))
    # names used as masks later: m = (...) & (...)
    if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and is_mask(node.value):
        env["masks"].add(node.targets[0].id)
        ops.out.append(dict(verb="filter", text=f"condition {node.targets[0].id}: " + cond_text(node.value, base_name(node.value) if not isinstance(node.value, ast.BinOp) else None)))
    figs, draws = figure_names(node, env)
    env["figs"] = (env["figs"] - nm.stores) | figs
    return dict(st, verbs=ops.out, reads=exposed(node), writes=nm.stores, mutates=nm.mutates | draws, choices=ops.choices, loads=ops.loads,
                records=records, figs=figs, draws=draws, label_only=label_only(node) if figs | draws else set())


# ---- the run ----------------------------------------------------------------------------------------------------------
def ext_label(k):
    """An outside source a statement reads: the kernel's own names, a document, or names an earlier chain left."""
    if k == "primary":
        return PRIMARY_LABEL
    if k == "context":
        return CONTEXT_LABEL
    if k.startswith("document:"):
        return k[len("document:"):]
    return chain_label(k[len("chain:"):])


def resolver(env):
    """File names from string constants, names bound to one, `+`, f-strings and os.path.join over them."""
    def resolve(n):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            return n.value
        if isinstance(n, ast.Name):
            return env["consts"].get(n.id)
        if isinstance(n, ast.BinOp) and isinstance(n.op, ast.Add):
            l, r = resolve(n.left), resolve(n.right)
            return l + r if l is not None and r is not None else None
        if isinstance(n, ast.JoinedStr):
            out = ""
            for v in n.values:
                if isinstance(v, ast.Constant):
                    out += str(v.value)
                else:
                    x = resolve(v.value)
                    if x is None:
                        return None
                    out += x
            return out
        if isinstance(n, ast.Call) and dotted(n.func) in ("os.path.join",):
            parts = [resolve(a) for a in n.args]
            return os.path.join(*parts) if all(p is not None for p in parts) else None
        return None
    return resolve


def build(doc):
    """Statements, lineage, results and inputs for one ChainRecord (blueprint section 3). A cell whose code does not
    parse keeps no statements and is named in `unparsed`; the view marks its row (4.13)."""
    cells = doc["cells"]
    env = dict(modules=set(V.MODULES0), funcs={}, consts={}, masks=set(), rngs=set(), data_names=set(), code="", figs=set())
    # a follow-up chain: the names earlier chains left in the kernel, and their helper functions, as their maps saw them
    earlier = doc.get("earlier") or {}
    e_names = earlier.get("names") or {}
    for f, fd in (earlier.get("funcs") or {}).items():
        env["funcs"][f] = dict(fd)
    env["resolve"] = resolver(env)
    documents = {i["label"] for i in doc.get("inputs", []) if i.get("kind") == "document"}

    stmts, unparsed = [], []
    for c in cells:
        try:
            tree = ast.parse(c["code"])
        except (SyntaxError, ValueError):
            unparsed.append(c["cell"])
            continue
        env["code"] = c["code"]
        for k, node in enumerate(list(tree.body)):
            # rngs named in this statement
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and (dotted(node.value.func) or "").endswith("default_rng"):
                env["rngs"] |= {t.id for t in node.targets if isinstance(t, ast.Name)}
            s = analyse(node, env)
            s["id"] = f"c{c['cell']}.s{k + 1}"
            s["cell"] = c["cell"]
            # names that hold data: written by a statement that loads, filters, combines, summarises or derives
            if any(o["verb"] in ("load", "filter", "combine", "summarise", "reshape", "derive", "select") for o in s["verbs"]):
                env["data_names"] |= s["writes"] | s["mutates"]
            stmts.append(s)

    # ---- lineage: each statement depends on the latest writer of every name it reads -------------------------------
    last = {}
    for s in stmts:
        deps, ext, taken, ext_data = set(), set(), set(), set()
        lab = s.get("label_only") or set()
        # a name the statement binds itself and then changes (cnt = zeros(...); cnt[c] += 1) is not an earlier value
        for name in sorted(s["reads"] | (s["mutates"] - s["writes"])):
            if name in env["modules"] or name in BUILTINS and name not in last:
                continue
            if name in last:
                deps.add(last[name])
            elif name in V.KERNEL:
                ext.add(V.KERNEL[name])
                if name not in lab:
                    ext_data.add(V.KERNEL[name])
            elif name in documents or (re.match(V.DOCUMENT_RE, name) and name not in last):
                ext.add("document:" + name)             # a document attached to the thread, read in the kernel as D1, D2, ... (2026-10-20)
                if name not in lab:
                    ext_data.add("document:" + name)
            elif name in e_names:
                ext.add(f"chain:{e_names[name]['chain_id']}")
                taken.add(name)
                if name not in lab:
                    ext_data.add(f"chain:{e_names[name]['chain_id']}")
        s["deps"], s["kernel"], s["taken"] = sorted(deps), sorted(ext), sorted(taken)
        s["kernel_data"] = sorted(ext_data)              # without names read only for a figure's words
        for name in s["writes"] | s["mutates"]:
            last[name] = s["id"]
        s["calls"] = sorted({o["fn"] for o in s["verbs"] if o["verb"] == "call"})

    by_id = {s["id"]: s for s in stmts}

    def closure(sid):
        seen, todo = set(), [sid]
        while todo:
            x = todo.pop()
            if x in seen:
                continue
            seen.add(x)
            todo.extend(by_id[x]["deps"])
        return seen

    # ---- results: one per RESULT call, with its printed line from the cell's output ---------------------------------
    printed = {}
    for c in cells:
        printed[c["cell"]] = [ln[len("RESULT: "):] for ln in (c.get("output") or "").splitlines() if ln.startswith("RESULT: ")]

    def trace(sids):
        """Everything behind some statements: the statements, the sources, the operations, the choices."""
        cl = set()
        for sid in sids:
            cl |= closure(sid)
        members = sorted(cl, key=lambda x: (by_id[x]["cell"], int(x.split(".s")[1])))
        srcs, ops, chs, fns = [], [], [], set()
        for m in members:
            st = by_id[m]
            for l in st["loads"]:
                if l[1] not in [x[1] for x in srcs]:
                    srcs.append(l)
            for kname in st["kernel"]:
                lab = ext_label(kname)
                if lab not in [x[1] for x in srcs]:
                    srcs.append((kname, lab, None))
            for o in st["verbs"]:
                if o["verb"] not in ("show", "setup"):
                    ops.append(dict(cell=st["cell"], stmt=m, **{k: v for k, v in o.items() if k in ("verb", "text")}))
            chs += [dict(c, cell=st["cell"]) for c in st["choices"]]
            fns |= set(st["calls"])
        for f in sorted(fns):
            fd = env["funcs"].get(f)
            if fd:
                chs += [dict(c, cell=None, fn=f) for c in fd["choices"]]
        return dict(cells=sorted({by_id[m]["cell"] for m in members}), sources=[dict(kind=x[0], label=x[1]) for x in srcs],
                    ops=ops, choices=chs, methods=sorted(fns), closure=members)

    results, recs_by_cell = [], defaultdict(list)
    for s in stmts:
        recs_by_cell[s["cell"]] += s["records"]
    lines_of, kernel_of, orphans, unpaired = {}, {}, defaultdict(list), defaultdict(list)
    for c in cells:
        cell, recs = c["cell"], recs_by_cell.get(c["cell"], [])
        kept = c.get("results") or []
        if kept and all(isinstance(k.get("line"), int) for k in kept):
            # the kernel's own records (2026-10-20): each RESULT line with the cell line its call ran from, so a line goes
            # to the call that spans it, in a loop or not; a line from a call inside a helper goes to the statement that
            # called the helper. A call with no record did not run
            for r in recs:
                lines_of[id(r)], kernel_of[id(r)] = [], []
            for k in kept:
                r = next((r for r in recs if r["lineno"] <= k["line"] <= r["end"]), None)
                if r is not None:
                    lines_of[id(r)].append(k.get("text") or "")
                    kernel_of[id(r)].append(k)
                    continue
                st = next((x for x in stmts if x["cell"] == cell and x["line"] <= k["line"] <= x["end"]), None)
                if st is not None:
                    orphans[st["id"]].append(k)
                else:
                    unpaired[cell].append(k)                   # a record no statement spans: the self-check names it (4.13)
        elif recs:                                     # an older run: printed lines to calls by order and fixed words
            for r, ls in zip(recs, assign_lines(recs, printed.get(cell, []))):
                lines_of[id(r)] = ls or [""]
        elif kept:
            unpaired[cell].extend(kept)                # records without a RESULT call in the code (a call the parse lost)

    def add_result(s, line, label, templated, corrects, test, typed):
        status = "not computed" if re.search(r":\s*\+?nan\b", line) else "recorded"
        if templated and line:                         # a label with filled-in values: as the line printed it
            mm = re.match(r"^(.*?): [+\-−]?(?:[\d.,]+|nan)\b", RESULT_NOTE.sub("", line))
            if mm:
                label = mm.group(1)
        results.append(dict(id=f"r{len(results) + 1}", kind="result", cell=s["cell"], stmt=s["id"], stmts=[s["id"]], label=label, line=line,
                            corrects=corrects, test=test, typed=typed, status=status, **trace([s["id"]])))

    for s in stmts:
        for r in s["records"]:
            ks = kernel_of.get(id(r)) or []
            for j, line in enumerate(lines_of.get(id(r)) or []):
                k = ks[j] if j < len(ks) else None      # what the kernel recorded wins over what the code says
                add_result(s, line, r["label"], r["templated"], k.get("corrects") if k else r["corrects"],
                           k.get("test") if k else r["test"], k.get("typed") if k else r["typed"])
        for k in orphans.get(s["id"], []):            # RESULT called inside a helper of the chain's own
            add_result(s, k.get("text") or "", k.get("text") or "", True, k.get("corrects"), k.get("test"), k.get("typed"))
    # ---- printouts the report cites, from cells that record no RESULT line: traced back from their print statements,
    # so every number the report relies on has a recipe
    cited = sorted({int(x) for x in re.findall(r"\[cell (\d+)\]", doc.get("report") or "")})
    with_result = {r["cell"] for r in results}
    out_of = {c["cell"]: (c.get("output") or "") for c in cells}
    for n in cited:
        if n in with_result or n not in out_of:
            continue
        prints = [s for s in stmts if s["cell"] == n and any(o["verb"] == "show" for o in s["verbs"])]
        if not prints:
            continue
        lines = [ln.rstrip() for ln in out_of[n].splitlines() if ln.strip()]
        results.append(dict(id=f"p{n}", kind="printed", cell=n, stmt=prints[-1]["id"], stmts=[s["id"] for s in prints],
                            label=f"printed in cell {n}", line=lines[0].strip() if lines else "", lines=lines[:3],
                            corrects=None, test=None, typed=False, status="printed", **trace([s["id"] for s in prints])))
    # corrected: a later RESULT with corrects=n replaces cell n's lines
    corrected_cells = set()                            # corrects is a cell, or a list of cells
    for r in results:
        cs = r["corrects"]
        corrected_cells |= set(cs) if isinstance(cs, (list, tuple)) else ({cs} if cs else set())
    for r in results:
        if r["cell"] in corrected_cells:
            r["status"] = "corrected" if r["status"] != "not computed" else r["status"]

    # ---- figures, dead ends, unused inputs --------------------------------------------------------------------------
    fig_cells = [c["cell"] for c in cells if c.get("kind") == "figures"]
    feeds = set()
    for r in results:
        if r["kind"] == "result":                      # what feeds a RESULT line or a figure; printouts do not count here
            feeds |= set(r["closure"])
    for s in stmts:
        if s["cell"] in fig_cells and any(o["verb"] == "draw" for o in s["verbs"]):
            feeds |= closure(s["id"])
    for s in stmts:
        s["feeds"] = s["id"] in feeds
    used_files = {l[1] for s in stmts if s["id"] in feeds for l in s["loads"]}
    used_kernel = {k for s in stmts if s["id"] in feeds for k in s["kernel"]}
    inputs = []
    for i in doc.get("inputs", []):
        lab = i["label"]
        used = (lab in used_files) or (i["kind"] == "primary" and ("primary" in used_kernel or PRIMARY_LABEL in used_files)) \
            or (i["kind"] == "context" and ("context" in used_kernel or any(x.startswith("context") for x in used_files))) \
            or (i["kind"] == "document" and ("document:" + lab) in used_kernel)
        inputs.append(dict(i, used=used))
    return dict(statements=stmts, results=results, functions=env["funcs"], inputs=inputs, figure_cells=fig_cells,
                unparsed=unparsed, unpaired={k: len(v) for k, v in unpaired.items()})
