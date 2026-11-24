import os
import threading
import time
import openai

from bambooai.utils import StoppableStreamWrapper

# The dispatcher's turn-level retry catches exactly these; see models/__init__.
TRANSPORT_ERRORS = (openai.APIError,)

from logger_config import get_logger
logger = get_logger(__name__)


from bambooai.models import prompt_cache
from bambooai.models import resilience


def init(api_keys=None):
    """
    Initialize xAI Grok client using OpenAI SDK with xAI's base URL.
    
    API key precedence:
    1. Use api_keys['xai'] if available (future use)
    2. Fall back to XAI_API_KEY environment variable
    
    Uses OpenAI SDK pointed at xAI's Responses API endpoint.
    """
    client_api_key = os.environ.get('XAI_API_KEY')
    if client_api_key is None:
        raise ValueError(
            "xAI API key not provided in api_keys dict and "
            "XAI_API_KEY environment variable not set"
        )
    # timeout_kwargs bounds a single attempt: without it the SDK waits 600s
    # and retries twice, so one stalled upstream blocks for half an hour.
    return openai.OpenAI(
        api_key=client_api_key,
        base_url="https://api.x.ai/v1",
        **resilience.timeout_kwargs("openai")
    )


def _convert_messages_to_input(messages):
    """
    Convert Chat Completions messages list to Responses API input format.
    
    Unlike the OpenAI Responses module, xAI does NOT support the 'instructions'
    parameter — the API will error if it is specified.  System messages are kept
    inline in the input array instead.
    
    Returns a list of input items (system, user, assistant roles preserved).
    """
    input_items = []
    for msg in messages:
        role = msg.get('role')
        content = msg.get('content', '')
        if role in ('system', 'user', 'assistant'):
            input_items.append({"role": role, "content": content})
    return input_items


# ---------------------------------------------------------------------------
# Reasoning model registry
# ---------------------------------------------------------------------------
# grok-4 family reasoning models always reason but do NOT accept
# reasoning_effort.  We request reasoning summaries so the thinking
# trace can be surfaced to the user.
NATIVE_REASONING_MODELS = {
    "grok-4",
    "grok-4-1-fast-reasoning",
    "grok-code-fast-1",
    "grok-4-fast-reasoning",
}


def _is_native_reasoning(model):
    """Exact strings miss every new slug (grok-4.5 and grok-4.6 both
    leaked temperature, 2026-08-15). Family rule: every grok-4* model
    reasons natively unless the slug says otherwise; the set keeps the
    odd family members."""
    m = (model or "").split("/")[-1].lower()
    return (m in NATIVE_REASONING_MODELS
            or (m.startswith("grok-4") and "non-reasoning" not in m))


# ---------------------------------------------------------------------------
# Non-streaming call
# ---------------------------------------------------------------------------

def llm_call(messages: str, model: str, temperature: str, max_tokens: str,
             response_format: str = None, api_keys=None):
    """
    Non-streaming Responses API call via xAI.
    Return signature matches the existing grok_models.llm_call exactly.
    """
    client = init(api_keys)
    input_items = _convert_messages_to_input(messages)

    prompt_cache.reset()
    kwargs = dict(
        model=model,
        input=input_items,
        max_output_tokens=max_tokens,
        store=False,                       # Never store on xAI servers
        # xAI caches automatically but is affinity-sensitive: without a stable
        # conversation id, requests land on different backends and hit rates
        # collapse even for byte-identical prefixes.
        extra_headers=prompt_cache.grok_headers(),
    )

    # Reasoning models: skip temperature (grok-4 always reasons internally
    # but does not expose readable reasoning content via the API)
    if _is_native_reasoning(model):
        pass
    else:
        if temperature is not None:
            kwargs["temperature"] = temperature

    if response_format:
        kwargs["text"] = {"format": response_format}

    try:
        start_time = time.time()
        response = client.responses.create(**kwargs)
        end_time = time.time()
    except openai.RateLimitError:
        time.sleep(10)
        start_time = time.time()
        response = client.responses.create(**kwargs)
        end_time = time.time()

    elapsed_time = end_time - start_time
    content = response.output_text or ""

    _r, _w, prompt_tokens_used = prompt_cache.from_responses_usage(response.usage)
    completion_tokens_used = response.usage.output_tokens if response.usage else 0
    total_tokens_used = prompt_tokens_used + completion_tokens_used
    tokens_per_second = (
        completion_tokens_used / elapsed_time if elapsed_time > 0 else 0
    )

    return (content, messages, prompt_tokens_used, completion_tokens_used,
            total_tokens_used, elapsed_time, tokens_per_second)


# ---------------------------------------------------------------------------
# Streaming call
# ---------------------------------------------------------------------------

def llm_stream(prompt_manager, log_and_call_manager, output_manager,
               chain_id: str, messages: str, model: str, temperature: str,
               max_tokens: str, tools: str = None, response_format: str = None,
               reasoning_models: list = None, reasoning_effort: str = "medium",
               api_keys=None, stop_event: threading.Event = None):
    # What the request was configured with, into the run log.
    resilience.record_request(
        reasoning_effort=reasoning_effort,
        max_tokens=max_tokens)
    """
    Streaming Responses API call via xAI. `tools` is the Web Search seat's: this adapter runs no search, and takes none.
    Return signature matches the existing grok_models.llm_stream exactly.
    
    Key xAI differences from the OpenAI Responses module:
    - No 'instructions' param (system messages stay inline)
    - store=False to prevent server-side storage
    - grok-4 family reasoning models always reason; reasoning_effort
      is NOT sent (would cause an error).  We request reasoning
      summaries via {"summary": "auto"} instead.
    """
    collected_messages = []

    client = init(api_keys)

    # --- Convert from internal message format ---
    input_items = _convert_messages_to_input(messages)

    # ------------------------------------------------------------------
    # Request builder
    # ------------------------------------------------------------------
    def build_kwargs(input_data):
        """
        Build request kwargs for the streaming call. store=False: nothing is kept on xAI's servers.
        """
        kw = dict(
            model=model,
            input=input_data,
            stream=True,
            store=False,                   # Never store on xAI servers
        )

        # Reasoning: grok-4 family models always reason internally
        # but do not expose readable reasoning content via the API.
        # Skip temperature for reasoning models.
        if _is_native_reasoning(model):
            output_manager.display_tool_info(
                'Thinking',
                'Native reasoning (no effort control)',
                chain_id=chain_id,
            )
        else:
            # Non-reasoning models: apply temperature
            if temperature is not None:
                kw["temperature"] = temperature

        kw["max_output_tokens"] = max_tokens

        if response_format:
            kw["text"] = {"format": response_format}

        return kw

    # ------------------------------------------------------------------
    # Stream processor
    # ------------------------------------------------------------------
    def process_stream(stream):
        """
        Iterate over a Responses API event stream.
        Populates collected_messages. Returns (prompt_tokens, completion_tokens).

        Handles ALL known reasoning event types since xAI may emit
        different events than OpenAI:
        - response.reasoning_text.delta        (raw reasoning text)
        - response.reasoning_summary_text.delta (reasoning summaries)
        """
        usage_prompt = usage_completion = 0
        thinking_buffer = []

        for event in stream:
            # Log event types for debugging (reasoning troubleshooting)
            logger.debug(f"xAI stream event: {event.type}")

            # -- Raw reasoning text deltas (xAI's primary reasoning output) --
            if event.type == "response.reasoning_text.delta":
                thinking_buffer.append(event.delta)

            elif event.type == "response.reasoning_text.done":
                if thinking_buffer:
                    thought_text = ''.join(thinking_buffer)
                    output_manager.print_wrapper(
                        thought_text, end="", flush=True,
                        chain_id=chain_id, thought=True,
                    )
                    thinking_buffer = []

            # -- Reasoning summary deltas (OpenAI-style, may be emitted) --
            elif event.type == "response.reasoning_summary_text.delta":
                thinking_buffer.append(event.delta)

            elif event.type == "response.reasoning_summary_text.done":
                if thinking_buffer:
                    thought_text = ''.join(thinking_buffer)
                    output_manager.print_wrapper(
                        thought_text, end="", flush=True,
                        chain_id=chain_id, thought=True,
                    )
                    thinking_buffer = []

            # -- Regular content deltas --
            elif event.type == "response.output_text.delta":
                collected_messages.append(event.delta)
                output_manager.print_wrapper(
                    event.delta, end="", flush=True, chain_id=chain_id,
                )

            # -- Response completed (carries usage data) --
            elif event.type == "response.completed":
                if event.response.usage:
                    _r, _w, usage_prompt = prompt_cache.from_responses_usage(
                        event.response.usage)
                    usage_completion = event.response.usage.output_tokens

            # -- Response INCOMPLETE: the answer was cut off --
            #
            # The Responses API does not set finish_reason == "length"; a
            # capped response arrives as its own terminal event with
            # status "incomplete" and incomplete_details naming the cause.
            # This event was silently ignored, so a truncated answer was
            # returned as if complete - the caller then failed later on
            # unparseable output, which presents as a stall, not a limit -
            # and its usage went unrecorded, under-billing the turn.
            elif event.type == "response.incomplete":
                resp = getattr(event, "response", None)
                if resp is not None and getattr(resp, "usage", None):
                    _r, _w, usage_prompt = prompt_cache.from_responses_usage(
                        resp.usage)
                    usage_completion = resp.usage.output_tokens
                details = getattr(resp, "incomplete_details", None)
                reason = getattr(details, "reason", None) or "unknown"
                if reason == "max_output_tokens":
                    resilience.report_truncation(model, max_tokens,
                                                 output_manager, chain_id)
                else:
                    logger.warning("xAI response incomplete (%s); the answer "
                                   "was cut off.", reason)
                    prompt_cache.record_meta(truncated=True)

        # Flush any remaining buffered thoughts (safety net)
        if thinking_buffer:
            thought_text = ''.join(thinking_buffer)
            output_manager.print_wrapper(
                thought_text, end="", flush=True,
                chain_id=chain_id, thought=True,
            )

        return usage_prompt, usage_completion

    # ------------------------------------------------------------------
    # Main streaming loop
    # ------------------------------------------------------------------
    try:
        combined_prompt = 0
        combined_completion = 0

        start_time = time.time()

        # First request
        # PRE-TOKEN STREAM RESTART (generic; see resilience.restartable).
        # xAI can accept the request and then drop the connection before
        # emitting anything. Before the first chunk a fresh stream is exactly
        # equivalent, so the open and the pre-token window are retried; a
        # later drop stays fatal because the answer cannot be resumed.
        raw_stream = resilience.restartable(
            lambda: client.responses.create(**build_kwargs(input_items)),
            openai.APIError, output_manager=output_manager,
            chain_id=chain_id, label="xAI")
        stream = StoppableStreamWrapper(raw_stream, stop_event)
        p_tok, c_tok = process_stream(stream)
        combined_prompt += p_tok
        combined_completion += c_tok

        end_time = time.time()
        elapsed_time = end_time - start_time

    except openai.APIError as e:
        error_message = (
            e.body.get('message') if isinstance(e.body, dict)
            else str(e.body or e)
        )
        output_manager.display_system_messages(
            f"xAI Grok API Error: {error_message}"
        )
        raise
    except Exception as e:
        if isinstance(e, StopIteration) and "cleanup request" in str(e):
            output_manager.display_system_messages(
                "INFO: The process was stopped by the server."
            )
            # Return partial results
            full_reply_content = ''.join(collected_messages)
            elapsed_time = time.time() - start_time
            combined_total = combined_prompt + combined_completion
            tokens_per_second = (
                combined_completion / elapsed_time if elapsed_time > 0 else 0
            )
            output_manager.print_wrapper("", chain_id=chain_id)
            return (full_reply_content, messages,
                    combined_prompt, combined_completion, combined_total,
                    elapsed_time, tokens_per_second)
        else:
            output_manager.display_system_messages(
                f"xAI Grok API Error: {str(e)}"
            )
            raise

    output_manager.print_wrapper("", chain_id=chain_id)

    full_reply_content = ''.join(collected_messages)
    combined_total = combined_prompt + combined_completion
    tokens_per_second = (
        combined_completion / elapsed_time if elapsed_time > 0 else 0
    )

    return (full_reply_content, messages,
            combined_prompt, combined_completion, combined_total,
            elapsed_time, tokens_per_second)