import os
import threading
import time
import openai

from bambooai.utils import StoppableStreamWrapper

# The dispatcher's turn-level retry catches exactly these; see models/__init__.
TRANSPORT_ERRORS = (openai.APIError,)

from logger_config import get_logger
logger = get_logger(__name__)

from bambooai.models import prompt_cache
from bambooai.models import resilience


def init(api_keys=None):
    """
    Initialize OpenAI client with API key precedence:
    1. Use api_keys['openai'] if available
    2. Fall back to environment variable
    """

    client_api_key = os.environ.get('OPENAI_API_KEY')
    
    if client_api_key is None:
        raise ValueError("OpenAI API key not provided in api_keys dict and OPENAI_API_KEY environment variable not set")
    
    openai_client = openai.OpenAI(api_key=client_api_key,
                                  **resilience.timeout_kwargs("openai"))
    return openai_client

def llm_call(messages: str, model: str, temperature: str, max_tokens: str, response_format: str = None, api_keys=None):  
    """
    Make a call to OpenAI's API with api_keys dictionary support
    """
    openai_client = init(api_keys)
    prompt_cache.reset()

    def get_response(model, messages, temperature, max_tokens, response_format):
        if model == 'o1-mini' or model == 'o1-preview':
            messages = [message for message in messages if message.get('role') != 'system']
            return openai_client.chat.completions.create(
                model=model,
                messages=messages,
                extra_body=prompt_cache.openai_extras(model),
            )
        else:
            return openai_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
                extra_body=prompt_cache.openai_extras(model),
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
    # OpenAI caches implicitly above ~1024 tokens; prompt_tokens already
    # includes any cached portion, so only the split needs recording.
    _r, _w, prompt_tokens = prompt_cache.from_openai_usage(response.usage)
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

def llm_stream(prompt_manager, log_and_call_manager, output_manager, chain_id: str, messages: str, model: str, temperature: str, max_tokens: str,
               tools: str = None, response_format: str = None, reasoning_models: list = None, reasoning_effort: str = "medium", api_keys=None, stop_event: threading.Event = None):  
    """
    Stream responses from OpenAI's API with complete API keys dictionary support. `tools` is the Web Search seat's:
    this adapter runs no search, and takes none.
    """
    collected_chunks = []
    collected_messages = []

    if reasoning_effort == "minimal":
        reasoning_effort = "none"
    prompt_cache.record_meta(reasoning_effort=reasoning_effort,
                             max_tokens=max_tokens)

    openai_client = init(api_keys)
    

    def get_response(model, messages, temperature, max_tokens, response_format, reasoning_models=None, reasoning_effort="low"):
        if reasoning_models and model in reasoning_models:
            output_manager.display_tool_info('Thinking', f"Reasoning Effort: {reasoning_effort}", chain_id=chain_id)
            return openai_client.chat.completions.create(
                model=model,
                messages=messages,
                reasoning_effort=reasoning_effort,
                max_completion_tokens=max_tokens,
                stream=True,
                stream_options={"include_usage": True},
                extra_body=prompt_cache.openai_extras(model),
            )
            
        else:
            return openai_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                stream_options={"include_usage": True},
                response_format=response_format,
                extra_body=prompt_cache.openai_extras(model),
            )
        
    try:
        combined_prompt_tokens_used = 0
        combined_completion_tokens_used = 0
        combined_total_tokens_used = 0

        # PRE-TOKEN STREAM RESTART (generic; see resilience.restartable).
        # OpenAI can accept the request and then drop the connection before
        # emitting anything - seen in the field on OpenRouter as "Upstream
        # error ... Connection closed", which killed a Synthesizer call fifty
        # model calls into a 1h45m run. Before the first chunk a fresh stream
        # is exactly equivalent, so the open and the pre-token window are
        # retried; a later drop stays fatal because the answer cannot be
        # resumed. Provider-SPECIFIC hardening (OpenRouter's THINKING_BUDGET,
        # effort/max_tokens exclusivity) is deliberately NOT copied here.
        raw_stream_1 = resilience.restartable(
            lambda: get_response(model, messages, temperature, max_tokens,
                                 response_format, reasoning_models,
                                 reasoning_effort),
            openai.APIError, output_manager=output_manager,
            chain_id=chain_id, label="OpenAI")

        stoppable_stream_1 = StoppableStreamWrapper(raw_stream_1, stop_event)

        start_time = time.time()
        # iterate through the stream of events
        for chunk in stoppable_stream_1:
            if chunk.choices:  # Only proceed if there are choices
                delta = chunk.choices[0].delta
                collected_chunks.append(chunk)  # save the event response

                if delta and delta.content is not None:
                    collected_messages.append(delta.content)  # save the message
                    output_manager.print_wrapper(delta.content,end="",flush=True,chain_id=chain_id)

            # If there are no choices but usage data is present, accumulate usage tokens.
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
        # body is None for timeouts and dropped connections
        error_message = e.body.get('message') if isinstance(e.body, dict) else str(e.body or e)
        output_manager.display_system_messages(f"Openai API Error: {error_message}")
        raise
    except Exception as e:
        if isinstance(e, StopIteration) and "cleanup request" in str(e):
            output_manager.display_system_messages("INFO: The process was stopped by the server.")
        else:
            output_manager.display_system_messages(f"Unexpected error: {str(e)}")
            raise
    
    output_manager.print_wrapper("",chain_id=chain_id)

    # get the complete text received
    full_reply_content = ''.join([m for m in collected_messages])
    
    if elapsed_time > 0:
        tokens_per_second = completion_tokens_used / elapsed_time
    else:
        tokens_per_second = 0

    return full_reply_content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second