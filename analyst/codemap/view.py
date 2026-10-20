"""The third stage of the code map (blueprint 4.7-4.13): the stored, render-ready view the modal draws. From the map
(objects.build_map) and the ChainRecord: the rows (steps, failed attempts, reviews, the report, in order), the input
lanes, the results, each result's recipe in plain words and its diagram (nodes and edges; the client lays them out),
the step details, the checks worth making, the one line of a chain that ran no code, and the self-checks.

Chains are referred to by id, as the token {chain:<id>}; the client numbers them (words.chain_ref). Ported from the
design package's prototype (vm.py, vm2.py, thread_vm.py); the fixtures under tests/analyst/fixtures/codemap pin it."""
import datetime as dt
import re
from collections import defaultdict

from . import words as W
from .words import CONTEXT_LABEL, MADE_IN_CODE, PRIMARY_LABEL, UNTRACED, chain_ref, gloss_of, is_chain_label, lane_name


# ---- small helpers (vm.py) -------------------------------------------------------------------------------------------
def tidy_purpose(text):
    """The STEP sentence as a row label: 'This turn does X' -> 'Does X'."""
    t = re.sub(r"^(?:Starting:\s*|This turn\s+|This cell\s+|Last turn's cell\s+)", "", text or "")
    return t[:1].upper() + t[1:] if t else t


def short_label(label, n=58):
    s = label
    while re.match(r"^\([^()]*\)\s*", s):               # notes in front: (test after turn 5), (corrects cell 14, label only)
        s = re.sub(r"^\([^()]*\)\s*", "", s, count=1)
    parts = [p.strip() for p in s.split(",")]
    s = parts[0]
    for p in parts[1:]:                                  # "yield" alone does not tell two results apart
        if len(s.split()) >= 3:
            break
        s += ", " + p
    s = s or label
    return s if len(s) <= n else s[:n - 1].rsplit(" ", 1)[0] + "…"


def input_name(label):
    """A lane's plain name before the app's names are applied (vm.py): the file name without its extension."""
    if is_chain_label(label):
        return label
    return {PRIMARY_LABEL: PRIMARY_LABEL}.get(label, label.rsplit(".", 1)[0].replace("_", " "))


def shape_text(desc):
    if not desc:
        return ""
    m = re.match(r"DataFrame (\d+)x(\d+)", desc)
    if m:
        return f"{int(m.group(1)):,} rows × {m.group(2)} cols"
    m = re.match(r"Series len=(\d+)", desc)
    if m:
        return f"{int(m.group(1)):,} values"
    m = re.match(r"ndarray shape=\((\d+),?\)", desc)
    if m:
        return f"{int(m.group(1)):,} values"
    m = re.match(r"ndarray shape=\(([\d, ]+)\)", desc)
    if m:
        return "array " + " × ".join(f"{int(x):,}" for x in m.group(1).split(",") if x.strip())
    m = re.match(r"(?:dict|set)\[.*\] len=(\d+)", desc)
    if m:
        return f"{int(m.group(1)):,} entries" if desc.startswith("dict") else f"set of {int(m.group(1)):,}"
    m = re.match(r"list\[.*\] len=(\d+)", desc)
    if m:
        return f"list of {m.group(1)}"
    if desc.startswith("function"):
        return ""
    return {"float64": "a number", "float": "a number", "int": "a number", "int64": "a number"}.get(desc, "")


# ---- plain words (vm2.py) --------------------------------------------------------------------------------------------
def day(d):
    y, m, dd = d[:4], int(d[5:7]), int(d[8:10])
    return f"{dd} {W.MONTHS[m - 1]} {y}"


def span(a, b):
    """'2026-08-13', '2026-10-07' -> '13 Aug – 7 Oct 2026'."""
    if a[:4] == b[:4]:
        return f"{int(a[8:10])} {W.MONTHS[int(a[5:7]) - 1]} – {day(b)}"
    return f"{day(a)} – {day(b)}"


def plain(text, params):
    """A step in values, not variables: parameters replaced, a date range said as one."""
    t = text
    for name, val in sorted(params.items(), key=lambda kv: -len(kv[0])):
        v = val.strip("'")
        if re.match(r"^\d{4}-\d{2}-\d{2}$", v) or re.match(r"^-?\d+(\.\d+)?$", v):
            t = re.sub(rf"(?<![\w.]){re.escape(name)}(?![\w(])", v, t)
    # date arithmetic done for the reader: "2026-08-13 - pd.Timedelta(days=7)" -> "2026-08-06"
    t = re.sub(r"(\w+)\.dt\.(?:normalize\(\)|date)", r"\1", t)
    t = re.sub(r"(\w+) < (\d{4}-\d{2}-\d{2}) \+ pd\.Timedelta\(days=1\)", r"\1 ≤ \2", t)     # "< D + 1 day" keeps D itself
    t = re.sub(r"(\d{4}-\d{2}-\d{2}) ([+-]) pd\.Timedelta\(days=(\d+)\)",
               lambda m: (dt.date.fromisoformat(m.group(1)) + dt.timedelta(days=int(m.group(3)) * (1 if m.group(2) == "+" else -1))).isoformat(), t)
    # a window around a day the code computed: "col ≥ X - 9 days and col ≤ X + 3 days"
    t = re.sub(r"(\w+) [≥>] (\w+) - pd\.Timedelta\(days=(\d+)\) and \1 [≤<] \2 \+ pd\.Timedelta\(days=(\d+)\)",
               lambda m: f"dated {m.group(3)} days before to {m.group(4)} days after {m.group(2)} (column {m.group(1)})", t)

    # col ≥ A and col ≤ B, A and B dates -> "dated A – B (column col)"
    def rng(m):
        col, a, b = m.group(1), m.group(2), m.group(3)
        if re.match(r"^\d{4}-\d{2}-\d{2}$", a) and re.match(r"^\d{4}-\d{2}-\d{2}$", b):
            return f"dated {span(a, b)} (column {col})"
        return f"{col} from {a} to {b}"
    t = re.sub(r"(\w+) [≥>] (\S+) and \1 [≤<] (\S+)", rng, t)
    t = re.sub(r"keep rows where dated", "keep rows dated", t)
    # a method first, the helper that ran it last: "bootstrap, 4,000 resamples (boot_ratio)"
    m = re.match(r"^(\w+)\(.+\): (a helper)(; " + UNTRACED + r")?$", t)
    if m:                                                 # a helper given words as arguments: the words are in the cell
        return f"computed with {m.group(1)}()" + (m.group(3) or "")
    m = re.match(r"^(\w+)\(\): (.+?)(?: · (.+))?$", t)
    if m and "pivot" not in t:
        what, extra = m.group(2), m.group(3) or ""
        untraced = what.endswith("; " + UNTRACED)            # said last, after the method and its settings
        what = what[: -len("; " + UNTRACED)] if untraced else what
        tail = f"; {UNTRACED}" if untraced else ""
        if what == "a helper" and not extra:              # a function of the analyst's own, not one the vocabulary knows
            return f"computed with {m.group(1)}()" + tail
        extra = re.sub(r"\bB=(\d+)", lambda k: f"{int(k.group(1)):,} resamples", extra)
        what = what.replace("bootstrap (resamples rows)", "bootstrap").replace(" with bootstrap", ", bootstrap")
        t = what + (", " + extra if extra else "") + tail + f" ({m.group(1)})"
    t = re.sub(r"^context passages \(CTX\.frame\)$", "read the context passages", t)
    t = re.sub(r"^context codes \(CTX\.codes\)$", "read the context codes", t)
    t = re.sub(r"(\w+) = ''", r"\1 is empty", t)
    t = re.sub(r"^(\w+)\(([^)]*)\): pivot (?:(\w+) )?by (\w+) × (\w+) \((\w+)\)$",
               lambda m: f"pivot {m.group(2) or m.group(3) or 'values'} into a grid: {m.group(4)} by {m.group(5)}, {m.group(6)} ({m.group(1)})", t)
    t = re.sub(r"(\w+) = '([^']*)'", r"\1 is \2", t)
    t = t.replace(" in ['", " in '").replace("']", "'")
    t = re.sub(r"^add (.+)$", r"add columns: \1", t) if t.startswith("add ") and not t.startswith("add columns") else t
    t = re.sub(r"^(\w+)\(\): pivot by (\w+) × (\w+) \((\w+)\)$", r"pivot into a grid: \2 by \3, \4 (\1())", t)
    t = t.replace("pivot by ", "pivot into a grid by ").replace(" × ", " by ")
    return t


def qualifiers(o, params):
    """What an object's own steps add to its name: the window it keeps, a value it keeps, what it is grouped by."""
    q = []
    for st in o["steps"]:
        t = plain(st["text"], params)
        m = re.search(r"dated ([^()]+?) \(column", t)
        if m:
            q.append(m.group(1).strip())
            continue
        m = re.search(r"where (\w+) is (\w+)", t)
        if m and st["verb"] == "filter":
            q.append(f"{m.group(2)} only")
            continue
        if t.startswith("group by "):
            q.append("by " + t[len("group by "):])
            continue
        m = re.search(r"pivot (\w+) into a grid: (\w+) by (\w+)", t)
        if m:
            q.append(f"{m.group(1)} by {m.group(2)} and {m.group(3)}")
            continue
        m = re.search(r"pivot into a grid(?: \w+)? by (.+?)(?: \(|$)", t)
        if m:
            q.append("by " + m.group(1))
            continue
        if t.startswith("drop rows missing ") and len(t) < 40:
            q.append("with " + t[len("drop rows missing "):])
    return q


def is_data(o):
    """Values made in the code: lists, arrays and numbers made from something else (or built in a loop). Not typed
    settings, word lists, functions, or names nothing was made from (a list of column names, an empty dict). A value
    read off a table with no operation of its own stays inside that table's box (mark_origins)."""
    return o["kind"] in ("value", "helper") and bool(o["parents"] or o["inputs"] or o.get("taken")
                                                     or any(op["verb"] == "compute" for op in o.get("ops", []))) \
        and bool(o.get("_own") or not o.get("_from_data")) and not o.get("_same")


def mark_origins(objs):
    """For each object, in the order they were made: is it made from a table or a data file, and has it an
    operation of its own (not just tidying types)? A name re-bound to its own earlier value with nothing done to it
    (P5 = np.asarray(P5, float) in a later cell) is that value carried on, not a new box."""
    for o in objs.values():
        o["_own"] = any(st["verb"] != "tidy" for st in o["steps"])
        o["_from_data"] = any(i != CONTEXT_LABEL and not is_chain_label(i) for i in o["inputs"]) or any(
            (objs[p]["kind"] == "table" or objs[p].get("_from_data")) for p in o["parents"] if p in objs)
        ps = [p for p in o["parents"] if p in objs]
        o["_same"] = (not o["_own"] and any(st["verb"] == "tidy" for st in o["steps"]) and len(ps) == 1
                      and objs[ps[0]]["names"] == o["names"] and not o["inputs"] and not o.get("taken"))


def is_box(o):
    """What a recipe draws as a box: a table, a calculation, a figure, or values made in the code."""
    return o["kind"] in ("table", "estimate", "figure") or is_data(o)


def family(o):
    return "table" if o["kind"] == "table" else ("data" if is_data(o) else o["kind"])


def and_list(xs, most=4):
    xs = list(dict.fromkeys(xs))
    if len(xs) > most:
        xs = xs[:most - 1] + [f"{len(xs) - most + 1} more"]
    return xs[0] if len(xs) == 1 else ", ".join(xs[:-1]) + " and " + xs[-1]


def data_label(o):
    """A value made in the code is named by its variable and its size (from the kernel's registry, when kept)."""
    names = [n for n in o["names"] if n != "_"] or o["names"]
    nm = ", ".join(names[:3]) + ("…" if len(names) > 3 else "")
    size = shape_text(o.get("shape"))
    return nm + (f", {size}" if size else "")


def data_steps(o, objs):
    """Its steps in plain words; with no operation the vocabulary knows, what it was computed from."""
    if any(st["verb"] != "tidy" for st in o["steps"]):
        return o["steps"]
    ps = [objs[p] for p in o["parents"] if p in objs]
    srcs = [q["name"] for q in ps if q["kind"] not in ("function", "param", "pattern")] + list(o.get("taken") or [])
    fns = [q["name"] + "()" for q in ps if q["kind"] == "function"]
    sets = [q["name"] for q in ps if q["kind"] == "param"]
    if any(op["text"] == "built in a loop" for op in o.get("ops", [])):
        text = "built in a loop" + (" from " + and_list(srcs) if srcs else "")
    elif srcs or fns:
        text = "computed from " + (and_list(srcs) if srcs else "") + ((" with " if srcs else "") + and_list(fns) if fns else "")
    elif sets:
        text = "computed from the setting" + ("s " if len(sets) > 1 else " ") + and_list(sets)
    else:
        text = MADE_IN_CODE
    return [dict(verb="compute", text=text)]


def build_labels(m, primary_name):
    objs = {o["id"]: o for o in m["objects"]}
    params = m.get("params", {})
    mark_origins(objs)
    app = lambda label: lane_name(label, primary_name)      # noqa: E731
    base = {}
    for oid, o in objs.items():                       # objects come in the order they were made
        if not is_box(o):
            continue
        ins = [app(i) for i in o["inputs"] if i != CONTEXT_LABEL]
        parents = []
        for p in o["parents"]:
            q = objs.get(p)
            if not q:
                continue
            if q["kind"] == "function":
                parents += [pp for pp in q["parents"] if pp in objs and objs[pp]["kind"] == "table"]
            elif q["kind"] == "table" or (is_data(q) and is_data(o)):
                parents.append(p)
        parents = list(dict.fromkeys(parents))
        if ins:
            b = " + ".join(dict.fromkeys(ins))
        elif len(parents) == 1:
            b = base.get(parents[0], objs[parents[0]]["name"])
        elif parents:
            b = " + ".join(dict.fromkeys(base.get(p, objs[p]["name"]) for p in parents))
            if len(b) > 48:
                b = "joined table"
        else:
            b = MADE_IN_CODE
        base[oid] = b
        if o["kind"] == "estimate":
            meth = [s["text"] for s in o["steps"] if s["verb"] in ("method", "resample", "test")]
            helpers = [s["text"].split(":")[0] for s in o["steps"] if s["verb"] == "helper"]
            if meth:
                what = meth[-1].split(": ", 1)[-1].split(" · ")[0].replace("; " + UNTRACED, "").split(", re-drawing")[0]
                if "can resample" in what and len(meth) > 1:
                    what = meth[0].split(": ", 1)[-1].split(" · ")[0]
            elif any(s["text"] == "percentile" for s in o["steps"]):
                what = "percentiles"
            elif helpers:
                what = "computed by " + helpers[0]
            else:
                what = "a number"
            what = what.replace("bootstrap (resamples rows)", "bootstrap").replace(" with bootstrap", ", bootstrap")
            bs = [s["text"] for s in o["steps"] if "B=" in s["text"]]
            if bs and "bootstrap" in what:
                n = re.search(r"B=(\d+)", bs[0]).group(1)
                what += f", {int(n):,} resamples"
            o["label"] = "estimate: " + what.replace("; can resample", "")
        elif o["kind"] == "figure":
            o["label"] = "figure"
        elif is_data(o):
            o["label"] = data_label(o)
            own_in = [app(i) for i in o["inputs"] if i != CONTEXT_LABEL]
            o["prov"] = ("from " + " + ".join(dict.fromkeys(own_in))).replace("from From ", "from ") if own_in else MADE_IN_CODE
            o["steps"] = data_steps(o, objs)
        else:
            tokens = b.split(" + ")
            if all(t == MADE_IN_CODE or t.startswith("From {chain:") for t in tokens):
                # a table the code built, not read from a data file: named by its variable and size, like a value
                chains = [t[len("From "):] for t in tokens if t.startswith("From {chain:")]
                o["label"] = data_label(o)
                o["prov"] = "from " + " + ".join(dict.fromkeys(chains)) if chains else MADE_IN_CODE
                o["named"] = True
                continue
            q = qualifiers(o, params)
            joined = len(parents) > 1 and not ins
            lab = b + (", joined" if joined and b != "joined table" else "") + ("".join(", " + x for x in q) if q else "")
            o["label"] = lab if len(lab) <= 72 else lab[:71].rsplit(" ", 1)[0] + "…"
    return objs


def compress(chain, objs):
    """A table made from one table that nothing else in the recipe uses merges into its child."""
    ids = [c for c in chain if is_box(objs[c])]
    inset = set(ids)
    kids = defaultdict(list)
    for c in ids:
        for p in objs[c]["parents"]:
            if p in inset:
                kids[p].append(c)
    merged_into = {}

    def head(x):
        seen = set()
        while x in merged_into and x not in seen:      # objects that change each other can point both ways
            seen.add(x)
            x = merged_into[x]
        return x
    for c in ids:
        ps = [p for p in objs[c]["parents"] if p in inset]
        if len(ps) == 1 and not [i for i in objs[c]["inputs"] if i != CONTEXT_LABEL] and len(kids[ps[0]]) == 1 \
                and objs[ps[0]]["cell"] == objs[c]["cell"] and family(objs[ps[0]]) == family(objs[c]) in ("table", "data") \
                and head(c) != ps[0]:                    # never merge into a loop
            merged_into[ps[0]] = c
    groups = defaultdict(list)
    for c in ids:
        groups[head(c)].append(c)
    return [groups[h] for h in ids if h in groups and head(h) == h], head


def recipe_items(groups, objs, params, app):
    items = []
    for g in groups:
        last = objs[g[-1]]
        steps, ins = [], []
        for c in g:
            for st in objs[c]["steps"]:
                if st["verb"] == "tidy":
                    continue
                t = plain(st["text"], params)
                if t not in [s["text"] for s in steps]:
                    steps.append(dict(text=t, gloss=gloss_of(t) if st["verb"] in ("method", "resample", "test", "summarise", "reshape", "combine") or "pivot" in t else ""))
            for i in objs[c]["inputs"]:
                if i != CONTEXT_LABEL and app(i) not in ins:
                    ins.append(app(i))
        data = is_data(last) or bool(last.get("named"))     # named by its variable: the sub line says where it came from
        names = " → ".join(objs[c]["name"] for c in g) if (len(g) > 1 or not data) else last.get("prov", MADE_IN_CODE)
        items.append(dict(id=g[-1], members=g, label=last.get("label") or last["name"], names=names,
                          cell=last["cell"], kind=last["kind"], shape="" if data else last.get("shape_text", ""), inputs=ins, steps=steps))
    return items


def acyclic(nodes, edges):
    """The edges without those that close a cycle: a table changed with a value computed from it is not a loop on the
    map. Broken where a depth-first walk from the nodes, in their order, closes it (the prototype's layout did this)."""
    out_e = defaultdict(list)
    for a, b in edges:
        out_e[a].append(b)
    state, back = {}, set()

    def dfs(u):
        state[u] = 1
        for v in out_e[u]:
            if state.get(v) == 1:
                back.add((u, v))
            elif not state.get(v):
                dfs(v)
        state[u] = 2
    for n in nodes:
        if not state.get(n["id"]):
            dfs(n["id"])
    return [e for e in edges if e not in back]


def inputs_through(direct, objs, items, head):
    """The inputs behind the plain values a RESULT read, up to the first box: a dataset read with no table in between
    (x = df["col"]; x = np.asarray(x, float); RESULT(f"... {x.mean()}")) still names the dataset (2026-10-20)."""
    item_ids = {it["id"] for it in items}
    out, seen, todo = [], set(), list(direct)
    while todo:
        p = todo.pop(0)
        if p in seen or p not in objs or head(p) in item_ids:
            continue
        seen.add(p)
        if objs[p]["kind"] in ("function", "value", "helper"):
            out += [i for i in objs[p]["inputs"] if i not in out]
            todo.extend(sorted(objs[p]["parents"]))
    return out


def diagram(items, result, objs, head):
    """The recipe as a picture: its inputs at the top, its tables in the middle, the number at the bottom. Nodes and
    edges only: the client lays them out (blueprint 8.8). An input node of an earlier chain is `in:chain:<id>`."""
    nodes, edges = [], []
    seen_inputs = []
    item_ids = {it["id"] for it in items}

    def in_id(name):
        return ("in:chain:" + name[len("From {chain:"):-1]) if name.startswith("From {chain:") else "in:" + name
    for it in items:
        for i in it["inputs"]:
            if i not in seen_inputs:
                seen_inputs.append(i)
                nodes.append(dict(id=in_id(i), kind="input", label=i, names="", cell=None, step=""))
            edges.append((in_id(i), it["id"]))
        for m in it["members"]:
            # through helpers and plain values to the tables behind them (a helper stands for the tables it reads)
            ps, seen, todo = [], set(), list(objs[m]["parents"])
            while todo:
                p = todo.pop()
                if p in seen or p not in objs:
                    continue
                seen.add(p)
                q = objs[p]
                if head(p) in item_ids:
                    ps.append(p)
                elif q["kind"] in ("function", "value", "helper"):
                    todo.extend(q["parents"])
            for p in ps:
                hp = head(p)
                # an edge runs from what was made earlier to what was made later: a table changed with a value
                # computed from it is not a loop on the map
                if hp in item_ids and hp != it["id"] and (hp, it["id"]) not in edges:
                    edges.append((hp, it["id"]))
        first = [s["text"] for s in it["steps"]][:2]
        nodes.append(dict(id=it["id"], kind=it["kind"], label=it["label"], names=it["names"], cell=it["cell"],
                          step=" · ".join(first)[:120]))
    if result is not None:
        nodes.append(dict(id="result", kind="result", label=result["label"], names="", cell=result["cell"], step=""))
        # what the result reads directly, through helpers and plain values to the boxes behind them
        direct, seen, todo = [], set(), list(result.get("direct", []))
        while todo:
            p = todo.pop(0)
            if p in seen or p not in objs:
                continue
            seen.add(p)
            if head(p) in item_ids:
                direct.append(head(p))
            elif objs[p]["kind"] in ("function", "value", "helper"):
                todo.extend(sorted(objs[p]["parents"]))
        for i in result.get("inputs", []):
            if i not in seen_inputs:
                seen_inputs.append(i)
                nodes.append(dict(id=in_id(i), kind="input", label=i, names="", cell=None, step=""))
            edges.append((in_id(i), "result"))
        if not direct and items and not result.get("inputs"):
            direct = [items[-1]["id"]]
        for d in dict.fromkeys(direct):
            edges.append((d, "result"))
    return dict(nodes=nodes, edges=[[a, b] for a, b in acyclic(nodes, edges)])


# ---- the view --------------------------------------------------------------------------------------------------------
def steps_view(m, chain_id, events=(), mode="", titles=None):
    """The rows, lanes, results, recipes (by variable names), step details and checks (vm.build)."""
    objects = {o["id"]: o for o in m["objects"]}

    def sources_of(o, here=None):
        """The tables and estimates an object was made from; a helper function stands for the tables it reads."""
        out = []
        for p in o["parents"]:
            q = objects.get(p)
            if not q:
                continue
            if q["kind"] == "function":
                for pp in q["parents"]:
                    qq = objects.get(pp)
                    if qq and qq["kind"] in ("table", "estimate") and qq["name"] not in out:
                        out.append(qq["name"] + (f" (cell {qq['cell']})" if here and qq["cell"] != here else ""))
            elif q["kind"] in ("table", "estimate", "figure"):
                nm = q["name"] + (f" (cell {q['cell']})" if here and q["cell"] != here else "")
                if nm not in out:
                    out.append(nm)
        return out + [input_name(x) for x in o["inputs"]]
    inputs = [i for i in m["inputs"]]

    def status_of(i):
        if i["status"].startswith("used through "):
            return "via"
        return {"used": "used", "loaded, not used": "loaded", "not used": "unused"}[i["status"]]

    def cols_of(i):
        if i["kind"] == "chain":
            names, cells = i.get("names", []), i.get("from_cells", [])
            if len(names) <= 3:
                return ", ".join(names)
            where = f"cell {cells[0]}" if len(cells) == 1 else f"cells {cells[0]}–{cells[-1]}"
            return f"{len(names)} names, {where}"            # the panel lists them; a lane holds a few words
        if i.get("through") and not i["cells"]:
            return f"through {chain_ref(i['through'])}"
        if not i["columns"]:
            return ""
        used = i["used_columns"]
        named = ", ".join(used)
        if used and len(used) < i["columns"] and len(named) <= 18:      # a lane holds a few words: name one or two
            return f"{named} · {len(used)} of {i['columns']}"
        return f"{len(used)} of {i['columns']} columns"
    vm_inputs = [dict(id=f"i{k}", name=input_name(i["label"]), file=i["label"], kind=i["kind"], chain=i.get("chain"),
                      through=i.get("through"), names=i.get("names", []), from_cells=i.get("from_cells", []),
                      status=status_of(i), cols=cols_of(i), detail=i.get("detail", ""),
                      used_columns=i.get("used_columns", []),
                      unused_columns=[c for c in i.get("all_columns", []) if c not in i.get("used_columns", [])]) for k, i in enumerate(inputs)]

    # which inputs each cell reads directly, and which reach it through earlier cells
    def roots(oid, seen=None):
        seen = seen if seen is not None else set()
        if oid in seen or oid not in objects:
            return set()
        seen.add(oid)
        o = objects[oid]
        out = set(o["inputs"])
        for p in o["parents"]:
            out |= roots(p, seen)
        return out

    results = {}
    for r in m["results"]:
        printed = r.get("kind") == "printed"
        results[r["id"]] = dict(id=r["id"], kind=r.get("kind", "result"), cell=r["cell"], label=r["label"],
                                short=(r["line"] if len(r["line"]) <= 58 else r["line"][:57].rstrip() + "…") if printed else short_label(r["label"]),
                                estimate=r["estimate"], interval=(r["interval"] or "").replace("+", ""), unit=r["unit_dir"], status=r["status"],
                                corrected_by=r.get("corrected_by"), test=r.get("test"), line=r["line"], lines=r.get("lines", []))
    used_by = {}
    for c in m["cells"]:
        for f in c["reads_from"]:
            used_by.setdefault(f, []).append(c["cell"])

    steps, rows = {}, []
    for c in m["cells"]:
        n = c["cell"]
        objs = [objects[o] for o in objects if objects[o]["cell"] == n]
        direct, via = set(c.get("direct_inputs", [])), set()
        for o in objs:
            direct |= set(o["inputs"])
            via |= set(o.get("via") or {})                   # reached through names an earlier chain made
            for p in o["parents"]:
                if p in objects and objects[p]["cell"] != n:
                    via |= roots(p)
        lanes = []
        for i in inputs:
            lab = i["label"]
            lanes.append("read" if lab in direct else ("via" if lab in via else ""))
        chips = []
        for o in objs:
            if o["kind"] not in ("table", "estimate", "figure", "value"):
                continue
            for st in o["steps"]:
                v, t = st["verb"], st["text"]
                if v == "derive":
                    chips.append("add columns")
                elif v == "method":
                    lab = t.split(": ", 1)[1] if ": " in t else t
                    for k, sh in W.TEST_SHORT.items():
                        if lab.startswith(k):
                            chips.append(sh)
                    if "bootstrap" in lab:
                        chips.append("bootstrap")
                elif v == "test":
                    chips.append(W.TEST_SHORT.get(t, t))
                elif v in W.VERB_CHIP:
                    chips.append(W.VERB_CHIP[v])
        chips = [x for x in chips if x != "compute"]
        if objs and not direct and not via and c["kind"] != "figures":
            chips.insert(0, "compute")
        if c["results"]:
            chips.append("RESULT")
        if c["kind"] == "figures":
            chips.append("figure")
        if not chips and c.get("printed"):
            chips = ["print"]
        chips = sorted(set(chips), key=lambda x: (W.CHIP_ORDER.index(x) if x in W.CHIP_ORDER else 7.5, x))
        role = c["role"]
        names_from = {}
        for o in objs:
            for pid in o["parents"]:
                q = objects.get(pid)
                if q and q["cell"] != n and q["kind"] in ("table", "estimate", "param", "pattern", "function"):
                    names_from.setdefault(q["cell"], [])
                    if q["name"] not in names_from[q["cell"]]:
                        names_from[q["cell"]].append(q["name"])
        steps[n] = dict(cell=n, turn=c.get("turn"), purpose=c["purpose"], role=role, printed=c.get("printed", []),
                        why=" ".join((c.get("why") or "").split())[:700], takes=[dict(cell=k, names=v) for k, v in sorted(names_from.items())],
                        inputs=[input_name(x) for x in sorted(direct) if x != CONTEXT_LABEL],
                        builds=[dict(name=o["name"], kind=o["kind"], shape=shape_text(o.get("shape")),
                                     from_=sources_of(o, n),
                                     steps=[s["text"] for s in o["steps"] if s["verb"] != "tidy"])
                                for o in objs if o["kind"] in ("table", "estimate", "figure")],
                        reads_from=c["reads_from"], used_by=sorted(set(used_by.get(n, []))), results=c["results"], lines=c["lines"],
                        cited=c["cited"], takes_chain=c.get("taken", []), printout=c.get("printout"))
        row = dict(type="step", cell=n, turn=c.get("turn"), purpose=tidy_purpose(c["purpose"]), role=role, chips=chips[:6],
                   lanes=lanes, results=c["results"], printout=c.get("printout"), uses=c["reads_from"], cited=c["cited"],
                   figures=(c["kind"] == "figures"))
        if not c.get("mapped", True):
            row["mapped"] = False
        rows.append(row)
    # failed attempts, reviews, the report: in turn order
    extra = list(events)
    for f in m.get("failed", []):
        extra.append(dict(type="failed", turn=f.get("turn"), after_cell=f.get("after_cell"), purpose=re.sub(r"^This turn ", "", f.get("step", "")).rstrip("."),
                          error=f.get("error", "")))
    ordered = []
    first_cell = rows[0]["cell"] if rows else None
    for e in extra:                                      # failed before this chain's first cell (after its path's last)
        if e["type"] == "failed" and first_cell is not None and (e.get("after_cell") or 0) < first_cell:
            ordered.append(e)
    for r in rows:
        ordered.append(r)
        for e in extra:
            if e.get("after_cell") == r["cell"]:
                ordered.append(e)
    # turn-ordered events (reviews, report) go after the step whose turn precedes them
    final = list(ordered)
    for e in [e for e in extra if e["type"] in ("review", "report")]:
        k = max([i for i, r in enumerate(final) if (r.get("turn") or 0) <= e["turn"] and r["type"] in ("step", "failed") and r.get("turn") is not None] or [len(final) - 1])
        final.insert(k + 1, e)
    for e in [e for e in extra if e["type"] == "final"]:
        final.append(e)

    recipes = {}
    for r in m["results"]:
        chain = [objects[o] for o in r["objects"] if o in objects]
        items = []
        for o in chain:
            if o["kind"] not in ("table", "estimate"):
                continue
            items.append(dict(name=o["name"], cell=o["cell"], kind=o["kind"], shape=shape_text(o.get("shape")),
                              from_=sources_of(o),
                              steps=[s["text"] for s in o["steps"] if s["verb"] != "tidy"]))
        params = [dict(name=o["name"], value=o.get("value", ""), typed=o.get("typed", False), cell=o["cell"])
                  for o in chain if o["kind"] == "param"]
        patterns = [dict(name=o["name"], cell=o["cell"], value=(o.get("value") or "")[:90]) for o in chain if o["kind"] == "pattern"]
        ch = []
        for c in r["choices"]:
            t = c["text"]
            if c["kind"] in ("typed date",):
                continue                              # shown with the parameters
            if t not in [x["text"] for x in ch] and not re.match(r"^[A-Za-z_]\w* resamples$", t):
                ch.append(dict(text=t, kind=c["kind"], cell=c.get("cell")))
        ins = []
        for o in chain:
            for x in o["inputs"]:
                if input_name(x) not in ins:
                    ins.append(input_name(x))
        recipes[r["id"]] = dict(inputs=ins, items=items, params=params, patterns=patterns, choices=ch, cells=r["cells"])

    checks = []
    for i in vm_inputs:
        if i["kind"] == "chain":
            checks.append(dict(kind="chain", text=W.check_rests_on(i["chain"], i["names"], i["from_cells"]), ref=i["id"], chain=i["chain"]))
        elif i["status"] not in ("used", "via"):
            checks.append(dict(kind="input", text=W.check_input(i["name"], i["status"]), ref=i["id"]))
    printed_answers = [c["cell"] for c in m["cells"] if c["role"] == "evidence"]
    if not any(r.get("kind", "result") == "result" for r in m["results"]) and printed_answers:
        checks.append(dict(kind="nan", text=W.check_no_result(printed_answers[-1]), ref=f"cell{printed_answers[-1]}"))
    typed = {}
    n_results = sum(1 for r in results.values() if r["kind"] == "result")
    for rid, rc in recipes.items():
        if results[rid]["kind"] != "result":
            continue                                  # the checks count RESULT lines
        for p in rc["params"]:
            if p["typed"]:
                typed.setdefault((p["name"], p["value"], p["cell"]), []).append(rid)
    merged = {}
    for (name, value, cell), rids in typed.items():
        e = merged.setdefault((name, value), dict(cells=[], rids=set()))
        e["cells"].append(cell); e["rids"] |= set(rids)
    for (name, value), e in merged.items():
        cells_txt = "cell " + str(e["cells"][0]) if len(e["cells"]) == 1 else "cells " + ", ".join(str(c) for c in sorted(e["cells"]))
        checks.append(dict(kind="typed", text=W.check_typed(name, value, cells_txt, len(e["rids"]), n_results), ref=f"cell{sorted(e['cells'])[0]}"))
    nan = [r for r in results.values() if r["status"] == "not computed"]
    if nan:
        checks.append(dict(kind="nan", text=W.check_nan(len(nan), sorted({r["cell"] for r in nan})), ref=nan[0]["id"]))
    corr = [r for r in results.values() if r["status"] == "corrected"]
    if corr:
        checks.append(dict(kind="corrected", text=W.check_corrected(len(corr)), ref=corr[0]["id"]))
    pats = {}
    for rid, rc in recipes.items():
        for p in rc["patterns"]:
            pats.setdefault((p["name"], p["cell"]), []).append(rid)
    if pats:
        names = sorted({n for n, _ in pats})
        checks.append(dict(kind="pattern", text=W.check_patterns(names), ref=f"cell{sorted(pats)[0][1]}"))
    return dict(id=str(chain_id), question=m["question"], inputs=vm_inputs, rows=final, results=results,
                recipes=recipes, steps={str(k): v for k, v in steps.items()}, checks=checks)


def upgrade(vm_chain, m, primary_name):
    """Plain labels, recipes compressed with their diagrams, one recipe per figure, step details (vm2.upgrade)."""
    app = lambda label: lane_name(label, primary_name)      # noqa: E731
    objs = build_labels(m, primary_name)
    params = m.get("params", {})
    for o in objs.values():
        o["shape_text"] = shape_text(o.get("shape"))
    results_by_id = {r["id"]: r for r in m["results"]}
    new_recipes, diagrams = {}, {}
    for rid, rec in vm_chain["recipes"].items():
        r = results_by_id[rid]
        groups, head = compress(r["objects"], objs)
        items = recipe_items(groups, objs, params, app)
        res_view = vm_chain["results"][rid]
        if res_view.get("kind") == "printed":          # a printout: its first printed line, cut to the box
            ln = res_view.get("line") or "printed"
            rlabel = ln if len(ln) <= 22 else ln[:21].rstrip() + "…"
        else:
            rlabel = (res_view["estimate"] or "—") + (f" ({res_view['interval']})" if res_view["interval"] else "")
        rin = list(dict.fromkeys(app(i) for i in r.get("direct_inputs", []) + inputs_through(r.get("direct", []), objs, items, head) if i != CONTEXT_LABEL))
        dg = diagram(items, dict(label=rlabel, cell=r["cell"], direct=r.get("direct", []), inputs=rin), objs, head)
        # the inputs behind its boxes, then what the RESULT read itself (a dataset read with no table in between)
        new_recipes[rid] = dict(rec, items=items, inputs=list(dict.fromkeys([i for it in items for i in it["inputs"]] + rin)))
        diagrams[rid] = dg
    # figures: one recipe per figure, as a result has one (the reader picks a result, a printout or a figure). Keyed
    # fig<cell> when the cell drew one figure, fig<cell>.<i> when it drew several, in the order they were made; the
    # captions come from the Figures reply, one per figure when the counts agree
    by_cell = defaultdict(list)
    for o in sorted(objs.values(), key=lambda o: o["order"]):
        if o["kind"] == "figure":
            by_cell[o["cell"]].append(o)
    figures = {}
    for cell, fl in by_cell.items():
        purpose = (vm_chain["steps"].get(str(cell)) or {}).get("purpose") or ""
        caps = [x.strip() for x in purpose[len("Figures: "):].split(" | ")] if purpose.startswith("Figures: ") else []
        for i, o in enumerate(fl, 1):
            anc, todo = [], list(o["parents"])
            while todo:
                x = todo.pop()
                if x in anc or x not in objs or x == o["id"]:
                    continue
                anc.append(x)
                todo.extend(objs[x]["parents"])
            groups, head = compress(sorted(anc, key=lambda x: objs[x]["order"]), objs)
            items = [it for it in recipe_items(groups, objs, params, app) if it["kind"] != "figure"]
            fid = f"fig{cell}" if len(fl) == 1 else f"fig{cell}.{i}"
            ins = list(dict.fromkeys(app(x) for x in o["inputs"] if x != CONTEXT_LABEL))
            label = "figure" if len(fl) == 1 else f"figure {i} of {len(fl)}"
            diagrams[fid] = diagram(items, dict(label=label, cell=cell, direct=sorted(o["parents"]), inputs=ins), objs, head)
            new_recipes[fid] = dict(inputs=list(dict.fromkeys([x for it in items for x in it["inputs"]] + ins)), items=items, params=[],
                                    patterns=[], choices=[], cells=sorted({it["cell"] for it in items} | {cell}))
            cap = caps[i - 1] if len(caps) == len(fl) else (" | ".join(caps) if len(fl) == 1 else "")
            figures[fid] = dict(id=fid, cell=cell, n=i, of=len(fl), name=o["name"], caption=cap, label=label)
    vm_chain["figures"] = figures
    # a label written as a format string ("... (%d)") reads as printed: the RESULT line carries the filled-in words
    for rid, r in vm_chain["results"].items():
        if "%" in r["label"] and r.get("line"):
            mm = re.match(r"^(.*?): [+\-−]?(?:[\d.,]+|nan)\b", r["line"])
            if mm:
                r["label"] = mm.group(1)
                r["short"] = short_label(r["label"])
    vm_chain["recipes"] = new_recipes
    vm_chain["diagrams"] = diagrams
    # step details: plain labels for what each step built
    for n, st in vm_chain["steps"].items():
        builds = []
        for o in objs.values():
            if str(o["cell"]) == n and is_box(o):
                data = is_data(o) or bool(o.get("named"))
                builds.append(dict(label=o.get("label") or o["name"], name=o.get("prov", MADE_IN_CODE) if data else o["name"], kind=o["kind"],
                                   shape="" if data else o["shape_text"],
                                   steps=[dict(text=plain(s["text"], params), gloss=gloss_of(plain(s["text"], params)) if s["verb"] in ("method", "resample", "test", "summarise", "reshape", "combine") else "")
                                          for s in o["steps"] if s["verb"] != "tidy"]))
        st["builds"] = builds
        st["inputs"] = [("From " + x[len("from "):]) if is_chain_label(x) else (app(x) if "." in x or x == PRIMARY_LABEL else x)
                        for x in st["inputs"]]
    for i in vm_chain["inputs"]:
        i["name"] = ("From " + chain_ref(i["chain"])) if i.get("kind") == "chain" else app(i["file"])
    for c in vm_chain["checks"]:
        for key, name in W.APP_NAMES:
            c["text"] = c["text"].replace(key.replace("_", " "), name)
        c["text"] = c["text"].replace("primary dataset", primary_name)
    return vm_chain


# ---- threads (thread_vm.py): citations into earlier chains, the no-code chain ----------------------------------------
def cites_checks(doc, own_cells):
    """'the report also cites {chain:<id>}'s cells 5, 6 and 12': a [cell n] the report cites that the path gives to an
    earlier chain; 'the report cites ...' when this chain ran no code."""
    path_cells = {int(k): str(v) for k, v in (doc.get("path_cells") or {}).items() if str(k).isdigit()}
    cites = sorted({int(x) for x in re.findall(r"\[cell (\d+)\]", doc.get("report") or "")})
    others = {}
    for n in cites:
        if n not in own_cells and path_cells.get(n) and path_cells[n] != str(doc.get("chain_id")):
            others.setdefault(path_cells[n], []).append(n)
    out = []
    for o, cells in sorted(others.items(), key=lambda kv: min(kv[1])):
        out.append(dict(kind="cites", text=W.check_cites(not own_cells, o, cells), chain=o, cell=cells[0], ref=f"cell{cells[0]}"))
    return out


def report_title(doc):
    t = (doc.get("title") or "").strip()
    if t:
        return t
    m = re.search(r"^#\s+(.+)$", doc.get("report") or "", re.M)
    return m.group(1).strip() if m else (doc.get("question") or "")


def counts(doc):
    """The header's facts from the record: turns, cells, a figures cell, failed attempts, reviews, RESULT lines."""
    cells = doc.get("cells") or []
    n_an = max([0] + [c.get("turn") or 0 for c in cells] + [f.get("turn") or 0 for f in doc.get("failed") or []]
               + [e.get("turn") or 0 for e in doc.get("events") or [] if e.get("type") == "report"])
    return dict(turns=n_an, cells=sum(1 for c in cells if c.get("kind") != "figures"), figures_cell=any(c.get("kind") == "figures" for c in cells),
                failed=len(doc.get("failed") or []), reviews=sum(1 for e in doc.get("events") or [] if e.get("type") in ("review", "final")))


def build_view(m, doc, primary_name="primary dataset"):
    """The whole view of one chain from its map and its record."""
    titles = doc.get("titles") or {}
    path = [str(x) for x in (doc.get("path") or [doc.get("chain_id")])]
    chain_id = str(doc.get("chain_id"))
    if not doc.get("cells"):
        cc = cites_checks(doc, set())
        where = f" {cc[0]['text'][0].upper()}{cc[0]['text'][1:]}." if cc else ""
        k = counts(doc)
        view = dict(id=chain_id, title=report_title(doc), question=doc.get("question"), meta=W.meta_nocode(doc.get("mode") or "", k["turns"], doc.get("searches") or 0),
                    inputs=[], rows=[], results={}, recipes={}, steps={}, checks=cc, diagrams={}, nocode=True,
                    nocodeText=W.nocode_text(doc.get("searches") or 0, doc.get("reads") or 0) + where)
    else:
        events = [e for e in (doc.get("events") or [])]
        v = steps_view(m, chain_id, events=events)
        v = upgrade(v, m, primary_name)
        own = {c["cell"] for c in doc["cells"]}
        v["checks"] = cites_checks(doc, own) + v["checks"]
        k = counts(doc)
        n_res = sum(1 for r in m["results"] if r.get("kind", "result") == "result")
        v["meta"] = W.meta_line(doc.get("mode") or "", k["turns"], k["cells"], k["figures_cell"], k["failed"], k["reviews"], n_res)
        v["title"] = report_title(doc)
        view = v
    view.update(path=path, pathTitles={c: titles.get(c, "") for c in path}, chain_id=chain_id,
                titles={c: titles.get(c, "") for c in sorted(set(path) | {str(x) for x in referenced_chains(view)})})
    return view


def referenced_chains(view):
    """Every chain id a view names: in its lanes, its checks, its step details and its texts."""
    ids = set()
    for i in view.get("inputs", []):
        for k in ("chain", "through"):
            if i.get(k):
                ids.add(str(i[k]))
    for c in view.get("checks", []):
        if c.get("chain"):
            ids.add(str(c["chain"]))
    for st in view.get("steps", {}).values():
        for t in st.get("takes_chain", []):
            if t.get("chain"):
                ids.add(str(t["chain"]))
    return ids


def self_check(view, m, doc):
    """Before storing (blueprint 4.13): RESULT records against results built per cell; a figure whose recipe has no data
    box while its cell reads data; a result or printout with an empty recipe. Each marks the view (`traced: false`)
    and is listed; nothing blocks the chain."""
    out = dict(results=[], figures=[], empty=[])
    built = defaultdict(int)
    for r in m["results"]:
        if r.get("kind", "result") == "result":
            built[r["cell"]] += 1
    for c in doc.get("cells") or []:
        kept = len(c.get("results") or [])
        if kept != built[c["cell"]] or (m.get("unpaired") or {}).get(c["cell"]):
            out["results"].append(dict(cell=c["cell"], records=kept, built=built[c["cell"]]))
            for rid, r in view.get("results", {}).items():
                if r["cell"] == c["cell"]:
                    r["traced"] = False
    reads = {c["cell"] for c in m.get("cells", []) if c.get("inputs") or c.get("reads_from")}
    for fid, rec in view.get("recipes", {}).items():
        empty = not rec.get("items")
        if fid.startswith("fig"):
            fig = view["figures"].get(fid) or {}
            if empty and not rec.get("inputs") and fig.get("cell") in reads:      # drawn straight off a dataset: traced
                out["figures"].append(fid)
                rec["traced"] = False
        elif empty and not rec.get("inputs"):           # a number read straight off a dataset has an input, no box
            out["empty"].append(fid)
            rec["traced"] = False
    return out
