"""Amendment notices are evidence, not instructions.

Measured on the live system (2026-10-21). The question "What is the cooling-off
period for a mutual consent divorce?" retrieved section 13B, whose text says
"not earlier than six months after the date of the presentation of the
petition", and the draft answered six months. The verifier rejected it twice as
an "invented six-month cooling-off period ... not supported by the passages".

The cause was this corpus, not the writer. The notice said the indexed text was
pre-amendment and told the model not to state that figure. A passage is
retrieved as evidence and judged as a claim, so the instruction was read as a
claim about the law, the statute contradicted it, and a correct answer was
thrown away.

These tests fail if a notice starts addressing the model or the reader again,
or if it goes back to denying the figures that are in force.
"""
import json
import re
from pathlib import Path

import pytest

NOTICES_PATH = Path(__file__).resolve().parents[2] / "corpus" / "amendments.jsonl"

EXPECTED_ROW_KEYS = {
    "title", "section", "lang", "chunk_id", "source_url", "text", "kind",
}

# Chunk ids are point ids. Changing one re-ingests a duplicate point, so the
# old stale notice stays in the collection beside the new one.
EXPECTED_CHUNK_IDS = ["amend-sma-2018-s28", "amend-sma-2018-s13b"]


def _notices():
    with open(NOTICES_PATH, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _texts():
    return [n["row"]["text"] for n in _notices()]


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if s.strip()]


# Phrases that only make sense as an instruction to a model or a reader. They
# are not legal propositions, so their presence means the passage is talking to
# the system instead of stating the law.
FORBIDDEN_PATTERNS = [
    ("second-person address", r"\b(you|your|yours|yourself)\b"),
    ("names the reader or the model",
     r"\b(the reader|the user|the model|anyone asking)\b"),
    ("'do not'", r"\bdo not\b|\bdon't\b"),
    ("'never'", r"\bnever\b"),
    ("'always tell'", r"\balways tell\b"),
    ("'tell them'", r"\btell (them|him|her|the reader|the user)\b"),
    ("'in the answer'", r"\bin the answer\b"),
    ("'must be checked'", r"\bmust be checked\b"),
    ("'be careful'", r"\bbe careful\b"),
    ("'check the'", r"\bcheck (the|this|it|that)\b"),
    ("'read before'", r"\bread before\b"),
    ("'confirm with'", r"\bconfirm (with|the)\b"),
    ("'should say/name/state'",
     r"\bshould (say|state|name|mention|cite|tell)\b"),
    ("'remember to'", r"\bremember to\b"),
    ("'make sure'", r"\bmake sure\b"),
]

IMPERATIVE_OPENERS = {
    "do", "don't", "never", "always", "tell", "name", "state", "say",
    "mention", "cite", "check", "confirm", "verify", "remember", "note",
    "ensure", "use", "avoid", "read", "be", "consider", "refer", "quote",
    "add", "include", "write", "explain", "answer",
}


def test_jsonl_shape_is_unchanged():
    rows = _notices()
    assert len(rows) == 2, rows
    assert [r["row"]["chunk_id"] for r in rows] == EXPECTED_CHUNK_IDS
    for obj in rows:
        assert set(obj) == {"act", "row"}, obj.keys()
        assert set(obj["row"]) == EXPECTED_ROW_KEYS, obj["row"].keys()
        assert obj["row"]["kind"] == "amendment_notice"
        assert obj["row"]["lang"] == "en"
        # agent.py finds a notice by this label, not by similarity.
        assert "Amendment notice" in obj["row"]["section"]


@pytest.mark.parametrize("text", _texts(), ids=EXPECTED_CHUNK_IDS)
def test_a_notice_gives_no_instruction(text):
    hits = [label for label, pat in FORBIDDEN_PATTERNS
            if re.search(pat, text, re.IGNORECASE)]
    assert not hits, "instruction language in a passage: %r" % hits


@pytest.mark.parametrize("text", _texts(), ids=EXPECTED_CHUNK_IDS)
def test_no_notice_sentence_opens_with_an_imperative(text):
    bad = [s for s in _sentences(text)
           if s.split()[0].lower().strip(",") in IMPERATIVE_OPENERS]
    assert not bad, "imperative sentence(s): %r" % bad


@pytest.mark.parametrize("text", _texts(), ids=EXPECTED_CHUNK_IDS)
def test_each_notice_names_the_amending_act_and_its_commencement(text):
    assert "Marriage Laws (Amendment) Act, 1976" in text
    assert "Act 68 of 1976" in text
    assert "27 May 1976" in text


@pytest.mark.parametrize("text", _texts(), ids=EXPECTED_CHUNK_IDS)
def test_each_notice_states_the_six_month_period_as_current(text):
    """The exact claim the verifier rejected as invented.

    Six months is in the statute and has been since 1976, so a notice that
    hedges on it, calls the indexed text pre-amendment, or sends the reader
    elsewhere for the figure puts the verifier back in conflict with the
    section it is reading.
    """
    assert "six months" in text
    assert "eighteen months" in text
    for sentence in _sentences(text):
        if "cooling-off" in sentence.lower():
            assert "six months" in sentence.lower(), sentence
    low = text.lower()
    for stale in ("pre-amendment", "out of date", "stale", "amended act"):
        assert stale not in low, "notice still calls the statute text %r" % stale


@pytest.mark.parametrize("text", _texts(), ids=EXPECTED_CHUNK_IDS)
def test_one_year_is_only_the_separation_requirement(text):
    """One year is section 28(1)/13B(1) separation, never the second motion.

    The pre-1976 rule did put the second motion a year after the petition.
    A notice that revives it, or that makes "one year" the waiting period a
    reader has to sit out before the decree, is wrong.
    """
    for sentence in _sentences(text):
        if "one year" in sentence.lower():
            assert "separat" in sentence.lower(), sentence


def test_the_sma_notice_is_about_the_special_marriage_act():
    sma = _texts()[0]
    assert "Special Marriage Act, 1954" in sma
    assert "section 28(2)" in sma
    assert "Hindu Marriage Act" not in sma


def test_the_hma_notice_is_about_the_hindu_marriage_act():
    hma = _texts()[1]
    assert "Hindu Marriage Act, 1955" in hma
    assert "section 13B(2)" in hma
    assert "Special Marriage Act" not in hma


@pytest.mark.parametrize("text", _texts(), ids=EXPECTED_CHUNK_IDS)
def test_no_notice_repeats_the_2018_amendment_claim(text):
    """The claim that started this: it names an Act that does not exist.

    Act 2 of 2019 is the National Council for Teacher Education (Amendment)
    Act, 2019. The Special Marriage (Amendment) Bill, 2018 was a private
    member's bill on section 4 (age of marriage) and was never passed.
    """
    assert "Special Marriage (Amendment) Act, 2018" not in text
    assert "1 June 2019" not in text


def test_the_sma_notice_does_not_cite_section_28a():
    """Section 28A is not on the statute book.

    It existed only in the Marriage Laws (Amendment) Bill, which lapsed in
    2014. Delhi HC, Suman Sankar Bhunia v. Debarati Bhunia Chakraborty
    (27.11.2025): a Family Court relied on "a provision, Section 28A of the
    SMA, that does not exist on the statute book".
    """
    assert "28A" not in _texts()[0]
