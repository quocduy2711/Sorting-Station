"""
utils/ — Utilities package.

Provides:
- setup_logging()      Rotating file + console + JSON handler
- setup_logging_from_config()  Config-aware variant
"""
from __future__ import annotations

import logging
import logging.handlers
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from config.app_config import LoggingConfig


# ── JSON formatter (requires python-json-logger) ──────────────────────────────

def _make_json_formatter() -> logging.Formatter:
    try:
        from pythonjsonlogger import jsonlogger  # type: ignore
        return jsonlogger.JsonFormatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s"
        )
    except ImportError:
        return logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )


# ── Public API ────────────────────────────────────────────────────────────────

def setup_logging(
    log_level: int = logging.INFO,
    log_dir: str = "logs",
    max_bytes: int = 10_485_760,
    backup_count: int = 5,
) -> None:
    """
    Configure logging with rotating file handler + console handler.

    Creates two log files:
    - logs/runtime.log  — all messages at or above log_level
    - logs/alarms.log   — WARNING and above only

    Args:
        log_level:     Root log level (e.g. logging.INFO)
        log_dir:       Directory for log files (created if missing)
        max_bytes:     Max size of each log file before rotation
        backup_count:  Number of backup files to keep
    """
    Path(log_dir).mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers when called multiple times
    if root_logger.handlers:
        root_logger.handlers.clear()

    json_fmt = _make_json_formatter()
    console_fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # ── File handler: runtime.log ─────────────────────────────────────────
    runtime_handler = logging.handlers.RotatingFileHandler(
        filename=os.path.join(log_dir, "runtime.log"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    runtime_handler.setLevel(log_level)
    runtime_handler.setFormatter(json_fmt)

    # ── File handler: alarms.log (WARNING+) ──────────────────────────────
    alarm_handler = logging.handlers.RotatingFileHandler(
        filename=os.path.join(log_dir, "alarms.log"),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    alarm_handler.setLevel(logging.WARNING)
    alarm_handler.setFormatter(json_fmt)

    # ── Console handler ───────────────────────────────────────────────────
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(console_fmt)

    root_logger.addHandler(runtime_handler)
    root_logger.addHandler(alarm_handler)
    root_logger.addHandler(console_handler)


def setup_logging_from_config(cfg: "LoggingConfig") -> None:
    """
    Configure logging from a LoggingConfig object.

    Args:
        cfg: LoggingConfig from AppConfig
    """
    level = getattr(logging, cfg.level.upper(), logging.INFO)
    setup_logging(
        log_level=level,
        log_dir=cfg.log_dir,
        max_bytes=cfg.max_bytes,
        backup_count=cfg.backup_count,
    )


__all__ = ["setup_logging", "setup_logging_from_config"]
