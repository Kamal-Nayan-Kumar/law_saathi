"""Voice input: audio -> text.

The browser's own SpeechRecognition is a client for Google's speech servers,
and on desktop Chrome that request fails outright — which is why voice input
worked on a phone and not on a laptop. These tests pin the behaviour that
replaced it: transcribe on our own server, Sarvam first, Groq when Sarvam
cannot answer, and never answer half a question on a pause.
"""
import base64

import pytest

from app import voice as voice_module
from tests.conftest import bff_headers


# A base64 blob that decodes to something big enough to pass the silence guard.
# The bytes are meaningless; every provider is stubbed.
def clip(size=4096):
    return base64.b64encode(b"\x00" * size).decode()


def test_sarvam_is_asked_first(monkeypatch):
    """Sarvam is the better model for the people this app is for. Groq is the
    insurance policy, not the default."""
    asked = []

    def fake_sarvam(audio):
        asked.append("sarvam")
        return "मुझे तलाक चाहिए"

    def fake_groq(audio):
        asked.append("groq")
        return "should not be reached"

    monkeypatch.setattr(voice_module, "_sarvam", fake_sarvam)
    monkeypatch.setattr(voice_module, "_groq", fake_groq)

    text, provider = voice_module.transcribe_detail(clip())
    assert text == "मुझे तलाक चाहिए"
    assert provider == "sarvam"
    assert asked == ["sarvam"]


def test_groq_answers_when_sarvam_cannot(monkeypatch):
    """An out-of-credit Sarvam account answers 402. That must not take voice
    input down, or the only way to ask a question would be to type it."""
    monkeypatch.setattr(voice_module, "_sarvam", lambda audio: None)
    monkeypatch.setattr(voice_module, "_groq", lambda audio: "How do I get a mutual consent divorce?")

    text, provider = voice_module.transcribe_detail(clip())
    assert text.startswith("How do I get")
    assert provider == "groq"


def test_empty_transcript_counts_as_failure(monkeypatch):
    """A provider that answers 200 with nothing has not answered. Falling
    through to Groq here is the difference between a working feature and a
    silent one."""
    monkeypatch.setattr(voice_module, "_sarvam", lambda audio: "   ")
    monkeypatch.setattr(voice_module, "_groq", lambda audio: "real text")

    assert voice_module.transcribe_detail(clip()) == ("real text", "groq")


def test_a_pause_does_not_end_anything(monkeypatch):
    """The bug this whole path exists to fix: pausing to think used to fire the
    first half of a sentence as the question. Recording is bounded by time, not
    by silence, so a long pause is just a longer clip."""
    assert voice_module.MAX_AUDIO_SECONDS >= 15
    # The server accepts a clip long enough to contain a real pause.
    big = base64.b64encode(b"\x00" * 400_000).decode()
    assert len(big) < voice_module.MAX_AUDIO_B64_CHARS
    assert voice_module._decode(big)


def test_silence_is_rejected_before_paying_for_it(monkeypatch):
    """Transcribing 50ms of nothing would spend a paid call to return empty."""
    def never(audio):
        raise AssertionError("no provider should be called for silence")

    monkeypatch.setattr(voice_module, "_sarvam", never)
    monkeypatch.setattr(voice_module, "_groq", never)

    with pytest.raises(voice_module.VoiceError):
        voice_module.transcribe(base64.b64encode(b"\x00" * 8).decode())


def test_transcribe_endpoint_returns_text_only(client, monkeypatch):
    """Audio becomes text and nothing else: no session, no agent run, no
    answer. The transcript has to reach the input box where the user can read
    it before it becomes a question."""
    monkeypatch.setattr(voice_module, "_sarvam", lambda audio: "he does not let me leave the house")
    monkeypatch.setattr(voice_module, "_groq", lambda audio: None)

    r = client.post("/voice/transcribe", json={"audio_b64": clip(), "lang": "en"},
                    headers=bff_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["transcript"] == "he does not let me leave the house"
    assert body["provider"] == "sarvam"
    assert body["error"] is None
    # The transcript must not have been persisted as a user message: it has
    # not been asked yet.
    assert client.get("/sessions", headers=bff_headers()).json() == []


def test_transcribe_endpoint_reports_failure_without_500(client, monkeypatch):
    """A bad clip is something the user fixes by speaking again. A 500 would
    show as a crash and tell them nothing."""
    monkeypatch.setattr(voice_module, "_sarvam", lambda audio: None)
    monkeypatch.setattr(voice_module, "_groq", lambda audio: None)

    r = client.post("/voice/transcribe", json={"audio_b64": clip(), "lang": "hi"},
                    headers=bff_headers())
    assert r.status_code == 200
    body = r.json()
    assert body["transcript"] == ""
    # A sentence the user can act on, not a machine code.
    assert body["error"] == "Voice input failed. Please type your question instead."


def test_transcribe_needs_login(client):
    """Transcribing costs money. An open endpoint that forwards audio to a paid
    provider is not something to leave on the internet."""
    assert client.post("/voice/transcribe", json={"audio_b64": clip()}).status_code == 401


def test_transcribe_rejects_an_oversized_clip(client):
    """The ceiling is what stops a hand-crafted request being a cheap way to
    make somebody else pay for an hour of audio."""
    huge = "A" * 3_000_000
    assert client.post("/voice/transcribe", json={"audio_b64": huge},
                       headers=bff_headers()).status_code == 422