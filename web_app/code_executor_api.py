from flask import Flask, request, jsonify
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

    log_info(f"Received execution request for DataFrame ID={df_id if df_id else 'None'}")

    # Only try to get DataFrame from cache if df_id is provided
    df = df_cache.get(df_id) if df_id is not None else None

    original_df = df.copy() if df is not None else None
    output_buffer = io.StringIO()
    plot_images = []
    generated_files = []

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

        return jsonify({
            'results': output_buffer.getvalue(),
            'error': None,
            'plot_images': plot_images
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
            'plot_images': []
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