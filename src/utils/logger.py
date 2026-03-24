"""Logging configuration for specdev."""

import logging
import os
from datetime import datetime
from logging.handlers import RotatingFileHandler


def setup_logging(debug: bool = False) -> None:
    """Configure rotating file + console logging.

    Args:
        debug: If True, all levels are DEBUG; otherwise INFO.
    """
    # Check for APP_LOG_DIR environment variable (set by runtime hook for frozen executable)
    log_dir_env = os.environ.get('APP_LOG_DIR')
    if log_dir_env:
        log_dir = log_dir_env
    else:
        # Fallback to original behavior for development
        log_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))), "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, f"app_{datetime.now():%Y%m%d}.log")
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    formatter = logging.Formatter(fmt)

    # Root logger
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    # Rotating file handler — DEBUG (or INFO if not debug), 10MB × 5 backups
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Console handler — INFO (or DEBUG if --debug)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if debug else logging.INFO)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("PySide6").setLevel(logging.WARNING)
    logging.getLogger("pyqtgraph").setLevel(logging.WARNING)
