import io
import os
import sys
import json
import traceback
import matplotlib
import matplotlib.pyplot as plt
import base64
from contextlib import redirect_stdout
import pyarrow as pa
import pyarrow.parquet as pq
import zlib
from datetime import datetime

class CodeExecutor:
    def __init__(self, webui=False, mode='local', api_client=None):
        self.webui = webui
        self.mode = mode
        self.plots_dir = "iframe_figures"
        self.original_df = None

        self.api_client = api_client

        BAMBOO_PLOT_FORMAT = os.environ.get('BAMBOO_PLOT_FORMAT')
        if BAMBOO_PLOT_FORMAT is None:
            BAMBOO_PLOT_FORMAT = 'json'

        self.html_patch_code = """
import plotly.io as pio
original_show = pio.show
def show(fig, *args, **kwargs):
    fig.update_layout(template='plotly_dark', dragmode='pan', hovermode='closest', autosize=True)
    filename = f'{_plots_dir}/figure_{id(fig)}.html'
    fig.write_html(filename)
    _generated_files.append(filename)
pio.show = show
"""
        self.json_patch_code = """
import plotly.io as pio
original_show = pio.show
def show(fig, *args, **kwargs):
    fig.update_layout(template='plotly_dark', dragmode='pan', hovermode='closest', autosize=True)
    filename = f'{_plots_dir}/figure_{id(fig)}.json'
    fig.write_json(filename)
    _generated_files.append(filename)
pio.show = show
"""
        if BAMBOO_PLOT_FORMAT == 'html':
            self.patch_code = self.html_patch_code
        elif BAMBOO_PLOT_FORMAT == 'json':
            self.patch_code = self.json_patch_code

        self.plot_format = BAMBOO_PLOT_FORMAT

        # Cross-platform directory handling
        if not os.path.isdir(self.plots_dir):
            try:
                os.makedirs(self.plots_dir)
            except Exception:
                # If directory creation fails for any reason but directory exists
                if not os.path.isdir(self.plots_dir):
                    raise  # Re-raise if directory doesn't exist

        if self.webui:
            matplotlib.use('Agg')
            plt.ioff()

    def log_to_file(self, message):
        """Write log message to file with timestamp"""

        LOG_DIR = 'logs'
        LOG_FILE = os.path.join(LOG_DIR, 'code_executor.log')
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        with open(LOG_FILE, 'a') as f:
            f.write(f"[INFO] {timestamp} - {message}\n")

    def execute(self, code, df=None, df_id=None, generated_datasets_path=None):
        # Store the original DataFrame for resetting if needed
        self._original_df = df.copy() if df is not None else None

        if self.mode == 'local':
            return self._execute_local(code, df, generated_datasets_path)
        elif self.mode == 'api':
            return self._execute_via_api_client(code, df, df_id, generated_datasets_path)
        else:
            raise ValueError("Invalid mode. Choose 'local' or 'api'.")
        
    def _execute_local(self, code, df=None, generated_datasets_path=None):
        output_buffer = io.StringIO()
        plot_images = []
        generated_files = []

        if generated_datasets_path is not None:
            if not os.path.isdir(generated_datasets_path):
                try:
                    os.makedirs(generated_datasets_path)
                except Exception as e:
                    self.log_to_file(f"Error creating directory {generated_datasets_path}: {str(e)}")

        try:
            plt.close('all')
            with redirect_stdout(output_buffer):

                local_vars = {
                    'df': df,
                    '_plots_dir': self.plots_dir,
                    '_generated_files': generated_files
                }
                
                # Only apply patch if in webui mode
                if self.webui:
                    exec(self.patch_code + code, local_vars)
                else:
                    exec(code, local_vars)
                    
                result_df = local_vars['df']

                if self.webui:
                    # Handle matplotlib figures
                    figs = [plt.figure(i) for i in plt.get_fignums()]
                    for fig in figs:
                        if len(fig.axes) > 0:
                            buf = io.BytesIO()
                            fig.savefig(buf, format='png')
                            buf.seek(0)
                            plot_images.append({
                                    'data': base64.b64encode(buf.getvalue()).decode('utf-8'),
                                    'format': 'png'
                                })
                            buf.close()
                        plt.close(fig)
                    
                    # Handle plotly figures
                    if os.path.isdir(self.plots_dir):
                        # Only process files we generated
                        for file_path in sorted(generated_files):
                            try:
                                # First try UTF-8
                                try:
                                    with open(file_path, 'r', encoding='utf-8') as f:
                                        file_content = f.read()
                                except UnicodeDecodeError:
                                    # If UTF-8 fails, read as latin-1 and encode back to UTF-8
                                    with open(file_path, 'r', encoding='latin-1') as f:
                                        raw_content = f.read()
                                        # Convert to UTF-8
                                        file_content = raw_content.encode('utf-8', errors='replace').decode('utf-8')
                                
                                # Validate JSON can be parsed before adding to plot_images
                                if self.plot_format == 'json':
                                    json.loads(file_content)  # This will raise an exception if JSON is invalid
                                    
                                plot_images.append({
                                    'data': file_content,
                                    'format': self.plot_format
                                })
                            except Exception as e:
                                print(f"Error reading file {file_path}: {str(e)}")
                                continue  # Skip this file and continue with others

            results = output_buffer.getvalue()

            # Iterate over generated_datasets_path directory for any generated datasets.
            if generated_datasets_path is not None:
                generated_datasets = []
                if os.path.isdir(generated_datasets_path):
                    for filename in os.listdir(generated_datasets_path):
                        file_path = os.path.join(generated_datasets_path, filename)
                        if os.path.isfile(file_path):
                            generated_datasets.append(file_path)
                    if not generated_datasets:
                        try:
                            os.rmdir(generated_datasets_path)
                        except OSError as e:
                            self.log_to_file(f"Error removing empty directory {generated_datasets_path}: {str(e)}")
                else:
                    self.log_to_file(f"Generated datasets path {generated_datasets_path} does not exist.")

            return result_df, results, None, plot_images, generated_datasets

        except Exception as error:
            exc_type, exc_value, tb = sys.exc_info()
            full_traceback = traceback.format_exc()
            exec_traceback = self.filter_exec_traceback(code, full_traceback, exc_type.__name__, str(exc_value))

            return self._original_df, None, exec_traceback, [], []

        finally:
            if self.webui:
                plt.close('all')
            output_buffer.close()

    def _execute_via_api_client(self, code, df=None, df_id=None, generated_datasets_path=None):
        """Execute code via executor API client"""
        try:
            response = self.api_client.execute_code(
                code=code,
                df_id=df_id,
                patch_code=self.patch_code,
                plots_dir=self.plots_dir,
                plot_format=self.plot_format,
                generated_datasets_path=generated_datasets_path
            )
            
            return (
                df,  # Return original df reference
                response.get('results'),
                response.get('error'),
                response.get('plot_images', []),
                response.get('generated_datasets', [])
            )
            
        except Exception as e:
            self.log_to_file(f"Error executing via API client: {str(e)}")
            return df, None, str(e), []

    def _serialize_df(self, df):
        buffer = io.BytesIO()
        pq.write_table(pa.Table.from_pandas(df), buffer)
        compressed = zlib.compress(buffer.getvalue())
        return base64.b64encode(compressed).decode('utf-8')

    def _deserialize_df(self, df_str):
        decompressed = zlib.decompress(base64.b64decode(df_str))
        buffer = io.BytesIO(decompressed)
        return pq.read_table(buffer).to_pandas()

    def filter_exec_traceback(self, code, full_traceback, exception_type, exception_value):
        # Calculate offset from monkey patch if in webui mode
        patch_offset = len(self.patch_code.split('\n')) - 1 if self.webui else 0
        
        # Split the full traceback and code into lines
        tb_lines = full_traceback.split('\n')
        code_lines = code.split('\n')
        
        # Find the line numbers from traceback and adjust for patch offset
        error_lines = []
        for line in tb_lines:
            if '<string>' in line:
                line_num = int(line.split(', line ')[1].split(',')[0]) - patch_offset
                error_lines.append(line_num)
        
        if error_lines:
            actual_error_line = error_lines[0]
            
            # Get the relevant code snippet for context
            start_line = max(0, actual_error_line - 3)
            end_line = min(len(code_lines), actual_error_line + 2)
            relevant_code = []
            for i, line in enumerate(code_lines[start_line:end_line], start=start_line+1):
                if i == actual_error_line:
                    relevant_code.append(f"{i}: --> {line}")
                else:
                    relevant_code.append(f"{i}:     {line}")
            relevant_code = '\n'.join(relevant_code)
            
            filtered_traceback = f"Error occurred in the following code snippet:\n\n{relevant_code}\n\n"
            filtered_traceback += f"Error on line {actual_error_line}:\n"
            filtered_traceback += f"{exception_type}: {exception_value}\n\n"
            
            filtered_traceback += "Traceback (most recent call last):\n"
            
            # Group traceback lines
            traceback_groups = []
            current_group = []
            for line in tb_lines:
                if '<string>' in line or exception_type in line:
                    if current_group and 'File "<string>"' in current_group[0]:
                        traceback_groups.append(current_group)
                    current_group = [line]
                elif current_group:
                    current_group.append(line)
            if current_group:
                traceback_groups.append(current_group)
            
            # Process groups adjusting line numbers
            for group in traceback_groups:
                for line in group:
                    if '<string>' in line:
                        original_line_num = int(line.split(', line ')[1].split(',')[0])
                        adjusted_line_num = original_line_num - patch_offset
                        # Replace the line number in the traceback
                        line = line.replace(f'line {original_line_num}', f'line {adjusted_line_num}')
                        filtered_traceback += line + '\n'
                        if 0 <= adjusted_line_num - 1 < len(code_lines):
                            filtered_traceback += "    " + code_lines[adjusted_line_num - 1].strip() + '\n'
                    elif exception_type in line and 'raise' in line:
                        filtered_traceback += "    " + line + '\n'
            
            if not filtered_traceback.strip().endswith(str(exception_value)):
                filtered_traceback += f"{exception_type}: {exception_value}\n"
        else:
            filtered_traceback = full_traceback
        
        # Truncate the traceback to 1000 characters
        if len(filtered_traceback) > 1000:
            filtered_traceback = filtered_traceback[:1000] + f"\n[...] (truncated to 1000 characters)\n"

        return filtered_traceback