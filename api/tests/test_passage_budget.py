"""The model must be shown whole passages, not fragments of them.

The corpus is chunked by section, so a chunk is a whole section. Cutting a
passage to 400 characters removed the part the answer was about: the Section
13B chunk puts the one-year separation in sub-section (1) and the six-month
wait in sub-section (2), so the verifier was shown "one year" and then asked
whether the draft's "six months" was in the passages. It was not, in what it
had been shown, so the verifier rejected a correct answer and the user was
told the law could not be confirmed.

These tests are about the budget, not about the law. The law is covered by
api/tests/test_amendment_notices.py.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent import (  # noqa: E402
    PASSAGE_CHAR_BUDGET,
    _evidence_block,
    plain_passage,
)

# The Section 13B chunk as the corpus holds it. The two figures live in
# different sub-sections, which is the whole point.
HMA_13B = """Act: The Hindu Marriage Act, 1955 (Act 25 of 1955) | India | Central | In Force
Section 13B: Divorce by mutual consent

**13B. Divorce by mutual consent.—** ( _1_ ) Subject to the provisions of this Act a petition for dissolution of marriage by a decree of divorce may be presented to the district court by both the parties to a marriage together, whether such marriage was solemnized before or after the commencement of the Marriage Laws (Amendment) Act, 1976 (68 of 1976), on the ground that they have been living separately for a period of one year or more, that they have not been able to live together and that they have mutually agreed that the marriage should be dissolved.

( _2_ ) On the motion of both the parties made not earlier than six months after the date of the presentation of the petition referred to in sub-section ( _1_ ) and not later than eighteen months after the said date, if the petition is not withdrawn in the meantime, the court shall, on being satisfied, after hearing the parties and after making such inquiry as it thinks fit, that a marriage has been solemnized and that the averments in the petition are true, pass a decree of divorce declaring the marriage to be dissolved with effect from the date of the decree."""


def _state(*texts):
    return {
        "evidence": [
            {"id": "p%d" % i, "score": 0.9,
             "payload": {"act": "Hindu Marriage Act, 1955",
                         "section": "Section 13B",
                         "text": t}}
            for i, t in enumerate(texts)
        ]
    }


def test_the_budget_covers_the_longest_chunk_in_the_corpus():
    """The longest chunk in the law_saathi collection is 1652 characters. The
    budget has to be above that, or some passages are still cut and the bug
    comes back for whichever section happens to be long."""
    assert PASSAGE_CHAR_BUDGET >= 1652, PASSAGE_CHAR_BUDGET


def test_a_whole_section_survives_the_budget():
    body = plain_passage(HMA_13B, limit=PASSAGE_CHAR_BUDGET)
    assert "six months" in body, "the cooling-off period was cut away"
    assert "eighteen months" in body
    assert "one year" in body


def test_the_evidence_block_shows_the_verifier_the_whole_section():
    """This is the one that bites. The verifier is asked whether the draft's
    figures are in the passages, so the passages it sees have to contain
    them."""
    block = _evidence_block(_state(HMA_13B))
    assert "six months" in block
    assert "eighteen months" in block
    assert "one year" in block


def test_the_old_budget_would_have_hidden_the_figure():
    """Guards the reason for the change. If this ever stops failing, the
    section text has changed shape and the budget should be looked at again
    rather than assumed."""
    body = plain_passage(HMA_13B, limit=400)
    assert "six months" not in body
    assert "one year" in body
