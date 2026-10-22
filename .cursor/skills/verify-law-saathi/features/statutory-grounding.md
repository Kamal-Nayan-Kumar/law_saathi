# Statutory Grounding

Statutory grounding ensures every legal statement is verified against the bare Acts from India Code and relevant case law, preventing hallucinated sections, fictitious remedies, or misapplied personal laws.

## Sub-features

- `grounding-bare-act-citations` verifies citations link to real enacted central family law acts and exact section numbers.
- `grounding-verifier-pass` ensures answers are verified against retrieved passages before returning.
- `grounding-personal-laws` verifies Hindu, Muslim, Christian, and Parsi family law provisions are never conflated.
- `grounding-mandatory-disclaimer` ensures an unambiguous disclaimer is appended stating this is legal information, not formal counsel.

## How to get to it (user POV)

- Ask any specific family law question on `http://localhost:3000/chat`.
- Click on the citation badges or source cards underneath the message.
- Verify that each assertion cites its governing Act and Section.

## Driving it with control-law-saathi

Preconditions:
- Doctor check passes.
- Qdrant Cloud collection `law_saathi` is populated (~8,852 points).

- **Verify Mutual Consent Divorce Grounding (HMA 13B).**
  ```sh
  .venv/bin/python -c 'import sys; sys.path.insert(0, "api/scripts"); import probe; s = probe.new_session(1, "divorce_grounding"); r = probe.ask(s, "What is the waiting period for mutual consent divorce under Hindu law?", lang="en"); print(r["citations"]); print("Verified:", r.get("verified"))'
  ```
  Observable result: Cites `Hindu Marriage Act, 1955 — Section 13B`, mentions the mandatory 6-month cooling off period, and reports `verified: True`.
- **Verify Domestic Violence Relief (PWDV Act 2005).**
  ```sh
  .venv/bin/python -c 'import sys; sys.path.insert(0, "api/scripts"); import probe; s = probe.new_session(1, "dv_grounding"); r = probe.ask(s, "Can a magistrate order an abusive husband to leave the shared household?", lang="en"); print(r["citations"])'
  ```
  Observable result: Cites `Protection of Women from Domestic Violence Act, 2005 — Section 19` (residence order).
- **Proof.** Inspect `artifacts/verify-law-saathi/chat_proof.json` and ensure `statutory_grounding.status: PASS` and `legal_disclaimer: PASS`.

## Gotchas

- Unamended central legislation may not mention subsequent Supreme Court rulings (e.g. waiver of 6-month cooling period under Article 142). The system incorporates amendment notices from `corpus/amendments.jsonl` for SMA s.28 and HMA s.13B.
- Never accept a citation without a section number (e.g., citing just "Hindu Law" without a statute fails verification).
