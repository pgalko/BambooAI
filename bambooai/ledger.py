"""
ledger.py — reading an investigation's navigation state for the outer loop.

auto_explore used to decide what to ask next from a prose "research model" that
a separate LLM call rewrote every round from the winning solution's TEXT ANSWER.
Two problems with that. A whole-document rewrite from a summary is lossy, and
applied each round the detail decays rather than accumulates. And what it was
reconstructing — biggest gap, contradictions, weak points — is what the
Investigator already recorded, structured, while it had the actual results in
front of it.

This reads that record instead. Nothing here calls a model.

    candidates(nav)   what is worth asking next, ranked
    blocked(nav)      directions already ruled out, with the reason
    deltas(a, b)      what opened and closed between two rounds

WHAT THE LEDGER IS AND IS NOT

It holds framings of ONE question — the estimand that chain was given. So it is
a good source for going DEEPER and a poor one for going WIDER: nothing in it
will ever say "you have only looked at two of forty columns". Breadth still
comes from the schema and the exploration tree, which is why the prose path
survives for MAPPING even though it is replaced everywhere else.

Accepts a NavState object or the dict form it persists as, because the state
arrives as an object within a run and as a dict after a restart.
"""

import logging

logger = logging.getLogger(__name__)

# Ranked by how directly the Investigator pointed at them. An in_progress
# framing is a thread it opened and did not finish, which beats anything it
# never started.
_RANK = [
    ("frontier", "in_progress", "unfinished thread"),
    ("frontier", "untested", "untested framing"),
    ("regimes", "not_examined", "unexamined regime"),
    ("risks", "open", "open risk"),
    ("breakdown", "thin", "underpowered result"),
    ("regimes", "partial", "partly examined regime"),
]

# Statuses that mean "do not go here again".
_CLOSED = {
    "frontier": {"foreclosed", "blocked"},
    "regimes": {"blocked"},
    "risks": {"blocked"},
    "breakdown": {"blocked"},
}


def _as_dict(nav):
    """A NavState, its dict form, or None -> a dict (possibly empty)."""
    if nav is None:
        return {}
    if isinstance(nav, dict):
        return nav
    to_dict = getattr(nav, "to_dict", None)
    if callable(to_dict):
        try:
            return to_dict()
        except Exception as exc:                                # noqa: BLE001
            logger.warning("Could not read the ledger: %s", exc)
    return {}


def _entries(nav, collection):
    out = []
    for e in (_as_dict(nav).get(collection) or []):
        if isinstance(e, dict) and e.get("label"):
            out.append(e)
    return out


def estimand(nav):
    """What that investigation was measuring, if it recorded one."""
    return _as_dict(nav).get("target_estimand") or None


def candidates(nav, limit=8):
    """What is worth asking next, most pointed first.

    Each entry is {label, kind, status, why, reason} — `reason` being why it is
    a candidate at all, which is what a question generator needs in order to
    turn a terse handle like "pace band for HR response" into a question.
    """
    out, seen = [], set()
    for collection, status, reason in _RANK:
        for e in _entries(nav, collection):
            if e.get("status") != status:
                continue
            label = e["label"]
            if label in seen:
                continue
            seen.add(label)
            out.append({
                "label": label,
                "kind": collection,
                "status": status,
                "why": e.get("why") or "",
                "reason": reason,
            })
            if len(out) >= limit:
                return out
    return out


def blocked(nav, limit=10):
    """Directions already ruled out, with the reason where one was recorded.

    Worth as much as the candidates. Nothing in the outer loop's prose context
    said which directions were dead, so it could spend a whole chain
    rediscovering that within-session altitude slopes measure terrain rather
    than hypoxia — which one chain had already established and written down.
    """
    out = []
    for collection, statuses in _CLOSED.items():
        for e in _entries(nav, collection):
            if e.get("status") in statuses:
                out.append({"label": e["label"], "kind": collection,
                            "status": e["status"], "why": e.get("why") or ""})
                if len(out) >= limit:
                    return out
    return out


def deltas(before, after):
    """What changed between two rounds.

    The phase machine asked a model whether its understanding had shifted. This
    counts it instead: an investigation that closed nothing and opened nothing
    has converged, whatever anyone thinks. Returns
    {opened, closed, still_open, moved} — `moved` being the total, which is the
    number that answers "is this still going anywhere".
    """
    def _index(nav):
        idx = {}
        for coll in ("frontier", "regimes", "risks", "breakdown"):
            for e in _entries(nav, coll):
                idx[(coll, e["label"])] = e.get("status")
        return idx

    a, b = _index(before), _index(after)
    opened = [k for k in b if k not in a]
    closed = [k for k in a
              if k in b and a[k] != b[k] and b[k] in _CLOSED.get(k[0], set())]
    changed = [k for k in a if k in b and a[k] != b[k]]
    still_open = [k for k in b
                  if b[k] not in _CLOSED.get(k[0], set())
                  and b[k] not in ("tested", "examined", "resolved")]
    return {
        "opened": len(opened),
        "closed": len(closed),
        "changed": len(changed),
        "still_open": len(still_open),
        "moved": len(opened) + len(changed),
    }


def render(nav, limit=8):
    """The candidates and the blocked list as prompt text.

    Deliberately terse: these are handles the Investigator wrote for itself, and
    padding them out would invent detail it did not record.
    """
    lines = []
    cands = candidates(nav, limit=limit)
    if cands:
        lines.append("UNEXPLORED, from the investigation's own record "
                     "(most pointed first):")
        for c in cands:
            why = f" — {c['why']}" if c["why"] else ""
            lines.append(f"  - [{c['reason']}] {c['label']}{why}")
    blocks = blocked(nav)
    if blocks:
        lines.append("")
        lines.append("ALREADY RULED OUT — do not propose these again:")
        for b in blocks:
            why = f" — {b['why']}" if b["why"] else ""
            lines.append(f"  - {b['label']}{why}")
    return "\n".join(lines)