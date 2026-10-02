"""vLLM: an OpenAI-compatible server the person runs (REMOTE_VLLM), typically on their own GPU.

Facts established against vLLM 0.30 serving Qwen3.8-27B (2026-10-02):
  * With --reasoning-parser the model's thinking streams as `delta.reasoning` (older servers and some
    models: `reasoning_content`), apart from `delta.content`; the final usage chunk counts it under
    completion_tokens_details.reasoning_tokens.
  * `reasoning_effort` is accepted in the request for models whose chat template takes it (Qwen3.8);
    thinking is switched off with chat_template_kwargs {"enable_thinking": false}.
  * A prompt longer than the server's --max-model-len is REJECTED (HTTP 400, "maximum context
    length"), not truncated - better than a daemon that drops the prompt's start, and worth a plain
    message instead of a traceback.
  * The server never bills: prices are the template's (zero for a local model).
"""
import json
import os
import threading
import time
import openai
import tiktoken
try:
    import httpx
except ImportError:                                     # the openai client depends on httpx; be tolerant
    httpx = None

from bambooai import google_search, utils, context_retrieval
from bambooai.utils import StoppableStreamWrapper

from logger_config import get_logger
logger = get_logger(__name__)

# ── Per-model facts, handed over by the dispatcher (the routing precedent) ─────
_props_local = threading.local()


def set_model_properties(props):
    """The dispatcher's hand-off: this model's model_properties entry (or {}), per thread."""
    _props_local.props = dict(props) if props else {}


def _props():
    return getattr(_props_local, 'props', None) or {}


# Transport trouble the dispatcher re-asks the turn for (5 / 10 / 20 s): the server unreachable,
# a stalled connection, a 5xx while it reloads, or a 429 while it is saturated.
TRANSPORT_ERRORS = tuple(t for t in (getattr(openai, 'APIConnectionError', None), getattr(openai, 'APITimeoutError', None),
                                     getattr(openai, 'InternalServerError', None), getattr(openai, 'RateLimitError', None)) if t)


def _effort_for(model, reasoning_effort):
    """What to send for the seat's effort: ('off', None) to switch thinking off, ('effort', name) to
    pass reasoning_effort (the model's own level name when it lists them, the nearest otherwise),
    or (None, None) to send nothing."""
    effort = (reasoning_effort or '').strip().lower()
    if not effort:
        return None, None
    if effort in ('none', 'off', 'false', '0'):
        return 'off', None
    levels = [str(x).lower() for x in (_props().get('reasoning_efforts') or []) if str(x).lower() != 'none']
    if not levels or effort in levels:
        return 'effort', effort
    order = ['minimal', 'low', 'medium', 'high', 'xhigh', 'max']
    if effort in order:                                    # fold an alias the model lacks to its nearest level
        rank = order.index(effort)
        return 'effort', sorted((abs(order.index(l) - rank) if l in order else 99, l) for l in levels)[0][1]
    return 'effort', effort


def _reasoning_kwargs(model, reasoning_models, reasoning_effort):
    """The request fields that control thinking, for a model the template marks as reasoning."""
    if not reasoning_models or model not in reasoning_models:
        return {}
    kind, value = _effort_for(model, reasoning_effort)
    if kind == 'off':
        return {'extra_body': {'chat_template_kwargs': {'enable_thinking': False}}}
    if kind == 'effort':
        return {'reasoning_effort': value}
    return {}


def _explain(exc):
    """An API error from the server, read for the person."""
    text = str(exc)
    if 'maximum context length' in text or 'max_model_len' in text or 'context length' in text:
        return (f"The prompt does not fit the server's context: {text[:300]}. Raise --max-model-len on the vLLM "
                f"server, or lower this seat's max_tokens; the analyst needs the contract and the cells so far.")
    if isinstance(exc, getattr(openai, 'NotFoundError', ())):
        return f"The server has no such model: {text[:200]}. The seat's model must match --served-model-name (GET /v1/models lists it)."
    return f"vLLM API error: {text[:300]}"


def _preflight(output_manager, chain_id, model, prompt_tokens, max_tokens):
    """The server rejects a prompt longer than its context; say so before sending, when the template
    declares the context (model_properties.context_window) and the sum cannot fit."""
    ctx = _props().get('context_window')
    try:
        ctx = int(ctx) if ctx else None
    except (TypeError, ValueError):
        ctx = None
    if ctx and prompt_tokens and prompt_tokens + int(max_tokens or 0) > ctx:
        msg = (f"About {prompt_tokens:,} prompt tokens plus {int(max_tokens or 0):,} for the answer exceed the "
               f"{ctx:,}-token context declared for {model}: the server will refuse. Raise --max-model-len "
               f"(and context_window in the template), or lower this seat's max_tokens.")
        logger.warning(msg)
        try:
            output_manager.display_system_messages(f"WARNING: {msg}")
        except Exception:                                   # noqa: BLE001
            pass


def init(api_keys=None):
    """
    Initialize VLLM client with configuration precedence:
    1. Use api_keys['vllm_host'] if available for remote VLLM
    2. Fall back to REMOTE_VLLM environment variable
    3. Default to localhost:8000 if neither is set
    """
    
    openai_api_key = os.environ.get('VLLM_API_KEY') or "EMPTY"  # a server started with --api-key wants it; others ignore it
    
    # Determine VLLM host
    vllm_host = os.environ.get('REMOTE_VLLM')
    
    if vllm_host:
        # Use remote VLLM host
        base_url = vllm_host if vllm_host.startswith('http') else f"http://{vllm_host}"
        if not base_url.endswith('/v1'):
            base_url = f"{base_url}/v1"
    else:
        # Default to localhost
        base_url = "http://localhost:8000/v1"
    
    # The read timeout is unbounded: a local model may evaluate a 30k-token prompt for minutes before its
    # first token; the stream is guarded instead (three phases - unbounded first chunk, an idle deadline
    # once output began, a tail deadline after finish - the same guard the OpenRouter adapter uses).
    kwargs = {'api_key': openai_api_key, 'base_url': base_url, 'max_retries': 0}
    if httpx:
        kwargs['timeout'] = httpx.Timeout(connect=30.0, read=None, write=120.0, pool=None)
    return openai.OpenAI(**kwargs)

def llm_call(messages: str, model: str, temperature: str, max_tokens: str, response_format: str = None, api_keys=None):  
    """
    Make a call to VLLM's API with api_keys dictionary support
    """
    openai_client = init(api_keys)

    try:
        start_time = time.time()
        params = {'model': model, 'messages': messages, 'temperature': temperature, 'max_tokens': max_tokens,
                  'extra_body': {'chat_template_kwargs': {'enable_thinking': False}}}   # a utility call: no thinking
        if response_format:
            params['response_format'] = response_format
        response = openai_client.chat.completions.create(**params)
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

def llm_stream(prompt_manager, log_and_call_manager, output_manager, chain_id: str, messages: str, model: str,
               temperature: str, max_tokens: str, tools: str = None, response_format: str = None,
               reasoning_models: list = None, reasoning_effort: str = "medium", api_keys=None,
               stop_event: threading.Event = None):  
    """
    Stream responses from VLLM's API with complete tool calls and StoppableStreamWrapper support
    Note: VLLM tool support depends on the model being served and may require specific configurations
    """
    collected_chunks = []
    collected_messages = []
    usage_prompt = usage_completion = usage_reasoning = 0        # the server's counts, from the final chunk
    tool_calls = []
    search_triplets = []
    google_search_messages = [{"role": "system", "content": prompt_manager.google_search_react_system.format(utils.get_readable_date())}]

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

    from bambooai.models.openrouter_models import _tail_guarded, _reasoning_delta_text   # the same wire protocol, the same guard

    def get_response(model, messages, temperature, max_tokens, tools, response_format):
        """One streaming request to the server, with exact usage at the end, the seat's thinking control,
        and the three-phase guard around the stream."""
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        params.update(_reasoning_kwargs(model, reasoning_models, reasoning_effort))
        if response_format:
            params["response_format"] = response_format
        logger.info(f"vllm: {model} effort={params.get('reasoning_effort')} thinking_off={'extra_body' in params} max_tokens={max_tokens}")
        return _tail_guarded(openai_client.chat.completions.create(**params), output_manager, chain_id)
    
    try:
        start_time = time.time()
        
        # Tiktoken encoding for token counting
        encoding = tiktoken.encoding_for_model("gpt-4")
        tokens_per_message = 3
        tokens_per_name = 1
        
        # Count initial prompt tokens
        prompt_tokens_used = 0
        for message in messages:
            prompt_tokens_used += tokens_per_message
            for key, value in message.items():
                if isinstance(value, str):
                    prompt_tokens_used += len(encoding.encode(value))
                if key == "name":
                    prompt_tokens_used += tokens_per_name
        prompt_tokens_used += 3  # reply primer
        _preflight(output_manager, chain_id, model, prompt_tokens_used, max_tokens)
        
        # Get the first stream
        raw_stream = get_response(model, messages, temperature, max_tokens, tools, response_format)
        stoppable_stream = StoppableStreamWrapper(raw_stream, stop_event)
        
        # Process tool calls - may happen multiple times
        max_iterations = 10  # Prevent infinite loops
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            tool_calls = []  # Reset for each iteration
            
            # Process the current stream
            for chunk in stoppable_stream:
                collected_chunks.append(chunk)
                chunk_usage = getattr(chunk, 'usage', None)
                if chunk_usage:                                     # the final chunk: the server's own counts
                    usage_prompt = getattr(chunk_usage, 'prompt_tokens', 0) or 0
                    usage_completion = getattr(chunk_usage, 'completion_tokens', 0) or 0
                    details = getattr(chunk_usage, 'completion_tokens_details', None)
                    usage_reasoning = (getattr(details, 'reasoning_tokens', 0) or 0) if details else 0
                
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    reasoning_text = _reasoning_delta_text(delta) if delta else None
                    if reasoning_text:                              # the model's thinking: the pane's reasoning block, never the answer
                        output_manager.print_wrapper(reasoning_text, end='', flush=True, chain_id=chain_id, thought=True)
                    
                    # Handle content
                    if delta and delta.content:
                        collected_messages.append(delta.content)
                        output_manager.print_wrapper(delta.content, end='', flush=True, chain_id=chain_id)
                    
                    # Handle tool calls (if supported by your VLLM setup)
                    elif delta and hasattr(delta, 'tool_calls') and delta.tool_calls:
                        for tcchunk in delta.tool_calls:
                            # Ensure tool_calls list is large enough
                            while len(tool_calls) <= tcchunk.index:
                                tool_calls.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                            tc = tool_calls[tcchunk.index]
                            
                            if tcchunk.id:
                                tc["id"] += tcchunk.id
                            if tcchunk.function.name:
                                tc["function"]["name"] += tcchunk.function.name
                            if tcchunk.function.arguments:
                                tc["function"]["arguments"] += tcchunk.function.arguments
            
            # If no tool calls, we're done
            if not tool_calls:
                break
            
            # Process tool calls
            messages.append({
                "tool_calls": tool_calls,
                "role": 'assistant',
            })
            
            # Execute each tool call
            for tool_call in tool_calls:
                function_name = tool_call['function']['name']
                function_to_call = available_functions.get(function_name)
                
                if not function_to_call:
                    output_manager.display_system_messages(f"Warning: Unknown function {function_name}")
                    continue
                
                function_args = json.loads(tool_call['function']['arguments'])
                
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
                
                # Add tool response to messages
                messages.append({
                    "tool_call_id": tool_call['id'],
                    "role": "tool",
                    "name": function_name,
                    "content": function_response,
                })
            
            # Get the next stream after processing tool calls
            raw_stream = get_response(model, messages, temperature, max_tokens, tools, response_format)
            stoppable_stream = StoppableStreamWrapper(raw_stream, stop_event)
        
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        output_manager.print_wrapper("", chain_id=chain_id)
        
        # Get the complete text received
        full_reply_content = ''.join([m for m in collected_messages])
        
        # Count completion tokens - the server's own counts when the usage chunk came (thinking included)
        if usage_prompt or usage_completion:
            prompt_tokens_used = usage_prompt or prompt_tokens_used
            completion_tokens_used = usage_completion
            if usage_reasoning:
                logger.info(f"vllm: {model} reasoning tokens {usage_reasoning} of {usage_completion} completion tokens")
        else:
            completion_tokens_used = len(encoding.encode(full_reply_content))
        
        # Calculate total tokens
        total_tokens_used = prompt_tokens_used + completion_tokens_used
        
        if elapsed_time > 0:
            tokens_per_second = completion_tokens_used / elapsed_time
        else:
            tokens_per_second = 0
        
    except openai.APIError as e:
        explanation = _explain(e)
        output_manager.display_system_messages(explanation)
        logger.warning(explanation)
        raise
    except Exception as e:
        if isinstance(e, StopIteration) and "cleanup request" in str(e):
            output_manager.display_system_messages("INFO: The process was stopped by the server.")
            # Return partial results
            full_reply_content = ''.join([m for m in collected_messages])
            elapsed_time = time.time() - start_time if 'start_time' in locals() else 0
            completion_tokens_used = len(encoding.encode(full_reply_content))
            total_tokens_used = prompt_tokens_used + completion_tokens_used
            tokens_per_second = completion_tokens_used / elapsed_time if elapsed_time > 0 else 0
        else:
            output_manager.display_system_messages(f"Unexpected error: {str(e)}")
            raise
    
    # Return format depends on whether tools were used
    if tools:
        return full_reply_content, search_triplets, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second
    else:
        return full_reply_content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second