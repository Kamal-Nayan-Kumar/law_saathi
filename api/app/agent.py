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
import logging
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
OPENROUTER_MODEL = os.environ.get(
    "OPENROUTER_MODEL", "qwen/qwen-2.5-7b-instruct")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1"
# Last-resort provider: OpenCode Zen's free tier costs nothing per token, so
# chat keeps working when Groq and OpenRouter are both rate-limited.
OPENCODE_URL = "https://opencode.ai/zen/v1/chat/completions"
OPENCODE_MODEL = os.environ.get("OPENCODE_MODEL", "space-bunny-free")
# Cloudflare in front of Zen answers 403 to urllib's default user agent.
OPENCODE_UA = os.environ.get("OPENCODE_USER_AGENT", "LawSaathi/1.0")
MAX_RETRIES = 2

NODES = ("intent", "planner", "tools", "verifier", "response")

TOPIC_KEYWORDS = {
    "divorce": ("divorce", "divorced", "talak", "talaq", "khula", "mubaraat",
                "तलाक", "ವಿಚ್ಛೇದನ"),
    "maintenance": ("maintenance", "maintainence", "bharan", "poshan",
                    "kharcha", "guzara", "भरण", "पोषण", "ಪೋಷಣೆ",
                    "alimony"),
    "custody": ("custody", "guardian", "अभिरक्षा", "ಹೆತ್ತವರ", "ವಶ"),
    "adoption": ("adoption", "adopt", "adopted", "गोद", "ದತ್ತು"),
    "succession": ("succession", "inheritance", "inherit", "heir",
                   "virasat", "viraasat",
                   "jaydad", "jaaydaad", "उत्तराधिकार", "ಉತ್ತರಾಧಿಕಾರ",
                   "वारिस"),
    "domestic_violence": ("domestic violence", "domestic-violence", "dowry",
                          "dahej", "marpeet", "maarpeet", "घरेलू हिंसा",
                          "ಕೌಟುಂಬಿಕ ಹಿಂಸೆ", "protection order"),
    "marriage": ("marriage", "marry", "married", "marital", "wedding",
                 "shadi", "shaadi", "vivah",
                 "nikah", "nikaha", "sagai", "engagement", "विवाह", "शादी",
                 "ಮದುವೆ", "conjugal"),
}

PARTY_WORDS = ("husband", "wife", "spouse", "pati", "patni", "biwi", "shohar",
               "bachcha", "bacha", "baccha", "beta", "beti", "maa", "baap",
               "aurat", "aadmi", "पति", "पत्नी", "ಗಂಡ", "ಹೆಂಡತಿ",
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
    """Detect en/hi/kn. Explicit hint wins; else script, then Hinglish."""
    if hint in ("en", "hi", "kn"):
        # Trust the caller (UI sends lang), but upgrade to hi/kn when the
        # script clearly says otherwise and hint is the default "en".
        if hint != "en":
            return hint
    blob = text or ""
    if re.search(r"[\u0C80-\u0CFF]", blob):
        return "kn"
    if re.search(r"[\u0900-\u097F]", blob):
        return "hi"
    if hint == "en" and hinglish_score(blob) >= 2:
        return "hi"  # Roman Hindi, e.g. "shadi ke liye umar"
    return hint if hint in ("en", "hi", "kn") else "en"


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
    if topics:
        # Prefer the most specific topic: maintenance/custody beat divorce.
        for pref in ("maintenance", "custody", "adoption", "succession",
                     "domestic_violence", "divorce", "marriage"):
            if pref in topics:
                slots["topic"] = pref
                break
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
        return ["topic"]
    if topic == "divorce" and not slots.get("divorce_type"):
        return ["divorce_type"]
    words = (query_en or "").split()
    if topic in ("divorce", "maintenance", "custody") \
            and not slots.get("parties") and len(words) < 6:
        return ["parties"]
    return []


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
                      timeout: float = 45.0) -> Tuple[str, str]:
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
         "temperature": 0.2, "max_tokens": 1500},
    )
    message = data["choices"][0]["message"] or {}
    text = (message.get("content") or "").strip()
    # Drop the model's scratchpad if it leaked into content.
    text = strip_reasoning_leak(text)
    if not text:
        raise RuntimeError("opencode returned an empty message")
    logger.info("agent llm provider=opencode model=%s", OPENCODE_MODEL)
    return text, "opencode:" + OPENCODE_MODEL


def chat_complete(messages: List[Dict[str, str]],
                  http_post: Optional[Callable] = None,
                  timeout: float = 45.0) -> Tuple[str, str]:
    """Chat with fallbacks: OpenRouter -> Groq -> OpenCode Zen.

    Returns (text, provider). ``http_post`` is a test seam:
    ``fn(url, headers, payload) -> dict`` in the OpenAI-chat-completions shape.
    Raises RuntimeError when no backend is available.
    """
    post = http_post or _post_json
    groq_key = os.environ.get("GROQ_API_KEY", "")
    or_key = os.environ.get("OPENROUTER_API_KEY", "")
    last_error: Optional[Exception] = None
    if or_key or http_post is not None:
        try:
            data = post(
                OPENROUTER_URL + "/chat/completions",
                {"Authorization": "Bearer " + or_key,
                 "Content-Type": "application/json",
                 "HTTP-Referer": "https://github.com/Kamal-Nayan-Kumar/law_saathi",
                 "X-Title": "LawSaathi"},
                {"model": OPENROUTER_MODEL, "messages": messages,
                 "temperature": 0.2, "max_tokens": 1500},
            )
            text = data["choices"][0]["message"]["content"].strip()
            logger.info("agent llm provider=openrouter model=%s", OPENROUTER_MODEL)
            return text, "openrouter:" + OPENROUTER_MODEL
        except Exception as e:  # noqa: BLE001 — fallback must catch all
            last_error = e
            logger.warning("agent openrouter failed (%r); trying groq", e)
    if groq_key or http_post is not None:
        try:
            data = post(
                GROQ_URL,
                {"Authorization": "Bearer " + groq_key,
                 "Content-Type": "application/json"},
                {"model": GROQ_MODEL, "messages": messages,
                 "temperature": 0.2, "max_tokens": 1500},
            )
            text = data["choices"][0]["message"]["content"].strip()
            logger.info("agent llm provider=groq model=%s", GROQ_MODEL)
            return text, "groq:" + GROQ_MODEL
        except Exception as e:  # noqa: BLE001 — fallback must catch all
            last_error = e
            logger.warning("agent groq failed (%r); trying opencode", e)
    # Free last resort: a rate-limited Groq/OpenRouter should not end the chat.
    try:
        return opencode_complete(messages, http_post=post, timeout=timeout)
    except Exception as e:  # noqa: BLE001 — caller sees the last error
        last_error = e
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
                       timeout: float = 45.0) -> Tuple[str, str]:
    """Translate using Groq only, falling back to the shared chat path.

    The default OpenRouter model is qwen-2.5-7b, which is weak in Hindi and
    Kannada — it produced garbled text and repeated phrases. Groq's
    gpt-oss-120b handled both cleanly, so translation routes there.
    """
    if os.environ.get("GROQ_API_KEY", "") or http_post is not None:
        post = http_post or _post_json
        try:
            data = post(
                GROQ_URL,
                {"Authorization": "Bearer " + os.environ.get("GROQ_API_KEY", ""),
                 "Content-Type": "application/json"},
                {"model": GROQ_MODEL, "messages": messages,
                 "temperature": 0.2, "max_tokens": 1500},
            )
            text = data["choices"][0]["message"]["content"].strip()
            logger.info("agent translate provider=groq model=%s", GROQ_MODEL)
            return text, "groq:" + GROQ_MODEL
        except Exception as e:  # noqa: BLE001 — caller falls back
            logger.warning("agent groq translate failed (%r)", e)
    return chat_complete(messages, http_post=http_post, timeout=timeout)


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


def _add_trace(state: Dict[str, Any], node: str, detail: str) -> None:
    state["trace"] = list(state.get("trace", [])) + [node]
    state["trace_detail"] = list(state.get("trace_detail", [])) + [
        {"node": node, "detail": detail}]


def carry_slots_from_history(slots: Dict[str, str],
                             history: List[Dict[str, str]]) -> Dict[str, str]:
    """Fill slots missing from a short follow-up with earlier user turns.

    One-word replies ("mutual", "wife") carry no topic on their own, so the
    planner would ask again. Merge slots from recent *user* messages; the
    current message always wins on conflict.
    """
    if not history:
        return slots
    if slots.get("topic") and (slots.get("topic") != "divorce"
                               or slots.get("divorce_type")):
        return slots  # current message already stands alone
    merged = dict(slots)
    for msg in history:
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        for key, val in extract_slots(msg.get("content", "")).items():
            if key not in merged:
                merged[key] = val
    return merged

def node_intent(state: Dict[str, Any],
                llm: Optional[Callable] = None) -> Dict[str, Any]:
    raw_query = state["query"]
    query = raw_query
    lang = state["lang"]
    query_en = query
    provider = state.get("provider", "")
    history = state.get("history", [])
    if history and llm is not None:
        # Follow-up questions ("mutual", "what about my daughter?") need
        # prior turns to stand alone for retrieval, so rewrite first.
        try:
            query, provider = llm([
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
            _add_trace(state, "contextualize",
                       "Follow-up %r became %r using chat history."
                       % (raw_query[:60], query.strip()[:100]))
        except Exception as e:  # noqa: BLE001 — fall back to raw query
            logger.warning("agent contextualize failed (%r); using raw query", e)
    if lang != "en":
        if llm is not None:
            try:
                query_en, provider = llm([
                    {"role": "system",
                     "content": "Translate this family-law question to English. "
                                "Output only the translation. No explanations, no preamble."},
                    {"role": "user", "content": query},
                ])
                state["provider"] = provider
            except Exception as e:  # noqa: BLE001 — pivot is best-effort
                logger.warning("agent translate failed (%r); using raw query", e)
        # Without an LLM the raw query still retrieves (e5 is multilingual).
    state["query_en"] = query_en.strip() or query
    slots = extract_slots(state["query_en"])
    carried = carry_slots_from_history(slots, history)
    if carried != slots:
        added = ", ".join("%s=%r" % (k, v) for k, v in carried.items()
                          if slots.get(k) != v)
        logger.info("agent carried slots from history: %s", added)
    slots = carried
    state["slots"] = slots
    state["intent"] = classify_intent(state["query_en"], slots)
    state["oos_redirect"] = is_oos(state["query_en"])
    topic = slots.get("topic")
    bits = []
    if topic:
        bits.append("topic %r" % topic)
    if slots.get("divorce_type"):
        bits.append("type %r" % slots["divorce_type"])
    if slots.get("parties"):
        bits.append("asking for %r" % slots["parties"])
    if slots.get("section"):
        bits.append("section %s" % slots["section"])
    found = "; ".join(bits) if bits else "no clear topic yet"
    _add_trace(state, "intent",
               "Detected %s, language %s." % (
                   found, LANG_NAMES.get(state["lang"], state["lang"])))
    return state


def node_planner(state: Dict[str, Any]) -> Dict[str, Any]:
    missing = missing_for(state.get("slots", {}),
                          state.get("query_en", ""),
                          is_followup=bool(state.get("history")))
    state["missing_slots"] = missing
    if missing:
        state["clarification"] = clarification_question(
            missing, state.get("lang", "en"))
        _add_trace(state, "planner",
                   "Still need: %s — asking you instead of guessing."
                   % ", ".join(missing))
    else:
        state["clarification"] = ""
        _add_trace(state, "planner", "Nothing missing — retrieving the law.")
    return state


# The act that actually governs each topic. Retrieval on the bare question
# alone lets one incidental word decide the results: "Who gets the custody of
# the child in a divorce?" returned Indian Divorce Act sections because
# "divorce" outweighed "custody", and never reached Guardians and Wards.
TOPIC_ACT = {
    "custody": "Guardians and Wards Act 1890",
    "divorce": "Hindu Marriage Act 1955 Indian Divorce Act 1869",
    "marriage": "Hindu Marriage Act 1955 Special Marriage Act 1954",
    "maintenance": "Hindu Adoption and Maintenance Act 1956",
    "adoption": "Hindu Adoption and Maintenance Act 1956",
    "succession": "Hindu Succession Act 1956",
    "domestic_violence": "Domestic Violence Act 2005",
}

_ALL_ACTS = ("Hindu Marriage Act 1955 Special Marriage Act 1954 Hindu Adoption "
             "and Maintenance Act 1956 Hindu Succession Act 1956 Guardians and "
             "Wards Act 1890 Domestic Violence Act 2005 Indian Divorce Act 1869")


def broaden_query(query_en: str, retries: int, topic: str = "") -> str:
    """Shape the retrieval query.

    Always anchor to the act that governs the detected topic, so a stray
    word in the question cannot drag the results into the wrong act. On a
    retry, add the full act list; on the second retry, drop section numbers
    that may be over-narrowing.
    """
    anchor = TOPIC_ACT.get(topic or "", "")
    if retries <= 0:
        return ("%s %s" % (query_en, anchor)).strip() if anchor else query_en
    if retries == 1:
        return "%s %s %s" % (query_en, anchor, _ALL_ACTS)
    # Retry 2: drop section numbers that may over-narrow the query.
    stripped = re.sub(r"section\s+\d+[A-Z\-]*", " ", query_en,
                      flags=re.IGNORECASE)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return "%s %s %s" % (stripped or query_en, anchor, _ALL_ACTS)


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


def node_tools(state: Dict[str, Any], retriever: Any = None,
               web_search: Optional[Callable] = None) -> Dict[str, Any]:
    store = retriever or default_retriever()
    query_en = broaden_query(state.get("query_en", state.get("query", "")),
                             state.get("retries", 0),
                             (state.get("slots") or {}).get("topic", ""))
    evidence: List[Dict[str, Any]] = []
    doc_id = state.get("doc_id") or state.get("doc_id", "")
    try:
        if doc_id and hasattr(store, "search_text"):
            evidence = list(store.search_text(query_en, top_k=5,
                              filter_payload={"doc_id": doc_id}) or [])
        elif doc_id and hasattr(store, "search"):
            # InMemoryVectorStore lacks text search; unfiltered fallback
            evidence = list(store.search(query_en, top_k=5) or [])
        else:
            evidence = list(store.search_text(query_en, top_k=5) or [])
    except Exception as e:  # noqa: BLE001 — retrieval failure is retryable
        logger.warning("agent retrieval failed (%r)", e)
        evidence = []
    ws = web_search or stub_web_search
    web_hits: List[Dict[str, Any]] = []
    web_error = ""
    try:
        web_hits = list(ws(query_en) or [])
        evidence = evidence + web_hits
    except Exception as e:  # noqa: BLE001 — web is best-effort
        logger.warning("agent web_search failed (%r)", e)
        web_error = str(e) or e.__class__.__name__
    state["evidence"] = evidence
    # Show the web search explicitly: a silent search failure is
    # indistinguishable from "the web had nothing", and the user asked to
    # see which query went out when the bare acts were not enough.
    shown = query_en[:80]
    if web_error:
        web_note = 'web_search:"%s" unavailable (%s).' % (shown, web_error[:60])
    elif web_hits:
        web_note = 'web_search:"%s" → %d web result%s.' % (
            shown, len(web_hits), "" if len(web_hits) == 1 else "s")
    else:
        web_note = 'web_search:"%s" → no results.' % shown
    rag_note = ""
    if len(evidence) - len(web_hits) > 0:
        rag_note = "Retrieved %d act section%s. " % (
            len(evidence) - len(web_hits),
            "" if len(evidence) - len(web_hits) == 1 else "s")
    elif not web_hits:
        rag_note = "No matching sections in the bare acts. "
    else:
        rag_note = "Nothing in the bare acts; used the web instead. "
    _add_trace(state, "tools", rag_note + web_note)
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


OOS_KEYWORDS = ("land", "property", "real estate", "criminal", "tax", "income tax",
                "property law", "criminal law", "theft", "murder", "rape")


def is_oos(query_en: str) -> bool:
    low = (query_en or "").lower()
    # Only redirect when clearly not family law and has OOS term
    has_oos = any(k in low for k in OOS_KEYWORDS)
    has_family = any(k in low for k in (
        "marriage", "married", "divorce", "divorced", "custody",
        "maintenance", "adoption", "adopted", "guardians",
        "domestic violence", "succession", "inheritance", "inherit",
        "heir"))
    return has_oos and not has_family


def node_verifier(state: Dict[str, Any],
                  min_score: float = 0.0) -> Dict[str, Any]:
    sufficient = evidence_sufficient(state.get("evidence", []),
                                     min_score=min_score)
    retries = int(state.get("retries", 0))
    # Emit confidence: max score of sufficient hits, else 0.0
    confidence = 0.0
    if sufficient:
        scores = []
        for hit in state.get("evidence", []):
            score = hit.get("score", 1.0) if isinstance(hit, dict) else 1.0
            try:
                scores.append(float(score))
            except (TypeError, ValueError):
                scores.append(1.0)
        confidence = max(scores) if scores else 0.0
    state["confidence"] = confidence
    if sufficient:
        state["verified"] = True
        _add_trace(state, "verifier",
                   "Citations cover the answer — confidence %.2f."
                   % confidence)
    elif retries < MAX_RETRIES:
        state["verified"] = False
        state["retries"] = retries + 1
        state["needs_retry"] = True
        _add_trace(state, "verifier",
                   "Evidence too thin — broadening the search (retry %d/%d)."
                   % (retries + 1, MAX_RETRIES))
    else:
        state["verified"] = False
        state["needs_retry"] = False
        _add_trace(state, "verifier",
                   "Still thin after %d retries — answering with a caution."
                   % MAX_RETRIES)
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

NEXT_STEPS = {
    "en": "Next steps: gather relevant documents (marriage certificate, court orders) and speak with a family-law lawyer for personalized guidance.",
    "hi": "अगले कदम: प्रासंगिक दस्तावेज़ (विवाह प्रमाणपत्र, न्यायालय आदेश) इकट्ठा करें और व्यक्तिगत मार्गदर्शन के लिए पारिवारिक कानून के वकील से बात करें।",
    "kn": "ಮುಂದಿನ ಹೆಜ್ಜೆಗಳು: ಸಂಬಂಧಿತ ದಾಖಲೆಗಳನ್ನು (ಮದುವೆ ಪ್ರಮಾಣಪತ್ರ, ನ್ಯಾಯಾಲಯದ ಆದೇಶಗಳು) ಸಂಗ್ರಹಿಸಿ ಮತ್ತು ವೈಯಕ್ತಿಕ ಮಾರ್ಗದರ್ಶನಕ್ಕಾಗಿ ಕುಟುಂಬ ಕಾನೂನು ವಕೀಲರನ್ನು ಸಂಪರ್ಕಿಸಿ.",
}


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


TOPIC_SUMMARY = {
    "divorce": "For divorce, Indian family law provides mutual-consent (joint petition after living apart) and contested (fault grounds) routes under the Hindu Marriage Act, Special Marriage Act, or Indian Divorce Act depending on religion and marriage type.",
    "maintenance": "For maintenance, the Hindu Adoption & Maintenance Act and related provisions let eligible spouses/children claim support based on need and the other party's means.",
    "custody": "For custody, the Guardians & Wards Act and related provisions decide on the child's welfare as paramount — custody, visitation, and guardianship.",
    "adoption": "For adoption, the Hindu Adoption & Maintenance Act lays down who may adopt, who may be adopted, and the required ceremonies and consents.",
    "succession": "For succession, the Hindu Succession Act governs how property devolves on heirs, including Class I/II heirs and testamentary succession.",
    "domestic_violence": "For domestic violence, the DV Act 2005 provides protection orders, residence orders, monetary relief, and custody orders for aggrieved persons.",
    "marriage": "For marriage, the Hindu Marriage Act and Special Marriage Act lay down conditions, ceremonies/registration, and validity requirements.",
    "general": "The relevant family-law acts set the conditions, procedure, and reliefs for this question.",
}


# Ingestion stamps every chunk with a provenance header and leaves markdown
# noise in the text. Both were reaching the user verbatim, which is what made
# an answer read like a database dump instead of advice.
_META_HEADER_RE = re.compile(r"^Act:.*?\n", re.DOTALL)
_SECTION_LINE_RE = re.compile(
    r"^Section\s+\d+[A-Za-z\-]*\s*:\s*", re.IGNORECASE)


def plain_passage(text: str, limit: int = 160) -> str:
    """Clean one retrieved chunk for human reading.

    Strips the scraper header and the markdown residue from the act text,
    drops the title the chunk repeats twice, and collapses to one line. The
    cut lands on a clause boundary so an answer never ends mid-sentence.
    """
    body = (text or "").strip()
    body = _META_HEADER_RE.sub("", body, count=1)
    body = re.sub(r"\*\*([^*]+)\*\*", r"\1", body)       # **13B. ...**
    body = re.sub(r"\(\s*_([^_]+)_\s*\)", r"(\1)", body)  # ( _1_ )
    body = re.sub(r"(?<![\w])_+([^_]+?)_+(?![\w])", r"\1", body)  # _i_

    # The chunk states its title twice: a "Section 13B: Divorce by mutual
    # consent" line, then "13B. Divorce by mutual consent.—" in the body.
    # Keep the first and cut the echo.
    if _SECTION_LINE_RE.match(body):
        head, _, rest = body.partition("\n")
        title = head.split(":", 1)[-1].strip() if ":" in head else ""
        probe = " ".join(title.lower().split()[-3:])
        if probe and probe in rest.lower()[:80]:
            at = rest.lower().index(probe) + len(probe)
            rest = rest[at:].lstrip(" .—-")
        body = rest
    else:
        body = _SECTION_LINE_RE.sub("", body, count=1)

    one_line = re.sub(r"\s+", " ", body).strip(" -–—")
    if not one_line:
        return ""
    if len(one_line) <= limit:
        return one_line
    cut = one_line[:limit]
    # Prefer the last clause boundary; fall back to the last space.
    for sep in (". ", "; ", ", ", " and ", " "):
        idx = cut.rfind(sep)
        if idx > limit * 0.5:
            return cut[:idx].rstrip(" ,;:-") + "…"
    return cut.rstrip() + "…"


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
        base = ("I could not verify this with the family-law acts I have. ")
        if state.get("slots", {}).get("topic") == "divorce":
            base += ("Divorce in India generally falls under the Hindu Marriage "
                     "Act (Section 13/13B), the Special Marriage Act, or the "
                     "Indian Divorce Act depending on religion and marriage type. ")
        base += "Please share the exact section/act name so I can verify, or consult a lawyer for personalized advice."
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
    summary = TOPIC_SUMMARY.get(topic, TOPIC_SUMMARY["general"])
    disclaimer = DISCLAIMER.get(lang, DISCLAIMER["en"])
    next_steps = NEXT_STEPS.get(lang, NEXT_STEPS["en"])
    confidence = float(state.get("confidence", 1.0))
    low_warn = ""
    if confidence < 0.7:
        low_warn = "\n\n> " + LOW_CONFIDENCE_DISCLAIMER.get(
            lang, LOW_CONFIDENCE_DISCLAIMER["en"])

    if written.strip():
        # The model wrote a plain-language explanation grounded in the
        # passages above. Show it as the answer; the passages themselves
        # belong in the Sources list, not in the body.
        answer = "%s\n\n### What to do next\n\n%s%s\n\n*%s*" % (
            written.strip(), next_steps, low_warn, disclaimer)
    else:
        # No model available: fall back to the template plus cleaned passages.
        lines = ["- **[%d] %s** — %s" % (
            i, format_citation(h.get("payload", {}) if isinstance(h, dict) else {}),
            _short_meaning((h.get("payload", {}) or {}).get("text", "")
                           if isinstance(h, dict) else ""))
            for i, h in enumerate(evidence[:5], start=1)]
        answer = (
            "## Quick answer\n\n%s\n\n"
            "### What the law says\n\n%s\n\n"
            "### What to do next\n\n%s%s\n\n"
            "*%s*"
            % (summary, "\n".join(lines), next_steps, low_warn, disclaimer))
    return answer, citations, citation_sources


TONE_GUIDE = {
    "simple": "Keep it short — 3 to 5 short sentences. Skip legal jargon. "
              "If you must use a term like 'petition', explain it in the same "
              "sentence. Prefer a couple of clear sentences over a long list.",
    "detailed": "Give a fuller but still plain explanation — 5 to 8 sentences. "
                "Name the sections you rely on, but explain what each one means "
                "in ordinary words. Bullets under a heading are welcome here.",
}


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
    topic = (state.get("slots") or {}).get("topic", "general")
    system = (
        "You are LawSaathi, a patient family-law advisor speaking to a normal "
        "person in India — not a lawyer. Explain the law below the way a good "
        "lawyer would explain it across a table.\n\n"
        "Rules:\n"
        "- Write in English, in plain everyday words.\n"
        "- Answer only from the numbered passages. Never add a section, a "
        "provision or a fact that is not in them.\n"
        "- If the passages do not cover the question, say what they do cover "
        "and what is missing. Do not guess.\n"
        "- Refer to a source as [1], [2] inline, right after the claim it "
        "supports. Use the numbers exactly as given.\n"
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
        "- 2 to 4 short paragraphs. Output ONLY the explanation.\n"
        "%s" % TONE_GUIDE.get(tone, TONE_GUIDE["simple"])
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
    _add_trace(state, "response",
               "Rewrote the raw sections as a plain-language explanation "
               "(%d chars) for topic %s." % (len(text), topic))
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


def node_response(state: Dict[str, Any],
                  llm: Optional[Callable] = None,
                  translate_in: Optional[Callable] = None) -> Dict[str, Any]:
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
        _add_trace(state, "response",
                   "Asked you for: %s." % ", ".join(missing) if missing
                   else "Asked you a follow-up question.")
        return state
    written = ""
    if llm is not None and evidence_sufficient(state.get("evidence", [])):
        written = write_plain_answer(state, llm)
    answer_en, citations, citation_sources = compose_answer(state, written)
    final = strip_reasoning_leak(answer_en)
    translated = False
    if written and lang != "en":
        # Written in English because the model is far steadier there; now
        # translate the finished explanation into the user's language.
        # Prefer Groq here: qwen-2.5-7b produced garbled Hindi ("माफिक आरोप
        # कार्यक्रम") where gpt-oss-120b was clean.
        translator = translate_in or llm
        try:
            final, provider = translator([
                {"role": "system",
                 "content": ("You are a translator. Translate the text into %s. "
                             "Keep the [1], [2] citation markers exactly as they "
                             "are. Keep act names and section names in English. "
                             "Translate each sentence once — never repeat a "
                             "sentence or a phrase. Output ONLY the translation. "
                             "Do NOT explain, do NOT think aloud, no preamble, "
                             "no code blocks, no commentary." % lang)},
                {"role": "user", "content": written},
            ])
            final = strip_reasoning_leak(final)
            if looks_looped(final):
                logger.warning("agent translation looped; keeping English")
                final = written
            else:
                translated = True
                state["provider"] = provider
        except Exception as e:  # noqa: BLE001 — English answer still usable
            logger.warning("agent answer translate failed (%r)", e)
            final = written
    state["answer"] = final
    state["citations"] = citations
    state["citation_sources"] = citation_sources
    how = ("wrote a plain-language answer" if written
           else "used the template answer (no model)")
    if translated:
        how += " and translated it"
    _add_trace(state, "response",
               "%s with %d citation%s%s."
               % (how[0].upper() + how[1:], len(citations),
                  "" if len(citations) == 1 else "s",
                  " in " + LANG_NAMES[lang]
                  if lang != "en" and lang in LANG_NAMES else ""))
    return state


# Apply LangSmith tracing to nodes when configured (no-op otherwise).
node_intent = _maybe_trace("intent")(node_intent)
node_planner = _maybe_trace("planner")(node_planner)
node_tools = _maybe_trace("tools")(node_tools)
node_verifier = _maybe_trace("verifier")(node_verifier)
node_response = _maybe_trace("response")(node_response)


def run_agent(query: str, lang: str = "en",
              memory: Optional[Dict[str, str]] = None,
              tone: str = "simple",
              retriever: Any = None,
              llm: Optional[Callable] = None,
              web_search: Optional[Callable] = None,
              min_score: float = 0.0,
              doc_id: str = "",
              history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """Run intent -> planner -> [clarify | tools <-> verifier] -> response.

    Returns the shared state dict (includes trace, answer, citations,
    provider, retries). Verifier loops back to tools at most MAX_RETRIES.
    """
    state = new_state(query, lang=lang, memory=memory, history=history)
    state["tone"] = tone
    state["doc_id"] = doc_id
    # Default LLM: live Groq/OpenRouter when keys exist, else None (templates).
    llm_fn = llm
    if llm_fn is None:
        if os.environ.get("GROQ_API_KEY", "") or os.environ.get(
                "OPENROUTER_API_KEY", ""):
            llm_fn = chat_complete
    try:
        state = node_intent(state, llm=llm_fn)
        state = node_planner(state)
        if state.get("clarification"):
            state = node_response(state, llm=llm_fn,
                                  translate_in=translate_complete)
            state.pop("needs_retry", None)
            return state
        store = retriever if retriever is not None else default_retriever()
        state = node_tools(state, retriever=store, web_search=web_search)
        state = node_verifier(state, min_score=min_score)
        while state.pop("needs_retry", False):
            state = node_tools(state, retriever=store, web_search=web_search)
            state = node_verifier(state, min_score=min_score)
        state = node_response(state, llm=llm_fn,
                              translate_in=translate_complete)
        state.pop("needs_retry", None)
        return state
    except Exception:
        # A crashed run is exactly what you want to see in LangSmith, so
        # mark it before letting the error reach the router.
        state["trace_error"] = True
        raise
    finally:
        trace_run(state)


# T10 eval hook (ADR-0006): eval_t10.py runs run_agent against golden_qas.json.
# Set LANGCHAIN_TRACING_V2=true + LANGCHAIN_API_KEY to trace to LangSmith.
# Metrics: ragas Faithfulness / AnswerRelevancy / ContextRecall.
def run_agent_for_t10(query: str, lang: str = "en") -> str:
    state = run_agent(query, lang=lang)
    return state.get("answer", "")


def build_graph(retriever: Any = None, llm: Optional[Callable] = None,
                web_search: Optional[Callable] = None,
                min_score: float = 0.0) -> Any:
    """Build the LangGraph StateGraph when langgraph is installed.

    Falls back to a small runner with the same node order so tests and
    bare checkouts work without the dependency. Both paths record the
    five node names in ``state["trace"]``.
    """
    try:
        from langgraph.graph import END, StateGraph  # type: ignore
    except Exception:
        def runner(query: str, lang: str = "en",
                   memory: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
            return run_agent(query, lang=lang, memory=memory,
                             retriever=retriever, llm=llm,
                             web_search=web_search, min_score=min_score)
        runner.graph_name = "lawsaathi-fallback"  # type: ignore[attr-defined]
        return runner

    def _intent(s: Dict[str, Any]) -> Dict[str, Any]:
        return node_intent(dict(s), llm=llm)

    def _planner(s: Dict[str, Any]) -> Dict[str, Any]:
        return node_planner(dict(s))

    def _tools(s: Dict[str, Any]) -> Dict[str, Any]:
        store = retriever if retriever is not None else default_retriever()
        return node_tools(dict(s), retriever=store, web_search=web_search)

    def _verifier(s: Dict[str, Any]) -> Dict[str, Any]:
        return node_verifier(dict(s), min_score=min_score)

    def _response(s: Dict[str, Any]) -> Dict[str, Any]:
        return node_response(dict(s), llm=llm)

    graph = StateGraph(dict)
    graph.add_node("intent", _intent)
    graph.add_node("planner", _planner)
    graph.add_node("tools", _tools)
    graph.add_node("verifier", _verifier)
    graph.add_node("response", _response)
    graph.set_entry_point("intent")
    graph.add_edge("intent", "planner")

    def _after_planner(s: Dict[str, Any]) -> str:
        return "response" if s.get("clarification") else "tools"

    graph.add_conditional_edges("planner", _after_planner,
                                {"response": "response", "tools": "tools"})

    def _after_verifier(s: Dict[str, Any]) -> str:
        if s.pop("needs_retry", False):
            return "tools"
        return "response"

    graph.add_conditional_edges("verifier", _after_verifier,
                                {"tools": "tools", "response": "response"})
    graph.add_edge("tools", "verifier")
    graph.add_edge("response", END)
    return graph.compile()
