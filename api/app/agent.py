"""T3: LangGraph 5-node agent (intent -> planner -> tools -> verifier -> response).

Design (per ADRs 0001/0002/0009):
- Five nodes + shared state; verifier loops back to tools on weak evidence
  (bounded retries). Planner asks a follow-up when key slots are missing
  instead of guessing.
- LLM: Groq ``openai/gpt-oss-120b`` primary, OpenRouter fallback with logging.
- English-pivot: detect input lang, translate non-EN query to EN, retrieve
  and reason in EN, answer in the user's lang.

No hard third-party imports at import time (Python 3.9 compatible): langgraph,
langsmith, and HTTP clients are imported lazily so unit tests run on a bare
checkout. Pass ``retriever`` / ``llm`` doubles in tests; live backends are
only constructed when keys exist.
"""
import json
import logging
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
# Tried in order after the primary model fails. Same key, same provider, but
# Groq meters its daily token allowance per model, so these do not go down when
# gpt-oss-120b does. See _groq_models() for what happened when nothing did.
GROQ_FALLBACK_MODELS_DEFAULT = "openai/gpt-oss-20b,qwen/qwen3.8-27b"
# OpenRouter is the *fallback* (ADR-0002). The old default was a 7B model, which
# is too small to write a grounded legal explanation: in persona testing it
# produced vague answers with no inline citations and a wrong section list. The
# fallback should still be a model that can reason over five passages.
OPENROUTER_MODEL = os.environ.get(
    "OPENROUTER_MODEL", "meta-llama/llama-3.3-70b-instruct")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1"
# Last-resort provider: OpenCode Zen's free tier costs nothing per token, so
# chat keeps working when Groq and OpenRouter are both rate-limited.
OPENCODE_URL = "https://opencode.ai/zen/v1/chat/completions"
OPENCODE_MODEL = os.environ.get("OPENCODE_MODEL", "space-bunny-free")
# Cloudflare in front of Zen answers 403 to urllib's default user agent.
OPENCODE_UA = os.environ.get("OPENCODE_USER_AGENT", "LawSaathi/1.0")
# A run makes five to seven model calls. With two retries the verifier loop can
# reach eleven, and on a rate-limited key each fallback costs seconds: persona
# testing saw a single Kannada question take 228s. One retry is enough to widen
# a search; past that the user waits longer than any extra passage is worth.
MAX_RETRIES = int(os.environ.get("LAWSAATHI_MAX_RETRIES", "1"))

# Hard ceiling on model calls per run. Hitting it degrades to the template
# answer rather than looping, so a bad key cannot make the chat unusable.
MAX_LLM_CALLS = int(os.environ.get("LAWSAATHI_MAX_LLM_CALLS", "6"))

# Short answers get a short budget. The verifier returns a one-line JSON object
# and the planner a small plan; giving them the full reasoning budget is what
# made a 0.8s call take 4s.
MAX_TOKENS_LONG = int(os.environ.get("LAWSAATHI_MAX_TOKENS", "6000"))
MAX_TOKENS_SHORT = int(os.environ.get("LAWSAATHI_MAX_TOKENS_SHORT", "1600"))
# A plan longer than this is a model rambling, not a plan. Cap it so one bad
# reply cannot turn into a dozen retrieval calls.
MAX_PLAN_STEPS = 4

NODES = ("intent", "planner", "tools", "reason", "verifier", "response")

TOPIC_KEYWORDS = {
    "divorce": ("divorce", "divorced", "talak", "talaq", "khula", "mubaraat",
                "तलाक", "ವಿಚ್ಛೇದನ"),
    "maintenance": ("maintenance", "maintainence", "bharan", "poshan",
                    "kharcha", "guzara", "भरण", "पोषण", "ಪೋಷಣೆ",
                    "alimony",
                    # People misspell: "मेहनाना" is how maintenance is usually
                    # written, while the Act says "maintenance". Both spellings,
                    # and the question that names no topic at all ("how much can
                    # I ask for?") had to be routed by what it is asking.
                    "मेहनाना", "महनाना", "मेनेनाना", "वेतन", "भरणपोषण",
                    "करचा", "खर्चा", "गुजारा", "पोसण", "पोषण",
                    "ಎಷ್ಟು ಕೊಡಿ", "ಎಷ್ಟು ಬೇಕು", "ಭರವಸೂ", "ಹಿಂಗಿರಿ", "ಭರಿಸುವ",
                    "ಜೀವನಾಂಶ"),
    "custody": ("custody", "guardian", "अभिरक्षा", "ಹೆತ್ತವರ", "ವಶ",
                 "removal order", "removed from the house", "residence order",
                 "right to reside", "who stays in the house",
                 "उसे रहने", "घर से बाहर", "ಮನೆಯಿಂದ ಹೊರಗೆ"),
    "adoption": ("adoption", "adopt", "adopted", "गोद", "ದತ್ತು"),
    "succession": ("succession", "inheritance", "inherit", "heir",
                   "virasat", "viraasat",
                   "jaydad", "jaaydaad", "उत्तराधिकार", "ಉತ್ತರಾಧಿಕಾರ",
                   "वारिस"),
    # People describe domestic violence in the words of the act, not its name:
    # "my husband hits me", "he beats me", "she tortures me". None of those
    # contain "domestic violence", so every one of them fell through to "what is
    # this about?" — the worst possible reply to someone who is frightened.
    "domestic_violence": ("domestic violence", "domestic-violence", "dowry",
                          "dahej", "marpeet", "maarpeet", "घरेलू हिंसा",
                          "ಕೌಟುಂಬಿಕ ಹಿಂಸೆ", "protection order",
                          "hits me", "hit me", "hits her", "beats me",
                          "beat me", "beating me", "beats her", "tortures me",
                          "torture", "abuses me", "abuse", "abused",
                          "abusing", "struck me", "slaps me", "slapped me",
                          "beats up", "threatens me", "threaten me",
                          "scared to tell", "afraid of my husband",
                          "afraid of my wife", "not safe at home",
                          # Coercive control is domestic violence under s.3(a) —
                          # "fear, harassment or injury" — but people describe it
                          # as confinement or being watched. None of the words
                          # below contain the name of the Act, and each of these
                          # questions returned zero evidence: no topic, no
                          # retrieval, no answer. That is the worst possible
                          # reply to someone who is frightened.
                          #
                          # These are kept out of TOPIC_KEYWORDS because "scared"
                          # and "not safe" alone are not about a person: "I am
                          # scared of the court process" is a maintenance
                          # question. They are matched in extract_slots, where the
                          # surrounding words are known — see _FEAR_IS_PERSONAL.
                          "not letting me leave", "does not let me leave",
                          "won't let me leave", "keeps me locked",
                          "locks the door", "locks me in",
                          "waits for me to leave", "waits till i leave",
                          "follows me", "watches me", "does not let me speak",
                          "won't let me speak", "takes my phone", "hides money",
                          "hide money", "keeps my phone", "keeps money from me",
                          "not allowed to leave", "not allowed to go out",
                          "i cannot leave", "i can't leave", "i cannot go out",
                          "threatens to", "shouted at me", "screams at me",
                          "scares me", "intimidates me", "follows me home",
                          "मुझे डर", "डर लगता", "अकेला नहीं छोड़",
                          "निकलने नहीं देता", "मारने की धमकी", "फोन छीन",
                          "नजर रखता", "निगरानी रखता",
                          "ನನಗೆ ಭಯ", "ಹೊರಡೆ", "ಬೀಗ ಹಾಕುತ್ತಾನೆ",
                          "ದೂರ ಮನೆ", "ಹೊಡೆ", "ಹಿಂಸೆ", "ಬೀದು", "ದೌರ್ಜನೆ"),
    "marriage": ("marriage", "marry", "married", "marital", "wedding",
                 "shadi", "shaadi", "vivah",
                 "nikah", "nikaha", "sagai", "engagement", "विवाह", "शादी",
                 "ಮದುವೆ", "conjugal"),
    # Inter-caste and inter-religious marriage are Special Marriage Act
    # questions, and they are the questions people are most afraid to ask.
    "interfaith_marriage": ("different religion", "different faith",
                            "inter religious", "inter-religious",
                            "interfaith", "other religion", "hindu and muslim",
                            "hindu muslim", "muslim boy", "muslim girl",
                            "christian boy", "christian girl", "inter caste",
                            "inter-caste", "different caste", "love marriage",
                            "हिंदू मुस्लिम", "अलग धर्म", "ಹಿಂದೂ ಮುಸ್ಲಿಂ"),
}

PARTY_WORDS = ("husband", "wife", "spouse", "pati", "patni", "biwi", "shohar",
               "bachcha", "bacha", "baccha", "beta", "beti", "maa", "baap",
               "aurat", "aadmi", "पति", "पत्नी", "पति", "पत्नी", "पोषण",
               "ಗಂಡ", "ಹೆಂಡತಿ", "ಪತಿ", "ಪತ್ನಿ",
               "mother", "father", "minor", "child", "widow", "widower",
               "माता", "पिता")

_DIVORCE_TYPE_RE = re.compile(
    r"mutual(\s+consent)?|contested|one[-\s]?sided|ex[-\s]?parte|आपसी\s*सहमति"
    r"|khula|mubaraat",
    re.IGNORECASE)
_SECTION_RE = re.compile(
    r"section\s+(\d+[A-Z\-]*)|धारा\s+(\d+)|dhara\s+(\d+)", re.IGNORECASE)

# Act names carry the word "marriage", so asking about "the Hindu Marriage
# Act" used to set topic=marriage even for a divorce section. When the user
# names a section, the section decides the topic.
_SECTION_TOPIC = {
    "4": "marriage", "5": "marriage", "6": "marriage", "7": "marriage",
    "8": "marriage", "9": "marriage", "10": "marriage", "11": "marriage",
    "12": "marriage",
    "13": "divorce", "13A": "divorce", "13B": "divorce", "14": "divorce",
    "24": "domestic_violence", "25": "domestic_violence",
    "26": "domestic_violence", "27": "domestic_violence",
}
# Same intent, romanised / other script.
_SECTION_TOPIC_ALIASES = {
    "13a": "divorce", "13b": "divorce",
}

# Names of the acts themselves. These must NOT decide the topic — an act
# covers many topics, and its name is always in play.
_ACT_NAME_RE = re.compile(
    r"hindu\s+marriage\s+act|special\s+marriage\s+act|"
    r"hindu\s+adoption\s+and\s+maintenance\s+act|"
    r"hindu\s+succession\s+act|guardians\s+and\s+wards\s+act|"
    r"domestic\s+violence\s+act|indian\s+divorce\s+act|"
    r"hindu\s+minority\s+act", re.IGNORECASE)


def _section_topic(section: str) -> Optional[str]:
    """Topic implied by a bare section number, or None if unknown."""
    if not section:
        return None
    key = section.strip().upper()
    if key in _SECTION_TOPIC:
        return _SECTION_TOPIC[key]
    return _SECTION_TOPIC_ALIASES.get(key.lower())


# Roman-Hindi (Hinglish) signals: users often type Hindi in Latin script
# ("kitna umar hona chahiye shadi ke liye"), which no Indic script matches.
# Nouns that also appear in English queries (talaq, nikah, dowry) are NOT
# markers — only grammar/function words and Hinglish-only nouns.
HINGLISH_WORDS = frozenset(
    "hai hain kya kaise kaun kahan kab kyun kyunki kitna kitne kitni "
    "chahiye liye batao bataiye bataye samjhao meri mera mere apna apni "
    "apne aapka aapki tumhara humara hamara mujhe tumhe tujhe aapko humko "
    "nahi nahin wala wali wale karo karein karna karne hona hoga hogi "
    "honge hota hoti hote tha thi raha rahi rahe gaya gayi gaye liya "
    "diya kiya hua hui hue sakta sakti sakte shadi shaadi vivah pati "
    "patni biwi shohar bachcha bacha baccha umar saal mahina paisa ghar "
    "maa baap beta beti aurat aadmi bharan poshan kharcha guzara dahej "
    "marpeet maarpeet virasat viraasat jaydad sagai".split())

HINGLISH_BIGRAMS = frozenset((
    "ke liye", "ke bare", "ke baare", "kya hai", "hai kya", "kaise kare",
    "kaise karein", "hona chahiye", "karna hai", "mein hai", "main hoon",
    "kya hota", "kya hoti", "kitna hai", "kitni hai",
))


def hinglish_score(text: str) -> int:
    """Count Hinglish signals (words + bigrams) in a Latin-script query."""
    low = re.sub(r"[^a-z\s]", " ", (text or "").lower())
    words = low.split()
    hits = sum(1 for w in words if w in HINGLISH_WORDS)
    pairs = {"%s %s" % (a, b) for a, b in zip(words, words[1:])}
    hits += sum(1 for b in pairs if b in HINGLISH_BIGRAMS)
    return hits


def detect_lang(text: str, hint: str = "en") -> str:
    """The language the answer must be written in: en, hi or kn.

    Driven by the question itself. A user who types Kannada gets Kannada back,
    and a user who types English gets English back even if an earlier preference
    said otherwise. The script of what they just wrote is a far stronger signal
    about the person in front of us than a stored setting.

    ``hint`` is the caller's guess. It is no longer trusted for choosing the
    output language; the script decides. That is what removed the failure where
    a stored "Hindi" preference made the product answer an English question in
    Hindi, leaving the reader convinced their own words were in the wrong
    language.
    """
    blob = text or ""
    if re.search(r"[\u0C80-\u0CFF]", blob):
        return "kn"
    if re.search(r"[\u0900-\u097F]", blob):
        return "hi"
    if hinglish_score(blob) >= 2:
        return "hi"  # Roman Hindi, e.g. "shadi ke liye umar"
    # Roman script and not Hinglish: English.
    return "en"


# The pivot prompt, kept in one place because losing a legal term here silently
# ruins retrieval: the word the user used never reaches the English corpus.
#
# Measured on the live Qdrant collection (5 questions x 4 languages, top-8 hit
# rate against the Act that actually governs the question):
#
#   raw query, no pivot : 15/20 in top-8,  7/20 at rank 1
#   English pivot       : 20/20 in top-8, 13/20 at rank 1
#
# e5-small aligns topics, not legal terms. A Kannada "sampattu kelike" matched
# the Indian Succession Act and a Hinglish "dahej maang rahe hai" matched the
# Christian Marriage Act, because nothing in a non-English string says "dowry".
# So the pivot stays — see ADR-0011.
#
# The gloss below exists because the same Kannada dowry line came back as "my
# former spouse is demanding property from me": both "in-laws" and "dowry" were
# replaced by ordinary words. Retrieval then chased succession law at rank 6
# instead of the Dowry Prohibition Act at rank 1.
QUERY_PIVOT_PROMPT = (
    "Translate this Indian family-law question into English so it can be "
    "matched against a corpus of Indian statutes written in English. Output "
    "only the translation, nothing else.\n"
    "\n"
    "Rules:\n"
    "- Translate for a search engine, not for elegance. Keep the exact legal "
    "meaning of every term.\n"
    "- Keep these terms as themselves or as their exact Indian legal English "
    "equivalent, and never replace them with a generic word: dowry, "
    "maintenance, alimony, custody, guardianship, adoption, succession, "
    "inheritance, joint family, partition, khula, talaq, iddat, mahr, "
    "domestic violence, restitution of conjugal rights, judicial separation, "
    "mutual consent, child marriage, registration of marriage.\n"
    "- 'Kannada/Hindi for dowry' is dowry. 'For maintenance' is maintenance. "
    "Do not widen a specific family-law term into 'property' or 'money'.\n"
    "- 'In-laws' (the husband's or wife's family) is in-laws, never 'former "
    "spouse' or 'relatives'.\n"
    "- Keep every detail: ages, numbers, relationship, religion, and who is "
    "asking. Do not add facts that are not there.\n"
    "- Roman Hindi (Hinglish) is a real language here. Translate it as "
    "Hinglish, not as broken English.\n"
)


def new_state(query: str, lang: str = "en",
              memory: Optional[Dict[str, str]] = None,
              history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    return {
        "query": query,
        "lang": detect_lang(query, lang),
        "query_en": "",
        "history": [m for m in (history or []) if m.get("content")][:10],
        "intent": "",
        "slots": {},
        "missing_slots": [],
        "clarification": "",
        "pivot_ok": True,
        "evidence": [],
        "verified": False,
        "retries": 0,
        "confidence": 0.0,
        "oos_redirect": False,
        "answer": "",
        "citations": [],
        "citation_sources": [],
        "provider": "",
        "tone": "simple",
        "trace": [],
        "trace_detail": [],
        "memory": dict(memory or {}),
        "doc_id": "",
    }


# Which spouse is speaking. Checked on the word before the spouse term, because
# "my husband" and "his wife" are opposites and the bare keyword cannot tell
# them apart.
_SELF_SIDE_PATTERNS = (
    # claimant side: the person is the wife/daughter complaining
    (("my husband", "my pati", "my shohar", "my बीवी", "my biwi",
      "my पति", "ನನ್ನ ಗಂಡ", "my husband has", "husband stopped",
      "husband has not", "husband refuses", "my husband left"), "claimant"),
    (("my wife", "my patni", "my hodti", "my wife has", "wife stopped",
      "wife left", "my wife refused", "ನನ್ನ ಹೆಂಡತಿ", "मेरी पत्नी"), "respondent"),
    (("my father", "my baap", "my father died", "my father has",
      "ನನ್ನ ತಂದೆ", "मेरे पिता"), "claimant"),
    (("my mother", "my maa", "my mother died", "ನನ್ನ ತಾಯಿ", "मेरी माँ"), "respondent"),
)


def _self_side(bare: str) -> str:
    """'claimant' or 'respondent' based on who the speaker is describing."""
    for phrases, side in _SELF_SIDE_PATTERNS:
        if any(p in bare for p in phrases):
            return side
    return ""


# Follow-ups that name no topic, mapped to what they are really asking. These
# are the second question of a real conversation: "how much can I ask for?"
# after a maintenance question, "can I get him removed" after a violence one.
# Without this the planner asks "what is this about?" to someone who already
# said, and it is the single most common shape of a real chat.
FOLLOW_UP_TOPIC = (
    (("how much can i ask", "how much should i ask", "how much can i get",
      "how much i can claim", "how much can be claimed", "what amount can i",
      "how much is reasonable", "what is a reasonable amount",
      "kitni maang", "कितनी मांग", "कितना", "ಎಷ್ಟು ಕೊಡಿ",
      "ಎಷ್ಟು ಹಿಂಗಿರಿ"), "maintenance"),
    (("how long does it take", "how much time", "how many months",
      "will it take", "timeline", "कितना समय", "ಎಷ್ಟು ಸಮಯ"), "divorce"),
    (("do i need a lawyer", "can i do it myself", "without a lawyer",
      "do i need a advocate", "क्या वकील", "ವಕೀಲ"), "divorce"),
    (("can i get him removed", "removed from the house", "make him leave",
      "residence order", "stay in the house", "उसे रहने दें",
      "ಮನೆಯಿಂದ ಹೊರಗೆ"), "domestic_violence"),
    (("what documents", "what papers", "which documents", "proof needed",
      "evidence", "कागज़", "ದಾಖಲೆ"), "custody"),
    (("who gets", "who will get", "who inherits", "who is entitled",
      "किसे मिलेगा", "ಯಾರಿಗೆ"), "succession"),
)


def _follow_up_topic(query_en: str) -> str:
    low = (query_en or "").lower()
    for phrases, topic in FOLLOW_UP_TOPIC:
        if any(p in low for p in phrases):
            return topic
    return ""


# "I am scared" and "I am not safe" only point at domestic violence when the
# fear is of a person. "I am scared of the court process" and "I am scared my
# husband will not pay me anything" are maintenance questions, and the DV Act is
# the wrong statute to answer them with.
_FEAR_IS_PERSONAL = (
    "not safe at home", "not safe in my", "not safe here", "not safe with",
    "i am scared at home", "i am scared at night", "i am scared to go home",
    "i am scared to tell", "i'm scared to go home", "i'm scared to tell",
    "scared of my husband", "scared of my wife", "scared of him",
    "scared of her", "afraid of my husband", "afraid of my wife",
    "afraid of him", "afraid of her", "afraid to go home", "i feel unsafe",
    "i don't feel safe", "i do not feel safe", "not safe",
    "मुझे डर है", "डर लगता है", "सुरक्षित नहीं", "नहीं लगता कि सुरक्षित",
    "ನನಗೆ ಭಯ", "ಸುರಕ್ಷಿತ", "ಭಯವಾಗುತ್ತದೆ",
)


def _fear_points_at_a_person(query_en: str) -> bool:
    """True when the expressed fear is of a person or place, not of a process."""
    low = (query_en or "").lower()
    return any(p in low for p in _FEAR_IS_PERSONAL)


def extract_slots(query_en: str) -> Dict[str, str]:
    low = (query_en or "").lower()
    slots: Dict[str, str] = {}
    sec = _SECTION_RE.search(query_en or "")
    section = (sec.group(1) or sec.group(2) or sec.group(3) or "") if sec else ""

    # An act name mentions "marriage" but says nothing about the topic —
    # "Section 13B of the Hindu Marriage Act" is a divorce question. Strip
    # act names before keyword matching so they cannot decide the topic.
    bare = _ACT_NAME_RE.sub(" ", low)

    topics = [t for t, kws in TOPIC_KEYWORDS.items()
              if any(k in bare for k in kws)]
    # Fear of a person is domestic violence even when no keyword above fires.
    # Coercive control — confinement, being watched, not allowed to leave — is
    # what s.3(a) covers, and these phrasings reached no topic at all.
    if "domestic_violence" not in topics and _fear_points_at_a_person(query_en):
        topics.append("domestic_violence")
    if topics:
        # Prefer the most specific topic: maintenance/custody beat divorce.
        for pref in ("interfaith_marriage", "maintenance", "custody",
                     "adoption", "succession", "domestic_violence",
                     "divorce", "marriage"):
            if pref in topics:
                slots["topic"] = pref
                break
    elif any(h in low for h in _SUCCESSION_HINTS):
        # People ask about inheriting in the words of the fight, not the law:
        # "my father died and my brother is taking all the ancestral land"
        # mentions no succession keyword at all, so it was being refused and
        # then asked to clarify. A death plus property is succession.
        slots["topic"] = "succession"
    else:
        follow = _follow_up_topic(query_en or "")
        if follow:
            # Routed from the shape of the question. history_aware=True stops
            # this overriding a topic the chat has already established.
            slots["topic"] = follow
            slots["topic_from_followup"] = "true"
    # A named section is the most specific signal available — let it win.
    sec_topic = _section_topic(section)
    if sec_topic:
        slots["topic"] = sec_topic

    m = _DIVORCE_TYPE_RE.search(query_en or "")
    if m:
        word = m.group(0).lower()
        if "khula" in word or "mubara" in word:
            slots["divorce_type"] = "khula"
        else:
            slots["divorce_type"] = ("mutual" if "mutual" in word or "आपसी" in word
                                     else "contested")
    for p in PARTY_WORDS:
        if p in bare:
            slots["parties"] = p
            break
    # Which side the person is on. "my husband stopped paying" means they are the
    # wife claiming; "my wife left" means the opposite. Getting this wrong makes a
    # follow-up ("what do I do now?") answer for the other spouse, so it is
    # captured as its own slot rather than left inside `parties`.
    self_side = _self_side(bare)
    if self_side:
        slots["self_side"] = self_side
    if section:
        slots["section"] = section
    return slots


def classify_intent(query_en: str, slots: Dict[str, str]) -> str:
    if slots.get("topic"):
        return slots["topic"]
    low = (query_en or "").lower()
    if any(w in low for w in ("what is", "explain", "section", "act", "law",
                              "rights", "procedure", "grounds")):
        return "general"
    return "general"


def _is_divorce_process_question(query: str) -> bool:
    """True when the person is trying to end the marriage, not living with it.

    Grounds and procedure matter only here. When someone describes harm,
    non-payment or a child's welfare, the answer is about that, and steering
    them into a mutual-vs-contested question wastes their one turn.
    """
    low = (query or "").lower()
    if any(w in low for w in ("hits me", "hit me", "beats me", "beat me",
                              "abuse", "abuses", "abused", "abusing",
                              "tortures", "slaps", "struck me", "threatens",
                              "scared to tell", "afraid of", "not safe",
                              "maintenance", "alimony", "not paying", "stops paying",
                              "has not paid", "hasn't paid", "custody",
                              "guardian", "child", "children", "daughter", "son")):
        return False
    return any(w in low for w in (
        "how do i get", "how can i get", "how to get", "process",
        "divorce", "talaq", "talak", "विवाह विच्छेद", "विच्छेद", "ವಿಚ್ಛೇದನ",
        "separate", "khula", "mutaraat", "legal separation"))


def missing_for(slots: Dict[str, str], query_en: str,
                is_followup: bool = False) -> List[str]:
    """Key slots the planner needs before guessing (T3 accept rule).

    ``is_followup`` short-circuits *first*: once the user has already been
    asked something in this session, answer with what you have. Otherwise a
    follow-up whose topic fails extraction returns ["topic"] again and the
    bot asks the same question forever.
    """
    if slots.get("section"):
        return []  # exact-section lookup is answerable as-is
    if is_followup:
        return []
    topic = slots.get("topic")
    if not topic:
        # "What is the Special Marriage Act?" names an Act, so act-name
        # stripping has (correctly) left no topic keyword — but naming an Act
        # is answerable, and asking "what is this about?" instead was the
        # single most useless reply the bot could give.
        if _ACT_NAME_RE.search(query_en or ""):
            return []
        return ["topic"]
    if topic == "divorce" and not slots.get("divorce_type"):
        # Only worth asking when the question is actually about getting a divorce.
        # "My husband hits me" is a domestic-violence matter that merely sounds
        # like a marriage dispute, and asking a frightened person whether her
        # divorce is mutual or contested was both useless and badly timed.
        if _is_divorce_process_question(query_en or ""):
            return ["divorce_type"]
        return []
    words = (query_en or "").split()
    if topic in ("divorce", "maintenance", "custody") \
            and not slots.get("parties") and len(words) < 6:
        return ["parties"]
    return []


# Asking "is this mutual or contested?" for a bare "how do I get a divorce" is
# legitimate — the two routes are genuinely different. But it costs the user a
# whole turn, and a Kannada or Hindi speaker who asked the simplest possible
# question got nothing but the follow-up. So the topic is answered *and* the
# disambiguation is offered, rather than one replacing the other.
_CLARIFY_WITH_ANSWER_NODES = ("planner", "tools", "reason", "verifier")


def should_answer_anyway(missing: List[str]) -> bool:
    """Answer with what we have rather than only asking.

    Only for the questions where the answer does not actually change: how much
    maintenance, how a protection order works. Never for "which act applies",
    which is the one case where asking is better than guessing.
    """
    return bool(missing) and set(missing) <= {"divorce_type", "parties"}


CLARIFY_TEMPLATES = {
    # Short per-slot questions; only the actually-missing slots are asked.
    "en": {"topic": "What is this about — divorce, maintenance, custody, "
                    "adoption, succession, or domestic violence?",
           "divorce_type": "Is this a mutual-consent divorce or a contested one?",
           "parties": "Who is asking — husband, wife, or guardian?"},
    "hi": {"topic": "यह किस बारे में है — तलाक, भरण-पोषण, अभिरक्षा, "
                    "गोद लेना, उत्तराधिकार या घरेलू हिंसा?",
           "divorce_type": "क्या यह आपसी सहमति से तलाक है या विवादित तलाक?",
           "parties": "कौन पूछ रहा है — पति, पत्नी या अभिभावक?"},
    "kn": {"topic": "ಇದು ಯಾವುದರ ಬಗ್ಗೆ — ವಿಚ್ಛೇದನ, ಜೀವನಾಂಶ, ಪಾಲನೆ, "
                    "ದತ್ತು, ಉತ್ತರಾಧಿಕಾರ ಅಥವಾ ಕೌಟುಂಬಿಕ ಹಿಂಸೆ?",
           "divorce_type": "ಇದು ಪರಸ್ಪರ ಒಪ್ಪಿಗೆಯ ವಿಚ್ಛೇದನವೇ ಅಥವಾ ವಿವಾದಿತ ವಿಚ್ಛೇದನವೇ?",
           "parties": "ಕೇಳುತ್ತಿರುವವರು ಯಾರು — ಗಂಡ, ಹೆಂಡತಿ ಅಥವಾ ಪಾಲಕರು?"},
}

_CLARIFY_LEAD = {
    "en": "To guide you correctly — ",
    "hi": "सही मार्गदर्शन के लिए — ",
    "kn": "ಸರಿಯಾಗಿ ಮಾರ್ಗದರ್ಶನ ನೀಡಲು — ",
}


def clarification_question(missing: List[str], lang: str) -> str:
    """Build the follow-up question in the user's own language.

    Every template is already a full, standalone question. Do not lowercase
    the first character: Hindi and Kannada have no letter case, so doing that
    only produces broken grammar ("...तलाक क्या है?").
    """
    bank = CLARIFY_TEMPLATES.get(lang, CLARIFY_TEMPLATES["en"])
    lead = _CLARIFY_LEAD.get(lang, _CLARIFY_LEAD["en"])
    asked = [bank.get(m, m) for m in missing[:2]]
    if len(asked) == 1:
        return lead + _sentence_case(asked[0], lang)
    return lead + " ".join("(%d) %s" % (i + 1, q)
                           for i, q in enumerate(asked))


def _sentence_case(text: str, lang: str) -> str:
    """Capitalise an English question that now follows a lead-in.

    Only English has letter case, so this is a no-op for hi/kn — which is
    exactly the point: lowercasing their first character corrupts them.
    """
    if lang != "en" or not text:
        return text
    return text[0].upper() + text[1:]


# ---------------------------------------------------------------------------
# LLM layer: OpenRouter primary, Groq for translation, OpenCode Zen last.
# ---------------------------------------------------------------------------

def _post_json(url: str, headers: Dict[str, str], payload: Dict[str, Any],
               timeout: float = 45.0) -> Dict[str, Any]:
    import httpx  # lazy: keeps bare checkouts importable

    resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def opencode_complete(messages: List[Dict[str, str]],
                      http_post: Optional[Callable] = None,
                      timeout: float = 45.0,
                      max_tokens: Optional[int] = None) -> Tuple[str, str]:
    """Call OpenCode Zen's free tier. Returns (text, provider).

    Used as the last-resort fallback so a user still gets an answer when
    Groq and OpenRouter are both rate-limited. Zen returns a
    ``reasoning_content`` field next to the answer; it must never be shown.
    """
    key = os.environ.get("OPENCODE_API_KEY", "")
    if not key and http_post is None:
        raise RuntimeError("no OPENCODE_API_KEY")
    post = http_post or _post_json
    data = post(
        OPENCODE_URL,
        {"Authorization": "Bearer " + key,
         "Content-Type": "application/json",
         "User-Agent": OPENCODE_UA},
        {"model": OPENCODE_MODEL, "messages": messages,
         "temperature": 0.2,
         "max_tokens": MAX_TOKENS_LONG if max_tokens is None else max_tokens},
    )
    message = data["choices"][0]["message"] or {}
    text = (message.get("content") or "").strip()
    # Drop the model's scratchpad if it leaked into content.
    text = strip_reasoning_leak(text)
    if not text:
        raise RuntimeError("opencode returned an empty message")
    logger.info("agent llm provider=opencode model=%s", OPENCODE_MODEL)
    return text, "opencode:" + OPENCODE_MODEL


# gpt-oss spends part of its budget reasoning out loud before it answers. 1500
# tokens was not enough: the model finished its reasoning and returned an empty
# content field, which the caller used verbatim as the answer.
MAX_TOKENS = int(os.environ.get("LAWSAATHI_MAX_TOKENS", "6000"))


# Provider circuit breaker.
#
# When a key is exhausted or rate-limited, every call used to walk the whole
# chain — Groq's 429, then OpenRouter's 402, then a 45s OpenCode timeout. Six
# model calls per run turned into minutes of waiting for an error, and the user
# saw nothing while it happened. A provider that has just failed is skipped for
# a cooldown, so the next call goes straight to the one that still works.
_PROVIDER_FAILURES: Dict[str, float] = {}
_PROVIDER_COOLDOWN = float(os.environ.get("LAWSAATHI_PROVIDER_COOLDOWN", "60"))


def _provider_available(name: str) -> bool:
    until = _PROVIDER_FAILURES.get(name, 0.0)
    if until <= time.monotonic():
        _PROVIDER_FAILURES.pop(name, None)
        return True
    return False


def _mark_failed(name: str, error: Exception) -> None:
    _PROVIDER_FAILURES[name] = time.monotonic() + _PROVIDER_COOLDOWN
    # 429 and 402 mean the key is spent; there is no point retrying for the
    # length of a normal cooldown.
    status = getattr(getattr(error, "response", None), "status_code", None)
    cooldown = _PROVIDER_COOLDOWN
    if status in (401, 402, 403) or "402" in str(error) or "401" in str(error):
        cooldown = _PROVIDER_COOLDOWN * 10
    _PROVIDER_FAILURES[name] = time.monotonic() + cooldown
    logger.warning("provider %s in cooldown for %.0fs (%r)", name, cooldown, error)


def _mark_healthy(name: str) -> None:
    _PROVIDER_FAILURES.pop(name, None)


def _message_text(data: Dict[str, Any]) -> str:
    """Pull the answer out of an OpenAI-shaped response.

    Reasoning models put their scratchpad in `reasoning` / `reasoning_content`
    and the answer in `content`. Only `content` is ever shown to a user.
    """
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    text = (message.get("content") or "").strip()
    if not text:
        # Some gateways return the answer under a different key when content is
        # empty; take it rather than showing the user a blank answer.
        for key in ("output_text", "text", "response"):
            alt = message.get(key) or data.get(key)
            if isinstance(alt, str) and alt.strip():
                return alt.strip()
    return text


def _groq_models() -> List[str]:
    """Groq models to try, in order, on one API key.

    Groq meters tokens per day *per model*. On 2026-10-14 `gpt-oss-120b` hit
    199,502 / 200,000 TPD, and because the chain went straight from "this
    model failed" to "try OpenRouter", one model's daily allowance took the
    whole product offline: OpenRouter had $0 credit and OpenCode Zen's free
    tier refuses non-OpenCode callers, so every question in production fell
    back to the template answer — raw statute text, no explanation.

    The other chat models on the same key have their own separate TPD
    allowance, so trying them in turn is the cheapest available fix: same
    key, same provider, no new vendor. gpt-oss-120b stays first because it is
    the one that writes the best grounded legal prose.

    The default is in code, not in the environment, on purpose: adding
    GROQ_FALLBACK_MODELS to render.yaml only reaches production when someone
    applies the blueprint, and this outage could not wait for that. Deploying
    this fix with the list still unset is the whole point of it.
    """
    raw = os.environ.get("GROQ_FALLBACK_MODELS", GROQ_FALLBACK_MODELS_DEFAULT)
    models = [m.strip() for m in raw.split(",") if m.strip()]
    return [GROQ_MODEL] + [m for m in models if m != GROQ_MODEL]


def chat_complete(messages: List[Dict[str, str]],
                  http_post: Optional[Callable] = None,
                  timeout: float = 45.0,
                  max_tokens: Optional[int] = None) -> Tuple[str, str]:
    """Chat with fallbacks: Groq (several models) -> OpenRouter -> OpenCode Zen.

    Groq is primary per ADR-0002. The order used to be reversed, which meant the
    small OpenRouter model answered almost every question and the good model was
    only reached when OpenRouter happened to be down.

    Within Groq the models are tried in turn, because the daily token quota is
    per model and spending one model's allowance should not mean the user gets
    nothing at all. See ``_groq_models``.

    Returns (text, provider). ``http_post`` is a test seam:
    ``fn(url, headers, payload) -> dict`` in the OpenAI-chat-completions shape.
    Raises RuntimeError when no backend is available.
    """
    post = http_post or _post_json
    groq_key = os.environ.get("GROQ_API_KEY", "")
    or_key = os.environ.get("OPENROUTER_API_KEY", "")
    budget = MAX_TOKENS_LONG if max_tokens is None else max_tokens
    last_error: Optional[Exception] = None
    if (groq_key or http_post is not None) and _provider_available("groq"):
        for model in _groq_models():
            try:
                data = post(
                    GROQ_URL,
                    {"Authorization": "Bearer " + groq_key,
                     "Content-Type": "application/json"},
                    {"model": model, "messages": messages,
                     "temperature": 0.2, "max_tokens": budget},
                )
                text = _message_text(data)
                if not text:
                    # An empty completion is a failure, not an answer: falling through
                    # beats showing the user a blank reply.
                    raise RuntimeError("groq %s returned no content" % model)
                logger.info("agent llm provider=groq model=%s", model)
                _mark_healthy("groq")
                return text, "groq:" + model
            except Exception as e:  # noqa: BLE001 — fallback must catch all
                last_error = e
                # Deliberately NOT _mark_failed("groq"): the key is fine, this
                # one model's daily quota is spent. Marking the whole provider
                # down would park it in cooldown and cost the next run the
                # models that still have quota.
                logger.warning("agent groq %s failed (%r); trying next model",
                               model, e)
        _mark_failed("groq", last_error)
        logger.warning("agent every groq model failed; trying openrouter")
    if (or_key or http_post is not None) and _provider_available("openrouter"):
        try:
            data = post(
                OPENROUTER_URL + "/chat/completions",
                {"Authorization": "Bearer " + or_key,
                 "Content-Type": "application/json",
                 "HTTP-Referer": "https://github.com/Kamal-Nayan-Kumar/law_saathi",
                 "X-Title": "LawSaathi"},
                {"model": OPENROUTER_MODEL, "messages": messages,
                 "temperature": 0.2, "max_tokens": budget},
            )
            text = _message_text(data)
            if not text:
                raise RuntimeError("openrouter returned no content")
            logger.info("agent llm provider=openrouter model=%s", OPENROUTER_MODEL)
            _mark_healthy("openrouter")
            return text, "openrouter:" + OPENROUTER_MODEL
        except Exception as e:  # noqa: BLE001 — fallback must catch all
            last_error = e
            _mark_failed("openrouter", e)
            logger.warning("agent openrouter failed (%r); trying opencode", e)
    # Free last resort: a rate-limited Groq/OpenRouter should not end the chat.
    if _provider_available("opencode"):
        try:
            text, provider = opencode_complete(messages, http_post=post,
                                               timeout=timeout,
                                               max_tokens=max_tokens)
            _mark_healthy("opencode")
            return text, provider
        except Exception as e:  # noqa: BLE001 — caller sees the last error
            last_error = e
            _mark_failed("opencode", e)
            logger.warning("agent opencode failed (%r)", e)
    raise RuntimeError("no LLM backend (OPENROUTER_API_KEY/GROQ_API_KEY/"
                       "OPENCODE_API_KEY empty; pass http_post in tests) :: %r"
                       % (last_error,))


TRACE_MODES = ("off", "errors", "all")


def trace_mode() -> str:
    """How much to send to LangSmith: off | errors | all.

    LangSmith's free tier allows only 5k base traces/month, and a single
    question costs ~6 (five nodes plus LLM calls). Tracing every question
    would run dry at ~700 questions/month, so tracing is opt-in via
    LAWSAATHI_TRACE. "errors" is the useful default: it spends the
    allowance on runs that actually went wrong.
    """
    raw = (os.environ.get("LAWSAATHI_TRACE", "") or "").strip().lower()
    return raw if raw in TRACE_MODES else "off"


def should_trace(state: Dict[str, Any]) -> bool:
    """Whether this finished run is worth spending a trace on."""
    mode = trace_mode()
    if mode == "off":
        return False
    if mode == "all":
        return True
    # mode == "errors": the runs you actually need to see are the ones with
    # no verified evidence, no answer, or a low-confidence answer.
    if not state.get("answer"):
        return True
    if state.get("confidence", 1.0) < 0.7:
        return True
    return not state.get("verified")


def translate_complete(messages: List[Dict[str, str]],
                       http_post: Optional[Callable] = None,
                       timeout: float = 45.0,
                       max_tokens: Optional[int] = None) -> Tuple[str, str]:
    """Translate using Groq only, falling back to the shared chat path.

    Groq's model handles Hindi and Kannada cleanly; the OpenRouter default was
    weak in both and produced garbled, repeated text. Translation therefore
    tries Groq first regardless of the order `chat_complete` uses.
    """
    if (os.environ.get("GROQ_API_KEY", "") or http_post is not None) \
            and _provider_available("groq"):
        post = http_post or _post_json
        budget = MAX_TOKENS_LONG if max_tokens is None else max_tokens
        for model in _groq_models():
            try:
                data = post(
                    GROQ_URL,
                    {"Authorization": "Bearer " + os.environ.get("GROQ_API_KEY", ""),
                     "Content-Type": "application/json"},
                    {"model": model, "messages": messages,
                     "temperature": 0.2, "max_tokens": budget},
                )
                text = _message_text(data)
                if not text:
                    raise RuntimeError("groq %s returned no content" % model)
                logger.info("agent translate provider=groq model=%s", model)
                _mark_healthy("groq")
                return text, "groq:" + model
            except Exception as e:  # noqa: BLE001 — caller falls back
                # Same reasoning as chat_complete: one model's spent quota is
                # not the provider being down. Translation is the step the
                # whole non-English answer depends on, so it must not be the
                # one that gives up first.
                logger.warning("agent groq %s translate failed (%r)", model, e)
        _mark_failed("groq", RuntimeError("every groq model failed translate"))
    return chat_complete(messages, http_post=http_post, timeout=timeout,
                         max_tokens=max_tokens)


def _maybe_trace(name: str) -> Callable:
    """LangSmith traceable decorator when tracing is on; else no-op.

    Node-level tracing is expensive (one trace per node per question), so it
    only turns on in "all" mode. "errors" mode traces the whole run at the
    end instead, via trace_run().
    """
    try:
        if trace_mode() != "all":
            raise ImportError("node tracing needs LAWSAATHI_TRACE=all")
        if not os.environ.get("LANGCHAIN_API_KEY", ""):
            raise ImportError("no langsmith key")
        from langsmith import traceable  # type: ignore
        return traceable(name="lawsaathi:" + name, project_name=os.environ.get(
            "LANGCHAIN_PROJECT", "lawsathi"))
    except Exception:
        def deco(fn: Callable) -> Callable:
            return fn
        return deco


def trace_run(state: Dict[str, Any]) -> None:
    """Send one summary trace for a finished run, if it is worth one.

    Best-effort: any LangSmith failure is swallowed so tracing can never
    break a user's answer.
    """
    if not should_trace(state):
        return
    try:
        if not os.environ.get("LANGCHAIN_API_KEY", ""):
            return
        from langsmith import Client  # type: ignore
        client = Client()
        client.create_run(
            name="lawsaathi:run",
            project_name=os.environ.get("LANGCHAIN_PROJECT", "lawsathi"),
            run_type="chain",
            inputs={"query": str(state.get("query", ""))[:500],
                    "lang": state.get("lang", ""),
                    "query_en": str(state.get("query_en", ""))[:500]},
            outputs={"answer": str(state.get("answer", ""))[:2000],
                     "citations": state.get("citations", []),
                     "provider": state.get("provider", ""),
                     "confidence": state.get("confidence", 0.0),
                     "verified": state.get("verified", False),
                     "retries": state.get("retries", 0),
                     "oos_redirect": state.get("oos_redirect", False),
                     "missing_slots": state.get("missing_slots", []),
                     "trace": state.get("trace", []),
                     "trace_detail": state.get("trace_detail", [])},
            # LangSmith's schema types `error` as a string, not a boolean;
            # passing True gets the whole run rejected with HTTP 422.
            error=(state.get("trace_error") and "run raised an exception")
                   or None,
        )
    except Exception as e:  # noqa: BLE001 — tracing must never break chat
        logger.warning("agent trace_run failed (%r)", e)


# ---------------------------------------------------------------------------
# Nodes — each takes and returns the shared state dict, appending to trace.
# ``trace`` stays a plain node-name list (tests + API contract);
# ``trace_detail`` carries one human-readable line per step for the UI.
# ---------------------------------------------------------------------------

LANG_NAMES = {"en": "English", "hi": "Hindi", "kn": "Kannada"}

# The name of each language, written *in* that language and in the other two.
# `LANGUAGE_NAMES[lang][reader_lang]` — a Hindi reader is told "हिंदी", not
# "Hindi", for the same reason the answer is not in English.
LANGUAGE_NAMES = {
    "en": {"en": "English", "hi": "अंग्रेज़ी", "kn": "ಇಂಗ್ಲಿಷ್"},
    "hi": {"en": "Hindi", "hi": "हिंदी", "kn": "ಹಿಂದಿ"},
    "kn": {"en": "Kannada", "hi": "कन्नड़", "kn": "ಕನ್ನಡ"},
}

# Topic, divorce-type and party names in the reader's language. `slots` holds the
# English identifier ("domestic_violence") because that is what the maps and the
# retrieval are keyed on; printing it to a Hindi reader is the defect this table
# fixes.
TOPIC_LOCAL = {
    "divorce": {"en": "divorce", "hi": "तलाक", "kn": "ವಿಚ್ಛೇದನ"},
    "maintenance": {"en": "maintenance", "hi": "भरण-पोषण", "kn": "ಜೀವನಾಂಶ"},
    "custody": {"en": "custody", "hi": "अभिरक्षा", "kn": "ಪಾಲನೆ"},
    "adoption": {"en": "adoption", "hi": "गोद लेना", "kn": "ದತ್ತು"},
    "succession": {"en": "succession", "hi": "उत्तराधिकार", "kn": "ಉತ್ತರಾಧಿಕಾರ"},
    "domestic_violence": {"en": "domestic violence", "hi": "घरेलू हिंसा",
                         "kn": "ಕೌಟುಂಬಿಕ ಹಿಂಸೆ"},
    "marriage": {"en": "marriage", "hi": "विवाह", "kn": "ಮದುವೆ"},
    "dowry": {"en": "dowry", "hi": "दहेज", "kn": "ಸंಪತ್ತು ಕೋಲಿಕೆ"},
    "interfaith_marriage": {"en": "inter-faith marriage", "hi": "अंतर-धार्मिक विवाह",
                            "kn": "ಬೇರೆ ಧರ್ಮದ ಮದುವೆ"},
    "general": {"en": "a general question", "hi": "सामान्य प्रश्न",
                "kn": "ಸಾಮಾನ್ಯ ಪ್ರಶ್ನೆ"},
}

DIVORCE_TYPE_LOCAL = {
    "mutual": {"en": "mutual consent", "hi": "आपसी सहमति", "kn": "ಪರಸ್ಪರ ಒಪ್ಪಿಗೆ"},
    "contested": {"en": "contested", "hi": "विवादित", "kn": "ವಿವಾದಿತ"},
    "khula": {"en": "khula", "hi": "खुला", "kn": "ಖುಲಾ"},
}

PARTY_LOCAL = {
    "husband": {"en": "the husband", "hi": "पति", "kn": "ಗಂಡ"},
    "wife": {"en": "the wife", "hi": "पत्नी", "kn": "ಹೆಂಡತಿ"},
    "spouse": {"en": "the spouse", "hi": "जीवनसाथी", "kn": "ಜೀವನಸಂಗಾತಿ"},
    "child": {"en": "the child", "hi": "बच्चा", "kn": "ಮಗು"},
    "minor": {"en": "the minor", "hi": "नाबालिग", "kn": "ಅಲ్పವಯಸ್ಸಿನವನು"},
    "father": {"en": "the father", "hi": "पिता", "kn": "ತಂದೆ"},
    "mother": {"en": "the mother", "hi": "माता", "kn": "ತಾಯಿ"},
    "widow": {"en": "the widow", "hi": "विधवा", "kn": "ವಿಧವೆ"},
    "widower": {"en": "the widower", "hi": "विधुर", "kn": "ವಿಧುರ"},
}


def _local(table: Dict[str, Dict[str, str]], value: str, lang: str) -> str:
    """Reader-language name for a stored English identifier."""
    bank = table.get(value or "")
    if not bank:
        return value
    return bank.get(lang) or bank.get("en") or value


def _phrase(bank: Dict[str, str], lang: str) -> str:
    """Reader-language text for a small fixed bank, e.g. "no clear topic yet"."""
    return bank.get(lang) or bank.get("en") or ""


def _plural(lang: str, n: int) -> str:
    """The plural suffix to append, per language.

    English is the only one of the three that marks a plural with a suffix.
    "3 ವಿಭಾಗs." in Kannada and "2 और धाराs." in Hindi read as a stray Latin
    letter in the middle of the sentence — which is the same defect as leaving
    `court` in Latin letters inside Devanagari, one letter at a time.
    """
    if lang != "en":
        return ""
    return "" if n == 1 else "s"


# Every line the Thinking panel shows, in the reader's language.
#
# These are template ids, not prose: `_add_trace(state, node, key, **fields)`
# renders the key for `state["lang"]`. A key with no translation falls back to
# English, which is the old behaviour — so the cost of adding a trace line and
# forgetting its translation is the old defect, not a blank panel.
#
# Act names, section numbers, tool names and the queries the agent actually ran
# stay as they are, in every language: they are the citation, and a translated
# citation cannot be checked.
TRACE_TEXT: Dict[str, Dict[str, str]] = {
    "ctx_resolved": {
        "en": "Read the conversation and expanded your follow-up “{q}” into a "
              "full question.",
        "hi": "बातचीत पढ़ी और आपके संक्षिप्त सवाल “{q}” को पूरा प्रश्न बना दिया।",
        "kn": "ಸಂಭಾಷಣೆಯನ್ನು ಓದಿ ನಿಮ್ಮ ಸಂಕ್ಷಿಪ್ತ ಪ್ರಶ್ನೆ “{q}” ಅನ್ನು ಪೂರ್ಣ "
              "ಪ್ರಶ್ನೆಯಾಗಿ ವಿಸ್ತರಿಸಿದೆ.",
    },
    "ctx_retry": {
        "en": "Read the conversation. Your follow-up needed a second attempt; "
              "it became “{q}”.",
        "hi": "बातचीत पढ़ी। आपके संक्षिप्त सवाल को दूसरी कोशिश चाहिए हुई; वह "
              "“{q}” बना।",
        "kn": "ಸಂಭಾಷಣೆಯನ್ನು ಓದಿದೆ. ನಿಮ್ಮ ಸಂಕ್ಷಿಪ್ತ ಪ್ರಶ್ನೆಗೆ ಎರಡನೇ ಪ್ರಯತ್ನ "
              "ಬೇಕಾಯಿತು; ಅದು “{q}” ಆಯಿತು.",
    },
    "ctx_standalone": {
        "en": "Read the conversation; your message stands on its own.",
        "hi": "बातचीत पढ़ी; आपका संदेश अपने आप पूरा है।",
        "kn": "ಸಂಭಾಷಣೆಯನ್ನು ಓದಿದೆ; ನಿಮ್ಮ ಸಂದೇಶವು ತನkVಾಗಿಯೇ ಪೂರ್ಣವಾಗಿದೆ.",
    },
    "mem_topic": {
        "en": "Remembered from an earlier session that you were asking about "
              "{topic}.",
        "hi": "पिछली बार की बातचीत से याद है कि आप {topic} के बारे में पूछ रहे "
              "थे।",
        "kn": "ಹಿಂದಿನ ಘಟನೆಯಿಂದ ನೆನಪಿದೆ — ನೀವು {topic} ಬಗ್ಗೆ ಕೇಳುತ್ತಿದ್ದೀರಿ.",
    },
    "mem_side": {
        "en": "Remembered which side of the dispute you are on from an earlier "
              "session.",
        "hi": "पिछली बार से याद है कि आप इस मामले में किस तरफ हैं।",
        "kn": "ಹಿಂದಿನ ಘಟನೆಯಿಂದ ನಿಮ್ಮ ಸ್ಥಾನ ಧ್ಯಾನದಲ್ಲಿದೆ.",
    },
    "intent_summary": {
        "en": "Detected {found}, language {langname}.",
        "hi": "{found} पहचाना गया, भाषा {langname}।",
        "kn": "{found} ಗುರುತಿಸಲಾಗಿದೆ, ಭಾಷೆ {langname}.",
    },
    "planner_pivot_failed": {
        "en": "The English pivot did not come back, so no topic could be read "
              "from the question. Answering anyway rather than asking what they "
              "were asking about.",
        "hi": "अंग्रेज़ी अनुवाद वापस नहीं आया, इसलिए प्रश्न से विषय नहीं पढ़ा जा "
              "सका। फिर भी उत्तर दिया जा रहा है — आपसे दोबारा पूछने के बजाय।",
        "kn": "ಇಂಗ್ಲಿಷ್ ಅನುವಾದ ಬಂದಿಲ್ಲ, ಆದ್ದರಿಂದ ಪ್ರಶ್ನೆಯಿಂದ ವಿಷಯವನ್ನು "
              "ಓದಲಾಗಲಿಲ್ಲ. ನೀವು ಏನು ಕೇಳಿದ್ದೀರಿ ಎಂದು ಮತ್ತೆ ಕೇಳುವ ಬದಲಿಗೆ, "
              "ಉತ್ತರಿಸಲಾಗುವಿದೆ.",
    },
    "planner_oos": {
        "en": "Outside family-law scope — saying so instead of answering or "
              "asking.",
        "hi": "यह पारिवारिक कानून के दायरे से बाहर है — उत्तर देने या पूछने के "
              "बजाय यही बताया जा रहा है।",
        "kn": "ಇದು ಕುಟುಂಬ ಕಾನೂನಿನ ವ್ಯಾಪ್ತಿಯಿಂದ ಹೊರಗಿದೆ — ಉತ್ತರಿಸುವುದು ಅಥವಾ "
              "ಕೇಳುವುದರ ಬದಲಿಗೆ ಅದನ್ನೇ ಹೇಳಲಾಗುವಿದೆ.",
    },
    "planner_ask": {
        "en": "Still need: {missing} — asking you instead of guessing.",
        "hi": "यह चाहिए: {missing} — अंदाज़ा लगाने के बजाय आपसे पूछा जा रहा है।",
        "kn": "ಇದು ಬೇಕು: {missing} — ಊಹಿಸುವುದರ ಬದಲಿಗೆ ನಿಮ್ಮನ್ನು ಕೇಳಲಾಗುವಿದೆ.",
    },
    "planner_answer_and_ask": {
        "en": "Missing {missing}, but answering anyway and asking at the end "
              "rather than making you wait.",
        "hi": "{missing} निर्णय नहीं हो सका, फिर भी उत्तर दिया जा रहा है और आगे "
              "एक प्रश्न रखा गया है — आपको इंतज़ार नहीं करवाना।",
        "kn": "{missing} ಇಲ್ಲ, ಆದರೂ ಉತ್ತರಿಸಿ ಕೊನೆಯಲ್ಲಿ ಒಂದು ಪ್ರಶ್ನೆ "
              "ಕೇಳಲಾಗುವುದು — ನಿಮ್ಮನ್ನು ಕಾಯಬೇಕಾಗಿಲ್ಲ.",
    },
    "planner_model_plan": {
        "en": "Chose {act}. {why} Plan: {steps}",
        "hi": "{act} चुना। {why} योजना: {steps}",
        "kn": "{act} ಆಯ್ಕೆ. {why} ಯೋಜನೆ: {steps}",
    },
    "planner_fixed_plan": {
        "en": "No planner model available — fixed plan: {steps}",
        "hi": "योजना बनाने वाला मॉडल उपलब्ध नहीं है — तय योजना: {steps}",
        "kn": "ಯೋಜನೆ ಮಾಡುವ ಮಾದರಿ ಲಭ್ಯವಿಲ್ಲ — ನಿಗದಿತ ಯೋಜನೆ: {steps}",
    },
    "planner_replan": {
        "en": "The Acts did not have an answer — re-planning: {steps}",
        "hi": "अधिनियमों में उत्तर नहीं मिला — नई योजना: {steps}",
        "kn": "ಕಾಯ್ದೆಗಳಲ್ಲಿ ಉತ್ತರ ಸಿಕ್ಕಿಲ್ಲ — ಹೊಸ ಯೋಜನೆ: {steps}",
    },
    "tools_web": {
        "en": 'web_search "{q}" → {n} web result{plural}.',
        "hi": 'web_search "{q}" → {n} वेब परिणाम।',
        "kn": 'web_search "{q}" → {n} ಜಾಲ ಪರಿಣಾಮ.',
    },
    "tools_web_fail": {
        "en": 'web_search "{q}" unavailable ({err}).',
        "hi": 'web_search "{q}" उपलब्ध नहीं ({err})।',
        "kn": 'web_search "{q}" ಲಭ್ಯವಿಲ್ಲ ({err}).',
    },
    "tools_sections": {
        "en": '{tool} "{q}" → {n} section{plural} from {act}.',
        "hi": '{tool} "{q}" → {act} से {n} धारा।',
        "kn": '{tool} "{q}" → {act} ಇಂದ {n} ವಿಭಾಗ.',
    },
    "tools_sections_no_act": {
        "en": '{tool} "{q}" → {n} section{plural}.',
        "hi": '{tool} "{q}" → {n} धारा।',
        "kn": '{tool} "{q}" → {n} ವಿಭಾಗ.',
    },
    "tools_nothing_new": {
        "en": '{tool} "{q}" → nothing new.',
        "hi": '{tool} "{q}" → कुछ नया नहीं।',
        "kn": '{tool} "{q}" → ಹೊಸದು ಏನೂ ಇಲ್ಲ.',
    },
    "tools_retrieval_failed": {
        "en": '{tool} "{q}" failed ({err}).',
        "hi": '{tool} "{q}" विफल ({err})।',
        "kn": '{tool} "{q}" ವಿಫಲವಾಯಿತು ({err}).',
    },
    "tools_skipped_bill": {
        "en": "Skipped {n} passage{plural} that is not enacted law (a Bill or a "
              "draft). It cannot be applied by a court.",
        "hi": "{n} अनुच्छेद छोड़े गए जो लागू होने वाला कानून नहीं है (बिल या "
              "मसौदा)। कोई अदालत इन्हें लागू नहीं कर सकती।",
        "kn": "{n} ಭಾಗ ಬದಲಾಗಿದೆ — ಇವು ಜಾರಿಯಾದ ಕಾಯ್ದೆ ಅಲ್ಲ (ಬಿಲ್ಲು ಅಥವಾ "
              "ಕರಡು). ಯಾವ ನ್ಯಾಯಾಲಯವೂ ಇವನ್ನು ಅನ್ವಯಿಸುವುದಿಲ್ಲ.",
    },
    "tools_no_evidence": {
        "en": "No evidence from any tool — the verifier will decide.",
        "hi": "किसी भी साधन से कोई प्रमाण नहीं मिला — जाँचकर्ता तय करेगा।",
        "kn": "ಯಾವುದೇ ಸಾಧನದಿಂದ ಪುರಾವೆ ಸಿಗಲಿಲ್ಲ — ಪರಿಶೀಲಕನು ನಿರ್ಧರಿಸುತ್ತಾನೆ.",
    },
    "tools_native": {
        "en": "Also searched your own words (“{q}”) — {n} more section{plural}.",
        "hi": "आपके अपने शब्दों (“{q}”) से भी खोज की — {n} और धारा।",
        "kn": "ನಿಮ್ಮನ್ನೇ ಪದಗಳಿಂದ (“{q}”) ಅನ್ನು ಹುಡುಕಿದೆ — {n} ಇನ್ನಷ್ಟು "
              "ವಿಭಾಗ.",
    },
    "tools_amendment": {
        "en": "Added the amendment notice for this Act, because the "
              "consolidated text is out of date.",
        "hi": "इस अधिनियम की संशोधन सूचना जोड़ी गई, क्योंकि एकीकृत पाठ पुराना "
              "है।",
        "kn": "ಈ ಕಾಯ್ದೆಯ ತಿದ್ದುಪಡಿ ಸೂಚನೆಯನ್ನು ಸೇರಿಸಲಾಗಿದೆ, ಏಕೀಕೃತ ಪಠ್ಯ "
              "ಹಳೆಯದಾಗಿರುವುದರಿಂದ.",
    },
    "verifier_grounded": {
        "en": "Checked the draft against the passages — {reason}. Confidence "
              "{conf}.",
        "hi": "मसौदे को अनुच्छेदों से मिलाया — {reason}। विश्वास {conf}।",
        "kn": "ಕರಡನ್ನು ಭಾಗಗಳೊಂದಿಗೆ ಹೊಂದಿಸಿ — {reason}. ವಿಶ್ವಾಸ {conf}.",
    },
    "verifier_retry": {
        "en": "Rejected the draft — {reason} Searching again with better "
              "queries (retry {n}/{max}).",
        "hi": "मसौदा अस्वीकृत — {reason} बेहतर प्रश्नों से दोबारा खोज ({n}/{max})।",
        "kn": "ಕರಡು ತಿರಸ್ಕೃತ — {reason} ಉತ್ತಮ ಪ್ರಶ್ನೆಗಳಿಂದ ಮತ್ತೆ ಹುಡುಕು "
              "({n}/{max}).",
    },
    "verifier_no_retries": {
        "en": "Rejected the draft — {reason} Out of retries, so the answer "
              "carries a caution.",
        "hi": "मसौदा अस्वीकृत — {reason} कोशिशें खत्म, इसलिए उत्तर में सावधानी "
              "दी गई है।",
        "kn": "ಕರಡು ತಿರಸ್ಕೃತ — {reason} ಪ್ರಯತ್ನಗಳು ಮುಗಿದವು, ಆದ್ದರಿಂದ "
              "ಉತ್ತರದಲ್ಲಿ ಎಚ್ಚರಿಕೆ ಇದೆ.",
    },
    "verifier_threshold_ok": {
        "en": "Citations cover the answer — confidence {conf}.",
        "hi": "उत्तर के हर हिस्से का संदर्भ मिला — विश्वास {conf}।",
        "kn": "ಉತ್ತರದ ಪ್ರತಿ ಭಾಗಕ್ಕೂ ಉಲ್ಲೇಖ ಸಿಕ್ಕಿದೆ — ವಿಶ್ವಾಸ {conf}.",
    },
    "verifier_thin": {
        "en": "Evidence too thin — broadening the search (retry {n}/{max}).",
        "hi": "प्रमाण बहुत कम — खोज को व्यापक किया जा रहा है ({n}/{max})।",
        "kn": "ಪುರಾವೆ ತುಂಬಾ ಕಡಿಮೆ — ಹುಡುಕಾಟವನ್ನು ವಿಸ್ತರಿಸಲಾಗುತ್ತಿದೆ "
              "({n}/{max}).",
    },
    "verifier_thin_out": {
        "en": "Still thin after {n} retries — answering with a caution.",
        "hi": "{n} कोशिशों के बाद भी कम — सावधानी के साथ उत्तर दिया जा रहा है।",
        "kn": "{n} ಪ್ರಯತ್ನಗಳ ನಂತರವೂ ಕಡಿಮೆ — ಎಚ್ಚರಿಕೆಯೊಂದಿಗೆ ಉತ್ತರಿಸಲಾಗುವಿದು.",
    },
    "verifier_default_reason": {
        "en": "every claim traces to a passage",
        "hi": "हर बात का संदर्भ किसी अनुच्छेद में मिला",
        "kn": "ಪ್ರತಿ ಹೇಳಿಕೆಗೂ ಒಂದು ಭಾಗದಲ್ಲಿ ಉಲ್ಲೇಖ ಸಿಕ್ಕಿದೆ",
    },
    "reason_drafted": {
        "en": "Drafted a {n}-character explanation of {m} passage{plural}, ready to "
              "be checked against them.",
        "hi": "{m} अनुभाग की {n}-अक्षर की व्याख्या लिखी, जाँच के लिए तैयार।",
        "kn": "{m} ಭಾಗದ {n}-ಅಕ್ಷರದ ವಿವರಣೆ ಬರೆಯಲಾಗಿದೆ, ಪರಿಶೀಲನೆಗೆ "
              "ಸಿದ್ಧ.",
    },
    "reason_none": {
        "en": "No draft to check — nothing readable came back from the "
              "retrieval.",
        "hi": "जाँचने के लिए कुछ नहीं — खोज से कुछ पढ़ने योग्य नहीं मिला।",
        "kn": "ಪರಿಶೀಲಿಸಲು ಏನೂ ಇಲ್ಲ — ಹುಡುಕಾಟದಿಂದ ಓದಬಹುದಾದದ್ದು ಸಿಗಲಿಲ್ಲ.",
    },
    "response_clarify_missing": {
        "en": "Asked you for: {missing}.",
        "hi": "आपसे यह पूछा: {missing}।",
        "kn": "ನಿಮ್ಮನ್ನು ಇದಕ್ಕಾಗಿ ಕೇಳಲಾಯಿತು: {missing}.",
    },
    "response_clarify_plain": {
        "en": "Asked you a follow-up question.",
        "hi": "आपसे एक प्रश्न पूछा।",
        "kn": "ನಿಮ್ಮನ್ನು ಒಂದು ಪ್ರಶ್ನೆ ಕೇಳಲಾಯಿತು.",
    },
    "response_amendment": {
        "en": "The passages carried an amendment notice and the draft quoted a "
              "duration, so the answer now carries the amending Act rather than "
              "the pre-amendment figure.",
        "hi": "अनुच्छेदों में संशोधन की सूचना थी और मसौदे में एक अवधि लिखी थी, "
              "इसलिए उत्तर में पुरानी अवधि के बजाय संशोधन करने वाला अधिनियम "
              "दिया गया है।",
        "kn": "ಭಾಗಗಳಲ್ಲಿ ತಿದ್ದುಪಡಿ ಸೂಚನೆ ಇದ್ದರಿಂದ ಮತ್ತು ಕರಡಿನಲ್ಲಿ ಒಂದು "
              "ಅವಧಿ ಇದ್ದುದರಿಂದ, ಹಳೆಯ ಅವಧಿಯ ಬದಲಿಗೆ ತಿದ್ದುಪಡಿ ಮಾಡಿದ ಕಾಯ್ದನ್ನು "
              "ಉತ್ತರದಲ್ಲಿ ನೀಡಲಾಗಿದೆ.",
    },
    "response_how_written": {
        "en": "Wrote a plain-language answer",
        "hi": "सरल भाषा में उत्तर लिखा",
        "kn": "ಸರಳ ಭಾಷೆಯಲ್ಲಿ ಉತ್ತರ ಬರೆದಿದೆ",
    },
    "response_how_template": {
        "en": "Used the template answer (no model)",
        "hi": "तैयार नमूना उत्तर इस्तेमाल किया (कोई मॉडल नहीं)",
        "kn": "ಸಿದ್ಧ ಮಾದರಿ ಉತ್ತರ ಬಳಸಲಾಗಿದೆ (ಮಾದರಿ ಇಲ್ಲ)",
    },
    "response_how_native": {
        "en": " in everyday {langname}, not translated word for word",
        "hi": " — {langname} में रोज़मर्रा की भाषा में, शब्द-दर-शब्द अनुवाद नहीं",
        "kn": " — {langname} ನಲ್ಲಿ ದಿನನಿತ್ಯದ ಭಾಷೆಯಲ್ಲಿ, ಪದಬಂದ ಪದ ಅನುವಾದವಲ್ಲ",
    },
    "response_how_english_fallback": {
        "en": " (kept in English — the {langname} rewrite came back unusable)",
        "hi": " (अंग्रेज़ी में ही रखा — {langname} में फिर लिखना असफल रहा)",
        "kn": " (ಇಂಗ್ಲಿಷ್ ನಲ್ಲಿ ಇರಿಸಲಾಗಿದೆ — {langname} ಗೆ ಮತ್ತೆ ಬರೆಯುವುದು "
              "ವಿಫಲವಾಯಿತು)",
    },
    "response_final": {
        "en": "{how} with {n} citation{plural}{extra}.",
        "hi": "{how} — {n} संदर्भ{extra}।",
        "kn": "{how} — {n} ಉಲ್ಲೇಖ{extra}.",
    },
}


def trace_text(lang: str, key: str, **fields: Any) -> str:
    """Render one trace template in the reader's language.

    A missing key or a missing field renders the template as-is rather than
    raising: the Thinking panel is never worth breaking an answer over.
    """
    bank = TRACE_TEXT.get(key) or {}
    template = bank.get(lang) or bank.get("en") or key
    try:
        return template.format(**fields)
    except (KeyError, IndexError, ValueError):
        return template


def _add_trace(state: Dict[str, Any], node: str, key: str, **fields: Any) -> None:
    state["trace"] = list(state.get("trace", [])) + [node]
    state["trace_detail"] = list(state.get("trace_detail", [])) + [
        {"node": node,
         "detail": trace_text(state.get("lang", "en"), key, **fields)}]


def carry_slots_from_history(slots: Dict[str, str],
                             history: List[Dict[str, str]]) -> Dict[str, str]:
    """Fill slots missing from a short follow-up with earlier user turns.

    One-word replies ("mutual", "wife") carry no topic on their own, so the
    planner would ask again. Merge slots from recent *user* messages; the
    current message always wins on conflict.
    """
    if not history:
        return slots
    if slots.get("topic") and not slots.get("topic_from_followup"):
        return slots  # current message already stands alone
    # A topic guessed from the question's shape is weaker than one the
    # conversation has already established, so a real topic in history wins.
    merged = dict(slots)
    if slots.get("topic_from_followup"):
        merged.pop("topic_from_followup", None)
    for msg in history:
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        for key, val in extract_slots(msg.get("content", "")).items():
            if key == "topic":
                # History's topic is a fact about the conversation; the guess
                # from question shape is not. Do not let a later message's guess
                # overwrite an established topic.
                if merged.get("topic_from_followup") and not merged.get("topic"):
                    merged["topic"] = val
                continue
            if key not in merged:
                merged[key] = val
    # A divorce question still needs its type even when the topic came from
    # history, so this check stays after the merge.
    merged.pop("topic_from_followup", None)
    return merged


_CONTEXTUALIZE_RETRY = (
    "Rewrite the user's last message as ONE standalone Indian family-law "
    "question. The previous attempt failed by returning the message "
    "unchanged, so the message does NOT stand on its own — it refers to the "
    "conversation. Expand whatever pronoun, ellipsis or one-word reply it "
    "uses into explicit legal terms. Example: if the conversation was about "
    "mutual consent divorce and the message is 'and if we have lived apart?', "
    "answer 'Under the Hindu Marriage Act 1955, can a couple get a "
    "mutual consent divorce if they have lived apart?'\n"
    "Output ONLY that one question. No preamble, no explanation."
)


def _force_contextualize(history: List[Dict[str, str]], raw_query: str,
                         llm: Optional[Callable]) -> str:
    """Second attempt at resolving a follow-up the first pass echoed back.

    A follow-up that comes back unchanged is either genuinely standalone or
    unresolved, and we cannot tell which by looking. Asking again, with the
    failure named explicitly, resolves the second case. Returns "" if the model
    still will not commit, and the slot-carry logic takes over.
    """
    try:
        text, _ = llm([
            {"role": "system", "content": _CONTEXTUALIZE_RETRY},
            *history[-6:],
            {"role": "user", "content": raw_query},
        ])
    except Exception as e:  # noqa: BLE001 — slot carry is the fallback
        logger.warning("agent contextualize retry failed (%r)", e)
        return ""
    candidate = (text or "").strip()
    if not candidate or candidate.lower() == raw_query.strip().lower():
        return ""
    if looks_looped(candidate):
        return ""
    return candidate


def looks_standalone(query: str) -> bool:
    """Whether a message is complete enough that rewriting it is pointless.

    Naming an Act or a section, or simply asking a full-length question, means
    there is nothing for the history to add. Without this check every such
    message costs a wasted model call: a correct model echoes a message that is
    already complete, and an echo is indistinguishable from a failed rewrite.
    """
    text = (query or "").strip()
    if not text:
        return True
    if _ACT_NAME_RE.search(text) or _SECTION_RE.search(text):
        return True
    return len(text.split()) >= 9


def node_intent(state: Dict[str, Any],
                llm: Optional[Callable] = None) -> Dict[str, Any]:
    raw_query = state["query"]
    query = raw_query
    lang = state["lang"]
    query_en = query
    provider = state.get("provider", "")
    history = state.get("history", [])
    memory = state.get("memory") or {}
    if history and llm is not None:
        # Follow-up questions ("mutual", "what about my daughter?") need
        # prior turns to stand alone for retrieval, so rewrite first.
        rewritten = ""
        try:
            rewritten, provider = llm([
                {"role": "system",
                 "content": ("You resolve follow-up questions. Given the "
                             "conversation history and the user's last message, "
                             "write ONE standalone family-law question that "
                             "keeps every detail from the last message "
                             "(e.g. 'mutual' after a divorce question means "
                             "mutual-consent divorce; 'wife' means the wife is "
                             "asking). If the last message already stands "
                             "alone, repeat it unchanged. Output ONLY that "
                             "one question — no explanation, no preamble.")},
                *history[-6:],
                {"role": "user", "content": query},
            ])
            state["provider"] = provider
        except Exception as e:  # noqa: BLE001 — fall back to raw query
            logger.warning("agent contextualize failed (%r); using raw query", e)
        candidate = (rewritten or "").strip()
        # A follow-up that comes back byte-identical was not resolved. Either
        # it genuinely stands alone, or the model just echoed it — and an
        # unresolved follow-up retrieves on two words and returns junk. Retry
        # once, insisting, before giving up.
        if candidate and candidate.lower() != raw_query.strip().lower():
            query = candidate
            _add_trace(state, "contextualize",
                       "ctx_resolved", q=raw_query[:60])
        else:
            retry = "" if looks_standalone(raw_query) else \
                _force_contextualize(history, raw_query, llm)
            if retry:
                query = retry
                _add_trace(state, "contextualize", "ctx_retry", q=retry[:100])
            else:
                _add_trace(state, "contextualize", "ctx_standalone")
        # query_en was seeded from the raw query and, for English, never
        # refreshed after the rewrite — so English follow-ups retrieved on the
        # unresolved text while Hindi ones (translated below) retrieved on
        # the resolved text. That asymmetry is the bug.
        query_en = query
    # Did the pivot actually produce English? Slot extraction, out-of-scope
    # detection and the plan all read English, so when the pivot failed they
    # are reading the user's Devanagari or Kannada script and finding nothing.
    # The planner has to know, because "no topic found" then means "we could
    # not read it", not "the user was vague" — and answering a frightened
    # Hindi speaker with "what is this about?" is the worst possible reply.
    state["pivot_ok"] = True
    if lang != "en":
        if llm is not None:
            try:
                query_en, provider = llm([
                    {"role": "system",
                     "content": QUERY_PIVOT_PROMPT},
                    {"role": "user", "content": query},
                ])
                state["provider"] = provider
                if not query_en.strip():
                    state["pivot_ok"] = False
            except Exception as e:  # noqa: BLE001 — pivot is best-effort
                logger.warning("agent translate failed (%r); using raw query", e)
                state["pivot_ok"] = False
        else:
            state["pivot_ok"] = False
        # Without a pivot the raw query still retrieves (e5 is multilingual):
        # measurably worse than the pivot, but far better than nothing.
    state["query_en"] = query_en.strip() or query
    slots = extract_slots(state["query_en"])
    carried = carry_slots_from_history(slots, history)
    if carried != slots:
        added = ", ".join("%s=%r" % (k, v) for k, v in carried.items()
                          if slots.get(k) != v)
        logger.info("agent carried slots from history: %s", added)
    slots = carried
    # Long-term memory, across sessions. Session history only helps inside one
    # conversation; a user who asked about custody yesterday and says "what
    # about maintenance?" today should not be asked the topic all over again.
    updates: Dict[str, str] = {}
    if not slots.get("topic") and memory.get("last_topic"):
        slots["topic"] = str(memory["last_topic"])
        _add_trace(state, "intent", "mem_topic",
                   topic=_local(TOPIC_LOCAL, slots["topic"], lang))
    if not slots.get("self_side") and memory.get("last_party_role"):
        # Someone who asked about maintenance as a wife should not be answered
        # as though they were the husband on their next question.
        slots["self_side"] = str(memory["last_party_role"])
        _add_trace(state, "intent", "mem_side")
    if slots.get("topic"):
        updates["last_topic"] = str(slots["topic"])
    # Which side they are on matters for the next question: "what about my
    # daughter?" after a custody answer needs the party, not the topic again.
    if slots.get("self_side"):
        updates["last_party_role"] = str(slots["self_side"])
    state["memory_updates"] = updates
    state["slots"] = slots
    state["intent"] = classify_intent(state["query_en"], slots)
    state["oos_redirect"] = is_oos(state["query_en"])
    topic = slots.get("topic")
    found_bits = []
    if topic:
        found_bits.append("topic %s" % _local(TOPIC_LOCAL, topic, lang))
    if slots.get("divorce_type"):
        found_bits.append("type %s"
                          % _local(DIVORCE_TYPE_LOCAL, slots["divorce_type"], lang))
    if slots.get("parties"):
        found_bits.append("asking for %s"
                          % _local(PARTY_LOCAL, slots["parties"], lang))
    if slots.get("section"):
        found_bits.append("section %s" % slots["section"])
    if not found_bits:
        found_bits.append(_phrase({"en": "no clear topic yet",
                                   "hi": "अभी कोई साफ़ विषय नहीं",
                                   "kn": "ಇನ್ನೂ ಸ್ಪಷ್ಟ ವಿಷಯವಿಲ್ಲ"}, lang))
    _add_trace(state, "intent", "intent_summary",
               found="; ".join(found_bits),
               langname=LANGUAGE_NAMES.get(lang, {}).get(lang, lang))
    return state


def node_planner(state: Dict[str, Any],
                 llm: Optional[Callable] = None) -> Dict[str, Any]:
    """Decide whether to ask the user, then decide how to search.

    Both decisions used to be a keyword table running before any model was
    consulted. The model now plans the retrieval; the slot rules stay as the
    floor so the no-key path and the tests behave exactly as before.
    """
    missing = missing_for(state.get("slots", {}),
                          state.get("query_en", ""),
                          is_followup=bool(state.get("history")))
    if missing == ["topic"] and not state.get("pivot_ok", True):
        # The only reason we cannot see a topic is that the English pivot did
        # not come back (every provider in cooldown). Ask "what is this about?"
        # in that case and the user, who already asked in their own language,
        # gets told they were unclear. Retrieval on the raw text will be
        # weaker, but an answer they can read beats a question they resent.
        _add_trace(state, "planner", "planner_pivot_failed")
        missing = []
    state["missing_slots"] = missing
    if state.get("oos_redirect"):
        # Out of scope is a decision, not a question. Asking "what is this
        # about?" to someone who asked about land was the wrong reply — the
        # redirect explaining our scope is the right one.
        state["clarification"] = ""
        state["plan"] = default_plan(state)
        _add_trace(state, "planner", "planner_oos")
        return state
    if missing and not should_answer_anyway(missing):
        state["clarification"] = clarification_question(
            missing, state.get("lang", "en"))
        # No retrieval worth planning when we are about to ask the user anyway.
        state["plan"] = default_plan(state)
        _add_trace(state, "planner", "planner_ask",
                   missing=", ".join(missing))
        return state
    if missing:
        # Answer now, and end with the question. Making the user wait a whole
        # turn for a bare "how do I get a divorce" was the wrong trade.
        state["clarification"] = ""
        _add_trace(state, "planner", "planner_answer_and_ask",
                   missing=", ".join(missing))
        state["follow_up_question"] = clarification_question(
            missing, state.get("lang", "en"))
    state["clarification"] = ""
    plan = plan_search(state, llm=llm)
    state["plan"] = plan
    steps = " then ".join(
        "%s (%s)" % (s["tool"], (s.get("why") or s["query"])[:60])
        for s in plan["steps"])
    if plan["source"] == "model":
        _add_trace(state, "planner", "planner_model_plan",
                   act=plan["governing_act"] or "an Act",
                   why=plan["reasoning"] or "", steps=steps)
    else:
        _add_trace(state, "planner", "planner_fixed_plan", steps=steps)
    return state


# The act that actually governs each topic. Retrieval on the bare question
# alone lets one incidental word decide the results: "Who gets the custody of
# the child in a divorce?" returned Indian Divorce Act sections because
# "divorce" outweighed "custody", and never reached Guardians and Wards.
TOPIC_ACT = {
    # Inter-religious and inter-caste marriage: Special Marriage Act 1954. It
    # is placed before "marriage" because the plain-marriage fallback is HMA,
    # which is the wrong answer for these questions.
    "interfaith_marriage": "Special Marriage Act 1954",
    "custody": "Guardians and Wards Act 1890",
    "divorce": "Hindu Marriage Act 1955 Indian Divorce Act 1869",
    # Special Marriage Act first for inter-religious/inter-caste marriage:
    # it is the statute that actually governs those, and putting HMA first
    # made the assistant cite the wrong Act for "can a Hindu girl marry a
    # Muslim boy".
    "marriage": "Special Marriage Act 1954 Hindu Marriage Act 1955",
    "maintenance": "Hindu Adoption and Maintenance Act 1956",
    "adoption": "Hindu Adoption and Maintenance Act 1956",
    "succession": "Hindu Succession Act 1956 Indian Succession Act 1925",
    "domestic_violence": "Domestic Violence Act 2005",
    "dowry": "Dowry Prohibition Act 1961",
}

_ALL_ACTS = ("Hindu Marriage Act 1955 Special Marriage Act 1954 Hindu Adoption "
             "and Maintenance Act 1956 Hindu Succession Act 1956 Guardians and "
             "Wards Act 1890 Domestic Violence Act 2005 Indian Divorce Act 1869")

# The legal words the Acts actually use, per topic.
#
# The embedding index is keyed on statute language, and a person rarely uses it.
# Guardians and Wards Act s.17 — the provision that decides almost every custody
# dispute — says "welfare of the minor shall be the first consideration". It
# never says "custody". So "who gets custody of my child" retrieved s.12 (produce
# the minor at a place and time) and never reached s.17 at all: not in the top
# ten. The same gap hid "residence order", "Class I heirs" and "living
# separately for one year".
#
# Adding the statute's own vocabulary to a plain question is what makes the
# right section findable. It is not keyword routing — the topic still comes from
# the model, and everything is still scored by vector similarity.
TOPIC_CONCEPTS = {
    "custody": "welfare of the minor first consideration guardian custody",
    "adoption": "adoption child welfare conditions adoption ceremony consent",
    "succession": "class I heirs intestate succession legal heirs share property",
    "divorce": "living separately one year mutual consent decree divorce",
    "maintenance": "maintenance amount reasonable income needs means arrears",
    "domestic_violence": "residence order shared household protection officer "
                         "monetary relief aggrieved person",
    "marriage": "solemnization registration valid marriage conditions",
    "dowry": "dowry prohibition amount punishment demand",
}


def concepts_for_topic(topic: str) -> str:
    """Statute vocabulary for a topic, to add to a plain-language query."""
    return TOPIC_CONCEPTS.get(topic or "", "")


def broaden_query(query_en: str, retries: int, topic: str = "") -> str:
    """Shape the retrieval query.

    Always anchor to the act that governs the detected topic, so a stray
    word in the question cannot drag the results into the wrong act. On a
    retry, add the full act list; on the second retry, drop section numbers
    that may be over-narrowing.

    Also add the statute's own vocabulary for the topic. The index is keyed on
    legal language, and "custody" does not retrieve a section that says
    "welfare of the minor" — see TOPIC_CONCEPTS.
    """
    anchor = TOPIC_ACT.get(topic or "", "")
    concepts = concepts_for_topic(topic)
    if retries <= 0:
        parts = [query_en, anchor, concepts]
        return re.sub(r"\s+", " ", " ".join(p for p in parts if p)).strip()
    if retries == 1:
        return "%s %s %s %s" % (query_en, anchor, concepts, _ALL_ACTS)
    # Retry 2: drop section numbers that may over-narrow the query.
    stripped = re.sub(r"section\s+\d+[A-Z\-]*", " ", query_en,
                      flags=re.IGNORECASE)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return "%s %s %s %s" % (stripped or query_en, anchor, concepts, _ALL_ACTS)


# ---------------------------------------------------------------------------
# Planning — the model decides the act and the tools, not a keyword table.
# ---------------------------------------------------------------------------

ACT_SEARCH = "search_acts"
WEB_SEARCH = "search_web"
SECTION_READ = "read_section"
TOOLS = (ACT_SEARCH, WEB_SEARCH, SECTION_READ)

# Passed to the model as a catalogue so it can only pick tools that exist.
TOOL_CATALOG = (
    "- %s: search the bare Acts (vector search). 'act' is an optional act name "
    "to rank results toward. The normal first choice.\n"
    "- %s: search the live web for recent judgments, amendments and procedure. "
    "Worth one call when the Acts may be out of date or the question is about "
    "'what do I actually do'.\n"
    "- %s: fetch one exact section when the user names a section number. "
    "Precise, but only correct if the user really gave a section."
    % (ACT_SEARCH, WEB_SEARCH, SECTION_READ))

_KNOWN_ACTS = (
    "Hindu Marriage Act 1955", "Special Marriage Act 1954",
    "Hindu Adoption and Maintenance Act 1956", "Hindu Succession Act 1956",
    "Guardians and Wards Act 1890", "Domestic Violence Act 2005",
    "Indian Divorce Act 1869", "Dowry Prohibition Act 1961",
    "Indian Succession Act 1925",
)


def acts_for_topic(topic: str) -> List[str]:
    """The acts that govern a topic, split out of the TOPIC_ACT anchor."""
    anchor = TOPIC_ACT.get(topic or "", "")
    return [a for a in _KNOWN_ACTS if a in anchor]


def parse_json_block(text: str) -> Optional[Dict[str, Any]]:
    """Pull the first JSON object out of a model reply.

    Small models fence their JSON, prefix it with "Here is the plan:", or trail a
    sentence after the closing brace. All of that is recoverable, so a chatty
    reply still plans. Returns None when there is genuinely no object, which is
    the caller's signal to fall back to the fixed plan.
    """
    if not text:
        return None
    body = str(text).strip()
    body = re.sub(r"^```(?:json)?", "", body).strip()
    body = re.sub(r"```$", "", body).strip()
    start = body.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(body)):
        if body[i] == "{":
            depth += 1
        elif body[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    out = json.loads(body[start:i + 1])
                except ValueError:
                    return None
                return out if isinstance(out, dict) else None
    return None


def default_plan(state: Dict[str, Any]) -> Dict[str, Any]:
    """The fixed plan used when there is no model, or the model's plan is junk.

    Same behaviour as the old code: anchor the query to the act that governs the
    keyword-detected topic, then search the web as well.
    """
    topic = (state.get("slots") or {}).get("topic", "")
    query_en = state.get("query_en") or state.get("query", "")
    acts = acts_for_topic(topic)
    steps = [{"tool": ACT_SEARCH, "query": query_en, "why": "",
              "act": acts[0] if acts else ""}]
    if not state.get("doc_id"):
        steps.append({"tool": WEB_SEARCH, "query": query_en, "why": ""})
    return {"governing_act": acts[0] if acts else "",
            "reasoning": "", "steps": steps, "source": "fixed"}


def normalise_plan(raw: Any, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Validate a model plan. None means 'use the fixed plan instead'.

    A plan that names no real tool, or no query, or nothing at all is not a
    plan — treating it as one would be worse than the keyword table it replaces.
    """
    if not isinstance(raw, dict):
        return None
    incoming = raw.get("steps")
    if not isinstance(incoming, list):
        return None
    steps: List[Dict[str, str]] = []
    for item in incoming[:MAX_PLAN_STEPS]:
        if not isinstance(item, dict):
            continue
        tool = str(item.get("tool") or "").strip()
        query = str(item.get("query") or "").strip()
        if tool not in TOOLS or not query:
            continue
        steps.append({"tool": tool,
                      "query": query[:200],
                      "why": str(item.get("why") or "").strip()[:200],
                      "act": str(item.get("act") or "").strip()[:80]})
    if not steps:
        return None
    # The Acts are the product. A plan made only of web searches leaves the
    # answer resting on whatever a crawler returns, and a live follow-up
    # ("and if I want a divorce?") came back with no evidence at all because the
    # model decided the Acts did not govern it and went to the web alone, where
    # nothing was found. So the Act search is not optional: if the model left
    # it out, it goes back in first.
    if not any(s["tool"] == ACT_SEARCH for s in steps):
        fixed = default_plan(state)["steps"][0]
        fixed["why"] = "The bare Acts are always searched, even when the web " \
                       "is also used."
        steps.insert(0, fixed)
    # The web is the fallback for anything the bare Acts do not cover (court
    # fees, filing steps, recent amendments, procedures). The planner often
    # omits it, and then a follow-up whose answer is not in the statutes comes
    # back grounded in irrelevant passages. Guarantee a web step is present so
    # the answer can draw on current sources when the Acts fall short.
    if (not state.get("doc_id") and len(steps) < MAX_PLAN_STEPS
            and not any(s["tool"] == WEB_SEARCH for s in steps)):
        steps.append({"tool": WEB_SEARCH,
                      "query": str(state.get("query_en") or state.get("query", "")).strip()[:200],
                      "why": "The Acts may not cover this; check current sources.",
                      "act": ""})
    return {"governing_act": str(raw.get("governing_act") or "").strip()[:120],
            "reasoning": str(raw.get("reasoning") or "").strip()[:400],
            "steps": steps, "source": "model"}


PLAN_SYSTEM = (
    "You are the planner of LawSaathi, a family-law assistant for India. You "
    "do not answer the user. You decide which Act governs their question and "
    "which searches to run.\n\n"
    "The Acts available:\n%s\n\n"
    "Tools available:\n%s\n\n"
    "Rules:\n"
    "- Decide which Act actually governs. An act's name does not make it the "
    "right one. In particular:\n"
    "  * Divorce, and marriage between two Hindus, Buddhists, Jains or Sikhs: "
    "Hindu Marriage Act 1955.\n"
    "  * Marriage between people of DIFFERENT religions, and marriage "
    "between people of DIFFERENT castes: Special Marriage Act 1954. Never "
    "the Hindu Marriage Act for these.\n"
    "  * Maintenance and adoption: Hindu Adoption and Maintenance Act 1956, "
    "but only for Hindus. For a Muslim wife it is the Muslim guardianship "
    "and maintenance rules, which we do not hold — say so instead of "
    "citing a Hindu Act.\n"
    "  * Custody of a minor: Guardians and Wards Act 1890, even when the user "
    "mentions divorce.\n"
    "  * Inheritance: Hindu Succession Act 1956 for Hindus, Indian Succession "
    "Act 1925 otherwise.\n"
    "  * Protection orders, and which court: Domestic Violence Act 2005.\n"
    "  * Dowry: Dowry Prohibition Act 1961.\n"
    "- If the user's question is governed by a statute we do not hold, pick "
    "the closest Act we do hold and say in 'reasoning' that the governing "
    "statute is missing. Do not pretend the Act you picked is the right one.\n"
    "- Write a short search query in English with the legal terms a section "
    "would actually use, not the user's casual wording.\n"
    "- Two or three steps. Add a web step only if the Acts may not answer it.\n"
    "- Reply with JSON only. No preamble, no explanation outside the JSON.\n"
    'Shape: {"governing_act": "...", "reasoning": "one sentence", '
    '"steps": [{"tool": "...", "query": "...", "why": "...", "act": "..."}]}'
    % ("\n".join("- " + a for a in _KNOWN_ACTS), TOOL_CATALOG))


def plan_search(state: Dict[str, Any],
                llm: Optional[Callable] = None) -> Dict[str, Any]:
    """Ask the model to plan the retrieval. Falls back to the fixed plan.

    This is the decision that used to be a keyword lookup, done before any model
    ran. Now the model picks the governing Act and the tools, and its reasoning
    is shown to the user in the Thinking panel.
    """
    fallback = default_plan(state)
    if llm is None:
        return fallback
    slots = state.get("slots") or {}
    bits = ["Topic so far: %s" % (slots.get("topic") or "unclear")]
    if slots.get("section"):
        bits.append("User named section %s." % slots["section"])
    if slots.get("divorce_type"):
        bits.append("Divorce type: %s." % slots["divorce_type"])
    if slots.get("parties"):
        bits.append("Asking for: %s." % slots["parties"])
    user = ("Question: %s\n\n%s\n\nReturn the JSON plan only."
            % (state.get("query_en") or state.get("query", ""),
               " ".join(bits)))
    try:
        text, provider = llm([{"role": "system", "content": PLAN_SYSTEM},
                             {"role": "user", "content": user}])
        state["provider"] = provider
        plan = normalise_plan(parse_json_block(strip_reasoning_leak(text)),
                              state)
    except Exception as e:  # noqa: BLE001 — the fixed plan is always valid
        logger.warning("agent planner failed (%r); using the fixed plan", e)
        plan = None
    if not plan:
        logger.info("agent planner returned no usable plan; using the fixed plan")
        return fallback
    return plan


REPLAN_SYSTEM = (
    "You are the planner of LawSaathi, a family-law assistant for India. A "
    "previous search of the bare Acts did NOT answer the question, so the "
    "answer must come from somewhere else.\n\n"
    "Decide the recovery plan:\n"
    "- If the question turns on a recent judgment, an amendment, a court "
    "procedure, a filing step, or a document the user must produce, add a "
    "%s step. That is what it is for.\n"
    "- If the bare Acts genuinely do not govern the question (a statute we do "
    "not hold), say so in 'reasoning' and still search the web for the "
    "current position.\n"
    "- Also re-query the Acts once with plainer wording, in case the first "
    "phrasing was the problem.\n"
    "- Steps must not repeat the failed query.\n\n"
    "Reply with JSON only, same shape as before."
    % WEB_SEARCH)


def replan_after_empty(state: Dict[str, Any],
                      llm: Optional[Callable] = None
                      ) -> Optional[Dict[str, Any]]:
    """Ask the planner for a second plan once the Acts have come up short.

    Without this, Firecrawl is only ever used when the first plan happens to
    include a web step — which in practice it usually does not, so the tool we
    pay for sat unused while the assistant kept re-phrasing the same Act
    search. Returns None when there is no model or the reply is unusable, and
    the caller keeps the existing plan.
    """
    if llm is None:
        return None
    question = state.get("query_en") or state.get("query", "")
    previous = "; ".join("%s: %s" % (s.get("tool"), s.get("query"))
                         for s in (state.get("plan") or {}).get("steps", []))
    user = ("Question: %s\n\nPlan already tried (and found nothing):\n%s\n\n"
            "Return the recovery JSON plan only."
            % (question, previous or "(nothing recorded)"))
    try:
        text, provider = llm([{"role": "system", "content": REPLAN_SYSTEM},
                              {"role": "user", "content": user}])
        state["provider"] = provider
        plan = normalise_plan(parse_json_block(strip_reasoning_leak(text)),
                              state)
    except Exception as e:  # noqa: BLE001 — keep the original plan
        logger.warning("agent replan failed (%r); keeping original plan", e)
        return None
    if not plan:
        return None
    # A recovery plan that repeats the failed searches is not a recovery.
    old = {s.get("query", "").strip().lower()
           for s in (state.get("plan") or {}).get("steps", [])}
    fresh = [s for s in plan["steps"]
             if s["query"].strip().lower() not in old]
    if not fresh:
        return None
    plan["steps"] = fresh
    return plan


# A mutual-consent divorce timing question is the single most common thing
# people ask this assistant, and the consolidated statute text that every
# corpus — including India Code itself — publishes is the PRE-2018 version.
# Measured on the live index: asking for "minimum period for separation"
# returns the amendment notice first (0.897), but the moment the query is
# anchored with the Act name, as the planner requires, the notice drops out of
# the top 16 entirely and generic sections 13/10/4/14 take its place.
#
# A safety rule cannot depend on vector similarity, so the notice is fetched
# by act and label rather than by relevance. It is a real corpus point, so it
# is citable like any other passage.
_AMENDMENT_LABEL = "Amendment notice"

# Material that is not law. A Bill is a proposal; a Bill *passed* is still not
# in force until notified. Quoting one as "BARE ACT" tells a person seeking
# custody that a rule exists when no court will apply it.
#
# Found live: the production answer to "who gets custody of my child" cited
# "Prohibition of Child Marriage (Amendment) Bill, 2021" as source 5, and
# stated a "children under five go to the mother" rule attributed to it. That
# rule is not in the Bill or in the Guardians and Wards Act — the model supplied
# it, and the citation made it look sourced. 22 chunks of that Bill were in the
# corpus, from a local text file.
#
# The word list now lives in ingest.py, which also refuses such a document on
# the way in. Filtering only at answer time left those chunks taking a slot in
# the top-k and pushing a real Guardians and Wards section out of the evidence,
# so ingestion and the answer now read the same rule from one place.


def is_enacted(payload: Dict[str, Any]) -> bool:
    """False for material a court would not apply today."""
    from app.ingest import is_enacted_law

    act = str((payload or {}).get("act") or "")
    if not act:
        # An amendment notice is a corpus point we created; it stays citable.
        return True
    return is_enacted_law(act)


_TIMING_WORDS = (
    "mutual consent", "mutual", "living separately", "live apart",
    "lived apart", "separation period", "how long", "waiting period",
    "cooling", "joint petition",
)


def wants_timing_correction(query: str) -> bool:
    low = (query or "").lower()
    if not any(w in low for w in _TIMING_WORDS):
        return False
    return any(w in low for w in ("divorce", "dissolution", "separat",
                                 "apart", "consent"))


def amendment_notices(state: Dict[str, Any],
                      store: Any) -> List[Dict[str, Any]]:
    """Fetch amendment notices for the governing Act, regardless of relevance."""
    finder = getattr(store, "find_amendment_notices", None)
    if not callable(finder):
        return []
    try:
        return list(finder(state.get("query_en") or state.get("query", ""))
                    or [])
    except Exception as e:  # noqa: BLE001 — best effort, never fatal
        logger.warning("agent amendment lookup failed (%r)", e)
        return []


class StubRetriever:
    """No-key retriever: returns no evidence (lets clarification path work)."""

    def search_text(self, text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        return []


def default_retriever() -> Any:
    try:
        from app.ingest import QdrantStore  # lazy: qdrant optional in tests
        return QdrantStore.connect()
    except Exception as e:  # noqa: BLE001 — offline/tests get the stub
        logger.warning("agent retriever unavailable (%r); using stub", e)
        return StubRetriever()


def stub_web_search(query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """Firecrawl seam for T5 — real crawl/search when FIRECRAWL_API_KEY set."""
    logger.info("agent web_search query=%r (T5 Firecrawl)", query[:80])
    try:
        import os
        from firecrawl import Firecrawl
        key = os.environ.get("FIRECRAWL_API_KEY", "")
        fc = Firecrawl(api_key=key or None)
        res = fc.search(query, limit=top_k, sources=["web"])
        results = []
        for item in (res.web or []):
            url = getattr(item, "url", None) or (getattr(item, "metadata", {}).get("sourceURL") if hasattr(item, "metadata") else None)
            title = getattr(item, "title", None) or (getattr(item, "metadata", {}).get("title") if hasattr(item, "metadata") else None)
            text = getattr(item, "description", None) or (getattr(item, "markdown", None) if hasattr(item, "markdown") else "")
            if isinstance(item, dict):
                url = item.get("url") or item.get("metadata", {}).get("sourceURL")
                title = item.get("title") or item.get("metadata", {}).get("title")
                text = item.get("description") or item.get("markdown") or item.get("text", "")
            if not url and isinstance(item, dict) and item.get("metadata"):
                url = item["metadata"].get("sourceURL")
            if url:
                payload = {
                    "url": url,
                    "title": title or url,
                    "text": (text or "Web source.")[:800],
                }
                results.append({"payload": payload, "score": 0.85})
        if results:
            logger.info("agent web_search returned %d web hits", len(results))
        return results
    except Exception as e:  # noqa: BLE001 — web is best-effort
        logger.info("agent web_search Firecrawl unavailable (%r); falling back to stub", e)
        return []


def _evidence_source_type(hit: Dict[str, Any]) -> str:
    payload = hit.get("payload", {}) if isinstance(hit, dict) else {}
    if isinstance(payload, dict) and payload.get("doc_id"):
        return "doc"
    if isinstance(payload, dict) and payload.get("url"):
        return "web"
    if isinstance(payload, dict) and payload.get("act"):
        return "bare_act"
    return "bare_act"


def format_citation(payload: Dict[str, Any]) -> str:
    act = str(payload.get("act", "") or "").strip()
    section = str(payload.get("section", "") or "").strip()
    url = str(payload.get("url", "") or "").strip()
    title = str(payload.get("title", "") or "").strip()
    doc_title = str(payload.get("doc_title", "") or "").strip()
    doc_id = str(payload.get("doc_id", "") or "").strip()
    if doc_id:
        base = (doc_title or "Uploaded doc") + (" — %s" % section if section else "")
        return base or ("doc:%s" % doc_id[:8])
    if act and section:
        return "%s — %s" % (act, section)
    if url:
        return title or url
    return act or section or "retrieved passage"


def _hit_key(hit: Dict[str, Any]) -> Tuple[str, str, str]:
    p = hit.get("payload") or {}
    return (str(p.get("act", "")), str(p.get("section", "")),
            str(p.get("text", ""))[:120])


def _act_of(hit: Dict[str, Any]) -> str:
    return str((hit.get("payload") or {}).get("act", "") or "")


def _matches_act(hit: Dict[str, Any], act: str) -> bool:
    """Whether a hit really belongs to the act the planner chose.

    Loose comparison on purpose: ingestion writes "Hindu Marriage Act, 1955"
    with a comma while the planner says "Hindu Marriage Act 1955" without one,
    and act names in the corpus are not perfectly consistent.
    """
    if not act:
        return True
    got = re.sub(r"[^a-z0-9]", "", _act_of(hit).lower())
    want = re.sub(r"[^a-z0-9]", "", act.lower())
    if not got:
        return False
    return got.startswith(want) or want.startswith(got)


def _section_of(hit: Dict[str, Any]) -> str:
    return str((hit.get("payload") or {}).get("section", "") or "")


def _rank_toward_section(hits: List[Dict[str, Any]],
                         section: str) -> List[Dict[str, Any]]:
    """Put the exact section the user named above everything else.

    Pure vector similarity cannot do this. Measured on the live corpus, asking
    for "Section 13B Hindu Marriage Act" returned the Preamble at 0.895,
    Section 13A at 0.892 and the real Section 13B fourth at 0.890 — a 0.005
    spread, so embeddings rank boilerplate above the provision actually asked
    about. When the user names a section, that is a hard lexical constraint,
    not a hint, and it should win.
    """
    if not section:
        return hits
    want = re.sub(r"[^0-9a-z]", "", section.lower())
    # "13b" must not match "13" — compare the full token from the label.
    def exact(hit: Dict[str, Any]) -> bool:
        label = re.match(r"\s*section\s+([0-9]+[a-z]*)",
                         _section_of(hit), re.IGNORECASE)
        return bool(label) and label.group(1).lower() == want
    return [h for h in hits if exact(h)] + [h for h in hits if not exact(h)]


def _rank_toward_act(hits: List[Dict[str, Any]],
                     act: str) -> List[Dict[str, Any]]:
    """Put the governing Act's sections first, then everything else.

    This is what makes the planner's choice actually change the answer. Without
    it the plan would be decoration: vector search would return whatever it
    liked and the Act the model reasoned about would be ignored.
    """
    if not act:
        return hits
    on = [h for h in hits if _matches_act(h, act)]
    off = [h for h in hits if not _matches_act(h, act)]
    return on + off


def node_tools(state: Dict[str, Any], retriever: Any = None,
               web_search: Optional[Callable] = None,
               llm: Optional[Callable] = None) -> Dict[str, Any]:
    """Run the steps the planner chose, one tool at a time.

    Previously this made the same two calls on every question with a query
    derived from a keyword table. Now each step names a tool and a query, so
    the Act the planner picked is the Act we actually search.
    """
    store = retriever or default_retriever()
    # The Acts have nothing and we are out of breadth on this query: re-plan
    # before searching again, or the third attempt repeats the first. Doing
    # this here rather than in the router keeps the LangGraph path and the
    # inline path identical — it once lived in the edge function and only one
    # of them re-planned.
    if (int(state.get("retries", 0)) >= MAX_RETRIES
            and not state.get("evidence")):
        fresh = replan_after_empty(state, llm=llm)
        if fresh:
            state["plan"] = fresh
            _add_trace(state, "planner", "planner_replan",
                       steps=" then ".join("%s (%s)" % (s["tool"], s["query"][:50])
                                           for s in fresh["steps"]))
    plan = state.get("plan") or default_plan(state)
    # On a retry the verifier's own next_queries replace the plan's queries,
    # but the tools stay the ones the planner picked.
    retry_queries = state.get("next_queries") or []
    doc_id = state.get("doc_id") or ""
    steps = plan["steps"] or default_plan(state)["steps"]

    evidence: List[Dict[str, Any]] = []
    seen = set()
    notes: List[str] = []
    n_web = 0
    lang = state.get("lang", "en")

    def note(key: str, **fields: Any) -> None:
        """One line of the step log, in the reader's language."""
        notes.append(trace_text(lang, key, **fields))

    # The reader's own words. e5-small is multilingual, so a Kannada or Hindi
    # question does match English statute text — at the level of topics. The
    # pivot exists because it does not match *legal terms*: nothing in a
    # non-English string says "dowry". Running both is what makes each one's
    # weakness the other's safety net — see ADR-0012 Decision 1.
    native_query = ""
    if lang != "en":
        raw = (state.get("query") or "").strip()
        pivot = (state.get("query_en") or "").strip()
        # Only when it would actually search something different. An English
        # fallback question (the pivot failed) is already all we have.
        if raw and raw.lower() != pivot.lower():
            native_query = raw

    for i, step in enumerate(steps):
        tool = step.get("tool", ACT_SEARCH)
        query = step["query"]
        if retry_queries:
            if i < len(retry_queries):
                query = retry_queries[i]
            else:
                # Verifier only needs as many queries as it supplied; the
                # remaining plan steps would just repeat what already failed.
                break
        elif tool != WEB_SEARCH:
            # The planner writes the query in the user's words, which is right for
            # a person and wrong for a statute: "custody" does not retrieve the
            # section that says "welfare of the minor". Always add the act anchor
            # and the statute's own vocabulary for the topic — including on the
            # first pass, where this previously did nothing.
            query = broaden_query(query, int(state.get("retries") or 0),
                                  (state.get("slots") or {}).get("topic", ""))
        shown = query[:80]
        if tool == WEB_SEARCH:
            ws = web_search or stub_web_search
            try:
                hits = list(ws(query) or [])
            except Exception as e:  # noqa: BLE001 — web is best-effort
                logger.warning("agent web_search failed (%r)", e)
                note("tools_web_fail", q=shown,
                     err=(str(e) or e.__class__.__name__)[:60])
                continue
            n_web += len(hits)
            for h in hits:
                k = _hit_key(h)
                if k not in seen:
                    seen.add(k)
                    evidence.append(h)
            note("tools_web", q=shown, n=len(hits),
                 plural=_plural(lang, len(hits)))
            continue

        # search_acts and read_section both go to the vector store; the act
        # anchor is what separates them in practice.
        act = step.get("act") or plan.get("governing_act") or ""
        # Anchor the embedding query to the Act the planner chose. The model's
        # own wording is good but e5-small needs the Act's own words to pull
        # the right sections back — this is what stopped "custody... in a
        # divorce?" from returning Divorce Act sections.
        search_text = "%s %s" % (query, act) if act else query
        try:
            if doc_id and hasattr(store, "search_text"):
                hits = list(store.search_text(search_text, top_k=6,
                              filter_payload={"doc_id": doc_id}) or [])
            elif doc_id and hasattr(store, "search"):
                # InMemoryVectorStore lacks text search; unfiltered fallback
                hits = list(store.search(query, top_k=6) or [])
            else:
                hits = list(store.search_text(search_text, top_k=6) or [])
        except Exception as e:  # noqa: BLE001 — retrieval failure is retryable
            logger.warning("agent retrieval failed (%r)", e)
            note("tools_retrieval_failed", tool=tool, q=shown,
                 err=(str(e) or e.__class__.__name__)[:60])
            continue
        act_for_filter = act
        # The second path runs before the ranking, on purpose: a section the
        # reader's own words found has to be able to outrank an off-Act hit the
        # anchored query produced, which is the whole point of running it.
        # Anything already known is dropped, so the two paths agree on what they
        # found rather than doubling the count.
        if native_query and tool != WEB_SEARCH and not retry_queries:
            try:
                extra = list(store.search_text(
                    "%s %s" % (native_query, act) if act else native_query,
                    top_k=4) or [])
            except Exception as e:  # noqa: BLE001 — best effort, like the first
                logger.warning("agent native-query search failed (%r)", e)
            else:
                known = {_hit_key(h) for h in hits}
                fresh = [h for h in extra if _hit_key(h) not in known]
                if fresh:
                    hits = list(hits) + fresh
                    note("tools_native", q=native_query[:80], n=len(fresh),
                         plural=_plural(lang, len(fresh)))
        if tool == SECTION_READ:
            section = re.sub(r"[^0-9A-Za-z]", "", query).lower()
            exact = [h for h in hits
                     if section and section in re.sub(
                         r"[^0-9a-z]", "", str(
                             (h.get("payload") or {}).get("section", "")).lower())]
            if not exact:
                # The section the user actually named is not in the top hits.
                # Vector search alone will keep missing it, so widen once:
                # ask for the whole Act and take more, then let the ranking
                # pick. Better a nearby section than answering with the wrong
                # one and saying nothing about what was asked.
                number = (state.get("slots") or {}).get("section", "")
                if number:
                    try:
                        rescued = list(store.search_text(
                            "%s %s" % (number, act or ""), top_k=12) or [])
                    except Exception as e:  # noqa: BLE001 — best effort
                        logger.warning("agent section rescue failed (%r)", e)
                    else:
                        if rescued:
                            hits = rescued
        hits = _rank_toward_section(
            hits, (state.get("slots") or {}).get("section", "")
            if tool == SECTION_READ else "")
        hits = _rank_toward_act(hits, act)
        enacted = [h for h in hits if is_enacted(h.get("payload") or {})]
        dropped = len(hits) - len(enacted)
        hits = enacted
        added = 0
        for h in hits:
            k = _hit_key(h)
            if k not in seen:
                seen.add(k)
                evidence.append(h)
                added += 1
        if added and act:
            note("tools_sections", tool=tool, q=shown, n=added,
                 plural=_plural(lang, added), act=act)
        elif added:
            note("tools_sections_no_act", tool=tool, q=shown, n=added,
                 plural=_plural(lang, added))
        elif not dropped:
            note("tools_nothing_new", tool=tool, q=shown)
        if dropped and not added:
            # Worth saying out loud: the person is watching a "nothing found"
            # and should know material was set aside, not lost.
            note("tools_skipped_bill", n=dropped,
                 plural=_plural(lang, dropped))

    rag_empty = (not evidence) or (not any(
        _evidence_source_type(h) in ("bare_act", "doc") for h in evidence))
    if rag_empty and not state.get("web_search_done"):
        state["web_search_done"] = True
        ws = web_search or stub_web_search
        shown = (state.get("query_en") or state.get("query", ""))[:80]
        try:
            web_hits = list(ws(state.get("query_en") or state.get("query", ""), top_k=3) or [])
        except Exception as e:  # noqa: BLE001 — web is best-effort
            logger.warning("agent web_search fallback failed (%r)", e)
            note("tools_web_fail", q=shown,
                 err=(str(e) or e.__class__.__name__)[:60])
            web_hits = []
        if web_hits:
            n_web += len(web_hits)
            for h in web_hits:
                k = _hit_key(h)
                if k not in seen:
                    seen.add(k)
                    evidence.append(h)
            note("tools_web", q=shown, n=len(web_hits),
                 plural=_plural(lang, len(web_hits)))
    state["evidence"] = evidence[:8]
    if wants_timing_correction(state.get("query_en") or state.get("query", "")):
        # Attach by act, not by relevance — see the note on the constant.
        for notice in amendment_notices(state, store):
            key = _hit_key(notice)
            if key in seen:
                continue
            seen.add(key)
            state["evidence"].append(notice)
        if any(_AMENDMENT_LABEL in _section_of(h)
               for h in state["evidence"]):
            note("tools_amendment")
    if not evidence:
        note("tools_no_evidence")
    _add_trace(state, "tools", " ".join(notes))
    state.pop("next_queries", None)
    return state


def evidence_sufficient(evidence: List[Dict[str, Any]],
                        min_score: float = 0.0) -> bool:
    if not evidence:
        return False
    for hit in evidence:
        text = ((hit.get("payload") or {}).get("text", "")
                if isinstance(hit, dict) else "")
        score = hit.get("score", 1.0) if isinstance(hit, dict) else 1.0
        try:
            ok_score = float(score) >= float(min_score)
        except (TypeError, ValueError):
            ok_score = True
        if text and text.strip() and ok_score:
            return True
    return False


OOS_KEYWORDS = ("land", "farmland", "agriculture", "soil", "crop", "farming",
                "property", "real estate", "criminal", "tax", "income tax",
                "property law", "criminal law", "theft", "murder", "rape",
                "cheque", "stamp duty", "tenant", "eviction", "motor vehicle",
                # Government-process and civil-remedy words. Someone with an RTI
                # notice or a police complaint was getting a confident answer
                # about the wrong law, which is worse than a redirect.
                "landlord", "rent", "police", "fir", "court case", "civil case",
                "consumer forum", "rti", "right to information", "notice",
                "notice under", "company", "employer", "employment",
                "labour", "labor", "bank", "loan", "debt", "recovery",
                "bail", "police station", "complaint", "case against me",
                "contract", "agreement", "nda", "patent", "trademark",
                "copyright", "passport", "visa", "electoral", "vote",
                "government job", "municipal", "gram panchayat",
                "कार्ड", "एफ़सीआरई", "किराया", "मकान", "पुलिस", "वसूली",
                "ಕೌಳೂರು", "ಪೊಲೀಸ್", "ಅರ್ಜಿ", "ಸರ್ಕಾರಿ")

# Signals that a question about land or property is really about *inheriting*
# it, which is family law. "My father died and my brother is taking the
# ancestral land" was being refused as out-of-scope property law, which is
# exactly backwards: who inherits is Hindu Succession Act, and it is one of the
# most common questions a family-law user asks.
_SUCCESSION_HINTS = (
    "died", "death", "deceased", "passed away", "ancestral", "ancestors",
    "inherit", "inheritance", "heir", "heirs", "succession", "successor",
    "legal heir", "family property", "left behind", "after his death",
    "after her death", "will", "testate", "intestate", "share of the property",
    "property left", "land left", "who gets the", "virasat", "jaydad",
    "उत्तराधिकार", "वारिस", "ಉತ್ತರಾಧಿಕಾರ", "ವಿರಾಶ",
)


# Short, ordinary words that collide with family-law wording. "rent" is inside
# "pa*rent*" and "current"; "bank" inside "bank*". Matching them as substrings
# refused an adoption question as tenancy law, which is a much worse failure
# than missing a stray mention of a bank.
_OOS_WHOLE_WORDS = {"rent", "rents", "loan", "loans", "bank", "tax", "land",
                    "property", "police", "tenant", "employer", "passport",
                    "visa", "company", "contract", "bail", "debt", "notice"}


def _oos_match(keyword: str, low: str) -> bool:
    if keyword in _OOS_WHOLE_WORDS:
        return re.search(r"\b%s\w*" % re.escape(keyword), low) is not None
    return keyword in low


def is_oos(query_en: str) -> bool:
    low = (query_en or "").lower()
    # Whole words only for the short, common ones. Substring matching made
    # "my aunt cannot live with the pa*rents*" trip the rent rule and refuse an
    # adoption question, which is a far worse failure than missing an out-of-
    # scope topic that happens to include one of these words.
    has_oos = any(_oos_match(k, low) for k in OOS_KEYWORDS)
    if not has_oos:
        return False
    # A dispute over land *between a living father and his son* is tenancy or
    # property law and we must not answer it. But land that changed hands
    # because someone died is succession, and that we can and must answer.
    if any(h in low for h in _SUCCESSION_HINTS):
        return False
    has_family = any(k in low for k in (
        "marriage", "married", "divorce", "divorced", "custody",
        "maintenance", "adoption", "adopted", "guardians",
        "domestic violence", "succession", "inheritance", "inherit",
        "heir", "adoption", "adopt", "residence order", "protection order",
            "maintenance", "custody", "guardian", "domestic violence"))
    return has_oos and not has_family


VERIFY_SYSTEM = (
    "You are the verifier of LawSaathi, a family-law assistant for India. You "
    "do not write answers. You check exactly one thing: did the draft make up "
    "law that is not in the passages?\n\n"
    "The draft is written in plain English for a layperson, so it paraphrases "
    "and simplifies the passages. That is correct — never reject for it.\n\n"
    "NEVER reject the draft for any of these, all of which are correct "
    "behaviour:\n"
    "- it says the passages do not cover part of the question\n"
    "- it says it cannot verify something, or recommends a lawyer\n"
    "- it uses different words from the passage to say the same thing\n"
    "- it is shorter or longer than the passage\n\n"
    "Reject ONLY if the draft states a specific legal rule — a section "
    "number, a ground, a period, an amount, a court, a date — that the "
    "passages do not support.\n\n"
    "A section named in the passages' own text is supported even if the draft "
    "words it differently. A section that appears nowhere in the passages is "
    "the only kind of missing reference that counts.\n\n"
    "When you are unsure, answer 'grounded'. A false rejection costs the user "
    "a second search and a warning they did not need.\n\n"
    'Reply with JSON only: {"verdict": "grounded"|"insufficient", "reason": '
    '"one sentence naming the invented rule", "next_queries": ["..."]}. '
    "next_queries may be empty."
)


def _evidence_block(state: Dict[str, Any], limit: int = 5) -> str:
    lines = []
    for i, hit in enumerate(state.get("evidence", [])[:limit], start=1):
        if not isinstance(hit, dict):
            continue
        payload = hit.get("payload") or {}
        body = plain_passage(str(payload.get("text", "") or ""), limit=400)
        if not body:
            continue
        lines.append("[%d] %s — %s" % (i, format_citation(payload), body))
    return "\n\n".join(lines)


def verify_grounding(state: Dict[str, Any],
                     llm: Optional[Callable] = None
                     ) -> Optional[Dict[str, Any]]:
    """Ask the model whether the draft is actually supported by the passages.

    Returns None when there is no model or the reply was unusable, which tells
    the caller to fall back to the old threshold check. The judge can only make
    a run *more* suspicious than the score test, never less: an empty passage
    list short-circuits before the model is even called.
    """
    passages = _evidence_block(state)
    draft = str(state.get("draft", "") or "").strip()
    if not passages or not draft or llm is None:
        return None
    user = ("Question: %s\n\nPassages:\n%s\n\nDraft answer:\n%s\n\n"
            "Return the JSON verdict only."
            % (state.get("query_en") or state.get("query", ""),
               passages, draft[:3000]))
    try:
        text, provider = llm([{"role": "system", "content": VERIFY_SYSTEM},
                              {"role": "user", "content": user}])
        state["provider"] = provider
        out = parse_json_block(strip_reasoning_leak(text))
    except Exception as e:  # noqa: BLE001 — fall back to the threshold check
        logger.warning("agent verifier judge failed (%r)", e)
        return None
    if not out:
        return None
    verdict = str(out.get("verdict") or "").strip().lower()
    if verdict not in ("grounded", "insufficient"):
        return None
    queries = out.get("next_queries")
    next_queries = []
    if isinstance(queries, list):
        for q in queries[:2]:
            q = str(q or "").strip()
            if q:
                next_queries.append(q[:200])
    return {"verdict": verdict,
            "reason": str(out.get("reason") or "").strip()[:300],
            "next_queries": next_queries}


def node_verifier(state: Dict[str, Any],
                  min_score: float = 0.0,
                  llm: Optional[Callable] = None) -> Dict[str, Any]:
    """Decide whether the draft holds up, and ask for better evidence if not.

    Two gates. The hard floor is unchanged: no passage text means no answer,
    whatever any model says. Above that floor a model judge reads the draft
    against the passages, which is the check the score threshold never could
    do. With no judge available the threshold is the whole test, exactly as
    before.
    """
    has_floor = evidence_sufficient(state.get("evidence", []),
                                    min_score=min_score)
    retries = int(state.get("retries", 0))

    # Confidence stays a retrieval statistic: how strong the best match was.
    confidence = 0.0
    if has_floor:
        scores = []
        for hit in state.get("evidence", []):
            score = hit.get("score", 1.0) if isinstance(hit, dict) else 1.0
            try:
                scores.append(float(score))
            except (TypeError, ValueError):
                scores.append(1.0)
        confidence = max(scores) if scores else 0.0
    state["confidence"] = confidence

    verdict = None
    if has_floor:
        verdict = verify_grounding(state, llm=llm)

    if verdict and verdict["verdict"] == "grounded":
        state["verified"] = True
        state["needs_retry"] = False
        reason = verdict["reason"] or trace_text(
            state.get("lang", "en"), "verifier_default_reason")
        _add_trace(state, "verifier", "verifier_grounded", reason=reason,
                   conf="%.2f" % confidence)
        return state

    if verdict:
        # A model saw something the score threshold could not see.
        state["verified"] = False
        reason = verdict["reason"] or trace_text(
            state.get("lang", "en"), "verifier_default_reason")
        if retries < MAX_RETRIES:
            state["retries"] = retries + 1
            state["needs_retry"] = True
            if verdict["next_queries"]:
                state["next_queries"] = verdict["next_queries"]
            _add_trace(state, "verifier", "verifier_retry", reason=reason,
                       n=retries + 1, max=MAX_RETRIES)
        else:
            state["needs_retry"] = False
            _add_trace(state, "verifier", "verifier_no_retries", reason=reason)
        return state

    # No judge: the old threshold behaviour, unchanged.
    if has_floor:
        state["verified"] = True
        state["needs_retry"] = False
        _add_trace(state, "verifier", "verifier_threshold_ok",
                   conf="%.2f" % confidence)
    elif retries < MAX_RETRIES:
        state["verified"] = False
        state["retries"] = retries + 1
        state["needs_retry"] = True
        _add_trace(state, "verifier", "verifier_thin",
                   n=retries + 1, max=MAX_RETRIES)
    else:
        state["verified"] = False
        state["needs_retry"] = False
        _add_trace(state, "verifier", "verifier_thin_out", n=MAX_RETRIES)
    return state


DISCLAIMER = {
    "en": "General information only, not legal advice. Please consult a lawyer "
          "for your specific situation.",
    "hi": "केवल सामान्य जानकारी, कानूनी सलाह नहीं। अपनी स्थिति के लिए कृपया "
          "वकील से सलाह लें।",
    "kn": "ಕೇವಲ ಸಾಮಾನ್ಯ ಮಾಹಿತಿ, ಕಾನೂನು ಸಲಹೆಯಲ್ಲ. ನಿಮ್ಮ ಪರಿಸ್ಥಿತಿಗೆ ದಯವಿಟ್ಟು "
          "ವಕೀಲರನ್ನು ಸಂಪರ್ಕಿಸಿ.",
}


OOS_REDIRECT = {
    "en": "This question is outside my family-law scope (land, property, criminal, tax, etc.). I only assist with marriage, divorce, custody, maintenance, adoption, succession, and domestic violence. Please consult a specialist for this topic.",
    "hi": "यह प्रश्न मेरे पारिवारिक कानून के दायरे से बाहर है (भूमि, संपत्ति, आपराधिक, कर, आदि)। मैं केवल विवाह, तलाक, अभिरक्षा, भरण-पोषण, गोद लेना, उत्तराधिकार और घरेलू हिंसा में सहायता करता हूँ। कृपया इस विषय के लिए विशेषज्ञ से परामर्श करें।",
    "kn": "ಈ ಪ್ರಶ್ನೆಯು ನನ್ನ ಕುಟುಂಬ ಕಾನೂನಿನ ವ್ಯಾಪ್ತಿಯಿಂದ ಹೊರಗಿದೆ (ಭೂಮಿ, ಆಸ್ತಿ, ಕ್ರಿಮಿನಲ್, ತೆರಿಗೆ ಇತ್ಯಾದಿ). ನಾನು ವಿವಾಹ, ವಿಚ್ಛೇದನ, ಪಾಲನೆ, ಜೀವನಾಂಶ, ದತ್ತು, ಉತ್ತರಾಧಿಕಾರ ಮತ್ತು ಕೌಟುಂಬಿಕ ಹಿಂಸೆಯಲ್ಲಿ ಮಾತ್ರ ಸಹಾಯ ಮಾಡುತ್ತೇನೆ. ದಯವಿಟ್ಟು ಈ ವಿಷಯಕ್ಕಾಗಿ ತಜ್ಞರನ್ನು ಸಂಪರ್ಕಿಸಿ.",
}

LOW_CONFIDENCE_DISCLAIMER = {
    "en": "Caution: this answer has lower verification confidence. Please consult a lawyer for your specific situation before acting.",
    "hi": "सावधानी: इस उत्तर का सत्यापन विश्वास कम है। कृपया कार्य करने से पहले अपनी स्थिति के लिए वकील से सलाह लें।",
    "kn": "ಎಚ್ಚರಿಕೆ: ಈ ಉತ್ತರದ ಪರಿಶೀಲನೆಯ ವಿಶ್ವಾಸ ಕಡಿಮೆ. ಕ್ರಮವಿರುವ ಮೊದಲು ನಿಮ್ಮ ನಿರ್ದಿಷ್ಟ ಪರಿಸ್ಥಿತಿಗೆ ವಕೀಲರನ್ನು ಸಂಪರ್ಕಿಸಿ.",
}

# What the reader is told when the retrieval produced nothing usable. This is
# the answer they get when the Acts have no answer and the web came back empty,
# and it was written in English for every language — so a Hindi reader got a
# Hindi disclaimer attached to three English sentences they could not read.
# Three sentences, all localised, same order.
NO_EVIDENCE = {
    "en": "I could not confirm this with the family-law acts I have.",
    "hi": "मेरे पास कानूनों की किताबें हैं, लेकिन इस सवाल का उत्तर मैं उनसे पक्का नहीं बना सका।",
    "kn": "ನನ್ನ ಬಳಿ ಕಾನೂನಿನ ಪುಸ್ತಕಗಳಿವೆ, ಆದರೆ ಈ ಪ್ರಶ್ನೆಯ ಉತ್ತರವನ್ನು ಅವುಗಳಿಂದ ಖಚಿತಪಡಿಸಲು ಸಾಧ್ಯವಾಗಿಲ್ಲ.",
}

DIVORCE_ACT_LIST = {
    "en": "Divorce in India generally falls under the Hindu Marriage Act "
          "(Section 13/13B), the Special Marriage Act, or the Indian Divorce "
          "Act depending on religion and marriage type.",
    "hi": "भारत में तलाक आमतौर पर हिंदू विवाह अधिनियम (धारा 13/13B), विशेष विवाह अधिनियम, "
          "या भारतीय तलाक अधिनियम के अंतर्गत आता है — यह आपके धर्म और विवाह के प्रकार पर निर्भर करता है।",
    "kn": "ಭಾರತದಲ್ಲಿ ವಿಚ್ಛೇದನೆಯು ಸಾಮಾನ್ಯವಾಗಿ ಹಿಂದೂ ವಿವಾಹ ಕಾಯ್ದೆ (ವಿಭಾಗ 13/13B), ವಿಶೇಷ "
          "ವಿವಾಹ ಕಾಯ್ದೆ, ಅಥವಾ ಭಾರತೀಯ ವಿಚ್ಛೇದನ ಕಾಯ್ದೆಯಡಿ ಬರುತ್ತದೆ — ಇದು ನಿಮ್ಮ ಧರ್ಮ "
          "ಮತ್ತು ಮದುವೆಯ ರೀತಿಯನ್ನು ಅವಲಂಬಿಸಿರುತ್ತದೆ.",
}

NO_EVIDENCE_ASK = {
    "en": "Please tell me the exact Act or section if you know it, or speak to "
          "a family-law lawyer about your situation.",
    "hi": "अगर आपको कोई अधिनियम या धारा का नाम पता है तो बताएँ, या अपनी स्थिति के लिए "
          "पारिवारिक कानून के वकील से बात करें।",
    "kn": "ನಿಮಗೆ ಯಾವುದೇ ಕಾಯ್ದೆ ಅಥವಾ ವಿಭಾಗದ ಹೆಸರು ತಿಳಿದಿದ್ದರೆ ಹೇಳಿ, ಅಥವಾ ನಿಮ್ಮ "
          "ಪರಿಸ್ಥಿತಿಗಾಗಿ ಕುಟುಂಬ ಕಾನೂನು ವಕೀಲರನ್ನು ಸಂಪರ್ಕಿಸಿ.",
}

NOT_FULLY_VERIFIED = {
    "en": "Note: I could not fully verify this answer against the sections I "
          "retrieved. Treat it as a starting point, not a confirmed position — "
          "check with a lawyer before you act on it.",
    "hi": "नोट: मैं इस उत्तर को प्राप्त अनुच्छेदों के विरुद्ध पूरी तरह सत्यापित नहीं कर सका। इसे केवल शुरुआती बिंदु मानें, पुष्टि नहीं — कार्रवाई से पहले वकील से जाँच कराएँ।",
    "kn": "ಗಮನಿಸಿ: ನಾನು ಈ ಉತ್ತರವನ್ನು ಪಡೆದ ವಿಭಾಗಗಳ ವಿರುದ್ಧ ಸಂಪೂರ್ಣವಾಗಿ ಪರಿಶೀಲಿಸಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ. ಇದನ್ನು ಆರಂಭಿಕ ಬಿಂದು ಎಂದು ಪರಿಗಣಿಸಿ, ಖಚಿತ ಸ್ಥಿತಿ ಎಂದು ಅಲ್ಲ — ಕ್ರಮವಿರುವ ಮೊದಲು ವಕೀಲರಿಂದ ಪರಿಶೀಲಿಸಿಕೊಳ್ಳಿ.",
}

# Fallback only. In persona testing this same sentence appeared under every
# answer, which made Saathi read like a form letter rather than a person. The
# model now writes next steps from the passages; this is what remains when there
# is no model to ask.
NEXT_STEPS = {
    # No leading "Next steps:" label: this text always renders under a
    # "What to do next" heading, so the label read "What to do next — Next
    # steps: gather…".
    "en": "Gather the relevant documents — your marriage certificate, any court orders — and speak with a family-law lawyer about your specific situation.",
    "hi": "प्रासंगिक दस्तावेज़ (विवाह प्रमाणपत्र, न्यायालय आदेश) इकट्ठा करें और अपनी विशेष स्थिति के लिए पारिवारिक कानून के वकील से बात करें।",
    "kn": "ಸಂಬಂಧಿತ ದಾಖಲೆಗಳನ್ನು (ಮದುವೆ ಪ್ರಮಾಣಪತ್ರ, ನ್ಯಾಯಾಲಯದ ಆದೇಶಗಳು) ಸಂಗ್ರಹಿಸಿ ಮತ್ತು ನಿಮ್ಮ ನಿರ್ದಿಷ್ಟ ಪರಿಸ್ಥಿತಿಯ ಬಗ್ಗೆ ಕುಟೂಬ ಕಾನೂನು ವಕೀಲರನ್ನು ಸಂಪರ್ಕಿಸಿ.",
}

# Section headings. These were English in every answer, so a Hindi or Kannada
# reply opened with two Hindi paragraphs, then "What the law says", then two
# more Hindi paragraphs — reading as one document badly stitched together.
# The quoted passages below stay in English on purpose: they are the bare act,
# and the citation beside them is what makes them usable.
SECTION_HEADINGS = {
    "en": ("What the law says", "What to do next"),
    "hi": ("कानून क्या कहता है", "आगे क्या करें"),
    "kn": ("ಕಾನೂನು ಏನು ಹೇಳುತ್ತದೆ", "ಮುಂದೆ ಏನು ಮಾಡಬೇಕು"),
}


def headings_for(lang: str) -> Tuple[str, str]:
    return SECTION_HEADINGS.get(lang, SECTION_HEADINGS["en"])


def strip_next_steps(answer: str) -> str:
    """Remove the appended next-steps block so it can be regenerated.

    Used when the model is asked to write next steps itself: it must not be
    shown the old boilerplate or it will echo it.
    """
    text = re.sub(
        r"\n*###+\s*What to do next\s*\n+.*?(?=\n*\*[A-Z]|\Z)",
        "", answer or "", flags=re.DOTALL | re.IGNORECASE)
    return (text or "").strip()


# Words a sentence cannot end on. A generation that runs out of tokens partway
# through stops on one of these, and the reader gets a dangling clause with no
# way to tell it is broken — "…entitled to maintenance [1]. Therefore," followed
# by an unrelated heading is what a person sees and cannot interpret.
_DANGLING = (
    "therefore", "because", "however", "which means", "and also", "so that",
    "since", "although", "unless", "while", "whereas", "that is", "in other "
    "words", "for example", "such as", "namely", "i.e", "e.g", "also",
    "but", "yet", "and", "or", "as", "if", "when", "than", "then",
)


def truncated_mid_sentence(text: str) -> bool:
    """True when a generation stops on a dangling connective.

    Only the part before any trailing "What to do next" is judged: that section
    is allowed to end in a bullet, and the disclaimer after it ends in a full
    stop.
    """
    body = strip_next_steps(text or "")
    # The disclaimer is a fixed string that always ends properly.
    body = re.split(r"\n\s*\*[^*]{20,}\*\s*$", body)[0]
    body = body.strip().rstrip("*_ ").strip()
    if not body:
        return False
    # A complete answer ends in a full stop, question mark, colon, or a list item.
    if re.search(r"[.?!:•*-]\s*$", body):
        return False
    # Cut on the last clause boundary so "…maintenance [1]. Therefore," is read
    # as ending on "Therefore," rather than on the earlier full stop.
    tail = re.split(r"(?<=[.!?])\s", body)[-1].strip().lower()
    tail = tail.strip("*_ —-·:;,")
    if not tail:
        return False
    last = tail.split()[-1].rstrip(".,;:!?")
    return any(last == d or tail.startswith(d + " ") or
               last in d.split() for d in _DANGLING)


def strip_reasoning_leak(text: str) -> str:
    """Remove chain-of-thought leakage from small translation models.

    qwen-2.5-7b often thinks aloud ("We need to translate…", "Let's parse…")
    and echoes the English source in a fenced block instead of returning only
    the translation. Strip those markers; keep the actual answer.
    """
    if not text:
        return text
    # Drop fenced code blocks that echo the English source answer.
    no_fence = re.sub(r"```.*?```", "", text, flags=re.DOTALL).strip()
    candidate = no_fence if no_fence.strip() else text
    leak_re = re.compile(
        r"^(we need to|we have the|actually the|let'?s parse|let us parse|"
        r"so we need|also keep|the rest of|we need to output|the user says|"
        r"we need to produce|we need to translate|here is the translation"
        r"|translation:)\b.*$",
        re.IGNORECASE)
    lines = [ln for ln in candidate.splitlines()
             if not leak_re.match(ln.strip())]
    cleaned = "\n".join(lines).strip()
    # If stripping removed everything, fall back to stripping only fences.
    return cleaned or no_fence.strip() or text.strip()


# The opening line of an answer written without a model.
#
# This is what a user sees when no provider is reachable, which is exactly when
# they most need the reply to read like help. The old text was a third-person
# summary of a topic — "For custody, the Guardians & Wards Act decides..." — which
# described the law without addressing the person who asked. These name their
# situation instead.
#
# Kept as separate single-line entries on purpose: a wrapped multi-line string
# literal is easy to break here and hard to spot.
TOPIC_SUMMARY = {
    "divorce": {
        "en": "Divorce in India follows two routes, and which one applies to you changes what you need to file. Here is the provision that governs it.",
        "hi": "भारत में तलाक के दो रास्ते हैं, और आपके लिए कौन सा लागू होता है यह बदल देता है कि आपको क्या दाखिल करना है। यहाँ वह धारा दी गई है।",
        "kn": "ಭಾರತದಲ್ಲಿ ವಿಚ್ಛೇದನೆಗೆ ಎರಡು ಮಾರ್ಗಗಳಿವೆ, ನಿಮಗೆ ಯಾವುದು ಅನ್ವಯವಾಗುತ್ತದೆ ಎಂಬುದೇ ನೀವು ಏನು ಸಲ್ಲಿಸಬೇಕೆಂದು ನಿರ್ಧರಿಸುತ್ತದೆ. ಅದರ ಕಲಂಕ ಇಲ್ಲಿ ಇದೆ.",
    },
    "maintenance": {
        "en": "If maintenance has stopped, the law lets you ask the family court to order it. Here is the provision that applies to you.",
        "hi": "यदि भरण-पोषण बंद हो गया है, तो कानून आपको परिवार न्यायालय से इसका आदेश माँगने देता है। यहाँ आप पर लागू धारा दी गई है।",
        "kn": "ಭರವಸೂ ನಿಲ್ಲಿದರೆ, ಕಾನೂನು ನೀವು ಕುಟುಂಬ ನ್ಯಾಯಾಲಯದಲ್ಲಿ ಆದೇಶ ಕೋರಲು ಅನುಮತಿ ನೀಡುತ್ತದೆ. ನಿಮಗೆ ಅನ್ವಯವಾಗುವ ಕಲಂಕ ಇಲ್ಲಿ ಇದೆ.",
    },
    "custody": {
        "en": "Custody is decided by what is best for your child, not by who wants it more or who earns more. Here is the provision that decides it.",
        "hi": "अभिरक्षा यह तय होती है कि बच्चे के हित में क्या है, न कि यह कि कौन ज़्यादा चाहता है या कमाता है। यहाँ वह धारा दी गई है।",
        "kn": "ಪಾಲನೆಯ ನಿರ್ಧಾರವು ಮಗುವಿನ ಕಲ್ಯಾಣದ ಆಧಾರದ ಮೇಲೆ, ಯಾರು ಹೆಚ್ಚು ಬೇಕು ಎಂಬುದರ ಮೇಲೆ ಅಲ್ಲ. ಅದನ್ನು ನಿರ್ಧರಿಸುವ ಕಲಂಕ ಇಲ್ಲಿ ಇದೆ.",
    },
    "adoption": {
        "en": "Adoption has strict conditions and they are not optional. Here is the provision that governs who may adopt, and who may be adopted.",
        "hi": "गोद लेने की कठोर शर्तें हैं और वह वैकल्पिक नहीं हैं। यहाँ वह धारा दी गई है जो बताती है कि कौन गोद ले सकता है।",
        "kn": "ದತ್ತು ಪಡೆಯುವುದು ಕಠಿಣ ನಿಯಮಗಳಿಗೆ ಒಳಗಾಗಿದೆ ಮತ್ತು ಅವು ಐಚ್ಛಿಕವಲ್ಲ. ಯಾರು ದತ್ತು ಪಡೆಯಬಹುದು ಎಂಬುದನ್ನು ನಿರ್ಧರಿಸುವ ಕಲಂಕ ಇಲ್ಲಿ ಇದೆ.",
    },
    "succession": {
        "en": "Who inherits is fixed by statute, not by what the family agrees. Here is the provision that decides your share.",
        "hi": "उत्तराधिकार कानून से तय होता है, परिवार की सहमति से नहीं। यहाँ वह धारा दी गई है जो आपका हिस्सा तय करती है।",
        "kn": "ಉತ್ತರಾಧಿಕಾರ ಕಾನೂನಿನಿಂದ ನಿರ್ಧರಿಸಲ್ಪಡುತ್ತದೆ, ಕುಟುಂಬದ ಒಮ್ಮತಿಯಿಂದಲ್ಲ. ನಿಮ್ಮ ಪಾಲು ನಿರ್ಧರಿಸುವ ಕಲಂಕ ಇಲ್ಲಿ ಇದೆ.",
    },
    "domestic_violence": {
        "en": "You do not have to tolerate this. The law gives you specific remedies, and you do not need a lawyer to ask for them.",
        "hi": "आपको यह सहन नहीं करना पड़ेगा। कानून आपको विशेष उपचार देता है, और उनके लिए माँगने के लिए वकील ज़रूरी नहीं है।",
        "kn": "ನೀವು ಇದನ್ನು ಸಹಿಕೊಳ್ಳಬೇಕಿಲ್ಲ. ಕಾನೂನು ನಿಮಗೆ ನಿರ್ದಿಷ್ಟ ಪರಿಹಾರ ನೀಡುತ್ತದೆ, ಮತ್ತು ಅವುಗಳನ್ನು ಕೋರಲು ವಕೀಲ ಅಗತ್ಯವಿಲ್ಲ.",
    },
    "marriage": {
        "en": "What makes a marriage valid is fixed by statute. Here is the provision that applies to your question.",
        "hi": "विवाह को वैध बनाने की शर्तें कानून से तय हैं। यहाँ आपके प्रश्न पर लागू धारा दी गई है।",
        "kn": "ವಿವಾಹ ಮಾನ್ಯವಾಗುವುದು ಎಂಬುದು ಕಾನೂನಿನಿಂದ ನಿರ್ಧರಿಸಲ್ಪಡುತ್ತದೆ. ನಿಮ್ನ ಪ್ರಶ್ನೆಗೆ ಅನ್ವಯವಾಗುವ ಕಲಂಕ ಇಲ್ಲಿ ಇದೆ.",
    },
    "general": {
        "en": "Here is the provision of law that applies to your question.",
        "hi": "आपके प्रश्न पर लागू कानून की धारा यहाँ दी गई है।",
        "kn": "ನಿಮ್ನ ಪ್ರಶ್ನೆಗೆ ಅನ್ವಯವಾಗುವ ಕಾನೂನಿನ ಕಲಂಕ ಇಲ್ಲಿ ಇದೆ.",
    },
}


def topic_opening(topic: str, lang: str) -> str:
    """The opening line for the no-model path, in the user's language."""
    bank = TOPIC_SUMMARY.get(topic, TOPIC_SUMMARY["general"])
    return bank.get(lang, bank["en"])


# Ingestion stamps every chunk with a provenance header and leaves markdown
# noise in the text. Both were reaching the user verbatim, which is what made
# an answer read like a database dump instead of advice.
_META_HEADER_RE = re.compile(r"^Act:.*?\n", re.DOTALL)
# The corpus prefixes each chunk with the chapter and the section on one line:
#   Chapter II: ADOPTION | Section 20: Maintenance of children and aged parents
# Both halves are metadata already shown in the citation, and they stopped the
# section-heading match below from ever firing, so the raw line reached the user.
_CHAPTER_PREFIX_RE = re.compile(r"^Chapter\s+[IVXLC0-9]+\s*:[^|\n]*\|", re.IGNORECASE)
_SECTION_LINE_RE = re.compile(
    r"^Section\s+\d+[A-Za-z\-]*\s*:\s*", re.IGNORECASE)
# "Title .―(1)Body" — the separator between a heading and its body. Deliberately
# excludes the ASCII hyphen: "widowed daughter in-law" is body text, not a joiner.
_HEADING_JOIN_RE = re.compile(r"[ \t.]*[―—][ \t]*")
# Bare markdown heading markers and the CHAPTERN banner the corpus leaves inline.
_MARKDOWN_NOISE_RE = re.compile(r"#{1,6}[ \t]*|[ \t]*#{1,6}")
_CHAPTER_BANNER_RE = re.compile(r"CHAPTER\s+[IVXLC0-9]+\b", re.IGNORECASE)


def plain_passage(text: str, limit: int = 160) -> str:
    """Clean one retrieved chunk for human reading.

    Strips the scraper header and the markdown residue from the act text,
    drops the title the chunk repeats twice, and collapses to one line. The
    cut lands on a clause boundary so an answer never ends mid-sentence.
    """
    body = (text or "").strip()
    body = _META_HEADER_RE.sub("", body, count=1)
    body = _CHAPTER_PREFIX_RE.sub("", body, count=1).lstrip()
    body = re.sub(r"\*\*([^*]+)\*\*", r"\1", body)       # **13B. ...**
    body = re.sub(r"\*\*+", "", body)                    # unbalanced residue
    # A subsection marker lost its trailing space in the scrape: "(1)Subject".
    # Put it back, or the first clause runs into the sub-section number.
    body = re.sub(r"\(\s*_?(\d+[A-Za-z]*)_?\s*\)", r" (\1) ", body)
    body = re.sub(r"(?<![\w])_+([^_]+?)_+(?![\w])", r"\1", body)  # _i_

    body = _MARKDOWN_NOISE_RE.sub(" ", body)
    body = _CHAPTER_BANNER_RE.sub(" ", body)

    # A chunk that begins mid-word is a bad split, not a passage. "rty (1) The
    # Court may direct..." reads as corrupted text, which is worse to a person
    # asking about their child than one citation fewer.
    if re.match(r"^[a-z]{1,4}[ \t]+\(", body):
        return ""

    # Collapse to one line before touching the heading. The corpus wraps a long
    # section title across two lines, so matching on line boundaries left the
    # second half of the word ("...and prope" / "rty") stranded at the front of
    # the passage.
    body = re.sub(r"\s+", " ", body).strip()

    # Drop the heading itself: the citation above already names the section, and
    # the text before the em dash is title, not law. If nothing follows the dash
    # the chunk was only a heading, and there is nothing worth quoting.
    m = _SECTION_LINE_RE.match(body)
    if m:
        body = body[m.end():]
        parts = _HEADING_JOIN_RE.split(body, maxsplit=1)
        title = parts[0].strip(" .")
        rest = parts[1] if len(parts) > 1 else ""
        if not rest.strip():
            # The chunk was only a heading. There is nothing here worth quoting,
            # and printing the heading alone would repeat the citation.
            return ""
        # The metadata line often previews the paragraph after it. Print one, not
        # both, or the answer stutters.
        echo = re.compile(r"(?:\d+[A-Za-z\-]*\.[ \t]*)?" + re.escape(title))
        at = echo.search(rest)
        body = rest[at.start():] if at and rest[at.start():].strip() else rest
        if at:
            body = echo.sub("", body, count=1)
        body = _HEADING_JOIN_RE.sub(" ", body, count=1).strip(" .")

    one_line = body.strip(" -–—")
    if not one_line:
        return ""
    return clip(one_line, limit)


# A quoted passage has to stop somewhere, and where it stops decides whether
# the reader sees a rule or a broken word. Three shapes were all wrong:
#
#   "…or a male child…"        cut a word in half mid-clause
#   "…from the shared…"        cut the last useful word of the passage
#   "…Section 2 —" (nothing)  the passage was all heading, so nothing to show
#
# A person asking about domestic violence cannot tell those apart from a
# broken app. So the clip prefers the last complete sentence, then the last
# clause, and only ever breaks on a space.
def clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text

    # 1. A whole sentence inside the budget. Best case: nothing is cut at all.
    #    A full stop only: a semicolon inside "(a) insults … or (b) commits …"
    #    is a clause in the middle of a list, and stopping there loses the rest
    #    of the rule the section is actually listing.
    for end in reversed([m.end() for m in re.finditer(r"\.\s", text[:limit])]):
        snippet = text[:end].strip()
        if len(snippet) >= limit * 0.45:
            return snippet

    # 2. No sentence ends in range. Take the last clause boundary that keeps
    #    most of the passage — a cut mid-clause reads as a missing half-rule.
    window = text[:limit]
    for sep in ("; ", ", ", " and ", " or ", " which ", " namely "):
        idx = window.rfind(sep)
        if idx > limit * 0.5:
            return window[:idx].rstrip(" ,;:-") + "…"

    # 3. Nothing but word boundaries. Break on the last space so the passage
    #    never ends on half a word, and mark that it was shortened.
    idx = window.rfind(" ")
    if idx > 0:
        return window[:idx].rstrip(" ,;:-") + "…"
    return window.rstrip() + "…"


def _short_meaning(text: str, limit: int = 160) -> str:
    return plain_passage(text, limit=limit)


def compose_answer(state: Dict[str, Any],
                   written: str = "") -> Tuple[str, List[str], List[str]]:
    evidence = state.get("evidence", [])
    lang = state.get("lang", "en")
    tone = state.get("tone", "simple")
    # Out-of-scope redirect takes precedence
    if state.get("oos_redirect"):
        return (OOS_REDIRECT.get(lang, OOS_REDIRECT["en"]), [], [])
    # Unverified / no-citation block: never return an uncited answer
    if not evidence_sufficient(evidence) and not state.get("verified"):
        # Strong redirect when verifier failed after retries
        base = NO_EVIDENCE.get(lang, NO_EVIDENCE["en"])
        if state.get("slots", {}).get("topic") == "divorce":
            base += (" " + DIVORCE_ACT_LIST.get(lang, DIVORCE_ACT_LIST["en"]))
        base += (" " + NO_EVIDENCE_ASK.get(lang, NO_EVIDENCE_ASK["en"]))
        return base + "\n\n" + DISCLAIMER.get(lang, DISCLAIMER["en"]) + "\n\n" + LOW_CONFIDENCE_DISCLAIMER.get(lang, LOW_CONFIDENCE_DISCLAIMER["en"]), [], []
    citations = [format_citation((h.get("payload") or {}) if isinstance(h, dict)
                                 else {}) for h in evidence[:5]]
    citations = [c for c in citations if c]
    citation_sources = [
        _evidence_source_type(h) if isinstance(h, dict) else "bare_act"
        for h in evidence[:5]
    ]
    slots = state.get("slots", {})
    topic = slots.get("topic", "general")
    disclaimer = DISCLAIMER.get(lang, DISCLAIMER["en"])
    next_steps = NEXT_STEPS.get(lang, NEXT_STEPS["en"])
    confidence = float(state.get("confidence", 1.0))
    low_warn = ""
    if not state.get("verified"):
        # The verifier read the draft and did not sign it off — either it ran
        # out of retries, or there was no model to judge it. Either way the
        # user is getting an answer we could not confirm, and must be told.
        # Keying this on `verified` rather than on confidence is deliberate: a
        # rejected draft can still have a strong retrieval score, and a 0.9
        # score is not evidence that the prose built on it is sound.
        low_warn = "\n\n> " + NOT_FULLY_VERIFIED.get(lang,
                                                     NOT_FULLY_VERIFIED["en"])
    elif confidence < 0.7:
        low_warn = "\n\n> " + LOW_CONFIDENCE_DISCLAIMER.get(
            lang, LOW_CONFIDENCE_DISCLAIMER["en"])

    body = written.strip()
    heading_law, heading_next = headings_for(lang)
    if body and truncated_mid_sentence(body):
        # The generation ran out of tokens mid-clause. Ship the cited passages
        # instead: they are whole sentences, and an answer that stops on
        # "Therefore," reads as broken rather than as truncated.
        body = ""

    if body:
        # The model wrote a plain-language explanation grounded in the passages
        # above. Show it as the answer; the passages themselves belong in the
        # Sources list, not in the body.
        #
        # The model is asked to write its own "What to do next" section, because
        # the fixed boilerplate appeared under every answer and made the product
        # read like a form. Only append the boilerplate when the model did not.
        if not re.search(r"what to do next", body, re.IGNORECASE) and \
                not re.search("###+\\s*%s" % re.escape(heading_next), body):
            body = "%s\n\n### %s\n\n%s" % (body, heading_next, next_steps)
        answer = "%s%s\n\n*%s*" % (body, low_warn, disclaimer)
    else:
        # No model available. Still answer as prose addressed to the person, then
        # list the passages. This is precisely when a user most needs the reply
        # to read like help, and it used to open with the heading "Quick answer"
        # and a third-person summary that never mentioned their situation.
        #
        # These passages get 320 characters, not the 160 a citation preview uses.
        # With no model there is no summary to carry the point, so the quoted text
        # is the answer — and at 160 it cut off exactly the operative words.
        # s.17 lost "welfare of the minor shall be the first consideration";
        # s.8 lost "class I of the Schedule".
        #
        # A passage that cleans down to nothing (the chunk was only a section
        # heading) used to render as "- **[3] … — Section 2 —**": a numbered
        # point with no content, which reads as a bug rather than as a law. The
        # reader gets the sections that actually say something; the Sources list
        # below still carries every citation, so nothing is hidden.
        lines = []
        for i, h in enumerate(evidence[:5], start=1):
            payload = h.get("payload", {}) if isinstance(h, dict) else {}
            meaning = _short_meaning((payload or {}).get("text", ""), limit=320)
            if not meaning:
                continue
            lines.append("- **[%d] %s** — %s"
                         % (i, format_citation(payload), meaning))
        answer = (
            "%s\n\n"
            "### %s\n\n%s\n\n"
            "### %s\n\n%s%s\n\n"
            "*%s*"
            % (topic_opening(topic, lang), heading_law, "\n".join(lines),
               heading_next, next_steps, low_warn, disclaimer))
    return answer, citations, citation_sources


TONE_GUIDE = {
    "simple": "Keep it short — 3 to 5 short sentences. Skip legal jargon. "
              "If you must use a term like 'petition', explain it in the same "
              "sentence. Prefer a couple of clear sentences over a long list.",
    "detailed": "Give a fuller but still plain explanation — 5 to 8 sentences. "
                "Name the sections you rely on, but explain what each one means "
                "in ordinary words. Bullets under a heading are welcome here.",
}

# How long the answer should be, decided by the question rather than by a
# setting. A tone switch cannot tell "what is the minimum age to marry?" from a
# paragraph describing a marriage, a child and a beating — and those two want
# opposite lengths. Padding a one-line question is what made it unreadable;
# starving a described situation is what made it useless.
#
# Signals, in order of how much they matter:
#   - a short question with no situation in it  -> one fact -> brief
#   - a long question, or one describing people and events -> full
#   - everything else -> normal
_SITUATION_RE = re.compile(
    r"\b(my|our|his|her|their)\b|,|;|\b(and|but|after|since|because|while)\b|"
    r"\b(19|20)\d{2}\b|\b(day|days|week|weeks|month|months|year|years)\b",
    re.IGNORECASE)


def answer_length(query_en: str) -> str:
    """'brief', 'normal' or 'full' — how much this question deserves."""
    text = (query_en or "").strip()
    words = text.split()
    if not words:
        return "normal"
    situation = bool(_SITUATION_RE.search(text))
    if len(words) <= 8 and not situation:
        return "brief"
    if len(words) >= 25 or situation:
        return "full"
    return "normal"


ANSWER_LENGTH_RULES = {
    "brief": (
        "Length: SHORT. The reader asked for one fact. Two or three sentences "
        "answer it, with the section in brackets. No background, no options they "
        "did not ask for, no padding. One step under 'what to do next' is "
        "enough."),
    "normal": (
        "Length: MEDIUM. Three to five short paragraphs. Answer the question, "
        "say what the rule means for this person, then two or three concrete "
        "steps. Stop when you have said it."),
    "full": (
        "Length: FULL, but still plain. Four to seven short paragraphs. The "
        "reader described a situation with several facts, so cover each one that "
        "the passages support: what the law says, how it applies to them, and "
        "what to do next. Use a short heading with bullets when there is a real "
        "list — conditions, grounds, documents — and flowing prose when there "
        "is not. Never pad a point you have already made."),
}


# A follow-up in a conversation that is already going. Without this the model
# restated the previous answer, which is the first thing a reader notices in a
# chat — and it doubled the reading for someone asking one narrow thing.
FOLLOW_UP_RULES = (
    "- This is a FOLLOW-UP in a conversation already going. Answer only what "
    "was just asked, using what came before. Do not restate the earlier answer "
    "and do not open with 'as mentioned above'. One short line showing you "
    "remember the situation is enough, then answer this question.\n"
)


# What the writing model was getting wrong, as a short list it can be held to.
# Screenshot evidence, each line: a real answer the user read and could not use.
#
#   "any act, omission or commission or conduct of the respondent shall
#    constitute domestic violence"          — Latin, and "respondent" is nobody
#   "the aggrieved person"                   — a term with no everyday meaning
#   "pass a residence order"                 — what the reader should actually do
#   "(a) restraining the respondent from dispossessing … the aggrieved person
#    from the shared…"                        — cut off mid-word, mid-rule
#
# So: name the actor as a person, use the reader's own words for their problem,
# and end on something the reader can act on. The section number stays so the
# citation is still checkable.
PLAIN_LANGUAGE_RULES = (
    "Plain-language rules, all of them required:\n"
    "- Name people as people. 'She', 'he', 'your husband', 'the court'. Never "
    "'the respondent', 'the aggrieved person', 'the applicant', 'the minor'.\n"
    "- Say what the reader can DO, not what the court 'may' do. 'You can ask the "
    "court to order him to stay away from the home' — not 'a residence order may "
    "be passed'.\n"
    "- No Latin words, no 'notwithstanding', no 'provided that', no "
    "'sub-section', no 's.17'. Write 'Section 17' if a number is needed.\n"
    "- One idea per sentence, and keep sentences short.\n"
    "- Never leave a sentence unfinished. Never end mid-word or mid-clause.\n"
    "- Finish with the step the reader takes next, in the words they would use "
    "for it.\n"
)


def write_plain_answer(state: Dict[str, Any], llm: Callable) -> str:
    """Explain the retrieved law to a layperson, in English.

    Previously the body of the answer was the raw act text with an ingestion
    header attached, which read like a database dump. The model now writes the
    explanation itself, grounded strictly in the numbered passages, and cites
    them as [1], [2] so every claim still traces back to a section.

    Always written in English, then translated. Asking the 7B model to write
    Hindi or Kannada directly made it loop badly (it repeated a phrase dozens
    of times); it is far steadier at plain English, and translating that is
    the step it is actually good at.
    """
    tone = state.get("tone", "simple")
    passages = []
    for i, hit in enumerate(state.get("evidence", [])[:5], start=1):
        if not isinstance(hit, dict):
            continue
        payload = hit.get("payload") or {}
        body = plain_passage(str(payload.get("text", "") or ""), limit=600)
        if not body:
            continue
        passages.append("[%d] %s — %s" % (i, format_citation(payload), body))
    if not passages:
        return ""
    length = ANSWER_LENGTH_RULES[answer_length(
        state.get("query_en") or state.get("query", ""))]
    # A follow-up is a continuation, not a fresh question: the model must not
    # repeat what was already said two turns ago.
    follow_up = FOLLOW_UP_RULES if state.get("history") else ""
    system = (
        "You are LawSaathi, a patient family-law advisor speaking to a normal "
        "person in India — not a lawyer. Explain the law below the way a good "
        "lawyer would explain it across a table.\n\n"
        "Rules:\n"
        "- Write in English, in plain everyday words.\n"
        "- Answer only from the numbered passages. Never add a section, a "
        "provision or a fact that is not in them.\n"
        "- Talk to the user, never about your inputs. Do NOT write 'the "
        "passages', 'the provided text', 'the excerpts', 'the documents "
        "above', or 'I was given'. The user does not know those exist. Open "
        "by answering the question itself.\n"
        "- If the passages do not cover the question, still answer as far as "
        "they do, then say plainly what could not be confirmed — for example "
        "'the exact amount is not fixed by the Act' — rather than apologising "
        "for your sources.\n"
        "- Refer to a source as [1], [2] inline, right after the claim it "
        "supports. Use the numbers exactly as given.\n"
        "- If a passage is an AMENDMENT NOTICE, follow it. The consolidated "
        "statute text in the other passages is out of date. Never state a "
        "waiting period, separation period or timeline as the current rule "
        "from a passage that an amendment notice has flagged. Name the "
        "amending Act and tell the reader to confirm the current figures.\n"
        "- Do NOT reproduce the passages. Do NOT quote the acts. Do NOT use "
        "'the court may deem', 'provided that', or any wording lifted from the "
        "raw text. Explain the meaning instead.\n"
        "- Be direct and warm, like a person talking, not a form letter.\n"
        "- Use markdown when it genuinely helps: a short '##' heading with "
        "bullets underneath for steps, conditions, or a list of what counts "
        "as grounds. Write flowing paragraphs when it does not. Never use "
        "markdown just to fill space, and never repeat the same heading "
        "template every time.\n"
        "- Never repeat a sentence or phrase. Every sentence must be new.\n"
        "%s"
        "%s"
        "- End with a '### What to do next' heading and 2 or 3 short bullets of "
        "concrete steps that fit THIS person's situation. These must be specific "
        "to the question just asked — for a maintenance arrears question, the "
        "documents to gather and where to file; for a custody question, what the "
        "court weighs. Never write generic advice like 'consult a lawyer' on its "
        "own, and never repeat the same list twice in a row.\n"
        "Output ONLY the explanation.\n"
        "%s"
        "%s" % (PLAIN_LANGUAGE_RULES, follow_up, length,
                TONE_GUIDE.get(tone, TONE_GUIDE["simple"]))
    )
    user = ("Question: %s\n\nPassages:\n%s"
            % (state.get("query_en") or state.get("query", ""),
               "\n\n".join(passages)))
    try:
        text, provider = llm([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
    except Exception as e:  # noqa: BLE001 — template answer is the fallback
        logger.warning("agent plain answer failed (%r)", e)
        return ""
    state["provider"] = provider
    text = strip_reasoning_leak(text or "")
    # A refusal, a loop, or an empty response must not blank the answer.
    if not text or len(text) < 40 or looks_looped(text):
        logger.info("agent plain answer unusable (short or looping); using template")
        return ""
    # No trace here: node_reason owns the "reason" line for the Thinking panel,
    # and tracing from both places showed the step twice.
    return text


# Per-language plain-language guidance. The English draft is already good; the
# problem was that it was then *translated*, and translation preserves register
# exactly. A clean English sentence with "maintenance pendente lite" in it
# becomes a perfectly grammatical Hindi sentence with "मेंटेनेंस पेंडेंट लाइट"
# in it — still unreadable to the person who asked. So the non-English answer
# is rewritten from scratch in that language with the same simplicity budget,
# using the words people actually use, not carried over word for word.
#
# The glosses below are the everyday words for each Act we ingest. They are
# given as a swap table because naming the everyday word beats asking for
# "simpler" — a model asked to be simpler picks a shorter legal word; a model
# told "maintenance is मासगी or गुजारा" writes it that way.
LANG_PLAIN_RULES = {
    "hi": (
        "हिंदी में लिखो — ऐसी भाषा में जैसे कोई अपने परिवार के सदस्य से बात "
        "कर रहा हो, कानूनी किताब जैसी नहीं।\n"
        "हर कानूनी शब्द की जगह वह शब्द लिखो जो लोग रोज़ बोलते हैं:\n"
        "- maintenance = मासगी / गुजारा देना\n"
        "- alimony = निभान सामग्री\n"
        "- maintenance pendente lite = शादी अभी चल रही है, तब तक का खर्च\n"
        "- judicial separation = अलग रहना\n"
        "- restitution of conjugal rights = पति-पत्नी को साथ रहने का हक़\n"
        "- custody of the child = बच्चे के साथ किसे रहना है\n"
        "- guardianship = अभिभावकता\n"
        "- court / magistrate = अदालत / कोर्ट / मजिस्ट्रेट\n"
        "- family court = परिवार अदालत\n"
        "- petition / application / proceedings = आवेदन / अर्ज़ी / कानूनी कार्रवाई\n"
        "- order / judgment = आदेश / फ़ैसला\n"
        "- protection order = सुरक्षा आदेश\n"
        "- residence order = घर में रहने का आदेश\n"
        "- monetary relief = पैसे की मदद\n"
        "- shared household = वह घर जहाँ आप रहती हैं\n"
        "- police / FIR = पुलिस / प्रथम सूचना (एफआईआर)\n"
        "- lawyer / advocate = वकील\n"
        "- case = मामला / केस\n"
        "- proof / evidence = सबूत\n"
        "- dowry = दहेज\n"
        "- respondent / applicant = पति / पत्नी / वो / आप\n"
        "- petition / proceedings = आवेदन / कानूनी कार्रवाई\n"
        "- section / Act / amendment = धारा / अधिनियम / बदलाव\n"
        "- joint family / partition = संयुक्त परिवार / बँटवारा\n"
        "- 'the court may' = 'आप अदालत से कह सकती हैं कि…' — जो कर सकती हैं वो लिखो\n"
        "सीधे 'आप' (आपको, आपसे, आप कर सकती हैं) इस्तेमाल करो, 'एक व्यक्ति' या "
        "'पक्षकार' जैसे औपचारिक शब्द नहीं।"
    ),
    "kn": (
        "ಕನ್ನಡದಲ್ಲಿ ಬರೆ — ಕಾನೂನಿನ ಪುಸ್ತಕದಂತೆ ಅಲ್ಲ, ಮನೆಯ "
        "ಮನೆಯರ ಜೊತೆ ಮಾತನಾಡುವ ಹಾಗೆ.\n"
        "ಪ್ರತಿ ಕಾನೂನಿನ ಪದಕ್ಕೆ ಬದಲು ಜನಸಾಮಾನೆಯ ಪದವನ್ನು ಬರೆ:\n"
        "- maintenance = ಹೆಂಡತಿಗೆ/ಗಂಡನಿಗೆ ಕೊಡುವ ಹಣಕಾಸು (ಅನ್ನಧನ)\n"
        "- alimony = ವಿಚ್ಛೇದದ ನಂತರ ಪತಿ/ಪತ್ನಿಯಿಂದ ಪಡೆಯುವ ಹಣಕಾಸು\n"
        "- maintenance pendente lite = ಮದುಪೆ ಇನ್ನೂ ನಡೆಯುತ್ತಿರುವಾಗ ಆಗುವ ವೆಚ್ಚ\n"
        "- judicial separation = ವಿವಾಹವನ್ನು ಮುಂದುವರಿಸುವುದು\n"
        "- restitution of conjugal rights = ಸಂಗಾತಿಯನೊಂದಿಗೆ ಜೊತೆಗೆ ಬರುವ ಹಕ್ಕು\n"
        "- custody of the child = ಮಕು ಯಾರಲ್ಲಿ ಉಳಿಯಬೇಕು\n"
        "- respondent / applicant = ಗಂಡ / ಹೆಂಡತಿ / ಅವರು / ನೀವು\n"
        "- petition / proceedings = ಅರ್ಜಿ / ಕಾನೂನು ಪ್ರಕ್ರಿಯೆ\n"
        "- section / Act = ವಿಭಾಗ / ಕಾಯಿದೆ\n"
        "- guardianship = ಪಾಲಕತ್ವ\n"
        "- court / magistrate = ನ್ಯಾಯಾಲಯ / ಕೋರ್ಟ್ / ಮಜಿಸ್ಟ್ರೇಟ್\n"
        "- family court = ಕುಟುಂಬ ನ್ಯಾಯಾಲಯ\n"
        "- order / judgment = ಆದೇಶ / ತೀರ್ಪು\n"
        "- protection order = ರಕ್ಷಣಾ ಆದೇಶ\n"
        "- residence order = ಮನೆಯಲ್ಲಿ ಇರುವ ಆದೇಶ\n"
        "- monetary relief = ಹಣದ ಸಹಾಯ\n"
        "- shared household = ನೀವು ಬದುಕುವ ಮನೆ\n"
        "- police / FIR = ಪೊಲೀಸ್ / ಪ್ರಥಮ ಸೂಚನೆ (ಎಫ್ಐಆರ್)\n"
        "- lawyer / advocate = ವಕೀಲ\n"
        "- case = ಪ್ರಕರಣ\n"
        "- proof / evidence = ಸಾಕ್ಷಿ\n"
        "- dowry = ಸಂಪತ್ತು ಕೋಲಿಕೆ\n"
        "- joint family / partition = ಉಮ್ಮ / ವಿಂಗಡಣೆ\n"
        "- 'the court may' = 'ನೀವು ನ್ಯಾಯಾಲಯದಿಂದ ಕೋರಿಬಹುದು…' — ನೀವು ಮಾಡಬಹುದಾದದ್ದನ್ನು "
        "ಬರೆ\n"
        "ನೀವು/ನಿಮ್ಮ (you) ಬಳಸಿ, 'ಒಂದು ವ್ಯಕ್ತಿ' ಅಥವಾ 'ಪಕ್ಷಿ' ಹಾಗಿ "
        "ಔಪಚಾರಿಕ ಪದಗಳನ್ನು ಬಳಸಬೇಡಿ."
    ),
}

# Rules that apply whichever language the answer is written in. Kept separate
# from LANG_PLAIN_RULES because the English draft already follows them.
NATIVE_SIMPLICITY_RULES = (
    "Before you answer, read this: the reader is a normal person who has "
    "never opened a legal book. They are upset, or worried about money, and "
    "they want to know what to do.\n"
    "- One idea per sentence. Most sentences under 12 words.\n"
    "- No semicolons, no parentheses, no lists of three or more commas. If a "
    "sentence needs a bracket, split it into two sentences.\n"
    "- Never use a legal term you have not just explained in the same "
    "sentence, in the everyday words.\n"
    "- Speak to the reader as 'you'. Warm, direct, calm. No formality, no "
    "passive voice hiding who must act.\n"
    "- Never repeat a sentence or phrase. Every sentence must be new.\n"
    "- Write in the reader's SCRIPT. Every ordinary word goes in Devanagari "
    "or Kannada, never in Latin letters. A loanword people really use is "
    "fine - write it in the reader's script. Latin letters are allowed only "
    "inside an Act name and a section number.\n"
    "- The only English words allowed are an Act name, a section number, and "
    "a place name the reader would say the same way. If a word has a word "
    "in the reader's language, use that one.\n"
    "- Never stop mid-sentence. Every sentence you start, you finish.\n"
    "- Do NOT follow the English sentence order. Say each point the way you "
    "would say it out loud, in the order that sounds natural in the "
    "reader's language. Two English sentences may become one; one may "
    "become two. What must not change is the facts, the numbers and the "
    "[1] [2] markers.\n"
)

# "What to do next" in the reader's language, and the other half of that
# heading. compose_answer only recognizes the English string or the exact
# localized heading, so a rewrite that came back with its own translation of
# the heading ("अगला क्या करें" against "आगे क्या करें") had the boilerplate
# next-steps appended under a second heading. The heading is now dictated, not
# left to the model.
def _next_steps_heading(lang: str) -> str:
    return headings_for(lang)[1]


# A body that stops mid-clause. truncated_mid_sentence() only knows English
# connectives, so a Hindi rewrite cut off at "इसलिए लड़की की शादी की" passed it
# and shipped a broken answer. What is actually being checked here is simpler
# and script-independent: does the text end on a finished sentence at all?
_ENDS_A_SENTENCE = ".!?।॥۔…:;\"')]}"


def ends_mid_sentence(text: str) -> bool:
    """True when the last line stops before finishing.

    The English-only version cannot see this in Devanagari or Kannada, and the
    failure it misses is the worst kind: an answer that trails off mid-clause
    looks broken rather than truncated, and a user cannot tell the difference.

    Bullets count. A live Hinglish rewrite stopped at "...वह आपके घर या काम के
    पास न" — a bullet that ran out of tokens mid-clause — and skipping bullet
    lines let it through to the user.
    """
    body = strip_next_steps(text or "")
    body = re.split(r"\n\s*\*[^*\n]{20,}\*\s*$", body)[0]
    lines = []
    for raw in body.splitlines():
        ln = raw.strip()
        if not ln or ln.startswith(("#", ">", "|")):
            continue
        # Strip the bullet marker rather than skipping the line: the thing that
        # got cut off is almost always inside a list.
        ln = re.sub(r"^(?:[-*•+]|\d+[.)])\s+", "", ln).strip()
        if ln:
            lines.append(ln)
    if not lines:
        return False
    tail = lines[-1].rstrip("*_ —-·:")
    if not tail:
        return False
    if tail[-1] in _ENDS_A_SENTENCE:
        return False
    # A one or two word trailing fragment is a label, not a broken sentence.
    return len(tail.split()) > 2


def rewrite_in_language(state: Dict[str, Any], english: str,
                        llm: Optional[Callable]) -> str:
    """Rewrite a verified English answer natively, in the reader's language.

    This replaced a plain translate call, and the difference is the whole point:
    a translator reproduces the source's difficulty. A rewriter is told what
    difficulty to remove, is given the everyday word for each legal term, and
    keeps the citations and the 'what to do next' steps. It is grounded on the
    same English draft the verifier already approved, so nothing new can be
    invented — it can only say the same thing more simply.

    Returns "" on any failure so the caller keeps the English answer, which is
    still correct and still cited.
    """
    lang = state.get("lang", "en")
    if lang == "en" or not english.strip() or llm is None:
        return ""
    name = LANG_NAMES.get(lang, lang)
    rules = LANG_PLAIN_RULES.get(lang, "")
    question = str(state.get("query") or state.get("query_en") or "")
    system = (
        "You are LawSaathi, a patient family-law advisor speaking to a normal "
        "person in India — not a lawyer. You are given a finished, "
        "source-checked answer written in English. Rewrite it in %s so the same "
        "person can read it as easily as if it had been written that way from "
        "the start.\n\n"
        "What must NOT change:\n"
        "- Every fact, number, age, amount and timeframe stays exactly as it "
        "is. You are rephrasing, not re-deciding.\n"
        "- Keep the [1], [2], [3] citation markers, attached to the same "
        "claims they are attached to now. Keep every Act name and section "
        "number in English (for example 'Hindu Marriage Act, Section 5').\n"
        "- Keep the same headings, and the same 'what to do next' steps at the "
        "end.\n"
        "- The final heading must read exactly '### %s'. Do not translate "
        "that heading differently, and do not add a second one.\n"
        "- Keep the same length or shorter. Never pad.\n\n"
        "How to write it:\n"
        "- Say it the way a person would say it out loud to someone they know. "
        "A rule that is a sentence in English may become a shorter, warmer "
        "sentence here; a clause may move. Holding the English sentence order "
        "is what makes a rewrite read as a translation, and that is the one "
        "thing this must not do.\n"
        "- Read the whole draft first, then write. Do not work through it "
        "line by line.\n\n"
        "Example of the difference (Hindi):\n"
        "  English:  'You may apply to the Magistrate for a protection order, "
        "and the Magistrate may direct the respondent to stay away from the "
        "shared household.'\n"
        "  Word-for-word: 'आप मजिस्ट्रेट के पास एक प्रोटेक्शन ऑर्डर के लिए आवेदन कर "
        "सकती हैं, और मजिस्ट्रेट रिस्पॉन्डेंट को शेयर्ड हाउसहोल्ड से दूर रहने का "
        "निर्देश दे सकता है।'\n"
        "  Written for the reader: 'आप अदालत में जाकर कह सकती हैं कि वह आपके घर के "
        "पास न आए। अदालत ऐसा आदेश दे सकती है, और इसके लिए वकील की ज़रूरत नहीं।'\n"
        "  Notice: the same two facts, the same meaning, in the reader's own "
        "words — and Act names and section numbers still in English.\n\n"
        "%s\n\n"
        "%s\n\n"
        "Output ONLY the rewritten answer in %s. No preamble, no explanation "
        "of what you changed, no English version alongside it, no code blocks."
        % (name, _next_steps_heading(lang), rules,
           NATIVE_SIMPLICITY_RULES, name)
    )
    user = ("The reader asked (in %s): %s\n\n"
            "Rewrite this answer in %s:\n\n%s"
            % (name, question or "(follow-up in the same conversation)",
               name, english))
    try:
        text, provider = llm([
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ])
    except Exception as e:  # noqa: BLE001 — English answer still usable
        logger.warning("agent native rewrite failed (%r); keeping English", e)
        return ""
    state["provider"] = provider
    text = strip_reasoning_leak(text or "")
    # A rewrite that came back empty, English-only, or looping is worse than
    # the English it was meant to improve. Reject all three.
    if not text or len(text) < 40 or looks_looped(text):
        logger.warning("agent native rewrite unusable; keeping English")
        return ""
    if ends_mid_sentence(text):
        # Shipping a half sentence in Devanagari reads as a broken product.
        # The English draft is unfinished in exactly the same place, so there
        # is nothing to gain by keeping this one.
        logger.warning("agent native rewrite stopped mid-sentence; keeping English")
        return ""
    if state.get("lang") in ("hi", "kn"):
        # Not a raw string: r"[\u0900-\u097F]" is a literal backslash-u and
        # matches nothing, which silently disabled this whole check once.
        script = "[\u0900-\u097F]" if state["lang"] == "hi" else "[\u0C80-\u0CFF]"
        # An "Hindi" answer with no Devanagari in it is an untranslated echo.
        if not re.search(script, text):
            logger.warning("agent native rewrite stayed in English script")
            return ""
    return text


_LOOP_NGRAM = 4


def looks_looped(text: str, limit: int = 6) -> bool:
    """True when a phrase repeats, which small models fall into.

    qwen-2.5-7b occasionally emits the same sentence over and over when asked
    for Hindi or Kannada directly. A user must never see that, so the answer
    is rejected and the template used instead.
    """
    words = re.findall(r"\w+", (text or "").lower())
    if len(words) < (_LOOP_NGRAM + 1) * 2:
        return False
    seen: Dict[str, int] = {}
    for i in range(len(words) - _LOOP_NGRAM + 1):
        gram = " ".join(words[i:i + _LOOP_NGRAM])
        seen[gram] = seen.get(gram, 0) + 1
        if seen[gram] > limit:
            return True
    return False


def node_reason(state: Dict[str, Any],
                llm: Optional[Callable] = None) -> Dict[str, Any]:
    """Write the draft explanation the verifier will then judge.

    Split out from the response node on purpose. The old order was
    tools -> verifier -> response, so the verifier only ever saw a bag of
    passages and could check nothing except whether one had text in it. Now the
    draft exists before verification, which is the only way a check like "does
    this claim follow from that passage" is even possible.
    """
    draft = ""
    if llm is not None and evidence_sufficient(state.get("evidence", [])):
        draft = write_plain_answer(state, llm)
    state["draft"] = draft
    if draft:
        lang = state.get("lang", "en")
        n_passages = len(state.get("evidence", []))
        _add_trace(state, "reason", "reason_drafted", n=len(draft),
                   m=n_passages, plural=_plural(lang, n_passages))
    else:
        _add_trace(state, "reason", "reason_none")
    return state


AMENDMENT_CAVEAT = {
    "en": ("Important: this waiting period was changed by the Special "
           "Marriage (Amendment) Act, 2018 (Act 2 of 2019), in force from "
           "1 June 2019. The section text above is the pre-amendment "
           "version, so do not rely on the figure it quotes. Check the "
           "current period against the amended Act, or ask a family-law "
           "lawyer, before you act on it."),
    "hi": ("महत्वपूर्ण: यह प्रतीक्षा अवधि विशेष विवाह (संशोधन) अधिनियम, 2018 "
           "(अधिनियम 2 of 2019) द्वारा बदल दी गई है, जो 1 जून 2019 से लागू "
           "हुआ। ऊपर दिया गया धारा का पाठ पुराना है, इसलिए उसकी अवधि पर "
           "भरोसा न करें। संशोधित अधिनियम से वर्तमान अवधि जाँच लें, या "
           "परामर्श के लिए पारिवारिक कानून वकील से बात करें।"),
    "kn": ("ಮುಖ್ಯ: ಈ ಕಾಯದುಪಡಿ ಅವಧಿಯನ್ನು ವಿಶೇಷ ವಿವಾಹ (ತಿದ್ದುಪಡಿ) "
           "ಅಧಿನಿಯಮ, 2018 (ಕಾಯ 2 of 2019) ಮೂಲಕ ಬದಲಾಗಿದೆ, ಅದು 1 "
           "ಜೂನ್ 2019ರಿಂದ ಜಾರಿಯಾಗಿದೆ. ಮೇಲಿನ ವಿಭಾಗದ ಪಠ್ಯ ಹಳೆಯದ್ದು, "
           "ಆದ್ದರಿಂದ ಅದರ ಅವಧಿಗೆ ನಂಬಬೇಡಿ. ತಿದ್ದುಪಡಿ ಕಾಯದಿಂದ ಪ್ರಸ್ತುತ "
           "ಅವಧಿ ಪರಿಶೀಲಿಸಿ, ಅಥವಾ ಕುಟುಂಬ ಕಾನೂನು ವಕೀಲರನ್ನು "
           "ಸಂಪರ್ಕಿಸಿ."),
}

# Any duration figure. If an amendment notice is in evidence and the draft
# quotes one of these, the draft is relying on text we know is out of date.
_DURATION_RE = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|twelve|eighteen|"
    r"twenty|1|2|3|4|5|6|7|8|9|10|12|18|24)\s*[-–]?\s*"
    r"(month|year|week|day)s?\b", re.IGNORECASE)


def apply_amendment_guard(state: Dict[str, Any], answer: str) -> str:
    """Stop a stale duration being presented as current law.

    The amendment notice is in the passages, but the writing model ignores it
    and the verifier — which only checks that a claim matches a passage —
    approves the stale figure, because in the stale passage the stale figure
    *is* correct. Prompts did not fix this; only enforcing it does. The caveat
    names the amending Act, which is a fact we hold in the corpus, and does
    not assert any replacement figure.
    """
    has_notice = any(_AMENDMENT_LABEL in _section_of(h)
                     for h in state.get("evidence", []))
    if not has_notice:
        return answer
    if not _DURATION_RE.search(answer or ""):
        return answer
    lang = state.get("lang", "en")
    caveat = AMENDMENT_CAVEAT.get(lang, AMENDMENT_CAVEAT["en"])
    if caveat in answer:
        return answer
    return "%s\n\n> %s" % (answer, caveat)


def node_response(state: Dict[str, Any],
                  llm: Optional[Callable] = None,
                  translate_in: Optional[Callable] = None) -> Dict[str, Any]:
    memory = state.get("memory") or {}
    lang = state.get("lang", "en")
    if state.get("clarification"):
        # Clarification path: answer in the user's language, no guessing.
        text = state["clarification"]
        if lang != "en" and llm is not None:
            try:
                rendered, provider = llm([
                    {"role": "system",
                     "content": "Render this clarification question in %s. "
                                "Translate it once. Output only the translation. "
                                "No explanations, no preamble." % lang},
                    {"role": "user", "content": text},
                ])
                # Never show a looped translation; the local template is
                # already correct in all three languages.
                if rendered and not looks_looped(rendered):
                    text = rendered
                    state["provider"] = provider
                elif rendered:
                    logger.warning("agent clarify translation looped; keeping template")
            except Exception as e:  # noqa: BLE001 — template is already local
                logger.warning("agent clarify translate failed (%r)", e)
        state["answer"] = text
        state["citations"] = []
        state["citation_sources"] = []
        missing = state.get("missing_slots", [])
        if missing:
            _add_trace(state, "response", "response_clarify_missing",
                       missing=", ".join(missing))
        else:
            _add_trace(state, "response", "response_clarify_plain")
        return state
    # The draft was written and checked in node_reason; this node assembles
    # the user-facing answer. Re-writing here would throw away the judge's work.
    written = str(state.get("draft", "") or "")
    rewritten = False
    if written and lang != "en":
        # Written in English because the model is far steadier there. Now
        # rewrite it natively rather than translating it: a translator carries
        # the source's register across intact, which is how a plain English
        # answer arrived in Hindi still full of "मेंटेनेंस पेंडेंट लाइट". The
        # rewriter is grounded on the same verified draft, so it can simplify
        # without being able to invent. English is the fallback, unchanged.
        #
        # Prefer Groq here: the small model produced garbled Hindi ("माफिक आरोप
        # कार्यक्रम") where gpt-oss-120b was clean.
        native = rewrite_in_language(state, written, translate_in or llm)
        if native:
            written = native
            rewritten = True
        else:
            logger.warning("agent falling back to English answer for lang=%s", lang)
    answer_en, citations, citation_sources = compose_answer(state, written)
    final = strip_reasoning_leak(answer_en)
    guarded = apply_amendment_guard(state, final)
    if guarded != final:
        _add_trace(state, "response", "response_amendment")
        final = guarded
    # Append the disambiguating question the planner held back, so the user got
    # an answer *and* the chance to narrow it down.
    follow_up = str(state.get("follow_up_question") or "")
    if follow_up:
        final = "%s\n\n> %s" % (final, follow_up)
    state["answer"] = final
    state["citations"] = citations
    state["citation_sources"] = citation_sources
    # The reader's name for their own language, and the preposition the sentence
    # needs in it. Both are per-language because "in Hindi" is not "हिंदी में"
    # read backwards — the case ending goes on the noun.
    lang_name = LANGUAGE_NAMES.get(lang, {}).get(lang,
                                                 LANG_NAMES.get(lang, lang))
    if not written:
        how = trace_text(lang, "response_how_template")
    elif rewritten:
        how = trace_text(lang, "response_how_written") + trace_text(
            lang, "response_how_native", langname=lang_name)
    elif lang != "en":
        how = trace_text(lang, "response_how_written") + trace_text(
            lang, "response_how_english_fallback", langname=lang_name)
    else:
        how = trace_text(lang, "response_how_written")
    if lang != "en" and lang in LANG_NAMES:
        extra = " " + _phrase({"en": "in %s" % lang_name,
                               "hi": "%s में" % lang_name,
                               "kn": "%sನಲ್ಲಿ" % lang_name}, lang)
    else:
        extra = ""
    _add_trace(state, "response", "response_final", how=how,
               n=len(citations), plural=_plural(lang, len(citations)),
               extra=extra)
    return state


# Apply LangSmith tracing to nodes when configured (no-op otherwise).
node_intent = _maybe_trace("intent")(node_intent)
node_planner = _maybe_trace("planner")(node_planner)
node_tools = _maybe_trace("tools")(node_tools)
node_reason = _maybe_trace("reason")(node_reason)
node_verifier = _maybe_trace("verifier")(node_verifier)
node_response = _maybe_trace("response")(node_response)


def _publish(state: Dict[str, Any],
             on_step: Optional[Callable[[Dict[str, Any]], None]]) -> None:
    """Report the run so far. Never let a listener break the agent."""
    if on_step is None:
        return
    try:
        on_step(state)
    except Exception as e:  # noqa: BLE001 — a broken listener is not the user's problem
        logger.warning("agent step listener failed (%r)", e)


def _run_agent_inline(query: str, lang: str, memory, tone, retriever,
                      llm_fn, web_search, min_score, doc_id,
                      history,
                      on_step: Optional[Callable[[Dict[str, Any]], None]] = None
                      ) -> Dict[str, Any]:
    """The graph's node order, hand-rolled. Used when langgraph is absent.

    Must stay identical to build_graph()'s trace; test_agent.py asserts the
    two paths agree so they cannot quietly drift apart.
    """
    state = new_state(query, lang=lang, memory=memory, history=history)
    state["tone"] = tone
    state["doc_id"] = doc_id
    state = node_intent(state, llm=llm_fn)
    _publish(state, on_step)
    state = node_planner(state, llm=llm_fn)
    _publish(state, on_step)
    if state.get("clarification") or state.get("oos_redirect"):
        state = node_response(state, llm=llm_fn,
                              translate_in=budgeted_llm(translate_complete))
        _publish(state, on_step)
        state.pop("needs_retry", None)
        return state
    store = retriever if retriever is not None else default_retriever()
    state = node_tools(state, retriever=store, web_search=web_search,
                       llm=llm_fn)
    _publish(state, on_step)
    while True:
        state = node_reason(state, llm=llm_fn)
        _publish(state, on_step)
        state = node_verifier(state, min_score=min_score, llm=llm_fn)
        _publish(state, on_step)
        if not state.pop("needs_retry", False):
            break
        state = node_tools(state, retriever=store, web_search=web_search,
                           llm=llm_fn)
        _publish(state, on_step)
    state = node_response(state, llm=llm_fn,
                          translate_in=budgeted_llm(translate_complete))
    _publish(state, on_step)
    state.pop("needs_retry", None)
    return state


# Sentinel for "use whatever provider is configured". Passing llm=None
# explicitly means "no model at all", which is what the tests and the offline
# demo want. Before this sentinel existed both cases collapsed to the same
# thing, so a developer's .env leaked a live Groq key into the test suite and
# the agent's behaviour depended on what the model happened to return.
_USE_CONFIGURED_LLM = object()


def run_agent(query: str, lang: str = "en",
              memory: Optional[Dict[str, str]] = None,
              tone: str = "simple",
              retriever: Any = None,
              llm: Any = _USE_CONFIGURED_LLM,
              web_search: Optional[Callable] = None,
              min_score: float = 0.0,
              doc_id: str = "",
              history: Optional[List[Dict[str, str]]] = None,
              on_step: Optional[Callable[[Dict[str, Any]], None]] = None
              ) -> Dict[str, Any]:
    """Run intent -> planner -> [clarify | tools -> reason -> verifier] -> response.

    Returns the shared state dict (includes trace, answer, citations,
    provider, retries). The verifier can send the run back to tools at most
    MAX_RETRIES times, with its own replacement queries.

    LangGraph drives this when it is installed; the inline runner above is the
    fallback for a bare checkout. Either way the same nodes run in the same
    order, and ``state["trace"]`` is identical.

    ``llm``: omit it to use the configured provider, pass None for no model, or
    pass a callable taking (messages) and returning (text, provider).

    ``on_step``: called with the state after every node, so a streaming
    endpoint can show each step as it happens instead of after the whole run.
    """
    state = new_state(query, lang=lang, memory=memory, history=history)
    state["tone"] = tone
    state["doc_id"] = doc_id
    if llm is _USE_CONFIGURED_LLM:
        llm_fn = None
        if os.environ.get("GROQ_API_KEY", "") or os.environ.get(
                "OPENROUTER_API_KEY", ""):
            llm_fn = chat_complete
    else:
        llm_fn = llm
    # Bound the work: a rate-limited key must not turn one question into an
    # unbounded wait.
    llm_fn = budgeted_llm(llm_fn)
    runner = build_graph(retriever=retriever, llm=llm_fn,
                         web_search=web_search, min_score=min_score,
                         on_step=on_step)
    try:
        if getattr(runner, "is_graph", False):
            state.update(runner.invoke(state))
        else:
            state = _run_agent_inline(query, lang, memory, tone, retriever,
                                      llm_fn, web_search, min_score, doc_id,
                                      history, on_step=on_step)
    except Exception:
        # A crashed run is exactly what you want to see in LangSmith, so
        # mark it before letting the error reach the router.
        state["trace_error"] = True
        raise
    finally:
        trace_run(state)
    state.pop("needs_retry", None)
    return state


# T10 eval hook (ADR-0006): eval_t10.py runs run_agent against golden_qas.json.
# Set LANGCHAIN_TRACING_V2=true + LANGCHAIN_API_KEY to trace to LangSmith.
# Metrics: ragas Faithfulness / AnswerRelevancy / ContextRecall.
def run_agent_for_t10(query: str, lang: str = "en") -> str:
    state = run_agent(query, lang=lang)
    return state.get("answer", "")


def build_graph(retriever: Any = None, llm: Optional[Callable] = None,
                web_search: Optional[Callable] = None,
                on_step: Optional[Callable[[Dict[str, Any]], None]] = None,
                min_score: float = 0.0) -> Any:
    """Build the LangGraph StateGraph when langgraph is installed.

    This is the real runtime, not a diagram. When langgraph cannot be imported
    the caller gets a marker object instead, and run_agent() falls back to the
    inline runner with the identical node order.

    Edges:
        intent -> planner
        planner -> response (asking the user) | tools
        tools -> reason
        reason -> verifier
        verifier -> tools (insufficient evidence) | response
        response -> END
    """
    try:
        from langgraph.graph import END, StateGraph  # type: ignore
    except Exception:
        return _NO_GRAPH

    def _wrap(fn: Callable[[Dict[str, Any]], Dict[str, Any]]
              ) -> Callable[[Dict[str, Any]], Dict[str, Any]]:
        """Publish the run's progress after each node.

        LangGraph owns the state dict, so the node works on a copy and reports
        that copy. Reporting the incoming dict instead would miss the trace the
        node just added.
        """
        def node(s: Dict[str, Any]) -> Dict[str, Any]:
            out = fn(s)
            _publish(out, on_step)
            return out
        return node

    def _intent(s: Dict[str, Any]) -> Dict[str, Any]:
        return node_intent(dict(s), llm=llm)

    def _planner(s: Dict[str, Any]) -> Dict[str, Any]:
        return node_planner(dict(s), llm=llm)

    def _tools(s: Dict[str, Any]) -> Dict[str, Any]:
        store = retriever if retriever is not None else default_retriever()
        return node_tools(dict(s), retriever=store, web_search=web_search,
                          llm=llm)

    def _reason(s: Dict[str, Any]) -> Dict[str, Any]:
        return node_reason(dict(s), llm=llm)

    def _verifier(s: Dict[str, Any]) -> Dict[str, Any]:
        return node_verifier(dict(s), min_score=min_score, llm=llm)

    def _response(s: Dict[str, Any]) -> Dict[str, Any]:
        return node_response(dict(s), llm=llm,
                             translate_in=budgeted_llm(translate_complete))

    graph = StateGraph(dict)
    graph.add_node("intent", _wrap(_intent))
    graph.add_node("planner", _wrap(_planner))
    graph.add_node("tools", _wrap(_tools))
    graph.add_node("reason", _wrap(_reason))
    graph.add_node("verifier", _wrap(_verifier))
    graph.add_node("response", _wrap(_response))
    graph.set_entry_point("intent")
    graph.add_edge("intent", "planner")

    def _after_planner(s: Dict[str, Any]) -> str:
        # Out of scope and "I need to ask you something" both end the run at
        # the response node — neither benefits from a retrieval round trip.
        return "response" if (s.get("clarification") or s.get("oos_redirect")) \
            else "tools"

    graph.add_conditional_edges("planner", _after_planner,
                                {"response": "response", "tools": "tools"})

    def _after_verifier(s: Dict[str, Any]) -> str:
        # Read, never pop: LangGraph owns this state and a local pop does not
        # write the channel back. node_verifier always sets the flag, so this
        # is a read of a value that is guaranteed to be correct.
        if s.get("needs_retry"):
            return "tools"
        return "response"

    graph.add_conditional_edges("verifier", _after_verifier,
                                {"tools": "tools", "response": "response"})
    graph.add_edge("tools", "reason")
    graph.add_edge("reason", "verifier")
    graph.add_edge("response", END)
    compiled = graph.compile()
    compiled.is_graph = True  # type: ignore[attr-defined]
    return compiled


def budgeted_llm(llm: Optional[Callable],
                 max_calls: int = MAX_LLM_CALLS) -> Optional[Callable]:
    """Cap how many times one run may call the model.

    Persona testing found a single question taking 228s: the key was
    rate-limited, every call fell through the provider chain, and the verifier
    retried on top. This wrapper counts calls and then behaves as if there were
    no model at all, which lands on the template answer — a correct, cited,
    immediate reply instead of an indefinite wait.
    """
    if llm is None:
        return None
    remaining = {"n": max_calls}
    # A test double may be a plain `def f(messages)`, so only pass max_tokens
    # when the callable actually accepts it. Silently dropping it is right:
    # failing every call on a signature mismatch would look like a broken model.
    import inspect

    try:
        takes_max_tokens = "max_tokens" in inspect.signature(llm).parameters
    except (TypeError, ValueError):
        takes_max_tokens = False

    def wrapper(messages: List[Dict[str, str]], **kw: Any) -> Tuple[str, str]:
        if remaining["n"] <= 0:
            raise RuntimeError("model call budget exhausted for this run")
        remaining["n"] -= 1
        if takes_max_tokens:
            # Short answers do not need the full reasoning budget.
            kw.setdefault("max_tokens", MAX_TOKENS_SHORT)
        return llm(messages, **kw)

    return wrapper


class _NoGraph:
    """Returned when langgraph is missing; run_agent then runs inline."""

    is_graph = False
    graph_name = "lawsaathi-inline"  # type: ignore[attr-defined]


_NO_GRAPH = _NoGraph()
