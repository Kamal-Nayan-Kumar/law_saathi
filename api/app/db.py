"""DB engine + session helpers. Postgres (Neon) in prod, SQLite locally."""
import os
from typing import Iterator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Optional[Engine] = None
_Session: Optional[sessionmaker] = None


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "sqlite:///./lawsathi.db")


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True)


def init_db(engine: Engine) -> None:
    """Create tables and remember engine for the app. Returns nothing."""
    global _engine, _Session
    from app.models import Base

    Base.metadata.create_all(engine)
    _engine = engine
    _Session = sessionmaker(bind=engine, autoflush=False)


def engine_for_test() -> Engine:
    assert _engine is not None, "init_db was not called"
    return _engine


def get_session() -> Iterator[Session]:
    assert _Session is not None, "init_db was not called"
    session = _Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
