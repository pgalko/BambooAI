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
        with open('code_executor.log', 'a') as f:
            f.write(f"[INFO] {timestamp} - {message}\n")

    def execute_code(self, code: str, 
                    df_id: Optional[str] = None, 
                    patch_code: Optional[str] = None,
                    plots_dir: Optional[str] = None,
                    plot_format: Optional[str] = None,
                    generated_datasets_path: Optional[list] = None) -> Dict[str, Any]:
    
        """Execute code via the executor API"""
        self.log_to_file(f"Starting API execution with DataFrame ID={df_id}")
        
        data = {
            'code': code,
            'df_id': df_id,
            'patch_code': patch_code,
            'plots_dir': plots_dir,
            'plot_format': plot_format,
            'generated_datasets_path': generated_datasets_path
        }

        try:
            self.log_to_file(f"Sending request to {self.base_url}/execute")
            response = requests.post(f"{self.base_url}/execute", json=data)
            response.raise_for_status()
            
            api_result = response.json()
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