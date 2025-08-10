import json
import os
import threading
import time
from groq import Groq
import tiktoken

from bambooai import google_search, utils, context_retrieval

def init():
    API_KEY = os.environ.get('GROQ_API_KEY')
    if API_KEY is None:
        return
    else:
        client = Groq()
        client.api_key = API_KEY
        return client

def llm_call(messages: str, model: str, temperature: str, max_tokens: str, response_format: str = None):  
    """
    Make a call to Groq's API with api_keys dictionary support
    """
    client = init()

    start_time = time.time()

    response = client.chat.completions.create(
        model=model, 
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
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
               reasoning_models: list = None, reasoning_effort: str = "medium"):  
    """
    Stream responses from Groq's API with tool calls and reasoning support for GPT-OSS models
    """
    collected_chunks = []
    collected_messages = []
    tool_calls = []
    search_triplets = []
    google_search_messages = [{"role": "system", "content": prompt_manager.google_search_react_system.format(utils.get_readable_date())}]

    client = init()
    
    # Define the available functions
    request_user_context = context_retrieval.request_user_context
    google_search_function = google_search.SmartSearchOrchestrator()

    available_functions = {
        "google_search": google_search_function,
        "request_user_context": request_user_context
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
        """Helper function to create a streaming response from Groq"""
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
            "stream": True,
        }
        
        # Add stream_options via extra_body to get usage information
        params["extra_body"] = {"stream_options": {"include_usage": True}}
        
        # Add tools if provided
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"
            
        # Add reasoning parameters for GPT-OSS models
        if reasoning_models and model in reasoning_models:
            output_manager.display_tool_info('Thinking', f"Reasoning Effort: {reasoning_effort}", chain_id=chain_id)
            # For GPT-OSS models, include_reasoning is used (not reasoning_format)
            params["include_reasoning"] = True
            params["reasoning_effort"] = reasoning_effort
        
        return client.chat.completions.create(**params)
    
    try:
        start_time = time.time()
        
        # Initialize token counters
        prompt_tokens_used = 0
        completion_tokens_used = 0
        total_tokens_used = 0
        
        # Get the first stream
        response = get_response(model, messages, temperature, max_tokens, tools, response_format)
        
        # Process tool calls - may happen multiple times
        max_iterations = 10  # Prevent infinite loops
        iteration = 0
        
        while iteration < max_iterations:
            iteration += 1
            tool_calls = []  # Reset for each iteration
            reasoning_complete = []  # Collect all reasoning text
            
            # Process the current stream
            for chunk in response:
                collected_chunks.append(chunk)
                
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    
                    # Handle reasoning content for GPT-OSS models
                    if hasattr(delta, 'reasoning') and delta.reasoning is not None:
                        reasoning_text = delta.reasoning
                        
                        # Collect all reasoning text
                        reasoning_complete.append(reasoning_text)
                    
                    # Handle regular content
                    if delta and delta.content is not None:
                        chunk_message = delta.content
                        collected_messages.append(chunk_message)
                        output_manager.print_wrapper(chunk_message, end='', flush=True, chain_id=chain_id)
                    
                    # Handle tool calls
                    elif delta and delta.tool_calls:
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
                
                # Check for usage data in the chunk
                if hasattr(chunk, 'usage') and chunk.usage is not None:
                    if chunk.usage.prompt_tokens is not None:
                        prompt_tokens_used = chunk.usage.prompt_tokens
                    if chunk.usage.completion_tokens is not None:
                        completion_tokens_used = chunk.usage.completion_tokens
                    if chunk.usage.total_tokens is not None:
                        total_tokens_used = chunk.usage.total_tokens
            
            # Output complete reasoning at once if any was collected
            if reasoning_complete:
                full_reasoning = ''.join(reasoning_complete)
                if full_reasoning:
                    output_manager.print_wrapper(full_reasoning, end='', flush=True, chain_id=chain_id, thought=True)
            
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
                
                # Add tool response to messages
                tool_message = {
                    "tool_call_id": tool_call['id'],
                    "role": "tool",
                    "name": function_name,
                    "content": function_response,
                }
                messages.append(tool_message)
            
            # Get the next stream after processing tool calls
            response = get_response(model, messages, temperature, max_tokens, tools, response_format)
        
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        output_manager.print_wrapper("", chain_id=chain_id)
        
        # Get the complete text received
        full_reply_content = ''.join([m for m in collected_messages])
        
        # Calculate total tokens if not provided by the API
        if total_tokens_used == 0:
            # Fallback to tiktoken estimation
            encoding = tiktoken.encoding_for_model("gpt-4")
            tokens_per_message = 3
            
            for message in messages:
                prompt_tokens_used += tokens_per_message
                for key, value in message.items():
                    if isinstance(value, str):
                        prompt_tokens_used += len(encoding.encode(value))
            
            completion_tokens_used = len(encoding.encode(full_reply_content))
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
            elapsed_time = time.time() - start_time
            total_tokens_used = prompt_tokens_used + completion_tokens_used
            tokens_per_second = completion_tokens_used / elapsed_time if elapsed_time > 0 else 0
        else:
            output_manager.display_system_messages(f"Groq API Error: {str(e)}")
            raise
    
    # Return format depends on whether tools were used
    if tools:
        return full_reply_content, search_triplets, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second
    else:
        return full_reply_content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second