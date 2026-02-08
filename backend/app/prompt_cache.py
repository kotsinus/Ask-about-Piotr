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

import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


def make_cache_key(*, namespace: str, payload: object) -> str:
    """Return a deterministic hash key for a JSON-serializable payload."""

    blob = json.dumps(
        {"namespace": namespace, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


@dataclass
class _Entry(Generic[T]):
    value: T
    expires_at: float


class TTLRUCache(Generic[T]):
    """A tiny in-memory TTL cache with LRU eviction.

    - Per-process, in-memory only.
    - Not thread-locked (good enough for typical FastAPI usage; worst case is
      duplicate in-flight calls).
    """

    def __init__(self, *, max_entries: int, ttl_seconds: float) -> None:
        if max_entries <= 0:
            raise ValueError("max_entries must be > 0")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be > 0")
        self._max_entries = int(max_entries)
        self._ttl_seconds = float(ttl_seconds)
        self._data: OrderedDict[str, _Entry[T]] = OrderedDict()

    def clear(self) -> None:
        self._data.clear()

    def get(self, key: str) -> T | None:
        now = time.monotonic()
        entry = self._data.get(key)
        if entry is None:
            return None
        if entry.expires_at <= now:
            self._data.pop(key, None)
            return None
        # LRU: mark as recently used.
        self._data.move_to_end(key)
        return entry.value

    def set(self, key: str, value: T) -> None:
        now = time.monotonic()
        self._data[key] = _Entry(value=value, expires_at=now + self._ttl_seconds)
        self._data.move_to_end(key)

        # Evict LRU items.
        while len(self._data) > self._max_entries:
            self._data.popitem(last=False)
