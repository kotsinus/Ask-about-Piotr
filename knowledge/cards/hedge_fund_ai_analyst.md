# Title
Hedge Fund AI Analyst Platform

# Category (project | research | certification | experience)
project

# Problem
Investment research workflows in hedge funds are complex, multi-step, and time-consuming. Analysts must process large volumes of unstructured documents and coordinate multiple analysis steps under strict security constraints.

# My role
Lead architect and hands-on engineer. I designed the end-to-end workflow, LLM orchestration, and backend services.

# What I built
An AI Analyst platform that automates a 28-step investment research workflow. The system ingests financial documents, orchestrates analysis across multiple LLM providers, tracks progress in real time, and generates structured briefing papers. It supports multi-tenant isolation and enterprise-grade security.

# Scale and impact
Designed for professional investment teams with strict latency and security requirements. The platform significantly reduces analyst effort and standardizes research outputs.

# Tech stack
Frontend: React 18, TypeScript, Material UI, WebSockets. Backend: FastAPI (Python 3.12), SQLAlchemy, JWT authentication. Data: PostgreSQL with Row-Level Security, Redis. Document processing: PyPDF2, Unstructured, Tesseract OCR. LLMs: OpenAI GPT models, Anthropic Claude models, Google Gemini. Infrastructure: Docker, Docker Compose, Nginx.

# Key decisions and trade-offs
Implemented multi-LLM routing to balance cost, latency, and output quality. Used explicit workflow orchestration instead of a single agent to improve predictability. Accepted higher system complexity to achieve enterprise-grade security and auditability.

# Links (URL or file reference)
assets/ai-projects/AI_Projects_Piotr_Synak.pdf
