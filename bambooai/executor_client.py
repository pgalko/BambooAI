# executor_client.py

import requests
import pandas as pd
from typing import Optional, Dict, Any, Union, List
from datetime import datetime

class ExecutorAPIClient:
    def __init__(self, base_url: str = None):
        self.base_url = base_url
        
    def log_to_file(self, message):
        """Write log message to file with timestamp"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open('/home/data/bambooai/orchestration/logs/code_executor.log', 'a') as f:
            f.write(f"[INFO] {timestamp} - {message}\n")

    def execute_code(self, code: str,
                    output_manager: Optional[Any] = None,
                    kill_signal: Optional[bool] = False,
                    df_id: Optional[str] = None, 
                    patch_code: Optional[str] = None,
                    plots_dir: Optional[str] = None,
                    plot_format: Optional[str] = None,
                    generated_datasets_path: Optional[list] = None,
                    persist_df: bool = True,
                    timeout: Optional[int] = None) -> Dict[str, Any]:
    
        """Execute code via the executor API"""
        self.log_to_file(f"Starting API execution with DataFrame ID={df_id}")

        # Set Timeout for the request (a caller replaying a long analysis passes its own)
        timeout = int(timeout) if timeout else 300
        
        data = {
            'code': code,
            'df_id': df_id,
            # False after an investigation: that script is a consolidation and is
            # told the frame arrives as uploaded, so its derived columns must not
            # persist into the shared cached copy.
            'persist_df': persist_df,
            'patch_code': patch_code,
            'plots_dir': plots_dir,
            'plot_format': plot_format,
            'generated_datasets_path': generated_datasets_path,
            'timeout': timeout
        }

        try:
            self.log_to_file(f"Sending request to {self.base_url}/execute")
            response = requests.post(f"{self.base_url}/execute", json=data, timeout=timeout + 60)
            response.raise_for_status()
            
            api_result = response.json()

            # Check for timeout
            if api_result.get('timeout'):
                self.log_to_file(f"Task timed out after {timeout} seconds")
                output_manager.display_system_messages(f"Execution timed out after {timeout} seconds.")
                # TODO: Add your timeout handling logic here
                pass

            has_results = bool(api_result.get('results'))
            has_error = bool(api_result.get('error'))
            num_plots = len(api_result.get('plot_images', []))
            num_datasets = len(api_result.get('generated_datasets', []))
            
            self.log_to_file(
                f"Received API response - "
                f"Results: {'Yes' if has_results else 'No'}, "
                f"Errors: {'Yes' if has_error else 'No'}, "
                f"Plots: {num_plots}, "
                f"Generated Datasets: {num_datasets}"
            )

            return api_result
            
        except requests.RequestException as e:
            self.log_to_file(f"Failed to execute code via API: {str(e)}")
            return {
                'results': None,
                'error': str(e),
                'plot_images': [],
                'generated_datasets': []
            }

    # TODO: Function to store dataset details if needed   
    def store_dataset_details(self, user_id, thread_id, chain_id, df_id, auxiliary_datasets):
        """Store dataset details in database"""
        
        self.log_to_file(f"Storing dataset details for user_id={user_id}, thread_id={thread_id}, chain_id={chain_id}, df_id={df_id}")
        
        metadata_records = []
        
        # Process primary dataset if df_id exists
        if df_id:
            try:
                response = requests.get(
                    f"{self.base_url}/cache/preview/{df_id}",
                    timeout=10
                )
                if response.status_code == 200:
                    df_data = response.json()
                    df_metadata = df_data.get('metadata', {})
                    
                    # Determine source
                    source = df_metadata.get('source', 'Unknown')
                    if source == 'csv':
                        source = 'CSV'
                    elif source == 'sweatstack':
                        source = 'SweatStack'
                    elif source == 'intervals':
                        source = 'Intervals'
                    elif source == 'endura':
                        source = 'Endura'
                    elif source == 'Unknown' and df_metadata.get('original_filename', '').endswith('.parquet'):
                        source = 'Parquet'
                    
                    record = {
                        'identifier': df_id,
                        'type': 'Primary',
                        'source': source,
                        'original_filename': df_metadata.get('original_filename'),
                        'columns': df_data.get('columns', []),
                        'date_range': df_metadata.get('date_range'),
                        'shape': df_data.get('shape')
                    }
                    metadata_records.append(record)
                    self.log_to_file(f"Primary dataset metadata: {record}")
            except Exception as e:
                self.log_to_file(f"Error getting primary dataset metadata: {str(e)}")
        
        # Process auxiliary datasets (max 3)
        for aux_path in auxiliary_datasets[:3]:
            try:
                response = requests.post(
                    f"{self.base_url}/cache/preview_aux",
                    json={'file_path': aux_path, 'user_id': user_id},
                    timeout=10
                )
                if response.status_code == 200:
                    aux_data = response.json()
                    
                    filename = aux_data.get('filename', '')
                    source = 'CSV'  # Default
                    date_range = None
                    
                    if 'activity_summary_' in filename or 'wellness_data_' in filename or 'activity_intervals_' in filename:
                        source = 'Intervals'
                        # Extract date range from filename
                        import re
                        match = re.search(r'_(\d{8})_to_(\d{8})', filename)
                        if match:
                            start = match.group(1)
                            end = match.group(2)
                            date_range = f"{start[:4]}-{start[4:6]}-{start[6:]} to {end[:4]}-{end[4:6]}-{end[6:]}"
                    if 'athlete_profiles_race_' in filename or 'race_turns_race_' in filename or 'race_climbs_race_' in filename or 'race_waymarkers_race_' in filename:
                        source = 'Endura'
                    
                    record = {
                        'identifier': aux_path,
                        'type': 'Auxiliary',
                        'source': source,
                        'original_filename': filename,
                        'columns': aux_data.get('columns', []),
                        'date_range': date_range,
                        'shape': aux_data.get('shape')
                    }
                    metadata_records.append(record)
                    self.log_to_file(f"Auxiliary dataset metadata: {record}")
            except Exception as e:
                self.log_to_file(f"Error getting auxiliary dataset metadata for {aux_path}: {str(e)}")
        
        # Insert into database
        from bambooai.db.supabase_client import SupabaseClient
        self.supabase_client = SupabaseClient()

        if metadata_records and hasattr(self, 'supabase_client') and self.supabase_client:
            success = self.supabase_client.insert_dataset_metadata(
                bamboo_user_id=user_id,
                thread_id=thread_id,
                chain_id=chain_id,
                metadata_records=metadata_records
            )
            if success:
                self.log_to_file(f"Successfully stored {len(metadata_records)} dataset metadata records in database")
            else:
                self.log_to_file("Failed to store dataset metadata in database")
        else:
            self.log_to_file(f"Metadata collected but not stored in DB (records: {len(metadata_records)}, client available: {hasattr(self, 'supabase_client')})")
        
        return metadata_records
      
        
    def compute_dataframe_sample(self, df_id: str, order_by: str = 'Datetime', ascending: bool = False) -> Optional[pd.DataFrame]:
        """Call the executor API to compute DataFrame index"""
        self.log_to_file(f"Attempting to compute index for df_id={df_id}")
        try:
            response = requests.post(
                f"{self.base_url}/df_utils/compute_df_sample",
                json={
                    'df_id': df_id
                }
            )
            response.raise_for_status()
            result = response.json()
            
            if 'error' in result:
                self.log_to_file(f"Error computing index: {result['error']}")
                return None
                
            self.log_to_file(f"Successfully computed index for df_id={df_id}")
            df = pd.DataFrame(result['data'], columns=result['columns'])
            return df
            
        except requests.RequestException as e:
            self.log_to_file(f"Failed to compute index via API: {str(e)}")
            return None
        
    def aux_page(self, path: str, offset: int = 0, limit: int = 50, order_by: Optional[str] = None, ascending: bool = True) -> Optional[dict]:
        """One page of an auxiliary file on the executor, for the Data tab's grid (None if the image lacks /aux_page)."""
        try:
            r = requests.post(f"{self.base_url}/aux_page", json={'path': path, 'offset': offset, 'limit': limit, 'order_by': order_by, 'ascending': bool(ascending)}, timeout=60)
            if r.status_code == 200:
                return r.json()
            log_to_file(f"aux_page failed: {r.status_code} {r.text[:200]}")
        except Exception as exc:                                # noqa: BLE001
            log_to_file(f"aux_page error: {exc}")
        return None

    def executor_build(self) -> Optional[str]:
        """The executor image's build stamp from /health (None for images before 2026-09-07)."""
        try:
            r = requests.get(f"{self.base_url}/health", timeout=10)
            if r.status_code == 200:
                return (r.json() or {}).get('build')
        except Exception:                                   # noqa: BLE001
            pass
        return None

    def dataframe_page(self, df_id: str, offset: int = 0, limit: int = 50, order_by: Optional[str] = None,
                       ascending: bool = True) -> Optional[Dict[str, Any]]:
        """One page of the cached dataframe (rows as JSON, columns, dtypes, total) for the Data tab."""
        try:
            response = requests.post(f"{self.base_url}/dataframe_page", json={
                'df_id': df_id, 'offset': int(offset), 'limit': int(limit), 'order_by': order_by, 'ascending': bool(ascending)}, timeout=60)
            if response.status_code == 200:
                return response.json()
            self.log_to_file(f"dataframe_page failed: {response.status_code} {response.text[:200]}")
            return None
        except Exception as e:                              # noqa: BLE001
            self.log_to_file(f"dataframe_page error: {e}")
            return None

    def dataframe_summary_to_string(self, df_id: str) -> Optional[str]:
        """Call the executor API to get DataFrame summary"""
        self.log_to_file(f"Attempting to get summary for df_id={df_id}")
        try:
            response = requests.post(
                f"{self.base_url}/df_utils/df_summary",
                json={'df_id': df_id}
            )
            response.raise_for_status()
            result = response.json()
            
            if 'error' in result:
                self.log_to_file(f"Error getting summary: {result['error']}")
                return None
                
            self.log_to_file(f"Successfully got summary for df_id={df_id}")
            return result['data']
            
        except requests.RequestException as e:
            self.log_to_file(f"Failed to get summary via API: {str(e)}")
            return None

    def dataframe_to_string(self, df_id: str, num_rows: int = 5) -> Optional[str]:
        """Call the executor API to convert DataFrame to string"""
        self.log_to_file(f"Attempting to convert to string for df_id={df_id}")
        try:
            response = requests.post(
                f"{self.base_url}/df_utils/df_to_string",
                json={
                    'df_id': df_id,
                    'num_rows': num_rows
                }
            )
            response.raise_for_status()
            result = response.json()
            
            if 'error' in result:
                self.log_to_file(f"Error converting to string: {result['error']}")
                return None
                
            self.log_to_file(f"Successfully converted to string for df_id={df_id}")
            return result['data']
            
        except requests.RequestException as e:
            self.log_to_file(f"Failed to convert to string via API: {str(e)}")
            return None

    def get_dataframe_columns(self, df_id: str) -> Optional[Dict[str, Any]]:
        """Call the executor API to get DataFrame columns"""
        self.log_to_file(f"Attempting to get columns for df_id={df_id}")
        try:
            response = requests.post(
                f"{self.base_url}/df_utils/df_columns",
                json={'df_id': df_id}
            )
            response.raise_for_status()
            result = response.json()
            
            if 'error' in result:
                self.log_to_file(f"Error getting columns: {result['error']}")
                return None
                
            self.log_to_file(f"Successfully got columns for df_id={df_id}")
            return result
            
        except requests.RequestException as e:
            self.log_to_file(f"Failed to get columns via API: {str(e)}")
            return None
        
    def aux_datasets_to_string(self, file_paths: List[str], num_rows: int = 5) -> Optional[str]:
        """Call the executor API to get string representation of auxiliary datasets."""
        self.log_to_file(f"Attempting to get aux datasets string for paths: {file_paths}, num_rows: {num_rows}")
        try:
            response = requests.post(
                f"{self.base_url}/file_utils/aux_datasets_to_string",
                json={'file_paths': file_paths, 'num_rows': num_rows}
            )
            response.raise_for_status()
            result = response.json()
            
            if 'error' in result:
                self.log_to_file(f"Error getting aux datasets string: {result['error']}")
                return None  # Or consider returning result['error'] to propagate the message
                
            self.log_to_file(f"Successfully got aux datasets string for paths: {file_paths}")
            return result.get('data') # Expects {'data': 'output_string'}
            
        except requests.RequestException as e:
            self.log_to_file(f"Failed to get aux datasets string via API: {str(e)}")
            return None

    def get_aux_datasets_columns(self, file_paths: List[str]) -> Optional[str]:
        """Call the executor API to get column names of auxiliary datasets."""
        self.log_to_file(f"Attempting to get aux datasets columns for paths: {file_paths}")
        try:
            response = requests.post(
                f"{self.base_url}/file_utils/get_aux_datasets_columns",
                json={'file_paths': file_paths}
            )
            response.raise_for_status()
            result = response.json()
            
            if 'error' in result:
                self.log_to_file(f"Error getting aux datasets columns: {result['error']}")
                return None
                
            self.log_to_file(f"Successfully got aux datasets columns for paths: {file_paths}")
            return result.get('data') # Expects {'data': 'columns_string'}
            
        except requests.RequestException as e:
            self.log_to_file(f"Failed to get aux datasets columns via API: {str(e)}")
            return None

    def compute_aux_dataset_sample(self, file_paths: List[str], num_rows: int = 100) -> Optional[List[str]]:
        """Call the executor API to compute HTML samples of auxiliary datasets."""
        self.log_to_file(f"Attempting to compute aux dataset sample for paths: {file_paths}, num_rows: {num_rows}")
        try:
            response = requests.post(
                f"{self.base_url}/file_utils/compute_aux_dataset_sample",
                json={'file_paths': file_paths, 'num_rows': num_rows}
            )
            response.raise_for_status()
            result = response.json()
            
            if 'error' in result:
                self.log_to_file(f"Error computing aux dataset sample: {result['error']}")
                return None
                
            self.log_to_file(f"Successfully computed aux dataset sample for paths: {file_paths}")
            return result.get('html_results') # Expects {'html_results': ['html_string1', ...]}
            
        except requests.RequestException as e:
            self.log_to_file(f"Failed to compute aux dataset sample via API: {str(e)}")
            return None