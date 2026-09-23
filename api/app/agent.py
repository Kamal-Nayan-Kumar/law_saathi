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
    "OPENROUTER_MODEL", "openrouter/free")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OPENROUTER_URL = "https://openrouter.ai/api/v1"
MAX_RETRIES = 2

NODES = ("intent", "planner", "tools", "verifier", "response")

TOPIC_KEYWORDS = {
    "divorce": ("divorce", "talak", "talaq", "तलाक", "ವಿಚ್ಛೇದನ"),
    "maintenance": ("maintenance", "maintainence", "भरण", "पोषण", "ಪೋಷಣೆ",
                    "alimony"),
    "custody": ("custody", "guardian", "अभिरक्षा", "ಹೆತ್ತವರ", "ವಶ"),
    "adoption": ("adoption", "adopt", "गोद", "ದತ್ತು"),
    "succession": ("succession", "inheritance", "उत्तराधिकार", "ಉತ್ತರಾಧಿಕಾರ",
                   "वारिस"),
    "domestic_violence": ("domestic violence", "domestic-violence", "घरेलू हिंसा",
                          "ಕೌಟುಂಬಿಕ ಹಿಂಸೆ", "protection order"),
    "marriage": ("marriage", "marry", "विवाह", "शादी", "ಮದುವೆ", "conjugal"),
}

PARTY_WORDS = ("husband", "wife", "spouse", "पति", "पत्नी", "ಗಂಡ", "ಹೆಂಡತಿ",
               "mother", "father", "minor", "child", "माता", "पिता")

_DIVORCE_TYPE_RE = re.compile(
    r"mutual(\s+consent)?|contested|one[-\s]?sided|ex[-\s]?parte|आपसी\s*सहमति",
    re.IGNORECASE)
_SECTION_RE = re.compile(r"section\s+(\d+[A-Z\-]*)|धारा\s+(\d+)", re.IGNORECASE)


def detect_lang(text: str, hint: str = "en") -> str:
    """Detect en/hi/kn. Explicit hint wins; else script heuristic."""
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
    return hint if hint in ("en", "hi", "kn") else "en"


def new_state(query: str, lang: str = "en",
              memory: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    return {
        "query": query,
        "lang": detect_lang(query, lang),
        "query_en": "",
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
        "memory": dict(memory or {}),
        "doc_id": "",
    }


def extract_slots(query_en: str) -> Dict[str, str]:
    low = (query_en or "").lower()
    slots: Dict[str, str] = {}
    topics = [t for t, kws in TOPIC_KEYWORDS.items()
              if any(k in low for k in kws)]
    if topics:
        # Prefer the most specific topic: maintenance/custody beat divorce.
        for pref in ("maintenance", "custody", "adoption", "succession",
                     "domestic_violence", "divorce", "marriage"):
            if pref in topics:
                slots["topic"] = pref
                break
    m = _DIVORCE_TYPE_RE.search(query_en or "")
    if m:
        word = m.group(0).lower()
        slots["divorce_type"] = ("mutual" if "mutual" in word or "आपसी" in word
                                 else "contested")
    for p in PARTY_WORDS:
        if p in low:
            slots["parties"] = p
            break
    sec = _SECTION_RE.search(query_en or "")
    if sec:
        slots["section"] = sec.group(1) or sec.group(2) or ""
    return slots


def classify_intent(query_en: str, slots: Dict[str, str]) -> str:
    if slots.get("topic"):
        return slots["topic"]
    low = (query_en or "").lower()
    if any(w in low for w in ("what is", "explain", "section", "act", "law",
                              "rights", "procedure", "grounds")):
        return "general"
    return "general"


def missing_for(slots: Dict[str, str], query_en: str) -> List[str]:
    """Key slots the planner needs before guessing (T3 accept rule)."""
    if slots.get("section"):
        return []  # exact-section lookup is answerable as-is
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
    "en": ("To guide you correctly, could you clarify: {asked}? "
           "(For example: mutual-consent or contested divorce; is this about "
           "maintenance or custody; and who is asking — husband, wife, or "
           "guardian?)"),
    "hi": ("आपका सही मार्गदर्शन करने के लिए कृपया स्पष्ट करें: {asked}? "
           "(जैसे: आपसी सहमति या विवादित तलाक; क्या यह भरण-पोषण या अभिरक्षा "
           "के बारे में है; और कौन पूछ रहा है — पति, पत्नी या अभिभावक?)"),
    "kn": ("ಸರಿಯಾಗಿ ಮಾರ್ಗದರ್ಶನ ನೀಡಲು ದಯವಿಟ್ಟು ಸ್ಪಷ್ಟಪಡಿಸಿ: {asked}? "
           "(ಉದಾ: ಪರಸ್ಪರ ಒಪ್ಪಿಗೆಯ ಅಥವಾ ವಿವಾದಿತ ವಿಚ್ಛೇದನ; ಇದು ಜೀವನಾಂಶ ಅಥವಾ "
           "ಪಾಲನೆಗೆ ಸಂಬಂಧಿಸಿದ್ದೇ; ಮತ್ತು ಕೇಳುತ್ತಿರುವವರು ಯಾರು — ಗಂಡ, "
           "ಹೆಂಡತಿ ಅಥವಾ ಪಾಲಕರು?)"),
}

_SLOT_LABELS = {
    "en": {"topic": "the exact issue (divorce type, maintenance vs custody)",
           "divorce_type": "whether this is mutual-consent or contested divorce",
           "parties": "who is asking (husband, wife, guardian)"},
    "hi": {"topic": "सटीक मुद्दा (तलाक का प्रकार, भरण-पोषण या अभिरक्षा)",
           "divorce_type": "क्या यह आपसी सहमति या विवादित तलाक है",
           "parties": "कौन पूछ रहा है (पति, पत्नी, अभिभावक)"},
    "kn": {"topic": "ನಿಖರ ವಿಷಯ (ವಿಚ್ಛೇದನದ ವಿಧ, ಜೀವನಾಂಶ ಅಥವಾ ಪಾಲನೆ)",
           "divorce_type": "ಇದು ಪರಸ್ಪರ ಒಪ್ಪಿಗೆಯ ಅಥವಾ ವಿವಾದಿತ ವಿಚ್ಛೇದನವೇ",
           "parties": "ಕೇಳುತ್ತಿರುವವರು ಯಾರು (ಗಂಡ, ಹೆಂಡತಿ, ಪಾಲಕರು)"},
}


def clarification_question(missing: List[str], lang: str) -> str:
    labels = _SLOT_LABELS.get(lang, _SLOT_LABELS["en"])
    asked = ", ".join(labels.get(m, m) for m in missing) or labels["topic"]
    template = CLARIFY_TEMPLATES.get(lang, CLARIFY_TEMPLATES["en"])
    return template.format(asked=asked)


# ---------------------------------------------------------------------------
# LLM layer: Groq primary, OpenRouter fallback, stub when keys are absent.
# ---------------------------------------------------------------------------

def _post_json(url: str, headers: Dict[str, str], payload: Dict[str, Any],
               timeout: float = 45.0) -> Dict[str, Any]:
    import httpx  # lazy: keeps bare checkouts importable

    resp = httpx.post(url, headers=headers, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def chat_complete(messages: List[Dict[str, str]],
                  http_post: Optional[Callable] = None,
                  timeout: float = 45.0) -> Tuple[str, str]:
    """Chat via OpenRouter (free endpoint preferred), falling back to Groq. Returns (text, provider).

    ``http_post`` is a test seam: ``fn(url, headers, payload) -> dict`` with
    the OpenAI-chat-completions shape. Raises RuntimeError when no backend
    (keys or seam) is available.
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
                 "temperature": 0.2, "max_tokens": 800},
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
                 "temperature": 0.2, "max_tokens": 800},
            )
            text = data["choices"][0]["message"]["content"].strip()
            logger.info("agent llm provider=groq model=%s", GROQ_MODEL)
            return text, "groq:" + GROQ_MODEL
        except Exception as e:  # noqa: BLE001 — caller sees the last error
            last_error = e
            logger.warning("agent groq failed (%r)", e)
    raise RuntimeError("no LLM backend (OPENROUTER_API_KEY/GROQ_API_KEY empty; "
                       "pass http_post in tests) :: %r" % (last_error,))


def _maybe_trace(name: str) -> Callable:
    """LangSmith traceable decorator when tracing is on; else no-op."""
    try:
        if os.environ.get("LANGCHAIN_TRACING_V2", "").lower() not in (
                "true", "1"):
            raise ImportError("tracing off")
        if not os.environ.get("LANGCHAIN_API_KEY", ""):
            raise ImportError("no langsmith key")
        from langsmith import traceable  # type: ignore
        return traceable(name="lawsaathi:" + name, project_name=os.environ.get(
            "LANGCHAIN_PROJECT", "lawsathi"))
    except Exception:
        def deco(fn: Callable) -> Callable:
            return fn
        return deco


# ---------------------------------------------------------------------------
# Nodes — each takes and returns the shared state dict, appending to trace.
# ---------------------------------------------------------------------------

def node_intent(state: Dict[str, Any],
                llm: Optional[Callable] = None) -> Dict[str, Any]:
    query = state["query"]
    lang = state["lang"]
    query_en = query
    provider = state.get("provider", "")
    if lang != "en":
        if llm is not None:
            try:
                query_en, provider = llm([
                    {"role": "system",
                     "content": "Translate this family-law question to English. "
                                "Reply with only the translation."},
                    {"role": "user", "content": query},
                ])
                state["provider"] = provider
            except Exception as e:  # noqa: BLE001 — pivot is best-effort
                logger.warning("agent translate failed (%r); using raw query", e)
        # Without an LLM the raw query still retrieves (e5 is multilingual).
    state["query_en"] = query_en.strip() or query
    slots = extract_slots(state["query_en"])
    state["slots"] = slots
    state["intent"] = classify_intent(state["query_en"], slots)
    state["oos_redirect"] = is_oos(state["query_en"])
    state["trace"] = list(state.get("trace", [])) + ["intent"]
    return state


def node_planner(state: Dict[str, Any]) -> Dict[str, Any]:
    missing = missing_for(state.get("slots", {}),
                          state.get("query_en", ""))
    state["missing_slots"] = missing
    if missing:
        state["clarification"] = clarification_question(
            missing, state.get("lang", "en"))
    else:
        state["clarification"] = ""
    state["trace"] = list(state.get("trace", [])) + ["planner"]
    return state


def broaden_query(query_en: str, retries: int) -> str:
    if retries <= 0:
        return query_en
    acts = ("Hindu Marriage Act 1955 Special Marriage Act 1954 Hindu Adoption "
            "and Maintenance Act 1956 Hindu Succession Act 1956 Guardians and "
            "Wards Act 1890 Domestic Violence Act 2005 Indian Divorce Act 1869")
    if retries == 1:
        return "%s family law India %s" % (query_en, acts)
    # Retry 2: drop section numbers that may over-narrow the query.
    stripped = re.sub(r"section\s+\d+[A-Z\-]*", " ", query_en,
                      flags=re.IGNORECASE)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return "%s %s" % (stripped or query_en, acts)


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
                             state.get("retries", 0))
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
    try:
        extra = ws(query_en) or []
        evidence = evidence + list(extra)
    except Exception as e:  # noqa: BLE001 — web is best-effort
        logger.warning("agent web_search failed (%r)", e)
    state["evidence"] = evidence
    state["trace"] = list(state.get("trace", [])) + ["tools"]
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
        "marriage", "divorce", "custody", "maintenance", "adoption",
        "guardians", "domestic violence", "succession", "inheritance"))
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
    elif retries < MAX_RETRIES:
        state["verified"] = False
        state["retries"] = retries + 1
        state["needs_retry"] = True
    else:
        state["verified"] = False
        state["needs_retry"] = False
    state["trace"] = list(state.get("trace", [])) + ["verifier"]
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
    "hi": "यह प्रश्न मेरे पारिवारिक कानून के दायरे से बाहर है (भूमि, संपत्ति, आपराधिक, कर, आदि)। मैं केवल विवाह, तलाक, अभiraksha, भरण-पोषण, गोद लेना, उत्तराधिकार और घरेलू हिंसा में सहायता करता हूँ। कृप्या इस विषय के लिए विशेषज्ञ से परामर्श करें।",
    "kn": "ಈ ಪ್ರಶ್ನೆ ನನ್ನ ಕುಟುಂಬ ಕಾನೂನು ವ್ಯಾಪ್ತige ಹೊರಗide (ಭೂಮಿ, ಆsti, criminal, ತೆರige ಇত্যাদি). ನಾನು ಮarriage, ವಿಚ್ಛೇದn, palli, życie, data, uttaradhikar ಮತ್ತು kountubiK ಹinseyinda ಸಹay maDutténe. dayavuse bhayga este viṣaya khāti t jñannikinda samaraksha maDi.",
}

LOW_CONFIDENCE_DISCLAIMER = {
    "en": "Caution: this answer has lower verification confidence. Please consult a lawyer for your specific situation before acting.",
    "hi": "सावधानी: इस उत्तर का सत्यापन विश्वास कम है। कृपया कार्य करने से पहले अपनी स्थिति के लिए वकील से सलाह लें।",
    "kn": "ಎಚ್ಚರಿಕೆ: ಈ ಉತ್ತರದ ಪರಿಶೀಲನಾ ನ confidence ಕಡಿಮೆ. ದಯವಿಟ್ಟು ನಿಮ್ಮ specifieke ಪರಿಸ್ಥಿತige ವಕೀlru samparkisi.",
}

NEXT_STEPS = {
    "en": "Next steps: gather relevant documents (marriage certificate, court orders) and speak with a family-law lawyer for personalized guidance.",
    "hi": "अgale ciraN: prasaMGika dastaweiZ (vivaha praMamata, nyayAlaya Adesha) ekataroM kareN_ar vyaktigat mArgaDarshaNa ke lie pArivArika kAnUna vakIla se bAt kareN।",
    "kn": "muNani: sambanḍita dākhalēgalannu saṅgrahisi (mariyāde cetṭika, koraṭṭu opekke) mariyu vyaktigaṭṭa mārgašașiṅge kaṇḍa kŌtumbiḵ kānūna vakīlannu samakari.",
}


def compose_answer(state: Dict[str, Any]) -> Tuple[str, List[str], List[str]]:
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
    lines = []
    for i, hit in enumerate(evidence[:3], start=1):
        payload = hit.get("payload", {}) if isinstance(hit, dict) else {}
        text = str(payload.get("text", "") or "").strip()
        if len(text) > 600:
            text = text[:600].rstrip() + "…"
        lines.append("[%d] %s: %s" % (i, format_citation(payload), text))
    slots = state.get("slots", {})
    topic = slots.get("topic", "family-law question")
    head = ("Based on the family-law acts I retrieved for your %s question:"
            % topic)
    body = "\n".join(lines)
    tail = "Cited: " + "; ".join(citations) if citations else ""
    confidence = float(state.get("confidence", 1.0))
    # Low-confidence: stronger disclaimer + consult lawyer
    if confidence < 0.7:
        extra_disclaim = "\n\n" + LOW_CONFIDENCE_DISCLAIMER.get(lang, LOW_CONFIDENCE_DISCLAIMER["en"])
    else:
        extra_disclaim = ""
    answer = "%s\n%s\n%s\n%s%s\n\n%s" % (
        head, body, tail, DISCLAIMER.get(lang, DISCLAIMER["en"]),
        extra_disclaim, NEXT_STEPS.get(lang, NEXT_STEPS["en"]))
    if tone == "detailed":
        detail = ("Note: the sections cited above are from the bare text of the "
                  "family-law acts. If you need the exact wording or a case-law "
                  "reference, share the section number and I will verify it.")
        answer = "%s\n%s" % (answer, detail)
    return answer, citations, citation_sources


def node_response(state: Dict[str, Any],
                  llm: Optional[Callable] = None) -> Dict[str, Any]:
    lang = state.get("lang", "en")
    if state.get("clarification"):
        # Clarification path: answer in the user's language, no guessing.
        text = state["clarification"]
        if lang != "en" and llm is not None:
            try:
                text, provider = llm([
                    {"role": "system",
                     "content": "Render this clarification question in %s. "
                                "Reply with only the translation." % lang},
                    {"role": "user", "content": text},
                ])
                state["provider"] = provider
            except Exception as e:  # noqa: BLE001 — template is already local
                logger.warning("agent clarify translate failed (%r)", e)
        state["answer"] = text
        state["citations"] = []
        state["citation_sources"] = []
        state["trace"] = list(state.get("trace", [])) + ["response"]
        return state
    answer_en, citations, citation_sources = compose_answer(state)
    final = answer_en
    if lang != "en" and llm is not None and evidence_sufficient(
            state.get("evidence", [])):
        try:
            final, provider = llm([
                {"role": "system",
                 "content": "Render this legal answer in %s. Keep citations "
                            "and section names in English. Reply with only the "
                            "translation." % lang},
                {"role": "user", "content": answer_en},
            ])
            state["provider"] = provider
        except Exception as e:  # noqa: BLE001 — English answer still usable
            logger.warning("agent answer translate failed (%r)", e)
    state["answer"] = final
    state["citations"] = citations
    state["citation_sources"] = citation_sources
    state["trace"] = list(state.get("trace", [])) + ["response"]
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
              doc_id: str = "") -> Dict[str, Any]:
    """Run intent -> planner -> [clarify | tools <-> verifier] -> response.

    Returns the shared state dict (includes trace, answer, citations,
    provider, retries). Verifier loops back to tools at most MAX_RETRIES.
    """
    state = new_state(query, lang=lang, memory=memory)
    state["tone"] = tone
    state["doc_id"] = doc_id
    # Default LLM: live Groq/OpenRouter when keys exist, else None (templates).
    llm_fn = llm
    if llm_fn is None:
        if os.environ.get("GROQ_API_KEY", "") or os.environ.get(
                "OPENROUTER_API_KEY", ""):
            llm_fn = chat_complete
    state = node_intent(state, llm=llm_fn)
    state = node_planner(state)
    if state.get("clarification"):
        state = node_response(state, llm=llm_fn)
        state.pop("needs_retry", None)
        return state
    store = retriever if retriever is not None else default_retriever()
    state = node_tools(state, retriever=store, web_search=web_search)
    state = node_verifier(state, min_score=min_score)
    while state.pop("needs_retry", False):
        state = node_tools(state, retriever=store, web_search=web_search)
        state = node_verifier(state, min_score=min_score)
    state = node_response(state, llm=llm_fn)
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
