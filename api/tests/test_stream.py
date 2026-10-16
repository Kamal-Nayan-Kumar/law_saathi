import json

from fastapi.testclient import TestClient

from app.stream import ANSWER_CHUNK_DELAY, chunk_answer
from tests.conftest import bff_headers


def test_stream_emits_steps_then_answer_then_done(client: TestClient, offline_agent):
    """The order the reader sees: work, then the answer filling in, then done."""
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
    assert "step" in events, body[:400]
    # The answer is revealed before the run is closed, so the card fills while
    # the response is still open rather than snapping shut at the end.
    if "answer" in events:
        assert events.index("answer") < events.index("done")


def test_streamed_answer_is_the_persisted_answer(client: TestClient, offline_agent,
                                                  monkeypatch):
    """What the reader watched arrive must be what the row actually holds.

    The card fills in from the `answer` events and then reconciles against
    `done`. If the two could differ, the user would read one answer and reopen
    the chat to find another.
    """
    # No pacing: these tests assert content, not pacing.
    monkeypatch.setattr("app.stream.ANSWER_CHUNK_DELAY", 0.0)
    with client:
        h = bff_headers("streamer")
        sid = client.post("/sessions", json={"title": "s"},
                          headers=h).json()["id"]
        hs = dict(h, Accept="text/event-stream")
        with client.stream("POST", f"/sessions/{sid}/ask/stream", json={
            "query": "what is maintenance", "lang": "en"}, headers=hs) as resp:
            body = "".join(resp.iter_text())

        streamed, payload = [], None
        for block in body.split("\n\n"):
            if block.startswith("event: answer"):
                streamed.append(json.loads(
                    [l for l in block.splitlines() if l.startswith("data: ")][0][6:])["text"])
            elif block.startswith("event: done"):
                payload = json.loads(
                    [l for l in block.splitlines() if l.startswith("data: ")][0][6:])

    assert payload is not None, body[:400]
    assert streamed, "the answer must arrive in pieces, not as one blob"
    assert "".join(streamed).strip() == payload["answer"].strip()


def test_answer_chunks_rejoin_to_the_original_text():
    """The one rule the chunker must never break.

    The card is filled from the pieces and then reconciled against the final
    answer. A dropped space or a lost paragraph break would show the reader one
    thing and persist another, so the split is asserted to be lossless.
    """
    answer = (
        "A parent who leaves home does not give up the right to see the child.\n"
        "\n"
        "### What you can do\n"
        "- Apply to the court under the guardians and wards act, 1890.\n"
        "- Keep a record of every visit you were able to make.\n"
        "\n"
        "If the other parent is withholding contact, the court treats that as "
        "a serious matter rather than a private disagreement between adults."
    )
    assert "".join(chunk_answer(answer)) == answer


def test_a_short_answer_is_not_stretched_into_chunks():
    """There is nothing to reveal progressively in one line, and pacing it only
    makes it arrive later."""
    short = "Yes. It is 18."
    assert list(chunk_answer(short)) == [short]
    assert list(chunk_answer("")) == []


def test_chunking_never_breaks_bold_across_a_boundary():
    """A chunk that opens `**bold` and closes it in the next chunk renders as
    literal asterisks for the length of the chunk, which is exactly the glitch
    the structural split exists to prevent."""
    answer = ("This is **important** and it needs to be *emphatic* here, with "
              "more than nine words so the chunk boundary falls inside the "
              "marked-up run somewhere along the way.")
    chunks = list(chunk_answer(answer))
    assert "".join(chunks) == answer
    # No chunk leaves a markdown marker dangling open.
    for chunk in chunks:
        assert chunk.count("**") % 2 == 0, chunk
        assert chunk.count("*") % 2 == 0, chunk


def test_pacing_defaults_to_a_visible_but_short_reveal():
    """The delay exists to shape what a human sees; it must stay small enough
    that it never dominates the wait it is decorating."""
    assert 0 < ANSWER_CHUNK_DELAY <= 0.1


def test_stream_persists_the_same_rows_as_the_json_endpoint(client: TestClient, offline_agent):
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