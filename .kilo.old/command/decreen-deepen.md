---
description: Deepen one area of a Decreen workspace
---

Use the `decreen-deepen` skill.

Target arguments are passed through from `$ARGUMENTS`. If no target is provided, inspect the manifest/status and ask for the single map area or node to deepen only if it cannot be inferred.

Use the project wrapper so Windows runs Decreen through WSL, where the managed CGC/Kuzu runtime is supported. The wrapper sets the QA endpoints for this workspace and runs `doctor --install-missing` automatically before deepen when needed:

```powershell
& .\.kilo\scripts\decreen.ps1 deepen $ARGUMENTS
```

Follow the skill's hard gates exactly: refresh workspace lifecycle first, stop if the workspace is still a temporary preview, and require/lazy-run Decreen agent auth before mutating a persistent workspace.

Run the appropriate local Decreen deepen workflow for `$ARGUMENTS` through `.kilo/scripts/decreen.ps1`; use monorepo `node packages/decreen-local/dist/cli.js ...` only when working from built local sources.

Do not access Decreen backend infrastructure directly. Use only Decreen HTTP APIs and local repository files.
On success, report the proposal/preview/apply result according to the skill. On failure, provide a short problem statement, one next action, and debug details only when the command failed or the user requested them.
