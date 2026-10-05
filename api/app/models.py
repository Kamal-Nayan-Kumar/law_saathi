"""Neon schema: users, sessions, messages, memories."""
from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stack Auth (Neon Auth) subject. NULL only for legacy local rows.
    external_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=True)
    email: Mapped[str] = mapped_column(String(255), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=True)  # legacy local auth
    preferred_lang: Mapped[str] = mapped_column(String(8), default="en")
    tone: Mapped[str] = mapped_column(String(16), default="simple")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ChatSession(Base):
    __tablename__ = "sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255), default="New chat")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user | assistant
    content: Mapped[str] = mapped_column(Text)
    lang: Mapped[str] = mapped_column(String(8), default="en")
    # Sources for an assistant turn, so a reopened chat still renders the
    # Sources list. NULL for rows written before these columns existed.
    citations: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    citation_sources: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    # The agent's step log, so the "Thinking" panel survives a reload instead of
    # silently disappearing the next time the chat is opened.
    trace: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    trace_detail: Mapped[Optional[list]] = mapped_column(JSON, nullable=True, default=list)
    verified: Mapped[Optional[bool]] = mapped_column(nullable=True)
    confidence: Mapped[Optional[float]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class Memory(Base):
    """Per-user long-term facts: preferences, retrieved knowledge pointers."""

    __tablename__ = "memories"
    __table_args__ = (UniqueConstraint("user_id", "key", name="uq_memory_user_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    key: Mapped[str] = mapped_column(String(64))
    value: Mapped[str] = mapped_column(Text)


class IngestedChunk(Base):
    """T2: record of each Qdrant point, per ADR-0004 (vectors in Qdrant,
    bookkeeping in Neon). Point ID is the stable uuid5 of act+section+idx,
    so re-runs upsert idempotently."""

    __tablename__ = "ingested_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    point_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    act: Mapped[str] = mapped_column(String(255), index=True)
    section: Mapped[str] = mapped_column(String(255))
    lang: Mapped[str] = mapped_column(String(8), default="en")
    source: Mapped[str] = mapped_column(String(512), default="")
    collection: Mapped[str] = mapped_column(String(128), default="law_saathi")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
