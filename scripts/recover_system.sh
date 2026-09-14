#!/bin/bash
# Simple recovery script

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

if [ $# -ne 1 ]; then
    echo "Usage: $0 <backup_file.tar.gz>"
    echo "Available backups:"
    ls -la /home/data/backups/*.tar.gz 2>/dev/null || echo "No backups found"
    exit 1
fi

BACKUP_FILE="$1"
if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "⚠️  WARNING: This will restore system configuration from backup"
echo "📁 Backup file: $BACKUP_FILE"
read -p "Continue? (y/N): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Recovery cancelled"
    exit 1
fi

echo "🛑 Stopping services..."
sudo systemctl stop bambooai-orchestrator nomad consul

echo "📂 Extracting backup..."
TEMP_DIR="/tmp/recovery_$(date +%s)"
mkdir -p "$TEMP_DIR"
cd "$TEMP_DIR"
tar -xzf "$BACKUP_FILE"

# Find the extracted directory
BACKUP_DIR=$(find . -maxdepth 1 -type d -name "bambooai_backup_*" | head -1)
if [ -z "$BACKUP_DIR" ]; then
    echo "❌ Invalid backup format"
    exit 1
fi

echo "🔄 Restoring configurations..."
sudo cp -r "$BACKUP_DIR/consul.d/"* /etc/consul.d/
sudo cp -r "$BACKUP_DIR/nomad.d/"* /etc/nomad.d/
sudo cp -r "$BACKUP_DIR/docker/"* /etc/docker/
sudo cp "$BACKUP_DIR/bambooai-orchestrator.service" /etc/systemd/system/

echo "🔄 Restoring application files..."
cp -r "$BACKUP_DIR/bambooai" $APP_ROOT_DIR/

echo "🔄 Reloading systemd and starting services..."
sudo systemctl daemon-reload
sudo systemctl start consul
sleep 5
sudo systemctl start nomad
sleep 5
sudo systemctl start bambooai-orchestrator

echo "✅ Recovery completed"
echo "🔍 Check service status:"
echo "  sudo systemctl status consul nomad bambooai-orchestrator"
echo "  curl http://localhost:8080/system/health"

# Cleanup
cd /
rm -rf "$TEMP_DIR"