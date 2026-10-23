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

import hashlib
import logging
from collections.abc import Callable

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector
from pydantic import BaseModel

from app.config import get_settings
from app.embeddings import get_embedding_provider

logger = logging.getLogger(__name__)


class RetrievedChunk(BaseModel):
    card_id: str
    card_category: str
    section: str
    source_url: str | None = None
    content: str
    distance: float | None = None

    # Internal-only metadata used by multi-category retrieval.
    origin_routing_categories: list[str] | None = None
    origin_routing_category: str | None = None
    pinned: bool = False


def _question_mentions_problem(question: str) -> bool:
    """Heuristic: does the user explicitly ask about the problem/challenge?

    Used to avoid penalizing the `Problem` section when it is likely the most
    relevant evidence.
    """

    q = " ".join((question or "").strip().lower().split())
    if not q:
        return False
    triggers = (
        "problem",
        "challenge",
        "pain",
        "issue",
        "bottleneck",
        "constraint",
        "trade-off",
        "tradeoff",
        "solve",
        "solved",
        "fix",
        "fixed",
    )
    return any(t in q for t in triggers)


def _norm_section(section: str) -> str:
    return " ".join((section or "").strip().lower().split())


def _norm_content_for_hash(content: str) -> str:
    return " ".join((content or "").strip().split())


def _dedup_key(chunk: RetrievedChunk) -> tuple[str, str, str]:
    normalized = _norm_content_for_hash(chunk.content)
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return (chunk.card_id, _norm_section(chunk.section), digest)


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
                SELECT card_id, card_category, section, source_url, content,
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
                # Privacy: do not log raw user input (may contain PII).
                "question_len": len(question or ""),
                "question_hash": hashlib.sha256(
                    (question or "").encode("utf-8")
                ).hexdigest()[:8],
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
        # Deduplicate by value, not object identity.
        #
        # Rows are tuples (from cursor.fetchall()) and therefore hashable.
        # Using id(row) is fragile and can lead to surprising edge-cases.
        selected_set = set(selected)
        for row in rows_ranked:
            if row in selected_set:
                continue
            selected.append(row)
            selected_set.add(row)
            if len(selected) >= limit:
                break

    filtered = selected[:limit]
    return [
        RetrievedChunk(
            card_id=row[0],
            card_category=row[1],
            section=row[2],
            source_url=row[3],
            content=row[4],
            distance=float(row[5]),
        )
        for row in filtered
    ]


def retrieve_for_category(
    question: str,
    *,
    routing_category: str,
    budget: int,
    conversation_topic: str | None = None,
    section_weights: dict[str, float] | None = None,
    card_conditioning: dict[str, list[str] | float] | None = None,
) -> list[RetrievedChunk]:
    """Retrieve up to `budget` chunks for a specific routed category.

    Notes:
    - Uses a fixed oversample factor for the DB candidate limit.
    - Applies the standard per-card cap semantics within this category run.
    - Section weights are POSITIVE values that BOOST section ranking (subtract from distance).
    - Card conditioning provides SOFT boosting based on card_category (content taxonomy).
    - The `routing_category` parameter is a ROUTER category (intent taxonomy), NOT a card category
      (content taxonomy). Retrieval is semantic-first and does NOT filter by card category.
      See docs/ARCHITECTURE.md for the distinction between these two taxonomies.
    """

    budget = max(1, int(budget))
    settings = get_settings()

    oversample_factor = 7

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
    embedding_vector = [float(value) for value in embedding]
    embedding_param = Vector(embedding_vector)

    # Oversample strongly to preserve recall; category selection will trim to budget.
    candidate_limit = max(budget * oversample_factor * 8, 30)

    # NOTE: We do NOT filter by card category here. The `routing_category` parameter is a router
    # category (intent taxonomy like "Hands-on engineering"), while the database
    # `card_category` column contains card categories (content taxonomy like "project",
    # "research", "experience"). These are intentionally different taxonomies.
    # Retrieval is semantic-first; router categories influence synthesis style,
    # not evidence filtering.
    with psycopg.connect(settings.database_url) as conn:
        register_vector(conn)
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT card_id, card_category, section, source_url, content,
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
        fallback_n = min(budget, 3)
        logger.warning(
            "retrieval_cutoff_filtered_to_zero_fallback",
            extra={
                "question_len": len(question or ""),
                "question_hash": hashlib.sha256(
                    (question or "").encode("utf-8")
                ).hexdigest()[:8],
                "candidate_count": len(candidate_rows),
                "best_distance": best_distance,
                "retrieval_max_distance": max_distance,
                "retrieval_distance_delta": delta,
                "fallback_n": fallback_n,
            },
        )
        rows = candidate_rows[:fallback_n]

    low_signal_sections = {
        "title",
        "category",
        "tech stack",
    }

    penalize_problem_section = False
    if not _question_mentions_problem(question):
        # If the caller provides weights that explicitly boost "What I built",
        # prefer those factual/detail sections over generic template-y "Problem".
        # This keeps behavior generic and avoids hardcoding routing categories.
        if section_weights:
            if any(_norm_section(k) == "what i built" for k in section_weights.keys()):
                penalize_problem_section = True

    # Maximum bonus cap to prevent weak chunks from jumping strong ones
    MAX_SECTION_BONUS = 0.25
    MAX_CARD_CATEGORY_BONUS = 0.25

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

    section_penalty = {
        "title": 0.25,
        "category": 0.30,
        "tech stack": 0.20,
    }

    long_section_len = 220
    short_section_len = 120
    short_substantive_penalty = 0.18

    # Parse card conditioning config
    card_category_boost: set[str] = set()
    card_category_weight: float = 0.0
    if card_conditioning:
        boost_list = card_conditioning.get("boost")
        if isinstance(boost_list, list):
            card_category_boost = {str(b).strip().lower() for b in boost_list if b}
        weight_val = card_conditioning.get("weight")
        if isinstance(weight_val, (int, float)):
            card_category_weight = min(
                max(0.0, float(weight_val)), MAX_CARD_CATEGORY_BONUS
            )

    def _adjusted_distance(row: tuple) -> tuple[float, float]:
        """
        Returns (adjusted_distance, raw_distance).

        Formula: adjusted = distance + penalty - bonus

        Where:
        - penalty >= 0 (for low-signal sections)
        - bonus >= 0 (for category-specific section weights and card category boosting)
        - bonus is capped at MAX_SECTION_BONUS + MAX_CARD_CATEGORY_BONUS
        """
        distance = float(row[5])
        card_id = row[0]
        section = _norm_section(row[2])
        card_cat = (row[1] or "").strip().lower()

        # Calculate penalty (only when card has substantive alternatives)
        penalty = 0.0
        if card_has_substantive.get(card_id, False):
            penalty = section_penalty.get(section, 0.0)

            if penalize_problem_section and section == "problem":
                penalty += 0.12

            if section not in low_signal_sections:
                if (
                    card_max_substantive_len.get(card_id, 0) >= long_section_len
                    and len(row[4] or "") < short_section_len
                ):
                    penalty += short_substantive_penalty

        # Calculate bonus (only when weights provided)
        bonus = 0.0
        if section_weights:
            # Normalize section weight keys for lookup (keys may be in original case)
            normalized_weights = {
                _norm_section(k): v for k, v in section_weights.items()
            }
            raw_weight = normalized_weights.get(section, 0.0)
            # Cap bonus to prevent weak chunks from jumping strong ones
            bonus += min(max(0.0, raw_weight), MAX_SECTION_BONUS)

        # Apply card category boosting (soft boost based on content taxonomy)
        if card_category_boost and card_cat in card_category_boost:
            bonus += card_category_weight

        adjusted = distance + penalty - bonus
        return (adjusted, distance)

    rows_ranked = sorted(rows, key=_adjusted_distance)

    per_card_cap = getattr(settings, "retrieval_per_card_cap", 2)
    selected: list[tuple] = []
    per_card_counts: dict[str, int] = {}
    deferred_low_signal: list[tuple] = []

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
        if len(selected) >= budget:
            break

    if len(selected) < budget and deferred_low_signal:
        for row in deferred_low_signal:
            card_id = row[0]
            if per_card_counts.get(card_id, 0) >= per_card_cap:
                continue
            selected.append(row)
            per_card_counts[card_id] = per_card_counts.get(card_id, 0) + 1
            if len(selected) >= budget:
                break

    if len(selected) < budget:
        selected_set = set(selected)
        for row in rows_ranked:
            if row in selected_set:
                continue
            selected.append(row)
            selected_set.add(row)
            if len(selected) >= budget:
                break

    filtered = selected[:budget]
    return [
        RetrievedChunk(
            card_id=row[0],
            card_category=row[1],
            section=row[2],
            source_url=row[3],
            content=row[4],
            distance=float(row[5]),
            origin_routing_categories=[str(routing_category).strip()],
            origin_routing_category=str(routing_category).strip(),
            pinned=False,
        )
        for row in filtered
    ]


def retrieve_for_card(
    question: str,
    *,
    card_id: str,
    limit: int,
    origin_routing_category: str,
    conversation_topic: str | None = None,
    section_weights: dict[str, float] | None = None,
) -> list[RetrievedChunk]:
    """Targeted retrieval constrained to a single knowledge card.

    Notes:
    - Applies the same section penalty/bonus logic as retrieve_for_category().
    - Section weights are POSITIVE values that BOOST section ranking (subtract from distance).
    - This ensures pinned cards select the most relevant section, not just the
      lowest-distance section which may be low-signal (e.g., "Category").
    """

    limit = max(1, int(limit))
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
    embedding_vector = [float(value) for value in embedding]
    embedding_param = Vector(embedding_vector)

    candidate_limit = max(limit * 20, 30)

    with psycopg.connect(settings.database_url) as conn:
        register_vector(conn)
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT card_id, card_category, section, source_url, content,
                       embedding <=> %s AS distance
                FROM knowledge_chunks
                WHERE section <> 'Links' AND card_id = %s
                ORDER BY distance
                LIMIT %s;
                """,
                (embedding_param, card_id, candidate_limit),
            )
            rows = cursor.fetchall()

    if not rows:
        return []

    # Apply the same section penalty/bonus logic as retrieve_for_category.
    low_signal_sections = {
        "title",
        "category",
        "tech stack",
    }

    penalize_problem_section = False
    if not _question_mentions_problem(question):
        if section_weights:
            if any(_norm_section(k) == "what i built" for k in section_weights.keys()):
                penalize_problem_section = True

    # Maximum bonus cap to prevent weak chunks from jumping strong ones
    MAX_SECTION_BONUS = 0.25

    card_has_substantive: dict[str, bool] = {}
    card_max_substantive_len: dict[str, int] = {}
    for row in rows:
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

    section_penalty = {
        "title": 0.25,
        "category": 0.30,
        "tech stack": 0.20,
    }

    long_section_len = 220
    short_section_len = 120
    short_substantive_penalty = 0.18

    def _adjusted_distance(row: tuple) -> tuple[float, float]:
        """
        Returns (adjusted_distance, raw_distance).

        Formula: adjusted = distance + penalty - bonus

        Where:
        - penalty >= 0 (for low-signal sections)
        - bonus >= 0 (for category-specific section weights)
        - bonus is capped at MAX_SECTION_BONUS
        """
        distance = float(row[5])
        section = _norm_section(row[2])

        # Calculate penalty (only when card has substantive alternatives)
        penalty = 0.0
        if card_has_substantive.get(card_id, False):
            penalty = section_penalty.get(section, 0.0)

            if penalize_problem_section and section == "problem":
                penalty += 0.12

            if section not in low_signal_sections:
                if (
                    card_max_substantive_len.get(card_id, 0) >= long_section_len
                    and len(row[4] or "") < short_section_len
                ):
                    penalty += short_substantive_penalty

        # Calculate bonus (only when weights provided)
        bonus = 0.0
        if section_weights:
            # Normalize section weight keys for lookup (keys may be in original case)
            normalized_weights = {
                _norm_section(k): v for k, v in section_weights.items()
            }
            raw_weight = normalized_weights.get(section, 0.0)
            # Cap bonus to prevent weak chunks from jumping strong ones
            bonus = min(max(0.0, raw_weight), MAX_SECTION_BONUS)

        adjusted = distance + penalty - bonus
        return (adjusted, distance)

    rows_ranked = sorted(rows, key=_adjusted_distance)
    filtered = rows_ranked[:limit]
    return [
        RetrievedChunk(
            card_id=row[0],
            card_category=row[1],
            section=row[2],
            source_url=row[3],
            content=row[4],
            distance=float(row[5]),
            origin_routing_categories=[str(origin_routing_category).strip()],
            origin_routing_category=str(origin_routing_category).strip(),
            pinned=True,
        )
        for row in filtered
    ]


def apply_pinning(
    chunks: list[RetrievedChunk],
    pinning_rules: dict[str, list[str]],
    routed_categories: list[str],
    retrieve_for_card_fn: Callable[[str, int, str], list[RetrievedChunk]],
    max_total_chunks: int = 5,
) -> tuple[list[RetrievedChunk], list[str]]:
    """Apply pinning rules to ensure required cards are included.

    Args:
        chunks: Current merged/deduped chunks from retrieval
        pinning_rules: Dict mapping category names to lists of card IDs to pin
        routed_categories: Categories returned by the router
        retrieve_for_card_fn: Function to retrieve chunks for a specific card (card_id, limit)
        max_total_chunks: Maximum chunks allowed in result

    Returns:
        Tuple of (updated chunks list, list of pinned card IDs)
    """
    pinned_card_ids: list[str] = []

    if not pinning_rules or not routed_categories:
        return chunks, pinned_card_ids

    # Track which card IDs are already present in results
    existing_card_ids: set[str] = {chunk.card_id for chunk in chunks}

    # Process each routed category
    for routing_category in routed_categories:
        routing_category = str(routing_category).strip()
        if not routing_category:
            continue

        # Check if pinning rules exist for this category
        cards_to_pin = pinning_rules.get(routing_category, [])
        if not cards_to_pin:
            continue

        # Process each card ID in the pinning rules for this category
        for card_id in cards_to_pin:
            card_id = str(card_id).strip()
            if not card_id:
                continue

            # Check if any chunk from this card is already in results
            if card_id in existing_card_ids:
                logger.debug(
                    "pinning_chunk_already_present",
                    extra={
                        "card_id": card_id,
                        "routing_category": routing_category,
                    },
                )
                continue

            # Retrieve the best chunk for this card.
            # IMPORTANT: pass the routing category we are pinning FOR so provenance
            # is correct (coverage capping + diagnostics depend on it).
            retrieved_chunks = retrieve_for_card_fn(card_id, 1, routing_category)

            if not retrieved_chunks:
                logger.warning(
                    "pinning_retrieval_empty",
                    extra={
                        "card_id": card_id,
                        "routing_category": routing_category,
                    },
                )
                continue

            # Mark the chunk as pinned and add to results
            pinned_chunk = retrieved_chunks[0]
            pinned_chunk.pinned = True

            # Set origin categories if not already set
            if not pinned_chunk.origin_routing_categories:
                pinned_chunk.origin_routing_categories = [routing_category]
            elif routing_category not in pinned_chunk.origin_routing_categories:
                pinned_chunk.origin_routing_categories.append(routing_category)

            if not pinned_chunk.origin_routing_category:
                pinned_chunk.origin_routing_category = routing_category
            else:
                # Ensure best-origin category matches the category that caused the pin.
                # This avoids misattribution to the primary routed category.
                pinned_chunk.origin_routing_category = routing_category

            chunks.append(pinned_chunk)
            existing_card_ids.add(card_id)
            pinned_card_ids.append(card_id)

            logger.info(
                "pinning_applied",
                extra={
                    "card_id": card_id,
                    "routing_category": routing_category,
                    "total_chunks": len(chunks),
                    "max_total_chunks": max_total_chunks,
                },
            )

    return chunks, pinned_card_ids


def merge_dedup_preserve_provenance(
    chunks_by_category: dict[str, list[RetrievedChunk]],
) -> tuple[list[RetrievedChunk], int]:
    """Merge per-category results and deduplicate while preserving provenance."""

    merged: list[RetrievedChunk] = []
    for routing_category, chunks in chunks_by_category.items():
        for chunk in chunks:
            if not chunk.origin_routing_categories:
                chunk.origin_routing_categories = [routing_category]
            else:
                if routing_category not in chunk.origin_routing_categories:
                    chunk.origin_routing_categories.append(routing_category)
            chunk.origin_routing_category = (
                chunk.origin_routing_category or routing_category
            )
            merged.append(chunk)

    collisions = 0
    best_by_key: dict[tuple[str, str, str], RetrievedChunk] = {}
    for chunk in merged:
        key = _dedup_key(chunk)
        existing = best_by_key.get(key)
        if existing is None:
            best_by_key[key] = chunk
            continue
        collisions += 1
        existing_distance = existing.distance if existing.distance is not None else 1e9
        chunk_distance = chunk.distance if chunk.distance is not None else 1e9
        if chunk_distance < existing_distance:
            winner, loser = chunk, existing
            best_by_key[key] = winner
        else:
            winner, loser = existing, chunk

        # Merge provenance.
        merged_origins = set(winner.origin_routing_categories or [])
        merged_origins.update(loser.origin_routing_categories or [])
        winner.origin_routing_categories = sorted(merged_origins)

        # Keep best_origin_category consistent with the best (lowest distance).
        winner.origin_routing_category = winner.origin_routing_category or str(
            winner.origin_routing_categories[0]
        )
        winner.pinned = bool(winner.pinned or loser.pinned)

    # Stable order: by distance, then by card/section.
    deduped = list(best_by_key.values())
    deduped.sort(
        key=lambda c: (
            float(c.distance) if c.distance is not None else 1e9,
            c.card_id,
            _norm_section(c.section),
        )
    )
    return deduped, collisions


def cap_chunks_with_coverage(
    *,
    chunks: list[RetrievedChunk],
    routed_categories: list[str],
    max_total_chunks: int,
) -> list[RetrievedChunk]:
    """Cap evidence to `max_total_chunks` while preserving category coverage.

    Eviction rules:
    - Never evict pinned chunks.
    - Never evict the only chunk that covers a routed category (when that category
      has at least one chunk available in `chunks`).
    - Prefer evicting from over-represented categories (by origin_routing_category).
    """

    max_total_chunks = max(1, int(max_total_chunks))
    if len(chunks) <= max_total_chunks:
        return chunks

    routed_set = {str(c).strip() for c in routed_categories if str(c).strip()}

    # Only require coverage for categories that are present in the current set.
    present_categories: set[str] = set()
    for chunk in chunks:
        for origin in chunk.origin_routing_categories or (
            [] if not chunk.origin_routing_category else [chunk.origin_routing_category]
        ):
            if origin in routed_set:
                present_categories.add(origin)

    def _coverage_counts(items: list[RetrievedChunk]) -> dict[str, int]:
        counts = {c: 0 for c in present_categories}
        for ch in items:
            origins = set(ch.origin_routing_categories or [])
            if ch.origin_routing_category:
                origins.add(ch.origin_routing_category)
            for origin in origins:
                if origin in counts:
                    counts[origin] += 1
        return counts

    def _best_origin_counts(items: list[RetrievedChunk]) -> dict[str, int]:
        counts = {c: 0 for c in present_categories}
        for ch in items:
            origin = ch.origin_routing_category
            if origin in counts:
                counts[origin] += 1
        return counts

    working = list(chunks)
    while len(working) > max_total_chunks:
        coverage = _coverage_counts(working)
        best_counts = _best_origin_counts(working)

        candidates: list[RetrievedChunk] = []
        for ch in working:
            if ch.pinned:
                continue
            # Can we remove this without breaking required coverage?
            removable = True
            origins = set(ch.origin_routing_categories or [])
            if ch.origin_routing_category:
                origins.add(ch.origin_routing_category)
            for origin in origins:
                if origin in coverage and coverage[origin] <= 1:
                    removable = False
                    break
            if removable:
                candidates.append(ch)

        if not candidates:
            # As a last resort, allow evicting non-pinned even if it breaks coverage.
            candidates = [ch for ch in working if not ch.pinned]
        if not candidates:
            break

        def _evict_key(ch: RetrievedChunk) -> tuple[int, float, str, str]:
            # Evict from over-represented categories first.
            origin = ch.origin_routing_category or ""
            overrep = best_counts.get(origin, 0)
            distance = float(ch.distance) if ch.distance is not None else 1e9
            return (-overrep, -distance, ch.card_id, _norm_section(ch.section))

        victim = sorted(candidates, key=_evict_key, reverse=False)[0]
        working.remove(victim)

    return working[:max_total_chunks]
