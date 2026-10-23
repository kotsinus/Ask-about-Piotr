---
name: decreen-complete
description: >-
  Complete workspace setup after claim — connect the map to local source context
  (one-time lifecycle step). Use when the user runs /decreen-complete or asks to
  complete workspace setup.
---

# Decreen Complete Workspace Setup

**Product name for the post-claim lifecycle step.**

Think **git init for Decreen** — run once after claim, before refresh or deepen.

**Follow Step 0 throughout this skill.**

## Step 0: User-facing output contract

Before / during, say only:

`Completing workspace setup…`

Do not narrate internal steps, manifest checks, server claim state, stale manifest reconciliation, CGC scope/index/reconcile, disclosure plumbing, reading this skill, or CLI command details.

First source-anchors disclosure prompts are allowed when required (show copy in chat for non-interactive runs).

On success, paste or mirror `formatFinalizeProductSummary` / CLI output only — see [Successful output style](#successful-output-style).

On failure or partial success:

- do not use the success template
- short problem statement and one next action only
- include **Debug details** only when:
  - the command failed
  - the user asks
  - `DECREEN_DEBUG=1`
  - `--verbose`

Do not claim `/decreen-refresh` or `/decreen-deepen` work until setup succeeded.

---

## When to use

- User just claimed a preview workspace
- User runs `/decreen-complete` or asks to complete workspace setup
- `/decreen-status` shows persistent workspace without grounding artifacts
- **Not** before claim — temporary previews must be claimed first

## Prerequisites

| Requirement | Check |
|-------------|--------|
| `@decreen/local` installed | `decreen doctor` or `npx -y @decreen/local setup` |
| `.decreen/manifest.json` | `workspaceLifecycle: persistent` |
| Source evidence sidecar | `.decreen/runs/latest.source-evidence.json` from `/decreen-preview` |
| CGC runtime | `decreen doctor --install-missing` if needed |

## Command

```bash
decreen complete --upload
```

Hidden CLI alias (maintainer): `decreen finalize --upload`

### First source-anchors upload (disclosure)

Default workspace mode is `source_anchors`. On the **first** anchor upload, complete shows a short disclosure (symbol names + opaque permalinks only; no source code).

| Context | What to do |
|---------|------------|
| Interactive terminal | User answers the prompt |
| Agent / non-interactive | Show disclosure copy in chat; on confirm, run with `DECREEN_ACCEPT_SOURCE_ANCHORS_DISCLOSURE=1` |
| User declines | Complete still finishes; counts + typed views upload; anchors are skipped |

Monorepo:

```bash
node packages/decreen-local/dist/cli.js complete --upload
```

Maintainer options: `--allow-stale-evidence`, `--skip-index`, `--json`, etc.
Archived maintainer spec: [`.cursor/skills/_archive/decreen-finalize/SKILL.md`](../_archive/decreen-finalize/SKILL.md).

## Product flow

```text
/decreen-preview  →  evidence sidecar
claim             →  persistent workspace
/decreen-complete →  source grounding on server + local artifacts
/decreen-refresh  →  map updates after repo changes
/decreen-deepen   →  expand one area
```

## Successful output style

Canonical formatter: `formatFinalizeProductSummary` in `packages/decreen-local/src/finalize/formatFinalizeProductSummary.ts`.

```text
Workspace setup complete

Your map contains N nodes and M edges.

X% of repository files are currently represented on the map.

Next:
• /decreen-refresh
• /decreen-deepen

Open map →
<workspaceUrl>
```

## Return result

Follow [Step 0](#step-0-user-facing-output-contract). Do not add extra narration.

---

## Errors

| Situation | Action |
|-----------|--------|
| No manifest | `/decreen-preview` first |
| Still temporary preview | Claim in Decreen; re-run `/decreen-complete` |
| No source evidence | Re-run `/decreen-preview` |
| CGC runtime missing | `decreen doctor --install-missing` |

## Related

- [`/decreen-preview`](../decreen-preview/SKILL.md)
- [`/decreen-refresh`](../decreen-refresh/SKILL.md)
- [`/decreen-deepen`](../decreen-deepen/SKILL.md)
- [`/decreen-status`](../decreen-status/SKILL.md)
