"""LawSaathi API — FastAPI gateway (T1 scaffold; agent graph lands in T3)."""
from typing import Optional

from fastapi import FastAPI
from sqlalchemy.engine import Engine

from app import db as db_module
from app.routers_auth import router as auth_router
from app.routers_chat import router as chat_router


def create_app(engine: Optional[Engine] = None) -> FastAPI:
    app = FastAPI(title="LawSaathi API")
    db_module.init_db(engine or db_module.make_engine(db_module.database_url()))
    app.include_router(auth_router)
    app.include_router(chat_router)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
