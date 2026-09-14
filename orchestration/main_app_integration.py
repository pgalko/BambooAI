"""
Integration module for main Flask app with orchestrator
"""
import os
import requests
import logging
from typing import Dict

from logger_config import get_logger
logger = get_logger(__name__)

class ContainerOrchestrator:
    """Client for interacting with the orchestrator API"""
    
    def __init__(self, orchestrator_url: str = None):
        self.orchestrator_url = orchestrator_url or os.getenv('ORCHESTRATOR_API_URL', 'http://localhost:8080')
        self.user_containers: Dict[str, dict] = {}
        
    def get_or_create_container(self, user_id: str, compute_tier: str) -> Dict[str, str]:
        """
        Get or create container for user - delegates all logic to orchestrator
        Returns: {"ip": "x.x.x.x", "port": "5000", "status": "ready"}
        """
        try:
            # Always call spawn - let orchestrator decide if reuse or create          
            spawn_response = requests.post(
                f"{self.orchestrator_url}/spawn/{user_id}",
                json={"compute_tier": compute_tier},
                timeout=180
            )
            spawn_response.raise_for_status()
            
            spawn_data = spawn_response.json()
            if spawn_data["status"] == "ready":
                container_info = {
                    "ip": spawn_data["ip"],
                    "port": spawn_data["port"],
                    "status": "ready",
                    "tier": spawn_data.get("tier", compute_tier),  # Include tier info
                    "action": spawn_data.get("action", "unknown")  # "reused", "created", or "recreated"
                }
                self.user_containers[user_id] = container_info
                
                return container_info
            else:
                raise Exception(f"Failed to get container: {spawn_data.get('error', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"Error getting container for user {user_id}: {str(e)}")
            return {
                "status": "error",
                "error": str(e)
            }
    
    def get_container_status(self, user_id: str) -> Dict[str, str]:
        """
        Get container status with enhanced details for user
        Returns: {"status": "ready/offline", "ip": "...", "port": "...", "uptime_minutes": ..., etc}
        """
        try:
            # Get basic status
            status_response = requests.get(f"{self.orchestrator_url}/status/{user_id}", timeout=5)
            
            if status_response.status_code == 200:
                status_data = status_response.json()
                
                # Add computed details for tooltip if container is ready
                if status_data.get('status') == 'ready':
                    try:
                        # Get container details for uptime calculation
                        containers_response = requests.get(f"{self.orchestrator_url}/containers", timeout=3)
                        if containers_response.status_code == 200:
                            containers_data = containers_response.json()
                            user_container = containers_data.get('active_containers', {}).get(user_id)
                            
                            if user_container and 'created_at' in user_container:
                                from datetime import datetime
                                created_at = datetime.fromisoformat(user_container['created_at'])
                                uptime_seconds = (datetime.now() - created_at).total_seconds()
                                
                                # Use actual RAM from status_data if available, otherwise fallback
                                ram_gb = status_data.get('ram_gb', 16)
                                
                                # Add enhanced details
                                status_data.update({
                                    'ram_allocated': f'{ram_gb}GB',
                                    'uptime_minutes': max(1, int(uptime_seconds / 60)),
                                    'job_id': status_data.get('job_id')
                                })
                    except Exception as detail_error:
                        logger.debug(f"Could not get container details: {detail_error}")
                        # Still return the basic status even if details fail
                
                return status_data
            else:
                logger.warning(f"Orchestrator returned status {status_response.status_code} for user {user_id}")
                return {
                    'status': 'offline',
                    'error': f'Orchestrator returned {status_response.status_code}'
                }
                
        except requests.RequestException as e:
            logger.error(f"Failed to connect to orchestrator: {str(e)}")
            return {
                'status': 'offline',
                'error': 'Cannot connect to orchestrator'
            }
        except Exception as e:
            logger.error(f"Container status check failed: {str(e)}")
            return {
                'status': 'offline', 
                'error': str(e)
            }
    
    def restart_container(self, user_id: str, compute_tier: str) -> Dict[str, str]:
        """
        Restart container for user (destroy + spawn)
        Returns: {"status": "success/error", "message": "...", "container_status": "..."}
        """
        try:
            logger.info(f"Restarting container for user {user_id}")
            
            # First destroy the current container
            destroy_response = requests.delete(f"{self.orchestrator_url}/destroy/{user_id}", timeout=10)
            
            if destroy_response.status_code != 200:
                logger.warning(f"Destroy returned {destroy_response.status_code}, continuing with spawn")
            
            # Clear cached container info
            if user_id in self.user_containers:
                del self.user_containers[user_id]
            
            # Then spawn a new container
            spawn_response = requests.post(
                f"{self.orchestrator_url}/spawn/{user_id}",
                json={"compute_tier": compute_tier},  # Pass tier in request body
                timeout=180
            )
            
            if spawn_response.status_code == 200:
                spawn_data = spawn_response.json()
                
                # Cache the new container info
                if spawn_data.get('status') == 'ready':
                    self.user_containers[user_id] = {
                        "ip": spawn_data.get('ip'),
                        "port": spawn_data.get('port'),
                        "status": "ready"
                    }
                
                logger.info(f"Container restarted successfully for user {user_id}")
                return {
                    'status': 'success',
                    'message': 'Container restarted successfully',
                    'container_status': spawn_data.get('status', 'ready')
                }
            else:
                logger.error(f"Spawn failed with status {spawn_response.status_code}")
                return {
                    'status': 'error',
                    'error': f'Failed to spawn new container: {spawn_response.status_code}'
                }
                
        except requests.RequestException as e:
            logger.error(f"Container restart failed for user {user_id}: {str(e)}")
            return {
                'status': 'error',
                'error': f'Network error during restart: {str(e)}'
            }
        except Exception as e:
            logger.error(f"Container restart failed for user {user_id}: {str(e)}")
            return {
                'status': 'error',
                'error': str(e)
            }