import json
import os
import threading
import time
import openai

from bambooai import google_search, utils, context_retrieval
from bambooai.utils import StoppableStreamWrapper
from bambooai.models import prompt_cache
from bambooai.models import resilience

# The dispatcher's turn-level retry catches exactly these; see models/__init__.
TRANSPORT_ERRORS = (openai.APIError,)

from logger_config import get_logger
logger = get_logger(__name__)


def init(api_keys=None):
    """Initialize OpenAI client (shared logic with openai_models.py)."""
    client_api_key = os.environ.get('OPENAI_API_KEY')
    if client_api_key is None:
        raise ValueError("OpenAI API key not provided and OPENAI_API_KEY environment variable not set")
    return openai.OpenAI(api_key=client_api_key,
                         **resilience.timeout_kwargs("openai"))


def _convert_messages_to_input(messages):
    """
    Convert Chat Completions messages list to Responses API format.
    Returns (input_items, instructions) where system messages become instructions.
    """
    instructions_parts = []
    input_items = []
    for msg in messages:
        role = msg.get('role')
        content = msg.get('content', '')
        if role == 'system':
            instructions_parts.append(content)
        elif role in ('user', 'assistant'):
            input_items.append({"role": role, "content": content})
    instructions = "\n\n".join(instructions_parts) if instructions_parts else None
    return input_items, instructions


def _convert_tools(tools):
    """Convert Chat Completions tool format to Responses API flat format."""
    if not tools:
        return None
    converted = []
    for tool in tools:
        if "function" in tool:
            func = tool["function"]
            converted.append({
                "type": "function",
                "name": func["name"],
                "description": func.get("description", ""),
                "parameters": func.get("parameters", {}),
            })
        else:
            converted.append(tool)
    return converted


# ---------------------------------------------------------------------------
# Non-streaming call
# ---------------------------------------------------------------------------

def llm_call(messages: str, model: str, temperature: str, max_tokens: str,
             response_format: str = None, api_keys=None):
    """
    Non-streaming Responses API call.
    Return signature matches openai_models.llm_call exactly.
    """
    openai_client = init(api_keys)
    input_items, instructions = _convert_messages_to_input(messages)

    kwargs = dict(model=model, input=input_items, max_output_tokens=max_tokens)
    kwargs["extra_body"] = prompt_cache.openai_extras(model)
    if instructions:
        kwargs["instructions"] = instructions
    if temperature is not None:
        kwargs["temperature"] = temperature
    if response_format:
        kwargs["text"] = {"format": response_format}

    try:
        start_time = time.time()
        response = openai_client.responses.create(**kwargs)
        end_time = time.time()
    except openai.RateLimitError:
        time.sleep(10)
        start_time = time.time()
        response = openai_client.responses.create(**kwargs)
        end_time = time.time()

    elapsed_time = end_time - start_time
    content = response.output_text or ""

    prompt_tokens_used = response.usage.input_tokens if response.usage else 0
    completion_tokens_used = response.usage.output_tokens if response.usage else 0
    total_tokens_used = prompt_tokens_used + completion_tokens_used
    tokens_per_second = completion_tokens_used / elapsed_time if elapsed_time > 0 else 0

    return (content, messages, prompt_tokens_used, completion_tokens_used,
            total_tokens_used, elapsed_time, tokens_per_second)


# ---------------------------------------------------------------------------
# Streaming call (with tool-call loop)
# ---------------------------------------------------------------------------

def llm_stream(prompt_manager, log_and_call_manager, output_manager, chain_id: str,
               messages: str, model: str, temperature: str, max_tokens: str,
               tools: str = None, response_format: str = None,
               reasoning_models: list = None, reasoning_effort: str = "medium",
               api_keys=None, stop_event: threading.Event = None):
    """
    Streaming Responses API call with tool-call support.
    Return signature matches openai_models.llm_stream exactly.
    """
    collected_messages = []
    function_calls = []
    search_triplets = []
    google_search_messages = [
        {"role": "system",
         "content": prompt_manager.google_search_react_system.format(utils.get_readable_date())}
    ]

    if reasoning_effort == "minimal":
        reasoning_effort = "none"
    # This is the module OpenAI actually goes through: a model declaring
    # api_type "responses" is routed here, and every gpt-5.6-* in the roster
    # does. Recorded after the coercion above, so it is what was SENT.
    prompt_cache.record_meta(reasoning_effort=reasoning_effort,
                             max_tokens=max_tokens)

    openai_client = init(api_keys)

    # Available tool implementations (identical to openai_models.py)
    available_functions = {
        "google_search": google_search.SmartSearchOrchestrator(api_keys=api_keys),
        "request_user_context": context_retrieval.request_user_context,
        "consult_assistant": context_retrieval.consult_assistant,
    }

    def add_triplet(query, result, links):
        search_triplets.append({"query": query, "result": result, "links": links})

    # --- Convert from Chat Completions format ---
    input_items, instructions = _convert_messages_to_input(messages)
    converted_tools = _convert_tools(tools)

    def build_kwargs(input_data, prev_response_id=None):
        """Build request kwargs, reusing common logic."""
        kw = dict(model=model, input=input_data, stream=True)
        kw["extra_body"] = prompt_cache.openai_extras(model)

        if prev_response_id:
            kw["previous_response_id"] = prev_response_id
        elif instructions:
            kw["instructions"] = instructions

        if reasoning_models and model in reasoning_models:
            effort = reasoning_effort or "medium"
            output_manager.display_tool_info(
                'Thinking', f"Reasoning Effort: {effort}", chain_id=chain_id)
            kw["reasoning"] = {"effort": effort, "summary": "auto"}
        else:
            if temperature is not None:
                kw["temperature"] = temperature

        kw["max_output_tokens"] = max_tokens

        if converted_tools:
            kw["tools"] = converted_tools
        if response_format and not prev_response_id:
            kw["text"] = {"format": response_format}
        return kw

    def process_stream(stream):
        """
        Iterate over a Responses API event stream.
        Populates collected_messages / function_calls and returns (response_id, usage).
        Reasoning summaries are buffered and flushed as complete sections
        (matching how Gemini emits thoughts in larger chunks).
        """
        resp_id = None
        usage_prompt = usage_completion = 0
        thinking_buffer = []

        for event in stream:
            if event.type == "response.reasoning_summary_text.delta":
                thinking_buffer.append(event.delta)

            elif event.type == "response.reasoning_summary_text.done":
                # Flush the accumulated thinking section as one block
                if thinking_buffer:
                    thought_text = ''.join(thinking_buffer)
                    output_manager.print_wrapper(
                        thought_text, end="", flush=True, chain_id=chain_id, thought=True)
                    thinking_buffer = []

            elif event.type == "response.output_text.delta":
                collected_messages.append(event.delta)
                output_manager.print_wrapper(event.delta, end="", flush=True, chain_id=chain_id)

            elif event.type == "response.output_item.done":
                if getattr(event.item, 'type', None) == "function_call":
                    function_calls.append(event.item)

            elif event.type == "response.completed":
                resp_id = event.response.id
                if event.response.usage:
                    usage_prompt = event.response.usage.input_tokens
                    usage_completion = event.response.usage.output_tokens

            # -- Response INCOMPLETE: the answer was cut off --
            #
            # The Responses API does not set finish_reason == "length"; a
            # capped response arrives as its own terminal event with
            # status "incomplete" and incomplete_details naming the cause.
            # This event was silently ignored, so a truncated answer was
            # returned as if complete - the caller then failed later on
            # unparseable output, which presents as a stall, not a limit -
            # and its usage and response id went unrecorded.
            elif event.type == "response.incomplete":
                resp = getattr(event, "response", None)
                if resp is not None:
                    resp_id = getattr(resp, "id", resp_id)
                    if getattr(resp, "usage", None):
                        usage_prompt = resp.usage.input_tokens
                        usage_completion = resp.usage.output_tokens
                details = getattr(resp, "incomplete_details", None)
                reason = getattr(details, "reason", None) or "unknown"
                if reason == "max_output_tokens":
                    resilience.report_truncation(model, max_tokens,
                                                 output_manager, chain_id)
                else:
                    logger.warning("OpenAI response incomplete (%s); the "
                                   "answer was cut off.", reason)
                    prompt_cache.record_meta(truncated=True)

        # Flush any remaining buffered thoughts (safety net)
        if thinking_buffer:
            thought_text = ''.join(thinking_buffer)
            output_manager.print_wrapper(
                thought_text, end="", flush=True, chain_id=chain_id, thought=True)

        return resp_id, usage_prompt, usage_completion

    def execute_tool(function_name, function_args):
        """Execute a single tool call, return the string result."""
        function_to_call = available_functions[function_name]

        if function_name == "google_search":
            google_search_messages.append(
                {"role": "user", "content": function_args.get("search_query")})
            result, links = function_to_call(
                prompt_manager, log_and_call_manager, output_manager, chain_id,
                messages=google_search_messages)
            add_triplet(function_args.get("search_query"), result, links)
            return result

        if function_name == "request_user_context":
            return function_to_call(
                output_manager, log_and_call_manager, chain_id,
                function_args.get("query_clarification"),
                function_args.get("context_needed"))

        if function_name == "consult_assistant":
            return function_to_call(
                output_manager, log_and_call_manager, chain_id,
                function_args.get("analytical_goal"),
                function_args.get("data_context"),
                function_args.get("decision_point"),
                function_args.get("options_considered"),
                function_args.get("plan_constraints"),
                reasoning_models, api_keys)

        raise ValueError(f"Unknown function: {function_name}")

    # --- Main streaming loop ---
    try:
        combined_prompt = 0
        combined_completion = 0
        response_id = None

        start_time = time.time()

        # First request
        # PRE-TOKEN STREAM RESTART (generic; see resilience.restartable).
        # OpenAI can accept the request and then drop the connection before
        # emitting anything. Before the first chunk a fresh stream is exactly
        # equivalent, so the open and the pre-token window are retried; a
        # later drop stays fatal because the answer cannot be resumed.
        raw_stream = resilience.restartable(
            lambda: openai_client.responses.create(**build_kwargs(input_items)),
            openai.APIError, output_manager=output_manager,
            chain_id=chain_id, label="OpenAI")
        stream = StoppableStreamWrapper(raw_stream, stop_event)
        resp_id, p_tok, c_tok = process_stream(stream)
        response_id = resp_id
        combined_prompt += p_tok
        combined_completion += c_tok

        # Tool-call loop
        max_iterations = 10
        iteration = 0

        while function_calls and iteration < max_iterations:
            iteration += 1

            # Build function_call_output items
            tool_outputs = []
            for fc in function_calls:
                func_args = json.loads(fc.arguments)
                result = execute_tool(fc.name, func_args)
                tool_outputs.append({
                    "type": "function_call_output",
                    "call_id": fc.call_id,
                    "output": result,
                })

            function_calls = []

            # Same pre-token restart on the tool follow-up round. The
            # closure binds response_id BY VALUE at wrap time (the retry must
            # re-send the same request, not one built from a later id).
            _prev_id = response_id
            raw_stream = resilience.restartable(
                lambda: openai_client.responses.create(
                    **build_kwargs(tool_outputs, prev_response_id=_prev_id)),
                openai.APIError, output_manager=output_manager,
                chain_id=chain_id, label="OpenAI")
            stream = StoppableStreamWrapper(raw_stream, stop_event)
            resp_id, p_tok, c_tok = process_stream(stream)
            response_id = resp_id
            combined_prompt += p_tok
            combined_completion += c_tok

            if not function_calls:
                break

        end_time = time.time()
        elapsed_time = end_time - start_time

    except openai.APIError as e:
        error_message = e.body.get('message') if e.body else str(e)
        output_manager.display_system_messages(f"OpenAI API Error: {error_message}")
        raise
    except Exception as e:
        if isinstance(e, StopIteration) and "cleanup request" in str(e):
            output_manager.display_system_messages("INFO: The process was stopped by the server.")
        else:
            output_manager.display_system_messages(f"Unexpected error: {str(e)}")
            raise

    output_manager.print_wrapper("", chain_id=chain_id)

    full_reply_content = ''.join(collected_messages)
    combined_total = combined_prompt + combined_completion
    tokens_per_second = combined_completion / elapsed_time if elapsed_time > 0 else 0

    if tools:
        return (full_reply_content, search_triplets, messages,
                combined_prompt, combined_completion, combined_total,
                elapsed_time, tokens_per_second)
    else:
        return (full_reply_content, messages,
                combined_prompt, combined_completion, combined_total,
                elapsed_time, tokens_per_second)