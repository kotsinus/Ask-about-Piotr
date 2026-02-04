# Title
Decreen: AI-powered knowledge graph and onboarding assistant

# Category
project

# Problem
Teams operating in complex Jira/Confluence/GitHub environments face fragmented knowledge, slow onboarding, and documentation drift. Manual architecture documentation rarely stays current, which increases operational risk and slows delivery.

# My role
End-to-end engineer on the monorepo. I defined service boundaries and the data model, designed the AI-assisted pipelines, and implemented backend APIs, background processing, and core UI workflows. I designed the multi-service architecture and the AI-assisted extraction/enrichment approach, and I contributed hands-on across backend services and pipelines. I focused on making LLM usage constrained and pipeline-driven so the system remains dependable.

# What I built
I built a platform that synchronizes knowledge from Jira, Confluence, and GitHub, extracts entities and relations, and assembles them into a graph-backed model that can be queried via REST and GraphQL. The product includes a diagramming layer that automatically generates and maintains living architecture diagrams (systems, APIs, teams, flows) and a React-based UI for exploration and dashboards.

# Scale and impact
The core impact is reducing time-to-understand for engineers and leaders by making system knowledge queryable, connected, and continuously updated. By generating diagrams from live sources and highlighting gaps, Decreen is designed to reduce documentation drift and improve onboarding quality without relying on manual upkeep.

# Tech stack
Frontend: React 18, Vite, Material UI, visualization libraries (e.g., Nivo, Recharts, React Flow, Three.js). Backend: Node.js/Express/Sequelize for REST, and Python/FastAPI/Strawberry for GraphQL and services. Pipelines: Celery workers; data: PostgreSQL + pgvector; cache/queues: Redis; auth: Auth0; integrations: Atlassian + GitHub; dev: Docker/Compose, Jest/Vitest/Pytest.

# Key decisions and trade-offs
- I combined a knowledge graph with embeddings to support both precise structural queries (graph) and fuzzy semantic access (vector search) without forcing everything into one representation. LLMs are used for extraction, summarization, and classification rather than as an unconstrained “answer engine,” trading some flexibility for reliability. 
- Automatic diagrams trade perfect completeness for continuous, explainable updates driven by source systems.
- I split REST and GraphQL into dedicated services to keep API layers independent from ingestion and pipeline workloads.
- I automated entity extraction and diagram generation to reduce documentation drift, accepting higher ingestion and processing complexity.


# Links
- AI projects overview: assets/ai-projects/AI_Projects_Piotr_Synak.pdf

