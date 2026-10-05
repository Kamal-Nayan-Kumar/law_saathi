import json

from fastapi.testclient import TestClient

from tests.conftest import bff_headers


def test_stream_emits_steps_then_done(client: TestClient):
    """The user must see progress, not a spinner. Steps arrive before done."""
    with client:
        sid = client.post("/sessions", json={"title": "s"},
                          headers=bff_headers("streamer")).json()["id"]
        h = bff_headers("streamer")
        h["Accept"] = "text/event-stream"
        with client.stream("POST", f"/sessions/{sid}/ask/stream", json={
            "query": "who gets custody of a 5 year old", "lang": "en",
        }, headers=h) as resp:
            assert resp.status_code == 200
            assert resp.headers["content-type"].startswith("text/event-stream")
            # X-Accel-Buffering is what stops a proxy re-buffering the stream.
            assert resp.headers.get("x-accel-buffering") == "no"
            body = "".join(chunk for chunk in resp.iter_text())

    events = [ln[7:] for ln in body.splitlines() if ln.startswith("event: ")]
    assert "done" in events, body[:400]
    # Steps come before done; that ordering is the whole point of the endpoint.
    assert events.index("done") == len(events) - 1, events


def test_stream_persists_the_same_rows_as_the_json_endpoint(client: TestClient):
    """Streaming must not be a second, different code path for storage."""
    with client:
        h = bff_headers("streamer")
        sid = client.post("/sessions", json={"title": "s"},
                          headers=h).json()["id"]
        hs = dict(h, Accept="text/event-stream")
        with client.stream("POST", f"/sessions/{sid}/ask/stream", json={
            "query": "what is maintenance", "lang": "en"}, headers=hs) as resp:
            body = "".join(resp.iter_text())

        payload = None
        for block in body.split("\n\n"):
            if block.startswith("event: done"):
                payload = json.loads(
                    [l for l in block.splitlines()
                     if l.startswith("data: ")][0][6:])
        assert payload is not None, body[:400]
        assert payload["answer"], payload

        msgs = client.get(f"/sessions/{sid}/messages", headers=h).json()
        assert [m["role"] for m in msgs] == ["user", "assistant"]
        assert msgs[1]["content"] == payload["answer"]
        # The message rows carry the citations, so a reopened chat keeps them.
        assert msgs[1]["citations"] == payload["citations"]
        assert msgs[0]["created_at"], "timestamps are needed by the dashboard"


def test_stream_reports_an_error_instead_of_hanging(client: TestClient, monkeypatch):
    """A crash inside the agent must reach the browser as an error event."""
    with client:
        h = bff_headers("streamer")
        sid = client.post("/sessions", json={"title": "s"},
                          headers=h).json()["id"]
        from app import agent as agent_module

        def boom(*a, **kw):
            raise RuntimeError("planner exploded")

        monkeypatch.setattr(agent_module, "run_agent", boom)
        hs = dict(h, Accept="text/event-stream")
        with client.stream("POST", f"/sessions/{sid}/ask/stream", json={
            "query": "custody", "lang": "en"}, headers=hs) as resp:
            body = "".join(resp.iter_text())
    assert "event: error" in body, body[:400]
    assert "planner exploded" in body