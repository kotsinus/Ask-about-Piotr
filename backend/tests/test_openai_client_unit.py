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
