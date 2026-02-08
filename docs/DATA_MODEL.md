# Data model

This document summarizes the persistence model in Postgres for Ask-about-Piotr.

Canonical schema source: [`backend/db/init.sql`](backend/db/init.sql:1).

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

## Transient / in-memory identifiers

These identifiers exist at runtime but are not “core data model tables”:

- `X-Request-ID` — per-request correlation header (also added to responses).
  - Helper: [`backend/app/observability.py`](backend/app/observability.py:1)
- `ask_piotr_session_id` — anonymous session cookie.
  - Set in middleware: [`backend/app/main.py`](backend/app/main.py:147)

