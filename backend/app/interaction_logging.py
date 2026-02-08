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

# Avoid multiple concurrent / repeated CREATE TABLE attempts per process on a
# fresh environment (can make logs noisy under burst traffic).
_INTERACTION_LOGS_TABLE_CREATE_ATTEMPTED = False


@dataclass(frozen=True)
class InteractionLog:
    request_id: str
    session_id: str | None
    conversation_id: str | None
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
            global _INTERACTION_LOGS_TABLE_CREATE_ATTEMPTED
            # Typical when Postgres is running but init.sql hasn't been applied
            # (e.g., existing Docker volume created before the table was added).
            if not _INTERACTION_LOGS_TABLE_CREATE_ATTEMPTED:
                _INTERACTION_LOGS_TABLE_CREATE_ATTEMPTED = True
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
                        _INTERACTION_LOGGING_DISABLED_REASON = (
                            "write_failed_after_create"
                        )
                        return

                _INTERACTION_LOGGING_DISABLED_REASON = "table_missing_and_create_failed"
                return

            # We've already tried creating the table in this process.
            #
            # Do not attempt CREATE TABLE again (noise under burst traffic), but
            # do one best-effort retry: the table may have been created by a
            # concurrent request while we were handling this error.
            try:
                _write_interaction_log_once(row)
                return
            except ProgrammingError as exc2:
                if _is_undefined_table(exc2):
                    _INTERACTION_LOGGING_DISABLED_REASON = (
                        "table_missing_create_already_attempted"
                    )
                    return
                logger.exception("interaction_log_write_failed")
                return
            except Exception:
                _INTERACTION_LOGGING_DISABLED_REASON = "write_failed_after_create"
                logger.exception("interaction_log_write_failed_after_create")
                return

        logger.exception("interaction_log_write_failed")
    except Exception:
        logger.exception("interaction_log_write_failed")


def _write_interaction_log_once(row: InteractionLog) -> None:
    with session_scope() as session:
        session.add(
            InteractionLogModel(
                request_id=row.request_id,
                session_id=row.session_id,
                conversation_id=row.conversation_id,
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


def get_interaction_logging_disabled_reason() -> str | None:
    """Expose the internal disable flag for diagnostics / tests."""

    return _INTERACTION_LOGGING_DISABLED_REASON
