from tests.conftest import auth_headers


def test_register_login_me(client):
    assert client.post("/auth/register", json={"email": "a@x.in", "password": "pass1234"}).status_code == 201
    res = client.post("/auth/login", json={"email": "a@x.in", "password": "pass1234"})
    assert res.status_code == 200
    assert "access_token" in res.json()
    me = client.get("/me", headers={"Authorization": "Bearer " + res.json()["access_token"]})
    assert me.status_code == 200
    assert me.json()["email"] == "a@x.in"


def test_register_duplicate_rejected(client):
    client.post("/auth/register", json={"email": "a@x.in", "password": "pass1234"})
    res = client.post("/auth/register", json={"email": "a@x.in", "password": "pass1234"})
    assert res.status_code == 409


def test_login_wrong_password_rejected(client):
    client.post("/auth/register", json={"email": "a@x.in", "password": "pass1234"})
    res = client.post("/auth/login", json={"email": "a@x.in", "password": "wrong"})
    assert res.status_code == 401


def test_me_without_token_rejected(client):
    assert client.get("/me").status_code == 401


def test_password_not_stored_plain(client):
    client.post("/auth/register", json={"email": "a@x.in", "password": "pass1234"})
    from app import db as db_module
    from app.models import User
    from sqlalchemy.orm import Session

    with Session(db_module.engine_for_test()) as s:
        user = s.query(User).filter_by(email="a@x.in").one()
        assert user.password_hash != "pass1234"
