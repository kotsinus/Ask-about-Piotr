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
# Quality validation for synthesized answers.
#
# Notes:
# In v1, quality rules are LOG-ONLY (no retry trigger).
# This allows monitoring false positives before enabling enforcement.

"""Quality validation for synthesized answers."""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class QualityValidationResult:
    """Result of quality validation.

    Attributes:
        passed: Whether the answer passed all quality checks
        failure_reasons: List of reasons why the answer failed (empty if passed)
        routing_category: The routing category that was validated
    """

    passed: bool
    failure_reasons: list[str]
    routing_category: str


def validate_answer_quality(
    *,
    answer: str,
    routing_category: str,
    quality_rules: dict[str, dict[str, list[str] | int]],
) -> QualityValidationResult:
    """Validate answer against routing category-specific quality rules.

    IMPORTANT: This function only checks, never modifies.
    Retry logic is handled separately in main.py.

    Supported rules:
    - min_tokens: list of required tokens
    - min_token_count: minimum number of tokens that must be present (default 1)

    Args:
        answer: The synthesized answer to validate
        routing_category: The routing category to validate against
        quality_rules: Dict mapping routing category names to quality rule configs

    Returns:
        QualityValidationResult with pass/fail status and reasons.
    """
    failures: list[str] = []
    rules = quality_rules.get(routing_category, {})

    if not rules:
        return QualityValidationResult(
            passed=True,
            failure_reasons=[],
            routing_category=routing_category,
        )

    # Check min_tokens rule
    required_tokens = rules.get("min_tokens", [])
    min_count = rules.get("min_token_count", 1)

    if required_tokens:
        answer_lower = answer.lower()
        found = sum(1 for token in required_tokens if token.lower() in answer_lower)
        if found < min_count:
            failures.append(
                f"missing_routing_category_tokens: found {found}/{min_count} required tokens"
            )

    return QualityValidationResult(
        passed=len(failures) == 0,
        failure_reasons=failures,
        routing_category=routing_category,
    )
