---
name: decreen-judge-pr
description: >-
  Customer-side agentic invariant judge for a git diff. Decreen prepares local
  routing/hydration bundle from invariants index; the customer's agent runtime
  (Cursor/CLI) emits verdicts. Not a Decreen-hosted PR review bot. Pilot:
  flag-only, never blocking. Use for /decreen-judge-PR, /decreen-judge-pr, or
  reviewing a diff against architectural laws.
disable-model-invocation: true
---

# decreen-judge-PR — customer-side agentic invariant judge

> **Decreen makes your agents and humans review against the same invariants.**

Decreen **does not** send diffs to a cloud reviewer. Decreen **does not** operate as an AI PR review bot.

Decreen supplies **local artifacts and contracts** in the customer repo:

- invariants index (routing metadata)
- `sourceRef` hydration
- observer metadata
- event log schema
- prepare-only bundle format
- verdict taxonomy
- this skill (instructions for the customer's agent)

**Judgment runs on the customer side** — their agent runtime, their repo, their permissions.

**Aliases:** `/decreen-judge-PR` (primary), `/decreen-judge-pr`, `/decreen-judge`

**Follow Step 0 throughout this skill.**

## Step 0: User-facing output contract

Before prepare:

`Preparing judge bundle…`

After agent judgment + apply:

```text
Prepared: N laws routed → judged → M events logged
  violated: 0  touched: 2  not-applicable: 5  cannot-judge: 1  orphan: 0
Log: .decreen/analysis/invariants-event-log.jsonl
Pilot: non-blocking
```

On failure: short problem + one next action.

---

## What Decreen is / is not

| Decreen is | Decreen is not |
|---|---|
| Local doctrine packaging | Hosted PR review service |
| Index + bundle + schemas | Another AI bot commenting on PRs |
| Arming the customer's existing agent | Sending diffs to Decreen cloud |
| Flag-only pilot telemetry | Blocking merge gates (ever, in pilot) |

Structural checks expressible as lint belong in **Phase 4 generated observers**, not this backstop.

## Pilot policy (non-negotiable)

| Context | Allowed |
|---|---|
| Client pilot | Flag + markdown report + **local** JSONL log |
| Client pilot | **Never** blocking CI / merge gate |
| carto_prototype dogfood | Same |

## Prerequisites

- [`.decreen/analysis/latest.invariants-index.json`](../../.decreen/analysis/latest.invariants-index.json)
- Git diff (`--base` / `--head`)
- **`--repo-root`** — worktree where `sourceRef` hydrates (required for fork/backtest)
- **Clean working tree (DECREEN-GIT-CLEAN-1)** for prepare — run `decreen preflight --authoritative` before bundle generation

**Index bit semantics (do not conflate):**

- `observed: yes` = named observer path exists on disk — not code truth
- `codeSupported: yes` = code assessment projected `supported` + `scope: full` @ current HEAD — not test passing
- `codeSupported: unknown` → flag-only "needs verification"; do not infer from `observed`
- `trueInCode` in index JSON/CSV is a **deprecated alias** of `codeSupported` (one release)

## Workflow position

```text
/decreen-index  →  /decreen-judge-PR prepare  →  agent judges  →  judge apply
                         ↑ optional layers doc for discussion framing
```

Full change loop: [`invariants-change-flow.md`](../../docs/engineering/invariants-layers/invariants-change-flow.md)

---

## Workflow

### Step 0 — Index present (if stale or missing)

If [`.decreen/analysis/latest.invariants-index.json`](../../.decreen/analysis/latest.invariants-index.json) is missing or older than inventory, run [`/decreen-index`](../decreen-index/SKILL.md) first — do not call `bootstrap-invariants-index.mjs` or `decreen index bootstrap` directly unless debugging.

**Prepare preflight:** run `decreen preflight --authoritative` only — **do not** use `git status --porcelain` as the gate. Bootstrap paths (including `.gitignore` from setup) are excluded. Proceed when preflight exits 0; STOP only on non-zero with blocking source paths.


### Step 1 — Prepare bundle (deterministic)

```bash
npx -y @decreen/demo@pilot judge prepare --base main --head HEAD
```

On failure: `npx -y @decreen/demo@pilot judge prepare --json`

Output: `decreen.invariants-judge-bundle.v1` at `.decreen/analysis/latest.judge-bundle.json` — routed laws, hydrated text, diff excerpt, orphan candidates, judge instructions.

**This is the first-class path.** Default behavior when no agent has judged yet.

### Step 2 — Customer agent judges (you)

Read the bundle. For each routed law, emit exactly one:

| result | Meaning |
|---|---|
| `violated` | Clear break (high bar) |
| `touched` | Law load-bearing for this change — future steering metric |
| `not-applicable` | Routed but does not meaningfully apply |
| `cannot-judge` | Diff insufficient — hard observer candidate |
| `orphan` | Heuristic only — new regularity without index link |

**Conservative posture:** prefer `not-applicable` / `cannot-judge` over alarm volume.

**`false_positive` is never a judge result.** Post-review: `calibration.decision: dismiss`.

#### Layers framing (when available)

When a routed `sourceId` has a **layers file** entry, read **Product → Human → Technical** before verdict (discussion order per change-flow):

| Repo | Layers file |
|------|-------------|
| carto (history pilot) | [`history-navigation-layers.md`](../../docs/engineering/invariants-layers/history-navigation-layers.md) |
| Other clusters | `docs/engineering/invariants-layers/<cluster>-layers.md` if present |
| New cluster | global `/invariants-layers` skill (portable; operator-installed) |

Use the **Product** layer in `touched` / `violated` rationale — symptom the user would notice, not root-cause jargon.

Do **not** modify index JSON or inventory when reading layers — Option A pilot links by `sourceId` only.

### Hard rules

**Hard rule 1:** `violated` requires diff-line evidence in `rationale` / `evidence[]`. Do not upgrade `touched` to `violated` without a cited hunk.

**Hard rule 2 (declaration laws):** For laws that mandate an explicit declaration, annotation, or marker, the absence of that declaration IS the violation. Do not infer defaults, do not assess whether an undeclared behavior would be appropriate — appropriateness of the default is not a defense against a declaration requirement. Covers stamp discipline (`PATCH-2`, `LAW-PATCH-1`), annotation requirements, and explicit mode markers — any law whose substance is "say it out loud."

Write verdicts JSON:

```json
{
  "verdicts": [
    { "sourceId": "HISTORY-GRAPH-INGEST-1", "result": "touched", "rationale": "..." }
  ]
}
```

Save to [`.decreen/analysis/latest.judge-verdicts.json`](../../.decreen/analysis/latest.judge-verdicts.json).

If no agent runtime is available: **do not fabricate a full judge run.** Stop at prepare-only or emit `cannot-judge` only where you explicitly attempted review.

### Step 3 — Apply verdicts → local event log

```bash
npx -y @decreen/demo@pilot judge apply --base main --head HEAD
# Debug (full not-applicable stream): add --log-all-verdicts
```

Appends to **customer-local** [`.decreen/analysis/invariants-event-log.jsonl`](../../.decreen/analysis/invariants-event-log.jsonl). Schema: [`.decreen/schema/invariants-event.v1.schema.json`](../../.decreen/schema/invariants-event.v1.schema.json).

Markdown report prints to stdout (paste into PR comment — flag-only).

**P1 telemetry hygiene:** Default apply logs **actionable verdicts + one run-summary row** only (`not-applicable` omitted). Use `decreen judge apply --log-all-verdicts` for the full P0 stream (~463 lines on baseline).

## Event log fields

`invariantId`, `result`, `layer: backstop`, `pr`, `changeSource`, `judge.executor: customer-side-agent`, optional `calibration`.

Telemetry must exist from first judged run — do not rely on PR comments alone.

## Calibration feedback loop

| calibration.decision | Action |
|---|---|
| `confirm` | Keep index |
| `dismiss` | False positive — narrow territory or downgrade `lawQuality` |
| `promote` | Codification path (below) |
| `recode` | Fix normative text in md |

## Codification promotion

When orphan or harvest-from-test law is accepted:

1. Write normative statement to corpus (`.cursor/ai/AREAS/` or `docs/adr/`)
2. Update index: `sourceRef` → md; `promotedFrom` → original ref
3. Set `bits.documented: yes`

## Extractor vs judge economics

| Role | Posture |
|---|---|
| Extractor | Confident + falsifiable; wrong drafts = mechanism |
| Customer-side judge | Conservative; low alarm volume |

Do not apply extractor confidence to judge instructions.

## Related artifacts

- Prepare/apply CLI: `decreen judge prepare`, `decreen judge apply`
- Script (debug): [`.decreen/scripts/judge-pr-invariants.mjs`](../../.decreen/scripts/judge-pr-invariants.mjs)
- Change flow: [`invariants-change-flow.md`](../../docs/engineering/invariants-layers/invariants-change-flow.md)
- Layers pilot: [`history-navigation-layers.md`](../../docs/engineering/invariants-layers/history-navigation-layers.md)
- Global layers skill: `/invariants-layers` (portable cluster enrichment)
- **P0 golden path:** [`.decreen/fixtures/p0-judge-baseline/README.md`](../../.decreen/fixtures/p0-judge-baseline/README.md)
- Regression: `node .decreen/scripts/verify-p0-judge-golden.mjs`
- Index schema: [`.decreen/schema/invariants-index.v1.schema.json`](../../.decreen/schema/invariants-index.v1.schema.json)

## Implementation status

| Component | Status |
|-----------|--------|
| Skill `/decreen-judge-PR` | ✅ local |
| `decreen judge prepare` | **Shipped** |
| `decreen judge apply` | **Shipped** (P1 telemetry: actionable + run summary) |
| Layers integration (Option A) | ✅ manual link by sourceId |
| Hosted PR review | ❌ never (pilot) |
