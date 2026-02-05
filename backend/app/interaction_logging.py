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
# Best-effort persistence of Q&A interaction logs.

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.exc import ProgrammingError

from app.db import get_engine, session_scope
from app.models import Base, InteractionLogModel

logger = logging.getLogger(__name__)

# Best-effort logging must never break `/chat`. However, repeated DB errors can
# create noisy logs. For known non-fatal situations (e.g., table missing on a
# fresh DB volume) we degrade gracefully.
_INTERACTION_LOGGING_DISABLED_REASON: str | None = None


@dataclass(frozen=True)
class InteractionLog:
    request_id: str
    request_at: datetime
    response_at: datetime
    latency_ms: float | None
    question: str
    answer: str
    router_model: str | None
    synthesis_model: str | None
    embeddings_provider: str | None
    embeddings_model: str | None
    ip_prefix: str | None
    ip_hash: str | None
    user_agent: str | None
    country: str | None


def write_interaction_log(row: InteractionLog) -> None:
    """Write one row; failures must not break the request path."""

    global _INTERACTION_LOGGING_DISABLED_REASON
    if _INTERACTION_LOGGING_DISABLED_REASON is not None:
        return

    try:
        _write_interaction_log_once(row)
    except ProgrammingError as exc:
        if _is_undefined_table(exc):
            # Typical when Postgres is running but init.sql hasn't been applied
            # (e.g., existing Docker volume created before the table was added).
            logger.warning(
                "interaction_logs_table_missing",
                extra={"action": "attempt_create_table"},
            )
            if _ensure_interaction_logs_table_exists():
                try:
                    _write_interaction_log_once(row)
                    return
                except Exception:
                    logger.exception("interaction_log_write_failed_after_create")
                    _INTERACTION_LOGGING_DISABLED_REASON = "write_failed_after_create"
                    return

            _INTERACTION_LOGGING_DISABLED_REASON = "table_missing_and_create_failed"
            return

        logger.exception("interaction_log_write_failed")
    except Exception:
        logger.exception("interaction_log_write_failed")


def _write_interaction_log_once(row: InteractionLog) -> None:
    with session_scope() as session:
        session.add(
            InteractionLogModel(
                request_id=row.request_id,
                request_at=row.request_at,
                response_at=row.response_at,
                latency_ms=row.latency_ms,
                question=row.question,
                answer=row.answer,
                router_model=row.router_model,
                synthesis_model=row.synthesis_model,
                embeddings_provider=row.embeddings_provider,
                embeddings_model=row.embeddings_model,
                ip_prefix=row.ip_prefix,
                ip_hash=row.ip_hash,
                user_agent=row.user_agent,
                country=row.country,
                # logged_at: server default (now())
            )
        )


def _is_undefined_table(exc: ProgrammingError) -> bool:
    # SQLAlchemy wraps DBAPI errors; for psycopg this is typically:
    # - `exc.orig` is `psycopg.errors.UndefinedTable`
    orig = getattr(exc, "orig", None)
    if orig is None:
        return False

    try:
        import psycopg

        return isinstance(orig, psycopg.errors.UndefinedTable)
    except Exception:
        # Fall back to string match if driver specifics are unavailable.
        return "UndefinedTable" in repr(orig)


def _ensure_interaction_logs_table_exists() -> bool:
    """Attempt to create the interaction_logs table if missing.

    This is a fallback for environments where init.sql wasn't applied.
    """

    try:
        engine = get_engine()
        Base.metadata.create_all(engine, tables=[InteractionLogModel.__table__])
        return True
    except Exception:
        logger.exception("interaction_logs_table_create_failed")
        return False
