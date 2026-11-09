#!/usr/bin/env python3
"""Live verifier eval (Phase E1).

For each VERIFIER_MUTATIONS pair (20), calls the real verifier path
(agent.verify_grounding, the judge that node_verifier delegates to) with
the grounded draft and the mutated draft against the same evidence block.
Evidence is fabricated from the grounded draft, exactly as the offline
run_verifier.py does: one evidence hit whose passage is the grounded
sentence. The two drafts therefore differ by precisely the mutated fact.

Budgets: MAX_LLM_CALLS=6 and MAX_RETRIES=1 per agent run are respected
by using the app's own chat_complete chain (Groq models -> OpenRouter
models -> OpenCode Zen, which already retries across providers on
429/rate limits). On top of that, a shared counter caps total live
verifier LLM calls at 40, a 1s delay separates calls, and a 429/rate
error waits 60s and retries once.

Outputs: report/evals/live_verifier_results.json
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "api"))
sys.path.insert(0, os.path.join(ROOT, "report", "dataset"))

MAX_TOTAL_LLM_CALLS = 40
RETRY_WAIT_SECS = float(os.environ.get("LAWSAATHI_LIVE_RETRY_WAIT_SECS", "60"))
DELAY_SECS = 1.0


def load_env():
    env = os.path.join(ROOT, "api", ".env")
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
    from app.agent import new_state, verify_grounding, budgeted_llm, chat_complete
    from golden_expanded import VERIFIER_MUTATIONS

    counter = {"calls": 0, "rate_limit_hits": 0, "waited_secs": 0.0}
    last_provider = {"name": ""}

    def live_llm(messages):
        """chat_complete behind the shared budget + 429 handling."""
        if counter["calls"] >= MAX_TOTAL_LLM_CALLS:
            raise RuntimeError("live verifier LLM call budget exhausted (%d)" % MAX_TOTAL_LLM_CALLS)
        counter["calls"] += 1
        try:
            text, provider = chat_complete(messages)
        except Exception as e:  # noqa: BLE001 — retry once after a 429 wait
            if is_rate_limit(e) and counter["calls"] < MAX_TOTAL_LLM_CALLS:
                counter["rate_limit_hits"] += 1
                time.sleep(RETRY_WAIT_SECS)
                counter["waited_secs"] += RETRY_WAIT_SECS
                counter["calls"] += 1
                text, provider = chat_complete(messages)
            else:
                raise
        last_provider["name"] = str(provider or "")
        return text, provider

    # Respect MAX_LLM_CALLS=6 per run: this wrapper is re-created per
    # mutation, but the live_llm above enforces the overall 40-call cap.
    bounded = lambda: budgeted_llm(live_llm, max_calls=6)

    def judge(draft, passage, topic):
        """One verify_grounding call. Returns (verdict, provider, error, latency_ms)."""
        state = new_state(topic, lang="en")
        state["draft"] = draft
        state["evidence"] = [{"score": 0.9, "payload": {"text": passage, "act": "",
                                                         "section": "", "kind": "bare_act"}}]
        state["query_en"] = topic
        t0 = time.time()
        try:
            out = verify_grounding(state, llm=bounded())
            latency = int((time.time() - t0) * 1000)
            if out is None:
                return (None, str(state.get("provider") or ""), "judge returned no verdict (model failure or unparseable reply)", latency)
            return (str(out.get("verdict") or ""), str(state.get("provider") or ""), "", latency)
        except Exception as e:  # noqa: BLE001 — the failure is the finding
            latency = int((time.time() - t0) * 1000)
            if is_rate_limit(e):
                counter["rate_limit_hits"] += 1
            return (None, str(state.get("provider") or ""), "%s: %s" % (type(e).__name__, str(e)[:200]), latency)

    rows = []
    grounded_ok = 0
    mutated_caught = 0
    judge_errors = 0
    n = len(VERIFIER_MUTATIONS)
    tried_each = n
    for mut in VERIFIER_MUTATIONS:
        if counter["calls"] >= MAX_TOTAL_LLM_CALLS:
            tried_each = len(rows)
            break
        passage = mut["grounded_draft"]
        topic = mut["topic"]
        gv, gp, gerr, glat = judge(mut["grounded_draft"], passage, topic)
        time.sleep(DELAY_SECS)
        mv, mp, merr, mlat = judge(mut["mutated_draft"], passage, topic)
        time.sleep(DELAY_SECS)
        g_ok = (gv == "grounded")
        m_caught = (mv == "insufficient")
        if gv is None or mv is None:
            judge_errors += 1
        if g_ok:
            grounded_ok += 1
        if m_caught:
            mutated_caught += 1
        rows.append({
            "id": mut["id"], "topic": topic, "mutation_type": mut["mutation_type"],
            "grounded_verdict": gv, "mutated_verdict": mv,
            "provider_grounded": gp, "provider_mutated": mp,
            "latency_grounded_ms": glat, "latency_mutated_ms": mlat,
            "grounded_ok": g_ok, "mutated_caught": m_caught,
            "grounded_error": gerr, "mutated_error": merr,
            "pass": bool(g_ok and m_caught),
        })

    total = len(rows)
    out = {
        "n": total, "intended_n": n, "tried_n": tried_each,
        "grounded_passed": grounded_ok,
        "mutated_caught": mutated_caught,
        "catch_rate": round(mutated_caught / total, 4) if total else 0.0,
        "grounded_pass_rate": round(grounded_ok / total, 4) if total else 0.0,
        "false_pass_rate": round(1.0 - (mutated_caught / total), 4) if total else 0.0,
        "false_fail_rate": round(1.0 - (grounded_ok / total), 4) if total else 0.0,
        "judge_error_rows": judge_errors,
        "llm_calls_used": counter["calls"],
        "llm_call_cap": MAX_TOTAL_LLM_CALLS,
        "rate_limit_hits": counter["rate_limit_hits"],
        "waited_secs": counter["waited_secs"],
        "rows": rows,
    }
    path = os.path.join(HERE, "live_verifier_results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print("Live verifier: n=%d grounded_pass=%d caught=%d catch_rate=%.3f false_pass=%.3f false_fail=%.3f judge_errors=%d llm_calls=%d/%d rate_hits=%d"
          % (total, grounded_ok, mutated_caught, out["catch_rate"], out["false_pass_rate"],
             out["false_fail_rate"], judge_errors, counter["calls"], MAX_TOTAL_LLM_CALLS,
             counter["rate_limit_hits"]))
    for r in rows:
        print("  %-8s %-32s %-14s grounded=%-12s mutated=%-12s provider=%s %s"
              % (r["id"], r["topic"][:32], r["mutation_type"],
                 r["grounded_verdict"] or "ERROR", r["mutated_verdict"] or "ERROR",
                 r["provider_grounded"] or r["provider_mutated"] or "-",
                 "PASS" if r["pass"] else "FAIL"))
    print("Wrote %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
