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
# API-level tests for /healthz and OpenAI exception handlers.

from __future__ import annotations

import httpx
import pytest
from openai import APIConnectionError, APIError, AuthenticationError, RateLimitError


@pytest.mark.anyio
async def test_healthz(asgi_client: httpx.AsyncClient) -> None:
    response = await asgi_client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def _httpx_request() -> httpx.Request:
    return httpx.Request("POST", "http://test/chat")


def _httpx_response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code=status_code, request=_httpx_request())


@pytest.mark.anyio
@pytest.mark.parametrize(
    "exc, expected_status, expected_type",
    [
        (
            RateLimitError(
                "rate-limited",
                response=_httpx_response(429),
                body={"error": "rate"},
            ),
            429,
            "rate_limit",
        ),
        (
            AuthenticationError(
                "auth",
                response=_httpx_response(401),
                body={"error": "auth"},
            ),
            401,
            "auth_error",
        ),
        (
            APIConnectionError(message="conn", request=_httpx_request()),
            503,
            "openai_unavailable",
        ),
        (
            APIError("api", request=_httpx_request(), body=None),
            503,
            "openai_unavailable",
        ),
    ],
)
async def test_openai_exception_handlers(
    monkeypatch: pytest.MonkeyPatch,
    asgi_client: httpx.AsyncClient,
    exc: Exception,
    expected_status: int,
    expected_type: str,
) -> None:
    # /chat calls rewrite_question() before any try/except, so raising here should
    # be handled by the FastAPI exception handlers.
    monkeypatch.setattr("app.main.rewrite_question", lambda *a, **k: (_ for _ in ()).throw(exc))

    response = await asgi_client.post("/chat", json={"question": "Q"})
    assert response.status_code == expected_status
    payload = response.json()
    assert payload.get("type") == expected_type
    assert payload.get("detail")

