# LawSaathi

Multilingual agentic AI legal support for family law (EN/HI/KN). See `docs/initial-plan.md`, `docs/stack.md`, `CONTEXT.md`.

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

Tests: `.venv/bin/python -m pytest api/tests -q`

## Env

- `api/.env`: `DATABASE_URL` (Neon), `INTERNAL_API_SECRET` (same value as web)
- `web/.env.local`: `NEON_AUTH_BASE_URL` (Neon console → Auth → Configuration),
  `NEON_AUTH_COOKIE_SECRET` (generate), `INTERNAL_API_SECRET`, `FASTAPI_URL`

## Deploy

- Web → Vercel (root `web/`), set `NEXT_PUBLIC_API_URL` to the Render API URL.
- API → Render via `render.yaml` (Docker), set `DATABASE_URL` (Neon) + `AUTH_SECRET`.
