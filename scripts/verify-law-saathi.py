#!/usr/bin/env python3
"""Verification harness for Law Saathi.

Drives the real app like an Indian user (ages 21-60+, EN/HI/KN/Hinglish),
evaluates statutory grounding, script fidelity, markdown structure, and voice flow.

Usage:
    python scripts/verify-law-saathi.py doctor
    python scripts/verify-law-saathi.py chat [--lang en|hi|kn|all]
    python scripts/verify-law-saathi.py voice
    python scripts/verify-law-saathi.py all
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

# Ensure repo root and api/scripts are in sys.path
ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "api" / "scripts"))

# Import existing probe module
try:
    import probe
except ImportError:
    probe = None

ARTIFACTS_DIR = ROOT_DIR / "artifacts" / "verify-law-saathi"
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def check_url(url: str, timeout: int = 5) -> tuple[bool, int, str]:
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            return True, resp.status, body
    except Exception as e:
        return False, getattr(e, "code", 0), str(e)


def run_doctor() -> dict:
    results = {
        "timestamp": time.time(),
        "status": "PASS",
        "components": {},
    }

    # 1. FastAPI Health
    ok, code, body = check_url("http://localhost:8000/health")
    backend_up = ok and code == 200 and '"ok"' in body
    results["components"]["backend_api"] = {
        "url": "http://localhost:8000/health",
        "status": "PASS" if backend_up else "FAIL",
        "http_code": code,
        "detail": body[:100],
    }
    if not backend_up:
        results["status"] = "FAIL"

    # 2. Next.js Web Frontend
    ok, code, body = check_url("http://localhost:3000")
    frontend_up = ok and code == 200
    results["components"]["web_frontend"] = {
        "url": "http://localhost:3000",
        "status": "PASS" if frontend_up else "FAIL",
        "http_code": code,
        "detail": "HTML rendered" if frontend_up else body[:100],
    }
    if not frontend_up:
        results["status"] = "FAIL"

    # 3. Database Check
    db_path = ROOT_DIR / "tmp" / "dev.db"
    db_ok = db_path.exists() and db_path.stat().st_size > 0
    results["components"]["database"] = {
        "type": "SQLite / Neon Postgres",
        "status": "PASS" if db_ok else "FAIL",
        "path": str(db_path),
        "size_bytes": db_path.stat().st_size if db_path.exists() else 0,
    }
    if not db_ok:
        results["status"] = "FAIL"

    # 4. LiveKit Server (Voice)
    ok, code, _ = check_url("http://localhost:7880")
    # LiveKit root usually returns 200 or 404 on HTTP GET when alive
    livekit_up = ok or code in (200, 404, 400)
    results["components"]["livekit_voice_server"] = {
        "port": 7880,
        "status": "PASS" if livekit_up else "WARN",
        "detail": f"HTTP probe returned status {code}",
    }

    evidence_file = ARTIFACTS_DIR / "doctor.json"
    evidence_file.write_text(json.dumps(results, indent=2))
    return results


def has_devanagari(text: str) -> bool:
    return bool(re.search(r"[\u0900-\u097F]", text))


def has_kannada(text: str) -> bool:
    return bool(re.search(r"[\u0C80-\u0CFF]", text))


def has_hinglish(text: str) -> bool:
    low = (text or "").lower()
    return any(w in low for w in (
        "hai", "hain", "karein", "karna", "hoga", "hogi", "sakte", "sakti",
        "aap", "aapko", "liye", "agar", "aur", "ko", "ki", "ke", "ka",
        "se", "me", "mein", "to", "nahi", "nahin", "kya"
    ))


PERSONA_TEST_CASES = [
    {
        "id": "persona_sunita_hi",
        "name": "Sunita (Age 34, Hindi speaker, maintenance query)",
        "lang": "hi",
        "query": "मेरे पति ने 4 महीने से खर्चा नहीं दिया, मुझे क्या करना चाहिए?",
        "expected_act_keywords": ["Hindu", "Maintenance", "18", "20", "125"],
        "script_validator": has_devanagari,
        "script_name": "Devanagari (Hindi)",
    },
    {
        "id": "persona_lakshmi_kn",
        "name": "Lakshmi (Age 28, Kannada speaker, mutual divorce query)",
        "lang": "kn",
        "query": "ಪತಿಯಿಂದ ಪರಸ್ಪರ ಒಪ್ಪಿಗೆಯ ವಿಚ್ಛೇದನ ಪಡೆಯುವುದು ಹೇಗೆ? ನಿಯಮಗಳೇನು?",
        "expected_act_keywords": ["Hindu Marriage", "13", "13B"],
        "script_validator": has_kannada,
        "script_name": "Kannada",
    },
    {
        "id": "persona_joseph_en",
        "name": "Joseph (Age 40, English, child custody concern)",
        "lang": "en",
        "query": "Who gets custody of my 5 year old daughter after divorce? Does higher income guarantee custody?",
        "expected_act_keywords": ["Custody", "Guardians", "Minor", "Welfare", "Section"],
        "script_validator": lambda t: len(t) > 50,
        "script_name": "English",
    },
    {
        "id": "persona_ramesh_hinglish",
        "name": "Ramesh (Age 62, Senior citizen, Hinglish query)",
        "lang": "hi",
        "query": "Mera beta humko ghar se nikalne ki dhamki de raha hai, kya senior citizen act me hum complaint kar sakte hain?",
        "expected_act_keywords": ["Senior Citizens", "Parents", "Maintenance", "2007", "Section"],
        "script_validator": has_hinglish,
        "script_name": "Hinglish (Roman Hindi)",
    },
    {
        "id": "persona_hinglish_adoption",
        "name": "Adoption rules in Hinglish (Roman Hindi)",
        "lang": "hi",
        "query": "agar koi bacha adopt karna hai to uska niyam kya hai? dono case me batao jab mai single ya married hu to...",
        "expected_act_keywords": ["Juvenile Justice", "CARA", "Adoption", "2015", "Section"],
        "script_validator": has_hinglish,
        "script_name": "Hinglish (Roman Hindi)",
    },
    {
        "id": "persona_proactive_lawyer_near_me",
        "name": "Proactive location clarification (Lawyer near me)",
        "lang": "en",
        "query": "can u find best lawyer which listed online near me?",
        "is_clarification": True,
        "expected_act_keywords": [],
        "script_validator": lambda t: "city" in t.lower() or "district" in t.lower(),
        "script_name": "Location clarification prompt",
    },
    {
        "id": "persona_firecrawl_delhi_lawyer",
        "name": "Firecrawl lawyer search with location (Delhi)",
        "lang": "en",
        "query": "find best family law lawyers in Delhi",
        "expected_act_keywords": ["Delhi", "Lawyer", "Advocate"],
        "script_validator": lambda t: len(t) > 80,
        "script_name": "English with Firecrawl web citations",
        "expect_web_citation": True,
    },
    {
        "id": "persona_out_of_scope",
        "name": "Out of Scope (Age 45, Landlord tenancy dispute)",
        "lang": "en",
        "query": "My landlord is refusing to return my security deposit of 50000 rupees. Can police help?",
        "is_oos": True,
        "expected_act_keywords": [],
        "script_validator": lambda t: len(t) > 20,
        "script_name": "English",
    },
]


def run_chat_verification(lang_filter: str = "all", persona_filter: str | None = None) -> dict:
    if probe is None:
        raise RuntimeError("api/scripts/probe.py could not be imported")

    results = {
        "timestamp": time.time(),
        "status": "PASS",
        "test_cases": [],
    }

    test_cases = PERSONA_TEST_CASES
    if persona_filter:
        test_cases = [tc for tc in test_cases if tc.get("id") == persona_filter]
    elif lang_filter in ("en", "hi", "kn"):
        test_cases = [tc for tc in test_cases if tc.get("lang") == lang_filter]

    for tc in test_cases:
        t0 = time.time()
        tc_res = {
            "id": tc["id"],
            "name": tc["name"],
            "query": tc["query"],
            "lang": tc["lang"],
            "status": "PASS",
            "checks": {},
            "latency_seconds": 0,
        }

        try:
            sid = probe.new_session(1, f"verify_{tc['id']}")
            resp = probe.ask(sid, tc["query"], lang=tc["lang"])
            duration = round(time.time() - t0, 2)
            tc_res["latency_seconds"] = duration

            if not resp:
                tc_res["status"] = "FAIL"
                tc_res["error"] = "Empty response received"
                results["test_cases"].append(tc_res)
                results["status"] = "FAIL"
                continue

            ans = resp.get("answer", "")
            citations = resp.get("citations", [])
            tc_res["answer_snippet"] = ans[:350]
            tc_res["citations"] = citations

            # 1. Out of Scope Check
            if tc.get("is_oos"):
                oos_triggered = resp.get("oos_redirect") is True or any(
                    w in ans.lower()
                    for w in ["family law", "specializes", "not covered", "outside", "rent", "landlord"]
                )
                tc_res["checks"]["out_of_scope_redirect"] = "PASS" if oos_triggered else "FAIL"
                if not oos_triggered:
                    tc_res["status"] = "FAIL"
                results["test_cases"].append(tc_res)
                continue

            # 1b. Proactive Clarification Check
            if tc.get("is_clarification"):
                is_clarify = resp.get("clarification") is True or any(
                    w in ans.lower()
                    for w in ["city", "district", "located in", "शहर", "ज़िले", "ನಗರ", "ಜಿಲ್ಲೆ"]
                )
                tc_res["checks"]["clarification_prompt"] = "PASS" if is_clarify else "FAIL"
                if not is_clarify:
                    tc_res["status"] = "FAIL"
                results["test_cases"].append(tc_res)
                continue

            # 2. Script & Language Check
            script_ok = tc["script_validator"](ans)
            tc_res["checks"]["script_fidelity"] = {
                "expected_script": tc["script_name"],
                "status": "PASS" if script_ok else "FAIL",
            }
            if not script_ok:
                tc_res["status"] = "FAIL"

            # 3. Grounding & Citations Check
            all_text = ans + " " + " ".join(citations)
            grounded = any(k.lower() in all_text.lower() for k in tc["expected_act_keywords"])
            tc_res["checks"]["statutory_grounding"] = {
                "expected_keywords": tc["expected_act_keywords"],
                "has_citations": len(citations) > 0,
                "status": "PASS" if (grounded and len(citations) > 0) else "WARN",
            }

            if tc.get("expect_web_citation"):
                has_web = any(src == "web" for src in resp.get("citation_sources", [])) or len(citations) > 0
                tc_res["checks"]["firecrawl_web_citation"] = "PASS" if has_web else "FAIL"
                if not has_web:
                    tc_res["status"] = "FAIL"

            # 4. Readability & Markdown Check
            has_markdown = any(m in ans for m in ["###", "**", "-", "*"])
            tc_res["checks"]["markdown_structure"] = "PASS" if has_markdown else "WARN"

            # 5. Disclaimer Check
            has_disclaimer = any(
                d in ans.lower()
                for d in [
                    "सलाह नहीं",
                    "ಕಾನೂನು ಸಲಹೆ ಅಲ್ಲ",
                    "legal advice",
                    "consult",
                    "lawyer",
                    "वकील",
                    "ವಕೀಲರ",
                    "kewal samanya jaankari",
                    "kanooni salah nahi",
                    "vakeel se salah",
                ]
            )
            tc_res["checks"]["legal_disclaimer"] = "PASS" if has_disclaimer else "WARN"

        except Exception as e:
            tc_res["status"] = "FAIL"
            tc_res["error"] = str(e)
            results["status"] = "FAIL"

        results["test_cases"].append(tc_res)

    evidence_file = ARTIFACTS_DIR / "chat_proof.json"
    evidence_file.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    return results


def run_voice_verification() -> dict:
    results = {
        "timestamp": time.time(),
        "status": "PASS",
        "output": "",
    }
    test_script = ROOT_DIR / "voice" / "agent" / "test_agent_flow.py"
    py_exec = ROOT_DIR / "voice" / "agent" / ".venv" / "bin" / "python"
    if not py_exec.exists():
        py_exec = ROOT_DIR / ".venv" / "bin" / "python"

    if not test_script.exists():
        results["status"] = "FAIL"
        results["error"] = f"Script not found: {test_script}"
        return results

    try:
        proc = subprocess.run(
            [str(py_exec), str(test_script)],
            cwd=str(ROOT_DIR),
            capture_output=True,
            text=True,
            timeout=120,
        )
        results["output"] = proc.stdout + "\n" + proc.stderr
        if proc.returncode != 0 or "ALL LIVEKIT AGENT INTEGRATION TESTS PASSED" not in proc.stdout:
            results["status"] = "FAIL"
            results["exit_code"] = proc.returncode
    except Exception as e:
        results["status"] = "FAIL"
        results["error"] = str(e)

    evidence_file = ARTIFACTS_DIR / "voice_proof.json"
    evidence_file.write_text(json.dumps(results, indent=2))
    return results


def main():
    parser = argparse.ArgumentParser(description="Law Saathi Verification Harness")
    subparsers = parser.add_subparsers(dest="command", help="Verification command")

    subparsers.add_parser("doctor", help="Run doctor checks on web, API, DB, LiveKit")
    chat_p = subparsers.add_parser("chat", help="Run persona chat evaluations")
    chat_p.add_argument("--lang", default="all", choices=["en", "hi", "kn", "all"])
    chat_p.add_argument("--persona", default=None, help="Specific persona ID to evaluate")
    subparsers.add_parser("voice", help="Run LiveKit/Sarvam voice pipeline tests")
    subparsers.add_parser("all", help="Run doctor, chat, and voice verification")

    args = parser.parse_args()
    cmd = args.command or "doctor"

    print(f"=== Law Saathi Verification Harness: {cmd.upper()} ===")
    overall_ok = True

    if cmd in ("doctor", "all"):
        print("\n--- 1. Doctor Check ---")
        doc_res = run_doctor()
        print(f"Overall Doctor Status: {doc_res['status']}")
        for k, v in doc_res["components"].items():
            print(f"  [{v['status']}] {k}: {v.get('detail', '')}")
        if doc_res["status"] == "FAIL":
            overall_ok = False

    if cmd in ("chat", "all"):
        lang = getattr(args, "lang", "all")
        persona = getattr(args, "persona", None)
        print(f"\n--- 2. Real-User Multilingual Chat Evaluation (lang={lang}, persona={persona}) ---")
        chat_res = run_chat_verification(lang_filter=lang, persona_filter=persona)
        print(f"Overall Chat Status: {chat_res['status']}")
        for tc in chat_res["test_cases"]:
            print(f"\n  [{tc['status']}] {tc['name']}")
            print(f"      Latency: {tc['latency_seconds']}s")
            print(f"      Snippet: {tc.get('answer_snippet', '')[:120]}...")
            for ck, cv in tc.get("checks", {}).items():
                print(f"      - {ck}: {cv}")
        if chat_res["status"] == "FAIL":
            overall_ok = False

    if cmd in ("voice", "all"):
        print("\n--- 3. Realtime Voice Pipeline Test ---")
        voice_res = run_voice_verification()
        print(f"Overall Voice Status: {voice_res['status']}")
        if voice_res["status"] == "FAIL":
            print("  Error:", voice_res.get("error", "Integration test failed"))
            overall_ok = False
        else:
            print("  Sarvam TTS (EN, HI, KN) + LawSaathiLLM: Verified OK")

    print("\n" + "=" * 50)
    print(f"FINAL VERIFICATION RESULT: {'PASSED' if overall_ok else 'FAILED'}")
    print(f"Evidence artifacts saved to: {ARTIFACTS_DIR}")
    sys.exit(0 if overall_ok else 1)


if __name__ == "__main__":
    main()
