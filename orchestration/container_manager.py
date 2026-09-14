"""
Container lifecycle management using Nomad with tier-based resource allocation
"""
import threading
import requests
import time
import sys
import os
import subprocess
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import logging
from collections import deque
from dotenv import load_dotenv

# Configure logging
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logger_config import get_logger
logger = get_logger(__name__)

class ContainerManager:
    def __init__(self, 
             nomad_url: str = "http://localhost:4646",
             total_memory_mb: int = None):
        
        # Load environment-specific configuration
        self.nomad_url = nomad_url
        
        # Memory management configuration
        # Default: 1TB total - 40GB reserved = 984GB for containers
        self.total_memory_mb = total_memory_mb or int(os.getenv('TOTAL_CONTAINER_MEMORY_MB', 1007616))  # 984GB in MB
        
        # Tier configuration
        self.tier_config = {
            'free': {
                'memory': 4096,   # 4GB
                'cpu': 200,       # 0.2 cores
                'cpu_threads': 2,
                'limit_ratio': 0.6,  # Can use up to 60% of total capacity
                'idle_time': 1800   # 30 minutes
            },
            'plus': {
                'memory': 8192,   # 8GB
                'cpu': 400,       # 0.4 cores
                'cpu_threads': 3,
                'limit_ratio': 0.7,  # Can use up to 70% of total capacity
                'idle_time': 2700   # 45 minutes
            },
            'pro': {
                'memory': 16384,  # 16GB
                'cpu': 800,       # 0.8 cores
                'cpu_threads': 4,
                'limit_ratio': 1.0,  # Can use 100% of capacity
                'idle_time': 3600   # 60 minutes
            }
        }
        
        # When system utilization exceeds this, tier limits kick in
        self.pressure_threshold = float(os.getenv('PRESSURE_THRESHOLD', 0.7))  # 70%
        
        self.active_containers: Dict[str, dict] = {}
        self.user_last_activity: Dict[str, datetime] = {}
        
        # Start with clean slate
        self._startup_cleanup()
        
        # Start cleanup daemon
        self._start_cleanup_daemon()

        # Performance tracking
        self.metrics = {
            "spawn_times": deque(maxlen=100),
            "spawn_start_times": {},
            "tier_rejections": {'free': 0, 'plus': 0, 'pro': 0}  # Track rejections per tier
        }
    
    def _can_spawn_container(self, tier: str) -> Tuple[bool, str]:
        """
        Check if a container of given tier can be spawned based on capacity rules.
        Returns (allowed, reason_if_denied)
        """
        if tier not in self.tier_config:
            return False, f"Invalid tier: {tier}"
        
        tier_memory = self.tier_config[tier]['memory']
        
        # Calculate current memory usage
        total_used = sum(c.get('memory', 0) for c in self.active_containers.values())
        tier_used = sum(c.get('memory', 0) for c in self.active_containers.values() 
                       if c.get('tier') == tier)
        
        # Check if adding this container would exceed total capacity
        if total_used + tier_memory > self.total_memory_mb:
            return False, "System at absolute capacity"
        
        # Calculate system utilization
        current_utilization = total_used / self.total_memory_mb
        
        logger.info(f"Capacity check for {tier}: current_util={current_utilization:.2%}, "
                   f"total_used={total_used}MB, tier_used={tier_used}MB")
        
        # If system is under pressure threshold, allow any tier
        if current_utilization < self.pressure_threshold:
            return True, "System under pressure threshold"
        
        # System is under pressure, check tier-specific limits
        tier_limit_ratio = self.tier_config[tier]['limit_ratio']
        tier_limit_mb = self.total_memory_mb * tier_limit_ratio
        
        # Check if tier would exceed its limit
        if tier_used + tier_memory > tier_limit_mb:
            self.metrics['tier_rejections'][tier] += 1
            return False, f"{tier.title()} tier limit reached ({tier_limit_ratio:.0%} of capacity)"
        
        return True, "Within tier limits"
    
    def get_capacity_status(self) -> dict:
        """Get detailed capacity status including tier breakdowns"""
        total_used = sum(c.get('memory', 0) for c in self.active_containers.values())
        
        # Calculate per-tier usage
        tier_usage = {
            'free': sum(c.get('memory', 0) for c in self.active_containers.values() 
                       if c.get('tier') == 'free'),
            'plus': sum(c.get('memory', 0) for c in self.active_containers.values() 
                       if c.get('tier') == 'plus'),
            'pro': sum(c.get('memory', 0) for c in self.active_containers.values() 
                      if c.get('tier') == 'pro')
        }
        
        tier_counts = {
            'free': sum(1 for c in self.active_containers.values() if c.get('tier') == 'free'),
            'plus': sum(1 for c in self.active_containers.values() if c.get('tier') == 'plus'),
            'pro': sum(1 for c in self.active_containers.values() if c.get('tier') == 'pro')
        }
        
        utilization = total_used / self.total_memory_mb
        
        return {
            "total_memory_mb": self.total_memory_mb,
            "total_used_mb": total_used,
            "total_available_mb": self.total_memory_mb - total_used,
            "utilization_percent": round(utilization * 100, 1),
            "pressure_mode": utilization >= self.pressure_threshold,
            "tier_usage_mb": tier_usage,
            "tier_counts": tier_counts,
            "tier_limits_mb": {
                tier: int(self.total_memory_mb * config['limit_ratio'])
                for tier, config in self.tier_config.items()
            },
            "rejections": self.metrics['tier_rejections']
        }
    
    def spawn_container(self, user_id: str, user_compute_tier: str) -> Dict[str, str]:
        """Spawn container with tier-based resource allocation"""
        # Start timing
        start_time = time.time()
        self.metrics["spawn_start_times"][user_id] = start_time
        
        # Validate and default tier
        if user_compute_tier not in self.tier_config:
            logger.warning(f"Invalid tier {user_compute_tier} for user {user_id}, defaulting to free")
            user_compute_tier = 'free'
        
        # Update user activity
        self.update_user_activity(user_id)
        
        # Check capacity based on tier
        can_spawn, reason = self._can_spawn_container(user_compute_tier)
        if not can_spawn:
            logger.warning(f"Cannot spawn {user_compute_tier} container for {user_id}: {reason}")
            return {
                "status": "error",
                "error": reason,
                "user_id": user_id,
                "tier": user_compute_tier
            }
        
        try:
            logger.info(f"Spawning {user_compute_tier} container for user: {user_id}")
            
            # Check if user already has an active container
            if user_id in self.active_containers:
                existing = self.active_containers[user_id]
                
                # Check if tier changed
                if existing.get('tier') != user_compute_tier:
                    logger.info(f"User {user_id} tier changed from {existing.get('tier')} to {user_compute_tier}, destroying old container")
                    self.destroy_container(user_id)
                    # Continue to create new container with new tier
                    action = "recreated"  # Track that we recreated due to tier change
                elif self._verify_container_health(existing):
                    logger.info(f"User {user_id} already has active {user_compute_tier} container")
                    
                    # Record reuse
                    total_time = time.time() - start_time
                    self._record_spawn_time(user_id, total_time, "reused")
                    
                    return {
                        "ip": existing["ip"],
                        "port": existing["port"],
                        "job_id": existing["job_id"],
                        "status": "ready",
                        "user_id": user_id,
                        "tier": user_compute_tier,
                        "action": "reused"  # Indicate we reused existing
                    }
                else:
                    # Remove stale entry and create new
                    del self.active_containers[user_id]
                    action = "created"  # New container due to unhealthy state
            else:
                action = "created"  # Brand new container
            
            # Get tier configuration
            tier_cfg = self.tier_config[user_compute_tier]
            
            # Construct tier-specific job template name
            job_template = f"bambooai-executor-{user_compute_tier}"
            
            # Dispatch to the tier-specific job
            dispatch_payload = {
                "Meta": {
                    "user_id": user_id,
                    "session_id": f"session-{user_id}-{int(time.time())}"
                }
            }
            
            response = requests.post(
                f"{self.nomad_url}/v1/job/{job_template}/dispatch",  # Using local job_template variable
                json=dispatch_payload,
                timeout=30
    )
            response.raise_for_status()
            
            job_id = response.json()["DispatchedJobID"]
            logger.info(f"Dispatched {user_compute_tier} job: {job_id} for user: {user_id}")
            
            # Wait for container to be ready
            container_info = self._wait_for_container_ready(job_id, user_id, timeout=120)
            
            # Store active container info with tier and memory
            self.active_containers[user_id] = {
                "job_id": job_id,
                "ip": container_info["ip"],
                "port": container_info["port"],
                "created_at": datetime.now().isoformat(),
                "status": "ready",
                "tier": user_compute_tier,
                "memory": tier_cfg['memory'],  # Store memory for capacity tracking
                "cpu": tier_cfg['cpu']
            }
            
            # Record successful spawn
            total_time = time.time() - start_time
            self._record_spawn_time(user_id, total_time, "success")
            
            # Log capacity after spawn
            capacity = self.get_capacity_status()
            logger.info(f"Container ready for {user_id} ({user_compute_tier}): "
                       f"{container_info['ip']}:{container_info['port']} "
                       f"(took {total_time:.2f}s). "
                       f"System at {capacity['utilization_percent']}% capacity")
            
            return {
                "ip": container_info["ip"],
                "port": container_info["port"],
                "job_id": job_id,
                "status": "ready",
                "user_id": user_id,
                "tier": user_compute_tier,
                "action": action
            }
            
        except Exception as e:
            # Record failed spawn
            total_time = time.time() - start_time
            self._record_spawn_time(user_id, total_time, "failed")
            
            logger.error(f"Failed to spawn {user_compute_tier} container for {user_id} after {total_time:.2f}s: {str(e)}")
            return {
                "status": "error",
                "error": str(e),
                "user_id": user_id,
                "tier": user_compute_tier
            }
    
    def destroy_container(self, user_id: str) -> Dict[str, str]:
        """Destroy container and free up capacity"""
        if user_id not in self.active_containers:
            return {"status": "not_found", "user_id": user_id}
        
        try:
            container = self.active_containers[user_id]
            job_id = container["job_id"]
            freed_memory = container.get('memory', 0)
            tier = container.get('tier', 'unknown')
            
            # Stop the job
            result = subprocess.run(['nomad', 'job', 'stop', job_id], 
                                capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0:
                logger.info(f"Stopped job {job_id} for user {user_id}, freed {freed_memory}MB ({tier} tier)")
            else:
                logger.warning(f"Failed to stop job {job_id}: {result.stderr}")
            
            # Remove from tracking
            del self.active_containers[user_id]
            if user_id in self.user_last_activity:
                del self.user_last_activity[user_id]
            
            # Log capacity after cleanup
            capacity = self.get_capacity_status()
            logger.info(f"After destroying container: System at {capacity['utilization_percent']}% capacity")
            
            return {"status": "destroyed", "user_id": user_id, "freed_memory_mb": freed_memory}
            
        except Exception as e:
            logger.error(f"Failed to destroy container for user {user_id}: {e}")
            return {"status": "error", "error": str(e), "user_id": user_id}
    
    # Keep all other methods unchanged
    def _start_cleanup_daemon(self):
        """Start background cleanup process"""
        cleanup_thread = threading.Thread(target=self._cleanup_daemon, daemon=True)
        cleanup_thread.start()
        logger.info("Started container cleanup daemon")
        
    def _cleanup_daemon(self):
        """Background process to cleanup idle containers every 5 minutes"""
        while True:
            try:
                self._cleanup_idle_containers()
                time.sleep(300)  # Check every 5 minutes
            except Exception as e:
                logger.error(f"Cleanup daemon error: {e}")
                time.sleep(60)  # Wait 1 minute on error

    def _startup_cleanup(self):
        """Clean up any orphaned containers/jobs on startup"""
        try:
            logger.info("Performing startup cleanup...")
            
            # Stop all dispatch jobs
            subprocess.run(['bash', '-c', 
                'nomad job status | grep "dispatch.*running" | awk \'{print $1}\' | xargs -I {} nomad job stop {} || true'
            ], timeout=30)
            
            # Clean Docker containers
            subprocess.run(['bash', '-c',
                'docker stop $(docker ps -q --filter "ancestor=localhost:5000/bambooai-executor:latest") 2>/dev/null || true'
            ], timeout=30)
            
            subprocess.run(['bash', '-c',
                'docker rm $(docker ps -aq --filter "ancestor=localhost:5000/bambooai-executor:latest") 2>/dev/null || true'
            ], timeout=30)
            
            logger.info("Startup cleanup completed")
        
        except Exception as e:
            logger.warning(f"Startup cleanup failed: {e}")
    
    def _cleanup_idle_containers(self):
        """Clean up containers that have exceeded their tier's idle time"""
        current_time = datetime.now()
        cleanup_candidates = []
        
        logger.info(f"Running cleanup check. Active containers: {len(self.active_containers)}")
        
        # Log current capacity
        capacity = self.get_capacity_status()
        logger.info(f"Current capacity: {capacity['utilization_percent']}% "
                f"(Free: {capacity['tier_counts']['free']}, "
                f"Plus: {capacity['tier_counts']['plus']}, "
                f"Pro: {capacity['tier_counts']['pro']})")
        
        for user_id, container_info in self.active_containers.items():
            # Get tier-specific idle time limit
            tier = container_info.get('tier', 'free')
            max_idle_time = self.tier_config.get(tier, {}).get('idle_time', 1800)  # Default 30min
            
            # Get last activity time
            last_activity = self.user_last_activity.get(user_id)
            
            if last_activity is None:
                container_created = datetime.fromisoformat(container_info.get('created_at', current_time.isoformat()))
                idle_time = (current_time - container_created).total_seconds()
                logger.warning(f"No activity recorded for user {user_id}, using creation time")
            else:
                idle_time = (current_time - last_activity).total_seconds()
            
            logger.info(f"User {user_id} ({tier}): idle for {idle_time:.0f}s (limit: {max_idle_time}s)")
            
            if idle_time > max_idle_time:
                cleanup_candidates.append(user_id)
                logger.info(f"Marking user {user_id} ({tier}) for cleanup (idle: {idle_time:.0f}s > limit: {max_idle_time}s)")
        
        # Clean up idle containers
        for user_id in cleanup_candidates:
            try:
                logger.info(f"Cleaning up idle container for user {user_id}")
                result = self.destroy_container(user_id)
                if result["status"] == "destroyed":
                    logger.info(f"Successfully cleaned up container for user {user_id}")
                else:
                    logger.warning(f"Cleanup failed for user {user_id}: {result}")
            except Exception as e:
                logger.error(f"Failed to cleanup container for user {user_id}: {e}")

    def update_user_activity(self, user_id: str):
        """Update user activity timestamp"""
        self.user_last_activity[user_id] = datetime.now()
        logger.debug(f"Updated activity timestamp for user {user_id}")
    
    def _wait_for_container_ready(self, job_id: str, user_id: str, timeout: int = 120) -> Dict[str, str]:
        """Wait for container to be healthy and return IP/port"""
        start_time = time.time()
        
        logger.info(f"Waiting for container {job_id} to be ready...")
        
        while time.time() - start_time < timeout:
            try:
                # Get job allocations
                allocs_response = requests.get(f"{self.nomad_url}/v1/job/{job_id}/allocations")
                allocs = allocs_response.json()
                
                logger.info(f"Found {len(allocs)} allocations for job {job_id}")
                
                for alloc in allocs:
                    logger.info(f"Allocation {alloc['ID']}: Status = {alloc['ClientStatus']}")
                    
                    if alloc["ClientStatus"] == "running":
                        # Get allocation details for network info
                        alloc_detail_response = requests.get(
                            f"{self.nomad_url}/v1/allocation/{alloc['ID']}"
                        )
                        alloc_detail = alloc_detail_response.json()
                        
                        # Extract IP and port from Resources.Networks
                        networks = alloc_detail.get("Resources", {}).get("Networks", [])
                        logger.info(f"Networks found: {len(networks)}")
                        
                        if networks:
                            network = networks[0]
                            ip = network["IP"]
                            
                            # Find the dynamic port for our service
                            dynamic_ports = network.get("DynamicPorts", [])
                            logger.info(f"Dynamic ports: {dynamic_ports}")
                            
                            for port_info in dynamic_ports:
                                if port_info["Label"] == "executor":
                                    port = port_info["Value"]
                                    logger.info(f"Testing health check: {ip}:{port}")
                                    
                                    # Verify container is healthy
                                    if self._check_container_health(ip, port):
                                        logger.info(f"Container healthy: {ip}:{port}")
                                        return {"ip": ip, "port": str(port)}
                                    else:
                                        logger.warning(f"Container not healthy yet: {ip}:{port}")
                
                # Check every 5 seconds
                time.sleep(5)
                
            except Exception as e:
                logger.warning(f"Error checking container status: {e}")
                time.sleep(5)
        
        raise TimeoutError(f"Container for user {user_id} not ready within {timeout}s")
    
    def _check_container_health(self, ip: str, port: int) -> tuple[bool, int]:
        """Verify container is healthy and get RAM allocation"""
        try:
            response = requests.get(f"http://{ip}:{port}/health", timeout=5)
            if response.status_code == 200:
                data = response.json()
                is_healthy = data.get("status") == "healthy"
                ram_gb = data.get("ram_gb", 0)  # Get RAM from health check
                return is_healthy, ram_gb
        except:
            pass
        return False, 0

    def _verify_container_health(self, container_info: dict) -> tuple[bool, int]:
        """Verify that a cached container is still healthy and get RAM"""
        return self._check_container_health(container_info["ip"], int(container_info["port"]))

    def get_container_status(self, user_id: str) -> Dict[str, str]:
        """Get status of user's container"""
        if user_id not in self.active_containers:
            return {"status": "not_found", "user_id": user_id}
        
        container = self.active_containers[user_id]
        
        # Check if container is still healthy and get RAM
        is_healthy, ram_gb = self._verify_container_health(container)
        
        if is_healthy:
            return {
                "status": "ready",
                "ip": container["ip"],
                "port": container["port"],
                "job_id": container["job_id"],
                "tier": container.get("tier", "unknown"),
                "ram_gb": ram_gb,  # Add actual RAM
                "user_id": user_id
            }
        else:
            # Container is not healthy, remove from active list
            logger.warning(f"Container for user {user_id} is no longer healthy, destroying")
            self.destroy_container(user_id)
            return {"status": "failed", "user_id": user_id}
    
    def list_active_containers(self) -> Dict[str, dict]:
        """List all active containers with health check"""
        active = {}
        stale_users = []
        
        for user_id, container in self.active_containers.items():
            if self._verify_container_health(container):
                active[user_id] = container
            else:
                stale_users.append(user_id)
        
        # Remove stale entries
        for user_id in stale_users:
            del self.active_containers[user_id]
            logger.info(f"Removed stale container entry for user: {user_id}")
        
        return active
    
    def _record_spawn_time(self, user_id: str, duration: float, status: str):
        """Record spawn time for performance tracking"""
        self.metrics["spawn_times"].append({
            "user_id": user_id,
            "duration": duration,
            "timestamp": datetime.now().isoformat(),
            "status": status  # "success", "failed", or "reused"
        })
        
        # Clean up tracking
        if user_id in self.metrics["spawn_start_times"]:
            del self.metrics["spawn_start_times"][user_id]

    def get_performance_stats(self) -> dict:
        """Get performance statistics including tier-based metrics"""
        now = datetime.now()
        
        # Analyze spawn times
        all_spawns = list(self.metrics["spawn_times"])
        successful = [s for s in all_spawns if s["status"] == "success"]
        failed = [s for s in all_spawns if s["status"] == "failed"]
        reused = [s for s in all_spawns if s["status"] == "reused"]
        
        # Get current capacity
        capacity = self.get_capacity_status()
        
        stats = {
            "timestamp": now.isoformat(),
            "capacity": capacity,
            "spawn_performance": {
                "total_attempts": len(all_spawns),
                "successful": len(successful),
                "failed": len(failed),
                "reused": len(reused)
            },
            "current_state": {
                "active_containers": len(self.active_containers),
                "pending_spawns": len(self.metrics["spawn_start_times"])
            }
        }
        
        # Calculate timing statistics for successful spawns
        if successful:
            times = [s["duration"] for s in successful]
            stats["spawn_performance"]["timing"] = {
                "average": sum(times) / len(times),
                "min": min(times),
                "max": max(times),
                "recent_average": sum([s["duration"] for s in successful[-10:]]) / min(10, len(successful))
            }
        
        return stats