# Title
API design: REST vs GraphQL and when to use each

# Category
experience

# Problem
User-facing platforms often need stable contracts for integration while also supporting flexible exploration and evolving frontend needs. Choosing the wrong API style can either slow delivery (too rigid) or create operational complexity (too flexible without governance).

# My role
I design APIs based on consumer needs and the data access patterns of the product. In some systems I provide both REST and GraphQL, using each where it fits best rather than forcing a single approach.

# What I built
In Decreen, insights are exposed via REST and GraphQL: REST supports integration-friendly endpoints and predictable operational behavior, while GraphQL supports exploration-heavy UI queries over a connected domain model. In the on-prem RAG and AI Analyst systems, FastAPI provides structured endpoints with clear error handling and auth, and real-time updates are delivered via WebSockets when needed.

# Scale and impact
The practical impact is faster frontend iteration without constantly adding new bespoke endpoints, while preserving stable integration points for external clients. A dual approach also reduces pressure to overload one API style beyond its strengths.

# Tech stack
REST: Node.js/Express and Python/FastAPI; GraphQL: Strawberry GraphQL. Supporting components include auth (e.g., JWT/Auth0), structured logging, and reverse proxies (Nginx).

# Key decisions and trade-offs
GraphQL adds schema governance and operational monitoring requirements, so I use it when query flexibility matters and the domain graph is rich. REST is preferred for simple, stable workflows and external integrations. I avoid “GraphQL everywhere” when it would complicate caching, authorization, or debugging.

# Links
- AI projects overview: assets/ai-projects/AI_Projects_Piotr_Synak.pdf
