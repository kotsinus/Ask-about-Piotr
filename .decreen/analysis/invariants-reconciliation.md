# Invariants code assessment report

> Generated from structured artifacts. Source of truth: `latest.invariants-code-assessment.json`.
> Reconciliation tiers (CONFIRMS / DISCOVERY-ONLY / INVENTORY-ONLY) are **not** derived here — they describe cross-source doctrine presence, not code truth.

## Run metadata

| Field | Value |
| --- | --- |
| Assessment run | `26624350-517a-473e-8d7d-48de5ee69238-code-assessment` |
| Inventory run | `26624350-517a-473e-8d7d-48de5ee69238` |
| Verified at commit | `78fcb9977729e94a05d7611d3b41ce8fb9200695` |
| Verified at | 2026-10-12T17:07:23Z |
| Working tree clean | yes |
| Repository | https://github.com/kotsinus/Ask-about-Piotr.git |
| Method | decreen-inv-phase2-phase5 |

## Summary

| Status | Count |
| --- | ---: |
| Code-supported | 17 |
| Code-contradicted | 0 |
| Partially assessed | 1 |
| Inconclusive | 0 |
| Not assessed | 18 |

---

## Code-supported

| sourceId | scope | confidence | statement (truncated) |
| --- | --- | --- | --- |
| `IMPORT-readme-line-16` | partial | medium | No answers beyond provided sources |
| `IMPORT-readme-line-17` | partial | medium | Every answer includes citations |
| `IMPORT-readme-line-18` | partial | medium | If evidence is insufficient, the system explicitly refuses |
| `IMPORT-readme-line-93` | partial | medium | Raw IP addresses are never persisted. |
| `IMPORT-readme-line-15` | partial | medium | Each card is a standalone Markdown file that MUST include the following sections |
| `IMPORT-readme-line-36` | partial | medium | When cards are chunked, each chunk MUST include these metadata fields: |
| `IMPORT-decisions-line-15` | partial | medium | The response contract is a strict structured schema (`answer`, `evidence`, `sources`, `confidence`). `formatted_answer`  |
| `IMPORT-decisions-line-24` | partial | medium | Conversation history can contain prompt injection attempts. The system allows using history only to resolve ambiguity (r |
| `IMPORT-decisions-line-31` | partial | medium | The backend, not the LLM, decides what is included in `evidence[]` and `sources[]`. Only retrieved chunks actually used  |
| `IMPORT-decisions-line-47` | partial | medium | Operational logging is useful, but it must never turn into an availability risk. The system schedules logging as a backg |
| `IMPORT-decisions-line-59` | partial | medium | Routing is computed from the **original** user question (not the rewritten question). |
| `IMPORT-decisions-line-68` | partial | medium | All multi-category routing mechanisms are implemented as **general, configurable systems** rather than category-specific |
| `IMPORT-retention-line-13` | partial | medium | Retention model: **rebuild by design**. |
| `IMPORT-retention-line-25` | partial | medium | Raw IP addresses are never stored; only privacy-minimized derived fields. |
| `IMPORT-architecture-line-610` | partial | medium | This system uses **two intentionally different category taxonomies** for different purposes. They must NOT be conflated. |
| `IMPORT-project-ask-about-piotr-demo-scope-problem` | partial | medium | This demo needs an AI assistant that answers only from curated, verifiable knowledge and refuses outside-scope questions |
| `IMPORT-project-ask-about-piotr-demo-scope-tech-stack` | partial | medium | Knowledge base: Markdown cards mounted read-only and ingested into pgvector for retrieval. |

### `IMPORT-readme-line-16`

**Evidence:**

- `backend/tests` (test, supports): Observer or implementation path cited by the harvested doctrine entry exists in the repository.

### `IMPORT-readme-line-17`

**Evidence:**

- `backend/tests` (test, supports): Observer or implementation path cited by the harvested doctrine entry exists in the repository.

### `IMPORT-readme-line-18`

**Evidence:**

- `backend/tests` (test, supports): Observer or implementation path cited by the harvested doctrine entry exists in the repository.

### `IMPORT-readme-line-93`

**Evidence:**

- `backend/tests/test_privacy.py` (test, supports): Observer or implementation path cited by the harvested doctrine entry exists in the repository.

### `IMPORT-readme-line-15`

**Evidence:**

- `backend/app/knowledge.py` (implementation, supports): Observer or implementation path cited by the harvested doctrine entry exists in the repository.

### `IMPORT-readme-line-36`

**Evidence:**

- `backend/app/knowledge.py` (implementation, supports): Observer or implementation path cited by the harvested doctrine entry exists in the repository.

### `IMPORT-decisions-line-15`

**Evidence:**

- `backend/app/schemas.py` (implementation, supports): Observer or implementation path cited by the harvested doctrine entry exists in the repository.

### `IMPORT-decisions-line-24`

**Evidence:**

- `backend/app/llm.py` (implementation, supports): Observer or implementation path cited by the harvested doctrine entry exists in the repository.

### `IMPORT-decisions-line-31`

**Evidence:**

- `backend/app/main.py` (implementation, supports): Observer or implementation path cited by the harvested doctrine entry exists in the repository.

### `IMPORT-decisions-line-47`

**Evidence:**

- `backend/app/interaction_logging.py` (implementation, supports): Observer or implementation path cited by the harvested doctrine entry exists in the repository.

### `IMPORT-decisions-line-59`

**Evidence:**

- `backend/tests` (test, supports): Observer or implementation path cited by the harvested doctrine entry exists in the repository.

### `IMPORT-decisions-line-68`

**Evidence:**

- `backend/app/config.py` (implementation, supports): Observer or implementation path cited by the harvested doctrine entry exists in the repository.

### `IMPORT-retention-line-13`

**Evidence:**

- `backend/scripts/ingest_cards.py` (implementation, supports): Observer or implementation path cited by the harvested doctrine entry exists in the repository.

### `IMPORT-retention-line-25`

**Evidence:**

- `backend/tests/test_privacy.py` (test, supports): Observer or implementation path cited by the harvested doctrine entry exists in the repository.

### `IMPORT-architecture-line-610`

**Evidence:**

- `backend/app/card_category.py` (implementation, supports): Observer or implementation path cited by the harvested doctrine entry exists in the repository.

### `IMPORT-project-ask-about-piotr-demo-scope-problem`

**Evidence:**

- `backend/tests` (test, supports): Observer or implementation path cited by the harvested doctrine entry exists in the repository.

### `IMPORT-project-ask-about-piotr-demo-scope-tech-stack`

**Evidence:**

- `docker-compose.yml` (config, supports): Observer or implementation path cited by the harvested doctrine entry exists in the repository.

## Code-contradicted

_None._

## Partially assessed

| sourceId | scope | confidence | statement (truncated) |
| --- | --- | --- | --- |
| `IMPORT-architecture-line-648` | partial | medium | **Retrieval functions** in [`backend/app/retrieval.py`](backend/app/retrieval.py:1) must NOT filter by routing categorie |

### `IMPORT-architecture-line-648`

**Evidence:**

- `backend/tests` (test, supports): Observer or implementation path cited by the harvested doctrine entry exists in the repository.

## Inconclusive

_None._

## Not assessed

| sourceId | scope | confidence | statement (truncated) |
| --- | --- | --- | --- |
| `IMPORT-readme-line-19` | partial | — | The pipeline is retrieval → synthesis with strict boundaries |
| `IMPORT-readme-line-25` | partial | — | This is not a general-purpose chatbot. |
| `IMPORT-readme-line-27` | partial | — | It does not use the open internet or external search. |
| `IMPORT-readme-line-30` | partial | — | Do not invent metrics, timelines, or scope. |
| `IMPORT-decisions-line-7` | partial | — | Retrieval selects evidence; synthesis produces language. Keeping these stages separate makes failures diagnosable (bad r |
| `IMPORT-migrations-line-7` | partial | — | **No data loss** for existing production DB volumes. |
| `IMPORT-migrations-line-75` | partial | — | Avoid `DROP COLUMN`, `TRUNCATE`, `DELETE`, etc. If you must do a destructive change, create a dedicated migration and do |
| `IMPORT-retention-line-39` | partial | — | Operators should define a retention window and enforce it outside the app (e.g., scheduled job). |
| `IMPORT-skills-programming-languages-scale-and-impact` | partial | — | Languages reflect production systems and long-lived codebases, not only prototypes. |
| `IMPORT-experience-rag-design-principles-my-role` | partial | — | I design RAG and agentic systems with explicit retrieval layers, constrained generation, and clear fallbacks. |
| `IMPORT-experience-rag-design-principles-key-decisions-and-trade-offs` | partial | — | I avoid using LLMs where correctness must be exact and verification is hard (e.g., authorization decisions, financial ca |
| `IMPORT-project-ask-about-piotr-demo-scope-scale-and-impact` | partial | — | The impact is better evaluation: the 100 sample questions can be mapped to specific cards, and out-of-scope questions ca |
| `IMPORT-project-ksa-bed-occupancy-forecasting-problem` | partial | — | Hospitals need reliable short-horizon capacity forecasts at ward level to support operational decision-making. |
| `IMPORT-experience-databases-and-data-modeling-problem` | partial | — | Data-intensive products must balance correctness, performance, and evolution as schemas and features change. |
| `IMPORT-experience-deepseas-securityondemand-anomaly-detection-problem` | partial | — | Systems must be fast, resilient, and cost-effective because latency and false alarms directly impact response workflows. |
| `IMPORT-skills-core-key-decisions-and-trade-offs` | partial | — | Lists only what is explicitly stated in the source documents; does not add “nice-to-have” skills without evidence. |
| `IMPORT-project-hedge-fund-ai-analyst-problem` | partial | — | A useful AI assistant must orchestrate many steps, track progress, and preserve auditability and tenant isolation. |
| `IMPORT-profile-professional-summary-key-decisions-and-trade-offs` | partial | — | Focused on building systems that are reliable in production, measurable, and grounded in empirical evaluation rather tha |

### `IMPORT-readme-line-19`

**Evidence:**

—

### `IMPORT-readme-line-25`

**Evidence:**

—

### `IMPORT-readme-line-27`

**Evidence:**

—

### `IMPORT-readme-line-30`

**Evidence:**

—

### `IMPORT-decisions-line-7`

**Evidence:**

—

### `IMPORT-migrations-line-7`

**Evidence:**

—

### `IMPORT-migrations-line-75`

**Evidence:**

—

### `IMPORT-retention-line-39`

**Evidence:**

—

### `IMPORT-skills-programming-languages-scale-and-impact`

**Evidence:**

—

### `IMPORT-experience-rag-design-principles-my-role`

**Evidence:**

—

### `IMPORT-experience-rag-design-principles-key-decisions-and-trade-offs`

**Evidence:**

—

### `IMPORT-project-ask-about-piotr-demo-scope-scale-and-impact`

**Evidence:**

—

### `IMPORT-project-ksa-bed-occupancy-forecasting-problem`

**Evidence:**

—

### `IMPORT-experience-databases-and-data-modeling-problem`

**Evidence:**

—

### `IMPORT-experience-deepseas-securityondemand-anomaly-detection-problem`

**Evidence:**

—

### `IMPORT-skills-core-key-decisions-and-trade-offs`

**Evidence:**

—

### `IMPORT-project-hedge-fund-ai-analyst-problem`

**Evidence:**

—

### `IMPORT-profile-professional-summary-key-decisions-and-trade-offs`

**Evidence:**

—

