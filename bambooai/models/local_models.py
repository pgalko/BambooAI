
import re
import logging
import time
logging.basicConfig(level='CRITICAL')
from transformers import (
    AutoModelForCausalLM,
    BitsAndBytesConfig,
    AutoTokenizer,
    pipeline,
    TextStreamer,
    logging,
)

logging.set_verbosity(logging.CRITICAL)

def convert_openai_to_alpaca(messages: str):
    formatted_content = ""
    last_role = None

    for i, item in enumerate(messages):
        role = item['role']
        content = item['content']

        if role == 'system':
            formatted_content += content + "\n"
        elif role == 'user':
            formatted_content += "### Instruction: " + content + "\n"
        elif role == 'assistant':
            formatted_content += "### Response: " + content + "\n"
        last_role = role
    
    # Remove the example output. 
    # It seems to get confused when the code is present in the instruction and tries to interpret rather than generate a new code.
    formatted_content = re.sub(r'Example Output:.*', '', formatted_content, flags=re.S)

    # If the last role was 'user', add an empty response
    if last_role == 'user':
        formatted_content += "### Response:\n"

    return formatted_content

def convert_openai_to_llama2_chat(messages: list):
    formatted_content = ""
    in_inst = False
    
    for i, item in enumerate(messages):
        role = item['role']
        content = item['content']
        
        if role == 'system':
            formatted_content += "<s>[INST]" + "<<SYS>>" + content + "<</SYS>>\n\n"
            in_inst = True
        elif role == 'user':
            if not in_inst:
                formatted_content += "<s>[INST]"
            formatted_content += content
            formatted_content += "[/INST]"
            in_inst = False
        elif role == 'assistant':
            formatted_content += content
            if in_inst:
                formatted_content += " "

    # Remove content starting with "Example Output:" and ending at the next "[/INST]"
    #formatted_content = re.sub(r'Example Output:.*?\[/INST\]', '[/INST]', formatted_content, flags=re.S)
    return formatted_content.strip()

def convert_openai_to_llama2_completion(messages: list):
    formatted_content = None
    for message in reversed(messages):
        if message['role'] == 'user':
            formatted_content = message['content']
            break
    # Remove content starting with "Example Output:" "
    #formatted_content = re.sub(r'Example Output:.*', '', formatted_content, flags=re.S)
    return formatted_content

def llm_stream(prompt_manager, log_and_call_manager, output_manager, chain_id: str, messages: str, local_model: str, temperature: str, max_tokens: str, tools: str=None, response_format: str = None, reasoning_models: list = None, reasoning_effort:str = "medium"):
    # (log_and_call_manager, output_manager, chain_id, messages, model, temperature, max_tokens, tools   
    total_tokens_used=0

    wizard_coder_models=['WizardCoder-15B-V1.0','WizardCoder-Python-7B-V1.0','WizardCoder-Python-13B-V1.0','WizardCoder-Python-34B-V1.0']
    phind_models=['Phind-CodeLlama-34B-v2']
    open_code_interpreter_models=['OpenCodeInterpreter-DS-33B']
    wizard_coder_gptq_models=['WizardCoder-15B-1.0-GPTQ','WizardCoder-Python-7B-V1.0-GPTQ','WizardCoder-Python-13B-V1.0-GPTQ','WizardCoder-Python-34B-V1.0-GPTQ']
    code_llama_instruct_models=['CodeLlama-7B-Instruct-fp16','CodeLlama-13B-Instruct-fp16','CodeLlama-34B-Instruct-fp16']
    code_llama_completion_models=['CodeLlama-7B-Python-fp16','CodeLlama-13B-Python-fp16','CodeLlama-34B-Python-fp16']
    all_models = wizard_coder_models + wizard_coder_gptq_models + code_llama_instruct_models + code_llama_completion_models + phind_models + open_code_interpreter_models

    try:
        from torch import cuda,bfloat16,float16
    except ImportError:
        raise ImportError("The torch package is required for using local models. Please install it using pip install torch.")
    
    if cuda.is_available():
        gpu_memory_gb = cuda.get_device_properties(0).total_memory / 1e9 if cuda.is_available() else 0  # In GB
        device = f'cuda:{cuda.current_device()}'
    else:
        gpu_memory_gb = 0
        device = 'cpu'

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type='nf4',
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=bfloat16
    )
    
    if local_model in wizard_coder_models:
        model_name = f"WizardLM/{local_model}"
        messages = convert_openai_to_alpaca(messages)
    elif local_model in wizard_coder_gptq_models:
        try:
            from auto_gptq import AutoGPTQForCausalLM, BaseQuantizeConfig
        except ImportError:
            raise ImportError("The auto_gptq package is required for using WizardCoder-GPTQ. Please install it using pip install auto-gptq")
        model_name = f"TheBloke/{local_model}"
        messages = convert_openai_to_alpaca(messages)
    elif local_model in phind_models:
        model_name = f"Phind/{local_model}"
        messages = convert_openai_to_alpaca(messages)
    elif local_model in code_llama_instruct_models:
        model_name = f"TheBloke/{local_model}"
        messages = convert_openai_to_llama2_chat(messages)
    elif local_model in code_llama_completion_models:
        model_name = f"TheBloke/{local_model}"
        messages = convert_openai_to_llama2_completion(messages)
    elif local_model in open_code_interpreter_models:
        model_name = f"m-a-p/{local_model}"
        messages = messages
    elif local_model.startswith('ollama'):
        slash_index = local_model.index('/')
        model_name = local_model[slash_index + 1:]
        messages = messages
    else:
        all_models_str = ', '.join(all_models)
        error_message = f"Currently the only supported local_models are: {all_models_str}"
        raise ValueError(error_message)

    if local_model in wizard_coder_models or local_model in code_llama_instruct_models or local_model in code_llama_completion_models or local_model in phind_models or local_model in open_code_interpreter_models:
        # If the GPU has more than 80GB of memory, use float16
        if cuda.is_available() and gpu_memory_gb >= 80:
            model_config = {
                "torch_dtype": float16,
            }
            output_manager.display_system_messages(f"Using {model_config['torch_dtype']} precision")
        else:
            model_config = {
                "quantization_config": bnb_config,
            }
            output_manager.display_system_messages(f"Using {model_config['quantization_config'].bnb_4bit_quant_type} quantization")
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            trust_remote_code=True,
            device_map='auto',
            **model_config,
        )

    elif local_model in wizard_coder_gptq_models:
        model = AutoGPTQForCausalLM.from_quantized(
            model_name,
            use_safetensors=True,
            device=device,
            use_triton=False,
            quantize_config=None
        )
    
    model.eval()
    output_manager.display_system_messages(f"Model loaded on {device}")
    output_manager.display_system_messages(f"GPU memory available: {gpu_memory_gb}GB\n")

    start_time = time.time()

    tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)

    streamer = TextStreamer(tokenizer,skip_prompt=True, skip_special_tokens=True)

    pipe = pipeline(task="text-generation", model=model, tokenizer=tokenizer)

    result = pipe(messages, 
                    do_sample=True,
                    top_k=1,
                    num_return_sequences=1,
                    eos_token_id=tokenizer.eos_token_id,
                    max_length=16000,
                    repetition_penalty=1.1,
                    streamer=streamer,
                    return_full_text=False,
                )

    result = result[0]['generated_text']

    end_time = time.time()
    elapsed_time = end_time - start_time

    # Calcutale tokens usage
    completion_tokens_used = len(tokenizer.encode(result))
    prompt_tokens_used = len(tokenizer.encode(messages))
    total_tokens_used = completion_tokens_used + prompt_tokens_used
    
    tokens_per_second = completion_tokens_used / elapsed_time

    return result,messages,prompt_tokens_used, completion_tokens_used, total_tokens_used, elapsed_time, tokens_per_second

