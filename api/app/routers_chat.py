import json
import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import auth as auth_lib
from app import db as db_module
from app import obs as obs_module
from app.models import ChatSession, Memory, Message, User
from app.schemas import (
    AskIn,
    AskOut,
    MemoriesOut,
    MemoryIn,
    MemoryOut,
    MessageIn,
    MessageOut,
    SessionIn,
    SessionOut,
    SessionPatch,
    UserOut,
    VoiceIn,
    VoiceOut,
)

router = APIRouter(tags=["chat"])
logger = logging.getLogger(__name__)


def _message_out(msg: Message) -> MessageOut:
    """Rows written before the citations and trace columns existed hold NULL."""
    return MessageOut(id=msg.id, role=msg.role, content=msg.content, lang=msg.lang,
                      citations=list(msg.citations or []),
                      citation_sources=list(msg.citation_sources or []),
                      created_at=msg.created_at.isoformat() if msg.created_at else None,
                      trace=list(msg.trace or []),
                      trace_detail=list(msg.trace_detail or []),
                      verified=msg.verified,
                      confidence=msg.confidence)


def _session_owned(session_id: int, user: User, db: Session) -> ChatSession:
    chat = db.query(ChatSession).filter_by(id=session_id, user_id=user.id).first()
    if chat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return chat


@router.put("/me", response_model=UserOut)
def update_me(body: dict,
             user: User = Depends(auth_lib.current_user),
             db: Session = Depends(db_module.get_session)):
    if "preferred_lang" in body:
        user.preferred_lang = str(body["preferred_lang"])
    if "tone" in body:
        user.tone = str(body["tone"])
    db.flush()
    return UserOut(id=user.id, email=user.email,
                   preferred_lang=user.preferred_lang, tone=user.tone)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(auth_lib.current_user)):
    return UserOut(id=user.id, email=user.email,
                   preferred_lang=user.preferred_lang, tone=user.tone)


@router.post("/sessions", response_model=SessionOut, status_code=201)
def create_session(body: SessionIn,
                   user: User = Depends(auth_lib.current_user),
                   db: Session = Depends(db_module.get_session)):
    chat = ChatSession(user_id=user.id, title=body.title or "New chat")
    db.add(chat)
    db.flush()
    return SessionOut(id=chat.id, title=chat.title)


@router.get("/sessions", response_model=List[SessionOut])
def list_sessions(user: User = Depends(auth_lib.current_user),
                  db: Session = Depends(db_module.get_session)):
    chats = db.query(ChatSession).filter_by(user_id=user.id).order_by(ChatSession.id).all()
    return [SessionOut(id=c.id, title=c.title) for c in chats]


@router.patch("/sessions/{session_id}", response_model=SessionOut)
def rename_session(session_id: int, body: SessionPatch,
                   user: User = Depends(auth_lib.current_user),
                   db: Session = Depends(db_module.get_session)):
    chat = _session_owned(session_id, user, db)
    chat.title = body.title.strip() or chat.title
    db.flush()
    return SessionOut(id=chat.id, title=chat.title)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(session_id: int,
                   user: User = Depends(auth_lib.current_user),
                   db: Session = Depends(db_module.get_session)):
    chat = _session_owned(session_id, user, db)
    db.query(Message).filter_by(session_id=chat.id).delete()
    db.delete(chat)
    db.flush()
    return None


@router.post("/sessions/{session_id}/messages", response_model=MessageOut, status_code=201)
def post_message(session_id: int, body: MessageIn,
                 user: User = Depends(auth_lib.current_user),
                 db: Session = Depends(db_module.get_session)):
    _session_owned(session_id, user, db)
    msg = Message(session_id=session_id, role=body.role, content=body.content, lang=body.lang)
    db.add(msg)
    db.flush()
    return _message_out(msg)


@router.get("/sessions/{session_id}/messages", response_model=List[MessageOut])
def get_messages(session_id: int,
                 user: User = Depends(auth_lib.current_user),
                 db: Session = Depends(db_module.get_session)):
    _session_owned(session_id, user, db)
    msgs = db.query(Message).filter_by(session_id=session_id).order_by(Message.id).all()
    return [_message_out(m) for m in msgs]


def _prepare_ask(session_id: int, body: AskIn, user: User, db: Session):
    """Everything the agent needs before it runs: memories, history, language.

    Shared by the JSON endpoint and the streaming one so the two cannot drift —
    they must persist the same rows and detect language the same way.
    """
    from app import agent as agent_module

    chat = _session_owned(session_id, user, db)
    memories = {m.key: m.value
                for m in db.query(Memory).filter_by(user_id=user.id).all()}
    # Conversation context: prior turns of this session for the agent.
    prior = (db.query(Message).filter_by(session_id=session_id)
             .order_by(Message.id.desc()).limit(10).all())
    history = [{"role": m.role, "content": m.content} for m in reversed(prior)]
    # The answer is written in the language the question was asked in. There is
    # no stored language preference any more: a user who once picked "Hindi" and
    # then typed an English question was answered in Hindi, and had to be told
    # their own words were in the wrong language. The script of the question is
    # the signal, and it is the only one.
    body_lang = agent_module.detect_lang(body.query, body.lang)

    # Tone still persists (it changes how long the explanation is), but a saved
    # preference must survive the schema default: body.tone is always populated
    # (it defaults to "simple"), so writing it unconditionally erased the stored
    # preference on every single request.
    tone_mem = memories.get("tone")
    if body.tone != "simple" or not tone_mem:
        memories["tone"] = body.tone
    # Persist memories.
    for k, v in memories.items():
        existing = db.query(Memory).filter_by(user_id=user.id, key=k).first()
        if existing:
            existing.value = v
        else:
            db.add(Memory(user_id=user.id, key=k, value=v))
    db.flush()
    if user.tone != memories["tone"]:
        user.tone = memories["tone"]
    db.add(Message(session_id=session_id, role="user",
                   content=body.query, lang=body_lang))
    db.flush()
    return chat, memories, history, body_lang


def _persist_ask(session_id: int, body: AskIn, user: User, db: Session,
                 memories: Dict[str, str], body_lang: str,
                 state: Dict[str, Any]) -> AskOut:
    """Store what the agent learned and the answer, then build the response.

    Also the single place the AskOut fields are built, so the streaming and
    JSON endpoints can never disagree about what the answer contains.
    """
    # Persist what the agent learned about this user for next time — currently
    # the legal topic, so "what about maintenance?" tomorrow does not restart
    # from nothing.
    for k, v in (state.get("memory_updates") or {}).items():
        # preferred_lang is recorded for the profile only. Nothing reads it to
        # decide how to answer: the answer follows the question's script.
        if k == "preferred_lang":
            continue
        if str(memories.get(k, "")) == str(v):
            continue
        existing = db.query(Memory).filter_by(user_id=user.id, key=k).first()
        if existing:
            existing.value = v
        else:
            db.add(Memory(user_id=user.id, key=k, value=v))
    db.flush()
    db.add(Message(session_id=session_id, role="assistant",
                   content=state.get("answer", ""), lang=body_lang,
                   citations=list(state.get("citations", [])),
                   citation_sources=list(state.get("citation_sources", [])),
                   # Persisted so the Thinking panel still works when the chat
                   # is reopened. It used to be thrown away with the run.
                   trace=list(state.get("trace", [])),
                   trace_detail=list(state.get("trace_detail", [])),
                   verified=bool(state.get("verified", False)),
                   confidence=float(state.get("confidence", 0.0))))
    db.flush()
    # Auto-title untitled sessions from the first question.
    chat = _session_owned(session_id, user, db)
    if chat.title == "New chat":
        chat.title = body.query.strip()[:60]
        db.flush()
    return AskOut(
        answer=state.get("answer", ""),
        clarification=bool(state.get("clarification")),
        citations=list(state.get("citations", [])),
        citation_sources=list(state.get("citation_sources", [])),
        provider=str(state.get("provider", "")),
        retries=int(state.get("retries", 0)),
        trace=list(state.get("trace", [])),
        trace_detail=list(state.get("trace_detail", [])),
        verified=bool(state.get("verified", False)),
        confidence=float(state.get("confidence", 0.0)),
        # Which language the answer was actually written in. The client needs
        # this to pick a speaking voice for "Read aloud", and it is the honest
        # answer to "why is this in the other language" when something goes
        # wrong — without it the field can only be guessed from the request.
        lang=body_lang,
    )


@router.post("/sessions/{session_id}/ask", response_model=AskOut)
def ask(session_id: int, body: AskIn,
        user: User = Depends(auth_lib.current_user),
        db: Session = Depends(db_module.get_session)):
    """T3: run the 5-node agent, persist both turns, return answer + trace."""
    from app import agent as agent_module

    chat, memories, history, body_lang = _prepare_ask(session_id, body, user, db)
    recorder = obs_module.new_run(user_id=user.id, lang=body_lang,
                                  tone=memories["tone"], query=body.query)
    state = agent_module.run_agent(body.query, lang=body_lang, memory=memories,
                                   tone=memories["tone"],
                                   doc_id=body.doc_id or "",
                                   min_score=float(body.min_score),
                                   history=history)
    obs_module.record_run(recorder, state)
    return _persist_ask(session_id, body, user, db, memories, body_lang, state)


@router.post("/sessions/{session_id}/ask/stream")
def ask_stream(session_id: int, body: AskIn,
               user: User = Depends(auth_lib.current_user),
               db: Session = Depends(db_module.get_session)):
    """Server-sent events version of ``ask``.

    A full run takes 10-20s. This reports each agent step the moment it happens,
    so the user sees Saathi working instead of a spinner for the whole time.

    Events: ``step`` (a trace line), ``done`` (the same AskOut payload the JSON
    endpoint returns) or ``error``.
    """
    from app import agent as agent_module
    from app import stream as stream_module
    from fastapi.responses import StreamingResponse

    chat, memories, history, body_lang = _prepare_ask(session_id, body, user, db)
    publisher = stream_module.StepPublisher()
    # Take plain values, not the ORM object: FastAPI closes the request's
    # database session before a streaming body is consumed, so touching `user`
    # from the worker thread raised DetachedInstanceError.
    user_id = user.id
    user_email = user.email
    recorder = obs_module.new_run(user_id=user_id, lang=body_lang,
                                  tone=memories["tone"], query=body.query)

    def run() -> Dict[str, Any]:
        return agent_module.run_agent(
            body.query, lang=body_lang, memory=memories, tone=memories["tone"],
            doc_id=body.doc_id or "", min_score=float(body.min_score),
            history=history, on_step=publisher.publish_state)

    def to_payload(state: Dict[str, Any]) -> Dict[str, Any]:
        # The agent state has already been streamed; only persistence is left.
        # It opens its own session because the request's one is long closed by
        # the time the answer is ready.
        from app.models import User as UserModel

        obs_module.record_run(recorder, state)
        session = db_module.new_session()
        try:
            fresh = session.query(UserModel).filter_by(id=user_id).one()
            out = _persist_ask(session_id, body, fresh, session, memories,
                               body_lang, state)
            session.commit()
            return json.loads(out.model_dump_json())
        finally:
            session.close()

    return StreamingResponse(
        stream_module.run_with_steps(run, publisher, to_payload),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            # Nginx buffers SSE by default, which turns streaming back into one
            # long wait. This is the header that stops it.
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/sessions/{session_id}/voice", response_model=VoiceOut)
def voice_roundtrip(session_id: int, body: VoiceIn,
                    user: User = Depends(auth_lib.current_user),
                    db: Session = Depends(db_module.get_session)):
    """T8: Sarvam STT -> agent -> Sarvam TTS; errors fall back to text."""
    from app import agent as agent_module
    from app import voice as voice_module

    _session_owned(session_id, user, db)
    # STT
    transcript = voice_module.transcribe(body.audio_b64, lang=body.lang)
    if not transcript:
        # Fallback: treat as empty / prompt text fallback
        return VoiceOut(
            transcript="",
            answer="",
            lang=body.lang,
            fallback_text=True,
            error="STT failed; fall back to text input.",
        )
    # Persist user turn like ask endpoint
    db.add(Message(session_id=session_id, role="user",
                   content=transcript, lang=body.lang))
    db.flush()
    # Agent
    memories = {m.key: m.value for m in db.query(Memory).filter_by(user_id=user.id).all()}
    state = agent_module.run_agent(transcript, lang=body.lang, memory=memories, tone="simple")
    answer = state.get("answer", "")
    db.add(Message(session_id=session_id, role="assistant",
                   content=answer, lang=body.lang))
    db.flush()
    # TTS
    audio = voice_module.synthesize(answer, lang=body.lang)
    return VoiceOut(
        transcript=transcript,
        answer=answer,
        audio_b64=audio,
        lang=body.lang,
        fallback_text=False,
        error=None,
    )


@router.get("/me/memories", response_model=MemoriesOut)
def get_memories(user: User = Depends(auth_lib.current_user),
                 db: Session = Depends(db_module.get_session)):
    all_mem = db.query(Memory).filter_by(user_id=user.id).all()
    return MemoriesOut(memories=[MemoryOut(key=m.key, value=m.value) for m in all_mem])


@router.put("/me/memories", response_model=MemoriesOut)
def put_memories(body: List[MemoryIn],
                 user: User = Depends(auth_lib.current_user),
                 db: Session = Depends(db_module.get_session)):
    for item in body:
        existing = db.query(Memory).filter_by(user_id=user.id, key=item.key).first()
        if existing:
            existing.value = item.value
        else:
            db.add(Memory(user_id=user.id, key=item.key, value=item.value))
    db.flush()
    all_mem = db.query(Memory).filter_by(user_id=user.id).all()
    return MemoriesOut(memories=[MemoryOut(key=m.key, value=m.value) for m in all_mem])
