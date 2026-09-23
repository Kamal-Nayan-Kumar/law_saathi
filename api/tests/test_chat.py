from tests.conftest import stack_headers


def test_chat_history_persists_per_user(client):
    h1 = stack_headers("u1")
    h2 = stack_headers("u2")

    s = client.post("/sessions", json={"title": "divorce"}, headers=h1)
    assert s.status_code == 201
    sid = s.json()["id"]

    assert client.post(f"/sessions/{sid}/messages",
                       json={"role": "user", "content": "What is maintenance?", "lang": "en"},
                       headers=h1).status_code == 201
    assert client.post(f"/sessions/{sid}/messages",
                       json={"role": "assistant", "content": "Support after separation. [HAMA Sec 18]", "lang": "en"},
                       headers=h1).status_code == 201

    history = client.get(f"/sessions/{sid}/messages", headers=h1)
    assert history.status_code == 200
    assert [m["content"] for m in history.json()] == [
        "What is maintenance?",
        "Support after separation. [HAMA Sec 18]",
    ]

    # user 2 cannot see user 1's session
    assert client.get(f"/sessions/{sid}/messages", headers=h2).status_code == 404
    mine = client.get("/sessions", headers=h2)
    assert mine.status_code == 200
    assert mine.json() == []


def test_message_needs_login(client):
    assert client.post("/sessions", json={}).status_code == 401
