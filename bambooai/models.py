
import os
import time
import json
import openai
import tiktoken

def load_llm_config():

    default_llm_config = [
    {"agent": "Expert Selector", "details": {"model": "gpt-3.5-turbo-0613", "provider":"openai","max_tokens": 500, "temperature": 0}},
    {"agent": "Analyst Selector", "details": {"model": "gpt-3.5-turbo-0613", "provider":"openai","max_tokens": 500, "temperature": 0}},
    {"agent": "Theorist", "details": {"model": "gpt-3.5-turbo-0613", "provider":"openai","max_tokens": 2000, "temperature": 0}},
    {"agent": "Planner", "details": {"model": "gpt-3.5-turbo-0613", "provider":"openai","max_tokens": 2000, "temperature": 0}},
    {"agent": "Code Generator", "details": {"model": "gpt-3.5-turbo-0613", "provider":"openai","max_tokens": 2000, "temperature": 0}},
    {"agent": "Code Debugger", "details": {"model": "gpt-3.5-turbo-0613", "provider":"openai","max_tokens": 2000, "temperature": 0}},
    {"agent": "Error Corrector", "details": {"model": "gpt-3.5-turbo-0613", "provider":"openai","max_tokens": 2000, "temperature": 0}},
    {"agent": "Code Ranker", "details": {"model": "gpt-3.5-turbo-0613", "provider":"openai","max_tokens": 500, "temperature": 0}},
    {"agent": "Solution Summarizer", "details": {"model": "gpt-3.5-turbo-0613", "provider":"openai","max_tokens": 2000, "temperature": 0}},
    {"agent": "Google Search Query Generator", "details": {"model": "gpt-3.5-turbo-0613", "provider":"openai","max_tokens": 2000, "temperature": 0}},
    {"agent": "Google Search Summarizer", "details": {"model": "gpt-3.5-turbo-16k", "provider":"openai","max_tokens": 2000, "temperature": 0}}
    ]

    # Get the LLM_CONFIG environment variable
    if os.environ.get('LLM_CONFIG'):
        llm_config = os.environ.get('LLM_CONFIG')
        llm_config = json.loads(llm_config)
    # load config from the JSON file
    elif os.path.exists("LLM_CONFIG.json"):
        try:
            with open("LLM_CONFIG.json", 'r') as f:
                llm_config = json.load(f)
        except Exception as e:
            llm_config = default_llm_config
    # Use hardcoded default configuration
    else:
        llm_config = default_llm_config

    return llm_config

def init(agent):
    
    llm_config = load_llm_config()

    for item in llm_config:
        if item['agent'] == agent:
            details = item.get('details', {})
            model = details.get('model', 'Unknown')
            provider = details.get('provider', 'Unknown')
            max_tokens = details.get('max_tokens', 'Unknown')
            temperature = details.get('temperature', 'Unknown')

    if provider == "openai":
        # Get the OPENAI_API_KEY environment variable
        API_KEY = os.environ.get('OPENAI_API_KEY')
        openai.api_key = API_KEY

    return model, provider, max_tokens, temperature

def get_model_name(agent):
    
    llm_config = load_llm_config()

    for item in llm_config:
        if item['agent'] == agent:
            details = item.get('details', {})
            model = details.get('model', 'Unknown')
            provider = details.get('provider', 'Unknown')

    return model, provider

def llm_call(log_and_call_manager, messages: str, agent: str = None, chain_id: str = None):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    default_16K_model = "gpt-3.5-turbo-16k"

    # Initialize the LLM parameters
    model,provider,max_tokens,temperature = init(agent)
    
    # If the provider is local, use the local model instead of OpenAI API
    if provider == "local": 
        try:
            # Attempt package-relative import
            from . import local_models
        except ImportError:
            # Fall back to script-style import
            import local_models
        content_received, local_llm_messages,prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second = local_models.llm_local_stream(messages,model)
        log_and_call_manager.write_to_log(agent, chain_id, timestamp, model, local_llm_messages, content_received, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second)
        return content_received
    else:
        try:
            # Attempt package-relative import
            from . import output_manager
        except ImportError:
            # Fall back to script-style import
            import output_manager

        output_manager = output_manager.OutputManager()
        
        try:
            start_time = time.time()
            response = openai.ChatCompletion.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            end_time = time.time()
        except openai.error.RateLimitError:
            output_manager.print_wrapper(
                "The OpenAI API rate limit has been exceeded. Waiting 10 seconds and trying again."
            )
            time.sleep(10)
            start_time = time.time()
            response = openai.ChatCompletion.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            end_time = time.time()
        # Exceeded the maximum number of tokens allowed by the API
        except openai.error.InvalidRequestError:
            output_manager.print_wrapper(
                "The OpenAI API maximum tokens limit has been exceeded. Switching to a 16K model."
            )
            start_time = time.time()
            response = openai.ChatCompletion.create(
                model=default_16K_model,   
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

        model_used = model
        content_received = content
        prompt_tokens_used = prompt_tokens
        completion_tokens_used = completion_tokens
        total_tokens_used = total_tokens
        if elapsed_time > 0:
            tokens_per_second = completion_tokens_used / elapsed_time
        else:
            tokens_per_second = 0
        
        log_and_call_manager.write_to_log(agent, chain_id, timestamp, model_used, messages, content_received, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time,tokens_per_second)

        return content

def llm_func_call(log_and_call_manager, messages: str, functions: str, function_name: str, agent: str = None, chain_id: str = None):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())

    # Initialize the LLM parameters
    model,provider,max_tokens,temperature = init(agent)

    try:
        # Attempt package-relative import
        from . import output_manager
    except ImportError:
        # Fall back to script-style import
        import output_manager

    output_manager = output_manager.OutputManager()

    try:
        start_time = time.time()
        response = openai.ChatCompletion.create(
        model = model,
        messages=messages,
        functions=functions,
        function_call = function_name,
        temperature=temperature,
        max_tokens = max_tokens, 
        )
        end_time = time.time()
    except openai.error.RateLimitError:
        output_manager.print_wrapper(
            "The OpenAI API rate limit has been exceeded. Waiting 10 seconds and trying again."
        )
        time.sleep(10)
        start_time = time.time()
        response = openai.ChatCompletion.create(
        model = model,
        messages=messages,
        functions=functions,
        function_call = function_name,
        temperature=temperature,
        )
        end_time = time.time()

    elapsed_time = end_time - start_time
    
    fn_name = response.choices[0].message["function_call"].name
    arguments = response.choices[0].message["function_call"].arguments
    prompt_tokens = response.usage.prompt_tokens
    completion_tokens = response.usage.completion_tokens
    total_tokens = response.usage.total_tokens

    tokens_per_second = completion_tokens / elapsed_time
    
    log_and_call_manager.write_to_log(agent, chain_id, timestamp, model, messages, arguments, prompt_tokens, completion_tokens, total_tokens, elapsed_time,tokens_per_second)

    return fn_name,arguments

def llm_stream(log_and_call_manager, messages: str, agent: str = None, chain_id: str = None): 
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    default_16K_model = "gpt-3.5-turbo-16k"

    # Initialize the LLM parameters
    model,provider,max_tokens,temperature = init(agent)

    # If the provider is local, use the local model instead of OpenAI API
    if provider == "local": 
        try:
            # Attempt package-relative import
            from . import local_models
        except ImportError:
            # Fall back to script-style import
            import local_models
        content_received, local_llm_messages,prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second = local_models.llm_local_stream(messages,model)
        log_and_call_manager.write_to_log(agent, chain_id, timestamp, model, local_llm_messages, content_received, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second)
        return content_received
    else:
        try:
            # Attempt package-relative import
            from . import output_manager
        except ImportError:
            # Fall back to script-style import
            import output_manager

        output_manager = output_manager.OutputManager()
        
        try:
            response = openai.ChatCompletion.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream = True
            )
        except openai.error.RateLimitError:
            output_manager.print_wrapper(
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
            output_manager.print_wrapper(
                "The OpenAI API maximum tokens limit has been exceeded. Switching to a 16K model."
            )
            response = openai.ChatCompletion.create(
                model=default_16K_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream = True
            )
        
        # create variables to collect the stream of chunks
        collected_chunks = []
        collected_messages = []
       
        start_time = time.time()
         # iterate through the stream of events
        for chunk in response:
            collected_chunks.append(chunk)  # save the event response
            chunk_message = chunk['choices'][0]['delta']  # extract the message
            collected_messages.append(chunk_message)  # save the message
            output_manager.print_wrapper(chunk_message.get('content', ''), end='', flush=True)  # output_manager.print_wrapper the message without a newline

        end_time = time.time()
        elapsed_time = end_time - start_time
        
        output_manager.print_wrapper("")  # output_manager.print_wrapper a newline

        # get the complete text received
        full_reply_content = ''.join([m.get('content', '') for m in collected_messages])

        model_used = model
        content_received = full_reply_content

        # count the number of response tokens used
        completion_tokens_used = len(collected_chunks)

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
        total_tokens_used = prompt_tokens_used + completion_tokens_used
        
        if elapsed_time > 0:
            tokens_per_second = completion_tokens_used / elapsed_time
        else:
            tokens_per_second = 0

        log_and_call_manager.write_to_log(agent, chain_id, timestamp, model_used, messages, content_received, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second)

        return full_reply_content