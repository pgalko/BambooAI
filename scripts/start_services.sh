#!/bin/bash
# BambooAI Services Startup Script

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

set -e

echo "🚀 Starting BambooAI Services..."

# Check prerequisites
echo "📋 Checking prerequisites..."
systemctl is-active --quiet docker || { echo "❌ Docker not running"; exit 1; }
systemctl is-active --quiet nomad || { echo "❌ Nomad not running"; exit 1; }
systemctl is-active --quiet consul || { echo "❌ Consul not running"; exit 1; }
echo "✅ Prerequisites checked"

# Start orchestrator
echo "🔧 Starting orchestrator..."
sudo systemctl start bambooai-orchestrator

# Wait for orchestrator to be ready
echo "⏳ Waiting for orchestrator to be ready..."
for i in {1..30}; do
    if curl -s http://localhost:8080/health > /dev/null 2>&1; then
        echo "✅ Orchestrator is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ Orchestrator failed to start"
        sudo journalctl -u bambooai-orchestrator -n 10 --no-pager
        exit 1
    fi
    sleep 1
done

# Start webapp
echo "🌐 Starting web application..."
sudo systemctl start bambooai-webapp

# Wait for webapp to be ready
echo "⏳ Waiting for webapp to be ready..."
for i in {1..30}; do
    if curl -s -k https://localhost:5001/ > /dev/null 2>&1 || curl -s http://localhost:5001/ > /dev/null 2>&1; then
        echo "✅ Web application is ready"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ Web application failed to start"
        sudo journalctl -u bambooai-webapp -n 10 --no-pager
        exit 1
    fi
    sleep 1
done

# Check system status
echo ""
echo "📊 System Status:"
echo "  Docker: $(systemctl is-active docker)"
echo "  Nomad: $(systemctl is-active nomad)"
echo "  Consul: $(systemctl is-active consul)"
echo "  Orchestrator: $(systemctl is-active bambooai-orchestrator)"
echo "  Web Application: $(systemctl is-active bambooai-webapp)"

# Check capacity
echo ""
echo "🐳 Container Capacity:"
if curl -s http://localhost:8080/containers > /dev/null 2>&1; then
    CONTAINER_COUNT=$(curl -s http://localhost:8080/containers | jq -r '.count' 2>/dev/null || echo "Unable to parse")
    echo "  Active containers: $CONTAINER_COUNT"
    
    # Show max capacity if available
    if [ -n "$MAX_CONTAINERS" ]; then
        echo "  Maximum containers: $MAX_CONTAINERS"
    fi
else
    echo "  ⚠️  Unable to query container status"
fi

# Service URLs
echo ""
echo "🌐 Service URLs:"
echo "  Orchestrator API: http://localhost:8080/"
echo "  Consul UI: http://localhost:8500/"
if [ "$SSL_ENABLED" = "true" ]; then
    echo "  Web Application: https://localhost:5001/"
else
    echo "  Web Application: http://localhost:5001/"
fi

echo ""
echo "✅ All services ready!"
echo ""
echo "🔧 Manual troubleshooting commands:"
echo "  Activate virtual environment: source /home/data/bambooai-venv/bin/activate"
echo "  Start webapp manually: cd $APP_ROOT_DIR/web_app && gunicorn -c webapp_gunicorn.conf.py --log-level debug app:application"
echo "  Start orchestrator manually: cd $APP_ROOT_DIR/orchestration && gunicorn -c orchestrator_gunicorn.conf.py --log-level debug orchestrator_api:application"
echo ""
echo "📋 Service management commands:"
echo "  Check status: sudo systemctl status bambooai-webapp bambooai-orchestrator"
echo "  View logs: sudo journalctl -u bambooai-webapp -f"
echo "  Restart services: sudo systemctl restart bambooai-webapp bambooai-orchestrator"
