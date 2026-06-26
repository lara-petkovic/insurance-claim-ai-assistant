from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import config

LOGGER_NAMESPACE = "claim_checker"

_configured_signature: tuple[str, str, bool] | None = None


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(f"{LOGGER_NAMESPACE}.{name}")


def log_event(logger: logging.Logger, message: str, **details: Any) -> None:
    logger.info("%s%s", message, _format_details(details))


def configure_logging() -> None:
    global _configured_signature

    settings = config.get_settings()
    log_path = Path(settings.log_file)
    if not log_path.is_absolute():
        log_path = config.BACKEND_DIR / log_path

    signature = (str(log_path), settings.log_level, settings.log_to_console)
    if _configured_signature == signature:
        return

    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(LOGGER_NAMESPACE)
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(getattr(logging, settings.log_level))

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    if settings.log_to_console:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    _configured_signature = signature


def _format_details(details: dict[str, Any]) -> str:
    if not details:
        return ""
    safe_details = {key: _summarize(value) for key, value in details.items()}
    return " | " + " ".join(f"{key}={value}" for key, value in safe_details.items())


def _summarize(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int | float) or value is None:
        return str(value)
    if isinstance(value, str):
        cleaned = " ".join(value.split())
        return repr(cleaned[:117] + "...") if len(cleaned) > 120 else repr(cleaned)
    if isinstance(value, list):
        return f"list({len(value)})"
    if isinstance(value, dict):
        return f"dict({len(value)})"
    return type(value).__name__
