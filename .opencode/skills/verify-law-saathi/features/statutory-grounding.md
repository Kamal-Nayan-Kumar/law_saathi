# Statutory Grounding

Statutory grounding ensures every legal statement is verified against the bare Acts from India Code, Supreme Court precedents, and live web search powered exclusively by Firecrawl, preventing hallucinated sections, fictitious remedies, or misapplied personal laws.

## Sub-features

- `grounding-bare-act-citations` verifies citations link to real enacted central family law acts and exact section numbers.
- `grounding-firecrawl-web-search` verifies that queries requiring live judicial updates or local directory lookups execute via Firecrawl exclusively without fallback to generic engines.
- `grounding-verifier-pass` ensures answers are verified against retrieved passages before returning (`verified: True`).
- `grounding-mandatory-disclaimer` ensures an unambiguous disclaimer is appended stating this is legal information, not formal counsel.

## How to get to it (user POV)

- Ask any specific family law question on `http://localhost:3000/chat`.
- Click on the citation badges or source cards underneath the message (marked `BARE ACT` or `WEB SOURCE`).
- Verify that each assertion cites its governing Act and Section or verified web source.

## Driving it with control-law-saathi

Preconditions:
- Doctor check passes.
- Qdrant Cloud collection `law_saathi` is populated (~8,852 points).
- `FIRECRAWL_API_KEY` configured in `api/.env`.

- **Verify Mutual Consent Divorce Grounding (HMA 13B).**
  ```sh
  .venv/bin/python -c 'import sys; sys.path.insert(0, "api/scripts"); import probe; s = probe.new_session(1, "divorce_grounding"); r = probe.ask(s, "What is the waiting period for mutual consent divorce under Hindu law?", lang="en"); print(r["citations"]); print("Verified:", r.get("verified"))'
  ```
  Observable result: Cites `Hindu Marriage Act, 1955 — Section 13B`, mentions the mandatory 6-month cooling off period, and reports `verified: True`.
- **Verify Firecrawl Web Search for Lawyers / Rulings.**
  ```sh
  .venv/bin/python scripts/verify-law-saathi.py chat --persona persona_firecrawl_delhi_lawyer
  ```
  Observable result: Executes `web_search` via Firecrawl, returns real Delhi family law listings and DLSA legal aid guidance, and attaches web citations.
- **Proof.** Inspect `artifacts/verify-law-saathi/chat_proof.json` and ensure `statutory_grounding.status: PASS` and `legal_disclaimer: PASS`.

## Gotchas

- If an amendment has taken place (e.g. mutual consent 6-month cooling off waiver under Supreme Court ruling or SMA s.28 / HMA s.13B notices), ensure the amendment notice chunk is cited alongside the bare Act.
- When searching online directories for lawyers, bare act divorce sections should not be injected as false citations.
