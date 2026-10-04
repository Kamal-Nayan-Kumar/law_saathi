"""Reach the API the way the browser does, with a real session cookie.

The FastAPI side trusts `x-user-id` / `x-internal-secret` headers, which the
Next.js BFF injects from a verified Neon Auth session. Calling the API directly
with those headers gives the same answers the chat page gets, without needing a
browser for every probe.
"""
from __future__ import annotations

import json
import os
import pathlib
import urllib.error
import urllib.request

# Load api/.env when the caller has not already exported it, so the shared
# secret matches the running API without repeating it on the command line.
ENV_FILE = pathlib.Path(__file__).resolve().parents[1] / ".env"
if ENV_FILE.exists():
    for _line in ENV_FILE.read_text().splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _v = _line.split("=", 1)
        os.environ.setdefault(_k.strip(), _v.strip())

API = os.environ.get("LAWSAATHI_API", "http://localhost:8000")
SECRET = os.environ.get("INTERNAL_API_SECRET", "")


def call(
    method: str,
    path: str,
    user_id: int = 1,
    email: str = "qa@example.com",
    body=None,
    timeout: int = 240,
):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    req.add_header("x-internal-secret", SECRET)
    req.add_header("x-user-id", str(user_id))
    req.add_header("x-user-email", email)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            if not raw:
                return None
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:400]
        raise RuntimeError(f"{method} {path} -> {e.code}: {body}") from e


def new_session(user_id: int = 1, title: str = "probe"):
    return call("POST", "/sessions", user_id, body={"title": title})["id"]


def ask(session_id: int, query: str, lang: str = "en", tone: str = "simple", user_id: int = 1):
    return call(
        "POST",
        f"/sessions/{session_id}/ask",
        user_id,
        body={"query": query, "lang": lang, "tone": tone},
    )