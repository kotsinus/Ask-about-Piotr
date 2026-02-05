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
# Central SQLAlchemy engine/session management.

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, get_settings


def _to_sqlalchemy_url(database_url: str) -> str:
    """Normalize DB URL so SQLAlchemy uses psycopg (already in requirements).

    SQLAlchemy's default Postgres driver is often `psycopg2`, which is not
    installed in this project.
    """

    if database_url.startswith("postgresql+psycopg://"):
        return database_url
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


_ENGINE: Engine | None = None
_SESSION_FACTORY: sessionmaker[Session] | None = None


def get_engine(settings: Settings | None = None) -> Engine:
    global _ENGINE

    if _ENGINE is None:
        settings = settings or get_settings()
        _ENGINE = create_engine(
            _to_sqlalchemy_url(settings.database_url),
            pool_pre_ping=True,
            future=True,
        )
    return _ENGINE


def get_session_factory(settings: Settings | None = None) -> sessionmaker[Session]:
    global _SESSION_FACTORY

    if _SESSION_FACTORY is None:
        _SESSION_FACTORY = sessionmaker(
            bind=get_engine(settings),
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
            class_=Session,
        )
    return _SESSION_FACTORY


@contextmanager
def session_scope(settings: Settings | None = None) -> Iterator[Session]:
    """Provide a transactional scope around a series of operations."""

    session = get_session_factory(settings)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

