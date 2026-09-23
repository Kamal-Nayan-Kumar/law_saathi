from tests.conftest import bff_headers


def test_me_provisions_user(client):
    res = client.get("/me", headers=bff_headers("user1"))
    assert res.status_code == 200
    assert res.json()["email"] == "user1@example.com"
    again = client.get("/me", headers=bff_headers("user1"))
    assert again.json()["id"] == res.json()["id"]


def test_me_wrong_secret_rejected(client):
    bad = dict(bff_headers("user1"), **{"x-internal-secret": "wrong"})
    assert client.get("/me", headers=bad).status_code == 401


def test_me_without_headers_rejected(client):
    assert client.get("/me").status_code == 401
