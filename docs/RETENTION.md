# Data retention and logging

This repository distinguishes two data sets with different retention characteristics:

1. **Knowledge chunks** (`knowledge_chunks`) used for retrieval.
2. **Interaction logs** (`interaction_logs`) used for operational visibility.

For the full architecture reference, see:
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md:1) (especially “Data model and retention”).

## `knowledge_chunks` (RAG evidence store)

Retention model: **rebuild by design**.

- Each ingestion run truncates and repopulates `knowledge_chunks`.
- This means previously ingested chunks are removed unless they still exist in the current card set.

Ingestion: [`backend/scripts/ingest_cards.py`](backend/scripts/ingest_cards.py:1).

## `interaction_logs` (privacy-first operational logs)

Retention model: **not enforced in code (TBD)**.

- The backend writes logs best-effort (failures must not break the request path).
- Raw IP addresses are never stored; only privacy-minimized derived fields.

Optional fields (operator-controlled):

- The backend can persist the **LLM conversation context window** (last few messages) used for the request.
  This is stored in `interaction_logs.llm_context_messages` when enabled via
  [`INTERACTION_LOG_INCLUDE_LLM_CONTEXT`](.env.example:1).
  Each message `content` is truncated to 2000 characters before storage.

Design notes: [`plans/interaction-logging.md`](plans/interaction-logging.md:1).

### Current status

There is no automated deletion/rotation job in this repository yet.
Operators should define a retention window and enforce it outside the app (e.g., scheduled job).

Minimal operator snippet (manual): [`plans/retention.md`](plans/retention.md:1).

Example (delete logs older than 30 days):

```sql
DELETE FROM interaction_logs
WHERE logged_at < now() - interval '30 days';
```

Schema reference: [`backend/db/init.sql`](backend/db/init.sql:1).

