# Multilingual Empathy Chat

Multilingual Empathy Chat verifies that Law Saathi provides clear, compassionate, and understandable legal guidance in the user's native language and script (Hindi, Kannada, English, Hinglish) across Indian demographics (ages 21 to 60+).

## Sub-features

- `chat-script-fidelity` ensures responses to Hindi queries render in Devanagari script and Kannada queries render in Kannada script (not transliterated or machine-translated).
- `chat-plain-language` checks that legal concepts are explained simply for everyday citizens without dense, unassisted legalese.
- `chat-markdown-structure` validates proper formatting with section headers, actionable bullet points, and clean typography.
- `chat-demographic-personas` exercises distinct scenarios (young newlywed in Karnataka, mother seeking maintenance in Hindi, senior citizen father facing eviction in Hinglish).

## How to get to it (user POV)

- Open `http://localhost:3000/chat`.
- Select language from the header pills: `English`, `हिंदी`, or `ಕನ್ನಡ`.
- Enter your question in the text box and press Enter or click the Send button.

## Driving it with control-law-saathi

Preconditions:
- Doctor check passes (`.venv/bin/python scripts/verify-law-saathi.py doctor`).
- System prompt and multilingual rewriters are operational.

- **Hindi Persona (Sunita, 34, Maintenance).** Ask in Devanagari:
  ```sh
  .venv/bin/python scripts/verify-law-saathi.py chat --lang hi
  ```
  Observable result: Response is in Devanagari script, cites HAMA/CrPC sections, explains maintenance in plain words, and includes legal disclaimer.
- **Kannada Persona (Lakshmi, 28, Mutual Divorce).** Ask in Kannada:
  ```sh
  .venv/bin/python scripts/verify-law-saathi.py chat --lang kn
  ```
  Observable result: Response is in Kannada script, covers mutual consent divorce under Hindu Marriage Act Section 13B, and formats actionable next steps.
- **Hinglish Senior Citizen (Ramesh, 62, Senior Citizen Act).** Ask in Hinglish:
  ```sh
  .venv/bin/python -c 'import sys; sys.path.insert(0, "api/scripts"); import probe; s = probe.new_session(1, "ramesh"); r = probe.ask(s, "Mera beta ghar se nikal raha hai kya senior citizen act me complaint kar sakte hain?", lang="hi"); print(r["answer"][:300])'
  ```
  Observable result: Response recognizes the Parents & Senior Citizens Act 2007, maintenance tribunal relief, and eviction protection.
- **Proof.** Confirm all test runs are recorded in `artifacts/verify-law-saathi/chat_proof.json` with `script_fidelity: PASS` and `markdown_structure: PASS`.

## Gotchas

- Act names and section numbers stay in English (e.g., "Hindu Marriage Act, 1955 — Section 13B") because statutory citations cannot be translated without losing legal verifiability.
- If a Hindi response is returned in English, check the multilingual pivot & native rewrite pipeline in `api/app/agent.py`.
