---
description: Create a Decreen preview with local evidence
---

Use the `decreen-analyze2` skill.

Analyze the current repository, generate the Mermaid C4 markdown artifact with a mandatory `## Containment Map`, write the local source-evidence sidecar, POST only the Mermaid artifact to the Decreen preview `/from-mermaid` endpoint, write local Decreen metadata, and return the viewer link.

Do not use `@decreen/local analyze` for this command. In the currently installed CLI, `analyze` performs local CGC analysis and does not upload a temporary preview. Use the skill's `/from-mermaid` upload flow.

Use the QA Decreen API for this workspace unless the user explicitly requests another target:

```powershell
$env:DECREEN_API = "https://decreen-qa.up.railway.app"
```

Write source evidence only to `.decreen/runs/latest.source-evidence.json`. Do not embed it in the uploaded artifact and do not POST it to Decreen.
On failure, provide a short problem statement, one next action, and debug details only when the preview could not be created or the user requested them.
