# Data model

This document summarizes the persistence model in Postgres for Ask-about-Piotr.

Canonical schema source: [`backend/db/init.sql`](backend/db/init.sql:1).

Schema migrations (existing production DBs):

- Postgres only runs `init.sql` automatically on **fresh** volumes.
- For an already-running production database, apply the relevant idempotent SQL
  migration(s) from [`backend/db/migrations/`](backend/db/migrations/2026-02-10_add_interaction_log_context_columns.sql:1).

Example (psql):

```sql
\i backend/db/migrations/2026-02-10_add_interaction_log_context_columns.sql
```

For retention posture, see [`docs/RETENTION.md`](docs/RETENTION.md:1).

## Overview

The database stores two primary tables:

- `knowledge_chunks` — retrieval evidence store for RAG.
- `interaction_logs` — privacy-minimized operational logs for `/chat` requests.

There are no relational foreign keys between these tables today; they serve different concerns.

## Table: `knowledge_chunks`

Purpose:

- Stores chunked content derived from Markdown knowledge cards, plus embeddings for similarity search.

Key columns (high level):

- `card_id` (text) — identifier used for citations.
- `category` (text) — high-level grouping.
- `section` (text) — section name inside the card.
- `source_url` (text, nullable) — human-auditable link carried from card metadata.
- `content` (text) — the chunk text shown as evidence.
- `embedding` (vector) — pgvector embedding for retrieval.

Data lifecycle:

- **Persistent within a DB volume**, but rebuilt on ingestion: the ingestion process truncates and repopulates the table.

References:

- Retrieval query: [`backend/app/retrieval.py`](backend/app/retrieval.py:48)
- Ingestion rebuild semantics: [`backend/scripts/ingest_cards.py`](backend/scripts/ingest_cards.py:1)

## Table: `interaction_logs`

Purpose:

- Records each `POST /chat` interaction for correlation/debugging and coarse analytics.

Key columns (high level):

- Correlation/timing: `request_id`, `session_id`, `conversation_id`, `request_at`, `response_at`, `latency_ms`, `logged_at`.
- Payload: `question`, `answer`.
- Model metadata: `router_model`, `synthesis_model`, `embeddings_provider`, `embeddings_model`.
- Client metadata (privacy-first): `ip_prefix`, `ip_hash`, `user_agent`, `country`.

Additional context columns (for debugging/analytics):

- `standalone_question` (text, nullable) — rewritten version of `question` used for retrieval/synthesis.
  Produced by [`rewrite_question()`](backend/app/llm.py:37).
- `incoming_last_topic` (text, nullable) — topic provided by the client in request context (`ChatRequest.context.last_topic`).
- `resolved_topic` (text, nullable) — topic returned to the client in response context (either best retrieved card id or `incoming_last_topic`).
- `topic_used_for_retrieval` (boolean, nullable) — whether `incoming_last_topic` was used to augment retrieval.
- `messages_count` (integer, nullable) — number of conversation history messages received in the request.
- `retrieval_chunk_count` (integer, nullable) — number of chunks returned by similarity search (`len(chunks)` from [`retrieve()`](backend/app/retrieval.py:48)).
  - `llm_context_messages` (jsonb, nullable) — last ~6 conversation messages actually used as LLM context.
  This field is controlled by env var `INTERACTION_LOG_INCLUDE_LLM_CONTEXT` (see [`.env.example`](.env.example:1)).
  Each message `content` is truncated to 2000 characters before storage.

Optional JSON context (multi-category routing/retrieval rollout):

- `routing` (jsonb, nullable) — normalized routing payload after server clamping.
  Shape: `{"categories": [{"category": str, "confidence": str, "budget": int}], "max_categories": int, "max_total_chunks": int, "router_fallback_used": bool}`.
- `retrieval_by_category` (jsonb, nullable) — per-category budgets and selected counts.
  Shape (v1): `{"max_total_chunks": int, "categories": [{"category": str, "budget": int, "selected_count": int}]}`.
- `quality_gate` (jsonb, nullable) — summary of synthesis quality gate outcome.
  Shape (v1): `{"passed": bool, "failure_reasons": [str], "retry_attempted": bool, "used_chunk_indices_count": int, "used_categories": [str]}`.

Derived vs. persisted:

- **Derived (privacy-minimized)**:
  - `ip_prefix` is derived from the client IP (IPv4 `/24`, IPv6 `/48`).
  - `ip_hash` is derived from the client IP + `IP_HASH_SALT`.
- **Persisted (operator-visible)**:
  - `question` and `answer` are persisted.
  - Raw IP is **not** persisted.

Write semantics:

- The write is **best effort** and must not break the response path.

References:

- Writer: [`backend/app/interaction_logging.py`](backend/app/interaction_logging.py:61)
- Privacy helpers: [`backend/app/privacy.py`](backend/app/privacy.py:34)
 - `/chat` orchestration + logging payload: [`backend/app/main.py`](backend/app/main.py:373)

## Transient / in-memory identifiers

These identifiers exist at runtime but are not “core data model tables”:

- `X-Request-ID` — per-request correlation header (also added to responses).
  - Helper: [`backend/app/observability.py`](backend/app/observability.py:1)
- `ask_piotr_session_id` — anonymous session cookie.
  - Set in middleware: [`backend/app/main.py`](backend/app/main.py:147)

