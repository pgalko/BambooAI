import os
import time
import google.generativeai as gemini

try:
    # Attempt package-relative import
    from . import output_manager
except ImportError:
    # Fall back to script-style import
    import output_manager

output_manager = output_manager.OutputManager()

def init():
    API_KEY = os.environ.get('GEMINI_API_KEY')
    gemini.configure(api_key=API_KEY)

def convert_openai_to_gemini(messages):
    updated_data = []
    system_content = None
    for item in messages:
        if item['role'] == 'system':
            system_content = item['content']
            continue 
        if item['role'] == 'assistant':
            item['role'] = 'model'
        item['parts'] = f"[{item.pop('content').strip()}]"
        updated_data.append(item)

    return updated_data, system_content

def llm_call(messages: str,model: str,temperature: str,max_tokens: str):  

    init()

    messages, system_instruction = convert_openai_to_gemini(messages)

    generation_config = {
        "temperature": temperature,
        "top_p": 1,
        "top_k": 1,
        "max_output_tokens": max_tokens,
    }

    model = gemini.GenerativeModel(model_name=model,
        generation_config=generation_config,
        system_instruction = system_instruction
    )

    start_time = time.time()


    response = model.generate_content(messages)

    end_time = time.time()

    elapsed_time = end_time - start_time

    content = response.text
    prompt_tokens_used = model.count_tokens(messages).total_tokens
    completion_tokens_used = model.count_tokens(content).total_tokens
    total_tokens_used = prompt_tokens_used + completion_tokens_used

    if elapsed_time > 0:
        tokens_per_second = completion_tokens_used / elapsed_time
    else:
        tokens_per_second = 0

    return content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second

def llm_stream(messages: str,model: str,temperature: str,max_tokens: str):
    collected_messages = []  

    init()

    messages, system_instruction = convert_openai_to_gemini(messages)

    generation_config = {
        "temperature": temperature,
        "top_p": 1,
        "top_k": 1,
        "max_output_tokens": max_tokens,
    }

    model = gemini.GenerativeModel(model_name=model,
        generation_config=generation_config,
        system_instruction = system_instruction,
    )

    response = model.generate_content(messages, stream=True)

    start_time = time.time()
    for chunk in response:
        if chunk.text is not None:
            chunk_message = chunk.text
            collected_messages.append(chunk_message)
            output_manager.print_wrapper(chunk_message, end='', flush=True)  

    end_time = time.time()
    elapsed_time = end_time - start_time

    output_manager.print_wrapper("")

    full_reply_content = ''.join([m for m in collected_messages])

    # Count tokens used
    completion_tokens_used = model.count_tokens(full_reply_content).total_tokens
    prompt_tokens_used = model.count_tokens(messages).total_tokens

    # calculate the total tokens used
    total_tokens_used = prompt_tokens_used + completion_tokens_used
    
    if elapsed_time > 0:
        tokens_per_second = completion_tokens_used / elapsed_time
    else:
        tokens_per_second = 0

    return full_reply_content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second