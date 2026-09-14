import re
import html
import gzip
import base64
import json
import os
import glob

from logger_config import get_logger
logger = get_logger(__name__)

def decompress_content(compressed_data):
    """
    Python equivalent of the JS decompressContent function.
    Handles both compressed (base64 gzipped) and uncompressed content.
    """
    if not compressed_data:
        return compressed_data
    
    try:
        # Check if data looks uncompressed (contains HTML/JSON markers or is too short)
        if ('<' in compressed_data or 
            '{' in compressed_data or 
            len(compressed_data) < 100):
            return compressed_data
        
        # Try to decode as base64 gzipped data
        compressed_bytes = base64.b64decode(compressed_data)
        decompressed_bytes = gzip.decompress(compressed_bytes)
        return decompressed_bytes.decode('utf-8')
        
    except Exception:
        # If decompression fails, assume it was stored uncompressed
        return compressed_data

def extract_python_code(document_text):
    """
    Extract Python code from the content-code section.
    Mirrors the JS querySelector('code').textContent approach.
    """
    pattern = r'<div id="content-code"[^>]*>.*?<code[^>]*>(.*?)</code>'
    match = re.search(pattern, document_text, re.DOTALL)
    
    if not match:
        return None
    
    # Get raw content and clean it
    code_content = html.unescape(match.group(1))
    
    # Remove only actual HTML span tags used for syntax highlighting
    clean_code = re.sub(r'<span[^>]*>|</span>', '', code_content)
    
    return clean_code.strip()

def get_python_code_from_chain(thread_id, chain_id, user_path_func):
    """
    Main function to retrieve and extract Python code from a stored chain.
    
    Args:
        thread_id: Thread identifier
        chain_id: Chain identifier
        user_path_func: The user_path function from the calling module
    
    Returns:
        str: Extracted Python code or None if not found
    """
    try:
        # Build path to chain file using the passed user_path function
        thread_path = user_path_func('storage', 'favourites', thread_id)
        chain_files = glob.glob(os.path.join(thread_path, f'{chain_id}.json'))
        
        if not chain_files:
            return None
        
        # Load the chain data
        with open(chain_files[0], 'r') as f:
            chain_data = json.load(f)
        
        # Get contentOutput (may be compressed)
        content_output = chain_data.get('contentOutput', '')
        
        if not content_output:
            return None
        
        # Decompress if needed
        decompressed_content = decompress_content(content_output)
        
        # Extract Python code
        python_code = extract_python_code(decompressed_content)
        
        return python_code
        
    except Exception as e:
        logger.error(f"Error extracting Python code: {e}")
        return None
    
def replace_dataset_paths(code, dataset_mappings):
    """
    Replace dataset paths in code based on mappings.
    
    Args:
        code: Original Python code
        dataset_mappings: Dict mapping old filenames to new filenames/paths
    
    Returns:
        Modified code with updated paths
    """
    if not dataset_mappings or not code:
        return code
    
    modified_code = code
    
    for old_filename, new_path in dataset_mappings.items():
        # Extract just the filenames
        old_name = os.path.basename(old_filename)
        new_name = os.path.basename(new_path)
        
        logger.info(f"Replacing: {old_name} -> {new_name}")
        
        # Pattern 1: Direct string references with quotes
        # "TSLA.csv" or 'TSLA.csv' -> "new_file.csv"
        patterns = [
            (rf'(["\']){re.escape(old_name)}(["\'])', rf'\1{new_name}\2'),
            (rf'(["\'])([^"\']*?){re.escape(old_name)}(["\'])', rf'\1\2{new_name}\3'),
        ]
        
        for pattern, replacement in patterns:
            modified_code = re.sub(pattern, replacement, modified_code)
        
        # Pattern 2: os.path.join - need to preserve the structure
        # os.path.join(ds_dir, "TSLA.csv") -> os.path.join(ds_dir, "new_file.csv")
        join_pattern = rf'(os\.path\.join\([^,]+,\s*["\']){re.escape(old_name)}(["\'])'
        modified_code = re.sub(join_pattern, rf'\1{new_name}\2', modified_code)
        
        # Pattern 3: f-strings
        # f"{path}/TSLA.csv" -> f"{path}/new_file.csv"
        fstring_pattern = rf'(f["\'][^"\']*?){re.escape(old_name)}([^"\']*?["\'])'
        modified_code = re.sub(fstring_pattern, rf'\1{new_name}\2', modified_code)
    
    return modified_code