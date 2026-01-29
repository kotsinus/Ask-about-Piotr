# Evaluation Checklist

## Objectives
- Verify answers are strictly grounded in retrieved knowledge cards.
- Confirm required output format is followed exactly.
- Ensure refusals are issued when evidence is insufficient.

## Pre-flight
- [ ] `docker compose up --build` starts backend and pgvector.
- [ ] `python backend/scripts/ingest_cards.py` loads chunks without errors.
- [ ] `/chat` responds in under 2 seconds for typical queries.

## Format Compliance
- [ ] Response includes `Answer`, `Why this matters`, `Evidence`, `Sources`, `Confidence`.
- [ ] Evidence snippets are quoted and include `card_id`.
- [ ] Sources list uses `card_id.section` format.

## Grounding & Refusal Behavior
- [ ] If no chunks are retrieved, answer is exactly: “I do not have enough evidence in the provided materials.”
- [ ] No claims appear that are not explicitly present in evidence snippets.
- [ ] No merging across cards unless supported by content.

## Sample Queries
- [ ] “What did you build for Decreen?”
- [ ] “Which tech stack was used in the on‑prem RAG system?”
- [ ] “What certification proves agile business skills?”
- [ ] “Do you have evidence of leadership strategy work?” (expect refusal if unsupported)

## Regression Checks
- [ ] Tests pass: `python -m pytest .\\backend\\tests`
- [ ] CI workflow succeeds on a PR.

