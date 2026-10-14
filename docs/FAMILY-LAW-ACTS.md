# Indian family law — the act inventory

Written before touching retrieval. The rule this document enforces: **the
corpus is derived from the list of laws, not the other way round.** `SCOPE.md`
currently describes what happened to land in Qdrant; this file describes what
family law in India actually consists of. Where the two disagree, this file
wins and the corpus gets fixed.

Column "in vaquill?" was measured against the real
`in_central_legislation.parquet` (26.5 MB, 74,484 rows) on 2026-10-12, not
guessed.

---

## 0. Verdict on the current corpus

Three findings, all measured against the live Qdrant collection, not inferred.

**There are no judgments in the vector DB.** The user's hypothesis was that
case law is polluting retrieval. It is not. Full scroll of
`collections/law_saathi`:

| Source | Points |
| --- | --- |
| `vaquill/open-india-law` (legislation) | 1292 |
| `enerscript/MARRIAGEACT` (bare acts) | 590 |
| Judgments / case law | **0** |

A regex sweep for `judgment|hearing|case no|petitioner|respondent|v. |at. |
counsel` over all 1882 texts returned 234 hits, every one of them a
false positive — statutory procedure sections that legitimately contain the
words "appeal", "petition", "heard". The retrieval problem is real but it is
not case law. `SCOPE.md` §7 is right: there is no case law in this system.

**The collection is 65% out-of-scope material.** `SCOPE.md` §2 promises 7
acts. The live index holds:

| Points | Act | In SCOPE.md? |
| --- | --- | --- |
| 517 | Indian Succession Act, 1925 | no — and 469 of its rows are probate/administration procedure, not the intestate-succession questions people ask |
| 354 | Special Marriage Act, 1954 | yes |
| 344 | Indian Christian Marriage Act, 1872 | yes |
| 168 | Hindu Marriage Act, 1955 | yes |
| 106 | Indian Divorce Act, 1869 | yes |
| 84 | Guardians and Wards Act, 1890 | yes |
| 78 | Parsi Marriage and Divorce Act, 1936 | no |
| 65 | Hindu Succession Act, 1956 | yes |
| 58 | Protection of Women from Domestic Violence Act, 2005 | yes |
| 54 | Hindu Adoption and Maintenance Act, 1956 | yes |
| 66 | 7 Muslim/Dowry acts | partly |

Indian Succession Act alone is 27% of the index. A custody question competes
with probate procedure for a slot in the top-k. That is a much better
explanation for weak answers than "judgments got in".

**The index has stale duplicates.** README says 1132 points; the collection
holds 1882. Nothing was ever deleted, and point IDs are salted with
`chunk_id`/`source_url`/filename (`ingest.stable_point_id`), so any change to
an alias or a source file orphans the old points instead of replacing them.
The Indian Christian Marriage Act is stored under two different `act` strings
(`THE INDIAN…` 223 points, `The Indian…` 121 points) with 303 distinct
section/chunk pairs for an Act of ~48 sections.

---

## 1. What "family law" contains in India

Nine clusters. The seven acts in `SCOPE.md` cover clusters 1, 3, 4, 5 and part
of 6. Clusters 2, 7, 8 and half of 9 are missing entirely.

### 1.1 Marriage — validity, ceremony, registration

| Act | Governs | Key sections | in vaquill? |
| --- | --- | --- | --- |
| Hindu Marriage Act, 1955 | Hindu marriage, void/voidable, registration | 5–8, 9–11, 12, 13, 13B, 24, 25 | **yes** (50) |
| Special Marriage Act, 1954 | inter-caste, inter-religious, foreign nationals | 4, 5, 6, 7, 9, 10, 11 | **yes** (80) |
| Indian Christian Marriage Act, 1872 | Christian marriage, registration | 7, 8, 9, 10, 11, 24, 25 | **yes** (110) |
| Parsi Marriage and Divorce Act, 1936 | Parsi marriage, registration | 3, 4, 5, 11, 12 | **yes** (74) |
| Foreign Marriage Act, 1969 | marriages outside India | 3, 4, 5, 6 | **yes** (47) |
| Anand Marriage Act, 1909 | validation of certain Hindu marriages | 2, 3, 4 | yes (6) — historical, low value |
| Arya Marriage Validation Act, 1937 | validation of Arya marriages | 2, 3 | yes (1) — drop |
| Hindu Minority and Guardianship Act, 1956 | minority, guardian of Hindu minor | 2, 3, 6, 7, 11 | yes (14) |
| Births, Deaths and Marriages Registration Act, 1886 | registration machinery, s.3 proviso | 3 | yes (44) |
| Registration of Births and Deaths Act, 1969 | birth/death certificates, legitimacy | 5–17, 26 | yes (46) |
| Marriage Laws (Amendment) Act, 2007 | inter-caste marriage in Maharashtra; s.3 accommodation booths | 3, 4 | **ABSENT** |

### 1.2 Muslim personal law — the largest hole

Muslim family law is **mostly uncodified**; it is Shariat applied by the
courts. That is a product constraint, not a dataset one, and it has to be
stated in the answer rather than faked with a citation.

| Act | Governs | in vaquill? |
| --- | --- | --- |
| Muslim Personal Law (Shariat) Application Act, 1937 | s.3 extends Shariat to Muslims; codifies the framework | **yes** (7) |
| Dissolution of Muslim Marriages Act, 1939 | khula, talaq, divorce by consent, polygamy bars | **yes** (8) |
| Muslim Family Laws Act, 1963 | **maintenance for Muslim wives, children and parents**; custody; dower | **ABSENT** ← critical |
| Muslim Women (Protection of Rights on Divorce) Act, 1986 | iddat, khula, divorce registration | **yes** (7) |
| Muslim Women (Protection of Rights on Marriage) Act, 2019 | minimum age for Muslim girls, registration | **yes** (7) |
| Muslim (Guardianship and Maintenance) Act, 1926 | guardian appointment, maintenance | **ABSENT** |
| Muslim Inheritance (Succession to Property) Act, 1926 | intestate succession among Muslims | **ABSENT** |

`Muslim Family Laws Act, 1963` is the statute that answers "my husband has not
paid maintenance, I am Muslim". Without it the agent reaches for the Hindu
Adoption and Maintenance Act, which does not apply — the exact failure
recorded in `ingest.py` comments.

### 1.3 Divorce and judicial separation

Covered by the marriage Acts above (HMA 13, 13B, 13B(2), 14; SMA 23–27;
ICMA 16–19; PMDA 13–19; DMMA 2, 7), plus:

| Act | Governs | in vaquill? |
| --- | --- | --- |
| Indian Divorce Act, 1869 | divorce for Christians in India | **yes** (95) |
| Special Marriage (Amendment) Act, 2018 | **the mutual-consent rewrite; created SMA s.28A** | **ABSENT** |
| Special Marriage (Amendment) Act, 2021 | adultery, no maintenance to the erring spouse | **ABSENT** |

`corpus/amendments.jsonl` exists precisely because these two are absent — the
dataset carries the pre-2018 SMA text. Hand-written notices are a workaround
for a missing source, not a fix.

### 1.4 Custody and guardianship

| Act | Governs | Key sections | in vaquill? |
| --- | --- | --- | --- |
| Guardians and Wards Act, 1890 | guardian appointment, custody, minor's property | 7, 11, 12, 13, 14, 17, 19, 20, 21 | **yes** (67) |
| Hindu Adoption and Maintenance Act, 1956 | adoption | 2, 3, 4, 5, 6, 9, 11 | **yes** (32) |
| Hindu Minority and Guardianship Act, 1956 | natural guardian | 6, 7, 11 | yes (14) |
| Family Courts Act, 1984 | **which court hears it; 2nd-look at an order passed by another court; counselling; s.10 waiver of monetary rights** | 4, 5, 6, 9, 10, 13, 14, 19, 20 | **yes (23) — but not in the alias list** |
| Juvenile Justice (Care and Protection of Children) Act, 2015 | child protection, JJBs, adoption, alternative placements | 2, 4, 15, 29, 30, 33, 34 | **yes (168) — not in the alias list** |

Adoption for Christian and Muslim children has **no dedicated statute** — it
runs through JJBA 2015 or personal law. The answer must say that rather than
cite HAMA.

### 1.5 Maintenance and financial relief

| Act | Governs | in vaquill? |
| --- | --- | --- |
| Hindu Marriage Act, 1955 s.24–25 | maintenance pendente lite, permanent maintenance | **yes** |
| Special Marriage Act, 1954 s.25, 25A | maintenance pendente lite, permanent maintenance | **yes** |
| Hindu Adoption and Maintenance Act, 1956 s.11–19 | maintenance of wife, children, parents; s.18–19 orders | **yes** |
| Code of Civil Procedure, 1908 s.9, 10, 24, 25, 125 | **right to sue, interim maintenance, s.125 maintenance** | **yes (1554) — not in the alias list** |
| Limitation Act, 1963 | limitation on maintenance/custody suits | **yes (72) — not in the alias list** |
| Maintenance and Welfare of Parents and Senior Citizens Act, 2007 | maintenance for aged parents | **yes (37) — not in the alias list** |
| Maintenance Orders Enforcement Act, 1921 | enforcing maintenance orders | **yes (20) — not in the alias list** |
| Legal Services Authorities Act, 1987 s.12(c) | **free legal aid to women in family disputes** | **yes (50) — not in the alias list** |

CPC s.125 is the provision most family-law litigants actually run on, and it
is absent from the index.

### 1.6 Domestic violence and dowry

| Act | Governs | in vaquill? |
| --- | --- | --- |
| Protection of Women from Domestic Violence Act, 2005 | SH/SL, protection order, residence, monetary relief, custody, compensation | **yes** (47) |
| Dowry Prohibition Act, 1961 | dowry definition, s.3 penalty, s.4 burden, s.5 Dowry Prohibition Officers | **yes** (15) |
| Protection of Civil Rights Act, 1955 | untouchability — **directly relevant to inter-caste marriage** | **yes (48) — not in the alias list** |
| Bharatiya Nyaya Sanhita, 2023 s.80 | the successor to IPC s.498A (dowry death / cruelty) | **yes (469) — not in the alias list** |
| Bharatiya Nagarik Suraksha Sanhita, 2023 | arrest, s.41-L protection officer, bailing | **yes (827) — partial** |

### 1.7 Succession and inheritance

| Act | Governs | in vaquill? |
| --- | --- | --- |
| Hindu Succession Act, 1956 | intestate succession, s.8 daughters, s.15 will | **yes** (53) |
| Hindu Succession (Amendment) Act, 2005 | **s.6 — daughters as coparceners; rewrote s.15** | **ABSENT** |
| Indian Succession Act, 1925 | intestate succession + probate for Christians, Parsis, domiciled persons | **yes** (469) |
| Indian Christian Succession Act, 1926 | intestate succession for Christians domiciled outside India | **ABSENT** |
| Indian Succession Act, 1865 / Parsi Succession and Administration Act, 1865 | repealed by the 1925 Act | repealed rows present |
| Transfer of Property Act, 1882 | property, gift, partition | **yes** (212) — out of SCOPE, property law |
| Hindu Disposition of Property Act, 1916 | converts joint Hindu family property to tenancy in common | yes (6) — niche |
| Hindu Wills Act, 1870 / Indian Succession Act, 1865 | repealed | repealed |

### 1.8 Child protection and child marriage

**The dangerous one.** `in_central_legislation.parquet` contains the
**Prohibition of Child Marriage Act, 2006** (25 rows, marked `in_force`). That
Act was passed but **never brought into force** — the governing statute is the
**Child Marriage (Prohibition) Act, 1929**, which is **ABSENT** from the
dataset entirely.

This is exactly the failure `is_enacted_law()` was built for, and that filter
will not catch it: "Prohibition of Child Marriage Act" contains none of
`bill|draft|ordinance|proposed`. The 1929 Act must be ingested from India
Code and the 2006 Act must be excluded explicitly.

| Act | Governs | in vaquill? |
| --- | --- | --- |
| Child Marriage (Prohibition) Act, 1929 | **minimum age 18/21, void marriages, registration** | **ABSENT** ← critical |
| Juvenile Justice (Care and Protection of Children) Act, 2015 | child protection | yes (168) |
| Commissions for Protection of Child Rights Act, 2005 | NCPCR | yes (43) |
| Protection of Children from Sexual Offences Act, 2012 | child sexual offences | yes (57) — adjacent |
| Child and Adolescent Labour (Prohibition and Regulation) Act, 1986 s.23A | bars marriage for adolescent workers | yes (6) — niche |
| Right of Children to Free and Compulsory Education Act, 2009 | age 6–14, custody implications | yes (49) — adjacent |

### 1.9 Procedure — the layer the index is entirely missing

| Act | Why it matters | in vaquill? |
| --- | --- | --- |
| Family Courts Act, 1984 | jurisdiction, s.10(2) second-look, counselling | **yes (23), not aliased** |
| Code of Civil Procedure, 1908 | s.9/10, 24, 25, 125 | **yes (1554), not aliased** |
| Limitation Act, 1963 | time limits | **yes (72), not aliased** |
| Legal Services Authorities Act, 1987 | s.12(c) free legal aid | **yes (50), not aliased** |
| Arbitration and Conciliation Act, 1996 | domestic arbitration, mediation | yes — not aliased |

---

## 2. The dataset plan

### 2.1 Do not swap the dataset — the dataset is mostly fine

The problem is not that `vaquill/open-india-law` is the wrong source. It is the
right source: official government sources, section-level, with
`act_status`, `in_force`, `source_url`, `mirror_url`, `legal_subject`,
`provision_type` — exactly the fields a legal corpus needs. 74,484 central
sections in a 26.5 MB file that downloads in seconds.

Search of Hugging Face for alternatives turned up nothing comparable for
Indian primary law:

| Dataset | Verdict |
| --- | --- |
| `vaquill/open-india-law` | **keep** — the only section-level official corpus |
| `enerscript/MARRIAGEACT` | **drop** — 4 files, all text already in vaquill, caused the duplicate-act bug, brought in a Bill |
| `steamed-potatop/indian-family-law-data` | eval only, never ingested |
| `KanoonGPT/indian-case-laws` | judgments; Apache-2.0, but vaquill is official and better |

The corpus is fixed by (a) rewriting the act list in `ingest.py`, (b) sourcing
the ~10 acts vaquill lacks from India Code directly, (c) dropping enerscript,
(d) rebuilding the collection from scratch.

### 2.2 What vaquill lacks, and where to get it

| Missing act | Why | Source |
| --- | --- | --- |
| Muslim Family Laws Act, 1963 | Muslim maintenance | India Code |
| Muslim (Guardianship and Maintenance) Act, 1926 | Muslim guardianship | India Code |
| Muslim Inheritance (Succession to Property) Act, 1926 | Muslim succession | India Code |
| Child Marriage (Prohibition) Act, 1929 | the real child-marriage statute | India Code |
| Hindu Succession (Amendment) Act, 2005 | daughters as coparceners | India Code |
| Special Marriage (Amendment) Act, 2018 | s.28A, the 2019 rewrite | India Code / gazette |
| Special Marriage (Amendment) Act, 2021 | adultery maintenance bar | India Code |
| Marriage Laws (Amendment) Act, 2007 | inter-caste, s.3 | India Code |
| Indian Christian Succession Act, 1926 | Christian intestacy abroad | India Code |
| Anand Marriage Act, 1909, Arya Marriage Validation Act, 1937 | historical validation | India Code (optional) |

India Code: https://www.indiacode.nic.in — every act has an HTML page and a
PDF. `ingest.chunks_from_firecrawl_url()` and `ingest.chunks_from_pdf()`
already exist for exactly this.

Note that vaquill carries **no amending Acts at all** — it is consolidated
text only. That is why `corpus/amendments.jsonl` was needed, and it means
every amendment consequence has to come from India Code or the gazette.

### 2.3 Two collections, not one

Judgments stay out of the statute collection permanently. If case law is ever
wanted, it goes in `law_saathi_cases`, from `in_supreme-court_judgments.parquet`
(3.7 GB) or the High Court files, filtered to family-law titles, and is only
consulted when the question is explicitly "has any court held / what did
judges rule". Mixing them is what the user suspected was happening, and the
architecture should make it impossible rather than merely absent today.

### 2.4 Rebuild, don't patch

`QdrantStore` has no delete. Given 1882 points of which ~65% is out of scope
plus 750 orphans, the fix is:

1. Create a **new collection** (`law_saathi_v2`) rather than mutate.
2. Ingest from a rewritten act list, from the local parquet — no re-download.
3. Drop enerscript.
4. Explicitly exclude the Prohibition of Child Marriage Act, 2006.
5. Cut Indian Succession Act to its intestate-succession sections (ss.33–93)
   and leave probate procedure out.
6. Point `QDRANT_COLLECTION` at v2, compare against the golden set, then
   delete v1.

---

## 3. Embedding model

Agreed direction, one caveat.

`sentence-transformers/all-minilm-l6-v2` is listed free on Qdrant Cloud
inference alongside `intfloat/multilingual-e5-small`, same 384 dimensions, so
the switch is a re-upsert and not a collection rebuild.
https://qdrant.tech/documentation/cloud/inference/

| | e5-small (current) | MiniLM-L6-v2 (proposed) |
| --- | --- | --- |
| Languages | 100+, incl. Hindi, Kannada | English only |
| Dim | 384 | 384 |
| Cost on Qdrant | free | free |
| Speed | slower | ~5x faster, 22M vs 118M params |
| Retrieval quality on EN legal text | good | good |

The reasoning holds: ADR-0009 is an **English-pivot** pipeline — non-English
input is translated to English before retrieval, so the embedder only ever
sees English statutory text and English queries. MiniLM is the right choice for
that.

The caveat: it makes the English pivot **load-bearing** rather than
defensive. `detect_lang()` currently classifies Hinglish as Hindi, and if a
Hinglish query reaches `search_text()` untranslated, e5-small degrades
gracefully and MiniLM degrades badly. So the switch must land together with a
hard guarantee that every non-English query is translated before it touches
Qdrant — a test that asserts no non-ASCII query string reaches
`search_text()`.

### Measured (2026-10-14, ADR-0011): the pivot is load-bearing even on e5-small

The premise above — that a good multilingual embedder makes the pivot optional
— was tested directly against the live collection. 5 questions × 4 languages,
same search run on the raw text and on the Groq translation, scored on whether
the Act that actually governs the question appeared in the top 8:

| | top-1 correct | in top 8 |
| --- | --- | --- |
| raw query, no pivot | 7/20 | 15/20 |
| English pivot | 13/20 | 20/20 |

So the guarantee asked for above is needed regardless of which embedder ships,
and dropping the pivot to "simplify" the pipeline would halve top-1 retrieval
accuracy. The corpus is English; the queries are not; something has to bridge
them, and measurement says it should be the pivot, not the embedder.

---

## 4. Order of work

1. Rewrite the act list in `ingest.py` from §1 above, with explicit
   exclusions (Child Marriage Act 2006; Indian Succession Act probate
   sections).
2. Drop enerscript from the ingest path.
3. Scrape the §2.2 gaps from India Code into `corpus/india_code/*.txt`.
4. Build `law_saathi_v2`; compare retrieval against `api/eval/golden_qas.py`.
5. Switch to MiniLM-L6-v2 with the non-ASCII-query guard test.
6. Rewrite `SCOPE.md` §2 from this inventory.