---
description: Show Decreen agent auth status
---

Use the `decreen-login` skill, specifically the `/decreen-auth-status` workflow.

Use the project wrapper so Windows runs Decreen through WSL when needed and QA endpoints are resolved consistently:

```powershell
& .\.kilo\scripts\decreen.ps1 status
```

Report whether the Decreen account is connected. Never print tokens or credential file contents.
On failure, provide a short problem statement, one next action, and debug details only when the command failed or the user requested them.
