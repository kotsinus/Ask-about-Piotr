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
# Basic coverage for logging initialization and request-id middleware.

from __future__ import annotations

import httpx
import pytest

from app.logging_setup import configure_logging
from app.main import app
from app.observability import REQUEST_ID_HEADER


def test_configure_logging_does_not_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LOG_LEVEL", "INFO")
    monkeypatch.setenv("LOG_FORMAT", "json")
    configure_logging(force=True)


@pytest.mark.anyio
async def test_request_id_is_set_on_response_when_missing() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/healthz")
        assert response.status_code == 200
        assert response.headers.get(REQUEST_ID_HEADER)


@pytest.mark.anyio
async def test_request_id_is_propagated_when_present() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/healthz",
            headers={REQUEST_ID_HEADER: "test-request-id"},
        )
        assert response.status_code == 200
        assert response.headers.get(REQUEST_ID_HEADER) == "test-request-id"
