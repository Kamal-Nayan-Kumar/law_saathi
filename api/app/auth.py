"""BFF auth: only the Next.js layer calls FastAPI.

The browser never talks to FastAPI directly. Next.js verifies the
Neon Auth (Better Auth) session, then forwards the request with the
internal secret + resolved user id. See ADR-0008.
"""
import os

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import db as db_module
from app.models import User


def internal_secret() -> str:
    secret = os.environ.get("INTERNAL_API_SECRET", "")
    if not secret:
        raise RuntimeError("Set INTERNAL_API_SECRET (shared with web/.env.local)")
    return secret


def current_user(
    request: Request,
    session: Session = Depends(db_module.get_session),
) -> User:
    if request.headers.get("x-internal-secret") != internal_secret():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    sub = request.headers.get("x-user-id", "")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    user = session.query(User).filter_by(external_id=sub).first()
    if user is None:
        user = User(external_id=sub, email=request.headers.get("x-user-email") or None)
        session.add(user)
        session.flush()
    return user
