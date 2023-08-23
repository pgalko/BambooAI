
import re
import logging
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

def convert_openai_to_wizard(messages: str):
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

def llm_local_stream(messages: str,local_model: str):   
    total_tokens_used=0

    try:
        from torch import cuda,bfloat16,float16
    except ImportError:
        raise ImportError("The torch package is required for using local models. Please install it using pip install torch.")
    
    if local_model == 'WizardCoder-15B-V1.0':
        model_name = "WizardLM/WizardCoder-15B-V1.0"
        messages = convert_openai_to_wizard(messages)
    elif local_model == 'WizardCoder-15B-1.0-GPTQ':
        try:
            from auto_gptq import AutoGPTQForCausalLM, BaseQuantizeConfig
        except ImportError:
            raise ImportError("The auto_gptq package is required for using WizardCoder-15B-1.0-GPTQ. Please install it using pip install auto-gptq")
        model_name = "TheBloke/WizardCoder-15B-1.0-GPTQ"
        messages = convert_openai_to_wizard(messages)
    else:
        raise ValueError('Currently the only supported local_models are WizardCoder-15B-V1.0 and WizardCoder-15B-1.0-GPTQ')

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

    if local_model == 'WizardCoder-15B-V1.0':
        # If the GPU has more than 80GB of memory, use float16
        if cuda.is_available() and gpu_memory_gb >= 80:
            model_config = {
                "torch_dtype": float16,
            }
            print(f"Using {model_config['torch_dtype']} precision")
        else:
            model_config = {
                "quantization_config": bnb_config,
            }
            print(f"Uing {model_config['quantization_config'].bnb_4bit_quant_type} quantization")
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            trust_remote_code=True,
            device_map='auto',
            **model_config,
        )

    elif local_model == 'WizardCoder-15B-1.0-GPTQ':
        model = AutoGPTQForCausalLM.from_quantized(
            model_name,
            use_safetensors=True,
            device=device,
            use_triton=False,
            quantize_config=None
        )

    model.eval()
    print(f"Model loaded on {device}")
    print(f"GPU memory available: {gpu_memory_gb}GB\n")

    tokenizer = AutoTokenizer.from_pretrained(model_name, use_fast=True)

    streamer = TextStreamer(tokenizer,skip_prompt=True)

    pipe = pipeline(task="text-generation", model=model, tokenizer=tokenizer)
    result = pipe(messages, 
                    do_sample=True,
                    top_k=5,
                    num_return_sequences=1,
                    eos_token_id=tokenizer.eos_token_id,
                    max_length=2048,
                    repetition_penalty=1.1,
                    streamer=streamer,
                    return_full_text=False,
                )

    result = result[0]['generated_text'] 

    return result,total_tokens_used
