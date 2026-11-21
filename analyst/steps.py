"""The steps of a brief's conversation (docs/ARCHITECT_DESIGN.md §2.25).

While a brief is written, what the person says or changes, with what the Pathfinder does in reply, is one step. A step
follows another, and more than one may follow the same step: the person went back and took another way. A framing
holds the conversation of one way - the way to the step in use: its turns, the passages its readings found, the
version of the brief that stands at its end - and, set aside, what the steps off that way hold:

    {"steps": [{"k": 1, "from": 0, "v": 2, "made": [1, 2], "turns": 1, "found": 0, "proposed": 0}, ...],
     "step": 3,                 the step in use: what is said or changed next follows it
     "tip": 5,                  the last step of the way being walked: the page's arrows go forward to it
     "aside": {"4": {"turns": [...], "found": [...]}, ...}}      what the steps off the way to the one in use hold

A step: its number, the step it follows (0: none), the version of the brief in use at its end, the versions it made,
how many turns and found passages are its own, and how many explanations the Pathfinder had proposed by its end.

take() counts what was added to a framing into a step: a new one where the person spoke or changed the brief by
hand, where the question was read before its analysis, or where the step in use has one after it - what was is not
changed; otherwise the step in use. go() puts another step in use: the framing then holds that step's way, and what
the others hold is set aside. So whoever reads a framing - the Pathfinder, the page, what is kept of a saved
analysis - reads one way and nothing of the others. A framing kept before steps is one way, a step to a version:
take() counts it so the first time it is touched.
"""
from __future__ import annotations

OPENERS = ("person", "reader")   # who a new step opens with: the person spoke, or pressed for the analysis and the question was read
LISTS = ("turns", "found")       # what a step holds of its own: its turns, and the passages its readings found


def _whole(n) -> bool:
    return isinstance(n, int) and not isinstance(n, bool)


def _in_use(framing: dict) -> int:
    """The number of the version of the brief in use: the one gone back to (`at`), else the last; 1 at least."""
    count = len(framing.get("versions") or [])
    at = framing.get("at")
    return at if _whole(at) and 1 <= at <= count else max(1, count)


def _by_version(framing: dict) -> list:
    """The steps of a framing kept before steps: one way, a step to a version. An exchange - the person's message,
    or the question's read, with what followed it - stands whole in one step: the one of the last version made by
    then. The passages found stand with the first reading."""
    count, turns = max(1, len(framing.get("versions") or [])), framing.get("turns") or []
    held, found_at, last, group = [0] * count, None, 1, []
    for i, t in enumerate(list(turns) + [None]):
        opens = t is None or t.get("who") == "version" or (t.get("who") in OPENERS and not (i and turns[i - 1].get("who") == "version"))
        if opens and group:
            last = max([last] + [min(count, x["v"]) for x in group if x.get("who") != "version" and _whole(x.get("v")) and x["v"] >= 1])
            held[last - 1] += len(group)
            found_at = last if found_at is None and any(x.get("who") == "memory" for x in group) else found_at
            group = []
        if t is not None:
            group.append(t)
    proposed = int(framing.get("proposed") or 0)
    return [{"k": n, "from": n - 1, "v": n, "made": [n], "turns": held[n - 1], "found": len(framing.get("found") or []) if n == (found_at or 1) else 0, "proposed": proposed}
            for n in range(1, count + 1)]


def way(steps: list, k: int) -> list:
    """The steps from the first to step `k`, in order: the way to it."""
    out = []
    while _whole(k) and 1 <= k <= len(steps) and len(out) < len(steps):
        out.append(steps[k - 1])
        k = steps[k - 1]["from"]
    return out[::-1]


def _end(steps: list, k: int) -> int:
    """Where the way from step `k` ends, taking at each step the newest of those that follow it."""
    while True:
        after = [s["k"] for s in steps if s["from"] == k]
        if not after:
            return k
        k = max(after)


def _counted(framing: dict) -> dict:
    """The framing with its steps, the one in use and the end of the way being walked said. One kept before steps
    gets them here: it held its whole conversation whichever version was in use, so its steps are counted with the
    last in use, and the step of the version it named is gone to."""
    if isinstance(framing.get("steps"), list) and framing["steps"]:
        return framing
    kept = _by_version(framing)
    return _to({**{key: value for key, value in framing.items() if key != "at"}, "steps": kept, "step": len(kept), "tip": len(kept)}, _in_use(framing))


def _held(framing: dict) -> dict:
    """What each step holds of its own, by its number: the steps on the way to the one in use from the framing's
    lists, cut by their counts, the others from what is set aside."""
    aside = framing.get("aside") or {}
    out = {s["k"]: {name: list((aside.get(str(s["k"])) or {}).get(name) or []) for name in LISTS} for s in framing["steps"]}
    at = dict.fromkeys(LISTS, 0)
    for s in way(framing["steps"], framing["step"]):
        out[s["k"]] = {name: list((framing.get(name) or [])[at[name]:at[name] + s[name]]) for name in LISTS}
        at = {name: at[name] + s[name] for name in LISTS}
    return out


def said(framing: dict) -> list:
    """Every turn a framing holds: those of the way to the step in use, then those set aside. What is counted over
    the whole brief - a call's number among its kind - is counted over these."""
    framing = framing if isinstance(framing, dict) else {}
    return list(framing.get("turns") or []) + [t for held in (framing.get("aside") or {}).values() for t in held.get("turns") or []]


def take(framing: dict) -> dict:
    """The framing with what was added to it since its steps were last counted taken into a step: the turns and
    found passages beyond those of the way to the step in use, the versions no step made, the version in use and
    the count of what the Pathfinder proposed. They are a new step - which follows the one in use, and is in use
    from then - where the first turn added is the person's or the question's read, where a version was made and
    nothing said (the person changed the brief by hand), or where the step in use has a step after it; otherwise
    they are the step in use's. A framing with nothing added is returned as it is."""
    framing = dict(framing or {})
    if not (isinstance(framing.get("steps"), list) and framing["steps"]):
        return _counted(framing)
    kept = [dict(s) for s in framing["steps"]]
    head = kept[framing["step"] - 1]
    path = way(kept, head["k"])
    added = {name: len(framing.get(name) or []) - sum(s[name] for s in path) for name in LISTS}
    first = (framing.get("turns") or [])[len(framing.get("turns") or []) - added["turns"]] if added["turns"] > 0 else None
    made = list(range(1 + max(n for s in kept for n in s["made"]), len(framing.get("versions") or []) + 1))
    now = {"v": _in_use(framing), "proposed": int(framing.get("proposed") or 0)}
    if not any(n > 0 for n in added.values()) and not made:
        return framing
    opens = (first is not None and first.get("who") in OPENERS) or (first is None and bool(made)) or any(s["from"] == head["k"] for s in kept)
    if opens:
        head = {"k": len(kept) + 1, "from": head["k"], "v": now["v"], "made": [], **dict.fromkeys(LISTS, 0), "proposed": now["proposed"]}
        kept.append(head)
    head.update({**now, "made": head["made"] + made, **{name: head[name] + added[name] for name in LISTS}})
    return {**framing, "steps": kept, "step": head["k"], "tip": head["k"]}      # a step that takes something in has none after it: its way ends on it


def _to(framing: dict, k: int) -> dict:
    """A framing whose steps are counted, with its step `k` in use (go())."""
    kept = framing["steps"]
    held, path = _held(framing), way(kept, k)
    on = [s["k"] for s in path]
    out = {key: value for key, value in framing.items() if key not in ("at", "aside")}
    out.update({"step": k, "tip": framing["tip"] if k in [s["k"] for s in way(kept, framing["tip"])] else _end(kept, k)})
    if path[-1]["proposed"] or "proposed" in framing:
        out["proposed"] = path[-1]["proposed"]
    for name in LISTS:
        mine = [x for n in on for x in held[n][name]]
        if mine or name in framing:
            out[name] = mine
    aside = {str(s["k"]): {name: held[s["k"]][name] for name in LISTS if held[s["k"]][name]} for s in kept if s["k"] not in on and any(held[s["k"]].values())}
    if aside:
        out["aside"] = aside
    if path[-1]["v"] != max(1, len(framing.get("versions") or [])):
        out["at"] = path[-1]["v"]
    return out


def go(framing: dict, k) -> dict:
    """The framing with step `k` in use: the person went to it, and what is said or changed next follows it. The
    framing then holds that step's way - its turns, the passages found on it, the count of what the Pathfinder had
    proposed by then, the version of the brief that stood at its end - and what the other steps hold is set aside.
    The way being walked ends where it did if the step is on it, else where the newest steps after `k` lead. What
    was added and not yet counted is taken into a step first; a step the framing does not have changes nothing."""
    framing = take(framing)
    return _to(framing, k) if _whole(k) and 1 <= k <= len(framing["steps"]) else framing
