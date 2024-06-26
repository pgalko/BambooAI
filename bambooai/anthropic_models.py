import json
import os
import time
from anthropic import Client

try:
    # Attempt package-relative import
    from . import output_manager, google_search, prompts, utils
except ImportError:
    # Fall back to script-style import
    import output_manager, google_search, prompts, utils

output_handler = output_manager.OutputManager()
google_search_function = google_search.SmartSearchOrchestrator()

def init():
    API_KEY = os.environ.get('ANTHROPIC_API_KEY')
    if API_KEY is None:
        output_manager.print_wrapper("Warning: ANTHROPIC_API_KEY environment variable not found.")
        return
    else:
        client = Client()
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

def llm_call(messages: str,model: str,temperature: str,max_tokens: str):  

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

def call_and_parse_stream(collected_messages, tools, messages,  system_instruction, model, temperature, max_tokens):
    client = init()
    tool_calls = []
    tool_use_block = None
    
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
                output_handler.print_wrapper(content, end='', flush=True)
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
                output_handler.print_wrapper(content, end='', flush=True)
            elif chunk.delta.type == "input_json_delta":
                if current_tool_call:
                    current_tool_call["function"]["arguments"] += chunk.delta.partial_json
        elif chunk.type == "content_block_stop":
            if chunk.index == 0:
                collected_messages.append(full_content)
                text_block.text =  full_content
            elif current_tool_call:
                tool_calls.append(current_tool_call)
                tool_use_block.input = json.loads(current_tool_call["function"]["arguments"])
        elif chunk.type == 'message_delta':
            completion_tokens_used = chunk.usage.output_tokens
        elif chunk.type == 'message_start':
            prompt_tokens_used = chunk.message.usage.input_tokens

    return messages, collected_messages, tool_calls, tool_use_block, text_block, prompt_tokens_used, completion_tokens_used

def llm_stream(log_and_call_manager, chain_id: str, messages: list, model: str, temperature: float, max_tokens: int, tools: list = []): 
    total_tokens_used = 0
    prompt_tokens_used = 0
    completion_tokens_used = 0
    tokens_per_second = 0
    collected_messages = []
    google_search_messages = [{"role": "system", "content": prompts.google_search_react_system.format(utils.get_readable_date())}]

    available_functions = {
        "google_search": google_search_function
    }

    messages, system_instruction = convert_openai_to_anthropic(messages)
    

    start_time = time.time()
    
    while True:
        messages, collected_messages, tool_calls, tool_use_block, text_block, new_prompt_tokens, new_completion_tokens = call_and_parse_stream(collected_messages, tools, messages,  system_instruction, model, temperature, max_tokens)

        prompt_tokens_used += new_prompt_tokens
        completion_tokens_used += new_completion_tokens

        if tool_calls:
            messages.append(
                {
                    "role": "assistant", 
                    "content": [text_block, tool_use_block]
                }
            )

            for tool_call in tool_calls:
                function_name = tool_call['function']['name']
                function_to_call = available_functions[function_name]
                function_args = json.loads(tool_call['function']['arguments'])
                google_search_messages.append({"role": "user", "content": function_args.get("search_query")})
                function_response = function_to_call(
                    log_and_call_manager, 
                    chain_id,
                    google_search_messages
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

    output_handler.print_wrapper("")

    full_reply_content = ''.join(collected_messages)

    # calculate the token usage
    total_tokens_used = prompt_tokens_used + completion_tokens_used
    
    if elapsed_time > 0:
        tokens_per_second = completion_tokens_used / elapsed_time
    else:
        tokens_per_second = 0

    return full_reply_content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second