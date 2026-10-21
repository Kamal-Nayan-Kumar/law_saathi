"""Review fixes on top of the personal-law slot.

Three of these lock down bugs found in review of the first implementation:

1. "love marriage" was in the interfaith trigger list, so a Hindu love
   marriage was routed to the Special Marriage Act. The word says nothing
   about religion; only naming two religions does.
2. A Muslim inheritance question was routed to the Indian Succession Act
   1925. Section 2(1)(a) of that Act excludes anyone subject to the Muslim
   personal law, so that is the "Hindu vs Muslim rules differ - never mix"
   failure CONTEXT.md warns about.
3. The clarification asked two questions at once, and "mutual or contested"
   was being asked before we knew which personal law applied, where it means
   something different.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent import (  # noqa: E402
    acts_for_topic,
    detect_personal_law,
    missing_for,
    personal_law_acts,
)


def test_love_marriage_is_not_by_itself_an_interfaith_signal():
    """A love marriage between two people of one faith is the Hindu Marriage
    Act. Only two religions named makes it interfaith."""
    assert detect_personal_law("I want to do a love marriage with my partner") == ""
    assert detect_personal_law("we want a love marriage, both of us are Hindu") == "hindu"
    # Two religions named is still interfaith, however it is phrased.
    assert detect_personal_law("Hindu girl wants to marry a Muslim boy") == "interfaith"
    assert detect_personal_law("hindu muslim marriage") == "interfaith"


def test_a_muslim_inheritance_question_never_reaches_the_indian_succession_act():
    """Section 2(1)(a) of the Indian Succession Act 1925 excludes persons
    subject to the Muslim personal law, so it must not be the anchor for a
    Muslim succession question."""
    anchor = personal_law_acts("muslim", "succession")
    assert "Indian Succession Act 1925" not in anchor
    assert "Muslim Personal Law (Shariat) Application Act 1937" in anchor

    acts = acts_for_topic("succession", personal_law="muslim")
    assert "Indian Succession Act 1925" not in acts
    assert "Bharatiya Nagarik Suraksha Sanhita 2023" not in acts


def test_christian_and_parsi_inheritance_still_reach_the_indian_succession_act():
    """The Indian Succession Act 1925 does apply to Christians and Parsees."""
    assert "Indian Succession Act 1925" in acts_for_topic(
        "succession", personal_law="christian")
    assert "Indian Succession Act 1925" in acts_for_topic(
        "succession", personal_law="parsi")


def test_christian_maintenance_reaches_the_secular_route():
    """CrPC 125 / BNSS 144 applies to every woman regardless of religion, so
    a Christian wife asking for maintenance needs the secular route too."""
    acts = acts_for_topic("maintenance", personal_law="christian")
    assert "Bharatiya Nagarik Suraksha Sanhita 2023" in acts
    assert "Indian Divorce Act 1869" in acts


def test_personal_law_is_asked_on_its_own():
    """One question per turn, and the personal law comes first: "mutual or
    contested" is a different question under each personal law."""
    slots = {"topic": "divorce"}
    missing = missing_for(slots, "How do I get a divorce")
    assert missing == ["personal_law"], missing

    # Once the personal law is known, the other slots come back.
    slots = {"topic": "divorce", "personal_law": "hindu"}
    missing = missing_for(slots, "How do I get a divorce")
    assert "personal_law" not in missing
    assert missing, "the remaining slots are still asked"


def test_a_question_that_names_the_personal_law_is_never_asked_about_it():
    slots = {"topic": "divorce", "personal_law": "christian"}
    assert "personal_law" not in missing_for(slots, "I am a Christian, how do I get a divorce")
