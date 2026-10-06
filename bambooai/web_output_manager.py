import os
from io import StringIO
import sys
import queue
import json
import logging
import pandas as pd
import plotly.graph_objects as go
import plotly.io as pio
import base64

from bambooai.output_manager import OutputManager

class WebOutputManager(OutputManager):
    def __init__(self):
        super().__init__()
        self.web_mode = True
        self.output_queue = queue.Queue()
        self.input_queue = queue.Queue()
        self.capture_output = StringIO()
        self.last_chunk_ended_with_newline = True
        self.max_interactive_points = 20000
        self.plot_size_threshold_mb = 2  # Convert plots larger than 2MB to PNG

        try:
            # Optimized Chromium args for better performance
            pio.kaleido.scope.chromium_args = [
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--single-process',
                '--disable-web-security',
                '--disable-features=VizDisplayCompositor',
                '--disable-software-rasterizer',
                '--disable-extensions',
                '--no-first-run',
                '--disable-default-apps',
                '--mute-audio',
                '--no-zygote'
            ]
        except:
            pass

    def plot_json_to_png(self, plot_json):
        """One plot wrapper, converted to a PNG wrapper (json string), or
        None on failure. The single conversion seam: size-triggered
        optimization and the synthesis figure resolver both ride it."""
        try:
            plot_data = json.loads(plot_json) if isinstance(plot_json, str) else plot_json
            if plot_data.get('format') == 'png':
                return json.dumps(plot_data)
            if plot_data.get('type') == 'plot' and 'data' in plot_data:
                actual = json.loads(plot_data['data']) if isinstance(plot_data['data'], str) else plot_data['data']
            else:
                actual = plot_data
            fig = go.Figure(data=actual.get('data', []),
                            layout=actual.get('layout', {}))
            png_bytes = pio.to_image(fig, format='png', width=1200, height=800, scale=2)
            result = plot_data.copy()
            result['format'] = 'png'
            result['data'] = base64.b64encode(png_bytes).decode('utf-8')
            return json.dumps(result)
        except Exception:
            # Log_44: four figures dropped with no cause on record. The
            # converter is the only place that knows why (kaleido,
            # chromium, malformed spec) - say so.
            import logging
            logging.getLogger(__name__).warning(
                "plot_json_to_png failed; the figure will be dropped.",
                exc_info=True)
            return None

    def optimize_plot_json(self, plot_json):
        """Convert large plots to PNG to reduce size"""
        try:
            plot_data = json.loads(plot_json) if isinstance(plot_json, str) else plot_json
            
            # Skip if already converted
            if plot_data.get('format') == 'png':
                return json.dumps(plot_data) if not isinstance(plot_json, str) else plot_json, 'png'
            
            # Extract actual plot data
            if plot_data.get('type') == 'plot' and 'data' in plot_data:
                actual_plot_data = json.loads(plot_data['data']) if isinstance(plot_data['data'], str) else plot_data['data']
            else:
                actual_plot_data = plot_data
            
            plot_json_str = json.dumps(plot_data) if not isinstance(plot_json, str) else plot_json
            plot_size_mb = sys.getsizeof(plot_json_str) / (1024 * 1024)
            
            # Only convert if size exceeds threshold
            if plot_size_mb > self.plot_size_threshold_mb:
                converted = self.plot_json_to_png(plot_json)
                if converted:
                    return converted, 'png'
                return plot_json_str, 'json'
            
            return plot_json_str, 'json'
            
        except:
            return json.dumps(plot_json) if not isinstance(plot_json, str) else plot_json, 'json'

    def print_wrapper(self, message, end="\n", flush=False, chain_id=None, thought=False):
        formatted_message = str(message)
        
        # Check silent mode first (inherited from parent)
        if self.silent_mode:
            self._captured_output.append(formatted_message)
            if end:
                self._captured_output.append(end)
            return
        
        # Original web mode behavior
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
        else:
            super().print_wrapper(formatted_message, end='', flush=flush, chain_id=chain_id, thought=thought)
    
    def send_assistant_consultation(self, chain_id, query_summary, response_content):
        """
        Send a Socratic assistant consultation result to the frontend.
        Displays as a single collapsible tool call with query and response.
        """
        if self.web_mode:
            self.output_queue.put(json.dumps({
                "type": "assistant_consultation",
                "query_summary": query_summary,
                "response": response_content,
                "chain_id": chain_id
            }))
        else:
            # CLI/Notebook mode - print formatted output
            print(f"\n{'='*60}")
            print(f"ASSISTANT PERSPECTIVE")
            print(f"{'='*60}")
            print(f"Query: {query_summary}")
            print(f"\nPerspective:\n{response_content}")
            print(f"{'='*60}\n")

    def send_synthesis_image(self, image_base64, mime_type, chain_id=None):
        """Send synthesis infographic image to frontend"""
        if self.web_mode:
            self.output_queue.put(json.dumps({
                'type': 'synthesis_image',
                'data': image_base64,
                'mime_type': mime_type,
                'chain_id': chain_id
            }))

    def get_captured_output(self):
        output = self.capture_output.getvalue()
        self.capture_output.truncate(0)
        self.capture_output.seek(0)
        return output

    def get_queue_output(self):
        output = []
        while not self.output_queue.empty():
            output.append(self.output_queue.get_nowait())
        return '\n'.join(output)
    
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

    def send_chain_id(self, thread_id, chain_id, df_id, **extra):
        # `parent_chain_id` rides here for plain user chains (rule B,
        # 2026-08-27): the server knows where the chain attached, and the
        # browser draws the map from that one record. Adaptive runs omit
        # it - their new_iteration headers place probes under their
        # planning turn.
        self.output_queue.put(json.dumps({
            "type": "id",
            "thread_id": thread_id, 
            "chain_id": chain_id,
            "df_id": df_id,
            **extra,
        }))

    def request_user_feedback(self, chain_id=None, query_clarification=None, context_needed=None):
        if self.web_mode:
            self.output_queue.put(json.dumps({
                "type": "request_user_context",
                "query_clarification": query_clarification,
                "context_needed": context_needed,
                "chain_id": chain_id
            }))
            return None
        else:
            return super().request_user_feedback(chain_id, query_clarification, context_needed)

    def send_html_content(self, html_content, chain_id=None):
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
                        query=None, data_model=None, 
                        plan=None, code=None, answer=None, 
                        simplified_answer=None,
                        plot_jsons=None, review=None, 
                        generated_datasets=None, code_exec_results=None, explore=False):
        from bambooai import utils
        
        if self.web_mode:
            if df_id is not None:
                # the Data tab (2026-09-07): the first page as JSON for the grid; the browser fetches the rest on demand
                page = None
                try:
                    if execution_mode == 'api' and api_client is not None and df_id:
                        page = api_client.dataframe_page(df_id, 0, 50)
                    elif df is not None:
                        page = utils.page_frame(df, 0, 50)
                except Exception as exc:                       # noqa: BLE001
                    logging.getLogger(__name__).warning("Data tab: page request failed (%s); falling back to the 100-row preview", exc)
                    page = None
                if page:
                    page['df_id'] = df_id
                    df_json = json.dumps({'type': 'dataframe', 'data': page, 'chain_id': chain_id})
                else:
                    if execution_mode == 'api':
                        build = api_client.executor_build() if api_client is not None else None
                        logging.getLogger(__name__).warning("Data tab: the executor returned no page (build %s) - falling back to the 100-row preview; "
                                                            "an image before 2026-09-07 has no /dataframe_page", build or "unknown/pre-2026-09-07")
                    df_index = utils.computeDataframeSample(df=df,execution_mode=execution_mode, df_id=df_id, executor_client=api_client)
                    df_html = df_index.to_html(classes='dataframe', border=0, index=False)
                    df_json = json.dumps({'type': 'dataframe', 'data': df_html, 'chain_id': chain_id})
                self.output_queue.put(df_json)
            
            for data_type, data in [
                ('query', query),
                ('model', data_model),
                ('plan', plan),
                ('code', code),
                ('answer', answer),
                ('simplified_answer', simplified_answer),
                ('code_exec_results', code_exec_results)      # generated datasets are the pane's pills, not a tab (2026-10-06: the tab was empty)
            ]:
                if data:
                    payload = {'type': data_type, 'data': data, 'chain_id': chain_id}
                    if explore and data_type == 'answer':
                        payload['explore'] = True          # the seedling's five questions: the Explore tab (2026-09-08)
                    self.output_queue.put(json.dumps(payload))

            if plot_jsons:
                for plot_json in plot_jsons:
                    optimized_plot, format_type = self.optimize_plot_json(plot_json)
                    self.output_queue.put(optimized_plot)
            
            self.output_queue.put(json.dumps({'type': 'end', 'data': None, 'chain_id': chain_id}))
        else:
            super().display_results(df=df, data_model=data_model, plan=plan, code=code, answer=answer, review=review)

    def display_tool_start(self, agent, model, chain_id=None):
        if self.silent_mode:
            return
        if self.web_mode:
            self.output_queue.put(json.dumps({'tool_start': {'agent': agent, 'model': model}, 'chain_id': chain_id}))
        else:
            super().display_tool_start(agent, model, chain_id)

    def display_error(self, error, chain_id=None):
        if self.web_mode:
            self.output_queue.put(json.dumps({'error': str(error), 'chain_id': chain_id}))
        else:
            super().display_error(error, chain_id)

    def display_corrected_code(self, code, chain_id=None):
        # A top-level key, like 'error', handled by the front end BEFORE the
        # generic type branch (which would invent a right-pane tab for it).
        # The pane's last fenced script is the FAULTY one - the corrector
        # streams edit blocks now, not a full fence - so this event is how
        # the reader ever sees the script that actually ran.
        if self.web_mode:
            self.output_queue.put(json.dumps({'corrected_code': str(code), 'chain_id': chain_id}))
        else:
            super().display_corrected_code(code, chain_id)

    def display_user_input_prompt(self):
        if self.web_mode:
            return None
        else:
            return super().display_user_input_prompt()

    def display_tool_info(self, action, action_input, chain_id=None):
        if self.silent_mode:
            return
        if self.web_mode:
            self.output_queue.put(json.dumps({'tool_call': {'action': action, 'input': action_input}, 'chain_id': chain_id}))
        else:
            super().display_tool_info(action, action_input, chain_id)

    def display_system_messages(self, message, chain_id=None):
        if self.web_mode:
            self.output_queue.put(json.dumps({'system_message': message}))
        else:
            super().display_system_messages(message, chain_id)

    def display_call_summary(self, summary_text):
        if self.web_mode:
            self.output_queue.put(json.dumps({'call_summary': summary_text}))
        else:
            super().display_call_summary(summary_text)