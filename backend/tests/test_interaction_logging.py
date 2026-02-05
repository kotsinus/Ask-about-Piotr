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
# End-to-end-ish tests for interaction DB logging and privacy rules.
#
# Notes:
# - Tests mock the DB write function to avoid needing Postgres in CI.
# - Retrieval is also stubbed (real retrieval uses Postgres + pgvector).

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Any

import httpx
import pytest

from app.geoip import lookup_country
from app.main import app
from app.observability import REQUEST_ID_HEADER
from app.privacy import anonymize_ip_prefix, hash_ip
from app.schemas import Confidence


def _stub_retrieve(*args: Any, **kwargs: Any) -> list:
    return []


class _StubSynthesis:
    answer = "stub-answer"
    why_this_matters = "stub-why"
    confidence = Confidence.medium
    confidence_reason = None
    used_chunk_indices: list[int] = []


def _stub_synthesize_answer(*args: Any, **kwargs: Any) -> _StubSynthesis:
    return _StubSynthesis()


@pytest.mark.anyio
async def test_chat_triggers_db_write_and_persists_only_anonymized_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.main.retrieve", _stub_retrieve)
    monkeypatch.setattr("app.main.synthesize_answer", _stub_synthesize_answer)

    monkeypatch.setenv("IP_HASH_SALT", "salt-a")
    monkeypatch.delenv("TRUSTED_PROXY_CIDRS", raising=False)
    monkeypatch.setenv("GEOIP_ENABLED", "false")

    captured: list[Any] = []

    def _capture(row: Any) -> None:
        captured.append(row)

    monkeypatch.setattr("app.main.write_interaction_log", _capture)

    peer_ip = "198.51.100.77"
    transport = httpx.ASGITransport(app=app, client=(peer_ip, 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/chat",
            json={"question": "What did you build?"},
            headers={"user-agent": "pytest-agent"},
        )
    assert response.status_code == 200
    assert len(captured) == 1

    row = captured[0]
    payload = response.json()
    request_id = response.headers.get(REQUEST_ID_HEADER)
    assert request_id

    assert row.request_id == request_id
    assert row.session_id
    assert row.conversation_id is None
    assert row.question == "What did you build?"
    assert row.answer == payload["answer"]
    assert isinstance(row.request_at, datetime)
    assert isinstance(row.response_at, datetime)
    assert row.response_at >= row.request_at
    assert isinstance(row.latency_ms, float)

    assert row.ip_prefix == "198.51.100.0/24"
    assert row.ip_hash == hash_ip(ip=peer_ip, salt="salt-a")
    assert row.user_agent == "pytest-agent"
    assert row.country is None

    # Raw IP must not be persisted in any column.
    values = [v for v in asdict(row).values() if isinstance(v, str)]
    assert peer_ip not in values


@pytest.mark.anyio
async def test_session_cookie_is_set_and_reused_across_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.main.retrieve", _stub_retrieve)
    monkeypatch.setattr("app.main.synthesize_answer", _stub_synthesize_answer)
    monkeypatch.setenv("IP_HASH_SALT", "salt-a")

    captured: list[Any] = []
    monkeypatch.setattr("app.main.write_interaction_log", lambda row: captured.append(row))

    transport = httpx.ASGITransport(app=app, client=("198.51.100.77", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/chat", json={"question": "Q1"})
        second = await client.post("/chat", json={"question": "Q2"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(captured) == 2

    # Cookie should be set on first response and reused by the client on second.
    assert captured[0].session_id
    assert captured[1].session_id
    assert captured[0].session_id == captured[1].session_id


def test_privacy_ip_hash_depends_on_salt_and_prefix_is_correct() -> None:
    ip4 = "203.0.113.45"
    ip6 = "2001:db8:abcd:1234::1"

    assert anonymize_ip_prefix(ip4) == "203.0.113.0/24"
    assert anonymize_ip_prefix(ip6) == "2001:db8:abcd::/48"

    assert hash_ip(ip=ip4, salt="salt-a") == hash_ip(ip=ip4, salt="salt-a")
    assert hash_ip(ip=ip4, salt="salt-a") != hash_ip(ip=ip4, salt="salt-b")


@pytest.mark.anyio
async def test_x_forwarded_for_is_ignored_when_no_trusted_proxies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.main.retrieve", _stub_retrieve)
    monkeypatch.setattr("app.main.synthesize_answer", _stub_synthesize_answer)

    monkeypatch.setenv("IP_HASH_SALT", "salt-a")
    monkeypatch.delenv("TRUSTED_PROXY_CIDRS", raising=False)

    captured: list[Any] = []
    monkeypatch.setattr(
        "app.main.write_interaction_log", lambda row: captured.append(row)
    )

    peer_ip = "203.0.113.5"
    xff_ip = "198.51.100.99"
    transport = httpx.ASGITransport(app=app, client=(peer_ip, 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/chat",
            json={"question": "Q"},
            headers={"x-forwarded-for": xff_ip},
        )
    assert response.status_code == 200
    assert len(captured) == 1
    row = captured[0]

    # No TRUSTED_PROXY_CIDRS => XFF must be ignored; peer_ip is used.
    assert row.ip_prefix == "203.0.113.0/24"
    assert row.ip_hash == hash_ip(ip=peer_ip, salt="salt-a")


@pytest.mark.anyio
async def test_x_forwarded_for_is_honored_when_peer_is_trusted_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.main.retrieve", _stub_retrieve)
    monkeypatch.setattr("app.main.synthesize_answer", _stub_synthesize_answer)

    monkeypatch.setenv("IP_HASH_SALT", "salt-a")
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "203.0.113.0/24")

    captured: list[Any] = []
    monkeypatch.setattr(
        "app.main.write_interaction_log", lambda row: captured.append(row)
    )

    peer_ip = "203.0.113.5"  # immediate peer
    xff_ip = "198.51.100.99"  # original client
    transport = httpx.ASGITransport(app=app, client=(peer_ip, 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/chat",
            json={"question": "Q"},
            headers={"x-forwarded-for": f"{xff_ip}, {peer_ip}"},
        )
    assert response.status_code == 200
    assert len(captured) == 1
    row = captured[0]

    assert row.ip_prefix == "198.51.100.0/24"
    assert row.ip_hash == hash_ip(ip=xff_ip, salt="salt-a")


@pytest.mark.anyio
async def test_geoip_does_not_make_http_call_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.main.retrieve", _stub_retrieve)
    monkeypatch.setattr("app.main.synthesize_answer", _stub_synthesize_answer)

    # GeoIP is disabled by default; set explicitly for clarity.
    monkeypatch.setenv("GEOIP_ENABLED", "false")

    called = {"get": 0}

    def _fail_if_called(*args: Any, **kwargs: Any):
        called["get"] += 1
        raise AssertionError("GeoIP HTTP call should not occur when disabled")

    monkeypatch.setattr("app.geoip.httpx.Client.get", _fail_if_called)

    # Sanity: the helper should return without touching HTTP.
    from app.config import get_settings

    assert lookup_country("198.51.100.1", get_settings()) is None
    assert called["get"] == 0

    # And /chat should remain stable, with country left unset.
    captured: list[Any] = []
    monkeypatch.setattr(
        "app.main.write_interaction_log", lambda row: captured.append(row)
    )

    transport = httpx.ASGITransport(app=app, client=("198.51.100.77", 1234))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/chat", json={"question": "Q"})
    assert response.status_code == 200
    assert len(captured) == 1
    assert captured[0].country is None
