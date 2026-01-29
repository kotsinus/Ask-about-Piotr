# Title
Decreen – AI-powered Knowledge Graph and Onboarding Assistant

# Category
project

# Problem
Teams operate in complex software environments with unclear system boundaries and fragmented documentation spread across Jira, Confluence, and GitHub. Manual documentation quickly becomes outdated, making onboarding slow and system understanding unreliable. Teams need a single, queryable source of truth with up-to-date architectural context and automatically maintained diagrams.

# My role
End-to-end engineer on the monorepo. I defined service boundaries and the data model, designed the AI-assisted pipelines, and implemented backend APIs, background processing, and core UI workflows.

# What I built
A multi-service platform that synchronizes Atlassian and GitHub content, extracts entities and relationships using AI-assisted pipelines, and assembles them into a knowledge graph backed by PostgreSQL with pgvector. The system exposes REST and GraphQL APIs and provides a React-based UI with dashboards, project exploration, and graph visualizations. A core feature is automated generation and maintenance of living architecture diagrams derived directly from ingested data.

# Scale and impact
Designed to support continuous ingestion and enrichment across multiple services in team and enterprise environments. The platform keeps organizational knowledge, onboarding workflows, and architectural views consistently up to date via APIs, dashboards, and scheduled pipelines.

# Tech stack
Frontend: React, Vite, Material UI, vis-network, amCharts. Backend: Node.js (Express, Sequelize), Python (FastAPI, Strawberry GraphQL). Data: PostgreSQL with pgvector, Redis. Processing: Celery workers and offline pipelines. AI/ML: LLM-based extraction, classification, summarisation, and embedding pipelines using OpenAI and optional Hugging Face models. Infrastructure: Docker, Docker Compose.

# Key decisions and trade-offs
- Combined a knowledge graph with embeddings to preserve explicit relationships while enabling semantic search.
- Split REST and GraphQL into dedicated services to keep API layers independent from ingestion and pipeline workloads.
- Automated entity extraction and diagram generation to reduce documentation drift, accepting higher ingestion and processing complexity.

# Links
assets/ai-projects/AI_Projects_Piotr_Synak.pdf
