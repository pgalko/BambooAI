import json
import os
import time
import openai

from bambooai import google_search, utils, context_retrieval

google_search_function = google_search.SmartSearchOrchestrator()
request_user_context = context_retrieval.request_user_context

def init():
    API_KEY = os.environ.get('OPENAI_API_KEY')
    if API_KEY is None:
        return
    else:
        openai_client = openai.OpenAI()
        openai_client.api_key = API_KEY
        return openai_client

def llm_call(messages: str,model: str,temperature: str,max_tokens: str, response_format: str = None):  

    openai_client = init()

    def get_response(model, messages, temperature, max_tokens, response_format):
        if model == 'o1-mini' or model == 'o1-preview':
            messages = [message for message in messages if message.get('role') != 'system']
            return openai_client.chat.completions.create(
                model=model,
                messages=messages,
            )
        else:
            return openai_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )

    try:
        start_time = time.time()
        response = get_response(model, messages, temperature, max_tokens, response_format)
        end_time = time.time()
    except openai.RateLimitError:
        time.sleep(10)
        start_time = time.time()
        response = get_response(model, messages, temperature, max_tokens, response_format)
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

def llm_stream(prompt_manager, log_and_call_manager, output_manager, chain_id: str, messages: str,model: str,temperature: str,max_tokens: str,tools: str = None, response_format: str = None, reasoning_models: list = None, reasoning_effort:str = "medium"):  
    collected_chunks = []
    collected_messages = []
    tool_calls = []
    search_triplets = []
    google_search_messages = [{"role": "system", "content": prompt_manager.google_search_react_system.format(utils.get_readable_date())}]

    tools = tools

    openai_client = init()

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

    def get_response(model, messages, temperature, max_tokens, tools, response_format, reasoning_models=None, reasoning_effort="medium"):
        if reasoning_models and model in reasoning_models:
            output_manager.display_tool_info('Thinking', f"Model needs a moment to think...", chain_id=chain_id)
            return openai_client.chat.completions.create(
                model=model,
                messages=messages,
                reasoning_effort=reasoning_effort,
                max_completion_tokens=max_tokens,
                tools=tools,
                stream=True,
                stream_options={"include_usage": True}
            )
            
        else:
            return openai_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
                stream=True,
                stream_options={"include_usage": True},
                response_format=response_format,
            )
        
    try:
        combined_prompt_tokens_used = 0
        combined_completion_tokens_used = 0
        combined_total_tokens_used = 0

        response = get_response(model, messages, temperature, max_tokens, tools, response_format, reasoning_models, reasoning_effort)

        start_time = time.time()
        # iterate through the stream of events
        for chunk in response:
            if chunk.choices:  # Only proceed if there are choices
                delta = chunk.choices[0].delta
                collected_chunks.append(chunk)  # save the event response

                if delta and delta.content is not None:
                    collected_messages.append(delta.content)  # save the message
                    output_manager.print_wrapper(delta.content,end="",flush=True,chain_id=chain_id)
                elif delta and delta.tool_calls:
                    for tcchunk in delta.tool_calls:
                        # Ensure tool_calls list is large enough:
                        while len(tool_calls) <= tcchunk.index:
                            tool_calls.append({"id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                        tc = tool_calls[tcchunk.index]
            
                        if tcchunk.id:
                            tc["id"] += tcchunk.id
                        if tcchunk.function.name:
                            tc["function"]["name"] += tcchunk.function.name
                        if tcchunk.function.arguments:
                            tc["function"]["arguments"] += tcchunk.function.arguments

            # If there are no choices but usage data is present, accumulate usage tokens.
            elif hasattr(chunk, 'usage') and chunk.usage:
                combined_prompt_tokens_used += chunk.usage.prompt_tokens
                combined_completion_tokens_used += chunk.usage.completion_tokens
                combined_total_tokens_used += chunk.usage.total_tokens

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
                    chain_id,
                    function_args.get("query_clarification"),
                    function_args.get("context_needed")
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
                response = get_response(model, messages, temperature, max_tokens, tools, response_format, reasoning_models, reasoning_effort)

        # iterate through the stream of events
        for chunk in response:
            # Check if there are any choices
            if chunk.choices:
                # If the first choice's delta has content, process it
                if chunk.choices[0].delta.content is not None:
                    delta = chunk.choices[0].delta
                    collected_chunks.append(chunk)           # Save the event response
                    collected_messages.append(delta.content)   # Save the message
                    output_manager.print_wrapper(
                        delta.content,
                        end="",
                        flush=True,
                        chain_id=chain_id
                    )
            # If there are no choices but usage data is present, accumulate usage tokens
            elif hasattr(chunk, 'usage') and chunk.usage:
                combined_prompt_tokens_used += chunk.usage.prompt_tokens
                combined_completion_tokens_used += chunk.usage.completion_tokens
                combined_total_tokens_used += chunk.usage.total_tokens

        end_time = time.time()
        elapsed_time = end_time - start_time

        prompt_tokens_used = combined_prompt_tokens_used
        completion_tokens_used = combined_completion_tokens_used
        total_tokens_used = combined_total_tokens_used

    except openai.APIError as e:
        error_message = e.body.get('message')
        output_manager.display_system_messages(f"Openai API Error: {error_message}")
        raise
    except Exception as e:
        output_manager.display_system_messages(f"Unexpected error: {str(e)}")
        raise
    
    output_manager.print_wrapper("",chain_id=chain_id)

    # get the complete text received
    full_reply_content = ''.join([m for m in collected_messages])
    
    if elapsed_time > 0:
        tokens_per_second = completion_tokens_used / elapsed_time
    else:
        tokens_per_second = 0

    if tools:
        return full_reply_content, search_triplets, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second
    else:
        return full_reply_content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second