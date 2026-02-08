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
# Ensure PROMPT_CACHE_ENABLED actually affects OpenAI chat calls.

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.llm import route_category


def test_ttlru_cache_validates_expires_and_evicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.prompt_cache import TTLRUCache

    with pytest.raises(ValueError, match="max_entries"):
        TTLRUCache(max_entries=0, ttl_seconds=1)
    with pytest.raises(ValueError, match="ttl_seconds"):
        TTLRUCache(max_entries=1, ttl_seconds=0)

    now = {"t": 100.0}
    monkeypatch.setattr("app.prompt_cache.time.monotonic", lambda: now["t"])

    cache = TTLRUCache(max_entries=2, ttl_seconds=10)
    cache.set("a", 1)
    cache.set("b", 2)

    # Touch "a" so "b" becomes LRU.
    assert cache.get("a") == 1
    cache.set("c", 3)
    assert cache.get("b") is None

    # Expiry removes entry and returns None.
    now["t"] += 11.0
    assert cache.get("a") is None


class _FakeOpenAI:
    def __init__(self, *, api_key: str, create_impl):
        self.api_key = api_key
        self._create_impl = create_impl

        class _Chat:
            def __init__(self, outer):
                self.completions = outer

        self.chat = _Chat(self)

    def create(self, **kwargs):
        return self._create_impl(**kwargs)


def _chat_response(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def test_prompt_cache_enabled_reuses_response_for_identical_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("PROMPT_CACHE_ENABLED", "true")

    calls = {"n": 0}

    def _create_impl(**kwargs):
        calls["n"] += 1
        return _chat_response(json.dumps({"category": "AI and ML practice"}))

    monkeypatch.setattr("app.openai_client._client", None)
    monkeypatch.setattr(
        "app.openai_client.OpenAI",
        lambda api_key: _FakeOpenAI(api_key=api_key, create_impl=_create_impl),
    )

    assert route_category("What is an embedding?")
    assert route_category("What is an embedding?")
    assert calls["n"] == 1
