"""T3 tests: planner clarification, verifier retry, LLM fallback, trace shape."""
import os

import pytest

from app import agent as agent_module
from app.agent import (
    NODES,
    StubRetriever,
    chat_complete,
    clarification_question,
    broaden_query,
    extract_slots,
    missing_for,
    new_state,
    node_planner,
    node_tools,
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


def test_broadened_query_does_not_let_one_word_hijack_retrieval():
    """"Who gets custody of the child in a divorce?" retrieved Indian Divorce
    Act sections: the single word "divorce" outweighed "custody" and pulled
    the whole search to divorce acts, never reaching Guardians and Wards."""
    q = "Who gets the custody of the child in a divorce?"
    b = broaden_query(q, 0, "custody")
    # the topic the user actually asked about must be stated first
    assert b.lower().startswith(q.lower()[:20])
    # and the retrieval must be anchored to the right act
    assert "guardians and wards" in b.lower()
    # repeat retrieval must broaden rather than re-weight the same words
    b2 = broaden_query(q, 1, "custody")
    assert "divorce" in b2.lower()


def test_web_search_shows_in_the_trace_with_its_query():
    """The product owner asked to see web_search:"query" in the Thinking
    steps, and to know when the RAG alone was not enough."""
    hits = [{"payload": {"url": "https://example.org/law", "title": "Law page",
                         "text": "some text"}, "score": 0.85}]
    st = new_state("quantum physics entanglement", lang="en")
    st["query_en"] = "quantum physics entanglement"
    st = node_tools(st, retriever=StubRetriever(),
                    web_search=lambda q, top_k=3: hits)
    steps = [d["detail"] for d in st["trace_detail"] if d["node"] == "tools"]
    assert steps, "tools must record a step"
    assert "web_search" in steps[0]
    assert "quantum physics entanglement" in steps[0]
    # web hits must be reachable for citation
    assert st["evidence"] == hits


def test_web_search_failure_is_visible_in_the_trace():
    """A silent web-search failure is indistinguishable from 'no results'."""
    def boom(q, top_k=3):
        raise RuntimeError("firecrawl down")

    st = new_state("obscure topic", lang="en")
    st["query_en"] = "obscure topic"
    st = node_tools(st, retriever=StubRetriever(), web_search=boom)
    steps = [d["detail"] for d in st["trace_detail"] if d["node"] == "tools"]
    assert "web_search" in steps[0]
    assert "unavailable" in steps[0]


def test_act_name_alone_does_not_set_the_topic():
    """"Section 13B of the Hindu Marriage Act" is about DIVORCE, not
    marriage. Matching the act's name against the topic keywords made the
    Quick answer describe marriage law for a divorce question."""
    slots = extract_slots("What is Section 13B of the Hindu Marriage Act?")
    assert slots.get("section") == "13B"
    assert slots.get("topic") != "marriage", slots


@pytest.mark.parametrize("query,expected", [
    ("Section 13B of the Hindu Marriage Act?", "divorce"),
    ("What does Section 7 of the Hindu Marriage Act say?", "marriage"),
    ("my wife wants maintenance", "maintenance"),
    ("who gets custody of my son", "custody"),
])
def test_section_number_wins_over_act_name(query, expected):
    assert extract_slots(query).get("topic") == expected


def test_missing_for_never_reasks_on_a_followup():
    """A follow-up must never come back with the same clarification.

    Regression: `is_followup` was checked *after* the topic test, so a
    follow-up whose topic failed extraction returned ["topic"] forever and
    the bot asked the same question over and over instead of answering.
    """
    # Follow-up that carries no topic of its own — the old code said "topic".
    assert missing_for({}, "mutual consent", is_followup=True) == []
    # Follow-up for a divorce thread that still lacks divorce_type.
    assert missing_for({"topic": "divorce"}, "mutual", is_followup=True) == []
    # A genuinely vague FIRST question must still be clarified.
    assert missing_for({}, "I want divorce", is_followup=False) == ["topic"]


def test_planner_does_not_repeat_a_slot_it_already_asked(client_stub=None):
    """Once a slot has been asked, the planner must not ask it again."""
    hist = [{"role": "user", "content": "I want divorce"},
            {"role": "assistant", "content": "Mutual or contested?"}]
    st = new_state("", lang="en", history=hist)
    st = node_planner(st)
    assert st["missing_slots"] == []
    assert st["clarification"] == ""


def test_clarify_question_is_not_broken_grammar():
    """Non-Latin scripts have no letter case, so lowercasing the first
    character corrupts Hindi/Kannada. Regression: the lead-in plus a
    lowercased template produced 'यह ... तलाक क्या है?'."""
    for lang in ("hi", "kn"):
        q = clarification_question(["divorce_type"], lang)
        assert q.rstrip().endswith("?"), (lang, q)
        # The template's own sentence must survive intact after the lead-in.
        template = agent_module.CLARIFY_TEMPLATES[lang]["divorce_type"]
        assert q.endswith(template), (lang, q)
        # must not end with the mangled '...क्या है?' pattern
        assert not q.rstrip().endswith("क्या है?"), (lang, q)
        assert not q.rstrip().endswith("ಏನು?"), (lang, q)


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
