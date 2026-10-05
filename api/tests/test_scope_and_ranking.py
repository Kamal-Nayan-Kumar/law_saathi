"""Tests for scope decisions and retrieval ranking.

These are the fixes found by testing the live system against real user
questions, not by reading the code. Each one records a question that was
answered wrongly before.
"""
import pytest

from app import agent as agent_module
from app.agent import (
    extract_slots,
    is_oos,
    missing_for,
    run_agent,
)


class EchoRetriever:
    """Returns a fixed set and records every query it was asked."""

    def __init__(self, hits):
        self.hits = hits
        self.queries = []

    def search_text(self, text, top_k=5, filter_payload=None):
        self.queries.append(text)
        return [dict(h) for h in self.hits]


# --------------------------------------------------------------------------
# Land: which land questions are family law, and which are not
# --------------------------------------------------------------------------

def test_land_dispute_between_living_relatives_is_not_family_law():
    """A tenancy/property fight is not ours to answer."""
    assert is_oos("My son and father are fighting over a farmland, "
                  "who wins the land?") is True


def test_land_that_changed_hands_because_someone_died_is_succession():
    """This was being refused as 'property law', which is exactly backwards."""
    q = "My father died and my elder brother is taking all the ancestral land"
    assert is_oos(q) is False


@pytest.mark.parametrize("q,topic", [
    ("My father died and my elder brother is taking all the ancestral land",
     "succession"),
    ("after my mother's death the house went to my uncle", "succession"),
    ("who are the legal heirs to ancestral property", "succession"),
    ("my father passed away, who gets the family land", "succession"),
])
def test_inheriting_is_detected_as_succession(q, topic):
    """People describe the fight, not the doctrine. Detect the death."""
    assert extract_slots(q).get("topic") == topic


def test_a_bare_land_question_stays_out_of_scope():
    for q in ("how do I get a soil test report for my farmland",
              "what is the stamp duty on a property transfer",
              "my tenant has not paid rent for six months"):
        assert is_oos(q) is True, q


def test_a_family_question_is_not_refused_by_a_substring_match():
    """Substring matching made "cannot live with the *pa*rents*" trip the rent
    rule, and an adoption question was refused as tenancy law. Refusing a real
    family-law question is worse than missing an out-of-scope one."""
    assert is_oos("can my aunt adopt a child who cannot live with the parents") is False


def test_a_genuine_tenancy_question_is_still_refused():
    assert is_oos("how do I remove a tenant from my flat") is True


# --------------------------------------------------------------------------
# Naming an Act is a question we can answer
# --------------------------------------------------------------------------

def test_naming_an_act_does_not_trigger_a_pointless_clarification():
    """'What is the Special Marriage Act?' was answered with 'what is this
    about?' — the least useful reply possible."""
    q = "What is the Special Marriage Act?"
    slots = extract_slots(q)
    assert missing_for(slots, q) == []


def test_a_named_act_is_answered_from_its_own_text():
    out = run_agent("What is the Special Marriage Act?", lang="en", llm=None,
                    retriever=EchoRetriever([
                        {"id": "1", "score": 0.9, "payload": {
                            "act": "Special Marriage Act, 1954",
                            "section": "Section 1: Short title",
                            "text": "This Act may be called the Special "
                                    "Marriage Act, 1954."}}]),
                    web_search=lambda q, **k: [])
    assert not out["clarification"], "must not ask what this is about"
    assert "Special Marriage" in out["answer"]


# --------------------------------------------------------------------------
# Out of scope must be answered, not turned into a question
# --------------------------------------------------------------------------

def test_out_of_scope_gives_the_redirect_not_a_clarifying_question():
    out = run_agent("My son and father are fighting over a farmland, "
                    "who wins the land?", lang="en", llm=None,
                    retriever=EchoRetriever([]))
    assert out["oos_redirect"] is True
    assert out["clarification"] == "", (
        "out of scope is a decision, not a missing slot")
    assert "outside my family-law scope" in out["answer"]
    assert out["trace"] == ["intent", "planner", "response"], (
        "no retrieval should happen for an out-of-scope question")


def test_out_of_scope_short_circuits_before_any_tool_runs():
    calls = []

    def ws(q, **k):
        calls.append(q)
        return []

    run_agent("what is the penalty for tax evasion", lang="en", llm=None,
              retriever=EchoRetriever([]), web_search=ws)
    assert not calls, "must not search the web for an out-of-scope question"


# --------------------------------------------------------------------------
# A named section must outrank the Preamble
# --------------------------------------------------------------------------

def _h(label):
    return {"id": label, "score": 0.89, "payload": {
        "act": "Hindu Marriage Act, 1955", "section": label,
        "text": "Body of %s." % label}}


def test_the_named_section_ranks_above_higher_scoring_boilerplate():
    """Live measurement: for 'Section 13B Hindu Marriage Act' the corpus
    returned the Preamble at 0.895 and the real 13B fourth at 0.890. A 0.005
    spread, so the user's own words have to break the tie."""
    hits = [_h("Preamble"), _h("Section 13A"), _h("Section 13B"),
            _h("Section 28"), _h("Full Text")]
    ranked = agent_module._rank_toward_section(hits, "13B")
    assert ranked[0]["payload"]["section"] == "Section 13B"
    assert len(ranked) == len(hits), "ranking must not drop anything"


def test_section_ranking_does_not_confuse_13_with_13b():
    hits = [_h("Section 13"), _h("Section 13B"), _h("Section 13A")]
    assert agent_module._rank_toward_section(hits, "13B")[0]["payload"][
        "section"] == "Section 13B"
    assert agent_module._rank_toward_section(hits, "13")[0]["payload"][
        "section"] == "Section 13"


def test_no_section_named_means_no_section_ranking():
    hits = [_h("Preamble"), _h("Section 13B")]
    assert agent_module._rank_toward_section(hits, "") == hits


def test_asking_for_section_13b_surfaces_section_13b():
    out = run_agent("What is Section 13B Hindu Marriage Act?", lang="en",
                    llm=None,
                    retriever=EchoRetriever([
                        _h("Preamble"), _h("Section 13A"), _h("Section 13B")]),
                    web_search=lambda q, **k: [])
    assert out["citations"], "must still cite something"
    assert any("13B" in c for c in out["citations"]), (
        "Section 13B must be cited; got %r" % out["citations"])
