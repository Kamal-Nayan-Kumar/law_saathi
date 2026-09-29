"""Tests for the agentic layer: model-driven planning, tool choice, judging.

These exist to falsify the claim that the system is agentic. Each one asserts a
decision the *model* made, and asserts that removing the model changes the
outcome — otherwise the old keyword pipeline would pass them too.
"""
import json

import pytest

from app import agent as agent_module
from app.agent import (
    ACT_SEARCH,
    NODES,
    SECTION_READ,
    TOOLS,
    WEB_SEARCH,
    acts_for_topic,
    build_graph,
    compose_answer,
    new_state,
    normalise_plan,
    node_planner,
    node_tools,
    node_verifier,
    parse_json_block,
    plan_search,
    run_agent,
    verify_grounding,
)

GW = {"act": "Guardians and Wards Act, 1890", "section": "Section 7: Guardians",
      "text": "The Court may appoint a guardian of the person of a minor."}
HMA = {"act": "Hindu Marriage Act, 1955", "section": "Section 13: Divorce",
       "text": "Any marriage solemnized under this Act may be dissolved by a "
               "decree of divorce."}


def hit(payload, score=0.9):
    return {"id": "p1", "score": score, "payload": dict(payload)}


class EchoRetriever:
    """Returns a fixed set and records every query it was asked."""

    def __init__(self, hits):
        self.hits = hits
        self.queries = []

    def search_text(self, text, top_k=5, filter_payload=None):
        self.queries.append(text)
        return [dict(h) for h in self.hits]


class ScriptedLLM:
    """Answers by matching the system prompt; records every call made."""

    def __init__(self, plan=None, verdict=None, draft=None):
        self.plan = plan
        self.verdict = verdict
        self.draft = draft
        self.calls = []
        self._verdict_queue = verdict if isinstance(verdict, list) else None
        self._verdict_at = 0

    def __call__(self, messages):
        system = messages[0]["content"]
        self.calls.append(system)
        if system.startswith("You are the planner"):
            return (self.plan if self.plan is not None else "{}"), "test:plan"
        if system.startswith("You are the verifier"):
            if self._verdict_queue is not None:
                queue = self._verdict_queue
                reply = (queue[self._verdict_at]
                         if self._verdict_at < len(queue) else None)
                self._verdict_at += 1
            else:
                reply = self.verdict
            return (reply if reply is not None
                    else '{"verdict": "grounded", "reason": "ok"}'), "test:verify"
        if "You are LawSaathi" in system:
            return (self.draft or ("This is a plain English explanation of what "
                                   "the section means for you, written for a "
                                   "layperson with no legal training.")), "test:write"
        return "", "test:none"

    def saw(self, prefix):
        return any(c.startswith(prefix) for c in self.calls)


def plan_json(act, steps, **extra):
    out = {"governing_act": act, "reasoning": "because", "steps": steps}
    out.update(extra)
    return json.dumps(out)


# --------------------------------------------------------------------------
# 1. The model is asked to plan
# --------------------------------------------------------------------------

def test_planner_asks_the_model_not_just_a_keyword_table():
    llm = ScriptedLLM(plan=plan_json(
        "Hindu Marriage Act 1955",
        [{"tool": ACT_SEARCH, "query": "maintenance amount for a wife"}]))
    state = new_state("maintenance for wife under HAMA", lang="en")
    state["query_en"] = "maintenance for wife under HAMA"
    state["slots"] = agent_module.extract_slots(state["query_en"])
    out = node_planner(state, llm=llm)
    assert llm.saw("You are the planner"), "planner must consult the model"
    assert out["plan"]["source"] == "model"


def test_plan_from_the_model_replaces_the_keyword_table():
    """The model's Act choice must be what gets searched."""
    act = "Guardians and Wards Act 1890"
    llm = ScriptedLLM(plan=plan_json(
        act, [{"tool": ACT_SEARCH, "query": "guardianship of a minor",
               "why": "custody sits here"}]))
    ret = EchoRetriever([hit(HMA), hit(GW)])
    out = run_agent("Who gets custody of the child in a divorce?", lang="en",
                    llm=llm, retriever=ret, web_search=lambda q, **k: [])
    assert act in ret.queries[0], (
        "search must name the Act the planner chose; got %r" % ret.queries[0])
    # And the choice has to change the ranking, not just the query string.
    assert out["citations"][0].startswith("Guardians and Wards"), (
        "planner's Act must win the ranking; got %r" % out["citations"])


def test_chosen_act_reorders_hits_without_discarding_the_rest():
    """Ranking toward the governing Act, not filtering the others away."""
    ranked = agent_module._rank_toward_act([hit(HMA), hit(GW)], "Guardians and Wards")
    assert ranked[0]["payload"]["act"].startswith("Guardians and Wards")
    assert len(ranked) == 2, "other Acts must still be available"


def test_no_model_falls_back_to_the_fixed_plan_and_says_so():
    state = new_state("maintenance for wife", lang="en")
    state["query_en"] = "maintenance for wife"
    state["slots"] = agent_module.extract_slots(state["query_en"])
    out = node_planner(state, llm=None)
    assert out["plan"]["source"] == "fixed"
    assert "No planner model" in out["trace_detail"][-1]["detail"], (
        "the Thinking panel must admit there was no planner")


# --------------------------------------------------------------------------
# 2. A junk plan must not beat a working fallback
# --------------------------------------------------------------------------

@pytest.mark.parametrize("reply", [
    "I cannot help with that.",                 # no JSON at all
    "```json\n{\"steps\": []}\n```",            # empty plan
    "{\"steps\": [{\"tool\": \"send_email\", \"query\": \"x\"}]}",  # fake tool
    "{\"steps\": [{\"tool\": \"search_acts\"}]}",                   # no query
    "not json at all {",                                       # truncated
])
def test_junk_plan_replies_fall_back(reply):
    state = new_state("maintenance for wife", lang="en")
    state["query_en"] = "maintenance for wife"
    state["slots"] = agent_module.extract_slots(state["query_en"])
    plan = plan_search(state, llm=ScriptedLLM(plan=reply))
    assert plan["source"] == "fixed", "junk plan %r leaked through" % reply


def test_plan_steps_are_capped():
    steps = [{"tool": ACT_SEARCH, "query": "q%d" % i} for i in range(9)]
    out = normalise_plan({"steps": steps}, {})
    assert len(out["steps"]) == agent_module.MAX_PLAN_STEPS


def test_all_three_tools_are_reachable():
    assert set(TOOLS) == {ACT_SEARCH, WEB_SEARCH, SECTION_READ}
    steps = [{"tool": t, "query": "q"} for t in TOOLS]
    assert len(normalise_plan({"steps": steps}, {})["steps"]) == 3


# --------------------------------------------------------------------------
# 3. Parsing has to survive how small models actually talk
# --------------------------------------------------------------------------

@pytest.mark.parametrize("raw,expect", [
    ('{"a": 1}', {"a": 1}),
    ('```json\n{"a": 1}\n```', {"a": 1}),
    ('Here is the plan:\n{"a": 1}', {"a": 1}),
    ('{"a": 1}\nHope that helps!', {"a": 1}),
    ('{"a": {"b": 2}}', {"a": {"b": 2}}),
])
def test_parse_json_block_survives_chatty_models(raw, expect):
    assert parse_json_block(raw) == expect


@pytest.mark.parametrize("raw", ["", None, "no braces here", "{unclosed"])
def test_parse_json_block_gives_up_cleanly(raw):
    assert parse_json_block(raw) is None


# --------------------------------------------------------------------------
# 4. Verification is a model decision, not a threshold
# --------------------------------------------------------------------------

def test_verifier_rejects_evidence_the_threshold_accepted():
    """score 0.9 with text passes the old gate. The judge must still be able to say no."""
    ret = EchoRetriever([hit(HMA)])
    llm = ScriptedLLM(
        plan=plan_json("Hindu Marriage Act 1955",
                       [{"tool": ACT_SEARCH, "query": "maintenance amount for a wife"}]),
        verdict=[json.dumps({"verdict": "insufficient",
                             "reason": "the draft cites a section that is "
                                       "not in the passages",
                             "next_queries": ["grounds for a decree of divorce"]}),
                 json.dumps({"verdict": "grounded", "reason": "now it does"})])
    out = run_agent("maintenance for wife under HAMA", lang="en", llm=llm,
                    retriever=ret, web_search=lambda q, **k: [])
    assert llm.saw("You are the verifier"), "the draft must be judged"
    assert out["retries"] == 1, "a rejected draft must trigger a retry"
    assert out["verified"] is True, "the second pass must be able to pass"
    assert out["trace"].count("tools") == 2


def test_the_judges_own_queries_drive_the_retry():
    """Not the hardcoded ladder — the queries the judge asked for."""
    ret = EchoRetriever([hit(HMA)])
    llm = ScriptedLLM(
        plan=plan_json("Hindu Marriage Act 1955",
                       [{"tool": ACT_SEARCH, "query": "maintenance amount for a wife"}]),
        verdict=json.dumps({"verdict": "insufficient",
                            "reason": "wrong section",
                            "next_queries": ["desertion as a ground for divorce"]}))
    run_agent("maintenance for wife under HAMA", lang="en", llm=llm, retriever=ret,
              web_search=lambda q, **k: [])
    assert ret.queries[1].startswith("desertion as a ground for divorce"), (
        "retry must use the judge's query; got %r" % ret.queries[1:])


def test_a_judge_that_cannot_be_parsed_is_ignored_not_fatal():
    state = new_state("q", lang="en")
    state["evidence"] = [hit(HMA)]
    state["draft"] = "A draft long enough to judge properly here."
    assert verify_grounding(state, llm=ScriptedLLM(verdict="I think so?")) is None


def test_verifier_never_asks_the_judge_when_there_are_no_passages():
    """The hard floor holds even with a model available."""
    state = new_state("q", lang="en")
    state["evidence"] = []
    state["draft"] = "Some draft."
    llm = ScriptedLLM()
    assert verify_grounding(state, llm=llm) is None
    assert not llm.calls, "no passages means no judging to do"


def test_an_answer_the_judge_rejected_is_labelled_as_such():
    """A rejected draft must never reach the user as a confident answer."""
    state = new_state("q", lang="en")
    state["evidence"] = [hit(HMA)]
    state["confidence"] = 0.95
    state["verified"] = False
    state["slots"] = {"topic": "divorce"}
    answer, _, _ = compose_answer(state, written="Here is the explanation.")
    assert "could not fully verify" in answer.lower(), (
        "an unverified answer must say so: %r" % answer[-300:])


def test_a_verified_answer_carries_no_doubt_banner():
    state = new_state("q", lang="en")
    state["evidence"] = [hit(HMA)]
    state["confidence"] = 0.95
    state["verified"] = True
    state["slots"] = {"topic": "divorce"}
    answer, _, _ = compose_answer(state, written="Here is the explanation.")
    assert "could not fully verify" not in answer.lower()


# --------------------------------------------------------------------------
# 5. The loop terminates — regression for a bug that shipped in this change
# --------------------------------------------------------------------------

def test_the_retry_loop_always_clears_its_own_flag():
    """needs_retry must be set on every path, or the graph loops forever."""
    llm = ScriptedLLM(verdict=json.dumps(
        {"verdict": "grounded", "reason": "fine"}))
    state = new_state("q", lang="en")
    state["evidence"] = [hit(HMA)]
    state["draft"] = "A perfectly ordinary draft of the explanation here."
    out = node_verifier(state, llm=llm)
    assert out["needs_retry"] is False, (
        "a grounded verdict must clear needs_retry even on the threshold path")


def test_the_threshold_path_also_clears_the_retry_flag():
    """Same, with no judge at all — this was the exact infinite-loop bug."""
    state = new_state("q", lang="en")
    state["evidence"] = [hit(HMA)]
    state["draft"] = "A draft."
    state["needs_retry"] = True          # as left by a previous round
    state["retries"] = 1
    out = node_verifier(state, llm=None)
    assert out["verified"] is True
    assert out["needs_retry"] is False


def test_a_run_with_good_evidence_finishes_in_one_pass():
    ret = EchoRetriever([hit(HMA)])
    llm = ScriptedLLM(plan=plan_json("Hindu Marriage Act 1955",
                                     [{"tool": ACT_SEARCH, "query": "maintenance amount for a wife"}]))
    out = run_agent("maintenance for wife under HAMA", lang="en", llm=llm,
                    retriever=ret, web_search=lambda q, **k: [])
    assert out["retries"] == 0
    assert out["trace"].count("tools") == 1


# --------------------------------------------------------------------------
# 6. Shape of the graph itself
# --------------------------------------------------------------------------

def test_the_draft_exists_before_it_is_verified():
    """Ordering is the whole point: you cannot judge a draft that does not exist."""
    assert NODES.index("reason") < NODES.index("verifier")
    ret = EchoRetriever([hit(HMA)])
    llm = ScriptedLLM(plan=plan_json("Hindu Marriage Act 1955",
                                     [{"tool": ACT_SEARCH, "query": "maintenance amount for a wife"}]))
    out = run_agent("maintenance for wife under HAMA", lang="en", llm=llm,
                    retriever=ret, web_search=lambda q, **k: [])
    seen_draft = []
    original = agent_module.verify_grounding

    def spy(state, llm=None):
        seen_draft.append(bool(state.get("draft")))
        return original(state, llm=llm)

    agent_module.verify_grounding = spy
    try:
        run_agent("maintenance for wife under HAMA", lang="en", llm=llm,
                  retriever=EchoRetriever([hit(HMA)]),
                  web_search=lambda q, **k: [])
    finally:
        agent_module.verify_grounding = original
    assert seen_draft and all(seen_draft), (
        "the verifier was called with no draft to judge: %r" % seen_draft)


def test_the_happy_path_visits_every_node_in_order():
    ret = EchoRetriever([hit(HMA)])
    llm = ScriptedLLM(plan=plan_json("Hindu Marriage Act 1955",
                                     [{"tool": ACT_SEARCH, "query": "maintenance amount for a wife"}]))
    out = run_agent("maintenance for wife under HAMA", lang="en", llm=llm,
                    retriever=ret, web_search=lambda q, **k: [])
    assert out["trace"] == ["intent", "planner", "tools", "reason",
                            "verifier", "response"]


def test_clarifying_short_circuits_before_any_tool_runs():
    out = run_agent("I want divorce", lang="en", llm=None,
                    retriever=EchoRetriever([]))
    assert out["clarification"]
    assert out["trace"] == ["intent", "planner", "response"]
    assert "tools" not in out["trace"]


# --------------------------------------------------------------------------
# 7. The graph is the runtime, and both paths agree
# --------------------------------------------------------------------------

def test_langgraph_drives_the_run_when_installed():
    assert getattr(build_graph(llm=None), "is_graph", False), (
        "langgraph is in requirements; the graph must be the real path")


def test_graph_and_inline_paths_produce_the_same_trace(monkeypatch):
    """Both runners must stay identical, or one of them is untested."""
    kwargs = dict(lang="en", llm=None, retriever=EchoRetriever([hit(HMA)]),
                  web_search=lambda q, **k: [])
    graphed = run_agent("maintenance for wife under HAMA", **kwargs)
    monkeypatch.setattr(agent_module, "build_graph",
                        lambda **kw: agent_module._NO_GRAPH)
    inlined = run_agent("maintenance for wife under HAMA", **kwargs)
    assert graphed["trace"] == inlined["trace"]
    assert graphed["answer"] == inlined["answer"]


# --------------------------------------------------------------------------
# 8. The plan must be visible to the user, not just to the code
# --------------------------------------------------------------------------

def test_the_thinking_panel_shows_the_models_actual_decision():
    ret = EchoRetriever([hit(HMA)])
    llm = ScriptedLLM(plan=plan_json(
        "Guardians and Wards Act 1890",
        [{"tool": ACT_SEARCH, "query": "guardianship of a minor",
          "why": "custody sits in this Act"}]))
    out = run_agent("Who gets custody of the child in a divorce?", lang="en",
                    llm=llm, retriever=ret, web_search=lambda q, **k: [])
    said = " ".join(d["detail"] for d in out["trace_detail"])
    assert "Guardians and Wards Act 1890" in said, (
        "user cannot see which Act was chosen: %r" % said)
    assert "search_acts" in said


# --------------------------------------------------------------------------
# 9. Topic → Act mapping used by the fallback
# --------------------------------------------------------------------------

def test_each_topic_maps_to_its_own_acts():
    assert acts_for_topic("custody") == ["Guardians and Wards Act 1890"]
    assert acts_for_topic("domestic_violence") == ["Domestic Violence Act 2005"]
    assert acts_for_topic("maintenance") == [
        "Hindu Adoption and Maintenance Act 1956"]
    # Succession carries the Hindu Act first (most users) and the general
    # Indian Succession Act second, for everyone else.
    assert acts_for_topic("succession")[0] == "Hindu Succession Act 1956"
    assert "Indian Succession Act 1925" in acts_for_topic("succession")


def test_interfaith_marriage_maps_to_the_special_marriage_act():
    """The Hindu Marriage Act does not govern a Hindu/Muslim marriage."""
    assert acts_for_topic("interfaith_marriage") == ["Special Marriage Act 1954"]
