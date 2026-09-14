#!/bin/bash
# Simple backup script for essential data - Concise logging version

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

BACKUP_DIR="/home/data/backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="bambooai_backup_$DATE"
START_TIME=$(date)

# Structured logging function
log_result() {
    local status=$1
    local component=$2
    local details=$3
    
    case $status in
        "SUCCESS") echo "[$(date '+%Y-%m-%d %H:%M:%S')] [OK] $component: $details" ;;
        "WARNING") echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WARN] $component: $details" ;;
        "ERROR")   echo "[$(date '+%Y-%m-%d %H:%M:%S')] [ERROR] $component: $details" ;;
        "INFO")    echo "[$(date '+%Y-%m-%d %H:%M:%S')] [INFO] $component: $details" ;;
    esac
}

# Initialize counters
SUCCESS_COUNT=0
WARNING_COUNT=0
ERROR_COUNT=0

log_result "INFO" "BACKUP_START" "Starting backup: $BACKUP_NAME"

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Create temporary staging area
STAGING_DIR="/tmp/$BACKUP_NAME"
mkdir -p "$STAGING_DIR"

# Backup essential configurations
CONFIG_COUNT=0

# Backup new configuration structure
if [ -d "/etc/bambooai" ]; then
    cp -r /etc/bambooai "$STAGING_DIR/" && ((CONFIG_COUNT++)) && ((SUCCESS_COUNT++))
else
    log_result "WARNING" "CONFIG" "/etc/bambooai not found"
    ((WARNING_COUNT++))
fi

# Function to backup config with counter
backup_config() {
    local source=$1
    local name=$2
    
    if [ -e "$source" ]; then
        cp -r "$source" "$STAGING_DIR/" 2>/dev/null && ((CONFIG_COUNT++)) && ((SUCCESS_COUNT++))
    else
        ((WARNING_COUNT++))
    fi
}

# Backup configurations (silent unless error)
backup_config "/etc/consul.d" "consul.d"
backup_config "/etc/nomad.d" "nomad.d" 
backup_config "/etc/docker" "docker"
backup_config "/etc/ssl/bambooai/certs" "ssl-certs"
backup_config "/etc/systemd/system/bambooai-orchestrator.service" "orchestrator-service"
backup_config "/etc/systemd/system/bambooai-webapp.service" "webapp-service"
backup_config "/etc/systemd/system/nomad.service" "nomad-service"
backup_config "/etc/systemd/system/consul.service" "consul-service"

log_result "SUCCESS" "CONFIG" "$CONFIG_COUNT configuration items backed up"

# Package inventory
if dpkg -l > "$STAGING_DIR/installed_packages.txt" 2>/dev/null; then
    log_result "SUCCESS" "PACKAGES" "Package list captured ($(wc -l < "$STAGING_DIR/installed_packages.txt") packages)"
    ((SUCCESS_COUNT++))
else
    log_result "ERROR" "PACKAGES" "Failed to capture package list"
    ((ERROR_COUNT++))
fi

# Services info
if systemctl list-unit-files --state=enabled > "$STAGING_DIR/enabled_services.txt" 2>/dev/null; then
    systemctl list-units --type=service --state=active >> "$STAGING_DIR/enabled_services.txt" 2>/dev/null
    ENABLED_COUNT=$(grep -c 'enabled' "$STAGING_DIR/enabled_services.txt" 2>/dev/null || echo "0")
    log_result "SUCCESS" "SERVICES" "Service states captured ($ENABLED_COUNT enabled services)"
    ((SUCCESS_COUNT++))
else
    log_result "ERROR" "SERVICES" "Failed to capture service states"
    ((ERROR_COUNT++))
fi

# Backup app data
APP_BACKED_UP=false
if [ -n "$APP_ROOT_DIR" ] && [ -d "$APP_ROOT_DIR" ]; then
    if rsync -aq --exclude="*.log" --exclude="__pycache__" --exclude="temp/*" --exclude=".git" "$APP_ROOT_DIR" "$STAGING_DIR/" 2>/dev/null; then
        APP_SIZE=$(du -sh "$STAGING_DIR/$(basename "$APP_ROOT_DIR")" 2>/dev/null | cut -f1 || echo "unknown")
        log_result "SUCCESS" "APP_DATA" "Backed up from $APP_ROOT_DIR ($APP_SIZE)"
        APP_BACKED_UP=true
        ((SUCCESS_COUNT++))
    else
        log_result "ERROR" "APP_DATA" "Failed to backup from $APP_ROOT_DIR"
        ((ERROR_COUNT++))
    fi
elif [ -d "/home/data/bambooai" ]; then
    if rsync -aq --exclude="*.log" --exclude="__pycache__" --exclude="temp/*" --exclude=".git" "/home/data/bambooai" "$STAGING_DIR/" 2>/dev/null; then
        APP_SIZE=$(du -sh "$STAGING_DIR/bambooai" 2>/dev/null | cut -f1 || echo "unknown")
        log_result "SUCCESS" "APP_DATA" "Backed up from /home/data/bambooai ($APP_SIZE)"
        APP_BACKED_UP=true
        ((SUCCESS_COUNT++))
    else
        log_result "ERROR" "APP_DATA" "Failed to backup from /home/data/bambooai"
        ((ERROR_COUNT++))
    fi
else
    log_result "WARNING" "APP_DATA" "No app directory found to backup"
    ((WARNING_COUNT++))
fi

# Backup virtual environment info
VENV_BACKED_UP=false
if [ -n "$VENV_PATH" ] && [ -d "$VENV_PATH" ]; then
    echo "Virtual environment path: $VENV_PATH" > "$STAGING_DIR/venv_info.txt"
    if pip freeze > "$STAGING_DIR/requirements_backup.txt" 2>/dev/null; then
        PACKAGE_COUNT=$(wc -l < "$STAGING_DIR/requirements_backup.txt")
        log_result "SUCCESS" "VENV" "Python environment info captured ($PACKAGE_COUNT packages)"
        VENV_BACKED_UP=true
        ((SUCCESS_COUNT++))
    fi
elif [ -d "/home/data/bambooai-venv" ]; then
    echo "Virtual environment path: /home/data/bambooai-venv" > "$STAGING_DIR/venv_info.txt"
    if /home/data/bambooai-venv/bin/pip freeze > "$STAGING_DIR/requirements_backup.txt" 2>/dev/null; then
        PACKAGE_COUNT=$(wc -l < "$STAGING_DIR/requirements_backup.txt")
        log_result "SUCCESS" "VENV" "Python environment info captured ($PACKAGE_COUNT packages)"
        VENV_BACKED_UP=true
        ((SUCCESS_COUNT++))
    fi
fi

if [ "$VENV_BACKED_UP" = false ]; then
    log_result "WARNING" "VENV" "Virtual environment not found or inaccessible"
    ((WARNING_COUNT++))
fi

# Create compressed backup
cd /tmp
if tar -czf "$BACKUP_DIR/$BACKUP_NAME.tar.gz" "$BACKUP_NAME/" 2>/dev/null; then
    BACKUP_SIZE=$(du -h "$BACKUP_DIR/$BACKUP_NAME.tar.gz" | cut -f1)
    log_result "SUCCESS" "COMPRESSION" "Archive created ($BACKUP_SIZE)"
    ((SUCCESS_COUNT++))
else
    log_result "ERROR" "COMPRESSION" "Failed to create archive"
    ((ERROR_COUNT++))
fi

# Cleanup staging
rm -rf "$STAGING_DIR"

# Keep only last 30 backups
cd "$BACKUP_DIR"
OLD_BACKUPS=$(ls -t *.tar.gz 2>/dev/null | tail -n +31)
if [ -n "$OLD_BACKUPS" ]; then
    REMOVED_COUNT=$(echo "$OLD_BACKUPS" | wc -l)
    echo "$OLD_BACKUPS" | xargs -r rm
    log_result "SUCCESS" "CLEANUP" "Removed $REMOVED_COUNT old backups"
else
    log_result "INFO" "CLEANUP" "No old backups to remove"
fi

# Final summary
END_TIME=$(date)
DURATION=$(($(date -d "$END_TIME" +%s) - $(date -d "$START_TIME" +%s)))

echo ""
echo "==============================================="
log_result "INFO" "SUMMARY" "Backup completed in ${DURATION}s"
log_result "INFO" "SUMMARY" "SUCCESS: $SUCCESS_COUNT | WARNINGS: $WARNING_COUNT | ERRORS: $ERROR_COUNT"
log_result "INFO" "SUMMARY" "Location: $BACKUP_DIR/$BACKUP_NAME.tar.gz ($BACKUP_SIZE)"

# Show file count instead of listing files
FILE_COUNT=$(tar -tzf "$BACKUP_DIR/$BACKUP_NAME.tar.gz" 2>/dev/null | wc -l)
log_result "INFO" "SUMMARY" "Archive contains $FILE_COUNT files/directories"
echo "==============================================="

# Exit with error code if there were any errors
if [ $ERROR_COUNT -gt 0 ]; then
    exit 1
else
    exit 0
fi