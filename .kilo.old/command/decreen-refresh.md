---
description: Refresh a persistent Decreen workspace
---

Use the `decreen-refresh` skill.

Use the project wrapper so Windows runs Decreen through WSL, where the managed CGC/Kuzu runtime is supported. The wrapper sets the QA endpoints for this workspace and runs `doctor --install-missing` automatically before refresh steps when needed.

Start refresh context with:

```powershell
& .\.kilo\scripts\decreen.ps1 refresh --local-only
```

Follow the refresh flow exactly:

Run the C4 prompt from the refresh context and write the required refresh artifact files, especially `docs/c4-architecture.mermaid.md`.

Then upload:

```powershell
& .\.kilo\scripts\decreen.ps1 refresh --upload
```

If authentication is missing, report one next action only:

```powershell
& .\.kilo\scripts\decreen.ps1 login
```

Do not use `/decreen-analyze2` preview flow or `/from-mermaid` for refresh.
On success, mirror the Decreen refresh summary without extra narration. On failure, provide a short problem statement, one next action, and debug details only when the command failed or the user requested them.
