#!/bin/bash
# BambooAI Services Stop Script

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

echo "🛑 Stopping BambooAI Services..."

# Clean up any remaining containers before stopping orchestrator
echo "🧹 Cleaning up containers..."
if curl -s -X POST http://localhost:8080/cleanup 2>/dev/null; then
    echo "✅ Container cleanup completed"
    sleep 2  # Give containers time to stop
else
    echo "⚠️  Orchestrator cleanup endpoint not available (service may already be stopped)"
fi

# Stop web application first
echo "🌐 Stopping web application..."
if systemctl is-active --quiet bambooai-webapp; then
    sudo systemctl stop bambooai-webapp
    echo "✅ Web application stopped"
else
    echo "ℹ️  Web application was not running"
fi

# Stop orchestrator
echo "🔧 Stopping orchestrator..."
if systemctl is-active --quiet bambooai-orchestrator; then
    sudo systemctl stop bambooai-orchestrator
    echo "✅ Orchestrator stopped"
else
    echo "ℹ️  Orchestrator was not running"
fi

# Additional cleanup - remove any orphaned containers
echo "🧽 Performing additional cleanup..."
ORPHANED=$(docker ps -q --filter "label=bambooai" 2>/dev/null || true)
if [ -n "$ORPHANED" ]; then
    echo "🗑️  Removing orphaned containers..."
    docker stop $ORPHANED 2>/dev/null || true
    docker rm $ORPHANED 2>/dev/null || true
    echo "✅ Orphaned containers cleaned up"
else
    echo "ℹ️  No orphaned containers found"
fi

# Final status check
echo ""
echo "📊 Final Status:"
echo "  Web Application: $(systemctl is-active bambooai-webapp)"
echo "  Orchestrator: $(systemctl is-active bambooai-orchestrator)"

# Count remaining containers
REMAINING=$(docker ps -q --filter "label=bambooai" 2>/dev/null | wc -l)
echo "  Remaining containers: $REMAINING"

if [ "$REMAINING" -eq 0 ]; then
    echo "✅ All services stopped successfully"
else
    echo "⚠️  Some containers may still be running"
    docker ps --filter "label=bambooai" --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
fi

echo ""
echo "🔧 Manual cleanup commands (if needed):"
echo "  Check service status: sudo systemctl status bambooai-webapp bambooai-orchestrator"
echo "  Force stop containers: docker stop \$(docker ps -q --filter 'label=bambooai')"
echo "  Remove containers: docker rm \$(docker ps -aq --filter 'label=bambooai')"
echo "  View service logs: sudo journalctl -u bambooai-orchestrator -n 20"
