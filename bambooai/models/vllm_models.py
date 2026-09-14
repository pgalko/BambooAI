import json
import os
import threading
import time
import openai
import tiktoken

from bambooai import google_search, utils, context_retrieval
from bambooai.utils import StoppableStreamWrapper

from logger_config import get_logger
logger = get_logger(__name__)

def init(api_keys=None):
    """
    Initialize VLLM client with configuration precedence:
    1. Use api_keys['vllm_host'] if available for remote VLLM
    2. Fall back to REMOTE_VLLM environment variable
    3. Default to localhost:8000 if neither is set
    """
    
    openai_api_key = "EMPTY"  # VLLM doesn't require a real API key
    
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
    
    openai_client = openai.OpenAI(
        api_key=openai_api_key,
        base_url=base_url
    )
    return openai_client

def llm_call(messages: str, model: str, temperature: str, max_tokens: str, response_format: str = None, api_keys=None):  
    """
    Make a call to VLLM's API with api_keys dictionary support
    """
    openai_client = init(api_keys)

    try:
        start_time = time.time()
        response = openai_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
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

    def get_response(model, messages, temperature, max_tokens, tools, response_format):
        """Helper function to create a streaming response from VLLM"""
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        
        # Note: Tool support in VLLM depends on the model and configuration
        # Uncomment these lines if your VLLM setup supports tools
        # if tools:
        #     params["tools"] = tools
        
        # if response_format:
        #     params["response_format"] = response_format
        
        return openai_client.chat.completions.create(**params)
    
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
            
            # Process the current stream
            for chunk in stoppable_stream:
                collected_chunks.append(chunk)
                
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    
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
        
        # Count completion tokens
        completion_tokens_used = len(encoding.encode(full_reply_content))
        
        # Calculate total tokens
        total_tokens_used = prompt_tokens_used + completion_tokens_used
        
        if elapsed_time > 0:
            tokens_per_second = completion_tokens_used / elapsed_time
        else:
            tokens_per_second = 0
        
    except openai.APIError as e:
        error_message = str(e)
        output_manager.display_system_messages(f"VLLM API Error: {error_message}")
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