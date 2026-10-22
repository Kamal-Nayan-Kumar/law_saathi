"""Professor-review probe: ask a fixed set of questions in EN/HI/KN and
print the answer, the language it was written in, the citations and the
trace, so the result can be read instead of guessed at.

Usage:  python3 scripts/prof_review_probe.py [name ...]
        (no args = run every case)

Writes a JSON report to tmp/prof_review.json as it goes.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import time

sys.path.insert(0, os.path.join(os.getcwd(), "api", "scripts"))
from probe import call, new_session  # noqa: E402

OUT = pathlib.Path("tmp/prof_review.json")
OUT.parent.mkdir(parents=True, exist_ok=True)

# name, query, expected language
CASES = [
    # --- core, in the three languages
    ("en-age", "what is the minimum age for a girl to get married in India", "en"),
    ("hi-age", "भारत में लड़की की शादी की कम उम्र क्या है", "hi"),
    ("kn-age", "ಭಾರತದಲ್ಲಿ ಹೆಣ್ಣೆಯ ಮದುಪೆಯ ಕನಿಷ್ಠ ವಯಸ್ಸು ಎಷ್ಟು", "kn"),
    # --- hinglish
    ("hing-age", "bharat me ladki ki shadi ki kam umar kya hai", "hi"),
    # --- dv / safety
    ("hi-dv", "मेरे पति मुझे मारते हैं, मैं अपनी रक्षा कैसे करूं", "hi"),
    ("kn-dv", "ನನ್ನ ಗಂಡ ನನ್ನನ್ನು ಹೊಡೆಯುತ್ತಾನೆ, ನಾನು ತನ್ನನ್ನು ಹೇಗೆ ರಕ್ಷಿಸಬೇಕು", "kn"),
    # --- maintenance
    ("hi-maint", "पत्नी अपने पति से कितनी मासगी मांग सकती है", "hi"),
    ("kn-maint", "ಹೆಂಡತಿ ತನ್ನ ಗಂಡನಿಂದ ಎಷ್ಟು ಹಣಕಾಸು ಕೋಲಬಹುದು", "kn"),
    # --- custody
    ("hi-custody", "भारत में तलाक के बाद बच्चे की हिरासत किसे मिलती है", "hi"),
    ("kn-custody", "ವಿವಾಹವಿಚ್ಛೇದದ ನಂತರ ಮಕುವನ ಆಧಿಕಾರ ಯಾರಿಗೆ", "kn"),
    # --- personal law edge cases
    ("en-christian-divorce", "I am a Christian man, how do I get a divorce", "en"),
    ("hi-muslim-talaq", "मैं मुस्लिम हूं, मुझे तलाक कैसे मिलेगा", "hi"),
    ("kn-hindu-succession", "ನನ್ನ ತಂದೆ ಮರಿದರು, ಮಕುವು ಎಲ್ಲ ಸಂಪತ್ತಿ ತೆಗೆದುಕೊಳ್ಳುತ್ತಾನೆ, ನಾನು ಏನು ಮಾಡಬಹುದು", "kn"),
    ("en-parsi", "I am Parsi and want to know about divorce", "en"),
    # --- edge cases a real user would type
    ("en-typo", "my husbend hasnt paid maintenence for 6 months what can i do", "en"),
    ("hi-typo", "मेरे पति ने 6 महीने से मासगी नहीं दी, मैं क्या करूं", "hi"),
    ("kn-typo", "ನನ್ನ ಗಂಡ 6 ತಿಂಗಳಿಂದ ಹಣಕಾಸು ಕೊಡುತ್ತಿಲ್ಲ, ನಾನು ಏನು ಮಾಡಬಹುದು", "kn"),
    ("en-emotional", "I am not safe in my own house", "en"),
    ("hi-emotional", "मैं अपने ही घर में सुरक्षित नहीं हूं", "hi"),
    ("kn-emotional", "ನಾನು ನನ್ನದೇ ಮನೆಯಲ್ಲಿ ಸುರಕ್ಷಿತವಾಗಿಲ್ಲ", "kn"),
    ("en-oos", "my landlord is not returning my security deposit", "en"),
    ("hi-oos", "मेरे landlord ने मेरा deposit वापस नहीं दिया", "hi"),
    ("en-empty-ish", "custody", "en"),
    ("kn-oneword", "ತಲಾಖ್", "kn"),
    ("en-dowry", "my in-laws are demanding dowry from me, what does the law say", "en"),
    ("hi-dowry", "मेरे ससुराल वाले मुझसे दहेज की मांग कर रहे हैं, कानून क्या कहता है", "hi"),
    ("kn-dowry", "ನನ್ನ ಹಿಂದಿನವರು ನನ್ನಿಂದ ಸಂಪತ್ತು ಕೋಲಿಕೆ ಮಾಡುತ್ತಿದ್ದಾರೆ, ಕಾಯಿದೆ ಏನು ಹೇಳುತ್ತದೆ", "kn"),
    ("en-mixed-script", "my पति beats me, what should I do", "hi"),
    ("en-registered", "my marriage was never registered, are we still legally married", "en"),
    ("en-interfaith", "I want to marry a girl of another religion, what do I need", "en"),
    ("en-grievance", "I want to file a complaint against my husband", "en"),
    ("hi-grievance", "मैं अपने पति के खिलाफ शिकायत दर्ज करना चाहती हूं", "hi"),
    ("kn-grievance", "ನನ್ನ ಗಂಡದ ವಿರುದ್ದು ದೂರು ನೆಗದಿ ಕೊಡಬೇಕು", "kn"),
    ("en-succession", "my father died without a will, how is the land divided", "en"),
    ("en-adoption", "can my aunt adopt a child who cannot live with the parents", "en"),
    ("en-vocational", "how much maintenance can a wife claim", "en"),
]


def script_of(text: str) -> str:
    if any("\u0c80" <= ch <= "\u0cff" for ch in text):
        return "kn"
    if any("\u0900" <= ch <= "\u097f" for ch in text):
        return "hi"
    if any(ch.isalpha() and ch.isascii() for ch in text):
        return "en"
    return "?"


def main() -> None:
    wanted = set(sys.argv[1:])
    results = []
    delay = float(os.environ.get("PROBE_DELAY", "4"))
    for name, query, want in CASES:
        if wanted and name not in wanted:
            continue
        time.sleep(delay)
        sid = new_session(user_id=1, title="prof-%s" % name)
        t0 = time.time()
        try:
            out = call("POST", "/sessions/%d/ask" % sid, body={
                "query": query, "lang": "en", "tone": "simple"})
        except Exception as exc:  # noqa: BLE001
            out = {"error": repr(exc)}
        dt = time.time() - t0
        answer = (out.get("answer") or "") if isinstance(out, dict) else ""
        rec = {
            "name": name,
            "query": query,
            "want_lang": want,
            "got_lang": out.get("lang") if isinstance(out, dict) else None,
            "answer_script": script_of(answer),
            "citations": (out.get("citations") or []) if isinstance(out, dict) else [],
            "verified": out.get("verified") if isinstance(out, dict) else None,
            "confidence": out.get("confidence") if isinstance(out, dict) else None,
            "provider": out.get("provider") if isinstance(out, dict) else None,
            "clarification": out.get("clarification") if isinstance(out, dict) else None,
            "oos_redirect": out.get("oos_redirect") if isinstance(out, dict) else None,
            "seconds": round(dt, 1),
            "answer": answer,
            "error": out.get("error") if isinstance(out, dict) else None,
            "trace": out.get("trace") if isinstance(out, dict) else None,
        }
        results.append(rec)
        OUT.write_text(json.dumps(results, ensure_ascii=False, indent=2))
        print("\n" + "#" * 76)
        print("## %-16s want=%s got=%s script=%s verified=%s prov=%s %.0fs"
              % (name, want, rec["got_lang"], rec["answer_script"],
                 rec["verified"], rec["provider"], dt))
        print("Q: %s" % query)
        if rec["error"]:
            print("ERROR: %s" % rec["error"])
        else:
            print(answer)
            print("CITES: %s" % (rec["citations"],))
        sys.stdout.flush()


if __name__ == "__main__":
    main()
