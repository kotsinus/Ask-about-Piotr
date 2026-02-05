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
# Optional geo-country lookup for client IP.

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class _CacheEntry:
    country: str | None
    expires_at: float


_CACHE: dict[str, _CacheEntry] = {}


def _cache_get(ip: str) -> str | None | object:
    entry = _CACHE.get(ip)
    if not entry:
        return _MISSING
    if time.monotonic() >= entry.expires_at:
        _CACHE.pop(ip, None)
        return _MISSING
    return entry.country


def _cache_set(ip: str, country: str | None, *, ttl_seconds: float) -> None:
    _CACHE[ip] = _CacheEntry(country=country, expires_at=time.monotonic() + ttl_seconds)


_MISSING = object()


def _build_url(settings: Settings, ip: str) -> str:
    if settings.geoip_url:
        return settings.geoip_url.replace("{ip}", ip)

    provider = settings.geoip_provider.strip().lower()
    if provider in {"ipapi", "ipapi_co", "ipapi.co"}:
        # Returns plain text country code with trailing newline.
        return f"https://ipapi.co/{ip}/country/"

    # Fallback to ipapi.co semantics.
    return f"https://ipapi.co/{ip}/country/"


def lookup_country(ip: str, settings: Settings) -> str | None:
    """Return 2-letter country code (best effort). Default is disabled."""

    if not settings.geoip_enabled:
        return None

    cached = _cache_get(ip)
    if cached is not _MISSING:
        return cached  # type: ignore[return-value]

    url = _build_url(settings, ip)

    timeout = httpx.Timeout(0.8, connect=0.3)
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.get(
                url, headers={"accept": "application/json, text/plain"}
            )
            response.raise_for_status()

            content_type = response.headers.get("content-type", "").lower()
            if "application/json" in content_type:
                payload = response.json()
                country = payload.get("country") or payload.get("country_code")
                if country:
                    country = str(country).strip().upper()
            else:
                country = response.text.strip().upper()

            if country and len(country) == 2:
                _cache_set(ip, country, ttl_seconds=3600)
                return country

    except (httpx.TimeoutException, httpx.HTTPError, json.JSONDecodeError) as exc:
        logger.info("geoip_lookup_failed", extra={"error": str(exc)})
    except Exception:
        logger.exception("geoip_lookup_failed")

    _cache_set(ip, None, ttl_seconds=300)
    return None
