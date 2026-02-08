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

from openai import OpenAI

from app.config import get_settings

_client: OpenAI | None = None


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

