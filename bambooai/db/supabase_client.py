import os
import logging
from typing import Optional
try:
    from supabase import create_client, Client
except ImportError:                                     # the self-hosted edition needs no Supabase SDK
    create_client, Client = None, None

from logger_config import get_logger
logger = get_logger(__name__)

class SupabaseClient:
    """Minimal Supabase client for usage tracking with chain/thread support"""
    
    def __init__(self):
        self.client: Optional[Client] = None
        self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Supabase client with service role key"""
        try:
            if os.getenv('AUTH_MODE', 'none') == 'single':      # the self-hosted edition writes no usage rows to Supabase
                logger.info("single-user mode: Supabase not used")
                return
            supabase_url = os.getenv('SUPABASE_URL')
            supabase_key = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
            
            if not supabase_url or not supabase_key:
                logger.warning("Supabase credentials not found in environment variables")
                return
            
            self.client = create_client(supabase_url, supabase_key)
            logger.info("Supabase client initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Supabase client: {e}")
            self.client = None

    def can_continue_exploration(self, bamboo_user_id: str) -> dict:
        """
        Check if user can continue auto-exploration.
        
        Args:
            bamboo_user_id: User identifier (user_id from BambooAI)
            
        Returns:
            dict: {"allowed": bool, "reason": str or None, ...}
        """
        if not self.client:
            return {"allowed": True}
        
        try:
            result = self.client.rpc('can_continue_exploration', {
                'p_bamboo_user_id': bamboo_user_id
            }).execute()
            
            return result.data if result.data else {"allowed": True}
            
        except Exception as e:
            logger.warning(f"can_continue_exploration failed: {e}")
            return {"allowed": True}  # Fail open
    
    def insert_usage_with_chain(self, usage_data: dict, thread_id: str) -> bool:
        """
        Insert a usage record with automatic chain/thread creation
        
        Args:
            usage_data: Dictionary containing usage information
            thread_id: Thread identifier for grouping chains
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.client:
            logger.warning("Supabase client not initialized, skipping database write")
            return False
        
        if not thread_id:
            logger.error("thread_id is required but not provided")
            return False
        
        try:
            result = self.client.rpc('insert_usage_with_chain', {
                'p_usage_data': usage_data,
                'p_thread_id': thread_id
            }).execute()
            
            if result.data and result.data.get('success'):
                logger.debug(f"Usage record inserted successfully")
                return True
            else:
                logger.error(f"Failed to insert usage record")
                return False
                
        except Exception as e:
            error_str = str(e)
            
            # Workaround for Supabase RPC parsing issue
            if ("'code': 200" in error_str and '"success": true' in error_str):
                return True
            
            logger.error(f"Error inserting usage with chain: {e}")
            return False
    
    def insert_usage_record(self, usage_data: dict) -> bool:
        """
        DEPRECATED: Use insert_usage_with_chain instead
        This method is kept for backward compatibility but should not be used
        """
        logger.warning("insert_usage_record is deprecated. Use insert_usage_with_chain instead.")
        return False
    
    def charge_query_completion(self, bamboo_user_id: str, chain_id: str) -> dict:
        """
        Charge for query completion (compute + model costs)
        
        Args:
            bamboo_user_id: User identifier
            chain_id: Unique chain identifier for the query
            
        Returns:
            dict: Result with ok status and charge details
        """
        if not self.client:
            logger.warning("Supabase client not initialized, cannot charge")
            return {"ok": False, "error": "client_not_initialized"}
        
        try:
            # Call the RPC function
            result = self.client.rpc('charge_query_completion', {
                'p_bamboo_user_id': bamboo_user_id,
                'p_chain_id': chain_id
            }).execute()
            
            if result.data:
                charge_data = result.data
                
                if charge_data.get('ok'):
                    if charge_data.get('message') == 'already_processed':
                        logger.debug(f"Charges already processed for chain {chain_id}")
                    elif charge_data.get('message') == 'no_usage_records':
                        logger.debug(f"No usage records found for chain {chain_id}")
                    elif charge_data.get('message') == 'free_tier_no_charge':
                        logger.debug(f"Free tier user, no charge for chain {chain_id}")
                    else:
                        # Check if this was a partial payment
                        if charge_data.get('partial_payment'):
                            logger.warning(
                                f"Partial payment for chain {chain_id} - "
                                f"Full cost: ${charge_data.get('full_cost', 0):.3f}, "
                                f"Charged: ${charge_data.get('total_charged', 0):.3f}, "
                                f"New balance: ${charge_data.get('new_balance', 0):.2f}"
                            )
                        else:
                            logger.info(
                                f"Charged query completion - Chain: {chain_id}, "
                                f"Compute: ${charge_data.get('compute_charged', 0):.3f}, "
                                f"Models: ${charge_data.get('model_charged', 0):.3f}, "
                                f"Total: ${charge_data.get('total_charged', 0):.3f}, "
                                f"New balance: ${charge_data.get('new_balance', 0):.2f}"
                            )
                    return charge_data
                else:
                    logger.error(f"Charge failed: {charge_data.get('error')}")
                    return charge_data
            else:
                logger.error("No data returned from charge_query_completion")
                return {"ok": False, "error": "no_data_returned"}
                
        except Exception as e:
            logger.error(f"Error charging query completion: {e}")
            return {"ok": False, "error": str(e)}
    
    def check_grounding_search_quota(self, query_count: int = 1) -> dict:
        """
        Check and increment the grounding search quota counter
        
        Args:
            query_count: Number of search queries to record (default 1)
        
        Returns:
            dict: Contains 'should_charge', 'current_count', 'quota_limit', 'google_month'
                Returns None if error occurs
        """
        if not self.client:
            logger.warning("Supabase client not initialized, skipping quota check")
            return None
        
        try:
            result = self.client.rpc('check_grounding_search_quota', {
                'p_query_count': query_count
            }).execute()
            
            if result.data:
                logger.debug(f"Grounding quota check: {result.data}")
                return result.data
            else:
                logger.error("No data returned from check_grounding_search_quota")
                return None
                
        except Exception as e:
            logger.error(f"Error checking grounding search quota: {e}")
            return None
        
    def insert_dataset_metadata(self, bamboo_user_id: str, thread_id: str, 
                           chain_id: str, metadata_records: list) -> bool:
        """
        Insert dataset metadata records for a chain
        
        Args:
            bamboo_user_id: User identifier
            thread_id: Thread identifier string
            chain_id: Chain identifier string
            metadata_records: List of metadata dictionaries
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not self.client:
            logger.warning("Supabase client not initialized, skipping metadata insert")
            return False
        
        if not all([bamboo_user_id, thread_id, chain_id]):
            logger.error("Missing required parameters for dataset metadata insert")
            return False
        
        if not metadata_records:
            logger.debug("No metadata records to insert")
            return True  # Not an error, just nothing to do
        
        try:
            # Call the RPC function
            self.client.rpc('insert_dataset_metadata', {
                'p_bamboo_user_id': bamboo_user_id,
                'p_thread_id': thread_id,
                'p_chain_id': chain_id,
                'p_metadata_records': metadata_records
            }).execute()
            
            # If we get here, it succeeded
            logger.info(f"Dataset metadata inserted successfully for chain: {chain_id}")
            return True
                
        except Exception as e:
            logger.error(f"Error inserting dataset metadata: {e}")
            return False
    
    def is_available(self) -> bool:
        """Check if Supabase client is available"""
        return self.client is not None