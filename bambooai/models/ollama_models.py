import json
import os
import threading
import time
from ollama import Client
import tiktoken

from bambooai import google_search, utils, context_retrieval
from bambooai.utils import StoppableStreamWrapper

from logger_config import get_logger
from bambooai.models import prompt_cache
from bambooai.models import resilience
logger = get_logger(__name__)

def init(api_keys=None):
    """
    Initialize Ollama client with configuration precedence:
    1. Use api_keys['ollama_host'] if available for remote Ollama
    2. Fall back to REMOTE_OLLAMA environment variable
    3. Default to localhost:11434 if neither is set
    """
    
    # Determine Ollama host
    ollama_host = os.environ.get('REMOTE_OLLAMA')
    
    if ollama_host:
        # Use remote Ollama host
        if not ollama_host.startswith('http'):
            ollama_host = f"http://{ollama_host}"
    else:
        # Default to localhost
        ollama_host = 'http://localhost:11434'
    
    # A local model can stall just as a hosted one can, and there is no SDK
    # default to fall back on.
    client = Client(host=ollama_host, timeout=resilience.LLM_TIMEOUT)
    return client

def llm_call(messages: str, model: str, temperature: str, max_tokens: str, response_format: str = None, api_keys=None):  
    """
    Make a call to Ollama's API with api_keys dictionary support
    """
    client = init(api_keys)

    start_time = time.time()

    # Prepare options
    options = {
        'temperature': temperature,
        'top_k': 10,
    }
    
    # Add max_tokens if specified (Ollama uses 'num_predict')
    if max_tokens:
        options['num_predict'] = max_tokens

    response = client.chat(
        model=model, 
        messages=messages,
        options=options,
    )

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

    def get_response(model, messages, temperature, max_tokens, tools, response_format):
        """Helper function to create a streaming response from Ollama"""
        options = {
            'temperature': temperature,
            'top_k': 10,
        }
        
        # Add max_tokens if specified
        if max_tokens:
            options['num_predict'] = max_tokens
        
        params = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": options,
        }
        
        # Add tools if provided and model supports them
        # Note: Tool support in Ollama is model-dependent
        if tools:
            # Convert OpenAI-style tools to Ollama format if needed
            # Ollama's tool format may differ - adjust as necessary
            params["tools"] = tools
        
        # Add format if specified (Ollama uses 'format' not 'response_format')
        if response_format and response_format.get('type') == 'json_object':
            params["format"] = "json"
        
        return client.chat(**params)
    
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
        
        # Update prompt tokens if provided
        if 'prompt_eval_count' in last_chunk:
            prompt_tokens_used = last_chunk['prompt_eval_count']
        
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