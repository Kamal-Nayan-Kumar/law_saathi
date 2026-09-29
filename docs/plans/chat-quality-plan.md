# LawSaathi — chat quality plan

Found by end-to-end testing on the deployed site (login → chat, EN/HI/KN) on 2026-09-29.

## Verified working

- Login/signup on `law-saathi.vercel.app` (after the Neon trusted-domain fix)
- Session + history sidebar
- All 5 LangGraph nodes run: `intent → planner → tools → verifier → response`
- Thinking toggle renders per-step detail with "— done"
- RAG retrieval returns real bare-act sections
- Markdown answers, disclaimers, next steps
- English → retrieval → English answer, 5 citations
- Cost control: `LAWSAATHI_TRACE` modes, node tracing off by default

## Bugs found (all reproduced)

### B1 — Infinite clarification loop (CRITICAL)
`missing_for()` checks `is_followup` *after* topic/divorce_type. A follow-up
whose topic fails extraction returns `["topic"]` forever, so the bot re-asks
the same question and never retrieves.

Reproduced: `"मुझे तलाक चाहिए?"` → clarify → `"आपसी सहमति से तलाक"` →
**same clarification again**, 0 citations. English `lang` masked it because
`contextualize` rewrote the query in English.

Fix: `is_followup` short-circuits first. Also: never ask the same slot twice
in one session.

### B2 — Wrong topic for act-name questions
`extract_slots("Section 13B of the Hindu Marriage Act?")` → `topic: marriage`.
"Marriage Act" matches the `marriage` keyword, but 13B is *divorce by mutual
consent*. The answer's "Quick answer" then describes marriage law for a
divorce question.

Fix: an exact section number wins; drop bare act names from topic keywords.

### B3 — No Sources block in the UI
`compose_answer` returns citations in state, but the answer markdown has no
sources section and the page renders none. User asked for blue numbered
inline citations plus a Sources block at the bottom.

### B4 — No `web_search` in the Thinking steps
Firecrawl key is present but `web_search` is never shown in the trace, and
its failures are silent. User asked for `web_search:"query"` in the steps.

### B5 — Kannada/Hindi grammar bug in clarification text
`"यह आपसी सहमति से तलाक है या विवादित तलाक क्या है?"` — the template lead +
lowercased first word produces broken Hindi. `clarification_question()`
lowercases `asked[0][0]`, which is wrong for non-Latin scripts.

## Decisions already made

- Translation stays **last** (retrieve in English, answer in user language),
  per the user's explicit flow. One LLM call to translate, one to answer.
- Clarification only when genuinely needed; then proceed regardless.
- All 5 nodes must do real work and appear in Thinking + LangSmith.

## Task order

1. **T1 — B1 clarification loop** (agent.py `missing_for`, `node_planner`)
2. **T2 — B5 grammar** (`clarification_question`)
3. **T3 — B2 topic vs section** (`extract_slots`, `classify_intent`)
4. **T4 — B3 sources + inline citations** (web `chat/page.tsx`, CSS)
5. **T5 — B4 web_search in trace** (`node_tools`, `stub_web_search`)
6. **T6 — LangSmith tracing on by default for `errors`** (Render env)
7. **T7 — end-to-end re-test in browser, all 3 languages**

## Test state

52 pass, 2 pre-existing live-LLM failures (network/quota on the base too).
Each bug fix lands with a failing test first.
