import os
import threading
import time
from groq import Groq
import tiktoken

from bambooai.utils import StoppableStreamWrapper

from logger_config import get_logger
logger = get_logger(__name__)

def init(api_keys=None):
    """
    Initialize Groq client with API key precedence:
    1. Use api_keys['groq'] if available
    2. Fall back to environment variable
    """

    client_api_key = os.environ.get('GROQ_API_KEY')
    
    if client_api_key is None:
        raise ValueError("Groq API key not provided in api_keys dict and GROQ_API_KEY environment variable not set")
    
    client = Groq(api_key=client_api_key)
    return client

def llm_call(messages: str, model: str, temperature: str, max_tokens: str, response_format: str = None, api_keys=None):  
    """
    Make a call to Groq's API with api_keys dictionary support
    """
    client = init(api_keys)

    start_time = time.time()

    response = client.chat.completions.create(
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

def llm_stream(prompt_manager, log_and_call_manager, output_manager, chain_id: str, messages: str, model: str, 
               temperature: str, max_tokens: str, tools: str = None, response_format: str = None, 
               reasoning_models: list = None, reasoning_effort: str = "medium", api_keys=None, 
               stop_event: threading.Event = None):  
    """
    Stream responses from Groq's API, with reasoning support for GPT-OSS models. `tools` is the Web Search seat's:
    this adapter runs no search, and takes none.
    """
    collected_chunks = []
    collected_messages = []

    client = init(api_keys)
    
    # openai os models do not yet support "minimal" reasoning effort, so we map it to "low"
    if reasoning_effort == "minimal":
        reasoning_effort = "low"
    

    def get_response(model, messages, temperature, max_tokens, response_format):
        """Helper function to create a streaming response from Groq"""
        params = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
            "stream": True,
        }
        
        # Add stream_options via extra_body to get usage information
        params["extra_body"] = {"stream_options": {"include_usage": True}}
        
            
        # Add reasoning parameters for GPT-OSS models
        if reasoning_models and model in reasoning_models:
            output_manager.display_tool_info('Thinking', f"Reasoning Effort: {reasoning_effort}", chain_id=chain_id)
            # For GPT-OSS models, include_reasoning is used (not reasoning_format)
            params["include_reasoning"] = True
            params["reasoning_effort"] = reasoning_effort
        
        return client.chat.completions.create(**params)
    
    try:
        start_time = time.time()
        
        # Initialize token counters
        prompt_tokens_used = 0
        completion_tokens_used = 0
        total_tokens_used = 0
        
        raw_stream = get_response(model, messages, temperature, max_tokens, response_format)
        stoppable_stream = StoppableStreamWrapper(raw_stream, stop_event)
        reasoning_complete = []  # Collect all reasoning text
            
        # Process the current stream
        for chunk in stoppable_stream:
            collected_chunks.append(chunk)
                
            if chunk.choices and len(chunk.choices) > 0:
                delta = chunk.choices[0].delta
                    
                # Handle reasoning content for GPT-OSS models
                if hasattr(delta, 'reasoning') and delta.reasoning is not None:
                    reasoning_text = delta.reasoning
                        
                    # Collect all reasoning text
                    reasoning_complete.append(reasoning_text)
                    
                # Handle regular content
                if delta and delta.content is not None:
                    chunk_message = delta.content
                    collected_messages.append(chunk_message)
                    output_manager.print_wrapper(chunk_message, end='', flush=True, chain_id=chain_id)

            # Check for usage data in the chunk
            if hasattr(chunk, 'usage') and chunk.usage is not None:
                if chunk.usage.prompt_tokens is not None:
                    prompt_tokens_used = chunk.usage.prompt_tokens
                if chunk.usage.completion_tokens is not None:
                    completion_tokens_used = chunk.usage.completion_tokens
                if chunk.usage.total_tokens is not None:
                    total_tokens_used = chunk.usage.total_tokens
            
        # Output complete reasoning at once if any was collected
        if reasoning_complete:
            full_reasoning = ''.join(reasoning_complete)
            if full_reasoning:
                output_manager.print_wrapper(full_reasoning, end='', flush=True, chain_id=chain_id, thought=True)

        end_time = time.time()
        elapsed_time = end_time - start_time
        
        output_manager.print_wrapper("", chain_id=chain_id)
        
        # Get the complete text received
        full_reply_content = ''.join([m for m in collected_messages])
        
        # Calculate total tokens if not provided by the API
        if total_tokens_used == 0:
            # Fallback to tiktoken estimation
            encoding = tiktoken.encoding_for_model("gpt-4")
            tokens_per_message = 3
            
            for message in messages:
                prompt_tokens_used += tokens_per_message
                for key, value in message.items():
                    if isinstance(value, str):
                        prompt_tokens_used += len(encoding.encode(value))
            
            completion_tokens_used = len(encoding.encode(full_reply_content))
            total_tokens_used = prompt_tokens_used + completion_tokens_used
        
        if elapsed_time > 0:
            tokens_per_second = completion_tokens_used / elapsed_time
        else:
            tokens_per_second = 0
        
    except Exception as e:
        if isinstance(e, StopIteration) and "cleanup request" in str(e):
            output_manager.display_system_messages("INFO: The process was stopped by the server.")
            # Return partial results
            full_reply_content = ''.join([m for m in collected_messages])
            elapsed_time = time.time() - start_time
            total_tokens_used = prompt_tokens_used + completion_tokens_used
            tokens_per_second = completion_tokens_used / elapsed_time if elapsed_time > 0 else 0
        else:
            output_manager.display_system_messages(f"Groq API Error: {str(e)}")
            raise
    
    return full_reply_content, messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second