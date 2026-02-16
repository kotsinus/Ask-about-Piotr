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

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import openai_client


def test_get_openai_client_requires_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(openai_client, "_client", None)
    monkeypatch.setattr(
        openai_client, "get_settings", lambda: SimpleNamespace(openai_api_key=None)
    )
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        openai_client.get_openai_client()


def test_get_openai_client_creates_client_with_timeout_and_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that OpenAI client is created with timeout and retries settings."""
    created_kwargs: dict = {}

    class _MockOpenAI:
        def __init__(self, **kwargs):
            created_kwargs.update(kwargs)
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self._create)
            )

        def _create(self, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="test"))]
            )

    monkeypatch.setattr(openai_client, "_client", None)
    monkeypatch.setattr(
        openai_client,
        "get_settings",
        lambda: SimpleNamespace(
            openai_api_key="test-key",
            openai_timeout_s=30.0,
            openai_max_retries=3,
        ),
    )
    monkeypatch.setattr(openai_client, "OpenAI", _MockOpenAI)

    client = openai_client.get_openai_client()
    assert created_kwargs["api_key"] == "test-key"
    assert created_kwargs["timeout"] == 30.0
    assert created_kwargs["max_retries"] == 3


def test_get_openai_client_fallback_on_typeerror(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that client creation falls back to api_key-only on TypeError."""

    class _OpenAIWithTypeError:
        call_count = 0

        def __init__(self, **kwargs):
            _OpenAIWithTypeError.call_count += 1
            if "timeout" in kwargs:
                raise TypeError("unexpected keyword argument 'timeout'")
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(create=self._create)
            )

        def _create(self, **kwargs):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="test"))]
            )

    monkeypatch.setattr(openai_client, "_client", None)
    monkeypatch.setattr(
        openai_client,
        "get_settings",
        lambda: SimpleNamespace(
            openai_api_key="test-key",
            openai_timeout_s=30.0,
            openai_max_retries=3,
        ),
    )
    monkeypatch.setattr(openai_client, "OpenAI", _OpenAIWithTypeError)

    client = openai_client.get_openai_client()
    # Should have been called twice: once with full args, once with just api_key
    assert _OpenAIWithTypeError.call_count == 2


def test_chat_completions_create_logs_and_reraises_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that chat_completions_create logs and re-raises exceptions."""

    class _MockClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            raise RuntimeError("API error")

    monkeypatch.setattr(openai_client, "_client", _MockClient())

    with pytest.raises(RuntimeError, match="API error"):
        openai_client.chat_completions_create(model="test", messages=[])


def test_chat_completions_create_cached_bypasses_cache_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that caching is bypassed when prompt_cache_enabled is False."""
    calls: list[dict] = []

    class _MockClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="response"))]
            )

    monkeypatch.setattr(openai_client, "_client", _MockClient())
    monkeypatch.setattr(
        openai_client,
        "get_settings",
        lambda: SimpleNamespace(prompt_cache_enabled=False),
    )

    result = openai_client.chat_completions_create_cached(
        cache_namespace="test", model="gpt", messages=[], temperature=0
    )
    assert len(calls) == 1


def test_chat_completions_create_cached_bypasses_cache_with_nonzero_temperature(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that caching is bypassed when temperature is non-zero."""
    calls: list[dict] = []

    class _MockClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="response"))]
            )

    monkeypatch.setattr(openai_client, "_client", _MockClient())
    monkeypatch.setattr(
        openai_client,
        "get_settings",
        lambda: SimpleNamespace(prompt_cache_enabled=True),
    )

    result = openai_client.chat_completions_create_cached(
        cache_namespace="test", model="gpt", messages=[], temperature=0.5
    )
    assert len(calls) == 1


def test_chat_completions_create_cached_uses_cache_on_hit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that cached response is returned on cache hit."""
    calls: list[dict] = []

    class _MockClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="fresh response"))]
            )

    monkeypatch.setattr(openai_client, "_client", _MockClient())
    monkeypatch.setattr(
        openai_client,
        "get_settings",
        lambda: SimpleNamespace(prompt_cache_enabled=True),
    )

    # First call should hit the API
    result1 = openai_client.chat_completions_create_cached(
        cache_namespace="test", model="gpt", messages=[{"role": "user", "content": "hello"}], temperature=0
    )
    assert len(calls) == 1
    assert result1.choices[0].message.content == "fresh response"

    # Second call with same params should return cached response
    result2 = openai_client.chat_completions_create_cached(
        cache_namespace="test", model="gpt", messages=[{"role": "user", "content": "hello"}], temperature=0
    )
    assert len(calls) == 1  # No additional API call
    assert result2.choices[0].message.content == "fresh response"


def test_chat_completions_create_cached_handles_non_serializable_payload(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Test that non-serializable payload bypasses cache gracefully."""
    calls: list[dict] = []

    class _MockClient:
        def __init__(self):
            self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

        def _create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="response"))]
            )

    monkeypatch.setattr(openai_client, "_client", _MockClient())
    monkeypatch.setattr(
        openai_client,
        "get_settings",
        lambda: SimpleNamespace(prompt_cache_enabled=True),
    )

    # Create a non-serializable object
    class NonSerializable:
        pass

    result = openai_client.chat_completions_create_cached(
        cache_namespace="test",
        model="gpt",
        messages=[],
        temperature=0,
        non_serializable=NonSerializable(),  # This will cause TypeError in cache key creation
    )
    # Should still work, just bypassing cache
    assert len(calls) == 1


def test_fake_chat_response() -> None:
    """Test _fake_chat_response creates correct structure."""
    response = openai_client._fake_chat_response(content="test content")
    assert response.choices[0].message.content == "test content"
