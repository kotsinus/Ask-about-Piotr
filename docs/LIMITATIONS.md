# Limitations and explicit non-goals

This repository is intentionally scoped as a grounded, evidence-only demo system.

## Product and platform limitations

- Not designed for high QPS or heavy concurrent traffic.
- No authentication/authorization.
- No multi-tenant isolation.
- No admin UI.

## Security and privacy limitations

- No built-in rate limiting / throttling.
- No automated retention enforcement for `interaction_logs`.
- No full threat-modeling exercise or red-teaming harness included.

## RAG / LLM limitations

- Retrieval quality depends on knowledge-card coverage and embedding quality.
- When evidence is missing, the system refuses rather than speculating.
- The system does not browse the internet or perform external search.

## Operational limitations

- Observability is logs-first; no metrics/tracing stack is included in-repo.

