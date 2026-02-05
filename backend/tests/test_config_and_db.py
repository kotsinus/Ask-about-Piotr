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

from app.config import get_settings
from app.db import _to_sqlalchemy_url


def test_get_settings_requires_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL is required"):
        get_settings()


def test_get_settings_parses_prompt_cache_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")

    monkeypatch.setenv("PROMPT_CACHE_ENABLED", "yes")
    assert get_settings().prompt_cache_enabled is True

    monkeypatch.setenv("PROMPT_CACHE_ENABLED", "true")
    assert get_settings().prompt_cache_enabled is True

    # Note: get_settings uses a minimal allowlist; "on" is intentionally False.
    monkeypatch.setenv("PROMPT_CACHE_ENABLED", "on")
    assert get_settings().prompt_cache_enabled is False


def test_get_settings_parses_csv_and_geoip_bool(monkeypatch: pytest.MonkeyPatch) -> None:
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

