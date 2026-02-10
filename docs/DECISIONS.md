# Decisions (mini ADR log)

This is a lightweight decision log for the most important architecture choices.

## 1) Separate retrieval from synthesis

Retrieval selects evidence; synthesis produces language.
Keeping these stages separate makes failures diagnosable (bad retrieval vs. bad synthesis) and allows deterministic rules around evidence handling.
It also makes it possible to test retrieval behavior without requiring an LLM.

References: [`backend/app/retrieval.py`](backend/app/retrieval.py:48), [`backend/app/llm.py`](backend/app/llm.py:140).

## 2) Structured schema is the source of truth (not free text)

The response contract is a strict structured schema (`answer`, `evidence`, `sources`, `confidence`).
`formatted_answer` is derived on the server for human readability, but it is not the authoritative contract.
This reduces ambiguity for clients and makes automated validation possible.

Reference: [`backend/app/schemas.py`](backend/app/schemas.py:92).

## 3) Conversation history is untrusted

Conversation history can contain prompt injection attempts.
The system allows using history only to resolve ambiguity (rewrite), but does not treat history as evidence.
Evidence must come from curated knowledge chunks.

References: [`backend/app/llm.py`](backend/app/llm.py:37), [`backend/app/llm.py`](backend/app/llm.py:240).

## 4) Post-generation guardrails exist as deterministic server behavior

The backend, not the LLM, decides what is included in `evidence[]` and `sources[]`.
Only retrieved chunks actually used in the answer are returned.
This avoids returning “citations” that were not used and keeps the response auditable.

Reference: [`backend/app/main.py`](backend/app/main.py:427).

## 5) Retention for knowledge is a rebuild; retention for logs is out-of-band

The knowledge evidence store (`knowledge_chunks`) is rebuilt on ingestion for correctness and simplicity.
Interaction logs are operational data; retention enforcement is currently out-of-band (operator-managed) and explicitly documented as not enforced in code.
This keeps the serving path simple while preserving an honest privacy posture.

References: [`docs/RETENTION.md`](docs/RETENTION.md:1), [`backend/scripts/ingest_cards.py`](backend/scripts/ingest_cards.py:1).

## 6) Best-effort interaction logging must not break `/chat`

Operational logging is useful, but it must never turn into an availability risk.
The system schedules logging as a background task and degrades gracefully on DB errors.
This is an explicit reliability decision.

References: [`backend/app/main.py`](backend/app/main.py:73), [`backend/app/interaction_logging.py`](backend/app/interaction_logging.py:61).

## 7) Multi-category routing budgets are clamped server-side and versioned

When multi-category mode is enabled, routing produces 1+ categories with per-category chunk budgets.

Policy:

- Max routed categories is clamped by `Settings.multi_category_max_categories` (default 2; allow 3 only when explicitly enabled).
- Total chunk budget is clamped by `Settings.multi_category_max_total_chunks` (default 5). A 6-chunk ceiling is permitted only under an explicit config gate (`multi_category_allow_six_chunks`) for the 3-intent case.
- Budget allocation is **server-side deterministic and versioned** via `Settings.multi_category_intent_budget_policy` (current: `intent_rules_v1`). If the router provides unusable budgets, the server applies the configured policy.

Rationale:

- Stable, versioned policy makes production behavior reproducible across releases.
- Server-side clamps prevent LLM output from increasing cost or degrading answer precision.

References: [`backend/app/main.py`](backend/app/main.py:511), [`plans/multi-category-routing-retrieval-implementation-plan.md`](plans/multi-category-routing-retrieval-implementation-plan.md:21).

