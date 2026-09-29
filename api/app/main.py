"""LawSaathi API — FastAPI gateway (T1 scaffold; agent graph lands in T3)."""
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from sqlalchemy.engine import Engine

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app import db as db_module
from app.routers_chat import router as chat_router
from app.routers_upload import router as upload_router


def create_app(engine: Optional[Engine] = None) -> FastAPI:
    app = FastAPI(title="LawSaathi API")
    db_module.init_db(engine or db_module.make_engine(db_module.database_url()))
    app.include_router(chat_router)
    app.include_router(upload_router)

    @app.get("/")
    def root():
        """The bare API URL is the first thing anyone opens, so answer with
        something useful instead of a bare 404."""
        return {
            "service": "LawSaathi API",
            "docs": "/docs",
            "endpoints": ["/health", "/sessions", "/upload/pdf", "/me"],
        }

    @app.get("/health")
    def health():
        return {"status": "ok"}

    return app


app = create_app()
