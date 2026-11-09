# Eval dataset expansion (report/dataset/)

Expands `api/eval/golden_qas.py` (`GOLDEN_QAS`, 24 questions). This file adds
coverage the original set does not have, plus two extra eval suites.

## Files

- `golden_expanded.py` — importable Python, three lists:
  - `GOLDEN_EXPANDED` (39 questions)
  - `VERIFIER_MUTATIONS` (20 pairs)
  - `RETRIEVAL_EXPECTED` (20 queries)

Do not overwrite `api/eval/golden_qas.py`. This folder is additive only.

## Dataset design

### GOLDEN_EXPANDED — what changed vs GOLDEN_QAS

Original set covers basics (HMA divorce, basic maintenance, residence, Class I).
This set adds the expert depth a family-law practitioner would ask for:

- Maintenance: arrears enforcement as execution/recovery, interim pendente
  lite (HMA s.24), past maintenance, and alimony vs maintenance as a
  discretionary quantum, not a formula.
- HAMA nuance: who is entitled under s.18/19/20/21/22, and s.25 alteration
  on changed circumstances.
- Dowry and stridhan: dowry harassment read as cruelty (HMA s.13), Dowry
  Prohibition Act civil remedy, 498A cruelty vs dowry distinction, stridhan
  as the woman's sole property.
- PWDV depth: right to residence vs ownership (s.17/19, shared household),
  monetary relief including interim (s.20, Magistrate).
- Custody: welfare factor checklist, grandparents vs parents (welfare decides,
  parents do not win by default).
- Marriage: legitimacy of children of void marriages (HMA s.16), restitution
  of conjugal rights (s.9).
- Succession: Class I daughters equal to sons, will (s.30) displacing
  intestate succession for property it covers.
- Adoption: unmarried woman under HAMA s.11 with conditions.
- Personal law: Special Marriage Act notice/objection (ss.5-8), triple talaq
  void under the Muslim Women (Protection of Rights on Marriage) Act 2019
  s.3/4, Christian (Divorce Act s.10), Parsi (1936 Act s.32/33), interfaith
  via Special Marriage Act.
- Scope traps: three new out-of-scope variants (RTI notice, landlord deposit,
  motor vehicle challan) with `must_redirect: True`, distinct from the
  existing `oos-rti-en`, `oos-landlord-en`, `oos-motor-en`.

Each entry keeps the `golden_qas.py` shape: `id`, `lang`, `persona`, `query`,
`must_include_any`, `must_include_terms`, `must_not`, `min_confidence`, `note`,
plus the optional `must_include_any_terms`, `must_include_terms_any_of`,
`must_redirect`, `must_ask_any`, `must_note_special_act` where the original set
uses them.

### Language mix

- English: 28
- Hindi-first: 4 (`maintenance-arrears-escalation-hi`, `custody-welfare-hi`,
  `dowry-harassment-hi`, `stridhan-hi`)
- Kannada-first: 4 (`interim-maintenance-kn`, `pwdv-residence-kn`,
  `custody-welfare-kn`, `succession-daughters-kn`)
- Hinglish: 3 (`pwdv-monetary-hinglish`, `adoption-unmarried-hinglish`,
  `maintenance-past-hinglish`)

Hindi and Kannada entries are written first in that language, not translated
English. Terms like भरण-पोषण/मेहनाना and ಭರವಸೂ are the words a person would
actually use.

### Persona voices

Short, realistic, varying by age, city, religion, and urgency. Examples:
a frightened first-time asker, a grandmother in a custody dispute, a
shopkeeper who got an RTI notice, a law intern asking about 498A. No textbook
phrasing. Queries are how a person types, not how a lawyer drafts.

### Expert checks baked in

- Every entry names a real section in `must_include_any`. A missing section
  is a fail even if the prose sounds helpful.
- `must_not` blocks the known failure modes: formulaic alimony, "mother
  always wins", ownership needed for residence, HMA for Christian/Parsi/Muslim
  questions, fixed maintenance forever, parents always winning custody.
- `must_redirect` entries must redirect out of scope and must not leak family
  law terms.
- The triple talaq entry expects the 2019 Act, not a general talaq answer from
  the Dissolution of Muslim Marriages Act, 1939.

### VERIFIER_MUTATIONS

20 pairs. `grounded_draft` says only what the passages support; `mutated_draft`
changes one fact (number, section, act, condition, classification, standard,
ownership). `mutation_type` names the kind of change and `why_it_must_fail`
explains the error. Run a verifier against both: it must accept grounded and
reject mutated.

### RETRIEVAL_EXPECTED

20 queries, each with `expected_act` and `expected_section`. Use to score
retrieval: a hit counts when the returned passages include the expected act
and section. Covers HMA, PWDV, HAMA, HSA, Special Marriage Act, Divorce Act,
Parsi Act, and Dissolution Act.

## Usage

```python
from report.dataset.golden_expanded import GOLDEN_EXPANDED, VERIFIER_MUTATIONS, RETRIEVAL_EXPECTED
```

Same runners as `golden_qas.py` apply; the fields are compatible.
