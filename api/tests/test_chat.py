from tests.conftest import bff_headers


def test_chat_history_persists_per_user(client):
    h1 = bff_headers("u1")
    h2 = bff_headers("u2")

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
    assert mine.json()["items"] == []


def test_the_history_arrives_a_page_at_a_time(client):
    """The sidebar used to be handed every chat at once.

    A user with a few hundred chats got a wall of them in a narrow column.
    The list is now paginated, newest first, and the page tells the client
    how much is behind it.
    """
    from tests.conftest import bff_headers

    h = bff_headers("paged")
    for i in range(25):
        client.post("/sessions", json={"title": "chat %d" % i}, headers=h)

    first = client.get("/sessions?page=1&per_page=10", headers=h).json()
    assert first["page"] == 1
    assert first["per_page"] == 10
    assert first["total"] == 25
    assert first["has_more"] is True
    assert len(first["items"]) == 10

    second = client.get("/sessions?page=2&per_page=10", headers=h).json()
    assert len(second["items"]) == 10
    assert second["has_more"] is True

    third = client.get("/sessions?page=3&per_page=10", headers=h).json()
    assert len(third["items"]) == 5
    assert third["has_more"] is False

    # No chat appears on two pages, or the list would show the same one twice.
    seen = [s["id"] for page in (first, second, third) for s in page["items"]]
    assert len(seen) == len(set(seen)) == 25

    # Newest first, because that is the order the sidebar shows them in.
    assert seen == sorted(seen, reverse=True)


def test_a_page_cannot_be_asked_for_too_big(client):
    """One request must not be able to pull the whole table into memory."""
    from tests.conftest import bff_headers

    h = bff_headers("greedy")
    for i in range(5):
        client.post("/sessions", json={"title": "chat %d" % i}, headers=h)

    page = client.get("/sessions?page=1&per_page=100000", headers=h).json()
    assert page["per_page"] <= 100


def test_a_bad_page_number_is_clamped_not_an_error(client):
    """A page of zero or minus one is a mistyped URL, not a broken server."""
    from tests.conftest import bff_headers

    h = bff_headers("badpage")
    client.post("/sessions", json={"title": "chat"}, headers=h)

    for asked in ("0", "-5"):
        page = client.get(f"/sessions?page={asked}", headers=h).json()
        assert page["page"] == 1
        assert len(page["items"]) == 1


def test_message_needs_login(client):
    assert client.post("/sessions", json={}).status_code == 401


def test_ask_persists_citations_so_reopened_chat_shows_sources(client, monkeypatch):
    """A reopened session must still show the Sources list, so the citations
    the agent produced have to be stored with the message, not just returned
    once in the ask response."""
    from app import agent as agent_module
    from tests.conftest import bff_headers

    h = bff_headers("asker")
    sid = client.post("/sessions", json={"title": "maintenance"}, headers=h).json()["id"]

    def fake_run_agent(query, **kwargs):
        return {"answer": "Maintenance is payable on separation.",
                "citations": ["HMA — Sec 18"], "citation_sources": ["bare_act"]}

    monkeypatch.setattr(agent_module, "run_agent", fake_run_agent)
    asked = client.post(f"/sessions/{sid}/ask",
                        json={"query": "What is maintenance?", "lang": "en"},
                        headers=h)
    assert asked.status_code == 200

    history = client.get(f"/sessions/{sid}/messages", headers=h).json()
    assistant = history[-1]
    assert assistant["role"] == "assistant"
    assert assistant["citations"] == ["HMA — Sec 18"]
    assert assistant["citation_sources"] == ["bare_act"]
    # the user turn has no sources
    assert history[0]["citations"] == []


def test_asking_twice_stores_two_turns_not_four(client, offline_agent):
    """The double-answer bug, at the layer it was actually caused.

    One question, asked once, must leave exactly one user row and one
    assistant row. The browser used to answer a dropped stream by re-running
    the whole agent over the JSON endpoint, which persisted a second pair — and
    the user read the same reply twice. Nothing in the API should make that
    easy, and the browser fix relies on this staying true.
    """
    from tests.conftest import bff_headers

    h = bff_headers("once")
    sid = client.post("/sessions", json={"title": "s"}, headers=h).json()["id"]
    client.post(f"/sessions/{sid}/ask",
                json={"query": "what is maintenance", "lang": "en"}, headers=h)

    rows = client.get(f"/sessions/{sid}/messages", headers=h).json()
    assert [r["role"] for r in rows] == ["user", "assistant"]
    assert rows[0]["content"] == "what is maintenance"


def test_the_response_reports_the_language_it_wrote_in(client, offline_agent):
    """The client picks a speaking voice from this. Guessing it client-side is
    how a Kannada answer once got read aloud by an English voice."""
    from tests.conftest import bff_headers

    h = bff_headers("langcheck")
    sid = client.post("/sessions", json={"title": "s"}, headers=h).json()["id"]
    # Asked in Kannada, sent with the English default.
    out = client.post(f"/sessions/{sid}/ask",
                      json={"query": "ಮಗುವಿನ ಕಸ್ಟಡಿ ಯಾರಿಗೆ ಸಿಗುತ್ತದೆ",
                            "lang": "en"}, headers=h).json()
    assert out["lang"] == "kn"


def test_one_question_gives_one_answer_even_if_the_stream_is_cut(client, offline_agent):
    """The exact failure from the bug report, asserted end to end.

    The browser's "recovery" for a dropped stream was to ask again over JSON.
    That is what produced two identical answers under one question. This test
    pins the contract that recovery now depends on: asking once writes one pair
    of rows, so reading them back can never surface a duplicate.
    """
    from tests.conftest import bff_headers

    h = bff_headers("dropped")
    hs = dict(h, Accept="text/event-stream")
    sid = client.post("/sessions", json={"title": "s"}, headers=h).json()["id"]

    # The streamed request. Its body is never read here: this simulates the
    # connection dying after the server has already done the work.
    with client.stream("POST", f"/sessions/{sid}/ask/stream",
                       json={"query": "what is maintenance", "lang": "en"},
                       headers=hs):
        pass

    # The browser's recovery: a plain GET, which cannot run the agent again.
    rows = client.get(f"/sessions/{sid}/messages", headers=h).json()
    answers = [r for r in rows if r["role"] == "assistant"]
    assert len(answers) == 1, rows
    assert answers[0]["content"].strip()


def test_messages_without_citations_still_read_back(client):
    """Rows written before the citations columns existed must not break."""
    from tests.conftest import bff_headers

    h = bff_headers("legacy")
    sid = client.post("/sessions", json={"title": "old"}, headers=h).json()["id"]
    assert client.post(f"/sessions/{sid}/messages",
                       json={"role": "assistant", "content": "old answer", "lang": "en"},
                       headers=h).status_code == 201
    msg = client.get(f"/sessions/{sid}/messages", headers=h).json()[0]
    assert msg["citations"] == [] and msg["citation_sources"] == []


def test_init_db_adds_citation_columns_to_an_existing_table():
    """create_all() never adds a column to a table that already exists, so a
    database deployed before this change needs an explicit ALTER."""
    from sqlalchemy import create_engine, inspect, text
    from sqlalchemy.pool import StaticPool

    from app import db as db_module

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE messages (id INTEGER PRIMARY KEY, session_id INTEGER, "
            "role VARCHAR(16), content TEXT, lang VARCHAR(8), created_at DATETIME)"
        ))
        conn.execute(text(
            "INSERT INTO messages (session_id, role, content, lang) "
            "VALUES (1, 'assistant', 'legacy', 'en')"
        ))

    db_module.init_db(engine)
    db_module.init_db(engine)  # idempotent: a second startup must not fail

    cols = {c["name"] for c in inspect(engine).get_columns("messages")}
    assert {"citations", "citation_sources"} <= cols
    with engine.begin() as conn:
        row = conn.execute(text("SELECT content, citations FROM messages")).fetchone()
    assert row[0] == "legacy" and row[1] is None
