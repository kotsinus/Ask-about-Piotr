# Title
Databases and data modeling: relational core + specialized indexing

# Category
experience

# Problem
Data-intensive products must balance correctness, performance, and evolution as schemas and features change. AI-enabled systems add additional requirements such as vector similarity search, document metadata, and graph-like relationships.

# My role
I have extensive experience with database engines from both the inside (Infobright internals) and as an architect using relational databases in production systems. I typically use relational databases as the operational source of truth and add specialized indexes or stores when needed.

# What I built
In recent projects I used PostgreSQL as the core store, including pgvector for embedding search and Row-Level Security for multi-tenant isolation. In addition, I used ChromaDB for vector search in the on-prem RAG platform and built graph-backed models for connected knowledge representation in Decreen.

# Scale and impact
The impact is predictable operations and strong data integrity, while still enabling modern AI features like semantic search. Using standard relational foundations also simplifies backups, migrations, and operational ownership compared to more exotic stacks.

# Tech stack
Databases: PostgreSQL, MySQL, SQL Server (experience), Infobright engine. Extensions/stores: pgvector, ChromaDB. Modeling patterns include structured metadata schemas and explicit access controls (e.g., RLS).

# Key decisions and trade-offs
The trade-off is avoiding over-specialization: I add vector stores or graph layers when they provide clear capability benefits, but I keep an authoritative schema to prevent “data sprawl.” For schema evolution, I prefer migrations (e.g., Alembic) and versioned contracts so systems remain stable as features evolve.

# Links
- CV: assets/cv/CV_Piotr_Synak.pdf
- AI projects overview: assets/ai-projects/AI_Projects_Piotr_Synak.pdf

