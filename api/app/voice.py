"""T8 — Sarvam STT/TTS voice wrapper (MVP push-to-talk)."""
import os
from typing import Optional

SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "")
SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"


def _lazy_client():
    try:
        import requests
        return requests
    except Exception:
        return None


def transcribe(audio_b64: str, lang: str = "en") -> str:
    """STT: audio base64 -> text. Fallback to empty / error string on failure."""
    if not SARVAM_API_KEY:
        return ""
    req = _lazy_client()
    if req is None:
        return ""
    try:
        payload = {"audio_content": audio_b64, "language": lang}
        headers = {"api-subscription-key": SARVAM_API_KEY, "Content-Type": "application/json"}
        resp = req.post(SARVAM_STT_URL, json=payload, headers=headers, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("transcript") or data.get("text") or ""
    except Exception:
        pass
    return ""


def synthesize(text: str, lang: str = "en") -> Optional[str]:
    """TTS: text -> audio base64 (or None). Fallback to None on failure."""
    if not SARVAM_API_KEY or not text:
        return None
    req = _lazy_client()
    if req is None:
        return None
    try:
        payload = {"text": text, "language": lang, "format": "mp3"}
        headers = {"api-subscription-key": SARVAM_API_KEY, "Content-Type": "application/json"}
        resp = req.post(SARVAM_TTS_URL, json=payload, headers=headers, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            # Sarvam may return url or base64 audio
            return data.get("audio_content") or data.get("audio_url") or None
    except Exception:
        pass
    return None
