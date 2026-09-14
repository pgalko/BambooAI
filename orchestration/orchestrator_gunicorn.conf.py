import os
from dotenv import load_dotenv

# Load environment variables in order (later files override earlier ones)
load_dotenv('/etc/bambooai/system.env')
load_dotenv('/etc/bambooai/shared.env')
load_dotenv('/etc/bambooai/orchestrator.env')

# CRITICAL: Single worker + threads to prevent race conditions
workers = 1
worker_class = 'gthread'
threads = 60  # High thread count for concurrent container requests
timeout = 600  # 10 minutes for container operations
keepalive = 5
max_requests = 0 # Set to zero to prevent frequent worker restarts
max_requests_jitter = 0

# Basic configuration - plain HTTP
bind = f"0.0.0.0:{os.getenv('ORCHESTRATOR_PORT', '8080')}"

# Process naming
proc_name = 'bambooai-orchestrator'

# Logging
accesslog = '-'
errorlog = '-'
loglevel = 'info'

# Performance
preload_app = True
worker_tmp_dir = '/dev/shm'
