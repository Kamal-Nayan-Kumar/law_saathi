# Multilingual Empathy Chat

Multilingual Empathy Chat verifies that Law Saathi provides clear, compassionate, and understandable legal guidance in the user's native language and script (Hindi in Devanagari, Kannada script, English, and conversational Roman Hinglish) across Indian demographics (ages 21 to 60+).

## Sub-features

- `chat-script-fidelity` ensures responses to Hindi queries render in Devanagari script, Kannada queries in Kannada script, and Hinglish queries in conversational Latin-script Hinglish.
- `chat-hinglish-native-answer` guarantees that when a user asks in Hinglish (e.g., "agar koi bacha adopt karna hai to uska niyam kya hai..."), the response is rewritten in conversational Roman Hindi ("Agar aap married hain to dono spouses ko milkar apply karna hoga..."), retaining English Act names and sections.
- `chat-plain-language` checks that legal concepts are explained simply for everyday citizens without dense, unassisted legalese.
- `chat-markdown-structure` validates proper formatting with section headers, actionable bullet points, and clean typography.
- `chat-demographic-personas` exercises distinct scenarios (young newlywed in Karnataka, mother seeking maintenance in Hindi, senior citizen father facing eviction in Hinglish).

## How to get to it (user POV)

- Open `http://localhost:3000/chat`.
- Select language from the header pills: `English`, `हिंदी`, or `ಕನ್ನಡ`, or type directly in Hinglish.
- Enter your question in the text box and press Enter or click the Send button.

## Driving it with control-law-saathi

Preconditions:
- Doctor check passes (`.venv/bin/python scripts/verify-law-saathi.py doctor`).
- System prompt and multilingual rewriters are operational.

- **Hindi Persona (Sunita, 34, Maintenance).** Ask in Devanagari:
  ```sh
  .venv/bin/python scripts/verify-law-saathi.py chat --persona persona_sunita_hi
  ```
  Observable result: Response is in Devanagari script, cites HAMA/CrPC sections, explains maintenance in plain words, and includes legal disclaimer.
- **Kannada Persona (Lakshmi, 28, Mutual Divorce).** Ask in Kannada:
  ```sh
  .venv/bin/python scripts/verify-law-saathi.py chat --persona persona_lakshmi_kn
  ```
  Observable result: Response is in Kannada script, covers mutual consent divorce under Hindu Marriage Act Section 13B, and formats actionable next steps.
- **Hinglish Persona (Adoption Rules).** Ask in Roman Hindi:
  ```sh
  .venv/bin/python scripts/verify-law-saathi.py chat --persona persona_hinglish_adoption
  ```
  Observable result: Response is in conversational Roman Hinglish, cites Juvenile Justice Act 2015 and CARA, and ends with Romanized disclaimer (`Kewal samanya jaankari, kanooni salah nahi...`).
- **Proof.** Confirm all test runs are recorded in `artifacts/verify-law-saathi/chat_proof.json` with `script_fidelity: PASS` and `markdown_structure: PASS`.

## Gotchas

- When a question is typed in Hinglish (Latin letters), the answer must NOT fall back to raw English or be forced into Devanagari; it should be rewritten into natural conversational Hinglish.
- Act names and section numbers stay in English (e.g., "Hindu Marriage Act, 1955 — Section 13B") because statutory citations cannot be translated without losing legal verifiability.
