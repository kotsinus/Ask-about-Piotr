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

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List


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
    category: str
    sections: Dict[str, str]
    source_url: str | None


@dataclass(frozen=True)
class KnowledgeChunk:
    card_id: str
    category: str
    section: str
    source_url: str | None
    content: str


def load_cards(knowledge_dir: Path) -> List[KnowledgeCard]:
    """Load knowledge cards from a directory.

    Only Markdown files are processed. README.md is ignored.
    """

    if not knowledge_dir.exists():
        raise FileNotFoundError(f"Knowledge directory not found: {knowledge_dir}")

    cards: List[KnowledgeCard] = []
    for path in sorted(knowledge_dir.glob("*.md")):
        if path.name.lower() == "readme.md":
            continue
        cards.append(_parse_card(path))
    return cards


def chunk_cards(cards: Iterable[KnowledgeCard]) -> List[KnowledgeChunk]:
    """Convert cards into section-level chunks with required metadata."""

    chunks: List[KnowledgeChunk] = []
    for card in cards:
        for section in REQUIRED_SECTIONS:
            content = card.sections.get(section, "").strip()
            if not content:
                continue
            chunks.append(
                KnowledgeChunk(
                    card_id=card.card_id,
                    category=card.category,
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
    category = sections["Category"].strip()
    source_url = _extract_source_url(sections.get("Links", ""))

    return KnowledgeCard(
        card_id=path.stem,
        title=title,
        category=category,
        sections=sections,
        source_url=source_url,
    )


def _split_sections(text: str, filename: str) -> Dict[str, str]:
    sections: Dict[str, str] = {}
    current_heading: str | None = None
    buffer: List[str] = []

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
    if stripped.startswith("# "):
        return stripped[2:].strip()
    return None


def _extract_source_url(links_section: str) -> str | None:
    for line in links_section.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        if candidate.startswith("-"):
            candidate = candidate[1:].strip()
        return candidate
    return None

