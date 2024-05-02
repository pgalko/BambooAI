import os
import time
from anthropic import Client

try:
    # Attempt package-relative import
    from . import output_manager
except ImportError:
    # Fall back to script-style import
    import output_manager

output_manager = output_manager.OutputManager()

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

def llm_stream(log_and_call_manager, chain_id: str,messages: str,model: str,temperature: str,max_tokens: str,tools: str = None):  

    collected_messages = []

    client = init()

    messages, system_instruction = convert_openai_to_anthropic(messages)

    response = client.messages.create(
        model=model, 
        system=system_instruction,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        stream =True,
    )

    start_time = time.time()
    for chunk in response:
        if chunk.type == 'content_block_delta':
            chunk_message = chunk.delta.text
            collected_messages.append(chunk_message)
            output_manager.print_wrapper(chunk_message, end='', flush=True)
        elif chunk.type == 'message_delta':
            completion_tokens_used = chunk.usage.output_tokens
        elif chunk.type == 'message_start':
            prompt_tokens_used = chunk.message.usage.input_tokens


    end_time = time.time()
    elapsed_time = end_time - start_time

    output_manager.print_wrapper("")

    full_reply_content = ''.join([m for m in collected_messages])

    # calculate the total tokens used
    total_tokens_used = prompt_tokens_used + completion_tokens_used
    
    if elapsed_time > 0:
        tokens_per_second = completion_tokens_used / elapsed_time
    else:
        tokens_per_second = 0

    return full_reply_content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second