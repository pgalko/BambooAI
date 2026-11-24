import os
import time
import openai
import tiktoken

from bambooai.utils import StoppableStreamWrapper
from bambooai.models import resilience

# The dispatcher's turn-level retry catches exactly these; see models/__init__.
TRANSPORT_ERRORS = (openai.APIError,)

from logger_config import get_logger
logger = get_logger(__name__)

def init():
    API_KEY = os.environ.get('DEEPSEEK_API_KEY')
    #API_KEY = os.environ.get('NVIDIA_NIM')
    if API_KEY is None:
        return
    else:
        # A stalled upstream must surface as an error, not a dead stream
        # the browser blames on the network - same bound every hardened
        # provider carries.
        openai_client = openai.OpenAI(**resilience.timeout_kwargs("openai"))
        openai_client.api_key = API_KEY
        openai_client.base_url = "https://api.deepseek.com"
        #openai_client.base_url = "https://integrate.api.nvidia.com/v1"
        return openai_client

def llm_call(messages: str,model: str,temperature: str,max_tokens: str, response_format: str = None, api_keys=None):
    # api_keys is the dispatcher's uniform calling convention
    # (models/__init__.llm_call passes six positionals to every provider).
    # This function predated it - the step-3 rehabilitation fixed llm_stream
    # and missed this sibling, so a non-streaming dispatch to provider
    # "deepseek" raised TypeError before a single token. Accepted for the
    # convention, exactly as llm_stream does; init() still reads the env key.

    openai_client = init()

    try:
        start_time = time.time()
        response = openai_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )
        end_time = time.time()
    except openai.RateLimitError:
        time.sleep(10)
        start_time = time.time()
        response = openai_client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format = response_format,
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

def llm_stream(prompt_manager, log_and_call_manager, output_manager, chain_id: str, messages: str,model: str,temperature: str,max_tokens: str,tools: str = None, response_format: str = None, reasoning_models: list = None, reasoning_effort:str = "medium", api_keys=None, stop_event=None):
    # api_keys and stop_event are the dispatcher's uniform calling convention
    # (models/__init__.llm_stream passes both to every provider). This module
    # predated them, so every dispatch to provider "deepseek" raised TypeError
    # before a single token - the direct path was unreachable dead code.
    # api_keys is accepted for the convention; init() still reads the env key.
    collected_chunks = []
    collected_messages = []
    reasoning_messages = []

    openai_client = init()


    # PRE-TOKEN STREAM RESTART (generic; see resilience.restartable).
    # Before the first chunk a fresh stream is exactly equivalent, so the
    # open and the pre-token window are retried; a later drop stays fatal.
    response = resilience.restartable(
        lambda: openai_client.chat.completions.create(
            model=model,
            messages=messages,
            #temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            response_format=response_format,
        ),
        openai.APIError, output_manager=output_manager,
        chain_id=chain_id, label="DeepSeek")
    response = StoppableStreamWrapper(response, stop_event)
    
    start_time = time.time()
    # iterate through the stream of events
    for chunk in response:
        delta = chunk.choices[0].delta
        # finish_reason == "length" means the model hit max_tokens and the
        # answer was cut off; say so instead of returning it as complete.
        if getattr(chunk.choices[0], 'finish_reason', None) == 'length':
            resilience.report_truncation(model, max_tokens,
                                         output_manager, chain_id)
        collected_chunks.append(chunk)  # save the event response

        if delta and hasattr(delta, 'content') and delta.content:
            collected_messages.append(delta.content)
            output_manager.print_wrapper(delta.content, end='', flush=True, chain_id=chain_id)
        elif delta and hasattr(delta, 'reasoning_content') and delta.reasoning_content:
            reasoning_messages.append(delta.reasoning_content)
            # thought=True: see openrouter_models. The reasoning belongs in the
            # Thinking block, not appended raw to the output pane.
            output_manager.print_wrapper(delta.reasoning_content, end='', flush=True, chain_id=chain_id, thought=True)

    end_time = time.time()
    elapsed_time = end_time - start_time
    
    output_manager.print_wrapper("",chain_id=chain_id)

    # get the complete reasoning and collected messages content
    full_reply_content = ''.join([m for m in collected_messages])
    reasoning_content = ''.join([m for m in reasoning_messages])

    # Tiktoken encoding
    encoding = tiktoken.encoding_for_model("gpt-4")

    # count the number of response tokens used
    completion_tokens_used = len(encoding.encode(full_reply_content+reasoning_content))

    # count the number of prompt tokens used
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