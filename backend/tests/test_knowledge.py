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
# Unit tests for knowledge card parsing and chunking.

from __future__ import annotations

from pathlib import Path

import pytest

from app.knowledge import (
    KnowledgeCard,
    REQUIRED_SECTIONS,
    chunk_cards,
    load_cards,
)


def _card_text(*, links_line: str = "- https://example.com/source") -> str:
    parts: list[str] = []
    for section in REQUIRED_SECTIONS:
        parts.append(f"# {section}")
        if section == "Title":
            parts.append("Some title")
        elif section == "Category":
            parts.append("project")
        elif section == "Links":
            parts.append(links_line)
        else:
            parts.append(f"{section} content")
        parts.append("")
    return "\n".join(parts).strip() + "\n"


def test_load_cards_reads_markdown_files_and_ignores_readme(tmp_path: Path) -> None:
    knowledge_dir = tmp_path / "knowledge"
    cards_dir = knowledge_dir / "cards"
    cards_dir.mkdir(parents=True)

    (cards_dir / "README.md").write_text(_card_text(), encoding="utf-8")
    (cards_dir / "b-card.md").write_text(_card_text(), encoding="utf-8")
    (cards_dir / "a-card.md").write_text(_card_text(), encoding="utf-8")

    cards = load_cards(knowledge_dir)
    assert [card.card_id for card in cards] == ["a-card", "b-card"]


def test_load_cards_raises_when_cards_dir_missing(tmp_path: Path) -> None:
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir(parents=True)

    with pytest.raises(FileNotFoundError, match="Cards directory not found"):
        load_cards(knowledge_dir)


def test_card_validation_requires_all_sections(tmp_path: Path) -> None:
    knowledge_dir = tmp_path / "knowledge"
    cards_dir = knowledge_dir / "cards"
    cards_dir.mkdir(parents=True)

    missing = [s for s in REQUIRED_SECTIONS if s != "Links"]
    text = "\n".join([f"# {s}\nX\n" for s in missing])
    (cards_dir / "bad.md").write_text(text, encoding="utf-8")

    with pytest.raises(ValueError, match=r"Missing sections.*Links"):
        load_cards(knowledge_dir)


def test_split_sections_rejects_content_before_first_heading(tmp_path: Path) -> None:
    knowledge_dir = tmp_path / "knowledge"
    cards_dir = knowledge_dir / "cards"
    cards_dir.mkdir(parents=True)

    (cards_dir / "bad.md").write_text(
        "This is not allowed\n\n# Title\nT\n", encoding="utf-8"
    )

    with pytest.raises(ValueError, match="Content before first heading"):
        load_cards(knowledge_dir)


@pytest.mark.parametrize(
    "links_line, expected",
    [
        ("- https://example.com/a", "https://example.com/a"),
        ("https://example.com/b", "https://example.com/b"),
        ("\n\n- https://example.com/c\n", "https://example.com/c"),
    ],
)
def test_load_cards_extracts_source_url_from_links_section(
    tmp_path: Path,
    links_line: str,
    expected: str,
) -> None:
    knowledge_dir = tmp_path / "knowledge"
    cards_dir = knowledge_dir / "cards"
    cards_dir.mkdir(parents=True)

    (cards_dir / "card.md").write_text(_card_text(links_line=links_line), encoding="utf-8")
    cards = load_cards(knowledge_dir)
    assert cards[0].source_url == expected


def test_chunk_cards_emits_only_non_empty_required_sections() -> None:
    card = KnowledgeCard(
        card_id="c1",
        title="T",
        category="project",
        sections={
            "Title": "T",
            "Category": "project",
            "Problem": "\n\n",  # should be treated as empty
            "What I built": "Built X",
            "Links": "- https://example.com",
        },
        source_url="https://example.com",
    )

    chunks = chunk_cards([card])
    assert {(c.section, c.content) for c in chunks} == {
        ("Title", "T"),
        ("Category", "project"),
        ("What I built", "Built X"),
        ("Links", "- https://example.com"),
    }
    assert all(chunk.card_id == "c1" for chunk in chunks)
    assert all(chunk.category == "project" for chunk in chunks)
    assert all(chunk.source_url == "https://example.com" for chunk in chunks)

