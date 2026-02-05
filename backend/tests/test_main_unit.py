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
# Unit tests for small helpers and middleware error path in main.

from __future__ import annotations

from typing import Any

import pytest
from starlette.requests import Request

from app.main import _is_uuid, classify_question, request_logging_middleware
from app.schemas import Category


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        ("", False),
        ("not-a-uuid", False),
        ("00000000-0000-0000-0000-000000000000", True),
    ],
)
def test_is_uuid(value: str | None, expected: bool) -> None:
    assert _is_uuid(value) is expected


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Tell me about your team strategy", Category.leadership_and_product_strategy),
        ("Discuss system architecture", Category.architecture_and_system_design),
        ("AI embedding models?", Category.ai_and_ml_practice),
        ("Any publication paper?", Category.research_and_academic_credibility),
        (
            "Are you a good fit for this position?",
            Category.career_fit_and_role_alignment,
        ),
        ("What did you build?", Category.hands_on_engineering),
    ],
)
def test_classify_question_branches(question: str, expected: Category) -> None:
    assert classify_question(question) == expected


@pytest.mark.anyio
async def test_request_logging_middleware_logs_and_reraises_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: dict[str, Any] = {"reset": 0}

    monkeypatch.setattr("app.main.set_request_id", lambda rid: "token")
    monkeypatch.setattr(
        "app.main.reset_request_id",
        lambda token: called.__setitem__("reset", called["reset"] + 1),
    )

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/boom",
        "headers": [],
        "client": ("203.0.113.10", 1234),
    }
    request = Request(scope)

    async def _call_next(req: Request):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await request_logging_middleware(request, _call_next)

    assert called["reset"] == 1
