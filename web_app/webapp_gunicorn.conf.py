import os
import sys
from dotenv import load_dotenv

# Add project root to Python path
sys.path.insert(0, '/home/data/bambooai')

# Load environment variables in order (later files override earlier ones)
load_dotenv('/etc/bambooai/system.env')
load_dotenv('/etc/bambooai/shared.env')
load_dotenv('/etc/bambooai/webapp-secrets.env')
load_dotenv('/etc/bambooai/webapp.env')

# Basic configuration
bind = f"0.0.0.0:{os.getenv('APP_PORT', '5001')}"
workers = int(os.getenv('GUNICORN_WORKERS', '4'))
worker_class = 'gthread'
threads = 60  # High thread count for concurrent users
timeout = 600  # 10 minutes for long-running jobs
keepalive = 5
max_requests = 0 # Set to zero to prevent frequent worker restarts
max_requests_jitter = 0

# SSL configuration
if os.getenv('SSL_ENABLED', 'false').lower() == 'true':
    certfile = os.getenv('SSL_CERT_PATH')
    keyfile = os.getenv('SSL_KEY_PATH')

# Process naming
proc_name = 'bambooai-webapp'

# Logging - suppress most logs
accesslog = None  # Disable access logs (the verbose request logs)
errorlog = '-'    # Keep error logs to stderr
loglevel = 'error'  # Only show errors, not warnings or info

# Performance
preload_app = True
worker_tmp_dir = '/dev/shm'
