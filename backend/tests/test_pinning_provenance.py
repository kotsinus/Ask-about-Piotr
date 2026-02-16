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
# Regression test: pinning must preserve provenance per routing category.

from __future__ import annotations

from app import retrieval


def test_apply_pinning_sets_origin_to_category_being_pinned_for() -> None:
    chunks: list[retrieval.RetrievedChunk] = []
    pinning_rules = {
        "education_and_formal_background": ["education-facts"],
        "hands_on_engineering": ["skills-core"],
    }
    routed = ["education_and_formal_background", "hands_on_engineering"]

    calls: list[tuple[str, int, str]] = []

    def _retrieve_for_card(
        card_id: str, limit: int, pin_for_category: str
    ) -> list[retrieval.RetrievedChunk]:
        calls.append((card_id, limit, pin_for_category))
        return [
            retrieval.RetrievedChunk(
                card_id=card_id,
                card_category="x",
                section="What I built",
                content="c",
                distance=0.1,
                origin_routing_categories=[pin_for_category],
                origin_routing_category=pin_for_category,
                pinned=True,
            )
        ]

    out, pinned_ids = retrieval.apply_pinning(
        chunks=chunks,
        pinning_rules=pinning_rules,
        routed_categories=routed,
        retrieve_for_card_fn=_retrieve_for_card,
    )

    assert set(pinned_ids) == {"education-facts", "skills-core"}
    assert len(out) == 2

    by_id = {c.card_id: c for c in out}
    assert by_id["education-facts"].origin_routing_category == "education_and_formal_background"
    assert by_id["skills-core"].origin_routing_category == "hands_on_engineering"

    # Ensure we passed the correct category to the retrieval callback.
    assert ("education-facts", 1, "education_and_formal_background") in calls
    assert ("skills-core", 1, "hands_on_engineering") in calls

