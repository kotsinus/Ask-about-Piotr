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
# Unit tests for privacy helpers (IP handling, proxy logic).

from __future__ import annotations

from dataclasses import replace
from typing import Any

from starlette.requests import Request

from app.config import Settings
from app.privacy import (
    _is_trusted_proxy,
    _parse_trusted_proxies,
    anonymize_ip_prefix,
    extract_client_ip,
)


def _settings(**overrides: Any) -> Settings:
    base = Settings(
        app_env="test",
        database_url="postgresql://test:test@localhost:5432/test",
        embeddings_provider="stub",
        embeddings_model=None,
        embeddings_dimensions=1536,
        openai_api_key=None,
        router_model="gpt-4.1-mini",
        synthesis_model="gpt-4o-mini",
        synthesis_temperature=0.1,
        prompt_cache_enabled=False,
        retrieval_max_distance=0.9,
        retrieval_distance_delta=0.25,
        retrieval_per_card_cap=2,
        ip_hash_salt="salt",
        trusted_proxy_cidrs=[],
        cookie_secure=False,
        cors_allow_origins=["http://localhost:3000"],
        geoip_enabled=False,
        geoip_provider="ipapi_co",
        geoip_url=None,
    )
    return replace(base, **overrides)


def _request(*, peer_ip: str | None, xff: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode("utf-8")))
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
    }
    if peer_ip is not None:
        scope["client"] = (peer_ip, 1234)
    return Request(scope)


def test_anonymize_ip_prefix_invalid_returns_none() -> None:
    assert anonymize_ip_prefix("not-an-ip") is None


def test_parse_trusted_proxies_skips_invalid_entries() -> None:
    nets = _parse_trusted_proxies(["10.0.0.0/8", "bad", "192.168.0.0/16"])
    assert len(nets) == 2


def test_is_trusted_proxy_empty_list_is_false() -> None:
    assert _is_trusted_proxy("10.0.0.1", []) is False


def test_is_trusted_proxy_invalid_peer_is_false() -> None:
    assert _is_trusted_proxy("bad-ip", ["10.0.0.0/8"]) is False


def test_extract_client_ip_returns_none_when_peer_missing() -> None:
    req = _request(peer_ip=None)
    assert extract_client_ip(req, _settings(trusted_proxy_cidrs=["10.0.0.0/8"])) is None


def test_extract_client_ip_uses_peer_when_proxy_not_trusted() -> None:
    req = _request(peer_ip="203.0.113.10", xff="198.51.100.10")
    settings = _settings(trusted_proxy_cidrs=["10.0.0.0/8"])
    assert extract_client_ip(req, settings) == "203.0.113.10"


def test_extract_client_ip_uses_xff_when_proxy_trusted_and_xff_valid() -> None:
    req = _request(peer_ip="10.0.0.1", xff="198.51.100.10, 203.0.113.99")
    settings = _settings(trusted_proxy_cidrs=["10.0.0.0/8"])
    assert extract_client_ip(req, settings) == "198.51.100.10"


def test_extract_client_ip_falls_back_to_peer_when_xff_first_ip_invalid() -> None:
    req = _request(peer_ip="10.0.0.1", xff="not-an-ip, 198.51.100.10")
    settings = _settings(trusted_proxy_cidrs=["10.0.0.0/8"])
    assert extract_client_ip(req, settings) == "10.0.0.1"
