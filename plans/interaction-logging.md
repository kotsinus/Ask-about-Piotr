# Interaction logging (Postgres) + privacy-first IP handling

The backend persists a **best-effort** log row for every `POST /chat` interaction
to Postgres table `interaction_logs`.

- Schema: [`backend/db/init.sql`](backend/db/init.sql:1)
- Writer: [`backend/app/interaction_logging.py`](backend/app/interaction_logging.py:1)
- ORM/session management: [`backend/app/models.py`](backend/app/models.py:1), [`backend/app/db.py`](backend/app/db.py:1)

## What is logged

Application data:
- `question` (user prompt)
- `answer` (final response)

Timing and correlation:
- `request_id` (also returned as `X-Request-ID`)
- `request_at`, `response_at`, `latency_ms`

Model metadata:
- `router_model`, `synthesis_model`
- `embeddings_provider`, `embeddings_model`

Client metadata (privacy-first):
- `ip_prefix`:
  - IPv4 is truncated to `/24` (example: `203.0.113.0/24`)
  - IPv6 is truncated to `/48`
- `ip_hash`: one-way salted hash of the client IP (stable for the same IP+salt)
- `user_agent`
- `country` (optional; populated only when GeoIP is enabled)

Non-goals / not stored:
- Raw IP address (MUST NOT be persisted)
- Full request headers / full request body (beyond `question`)

## Privacy model and rationale

The goal is to support basic operational visibility (debugging, abuse monitoring,
coarse usage aggregation) while minimizing the collection of personal data.

Two derived values are stored instead of the raw IP:

1) `ip_prefix` (coarse network bucket)
- Enables aggregation by network without identifying a specific device.
- Reduces the risk of long-term tracking compared to full IP storage.

2) `ip_hash` (salted, one-way)
- Enables de-duplication patterns (same client across requests) without storing
  the original IP.
- Salted so that hashes are not comparable across deployments.

`IP_HASH_SALT` should be treated as a secret.

## Proxy handling: when `X-Forwarded-For` is trusted

The application only honors `X-Forwarded-For` when `TRUSTED_PROXY_CIDRS` is set
and the immediate peer IP is within one of those CIDRs.

Rationale: `X-Forwarded-For` is a user-controlled header unless it comes from a
trusted reverse proxy.

## Configuration

Required:
- `DATABASE_URL` (Postgres connection string)
- `IP_HASH_SALT` (secret; unique per deployment)

Required for deployments behind reverse proxies (recommended in production):
- `TRUSTED_PROXY_CIDRS` (comma-separated CIDR list)

Optional GeoIP (default OFF):
- `GEOIP_ENABLED=false`
- `GEOIP_PROVIDER` (default `ipapi_co`)
- `GEOIP_URL` (optional override; supports `{ip}` placeholder)

See [`.env.example`](.env.example:1) for the current set of environment variables.

## Inspecting the data

Example: most recent interactions (trim the prompt for readability):

```sql
SELECT
  logged_at,
  request_id,
  latency_ms,
  router_model,
  synthesis_model,
  ip_prefix,
  country,
  left(question, 120) AS question_preview
FROM interaction_logs
ORDER BY logged_at DESC
LIMIT 50;
```

Example: coarse aggregation by network prefix:

```sql
SELECT
  ip_prefix,
  count(*) AS interactions
FROM interaction_logs
WHERE logged_at > now() - interval '7 days'
GROUP BY ip_prefix
ORDER BY interactions DESC
LIMIT 50;
```
