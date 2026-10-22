"""LiveKit Voice Agent for Law Saathi.

Realtime voice conversation in English, Hindi, and Kannada.
- STT: Sarvam STTRealtime (Streaming WebSocket, server-side VAD, auto language detection)
- LLM / Reasoner: Law Saathi Agentic Pipeline (RAG + Verifier + Native Rewrite)
- TTS: Multilingual Sarvam TTS (Bulbul v4-flash with Kannada, Hindi, and English voice routing)
"""

import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

# Load env from parent repo
ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / "api" / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env")

from livekit import agents
from livekit.agents import Agent, AgentServer, AgentSession, TurnHandlingOptions, llm, tts
from livekit.agents.types import APIConnectOptions
from livekit.plugins import sarvam

logger = logging.getLogger("law-voice-agent")
logging.basicConfig(level=logging.INFO)

SARVAM_API_KEY = os.environ.get("SARVAM_API_KEY", "")
INTERNAL_API_SECRET = os.environ.get("INTERNAL_API_SECRET", "")
FASTAPI_URL = os.environ.get("FASTAPI_URL", "http://127.0.0.1:8000")


def clean_for_speech(text: str) -> str:
    """Format markdown legal prose into clean conversational speech."""
    plain = text.replace("```", " ").replace("#", "").replace("*", "").replace(">", "").replace("_", "")
    plain = re.sub(r"\[\d+\]", "", plain)
    plain = re.sub(r"https?://\S+", "", plain)
    cut = re.split(
        r"what to do next|आगे क्या करें|ಮುಂದಿನ ಏನು ಮಾಡಬೇಕು|ಮುಂದೆ ಏನು ಮಾಡಬೇಕು",
        plain,
        flags=re.IGNORECASE,
    )[0]
    return re.sub(r"\s+", " ", cut).strip()


class MultilingualSarvamTTS(tts.TTS):
    """Dynamic TTS router that directs speech to native language speakers.

    Kannada -> chaitra_kn_conversation
    Hindi   -> aayan_hi_conversational
    English -> shubh_en_narration_gentle
    """

    def __init__(self, api_key: Optional[str] = None):
        super().__init__(
            capabilities=tts.TTSCapabilities(streaming=False),
            sample_rate=22050,
            num_channels=1,
        )
        self.api_key = api_key or SARVAM_API_KEY
        self._hi = sarvam.TTS(
            target_language_code="hi-IN",
            model="bulbul:v4-flash",
            speaker="aayan_hi_conversational",
            api_key=self.api_key,
        )
        self._kn = sarvam.TTS(
            target_language_code="kn-IN",
            model="bulbul:v4-flash",
            speaker="chaitra_kn_conversation",
            api_key=self.api_key,
        )
        self._en = sarvam.TTS(
            target_language_code="en-IN",
            model="bulbul:v4-flash",
            speaker="shubh_en_narration_gentle",
            api_key=self.api_key,
        )

    def _select(self, text: str) -> tts.TTS:
        if re.search(r"[\u0C80-\u0CFF]", text):
            return self._kn
        if re.search(r"[\u0900-\u097F]", text):
            return self._hi
        return self._en

    def synthesize(self, text: str, *, conn_options: Optional[APIConnectOptions] = None) -> tts.ChunkedStream:
        target = self._select(text)
        return target.synthesize(text, conn_options=conn_options) if conn_options else target.synthesize(text)


class LawSaathiLLMStream(llm.LLMStream):
    """Streams verified answers from the Law Saathi 5-node RAG pipeline."""

    async def _run(self) -> None:
        msgs = self._chat_ctx.messages() if callable(self._chat_ctx.messages) else self._chat_ctx.messages
        user_msgs = [m for m in msgs if m.role == "user"]
        query = user_msgs[-1].content if user_msgs else ""
        if isinstance(query, list):
            query = " ".join(str(p) for p in query)

        logger.info("Voice query received: %r", query)
        headers = {
            "Content-Type": "application/json",
            "x-internal-secret": INTERNAL_API_SECRET,
            "x-user-id": "1",
            "x-user-email": "voice@example.com",
        }

        answer = ""
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                # 1. Create a transient session
                sess_res = await client.post(
                    f"{FASTAPI_URL}/sessions",
                    json={"title": f"Voice: {query[:30]}"},
                    headers=headers,
                )
                session_id = sess_res.json()["id"]

                # 2. Run the agent pipeline
                ask_res = await client.post(
                    f"{FASTAPI_URL}/sessions/{session_id}/ask",
                    json={"query": query, "lang": "en", "tone": "simple"},
                    headers=headers,
                )
                if ask_res.status_code == 200:
                    answer = ask_res.json().get("answer", "")
                else:
                    logger.warning("FastAPI ask failed: %s %s", ask_res.status_code, ask_res.text[:200])
        except Exception as exc:
            logger.error("Failed to connect to Law Saathi API: %r", exc)

        if not answer:
            answer = "I am having trouble reaching the legal knowledge base right now. Please try again in a moment."

        spoken_text = clean_for_speech(answer)
        logger.info("Spoken answer: %r", spoken_text[:120])

        self._event_ch.send_nowait(
            llm.ChatChunk(
                id="answer",
                delta=llm.ChoiceDelta(
                    content=spoken_text,
                    role="assistant",
                ),
            )
        )


class LawSaathiLLM(llm.LLM):
    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: Optional[list] = None,
        conn_options: Optional[APIConnectOptions] = None,
    ) -> llm.LLMStream:
        return LawSaathiLLMStream(
            self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options or APIConnectOptions(),
        )


class LawSaathiVoiceAgent(Agent):
    def __init__(self) -> None:
        super().__init__(
            instructions=(
                "You are Law Saathi, an accessible legal-support voice companion for Indian family law. "
                "You answer user queries grounded in statutory bare acts in their own language."
            ),
            stt=sarvam.STTRealtime(
                language="auto",
                stream_type="fast",
                mode="transcribe",
                api_key=SARVAM_API_KEY,
            ),
            llm=LawSaathiLLM(),
            tts=MultilingualSarvamTTS(api_key=SARVAM_API_KEY),
        )


server = AgentServer()


@server.rtc_session(agent_name="law-voice")
async def law_voice_session(ctx: agents.JobContext):
    logger.info("Client connected to room: %s", ctx.room.name)
    session = AgentSession(
        turn_handling=TurnHandlingOptions(
            turn_detection="stt",
            endpointing={"min_delay": 0.07},
        ),
    )
    await session.start(agent=LawSaathiVoiceAgent(), room=ctx.room)
    await session.generate_reply(
        instructions="Greet the user warmly in English and Hindi and say you are Law Saathi, ready to help with family law questions."
    )


if __name__ == "__main__":
    agents.cli.run_app(server)
