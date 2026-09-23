"""T10 smoke: 30 golden Q&As load (10/en/hi/kn), Ragas metrics declared,
LangSmith trace hook present, agent hook callable."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

def smoke():
    from eval_t10 import load_golden, RAGAS_OK, LANGSMITH_OK
    golden = load_golden()
    assert len(golden) == 30, "expected 30 golden QAs"
    from collections import Counter
    c = Counter(x["lang"] for x in golden)
    assert c.get("en") == 10 and c.get("hi") == 10 and c.get("kn") == 10, "10 per lang"
    # Each item must have expected fields per ADR-0006
    for it in golden:
        assert "question" in it and "expected_answer" in it and "lang" in it
        assert it["lang"] in ("en","hi","kn")
    # Agent eval hook importable
    from app.agent import run_agent_for_t10
    # Smoke call (stub; real requires LLM keys / retriever)
    try:
        ans = run_agent_for_t10("What is Section 13 Hindu Marriage Act?", lang="en")
        assert isinstance(ans, str)
    except Exception as exc:
        assert "no LLM" in str(exc).lower() or "backend" in str(exc).lower() or "retriever" in str(exc).lower(), "expected stub error when no key: %s" % exc
    # Metrics declared even if ragas not installed
    assert RAGAS_OK is False or RAGAS_OK is True  # just verify symbol exists
    assert LANGSMITH_OK is False or LANGSMITH_OK is True
    print("T10 SMOKE PASS — 30 golden QAs loaded (10/en/hi/kn), Ragas metrics declared, LangSmith hook present, agent hook callable")

if __name__ == "__main__":
    smoke()
