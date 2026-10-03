import json
import os
import time
import litellm
import tiktoken

from bambooai import google_search, utils
from bambooai.utils import StoppableStreamWrapper
from bambooai.models import resilience

# The dispatcher's turn-level retry catches exactly these; see models/__init__.
# litellm re-raises provider failures as litellm.exceptions.* (which subclass
# the OpenAI error types), so APIError covers the transport-death family.
TRANSPORT_ERRORS = (litellm.exceptions.APIError,)

from logger_config import get_logger
logger = get_logger(__name__)

google_search_function = google_search.SmartSearchOrchestrator()


def _request_kwargs(api_keys=None):
    """Shared litellm.completion kwargs.

    ``drop_params=True`` lets litellm silently drop per-provider-unsupported
    params (e.g. reasoning models rejecting ``temperature``, Gemini rejecting
    OpenAI-schema ``response_format``) instead of erroring - the SDK does what
    the sibling providers hand-code per model.

    Credentials are resolved by litellm from each provider's own env var
    (``OPENAI_API_KEY``, ``ANTHROPIC_API_KEY``, ...). To target a LiteLLM
    proxy instead, set ``LITELLM_API_BASE`` (or ``LITELLM_BASE_URL``) and
    optionally ``LITELLM_API_KEY``; passed here only when present so the
    provider-env fallback keeps working.
    """
    kwargs = {"drop_params": True, "timeout": resilience.LLM_TIMEOUT}
    api_key = (api_keys or {}).get("litellm") or os.environ.get("LITELLM_API_KEY")
    api_base = os.environ.get("LITELLM_API_BASE") or os.environ.get("LITELLM_BASE_URL")
    if api_key:
        kwargs["api_key"] = api_key
    if api_base:
        kwargs["api_base"] = api_base
    return kwargs


def llm_call(messages: str, model: str, temperature: str, max_tokens: str, response_format: str = None, api_keys=None):
    # api_keys is the dispatcher's uniform calling convention
    # (models/__init__.llm_call passes six positionals to every provider).
    request_kwargs = _request_kwargs(api_keys)

    try:
        start_time = time.time()
        response = litellm.completion(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            **request_kwargs,
        )
        end_time = time.time()
    except litellm.exceptions.RateLimitError:
        time.sleep(10)
        start_time = time.time()
        response = litellm.completion(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            **request_kwargs,
        )
        end_time = time.time()

    elapsed_time = end_time - start_time

    content = response.choices[0].message.content.strip()
    prompt_tokens = response.usage.prompt_tokens
    completion_tokens = response.usage.completion_tokens
    total_tokens = response.usage.total_tokens

    prompt_tokens_used = prompt_tokens
    completion_tokens_used = completion_tokens
    total_tokens_used = total_tokens
    if elapsed_time > 0:
        tokens_per_second = completion_tokens_used / elapsed_time
    else:
        tokens_per_second = 0

    return content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second


def llm_stream(prompt_manager, log_and_call_manager, output_manager, chain_id: str, messages: str, model: str, temperature: str, max_tokens: str, tools: str = None, response_format: str = None, reasoning_models: list = None, reasoning_effort: str = "medium", api_keys=None, stop_event=None):
    # api_keys and stop_event are the dispatcher's uniform calling convention
    # (models/__init__.llm_stream passes both to every provider).
    collected_chunks = []
    collected_messages = []
    reasoning_messages = []
    tool_calls = []
    search_triplets = []
    google_search_messages = [{"role": "system", "content": prompt_manager.google_search_react_system.format(utils.get_readable_date())}]

    tools = tools

    request_kwargs = _request_kwargs(api_keys)

    available_functions = {
        "google_search": google_search_function
    }

    def add_triplet(query, result, links):
        '''Add a triplet to the search_triplets list'''
        triplet = {
            "query": query,
            "result": result,
            "links": links
        }
        search_triplets.append(triplet)

    # PRE-TOKEN STREAM RESTART (generic; see resilience.restartable).
    # Before the first chunk a fresh stream is exactly equivalent, so the
    # open and the pre-token window are retried; a later drop stays fatal.
    response = resilience.restartable(
        lambda: litellm.completion(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            tools=tools,
            stream=True,
            response_format=response_format,
            **request_kwargs,
        ),
        litellm.exceptions.APIError, output_manager=output_manager,
        chain_id=chain_id, label="LiteLLM")
    response = StoppableStreamWrapper(response, stop_event)

    start_time = time.time()
    # iterate through the stream of events
    for chunk in response:
        delta = chunk.choices[0].delta
        # finish_reason == "length" means the model hit max_tokens and the
        # answer was cut off; say so instead of returning it as complete.
        if getattr(chunk.choices[0], 'finish_reason', None) == 'length':
            resilience.report_truncation(model, max_tokens,
                                         output_manager, chain_id)
        collected_chunks.append(chunk)  # save the event response

        if delta and hasattr(delta, 'content') and delta.content:
            collected_messages.append(delta.content)
            output_manager.print_wrapper(delta.content, end='', flush=True, chain_id=chain_id)
        elif delta and hasattr(delta, 'reasoning_content') and delta.reasoning_content:
            reasoning_messages.append(delta.reasoning_content)
            # thought=True: see openrouter_models. The reasoning belongs in the
            # Thinking block, not appended raw to the output pane.
            output_manager.print_wrapper(delta.reasoning_content, end='', flush=True, chain_id=chain_id, thought=True)
        elif delta and hasattr(delta, 'tool_calls') and delta.tool_calls:
            tcchunklist = delta.tool_calls
            for tcchunk in tcchunklist:
                if len(tool_calls) <= tcchunk.index:
                    tool_calls.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                tc = tool_calls[tcchunk.index]

                if tcchunk.id:
                    tc["id"] += tcchunk.id
                if tcchunk.function.name:
                    tc["function"]["name"] += tcchunk.function.name
                if tcchunk.function.arguments:
                    tc["function"]["arguments"] += tcchunk.function.arguments

    if tool_calls:
        messages.append(
            {
                "tool_calls": tool_calls,
                "role": 'assistant',
            }
        )

    for index, tool_call in enumerate(tool_calls):
        function_name = tool_call['function']['name']
        function_to_call = available_functions[function_name]
        function_args = json.loads(tool_call['function']['arguments'])
        google_search_messages.append({"role": "user", "content": function_args.get("search_query")})
        function_response, links = function_to_call(
            prompt_manager,
            log_and_call_manager,
            output_manager,
            chain_id,
            messages=google_search_messages
        )

        messages.append(
            {
                "tool_call_id": tool_call['id'],
                "role": "tool",
                "name": function_name,
                "content": function_response,
            }  # extend conversation with function response
        )

        add_triplet(
            function_args.get("search_query"),
            function_response,
            links
        )

        # Check if it's the last tool call in the list before calling
        if index == len(tool_calls) - 1:
            # Same pre-token restart on the tool follow-up round.
            response = resilience.restartable(
                lambda: litellm.completion(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=True,
                    response_format=response_format,
                    **request_kwargs,
                ),
                litellm.exceptions.APIError, output_manager=output_manager,
                chain_id=chain_id, label="LiteLLM")
            response = StoppableStreamWrapper(response, stop_event)

    # iterate through the stream of events
    for chunk in response:
        delta = chunk.choices[0].delta
        collected_chunks.append(chunk)  # save the event response
        if getattr(chunk.choices[0], 'finish_reason', None) == 'length':
            resilience.report_truncation(model, max_tokens,
                                         output_manager, chain_id)

        if delta and hasattr(delta, 'content') and delta.content:
            collected_messages.append(delta.content)
            output_manager.print_wrapper(delta.content, end='', flush=True, chain_id=chain_id)
        elif delta and hasattr(delta, 'reasoning_content') and delta.reasoning_content:
            reasoning_messages.append(delta.reasoning_content)
            # thought=True: see openrouter_models. The reasoning belongs in the
            # Thinking block, not appended raw to the output pane.
            output_manager.print_wrapper(delta.reasoning_content, end='', flush=True, chain_id=chain_id, thought=True)

    end_time = time.time()
    elapsed_time = end_time - start_time

    output_manager.print_wrapper("", chain_id=chain_id)

    # get the complete reasoning and collected messages content
    full_reply_content = ''.join([m for m in collected_messages])
    reasoning_content = ''.join([m for m in reasoning_messages])

    # Tiktoken encoding
    encoding = tiktoken.encoding_for_model("gpt-4")

    # count the number of response tokens used
    completion_tokens_used = len(encoding.encode(full_reply_content + reasoning_content))

    # count the number of prompt tokens used
    tokens_per_message = 3
    tokens_per_name = 1
    prompt_tokens_used = 0

    for message in messages:
        prompt_tokens_used += tokens_per_message
        for key, value in message.items():
            if isinstance(value, str):
                prompt_tokens_used += len(encoding.encode(value))
            if key == "name":
                prompt_tokens_used += tokens_per_name
    prompt_tokens_used += 3  # every reply is primed with <|start|>assistant<|message|>

    # calculate the total tokens used
    total_tokens_used = prompt_tokens_used + completion_tokens_used

    if elapsed_time > 0:
        tokens_per_second = completion_tokens_used / elapsed_time
    else:
        tokens_per_second = 0

    if tools:
        return full_reply_content, search_triplets, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second
    else:
        return full_reply_content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second
