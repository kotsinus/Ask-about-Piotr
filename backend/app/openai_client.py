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

import logging
from types import SimpleNamespace

from openai import OpenAI

from app.config import get_settings
from app.prompt_cache import TTLRUCache, make_cache_key

logger = logging.getLogger(__name__)

_client: OpenAI | None = None

# Cache OpenAI chat completion *responses* for deterministic calls.
#
# Why here:
# - Centralizes caching (and future retry/telemetry) in one place.
# - Controlled by Settings.prompt_cache_enabled.
#
# NOTE: This is not OpenAI's server-side "prompt caching" feature.
# It's a local, per-process response cache to reduce duplicate calls.
_CHAT_COMPLETION_CACHE = TTLRUCache[str](max_entries=256, ttl_seconds=15 * 60)


def get_openai_client() -> OpenAI:
    """Return a cached OpenAI client.

    Creating the SDK client repeatedly adds avoidable overhead and makes it
    harder to centralize retry/backoff and telemetry.
    """

    global _client
    if _client is None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY missing")
        _client = OpenAI(api_key=settings.openai_api_key)
    return _client


def _fake_chat_response(*, content: str):
    """Create a minimal response-like object compatible with existing callers."""

    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )


def chat_completions_create(**kwargs):
    """Create a chat completion with no local response caching."""

    client = get_openai_client()
    return client.chat.completions.create(**kwargs)


def chat_completions_create_cached(*, cache_namespace: str, **kwargs):
    """Create a chat completion, optionally served from an in-memory cache.

    Cache policy:
    - enabled only when Settings.prompt_cache_enabled is True
    - enabled only when temperature is 0 or None (avoid caching stochastic output)
    """

    settings = get_settings()
    temperature = kwargs.get("temperature")
    use_cache = bool(settings.prompt_cache_enabled) and (
        temperature in (None, 0) or temperature == 0.0
    )
    if not use_cache:
        return chat_completions_create(**kwargs)

    try:
        key = make_cache_key(namespace=cache_namespace, payload=kwargs)
    except TypeError:
        # Cache key creation can fail if kwargs contain non-JSON-serializable
        # objects. Caching must never break routing/rewrite.
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "prompt_cache_key_non_serializable_payload",
                extra={"cache_namespace": cache_namespace},
            )
        return chat_completions_create(**kwargs)

    cached = _CHAT_COMPLETION_CACHE.get(key)
    if cached is not None:
        return _fake_chat_response(content=cached)

    response = chat_completions_create(**kwargs)
    content = response.choices[0].message.content or ""
    _CHAT_COMPLETION_CACHE.set(key, content)
    return response
