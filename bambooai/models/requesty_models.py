"""Requesty: an OpenAI-compatible LLM gateway, reached through the OpenAI SDK.

Model ids are the gateway's own, e.g. "openai/gpt-4o-mini" or
"anthropic/claude-sonnet-4-5". Keys: https://app.requesty.ai/api-keys,
docs: https://docs.requesty.ai. REQUESTY_BASE_URL picks a regional router
(https://router.eu.requesty.ai/v1 keeps traffic in the EU).

Generic hardening comes from resilience.py. The OpenRouter-only parts of
openrouter_models (its `provider` routing object, `usage.include`, the
`reasoning` body and its THINKING_BUDGET table) are deliberately not copied:
Requesty takes the standard `reasoning_effort` parameter instead.
"""

import json
import os
import threading
import time
import openai
import tiktoken

from bambooai import google_search, utils, context_retrieval
from bambooai.utils import StoppableStreamWrapper

# The dispatcher's turn-level retry catches exactly these; see models/__init__.
TRANSPORT_ERRORS = (openai.APIError,)

from logger_config import get_logger
logger = get_logger(__name__)

from bambooai.models import prompt_cache
from bambooai.models import resilience

DEFAULT_BASE_URL = "https://router.requesty.ai/v1"

# Hard ceiling on tool-call round trips before we force a plain text answer.
MAX_TOOL_ITERATIONS = 10

_EFFORT_ALIASES = {"default": "medium", "off": "none"}
_EFFORT_WORDS = {"none", "minimal", "low", "medium", "high", "xhigh", "max"}


def init(api_keys=None):
    """
    Initialize Requesty client with API key precedence:
    1. Use api_keys['requesty'] if available
    2. Fall back to environment variable
    """
    client_api_key = None

    if api_keys:
        client_api_key = api_keys.get('requesty')

    if not client_api_key:
        client_api_key = os.environ.get('REQUESTY_API_KEY')

    if not client_api_key:
        raise ValueError(
            "Requesty API key not provided in api_keys dict and "
            "REQUESTY_API_KEY environment variable not set"
        )

    # Optional attribution headers, same as the OpenRouter provider.
    default_headers = {}
    referer = os.environ.get('REQUESTY_SITE_URL')
    title = os.environ.get('REQUESTY_APP_NAME')
    if referer:
        default_headers["HTTP-Referer"] = referer
    if title:
        default_headers["X-Title"] = title

    return openai.OpenAI(
        api_key=client_api_key,
        base_url=os.environ.get('REQUESTY_BASE_URL') or DEFAULT_BASE_URL,
        default_headers=default_headers or None,
        **resilience.timeout_kwargs("openai"),
    )


def _normalise_effort(effort):
    """The seat's effort word as Requesty takes it; garbage becomes medium."""
    if not effort:
        return "medium"
    effort = str(effort).strip().lower()
    effort = _EFFORT_ALIASES.get(effort, effort)
    return effort if effort in _EFFORT_WORDS else "medium"


def _get_encoding():
    """tiktoken encoder used only as a fallback when no usage is returned."""
    try:
        return tiktoken.encoding_for_model("gpt-4")
    except Exception:
        return tiktoken.get_encoding("cl100k_base")


def llm_call(messages: str, model: str, temperature: str, max_tokens: str, response_format: str = None, api_keys=None):
    """
    Make a call to Requesty's API with api_keys dictionary support
    """
    openai_client = init(api_keys)
    prompt_cache.reset()

    def get_response():
        return openai_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )

    try:
        start_time = time.time()
        response = get_response()
        end_time = time.time()
    except openai.RateLimitError:
        time.sleep(10)
        start_time = time.time()
        response = get_response()
        end_time = time.time()

    elapsed_time = end_time - start_time

    content = (response.choices[0].message.content or "").strip()

    usage = getattr(response, 'usage', None)
    # prompt_tokens already INCLUDES cached tokens on OpenAI-compatible APIs,
    # so the total passes through unchanged; the split is recorded for pricing.
    _r, _w, prompt_tokens_used = prompt_cache.from_openai_usage(usage)
    completion_tokens_used = getattr(usage, 'completion_tokens', 0) or 0
    total_tokens_used = getattr(usage, 'total_tokens', 0) or (prompt_tokens_used + completion_tokens_used)

    tokens_per_second = completion_tokens_used / elapsed_time if elapsed_time > 0 else 0

    return content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second


def llm_stream(prompt_manager, log_and_call_manager, output_manager, chain_id: str, messages: str, model: str,
               temperature: str, max_tokens: str, tools: str = None, response_format: str = None,
               reasoning_models: list = None, reasoning_effort: str = "medium", api_keys=None,
               stop_event: threading.Event = None):
    """
    Stream responses from Requesty's API with tool calls and StoppableStreamWrapper support
    """
    collected_messages = []
    reasoning_messages = []
    search_triplets = []
    google_search_messages = [{"role": "system", "content": prompt_manager.google_search_react_system.format(utils.get_readable_date())}]

    encoding = _get_encoding()
    start_time = time.time()
    elapsed_time = 0
    prompt_tokens_used = 0
    completion_tokens_used = 0
    total_tokens_used = 0
    usage_prompt = 0
    usage_completion = 0
    usage_total = 0
    saw_usage = False
    truncated = False

    reasoning = bool(reasoning_models) and model in reasoning_models
    effort = _normalise_effort(reasoning_effort)
    resilience.record_request(reasoning_effort=effort if reasoning else None,
                              max_tokens=max_tokens,
                              requested=str(reasoning_effort).lower() if reasoning and reasoning_effort else None)

    openai_client = init(api_keys)

    available_functions = {
        "google_search": google_search.SmartSearchOrchestrator(api_keys=api_keys),
        "request_user_context": context_retrieval.request_user_context,
        "consult_assistant": context_retrieval.consult_assistant,
    }

    def get_response(active_tools):
        request_body = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        if active_tools:
            request_body["tools"] = active_tools
        if response_format:
            request_body["response_format"] = response_format
        if reasoning:
            request_body["reasoning_effort"] = effort
        return openai_client.chat.completions.create(**request_body)

    def dispatch_tool_calls(pending_tool_calls):
        """Execute each tool call; every tool_call_id gets a `tool` reply."""
        messages.append({
            "role": "assistant",
            "content": None,
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
                        search_triplets.append({"query": function_args.get("search_query"),
                                                "result": function_response, "links": links})

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

            messages.append({
                "tool_call_id": tool_call['id'],
                "role": "tool",
                "name": function_name,
                "content": function_response if isinstance(function_response, str) else str(function_response),
            })

    try:
        if reasoning:
            output_manager.display_tool_info('Thinking', f"Reasoning Effort: {effort}", chain_id=chain_id)

        active_tools = tools
        iteration = 0

        while True:
            iteration += 1
            tool_calls = []
            raw_stream = resilience.restartable(
                lambda: get_response(active_tools), openai.APIError,
                output_manager=output_manager, chain_id=chain_id, label="Requesty")

            for chunk in StoppableStreamWrapper(raw_stream, stop_event):
                chunk_usage = getattr(chunk, 'usage', None)
                if chunk_usage:
                    saw_usage = True
                    prompt_cache.from_openai_usage(chunk_usage)
                    usage_prompt += getattr(chunk_usage, 'prompt_tokens', 0) or 0
                    usage_completion += getattr(chunk_usage, 'completion_tokens', 0) or 0
                    usage_total += getattr(chunk_usage, 'total_tokens', 0) or 0

                if not chunk.choices:
                    continue
                if getattr(chunk.choices[0], 'finish_reason', None) == 'length':
                    truncated = True

                delta = chunk.choices[0].delta
                if not delta:
                    continue

                if getattr(delta, 'content', None):
                    collected_messages.append(delta.content)
                    output_manager.print_wrapper(delta.content, end='', flush=True, chain_id=chain_id)

                # thought=True routes the reasoning into the collapsible
                # Thinking block rather than the answer pane.
                _rt = getattr(delta, 'reasoning_content', None) or getattr(delta, 'reasoning', None)
                if _rt:
                    reasoning_messages.append(_rt)
                    output_manager.print_wrapper(_rt, end='', flush=True, chain_id=chain_id, thought=True)

                if getattr(delta, 'tool_calls', None):
                    for tcchunk in delta.tool_calls:
                        idx = getattr(tcchunk, 'index', None) or 0
                        while len(tool_calls) <= idx:
                            tool_calls.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                        tc = tool_calls[idx]
                        if getattr(tcchunk, 'id', None):
                            tc["id"] += tcchunk.id
                        fn = getattr(tcchunk, 'function', None)
                        if fn:
                            if getattr(fn, 'name', None):
                                tc["function"]["name"] += fn.name
                            if getattr(fn, 'arguments', None):
                                tc["function"]["arguments"] += fn.arguments

            tool_calls = [tc for tc in tool_calls if tc["id"] and tc["function"]["name"]]
            if not tool_calls or not active_tools:
                break

            dispatch_tool_calls(tool_calls)

            if iteration >= MAX_TOOL_ITERATIONS:
                logger.warning(
                    f"Tool call limit ({MAX_TOOL_ITERATIONS}) reached for agent model {model}; "
                    "requesting a final answer without tools."
                )
                output_manager.display_system_messages(
                    "Warning: tool call limit reached. Requesting a final answer without tools."
                )
                active_tools = None

        elapsed_time = time.time() - start_time
        output_manager.print_wrapper("", chain_id=chain_id)

    except openai.APIError as e:
        output_manager.display_system_messages(f"Requesty API Error: {str(e)}")
        raise
    except Exception as e:
        if isinstance(e, StopIteration) and "cleanup request" in str(e):
            output_manager.display_system_messages("INFO: The process was stopped by the server.")
            elapsed_time = time.time() - start_time
        else:
            output_manager.display_system_messages(f"Unexpected error: {str(e)}")
            raise

    full_reply_content = ''.join(collected_messages)

    # Prefer the provider's own accounting; fall back to tiktoken.
    if saw_usage:
        prompt_tokens_used = usage_prompt
        completion_tokens_used = usage_completion
        total_tokens_used = usage_total or (usage_prompt + usage_completion)
    else:
        completion_tokens_used = len(encoding.encode(full_reply_content + ''.join(reasoning_messages)))
        total_tokens_used = prompt_tokens_used + completion_tokens_used

    tokens_per_second = completion_tokens_used / elapsed_time if elapsed_time > 0 else 0

    if truncated:
        resilience.report_truncation(model, max_tokens, output_manager, chain_id)

    if tools:
        return full_reply_content, search_triplets, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second
    else:
        return full_reply_content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second
