# Retention snippets (operator runbook)

This repository currently does **not** enforce retention for `interaction_logs` in code.

A minimal (manual) approach is to run a periodic cleanup query directly against Postgres.

## Delete interaction logs older than 30 days

```sql
DELETE FROM interaction_logs
WHERE logged_at < now() - interval '30 days';
```

Notes:

- The timestamp column is `logged_at` (see [`backend/db/init.sql`](backend/db/init.sql:33)).
- Consider running this as a scheduled job in your deployment environment (outside the app) once you have an agreed retention window.
