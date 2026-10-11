---
name: decreen-deepen
description: >-
  Deepen a part of an existing persistent Decreen workspace map. Produces a
  decreen.deepen.v1 expansion patch from local code analysis. Requires
  workspaceLifecycle persistent in .decreen/manifest.json. Use when the user
  runs /decreen-deepen or asks to expand/deepen a node or area of the map.
---

# Decreen Deepen

Expand **one area** of an existing **persistent** Decreen workspace map with a structured expansion patch.

**Invariant:** `/decreen-deepen` only operates on persistent Decreen workspaces. Temporary previews are read-only and cannot be deepened.

Contract: [`.decreen/schema/deepen.v1.schema.json`](../../.decreen/schema/deepen.v1.schema.json)

## When to use

- User runs `/decreen-deepen RepoAnalysisWorker`
- User asks to deepen, expand, or add detail to a part of an existing Decreen map
- User has **claimed** their map (persistent workspace)

## Do NOT use when

- No `.decreen/manifest.json` → run [`/decreen-analyze`](../decreen-analyze/SKILL.md) first
- `manifest.decreen.workspaceLifecycle !== "persistent"` → **stop** (see below)
- User only wants a new preview diagram → use `/decreen-analyze`
- User wants full-repo re-analysis → use `/decreen-analyze`, not deepen

## Product flows

```text
Anonymous:
  /decreen-analyze → temporary_preview → viewer link → NO deepen

Authenticated / claimed:
  /decreen-analyze → claim in viewer → manifest workspaceLifecycle: persistent
  /decreen-deepen → (lazy login if needed) → proposal + preview → apply → new KG commit
```

**F7 gate (default):** deepen **proposes** a change; **apply** accepts it as a new graph revision. Do not skip preview unless the proposal is `clean` and the user explicitly asked for auto-apply.

| Mode | When | API |
|------|------|-----|
| **Preview (default)** | Always first | `POST /architecture/deepen/proposals` |
| **Auto-apply** | `status: clean` only | same + `?autoApply=true` |
| **Manual apply** | `review_required` or user choice | `POST .../proposals/:id/apply` |
| **Legacy direct apply** | Avoid unless debugging | `POST /architecture/expand` |

---

## Prerequisites (hard gate)

**Always run Step 0 first** — do not trust a stale local manifest.

**Forbidden (never use as fallback):**

- Do **not** access Decreen backend infrastructure directly (database clients, ORM consoles, auth tables, internal admin APIs).
- Use **only** Decreen HTTP APIs and local repository files (`.decreen/manifest.json`, deepen patches).

---

## Step 0 — Refresh workspace status

Before generating a deepen patch, read `.decreen/manifest.json` and refresh lifecycle from Decreen.

### 0a. Read manifest

Extract `decreen.workspaceId` from `.decreen/manifest.json`.

If manifest is missing → stop: run [`/decreen-analyze`](../decreen-analyze/SKILL.md) first.

### 0b. Public preview status (no auth)

Always call first — detects browser claim without agent session:

```text
GET ${DECREEN_API}/api/v0/local-architecture-preview/{workspaceId}/status
```

No `Authorization` header required. Response contains only lifecycle + URLs (no tenant/user/graph data).

Update `.decreen/manifest.json` `decreen` block from the response.

**If `workspaceLifecycle === "temporary_preview"`** — merge and **stop**:

```json
{
  "decreen": {
    "workspaceLifecycle": "temporary_preview",
    "claimAvailable": true,
    "claimUrl": "<from response>",
    "expiresAt": "<from response>",
    "publicExploreUrl": "<from response>",
    "embedUrl": "<from response>",
    "exploreUrl": "<from response — alias of publicExploreUrl for temporary preview>"
  }
}
```

Do **not** analyze code, do **not** write `.decreen/deepen-runs/`, do **not** POST to `/architecture/deepen/proposals` or `/architecture/expand`.

Show the user `claimUrl` and tell them to claim the map first, then run `/decreen-deepen` again.

**If `workspaceLifecycle === "persistent"`** — merge lifecycle fields:

```json
{
  "decreen": {
    "workspaceLifecycle": "persistent",
    "claimAvailable": false,
    "claimedAt": "<from response if present>",
    "workspaceUrl": "<from response — /w/:id/diagrams?view=facet%3Ac4>",
    "workspaceFocusUrl": null,
    "publicExploreUrl": null
  }
}
```

Remove `claimUrl`, `expiresAt`, and legacy-only `exploreUrl` from manifest if present.

### 0c. Agent auth (required for mutate) — lazy login

Deepen **mutation** requires a valid bearer token. Resolve credentials via shared auth helper:

```bash
npx -y @decreen/local login --if-needed
```

Monorepo / pre-publish:

```bash
node packages/decreen-local/dist/cli.js login --if-needed
```

Or run explicit login first: [`/decreen-login`](../decreen-login/SKILL.md)

Programmatic (agent scripts):

```bash
node -e "
import { ensureAuthenticated } from 'decreen-agent/auth';
const token = await ensureAuthenticated({ onStatus: console.log });
console.log('OK', token.slice(0, 12) + '…');
"
```

**Resolution order** (`ensureAuthenticated`):

1. `DECREEN_AGENT_BEARER_TOKEN` env (if valid via `GET /api/v1/agent/oauth/whoami`)
2. `~/.config/decreen/auth.json` (if valid)
3. **Lazy browser PKCE login** — if workspace is persistent and user has not opted out

**If persistent + no valid credentials**, tell the user and start lazy login:

```text
This map has been claimed and is now persistent.

To deepen it, I need to connect your Decreen account so the agent can update the workspace.

Opening browser login…
```

Run `ensureAuthenticated()` (opens browser → saves credentials → continues).

**Do not** stop with manual `export DECREEN_AGENT_BEARER_TOKEN` unless browser login fails or user declines.

**Do not** auto-claim preview workspaces — if Step 0b is still `temporary_preview`, show `claimUrl` and stop (no login).

After successful login:

```text
Decreen account connected. Continuing /decreen-deepen <target>…
```

Optionally confirm workspace access:

```text
GET ${DECREEN_API}/api/v1/agent/architecture/workspaces/{workspaceId}/status
Authorization: Bearer ${token}
```

### 0e. Resolve live map head (required before patch)

**Default `/decreen-deepen` must anchor on the current map head** — not a recycled SHA from a prior run, manifest, or conversation context.

```text
GET ${DECREEN_API}/api/v1/agent/architecture/workspaces/{workspaceId}/head
Authorization: Bearer ${token}
```

Response:

```json
{ "workspaceId": "...", "commitSha": "<live KG architecture head>", "facetId": "c4" }
```

Set `source.commitSha` in the patch to this value.

**Do not** use `GET /kg/hierarchies/facets` as primary — agent JWT often gets `SESSION_EXPIRED` on workspace session routes. Use the agent `/head` endpoint above (same API host as proposal POST).

**Do not** recycle `commitSha` from:
- a previous deepen run in this chat
- `.decreen/manifest.json` `analysis.lastCommitSha`
- `git rev-parse HEAD`

**Historical parent (advanced only):** if the user explicitly asks to deepen against a specific revision, set `source.commitSha` to that viewable KG commit. Expect proposal finding `source_commit_not_latest` when it differs from live head.

Before POST, log for the user:

```text
Decreen API: ${DECREEN_API}
Workspace: ${workspaceId}
Live map head: ${head.commitSha}
Patch source.commitSha: ${payload.source.commitSha}
Review URL origin: ${frontendOrigin}
```

If `payload.source.commitSha !== head.commitSha` without explicit user request for historical parent → **stop and re-resolve head** before POST.

### 0d. Continue

If Step 0b reports `persistent` **and** `ensureAuthenticated()` succeeded **and** Step 0e head resolved → proceed to target resolution and patch build.

**Why public status first:** User may claim in the browser while local manifest still says `temporary_preview`. Public endpoint resolves that without agent session cookie.

---

## Prerequisites (after Step 0)

1. **`.decreen/manifest.json` exists**
2. **`decreen.workspaceId` is set**
3. **`decreen.workspaceLifecycle === "persistent"`** (confirmed by Step 0 refresh)

If Step 0 reports `temporary_preview`:

**Stop immediately.** Do not generate a patch.

**Hard rule:** If `.decreen/manifest.json` has `workspaceLifecycle = "temporary_preview"`, do not generate a deepen patch. Provide `manifest.decreen.claimUrl`. If `claimUrl` is missing, derive it:

```text
{origin}/claim-preview/{workspaceId}?intent=deepen&next=/w/{workspaceId}/diagrams?view=facet%3Ac4
```

(`origin` = scheme + host from `viewerUrl`; canonical route: [`/claim-preview/:workspaceId`](../../frontend/src/pages/ClaimLocalPreviewPage.tsx))

**Message (English):**

```text
This Decreen map is a temporary preview, so it cannot be deepened yet.

To deepen this map, first claim it as a persistent workspace:

{claimUrl}

Then run:

/decreen-deepen <target>
```

**Message (Polish — use when user writes in Polish):**

```text
Ta mapa Decreen jest tymczasowym preview, więc nie można jej jeszcze pogłębiać.

Żeby pogłębić tę mapę, najpierw zachowaj ją jako trwały workspace:

{claimUrl}

Potem uruchom ponownie:

/decreen-deepen <target>
```

Include repo context when helpful: `manifest.repo.fullName`, `manifest.decreen.workspaceId`.

If manifest is missing:

```text
Run /decreen-analyze first to create a map, then claim it before using /decreen-deepen.
```

---

## v1 target resolution (agent-side only)

Supported:

```text
/decreen-deepen RepoAnalysisWorker
/decreen-deepen backend/src/workers/repoAnalysisWorker.js
/decreen-deepen "repo analysis worker"
```

Not supported in v1:

```text
/decreen-deepen auth flow
/decreen-deepen onboarding capability
```

Algorithm:

1. Read manifest → `workspaceId`, `workspaceUrl` (persistent) or `publicExploreUrl` / `exploreUrl` (preview only)
2. Resolve target via grep, file path, class/module/symbol name
3. Read surrounding files (imports, calls, config, queue bindings, DB access)
4. Build patch — do not invent nodes without code evidence

Optional: MCP `decreen.get_graph` to align `target.nodeId` with canonical map.

---

## Analysis depth (single target)

Three change levels (may combine in one patch):

| Level | Effect |
|-------|--------|
| **L0 refine** | `updateNodes` — description, responsibilities, sourcePaths |
| **L1 decompose** | `addNodes` + `addContainment` — internal children |
| **L2 connect** | `addEdges` — external deps (queues, DB, services) |

Keep patches focused: typically 3–15 new nodes for v1.

---

## Build `decreen.deepen.v1` artifact

Validate against [`.decreen/schema/deepen.v1.schema.json`](../../.decreen/schema/deepen.v1.schema.json).

Required shape — see [`.decreen/examples/deepen.v1.example.json`](../../.decreen/examples/deepen.v1.example.json).

Rules:

- `source.kind` must be `"agent_partial"` (rank 50 — provisional, must not overwrite manual/c4_model)
- **`source.commitSha` must be the live KG architecture head** from the **same API** used for proposal POST
  - **Required:** `GET ${DECREEN_API}/api/v1/agent/architecture/workspaces/{workspaceId}/head` → `commitSha`
  - Fallback (browser session only): `GET ${DECREEN_API}/kg/hierarchies/facets` with workspace auth
  - **Forbidden:** recycling SHA from prior runs, manifest `analysis.lastCommitSha`, or `git rev-parse HEAD`
  - Optional: set `source.gitHeadSha` to Git HEAD for provenance only; expand API maps Git → KG when needed
  - Historical parent: only when user explicitly requests a specific viewable commit
- Every significant `addNodes` entry should have matching `addEvidence` with non-empty `reason`
- Nodes without evidence → set `provisional: true` and `confidence` ≤ 0.6
- `summary.*` counts must match array lengths in `changes`
- `runId`: e.g. `2026-05-26T10-00-00-repo-analysis-worker`

**Forbidden in v1:** `removeNodes`, rename, new workspace, Mermaid output, `POST /api/v0/snapshots`

---

## Output (Sprint 2 — local patch + backend proposal/apply)

Write validated JSON to:

```text
.decreen/deepen-runs/<runId>.json
```

Do **not** commit this directory (gitignored).

When manifest is **persistent** and auth is available (`ensureAuthenticated`), **default to preview** — POST the same payload to:

```text
POST /api/v1/agent/architecture/deepen/proposals
Authorization: Bearer <DECREEN_AGENT_BEARER_TOKEN>
Content-Type: application/json
```

(`DECREEN_AGENT_BEARER_TOKEN` = session JWT or workspace-scoped `sk_…` service key.)

### Proposal response (F7)

Expect **201** with:

```json
{
  "status": "clean" | "review_required",
  "proposalId": "...",
  "parentCommitSha": "...",
  "currentHeadCommitSha": "...",
  "preview": { "addedNodes": 0, "addedEdges": 0, "enrichedNodes": 0 },
  "findings": [{ "severity": "info|warning|blocker", "kind": "...", "message": "..." }]
}
```

Finding `source_commit_not_latest` (warning): proposal parent is viewable but not the current map head — re-run deepen with live head unless historical parent was intentional.

**Default:** stop after preview and show findings to the user. Do **not** auto-apply unless the user explicitly requested it **and** `status === "clean"`.

### Apply paths

| Situation | Action |
|-----------|--------|
| `status: clean` + user asked auto-apply | Re-POST with `?autoApply=true`, or `POST .../proposals/:proposalId/apply` |
| `status: review_required` | Show findings; apply only after user confirms → `POST .../proposals/:proposalId/apply` |
| Re-fetch proposal | `GET .../proposals/:proposalId` |

Apply response (200):

```json
{
  "status": "applied",
  "proposalId": "...",
  "revision": { "previousCommitSha": "...", "newCommitSha": "..." },
  "viewUrl": "..."
}
```

**Legacy (avoid):** `POST /api/v1/agent/architecture/expand` — direct apply without proposal gate.

### Verify ingest (required — do not guess)

After **apply** (not preview-only), confirm all three before telling the user deepen succeeded:

1. **Apply response** — HTTP **200**, body has `status: "applied"` and non-empty `viewUrl` or `workspaceFocusUrl`.
2. **History event** — authenticated GET confirms the run:

```text
GET ${DECREEN_API}/api/workspaces/{workspaceId}/architecture/history?limit=20
Authorization: Bearer ${DECREEN_AGENT_BEARER_TOKEN}
```

Response must contain an item with `kind: "agent_deepen_applied"` and matching `runId`.

3. **Local artifact** — `.decreen/deepen-runs/<runId>.json` exists on disk.

If any check fails, report the failure honestly. Do **not** write “should appear in history”.

If the user only wanted preview (default), report proposal `status`, `findings`, and `preview` counts — do **not** claim the map was updated.

On **apply 200**, update manifest with `workspaceUrl` / `workspaceFocusUrl` from the apply response.

### Map link preference (persistent workspace)

Use **authenticated workspace routes** only — never `/explore/workspace/` for claimed maps:

```text
1. applyResponse.viewUrl || applyResponse.workspaceFocusUrl
2. applyResponse.workspaceUrl
3. manifest.decreen.workspaceFocusUrl
4. manifest.decreen.workspaceUrl
```

Do **not** link users to `/explore/workspace/` or `/embed/explore/` after claim — those are public preview routes.

On **403** `WORKSPACE_NOT_PERSISTENT`, show `error.details.claimUrl` (same as temporary-preview gate above).

On **404** `TARGET_NOT_FOUND`, re-resolve `target.nodeId` via MCP `decreen.get_graph` or fix the URN.

On **422** `EDGE_ENDPOINT_UNRESOLVED`, add missing endpoints as `addNodes`, use `toNodeId`/`fromNodeId`, or reference `"target"`.

If token is missing after Step 0b reports persistent, run **lazy login** (Step 0c) — do not save a patch unless the user explicitly asks for local-only patch without ingest.

---

## Present to user

**After preview (default):**

```text
Deepen proposal: <target.label>
Status: clean | review_required

Preview:
- +N nodes, +M edges, K enriched nodes

Findings:
- (list warnings/blockers, or "none")

Proposal: <proposalId>
Parent revision: <parentCommitSha>
Current map head: <currentHeadCommitSha from response, if present>
Decreen API: <API base used for POST>
Review in map (frontend origin only — NOT ${DECREEN_API}):
  {frontendOrigin}/w/<workspaceId>/diagrams?view=facet:c4&proposalId=<proposalId>
  frontendOrigin = origin from manifest.decreen.workspaceUrl or VITE_BASE_URL (e.g. http://localhost:3000)
Patch saved: .decreen/deepen-runs/<runId>.json

Next: user reviews in Proposal drawer → Apply, or POST .../proposals/<proposalId>/apply when ready
(or re-POST with ?autoApply=true only if status is clean and user asked)
```

**After apply:**

```text
Deepened: <target.label>

Added:
- N internal components / nodes
- M relationships
- K source-backed evidence entries
- Q unresolved questions

Patch saved: .decreen/deepen-runs/<runId>.json
Ingest: confirmed (apply 200 + history event agent_deepen_applied:<runId>)
View updated map: <viewUrl || workspaceFocusUrl from apply response>

If your browser asks you to sign in, log in and you should return to this map.

History: verified via GET /api/workspaces/{id}/architecture/history
```

If patch is empty after analysis, say so honestly and list what was searched.

---

## Bootstrap in a new repository

Install Decreen agent support once (idempotent):

```bash
npx -y @decreen/local init
```

Monorepo / pre-publish:

```bash
node packages/decreen-local/dist/cli.js init
```

This copies skills, schema, examples, and `.gitignore` entries. It does **not** write `manifest.json` or run login.

Then in Cursor: `/decreen-deepen <target>` (lazy login on first mutate if needed).

**Manual fallback** (power users only): copy skill text from this repo into `.cursor/skills/decreen-deepen/SKILL.md`.

---

## After claim (manual fallback)

If public status is unavailable, update manifest per [`.decreen/README.md`](../../.decreen/README.md):

- `workspaceLifecycle`: `"persistent"`
- `claimedAt`, `workspaceUrl` from status/claim response
- `expiresAt`: null, `claimAvailable`: false
- **Remove `claimUrl`**, legacy `exploreUrl` for persistent workspaces

Then `/decreen-deepen` may proceed.

---

## Non-goals (v1)

- No deepen on `temporary_preview`
- No Decreen-side target search API
- No new diagram / snapshot / Mermaid deliverable
- No auto-merge to canonical without backend (Sprint 2)

## Future (Sprint 4+)

- MCP `decreen.deepen` tool
- UI badge / provisional overlay styling for agent-suggested nodes
- Time-travel / delta preview on history event click
