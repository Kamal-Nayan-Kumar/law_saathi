"""Run a persona through the chat and print every answer.

Each persona is a real person with a real problem, written the way that person
would actually type: short, misspelled, in their own language, often missing
the facts a lawyer would ask for. The point is to see what Saathi does with a
real question, not a benchmark question.

    python3 api/scripts/personas.py            # all personas
    python3 api/scripts/personas.py maintenance # one by name
"""
from __future__ import annotations

import json
import sys
import time

sys.path.insert(0, __file__.rsplit("/", 1)[0])

import probe  # noqa: E402


class Persona:
    def __init__(self, key, name, lang, turns):
        self.key = key
        self.name = name
        self.lang = lang
        self.turns = turns


PERSONAS = [
    Persona(
        "maintenance",
        "Sunita, 34, Bengaluru. Married 8 years, two kids, husband stopped paying.",
        "en",
        [
            "my husband has not given maintenance for 4 months what can i do",
            "how much can i ask for? i get 18000 he earns around 90000",
            "how long does it take",
            "do i need a lawyer?",
        ],
    ),
    Persona(
        "custody",
        "Joseph, 40, Kochi. Contested custody of a 5-year-old after a divorce.",
        "en",
        [
            "who gets custody of my 5 year old daughter after divorce",
            "my wife says i earn more so i should pay more. is that how it works?",
        ],
    ),
    Persona(
        "elderly",
        "Kamala, 68, Thiruvananthapuram. Widowed, son in Dubai, wants to know her rights.",
        "en",
        [
            "i am 68 my husband passed away last year. my son lives in dubai and sends money sometimes. am i entitled to anything from my husband's property?",
            "if he made a will and left everything to the son can i still claim",
        ],
    ),
    Persona(
        "hindi_first",
        "Sunita, first time using the app, types in Hindi, mixes in English.",
        "hi",
        [
            "मेरे पति ने 4 महीने से मेहनाना नहीं दी क्या करूं",
            "कितनी मांग सकती हूं",
            "क्या वकील लेना जरूरी है",
        ],
    ),
    Persona(
        "kannada_first",
        "Lakshmi, 28, Mysuru. Newly married, in Kannada, very short questions.",
        "kn",
        [
            "ಪತಿ ಬಿಡಿ ಮಾಡಿಕೊಡುತ್ತಾನೆ ಏನು ಮಾಡಬೇಕು",
            "ವಿವಾಹ ವಿಚ್ಛೇದನೆ ಹೇಗೆ ಪಡೆಯುವುದು",
        ],
    ),
    Persona(
        "domestic_violence",
        "Priya, 29, Delhi. Frightened, asking quietly.",
        "en",
        [
            "my husband hits me. i am scared to tell anyone. what are my options",
            "can i get him removed from the house",
        ],
    ),
    Persona(
        "low_information",
        "A confused first-time user who gives almost no facts.",
        "en",
        [
            "custody",
            "maintenance krna hai",
            "divorce",
        ],
    ),
    Persona(
        "out_of_scope",
        "A user who asks about something the product does not cover.",
        "en",
        [
            "my landlord is not returning my deposit",
            "i got an RTI notice from the police, what do i do",
        ],
    ),
]


def run(p: Persona) -> dict:
    sid = probe.new_session(1, f"persona:{p.key}")
    out = []
    for q in p.turns:
        t0 = time.time()
        try:
            r = probe.ask(sid, q, lang=p.lang)
        except Exception as e:  # noqa: BLE001 - the failure is the finding
            out.append({"q": q, "error": str(e)})
            continue
        out.append(
            {
                "q": q,
                "ms": int((time.time() - t0) * 1000),
                "answer": r.get("answer"),
                "citations": r.get("citations"),
                "clarification": r.get("clarification"),
                "verified": r.get("verified"),
                "confidence": r.get("confidence"),
                "trace": r.get("trace"),
                "provider": r.get("provider"),
                "retries": r.get("retries"),
            }
        )
    return {"persona": p.key, "who": p.name, "lang": p.lang, "session": sid, "turns": out}


def main(argv):
    only = argv[1] if len(argv) > 1 else None
    people = [p for p in PERSONAS if not only or p.key == only]
    if not people:
        print("no persona named", only)
        return 1
    results = [run(p) for p in people]
    print(json.dumps(results, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))