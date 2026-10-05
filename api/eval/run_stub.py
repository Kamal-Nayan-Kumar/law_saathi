"""Run the golden dataset with the model stubbed out.

The checks in run_golden.py are about routing, language and scope — decisions
the code makes, not the model's prose. Those must be verifiable without any API
key, and they must keep working when every free tier is rate-limited, which is
most of the time on this project.

What it cannot check is answer content: a stub writes a fixed answer, so term
checks are skipped and only the structural ones run. Answer quality needs a
live run (`run_golden.py --flows`) or the judged metrics in `ragas_eval.py`.

    python3 api/eval/run_golden.py --stub
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.dirname(HERE)
sys.path.insert(0, API)

from eval.golden_qas import GOLDEN_QAS  # noqa: E402


def stub_agent() -> None:
    """Point the agent at a canned model and a canned corpus."""
    from app import agent as A

    def fake_llm(messages, **kw):
        system = messages[0]["content"].lower()
        user = messages[-1]["content"]
        if "planner" in system:
            return json.dumps({
                "governing_act": "Hindu Adoption and Maintenance Act, 1956",
                "reasoning": "stub",
                "steps": [{"tool": "search_acts", "query": user[:60],
                           "why": "stub"}],
            }), "stub"
        if "verifier" in system:
            return json.dumps({"verdict": "grounded", "reason": "stub",
                               "next_queries": []}), "stub"
        if "translator" in system or "Translate this" in system:
            return user, "stub"
        return ("Here is a plain-language explanation. A petition may be filed in "
                "the family court for a reasonable amount based on income and "
                "needs, and the welfare of the minor is the first consideration "
                "[1]."), "stub"

    A.chat_complete = fake_llm
    A.translate_complete = fake_llm

    class Store:
        def search_text(self, text, top_k=5, filter_payload=None):
            act = ("Guardians and Wards Act, 1890"
                   if "guardian" in text.lower() or "custody" in text.lower()
                   else "Hindu Adoption and Maintenance Act, 1956")
            section = "Section 17: Guardian of the minor" if "17" in act else \
                "Section 18: Maintenance of wife"
            body = ("In the matter of a minor the Court shall be guided by what "
                    "is conducive to the welfare of the minor.") if "17" in act \
                else ("A Hindu wife is entitled to maintenance from her husband "
                      "and the Court shall decide a reasonable amount having "
                      "regard to her needs and his means.")
            return [{"id": "p1", "score": 0.9,
                     "payload": {"act": act, "section": section, "text": body}}]

        def search(self, q, top_k=5):
            return self.search_text(str(q), top_k)

    A.default_retriever = lambda: Store()


def structural_checks(item: Dict[str, Any], result: Dict[str, Any]) -> List[str]:
    """The checks that hold regardless of what the model wrote."""
    problems: List[str] = []
    answer = str(result.get("answer") or "")
    low = answer.lower()

    if item.get("must_redirect"):
        if not result.get("oos_redirect") and "outside my family-law scope" not in low:
            problems.append("should have redirected out of scope")
        for banned in item.get("must_not", []):
            if banned.lower() in low:
                problems.append(f"mentioned {banned!r} on an out-of-scope question")
        return problems

    if not answer:
        return ["empty answer"]
    if not result.get("citations"):
        problems.append("no citations")
    if not result.get("verified", False):
        problems.append("not verified")

    # Language is a code decision, not a prose decision: the right script must
    # come back for a Hindi or Kannada question.
    if item["lang"] in ("hi", "kn"):
        script = "ऀ-ॿ" if item["lang"] == "hi" else "ಀ-೿"
        if not re.search(f"[{script}]", answer):
            problems.append(f"wrong script for lang={item['lang']}")

    # The disclaimer must be on a legal answer, in the right language.
    if item["lang"] == "hi" and "कानूनी सलाह नहीं" not in answer:
        problems.append("missing the Hindi disclaimer")
    if item["lang"] == "kn" and "ಕಾನೂನು ಸಲಹೆಯಲ್ಲ" not in answer:
        problems.append("missing the Kannada disclaimer")

    # A clarification is a legitimate outcome for a genuinely vague question, but
    # not for these: each names its topic clearly enough to answer.
    if result.get("clarification"):
        problems.append("asked for clarification on a clear question")

    return problems


def main(argv: List[str]) -> int:
    stub_agent()
    from app import agent as A

    rows: List[Dict[str, Any]] = []
    for item in GOLDEN_QAS:
        slots = A.extract_slots(item["query"])
        oos = A.is_oos(item["query"])
        problems: List[str] = []

        if item.get("must_redirect") and not oos:
            problems.append("routing: should be out of scope")
        if not item.get("must_redirect"):
            if oos:
                problems.append("routing: wrongly out of scope")
            if not slots.get("topic"):
                problems.append(f"routing: no topic ({slots})")
            if A.detect_lang(item["query"], item["lang"]) != item["lang"]:
                problems.append("routing: wrong language detected")
            # A clarification may only replace the answer when the answer would
            # actually change. For these two slots it is appended to a full
            # answer instead, so what must not happen is a bare question.
            missing = A.missing_for(slots, item["query"])
            if missing and not A.should_answer_anyway(missing):
                problems.append(
                    f"routing: would ask for {missing} instead of answering")
            elif missing and not A.clarification_question(missing, item["lang"]):
                problems.append("routing: follow-up question is empty")

        rows.append({"id": item["id"], "topic": slots.get("topic"),
                     "oos": oos, "problems": problems})

    # The OOS branch must produce the redirect itself, not an empty answer.
    for item in GOLDEN_QAS:
        if not item.get("must_redirect"):
            continue
        state = A.new_state(item["query"], lang=item["lang"])
        state["slots"] = A.extract_slots(item["query"])
        state["oos_redirect"] = True
        answer, cites, _ = A.compose_answer(state)
        if "outside my family-law scope" not in answer.lower():
            rows.append({"id": item["id"] + "-redirect",
                         "problems": ["no redirect text produced"]})
        if cites:
            rows.append({"id": item["id"] + "-redirect",
                         "problems": ["redirect carried citations"]})

    passed = [r for r in rows if not r["problems"]]
    print(f"\n{len(passed)}/{len(rows)} passed (stub, routing and structure)\n")
    for r in rows:
        print(("PASS  " if not r["problems"] else "FAIL  ") + r["id"])
        for p in r["problems"]:
            print(f"        - {p}")

    out = sys.argv[2] if len(sys.argv) > 2 else None
    if out:
        with open(out, "w") as fh:
            json.dump({"total": len(rows), "passed": len(passed), "rows": rows},
                      fh, indent=1, ensure_ascii=False)
        print(f"\nwrote {out}")
    return 0 if len(passed) == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))