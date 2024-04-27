import time
from ollama import Client
import tiktoken

client = Client()

try:
    # Attempt package-relative import
    from . import output_manager
except ImportError:
    # Fall back to script-style import
    import output_manager

output_manager = output_manager.OutputManager()

def llm_call(messages: str,model: str,temperature: str,max_tokens: str):  
    client = Client(host='http://localhost:11434')

    start_time = time.time()

    response = client.chat(
        model=model, 
        messages=messages,
        options = {
            'temperature': temperature,
            'top_k': 10,
        }, 
    )

    end_time = time.time()

    content = response['message']['content']

    elapsed_time = end_time - start_time

    prompt_tokens_used = response['prompt_eval_count']
    completion_tokens_used = response['eval_count']
    total_tokens_used = prompt_tokens_used + completion_tokens_used
    
    if elapsed_time > 0:
        tokens_per_second = completion_tokens_used / elapsed_time
    else:
        tokens_per_second = 0

    return content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second

def llm_stream(messages: str,model: str,temperature: str,max_tokens: str):  
    collected_chunks = []
    collected_messages = []

    client = Client(host='http://localhost:11434')
    response = client.chat(
        model=model, 
        messages=messages,
        stream =True,
        options = {
            'temperature': temperature,
            'top_k': 10,
        }, 
    )

    start_time = time.time()
    for chunk in response:
        collected_chunks.append(chunk)
        chunk_message = chunk['message']['content']
        collected_messages.append(chunk_message)
        output_manager.print_wrapper(chunk_message, end='', flush=True)  

    end_time = time.time()
    elapsed_time = end_time - start_time

    output_manager.print_wrapper("")

    full_reply_content = ''.join([m for m in collected_messages])

    # count the number of response tokens used
    completion_tokens_used = len(collected_chunks)

    # count the number of prompt tokens used
    encoding = tiktoken.encoding_for_model("gpt-4")   
    tokens_per_message = 3
    tokens_per_name = 1
    prompt_tokens_used = 0
    for message in messages:
        prompt_tokens_used += tokens_per_message
        for key, value in message.items():
            prompt_tokens_used += len(encoding.encode(value))
            if key == "name":
                prompt_tokens_used += tokens_per_name
    prompt_tokens_used += 3  # every reply is primed with <|start|>assistant<|message|>

    # calculate the total tokens used
    total_tokens_used = prompt_tokens_used + completion_tokens_used
    
    if elapsed_time > 0:
        tokens_per_second = completion_tokens_used / elapsed_time
    else:
        tokens_per_second = 0

    return full_reply_content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second
