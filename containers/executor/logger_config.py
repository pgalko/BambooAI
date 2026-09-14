import logging
import sys

def get_logger(name):
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(name)s] %(levelname)s: %(message)s',
            datefmt='%H:%M:%S'
        ))
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
    return logger
