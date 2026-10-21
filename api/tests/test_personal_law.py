"""Tests for personal-law (religion) routing.

Each test names the bug it would catch: a regression that makes a Christian
question answer with the Hindu Marriage Act, that routes an inter-faith
marriage to HMA, that assumes Hindu law for a bare divorce question, or that
drops the new golden entries.
"""
import pytest

from app import agent as agent_module
from app.agent import (
    extract_slots,
    missing_for,
    run_agent,
    detect_personal_law,
)
from eval.golden_qas import GOLDEN_QAS


def _ids():
    return {q["id"] for q in GOLDEN_QAS}


class EchoRetriever:
    def __init__(self, hits):
        self.hits = hits
        self.queries = []
        self.filters = []

    def search_text(self, text, top_k=5, filter_payload=None):
        self.queries.append(text)
        self.filters.append(filter_payload)
        if filter_payload:
            return [dict(h) for h in self.hits
                    if all((h.get("payload") or {}).get(k) == v
                           for k, v in filter_payload.items())]
        return [dict(h) for h in self.hits]


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("text,expected", [
    ("I am a Christian man, how do I get a divorce?", "christian"),
    ("I am a Roman Catholic woman, divorce?", "christian"),
    ("Catholic husband wants divorce", "christian"),
    ("Protestant marriage registration", "christian"),
    ("I am a Muslim woman, how do I get a divorce?", "muslim"),
    ("nikah and talaq question", "muslim"),
    ("khula from my husband", "muslim"),
    ("I am a Parsi, how do I get a divorce?", "parsi"),
    ("Zoroastrian marriage", "parsi"),
    ("Can a Hindu girl marry a Muslim boy?", "interfaith"),
    ("inter-caste marriage", "interfaith"),
    ("different religion marriage", "interfaith"),
    ("I am a Hindu, divorce?", "hindu"),
])
def test_detection_english(text, expected):
    assert detect_personal_law(text) == expected
    assert extract_slots(text).get("personal_law") == expected


def test_detection_hindi():
    assert detect_personal_law("मैं ईसाई हूँ, तलाक कैसे लूँ?") == "christian"
    assert detect_personal_law("मैं मुस्लिम हूँ, तलाक कैसे लूँ?") == "muslim"
    assert detect_personal_law("मैं हिंदू हूँ, तलाक?") == "hindu"
    assert detect_personal_law("अलग धर्म का विवाह") == "interfaith"
    assert detect_personal_law("पारसी विवाह") == "parsi"
    # slot is stored
    assert extract_slots("मैं ईसाई हूँ, तलाक कैसे लूँ?").get("personal_law") == "christian"


def test_detection_kannada():
    assert detect_personal_law("ನಾನು ಕ್ರಿಶ್ಚಿಯನ್, ವಿಚ್ಛೇದನೆ?") == "christian"
    assert detect_personal_law("ನಾನು ಮುಸ್ಲಿಂ, ವಿಚ್ಛೇದನೆ?") == "muslim"
    assert detect_personal_law("ಹಿಂದೂ ಮುಸ್ಲಿಂ ಮದುವೆ") == "interfaith"
    assert detect_personal_law("ಪಾರ್ಸಿ ವಿವಾಹ") == "parsi"
    assert extract_slots("ನಾನು ಮುಸ್ಲಿಂ, ವಿಚ್ಛೇದನೆ?").get("personal_law") == "muslim"


def test_detection_by_implication():
    # talaq/khula imply Muslim personal law even without the word "Muslim"
    assert detect_personal_law("how do I get a khula?") == "muslim"
    assert detect_personal_law("talaq procedure") == "muslim"


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


def test_christian_divorce_routes_to_divorce_act_not_hma():
    hit = {"id": "p1", "score": 0.9, "payload": {
        "act": "Indian Divorce Act, 1869", "section": "Section 10: Grounds",
        "text": "Grounds for dissolution of marriage."}}
    ret = EchoRetriever([hit])
    out = run_agent("I am a Christian man, how do I get a divorce?",
                    lang="en", llm=None, retriever=ret,
                    web_search=lambda q, **k: [])
    assert out["slots"].get("personal_law") == "christian"
    assert out["plan"]["governing_act"] == "Divorce Act 1869"
    # The Act anchor must reach retrieval, not HMA. The retriever records the
    # queries it was given, so this is a real assertion about the query that
    # was sent, not about a key that never existed.
    queries = " ".join(ret.queries)
    assert "Divorce Act 1869" in queries
    assert "Hindu Marriage Act" not in queries
    # And the governing Act's own sections are fetched by payload filter, so
    # the answer cannot be built out of the Hindu Marriage Act just because
    # those words sit closer to the question.
    assert any(f and f.get("act") == "Divorce Act, 1869" for f in ret.filters), \
        "the governing Act has to be fetched by filter, not just mentioned"
    # No Hindu Marriage Act anywhere in the plan's act anchor.
    assert "Hindu Marriage Act" not in (out["plan"].get("governing_act") or "")
    assert "Hindu Marriage Act" not in " ".join(
        s.get("act", "") for s in out["plan"].get("steps", []))


def test_interreligious_routes_to_special_marriage_act():
    hit = {"id": "p1", "score": 0.9, "payload": {
        "act": "Special Marriage Act, 1954", "section": "Section 4: Conditions",
        "text": "Conditions relating to solemnization."}}
    out = run_agent("Can a Hindu girl marry a Muslim boy?", lang="en", llm=None,
                    retriever=EchoRetriever([hit]),
                    web_search=lambda q, **k: [])
    assert out["slots"].get("personal_law") == "interfaith"
    assert out["plan"]["governing_act"] == "Special Marriage Act 1954"
    assert "Hindu Marriage Act" not in (out["plan"].get("governing_act") or "")


def test_bare_divorce_asks_rather_than_assuming_hindu():
    out = run_agent("How do I get a divorce", lang="en", llm=None,
                    retriever=EchoRetriever([]),
                    web_search=lambda q, **k: [])
    assert out["clarification"], "must ask instead of silently assuming Hindu law"
    assert "personal_law" in (out.get("missing_slots") or [])


# ---------------------------------------------------------------------------
# Golden set
# ---------------------------------------------------------------------------


def test_golden_set_loads_and_new_entries_present():
    assert len(GOLDEN_QAS) >= 22
    ids = _ids()
    for required in (
        "divorce-christian-en",
        "divorce-muslim-en",
        "divorce-muslim-hi",
        "divorce-parsi-en",
        "marriage-interfaith-en",
        "clarify-personal-law-en",
    ):
        assert required in ids, required
    # Christian entry now names a section of the right Act.
    christian = next(q for q in GOLDEN_QAS if q["id"] == "divorce-christian-en")
    assert christian["must_include_any"], "must name a section of the right Act"
    assert "Hindu Marriage Act" in christian["must_not"]


def test_golden_entries_well_formed():
    required_keys = {"id", "lang", "persona", "query", "must_include_any",
                     "must_include_terms", "must_not", "min_confidence", "note"}
    for q in GOLDEN_QAS:
        assert required_keys <= set(q.keys()), q.get("id")
        assert isinstance(q["must_include_any"], list)
        assert isinstance(q["must_include_terms"], list)
        assert isinstance(q["must_not"], list)