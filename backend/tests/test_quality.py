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
# Unit tests for quality validation module.

"""Unit tests for quality validation module."""

import pytest

from app.quality import QualityValidationResult, validate_answer_quality


class TestValidateAnswerQuality:
    """Tests for validate_answer_quality function."""

    def test_empty_rules_returns_pass(self):
        """Empty quality rules should always pass."""
        result = validate_answer_quality(
            answer="Any answer text",
            routing_category="education",
            quality_rules={},
        )
        assert result.passed is True
        assert result.failure_reasons == []
        assert result.routing_category == "education"

    def test_unknown_routing_category_returns_pass(self):
        """Unknown routing category (not in rules) should pass."""
        result = validate_answer_quality(
            answer="Some answer",
            routing_category="Unknown Category",
            quality_rules={
                "education": {
                    "min_tokens": ["degree", "university"],
                    "min_token_count": 1,
                }
            },
        )
        assert result.passed is True
        assert result.failure_reasons == []

    def test_min_tokens_pass_when_tokens_present(self):
        """Should pass when required tokens are present in answer."""
        result = validate_answer_quality(
            answer="I have a degree from Stanford University in Computer Science.",
            routing_category="education",
            quality_rules={
                "education": {
                    "min_tokens": ["degree", "university", "stanford"],
                    "min_token_count": 2,
                }
            },
        )
        assert result.passed is True
        assert result.failure_reasons == []

    def test_min_tokens_fail_when_tokens_missing(self):
        """Should fail when not enough required tokens are present."""
        result = validate_answer_quality(
            answer="I studied computer science.",
            routing_category="education",
            quality_rules={
                "education": {
                    "min_tokens": ["degree", "university", "diploma"],
                    "min_token_count": 2,
                }
            },
        )
        assert result.passed is False
        assert len(result.failure_reasons) == 1
        assert "missing_routing_category_tokens" in result.failure_reasons[0]

    def test_min_tokens_case_insensitive(self):
        """Token matching should be case-insensitive."""
        result = validate_answer_quality(
            answer="I have a DEGREE from UNIVERSITY.",
            routing_category="education",
            quality_rules={
                "education": {
                    "min_tokens": ["degree", "university"],
                    "min_token_count": 2,
                }
            },
        )
        assert result.passed is True

    def test_min_token_count_defaults_to_one(self):
        """If min_token_count not specified, should default to 1."""
        result = validate_answer_quality(
            answer="I have a degree in computer science.",
            routing_category="education",
            quality_rules={
                "education": {
                    "min_tokens": ["degree", "university"],
                }
            },
        )
        assert result.passed is True  # Has "degree", so passes with default count=1

    def test_min_tokens_zero_count_impossible(self):
        """min_token_count of 0 should still require 0 tokens found (passes)."""
        result = validate_answer_quality(
            answer="No relevant tokens here.",
            routing_category="education",
            quality_rules={
                "education": {
                    "min_tokens": ["degree", "university"],
                    "min_token_count": 0,
                }
            },
        )
        assert result.passed is True

    def test_empty_answer_with_rules(self):
        """Empty answer should fail if tokens required."""
        result = validate_answer_quality(
            answer="",
            routing_category="education",
            quality_rules={
                "education": {
                    "min_tokens": ["degree"],
                    "min_token_count": 1,
                }
            },
        )
        assert result.passed is False

    def test_multiple_routing_categories_in_rules(self):
        """Should validate only the specified routing category, not others."""
        quality_rules = {
            "education": {
                "min_tokens": ["degree"],
                "min_token_count": 1,
            },
            "Hands-on engineering": {
                "min_tokens": ["built", "designed", "implemented"],
                "min_token_count": 2,
            },
        }

        # Answer passes for Education (has "degree")
        result_edu = validate_answer_quality(
            answer="I have a degree in CS.",
            routing_category="education",
            quality_rules=quality_rules,
        )
        assert result_edu.passed is True

        # Same answer fails for Hands-on engineering (no action verbs)
        result_eng = validate_answer_quality(
            answer="I have a degree in CS.",
            routing_category="Hands-on engineering",
            quality_rules=quality_rules,
        )
        assert result_eng.passed is False


class TestQualityValidationResult:
    """Tests for QualityValidationResult dataclass."""

    def test_result_is_frozen(self):
        """Result should be immutable (frozen dataclass)."""
        result = QualityValidationResult(
            passed=True,
            failure_reasons=[],
            routing_category="Test",
        )
        with pytest.raises(AttributeError):
            result.passed = False

    def test_result_with_failures(self):
        """Result should store failure reasons correctly."""
        result = QualityValidationResult(
            passed=False,
            failure_reasons=[
                "missing_routing_category_tokens: found 0/2 required tokens"
            ],
            routing_category="education",
        )
        assert result.passed is False
        assert len(result.failure_reasons) == 1
        assert "missing_routing_category_tokens" in result.failure_reasons[0]
