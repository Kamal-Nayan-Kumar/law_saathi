from typing import List, Optional

from pydantic import BaseModel, Field


class UserOut(BaseModel):
    id: int
    email: Optional[str]
    preferred_lang: str
    tone: str


class SessionIn(BaseModel):
    title: Optional[str] = "New chat"


class SessionOut(BaseModel):
    id: int
    title: str


class SessionPatch(BaseModel):
    title: str = Field(min_length=1, max_length=255)


class MessageIn(BaseModel):
    role: str = Field(pattern="^(user|assistant)$")
    content: str = Field(min_length=1, max_length=20000)
    lang: str = Field(default="en", pattern="^(en|hi|kn)$")


class MessageOut(BaseModel):
    id: int
    role: str
    content: str
    lang: str


class MemoryIn(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=4000)


class MemoryOut(BaseModel):
    key: str
    value: str


class MemoriesOut(BaseModel):
    memories: List[MemoryOut]


class VoiceIn(BaseModel):
    audio_b64: str = Field(min_length=1, max_length=200000)
    lang: str = Field(default="en", pattern="^(en|hi|kn)$")


class VoiceOut(BaseModel):
    transcript: str = ""
    answer: str = ""
    audio_b64: Optional[str] = None
    lang: str = "en"
    fallback_text: bool = False
    error: Optional[str] = None


class AskIn(BaseModel):
    query: str = Field(min_length=1, max_length=20000)
    lang: str = Field(default="en", pattern="^(en|hi|kn)$")
    tone: str = Field(default="simple", pattern="^(simple|detailed)$")
    doc_id: Optional[str] = Field(default="", max_length=64)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class AskOut(BaseModel):
    answer: str
    clarification: bool = False
    citations: List[str] = []
    citation_sources: List[str] = []
    provider: str = ""
    retries: int = 0
    trace: List[str] = []
    verified: bool = False
    confidence: float = 0.0
