import json
from json import JSONEncoder
import logging
from logging.handlers import RotatingFileHandler
import os

LOG_DIR = 'logs'
RUN_LOG_FILE_PATH = os.path.join(LOG_DIR, 'bambooai_run_log.json')
CONSOLIDATED_LOG_FILE_PATH = os.path.join(LOG_DIR, 'consolidated_logs.json')

# Create the logs directory if it doesn't exist
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Initialize the JSON logger
logger = logging.getLogger('bambooai_json_logger')
logger.setLevel(logging.INFO)
logger.propagate = False

# Remove all handlers associated with the logger object.
for handler in logger.handlers:
    logger.removeHandler(handler)

# Initialize the Rotating File Handler for JSON log
handler = RotatingFileHandler(CONSOLIDATED_LOG_FILE_PATH, maxBytes=5*1024*1024, backupCount=3)  # 5 MB
logger.addHandler(handler)

# The purpose of this class is to provide a custom JSON encoder that can serialize custom objects that come as a part of Anthropic API tool use responses.
class FlexibleJSONEncoder(JSONEncoder):
    def default(self, obj):
        if hasattr(obj, '__dict__'):
            return self.serialize_custom_object(obj)
        elif isinstance(obj, dict):
            return {k: self.default(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self.default(item) for item in obj]
        return super().default(obj)

    def serialize_custom_object(self, obj):
        obj_dict = obj.__dict__.copy()
        obj_dict['__custom_class__'] = obj.__class__.__name__
        return obj_dict

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

    def print_summary_to_terminal(self, output_manager):
        prompt_tokens = 0
        completion_tokens = 0
        total_tokens = 0
        elapsed_time = 0
        total_cost = 0

        for chain_id, tokens in self.token_summary.items():
            prompt_tokens += tokens['prompt_tokens']
            completion_tokens += tokens['completion_tokens']
            total_tokens += tokens['total_tokens']
            elapsed_time += tokens['elapsed_time']
            total_cost += tokens['total_cost']

        avg_speed = completion_tokens / elapsed_time if elapsed_time > 0 else 0

        summary_text = ""
        summary_text += f"Chain ID: {chain_id}\n"
        summary_text += f"Total Prompt Tokens: {prompt_tokens}\n"
        summary_text += f"Total Completion Tokens: {completion_tokens}\n"
        summary_text += f"Total Tokens: {total_tokens}\n"
        summary_text += f"Total Time (LLM Interact.): {elapsed_time:.2f} seconds\n"
        summary_text += f"Average Response Speed: {avg_speed:.2f} tokens/second\n"
        summary_text += f"Total Cost: ${total_cost:.4f}\n"

        output_manager.display_call_summary(summary_text)

    def write_to_log(self, agent, chain_id, timestamp, model, messages, content, prompt_tokens, completion_tokens, total_tokens, elapsed_time, tokens_per_second):
        # Calculate the costs
        token_costs = self.token_cost_dict.get(model, {})
        prompt_token_cost = token_costs.get('prompt_tokens', 0)
        completion_token_cost = token_costs.get('completion_tokens', 0)
        cost = ((prompt_tokens * prompt_token_cost) / 1000) + ((completion_tokens * completion_token_cost) / 1000)
        
        self.update_token_summary(chain_id, prompt_tokens, completion_tokens, total_tokens, elapsed_time, cost)

        # Writing to JSON log
        json_entry = {
            'agent': agent,
            'chain_id': chain_id,
            'timestamp': timestamp,
            'model': model,
            'messages': messages,
            'content': content,
            'prompt_tokens': prompt_tokens,
            'completion_tokens': completion_tokens,
            'total_tokens': total_tokens,
            'elapsed_time': elapsed_time,
            'tokens_per_second': tokens_per_second,
            'cost': cost
        }
        # Load existing JSON logs from file
        try:
            with open(RUN_LOG_FILE_PATH, 'r') as json_file:
                file_content = json_file.read()
                if not file_content:
                    existing_json_logs = []
                else:
                    existing_json_logs = json.loads(file_content)
        except FileNotFoundError:
            existing_json_logs = []
        
        # Append the new JSON log entry to the existing logs
        existing_json_logs.append(json_entry)
        
        # Write the updated JSON logs back to the file
        with open(RUN_LOG_FILE_PATH, 'w') as json_file:
            json.dump(existing_json_logs, json_file, indent=2, cls=FlexibleJSONEncoder)


    def consolidate_logs(self):     
        # Read the existing original JSON log file
        if os.path.exists(RUN_LOG_FILE_PATH):
            with open(RUN_LOG_FILE_PATH, 'r') as json_file:
                existing_json_logs = json.load(json_file)
        else:
            existing_json_logs = []
        
        # Read the existing consolidated JSON log file
        consolidated_logs = {}
        if os.path.exists(CONSOLIDATED_LOG_FILE_PATH):
            with open(CONSOLIDATED_LOG_FILE_PATH, 'r') as json_file:
                file_content = json_file.read()
                if file_content.strip():
                    consolidated_logs = json.loads(file_content)
        
        # Update the consolidated logs
        for entry in existing_json_logs:
            chain_id = entry['chain_id']
            model = entry['model']
            
            if chain_id not in consolidated_logs:
                consolidated_logs[chain_id] = {
                    'chain_details': [],
                    'chain_summary': {},
                    'summary_per_model': {}
                }
            
            if model not in consolidated_logs[chain_id]['summary_per_model']:
                consolidated_logs[chain_id]['summary_per_model'][model] = {
                    'LLM Calls': 0,
                    'Prompt Tokens': 0,
                    'Completion Tokens': 0,
                    'Total Tokens': 0,
                    'Total Time': 0, 
                    'Tokens per Second': 0,
                    'Total Cost': 0
                }
            
            consolidated_logs[chain_id]['chain_details'].append(entry)
            consolidated_logs[chain_id]['summary_per_model'][model]['LLM Calls'] += 1
            consolidated_logs[chain_id]['summary_per_model'][model]['Prompt Tokens'] += entry['prompt_tokens']
            consolidated_logs[chain_id]['summary_per_model'][model]['Completion Tokens'] += entry['completion_tokens']
            consolidated_logs[chain_id]['summary_per_model'][model]['Total Tokens'] += entry['total_tokens']
            consolidated_logs[chain_id]['summary_per_model'][model]['Total Time'] += entry['elapsed_time']
            consolidated_logs[chain_id]['summary_per_model'][model]['Tokens per Second'] = round(
                consolidated_logs[chain_id]['summary_per_model'][model]['Completion Tokens'] /
                consolidated_logs[chain_id]['summary_per_model'][model]['Total Time'], 2)
            consolidated_logs[chain_id]['summary_per_model'][model]['Total Cost'] += entry['cost']
            

        # Update chain summaries
        for chain_id, summary_data in self.token_summary.items():
            if chain_id in consolidated_logs:
                summary = {}
                summary['Total LLM Calls'] = len(consolidated_logs[chain_id]['chain_details'])
                summary['Prompt Tokens'] = summary_data['prompt_tokens']
                summary['Completion Tokens'] = summary_data['completion_tokens']
                summary['Total Tokens'] = summary_data['total_tokens']
                summary['Total Time'] = round(summary_data['elapsed_time'], 2)
                summary['Tokens per Second'] = round(summary_data['completion_tokens'] / summary_data['elapsed_time'], 2)
                summary['Total Cost'] = round(summary_data['total_cost'], 4)
                
                consolidated_logs[chain_id]['chain_summary'] = summary
        
        # Write the updated consolidated logs back to the file
        with open(CONSOLIDATED_LOG_FILE_PATH, 'w') as json_file:
            json.dump(consolidated_logs, json_file, indent=2, cls=FlexibleJSONEncoder)

    def clear_run_logs(self):
        # Clear the existing log entries and token summary
        self.token_summary.clear()

        # Clear the original log file
        with open(RUN_LOG_FILE_PATH, 'w') as json_file:
            json.dump([], json_file, indent=2, cls=FlexibleJSONEncoder)


