"""Runtime configuration for the Law Saathi voice worker.

The worker runs on the same machine as the FastAPI, so it reads `api/.env`
instead of asking for the same keys to be exported a second time. That file is
gitignored and never leaves the machine. `voice/.env` is read afterwards and
wins, so a local override does not mean editing the API's env file.

LiveKit's local dev server uses the fixed `devkey`/`devsecret` pair, so those
are the defaults: the demo should work the moment the server is up, with no
LiveKit Cloud account anywhere in sight.
"""
from __future__ import annotations

import os
import pathlib

# voice/agent/config.py -> voice/agent -> voice -> repo root
REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
VOICE_DIR = REPO_ROOT / "voice"
API_ENV = REPO_ROOT / "api" / ".env"
VOICE_ENV = VOICE_DIR / ".env"


def _load_env_file(path: pathlib.Path) -> None:
    """Read a KEY=VALUE file into the environment without overwriting what is set.

    `setdefault` is the important part: a value already exported by the shell
    wins over the file, so a developer can override one key without editing a
    gitignored file that the API is also reading.
    """
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


_load_env_file(API_ENV)
_load_env_file(VOICE_ENV)


def _get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# --- LiveKit -------------------------------------------------------------
# `ws://localhost:7880` is the local server's websocket endpoint; the HTTP
# endpoint on 7880 is what the browser and the token endpoint talk to.
LIVEKIT_URL = _get("LIVEKIT_URL", "ws://localhost:7880")
LIVEKIT_API_KEY = _get("LIVEKIT_API_KEY", "devkey")
LIVEKIT_API_SECRET = _get("LIVEKIT_API_SECRET", "devsecret")

# --- Sarvam --------------------------------------------------------------
# The Sarvam plugin reads SARVAM_API_KEY from the environment itself, so the
# value only has to exist in the process, not be passed to the constructor.
SARVAM_API_KEY = _get("SARVAM_API_KEY")

# --- Law Saathi API ------------------------------------------------------
LAWSAATHI_API = _get("LAWSAATHI_API", "http://localhost:8000")
INTERNAL_API_SECRET = _get("INTERNAL_API_SECRET")
# The demo talks to the API as user 1, the same account `api/scripts/probe.py`
# uses, so the answers are the ones the chat page gives.
LAWSAATHI_USER_ID = _get("LAWSAATHI_USER_ID", "1")
LAWSAATHI_USER_EMAIL = _get("LAWSAATHI_USER_EMAIL", "qa@example.com")
# A full agent run is 10 to 20 seconds. The default HTTP timeout is shorter
# than that and would cut a good answer in half.
LAWSAATHI_TIMEOUT = float(_get("LAWSAATHI_TIMEOUT", "180"))


def missing_keys() -> list[str]:
    """The keys the worker cannot run without, for a clear failure message."""
    missing = []
    if not SARVAM_API_KEY:
        missing.append("SARVAM_API_KEY (api/.env)")
    if not INTERNAL_API_SECRET:
        missing.append("INTERNAL_API_SECRET (api/.env)")
    return missing
