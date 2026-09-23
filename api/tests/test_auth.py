from tests.conftest import stack_headers


def test_me_provisions_stack_user(client):
    res = client.get("/me", headers=stack_headers("user1"))
    assert res.status_code == 200
    assert res.json()["email"] == "user1@example.com"
    # second call returns the same user, no duplicate
    again = client.get("/me", headers=stack_headers("user1"))
    assert again.json()["id"] == res.json()["id"]


def test_me_bad_token_rejected(client):
    assert client.get("/me", headers={"x-stack-access-token": "junk"}).status_code == 401


def test_me_without_token_rejected(client):
    assert client.get("/me").status_code == 401
