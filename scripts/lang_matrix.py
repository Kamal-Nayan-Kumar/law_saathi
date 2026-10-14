"""End-to-end: 5 questions x 4 languages through the real agent, live Qdrant
+ live Groq. Prints the answer, the citations and the trace so the answer
quality can be read, not guessed at.

Usage: python3 scripts/lang_matrix.py [lang ...]   (default: all four)
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.getcwd(), "api"))
from dotenv import load_dotenv

load_dotenv(os.path.join(os.getcwd(), "api", ".env"))
from app.agent import run_agent  # noqa: E402

QUESTIONS = [
    ("marriage age",
     {"en": "what is the minimum age for a girl to get married in India",
      "hi": "भारत में लड़की की शादी की कम उम्र क्या है",
      "hinglish": "bharat me ladki ki shadi ki kam umar kya hai",
      "kn": "ಭಾರತದಲ್ಲಿ ಹೆಣ್ಣೆಯ ಮದುಪೆಯ ಕನಿಷ್ಠ ವಯಸ್ಸು ಎಷ್ಟು"}),
    ("husband beats me",
     {"en": "my husband beats me, what can I do to protect myself",
      "hi": "मेरे पति मुझे मारते हैं, मैं अपनी रक्षा कैसे करूं",
      "hinglish": "mere pati mujhe marte hai main apni raksha kaise karu",
      "kn": "ನನ್ನ ಗಂಡ ನನ್ನನ್ನು ಹೊಡೆಯುತ್ತಾನೆ, ನಾನು ತನ್ನನ್ನು ಹೇಗೆ ರಕ್ಷಿಸಬೇಕು"}),
    ("dowry demand",
     {"en": "my in-laws are demanding dowry from me, what does the law say",
      "hi": "मेरे ससुराल वाले मुझसे दहेज की मांग कर रहे हैं, कानून क्या कहता है",
      "hinglish": "mere sasural wale mujhse dahej ki maang kar rahe hai kanoon kya kehta hai",
      "kn": "ನನ್ನ ಹಿಂದಿನವರು ನನ್ನಿಂದ ಸಂಪತ್ತು ಕೋಲಿಕೆ ಮಾಡುತ್ತಿದ್ದಾರೆ, ಕಾಯಿದೆ ಏನು ಹೇಳುತ್ತದೆ"}),
    ("child custody",
     {"en": "who gets custody of the child after a divorce in India",
      "hi": "भारत में तलाक के बाद बच्चे की हिरासत किसे मिलती है",
      "hinglish": "bharat me talak ke baad bacche ki hirasat kise milti hai",
      "kn": "ಭಾರತದಲ್ಲಿ ವಿವಾಹವಿಚ್ಛೇದದ ನಂತರ ಮಕುವನ ಆಧಿಕಾರ ಯಾರಿಗೆ"}),
    ("maintenance",
     {"en": "how much maintenance can a wife claim from her husband",
      "hi": "पत्नी अपने पति से कितनी मासगी मांग सकती है",
      "hinglish": "patni apne pati se kitni masgi maang sakti hai",
      "kn": "ಹೆಂಡತಿ ತನ್ನ ಗಂಡನಿಂದ ಎಷ್ಟು ಹಣಕಾಸು ಕೋಲಬಹುದು"}),
]

langs = sys.argv[1:] or ["en", "hi", "hinglish", "kn"]
DELAY = float(os.environ.get("MATRIX_DELAY", "10"))
out = {}
for name, by_lang in QUESTIONS:
    for lang in langs:
        q = by_lang[lang]
        time.sleep(DELAY)   # stay out of the provider circuit breaker
        t0 = time.time()
        try:
            st = run_agent(q, lang=lang, memory={})
            ans = st.get("answer", "")
            cites = st.get("citations") or []
            prov = st.get("provider", "")
        except Exception as e:  # noqa: BLE001
            ans, cites, prov = "ERROR: %r" % (e,), [], ""
        out[(name, lang)] = ans
        print("\n" + "=" * 78)
        print("### %s / %s  (%.1fs, provider=%s, detected=%s)"
              % (name, lang, time.time() - t0, prov,
                 st.get("lang") if isinstance(st, dict) else "?"))
        print("Q: %s" % q)
        print("-" * 78)
        print(ans)
        print("-" * 78)
        for c in cites:
            print("   src: %s" % str(c)[:110])
        sys.stdout.flush()