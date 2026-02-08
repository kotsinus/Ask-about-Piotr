# RAG pipeline design

This document is a short, implementation-aligned overview of how Ask-about-Piotr answers questions.

For the full architecture reference (including diagrams and request flows), see
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md:1).

## Core idea

The system is a **strictly grounded** RAG pipeline:

1. **Retrieval**: find candidate evidence chunks in Postgres (`knowledge_chunks`) using pgvector.
2. **Synthesis**: produce an answer using retrieved evidence only (or refuse when evidence is insufficient).
3. **Contract assembly**: build the strict structured response (`answer`, `evidence`, `sources`, `confidence`).
4. **Deterministic formatting**: render `formatted_answer` as a human-readable view derived from the structured fields.

The design goal is to make failures diagnosable (retrieval empty vs. synthesis non-compliant vs. formatting/schema failure)
and to avoid “helpful” hallucinations.

## End-to-end flow (rewrite → route → retrieve → synthesize → guardrails)

This is the current request path for `POST /chat`:

1) **Rewrite (optional)**

- Purpose: rewrite potentially ambiguous follow-up questions into a standalone question.
- Input: user question + limited conversation history.
- Trust boundary: conversation history is treated as **untrusted**; the rewrite step is instructed to ignore any instructions in history.
- Failure behavior: if the OpenAI key is not configured or JSON parsing fails, the original question is used.

Code reference: [`backend/app/llm.py`](backend/app/llm.py:37).

2) **Route (optional)**

- Purpose: classify the question into exactly one category.
- Failure behavior:
  - If routing via LLM fails or is not configured, the backend falls back to a deterministic heuristic classifier.

Code references: [`backend/app/llm.py`](backend/app/llm.py:103), [`backend/app/main.py`](backend/app/main.py:264).

3) **Retrieve**

- Purpose: select candidate evidence chunks from Postgres table `knowledge_chunks` via pgvector similarity search.
- Boundaries:
  - Hard cutoffs (max distance / delta) can intentionally yield fewer than `limit` chunks.
  - Post-processing diversifies across cards (per-card cap) and de-prioritizes low-signal sections (e.g., Title).
  - If cutoffs filter all candidates, the system returns a small fallback set instead of returning zero sources.

Code reference: [`backend/app/retrieval.py`](backend/app/retrieval.py:48).

4) **Synthesize**

- Purpose: generate a grounded answer and explain “why this matters” using retrieved evidence.
- Grounding rules:
  - Use only provided evidence.
  - Conversation context may help interpret the question but is not evidence.
  - If evidence is insufficient, return the exact refusal message.
  - If evidence is used, provide the indices of used chunks.

Failure behavior:

- If there are no retrieved chunks, synthesis returns a standard refusal.
- If OpenAI is not configured, synthesis falls back to deterministic synthesis over retrieved chunks.
- If the model returns an answer but does not provide used indices, the system falls back to “all chunks” to preserve traceability.

Code reference: [`backend/app/llm.py`](backend/app/llm.py:140).

5) **Guardrails / contract assembly (server-side)**

- The backend constructs `evidence[]` and `sources[]` only from chunks that were actually used.
- The response contract is strict and structured; `formatted_answer` is rendered deterministically from structured fields.

Code references: [`backend/app/main.py`](backend/app/main.py:427), [`backend/app/main.py`](backend/app/main.py:284), [`backend/app/schemas.py`](backend/app/schemas.py:92).

## Authoritative response contract

The API’s source of truth is the strict structured schema:

- `answer`
- `evidence[]`
- `sources[]`
- `confidence`

`formatted_answer` is a deterministic rendering derived from the structured fields.

Schema definition: [`backend/app/schemas.py`](backend/app/schemas.py:1).

## Implementation map

- Endpoint orchestration: [`backend/app/main.py`](backend/app/main.py:1)
- Retrieval logic and post-processing: [`backend/app/retrieval.py`](backend/app/retrieval.py:1)
- Knowledge-card parsing + chunking (ingestion): [`backend/app/knowledge.py`](backend/app/knowledge.py:1)
- LLM routing/synthesis and grounded refusal behavior: [`backend/app/llm.py`](backend/app/llm.py:1)
- Embeddings provider abstraction: [`backend/app/embeddings.py`](backend/app/embeddings.py:1)

## Retrieval boundaries

Retrieval is explicitly constrained by distance thresholds and post-processing rules.
This controls evidence quality and limits “partial matches” from dominating the answer.

Primary configuration knobs are defined in [`backend/app/config.py`](backend/app/config.py:1).

## Ingestion (knowledge base rebuild)

Ingestion is run separately from serving. Each ingestion run **rebuilds** the `knowledge_chunks` table
(truncate + insert), so the served knowledge base is always a snapshot of the current Markdown cards.

Ingestion script: [`backend/scripts/ingest_cards.py`](backend/scripts/ingest_cards.py:1).

## Where RAG can fail (and how the system responds)

Common RAG failure modes and the current handling:

- **No relevant evidence retrieved** → explicit refusal (low confidence) rather than guessing.
- **Retrieval cutoffs too strict** → warning + small fallback set of top candidates.
- **Routing not available** → deterministic heuristic classifier.
- **Provider outages / rate limits** → HTTP error mapping for OpenAI SDK exceptions.

Code references: [`backend/app/llm.py`](backend/app/llm.py:149), [`backend/app/retrieval.py`](backend/app/retrieval.py:94), [`backend/app/main.py`](backend/app/main.py:214).

