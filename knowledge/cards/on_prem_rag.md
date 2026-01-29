# Title
On-Premises Retrieval-Augmented Generation System

# Category (project | research | certification | experience)
project

# Problem
Many organizations require AI assistants that operate entirely on-premises due to security, privacy, or cost constraints. Typical SaaS-based RAG solutions do not meet these requirements and lack operational transparency.

# My role
System architect and lead developer. I designed and implemented the full stack, including model routing, retrieval, and deployment.

# What I built
A production-ready, containerized RAG platform that allows users to upload documents, build vector indexes, and query them via an AI assistant. The system supports multiple runtime-selectable backends, including baseline RAG, LangGraph-based agents, and LlamaIndex agents.

# Scale and impact
Designed for single-server and small-cluster deployments with GPU acceleration. Supports multiple models and can be operated fully offline. Suitable for internal knowledge bases and regulated environments.

# Tech stack
Frontend: React 18, Vite, Material UI. Backend: FastAPI (Python). LLM service: FastAPI-based microservice with model adapters. Data: PostgreSQL (metadata), ChromaDB (vector store), Redis. Agents: LangGraph, LlamaIndex. Infrastructure: Docker, Docker Compose, Nginx reverse proxy.

# Key decisions and trade-offs
Chose adapter-based model registry to allow runtime switching between models. Prioritized observability and health checks over maximum throughput. Accepted higher deployment complexity to enable offline and cost-controlled usage.

# Links (URL or file reference)
assets/ai-projects/AI_Projects_Piotr_Synak.pdf
