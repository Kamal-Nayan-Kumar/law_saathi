"""Score the agent against the golden dataset.

Run with the API up:  python3 api/eval/run_golden.py
Or offline against the stub:  python3 api/eval/run_golden.py --offline

Deliberately not RAGAS yet. RAGAS needs an LLM judge and an embedding matrix;
what matters here first is that the governing section is cited, the right
language comes back, and nothing confidently wrong is said. Those are checks,
not judgements, so they are cheap, deterministic and cannot be talked into
passing. `eval/ragas_eval.py` adds the judged metrics on top.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any, Dict, List

HERE = os.path.dirname(os.path.abspath(__file__))
API = os.path.dirname(HERE)
sys.path.insert(0, API)
sys.path.insert(0, os.path.join(API, "scripts"))

from eval.golden_qas import GOLDEN_QAS  # noqa: E402


def load_env() -> None:
    env = os.path.join(API, ".env")
    if not os.path.exists(env):
        return
    for line in open(env):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


def run_persona_flows() -> List[Dict[str, Any]]:
    """Ask each persona's questions in order, in one chat.

    The per-question checks cannot catch a conversation-level failure: a follow-
    up that answers from the other spouse's point of view, or drops the topic
    entirely, still "cites the right section" on its own. So the golden set is
    also replayed as real conversations.
    """
    load_env()
    import probe

    personas = [
        ("maintenance", [
            "my husband has not given maintenance for 4 months what can i do",
            "how much can i ask for? i get 18000 he earns around 90000",
            "how long does it take",
            "do i need a lawyer?",
        ]),
        ("domestic_violence", [
            "my husband hits me. i am scared to tell anyone. what are my options",
            "can i get him removed from the house",
        ]),
        ("succession", [
            "my husband passed away and my son is taking all the property",
            "if he made a will and left everything to the son can i still claim",
        ]),
        ("hindi", [
            "मेरे पति ने 4 महीने से महनाना नहीं दी क्या करूं",
            "कितनी मांग सकती हूं",
            "क्या वकील लेना जरूरी है",
        ]),
        ("kannada", [
            "ಪತಿ ಬಿಡಿ ಮಾಡಿಕೊಡುತ್ತಾನೆ ಏನು ಮಾಡಬೇಕು",
            "ವಿವಾಹ ವಿಚ್ಛೇದನೆ ಹೇಗೆ ಪಡೆಯುವುದು",
        ]),
    ]
    out = []
    for name, turns in personas:
        lang = {"hindi": "hi", "kannada": "kn"}.get(name, "en")
        problems: List[str] = []
        try:
            sid = probe.new_session(1, "flow:" + name)
            results = [probe.ask(sid, q, lang=lang) for q in turns]
        except Exception as e:  # noqa: BLE001
            out.append({"id": "flow-" + name, "mode": "flow",
                        "problems": [f"crashed: {e}"[:200]]})
            continue

        for i, r in enumerate(results):
            answer = (r.get("answer") or "").lower()
            if not answer:
                problems.append(f"turn {i + 1}: empty answer")
                continue
            if lang in ("hi", "kn"):
                script = "ऀ-ॿ" if lang == "hi" else "ಀ-೿"
                if not re.search(f"[{script}]", answer):
                    problems.append(f"turn {i + 1}: answered in the wrong script")
            # A follow-up must not fall back to asking what the question is
            # about: the conversation already answered that.
            if i > 0 and ("what is this about" in answer
                          or "what's this about" in answer):
                problems.append(f"turn {i + 1}: asked the topic again")

        out.append({
            "id": "flow-" + name,
            "mode": "flow",
            "turns": len(results),
            "latencies_ms": [int((r.get("_ms") or 0)) for r in results],
            "problems": problems,
        })
    return out


def check(item: Dict[str, Any], result: Dict[str, Any]) -> List[str]:
    """Return the list of failures for one question. Empty means it passed."""
    problems: List[str] = []
    answer = str(result.get("answer") or "")
    low = answer.lower()
    citations = " ".join(result.get("citations") or [])

    if item.get("must_redirect"):
        if not result.get("oos_redirect") and "outside my family-law scope" not in low:
            problems.append("should have redirected out of scope")
        for banned in item.get("must_not", []):
            if banned.lower() in low:
                problems.append(f"answered out-of-scope question, mentioned {banned!r}")
        return problems

    for term in item.get("must_include_terms", []):
        if term.lower() not in low and term.lower() not in citations.lower():
            problems.append(f"missing term {term!r}")

    sections = [s for s in item.get("must_include_any", []) if s]
    if sections:
        if not any(s in answer or s in citations for s in sections):
            problems.append(f"none of {sections} cited")

    for banned in item.get("must_not", []):
        if banned.lower() in low:
            problems.append(f"said {banned!r}, which is wrong")

    # Language: a Hindi question must not get an English answer.
    if item["lang"] in ("hi", "kn"):
        script = "ऀ-ॿ" if item["lang"] == "hi" else "ಀ-೿"
        if not re.search(f"[{script}]", answer):
            problems.append(f"answered in the wrong script for lang={item['lang']}")

    conf = float(result.get("confidence") or 0.0)
    floor = float(item.get("min_confidence") or 0.0)
    if conf < floor:
        problems.append(f"confidence {conf:.2f} below floor {floor:.2f}")

    if not result.get("verified", False) and not item.get("must_redirect"):
        problems.append("answer was not verified")

    return problems


def run_offline() -> List[Dict[str, Any]]:
    """Exercise the routing decisions without any model.

    Fast and key-free: it catches the class of bug that hurt most, where a
    question routed to the wrong act entirely.
    """
    from app import agent as A

    out = []
    for item in GOLDEN_QAS:
        oos = A.is_oos(item["query"])
        slots = A.extract_slots(item["query"])
        problems = []
        if item.get("must_redirect") and not oos:
            problems.append("should be out of scope")
        if not item.get("must_redirect") and oos:
            problems.append("wrongly treated as out of scope")
        if item["lang"] != "en":
            detected = A.detect_lang(item["query"])
            if detected != item["lang"]:
                problems.append(f"language detected as {detected}, expected {item['lang']}")
        if not item.get("must_redirect"):
            if not slots.get("topic"):
                problems.append(f"no topic extracted (got {slots})")
        out.append({"id": item["id"], "mode": "offline", "problems": problems,
                    "topic": slots.get("topic")})
    return out


def run_live() -> List[Dict[str, Any]]:
    load_env()
    import probe

    out = []
    for item in GOLDEN_QAS:
        try:
            sid = probe.new_session(1, "golden:" + item["id"])
            result = probe.ask(sid, item["query"], lang=item["lang"])
        except Exception as e:  # noqa: BLE001 — the failure is the finding
            out.append({"id": item["id"], "mode": "live",
                        "problems": [f"crashed: {e}"[:200]]})
            continue
        problems = check(item, result)
        out.append({
            "id": item["id"],
            "mode": "live",
            "lang": item["lang"],
            "topic": (result.get("trace_detail") or [{}])[0].get("detail", "")[:80],
            "confidence": result.get("confidence"),
            "verified": result.get("verified"),
            "citations": result.get("citations"),
            "provider": result.get("provider"),
            "problems": problems,
        })
    return out


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true",
                    help="check routing only, no model calls")
    ap.add_argument("--flows", action="store_true",
                    help="replay whole persona conversations")
    ap.add_argument("--only", help="run one question id")
    ap.add_argument("--json", help="write the full report here")
    args = ap.parse_args(argv[1:])

    rows = run_offline() if args.offline else run_live()
    if args.flows:
        rows = rows + run_persona_flows()
    if args.only:
        rows = [r for r in rows if r["id"] == args.only]

    passed = [r for r in rows if not r["problems"]]
    label = ("offline routing" if args.offline else "live")
    if args.flows:
        label += " + persona flows"
    print(f"\n{len(passed)}/{len(rows)} passed ({label})\n")
    for r in rows:
        mark = "PASS" if not r["problems"] else "FAIL"
        print(f"{mark}  {r['id']}")
        for p in r["problems"]:
            print(f"        - {p}")

    if args.json:
        with open(args.json, "w") as fh:
            json.dump({"total": len(rows), "passed": len(passed), "rows": rows},
                      fh, indent=1, ensure_ascii=False)
        print(f"\nwrote {args.json}")

    return 0 if len(passed) == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))