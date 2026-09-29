# Make it actually agentic

## The problem, honestly

`build_graph()` (`api/app/agent.py:1334`) builds a LangGraph `StateGraph`. Nothing calls it.
Production runs `run_agent()`, a hand-written `if`/`while` chain. LangGraph is never imported.

Three specific reasons it doesn't feel agentic:

1. **No model decides anything.** The LLM is called in three places, all text-in/text-out:
   contextualize (`:581`), translate (`:604`), write the answer (`:1144`). It never picks a tool,
   never picks a query, never reacts to a failure.
2. **`node_tools` has no tools to choose.** It runs the same two calls every question —
   `search_text(query_en, top_k=5)` and `web_search(query_en)`. Fixed query, no choice of act.
3. **`node_verifier` cannot fail on relevance.** `evidence_sufficient()` (`:831`) asks "is any
   text non-empty and score >= `min_score`". `min_score` defaults to `0.0`
   (`schemas.py:74`, passed through untouched at `routers_chat.py:160`). So anything with text
   in it is "verified". The retry ladder in `broaden_query()` is 3 hardcoded strings, not a
   reaction to *why* retrieval failed.

Topic is decided by `TOPIC_KEYWORDS` regex *before* any model runs. That is why the Thinking
panel shows the same four steps for every question.

## Target graph

```
START → intent → planner ─┬─(low confidence)→ response → END
                          ↓
                        tools      executes the planner's chosen steps
                          ↓
                        reason     model writes the explanation, cites [1] [2]
                          ↓
                        verifier   model judges grounding → next_queries
                          └─(insufficient, retries left)→ tools → reason → verifier
                          ↓
                        response   assemble, translate, next steps, disclaimer → END
```

Six nodes, and the loop is entered by a **model decision**, not a threshold.
This matches `docs/initial-plan.md` Steps 4–13 and §50 (self-reflection loop).

## The three changes

### 1. The planner chooses the act and the tools — `plan_search()`

Give the model the question and the catalogue of available acts and tools; it returns JSON:

```json
{"governing_act": "Guardians and Wards Act 1890",
 "reasoning": "Custody of a minor is decided there, not the Divorce Act.",
 "steps": [{"tool": "search_acts", "query": "custody minor child guardianship", "why": "..."},
           {"tool": "search_web",   "query": "...", "why": "..."}]}
```

Tool registry: `search_acts` (vector search, act-biased), `search_web` (Firecrawl),
`read_section` (exact section by number).

**Fallback:** no LLM, or unparseable JSON, or a tool it did not name → today's regex
`TOPIC_ACT` behaviour. The no-key demo and all existing tests keep working unchanged.

### 2. Verification is a model — `verify_grounding()`

The judge reads the draft answer plus the numbered passages and returns
`{"verdict": "grounded"|"insufficient", "reason": "...", "next_queries": [...]}`.

`evidence_sufficient()` stays as a hard floor: if there is no text at all, no judge rescues
it. It is no longer the *only* gate.

`min_score` keeps working as a hard floor, but stops being the whole story.

The `next_queries` the judge returns replace the hardcoded `broaden_query()` ladder when a
model is present. The ladder stays as the fallback.

### 3. LangGraph is the real runtime

`run_agent()` calls `build_graph()` when langgraph imports, and keeps the inline loop as the
fallback for bare checkouts. Both paths must produce an identical `trace`.

A test asserts both paths produce the same trace shape, so the two can't silently diverge.

## Cost

Roughly 6 LLM calls per question, up from ~4: +1 planner, +1 verifier.
Groq free tier absorbs this; it is the single biggest cost change and worth watching.

## Acceptance criteria — strict

Not "it works". Each must be **falsifiable**:

1. `pytest api/tests -q` — 81 existing tests still pass, plus new ones.
2. The model is asked to plan. Kill the planner call and planning must visibly fall back.
   *Test:* a fake LLM recording calls proves `plan_search` reaches the model.
3. The model picks a *different act* than the keyword table would. "Who gets custody of the
   child in a divorce?" must reach Guardians & Wards via a model decision.
   *Test:* fake planner returns G&W, assert the retrieval query names G&W.
4. The verifier can **reject** evidence that the old code accepted. A high-score but
   off-topic passage set must come back `insufficient` and trigger a retry.
   *Test:* fake judge returns `insufficient`, assert `retries == 1` and tools ran twice.
5. A draft answer that invents a section gets caught.
   *Test:* judge sees a citation not in the passages → `insufficient`.
6. The loop is entered by the judge, not a score threshold.
7. Both run paths (graph + fallback) give the same `trace`.
8. Every new model call is optional. No keys → identical behaviour to today, no crash.
9. The Thinking panel shows the plan and the verdict, not just node names.

## Non-goals

Voice, GitHub issue cleanup, and doc ingestion stay out of this change — separate passes.

## Outcome (status)

All three built. `pytest api/tests` → **133 passed** (81 before, +52 new).

### What changed
- `node_planner(state, llm)` — model picks the governing Act and the tool steps;
  falls back to `default_plan()` (the old keyword table) with no model or junk JSON.
- `node_tools` executes each planned step; `search_acts` / `read_section` are
  anchored to the chosen Act and re-ranked toward it.
- `node_reason` — new node. Writes the draft *before* verification, so the
  verifier has something to check.
- `node_verifier(state, min_score, llm)` — model judge (`verify_grounding`).
  `evidence_sufficient()` remains the hard floor; `min_score` is no longer the
  whole test.
- `build_graph()` is now the real runtime, not dead code.
- Six nodes: intent → planner → [clarify|oos] → tools → reason → verifier ⇄ tools → response.

### Bugs found by testing, not reading
| Bug | Effect |
|---|---|
| `has_floor` branch never cleared `needs_retry` | infinite retry loop once LangGraph was installed |
| `llm=None` fell through to the live provider | `.env` leaked into the test suite; suite was non-deterministic and took 47s |
| `write_plain_answer` traced as `response` from inside `reason` | Thinking panel showed steps out of order |
| `next_queries` shorter than the plan | remaining plan steps re-ran the failing query |
| verifier rejected drafts for *correctly admitting* a gap | worse answers than before; rubric rewritten |
| rejected draft reached user unlabelled | safety hole; added `NOT_FULLY_VERIFIED` banner |

### Scope fixes (found by asking real questions)
- `"My father died and my brother is taking the ancestral land"` was **refused**
  as property law. Inheritance is family law — now routes to Hindu Succession Act 1956.
- `"What is the Special Marriage Act?"` was answered with *"what is this about?"*.
- Out-of-scope questions were turned into clarifying questions instead of the redirect.
- Inter-religious marriage cited the Hindu Marriage Act; now the Special Marriage Act 1954.

### Retrieval
`_rank_toward_section()` — a user-named section now outranks the Preamble.
Measured on the live corpus, embeddings put "Section 13B" **fourth**, 0.005 behind
the Preamble, so pure similarity cannot answer "what is Section 13B".

### Known open
- **Every HF corpus has a stale Special Marriage Act s.28** — pre-2018 timings
  ("one year" separation, "six months" window). Current law is six months'
  separation plus a one-year cooling-off period. This affects the single most
  common family-law query in India and must be hand-patched before any demo.
- Corpus provenance: 18 chunks tagged `Hindu Marriage Act 1955` contain Special
  Marriage Act text, including a non-existent `Section 28`.
- No Muslim personal law in the corpus (Code of Muslim Personal Law 1936,
  Muslim Family Laws Act 1963, Guardianship and Maintenance 1926 are on neither
  India Code nor any HF dataset).

---

## Round 2 — memory, follow-ups, recovery, amendments

`pytest api/tests` → **157 passed** (81 → 157).

### 1. Long-term memory
`node_intent` now reads `state["memory"]`:
- `last_topic` is carried when the turn names no topic of its own, so
  "and what about my situation?" the next day no longer restarts from nothing.
  The Thinking panel says it remembered — silently remembering is worse than
  not remembering, because the user cannot tell which happened.
- `state["memory_updates"]` carries the topic back; `routers_chat` persists it.
- **Tone was being destroyed on every request.** `body.tone` is always
  populated (schema default `"simple"`), so `if body.tone != tone_mem` wrote
  `"simple"` over the saved preference each turn. Now only an explicit
  non-default choice overwrites, and the agent is called with the saved tone.

### 2. Follow-up resolution
The actual bug: `query_en` was seeded from the raw query and only refreshed
inside the `lang != "en"` branch, so **English follow-ups retrieved on the
unresolved text while Hindi ones retrieved on the resolved text.**

Now: a reply identical to the input triggers one insisting retry, with
`looks_standalone()` short-circuiting the retry when the message already names
an Act/section or is long enough to stand alone (a correct model echoes such a
message, and an echo used to be indistinguishable from a failure).

### 3. Recovery planning
Firecrawl was paid for and never used: the first plan rarely had a web step, and
re-phrasing the same Act search cannot produce new hits. `node_tools` now asks
the planner for a second plan once retries are exhausted and evidence is empty.
This lives in `node_tools`, not in the LangGraph edge function — it originally
lived in the edge, and **only the inline path re-planned**.

### 4. Amendment guard (SMA s.28 / HMA s.13B)
Measured: the notice ranks **first** on a bare query (0.897) but drops out of
the **top 16** once the query is anchored with the Act name, which the planner
always does. So it is fetched by a `kind=amendment_notice` payload filter
(needed a Qdrant keyword index on `act`/`section`/`kind`), not by relevance.

Prompts were not enough: the writer ignored the notice and the verifier
**approved** the stale figure, because in the stale passage the stale figure
*is* correct. `apply_amendment_guard()` now appends a caveat naming the
amending Act whenever a notice is in evidence and the draft quotes a duration.
It asserts no replacement figure, because the amended text could not be
sourced from a primary source — India Code itself still publishes the
pre-amendment consolidation.

## Corrections made during this work

Recorded because each was stated confidently and was wrong:
1. "Section 13B is not in the corpus" — it is. It was a retrieval/ranking
   problem; the regex used to check (`\b` at end-of-string) never matched.
2. "The Hindu Minority and Special Marriage Act 1950 is missing and governs
   inter-religious marriage" — its marriage provisions were repealed into the
   Special Marriage Act 1954. No corpus contains it for that reason.


