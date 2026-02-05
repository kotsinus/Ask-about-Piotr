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
# Unit tests for logging setup utilities (formatters, filters, and configuration).

from __future__ import annotations

import logging
import sys

import pytest

from app import logging_setup


def test_request_id_filter_sets_record_request_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(logging_setup, "get_request_id", lambda: "rid-123")
    filt = logging_setup.RequestIdFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )
    assert filt.filter(record) is True
    assert getattr(record, "request_id") == "rid-123"


def test_json_formatter_includes_structured_fields_and_exc_info() -> None:
    formatter = logging_setup.JsonFormatter()
    try:
        raise ValueError("boom")
    except ValueError:
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="msg",
        args=(),
        exc_info=exc_info,
    )
    record.request_id = "rid"
    record.method = "GET"
    record.path = "/healthz"
    record.status_code = 200
    record.duration_ms = 12.34

    rendered = formatter.format(record)
    assert '"request_id": "rid"' in rendered
    assert '"method": "GET"' in rendered
    assert '"path": "/healthz"' in rendered
    assert '"status_code": 200' in rendered
    assert '"duration_ms": 12.34' in rendered
    assert '"exc_info":' in rendered


def test_key_value_formatter_includes_request_id_and_fields_and_exc_info() -> None:
    formatter = logging_setup.KeyValueFormatter()
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=exc_info,
    )
    record.request_id = "rid"
    record.method = "POST"
    record.path = "/chat"
    record.status_code = 500
    record.duration_ms = 9.87

    rendered = formatter.format(record)
    assert "timestamp=" in rendered
    assert "level=ERROR" in rendered
    assert "logger=test" in rendered
    assert "request_id=rid" in rendered
    assert "method=POST" in rendered
    assert "path=/chat" in rendered
    assert "status_code=500" in rendered
    assert "duration_ms=9.87" in rendered
    assert "message=hello" in rendered
    assert "exc_info=" in rendered


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("debug", "DEBUG"),
        ("INFO", "INFO"),
        ("", "INFO"),
        ("wat", "INFO"),
    ],
)
def test_normalize_log_level(value: str, expected: str) -> None:
    assert logging_setup._normalize_log_level(value) == expected


def test_configure_logging_is_idempotent_and_respects_force(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    def _fake_dict_config(payload: dict) -> None:
        calls.append(payload)

    monkeypatch.setattr(logging_setup, "dictConfig", _fake_dict_config)
    monkeypatch.setattr(logging_setup, "_CONFIGURED", False)

    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("LOG_FORMAT", "text")
    monkeypatch.setenv("UVICORN_ACCESS_LOG_LEVEL", "WARNING")

    logging_setup.configure_logging()
    logging_setup.configure_logging()
    assert len(calls) == 1, (
        "Expected configure_logging() to be a no-op when already configured"
    )

    logging_setup.configure_logging(force=True)
    assert len(calls) == 2

    formatter_cls = calls[-1]["formatters"]["default"]["()"]
    assert formatter_cls is logging_setup.KeyValueFormatter
