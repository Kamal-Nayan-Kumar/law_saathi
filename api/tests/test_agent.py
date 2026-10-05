"""T3 tests: planner clarification, verifier retry, LLM fallback, trace shape."""
import os
import re

import pytest

from app import agent as agent_module
"""Tests for the agent."""
import pytest

from app.agent import (
    NODES,
    GROQ_URL,
    OPENROUTER_MODEL,
    OPENROUTER_URL,
    StubRetriever,
    write_plain_answer,
    chat_complete,
    clarification_question,
    compose_answer,
    broaden_query,
    extract_slots,
    missing_for,
    new_state,
    node_planner,
    node_tools,
    opencode_complete,
    looks_looped,
    plain_passage,
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


def test_full_run_clarification_path_has_all_six_nodes():
    out = run_agent("I want divorce", lang="en", llm=None,
                    retriever=StubRetriever())
    assert out["clarification"], "vague query must clarify, not guess"
    assert out["trace"] == ["intent", "planner", "response"]
    assert set(NODES) == {"intent", "planner", "tools", "reason",
                          "verifier", "response"}
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
    """Groq is primary (ADR-0002); when it is down the answer must come from
    OpenRouter without the user seeing an error."""
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
    assert calls[0].startswith(GROQ_URL)


def test_llm_never_returns_empty_answer():
    """A reasoning model that spends its budget on scratchpad returns an empty
    content field. That must fall through to the next provider, not reach the
    user as a blank reply."""
    calls = []

    def fake_post(url, headers, payload):
        calls.append(url)
        if "groq" in url:
            return {"choices": [{"message": {"content": "",
                                             "reasoning": "thinking..."}}]}
        return {"choices": [{"message": {"content": "real answer"}}]}

    text, provider = chat_complete([{"role": "user", "content": "hi"}],
                                   http_post=fake_post)
    assert text == "real answer"
    assert provider.startswith("openrouter:")


def test_llm_max_tokens_leaves_room_for_reasoning():
    """A 7B fallback silently degraded every legal answer; the fallback must be
    a model that can reason over the passages."""
    assert OPENROUTER_MODEL not in ("qwen/qwen-2.5-7b-instruct",)


def test_llm_primary_groq_no_fallback():
    from app import agent as agent_module

    agent_module._PROVIDER_FAILURES.clear()

    def fake_post(url, headers, payload):
        assert "groq" in url
        return {"choices": [{"message": {"content": "groq answer"}}]}

    text, provider = chat_complete([{"role": "user", "content": "hi"}],
                                   http_post=fake_post)
    assert provider.startswith("groq:")


def test_llm_skips_a_provider_already_in_cooldown():
    """After a failure the provider is skipped, so `http_post=None` style tests
    and live calls both avoid paying for the same dead key twice."""
    from app import agent as agent_module

    agent_module._PROVIDER_FAILURES.clear()
    agent_module._mark_failed("groq", RuntimeError("429"))
    try:
        def fake_post(url, headers, payload):
            assert "groq" not in url, "a failed provider was retried"
            return {"choices": [{"message": {"content": "fell through"}}]}

        _text, provider = chat_complete([{"role": "user", "content": "hi"}],
                                        http_post=fake_post)
        assert provider.startswith("openrouter:")
    finally:
        agent_module._PROVIDER_FAILURES.clear()


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


RAW_ACT_TEXT = (
    "Act: The Hindu Marriage Act, 1955 (Act 25 of 1955) | India | Central | "
    "In Force\nSection 13B: Divorce by mutual consent\n\n"
    "**13B. Divorce by mutual consent.—** ( _1_ ) Subject to the provisions of "
    "this Act a petition for dissolution of marriage by a decree of divorce may "
    "be presented to the district court by both the parties to a marriage "
    "together, on the ground that they have been living apart for one year or "
    "more."
)


def test_opencode_is_the_free_last_resort():
    """Groq and OpenRouter can both be down or rate-limited. OpenCode Zen's
    space-bunny-free model costs nothing, so it is the final fallback that
    keeps chat working instead of returning a bare error."""
    from app import agent as agent_module

    agent_module._PROVIDER_FAILURES.clear()
    order = []
    msg = [{"role": "user", "content": "hi"}]

    def dead(url, headers, payload):
        order.append(url)
        raise RuntimeError("503 upstream down")

    with pytest.raises(RuntimeError):
        chat_complete(msg, http_post=dead)
    # Every provider is reachable once (the cooldown is per provider, and this
    # is the first call for each).
    assert len(order) == 3, order
    assert "groq" in order[0]
    assert "openrouter" in order[1]
    assert "opencode" in order[2], order


def test_opencode_completion_returns_text_and_provider():
    captured = {}

    def fake_post(url, headers, payload):
        captured["url"] = url
        captured["model"] = payload["model"]
        captured["auth"] = headers.get("Authorization")
        captured["ua"] = headers.get("User-Agent")
        return {"choices": [{"message": {"content": "hello from bunny"}}]}

    text, provider = opencode_complete([{"role": "user", "content": "hi"}],
                                       http_post=fake_post)
    assert text == "hello from bunny"
    assert provider == "opencode:space-bunny-free"
    assert captured["model"] == "space-bunny-free"
    # Cloudflare rejects the default urllib UA with a 403
    assert captured["ua"], "must send a User-Agent or Zen returns 403"


def test_opencode_reasoning_content_is_not_shown_to_the_user():
    """Zen returns a `reasoning_content` field alongside the answer. It must
    never reach the user, or every reply opens with 'We need to...'."""
    def fake_post(url, headers, payload):
        return {"choices": [{"message": {
            "content": "The real answer.",
            "reasoning_content": "We need answer this carefully. Let me parse."}}]}

    text, _ = opencode_complete([{"role": "user", "content": "hi"}],
                                http_post=fake_post)
    assert text == "The real answer."
    assert "We need" not in text
    assert "Let me parse" not in text


def test_looped_model_output_is_rejected():
    """qwen-2.5-7b loops when pushed into Hindi/Kannada. A user must never
    see the same sentence twenty times, so the run must be detected and the
    template answer used instead."""
    looped = "दर्जन की बारिश " * 60
    assert looks_looped(looped) is True
    normal = ("If you both agree, you can ask the court to end the marriage. "
              "You must have lived apart for a year. A lawyer files it for you.")
    assert looks_looped(normal) is False
    assert looks_looped("") is False


def test_hindi_answer_never_repeats_a_phrase():
    """End-to-end guard: whatever the model returns, the delivered Hindi
    answer must not contain a repeated 4-gram."""
    def loopy_llm(msgs):
        return "दोनों पति और पत्नी " * 30, "test:loop"

    out = run_agent("आपसी सहमति से तलाक कैसे मिलता है?", lang="hi",
                    llm=loopy_llm, retriever=HitRetriever(),
                    web_search=lambda q: [])
    assert not looks_looped(out["answer"]), out["answer"][:200]


def test_plain_answer_is_written_not_pasted_and_stays_grounded():
    """The body of the answer must be written by the model from the
    passages, in the user's language, and must not paste the raw act text."""
    captured = {}

    def fake_llm(msgs):
        captured["system"] = msgs[0]["content"]
        captured["user"] = msgs[1]["content"]
        return ("If both of you agree, you can ask the court to end the "
                "marriage [1]. You need to have lived apart for a year [1]. "
                "A lawyer will file it for you."), "test:fake"

    st = new_state("How do I get a mutual consent divorce?", lang="hi")
    st["evidence"] = [{"score": 0.9, "payload": {
        "act": "Hindu Marriage Act, 1955", "section": "Section 13B",
        "text": RAW_ACT_TEXT}}]
    st["slots"] = {"topic": "divorce"}
    out = write_plain_answer(st, fake_llm)
    assert "petition for dissolution" not in out, "must not paste the act text"
    # prompt must instruct plain language, grounding, and English-first writing
    assert "Write in English" in captured["system"]
    assert "everyday words" in captured["system"]
    assert "Never add a section" in captured["system"]
    # passages must be handed over, numbered, and cleaned
    assert "[1]" in captured["user"]
    assert "Act: The Hindu Marriage Act" not in captured["user"]


def test_plain_answer_falls_back_to_template_when_model_fails():
    def boom(msgs):
        raise RuntimeError("model down")

    st = new_state("q", lang="en")
    st["evidence"] = [{"score": 0.9, "payload": {"act": "A", "section": "1",
                                                "text": RAW_ACT_TEXT}}]
    assert write_plain_answer(st, boom) == ""
    # compose_answer must still produce a usable answer with no model output
    answer, cites, _ = compose_answer(st, "")
    assert cites and "What to do next" in answer
    assert "Act: The Hindu Marriage Act" not in answer


def test_plain_passage_drops_scraper_metadata_and_markup():
    """The stored chunks carry an ingestion header and markdown noise. Both
    were being shown to the user verbatim, which is what made every answer
    look like a database dump rather than advice."""
    out = plain_passage(RAW_ACT_TEXT)
    assert "Act:" not in out
    assert "| India |" not in out
    assert "In Force" not in out
    assert "**" not in out
    assert "_1_" not in out
    # the title is stated twice in the chunk; both copies must go, since the
    # Sources list already shows the act and section name
    assert "divorce by mutual consent" not in out.lower(), out
    # the operative law must survive
    assert "petition for dissolution of marriage" in out


def test_plain_passage_never_ends_mid_sentence():
    """A hard 160-char cut produced '... they have been living as…'."""
    for limit in (60, 90, 120, 160):
        out = plain_passage(RAW_ACT_TEXT, limit=limit)
        assert out.endswith("…") or out.endswith((".", "!", "?")), out
        if out.endswith("…"):
            # must end on a whole word, not a fragment of one
            assert not re.search(r"\b\w*…$", out[:-1].rstrip()), out


def test_written_answer_replaces_the_template_body():
    """When the model writes an explanation, that becomes the body — no
    rigid 'Quick answer / What the law says' scaffolding, and no raw act
    text pasted underneath it."""
    state = new_state("How do I get a mutual consent divorce?", lang="en")
    state["evidence"] = [{"score": 0.9, "payload": {
        "act": "Hindu Marriage Act, 1955", "section": "Section 13B",
        "text": RAW_ACT_TEXT}}]
    state["verified"] = True
    state["confidence"] = 0.9
    written = "If you both agree, you can ask the court to end the marriage [1]."
    answer, cites, _ = compose_answer(state, written)
    assert answer.startswith(written)
    assert "### What the law says" not in answer
    assert "Act: The Hindu Marriage Act" not in answer
    assert "| India |" not in answer
    assert cites, "the sources list must still be returned"


def test_trace_run_sends_a_summary_for_a_bad_run(monkeypatch):
    """trace_run() must actually reach LangSmith for a run that went wrong.

    Guards the silent-failure trap: a swallowed exception here would mean
    debugging data is never recorded, with no symptom anywhere.
    """
    sent = {}

    class FakeClient:
        def create_run(self, **kwargs):
            sent.update(kwargs)

    fake = type("M", (), {"Client": lambda self=None: FakeClient()})
    monkeypatch.setenv("LAWSAATHI_TRACE", "errors")
    monkeypatch.setenv("LANGCHAIN_API_KEY", "lsv2_fake")
    monkeypatch.setenv("LANGCHAIN_PROJECT", "lawsaathi")
    monkeypatch.setitem(__import__("sys").modules, "langsmith", fake)

    bad = {"answer": "", "verified": False, "confidence": 0.0,
           "query": "q", "query_en": "q", "lang": "en",
           "trace": ["intent", "planner"], "trace_error": True}
    agent_module.trace_run(bad)
    assert sent.get("name") == "lawsaathi:run"
    assert sent.get("project_name") == "lawsaathi"
    assert sent.get("error") == "run raised an exception"
    assert "intent" in sent["outputs"]["trace"]


def test_trace_run_sends_nothing_for_a_good_run(monkeypatch):
    """A healthy run must not cost a trace — that is the whole point of
    the errors-only mode, since the free tier allows only 5k/month."""
    sent = {}

    class FakeClient:
        def create_run(self, **kwargs):
            sent.update(kwargs)

    fake = type("M", (), {"Client": lambda self=None: FakeClient()})
    monkeypatch.setenv("LAWSAATHI_TRACE", "errors")
    monkeypatch.setenv("LANGCHAIN_API_KEY", "lsv2_fake")
    monkeypatch.setitem(__import__("sys").modules, "langsmith", fake)

    good = {"answer": "a", "verified": True, "confidence": 0.9,
            "trace": ["intent"], "evidence": [dict(HIT)]}
    agent_module.trace_run(good)
    assert sent == {}


def test_trace_run_never_breaks_a_users_answer(monkeypatch):
    """Tracing is best-effort: a LangSmith outage must not fail the chat."""
    class Boom:
        def __init__(self, *a, **k):
            raise RuntimeError("langsmith down")

    monkeypatch.setenv("LAWSAATHI_TRACE", "errors")
    monkeypatch.setenv("LANGCHAIN_API_KEY", "lsv2_fake")
    monkeypatch.setitem(__import__("sys").modules, "langsmith",
                        type("M", (), {"Client": Boom}))
    bad = {"answer": "", "verified": False, "confidence": 0.0}
    agent_module.trace_run(bad)  # must not raise


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
    """Smoke test against the real providers and the real vector store.

    Skipped when every provider is unavailable: this checks wiring, not
    correctness, and a developer with a spent free tier should not get a
    failure that looks like a code bug. The behaviour itself is covered by the
    offline tests.
    """
    from app import agent as agent_module

    agent_module._PROVIDER_FAILURES.clear()
    try:
        out = run_agent("What is Section 13 Hindu Marriage Act divorce?",
                        lang="en")
    except RuntimeError as e:
        if "no LLM backend" in str(e):
            pytest.skip("no LLM provider reachable right now")
        raise
    assert out["trace"][0] == "intent"
    assert out["trace"][-1] == "response"
    # Which provider answered depends on which free tier is not rate-limited
    # that minute; Groq is primary and OpenRouter is the fallback. Asserting
    # one specific name made this test fail whenever the other one was up.
    assert any(out["provider"].startswith(p) for p in
               ("groq:", "openrouter:", "opencode:")), out["provider"]
