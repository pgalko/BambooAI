"""
Unified logging configuration for BambooAI project.
"""

import logging
import sys
from datetime import datetime
import os

# Global flag to track if logging has been configured
_logging_configured = False

def setup_logging(log_level=None):
    """
    Configure logging for the entire application.
    Call this once at application startup (in web_app/app.py).
    
    Args:
        log_level: Override log level (DEBUG, INFO, WARNING, ERROR)
                  If None, uses INFO for development, WARNING for production
    """
    global _logging_configured
    
    # Prevent multiple configurations
    if _logging_configured:
        return
    
    # Determine log level
    if log_level is None:
        # Use environment variable or default to INFO
        env = os.getenv('FLASK_ENV', 'production')
        if env == 'development':
            log_level = logging.INFO
        else:
            log_level = logging.INFO  # Keep INFO for production too for better visibility
    elif isinstance(log_level, str):
        log_level = getattr(logging, log_level.upper())
    
    # Create formatter - human readable, single line
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Remove any existing handlers to avoid duplicates
    root_logger.handlers = []
    
    # Console handler for everything
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Setup orchestration logs directory
    app_root = os.getenv('APP_ROOT_DIR', '/home/data/bambooai')
    log_dir = os.path.join(app_root, 'orchestration', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    
    # Configure file handlers for ANY logger that starts with these patterns
    # This catches both 'orchestration.container_manager' and '__main__' when run directly
    
    # Container manager - file only, no console
    cm_file_handler = logging.FileHandler(os.path.join(log_dir, 'container_manager.log'))
    cm_file_handler.setFormatter(formatter)
    cm_file_handler.setLevel(log_level)
    
    # Add file handler to multiple possible logger names
    for logger_name in ['orchestration.container_manager', 'container_manager', '__main__']:
        cm_logger = logging.getLogger(logger_name)
        # Only add if this specific logger is for container_manager
        if 'container_manager' in logger_name:
            cm_logger.propagate = False  # No console
            cm_logger.addHandler(cm_file_handler)
            cm_logger.setLevel(log_level)
    
    # Orchestrator API - both file and console
    api_file_handler = logging.FileHandler(os.path.join(log_dir, 'orchestrator_api.log'))
    api_file_handler.setFormatter(formatter)
    api_file_handler.setLevel(log_level)
    
    # Add to multiple possible logger names for orchestrator_api
    for logger_name in ['orchestration.orchestrator_api', 'orchestrator_api', '__main__']:
        api_logger = logging.getLogger(logger_name)
        # Check if we should add the handler
        if 'orchestrator_api' in logger_name or logger_name == '__main__':
            # Don't add duplicate handlers
            if not any(isinstance(h, logging.FileHandler) and 
                      h.baseFilename.endswith('orchestrator_api.log') 
                      for h in api_logger.handlers):
                api_logger.addHandler(api_file_handler)
                api_logger.setLevel(log_level)
    
    # Suppress noisy third-party loggers
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)  # Flask's request logger
    logging.getLogger('PIL').setLevel(logging.WARNING)  # Pillow
    logging.getLogger('matplotlib').setLevel(logging.WARNING)
    
    # Suppress Gunicorn's access logs (if running under Gunicorn)
    logging.getLogger('gunicorn.access').setLevel(logging.ERROR)
    
    _logging_configured = True
    
    # Log that logging is configured
    logger = logging.getLogger('logger_config')
    logger.info(f"Logging configured at {log_level} level")

def get_logger(name=None):
    """
    Get a logger instance. This is the primary interface for all modules.
    
    Args:
        name: Logger name (typically __name__). If None, returns root logger.
    
    Returns:
        Logger instance
    
    Usage:
        from logger_config import get_logger
        logger = get_logger(__name__)
        logger.info("This is an info message")
    """
    # Auto-configure if not already done (fallback for modules imported before setup)
    if not _logging_configured:
        setup_logging()
    
    # Special handling for orchestration modules
    if name and ('orchestrator_api' in name or name == '__main__'):
        # Make sure file handler is attached for orchestrator_api
        logger = logging.getLogger(name)
        app_root = os.getenv('APP_ROOT_DIR', '/home/data/bambooai')
        log_file = os.path.join(app_root, 'orchestration', 'logs', 'orchestrator_api.log')
        
        # Check if file handler already exists
        has_file_handler = any(isinstance(h, logging.FileHandler) and 
                               h.baseFilename == log_file 
                               for h in logger.handlers)
        
        if not has_file_handler:
            formatter = logging.Formatter(
                '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )
            file_handler = logging.FileHandler(log_file)
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
            
        return logger
    
    return logging.getLogger(name)

# Convenience function for backward compatibility with existing code
def get_app_logger():
    """Get the main application logger."""
    return get_logger('web_app.app')