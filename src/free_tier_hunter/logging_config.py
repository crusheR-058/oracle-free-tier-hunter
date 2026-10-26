"""
Structured Logging Configuration with Log Rotation and Secret Redaction.
"""

import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re


class SensitiveDataFilter(logging.Filter):
    """Redacts potential secrets, private keys, and authentication tokens from log lines."""

    PATTERNS = [
        (re.compile(r"-----BEGIN [A-Z0-9 ]+PRIVATE KEY-----[^\-]+-----END [A-Z0-9 ]+PRIVATE KEY-----", re.DOTALL), "[REDACTED_PRIVATE_KEY]"),
        (re.compile(r"password=['\"][^'\"]+['\"]", re.IGNORECASE), "password='[REDACTED]'"),
        (re.compile(r"smtp_password=['\"][^'\"]+['\"]", re.IGNORECASE), "smtp_password='[REDACTED]'"),
        (re.compile(r"ocid1\.tenancy\.oc1\.[a-z0-9]+\.[a-z0-9]{20,}", re.IGNORECASE), lambda m: m.group(0)[:25] + "...[TRUNCATED]"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            for pattern, repl in self.PATTERNS:
                if callable(repl):
                    record.msg = pattern.sub(repl, record.msg)
                else:
                    record.msg = pattern.sub(repl, record.msg)
        return True


def setup_logging(log_level: str = "INFO", log_dir: str = "logs") -> logging.Logger:
    """Configures root logger with console and rotating file output."""
    os.makedirs(log_dir, exist_ok=True)
    log_file = Path(log_dir) / "hunter.log"

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Clear existing handlers
    root_logger.handlers.clear()

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    redaction_filter = SensitiveDataFilter()

    # Rotating File Handler (Max 10 MB, up to 5 backups)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(redaction_filter)
    root_logger.addHandler(file_handler)

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.addFilter(redaction_filter)
    root_logger.addHandler(console_handler)

    return logging.getLogger("free_tier_hunter")
