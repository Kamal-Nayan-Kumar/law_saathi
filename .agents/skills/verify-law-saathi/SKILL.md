---
name: verify-law-saathi
description: "Verify Law Saathi family-law legal assistant end-to-end: API, web, chat, multilingual answers, bare-act citations, and voice."
disable-model-invocation: true
---

# Verify Law Saathi

Scripted verification for Law Saathi. Drives the real API and web app to prove that legal guidance, multilingual rewriting, section citations, and voice flows work without manual eyeballing.

## Launch

```bash
# Terminal 1: API (FastAPI)
export DATABASE_URL="sqlite:///./tmp/dev.db"
.venv/bin/uvicorn app.main:app --app-dir api --port 8000 --reload

# Terminal 2: Web frontend (Next.js)
cd web && npm run dev
```

Ready check:
- API responds `{"status":"ok"}` on `http://localhost:8000/health`.
- Web responds HTTP 200/307 on `http://localhost:3000`.

## Doctor

Quick health check to ensure dependencies and services are up before driving:

```bash
python3 - << 'EOF'
import urllib.request, json
try:
    with urllib.request.urlopen("http://localhost:8000/health", timeout=3) as r:
        assert json.loads(r.read()) == {"status": "ok"}
    print("DOCTOR OK: API is up and healthy")
except Exception as e:
    print("DOCTOR FAIL: API not responding:", e)
EOF
```

## Drive

Run the probe suite across English, Hindi, and Kannada:

```bash
# 1. Automated multi-case probe (36 golden scenarios)
.venv/bin/python scripts/prof_review_probe.py

# 2. Browser end-to-end verification via ego-browser
ego-browser nodejs -e '
const task = await taskSpace("verify-law-saathi");
const page = task.page("p1");
await page.goto("http://localhost:3000/chat");
await page.waitForTimeout(2000);
console.log("Chat title:", await page.title());
'

# 3. Unit and integration tests
.venv/bin/python -m pytest api/tests -q
```

## Evidence

Every run must generate concrete evidence:
- Test output with pass/fail counts
- Probe results saved in `tmp/prof_review.json` with citations and verification status
- Browser snapshots or screenshots saved in `tmp/`
