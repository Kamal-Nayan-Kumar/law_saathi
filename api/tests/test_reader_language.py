"""The reader's language, everywhere: steps, sources, fallbacks, and the answer.

The three claims, each of which failed live before it was an assertion:

1. The step log is written in the reader's language. A Hindi reader used to get
   five English sentences explaining what the agent had done — the three things
   the panel exists to say (which Act, that a Bill was set aside, that the
   answer carries a caution) were unreadable to exactly the person they were
   for.
2. The reader's own words are searched as well as the English pivot. e5-small is
   multilingual, so a Kannada or Hindi question does match English statute text;
   what it cannot do is match legal terms, which is the pivot's job. Running
   both is what stops a bad pivot from losing a section.
3. A follow-up is answered from the conversation, in the conversation's
   language, without restating it — and a plan can never skip the bare Acts.
"""
import re

from app import agent as A


HIT_KN = {"id": "k1", "score": 0.88,
          "payload": {"act": "Dowry Prohibition Act, 1961",
                      "section": "Section 4",
                      "text": "If any person demands dowry, he shall be "
                              "punishable with imprisonment."}}
HIT_EN = {"id": "e1", "score": 0.71,
          "payload": {"act": "Indian Succession Act, 1925",
                      "section": "Section 25",
                      "text": "Where the intestate has left a widow, she "
                              "shall take one share."}}


class SplitRetriever:
    """Returns a different answer per query, so the two paths are visible.

    The Dowry Prohibition Act comes back only for a Kannada query and the
    Succession Act only for the English one — exactly the shape of the failure
    the second path exists to catch.
    """

    def __init__(self):
        self.queries = []
        # Every call with the filter it was made with. The Act-scoped
        # fetches are a separate thing: they are how a topic governed by
        # two Acts gets both of them, and they are deliberately extra
        # queries. The tests below are about the pivot path, so they count
        # the unfiltered ones.
        self.calls = []

    def search_text(self, text, top_k=6, filter_payload=None):
        self.queries.append(text)
        self.calls.append((text, filter_payload))
        if re.search(r"[\u0C80-\u0CFF]", text):
            return [dict(HIT_KN)]
        return [dict(HIT_EN)]


# --- 1. the step log is in the reader's language -----------------------------

def test_every_trace_line_has_a_hindi_and_kannada_rendering():
    """A new trace line with no translation falls back to English, which is the
    old defect. This test fails the moment somebody adds one and forgets."""
    for key, bank in A.TRACE_TEXT.items():
        for lang in ("hi", "kn"):
            assert bank.get(lang), "%s has no %s rendering" % (key, lang)
        assert bank.get("en"), "%s has no English rendering" % key


def test_trace_text_falls_back_to_english_rather_than_raising():
    assert A.trace_text("hi", "not_a_real_key", anything=1) == "not_a_real_key"
    # A template whose fields are missing renders rather than raising: the
    # Thinking panel must never cost the user their answer.
    assert A.trace_text("hi", "intent_summary") == A.TRACE_TEXT["intent_summary"]["hi"]


def test_a_hindi_run_writes_hindi_steps():
    st = A.new_state("मेरे पति मुझे मारते हैं", lang="hi")
    st["slots"] = A.extract_slots("my husband beats me")
    st["plan"] = A.default_plan(st)
    A.node_planner(st, llm=None)
    said = " ".join(d["detail"] for d in st["trace_detail"])
    assert re.search(r"[\u0900-\u097F]", said), "no Devanagari in the planner step: %r" % said
    assert "Hindi" not in said, "the language name is still English: %r" % said


def test_a_kannada_run_writes_kannada_steps():
    st = A.new_state("ನನ್ನ ಗಂಡ ನನ್ನನ್ನು ಹೊಡೆಯುತ್ತಾನೆ", lang="kn")
    st["slots"] = A.extract_slots("my husband beats me")
    st["plan"] = A.default_plan(st)
    A.node_planner(st, llm=None)
    said = " ".join(d["detail"] for d in st["trace_detail"])
    assert re.search(r"[\u0C80-\u0CFF]", said), "no Kannada in the planner step: %r" % said


def test_the_language_is_named_in_the_readers_own_language():
    assert A.LANGUAGE_NAMES["hi"]["hi"] == "हिंदी"
    assert A.LANGUAGE_NAMES["kn"]["kn"] == "ಕನ್ನಡ"
    assert A.LANGUAGE_NAMES["hi"]["kn"] == "ಹಿಂದಿ"


def test_a_topic_is_named_in_the_readers_language_not_as_an_identifier():
    st = A.new_state("मुझे तलाक चाहिए", lang="hi")
    st["query_en"] = "I want a divorce"
    st["slots"] = A.extract_slots(st["query_en"])
    A.node_intent(st, llm=None)
    said = " ".join(d["detail"] for d in st["trace_detail"])
    assert "तलाक" in said
    # The raw English identifier is what retrieval is keyed on; printing it to
    # the reader is the defect.
    assert "'divorce'" not in said


def test_plural_is_not_an_s_in_hindi_or_kannada():
    # "3 ವಿಭಾಗs." and "2 और धाराs." read as a stray Latin letter mid-sentence.
    assert A._plural("en", 2) == "s"
    assert A._plural("en", 1) == ""
    assert A._plural("hi", 2) == ""
    assert A._plural("kn", 1) == ""


def test_no_evidence_answer_is_localised_not_english_with_a_hindi_sticker():
    """A Hindi reader used to get three English sentences and a Hindi disclaimer
    attached underneath, which is worse than either alone."""
    for lang, script in (("hi", "[\u0900-\u097F]"), ("kn", "[\u0C80-\u0CFF]")):
        st = A.new_state("कुछ भी नहीं" if lang == "hi" else "ಏನೂ ಇಲ್ಲ", lang=lang)
        answer, citations, _ = A.compose_answer(st, "")
        assert re.search(script, answer), "%s: %r" % (lang, answer)
        assert A.DISCLAIMER[lang] in answer
        assert not citations


def test_every_language_has_a_no_evidence_answer():
    for lang in A.LANG_NAMES:
        assert lang in A.NO_EVIDENCE, lang
        assert lang in A.DIVORCE_ACT_LIST, lang
        assert lang in A.NO_EVIDENCE_ASK, lang


# --- 2. the reader's own words are searched too ------------------------------

def test_the_readers_own_words_are_searched_as_well_as_the_pivot():
    st = A.new_state("ಸಂಪತ್ತು ಕೋಲಿಕೆ ಮಾಡುತ್ತಿದ್ದಾರೆ, ನಾನು ಏನು ಮಾಡಬೇಕು?", lang="kn")
    st["query_en"] = "in-laws are demanding dowry from me"
    st["slots"] = {"topic": "dowry"}
    ret = SplitRetriever()
    out = A.node_tools(st, retriever=ret, web_search=lambda q, **k: [])
    # Two searches for one tool: the English pivot and the reader's own words.
    assert len(ret.queries) >= 2, ret.queries
    assert any(re.search(r"[\u0C80-\u0CFF]", q) for q in ret.queries), ret.queries
    # The section only the Kannada query finds must survive into the evidence.
    acts = {str(h["payload"].get("act")) for h in out["evidence"]}
    assert "Dowry Prohibition Act, 1961" in acts, acts
    said = " ".join(d["detail"] for d in out["trace_detail"])
    assert re.search(r"[\u0C80-\u0CFF]", said), "the step log stayed English"


def test_an_english_question_is_not_searched_twice():
    """The second path only exists for a language the pivot had to translate.
    Running it on English would double every search in the product."""
    st = A.new_state("how much maintenance can a wife claim", lang="en")
    st["query_en"] = "how much maintenance can a wife claim"
    st["slots"] = {"topic": "maintenance"}
    ret = SplitRetriever()
    A.node_tools(st, retriever=ret, web_search=lambda q, **k: [])
    unfiltered = [t for t, f in ret.calls if not f]
    assert len(unfiltered) == 1, ret.queries


def test_the_two_paths_agree_on_what_they_found_rather_than_doubling_it():
    """A hit both searches return must be counted once."""
    class Same(SplitRetriever):
        def search_text(self, text, top_k=6, filter_payload=None):
            self.queries.append(text)
            self.calls.append((text, filter_payload))
            return [dict(HIT_EN)]

    st = A.new_state("सुसाइड नहीं चाहिए", lang="hi")
    st["query_en"] = "succession of property"
    st["slots"] = {"topic": "succession"}
    ret = Same()
    out = A.node_tools(st, retriever=ret, web_search=lambda q, **k: [])
    unfiltered = [t for t, f in ret.calls if not f]
    assert len(unfiltered) == 2, ret.queries
    # The Act-scoped fetches are extra queries on purpose, but a hit they
    # both return is still counted once.
    assert len(out["evidence"]) == 1, out["evidence"]


# --- 3. the plan can never skip the bare Acts --------------------------------

def test_a_plan_of_only_web_searches_gets_the_acts_back():
    """A live Hindi follow-up ("and if I want a divorce?") came back with no
    evidence at all: the model decided the Acts did not govern it, searched
    only the web, and the web had nothing."""
    plan = {"governing_act": "",
            "reasoning": "Muslim personal law is not in the corpus",
            "steps": [{"tool": A.WEB_SEARCH, "query": "talaq procedure"}]}
    st = A.new_state("how do I get a divorce", lang="en")
    st["slots"] = {"topic": "divorce"}
    st["query_en"] = "how do I get a divorce"
    out = A.normalise_plan(plan, st)
    tools = [s["tool"] for s in out["steps"]]
    assert A.ACT_SEARCH in tools, tools
    assert tools[0] == A.ACT_SEARCH, "the Acts go first, not last"


# --- 4. length follows the question ------------------------------------------

def test_a_one_fact_question_is_brief():
    assert A.answer_length("what is the minimum age to marry") == "brief"
    assert A.answer_length("who gets custody of the child") == "brief"


def test_a_described_situation_gets_the_full_treatment():
    assert A.answer_length(
        "my wife left the house in 2022 and refuses to come back, and my son "
        "is 9 years old, so who keeps him") == "full"
    assert A.answer_length(
        "my husband beats me and does not give money for the children") == "full"


def test_the_writing_prompt_carries_the_length_and_the_follow_up_rule():
    st = A.new_state("what is the minimum age to marry", lang="en")
    st["evidence"] = [{"score": 0.9, "payload": {
        "act": "Hindu Marriage Act, 1955", "section": "Section 5",
        "text": "(iii) the bride has not attained the age of eighteen "
                "years."}}]
    st["slots"] = {"topic": "marriage"}
    seen = {}

    def spy(messages):
        seen["system"] = messages[0]["content"]
        return ("The bride must be eighteen [1]. A groom must be twenty-one "
                "[1]."), "stub"

    A.write_plain_answer(st, spy)
    assert "Length: SHORT" in seen["system"]
    assert "FOLLOW-UP" not in seen["system"]


def test_a_follow_up_is_told_to_use_the_history_without_repeating_it():
    st = A.new_state("what about my daughter?", lang="en")
    st["history"] = [{"role": "user", "content": "who gets custody of my child"},
                     {"role": "assistant", "content": "The court decides."}]
    st["evidence"] = [{"score": 0.9, "payload": {
        "act": "Guardians and Wards Act, 1890", "section": "Section 17",
        "text": "The welfare of the minor shall be the first consideration."}}]
    st["slots"] = {"topic": "custody"}
    seen = {}

    def spy(messages):
        seen["system"] = messages[0]["content"]
        return ("A daughter is treated the same as a son [1]. The court looks "
                "at her welfare first."), "stub"

    A.write_plain_answer(st, spy)
    assert "FOLLOW-UP" in seen["system"]
    assert "restating" in seen["system"].lower() or "restate" in seen["system"].lower()


# --- the rewrite that must not read as a translation -------------------------

def test_the_rewrite_is_told_not_to_follow_the_english_order():
    seen = {}

    def spy(messages):
        seen["system"] = messages[0]["content"]
        return ("आप अदालत में जाकर कह सकती हैं कि वह आपके घर के पास न आए [1]। "
                "इसके लिए वकील की ज़रूरत नहीं। यह उत्तर पर्याप्त लंबा है।"), "stub"

    st = A.new_state("मेरे पति मुझे मारते हैं", lang="hi")
    st["evidence"] = [{"score": 0.9, "payload": {
        "act": "Domestic Violence Act, 2005", "section": "Section 18",
        "text": "The Magistrate may pass a protection order."}}]
    st["verified"] = True
    A.rewrite_in_language(st, "You may ask the Magistrate for a protection "
                              "order so that he stays away from the house [1].",
                          spy)
    assert "English sentence order" in seen["system"]
    assert "SCRIPT" in seen["system"]


def test_the_rewrite_glosses_the_words_that_came_back_in_latin_letters():
    for lang, words in (("hi", ("एफआईआर", "कोर्ट")), ("kn", ("ಎಫ್ಐಆರ್", "ಕೋರ್ಟ್"))):
        for word in words:
            assert word in A.LANG_PLAIN_RULES[lang], f"{word} missing in {lang}"
    assert "SCRIPT" in A.NATIVE_SIMPLICITY_RULES

