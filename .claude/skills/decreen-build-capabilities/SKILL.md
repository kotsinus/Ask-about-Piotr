---
name: decreen-build-capabilities
description: >-
  Infer and publish a Decreen Capabilities hierarchy facet from the current
  repository and existing Decreen architecture graph context. Produces a
  decreen.capabilities.v1 facet payload — not a new architecture map. Requires
  persistent workspace. Use when the user runs /decreen-build-capabilities,
  /decreen-capabilities, or asks to create/update a product/business
  capabilities view for a Decreen workspace.
---

# Decreen Build Capabilities

Infer a **product/business capabilities** hierarchy facet from the repository and existing Decreen architecture context, then publish it as facet `capabilities`.

**Product framing:**

> Capabilities are inferred groupings over your existing architecture graph. They help explain what the system enables, not just what it contains.

**Aliases:** `/decreen-build-capabilities`, `/decreen-capabilities`

Contract: [`.decreen/schema/capabilities.v1.schema.json`](../../.decreen/schema/capabilities.v1.schema.json)

**Follow Step 0 throughout this skill.**

## Step 0: User-facing output contract

Before plan / inference:

`Inferring capabilities…`

Before publish:

`Publishing capabilities facet…`

Do not narrate internal steps, pre-flight gates, manifest refresh, head resolution, artifact paths, schema validation, reading this skill, or API host diagnostics.

On success after **plan**, use [Plan output style](#plan-output-style).

On success after **publish**, use [Publish output style](#publish-output-style).

On failure or partial success:

- do not use success templates
- short problem statement and one next action only
- include **Debug details** only when:
  - capabilities could not proceed
  - the user asks
  - `DECREEN_DEBUG=1`
  - `--verbose`

---

## Naming disambiguation (read first)

| Term | Meaning |
|------|---------|
| **Capabilities facet** (`facet:capabilities`) | Product/business ability groupings over the architecture graph — **this skill** |
| `.decreen/capabilities/` | Agent operational index (choke points) — **not** this skill |
| `decreen.architecture.patch.v1` → `capabilities[]` | Flat local-analyze heuristic in public beta CLI — **different shape**; do not reuse |

---

## When to use

- User runs `/decreen-build-capabilities` or `/decreen-capabilities`
- User asks to create, update, infer, or publish a product/business capabilities map
- User has a **claimed persistent** Decreen workspace with an existing `c4` architecture map

## Do NOT use when

- No `.decreen/manifest.json` → run [`/decreen-preview`](../decreen-preview/SKILL.md) first
- `manifest.decreen.workspaceLifecycle !== "persistent"` → stop (preview cannot publish facets)
- User only wants a new architecture map → use `/decreen-preview` or `/decreen-update`
- User wants to register a code choke point → use [`/register-capability`](../register-capability/SKILL.md)

## Mental model

```text
Architecture facet (c4):
  What components exist?

Capabilities facet (capabilities):
  What product/business abilities do those components support?

Four orthogonal axes (capabilities v2):
  Capability     = meaning / what the system can do
  Value stream   = behavior / ordered flow that exercises capabilities
  Realization    = code / where ability lives (architecture node_ids)
  Invariant      = semantic guard / what must remain true (proposed laws)

Invariants are NOT zoomLevel 3. After plan + expand, run
[/decreen-suggest-invariants](../decreen-suggest-invariants/SKILL.md) for selective law proposals.
```

This skill must **not** replace or mutate the `c4` facet. It adds an alternate hierarchy over the same KG nodes.

## Product flows

```text
/decreen-preview → claim → persistent workspace
  → decreen setup (optional grounding)
  → /decreen-build-capabilities plan    → local proposal
  → user reviews capability names
  → /decreen-build-capabilities publish → facet persisted at new KG commit
  → open ?view=facet:capabilities
```

**Re-run:** After major `/decreen-update` changes, re-run this skill. Refresh materializes `c4` only; it does not rebuild capabilities.

---

## Modes

| Mode | Command | Effect |
|------|---------|--------|
| **plan** (default) | `/decreen-build-capabilities plan` or `/decreen-build-capabilities` | Infer + write local proposal only |
| **expand** | `/decreen-build-capabilities expand <capability-id>` or `rozwiń <capability-id>` | Decompose one capability into sub-capabilities (meaning axis only) |
| **publish** | `/decreen-build-capabilities publish` | Validate + persist facet (requires prior plan or inline inference) |

**Default:** `plan` — capability naming is subjective; show the proposal before publish.

**Expand (rozwiń):** One capability at a time. Requires existing proposal at `.decreen/analysis/latest.capabilities-proposal.json`. Writes `.decreen/analysis/expansions/<slug>.expansion.json`. Contract: [`.decreen/schema/capability-expansion.v1.schema.json`](../../.decreen/schema/capability-expansion.v1.schema.json)

**Fast path (beta):** If the user explicitly says "publish without review" and confidence is decent, run plan + publish in one turn.

---

## Expand mode (rozwiń)

Decide whether **one** capability has a legitimate third level — and only emit sub-capabilities if it does.

Before expand, say only:

`Expanding capability…`

### The default answer is "this is a leaf"

Most capabilities do **not** have a real third level. The third level is squeezed
between two adjacent axes and collapses toward whichever is nearer:

- **Collapses down → code/mechanism.** Sub-capabilities become 1:1 relabels of files
  (e.g. "Resolve Edge Geometry Fallbacks" ≈ `edgeGeometryResolver.ts`). Dead weight —
  the realization edges already say this.
- **Collapses sideways → value stream.** Sub-capabilities form an ordered pipeline
  (detect → build → generate → submit → apply). That is the **behavioral axis**, not a
  structural decomposition.

So expand must **justify** a third level, not assume one. Three outcomes:

| Outcome | When | Emit |
|---------|------|------|
| **leaf** | No abilities survive both tests below | `verdict: "leaf"`, no sub-capabilities; route mechanisms to `realizationHints` on the parent |
| **subcapabilities** | ≥2 genuine abilities survive | `subCapabilities[]` (leaves) |
| **value-stream-candidate** | Candidates form an ordered stage sequence | `valueStreamCandidate` (steps), NOT sub-capabilities |

### Two rejection axes (both must pass to be a sub-capability)

**Axis 1 — refactor-survival (vs. code).** Replaces the old "non-engineer" test, which is
useless when the users are engineers.

> Would this name survive rewriting the implementation?

A real ability persists through a rewrite. A mechanism is named after the current code and
dies with it.

| Survives rewrite (ability) | Dies with refactor (mechanism → realization) |
|---|---|
| "Route Cross-Boundary Edges" | "Resolve Edge Geometry Fallbacks" (named after the fallback cascade) |
| "Route Same-Space Edges" | "Schedule Layout After Graph Changes" (named after orchestration timing) |
| | "Apply flat-intent deflection", "NETWORK_SIMPLEX placement" |

**Axis 2 — not-a-pipeline-stage (vs. value stream).**

> Do the candidates form an ordered sequence (verb the system does *in order*)?

If the set reads as detect → … → apply, or mirrors the `propose → review → apply`
machinery, it is a **value stream**, not a decomposition. Tell: candidate sets across two
capabilities come out near-parallel (Refresh `detect/build/generate/submit/apply` ≈ Deepen
`resolve/scope/propose/submit/apply`) — that is one stream pattern showing up twice.

Stage-shaped candidates ("Submit Proposal", "Apply Approved …") are **stream steps**; the
capability stays a thin leaf the stream draws on.

Record axis-1 failures in `rejectedAsMechanism[]` and axis-2 outcomes in
`valueStreamCandidate`. Never keep them as sub-capabilities.

### Realization hints must resolve to node ids

`realizationHints` are an **intermediate stage only**. A file path cannot detect capability
drift on refresh — it silently diverges from what the architecture facet calls that node.

- Each hint is `{ "path": "…", "nodeId": "…" | null, "status": "resolved" | "provisional" }`.
- `provisional` until resolved to an **architecture-facet `node_id` (URN)** via the KG graph
  (same source as `plan` step e). Unresolved hints do not count toward realization.
- Ground hints to the **primary** implementation, not the legacy fallback. (E.g. cross-boundary
  routing lives in `lib/emergentHighways/` + `lib/purePipeline/` corridor code, **not**
  `crossContainerRouting.ts`, which is the LCA fallback.) Verify the path exists before citing it.

### Expand output

Write `.decreen/analysis/expansions/<parent-slug>.expansion.json`:

```json
{
  "kind": "decreen.capability-expansion.v1",
  "parentCapabilityId": "capability:architecture-visualization-layout-routing",
  "parentLabel": "Layout & Routing",
  "domainId": "capability:architecture-visualization",
  "verdict": "leaf",
  "subCapabilities": [],
  "valueStreamCandidate": null,
  "realizationHints": [
    { "path": "frontend/src/features/diagrams/lib/emergentHighways/buildEmergentHighwaysRoutes.ts", "nodeId": null, "status": "provisional" }
  ],
  "rejectedAsMechanism": [
    { "phrase": "Resolve Edge Geometry Fallbacks", "reason": "Named after the fallback cascade; dies on refactor" }
  ]
}
```

### Expand output style

Three shapes, one per verdict:

```text
Capability expanded: Layout & Routing
Verdict: subcapabilities (mixed — kept the routing distinctions, demoted the mechanisms)

Kept (survive a rewrite):
- Route Same-Space Edges
- Route Cross-Boundary Edges
- Compute Hierarchical Layout (borderline)

Demoted to realization (die on refactor):
- Resolve Edge Geometry Fallbacks
- Schedule Layout After Graph Changes
```

```text
Capability expanded: Map Refresh
Verdict: value-stream-candidate (ordered pipeline, not a decomposition)

Stream "Refresh Loop": detect → build context → generate → submit → apply → sync
Capability stays a thin leaf the stream draws on.
```

```text
Capability expanded: <X>
Verdict: leaf (rich realization, no honest third level)
Demoted to realization: <…>
```

Do not publish from expand mode. Do not add implementation file names as sub-capability labels.

---

## Pre-flight (hard gate)

**Authoritative preflight (DECREEN-GIT-CLEAN-1)** — before writing capabilities artifacts:

```bash
npx -y @decreen/demo@pilot preflight --authoritative
```

**Do not use `git status --porcelain` as the gate.** Strict porcelain empty is wrong here — Decreen excludes setup/bootstrap paths from the authoritative check.

Requires **committed application source @ HEAD**. Decreen setup files do **not** count as dirty:

- `.cursor/skills/decreen-*`, `.kilo/skills/decreen-*`, `.kilo/command/decreen-*`, `.claude/skills/decreen-*`
- `.decreen/schema/`, `.decreen/scripts/`, `.decreen/demo/`, `.decreen/fixtures/`, example manifests, **`.gitignore`** (Decreen block from `decreen setup`)

If `decreen preflight --authoritative` exits **0** → proceed (even when `git status` shows bootstrap-only paths like ` M .gitignore`).

If it exits **non-zero** with **source** changes → **STOP** (same message as `/decreen-preview`):

```text
STOP — working tree is not clean.

Decreen artifacts must describe a committed repository state.
There are pending changes:
- backend/src/app.js
Commit, stash, or discard these changes, then rerun.
```

Do **not** tell the user to commit `.gitignore` when preflight passes and only bootstrap paths are dirty.

### Agent HTTP error shapes (read before retrying)

| Body shape | Meaning | Agent action |
|------------|---------|--------------|
| `{ code: "BROWSER_SESSION_REQUIRED", error: "Authentication required" }` (no `debug`) | Hit **session** middleware (`requireAuth` on `/kg/*`) or wrong HTTP method on agent routes | Use **POST** agent graph (below); never `/kg/hierarchies/*` |
| `{ code: "TENANT_UNRESOLVED", message: "...", debug: { hasUser, path } }` | **`enforceTenant`** — Bearer missing/invalid | Re-read token; verify `Authorization: Bearer` on POST |
| `{ error: { code: "UNAUTHENTICATED", message } }` | **`agentAuth`** gate | Run `decreen login`; refresh token |
| HTTP 404/405 on `/api/v1/agent/architecture/graph` | Wrong method (GET) or path | Agent graph is **POST-only** — use `decreen capabilities plan` |
| `decreen capabilities plan --json` → `error.code` | CLI mapped API/auth failure | Read `error.hint`; do not hand-curl unless debugging |

Reuse the deepen pre-flight pattern. **Always refresh workspace status** — do not trust a stale manifest.

**Forbidden for agent flows:**

- `GET /kg/hierarchies/*` (browser session routes — agent JWT never works)
- `git status --porcelain` as preflight gate
- Hand-curling agent graph/head when `decreen capabilities plan` is available
- Do **not** access Decreen backend infrastructure directly (database, ORM, admin APIs)

### a–e. Prepare architecture context (CLI — authoritative)

Run the capabilities plan prepare command (handles manifest, auth, head, graph, G0 fallback):

```bash
npx -y @decreen/demo@pilot capabilities plan
```


```bash
npx -y @decreen/demo@pilot capabilities plan --json
```

| Exit / `error.code` | Meaning | Agent action |
|---------------------|---------|--------------|
| `preview_not_claimed` | Temporary preview workspace | Show claim URL; stop |
| `auth_required` / `auth_invalid` | Missing or invalid Bearer | Run `decreen login` |
| `graph_unavailable` | No URNs from API or G0 | Retry with `--provisional-ok` for provisional scaffold only |
| `wrong_route` / `wrong_http_method` | Stale skill or debug curl mistake | Use CLI, not `/kg/*` or GET graph |

**Artifacts written by prepare:**

| Artifact | Path |
|----------|------|
| Agent prompt | `.decreen/runs/latest.capabilities-agent-prompt.md` |
| Context (graph index) | `.decreen/runs/latest.capabilities-context.json` |
| Agent draft scaffold | `.decreen/capabilities-runs/{runId}.agent-draft.json` |
| Prepare summary | `.decreen/runs/latest.capabilities-prepare-summary.json` |

- `source.commitSha` is prefilled from live `/head` in the scaffold — do not replace with `git rev-parse HEAD`.
- Graph loading tries `at: head` then `at: baseline`; G0 fallback reads `.decreen/runs/latest.refresh-context.json` when API returns no URNs.
- **Membership `nodeId` must be an existing KG `node_id` (URN)** — e.g. `urn:decreen:c4:…`. Do **not** use `c4-sg:*` render slugs.

**Debugging only** (when CLI is unavailable): POST agent graph with `{ repo, workspace_id, format:"full", at:"baseline" }` — never GET, never `/kg/hierarchies/*`.

---

## Inference task (agent reasoning — not keyword rules)

Infer a small, useful set of **product/business capabilities** from:

- Architecture map nodes (labels, types, containers)
- Repo structure (packages, modules, services)
- Route/API names
- README/docs
- Domain language in code
- `.decreen/` artifacts (manifest, source-evidence, refresh-evidence)
- Queue/job/worker names
- Integration names

**Do not** classify by keyword tables or hardcoded domain lists. Reason from evidence.

### Good capability examples

- User Authentication
- Workspace Management
- Architecture Analysis
- Change History
- Collaboration
- Billing & Subscription
- Admin Operations
- External Integrations

### Bad capability examples (implementation elements — not capabilities)

- `auth-service`, `BillingController`, `Postgres`, `src/routes/users.ts`, `POST /api/login`

Those may be **members** of a capability, not capability names.

### Hierarchy shape (v1.1)

Two-level capability tree:

```text
Capabilities (capability:root, zoomLevel 0)
  Capability domain (zoomLevel 1, kind: capability)
    Sub-capability (zoomLevel 2, kind: subcapability)
```

| Level | zoomLevel | kind | Purpose |
|-------|-----------|------|---------|
| Root | 0 | `capability` | Facet entry |
| Domain | 1 | `capability` | Broad product/business area (5–12 domains) |
| Sub-capability | 2 | `subcapability` | Specific ability within a domain (2–8 per domain) |

**v1.1 rules:**

- For each **high** or **medium** confidence domain, infer **2–8 sub-capabilities**.
- Sub-capabilities must be **product/business abilities**, not file names, services, routes, or implementation artifacts.
- Keep `capability:uncategorized` flat (no sub-capabilities) unless the repo clearly needs infrastructure buckets.
- Use **zoomLevel 3** (operations/workflows) only when the repo has stable, readable workflows — otherwise stop at zoomLevel 2.
- Do **not** create code/file/function hierarchy under capabilities. Implementation artifacts belong in **memberships** and `evidence`, not as child nodes.

**Stable ids:** `capability:{domain-slug}-{subcap-slug}` — lowercase kebab-case, hyphen-separated (no dots).

**Internal C4 analogue (do not use in product copy):**

```text
zoomLevel 1 ≈ capability domains (navigable buckets)
zoomLevel 2 ≈ sub-capabilities (where meaning lives)
memberships ≈ realization layer (existing KG nodes)
```

### Membership rules

- Attach existing KG nodes primarily to **zoomLevel 2 sub-capabilities**, not only to domains.
- Assignment priority:
  1. Most specific matching sub-capability (preferred)
  2. zoomLevel 1 domain only if no sub-capability fits
  3. `capability:uncategorized` if evidence is weak
- Never attach memberships to `capability:root`.
- Preferred role: `implements`
- Acceptable: `supports`, `exposes`, `uses_data`, `enables`
- Do **not** duplicate KG nodes.
- Do **not** invent implementation nodes absent from the graph.
- If repo evidence exists but no graph node → note in `evidence`; do not create unsupported memberships.

**Hierarchy `evidence[]`** — why this capability/sub-capability exists (docs, routes, packages).  
**Membership `evidence[]`** — why this KG node realizes it (label match, container, role).

### Confidence

Per capability and membership:

- `high` — multiple implementation elements support it
- `medium` — some evidence
- `low` — weak / naming-only inference

Do not overstate certainty. Route unclear nodes to `capability:uncategorized` or `capability:supporting-platform`.

---

## Plan mode

After pre-flight:

1. Run prepare:

```bash
npx -y @decreen/demo@pilot capabilities plan
```

2. Read `.decreen/runs/latest.capabilities-agent-prompt.md` and the agent draft scaffold from prepare summary.
3. Complete inference (see [Inference task](#inference-task-agent-reasoning--not-keyword-rules)).
4. Validate against [Validation](#validation).
5. Write local artifacts:

| Artifact | Path |
|----------|------|
| Proposal | `.decreen/analysis/latest.capabilities-proposal.json` |
| Summary | `.decreen/runs/latest.capabilities-run-summary.json` |

6. Present [Plan output style](#plan-output-style) to the user.
7. Run validate; ask for confirmation before publish (unless user already requested publish):

```bash
npx -y @decreen/demo@pilot capabilities validate
```

If prepare reported `provisionalAllowed: true`, use provisional memberships and **do not publish**.

### Plan output style

```text
Capabilities proposal

Domains (12) · Sub-capabilities (68)

- Identity & Access — 5 sub-capabilities (high)
  - Authentication, Authorization & Permissions, …
- Architecture Analysis & Map Evolution — 9 sub-capabilities (high)
  - Local Preview Generation, Map Refresh, Deepen Proposals, …

Uncategorized KG nodes: 48

Saved: .decreen/analysis/latest.capabilities-proposal.json

Reply **publish** to persist this facet. This will not change the c4 architecture map.
```

---

## Publish mode

Prerequisites:

- Valid proposal at `.decreen/analysis/latest.capabilities-proposal.json`
- Pre-flight passed; `source.commitSha` matches live head (unless `--allow-stale-head`)
- Run validate first (recommended)

Steps:

1. Validate:

```bash
npx -y @decreen/demo@pilot capabilities validate
```

2. Publish:

```bash
npx -y @decreen/demo@pilot capabilities publish
```


Apply semantics (mirror deepen):

- `copyParentHierarchyState` — preserve all existing facets including `c4`
- Copy parent node/edge facts unchanged to the new KG commit (required for membership rendering)
- Upsert/replace only `facet_id = 'capabilities'` at new KG commit
- Never remove or replace `c4` hierarchy data
- Append `agent_capabilities_applied` history event (empty graph delta; facet-only KG commit)

**Debugging only:** raw POST to `/api/v1/agent/architecture/capabilities/proposals` when CLI unavailable.

### Publish output style

```text
Capabilities facet created

Capabilities:
- Identity & Access — 4 supporting nodes
- Architecture Analysis — 6 supporting nodes
- Workspace Management — 3 supporting nodes

Uncategorized:
- 5 nodes

Open in Decreen:
?view=facet:capabilities

Notes:
- Low-confidence capability: Uncategorized / Supporting Platform
- Some nodes could not be confidently assigned
```

---

## Output requirements

Produce `decreen.capabilities.v1` JSON:

```json
{
  "kind": "decreen.capabilities.v1",
  "workspaceId": "<from manifest>",
  "runId": "<ISO timestamp>-capabilities",
  "source": {
    "kind": "agent_partial",
    "commitSha": "<from agent /head>"
  },
  "facets": [
    {
      "id": "capabilities",
      "label": "Capabilities",
      "description": "Product and business capabilities inferred from repository structure and Decreen architecture context.",
      "rootIds": ["capability:root"],
      "nodes": []
    }
  ],
  "memberships": [],
  "summary": {
    "domainCount": 0,
    "subCapabilityCount": 0,
    "membershipCount": 0,
    "uncategorizedNodeCount": 0,
    "lowConfidenceCapabilities": []
  }
```

### Hierarchy node requirements

| Field | Rule |
|-------|------|
| `id` | Stable; `capability:` prefix; lowercase kebab-case hyphens |
| root | Exactly `capability:root`; `parentId: null`; `zoomLevel: 0`; `kind: capability` |
| domain | `parentId: "capability:root"`; `zoomLevel: 1`; `kind: capability` |
| sub-capability | `parentId: domain id`; `zoomLevel: 2`; `kind: subcapability` |
| `label` | Human-readable product/business name |

Example domain:

```json
{
  "id": "capability:architecture-analysis",
  "label": "Architecture Analysis & Map Evolution",
  "parentId": "capability:root",
  "zoomLevel": 1,
  "kind": "capability"
}
```

Example sub-capability:

```json
{
  "id": "capability:architecture-analysis-map-refresh",
  "label": "Map Refresh",
  "parentId": "capability:architecture-analysis",
  "zoomLevel": 2,
  "kind": "subcapability",
  "description": "Updates an existing architecture map from repository changes and publishes a new version.",
  "confidence": "high",
  "evidence": [".cursor/skills/decreen-update", "applyRefreshRevisionFusion.js"]
}
```

Example membership (prefer zoomLevel 2 target):

```json
{
  "facetId": "capabilities",
  "hierNodeId": "capability:architecture-analysis-map-refresh",
  "nodeId": "urn:decreen:c4:repo:component:refresh_service",
  "role": "implements",
  "confidence": "high",
  "evidence": ["Node label references refresh", "Agent refresh proposal route"]
}
```

Golden example: [`.decreen/examples/capabilities.v1.example.json`](../../.decreen/examples/capabilities.v1.example.json)

---

## Validation

Before plan save or publish:

- [ ] `kind` is `decreen.capabilities.v1`
- [ ] `facets` has exactly one entry with `id: "capabilities"`
- [ ] `rootIds` is exactly `["capability:root"]`
- [ ] Root node `capability:root` exists with `parentId: null`, `zoomLevel: 0`
- [ ] Domain nodes have `zoomLevel: 1`, `kind: capability`, `parentId: capability:root`
- [ ] Sub-capability nodes have `zoomLevel: 2`, `kind: subcapability`, valid domain `parentId`
- [ ] High/medium domains have 2–8 sub-capabilities each
- [ ] Every non-root node has valid `parentId` pointing to an existing hierarchy node
- [ ] No duplicate hierarchy node ids
- [ ] Every membership has `facetId: "capabilities"`
- [ ] Memberships target zoomLevel 2 sub-capabilities when possible (not only domains)
- [ ] Every membership `nodeId` exists in the KG graph at `source.commitSha`
- [ ] No duplicate memberships (`hierNodeId` + `nodeId` + `role`)
- [ ] Domain count is 5–12 (excluding root; uncategorized bucket is ok)
- [ ] No implementation file/service names as sub-capability labels
- [ ] No `c4` facet data in this payload

Optional schema check (also run via `decreen capabilities validate`):

```bash
npx -y @decreen/demo@pilot capabilities validate
```

---

## Privacy and upload scope

**Uploaded (publish only):** capabilities facet payload (hierarchy nodes + memberships metadata)

**Not uploaded:** source code, `.env`, credentials, full repo tree

Prefer local analysis and existing Decreen artifacts. Same privacy posture as deepen/refresh.

---

## Related skills

| Situation | Use |
|-----------|-----|
| No map yet | [`/decreen-preview`](../decreen-preview/SKILL.md) |
| Check workspace state | [`/decreen-status`](../decreen-status/SKILL.md) |
| Update architecture map | [`/decreen-update`](../decreen-update/SKILL.md) |
| Expand one area | [`/decreen-deepen`](../decreen-deepen/SKILL.md) |
| Register code choke point | [`/register-capability`](../register-capability/SKILL.md) |

---

## Implementation status (v1)

| Piece | Status |
|-------|--------|
| Expand mode (rozwiń) + capability-expansion schema | **This skill** |
| Invariants suggest (`/decreen-suggest-invariants`) | **Separate skill** — semantic guard layer |
| Read path (`GET /kg/hierarchies/capabilities/*`) | Exists when facet is persisted |
| Publish API (`POST .../capabilities/proposals`) | **Shipped** |
| Plan CLI (`decreen capabilities plan`) | **Shipped** |
| Validate CLI (`decreen capabilities validate`) | **Shipped** |
| Publish CLI (`decreen capabilities publish`) | **Shipped** |

Agents may run **publish** when pre-flight passes and the user confirms (or explicitly requests publish without review).
