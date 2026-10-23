---
name: decreen-finalize
description: >-
  Finalize a claimed Decreen preview workspace by source-grounding the map with
  local CGC and evidence reconciliation. Requires @decreen/local package,
  .decreen/manifest.json with persistent lifecycle, and
  latest.source-evidence.json from /decreen-analyze2. Use when the user runs
  /decreen-finalize or asks to connect a claimed preview to local source context.
---

# Decreen Finalize

Connect a **claimed** preview workspace to local source context so `decreen deepen run` can ground patches in code.

## When to use

- User ran `/decreen-analyze2` → claimed preview → installed `@decreen/local`
- User runs `/decreen-finalize` or asks to finalize / source-ground the repo
- **Not** before claim — temporary previews must be claimed first

## Prerequisites

| Requirement | Check |
|-------------|--------|
| `@decreen/local` installed | `node packages/decreen-local/dist/cli.js doctor` |
| `.decreen/manifest.json` | `workspaceLifecycle: persistent` (or claimable via status API) |
| Source evidence sidecar | `.decreen/runs/latest.source-evidence.json` from analyze2 |
| CGC runtime | `decreen doctor --install-missing` if needed |

## Command

```bash
decreen finalize
```

Monorepo:

```bash
node packages/decreen-local/dist/cli.js finalize
```

### Common options

```bash
decreen finalize --allow-stale-evidence
decreen finalize --skip-index          # reuse latest.cgc-info.json
decreen finalize --skip-scope --skip-index --skip-reconcile  # fast re-summary
decreen finalize --json
```

## What it does

```text
1. Read .decreen/manifest.json
2. Verify workspace is persistent (refresh via public status API if needed)
3. Run scope → index → reconcile from source-evidence sidecar
4. Write .decreen/runs/latest.finalize-summary.json
5. Print next step: decreen deepen run <targetId>
```

## Product flow

```text
/decreen-analyze2     → temp preview + local evidence sidecar
claim in browser      → persistent workspace
npx -y @decreen/local init + decreen doctor
/decreen-finalize     → source-grounded repo
decreen deepen run X  → local deepen patch
```

## Errors

| Situation | Action |
|-----------|--------|
| No manifest | Run `/decreen-analyze2` first |
| Still temporary preview | Open `claimUrl` from manifest; claim; re-run finalize |
| No source evidence | Re-run `/decreen-analyze2` |
| CGC runtime missing | `decreen doctor --install-missing` |

## Upload

```bash
decreen finalize --upload
```

Posts **counts-only** grounding metadata to the workspace (`POST /api/v1/agent/architecture/workspaces/:workspaceId/grounding`). No local file paths are uploaded.

Default is local-only (`--local-only` is implicit unless `--upload` is passed). Requires agent auth (`npx -y @decreen/local login` or `DECREEN_AGENT_BEARER_TOKEN`).

The workspace status API and product UI badge expose `sourceGrounding` after upload.

## Related

- [`/decreen-analyze2`](../decreen-analyze2/SKILL.md) — writes evidence sidecar
- [`decreen deepen run`](../../packages/decreen-local/README.md) — deepen after finalize
- [`.decreen/README.md`](../../.decreen/README.md) — lifecycle docs
