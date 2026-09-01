import os
import logging
from logging.handlers import RotatingFileHandler

def setup_logger(name: str = "nova", log_file: str = "logs/app.log", level: int = logging.INFO) -> logging.Logger:
    """Sets up a logger that outputs to both console and a file."""
    # Ensure logs directory exists
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(level)

    # Avoid duplicate handlers if logger is already configured
    if not logger.handlers:
        formatter = logging.Formatter(
            '[%(asctime)s] [%(levelname)s] [%(name)s] (%(filename)s:%(lineno)d): %(message)s'
        )

        # Console Handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # File Handler (rotating file to manage disk usage)
        try:
            file_handler = RotatingFileHandler(
                log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except Exception as e:
            # Fallback if log file cannot be created
            print(f"Failed to setup file handler for logging: {e}")

    return logger

# Default log file path resolved relative to the directory of this script (project_root/logs/app.log)
utils_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(utils_dir)
default_log_path = os.path.join(project_root, "logs", "app.log")

# Default app logger instance
logger = setup_logger(log_file=default_log_path)

