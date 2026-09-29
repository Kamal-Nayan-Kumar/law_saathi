def test_health_green(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_root_is_informational_not_404(client):
    """The public URL of the API lands on `/`, so it must answer instead of 404."""
    res = client.get("/")
    assert res.status_code == 200
    body = res.json()
    assert body["service"] == "LawSaathi API"
    assert body["docs"] == "/docs"
    assert "/health" in body["endpoints"]
