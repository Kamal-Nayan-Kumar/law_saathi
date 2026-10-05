"""The no-model path must still read like help, not like a database export.

When every provider is rate-limited — which is most of the time on free tiers —
`compose_answer` falls back to a template. That is when a user most needs the
reply to read like a person answering them, and it used to open with the heading
"Quick answer" and a third-person summary of a topic that never mentioned their
situation.
"""
from app.agent import compose_answer, new_state

HIT = {
    "act": "Hindu Adoption and Maintenance Act, 1956",
    "section": "Section 18: Maintenance of wife",
    "text": "A Hindu wife is entitled to maintenance from her husband during "
            "her lifetime.",
}


def build(topic, lang="en"):
    state = new_state("q", lang=lang)
    state["slots"] = {"topic": topic}
    state["evidence"] = [{"id": "p1", "score": 0.9, "payload": dict(HIT)}]
    state["verified"] = True
    state["confidence"] = 0.9
    return state


def test_the_fallback_does_not_open_with_a_heading():
    answer, _, _ = compose_answer(build("maintenance"))
    assert not answer.startswith("#")
    assert not answer.startswith("**")


def test_the_fallback_addresses_the_person():
    """It has to be in the second person. A topic description reads as the law
    talking about itself rather than answering the person who asked."""
    answer, _, _ = compose_answer(build("maintenance"))
    opening = answer.split("\n\n")[0].lower()
    assert " you " in f" {opening} " or "your" in opening, opening


def test_the_fallback_names_the_specific_provision():
    answer, cites, _ = compose_answer(build("maintenance"))
    assert cites, "a fallback with no citation is not verified"
    assert "What the law says" in answer


def test_each_area_gets_its_own_opening():
    """One generic sentence for everything is what made this read as a form."""
    openings = {}
    for topic in ("maintenance", "custody", "divorce", "domestic_violence",
                  "succession", "adoption", "marriage", "general"):
        answer, _, _ = compose_answer(build(topic))
        openings[topic] = answer.split("\n\n")[0]
    assert len(set(openings.values())) == len(openings), openings


def test_the_fallback_is_written_in_the_users_language():
    for lang, script in (("hi", "ऀ-ॿ"), ("kn", "ಀ-೿")):
        answer, _, _ = compose_answer(build("custody", lang))
        assert answer.split("\n\n")[0][:20]
        # The whole reply must be in that language, not just the opening.
        assert any(ch in script for ch in answer), lang


def test_the_disclaimer_survives_the_fallback():
    for lang in ("en", "hi", "kn"):
        answer, _, _ = compose_answer(build("custody", lang))
        assert "consult a lawyer" in answer.lower() or "वकील" in answer \
            or "ವಕೀಲ" in answer, lang


# Guardians and Wards Act s.17, verbatim. The word "welfare" — the whole reason
# this section decides custody — sits about 300 characters in.
S17 = {
    "act": "Guardians and Wards Act, 1890",
    "section": "Section 17",
    "text": (
        "Act: The Guardians and Wards Act, 1890 (Act 08 of 1890) | India | "
        "Central | In Force\n"
        "Chapter II: ## APPOINTMENT AND DECLARATION OF GUARDIANS | Section 17: "
        "Matters to be considered by the Court in appointing guardian.** —( _1_ )"
        " In appointing or declaring\n\n"
        "**17. Matters to be considered by the Court in appointing guardian.** "
        "—( _1_ ) In appointing or declaring the guardian of a minor, the Court "
        "shall, subject to the provisions of this section, be guided by what, "
        "consistently with the law to which the minor is subject, appears in "
        "the circumstances to be for the welfare of the minor.\n\n"
        "( _2_ ) In considering what will be for the welfare of the minor, the "
        "Court shall have regard to the age,"),
}


def test_the_fallback_does_not_cut_the_reasoning_off_the_operative_words():
    """With no model there is no summary, so the quoted text is the answer.

    At 160 characters s.17 stopped mid-sentence at "be guided by what..." and the
    phrase that decides the case — "for the welfare of the minor" — was gone.
    A reader was left with a clause and no point."""
    state = new_state("q", lang="en")
    state["slots"] = {"topic": "custody"}
    state["evidence"] = [{"id": "p1", "score": 0.9, "payload": dict(S17)}]
    state["verified"] = True
    state["confidence"] = 0.9
    answer, _, _ = compose_answer(state)
    assert "welfare of the minor" in answer, answer


def test_the_headings_are_in_the_users_language():
    """A Hindi reply that opened with two Hindi paragraphs, then the English
    words "What the law says", then two more Hindi paragraphs, read as one
    document badly stitched together."""
    english = ("What the law says", "What to do next")
    for lang in ("hi", "kn"):
        answer, _, _ = compose_answer(build("maintenance", lang))
        for heading in english:
            assert heading not in answer, (lang, heading, answer[:200])
        assert answer.count("###") == 2, (lang, answer[:200])

    # English keeps them — that is the point of the mapping, not a leftover.
    answer, _, _ = compose_answer(build("maintenance", "en"))
    for heading in english:
        assert heading in answer, heading


def test_the_quoted_law_stays_in_english():
    """The passages are the bare act. Translating them would put words in the
    reader's mouth that no court said, and the citation beside them is what
    makes them checkable."""
    for lang in ("hi", "kn"):
        answer, cites, _ = compose_answer(build("custody", lang))
        assert cites
        assert "Section" in answer, (lang, answer[:300])


def test_a_model_written_answer_is_untouched():
    """The fallback must not leak into the normal path."""
    state = build("maintenance")
    written = ("You can file a maintenance petition in the family court under "
               "Section 18 of the HAMA [1].\n\n### What to do next\n\n"
               "- Gather your marriage certificate.")
    answer, _, _ = compose_answer(state, written)
    assert answer.startswith("You can file")
    assert "What the law says" not in answer