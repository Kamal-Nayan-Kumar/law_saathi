"""DB engine + session helpers. Postgres (Neon) in prod, SQLite locally."""
import logging
import os
from typing import Iterator, Optional

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateColumn

logger = logging.getLogger(__name__)

_engine: Optional[Engine] = None
_Session: Optional[sessionmaker] = None


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "sqlite:///./lawsathi.db")


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url, pool_pre_ping=True)


def _add_missing_columns(engine: Engine) -> None:
    """Add model columns to tables that already exist in the database.

    `create_all` only creates missing tables — it never alters one, so a
    column added to a model would stay missing on the already-deployed
    database. This runs on every startup, is a no-op once the columns are
    there, and never raises: a migration failure must not stop the app from
    booting.
    """
    from app.models import Base

    try:
        existing_tables = set(inspect(engine).get_table_names())
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue  # just created by create_all, already up to date
            have = {col["name"] for col in inspect(engine).get_columns(table.name)}
            for column in table.columns:
                if column.name in have:
                    continue
                ddl = str(CreateColumn(column).compile(dialect=engine.dialect))
                with engine.begin() as conn:
                    conn.execute(text("ALTER TABLE %s ADD COLUMN %s"
                                      % (table.name, ddl)))
                logger.info("migration: added %s.%s", table.name, column.name)
    except Exception as exc:  # noqa: BLE001 - best effort, log and carry on
        logger.warning("migration: could not add missing columns (%r)", exc)


def init_db(engine: Engine) -> None:
    """Create tables and remember engine for the app. Returns nothing."""
    global _engine, _Session
    from app.models import Base

    Base.metadata.create_all(engine)
    _add_missing_columns(engine)
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
