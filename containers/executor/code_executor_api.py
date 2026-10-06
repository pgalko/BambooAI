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
import threading
import queue
from threading import Lock
from collections import OrderedDict
from datetime import datetime
import pandas as pd
import numpy as np
import tempfile
import csv
import sweatstack as ss

# Intervals imports
import requests
from fitparse import FitFile
import gzip
from concurrent.futures import ThreadPoolExecutor, as_completed, ProcessPoolExecutor
import uuid
import re
import hashlib
import shutil
from datetime import datetime, timedelta

# Set the number of CPU cores for pyarrow
pa.set_cpu_count(3)

intervals_jobs = {}

EXECUTOR_BUILD = '2026-10-06 v51 (DS in every run)'   # bumped with every image-bearing ship; reported by /health

app = Flask(__name__)

def log_info(message):
    """Helper function for consistent logging format"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[INFO] {timestamp} - {message}", flush=True)
    sys.stdout.flush()

def configure_pandas_optimizations():
    """Configure pandas performance optimizations"""
    
    # Enable numexpr
    try:
        import numexpr
        pd.set_option('compute.use_numexpr', True)
        numexpr.set_num_threads(3)
        log_info("Numexpr enabled (3 threads)")
    except ImportError:
        pass
    
    # Enable bottleneck
    try:
        import bottleneck
        pd.set_option('compute.use_bottleneck', True)
        log_info("Bottleneck enabled")
    except ImportError:
        pass
    
    # Enable Copy-on-Write (Pandas 2.0+)
    if hasattr(pd.options.mode, 'copy_on_write'):
        pd.options.mode.copy_on_write = True
        log_info("Copy-on-Write enabled")

def get_container_ram_gb():
    """Get actual container RAM limit from cgroups"""
    try:
        with open('/sys/fs/cgroup/memory.max', 'r') as f:
            mem_bytes = f.read().strip()
            if mem_bytes != 'max':  # 'max' means unlimited
                return int(int(mem_bytes) / (1024**3))
    except:
        pass
    
    # Fallback if can't read cgroup
    return 16

#### DATAFRAME CACHE ####

class DataFrameCache:
    def __init__(self, max_size=3):
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
                entry = self.cache.pop(df_id)
                self.cache[df_id] = entry  # Re-add the FULL entry
                
                # Update access tracking
                entry['access_count'] = entry.get('access_count', 0) + 1
                entry['last_accessed'] = datetime.now()
                
                log_info(f"Retrieved DataFrame from cache: ID={df_id}")
                return entry['dataframe']  # Return just the DataFrame
            log_info(f"Cache miss for DataFrame: ID={df_id}")
            return None
    
    def put(self, df_id, df, metadata=None):
        if df_id is None:
            return
        with self.lock:
            # Create cache entry with metadata
            entry = {
                'dataframe': df,
                'metadata': metadata or {},
                'cached_at': datetime.now(),
                'last_accessed': datetime.now(),
                'access_count': 0,
                'memory_mb': df.memory_usage(deep=True).sum() / (1024 * 1024)
            }
            
            if df_id in self.cache:
                # Preserve existing metadata if updating
                existing_entry = self.cache[df_id]
                entry['access_count'] = existing_entry.get('access_count', 0)
                entry['cached_at'] = existing_entry.get('cached_at', entry['cached_at'])
                # Merge metadata (new metadata takes precedence)
                if existing_entry.get('metadata'):
                    entry['metadata'] = {**existing_entry['metadata'], **(metadata or {})}
                self.cache.pop(df_id)
            elif len(self.cache) >= self.max_size:
                removed_id = next(iter(self.cache))
                self.cache.popitem(last=False)
                log_info(f"Evicted DataFrame from cache: ID={removed_id}")
            
            self.cache[df_id] = entry
            log_info(f"Stored DataFrame in cache: ID={df_id}, Size={entry['memory_mb']:.2f} MB")
    
    def get_all_metadata(self):
        """Return metadata for all cached DataFrames"""
        with self.lock:
            result = []
            for df_id, entry in self.cache.items():
                df = entry['dataframe']
                meta = {
                    'df_id': df_id,
                    'shape': list(df.shape),
                    'columns': df.columns.tolist()[:10],  # First 10 columns
                    'memory_mb': entry['memory_mb'],
                    'cached_at': entry['cached_at'].isoformat(),
                    'last_accessed': entry['last_accessed'].isoformat(),
                    'access_count': entry['access_count'],
                    **entry.get('metadata', {})  # Include custom metadata
                }
                result.append(meta)
            return result

# Call this function to configure pandas optimizations
configure_pandas_optimizations()            

# Initialize cache
df_cache = DataFrameCache()

# --- delv-e persistent kernel -------------------------------------------------
# The kernel is RELOCATED here, not reimplemented: kernel.py, executor.py,
# dataio.py is vendored from delv-e unchanged, and
# kernel_service only adds session management and a wire protocol. Crash
# isolation, checkpointing and transactional rollback stay inside
# PersistentKernel where they already work.
try:
    from kernel_service import kernel_bp, init_kernel_service

    def _evict_df(df_id):
        with df_cache.lock:
            return df_cache.cache.pop(df_id, None)

    init_kernel_service(get_df=df_cache.get, evict_df=_evict_df)
    app.register_blueprint(kernel_bp)
    KERNEL_SERVICE = {"available": True, "error": None}
    log_info("Persistent kernel service registered at /kernel")
except Exception as _kernel_err:
    # A container without the delv-e modules still serves normal mode, which is
    # the path that must never break. But the failure is reported on /health:
    # a Dockerfile that forgot a COPY otherwise produces a container that builds,
    # starts, passes its health check, and simply has no deep mode.
    KERNEL_SERVICE = {"available": False, "error": str(_kernel_err)}
    log_info(f"Kernel service unavailable ({_kernel_err}); /execute unaffected")
# ------------------------------------------------------------------------------

#### CACHE CONTENT INSPECTION ENDPOINTS ####

@app.route('/cache/inspect', methods=['GET'])
def inspect_cache():
    """
    Returns information about cached DataFrames, auxiliary datasets, and generated datasets
    """
    try:
        user_id = request.args.get('user_id', 'default')
        
        # Get cached DataFrames info
        cached_dataframes = df_cache.get_all_metadata()
        
        # Get auxiliary datasets info
        auxiliary_datasets = []
        user_datasets_dir = os.path.join('datasets', user_id)
        
        if os.path.exists(user_datasets_dir):
            for filename in os.listdir(user_datasets_dir):
                filepath = os.path.join(user_datasets_dir, filename)
                if os.path.isfile(filepath):
                    file_stat = os.stat(filepath)
                    
                    auxiliary_datasets.append({
                        'filename': filename,
                        'path': filepath,
                        'size_mb': file_stat.st_size / (1024 * 1024),
                        'created_at': datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
                        'modified_at': datetime.fromtimestamp(file_stat.st_mtime).isoformat()
                    })
        
        # Get generated datasets info
        generated_datasets = []
        generated_dir = os.path.join('datasets', user_id, 'generated')
        
        if os.path.exists(generated_dir):
            for filename in os.listdir(generated_dir):
                filepath = os.path.join(generated_dir, filename)
                if os.path.isfile(filepath):
                    file_stat = os.stat(filepath)
                    
                    generated_datasets.append({
                        'filename': filename,
                        'path': filepath,
                        'size_mb': file_stat.st_size / (1024 * 1024),
                        'created_at': datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
                        'modified_at': datetime.fromtimestamp(file_stat.st_mtime).isoformat()
                    })
        
        # Sort datasets by modified time (newest first)
        auxiliary_datasets.sort(key=lambda x: x['modified_at'], reverse=True)
        generated_datasets.sort(key=lambda x: x['modified_at'], reverse=True)
        
        # Calculate total cache memory usage
        total_cache_mb = sum(df['memory_mb'] for df in cached_dataframes)
        
        return jsonify({
            'cached_dataframes': cached_dataframes,
            'auxiliary_datasets': auxiliary_datasets,
            'generated_datasets': generated_datasets,  # Add this line
            'cache_stats': {
                'total_memory_mb': total_cache_mb,
                'max_cache_size': df_cache.max_size,
                'current_cache_size': len(cached_dataframes)
            }
        }), 200
        
    except Exception as e:
        log_info(f"Error inspecting cache: {str(e)}")
        return jsonify({'error': f'Failed to inspect cache: {str(e)}'}), 500
    
@app.route('/cache/preview/<df_id>', methods=['GET'])
def preview_cached_dataframe(df_id):
    """
    Get a preview of a specific cached DataFrame
    """
    try:
        df = df_cache.get(df_id)
        if df is None:
            return jsonify({'error': 'DataFrame not found in cache'}), 404
        
        # Get metadata for this specific df_id
        all_metadata = df_cache.get_all_metadata()
        df_metadata = next((m for m in all_metadata if m['df_id'] == df_id), {})
        
        # Basic info only - fast and lean
        preview = {
            'df_id': df_id,
            'metadata': df_metadata,
            'shape': list(df.shape),
            'columns': df.columns.tolist(),
            'dtypes': {col: str(df[col].dtype) for col in df.columns}
        }
        
        return jsonify(preview), 200
        
    except Exception as e:
        log_info(f"Error previewing DataFrame {df_id}: {str(e)}")
        return jsonify({'error': f'Failed to preview DataFrame: {str(e)}'}), 500

@app.route('/cache/preview_aux', methods=['POST'])
def preview_aux_dataset():
    """
    Get a preview of an auxiliary dataset file
    """
    try:
        data = request.json
        file_path = data.get('file_path')
        user_id = data.get('user_id', 'default')
        
        if not file_path:
            return jsonify({'error': 'file_path is required'}), 400
        
        # Security validation
        executor_base_dir = os.path.abspath(os.getcwd())
        allowed_user_dir = os.path.abspath(os.path.join(executor_base_dir, 'datasets', user_id))
        requested_file_abs = os.path.abspath(file_path)
        
        if not requested_file_abs.startswith(allowed_user_dir):
            return jsonify({'error': 'Access denied - invalid file path'}), 403
        
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found'}), 404
        
        file_ext = os.path.splitext(file_path)[1].lower()
        
        # Get file stats
        file_stat = os.stat(file_path)
        
        preview = {
            'path': file_path,
            'filename': os.path.basename(file_path),
            'size_mb': file_stat.st_size / (1024 * 1024),
            'created_at': datetime.fromtimestamp(file_stat.st_ctime).isoformat(),
            'modified_at': datetime.fromtimestamp(file_stat.st_mtime).isoformat()
        }
        
        # Add file-specific info based on type
        if file_ext == '.csv':
            # Just get shape and columns for CSV
            with open(file_path, 'r', newline='', encoding='utf-8') as f:
                reader = csv.reader(f)
                columns = next(reader, [])
                row_count = sum(1 for _ in reader) + 1  # +1 for header
            
            preview['shape'] = [row_count, len(columns)]
            preview['columns'] = columns
            
        elif file_ext in ['.parquet', '.pq']:
            # Get schema info for Parquet
            parquet_file = pq.ParquetFile(file_path)
            preview['shape'] = [parquet_file.metadata.num_rows, len(parquet_file.schema)]
            preview['columns'] = parquet_file.schema.names

        elif file_ext == '.json':
            df_temp = pd.read_json(file_path)
            preview['shape'] = list(df_temp.shape)
            preview['columns'] = df_temp.columns.tolist()
            del df_temp

        elif file_ext in ['.xlsx', '.xls']:
            df_temp = pd.read_excel(file_path, engine='openpyxl')
            preview['shape'] = list(df_temp.shape)
            preview['columns'] = df_temp.columns.tolist()
            del df_temp

        elif file_ext in ['.txt', '.tsv']:
            # a tab-separated table when it reads as one; otherwise the file's basic information stands (2026-10-06)
            try:
                df_temp = pd.read_csv(file_path, sep='\t')
                if df_temp.shape[1] > 1:
                    preview['shape'] = list(df_temp.shape)
                    preview['columns'] = df_temp.columns.tolist()
                del df_temp
            except Exception:
                pass
        
        return jsonify(preview), 200
        
    except Exception as e:
        log_info(f"Error previewing aux dataset: {str(e)}")
        return jsonify({'error': f'Failed to preview aux dataset: {str(e)}'}), 500

#### CODE EXECUTION ENDPOINTS ####

@app.route('/execute', methods=['POST'])
def execute_code():
    data = request.json
    code = data.get('code')
    df_id = data.get('df_id')
    # Default TRUE: quick mode relies on the write-back, and an older
    # client that does not send the flag must keep working.
    persist_df = bool(data.get('persist_df', True))  # Can be None
    patch_code = data.get('patch_code')
    plots_dir = data.get('plots_dir')
    plot_format = data.get('plot_format')
    generated_datasets_path = data.get('generated_datasets_path', [])
    timeout_seconds = data.get('timeout', 300)  # Default 5 minutes

    log_info(f"Received execution request for DataFrame ID={df_id if df_id else 'None'}")

    # Ensure the plots directory exists
    if plots_dir and not os.path.exists(plots_dir):
        try:
            os.makedirs(plots_dir)
        except Exception as e:
            log_info(f"Error creating plots directory {plots_dir}: {str(e)}")

    # Only try to get DataFrame from cache if df_id is provided
    df = df_cache.get(df_id) if df_id is not None else None

    original_df = df.copy() if df is not None else None
    output_buffer = io.StringIO()
    plot_images = []
    generated_files = []
    
    # Track existing files before execution
    existing_files = set()
    if generated_datasets_path is not None:
        # Ensure that the directory exists
        if not os.path.isdir(generated_datasets_path):
            try:
                os.makedirs(generated_datasets_path)
            except Exception as e:
                log_info(f"Error creating directory {generated_datasets_path}: {str(e)}")
        else:
            # Capture existing files with their modification times
            existing_files = {
                os.path.join(generated_datasets_path, f): os.path.getmtime(os.path.join(generated_datasets_path, f))
                for f in os.listdir(generated_datasets_path)
                if os.path.isfile(os.path.join(generated_datasets_path, f))
            }

    try:
        plt.close('all')
        
        # Execute with timeout using threading
        result_queue = queue.Queue()
        exception_queue = queue.Queue()
        
        def execute_target():
            try:
                # Create a separate output buffer for the thread
                thread_output_buffer = io.StringIO()
                
                with redirect_stdout(thread_output_buffer):
                    local_vars = {
                        'df': df,
                        '_plots_dir': plots_dir,
                        '_generated_files': generated_files,
                        '_generated_dir': generated_datasets_path      # the replay stub's DS.save writes here (2026-10-06)
                    }
                    
                    log_info(f"Executing code")
                    exec(patch_code + code, local_vars)
                    
                    # Put results in queue
                    local_vars['_output'] = thread_output_buffer.getvalue()
                    result_queue.put(local_vars)
                    
            except Exception as e:
                exception_queue.put(e)
        
        # Start execution thread as daemon
        thread = threading.Thread(target=execute_target, daemon=True)
        thread.start()
        thread.join(timeout_seconds)
        
        # Check if thread is still alive (timeout occurred)
        if thread.is_alive():
            log_info(f"Code execution timed out after {timeout_seconds} seconds")
            
            # Restore original DataFrame state immediately
            if df_id is not None and original_df is not None:
                df_cache.put(df_id, original_df)
            
            # Clean up matplotlib state
            plt.close('all')
            
            # The daemon thread will be abandoned and eventually cleaned up
            # Since it's a daemon thread, it won't prevent the process from functioning
            
            return jsonify({
                'results': None,
                'error': f'TIMEOUT: Code execution exceeded {timeout_seconds} seconds. '
                        f'Available resources: {get_container_ram_gb()}GB RAM, ~0.4-4 CPU cores (varies with load), '
                        f'single-threaded execution recommended. Consider optimizing algorithms, '
                        f'reducing data size, or using chunked processing.',
                'plot_images': [],
                'generated_datasets': [],
                'timeout': True
            })
        
        # Check for exceptions from the execution thread
        if not exception_queue.empty():
            raise exception_queue.get()
        
        # Get results from execution thread
        if not result_queue.empty():
            local_vars = result_queue.get()
            df = local_vars['df']
            generated_files = local_vars['_generated_files']
            # Transfer output from thread buffer to main buffer
            output_buffer.write(local_vars.get('_output', ''))
        else:
            raise RuntimeError("Execution completed but no results returned")
        
        # Update cache with modified DataFrame on success.
        #
        # `persist_df` lets the caller decline. The write-back exists so a
        # follow-up question can build on what the last script did, which fits
        # a short quick-mode script. It does NOT fit a consolidated deep-mode
        # script: that one is told the dataframe arrives exactly as the user
        # uploaded it, so silently persisting its derived columns contradicts
        # its own contract - and a script that binned anything left a
        # categorical in the cache that broke every later preview.
        if df_id is not None and persist_df:
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

        # Find only newly generated datasets
        generated_datasets = []
        if generated_datasets_path is not None and os.path.isdir(generated_datasets_path):
            for filename in os.listdir(generated_datasets_path):
                file_path = os.path.join(generated_datasets_path, filename)
                if os.path.isfile(file_path):
                    # Check if file is new or modified
                    if file_path not in existing_files:
                        # New file
                        generated_datasets.append(file_path)
                        log_info(f"New generated dataset: {file_path}")
                    else:
                        # Check if file was modified
                        current_mtime = os.path.getmtime(file_path)
                        if current_mtime > existing_files[file_path]:
                            generated_datasets.append(file_path)
                            log_info(f"Modified generated dataset: {file_path}")

        return jsonify({
            'results': output_buffer.getvalue(),
            'error': None,
            'plot_images': plot_images,
            'generated_datasets': generated_datasets
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
        temp_path = os.path.join(tempfile.gettempdir(), f"{df_id}_{file.filename}")
        file.save(temp_path)
        
        # Load into DataFrame based on file type
        if file.filename.endswith('.csv'):
            df = pd.read_csv(temp_path, engine='pyarrow')
        elif file.filename.endswith('.parquet'):
            df = pd.read_parquet(temp_path, engine='pyarrow')
        elif file.filename.endswith('.json'):
            df = pd.read_json(temp_path)
        elif file.filename.endswith('.xlsx'):
            df = pd.read_excel(temp_path, engine='openpyxl')
        else:
            return jsonify({'error': 'Unsupported file type'}), 400
            
        # Clean up temp file
        os.remove(temp_path)

        # Log the memory usage before caching
        memory_mb = df.memory_usage(deep=True).sum() / (1024 * 1024)
        log_info(f"Loaded file {file.filename}: Shape={df.shape}, Memory={memory_mb:.2f} MB")

        # Add descriptive metadata when caching
        metadata = {
            'source': 'csv',
            'original_filename': file.filename,
            'uploaded_at': datetime.now().isoformat()
        }
        
        # Store in cache
        df_cache.put(df_id, df, metadata)
        
        return jsonify({
            'message': 'Dataset uploaded and cached successfully',
            'df_id': df_id,
            'shape': df.shape,
            'columns': df.columns.tolist()
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

#### DATAFRAME UTILITY ENDPOINTS ####

@app.route('/cache/remove_primary', methods=['POST'])
def remove_primary_from_cache():
    """Remove a primary dataset from cache"""
    data = request.json
    df_id = data.get('df_id')
    
    if not df_id:
        return jsonify({'error': 'df_id is required'}), 400
    
    # Remove from cache if exists
    with df_cache.lock:
        if df_id in df_cache.cache:
            df_cache.cache.pop(df_id)
            log_info(f"Removed DataFrame {df_id} from cache")
            return jsonify({'message': 'DataFrame removed from cache'}), 200
        else:
            return jsonify({'error': 'DataFrame not found in cache'}), 404

# This endpoint computes the index for the given DataFrame

def page_frame(df, offset=0, limit=50, order_by=None, ascending=True):
    """One page of a dataframe for the Data tab: rows as JSON-safe lists, the
    columns with their dtypes, the total row count. Sorting happens here, on the
    whole frame, so the last row of a sorted view costs the same as the first.
    The browser never holds more than one page."""
    import math
    import numpy as _np
    import pandas as _pd
    total = int(len(df))
    limit = max(1, min(int(limit or 50), 500))
    offset = max(0, min(int(offset or 0), max(0, total - 1)))
    frame = df
    if order_by and order_by in df.columns:
        try:
            frame = df.sort_values(order_by, ascending=bool(ascending), kind="mergesort", na_position="last")
        except Exception:                                   # noqa: BLE001 - an unsortable column: unsorted
            frame = df
    page = frame.iloc[offset:offset + limit]
    cols = [str(c) for c in df.columns]
    dtypes = [str(df[c].dtype) for c in df.columns]
    rows = []
    for rec in page.itertuples(index=False, name=None):
        out = []
        for v in rec:
            if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
                out.append(None)
            elif isinstance(v, (_np.integer,)):
                out.append(int(v))
            elif isinstance(v, (_np.floating,)):
                out.append(None if (_np.isnan(v) or _np.isinf(v)) else float(v))
            elif isinstance(v, (_np.bool_, bool)):
                out.append(bool(v))
            elif isinstance(v, (_pd.Timestamp,)):
                out.append(None if _pd.isna(v) else v.isoformat(sep=" "))
            elif hasattr(v, "isoformat"):
                out.append(v.isoformat())
            else:
                try:
                    if _pd.isna(v):
                        out.append(None); continue
                except (TypeError, ValueError):
                    pass
                out.append(v if isinstance(v, (int, float, str)) else str(v))
        rows.append(out)
    return {"columns": cols, "dtypes": dtypes, "rows": rows, "offset": offset, "limit": limit, "total": total,
            "order_by": order_by if order_by in cols else None, "ascending": bool(ascending)}


_AUX_FRAMES = {}     # path -> (mtime, frame)

@app.route('/aux_page', methods=['POST'])
def aux_page_route():
    """One page of an auxiliary dataset file for the Data tab's grid (2026-09-08)."""
    data = request.get_json(silent=True) or {}
    path = data.get('path')
    if not path or not os.path.exists(path):
        return jsonify({'error': 'file not found'}), 404
    try:
        mtime = os.path.getmtime(path)
        cached = _AUX_FRAMES.get(path)
        if cached is None or cached[0] != mtime:
            ext = os.path.splitext(path)[1].lower()
            if ext == '.csv':
                frame = pd.read_csv(path)
            elif ext in ('.parquet', '.pq'):
                frame = pd.read_parquet(path)
            elif ext == '.json':
                frame = pd.read_json(path)
            elif ext in ('.xlsx', '.xls'):
                frame = pd.read_excel(path)
            else:
                return jsonify({'error': f'unsupported file type {ext}'}), 400
            if len(_AUX_FRAMES) > 8:
                _AUX_FRAMES.clear()
            _AUX_FRAMES[path] = (mtime, frame); cached = _AUX_FRAMES[path]
        page = page_frame(cached[1], int(data.get('offset', 0)), int(data.get('limit', 50)), data.get('order_by') or None, bool(data.get('ascending', True)))
        page['df_id'] = 'aux:' + path
        return jsonify(page)
    except Exception as exc:                                # noqa: BLE001
        return jsonify({'error': str(exc)}), 500

@app.route('/dataframe_page', methods=['POST'])
def dataframe_page_endpoint():
    """One page of the cached dataframe for the Data tab (2026-09-07)."""
    data = request.json or {}
    df_id = data.get('df_id')
    if not df_id:
        return jsonify({'error': 'No df_id provided'}), 400
    df = df_cache.get(df_id)
    if df is None:
        return jsonify({'error': 'DataFrame not found in cache'}), 404
    try:
        page = page_frame(df, data.get('offset', 0), data.get('limit', 50), data.get('order_by'), data.get('ascending', True))
        return jsonify(page)
    except Exception as exc:                                # noqa: BLE001
        return jsonify({'error': str(exc)}), 500


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

        # .replace() RAISES on a categorical column: the replacement values are
        # not among its categories. A script that binned anything (pd.cut,
        # astype("category")) and had its frame written back to the cache made
        # every later preview fail here - the frame was always found, always
        # 200, and the client saw only 'error'. Cast those columns to object
        # first; this is a display sample, so the dtype does not matter.
        cat_cols = [c for c in result_df.columns
                    if str(result_df[c].dtype) == "category"]
        if cat_cols:
            result_df = result_df.copy()
            for c in cat_cols:
                result_df[c] = result_df[c].astype(object)

        try:
            result_df = result_df.replace({np.nan: None, np.inf: None, -np.inf: None})
        except Exception as exc:                            # noqa: BLE001
            # A sample the caller can render beats no sample at all.
            log_info(f"compute_df_sample: replace() failed ({exc}); "
                     f"sending the rows unreplaced")

        return jsonify({
            'data': result_df.to_dict(orient='records'),
            'columns': result_df.columns.tolist()
        })
        
    except Exception as e:
        # No 'data' here. The old handler returned the error AND the entire
        # dataframe, so a failure shipped megabytes the client discarded
        # unread - it checks for 'error' first and returns None.
        log_info(f"compute_df_sample failed for {df_id}: {e}")
        return jsonify({'error': f'Error computing index: {str(e)}'}), 500

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
    
# This endpoint returns the DataFrame summary as a JSON object
@app.route('/df_utils/df_summary', methods=['POST'])
def dataframe_summary_endpoint():
    data = request.json
    df_id = data.get('df_id')
    
    if not df_id:
        return jsonify({'error': 'No df_id provided'}), 400
        
    df = df_cache.get(df_id)
    if df is None:
        return jsonify({'error': 'DataFrame not found in cache'}), 404
        
    try:
        result = []
        
        # Define ID keywords once
        id_keywords = ['_id', 'id_', '_code', 'code_', '_index', 'index_', '_key', 'key_']
        
        # Dataset overview
        result.append(f"DATASET: {len(df)} rows x {len(df.columns)} columns")
        result.append("---")
        
        for col in df.columns:
            missing = df[col].isnull().sum()
            missing_pct = (missing / len(df)) * 100
            missing_info = f" missing={missing}({missing_pct:.1f}%)" if missing > 0 else ""
            
            # Check if this column should be treated as an identifier
            is_identifier = any(keyword in col.lower() for keyword in id_keywords)
            
            # --- Datetime detection (native) ---
            if pd.api.types.is_datetime64_any_dtype(df[col]):
                vals = df[col].dropna()
                if len(vals) == 0:
                    result.append(f"{col}: datetime all_missing")
                    continue
                date_min = vals.min()
                date_max = vals.max()
                span = date_max - date_min
                if len(vals) > 1:
                    diffs = vals.sort_values().diff().dropna()
                    median_diff = diffs.median()
                    granularity = str(median_diff)
                else:
                    granularity = "single value"
                result.append(f"{col}: datetime(n={len(vals)}) range=[{date_min} to {date_max}] "
                             f"span={span} granularity~{granularity}{missing_info}")
                continue
            
            # --- Numeric columns ---
            if pd.api.types.is_numeric_dtype(df[col]):
                vals = df[col].dropna()
                if len(vals) == 0:
                    result.append(f"{col}: numeric all_missing")
                    continue
                
                unique_count = vals.nunique()
                
                if is_identifier:
                    if unique_count > 100:
                        result.append(f"{col}: identifier(n={len(vals)}) unique={unique_count} "
                                    f"range={vals.min():.0f}-{vals.max():.0f}{missing_info}")
                    elif unique_count <= 10:
                        value_counts = vals.value_counts()
                        values_str = ', '.join([f"{int(v) if v == int(v) else v}({c})" 
                                               for v, c in value_counts.items()])
                        result.append(f"{col}: identifier(n={len(vals)}) unique={unique_count} "
                                    f"values=[{values_str}]{missing_info}")
                    else:
                        value_counts = vals.value_counts().head(5)
                        values_str = ', '.join([f"{int(v) if v == int(v) else v}({c})" 
                                               for v, c in value_counts.items()])
                        result.append(f"{col}: identifier(n={len(vals)}) unique={unique_count} "
                                    f"top_values=[{values_str}...]{missing_info}")
                
                elif unique_count <= 10:
                    # Low-cardinality numeric — treat as discrete/ordinal
                    value_counts = vals.value_counts().sort_index()
                    values_str = ', '.join([f"{int(v) if v == int(v) else v}({c})" 
                                           for v, c in value_counts.items()])
                    result.append(f"{col}: numeric_discrete(n={len(vals)}) unique={unique_count} "
                                f"values=[{values_str}]{missing_info}")
                
                else:
                    # Regular continuous numeric column
                    mean_val = vals.mean()
                    median_val = vals.median()
                    
                    # Zero-inflation check
                    zero_count = (vals == 0).sum()
                    zero_pct = (zero_count / len(vals)) * 100
                    zero_info = ""
                    nonzero_info = ""
                    if zero_pct > 5:
                        nonzero_vals = vals[vals != 0]
                        if len(nonzero_vals) > 0:
                            zero_info = f" zeros={zero_count}({zero_pct:.1f}%)"
                            nonzero_info = f" nonzero_mean={nonzero_vals.mean():.1f}"
                    
                    # Skew signal
                    skew_info = ""
                    if median_val != 0:
                        skew_ratio = abs(mean_val - median_val) / abs(median_val)
                        if skew_ratio > 0.15:
                            skew_info = " SKEWED"
                    
                    result.append(f"{col}: numeric(n={len(vals)}) range={vals.min():.1f}-{vals.max():.1f} "
                                f"mean={mean_val:.1f} median={median_val:.1f}"
                                f"{zero_info}{nonzero_info}{skew_info}{missing_info}")
            
            else:
                # --- Categorical/string columns ---
                unique_count = df[col].nunique()
                non_null = df[col].dropna()
                
                if is_identifier:
                    if unique_count > 100:
                        result.append(f"{col}: identifier(n={df[col].count()}) unique={unique_count}{missing_info}")
                    elif unique_count <= 10:
                        value_counts = df[col].value_counts()
                        values_str = ', '.join([f"{v}({c})" for v, c in value_counts.items()])
                        result.append(f"{col}: identifier(n={df[col].count()}) unique={unique_count} "
                                    f"values=[{values_str}]{missing_info}")
                    else:
                        value_counts = df[col].value_counts().head(5)
                        values_str = ', '.join([f"{v}({c})" for v, c in value_counts.items()])
                        result.append(f"{col}: identifier(n={df[col].count()}) unique={unique_count} "
                                    f"top_values=[{values_str}...]{missing_info}")
                else:
                    if unique_count <= 10:
                        # Show ALL values with counts — first/last not needed
                        value_counts = df[col].value_counts()
                        values_str = ', '.join([f"{v}({c})" for v, c in value_counts.items()])
                        samples = f" values=[{values_str}]"
                    elif unique_count <= 100:
                        # Show top 5 with counts + first/last for boundary context
                        value_counts = df[col].value_counts().head(5)
                        values_str = ', '.join([f"{v}({c})" for v, c in value_counts.items()])
                        first_val = non_null.iloc[0] if len(non_null) > 0 else 'N/A'
                        last_val = non_null.iloc[-1] if len(non_null) > 0 else 'N/A'
                        samples = f" top_values=[{values_str}...] first={first_val} last={last_val}"
                    else:
                        # High cardinality - top 3 with counts + first/last
                        value_counts = df[col].value_counts().head(3)
                        values_str = ', '.join([f"{v}({c})" for v, c in value_counts.items()])
                        first_val = non_null.iloc[0] if len(non_null) > 0 else 'N/A'
                        last_val = non_null.iloc[-1] if len(non_null) > 0 else 'N/A'
                        samples = f" top_values=[{values_str}...] first={first_val} last={last_val} (high cardinality)"
                    
                    result.append(f"{col}: categorical(n={df[col].count()}) unique={unique_count}{samples}{missing_info}")
        
        summary_string = '\n'.join(result)
        return jsonify({'data': summary_string})
        
    except Exception as e:
        log_info(f"Error generating DataFrame summary: {str(e)}")
        return jsonify({'error': f'Error generating summary: {str(e)}'})

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
    user_id = request.form.get('user_id', 'default')
    
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    try:
        # Create user-specific directory
        executor_datasets_dir = os.path.join('datasets', user_id)
        os.makedirs(executor_datasets_dir, exist_ok=True)
        
        filepath_on_executor = os.path.join(executor_datasets_dir, file.filename)
        file.save(filepath_on_executor)
        
        return jsonify({
            'message': 'Auxiliary dataset uploaded successfully to executor.',
            'filepath': filepath_on_executor
        }), 200
        
    except Exception as e:
        log_info(f"Error uploading auxiliary dataset to executor: {str(e)}")
        return jsonify({'error': f'Error uploading auxiliary dataset to executor: {str(e)}'}), 500

@app.route('/file_utils/remove_aux_dataset', methods=['POST'])
def remove_aux_dataset_endpoint():
    data = request.json
    file_path_on_executor = data.get('file_path')
    user_id = data.get('user_id', 'default')

    if not file_path_on_executor:
        return jsonify({'error': 'file_path is required'}), 400

    # Add security validation
    executor_base_dir = os.path.abspath(os.getcwd())
    allowed_user_dir = os.path.abspath(os.path.join(executor_base_dir, 'datasets', user_id))
    requested_file_abs = os.path.abspath(file_path_on_executor)
    
    if not requested_file_abs.startswith(allowed_user_dir):
        log_info(f"Security: User {user_id} denied access to {file_path_on_executor}")
        return jsonify({'error': 'Access denied - invalid file path'}), 403

    try:
        if os.path.exists(file_path_on_executor):
            os.remove(file_path_on_executor)
            log_info(f"Auxiliary dataset '{file_path_on_executor}' removed from executor.")
            return jsonify({'message': 'Auxiliary dataset removed successfully from executor.'}), 200
        else:
            return jsonify({'error': 'File not found on executor.'}), 404
            
    except Exception as e:
        log_info(f"Error removing auxiliary dataset from executor: {str(e)}")
        return jsonify({'error': f'Error removing auxiliary dataset from executor: {str(e)}'}), 500
    
#### DOCUMENT FILE ENDPOINTS ####
# A thread's documents (docs/DOCUMENTS_DESIGN.md): the app mirrors text.json, text.md and the tables of
# each document into datasets/<user>/documents/<D-id>/ at every chain start and before a replay, by content.
# The container forgets between restarts; these three routes are how it is told. Never the original file.

_DOC_PATH_RE = re.compile(r'^D\d+/(text\.json|text\.md|tables/\d+\.csv)$')
_USER_RE = re.compile(r'^[\w.@-]{1,120}$')


def _documents_root(user_id):
    return os.path.join('datasets', user_id, 'documents')


def _sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


@app.route('/file_utils/documents', methods=['GET'])
def documents_inventory_endpoint():
    """{relative path: sha256} of the documents folder, so the app sends only what is missing or changed."""
    user_id = request.args.get('user_id', 'default')
    if not _USER_RE.match(user_id):
        return jsonify({'error': 'invalid user_id'}), 400
    root = _documents_root(user_id)
    out = {}
    if os.path.isdir(root):
        for dirpath, _, files in os.walk(root):
            for name in files:
                p = os.path.join(dirpath, name)
                out[os.path.relpath(p, root).replace(os.sep, '/')] = _sha256(p)
    return jsonify({'files': out}), 200


@app.route('/file_utils/upload_document', methods=['POST'])
def upload_document_endpoint():
    """One file of a document, at its relative path (D3/text.md, D3/tables/2.csv)."""
    if 'file' not in request.files:
        return jsonify({'error': 'No file part in request'}), 400
    user_id = request.form.get('user_id', 'default')
    rel = request.form.get('path', '')
    if not _USER_RE.match(user_id):
        return jsonify({'error': 'invalid user_id'}), 400
    if not _DOC_PATH_RE.match(rel):
        return jsonify({'error': 'path must be D<n>/text.json, D<n>/text.md or D<n>/tables/<n>.csv'}), 400
    try:
        dst = os.path.join(_documents_root(user_id), *rel.split('/'))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        request.files['file'].save(dst)
        return jsonify({'message': 'stored', 'path': rel, 'sha256': _sha256(dst)}), 200
    except Exception as e:
        log_info(f"Error storing document file {rel}: {str(e)}")
        return jsonify({'error': f'Error storing document file: {str(e)}'}), 500


@app.route('/file_utils/remove_document', methods=['POST'])
def remove_document_endpoint():
    """Remove one file (D3/text.md) or a whole document (D3) from the documents folder."""
    data = request.json or {}
    user_id = data.get('user_id', 'default')
    rel = data.get('path', '')
    if not _USER_RE.match(user_id):
        return jsonify({'error': 'invalid user_id'}), 400
    if not (_DOC_PATH_RE.match(rel) or re.match(r'^D\d+$', rel)):
        return jsonify({'error': 'path must be a document id or one of its files'}), 400
    target = os.path.join(_documents_root(user_id), *rel.split('/'))
    try:
        if os.path.isdir(target):
            shutil.rmtree(target)
        elif os.path.exists(target):
            os.remove(target)
            parent = os.path.dirname(target)
            while parent != _documents_root(user_id) and os.path.isdir(parent) and not os.listdir(parent):
                os.rmdir(parent); parent = os.path.dirname(parent)
        else:
            return jsonify({'message': 'not present', 'path': rel}), 200
        return jsonify({'message': 'removed', 'path': rel}), 200
    except Exception as e:
        log_info(f"Error removing document path {rel}: {str(e)}")
        return jsonify({'error': f'Error removing document path: {str(e)}'}), 500

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
            elif file_ext == '.json':
                df = pd.read_json(path)
                if len(df) > num_rows:
                    df = df.head(num_rows)
            elif file_ext in ['.xlsx', '.xls']:
                df = pd.read_excel(path, engine='openpyxl')
                if len(df) > num_rows:
                    df = df.head(num_rows)
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
            elif file_ext == '.json':
                # Read just enough to get columns
                df_temp = pd.read_json(path)
                columns = df_temp.columns.tolist()
                del df_temp
            elif file_ext in ['.xlsx', '.xls']:
                df_temp = pd.read_excel(path, engine='openpyxl', nrows=0)
                columns = df_temp.columns.tolist()
                del df_temp
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
            elif file_ext == '.json':
                df = pd.read_json(path)
                if len(df) > num_rows:
                    df = df.head(num_rows)
            elif file_ext in ['.xlsx', '.xls']:
                df = pd.read_excel(path, engine='openpyxl', nrows=num_rows)
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
    user_id = request.args.get('user_id')

    if not file_path_param:
        log_info("Download request for generated dataset missing 'path' parameter.")
        return jsonify({'error': "Missing 'path' query parameter."}), 400
    
    if not user_id:
        log_info("Download request for generated dataset missing 'user_id' parameter.")
        return jsonify({'error': "Missing 'user_id' query parameter."}), 400

    log_info(f"Attempting to serve generated dataset: {file_path_param}")

    # Get the absolute path of the executor's current working directory
    executor_base_dir = os.path.abspath(os.getcwd())
    
    # Construct the full absolute path to the requested file
    requested_file_abs = os.path.abspath(os.path.join(executor_base_dir, file_path_param))

    # Define the allowed base directory for generated datasets on the executor
    allowed_generated_prefix = os.path.abspath(os.path.join(executor_base_dir, "datasets", user_id, "generated"))

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
    
#### INTEGRATIONS ####

### SweatStack

@app.route('/fetch_sweatstack_data', methods=['POST'])
def fetch_sweatstack_data():
    """Fetch SweatStack data directly and cache it"""
    data = request.json
    
    access_token = data.get('access_token')
    df_id = data.get('df_id')
    fetch_params = data.get('fetch_params')
    
    if not all([access_token, df_id, fetch_params]):
        return jsonify({'error': 'Missing required parameters'}), 400
    
    try:
        log_info(f"Fetching SweatStack data for df_id: {df_id}")
        
        # Create SweatStack client
        sweatstack_client = ss.Client(api_key=access_token)
        
        # Extract parameters
        selected_sports = fetch_params['sports']
        selected_metrics = fetch_params['metrics'] 
        selected_users = fetch_params['users']
        start_date = datetime.strptime(fetch_params['start_date'], '%Y-%m-%d')
        end_date = datetime.strptime(fetch_params['end_date'], '%Y-%m-%d')
        
        # Fetch data for all users
        all_dfs = []
        for user_id in selected_users:
            try:
                delegated_client = sweatstack_client.delegated_client(user_id)
                df = delegated_client.get_longitudinal_data(
                    start=start_date,
                    end=end_date,
                    sports=selected_sports,
                    metrics=selected_metrics,
                )
                df['athlete_id'] = user_id
                user_info = delegated_client.get_user(user_id)
                df['athlete_name'] = user_info.display_name
                all_dfs.append(df)
            except Exception as e:
                log_info(f'Error loading data for user {user_id}: {str(e)}')
                continue
        
        if not all_dfs:
            return jsonify({'error': 'No data could be loaded'}), 400
            
        # Combine and transform data
        combined_df = pd.concat(all_dfs, ignore_index=False)
        transformed_df = transform_sweatstack_longitudinal_data(combined_df)

        # Add descriptive metadata when caching
        metadata = {
            'source': 'sweatstack',
            'sports': selected_sports,
            'metrics': selected_metrics,
            'date_range': f"{fetch_params['start_date']} to {fetch_params['end_date']}",
            'athletes': len(selected_users)
        }
        
        # Cache the DataFrame
        df_cache.put(df_id, transformed_df, metadata)
        
        log_info(f"SweatStack data cached successfully: {transformed_df.shape}")
        
        return jsonify({
            'message': 'SweatStack data fetched and cached successfully',
            'df_id': df_id,
            'shape': list(transformed_df.shape),
            'columns': transformed_df.columns.tolist()
        }), 200
        
    except Exception as e:
        log_info(f"Error fetching SweatStack data: {str(e)}")
        return jsonify({'error': f'Failed to fetch SweatStack data: {str(e)}'}), 500

def transform_sweatstack_longitudinal_data(df):
    """Transform SweatStack longitudinal data to the required format"""
    # 1. Convert timestamp column to local time and rename to "datetime"
    df["datetime"] = pd.to_datetime(df.index).tz_localize(None)  # Remove timezone info to convert to local time
    df = df.reset_index(drop=True)  # Remove the original timestamp index

    # 2. Convert activity_id column to integers (incrementing from oldest to newest activity per athlete)
    df = df.sort_values('datetime')

    # Check if we have athlete_id column (multi-user scenario)
    if 'athlete_id' in df.columns:
        # Create unique activity IDs per athlete
        unique_activities = df.groupby(['athlete_id', 'activity_id'])['datetime'].min().sort_values()
        activity_mapping = {}

        for athlete_id in df['athlete_id'].unique():
            athlete_activities = unique_activities[athlete_id]
            for new_id, (old_id, _) in enumerate(athlete_activities.items(), 1):
                activity_mapping[(athlete_id, old_id)] = new_id

        # Apply mapping using both athlete_id and activity_id
        df['activity_id'] = df.apply(lambda row: activity_mapping.get((row['athlete_id'], row['activity_id']), row['activity_id']), axis=1)

        # Convert athlete_id to integers (incrementing from first appearance)
        unique_athletes = sorted(df['athlete_id'].unique())
        athlete_mapping = {old_id: new_id for new_id, old_id in enumerate(unique_athletes, 1)}
        df['athlete_id'] = df['athlete_id'].map(athlete_mapping)
    else:
        # Single user scenario
        unique_activities = df.groupby('activity_id')['datetime'].min().sort_values()
        activity_mapping = {old_id: new_id for new_id, old_id in enumerate(unique_activities.index, 1)}
        df['activity_id'] = df['activity_id'].map(activity_mapping)

    # 3. Add cumulative distance column calculated from duration × speed
    if 'duration' in df.columns and 'speed' in df.columns:
        df['distance_increment'] = df['duration'].dt.total_seconds() * df['speed']

        # Calculate cumulative distance per activity (and per athlete if multi-user)
        if 'athlete_id' in df.columns:
            df['distance'] = df.groupby(['athlete_id', 'activity_id'])['distance_increment'].cumsum()
        else:
            df['distance'] = df.groupby('activity_id')['distance_increment'].cumsum()

        df = df.drop('distance_increment', axis=1)

    # 4. Remove duration column
    df = df.drop('duration', axis=1)

    # 5. Convert semicircles to degrees for GPS coordinates
    for col in ['longitude', 'latitude']:
        if col in df.columns:
            df[col] = df[col].where(df[col].isna(), df[col] * (180 / 2**31))

    # 6. Sort columns by athlete_id, datetime, activity_id, sport, then other columns
    priority_columns = ['athlete_id', 'datetime', 'activity_id', 'sport']
    existing_priority_columns = [col for col in priority_columns if col in df.columns]
    other_columns = [col for col in df.columns if col not in priority_columns]
    df = df[existing_priority_columns + sorted(other_columns)]
    
    return df

### Intervals ICU

@app.route('/fetch_intervals_data', methods=['POST'])
def fetch_intervals_data():
    """Start Intervals.icu data fetch job"""
    data = request.json
    
    # Validate required parameters
    if not all([data.get('api_key'), data.get('df_id'), data.get('start_date'), data.get('end_date')]):
        return jsonify({'error': 'Missing required parameters'}), 400
    
    # Clean up old jobs
    intervals_jobs.clear()
    
    # Create new job
    job_id = str(uuid.uuid4())
    intervals_jobs[job_id] = {
        'status': 'starting',
        'message': 'Initializing...',
        'created_at': datetime.now(),
        'progress': 0,
        'total': 0
    }
    
    # Start background thread
    thread = threading.Thread(
        target=fetch_intervals_background,
        args=(data, job_id),
        daemon=True
    )
    thread.start()
    
    # Return immediately with job_id
    return jsonify({'job_id': job_id}), 202

def fetch_intervals_background(data, job_id):
    """Background worker for fetching Intervals data"""
    try:
        # Extract parameters
        api_key = data.get('api_key')
        df_id = data.get('df_id')
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        selected_metrics = data.get('metrics', [])
        aux_datasets = data.get('aux_datasets', [])
        user_id = data.get('user_id', 'default')
        
        # Update status
        intervals_jobs[job_id]['status'] = 'processing'
        intervals_jobs[job_id]['message'] = 'Connecting to Intervals.icu...'
        
        log_info(f"Fetching Intervals.icu data for job_id: {job_id}")
        
        # Create session
        session = requests.Session()
        session.auth = ("API_KEY", api_key)
        base_url = "https://intervals.icu/api/v1"
        
        # Fetch activities
        intervals_jobs[job_id]['message'] = 'Fetching activity list...'
        
        activities_url = f"{base_url}/athlete/0/activities"
        activities_params = {'oldest': start_date, 'newest': end_date}
        
        response = session.get(activities_url, params=activities_params)
        response.raise_for_status()
        activities = response.json()
        
        # Filter activities
        activities_with_files = [
            act for act in activities 
            if act.get('file_type') in ['fit', 'tcx', 'gpx']
        ]
        
        if not activities_with_files:
            intervals_jobs[job_id]['status'] = 'error'
            intervals_jobs[job_id]['error'] = 'No activities found with files in date range'
            return
        
        total_activities = len(activities_with_files)
        intervals_jobs[job_id]['total'] = total_activities
        intervals_jobs[job_id]['message'] = f'Found {total_activities} activities to download...'
        
        log_info(f"Found {total_activities} activities to process")
        
        # Download and parse FIT files with progress tracking
        detail_df = download_and_parse_fits_with_progress(
            session, base_url, activities_with_files, selected_metrics, job_id
        )
        
        if detail_df.empty:
            intervals_jobs[job_id]['status'] = 'error'
            intervals_jobs[job_id]['error'] = 'No data could be extracted from activities'
            return
        
        # Process data
        intervals_jobs[job_id]['message'] = 'Processing data...'
        detail_df = transform_intervals_detail_data(detail_df)
        
        # Prepare metadata for caching
        metadata = {
            'source': 'intervals',
            'activities_count': len(activities_with_files),
            'date_range': f"{start_date} to {end_date}",
            'metrics': selected_metrics
        }
        
        # Cache the DataFrame with metadata
        df_cache.put(df_id, detail_df, metadata)
        
        # Handle auxiliary datasets
        aux_filepaths = []

        if 'intervals' in aux_datasets:
            intervals_jobs[job_id]['message'] = 'Fetching activity intervals data...'
            intervals_df = fetch_activity_intervals_data(session, base_url, activities, job_id)
            if not intervals_df.empty:
                intervals_path = save_aux_dataset(intervals_df, 'intervals', user_id, start_date, end_date)
                aux_filepaths.append(intervals_path)
        
        if 'summary' in aux_datasets:
            intervals_jobs[job_id]['message'] = 'Preparing summary data...'
            summary_df = create_activity_summary(activities)
            if not summary_df.empty:
                summary_path = save_aux_dataset(summary_df, 'summary', user_id, start_date, end_date)
                aux_filepaths.append(summary_path)
        
        if 'wellness' in aux_datasets:
            intervals_jobs[job_id]['message'] = 'Fetching wellness data...'
            wellness_df = fetch_wellness_data(session, base_url, start_date, end_date)
            if not wellness_df.empty:
                wellness_path = save_aux_dataset(wellness_df, 'wellness', user_id, start_date, end_date)
                aux_filepaths.append(wellness_path)
        
        # Mark as completed
        intervals_jobs[job_id]['status'] = 'completed'
        intervals_jobs[job_id]['message'] = 'Data loaded successfully'
        intervals_jobs[job_id]['result'] = {
            'df_id': df_id,
            'shape': list(detail_df.shape),
            'columns': detail_df.columns.tolist(),
            'aux_datasets': aux_filepaths
        }
        
        log_info(f"Intervals.icu data cached successfully: {detail_df.shape}")
        
    except requests.exceptions.HTTPError as e:
        log_info(f"HTTP error in job {job_id}: {str(e)}")
        intervals_jobs[job_id]['status'] = 'error'
        intervals_jobs[job_id]['error'] = f'API request failed: {str(e)}'
    except Exception as e:
        log_info(f"Error in job {job_id}: {str(e)}")
        intervals_jobs[job_id]['status'] = 'error'
        intervals_jobs[job_id]['error'] = f'Failed to fetch data: {str(e)}'


def download_and_parse_fits_with_progress(session, base_url, activities, selected_metrics, job_id):
    """Modified version that uses parallel processing for parsing"""
    
    def download_single_fit(activity):
        """Download a single FIT file"""
        activity_id = activity['id']
        url = f"{base_url}/activity/{activity_id}/fit-file"
        
        try:
            response = session.get(url, timeout=30)
            response.raise_for_status()
            
            content = response.content
            # Check if gzipped
            if len(content) > 2 and content[0] == 0x1f and content[1] == 0x8b:
                fit_bytes = gzip.decompress(content)
            else:
                fit_bytes = content
            
            # Verify FIT file
            if len(fit_bytes) > 0 and fit_bytes[0] == 0x0e:
                return (activity_id, fit_bytes, activity)
            return None
            
        except Exception as e:
            log_info(f"Failed to download {activity_id}: {e}")
            return None
    
    # PHASE 1: Download (unchanged)
    fit_data = {}
    completed = 0
    total = len(activities)
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(download_single_fit, act) for act in activities]
        
        for future in as_completed(futures):
            completed += 1
            
            if job_id in intervals_jobs:
                intervals_jobs[job_id]['progress'] = completed
                intervals_jobs[job_id]['total'] = total
                intervals_jobs[job_id]['message'] = f'Downloading activities... ({completed}/{total})'
            
            result = future.result()
            if result:
                activity_id, fit_bytes, activity_meta = result
                fit_data[activity_id] = (fit_bytes, activity_meta)
    
    # Reset progress for parsing phase
    if job_id in intervals_jobs:
        intervals_jobs[job_id] = {
            'status': 'processing',
            'message': f'Parsing activity data... (0/{len(fit_data)})',
            'created_at': intervals_jobs[job_id].get('created_at'),
            'progress': 0,
            'total': len(fit_data),
            'percent': 0
        }
    
    # PHASE 2: Parse with multiprocessing (NEW)
    all_dfs = []
    parsed = 0
    total_to_parse = len(fit_data)
    
    # Use ProcessPoolExecutor for CPU-bound parsing
    with ProcessPoolExecutor(max_workers=4) as executor:
        # Submit all parsing tasks
        future_to_activity = {
            executor.submit(parse_fit_file_parallel, fit_bytes, activity_id, meta, selected_metrics): activity_id
            for activity_id, (fit_bytes, meta) in fit_data.items()
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_activity):
            activity_id = future_to_activity[future]
            try:
                df = future.result()
                if df is not None:
                    all_dfs.append(df)
                
                # Update progress in main thread (thread-safe)
                parsed += 1
                if job_id in intervals_jobs:
                    intervals_jobs[job_id]['progress'] = parsed
                    intervals_jobs[job_id]['total'] = total_to_parse
                    intervals_jobs[job_id]['message'] = f'Parsing activity data... ({parsed}/{total_to_parse})'
                    intervals_jobs[job_id]['percent'] = int((parsed / total_to_parse) * 100)
                    
            except Exception as e:
                log_info(f"Failed to parse activity {activity_id}: {e}")
                # Still update progress for failed files
                parsed += 1
                if job_id in intervals_jobs:
                    intervals_jobs[job_id]['progress'] = parsed
    
    if not all_dfs:
        return pd.DataFrame()
    
    # Final concatenation and sort (unchanged)
    if job_id in intervals_jobs:
        intervals_jobs[job_id]['message'] = 'Combining activity data...'
    
    combined_df = pd.concat(all_dfs, ignore_index=True)
    return combined_df.sort_values('datetime', ascending=False).reset_index(drop=True)


@app.route('/intervals_job/<job_id>', methods=['GET'])
def get_intervals_job(job_id):
    """Get status of Intervals fetch job"""
    
    if job_id not in intervals_jobs:
        return jsonify({'status': 'not_found'}), 404
    
    job = intervals_jobs[job_id]
    
    # Build response
    response = {
        'status': job['status'],
        'message': job.get('message', ''),
        'progress': job.get('progress', 0),
        'total': job.get('total', 0)
    }
    
    # Use explicit percent if available, otherwise calculate
    if 'percent' in job:
        response['percent'] = job['percent']
    elif job.get('total', 0) > 0:
        response['percent'] = int((job.get('progress', 0) / job['total']) * 100)
    else:
        response['percent'] = 0
    
    # Include result or error if completed
    if job['status'] == 'completed':
        response['result'] = job.get('result', {})
    elif job['status'] == 'error':
        response['error'] = job.get('error', 'Unknown error')
    
    return jsonify(response)


def parse_fit_file_parallel(fit_bytes, activity_id, activity_meta, selected_metrics):
    """Standalone parse function for multiprocessing - must be at module level"""
    try:
        fitfile = FitFile(io.BytesIO(fit_bytes))
        records = []
        
        # Define metrics mapping
        metric_mappings = {
            'timestamp': 'datetime',
            'position_lat': 'lat',
            'position_long': 'lon',
            'heart_rate': 'heart_rate',
            'power': 'power',
            'speed': 'speed',
            'enhanced_speed': 'speed',
            'cadence': 'cadence',
            'altitude': 'altitude',
            'temperature': 'temperature',
            'distance': 'distance',
            'left_right_balance': 'left_right_balance',
            'unknown_108': 'respiration_rate',
            'enhanced_respiration_rate': 'respiration_rate',
            'tidal_volume': 'tidal_volume',
            'tidal_volume_min': 'tidal_volume_minute'
        }
        
        for record in fitfile.get_messages('record'):
            data = {}
            
            for field in record:
                # Map field names to our standard names
                if field.name in metric_mappings:
                    standard_name = metric_mappings[field.name]
                    
                    # Skip if metrics are specified and this isn't in the list
                    if selected_metrics and standard_name not in selected_metrics and standard_name != 'datetime':
                        continue
                    
                    if field.value is not None:
                        if field.name == 'timestamp':
                            data['datetime'] = field.value
                        elif field.name == 'position_lat':
                            # Convert semicircles to degrees
                            data['lat'] = field.value * (180.0 / 2**31)
                        elif field.name == 'position_long':
                            data['lon'] = field.value * (180.0 / 2**31)
                        elif field.name == 'unknown_108': # Respiration rate scaling
                            data['respiration_rate'] = field.value / 100.0
                        else:
                            data[standard_name] = field.value
            
            if 'datetime' in data:
                records.append(data)
        
        if not records:
            return None
        
        df = pd.DataFrame(records)
        df['activity_id'] = activity_id
        df['activity_type'] = activity_meta.get('type', 'Unknown')
        df['activity_name'] = activity_meta.get('name', 'Unnamed')
        
        # Ensure datetime is proper type
        df['datetime'] = pd.to_datetime(df['datetime'])
        
        # Reorder columns
        priority_cols = ['activity_id', 'datetime']
        other_cols = [c for c in df.columns if c not in priority_cols]
        df = df[priority_cols + other_cols]
        
        return df
        
    except Exception as e:
        # Log errors but don't raise - return None for failed parses
        print(f"Failed to parse activity {activity_id}: {e}")
        return None


def transform_intervals_detail_data(df):
    """Transform Intervals.icu detail data for consistency and efficiency"""
    
    # Round GPS coordinates to 6 decimal places (0.11m precision)
    if 'lat' in df.columns:
        df['lat'] = df['lat'].round(6)
    if 'lon' in df.columns:
        df['lon'] = df['lon'].round(6)
    
    # Round altitude to 1 decimal place
    if 'altitude' in df.columns:
        df['altitude'] = df['altitude'].round(1)
    
    # Ensure consistent data types
    numeric_cols = ['power', 'heart_rate', 'speed', 'cadence', 'temperature', 'distance']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Sort by datetime descending (newest first)
    df = df.sort_values('datetime', ascending=False)
    
    return df

def fetch_activity_intervals_data(session, base_url, activities, job_id):
    """Fetch intervals for all activities using parallel requests"""
    
    # Filter activities with IDs
    activities_with_ids = [act for act in activities if 'id' in act]
    
    if not activities_with_ids:
        return pd.DataFrame()
    
    def fetch_intervals_for_activity(activity):
        """Download all intervals for a single activity"""
        activity_id = activity['id']
        url = f"{base_url}/activity/{activity_id}/intervals"
        
        try:
            response = session.get(url, timeout=10)
            if response.ok:
                data = response.json()
                # Transform to flat structure - returns list of records
                return process_interval_data(data, activity_id)
            return []
        except Exception as e:
            log_info(f"Error fetching intervals for activity {activity_id}: {e}")
            return []
    
    # Use ThreadPoolExecutor for parallel downloads
    all_intervals = []
    completed = 0
    total = len(activities_with_ids)
    
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(fetch_intervals_for_activity, act) 
                  for act in activities_with_ids]
        
        for future in as_completed(futures):
            completed += 1
            
            # Update progress
            if job_id in intervals_jobs:
                intervals_jobs[job_id]['message'] = \
                    f'Processing Activity Intervals {completed}/{total}'
            
            result = future.result()
            if result:
                all_intervals.extend(result)
    
    if not all_intervals:
        return pd.DataFrame()
    
    # Convert to DataFrame and sort
    df = pd.DataFrame(all_intervals)
    
    # Sort by activity_id and lap_number
    if 'activity_id' in df.columns and 'lap_number' in df.columns:
        df = df.sort_values(['activity_id', 'lap_number'])
    
    return df

def process_interval_data(data, activity_id):
    """Transform the JSON response into multiple flat records"""
    intervals_list = []
    
    if 'icu_intervals' in data and data['icu_intervals']:
        for interval in data['icu_intervals']:
            # Create a flat record for each interval
            record = {
                'activity_id': activity_id,
                'lap_number': interval.get('LapNumber'),
                'start_time': interval.get('start_time'),
                'end_time': interval.get('end_time'),
                'start_index': interval.get('start_index'),
                'end_index': interval.get('end_index'),
                'distance': interval.get('distance'),
                'moving_time': interval.get('moving_time'),
                'elapsed_time': interval.get('elapsed_time'),
                'joules': interval.get('joules'),
                'avg_lr_balance': interval.get('avg_lr_balance'),
                'average_watts': interval.get('average_watts'),
                'average_respiration': interval.get('average_respiration'),
                'average_tidal_volume': interval.get('average_tidal_volume'),
                'average_tidal_volume_min': interval.get('average_tidal_volume_min'),
                'average_speed': interval.get('average_speed'),
                'average_heartrate': interval.get('average_heartrate'),
                'average_cadence': interval.get('average_cadence'),
                'average_torque': interval.get('average_torque'),
                'min_altitude': interval.get('min_altitude'),
                'max_altitude': interval.get('max_altitude'),
                'total_elevation_gain': interval.get('total_elevation_gain'),
                'average_gradient': interval.get('average_gradient'),
                'average_weather_temp': interval.get('average_weather_temp'),
                'average_wind_speed': interval.get('average_wind_speed'),
                'average_wind_gust': interval.get('average_wind_gust'),
                'prevailing_wind_deg': interval.get('prevailing_wind_deg'),
                'average_yaw': interval.get('average_yaw'),
                'headwind_percent': interval.get('headwind_percent'),
                'tailwind_percent': interval.get('tailwind_percent'),
                'zone': interval.get('zone'),
                'label': interval.get('TVLlabelfield'),
                'RPE': interval.get('TVLRPEfield'),
                'lactate': interval.get('Lactate'),
            }
            intervals_list.append(record)
    
    return intervals_list


def create_activity_summary(activities):
    """Create comprehensive summary DataFrame from activities list"""
    
    # Field mapping for summary
    summary_fields = {
        # Basic info
        'id': 'activity_id',
        'name': 'name',
        'type': 'type',
        'start_date_local': 'start_date_local',
        'start_date': 'start_date_utc',
        'timezone': 'timezone',
        
        # Duration and distance
        'elapsed_time': 'elapsed_time_sec',
        'moving_time': 'moving_time_sec',
        'distance': 'distance_m',
        
        # Power metrics
        'icu_ftp': 'ftp_watts',
        'icu_weighted_avg_watts': 'normalized_power',
        'icu_average_watts': 'avg_power',
        'icu_variability_index': 'variability_index',
        'icu_efficiency_factor': 'efficiency_factor',
        'icu_rolling_cp': 'critical_power',
        'icu_rolling_w_prime': 'w_prime_joules',
        'icu_rolling_p_max': 'max_power',
        'icu_joules': 'work_joules',
        'power_load': 'power_load',
        'avg_lr_balance': 'avg_left_right_balance',
        
        # Heart rate
        'average_heartrate': 'avg_hr',
        'max_heartrate': 'max_hr',
        'lthr': 'lactate_threshold_hr',
        'icu_resting_hr': 'resting_hr',
        'hr_load': 'hr_load',
        
        # Training metrics
        'icu_training_load': 'training_load',
        'icu_atl': 'acute_training_load',
        'icu_ctl': 'chronic_training_load',
        'trimp': 'trimp',
        'strain_score': 'strain_score',
        'session_rpe': 'session_rpe',
        'icu_intensity': 'intensity',
        
        # Speed/Pace
        'average_speed': 'avg_speed_mps',
        'max_speed': 'max_speed_mps',
        'pace': 'pace',
        'gap': 'grade_adjusted_pace',
        'pace_load': 'pace_load',
        
        # Elevation
        'total_elevation_gain': 'elevation_gain_m',
        'total_elevation_loss': 'elevation_loss_m',
        'average_altitude': 'avg_altitude_m',
        'min_altitude': 'min_altitude_m',
        'max_altitude': 'max_altitude_m',
        
        # Cadence and dynamics
        'average_cadence': 'avg_cadence',
        'average_stride': 'avg_stride_length',
        
        # Nutrition and physiology
        'calories': 'calories',
        'carbs_used': 'carbs_used_g',
        'carbs_ingested': 'carbs_ingested_g',
        'icu_weight': 'athlete_weight_kg',
        
        # Feel and RPE
        'icu_rpe': 'rpe',
        'feel': 'feel_score',
        'perceived_exertion': 'perceived_exertion',
        
        # Weather (if available)
        'average_weather_temp': 'weather_temp_c',
        'min_weather_temp': 'min_weather_temp_c',
        'max_weather_temp': 'max_weather_temp_c',
        'average_wind_speed': 'wind_speed_mps',
        'average_wind_gust': 'wind_gust_mps',
        'headwind_percent': 'headwind_percent',
        'tailwind_percent': 'tailwind_percent',
        
        # Metadata
        'source': 'data_source',
        'device_name': 'device_name',
        'power_meter': 'power_meter_name',
        'trainer': 'is_trainer',
        'race': 'is_race',
        'commute': 'is_commute',
        'sub_type': 'sub_type',
        
        # Performance metrics
        'decoupling': 'aerobic_decoupling',
        'polarization_index': 'polarization_index',
        'compliance': 'workout_compliance',
        
        # Additional fields
        'gear': 'gear_name',
        'external_id': 'external_id',
        'strava_id': 'strava_id'
    }
    
    summary_data = []
    for activity in activities:
        row = {}
        
        # Extract standard fields
        for api_field, df_field in summary_fields.items():
            if api_field in activity and activity[api_field] is not None:
                value = activity[api_field]
                
                # Handle special cases
                if api_field == 'gear' and isinstance(value, dict):
                    value = value.get('name', '')
                elif 'date' in api_field:
                    try:
                        value = pd.to_datetime(value)
                    except:
                        pass
                        
                row[df_field] = value
        
        # Add zone times if available
        if 'icu_zone_times' in activity and activity['icu_zone_times']:
            for zone in activity['icu_zone_times']:
                if isinstance(zone, dict):
                    zone_id = zone.get('id', '')
                    zone_secs = zone.get('secs', 0)
                    if zone_id:
                        row[f'zone_{zone_id}_sec'] = zone_secs
        
        # Add HR zone times if available
        if 'icu_hr_zone_times' in activity and isinstance(activity['icu_hr_zone_times'], list):
            for i, secs in enumerate(activity['icu_hr_zone_times']):
                if secs:
                    row[f'hr_zone_{i+1}_sec'] = secs
        
        # Add pace zone times if available
        if 'pace_zone_times' in activity and isinstance(activity['pace_zone_times'], list):
            for i, secs in enumerate(activity['pace_zone_times']):
                if secs:
                    row[f'pace_zone_{i+1}_sec'] = secs
        
        summary_data.append(row)
    
    df = pd.DataFrame(summary_data)
    
    # Remove columns with no data
    df = df.dropna(axis=1, how='all')
    
    # Sort by date
    if 'start_date_local' in df.columns:
        df['start_date_local'] = pd.to_datetime(df['start_date_local'])
        df = df.sort_values('start_date_local', ascending=False)
    
    return df


def fetch_wellness_data(session, base_url, start_date, end_date):
    """Fetch wellness data from Intervals.icu"""
    
    url = f"{base_url}/athlete/0/wellness"
    params = {'oldest': start_date, 'newest': end_date}
    
    try:
        response = session.get(url, params=params)
        response.raise_for_status()
        wellness_data = response.json()
        
        if not wellness_data:
            return pd.DataFrame()
        
        df = pd.DataFrame(wellness_data)
        
        # Rename 'id' to 'date'
        if 'id' in df.columns:
            df.rename(columns={'id': 'date'}, inplace=True)
            df['date'] = pd.to_datetime(df['date'])
        
        # Remove columns with no data
        df = df.dropna(axis=1, how='all')
        
        # Sort by date (newest first)
        if 'date' in df.columns:
            df = df.sort_values('date', ascending=False)
        
        return df
        
    except Exception as e:
        log_info(f"Error fetching wellness data: {e}")
        return pd.DataFrame()

def save_aux_dataset(df, dataset_type, user_id, start_date, end_date):
    """Save auxiliary dataset to filesystem"""
    
    # Create user-specific directory
    executor_datasets_dir = os.path.join('datasets', user_id)
    os.makedirs(executor_datasets_dir, exist_ok=True)
    
    # Create descriptive filename - simplified format
    date_range = f"{start_date.replace('-', '')}_to_{end_date.replace('-', '')}"
    
    # Map dataset types to cleaner names
    type_mapping = {
        'summary': 'activity_summary',
        'wellness': 'wellness_data',
        'intervals': 'activity_intervals'
    }
    clean_type = type_mapping.get(dataset_type, dataset_type)
    
    filename = f"{clean_type}_{date_range}.csv"
    
    filepath = os.path.join(executor_datasets_dir, filename)
    
    # Save DataFrame
    df.to_csv(filepath, index=False)
    
    return filepath

### Endura API

@app.route('/endura/get_races', methods=['GET'])
def endura_get_races():
    """Get list of races from Endura API"""
    api_key = request.headers.get('X-API-Key')
    
    if not api_key:
        return jsonify({'error': 'No API key provided'}), 401
    
    try:
        log_info("Fetching races from Endura")
        
        response = requests.get(
            'https://team-hub.co.uk/endura_api/getraces',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=10
        )
        
        if response.status_code == 401:
            return jsonify({'error': 'Invalid API key'}), 401
        
        response.raise_for_status()
        races = response.json()
        
        log_info(f"Retrieved {len(races)} races from Endura")
        
        return jsonify({'races': races}), 200
        
    except requests.exceptions.RequestException as e:
        log_info(f"Error fetching races from Endura: {str(e)}")
        return jsonify({'error': f'Failed to fetch races: {str(e)}'}), 500


@app.route('/endura/load_race_data', methods=['POST'])
def endura_load_race_data():
    """Fetch and process Endura race data"""
    data = request.json
    
    api_key = data.get('api_key')
    df_id = data.get('df_id')
    race_id = data.get('race_id')
    aux_datasets = data.get('aux_datasets', ['profile'])
    user_id = data.get('user_id', 'default')
    
    if not all([api_key, df_id, race_id]):
        return jsonify({'error': 'Missing required parameters'}), 400
    
    try:
        log_info(f"Fetching Endura data for race_id: {race_id}")
        
        # Fetch race data from Endura
        response = requests.get(
            f'https://team-hub.co.uk/endura_api/getracedata?raceid={race_id}',
            headers={'Authorization': f'Bearer {api_key}'},
            timeout=30
        )
        
        if response.status_code == 401:
            return jsonify({'error': 'Invalid API key'}), 401
            
        response.raise_for_status()
        
        race_data = response.json()
        
        # Process primary data
        primary_records = []
        for record in race_data.get('primary_data', []):
            # Rename euid to athlete_id
            if 'euid' in record:
                record['athlete_id'] = record.pop('euid')
            primary_records.append(record)
        
        # Create DataFrame from primary data
        primary_df = pd.DataFrame(primary_records)
        
        # Remove columns that are all zeros, nulls, or 0.0
        if not primary_df.empty:
            # Identify columns to drop
            cols_to_drop = []
            for col in primary_df.columns:
                if col in ['athlete_id', 'timestamp']:  # Never drop these key columns
                    continue
                    
                # Check if column contains only 0, 0.0, or null values
                unique_vals = primary_df[col].dropna().unique()
                if len(unique_vals) == 0:  # All nulls
                    cols_to_drop.append(col)
                elif len(unique_vals) == 1 and unique_vals[0] in [0, 0.0]:  # All zeros
                    cols_to_drop.append(col)
                elif all(v in [0, 0.0] for v in unique_vals):  # Mix of 0 and 0.0
                    cols_to_drop.append(col)
            
            if cols_to_drop:
                log_info(f"Dropping {len(cols_to_drop)} columns with no useful data: {cols_to_drop[:5]}...")  # Log first 5
                primary_df = primary_df.drop(columns=cols_to_drop)
            
            # Reorder columns: athlete_id first, timestamp second, then others
            cols = primary_df.columns.tolist()
            ordered_cols = []
            
            # Add athlete_id first
            if 'athlete_id' in cols:
                ordered_cols.append('athlete_id')
                cols.remove('athlete_id')
            
            # Add timestamp second
            if 'timestamp' in cols:
                ordered_cols.append('timestamp')
                cols.remove('timestamp')
            
            # Add remaining columns
            ordered_cols.extend(sorted(cols))  # Sort remaining for consistency
            
            primary_df = primary_df[ordered_cols]
            
            # Sort by athlete_id and timestamp
            if 'athlete_id' in primary_df.columns and 'timestamp' in primary_df.columns:
                primary_df = primary_df.sort_values(['athlete_id', 'timestamp'])
        
        # Add metadata for caching
        metadata = {
            'source': 'endura',
            'race_id': race_id,
            'race_title': race_data.get('race_title', 'Unknown Race'),
            'race_date': race_data.get('race_date', 'Unknown Date'),
            'athletes_count': primary_df['athlete_id'].nunique() if 'athlete_id' in primary_df.columns else 0
        }
        
        # Cache the primary DataFrame
        df_cache.put(df_id, primary_df, metadata)
        
        # Process auxiliary datasets
        executor_datasets_dir = os.path.join('datasets', user_id)
        os.makedirs(executor_datasets_dir, exist_ok=True)
        
        aux_filepaths = []
        
        # Process profile data (always included)
        if 'profile' in aux_datasets and 'profile_data' in race_data:
            profile_records = []
            for record in race_data.get('profile_data', []):
                if 'euid' in record:
                    record['athlete_id'] = record.pop('euid')
                profile_records.append(record)
            
            if profile_records:
                profile_df = pd.DataFrame(profile_records)
                
                # Reorder columns: athlete_id first
                if 'athlete_id' in profile_df.columns:
                    cols = profile_df.columns.tolist()
                    cols.remove('athlete_id')
                    profile_df = profile_df[['athlete_id'] + cols]
                
                profile_path = os.path.join(executor_datasets_dir, f'athlete_profiles_race_{race_id}.csv')
                profile_df.to_csv(profile_path, index=False)
                aux_filepaths.append(profile_path)
        
        # Process turns
        if 'turns' in aux_datasets and 'turns' in race_data:
            turns_df = pd.DataFrame(race_data['turns'])
            
            # Reorder columns: turn_turn_name first, turn_time second
            if not turns_df.empty:
                cols = turns_df.columns.tolist()
                ordered_cols = []
                
                # Add turn_turn_name first
                if 'turn_turn_name' in cols:
                    ordered_cols.append('turn_turn_name')
                    cols.remove('turn_turn_name')
                
                # Add turn_time second
                if 'turn_time' in cols:
                    ordered_cols.append('turn_time')
                    cols.remove('turn_time')
                
                # Add remaining columns
                ordered_cols.extend(cols)
                
                turns_df = turns_df[ordered_cols]
            
            turns_path = os.path.join(executor_datasets_dir, f'race_turns_race_{race_id}.csv')
            turns_df.to_csv(turns_path, index=False)
            aux_filepaths.append(turns_path)
        
        # Process climbs (already good as is)
        if 'climbs' in aux_datasets and 'climbs' in race_data:
            climbs_df = pd.DataFrame(race_data['climbs'])
            climbs_path = os.path.join(executor_datasets_dir, f'race_climbs_race_{race_id}.csv')
            climbs_df.to_csv(climbs_path, index=False)
            aux_filepaths.append(climbs_path)
        
        # Process waymarkers (already good as is)
        if 'waymarkers' in aux_datasets and 'waymarkers' in race_data:
            waymarkers_df = pd.DataFrame(race_data['waymarkers'])
            waymarkers_path = os.path.join(executor_datasets_dir, f'race_waymarkers_race_{race_id}.csv')
            waymarkers_df.to_csv(waymarkers_path, index=False)
            aux_filepaths.append(waymarkers_path)
        
        log_info(f"Endura data processed successfully: {primary_df.shape}, {len(cols_to_drop) if 'cols_to_drop' in locals() else 0} empty columns removed")
        
        return jsonify({
            'df_id': df_id,
            'shape': list(primary_df.shape),
            'columns': primary_df.columns.tolist(),
            'aux_datasets': aux_filepaths,
            'race_title': race_data.get('race_title', 'Unknown Race')
        }), 200
        
    except requests.exceptions.RequestException as e:
        log_info(f"Error fetching Endura data: {str(e)}")
        return jsonify({'error': f'Failed to fetch Endura data: {str(e)}'}), 500
    except Exception as e:
        log_info(f"Error processing Endura data: {str(e)}")
        return jsonify({'error': f'Failed to process data: {str(e)}'}), 500
    
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

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint for container monitoring"""
    try:
        # Basic health checks without complex path operations
        current_time = datetime.now().isoformat()
        
        # Simple test to verify pandas is working
        import pandas as pd
        import numpy as np
        test_df = pd.DataFrame({'test': [1, 2, 3]})
        test_result = len(test_df) == 3
        
        # Check if we can access basic directories
        app_dir_exists = os.path.exists('/app')
        
        # Get actual container RAM allocation
        total_ram_gb = get_container_ram_gb()
        
        return jsonify({
            'status': 'healthy',
            'build': EXECUTOR_BUILD,
            'timestamp': current_time,
            'cache_size': len(df_cache.cache),
            'test_passed': test_result,
            'app_directory': app_dir_exists,
            'ram_gb': total_ram_gb,  # Add this line
            'kernel_service': KERNEL_SERVICE,
            'libraries': {
                'pandas': pd.__version__,
                'numpy': np.__version__
            }
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }), 503

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)