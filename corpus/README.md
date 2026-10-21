# Curated corpus

Hand-authored or hand-verified chunks that no download produces.

These live here, not in `data/`, because `data/` is gitignored — it holds
downloads and PDFs that anyone can re-fetch. Anything in this folder is a
correction we made by hand, and a fresh clone needs it to reproduce the
knowledge base.

## amendments.jsonl

Two notices for the mutual-consent divorce provisions:

- `Section 28, Special Marriage Act 1954`
- `Section 13B, Hindu Marriage Act 1955`

### What these notices are for

They put the operative timing in one passage, with the case-law rule on waiver
that the bare text does not carry. Section 28(1) and section 13B(1) require one
year of living separately. Section 28(2) and section 13B(2) put the second
motion no earlier than six months and no later than eighteen months after the
petition. The six-month period is directory and may be waived under
`Amardeep Singh v. Harveen Kaur` (2017) 8 SCC 746.

Those periods were last fixed by the **Marriage Laws (Amendment) Act, 1976
(Act 68 of 1976)**, in force 27 May 1976: section 29 for the Special Marriage
Act, section 7 for the Hindu Marriage Act. No later amendment has changed them,
and the consolidated text in the index is the text in force.

An earlier version of this file claimed a **Special Marriage (Amendment) Act,
2018 (Act 2 of 2019)** in force 1 June 2019, and said the indexed text was
pre-amendment. That Act does not exist. Act 2 of 2019 is the National Council
for Teacher Education (Amendment) Act, 2019. The only Special Marriage
(Amendment) Bill of 2018 was a private member's bill on section 4 (age of
marriage), never passed. Section 28A of the Special Marriage Act is not in
force either: the Marriage Laws (Amendment) Bill that would have inserted it
lapsed in 2014. The false claim made the agent deny a correct six-month answer.

### A notice is evidence, not an instruction

A notice is indexed and retrieved as a passage, and the verifier reads it as a
claim about the law. Write facts about the law, quotations and figures. Never
write a command aimed at the model or the reader: no "Do not state ...", no
"tell them ...", no "Name the amending Act in the answer", no "be careful to
...". An instruction inside a passage is read as evidence, and it becomes a
claim that the statute contradicts.
`api/tests/test_amendment_notices.py` fails the build on those patterns.

### Why they are chunk `kind: amendment_notice`

Measured on the live index: the notice ranks **first** for a bare timing query
(0.897), but the planner anchors every query with an Act name, and doing so
pushes the notice out of the **top 16**. So it is fetched by a payload filter
rather than by relevance — a correctness rule cannot depend on vector
similarity.

Requires keyword payload indexes on `act`, `section` and `kind`:

```
PUT /collections/law_saathi/index
{"field_name": "kind", "field_schema": {"type": "keyword"}}
```

### Ingest

```
.venv/bin/python api/scripts/ingest.py --jsonl corpus/amendments.jsonl
```

Idempotent — point IDs are derived from act + section + chunk index, so
re-running updates the existing points in place.

### The guard caveat

`apply_amendment_guard()` appends a caveat to any answer that quotes a duration
while an amendment notice is in evidence. The caveat has to agree with the
notices. One that calls the indexed text pre-amendment, or sends the reader
elsewhere for the current figures, contradicts them and gets a correct answer
rejected.
