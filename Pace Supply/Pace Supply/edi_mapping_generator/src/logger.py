"""
Logger module with auto-cleanup of old log files.
"""
import os
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path


def setup_logger(log_dir: str = "logs", log_retention_days: int = 10) -> logging.Logger:
    """
    Set up logging with file and console handlers.
    Auto-deletes log files older than log_retention_days.
    
    Args:
        log_dir: Directory to store log files
        log_retention_days: Delete logs older than this many days
    
    Returns:
        Configured logger instance
    """
    # Create logs directory if not exists
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    
    # Clean up old log files
    cleanup_old_logs(log_path, log_retention_days)
    
    # Create logger
    logger = logging.getLogger("edi_mapping_generator")
    logger.setLevel(logging.DEBUG)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Create log filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_path / f"mapping_generator_{timestamp}.log"
    
    # File handler - DEBUG level
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_format = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_format)
    
    # Console handler - INFO level
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_format = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    
    # Add handlers
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    logger.info(f"Log file created: {log_file}")
    
    return logger


def cleanup_old_logs(log_dir: Path, retention_days: int) -> int:
    """
    Delete log files older than retention_days.
    
    Args:
        log_dir: Path to logs directory
        retention_days: Delete files older than this many days
    
    Returns:
        Number of files deleted
    """
    if not log_dir.exists():
        return 0
    
    cutoff_time = time.time() - (retention_days * 24 * 60 * 60)
    deleted_count = 0
    
    for log_file in log_dir.glob("*.log"):
        try:
            if log_file.stat().st_mtime < cutoff_time:
                log_file.unlink()
                deleted_count += 1
        except Exception:
            pass  # Ignore errors during cleanup
    
    return deleted_count


def get_logger() -> logging.Logger:
    """Get the existing logger instance."""
    return logging.getLogger("edi_mapping_generator")
