"""The golden comparison's helpers (tests/analyst/test_code_map.py): the port's view against the prototype's expected
output. Also used to run the design package's coach chain locally, which is never committed."""
import copy
import re
import json  # noqa: F401

LAYOUT = {"x", "y", "w", "h", "segs", "heads"}
BUILT_DIFFERENTLY = {"id", "meta", "title", "pathTitles", "version", "chain_id", "titles", "sizes", "mapped", "traced", "pills", "built",
                     "reaches"}                           # the reach report (2026-10-28): from the kernel's record, which the prototype did not have


def as_numbers(obj):
    """The port's chain ids and {chain:<id>} tokens as the fixtures' numbers (the fixtures' chain ids are their numbers)."""
    if isinstance(obj, dict):
        return {k: as_numbers(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [as_numbers(v) for v in obj]
    if isinstance(obj, str):
        s = re.sub(r"\{chain:(\w+)\}", r"chain \1", obj)
        s = re.sub(r"^in:chain:(\w+)$", r"in:From chain \1", s)
        return s
    return obj


def comparable(view):
    """A view without the fields the comparison leaves out, chain references as numbers, diagrams as nodes and edges."""
    v = copy.deepcopy(view)
    for k in list(v):
        if k in BUILT_DIFFERENTLY:
            v.pop(k)
    v["path"] = [int(x) if str(x).isdigit() else x for x in v.get("path", [])]
    for i in v.get("inputs", []):
        for k in ("chain", "through"):
            if i.get(k) is not None and str(i[k]).isdigit():
                i[k] = int(i[k])
    for st in v.get("steps", {}).values():
        for t in st.get("takes_chain", []):
            if str(t.get("chain")).isdigit():
                t["chain"] = int(t["chain"])
    for c in v.get("checks", []):
        if c.get("chain") is not None and str(c["chain"]).isdigit():
            c["chain"] = int(c["chain"])
    for d in v.get("diagrams", {}).values():
        for k in LAYOUT:
            d.pop(k, None)
        d["nodes"] = [{k: x for k, x in n.items() if k not in LAYOUT} for n in d["nodes"]]
        for n in d["nodes"]:
            if isinstance(n.get("step"), str):
                n["step"] = n["step"][:120]                   # the port keeps 200 characters of a box's step, the prototype 120
        d["edges"] = [list(e) for e in d["edges"]]
    for r in v.get("rows", []):
        r.pop("mapped", None); r.pop("reach", None); r.pop("refused", None)      # the reach report's row fields (2026-10-28)
        if r.get("type") == "step" and not r.get("figures"):
            r["purpose"] = str(r.get("purpose", ""))[:120]   # the port keeps 320 characters of a step's sentence, the prototype 140
    for st in v.get("steps", {}).values():
        if st.get("role") != "figures":
            st["purpose"] = str(st.get("purpose", ""))[:120]
    for r in v.get("results", {}).values():
        if r.get("kind", "result") == "result" and isinstance(r.get("short"), str):
            r["short"] = r["short"][:50]                      # the port keeps 96 characters of a short label, the prototype 58
        r.pop("traced", None)
    for r in v.get("recipes", {}).values():
        r.pop("traced", None); r.pop("lines", None); r.pop("own", None)    # the lines behind a number (2026-10-24), which the prototype did not keep
    return as_numbers(v)


def drop_colliding_shorts(got, want):
    """The port tells results that share a short label apart (view.distinct_shorts, 2026-10-20); the prototype left them
    identical. Where the prototype's view has such a collision, the short labels concerned are left out of the comparison."""
    from collections import Counter
    counts = Counter(r.get("short") for r in (want.get("results") or {}).values() if r.get("kind", "result") == "result")
    for rid, r in (want.get("results") or {}).items():
        if counts[r.get("short")] > 1:
            r.pop("short", None)
            if rid in (got.get("results") or {}):
                got["results"][rid].pop("short", None)
    return got, want


def first_difference(a, b, path="view"):
    """Where two JSON trees first differ, for the report."""
    if type(a) != type(b):
        return f"{path}: {type(a).__name__} vs {type(b).__name__}: {str(a)[:80]!r} vs {str(b)[:80]!r}"
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                return f"{path}.{k}: missing in the port"
            if k not in b:
                return f"{path}.{k}: not in the fixture ({str(a[k])[:80]!r})"
            d = first_difference(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return ""
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: {len(a)} vs {len(b)} items; first extra: {str((a if len(a) > len(b) else b)[min(len(a), len(b))])[:120]!r}"
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_difference(x, y, f"{path}[{i}]")
            if d:
                return d
        return ""
    return "" if a == b else f"{path}: {str(a)[:120]!r} vs {str(b)[:120]!r}"


def with_ids(doc):
    """A fixture ChainRecord with its chain numbers as chain ids, as the port expects (section 3 of the blueprint)."""
    d = copy.deepcopy(doc)
    d["chain_id"] = str(d.get("chain") or 1)
    d["path"] = [str(x) for x in d.get("path") or [d["chain_id"]]]
    d["path_cells"] = {str(k): str(v) for k, v in (d.get("path_cells") or {}).items()}
    if d.get("earlier"):
        for n, e in (d["earlier"].get("names") or {}).items():
            e["chain_id"] = str(e.pop("chain", e.get("chain_id")))
    return d


def strip_lines(doc):
    d = copy.deepcopy(doc)
    for c in d["cells"]:
        for k in c.get("results") or []:
            k.pop("line", None)
    return d


MAPS = {"trial": "expected/trial_map.json", "trial2": "expected/trial2_map.json", "sim1": "expected/sim1_map.json",
        "t1": "expected/thread5/chain1_map.json", "t2": "expected/thread5/chain2_map.json", "t3": "expected/thread5/chain3_map.json",
        "t4": "expected/thread5/chain4_map.json"}


def norm_map(m):
    """A map as the prototype dumped it: sets sorted, chain ids as numbers, nothing else."""
    def fix(o):
        if isinstance(o, dict):
            return {k: fix(v) for k, v in o.items()}
        if isinstance(o, list):
            return [fix(v) for v in o]
        if isinstance(o, (set, frozenset)):
            return sorted(o)
        if isinstance(o, str):
            o = re.sub(r"\{chain:(\w+)\}", r"chain \1", o)
            return re.sub(r"^chain:(\w+)$", r"chain\1", o)       # a kernel source keyed by chain id
        return o
    m = fix(json.loads(json.dumps(m, default=lambda o: sorted(o) if isinstance(o, set) else str(o))))
    for o in m.get("objects", []):
        o["via"] = {k: (int(v) if str(v).isdigit() else v) for k, v in (o.get("via") or {}).items()}
    if str(m.get("chain", "")).isdigit():
        m["chain"] = int(m["chain"])
    for i in m.get("inputs", []):
        for k in ("chain", "through"):
            if i.get(k) is not None and str(i[k]).isdigit():
                i[k] = int(i[k])
    for c in m.get("cells", []):
        for t in c.get("taken", []):
            if str(t.get("chain")).isdigit():
                t["chain"] = int(t["chain"])
    m.pop("unparsed", None); m.pop("unpaired", None)
    for o in m.get("objects", []):
        o.pop("code_lines", None)    # the object's lines (2026-10-24), which the prototype did not keep
    for r in m.get("results", []):
        r.pop("code_lines", None); r.pop("own_lines", None)
    for c in m.get("cells", []):
        c.pop("mapped", None)
        if c.get("kind") != "figures":
            c["purpose"] = str(c.get("purpose", ""))[:120]   # the port keeps 320 characters of a step's sentence, the prototype 140
    for i in m.get("inputs", []):
        i.pop("loaded", None)        # the port also counts a cell whose print or RESULT read the input itself (the rule test)
        i.pop("name", None)          # the record's own name for a document (decision 7), carried through the map
    return m
