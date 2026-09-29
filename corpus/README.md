# Curated corpus

Hand-authored or hand-verified chunks that no download produces.

These live here, not in `data/`, because `data/` is gitignored — it holds
downloads and PDFs that anyone can re-fetch. Anything in this folder is a
correction we made by hand, and a fresh clone needs it to reproduce the
knowledge base.

## amendments.jsonl

Amendment notices for the two mutual-consent divorce provisions:

- `Section 28, Special Marriage Act 1954`
- `Section 13B, Hindu Marriage Act 1955`

### Why these exist

Every HF corpus reproduces the **pre-2018** consolidation, which still says the
couple must have been "living separately for one year or more". India Code
itself still publishes that text, so no dataset swap fixes it. Both sections
were amended by the **Special Marriage (Amendment) Act, 2018 (Act 2 of 2019)**,
in force 1 June 2019.

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

### What the guard does and does not claim

`apply_amendment_guard()` appends a caveat naming the amending Act. It
deliberately asserts **no replacement figure**: the amended text could not be
sourced from a primary source, and typing statutory text from memory into a
legal assistant is exactly the failure this project exists to prevent. If you
later obtain the gazette text, put the real figures here and drop the caveat.
