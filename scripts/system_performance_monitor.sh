#!/bin/bash
# Comprehensive system performance monitoring

# Auto-detect environment based on script location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Load environment variables from new configuration files
if [ -f "/etc/bambooai/system.env" ]; then
    set -a  # Automatically export variables
    source <(grep -v '^#' "/etc/bambooai/system.env" | grep -E '^[A-Z_]+=')
    set +a  # Stop auto-exporting
fi

# Also load shared config for any additional variables
if [ -f "/etc/bambooai/shared.env" ]; then
    set -a
    source <(grep -v '^#' "/etc/bambooai/shared.env" | grep -E '^[A-Z_]+=')
    set +a
fi

LOG_DIR="$APP_ROOT_DIR/orchestration/logs"
PERF_LOG="$LOG_DIR/performance_detailed.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Function to log with timestamp
log_metric() {
    echo "[$TIMESTAMP] $1" >> "$PERF_LOG"
}

echo "🔍 Collecting system performance data..."

# System Resource Metrics
CPU_USAGE=$(top -bn1 | grep "Cpu(s)" | awk '{print $2}' | sed 's/%us,//')
MEMORY_INFO=$(free -m)
MEMORY_USED=$(echo "$MEMORY_INFO" | grep '^Mem:' | awk '{printf "%.1f", $3/1024}')
MEMORY_AVAILABLE=$(echo "$MEMORY_INFO" | grep '^Mem:' | awk '{printf "%.1f", $7/1024}')
LOAD_AVG=$(uptime | awk -F'load average:' '{print $2}' | tr -d ' ')

log_metric "CPU_USAGE_PERCENT:$CPU_USAGE"
log_metric "MEMORY_USED_GB:$MEMORY_USED"
log_metric "MEMORY_AVAILABLE_GB:$MEMORY_AVAILABLE"
log_metric "LOAD_AVERAGE:$LOAD_AVG"

# Docker Metrics
DOCKER_CONTAINERS=$(docker ps -q | wc -l)
DOCKER_IMAGES=$(docker images -q | wc -l)
DOCKER_VOLUMES=$(docker volume ls -q | wc -l)

log_metric "DOCKER_CONTAINERS:$DOCKER_CONTAINERS"
log_metric "DOCKER_IMAGES:$DOCKER_IMAGES"
log_metric "DOCKER_VOLUMES:$DOCKER_VOLUMES"

# Disk Usage
DOCKER_DISK=$(df /var/lib/docker | tail -1 | awk '{print $5}' | sed 's/%//')
HOME_DISK=$(df /home/data | tail -1 | awk '{print $5}' | sed 's/%//')
ROOT_DISK=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')

log_metric "DOCKER_DISK_USAGE_PERCENT:$DOCKER_DISK"
log_metric "HOME_DISK_USAGE_PERCENT:$HOME_DISK"
log_metric "ROOT_DISK_USAGE_PERCENT:$ROOT_DISK"

# Service Status
check_service() {
    if systemctl is-active --quiet "$1"; then
        log_metric "SERVICE_${1^^}_STATUS:UP"
    else
        log_metric "SERVICE_${1^^}_STATUS:DOWN"
    fi
}

check_service "docker"
check_service "consul"
check_service "nomad"
check_service "bambooai-orchestrator"

# Orchestrator Performance Data
ORCH_DATA=$(curl -s http://localhost:8080/monitoring/performance 2>/dev/null)
if [ $? -eq 0 ] && [ ! -z "$ORCH_DATA" ]; then
    # Extract key metrics
    ACTIVE_CONTAINERS=$(echo "$ORCH_DATA" | jq -r '.current_state.active_containers // 0')
    PENDING_SPAWNS=$(echo "$ORCH_DATA" | jq -r '.current_state.pending_spawns // 0')
    SUCCESS_RATE=$(echo "$ORCH_DATA" | jq -r '.spawn_performance.success_rate // 0')
    
    log_metric "ACTIVE_CONTAINERS:$ACTIVE_CONTAINERS"
    log_metric "PENDING_SPAWNS:$PENDING_SPAWNS"
    log_metric "SPAWN_SUCCESS_RATE:$SUCCESS_RATE"
    
    # Spawn time metrics (if available)
    AVG_SPAWN_TIME=$(echo "$ORCH_DATA" | jq -r '.spawn_performance.average_time // null')
    RECENT_SPAWN_TIME=$(echo "$ORCH_DATA" | jq -r '.spawn_performance.recent_average // null')
    
    if [ "$AVG_SPAWN_TIME" != "null" ]; then
        log_metric "AVERAGE_SPAWN_TIME:$AVG_SPAWN_TIME"
    fi
    
    if [ "$RECENT_SPAWN_TIME" != "null" ]; then
        log_metric "RECENT_SPAWN_TIME:$RECENT_SPAWN_TIME"
    fi
else
    log_metric "ORCHESTRATOR_API_STATUS:DOWN"
fi

# Network checks
CONSUL_API=$(curl -s -w "%{http_code}" http://localhost:8500/v1/status/leader -o /dev/null)
NOMAD_API=$(curl -s -w "%{http_code}" http://localhost:4646/v1/status/leader -o /dev/null)
REGISTRY_API=$(curl -s -w "%{http_code}" http://localhost:5000/v2/_catalog -o /dev/null)

log_metric "CONSUL_API_STATUS:$CONSUL_API"
log_metric "NOMAD_API_STATUS:$NOMAD_API"
log_metric "REGISTRY_API_STATUS:$REGISTRY_API"

echo "✅ Performance data logged to: $PERF_LOG"