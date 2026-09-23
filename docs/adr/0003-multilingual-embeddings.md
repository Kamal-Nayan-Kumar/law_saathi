# ADR-0003 — multilingual-e5-base embeddings

Status: accepted.

Context: Initial doc said all-MiniLM-L6-v2, which is English-only and fails Hindi/Kannada retrieval.

Decision: `intfloat/multilingual-e5-small` via Qdrant Cloud Inference
(free hosted model, server-side embedding on upsert/query); Qdrant stores
vectors only. Covers EN/HI/KN. (2026-09-24 updates: local Sentence
Transformers dropped — no local torch runs on these machines; then the HF
Inference API detour dropped too once Cloud Inference proved live 4/4 on
EN/HI/KN probes. No HF_TOKEN needed.)

Consequences: Needs QDRANT_URL/QDRANT_API_KEY at ingest time, but HI/KN semantic search works; chunks must record language.
