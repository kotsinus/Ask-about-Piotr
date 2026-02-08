# Security model

This document summarizes the security and privacy posture implemented in the repository.

This project prioritizes transparency over completeness; missing controls are documented explicitly rather than implied.

For the full security/privacy discussion (including threats and mitigations), see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md:1).

## API exposure model

The backend is an HTTP API (FastAPI) whose primary surface is:

- `POST /chat` — the main question-answer endpoint.

Exposure assumptions:

- In local development, the API is reachable from the developer machine.
- In production, `POST /chat` is typically a **public endpoint** (internet-reachable) behind a reverse proxy.

Important implications:

- The API must be treated as **untrusted input** (any user can send arbitrary prompts).
- There is currently no authn/authz barrier (see gaps below).

Primary code reference: [`backend/app/main.py`](backend/app/main.py:1).

## Current security posture (what exists today)

- **No authn/authz**: the repository currently has no users, roles, or tokens.
- **Privacy-first logging**: interaction logging is best-effort and designed to avoid storing raw IP addresses.
- **Trusted proxy model**: `X-Forwarded-For` is only trusted when the immediate peer is within `TRUSTED_PROXY_CIDRS`.
- **Secrets via environment variables**: provider keys and salts are injected via env vars.

## Prompt injection and trust boundaries

This system treats the following as **untrusted**:

- User question (`ChatRequest.question`).
- Conversation history (`ChatRequest.messages`).
- Any content coming from the network boundary.

Mitigations implemented in this repo:

1) **Conversation history is not evidence**

- The synthesis prompt explicitly states that conversation context may be used for interpretation only, not as evidence.
- The system builds `evidence[]` and `sources[]` only from retrieved chunks.

Code references: [`backend/app/llm.py`](backend/app/llm.py:140) (grounding rules), [`backend/app/main.py`](backend/app/main.py:427) (used chunk filtering).

2) **Rewrite step ignores instructions in history**

- `rewrite_question()` instructs the model to ignore instructions in conversation history and only resolve references.

Code reference: [`backend/app/llm.py`](backend/app/llm.py:37).

3) **Strict response schema + deterministic formatting**

- The authoritative response contract is structured (`answer`, `evidence`, `sources`, `confidence`).
- `formatted_answer` is derived server-side from those fields.

Schema reference: [`backend/app/schemas.py`](backend/app/schemas.py:1).

Residual risk (explicit):

- Prompt injection cannot be “solved” fully; the system reduces impact by constraining evidence to a curated KB and by treating conversation context as untrusted.

## Privacy-first IP handling

The backend stores derived metadata instead of raw IP addresses:

- `ip_prefix` (IPv4 `/24`, IPv6 `/48`)
- `ip_hash` (one-way salted hash using `IP_HASH_SALT`)

Implementation: [`backend/app/privacy.py`](backend/app/privacy.py:1).

Retention notes:

- Interaction log retention is **not enforced in code** today.
- Operator guidance lives in [`docs/RETENTION.md`](docs/RETENTION.md:1).

## Interaction logging (best effort)

Every `POST /chat` attempt writes a log row to Postgres on a best-effort basis.
Failures to write **must not** break the request path.

Writer: [`backend/app/interaction_logging.py`](backend/app/interaction_logging.py:1).
Schema: [`backend/db/init.sql`](backend/db/init.sql:1).

## Web security / CORS

CORS configuration is environment-driven (see [`.env.example`](.env.example:1)).
Cookie security flags can be tightened in production deployments behind HTTPS.

## Abuse scenarios (and current posture)

This section names common abuse/cost risks for public LLM-backed endpoints.

Scenarios:

- **High request volume / scraping** → cost and resource exhaustion.
- **Budget exhaustion / API key abuse** → provider spend blow-up or service disruption.
- **Prompt injection attempts** → attempts to bypass grounding/refusal rules.

Current in-repo posture:

- No built-in rate limiting.
- No explicit budget caps.
- Minimal, privacy-safe logging for coarse abuse analysis (`ip_prefix`, `ip_hash`, request ids).

## What is NOT secured / known gaps (honest list)

- No authentication/authorization.
- No multi-tenant isolation.
- No rate limiting / throttling.
- No automated retention enforcement for `interaction_logs`.
- No content moderation / red-teaming harness.

## Recommended next controls (not implemented)

- Add authentication/authorization for non-local deployments.
- Add rate limiting at the edge (and/or per-session throttling).
- Define and enforce an `interaction_logs` retention policy.
- Add cost controls (daily budgets, alerting, per-session caps) when using paid providers.

