# Database migrations

This repository uses a lightweight, SQL-only migration approach designed to work well with Docker Compose and Postgres.

## Goals

- **No data loss** for existing production DB volumes.
- **Idempotent** migrations: safe to run multiple times.
- **Deterministic ordering**: migrations apply in a predictable sequence.
- Keep [`backend/db/init.sql`](backend/db/init.sql:1) as the **canonical schema** for *fresh* installations.

## What runs automatically (and when)

### 1) Fresh Postgres volume (bootstrap)

When Postgres starts on a **fresh data volume**, it executes:

- [`backend/db/init.sql`](backend/db/init.sql:1) via `/docker-entrypoint-initdb.d` (see [`docker-compose.yml`](docker-compose.yml:71) and [`docker-compose.prod.yml`](docker-compose.prod.yml:54)).

This is the only thing Postgres does “automatically” by itself.

### 2) Existing production DB (migrations)

For an already-running DB volume, `init.sql` is **not** re-applied.
Instead, this repo provides a migration runner:

- [`backend/scripts/run_migrations.py`](backend/scripts/run_migrations.py:1)

It applies all `*.sql` files from:

- [`backend/db/migrations/`](backend/db/migrations/2026-02-10_add_interaction_log_context_columns.sql:1)

Migrations are executed by the backend container entrypoint on startup:

- [`backend/entrypoint.sh`](backend/entrypoint.sh:1)

## Migration file conventions

### Where to put migrations

Put new migrations into:

- [`backend/db/migrations/`](backend/db/migrations/2026-02-10_add_interaction_log_context_columns.sql:1)

### Naming

Use a lexicographically sortable prefix so ordering is stable:

- `YYYY-MM-DD_<short_description>.sql`

Example:

- `2026-03-01_add_user_feedback_table.sql`

### Style requirements (important)

The migration runner is intentionally simple. To keep it reliable:

1) **Idempotent DDL only**

Prefer:

```sql
ALTER TABLE some_table
  ADD COLUMN IF NOT EXISTS new_col TEXT;
```

2) **Prefer plain SQL DDL (procedural blocks are supported, but still discouraged)**

The runner has a splitter that attempts to handle strings/comments and Postgres dollar-quoted blocks,
but this is still intentionally not a full SQL parser. Keep migrations simple when possible.

3) **No destructive changes by default**

Avoid `DROP COLUMN`, `TRUNCATE`, `DELETE`, etc. If you must do a destructive change, create a dedicated migration and document the operator steps.

4) **One concern per migration**

Keep migrations small and focused. This makes roll-forward safer.

## How migrations are applied

### Automatic at backend startup

When the backend container starts, it runs:

1) [`run_migrations.py`](backend/scripts/run_migrations.py:1) `up`
2) [`ensure_ingested.py`](backend/scripts/ensure_ingested.py:1)
3) The actual server command (Gunicorn/Uvicorn)

This behavior is controlled by environment variables:

- `AUTO_MIGRATE_ENABLED` (default `true`)
- `AUTO_INGEST_ENABLED` (default `true`)
- `AUTO_STARTUP_FAIL_FAST` (default `true`)

### Concurrency and safety

- The migration runner uses a Postgres advisory lock (`pg_advisory_lock`) so only one backend instance applies migrations at a time.
- Applied migrations are recorded in `schema_migrations` with a SHA-256 checksum (see [`_ensure_schema_migrations_table()`](backend/scripts/run_migrations.py:164)).
  If a file changes after being applied, startup fails (checksum mismatch), which prevents silent drift.

### Manual execution (psql)

You can run a migration manually with:

```sql
\i backend/db/migrations/<migration-file>.sql
```

## Knowledge ingestion automation

In addition to schema migrations, the stack can automatically ensure the knowledge base is loaded:

- Wrapper: [`backend/scripts/ensure_ingested.py`](backend/scripts/ensure_ingested.py:1)
- Full ingestion: [`backend/scripts/ingest_cards.py`](backend/scripts/ingest_cards.py:1)

Behavior:

- If `knowledge_chunks` already has rows **and** the knowledge directory hash is unchanged, ingestion is a no-op.
- If empty (or missing), ingestion runs and populates embeddings.
- If the knowledge directory hash changed since last run, ingestion runs again.
- To force a rebuild, set `FORCE_REINGEST=1` (this triggers a TRUNCATE + reinsert in the ingestion script).

### Concurrency and safety

- Ingestion also uses a Postgres advisory lock (see [`main()`](backend/scripts/ensure_ingested.py:161)) so multiple backend replicas won’t ingest concurrently.
- Ingestion state is persisted in `knowledge_ingestion_state` (hash + embeddings config), and is used to decide if re-ingestion is needed.

## Operator notes / limitations

- **Long-running ingestion**: embedding generation can be slow and depends on provider limits.

