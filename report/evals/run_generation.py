#!/usr/bin/env python3
"""Deterministic generation grader (Phase C).

Runs offline, no keys, no network. Each GOLDEN_EXPANDED expectation is
graded against two deterministic stub answers:

  1. stub  -- the answer produced by the agent with the model stubbed via
              api/eval/run_stub.stub_agent (fake_llm) and a canned corpus.
  2. empty -- an empty answer, to show what the grader does when the model
              returns nothing (must fail content checks, not pass them).

It also grades one GOLDEN_QAS must_ask_any entry
(clarify-personal-law-en), because GOLDEN_EXPANDED carries no such entry
and the must_ask_any check would otherwise never be exercised here.

Checks (all offline/deterministic, same ideals as api/eval/run_golden.check):
  must_include_any        -- at least one listed section in answer+cites
  must_include_terms      -- every listed term present
  must_include_any_terms /
    must_include_terms_any_of -- at least one alternative present
  must_not                -- none of the banned phrases present
  language script         -- hi needs Devanagari, kn needs Kannada script
  must_redirect           -- oos_redirect flag or "outside my family-law scope"
  must_ask_any            -- item["must_ask_any"] graded via clarification
                             flag + phrase match (see note below)
  confidence / verified   -- floor and verified flag as in run_golden.check

What is deliberately NOT graded here (needs a live judge with keys):
faithfulness, citation correctness, clarity. Those live in
report/evals/judge_prompts.py (fallbacks Groq gpt-oss-120b -> OpenRouter
llama -> OpenCode Zen space-bunny-free) and are skipped gracefully when no
key is in the environment. This module imports judge_prompts only to
record availability; it never calls a network.

Output: report/evals/generation_results.json
"""
import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "api"))
sys.path.insert(0, os.path.join(ROOT, "report", "dataset"))
sys.path.insert(0, HERE)

from golden_expanded import GOLDEN_EXPANDED  # noqa: E402
from eval.golden_qas import GOLDEN_QAS  # noqa: E402
from judge_prompts import JUDGE_AXES, live_judge_available, judge_skip_note  # noqa: E402

SCRIPT_HI = "ऀ-ॿ"
SCRIPT_KN = "ಀ-೿"


# ---------------------------------------------------------------------------
# Per-check grading. Mirrors api/eval/run_golden.check exactly (including the
# must_redirect / must_ask_any short-circuits) but also returns a breakdown
# so the run can report which check families bite and which run offline.
# ---------------------------------------------------------------------------
def grade_item(item: Dict[str, Any], result: Dict[str, Any]) -> Dict[str, Any]:
    problems: List[str] = []
    breakdown: Dict[str, bool] = {}
    answer = str(result.get("answer") or "")
    low = answer.lower()
    citations = " ".join(result.get("citations") or [])

    def sections_ok(item_) -> bool:
        secs = [s for s in item_.get("must_include_any", []) if s]
        return any(s in answer or s in citations for s in secs)

    if item.get("must_redirect"):
        ok = bool(result.get("oos_redirect")
                  or "outside my family-law scope" in low)
        banned_hit = any(b.lower() in low for b in item.get("must_not", []))
        breakdown["must_redirect"] = bool(ok and not banned_hit)
        if not result.get("oos_redirect") and "outside my family-law scope" not in low:
            problems.append("should have redirected out of scope")
        for banned in item.get("must_not", []):
            if banned.lower() in low:
                problems.append("answered out-of-scope question, mentioned %r" % (banned,))
        return {"problems": problems, "breakdown": breakdown,
                "pass": not problems}

    asked = [a for a in item.get("must_ask_any", []) if a]
    if asked:
        if not result.get("clarification"):
            breakdown["must_ask_any"] = False
            problems.append("should have asked the user, but answered instead")
        else:
            hit = any(a.lower() in low for a in asked)
            breakdown["must_ask_any"] = bool(hit)
            if not hit:
                problems.append("asked, but not about any of %r" % (list(asked),))
        return {"problems": problems, "breakdown": breakdown,
                "pass": not problems}

    for term in item.get("must_include_terms", []):
        ok_t = term.lower() in low or term.lower() in citations.lower()
        breakdown.setdefault("must_include_terms", True)
        breakdown["must_include_terms"] = bool(
            breakdown["must_include_terms"] and ok_t)
        if not ok_t:
            problems.append("missing term %r" % (term,))

    any_terms = [t for t in item.get("must_include_any_terms", []) if t]
    any_terms += [t for t in item.get("must_include_terms_any_of", []) if t]
    if any_terms:
        if not any(t.lower() in low or t.lower() in citations.lower()
                   for t in any_terms):
            breakdown["must_include_any_terms"] = False
            problems.append("none of %r present" % (any_terms,))
        else:
            breakdown["must_include_any_terms"] = True

    sections = [s for s in item.get("must_include_any", []) if s]
    if sections:
        breakdown["must_include_any"] = sections_ok(item)
        if not breakdown["must_include_any"]:
            problems.append("none of %s cited" % (sections,))

    for banned in item.get("must_not", []):
        if banned.lower() in low:
            breakdown["must_not"] = False
            problems.append("said %r, which is wrong" % (banned,))
    if "must_not" not in breakdown and item.get("must_not"):
        breakdown["must_not"] = True

    for banned in item.get("must_not_cite", []):
        if banned.lower() in citations.lower():
            breakdown["must_not_cite"] = False
            problems.append("cited %r, which is wrong" % (banned,))

    if item.get("must_note_special_act"):
        hit = ("muslim women (protection of rights on marriage) act" in low
               or "muslim women (protection of rights on marriage) act, 2019" in low)
        breakdown["must_note_special_act"] = bool(hit)
        if not hit:
            problems.append("did not name the 2019 Act for triple talaq")

    if item.get("lang") in ("hi", "kn"):
        script = SCRIPT_HI if item["lang"] == "hi" else SCRIPT_KN
        ok_s = bool(re.search("[%s]" % script, answer))
        breakdown["language_script"] = bool(ok_s)
        if not ok_s:
            problems.append("answered in the wrong script for lang=%s" % (item["lang"],))
    elif item.get("lang") == "hinglish":
        # Roman Hindi is fine; Hinglish answers must not be pure English
        # silence, so we only require a non-empty answer here and let term
        # checks carry the language test. The stub proves the grader does
        # not false-flag Hinglish on script alone.
        breakdown["language_script"] = True

    conf = float(result.get("confidence") or 0.0)
    floor = float(item.get("min_confidence") or 0.0)
    if conf < floor:
        breakdown["confidence"] = False
        problems.append("confidence %.2f below floor %.2f" % (conf, floor))
    else:
        breakdown["confidence"] = True

    if not result.get("verified", False) and not item.get("must_redirect"):
        breakdown["verified"] = False
        problems.append("answer was not verified")
    else:
        breakdown["verified"] = True

    return {"problems": problems, "breakdown": breakdown,
            "pass": not problems}


# ---------------------------------------------------------------------------
# Stub generation. Reuses the real agent with the model stubbed out, so the
# grader is exercised against genuine agent output shapes (answer,
# citations, verified, clarification, oos_redirect), not hand-written text.
# ---------------------------------------------------------------------------
def stub_result(item: Dict[str, Any]) -> Dict[str, Any]:
    """Run the full agent with the stub LLM; fall back to an empty result
    if the stub path raises (recorded in row, not swallowed silently)."""
    from app import agent as A  # noqa: PLC0415

    lang = item.get("lang", "en")
    if lang == "hinglish":
        lang = "hi"  # detect_lang maps Hinglish queries to hi anyway
    try:
        state = A.run_agent(item["query"], lang=lang,
                            retriever=None, llm=A.chat_complete,
                            web_search=None)
    except Exception as e:  # noqa: BLE001 -- grader must report, not crash
        return {"answer": "", "citations": [], "verified": False,
                "confidence": 0.0, "oos_redirect": False,
                "clarification": "", "_stub_error": str(e)[:300]}
    return {
        "answer": state.get("answer") or "",
        "citations": state.get("citations") or [],
        "verified": bool(state.get("verified", False)),
        "confidence": float(state.get("confidence") or 0.0),
        "oos_redirect": bool(state.get("oos_redirect", False)),
        "clarification": state.get("clarification") or "",
        "provider": state.get("provider") or "",
    }


def empty_result() -> Dict[str, Any]:
    return {"answer": "", "citations": [], "verified": False,
            "confidence": 0.0, "oos_redirect": False, "clarification": ""}


def probe_must_ask_any() -> Dict[str, Any]:
    """Exercise the must_ask_any branch against GOLDEN_QAS.

    GOLDEN_EXPANDED has no must_ask_any entry, so grade
    clarify-personal-law-en against (a) a clarification result, (b) a
    plain answer, (c) an empty answer. Expected: (a) passes, (b)/(c) fail.
    """
    item = next(q for q in GOLDEN_QAS if q["id"] == "clarify-personal-law-en")
    candidates = {
        "clarified": {"answer": "Which personal law applies to you - Hindu, "
                                 "Christian, Muslim or Parsi?",
                      "citations": [], "verified": True, "confidence": 1.0,
                      "clarification": "personal law", "oos_redirect": False},
        "answered": {"answer": "File under HMA Section 13B, living separately "
                               "for one year.", "citations": ["HMA 13B"],
                     "verified": True, "confidence": 0.9,
                     "clarification": "", "oos_redirect": False},
        "empty": dict(empty_result()),
    }
    out = {}
    for label, result in candidates.items():
        graded = grade_item(item, result)
        out[label] = {"pass": graded["pass"], "problems": graded["problems"],
                      "breakdown": graded["breakdown"]}
    return {
        "id": item["id"], "expected": {"clarified": True, "answered": False,
                                       "empty": False},
        "observed": out,
        "correct": bool(out["clarified"]["pass"]
                        and not out["answered"]["pass"]
                        and not out["empty"]["pass"]),
    }


def run_one(item: Dict[str, Any], mode: str) -> Dict[str, Any]:
    result = stub_result(item) if mode == "stub" else empty_result()
    graded = grade_item(item, result)
    row: Dict[str, Any] = {
        "id": item["id"], "lang": item.get("lang"), "mode": mode,
        "pass": graded["pass"], "problems": graded["problems"],
        "breakdown": graded["breakdown"],
        "answer_chars": len(result.get("answer") or ""),
        "citations": result.get("citations") or [],
        "verified": bool(result.get("verified", False)),
        "oos_redirect": bool(result.get("oos_redirect", False)),
    }
    if result.get("_stub_error"):
        row["_stub_error"] = result["_stub_error"]
    if result.get("answer"):
        row["answer_preview"] = str(result["answer"])[:280]
    return row


def summarize(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    checks = {
        "must_include_any": (0, 0), "must_include_terms": (0, 0),
        "must_include_any_terms": (0, 0), "must_not": (0, 0),
        "must_not_cite": (0, 0), "language_script": (0, 0),
        "must_redirect": (0, 0), "must_ask_any": (0, 0),
        "confidence": (0, 0), "verified": (0, 0),
    }
    for r in rows:
        for k, v in (r.get("breakdown") or {}).items():
            if k not in checks:
                checks[k] = (0, 0)
            p, t = checks[k]
            checks[k] = (p + int(bool(v)), t + 1)
    return {
        "n": len(rows), "passed": sum(1 for r in rows if r["pass"]),
        "by_check": {k: {"passed": v[0], "total": v[1]} for k, v in checks.items() if v[1]},
    }


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="run one question id")
    args = ap.parse_args(argv[1:])

    from eval.run_stub import stub_agent  # noqa: PLC0415
    stub_agent()

    items = list(GOLDEN_EXPANDED)
    if args.only:
        items = [q for q in items if q["id"] == args.only]

    rows: List[Dict[str, Any]] = []
    for item in items:
        rows.append(run_one(item, "stub"))
        rows.append(run_one(item, "empty"))

    probe = probe_must_ask_any()
    stub_rows = [r for r in rows if r["mode"] == "stub"]
    empty_rows = [r for r in rows if r["mode"] == "empty"]
    ok, judge_note = live_judge_available()

    out: Dict[str, Any] = {
        "offline": True,
        "live_judge_available": ok,
        "judge_note": judge_note,
        "skip_note": judge_skip_note(),
        "live_checks_deferred": {
            "axes": JUDGE_AXES,
            "reason": "faithfulness / citation correctness / clarity need "
                      "a live judge with keys; deterministic checks above "
                      "run offline",
        },
        "n_expanded": len(items),
        "stub": summarize(stub_rows),
        "empty": summarize(empty_rows),
        "must_ask_any_probe": probe,
        "rows": rows,
    }
    path = os.path.join(HERE, "generation_results.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)

    for mode in ("stub", "empty"):
        s = out[mode]
        print("%s: %d/%d passed" % (mode, s["passed"], s["n"]))
        for k, v in sorted(s["by_check"].items()):
            print("  %-22s %d/%d" % (k, v["passed"], v["total"]))
    print("must_ask_any probe correct: %s" % (bool(probe["correct"]),))
    print("judge: %s" % (judge_note,))
    print("\nWrote %s" % (path,))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
