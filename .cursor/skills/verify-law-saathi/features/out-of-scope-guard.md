# Scope Guard and Follow-ups

Scope Guard and Follow-ups verifies that Law Saathi enforces strict domain boundaries (Indian family law only) by refusing non-family queries gracefully, while maintaining multi-turn context on follow-up questions.

## Sub-features

- `scope-redirect-non-family` detects criminal, tenancy, commercial, or tax disputes and redirects politely without fabricating legal advice.
- `scope-follow-up-resolution` resolves conversational follow-ups (e.g. "how long does it take?" or "how much can I ask?") against prior turns.
- `scope-topic-switch` allows clean pivot when the user deliberately transitions between two distinct family law matters.

## How to get to it (user POV)

- In `http://localhost:3000/chat`, submit a question unrelated to family law (e.g. "My landlord won't refund my security deposit").
- Observe the gentle refusal stating Law Saathi's specialization in family law and recommending appropriate civil/local remedies.
- In an ongoing conversation about divorce, ask "how long does it take?" and observe that it answers specifically regarding the divorce timeline.

## Driving it with control-law-saathi

Preconditions:
- Doctor check passes.
- API is running with intent classification active.

- **Test Non-Family Law Redirection (Tenancy / Landlord).**
  ```sh
  .venv/bin/python -c 'import sys; sys.path.insert(0, "api/scripts"); import probe; s = probe.new_session(1, "test_oos"); r = probe.ask(s, "My landlord is not giving back my security deposit. What should I do?"); print("OOS:", r.get("oos_redirect")); print(r["answer"][:250])'
  ```
  Observable result: `oos_redirect: True`, and text politely explains that Law Saathi focuses on family law and advises approaching the local rent authority or civil court.
- **Test Contextual Follow-up Resolution.**
  ```sh
  .venv/bin/python -c 'import sys; sys.path.insert(0, "api/scripts"); import probe; s = probe.new_session(1, "test_followup"); r1 = probe.ask(s, "How do I file for mutual consent divorce under Hindu law?"); r2 = probe.ask(s, "how long does it take?"); print("Followup answer snippet:\n", r2["answer"][:300])'
  ```
  Observable result: Turn 2 explains the 6 to 18-month timeline of Hindu Marriage Act Section 13B without needing the user to repeat the topic.
- **Proof.** Confirm entries in `artifacts/verify-law-saathi/chat_proof.json` verifying `out_of_scope_redirect: PASS`.

## Gotchas

- Do not provide legal analysis for out-of-scope matters; giving detailed advice on criminal IPC/BNS or corporate law violates system guardrails.
- Follow-ups must not drag stale context into an unrelated new question.
