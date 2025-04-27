# executor_client.py

import requests
import pandas as pd
from typing import Optional, Dict, Any, Union
from datetime import datetime

class ExecutorAPIClient:
    def __init__(self, base_url: str = None):
        self.base_url = base_url
        
    def log_to_file(self, message):
        """Write log message to file with timestamp"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        with open('code_executor.log', 'a') as f:
            f.write(f"[INFO] {timestamp} - {message}\n")

    def execute_code(self, code: str, df_id: Optional[str] = None, 
                    patch_code: Optional[str] = None,
                    plots_dir: Optional[str] = None,
                    plot_format: Optional[str] = None) -> Dict[str, Any]:
        """Execute code via the executor API"""
        self.log_to_file(f"Starting API execution with DataFrame ID={df_id}")
        
        data = {
            'code': code,
            'df_id': df_id,
            'patch_code': patch_code,
            'plots_dir': plots_dir,
            'plot_format': plot_format
        }

        try:
            self.log_to_file(f"Sending request to {self.base_url}/execute")
            response = requests.post(f"{self.base_url}/execute", json=data)
            response.raise_for_status()
            
            api_result = response.json()
            has_results = bool(api_result.get('results'))
            has_error = bool(api_result.get('error'))
            num_plots = len(api_result.get('plot_images', []))
            
            self.log_to_file(
                f"Received API response - "
                f"Results: {'Yes' if has_results else 'No'}, "
                f"Errors: {'Yes' if has_error else 'No'}, "
                f"Plots: {num_plots}"
            )

            return api_result
            
        except requests.RequestException as e:
            self.log_to_file(f"Failed to execute code via API: {str(e)}")
            return {
                'results': None,
                'error': str(e),
                'plot_images': []
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