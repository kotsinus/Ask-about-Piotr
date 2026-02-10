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
from collections.abc import Iterable

import psycopg
from pgvector import Vector
from pgvector.psycopg import register_vector
from pydantic import BaseModel

from app.config import get_settings
from app.embeddings import get_embedding_provider
from app.schemas import Category

logger = logging.getLogger(__name__)


class RetrievedChunk(BaseModel):
    # Optional stable DB identifier (knowledge_chunks.id). Present when selected
    # from SQL retrieval. Used for dedup across category retrieval runs.
    chunk_id: int | None = None

    card_id: str
    category: str
    section: str
    source_url: str | None = None
    content: str
    distance: float | None = None

    # Internal-only provenance / ranking helpers.
    adjusted_distance: float | None = None
    origin_categories: list[str] | None = None
    best_origin_category: str | None = None
    pinned: bool = False

    # Optional ingestion-time chunk index (not currently stored in DB). This is
    # used only as a secondary dedup key when provided by callers/tests.
    chunk_index: int | None = None


def _norm_section(section: str) -> str:
    return " ".join((section or "").strip().lower().split())


def _norm_category(category: str | Category | None) -> str:
    if category is None:
        return ""
    if isinstance(category, Category):
        return str(category.value)
    return str(category)


def _is_education_category(category: str | Category | None) -> bool:
    return _norm_category(category).strip().lower() == Category.education_and_formal_background.value.lower()


def _normalize_content_for_hash(content: str) -> str:
    # Normalize whitespace so formatting-only differences do not break dedup.
    return " ".join((content or "").strip().split())


def _dedup_key(chunk: RetrievedChunk) -> tuple:
    if chunk.chunk_id is not None:
        return ("chunk_id", int(chunk.chunk_id))
    if chunk.chunk_index is not None:
        return (
            "card_section_index",
            chunk.card_id,
            _norm_section(chunk.section),
            int(chunk.chunk_index),
        )
    norm = _normalize_content_for_hash(chunk.content)
    h = hashlib.sha256(norm.encode("utf-8")).hexdigest()
    return ("card_section_hash", chunk.card_id, _norm_section(chunk.section), h)


# Category-aware section weighting table.
#
# Values are *additive* adjustments to the adjusted distance:
# - Negative numbers slightly boost the section (rank earlier)
# - Positive numbers slightly penalize the section
#
# Guardrail: keep magnitudes small so similarity remains dominant.
CATEGORY_SECTION_BONUS: dict[str, dict[str, float]] = {
    Category.education_and_formal_background.value: {
        # Education answers benefit from concrete facts (degrees, institutions).
        "problem": -0.02,
        "my role": -0.02,
        "what i built": -0.02,
        "overview": -0.06,
        "facts": -0.10,
        "degrees": -0.10,
        "education": -0.08,
        "certifications": -0.06,
        "timeline": -0.05,
        # Avoid pulling in impact/metrics when question is purely education.
        "scale and impact": +0.05,
        "tech stack": +0.03,
    },
    Category.hands_on_engineering.value: {
        "what i built": -0.08,
        "key decisions and trade-offs": -0.06,
        "scale and impact": -0.05,
        "my role": -0.03,
        "problem": -0.02,
        "overview": -0.02,
    },
}


def _category_section_bonus(
    *, routed_category: str | Category | None, preferred_sections: Iterable[str] | None
) -> dict[str, float]:
    bonus: dict[str, float] = {}
    cat = _norm_category(routed_category)
    if cat:
        bonus.update(CATEGORY_SECTION_BONUS.get(cat, {}))

    # Preferred sections are caller hints: apply a small boost.
    for section in preferred_sections or []:
        section_norm = _norm_section(section)
        if not section_norm:
            continue
        # Only a tie-breaker.
        bonus[section_norm] = min(bonus.get(section_norm, 0.0), -0.04)
    return bonus


def _retrieve_impl(
    *,
    question: str,
    limit: int,
    conversation_topic: str | None,
    routed_category: str | Category | None,
    preferred_sections: list[str] | None,
    card_id_filter: list[str] | None,
    oversample_factor: int | None,
) -> list[RetrievedChunk]:
    """Internal retrieval implementation shared by retrieve() and per-category runs."""

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

    # Candidate oversampling:
    # - Legacy single-category path uses limit*8.
    # - Per-category path uses budget*oversample_factor (default depends on category).
    if oversample_factor is None:
        if routed_category is None and not card_id_filter:
            candidate_limit = max(limit * 8, 30)
        else:
            # Defaults tuned for multi-category (tie-breaker only; does not override similarity).
            default = 10 if _is_education_category(routed_category) else 7
            candidate_limit = max(limit * default, 30)
    else:
        candidate_limit = max(limit * int(oversample_factor), 30)

    routed_category_str = _norm_category(routed_category)
    category_filter = routed_category_str if routed_category_str else None

    with psycopg.connect(settings.database_url) as conn:
        register_vector(conn)
        with conn.cursor() as cursor:
            params: list[object] = [embedding_param]
            where = ["section <> 'Links'"]
            if category_filter:
                where.append("category = %s")
                params.append(category_filter)
            if card_id_filter:
                where.append("card_id = ANY(%s)")
                params.append(list(card_id_filter))

            cursor.execute(
                f"""
                SELECT id, card_id, category, section, source_url, content,
                       embedding <=> %s AS distance
                FROM knowledge_chunks
                WHERE {' AND '.join(where)}
                ORDER BY distance
                LIMIT %s;
                """,
                (*params, candidate_limit),
            )
            rows = cursor.fetchall()

    if not rows:
        return []

    candidate_rows = rows

    # Hard cutoffs: allow fewer than `limit` chunks when retrieval is weak.
    #
    # pgvector distance interpretation depends on the chosen operator; this code
    # assumes cosine distance (lower = more similar).
    best_distance = min(float(row[6]) for row in rows)
    max_distance = settings.retrieval_max_distance
    delta = settings.retrieval_distance_delta

    def _keep(row: tuple) -> bool:
        distance = float(row[6])
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
                "category_filter": category_filter,
                "card_id_filter_count": len(card_id_filter or []),
            },
        )
        rows = candidate_rows[:fallback_n]

    # Generic post-processing to prefer substantive sections when the per-card cap
    # forces tradeoffs.
    low_signal_sections = {
        "title",
        "category",
        "tech stack",
    }

    card_has_substantive: dict[str, bool] = {}
    card_max_substantive_len: dict[str, int] = {}
    for row in rows:
        card_id = row[1]
        section = _norm_section(row[3])
        content_len = len(row[5] or "")
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

    # If a card has a clearly substantive (longer) section available, avoid using
    # very short boilerplate-y sections when the per-card cap is tight.
    long_section_len = 220
    short_section_len = 120
    short_substantive_penalty = 0.18

    section_bonus = _category_section_bonus(
        routed_category=routed_category,
        preferred_sections=preferred_sections,
    )

    def _adjusted_distance(row: tuple) -> tuple[float, float, str, str, int]:
        distance = float(row[6])
        card_id = str(row[1])
        section = _norm_section(str(row[3]))
        if not card_has_substantive.get(card_id, False):
            # Deterministic tiebreakers even when no adjustment applies.
            return (distance, distance, card_id, section, int(row[0] or 0))

        penalty = section_penalty.get(section, 0.0)
        penalty += section_bonus.get(section, 0.0)
        if section not in low_signal_sections:
            if (
                card_max_substantive_len.get(card_id, 0) >= long_section_len
                and len(row[5] or "") < short_section_len
            ):
                penalty += short_substantive_penalty

        return (
            distance + penalty,
            distance,
            card_id,
            section,
            int(row[0] or 0),
        )

    rows_ranked = sorted(rows, key=_adjusted_distance)

    per_card_cap = getattr(settings, "retrieval_per_card_cap", 2)
    selected: list[tuple] = []
    per_card_counts: dict[str, int] = {}
    deferred_low_signal: list[tuple] = []

    for row in rows_ranked:
        card_id = row[1]
        if per_card_counts.get(card_id, 0) >= per_card_cap:
            continue

        section_norm = _norm_section(row[3])
        if card_has_substantive.get(card_id, False) and section_norm in low_signal_sections:
            deferred_low_signal.append(row)
            continue

        selected.append(row)
        per_card_counts[card_id] = per_card_counts.get(card_id, 0) + 1
        if len(selected) >= limit:
            break

    if len(selected) < limit and deferred_low_signal:
        for row in deferred_low_signal:
            card_id = row[1]
            if per_card_counts.get(card_id, 0) >= per_card_cap:
                continue
            selected.append(row)
            per_card_counts[card_id] = per_card_counts.get(card_id, 0) + 1
            if len(selected) >= limit:
                break

    if len(selected) < limit:
        selected_set = set(selected)
        for row in rows_ranked:
            if row in selected_set:
                continue
            selected.append(row)
            selected_set.add(row)
            if len(selected) >= limit:
                break

    filtered = selected[:limit]
    out: list[RetrievedChunk] = []
    for row in filtered:
        adjusted, *_ = _adjusted_distance(row)
        out.append(
            RetrievedChunk(
                chunk_id=int(row[0]) if row[0] is not None else None,
                card_id=row[1],
                category=row[2],
                section=row[3],
                source_url=row[4],
                content=row[5],
                distance=float(row[6]),
                adjusted_distance=float(adjusted),
                origin_categories=[routed_category_str] if routed_category_str else None,
                best_origin_category=routed_category_str if routed_category_str else None,
            )
        )
    return out


def retrieve(
    question: str, limit: int = 25, conversation_topic: str | None = None
) -> list[RetrievedChunk]:
    """Retrieve relevant chunks for a question using pgvector."""

    return _retrieve_impl(
        question=question,
        limit=limit,
        conversation_topic=conversation_topic,
        routed_category=None,
        preferred_sections=None,
        card_id_filter=None,
        oversample_factor=None,
    )


def retrieve_for_category(
    question: str,
    category: str | Category,
    budget: int,
    conversation_topic: str | None = None,
    preferred_sections: list[str] | None = None,
    must_include_cards: list[str] | None = None,
    oversample_factor: int | None = None,
) -> list[RetrievedChunk]:
    """Per-category retrieval entrypoint.

    This runs the same SQL similarity search as [`python.retrieve()`](backend/app/retrieval.py:48)
    but:
    - applies a category filter (knowledge_chunks.category)
    - applies category-aware section tie-break bonuses
    - enforces [`python.Settings.retrieval_per_card_cap`](backend/app/config.py:45) per category run
    - returns at most `budget` chunks

    Note: `must_include_cards` currently acts as a *filter* (restricted retrieval
    to those card_ids). This is intentional for pinning flows.
    """

    budget = max(0, int(budget))
    if budget <= 0:
        return []

    return _retrieve_impl(
        question=question,
        limit=budget,
        conversation_topic=conversation_topic,
        routed_category=category,
        preferred_sections=preferred_sections,
        card_id_filter=must_include_cards,
        oversample_factor=oversample_factor,
    )


def merge_retrieval_results_by_category(
    per_category_chunks: dict[str, list[RetrievedChunk]],
) -> list[RetrievedChunk]:
    """Merge + dedup per-category selected chunks, preserving provenance.

    Dedup keys (in priority order):
    1) chunk_id
    2) (card_id, section, chunk_index)
    3) (card_id, section, sha256(normalized_content))

    For dedup collisions, keep the instance with the best (lowest) adjusted
    distance, and record:
    - origin_categories: list[str]
    - best_origin_category: str
    """

    merged_by_key: dict[tuple, RetrievedChunk] = {}
    best_by_key: dict[tuple, dict[str, float]] = {}

    for origin_category, chunks in per_category_chunks.items():
        origin_category = str(origin_category)
        for chunk in chunks or []:
            key = _dedup_key(chunk)
            cand_score = float(
                chunk.adjusted_distance
                if chunk.adjusted_distance is not None
                else (chunk.distance if chunk.distance is not None else 1e9)
            )

            if key not in merged_by_key:
                kept = chunk.model_copy(deep=True)
                kept.origin_categories = [origin_category]
                kept.best_origin_category = origin_category
                merged_by_key[key] = kept
                best_by_key[key] = {origin_category: cand_score}
                continue

            kept = merged_by_key[key]
            origin_dist = best_by_key.setdefault(key, {})
            origin_dist[origin_category] = min(origin_dist.get(origin_category, 1e9), cand_score)

            # Update origin categories list.
            origins = kept.origin_categories or []
            if origin_category not in origins:
                kept.origin_categories = [*origins, origin_category]

            # Preserve pinning: if any instance is pinned, keep pinned.
            kept.pinned = bool(kept.pinned or chunk.pinned)

            # Keep best-scoring instance as the representative.
            best_score = min(origin_dist.values()) if origin_dist else cand_score
            current_best = float(
                kept.adjusted_distance
                if kept.adjusted_distance is not None
                else (kept.distance if kept.distance is not None else 1e9)
            )
            if cand_score < current_best:
                # Replace representative fields with the better instance.
                merged_by_key[key] = chunk.model_copy(deep=True)
                merged_by_key[key].origin_categories = kept.origin_categories
                merged_by_key[key].pinned = kept.pinned
                merged_by_key[key].best_origin_category = kept.best_origin_category
                kept = merged_by_key[key]
                current_best = cand_score

            # Best origin category is the category with the best (lowest) adjusted distance.
            kept.best_origin_category = min(
                origin_dist.items(),
                key=lambda kv: (kv[1], kv[0]),
            )[0]

    merged = list(merged_by_key.values())
    merged.sort(
        key=lambda c: (
            float(
                c.adjusted_distance
                if c.adjusted_distance is not None
                else (c.distance if c.distance is not None else 1e9)
            ),
            float(c.distance if c.distance is not None else 1e9),
            str(c.card_id),
            _norm_section(c.section),
            int(c.chunk_id or 0),
        )
    )
    return merged


def _cap_and_evict_with_category_coverage(
    chunks: list[RetrievedChunk],
    *,
    max_total_chunks: int,
    required_categories: list[str] | None,
) -> list[RetrievedChunk]:
    max_total_chunks = max(0, int(max_total_chunks))
    if max_total_chunks <= 0:
        return []
    if len(chunks) <= max_total_chunks:
        return list(chunks)

    required = [str(c) for c in (required_categories or []) if str(c).strip()]
    required_set = set(required)
    # If the cap is smaller than required categories, coverage cannot be satisfied.
    if required_set and max_total_chunks < len(required_set):
        required_set = set()

    kept = list(chunks)

    def _score(c: RetrievedChunk) -> float:
        return float(
            c.adjusted_distance
            if c.adjusted_distance is not None
            else (c.distance if c.distance is not None else 1e9)
        )

    while len(kept) > max_total_chunks:
        counts: dict[str, int] = {}
        for c in kept:
            cat = str(c.best_origin_category or "")
            counts[cat] = counts.get(cat, 0) + 1

        removable: list[RetrievedChunk] = []
        for c in kept:
            if c.pinned:
                continue
            cat = str(c.best_origin_category or "")
            if cat in required_set and counts.get(cat, 0) <= 1:
                continue
            removable.append(c)

        if not removable:
            # Nothing can be removed without violating constraints. Break.
            break

        # Prefer evicting from over-represented categories.
        def _evict_key(c: RetrievedChunk) -> tuple:
            cat = str(c.best_origin_category or "")
            return (
                -(counts.get(cat, 0)),  # higher count first
                _score(c),  # weaker (higher distance) later; we reverse below
                str(c.card_id),
                _norm_section(c.section),
                int(c.chunk_id or 0),
            )

        # Choose the weakest among the most over-represented.
        removable_sorted = sorted(removable, key=_evict_key)
        # removable_sorted[0] is from the most over-represented; among same category
        # we want to evict the weakest => pick max score within that front group.
        top_cat = str(removable_sorted[0].best_origin_category or "")
        top_group = [c for c in removable_sorted if str(c.best_origin_category or "") == top_cat]
        evict = max(top_group, key=lambda c: (_score(c), str(c.card_id), _norm_section(c.section), int(c.chunk_id or 0)))
        kept.remove(evict)

    return kept[:max_total_chunks]


def merge_dedup_pin_and_cap(
    *,
    question: str,
    per_category_selected: dict[str, list[RetrievedChunk]],
    routed_categories: list[str] | list[Category],
    max_total_chunks: int,
    conversation_topic: str | None = None,
    ensure_education_facts: bool | None = None,
) -> list[RetrievedChunk]:
    """Merge/dedup + optional education-facts pinning + cap/eviction.

    This helper is intentionally retrieval-local (no changes to chat() orchestration yet).
    """

    routed_str = [_norm_category(c) for c in (routed_categories or [])]
    routed_str = [c for c in routed_str if c]
    needs_pin = bool(ensure_education_facts) or any(_is_education_category(c) for c in routed_str)

    merged = merge_retrieval_results_by_category(per_category_selected)
    has_edu_facts = any(c.card_id == "education-facts" for c in merged)
    if needs_pin and not has_edu_facts:
        pinned = retrieve_for_category(
            question,
            Category.education_and_formal_background,
            budget=1,
            conversation_topic=conversation_topic,
            must_include_cards=["education-facts"],
        )
        if pinned:
            for c in pinned:
                c.pinned = True
                c.origin_categories = [Category.education_and_formal_background.value]
                c.best_origin_category = Category.education_and_formal_background.value
            # Insert under education category and re-merge/dedup.
            key = Category.education_and_formal_background.value
            existing = list(per_category_selected.get(key, []))
            per_category_selected = dict(per_category_selected)
            per_category_selected[key] = [*pinned, *existing]
            merged = merge_retrieval_results_by_category(per_category_selected)

    # Apply final cap with category coverage.
    capped = _cap_and_evict_with_category_coverage(
        merged,
        max_total_chunks=max_total_chunks,
        required_categories=routed_str,
    )
    return capped
