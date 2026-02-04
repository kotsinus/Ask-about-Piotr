# Title
On-prem RAG platform with switchable agent backends

# Category
project

# Problem
Many organizations need Retrieval-Augmented Generation that runs locally or in controlled environments, with predictable operations and the ability to swap models and orchestration strategies. Typical prototypes lack deployment discipline, observability, and clear separation between UI, retrieval, and inference.

# My role
I designed the system as a production-ready, containerized platform and emphasized clean boundaries between the UI, API, vector store, and LLM inference service. I also defined the runtime-switchable orchestration modes to support experimentation without rewriting the product.

# What I built
I built a React web UI, a FastAPI backend, a dedicated LLM inference microservice with model adapters, and supporting data services behind an Nginx reverse proxy. Users can upload documents, build vector indexes, and query through an assistant that can run as baseline RAG, a LangGraph agent, or a LlamaIndex agent.

# Scale and impact
The platform is designed to move beyond proof-of-concept by shipping with Docker Compose profiles for dev/test/prod, health checks, structured logging, and optional SSL/TLS. The runtime-switchable backend enables controlled A/B testing of orchestration approaches while keeping deployment and data services stable.

# Tech stack
Frontend: React 18, Vite, Material UI. Backend: FastAPI with structured logging and global exception handling. LLM service: FastAPI with adapters for Hugging Face/Sentence Transformers and optional CUDA. Agents: LangGraph, LlamaIndex. Data: PostgreSQL (metadata), ChromaDB (vectors), Redis (cache/session). Infra: Nginx, Docker/Compose; optional tools in profiles (e.g., Jupyter, Prometheus, SonarQube).

# Key decisions and trade-offs
I separated inference into its own microservice to isolate model lifecycle, GPU usage, and readiness checks, trading a slightly more complex deployment for operational clarity. The registry-driven adapter approach trades some immediate simplicity for the ability to manage multiple models consistently. Offering both “baseline RAG” and “agent” modes recognizes that agents add power but can increase non-determinism and cost.

# Links
- AI projects overview: assets/ai-projects/AI_Projects_Piotr_Synak.pdf

