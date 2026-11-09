#!/usr/bin/env python3
"""Live retrieval + live smoke eval (Phase E1).

Loads api/.env (never prints values), connects to Qdrant if possible,
runs 8 RETRIEVAL_EXPECTED queries through QdrantStore.search_text
(server-side embedding with intfloat/multilingual-e5-small), and checks
whether the expected act/section appears in the top-3. Then runs 3 live
end-to-end run_agent calls (maintenance, domestic violence, succession)
through the real Groq -> OpenRouter -> OpenCode Zen chain in
agent.chat_complete.

Outputs:
  report/evals/live_retrieval_results.json
  report/evals/live_smoke_results.json

If Qdrant is unreachable, live_retrieval is recorded as blocked with a
reason; the script still writes both JSON files and exits 0.
"""
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "api"))
sys.path.insert(0, os.path.join(ROOT, "report", "dataset"))

# 8 queries spread across acts: HMA divorce, HMA maintenance, PWDV
# residence, PWDV monetary, HAMA wife, HSA class I, HSA stridhan,
# Special Marriage notice.
RETRIEVAL_IDS = ["re-01", "re-05", "re-08", "re-09", "re-11", "re-14", "re-15", "re-17"]

# One maintenance, one domestic-violence, one succession end-to-end smoke.
SMOKE_QUERIES = [
    {"id": "smoke-maintenance", "query": "my husband has not given maintenance for 4 months what can i do"},
    {"id": "smoke-dv", "query": "my husband hits me. i am scared to tell anyone. what are my options"},
    {"id": "smoke-succession", "query": "if a hindu man dies without a will, who gets his property, daughters or son only"},
]

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


def section_token(section):
    """Extract the section number token from a label like 'Section 13B: ...'."""
    m = re.match(r"\s*section\s+([0-9]+[a-z]*)", (section or ""), re.I)
    return m.group(1).lower() if m else (section or "").strip().lower()


def act_matches(got, want):
    """Loose act match: strip punctuation/case, then prefix-compare."""
    g = re.sub(r"[^a-z0-9]", "", (got or "").lower())
    w = re.sub(r"[^a-z0-9]", "", (want or "").lower())
    if not g or not w:
        return False
    return g.startswith(w) or w.startswith(g)


def is_rate_limit(err):
    s = str(err).lower()
    return "429" in s or "rate" in s or "quota" in s


def main():
    load_env()
    from golden_expanded import RETRIEVAL_EXPECTED

    def want_entry(qid):
        for e in RETRIEVAL_EXPECTED:
            if e["id"] == qid:
                return e
        return None

    # --- Live retrieval -------------------------------------------------
    retrieval = {"blocked": True, "blocked_reason": "", "embedding_provider": "qdrant-cloud-inference",
                 "embedding_model": "intfloat/multilingual-e5-small", "results": [],
                 "n": 0, "passed": 0, "pass_rate": 0.0, "rate_limit_hits": 0}
    store = None
    blocked_reason = ""
    try:
        from app.ingest import QdrantStore
        store = QdrantStore.connect()
        retrieval["embedding_model"] = str(getattr(store, "model", retrieval["embedding_model"]))
        retrieval["collection"] = str(getattr(store, "collection", ""))
        try:
            n_points = store.count()
            retrieval["collection_points"] = n_points
            if n_points == 0:
                retrieval["collection_empty_note"] = "collection exists but has 0 points"
        except Exception as e:  # noqa: BLE001
            # Collection missing or count failed: record, do not crash.
            blocked_reason = "store.count failed: %s" % type(e).__name__
    except Exception as e:  # noqa: BLE001
        blocked_reason = "Qdrant unreachable or misconfigured: %s" % type(e).__name__

    if store is not None and not blocked_reason:
        retrieval["blocked"] = False
        for qid in RETRIEVAL_IDS:
            entry = want_entry(qid)
            if entry is None:
                continue
            query = entry["query"]
            hits_out = []
            passed = False
            err = ""
            t0 = time.time()
            try:
                hits = store.search_text(query, top_k=3)
                for h in hits:
                    payload = h.get("payload") or {}
                    act = str(payload.get("act") or "")
                    sec = str(payload.get("section") or "")
                    hits_out.append({"act": act, "section": sec,
                                     "score": float(h.get("score", 0.0) or 0.0)})
                    if act_matches(act, entry["expected_act"]):
                        if section_token(sec) == str(entry["expected_section"]).lower():
                            passed = True
            except Exception as e:  # noqa: BLE001 — the error is the finding
                err = "%s: %s" % (type(e).__name__, str(e)[:200])
                if is_rate_limit(e):
                    retrieval["rate_limit_hits"] += 1
            latency_ms = int((time.time() - t0) * 1000)
            retrieval["results"].append({
                "id": qid, "query": query,
                "expected_act": entry["expected_act"],
                "expected_section": entry["expected_section"],
                "top_hits": hits_out, "pass": passed,
                "error": err, "latency_ms": latency_ms,
            })
            time.sleep(DELAY_SECS)
        retrieval["n"] = len(retrieval["results"])
        retrieval["passed"] = sum(1 for r in retrieval["results"] if r["pass"])
        retrieval["pass_rate"] = round(retrieval["passed"] / retrieval["n"], 4) if retrieval["n"] else 0.0
    else:
        retrieval["blocked_reason"] = blocked_reason or "Qdrant unavailable"

    path_ret = os.path.join(HERE, "live_retrieval_results.json")
    with open(path_ret, "w", encoding="utf-8") as f:
        json.dump(retrieval, f, indent=2, ensure_ascii=False)

    # --- Live smoke (3 run_agent calls) --------------------------------
    smoke = {"n": 0, "checked": 0, "results": [], "rate_limit_hits": 0}
    if store is None:
        smoke["blocked_reason"] = "no Qdrant store; run_agent needs retrieval"
    else:
        from app.agent import run_agent
        for item in SMOKE_QUERIES:
            qid = item["id"]
            query = item["query"]
            t0 = time.time()
            row = {"id": qid, "query": query, "latency_ms": 0, "provider": "",
                   "verified": False, "citations": [], "trace_nodes": [],
                   "answer_chars": 0, "error": ""}
            try:
                state = run_agent(query, lang="en", retriever=store)
                row["provider"] = str(state.get("provider") or "")
                row["verified"] = bool(state.get("verified", False))
                row["citations"] = list(state.get("citations") or [])
                row["trace_nodes"] = [t.get("node") for t in (state.get("trace") or []) if isinstance(t, dict)]
                row["answer_chars"] = len(state.get("answer") or "")
                row["confidence"] = float(state.get("confidence") or 0.0)
            except Exception as e:  # noqa: BLE001
                if is_rate_limit(e):
                    smoke["rate_limit_hits"] += 1
                    try:
                        time.sleep(RETRY_WAIT_SECS)
                        state = run_agent(query, lang="en", retriever=store)
                        row["provider"] = str(state.get("provider") or "")
                        row["verified"] = bool(state.get("verified", False))
                        row["citations"] = list(state.get("citations") or [])
                        row["trace_nodes"] = [t.get("node") for t in (state.get("trace") or []) if isinstance(t, dict)]
                        row["answer_chars"] = len(state.get("answer") or "")
                        row["confidence"] = float(state.get("confidence") or 0.0)
                        row["retried_after_rate_limit"] = True
                    except Exception as e2:  # noqa: BLE001
                        row["error"] = "%s: %s" % (type(e2).__name__, str(e2)[:200])
                else:
                    row["error"] = "%s: %s" % (type(e).__name__, str(e)[:200])
            row["latency_ms"] = int((time.time() - t0) * 1000)
            smoke["results"].append(row)
            smoke["n"] += 1
            if not row["error"]:
                smoke["checked"] += 1
            time.sleep(DELAY_SECS)

    path_smoke = os.path.join(HERE, "live_smoke_results.json")
    with open(path_smoke, "w", encoding="utf-8") as f:
        json.dump(smoke, f, indent=2, ensure_ascii=False)

    print("Live retrieval: n=%d passed=%d pass_rate=%.3f blocked=%s %s"
          % (retrieval["n"], retrieval["passed"], retrieval["pass_rate"],
             retrieval["blocked"], retrieval.get("blocked_reason", "")))
    for r in retrieval["results"]:
        print("  %-8s %s top1=%s" % (r["id"], "PASS" if r["pass"] else "FAIL",
              (r["top_hits"][0]["section"] + " | " + r["top_hits"][0]["act"][:40]) if r["top_hits"] else "no hits"))
        if r["error"]:
            print("           error: %s" % r["error"])
    print("Live smoke: n=%d ok=%d rate_limit_hits=%d" % (smoke["n"], smoke["checked"], smoke["rate_limit_hits"]))
    for r in smoke["results"]:
        print("  %-18s %s provider=%s verified=%s latency_ms=%d citations=%d %s"
              % (r["id"], "OK" if not r["error"] else "ERROR", r["provider"] or "-",
                 r["verified"], r["latency_ms"], len(r["citations"]), r["error"]))
    print("Wrote %s" % path_ret)
    print("Wrote %s" % path_smoke)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
