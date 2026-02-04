# Title
Infobright: co-founding and building a C++ columnar analytics database

# Category
experience

# Problem
Analytical workloads need high-speed processing over large datasets with predictable performance. Traditional row-stores struggle with ad-hoc analytics and complex queries at scale, motivating specialized columnar storage and execution strategies.

# My role
I co-founded Infobright and served as chief architect, lead designer, and developer of the core C++ database engine. I also acted as Scrum Master for a database design group and supported customer-facing issue resolution with sales engineers.

# What I built
I designed and implemented key data structures and algorithms for query execution, including execution plans, rough queries, correlated sub-queries, joins, and aggregation. I participated in architectural decisions around parallelization, memory optimization, scaling strategies, partitioning, high availability, and the transition toward open source.

# Scale and impact
The engine was adopted for enterprise analytics workloads (described as Fortune 500 usage in my CV). The work produced multiple database-related patents and contributed to peer-reviewed publications on rough set / granular approaches to query execution and optimization.

# Tech stack
C/C++ core engine; SQL frontends for PostgreSQL/MySQL; Windows and Linux support. Engineering workflow included Agile practices and cross-functional collaboration.

# Key decisions and trade-offs
Using rough/approximate techniques can dramatically reduce compute, but requires careful semantics and user trust. Database internals work forces explicit trade-offs between performance, correctness, complexity, and maintainability. I favored designs that keep execution behavior explainable to engineers and debuggable in production.

# Links
- CV: assets/cv/CV_Piotr_Synak.pdf
- Publications list: assets/publications/Publications_Piotr_Synak.pdf
