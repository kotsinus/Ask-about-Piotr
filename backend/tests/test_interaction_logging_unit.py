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
# Unit tests for best-effort interaction logging degradation paths.

from __future__ import annotations

from datetime import UTC, datetime

import psycopg
import pytest
from sqlalchemy.exc import ProgrammingError

import app.interaction_logging as il
from app.interaction_logging import InteractionLog
from app.models import InteractionLogModel


def _row() -> InteractionLog:
    now = datetime.now(UTC)
    return InteractionLog(
        request_id="r",
        session_id=None,
        conversation_id=None,
        request_at=now,
        response_at=now,
        latency_ms=1.0,
        question="q",
        standalone_question=None,
        answer="a",
        router_model=None,
        synthesis_model=None,
        embeddings_provider=None,
        embeddings_model=None,

        incoming_last_topic=None,
        resolved_topic=None,
        topic_used_for_retrieval=None,
        messages_count=None,
        retrieval_chunk_count=None,
        llm_context_messages=None,

        ip_prefix=None,
        ip_hash=None,
        user_agent=None,
        country=None,
    )


def _undefined_table_exc() -> ProgrammingError:
    orig = psycopg.errors.UndefinedTable.__new__(psycopg.errors.UndefinedTable)
    return ProgrammingError("stmt", {}, orig)


def test_write_interaction_log_disables_when_table_missing_and_create_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"write": 0}

    def _write_once(row: InteractionLog) -> None:
        calls["write"] += 1
        raise _undefined_table_exc()

    monkeypatch.setattr(il, "_write_interaction_log_once", _write_once)
    monkeypatch.setattr(il, "_ensure_interaction_logs_table_exists", lambda: False)

    il.write_interaction_log(_row())
    assert il._INTERACTION_LOGGING_DISABLED_REASON == "table_missing_and_create_failed"

    # Once disabled, it should be a no-op.
    il.write_interaction_log(_row())
    assert calls["write"] == 1


def test_write_interaction_log_disables_when_write_fails_after_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {"n": 0}

    def _write_once(row: InteractionLog) -> None:
        state["n"] += 1
        if state["n"] == 1:
            raise _undefined_table_exc()
        raise RuntimeError("db still broken")

    monkeypatch.setattr(il, "_write_interaction_log_once", _write_once)
    monkeypatch.setattr(il, "_ensure_interaction_logs_table_exists", lambda: True)

    il.write_interaction_log(_row())
    assert il._INTERACTION_LOGGING_DISABLED_REASON == "write_failed_after_create"

    il.write_interaction_log(_row())
    assert state["n"] == 2


def test_write_interaction_log_does_not_disable_on_other_programming_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _OtherOrig(Exception):
        pass

    def _write_once(row: InteractionLog) -> None:
        raise ProgrammingError("stmt", {}, _OtherOrig())

    monkeypatch.setattr(il, "_write_interaction_log_once", _write_once)
    monkeypatch.setattr(il, "_ensure_interaction_logs_table_exists", lambda: True)

    il.write_interaction_log(_row())
    assert il._INTERACTION_LOGGING_DISABLED_REASON is None


def test_ensure_interaction_logs_table_exists_calls_create_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = object()
    called: dict[str, object] = {}

    monkeypatch.setattr(il, "get_engine", lambda: engine)

    def _create_all(*args, **kwargs):
        called["args"] = args
        called["kwargs"] = kwargs

    monkeypatch.setattr(il.Base.metadata, "create_all", _create_all)

    assert il._ensure_interaction_logs_table_exists() is True
    assert called["args"] == (engine,)

    tables = called["kwargs"]["tables"]
    assert tables == [InteractionLogModel.__table__]


def test_interaction_logging_success_after_create_and_import_fallbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    il._INTERACTION_LOGGING_DISABLED_REASON = None

    # Successful path: undefined table -> create -> second write succeeds.
    state = {"n": 0}

    def _write_once(row: InteractionLog) -> None:
        state["n"] += 1
        if state["n"] == 1:
            raise _undefined_table_exc()
        return None

    monkeypatch.setattr(il, "_write_interaction_log_once", _write_once)
    monkeypatch.setattr(il, "_ensure_interaction_logs_table_exists", lambda: True)

    il.write_interaction_log(_row())
    assert state["n"] == 2
    assert il.get_interaction_logging_disabled_reason() is None

    # Branch: ProgrammingError without orig.
    from sqlalchemy.exc import ProgrammingError

    assert il._is_undefined_table(ProgrammingError("stmt", {}, None)) is False

    # Branch: psycopg import fails => fallback to string match.
    import builtins

    orig_import = builtins.__import__

    def _import(name, *args, **kwargs):
        if name == "psycopg":
            raise ImportError("blocked for test")
        return orig_import(name, *args, **kwargs)

    class _Orig:
        def __repr__(self) -> str:
            return "UndefinedTable(whatever)"

    monkeypatch.setattr(builtins, "__import__", _import)
    assert il._is_undefined_table(ProgrammingError("stmt", {}, _Orig())) is True


def test_ensure_interaction_logs_table_exists_returns_false_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        il,
        "get_engine",
        lambda: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    assert il._ensure_interaction_logs_table_exists() is False
