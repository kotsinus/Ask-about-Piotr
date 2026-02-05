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
# SQLAlchemy ORM models.

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, Index, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class InteractionLogModel(Base):
    __tablename__ = "interaction_logs"

    __table_args__ = (
        Index("interaction_logs_logged_at_idx", "logged_at"),
        Index("interaction_logs_request_id_idx", "request_id"),
        Index("interaction_logs_session_id_idx", "session_id"),
        Index("interaction_logs_conversation_id_idx", "conversation_id"),
        Index("interaction_logs_ip_prefix_idx", "ip_prefix"),
        Index("interaction_logs_ip_hash_idx", "ip_hash"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    request_id: Mapped[str] = mapped_column(Text, nullable=False)
    session_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    response_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)

    router_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    synthesis_model: Mapped[str | None] = mapped_column(Text, nullable=True)
    embeddings_provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    embeddings_model: Mapped[str | None] = mapped_column(Text, nullable=True)

    ip_prefix: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(Text, nullable=True)

    logged_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
