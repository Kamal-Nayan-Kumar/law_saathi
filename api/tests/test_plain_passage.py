"""A quoted passage has to read like a sentence, not like the corpus it came from.

These strings are verbatim from India Code after ingestion. They carry a
provenance header, a chapter banner, markdown residue, a repeated section
heading, and a truncated preview of the paragraph that follows. None of that
is the reader's problem, and all of it was reaching the answer.
"""
from app.agent import clip, plain_passage

# Section 20, in the two shapes the corpus uses: one line with a preview of the
# clause after it, and one without.
WITH_PREVIEW = (
    "Act: The Hindu Adoptions and Maintenance  Act, 1956 (Act 78 of 1956) | "
    "India | Central | In Force\n"
    "Chapter II: ADOPTION | Section 20: Maintenance of children and aged "
    "parents** .―( _1_ )Subject to the provisions of this section a Hindu is "
    "bound, during his or her life time, to maintain his or her legitimate or "
    "illegitimate children\n\n"
    "**20. Maintenance of children and aged parents** .―( _1_ )Subject to the "
    "provisions of this section a Hindu is bound, during his life time, to "
    "maintain his legitimate children.")

WITHOUT_PREVIEW = (
    "Act: The Special Marriage Act, 1954 (Act 43 of 1954) | India | Central | "
    "In Force\n"
    "Section 13B: Divorce by mutual consent\n\n"
    "**13B. Divorce by mutual consent.**―( _1_ ) Subject to the provisions of "
    "this Act a petition for dissolution of marriage may be presented to the "
    "district court by both parties together.")


def clean(text, **kw):
    return plain_passage(text, limit=400, **kw)


def test_the_provenance_header_is_gone():
    for raw in (WITH_PREVIEW, WITHOUT_PREVIEW):
        out = clean(raw)
        assert "Act:" not in out, out
        assert "India" not in out and "Central" not in out, out


def test_the_chapter_banner_is_gone():
    assert "ADOPTION" not in clean(WITH_PREVIEW)
    assert "Chapter" not in clean(WITH_PREVIEW)


def test_markdown_residue_is_gone():
    for raw in (WITH_PREVIEW, WITHOUT_PREVIEW):
        out = clean(raw)
        assert "**" not in out, out
        assert "#" not in out, out
        assert "_1_" not in out, out


def test_the_section_number_does_not_crowd_the_first_clause():
    """The scrape loses the space in "( _1_ )Subject", which reads as one word."""
    assert "(1)Subject" not in clean(WITH_PREVIEW)


def test_the_heading_is_not_repeated():
    """The chunk says its title twice. The citation already shows it once."""
    assert clean(WITH_PREVIEW).count("Maintenance of children and aged parents") <= 1
    assert clean(WITHOUT_PREVIEW).count("Divorce by mutual consent") <= 1


def test_a_preview_is_not_printed_next_to_the_paragraph_it_previews():
    out = clean(WITH_PREVIEW)
    assert out.count("Subject to the provisions of this section") == 1, out


def test_the_clause_actually_survives():
    """Every rule above is a deletion. This is what they must not delete."""
    assert "maintain his legitimate children" in clean(WITH_PREVIEW)
    assert "district court" in clean(WITHOUT_PREVIEW)


def test_a_hyphen_inside_a_title_is_not_mistaken_for_a_separator():
    """"widowed daughter in-law" broke an earlier version that split on any dash.
    The separator is an em dash; an ASCII hyphen is part of the title."""
    out = plain_passage(
        "Act: Hindu Adoptions and Maintenance Act, 1956\n"
        "Chapter II: ADOPTION | Section 19: Maintenance of widowed daughter "
        "in-law .―( _1_ ) A Hindu wife shall be entitled to maintenance after "
        "the death of her husband.", limit=400)
    # The title is dropped whole — hyphen and all — and the clause survives.
    assert "in-law" not in out, out
    assert "entitled to maintenance" in out, out
    assert "―" not in out, out


def test_a_chunk_that_starts_mid_word_is_dropped():
    """The ingester splits some sections mid-word ("...and prope" / "rty").

    Shown to a reader, "rty (1) The Court may direct..." looks like corrupted
    text, which is worse than showing one passage fewer."""
    out = plain_passage("rty (1) The Court may direct that the person shall "
                        "produce him at such place and time.", limit=400)
    assert out == "", out


def test_a_heading_with_no_body_produces_nothing_rather_than_junk():
    assert clean("Act: X\nSection 13B: Divorce by mutual consent") == ""


def test_empty_and_none_input():
    assert plain_passage("") == ""
    assert plain_passage(None) == ""


def test_a_whole_sentence_is_preferred_over_a_mid_clause_cut():
    """A cut that keeps the first sentence whole beats one that keeps more text.

    The reader is a person asking about their situation. "…during her lifetime."
    is a finished thought; "…from her husband during her lifetime. Nothing in
    this" is a longer string that ends mid-rule. Length is not the goal.
    """
    out = plain_passage(
        "Act: X\nSection 18: Maintenance of wife\n\n"
        "**18. Maintenance of wife.**―A Hindu wife is entitled to maintenance "
        "from her husband during her lifetime. Nothing in this section shall "
        "be construed to limit her rights.", limit=90)
    assert out.endswith("her lifetime."), out
    assert len(out) <= 91, out


def test_when_no_sentence_ends_in_budget_the_cut_is_still_not_mid_word():
    """One clause, no full stop anywhere near the limit."""
    text = ("any act, omission or commission or conduct of the respondent "
            "shall constitute domestic violence in case it insults, ridicules, "
            "humiliates or calls the woman names")
    out = clip(text, limit=90)
    assert out.endswith("…"), out
    # Not mid-word, and not a cut so early the passage says nothing.
    assert not out[:-1].endswith(" "), out
    assert out[:-1].split()[-1].isalpha(), out
    assert len(out) >= 45, out


def test_clip_is_a_no_op_when_the_passage_fits():
    text = "A short, whole sentence."
    assert clip(text, limit=160) == text


def test_a_semicolon_inside_a_list_is_not_a_sentence_end():
    """The list in s.3 is the point of the section. Cutting at its first
    semicolon left the reader with one item out of three and no sign that
    anything was left out."""
    text = ("any act, omission or commission or conduct of the respondent shall "
            "constitute domestic violence in case it (a) insults, ridicules, "
            "humiliates or calls the woman names with regard to not having a "
            "child or a male child; or (b) commits any act of destruction or "
            "injury to any property including stridhanam; or (c) takes any "
            "action contrary to law")
    out = clip(text, limit=240)
    assert not out.rstrip("…").endswith(";"), out
    assert out.endswith("…"), out