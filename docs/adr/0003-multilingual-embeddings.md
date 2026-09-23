# ADR-0003 — multilingual-e5-base embeddings

Status: accepted.

Context: Initial doc said all-MiniLM-L6-v2, which is English-only and fails Hindi/Kannada retrieval.

Decision: `intfloat/multilingual-e5-small` run locally via Sentence Transformers; Qdrant stores vectors only. Small variant is free to run and covers EN/HI/KN.

Consequences: Larger embedding model locally, but HI/KN semantic search works; chunks must record language.
