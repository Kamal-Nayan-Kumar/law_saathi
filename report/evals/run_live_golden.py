#!/usr/bin/env python3
"""Live golden eval (Phase E2): GOLDEN_QAS end-to-end via run_agent.

Runs all 23 GOLDEN_QAS questions live through app.agent.run_agent (in-process,
no API server) with a Qdrant retriever, scores with
api/eval/run_golden.check, and saves the professor-facing number to
report/evals/live_golden_results.json.

Quota discipline:
- 1s delay between calls; on 429/rate/quota wait 60s, retry once; provider
  fallback is the agent's Groq -> OpenRouter -> OpenCode chain.
- If quota gets tight (waited_secs >= 120 or >= 3 rate-limit hits) before
  finishing, stop after 15 questions, mark partial and record why.

Keys: loaded from api/.env via load_env; values are never printed.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
API = os.path.join(ROOT, "api")
sys.path.insert(0, API)
sys.path.insert(0, os.path.join(ROOT, "report", "dataset"))
sys.path.insert(0, HERE)

os.environ.setdefault("LAWSAATHI_MAX_LLM_CALLS", "6")
os.environ.setdefault("LAWSAATHI_MAX_RETRIES", "1")

DELAY_SECS = 1.0
RETRY_WAIT_SECS = float(os.environ.get("LAWSAATHI_LIVE_RETRY_WAIT_SECS", "60"))
PARTIAL_AFTER = 15
WAITED_PARTIAL_THRESHOLD = 120.0
RATE_HITS_PARTIAL_THRESHOLD = 3


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


def main():
    load_env()
    from app.agent import run_agent  # noqa: PLC0415
    from eval.golden_qas import GOLDEN_QAS  # noqa: PLC0415
    from eval.run_golden import check  # noqa: PLC0415

    retriever = None
    retriever_error = ""
    try:
        from app.ingest import QdrantStore  # noqa: PLC0415
        retriever = QdrantStore.connect()
    except Exception as e:  # noqa: BLE001
        retriever_error = "%s: %s" % (type(e).__name__, str(e)[:200])

    counter = {"run_agent_calls": 0, "rate_limit_hits": 0, "waited_secs": 0.0}
    results = []
    partial = False
    partial_reason = ""

    for idx, item in enumerate(GOLDEN_QAS):
        if idx >= PARTIAL_AFTER and (counter["waited_secs"] >= WAITED_PARTIAL_THRESHOLD
                                     or counter["rate_limit_hits"] >= RATE_HITS_PARTIAL_THRESHOLD):
            partial = True
            partial_reason = ("quota tight after %d questions: waited_secs=%.0f "
                              "rate_limit_hits=%d" % (len(results),
                                                      counter["waited_secs"],
                                                      counter["rate_limit_hits"]))
            break
        qid = item["id"]
        query = item["query"]
        lang = item.get("lang", "en")
        if lang == "hinglish":
            lang = "hi"
        state = None
        err = ""
        t0 = time.time()
        if retriever is None:
            err = "no Qdrant retriever; %s" % (retriever_error or "unavailable")
        else:
            counter["run_agent_calls"] += 1
            try:
                state = run_agent(query, lang=lang, retriever=retriever)
            except Exception as e:  # noqa: BLE001 -- retry once after a 429 wait
                if is_rate_limit(e):
                    counter["rate_limit_hits"] += 1
                    time.sleep(RETRY_WAIT_SECS)
                    counter["waited_secs"] += RETRY_WAIT_SECS
                    counter["run_agent_calls"] += 1
                    try:
                        state = run_agent(query, lang=lang, retriever=retriever)
                    except Exception as e2:  # noqa: BLE001
                        err = "%s: %s" % (type(e2).__name__, str(e2)[:200])
                else:
                    err = "%s: %s" % (type(e).__name__, str(e)[:200])
        latency_ms = int((time.time() - t0) * 1000)

        if state is None:
            results.append({
                "id": qid, "lang": item.get("lang"), "query": query,
                "deterministic_pass": False,
                "problems": ["run_agent failed: %s" % err],
                "provider": "", "latency_ms": latency_ms,
                "citation_count": 0, "citations": [],
                "verified": False, "confidence": 0.0,
                "answer_chars": 0, "error": err,
                "oos_redirect": False, "clarification": False,
            })
            print("ERROR %-30s %s" % (qid, err))
        else:
            problems = check(item, state)
            citations = list(state.get("citations") or [])
            results.append({
                "id": qid, "lang": item.get("lang"), "query": query,
                "deterministic_pass": not problems,
                "problems": problems,
                "provider": str(state.get("provider") or ""),
                "latency_ms": latency_ms,
                "citation_count": len(citations),
                "citations": citations,
                "verified": bool(state.get("verified", False)),
                "confidence": float(state.get("confidence") or 0.0),
                "answer_chars": len(str(state.get("answer") or "")),
                "oos_redirect": bool(state.get("oos_redirect", False)),
                "clarification": bool(state.get("clarification")),
                "error": "",
            })
            print("%s %-30s provider=%s verified=%s citations=%d latency_ms=%d"
                  % ("PASS" if not problems else "FAIL", qid,
                     state.get("provider") or "-", bool(state.get("verified", False)),
                     len(citations), latency_ms))
            for p in problems:
                print("        - %s" % p)
        time.sleep(DELAY_SECS)

    # Natural completion case: if quota pressure appeared only at the end,
    # partial stays False; if we stopped early it is True.
    if not partial and len(results) < len(GOLDEN_QAS):
        partial = True
        partial_reason = partial_reason or (
            "stopped early at %d/%d questions" % (len(results), len(GOLDEN_QAS)))

    passed = sum(1 for r in results if r["deterministic_pass"])
    by_lang = {}
    for r in results:
        bucket = by_lang.setdefault(r["lang"], {"n": 0, "passed": 0})
        bucket["n"] += 1
        bucket["passed"] += int(bool(r["deterministic_pass"]))
    out = {
        "n": len(results),
        "intended_n": len(GOLDEN_QAS),
        "passed": passed,
        "pass_rate": round(passed / len(results), 4) if results else 0.0,
        "partial": partial,
        "partial_reason": partial_reason,
        "by_lang": by_lang,
        "run_agent_calls": counter["run_agent_calls"],
        "rate_limit_hits": counter["rate_limit_hits"],
        "waited_secs": counter["waited_secs"],
        "retriever_error": retriever_error,
        "results": results,
    }
    path = os.path.join(HERE, "live_golden_results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print("\nLive golden: n=%d (intended %d) passed=%d pass_rate=%.3f partial=%s "
          "run_agent_calls=%d rate_hits=%d waited=%ss"
          % (len(results), len(GOLDEN_QAS), passed, out["pass_rate"], partial,
             counter["run_agent_calls"], counter["rate_limit_hits"],
             counter["waited_secs"]))
    for lg in sorted(by_lang):
        b = by_lang[lg]
        print("  %-10s %d/%d" % (lg, b["passed"], b["n"]))
    if partial_reason:
        print("partial_reason: %s" % partial_reason)
    print("Wrote %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
