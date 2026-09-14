"""
prompt_cache.py - prompt caching shared by BambooAI's providers.

WHY THIS EXISTS
---------------
Every agent in BambooAI re-sends a growing message list each turn: code_messages
accumulate across a chain, and an autonomous investigation accumulates a step
history that dwarfs them. Without caching, turn N pays full input price for
everything turns 1..N-1 already sent. A measured 5-turn investigation sent
83,750 prompt characters and was still growing linearly.

Providers cache differently, so this module normalises three things:

  1. WHERE breakpoints go (Anthropic-family models need them explicitly;
     OpenAI and xAI cache automatically but want a stable routing key).
  2. HOW MUCH was cached, reported back through a per-thread side channel so
     provider return signatures stay unchanged.
  3. WHAT COUNTS as the total input, which differs by vendor - see
     NORMALISATION below.

NORMALISATION (the part that silently corrupts billing if you get it wrong)
--------------------------------------------------------------------------
Anthropic's `usage.input_tokens` EXCLUDES both cache reads and cache writes.
OpenAI's `usage.prompt_tokens` INCLUDES cached tokens.

So providers must report prompt_tokens as the TOTAL input:

    anthropic:  input_tokens + cache_creation_input_tokens + cache_read_input_tokens
    openai/xAI: prompt_tokens (already total)

log_manager then prices uncached = total - cached - written, and prices the
cached and written portions at their own rates. Report Anthropic's raw
input_tokens as the total and every cached run under-bills; price OpenAI's
prompt_tokens as if it were all uncached and every run over-bills.

THREAD SAFETY
-------------
BambooAI runs each query on its own thread and calls providers sequentially
within it, so a threading.local side channel is exact. Call reset() before a
request and last() after.
"""

import os
import threading
import uuid

# Anthropic will not cache a prefix below 1024 tokens (2048 for Haiku), and a
# cache WRITE costs 1.25x. Marking a short prompt therefore pays a 25% premium
# for a cache that can never be read. ~4 chars/token, with the Haiku floor
# applied, so short normal-mode calls are left alone.
MIN_CACHEABLE_CHARS = int(os.getenv("BAMBOO_CACHE_MIN_CHARS", "8192"))

# Anthropic allows at most 4 cache_control breakpoints per request.
MAX_BREAKPOINTS = 4

ENABLED = os.getenv("BAMBOO_PROMPT_CACHE", "1") not in ("0", "false", "False")

_local = threading.local()


# ── per-request side channel ───────────────────────────────────────────────

def reset():
    """Clear the counters. Call at the start of every provider request."""
    _local.read = 0
    _local.write = 0
    _local.meta = {}


def record(read=0, write=0):
    _local.read = getattr(_local, "read", 0) + int(read or 0)
    _local.write = getattr(_local, "write", 0) + int(write or 0)


def last():
    """(cached_tokens, cache_write_tokens) for the request just completed."""
    return getattr(_local, "read", 0), getattr(_local, "write", 0)


def record_meta(**fields):
    """Facts about the request the log cannot otherwise see.

    The same thread-local channel the token split uses, and exact for the same
    reason: one provider request per thread, reset before dispatch.

    What goes here is what a log reader needs but the return value does not
    carry - above all the reasoning effort ACTUALLY SENT, as opposed to what
    was asked for. Those diverged silently once: delv-e asked for "none" to
    turn thinking off in the Executor seat, the provider layer rewrote it to
    "low", and the model spent its entire budget thinking and emitted no code.
    Nothing in the log could have shown that.
    """
    meta = getattr(_local, "meta", None)
    if meta is None:
        meta = _local.meta = {}
    meta.update({k: v for k, v in fields.items() if v is not None})


def last_meta():
    """The recorded facts for the request just completed."""
    return dict(getattr(_local, "meta", None) or {})


# ── per-run affinity key ───────────────────────────────────────────────────
# OpenAI wants a stable prompt_cache_key for reliable matching on GPT-5.x, and
# xAI's cache is affinity-sensitive: without a stable id, requests land on
# different backends and hit rates collapse even for identical prefixes.

# Affinity must outlive the request thread: BambooAI runs each user
# turn on its own thread, so a lazily thread-local key minted a NEW
# conversation id every turn and xAI/OpenAI cache affinity never
# crossed a turn boundary - measured in production as a flat
# "cached 128" on every grok-4.6 turn (2026-08-15). The process-stable
# default restores cross-turn affinity; new_session() remains the
# deliberate per-thread override for tests and isolation.
_PROCESS_SESSION = uuid.uuid4().hex


def session_key(chain_id=None):
    key = getattr(_local, "session", None) or _PROCESS_SESSION
    return f"{key}-{chain_id}" if chain_id else key


def new_session():
    _local.session = uuid.uuid4().hex
    return _local.session


# ── breakpoint placement ───────────────────────────────────────────────────

def _text_len(content):
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(len(p.get("text", "")) for p in content if isinstance(p, dict))
    return len(str(content or ""))


def already_marked(content):
    """True when a content list already carries breakpoints.

    delv-e's build_cached_messages places its own, per history step, which is
    finer-grained than anything this module can infer from the outside: it
    knows which blocks are append-only and which is the volatile tail. When it
    has spoken, defer to it. Re-marking would spend one of the four breakpoints
    on a boundary that is already covered and can push the useful one off the
    end.
    """
    if not isinstance(content, list):
        return False
    return any(isinstance(b, dict) and "cache_control" in b for b in content)


def _as_blocks(content):
    """A string becomes a single text block; an existing block list passes
    through. Never mutates the caller's list."""
    if isinstance(content, list):
        return [dict(p) for p in content]
    return [{"type": "text", "text": str(content or "")}]


def anthropic_system(system_instruction):
    """The system prompt as cacheable blocks.

    The system prompt is the most stable thing in any request and never changes
    within a chain, so it is always worth a breakpoint when it is long enough
    to be cacheable at all.
    """
    if not system_instruction:
        return system_instruction
    if already_marked(system_instruction):
        return system_instruction
    if not ENABLED or len(str(system_instruction)) < MIN_CACHEABLE_CHARS:
        return system_instruction
    blocks = _as_blocks(system_instruction)
    blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks


def anthropic_messages(messages):
    """Copy of `messages` with cache breakpoints on the stable prefix.

    Placement: the FIRST message (a cheap fallback that stays valid all chain)
    and the LAST message before the newest one (the moving frontier). The
    newest message is never marked - it is the volatile part, and marking it
    would write a cache entry that the next turn's different tail can never
    match.

    Incremental behaviour: on turn N the frontier breakpoint sits at the end of
    turn N-1's content. Turn N+1 places its own frontier one message later, so
    the older boundary is still inside the prefix and is READ back, while only
    the delta is written. This only holds if earlier messages are byte-stable -
    see the warning in the module docstring of message_manager: any maintenance
    that rewrites old messages invalidates the prefix and forces a full
    re-write at 1.25x.
    """
    out = [dict(m) for m in (messages or [])]
    if any(already_marked(m.get("content")) for m in out):
        return out
    if not ENABLED or len(out) < 2:
        return out

    stable = out[:-1]
    if sum(_text_len(m.get("content")) for m in stable) < MIN_CACHEABLE_CHARS:
        return out

    marks = []
    frontier = len(stable) - 1
    marks.append(frontier)
    if frontier > 0:
        marks.append(0)                      # fallback anchor

    for i in sorted(set(marks))[:MAX_BREAKPOINTS - 1]:   # -1: system holds one
        blocks = _as_blocks(out[i].get("content"))
        blocks[-1]["cache_control"] = {"type": "ephemeral"}
        out[i]["content"] = blocks
    return out


def is_anthropic_family(model):
    """Does this model take EXPLICIT cache_control breakpoints?

    True for Anthropic direct and for Anthropic models routed through
    OpenRouter, which forwards cache_control unchanged. Everything else caches
    implicitly and must NOT be sent breakpoints - some providers reject the
    unknown field outright.
    """
    m = (model or "").lower()
    return "claude" in m or m.startswith("anthropic/")


def takes_cache_control(model):
    """Does THIS ROUTE take explicit cache_control breakpoints?

    Anthropic always has (direct or via OpenRouter). Gemini VIA
    OPENROUTER joined 2026-08-20: implicit caching through the shared
    route is empirically unreliable - Log_28's six Investigator calls
    each offered 6,534-9,183 byte-stable prefix tokens (measured by
    consecutive-prompt divergence) and reported zero cached tokens, and
    the ecosystem reports the same (opencode #36069, n8n #26640).
    OpenRouter's own remedy is explicit breakpoints for Gemini,
    announced as "exactly the same as Anthropic", with writes billed at
    input price plus five minutes of storage and reads at the model
    page's cache-read rate. The predicate is ROUTE-shaped on purpose:
    bare gemini-* slugs are the native Google transport, which caches
    implicitly on its own and must not be sent the field.
    """
    m = (model or "").lower()
    return is_anthropic_family(m) or m.startswith("google/gemini")


def openai_extras(model=None, chain_id=None):
    """Extra request params for implicit-cache providers.

    OpenAI caches automatically above ~1024 tokens but routes by prompt prefix;
    a stable prompt_cache_key keeps a conversation landing on the same cache.
    """
    if not ENABLED:
        return {}
    return {"prompt_cache_key": session_key(chain_id)}


def grok_headers(chain_id=None):
    """xAI's cache is automatic but affinity-sensitive; a stable conversation
    id keeps requests on one backend so identical prefixes actually hit."""
    if not ENABLED:
        return {}
    return {"x-grok-conv-id": session_key(chain_id)}


# ── usage extraction ───────────────────────────────────────────────────────

def _attr(obj, name, default=0):
    v = getattr(obj, name, None)
    if v is None and hasattr(obj, "model_dump"):
        try:
            v = obj.model_dump().get(name)
        except Exception:                                       # noqa: BLE001
            v = None
    if v is None and isinstance(obj, dict):
        v = obj.get(name)
    return default if v is None else v


def from_anthropic_usage(usage):
    """(read, write, total_input) from an Anthropic usage object.

    total_input adds the cached portions back, because Anthropic's
    input_tokens excludes both.
    """
    if usage is None:
        return 0, 0, 0
    read = int(_attr(usage, "cache_read_input_tokens") or 0)
    write = int(_attr(usage, "cache_creation_input_tokens") or 0)
    base = int(_attr(usage, "input_tokens") or 0)
    record(read=read, write=write)
    return read, write, base + read + write


def from_openai_usage(usage):
    """(read, write, total_input) from an OpenAI-compatible usage object.

    prompt_tokens already includes cached tokens, so the total is returned
    unchanged. Implicit caches report no write count; cache creation is not
    billed at a premium on these providers, so 0 is correct rather than
    missing.
    """
    if usage is None:
        return 0, 0, 0
    details = _attr(usage, "prompt_tokens_details", None) or {}
    read = int(_attr(details, "cached_tokens") or 0)
    write = int(_attr(details, "cache_write_tokens") or 0)
    total = int(_attr(usage, "prompt_tokens") or 0)
    record(read=read, write=write)
    return read, write, total


def from_responses_usage(usage):
    """xAI / OpenAI Responses API: input_tokens with a cached breakdown."""
    if usage is None:
        return 0, 0, 0
    details = _attr(usage, "input_tokens_details", None) or {}
    read = int(_attr(details, "cached_tokens") or 0)
    total = int(_attr(usage, "input_tokens") or 0)
    record(read=read, write=0)
    return read, 0, total