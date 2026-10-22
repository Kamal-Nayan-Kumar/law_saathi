"""A/B the native rewrite against the live Groq API.

The question: does `reasoning_effort: "low"` make the Hindi/Kannada rewrite
reliable, and does it cut the reasoning tokens that are burning the TPM quota?

Usage:  python3 scripts/rewrite_ab.py [runs] [gap_seconds]
"""
from __future__ import annotations

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.getcwd(), "api"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.getcwd(), "api", ".env"))
from app import agent as A  # noqa: E402
import httpx  # noqa: E402

DRAFT = """You have a clear legal right to receive maintenance from your husband while you are married. The law requires him to support you if you cannot maintain yourself out of your own earnings or property. [1]

The court decides the amount by looking at your financial situation and your standard of living during the marriage. It also considers your daily needs, and the needs of your children. [1]

You can ask the court for the arrears he has not paid, along with the monthly amount going forward. [2]

### What to do next
- Keep your marriage certificate and any earlier orders.
- Collect bank statements that show the payments stopping.
- Talk to a family lawyer about filing the application."""

RUNS = int(sys.argv[1]) if len(sys.argv) > 1 else 5
GAP = float(sys.argv[2]) if len(sys.argv) > 2 else 12.0

key = os.environ.get("GROQ_API_KEY", "")
MODEL = "openai/gpt-oss-120b"


def build_prompt(lang: str):
    name = A.LANG_NAMES[lang]
    system = (
        "You rewrite one legal answer into %s for a reader who asked in %s. "
        "Rewrite it as if you are saying it to them out loud. Keep every fact and "
        "every citation marker ([1], [2]) exactly as it is. %s\n%s\n"
        "### What to do next\n%s"
    ) % (name, name, A.LANG_PLAIN_RULES[lang], A.NATIVE_SIMPLICITY_RULES,
         A._next_steps_heading(lang))
    return [{"role": "system", "content": system},
            {"role": "user", "content": DRAFT}]


def call(lang, extra):
    payload = {"model": MODEL, "messages": build_prompt(lang), "temperature": 0.2,
               "max_tokens": A.MAX_TOKENS_LONG}
    payload.update(extra)
    t0 = time.time()
    r = httpx.post(A.GROQ_URL,
                   headers={"Authorization": "Bearer " + key,
                            "Content-Type": "application/json"},
                   json=payload, timeout=90.0)
    dt = int((time.time() - t0) * 1000)
    if r.status_code != 200:
        return {"http": r.status_code, "ms": dt, "empty": None}
    d = r.json()
    ch = d["choices"][0]
    m = ch["message"]
    content = (m.get("content") or "").strip()
    return {
        "finish": ch.get("finish_reason"),
        "empty": 0 if content else 1,
        "reasoning": len((m.get("reasoning") or "").strip()),
        "tokens": d.get("usage", {}).get("completion_tokens"),
        "ms": dt,
        "has_native": bool(__import__("re").search(
            r"[\u0900-\u097F]" if lang == "hi" else r"[\u0C80-\u0CFF]", content)),
    }


CONFIGS = [
    ("A current  (max_tokens=%d, no reasoning_effort)" % A.MAX_TOKENS_LONG, {}),
    ("B fix     (max_tokens=%d, reasoning_effort=low)" % A.MAX_TOKENS_LONG,
     {"reasoning_effort": "low"}),
]

for label, extra in CONFIGS:
    print("=" * 74)
    print(label)
    empty = 0
    native = 0
    ok = 0
    toks = []
    for i in range(RUNS):
        res = call("hi", extra)
        print("  run %d: %s" % (i + 1, json.dumps(res)))
        if res.get("empty") == 1:
            empty += 1
        elif res.get("empty") == 0:
            ok += 1
            native += 1 if res.get("has_native") else 0
            toks.append(res.get("tokens") or 0)
        time.sleep(GAP)
    print("  -> empty %d/%d | answered %d | native-script %d | mean tokens %s"
          % (empty, RUNS, ok, native,
             int(sum(toks) / len(toks)) if toks else "-"))
    print()
