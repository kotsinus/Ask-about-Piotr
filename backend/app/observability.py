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
# Small observability helpers (request-id context propagation).

from __future__ import annotations

from contextvars import ContextVar

REQUEST_ID_HEADER = "X-Request-ID"

_request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return _request_id_ctx.get()


def set_request_id(request_id: str | None) -> ContextVar.Token[str | None]:
    return _request_id_ctx.set(request_id)


def reset_request_id(token: ContextVar.Token[str | None]) -> None:
    _request_id_ctx.reset(token)
