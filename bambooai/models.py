
import os
import time
import openai
import tiktoken
import json
import logging
from logging.handlers import RotatingFileHandler
from IPython.display import display, HTML
from termcolor import cprint
import sys

# Initialize the logger
logger = logging.getLogger('bambooai_logger')
logger.setLevel(logging.INFO)

# Disable propagation to the root logger
logger.propagate = False

# Remove all handlers associated with the logger object.
for handler in logger.handlers:
    logger.removeHandler(handler)

# Initialize the Rotating File Handler
handler = RotatingFileHandler('bambooai_log.log', maxBytes=5*1024*1024, backupCount=3)  # 5 MB
logger.addHandler(handler)

class LogAndCallManager:
    def __init__(self, token_cost_dict):
        self.token_summary = {}
        self.token_cost_dict = token_cost_dict
        
    def update_token_summary(self, chain_id, prompt_tokens, completion_tokens, total_tokens, elapsed_time, cost):
        if chain_id not in self.token_summary:
            self.token_summary[chain_id] = {'prompt_tokens': 0, 'completion_tokens': 0, 'total_tokens': 0, 'elapsed_time': 0,'total_cost': 0}
        
        self.token_summary[chain_id]['prompt_tokens'] += prompt_tokens
        self.token_summary[chain_id]['completion_tokens'] += completion_tokens
        self.token_summary[chain_id]['total_tokens'] += total_tokens
        self.token_summary[chain_id]['elapsed_time'] += elapsed_time
        self.token_summary[chain_id]['total_cost'] += cost

    def write_summary_to_log(self):
        log_entry = "\n" + "*" * 100 + "\n"
        log_entry += f"CHAIN COMPLETED"
        log_entry += "\n" + "*" * 100 + "\n"
        log_entry += "\n*** Chain Summary ***\n"

        for chain_id, tokens in self.token_summary.items():
            avg_speed = tokens['completion_tokens'] / tokens['elapsed_time']

            log_entry += f"Chain ID: {chain_id}\n"
            log_entry += f"Prompt Tokens: {tokens['prompt_tokens']}\n"
            log_entry += f"Completion Tokens: {tokens['completion_tokens']}\n"
            log_entry += f"Total Tokens: {tokens['total_tokens']}\n"
            log_entry += f"Total Time (LLM Interact.): {tokens['elapsed_time']:.2f} seconds\n"
            log_entry += f"Average Response Speed: {avg_speed:.2f} tokens/second\n"
            log_entry += f"Total Cost: ${tokens['total_cost']:.4f}\n"
            
        log_entry += "\n" + "*" * 100 + "\n"
        log_entry += f"NEW CHAIN"
        log_entry += "\n" + "*" * 100 + "\n"

        logger.info(log_entry)

    def print_summary_to_terminal(self):
        summary_text = ""
        for chain_id, tokens in self.token_summary.items():
            avg_speed = tokens['completion_tokens'] / tokens['elapsed_time']

            summary_text += f"Chain ID: {chain_id}\n"
            summary_text += f"Prompt Tokens: {tokens['prompt_tokens']}\n"
            summary_text += f"Completion Tokens: {tokens['completion_tokens']}\n"
            summary_text += f"Total Tokens: {tokens['total_tokens']}\n"
            summary_text += f"Total Time (LLM Interact.): {tokens['elapsed_time']:.2f} seconds\n"
            summary_text += f"Average Response Speed: {avg_speed:.2f} tokens/second\n"
            summary_text += f"Total Cost: ${tokens['total_cost']:.4f}\n"

        if 'ipykernel' in sys.modules:
            # Jupyter notebook or ipython
            display(HTML(f'''
            <br>
            <p><b style="color: blue;">Chain Summary (Detailed info in bambooai_log.log file):</b></p>
            <pre style="color: black; white-space: pre-line;">{summary_text}</pre>
            '''))
        else:
            # Other environment (like terminal)
            cprint("\n>> Chain Summary (Detailed info in bambooai_log.log file):", 'yellow', attrs=['bold'])
            print(summary_text)

    def write_to_log(self, tool, chain_id, timestamp, model, messages, content, prompt_tokens, completion_tokens, total_tokens, elapsed_time, tokens_per_second):
        # Calculate the costs
        token_costs = self.token_cost_dict.get(model, {})
        prompt_token_cost = token_costs.get('prompt_tokens', 0)
        completion_token_cost = token_costs.get('completion_tokens', 0)
        cost = ((prompt_tokens * prompt_token_cost) / 1000) + ((completion_tokens * completion_token_cost) / 1000)
        
        self.update_token_summary(chain_id, prompt_tokens, completion_tokens, total_tokens, elapsed_time, cost)

        log_entry = "\n" + "=" * 100 + "\n"
        log_entry += f"Tool: {tool}\n"
        log_entry += f"Chain ID: {chain_id}\n"
        log_entry += f"Timestamp (GMT): {timestamp}\n"
        log_entry += f"Model: {model}\n"
        log_entry += "=" * 100 + "\n"
        log_entry += "\n=== Messages ===\n"
        pretty_messages = json.dumps(messages, indent=2)
        log_entry += pretty_messages + "\n"
        log_entry += "\n=== Response ===\n"
        log_entry += content + "\n"
        log_entry += "\n=== Statistics ===\n"
        log_entry += f"Prompt Tokens: {prompt_tokens} tokens\n"
        log_entry += f"Completion Tokens: {completion_tokens} tokens\n"
        log_entry += f"Total Tokens: {total_tokens} tokens\n"
        log_entry += f"Total Time: {elapsed_time:.2f} seconds\n"
        log_entry += f"Response Speed: {tokens_per_second:.2f} tokens/second\n"
        log_entry += f"Cost: ${cost:.4f}\n"
        
        logger.info(log_entry)

def init_openai():
    # Get the OPENAI_API_KEY environment variable
    API_KEY = os.environ.get('OPENAI_API_KEY')
    openai.api_key = API_KEY

def llm_call(log_and_call_manager, model_dict: dict, messages: str, temperature: float = 0, max_tokens: int = 1000, llm_cascade: bool = False, local_model: str = None, tool: str = None, chain_id: str = None):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    #If local_model is not None, and llm_cascade is False use local model instead of OpenAI API
    if local_model and not llm_cascade: 
        try:
            # Attempt package-relative import
            from . import local_models
        except ImportError:
            # Fall back to script-style import
            import local_models
        content_received, local_llm_messages,prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second = local_models.llm_local_stream(messages,local_model)
        log_and_call_manager.write_to_log(tool, chain_id, timestamp, local_model, local_llm_messages, content_received, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second)
        return content_received, total_tokens_used
    #If local_model is None, use OpenAI API
    else:
        init_openai()
        model = model_dict['llm']
        if llm_cascade:
            model = model_dict['llm_gpt4']
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
            print(
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
            print(
                "The OpenAI API maximum tokens limit has been exceeded. Switching to a 16K model."
            )
            start_time = time.time()
            response = openai.ChatCompletion.create(
                model=model_dict['llm_16k'],   
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
            tokens_per_second = 'N/A'
        
        log_and_call_manager.write_to_log(tool, chain_id, timestamp, model_used, messages, content_received, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time,tokens_per_second)

        return content

def llm_func_call(log_and_call_manager, model_dict: dict, messages: str, functions: str, function_name: str, tool: str = None, chain_id: str = None):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    init_openai()
    model = model_dict['llm_func']
    try:
        start_time = time.time()
        response = openai.ChatCompletion.create(
        model = model,
        messages=messages,
        functions=functions,
        function_call = function_name,
        temperature=0,
        max_tokens = 700, 
        )
        end_time = time.time()
    except openai.error.RateLimitError:
        print(
            "The OpenAI API rate limit has been exceeded. Waiting 10 seconds and trying again."
        )
        time.sleep(10)
        start_time = time.time()
        response = openai.ChatCompletion.create(
        model = model,
        messages=messages,
        functions=functions,
        function_call = function_name,
        temperature=0,
        )
        end_time = time.time()

    elapsed_time = end_time - start_time
    
    fn_name = response.choices[0].message["function_call"].name
    arguments = response.choices[0].message["function_call"].arguments
    prompt_tokens = response.usage.prompt_tokens
    completion_tokens = response.usage.completion_tokens
    total_tokens = response.usage.total_tokens

    tokens_per_second = completion_tokens / elapsed_time
    
    log_and_call_manager.write_to_log(tool, chain_id, timestamp, model, messages, arguments, prompt_tokens, completion_tokens, total_tokens, elapsed_time,tokens_per_second)

    return fn_name,arguments

def llm_stream(log_and_call_manager, model_dict: dict, messages: str, temperature: float = 0, max_tokens: int = 1000, llm_cascade: bool = False, local_model: str = None, tool: str = None, chain_id: str = None): 
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    #If local_model is not None, and llm_cascade is False use local model instead of OpenAI API
    if local_model and not llm_cascade: 
        try:
            # Attempt package-relative import
            from . import local_models
        except ImportError:
            # Fall back to script-style import
            import local_models
        content_received, local_llm_messages,prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second = local_models.llm_local_stream(messages,local_model)
        log_and_call_manager.write_to_log(tool, chain_id, timestamp, local_model, local_llm_messages, content_received, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second)
        return content_received, total_tokens_used
    #If local_model is None, use OpenAI API
    else:
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
       
        start_time = time.time()
         # iterate through the stream of events
        for chunk in response:
            collected_chunks.append(chunk)  # save the event response
            chunk_message = chunk['choices'][0]['delta']  # extract the message
            collected_messages.append(chunk_message)  # save the message
            print(chunk_message.get('content', ''), end='', flush=True)  # print the message without a newline

        end_time = time.time()
        elapsed_time = end_time - start_time
        
        print()  # print a newline

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

        tokens_per_second = completion_tokens_used / elapsed_time

        log_and_call_manager.write_to_log(tool, chain_id, timestamp, model_used, messages, content_received, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second)

        return full_reply_content