---
name: decreen-status
description: >-
  Show the current local Decreen state for this repository. Reads local Decreen
  manifest and run artifacts, compares the last analyzed commit with current git
  HEAD, checks whether the workspace is a temporary preview or persistent, and
  suggests the next Decreen action. Does not upload data or modify the map.
  Use when the user runs /decreen-status or asks what the current Decreen state is.
---

# Decreen Status

Show the current Decreen state for the current repository.

This skill is **read-only**. It must not upload data, create previews, refresh maps, deepen maps, claim workspaces, or modify remote Decreen state.

It must **not** write or overwrite `.decreen/manifest.json` (unlike `/decreen-deepen` pre-flight, which may merge lifecycle from the status API).

**Follow Step 0 throughout this skill.**

## Step 0: User-facing output contract

Before / during (optional — skip if instant), you may say only:

`Checking workspace status…`

Do not narrate internal steps, file existence checks, git SHA comparison, remote GET status calls, manifest field reconciliation, reading this skill, or curl commands.

On success, use a concise status block only — see [Successful output style](#successful-output-style).

On failure:

- short problem statement and one next action only
- include **Debug details** only when:
  - status could not be determined
  - the user asks
  - `DECREEN_DEBUG=1`
  - `--verbose`

Do not include ASCII art from `/decreen-preview` or upload narration.

---

## When to use

Use when:

* the user runs `/decreen-status`
* the user asks whether the repo already has a Decreen map
* the user asks whether the preview was claimed
* the user asks what to do next with Decreen
* the user asks whether the local repo changed since the last Decreen preview or refresh

Do not use for:

* creating a new preview → [`/decreen-preview`](../decreen-preview/SKILL.md)
* updating a persistent map → [`/decreen-refresh`](../decreen-refresh/SKILL.md)
* expanding one area → [`/decreen-deepen`](../decreen-deepen/SKILL.md)
* connecting agent auth → [`/decreen-login`](../decreen-login/SKILL.md)

## Lifecycle context

```text
/decreen-preview  → create temporary map
/decreen-status   → where am I? (this skill)
/decreen-deepen   → improve one area (persistent only)
/decreen-refresh  → update persistent map
```

---

## Flow

1. Read `.decreen/manifest.json` if present.
2. Read current git context (read-only):
   * current branch (`git rev-parse --abbrev-ref HEAD`)
   * current commit SHA (`git rev-parse HEAD`)
   * remote URL if available (`git remote get-url origin`) — **sanitize** before display (no embedded credentials)
3. Compare current commit with `analysis.lastCommitSha` when present.
4. Check local run files (existence only, do not read bodies):
   * `.decreen/runs/latest.upload.md` (preview)
   * `.decreen/runs/latest.source-evidence.json`
   * `.decreen/runs/latest.request.json`
   * `.decreen/runs/latest.refresh-context.json` (refresh)
   * `.decreen/runs/latest.refresh-agent-prompt.md`
   * `.decreen/runs/latest.refresh.upload.md`
   * `.decreen/runs/latest.repo-map-coverage.json` (coverage health summary)
5. Determine workspace state from manifest `decreen.workspaceLifecycle` and required fields.
6. For **persistent** workspaces only: check whether agent credentials exist (see [Agent auth check](#agent-auth-check)) — do not print tokens.
7. Suggest **one** primary next action.

### Optional remote check (verbose only)

When the user asks for verbose output, or `DECREEN_DEBUG=1`, or `DECREEN_API` is not the production default, you may call:

```text
GET ${DECREEN_API}/api/v0/local-architecture-preview/{workspaceId}/status
```

No `Authorization` header. Use the response to report remote lifecycle, expiry, and URLs — **do not** merge into `manifest.json` from this skill.

Capability: [`.decreen/capabilities/local_preview_workspace_status.yaml`](../../.decreen/capabilities/local_preview_workspace_status.yaml)

---

## What to read

| Source | Use |
|--------|-----|
| `.decreen/manifest.json` | Workspace id, lifecycle, URLs, `analysis.lastCommitSha`, counts, artifact paths |
| Git metadata | Current branch, HEAD, sanitized remote |
| Local run files | Presence of latest artifacts |
| `~/.config/decreen/auth.json` or env | Auth presence only (verbose / persistent) — never print secrets |
| `DECREEN_API`, `DECREEN_FRONTEND_URL` | Configured API host (verbose only by default) |

Do not read source code files. Do not read upload artifact or evidence sidecar **contents** unless the user explicitly asks in verbose mode for artifact metadata (size, heading presence) — default is existence only.

---

## State rules

### No local Decreen state

If `.decreen/manifest.json` does not exist:

```text
Decreen status: not set up for this repo

Next:
Run /decreen-preview to create a temporary architecture map.
```

### Incomplete local state

If manifest exists but is missing `decreen.workspaceId`, `decreen.workspaceLifecycle`, or `analysis.lastCommitSha`:

```text
Decreen status: incomplete local state

Next:
Re-run /decreen-preview, or repair .decreen/manifest.json from a known good backup.
```

Do not guess missing fields.

### Temporary preview

If `decreen.workspaceLifecycle` is `"temporary_preview"`:

* show preview link: prefer `decreen.embedUrl`, else `decreen.viewerUrl`, else `decreen.publicExploreUrl`
* show claim link if `decreen.claimAvailable` and `decreen.claimUrl` exist; else derive `{frontendOrigin}/claim-preview/{workspaceId}` only in verbose mode
* show expiry if `decreen.expiresAt` is set
* if current git HEAD ≠ `analysis.lastCommitSha`: change status is **repo changed**

Suggested next action (pick one):

* preview still useful and unclaimed → claim the map
* repo changed or preview stale → re-run `/decreen-preview`

### Persistent workspace

If `decreen.workspaceLifecycle` is `"persistent"`:

* show workspace URL: `decreen.workspaceUrl` when present
* if current HEAD ≠ `analysis.lastCommitSha`: **repo changed**
* check local grounding artifacts: `latest.finalize-summary.json`, `latest.node-grounding-receipts.json`
* when possible, check remote: `sourceGrounded` / `hasNodeGroundingReceipts` via public status API

Suggested next action (pick one, in order):

* **setup not complete** (persistent but no finalize artifacts / not `sourceGrounded`) → `/decreen-complete`
* repo changed **and** setup complete → `/decreen-refresh`
* repo up to date **and** setup complete → `/decreen-deepen <area>` if the user wants more detail; otherwise open the workspace map

### Unknown lifecycle

If `workspaceLifecycle` is missing or unrecognized, treat as **incomplete**.

---

## Change status

Compute from git HEAD vs `analysis.lastCommitSha`:

| Condition | Label |
|-----------|--------|
| No `lastCommitSha` in manifest | `unknown` |
| `HEAD` equals `lastCommitSha` | `up to date` |
| `HEAD` differs | `repo changed` |

Use short SHAs (7–8 characters) in user-facing output.

---

## Agent auth check

For persistent workspaces, report auth **presence only**:

1. If `DECREEN_AGENT_BEARER_TOKEN` or `DECREEN_BEARER_TOKEN` is set → `Auth: env token set` (do not print value)
2. Else if `~/.config/decreen/auth.json` exists → run `npx -y @decreen/local status` when available, or report `Auth: credentials file present`
3. Else → `Auth: not signed in` — suggest `/decreen-login` or lazy login on first `/decreen-deepen`

Never print bearer tokens, refresh tokens, or cookie values.

---

## Successful output style

Default to a concise status response — like `git status`, not a debug report.

### Default (concise)

Use this shape:

```text
Decreen status: <lifecycle summary> · <change status>

Open preview: <link>          # temporary only, when URL known
Claim map: <link>             # temporary only, when claim available
Open workspace: <link>        # persistent only

Next: <one recommended action>
```

Examples:

```text
Decreen status: temporary preview · repo changed

Open preview: ...
Claim map: ...

Next: claim this map or rerun /decreen-preview for a fresh map.
```

```text
Decreen status: persistent · up to date

Open workspace: ...

Next: run /decreen-deepen <area> to add detail, or open the map.
```

### Verbose

When the user asks for verbose output, runs `/decreen-status --verbose`, or sets `DECREEN_DEBUG=1`, use the expanded template:

```text
Decreen status

Workspace
- State: <none | temporary preview | persistent | incomplete>
- Workspace: <workspaceId or —>
- Expires: <date or —>
- Claim: <available | not available | —>

Repo
- Repo: <fullName or —>
- Branch: <branch>
- Analyzed commit: <short_sha or none>
- Current commit: <short_sha>
- Status: <up to date | repo changed | unknown>

Local files
- .decreen/manifest.json <✓ | missing>
- .decreen/runs/latest.upload.md <✓ | missing>
- .decreen/runs/latest.source-evidence.json <✓ | missing>
- .decreen/runs/latest.request.json <✓ | missing>
- .decreen/runs/latest.refresh-context.json <✓ | missing>
- .decreen/runs/latest.refresh.upload.md <✓ | missing>

Links
- Preview/embed: <url or —>
- Claim: <url or —>
- Workspace: <url or —>

Agent support
- Auth: <signed in | not signed in | env token set>
- API: <DECREEN_API value>
- Evidence sidecar: <available | missing>

Next step
- <one primary action>
```

Put remote-vs-manifest drift (from optional GET status) under a **Remote check** subsection at the end in verbose mode only.

## Return result

Follow [Step 0](#step-0-user-facing-output-contract). Do not add extra narration.

---

## Safety

* Do not upload anything.
* Do not modify `.decreen/manifest.json`, `.decreen/config.json`, or run artifacts.
* Do not read source files except local Decreen metadata and git metadata.
* Do not print secrets, tokens, or full remote URLs with embedded credentials.
* Sanitize remote URLs before display (strip `user:password@` from HTTPS URLs; never show SSH keys or tokens in URLs).

---

## Related skills

| Skill | Role |
|-------|------|
| [`/decreen-preview`](../decreen-preview/SKILL.md) | Create temporary map + local evidence |
| [`/decreen-deepen`](../decreen-deepen/SKILL.md) | Expand one area (persistent; may refresh manifest from status API) |
| [`/decreen-refresh`](../decreen-refresh/SKILL.md) | Re-analyze persistent workspace |
| [`/decreen-login`](../decreen-login/SKILL.md) | Agent OAuth for authenticated APIs |
