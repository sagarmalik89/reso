"""
printer_agent/logger.py
-----------------------
Centralised logging: console (coloured) + rotating file log.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from colorama import Fore, Style, init as colorama_init

if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure"):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

colorama_init(autoreset=True)

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s – %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class _ColorFormatter(logging.Formatter):
    LEVEL_COLORS = {
        logging.DEBUG:    Fore.CYAN,
        logging.INFO:     Fore.GREEN,
        logging.WARNING:  Fore.YELLOW,
        logging.ERROR:    Fore.RED,
        logging.CRITICAL: Fore.MAGENTA + Style.BRIGHT,
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.levelno, "")
        record.levelname = f"{color}{record.levelname}{Style.RESET_ALL}"
        return super().format(record)


def get_logger(name: str, log_dir: Path | None = None) -> logging.Logger:
    """Return a named logger with console + optional file handler."""
    logger = logging.getLogger(name)

    if logger.handlers:          # already configured – return as-is
        return logger

    logger.setLevel(logging.DEBUG)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    ch.setFormatter(_ColorFormatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
    logger.addHandler(ch)

    # File handler (rotating, max 5 MB × 3 backups)
    if log_dir:
        log_dir.mkdir(parents=True, exist_ok=True)
        fh = RotatingFileHandler(
            log_dir / "printer_agent.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT))
        logger.addHandler(fh)

    return logger
