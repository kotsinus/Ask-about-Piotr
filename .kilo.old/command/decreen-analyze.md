---
description: Create a Decreen architecture map preview
---

Use the `decreen-analyze` skill.

Analyze the current repository, generate the Mermaid C4 markdown artifact with a mandatory `## Containment Map`, POST it to the Decreen preview `/from-mermaid` endpoint, and return the viewer link.

Do not use `@decreen/local analyze` for this command. In the currently installed CLI, `analyze` performs local CGC analysis and does not upload a temporary preview. Use the skill's `/from-mermaid` upload flow.

Use the QA Decreen API for this workspace unless the user explicitly requests another target:

```powershell
$env:DECREEN_API = "https://decreen-qa.up.railway.app"
```

Do not upload source files, source file contents, `.env` files, credentials, or local evidence sidecars.
On failure, provide a short problem statement, one next action, and debug details only when the preview could not be created or the user requested them.
