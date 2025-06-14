import os
import time
from google import genai
from google.genai import types
import copy
import json
import base64

def init():
    API_KEY = os.environ.get('GEMINI_API_KEY')
    
    client = genai.Client(
        api_key=API_KEY,
        )
    return client

def convert_openai_to_gemini(messages):
    updated_data = []
    system_content = None
    
    # Create deep copies of messages
    messages_copy = copy.deepcopy(messages)
    
    for item in messages_copy:
        if item['role'] == 'system':
            system_content = item['content']
            continue 
        if item['role'] == 'assistant':
            item['role'] = 'model'
            
        try:
            content = item.pop('content')
            parts = []
            
            if isinstance(content, str):
                # Handle text-only content
                parts.append(types.Part(text=content.strip()))
            elif isinstance(content, list):
                # Handle multimodal content (text + image)
                for part in content:
                    if part['type'] == 'text':
                        parts.append(types.Part(text=part['text'].strip()))
                    elif part['type'] == 'image_base64':
                        # Create a Blob for inline_data
                        image_bytes = base64.b64decode(part['data'])
                        parts.append(types.Part(
                            inline_data=types.Blob(
                                data=image_bytes,
                                mime_type=part['mime_type']
                            )
                        ))
            
            if parts:
                # Create Content object directly with proper structure
                message = types.Content(
                    role=item['role'],
                    parts=parts
                )
                updated_data.append(message)
                
        except KeyError:
            pass

    return updated_data, system_content

def llm_call(messages: str, model_name: str, temperature: str, max_tokens: str, response_format: str = None):  
    client = init()

    gemini_messages, system_instruction = convert_openai_to_gemini(messages)

    # Create base config parameters
    config_params = {
        'http_options': types.HttpOptions(api_version='v1alpha'),
        'temperature': temperature,
        'max_output_tokens': max_tokens,
        'system_instruction': system_instruction
    }

    # Count prompt tokens before the call
    prompt_tokens = client.models.count_tokens(
        model=model_name,
        contents=gemini_messages
    ).total_tokens

    start_time = time.time()

    # Create config object and make the call
    response = client.models.generate_content(
        model=model_name,
        contents=gemini_messages,
        config=types.GenerateContentConfig(**config_params)
    )

    end_time = time.time()
    elapsed_time = end_time - start_time

    content = response.text

    # Count response tokens
    completion_tokens = client.models.count_tokens(
        model=model_name,
        contents=[types.ContentDict(
            role="model",
            parts=[types.PartDict(text=content)]
        )]
    ).total_tokens

    # Calculate total tokens
    total_tokens_used = prompt_tokens + completion_tokens

    if elapsed_time > 0:
        tokens_per_second = completion_tokens / elapsed_time
    else:
        tokens_per_second = 0

    return content, messages, prompt_tokens, completion_tokens, total_tokens_used, elapsed_time, tokens_per_second

def llm_stream(prompt_manager, log_and_call_manager, output_manager, chain_id: str, messages: str, model_name: str, temperature: str, max_tokens: str, tools: str = None, response_format: str = None, reasoning_models: list = None, reasoning_effort: str = None):
    answer_messages = []
    thinking_messages = []
    search_triplet = []
    search_html = None

    client = init()
    
    # Set thinking budget based on reasoning effort. Default to minimal if not specified. As of 06/06 "none" only works for Flash.
    thinking_budget = {"high": 8000, "medium": 4000, "low": 2000, "minimal": 128, "none": 0}.get(reasoning_effort, 128)

    gemini_messages, system_instruction = convert_openai_to_gemini(messages)

    # Create google search tool
    google_search_tool = types.Tool(
        google_search=types.GoogleSearch()
    )

    # Create base config parameters
    config_params = {
        'http_options': types.HttpOptions(api_version='v1alpha'),
        'temperature': temperature,
        'max_output_tokens': max_tokens,
        'system_instruction': system_instruction
    }

    if reasoning_models and model_name in reasoning_models:
        config_params['thinking_config'] = types.ThinkingConfig(include_thoughts=True, thinking_budget=thinking_budget)
        output_manager.display_tool_info('Thinking', f"Thinking budget: {thinking_budget} tokens", chain_id=chain_id)

    if tools:
        for tool in tools:
            if tool['name'] == 'google_search':
                config_params['tools'] = [google_search_tool]
                break

    prompt_tokens = client.models.count_tokens(
        model=model_name,
        contents=gemini_messages
    ).total_tokens

    response = client.models.generate_content_stream(
        model=model_name,
        contents=gemini_messages,
        config=types.GenerateContentConfig(**config_params)
    )

    try:
        start_time = time.time()
        
        for chunk in response:
            if not chunk.candidates:
                continue
            
            candidate = chunk.candidates[0]
            
            # Check if content exists and is not None
            if not hasattr(candidate, 'content') or candidate.content is None:
                continue
            
            # Check if parts exists and is not None
            if not hasattr(candidate.content, 'parts') or candidate.content.parts is None:
                continue
            
            for part in candidate.content.parts:
                # Check if part has the expected attributes
                if not hasattr(part, 'text') and not hasattr(part, 'thought'):
                    continue
                    
                # Check if either text or thought has content
                has_text = hasattr(part, 'text') and part.text
                has_thought = hasattr(part, 'thought') and part.thought is not None
                
                if has_text or has_thought:
                    if has_thought:
                        thinking_messages.append(part.text)
                        output_manager.print_wrapper(part.text, end='', flush=True, chain_id=chain_id, thought=True)
                    elif has_text:
                        answer_messages.append(part.text)
                        output_manager.print_wrapper(part.text, end='', flush=True, chain_id=chain_id)

            # Capture grounding metadata if present
            if hasattr(chunk.candidates[0], 'grounding_metadata') and chunk.candidates[0].grounding_metadata:
                metadata = chunk.candidates[0].grounding_metadata
                
                links = []
                if metadata.grounding_chunks is not None:
                    links = [
                        {"title": gc.web.title, "link": gc.web.uri}
                        for gc in metadata.grounding_chunks if hasattr(gc, 'web') and gc.web
                    ]
                
                queries = None
                if hasattr(metadata, 'web_search_queries') and metadata.web_search_queries is not None:
                    queries = metadata.web_search_queries
                
                # Check if search_entry_point exists and is not None before accessing rendered_content
                if hasattr(metadata, 'search_entry_point') and metadata.search_entry_point is not None and hasattr(metadata.search_entry_point, 'rendered_content'):
                    search_html = metadata.search_entry_point.rendered_content
                
                # Only process if we have both grounding_supports AND queries
                if (hasattr(metadata, 'grounding_supports') and metadata.grounding_supports and 
                    queries is not None):
                    
                    supports = metadata.grounding_supports
                    supports_per_query = max(1, len(supports) // len(queries))
                    
                    for i, q in enumerate(queries):
                        start_idx = i * supports_per_query
                        end_idx = min((i + 1) * supports_per_query, len(supports))
                        relevant_supports = supports[start_idx:end_idx]
                        
                        result_text = " ".join(support.segment.text for support in relevant_supports)
                        relevant_link_indices = set()
                        for support in relevant_supports:
                            relevant_link_indices.update(support.grounding_chunk_indices)
                        
                        search_triplet.append({
                            "query": q,
                            "result": result_text.strip(),
                            "links": [links[idx] for idx in relevant_link_indices if idx < len(links)]
                        })

        end_time = time.time()
        elapsed_time = end_time - start_time

    except Exception as e:
        output_manager.display_system_messages(f"Gemini API Error: {e}")
        raise

    output_manager.print_wrapper("", chain_id=chain_id)

    answer_content = ''.join([m for m in answer_messages])
    thinking_content = ''.join([m for m in thinking_messages])

    # Output the search_entry_point HTML as a JSON structure
    if search_html:
        output_manager.send_html_content(search_html, chain_id=chain_id)

    completion_tokens = client.models.count_tokens(
        model=model_name,
        contents=[types.ContentDict(
            role="model",
            parts=[types.PartDict(text=answer_content + thinking_content)]
        )]
    ).total_tokens

    total_tokens_used = prompt_tokens + completion_tokens
    
    if elapsed_time > 0:
        tokens_per_second = completion_tokens / elapsed_time
    else:
        tokens_per_second = 0
    
    if tools:
        return answer_content, search_triplet, messages, prompt_tokens, completion_tokens, total_tokens_used, elapsed_time, tokens_per_second
    else:
        return answer_content, messages, prompt_tokens, completion_tokens, total_tokens_used, elapsed_time, tokens_per_second