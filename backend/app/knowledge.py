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
# Loads knowledge cards from Markdown and chunks them into section-level units.
#
# Notes:
# Enforces the required card schema and preserves strict metadata for citations.

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from app.card_category import ALLOWED_CARD_CATEGORIES, CardCategory

REQUIRED_SECTIONS = [
    "Title",
    "Category",
    "Problem",
    "My role",
    "What I built",
    "Scale and impact",
    "Tech stack",
    "Key decisions and trade-offs",
    "Links",
]


@dataclass(frozen=True)
class KnowledgeCard:
    card_id: str
    title: str
    card_category: CardCategory
    sections: dict[str, str]
    source_url: str | None


@dataclass(frozen=True)
class KnowledgeChunk:
    card_id: str
    card_category: CardCategory
    section: str
    source_url: str | None
    content: str


def load_cards(knowledge_dir: Path) -> list[KnowledgeCard]:
    """Load knowledge cards from a directory.

    Only Markdown files are processed. README.md is ignored.
    """

    if not knowledge_dir.exists():
        raise FileNotFoundError(f"Knowledge directory not found: {knowledge_dir}")

    cards: list[KnowledgeCard] = []
    for path in _iter_card_files(knowledge_dir):
        cards.append(_parse_card(path))
    return cards


def _iter_card_files(knowledge_dir: Path) -> list[Path]:
    cards_dir = knowledge_dir / "cards"
    if not cards_dir.exists():
        raise FileNotFoundError(f"Cards directory not found: {cards_dir}")

    candidates = list(cards_dir.glob("*.md"))

    return [path for path in sorted(candidates) if path.name.lower() != "readme.md"]


def chunk_cards(cards: Iterable[KnowledgeCard]) -> list[KnowledgeChunk]:
    """Convert cards into section-level chunks with required metadata."""

    chunks: list[KnowledgeChunk] = []
    for card in cards:
        for section in REQUIRED_SECTIONS:
            content = card.sections.get(section, "").strip()
            if not content:
                continue
            chunks.append(
                KnowledgeChunk(
                    card_id=card.card_id,
                    card_category=card.card_category,
                    section=section,
                    source_url=card.source_url,
                    content=content,
                )
            )
    return chunks


def _parse_card(path: Path) -> KnowledgeCard:
    text = path.read_text(encoding="utf-8").strip()
    sections = _split_sections(text, path.name)

    missing = [section for section in REQUIRED_SECTIONS if section not in sections]
    if missing:
        raise ValueError(f"Missing sections in {path.name}: {', '.join(missing)}")

    title = sections["Title"].strip()
    category_raw = sections["Category"].strip()
    if category_raw not in ALLOWED_CARD_CATEGORIES:
        allowed = ", ".join(sorted(ALLOWED_CARD_CATEGORIES))
        raise ValueError(
            "Invalid card category "
            f"{category_raw!r} in {path.as_posix()} (card_id={path.stem}). "
            f"Allowed categories: {allowed}."
        )

    card_category = CardCategory(category_raw)
    source_url = _extract_source_url(sections.get("Links", ""))

    return KnowledgeCard(
        card_id=path.stem,
        title=title,
        card_category=card_category,
        sections=sections,
        source_url=source_url,
    )


def _split_sections(text: str, filename: str) -> dict[str, str]:
    sections: dict[str, str] = {}
    current_heading: str | None = None
    buffer: list[str] = []

    for line in text.splitlines():
        heading = _parse_heading(line)
        if heading is not None:
            if current_heading is not None:
                sections[current_heading] = "\n".join(buffer).strip()
            current_heading = heading
            buffer = []
            continue
        if current_heading is None and line.strip():
            raise ValueError(
                f"Content before first heading in {filename}. "
                "Cards must start with a top-level heading."
            )
        buffer.append(line)

    if current_heading is not None:
        sections[current_heading] = "\n".join(buffer).strip()

    return sections


def _parse_heading(line: str) -> str | None:
    stripped = line.strip()
    match = re.match(r"^(#{1,2})\s+(.+)$", stripped)
    if match:
        heading_raw = match.group(2).strip()
        # Allow headings like "Problem:" / "Category:".
        heading = heading_raw.rstrip(":").strip()

        # Special-case required sections that may appear with extra punctuation.
        if heading.lower().startswith("category"):
            return "Category"
        if heading.lower().startswith("links"):
            return "Links"
        return heading
    return None


def _extract_source_url(links_section: str) -> str | None:
    for line in links_section.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        if candidate.startswith("-"):
            candidate = candidate[1:].strip()
            if not candidate:
                continue
        return candidate
    return None
