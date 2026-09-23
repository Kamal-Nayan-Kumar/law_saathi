# CONTEXT.md — LawSaathi (single-context)

Family-law legal assistant. Agentic RAG chatbot, EN + HI + KN, text + voice.

## Glossary (use these exact terms)

| Term | Meaning | Notes |
| ---- | ------- | ----- |
| Maintenance | Financial support after separation/divorce (e.g. CrPC 125, Hindu Adoption & Maintenance Act) | Don't say "alimony" as default; say maintenance |
| Custody | Who the child lives with + visitation | Distinct from guardianship (legal authority) |
| Guardianship | Legal authority over minor/person (Guardians & Wards Act) | Custody = care; guardianship = legal power |
| Mutual-consent divorce | Both spouses agree (e.g. HMA Sec 13B) | vs contested divorce (one-sided grounds) |
| Contested divorce | Divorce on grounds (cruelty, desertion…) | Always name the ground + section |
| Adoption | Legal parent-child creation (HAMA / JJ Act) | State which Act applies (Hindu vs others) |
| Succession | Inheritance after death (Hindu Succession Act / Muslim law) | Hindu vs Muslim rules differ — never mix |
| Domestic violence | Abuse grounds + relief (PWDV Act 2005) | Protection order, residence, monetary relief |
| Bare act | Exact statute text from India Code | Ground truth; quotes beat paraphrase |
| Evidence | Retrieved chunks + web sources passed to LLM | Every legal claim needs ≥1 evidence |
| Tool-call step | Visible intermediate step (intent → retrieve → web → verify) shown in chat | Like ChatGPT expandable steps; streams from LangGraph node events |
| Verified answer | Verifier passed: accurate, cited, disclaimer present | No citation = not verified |

## Rules

- Scope is family law only (marriage, divorce, custody, maintenance, adoption, succession, DV). Land/property/criminal/tax = out of scope, reply with redirect.
- Every legal answer: simple language + section/act citation + disclaimer (not a lawyer, verify with professional).
- Hindi/Kannada answers must come from multilingual retrieval, not English-only translation.
