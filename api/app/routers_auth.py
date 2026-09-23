from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app import auth as auth_lib
from app import db as db_module
from app.models import User
from app.schemas import LoginIn, RegisterIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: RegisterIn, session: Session = Depends(db_module.get_session)):
    if session.query(User).filter_by(email=body.email).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already registered")
    user = User(email=body.email, password_hash=auth_lib.hash_password(body.password))
    session.add(user)
    session.flush()
    return UserOut(id=user.id, email=user.email,
                   preferred_lang=user.preferred_lang, tone=user.tone)


@router.post("/login", response_model=TokenOut)
def login(body: LoginIn, session: Session = Depends(db_module.get_session)):
    user = session.query(User).filter_by(email=body.email).first()
    if user is None or not auth_lib.check_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Wrong email or password")
    return TokenOut(access_token=auth_lib.make_token(user.id))
