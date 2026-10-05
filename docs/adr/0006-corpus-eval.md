# ADR-0006 — Curated corpus + Ragas eval on LangSmith

Status: **accepted, partly delivered** — see "What actually shipped".

Context: No single trusted "family law" dump; random Kaggle data risks wrong jurisdiction; verified-answers claim needs proof.

Decision: Corpus = `vaquill/open-india-law` filtered to 6 family acts + `enerscript/MARRIAGEACT` + India Code PDFs + 20–30 curated judgments. Eval = 30 golden Q&As (10/lang, seeded from `steamed-potatop/indian-family-law-data`), Ragas faithfulness + relevancy + context recall, tracked in LangSmith. Langfuse dropped — LangSmith alone is enough for solo.

Consequences: Manual curation + golden-set writing up front; every retrieval change re-runs eval.

## What actually shipped

The corpus shipped. The judged eval did not.

**Corpus** — 1,134 chunks across 8 Acts plus 1 Bill. No curated judgments were
added, so there is still no case law: the answer to "how has this particular
judge ruled" is out of reach, and `SCOPE.md` §7 says so. Two entries are wrong
in the direction of over- and under-scoping:

- **Indian Christian Marriage Act, 1872** is 223 chunks, the second-largest
  source, and appears in no plan document. Christian marriages in India are
  governed by it. `SCOPE.md` lists seven Acts and omits this one.
- **Prohibition of Child Marriage (Amendment) Bill, 2021** is 22 chunks from
  the non-official `enerscript` dataset. A Bill is not law. It is filtered from
  retrieval by `is_enacted()`, but it remains in the vector store.

**Eval** — two golden sets exist and they are easy to confuse:

| File | Count | Usable |
| --- | --- | --- |
| `api/eval/golden_qas.py` | 17 | yes — `run_golden.py`, `run_stub.py` |
| `data/eval/golden_qas.json` | 30 | no — `data/` is gitignored, so it is in no repository |

**Ragas is not installed.** `import ragas` fails. `api/eval_t10.py` guards the
import and prints a notice; `eval/ragas_eval.py`, referenced in several
docstrings, was never written. The 30-questions-per-language design was reduced
to 17 total across three languages.

**LangSmith is wired but unverified** — hooks exist, nothing has confirmed a
trace arrives. The local JSONL log in `api/app/obs.py` works with no key and is
what development actually uses.

The deliberate departure: `run_golden.py` checks what can be checked
deterministically — right language, right section cited, nothing confidently
wrong — rather than asking a model to grade prose. Those checks cannot be
talked into passing. Judged metrics remain the gap, and `TO-DO.md` F5 records
it as partial rather than done.
