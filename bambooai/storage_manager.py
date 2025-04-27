from dataclasses import dataclass, field
from typing import Dict, List, Optional
import json
from pathlib import Path
import time
import os
import tempfile
import shutil
import platform
from contextlib import contextmanager
import codecs

@dataclass
class Tools:
    search: Dict = field(default_factory=lambda: {
        'searches': []  # List of search triplets with query, result, and links
    })
    code_exec: Dict = field(default_factory=lambda: {
        'executed_code': None,
        'code_exec_results': None,
        'plot_jsons': []
    })

@dataclass
class Chain:
    chain_id: str
    timestamp: float
    messages: Dict[str, List[Dict]] = field(default_factory=lambda: {
        'pre_eval_messages': [],
        'select_analyst_messages': [],
        'eval_messages': [],
        'df_inspector_messages': [],
        'code_messages': [],
        'plan_review_messages': [],
        'insight_messages': []
    })
    tools: Tools = field(default_factory=Tools)

class StorageError(Exception):
    """Custom exception for storage-related errors"""
    pass

class SimpleInteractionStore:
    def __init__(self, storage_dir: str = None):
        """
        Initialize the interaction store with a storage directory.
        
        Args:
            storage_dir: Base directory for storing interactions. If None, creates
                        'storage' directory in the current working directory
        """
        if storage_dir is None:
            # Create storage directory in the current working directory
            self.storage_dir = Path(os.getcwd()) / 'storage'
        else:
            self.storage_dir = Path(storage_dir).resolve()

        self._initialize_storage()

    def _initialize_storage(self) -> None:
        """
        Safely create storage directory structure.
        Handles potential permission and existence issues.
        """
        try:
            threads_dir = self.storage_dir / "threads"
            threads_dir.mkdir(parents=True, exist_ok=True)
            
            # Test write permissions by creating and removing a temporary file
            test_file = threads_dir / '.write_test'
            try:
                test_file.touch()
                test_file.unlink()
            except OSError:
                raise StorageError(f"No write permission in {threads_dir}")

        except Exception as e:
            raise StorageError(f"Failed to initialize storage: {str(e)}")

    @contextmanager
    def _atomic_write(self, filepath: Path):
        """
        Context manager for atomic file writes using a temporary file.
        Ensures proper Unicode handling across platforms.
        """
        # Create temporary file in the same directory
        temp_dir = filepath.parent
        try:
            # Use a random suffix to avoid collisions
            temp_suffix = f'.{os.urandom(6).hex()}.tmp'
            temp_path = Path(temp_dir) / f"{filepath.stem}{temp_suffix}"
            
            # Open with explicit UTF-8 encoding using codecs
            with codecs.open(str(temp_path), 'w', encoding='utf-8') as tmp_file:
                yield tmp_file

            # On Windows, we need to remove the destination file first
            if platform.system() == 'Windows' and filepath.exists():
                filepath.unlink()
            
            # Rename temporary file to target file
            shutil.move(str(temp_path), str(filepath))

        except Exception as e:
            # Clean up temporary file if something goes wrong
            if 'temp_path' in locals() and temp_path.exists():
                temp_path.unlink()
            raise StorageError(f"Failed to write file: {str(e)}")

    def _get_thread_file(self, thread_id: str) -> Path:
        """
        Get the path for a thread file, ensuring thread_id is filesystem safe.
        """
        # Clean thread_id to be filesystem safe
        safe_id = "".join(c for c in thread_id if c.isalnum() or c in '-_')
        return self.storage_dir / "threads" / f"{safe_id}.json"

    def _load_thread_data(self, thread_file: Path) -> dict:
        """
        Safely load thread data from file with error handling.
        """
        try:
            if thread_file.exists():
                # Use codecs to ensure proper UTF-8 handling
                with codecs.open(str(thread_file), 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {'chains': {}}
        except json.JSONDecodeError as e:
            # If file is corrupted, backup and start fresh
            if thread_file.exists():
                backup_file = thread_file.with_suffix('.json.bak')
                shutil.copy2(thread_file, backup_file)
            return {'chains': {}}
        except Exception as e:
            raise StorageError(f"Failed to load thread data: {str(e)}")

    def store_interaction(self, 
                        thread_id: str,
                        chain_id: str,
                        messages: Dict[str, List[Dict]],
                        tool_results: Dict[str, Dict]) -> None:
        """
        Store a complete interaction chain to a thread file.
        
        Args:
            thread_id: Unique identifier for the thread
            chain_id: Unique identifier for this specific interaction
            messages: Dictionary containing all message types and their contents
            tool_results: Dictionary containing results from tools
        
        Raises:
            StorageError: If there's any issue with storage operations
        """
        try:
            thread_file = self._get_thread_file(thread_id)
            thread_data = self._load_thread_data(thread_file)

            # Create new chain
            chain = Chain(
                chain_id=chain_id,
                timestamp=time.time(),
            )
            
            # Add messages
            for msg_type, msg_list in messages.items():
                if msg_list:  # Only store non-empty message lists
                    chain.messages[msg_type] = msg_list

            # Add tool results
            if tool_results.get('search') is not None:
                chain.tools.search = tool_results['search']
            if 'code_exec' in tool_results:
                chain.tools.code_exec.update(tool_results['code_exec'])

            # Add chain to thread data
            thread_data['chains'][chain_id] = {
                'chain_id': chain.chain_id,
                'timestamp': chain.timestamp,
                'messages': chain.messages,
                'tools': {
                    'search': chain.tools.search,
                    'code_exec': chain.tools.code_exec
                }
            }

            # Atomic write to file
            with self._atomic_write(thread_file) as tmp_file:
                json_str = json.dumps(thread_data, indent=2, ensure_ascii=False)
                tmp_file.write(json_str)

        except Exception as e:
            raise StorageError(f"Failed to store interaction: {str(e)}")
        
    def restore_interaction(self, thread_id: str, chain_id: str) -> Dict:
        """
        Restore messages and code execution results from a specific chain in a thread file.
        
        Args:
            thread_id: Identifier for the thread to restore
            chain_id: Identifier for specific chain to restore
        
        Returns:
            Dictionary containing messages and code execution results for the specified chain
            
        Raises:
            StorageError: If thread/chain not found or other storage issues
        """
        if not thread_id or not chain_id:
            raise StorageError("Both thread_id and chain_id must be provided")

        try:
            thread_file = self._get_thread_file(thread_id)
            if not thread_file.exists():
                raise StorageError(f"Thread file not found: {thread_file}")

            thread_data = self._load_thread_data(thread_file)
            
            # Get the specified chain
            if chain_id not in thread_data['chains']:
                raise StorageError(f"Chain not found: {chain_id}")

            chain_data = thread_data['chains'][chain_id]
            
            # Extract messages and code execution results
            message_data = chain_data['messages']
            
            # Return the data in the expected structure
            return {
                'pre_eval_messages': message_data.get('pre_eval_messages', []),
                'select_analyst_messages': message_data.get('select_analyst_messages', []),
                'eval_messages': message_data.get('eval_messages', []),
                'df_inspector_messages': message_data.get('df_inspector_messages', []),
                'code_messages': message_data.get('code_messages', []),
                'plan_review_messages': message_data.get('plan_review_messages', []),
                'insight_messages': message_data.get('insight_messages', []),
                'code_exec_results': chain_data['tools']['code_exec'].get('code_exec_results', ''),
                'executed_code': chain_data['tools']['code_exec'].get('executed_code', ''),
                'qa_pairs': chain_data['tools']['code_exec'].get('qa_pairs', []),
                'tasks': chain_data['tools']['code_exec'].get('tasks', [])
            }

        except Exception as e:
            raise StorageError(f"Failed to restore interaction: {str(e)}")