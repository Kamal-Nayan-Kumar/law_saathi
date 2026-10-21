"""The writer, the verifier and the citations must see the same passages.

The writer writes from the passages it was given and the verifier judges the
draft against the passages it was given. When those two sets were chosen
separately, the verifier was shown five bare-act chunks while the writer had
also read the web results, so the writer's use of a web source looked to the
verifier like an invention. The draft was rejected twice and the user was
told the law could not be confirmed.

The curated notice was worse off: it sat at the end of the evidence list,
past the window both of them were looking at, so a draft that stated the
waiver rule (which is in the notice and nowhere else) was judged
unsupported.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent import (  # noqa: E402
    _evidence_block,
    select_evidence_for_answer,
)


def _hit(act, section, text, url="", kind=""):
    payload = {"act": act, "section": section, "text": text}
    if url:
        payload["url"] = url
        # A web result has no Act. The citation falls back to the title.
        payload["act"] = ""
        payload["title"] = section
    if kind:
        payload["kind"] = kind
    return {"id": section, "score": 0.9, "payload": payload}


NOTICE = _hit(
    "Hindu Marriage Act, 1955",
    "Section 13B: Amendment notice — divorce by mutual consent",
    "The six-month period is directory, not mandatory (Amardeep Singh v. "
    "Harveen Kaur (2017) 8 SCC 746).",
    kind="amendment_notice",
)


def _evidence():
    return [
        _hit("Hindu Marriage Act, 1955", "Section 13B", "13B. Divorce by mutual consent."),
        _hit("Hindu Marriage Act, 1955", "Section 13", "13. Divorce on certain grounds."),
        _hit("Hindu Marriage Act, 1955", "Section 14", "14. Division of property."),
        _hit("Hindu Marriage Act, 1955", "Section 15", "15. Appeal."),
        _hit("Hindu Marriage Act, 1955", "Section 21", "21. Restraint on marriage."),
        _hit("Some site", "waiver", "The court can waive the waiting period.",
             url="https://example.invalid/waiver"),
        _hit("Another site", "case law", "A case about the cooling-off period.",
             url="https://example.invalid/case"),
        _hit("Third site", "news", "An article about divorce.", url="https://example.invalid/news"),
        NOTICE,
    ]


def test_the_notice_is_in_the_selection():
    """It carries the waiver rule, which is in nothing else."""
    picked = select_evidence_for_answer(_evidence())
    assert NOTICE in picked
    assert any("Amardeep Singh" in str(h["payload"]["text"]) for h in picked)


def test_the_web_results_are_in_the_selection():
    """The writer uses them, so the verifier has to see them."""
    picked = select_evidence_for_answer(_evidence())
    urls = [h["payload"].get("url") for h in picked]
    assert any(u for u in urls if u)


def test_the_notice_does_not_take_a_bare_act_slot():
    """It is a note about a section, not the section itself, so it must not
    crowd out the statute text."""
    picked = select_evidence_for_answer(_evidence())
    bare = [h for h in picked
            if h["payload"].get("kind") != "amendment_notice"
            and not h["payload"].get("url")]
    assert len(bare) >= 3, "the statute passages still have to be there"


def test_the_verifier_sees_the_same_passages_as_the_writer():
    """The writer's passages and the verifier's passages are the same list, so
    the verifier is never asked about something the writer could not read."""
    evidence = _evidence()
    writer_passages = select_evidence_for_answer(evidence)
    state = {"evidence": evidence}
    block = _evidence_block(state)
    assert block, "the verifier needs passages"
    for hit in writer_passages:
        body = str(hit["payload"].get("text", ""))
        if not body:
            continue
        assert body[:40] in block, "the verifier cannot see: %r" % body[:40]


def test_the_verifier_block_does_not_go_back_to_the_raw_evidence_list():
    """Guards the bug: the verifier used to take the first five of the raw
    list, which is five bare-act chunks and no web result and no notice."""
    evidence = _evidence()
    state = {"evidence": evidence}
    block = _evidence_block(state)
    assert "waiver" in block, "the web results must reach the verifier"
    assert "Amardeep Singh" in block, "the notice must reach the verifier"
