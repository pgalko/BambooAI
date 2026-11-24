import pandas as pd
import io
import os
import threading
import time
from typing import Optional, List
import pyarrow.parquet as pq
import csv

# Configure logger
from logger_config import get_logger
logger = get_logger(__name__)


# Utility functions

class StoppableStreamWrapper:
    """
    A wrapper for an iterable stream that safely checks a threading.Event
    on each iteration. If no event is provided, it acts as a simple pass-through.
    """
    def __init__(self, stream, stop_event: threading.Event = None):
        self._stream = stream
        self._stop_event = stop_event

    def __iter__(self):
        # Return an iterator from the original stream
        self._iterator = iter(self._stream)
        return self

    def __next__(self):
        # If a stop event exists and is set, stop the iteration cleanly.
        if self._stop_event and self._stop_event.is_set():
            # This cleanly stops the 'for' loop that is using this object.
            raise StopIteration("Process was stopped by a server cleanup request.")
        
        # Otherwise, get the next item from the original stream.
        return next(self._iterator)

def aux_datasets_to_string(file_paths: List[str],
                           num_rows: int = 5,
                           execution_mode: str = 'local',
                           executor_client=None) -> str:
    """
    Load and preview the first num_rows from each dataset in file_paths
    in a memory-efficient way, either locally or via executor API.
    """
    if execution_mode == 'api' and executor_client is not None:
        api_result = executor_client.aux_datasets_to_string(file_paths=file_paths, num_rows=num_rows)
        if api_result is not None:
            return api_result

    # Local execution
    result = []
    if not file_paths:
        return "No auxiliary datasets provided."
    
    for i, path in enumerate(file_paths, 1):
        file_ext = os.path.splitext(path)[1].lower()
        
        try:
            if not os.path.exists(path):
                result.append(f"{i}.\nPath: {path}\nError: File not found")
                continue

            if file_ext == '.csv':
                df = pd.read_csv(path, nrows=num_rows)
            elif file_ext in ['.parquet', '.pq']:
                parquet_file = pq.ParquetFile(path)
                # Read only the first batch (up to num_rows)
                # Ensure there are row groups to read
                if parquet_file.num_row_groups > 0:
                    df = parquet_file.read_row_group(0, columns=parquet_file.schema.names).to_pandas()
                    if len(df) > num_rows: # Slice if the row group is larger
                        df = df.iloc[:num_rows]
                else: # Handle empty parquet file
                    df = pd.DataFrame(columns=parquet_file.schema.names) # Empty df with correct columns
            elif file_ext == '.json':
                df = pd.read_json(path)
                if len(df) > num_rows:
                    df = df.head(num_rows)
            elif file_ext in ['.xlsx', '.xls']:
                df = pd.read_excel(path, engine='openpyxl')
                if len(df) > num_rows:
                    df = df.head(num_rows)
            else:
                result.append(f"{i}.\nPath: {path}\nError: Unsupported file format")
                continue
            
            buffer = io.StringIO()
            with pd.option_context('display.max_columns', None, 
                                  'display.width', None,
                                  'display.max_colwidth', None):
                df.to_string(buf=buffer, index=False)
            
            result.append(f"{i}.\nPath: {path}\nHead:\n{buffer.getvalue()}")
            
        except Exception as e:
            result.append(f"{i}.\nPath: {path}\nError: {str(e)}")
    
    return "\n\n".join(result)

def get_dataframe_columns(df: pd.DataFrame,
                         execution_mode: str = 'local',
                         df_id: Optional[str] = None,
                         executor_client=None) -> str:
    """
    Get DataFrame columns either locally or via executor API.
    Returns string of column names.
    """
    if execution_mode == 'api' and df_id is not None:
        result = executor_client.get_dataframe_columns(df_id)
        if result is not None:
            return ', '.join(result.get('columns') or [])
    if df is None:
        # In api mode the frame lives in the container; when the API cannot
        # serve it (container restarted, df reaped) there is no local frame to
        # fall back to. Returning "" is the honest degenerate - the old
        # fallback dereferenced None and crashed whoever called.
        return ""
    return ', '.join(df.columns.tolist())

def get_aux_datasets_columns(file_paths: List[str],
                             execution_mode: str = 'local',
                             executor_client=None) -> str:
    """
    Extract only the column names from each dataset in file_paths
    in a memory-efficient way, either locally or via executor API.
    """
    if execution_mode == 'api' and executor_client is not None:
        api_result = executor_client.get_aux_datasets_columns(file_paths=file_paths)
        if api_result is not None:
            return api_result
        # Fallback or error handling

    # Local execution
    result = []
    if not file_paths:
        return "No auxiliary datasets provided."
    
    for i, path in enumerate(file_paths, 1):
        file_ext = os.path.splitext(path)[1].lower()
        
        try:
            if not os.path.exists(path):
                result.append(f"{i}.\nPath: {path}\nError: File not found")
                continue

            if file_ext == '.csv':
                with open(path, 'r', newline='', encoding='utf-8') as csvfile: # Specify encoding
                    reader = csv.reader(csvfile)
                    columns = next(reader)
            elif file_ext in ['.parquet', '.pq']:
                parquet_file = pq.ParquetFile(path)
                columns = parquet_file.schema.names
            elif file_ext == '.json':
                df_temp = pd.read_json(path)
                columns = df_temp.columns.tolist()
                del df_temp
            elif file_ext in ['.xlsx', '.xls']:
                df_temp = pd.read_excel(path, engine='openpyxl', nrows=0)
                columns = df_temp.columns.tolist()
                del df_temp
            else:
                result.append(f"{i}.\nPath: {path}\nError: Unsupported file format")
                continue
            
            columns_str = ", ".join(columns)
            result.append(f"{i}.\nPath: {path}\nColumns:\n{columns_str}")
            
        except StopIteration: # Handles empty CSV file
             result.append(f"{i}.\nPath: {path}\nError: CSV file is empty or has no header")
        except Exception as e:
            result.append(f"{i}.\nPath: {path}\nError: {str(e)}")
    
    return "\n\n".join(result)
 
def computeDataframeSample(df: pd.DataFrame, 
                         execution_mode: str = 'local',
                         df_id: Optional[str] = None,
                         executor_client=None) -> pd.DataFrame:
    """
    Compute the index of a DataFrame either locally or via executor API.
    Returns a DataFrame with aggregated statistics for each activity.
    """
    
    if execution_mode == 'api' and df_id is not None and executor_client is not None:
        result = executor_client.compute_dataframe_sample(df_id)
        if result is not None:
            return result

    # Reached when the executor returned nothing usable. In remote mode there is
    # no local frame to fall back on - `df` is None by design - and the bare
    # except below then RETURNED that None, which display_results called
    # .to_html() on. Hand back an empty frame instead: the caller wants
    # something to render, not an exception three lines later.
    if df is None:
        return pd.DataFrame({"(dataframe preview unavailable)": []})

    try:
        df_sample = df.head(100)
    except Exception:
        return df

    return df_sample

def compute_aux_dataset_sample(file_paths: List[str],
                               num_rows: int = 100,
                               execution_mode: str = 'local',
                               executor_client=None) -> List[str]: # Returns list of HTML strings
    """
    Load a sample of each dataset in file_paths and convert to HTML
    in a memory-efficient way, either locally or via executor API.
    """
    if execution_mode == 'api' and executor_client is not None:
        api_result = executor_client.compute_aux_dataset_sample(file_paths=file_paths, num_rows=num_rows)
        if api_result is not None:
            return api_result 
        # Fallback or error handling

    # Local execution
    html_results = []
    if not file_paths: # Handle empty file_paths list
        error_df = pd.DataFrame([{"Error": "No auxiliary dataset paths provided."}])
        html_results.append(error_df.to_html(classes='dataframe', border=0, index=False))
        return html_results

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
            error_df = pd.DataFrame([{"Error": f"Failed to process {os.path.basename(path)}: {str(e)}"}])
            html_results.append(error_df.to_html(classes='dataframe', border=0, index=False))
    
    return html_results
    
# ── chain identifiers ──────────────────────────────────────────────────────
_CHAIN_ID_LOCK = threading.Lock()
_LAST_CHAIN_ID = 0


def next_chain_id():
    """A chain id that is never reused within this process.

    Chain ids were `int(time.time())`, so anything minted inside the same
    second collided. That is rare when a human is typing and routine when a
    machine is not: auto_explore mints two solution chains as
    `int(time.time()) + q_idx` and then a supporting chain as plain
    `int(time.time())`, which is the SAME value as solution 0 whenever the
    round takes under a second. A collision silently overwrites the earlier
    chain in the thread file, so its context is lost and a later restore gets
    the wrong conversation.

    Still a unix timestamp, still ten digits, still roughly chronological, so
    stored threads and anything reading these ids are unaffected. It only ever
    moves forward: when the clock has not advanced, the next id is the last one
    plus one.

    Not cross-process unique. Separate gunicorn workers keep separate counters,
    so two workers minting in the same second could still agree - but every
    collision seen so far has been within one process, and making these ids
    globally unique would mean changing their format.
    """
    global _LAST_CHAIN_ID
    with _CHAIN_ID_LOCK:
        candidate = int(time.time())
        if candidate <= _LAST_CHAIN_ID:
            candidate = _LAST_CHAIN_ID + 1
        _LAST_CHAIN_ID = candidate
        return candidate


# ── thread identifiers ─────────────────────────────────────────────────────
_THREAD_ID_LOCK = threading.Lock()
_LAST_THREAD_ID = 0


def next_thread_id():
    """A thread id that is never reused within this process.

    Same weakness `next_chain_id` cures, wider blast radius: the thread id is
    the thread FILENAME, so two threads minted inside the same second share
    one file and every chain of the first is overwritten or interleaved by
    the second - the whole conversation, not one chain, is what a later
    restore gets wrong. Two browser tabs opened together, or an API caller
    starting threads in a loop, is all it takes.

    Same format guarantees as chain ids: still a ten-digit unix timestamp,
    still roughly chronological, so the storage layout, the UI and anything
    parsing these ids are unaffected. Deliberately a SEPARATE counter from
    chain ids - the two id spaces never compare against each other, and
    coupling them would make a burst of chains push thread ids into the
    future for no benefit.

    Not cross-process unique, exactly as documented on next_chain_id.
    """
    global _LAST_THREAD_ID
    with _THREAD_ID_LOCK:
        candidate = int(time.time())
        if candidate <= _LAST_THREAD_ID:
            candidate = _LAST_THREAD_ID + 1
        _LAST_THREAD_ID = candidate
        return candidate

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


# ---- the Data tab's grid for auxiliary files (2026-09-08): a page of a file on disk ----
_AUX_FRAMES = {}     # path -> (mtime, frame); the file is read once, then paged

def aux_page(path, offset=0, limit=50, order_by=None, ascending=True):
    """One page of an auxiliary dataset file (csv, parquet, json, xlsx), read whole once and cached by mtime."""
    import os
    import pandas as pd
    mtime = os.path.getmtime(path)
    cached = _AUX_FRAMES.get(path)
    if cached is None or cached[0] != mtime:
        ext = os.path.splitext(path)[1].lower()
        if ext == '.csv':
            df = pd.read_csv(path)
        elif ext in ('.parquet', '.pq'):
            df = pd.read_parquet(path)
        elif ext == '.json':
            df = pd.read_json(path)
        elif ext in ('.xlsx', '.xls'):
            df = pd.read_excel(path)
        else:
            raise ValueError(f"unsupported auxiliary file type: {ext}")
        if len(_AUX_FRAMES) > 8:
            _AUX_FRAMES.clear()
        _AUX_FRAMES[path] = (mtime, df)
        cached = _AUX_FRAMES[path]
    page = page_frame(cached[1], offset, limit, order_by, ascending)
    page['df_id'] = 'aux:' + path
    return page
