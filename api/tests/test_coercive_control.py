"""Someone describing coercion must be answered, not asked to clarify.

Domestic violence s.3(a) covers "fear, harassment or injury". People describe
confinement, being watched and not being allowed to leave without ever using
the name of the Act — and before this, each of these questions detected no topic
at all, retrieved nothing, and returned an answer that named nothing. For a
person who is frightened and asking what she can do, silence is the worst
possible reply.

These are the phrasings, not the statute's.
"""
import pytest

from app.agent import extract_slots, run_agent


@pytest.mark.parametrize("query", [
    "can he be removed from our shared house? i am not safe there",
    "i am not safe in my own house",
    "he does not let me leave the house",
    "he won't let me leave",
    "i am scared to go home",
    "he locks the door on me",
    "he waits for me to leave the house",
    "he follows me everywhere",
    "he takes my phone",
    "he threatens to hurt me if I refuse",
])
def test_coercion_without_the_word_violence_is_still_domestic_violence(query):
    slots = extract_slots(query)
    assert slots.get("topic") == "domestic_violence", (query, slots)


@pytest.mark.parametrize("query", [
    "i am not safe in my own house",
    "he does not let me leave the house",
    "i am scared to go home",
])
def test_those_questions_actually_retrieve_the_act(query):
    """A topic with no evidence is still an empty answer. This is the bug that
    mattered: not misrouting, but returning nothing at all."""
    state = run_agent(query, lang="en", memory={}, llm=None)
    assert state.get("evidence"), query


def test_the_answer_cites_the_dv_act():
    state = run_agent("he locks the door on me and i cannot leave",
                      lang="en", memory={}, llm=None)
    text = " ".join(state.get("citations") or [])
    assert "Domestic Violence" in text, state.get("citations")


def test_fear_in_hindi_and_kannada():
    for query in ("मुझे डर लगता है घर में", "ನನಗೆ ಭಯ ಆಗುತ್ತದೆ ಮನೆಯಲ್ಲಿ"):
        slots = extract_slots(query)
        assert slots.get("topic") == "domestic_violence", (query, slots)


def test_ordinary_fear_questions_are_not_dragged_into_it():
    """These are safety nets against the keyword list swallowing real questions."""
    for query in ("i am scared of the court process",
                  "i am scared my husband will not pay me anything",
                  "my landlord is not returning my deposit"):
        slots = extract_slots(query)
        assert slots.get("topic") != "domestic_violence", (query, slots)