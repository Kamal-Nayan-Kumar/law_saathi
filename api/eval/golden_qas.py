"""Golden dataset: real questions with the law each answer must contain.

Not benchmark prose. Each entry is something a person actually typed, taken from
persona runs, and the expectation is the section the answer has to reach. This
is the set RAGAS and `eval_t10.py` run against, so a change that quietly drops
the governing section fails here rather than in someone's inbox.

`must_include`  — a section or term the answer must cite. Missing it is a fail.
`must_not`      — a claim that would be wrong. Saying it fails.
`min_confidence — below this the answer is not trusted.
"""

from typing import Any, Dict, List

GOLDEN_QAS: List[Dict[str, Any]] = [
    {
        "id": "maintenance-arrears-en",
        "lang": "en",
        "persona": "Wife, 34, Bengaluru. Husband stopped paying four months ago.",
        "query": "my husband has not given maintenance for 4 months what can i do",
        "must_include_any": ["18", "19", "24", "125"],
        "must_include_terms": ["maintenance", "petition", "family court"],
        "must_not": ["alimony is", "you can definitely win"],
        "min_confidence": 0.7,
        "note": "Must route to maintenance and name a real provision.",
    },
    {
        "id": "maintenance-amount-en",
        "lang": "en",
        "persona": "Same person, asking what she can claim.",
        "query": "how much can i ask for? i get 18000 he earns around 90000",
        "must_include_any": ["19", "25", "24"],
        "must_include_terms": ["reasonable", "income", "means", "needs"],
        "must_not": ["a fixed percentage", "exactly half"],
        "min_confidence": 0.7,
        "note": "Must say the amount is discretionary, not quote a formula.",
    },
    {
        "id": "custody-welfare-en",
        "lang": "en",
        "persona": "Father, 40, Kochi. Contested custody of a five-year-old.",
        "query": "who gets custody of my 5 year old daughter after divorce",
        "must_include_any": ["17", "24"],
        "must_include_terms": ["welfare", "minor"],
        "must_not": ["the mother always gets", "the father always gets"],
        "min_confidence": 0.7,
        "note": "Custody follows welfare, never a parent by default.",
    },
    {
        "id": "custody-vs-guardianship-en",
        "lang": "en",
        "persona": "Someone who has been told the wrong thing.",
        "query": "is guardianship the same as custody",
        "must_include_any": ["7", "17", "21", "22"],
        "must_include_terms": ["guardian", "welfare"],
        "must_not": ["they are the same thing"],
        "min_confidence": 0.6,
        "note": "CONTEXT.md: custody is care, guardianship is legal authority.",
    },
    {
        "id": "dv-first-report-en",
        "lang": "en",
        "persona": "Priya, 29, Delhi. Frightened, asking quietly for the first time.",
        "query": "my husband hits me. i am scared to tell anyone. what are my options",
        "must_include_any": ["17", "18", "19", "20", "21", "22"],
        "must_include_terms": ["protection", "magistrate"],
        # The single worst failure: asking a frightened woman whether her divorce
        # is mutual or contested.
        "must_not": ["mutual consent", "contested divorce"],
        "min_confidence": 0.7,
        "note": "Must reach the PWDV Act and must not pivot to divorce.",
    },
    {
        "id": "dv-residence-en",
        "lang": "en",
        "persona": "Same person, next question.",
        "query": "can i get him removed from the house",
        "must_include_any": ["19"],
        "must_include_terms": ["residence order", "shared household"],
        "must_not": [],
        "min_confidence": 0.7,
        "note": "Section 19 is the residence order.",
    },
    {
        "id": "succession-widow-en",
        "lang": "en",
        "persona": "Kamala, 68. Widowed, son abroad.",
        "query": "my husband passed away and my son is taking all the property. what can i claim",
        "must_include_any": ["8", "15", "17"],
        "must_include_terms": ["Class I", "share", "intestate"],
        "must_not": ["property law", "you should hire a property lawyer"],
        "min_confidence": 0.7,
        "note": "Land that changed hands on death is succession, not property law.",
    },
    {
        "id": "succession-will-en",
        "lang": "en",
        "persona": "Same person, asking about a will.",
        "query": "if he made a will and left everything to the son can i still claim",
        "must_include_any": ["30", "8", "15"],
        "must_include_terms": ["will", "testamentary"],
        "must_not": [],
        "min_confidence": 0.6,
        "note": "A will displaces intestate succession; must not claim otherwise.",
    },
    {
        "id": "divorce-mutual-en",
        "lang": "en",
        "persona": "Couple agreeing to end a marriage.",
        "query": "how do i get a mutual consent divorce",
        "must_include_any": ["13B"],
        "must_include_terms": ["living separately", "one year", "petition"],
        "must_not": ["you do not need a lawyer"],
        "min_confidence": 0.7,
        "note": "Section 13B is the whole answer.",
    },
    {
        "id": "adoption-relative-en",
        "lang": "en",
        "persona": "Aunt wanting to adopt a child she already cares for.",
        "query": "can my aunt adopt a child who cannot live with the parents",
        "must_include_any": ["3", "4", "9", "11"],
        "must_include_terms": ["adoption", "welfare"],
        "must_not": [],
        "min_confidence": 0.6,
        "note": "HAMA conditions for adoption by a relative.",
    },
    {
        # ---- Hindi ----
        "id": "maintenance-arrears-hi",
        "lang": "hi",
        "persona": "Sunita, Hindi-first, mixes in English.",
        "query": "मेरे पति ने 4 महीने से महनाना नहीं दी क्या करूं",
        "must_include_any": ["18", "19", "24"],
        "must_include_terms": ["मेहनाना", "याचिका", "परिवार न्यायालय"],
        "must_not": [],
        "min_confidence": 0.7,
        "note": "Must answer in Hindi, not English with a Hindi question.",
    },
    {
        "id": "custody-hi",
        "lang": "hi",
        "persona": "Hindi-speaking father.",
        "query": "अपने बच्चे की अभिरक्षा किसे मिलेगी तलाक में",
        "must_include_any": ["17", "24"],
        "must_include_terms": ["अभिरक्षा", "कल्याण"],
        "must_not": [],
        "min_confidence": 0.6,
        "note": "Devanagari must render; the answer must be in Hindi.",
    },
    # ---- Kannada ----
    {
        "id": "divorce-kn",
        "lang": "kn",
        "persona": "Lakshmi, 28, Mysuru. Newly married, short questions.",
        "query": "ವಿವಾಹ ವಿಚ್ಛೇದನೆ ಹೇಗೆ ಪಡೆಯುವುದು",
        "must_include_any": ["13B", "13"],
        "must_include_terms": ["ವಿಚ್ಛೇದನ", "ಅರ್ಜಿ"],
        "must_not": [],
        "min_confidence": 0.6,
        "note": "Kannada script must render, not boxes.",
    },
    {
        "id": "maintenance-kn",
        "lang": "kn",
        "persona": "Kannada-speaking wife.",
        "query": "ಪತಿ ಭರವಸೂ ಕೊಡುತ್ತಿಲ್ಲ ಏನು ಮಾಡಬೇಕು",
        "must_include_any": ["18", "19", "24"],
        "must_include_terms": ["ಭರವಸೂ", "ನ್ಯಾಯಾಲಯ"],
        "must_not": [],
        "min_confidence": 0.6,
        "note": "Kannada must render.",
    },
    # ---- scope ----
    {
        "id": "oos-rti-en",
        "lang": "en",
        "persona": "Someone with an RTI notice from the police.",
        "query": "i got an RTI notice from the police, what do i do",
        "must_include_any": [],
        "must_include_terms": [],
        "must_redirect": True,
        "must_not": ["Hindu Marriage Act", "Guardians and Wards", "Section 13B"],
        "min_confidence": 0.0,
        "note": "Must redirect, not answer confidently about the wrong law.",
    },
    {
        "id": "oos-landlord-en",
        "lang": "en",
        "persona": "Tenant with a deposit dispute.",
        "query": "my landlord is not returning my deposit",
        "must_include_any": [],
        "must_include_terms": [],
        "must_redirect": True,
        "must_not": ["Hindu Marriage Act"],
        "min_confidence": 0.0,
        "note": "Must redirect.",
    },
    {
        "id": "oos-motor-en",
        "lang": "en",
        "persona": "Someone whose vehicle was towed.",
        "query": "the police towed my motor vehicle, what are my rights",
        "must_include_any": [],
        "must_include_terms": [],
        "must_redirect": True,
        "must_not": ["Guardians and Wards"],
        "min_confidence": 0.0,
        "note": "Must redirect.",
    },
]


def by_id(qid: str) -> Dict[str, Any]:
    for item in GOLDEN_QAS:
        if item["id"] == qid:
            return item
    raise KeyError(qid)


def for_lang(lang: str) -> List[Dict[str, Any]]:
    return [q for q in GOLDEN_QAS if q["lang"] == lang]


def for_persona(persona: str) -> List[Dict[str, Any]]:
    """Every question a persona would realistically ask, in order."""
    return [q for q in GOLDEN_QAS if q["persona"].startswith(persona)]


if __name__ == "__main__":
    langs: Dict[str, int] = {}
    for q in GOLDEN_QAS:
        langs[q["lang"]] = langs.get(q["lang"], 0) + 1
    print(f"{len(GOLDEN_QAS)} golden questions: {langs}")
    for q in GOLDEN_QAS:
        print(f"  {q['id']:32} {q['lang']}  redirect={q.get('must_redirect', False)}")