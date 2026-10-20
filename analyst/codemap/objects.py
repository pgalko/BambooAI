"""The second stage of the code map (blueprint 4.6, 4.10): from statements to the objects a reader sees - the named
tables and values the code built, one per (names, cell), with what each was made from, its kind, its steps in plain
words, its size from the kernel's registry; the results with the objects behind them; the cells with their roles; the
inputs, offered or used, with the columns used; the choices typed into the code; and what the chain leaves for later
chains (exports). Pure, no model, no kernel.

Ported from the design package's prototype (2026-10-20); the fixtures under tests/analyst/fixtures/codemap pin it."""
import ast
import re
from collections import OrderedDict, defaultdict

from ..notebook import step_sentence                       # the app's own "what this cell was for"
from . import extract as X
from . import vocab as V
from .words import CONTEXT_LABEL, UNTRACED, chain_label, status_via


def tokens(src):
    try:
        t = ast.parse(src)
    except (SyntaxError, ValueError):
        return set()
    out = set()
    for n in ast.walk(t):
        if isinstance(n, ast.Constant) and isinstance(n.value, str):
            out.add(n.value)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
        elif isinstance(n, ast.keyword) and n.arg:
            out.add(n.arg)
    return out


# ---- typed values, evaluated without the data (the prototype used exec over a whitelist; this walks the tree) ---------
class _Unsafe(Exception):
    pass


_BIN = {ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b, ast.Mult: lambda a, b: a * b, ast.Div: lambda a, b: a / b,
        ast.FloorDiv: lambda a, b: a // b, ast.Mod: lambda a, b: a % b, ast.Pow: lambda a, b: a ** b,
        ast.BitOr: lambda a, b: a | b, ast.BitAnd: lambda a, b: a & b, ast.BitXor: lambda a, b: a ^ b}   # set algebra on column sets
_BUILTIN = {"int": int, "float": float, "str": str, "round": round}


def _safe_lib():
    import numpy as np
    import pandas as pd
    return {"pd": pd, "np": np}


def _eval(node, known, lib):
    """A value from typed constants, known names, date arithmetic and the safe calls; _Unsafe for anything else."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in known:
            return known[node.id]
        if node.id in _BUILTIN:
            return _BUILTIN[node.id]
        if node.id in lib:
            return lib[node.id]
        raise _Unsafe(node.id)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        vals = [_eval(e, known, lib) for e in node.elts]
        return list(vals) if isinstance(node, ast.List) else (tuple(vals) if isinstance(node, ast.Tuple) else set(vals))
    if isinstance(node, ast.Dict):
        return {_eval(k, known, lib): _eval(v, known, lib) for k, v in zip(node.keys, node.values) if k is not None}
    if isinstance(node, ast.JoinedStr):
        out = ""
        for v in node.values:
            out += str(v.value) if isinstance(v, ast.Constant) else format(_eval(v.value, known, lib), "")
        return out
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _eval(node.operand, known, lib)
        return -v if isinstance(node.op, ast.USub) else +v
    if isinstance(node, ast.BinOp) and type(node.op) in _BIN:
        return _BIN[type(node.op)](_eval(node.left, known, lib), _eval(node.right, known, lib))
    if isinstance(node, ast.Attribute):
        base = _eval(node.value, known, lib)
        if node.attr.startswith("_"):
            raise _Unsafe(node.attr)
        return getattr(base, node.attr)
    if isinstance(node, ast.Subscript):
        return _eval(node.value, known, lib)[_eval(node.slice, known, lib)]
    if isinstance(node, ast.Slice):
        return slice(*(None if x is None else _eval(x, known, lib) for x in (node.lower, node.upper, node.step)))
    if isinstance(node, ast.Call):
        f = X.dotted(node.func)
        if f in V.SAFE_CALLS or (isinstance(node.func, ast.Attribute) and node.func.attr == "normalize"):
            fn = _eval(node.func, known, lib)
            args = [_eval(a, known, lib) for a in node.args]
            kwargs = {k.arg: _eval(k.value, known, lib) for k in node.keywords if k.arg}
            return fn(*args, **kwargs)
        raise _Unsafe(f)
    raise _Unsafe(type(node).__name__)


def safe_value(stmt, known):
    """Evaluate a parameter's assignment when it uses only typed values, other known parameters and date arithmetic."""
    try:
        node = ast.parse(stmt["src"]).body[0]
    except (SyntaxError, ValueError, IndexError):
        return None
    if not isinstance(node, ast.Assign) or not all(isinstance(t, ast.Name) for t in node.targets):
        return None
    for c in ast.walk(node.value):
        if isinstance(c, ast.Call):
            f = X.dotted(c.func)
            if f not in V.SAFE_CALLS and not (isinstance(c.func, ast.Attribute) and c.func.attr in ("normalize",)):
                return None
        if isinstance(c, ast.Name) and c.id not in known and c.id not in ("pd", "np", "int", "float", "str", "round"):
            return None
    try:
        v = _eval(node.value, known, _safe_lib())
    except Exception:                                       # noqa: BLE001 - anything the tree walk cannot value
        return None
    return {t.id: v for t in node.targets}


def is_scalar(v):
    import pandas as pd
    return isinstance(v, (pd.Timestamp, pd.Timedelta, int, float)) and not isinstance(v, bool)


def is_pattern(v):
    """A typed word list or pattern: what a keyword search or a code filter counts."""
    if isinstance(v, str):
        return bool(re.search(r"[|\\]", v))
    if isinstance(v, dict):
        return any(is_pattern(x) for x in v.values())
    if isinstance(v, (list, set, tuple)):
        return len(v) > 0 and all(isinstance(x, str) for x in v)
    return False


def is_column_list(v, columns):
    return isinstance(v, (list, set, tuple)) and len(v) > 0 and all(isinstance(x, str) and x in columns for x in v)


def fmt_value(v):
    import pandas as pd
    if isinstance(v, pd.Timestamp):
        return v.strftime("%Y-%m-%d") if v == v.normalize() else str(v)
    if isinstance(v, pd.Timedelta):
        return f"{v.days} days" if v.seconds == 0 else str(v)
    if isinstance(v, (set, frozenset)):                # sorted, so the same chain always prints the same map
        return "{" + ", ".join(repr(x) for x in sorted(v, key=str)) + "}"
    return repr(v)


def exports(m, chain_id):
    """What a chain leaves for later chains in the thread: every name alive in the kernel at its end, with the cell that
    last wrote it and the inputs it was made from; and its helper functions. Built from the chain's stored map."""
    objs = {o["id"]: o for o in m["objects"]}
    latest = {}
    for o in sorted(m["objects"], key=lambda o: o["order"]):
        for n in o["names"]:
            latest[n] = o
    memo = {}

    def roots(oid, seen=()):
        if oid in memo:
            return memo[oid]
        if oid in seen or oid not in objs:
            return set()
        o = objs[oid]
        out = set(o["inputs"])
        for p in o["parents"]:
            out |= roots(p, seen + (oid,))
        memo[oid] = out
        return out
    names = {n: dict(chain_id=str(chain_id), cell=o["cell"], kind=o["kind"], roots=sorted(roots(o["id"]))) for n, o in latest.items()}
    return dict(names=names, funcs=m.get("functions") or {})


def build_map(doc):
    base = X.build(doc)
    e_names = (doc.get("earlier") or {}).get("names") or {}
    stmts, funcs = base["statements"], base["functions"]
    by = {s["id"]: s for s in stmts}
    cells = {c["cell"]: c for c in doc["cells"]}
    # the kernel's registry as the chain kept it: per cell, the names that cell made or changed; a name's description at
    # cell n is its latest entry at or before n, starting from what the kernel held when the chain began
    regs, held = {}, dict(doc.get("registry_start") or {})
    for c in doc["cells"]:
        held.update(c.get("registry") or {})
        regs[c["cell"]] = dict(held)

    # ---- objects --------------------------------------------------------------------------------------------------
    objects, current, order = OrderedDict(), {}, 0
    loopvars = defaultdict(set)
    for s in stmts:
        try:
            node = ast.parse(s["src"]).body[0]
        except Exception:                                   # noqa: BLE001
            node = None
        if isinstance(node, (ast.For, ast.AsyncFor)):
            loopvars[s["id"]] = {t.id for t in ast.walk(node.target) if isinstance(t, ast.Name)}
        group = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Tuple):
            group = [e.id for e in node.targets[0].elts if isinstance(e, ast.Name)]
        outs = (set(s["writes"]) | set(s["mutates"])) - loopvars[s["id"]] - V.MODULES0
        if not outs:
            continue
        figs = (set(s.get("figs", ())) | set(s.get("draws", ()))) & outs
        if isinstance(node, (ast.For, ast.AsyncFor, ast.While, ast.If, ast.With, ast.Try)) and len(outs) > 1:
            rest = sorted(outs - figs)                 # what a loop or a block makes is one thing on the map;
            groups = ([rest] if rest else []) + [[f] for f in sorted(figs)]   # a figure it draws on stays the figure
        else:
            groups = [group] if group and set(group) == outs else [[o] for o in sorted(outs)]
        oids = []
        for g in groups:
            oid = f"{', '.join(g)}@{s['cell']}"
            cur = current.get(g[0])
            if len(g) == 1 and g[0] in figs and g[0] not in s["writes"] and cur in objects and objects[cur]["cell"] == s["cell"]:
                oid = cur                              # drawing on axes of fig, ax = plt.subplots() in the same cell
            oids.append(oid)
            if oid not in objects:
                order += 1
                objects[oid] = dict(id=oid, name=", ".join(g), names=g, cell=s["cell"], stmts=[], parents=set(), inputs=set(),
                                    ops=[], choices=[], order=order, function=s.get("defines"), via={}, taken=set())
            o = objects[oid]
            o["stmts"].append(s["id"])
            fig_g = bool(set(g) & figs)
            if fig_g:
                o["drawn"] = True
            # a figure is made from the data it draws; a number quoted in its title or an annotation has its own recipe
            lab = set(s.get("label_only") or ()) if fig_g else set()
            for n in sorted((set(s["reads"]) - lab) | (set(s["mutates"]) & set(g))):
                p = current.get(n)
                if p and p != oid:
                    o["parents"].add(p)
            for l in s["loads"]:
                o["inputs"].add(V.CTX_FILE.get(l[1], l[1]))
            for k in (s.get("kernel_data", s["kernel"]) if fig_g else s["kernel"]):
                o["inputs"].add(X.ext_label(k))
            for n in [t for t in s.get("taken", []) if t not in lab]:   # a name an earlier chain made: the inputs it was made from
                o["taken"].add(n)
                for lab_ in e_names[n].get("roots", []):
                    o["via"].setdefault(lab_, e_names[n]["chain_id"])
            o["ops"] += [op for op in s["verbs"] if op["verb"] not in ("show", "setup") and not op.get("shown")
                         and not (op["verb"] == "draw" and figs and not set(g) & figs)]   # the drawing is the figure's
            o["choices"] += [dict(c, cell=s["cell"]) for c in s["choices"]]
        for g, oid in zip(groups, oids):
            for n in g:
                current[n] = oid
    # every statement's object (for result traces)
    stmt_obj = defaultdict(set)
    for oid, o in objects.items():
        for sid in o["stmts"]:
            stmt_obj[sid].add(oid)

    # parameter values: typed dates and their arithmetic, evaluated without the data
    known = {}
    for s in stmts:
        v = safe_value(s, known)
        if v:
            known.update(v)
    all_columns = {c for i in doc.get("inputs", []) for c in (i.get("columns") or [])}
    # kinds and shapes
    for oid, o in objects.items():
        reg = None
        for n in o["names"]:
            r = regs.get(o["cell"], {}).get(n)
            if r:
                reg = r
        o["shape"] = reg["desc"] if reg else None
        verbs = {op["verb"] for op in o["ops"]}
        typ = (reg or {}).get("type", "")
        if o["function"] or typ == "function":
            o["kind"] = "function"
        elif o.get("drawn") or typ in ("Figure",):           # bound to a figure, or drawn on
            o["kind"] = "figure"
        elif "compute" in verbs and not o["parents"] and not o["inputs"]:
            o["kind"] = "table"
        elif typ in ("Figure",) or "draw" in verbs and not verbs & {"load", "filter", "combine"}:
            o["kind"] = "figure"
        elif typ in ("float", "float64", "int", "int64", "float32", "ndarray", "tuple") and (o["parents"] or o["inputs"]):
            o["kind"] = "estimate" if (verbs & {"test", "resample"} or any(op["verb"] == "call" for op in o["ops"]) or any(objects[p]["kind"] == "estimate" for p in o["parents"] if p in objects and "kind" in objects[p])) else "value"
        elif typ in ("DataFrame", "Series") or verbs & {"load", "filter", "select", "combine", "reshape"} or any(op.get("column") for op in o["ops"]) or ("summarise" in verbs and any(op["text"].startswith("group by") for op in o["ops"])):
            o["kind"] = "table"
        elif any(objects[p].get("kind") == "estimate" for p in o["parents"] if p in objects) and not verbs & {"load", "filter", "combine", "reshape"}:
            o["kind"] = "estimate"
        elif verbs & {"test", "resample"} or any(op["verb"] == "call" and "bootstrap" in funcs.get(op["text"], {}).get("label", "") or op["verb"] == "call" and any(w in funcs.get(op["text"], {}).get("label", "") for w in ("test", "correlation", "regression")) for op in o["ops"]):
            o["kind"] = "estimate"
        elif any(op["verb"] == "call" and funcs.get(op["text"], {}).get("produces") == "table" for op in o["ops"]):
            o["kind"] = "table"
        elif all(n in known for n in o["names"]) and all(is_scalar(known[n]) for n in o["names"]):
            o["kind"] = "param"
            o["value"] = ", ".join(fmt_value(known[n]) for n in o["names"])
        elif all(n in known for n in o["names"]) and any(is_pattern(known[n]) and not is_column_list(known[n], all_columns) for n in o["names"]):
            o["kind"] = "pattern"
            o["value"] = ", ".join(fmt_value(known[n]) for n in o["names"])
        elif typ in ("list", "set", "dict", "tuple", "Generator") or not o["parents"] and not o["inputs"]:
            o["kind"] = "helper"
        else:
            o["kind"] = "value"
        if o["kind"] != "param" and all(n in known for n in o["names"]):
            o["value"] = ", ".join(fmt_value(known[n]) for n in o["names"])
        o["typed"] = any(c["kind"] in ("typed date", "typed value") for c in o["choices"])
    for o in objects.values():
        o["steps"] = plain_steps(o, funcs, all_columns)
        o.pop("_new", None)

    # ---- results ----------------------------------------------------------------------------------------------------
    results = []
    for r in base["results"]:
        objs = set()
        for sid in r["closure"]:
            objs |= stmt_obj.get(sid, set())
        # the result's direct parents: objects read by the RESULT statement (a printout: by its print statements)
        direct, direct_inputs = set(), []
        for sid in r.get("stmts") or [r["stmt"]]:
            st = by[sid]
            direct |= {current_at(objects, n, st) for n in st["reads"]} - {None}
            for lab in [V.CTX_FILE.get(l[1], l[1]) for l in st["loads"]] + [X.ext_label(k) for k in st["kernel"]]:
                if lab not in direct_inputs:
                    direct_inputs.append(lab)              # read by the RESULT (or print) itself, not through a table
        chain = sorted(objs, key=lambda x: objects[x]["order"])
        params = [x for x in chain if objects[x]["kind"] == "param"]
        rec = dict(r, objects=chain, direct=sorted(direct), direct_inputs=direct_inputs, params=[dict(name=objects[p]["name"], value=objects[p].get("value"),
                                                                         typed=objects[p]["typed"], cell=objects[p]["cell"]) for p in params])
        rec.pop("ops", None); rec.pop("closure", None)
        # number and interval from the printed line
        m = re.search(r":\s*([+\-−]?[\d.,]+|[+\-]?nan)(?:\s*\(95% CI ([^)]*)\))?\s*(.*)$", r["line"] or "") if r["kind"] == "result" else None
        rec["estimate"], rec["interval"], rec["unit_dir"] = (m.group(1), m.group(2), m.group(3)) if m else ("", "", "")
        results.append(rec)
    corrected_by = {}
    for r in results:
        if r["kind"] == "result" and r["corrects"]:
            for c in (r["corrects"] if isinstance(r["corrects"], (list, tuple)) else [r["corrects"]]):
                corrected_by.setdefault(c, r["cell"])
    for r in results:
        if r["status"] == "corrected":
            r["corrected_by"] = corrected_by.get(r["cell"])

    # ---- cells ------------------------------------------------------------------------------------------------------
    report = doc.get("report") or ""
    cited = set(int(x) for x in re.findall(r"\[cell (\d+)\]", report))
    cited_fig = set(int(x) for x in re.findall(r"\[fig (\d+)\]", report))
    feeding = {s["cell"] for s in stmts if s["feeds"]}
    out_cells = []
    for n, c in cells.items():
        cs = [s for s in stmts if s["cell"] == n]
        verbs = []
        printed = []
        for s in cs:
            for op in s["verbs"]:
                if op.get("shown"):
                    if op["verb"] in ("summarise", "reshape", "test", "combine") and op["text"] not in printed:
                        printed.append(op["text"])
                    continue
                if op["verb"] not in ("show", "setup", "define") and op["text"] not in V.TIDY:
                    verbs.append(op["verb"])
        res = [r["id"] for r in results if r["cell"] == n and r["kind"] == "result"]
        printout = next((r["id"] for r in results if r["cell"] == n and r["kind"] == "printed"), None)
        carries_to_later = any(objects[p]["cell"] == n for o in objects.values() if o["cell"] != n for p in o["parents"])
        if c.get("kind") == "figures":
            role = "figures"
        elif res:
            role = "results"
        elif n in feeding and carries_to_later:
            role = "carries"
        elif n in cited:
            role = "evidence"
        else:
            role = "printed"
        reads_from = sorted({objects[p]["cell"] for o in objects.values() if o["cell"] == n for p in o["parents"] if objects[p]["cell"] != n})
        direct_inputs = set()
        for s_ in cs:
            for l in s_["loads"]:
                direct_inputs.add(V.CTX_FILE.get(l[1], l[1]))
            for k in s_["kernel"]:
                direct_inputs.add(X.ext_label(k))
        taken = defaultdict(set)
        for s_ in cs:
            for nm in s_.get("taken", []):
                taken[e_names[nm]["chain_id"]].add(nm)
        out_cells.append(dict(cell=n, turn=c.get("turn"), kind=c.get("kind"), role=role, cited=n in cited or n in cited_fig, why=c.get("step", ""),
                              purpose=step_sentence(c.get("step", ""), 140) if c.get("kind") != "figures" else c.get("step", ""),
                              verbs=sorted(set(verbs), key=verbs.index), objects=[oid for oid, o in objects.items() if o["cell"] == n and o["kind"] in ("table", "estimate")],
                              results=res, printout=printout, reads_from=reads_from, lines=len(c["code"].splitlines()), printed=printed[:6], direct_inputs=sorted(direct_inputs),
                              inputs=sorted({i for o in objects.values() if o["cell"] == n for i in o["inputs"]}),
                              taken=[dict(chain=k, names=sorted(v), cells=sorted({e_names[x]["cell"] for x in v})) for k, v in sorted(taken.items())],
                              via=sorted({lab for o in objects.values() if o["cell"] == n for lab in o["via"]}),
                              mapped=n not in base["unparsed"]))

    # ---- inputs: used, by which cells, which columns -------------------------------------------------------------------
    roots = {}

    def root_inputs(oid, seen=None):
        if oid in roots:
            return roots[oid]
        seen = seen or set()
        if oid in seen:
            return set()
        seen.add(oid)
        o = objects[oid]
        out = set(o["inputs"])
        for p in o["parents"]:
            out |= root_inputs(p, seen)
        roots[oid] = out
        return out
    toks_by_input = defaultdict(set)
    for oid, o in objects.items():
        ri = root_inputs(oid)
        tk = set()
        for sid in o["stmts"]:
            tk |= tokens(by[sid]["src"])
        for i in ri:
            toks_by_input[i] |= tk
    used_in, loaded_in = defaultdict(set), defaultdict(set)
    traced = set()
    for r in results:
        traced |= set(r["objects"])
    cited_cells = set(int(x) for x in re.findall(r"\[(?:cell|fig) (\d+)\]", report))
    fig_cells = {c["cell"] for c in doc["cells"] if c.get("kind") == "figures"}

    def upstream(oid, seen):
        if oid in seen:
            return
        seen.add(oid)
        for p in objects[oid]["parents"]:
            upstream(p, seen)
    for oid, o in objects.items():
        if o["cell"] in cited_cells or o["cell"] in fig_cells:
            upstream(oid, traced)
    for oid, o in objects.items():
        for i in o["inputs"]:
            loaded_in[i].add(o["cell"])
            if oid in traced:
                used_in[i].add(o["cell"])
    # an input a RESULT or print statement reads itself, with no object in between (RESULT(f"... {df[...].mean()}")):
    # loaded in that cell, used when the statement feeds a result or a cited printout, its columns counted (2026-10-20;
    # the prototype said "offered, never read" of such an input)
    printing = {sid for r in results if r["kind"] == "printed" for sid in r["stmts"]}
    for s_ in stmts:
        if not s_["records"] and not any(o["verb"] == "show" for o in s_["verbs"]):
            continue
        labs = {V.CTX_FILE.get(l[1], l[1]) for l in s_["loads"]} | {X.ext_label(k) for k in s_["kernel_data"]}
        for lab in labs:
            loaded_in[lab].add(s_["cell"])
            if s_["feeds"] or s_["id"] in printing:
                used_in[lab].add(s_["cell"])
            toks_by_input[lab] |= tokens(s_["src"])
    # what this chain took from earlier chains: one input per earlier chain, first, since a follow-up starts from it;
    # an input the chain reached only through those names counts as used through that chain
    via_used = {}
    for oid in traced:
        for lab, k in objects[oid]["via"].items():
            via_used.setdefault(lab, k)
    inputs = []
    taken_by = defaultdict(set)
    for o in objects.values():
        for nm in o["taken"]:
            taken_by[e_names[nm]["chain_id"]].add(nm)
    for s_ in stmts:
        for nm in s_.get("taken", []):
            taken_by[e_names[nm]["chain_id"]].add(nm)
    for k, names in sorted(taken_by.items()):
        lab = chain_label(k)
        inputs.append(dict(label=lab, kind="chain", chain=k, detail="", columns=0, used_columns=[], names=sorted(names),
                           from_cells=sorted({e_names[x]["cell"] for x in names}),
                           cells=sorted(used_in.get(lab, set())), loaded=sorted(loaded_in.get(lab, set())),
                           used=bool(used_in.get(lab)), status="used" if used_in.get(lab) else ("loaded, not used" if loaded_in.get(lab) else "not used")))
    for i in doc.get("inputs", []):
        lab = i["label"]
        if lab == CONTEXT_LABEL:
            continue
        cols = i.get("columns") or []
        used_cols = [c for c in cols if c in toks_by_input.get(lab, set())]
        status = "used" if used_in.get(lab) else (status_via(via_used[lab]) if lab in via_used else ("loaded, not used" if loaded_in.get(lab) else "not used"))
        inputs.append(dict(label=lab, kind=i["kind"], detail=i.get("detail", ""), columns=len(cols), used_columns=used_cols, all_columns=list(cols),
                           cells=sorted(used_in.get(lab, set())), loaded=sorted(loaded_in.get(lab, set())), through=via_used.get(lab) if not used_in.get(lab) else None,
                           used=bool(used_in.get(lab)) or lab in via_used, status=status))

    # ---- choices behind the results ---------------------------------------------------------------------------------------
    choices = []
    seen = set()
    for r in results:
        for c in r["choices"]:
            key = (c.get("text"), c.get("cell"))
            if key in seen:
                continue
            seen.add(key)
            choices.append(dict(c, results=[x["id"] for x in results if any(cc.get("text") == c.get("text") for cc in x["choices"])]))

    for o in objects.values():
        o["parents"] = sorted(o["parents"])
        o["inputs"] = sorted(o["inputs"])
        o["taken"] = sorted(o["taken"])
    return dict(chain=doc.get("chain_id") or doc.get("chain"), question=doc.get("question"), inputs=inputs, cells=out_cells, objects=list(objects.values()),
                results=results, choices=choices, failed=doc.get("failed", []), functions=funcs, params={k: fmt_value(v) for k, v in known.items()},
                unparsed=list(base["unparsed"]), unpaired=base["unpaired"])


def current_at(objects, name, stmt):
    """The object holding `name` when `stmt` ran: the latest (name, cell) at or before the statement's cell."""
    best = None
    for oid, o in objects.items():
        if name in o["names"] and (o["cell"], o["order"]) <= (stmt["cell"], 10 ** 9):
            if any(int(s.split(".s")[1]) < int(stmt["id"].split(".s")[1]) or o["cell"] < stmt["cell"] for s in o["stmts"]):
                best = oid
    return best


def helper_words(f, op):
    """A helper of the chain's own, as this call runs it, from its code (extract.helper_profile): its steps when they
    are few (group by soil; keep rows where regime = 'A'; ...), else the calls it makes; that it re-draws the rows of
    the table this call passes, when the call switches its resampling on; and, when the number it returns comes from
    arithmetic the vocabulary does not name, that this is not traced, so the analyst's own description of it is not
    taken for the map's."""
    lab = f.get("label", "a helper")
    if "own" not in f:                                     # a helper the map knows only by its label
        return lab
    if f.get("produces") == "estimate":                   # a named method: keep its name; say what is not traced
        return lab + (f"; {UNTRACED}" if f.get("untraced") else "")
    active, am = bool(op.get("seeded")), op.get("argmap") or {}
    real = any(s["verb"] == "resample" and s["text"] != "draw random indices" for s in f["own"])
    steps, redraw = [], None
    for s in f["own"]:
        if s["verb"] == "resample":
            if (s.get("guarded") and not active) or (s["text"] == "draw random indices" and real):
                continue                                   # off in this call, or only seeding a re-draw
            arg = am.get(s.get("param")) if s.get("param") else None
            redraw = f"re-draws the rows of {arg} with replacement" if arg else "re-draws rows with replacement"
            continue
        if s["text"] not in steps:
            steps.append(s["text"])
    words = "; ".join(steps) if 0 < len(steps) <= 4 else lab.replace("; can resample", "")
    parts = [w for w in (words, redraw) if w and w != "a helper"]
    if f.get("untraced"):
        parts.append(UNTRACED)
    return "; ".join(parts) if parts and parts[0] != UNTRACED else ("a helper" + (f"; {UNTRACED}" if f.get("untraced") else ""))


def plain_steps(o, funcs, input_columns):
    """An object's operations as a few plain steps: reads, filters, joins, groupings, methods; type tidying folded."""
    steps, cols, tidy = [], [], False
    for op in o["ops"]:
        v, t = op["verb"], op["text"]
        if v == "derive" and op.get("column"):
            if op["column"] in input_columns and op["column"] not in o.get("_new", set()):
                tidy = True
                continue
            o.setdefault("_new", set()).add(op["column"])
            if op["column"] not in cols:
                cols.append(op["column"])
            continue
        if v == "derive" and (t.split(" (for")[0] in V.TIDY):
            tidy = True
            continue
        if v in ("select", "record", "draw", "define"):
            continue
        if v == "resample" and op.get("redraws"):           # what the bootstrap re-draws: its unit
            t = f"{t}, re-drawing the rows of {op['redraws']}"
        if v == "call":
            f = funcs.get(t, {})
            if op.get("args"):
                t = t + "(" + ", ".join(op["args"]) + ")"
                f = funcs.get(op["text"], {})
            lab = helper_words(f, op)
            ch = ", ".join(c["text"] for c in f.get("choices", []))
            t = (f"{t}: {lab}" if t.endswith(")") else f"{t}(): {lab}") + (f" · {ch}" if ch and lab != "a helper" else "")
            v = "method" if f.get("produces") == "estimate" else "helper"
        if v == "summarise" and o["kind"] in ("table",) and not t.startswith(("group by", "resample", "rolling", "count values", "cross-tabulate", "pivot")):
            continue
        if v == "compute" and t == "built in a loop" and (o["parents"] or o["inputs"]):
            continue
        step = (v, t)
        if step not in steps:
            steps.append(step)
    out = [dict(verb=v, text=t) for v, t in steps]
    if cols:
        out.append(dict(verb="derive", text="add " + ", ".join(cols)))
    if tidy:
        out.append(dict(verb="tidy", text="tidy types"))
    return out
