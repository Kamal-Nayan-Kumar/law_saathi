# Law Saathi Verification Map

This directory is the maintained source for verifying user-facing behavior in Law Saathi. Read the index before driving the app, then use the matching feature file as the recipe.

## Baseline preconditions

- Launch FastAPI backend at `http://localhost:8000`.
- Launch Next.js web frontend at `http://localhost:3000`.
- Database initialized at `tmp/dev.db`.
- Run `.venv/bin/python scripts/verify-law-saathi.py doctor` and require all components PASS.
- Never drive an instance before doctor passes.

## Driving conventions

- Test from the viewpoint of real Indian citizens aged 21 to 60+ (Sunita, Lakshmi, Joseph, Ramesh, Priya).
- Support non-English queries natively (Hindi in Devanagari script, Kannada in Kannada script, Hinglish).
- Run CLI actions through `.venv/bin/python scripts/verify-law-saathi.py <command>`.
- Run browser actions against `http://localhost:3000`.
- Ensure proof artifacts survive in `artifacts/verify-law-saathi/`.

## Proof and skip reporting

- Capture the query, full answer text, citations list, step log, and latency.
- Non-English proof requires script validation (no Romanized English output when Hindi or Kannada is requested).
- Statutory grounding requires matching enacted Acts (e.g., Hindu Marriage Act, 1955, PWDV Act, 2005) and Section numbers.
- Legal disclaimer check is mandatory on all substantive legal responses.
- Out-of-scope redirection is verified when queries stray into landlord-tenant, criminal, or tax disputes.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph describing user-visible behavior. It then uses exactly four H2 sections in this order:
1. `Sub-features`
2. `How to get to it (user POV)`
3. `Driving it with <harness>`
4. `Gotchas`

## Features

- [System Health](./system-health.md) covers backend API, Next.js web app, database, and vector collection connectivity.
- [Multilingual Empathy Chat](./multilingual-chat.md) covers English, Hindi, Kannada, and Hinglish persona queries, script correctness, and plain-language formatting.
- [Statutory Grounding](./statutory-grounding.md) covers bare Act retrieval, section citations, verifier pass, and legal disclaimers.
- [Scope Guard & Follow-ups](./out-of-scope-guard.md) covers out-of-scope redirection and multi-turn contextual continuity.
- [Voice Assistant](./voice-assistant.md) covers LiveKit WebRTC connection and Sarvam STT/TTS in all three languages.
