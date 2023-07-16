
import os
import time
import openai
import tiktoken

def init_openai():
    # Get the OPENAI_API_KEY environment variable
    API_KEY = os.environ.get('OPENAI_API_KEY')
    openai.api_key = API_KEY

def llm_call( model_dict: dict, messages: str, temperature: float = 0, max_tokens: int = 1000, llm_cascade: bool = False):
    init_openai()
    model = model_dict['llm']
    if llm_cascade:
        model = model_dict['llm_gpt4']
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except openai.error.RateLimitError:
        print(
            "The OpenAI API rate limit has been exceeded. Waiting 10 seconds and trying again."
        )
        time.sleep(10)
        response = openai.ChatCompletion.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    # Exceeded the maximum number of tokens allowed by the API
    except openai.error.InvalidRequestError:
        print(
            "The OpenAI API maximum tokens limit has been exceeded. Switching to a 16K model."
        )
        response = openai.ChatCompletion.create(
            model=model_dict['llm_16k'],   
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    content = response.choices[0].message.content.strip()
    tokens_used = response.usage.total_tokens

    return content, tokens_used

def llm_func_call(model_dict: dict, messages: str, functions: str, function_name: str):
    init_openai()
    model = model_dict['llm_func']
    try:
        response = openai.ChatCompletion.create(
        model = model,
        messages=messages,
        functions=functions,
        function_call = function_name,
        temperature=0,
        max_tokens = 700, 
        )
    except openai.error.RateLimitError:
        print(
            "The OpenAI API rate limit has been exceeded. Waiting 10 seconds and trying again."
        )
        time.sleep(10)
        response = openai.ChatCompletion.create(
        model = model,
        messages=messages,
        functions=functions,
        function_call = function_name,
        temperature=0,
        )
    
    fn_name = response.choices[0].message["function_call"].name
    arguments = response.choices[0].message["function_call"].arguments
    tokens_used = response.usage.total_tokens

    return fn_name,arguments,tokens_used

def llm_stream(model_dict: dict, messages: str, temperature: float = 0, max_tokens: int = 1000, llm_cascade: bool = False):
    init_openai()
    model = model_dict['llm']
    if llm_cascade:
        model = model_dict['llm_gpt4']
    try:
        response = openai.ChatCompletion.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream = True
        )
    except openai.error.RateLimitError:
        print(
            "The OpenAI API rate limit has been exceeded. Waiting 10 seconds and trying again."
        )
        time.sleep(10)
        response = openai.ChatCompletion.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream = True
        )
    # Exceeded the maximum number of tokens allowed by the API
    except openai.error.InvalidRequestError:
        print(
            "The OpenAI API maximum tokens limit has been exceeded. Switching to a 16K model."
        )
        response = openai.ChatCompletion.create(
            model=model_dict['llm_16k'],
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream = True
        )
    
    # create variables to collect the stream of chunks
    collected_chunks = []
    collected_messages = []
    # iterate through the stream of events
    for chunk in response:
        collected_chunks.append(chunk)  # save the event response
        chunk_message = chunk['choices'][0]['delta']  # extract the message
        collected_messages.append(chunk_message)  # save the message
        print(chunk_message.get('content', ''), end='', flush=True)  # print the message without a newline
    
    print()  # print a newline

    # get the complete text received
    full_reply_content = ''.join([m.get('content', '') for m in collected_messages])

    # count the number of response tokens used
    response_tokens_used = len(collected_chunks)

    # count the number of prompt tokens used
    encoding = tiktoken.encoding_for_model(model)   
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
    total_tokens_used = prompt_tokens_used + response_tokens_used

    return full_reply_content, total_tokens_used
