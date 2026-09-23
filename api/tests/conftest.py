"""Pytest fixtures: isolated in-memory DB per test session."""
import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["AUTH_SECRET"] = "test-secret"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app import db as db_module
from app.main import create_app


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db_module.init_db(engine)
    app = create_app(engine)
    with TestClient(app) as c:
        yield c


def auth_headers(client, email="test@example.com", password="pass1234"):
    client.post("/auth/register", json={"email": email, "password": password})
    res = client.post("/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return {"Authorization": "Bearer " + res.json()["access_token"]}
