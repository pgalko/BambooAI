import json
import os
import queue
import threading
import time
import openai

from logger_config import get_logger
logger = get_logger(__name__)

# Seconds a single LLM attempt may take before it is abandoned. Generous enough
# for a long reasoning turn (the Investigator's have run to ~150s) and far short
# of nginx's proxy_read_timeout, so a stall surfaces as an error the app can
# report rather than as a dead stream the browser blames on the network.
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "300"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "1"))

# Extra attempts at OPENING a stream when the upstream provider errors.
# Separate from LLM_MAX_RETRIES, which the SDK applies to its own
# transport-level failures and which does not cover an APIError raised
# from the provider itself.
STREAM_OPEN_RETRIES = int(os.getenv("STREAM_OPEN_RETRIES", "2"))
# Reopens allowed when a stream dies before emitting anything.
# The post-finish tail deadline (see _tail_guarded). Env-tunable; a stalled
# provider costs this much per call instead of ~8 minutes.
try:
    STREAM_TAIL_TIMEOUT = float(os.getenv("BAMBOO_STREAM_TAIL_TIMEOUT", "30"))
except (TypeError, ValueError):
    STREAM_TAIL_TIMEOUT = 30.0

# The MID-STREAM idle deadline (see _tail_guarded). Production
# 2026-08-18: an Investigator call ran 512s - every content chunk
# delivered, the UI complete, finish_reason never sent - and sat on
# the deliberately unbounded pre-finish leg until the provider closed
# the socket. Once streaming has BEGUN, reasoning deltas flow
# continuously and silence is pathological; BEFORE the first chunk the
# wait stays unbounded so a reasoning model may think as long as it
# needs. Env-tunable like its sibling.
try:
    STREAM_IDLE_TIMEOUT = float(os.getenv("BAMBOO_STREAM_IDLE_TIMEOUT", "120"))
except (TypeError, ValueError):
    STREAM_IDLE_TIMEOUT = 120.0

STREAM_MIDFLIGHT_RETRIES = int(os.getenv("STREAM_MIDFLIGHT_RETRIES", "2"))

# Ceiling on the hidden reasoning channel, per effort level. Capped again
# at half of max_tokens at the call site, so the answer always has room.
THINKING_BUDGET = {
    "none": None,          # thinking already off
    "low": int(os.getenv("THINKING_BUDGET_LOW", "4000")),
    "medium": int(os.getenv("THINKING_BUDGET_MEDIUM", "12000")),
    "high": int(os.getenv("THINKING_BUDGET_HIGH", "24000")),
    # 2026-08-20, the completed dictionary: max/xhigh are the house
    # ceiling - an admin's "max" is the top number, never the middle.
    "xhigh": int(os.getenv("THINKING_BUDGET_XHIGH", "24000")),
    "max": int(os.getenv("THINKING_BUDGET_MAX", "24000")),
}
STREAM_RETRY_BACKOFF = float(os.getenv("STREAM_RETRY_BACKOFF", "2"))
import tiktoken

from bambooai import google_search, utils, context_retrieval
from bambooai.utils import StoppableStreamWrapper

# The dispatcher's turn-level retry catches exactly these; see models/__init__.
TRANSPORT_ERRORS = (openai.APIError,)

from logger_config import get_logger
logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# Module level switches / helpers
# ---------------------------------------------------------------------------

# When False (default) the text from every streaming round is concatenated, which
# preserves the historical behaviour: an agent that narrates before calling a tool
# keeps that narration in the returned content.
# Flip to True if you would rather only keep the text emitted after the final tool
# round -- useful when a model emits a partial <plan>/code block, calls a tool, and
# then re-emits a complete one (concatenation can confuse the reg_ex extractors).
RETURN_FINAL_ROUND_ONLY = False

# Hard ceiling on tool-call round trips before we force a plain text answer.
MAX_TOOL_ITERATIONS = 10

# OpenRouter forwards `reasoning.effort` to the upstream provider. Only the gpt-5
# family accepts "minimal"; everything else expects high|medium|low. bambooai asks
# for "minimal" in several places, so normalise at the boundary rather than making
# every call site provider-aware.
# "none" is NOT an alias for "low". OpenRouter accepts it and relays it to the
# provider's native control, and it is the only dependable way to turn thinking
# OFF - some models collapse low and medium to their maximum. delv-e runs the
# Executor at "none" precisely because a reasoning model in a transcription seat
# can spend its whole output budget thinking and emit no code. Rewriting it to
# "low" caused exactly that: two 16,000-token responses containing nothing, and
# delv-e's truncation ladder could not rescue it because its fallback rung
# ("none") normalised to the same value that was already failing.
_EFFORT_ALIASES = {"minimal": "low", "default": "medium", "off": "none"}
_VALID_EFFORTS = {"none", "low", "medium", "high", "xhigh", "max"}
# The vocabulary for EFFORT-WORD models (reasoning_style: "effort") is the
# provider's own: minimal is a real OpenRouter level there, not an alias,
# 2026-08-20: the budget dictionary is COMPLETE and monotone - max/xhigh
# carry the house ceiling, so an admin's "max" is never silently the middle.
_EFFORT_WORDS = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}
_EFFORT_WORD_ALIASES = {"default": "medium", "off": "none"}




def _tail_guarded(stream, output_manager=None, chain_id=None):
    """Bound the wait for what comes AFTER the answer is complete.

    Third member of a family this file already knows: a stream that never
    starts (retried above), one that dies mid-body (fatal, unresumable),
    and - production Log_9, 2026-08-16 - one that delivers the whole
    answer, emits finish_reason, and then holds the connection open while
    the provider fetches its usage frame. Keep-alive comments are filtered
    by the SDK, so no read timeout ever fires: 33 stalls of 240-475s cost
    ~2h45m of a 6h run, with the pipeline thread asleep in ssl.read.

    The wait is THREE-PHASE (2026-08-18, the 512s Investigator stall:
    all content delivered, finish_reason never sent, the unbounded
    pre-finish leg held until the provider's socket close). Before the
    first chunk the wait is unbounded on purpose - a reasoning model
    may think for minutes before its first token. Once streaming has
    begun, an idle deadline applies: silence after output is the same
    disease as the tail stall and gets the same cure. After
    finish_reason, the original tail deadline applies. On any expiry
    the intact answer received so far is returned; the accounting
    layer already prices a call without a usage frame.
    """
    q = queue.Queue()

    def _pump():
        try:
            for chunk in stream:
                q.put((True, chunk))
        except BaseException as exc:                        # noqa: BLE001
            q.put((False, exc))
        else:
            q.put((False, None))

    t = threading.Thread(target=_pump, daemon=True)
    t.start()
    finished = False
    started = False
    while True:
        try:
            ok, item = q.get(timeout=STREAM_TAIL_TIMEOUT if finished
                             else (STREAM_IDLE_TIMEOUT if started else None))
        except queue.Empty:
            if finished:
                message = (f"The provider completed the answer but did not "
                           f"close the stream within {STREAM_TAIL_TIMEOUT}s; "
                           f"proceeding without its usage frame.")
            else:
                message = (f"The stream went silent for "
                           f"{STREAM_IDLE_TIMEOUT}s after output began, "
                           f"without a finish signal; proceeding with the "
                           f"answer received so far.")
            logger.warning(message)
            try:
                if output_manager is not None:
                    output_manager.display_system_messages(message,
                                                           chain_id=chain_id)
            except Exception:                               # noqa: BLE001
                pass
            return
        if not ok:
            if item is not None:
                raise item
            return
        started = True
        yield item
        if not finished:
            for choice in (getattr(item, "choices", None) or []):
                if getattr(choice, "finish_reason", None):
                    finished = True
                    break


def _restartable(open_stream, output_manager=None, chain_id=None):
    """Yield chunks, reopening the stream if it dies BEFORE the first one.

    get_response already retries a stream that fails to open. A provider can
    also accept the connection and then close it - seen in the field as
    "APIError: Upstream error from DigitalOcean: Connection closed." That killed
    a Synthesizer call fifty model calls into a 1h45m run and lost the whole
    question.

    The retry is deliberately confined to the window before the first chunk.
    With nothing emitted a fresh stream is exactly equivalent; once content has
    started arriving the answer cannot be resumed, and replaying it would
    produce a mangled one, so a later drop stays fatal.

    `open_stream()` must return a fresh iterator each time it is called.
    """
    attempts = 0
    while True:
        stream = _tail_guarded(open_stream(), output_manager, chain_id)
        started = False
        try:
            for chunk in stream:
                started = True
                yield chunk
            return
        except openai.APIError as exc:
            if started or attempts >= STREAM_MIDFLIGHT_RETRIES:
                raise
            attempts += 1
            delay = STREAM_RETRY_BACKOFF * attempts
            message = (f"The provider closed the stream before sending anything "
                       f"({exc}); retrying in {delay}s "
                       f"[{attempts}/{STREAM_MIDFLIGHT_RETRIES}]")
            try:
                if output_manager is not None:
                    output_manager.display_system_messages(message,
                                                           chain_id=chain_id)
            except Exception:                                   # noqa: BLE001
                pass
            time.sleep(delay)

def _normalise_effort(effort, style=None):
    """Coerce bambooai's effort vocabulary into what OpenRouter accepts.

    Two vocabularies, chosen by the model's declared reasoning style.
    Budget models (the default) keep the original clamp to the four
    levels THINKING_BUDGET prices. Effort-word models speak the
    provider's own scale: minimal passes through, and max/xhigh - the
    levels the GLM family actually reasons at - survive instead of
    collapsing to medium. Garbage degrades to medium in both."""
    if not effort:
        return "medium"
    effort = str(effort).strip().lower()
    if style == "effort":
        effort = _EFFORT_WORD_ALIASES.get(effort, effort)
        return effort if effort in _EFFORT_WORDS else "medium"
    effort = _EFFORT_ALIASES.get(effort, effort)
    return effort if effort in _VALID_EFFORTS else "medium"


def _reasoning_delta_text(delta):
    """Reasoning text carried on a stream delta, whichever channel served it.

    OpenRouter's original channel is `reasoning` - a plain string
    (DeepSeek et al.), and it is all this reader ever surfaced. Newer
    providers emit only the `reasoning_details` array (GLM-5.3,
    2026-08-19: the planner's thinking ran and billed but never
    displayed and never reached the token fallback). The string is
    preferred when both are present - it IS the concatenated details,
    so reading both would print every token twice. Entries may be dicts
    or SDK objects; encrypted entries carry nothing displayable and are
    skipped."""
    text = getattr(delta, "reasoning", None)
    if text:
        return text
    details = getattr(delta, "reasoning_details", None) or []
    parts = []
    for entry in details:
        if isinstance(entry, dict):
            def _get(key, _e=entry):
                return _e.get(key)
        else:
            def _get(key, _e=entry):
                return getattr(_e, key, None)
        if "encrypted" in str(_get("type") or ""):
            continue
        piece = _get("text") or _get("summary")
        if piece:
            parts.append(str(piece))
    return "".join(parts)


def _get_encoding():
    """tiktoken encoder used only as a fallback when OpenRouter returns no usage."""
    try:
        return tiktoken.encoding_for_model("gpt-4")
    except Exception:
        return tiktoken.get_encoding("cl100k_base")


def _estimate_prompt_tokens(messages, encoding):
    """Rough OpenAI-style prompt token estimate. Fallback only."""
    tokens_per_message = 3
    tokens_per_name = 1
    total = 0
    for message in messages:
        total += tokens_per_message
        for key, value in message.items():
            if isinstance(value, str):
                total += len(encoding.encode(value))
            if key == "name":
                total += tokens_per_name
    total += 3  # reply primer
    return total


from bambooai.models import prompt_cache
from bambooai.models.grok_models import _is_native_reasoning as _mandatory_reasoning


def init(api_keys=None):
    """
    Initialize OpenRouter client with API key precedence:
    1. Use api_keys['openrouter'] if available
    2. Fall back to environment variable
    """
    client_api_key = None

    if api_keys:
        client_api_key = api_keys.get('openrouter')

    if not client_api_key:
        client_api_key = os.environ.get('OPENROUTER_API_KEY')

    if not client_api_key:
        raise ValueError(
            "OpenRouter API key not provided in api_keys dict and "
            "OPENROUTER_API_KEY environment variable not set"
        )

    # Optional attribution headers -- OpenRouter uses these for its rankings page.
    default_headers = {}
    referer = os.environ.get('OPENROUTER_SITE_URL')
    title = os.environ.get('OPENROUTER_APP_NAME')
    if referer:
        default_headers["HTTP-Referer"] = referer
    if title:
        default_headers["X-Title"] = title

    # A HUNG CALL MUST FAIL, NOT HANG.
    #
    # The SDK defaults to a 600s timeout with 2 retries, so one unresponsive
    # upstream can block a request for around half an hour. Observed live:
    # gunicorn sent nothing for 15 minutes, nginx gave up at its 900s
    # proxy_read_timeout, and the browser reported ERR_HTTP2_PROTOCOL_ERROR
    # with nothing in any server log - because nothing had failed yet.
    #
    # OpenRouter routes to third-party providers, so an upstream that accepts
    # the connection and then stalls is a normal event, not an exotic one.
    # LLM_TIMEOUT bounds a single attempt; one retry covers a transient stall
    # without doubling the worst case.
    openai_client = openai.OpenAI(
        api_key=client_api_key,
        base_url="https://openrouter.ai/api/v1",
        default_headers=default_headers or None,
        timeout=LLM_TIMEOUT,
        max_retries=LLM_MAX_RETRIES,
    )
    return openai_client


# ── Per-model routing, handed over by the dispatcher ──────────────────────
#
# Routing preferences are a fact about the MODEL and its hosts, so they live
# where per-model facts live: an optional "routing" object on the model's
# model_properties entry in LLM_CONFIG, passed VERBATIM as OpenRouter's
# `provider` object for that model. For example:
#
#   "deepseek/deepseek-v4-flash-0731": {
#       "capability": "reasoning", ...,
#       "routing": {"quantizations": ["fp8", "bf16"],
#                    "preferred_min_throughput": 40}}
#
# VERBATIM means no vocabulary of our own: the config author writes what
# that model's hosts accept, and a wrong field fails loudly as a 400 on
# that model only - blast radius of one seat, not the roster. Useful fields
# as of writing (OpenRouter's provider-routing docs are the authority):
#
#   order / allow_fallbacks   pin hosts; exclusive when fallbacks are off
#   ignore                    never these hosts
#   sort                      "price" | "throughput" | "latency". Disables
#                             load balancing - locks onto the winner, which
#                             also keeps the cache-writing host stable
#   max_price                 {"prompt": $/M, "completion": $/M}. Compared
#                             against each host's LISTED per-million rate -
#                             catalog data, not this request's cost - and a
#                             HARD gate: no qualifying host means the
#                             request FAILS rather than silently paying
#                             more. The ceiling sits beside the model's own
#                             prompt_tokens/completion_tokens rates in the
#                             same JSON object, so it is set in sight of
#                             the number it caps
#   quantizations             only these precisions - the open-model
#                             quality lever; hosts differ mainly by quant
#   preferred_min_throughput  soft floor: slower hosts are DEPRIORITIZED,
#                             not excluded, and load balancing survives.
#                             Doubles as the journal flag: any call that
#                             still MEASURED below it logs a warning naming
#                             the host (see _journal_serving)
#
# ABSENCE IS THE DEFAULT AND ABSENCE IS SAFE. A model with no routing key
# sends an untouched request - which is how a mixed roster works: DeepSeek
# seats carry quant filters and floors while Claude Fable 5, listed at
# $10/M on every host that serves it, carries nothing and is never at risk
# from a ceiling sized for a $0.09/M model. The env-var generation of these
# knobs (steps 14-15) died of exactly that globality, one review at a time.
#
# The dispatcher hands the dict over through set_model_routing() before
# EVERY dispatch, None included - worker threads are reused, and a stale
# dict left by the previous call would route this model with the last
# one's rules. threading.local keeps per-user configs per-user on a
# threaded server; same pattern, same reason, as prompt_cache's counters.

_routing_local = threading.local()


def set_model_routing(routing):
    """The dispatcher's hand-off: this model's routing object, or None.

    Called unconditionally before each dispatch; see the block comment
    above for the schema and the reasons. A copy is taken so nothing the
    request machinery does can write back into the user's config dict.
    """
    _routing_local.routing = dict(routing) if routing else None


def _model_routing():
    """What the dispatcher handed over for the model being served."""
    return getattr(_routing_local, "routing", None)


def set_reasoning_style(style):
    """The dispatcher's hand-off: how this model takes its reasoning dial.

    "effort" marks an effort-word model (GLM-5.3: levels low/high/max,
    reasoning mandatory); absent/None keeps the token-budget shape. Same
    per-thread side channel and same unconditional reset-before-dispatch
    discipline as set_model_routing above: worker threads are reused, and
    a stale style would dress the next model in this one's mode."""
    _routing_local.reasoning_style = (
        str(style).strip().lower() if style else None)


def _reasoning_style():
    """What the dispatcher handed over for the model being served."""
    return getattr(_routing_local, "reasoning_style", None)


# Rank order of the effort vocabulary, for snapping a requested level to
# a model's DECLARED set (2026-08-20): the dispatcher's default effort is
# "medium" and delve's worker seats inherit it, but effort-word models
# may not have that level (GLM-5.3: low/high/max) - sending an
# undeclared word verbatim is undefined mapping at best. A declared
# vocabulary snaps the request to the lowest declared level at or above
# it, or the highest declared level when the request exceeds them all.
_EFFORT_RANK = {"none": 0, "minimal": 1, "low": 2, "medium": 3,
                "high": 4, "xhigh": 5, "max": 6}


def set_reasoning_efforts(efforts):
    """The dispatcher's hand-off: the model's DECLARED effort vocabulary
    ("reasoning_efforts" on its properties entry), or None for models
    that take any word. Same per-thread side channel and unconditional
    reset-before-dispatch discipline as the routing and style hand-offs."""
    if efforts:
        _routing_local.reasoning_efforts = tuple(
            str(e).strip().lower() for e in efforts if str(e).strip())
    else:
        _routing_local.reasoning_efforts = None


def _reasoning_efforts():
    """What the dispatcher handed over for the model being served."""
    return getattr(_routing_local, "reasoning_efforts", None)


def _journal_serving(model, provider, tokens_per_second, completion_tokens,
                     elapsed_time):
    """One journal line per call naming which upstream served it, at what
    speed - the ignore/order levers have nothing to aim at without this.
    The model's own preferred_min_throughput (from its routing object, if
    any) doubles as the flag threshold: a call measured below it is a
    WARNING naming the host, so the journal accumulates the blocklist
    candidates by itself. Different models rightly carry different floors -
    40 tps is disappointing for a flash model and fine for a premium one.
    No floor on this model, no warning: opt-in per model like everything
    else in the routing object.
    """
    host = provider or "unknown"
    line = (f"OpenRouter: {model} served by {host} at "
            f"{tokens_per_second:.0f} tps "
            f"({completion_tokens} tokens in {elapsed_time:.1f}s)")
    floor = (_model_routing() or {}).get("preferred_min_throughput")
    try:
        slow = floor is not None and tokens_per_second < float(floor)
    except (TypeError, ValueError):
        slow = False
    if slow:
        logger.warning("%s - below this model's preferred_min_throughput "
                       "of %s; a repeat offender is a candidate for its "
                       "routing \"ignore\" list.", line, floor)
    else:
        logger.info(line)


def _reasoning_body(model, reasoning_models, effort, max_tokens, style=None):
    """The unified `reasoning` dict for OpenRouter, or None.

    Three lessons live here. (1) A HARD THINKING BUDGET, not just an
    effort hint, wherever we have one - one Investigator turn once
    spent its entire 64,000-token allowance in the hidden channel and
    emitted nothing; effort is a dial the model can talk itself past,
    max_tokens is the guard it cannot (the two keys are mutually
    exclusive on OpenRouter - sending both broke every call). Never
    more than half the allowance: the answer must still fit.
    (2) grok-4* endpoints refuse to disable reasoning - effort "none"
    came back 400 "Reasoning is mandatory ... cannot be disabled"
    (production, 2026-08-15, OpenRouter-only; native grok never sends
    a disable). The lowest legal dial goes instead, and the rewrite is
    put on the meta channel - the silent-rewrite lesson.
    (3) The family gate: a grok-4* model missing from the config's
    reasoning_models list still gets the budget - lagging lists must
    not reopen the hidden-channel burn."""
    listed = bool(reasoning_models) and model in reasoning_models
    if not (listed or _mandatory_reasoning(model)):
        return None
    if style == "effort":
        # EFFORT-WORD MODELS (2026-08-19, the GLM-5.3 floor). This
        # adapter's budget shape is converted by OpenRouter into an
        # effort level by its RATIO to max_tokens, and the
        # half-allowance clamp caps that ratio at 0.5 forever - a model
        # whose levels sit at 0.2/0.8/0.95 is pinned to its floor and
        # the tier's effort knob is structurally disconnected (production:
        # 529 completion tokens on a planner turn flash spent 1,349 on).
        # These models get the word itself, verbatim; the runaway guard
        # cannot apply here because a budget cannot be expressed, so the
        # bound is the provider's own level definitions. "none" is
        # rewritten to the floor - the grok-4* lesson: effort-word
        # families refuse to disable reasoning, and a 400 here kills the
        # seat. A DECLARED vocabulary ("reasoning_efforts" on the model's
        # properties entry, 2026-08-20) then snaps any undeclared word to
        # the nearest declared level, preferring up - the dispatcher's
        # default "medium" on a low/high/max model becomes "high", on the
        # meta channel like every other silent rewrite.
        # A DECLARED "none" (2026-09-10, DeepSeek V4.1 Flash: an effort
        # scale whose utility seats run reasoning-off) is sent as is - the
        # same request the budget path already sends for that family; the
        # rewrite to the floor stays for families that never declared it.
        requested = effort
        allowed = _reasoning_efforts()
        if effort == "none" and allowed and "none" in allowed:
            return {"effort": "none"}
        if effort == "none":
            effort = "low"
        if allowed and effort not in allowed:
            rank = _EFFORT_RANK.get(effort, _EFFORT_RANK["medium"])
            ups = [a for a in allowed if _EFFORT_RANK.get(a, -1) >= rank]
            effort = (min(ups, key=lambda a: _EFFORT_RANK[a]) if ups
                      else max(allowed,
                               key=lambda a: _EFFORT_RANK.get(a, -1)))
        if effort != requested:
            prompt_cache.record_meta(reasoning_effort=effort,
                                     reasoning_effort_requested=requested)
        return {"effort": effort}
    budget = THINKING_BUDGET.get(effort)
    if budget:
        return {"max_tokens": min(budget,
                                  max(1024, int((max_tokens or 0) * 0.5)))}
    if effort == "none" and _mandatory_reasoning(model):
        prompt_cache.record_meta(reasoning_effort="low",
                                 reasoning_effort_requested="none")
        return {"effort": "low"}
    return {"effort": effort}


def llm_call(messages: str, model: str, temperature: str, max_tokens: str, response_format: str = None, api_keys=None):
    """
    Make a call to OpenRouter's API with api_keys dictionary support
    """
    openai_client = init(api_keys)

    prompt_cache.reset()
    # OpenRouter forwards cache_control unchanged to the routes that take
    # explicit breakpoints: Anthropic models, and Gemini via the google/
    # slugs (2026-08-20 - implicit caching through this route missed a
    # 6.5-9.2k-token stable prefix six calls straight; see
    # prompt_cache.takes_cache_control). Everything else caches
    # implicitly and must NOT receive breakpoints.
    if prompt_cache.takes_cache_control(model):
        messages = prompt_cache.anthropic_messages(messages)
    _cache_body = {"usage": {"include": True}}   # needed to see cached_tokens
    # xAI via OpenRouter is the same affinity-sensitive cache as native
    # xAI: send the same conversation header so both transports share
    # one affinity (the flat cached-128 miss, 2026-08-15). None for
    # everyone else - unknown headers are dropped harmlessly, but only
    # grok needs it.
    _xai_hdrs = (prompt_cache.grok_headers()
                 if "grok" in (model or "").lower() else None)
    # The same routing preferences the streaming path sends - a lever that
    # skips the rare path is the partial-application disease.
    _pp = _model_routing()
    if _pp:
        _cache_body.setdefault("provider", {}).update(_pp)

    try:
        start_time = time.time()
        response = openai_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            extra_body=_cache_body,
            extra_headers=_xai_hdrs,
        )
        end_time = time.time()
    except openai.RateLimitError:
        time.sleep(10)
        start_time = time.time()
        response = openai_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            extra_body=_cache_body,
            extra_headers=_xai_hdrs,
        )
        end_time = time.time()

    elapsed_time = end_time - start_time

    content = (response.choices[0].message.content or "").strip()

    usage = getattr(response, 'usage', None)
    # prompt_tokens already INCLUDES cached tokens on OpenAI-compatible APIs,
    # so the total passes through unchanged; the split is recorded for pricing.
    _r, _w, prompt_tokens_used = prompt_cache.from_openai_usage(usage)
    completion_tokens_used = getattr(usage, 'completion_tokens', 0) or 0
    total_tokens_used = getattr(usage, 'total_tokens', 0) or (prompt_tokens_used + completion_tokens_used)

    if elapsed_time > 0:
        tokens_per_second = completion_tokens_used / elapsed_time
    else:
        tokens_per_second = 0

    _journal_serving(model, getattr(response, 'provider', None),
                     tokens_per_second, completion_tokens_used, elapsed_time)

    return content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second


def _tool_calls_as_text(tool_calls):
    """Text for tool calls the model emitted unasked. A call carrying code (a
    'code'/'python'/'script'/'source' argument, or a function named like an
    interpreter) becomes a fenced python block under the analyst's ACTION
    marker; anything else becomes its arguments, verbatim."""
    parts = []
    for tc in tool_calls:
        fn = (tc.get("function") or {})
        name = (fn.get("name") or "").lower()
        raw = fn.get("arguments") or ""
        code = None
        try:
            args = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            args = None
        if isinstance(args, dict):
            for key in ("code", "python", "script", "source", "cell", "command"):
                if isinstance(args.get(key), str) and args[key].strip():
                    code = args[key]
                    break
            if code is None and len(args) == 1:
                only = next(iter(args.values()))
                if isinstance(only, str) and ("\n" in only or "print(" in only or "import " in only):
                    code = only
        elif isinstance(args, str) and args.strip():
            code = args
        if code is None and args is None and any(k in name for k in ("python", "code", "exec", "interpreter", "repl")):
            code = raw
        if code is not None:
            parts.append("###ACTION###\nCELL\n```python\n" + code.rstrip() + "\n```")
        elif raw.strip():
            parts.append(raw)
    return "\n".join(parts)


def llm_stream(prompt_manager, log_and_call_manager, output_manager, chain_id: str, messages: str, model: str,
               temperature: str, max_tokens: str, tools: str = None, response_format: str = None,
               reasoning_models: list = None, reasoning_effort: str = "medium", api_keys=None,
               stop_event: threading.Event = None):
    """
    Stream responses from OpenRouter's API with complete tool calls and StoppableStreamWrapper support
    """
    collected_chunks = []
    collected_messages = []   # text from every round
    round_messages = []       # text from the current round only
    reasoning_messages = []
    tool_calls = []
    search_triplets = []
    google_search_messages = [{"role": "system", "content": prompt_manager.google_search_react_system.format(utils.get_readable_date())}]

    # Initialised up front so the exception handlers can always reference them.
    encoding = _get_encoding()
    start_time = time.time()
    elapsed_time = 0
    prompt_tokens_used = 0
    completion_tokens_used = 0
    total_tokens_used = 0
    tokens_per_second = 0
    usage_prompt = 0
    usage_completion = 0
    usage_total = 0
    saw_usage = False
    served_by = None      # the upstream host, read off the stream chunks

    style = _reasoning_style()
    effort = _normalise_effort(reasoning_effort, style)
    # Record what was ACTUALLY sent, and what was asked for when the two differ.
    # They diverged silently once: delv-e asked for "none" to turn thinking off
    # in the Executor seat, this layer rewrote it to "low", and the model spent
    # its whole budget thinking. Nothing in the log could have shown that.
    # max_tokens rides along so a `truncated` entry is interpretable on its own.
    _asked = str(reasoning_effort).lower() if reasoning_effort else None
    prompt_cache.record_meta(
        reasoning_effort=effort,
        reasoning_effort_requested=_asked if _asked and _asked != effort else None,
        max_tokens=max_tokens)

    openai_client = init(api_keys)

    # Define the available functions
    request_user_context = context_retrieval.request_user_context
    consult_assistant = context_retrieval.consult_assistant
    google_search_function = google_search.SmartSearchOrchestrator(api_keys=api_keys)

    available_functions = {
        "google_search": google_search_function,
        "request_user_context": request_user_context,
        "consult_assistant": consult_assistant
    }

    def add_triplet(query, result, links):
        '''Add a triplet to the search_triplets list'''
        triplet = {
            "query": query,
            "result": result,
            "links": links
        }
        search_triplets.append(triplet)

    def get_response(model, messages, temperature, max_tokens, active_tools, response_format,
                     reasoning_models=None, effort="medium"):
        """Helper function to create a streaming response from OpenRouter"""
        if _reasoning_body(model, reasoning_models, effort, max_tokens, style):
            output_manager.display_tool_info('Thinking', f"Model {model} needs a moment to think...", chain_id=chain_id)

        request_body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            # Ask for a final usage chunk so billing is based on the upstream
            # provider's real counts rather than a gpt-4 tiktoken estimate.
            "stream_options": {"include_usage": True},
        }

        if "grok" in (model or "").lower():
            # Same affinity as llm_call and native xAI. The streaming
            # path is the THIRD create site; skipping it would be the
            # partial-application disease this file already names.
            request_body["extra_headers"] = prompt_cache.grok_headers()

        extra_body = {"usage": {"include": True}}
        # Anthropic-family models routed through OpenRouter take explicit
        # breakpoints; implicit-cache models must not be sent them.
        if prompt_cache.takes_cache_control(model):
            request_body["messages"] = prompt_cache.anthropic_messages(
                request_body.get("messages", messages))

        # Add tools if provided
        if active_tools:
            request_body["tools"] = active_tools
            # Stop OpenRouter's fallback routing from landing on an upstream that
            # silently ignores the `tools` parameter.
            extra_body["provider"] = {"require_parameters": True}

        # Add response format if provided
        if response_format:
            request_body["response_format"] = response_format

        _rbody = _reasoning_body(model, reasoning_models, effort,
                                 max_tokens, style)
        if _rbody:
            extra_body["reasoning"] = _rbody

        _pp = _model_routing()
        if _pp:
            extra_body.setdefault("provider", {}).update(_pp)

        request_body["extra_body"] = extra_body

        # RETRY A MID-STREAM DROP.
        #
        # The SDK's own max_retries only covers failures BEFORE the stream
        # opens. Once tokens are flowing, an upstream that dies raises straight
        # through - seen as "APIError: Upstream error from Ambient", which killed
        # a chain and, through auto_explore, the whole exploration. OpenRouter
        # fans out to third-party providers, so this is a normal event.
        #
        # Only the OPENING is retried here; a stream that breaks after emitting
        # tokens is handled by the caller, which cannot resume mid-answer.
        last_exc = None
        for attempt in range(STREAM_OPEN_RETRIES + 1):
            try:
                return openai_client.chat.completions.create(**request_body)
            except openai.APIError as exc:
                last_exc = exc
                if attempt >= STREAM_OPEN_RETRIES:
                    break
                delay = STREAM_RETRY_BACKOFF * (attempt + 1)
                log_message = (f"Upstream error opening the stream "
                               f"({type(exc).__name__}: {exc}); retrying in "
                               f"{delay}s")
                try:
                    output_manager.display_system_messages(log_message)
                except Exception:                               # noqa: BLE001
                    pass
                time.sleep(delay)
        raise last_exc

    def dispatch_tool_calls(pending_tool_calls):
        """
        Execute each tool call and append the assistant + tool messages.

        Every tool_call_id MUST receive a matching `role: "tool"` reply, otherwise
        the follow-up request is rejected for having a dangling call. So failures
        (unknown function, malformed arguments) are reported back as tool content
        rather than skipped.
        """
        messages.append({
            "role": "assistant",
            "content": None,          # some upstreams reject a message with no content key
            "tool_calls": pending_tool_calls,
        })

        for tool_call in pending_tool_calls:
            function_name = tool_call['function']['name']
            function_to_call = available_functions.get(function_name)
            function_response = None
            function_args = None

            try:
                function_args = json.loads(tool_call['function']['arguments'] or "{}")
            except json.JSONDecodeError as e:
                logger.warning(f"Malformed tool arguments for {function_name}: {e}")
                function_response = f"Error: could not parse arguments for {function_name} ({e}). Please retry with valid JSON."

            if function_response is None and not function_to_call:
                output_manager.display_system_messages(f"Warning: Unknown function {function_name}")
                function_response = f"Error: unknown function '{function_name}'. Available functions: {', '.join(available_functions)}."

            if function_response is None:
                try:
                    if function_name == "google_search":
                        google_search_messages.append({"role": "user", "content": function_args.get("search_query")})
                        function_response, links = function_to_call(
                            prompt_manager,
                            log_and_call_manager,
                            output_manager,
                            chain_id,
                            messages=google_search_messages
                        )
                        add_triplet(function_args.get("search_query"), function_response, links)

                    elif function_name == "request_user_context":
                        function_response = function_to_call(
                            output_manager,
                            log_and_call_manager,
                            chain_id,
                            function_args.get("query_clarification"),
                            function_args.get("context_needed")
                        )

                    elif function_name == "consult_assistant":
                        function_response = function_to_call(
                            output_manager,
                            log_and_call_manager,
                            chain_id,
                            function_args.get("analytical_goal"),
                            function_args.get("data_context"),
                            function_args.get("decision_point"),
                            function_args.get("options_considered"),
                            function_args.get("plan_constraints"),
                            reasoning_models,
                            api_keys
                        )
                except Exception as e:
                    logger.warning(f"Tool '{function_name}' raised: {e}")
                    function_response = f"Error: '{function_name}' failed ({e})."

            # Add tool response to messages
            messages.append({
                "tool_call_id": tool_call['id'],
                "role": "tool",
                "name": function_name,
                "content": function_response if isinstance(function_response, str) else str(function_response),
            })

    try:
        # Fallback prompt token estimate, replaced by real usage when it arrives.
        prompt_tokens_used = _estimate_prompt_tokens(messages, encoding)

        active_tools = tools
        truncated = False

        # Get the first stream.
        #
        # _restartable reopens it if the provider closes the connection before
        # sending anything - a distinct failure from one that never opens, and
        # one that cost a whole question in the field.
        def _open_stream():
            return StoppableStreamWrapper(
                get_response(model, messages, temperature, max_tokens,
                             active_tools, response_format, reasoning_models,
                             effort),
                stop_event)

        stoppable_stream = _restartable(_open_stream, output_manager, chain_id)

        iteration = 0

        while True:
            iteration += 1
            tool_calls = []      # Reset for each iteration
            round_messages = []  # Reset for each iteration

            # Process the current stream
            for chunk in stoppable_stream:
                collected_chunks.append(chunk)

                # OpenRouter stamps every chunk with the upstream that is
                # serving it. Keep the last one seen: on a multi-round tool
                # loop that is the host that produced the final answer, and
                # on the overwhelmingly common single round they are all the
                # same. Without this the 9tps host has no name and the
                # ignore/order levers have nothing to aim at.
                served_by = getattr(chunk, 'provider', None) or served_by

                # The usage chunk typically arrives last and carries no choices.
                chunk_usage = getattr(chunk, 'usage', None)
                if chunk_usage:
                    saw_usage = True
                    # from_openai_usage reads prompt_tokens_details.cached_tokens
                    # and records it on the side channel that write_to_log
                    # prices. Reading the three top-level fields directly - as
                    # this did - throws the cache split away, so every STREAMING
                    # agent reported zero cached tokens while the non-streaming
                    # llm_call path (which does call it) reported them correctly.
                    # That is why only Executor rows showed a cache hit.
                    prompt_cache.from_openai_usage(chunk_usage)
                    usage_prompt += getattr(chunk_usage, 'prompt_tokens', 0) or 0
                    usage_completion += getattr(chunk_usage, 'completion_tokens', 0) or 0
                    usage_total += getattr(chunk_usage, 'total_tokens', 0) or 0

                if chunk.choices and len(chunk.choices) > 0:
                    # TRUNCATION WAS INVISIBLE.
                    #
                    # finish_reason == "length" means the model hit max_tokens
                    # mid-answer. Nothing read it, so a half-written response was
                    # returned as if complete and the caller failed later on
                    # unparseable output - which presents as a stall rather than
                    # an error. On a reasoning model the thinking is charged to
                    # the same budget, so a seat can spend it all before writing
                    # anything at all.
                    if getattr(chunk.choices[0], 'finish_reason', None) == 'length':
                        truncated = True
                        prompt_cache.record_meta(truncated=True)

                    delta = chunk.choices[0].delta
                    if not delta:
                        continue

                    # Handle content. These are independent `if`s, not `elif`s:
                    # some upstreams put content and tool_calls in the same delta.
                    if getattr(delta, 'content', None):
                        collected_messages.append(delta.content)
                        round_messages.append(delta.content)
                        output_manager.print_wrapper(delta.content, end='', flush=True, chain_id=chain_id)

                    # Handle reasoning (for reasoning models).
                    #
                    # thought=True routes this into the collapsible block that
                    # get_response already opened for a reasoning model. Without
                    # it the reasoning went to data.text and appended raw to the
                    # pane, so every reasoning agent dumped its thinking into
                    # the output while its Thinking block sat there empty.
                    # `delta.content` is deliberately NOT marked: that is the
                    # answer, and it belongs in the pane.
                    _rt = _reasoning_delta_text(delta)
                    if _rt:
                        reasoning_messages.append(_rt)
                        output_manager.print_wrapper(_rt, end='', flush=True, chain_id=chain_id, thought=True)

                    # Handle tool calls
                    if getattr(delta, 'tool_calls', None):
                        for tcchunk in delta.tool_calls:
                            # `index` is optional on some upstreams; assume slot 0.
                            idx = getattr(tcchunk, 'index', None)
                            if idx is None:
                                idx = 0

                            while len(tool_calls) <= idx:
                                tool_calls.append({
                                    "id": "",
                                    "type": "function",
                                    "function": {"name": "", "arguments": ""}
                                })
                            tc = tool_calls[idx]

                            if getattr(tcchunk, 'id', None):
                                tc["id"] += tcchunk.id
                            if getattr(tcchunk, 'type', None):
                                tc["type"] = tcchunk.type

                            # The opening chunk often carries only id/type, with no
                            # `function` attribute at all.
                            fn = getattr(tcchunk, 'function', None)
                            if fn:
                                if getattr(fn, 'name', None):
                                    tc["function"]["name"] += fn.name
                                if getattr(fn, 'arguments', None):
                                    tc["function"]["arguments"] += fn.arguments

            # Drop any slots that never received an id or a name.
            tool_calls = [tc for tc in tool_calls if tc["id"] and tc["function"]["name"]]

            # A tool call when NO tools were offered is the provider intercepting the
            # model's own text (2026-09-05, Muse: the analyst's Python cell came back as
            # a code-interpreter call with empty content, every other turn). It is not
            # dispatched - there is nothing to dispatch to - it is turned back into the
            # text it was: a fenced python block for a code call, the raw arguments else.
            if tool_calls and not active_tools:
                salvaged = _tool_calls_as_text(tool_calls)
                if salvaged:
                    logger.warning("OpenRouter: %s emitted %d native tool call(s) with no tools offered; "
                                   "returned as text (%d chars)", model, len(tool_calls), len(salvaged))
                    collected_messages.append(salvaged)
                    round_messages.append(salvaged)
                break

            # If no tool calls, we're done
            if not tool_calls:
                break

            # Execute the tool calls and append their results
            dispatch_tool_calls(tool_calls)

            if iteration >= MAX_TOOL_ITERATIONS:
                # Force a plain text answer instead of abandoning an unconsumed
                # stream (or looping forever).
                logger.warning(
                    f"Tool call limit ({MAX_TOOL_ITERATIONS}) reached for agent model {model}; "
                    "requesting a final answer without tools."
                )
                output_manager.display_system_messages(
                    "Warning: tool call limit reached. Requesting a final answer without tools."
                )
                active_tools = None

            # Get the next stream after processing tool calls. `messages` and
            # `active_tools` have changed, so the closure is rebuilt.
            def _open_stream():
                return StoppableStreamWrapper(
                    get_response(model, messages, temperature, max_tokens,
                                 active_tools, response_format,
                                 reasoning_models, effort),
                    stop_event)

            stoppable_stream = _restartable(_open_stream, output_manager, chain_id)

        end_time = time.time()
        elapsed_time = end_time - start_time

        output_manager.print_wrapper("", chain_id=chain_id)

        # Get the complete text received
        if RETURN_FINAL_ROUND_ONLY and round_messages:
            full_reply_content = ''.join(round_messages)
        else:
            full_reply_content = ''.join([m for m in collected_messages])
        reasoning = ''.join([m for m in reasoning_messages])

        # An empty answer with tokens billed (2026-09-05, Muse: every other turn)
        # is one of two things: the provider intercepted the text as a tool call
        # (handled above), or the model wrote its whole reply into the reasoning
        # channel and stopped. Say which in the journal, and in the second case
        # use the reasoning as the reply - it IS the answer, misfiled.
        if not full_reply_content.strip():
            _fr = None
            for _ch in reversed(collected_chunks):
                try:
                    _fr = _ch.choices[0].finish_reason
                    if _fr:
                        break
                except Exception:                                # noqa: BLE001
                    continue
            logger.warning("OpenRouter: %s returned no content (finish_reason=%s, reasoning %d chars, "
                           "%d tool call(s), %d chunks)%s", model, _fr, len(reasoning), len(tool_calls),
                           len(collected_chunks), (": " + reasoning[:240].replace("\n", " ")) if reasoning else "")
            if reasoning and any(m in reasoning for m in ("###ACTION###", "###NOTE###", "```python")):
                logger.warning("OpenRouter: the reply was in the reasoning channel; using it as the answer")
                full_reply_content = reasoning


        # Prefer the provider's own accounting; fall back to tiktoken.
        if saw_usage:
            prompt_tokens_used = usage_prompt
            completion_tokens_used = usage_completion
            total_tokens_used = usage_total or (usage_prompt + usage_completion)
        else:
            completion_tokens_used = len(encoding.encode(full_reply_content + reasoning))
            total_tokens_used = prompt_tokens_used + completion_tokens_used

        if elapsed_time > 0:
            tokens_per_second = completion_tokens_used / elapsed_time
        else:
            tokens_per_second = 0

    except openai.APIError as e:
        error_message = str(e)
        output_manager.display_system_messages(f"OpenRouter API Error: {error_message}")
        raise
    except Exception as e:
        if isinstance(e, StopIteration) and "cleanup request" in str(e):
            output_manager.display_system_messages("INFO: The process was stopped by the server.")
            # Return partial results
            full_reply_content = ''.join([m for m in collected_messages])
            reasoning = ''.join([m for m in reasoning_messages])
            elapsed_time = time.time() - start_time
            if saw_usage:
                prompt_tokens_used = usage_prompt
                completion_tokens_used = usage_completion
                total_tokens_used = usage_total or (usage_prompt + usage_completion)
            else:
                completion_tokens_used = len(encoding.encode(full_reply_content + reasoning))
                total_tokens_used = prompt_tokens_used + completion_tokens_used
            tokens_per_second = completion_tokens_used / elapsed_time if elapsed_time > 0 else 0
        else:
            output_manager.display_system_messages(f"Unexpected error: {str(e)}")
            raise

    # The journal names the host and its speed, every call - covering the
    # normal exit and the server-stop salvage alike, since both fall through
    # here on their way to the returns.
    _journal_serving(model, served_by, tokens_per_second,
                     completion_tokens_used, elapsed_time)

    # Say so when the answer was cut off. It cannot be fixed here - the caller
    # owns the retry - but a truncated response that looks complete is the
    # difference between "the run stalled" and "the Result Evaluator hit its
    # token limit", and only one of those is actionable.
    if truncated:
        message = (f"{model} hit its {max_tokens}-token limit and its "
                   f"answer was cut off. Raise max_tokens for that agent in "
                   f"LLM_CONFIG if this recurs.")
        try:
            output_manager.display_system_messages(message, chain_id=chain_id)
        except Exception:                                       # noqa: BLE001
            pass
        try:
            from logger_config import get_logger
            get_logger(__name__).warning(message)
        except Exception:                                       # noqa: BLE001
            pass

    # Return format depends on whether tools were used
    if tools:
        return full_reply_content, search_triplets, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second
    else:
        return full_reply_content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second