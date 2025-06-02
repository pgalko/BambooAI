from io import StringIO
import sys
import queue
import json
import pandas as pd

from bambooai.output_manager import OutputManager

class WebOutputManager(OutputManager):
    def __init__(self):
        super().__init__()
        self.web_mode = False
        self.output_queue = queue.Queue()
        self.input_queue = queue.Queue()
        self.capture_output = StringIO()
        self.last_chunk_ended_with_newline = True

    def enable_web_mode(self):
        self.web_mode = True
        self.capture_output = StringIO()
        sys.stdout = self.capture_output

    def disable_web_mode(self):
        self.web_mode = False
        sys.stdout = sys.__stdout__
        self.capture_output.close()

    def print_wrapper(self, message, end="\n", flush=False, chain_id=None, thought=False):
        formatted_message = str(message)
        if self.web_mode:
            if self.last_chunk_ended_with_newline and formatted_message.startswith("\n"):
                formatted_message = formatted_message.lstrip("\n")
            if end:
                formatted_message += end
                self.last_chunk_ended_with_newline = end.endswith("\n")
            else:
                self.last_chunk_ended_with_newline = False
            
            if formatted_message:
                if thought:
                    self.output_queue.put(json.dumps({"thought": formatted_message, "chain_id": chain_id}))
                else:
                    self.output_queue.put(json.dumps({"text": formatted_message, "chain_id": chain_id}))

        super().print_wrapper(formatted_message, end='', flush=flush, chain_id=chain_id, thought=thought)

    def get_captured_output(self):
        output = self.capture_output.getvalue()
        self.capture_output.truncate(0)
        self.capture_output.seek(0)
        return output

    def get_queue_output(self):
        output = []
        while not self.output_queue.empty():
            output.append(self.output_queue.get_nowait())
        return '\n'.join(output)  # Join with newlines for compatibility with existing code
    
    def get_user_input(self):
        if self.web_mode:
            try:
                return self.input_queue.get(block=False)
            except queue.Empty:
                return None
        else:
            return super().display_user_input_prompt()

    def add_user_input(self, user_input):
        self.input_queue.put(user_input)

    def send_chain_id(self, thread_id, chain_id, df_id):
        self.output_queue.put(json.dumps({
            "type": "id",
            "thread_id": thread_id, 
            "chain_id": chain_id,
            "df_id": df_id
        }))

    def request_user_feedback(self, chain_id=None, query_clarification=None, context_needed=None):
        if self.web_mode:
            self.output_queue.put(json.dumps({
                "type": "request_user_context",
                "query_clarification": query_clarification,
                "context_needed": context_needed,
                "chain_id": chain_id
            }))
            return None  # In web mode, feedback is handled by the Flask route
        else:
            return super().request_user_feedback(chain_id, query_clarification, context_needed)

    def send_html_content(self, html_content, chain_id=None):
        """Send HTML content directly to the client"""
        if self.web_mode:
            self.output_queue.put(json.dumps({
                "type": "html",
                "content": html_content,
                "chain_id": chain_id
            }))
        else:
            super().send_html_content(html_content, chain_id)

    def display_results(self, chain_id=None, execution_mode=None, 
                        df_id=None, api_client=None, df=None, 
                        query=None, data_model=None, research=None, 
                        plan=None, code=None, answer=None, 
                        plot_jsons=None, review=None, 
                        vector_db=False, generated_datasets=None, 
                        semantic_search=None, code_exec_results=None):
        from bambooai import utils
        
        if self.web_mode:
            if df_id is not None:
                df_index = utils.computeDataframeSample(df=df,execution_mode=execution_mode, df_id=df_id, executor_client=api_client)
                df_html = df_index.to_html(classes='dataframe', border=0, index=False)
                df_json = json.dumps({'type': 'dataframe', 'data': df_html, 'chain_id': chain_id})
                self.output_queue.put(df_json)
            
            for data_type, data in [
                ('query', query),
                ('model', data_model),
                ('research', research),
                ('plan', plan),
                ('code', code),
                ('answer', answer),
                ('generated_datasets', generated_datasets),
                ('semantic_search', semantic_search),
                ('code_exec_results', code_exec_results)
            ]:
                if data:
                    json_data = json.dumps({'type': data_type, 'data': data, 'chain_id': chain_id})
                    self.output_queue.put(json_data)

            # Send plot JSONs if they exist
            if plot_jsons:
                for plot_json in plot_jsons:
                    self.output_queue.put(plot_json)
            
            # Signal end of results
            self.output_queue.put(json.dumps({'type': 'end', 'data': None, 'chain_id': chain_id}))
        else:
            super().display_results(df=df, data_model=data_model, research=research, plan=plan, code=code, answer=answer, review=review, vector_db=vector_db)


    def display_tool_start(self, agent, model, chain_id=None):
        if self.web_mode:
            self.output_queue.put(json.dumps({'tool_start': {'agent': agent, 'model': model}, 'chain_id': chain_id}))
        else:
            super().display_tool_start(agent, model, chain_id)

    def display_error(self, error, chain_id=None):
        if self.web_mode:
            self.output_queue.put(json.dumps({'error': str(error), 'chain_id': chain_id}))
        else:
            super().display_error(error, chain_id)

    def display_user_input_prompt(self):
        if self.web_mode:
            return None  # In web mode, input is handled by the Flask route
        else:
            return super().display_user_input_prompt()

    def display_user_input_rank(self):
        if self.web_mode:
            return None  # In web mode, ranking input is handled by the Flask route
        else:
            return super().display_user_input_rank()

    def display_tool_info(self, action, action_input, chain_id=None):
        if self.web_mode:
            self.output_queue.put(json.dumps({'tool_call': {'action': action, 'input': action_input}, 'chain_id': chain_id}))
        else:
            super().display_tool_info(action, action_input, chain_id)

    def display_system_messages(self, message):
        if self.web_mode:
            self.output_queue.put(json.dumps({'system_message': message}))
        else:
            super().display_system_messages(message)

    def display_call_summary(self, summary_text):
        if self.web_mode:
            self.output_queue.put(json.dumps({'call_summary': summary_text}))
        else:
            super().display_call_summary(summary_text)