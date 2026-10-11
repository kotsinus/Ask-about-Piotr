---
description: Finalize Decreen source grounding
---

Use the `decreen-finalize` skill.

Use the project wrapper so Windows runs Decreen through WSL, where the managed CGC/Kuzu runtime is supported. The wrapper sets the QA endpoints for this workspace and runs `doctor --install-missing` automatically before finalization when needed:

```powershell
& .\.kilo\scripts\decreen.ps1 finalize --upload
```

If authentication is missing, report one next action only:

```powershell
& .\.kilo\scripts\decreen.ps1 login
```

On success, mirror the Decreen finalization summary without extra narration.
On failure, provide a short problem statement, one next action, and debug details only when the command failed or the user requested them.
