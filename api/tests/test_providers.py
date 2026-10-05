"""The provider chain must not turn one bad key into minutes of waiting.

Persona testing hit a run where Groq was rate-limiting, OpenRouter had run out
of credit, and OpenCode timed out — six model calls per question each walking
all three. These tests pin the behaviour that prevents that.
"""
import json

import pytest

from app import agent as agent_module
from app.agent import (
    GROQ_URL,
    OPENROUTER_URL,
    chat_complete,
    opencode_complete,
    translate_complete,
)


@pytest.fixture(autouse=True)
def clear_cooldowns():
    """No provider is in cooldown before or after a test."""
    agent_module._PROVIDER_FAILURES.clear()
    yield
    agent_module._PROVIDER_FAILURES.clear()


def test_a_failed_provider_is_skipped_on_the_next_call():
    """The second call must go straight past the broken provider."""
    seen = []

    def fake_post(url, headers, payload):
        seen.append(url)
        if "groq" in url:
            raise RuntimeError("429 rate limited")
        return {"choices": [{"message": {"content": "from openrouter"}}]}

    first, provider1 = chat_complete([{"role": "user", "content": "hi"}],
                                     http_post=fake_post)
    assert first == "from openrouter"
    assert provider1.startswith("openrouter:")
    assert seen == [GROQ_URL, OPENROUTER_URL + "/chat/completions"]

    seen.clear()
    second, provider2 = chat_complete([{"role": "user", "content": "again"}],
                                      http_post=fake_post)
    assert second == "from openrouter"
    # Groq is in cooldown, so it is not tried again.
    assert GROQ_URL not in seen, seen
    assert seen == [OPENROUTER_URL + "/chat/completions"]


def test_a_recovered_provider_is_used_again():
    def fake_post(url, headers, payload):
        if "groq" in url:
            return {"choices": [{"message": {"content": "groq back"}}]}
        raise AssertionError("should not reach the fallback")

    # Put groq in cooldown, then let it expire.
    agent_module._mark_failed("groq", RuntimeError("boom"))
    agent_module._PROVIDER_FAILURES["groq"] -= 1000
    text, provider = chat_complete([{"role": "user", "content": "hi"}],
                                   http_post=fake_post)
    assert provider.startswith("groq:")
    assert text == "groq back"


def test_an_empty_completion_opens_the_cooldown():
    """A reasoning model that burns its budget returns empty content. That is
    a failure, and the next call should not pay for it again."""
    calls = {"groq": 0}

    def fake_post(url, headers, payload):
        if "groq" in url:
            calls["groq"] += 1
            return {"choices": [{"message": {"content": "",
                                             "reasoning": "thinking"}}]}
        return {"choices": [{"message": {"content": "recovered"}}]}

    chat_complete([{"role": "user", "content": "1"}], http_post=fake_post)
    chat_complete([{"role": "user", "content": "2"}], http_post=fake_post)
    assert calls["groq"] == 1, "the empty provider was retried"


def test_translation_does_not_retry_a_dead_groq():
    calls = {"groq": 0}

    def fake_post(url, headers, payload):
        if "groq" in url:
            calls["groq"] += 1
            raise RuntimeError("429")
        return {"choices": [{"message": {"content": "अनुवाद"}}]}

    translate_complete([{"role": "user", "content": "translation"}],
                       http_post=fake_post)
    translate_complete([{"role": "user", "content": "translation"}],
                       http_post=fake_post)
    assert calls["groq"] == 1


def test_one_run_cannot_loop_forever_on_the_model():
    """The per-run budget must exist: past it the call fails fast, so the run
    lands on the template answer instead of retrying for minutes."""
    calls = {"n": 0}

    def counting(messages, **kw):
        calls["n"] += 1
        return "an answer", "stub"

    bounded = agent_module.budgeted_llm(counting, max_calls=3)
    for _ in range(3):
        bounded([{"role": "user", "content": "x"}])
    with pytest.raises(RuntimeError):
        bounded([{"role": "user", "content": "x"}])
    assert calls["n"] == 3


def test_the_budget_passes_a_short_token_budget():
    seen = {}

    def llm(messages, max_tokens=None):
        seen["max_tokens"] = max_tokens
        return "ok", "stub"

    agent_module.budgeted_llm(llm)([{"role": "user", "content": "x"}])
    assert seen["max_tokens"] == agent_module.MAX_TOKENS_SHORT


def test_the_budget_tolerates_a_plain_test_double():
    """Most test doubles are `def f(messages)`. Passing max_tokens to one
    raises TypeError and looks exactly like a broken model."""
    def bare(messages):
        return "ok", "stub"

    assert agent_module.budgeted_llm(bare)([{"role": "user", "content": "x"}]) \
        == ("ok", "stub")


def test_max_retries_is_one_by_default():
    """Two retries meant up to eleven model calls per question."""
    assert agent_module.MAX_RETRIES == 1


def test_the_fallback_model_is_not_the_small_one():
    """qwen-2.5-7b produced vague answers with no inline citations."""
    assert "7b" not in agent_module.OPENROUTER_MODEL