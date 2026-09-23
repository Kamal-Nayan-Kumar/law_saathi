# ADR-0003 — multilingual-e5-base embeddings

Status: accepted.

Context: Initial doc said all-MiniLM-L6-v2, which is English-only and fails Hindi/Kannada retrieval.

Decision: `intfloat/multilingual-e5-small` via Hugging Face Inference API
(no local model runs); Qdrant stores vectors only. Small variant is free
via the HF API and covers EN/HI/KN. (2026-09-24 update: local Sentence
Transformers runs dropped — Nayan's call, machines here can't run torch.)

Consequences: Needs HF_TOKEN at ingest time, but HI/KN semantic search works; chunks must record language.
