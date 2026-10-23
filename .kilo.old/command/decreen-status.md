---
description: Show local Decreen workspace status
---

Use the `decreen-status` skill.

Follow its user-facing output contract exactly.

This command is read-only. Do not upload data, create previews, refresh maps, deepen maps, claim workspaces, or modify remote Decreen state.

Use the QA Decreen endpoints for this workspace when a verbose or remote status check is needed:

```powershell
$env:DECREEN_API = "https://decreen-qa.up.railway.app"
$env:DECREEN_FRONTEND_URL = "https://carto-prototype-qa.vercel.app"
```

Read `.decreen/manifest.json`, current git metadata, local Decreen run-file existence, and auth presence only. Never print tokens or credential contents.

On success, return a concise status block and one primary next action. On failure, provide a short problem statement, one next action, and debug details only when status could not be determined or the user requested them.
