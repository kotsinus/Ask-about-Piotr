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
# Unit tests for GeoIP lookup, caching and error handling.

from __future__ import annotations

import json
from dataclasses import replace
from typing import Any

import httpx
import pytest

from app.config import Settings
from app.geoip import lookup_country


def _settings(**overrides: Any) -> Settings:
    base = Settings(
        database_url="postgresql://test:test@localhost:5432/test",
        embeddings_provider="stub",
        embeddings_model=None,
        embeddings_dimensions=1536,
        openai_api_key=None,
        router_model="gpt-4.1-mini",
        synthesis_model="gpt-4o-mini",
        prompt_cache_enabled=False,
        retrieval_max_distance=0.9,
        retrieval_distance_delta=0.25,
        ip_hash_salt="",
        trusted_proxy_cidrs=[],
        geoip_enabled=True,
        geoip_provider="ipapi_co",
        geoip_url=None,
    )
    return replace(base, **overrides)


class _FakeResponse:
    def __init__(
        self,
        *,
        headers: dict[str, str] | None = None,
        text: str = "",
        json_payload: dict[str, Any] | None = None,
        raise_for_status_exc: Exception | None = None,
    ) -> None:
        self.headers = headers or {}
        self.text = text
        self._json_payload = json_payload
        self._raise_for_status_exc = raise_for_status_exc

    def raise_for_status(self) -> None:
        if self._raise_for_status_exc is not None:
            raise self._raise_for_status_exc

    def json(self) -> dict[str, Any]:
        if self._json_payload is None:
            raise AssertionError("json() called but no JSON payload configured")
        return self._json_payload


def test_lookup_country_cache_hit_and_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(geoip_enabled=True)

    now = {"t": 100.0}
    monkeypatch.setattr("app.geoip.time.monotonic", lambda: now["t"])

    calls = {"get": 0}

    def _fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        calls["get"] += 1
        return _FakeResponse(text="pl\n", headers={"content-type": "text/plain"})

    monkeypatch.setattr("app.geoip.httpx.Client.get", _fake_get)

    ip = "198.51.100.10"
    assert lookup_country(ip, settings) == "PL"
    assert lookup_country(ip, settings) == "PL"
    assert calls["get"] == 1

    # After TTL (3600s) expires, it should perform a fresh lookup.
    now["t"] += 3600.0
    assert lookup_country(ip, settings) == "PL"
    assert calls["get"] == 2


def test_lookup_country_parses_application_json(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(geoip_enabled=True)
    monkeypatch.setattr("app.geoip.time.monotonic", lambda: 1.0)

    monkeypatch.setattr(
        "app.geoip.httpx.Client.get",
        lambda *a, **k: _FakeResponse(
            headers={"content-type": "application/json; charset=utf-8"},
            json_payload={"country": "de"},
        ),
    )

    assert lookup_country("203.0.113.77", settings) == "DE"


def test_lookup_country_accepts_country_code_fallback_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(geoip_enabled=True)
    monkeypatch.setattr("app.geoip.time.monotonic", lambda: 1.0)

    monkeypatch.setattr(
        "app.geoip.httpx.Client.get",
        lambda *a, **k: _FakeResponse(
            headers={"content-type": "application/json"},
            json_payload={"country_code": "fr"},
        ),
    )

    assert lookup_country("203.0.113.88", settings) == "FR"


def test_lookup_country_negative_caches_invalid_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(geoip_enabled=True)

    now = {"t": 10.0}
    monkeypatch.setattr("app.geoip.time.monotonic", lambda: now["t"])

    calls = {"get": 0}

    def _fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        calls["get"] += 1
        return _FakeResponse(text="USA", headers={"content-type": "text/plain"})

    monkeypatch.setattr("app.geoip.httpx.Client.get", _fake_get)

    ip = "198.51.100.99"
    assert lookup_country(ip, settings) is None
    assert lookup_country(ip, settings) is None
    assert calls["get"] == 1

    # After the negative TTL (300s), it should re-try.
    now["t"] += 300.0
    assert lookup_country(ip, settings) is None
    assert calls["get"] == 2


def test_lookup_country_handles_timeout_and_json_decode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(geoip_enabled=True)
    monkeypatch.setattr("app.geoip.time.monotonic", lambda: 1.0)

    def _timeout(*args: Any, **kwargs: Any):
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr("app.geoip.httpx.Client.get", _timeout)
    assert lookup_country("192.0.2.1", settings) is None

    class _BadJsonResponse(_FakeResponse):
        def json(self) -> dict[str, Any]:
            raise json.JSONDecodeError("bad", "{", 0)

    monkeypatch.setattr(
        "app.geoip.httpx.Client.get",
        lambda *a, **k: _BadJsonResponse(headers={"content-type": "application/json"}),
    )
    assert lookup_country("192.0.2.2", settings) is None


def test_lookup_country_handles_http_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(geoip_enabled=True)
    monkeypatch.setattr("app.geoip.time.monotonic", lambda: 1.0)

    def _http_error(*args: Any, **kwargs: Any):
        raise httpx.HTTPError("boom")

    monkeypatch.setattr("app.geoip.httpx.Client.get", _http_error)
    assert lookup_country("192.0.2.3", settings) is None


def test_lookup_country_uses_custom_url_template_and_provider_fallback_and_handles_unexpected_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings(
        geoip_enabled=True,
        geoip_provider="unknown-provider",
        geoip_url="https://example.test/geo/{ip}",
    )
    monkeypatch.setattr("app.geoip.time.monotonic", lambda: 1.0)

    captured = {"url": None}

    def _boom(self, url: str, **kwargs):
        captured["url"] = url
        raise RuntimeError("unexpected")

    monkeypatch.setattr("app.geoip.httpx.Client.get", _boom)
    assert lookup_country("203.0.113.1", settings) is None
    assert captured["url"] == "https://example.test/geo/203.0.113.1"
