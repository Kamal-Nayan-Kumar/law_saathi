# Scope Guard and Follow-ups

Scope Guard and Follow-ups verifies that Law Saathi enforces strict domain boundaries (Indian family law only) by refusing non-family queries gracefully, proactively clarifying missing location slots for local advocate/court searches, and maintaining multi-turn context on follow-up questions.

## Sub-features

- `scope-redirect-non-family` detects criminal, tenancy, commercial, or tax disputes and redirects politely without fabricating legal advice.
- `scope-proactive-location-clarification` intercepts location-dependent requests (e.g., "find best lawyer online near me", "family court near me") and proactively asks for the user's city/district in India in short without traversing heavy retrieval nodes.
- `scope-follow-up-resolution` resolves conversational follow-ups (e.g. providing "Delhi" after being asked for location, or "how long does it take?" after divorce) against prior turns.

## How to get to it (user POV)

- In `http://localhost:3000/chat`, submit a non-family-law query like: "My landlord is not giving back my security deposit, can I file a police complaint?"
- Submit "can u find best lawyer which listed online near me?" and observe the assistant immediately ask: "To help you find family law advocates... which city or district in India are you located in?"
- Reply with your city (e.g. "Delhi" or "Bengaluru") and receive verified local advocates and District Legal Services Authority (DLSA) information.

## Driving it with control-law-saathi

Preconditions:
- Doctor check passes.
- API is running with intent classification active.

- **Test Non-Family Law Redirection (Tenancy / Landlord).**
  ```sh
  .venv/bin/python scripts/verify-law-saathi.py chat --persona persona_out_of_scope
  ```
  Observable result: `out_of_scope_redirect: PASS`, and text politely explains that Law Saathi focuses on family law.
- **Test Proactive Location Clarification (Short Path).**
  ```sh
  .venv/bin/python scripts/verify-law-saathi.py chat --persona persona_proactive_lawyer_near_me
  ```
  Observable result: Status `PASS`, `clarification: True`, response time < 1s (short path), asks for city or district in India.
- **Test Follow-up Location Resolution.**
  ```sh
  .venv/bin/python -c 'import sys; sys.path.insert(0, "api/scripts"); import probe; s = probe.new_session(1, "loc_flow"); probe.ask(s, "can u find best lawyer which listed online near me?"); r2 = probe.ask(s, "Delhi"); print("Citations:", r2["citations"]); print("Sources:", r2["citation_sources"])'
  ```
  Observable result: Turn 2 executes Firecrawl web search targeting Delhi and returns local family law advocates and DLSA aid.
- **Proof.** Confirm entries in `artifacts/verify-law-saathi/chat_proof.json` verifying `out_of_scope_redirect: PASS` and `clarification_prompt: PASS`.

## Gotchas

- Do not provide legal analysis for out-of-scope matters; giving detailed advice on criminal IPC/BNS or corporate law violates system guardrails.
- Follow-ups must not drag stale context into an unrelated new question.
