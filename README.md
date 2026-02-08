# Ask about Piotr

AI-powered application that answers questions about Piotr's professional experience
using only a curated knowledge base. The system is strictly grounded in evidence
from Markdown knowledge cards and refuses to answer when evidence is missing.

## Repository Structure
- `backend/` — FastAPI RAG backend (current focus)
- `frontend/` — placeholder for future UI
- `knowledge/` — Markdown knowledge cards
- `plans/` — architecture notes and decisions

## Core Guarantees
- No answers beyond provided sources
- Every answer includes citations
- If evidence is insufficient, the system explicitly refuses
- The pipeline is retrieval → synthesis with strict boundaries

## Quick Start (Backend)
### Run with Docker
```bash
docker compose up --build
```

### Run locally (Python 3.12)
```bash
python -m venv .venv
source .venv/bin/activate
 pip install -r backend/requirements.txt
 uvicorn app.main:app --reload
```

### Logging

The backend uses stdlib logging with consistent formatting for app + uvicorn.

Env vars:
- `LOG_LEVEL` (default: `INFO`)
- `LOG_FORMAT` (default: `json`, allowed: `json` or `text`)
- `UVICORN_ACCESS_LOG_LEVEL` (default: `WARNING`) — uvicorn access logs are
  suppressed by default to avoid duplicate per-request logs (the app emits its
  own request log line).

Each request gets an `X-Request-ID` response header. If the client sends
`X-Request-ID`, it is propagated.

### Interaction logging (Postgres)

On every `POST /chat` request, the backend performs **best-effort** persistence of
the final interaction to Postgres table `interaction_logs` (created in
[`backend/db/init.sql`](backend/db/init.sql:1)). Failures to write the log **must
not** break the request path.

Implementation note: persistence is implemented via SQLAlchemy ORM (engine + session
management in [`backend/app/db.py`](backend/app/db.py:1) and model mapping in
[`backend/app/models.py`](backend/app/models.py:1)).

Logged fields (high level):
- `question`, `answer`
- `request_id`, `request_at`, `response_at`, `latency_ms`
- Model metadata: `router_model`, `synthesis_model`, `embeddings_provider`, `embeddings_model`
- Client metadata:
  - `ip_prefix` (IPv4 `/24` or IPv6 `/48`)
  - `ip_hash` (salted, one-way hash)
  - `user_agent`
  - `country` (optional; see GeoIP below)

Privacy model (IP handling):
- **Raw IP addresses are never persisted**.
- `ip_prefix` keeps only coarse network information for basic aggregation and abuse
  monitoring.
- `ip_hash` enables stable de-duplication/rate-limit analysis without storing the raw IP.
- `X-Forwarded-For` is only trusted when `TRUSTED_PROXY_CIDRS` is set; otherwise the
  direct peer IP is used.

Configuration:
- Required:
  - `DATABASE_URL`
  - `IP_HASH_SALT` (set a secret unique per deployment; see [`.env.example`](.env.example:1))

Web security / CORS:
- `COOKIE_SECURE` (default: `false`; set `true` in production behind HTTPS)
- `CORS_ALLOW_ORIGINS` (default: `http://localhost:3000`; comma-separated)
- Required when running behind a reverse proxy:
  - `TRUSTED_PROXY_CIDRS` (comma-separated CIDRs that identify trusted proxy peers)
- Optional (default OFF):
  - `GEOIP_ENABLED=false` to disable country lookup
  - `GEOIP_PROVIDER`, `GEOIP_URL`

Inspecting logged interactions (example SQL):
```sql
SELECT
  logged_at,
  request_id,
  latency_ms,
  ip_prefix,
  country,
  left(question, 120) AS question_preview
FROM interaction_logs
ORDER BY logged_at DESC
LIMIT 20;
```

## Ingestion Runbook
1) Start Postgres + backend:
```bash
docker compose up --build
```
2) Load knowledge cards into pgvector:
```bash
python backend/scripts/ingest_cards.py
```
3) Ask a question via UI or API.

Environment variables are defined in [`.env.example`](.env.example:1).

For more detail on the privacy-first design and proxy trust model, see
[`plans/interaction-logging.md`](plans/interaction-logging.md:1).

## Frontend Toolchain (Node / npm / Next.js / TypeScript)

Current frontend versions are pinned in [`frontend/package.json`](frontend/package.json:1).

- Node.js: **22 LTS** (Docker uses `node:22.22.0-alpine` in [`frontend/Dockerfile`](frontend/Dockerfile:1))
- npm: pinned via `packageManager` in [`frontend/package.json`](frontend/package.json:1)
- Next.js: pinned in [`frontend/package.json`](frontend/package.json:1)
- TypeScript: pinned in [`frontend/package.json`](frontend/package.json:1)

Local dev alignment:
- Use [`frontend/.nvmrc`](frontend/.nvmrc:1) to select a compatible Node 22 version.

## API
`POST /chat`

Request body:
```json
{
  "question": "What did you build for X project?"
}
```

Response contains the mandatory answer format in `formatted_answer`, plus
structured fields for evidence and sources.

## Knowledge Cards
See [`knowledge/README.md`](knowledge/README.md:1) for the required card schema
and metadata model.

## License
Apache License 2.0. See [`LICENSE`](LICENSE:1).

