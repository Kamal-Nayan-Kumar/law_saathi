"""Neon Auth (Stack Auth) verification.

Frontend sends the Stack access token (`await user.getAuthJson()`),
backend verifies it locally via JWKS and auto-provisions the user row.
"""
import os
from functools import lru_cache
from typing import Any, Dict, Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import db as db_module
from app.models import User


def project_id() -> str:
    pid = os.environ.get("STACK_PROJECT_ID") or os.environ.get("NEXT_PUBLIC_STACK_PROJECT_ID", "")
    if not pid:
        raise RuntimeError("Set STACK_PROJECT_ID (Neon Auth → Stack project ID)")
    return pid


def jwks_url() -> str:
    return f"https://api.stack-auth.com/api/v1/projects/{project_id()}/.well-known/jwks.json"


@lru_cache(maxsize=1)
def jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(jwks_url())


def verify_stack_token(token: str) -> Dict[str, Any]:
    """Return decoded claims or raise. ES256, audience = project ID."""
    key = jwks_client().get_signing_key_from_jwt(token)
    return jwt.decode(token, key.key, algorithms=["ES256"], audience=project_id())


def token_from_request(request: Request) -> Optional[str]:
    token = request.headers.get("x-stack-access-token")
    if token:
        return token
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:]
    return None


def current_user(
    request: Request,
    session: Session = Depends(db_module.get_session),
) -> User:
    token = token_from_request(request)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    try:
        claims = verify_stack_token(token)
        sub = claims.get("sub")
    except Exception:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad token")
    if not sub:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad token")
    user = session.query(User).filter_by(external_id=sub).first()
    if user is None:
        user = User(external_id=sub, email=claims.get("email"))
        session.add(user)
        session.flush()
    return user
