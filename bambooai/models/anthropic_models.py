import json
import os
import time
import anthropic
import logging

from bambooai import google_search, utils, context_retrieval

# Define the available functions
google_search_function = google_search.SmartSearchOrchestrator()
request_user_context = context_retrieval.request_user_context

def init():
    API_KEY = os.environ.get('ANTHROPIC_API_KEY')
    if API_KEY is None:
        return
    else:
        client = anthropic.Client()
        client.api_key = API_KEY
        return client

def convert_openai_to_anthropic(messages):
    updated_data = []
    system_content = ""
    for item in messages:
        if item['role'] == 'system':
            system_content = item['content']
            continue 
        updated_data.append(item) 

    return updated_data, system_content

def llm_call(messages: str,model: str,temperature: str,max_tokens: str, response_format: str = None):  

    client = init()

    messages, system_instruction = convert_openai_to_anthropic(messages)

    start_time = time.time()
    
    response = client.messages.create(
        model=model, 
        system=system_instruction,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    end_time = time.time()

    elapsed_time = end_time - start_time

    content = response.content[0].text

    prompt_tokens_used = response.usage.input_tokens
    completion_tokens_used = response.usage.output_tokens
    total_tokens_used = prompt_tokens_used + completion_tokens_used

    if elapsed_time > 0:
        tokens_per_second = completion_tokens_used / elapsed_time
    else:
        tokens_per_second = 0

    return content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second

def call_and_parse_stream(output_manager, collected_messages, tools, messages, system_instruction, model, temperature, max_tokens, chain_id):
    client = init()
    tool_calls = []
    tool_use_block = None
    text_block = None  # Initialize text_block to None
    
    # Prepare the base parameters for the API call
    api_params = {
        "model": model,
        "system": system_instruction,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": True,
    }
    
    # Only include the 'tools' parameter if it's not empty
    if tools:
        api_params["tools"] = tools
    
    try:
        response = client.messages.create(**api_params)
        
        full_content = ""
        tool_calls = []
        current_tool_call = None

        for chunk in response:
            if chunk.type == "content_block_start":
                if chunk.content_block.type == "text":
                    content = chunk.content_block.text
                    full_content += content
                    text_block = chunk.content_block
                    output_manager.print_wrapper(content, end='', flush=True, chain_id=chain_id)
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
            elif chunk.type == "content_block_delta":
                if chunk.delta.type == "text_delta":
                    content = chunk.delta.text
                    full_content += content
                    output_manager.print_wrapper(content, end='', flush=True, chain_id=chain_id)
                elif chunk.delta.type == "input_json_delta":
                    if current_tool_call:
                        current_tool_call["function"]["arguments"] += chunk.delta.partial_json
            elif chunk.type == "content_block_stop":
                if chunk.index == 0 and text_block is not None:  # Check if text_block exists
                    collected_messages.append(full_content)
                    text_block.text = full_content
                elif current_tool_call:
                    tool_calls.append(current_tool_call)
                    tool_use_block.input = json.loads(current_tool_call["function"]["arguments"])
            elif chunk.type == 'message_delta':
                completion_tokens_used = chunk.usage.output_tokens
            elif chunk.type == 'message_start':
                prompt_tokens_used = chunk.message.usage.input_tokens

        # Default values in case they weren't set
        prompt_tokens_used = prompt_tokens_used if 'prompt_tokens_used' in locals() else 0
        completion_tokens_used = completion_tokens_used if 'completion_tokens_used' in locals() else 0

    except (anthropic.APIError) as e:
        error_message = e.body.get('error', {}).get('message', 'Unknown error')
        output_manager.display_system_messages(f"Anthropic API Error: {error_message}")
        raise
    except Exception as e:
        output_manager.display_system_messages(f"Unexpected error: {str(e)}")
        raise
    
    return messages, collected_messages, tool_calls, tool_use_block, text_block, prompt_tokens_used, completion_tokens_used

def llm_stream(prompt_manager, log_and_call_manager, output_manager, chain_id: str, messages: list, model: str, temperature: float, max_tokens: int, tools: list = [], response_format: str = None, reasoning_models: list = None, reasoning_effort:str = "medium"): 
    total_tokens_used = 0
    prompt_tokens_used = 0
    completion_tokens_used = 0
    tokens_per_second = 0
    collected_messages = []
    google_search_messages = [{"role": "system", "content": prompt_manager.google_search_react_system.format(utils.get_readable_date())}]
    search_triplets = []

    available_functions = {
        "google_search": google_search_function,
        "request_user_context": request_user_context
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
        messages, collected_messages, tool_calls, tool_use_block, text_block, new_prompt_tokens, new_completion_tokens = call_and_parse_stream(output_manager, collected_messages, tools, messages, system_instruction, model, temperature, max_tokens, chain_id)

        prompt_tokens_used += new_prompt_tokens
        completion_tokens_used += new_completion_tokens

        if tool_calls:
            # Create the assistant message content appropriately based on whether text_block exists
            if text_block is not None:
                assistant_content = [text_block, tool_use_block]
            else:
                assistant_content = [tool_use_block]
                
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
                        chain_id,
                        function_args.get("query_clarification"),
                        function_args.get("context_needed")
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

    if tools:
        return full_reply_content, search_triplets, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second
    else:
        return full_reply_content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second