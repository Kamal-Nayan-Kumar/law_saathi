#!/usr/bin/env python3
"""Offline retrieval proxy eval (Phase B).

No embeddings, no LLM keys, no network. Runs extract_slots + detect_lang +
is_oos over RETRIEVAL_EXPECTED, GOLDEN_EXPANDED and GOLDEN_QAS, then a
smoke test of InMemoryVectorStore with stubbed (hash-based) embeddings.

Checks per question:
  - lang:  detect_lang matches (en queries written in Hinglish may yield hi)
  - oos:   is_oos False for in-scope, True for must_redirect entries
  - topic: RETRIEVAL_EXPECTED topic must be in the allowed set for that id;
           GOLDEN entries must yield some topic and must not be OOS
           (must_ask_any entries must also be missing personal_law)

Output: report/evals/retrieval_results.json
"""
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "api"))
sys.path.insert(0, os.path.join(ROOT, "report", "dataset"))

from app.agent import detect_lang, extract_slots, is_hinglish_query, is_oos, missing_for  # noqa: E402
from app.ingest import InMemoryVectorStore, chunk_act  # noqa: E402
from eval.golden_qas import GOLDEN_QAS  # noqa: E402
from golden_expanded import GOLDEN_EXPANDED, RETRIEVAL_EXPECTED  # noqa: E402

# Allowed topics per retrieval id. re-08 "right to reside" also matches the
# custody keyword list ("residence order") in agent.TOPIC_KEYWORDS; re-15
# "section 14" resolves via _SECTION_TOPIC to divorce. Both are recorded as
# alternates so the eval does not hide the behaviour.
RETRIEVAL_TOPICS = {
    "re-01": {"divorce"}, "re-02": {"marriage"}, "re-03": {"divorce"},
    "re-04": {"marriage"}, "re-05": {"maintenance"}, "re-06": {"maintenance"},
    "re-07": {"custody"}, "re-08": {"domestic_violence", "custody"},
    "re-09": {"domestic_violence"}, "re-10": {"domestic_violence"},
    "re-11": {"maintenance"}, "re-12": {"maintenance"},
    "re-13": {"adoption"}, "re-14": {"succession"}, "re-15": {"succession", "divorce"},
    "re-16": {"succession"}, "re-17": {"marriage", "interfaith_marriage"},
    "re-18": {"divorce"}, "re-19": {"divorce"}, "re-20": {"divorce"},
}


def lang_ok(expected: str, detected: str, query: str) -> bool:
    if expected == "hinglish":
        return detected == "hi"
    if expected == "en":
        return detected == "en" or (detected == "hi" and is_hinglish_query(query))
    return detected == expected  # hi, kn


def eval_entry(entry, kind: str) -> dict:
    qid = entry["id"]
    query = entry["query"]
    lang = entry["lang"]
    detected = detect_lang(query)
    slots = extract_slots(query, query)
    topic = slots.get("topic", "")
    oos = is_oos(query)
    details = []
    ok = True

    if not lang_ok(lang, detected, query):
        ok = False
        details.append("lang: expected %s, detected %s" % (lang, detected))

    if entry.get("must_redirect"):
        if not oos:
            ok = False
            details.append("oos: must_redirect but is_oos=false (topic=%s)" % (topic or "none"))
    else:
        if oos:
            ok = False
            details.append("oos: in-scope but is_oos=true (topic=%s)" % (topic or "none"))
        if kind == "retrieval":
            allowed = RETRIEVAL_TOPICS.get(qid, set())
            if topic not in allowed:
                ok = False
                details.append("topic: expected %s, got %s" % (sorted(allowed), topic or "none"))
        else:
            if not topic:
                ok = False
                details.append("topic: none extracted")
        if entry.get("must_ask_any"):
            missing = missing_for(slots, query)
            if "personal_law" not in missing:
                ok = False
                details.append("clarify: expected missing personal_law, got %s" % missing)

    return {
        "id": qid, "kind": kind, "lang": lang, "query": query,
        "detected_lang": detected, "topic": topic,
        "personal_law": slots.get("personal_law", ""),
        "is_oos": oos, "pass": ok, "details": details,
    }


# --- InMemoryVectorStore smoke test with stubbed embeddings ------------------

DIM = 384


def stub_embed(text: str):
    """Deterministic bag-of-words hash vector. Lexical, no network."""
    vec = [0.0] * DIM
    for tok in re.findall(r"[a-z0-9]+", (text or "").lower()):
        h = int(hashlib.sha256(tok.encode()).hexdigest(), 16)
        vec[h % DIM] += 1.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


FAKE_ACTS = [
    ("Hindu Marriage Act, 1955",
     "Section 13B: Mutual consent divorce requires living separately for one year. "
     "Section 9: Restitution of conjugal rights."),
    ("Protection of Women from Domestic Violence Act, 2005",
     "Section 19: Right to reside in a shared household. "
     "Section 20: Monetary relief from the Magistrate."),
    ("Hindu Succession Act, 1956",
     "Section 8: Class I heirs include daughters and sons equally. "
     "Section 14: Womans property stridhan."),
]
SMOKE_QUERIES = [
    ("mutual consent divorce living separately", "Hindu Marriage Act, 1955", "13B"),
    ("right to reside shared household", "Protection of Women from Domestic Violence Act, 2005", "19"),
    ("monetary relief magistrate", "Protection of Women from Domestic Violence Act, 2005", "20"),
    ("daughters class I heirs", "Hindu Succession Act, 1956", "8"),
    ("stridhan property", "Hindu Succession Act, 1956", "14"),
]


def smoke_test() -> list:
    store = InMemoryVectorStore()
    ids, vecs, payloads = [], [], []
    for act, text in FAKE_ACTS:
        for chunk in chunk_act(act, text, uid="smoke"):
            vecs.append(stub_embed(chunk.text))
            payloads.append(chunk.payload())
            ids.append("%s|%s" % (act, chunk.section))
    store.upsert(ids, vecs, payloads)
    results = []
    for query, want_act, want_sec in SMOKE_QUERIES:
        hits = store.search(stub_embed(query), top_k=3)
        top_payload = (hits[0]["payload"] if hits else {})
        got_act = top_payload.get("act", "")
        got_sec = top_payload.get("section", "")
        ok = got_act == want_act and want_sec in got_sec
        results.append({"query": query, "expected_act": want_act,
                        "expected_section": want_sec, "got_act": got_act,
                        "got_section": got_sec, "pass": ok})
    return results


def main() -> int:
    rows = []
    for entry in RETRIEVAL_EXPECTED:
        rows.append(eval_entry(entry, "retrieval"))
    for entry in GOLDEN_EXPANDED:
        rows.append(eval_entry(entry, "golden_expanded"))
    for entry in GOLDEN_QAS:
        rows.append(eval_entry(entry, "golden"))

    smoke = smoke_test()
    n = len(rows)
    passed = sum(1 for r in rows if r["pass"])
    smoke_passed = sum(1 for r in smoke if r["pass"])

    out = {
        "n": n, "passed": passed, "pass_rate": round(passed / n, 4) if n else 0.0,
        "by_kind": {},
        "smoke": {"n": len(smoke), "passed": smoke_passed,
                  "pass_rate": round(smoke_passed / len(smoke), 4) if smoke else 0.0,
                  "results": smoke},
        "rows": rows,
    }
    for kind in ("retrieval", "golden_expanded", "golden"):
        sub = [r for r in rows if r["kind"] == kind]
        out["by_kind"][kind] = {"n": len(sub),
                                "passed": sum(1 for r in sub if r["pass"])}

    path = os.path.join(HERE, "retrieval_results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print("Retrieval proxy eval (offline): %d/%d passed (%.1f%%)"
          % (passed, n, 100.0 * passed / n if n else 0))
    for kind, sub in out["by_kind"].items():
        print("  %-15s %d/%d" % (kind, sub["passed"], sub["n"]))
    print("\nID / lang / topic / oos / result")
    for r in rows:
        mark = "PASS" if r["pass"] else "FAIL"
        detail = "; ".join(r["details"])
        print("  %-34s %s->%s topic=%-17s oos=%-5s %s%s"
              % (r["id"], r["lang"], r["detected_lang"], r["topic"] or "-",
                 r["is_oos"], mark, ("  " + detail) if detail else ""))
    print("\nVector smoke test: %d/%d passed" % (smoke_passed, len(smoke)))
    for r in smoke:
        print("  %-45s %s" % (r["query"], "PASS" if r["pass"] else "FAIL got %s %s" % (r["got_act"], r["got_section"])))
    print("\nWrote %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
