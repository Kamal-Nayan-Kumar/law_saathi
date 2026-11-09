#!/usr/bin/env python3
"""Live generation eval (Phase E2).

Sample of 15 questions from GOLDEN_QAS + GOLDEN_EXPANDED covering in-scope EN,
Hindi, Kannada, Hinglish, out-of-scope, and the clarify case. Calls
app.agent.run_agent directly in-process with a Qdrant retriever (no API
server), scores deterministically with api/eval/run_golden.check, then runs
the blind LLM judge from report/evals/judge_prompts.py over the same answers.

Budgets (deliberately disciplined):
- at most 15 run_agent calls, 1s delay between calls
- on 429/rate/quota wait 60s, retry once; provider fallback is the agent's
  own Groq -> OpenRouter -> OpenCode chain (chat_complete)
- judge calls capped at 15 total: one combined call per question scoring all
  five axes (faithfulness, citation_correctness, clarity, language_match,
  refusal_correctness), so 15 questions -> 15 judge calls, not 75. Each
  axis rubric text is taken from judge_prompts.JUDGE_PROMPTS.
- blind judge: the judge prompt never sees the deterministic verdict,
  confidence, or verified flag. Only question/answer/citations/evidence and
  the scope note (expectation) are passed.

Outputs: report/evals/live_generation_results.json
Keys: loaded from api/.env via load_env; values are never printed.
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
API = os.path.join(ROOT, "api")
sys.path.insert(0, API)
sys.path.insert(0, os.path.join(ROOT, "report", "dataset"))
sys.path.insert(0, HERE)

# Respect MAX_LLM_CALLS=6 per run and MAX_RETRIES=1 before importing agent
# (agent reads these env vars at import time).
os.environ.setdefault("LAWSAATHI_MAX_LLM_CALLS", "6")
os.environ.setdefault("LAWSAATHI_MAX_RETRIES", "1")

MAX_RUN_AGENT_CALLS = 15
MAX_JUDGE_CALLS = 15
DELAY_SECS = 1.0
RETRY_WAIT_SECS = float(os.environ.get("LAWSAATHI_LIVE_RETRY_WAIT_SECS", "60"))

# 15-question sample: 6 from GOLDEN_QAS, 9 from GOLDEN_EXPANDED.
# coverage: in-scope EN (incl. expanded depth), Hindi, Kannada, Hinglish,
# out-of-scope, clarify (must_ask_any).
SAMPLE_IDS = [
    "maintenance-arrears-en",           # QAS, en, maintenance
    "dv-first-report-en",               # QAS, en, PWDV (must-not-divorce)
    "maintenance-arrears-hi",           # QAS, hi
    "maintenance-kn",                   # QAS, kn
    "oos-rti-en",                       # QAS, out-of-scope
    "clarify-personal-law-en",          # QAS, must_ask_any (clarify)
    "interim-maintenance-en",           # EXP, en
    "pwdv-residence-vs-ownership-en",   # EXP, en
    "succession-class1-en",             # EXP, en
    "pwdv-monetary-hinglish",           # EXP, hinglish
    "maintenance-arrears-escalation-hi",  # EXP, hi
    "custody-welfare-kn",               # EXP, kn
    "adoption-unmarried-hinglish",      # EXP, hinglish
    "oos-landlord-deposit-en",          # EXP, out-of-scope variant
    "special-marriage-notice-en",       # EXP, en
]


def load_env():
    env = os.path.join(API, ".env")
    if not os.path.exists(env):
        return
    for line in open(env):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def is_rate_limit(err):
    s = str(err).lower()
    return "429" in s or "rate" in s or "quota" in s


def evidence_to_text(evidence, max_hits=6, hit_chars=500):
    parts = []
    for h in (evidence or [])[:max_hits]:
        payload = h.get("payload") or {}
        text = str(payload.get("text") or h.get("text") or "")[:hit_chars]
        act = str(payload.get("act") or "")
        sec = str(payload.get("section") or "")
        label = ("[%s | Section %s]" % (act, sec)).strip() if act or sec else "[passage]"
        parts.append("%s %s" % (label, text))
    return "\n\n".join(parts) if parts else "(no passage available to the judge)"


def scope_expectation(item):
    if item.get("must_redirect"):
        return "out of family-law scope; a redirect without advice on the wrong topic is expected"
    if item.get("must_ask_any"):
        return "in scope, but a clarification question about which personal law applies is expected before answering"
    return item.get("note", "in scope; a substantive family-law answer is expected")


def build_combined_judge_prompt(judge_prompts, question, answer, citations,
                                evidence, expectation):
    """One blind prompt covering all five judge_prompts axes."""
    jp = judge_prompts.JUDGE_PROMPTS
    # Pull rubric wording verbatim from judge_prompts so this eval judges by
    # the same definitions as the offline grader, without copying them here.
    axes = judge_prompts.JUDGE_AXES
    rubric_lines = []
    for ax in axes:
        # Use only the definition sentence (truncate the template tail that
        # repeats the JSON shape; the combined output schema is stated below).
        tpl = jp[ax]
        m = re.search(r"Rate [A-Z ]+:(.*?)\n", tpl, re.S)
        definition = (m.group(1).strip() if m else tpl.strip())
        definition = " ".join(definition.split())[:400]
        rubric_lines.append("- %s: %s" % (ax, definition))
    user = (
        "You are an evaluation judge for Indian family-law answers. "
        "You have NOT seen any automatic verdict, confidence score, or "
        "system flag. Judge only the evidence in front of you.\n\n"
        "Question:\n%s\n\n"
        "Answer:\n%s\n\n"
        "Citations:\n%s\n\n"
        "Cited passages:\n%s\n\n"
        "System expectation (scope note, not a verdict):\n%s\n\n"
        "Score each axis 1-5 (1=worst, 5=best) by these definitions:\n%s\n\n"
        "Output ONLY JSON with this shape and nothing else:\n"
        '{"faithfulness": {"score": 1-5, "reason": "one sentence"}, '
        '"citation_correctness": {"score": 1-5, "reason": "one sentence"}, '
        '"clarity": {"score": 1-5, "reason": "one sentence"}, '
        '"language_match": {"score": 1-5, "reason": "one sentence"}, '
        '"refusal_correctness": {"score": 1-5, "reason": "one sentence"}}'
    ) % (question, answer, citations, evidence, expectation, "\n".join(rubric_lines))
    return [{"role": "system", "content": "Judge only the evidence given."},
            {"role": "user", "content": user}]


def parse_judge_json(text):
    """Extract the first JSON object; return dict or None."""
    if not text:
        return None
    t = text.strip()
    # Strip code fences if present.
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t, flags=re.I | re.S).strip()
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except Exception:
        pass
    m = re.search(r"\{.*\}", t, re.S)
    if m:
        try:
            obj = json.loads(m.group(0))
            return obj if isinstance(obj, dict) else None
        except Exception:
            return None
    return None


def judge_scores(judge_prompts, question, answer, citations, evidence,
                 expectation, counter):
    """One combined judge call. Returns (scores_dict, judge_provider, error, latency_ms)."""
    if counter["judge_calls"] >= MAX_JUDGE_CALLS:
        return (None, "", "judge budget exhausted (%d)" % MAX_JUDGE_CALLS, 0)
    from app.agent import chat_complete  # noqa: PLC0415

    messages = build_combined_judge_prompt(
        judge_prompts, question, answer, citations, evidence, expectation)
    t0 = time.time()
    try:
        counter["judge_calls"] += 1
        raw, provider = chat_complete(messages, max_tokens=800)
    except Exception as e:  # noqa: BLE001 -- retry once after a 429 wait
        if is_rate_limit(e) and counter["judge_calls"] < MAX_JUDGE_CALLS:
            counter["rate_limit_hits"] += 1
            time.sleep(RETRY_WAIT_SECS)
            counter["waited_secs"] += RETRY_WAIT_SECS
            try:
                counter["judge_calls"] += 1
                raw, provider = chat_complete(messages, max_tokens=800)
            except Exception as e2:  # noqa: BLE001
                latency = int((time.time() - t0) * 1000)
                return (None, "", "%s: %s" % (type(e2).__name__, str(e2)[:200]), latency)
        else:
            latency = int((time.time() - t0) * 1000)
            if is_rate_limit(e):
                counter["rate_limit_hits"] += 1
            return (None, "", "%s: %s" % (type(e).__name__, str(e)[:200]), latency)
    latency = int((time.time() - t0) * 1000)
    obj = parse_judge_json(raw)
    if obj is None:
        return (None, str(provider or ""), "judge reply unparseable: %r" % str(raw)[:200], latency)
    scores = {}
    for ax in judge_prompts.JUDGE_AXES:
        entry = obj.get(ax)
        if isinstance(entry, dict):
            try:
                score = int(entry.get("score"))
            except Exception:
                score = None
            scores[ax] = {"score": score, "reason": str(entry.get("reason") or "")[:300]}
        elif isinstance(entry, (int, float)):
            scores[ax] = {"score": int(entry), "reason": ""}
        else:
            scores[ax] = {"score": None, "reason": "missing in judge reply"}
    return (scores, str(provider or ""), "", latency)


def run_agent_with_retry(run_agent, retriever, query, lang, counter):
    """One live run_agent call with 429 wait + single retry. Returns (state, error)."""
    if counter["run_agent_calls"] >= MAX_RUN_AGENT_CALLS:
        return (None, "run_agent budget exhausted (%d)" % MAX_RUN_AGENT_CALLS)
    counter["run_agent_calls"] += 1
    try:
        state = run_agent(query, lang=lang, retriever=retriever)
        return (state, "")
    except Exception as e:  # noqa: BLE001
        if is_rate_limit(e) and counter["run_agent_calls"] < MAX_RUN_AGENT_CALLS:
            counter["rate_limit_hits"] += 1
            time.sleep(RETRY_WAIT_SECS)
            counter["waited_secs"] += RETRY_WAIT_SECS
            counter["run_agent_calls"] += 1
            try:
                state = run_agent(query, lang=lang, retriever=retriever)
                return (state, "")
            except Exception as e2:  # noqa: BLE001
                return (None, "%s: %s" % (type(e2).__name__, str(e2)[:200]))
        if is_rate_limit(e):
            counter["rate_limit_hits"] += 1
        return (None, "%s: %s" % (type(e).__name__, str(e)[:200]))


def main():
    load_env()
    from app.agent import run_agent  # noqa: PLC0415
    from eval.golden_qas import GOLDEN_QAS  # noqa: PLC0415
    from eval.run_golden import check  # noqa: PLC0415
    from golden_expanded import GOLDEN_EXPANDED  # noqa: PLC0415
    import judge_prompts  # noqa: PLC0415
    judge_prompts.__dict__  # keep linter quiet

    by_id = {}
    for item in list(GOLDEN_QAS) + list(GOLDEN_EXPANDED):
        by_id[item["id"]] = item
    items = []
    missing = []
    for qid in SAMPLE_IDS:
        if qid in by_id:
            items.append(by_id[qid])
        else:
            missing.append(qid)
    if missing:
        print("WARNING missing sample ids: %r" % missing)

    # Retriever: same Qdrant store the smoke eval uses.
    retriever = None
    retriever_error = ""
    try:
        from app.ingest import QdrantStore  # noqa: PLC0415
        retriever = QdrantStore.connect()
    except Exception as e:  # noqa: BLE001
        retriever_error = "%s: %s" % (type(e).__name__, str(e)[:200])

    counter = {"run_agent_calls": 0, "judge_calls": 0,
               "rate_limit_hits": 0, "waited_secs": 0.0}

    results = []
    for item in items:
        qid = item["id"]
        query = item["query"]
        lang = item.get("lang", "en")
        if lang == "hinglish":
            lang = "hi"  # detect_lang maps Roman Hindi to hi anyway
        state = None
        err = ""
        t0 = time.time()
        if retriever is None:
            err = "no Qdrant retriever; %s" % (retriever_error or "unavailable")
            state = None
        else:
            state, err = run_agent_with_retry(run_agent, retriever, query, lang, counter)
        latency_ms = int((time.time() - t0) * 1000)

        if state is None:
            results.append({
                "id": qid, "lang": item.get("lang"), "query": query,
                "deterministic_pass": False,
                "problems": ["run_agent failed: %s" % err],
                "judge_scores": None, "judge_provider": "",
                "judge_latency_ms": 0, "judge_error": "run_agent failed; judge skipped",
                "provider": "", "latency_ms": latency_ms,
                "citation_count": 0, "verified": False,
                "confidence": 0.0, "answer_chars": 0,
                "error": err,
            })
            print("ERROR %-34s %s" % (qid, err))
        else:
            problems = check(item, state)
            answer = str(state.get("answer") or "")
            citations = list(state.get("citations") or [])
            citations_text = "\n".join(citations) if citations else "(none cited)"
            evidence_text = evidence_to_text(state.get("evidence"))
            expectation = scope_expectation(item)
            scores, judge_provider, judge_error, judge_latency = judge_scores(
                judge_prompts, query, answer, citations_text,
                evidence_text, expectation, counter)
            results.append({
                "id": qid, "lang": item.get("lang"), "query": query,
                "deterministic_pass": not problems,
                "problems": problems,
                "judge_scores": scores, "judge_provider": judge_provider,
                "judge_latency_ms": judge_latency, "judge_error": judge_error,
                "provider": str(state.get("provider") or ""),
                "latency_ms": latency_ms,
                "citation_count": len(citations),
                "verified": bool(state.get("verified", False)),
                "confidence": float(state.get("confidence") or 0.0),
                "answer_chars": len(answer),
                "oos_redirect": bool(state.get("oos_redirect", False)),
                "clarification": bool(state.get("clarification")),
                "error": "",
            })
            print("%s %-34s provider=%s verified=%s citations=%d latency_ms=%d "
                  "judge_provider=%s" % ("PASS" if not problems else "FAIL",
                                         qid, state.get("provider") or "-",
                                         bool(state.get("verified", False)),
                                         len(citations), latency_ms,
                                         judge_provider or "-"))
            for p in problems:
                print("        - %s" % p)
            if judge_error:
                print("        judge_error: %s" % judge_error)
        time.sleep(DELAY_SECS)

    passed = sum(1 for r in results if r["deterministic_pass"])
    judge_ok = sum(1 for r in results if r.get("judge_scores"))
    # Mean judge score per axis over questions that were judged.
    axes_mean = {}
    for ax in judge_prompts.JUDGE_AXES:
        vals = []
        for r in results:
            js = r.get("judge_scores") or {}
            entry = js.get(ax) or {}
            if isinstance(entry.get("score"), int) and 1 <= entry["score"] <= 5:
                vals.append(entry["score"])
        axes_mean[ax] = round(sum(vals) / len(vals), 2) if vals else None
    out = {
        "sample_ids": SAMPLE_IDS,
        "n": len(results),
        "deterministic_passed": passed,
        "deterministic_pass_rate": round(passed / len(results), 4) if results else 0.0,
        "judge_scored": judge_ok,
        "judge_mean_scores": axes_mean,
        "run_agent_calls": counter["run_agent_calls"],
        "run_agent_call_cap": MAX_RUN_AGENT_CALLS,
        "judge_calls": counter["judge_calls"],
        "judge_call_cap": MAX_JUDGE_CALLS,
        "judge_axes": judge_prompts.JUDGE_AXES,
        "rate_limit_hits": counter["rate_limit_hits"],
        "waited_secs": counter["waited_secs"],
        "retriever_error": retriever_error,
        "results": results,
    }
    path = os.path.join(HERE, "live_generation_results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print("\nLive generation: n=%d deterministic_pass=%d (%.3f) judge_scored=%d/%d "
          "run_agent_calls=%d/%d judge_calls=%d/%d rate_hits=%d waited=%ss"
          % (len(results), passed, out["deterministic_pass_rate"], judge_ok, len(results),
             counter["run_agent_calls"], MAX_RUN_AGENT_CALLS,
             counter["judge_calls"], MAX_JUDGE_CALLS,
             counter["rate_limit_hits"], counter["waited_secs"]))
    for ax in judge_prompts.JUDGE_AXES:
        print("  judge %-22s mean=%s" % (ax, axes_mean[ax]))
    print("Wrote %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
