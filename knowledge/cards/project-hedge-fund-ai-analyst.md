# Title
Hedge Fund AI Analyst: automated 28-step investment research workflow

# Category
project

# Problem
Investment research workflows are document-heavy, time-sensitive, and prone to inconsistency when executed manually. A useful AI assistant must orchestrate many steps, track progress, and preserve auditability and tenant isolation.

# My role
I designed and implemented an AI Analyst platform that automates a defined multi-step workflow end-to-end, including document ingestion, LLM routing, and result packaging. I focused on enterprise-grade concerns such as multi-tenancy, security boundaries, and real-time visibility into workflow state.

# What I built
I built a React/TypeScript frontend with real-time updates, a FastAPI backend with JWT auth, and a workflow layer that orchestrates multi-provider LLM analysis and produces briefing papers and structured outputs. The system supports ingestion of financial documents and tracks workflow progress across steps to provide operational transparency.

# Scale and impact
The workflow automates a 28-step process, enabling repeatability and faster turnaround for research deliverables. Multi-provider routing enables using different LLMs for different subtasks and supports controlled comparison across providers (A/B testing) to manage quality and cost.

# Tech stack
Frontend: React 18 + TypeScript, Redux Toolkit, WebSockets (Socket.IO client). Backend: FastAPI (Python 3.12), Pydantic v2, SQLAlchemy 2, Alembic, JWT, Uvicorn/Gunicorn. Data: PostgreSQL 16 with Row-Level Security, Redis, Nginx, Docker/Compose. Docs: PyPDF2, Unstructured, pdf2image, Tesseract OCR. Observability/testing: Prometheus metrics, structured logging, pytest/Vitest.

# Key decisions and trade-offs
I used Row-Level Security to enforce tenant isolation at the database level, trading some query complexity for stronger guarantees. Multi-provider LLM routing trades operational complexity for resilience and the ability to tune tasks to model strengths. Real-time progress visibility trades additional frontend/backend wiring for better user trust and operability.

# Links
- AI projects overview: assets/ai-projects/AI_Projects_Piotr_Synak.pdf

