# ADR-0011 — the English pivot stays; the answer is rewritten, not translated

Status: accepted (2026-10-14).

Supersedes nothing. Amends [ADR-0009](0009-english-pivot-language-pipeline.md)
(keeps its pivot, replaces its answer-translation step) and adds evidence to
[ADR-0003](0003-multilingual-embeddings.md). Amended in turn by
[ADR-0012](0012-readers-language-and-a-talking-answer.md).

## Context

Two questions were open:

1. Is `intfloat/multilingual-e5-small` used for both ingestion and query?
2. If the embedding model is multilingual, is the translation step needed at
   all? The belief under test was: "ask in Hindi or Kannada, the English
   corpus still retrieves the right top-k, so we can drop translation."

And one complaint: answers in English read well, but the same answer in
Hindi or Kannada read as harder than the English, not easier.

## Decision 1 — one embedding model on both sides, no re-ingestion

`intfloat/multilingual-e5-small` has been the only model since the pipeline was
written (`git log -S"multilingual-e5" -- api/app/ingest.py` returns only the
three commits that built it). `QdrantStore.MODEL` is used for both
`upsert_texts` and `search_text`, so the query vector and the stored vectors
come from the same model by construction. The live collection is 384-dim Cosine,
which is e5-small. **No re-ingestion.**

## Decision 2 — the pivot stays, because it measurably works

Tested against the live collection: 5 questions × 4 languages, the same search
run twice — once on the raw text, once on the Groq translation — scored on
whether the Act that actually governs the question appeared in the top 8.

| | top-1 correct | in top 8 |
|---|---|---|
| raw query, no pivot | 7/20 | 15/20 |
| English pivot | **13/20** | **20/20** |

e5-small aligns topics, not legal terms. The failure is concentrated exactly
where the product lives:

- *"my husband beats me"* — raw Hindi/Hinglish/Kannada returned Special
  Marriage Act and the Hindu Succession Act. The pivot returned the Domestic
  Violence Act at rank 1 in all three.
- *"in-laws demanding dowry"* — raw Hinglish and Kannada returned the Indian
  Christian Marriage Act and the Indian Succession Act. Nothing in a
  non-English string says "dowry". The pivot returned the Dowry Prohibition
  Act at rank 1.

So the pivot stays. What changed is the prompt: `QUERY_PIVOT_PROMPT` now
pins the legal terms and forbids widening one into a generic word, because the
observed translation failure was `ಸಂಪತ್ತು ಕೋಲಿಕೆ` → "demanding property" and
`ಹಿಂದಿನವರು` (in-laws) → "former spouse", which sent retrieval to
succession law at rank 6 instead of the Dowry Prohibition Act at rank 1.

## Decision 3 — rewrite the answer natively instead of translating it

Translation reproduces the register of its source. A clean English sentence
containing "maintenance pendente lite" becomes a perfectly grammatical Hindi
sentence containing "मेंटेनेंस पेंडेंट लाइट" — still unreadable to the person who
asked. That is the complaint, and it is structural, not a prompt problem.

`rewrite_in_language` takes the **verified English draft** and rewrites it in
the reader's language under `LANG_PLAIN_RULES` + `NATIVE_SIMPLICITY_RULES`.
Two properties make it safe:

- **It cannot invent.** It is grounded on the draft the verifier already
  approved and is told to change wording only, never facts, numbers or
  timelines. Citations `[1]`, `[2]` and Act/section names stay in English.
- **It can be rejected.** Empty, too short, looping, or still in the wrong
  script → the English answer is used. A rewrite that made things worse is
  never shipped.

> **Amended 2026-10-15 (ADR-0012).** "Keep the structure" below is what let a
> rewrite read as line-by-line translation: holding the English sentence order
> produces exactly the register it was meant to remove. The rewriter is now told
> to re-say the answer naturally, and to keep the *facts and citations* rather
> than the English shape.

Naming the everyday word is what makes it work: `LANG_PLAIN_RULES` gives
"maintenance = मासगी / गुजारा देना", not "be simpler". A model told to be
simpler picks a shorter legal word.

### Bug this fixed in passing

The old path replaced the *composed* answer with the translation, discarding
the localized disclaimer, next-steps boilerplate and low-confidence warning
that `compose_answer` had appended. For Hindi and Kannada users those were
simply never shown. The rewrite now runs on the draft, and `compose_answer`
runs after it, so the localized furniture survives.

## Decision 4 — a failed pivot must not ask the user to repeat themselves

Slot extraction, scope detection and the plan all read English. When every
provider was in cooldown and the pivot returned nothing, a Hindi question
produced "what is this about?" — telling a user who had already explained
themselves that they had been unclear. `state["pivot_ok"]` now records whether
the pivot came back, and the planner skips the `["topic"]` clarification when
it did not.

## Consequences

- One extra model call per non-English answer. It shares the same provider
  (Groq) and fails soft to English.
- Non-English answers can be *less* verbose than the English draft by
  instruction; that is intended.
- The `\u0900-\u097F` script check caught a real self-inflicted bug: written
  `r"[\u0900-\u097F]"`, the raw string does not interpret `\u`, so the check
  matched nothing and silently disabled itself. There is a test that fails if
  this ever comes back.
- Retrieval quality is still limited by the corpus, not by the language. The
  corpus is 7 English family Acts; some Acts are thinly covered (the Dowry
  Prohibition Act has 18 chunks, the Muslim family Acts 9-10 each). That is
  the next thing worth fixing, and it affects every language equally.