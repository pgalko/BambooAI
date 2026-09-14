#!/bin/bash
# Simple status dashboard

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
echo "🚀 BambooAI System Status Dashboard"
echo "=================================="
echo

# System info
echo "📊 System Overview:"
echo "  Date: $(date)"
echo "  Uptime: $(uptime -p)"
echo "  Load: $(uptime | awk -F'load average:' '{print $2}')"
echo

# Services status
echo "🔧 Services Status:"
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

# Resource usage (SIMPLIFIED - single clean version)
echo "💾 Resource Usage:"
MEMORY_LINE=$(free -h | grep '^Mem:')
MEMORY_USED=$(echo "$MEMORY_LINE" | awk '{print $3}')
MEMORY_TOTAL=$(echo "$MEMORY_LINE" | awk '{print $2}')
MEMORY_PERCENT=$(free | grep '^Mem:' | awk '{printf("%.1f", ($3/$2)*100)}')

echo "  Memory: $MEMORY_USED / $MEMORY_TOTAL (${MEMORY_PERCENT}%)"
echo "  Docker Storage: $(df -h /var/lib/docker | tail -1 | awk '{printf("%s / %s (%s)", $3, $2, $5)}')"
echo "  User Data: $(df -h /home/data | tail -1 | awk '{printf("%s / %s (%s)", $3, $2, $5)}')"
echo

# Container status
echo "🐳 Container Status:"
if curl -s http://localhost:8080/health > /dev/null 2>&1; then
    CONTAINER_DATA=$(curl -s http://localhost:8080/containers 2>/dev/null)
    if [ $? -eq 0 ] && [ -n "$CONTAINER_DATA" ]; then
        ACTIVE_COUNT=$(echo "$CONTAINER_DATA" | jq -r '.count // 0' 2>/dev/null || echo "0")
        echo "  Active Containers: $ACTIVE_COUNT"
        
        # Try to get capacity data
        CAPACITY_DATA=$(curl -s http://localhost:8080/capacity 2>/dev/null)
        if [ $? -eq 0 ] && [ -n "$CAPACITY_DATA" ] && echo "$CAPACITY_DATA" | jq . >/dev/null 2>&1; then
            CAPACITY_PCT=$(echo "$CAPACITY_DATA" | jq -r '.capacity_used_percent // 0' 2>/dev/null || echo "0")
            AVAILABLE=$(echo "$CAPACITY_DATA" | jq -r '.available_slots // 60' 2>/dev/null || echo "60")
            echo "  Capacity Used: ${CAPACITY_PCT}%"
            echo "  Available Slots: $AVAILABLE"
        else
            # Fallback calculation without bc
            MAX_CONTAINERS=60
            AVAILABLE=$((MAX_CONTAINERS - ACTIVE_COUNT))
            if [ $ACTIVE_COUNT -eq 0 ]; then
                CAPACITY_PCT="0.0"
            else
                CAPACITY_PCT=$(awk "BEGIN {printf \"%.1f\", $ACTIVE_COUNT * 100 / $MAX_CONTAINERS}")
            fi
            echo "  Capacity Used: ${CAPACITY_PCT}%"
            echo "  Available Slots: $AVAILABLE"
        fi
    else
        echo "  ❌ Unable to fetch container data"
    fi
else
    echo "  ❌ Orchestrator not responding"
fi
echo

# Recent alerts
echo "🚨 Recent Alerts (last 24h):"
if [ -f "$APP_ROOT_DIR/orchestration/logs/system_monitor.log" ]; then
    YESTERDAY=$(date -d "yesterday" +%Y-%m-%d)
    TODAY=$(date +%Y-%m-%d)
    grep -E "($YESTERDAY|$TODAY).*ALERT:" $APP_ROOT_DIR/orchestration/logs/system_monitor.log | tail -5 | while read line; do
        echo "  ⚠️  $line"
    done | grep -q "ALERT" || echo "  ✅ No recent alerts"
else
    echo "  📊 No monitoring data available"
fi
echo

echo "💡 Quick Commands:"
echo "  View logs: sudo journalctl -u bambooai-orchestrator -f"
echo "  Restart services: ./scripts/start_services.sh"
echo "  System backup: ./scripts/backup_system.sh"
echo "  Health check: curl http://localhost:8080/system/health | jq"