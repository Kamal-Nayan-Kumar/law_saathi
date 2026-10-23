# Law Saathi Comprehensive Testing Guide

This guide provides test questions across English, Hindi, Hinglish, and Bhojpuri, edge cases, voice testing, and known issues.

---

## 1. Current Known Issues to Watch For

1. **Bhojpuri and regional dialects:** When asked in Devanagari Bhojpuri (`हमार पति खर्चा नइखन देत, हम का करीं?`), retrieval finds the right statute, but the rewriter may sometimes fall back to English if the translation model struggles with regional dialect vocabulary.
2. **Groq rate limits on the 120B model:** If you send several complex questions in quick succession, Groq may return HTTP 429. The pipeline will step down to `gpt-oss-20b` or `qwen3.8-27b`. If all models time out, you will receive the English draft.
3. **Repealed statutes (CrPC 125):** The bare act index holds BNSS 2023 Section 144, not repealed CrPC 1973. If you ask about CrPC 125, verify that it links to BNSS 144 and the Supreme Court 2024 ruling (*Mohd. Abdul Samad*).
4. **Uncodified Muslim personal law:** Muslim maintenance and divorce rely on the 1939 and 1986 Acts and Supreme Court precedents. The database contains no codified Muslim inheritance statute because none exists in India.

---

## 2. Test Suite by Category

### Category 1: Core Legal Questions Across 4 Languages

#### English
- **Child Custody:**
  - *Query:* `Can a mother get custody of her 3-year-old child if she is not earning?`
  - *What to check:* Cites Hindu Minority and Guardianship Act Section 6(a) (child under 5 ordinarily with mother) and Guardians and Wards Act Section 17 (paramount welfare of child).
- **Mutual Consent Divorce Waiver:**
  - *Query:* `Can the 6-month cooling off period in mutual consent divorce be waived?`
  - *What to check:* Cites HMA Section 13B and Supreme Court waiver rulings (*Amardeep Singh* or *Shilpa Sailesh*).

#### Hindi
- **Maintenance (Alimony):**
  - *Query:* `मेरे पति ने 6 महीने से खर्चा नहीं दिया, क्या मैं अलग रहकर भी भरण-पोषण मांग सकती हूँ?`
  - *What to check:* Cites Hindu Adoptions and Maintenance Act Section 18, gives an answer in Devanagari Hindi, and includes actionable next steps.
- **Inheritance & Succession:**
  - *Query:* `क्या शादीशुदा बेटी का अपने पिता की पैतृक संपत्ति में बराबर का हक है?`
  - *What to check:* Cites Hindu Succession Act Section 6 (2005 amendment) and *Vineeta Sharma* ruling.

#### Hinglish
- **Child Adoption:**
  - *Query:* `agar koi bacha adopt karna hai to uska niyam kya hai? dono case me batao jab mai single ya married hu to...`
  - *What to check:* Answer must stay in conversational Roman script Hinglish, cite the Juvenile Justice Act 2015, and list CARA rules.
- **Senior Citizens Protection:**
  - *Query:* `mera beta humko ghar se nikalne ki dhamki de raha hai, kya senior citizen act me complaint kar sakte hain?`
  - *What to check:* Cites Maintenance and Welfare of Parents and Senior Citizens Act 2007 (Section 4 and Section 23 property revocation).

#### Bhojpuri (Devanagari)
- **Wife Maintenance:**
  - *Query:* `हमार पति खर्चा नइखन देत, हम का करीं?`
  - *What to check:* Does it understand that the user is a wife asking for maintenance under HAMA Section 18?
- **Daughter Inheritance:**
  - *Query:* `का बियाह के बाद लइकी के बापू के सम्पति में हक मिलेला?`
  - *What to check:* Does it map to Hindu Succession Act coparcenary rights?

---

### Category 2: Agentic Edge Cases

#### Edge Case A: Proactive Location Clarification (Short Path)
- **Step 1:** Ask: `can u find best lawyer which listed online near me?`
  - *What to check:* It must NOT return US (Dallas/San Jose) lawyers. It must stop in 3 steps and proactively ask: *"To help you find family law advocates, legal aid clinics, or the family court near you, which city or district in India are you located in?"*
- **Step 2:** Follow-up turn in the same chat: Type `dharwad, karnataka` or `Delhi`.
  - *What to check:* It must not end the conversation or reject as out-of-scope. It runs Firecrawl web search, returns real local practitioners in that city, and mentions the District Legal Services Authority (DLSA) for free legal aid.

#### Edge Case B: Out-of-Scope Redirection
- *Query 1:* `My landlord is refusing to return my security deposit of 50000 rupees. Can police help?`
- *Query 2:* `Someone stole my bike from the parking lot. How to file FIR?`
- *What to check:* The agent must immediately refuse with a polite redirection explaining that it covers Indian family law, without citing fake divorce sections.

#### Edge Case C: Conversational Pleasantries and Identity
- *Query 1:* `Who are you and what laws do you know?`
  - *What to check:* Answers in short with its family law specialties and disclaimer.
- *Query 2:* `Thank you so much, this helped!`
  - *What to check:* Replies with a polite *"You are welcome"* in 1 turn, without saying *"I am only a family-law assistant"*.

#### Edge Case D: Multi-turn Contextual Follow-ups
- *Turn 1:* `How to apply for mutual consent divorce under Hindu law?`
- *Turn 2:* `How long does it take?`
  - *What to check:* Turn 2 must remember Turn 1 and answer with the 6 to 18-month timeline of Section 13B without needing "divorce" repeated.
- *Turn 3:* `What documents are required?`
  - *What to check:* Lists marriage certificate, proof of 1-year separation, and photographs.

#### Edge Case E: Low-Information Inputs
- *Query 1:* `custody`
- *Query 2:* `maintenance krna hai`
- *What to check:* It must provide the general rule and ask a clear follow-up to narrow down who is claiming.

---

### Category 3: Voice Testing in Normal Chat

1. **Microphone voice input (STT):**
   - Click the mic icon in the composer.
   - Speak in English, Hindi, or Hinglish: *"What is Section 13B mutual divorce?"*
   - Tap mic again to stop.
   - *What to check:* The transcript lands in the text box accurately before sending (via Sarvam AI `saaras:v4` or Groq Whisper fallback).
2. **Read aloud button (TTS):**
   - Click the "Read aloud" speaker button below an answer card.
   - *What to check:* The browser voice reads the content naturally without speaking markdown symbols (`#`, `*`, `[1]`).

---

### Collaborative Testing Workflow

1. Send: `divorce ke liye cooling off period kaise waive hota hai?`
2. Send: `हमार पति खर्चा नइखन देत, हम का करीं?`
3. Send: `can u find best lawyer which listed online near me?` -> follow up with `dharwad, karnataka`.
4. Inspect the decision trace under *"How Saathi worked this out"* to verify node paths and citations.
