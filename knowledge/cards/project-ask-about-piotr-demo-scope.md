# Title
Ask About Piotr demo: curated knowledge cards + controlled refusal behavior

# Category
project

# Problem
Generic assistants tend to hallucinate when information is missing, which is risky for professional demos and enterprise use. This demo needs an AI assistant that answers only from curated, verifiable knowledge and refuses outside-scope questions gracefully.

# My role
Designer and author of the Ask About Piotr demo and its underlying knowledge-card repository. I designed and populated a knowledge-card-based repository where each card is a standalone source of truth with an explicit schema. The goal is to make the assistant’s behavior predictable, auditable, and easy to evaluate against a fixed question set.

# What I built
A demo system based on curated knowledge cards derived from a CV, project descriptions, publication list, and certifications. The cards describe professional experience, AI projects, research contributions, certifications, leadership topics, and documented personal facts.

# Scale and impact
The impact is better evaluation: the 100 sample questions can be mapped to specific cards, and out-of-scope questions can reliably trigger refusal. This demonstrates a production mindset: grounding, scope control, and evidence-based answers instead of “always answer.”

# Tech stack
Frontend: Next.js (React). Backend: FastAPI (Python 3.12) with Pydantic and SQLAlchemy. Storage: PostgreSQL with pgvector for embedding search. LLM + embeddings: OpenAI API (model selection via env). Knowledge base: Markdown cards mounted read-only and ingested into pgvector for retrieval. Deployment: Docker Compose.

# Key decisions and trade-offs
The key trade-off is that strict grounding can feel less “chatty,” but it improves trust and reduces hallucinations. Refusal is treated as a feature, not a failure, and the demo makes that explicit to users and evaluators.

# Links
- AI projects overview: assets/ai-projects/AI_Projects_Piotr_Synak.pdf
