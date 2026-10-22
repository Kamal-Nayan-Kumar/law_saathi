"""Why do valid family-law questions get refused?

The claim: the routing depends on the English pivot, which is an LLM call, and
the LLM call is the first thing to fail under a rate limit. When it fails, the
topic is read from the raw native text, the English keyword list finds
nothing, and the question is refused as out of scope.

This script runs the same questions twice: once with the pivot working, and
once with the pivot forced to fail, and shows the difference in routing.

Usage:  python3 scripts/pivot_dependency.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.getcwd(), "api"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.getcwd(), "api", ".env"))
from app import agent as A  # noqa: E402

QUESTIONS = [
    ("hi-maint", "पत्नी अपने पति से कितनी मासगी मांग सकती है"),
    ("hi-typo", "मेरे पति ने 6 महीने से मासगी नहीं दी, मैं क्या करूं"),
    ("hi-griev", "मैं अपने पति के खिलाफ शिकायत दर्ज करना चाहती हूं"),
    ("kn-maint", "ಹೆಂಡತಿ ತನ್ನ ಗಂಡನಿಂದ ಎಷ್ಟು ಹಣಕಾಸು ಕೋಲಬಹುದು"),
    ("kn-dowry", "ನನ್ನ ಹಿಂದಿನವರು ನನ್ನಿಂದ ಸಂಪತ್ತು ಕೋಲಿಕೆ ಮಾಡುತ್ತಿದ್ದಾರೆ"),
    ("kn-dv", "ನನ್ನ ಗಂಡ ನನ್ನನ್ನು ಹೊಡೆಯುತ್ತಾನೆ"),
    ("hi-custody", "भारत में तलाक के बाद बच्चे की हिरासत किसे मिलती है"),
    ("en-typo", "my husbend hasnt paid maintenence for 6 months what can i do"),
]

PIVOT = "Translate this Indian family-law question into English so it can be matched against a corpus of Indian statutes written in English. Output only the translation, nothing else."


def routing(query: str, pivot: str) -> dict:
    """What the agent decides, given this English pivot."""
    slots = A.extract_slots(pivot, query_native=query)
    return {
        "topic": slots.get("topic"),
        "oos": A.is_oos(pivot) and A.is_oos(query),
        "oos_pivot_only": A.is_oos(pivot),
        "missing": A.missing_for(slots, pivot),
    }


def main() -> None:
    print("=" * 78)
    print("The same question, routed with the English pivot and without it.")
    print("=" * 78)
    for name, query in QUESTIONS:
        lang = A.detect_lang(query)
        if lang == "en":
            pivot = query
            how = "english question, no pivot needed"
        else:
            try:
                pivot, _ = A.chat_complete([
                    {"role": "system", "content": PIVOT},
                    {"role": "user", "content": query},
                ])
            except Exception as exc:  # noqa: BLE001
                pivot = query
                how = "pivot FAILED (%s)" % (str(exc)[:40])
            else:
                how = "pivot returned"
        with_pivot = routing(query, pivot)
        without = routing(query, query)   # pivot failed -> raw native text
        flag = "  <-- DIFFERENT" if (
            with_pivot["topic"] != without["topic"]
            or with_pivot["oos"] != without["oos"]
        ) else ""
        print("\n%s  [%s]  %s" % (name, lang, query))
        print("   pivot        : %r   (%s)" % (pivot[:60], how))
        print("   with pivot   : topic=%-18s oos=%-5s missing=%s"
              % (with_pivot["topic"], with_pivot["oos"], with_pivot["missing"]))
        print("   pivot failed : topic=%-18s oos=%-5s missing=%s"
              % (without["topic"], without["oos"], without["missing"]))
        print("   is_oos on the pivot alone: %s" % with_pivot["oos_pivot_only"])
        if flag:
            print(flag)


if __name__ == "__main__":
    main()
