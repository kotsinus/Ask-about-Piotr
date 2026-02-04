# Title
Architecture: boundaries, multi-service design, and pipeline-based backends

# Category
experience

# Problem
Complex products often accumulate hidden coupling, making them hard to change, observe, and scale. AI systems add additional uncertainty due to model behavior, evolving data, and cost/latency variability.

# My role
I design architectures with explicit boundaries, clear ownership, and observable workflows. In recent systems, I frequently use multi-service layouts (UI, APIs, pipelines, inference services) when it improves operational isolation and independent scaling.

# What I built
I build pipeline-driven backends where ingestion, extraction, enrichment, and serving are separated into stages with clear contracts. This supports reproducibility, debugging, and gradual enhancement, especially when AI/LLM components are involved.

# Scale and impact
The impact is that systems remain maintainable as they grow: services can be evolved or replaced without rewriting the whole product, and failures are isolated and diagnosable. This is reflected in designs like Decreen (multi-service knowledge graph) and the on-prem RAG platform (separate inference service).

# Tech stack
Typical building blocks include REST and GraphQL APIs, background workers (Celery), relational stores (PostgreSQL), vector search (pgvector/ChromaDB), caches/queues (Redis), and container-based deployments (Docker/Compose, Nginx).

# Key decisions and trade-offs
I choose multi-service boundaries when I need isolation of concerns like model lifecycle, long-running pipelines, or different scaling profiles, trading deployment complexity for clarity. When a monolith is sufficient, I avoid unnecessary split; the decision is driven by operational needs, not fashion.

# Links
- AI projects overview: assets/ai-projects/AI_Projects_Piotr_Synak.pdf
- CV: assets/cv/CV_Piotr_Synak.pdf
