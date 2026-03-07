"""
Logging utility for the Self-Healing System.
Provides consistent logging across all components.
"""

import logging
import os
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional

# Force unbuffered output globally
os.environ["PYTHONUNBUFFERED"] = "1"


# Always log to a file as well, so we never lose webhook logs
_LOG_DIR = Path(__file__).resolve().parent.parent.parent / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_APP_LOG_FILE = _LOG_DIR / "app.log"


def setup_logger(
    name: str,
    log_file: Optional[Path] = None,
    level: int = logging.INFO,
    console_output: bool = True,
) -> logging.Logger:
    """
    Set up a logger with file and/or console output.
    
    Args:
        name: Logger name
        log_file: Optional path to log file
        level: Logging level
        console_output: Whether to output to console
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Create formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # Console handler
    if console_output:
        console_handler = FlushingStreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    
    # File handler (always add app-wide log)
    file_handler = logging.FileHandler(_APP_LOG_FILE, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Additional file handler
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get an existing logger by name."""
    return logging.getLogger(name)


class FlushingStreamHandler(logging.StreamHandler):
    """StreamHandler that writes to stderr and flushes after every record.
    stderr is unbuffered on most platforms, avoiding lost logs on Windows."""
    def __init__(self):
        super().__init__(sys.stderr)

    def emit(self, record):
        super().emit(record)
        self.flush()


class ColoredFormatter(logging.Formatter):
    """Custom formatter with color support for console output."""
    
    COLORS = {
        "DEBUG": "\033[36m",     # Cyan
        "INFO": "\033[32m",      # Green
        "WARNING": "\033[33m",   # Yellow
        "ERROR": "\033[31m",     # Red
        "CRITICAL": "\033[35m",  # Magenta
        "RESET": "\033[0m",
    }
    
    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, self.COLORS["RESET"])
        reset = self.COLORS["RESET"]
        record.levelname = f"{color}{record.levelname}{reset}"
        return super().format(record)


def setup_colored_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """Set up a logger with colored console output + file logging."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.handlers.clear()
    
    handler = FlushingStreamHandler()
    handler.setFormatter(ColoredFormatter(
        fmt="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(handler)
    
    # Always log to file as well
    file_handler = logging.FileHandler(_APP_LOG_FILE, encoding="utf-8")
    file_handler.setLevel(level)
    file_handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(file_handler)
    
    return logger
