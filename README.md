# LawSaathi

Multilingual agentic AI legal support for family law (EN/HI/KN). See `docs/initial-plan.md`, `docs/stack.md`, `CONTEXT.md`.

**Live:** https://law-saathi.vercel.app

The API has no stable public hostname. Its address lives in the Vercel
production env as `FASTAPI_URL` (`cd web && npx vercel env pull`). Nothing else
in this repo needs it, because the browser never talks to the API directly.

## Corpus (law data we use)

| Source | What | Size |
| ------ | ---- | ---- |
| `vaquill/open-india-law` (gated, HF token) | `in_central_legislation.parquet` streamed, title-matched to 7 family acts, repealed rows dropped | 424 in-force section rows → `data/corpus/open-india-law-family-acts.jsonl` (729KB, gitignored) |
| `enerscript/MARRIAGEACT` | 4 bare-act txt files (HMA, SMA, Christian Marriage Act, Child Marriage Bill) | 244KB → `data/corpus/marriageact_raw/` (gitignored) |
| India Code (indiacode.nic.in) | Ground truth: per-row `source_url` + act-PDF `mirror_url` stored in every chunk payload | Referenced, PDFs ingested on demand |

7 acts: Hindu Marriage 1955 (50 rows), Special Marriage 1954 (80), Hindu Adoption & Maintenance 1956 (32), Hindu Succession 1956 (53), Guardians & Wards 1890 (67), Domestic Violence 2005 (47), Indian Divorce Act 1869 (95).

Vectors live in Qdrant Cloud collection `law_saathi` (e5-small, 384 dims, 1132 points); Neon `ingested_chunks` mirrors every point ID (ADR-0004). Re-ingest: `api/scripts/download_corpus.py` then `api/scripts/ingest.py --jsonl ... --text-dir ...`.

## Languages (EN/HI/KN)

English-pivot pipeline (ADR-0009): detect input language → translate non-English queries to English → retrieve + reason in English → answer back in the user's language. Voice uses Sarvam STT/TTS at the edges.

**There is no language setting, and that is deliberate.** The script of the
question decides the language of the answer, on both sides of the wire:

- `agent.detect_lang()` reads the question's script and ignores the caller's
  hint. A stored preference used to win, which meant a user who had once picked
  Hindi got their English question answered in Hindi — and was left convinced
  their own words were in the wrong language.
- The server reports the language it actually wrote in, as `lang` on the ask
  response. "Read aloud" uses that rather than a guess, so a Kannada answer is
  spoken by a Kannada voice.

Hinglish ("shadi ke liye umar") is detected as Hindi.

## Run locally (T1 scaffold)

Backend:

```sh
cd /Users/nayan/Documents/projects/law_saathi
python3 -m venv .venv && .venv/bin/pip install -r api/requirements.txt
cp .env.example api/.env   # fill DATABASE_URL (Neon) + AUTH_SECRET when ready
DATABASE_URL="sqlite:///./lawsathi.db" .venv/bin/uvicorn app.main:app --app-dir api --reload
```

Frontend:

```sh
cd web && npm install && npm run dev   # needs API on :8000 (see FASTAPI_URL)
```

Auth: browser → Next.js (`/api/bff/*` verifies Neon Auth session) → FastAPI
(internal secret). Never call FastAPI directly from the browser.

Tests: `.venv/bin/python -m pytest api/tests -q` (270)
Golden routing: `.venv/bin/python api/eval/run_golden.py --offline` (18/18)

`--offline` matters. A live run measures whatever the providers are doing that
minute, and several of them are rate-limited, so a degraded run tells you about
the keys rather than about the product.

## Env

- `api/.env`: `DATABASE_URL` (Neon), `INTERNAL_API_SECRET` (same value as web)
- `web/.env.local`: `NEON_AUTH_BASE_URL` (Neon console → Auth → Configuration),
  `NEON_AUTH_COOKIE_SECRET` (generate), `INTERNAL_API_SECRET`, `FASTAPI_URL`

## Deploy

Web is Vercel with `web/` as the root directory. The API is Render, from
`render.yaml` (Docker), and autodeploys on push to `main`.

Required Vercel production env: `FASTAPI_URL`, `INTERNAL_API_SECRET`,
`NEON_AUTH_BASE_URL`, `NEON_AUTH_COOKIE_SECRET`.

```sh
cd web && npx vercel deploy --prod --yes
```

Two things about the web deploy that are easy to lose an afternoon to:

- **Vercel's Git integration is not currently triggering.** A push to `main`
  did not produce a build on 2026-10-05 — the newest deployment was still hours
  old. Push, then check `npx vercel ls`; if nothing appeared after a few
  minutes, deploy by hand as above.
- **Both API proxies set `maxDuration = 300`.** An agent run takes 60–90s. At
  Vercel's default function limit the `/api/stream` response is cut mid-answer,
  and the browser sees a stream that ends cleanly with no `done` event. Do not
  lower it, and do not remove the raised value from `/api/bff` either — that one
  surfaces as a bare "500" under the answer.

## Verify a deploy

Deploying is not the same as working. Both have shipped broken while the suite
was green, because the failures were in what the answer *said* and in what the
user *saw*, and neither is an assertion.

1. Sign in on the real site and ask something in ordinary words.
2. Read the whole answer, top to bottom. Cut-off passages, an empty numbered
   point, or a stray legal term are all defects the tests do not catch.
3. Ask one question and confirm you get one answer.
4. Collapse the chat history, and check what is left in the rail.

`bash scripts/dev.sh --observe` runs both servers locally and writes
`tmp/agent-runs.jsonl`; `EGO_SPACE=<id> .venv/bin/python scripts/shots.py chat
<tiny|phone|tablet|laptop|xl>` reports horizontal overflow per viewport.
