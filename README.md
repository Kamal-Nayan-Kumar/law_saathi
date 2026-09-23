# LawSaathi

Multilingual agentic AI legal support for family law (EN/HI/KN). See `docs/initial-plan.md`, `docs/stack.md`, `CONTEXT.md`.

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
cd web && npm install && npm run dev   # needs API on :8000 (see next.config.ts)
```

Tests: `.venv/bin/python -m pytest api/tests -q`

## Deploy

- Web → Vercel (root `web/`), set `NEXT_PUBLIC_API_URL` to the Render API URL.
- API → Render via `render.yaml` (Docker), set `DATABASE_URL` (Neon) + `AUTH_SECRET`.
