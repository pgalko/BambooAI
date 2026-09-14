"""
Standalone orchestrator API service
Provides HTTP API for container lifecycle management
"""
from flask import Flask, jsonify, request
from container_manager import ContainerManager
import sys
import os
from datetime import datetime
import requests
from dotenv import load_dotenv

# Configure logging

# Add parent directory to path to find logger_config  
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logger_config import setup_logging, get_logger

# Initialize logging for this standalone service
setup_logging()

# Then get the logger
logger = get_logger(__name__)

# Load environment variables from .env in project root
project_root = os.environ.get('APP_ROOT_DIR', os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
env_path = os.path.join(project_root, '.env')
load_dotenv(env_path)

# Configuration from environment variables
ORCHESTRATOR_PORT = int(os.getenv('ORCHESTRATOR_PORT', 8080))

"""Factory function to create orchestrator Flask app"""
app = Flask(__name__)

# Initialize container manager with environment-specific settings
_container_manager = None

def get_container_manager():
    global _container_manager
    if _container_manager is None:
        _container_manager = ContainerManager(
            nomad_url=os.getenv('NOMAD_URL', 'http://localhost:4646'),
            total_memory_mb=int(os.getenv('TOTAL_CONTAINER_MEMORY_MB', 1007616)),  # 984GB
        )
    return _container_manager
    
@app.route('/health', methods=['GET'])
def health():
    """Orchestrator health check"""
    return jsonify({
        "status": "healthy",
        "service": "bambooai-orchestrator",
        "timestamp": datetime.now().isoformat(),
        "active_containers": len(get_container_manager().active_containers),
        "version": "1.0.0"
    })

@app.route('/system/health', methods=['GET'])
def system_health():
    """Comprehensive system health check"""
    try:
        health_data = {
            "timestamp": datetime.now().isoformat(),
            "status": "healthy",
            "services": {},
            "capacity": get_container_manager().get_system_capacity(),
            "containers": {
                "active": len(get_container_manager().active_containers),
                "details": get_container_manager().active_containers
            }
        }
        
        # Check service dependencies
        services_to_check = [
            ("docker", "http://localhost:2376/version"),
            ("nomad", "http://localhost:4646/v1/status/leader"),
            ("consul", "http://localhost:8500/v1/status/leader"),
            ("registry", "http://localhost:5000/v2/_catalog")
        ]
        
        overall_healthy = True
        for service_name, health_url in services_to_check:
            try:
                if service_name == "docker":
                    # Use docker command instead of API
                    import subprocess
                    result = subprocess.run(['docker', 'info'], capture_output=True, timeout=5)
                    service_healthy = result.returncode == 0
                else:
                    response = requests.get(health_url, timeout=3)
                    service_healthy = response.status_code == 200
                
                health_data["services"][service_name] = {
                    "status": "healthy" if service_healthy else "unhealthy",
                    "checked_at": datetime.now().isoformat()
                }
                
                if not service_healthy:
                    overall_healthy = False
                    
            except Exception as e:
                health_data["services"][service_name] = {
                    "status": "unhealthy",
                    "error": str(e),
                    "checked_at": datetime.now().isoformat()
                }
                overall_healthy = False
        
        if not overall_healthy:
            health_data["status"] = "degraded"
            
        status_code = 200 if overall_healthy else 503
        return jsonify(health_data), status_code
        
    except Exception as e:
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 503

@app.route('/spawn/<user_id>', methods=['POST'])
def spawn_container(user_id: str):
    """Spawn a container for the user"""
    logger.info(f"Spawn request for user: {user_id}")
    
    # Validate user_id
    if not user_id or user_id == 'null':
        return jsonify({"error": "Invalid user_id"}), 400
    
    # Get compute tier from request body
    data = request.get_json() or {}
    user_compute_tier = data.get('compute_tier', 'free')  # Default to 'free' if not provided
    
    # Spawn container with tier
    result = get_container_manager().spawn_container(user_id, user_compute_tier)
    
    if result["status"] == "ready":
        logger.info(f"Container spawned successfully for user {user_id}: {result['ip']}:{result['port']}")
        return jsonify(result), 200
    else:
        logger.error(f"Failed to spawn container for user {user_id}: {result.get('error', 'Unknown error')}")
        return jsonify(result), 500

@app.route('/status/<user_id>', methods=['GET'])
def get_status(user_id: str):
    """Get container status for user"""
    result = get_container_manager().get_container_status(user_id)
    return jsonify(result), 200

@app.route('/destroy/<user_id>', methods=['DELETE'])
def destroy_container(user_id: str):
    """Manually destroy user's container"""
    logger.info(f"Destroy request for user: {user_id}")
    result = get_container_manager().destroy_container(user_id)
    
    if result["status"] in ["destroyed", "not_found"]:
        return jsonify(result), 200
    else:
        return jsonify(result), 500

@app.route('/containers', methods=['GET'])
def list_containers():
    """List all active containers (for monitoring)"""
    active_containers = get_container_manager().list_active_containers()
    return jsonify({
        "active_containers": active_containers,
        "count": len(active_containers),
        "timestamp": datetime.now().isoformat()
    })

@app.route('/metrics', methods=['GET'])
def metrics():
    """Basic metrics for monitoring"""
    active_containers = get_container_manager().list_active_containers()
    return jsonify({
        "total_containers": len(active_containers),
        "containers_by_status": {
            "active": len(active_containers)
        },
        "timestamp": datetime.now().isoformat()
    })

@app.route('/activity/<user_id>', methods=['POST'])
def update_activity(user_id: str):
    """Update user activity timestamp"""
    try:
        get_container_manager().update_user_activity(user_id)
        logger.info(f"Updated activity for user {user_id}")
        return jsonify({"status": "updated", "user_id": user_id}), 200
    except Exception as e:
        logger.error(f"Failed to update activity for user {user_id}: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

@app.route('/cleanup', methods=['POST'])
def force_cleanup():
    """Force immediate cleanup of idle containers"""
    try:
        get_container_manager()._cleanup_idle_containers()
        return jsonify({"status": "cleanup_completed"}), 200
    except Exception as e:
        return jsonify({"status": "error", "error": str(e)}), 500
    
@app.route('/capacity', methods=['GET'])
def get_capacity():
    """Get system capacity information"""
    try:
        capacity = get_container_manager().get_system_capacity()
        return jsonify(capacity), 200
    except Exception as e:
        logger.error(f"Error getting capacity: {e}")
        return jsonify({"error": str(e)}), 500
    
@app.route('/monitoring/performance', methods=['GET'])
def get_performance_monitoring():
    """Comprehensive performance monitoring endpoint"""
    try:
        # Get performance stats from container manager
        perf_stats = get_container_manager().get_performance_stats()
        
        # Add system resource info
        import psutil
        import subprocess
        
        # Memory info
        memory = psutil.virtual_memory()
        perf_stats["system_resources"] = {
            "memory": {
                "total_gb": round(memory.total / (1024**3), 1),
                "available_gb": round(memory.available / (1024**3), 1),
                "used_percent": memory.percent
            },
            "cpu": {
                "usage_percent": psutil.cpu_percent(interval=1),
                "load_average": psutil.getloadavg()
            }
        }
        
        # Docker info
        try:
            docker_info = subprocess.run(['docker', 'info', '--format', '{{.Containers}}'], 
                                    capture_output=True, text=True, timeout=5)
            if docker_info.returncode == 0:
                perf_stats["docker"] = {
                    "total_containers": int(docker_info.stdout.strip())
                }
        except:
            perf_stats["docker"] = {"error": "Unable to get Docker info"}
        
        return jsonify(perf_stats), 200
        
    except Exception as e:
        logger.error(f"Error getting performance monitoring: {e}")
        return jsonify({"error": str(e), "timestamp": datetime.now().isoformat()}), 500

@app.route('/monitoring/trends', methods=['GET'])
def get_performance_trends():
    """Get performance trends over time"""
    try:
        # Get last 24 hours of data from logs
        trends = {
            "timestamp": datetime.now().isoformat(),
            "spawn_trends": [],
            "resource_trends": []
        }
        
        # Read recent spawn data from metrics
        recent_spawns = list(get_container_manager().metrics["spawn_times"])[-50:]
        
        # Group by hour for trends
        hourly_data = {}
        for spawn in recent_spawns:
            spawn_time = datetime.fromisoformat(spawn["timestamp"])
            hour_key = spawn_time.strftime("%Y-%m-%d %H:00")
            
            if hour_key not in hourly_data:
                hourly_data[hour_key] = {"times": [], "failures": 0}
            
            if spawn["success"]:
                hourly_data[hour_key]["times"].append(spawn["duration"])
            else:
                hourly_data[hour_key]["failures"] += 1
        
        # Calculate hourly averages
        for hour, data in hourly_data.items():
            if data["times"]:
                trends["spawn_trends"].append({
                    "hour": hour,
                    "average_time": sum(data["times"]) / len(data["times"]),
                    "spawn_count": len(data["times"]),
                    "failure_count": data["failures"]
                })
        
        return jsonify(trends), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# Factory function for Gunicorn
def create_orchestrator_app():
    """Factory function for Gunicorn"""
    return app

# Entry points
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=ORCHESTRATOR_PORT, debug=False, threaded=True)
else:
    application = create_orchestrator_app()