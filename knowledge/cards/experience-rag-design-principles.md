# Title
RAG and LLM engineering principles: when to use models vs deterministic logic

# Category
experience

# Problem
LLMs can add value in summarization, extraction, and natural-language interaction, but they introduce non-determinism, cost, and hallucination risk. Production systems need a disciplined approach that decides where probabilistic methods are appropriate and where deterministic logic is safer.

# My role
I design RAG and agentic systems with explicit retrieval layers, constrained generation, and clear fallbacks. I also decide early which tasks must remain deterministic (e.g., security boundaries, workflow state, authoritative facts) and which can be LLM-assisted.

# What I built
In Decreen, LLMs are used in constrained, pipeline-driven roles such as information extraction, classification, summarization, and generating personalized onboarding tasks from organizational context. In the on-prem RAG platform, retrieval and orchestration are explicit and switchable (baseline vs agentic backends), and the inference service is isolated for operational control.

# Scale and impact
The impact is that LLMs amplify human workflows without becoming an uncontrolled “source of truth.” This supports controlled hallucination mitigation by grounding responses in retrieved context and by limiting model roles to tasks with verifiable outputs.

# Tech stack
Key building blocks: embeddings (OpenAI or Sentence Transformers), vector stores (pgvector/ChromaDB), API backends (FastAPI), agent frameworks (LangGraph, LlamaIndex), and containerized deployment. Model choices include both hosted models and on-device Hugging Face options for cost/offline constraints.

# Key decisions and trade-offs
I avoid using LLMs where correctness must be exact and verification is hard (e.g., authorization decisions, financial calculations without explicit sources, or critical incident response without human review). I accept that constrained pipelines may reduce “magic” conversational flexibility, but they improve reliability, debuggability, and cost control.

# Links
- AI projects overview: assets/ai-projects/AI_Projects_Piotr_Synak.pdf
- CV: assets/cv/CV_Piotr_Synak.pdf
