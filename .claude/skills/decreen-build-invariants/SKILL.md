---
name: decreen-build-invariants
description: >-
  Full doctrine extraction pass for a repository: locate the corpus, inventory
  codified laws, discover uncodified laws from code and git history, reconcile
  sources, and produce interview questions. Step 3 of the Decreen pipeline.
  Requires architecture graph + capabilities proposal. Use when the user runs
  /decreen-build-invariants or asks for doctrine bootstrap, invariants inventory, or full
  law extraction.
disable-model-invocation: true
---

# Decreen Build Invariants — Doctrine Bootstrap (Full Extraction Pass)

**Minimum CLI:** `@decreen/demo@>=0.5.8-beta.0` or monorepo `packages/decreen-local`. Audit: [`docs/engineering/invariants-skill-cli-audit.md`](../../docs/engineering/invariants-skill-cli-audit.md). Pilot `@0.5.7` lacks `--corpus-include` and `invariants validate`.

Produce the **architecture doctrine** for this repository in a single pass: harvesting every law the team has already codified, discovering the laws that live only in code and git history, and reconciling both into one inventory. Doctrine is the intensional layer — the set of laws that must remain true regardless of how the code is currently written, plus the reasons why. It documents what MUST BE, while code only shows what IS.

**Product framing:**

> Doctrine is a DRAFT FOR HUMAN CORRECTION. Output must be precise enough to be falsified — a confident, specific, wrong claim is more useful than a vague guess.

**Aliases:** `/decreen-build-invariants`, `/decreen-doctrine`, `/decreen-inventory` (supersedes deprecated `/decreen-inv`)

**Follow Step 0 throughout this skill.**

## Step 0: User-facing output contract

Before extraction:

`Extracting doctrine…`

Do not narrate internal steps unless debug.

On success:

```text
Corpus: N files confirmed (M rejected by score, K added by human)
Inventory: X codified laws — Y watched, Z unwatched, T tracks-implementation
Discovery: C candidates enumerated · P promoted (H high / M medium) · R rejected (by reason) · S speculation → interview
Interview: Q questions
Reconciliation: A confirmed by 2+ sources · B discovery-only · C inventory-only
Code assessment: X supported · Y partial · Z not assessed @ <short-sha>
Coverage gaps: <list, "none", or "coverage gate skipped: no churn data">
```

On failure: short problem + one next action.

---

## Critical epistemic constraint

Doctrine cannot be derived from code alone. Intent is not in the text. Your output is a DRAFT FOR HUMAN CORRECTION. Your job is to make claims precise enough to be falsified by the human reviewing them. A vague guess wastes their time; a confident, specific, wrong claim is useful — catching it is how the real doctrine surfaces.

---

## Prerequisites — this is Step 3 of the pipeline

This pass runs after and depends on:

1. **System architecture graph** (Step 1) — the structural map of the repo: modules, layers, dependency edges. Requires persistent Decreen workspace with `c4` facet (see [`/decreen-preview`](../decreen-preview/SKILL.md) or [`/decreen-update`](../decreen-update/SKILL.md)).
2. **Capabilities proposal** (Step 2) — [`.decreen/analysis/latest.capabilities-proposal.json`](../../.decreen/analysis/latest.capabilities-proposal.json) and the capability hierarchy it pins to. Prepare with [`/decreen-build-capabilities plan`](../decreen-build-capabilities/SKILL.md) (`decreen capabilities plan`); validate with `decreen capabilities validate`; publish with `decreen capabilities publish` when ready.

Optional prior artifact: [`.decreen/analysis/latest.invariants-proposal.json`](../../.decreen/analysis/latest.invariants-proposal.json) from [`/decreen-suggest-invariants`](../decreen-suggest-invariants/SKILL.md) — used in Phase 5 reconciliation only.

If either Step 1 or Step 2 artifact is missing, **STOP** and report which one — do not degrade into a standalone pass. Both are load-bearing: the graph defines the boundaries and churn data that discovery reads, and the capability hierarchy is the pinning target for every law.

### Pre-flight

**Authoritative preflight (DECREEN-GIT-CLEAN-1)** — before any artifact writes:

```bash
npx -y @decreen/demo@pilot preflight --authoritative
```


**Prepare (deterministic — recommended before agent harvest):**

```bash
npx -y @decreen/demo@pilot invariants prepare
```

On failure: `npx -y @decreen/demo@pilot invariants prepare --json`

Writes:

- `.decreen/runs/latest.inv-context.json`
- `.decreen/runs/latest.inv-agent-prompt.md`
- `.decreen/analysis/doctrine-corpus.md` (Phase 0 pre-scan — agent confirms)
- `.decreen/inv-runs/<runId>.agent-draft.json` (empty inventory scaffold — the agent harvests freely; pre-filled entries would anchor the agent and depress recall)
- `.decreen/runs/latest.inv-coverage-checklist.json` (deterministic law-bearing section scan — the **recall floor** audited by `invariants reconcile`, never a pre-fill)

Requires [`.decreen/analysis/latest.capabilities-proposal.json`](../../.decreen/analysis/latest.capabilities-proposal.json). Does **not** discover laws — the agent completes Phases 0–5b from the prompt.

**Reconcile (deterministic — mandatory after Phase 1 harvest):**

```bash
npx -y @decreen/demo@pilot invariants reconcile
```

The agent **finds** laws; code **names** them. Per entry, in priority order:

1. **Evidence gate (hallucination gate):** the verbatim quoted `statement` is located in the cited file @ HEAD — exact hit, else fuzzy match (paraphrase repair). A quote that cannot be located is quarantined with `evidence_not_found` (sourceId stays null; entry flagged). Previously a fabricated `sourceRef` entered the inventory unopposed — this gate is load-bearing, not an implementation detail.
2. **Own ID wins:** a law ID present in the located section (re-derived from the file, never from the agent's string).
3. **Inheritance:** the same law (same sourceRef path + statement similarity vs the previous retained inventory) inherits its old ID — cross-run and cross-commit continuity.
4. **Mint:** `IMPORT-<file-slug>-<heading-slug>`; collisions under one heading are tie-broken by **span order in the file** — fully a function of the file @ commit, zero LLM text in the key. Ordinal fragility across commits does not bite: cross-commit continuity is inheritance's job; minting only names laws the previous inventory does not know.

It also runs the **coverage audit**: every checklist section must be covered by an entry or explicitly dismissed with a reason. Non-zero exit on quarantined entries or gaps — fix and rerun until clean.

> **Architectural decision — matching vs minting asymmetry:** statement similarity is legal in *matching* (inheritance; a wrong match costs one false split/new which human ratification catches) and forbidden in *minting* (a statement-derived key destroys identity permanently under rewording). These two mechanisms look similar; do **not** unify them.

**Stability harness (measurement, not extraction):**

- `invariants prepare --corpus-include <prefix...>` — freeze the included corpus to a path-prefix subset for cheap repeated runs (a full harvest takes hours; a frozen 5–8 file subset answers "did this change move variance").
- `decreen invariants diff <runA> <runB>` — compare two retained runs on three separate axes: **recall stability** (entry overlap; sourceRef-path + statement-similarity fallback so a renamed ID reports as `renamed`, not `lost + new`), **status stability** (enforcement/quality agreement on matched pairs), **statement drift**. Accepts runIds retained under `.decreen/inv-runs/` or explicit inventory JSON paths.
- Diff and reconcile **share one matcher** (`sourceRef` path + statement similarity). If they ever disagree on the same data, someone forked the logic and one copy is lying.

**Do not use `git status --porcelain` as the gate.** Bootstrap-only dirty paths (including `.gitignore` from `decreen setup`) are excluded. Proceed when preflight exits 0.

After preflight passes:

```bash
git rev-parse HEAD       # anchor for verifiedAtCommit
```

If `decreen preflight --authoritative` exits non-zero → **STOP** (do not write inventory, assessment, or reconciliation):

```text
STOP — working tree is not clean.

Decreen artifacts must describe a committed repository state.
Commit, stash, or discard local changes, then rerun.
```

Then:

1. Read [`.decreen/manifest.json`](../../.decreen/manifest.json) — require `workspaceLifecycle: persistent`
2. Confirm architecture graph context — read [`.decreen/runs/latest.capabilities-context.json`](../../.decreen/runs/latest.capabilities-context.json) (from `decreen capabilities plan`) or [`.decreen/runs/latest.refresh-context.json`](../../.decreen/runs/latest.refresh-context.json). If neither exists or `graph.provisional === true` without operator approval, run [`/decreen-build-capabilities plan`](../decreen-build-capabilities/SKILL.md) or [`/decreen-update`](../decreen-update/SKILL.md) first.
3. Read [`.decreen/analysis/latest.capabilities-proposal.json`](../../.decreen/analysis/latest.capabilities-proposal.json) — if missing, run build-capabilities **plan** (agent inference) then `decreen capabilities validate` before this pass
4. Optional: read [`.decreen/analysis/expansions/index.json`](../../.decreen/analysis/expansions/index.json) for high-churn capability signals

**Forbidden:** direct DB/ORM access. HTTP APIs + local files only.

---

## Naming disambiguation

| Term | Meaning |
|------|---------|
| **Doctrine** (this skill) | Full intensional law layer — harvested + discovered + reconciled |
| **Inventory** | Codified laws imported by reference (`latest.invariants-inventory.json`) |
| **Code assessment** | Agent verdict on code vs law @ commit (`latest.invariants-code-assessment.json`) |
| **Index** | Lean routing metadata (`latest.invariants-index.json`) — produced by bootstrap script, not this skill |
| **Invariants proposal** | Selective guard layer (`latest.invariants-proposal.json`) — [`decreen-suggest-invariants`](../decreen-suggest-invariants/SKILL.md) |
| `.decreen/capabilities/*.yaml` | Agent operational choke points — not doctrine |

---

## When to use

- After `/decreen-build-capabilities plan` (and optionally `expand`)
- User runs `/decreen-build-invariants` or asks for doctrine bootstrap, full law extraction, invariants inventory
- Preparing [`/decreen-judge-PR`](../decreen-judge-pr/SKILL.md) index bootstrap from a complete inventory
- Backtest or time-shifted extraction (use `--repo-root` / worktree per operator brief)

## Do NOT use when

- No `.decreen/analysis/latest.capabilities-proposal.json` → run build-capabilities first
- No architecture graph → run `/decreen-preview` or `/decreen-update` first
- User only wants selective proposed invariants (8–15 sharp laws) → use `/decreen-suggest-invariants` instead
- User wants a new architecture map → `/decreen-update`

---

## What qualifies as a doctrine item

Every *discovered* item must pass ALL of these gates (harvested items bypass the gates — they are codified fact, and gate failures are flagged instead via `tracksImplementation`). The gates are **enforced procedurally in Phase 2b** — each is answered yes/no with written proof, never by feel:

1. **Refactor-invariant:** survives a full rewrite of the implementation it governs. If it names a function, file, or current mechanism, it dies with the code → rewrite it in terms of the capability, or discard. (Procedure: the `statement_v0` → `statement_v1` rewrite in Phase 2b.)
2. **Not discoverable:** an agent reading the repo would NOT infer it. A pattern is a law only if deviation would be a bug rather than a style choice. (Procedure: construct a plausible violating implementation that does not look like a bug.)
3. **Not default behavior:** a competent agent without the item would plausibly violate it. Items restating good general practice are noise.
4. **Falsifiable:** a violation can be stated concretely ("two writers to the same projection", "a domain-layer function throws"), even if no lint rule exists yet.
5. **Justified:** carries a one-sentence WHY naming a failure class that lets an agent extrapolate to unforeseen cases.

---

## Phase 0 — Locate the doctrine corpus (do not assume file names)

Doctrine files are wherever the team put them. Build a candidate pool, score it, and **auto-include** — do not block on human confirmation.

**Path/name signals (weak, cheap — use to build the pool):**
glob for `AGENTS.md`, `CLAUDE.md`, `.cursorrules`, `.cursor/rules/**`, `.cursor/ai/**`, `*.mdc`, `.github/copilot-instructions.md`, `.windsurfrules`, `CONTRIBUTING*`, `ARCHITECTURE*`, `CONVENTIONS*`, `GUIDELINES*`, `PRINCIPLES*`, `INVARIANTS*`, `THINKING*`, `CONTRACTS*`, `adr/**`, `docs/adr/**`, `docs/decisions/**`, `docs/engineering/**`, `RFC*`, plus any `*.md` under `docs/`.
Exclude `node_modules/**` and vendored/generated trees (vendored AGENTS.md files are a known trap), changelogs, generated API docs, marketing READMEs.
Exclude Decreen bootstrap paths (same carve-out as `DECREEN-GIT-CLEAN-1`): `.decreen/demo/**`, `.decreen/fixtures/**`, `.decreen/schema/**`, `.decreen/scripts/**`, `.decreen/examples/**`, and `.cursor`/`.claude`/`.kilo/skills/decreen-*`. These may score high but are tooling install, not project doctrine.

**Content signals (strong — score every candidate):**

- Modal density: must / never / always / only / forbidden / required / MUST NOT per 100 lines.
- Law-ID patterns: `[A-Z][A-Z0-9]*(-[A-Z0-9]+)+-\d+` style identifiers.
- Section headers matching invariant/rule/contract/law/non-negotiable/discipline/authority.
- Prohibition + justification pairs ("never X because Y").

A file with high content score and no matching name IS corpus. A file with a matching name and low content score (setup guide, changelog) is NOT.

**Auto-include (default — no confirmation gate):**

- **Include** every candidate with score ≥ 40, or any path under `.cursor/ai/**`, `.cursor/rules/**`, `adr/**`, `docs/adr/**`, `docs/decisions/**`.
- **Exclude** score < 40 unless it matches a path signal above.
- Bootstrap paths are **never** corpus, even when score ≥ 40.
- **Never block** harvesting or Phase 2a discovery waiting for corpus approval.
- Log the scored list in run output (top paths + scores). Proceed immediately to Phase 1.

**Optional human override:** only if the user explicitly says "exclude X" or "add Y" during the run — apply before Phase 1 harvest.

**Write:** [`.decreen/analysis/doctrine-corpus.md`](../../.decreen/analysis/doctrine-corpus.md) — Phase 0 scored list with `included` / `excluded` / `reason` per path.

---

## Phase 1 — Inventory codified laws (harvest freely; code names the laws)

Harvest every codified law from the confirmed corpus. **You find laws; `invariants reconcile` names them** — this split is what makes law identity deterministic across runs.

- **Never assign or invent a `sourceId`** — leave it `null`. IDs are assigned deterministically in Phase 1-R.
- `statement` MUST be a **verbatim quote** of the law line. Reconcile locates the quote in the cited file; an unlocatable quote (exact or fuzzy) is quarantined as `evidence_not_found`. Paraphrase kills the entry.
- Harvest exhaustively — the coverage checklist from prepare is the recall floor, audited in Phase 1-R.

Per-entry fields:

- `sourceId`: `null` (assigned by reconcile: own ID > inherited > minted).
- `sourceRef`: file path + heading/line — the entry POINTS at the text, it does not rewrite it. No second source of truth. Reconcile re-derives the enclosing heading from the file itself, so an approximate pointer is acceptable; the verbatim `statement` is what must be exact.
- `statement`: verbatim one-line quote (compression allowed only after reconcile passes; mark via `statementMode`).
- `pinnedCapabilities[]`: mapping to the Step 2 capability hierarchy; `unpinned` is allowed and is itself a finding (a law that governs nothing in the capability map means either a missing capability or a dead law — say which you suspect).
- `enforcement`: `{ status: "watched" | "unwatched", observer?: string }` — name the observer (lint rule, test, CI check, schema constraint) or prose-only.
- `tracksImplementation`: `true` when the statement fails refactor-survival (names current functions/files); do not drop such entries, the human decides. This is a **law-wording quality flag** — a separate axis from Phase 5b code assessment (`contradicted` = code disagrees with the law; `tracksImplementation` = the law is phrased in implementation terms). Never use one to mean the other.
- `derivation`: `harvested`.

No caps, no selectivity — this is an inventory. Completeness IS the quality bar here.

**Write:** [`.decreen/analysis/latest.invariants-inventory.json`](../../.decreen/analysis/latest.invariants-inventory.json)

```json
{
  "kind": "decreen.invariants-inventory.v1-draft",
  "runId": "<ISO-ish run id>",
  "corpusRef": ".decreen/analysis/doctrine-corpus.md",
  "capabilitiesRunId": "<from latest.capabilities-proposal.json>",
  "entries": []
}
```

### Phase 1-R — Reconcile (deterministic ID assignment + evidence gate)

```bash
npx -y @decreen/demo@pilot invariants reconcile
```

Runs the pipeline described in Pre-flight: evidence gate (`evidence_not_found` quarantine) → own ID → inheritance from the previous retained run → mint with span-order tiebreaker → coverage audit against the checklist. Writes assigned IDs back into the inventory and a report to `.decreen/runs/latest.inv-reconcile-report.json`.

Non-zero exit = quarantined entries or coverage gaps remain. For each:

- `evidence_not_found` → re-read the section and fix the quote to verbatim (paraphrase repair failed), or drop the entry if the evidence was imagined — log which in run output.
- coverage gap → harvest the missed section, or dismiss it explicitly with a reason ("section is law-shaped but describes tooling setup, not doctrine").

Rerun until clean. **Do not hand-assign IDs to bypass the gate.**

### Phase 1-V — Validate (form gate + corpus floor)

```bash
npx -y @decreen/demo@pilot invariants validate
```

Runs after reconcile, before Phase 2a. Checks duplicate `sourceId`, watched-without-observer, reconcile report failures/gaps, corpus floor (`corpusIncludedCount` or confirmed paths in `doctrine-corpus.md`), and vacuous checklist. Non-zero exit blocks discovery.

### Inventory gate (before Phase 2a)

- `decreen invariants validate` exits 0
- Reconcile exits 0 (no quarantined entries, no coverage gaps)
- No duplicate `sourceId`
- Every `sourceRef` path resolves under `--repo-root` (default: repo root)
- Every `watched` entry names a concrete observer path or CI job

**Retention:** copy the completed inventory to `.decreen/inv-runs/<runId>.inventory.json` (the `latest.*` file is overwritten every run — retained copies feed `decreen invariants diff` and ID inheritance in the next run's reconcile).

---

## Phase 2a — ENUMERATE discovery candidates (recall pass — no judgment)

With the inventory in hand, hunt for laws that are NOT yet codified. This pass is **exhaustive enumeration only**: no gates, no CONFIDENCE, no merging, no rejection. Recording a candidate costs nothing; a candidate skipped here is unrecoverable. Read against the Step 1 graph, and look where doctrine hides:

- **Asymmetries:** two similar modules handled differently — the graph tells you which modules are structurally similar; check whether the code treats them the same. Either accidental drift or a deliberate distinction — you cannot tell which; the human can.
- **Single-writer patterns:** state, projections, caches, files that only one code path mutates. The graph's dependency edges show fan-in — any node with many readers and one writer is a candidate authority law.
- **Suspicious survivors:** dead-looking code, odd timeouts, deliberate duplication, disabled checks. Candidate landmines — things that look like bugs but may be intentional.
- **One-way doors:** schema migrations, published APIs, event formats, ID schemes. Candidate irreversibility laws.
- **Boundary crossings:** the layer boundaries come from the Step 1 graph (domain/infra, frontend/backend, tenant isolation) — check each edge that crosses one. Candidate prohibition laws.
- **Git archaeology:** reverted commits, repeated fix patterns, commit messages containing "again", "actually", "revert". Each recurring fix is a law someone keeps re-learning. Prioritize files belonging to high-churn capabilities.

**Write:** `.decreen/analysis/discovery-candidates.json` — one row per candidate:

```json
{
  "candidateId": "CAND-001",
  "rawObservation": "<what you saw, in observation terms>",
  "channel": "archaeology | enforcement | asymmetry | survivor | one-way-door | boundary",
  "evidence": [{ "path": "<file or commit>", "kind": "code | commit | config | test" }],
  "pinnedCapabilities": ["capability:..."],
  "gateEvaluation": null
}
```

`gateEvaluation` stays `null` in this phase — classification happens in 2b.

**Coverage gate:** for every high-churn capability (churn per `expansions/index.json`), the candidate list must contain ≥1 entry pinned to it OR an explicit gap row explaining why the channel sweep found nothing. If `expansions/index.json` is absent, emit `coverage gate skipped: no churn data` in run output — never skip silently.

**Dedup rule:** if reconnaissance surfaces a law already present in the Phase 1 inventory, do NOT record it as a candidate — append structured evidence to the in-memory **code assessment map** keyed by `sourceId` (feeds Phase 5b). Enumerate only what the corpus does not already state.

---

## Phase 2b — CLASSIFY candidates (precision pass — the rubric is the cap)

Evaluate every Phase 2a candidate against the promotion rubric. Fill `gateEvaluation` per candidate; every non-promotion is logged, never silent.

**Refactor-invariance procedure (mandatory, per candidate):**

1. `statement_v0` = the raw observation.
2. `statement_v1` = rewrite `statement_v0` removing ALL implementation identifiers — file names, function names, ports, timeout values, library names.
3. If `statement_v1` is empty, circular, or untestable → REJECT `tracks_implementation`.
4. The promoted statement is `statement_v1`, never `statement_v0`.

**Remaining gates (each answered yes/no with written proof):**

| Gate | Test | Reject reason on failure |
|------|------|--------------------------|
| `notDiscoverable` | Construct a counterexample: describe a **plausible implementation that violates the law and does not look like a bug**. If you cannot construct one, deviation would be an obvious bug and the law is discoverable. | `discoverable_from_code` |
| `notDefaultBehavior` | Name a concrete diff a competent agent would plausibly produce that violates the law. "It would look worse" does not count. | `style_choice` or `ops_convention` |
| `falsifiable` | A concrete violation example exists ("two writers to the same projection") — not a generic quality complaint. | `not_falsifiable` |
| `justified` | The WHY names a failure class (incident, regression, security, data loss) — not "best practice". | `generic_quality_attribute` |

**Promotion rule (no numeric cap — the rubric is the cap):**

```text
PROMOTE iff ALL gates pass
        AND (corpus citation exists OR >= 2 evidence items from different channels)
```

If 23 candidates pass, promote 23. The only permitted reduction is merging laws that share one WHY.

**CONFIDENCE is a function of evidence, not judgment:**

| Tier | Rule |
|------|------|
| `high` | Corpus citation OR ≥2 evidence items from different channels |
| `medium` | 1 evidence item, all gates pass |
| `speculation` | Gates pass, zero code evidence — goes to Phase 4 interview questions, NOT to draft laws |

**Write:** `.decreen/analysis/discovery-rejections.json` — every rejected candidate with `candidateId`, `reason` (enum above, plus `duplicate_inventory`), and one-line `notes`. Pattern: [`.decreen/schema/invariants-rejections.v1.schema.json`](../../.decreen/schema/invariants-rejections.v1.schema.json).

---

## Phase 3 — Draft promoted laws (format only)

For each **promoted** candidate from 2b, output exactly this format:

```text
LAW-<AREA>-<N>: <statement_v1 — one falsifiable statement, refactor-invariant terms>
WHY: <one sentence naming the failure class>
VIOLATION LOOKS LIKE: <concrete example of code that would break it>
EVIDENCE: <file/commit that suggests this law exists>
CHANNEL: <archaeology | enforcement | asymmetry | survivor | one-way-door | boundary>
CONFIDENCE: <high | medium — from the 2b evidence tier, never re-judged here>
ENFORCEABLE BY: <lint rule / test / CI check that could observe it — or "prose-only" if genuinely unmechanizable>
```

Rules for drafting:

- No new judgment in this phase — promotion and confidence were decided in 2b.
- If two laws share a WHY, merge them.
- Anything ENFORCEABLE BY a mechanism should be flagged for migration to that mechanism — doctrine prose is where rules live only until they can be automated.

Group draft laws by area, highest-confidence first. Include in the run output (markdown section or `.decreen/analysis/draft-discovered-laws.md`).

---

## Phase 4 — Interview questions for the human

List every question that Phase 2a/2b raised but code cannot answer — including every `speculation`-tier candidate from 2b (gates passed, zero code evidence). These are the actual doctrine-extraction mechanism. Group them:

1. **Asymmetries:** "X and Y are structurally similar but treated differently at <location> — deliberate distinction or drift?"
2. **Landmine candidates:** "<thing> looks like a bug/dead code at <location> — intentional? If yes, what protects it and why?"
3. **Arbitrary choices:** "You use <A> where <B> is the common default — is there a reason an agent must not migrate to B?"
4. **Escalation boundaries:** "Which of these change categories require a human decision before an agent proceeds: schema, auth, public API, <others found in Phase 2a>?"
5. **Undocumented constraints:** "Is there any external constraint (client contract, compliance, upstream API quirk) that shapes code but is invisible in it?"

Order by how much doctrine hangs on the answer.

> **Known gap (not yet deterministic):** question grouping and ordering is currently agent judgment and re-rolls between runs. Planned fix: group by `pinnedCapabilities`, sort by count of dependent laws, in a renderer script — not in this skill yet.

Include in run output (markdown section or `.decreen/analysis/doctrine-interview-questions.md`).

---

## Phase 5 — Reconciliation

Cross-reference all available sources: the Phase 1 inventory, the Phase 3 draft, and — if present — [`.decreen/analysis/latest.invariants-proposal.json`](../../.decreen/analysis/latest.invariants-proposal.json). Produce a table:

- **CONFIRMS:** found in ≥2 sources — highest confidence tier. Includes every inventory entry that Phase 2a found independent code evidence for.
- **DISCOVERY-ONLY:** uncodified laws — tag which channel found each.
- **INVENTORY-ONLY:** codified laws with no code evidence and no proposal match — per entry, one line on why discovery missed it (this is the channel-gap report).
- **Coverage check:** for every capability in the Step 2 hierarchy, count entries across all sources. List every high-churn capability (churn per the Step 1 graph / git history) with zero entries — each such row is an explicit gap, not silence. A quiet capability with heavy churn is where the next incident lives.

This table is a **separate axis** from code assessment (cross-source doctrine presence ≠ code truth). Do not map CONFIRMS to `assessment=supported`.

---

## Phase 5b — Write code assessment (structured)

Write [`.decreen/analysis/latest.invariants-code-assessment.json`](../../.decreen/analysis/latest.invariants-code-assessment.json) — schema: [`.decreen/schema/invariants-code-assessment.v1.schema.json`](../../.decreen/schema/invariants-code-assessment.v1.schema.json)

Document header:

- `inventoryRunId` = inventory `runId`
- `verifiedAtCommit` = `git rev-parse HEAD` from preflight
- `workingTreeClean: true` (preflight enforced)
- `repository` = origin remote when available

Per assessed inventory entry (`sourceId` join key):

| Field | Rule |
|-------|------|
| `assessment` | `supported` \| `contradicted` \| `partial` \| `unknown` \| `not-assessed` |
| `scope` | Default `partial`. `full` only with explicit `scopeBasis` (what territory was inspected). |
| `evidence` | Required for `supported`, `contradicted`, `partial`. Each item: `path`, `kind`, `relation`, `reason`. |
| `relation` | `supports` required for `supported`; `contradicts` for `contradicted`. |
| `not-assessed` | No evidence (unread entries). |

Then render human report (not source of truth):

```bash
node .decreen/scripts/render-invariants-reconciliation.mjs --repo-root .
```

Produces [`.decreen/analysis/invariants-reconciliation.md`](../../.decreen/analysis/invariants-reconciliation.md) with sections: Code-supported, Code-contradicted, Partially assessed, Inconclusive, Not assessed.

**Retention:** copy the assessment to `.decreen/inv-runs/<runId>.code-assessment.json` (feeds `decreen invariants diff` alongside the retained inventory).

---

## Outputs

| File | Phase | Content |
|------|-------|---------|
| `.decreen/analysis/doctrine-corpus.md` | 0 | Scored candidate list, post-confirmation |
| `.decreen/runs/latest.inv-coverage-checklist.json` | prepare | Law-bearing section scan — recall floor audited by reconcile |
| `.decreen/analysis/latest.invariants-inventory.json` | 1 | Full codified-law inventory (IDs assigned by reconcile) |
| `.decreen/runs/latest.inv-reconcile-report.json` | 1-R | ID assignments, evidence failures, coverage gaps |
| `.decreen/inv-runs/<runId>.inventory.json` | 1 | Retained per-run inventory copy (stability diff + next-run inheritance) |
| `.decreen/analysis/discovery-candidates.json` | 2a | Exhaustive candidate enumeration (no judgment) |
| `.decreen/analysis/discovery-rejections.json` | 2b | Every rejected candidate with reason enum |
| `.decreen/analysis/draft-discovered-laws.md` | 3 | Promoted laws grouped by area |
| `.decreen/analysis/doctrine-interview-questions.md` | 4 | Grouped interview questions (incl. speculation tier) |
| `.decreen/analysis/latest.invariants-code-assessment.json` | 5b | Structured code assessment @ HEAD |
| `.decreen/inv-runs/<runId>.code-assessment.json` | 5b | Retained per-run assessment copy (stability diff) |
| `.decreen/analysis/invariants-reconciliation.md` | 5b | Generated human report from assessment JSON |
| Run output (chat) | 2b | Rejection counts by reason + coverage gate status (`coverage gate skipped: no churn data` when applicable) |

Do not write operational content (build commands, test instructions, escalation procedure text) — that is a separate, easier layer. Doctrine only.

---

## Handoff — index bootstrap

After human approves inventory, build the lean routing index:

[`/decreen-index`](../decreen-index/SKILL.md)

Produces:

- [`.decreen/analysis/latest.invariants-index.json`](../../.decreen/analysis/latest.invariants-index.json) — schema: [`.decreen/schema/invariants-index.v1.schema.json`](../../.decreen/schema/invariants-index.v1.schema.json)
- [`.decreen/analysis/latest.invariants-index.csv`](../../.decreen/analysis/latest.invariants-index.csv)

Then optionally:

- [`/decreen-suggest-invariants`](../decreen-suggest-invariants/SKILL.md) — selective proposed invariants from the same corpus (complementary, not duplicate)
- [`/decreen-judge-PR`](../decreen-judge-pr/SKILL.md) — judge diffs against indexed laws

---

## Workflow position

```text
/decreen-preview or /decreen-update          ← Step 1: architecture graph
  → /decreen-build-capabilities plan         ← Step 2: capabilities proposal
  → /decreen-build-invariants                             ← Step 3: doctrine bootstrap (this skill)
  → human review (inventory approve — corpus is auto-included)
  → /decreen-index
  → /decreen-suggest-invariants (optional)   ← selective guard proposals
  → /decreen-judge-PR                        ← diff judgment
```

---

## Backtest / time-shifted runs

When doctrine must predate judged PRs (e.g. cal.com backtest):

- Run all extraction and `sourceRef` hydration on the **T0 worktree** only
- Write outputs to the operator workspace; copy inventory into T0 `.decreen/analysis/` only for bootstrap if required
- Never mix T0 extraction with post-T0 git history for law discovery

See [`docs/engineering/calcom-doctrine-backtest-agent-brief.md`](../../docs/engineering/calcom-doctrine-backtest-agent-brief.md) for the full two-worktree contract.

---

## Stability measurement protocol

Determinism changes are validated against measured runs, not intuition:

1. **Baseline:** retained runs before a change (R1/R2-style full runs, or frozen-subset runs via `invariants prepare --corpus-include`).
2. **After each change:** rerun on the same commit + same corpus subset; compare with `decreen invariants diff <runA> <runB>`.
3. **Axes are read separately** — recall stability (did the same laws surface), status stability (same enforcement/quality verdicts), statement drift (same wording). Do not average them.
4. **Expect asymmetric readings — this is the designed shape, not a regression.** Harvested laws are stable *by construction* (checklist floor + code-side ID assignment + inheritance): expect ~100% recall stability there. Discovered laws (Phase 2a/2b) still rest on agent enumeration and matching — variance remains and the harness is a real measurement there, not a formality. A diff showing 100% harvested / 70% discovered is the expected shape.
5. **Subagent split (scout/judge) is conditional:** only if recall stability of high-confidence discovery stays **below 90%** after the reconcile + 2a/2b + rubric changes. Above that threshold, subagents are an optimization, not a fix — defer.

Operator runbook for repeated same-commit measurement (archive, workspace clean, diff): [`docs/engineering/invariants-stability-harness.md`](../../docs/engineering/invariants-stability-harness.md) — script: [`.decreen/scripts/harness-invariants-run.sh`](../../.decreen/scripts/harness-invariants-run.sh) (shipped with `@decreen/demo` setup).

## Implementation status

| Component | Status |
|-----------|--------|
| Skill `/decreen-build-invariants` | ✅ local |
| `decreen invariants prepare` | **Shipped** (all tiers) |
| Coverage checklist (law-bearing section scan) | ✅ `invariants prepare` |
| Deterministic ID assignment + evidence gate (`decreen invariants reconcile`) | ✅ CLI |
| Frozen-corpus harness flag (`--corpus-include`) | ✅ CLI since `@decreen/demo@pilot` (>=0.5.8-beta.2) |
| Form gate (`decreen invariants validate`) | ✅ CLI since `@decreen/demo@pilot` (>=0.5.8-beta.2) |
| Stability diff (`decreen invariants diff`) | ✅ CLI |
| Harness operator script (`harness-invariants-run.sh --suite`) | ✅ since `0.5.8-beta.0` |
| Per-run retention (`.decreen/inv-runs/<runId>.inventory.json`, `.code-assessment.json`) | agent-written (this skill) |
| Discovery candidates / rejections artifacts (2a/2b) | agent-written (this skill) |
| Deterministic Phase 4 question grouping | ❌ known gap (renderer, by pinnedCapabilities) |
| Inventory schema `invariants-inventory.v1` | draft (skill emits `v1-draft`) |
| Index bootstrap CLI (`decreen index bootstrap`) | **Shipped** |
| Index bootstrap script | ✅ `.decreen/scripts/bootstrap-invariants-index.mjs` (invoked by CLI) |
| Index skill `/decreen-index` | ✅ local |
| Index schema `invariants-index.v1` | ✅ local |
| KG persist / ratify API | ❌ Phase 2 |
| Code assessment schema | ✅ `.decreen/schema/invariants-code-assessment.v1.schema.json` |
| Reconciliation renderer | ✅ `.decreen/scripts/render-invariants-reconciliation.mjs` |
| Git clean preflight | ✅ DECREEN-GIT-CLEAN-1 (`decreen preflight --authoritative`) |
