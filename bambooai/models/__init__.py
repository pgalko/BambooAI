import importlib
import os
import time
import json
import sys


def load_llm_config():
    """
    Load LLM configuration from JSON file.
    Raises an error if configuration can't be loaded.
    """
    # Check if configuration file exists
    if os.path.exists("LLM_CONFIG.json"):
        try:
            with open("LLM_CONFIG.json", 'r') as f:
                config_data = json.load(f)
                return config_data
        except Exception as e:
            raise ValueError(f"Error reading LLM_CONFIG.json file: {e}")
    
    # No configuration found
    sys.exit("Error: LLM_CONFIG.json not found. Please provide model configuration.")

def get_model_properties():
    """Get the model properties dictionary from config"""
    config = load_llm_config()
    return config.get("model_properties", {})

def init(agent):
    """Initialize configuration for a specific agent"""
    config = load_llm_config()
    agent_configs = config.get("agent_configs", [])
    
    # Default values
    model = None
    provider = None
    max_tokens = 4000
    temperature = 0
    response_format = None
    
    # Search for the agent in the config
    for item in agent_configs:
        if item.get('agent') == agent:
            details = item.get('details', {})
            model = details.get('model')
            provider = details.get('provider')
            max_tokens = details.get('max_tokens', max_tokens)
            temperature = details.get('temperature', temperature)
            
            # Check if provider is 'openai' and response_format is set
            if provider == 'openai' and 'response_format' in details:
                response_format = details.get('response_format')
            break
    
    if not model or not provider:
        raise ValueError(f"Agent '{agent}' not found in configuration or has incomplete details")
    
    return model, provider, max_tokens, temperature, response_format


def get_model_name(agent):
    """Get model name and provider for a specific agent"""
    config = load_llm_config()
    agent_configs = config.get("agent_configs", [])
    
    model = None
    provider = None
    
    # Search for the agent in the config
    for item in agent_configs:
        if item.get('agent') == agent:
            details = item.get('details', {})
            model = details.get('model')
            provider = details.get('provider')
            break
    
    if not model or not provider:
        raise ValueError(f"Agent '{agent}' not found in configuration or has incomplete details")
    
    return model, provider

# Import models module based on provider
def try_import(module_name):
    module = importlib.import_module(__package__ + '.' + module_name)
    return module

def llm_call(log_and_call_manager, messages: str, agent: str = None, chain_id: str = None):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    model, provider, max_tokens, temperature, response_format = init(agent)

    # Map providers to their respective function names ('llm_stream' for local, 'llm_call' for others)
    provider_function_map = {
        'local': 'llm_stream',
        'groq': 'llm_call',
        'openai': 'llm_call',
        'ollama': 'llm_call',
        'vllm': 'llm_call',
        'gemini': 'llm_call',
        'anthropic': 'llm_call',
        'mistral': 'llm_call',
        'openrouter': 'llm_call',
        "deepseek": 'llm_call'
    }

    if provider in provider_function_map:
        # Try to import the correct module
        provider_module = try_import(f'{provider}_models')

        # Call the appropriate function from the imported module
        function_name = provider_function_map[provider]
        content_received, local_llm_messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second = getattr(provider_module, function_name)(messages, model, temperature, max_tokens, response_format)
        
        # Log the results
        log_and_call_manager.write_to_log(agent, chain_id, timestamp, model, local_llm_messages, content_received, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second)
        
        return content_received
    else:
        raise ValueError(f"Unsupported provider: {provider}")

def llm_stream(prompt_manager, log_and_call_manager, output_manager, messages: str, agent: str = None, chain_id: str = None, tools:str = None, reasoning_models:list = None, reasoning_effort:str = "medium"):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())

    # Initialize the LLM parameters
    model, provider, max_tokens, temperature, response_format = init(agent)

    # Map providers to their respective function names
    provider_function_map = {
        'local': 'llm_stream',
        'groq': 'llm_stream',
        'openai': 'llm_stream',
        'ollama': 'llm_stream',
        'vllm': 'llm_stream',
        'gemini': 'llm_stream',
        'anthropic': 'llm_stream',
        'mistral': 'llm_stream',
        'openrouter': 'llm_stream',
        "deepseek": 'llm_stream'
    }

    if provider in provider_function_map:
        # Try to import the correct module
        provider_module = try_import(f'{provider}_models')

        # Call the appropriate function from the imported module
        function_name = provider_function_map[provider]
        result = getattr(provider_module, function_name)(prompt_manager, log_and_call_manager, output_manager, chain_id, messages, model, temperature, max_tokens, tools, response_format, reasoning_models, reasoning_effort)
        
        # Unpack the result
        if tools:
            content_received, tool_response, local_llm_messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second = result
        else:
            content_received, local_llm_messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second = result
            tool_response = []

        # Log the results
        log_and_call_manager.write_to_log(agent, chain_id, timestamp, model, local_llm_messages, content_received, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second)
        
        if tools:
            return content_received, tool_response
        else:
            return content_received
    else:
        raise ValueError(f"Unsupported provider: {provider}")

        