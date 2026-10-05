# LawSaathi — Stack

**This file describes what is deployed, not what was planned.** Where the
original September plan and the code disagree, the code wins and the difference
is called out. Anything marked *planned* or *not installed* is not running.

Solo project. Three surfaces — landing → login/signup → chat — plus an admin page
used only for corpus ingestion. English, Hindi and Kannada.

---

## 1. What is deployed

| Piece | Where | How |
| --- | --- | --- |
| Web | Vercel — `law-saathi.vercel.app` | Next.js, root directory `web/` |
| API | Render — service `law_saathi` | Docker image, autodeploy on push to `main` |
| Postgres | Neon | users, sessions, history, memory, preferences |
| Vectors | Qdrant Cloud | collection `law_saathi`, 1,134 chunks |

The browser never calls FastAPI. Next.js verifies the Neon Auth session and
forwards each request with `x-internal-secret` plus the resolved user id;
`api/app/auth.py` rejects anything without both. There is no JWT and the API is
not reachable from a browser session directly.

---

## 2. Frontend

| Concern | Choice | Note |
| --- | --- | --- |
| Framework | Next.js 16, React 19 | App Router |
| Language | TypeScript 5.7 | |
| Auth | `@neondatabase/auth` | session cookie, verified server-side |
| Answer rendering | `react-markdown` + `remark-gfm` | |
| Icons and charts | hand-built SVG | no icon or chart library — see `CONTEXT.md` |

Voice is **browser Web Speech** (`web/lib/voice.ts`) — `SpeechRecognition` and
`speechSynthesis`. No key, no server round-trip, and nothing leaves the device.
Buttons are hidden when the API is absent rather than shown broken.

> The plan said Sarvam STT/TTS. That was not built. `api/app/voice.py` and the
> `/sessions/{id}/voice` route still exist but the frontend never calls them, so
> that path is dead.

---

## 3. Backend

| Concern | Choice |
| --- | --- |
| API | FastAPI 0.115 + Uvicorn |
| Graph | LangGraph — `intent → planner → tools → reason → verifier → response` |
| Data | SQLAlchemy 2.0 + Postgres (Neon) |
| Config | Pydantic 2 / pydantic-settings |
| Runtime | `python:3.11-slim` in Docker; local dev is on 3.9 |

Two model-driven decisions, not keyword rules: **which Act governs**, and
**whether the draft invented law**. If the verifier rejects, the run returns to
tools once with the verifier's own replacement queries.

### Provider order

| Order | Provider | Model |
| --- | --- | --- |
| 1 | Groq | `openai/gpt-oss-120b` |
| 2 | OpenRouter | `meta-llama/llama-3.3-70b-instruct` |
| 3 | OpenCode | `space-bunny-free` |

A circuit breaker puts a failed provider in cooldown so one dead key cannot turn
a question into minutes. When all three are unavailable the answer degrades to a
cited template rather than failing — see `TO-DO.md` §4, because this is currently
the common case and it makes live quality checks unreliable.

---

## 4. Retrieval

| Concern | Choice | Note |
| --- | --- | --- |
| Vector store | Qdrant Cloud | 1,134 chunks, 9 titles |
| Embeddings | `intfloat/multilingual-e5-small` | **server-side**, via Qdrant cloud inference |
| Query cache | 300 s TTL | one question re-searches several times per run |

> The plan said embeddings run locally via Sentence Transformers. They do not:
> `api/app/ingest.py` passes `cloud_inference=True`, so Qdrant embeds. Nothing
> pulls a model locally at query time.

### Corpus

| Chunks | Act |
| --- | --- |
| 354 | Special Marriage Act, 1954 |
| 223 | Indian Christian Marriage Act, 1872 |
| 168 | Hindu Marriage Act, 1955 |
| 106 | Indian Divorce Act, 1869 |
| 84 | Guardians and Wards Act, 1890 |
| 65 | Hindu Succession Act, 1956 |
| 58 | Protection of Women from Domestic Violence Act, 2005 |
| 54 | Hindu Adoption and Maintenance Act, 1956 |
| 22 | Prohibition of Child Marriage (Amendment) **Bill**, 2021 |

Two things about that table:

- **The Christian Marriage Act is missing from every plan document** and is the
  second-largest source in the corpus. Christian marriages in India are governed
  by it, so `SCOPE.md` understates the scope. Either the scope or the corpus is
  wrong; they should agree.
- **The Bill is not law** and is filtered out of retrieval by `is_enacted()` in
  `api/app/agent.py`. It is still in the vector store. See `TO-DO.md` §0e for how
  it reached a user in an answer first.

### Known defect: personal law is not selected

"I am a Christian man, how do I get a divorce?" retrieves **Hindu Marriage Act
s.13B** — mutual consent under the Hindu Act — as its top source. The Indian
Divorce Act does appear (s.22), ranked sixth, so the Act is retrievable; the
ranking simply favours the wrong one, and the model is handed both as equally
applicable.

India applies different personal law by religion. A Christian's divorce is
governed by the Indian Divorce Act, 1869 and the Indian Christian Marriage Act,
1872 — not the Hindu Marriage Act. Answering with Hindu sections is the same
class of error as citing a Bill: a confident statement of the wrong law.

This is more than a documentation gap and is **not fixed**. `TOPIC_ACT["divorce"]`
lists both Acts with no way to choose, and nothing records the person's
religion. Either the intent is "cover every religion and pick from what the user
says", in which case religion needs to become a slot, or Christian family law is
out of scope, in which case it should be redirected rather than answered from
the wrong Act. That is a product decision, not a bug to patch — see `TO-DO.md`.

---

## 5. Evaluation

Two sets, easy to confuse:

| File | Count | Runs against | Needs network |
| --- | --- | --- | --- |
| `api/eval/golden_qas.py` | 17 | `run_golden.py`, `run_stub.py` | live only |
| `data/eval/golden_qas.json` | 30 | `api/eval_t10.py` | yes |

**RAGAS is not installed.** `import ragas` fails. `api/eval_t10.py` guards the
import and prints a notice. `eval/ragas_eval.py` is referenced in several
docstrings but was never written.

`api/eval_t10.py` also cannot run on a fresh clone: it reads
`data/eval/golden_qas.json`, and `data/` is gitignored, so that file is in no
repository. The 17-question set is the working one.

What runs today:

- `python3 api/eval/run_golden.py --offline` — routing only, no network, no model.
- `python3 api/eval/run_golden.py` — live; degrades to the template when no
  provider is reachable, so it measures a degraded path rather than the product.
- `python3 -m pytest api/tests` — 264 tests.

---

## 6. Not installed, not wired

| Thing | Status |
| --- | --- |
| `firecrawl` | not installed — web search silently no-ops |
| `ragas` | not installed — see above |
| Sarvam / LiveKit | not used; voice is browser-based |
| LangSmith | tracing hooks present, **never verified against a live account** |
| Local observability | works with no key — `api/app/obs.py`, read by `api/scripts/agent_stats.py` |

---

## 7. Why Docker on Render

Render supports a native Python runtime, where you give it a start command and
`requirements.txt`. This service uses the Docker runtime instead. That is a
choice, not a requirement — there is no compiled dependency or system library
here that needs it.

Two costs as written:

- **No `.dockerignore`.** The build context uploads the whole repo, including
  `.venv/`, `node_modules/` and `tmp/`.
- **Only `api/app` is copied**, so `api/eval`, `api/tests` and `api/scripts` do
  not exist in the container. Production cannot run the eval suite. That is a
  reasonable outcome, but it is accidental rather than intended.

Switching to the native runtime is a small change if the build time matters.

---

## 8. Repo layout

```
api/     FastAPI service, agent graph, corpus ingestion, evals, tests
web/     Next.js app (Vercel root directory)
scripts/ asset pipeline, screenshots, dev runner
docs/    stack, ADRs, plans, design
```

`CONTEXT.md` holds the rules the code must obey. `SCOPE.md` describes what the
product answers. `TO-DO.md` is the task list, kept honest about what is claimed
versus what runs.