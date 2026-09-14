#!/bin/bash
# Simple log rotation setup

echo "🔄 Setting up log rotation..."

# Create logrotate configuration for orchestrator
sudo tee /etc/logrotate.d/bambooai-orchestrator << 'EOF'
/home/data/bambooai/orchestration/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 664 palo bambooai-data
    su palo bambooai-data
    postrotate
        /bin/systemctl reload bambooai-orchestrator || true
    endscript
}
EOF

# Test the configuration
sudo logrotate -d /etc/logrotate.d/bambooai-orchestrator

echo "✅ Log rotation configured"
echo "📁 Logs will be rotated daily, keeping 7 days of history"