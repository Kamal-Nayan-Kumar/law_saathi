"""T3 tests: planner clarification, verifier retry, LLM fallback, trace shape."""
import os

import pytest

from app import agent as agent_module
from app.agent import (
    NODES,
    StubRetriever,
    chat_complete,
    new_state,
    node_planner,
    run_agent,
)


HIT = {"id": "p1", "score": 0.9,
       "payload": {"act": "Hindu Marriage Act, 1955",
                   "section": "Section 13: Divorce",
                   "text": "Any marriage solemnized under this Act may be "
                           "dissolved by a decree of divorce on cruelty."}}


class SeqRetriever:
    """Return scripted result lists per call (verifier-retry seam)."""

    def __init__(self, scripts):
        self.scripts = list(scripts)
        self.calls = []

    def search_text(self, text, top_k=5):
        self.calls.append(text)
        if len(self.calls) <= len(self.scripts):
            return self.scripts[len(self.calls) - 1]
        return self.scripts[-1]


class HitRetriever:
    def search_text(self, text, top_k=5):
        return [dict(HIT)]


def test_planner_asks_followup_on_vague_divorce():
    state = new_state("I want divorce", lang="en")
    state["query_en"] = "I want divorce"
    state["slots"] = agent_module.extract_slots("I want divorce")
    state["intent"] = "divorce"
    out = node_planner(state)
    assert out["missing_slots"], "vague divorce must miss slots"
    assert out["clarification"], "planner must ask instead of guessing"


def test_planner_no_clarification_for_exact_section():
    state = new_state("What is Section 13 Hindu Marriage Act?", lang="en")
    state["query_en"] = "What is Section 13 Hindu Marriage Act?"
    state["slots"] = agent_module.extract_slots(state["query_en"])
    out = node_planner(state)
    assert out["missing_slots"] == []
    assert out["clarification"] == ""


def test_full_run_clarification_path_has_all_five_nodes():
    out = run_agent("I want divorce", lang="en", llm=None,
                    retriever=StubRetriever())
    assert out["clarification"], "vague query must clarify, not guess"
    assert out["trace"] == ["intent", "planner", "response"]
    assert set(NODES) == {"intent", "planner", "tools", "verifier", "response"}
    assert out["answer"], "clarification question must be non-empty"


def test_verifier_retries_on_empty_evidence_then_answers():
    retriever = SeqRetriever([[], [dict(HIT)]])
    out = run_agent("What is the maintenance amount for wife under HAMA section?",
                    lang="en", llm=None, retriever=retriever)
    assert out["retries"] == 1
    assert out["trace"].count("tools") == 2
    assert out["trace"].count("verifier") == 2
    assert out["trace"][0] == "intent" and out["trace"][-1] == "response"
    assert "Hindu Marriage Act" in out["answer"]
    assert out["citations"], "verified answer must cite the act"


def test_verifier_gives_up_after_max_retries():
    out = run_agent("Explain the custody rights of a mother for her minor child",
                    lang="en", llm=None, retriever=StubRetriever())
    assert out["retries"] == agent_module.MAX_RETRIES
    assert out["trace"].count("tools") == 1 + agent_module.MAX_RETRIES
    assert out["answer"], "must still answer (unverified) after retries"


def test_english_pivot_detects_hindi_and_answers_in_hindi_shape():
    out = run_agent("तलाक कैसे मिलता है, पत्नी भरण-पोषण चाहती है", lang="hi",
                    llm=None, retriever=HitRetriever())
    assert out["lang"] == "hi"
    assert out["query_en"], "pivot must keep an EN working query"
    assert out["answer"], "must answer (template) without LLM keys"


def test_detect_lang_roman_hindi():
    assert agent_module.detect_lang(
        "kitna umar hona chahiye shadi ke liye", "en") == "hi"
    assert agent_module.detect_lang(
        "How do I get a mutual-consent divorce?", "en") == "en"
    assert agent_module.detect_lang(
        "What are the talaq rules under Muslim law?", "en") == "en"


def test_extract_slots_roman_hindi_marriage():
    slots = agent_module.extract_slots("kitna umar hona chahiye shadi ke liye")
    assert slots.get("topic") == "marriage"


def test_marriage_age_question_answers_directly():
    # Deterministic fake LLM: Hinglish in, plain English out (like live).
    def fake_llm(msgs):
        return "How old should one be to get married?", "test:fake"

    out = run_agent("kitna umar hona chahiye shadi ke liye", lang="hi",
                    llm=fake_llm, retriever=HitRetriever(),
                    web_search=lambda q: [])
    assert out["lang"] == "hi"
    assert not out["clarification"], "clear marriage question must not ask back"
    assert out["citations"], "direct answer must still cite the acts"
    assert out["trace"][0] == "intent" and out["trace"][-1] == "response"


def test_llm_fallback_switch_on_groq_failure():
    calls = []

    def fake_post(url, headers, payload):
        calls.append(url)
        if "groq" in url:
            raise RuntimeError("429 rate limited")
        return {"choices": [{"message": {"content": "fallback answer"}}]}

    text, provider = chat_complete([{"role": "user", "content": "hi"}],
                                   http_post=fake_post)
    assert text == "fallback answer"
    assert provider.startswith("openrouter:")
    assert any("groq" in u for u in calls)
    assert any("openrouter" in u for u in calls)


def test_llm_primary_groq_no_fallback():
    def fake_post(url, headers, payload):
        assert "groq" in url
        return {"choices": [{"message": {"content": "groq answer"}}]}

    text, provider = chat_complete([{"role": "user", "content": "hi"}],
                                   http_post=fake_post)
    assert provider.startswith("groq:")


def test_ask_endpoint_clarification_path(client):
    from tests.conftest import bff_headers
    h = bff_headers("asker")
    sid = client.post("/sessions", json={"title": "t"}, headers=h).json()["id"]
    resp = client.post("/sessions/%d/ask" % sid,
                       json={"query": "I want divorce", "lang": "en"},
                       headers=h)
    assert resp.status_code == 200
    body = resp.json()
    assert body["clarification"] is True
    assert body["answer"]
    assert body["trace"] == ["intent", "planner", "response"]
    history = client.get("/sessions/%d/messages" % sid, headers=h).json()
    assert [m["role"] for m in history] == ["user", "assistant"]


def test_trace_mode_off_by_default(monkeypatch):
    """Tracing costs money past 5k traces/mo, so it must be opt-in."""
    monkeypatch.delenv("LAWSAATHI_TRACE", raising=False)
    monkeypatch.delenv("LANGCHAIN_TRACING_V2", raising=False)
    assert agent_module.trace_mode() == "off"


@pytest.mark.parametrize("value,expected", [
    ("off", "off"), ("errors", "errors"), ("all", "all"),
    ("ALL", "all"), ("nonsense", "off"),
])
def test_trace_mode_reads_env(monkeypatch, value, expected):
    monkeypatch.setenv("LAWSAATHI_TRACE", value)
    assert agent_module.trace_mode() == expected


def test_trace_mode_errors_trace_only_bad_runs(monkeypatch):
    monkeypatch.setenv("LAWSAATHI_TRACE", "errors")
    good = {"trace": ["intent", "planner", "tools", "verifier", "response"],
            "verified": True, "evidence": [dict(HIT)], "confidence": 0.9,
            "provider": "groq:x", "answer": "ok", "clarification": ""}
    bad = dict(good, verified=False, evidence=[], confidence=0.0)
    assert agent_module.should_trace(good) is False
    assert agent_module.should_trace(bad) is True


def test_trace_mode_all_traces_everything(monkeypatch):
    monkeypatch.setenv("LAWSAATHI_TRACE", "all")
    good = {"trace": ["intent", "response"], "verified": True,
            "evidence": [dict(HIT)], "confidence": 0.9}
    assert agent_module.should_trace(good) is True


@pytest.mark.parametrize("table_name", [
    "DISCLAIMER", "LOW_CONFIDENCE_DISCLAIMER", "NEXT_STEPS", "OOS_REDIRECT",
])
def test_user_facing_strings_are_pure_script(table_name):
    """Hindi/Kannada copy must not mix Latin letters into the Devanagari or
    Kannada script. A hand-typed string once shipped as
    'ವಕೀlru' — invisible unless something checks the script."""
    import re
    table = getattr(agent_module, table_name)
    for lang in ("hi", "kn"):
        text = table[lang]
        assert not re.search(r"[A-Za-z]", text), (
            "%s[%r] mixes Latin into native script: %r"
            % (table_name, lang, text))
        assert text.strip()


@pytest.mark.skipif(not os.environ.get("GROQ_API_KEY", ""),
                    reason="no GROQ_API_KEY — live trace needs keys")
def test_live_trace_smoke():
    out = run_agent("What is Section 13 Hindu Marriage Act divorce?",
                    lang="en")
    assert out["trace"][0] == "intent"
    assert out["trace"][-1] == "response"
    assert out["provider"].startswith("openrouter:")
