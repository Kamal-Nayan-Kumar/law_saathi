# ADR-0009 — English-pivot language pipeline

Status: accepted.

Context: Users ask in EN/HI/KN, but the corpus and embeddings retrieve best
in English (ADR-0003). Maintaining three parallel pipelines is too much for
solo.

Decision: Detect input language → if not English, translate the query to
English (LLM step inside the T3 agent, no new vendor) → retrieve + reason
in English → render the final answer back in the user's language. Voice
uses Sarvam STT/TTS in the user's language at the edges.

Consequences: One retrieval path to eval; translation errors are possible
but visible in LangSmith traces; KN quality depends on the LLM, tracked in
the T10 golden set (10 Q&As per language).
