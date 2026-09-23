"""T5 smoke QA: amendment-style query → citation_sources has bare_act + web."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from app.agent import run_agent, new_state, compose_answer

def smoke():
    # Inject fake evidence like RAG chunk + web hit (simulates Firecrawl return)
    state = new_state("amended section 13B Hindu Marriage Act 2024")
    state["evidence"] = [
        {"payload": {"act": "Hindu Marriage Act", "section": "13B", "text": "Mutual consent divorce."}, "score": 0.92},
        {"payload": {"url": "https://example.gov/in/amendment-2024", "title": "Amendment 2024", "text": "Recent amendment to Section 13B."}, "score": 0.88},
    ]
    answer, citations, sources = compose_answer(state)
    print("Answer head:", answer[:120])
    print("Citations:", citations)
    print("Sources:", sources)
    assert "bare_act" in sources, "missing bare_act citation"
    assert "web" in sources, "missing web citation"
    assert any("Amendment 2024" in c for c in citations), "web citation missing"
    print("T5 SMOKE PASS: both bare_act and web cited.")

if __name__ == "__main__":
    smoke()
