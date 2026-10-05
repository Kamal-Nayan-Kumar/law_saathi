"""Memory behaviour: what Saathi must remember between turns and sessions."""
from fastapi.testclient import TestClient

from tests.conftest import bff_headers


def ask(client: TestClient, h, sid, q, lang="en", tone="simple"):
    return client.post(f"/sessions/{sid}/ask",
                       json={"query": q, "lang": lang, "tone": tone},
                       headers=h).json()


def memories(client: TestClient, h, user):
    out = {}
    for m in client.get("/me/memories", headers=h).json()["memories"]:
        out[m["key"]] = m["value"]
    return out


def test_one_english_question_does_not_overwrite_a_saved_hindi_preference(client, offline_agent):
    """The bug: every request wrote the detected language over the saved
    preference, so a single English question silently reset a Hindi user."""
    with client:
        h = bff_headers("hindi_user")
        client.put("/me", json={"preferred_lang": "hi"}, headers=h)
        sid = client.post("/sessions", json={"title": "s"}, headers=h).json()["id"]

        ask(client, h, sid, "what is mutual consent divorce")
        assert client.get("/me", headers=h).json()["preferred_lang"] == "hi", \
            "one English question must not move a saved preference"

        # Two Hindi questions in a row is a real preference, so it should move.
        ask(client, h, sid, "आपसी सहमति से तलाक कैसे होता है", lang="hi")
        ask(client, h, sid, "तलाक के लिए कितना समय लगता है", lang="hi")
        assert client.get("/me", headers=h).json()["preferred_lang"] == "hi"


def test_repeated_language_does_move_the_preference(client, offline_agent):
    with client:
        h = bff_headers("switcher")
        client.put("/me", json={"preferred_lang": "en"}, headers=h)
        sid = client.post("/sessions", json={"title": "s"}, headers=h).json()["id"]
        ask(client, h, sid, "ಮಗುವಿನ ಕಸ್ಟಡಿ ಯಾರಿಗೆ ಸಿಗುತ್ತದೆ", lang="kn")
        ask(client, h, sid, "ವಿಚ್ಛೇದನ ಹೇಗೆ ಪಡೆಯುವುದು", lang="kn")
        assert client.get("/me", headers=h).json()["preferred_lang"] == "kn"


def test_topic_is_remembered_across_sessions(client, offline_agent):
    """Asking 'what about maintenance?' in a new chat must not restart from
    nothing — the topic came from an earlier session."""
    with client:
        h = bff_headers("returner")
        s1 = client.post("/sessions", json={"title": "one"}, headers=h).json()["id"]
        ask(client, h, s1, "my husband has not paid maintenance for four months")
        assert memories(client, h, "returner")["last_topic"] == "maintenance"

        s2 = client.post("/sessions", json={"title": "two"}, headers=h).json()["id"]
        res = ask(client, h, s2, "what can I do about it")
        assert "maintenance" in res["answer"].lower() or res["citations"], res["answer"]


def test_party_side_is_remembered(client, offline_agent):
    """A follow-up must not answer from the other spouse's point of view."""
    with client:
        h = bff_headers("wife")
        sid = client.post("/sessions", json={"title": "s"}, headers=h).json()["id"]
        ask(client, h, sid, "my husband has not paid maintenance for four months")
        assert memories(client, h, "wife")["last_party_role"] == "claimant"


def test_tone_preference_survives_a_default_request(client, offline_agent):
    """`tone` defaults to 'simple' on every request. Writing it unconditionally
    erased the stored preference, so 'remembers your tone' never worked."""
    with client:
        h = bff_headers("toned")
        sid = client.post("/sessions", json={"title": "s"}, headers=h).json()["id"]
        client.put("/me/memories", json=[{"key": "tone", "value": "detailed"}],
                   headers=h)
        ask(client, h, sid, "what is maintenance")  # tone omitted -> "simple"
        assert memories(client, h, "toned")["tone"] == "detailed"


def test_explicit_tone_choice_is_stored(client, offline_agent):
    with client:
        h = bff_headers("toned2")
        sid = client.post("/sessions", json={"title": "s"}, headers=h).json()["id"]
        ask(client, h, sid, "explain maintenance in detail", tone="detailed")
        assert memories(client, h, "toned2")["tone"] == "detailed"


def test_reopened_chat_keeps_the_thinking_log(client, offline_agent):
    """The trace is stored on the message row, so the Thinking panel is still
    there after a reload instead of vanishing."""
    with client:
        h = bff_headers("reopener")
        sid = client.post("/sessions", json={"title": "s"}, headers=h).json()["id"]
        res = ask(client, h, sid, "who gets custody of a child")
        msgs = client.get(f"/sessions/{sid}/messages", headers=h).json()
        answer = [m for m in msgs if m["role"] == "assistant"][0]
        assert answer["trace_detail"], "no stored steps"
        assert answer["trace"] == res["trace"]
        assert answer["verified"] is not None