# ADR-0009 — English-pivot language pipeline

Status: accepted. Partly amended by
[ADR-0011](0011-pivot-stays-native-rewrite.md).

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

## Amendment (2026-10-14, ADR-0011)

The first two steps are unchanged and were re-validated against the live
collection (pivot: 13/20 top-1 correct vs 7/20 without it).

The last step changed. "Render the final answer back in the user's language"
was implemented as *translate the finished English answer*. That preserves
register across intact, so a plain English answer arrived in Hindi still full
of untranslated legal terminology. The answer is now **rewritten** natively in
the user's language, grounded on the same verified English draft, with the
everyday word named for each legal term and English kept as the fallback.

## Amendment (2026-10-15, ADR-0012)

"Detect input language → translate to English → retrieve + reason in English →
answer in the user's language" is still the shape, with two changes. The
translation step is no longer the only search: the reader's own words are
retrieved as well and merged, because the multilingual embeddings are the safety
net for the terms a pivot drops. And "answer in the user's language" now covers
the step log and the source tags, not just the answer — see
[ADR-0012](0012-readers-language-and-a-talking-answer.md).
