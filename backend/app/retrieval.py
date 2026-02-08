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
# Executes similarity search over knowledge chunks using pgvector.
#
# Notes:
# Embeddings are required; the stub provider will raise until configured.

"""Retrieval over knowledge chunks using pgvector."""

from __future__ import annotations

import logging

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector
from pydantic import BaseModel

from app.config import get_settings
from app.embeddings import get_embedding_provider

logger = logging.getLogger(__name__)


class RetrievedChunk(BaseModel):
    card_id: str
    category: str
    section: str
    source_url: str | None = None
    content: str
    distance: float | None = None


def retrieve(
    question: str, limit: int = 25, conversation_topic: str | None = None
) -> list[RetrievedChunk]:
    """Retrieve relevant chunks for a question using pgvector."""

    settings = get_settings()
    retrieval_query = (
        f"{question}\n\nConversation topic: {conversation_topic}"
        if conversation_topic
        else question
    )
    provider = get_embedding_provider(
        name=settings.embeddings_provider,
        dimensions=settings.embeddings_dimensions,
    )
    embedding = provider.embed([retrieval_query])[0]
    # Prefer passing the vector as a native sequence so pgvector's psycopg adapter
    # can serialize it efficiently (instead of formatting a textual "[...]").
    embedding_vector = [float(value) for value in embedding]
    embedding_param = Vector(embedding_vector)

    # We may skip many highly-similar chunks from a single card to allow evidence
    # to come from multiple cards. Fetch a larger candidate set to keep recall.
    candidate_limit = max(limit * 8, 30)

    with psycopg.connect(settings.database_url) as conn:
        register_vector(conn)
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT card_id, category, section, source_url, content,
                       embedding <=> %s AS distance
                FROM knowledge_chunks
                WHERE section <> 'Links'
                ORDER BY distance
                LIMIT %s;
                """,
                (embedding_param, candidate_limit),
            )
            rows = cursor.fetchall()

    if not rows:
        return []

    candidate_rows = rows

    # Hard cutoffs: allow fewer than `limit` chunks when retrieval is weak.
    #
    # pgvector distance interpretation depends on the chosen operator; this code
    # assumes cosine distance (lower = more similar).
    best_distance = min(float(row[5]) for row in rows)
    max_distance = settings.retrieval_max_distance
    delta = settings.retrieval_distance_delta

    def _keep(row: tuple) -> bool:
        distance = float(row[5])
        if max_distance is not None and distance > max_distance:
            return False
        if delta is not None and distance > best_distance + delta:
            return False
        return True

    rows = [row for row in rows if _keep(row)]
    if not rows:
        # Safe fallback: some deployments override cutoffs too aggressively
        # (e.g., via env), causing the hard filtering to drop all candidates.
        # In that case, return a small number of top candidates (by distance)
        # rather than returning zero sources.
        fallback_n = min(limit, 3)
        logger.warning(
            "retrieval_cutoff_filtered_to_zero_fallback",
            extra={
                "question": question,
                "candidate_count": len(candidate_rows),
                "best_distance": best_distance,
                "retrieval_max_distance": max_distance,
                "retrieval_distance_delta": delta,
                "fallback_n": fallback_n,
            },
        )
        rows = candidate_rows[:fallback_n]

    # Generic post-processing to prefer substantive sections when the per-card cap
    # forces tradeoffs.
    #
    # Problem:
    # - Similarity search often ranks small header-like sections (e.g. "Title")
    #   very high.
    # - Under a strict per-card cap, those low-signal sections can crowd out
    #   evidence-bearing sections (e.g. "What I built").
    #
    # Constraints:
    # - Must be generic across cards/queries: no query token hardcoding.
    # - Still preserve multi-card behavior and similarity ordering as much as
    #   possible.
    low_signal_sections = {
        "title",
        "category",
        "tech stack",
    }

    def _norm_section(section: str) -> str:
        return " ".join(section.strip().lower().split())

    card_has_substantive: dict[str, bool] = {}
    card_max_substantive_len: dict[str, int] = {}
    for row in rows:
        card_id = row[0]
        section = _norm_section(row[2])
        content_len = len(row[4] or "")
        if card_id not in card_has_substantive:
            card_has_substantive[card_id] = section not in low_signal_sections
        else:
            card_has_substantive[card_id] = card_has_substantive[card_id] or (
                section not in low_signal_sections
            )

        if section not in low_signal_sections:
            card_max_substantive_len[card_id] = max(
                card_max_substantive_len.get(card_id, 0),
                content_len,
            )

    # Penalties are applied only when a card has at least one substantive section
    # in the candidate set.
    #
    # Note: pgvector distances are typically in a small range (often ~[0, 2] for
    # cosine distance). These penalties are intentionally modest: they only
    # break ties / close calls within the same card's candidate set.
    section_penalty = {
        "title": 0.25,
        "category": 0.30,
        "tech stack": 0.20,
    }

    # If a card has a clearly substantive (longer) section available, avoid using
    # very short boilerplate-y sections (e.g., one-liners like "My role") when
    # the per-card cap is tight.
    long_section_len = 220
    short_section_len = 120
    short_substantive_penalty = 0.18

    def _adjusted_distance(row: tuple) -> tuple[float, float]:
        distance = float(row[5])
        card_id = row[0]
        section = _norm_section(row[2])
        if not card_has_substantive.get(card_id, False):
            return (distance, distance)

        penalty = section_penalty.get(section, 0.0)
        if section not in low_signal_sections:
            if (
                card_max_substantive_len.get(card_id, 0) >= long_section_len
                and len(row[4] or "") < short_section_len
            ):
                penalty += short_substantive_penalty

        return (distance + penalty, distance)

    rows_ranked = sorted(rows, key=_adjusted_distance)

    # Diversify lightly across cards: keep similarity ordering, but avoid returning
    # too many chunks from a single card when other relevant cards are present.
    per_card_cap = getattr(settings, "retrieval_per_card_cap", 2)
    selected: list[tuple] = []
    per_card_counts: dict[str, int] = {}
    deferred_low_signal: list[tuple] = []

    # Pass 1 (capped): select substantive sections first.
    # If a card has any substantive section candidates, defer low-signal sections
    # (Title/Category/Tech stack) so they don't crowd out evidence-bearing
    # sections under the per-card cap.
    for row in rows_ranked:
        card_id = row[0]
        if per_card_counts.get(card_id, 0) >= per_card_cap:
            continue

        section_norm = _norm_section(row[2])
        if (
            card_has_substantive.get(card_id, False)
            and section_norm in low_signal_sections
        ):
            deferred_low_signal.append(row)
            continue

        selected.append(row)
        per_card_counts[card_id] = per_card_counts.get(card_id, 0) + 1
        if len(selected) >= limit:
            break

    # Pass 2 (capped): if we still have budget, allow deferred low-signal
    # sections. This keeps behavior reasonable when the candidate set contains
    # mostly low-signal sections for some cards.
    if len(selected) < limit and deferred_low_signal:
        for row in deferred_low_signal:
            card_id = row[0]
            if per_card_counts.get(card_id, 0) >= per_card_cap:
                continue
            selected.append(row)
            per_card_counts[card_id] = per_card_counts.get(card_id, 0) + 1
            if len(selected) >= limit:
                break

    # If diversification was too strict (e.g., only one card exists), fill the
    # remaining slots without the per-card cap.
    if len(selected) < limit:
        selected_set = {id(row) for row in selected}
        for row in rows_ranked:
            if id(row) in selected_set:
                continue
            selected.append(row)
            if len(selected) >= limit:
                break

    filtered = selected[:limit]
    return [
        RetrievedChunk(
            card_id=row[0],
            category=row[1],
            section=row[2],
            source_url=row[3],
            content=row[4],
            distance=float(row[5]),
        )
        for row in filtered
    ]
