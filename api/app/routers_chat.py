from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import auth as auth_lib
from app import db as db_module
from app.models import ChatSession, Memory, Message, User
from app.schemas import (
    MemoriesOut,
    MemoryIn,
    MemoryOut,
    MessageIn,
    MessageOut,
    SessionIn,
    SessionOut,
    UserOut,
)

router = APIRouter(tags=["chat"])


def _session_owned(session_id: int, user: User, db: Session) -> ChatSession:
    chat = db.query(ChatSession).filter_by(id=session_id, user_id=user.id).first()
    if chat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Session not found")
    return chat


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


@router.post("/sessions/{session_id}/messages", response_model=MessageOut, status_code=201)
def post_message(session_id: int, body: MessageIn,
                 user: User = Depends(auth_lib.current_user),
                 db: Session = Depends(db_module.get_session)):
    _session_owned(session_id, user, db)
    msg = Message(session_id=session_id, role=body.role, content=body.content, lang=body.lang)
    db.add(msg)
    db.flush()
    return MessageOut(id=msg.id, role=msg.role, content=msg.content, lang=msg.lang)


@router.get("/sessions/{session_id}/messages", response_model=List[MessageOut])
def get_messages(session_id: int,
                 user: User = Depends(auth_lib.current_user),
                 db: Session = Depends(db_module.get_session)):
    _session_owned(session_id, user, db)
    msgs = db.query(Message).filter_by(session_id=session_id).order_by(Message.id).all()
    return [MessageOut(id=m.id, role=m.role, content=m.content, lang=m.lang) for m in msgs]


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
