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
from dataclasses import dataclass, field


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


def _parse_pinning_rules(value: str | None) -> dict[str, list[str]]:
    """Parse pinning rules from JSON environment variable.

    Args:
        value: JSON string mapping RoutingCategory values to lists of card IDs to pin.
            Example: '{"education_and_formal_background": ["education-facts"]}'

    Returns:
        Dict mapping RoutingCategory values to lists of card IDs. Empty dict if not set.
    """
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            parsed = _normalize_router_category_map(parsed)
            # Validate structure: dict[str, list[str]]
            result: dict[str, list[str]] = {}
            for category, card_ids in parsed.items():
                if isinstance(category, str) and isinstance(card_ids, list):
                    # Ensure all card IDs are strings
                    result[category] = [str(cid) for cid in card_ids if cid]
            return result
    except json.JSONDecodeError:
        pass
    return {}


def _normalize_router_category_name(value: str) -> str:
    """Normalize router category names.

    Router category strings are used as dictionary keys in settings (pinning,
    section weights, quality rules).

    NOTE: This function intentionally does NOT perform taxonomy migrations or
    legacy-name mapping. Only canonical category strings should be used.
    """

    return (value or "").strip()


def _normalize_router_category_map(value: dict[str, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, val in (value or {}).items():
        if not isinstance(key, str):
            continue
        normalized[_normalize_router_category_name(key)] = val
    return normalized


def _parse_section_weights(value: str | None) -> dict[str, dict[str, float]]:
    """Parse section weights from JSON environment variable.

    Args:
        value: JSON string mapping RoutingCategory values to section weight maps.
            Example: '{"education_and_formal_background": {"degrees": 0.15, "education": 0.12}}'

    Returns:
        Dict mapping RoutingCategory values to section weight maps. Empty dict if not set.
        Section weights are positive floats that BOOST section ranking (subtract from distance).
    """
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            parsed = _normalize_router_category_map(parsed)
            # Validate structure: dict[str, dict[str, float]]
            result: dict[str, dict[str, float]] = {}
            for category, weights in parsed.items():
                if isinstance(category, str) and isinstance(weights, dict):
                    # Ensure all weights are floats
                    section_weights: dict[str, float] = {}
                    for section, weight in weights.items():
                        if isinstance(section, str):
                            try:
                                # Clamp weight to reasonable range [0.0, 0.5]
                                # This prevents extreme values from distorting ranking
                                raw_weight = float(weight)
                                section_weights[section] = max(
                                    0.0, min(0.5, raw_weight)
                                )
                            except (ValueError, TypeError):
                                pass
                    if section_weights:
                        result[category] = section_weights
            return result
    except json.JSONDecodeError:
        pass
    return {}


def _parse_quality_rules(value: str | None) -> dict[str, dict[str, list[str] | int]]:
    """Parse quality rules from JSON environment variable.

    Args:
        value: JSON string mapping RoutingCategory values to quality rule configs.
            Example: '{"education_and_formal_background": {"min_tokens": ["degree", "university"], "min_token_count": 1}}'

    Returns:
        Dict mapping RoutingCategory values to quality rule configs. Empty dict if not set.
        Each rule config can contain:
        - min_tokens: list of required tokens (any must be present)
        - min_token_count: minimum number of tokens that must be present (default 1)
    """
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            parsed = _normalize_router_category_map(parsed)
            # Validate structure: dict[str, dict]
            result: dict[str, dict[str, list[str] | int]] = {}
            for category, rules in parsed.items():
                if isinstance(category, str) and isinstance(rules, dict):
                    validated_rules: dict[str, list[str] | int] = {}
                    # Validate min_tokens
                    min_tokens = rules.get("min_tokens")
                    if isinstance(min_tokens, list):
                        validated_rules["min_tokens"] = [
                            str(t) for t in min_tokens if t
                        ]
                    # Validate min_token_count
                    min_token_count = rules.get("min_token_count")
                    if isinstance(min_token_count, (int, float)):
                        validated_rules["min_token_count"] = max(
                            1, int(min_token_count)
                        )
                    if validated_rules:
                        result[category] = validated_rules
            return result
    except json.JSONDecodeError:
        pass
    return {}


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

    # Multi-category routing + per-category retrieval (flag-gated)
    #
    # Defaults are set here so unit tests can build Settings() directly without
    # needing to specify these fields.
    multi_category_retrieval_enabled: bool = False
    multi_category_rollout_percent: int = 0
    multi_category_max_categories: int = 2
    multi_category_max_total_chunks: int = 5
    multi_category_allow_six_chunks: bool = False
    multi_category_budget_policy: str = "deterministic"

    # Multi-category pinning rules.
    #
    # Pinning ensures specific cards are always included in retrieval results
    # for certain routing categories, regardless of their similarity score. This is a
    # general mechanism applicable to any routing category.
    #
    # Configuration:
    # - Map RoutingCategory values to lists of card IDs that should be pinned
    # - Set via MULTI_CATEGORY_PINNING_RULES environment variable (JSON format)
    # - Example: '{"education_and_formal_background": ["education-facts"]}'
    #
    # Use cases:
    # - Ensure foundational/essential cards are always retrieved
    # - Guarantee important context appears in multi-category responses
    # - Override similarity-based ranking for critical information
    multi_category_pinning_rules: dict[str, list[str]] = field(
        default_factory=lambda: {
            "education_and_formal_background": ["education-facts"],
        }
    )

    # Multi-category section weights.
    #
    # Section weights allow routing_category-specific boosting of certain sections during
    # retrieval. This is a general mechanism applicable to any routing category.
    #
    # Configuration:
    # - Map RoutingCategory values to section weight maps (section name -> weight)
    # - Set via MULTI_CATEGORY_SECTION_WEIGHTS environment variable (JSON format)
    # - Example: '{"education_and_formal_background": {"degrees": 0.15, "education": 0.12}}'
    #
    # How it works:
    # - Weights are POSITIVE values that BOOST section ranking (subtract from distance)
    # - Formula: adjusted_distance = distance + penalty - bonus
    # - Maximum bonus is capped at 0.25 to prevent weak chunks from jumping strong ones
    #
    # Use cases:
    # - Boost "degrees" sections for education_and_formal_background routing category
    # - Boost "publications" sections for research_and_academic_credibility routing category
    # - Improve precision for routing_category-specific retrieval
    multi_category_section_weights: dict[str, dict[str, float]] = field(
        default_factory=dict
    )

    # Multi-category quality rules.
    #
    # Quality rules allow routing_category-specific validation of synthesized answers.
    # This is a general mechanism applicable to any routing category.
    #
    # Configuration:
    # - Map RoutingCategory values to quality rule configs
    # - Set via MULTI_CATEGORY_QUALITY_RULES environment variable (JSON format)
    # - Example: '{"education_and_formal_background": {"min_tokens": ["degree", "university"], "min_token_count": 1}}'
    #
    # How it works:
    # - min_tokens: list of required tokens (at least min_token_count must be present)
    # - min_token_count: minimum number of tokens that must be present (default 1)
    #
    # Use cases:
    # - Ensure education_and_formal_background answers contain education-related terms
    # - Ensure hands_on_engineering answers contain named examples
    # - Detect generic/low-quality answers for retry
    #
    # NOTE: In v1, quality rules are LOG-ONLY (no retry trigger).
    # This allows monitoring false positives before enabling enforcement.
    multi_category_quality_rules: dict[str, dict[str, list[str] | int]] = field(
        default_factory=dict
    )

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

    # Multi-category routing + per-category retrieval.
    multi_category_retrieval_enabled = _parse_bool(
        os.getenv("MULTI_CATEGORY_RETRIEVAL_ENABLED"), default=False
    )
    try:
        multi_category_rollout_percent = int(
            os.getenv("MULTI_CATEGORY_ROLLOUT_PERCENT", "0")
        )
    except Exception:
        multi_category_rollout_percent = 0
    multi_category_rollout_percent = max(0, min(100, multi_category_rollout_percent))

    try:
        multi_category_max_categories = int(
            os.getenv("MULTI_CATEGORY_MAX_CATEGORIES", "2")
        )
    except Exception:
        multi_category_max_categories = 2
    multi_category_max_categories = max(1, min(3, multi_category_max_categories))

    try:
        multi_category_max_total_chunks = int(
            os.getenv("MULTI_CATEGORY_MAX_TOTAL_CHUNKS", "5")
        )
    except Exception:
        multi_category_max_total_chunks = 5
    multi_category_max_total_chunks = max(1, min(10, multi_category_max_total_chunks))

    multi_category_allow_six_chunks = _parse_bool(
        os.getenv("MULTI_CATEGORY_ALLOW_SIX_CHUNKS"), default=False
    )
    multi_category_budget_policy = (
        os.getenv("MULTI_CATEGORY_BUDGET_POLICY", "deterministic") or "deterministic"
    ).strip()

    # Multi-category pinning rules (parsed from JSON env var).
    # Falls back to default if not set or invalid JSON.
    env_pinning_rules = _parse_pinning_rules(os.getenv("MULTI_CATEGORY_PINNING_RULES"))
    multi_category_pinning_rules = (
        env_pinning_rules
        if env_pinning_rules
        else {
            "education_and_formal_background": ["education-facts"],
        }
    )

    # Multi-category section weights (parsed from JSON env var).
    # Empty by default - no section boosting unless explicitly configured.
    multi_category_section_weights = _parse_section_weights(
        os.getenv("MULTI_CATEGORY_SECTION_WEIGHTS")
    )

    # Multi-category quality rules (parsed from JSON env var).
    # Empty by default - no quality validation unless explicitly configured.
    multi_category_quality_rules = _parse_quality_rules(
        os.getenv("MULTI_CATEGORY_QUALITY_RULES")
    )

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
        multi_category_rollout_percent=multi_category_rollout_percent,
        multi_category_max_categories=multi_category_max_categories,
        multi_category_max_total_chunks=multi_category_max_total_chunks,
        multi_category_allow_six_chunks=multi_category_allow_six_chunks,
        multi_category_budget_policy=multi_category_budget_policy,
        multi_category_pinning_rules=multi_category_pinning_rules,
        multi_category_section_weights=multi_category_section_weights,
        multi_category_quality_rules=multi_category_quality_rules,
        ip_hash_salt=ip_hash_salt,
        trusted_proxy_cidrs=trusted_proxy_cidrs,
        interaction_log_include_llm_context=interaction_log_include_llm_context,
        cookie_secure=web.cookie_secure,
        cors_allow_origins=web.cors_allow_origins,
        geoip_enabled=geoip_enabled,
        geoip_provider=geoip_provider,
        geoip_url=geoip_url,
    )
