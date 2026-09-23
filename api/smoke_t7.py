"""T7 smoke QA: verified & safe responses — verified flag, disclaimer, min_score."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from app.agent import run_agent, new_state, compose_answer, DISCLAIMER, StubRetriever
from app.schemas import AskOut

class HitRetriever:
    def search_text(self, text, top_k=5):
        return [{"payload": {"act":"Hindu Marriage Act 1955","section":"Section 13","text":"Any marriage may be dissolved by divorce."}, "score":0.95}]

def smoke():
    # Verified with evidence
    out = run_agent("What is Section 13 Hindu Marriage Act divorce?", lang="en",
                    llm=None, retriever=HitRetriever())
    assert out.get("verified") is True, "evidence sufficient => verified"
    assert DISCLAIMER["en"] in out.get("answer", ""), "disclaimer in safe answer"
    assert out.get("citations"), "verified answer must cite"
    assert out.get("retries", 0) == 0

    # Unverified (stub => clarification or retries)
    out_u = run_agent("Unknown obscure family law", lang="en", llm=None,
                      retriever=StubRetriever())
    assert out_u.get("verified") is False or out_u.get("verified") == False
    # When evidence is empty after retries, verified stays False.
    # If clarification triggered, verified also False by default.

    # Schema accepts verified + min_score
    ask = AskOut(answer="a", verified=True, citations=["HMA — 13"])
    assert ask.verified is True
    # min_score parameter flows through endpoint shape
    from app.schemas import AskIn
    body = AskIn(query="q", lang="en", min_score=0.8)
    assert body.min_score == 0.8

    print("T7 SMOKE PASS — verified flag, disclaimer, min_score, schema OK")

if __name__ == "__main__":
    smoke()
