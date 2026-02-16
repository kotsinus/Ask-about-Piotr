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
# Canonical content taxonomy for knowledge cards.

from __future__ import annotations

from enum import StrEnum


class CardCategory(StrEnum):
    """Allowed knowledge-card content categories (canonical, lowercase)."""

    project = "project"
    research = "research"
    certification = "certification"
    experience = "experience"
    profile = "profile"
    education = "education"


ALLOWED_CARD_CATEGORIES: frozenset[str] = frozenset(
    {str(item.value) for item in CardCategory}
)
