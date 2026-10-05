# SCOPE.md — what Law Saathi does, and what it will not do

Written because the questions are the product. A user who asks something outside
this list should be told so in one sentence and pointed somewhere useful — not
given a confident answer about the wrong law.

---

## 1. The one-line scope

**Family law in India: marriage, divorce, child custody, maintenance, adoption,
succession and domestic violence. English, Hindi and Kannada. By voice or
text.**

---

## 2. The seven acts we actually retrieve from

Every answer is grounded in one of these, read from India Code and the Open
India Law corpus. Nothing else is quoted as law.

| Act | What it governs | Sections most asked |
| --- | --- | --- |
| **Hindu Marriage Act, 1955** | marriage, divorce, maintenance pendente lite | 13, 13B, 24, 25 |
| **Special Marriage Act, 1954** | inter-caste and inter-religious marriage, divorce | 13B, 25, 27 |
| **Hindu Adoption and Maintenance Act, 1956** | adoption, maintenance | 3, 4, 11, 18, 19 |
| **Hindu Succession Act, 1956** | inheritance | 8, 15, 17, 18 |
| **Guardians and Wards Act, 1890** | custody and guardianship | 7, 17, 21 |
| **Protection of Women from Domestic Violence Act, 2005** | protection, residence, monetary relief | 17–22 |
| **Indian Divorce Act, 1869** | divorce for Christians | 10, 13 |

424 in-force sections. Repealed provisions are dropped at ingestion, so a
section in an answer is a section in force.

---

## 3. The questions we answer well

Drawn from what people actually typed during persona testing.

**Marriage**
- How do we get married, and what makes a marriage valid?
- Is our marriage registered? What happens if it isn't?
- My marriage was never registered — are we still legally married?
- Can I marry without my family's consent?
- What age can someone get married?

**Divorce**
- How do I get a mutual-consent divorce?
- What grounds does a contested divorce need?
- My husband wants a divorce. What can I do?
- We have lived apart for two years. What are my options?
- Is a divorce valid if it happened without the court?

**Custody and guardianship**
- Who gets custody of my child?
- Is guardianship the same as custody?
- My ex will not let me see my child. What can I do?
- The child says they want to live with me. Does that decide it?
- Can I take my child to live with my family?

**Maintenance**
- My husband has not paid maintenance. What can I do?
- How much can I claim?
- How long does it take?
- Do I need a lawyer?
- Can I claim maintenance for my children?
- What if I left the marital home?

**Domestic violence**
- My husband hits me. What are my options?
- Can I get him removed from the house?
- How do I get a protection order?
- Can the police help me?

**Adoption**
- Can my aunt adopt a child who cannot live with the parents?
- What does adoption by a relative require?
- Does an adopted child inherit from me?

**Succession**
- My husband died and my son is taking all the property.
- If he made a will and left everything to the son, can I still claim?
- Who are the legal heirs?
- My father died without a will. How is the land divided?

---

## 4. The questions we redirect

Refusing is a feature. Answering confidently about the wrong law is worse than
saying no, and in a legal context "I don't know" is information.

| Out of scope | Example we get | Why |
| --- | --- | --- |
| Property and land | "my landlord won't return my deposit" | tenancy and property law |
| Criminal | "the police towed my car" | criminal procedure |
| Government process | "I got an RTI notice" | right to information |
| Money and debt | "the bank sent a recovery notice" | banking law |
| Employment | "my employer fired me without notice" | labour law |
| Civil contracts | "they breached my NDA" | contract law |
| Tax | "how do I file my return?" | income tax |
| Passport / visa / elections | "my passport was rejected" | administrative |

The redirect names what we do cover and says to consult a specialist for the
rest. It never guesses.

---

## 5. What we will never do

Non-negotiable, in `CONTEXT.md` and enforced in code:

1. **Never state an uncited legal rule.** Every claim traces to a section. An
   answer with no citation is not verified and says so.
2. **Never present ourselves as a lawyer.** Every answer carries the disclaimer,
   in the user's language.
3. **Never use "alimony" as the default word.** The term is maintenance, and
   "alimony" carries a different implication in Indian practice.
4. **Never mix Hindu and Muslim succession.** The rules differ entirely. Say
   which one applies, or say we cannot tell.
5. **Never state a repealed provision as current.** Amendment notices in the
   corpus trigger a guard that names the amending Act instead.
6. **Never give a timeline as certain.** Court timelines are not in the bare
   acts. Say the Act does not fix one.
7. **Never take a side or predict an outcome.** "You can ask for X" yes;
   "you will win X" never.
8. **Never collect or keep case documents.** The chat stores text only.

---

## 6. How the answer is built

```
question
   ↓  intent       which area, which language, who is asking
   ↓  planner      the MODEL picks the act and the tools
   ↓  tools        search_acts / read_section / search_web
   ↓  reason       the model writes plain English, citing [1] [2]
   ↓  verifier     the MODEL judges whether the draft invented any law
   ↓  response     translate, disclaimer, next steps
answer
```

Two decisions are made by a model, not a rule: which act governs, and whether
the draft is grounded. If the verifier rejects, the run goes back to tools with
the verifier's own replacement queries, once.

---

## 7. Known limits

Honest about what is weak:

- **We cannot tell if you are telling the truth.** We read the question, not
  the evidence.
- **We do not know your state.** Rules are mostly the same across India, but
  procedure varies by state court.
- **Section-level only.** We do not have case law, so we cannot say how a
  particular judge has ruled.
- **One topic at a time.** "Can I get maintenance and custody" is answered as
  two questions, not one combined answer.
- **If no provider is reachable,** the answer degrades to a template built from
  the retrieved sections. It is correct and cited, but plainer than usual. The
  chat tells you the Thinking log, so you can see what happened.

---

## 8. Where the scope lives in code

| Concern | File |
| --- | --- |
| Act and topic routing | `api/app/agent.py` — `TOPIC_KEYWORDS` |
| Out-of-scope refusal | `api/app/agent.py` — `OOS_KEYWORDS`, `is_oos` |
| Disclaimer and redirect text | `api/app/agent.py` — `DISCLAIMER`, `OOS_REDIRECT` |
| Golden questions | `api/eval/golden_qas.py` |
| Routing checks | `api/eval/run_stub.py` |
| Live answer checks | `api/eval/run_golden.py` |

Change the scope in `agent.py`, add a golden question in `golden_qas.py`, and a
test will tell you what broke.