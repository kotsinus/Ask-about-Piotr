# Title
Observability and operations: making AI and data systems debuggable

# Category
experience

# Problem
AI-enabled systems can fail in subtle ways: retrieval quality drifts, costs spike, pipelines break, and model behavior changes. Without observability, teams cannot diagnose issues or make safe improvements.

# My role
I design systems with operational visibility as a first-class requirement, including health endpoints, structured logging, and metrics. In recent projects I also applied production-friendly deployment patterns (profiles, readiness checks, reverse proxies) to keep systems stable.

# What I built
I implemented structured logging and global exception handling in FastAPI services, health checks for containerized services, and metrics instrumentation (e.g., Prometheus client metrics) where it supports runtime monitoring. I also use test suites across stacks (pytest and Vitest/Jest) to catch regressions early.

# Scale and impact
The impact is faster incident diagnosis and safer iteration on both ML and non-ML components. This is especially important when LLM-based pipelines are used for extraction or multi-step workflows, because failures can present as “bad answers” rather than explicit crashes.

# Tech stack
FastAPI with structured logging; Prometheus client metrics (in the AI Analyst platform); Docker/Compose health checks; Nginx reverse proxy; testing frameworks including pytest, Vitest, and Jest.

# Key decisions and trade-offs
Observability adds upfront work but pays back by enabling controlled experimentation and reliable operations. For AI features, I prefer measurable signals (retrieval hit rates, workflow step success, cost/latency budgets) over subjective “it feels better” evaluation.

# Links
- AI projects overview: assets/ai-projects/AI_Projects_Piotr_Synak.pdf

