# System Health

System health verifies that all foundational services are active and reachable: FastAPI backend on port 8000, Next.js frontend on port 3000, the local SQLite database, and LiveKit voice service.

## Sub-features

- `health-backend` checks FastAPI `/health` returns `{"status":"ok"}`.
- `health-frontend` checks Next.js root `/` returns HTTP 200 with rendered HTML.
- `health-database` checks database file exists and is readable.
- `health-livekit` checks LiveKit WebRTC port 7880 is open.

## How to get to it (user POV)

- Open `http://localhost:3000/` in any desktop or mobile browser.
- Open `http://localhost:8000/health` directly in the browser or via curl.

## Driving it with control-harness

Preconditions:
- Backend running on `http://localhost:8000`.
- Frontend running on `http://localhost:3000`.

- **Run doctor diagnostic.** Execute the verification doctor check:
  Run `.venv/bin/python scripts/verify-law-saathi.py doctor`.
  Exit code `0` and console output shows `[PASS]` for `backend_api`, `web_frontend`, and `database`.
- **Proof inspection.** Inspect `artifacts/verify-law-saathi/doctor.json`.
  The file records `healthy: true`, HTTP 200 response codes, and round-trip millisecond latencies.

## Gotchas

- If backend returns 500, verify `INTERNAL_API_SECRET` and `DATABASE_URL` in `api/.env`.
- If frontend fails to connect to backend, check `FASTAPI_URL=http://localhost:8000` in `web/.env.local`.
- LiveKit is optional for pure text chat but required for the `/voice` route and realtime speech.
