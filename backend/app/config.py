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

import json
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


def _parse_json_object(value: str | None) -> dict:
    if not value:
        return {}
    lowered = value.strip().lower()
    if lowered in {"", "none", "null", "off", "false"}:
        return {}
    try:
        payload = json.loads(value)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


@dataclass(frozen=True)
class Settings:
    # Deployment environment (used for safety checks)
    app_env: str

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
    retrieval_per_card_cap: int

    # Privacy-first logging / metadata
    ip_hash_salt: str
    trusted_proxy_cidrs: list[str]

    # Interaction logging controls
    interaction_log_include_llm_context: bool

    # Web security / cross-origin configuration
    cookie_secure: bool
    cors_allow_origins: list[str]

    # Optional GEO-IP lookup (default OFF)
    geoip_enabled: bool
    geoip_provider: str
    geoip_url: str | None

    # Multi-category routing/retrieval feature flags (default OFF)
    # NOTE: defaults are duplicated here so tests that instantiate Settings directly
    # don't have to pass the fields.
    multi_category_retrieval_enabled: bool = False
    multi_category_max_categories: int = 2
    multi_category_max_total_chunks: int = 5
    multi_category_allow_six_chunks: bool = False
    multi_category_intent_budget_policy: str = "intent_rules_v1"
    multi_category_rollout_percent: int = 0

    # Retrieval oversampling policy (general mechanism):
    # - default used for per-category retrieval when caller does not override.
    # - optional per-category overrides by canonical category string.
    # Default oversampling for per-category retrieval.
    # Plan v1 target: keep it moderate to reduce noisy candidates.
    multi_category_oversample_default: int = 5
    multi_category_oversample_by_category: dict[str, int] | None = None

    # OpenAI SDK behavior controls (keep defaults safe for local dev).
    openai_timeout_s: float = 60.0
    openai_max_retries: int = 2


@dataclass(frozen=True)
class WebSettings:
    cookie_secure: bool
    cors_allow_origins: list[str]


def get_web_settings() -> WebSettings:
    """Settings needed at import time (must NOT require DATABASE_URL)."""

    cookie_secure = _parse_bool(os.getenv("COOKIE_SECURE"), default=False)
    cors_allow_origins = _parse_csv(
        os.getenv("CORS_ALLOW_ORIGINS", "http://localhost:3000")
    )
    return WebSettings(
        cookie_secure=cookie_secure, cors_allow_origins=cors_allow_origins
    )


def _parse_optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in {"", "none", "null", "off", "false"}:
        return None
    return float(lowered)


def get_settings() -> Settings:
    app_env = (os.getenv("APP_ENV", "dev") or "dev").strip().lower()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required.")

    embeddings_provider = (
        (os.getenv("EMBEDDINGS_PROVIDER", "stub") or "stub").strip().lower()
    )
    embeddings_model = os.getenv("EMBEDDINGS_MODEL")
    embeddings_dimensions = int(os.getenv("EMBEDDINGS_DIMENSIONS", "1536"))
    openai_api_key = os.getenv("OPENAI_API_KEY")
    try:
        openai_timeout_s = float(os.getenv("OPENAI_TIMEOUT_S", "60"))
    except Exception:
        openai_timeout_s = 60.0
    try:
        openai_max_retries = int(os.getenv("OPENAI_MAX_RETRIES", "2"))
    except Exception:
        openai_max_retries = 2
    openai_max_retries = max(0, openai_max_retries)
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

    # Retrieval result diversification.
    # - Caps how many chunks can come from a single card during the capped passes.
    # - The final fill pass may exceed it when there aren't enough distinct cards.
    try:
        retrieval_per_card_cap = int(os.getenv("RETRIEVAL_PER_CARD_CAP", "2"))
    except Exception:
        retrieval_per_card_cap = 2
    retrieval_per_card_cap = max(1, retrieval_per_card_cap)

    # Multi-category routing/retrieval flags
    multi_category_retrieval_enabled = _parse_bool(
        os.getenv("MULTI_CATEGORY_RETRIEVAL_ENABLED"),
        default=False,
    )
    try:
        multi_category_max_categories = int(
            os.getenv("MULTI_CATEGORY_MAX_CATEGORIES", "2")
        )
    except Exception:
        multi_category_max_categories = 2
    multi_category_max_categories = max(1, multi_category_max_categories)

    try:
        multi_category_max_total_chunks = int(
            os.getenv("MULTI_CATEGORY_MAX_TOTAL_CHUNKS", "5")
        )
    except Exception:
        multi_category_max_total_chunks = 5
    multi_category_max_total_chunks = max(1, multi_category_max_total_chunks)

    multi_category_allow_six_chunks = _parse_bool(
        os.getenv("MULTI_CATEGORY_ALLOW_SIX_CHUNKS"),
        default=False,
    )
    multi_category_intent_budget_policy = (
        os.getenv("MULTI_CATEGORY_INTENT_BUDGET_POLICY", "intent_rules_v1")
        or "intent_rules_v1"
    ).strip()

    # Rollout sampling (0..100). When 0, feature remains OFF even if enabled.
    try:
        multi_category_rollout_percent = int(
            os.getenv("MULTI_CATEGORY_ROLLOUT_PERCENT", "0")
        )
    except Exception:
        multi_category_rollout_percent = 0
    multi_category_rollout_percent = max(0, min(100, multi_category_rollout_percent))

    # Retrieval oversampling policy (general mechanism).
    try:
        multi_category_oversample_default = int(
            os.getenv("MULTI_CATEGORY_OVERSAMPLE_DEFAULT", "5")
        )
    except Exception:
        multi_category_oversample_default = 5
    multi_category_oversample_default = max(1, multi_category_oversample_default)

    raw_oversample_by_category = _parse_json_object(
        os.getenv("MULTI_CATEGORY_OVERSAMPLE_BY_CATEGORY")
    )
    multi_category_oversample_by_category: dict[str, int] | None = None
    if raw_oversample_by_category:
        parsed: dict[str, int] = {}
        for k, v in raw_oversample_by_category.items():
            key = str(k).strip()
            if not key:
                continue
            try:
                parsed[key] = max(1, int(v))
            except Exception:
                continue
        multi_category_oversample_by_category = parsed or None

    # Logging metadata
    ip_hash_salt = os.getenv("IP_HASH_SALT", "")
    if app_env in {"prod", "production"} and not ip_hash_salt.strip():
        raise RuntimeError("IP_HASH_SALT is required in production.")

    # Fail fast on unsafe/default embedding configuration in production.
    # Without embeddings, retrieval cannot run and /chat will 500 at runtime.
    if app_env in {"prod", "production"}:
        if embeddings_provider == "stub":
            raise RuntimeError(
                "EMBEDDINGS_PROVIDER must be configured for production (e.g., 'openai'); "
                "the default 'stub' provider raises at runtime."
            )
        if embeddings_provider == "openai" and not (openai_api_key or "").strip():
            raise RuntimeError(
                "OPENAI_API_KEY is required when EMBEDDINGS_PROVIDER=openai."
            )

    trusted_proxy_cidrs = _parse_csv(os.getenv("TRUSTED_PROXY_CIDRS"))

    interaction_log_include_llm_context = _parse_bool(
        os.getenv("INTERACTION_LOG_INCLUDE_LLM_CONTEXT"), default=True
    )

    # Web security / CORS
    web = get_web_settings()

    geoip_enabled = _parse_bool(os.getenv("GEOIP_ENABLED"), default=False)
    geoip_provider = (os.getenv("GEOIP_PROVIDER", "ipapi_co") or "ipapi_co").strip()
    geoip_url = os.getenv("GEOIP_URL")

    return Settings(
        app_env=app_env,
        database_url=database_url,
        embeddings_provider=embeddings_provider,
        embeddings_model=embeddings_model,
        embeddings_dimensions=embeddings_dimensions,
        openai_api_key=openai_api_key,
        openai_timeout_s=openai_timeout_s,
        openai_max_retries=openai_max_retries,
        router_model=router_model,
        synthesis_model=synthesis_model,
        synthesis_temperature=synthesis_temperature,
        prompt_cache_enabled=prompt_cache_enabled,
        retrieval_max_distance=retrieval_max_distance,
        retrieval_distance_delta=retrieval_distance_delta,
        retrieval_per_card_cap=retrieval_per_card_cap,
        multi_category_retrieval_enabled=multi_category_retrieval_enabled,
        multi_category_max_categories=multi_category_max_categories,
        multi_category_max_total_chunks=multi_category_max_total_chunks,
        multi_category_allow_six_chunks=multi_category_allow_six_chunks,
        multi_category_intent_budget_policy=multi_category_intent_budget_policy,
        multi_category_rollout_percent=multi_category_rollout_percent,
        multi_category_oversample_default=multi_category_oversample_default,
        multi_category_oversample_by_category=multi_category_oversample_by_category,
        ip_hash_salt=ip_hash_salt,
        trusted_proxy_cidrs=trusted_proxy_cidrs,
        interaction_log_include_llm_context=interaction_log_include_llm_context,
        cookie_secure=web.cookie_secure,
        cors_allow_origins=web.cors_allow_origins,
        geoip_enabled=geoip_enabled,
        geoip_provider=geoip_provider,
        geoip_url=geoip_url,
    )
