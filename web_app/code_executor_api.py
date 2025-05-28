from flask import Flask, request, jsonify, send_from_directory
import io
import os
import sys
import traceback
import matplotlib
import json
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import base64
from contextlib import redirect_stdout
import pyarrow as pa
import pyarrow.parquet as pq
import zlib
from threading import Lock
from collections import OrderedDict
from datetime import datetime
import pandas as pd
import numpy as np
import tempfile
import csv


app = Flask(__name__)

def log_info(message):
    """Helper function for consistent logging format"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[INFO] {timestamp} - {message}")

#### DATAFRAME CACHE ####

class DataFrameCache:
    def __init__(self, max_size=1):
        self.cache = OrderedDict()
        self.lock = Lock()
        self.max_size = max_size
        log_info(f"DataFrame cache initialized with max size: {max_size}")
    
    def get(self, df_id):
        if df_id is None:
            return None
        with self.lock:
            if df_id in self.cache:
                # Move to end to mark as recently used
                df = self.cache.pop(df_id)
                self.cache[df_id] = df
                log_info(f"Retrieved DataFrame from cache: ID={df_id}")
                return df
            log_info(f"Cache miss for DataFrame: ID={df_id}")
            return None
    
    def put(self, df_id, df):
        if df_id is None:
            return
        with self.lock:
            if df_id in self.cache:
                self.cache.pop(df_id)
            elif len(self.cache) >= self.max_size:
                removed_id = next(iter(self.cache))
                self.cache.popitem(last=False)
            self.cache[df_id] = df

# Initialize cache
df_cache = DataFrameCache()

#### CODE EXECUTION ENDPOINTS ####

@app.route('/execute', methods=['POST'])
def execute_code():
    data = request.json
    code = data.get('code')
    df_id = data.get('df_id')  # Can be None
    patch_code = data.get('patch_code')
    plots_dir = data.get('plots_dir')
    plot_format = data.get('plot_format')
    generated_datasets_path = data.get('generated_datasets_path', [])

    log_info(f"Received execution request for DataFrame ID={df_id if df_id else 'None'}")

    # Only try to get DataFrame from cache if df_id is provided
    df = df_cache.get(df_id) if df_id is not None else None

    original_df = df.copy() if df is not None else None
    output_buffer = io.StringIO()
    plot_images = []
    generated_files = []

    if generated_datasets_path is not None:
        # Ensure that the directory exists
        if not os.path.isdir(generated_datasets_path):
            try:
                os.makedirs(generated_datasets_path)
            except Exception as e:
                log_info(f"Error creating directory {generated_datasets_path}: {str(e)}")

    try:
        plt.close('all')
        with redirect_stdout(output_buffer):
            local_vars = {
                'df': df,
                '_plots_dir': plots_dir,
                '_generated_files': generated_files
            }
            
            log_info(f"Executing code")
            exec(patch_code + code, local_vars)
            
            # Get potentially modified DataFrame
            df = local_vars['df']
            
            # Update cache with modified DataFrame on success
            if df_id is not None:
                df = local_vars['df']
                if df is not original_df:
                    df_cache.put(df_id, df)
            
            # Handle matplotlib figures
            figs = [plt.figure(i) for i in plt.get_fignums()]
            if figs:
                log_info(f"Processing {len(figs)} matplotlib figures")
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
            if os.path.isdir(plots_dir):
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
                        if plot_format == 'json':
                            json.loads(file_content)  # This will raise an exception if JSON is invalid
                            
                        plot_images.append({
                            'data': file_content,
                            'format': plot_format
                        })
                        log_info(f"Processed plotly figure: {file_path}")
                    except Exception as e:
                        log_info(f"Error processing plotly figure {file_path}: {str(e)}")
                        continue

        # Iterate over generated_datasets_path directory for any generated datasets.    
        if generated_datasets_path is not None:
            generated_datasets = []
            if os.path.isdir(generated_datasets_path):
                for filename in os.listdir(generated_datasets_path):
                    file_path = os.path.join(generated_datasets_path, filename)
                    if os.path.isfile(file_path):
                        generated_datasets.append(file_path)
                # If the generated_datasets_path directory is empty, delete it.
                if not generated_datasets:
                    try:
                        os.rmdir(generated_datasets_path)
                    except OSError as e:
                        log_info(f"Error removing empty directory {generated_datasets_path}: {str(e)}")
            else:
                log_info(f"Generated datasets path {generated_datasets_path} does not exist.")

        return jsonify({
            'results': output_buffer.getvalue(),
            'error': None,
            'plot_images': plot_images,
            'generated_datasets': generated_datasets if generated_datasets else []
        })

    except Exception as error:
        exc_type, exc_value, tb = sys.exc_info()
        full_traceback = traceback.format_exc()
        exec_traceback = filter_exec_traceback(code, patch_code, full_traceback, exc_type.__name__, str(exc_value))
        
        # Always restore original state in cache on error
        if df_id is not None and original_df is not None:
            df_cache.put(df_id, original_df)
        
        return jsonify({
            'results': None,
            'error': exec_traceback,
            'plot_images': [],
            'generated_datasets': []
        })

    finally:
        plt.close('all')
        output_buffer.close()

#### DATASET UPLOAD ENDPOINT ####

# This endpoint allows users to upload a dataset file (CSV or Parquet) and store it in the cache
@app.route('/upload_dataset', methods=['POST'])
def upload_dataset():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
        
    file = request.files['file']
    df_id = request.form.get('df_id')
    
    if not df_id:
        return jsonify({'error': 'No df_id provided'}), 400
    
    try:
        # Save file temporarily
        temp_path = os.path.join(tempfile.gettempdir(), file.filename)
        file.save(temp_path)
        
        # Load into DataFrame based on file type
        if file.filename.endswith('.csv'):
            df = pd.read_csv(temp_path)
        elif file.filename.endswith('.parquet'):
            df = pd.read_parquet(temp_path)
        else:
            return jsonify({'error': 'Unsupported file type'}), 400
            
        # Clean up temp file
        os.remove(temp_path)
        
        # Store in cache
        df_cache.put(df_id, df)
        
        return jsonify({
            'message': 'Dataset uploaded and cached successfully',
            'df_id': df_id,
            'shape': df.shape,
            'columns': df.columns.tolist()
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

#### DATAFRAME UTILITY ENDPOINTS ####

# This endpoint computes the index for the given DataFrame
@app.route('/df_utils/compute_df_sample', methods=['POST'])
def compute_dataframe_sample():
    data = request.json
    df_id = data.get('df_id')
    
    if not df_id:
        return jsonify({'error': 'No df_id provided'}), 400
        
    df = df_cache.get(df_id)
    if df is None:
        return jsonify({'error': 'DataFrame not found in cache'}), 404
        
    try: 
        result_df = df.head(100)

        return jsonify({
            'data': result_df.to_dict(orient='records'),
            'columns': result_df.columns.tolist()
        })
        
    except Exception as e:
        return jsonify({
            'error': f'Error computing index: {str(e)}',
            'data': df.to_dict(orient='records'),
            'columns': df.columns.tolist()
        })

# This  endpoint returns the df head as a JSON object
@app.route('/df_utils/df_to_string', methods=['POST'])
def dataframe_to_string_endpoint():
    data = request.json
    df_id = data.get('df_id')
    num_rows = data.get('num_rows', 5)
    
    if not df_id:
        return jsonify({'error': 'No df_id provided'}), 400
        
    df = df_cache.get(df_id)
    if df is None:
        return jsonify({'error': 'DataFrame not found in cache'}), 404
        
    try:
        first_row = 50
        last_row = first_row + num_rows
        
        with pd.option_context('display.max_columns', None, 
                             'display.width', None,
                             'display.max_colwidth', None):
            buffer = io.StringIO()
            df.iloc[first_row:last_row].to_string(buf=buffer, index=False)
            df_string = buffer.getvalue()
            buffer.close()
            
        return jsonify({'data': df_string})
    except Exception as e:
        return jsonify({
            'error': f'Error converting to string: {str(e)}',
            'data': df.iloc[first_row:last_row].to_string(index=False)
        })

# This returns the df columns as a JSON object
@app.route('/df_utils/df_columns', methods=['POST'])
def get_dataframe_columns():
    data = request.json
    df_id = data.get('df_id')
    
    if not df_id:
        return jsonify({'error': 'No df_id provided'}), 400
        
    df = df_cache.get(df_id)
    if df is None:
        return jsonify({'error': 'DataFrame not found in cache'}), 404
        
    try:
        columns_info = {
            'columns': df.columns.tolist(),
            'dtypes': {col: str(df[col].dtype) for col in df.columns}
        }
        return jsonify(columns_info)
    except Exception as e:
        return jsonify({'error': f'Error getting columns: {str(e)}'})
    
#### AUXILIARY FILE MANAGEMENT ENDPOINTS ####

@app.route('/file_utils/upload_aux_dataset', methods=['POST'])
def upload_aux_dataset_endpoint():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in request'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    try:
        # Ensure 'datasets' directory exists on the executor server
        executor_datasets_dir = 'datasets'
        os.makedirs(executor_datasets_dir, exist_ok=True)
        
        # Save the file to the executor's 'datasets' directory
        filepath_on_executor = os.path.join(executor_datasets_dir, file.filename)
        file.save(filepath_on_executor)
        
        log_info(f"Auxiliary dataset '{file.filename}' uploaded to '{filepath_on_executor}' on executor.")
        
        return jsonify({
            'message': 'Auxiliary dataset uploaded successfully to executor.',
            'filepath': filepath_on_executor # This path is on the executor server
        }), 200
        
    except Exception as e:
        log_info(f"Error uploading auxiliary dataset to executor: {str(e)}")
        return jsonify({'error': f'Error uploading auxiliary dataset to executor: {str(e)}'}), 500

@app.route('/file_utils/remove_aux_dataset', methods=['POST'])
def remove_aux_dataset_endpoint():
    data = request.json
    file_path_on_executor = data.get('file_path')

    if not file_path_on_executor:
        return jsonify({'error': 'file_path is required'}), 400

    try:
        if os.path.exists(file_path_on_executor):
            os.remove(file_path_on_executor)
            log_info(f"Auxiliary dataset '{file_path_on_executor}' removed from executor.")
            return jsonify({'message': 'Auxiliary dataset removed successfully from executor.'}), 200
        else:
            log_info(f"Auxiliary dataset '{file_path_on_executor}' not found on executor for removal.")
            return jsonify({'error': 'File not found on executor.'}), 404
            
    except Exception as e:
        log_info(f"Error removing auxiliary dataset from executor: {str(e)}")
        return jsonify({'error': f'Error removing auxiliary dataset from executor: {str(e)}'}), 500
    
#### AUXILIARY FILE UTILITY ENDPOINTS ####

@app.route('/file_utils/aux_datasets_to_string', methods=['POST'])
def aux_datasets_to_string_endpoint():
    data = request.json
    file_paths = data.get('file_paths')
    num_rows = data.get('num_rows', 5)

    if not isinstance(file_paths, list):
        return jsonify({'error': 'file_paths must be a list'}), 400
    if not file_paths:
        return jsonify({'data': "No auxiliary datasets provided."}) # Consistent with local

    log_info(f"Processing aux_datasets_to_string for {len(file_paths)} files, num_rows={num_rows}")
    
    results_list = []
    for i, path in enumerate(file_paths, 1):
        file_ext = os.path.splitext(path)[1].lower()
        try:
            if not os.path.exists(path):
                results_list.append(f"{i}.\nPath: {path}\nError: File not found")
                continue

            if file_ext == '.csv':
                df = pd.read_csv(path, nrows=num_rows)
            elif file_ext in ['.parquet', '.pq']:
                parquet_file = pq.ParquetFile(path)
                if parquet_file.num_row_groups > 0:
                    df = parquet_file.read_row_group(0, columns=parquet_file.schema.names).to_pandas()
                    if len(df) > num_rows:
                        df = df.iloc[:num_rows]
                else:
                    df = pd.DataFrame(columns=parquet_file.schema.names)
            else:
                results_list.append(f"{i}.\nPath: {path}\nError: Unsupported file format")
                continue
            
            buffer = io.StringIO()
            with pd.option_context('display.max_columns', None, 
                                  'display.width', None,
                                  'display.max_colwidth', None):
                df.to_string(buf=buffer, index=False)
            results_list.append(f"{i}.\nPath: {path}\nHead:\n{buffer.getvalue()}")
        except Exception as e:
            log_info(f"Error processing {path} for aux_datasets_to_string: {str(e)}")
            results_list.append(f"{i}.\nPath: {path}\nError: {str(e)}")
            
    return jsonify({'data': "\n\n".join(results_list)})

@app.route('/file_utils/get_aux_datasets_columns', methods=['POST'])
def get_aux_datasets_columns_endpoint():
    data = request.json
    file_paths = data.get('file_paths')

    if not isinstance(file_paths, list):
        return jsonify({'error': 'file_paths must be a list'}), 400
    if not file_paths:
        return jsonify({'data': "No auxiliary datasets provided."})

    log_info(f"Processing get_aux_datasets_columns for {len(file_paths)} files")

    results_list = []
    for i, path in enumerate(file_paths, 1):
        file_ext = os.path.splitext(path)[1].lower()
        try:
            if not os.path.exists(path):
                results_list.append(f"{i}.\nPath: {path}\nError: File not found")
                continue

            if file_ext == '.csv':
                with open(path, 'r', newline='', encoding='utf-8') as csvfile:
                    reader = csv.reader(csvfile)
                    columns = next(reader) 
            elif file_ext in ['.parquet', '.pq']:
                parquet_file = pq.ParquetFile(path)
                columns = parquet_file.schema.names
            else:
                results_list.append(f"{i}.\nPath: {path}\nError: Unsupported file format")
                continue
            
            columns_str = ", ".join(columns)
            results_list.append(f"{i}.\nPath: {path}\nColumns:\n{columns_str}")
        except StopIteration: # Handles empty CSV
            results_list.append(f"{i}.\nPath: {path}\nError: CSV file is empty or has no header")
        except Exception as e:
            log_info(f"Error processing {path} for get_aux_datasets_columns: {str(e)}")
            results_list.append(f"{i}.\nPath: {path}\nError: {str(e)}")
            
    return jsonify({'data': "\n\n".join(results_list)})

@app.route('/file_utils/compute_aux_dataset_sample', methods=['POST'])
def compute_aux_dataset_sample_endpoint():
    data = request.json
    file_paths = data.get('file_paths')
    num_rows = data.get('num_rows', 100)

    if not isinstance(file_paths, list):
        return jsonify({'error': 'file_paths must be a list'}), 400
    
    log_info(f"Processing compute_aux_dataset_sample for {len(file_paths)} files, num_rows={num_rows}")

    html_results = []
    if not file_paths:
        error_df = pd.DataFrame([{"Error": "No auxiliary dataset paths provided."}])
        html_results.append(error_df.to_html(classes='dataframe', border=0, index=False))
        return jsonify({'html_results': html_results})

    for path in file_paths:
        file_ext = os.path.splitext(path)[1].lower()
        try:
            if not os.path.exists(path):
                df = pd.DataFrame([{"Error": f"File not found: {os.path.basename(path)}"}])
            elif file_ext == '.csv':
                df = pd.read_csv(path, nrows=num_rows)
            elif file_ext in ['.parquet', '.pq']:
                parquet_file = pq.ParquetFile(path)
                if parquet_file.num_row_groups > 0:
                    first_row_group_reader = parquet_file.reader.read_row_group(0)
                    df = first_row_group_reader.to_pandas(use_threads=True)
                    if len(df) > num_rows:
                        df = df.head(num_rows)
                else:
                    df = pd.DataFrame([{"Info": f"Parquet file is empty: {os.path.basename(path)}"}])
            else:
                df = pd.DataFrame([{"Error": f"Unsupported file format: {file_ext}"}])
            
            html = df.to_html(classes='dataframe', border=0, index=False)
            html_results.append(html)
        except Exception as e:
            log_info(f"Error processing {path} for compute_aux_dataset_sample: {str(e)}")
            error_df = pd.DataFrame([{"Error": f"Failed to process {os.path.basename(path)}: {str(e)}"}])
            html_results.append(error_df.to_html(classes='dataframe', border=0, index=False))
            
    return jsonify({'html_results': html_results})

#### GENERATED DATASET DOWNLOAD ENDPOINT ####

@app.route('/download_generated_dataset', methods=['GET'])
def download_generated_dataset_endpoint():
    file_path_param = request.args.get('path')

    if not file_path_param:
        log_info("Download request for generated dataset missing 'path' parameter.")
        return jsonify({'error': "Missing 'path' query parameter."}), 400

    log_info(f"Attempting to serve generated dataset: {file_path_param}")
    
    # Get the absolute path of the executor's current working directory
    executor_base_dir = os.path.abspath(os.getcwd())
    
    # Construct the full absolute path to the requested file
    requested_file_abs = os.path.abspath(os.path.join(executor_base_dir, file_path_param))

    # Define the allowed base directory for generated datasets on the executor
    allowed_generated_prefix = os.path.abspath(os.path.join(executor_base_dir, "datasets", "generated"))

    if not requested_file_abs.startswith(allowed_generated_prefix):
        log_info(f"Access denied for generated dataset download: {file_path_param}. Resolved path {requested_file_abs} is outside allowed prefix {allowed_generated_prefix}.")
        return jsonify({'error': 'Access denied or invalid file path for generated dataset.'}), 403
    
    if not os.path.exists(requested_file_abs) or not os.path.isfile(requested_file_abs):
        log_info(f"Generated dataset file not found on executor: {requested_file_abs}")
        return jsonify({'error': 'File not found on executor.'}), 404

    try:
        # send_from_directory needs the directory and the filename separately.
        directory, filename = os.path.split(requested_file_abs)
        log_info(f"Serving generated dataset from executor: directory='{directory}', filename='{filename}'")
        return send_from_directory(directory, filename, as_attachment=True)
    except Exception as e:
        log_info(f"Error serving generated dataset {file_path_param} from executor: {str(e)}")
        return jsonify({'error': f'Error serving file from executor: {str(e)}'}), 500
    
#### HELPER FUNCTIONS ####

def serialize_df(df):
    buffer = io.BytesIO()
    pq.write_table(pa.Table.from_pandas(df), buffer)
    compressed = zlib.compress(buffer.getvalue())
    return base64.b64encode(compressed).decode('utf-8')

def deserialize_df(df_str):
    decompressed = zlib.decompress(base64.b64decode(df_str))
    buffer = io.BytesIO(decompressed)
    return pq.read_table(buffer).to_pandas()

def filter_exec_traceback(code, patch_code, full_traceback, exception_type, exception_value):
    # Calculate offset from monkey patch
    patch_offset = len(patch_code.split('\n')) - 1
    
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
    
    # Truncate to 1000 characters
    if len(filtered_traceback) > 1000:
        filtered_traceback = filtered_traceback[:1000] + f"\n[...] (truncated to 1000 characters)\n"

    return filtered_traceback

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)