import importlib
import os
import time
import json


def load_llm_config():

    default_llm_config = [
    {"agent": "Expert Selector", "details": {"model": "gpt-4o", "provider":"openai","max_tokens": 4000, "temperature": 0}},
    {"agent": "Analyst Selector", "details": {"model": "gpt-4o", "provider":"openai","max_tokens": 4000, "temperature": 0}},
    {"agent": "Theorist", "details": {"model": "gpt-4o", "provider":"openai","max_tokens": 4000, "temperature": 0}},
    {"agent": "Planner", "details": {"model": "gpt-4o", "provider":"openai","max_tokens": 4000, "temperature": 0}},
    {"agent": "Code Generator", "details": {"model": "gpt-4o", "provider":"openai","max_tokens": 4000, "temperature": 0}},
    {"agent": "Code Debugger", "details": {"model": "gpt-4o", "provider":"openai","max_tokens": 4000, "temperature": 0}},
    {"agent": "Error Corrector", "details": {"model": "gpt-4o", "provider":"openai","max_tokens": 4000, "temperature": 0}},
    {"agent": "Code Ranker", "details": {"model": "gpt-4o", "provider":"openai","max_tokens": 4000, "temperature": 0}},
    {"agent": "Solution Summarizer", "details": {"model": "gpt-4o", "provider":"openai","max_tokens": 4000, "temperature": 0}},
    {"agent": "Google Search Query Generator", "details": {"model": "gpt-4o", "provider":"openai","max_tokens": 4000, "temperature": 0}},
    {"agent": "Google Search Summarizer", "details": {"model": "gpt-4o", "provider":"openai","max_tokens": 4000, "temperature": 0}}
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

    return model, provider, max_tokens, temperature

def get_model_name(agent):
    
    llm_config = load_llm_config()

    for item in llm_config:
        if item['agent'] == agent:
            details = item.get('details', {})
            model = details.get('model', 'Unknown')
            provider = details.get('provider', 'Unknown')

    return model, provider

def try_import(module_name):
    try:
        # Attempt package-relative import
        module = importlib.import_module(f'.{module_name}','bambooai')
    except ImportError:
        # Fall back to script-style import
        module = importlib.import_module(module_name)
    return module

def llm_call(log_and_call_manager, messages: str, agent: str = None, chain_id: str = None):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())
    model, provider, max_tokens, temperature = init(agent)

    # Map providers to their respective function names ('llm_stream' for local, 'llm_call' for others)
    provider_function_map = {
        'local': 'llm_stream',
        'groq': 'llm_call',
        'openai': 'llm_call',
        'ollama': 'llm_call',
        'gemini': 'llm_call',
        'anthropic': 'llm_call',
        'mistral': 'llm_call'
    }

    if provider in provider_function_map:
        # Try to import the correct module
        provider_module = try_import(f'{provider}_models')

        # Call the appropriate function from the imported module
        function_name = provider_function_map[provider]
        content_received, local_llm_messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second = getattr(provider_module, function_name)(messages, model, temperature, max_tokens)
        
        # Log the results
        log_and_call_manager.write_to_log(agent, chain_id, timestamp, model, local_llm_messages, content_received, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second)
        
        return content_received
    else:
        raise ValueError(f"Unsupported provider: {provider}")

def llm_stream(log_and_call_manager, messages: str, agent: str = None, chain_id: str = None, tools:str = None):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime())

    # Initialize the LLM parameters
    model, provider, max_tokens, temperature = init(agent)

    # Map providers to their respective function names
    provider_function_map = {
        'local': 'llm_stream',
        'groq': 'llm_stream',
        'openai': 'llm_stream',
        'ollama': 'llm_stream',
        'gemini': 'llm_stream',
        'anthropic': 'llm_stream',
        'mistral': 'llm_stream'
    }

    if provider in provider_function_map:
        # Try to import the correct module
        provider_module = try_import(f'{provider}_models')

        # Call the appropriate function from the imported module
        function_name = provider_function_map[provider]
        content_received, local_llm_messages, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second = getattr(provider_module, function_name)(log_and_call_manager, chain_id, messages, model, temperature, max_tokens, tools)
        
        # Log the results
        log_and_call_manager.write_to_log(agent, chain_id, timestamp, model, local_llm_messages, content_received, prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second)
        
        return content_received
    else:
        raise ValueError(f"Unsupported provider: {provider}")

        