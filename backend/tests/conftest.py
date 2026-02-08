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
# Ensures the backend package is importable during tests.

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(autouse=True)
def _test_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
    monkeypatch.setenv("EMBEDDINGS_PROVIDER", "stub")
    monkeypatch.setenv("PROMPT_CACHE_ENABLED", "false")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


@pytest.fixture(autouse=True)
def _reset_module_state() -> None:
    """Reset in-memory module state that could leak across tests."""

    # GeoIP has an in-memory cache.
    from app import geoip

    geoip._CACHE.clear()

    # Interaction logging can disable itself after repeated failures.
    from app import interaction_logging

    interaction_logging._INTERACTION_LOGGING_DISABLED_REASON = None

    # LLM has an in-memory prompt/response cache.
    from app import openai_client

    openai_client._CHAT_COMPLETION_CACHE.clear()


@pytest.fixture
def asgi_transport():
    from app.main import app

    return httpx.ASGITransport(app=app)


@pytest.fixture
async def asgi_client(asgi_transport: httpx.ASGITransport):
    async with httpx.AsyncClient(
        transport=asgi_transport,
        base_url="http://test",
    ) as client:
        yield client
