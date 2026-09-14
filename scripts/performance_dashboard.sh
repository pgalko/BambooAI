#!/bin/bash
# Clean Performance Dashboard - Fixed Memory Calculation

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

clear
echo "📊 BambooAI Performance Analysis Dashboard"
echo "========================================="
echo

# Live service status
echo "🔧 Service Status:"
services=("docker" "consul" "nomad" "bambooai-orchestrator")
for service in "${services[@]}"; do
    STATUS=$(systemctl is-active "$service" 2>/dev/null)
    case "$STATUS" in
        "active")
            echo "  ✅ $service: running"
            ;;
        "activating")
            echo "  🔄 $service: starting"
            ;;
        "inactive"|"failed")
            echo "  ❌ $service: stopped"
            ;;
        *)
            echo "  ⚠️  $service: $STATUS"
            ;;
    esac
done
echo

# API health
echo "🌐 API Health:"
apis=(
    "Consul:http://localhost:8500/v1/status/leader"
    "Nomad:http://localhost:4646/v1/status/leader"
    "Orchestrator:http://localhost:8080/health"
    "Registry:http://localhost:5000/v2/_catalog"
)

for api in "${apis[@]}"; do
    name=$(echo "$api" | cut -d: -f1)
    url=$(echo "$api" | cut -d: -f2-)
    status=$(curl -s -w "%{http_code}" "$url" -o /dev/null 2>/dev/null)
    echo "  $name: HTTP $status"
done
echo

# Performance data
echo "⚡ Performance Metrics:"
perf_response=$(curl -s http://localhost:8080/monitoring/performance 2>/dev/null)
if [ $? -eq 0 ] && echo "$perf_response" | jq . >/dev/null 2>&1; then
    ACTIVE_CONTAINERS=$(echo "$perf_response" | jq -r '.current_state.active_containers // 0')
    PENDING_SPAWNS=$(echo "$perf_response" | jq -r '.current_state.pending_spawns // 0')
    TOTAL_ATTEMPTS=$(echo "$perf_response" | jq -r '.spawn_performance.total_attempts // 0')
    SUCCESSFUL=$(echo "$perf_response" | jq -r '.spawn_performance.successful // 0')
    FAILED=$(echo "$perf_response" | jq -r '.spawn_performance.failed // 0')
    
    echo "  Active Containers: $ACTIVE_CONTAINERS"
    echo "  Pending Spawns: $PENDING_SPAWNS"
    echo "  Total Attempts: $TOTAL_ATTEMPTS"
    echo "  Successful: $SUCCESSFUL"
    echo "  Failed: $FAILED"
    
    # Calculate success rate
    if [ "$TOTAL_ATTEMPTS" -gt 0 ]; then
        SUCCESS_RATE=$(awk "BEGIN {printf \"%.1f\", $SUCCESSFUL * 100 / $TOTAL_ATTEMPTS}")
        echo "  Success Rate: ${SUCCESS_RATE}%"
    fi
    
    # Timing data if available
    AVG_TIME=$(echo "$perf_response" | jq -r '.spawn_performance.timing.average // null')
    RECENT_TIME=$(echo "$perf_response" | jq -r '.spawn_performance.timing.recent_average // null')
    
    if [ "$AVG_TIME" != "null" ]; then
        printf "  Average Spawn Time: %.2fs\n" "$AVG_TIME"
    fi
    
    if [ "$RECENT_TIME" != "null" ]; then
        printf "  Recent Average: %.2fs\n" "$RECENT_TIME"
    fi
else
    echo "  ❌ Performance data unavailable"
fi
echo

# System capacity
echo "📊 System Capacity:"
cap_response=$(curl -s http://localhost:8080/capacity 2>/dev/null)
if [ $? -eq 0 ] && echo "$cap_response" | jq . >/dev/null 2>&1; then
    CAPACITY_USED=$(echo "$cap_response" | jq -r '.capacity_used_percent // 0')
    AVAILABLE_SLOTS=$(echo "$cap_response" | jq -r '.available_slots // 60')
    MAX_CONTAINERS=$(echo "$cap_response" | jq -r '.max_containers // 60')
    
    echo "  Capacity Used: ${CAPACITY_USED}%"
    echo "  Available Slots: $AVAILABLE_SLOTS"
    echo "  Max Containers: $MAX_CONTAINERS"
else
    echo "  ❌ Capacity data unavailable"
fi
echo

# FIXED: System Resources (using the working approach from status_dashboard.sh)
echo "💾 System Resources:"
MEMORY_LINE=$(free -h | grep '^Mem:')
MEMORY_USED=$(echo "$MEMORY_LINE" | awk '{print $3}')
MEMORY_TOTAL=$(echo "$MEMORY_LINE" | awk '{print $2}')
MEMORY_PERCENT=$(free | grep '^Mem:' | awk '{printf("%.1f", ($3/$2)*100)}')

echo "  Memory: $MEMORY_USED / $MEMORY_TOTAL (${MEMORY_PERCENT}%)"
echo "  Docker Storage: $(df -h /var/lib/docker | tail -1 | awk '{printf("%s / %s (%s)", $3, $2, $5)}')"
echo "  User Data: $(df -h /home/data | tail -1 | awk '{printf("%s / %s (%s)", $3, $2, $5)}')"
echo "  Load Average: $(uptime | awk -F'load average:' '{print $2}' | xargs)"
echo "  Docker Containers: $(docker ps -q | wc -l)"
echo

# Performance history (simplified, no complex log parsing)
echo "📈 Performance Summary:"
if [ -f "$APP_ROOT_DIR/orchestration/logs/performance_detailed.log" ]; then
    LOG_SIZE=$(wc -l < $APP_ROOT_DIR/orchestration/logs/performance_detailed.log)
    LAST_UPDATE=$(stat -c %y $APP_ROOT_DIR/orchestration/logs/performance_detailed.log 2>/dev/null | cut -d. -f1)
    echo "  Monitoring log entries: $LOG_SIZE"
    echo "  Last monitoring update: $LAST_UPDATE"
    
    # Simple alert check (last 24 hours)
    YESTERDAY=$(date -d "yesterday" +%Y-%m-%d)
    TODAY=$(date +%Y-%m-%d)
    RECENT_ALERTS=$(grep -E "($YESTERDAY|$TODAY).*ALERT:" $APP_ROOT_DIR/orchestration/logs/performance_detailed.log 2>/dev/null | wc -l)
    
    if [ "$RECENT_ALERTS" -gt 0 ]; then
        echo "  ⚠️  Recent alerts (24h): $RECENT_ALERTS"
    else
        echo "  ✅ No alerts in last 24 hours"
    fi
else
    echo "  📊 No performance history available"
fi
echo

echo "💡 Performance Commands:"
echo "  Test container spawn: curl -X POST http://localhost:8080/spawn/test_user"
echo "  Live performance data: curl http://localhost:8080/monitoring/performance | jq"
echo "  System health check: curl http://localhost:8080/system/health | jq"
echo "  Force cleanup: curl -X POST http://localhost:8080/cleanup"
echo "  Generate monitoring data: ./scripts/system_performance_monitor.sh"