import os
import threading
import time

from mistralai import Mistral

# Try to import SDKError for proper error handling
try:
    from mistralai.models.sdkerror import SDKError
except ImportError:
    # Fallback - create a dummy class that won't match anything
    class SDKError(Exception):
        pass

# Try to import Unset type for proper type checking
try:
    from mistralai.types import Unset, UNSET
except ImportError:
    try:
        from mistralai.models import Unset, UNSET
    except ImportError:
        # Fallback if Unset isn't available - we'll check by type name
        Unset = None
        UNSET = None

from bambooai.utils import StoppableStreamWrapper


def is_valid_content(content):
    """Check if content is a valid string (not None, not Unset, not empty-ish)"""
    if content is None:
        return False
    # Check for Unset type by class name (handles import issues)
    if type(content).__name__ == 'Unset':
        return False
    # Check against imported Unset if available
    if Unset is not None and isinstance(content, Unset):
        return False
    if UNSET is not None and content is UNSET:
        return False
    # Must be a string
    if not isinstance(content, str):
        return False
    return True


def init(api_keys=None):
    """
    Initialize Mistral client with API key precedence:
    1. Use api_keys['mistral'] if available
    2. Fall back to environment variable
    """
    client_api_key = None
    
    if api_keys and 'mistral' in api_keys:
        client_api_key = api_keys['mistral']
    
    if client_api_key is None:
        client_api_key = os.environ.get('MISTRAL_API_KEY')
    
    if client_api_key is None:
        raise ValueError("Mistral API key not provided in api_keys dict and MISTRAL_API_KEY environment variable not set")
    
    client = Mistral(api_key=client_api_key)
    return client


def llm_call(messages: str, model: str, temperature: str, max_tokens: str, response_format: str = None, api_keys=None):
    """
    Make a call to Mistral's API with api_keys dictionary support.
    
    Args:
        messages: List of message dictionaries
        model: Model identifier string
        temperature: Sampling temperature
        max_tokens: Maximum tokens to generate
        response_format: Optional response format specification
        api_keys: Optional dictionary containing API keys
        
    Returns:
        Tuple of (content, messages, prompt_tokens, completion_tokens, total_tokens, elapsed_time, tokens_per_second)
    """
    client = init(api_keys)

    def get_response(model, messages, temperature, max_tokens, response_format):
        return client.chat.complete(
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
    except SDKError as e:
        # Handle rate limiting with retry
        error_str = str(e).lower()
        if "rate" in error_str or "429" in error_str:
            time.sleep(10)
            start_time = time.time()
            response = get_response(model, messages, temperature, max_tokens, response_format)
            end_time = time.time()
        else:
            raise
    except Exception as e:
        # Handle other exceptions that might contain rate limit info
        error_str = str(e).lower()
        if "rate" in error_str or "429" in error_str:
            time.sleep(10)
            start_time = time.time()
            response = get_response(model, messages, temperature, max_tokens, response_format)
            end_time = time.time()
        else:
            raise

    elapsed_time = end_time - start_time

    content = response.choices[0].message.content
    # Handle Unset type and ensure content is a valid string
    if not is_valid_content(content):
        content = ""
    else:
        content = content.strip()

    # Use native usage reporting
    prompt_tokens_used = response.usage.prompt_tokens if response.usage else 0
    completion_tokens_used = response.usage.completion_tokens if response.usage else 0
    total_tokens_used = response.usage.total_tokens if response.usage else 0

    if elapsed_time > 0:
        tokens_per_second = completion_tokens_used / elapsed_time
    else:
        tokens_per_second = 0

    return content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second


def llm_stream(prompt_manager, log_and_call_manager, output_manager, chain_id: str, messages: str, model: str, temperature: str, max_tokens: str,
               tools: str = None, response_format: str = None, reasoning_models: list = None, reasoning_effort: str = "medium", api_keys=None, stop_event: threading.Event = None):
    """
    Stream responses from Mistral's API with complete API keys dictionary support.
    
    Supports:
    - Native usage token tracking
    - StoppableStreamWrapper for cancellation
    - Reasoning models with prompt_mode
    
    Args:
        prompt_manager: Prompt manager instance
        log_and_call_manager: Log and call manager instance
        output_manager: Output manager for displaying content
        chain_id: Chain identifier for output routing
        messages: List of message dictionaries
        model: Model identifier string
        temperature: Sampling temperature
        max_tokens: Maximum tokens to generate
        tools: the Web Search seat's; this adapter runs no search, and takes none
        response_format: Optional response format specification
        reasoning_models: List of model names that support reasoning mode
        reasoning_effort: Reasoning effort level (note: Mistral uses prompt_mode instead)
        api_keys: Optional dictionary containing API keys
        stop_event: Optional threading.Event for stopping the stream
        
    Returns:
        Tuple of (content, messages, prompt_tokens, completion_tokens, total_tokens, elapsed_time, tokens_per_second)
    """
    collected_chunks = []
    collected_messages = []

    client = init(api_keys)


    def get_response(model, messages, temperature, max_tokens, response_format, reasoning_models=None, reasoning_effort="medium"):
        """Get streaming response from Mistral API"""
        # Check if this is a reasoning model - Mistral uses prompt_mode instead of reasoning_effort
        if reasoning_models and model in reasoning_models:
            output_manager.display_tool_info('Thinking', f"Reasoning Mode: enabled", chain_id=chain_id)
            return client.chat.stream(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                prompt_mode="reasoning",
            )
        else:
            return client.chat.stream(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                response_format=response_format,
            )

    def process_stream_chunk(event, collected_chunks, collected_messages):
        """Process a single stream chunk and extract its content"""
        # Mistral streaming returns events with a 'data' attribute containing the chunk
        chunk = event.data if hasattr(event, 'data') else event
        
        usage_data = {"prompt": 0, "completion": 0, "total": 0}
        
        if chunk.choices:  # Only proceed if there are choices
            choice = chunk.choices[0]
            delta = choice.delta
            collected_chunks.append(chunk)

            # Check for content - use is_valid_content to handle Unset type
            if delta and is_valid_content(delta.content):
                collected_messages.append(delta.content)
                output_manager.print_wrapper(delta.content, end="", flush=True, chain_id=chain_id)

        # Check for usage data in the chunk (typically comes at the end)
        if hasattr(chunk, 'usage') and chunk.usage:
            if hasattr(chunk.usage, 'prompt_tokens') and chunk.usage.prompt_tokens:
                usage_data["prompt"] = chunk.usage.prompt_tokens
            if hasattr(chunk.usage, 'completion_tokens') and chunk.usage.completion_tokens:
                usage_data["completion"] = chunk.usage.completion_tokens
            if hasattr(chunk.usage, 'total_tokens') and chunk.usage.total_tokens:
                usage_data["total"] = chunk.usage.total_tokens
                
        return usage_data

    try:
        combined_prompt_tokens_used = 0
        combined_completion_tokens_used = 0
        combined_total_tokens_used = 0

        # Get the first raw stream
        raw_stream_1 = get_response(model, messages, temperature, max_tokens, response_format, reasoning_models, reasoning_effort)

        # Wrap with StoppableStreamWrapper if stop_event is provided
        if stop_event:
            stoppable_stream_1 = StoppableStreamWrapper(raw_stream_1, stop_event)
        else:
            stoppable_stream_1 = raw_stream_1

        start_time = time.time()

        # Iterate through the stream of events
        for event in stoppable_stream_1:
            usage_data = process_stream_chunk(event, collected_chunks, collected_messages)
            if usage_data["prompt"] > 0:
                combined_prompt_tokens_used = usage_data["prompt"]
            if usage_data["completion"] > 0:
                combined_completion_tokens_used = usage_data["completion"]
            if usage_data["total"] > 0:
                combined_total_tokens_used = usage_data["total"]

        end_time = time.time()
        elapsed_time = end_time - start_time

        prompt_tokens_used = combined_prompt_tokens_used
        completion_tokens_used = combined_completion_tokens_used
        total_tokens_used = combined_total_tokens_used

    except SDKError as e:
        error_str = str(e)
        if "rate" in error_str.lower() or "429" in error_str:
            output_manager.display_system_messages(f"Mistral API Rate Limit Error: {error_str}")
        else:
            output_manager.display_system_messages(f"Mistral SDK Error: {error_str}")
        raise
    except Exception as e:
        error_str = str(e)
        if isinstance(e, StopIteration) and "cleanup request" in error_str:
            output_manager.display_system_messages("INFO: The process was stopped by the server.")
        elif "rate" in error_str.lower() or "429" in error_str:
            output_manager.display_system_messages(f"Mistral API Rate Limit Error: {error_str}")
            raise
        else:
            output_manager.display_system_messages(f"Mistral API Error: {error_str}")
            raise

    output_manager.print_wrapper("", chain_id=chain_id)

    # Get the complete text received - filter to ensure only strings are joined
    full_reply_content = ''.join([m for m in collected_messages if isinstance(m, str)])

    if elapsed_time > 0:
        tokens_per_second = completion_tokens_used / elapsed_time
    else:
        tokens_per_second = 0

    return full_reply_content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second