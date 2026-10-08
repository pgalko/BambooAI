import json
import os
import time
import anthropic
import threading

from bambooai import google_search, utils, context_retrieval
from bambooai.models import prompt_cache
from bambooai.models import resilience
from bambooai.utils import StoppableStreamWrapper

# The dispatcher's turn-level retry catches exactly these; see models/__init__.
TRANSPORT_ERRORS = (anthropic.APIError,)

from logger_config import get_logger
logger = get_logger(__name__)

def init(api_keys=None):
    """
    Initialize Anthropic client with API key precedence:
    1. Use api_keys['anthropic'] if available
    2. Fall back to environment variable

    NOTE: the previous version ignored api_keys entirely and read only the env
    var, contradicting this docstring. Restored precedence below. If you rely on
    the env var only, this remains backward compatible (api_keys empty -> env).
    """
    client_api_key = None
    if api_keys and api_keys.get('anthropic'):
        client_api_key = api_keys['anthropic']
    if client_api_key is None:
        client_api_key = os.environ.get('ANTHROPIC_API_KEY')

    if client_api_key is None:
        raise ValueError("Anthropic API key not provided in api_keys dict and ANTHROPIC_API_KEY environment variable not set")

    # A hung call must fail, not hang: the SDK defaults to 600s with two
    # retries, so one stalled upstream can block for half an hour.
    client = anthropic.Client(api_key=client_api_key,
                              **resilience.timeout_kwargs("anthropic"))
    return client

# ---- The dispatcher's hand-offs (2026-10-08): the model's properties entry, its reasoning style and its declared
# effort vocabulary, through the same per-thread channel the OpenRouter adapter uses (reset before every dispatch, so a
# stale entry never dresses the next model in this one's rules). The Claude 5.5 family controls thinking with
# output_config.effort and adaptive thinking, takes no sampling parameters (a non-default temperature is a 400), and
# returns thinking blocks empty unless display "summarized" is asked for; the 4.5 models and earlier keep the old shape.
_props_local = threading.local()

_EFFORT_RANK = {"none": 0, "minimal": 1, "low": 2, "medium": 3, "high": 4, "xhigh": 5, "max": 6}


def set_model_properties(props):
    """The whole model_properties entry for the model being served, or {}."""
    _props_local.props = dict(props) if props else {}


def set_reasoning_style(style):
    _props_local.style = str(style).strip().lower() if style else None


def set_reasoning_efforts(efforts):
    _props_local.efforts = tuple(str(e).strip().lower() for e in efforts if str(e).strip()) if efforts else None


def _props():
    return getattr(_props_local, "props", None) or {}


def _style():
    return getattr(_props_local, "style", None)


def _efforts():
    return getattr(_props_local, "efforts", None)


def _snap_effort(effort):
    """The requested effort word snapped to the model's declared vocabulary: the lowest declared level at or above the
    request, else the highest declared; "none" asks for no thinking and snaps to the lowest level."""
    want = str(effort or "medium").strip().lower()
    declared = _efforts()
    if not declared:
        return want if want in _EFFORT_RANK and want != "none" else "low"
    rank = _EFFORT_RANK.get(want, 3)
    above = [e for e in declared if _EFFORT_RANK.get(e, 3) >= rank]
    return min(above, key=lambda e: _EFFORT_RANK.get(e, 3)) if above else max(declared, key=lambda e: _EFFORT_RANK.get(e, 3))


def request_params(model, temperature, max_tokens, effort=None, stream=False):
    """The request parameters for this model, from its properties entry (2026-10-08).

    - An effort-word model (reasoning_style "effort": the Claude 5.5 family) gets output_config.effort at the snapped
      level and adaptive thinking with summarized display, so the pane sees the reasoning. A seat that asks for "none"
      turns thinking off where the model allows it - the entry's `thinking_off` names the way: "disabled" (Haiku 5.5)
      or "between_tools" (Sonnet 5.5), each accepted at effort high or below and taking no display field - and runs at
      the lowest effort; a model with no way to turn it off (Opus 5.5) runs adaptive at the lowest effort.
    - `no_sampling` true on the entry leaves temperature out: these models reject a non-default value with a 400.
    - Anything else keeps the old shape: temperature when given (in extra_body, since the SDK's create() no longer
      takes sampling keywords), no thinking field.
    """
    params = {"model": model, "max_tokens": max_tokens}
    if stream:
        params["stream"] = True
    props = _props()
    if not props.get("no_sampling") and temperature is not False and temperature is not None:
        # through extra_body, which every SDK version merges into the request body: the SDK's typed create() has no
        # temperature/top_p/top_k any more, and the keyword raised a TypeError before the request was made (2026-10-08,
        # a seat on a Claude model whose properties entry was missing - its model string had a dot, claude-opus-5.5)
        params["extra_body"] = {"temperature": temperature}
    if _style() == "effort" and effort is not None:
        want = str(effort).strip().lower()
        level = _snap_effort(effort)
        off = props.get("thinking_off")
        if want == "none" and off and _EFFORT_RANK.get(level, 3) <= _EFFORT_RANK["high"]:
            params["thinking"] = {"type": str(off)}
        else:
            params["thinking"] = {"type": "adaptive", "display": "summarized"}
        params["output_config"] = {"effort": level}
    return params


def convert_openai_to_anthropic(messages):
    updated_data = []
    system_content = ""
    for item in messages:
        if item['role'] == 'system':
            system_content = item['content']
            continue
        updated_data.append(item)

    return updated_data, system_content

def _first_text(response):
    """Return the text of the first text content block, or '' if none.

    Replaces `response.content[0].text`, which assumes block 0 is text. On
    adaptive-thinking models (Sonnet 5, Opus 4.7+/4.8) block 0 is often a
    thinking block, which has no `.text` attribute and would raise AttributeError.
    """
    for block in response.content:
        if getattr(block, "type", None) == "text":
            return block.text
    return ""

def llm_call(messages: str, model: str, temperature: str, max_tokens: str, response_format: str = None, api_keys=None):
    """
    Make a call to Anthropic's API with api_keys dictionary support
    """
    client = init(api_keys)

    messages, system_instruction = convert_openai_to_anthropic(messages)

    start_time = time.time()

    prompt_cache.reset()
    # Anthropic controls thinking with a token budget rather than an effort
    # level, and reasoning_effort is not a parameter of these functions - so
    # only max_tokens is recorded here. That is what makes a `truncated` entry
    # interpretable on its own.
    prompt_cache.record_meta(max_tokens=max_tokens)
    api_params = request_params(model, temperature, max_tokens)
    api_params["system"] = prompt_cache.anthropic_system(system_instruction)
    api_params["messages"] = prompt_cache.anthropic_messages(messages)

    response = client.messages.create(**api_params)
    end_time = time.time()

    elapsed_time = end_time - start_time

    # FIX: was `response.content[0].text` — breaks when a thinking block is first.
    content = _first_text(response)

    # input_tokens EXCLUDES cache reads and writes on Anthropic; the helper adds
    # them back so prompt_tokens_used is the TOTAL input, which is what
    # log_manager prices against.
    _r, _w, prompt_tokens_used = prompt_cache.from_anthropic_usage(response.usage)
    completion_tokens_used = response.usage.output_tokens
    total_tokens_used = prompt_tokens_used + completion_tokens_used

    if elapsed_time > 0:
        tokens_per_second = completion_tokens_used / elapsed_time
    else:
        tokens_per_second = 0

    return content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second

def call_and_parse_stream(output_manager, collected_messages, tools, messages, system_instruction, model, temperature, max_tokens, chain_id, api_keys=None, stop_event: threading.Event = None, effort=None):
    """
    Internal function to handle streaming with api_keys support.

    Collection is keyed on the *block type* of each content block, not on
    `chunk.index`. The old code only saved text when the text block was at
    index 0; on adaptive-thinking models the stream leads with a thinking block
    at index 0, pushing text to index 1, so the text was silently dropped and
    `full_reply_content` came back empty. Thinking/redacted-thinking blocks are
    now captured and returned so they can be replayed with tool results (required
    by the API when using tools with extended thinking).
    """
    client = init(api_keys)
    tool_calls = []
    tool_use_block = None
    text_block = None
    thinking_blocks = []          # captured for tool-use replay

    # Initialize up front so we never depend on locals() introspection.
    prompt_tokens_used = 0
    completion_tokens_used = 0
    thinking_chars = 0            # the summarized thinking's length: 0 when the model produced no thinking block

    prompt_cache.reset()
    # Anthropic controls thinking with a token budget rather than an effort
    # level, and reasoning_effort is not a parameter of these functions - so
    # only max_tokens is recorded here. That is what makes a `truncated` entry
    # interpretable on its own.
    api_params = request_params(model, temperature, max_tokens, effort=effort, stream=True)
    prompt_cache.record_meta(max_tokens=max_tokens, effort=(api_params.get("output_config") or {}).get("effort"),
                             thinking=(api_params.get("thinking") or {}).get("type"))
    api_params["system"] = prompt_cache.anthropic_system(system_instruction)
    api_params["messages"] = prompt_cache.anthropic_messages(messages)
    if tools:
        api_params["tools"] = tools

    try:
        # PRE-TOKEN STREAM RESTART (generic; see resilience.restartable).
        # Anthropic can accept the request and then drop the connection before
        # emitting anything - seen in the field on OpenRouter as "Upstream
        # error ... Connection closed", which killed a Synthesizer call fifty
        # model calls into a 1h45m run. Before the first chunk a fresh stream
        # is exactly equivalent, so the open and the pre-token window are
        # retried; a later drop stays fatal because the answer cannot be
        # resumed. Provider-SPECIFIC hardening (OpenRouter's THINKING_BUDGET,
        # effort/max_tokens exclusivity) is deliberately NOT copied here.
        raw_stream = resilience.restartable(
            lambda: client.messages.create(**api_params),
            anthropic.APIError, output_manager=output_manager,
            chain_id=chain_id, label="Anthropic")
        stoppable_stream = StoppableStreamWrapper(raw_stream, stop_event)

        full_content = ""
        current_tool_call = None
        current_thinking = None
        block_types = {}          # index -> block type, so stop events can dispatch by type

        for chunk in stoppable_stream:
            if chunk.type == "content_block_start":
                block_types[chunk.index] = chunk.content_block.type

                if chunk.content_block.type == "text":
                    text_block = chunk.content_block
                    full_content += chunk.content_block.text
                    output_manager.print_wrapper(chunk.content_block.text, end='', flush=True, chain_id=chain_id)

                elif chunk.content_block.type == "tool_use":
                    tool_use_block = chunk.content_block
                    current_tool_call = {
                        "id": chunk.content_block.id,
                        "type": "function",
                        "function": {
                            "name": chunk.content_block.name,
                            "arguments": ""
                        }
                    }

                elif chunk.content_block.type in ("thinking", "redacted_thinking"):
                    # With display="omitted" (the Sonnet 5 / Opus 4.8 default) the
                    # thinking text is empty; only a signature_delta follows. We
                    # still capture the block for replay during tool use.
                    current_thinking = chunk.content_block

            elif chunk.type == "content_block_delta":
                d = chunk.delta
                if d.type == "text_delta":
                    full_content += d.text
                    output_manager.print_wrapper(d.text, end='', flush=True, chain_id=chain_id)

                elif d.type == "input_json_delta":
                    if current_tool_call:
                        current_tool_call["function"]["arguments"] += d.partial_json

                elif d.type == "thinking_delta":
                    if current_thinking is not None:
                        current_thinking.thinking = (getattr(current_thinking, "thinking", "") or "") + d.thinking
                    if d.thinking:
                        # the summarized thinking to the pane's reasoning fold, as every other reasoning adapter does
                        # (2026-10-08: it was captured for tool replay and shown nowhere, so a Claude card had no
                        # reasoning and how much a turn thought could not be seen)
                        thinking_chars += len(d.thinking)
                        output_manager.print_wrapper(d.thinking, end='', flush=True, chain_id=chain_id, thought=True)

                elif d.type == "signature_delta":
                    if current_thinking is not None:
                        current_thinking.signature = (getattr(current_thinking, "signature", "") or "") + d.signature

            elif chunk.type == "content_block_stop":
                btype = block_types.get(chunk.index)

                if btype == "text":
                    # THE FIX: save on block type, not on `chunk.index == 0`.
                    collected_messages.append(full_content)
                    if text_block is not None:
                        text_block.text = full_content
                    full_content = ""   # reset in case another text block follows

                elif btype == "tool_use":
                    if current_tool_call:
                        tool_calls.append(current_tool_call)
                        tool_use_block.input = json.loads(current_tool_call["function"]["arguments"])
                        current_tool_call = None

                elif btype in ("thinking", "redacted_thinking"):
                    if current_thinking is not None:
                        thinking_blocks.append(current_thinking)
                        current_thinking = None

            elif chunk.type == 'message_delta':
                completion_tokens_used = chunk.usage.output_tokens
                # stop_reason "max_tokens" means the answer was cut off. It
                # arrives on this event and was never read, so a truncated
                # response was returned as if complete.
                _stop = getattr(getattr(chunk, 'delta', None), 'stop_reason', None)
                if _stop == 'max_tokens':
                    resilience.report_truncation(model, max_tokens,
                                                 output_manager, chain_id)
                elif _stop == 'refusal':
                    # the Claude 5.5 family's safety classifiers decline a request with this stop reason and no text
                    # (2026-10-08); said in the pane and in the reply, so the turn does not read as an empty answer.
                    # stop_details names the category (cyber, bio, frontier_llm, reasoning_extraction, general_harms,
                    # or none) and carries an explanation; both go to the pane, the category to the log and the session
                    _details = getattr(getattr(chunk, 'delta', None), 'stop_details', None)
                    _category = getattr(_details, 'category', None) or 'no category given'
                    _why = getattr(_details, 'explanation', None) or ''
                    output_manager.display_system_messages(
                        f"{model} declined this request (stop_reason: refusal, {_category}){': ' + _why if _why else '.'}")
                    prompt_cache.record_meta(declined=_category, declined_why=_why or None)
                    collected_messages.append(f"[{model} declined this request: stop_reason refusal, {_category}]")

            elif chunk.type == 'message_start':
                _r, _w, prompt_tokens_used = prompt_cache.from_anthropic_usage(
                    chunk.message.usage)

    except (anthropic.APIError) as e:
        body = getattr(e, 'body', None)
        error_message = body.get('error', {}).get('message', 'Unknown error') if isinstance(body, dict) else str(e)
        output_manager.display_system_messages(f"Anthropic API Error: {error_message}")
        raise
    except Exception as e:
        output_manager.display_system_messages(f"Unexpected error: {str(e)}")
        raise

    # how much the call thought, for the log: the summary's length and the number of thinking blocks - with adaptive
    # thinking the model may skip thinking altogether, and output_tokens does not separate thinking from text
    prompt_cache.record_meta(thinking_chars=thinking_chars, thinking_blocks=len(thinking_blocks))
    return messages, collected_messages, tool_calls, tool_use_block, text_block, thinking_blocks, prompt_tokens_used, completion_tokens_used

def llm_stream(prompt_manager, log_and_call_manager, output_manager, chain_id: str, messages: list, model: str, temperature: float, max_tokens: int,
               tools: list = [], response_format: str = None, reasoning_models: list = None, reasoning_effort: str = "medium", api_keys=None, stop_event: threading.Event = None):
    """
    Stream responses from Anthropic's API with complete API keys dictionary support
    """
    total_tokens_used = 0
    prompt_tokens_used = 0
    completion_tokens_used = 0
    tokens_per_second = 0
    collected_messages = []
    google_search_messages = [{"role": "system", "content": prompt_manager.google_search_react_system.format(utils.get_readable_date())}]
    search_triplets = []

    # Define the available functions
    request_user_context = context_retrieval.request_user_context
    consult_assistant = context_retrieval.consult_assistant
    google_search_function = google_search.SmartSearchOrchestrator(api_keys=api_keys)

    available_functions = {
        "google_search": google_search_function,
        "request_user_context": request_user_context,
        "consult_assistant": consult_assistant
    }

    messages, system_instruction = convert_openai_to_anthropic(messages)

    def add_triplet(query, result, links):
        '''Add a triplet to the search_triplets list'''
        triplet = {
            "query": query,
            "result": result,
            "links": links
        }
        search_triplets.append(triplet)

    start_time = time.time()

    while True:
        (messages, collected_messages, tool_calls, tool_use_block, text_block,
         thinking_blocks, new_prompt_tokens, new_completion_tokens) = call_and_parse_stream(
            output_manager, collected_messages, tools, messages, system_instruction, model, temperature, max_tokens, chain_id, api_keys,
            stop_event=stop_event, effort=reasoning_effort)

        prompt_tokens_used += new_prompt_tokens
        completion_tokens_used += new_completion_tokens

        if tool_calls:
            # Reconstruct the assistant turn in original block order:
            # thinking block(s) first, then text (if any), then the tool_use block.
            # Passing the thinking block(s) back is REQUIRED by the API when using
            # tools with extended thinking; omitting them causes a 400 on the next turn.
            assistant_content = list(thinking_blocks)
            if text_block is not None:
                assistant_content.append(text_block)
            assistant_content.append(tool_use_block)

            messages.append(
                {
                    "role": "assistant",
                    "content": assistant_content
                }
            )

            for tool_call in tool_calls:
                function_name = tool_call['function']['name']
                function_to_call = available_functions[function_name]
                function_args = json.loads(tool_call['function']['arguments'])

                if function_name == "google_search":
                    google_search_messages.append({"role": "user", "content": function_args.get("search_query")})
                    function_response, links = function_to_call(
                        prompt_manager,
                        log_and_call_manager,
                        output_manager,
                        chain_id,
                        google_search_messages
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

                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": tool_call['id'],
                                "content": function_response
                            }
                        ]
                    }
                )
        else:
            break

    end_time = time.time()
    elapsed_time = end_time - start_time

    output_manager.print_wrapper("", chain_id=chain_id)

    full_reply_content = ''.join(collected_messages)

    # calculate the token usage
    total_tokens_used = prompt_tokens_used + completion_tokens_used

    if elapsed_time > 0:
        tokens_per_second = completion_tokens_used / elapsed_time
    else:
        tokens_per_second = 0

    # We now need to add the system_instructions back to the top of messages for logging
    if system_instruction:
        messages.insert(0, {"role": "system", "content": system_instruction})

    if tools:
        return full_reply_content, search_triplets, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second
    else:
        return full_reply_content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second