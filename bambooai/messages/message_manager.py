import os
import json
from bambooai import prompts, reg_ex
# from .bambooai import BambooAI
from bambooai.output_manager import OutputManager
from bambooai.storage_manager import SimpleInteractionStore, StorageError
from bambooai.service_registry import services

class MessageManager:
    def __init__(self, output_manager: OutputManager, interaction_store, model_dict, max_conversations=5):
        self.max_conversations = max_conversations
        self.output_manager = output_manager
        self.model_dict = model_dict
        self.interaction_store = interaction_store
        self.prompts = services.get_prompts()

        # QA Pairs (a list of dictionaries containing "question/results of the code execution" pairs)
        self.qa_pairs = []

        # Tasks (a list of task)
        self.tasks = []

        # Last generated code
        self.last_code = None

        # Last generated plan
        self.last_plan = None
        try:
            self.interaction_store = SimpleInteractionStore()
        except StorageError as e:
            # self.output_manager.print_wrapper(f"Warning: Failed to initialize interaction store: {e}")
            self.interaction_store = None

        # Messages lists
        self.pre_eval_messages = [{"role": "system", "content": self.prompts.expert_selector_system}]
        self.select_analyst_messages = [{"role": "system", "content": self.prompts.analyst_selector_system}]
        self.eval_messages = [{"role": "system", "content": self.prompts.planner_system}]
        self.code_messages = [{"role": "system", "content": self.prompts.code_generator_system_df}]
        self.df_inspector_messages = [{"role": "system", "content": self.prompts.dataframe_inspector_system}]
        self.plan_review_messages = None
        self.insight_messages = None

    def restore_interaction(self, thread_id, chain_id):
        if self.interaction_store:
            restored_data = self.interaction_store.restore_interaction(
                thread_id=str(thread_id),
                chain_id=str(chain_id)
            )
            
            # Set the messages from restored data
            self.pre_eval_messages = restored_data['pre_eval_messages']
            self.select_analyst_messages = restored_data['select_analyst_messages']
            self.eval_messages = restored_data['eval_messages']
            self.df_inspector_messages = restored_data['df_inspector_messages']
            self.code_messages = restored_data['code_messages']
            self.plan_review_messages = restored_data['plan_review_messages']
            self.insight_messages = restored_data['insight_messages']

            # Restore code execution results
            self.code_exec_results = restored_data['code_exec_results']

            # Restore the last executed code
            self.last_code = restored_data['executed_code']

            # Restore the QA pairs
            self.qa_pairs = restored_data['qa_pairs']
            
            # Restore the tasks
            self.tasks = restored_data['tasks']

    def store_interaction(self, thread_id, chain_id, google_search_results=None, code_exec_results=None, plot_jsons=None):
        if self.interaction_store:
            messages = {
                'pre_eval_messages': self.pre_eval_messages,
                'select_analyst_messages': self.select_analyst_messages,
                'eval_messages': self.eval_messages,
                'df_inspector_messages': self.df_inspector_messages,
                'code_messages': self.code_messages,
                'plan_review_messages': self.plan_review_messages,
                'insight_messages': self.insight_messages
            }
            
            # Collect all search triplets maintaining query-links relationship
            search_results = {
                'search': {
                    'searches': [] # List of search triplets
                }
            }
            
            # Add search triplets if they exist
            if google_search_results:
                for triplet in google_search_results:
                    search_results['search']['searches'].append({
                        'query': triplet['query'],
                        'result': triplet['result'],
                        'links': triplet['links']
                    })
            
            # Combine search results with code execution results
            tool_results = {
                'search': search_results['search'] if search_results['search']['searches'] else None,
                'code_exec': {
                    'executed_code': self.last_code,
                    'code_exec_results': code_exec_results,
                    'plot_jsons': plot_jsons if plot_jsons else [],
                    'qa_pairs': self.qa_pairs if self.qa_pairs else [],
                    'tasks': self.tasks if self.tasks else []
                }
            }
            
            self.interaction_store.store_interaction(
                thread_id=str(thread_id),
                chain_id=str(chain_id),
                messages=messages,
                tool_results=tool_results
            )

    def reset_messages_and_logs(self, bambooai_instance):
        self.pre_eval_messages = [{"role": "system", "content": self.prompts.expert_selector_system}]
        self.select_analyst_messages = [{"role": "system", "content": self.prompts.analyst_selector_system}]
        self.eval_messages = [{"role": "system", "content": self.prompts.planner_system}]
        self.code_messages = [{"role": "system", "content": self.prompts.code_generator_system_df}]
        self.df_inspector_messages = [{"role": "system", "content": self.prompts.dataframe_inspector_system}]
        self.code_exec_results = None

        bambooai_instance.log_and_call_manager.clear_run_logs()

    def reset_non_cumul_messages(self):
        self.plan_review_messages = None
        self.insight_messages = None

    def reset_retrieved_data(self, bambooai_instance):
        bambooai_instance.retrieved_data_model = None
        bambooai_instance.retrieved_plan = None
        bambooai_instance.retrieved_code = None

    def messages_maintenance(self, messages):
        # Remove tool_calls messages from the messages list
        for i in range(len(messages) - 1, -1, -1):  # Start from the last item to index 0
            msg = messages[i]
            if "tool_calls" in msg or msg.get("role") == "tool":
                messages.pop(i)
        # Remove the oldest conversation from the messages list
        if len(messages) > self.max_conversations:
            messages.pop(1)
            messages.pop(1)
            self.output_manager.display_system_messages("Truncating messages")

    def append_qa_pair(self, question, results):
        # Define the custom operation identifier strings
        custom_identifiers = [
            "User requested to run the code to do a custom analysis of the activity with ID:",
            "User manually edited your code, and requested to run it, and return the result."
        ]

        # Remove all existing custom operation entries
        self.qa_pairs = [
            pair for pair in self.qa_pairs
            if not any(identifier in pair["task"] for identifier in custom_identifiers)
        ]

        # Append the new QA pair
        self.qa_pairs.append({"task": question, "result": results})
        return self.qa_pairs

    def format_qa_pairs(self, max_qa_pairs=8):
        # Format QA pairs for prompts
        if not self.qa_pairs:
            return "No previous analyses."

        # Trim qa_pairs first if it exceeds max_qa_pairs
        if len(self.qa_pairs) > max_qa_pairs:
            self.qa_pairs = self.qa_pairs[-max_qa_pairs:]  # Keep only the most recent pairs

        formatted_str = ["Previous Analyses:"]

        for i, pair in enumerate(self.qa_pairs, 1):
            # Add question with minimal formatting
            formatted_str.append(f"\n{i}. Task: {pair['task']}")

            # Format answer with minimal separators and line preservation
            answer_lines = [line for line in pair['result'].split('\n') if line.strip()]
            formatted_str.append('Result:\n' + '\n'.join(answer_lines))

            # Add minimal separator if not the last pair
            if i < len(self.qa_pairs):
                formatted_str.append("-" * 5)

        return '\n'.join(formatted_str)

    def format_tasks(self):
        # Format tasks for prompts
        if not self.tasks:
            return "No previous tasks."

        formatted_str = ["Tasks:"]

        for i, task in enumerate(self.tasks, 1):
            # Add task with minimal formatting
            formatted_str.append(f"\n{i}. {task}")

            # Add minimal separator if not the last task
            if i < len(self.tasks):
                formatted_str.append("-" * 5)

        return '\n'.join(formatted_str)
    
    def messages_content_maintenance(self, agent, messages, model_template_formating):
        def _process_user_messages(messages, process_func):
            for msg in messages:
                if msg.get('role') == 'user':
                    content = msg.get('content', '')
                    if isinstance(content, list):
                        # Extract only the text content from the message
                        text_content = next((item.get('text', '') for item in content if item.get('type') == 'text'), '')
                        msg['content'] = process_func(text_content)
                    else:
                        msg['content'] = process_func(content)

        if agent == 'Dataframe Inspector':
            _process_user_messages(messages, reg_ex._remove_all_except_task_ontology_text)

        elif agent in ('Planner', 'Theorist'):
            _process_user_messages(messages, reg_ex._remove_all_except_task_xml)

        elif agent == 'Code Executor':
            def code_executor_process_func(content):
                if model_template_formating == 'xml':
                    return reg_ex._remove_all_except_task_xml(content)
                else:
                    return reg_ex._remove_all_except_task_text(content)
            _process_user_messages(messages, code_executor_process_func)

    def format_image_message(self, agent, message_content, image, provider, model, multimodal_models):
        # Format the message content with an image.
        # This replaces the last message content with the image and message content.

        if agent == 'Code Generator' or agent == 'Planner':
            message_content = message_content
        else:
            message_content = self.prompts.plot_query.format(message_content)

        if model in multimodal_models:
            if provider == 'anthropic':
                return {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": image,
                            },
                        },
                        {
                            "type": "text",
                            "text": message_content
                        }
                    ]
                }
            elif provider == 'openai':
                return {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image}"
                            }
                        },
                        {
                            "type": "text",
                            "text": message_content
                        }
                    ]
                }
            elif provider == 'gemini':
                # For Gemini, we'll return a format that can be converted to types.ContentDict later
                return {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_base64",
                            "data": image,
                            "mime_type": "image/png"
                        },
                        {
                            "type": "text",
                            "text": message_content
                        }
                    ]
                }
        else:
            return {
                "role": "user",
                "content": message_content
            }
