#!/bin/bash
# Simple system monitoring - run via cron

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

LOG_FILE="$APP_ROOT_DIR/orchestration/logs/system_monitor.log"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

# Function to log with timestamp
log_metric() {
    echo "[$TIMESTAMP] $1" >> "$LOG_FILE"
}

# System metrics
MEMORY_USED_PCT=$(free | grep Mem | awk '{printf("%.1f", $3/$2 * 100.0)}')
DISK_USED_PCT=$(df /var/lib/docker | tail -1 | awk '{print $5}' | sed 's/%//')
CONTAINER_COUNT=$(curl -s http://localhost:8080/containers 2>/dev/null | jq -r '.count // 0')

# Log metrics
log_metric "MEMORY_USED_PCT:$MEMORY_USED_PCT"
log_metric "DISK_USED_PCT:$DISK_USED_PCT"
log_metric "CONTAINER_COUNT:$CONTAINER_COUNT"

# Check for issues
if (( $(echo "$MEMORY_USED_PCT > 90" | bc -l) )); then
    log_metric "ALERT:HIGH_MEMORY_USAGE:$MEMORY_USED_PCT%"
fi

if (( DISK_USED_PCT > 85 )); then
    log_metric "ALERT:HIGH_DISK_USAGE:$DISK_USED_PCT%"
fi

if (( CONTAINER_COUNT > 50 )); then
    log_metric "ALERT:HIGH_CONTAINER_COUNT:$CONTAINER_COUNT"
fi

# Service health check
if ! curl -s http://localhost:8080/health > /dev/null; then
    log_metric "ALERT:ORCHESTRATOR_DOWN"
fi