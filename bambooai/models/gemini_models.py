import os
import threading
import time
import copy
import json
import base64

from google import genai
from google.genai import types
from google.genai import errors as genai_errors

from bambooai import google_search, utils, context_retrieval
from bambooai.utils import StoppableStreamWrapper

# The dispatcher's turn-level retry catches exactly these; see models/__init__.
TRANSPORT_ERRORS = (genai_errors.APIError,)

from logger_config import get_logger
from bambooai.models import prompt_cache
from bambooai.models import resilience
logger = get_logger(__name__)

request_user_context = context_retrieval.request_user_context


def init(api_keys=None):
    """Initialize Gemini client. Uses GEMINI_API_KEY from env."""
    client_api_key = os.environ.get('GEMINI_API_KEY')
    if client_api_key is None:
        raise ValueError("Gemini API key not provided and GEMINI_API_KEY is not set")
    # google-genai takes its timeout in http_options (milliseconds), not the
    # constructor keywords the OpenAI-compatible SDKs use - so this is spelled
    # out here rather than taken from timeout_kwargs, which returns {} for
    # anything it cannot be sure of.
    return genai.Client(
        api_key=client_api_key,
        http_options={"timeout": int(resilience.LLM_TIMEOUT * 1000)})


def convert_openai_to_gemini(messages):
    """
    Convert an OpenAI-style messages list into Gemini types.Content parts.
    Returns (contents_list, system_instruction_str_or_None).
    """
    updated_data = []
    system_content = None
    messages_copy = copy.deepcopy(messages)

    for item in messages_copy:
        if item.get('role') == 'system':
            system_content = item.get('content')
            continue

        role = item.get('role')
        if role == 'assistant':
            role = 'model'

        try:
            content = item.pop('content')
            parts = []

            if isinstance(content, str):
                parts.append(types.Part(text=content.strip()))
            elif isinstance(content, list):
                for part in content:
                    if part.get('type') == 'text':
                        parts.append(types.Part(text=part['text'].strip()))
                    elif part.get('type') == 'image_base64':
                        img_bytes = base64.b64decode(part['data'])
                        parts.append(types.Part(
                            inline_data=types.Blob(data=img_bytes, mime_type=part['mime_type'])
                        ))

            if parts:
                msg = types.Content(role=role, parts=parts)
                updated_data.append(msg)

        except KeyError:
            pass

    return updated_data, system_content


def detect_tool_mode(tools):
    """
    Determine tool execution mode.
    
    Returns:
        'native': Use Gemini's native google_search/url_context
        'custom': Use function calling for request_user_context
        None: No tools
    """
    if not tools:
        return None
    
    tool_names = [tool.get('name') for tool in tools]
    
    if 'google_search' in tool_names:
        return 'native'
    elif 'request_user_context' in tool_names:
        return 'custom'
    
    return None


def convert_to_gemini_function_declarations(tools):
    """Convert tool definitions to Gemini FunctionDeclaration objects."""
    function_declarations = []
    for tool in tools:
        func_decl = types.FunctionDeclaration(
            name=tool['name'],
            description=tool['description'],
            parameters=tool['parameters']
        )
        function_declarations.append(func_decl)
    return function_declarations


def _safe_int(x):
    """Helper to safely convert to int."""
    try:
        return int(x) if x is not None else 0
    except Exception:
        return 0


def setup_thinking_config(config_params, model_name, reasoning_models, reasoning_effort, output_manager, chain_id, image_generation_models=None):
    """Setup thinking configuration if reasoning or image generation model is used."""
    is_reasoning = reasoning_models and model_name in reasoning_models
    is_image_gen = image_generation_models and model_name in image_generation_models

    if is_reasoning or is_image_gen:
        thinking_budget = {"max": 8000, "xhigh": 8000, "high": 8000, "medium": 4000, "low": 2000, "minimal": 128, "none": 0}.get(reasoning_effort, 128)
        config_params['thinking_config'] = types.ThinkingConfig(include_thoughts=True, thinking_budget=thinking_budget)
        output_manager.display_tool_info('Thinking', f"Thinking budget: {thinking_budget} tokens", chain_id=chain_id)


def setup_tools_config(config_params, tool_mode, tools):
    """Setup tool configuration based on mode."""
    if tool_mode == 'native':
        google_search_tool = types.Tool(google_search=types.GoogleSearch())
        url_context_tool = types.Tool(url_context=types.UrlContext())
        config_params['tools'] = [google_search_tool, url_context_tool]
    elif tool_mode == 'custom':
        function_declarations = convert_to_gemini_function_declarations(tools)
        config_params['tools'] = [types.Tool(function_declarations=function_declarations)]


def process_streaming_chunk(chunk, answer_messages, thinking_messages, output_manager, chain_id, tool_mode):
    """
    Process a single streaming chunk and extract text, thoughts, function calls, and grounding data.
    Returns: (function_call_parts, grounding_data, usage_metadata)
    """
    function_call_parts = []  # Store actual Part objects with function_call
    grounding_data = None
    usage_metadata = None
    
    if hasattr(chunk, "usage_metadata") and chunk.usage_metadata:
        usage_metadata = chunk.usage_metadata
    
    if not chunk.candidates:
        return function_call_parts, grounding_data, usage_metadata
    
    candidate = chunk.candidates[0]
    # MAX_TOKENS means the answer was cut off. Nothing read this, so a
    # truncated response was returned as if complete and the caller failed
    # later on unparseable output - which presents as a stall, not an error.
    _finish = getattr(candidate, 'finish_reason', None)
    if _finish is not None and 'MAX_TOKENS' in str(_finish).upper():
        prompt_cache.record_meta(truncated=True)
    if not hasattr(candidate, 'content') or candidate.content is None:
        return function_call_parts, grounding_data, usage_metadata
    if not hasattr(candidate.content, 'parts') or candidate.content.parts is None:
        return function_call_parts, grounding_data, usage_metadata
    
    # Process parts
    for part in candidate.content.parts:
        # Handle thoughts
        if hasattr(part, 'thought') and part.thought is not None:
            thinking_messages.append(part.text)
            output_manager.print_wrapper(part.text, end='', flush=True, chain_id=chain_id, thought=True)
            continue
        
        # Handle text
        if hasattr(part, 'text') and part.text:
            answer_messages.append(part.text)
            output_manager.print_wrapper(part.text, end='', flush=True, chain_id=chain_id)
        
        # Handle function calls - store the actual Part object
        if tool_mode == 'custom' and hasattr(part, 'function_call') and part.function_call:
            function_call_parts.append(part)  # Keep the original part with thought_signature
    
    # Handle grounding metadata (native mode only)
    if tool_mode == 'native' and hasattr(candidate, 'grounding_metadata') and candidate.grounding_metadata:
        grounding_data = candidate.grounding_metadata
    
    return function_call_parts, grounding_data, usage_metadata


def extract_grounding_triplets(grounding_metadata_list):
    """Extract search triplets from accumulated grounding metadata."""
    search_triplets = []
    search_html = None
    
    for metadata in grounding_metadata_list:
        links = []
        if metadata.grounding_chunks is not None:
            links = [
                {"title": gc.web.title, "link": gc.web.uri}
                for gc in metadata.grounding_chunks if hasattr(gc, 'web') and gc.web
            ]
        
        queries = None
        if hasattr(metadata, 'web_search_queries') and metadata.web_search_queries is not None:
            queries = metadata.web_search_queries
        
        if hasattr(metadata, 'search_entry_point') and metadata.search_entry_point is not None and hasattr(metadata.search_entry_point, 'rendered_content'):
            search_html = metadata.search_entry_point.rendered_content
        
        if hasattr(metadata, 'grounding_supports') and metadata.grounding_supports and queries is not None:
            supports = metadata.grounding_supports
            supports_per_query = max(1, len(supports) // len(queries))
            
            for i, q in enumerate(queries):
                start_idx = i * supports_per_query
                end_idx = min((i + 1) * supports_per_query, len(supports))
                relevant_supports = supports[start_idx:end_idx]
                
                result_text = " ".join(support.segment.text for support in relevant_supports)
                relevant_link_indices = set()
                segments = []
                for support in relevant_supports:
                    relevant_link_indices.update(support.grounding_chunk_indices)
                    # each supported sentence with the sources behind it: a citable claim (2026-09-07)
                    segments.append({"text": (support.segment.text or "").strip(),
                                     "links": [links[idx] for idx in support.grounding_chunk_indices if idx < len(links)]})
                
                search_triplets.append({
                    "query": q,
                    "result": result_text.strip(),
                    "links": [links[idx] for idx in relevant_link_indices if idx < len(links)],
                    "segments": segments
                })
    
    return search_triplets, search_html


def calculate_token_usage(usage_final, prompt_tokens_baseline, answer_content, thinking_content, client, model_name):
    """Calculate token usage from usage_metadata or fallback to count_tokens."""
    if usage_final:
        prompt_tokens_used = _safe_int(getattr(usage_final, "prompt_token_count", 0)) + \
                             _safe_int(getattr(usage_final, "tool_use_prompt_token_count", 0))
        completion_tokens_used = _safe_int(getattr(usage_final, "candidates_token_count", 0)) + \
                                 _safe_int(getattr(usage_final, "thoughts_token_count", 0))
        total_tokens_used = _safe_int(getattr(usage_final, "total_token_count", 0))
        tool_use_prompt_token_count = _safe_int(getattr(usage_final, "tool_use_prompt_token_count", 0))
        if total_tokens_used == 0:
            total_tokens_used = prompt_tokens_used + completion_tokens_used
    else:
        completion_tokens_used = client.models.count_tokens(
            model=model_name,
            contents=[types.ContentDict(
                role="model",
                parts=[types.PartDict(text=answer_content + thinking_content)]
            )]
        ).total_tokens
        prompt_tokens_used = prompt_tokens_baseline
        total_tokens_used = prompt_tokens_used + completion_tokens_used
        tool_use_prompt_token_count = 0
    
    return prompt_tokens_used, completion_tokens_used, total_tokens_used, tool_use_prompt_token_count


def execute_custom_function(function_name, function_args, output_manager, log_and_call_manager, chain_id):
    """Execute a custom function and return the result."""
    available_functions = {
        "request_user_context": request_user_context
    }
    
    if function_name == "request_user_context":
        result = available_functions[function_name](
            output_manager,
            log_and_call_manager,
            chain_id,
            function_args.get("query_clarification"),
            function_args.get("context_needed")
        )
        return result
    
    return None


def llm_call(messages: str, model_name: str, temperature: str, max_tokens: str,
             response_format: str = None, api_keys=None):
    """Non-streaming call to Gemini."""
    client = init(api_keys)
    gemini_messages, system_instruction = convert_openai_to_gemini(messages)

    config_params = {
        'http_options': types.HttpOptions(api_version='v1alpha'),
        'temperature': temperature,
        'max_output_tokens': max_tokens,
        'system_instruction': system_instruction
    }

    prompt_tokens_baseline = client.models.count_tokens(
        model=model_name,
        contents=gemini_messages
    ).total_tokens

    start_time = time.time()
    response = client.models.generate_content(
        model=model_name,
        contents=gemini_messages,
        config=types.GenerateContentConfig(**config_params)
    )
    elapsed_time = time.time() - start_time

    content = response.text
    usage = getattr(response, "usage_metadata", None)

    prompt_tokens_used, completion_tokens_used, total_tokens_used, _ = calculate_token_usage(
        usage, prompt_tokens_baseline, content, "", client, model_name
    )

    tokens_per_second = (completion_tokens_used / elapsed_time) if elapsed_time > 0 else 0.0

    return content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second


def llm_stream(prompt_manager, log_and_call_manager, output_manager, chain_id: str, messages: str,
               model_name: str, temperature: str, max_tokens: str, tools: str = None,
               response_format: str = None, reasoning_models: list = None, reasoning_effort: str = None,
               api_keys=None, stop_event: threading.Event = None):
    # What the request was configured with, into the run log.
    resilience.record_request(
        reasoning_effort=reasoning_effort,
        max_tokens=max_tokens)
    """Streaming call to Gemini with tool routing."""
    client = init(api_keys)
    gemini_messages, system_instruction = convert_openai_to_gemini(messages)
    
    config_params = {
        'http_options': types.HttpOptions(api_version='v1alpha'),
        'temperature': temperature,
        'max_output_tokens': max_tokens,
        'system_instruction': system_instruction
    }
    
    # Detect tool mode and setup configuration
    tool_mode = detect_tool_mode(tools)
    setup_thinking_config(config_params, model_name, reasoning_models, reasoning_effort, output_manager, chain_id)
    setup_tools_config(config_params, tool_mode, tools)
    
    # Initialize tracking variables
    answer_messages = []
    thinking_messages = []
    grounding_metadata_list = []
    total_prompt_tokens = 0
    total_completion_tokens = 0
    start_time = time.time()
    
    # Get baseline token count for fallback
    prompt_tokens_baseline = client.models.count_tokens(
        model=model_name,
        contents=gemini_messages
    ).total_tokens
    
    # Main streaming loop (iterates multiple times only for custom functions)
    while True:
        if stop_event and stop_event.is_set():
            break
        
        # PRE-TOKEN STREAM RESTART (generic; see resilience.restartable).
        # Retried on the SDK's APIError only - google-genai wraps transport
        # and server failures into it. Before the first chunk a fresh stream
        # is exactly equivalent; a later drop stays fatal. gemini_messages is
        # only appended to AFTER a round completes, so a retry re-sends the
        # same request.
        raw_stream = resilience.restartable(
            lambda: client.models.generate_content_stream(
                model=model_name,
                contents=gemini_messages,
                config=types.GenerateContentConfig(**config_params)),
            genai_errors.APIError, output_manager=output_manager,
            chain_id=chain_id, label="Gemini")
        
        stoppable_stream = StoppableStreamWrapper(raw_stream, stop_event)
        
        current_iteration_function_calls = []
        current_iteration_text = []
        usage_final = None
        stream_stopped = False
        
        try:
            for chunk in stoppable_stream:
                function_calls, grounding_data, usage_metadata = process_streaming_chunk(
                    chunk, current_iteration_text, thinking_messages, output_manager, chain_id, tool_mode
                )
                
                if usage_metadata:
                    usage_final = usage_metadata
                
                if grounding_data:
                    grounding_metadata_list.append(grounding_data)
                
                if function_calls:
                    current_iteration_function_calls.extend(function_calls)
        
        except StopIteration as e:
            if "cleanup request" in str(e):
                output_manager.display_system_messages("INFO: The process was stopped by the server.")
                stream_stopped = True
            else:
                raise
        except Exception as e:
            output_manager.display_system_messages(f"Gemini API Error: {e}")
            raise
        
        if stream_stopped:
            break
        
        # Update token counts
        if usage_final:
            total_prompt_tokens += _safe_int(getattr(usage_final, "prompt_token_count", 0))
            total_completion_tokens += _safe_int(getattr(usage_final, "candidates_token_count", 0))
        
        # Add current iteration text to answer
        answer_messages.extend(current_iteration_text)
        
        # Handle custom function calls (if any)
        if tool_mode == 'custom' and current_iteration_function_calls:
            # Build assistant message with text AND function calls
            assistant_parts = []
            
            # Add text first if present
            if current_iteration_text:
                assistant_parts.append(types.Part(text=''.join(current_iteration_text)))
            
            # Add the original function call parts (preserves thought_signature)
            assistant_parts.extend(current_iteration_function_calls)
            
            gemini_messages.append(types.Content(role='model', parts=assistant_parts))
            
            # Execute functions and build response
            function_response_parts = []
            for fc_part in current_iteration_function_calls:
                result = execute_custom_function(
                    fc_part.function_call.name,
                    dict(fc_part.function_call.args),
                    output_manager,
                    log_and_call_manager,
                    chain_id
                )
                function_response_parts.append(types.Part(
                    function_response=types.FunctionResponse(
                        name=fc_part.function_call.name,
                        response={"result": result}
                    )
                ))
            
            gemini_messages.append(types.Content(role='user', parts=function_response_parts))
            continue  # Loop again with function response
        
        # No function calls - we're done
        break
    
    output_manager.print_wrapper("", chain_id=chain_id)
    
    # Calculate final metrics
    elapsed_time = time.time() - start_time
    answer_content = ''.join(answer_messages)
    thinking_content = ''.join(thinking_messages)
    
    # Use accumulated tokens or fallback
    if total_prompt_tokens == 0 and total_completion_tokens == 0:
        prompt_tokens_used, completion_tokens_used, total_tokens_used, tool_use_prompt_token_count = calculate_token_usage(
            usage_final, prompt_tokens_baseline, answer_content, thinking_content, client, model_name
        )
    else:
        prompt_tokens_used = total_prompt_tokens
        completion_tokens_used = total_completion_tokens
        total_tokens_used = prompt_tokens_used + completion_tokens_used
        tool_use_prompt_token_count = _safe_int(getattr(usage_final, "tool_use_prompt_token_count", 0)) if usage_final else 0
    
    tokens_per_second = (completion_tokens_used / elapsed_time) if elapsed_time > 0 else 0.0
    
    # Build response based on tool mode
    if tool_mode == 'native':
        search_triplets, search_html = extract_grounding_triplets(grounding_metadata_list)
        
        if search_html:
            output_manager.send_html_content(search_html, chain_id=chain_id)
        
        # Count actual search queries performed
        search_query_count = sum(
            len(metadata.web_search_queries) 
            for metadata in grounding_metadata_list 
            if hasattr(metadata, 'web_search_queries') and metadata.web_search_queries
        )
        
        # Add meta record
        meta_record = {
            "__meta__": {
                "search_billed": search_query_count,  # Actual query count
                "usage": {
                    "prompt_token_count": prompt_tokens_used,
                    "completion_token_count": completion_tokens_used,
                    "total_token_count": total_tokens_used,
                    "tool_use_prompt_token_count": tool_use_prompt_token_count
                }
            }
        }
        search_triplets.append(meta_record)
        
        return (answer_content, search_triplets, messages,
                prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second)
    
    elif tool_mode == 'custom':
        return (answer_content, [], messages,
                prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second)
    
    else:
        return (answer_content, messages,
                prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second)