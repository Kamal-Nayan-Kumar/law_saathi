"""A generation that runs out of tokens must not be shown as an answer.

Seen in live testing: "…entitled to maintenance [1]. Therefore," followed by an
unrelated heading. The reader cannot tell that is a truncated draft — it looks
like a broken product. The cited passages are always whole sentences, so a
truncated draft falls back to those rather than shipping.
"""
import pytest

from app.agent import (
    compose_answer, new_state, truncated_mid_sentence,
)

TRAILING = ("\n\n### What to do next\n\n- Talk to a family-law lawyer\n\n"
            "*General information only, not legal advice.*")

COMPLETE = ("You can file a maintenance petition in the family court under "
            "Section 20 of the HAMA [1]. The court decides the amount.")

TRUNCATED = ("₹18,000 is 20% of ₹90,000, but there is no automatic 20% rule. "
             "The court decides by exercising discretion and considering your "
             "property, income from any source, and the number of other people "
             "entitled to maintenance [1]. Therefore,")


@pytest.mark.parametrize("body", [
    "The court decides. It considers income, and",
    "You may file a petition. Because",
    "He cannot do this. However",
    "The Act provides. Which means",
    "The Act provides. So that",
    "The court will look at. As",
])
def test_dangling_connectives_are_truncation(body):
    assert truncated_mid_sentence(body)


@pytest.mark.parametrize("body", [
    "You can file a petition under Section 20 [1].",
    "Custody is decided by what is best for your child.",
    "Does the Act apply? Ask the Magistrate.",
    "Here are the three steps you should take:",
    "The court considers the child's age and character [1].",
])
def test_finished_answers_are_not_flagged(body):
    assert not truncated_mid_sentence(body)


def test_a_list_ending_in_a_bullet_is_not_truncation():
    assert not truncated_mid_sentence(
        "Here is what to do.\n\n- Contact the Magistrate\n- Keep a diary")


def test_the_trailing_sections_do_not_decide_the_verdict():
    """The next-steps bullets and the disclaimer are allowed to end abruptly.
    Only the prose before them is judged."""
    assert truncated_mid_sentence(TRUNCATED + TRAILING)
    assert not truncated_mid_sentence(COMPLETE + TRAILING)


def test_empty_and_none():
    assert not truncated_mid_sentence("")
    assert not truncated_mid_sentence(None)


def build():
    state = new_state("q", lang="en")
    state["slots"] = {"topic": "maintenance"}
    state["evidence"] = [{
        "id": "p1", "score": 0.9,
        "payload": {
            "act": "Hindu Adoption and Maintenance Act, 1956",
            "section": "Section 20: Maintenance of children and aged parents",
            "text": "A Hindu is bound to maintain his legitimate children.",
        },
    }]
    state["verified"] = True
    state["confidence"] = 0.9
    return state


def test_a_truncated_draft_is_not_shipped_to_the_reader():
    answer, cites, _ = compose_answer(build(), TRUNCATED)
    assert not answer.rstrip().endswith("Therefore,"), answer
    assert "Therefore," not in answer, answer
    # And the reader still gets law, not silence.
    assert "Section 20" in answer, answer
    assert cites


def test_a_complete_draft_is_shipped_untouched():
    answer, _, _ = compose_answer(build(), COMPLETE + TRAILING)
    assert answer.startswith("You can file a maintenance petition")