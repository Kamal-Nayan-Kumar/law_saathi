"""T9 smoke QA: verified safe responses — citations, disclaimer, confidence,
low-confidence stronger disclaimer, OOS redirect, no-citation block."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from app.agent import (run_agent, new_state, compose_answer, is_oos,
                       StubRetriever, DISCLAIMER, LOW_CONFIDENCE_DISCLAIMER, OOS_REDIRECT)
from app.schemas import AskOut

class HitRetriever:
    def search_text(self, text, top_k=5):
        return [{"payload": {"act":"Hindu Marriage Act 1955","section":"Section 13","text":"Any marriage may be dissolved by divorce."}, "score":0.95}]

class LowRetriever:
    def search_text(self, text, top_k=5):
        return [{"payload": {"act":"HMA","section":"13","text":"x"}, "score":0.4}]

class EmptyRetriever:
    def search_text(self, text, top_k=5):
        return []

def smoke():
    # Verified with high evidence => citations + disclaimer + next steps + confidence
    out = run_agent("What is Section 13 Hindu Marriage Act divorce?", lang="en",
                    llm=None, retriever=HitRetriever())
    assert out.get("verified") is True, "verified with evidence"
    assert out.get("confidence", 0) >= 0.7, "high confidence"
    assert "Based on" in out.get("answer", ""), "answer present"
    assert "Cited:" in out.get("answer", "") or out.get("citations"), "citation present"
    assert "Next steps" in out.get("answer", ""), "step guidance present"
    assert "General information" in out.get("answer", ""), "disclaimer present"

    # Low confidence (<0.7) => stronger disclaimer included
    out_low = run_agent("low evidence query", lang="en", llm=None,
                        retriever=LowRetriever())
    # Low score 0.4 below min_score 0.0 still sufficient if text present; confidence low
    assert out_low.get("confidence", 1.0) < 0.7, "low confidence emitted"
    if out_low.get("verified"):
        assert LOW_CONFIDENCE_DISCLAIMER["en"] in out_low.get("answer", ""), "strong disclaimer on low conf"

    # Unverified / empty => when clarification is not triggered, no-citation answer never reaches user
    out_u = run_agent("Unknown obscure family law", lang="en", llm=None,
                      retriever=StubRetriever())
    assert out_u.get("verified") is False, "unverified when empty"
    # If clarification triggered, it's safe; else must redirect with consult/lawyer
    answer_u = out_u.get("answer", "")
    if out_u.get("clarification"):
        assert "clarify" in answer_u.lower() or "exact issue" in answer_u.lower(), "clarification shown"
    else:
        assert "consult" in answer_u.lower() or "verify" in answer_u.lower() or "lawyer" in answer_u.lower(), "unverified blocks with redirect"
    assert out_u.get("citations") == [] or len(out_u.get("citations", [])) == 0, "no citations for unverified"

    # OOS redirect
    assert is_oos("What about property tax on land?") is True, "OOS detected"
    assert is_oos("What is divorce procedure?") is False, "family law not OOS"
    out_oos = compose_answer(new_state("tax on property"))
    # manually inject oos_redirect to test redirect path
    s = new_state("tax on property")
    s["oos_redirect"] = True
    redirect_ans, _, _ = compose_answer(s)
    assert "outside" in redirect_ans.lower() or OOS_REDIRECT["en"] in redirect_ans, "OOS redirect shown"

    # Schema accepts confidence + verified
    ask = AskOut(answer="a", verified=True, citations=["HMA — 13"], confidence=0.95)
    assert ask.confidence == 0.95
    assert ask.verified is True

    print("T9 SMOKE PASS — verified, citations, disclaimer, confidence, low-conf, OOS, block-uncited OK")

if __name__ == "__main__":
    smoke()
