"""resilience.py — the provider-agnostic half of what openrouter_models learned.

Every provider module grew independently, so the hardening that went into
openrouter over the 2026-08 runs reached none of the others. This holds the
parts that are genuinely the same everywhere, so a roster change does not
silently drop a run into an unhardened path.

Deliberately NOT here: anything provider-specific. OpenRouter's mutually
exclusive reasoning.effort / reasoning.max_tokens, its THINKING_BUDGET table,
Anthropic's thinking budget_tokens, Gemini's thinking_config. Copying those
blind is how a request went out with two keys the API rejects, and it broke
every call until it was found.

    timeout_kwargs()          the SDK arguments that stop a hung call
    restartable()             reopen a stream that died before its first token
    report_truncation()       say so when an answer was cut off
    record_request()          effort and max_tokens into the run log

WHY EACH ONE EXISTS

timeout        A stalled upstream blocked for ~15 minutes with no client
               timeout; nginx reset the connection and nothing was logged,
               because nothing had failed yet.
restart        "Upstream error from DigitalOcean: Connection closed" killed a
               Synthesizer call fifty model calls into a 1h45m run.
truncation     finish_reason was never read anywhere, so a cut-off answer was
               returned as if complete and the caller failed later on
               unparseable output - which presents as a stall, not an error.
metadata       The effort ACTUALLY sent, which diverged from the effort
               requested for weeks without anything being able to show it.
"""

import logging
import os
import time

from bambooai.models import prompt_cache

logger = logging.getLogger(__name__)

# Seconds a single attempt may take. Generous for a long reasoning turn, far
# short of a reverse proxy's read timeout, so a stall surfaces as an error the
# app can report rather than a dead stream the browser blames on the network.
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "300"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "1"))

# Reopens allowed when a stream dies before emitting anything.
STREAM_MIDFLIGHT_RETRIES = int(os.getenv("STREAM_MIDFLIGHT_RETRIES", "2"))
STREAM_RETRY_BACKOFF = float(os.getenv("STREAM_RETRY_BACKOFF", "2"))


def timeout_kwargs(sdk="openai"):
    """Client-constructor arguments that bound a single call.

    `sdk="openai"` covers every OpenAI-compatible client - OpenAI itself,
    Grok, OpenRouter, vLLM - and Anthropic's, which takes the same two names.
    Returns an empty dict for anything else rather than guessing, because a
    wrong keyword is a TypeError at construction and takes the provider down
    entirely.
    """
    if sdk in ("openai", "anthropic"):
        return {"timeout": LLM_TIMEOUT, "max_retries": LLM_MAX_RETRIES}
    return {}


def restartable(open_stream, exc_types, output_manager=None, chain_id=None,
                label="provider"):
    """Yield chunks, retrying if the stream dies BEFORE the first one.

    Covers BOTH failure shapes in one budget: an exception while OPENING the
    stream (the SDK's create() call) and one after opening but before any
    chunk arrives. Before anything has been emitted the two are the same
    event - nothing exists to duplicate, so a fresh stream is exactly
    equivalent. Once tokens have started the answer cannot be resumed, and
    replaying it would produce a mangled one, so a later drop stays fatal.

    `open_stream()` must return a FRESH iterator on each call. `exc_types` is
    the provider's own error class or a tuple of them - passed in rather than
    caught broadly, so a genuine bug is not mistaken for a network blip.
    """
    attempts = 0
    while True:
        started = False
        try:
            stream = open_stream()
            for chunk in stream:
                started = True
                yield chunk
            return
        except exc_types as exc:                                # noqa: B902
            if started or attempts >= STREAM_MIDFLIGHT_RETRIES:
                raise
            attempts += 1
            delay = STREAM_RETRY_BACKOFF * attempts
            message = (f"{label} dropped the stream before sending anything "
                       f"({exc}); retrying in {delay:g}s "
                       f"[{attempts}/{STREAM_MIDFLIGHT_RETRIES}]")
            logger.warning(message)
            _tell(output_manager, message, chain_id)
            time.sleep(delay)


def report_truncation(model, max_tokens, output_manager=None, chain_id=None):
    """Say that an answer was cut off, on screen and in the log.

    It cannot be fixed here - the caller owns the retry - but a truncated
    response that looks complete is the difference between "the run stalled"
    and "this agent hit its token limit", and only one of those is actionable.
    """
    message = (f"{model} hit its {max_tokens}-token limit and its answer was "
               f"cut off. Raise max_tokens for that agent in LLM_CONFIG if "
               f"this recurs.")
    logger.warning(message)
    _tell(output_manager, message, chain_id)
    prompt_cache.record_meta(truncated=True)


def record_request(reasoning_effort=None, max_tokens=None, requested=None):
    """Put what the request was CONFIGURED with into the run log.

    `reasoning_effort` is what was SENT, after any provider coercion;
    `requested` only when the two differ. They diverged silently once - "none"
    was rewritten to "low" and a seat spent its whole budget thinking - and
    nothing in the log could show it. max_tokens rides along so a `truncated`
    entry is interpretable without the config.
    """
    fields = {"reasoning_effort": reasoning_effort, "max_tokens": max_tokens}
    if requested and requested != reasoning_effort:
        fields["reasoning_effort_requested"] = requested
    prompt_cache.record_meta(**fields)


def _tell(output_manager, message, chain_id):
    """Best effort: a reporting failure must never mask what it reports."""
    if output_manager is None:
        return
    try:
        output_manager.display_system_messages(message, chain_id=chain_id)
    except Exception:                                           # noqa: BLE001
        pass