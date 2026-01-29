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


@dataclass(frozen=True)
class Settings:
    database_url: str
    embeddings_provider: str
    embeddings_model: str | None
    embeddings_dimensions: int


def get_settings() -> Settings:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is required.")

    embeddings_provider = os.getenv("EMBEDDINGS_PROVIDER", "stub")
    embeddings_model = os.getenv("EMBEDDINGS_MODEL")
    embeddings_dimensions = int(os.getenv("EMBEDDINGS_DIMENSIONS", "1536"))

    return Settings(
        database_url=database_url,
        embeddings_provider=embeddings_provider,
        embeddings_model=embeddings_model,
        embeddings_dimensions=embeddings_dimensions,
    )

