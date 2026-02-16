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
# Unit tests for configuration parsing and DB URL normalization.

from __future__ import annotations

import pytest

from app.config import _parse_bool, _parse_optional_float, get_settings
from app.db import _to_sqlalchemy_url


def test_get_settings_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        get_settings()


def test_get_settings_parses_prompt_cache_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")

    monkeypatch.setenv("PROMPT_CACHE_ENABLED", "yes")
    assert get_settings().prompt_cache_enabled is True

    monkeypatch.setenv("PROMPT_CACHE_ENABLED", "true")
    assert get_settings().prompt_cache_enabled is True

    # Note: get_settings uses a minimal allowlist; "on" is intentionally False.
    monkeypatch.setenv("PROMPT_CACHE_ENABLED", "on")
    assert get_settings().prompt_cache_enabled is False


def test_get_settings_parses_csv_and_geoip_bool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", " 203.0.113.0/24, ,198.51.100.0/24 ")
    monkeypatch.setenv("GEOIP_ENABLED", "yes")
    monkeypatch.setenv("GEOIP_PROVIDER", "  ipapi_co  ")

    settings = get_settings()
    assert settings.trusted_proxy_cidrs == ["203.0.113.0/24", "198.51.100.0/24"]
    assert settings.geoip_enabled is True
    assert settings.geoip_provider == "ipapi_co"


@pytest.mark.parametrize(
    "value, expected",
    [
        ("off", None),
        ("none", None),
        ("null", None),
        ("0.42", 0.42),
    ],
)
def test_get_settings_parses_optional_floats(
    monkeypatch: pytest.MonkeyPatch, value: str, expected: float | None
) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("RETRIEVAL_MAX_DISTANCE", value)
    settings = get_settings()
    assert settings.retrieval_max_distance == expected


def test_to_sqlalchemy_url_normalizes_psycopg_driver() -> None:
    assert (
        _to_sqlalchemy_url("postgresql://user:pass@localhost:5432/db")
        == "postgresql+psycopg://user:pass@localhost:5432/db"
    )
    assert (
        _to_sqlalchemy_url("postgresql+psycopg://user:pass@localhost:5432/db")
        == "postgresql+psycopg://user:pass@localhost:5432/db"
    )
    assert _to_sqlalchemy_url("sqlite:///file.db") == "sqlite:///file.db"


def test_config_parsers_cover_edge_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _parse_bool("maybe", default=True) is True
    assert _parse_optional_float(None) is None

    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("RETRIEVAL_PER_CARD_CAP", "not-an-int")
    assert get_settings().retrieval_per_card_cap == 2

    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("IP_HASH_SALT", "")
    with pytest.raises(RuntimeError, match="IP_HASH_SALT is required"):
        get_settings()


def test_parse_pinning_rules_valid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test _parse_pinning_rules with valid JSON."""
    from app.config import _parse_pinning_rules

    # Valid JSON with proper structure
    result = _parse_pinning_rules('{"education_and_formal_background": ["card1", "card2"]}')
    assert result == {"education_and_formal_background": ["card1", "card2"]}

    # Empty string returns empty dict
    assert _parse_pinning_rules("") == {}
    assert _parse_pinning_rules(None) == {}

    # Invalid JSON returns empty dict
    assert _parse_pinning_rules("not json") == {}

    # JSON with non-dict returns empty dict
    assert _parse_pinning_rules('["a", "b"]') == {}

    # JSON with non-string values filtered
    result = _parse_pinning_rules('{"valid": ["card"], "invalid": "not-a-list"}')
    assert result == {"valid": ["card"]}

    # JSON with non-list values filtered
    result = _parse_pinning_rules('{"valid": ["card"], "invalid": "not-a-list"}')
    assert result == {"valid": ["card"]}


def test_normalize_router_category_name() -> None:
    """Test _normalize_router_category_name function."""
    from app.config import _normalize_router_category_name

    assert _normalize_router_category_name("  test  ") == "test"
    assert _normalize_router_category_name(None) == ""
    assert _normalize_router_category_name("") == ""


def test_normalize_router_category_map() -> None:
    """Test _normalize_router_category_map function."""
    from app.config import _normalize_router_category_map

    result = _normalize_router_category_map({"  key  ": "value"})
    assert result == {"key": "value"}

    # Non-string keys are skipped
    result = _normalize_router_category_map({123: "value", "valid": "val"})
    assert result == {"valid": "val"}

    # None input
    assert _normalize_router_category_map(None) == {}


def test_parse_section_weights_valid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test _parse_section_weights with valid JSON."""
    from app.config import _parse_section_weights

    # Valid JSON with proper structure
    result = _parse_section_weights('{"education_and_formal_background": {"degrees": 0.15}}')
    assert result == {"education_and_formal_background": {"degrees": 0.15}}

    # Weight clamped to max 0.5
    result = _parse_section_weights('{"cat": {"section": 0.8}}')
    assert result == {"cat": {"section": 0.5}}

    # Weight clamped to min 0.0
    result = _parse_section_weights('{"cat": {"section": -0.1}}')
    assert result == {"cat": {"section": 0.0}}

    # Empty string returns empty dict
    assert _parse_section_weights("") == {}
    assert _parse_section_weights(None) == {}

    # Invalid JSON returns empty dict
    assert _parse_section_weights("not json") == {}

    # JSON with non-dict returns empty dict
    assert _parse_section_weights('["a", "b"]') == {}

    # Invalid weight values are skipped
    result = _parse_section_weights('{"cat": {"valid": 0.1, "invalid": "not-a-float"}}')
    assert result == {"cat": {"valid": 0.1}}


def test_parse_quality_rules_valid_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test _parse_quality_rules with valid JSON."""
    from app.config import _parse_quality_rules

    # Valid JSON with proper structure
    result = _parse_quality_rules('{"education_and_formal_background": {"min_tokens": ["degree", "university"], "min_token_count": 2}}')
    assert result == {"education_and_formal_background": {"min_tokens": ["degree", "university"], "min_token_count": 2}}

    # Empty string returns empty dict
    assert _parse_quality_rules("") == {}
    assert _parse_quality_rules(None) == {}

    # Invalid JSON returns empty dict
    assert _parse_quality_rules("not json") == {}

    # JSON with non-dict returns empty dict
    assert _parse_quality_rules('["a", "b"]') == {}

    # min_token_count clamped to min 1
    result = _parse_quality_rules('{"cat": {"min_token_count": 0}}')
    assert result == {"cat": {"min_token_count": 1}}

    # min_token_count from float
    result = _parse_quality_rules('{"cat": {"min_token_count": 2.5}}')
    assert result == {"cat": {"min_token_count": 2}}


def test_get_settings_openai_timeout_and_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test OPENAI_TIMEOUT_S and OPENAI_MAX_RETRIES parsing."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")

    # Invalid timeout falls back to default
    monkeypatch.setenv("OPENAI_TIMEOUT_S", "not-a-float")
    settings = get_settings()
    assert settings.openai_timeout_s == 60.0

    # Invalid max retries falls back to default
    monkeypatch.setenv("OPENAI_TIMEOUT_S", "30")
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "not-an-int")
    settings = get_settings()
    assert settings.openai_max_retries == 2

    # Negative retries clamped to 0
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "-5")
    settings = get_settings()
    assert settings.openai_max_retries == 0


def test_get_settings_multi_category_parsing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test multi-category settings parsing with invalid values."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")

    # Invalid rollout percent falls back to 0
    monkeypatch.setenv("MULTI_CATEGORY_ROLLOUT_PERCENT", "not-an-int")
    settings = get_settings()
    assert settings.multi_category_rollout_percent == 0

    # Rollout percent clamped to 0-100
    monkeypatch.setenv("MULTI_CATEGORY_ROLLOUT_PERCENT", "150")
    settings = get_settings()
    assert settings.multi_category_rollout_percent == 100

    monkeypatch.setenv("MULTI_CATEGORY_ROLLOUT_PERCENT", "-10")
    settings = get_settings()
    assert settings.multi_category_rollout_percent == 0

    # Invalid max categories falls back to 2
    monkeypatch.setenv("MULTI_CATEGORY_MAX_CATEGORIES", "not-an-int")
    settings = get_settings()
    assert settings.multi_category_max_categories == 2

    # Max categories clamped to 1-3
    monkeypatch.setenv("MULTI_CATEGORY_MAX_CATEGORIES", "5")
    settings = get_settings()
    assert settings.multi_category_max_categories == 3

    monkeypatch.setenv("MULTI_CATEGORY_MAX_CATEGORIES", "0")
    settings = get_settings()
    assert settings.multi_category_max_categories == 1

    # Invalid max total chunks falls back to 5
    monkeypatch.setenv("MULTI_CATEGORY_MAX_TOTAL_CHUNKS", "not-an-int")
    settings = get_settings()
    assert settings.multi_category_max_total_chunks == 5

    # Max total chunks clamped to 1-10
    monkeypatch.setenv("MULTI_CATEGORY_MAX_TOTAL_CHUNKS", "15")
    settings = get_settings()
    assert settings.multi_category_max_total_chunks == 10

    monkeypatch.setenv("MULTI_CATEGORY_MAX_TOTAL_CHUNKS", "0")
    settings = get_settings()
    assert settings.multi_category_max_total_chunks == 1


def test_get_settings_production_embedding_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test production environment checks for embeddings."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("IP_HASH_SALT", "test-salt")

    # Stub provider not allowed in production
    monkeypatch.setenv("EMBEDDINGS_PROVIDER", "stub")
    with pytest.raises(RuntimeError, match="EMBEDDINGS_PROVIDER must be configured"):
        get_settings()

    # OpenAI provider requires API key
    monkeypatch.setenv("EMBEDDINGS_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY is required"):
        get_settings()

    # Valid OpenAI config
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    settings = get_settings()
    assert settings.embeddings_provider == "openai"


def test_get_settings_custom_pinning_rules(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test custom pinning rules override default."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("MULTI_CATEGORY_PINNING_RULES", '{"custom_category": ["custom-card"]}')

    settings = get_settings()
    assert settings.multi_category_pinning_rules == {"custom_category": ["custom-card"]}


def test_get_settings_empty_pinning_rules_uses_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that empty pinning rules JSON uses default."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("MULTI_CATEGORY_PINNING_RULES", '{}')

    settings = get_settings()
    # Empty env value falls back to default
    assert settings.multi_category_pinning_rules == {
        "education_and_formal_background": ["education-facts"],
    }
