"""Sarvam TTS that speaks whichever of the three languages the text is in.

One `sarvam.TTS` instance is bound to one `target_language_code` and one
speaker. A reader who asks in Kannada and gets a Kannada answer cannot be
served by an instance configured for Hindi, and a single instance cannot be
retargeted mid-answer without throwing away the connection it already has.

So this is a router: three Sarvam instances, one per language, and the text's
script decides which one speaks it. The answer from the Law Saathi pipeline
is already written in the language of the question, so the routing is not a
guess: the script of the answer is the script the reader used.

The router declares itself non-streaming on purpose. The framework wraps a
non-streaming TTS in a `StreamAdapter`, which splits the answer into sentences
and calls `synthesize()` once per sentence. Each sentence is routed on its own,
which is the right granularity: a sentence that is half Kannada and half
English goes to the Kannada voice, because that is the language it is mostly
written in.
"""
from __future__ import annotations

import logging

from livekit.agents import APIConnectOptions, DEFAULT_API_CONNECT_OPTIONS, tts
from livekit.plugins import sarvam

from . import config

logger = logging.getLogger(__name__)

# Bulbul v4 speaker ids, one per language. v3 speaker names ("shubh", "priya")
# are rejected by v4, so the model and the speaker list have to agree.
SPEAKERS = {
    "en-IN": "shubh_en_narration_gentle",
    "hi-IN": "aayan_hi_conversational",
    "kn-IN": "chaitra_kn_conversation",
}

# The languages the project covers. Anything else falls back to English, which
# is the only one of the three that is guaranteed to have a voice.
DEFAULT_LANGUAGE = "en-IN"


def detect_language(text: str) -> str:
    """The dominant script of the text, as a Sarvam language code.

    Counting characters rather than looking for the first one matters: a
    Kannada answer that opens with "Section 3 of the Dowry Prohibition Act"
    has Latin characters in it, and a first-match rule would send the whole
    answer to the English voice.
    """
    devanagari = 0
    kannada = 0
    for ch in text:
        code = ord(ch)
        if 0x0900 <= code <= 0x097F:
            devanagari += 1
        elif 0x0C80 <= code <= 0x0CFF:
            kannada += 1
    if kannada > devanagari:
        return "kn-IN"
    if devanagari > 0:
        return "hi-IN"
    return DEFAULT_LANGUAGE


class SarvamLanguageRouter(tts.TTS):
    """Sarvam TTS with one instance per language, picked by the text's script."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "bulbul:v4-flash",
        sample_rate: int = 22050,
    ) -> None:
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=sample_rate,
            num_channels=1,
        )
        # The key comes from api/.env, the same file the API reads, so the
        # worker and the server always bill the same Sarvam account.
        api_key = api_key or config.SARVAM_API_KEY
        if not api_key:
            raise ValueError(
                "SARVAM_API_KEY is not set. The worker reads it from api/.env."
            )
        self._instances: dict[str, sarvam.TTS] = {
            code: sarvam.TTS(
                target_language_code=code,
                model=model,
                speaker=speaker,
                speech_sample_rate=sample_rate,
                api_key=api_key,
            )
            for code, speaker in SPEAKERS.items()
        }

    @property
    def model(self) -> str:
        return "bulbul:v4-flash"

    @property
    def provider(self) -> str:
        return "Sarvam"

    def instance_for(self, text: str) -> sarvam.TTS:
        """The Sarvam instance that should speak this text."""
        code = detect_language(text)
        logger.debug("tts route: %s -> %s", code, text[:60])
        return self._instances[code]

    def synthesize(
        self, text: str, *, conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS
    ) -> tts.ChunkedStream:
        # The delegate owns the connection and the audio bytes; this class
        # only decides who speaks.
        return self.instance_for(text).synthesize(text, conn_options=conn_options)

    def prewarm(self) -> None:
        for instance in self._instances.values():
            instance.prewarm()

    async def aclose(self) -> None:
        for instance in self._instances.values():
            await instance.aclose()
