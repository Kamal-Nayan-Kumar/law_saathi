"""Tests for memory, follow-up resolution, recovery planning, and the
amendment guard.

Each of these was found broken by running the system against realistic
questions, not by reading the code.
"""
import json

import pytest

from app import agent as agent_module
from app.agent import (
    ACT_SEARCH,
    WEB_SEARCH,
    apply_amendment_guard,
    node_intent,
    node_response,
    replan_after_empty,
    run_agent,
    wants_timing_correction,
)


def hit(act, section, text="Some section text that is long enough to use.",
        score=0.9):
    return {"id": "%s-%s" % (act, section), "score": score,
            "payload": {"act": act, "section": section, "text": text}}


NOTICE = hit("Hindu Marriage Act, 1955",
             "Section 13B: Amendment notice — divorce by mutual consent",
             "AMENDMENT NOTICE. Amended by the Special Marriage (Amendment) "
             "Act, 2018 (Act 2 of 2019).")

HMA13B = hit("Hindu Marriage Act, 1955", "Section 13B",
             "They have been living separately for a period of one year.")


class Retriever:
    def __init__(self, hits, with_notice=False):
        self.hits = hits
        self.with_notice = with_notice
        self.queries = []

    def search_text(self, text, top_k=5, filter_payload=None):
        self.queries.append(text)
        return [dict(h) for h in self.hits]

    def find_amendment_notices(self, query=""):
        return [dict(NOTICE)] if self.with_notice else []


class RoutingLLM:
    """Answers by system prompt; records the order calls arrive in."""

    def __init__(self, plan=None, replan=None, context=None,
                 context_then=None):
        self.plan, self.replan = plan, replan
        self.context, self.context_then = context, context_then
        self.systems = []
        self.context_calls = 0

    def __call__(self, messages):
        system = messages[0]["content"]
        self.systems.append(system)
        # Both the first contextualize prompt and the retry prompt count as
        # follow-up resolution attempts.
        if ("You resolve follow-up" in system
                or "previous attempt failed" in system and "Rewrite" in system):
            self.context_calls += 1
            if self.context_calls == 1:
                return self.context, "test:ctx"
            return self.context_then, "test:ctx"
        if "bare Acts did NOT answer" in system:
            return self.replan or '{"steps": []}', "test:replan"
        if system.startswith("You are the planner"):
            return self.plan or '{"steps": []}', "test:plan"
        if system.startswith("You are the verifier"):
            return '{"verdict": "grounded", "reason": "fine"}', "test:v"
        if system.startswith("You are LawSaathi"):
            return ("A plain English explanation of the law for the reader, "
                    "long enough to pass the length check."), "test:w"
        return "", "test:none"

    def reasked(self):
        return [s for s in self.systems if s.startswith("You resolve follow-up")]


# --------------------------------------------------------------------------
# 1. Long-term memory
# --------------------------------------------------------------------------

def test_the_topic_is_remembered_across_sessions():
    """A user who asked about custody yesterday should not be asked again.

    The query names no topic of its own — that is the whole point: without
    memory this is exactly the message that produces "what is this about?".
    """
    q = "and what about my situation?"
    state = agent_module.new_state(q, lang="en")
    state["memory"] = {"last_topic": "custody"}
    state["query_en"] = q
    out = node_intent(state, llm=None)
    assert out["slots"]["topic"] == "custody", (
        "remembered topic was dropped: %r" % out["slots"])


def test_remembering_is_advertised_not_silent():
    state = agent_module.new_state("what about it?", lang="en")
    state["memory"] = {"last_topic": "custody"}
    state["query_en"] = "what about it?"
    out = node_intent(state, llm=None)
    said = " ".join(d["detail"] for d in out["trace_detail"])
    assert "Remembered" in said, "the user should be told we remembered"


def test_a_fresh_topic_overrides_what_was_remembered():
    state = agent_module.new_state("What is adoption?", lang="en")
    state["memory"] = {"last_topic": "custody"}
    state["query_en"] = "What is adoption?"
    out = node_intent(state, llm=None)
    assert out["slots"]["topic"] == "adoption"


def test_memory_records_the_topic_for_next_time():
    state = agent_module.new_state("What is adoption?", lang="en")
    state["memory"] = {}
    state["query_en"] = "What is adoption?"
    out = node_intent(state, llm=None)
    assert out["memory_updates"].get("last_topic") == "adoption"


def test_no_topic_means_nothing_to_remember():
    state = agent_module.new_state("hello", lang="en")
    state["memory"] = {}
    state["query_en"] = "hello"
    out = node_intent(state, llm=None)
    assert "last_topic" not in out["memory_updates"]


# --------------------------------------------------------------------------
# 2. Follow-up resolution
# --------------------------------------------------------------------------

HISTORY = [{"role": "user", "content": "Tell me about mutual consent divorce"},
           {"role": "assistant", "content": "..."},
           {"role": "user", "content": "and if we have lived apart?"}]


def test_an_unchanged_followup_is_asked_about_again():
    """The model echoing the input meant retrieval ran on two words."""
    llm = RoutingLLM(context="and if we have lived apart?",
                     context_then="Under the Hindu Marriage Act 1955, can a "
                                  "couple get a mutual consent divorce after "
                                  "living apart?")
    state = agent_module.new_state("and if we have lived apart?", lang="en",
                                   history=HISTORY)
    out = node_intent(state, llm=llm)
    assert llm.context_calls == 2, "an unchanged reply must be re-asked"
    assert "living apart" in out["query_en"].lower()
    assert "Hindu Marriage Act" in out["query_en"], (
        "query_en never took the rewrite: %r" % out["query_en"])


def test_the_english_path_uses_the_rewritten_query():
    """This was the actual bug: query_en was seeded from the raw query and
    only refreshed on the non-English branch."""
    llm = RoutingLLM(context="Can a couple get mutual consent divorce after "
                             "living apart under the Hindu Marriage Act?")
    state = agent_module.new_state("and after living apart?", lang="en",
                                   history=HISTORY)
    out = node_intent(state, llm=llm)
    assert out["query_en"] != "and after living apart?"


def test_a_genuinely_standalone_message_is_not_re_asked():
    """Not every short message is a broken follow-up."""
    llm = RoutingLLM(context="What is Section 13B of the Hindu Marriage Act?")
    state = agent_module.new_state("What is Section 13B of the Hindu "
                                   "Marriage Act?", lang="en",
                                   history=HISTORY)
    node_intent(state, llm=llm)
    assert llm.context_calls == 1


def test_a_model_that_refuses_both_times_is_not_crashed():
    llm = RoutingLLM(context="and if we have lived apart?",
                     context_then="and if we have lived apart?")
    state = agent_module.new_state("and if we have lived apart?", lang="en",
                                   history=HISTORY)
    out = node_intent(state, llm=llm)
    assert out["query_en"], "must always produce a working query"


def test_a_looped_rewrite_is_rejected():
    llm = RoutingLLM(context="and if we have lived apart?",
                     context_then=("what is mutual consent divorce "
                                   + "mutual consent divorce " * 8))
    state = agent_module.new_state("and if we have lived apart?", lang="en",
                                   history=HISTORY)
    out = node_intent(state, llm=llm)
    assert agent_module.looks_looped(out["query_en"]) is False


# --------------------------------------------------------------------------
# 3. Recovery planning — the web tool actually gets used
# --------------------------------------------------------------------------

def test_the_planner_is_re_asked_once_the_acts_come_up_empty():
    """Firecrawl was paid for and never used, because the first plan did not
    include a web step and re-phrasing the same Act search cannot help."""
    plan = json.dumps({"governing_act": "Hindu Marriage Act 1955",
                       "steps": [{"tool": ACT_SEARCH, "query": "how to register a marriage"}]})
    replan = json.dumps({
        "governing_act": "Hindu Marriage Act 1955",
        "steps": [{"tool": WEB_SEARCH, "query": "procedure to register a marriage in India"},
                  {"tool": ACT_SEARCH, "query": "registration of marriages"}]})
    llm = RoutingLLM(plan=plan, replan=replan)
    ret = Retriever([])  # the Acts have nothing
    out = run_agent("how do I register a marriage with the government?",
                    lang="en", llm=llm, retriever=ret,
                    web_search=lambda q, **k: [])
    said = " ".join(d["detail"] for d in out["trace_detail"])
    assert "re-planning" in said, (
        "the planner should get a second look; trace was %r" % said)
    assert WEB_SEARCH in str([s["tool"] for s in out["plan"]["steps"]])


def test_no_replan_when_the_acts_did_answer():
    plan = json.dumps({"governing_act": "Hindu Marriage Act 1955",
                       "steps": [{"tool": ACT_SEARCH, "query": "grounds for contested divorce"}]})
    llm = RoutingLLM(plan=plan)
    ret = Retriever([HMA13B])
    # Long enough, with a named party, so the planner does not stop to clarify.
    run_agent("What are the grounds for a contested divorce for my wife?",
              lang="en", llm=llm, retriever=ret,
              web_search=lambda q, **k: [])
    assert len([s for s in llm.systems
                if s.startswith("You are the planner")]) == 1, (
        "the planner should not be consulted twice when retrieval worked")


def test_a_replan_that_repeats_the_failed_query_is_refused():
    """Repeating is not recovery."""
    same = json.dumps({"steps": [{"tool": ACT_SEARCH, "query": "q1"}]})
    state = agent_module.new_state("q", lang="en")
    state["plan"] = {"steps": [{"tool": ACT_SEARCH, "query": "q1"}]}
    assert replan_after_empty(state, llm=RoutingLLM(replan=same)) is None


def test_replanning_survives_a_dead_model():
    state = agent_module.new_state("q", lang="en")
    state["plan"] = {"steps": []}
    assert replan_after_empty(state, llm=None) is None


# --------------------------------------------------------------------------
# 4. The amendment guard
# --------------------------------------------------------------------------

@pytest.mark.parametrize("q,expected", [
    ("how long before mutual consent divorce", True),
    ("how long must a couple live apart before filing for divorce", True),
    ("what is Section 13 of the Hindu Marriage Act", False),
    ("who gets custody of the child", False),
])
def test_only_timing_questions_ask_for_the_amendment_notice(q, expected):
    assert wants_timing_correction(q) is expected


def test_a_stale_duration_gets_the_amendment_caveat():
    state = agent_module.new_state("how long before mutual consent divorce",
                                   lang="en")
    state["evidence"] = [HMA13B, NOTICE]
    answer = ("You need to have lived apart for at least one year before you "
              "can file [1].")
    out = apply_amendment_guard(state, answer)
    assert "Act 2 of 2019" in out, "must name the amending Act"
    assert "pre-amendment" in out


def test_no_notice_means_no_caveat():
    state = agent_module.new_state("how long before mutual consent divorce",
                                   lang="en")
    state["evidence"] = [HMA13B]
    answer = "You need to have lived apart for at least one year [1]."
    assert apply_amendment_guard(state, answer) == answer


def test_notice_present_but_no_duration_means_no_caveat():
    """Do not bolt a legal warning onto an answer that states no timeline."""
    state = agent_module.new_state("how long before mutual consent divorce",
                                   lang="en")
    state["evidence"] = [NOTICE]
    answer = "Both spouses must agree and file together [1]."
    assert apply_amendment_guard(state, answer) == answer


def test_the_caveat_is_never_duplicated():
    state = agent_module.new_state("how long before mutual consent divorce",
                                   lang="en")
    state["evidence"] = [HMA13B, NOTICE]
    once = apply_amendment_guard(state, "Live apart for one year [1].")
    twice = apply_amendment_guard(state, once)
    assert once == twice


def test_the_notice_is_fetched_by_act_not_by_relevance():
    """Anchoring every query with an Act name pushes the notice out of the
    top 16, so it has to be fetched deliberately."""
    ret = Retriever([HMA13B], with_notice=True)
    out = run_agent("how long must we live apart for mutual consent divorce?",
                    lang="en", llm=None, retriever=ret,
                    web_search=lambda q, **k: [])
    sections = [str(h["payload"].get("section")) for h in out["evidence"]]
    assert any("Amendment notice" in s for s in sections), (
        "the notice never made it into the evidence: %r" % sections)
    said = " ".join(d["detail"] for d in out["trace_detail"])
    assert "amendment notice" in said.lower()


def test_an_unrelated_question_gets_no_notice():
    ret = Retriever([HMA13B], with_notice=True)
    out = run_agent("what are the grounds for a contested divorce?",
                    lang="en", llm=None, retriever=ret,
                    web_search=lambda q, **k: [])
    sections = [str(h["payload"].get("section")) for h in out["evidence"]]
    assert not any("Amendment notice" in s for s in sections)
