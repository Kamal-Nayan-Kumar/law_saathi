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

| # | Report | Where |
| --- | --- | --- |
| B1 | After login it hangs on the login screen | frontend |
| B2 | Login screen is not properly responsive | frontend |
| B3 | The "home" icon in the sidebar should be a settings/profile control with logout | frontend |
| B4 | Chat does not feel natural — reads like a form, not a person | frontend + agent |
| B5 | Language preference is not remembered properly | frontend + agent memory |
| B6 | The "Thinking" toggle is not robust — steps are hidden, thin, or wrong | frontend + agent |
| B7 | Web search is not visibly implemented | agent |
| B8 | Voice (STT/TTS) is missing from the UI | frontend + agent |
| B9 | No real-time voice | frontend + agent |
| B10 | No visibility into what the agent is doing | both |

### 0c. Features requested

| # | Feature |
| --- | --- |
| F1 | List the questions in scope and the project's boundaries |
| F2 | Short-term and long-term memory for language preference |
| F3 | Show every step the agent takes |
| F4 | LangSmith tracing, evals and monitoring |
| F5 | RAGAS evaluation with a golden dataset |
| F6 | Robust "thinking" toggle so the agent reads as agentic |
| F7 | Voice: speech-to-text and text-to-speech |
| F8 | Real-time voice (streaming, low latency) |
| F9 | A developer view that visualises agent states, graphs and latency |

### 0d. How to work

- [ ] Act as a real user with a real family-law problem, role-play every
      persona (male, female, elderly, young, Hindi, Kannada, first-time)
- [ ] Test the chat and the auth flows regressively
- [ ] When an answer is not good enough: record it, fix it, re-test
- [ ] Then act as a senior developer and widen the product where the gap shows
- [ ] Commit after each fix

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
| Web search | `api/app/agent.py` | Firecrawl, key present |
| STT / TTS | `api/app/voice.py` | code exists, **no key** |
| LangSmith | `api/app/agent.py` | env present, needs verification |
| RAGAS | none | to build |

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

1. Scope correction and cleanup — done
2. Frontend bugs B1–B6, F6
3. F1 scope and question list
4. F2 memory for language preference
5. F3 + F9 agent step visibility, tracing
6. F7 voice, then F8 real-time voice
7. F4 LangSmith verification, F5 RAGAS golden dataset
8. Persona-based regression testing, fix, re-test