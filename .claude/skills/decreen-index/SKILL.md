---
name: decreen-index
description: >-
  Build the lean invariants routing index from an approved inventory. Runs
  `decreen index bootstrap`, validates outputs, and summarizes tier/enforcement
  bits for the operator. Workflow step between /decreen-build-invariants and /decreen-judge-PR.
  Use when the user runs /decreen-index or /decreen-bootstrap-index.
disable-model-invocation: true
---

# Decreen Index — lean routing index bootstrap

Build the **lean invariants index** — routing metadata that maps diffs to laws without duplicating law text.

**Product framing:**

> The index routes diffs to laws. Full text hydrates from `sourceRef` at judge time — the index stays lean.

**Aliases:** `/decreen-index`, `/decreen-bootstrap-index`

**Follow Step 0 throughout this skill.**

## Step 0: User-facing output contract

Before bootstrap:

`Building invariants index…`

On success:

```text
Index built: N laws
Tier: global X · domain Y · scoped Z
Observed: yes A · no B · unknown C
codeSupported: yes X · no Y · unknown Z · stale W
Broken observer links: K
Next: /decreen-judge-PR
```

On failure: short problem + one next action.

Do not dump law text or full index JSON in chat.

---

## Naming disambiguation

| Term | Meaning |
|------|---------|
| **Inventory** | Full codified-law catalog (`latest.invariants-inventory.json`) — from `/decreen-build-invariants` |
| **Index** (this skill) | Lean routing metadata (`latest.invariants-index.json`) |
| **Invariants proposal** | Selective 8–15 guards — `/decreen-suggest-invariants` (complementary) |

---

## Prerequisites

- [`.decreen/analysis/latest.invariants-inventory.json`](../../.decreen/analysis/latest.invariants-inventory.json) must exist

If missing:

- **STOP** — one next action only:
  - Run [`/decreen-build-invariants`](../decreen-build-invariants/SKILL.md), or
  - Demo fast path: `decreen reset --scenario carto` (requires `@decreen/demo@pilot` setup)

---

## Workflow

### 1. Preflight

**Authoritative preflight (DECREEN-GIT-CLEAN-1)** — bootstrap requires committed application source @ HEAD:

```bash
npx -y @decreen/demo@pilot preflight --authoritative
```


**Do not use `git status --porcelain` as the gate.** Bootstrap-only dirty paths (including `.gitignore` from setup) are excluded. Proceed when preflight exits 0.

If preflight exits non-zero → STOP (same message as `/decreen-build-invariants`). Do not bootstrap on uncommitted **source** changes.

Verify inventory exists and parses:

- `kind` is `decreen.invariants-inventory.v1-draft` (or future ratified kind)
- `entries[]` is non-empty
- no duplicate `sourceId` values

If any check fails → STOP with specific fix.

### 2. Run bootstrap (deterministic)

```bash
npx -y @decreen/demo@pilot index bootstrap
```


```bash
npx -y @decreen/demo@pilot index bootstrap --json
```

Requires inventory from `/decreen-build-invariants` and scripts installed by `@decreen/demo@pilot setup` (or monorepo dogfood at repo root).

### 3. Validate outputs

Confirm both files exist:

- [`.decreen/analysis/latest.invariants-index.json`](../../.decreen/analysis/latest.invariants-index.json) — schema: [`.decreen/schema/invariants-index.v1.schema.json`](../../.decreen/schema/invariants-index.v1.schema.json)
- [`.decreen/analysis/latest.invariants-index.csv`](../../.decreen/analysis/latest.invariants-index.csv)

JSON checks:

- `kind === 'decreen.invariants-index.v1'`
- `entries.length > 0`
- read `summary.tier`, `summary.bits.observed`, `summary.bits.codeSupported`, `summary.assessmentStale`, `summary.brokenObserverLinks`

### 4. Summarize (Step 0 template)

Use counts from `summary` in the index JSON. Mention CSV path only if operator asks for spreadsheet review.

### 5. Handoff

Next step: [`/decreen-judge-PR`](../decreen-judge-pr/SKILL.md)

---

## When to re-run

- Inventory updated (new laws, observer paths changed)
- Capability YAML or coverage matrix changed (territory inference inputs)
- Index older than inventory (`inventoryRunId` mismatch in index vs inventory `runId`)

---

## Do NOT

- Duplicate `statement` text from inventory into chat
- Edit index entries by hand — fix inventory or territory sources, then re-bootstrap
- Skip inventory gate and bootstrap from CSV directly (use `/decreen-build-invariants` or demo prebuilt inventory)
