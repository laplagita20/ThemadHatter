"""Logging configuration with console + rotating file handlers."""

import logging
import logging.handlers
import sys
from pathlib import Path

from colorama import Fore, Style, init as colorama_init


class ColoredFormatter(logging.Formatter):
    """Console formatter with color-coded log levels."""

    COLORS = {
        logging.DEBUG: Fore.CYAN,
        logging.INFO: Fore.GREEN,
        logging.WARNING: Fore.YELLOW,
        logging.ERROR: Fore.RED,
        logging.CRITICAL: Fore.RED + Style.BRIGHT,
    }

    def format(self, record):
        color = self.COLORS.get(record.levelno, "")
        record.levelname = f"{color}{record.levelname}{Style.RESET_ALL}"
        return super().format(record)


def setup_logging(log_dir: Path, level: str = "INFO") -> logging.Logger:
    """Configure root logger with console and rotating file handlers."""
    colorama_init()

    root_logger = logging.getLogger("stock_model")
    root_logger.setLevel(logging.DEBUG)

    # Clear existing handlers
    root_logger.handlers.clear()

    # Console handler (INFO level by default)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(getattr(logging, level.upper(), logging.INFO))
    console_fmt = ColoredFormatter("%(levelname)s %(name)s: %(message)s")
    console.setFormatter(console_fmt)
    root_logger.addHandler(console)

    # Rotating file handler (DEBUG level, 5MB max, 5 backups)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "stock_model.log"
    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s [%(filename)s:%(lineno)d] %(message)s"
    )
    file_handler.setFormatter(file_fmt)
    root_logger.addHandler(file_handler)

    return root_logger
