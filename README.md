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

