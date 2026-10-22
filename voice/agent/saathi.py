"""The Law Saathi voice agent.

Three pieces, all of them chosen because they are the free or near-free ones
and because they work in Indian languages:

- STT is Sarvam's realtime endpoint (`sarvam.STTRealtime`). It streams partial
  transcripts and does its own voice activity detection, so the LiveKit turn
  detector is never switched on. Groq Whisper is not an option here: it has no
  streaming endpoint, so the agent would have to buffer and upload a file, and
  the whole point of realtime is not buffering.
- The LLM is the Law Saathi pipeline itself, reached over HTTP. See
  `lawsaathi_llm.py`.
- TTS is Sarvam Bulbul, routed by the script of the text. See `tts_router.py`.

The answer comes back from the pipeline already written in the language of the
question, so it is spoken as it comes. Nothing here translates.
"""
from __future__ import annotations

import logging

from livekit.agents import Agent, AgentSession
from livekit.agents import JobContext
from livekit.plugins import sarvam

from .lawsaathi_llm import LawSaathiLLM
from .tts_router import SarvamLanguageRouter, detect_language

logger = logging.getLogger(__name__)

INSTRUCTIONS = (
    "You are Law Saathi, an assistant for Indian family law. You answer from the "
    "bare statutes, name the section you rely on, and you write in the language "
    "the reader used. You are not a lawyer and you do not give legal advice."
)

# The greeting is spoken once, in the language of the reader's first question.
# It does not go through the pipeline: a greeting is not a legal question, and
# spending a 15 second agent run on "hello" would be silly.
GREETINGS = {
    "en": (
        "Hello. I am Law Saathi. Ask me about family law in English, Hindi or Kannada."
    ),
    "hi": "नमस्ते, मैं लॉ साथी हूँ। कानूनी सवाल पूछिए, मैं हिंदी में जवाब दूँगा।",
    "kn": "ನಮಸ್ಕಾರ, ನಾನು ಲಾ ಸಾಥಿ. ಕಾನೂನು ಪ್ರಶ್ನೆ ಕೇಳಿ, ನಾನು ಕನ್ನಡದಲ್ಲಿ ಉತ್ತರಿಸುತ್ತೇನೆ.",
}


class LawSaathiAgent(Agent):
    """The agent the LiveKit session drives.

    The STT, the pipeline and the voice are all wired here, so the session
    itself stays about the room and the turn handling.
    """

    def __init__(self) -> None:
        super().__init__(
            instructions=INSTRUCTIONS,
            # "auto" is what makes one agent serve three languages: Sarvam
            # identifies the language from the audio, and the pipeline then
            # answers in that same language.
            stt=sarvam.STTRealtime(language="auto", stream_type="fast"),
            llm=LawSaathiLLM(),
            tts=SarvamLanguageRouter(),
        )


def greet(session: AgentSession, transcript: str) -> None:
    """Speak the opening line in the language of the first question."""
    code = detect_language(transcript)
    greeting = GREETINGS.get(code, GREETINGS["en"])
    logger.info("greeting in %s", code)
    session.say(greeting)


def build_session() -> AgentSession:
    """The session, with the turn handling the project needs.

    `turn_detection="stt"` means the Sarvam endpoint's own voice activity
    detection decides when the reader has finished speaking. LiveKit's
    turn detector is not used at all, which is both more accurate for code
    mixed speech and free: the LiveKit Build plan is a hard cap on usage and
    there is no reason to spend it on turn detection.
    """
    from livekit.agents import TurnHandlingOptions

    return AgentSession(
        turn_handling=TurnHandlingOptions(
            turn_detection="stt",
            # 70 ms is the pause that counts as the end of a turn. The default
            # of 500 ms makes the agent feel slow, and Sarvam's own VAD has
            # already decided that the speaker stopped.
            endpointing={"min_delay": 0.07},
        )
    )


async def run(ctx: JobContext) -> None:
    """One LiveKit session: connect, serve, wait."""
    await ctx.connect()
    logger.info("connected to room %s", ctx.room.name)

    session = build_session()
    greeted = False

    def _on_transcribed(ev) -> None:
        nonlocal greeted
        if greeted or not getattr(ev, "is_final", False):
            return
        if not (ev.transcript or "").strip():
            return
        greeted = True
        logger.info("user said: %s", ev.transcript)
        greet(session, ev.transcript)

    session.on("user_input_transcribed", _on_transcribed)
    await session.start(agent=LawSaathiAgent(), room=ctx.room)
    logger.info("session started")
    await ctx.wait_for_disconnect()
