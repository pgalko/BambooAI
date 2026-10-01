"""Ollama: the daemon on this machine (or the one REMOTE_OLLAMA names), local models and - when the
daemon is signed in - cloud models alike, through the native /api/chat (the `ollama` client).

Facts from docs.ollama.com that shape this adapter (2026-10-01):
  * A local model's context defaults by VRAM: under 24 GiB 4k, 24-48 GiB 32k, 48 GiB+ 256k; agents
    should run at 64k or more; the daemon truncates a longer prompt silently - the analyst's prompt
    is 10-30k tokens, and the contract is at its start. Cloud models run at their maximum context.
    The native API takes `options.num_ctx` per request (the OpenAI-compatible endpoint cannot):
    sent when the model's model_properties entry declares `context_window`; otherwise the daemon's
    default stands and a prompt the daemon reports as shorter than we sent is called out.
  * Thinking: `think` is true / false / a model-defined level name (gpt-oss: low/medium/high);
    /api/show lists each model's capabilities and levels. The streamed `message.thinking` carries
    the reasoning apart from the content.
  * `keep_alive` keeps a model loaded between turns (the daemon unloads after 5 minutes).
  * Direct cloud access without a daemon: OLLAMA_API_KEY against https://ollama.com.
"""
import json
import os
import queue
import threading
import time
from ollama import Client
import tiktoken
try:
    import httpx
except ImportError:                                     # the ollama client depends on httpx; be tolerant
    httpx = None

from bambooai import google_search, utils, context_retrieval
from bambooai.utils import StoppableStreamWrapper

from logger_config import get_logger
from bambooai.models import prompt_cache
from bambooai.models import resilience
logger = get_logger(__name__)

# ── Per-model facts, handed over by the dispatcher (the routing precedent) ─────
_props_local = threading.local()


def set_model_properties(props):
    """The dispatcher's hand-off: this model's model_properties entry (or {}), per thread,
    reset before every dispatch so a reused worker thread never carries the last model's."""
    _props_local.props = dict(props) if props else {}


def _props():
    return getattr(_props_local, 'props', None) or {}


# How long the stream may be silent AFTER its first chunk before it is given up (seconds); the
# wait for the first chunk is unbounded on purpose - a local model evaluating a 20k-token prompt
# on modest hardware can take minutes before it says anything.
OLLAMA_IDLE_TIMEOUT = float(os.getenv('OLLAMA_IDLE_TIMEOUT', '300'))
# Keep the model loaded between turns of a run; the daemon's own default unloads after 5 minutes.
OLLAMA_KEEP_ALIVE = os.getenv('OLLAMA_KEEP_ALIVE', '30m')
# Below this share of our own estimate, the daemon's prompt_eval_count means it dropped prompt.
TRUNCATION_RATIO = 0.8

TRANSPORT_ERRORS = tuple(t for t in (getattr(httpx, 'TransportError', None), ConnectionError) if t)


def _host():
    host = os.environ.get('REMOTE_OLLAMA') or 'http://localhost:11434'
    return host if host.startswith('http') else f"http://{host}"


def init(api_keys=None):
    """The client for the daemon REMOTE_OLLAMA names (default localhost:11434). Direct cloud access
    (https://ollama.com) carries OLLAMA_API_KEY. The read timeout is unbounded: the idle deadline is
    enforced around the stream instead (see _with_idle_deadline), so a slow first token is not an
    error and a dead stream still is."""
    host = _host()
    headers = {}
    key = os.environ.get('OLLAMA_API_KEY')
    if key and 'ollama.com' in host:
        headers['Authorization'] = f"Bearer {key}"
    timeout = httpx.Timeout(connect=30.0, read=None, write=120.0, pool=None) if httpx else None
    kwargs = {'host': host, 'timeout': timeout}
    if headers:
        kwargs['headers'] = headers
    return Client(**kwargs)


_show_cache = {}


def _capabilities(client, model):
    """What /api/show says the model can do (e.g. 'completion', 'thinking', 'tools'); cached per
    model and host; an unreachable or old daemon gives an empty list, and nothing is sent that
    depends on it."""
    key = (_host(), model)
    if key not in _show_cache:
        caps = []
        try:
            info = client.show(model)
            raw = info.get('capabilities') if isinstance(info, dict) else getattr(info, 'capabilities', None)
            caps = [str(c) for c in (raw or [])]
        except Exception as exc:                            # noqa: BLE001
            logger.info(f"ollama: /api/show for {model} unavailable ({exc}); sending no thinking control")
        _show_cache[key] = caps
    return _show_cache[key]


def _think_value(reasoning_effort, caps):
    """The native `think` field for this model and effort, or None to send none.
    Only a model that lists 'thinking' in its capabilities is sent the field. 'none' turns thinking
    off; a level the model defines (model_properties.reasoning_efforts) is sent by name, with
    OpenAI-style aliases folded to the nearest level it has; otherwise plain `true`."""
    if 'thinking' not in (caps or []):
        return None
    effort = (reasoning_effort or '').strip().lower()
    if effort in ('none', 'off', 'false', '0'):
        return False
    levels = [str(x).lower() for x in (_props().get('reasoning_efforts') or []) if str(x).lower() != 'none']
    if not levels:
        return True
    if effort in levels:
        return effort
    order = ['minimal', 'low', 'medium', 'high', 'xhigh', 'max']
    if effort in order:                                    # the nearest level the model has, by rank
        rank = order.index(effort)
        ranked = sorted((abs(order.index(l) - rank) if l in order else 99, l) for l in levels)
        return ranked[0][1]
    return True


def _request_options(temperature, max_tokens):
    """Runtime options: temperature, the output cap, and the context length when the template
    declares it for this model (model_properties.context_window). Nothing else: a forced num_ctx on
    a small GPU is an out-of-memory failure, so the daemon's default stands unless the person set
    one, and truncation is reported instead (see _report_truncation)."""
    options = {'temperature': temperature}
    if max_tokens:
        options['num_predict'] = max_tokens
    ctx = _props().get('context_window')
    if ctx:
        try:
            options['num_ctx'] = int(ctx)
        except (TypeError, ValueError):
            logger.warning(f"ollama: context_window {ctx!r} is not a number; ignored")
    return options


def _with_idle_deadline(stream, stop_event):
    """Yield the daemon's chunks with the three-phase wait: unbounded before the first chunk (a slow
    prompt evaluation is not a failure), then OLLAMA_IDLE_TIMEOUT of silence ends the stream, and a
    stop_event ends it at any point. The producer thread is a daemon thread, so a stream abandoned
    here cannot keep the process alive."""
    q = queue.Queue()
    done = object()

    def pump():
        try:
            for chunk in stream:
                q.put(chunk)
        except BaseException as exc:                       # noqa: BLE001 - handed to the consumer
            q.put(exc)
        finally:
            q.put(done)
    threading.Thread(target=pump, daemon=True).start()
    started = False
    while True:
        try:
            item = q.get(timeout=1.0 if not started else OLLAMA_IDLE_TIMEOUT)
        except queue.Empty:
            if stop_event is not None and stop_event.is_set():
                return
            if started:
                raise TimeoutError(f"ollama: no data for {OLLAMA_IDLE_TIMEOUT:.0f}s after the stream began")
            continue
        if item is done:
            return
        if isinstance(item, BaseException):
            raise item
        started = True
        yield item
        if stop_event is not None and stop_event.is_set():
            return


def _report_truncation(output_manager, chain_id, model, estimated, reported):
    """The daemon saw fewer prompt tokens than we sent: its context is shorter than the prompt and
    the beginning - the contract - was dropped. Said once per call, in the log and the pane."""
    if not (estimated and reported) or estimated < 2000 or reported >= TRUNCATION_RATIO * estimated:
        return
    msg = (f"Ollama evaluated {reported:,} prompt tokens of about {estimated:,} sent to {model}: the model's "
           f"context length is shorter than the prompt and its beginning was dropped. Raise it: the Ollama "
           f"app's context slider, OLLAMA_CONTEXT_LENGTH for the daemon, or \"context_window\" on this "
           f"model's model_properties entry (the analyst needs 32k or more).")
    logger.warning(msg)
    try:
        output_manager.display_system_messages(f"WARNING: {msg}")
    except Exception:                                       # noqa: BLE001
        pass


def llm_call(messages: str, model: str, temperature: str, max_tokens: str, response_format: str = None, api_keys=None):  
    """
    Make a call to Ollama's API with api_keys dictionary support
    """
    client = init(api_keys)

    start_time = time.time()

    options = _request_options(temperature, max_tokens)
    think = _think_value('none', _capabilities(client, model))   # a plain call is a utility call: no thinking
    params = {'model': model, 'messages': messages, 'options': options, 'keep_alive': OLLAMA_KEEP_ALIVE}
    if think is not None:
        params['think'] = think
    if response_format and isinstance(response_format, dict) and response_format.get('type') == 'json_object':
        params['format'] = 'json'
    response = client.chat(**params)

    end_time = time.time()
    elapsed_time = end_time - start_time

    content = response['message']['content']

    # Handle token counts - Ollama may not always provide these
    prompt_tokens_used = response.get('prompt_eval_count', 0)
    completion_tokens_used = response.get('eval_count', 0)
    total_tokens_used = prompt_tokens_used + completion_tokens_used
    
    if elapsed_time > 0:
        tokens_per_second = completion_tokens_used / elapsed_time
    else:
        tokens_per_second = 0

    return content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second

def llm_stream(prompt_manager, log_and_call_manager, output_manager, chain_id: str, messages: str, model: str,
               temperature: str, max_tokens: str, tools: str = None, response_format: str = None,
               reasoning_models: list = None, reasoning_effort: str = "medium", api_keys=None,
               stop_event: threading.Event = None):
    # What the request was configured with, into the run log.
    resilience.record_request(reasoning_effort=reasoning_effort,
                              max_tokens=max_tokens)
    """
    Stream responses from Ollama's API with tool calls and StoppableStreamWrapper support
    Note: Tool support in Ollama depends on the model being used (e.g., some Llama models support it)
    """
    collected_chunks = []
    collected_messages = []
    tool_calls = []
    search_triplets = []
    google_search_messages = [{"role": "system", "content": prompt_manager.google_search_react_system.format(utils.get_readable_date())}]

    client = init(api_keys)
    
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

    caps = _capabilities(client, model)
    think = _think_value(reasoning_effort, caps)
    logger.info(f"ollama: {model} think={think!r} num_ctx={_request_options(temperature, max_tokens).get('num_ctx')} keep_alive={OLLAMA_KEEP_ALIVE}")

    def get_response(model, messages, temperature, max_tokens, tools, response_format):
        """One streaming request to the daemon, wrapped in the idle deadline."""
        params = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": _request_options(temperature, max_tokens),
            "keep_alive": OLLAMA_KEEP_ALIVE,
        }
        if think is not None:
            params["think"] = think
        
        # Add tools if provided and model supports them
        # Note: Tool support in Ollama is model-dependent
        if tools:
            # Convert OpenAI-style tools to Ollama format if needed
            # Ollama's tool format may differ - adjust as necessary
            params["tools"] = tools
        
        # Add format if specified (Ollama uses 'format' not 'response_format')
        if response_format and response_format.get('type') == 'json_object':
            params["format"] = "json"
        
        return _with_idle_deadline(client.chat(**params), stop_event)
    
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
        
        # Get the first stream
        raw_stream = get_response(model, messages, temperature, max_tokens, tools, response_format)
        stoppable_stream = StoppableStreamWrapper(raw_stream, stop_event)
        
        # Process tool calls - may happen multiple times
        max_iterations = 10  # Prevent infinite loops
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            tool_calls = []  # Reset for each iteration
            current_message_content = []
            
            # Process the current stream
            for chunk in stoppable_stream:
                collected_chunks.append(chunk)

                # 'length' means the answer was cut off at num_predict.
                if str(chunk.get('done_reason', '')).lower() == 'length':
                    prompt_cache.record_meta(truncated=True)
                
                # The reasoning channel: thinking models stream it apart from the content when `think`
                # is on; it goes to the pane's collapsible block, never into the answer.
                if 'message' in chunk and chunk['message'].get('thinking'):
                    output_manager.print_wrapper(chunk['message']['thinking'], end='', flush=True, chain_id=chain_id, thought=True)
                # Handle regular content
                if 'message' in chunk and 'content' in chunk['message']:
                    chunk_message = chunk['message']['content']
                    if chunk_message:
                        current_message_content.append(chunk_message)
                        collected_messages.append(chunk_message)
                        output_manager.print_wrapper(chunk_message, end='', flush=True, chain_id=chain_id)
                
                # Handle tool calls (if supported by the model)
                # Note: Ollama's tool call format may differ from OpenAI's
                if 'message' in chunk and 'tool_calls' in chunk['message']:
                    chunk_tool_calls = chunk['message']['tool_calls']
                    if isinstance(chunk_tool_calls, list):
                        for tc in chunk_tool_calls:
                            tool_calls.append({
                                "id": tc.get('id', f"call_{len(tool_calls)}"),
                                "type": "function",
                                "function": {
                                    "name": tc.get('function', {}).get('name', ''),
                                    "arguments": json.dumps(tc.get('function', {}).get('arguments', {}))
                                }
                            })
            
            # If no tool calls, we're done
            if not tool_calls:
                break
            
            # Process tool calls
            messages.append({
                "role": 'assistant',
                "content": ''.join(current_message_content) if current_message_content else None,
                "tool_calls": tool_calls,
            })
            
            # Execute each tool call
            for tool_call in tool_calls:
                function_name = tool_call['function']['name']
                function_to_call = available_functions.get(function_name)
                
                if not function_to_call:
                    output_manager.display_system_messages(f"Warning: Unknown function {function_name}")
                    continue
                
                try:
                    function_args = json.loads(tool_call['function']['arguments'])
                except json.JSONDecodeError:
                    function_args = tool_call['function']['arguments']
                
                if function_name == "google_search":
                    search_query = function_args.get("search_query", "") if isinstance(function_args, dict) else str(function_args)
                    google_search_messages.append({"role": "user", "content": search_query})
                    function_response, links = function_to_call(
                        prompt_manager,
                        log_and_call_manager,
                        output_manager, 
                        chain_id,
                        messages=google_search_messages
                    )
                    add_triplet(search_query, function_response, links)
                
                elif function_name == "request_user_context":
                    query_clarification = function_args.get("query_clarification", "") if isinstance(function_args, dict) else ""
                    context_needed = function_args.get("context_needed", "") if isinstance(function_args, dict) else ""
                    function_response = function_to_call(
                        output_manager,
                        log_and_call_manager,
                        chain_id,
                        query_clarification,
                        context_needed
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
                    "role": "tool",
                    "tool_call_id": tool_call['id'],
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
        
        # Count completion tokens
        # For Ollama, we might get actual token counts from the last chunk
        last_chunk = collected_chunks[-1] if collected_chunks else {}
        if 'eval_count' in last_chunk:
            completion_tokens_used = last_chunk['eval_count']
        else:
            # Fall back to tiktoken estimation
            completion_tokens_used = len(encoding.encode(full_reply_content))
        
        # Update prompt tokens if provided - and compare with what we sent: a daemon whose context is
        # shorter than the prompt evaluates fewer tokens than we counted, silently.
        if 'prompt_eval_count' in last_chunk:
            estimated_prompt_tokens = prompt_tokens_used
            prompt_tokens_used = last_chunk['prompt_eval_count']
            _report_truncation(output_manager, chain_id, model, estimated_prompt_tokens, prompt_tokens_used)
        
        # Calculate total tokens
        total_tokens_used = prompt_tokens_used + completion_tokens_used
        
        if elapsed_time > 0:
            tokens_per_second = completion_tokens_used / elapsed_time
        else:
            tokens_per_second = 0
        
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
            output_manager.display_system_messages(f"Ollama API Error: {str(e)}")
            raise
    
    # Return format depends on whether tools were used
    if tools:
        return full_reply_content, search_triplets, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second
    else:
        return full_reply_content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second