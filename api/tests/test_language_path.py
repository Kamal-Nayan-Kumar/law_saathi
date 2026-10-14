"""The language path: pivot in, native answer out.

Two separate claims are tested here, and they were separated because they fail
differently:

1. The English pivot stays. Measured against the live collection, dropping it
   halved top-1 retrieval accuracy, so QUERY_PIVOT_PROMPT must keep telling the
   model to hold legal terms steady.

2. The answer is rewritten natively, not translated. A translator reproduces the
   source's difficulty, which is the whole complaint this replaced. The tests
   below pin the properties that make the rewrite safe: same citations, same
   length or shorter, actually in the right script, and a plain-English
   fallback when the rewrite comes back unusable.
"""
import re

from app import agent as A


# detect_lang reads the script of the question, not the hint, so a test state
# has to hold a real question in the language it is testing.
QUESTION_IN = {
    "en": "how much maintenance can a wife claim",
    "hi": "पत्नी अपने पति से कितनी मासगी मांग सकती है",
    "kn": "ಹೆಂಡತಿ ತನ್ನ ಗಂಡನಿಂದ ಎಷ್ಟು ಹಣಕಾಸು ಕೋಲಬಹುದು",
}


def _state(lang, evidence=None):
    st = A.new_state(QUESTION_IN[lang], lang=lang)
    assert st["lang"] == lang
    st["evidence"] = evidence or [{
        "id": "p1", "score": 0.9,
        "payload": {"act": "Hindu Marriage Act, 1955", "section": "Section 5",
                    "text": "(iii) the bride has not attained the age of "
                            "eighteen years."},
    }]
    st["verified"] = True
    return st


def _echo_llm(text):
    def llm(messages, **kw):
        return text, "stub"
    return llm


# --- the pivot prompt ------------------------------------------------------

def test_pivot_prompt_pins_the_terms_retrieval_depends_on():
    for term in ("dowry", "maintenance", "custody", "joint family",
                 "Hinglish", "in-laws"):
        assert term.lower() in A.QUERY_PIVOT_PROMPT.lower(), term


def test_pivot_prompt_forbids_widening_a_specific_term():
    # "Sampattu kelike" came back as "demanding property", which sent retrieval
    # to the Indian Succession Act instead of the Dowry Prohibition Act.
    low = A.QUERY_PIVOT_PROMPT.lower()
    assert "never replace them with a generic word" in low
    assert "not 'former spouse'" in low.replace('"', "'") or \
        "former spouse" in low


# --- the native rewrite ----------------------------------------------------

def test_rewrite_returns_the_model_text_untouched():
    out = A.rewrite_in_language(
        _state("hi"), "English draft that is long enough to pass the length "
        "check and is not looping at all.",
        _echo_llm("आप अदालत में आवेदन दे सकती हैं। कोर्ट राशि तय करेगा। "
                  "विवाह प्रमाणपत्र साथ ले जाएँ। यह पर्याप्त लंबा उत्तर है।"))
    assert "आप अदालत में आवेदन" in out


def test_rewrite_in_english_is_a_no_op():
    assert A.rewrite_in_language(_state("en"), "anything", _echo_llm("x")) == ""


def test_rewrite_keeps_the_citation_markers():
    draft = ("The court fixes the amount [1] and you may appeal [2]. "
             "That is the whole of what the passage says.")
    out = A.rewrite_in_language(
        _state("hi"), draft,
        _echo_llm("कोर्ट राशि तय करता है [1]। आप अपील कर सकते हैं [2]। "
                  "धारा में इतना ही लिखा है। यह पर्याप्त लंबा उत्तर है ताकि "
                  "यह जाँच पास कर सके।"))
    assert "[1]" in out and "[2]" in out


def test_rewrite_rejects_an_answer_that_stayed_in_english():
    # The failure this guards: the model ignores the instruction and echoes the
    # English back. Shipping that would be worse than shipping the English,
    # because the user would see a Hindi question answered in English with no
    # indication anything went wrong.
    out = A.rewrite_in_language(
        _state("hi"), "A perfectly reasonable English draft of decent length.",
        _echo_llm("A perfectly reasonable English draft of decent length, "
                  "returned unchanged because the model ignored the prompt."))
    assert out == ""


def test_rewrite_rejects_a_looping_answer():
    out = A.rewrite_in_language(
        _state("kn"), "An English draft of a perfectly reasonable length here.",
        _echo_llm("ನಿಮ್ಮ ಪ್ರಶ್ನೆಗೆ ಸ್ವಾಗರಸವಾಗಿದೆ. " * 12))
    assert out == ""


def test_rewrite_rejects_an_empty_answer():
    out = A.rewrite_in_language(
        _state("hi"), "An English draft of a perfectly reasonable length here.",
        _echo_llm(""))
    assert out == ""


def test_rewrite_survives_a_dead_model():
    def boom(messages, **kw):
        raise RuntimeError("provider in cooldown")

    assert A.rewrite_in_language(
        _state("hi"), "An English draft of a reasonable length.", boom) == ""


def test_lang_plain_rules_exist_for_every_non_english_language():
    for lang in ("hi", "kn"):
        rules = A.LANG_PLAIN_RULES[lang]
        # The swap table is the mechanism: naming the everyday word works,
        # asking for "simpler" does not.
        assert "maintenance" in rules.lower()
        assert "respondent" in rules.lower()


# --- node_response ---------------------------------------------------------

def test_non_english_answer_is_natively_rewritten_and_stays_cited():
    st = _state("hi")
    st["draft"] = ("The Hindu Marriage Act sets the minimum age for a bride "
                   "at eighteen [1]. You can check this on the official "
                   "government website before you act on it.\n\n"
                   "### What to do next\n\n- Check section 5 of the Act.\n"
                   "- Talk to a family-law lawyer about your case.")
    seen = {}

    def replier(messages, **kw):
        seen["system"] = messages[0]["content"]
        return ("हिंदू विवाह अधिनियम में लड़की की उमर 18 साल तय की गई है [1]। "
                "कार्रवाई से पहले सरकारी वेबसाइट पर जाँच लें।\n\n"
                "### आगे क्या करें\n\n- अधिनियम की धारा 5 देखें।\n"
                "- किसी वकील से बात करें।\n\nयह पर्याप्त लंबा उत्तर है, इसमें "
                "कुछ और कहने को भी जगह है।"), "stub"

    out = A.node_response(st, llm=None, translate_in=replier)
    assert "हिंदू विवाह अधिनियम" in out["answer"]
    assert "[1]" in out["answer"]
    assert "18 साल" in out["answer"]
    # The localized disclaimer now survives, which the old translate path
    # threw away by replacing the composed answer wholesale.
    assert A.DISCLAIMER["hi"] in out["answer"]
    assert out["citations"]


def test_non_english_falls_back_to_english_rather_than_serving_nothing():
    st = _state("hi")
    st["draft"] = ("The Hindu Marriage Act sets the minimum age for a bride "
                   "at eighteen [1]. Check it before you act on it.\n\n"
                   "### What to do next\n\n- Check section 5 of the Act.")

    def dead(messages, **kw):
        return "", "stub"

    out = A.node_response(st, llm=None, translate_in=dead)
    assert "eighteen" in out["answer"]
    assert out["citations"]


def test_english_answer_is_never_sent_to_the_rewriter():
    st = _state("en")
    st["draft"] = ("The Hindu Marriage Act sets the minimum age at eighteen "
                   "[1]. Check it before you act.\n\n### What to do next\n\n"
                   "- Read section 5.")
    calls = []

    def spy(messages, **kw):
        calls.append(messages)
        return "should not happen", "stub"

    out = A.node_response(st, llm=None, translate_in=spy)
    assert calls == []
    assert "eighteen" in out["answer"]


# --- the degraded pivot ----------------------------------------------------

def test_a_failed_pivot_does_not_trigger_a_pointless_clarification():
    """Every provider in cooldown used to turn a Hindi question into
    'what is this about?' — telling a user who had already explained that
    they had been unclear."""
    st = A.new_state("मेरे पति मुझे मारते हैं", lang="hi")
    # Force the degraded state: no pivot, so no English to read a topic from.
    st["query_en"] = "मेरे पति मुझे मारते हैं"
    st["slots"] = {}
    st["pivot_ok"] = False
    st["plan"] = A.default_plan(st)
    A.node_planner(st, llm=None)
    assert st["missing_slots"] == []
    assert not st["clarification"]


def test_a_missing_topic_still_asks_when_the_pivot_worked():
    st = A.new_state("what is it then", lang="hi")
    st["query_en"] = "what is it then"
    st["slots"] = {}
    st["pivot_ok"] = True
    st["plan"] = A.default_plan(st)
    A.node_planner(st, llm=None)
    assert st["missing_slots"] == ["topic"]


def test_pivot_ok_defaults_to_true_in_a_fresh_state():
    assert A.new_state("hello", lang="en")["pivot_ok"] is True


# --- language detection (unchanged, but load-bearing for all of the above) --

def test_detect_lang_still_decides_the_output_language():
    assert A.detect_lang("my husband beats me") == "en"
    assert A.detect_lang("मेरे पति मुझे मारते हैं") == "hi"
    assert A.detect_lang("mere pati mujhe marte hai") == "hi"
    assert A.detect_lang("ನನ್ನ ಗಂಡ ನನ್ನನ್ನು ಹೊಡೆಯುತ್ತಾನೆ") == "kn"


def test_every_answer_language_has_plain_language_rules_or_is_english():
    for lang in A.LANG_NAMES:
        if lang == "en":
            continue
        assert lang in A.LANG_PLAIN_RULES, lang
        assert lang in A.SECTION_HEADINGS, lang
        assert lang in A.DISCLAIMER, lang
        assert lang in A.NEXT_STEPS, lang
        assert lang in A.AMENDMENT_CAVEAT, lang


def test_kannada_rewrite_is_not_accepted_as_hindi_or_english():
    # Guards the script check: a Kannada answer must not pass the Hindi regex
    # and vice versa.
    out = A.rewrite_in_language(
        _state("kn"), "An English draft of a perfectly reasonable length here.",
        _echo_llm("ಹೆಂಡತಿಗೆ ಗಂಡನಿಂದ ಹಣಕಾಸು ಸಿಗುತ್ತದೆ. ಎಷ್ಟು ಬೇಕೆಂದು "
                  "ನ್ಯಾಯಾಲಯ ತೀರ್ಮಾನಿಸುತ್ತದೆ. ದಾಖಲೆ ಸಂಗ್ರಹಿಸಿ ಅರ್ಜಿ "
                  "ಸಲ್ಲಿಸಿ."))
    assert out and re.search(r"[\u0C80-\u0CFF]", out)
    assert not re.search(r"[\u0900-\u097F]", out)


# --- a rewrite that stopped mid-sentence -----------------------------------

def test_ends_mid_sentence_sees_devanagari_and_kannada():
    # truncated_mid_sentence() only knows English connectives. This is the real
    # Hindi failure: the answer trailed off at "इसलिए लड़की की शादी की" and
    # shipped, because nothing could tell it was broken.
    assert A.ends_mid_sentence("आप कोर्ट में आवेदन दे सकती हैं। इसलिए लड़की की")
    assert A.ends_mid_sentence(
        "ನೀವು ಅರ್ಜಿ ಸಲ್ಲಿಸಬಹುದು. ಆದ್ದರಿಂದ ಮಕುವನ")
    assert not A.ends_mid_sentence("आप कोर्ट में आवेदन दे सकती हैं।")


def test_ends_mid_sentence_ignores_the_trailing_disclaimer_and_bullets():
    ok = ("कोर्ट राशि तय करेगा।\n\n### आगे क्या करें\n\n- धारा 5 देखें।\n"
          "- वकील से बात करें।\n\n*केवल सामान्य जानकारी, कानूनी सलाह नहीं।*")
    assert not A.ends_mid_sentence(ok)


def test_rewrite_stopping_mid_sentence_is_rejected():
    # Live failure: the Hindi rewrite ended on a dangling clause and shipped.
    out = A.rewrite_in_language(
        _state("hi"), "An English draft of a perfectly reasonable length here.",
        _echo_llm("हिंदू विवाह अधिनियम में शर्त तोड़ने पर जेल हो सकता है [1]. "
                  "आपके पास जो अंश हैं, उनमें उम्र की शर्त नहीं बताई गई. इसलिए "
                  "लड़की की शादी की"))
    assert out == ""


def test_a_truncated_bullet_is_rejected_too():
    # Live failure: the Hinglish rewrite ran out of tokens inside a bullet and
    # shipped "…या काम के पास न".
    out = A.rewrite_in_language(
        _state("hi"), "An English draft of a perfectly reasonable length here.",
        _echo_llm("कोर्ट आपकी रक्षा कर सकता है [1]।\n\n"
                  "### आगे क्या करें\n\n"
                  "- अदालत से कहें कि वह आपके घर या काम के पास न"))
    assert out == ""


def test_a_finished_bullet_list_is_accepted():
    out = A.rewrite_in_language(
        _state("hi"), "An English draft of a perfectly reasonable length here.",
        _echo_llm("कोर्ट आपकी रक्षा कर सकता है [1]।\n\n"
                  "### आगे क्या करें\n\n"
                  "- चोटों की तस्वीरें इकट्ठा करें।\n"
                  "- नज़दीकी अदालत में आवेदन दें।"))
    assert "चोटों की तस्वीरें" in out


# --- one next-steps heading, in the reader's language ----------------------

def test_rewrite_is_told_the_exact_localized_next_steps_heading():
    seen = {}

    def spy(messages, **kw):
        seen["system"] = messages[0]["content"]
        return ("कोर्ट राशि तय करेगा [1]। आप आवेदन दे सकती हैं।\n\n"
                "### आगे क्या करें\n\n- धारा 5 देखें।\n- वकील से बात करें।\n\n"
                "यह पर्याप्त लंबा उत्तर है, इसमें कुछ और भी कहने को जगह है।"), "stub"

    A.rewrite_in_language(_state("hi"), "An English draft of reasonable length.", spy)
    assert "### %s" % A.headings_for("hi")[1] in seen["system"]


def test_no_duplicate_next_steps_heading_after_a_rewrite():
    st = _state("hi")
    st["draft"] = ("The Hindu Marriage Act sets the minimum age at eighteen "
                   "[1]. Check it before you act.\n\n### What to do next\n\n"
                   "- Read section 5 of the Act.")

    def replier(messages, **kw):
        return ("हिंदू विवाह अधिनियम में उम्र 18 साल है [1]। कार्रवाई से पहले "
                "जाँच लें।\n\n### आगे क्या करें\n\n- अधिनियम की धारा 5 पढ़ें।\n\n"
                "यह पर्याप्त लंबा उत्तर है, इसमें कुछ और कहने को भी जगह है।"), "stub"

    out = A.node_response(st, llm=None, translate_in=replier)
    assert out["answer"].count(A.headings_for("hi")[1]) == 1