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
# Regression tests: when section weights explicitly boost "What I built",
# retrieval should avoid selecting generic "Problem" sections unless the user
# explicitly asks about the problem/challenge.

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import retrieval


class _Cursor:
    def __init__(self, rows: list[tuple]):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, *args, **kwargs):
        return None

    def fetchall(self):
        return self._rows


class _Conn:
    def __init__(self, rows: list[tuple]):
        self._rows = rows

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return _Cursor(self._rows)


def _settings(**overrides):
    base = SimpleNamespace(
        database_url="postgresql://test:test@localhost:5432/test",
        embeddings_provider="stub",
        embeddings_dimensions=3,
        retrieval_max_distance=None,
        retrieval_distance_delta=None,
        retrieval_per_card_cap=2,
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _stub_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Provider:
        def embed(self, texts: list[str]):
            return [[0.0, 0.0, 0.0] for _ in texts]

    monkeypatch.setattr(retrieval, "get_embedding_provider", lambda **k: _Provider())


def test_penalize_problem_when_boosting_what_i_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(retrieval, "get_settings", lambda: _settings())
    monkeypatch.setattr(retrieval, "register_vector", lambda conn: None)
    _stub_embeddings(monkeypatch)

    # Same card; Problem has lower raw distance, but we want What I built to win
    # when weights boost What I built and question does not ask about "problem".
    rows = [
        ("education-facts", "education", "Problem", None, "Generic template", 0.10),
        (
            "education-facts",
            "education",
            "What I built",
            None,
            "PhD / M.Sc / xMBA list",
            0.20,
        ),
    ]
    monkeypatch.setattr(retrieval.psycopg, "connect", lambda *a, **k: _Conn(rows))

    chunks = retrieval.retrieve_for_category(
        "What is your educational background?",
        routing_category="education_and_formal_background",
        budget=1,
        section_weights={"What I built": 0.20},
    )
    assert chunks[0].section == "What I built"


def test_do_not_penalize_problem_when_question_mentions_problem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(retrieval, "get_settings", lambda: _settings())
    monkeypatch.setattr(retrieval, "register_vector", lambda conn: None)
    _stub_embeddings(monkeypatch)

    rows = [
        ("card", "x", "Problem", None, "This is the problem.", 0.10),
        ("card", "x", "What I built", None, "This is what I built.", 0.20),
    ]
    monkeypatch.setattr(retrieval.psycopg, "connect", lambda *a, **k: _Conn(rows))

    chunks = retrieval.retrieve_for_category(
        "What was the main problem/challenge you solved?",
        routing_category="hands_on_engineering",
        budget=1,
        # Small boost: if the question is explicitly about the problem,
        # we should NOT apply the extra Problem penalty.
        # With no extra penalty, Problem (0.10) should still beat
        # What I built (0.20 - 0.05 = 0.15).
        section_weights={"What I built": 0.05},
    )
    assert chunks[0].section == "Problem"
