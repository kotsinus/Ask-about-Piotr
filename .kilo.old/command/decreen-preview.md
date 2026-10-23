---
description: Create a temporary Decreen preview
---

Use the `decreen-preview` skill.

Follow its user-facing output contract exactly.

Do not use `@decreen/local analyze` for this command. In the currently installed CLI, `analyze` performs local CGC analysis and does not upload a temporary preview. Use the `decreen-preview` skill flow instead: generate `.decreen/runs/latest.upload.md`, write `.decreen/runs/latest.source-evidence.json`, POST only the generated Mermaid artifact to `/api/v0/local-architecture-preview/from-mermaid`, write `.decreen/manifest.json`, and return the viewer link.

Use the QA Decreen endpoint for this workspace unless the user explicitly requests another target:

```powershell
$env:DECREEN_API = "https://decreen-qa.up.railway.app"
$env:DECREEN_FRONTEND_URL = "https://carto-prototype-qa.vercel.app"
```

Create a temporary Decreen architecture preview from the current repository: analyze runtime structure, generate `.decreen/runs/latest.upload.md`, write `.decreen/runs/latest.source-evidence.json`, upload only the generated Mermaid artifact, write `.decreen/manifest.json`, and return the viewer link and claim instructions.

Do not upload source files, source file contents, `.env` files, secrets, credentials, or the local evidence sidecar.
On success, mirror the Decreen preview summary without extra narration. On failure, provide a short problem statement, one next action, and debug details only when the preview could not be created or the user requested them.
