"""Structured, rotating application and alert logs."""

from __future__ import annotations
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure_logs(
    directory: str | Path = "logs",
    level: int = logging.INFO,
    max_bytes: int = 2_000_000,
    backup_count: int = 5,
) -> logging.Logger:
    folder = Path(directory)
    folder.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("nvme_insight")
    logger.setLevel(level)
    logger.propagate = False
    if logger.handlers:
        return logger
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    for name, minimum in (
        ("application.log", level),
        ("alerts.log", logging.WARNING),
    ):
        handler = RotatingFileHandler(
            folder / name,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        handler.setLevel(minimum)
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


def log_alerts(logger: logging.Logger, events: list[dict]) -> None:
    """Persist structured alert events at their appropriate log level."""

    for event in events:
        message = (
            f"alert code={event.get('code')} source={event.get('source')} "
            f"value={event.get('value')} threshold={event.get('threshold')} "
            f"message={event.get('message')}"
        )
        severity = event.get("severity")
        if severity == "critical":
            logger.error(message)
        elif severity == "warning":
            logger.warning(message)
        else:
            logger.info(message)
