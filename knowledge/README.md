# Knowledge Base

This directory contains curated knowledge cards.
Knowledge cards are the only source of truth used by the AI system.
Source documents (CV, PDFs, certificates) stored in `assets/` are not
ingested directly and serve only as reference material.

## Directory contents
- Cards live in `knowledge/cards/` (one Markdown file per card).
- [`knowledge/CARD_REGISTRY.md`](knowledge/CARD_REGISTRY.md) is the canonical list of card IDs → file paths.
- [`knowledge/KNOWLEDGE_INDEX.md`](knowledge/KNOWLEDGE_INDEX.md) maps the demo question set to cards that provide evidence.
- [`knowledge/sample_questions.md`](knowledge/sample_questions.md) contains the demo questions.

## Knowledge Card Schema (Required)
Each card is a standalone Markdown file that MUST include the following sections
in this exact order and with these exact headings.

1. Title
2. Category (profile | project | research | certification | experience)
3. Problem
4. My role
5. What I built
6. Scale and impact
7. Tech stack
8. Key decisions and trade-offs
9. Links (URL or file reference)

## Authoring Guidelines
- Use concise, factual statements; avoid opinions unless explicitly supported.
- Do not invent metrics, timelines, or scope.
- Each section should be 1–6 sentences maximum.
- Cards should describe a single, well-defined scope (one project, role, or credential).
- Links SHOULD preferentially reference files in `assets/` or authoritative external URLs.

## Chunking and Metadata Model
When cards are chunked, each chunk MUST include these metadata fields:

- `card_id`: stable identifier derived from the filename (e.g., `project-ml-platform`).
- `category`: one of `profile | project | research | certification | experience`.
- `section`: exact section heading from the schema (e.g., `Tech stack`).
- `source_url`: URL or file reference from the Links section (if present).

## Example Card Template
```md
# Title
<short title>

# Category
project

# Problem
<what problem was solved>

# My role
<your responsibilities>

# What I built
<systems, features, or artifacts>

# Scale and impact
<scope, usage context, or operational impact>

# Tech stack
<languages, frameworks, infra>

# Key decisions and trade-offs
<notable architectural or design choices>

# Links
<URL or file reference>
```

