"""A Bill is not law, and citing one tells a person a rule exists.

Found in production. The answer to "who gets custody of my child after divorce"
listed "Prohibition of Child Marriage (Amendment) Bill, 2021" as source 5 and
stated that children under five normally go to the mother — attributed to it.
That rule is in neither the Bill nor the Guardians and Wards Act. The model
supplied it, and the citation made it look sourced. Twenty-two chunks of that
Bill are in the corpus, from a non-official dataset.

A person deciding where a child lives should never be shown pending legislation
labelled BARE ACT.
"""
import pytest

from app.agent import is_enacted, run_agent

BILL = "The Prohibition of Child Marriage (Amendment) Bill, 2021"


def test_a_bill_is_not_law():
    assert not is_enacted({"act": BILL})


@pytest.mark.parametrize("title", [
    "The Protection of Women from Domestic Violence Bill, 2021",
    "The Muslim Marriage Bill, 2024",
    "The Indian Succession (Amendment) Bill",
    "The Hindu Marriage (Amendment) Bill, 2021",
    "Draft Uniform Civil Code",
    "The Insolvency and Bankruptcy Code, 2016 (Bill no. 5 of 2015)",
])
def test_proposals_are_not_law(title):
    assert not is_enacted({"act": title})


@pytest.mark.parametrize("title", [
    "Guardians and Wards Act, 1890",
    "Hindu Marriage Act, 1955",
    "Protection of Women from Domestic Violence Act, 2005",
    "Hindu Succession Act, 1956",
    "Hindu Adoption and Maintenance Act, 1956",
    "Indian Divorce Act, 1869",
    "Special Marriage Act, 1954",
    "Indian Succession Act, 1925",
    "Dowry Prohibition Act, 1961",
])
def test_enacted_acts_are_law(title):
    assert is_enacted({"act": title})


def test_an_amendment_notice_stays_citable():
    """We generate these ourselves and they must survive the filter — they are
    how a repealed waiting period gets corrected."""
    assert is_enacted({"act": "", "section": "Amendment notice"})


def test_a_payload_with_no_act_is_not_silently_dropped():
    """Absence of an act name is not evidence of a proposal."""
    assert is_enacted({})
    assert is_enacted({"section": "Section 17"})


def test_a_custody_answer_never_cites_a_bill():
    state = run_agent("who gets custody of my child after divorce",
                      lang="en", memory={}, llm=None)
    cited = " ".join(state.get("citations") or [])
    assert "bill" not in cited.lower(), state.get("citations")
    for payload in state.get("evidence") or []:
        assert is_enacted(payload.get("payload") or {}), payload


def test_the_acts_that_should_appear_still_do():
    """A filter that removes too much is its own failure. Guardians and Wards
    Act s.17 is the section that decides most custody disputes."""
    state = run_agent("who gets custody of my child after divorce",
                      lang="en", memory={}, llm=None)
    cited = " ".join(state.get("citations") or [])
    assert "Guardians and Wards" in cited, state.get("citations")