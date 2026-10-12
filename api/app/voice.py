"""Speech-to-text: Sarvam SAAR first, Groq Whisper as the fallback.

Why the server at all: the browser's own `webkitSpeechRecognition` is a thin
client over Google's speech servers. It works on Android Chrome and fails on
desktop Linux Chrome with `network`, because the request to Google is the part
that breaks — an adblocker, Brave Shields, or a filtered network kills it. So
the browser's microphone is only ever used to *capture* audio; the audio is
transcribed here, where the network path is ours and not a page extension's.

Why two providers: Sarvam is the better model for the people this app is for —
Indian accents, Hinglish code-switching, Kannada. But Sarvam bills per minute
and an account with no credits answers 402, which must not take voice input
down with it. Groq Whisper is the same call shape, costs nothing at this
volume, and carries English and Hindi well. So: ask Sarvam, and if it does not
answer with a transcript, ask Groq. Whichever answers, the user sees the same
thing.

Language is never forced. Both providers auto-detect, and the agent decides
the answer's language from the question's script anyway — telling Sarvam
"en-IN" when the user is about to speak Kannada would only make it worse.
"""
import base64
import binascii
import logging
import os
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"
SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"
GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

SARVAM_MODEL = os.environ.get("SARVAM_STT_MODEL", "saaras:v4")
GROQ_MODEL = os.environ.get("GROQ_STT_MODEL", "whisper-large-v3-turbo")

# Sarvam's REST endpoint handles clips under 30s. The browser is told to stop
# recording at the same number so the audio we reject is never sent.
MAX_AUDIO_SECONDS = 25

# Base64 inflates by a third, so this is ~1.5MB of audio. A 25s clip at the
# bitrate the recorder produces is well under it; the ceiling exists to stop a
# hand-crafted request from being a free way to make Sarvam expensive.
MAX_AUDIO_B64_CHARS = 2_000_000


class VoiceError(Exception):
    """The audio could not be decoded or transcribed by any provider."""


def _client():
    """httpx is a hard dependency of the API; requests is not."""
    try:
        import httpx
        return httpx
    except Exception:
        return None


def _decode(audio_b64: str) -> bytes:
    if not audio_b64:
        raise VoiceError("No audio received.")
    if len(audio_b64) > MAX_AUDIO_B64_CHARS:
        raise VoiceError("Recording too long. Try again and keep it shorter.")
    # The browser sends a bare base64 string, but a data: URL costs nothing to
    # strip and is what anyone testing this from a console will paste.
    payload = audio_b64.split(",", 1)[1] if audio_b64.startswith("data:") else audio_b64
    try:
        raw = base64.b64decode(payload, validate=False)
    except (binascii.Error, ValueError):
        raise VoiceError("Audio could not be read.")
    if len(raw) < 1024:
        # Anything this small is silence or a truncated clip. Transcribing it
        # would spend a paid call to return nothing.
        raise VoiceError("Did not hear anything. Try speaking closer to the mic.")
    return raw


def _sarvam(audio: bytes) -> Optional[str]:
    if not SARVAM_API_KEY:
        return None
    httpx = _client()
    if httpx is None:
        return None
    try:
        resp = httpx.post(
            SARVAM_STT_URL,
            headers={"api-subscription-key": SARVAM_API_KEY},
            files={"file": ("clip.webm", audio, "audio/webm")},
            # "unknown" asks SAAR to detect. Pinning a language here is a guess
            # made before the user has spoken, and a wrong guess costs accuracy
            # on exactly the code-mixed speech this app is built for.
            data={"model": SARVAM_MODEL, "language_code": "unknown"},
            timeout=60.0,
        )
        if resp.status_code == 200:
            return (resp.json().get("transcript") or "").strip() or None
        # 402 is the one worth naming: the account is out of credits, which is
        # an action someone has to take, not a transient fault worth retrying.
        if resp.status_code == 402:
            logger.warning("sarvam stt out of credits; falling back to groq")
        else:
            logger.warning("sarvam stt http=%s body=%s", resp.status_code,
                           resp.text[:200])
    except Exception as exc:
        logger.warning("sarvam stt failed: %s", exc)
    return None


def _groq(audio: bytes) -> Optional[str]:
    if not GROQ_API_KEY:
        return None
    httpx = _client()
    if httpx is None:
        return None
    try:
        resp = httpx.post(
            GROQ_STT_URL,
            headers={"Authorization": "Bearer " + GROQ_API_KEY},
            files={"file": ("clip.webm", audio, "audio/webm")},
            data={"model": GROQ_MODEL, "response_format": "json"},
            timeout=60.0,
        )
        if resp.status_code == 200:
            return (resp.json().get("text") or "").strip() or None
        logger.warning("groq stt http=%s body=%s", resp.status_code, resp.text[:200])
    except Exception as exc:
        logger.warning("groq stt failed: %s", exc)
    return None


def _try(provider, audio) -> str:
    """One provider's answer, normalised, or "" if it did not answer.

    The strip lives here rather than in each provider so that whitespace is a
    failure everywhere. A provider that returns 200 and a blank string has not
    answered, and treating that as success would leave the user staring at an
    empty input box with no error to act on.
    """
    try:
        return (provider(audio) or "").strip()
    except Exception as exc:
        logger.warning("stt provider raised: %s", exc)
        return ""


def transcribe(audio_b64: str, lang: str = "en") -> str:
    """Base64 audio -> text, Sarvam first then Groq.

    `lang` is accepted because the caller always has it, but deliberately
    unused: both providers detect, and the agent re-decides the language from
    the transcript anyway.
    """
    return _transcribe_detail(audio_b64)[0]


def _transcribe_detail(audio_b64: str) -> Tuple[str, str]:
    audio = _decode(audio_b64)
    for name, provider in (("sarvam", _sarvam), ("groq", _groq)):
        text = _try(provider, audio)
        if text:
            return text, name
    raise VoiceError("Voice input failed. Please type your question instead.")


def transcribe_detail(audio_b64: str, lang: str = "en") -> Tuple[str, str]:
    """Same as transcribe, plus the provider that answered. Used in logs and
    tests so a silent regression to the fallback is visible."""
    return _transcribe_detail(audio_b64)


def synthesize(text: str, lang: str = "en") -> Optional[str]:
    """TTS: text -> audio base64 (or None). Answers are read by the browser's
    own speechSynthesis, which is free and offline, so nothing calls this."""
    if not SARVAM_API_KEY or not text:
        return None
    httpx = _client()
    if httpx is None:
        return None
    try:
        payload = {"text": text, "language": lang, "format": "mp3"}
        headers = {"api-subscription-key": SARVAM_API_KEY, "Content-Type": "application/json"}
        resp = httpx.post(SARVAM_TTS_URL, json=payload, headers=headers, timeout=30.0)
        if resp.status_code == 200:
            data = resp.json()
            # Sarvam may return url or base64 audio
            return data.get("audio_content") or data.get("audio_url") or None
    except Exception:
        pass
    return None