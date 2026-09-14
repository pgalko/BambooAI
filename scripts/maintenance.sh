#!/bin/bash
# Simple maintenance operations

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

ACTION="${1:-help}"

case "$ACTION" in
    "help")
        echo "🛠️  BambooAI Maintenance Script"
        echo "Usage: $0 {cleanup|backup|status|restart|logs}"
        echo
        echo "Commands:"
        echo "  cleanup  - Clean up unused Docker resources and old logs"
        echo "  backup   - Create system backup"
        echo "  status   - Show system status"
        echo "  restart  - Restart all services"
        echo "  logs     - Show recent logs"
        ;;
        
    "cleanup")
        echo "🧹 Starting system cleanup..."
        
        # Clean Docker resources
        echo "🐳 Cleaning Docker resources..."
        docker system prune -f
        docker volume prune -f
        
        # Clean old logs
        echo "📝 Cleaning old logs..."
        find $APP_ROOT_DIR/orchestration/logs/ -name "*.log.*" -mtime +7 -delete
        
        # Clean old backups (keep only 7)
        echo "💾 Cleaning old backups..."
        cd $APP_ROOT_DIR/backups 2>/dev/null && ls -t *.tar.gz 2>/dev/null | tail -n +8 | xargs -r rm
        
        # Force container cleanup
        echo "🔄 Force container cleanup..."
        curl -s -X POST http://localhost:8080/cleanup > /dev/null
        
        echo "✅ Cleanup completed"
        ;;
        
    "backup")
        echo "💾 Creating backup..."
        ./scripts/backup_system.sh
        ;;
        
    "status")
        ./scripts/status_dashboard.sh
        ;;
        
    "restart")
        echo "🔄 Restarting services..."
        ./scripts/stop_services.sh
        sleep 5
        ./scripts/start_services.sh
        ;;
        
    "logs")
        echo "📝 Recent orchestrator logs:"
        sudo journalctl -u bambooai-orchestrator --since "1 hour ago" -n 20
        ;;
        
    *)
        echo "❌ Unknown action: $ACTION"
        echo "Use '$0 help' for available commands"
        exit 1
        ;;
esac