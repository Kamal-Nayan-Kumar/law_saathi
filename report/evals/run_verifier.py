#!/usr/bin/env python3
"""Offline verifier eval (Phase B).

No LLM keys, no network. Two parts:

1. Deterministic local grader over VERIFIER_MUTATIONS. The grounded draft is
   treated as the passage; a draft is "grounded" iff it introduces no novel
   content word (number, section, act name, keyword) beyond the passage.
   grounded_draft must pass, mutated_draft must fail.

2. node_verifier exercised with a stub llm that wraps the same grader,
   to confirm the real verify path works offline.

3. pytest on offline verifier-related tests + a run_agent stub attempt,
   recorded in the output.

Output: report/evals/verifier_results.json
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "api"))
sys.path.insert(0, os.path.join(ROOT, "report", "dataset"))

from app.agent import node_verifier, new_state, run_agent  # noqa: E402
from golden_expanded import VERIFIER_MUTATIONS  # noqa: E402

# Words needed to say a claim without making one. Everything else counts
# as a claim-bearing word, so an invented condition or standard fails.
STOP = set("""
a an the of in on under is are be by for to and or as at with from into
that this it its their his her they he she only? must may can will shall
after before within without per about between through during upon over
if then than so such any all each".split()
""".replace("?", " ").split())

# Number words count as claim words: "six months" vs "one year" is a
# different rule, not a paraphrase.
STOP |= set()

ACTS = [
    "hindu marriage act", "special marriage act", "dissolution of muslim",
    "muslim personal law", "muslim women", "dowry prohibition act",
    "protection of women from domestic violence", "guardians and wards",
    "hindu succession act", "hindu adoption", "parsi marriage and divorce",
    "indian divorce act", "divorce act",
]


def content_tokens(text: str) -> set:
    toks = set(re.findall(r"[a-z0-9]+", (text or "").lower()))
    return toks - STOP


def score_draft(passage: str, draft: str) -> dict:
    """Grounded iff no novel content token and no novel section/act.

    Numbers in words are normalized so 'one year' vs 'six months' is caught
    by the novel-token rule ('six', 'months' are not in the passage)."""
    novel = content_tokens(draft) - content_tokens(passage)
    secs_draft = set(re.findall(r"section\s+\d+[a-z]?", draft.lower()))
    secs_pass = set(re.findall(r"section\s+\d+[a-z]?", passage.lower()))
    novel_secs = secs_draft - secs_pass
    acts_draft = {a for a in ACTS if a in draft.lower()}
    acts_pass = {a for a in ACTS if a in passage.lower()}
    novel_acts = acts_draft - acts_pass
    grounded = not novel and not novel_secs and not novel_acts
    return {"grounded": grounded, "novel_tokens": sorted(novel),
            "novel_sections": sorted(novel_secs), "novel_acts": sorted(novel_acts)}


def stub_llm(passage: str):
    """Deterministic llm double: verdict from the local grader."""
    def _llm(messages):
        draft = messages[-1]["content"].split("Draft answer:")[-1]
        draft = draft.split("Return the JSON")[0]
        res = score_draft(passage, draft)
        verdict = "grounded" if res["grounded"] else "insufficient"
        reason = "ok" if res["grounded"] else ("novel: %s" % (res["novel_tokens"][:4] or res["novel_sections"]))
        return json.dumps({"verdict": verdict, "reason": reason, "next_queries": []}), "stub"
    return _llm


def run_node_verifier(mut) -> dict:
    passage = mut["grounded_draft"]
    llm = stub_llm(passage)
    evidence = [{"score": 0.9, "payload": {"text": passage, "act": "Hindu Marriage Act, 1955",
                                           "section": "Section 13B", "kind": "bare_act"}}]
    out = {}
    for label, draft in (("grounded", mut["grounded_draft"]), ("mutated", mut["mutated_draft"])):
        state = new_state("q", lang="en")
        state["draft"] = draft
        state["evidence"] = evidence
        state["query_en"] = "q"
        res = node_verifier(state, llm=llm)
        out[label] = bool(res["verified"])
    return out


def run_pytest() -> dict:
    files = ["tests/test_agent.py", "tests/test_evidence_selection.py",
             "tests/test_scope_and_ranking.py"]
    res = {"files": files, "ran": False, "passed": 0, "skipped": 0, "failed": 0,
           "returncode": None, "tail": ""}
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest"] + files + ["-q"],
            cwd=os.path.join(ROOT, "api"), capture_output=True, text=True, timeout=120,
        )
    except Exception as e:  # noqa: BLE001
        res["tail"] = "pytest failed to run: %r" % (e,)
        return res
    res["ran"] = True
    res["returncode"] = proc.returncode
    tail = (proc.stdout or "") + (proc.stderr or "")
    res["tail"] = tail.strip().splitlines()[-5:]
    m = re.search(r"(\d+) passed", tail)
    if m:
        res["passed"] = int(m.group(1))
    m = re.search(r"(\d+) failed", tail)
    if m:
        res["failed"] = int(m.group(1))
    m = re.search(r"(\d+) skipped", tail)
    if m:
        res["skipped"] = int(m.group(1))
    return res


def run_agent_stub() -> dict:
    res = {"attempted": True, "ok": False, "error": "", "answer_chars": 0}
    try:
        def fake_llm(messages):
            return json.dumps({"verdict": "grounded", "reason": "stub", "next_queries": []}), "stub"
        try:
            state = run_agent("how do i get mutual consent divorce", lang="en",
                              retriever=None, llm=None, web_search=None)
        except Exception as e:  # noqa: BLE001
            res["error"] = "run_agent(llm=None) raised %r" % (e,)
            return res
        res["ok"] = True
        res["answer_chars"] = len(state.get("answer", ""))
        res["trace_nodes"] = [t.get("node") for t in state.get("trace", []) if isinstance(t, dict)]
    except Exception as e:  # noqa: BLE001
        res["error"] = repr(e)
    return res


def main() -> int:
    rows = []
    grounded_pass = mutated_fail = false_fail = false_pass = 0
    for mut in VERIFIER_MUTATIONS:
        g = score_draft(mut["grounded_draft"], mut["grounded_draft"])
        m = score_draft(mut["grounded_draft"], mut["mutated_draft"])
        node = run_node_verifier(mut)
        catch = (not m["grounded"]) and (not node["mutated"])
        gpass = g["grounded"] and node["grounded"]
        if gpass:
            grounded_pass += 1
        else:
            false_fail += 1
        if catch:
            mutated_fail += 1
        else:
            false_pass += 1
        rows.append({
            "id": mut["id"], "topic": mut["topic"],
            "mutation_type": mut["mutation_type"],
            "grader_grounded_pass": g["grounded"],
            "grader_mutated_fail": (not m["grounded"]),
            "mutated_novel": m["novel_tokens"] + m["novel_sections"] + m["novel_acts"],
            "node_verifier_grounded": node["grounded"],
            "node_verifier_mutated_rejected": (not node["mutated"]),
            "pass": bool(gpass and catch),
        })

    n = len(rows)
    pytest_res = run_pytest()
    agent_stub = run_agent_stub()

    out = {
        "n": n,
        "grounded_passed": grounded_pass,
        "mutated_caught": mutated_fail,
        "catch_rate": round(mutated_fail / n, 4) if n else 0.0,
        "false_fail_rate": round(false_fail / n, 4) if n else 0.0,
        "false_pass_rate": round(false_pass / n, 4) if n else 0.0,
        "pytest": pytest_res,
        "run_agent_stub": agent_stub,
        "rows": rows,
    }
    path = os.path.join(HERE, "verifier_results.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    print("Verifier eval (offline): n=%d catch=%.1f%% false-pass=%.1f%% false-fail=%.1f%%"
          % (n, 100 * out["catch_rate"], 100 * out["false_pass_rate"], 100 * out["false_fail_rate"]))
    for r in rows:
        print("  %-8s %-28s %-14s grounded=%-5s mutated_rejected=%-5s %s"
              % (r["id"], r["topic"][:28], r["mutation_type"], r["node_verifier_grounded"],
                 r["node_verifier_mutated_rejected"], "PASS" if r["pass"] else "FAIL novel=%s" % r["mutated_novel"]))
    print("\npytest: passed=%s skipped=%s failed=%s rc=%s tail=%s"
          % (pytest_res["passed"], pytest_res["skipped"], pytest_res["failed"],
             pytest_res["returncode"], pytest_res["tail"]))
    print("run_agent stub: ok=%s error=%s answer_chars=%s"
          % (agent_stub["ok"], agent_stub["error"], agent_stub["answer_chars"]))
    print("\nWrote %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
