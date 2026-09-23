"""JWT auth: bcrypt passwords, 7-day tokens."""
import os
from datetime import datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app import db as db_module
from app.models import User

ALGORITHM = "HS256"
TOKEN_DAYS = 7

bearer = HTTPBearer(auto_error=False)


def secret() -> str:
    return os.environ.get("AUTH_SECRET", "dev-only-change-me")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def check_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def make_token(user_id: int) -> str:
    exp = datetime.utcnow() + timedelta(days=TOKEN_DAYS)
    return jwt.encode({"sub": str(user_id), "exp": exp}, secret(), algorithm=ALGORITHM)


def current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
    session: Session = Depends(db_module.get_session),
) -> User:
    if creds is None or not creds.credentials:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    try:
        payload = jwt.decode(creds.credentials, secret(), algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Bad token")
    user = session.get(User, int(payload.get("sub") or 0))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown user")
    return user
