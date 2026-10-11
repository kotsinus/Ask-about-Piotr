---
name: decreen-refresh
description: >-
  Refresh an existing Decreen workspace architecture map from the current local
  repo using the server C4 prompt contract (c4prompt-incremental / c4prompt).
  Requires persistent workspace, .decreen/manifest.json, and decreen refresh
  context. Use when the user runs /decreen-refresh or asks to update the whole
  map from local code — not for first-time preview (analyze2) or single-node
  deepen.
---

# Decreen Refresh

Re-analyze the **connected workspace map** from your **local repo** using the same C4 contract as server **Re-analyze repository** — but executed in your coding agent.

```text
decreen refresh ≠ analyze2
decreen refresh = local version of server re-analyze
```

## When to use

- Workspace is already **persistent** (claimed)
- User runs `/decreen-refresh` or `decreen refresh`
- User wants a **whole-map update**, not single-node deepen

## When NOT to use

| Situation | Use instead |
|-----------|-------------|
| No manifest / unclaimed preview | `/decreen-analyze2` + claim |
| Source grounding / CGC plumbing | `/decreen-finalize` |
| Expand one node | `decreen deepen run <targetId>` |
| Server-side re-analyze on GitHub mirror | Dev panel **Re-analyze repository** |

## Prerequisites

```bash
decreen refresh --local-only    # writes .decreen/runs/latest.refresh-context.json
```

Requires auth for G0 fetch: `npx -y @decreen/local login` or `DECREEN_AGENT_BEARER_TOKEN`.

## Flow

```text
1. decreen refresh --local-only
   → fetch G0 + parent KG commit from workspace API
   → compute local git delta metadata
   → write latest.refresh-context.json

2. Agent runs C4 prompt (THIS SKILL)
   → docs/c4prompt-incremental.md + G0 + code delta  (default)
   → docs/c4prompt.md fallback when mode=cold
   → output: docs/c4-architecture.mermaid.md (+ c4-events.ndjson siblings)

3. decreen refresh --upload
   → POST workspace refresh (Mermaid → KG publish)
   → print workspace URL
```

## Step 1 — Read refresh context

Read `.decreen/runs/latest.refresh-context.json` if present. Otherwise run:

```bash
decreen refresh --local-only
```

Fields:

| Field | Use |
|-------|-----|
| `mode` | `incremental` → c4prompt-incremental; `cold` → c4prompt |
| `priorGraph` | G0 carry-forward baseline (incremental) |
| `delta` | Local git name-status since base SHA |
| `parentKgCommitSha` | Current map head |
| `promptFiles` | Paths to prompt templates |

## Step 2 — Run the C4 prompt

**Incremental (default):** read `docs/c4prompt-incremental.md` from this repository (Decreen product repo) or equivalent path in your checkout.

Inject after the prompt template:

```markdown
--- PRIOR GRAPH (G0) ---
<paste priorGraph JSON from refresh context>

--- CODE DELTA (S0_git → C) ---
<paste delta.files from refresh context>
Base: {fromSha}
Head: {toSha}
```

**Cold fallback:** read `docs/c4prompt.md` when `mode=cold` or no G0.

Follow the prompt exactly:

- Write-first, stream-first discipline
- Output files: `docs/c4-events.ndjson`, `docs/c4-live.mermaid.md`, `docs/c4-architecture.mermaid.md`, `docs/c4-partial.ndjson`
- Final artifact for upload: **`docs/c4-architecture.mermaid.md`**

Do **not** use `/decreen-analyze2` preview flow or `/from-mermaid` for refresh.

## Step 3 — Upload

```bash
decreen refresh --upload
```

Publishes Mermaid into the **existing workspace** (new KG revision). Browser shows update/reconciliation flow — **not** a deepen proposal pill.

## CLI reference

```bash
decreen refresh --local-only
decreen refresh --upload
decreen refresh --cold
decreen refresh --from <sha> --to HEAD
decreen refresh --json
```

## Product verbs

```text
init/analyze2  → first map (preview)
finalize       → source-ground repo
deepen         → one node
refresh        → whole map from local repo
```

## Related

- [`docs/c4prompt-incremental.md`](../../docs/c4prompt-incremental.md)
- [`docs/c4prompt.md`](../../docs/c4prompt.md)
- [`/decreen-finalize`](decreen-finalize/SKILL.md)
- [`/decreen-analyze2`](decreen-analyze2/SKILL.md)
