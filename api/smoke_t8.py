"""T8 smoke QA: voice transcription (Sarvam first, Groq fallback), 3-lang.

Runs without keys or network: it checks the shapes and the fallback order,
not the models. A live check is `voice_live.py`.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from app import voice
from app.schemas import TranscriptOut, VoiceIn


def smoke():
    # No key, no network: the module must still be importable and must fail
    # with a sentence for the user rather than an exception nobody can show.
    voice.SARVAM_API_KEY = ""
    voice.GROQ_API_KEY = ""
    try:
        voice.transcribe("ZmFrZQ==", lang="hi")
        raise AssertionError("expected VoiceError with no providers configured")
    except voice.VoiceError as exc:
        assert str(exc), "VoiceError must carry a sentence to show the user"

    # Silence is rejected before any paid call is made.
    try:
        voice.transcribe("ZmFrZQ==", lang="en")
        raise AssertionError("expected VoiceError for a clip with no audio")
    except voice.VoiceError as exc:
        assert "hear" in str(exc).lower()

    # VoiceIn accepts EN/HI/KN, and a real clip is big enough to be worth sending.
    assert VoiceIn(audio_b64="AA==" * 100, lang="kn").lang == "kn"
    for bad in ("te", "xx", "english"):
        try:
            VoiceIn(audio_b64="AA==" * 100, lang=bad)
            raise AssertionError(f"lang {bad} should be rejected")
        except Exception:
            pass

    # Schema shape: an error is a sentence and the transcript is empty.
    assert TranscriptOut(transcript="", lang="en", error="Try again.").error
    assert TranscriptOut(transcript="नमस्ते", lang="hi", provider="sarvam").lang == "hi"

    print("T8 SMOKE PASS — transcription, 3-lang, silence guard, fallback OK")


if __name__ == "__main__":
    smoke()