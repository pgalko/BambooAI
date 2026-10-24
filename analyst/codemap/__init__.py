"""The code map (docs/CODEMAP_DESIGN.md, 2026-10-20): how one analysis chain got from its data to its numbers, built
mechanically from the chain's committed cells and the kernel's record, once when the chain ends, and shown in a modal.
No model call anywhere; the same chain always gives the same map. Nothing here reaches a prompt.

    build(nb, run, inputs, context)  -> {version, built, ms, view, exports, selfcheck, inputs} | {version, built, error, inputs}
    build_record(record)             -> the same from a ChainRecord (tests, the route's on-demand build)

A failure is recorded, never raised: the chain is answered whether or not it has a map."""
import copy
import time

VERSION = 3      # 3 (2026-10-24): each recipe carries the lines behind its number, for the notebook; 2 (2026-10-21): short labels told apart, longer texts; older maps are rebuilt on request


def build_record(doc, primary_name=None):
    """The map of one ChainRecord (blueprint section 3): the view, the exports for later chains, the self-checks, and
    the intermediate map (not stored: tests compare it with the prototype's)."""
    from . import objects as O
    from . import view as VW
    t0 = time.perf_counter()
    m = O.build_map(doc)
    name = primary_name or next((i.get("name") for i in doc.get("inputs", []) if i.get("kind") == "primary" and i.get("name")), None) or "primary dataset"
    view = VW.build_view(copy.deepcopy(m), doc, name)        # the view annotates the objects it labels; the map stays as built
    view["version"] = VERSION
    boxes = any(o["kind"] in ("table", "estimate") or o.get("shape") for o in m["objects"])
    has_registry = bool(doc.get("registry_start")) or any(c.get("registry") for c in doc.get("cells") or [])
    if doc.get("cells") and boxes and not has_registry and any(o["names"] for o in m["objects"]):
        view["sizes"] = False                             # an old run: no registry anywhere, so the panel says sizes not recorded
    selfcheck = VW.self_check(view, m, doc)
    return dict(version=VERSION, built=time.time(), ms=round((time.perf_counter() - t0) * 1000), view=view,
                exports=O.exports(m, doc.get("chain_id")), selfcheck=selfcheck, inputs=list(doc.get("inputs") or []), map=m)


def build(nb, run, inputs=None, context=False, ancestors=None):
    """The map of a Run at its end, stored on the Run (7.3). `inputs` is the host's list of what the chain was offered
    (7.6); `ancestors` maps an earlier chain id to its exports (the route passes memoised ones for old runs without a
    map). Never raises."""
    t0 = time.time()
    try:
        from . import record as R
        earlier, registry_start = earlier_of(nb, run, ancestors or {})
        doc = R.chain_record(nb, run, inputs=inputs, context=context, earlier=earlier, registry_start=registry_start)
        out = build_record(doc)
        out.pop("map", None)
        return out
    except Exception as exc:                              # noqa: BLE001 - a map failure never breaks a chain
        return dict(version=VERSION, built=t0, error=" ".join(str(exc).split())[:300], inputs=list(inputs or []))


def earlier_of(nb, run, ancestors):
    """The merged exports of the earlier runs on the computed path (root first, a later chain overriding an earlier
    one), and the registry the kernel held when this chain began: the earlier cells' entries merged in order."""
    names, funcs, registry = {}, {}, {}
    if nb is None:
        return dict(names=names, funcs=funcs), registry
    for r in nb.computed_runs(run.id)[:-1]:
        ex = ancestors.get(r.id) or ((r.code_map or {}).get("exports") if isinstance(getattr(r, "code_map", None), dict) else None) or {}
        names.update(ex.get("names") or {})
        funcs.update(ex.get("funcs") or {})
        for t in r.cells():
            registry.update(getattr(t, "registry", {}) or {})
    return dict(names=names, funcs=funcs), registry
