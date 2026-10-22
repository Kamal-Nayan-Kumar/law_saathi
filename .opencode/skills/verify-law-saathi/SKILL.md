---
name: verify-law-saathi
description: Verify Law Saathi end to end across web UI, FastAPI backend, multilingual legal chat (EN/HI/KN/Hinglish), statutory grounding against bare Acts, out-of-scope guards, and realtime voice.
---

# Verify Law Saathi

Automated and manual verification for Law Saathi: Indian family law AI legal support for citizens aged 21 to 60+ across English, Hindi, Kannada, and Hinglish.

## Launch

When running verification against a local instance, start services in separate terminals:

```sh
# 1. Backend API (FastAPI on port 8000)
export DATABASE_URL="sqlite:///./tmp/dev.db"
.venv/bin/uvicorn app.main:app --app-dir api --port 8000

# 2. Web Frontend (Next.js 16 on port 3000)
cd web && npm run dev

# 3. Realtime Voice Server & Worker (Optional for voice tests)
# LiveKit local server (port 7880)
livekit-server --dev
# Voice worker
export LIVEKIT_URL="ws://127.0.0.1:7880" LIVEKIT_API_KEY="devkey" LIVEKIT_API_SECRET="secret"
voice/agent/.venv/bin/python voice/agent/agent.py dev
```

How to tell it is ready:
- Backend: `curl -s http://localhost:8000/health` returns `{"status":"ok"}`.
- Web: `curl -s -I http://localhost:3000` returns `HTTP/1.1 200 OK`.
- LiveKit: TCP port 7880 is listening.

## Doctor

Run the read-only diagnostic check before driving:

```sh
.venv/bin/python scripts/verify-law-saathi.py doctor
```

The check verifies:
- FastAPI `/health` endpoint responds HTTP 200 with status `ok`.
- Next.js root `/` responds HTTP 200.
- SQLite or Neon database exists and has non-zero size.
- LiveKit voice server port 7880 is reachable.
- Writes proof to `artifacts/verify-law-saathi/doctor.json`.

If any check fails, do not proceed with feature drives until resolved.

## Drive

Drive verification via the CLI harness or browser:

### 1. Programmatic CLI Driver

```sh
# Drive all persona chat checks (Hindi, Kannada, English, Hinglish, Out-of-Scope)
.venv/bin/python scripts/verify-law-saathi.py chat

# Drive specific language persona
.venv/bin/python scripts/verify-law-saathi.py chat --lang hi
.venv/bin/python scripts/verify-law-saathi.py chat --lang kn
.venv/bin/python scripts/verify-law-saathi.py chat --lang en

# Drive standalone realtime voice flow (Sarvam TTS + LawSaathiLLM integration)
.venv/bin/python scripts/verify-law-saathi.py voice

# Run complete end-to-end verification suite
.venv/bin/python scripts/verify-law-saathi.py all
```

### 2. Browser UI Driver

- Navigate to `http://localhost:3000/chat`.
- Select language pill (English / हिंदी / ಕನ್ನಡ).
- Type a question or click a suggested prompt (e.g., "भरण-पोषण कैसे मांगें?").
- Confirm:
  - Step progress indicators stream ("How Saathi worked this out").
  - Final verified answer renders in clean markdown with section headings and bullet points.
  - Statutory citations appear (Act name, Section number, clickable source cards).
  - Disclaimer is clearly visible at the bottom.

## Evidence

Every run produces persistent evidence in `artifacts/verify-law-saathi/`:

- `doctor.json`: Component health status and response latencies.
- `chat_proof.json`: Full evaluation record including queries, answers, script fidelity verification, bare Act citations, disclaimer presence, and latency.
- `voice_proof.json`: Realtime voice TTS synthesis and LLM response transcripts.

Proof standards:
- Real Indian citizen queries with varied literacy and language needs (not robotic benchmark prompts).
- Answers must be in the reader's native script (Devanagari for Hindi, Kannada script for Kannada).
- Every answer must cite exact statutory provisions (Act and Section) and include the mandatory non-advice disclaimer.
- Out-of-scope queries (tax, criminal, property disputes) must be redirected politely without fabricated legal advice.

## Cleanup

The verification harness creates isolated sessions prefixed with `verify_`.
Cleanup does not delete `artifacts/verify-law-saathi/` evidence artifacts.

To clear temporary test sessions from the database:
```sh
# Test sessions can remain in dev.db or be cleared by wiping tmp/dev.db if restarting scratch
```

## Helpers

- `scripts/verify-law-saathi.py`: Unified executable harness supporting `doctor`, `chat`, `voice`, and `all`.
- `api/scripts/probe.py`: Python module to make authenticated BFF-equivalent calls to the API.
- `voice/agent/test_agent_flow.py`: Standalone LiveKit/Sarvam audio synthesis and LLM integration test.
