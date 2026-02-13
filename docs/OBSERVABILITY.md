# Observability

This document describes the in-repo observability model (what you can see and how to correlate events).

Metrics and tracing are intentionally omitted to keep the runtime minimal and auditable.

## Correlation primitives

### Request ID (`X-Request-ID`)

- Every HTTP request is assigned a request id.
- If the client sends `X-Request-ID`, it is propagated; otherwise a UUID is generated.
- The response also includes the `X-Request-ID` header.

Code references: [`backend/app/observability.py`](backend/app/observability.py:1), [`backend/app/main.py`](backend/app/main.py:147).

### Anonymous session cookie (`ask_piotr_session_id`)

- A privacy-friendly, HttpOnly UUID cookie is set for browser clients.
- It is not derived from IP.
- It is used for coarse session correlation in `interaction_logs`.

Code reference: [`backend/app/main.py`](backend/app/main.py:152).

## Structured logging

The backend uses stdlib logging with a centralized configuration.

Formats:

- JSON (default)
- key-value text (`LOG_FORMAT=text`)

Per-request fields:

- `request_id`
- `method`, `path`, `status_code`, `duration_ms`

Code reference: [`backend/app/logging_setup.py`](backend/app/logging_setup.py:98).

### Chat pipeline events

In addition to high-level request logs, `POST /chat` emits structured events that describe the RAG stages without logging raw user text.

- `chat_routing`: routed categories with per-category budgets; includes `router_fallback_used`.
- `chat_retrieve_category`: per-category retrieval selection counts and budgets.
- `chat_pinning`: pinned card IDs when pinning rules are applied for routed categories.
- `chat_retrieve_merge`: merge/dedup counts, pinned cards and final chunk count.
- `chat_synthesis_quality_gate`: quality-gate pass/fail, failure reasons, and whether a retry was attempted.
- `chat_quality_rules_log_only`: category-specific quality rule validation failures (v1 log-only mode).

Code reference: [`backend/app/main.py`](backend/app/main.py:373).

## What is logged vs. intentionally not logged

Logged (high level):

- Request lifecycle events (start, request completion/failure).
- Best-effort interaction log rows (question + final answer + privacy-minimized metadata).

Intentionally not logged:

- Raw IP addresses.
- Full request headers.
- Full request body beyond the `question` payload.

Rationale and details:

- Privacy helpers: [`backend/app/privacy.py`](backend/app/privacy.py:1)
- Interaction log design notes: [`plans/interaction-logging.md`](plans/interaction-logging.md:1)

