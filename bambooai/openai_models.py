import json
import os
import time
import openai
import tiktoken

try:
    # Attempt package-relative import
    from . import output_manager, google_search, prompts, utils
except ImportError:
    # Fall back to script-style import
    import output_manager, google_search, prompts, utils

output_handler = output_manager.OutputManager()
google_search_function = google_search.SmartSearchOrchestrator()

def init():
    API_KEY = os.environ.get('OPENAI_API_KEY')
    if API_KEY is None:
        output_handler.print_wrapper("Warning: OPENAI_API_KEY environment variable not found.")
        return
    else:
        openai_client = openai.OpenAI()
        openai_client.api_key = API_KEY
        return openai_client

def llm_call(messages: str,model: str,temperature: str,max_tokens: str):  

    openai_client = init()

    try:
        start_time = time.time()
        response = openai_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        end_time = time.time()
    except openai.RateLimitError:
        output_handler.print_wrapper(
            "The OpenAI API rate limit has been exceeded. Waiting 10 seconds and trying again."
        )
        time.sleep(10)
        start_time = time.time()
        response = openai_client.chat.completions.create(
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

def llm_stream(log_and_call_manager, chain_id: str, messages: str,model: str,temperature: str,max_tokens: str,tools: str = None):  
    collected_chunks = []
    collected_messages = []
    tool_calls = []
    google_search_messages = [{"role": "system", "content": prompts.google_search_react_system.format(utils.get_readable_date())}]

    tools = tools

    openai_client = init()

    available_functions = {
        "google_search": google_search_function
    }

    response = openai_client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        tools=tools,
        stream = True
    )
    
    start_time = time.time()
    # iterate through the stream of events
    for chunk in response:
        delta = chunk.choices[0].delta
        collected_chunks.append(chunk)  # save the event response

        if delta and delta.content:
            collected_messages.append(delta.content)  # save the message
            output_handler.print_wrapper(delta.content, end='', flush=True)
        elif delta and delta.tool_calls:
            tcchunklist = delta.tool_calls
            for tcchunk in tcchunklist:
                if len(tool_calls) <= tcchunk.index:
                    tool_calls.append({"id": "", "type": "function", "function": { "name": "", "arguments": "" } })
                tc = tool_calls[tcchunk.index] 

                if tcchunk.id:
                    tc["id"] += tcchunk.id
                if tcchunk.function.name:
                    tc["function"]["name"] += tcchunk.function.name
                if tcchunk.function.arguments:
                    tc["function"]["arguments"] += tcchunk.function.arguments

    if tool_calls:
        messages.append(
            {
                "tool_calls": tool_calls,
                "role": 'assistant',
            }                    
        )
    
    for index, tool_call in enumerate(tool_calls):
        function_name = tool_call['function']['name']
        function_to_call = available_functions[function_name]
        function_args = json.loads(tool_call['function']['arguments'])
        google_search_messages.append({"role": "user", "content": function_args.get("search_query")})
        function_response = function_to_call(
            log_and_call_manager, 
            chain_id,
            messages=google_search_messages
        )
        
        messages.append(
            {
                "tool_call_id": tool_call['id'],
                "role": "tool",
                "name": function_name,
                "content": function_response,
            }  # extend conversation with function response
        )

        # Check if it's the last tool call in the list before calling 
        if index == len(tool_calls) - 1:
            response = openai_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True
            )

    # iterate through the stream of events
    for chunk in response:
        delta = chunk.choices[0].delta
        collected_chunks.append(chunk)  # save the event response

        if delta and delta.content:
            collected_messages.append(delta.content)  # save the message
            output_handler.print_wrapper(delta.content, end='', flush=True)

    end_time = time.time()
    elapsed_time = end_time - start_time
    
    output_handler.print_wrapper("")

    # get the complete text received
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
            if isinstance(value, str):
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