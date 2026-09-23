"""Pytest fixtures: isolated in-memory DB per test, mocked Stack tokens."""
import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["STACK_PROJECT_ID"] = "test-project"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app import auth as auth_module
from app import db as db_module
from app.main import create_app


@pytest.fixture()
def client(monkeypatch):
    def fake_verify(token):
        if token.startswith("good-token-"):
            sub = token[len("good-token-"):]
            return {"sub": sub, "email": sub + "@example.com"}
        raise ValueError("bad token")

    monkeypatch.setattr(auth_module, "verify_stack_token", fake_verify)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db_module.init_db(engine)
    app = create_app(engine)
    with TestClient(app) as c:
        yield c


def stack_headers(sub="user1"):
    return {"x-stack-access-token": "good-token-" + sub}
