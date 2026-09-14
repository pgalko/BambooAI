"""
The memory pack: one YAML file of method cards as the app's long-term memory.

This is the successor to both the OWL ontology (retired, step 21) and the
retired QA-pair store (gone since step 23). The file is the SOURCE OF TRUTH -
human-readable, versionable, patchable by the same SEARCH/REPLACE edit-block
machinery the Error Corrector uses - and everything else here (the hook
index, retrieval ranking) is derived from it and rebuilt on load. Contract:
memory_pack_design.md at the repo root.

A card is one method: what question it answers, when to reach for it, the
formula or procedure, what it assumes, and where it breaks. Cards carry a
status - candidate (unproven), established (user-approved), vetted (ships a
tested implementation callable in the kernel) - and an evidence trail of the
chains that earned them their standing. Reads here are PURE: nothing on the
read path writes counters or mutates the file; use tracking belongs to the
post-synthesis write pass (step 23).

Retrieval embeds each card's hooks (answers_question + use_when) with the
same embedding client the QA machinery used; when no embedder is available
the ranking falls back to deterministic lexical overlap, so the system
degrades gracefully rather than binarily. Established/vetted cards get a
small score bonus: authority outranks similarity at the margin, by design.
"""

import copy
import json
import logging
import math
import os
import re
from datetime import date, datetime

import yaml

logger = logging.getLogger(__name__)

MEMORY_PREFIX = "memory:"
DECAY_DAYS = 180
PROMOTION_THRESHOLD = 3

_STATUSES = ("candidate", "established", "vetted")
STATUS_BONUS = {"vetted": 0.10, "established": 0.08, "candidate": 0.0}

_REQUIRED = (
    ("name",), ("status",),
    ("hooks", "answers_question"), ("hooks", "use_when"),
    ("body", "function_definition"), ("body", "assumes"),
    ("body", "limitations"),
)

_RELATION_KEYS = ("requires", "depends_on", "produces",
                  "alternative_to", "complemented_by")


# ── loading ────────────────────────────────────────────────────────────────

def _parse_date(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _get(card, path):
    node = card
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return None
        node = node[key]
    return node


def _last_activity(card):
    """The most recent date the card was touched: creation, last use, or the
    latest evidence reinforcement. Drives candidate decay."""
    dates = [_parse_date(_get(card, ("provenance", "created"))),
             _parse_date(card.get("last_used"))]
    for ev in card.get("evidence") or []:
        if isinstance(ev, dict):
            dates.append(_parse_date(ev.get("reinforced_at")))
    dates = [d for d in dates if d]
    return max(dates) if dates else None


def load_pack(path, now=None):
    """Load and validate a pack. Returns (pack, report).

    Invalid cards are rejected INDIVIDUALLY with a legible message while the
    rest of the pack loads; unknown relation names warn but keep the card.
    A missing or unreadable file loads as an empty pack - cold start is
    silent, and a broken pack must never end a run. Candidates whose last
    activity predates DECAY_DAYS are flagged `_decayed` (an internal,
    non-persisted mark): they leave the index but stay reachable by exact
    name until the maintenance pass prunes them (step 24).
    """
    report = {"errors": [], "warnings": []}
    empty = {"version": 1, "cards": []}
    if not path:
        return empty, report
    try:
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except FileNotFoundError:
        return empty, report
    except Exception as exc:                                    # noqa: BLE001
        report["errors"].append(f"pack unreadable: {exc}")
        return empty, report
    if raw is None:
        # A deliberately blanked pack is a cold start, not a malformed one.
        return empty, report
    if not isinstance(raw, dict) or not isinstance(raw.get("cards"), list):
        report["errors"].append("pack has no cards: list")
        return empty, report

    today = _parse_date(now) or date.today()
    cards, seen = [], set()
    for card in raw["cards"]:
        if not isinstance(card, dict):
            report["errors"].append("non-mapping card rejected")
            continue
        name = card.get("name") or "(unnamed)"
        missing = [".".join(p) for p in _REQUIRED if not _get(card, p)]
        if missing:
            report["errors"].append(
                f"card '{name}' rejected: missing {', '.join(missing)}")
            continue
        if card["status"] not in _STATUSES:
            report["errors"].append(
                f"card '{name}' rejected: status '{card['status']}' is not "
                f"one of {'/'.join(_STATUSES)}")
            continue
        if name in seen:
            report["errors"].append(f"card '{name}' rejected: duplicate name")
            continue
        seen.add(name)
        cards.append(card)

    names = {c["name"] for c in cards}
    for card in cards:
        relations = card.get("relations") or {}
        for key in _RELATION_KEYS:
            for ref in relations.get(key) or []:
                if ref not in names:
                    report["warnings"].append(
                        f"card '{card['name']}' {key} references unknown "
                        f"'{ref}'")
        if card["status"] == "candidate":
            last = _last_activity(card)
            if last and (today - last).days > DECAY_DAYS:
                card["_decayed"] = True

    return {"version": raw.get("version", 1), "cards": cards}, report


def save_pack(pack, path):
    """Write a pack back to disk. Internal (underscore-prefixed) marks are
    stripped; the file stays the clean source of truth."""
    clean = copy.deepcopy(pack)
    for card in clean.get("cards", []):
        for key in [k for k in card if str(k).startswith("_")]:
            del card[key]
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        yaml.safe_dump(clean, fh, sort_keys=False, allow_unicode=True)
    os.replace(tmp, path)


# ── retrieval ──────────────────────────────────────────────────────────────

_EMBEDDER = ["unset"]


def _get_embedder():
    """The QA machinery's embedding client, imported lazily. Any failure -
    missing key, missing library - yields None and the lexical fallback:
    the system degrades gracefully, never binarily."""
    if _EMBEDDER[0] != "unset":
        return _EMBEDDER[0]
    try:
        from bambooai.embeddings import build_embedding_client
        client = build_embedding_client()
    except Exception:                                           # noqa: BLE001
        client = None
    _EMBEDDER[0] = client
    return client


def _tokens(text):
    return set(re.findall(r"[a-z0-9]+", (text or "").lower()))


def _hooks_text(card):
    hooks = card.get("hooks") or {}
    return f"{hooks.get('answers_question', '')} {hooks.get('use_when', '')}"


def _cosine(a, b):
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(y * y for y in b))
    return num / (da * db) if da and db else 0.0


def _lexical_scores(seed, cards):
    """Deterministic lexical cosine over token sets, in [0, 1]. The PUSH
    relevance GATE runs on this always: embedding cosines between
    unrelated technical sentences routinely sit at 0.3-0.7, so an
    absolute floor is meaningless there (2026-08-14: the cycling pack
    vs a Lorenz seed scores 0.089-0.138 lexically - blockable - while
    a cosine backend would have sailed it through)."""
    st = _tokens(seed)
    out = []
    for card in cards:
        ht = _tokens(_hooks_text(card))
        inter = len(st & ht)
        out.append(inter / math.sqrt(len(st) * len(ht))
                   if inter and st and ht else 0.0)
    return out


def _embedding_scores(seed, cards):
    """Embedding cosine per card, or None when no client / on failure.
    ABSOLUTE values are uncalibratable (unrelated technical sentences
    sit at 0.3-0.7), but DIFFERENCES are trustworthy - the inflated
    baseline is common-mode and cancels within one pack."""
    client = _get_embedder()
    if client is None:
        return None
    try:
        vecs = [client.vectorize(t) for t in
                [seed] + [_hooks_text(c) for c in cards]]
        return [_cosine(vecs[0], v) for v in vecs[1:]]
    except Exception:                                           # noqa: BLE001
        return None


def _push_embedding_geometry(seed, cards):
    """For the PUSH gate only: (per-card cosine to the seed, AMBIENT),
    or None when no client / on failure. AMBIENT is the median pairwise
    cosine among the pack's own hook vectors - the room's background
    hum, computed from the same vectors (zero extra calls). A card must
    beat the hum, not merely the other strangers: the median-of-others
    test admitted the LEAST-irrelevant card on off-topic seeds
    (2026-08-14, the recurring gradient card on Lorenz questions)."""
    client = _get_embedder()
    if client is None:
        return None
    try:
        vecs = [client.vectorize(t) for t in
                [seed] + [_hooks_text(c) for c in cards]]
        scores = [_cosine(vecs[0], v) for v in vecs[1:]]
        hooks = vecs[1:]
        pairs = [_cosine(hooks[i], hooks[j])
                 for i in range(len(hooks))
                 for j in range(i + 1, len(hooks))]
        ambient = sorted(pairs)[len(pairs) // 2] if pairs else None
        return scores, ambient
    except Exception:                                           # noqa: BLE001
        return None


def _scores(seed, cards):
    """Similarity of the seed to each card's hooks, in [0, 1]-ish. Embedding
    cosine when a client is available; deterministic lexical cosine over
    token sets otherwise."""
    emb = _embedding_scores(seed, cards)
    return emb if emb is not None else _lexical_scores(seed, cards)


def _ranked(cards, seed):
    scores = _scores(seed, cards) if seed else [0.0] * len(cards)
    pairs = [(s + STATUS_BONUS.get(c["status"], 0.0), c)
             for s, c in zip(scores, cards)]
    pairs.sort(key=lambda p: -p[0])
    return [c for _, c in pairs]


def retrieve(path, seed, top_k=12, now=None):
    """Names of the top-k non-decayed cards for a seed question."""
    pack, _ = load_pack(path, now=now)
    live = [c for c in pack["cards"] if not c.get("_decayed")]
    return [c["name"] for c in _ranked(live, seed)[:top_k]]


# ── the index (schema-slot text) ───────────────────────────────────────────

_INDEX_INSTRUCTIONS = f"""MEMORY (methods this workspace has learned)

What follows is an INDEX of the memory pack: method names with the question
each answers. Full definitions - the formula, its inputs, what it assumes
and where it breaks - are fetched on demand: issue a SEARCH whose query
begins with `{MEMORY_PREFIX}` followed by card names (comma separated), or a
plain question to match by meaning. For example:

    {MEMORY_PREFIX} card_name_from_the_index, another_card_name
    {MEMORY_PREFIX} methods for zero-inflated series

(Replace with REAL names from the index below - never copy these
placeholders. Request only the cards whose hook matches your need;
one is usual.)

The definitions come back as evidence, exactly as a web search would, and
stay in the record for the rest of the run. Do not guess a formula memory
defines - look it up. Entries marked [candidate] are UNVERIFIED: they have
been used but not yet approved by the user; weigh them accordingly.
The user's explicit instruction in the CURRENT question always outranks
memory: if they name a method or approach, use theirs, leave conflicting
cards aside, and note the divergence rather than silently overriding it.
"""


def _index_line(card):
    hooks = card.get("hooks") or {}
    q = str(hooks.get("answers_question", "")).strip()
    if len(q) > 88:
        q = q[:85] + "..."
    line = f"- {card['name']} — {q}"
    if card["status"] == "vetted":
        line += " (callable)"
    elif card["status"] == "candidate":
        line += f" [candidate, used {int(card.get('use_count') or 0)}x]"
    return line


def memory_index(path, seed=None, top_k=12, max_chars=4000, now=None):
    """The pack as schema-slot text: instructions + a status-grouped roster
    of hooks. With a seed, the roster is relevance-ranked; without one,
    established-first. Empty or missing pack => "" (cold start is silent).
    Never raises."""
    try:
        pack, _ = load_pack(path, now=now)
        live = [c for c in pack["cards"] if not c.get("_decayed")]
        if not live:
            return ""
        chosen = _ranked(live, seed)[:top_k]
        groups = {"vetted": [], "established": [], "candidate": []}
        for card in chosen:
            groups[card["status"]].append(_index_line(card))
        parts = [_INDEX_INSTRUCTIONS]
        if groups["vetted"]:
            parts.append("VETTED (tested implementations, callable):")
            parts.extend(groups["vetted"])
        if groups["established"]:
            parts.append("ESTABLISHED:")
            parts.extend(groups["established"])
        if groups["candidate"]:
            parts.append("CANDIDATES (unverified):")
            parts.extend(groups["candidate"])
        if len(live) > len(chosen):
            parts.append(f"...and {len(live) - len(chosen)} more - match by "
                         f"meaning with `{MEMORY_PREFIX} <your question>`.")
        text = "\n".join(parts)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n# ... index truncated\n"
        return text
    except Exception as exc:                                    # noqa: BLE001
        logger.warning("Could not build memory index from %s: %s", path, exc)
        return ""


_CARDS_HEADER = """MEMORY — methods this workspace has learned.
Established and vetted entries below are trusted house conventions: follow
them over textbook defaults whenever they apply. Entries with status
`candidate` are UNVERIFIED — weigh them accordingly. Where an
`implementation` is provided it is tested code: reuse it rather than
rewriting. The user's explicit instruction in the current question always
outranks memory: if they name a method, use theirs and note the
divergence.

"""


def memory_cards_for_prompt(path, seed, top_k=3, max_chars=6000, now=None):
    """The PUSH path (quick mode): the top-k cards rendered WHOLE - formula,
    assumptions, limitations, and tested implementations - for injection
    into a one-shot prompt that has no second hop to pull with. Empty or
    missing memory returns "" so the prompt stays perfectly silent.
    Never raises."""
    if not path or not seed:
        return ""
    try:
        pack, _ = load_pack(path, now=now)
        live = [c for c in pack["cards"] if not c.get("_decayed")]
        if not live:
            return ""
        # TWO-DOOR GATE: shared vocabulary (lexical floor, backend-
        # proof) OR a clear standout above the pack's own embedding
        # baseline for this seed. A single-card pack has no crowd to
        # stand out from - that residual stays lexical-only, pinned.
        raw = _lexical_scores(seed, live)
        geo = _push_embedding_geometry(seed, live)

        def _passes(i):
            if raw[i] >= PUSH_MATCH_MIN:
                return True
            if geo is not None:
                scores, ambient = geo
                if ambient is not None:
                    return scores[i] - ambient >= PUSH_STANDOUT_MARGIN
            return False

        keep = [c for i, c in enumerate(live) if _passes(i)]
        if not keep:
            logger.info("Memory push: no card clears the relevance floor "
                        "(%.2f); the prompt stays silent", PUSH_MATCH_MIN)
            return ""
        chosen = _ranked(keep, seed)[:top_k]
        logger.info("Memory push: %d cards into quick prompt (%s)",
                    len(chosen), ", ".join(c["name"] for c in chosen))
        text = _CARDS_HEADER + "\n".join(_render_card(c) for c in chosen)
        if len(text) > max_chars:
            text = text[:max_chars] + "\n# ... truncated\n"
        return text
    except Exception as exc:                                    # noqa: BLE001
        logger.warning("memory_cards_for_prompt failed: %s", exc)
        return ""


# ── the write pass (step 24) ───────────────────────────────────────────────

CAP_CARDS = 60          # implementation constant; the spec is silent - a
                        # pack past this size needs curation, not appends.
NEAR_DUP_REFUSE = 0.80   # hook-cosine at/above: covers existing ground
NEAR_DUP_NOTE = 0.60     # gray zone: append, but flag for the review
SEMANTIC_MATCH_MIN = 0.25  # meaning-match floor: below this, report
                           # "nothing matches" rather than surface an
                           # unrelated card (proven live, chain ...999).
try:
    PUSH_STANDOUT_MARGIN = float(os.getenv("BAMBOO_PUSH_STANDOUT_MARGIN",
                                           "0.10"))
except ValueError:
    # A malformed env value must degrade to the default, never crash
    # module import - this constant is read at import time and the
    # module serves BOTH modes (deep index/retrieval included).
    PUSH_STANDOUT_MARGIN = 0.10
                           # the SECOND door: a card passes with zero
                           # shared vocabulary iff its cosine to the
                           # seed beats the pack's AMBIENT (median
                           # pairwise hook similarity) by this margin.
                           # Anchoring on ambient - not on the other
                           # cards' median - is what stops the
                           # LEAST-irrelevant card from winning on
                           # off-topic seeds (the recurring gradient
                           # card, 2026-08-14). Differences on the
                           # cosine scale are trustworthy where
                           # absolutes are not; 0.10 is the codebase's
                           # meaningful-nudge unit (STATUS_BONUS max),
                           # and the env var is the ops-tuning knob.
PUSH_MATCH_MIN = SEMANTIC_MATCH_MIN  # one policy: the quick PUSH shares
                           # the search floor. 2026-08-14: a Lorenz
                           # question received three cycling cards -
                           # STATUS_BONUS (max 0.10) outranked silence
                           # because the push had no floor at all.
MAX_CARDS_PER_KEEP = 3  # a genuinely multifaceted kept chain may card
                        # several distinct methods; beyond this, curation.
REINFORCE_RANK_MIN = 5  # the UI's own contract: the rating bar (1-10)
                        # marks 5+ as "also adds to your private BambooAI
                        # memory". Below it: favorites only, memory
                        # untouched - the bar is the consent dial.
PROMOTION_THRESHOLD = 3  # reinforcements in DISTINCT chains before the
                         # promotion review is offered (step 26).
_EVIDENCE_KEEP = 12     # evidence entries kept per card (newest last)


def _snake(name):
    out = re.sub(r"[^a-z0-9_]+", "_", str(name).strip().lower())
    return re.sub(r"_+", "_", out).strip("_") or "unnamed_method"


def _card_field_errors(card):
    """The loader's per-card checks, shared with the write pass so a card
    is judged identically at birth and at load."""
    if not isinstance(card, dict):
        return ["not a mapping"]
    missing = [".".join(pth) for pth in _REQUIRED if not _get(card, pth)]
    if missing:
        return [f"missing {', '.join(missing)}"]
    if card["status"] not in _STATUSES:
        return [f"status '{card['status']}' is not one of "
                f"{'/'.join(_STATUSES)}"]
    return []


def _hook_tokens(text):
    return {t for t in re.findall(r"[a-z0-9]+", str(text).lower())
            if len(t) > 3}


def cards_from_distiller_output(text, *, chain_id, question, now=None,
                                existing_cards=None):
    """Parse the Distiller's draft into a LIST of validated CANDIDATE
    cards (a multifaceted kept chain may teach several distinct methods),
    capped at MAX_CARDS_PER_KEEP, or ([], reason). Server-side coercions
    per card are non-negotiable: status forced to candidate,
    implementation stripped (vetted only, per spec), provenance and
    counters set here - the model drafts, it does not certify. Never
    raises."""
    try:
        if not text or "NO_CARD" in text.upper()[:2000] and "```" not in text:
            return [], "no card (the pass's most common correct output)"
        m = re.search(r"```(?:yaml)?\s*\n(.*?)```", text, re.DOTALL)
        raw = m.group(1) if m else text
        data = yaml.safe_load(raw)
        if isinstance(data, dict) and isinstance(data.get("cards"), list):
            drafts = [d for d in data["cards"] if isinstance(d, dict)]
        elif isinstance(data, dict):
            drafts = [data]
        else:
            return [], "draft is not a card mapping"
        if not drafts:
            return [], "draft is not a card mapping"
        out, reasons = [], []
        known = list(existing_cards or [])
        for data in drafts[:MAX_CARDS_PER_KEEP]:
            card, why = _coerce_one_draft(data, chain_id=chain_id,
                                          question=question, now=now)
            if not card:
                reasons.append(why)
                continue
            # Near-duplicate check by hook COSINE (the retrieval metric),
            # two-banded. Raw token overlap ate a legitimate MMP-20 card
            # live: same-domain hooks always share generic tokens
            # (power/ride/data), so counting them strangles births.
            # Refuse only genuine coverage; flag the gray zone for the
            # promotion review instead.
            seed_text = _hooks_text(card)
            if known:
                sims = _scores(seed_text, known)
                worst = max(range(len(sims)), key=lambda i: sims[i])
                if sims[worst] >= NEAR_DUP_REFUSE:
                    reasons.append(f"covers existing card "
                                   f"'{known[worst].get('name', '?')}'")
                    continue
                if sims[worst] >= NEAR_DUP_NOTE:
                    card["provenance"]["note"] += (
                        f"; near '{known[worst].get('name', '?')}' - "
                        f"review overlap at promotion")
            known.append(card)
            out.append(card)
        if len(drafts) > MAX_CARDS_PER_KEEP:
            reasons.append(f"{len(drafts) - MAX_CARDS_PER_KEEP} drafts over "
                           f"the per-keep cap dropped")
        if not out:
            return [], "; ".join(reasons) or "no valid card"
        return out, ("ok" if not reasons else "ok; " + "; ".join(reasons))
    except Exception as exc:                                    # noqa: BLE001
        return [], f"draft unparseable: {exc}"


def _coerce_one_draft(data, *, chain_id, question, now=None):
    try:
        card = dict(data)
        card["name"] = _snake(card.get("name"))
        card["kind"] = card.get("kind") or "method"
        card["status"] = "candidate"
        stripped = card.pop("implementation", None)
        today = (_parse_date(now) or date.today()).isoformat()
        card["provenance"] = {
            "source": "run", "created": today, "chain": chain_id,
            "note": ("distilled from a successful investigation"
                     + ("; implementation withheld until vetted"
                        if stripped else "")),
        }
        card["taught"] = False
        card["use_count"] = 0
        card["last_used"] = None
        card["evidence"] = [{"chain": chain_id, "findings": [],
                             "reinforced": False, "reinforced_at": None,
                             "tombstoned": False}]
        errors = _card_field_errors(card)
        if errors:
            return None, f"draft rejected: {'; '.join(errors)}"
        # Genericity guard: hooks are the retrieval keys and must name the
        # GENERAL capability, not echo the prompt that sparked the card.
        # High verbatim overlap with the sparking question is annotated so
        # the promotion review (step 27) knows to polish the hooks before
        # the card gains authority.
        q_tokens = {t for t in re.findall(r"[a-z0-9]+", str(question).lower())
                    if len(t) > 3}
        h_tokens = {t for t in re.findall(
            r"[a-z0-9]+", str(card["hooks"]["answers_question"]).lower())
            if len(t) > 3}
        if h_tokens and q_tokens:
            overlap = len(h_tokens & q_tokens) / len(h_tokens)
            if overlap >= 0.6:
                card["provenance"]["note"] += (
                    "; hooks may echo the sparking prompt - review for "
                    "genericity at promotion")
            elif not (h_tokens & q_tokens):
                # The mirror failure: a hook so generalized it shares no
                # vocabulary with the question that sparked it will never
                # be found by tomorrow's concrete question (proven live -
                # a good method died unread behind an abstract label).
                card["provenance"]["note"] += (
                    "; hooks may be too abstract to find - add the "
                    "concrete anchor at promotion")
        return card, "ok"
    except Exception as exc:                                    # noqa: BLE001
        return None, f"draft unparseable: {exc}"


def append_card(path, card, now=None, cap=CAP_CARDS):
    """Append one card to the pack at `path`, creating the file on first
    write. Duplicate names (case-insensitive) and a full pack are refused
    with a reason; relations are pruned to names that exist. Atomic via
    save_pack. Never raises: (ok, reason)."""
    try:
        errors = _card_field_errors(card)
        if errors:
            return False, f"invalid card: {'; '.join(errors)}"
        pack, _ = load_pack(path, now=now)
        names = {c["name"].lower() for c in pack["cards"]}
        if card["name"].lower() in names:
            return False, f"duplicate: '{card['name']}' already in the pack"
        if len(pack["cards"]) >= cap:
            return False, (f"pack at cap ({cap} cards) - curation before "
                           f"accumulation")
        keep = names | {card["name"].lower()}
        relations = card.get("relations") or {}
        pruned = {}
        for key in _RELATION_KEYS:
            vals = [r for r in (relations.get(key) or [])
                    if str(r).lower() in keep and str(r).lower() != card["name"].lower()]
            if vals:
                pruned[key] = vals
        if pruned:
            card["relations"] = pruned
        else:
            card.pop("relations", None)
        pack["cards"].append(card)
        save_pack(pack, path)
        return True, "ok"
    except Exception as exc:                                    # noqa: BLE001
        return False, f"error: {exc}"


def record_use(path, names, chain_id, findings_text="", now=None):
    """Warm the consulted cards: use_count, last_used, and one evidence
    stub per chain citing the findings whose text mentions the card -
    reinforced:false, for the step-25 rank hook to flip. Idempotent on
    evidence per (card, chain); counters always warm. Never raises;
    returns how many cards were updated."""
    try:
        if not path or not names:
            return 0
        pack, _ = load_pack(path, now=now)
        by_name = {c["name"].lower(): c for c in pack["cards"]}
        today = (_parse_date(now) or date.today()).isoformat()
        updated = 0
        for requested in names:
            card = by_name.get(str(requested).strip().lower())
            if not card:
                continue
            card["use_count"] = int(card.get("use_count") or 0) + 1
            card["last_used"] = today
            evidence = card.setdefault("evidence", [])
            if not any(str(e.get("chain")) == str(chain_id)
                       for e in evidence if isinstance(e, dict)):
                cited = []
                low = card["name"].lower()
                for line in (findings_text or "").splitlines():
                    fm = re.match(r"\s*(F\d+)\b", line)
                    if fm and low in line.lower():
                        cited.append(fm.group(1))
                evidence.append({"chain": chain_id, "findings": cited,
                                 "reinforced": False,
                                 "reinforced_at": None,
                                 "tombstoned": False})
                del evidence[:-_EVIDENCE_KEEP]
            updated += 1
        if updated:
            save_pack(pack, path)
        return updated
    except Exception as exc:                                    # noqa: BLE001
        logger.warning("record_use failed: %s", exc)
        return 0


STAGED_TTL_SECONDS = 48 * 3600   # unclaimed distillation sources die


def _staged_dir(memory_path):
    return os.path.join(os.path.dirname(memory_path), "staged")


def stage_distill_source(memory_path, chain_id, payload):
    """Persist a chain's distillation source beside the pack. The in-
    process ring cannot be trusted across gunicorn workers or restarts -
    the run may execute in one process and the keep arrive in another
    (proven live: the fallback's removal exposed it). Staging is scratch,
    not memory: unclaimed sources are pruned by maintain(). Never
    raises; returns bool."""
    try:
        d = _staged_dir(memory_path)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, f"{chain_id}.json"), "w",
                  encoding="utf-8") as f:
            json.dump(payload, f)
        return True
    except Exception as exc:                                    # noqa: BLE001
        logger.warning("stage_distill_source failed: %s", exc)
        return False


def discard_staged(memory_path, chain_ids):
    """Delete the named staged parcels. The teardown's broom: when a
    conversation ends (new conversation, logout, instance recreation),
    its unstarred chains become unreachable - the Workflows list shows
    only threads with SAVED chains - so their parcels are orphans from
    that instant. The 48h TTL in maintain() remains only as the crash
    backstop. Tolerates missing files and strangers; never raises;
    returns how many were actually removed."""
    removed = 0
    try:
        staged = _staged_dir(memory_path)
        for cid in set(chain_ids or ()):
            f = os.path.join(staged, f"{cid}.json")
            if os.path.isfile(f):
                os.remove(f)
                removed += 1
    except Exception as exc:                                    # noqa: BLE001
        logger.warning("discard_staged failed: %s", exc)
    return removed


def pop_distill_source(memory_path, chain_id):
    """Claim (read and DELETE) a staged source - any worker, once. The
    delete is the cross-process idempotence: the fused gesture's second
    leg finds nothing and stands down. Never raises; dict or None."""
    try:
        fp = os.path.join(_staged_dir(memory_path), f"{chain_id}.json")
        if not os.path.exists(fp):
            return None
        with open(fp, encoding="utf-8") as f:
            payload = json.load(f)
        try:
            os.remove(fp)
        except OSError:
            pass
        return payload if isinstance(payload, dict) else None
    except Exception as exc:                                    # noqa: BLE001
        logger.warning("pop_distill_source failed: %s", exc)
        return None


def reinforce(path, chain_id, reason="rank", now=None):
    """Flip the reinforced flag on evidence for `chain_id`. An evidence
    entry exists only because the run CONSULTED the card (record_use) or
    the card was BORN from the chain - consultation recorded at use time
    IS the citation, so kept means credited. (The first live keep proved
    findings-name-matching structurally dead: prose findings never
    contain card names, so consulted-and-kept chains could never credit;
    finer citation detection is a future refinement, noted in the spec.)
    Tombstoned evidence cannot be credited. Idempotent; returns the
    names NEWLY credited; never raises."""
    try:
        if not path or not os.path.exists(path):
            return []
        pack, _ = load_pack(path, now=now)
        today = (_parse_date(now) or date.today()).isoformat()
        credited = []
        for card in pack["cards"]:
            for e in card.get("evidence") or []:
                if not isinstance(e, dict):
                    continue
                if (str(e.get("chain")) == str(chain_id)
                        and not e.get("tombstoned")
                        and not e.get("reinforced")):
                    e["reinforced"] = True
                    e["reinforced_at"] = today
                    credited.append(card["name"])
        if credited:
            save_pack(pack, path)
        _ = reason  # recorded by callers' logs; kept for future provenance
        return sorted(set(credited))
    except Exception as exc:                                    # noqa: BLE001
        logger.warning("reinforce failed: %s", exc)
        return []


def tombstone(path, chain_ids, now=None):
    """Chain deletion under consent-on-write. CANDIDATE evidence citing
    the deleted chains is marked tombstoned; then any candidate this
    deletion TOUCHED that retains no un-tombstoned reinforced evidence
    is REMOVED - its every consent has been withdrawn, and a card kept
    alive by ambient use alone would be influence with no keep behind
    it. Candidates blessed by another surviving keep stay (entry marked,
    card intact). Established and vetted cards are immune everywhere:
    promotion was its own explicit consent, and repudiating it belongs
    to the review's demote/retire, not to housekeeping. Untouched cards
    are never evaluated. Idempotent; returns (entries_marked,
    removed_names); never raises."""
    try:
        if not path or not os.path.exists(path) or not chain_ids:
            return 0, []
        wanted = {str(c) for c in chain_ids}
        pack, _ = load_pack(path, now=now)
        marked, touched = 0, []
        for card in pack["cards"]:
            if card.get("status") != "candidate":
                continue
            hit = False
            for e in card.get("evidence") or []:
                if (isinstance(e, dict) and str(e.get("chain")) in wanted
                        and not e.get("tombstoned")):
                    e["tombstoned"] = True
                    marked += 1
                    hit = True
            if hit:
                touched.append(card)
        removed = []
        for card in touched:
            alive = any(isinstance(e, dict) and e.get("reinforced")
                        and not e.get("tombstoned")
                        for e in card.get("evidence") or [])
            if not alive:
                removed.append(card["name"])
        if removed:
            pack["cards"] = [c for c in pack["cards"]
                             if c["name"] not in set(removed)]
            logger.info("Memory: removed %d candidates whose every keep "
                        "was deleted (%s)", len(removed),
                        ", ".join(removed))
        if marked or removed:
            save_pack(pack, path)
        return marked, removed
    except Exception as exc:                                    # noqa: BLE001
        logger.warning("tombstone failed: %s", exc)
        return 0, []


def maintain(path, now=None):
    """The maintenance sweep: physically prune CANDIDATES with no activity
    for DECAY_DAYS - activity being creation, last use, or the latest
    evidence date. Established and vetted never decay. Idempotent; returns
    the pruned names; never raises."""
    try:
        if not path or not os.path.exists(path):
            return []
        pack, _ = load_pack(path, now=now)
        today = _parse_date(now) or date.today()
        keep, pruned = [], []
        for card in pack["cards"]:
            if card.get("status") != "candidate":
                keep.append(card)
                continue
            dates = [_parse_date((card.get("provenance") or {}).get("created")),
                     _parse_date(card.get("last_used"))]
            for e in card.get("evidence") or []:
                if isinstance(e, dict):
                    dates.append(_parse_date(e.get("reinforced_at")))
            dates = [d for d in dates if d]
            latest = max(dates) if dates else None
            if latest and (today - latest).days > DECAY_DAYS:
                pruned.append(card["name"])
            else:
                keep.append(card)
        if pruned:
            pack["cards"] = keep
            save_pack(pack, path)
            logger.info("Memory: pruned %d decayed candidates (%s)",
                        len(pruned), ", ".join(pruned))
        # Unclaimed staged sources age out too - scratch, not memory.
        try:
            d = _staged_dir(path)
            if os.path.isdir(d):
                import time as _time
                cutoff = _time.time() - STAGED_TTL_SECONDS
                stale = [f for f in os.listdir(d) if f.endswith(".json")
                         and os.path.getmtime(os.path.join(d, f)) < cutoff]
                for f in stale:
                    os.remove(os.path.join(d, f))
                if stale:
                    logger.info("Memory: pruned %d unclaimed staged "
                                "sources", len(stale))
        except Exception:                                       # noqa: BLE001
            pass
        return pruned
    except Exception as exc:                                    # noqa: BLE001
        logger.warning("maintain failed: %s", exc)
        return []


# ── graduation (step 27) ───────────────────────────────────────────────────

def _distinct_kept(card):
    """Chains that count toward promotion: reinforced, un-tombstoned,
    each chain once."""
    return {str(e.get("chain")) for e in card.get("evidence") or []
            if isinstance(e, dict) and e.get("reinforced")
            and not e.get("tombstoned")}


def promotable(path, now=None):
    """Candidates at or past PROMOTION_THRESHOLD distinct kept chains,
    each with what the review needs: the count, the provenance note (the
    flags to clear), and similar cards (hook cosine >= NEAR_DUP_NOTE)
    for the merge decision. Never raises."""
    try:
        if not path or not os.path.exists(path):
            return []
        pack, _ = load_pack(path, now=now)
        out = []
        for card in pack["cards"]:
            if card.get("status") != "candidate":
                continue
            distinct = _distinct_kept(card)
            if len(distinct) < PROMOTION_THRESHOLD:
                continue
            others = [c for c in pack["cards"] if c is not card]
            sims = _scores(_hooks_text(card), others) if others else []
            similar = [{"name": o["name"],
                        "status": o.get("status", "candidate")}
                       for o, sc in zip(others, sims)
                       if sc >= NEAR_DUP_NOTE]
            out.append({"name": card["name"],
                        "distinct": len(distinct),
                        "hooks": dict(card.get("hooks") or {}),
                        "body": dict(card.get("body") or {}),
                        "note": (card.get("provenance") or {}).get("note", ""),
                        "similar": similar})
        return out
    except Exception as exc:                                    # noqa: BLE001
        logger.warning("promotable failed: %s", exc)
        return []


def promote(path, name, hooks=None, now=None):
    """The human rung: candidate -> established, threshold enforced
    server-side, optional hook polish (both fields required non-empty
    when given). Promotion is written into provenance. Never raises;
    (ok, reason)."""
    try:
        if not path or not os.path.exists(path):
            return False, "no pack"
        pack, _ = load_pack(path, now=now)
        card = next((c for c in pack["cards"]
                     if c["name"].lower() == str(name).lower()), None)
        if card is None:
            return False, f"no card named '{name}'"
        if card.get("status") != "candidate":
            return False, f"'{name}' is not a candidate"
        distinct = _distinct_kept(card)
        if len(distinct) < PROMOTION_THRESHOLD:
            return False, (f"below threshold: {len(distinct)} of "
                           f"{PROMOTION_THRESHOLD} distinct keeps")
        polished = False
        if hooks is not None:
            aq = str(hooks.get("answers_question") or "").strip()
            uw = str(hooks.get("use_when") or "").strip()
            if not aq or not uw:
                return False, "polished hooks must fill both fields"
            card["hooks"]["answers_question"] = aq
            card["hooks"]["use_when"] = uw
            polished = True
        card["status"] = "established"
        today = (_parse_date(now) or date.today()).isoformat()
        prov = card.setdefault("provenance", {})
        prov["note"] = ((prov.get("note") or "").rstrip("; ")
                        + f"; promoted {today} ({len(distinct)} distinct "
                          f"keeps)"
                        + ("; hooks polished" if polished else ""))
        save_pack(pack, path)
        logger.info("Memory: '%s' promoted to established (%d keeps)",
                    card["name"], len(distinct))
        return True, "ok"
    except Exception as exc:                                    # noqa: BLE001
        logger.warning("promote failed: %s", exc)
        return False, f"error: {exc}"


def retire(path, name, now=None):
    """The explicit repudiation channel: remove a card by name - any
    status; trust moves down only through judgment like this. Never
    raises; (ok, reason)."""
    try:
        if not path or not os.path.exists(path):
            return False, "no pack"
        pack, _ = load_pack(path, now=now)
        before = len(pack["cards"])
        pack["cards"] = [c for c in pack["cards"]
                         if c["name"].lower() != str(name).lower()]
        if len(pack["cards"]) == before:
            return False, f"no card named '{name}'"
        _prune_dangling_relations(pack)
        save_pack(pack, path)
        logger.info("Memory: '%s' retired by review", name)
        return True, "ok"
    except Exception as exc:                                    # noqa: BLE001
        logger.warning("retire failed: %s", exc)
        return False, f"error: {exc}"


def merge(path, keep, absorb, now=None):
    """Absorb sibling cards into `keep`: evidence unioned and deduped by
    chain (reinforced and tombstoned flags OR-ed), counters summed,
    absorption written into provenance, absorbed cards removed. The
    merged card STAYS a candidate - promotion remains a separate human
    act. Never raises; (ok, reason)."""
    try:
        if not path or not os.path.exists(path):
            return False, "no pack"
        if not absorb:
            return False, "nothing to absorb"
        pack, _ = load_pack(path, now=now)
        by = {c["name"].lower(): c for c in pack["cards"]}
        target = by.get(str(keep).lower())
        if target is None:
            return False, f"no card named '{keep}'"
        victims = []
        _rank = {"candidate": 0, "established": 1, "vetted": 2}
        for nm in absorb:
            v = by.get(str(nm).lower())
            if v is None or v is target:
                return False, f"no card named '{nm}'"
            # Trust only moves down through explicit judgment: a lower-
            # status card must never silently swallow a higher one (a
            # candidate absorbing an established card deletes a governor
            # and keeps the CANDIDATE's method text - proven live, chain
            # of 2026-08-11 13:20). Retire or demote the governor first,
            # deliberately, if that is truly the intent.
            if (_rank.get(v.get("status", "candidate"), 0)
                    > _rank.get(target.get("status", "candidate"), 0)):
                return False, (f"cannot absorb '{v['name']}' "
                               f"({v.get('status')}) into a "
                               f"{target.get('status', 'candidate')} - "
                               f"retire it explicitly instead")
            victims.append(v)
        ev_by_chain = {}
        for e in target.get("evidence") or []:
            if isinstance(e, dict):
                ev_by_chain[str(e.get("chain"))] = dict(e)
        for v in victims:
            for e in v.get("evidence") or []:
                if not isinstance(e, dict):
                    continue
                ch = str(e.get("chain"))
                cur = ev_by_chain.get(ch)
                if cur is None:
                    ev_by_chain[ch] = dict(e)
                else:
                    cur["reinforced"] = bool(cur.get("reinforced")
                                             or e.get("reinforced"))
                    cur["reinforced_at"] = (cur.get("reinforced_at")
                                            or e.get("reinforced_at"))
                    cur["tombstoned"] = bool(cur.get("tombstoned")
                                             or e.get("tombstoned"))
            target["use_count"] = (int(target.get("use_count") or 0)
                                   + int(v.get("use_count") or 0))
            lu = [d for d in (target.get("last_used"), v.get("last_used"))
                  if d]
            target["last_used"] = max(lu) if lu else None
        target["evidence"] = list(ev_by_chain.values())
        today = (_parse_date(now) or date.today()).isoformat()
        prov = target.setdefault("provenance", {})
        prov["note"] = ((prov.get("note") or "").rstrip("; ")
                        + f"; absorbed {', '.join(v['name'] for v in victims)}"
                          f" ({today})")
        gone = {v["name"].lower() for v in victims}
        pack["cards"] = [c for c in pack["cards"]
                         if c["name"].lower() not in gone]
        _prune_dangling_relations(pack)
        save_pack(pack, path)
        logger.info("Memory: '%s' absorbed %s", target["name"],
                    ", ".join(sorted(gone)))
        return True, "ok"
    except Exception as exc:                                    # noqa: BLE001
        logger.warning("merge failed: %s", exc)
        return False, f"error: {exc}"


def governing(path, now=None):
    """Established and vetted cards, for the review's second section -
    the repudiation channel needs somewhere to see the governors.
    Never raises."""
    try:
        if not path or not os.path.exists(path):
            return []
        pack, _ = load_pack(path, now=now)
        return [{"name": c["name"],
                 "status": c.get("status", "candidate"),
                 "distinct": len(_distinct_kept(c)),
                 "hooks": dict(c.get("hooks") or {}),
                 "body": dict(c.get("body") or {}),
                 "note": (c.get("provenance") or {}).get("note", ""),
                 "use_count": int(c.get("use_count") or 0),
                 "last_used": c.get("last_used")}
                for c in pack["cards"]
                if c.get("status") in ("established", "vetted")]
    except Exception as exc:                                    # noqa: BLE001
        logger.warning("governing failed: %s", exc)
        return []


def _prune_dangling_relations(pack):
    live = {c["name"].lower() for c in pack["cards"]}
    for c in pack["cards"]:
        rel = c.get("relations")
        if not isinstance(rel, dict):
            continue
        pruned = {}
        for k in _RELATION_KEYS:
            vals = [r for r in (rel.get(k) or [])
                    if str(r).lower() in live]
            if vals:
                pruned[k] = vals
        if pruned:
            c["relations"] = pruned
        else:
            c.pop("relations", None)


def extract_memory_lookups(run_text):
    """The lookups a run actually made, read from its own evidence: the
    MEMORY DEFINITIONS headers, minus NOT FOUND, plus MATCHED BY MEANING.
    Never raises; returns a set of names."""
    names = set()
    try:
        for m in re.finditer(
                r"MEMORY DEFINITIONS for: ([^\n]+)\n"
                r"(?:NOT FOUND in memory: ([^\n]+)\n)?"
                r"(?:MATCHED BY MEANING: ([^\n]+)\n)?",
                run_text or ""):
            wanted = {n.strip() for n in m.group(1).split(",") if n.strip()}
            missing = {n.strip() for n in (m.group(2) or "").split(",")
                       if n.strip()}
            meaning = {n.strip() for n in (m.group(3) or "").split(",")
                       if n.strip()}
            names |= (wanted - missing) | meaning
    except Exception:                                           # noqa: BLE001
        pass
    return names


# ── lookup ─────────────────────────────────────────────────────────────────

def parse_memory_query(query):
    """Parts of a `memory: A, B` query, or None when it is not one."""
    if not query:
        return None
    q = query.strip()
    if not q.lower().startswith(MEMORY_PREFIX):
        return None
    body = q[len(MEMORY_PREFIX):]
    return [p.strip() for p in body.replace("\n", ",").split(",")
            if p.strip()]


def _render_card(card):
    shown = {k: v for k, v in card.items()
             if not str(k).startswith("_")
             and k not in ("evidence", "use_count", "last_used")}
    return yaml.safe_dump([shown], sort_keys=False, allow_unicode=True)


def _closure(found, by_name):
    """Dependency closure: a card's depends_on/requires that name other
    cards ride along - asking for a formula returns the formulas it is
    built from, which is the whole reason memory beats guessing."""
    queue = list(found)
    seen = {c["name"] for c in found}
    out = list(found)
    while queue:
        card = queue.pop(0)
        relations = card.get("relations") or {}
        for key in ("depends_on", "requires"):
            for ref in relations.get(key) or []:
                dep = by_name.get(str(ref).lower())
                if dep and dep["name"] not in seen:
                    seen.add(dep["name"])
                    out.append(dep)
                    queue.append(dep)
    return out


def memory_lookup(path, parts, max_chars=24000, now=None):
    """Full definitions for named cards (case-insensitive), with dependency
    closure; parts matching no name are joined into one semantic query
    (top 3). Misses are reported by name. Never raises: a failed lookup
    must not end an investigation."""
    if not path or not parts:
        return ""
    wanted = [p.strip() for p in parts if p and p.strip()]
    if not wanted:
        return ""
    try:
        pack, _ = load_pack(path, now=now)
        by_name = {c["name"].lower(): c for c in pack["cards"]}
        found, unresolved = [], []
        for part in wanted:
            card = by_name.get(part.lower())
            if card and card not in found:
                found.append(card)
            elif not card:
                unresolved.append(part)
        semantic_note = ""
        if unresolved:
            live = [c for c in pack["cards"]
                    if not c.get("_decayed") and c not in found]
            # A meaning-match needs a real floor: with a floorless top-k,
            # one miss-typed name dragged the pack's only OTHER card into
            # a critical-power question, live (chain 1786443999). Better
            # an honest "nothing matches" than an irrelevant card in the
            # context - the pill shows whatever comes back, and at 350
            # cards floorless matching would poison every miss.
            matches = _ranked(live, " ".join(unresolved))[:2]
            matches = [m for m in matches
                       if _scores(" ".join(unresolved), [m])[0]
                       >= SEMANTIC_MATCH_MIN]
            if matches:
                semantic_note = ("MATCHED BY MEANING: "
                                 + ", ".join(m["name"] for m in matches)
                                 + "\n")
                found.extend(m for m in matches if m not in found)
                unresolved = []
        if not found:
            return (f"MEMORY LOOKUP: nothing in memory matches "
                    f"{', '.join(wanted)}. Check the names against the "
                    f"index, or ask by meaning.")
        found = _closure(found, by_name)
        header = f"MEMORY DEFINITIONS for: {', '.join(wanted)}\n"
        if unresolved:
            header += f"NOT FOUND in memory: {', '.join(unresolved)}\n"
        header += semantic_note
        text = header + "\n" + "\n".join(_render_card(c) for c in found)
        if len(text) > max_chars:
            text = (text[:max_chars]
                    + "\n# ... definitions truncated; look up fewer names\n")
        return text
    except Exception as exc:                                    # noqa: BLE001
        logger.warning("Memory lookup failed for %s: %s", parts, exc)
        return f"MEMORY LOOKUP failed: {exc}"