def test_health_green(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"
