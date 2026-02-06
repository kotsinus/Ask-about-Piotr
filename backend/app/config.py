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
# Centralized runtime configuration for database and embedding settings.
#
# Notes:
# Keep defaults safe and explicit; enforce missing required config.

from __future__ import annotations

import os
from dataclasses import dataclass


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_csv(value: str | None) -> list[str]:
    if not value:
        return []
    parts = [item.strip() for item in value.split(",")]
    return [item for item in parts if item]


@dataclass(frozen=True)
class Settings:
    database_url: str
    embeddings_provider: str
    embeddings_model: str | None
    embeddings_dimensions: int
    openai_api_key: str | None
    router_model: str
    synthesis_model: str
    synthesis_temperature: float
    prompt_cache_enabled: bool
    retrieval_max_distance: float | None
    retrieval_distance_delta: float | None

    # Privacy-first logging / metadata
    ip_hash_salt: str
    trusted_proxy_cidrs: list[str]

    # Optional GEO-IP lookup (default OFF)
    geoip_enabled: bool
    geoip_provider: str
    geoip_url: str | None


def _parse_optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in {"", "none", "null", "off", "false"}:
        return None
    return float(lowered)


def get_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required.")

    embeddings_provider = os.getenv("EMBEDDINGS_PROVIDER", "stub")
    embeddings_model = os.getenv("EMBEDDINGS_MODEL")
    embeddings_dimensions = int(os.getenv("EMBEDDINGS_DIMENSIONS", "1536"))
    openai_api_key = os.getenv("OPENAI_API_KEY")
    router_model = os.getenv("ROUTER_MODEL", "gpt-4.1-mini")
    synthesis_model = os.getenv("SYNTHESIS_MODEL", "gpt-4o-mini")
    synthesis_temperature = float(os.getenv("SYNTHESIS_TEMPERATURE", "0.1"))
    prompt_cache_enabled = os.getenv("PROMPT_CACHE_ENABLED", "true").lower() in (
        "1",
        "true",
        "yes",
    )

    # Retrieval cutoffs (cosine distance): conservative defaults.
    # - Lower distance = more similar.
    # - You can disable each cutoff by setting the env var to "off".
    retrieval_max_distance = _parse_optional_float(
        os.getenv("RETRIEVAL_MAX_DISTANCE", "0.90")
    )
    retrieval_distance_delta = _parse_optional_float(
        os.getenv("RETRIEVAL_DISTANCE_DELTA", "0.25")
    )

    # Logging metadata
    ip_hash_salt = os.getenv("IP_HASH_SALT", "")
    trusted_proxy_cidrs = _parse_csv(os.getenv("TRUSTED_PROXY_CIDRS"))

    geoip_enabled = _parse_bool(os.getenv("GEOIP_ENABLED"), default=False)
    geoip_provider = (os.getenv("GEOIP_PROVIDER", "ipapi_co") or "ipapi_co").strip()
    geoip_url = os.getenv("GEOIP_URL")

    return Settings(
        database_url=database_url,
        embeddings_provider=embeddings_provider,
        embeddings_model=embeddings_model,
        embeddings_dimensions=embeddings_dimensions,
        openai_api_key=openai_api_key,
        router_model=router_model,
        synthesis_model=synthesis_model,
        synthesis_temperature=synthesis_temperature,
        prompt_cache_enabled=prompt_cache_enabled,
        retrieval_max_distance=retrieval_max_distance,
        retrieval_distance_delta=retrieval_distance_delta,
        ip_hash_salt=ip_hash_salt,
        trusted_proxy_cidrs=trusted_proxy_cidrs,
        geoip_enabled=geoip_enabled,
        geoip_provider=geoip_provider,
        geoip_url=geoip_url,
    )
