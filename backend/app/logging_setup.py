# Copyright 2026 Piotr Synak
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Purpose:
# Centralized logging configuration (stdlib logging) for app + uvicorn.

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from logging.config import dictConfig

from app.observability import get_request_id

_CONFIGURED = False


def _utc_iso_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.request_id = get_request_id()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": _utc_iso_now(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        request_id = getattr(record, "request_id", None)
        if request_id:
            payload["request_id"] = request_id

        # Optional structured fields used by request logging middleware.
        for key in ("method", "path", "status_code", "duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value

        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


class KeyValueFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        parts = [
            f"timestamp={_utc_iso_now()}",
            f"level={record.levelname}",
            f"logger={record.name}",
        ]
        request_id = getattr(record, "request_id", None)
        if request_id:
            parts.append(f"request_id={request_id}")

        for key in ("method", "path", "status_code", "duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                parts.append(f"{key}={value}")

        parts.append(f"message={record.getMessage()}")

        if record.exc_info:
            parts.append(f"exc_info={self.formatException(record.exc_info)}")

        return " ".join(parts)


def _normalize_log_level(value: str) -> str:
    normalized = (value or "").strip().upper()
    if normalized in {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}:
        return normalized
    return "INFO"


def configure_logging(*, force: bool = False) -> None:
    """Configure stdlib logging for app + uvicorn.

    Env vars:
      - LOG_LEVEL: DEBUG/INFO/WARNING/ERROR/CRITICAL (default: INFO)
      - LOG_FORMAT: json|text (default: json)
      - UVICORN_ACCESS_LOG_LEVEL: defaults to WARNING to avoid duplicate per-request logs
    """

    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    level = _normalize_log_level(os.getenv("LOG_LEVEL", "INFO"))
    log_format = (os.getenv("LOG_FORMAT", "json") or "json").strip().lower()
    use_json = log_format != "text"

    uvicorn_access_level = _normalize_log_level(
        os.getenv("UVICORN_ACCESS_LOG_LEVEL", "WARNING")
    )

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {
                "request_id": {
                    "()": RequestIdFilter,
                }
            },
            "formatters": {
                "default": {
                    "()": JsonFormatter if use_json else KeyValueFormatter,
                },
            },
            "handlers": {
                "stdout": {
                    "class": "logging.StreamHandler",
                    "stream": sys.stdout,
                    "filters": ["request_id"],
                    "formatter": "default",
                },
            },
            "root": {
                "handlers": ["stdout"],
                "level": level,
            },
            "loggers": {
                # Uvicorn loggers (keep consistent formatting).
                "uvicorn": {
                    "handlers": ["stdout"],
                    "level": level,
                    "propagate": False,
                },
                "uvicorn.error": {
                    "handlers": ["stdout"],
                    "level": level,
                    "propagate": False,
                },
                # Suppress uvicorn's access logs by default (we emit one line per
                # request in our middleware).
                "uvicorn.access": {
                    "handlers": ["stdout"],
                    "level": uvicorn_access_level,
                    "propagate": False,
                },
            },
        }
    )

    _CONFIGURED = True
