"""Pytest fixtures: isolated in-memory DB, BFF headers."""
import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["INTERNAL_API_SECRET"] = "test-internal"

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


def bff_headers(sub="user1"):
    return {
        "x-internal-secret": "test-internal",
        "x-user-id": sub,
        "x-user-email": sub + "@example.com",
    }
