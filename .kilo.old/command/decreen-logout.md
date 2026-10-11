---
description: Disconnect Decreen account
---

Use the `decreen-login` skill, specifically the `/decreen-logout` workflow.

Use the project wrapper so Windows runs Decreen through WSL when needed and QA endpoints are resolved consistently:

```powershell
& .\.kilo\scripts\decreen.ps1 logout
```

Report the logout result concisely. Never print tokens or credential file contents.
On failure, provide a short problem statement, one next action, and debug details only when the command failed or the user requested them.
