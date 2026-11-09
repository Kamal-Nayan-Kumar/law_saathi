#!/usr/bin/env python3
"""LLM-as-judge rubric prompts for Law Saathi generation eval (Phase C).

No live calls are made from this module. It only builds prompts and reports
whether a live judge provider is configured. The deterministic grader in
report/evals/run_generation.py covers section/term/must-not/script/
redirect/ask checks offline. Faithfulness, citation correctness and clarity
need a judge, and they run only when keys are present.

Fallback chain (first configured provider wins, no fallback on missing keys
at import time):
  1. Groq gpt-oss-120b     (env GROQ_API_KEY, model openai/gpt-oss-120b)
  2. OpenRouter llama      (env OPENROUTER_API_KEY, model
                            meta-llama/llama-3.3-70b-instruct)
  3. OpenCode Zen
     space-bunny-free      (env OPENCODE_ZEN_API_KEY / OPENCODE_API_KEY,
                            model space-bunny-free)

When no key is present the judge is skipped gracefully: every helper below
returns without contacting a network. Live generation eval needs keys and
will run when keys present; offline grading is the default.
"""
import os
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Provider fallback chain. Order matters; the first entry with a key set
# is the one a live run would use.
# ---------------------------------------------------------------------------
JUDGE_CHAIN: List[Dict[str, str]] = [
    {"provider": "groq", "model": "openai/gpt-oss-120b",
     "env_keys": "GROQ_API_KEY"},
    {"provider": "openrouter", "model": "meta-llama/llama-3.3-70b-instruct",
     "env_keys": "OPENROUTER_API_KEY"},
    {"provider": "opencode_zen", "model": "space-bunny-free",
     "env_keys": "OPENCODE_ZEN_API_KEY,OPENCODE_API_KEY"},
]

# ---------------------------------------------------------------------------
# Rubrics. Each entry is a self-contained prompt template with named slots:
#   QUESTION, ANSWER, CITATIONS, EVIDENCE, EXPECTATION
# The judge never sees the deterministic verdict or confidence; blinding
# prevents the judge from anchoring on the host pipeline's own judgement.
# ---------------------------------------------------------------------------
JUDGE_PROMPTS: Dict[str, str] = {
    "faithfulness": (
        "You are an evaluation judge for Indian family-law answers. "
        "You have NOT seen any automatic verdict, confidence score, or "
        "system flag. Judge only the evidence in front of you.\n\n"
        "Question:\n{QUESTION}\n\n"
        "Answer:\n{ANSWER}\n\n"
        "Cited passages:\n{EVIDENCE}\n\n"
        "Rate FAITHFULNESS: does every legal claim in the answer follow "
        "from the cited passages without adding conditions, numbers, "
        "sections or acts that are not there?\n"
        "Answer with ONLY JSON: "
        '{"faithful": true|false, "score": 1-5, "reason": "one sentence"}\n'
        "A single invented condition or wrong section is unfaithful (false)."
    ),
    "citation_correctness": (
        "You are an evaluation judge for Indian family-law answers. "
        "You have NOT seen any automatic verdict, confidence score, or "
        "system flag.\n\n"
        "Question:\n{QUESTION}\n\n"
        "Answer:\n{ANSWER}\n\n"
        "Citations:\n{CITATIONS}\n\n"
        "PASSAGES:\n{EVIDENCE}\n\n"
        "Rate CITATION CORRECTNESS: does each citation point at a passage "
        "that actually supports the sentence it follows, and does the "
        "cited act/section match the governing law for the question?\n"
        "Output ONLY JSON: "
        '{"correct": true|false, "score": 1-5, "reason": "one sentence"}\n'
        "Citing a real passage for the wrong proposition is incorrect."
    ),
    "clarity": (
        "You are an evaluation judge for plain-language legal answers. "
        "You have NOT seen any automatic verdict or confidence score.\n\n"
        "User question:\n{QUESTION}\n\n"
        "Answer:\n{ANSWER}\n\n"
        "Rate CLARITY: is the answer understandable to a non-lawyer in "
        "the same language as the question, with the next step stated in "
        "plain terms and no unexplained jargon?\n"
        "Output ONLY JSON: "
        '{"clear": true|false, "score": 1-5, "reason": "one sentence"}'
    ),
    "language_match": (
        "You are an evaluation judge for multilingual answers. "
        "You have NOT seen any automatic verdict or confidence score.\n\n"
        "User question:\n{QUESTION}\n\n"
        "Answer:\n{ANSWER}\n\n"
        "Rate LANGUAGE MATCH: is the answer written in the language and "
        "script of the question (Hindi questions in Devanagari, Kannada "
        "in Kannada script, Hinglish may mix)? English with a Hindi "
        "question is a failure.\n"
        "Output ONLY JSON: "
        '{"matched": true|false, "score": 1-5, "reason": "one sentence"}'
    ),
    "refusal_correctness": (
        "You are an evaluation judge for scope handling. "
        "You have NOT seen any automatic verdict or confidence score.\n\n"
        "User question:\n{QUESTION}\n\n"
        "System expectation (scope note, not a verdict):\n{EXPECTATION}\n\n"
        "Answer:\n{ANSWER}\n\n"
        "Rate REFUSAL CORRECTNESS: if the question is out of family-law "
        "scope, the answer must redirect without giving legal advice on "
        "the wrong topic; if it is in scope, it must answer rather than "
        "refuse. Answering an out-of-scope question confidently, or "
        "refusing an in-scope one, is a failure.\n"
        "Output ONLY JSON: "
        '{"correct": true|false, "score": 1-5, "reason": "one sentence"}'
    ),
}

# Axes the live judge would score, in reporting order.
JUDGE_AXES: List[str] = [
    "faithfulness", "citation_correctness", "clarity",
    "language_match", "refusal_correctness",
]

# ---------------------------------------------------------------------------
# Human-check sampling guide. The judge is a filter, not the ground truth:
# humans audit a fixed slice so grader drift or judge bias shows up.
# ---------------------------------------------------------------------------
HUMAN_SAMPLING_GUIDE: Dict[str, object] = {
    "min_sample": 20,
    "stratify_by": ["lang (en/hi/kn/hinglish)", "topic",
                    "deterministic verdict (pass/fail)"],
    "always_include": [
        "every must_redirect case",
        "every must_ask_any / clarification case",
        "every answer where judge and deterministic grader disagree",
        "every answer scoring 1-2 on any rubric axis",
    ],
    "gold_anchor_set": "report/dataset/golden_expanded.py "
                       "GOLDEN_EXPANDED ids",
    "blindness": "humans see question, answer, citations and evidence; "
                 "they do NOT see the deterministic verdict, judge "
                 "scores, or provider name until after scoring.",
    "agreement_target": "Cohen kappa >= 0.70 human vs judge on each axis; "
                        "human vs deterministic grader >= 0.80 on "
                        "section, term and refusal axes.",
    "tiebreak": "When human and judge disagree on faithfulness, the "
                "human label wins and the case is logged as a judge "
                "failure for the next prompt revision.",
}


def build_judge_messages(axis: str, question: str, answer: str,
                         citations: str = "", evidence: str = "",
                         expectation: str = "") -> List[Dict[str, str]]:
    """Return chat messages for one rubric axis, blind to verdict.

    The deterministic grader's pass/fail, confidence and verified flags
    are deliberately not slots in any prompt: the judge cannot see them.
    """
    if axis not in JUDGE_PROMPTS:
        raise ValueError("unknown axis %r, want one of %r" % (axis, JUDGE_AXES))
    text = JUDGE_PROMPTS[axis].format(
        QUESTION=question or "",
        ANSWER=answer or "",
        CITATIONS=citations or "(none cited)",
        EVIDENCE=evidence or "(no passage available to the judge)",
        EXPECTATION=expectation or "(none)",
    )
    return [{"role": "system", "content": "Judge only the evidence given."},
            {"role": "user", "content": text}]


def active_provider() -> Optional[Dict[str, str]]:
    """Return the first chain entry whose env key is set, or None.

    Reads the process env only; it never loads a .env file and never opens
    a socket. Callers who need .env loading do it before importing this.
    """
    for entry in JUDGE_CHAIN:
        for key in entry["env_keys"].split(","):
            if os.environ.get(key.strip()):
                return dict(entry, key=key.strip())
    return None


def live_judge_available() -> Tuple[bool, str]:
    """(available, note). Offline runs always return False without a key."""
    prov = active_provider()
    if prov is None:
        return False, ("no judge key in env; live LLM-as-judge skipped, "
                       "deterministic offline grading only")
    return True, "judge provider %s model %s via %s" % (
        prov["provider"], prov["model"], prov["key"])


def judge_skip_note() -> str:
    ok, note = live_judge_available()
    if ok:
        return "live judge available: " + note
    return ("LIVE GENERATION EVAL NEEDS KEYS AND WILL RUN WHEN KEYS "
            "PRESENT. " + note)


def main() -> int:
    print(judge_skip_note())
    for axis in JUDGE_AXES:
        print("  - %s" % axis)
    print("human sampling guide: min_sample=%d, blinded; see "
          "HUMAN_SAMPLING_GUIDE" % HUMAN_SAMPLING_GUIDE["min_sample"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
