"""The Law Saathi pipeline as a LiveKit LLM.

The point of this project is not "a voice agent that talks to a model". It is
that the voice agent answers from the bare Acts, cites the section, and speaks
in the reader's own language. So the LLM step of the LiveKit agent is not an
LLM at all: it is the five-node LangGraph pipeline in `api/app/agent.py`,
reached over HTTP.

Two consequences worth stating plainly:

- The answer arrives already written in the language of the question. The
  rewrite to Hindi or Kannada happens inside the pipeline, so there is no
  second translation step here and nothing to get out of sync.
- The pipeline takes 10 to 20 seconds. The LiveKit session has to survive that
  wait without the user thinking the agent hung, which is what the spoken
  "working on it" line and the long HTTP timeout are for.

Authentication is the same trick `api/scripts/probe.py` uses: the FastAPI
trusts `x-internal-secret` and `x-user-id` headers, which the Next.js BFF
normally injects from a verified session. The voice worker runs on the same
machine and holds the same secret, so it asks the API directly.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import httpx
from livekit.agents import APIConnectionError, APIStatusError, llm

from . import config

logger = logging.getLogger(__name__)


class LawSaathiError(RuntimeError):
    """The Law Saathi API did not answer."""


class LawSaathiClient:
    """A thin HTTP client for the two endpoints the worker needs.

    Only `POST /sessions` and `POST /sessions/{id}/ask` are used. The ask
    endpoint is the one the browser calls, so the answer is the same answer
    the text chat gives, with the same citations and the same refusal rules.
    """

    def __init__(
        self,
        base_url: str | None = None,
        secret: str | None = None,
        user_id: int | None = None,
        user_email: str | None = None,
        timeout: float | None = None,
    ) -> None:
        self.base_url = (base_url or config.LAWSAATHI_API).rstrip("/")
        self.secret = secret if secret is not None else config.INTERNAL_API_SECRET
        self.user_id = user_id if user_id is not None else int(config.LAWSAATHI_USER_ID)
        self.user_email = user_email or config.LAWSAATHI_USER_EMAIL
        self.timeout = timeout if timeout is not None else config.LAWSAATHI_TIMEOUT
        if not self.secret:
            raise LawSaathiError(
                "INTERNAL_API_SECRET is not set. The voice worker reads it from api/.env; "
                "export it or run the worker from the repo root."
            )
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-internal-secret": self.secret,
            "x-user-id": str(self.user_id),
            "x-user-email": self.user_email,
        }

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = await self._client.post(path, json=body, headers=self._headers())
        except httpx.HTTPError as exc:
            raise APIConnectionError(f"Law Saathi API unreachable at {self.base_url}: {exc}") from exc
        if resp.status_code >= 400:
            # The body carries the FastAPI detail, which is the only useful
            # thing in a failure log, but it can echo the query back.
            raise APIStatusError(
                message=f"Law Saathi API {resp.status_code} on {path}",
                status_code=resp.status_code,
                body=resp.text[:400],
            )
        return resp.json()

    async def new_session(self, title: str = "Voice session") -> int:
        data = await self._post("/sessions", {"title": title})
        return int(data["id"])

    async def ask(self, session_id: int, query: str, lang: str = "en") -> dict[str, Any]:
        # `lang` is a hint only. The server decides the answer's language from
        # the script of the question, which is the behaviour the text chat has.
        return await self._post(
            f"/sessions/{session_id}/ask",
            {"query": query, "lang": lang, "tone": "simple"},
        )


def detect_language(text: str) -> str:
    """The script of the text decides the language: en, hi or kn.

    Mirrors `api/app/agent.py:detect_lang` so the worker and the pipeline
    agree on which language a question was asked in.
    """
    if any("\u0c80" <= ch <= "\u0cff" for ch in text):
        return "kn"
    if any("\u0900" <= ch <= "\u097f" for ch in text):
        return "hi"
    return "en"


class _LawSaathiStream(llm.LLMStream):
    """One turn of the Law Saathi pipeline, streamed back as one text chunk.

    The pipeline does not stream its tokens, so there is nothing to interleave.
    The whole answer arrives at once and is pushed as a single chunk, which the
    framework then splits into sentences for the TTS.
    """

    def __init__(
        self,
        *,
        llm_instance: "LawSaathiLLM",
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool],
        conn_options: Any,
    ) -> None:
        super().__init__(
            llm_instance,
            chat_ctx=chat_ctx,
            tools=tools,
            conn_options=conn_options,
        )

    async def _run(self) -> None:
        question = self._last_user_text()
        if not question:
            self._event_ch.send_nowait(
                llm.ChatChunk(
                    id="law-saathi-empty",
                    delta=llm.ChoiceDelta(
                        role="assistant",
                        content="I did not hear a question. Please ask again.",
                    ),
                )
            )
            return

        started = time.perf_counter()
        logger.info("law saathi ask: %s", question[:120])
        session_id = await self._llm.ensure_session()
        payload = await self._llm.client.ask(
            session_id, question, lang=detect_language(question)
        )
        answer = str(payload.get("answer") or "").strip()
        if not answer:
            # The pipeline persists the turn either way, so an empty answer is
            # its own failure and saying so is better than speaking nothing.
            answer = (
                "I could not answer that just now. Please try again, or type your "
                "question so I can read it exactly as written."
            )
        logger.info(
            "law saathi answered in %.1fs lang=%s citations=%d",
            time.perf_counter() - started,
            payload.get("lang"),
            len(payload.get("citations") or []),
        )
        self._event_ch.send_nowait(
            llm.ChatChunk(
                id=f"law-saathi-{session_id}",
                delta=llm.ChoiceDelta(role="assistant", content=answer),
            )
        )

    def _last_user_text(self) -> str:
        """The most recent user message, which is the question just spoken.

        The agent's instructions and the previous turns are ignored on
        purpose: the Law Saathi API keeps its own conversation history in the
        session it created, and it wants the raw question, not a transcript of
        the dialogue.
        """
        for item in reversed(self._chat_ctx.items):
            if getattr(item, "role", None) != "user":
                continue
            text = getattr(item, "raw_text_content", None)
            if not text:
                content = getattr(item, "content", None)
                if isinstance(content, list):
                    text = "\n".join(part for part in content if isinstance(part, str))
                elif isinstance(content, str):
                    text = content
            if text and text.strip():
                return text.strip()
        return ""


class LawSaathiLLM(llm.LLM):
    """The Law Saathi pipeline behind the LiveKit agent's LLM step.

    One instance per LiveKit session, so the API chat session it opens is the
    same conversation for the whole call.
    """

    def __init__(self, client: LawSaathiClient | None = None) -> None:
        super().__init__()
        self.client = client or LawSaathiClient()
        self._session_id: int | None = None

    @property
    def model(self) -> str:
        return "law-saathi-pipeline"

    @property
    def provider(self) -> str:
        return "law-saathi"

    @property
    def session_id(self) -> int | None:
        """The API chat session id, once the first question has opened it."""
        return self._session_id

    async def ensure_session(self) -> int:
        """The API chat session, opened on first use.

        Opening it lazily keeps the worker from creating a row in the API's
        database for every participant who connects and never speaks.
        """
        if self._session_id is None:
            self._session_id = await self.client.new_session(title="Voice session")
            logger.info("law saathi session %s opened", self._session_id)
        return self._session_id

    def chat(
        self,
        *,
        chat_ctx: llm.ChatContext,
        tools: list[llm.Tool] | None = None,
        conn_options: Any = None,
        parallel_tool_calls: Any = None,
        tool_choice: Any = None,
        extra_kwargs: Any = None,
    ) -> llm.LLMStream:
        if conn_options is None:
            from livekit.agents import DEFAULT_API_CONNECT_OPTIONS

            conn_options = DEFAULT_API_CONNECT_OPTIONS
        return _LawSaathiStream(
            llm_instance=self,
            chat_ctx=chat_ctx,
            tools=tools or [],
            conn_options=conn_options,
        )

    async def aclose(self) -> None:
        await super().aclose()
        await self.client.aclose()
