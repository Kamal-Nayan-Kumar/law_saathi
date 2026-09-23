# LawSaathi — Finalized Stack (grill-with-docs, 2026-09-23)

Solo college agentic-AI project. All 10 features, EN+HI+KN, dictation voice now, live-talk Phase 2.

| Layer | Choice | Why (one line) |
| ----- | ------ | -------------- |
| Frontend | Next.js: landing → login/signup → chat; admin portal for ingestion | Reuse campus_saathi patterns: dot-grid thread bg, bubbles, sources box, admin dropzone + confirm modal (ADR-0007) |
| Theme | Indian family-law feel (deep maroon/slate + marigold, serif display) | Distinct from Campus Saathi slate; WhatsApp integrations out of scope |
| Backend | Python FastAPI on Render | API gateway: auth, validation, rate-limit, logs |
| Agents | LangGraph, 5 nodes + verify-retry loop | Viva's core diagram: intent → planner → tools → verifier → response |
| LLM | Groq `gpt-oss-120b` primary, OpenRouter fallback | Fast + free-tier friendly, fallback avoids demo failure |
| Embeddings | `intfloat/multilingual-e5-small` (local, Sentence Transformers) | Small, free, covers EN/HI/KN; MiniLM dropped (English-only) |
| Vectors | Qdrant Cloud | Managed semantic search, stores e5-small vectors + provenance |
| App data | Neon Postgres | Users, sessions, history, memory, preferences, logs |
| Web search | Firecrawl | Real-time search + extraction for Tool agent |
| Voice now | Sarvam STT + TTS (push-to-talk) | Best HI/KN quality; ElevenLabs dropped (weak KN + cost) |
| Voice Phase 2 | LiveKit realtime | Flagged off for MVP, solo risk too high to bundle |
| Observability | LangSmith only | Traces LangGraph directly; Langfuse dropped, one tool for solo |
| Eval | Ragas (faithfulness + answer relevancy + context recall) on 30 golden Q&As via LangSmith | Proves verified-answers claim |
| Corpus | `vaquill/open-india-law` legislation filtered to 6 family acts + `enerscript/MARRIAGEACT` + India Code PDFs as truth; 20–30 curated judgments; `steamed-potatop/indian-family-law-data` for eval seed | No random Kaggle dumps; Pakistan-acts dataset explicitly rejected |

## Repo

One repo: `web/` (Next.js) + `api/` (FastAPI). Real login, per-user history/memory in Neon.

## Family acts (MVP corpus)

Hindu Marriage Act 1955, Special Marriage Act 1954, Hindu Adoption & Maintenance Act 1956, Hindu Succession Act 1956, Guardians & Wards Act 1890, Protection of Women from Domestic Violence Act 2005 (+ Indian Divorce Act 1869 where structured data exists).
