"""Fixes from the review of the personal-law routing.

Each test here is one finding. The review found eight, and two of them were
in my own follow-up commit, which is why they are written down.

1. The Special Marriage Act signals were checked after the single-religion
   shortcut, so "Hindu marriage under the Special Marriage Act" was routed to
   the Hindu Marriage Act.
2. A non-Hindu adoption question was routed to the Hindu Adoptions and
   Maintenance Act, which excludes them by statute.
3. Naming the Indian Divorce Act still asked which personal law applies.
4. Latin tokens were matched as substrings, so "parsing" matched "parsi" and
   "Hindustan" matched "hindu".
5. The two-religion check missed Hindi and Kannada synonyms.
6. Standard native-script terms were missing.
7. The planner prompt named a Muslim Inheritance Act that does not exist.
8. A test asserted on a key the agent never returned, so it passed whatever
   the agent did.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent import (  # noqa: E402
    PLAN_SYSTEM,
    _corpus_act_name,
    acts_for_topic,
    detect_personal_law,
)

# --- 1. the Special Marriage Act wins over a single religion ---------------

def test_naming_the_special_marriage_act_is_a_secular_marriage():
    for q in ("Hindu marriage under Special Marriage Act",
              "I am a Christian, can I marry under Special Marriage Act?",
              "I am Hindu, can I marry under Special Marriage Act?",
              "Hindu girl different caste marriage",
              "can we do a court marriage"):
        assert detect_personal_law(q) == "interfaith", q


def test_two_religions_named_is_interfaith():
    assert detect_personal_law("Hindu girl marrying a Muslim boy") == "interfaith"
    assert detect_personal_law("hindu muslim marriage") == "interfaith"
    assert detect_personal_law("हिंदू और कैथोलिक विवाह") == "interfaith"
    assert detect_personal_law("हिंदू और मुसलमान का विवाह") == "interfaith"
    assert detect_personal_law("ಹಿಂದೂ ಮತ್ತು ಕ್ಯಾಥಲಿಕ್ ಮದುವೆ") == "interfaith"


# --- 2. adoption for anyone who is not a Hindu ------------------------------

def test_a_non_hindu_adoption_question_does_not_reach_the_hindu_act():
    """Section 2 of the Hindu Adoptions and Maintenance Act 1956 applies only
    to Hindus. A Muslim, Christian or Parsi adopting is under the secular
    Juvenile Justice Act 2015 (Shabnam Hashmi v. Union of India)."""
    for pl in ("muslim", "christian", "parsi", "interfaith"):
        acts = acts_for_topic("adoption", personal_law=pl)
        assert acts, pl
        assert not any("Hindu Adoptions and Maintenance" in a for a in acts), \
            "%s was routed to the Hindu Act: %s" % (pl, acts)
        assert any("Juvenile Justice" in a for a in acts), \
            "%s was not routed to the secular Act: %s" % (pl, acts)


def test_a_hindu_adoption_question_still_reaches_the_hindu_act():
    acts = acts_for_topic("adoption", personal_law="hindu")
    assert any("Hindu Adoptions and Maintenance" in a for a in acts), acts


# --- 3. naming the Indian Divorce Act --------------------------------------

def test_naming_the_divorce_act_1869_is_a_christian_question():
    for q in ("How do I get a divorce under the Indian Divorce Act?",
              "Divorce Act 1869 grounds",
              "grounds under the Divorce Act, 1869"):
        assert detect_personal_law(q) == "christian", q


# --- 4. Latin tokens are matched on word boundaries -------------------------

def test_a_word_containing_a_religion_name_is_not_a_religion():
    for q in ("help in parsing this divorce decree",
              "as reported in hindustan times, divorce rules",
              "my divorce decree from islamabad"):
        assert detect_personal_law(q) == "", q


# --- 5 and 6. the native script terms ---------------------------------------

def test_the_standard_native_terms_are_recognised():
    cases = [
        ("निकाह के नियम", "muslim"),
        ("मेरा निकाह हुआ था", "muslim"),
        ("तलाक कैसे लूँ", ""),                # the word for divorce, not a marker
        ("दूसरे धर्म में शादी", "interfaith"),
        ("कोर्ट मैरिज", "interfaith"),
        ("ತಲಾಖ್ ನಿಯಮಗಳು", "muslim"),
        ("ಬೇರೆ ಜಾತಿಯಲ್ಲಿ ಮದುವೆ", "interfaith"),
        ("ಅಂತರ್ಜಾತಿ ವಿವಾಹ", "interfaith"),
    ]
    for q, want in cases:
        assert detect_personal_law(q) == want, "%s -> %s" % (q, detect_personal_law(q))


def test_the_ordinary_word_for_divorce_is_not_a_muslim_marker():
    """"तलाक" and "ತಲಾಕ್" are how Hindi and Kannada say divorce. Treating
    them as markers of Muslim law sent every Hindu asking in Hindi down the
    inter-faith route."""
    assert detect_personal_law("मैं हिंदू हूँ, तलाक कैसे लूँ?") == "hindu"
    assert detect_personal_law("मैं ईसाई हूँ, तलाक कैसे लूँ?") == "christian"
    assert detect_personal_law("मैं मुस्लिम हूँ, तलाक कैसे लूँ?") == "muslim"


# --- 7. the planner prompt names no statute that does not exist -------------

def test_the_planner_prompt_names_no_fictional_muslim_inheritance_act():
    """There is no Muslim Inheritance (Succession to Property) Act 1926 in
    India. Naming one is the same mistake as citing a Bill that was never
    passed, and it was in the prompt I wrote."""
    assert "Muslim Inheritance" not in PLAN_SYSTEM
    assert "Uncodified" in PLAN_SYSTEM or "uncodified" in PLAN_SYSTEM


# --- the Act names the corpus actually uses --------------------------------

def test_the_act_names_match_the_corpus():
    """The corpus writes "Divorce Act, 1869". The agent said "Indian Divorce
    Act 1869", which matched nothing, so the Act was never reachable as a
    governing Act and its 106 chunks of Christian divorce law were dead."""
    assert _corpus_act_name("Divorce Act 1869") == "Divorce Act, 1869"
    assert _corpus_act_name("Indian Divorce Act 1869") == ""
    assert _corpus_act_name("Hindu Adoptions and Maintenance Act 1956") == \
        "Hindu Adoptions and Maintenance Act, 1956"
    assert _corpus_act_name(
        "Protection of Women from Domestic Violence Act 2005") == \
        "Protection of Women from Domestic Violence Act, 2005"
