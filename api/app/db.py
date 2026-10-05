"""DB engine + session helpers. Postgres (Neon) in prod, SQLite locally."""
import logging
import os
from typing import Iterator, Optional

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateColumn

logger = logging.getLogger(__name__)

_engine: Optional[Engine] = None
_Session: Optional[sessionmaker] = None


def database_url() -> str:
    return os.environ.get("DATABASE_URL", "sqlite:///./lawsathi.db")


def make_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        # Two requests overlapping (a long agent run while the sidebar refreshes
        # the session list) took the SQLite write lock and the loser failed with
        # "database is locked". WAL lets readers run during a write, and the
        # busy timeout makes a writer wait rather than error immediately.
        return create_engine(
            url,
            connect_args={"check_same_thread": False, "timeout": 30},
            poolclass=StaticPool if ":memory:" in url else None,
        )
    return create_engine(url, pool_pre_ping=True)


def _sqlite_pragmas(engine: Engine) -> None:
    """Turn on WAL and a busy timeout for every SQLite connection."""
    if engine.dialect.name != "sqlite":
        return
    try:
        @event.listens_for(engine, "connect")
        def _set_pragmas(dbapi_conn, _record):  # noqa: ANN001
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.close()
    except Exception as exc:  # noqa: BLE001 - never block startup on this
        logger.warning("sqlite pragmas not applied (%r)", exc)


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
    _sqlite_pragmas(engine)
    _add_missing_columns(engine)
    _engine = engine
    _Session = sessionmaker(bind=engine, autoflush=False)


def engine_for_test() -> Engine:
    assert _engine is not None, "init_db was not called"
    return _engine


def new_session() -> Session:
    """A session the caller owns and must close.

    For work that outlives the request — the SSE stream runs the agent in a
    worker thread and persists afterwards, by which time FastAPI has already
    closed the request's session.
    """
    assert _Session is not None, "init_db was not called"
    return _Session()


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
