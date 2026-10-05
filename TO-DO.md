# TO-DO.md — Law Saathi

Product scope, in one line: **landing page → login/signup → chat.** Those three
surfaces and the agent behind them. Nothing else ships.

Design source of truth: `Law Saathi_ Family Law Guidance.png`.
Asset rules: `CHATGPT_RULES.md`. Colour tokens: `web/app/globals.css`.
Product questions and scope: `SCOPE.md`.

---

## How this document is organised

Section 0 is the work Nayan asked for. Sections 1+ are the state of the code,
kept honest so a reader can tell what is done from what is claimed.

---

## 0. Requested work (from Nayan, verbatim intent)

### 0a. Scope correction

- [x] Remove the cases / simulator / dashboard pages — not part of the product
- [x] Remove the case data and the chart components that fed them
- [x] Nav and footer point only at real routes
- [x] Supabase/Neon dashboard redirect removed; login lands on `/chat`

### 0b. Bugs reported

| # | Report | State |
| --- | --- | --- |
| B1 | After login it hangs on the login screen | **fixed** — login pushes to `/chat`; Nav/Footer returned null after hooks, which was the hang |
| B2 | Login screen is not properly responsive | **fixed** — verified at 360/390/768/1440/2560 |
| B3 | The "home" icon should be a settings/profile control with logout | **fixed** — account menu. Language, tone and "back to the site" were later removed; sign out is all it holds now |
| B4 | Chat does not feel natural — reads like a form, not a person | **fixed** — the model writes its own next steps; the no-provider fallback now opens by naming the person's situation |
| B5 | Language preference is not remembered properly | **superseded** — there is no language preference to remember. The answer follows the script of the question, so the picker was removed rather than fixed (see 0f) |
| B6 | The "Thinking" toggle is not robust | **fixed** — SSE streams each step live, persisted on the message row |
| B7 | Web search is not visibly implemented | **blocked** — `api/app/agent.py: stub_web_search` is written, but the `firecrawl` package is not installed. Add it and set `FIRECRAWL_API_KEY` |
| B8 | Voice (STT/TTS) is missing from the UI | **done** — browser Web Speech APIs, no key needed. The mic is inside the input pill, left of the send arrow; Read aloud per answer |
| B9 | No real-time voice | **open** — see F8 |
| B10 | No visibility into what the agent is doing | **fixed** — `api/app/obs.py` records one JSONL line per run; `api/scripts/agent_stats.py` draws node frequency, decisions, latency, providers, outcomes and the number of distinct paths |

### 0c. Features requested

| # | Feature | State |
| --- | --- | --- |
| F1 | List the questions in scope and the project's boundaries | **done** — `SCOPE.md`: the seven acts, in-scope questions by area, what gets redirected, and the eight things Saathi will never do |
| F2 | Short-term and long-term memory for language preference | **dropped** — a preference was the wrong shape for this product. The question's script decides the answer, so there is nothing to store and nothing to get wrong |
| F3 | Show every step the agent takes | **done** — streamed live during the run, persisted afterwards |
| F4 | LangSmith tracing, evals and monitoring | **partial** — tracing hooks are in place but unverified against a live LangSmith account. The local JSONL log works with no key and no network |
| F5 | RAGAS evaluation with a golden dataset | **partial** — the dataset is real: `api/eval/golden_qas.py`, 17 questions, plus offline and live runners. RAGAS itself is **not** written; it needs an LLM judge and an embedding matrix. The runners deliberately check what can be checked deterministically: right language, right section cited, nothing confidently wrong |
| F6 | Robust "thinking" toggle so the agent reads as agentic | **done** |
| F7 | Voice: speech-to-text and text-to-speech | **done** |
| F8 | Real-time voice (streaming, low latency) | **open** — needs a streaming STT/TTS provider. Browser Web Speech cannot do low-latency streaming |
| F9 | A developer view that visualises agent states, graphs and latency | **done** — `api/app/obs.py` + `api/scripts/agent_stats.py`. A pipeline takes exactly one path per run; an agent does not. Distinct-path count is the check |

### 0d. How to work

- [x] Act as a real user with a real family-law problem, role-play every
      persona (male, female, elderly, young, Hindi, Kannada, first-time)
- [x] Test the chat and the auth flows regressively
- [x] When an answer is not good enough: record it, fix it, re-test
- [x] Then act as a senior developer and widen the product where the gap shows
- [x] Commit after each fix

### 0e. What persona testing actually found

Five of these were real defects, not polish. Each is now covered by a test.

| Found | Why it mattered |
| --- | --- |
| Guardians and Wards Act s.17 never retrieved | It says "welfare of the minor", never "custody". The section that decides nearly every custody dispute was not in the top ten for "who gets custody of my child" |
| DV Act s.19, HSA s.8 and s.15, HMA s.13B not retrieved | Same cause: the Acts use different words from the people asking |
| `broaden_query` only applied on retry | So the fix above was inert on the path that actually runs |
| "i am not safe in my own house" returned nothing | Coercive control is what DV Act s.3(a) covers. The keyword list knew only the statute's words, so these phrasings detected no topic, retrieved nothing, and answered nothing |
| "I am scared of the court process" would have become a DV question | Caught by a test written to check the fix. Fear now counts only when it is fear of a person |
| Fallback quotes truncated at 160 characters | s.17 stopped at "be guided by what…" — dropping "for the welfare of the minor", the entire reason the section governs custody |
| The passage cleaner never fired | Every corpus chunk starts `Chapter II: … \| Section 20: …`, so its `^Section` match failed and the raw line reached the user |

### 0f. Defects found by reading the screen (2026-10-05)

Found by asking real questions on the deployed site and reading what came back,
not by running the suite. Every automated check passed while all of these were
happening.

| Found | Why it mattered | State |
| --- | --- | --- |
| One question produced two answers | The SSE stream was killed by the platform's function timeout. The client treated a stream that ended without `done` as "streaming is unavailable" and re-ran the whole agent over JSON, which persisted a second answer under the same question | **fixed** — a stream that dies is never retried; the saved answer is read back over GET, which cannot run the agent. `maxDuration = 300` on both proxies stops the cut in the first place |
| A bare "500" under the answer | The BFF had the default function timeout, so the proxy was killed mid-run and returned a status with no body | **fixed** — `maxDuration = 300`, and an empty error body now becomes a sentence a person can read |
| "How Saathi worked this out" wrapped one word per line | The step label and its detail were siblings in a 2-column grid, so the detail landed in the 20px dot column | **fixed** — both are placed in the content column |
| The collapsed rail showed "K" and a stray "I" | The rail is 66px. The name and the language line were squeezed into it, so the avatar looked like a stray letter | **fixed** — collapsed shows the avatar alone, pinned to the bottom left |
| Quoted passages cut mid-clause ("…or a male child…", "…from the shared…") | `plain_passage` cut at the last comma it could find, which is usually mid-rule | **fixed** — `clip()` prefers a whole sentence, then a clause, and never breaks a word |
| A numbered point with no text ("**[3] … — Section 2 —**") | The chunk was only a section heading, so the cleaner correctly returned nothing — but the bullet was still printed | **fixed** — a passage with nothing to say is not listed |
| The disclaimer read as part of the advice | It rendered in the same near-black as the answer | **fixed** — muted grey, still well above the contrast floor |
| Answers used "the respondent", "the aggrieved person", Latin | Unusable for the people who need it | **fixed** — `PLAIN_LANGUAGE_RULES` in the writing prompt, each rule traceable to a line in a real answer |
| The collapsed rail's avatar jumped to the top | The spacer that pushes it down was the chat list, which is hidden when collapsed | **fixed** — `margin-top: auto` on the account block |

---

## 1. Current state

### Surfaces that exist

| Route | File | State |
| --- | --- | --- |
| `/` | `web/app/page.tsx` | rebuilt to the reference |
| `/login` | `web/app/login/page.tsx` | split card, language picker on signup |
| `/chat` | `web/app/chat/page.tsx` | history, language detect, thinking, sources |
| `/admin` | `web/app/admin/page.tsx` | ingestion, not part of the product |

### Agents and services

| Concern | File | State |
| --- | --- | --- |
| LangGraph five nodes | `api/app/agent.py` | graph built and used |
| Planner chooses act + tools | `api/app/agent.py` | implemented |
| Verifier is a model | `api/app/agent.py` | implemented |
| Web search | `api/app/agent.py` | written; **blocked**, `firecrawl` not installed |
| STT / TTS | `web/lib/voice.ts` | done via browser Web Speech, no key |
| Observability | `api/app/obs.py` | done, local JSONL, no key |
| LangSmith | `api/app/agent.py` | hooks in, **unverified** against a live account |
| RAGAS | none | to build; the golden dataset it needs already exists |

### Assets

All generated in the pinned ChatGPT chat and cropped by
`scripts/prep_assets.py`. See `CHATGPT_RULES.md`.

| File | Slot |
| --- | --- |
| `logo-mark.png` | nav, footer, favicon (alpha) |
| `hero-scene.png` | hero, 5:6 |
| `skyline.png` | full-bleed band under the hero |
| `family-scales.png` | "why" section, chips overlap the frame |
| `auth-scene.png` | login art panel |
| `chat-empty.png` | chat empty state |

---

## 2. Standing constraints

- Assets are generated only through `scripts/gpt_job.py`, in the one pinned
  ChatGPT chat. Never open another chat.
- UI icons are hand-built SVG in `web/components/Icon.tsx` on one 24px grid.
  Never add an icon from a generated image.
- Charts are hand-built SVG. Do not add Recharts.
- Every legal answer needs a section citation or it is not verified
  (`CONTEXT.md`).
- Family law only. Out-of-scope topics get a redirect, not an answer.
- Never commit a key. `api/.env` and `web/.env.local` are gitignored.

---

## 3. Order of work

1. Scope correction and cleanup — **done**
2. Frontend bugs B1–B6, F6 — **done**
3. F1 scope and question list — **done** (`SCOPE.md`)
4. F2 memory for language preference — **done**
5. F3 + F9 agent step visibility, tracing — **done**
6. F7 voice — **done**. F8 real-time voice — **open**
7. F4 LangSmith verification, F5 RAGAS — **partial**, see 0c
8. Persona-based regression testing, fix, re-test — **done**, 7 defects fixed

## 4. Known blockers

Two things stop work that is otherwise ready. Both are environment, not code.

| Blocker | Effect | Fix |
| --- | --- | --- |
| Groq returns 429, OpenRouter returns 402 (out of credit), OpenCode times out | Roughly one question in twenty gets a model. The rest degrade to the cited template, so the live golden run measures a degraded path | Add credit or a second Groq key. The circuit breaker already keeps this from getting worse |
| `firecrawl` is not installed | Web search silently no-ops, so B7 is open | `pip install firecrawl` and set `FIRECRAWL_API_KEY` |

Verify a provider before trusting a live eval: `api/scripts/probe.py`. Without
one, use `--offline`, which checks routing with no network at all.

## 5. Open decisions (Nayan)

### 5a. Does Law Saathi cover Christian family law?

The corpus has always held the Indian Christian Marriage Act, 1872 — 223 chunks,
the second-largest source. But it appears in no plan document, `SCOPE.md` omits
it, and nothing in the agent selects personal law by religion.

The consequence today: *"I am a Christian man, how do I get a divorce?"*
answers with **Hindu Marriage Act s.13B**. The Indian Divorce Act is retrieved
too, ranked sixth, but the wrong Act wins on similarity. India applies different
personal law by religion, so this is the same class of error as citing a Bill —
a confident statement of the wrong law — and it reaches a real person deciding
how to end a marriage.

Two ways forward, and I have not chosen because both are defensible:

| Option | What it means |
| --- | --- |
| **Cover every religion** | Add religion as a slot. Ask when it is unclear, route to the right Act, keep both statutes in `TOPIC_ACT`. More correct, more work, and "which religion" is an awkward question to ask someone in distress |
| **Hindu law only** | Redirect Christian questions explicitly, as out of scope. Cheaper and honest, but less useful for a population the corpus already serves |

Whichever is chosen, it needs a golden question each way so the answer cannot
drift back silently. Nothing in the eval set currently covers religion.

### 5b. Drop the pending Bill from the corpus

`is_enacted()` keeps it out of answers, but 22 chunks of the Prohibition of Child
Marriage (Amendment) Bill, 2021 are still in Qdrant, from the non-official
`enerscript` dataset. Filtering at retrieval is the right immediate fix — it
deployed without re-indexing — but the record itself should not exist. Removing
it needs a re-ingest.