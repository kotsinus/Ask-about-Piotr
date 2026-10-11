---
description: Connect Decreen account
---

Use the `decreen-login` skill, specifically the `/decreen-login` workflow.

Use the project wrapper so Windows runs Decreen through WSL when needed and QA endpoints are resolved consistently:

```powershell
& .\.kilo\scripts\decreen.ps1 login
```

On success, report:

```text
Decreen account connected.
Credentials saved locally (~/.config/decreen/auth.json).
Agent token valid for 7 days.
```

Never print tokens or credential file contents.
On failure, provide a short problem statement, one next action, and debug details only when the command failed or the user requested them.
