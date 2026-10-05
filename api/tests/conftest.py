"""Pytest fixtures: isolated in-memory DB, BFF headers."""
import json
import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["INTERNAL_API_SECRET"] = "test-internal"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app import db as db_module
from app.main import create_app


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    db_module.init_db(engine)
    app = create_app(engine)
    with TestClient(app) as c:
        yield c


def bff_headers(sub="user1"):
    return {
        "x-internal-secret": "test-internal",
        "x-user-id": sub,
        "x-user-email": sub + "@example.com",
    }


# Two canned bare-act passages, enough for the planner, the writer and the
# verifier to all have something real to work with.
CANNED = {
    "maintenance": {
        "act": "Hindu Adoption and Maintenance Act, 1956",
        "section": "Section 18: Maintenance of wife",
        "text": "A Hindu wife is entitled to maintenance from her husband "
                "during her lifetime. The court shall decide the amount of "
                "maintenance having regard to the needs of the wife and the "
                "means of the husband.",
    },
    "custody": {
        "act": "Guardians and Wards Act, 1890",
        "section": "Section 17: Appointment of guardian",
        "text": "In the matter of a minor, the Court shall be guided by what "
                "is conducive to the welfare of the minor, and the wishes of "
                "the minor shall be considered.",
    },
}


@pytest.fixture()
def offline_agent(monkeypatch):
    """Run the agent without the network.

    Without this, an endpoint test silently calls the real model and the real
    vector store: the suite took 13 minutes and its results depended on the
    developer's keys. A stubbed run is both fast and deterministic.
    """
    from app import agent as agent_module

    calls: list = []

    def fake_llm(messages, **kw):
        calls.append(messages)
        system = messages[0]["content"]
        user = messages[-1]["content"]
        if "planner" in system.lower():
            payload = {
                "governing_act": "Hindu Adoption and Maintenance Act, 1956",
                "reasoning": "Maintenance is governed by the HAMA.",
                "steps": [{"tool": "search_acts",
                           "query": "maintenance wife entitlement",
                           "why": "find the entitlement"}],
            }
            return json.dumps(payload), "stub"
        if "verifier" in system.lower():
            return json.dumps({"verdict": "grounded",
                               "reason": "every claim traces to a passage",
                               "next_queries": []}), "stub"
        if "Translate this family-law question" in system or "translator" in system.lower():
            return user, "stub"
        # The plain-language writer.
        return ("A Hindu wife is entitled to maintenance from her husband "
                "under the Hindu Adoption and Maintenance Act, 1956 [1]. The "
                "court decides a reasonable amount from her needs and his "
                "means [1]. You can file a petition in the family court where "
                "you live.\n\n### What to do next\n\n- Gather your marriage "
                "certificate and proof of his income.\n- File the petition in "
                "the family court of your district."), "stub"

    monkeypatch.setattr(agent_module, "chat_complete", fake_llm)
    monkeypatch.setattr(agent_module, "translate_complete", fake_llm)

    class FakeStore:
        def search_text(self, text, top_k=5, filter_payload=None):
            picks = [CANNED["maintenance"]]
            if "custody" in text.lower() or "guardian" in text.lower():
                picks.append(CANNED["custody"])
            return [{"id": "p%d" % i, "score": 0.9, "payload": dict(p)}
                    for i, p in enumerate(picks, 1)][:top_k]

        def search(self, q, top_k=5):
            return self.search_text(str(q), top_k)

    monkeypatch.setattr(agent_module, "default_retriever", lambda: FakeStore())
    return calls
