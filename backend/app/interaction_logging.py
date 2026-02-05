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

from app.db import session_scope
from app.models import InteractionLogModel

logger = logging.getLogger(__name__)


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
    try:
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
    except Exception:
        logger.exception("interaction_log_write_failed")
