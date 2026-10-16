# LawSaathi

Multilingual agentic AI legal support for family law (EN/HI/KN). See `docs/initial-plan.md`, `docs/stack.md`, `CONTEXT.md`.

**Live:** https://law-saathi.vercel.app

The API has no stable public hostname. Its address lives in the Vercel
production env as `FASTAPI_URL` (`cd web && npx vercel env pull`). Nothing else
in this repo needs it, because the browser never talks to the API directly.

## Corpus (law data we use)

| Source | Link | What we take from it | Size |
| ------ | ---- | ---- | ---- |
| `vaquill/open-india-law` (gated, HF token) | https://huggingface.co/datasets/vaquill/open-india-law | Only `in_central_legislation.parquet`, **streamed row by row** (never the ~54GB full dump). Per row we keep `text` / `title` / `section` / `lang` / `page` / `chunk_id` / `source_url` / `act_status`, for rows whose title matches a family-act alias and whose status is not `repealed` | 424 in-force section rows → `data/corpus/open-india-law-family-acts.jsonl` (729KB, gitignored) |
| `enerscript/MARRIAGEACT` | https://huggingface.co/datasets/enerscript/MARRIAGEACT | The 4 bare-act `.txt` files (HMA 1955, SMA 1954, Indian Christian Marriage Act 1872, Prohibition of Child Marriage (Amendment) Bill 2021). Plain full-Act text, no section column — we recover sections ourselves | 3,915 rows / 246KB → `data/corpus/marriageact_raw/` (gitignored) |
| India Code | https://www.indiacode.nic.in | **Not bulk-downloaded.** Used as the citation of record: the row's `source_url` and the act-PDF `mirror_url` are copied into every chunk payload. Act PDFs (`--pdf "path:Act Name"`) and scraped pages (`--url "url:Act Name"`, Firecrawl) are ingested on demand |
| `corpus/amendments.jsonl` (hand-written) | this repo | Two editorial `kind: amendment_notice` chunks for SMA s.28 and HMA s.13B. India Code still publishes the **pre-2018** "living separately for one year" text, so no dataset swap can fix it | 2 chunks |

Act PDF handles currently referenced in payloads, e.g.
https://www.indiacode.nic.in/handle/123456789/17272 (HMA),
https://www.indiacode.nic.in/handle/123456789/1387 (SMA).

### Nothing goes into Qdrant raw

Every source passes through `api/app/ingest.py` first. The dataset is never
embedded as-is:

1. **Filter at download** — `api/scripts/download_corpus.py` streams the
   parquet, drops non-family rows and repealed rows (`matching_act`), and
   writes JSONL. The full dump is never fetched.
2. **Filter again at parse** — `is_enacted_law()` rejects anything whose Act
   name contains `bill`, `draft`, `ordinance`, `lok sabha`, … This is what
   keeps the Child Marriage (Amendment) Bill out of the index.
3. **Section-aware chunking** — `split_sections()` finds `Section N` /
   numbered bare-act headings, then `chunk_text()` slides a 1500-char window
   with 200-char overlap, preferring sentence boundaries. Two sections are
   never merged into one chunk.
4. **Deterministic IDs** — `stable_point_id()` is `uuid5` over
   `act|section|chunk_index|uid`, so re-running updates points in place.
5. **Payload enrichment** — `act`, `section`, `lang`, `page`, `source`
   (`source_url` appended), `kind` are stored so retrieval can filter on them.
6. **Embedding last** — `QdrantStore.upsert_texts()` ships **raw text** as a
   `{"text": ..., "model": ...}` Document; Qdrant Cloud embeds it with
   `intfloat/multilingual-e5-small` (384-dim) and applies the
   `passage:`/`query:` prefixes. Nothing is embedded locally.
7. **Bookkeeping** — point IDs are mirrored into Neon `ingested_chunks`.

The Acts that carry the product, as they stand in the live collection (counted
2026-10-15): Hindu Marriage 1955 (57), Special Marriage 1954 (98), Hindu
Adoption & Maintenance 1956 (42), Hindu Succession 1956 (65), Guardians & Wards
1890 (75), Domestic Violence 2005 (58), Indian Divorce 1869 (106), Indian
Christian Marriage 1872 (121), Parsi Marriage & Divorce 1936 (78), Foreign
Marriage 1969 (56), Family Courts 1984 (31), Parents & Senior Citizens 2007
(45).

The collection is much larger than the family-law slice: **8,852 points**, of
which 1,385 are `kind: repealed_statute` (kept for history, never retrieved) and
2 are hand-written amendment notices. The rest is tagged with a `topic` on
ingestion — `civil_procedure` (1,896, mostly the Code of Civil Procedure 1908),
`criminal` (1,468), `evidence`, `succession`, `property`, `children`, and so on.
Only the family-law topics are in scope; see `AGENTS.md` → Open items for the
two consequences of the wider collection that are still open.

The golden eval set in `api/eval/golden_qas.py` was seeded from questions in
`steamed-potatop/indian-family-law-data`
(https://huggingface.co/datasets/steamed-potatop/indian-family-law-data) and
then rewritten to assert a specific governing section. It is an eval set — it
is never ingested into Qdrant.

Vectors live in Qdrant Cloud collection `law_saathi` (e5-small, 384 dims);
Neon `ingested_chunks` mirrors every point ID (ADR-0004). Re-ingest:
`api/scripts/download_corpus.py` then `api/scripts/ingest.py --jsonl ... --text-dir ...`.

## Languages (EN/HI/KN)

**There is no language setting, and that is deliberate.** The script of the
question decides the language of the answer, on both sides of the wire:

- `agent.detect_lang()` reads the question's script and ignores the caller's
  hint. A stored preference used to win, which meant a user who had once picked
  Hindi got their English question answered in Hindi — and was left convinced
  their own words were in the wrong language.
- The server reports the language it actually wrote in, as `lang` on the ask
  response. "Read aloud" uses that rather than a guess, so a Kannada answer is
  spoken by a Kannada voice.

Hinglish ("shadi ke liye umar") is detected as Hindi.

### How a non-English question is answered

1. **The question is read in the reader's own words.** It is embedded as written
   and searched. e5-small is multilingual, so a Hindi or Kannada question does
   match English statute text at the level of *topics*.
2. **The question is also pivoted to English** and searched. This is the half
   that is not optional: nothing in a non-English string says "dowry", so raw
   Hinglish and Kannada went to the Christian Marriage Act and the Succession
   Act instead. Measured on the live collection — 5 questions × 4 languages,
   scored on whether the governing Act came back in the top 8: the reader's own
   words alone got 15/20 (7/20 at rank 1), the English pivot 20/20 (13/20 at
   rank 1). Both result sets are merged, so a translation that drops a term
   cannot drop the section with it.
3. **The answer is written once, in English**, grounded in the sections that
   were retrieved, and checked against them.
4. **The answer is then rewritten in the reader's language** — not translated.
   A translator carries the source's difficulty across intact; a rewriter is
   given the everyday word for each legal term (maintenance = मासगी, not
   "maintenance"), is told to say it the way a person would say it out loud,
   and cannot invent anything because it only re-says a verified draft.
   Citations, Act names, section numbers and every number stay as they are.
   If the rewrite comes back empty, looping, half-finished, in the wrong script,
   or with English words left in Latin letters inside Devanagari, the English
   answer ships instead.

### The reasoning is in the reader's language too

"How Saathi worked this out" and the source tags are localised the same way, so
a Hindi reader can see which Act was chosen, that a Bill was set aside, or that
the answer carries a caution. Act names and section numbers stay in English —
they are the citation, and a translated citation cannot be checked.

### Streaming and latency

- **Step-level SSE streaming is active:** Every intermediate agent step ("How Saathi worked this out" / "Working on it…", intent detection, tool searches, verification) streams live over Server-Sent Events as it happens so the user sees live progress instead of a blank spinner.
- **The verified answer streams too:** once the verifier has passed, the answer goes out as `answer` events and fills the card as it arrives. Measured: first step ~1.4 s, first answer text ~11.4 s, complete ~12.4 s.
- **Model tokens are deliberately *not* streamed during drafting.** LawSaathi runs a strict **legal verifier** and a **native-language rewriter** after drafting; streaming tokens before the verifier approves could display legal hallucination or unverified text that would later be rejected and retracted. Nothing reaches the browser until the verifier has passed.
- The answer pacing (`LAWSAATHI_ANSWER_CHUNK_DELAY_MS`, default 22 ms per chunk) is presentation only. Set it to `0` for the whole answer at once.

Full decisions: [ADR-0009](docs/adr/0009-english-pivot-language-pipeline.md),
[ADR-0011](docs/adr/0011-pivot-stays-native-rewrite.md),
[ADR-0012](docs/adr/0012-readers-language-and-a-talking-answer.md),
[ADR-0013](docs/adr/0013-stream-the-verified-answer.md).

## Page weight

The illustrations are exported at 2x the size the layout draws them, as WebP, by
`scripts/export_web_assets.py` (the second half of `prep_assets.py`, which
crops and alpha-keys the raw art). Re-run it after changing any image.

Measured cold, median of 5 runs, compressed bytes on the wire in a production
build:

| Route | Before | After |
| --- | --- | --- |
| `/` | 863 KB | 757 KB |
| `/admin` | 819 KB | 706 KB |

Almost all of it was the favicon: `metadata.icons` pointed at the 512 px mark,
so every page load fetched 121 KB for a 16 px square in the tab. It is now a
quantised 32 px PNG at 917 bytes.

On the dev server, which has no image optimiser and therefore serves the source
files as they are, the difference is much larger — 1338 KB -> 1071 KB per page
on average, and `/chat` 1937 KB -> 1299 KB.

What is left is framework: ~950 KB of React and Next runtime on every route,
and ~86 KB of fonts. The fonts are three variable woff2 files; that is already
the floor.

## Run locally (T1 scaffold)

Backend:

```sh
cd /Users/nayan/Documents/projects/law_saathi
python3 -m venv .venv && .venv/bin/pip install -r api/requirements.txt
cp .env.example api/.env   # fill DATABASE_URL (Neon) + AUTH_SECRET when ready
DATABASE_URL="sqlite:///./lawsathi.db" .venv/bin/uvicorn app.main:app --app-dir api --reload
```

Frontend:

```sh
cd web && npm install && npm run dev   # needs API on :8000 (see FASTAPI_URL)
```

Auth: browser → Next.js (`/api/bff/*` verifies Neon Auth session) → FastAPI
(internal secret). Never call FastAPI directly from the browser.

Tests: `.venv/bin/python -m pytest api/tests -q` (315)
Golden routing: `.venv/bin/python api/eval/run_golden.py --offline` (18/18)

`--offline` matters. A live run measures whatever the providers are doing that
minute, and several of them are rate-limited, so a degraded run tells you about
the keys rather than about the product.

## Env

- `api/.env`: `DATABASE_URL` (Neon), `INTERNAL_API_SECRET` (same value as web)
- `web/.env.local`: `NEON_AUTH_BASE_URL` (Neon console → Auth → Configuration),
  `NEON_AUTH_COOKIE_SECRET` (generate), `INTERNAL_API_SECRET`, `FASTAPI_URL`

## Deploy

Web is Vercel (project `law-saathi`, root directory `web`). The API is Render
service `law_saathi` at `https://law-saathi.onrender.com`, from `render.yaml`
(Docker), and autodeploys on push to `main`.

Required Vercel production env: `FASTAPI_URL`, `INTERNAL_API_SECRET`,
`NEON_AUTH_BASE_URL`, `NEON_AUTH_COOKIE_SECRET`. Pull them with
`cd web && npx vercel env pull .env.production.local --environment=production`
— note it writes the values as empty strings, which is a CLI decryption
limitation, **not** an unset variable. Chat working is the real proof they are set.

```sh
cd web && npx vercel deploy --prod --yes
```

### The web deploy is manual, and that is a real gap

**Vercel has never been connected to this Git repository.** Every deployment has
been a manual `vercel deploy --prod`. Pushing to `main` does not build anything,
and there is no failure signal — the push just succeeds and production keeps
serving the old code.

This is not theoretical. The server-side voice fix (`677bbfb`, 2026-10-12) sat
undeployed until 2026-10-14, so production ran the old `webkitSpeechRecognition`
path for two days and voice failed on desktop with "Voice input failed (network)"
— the exact failure ADR-0005 predicts, since that API is a client for Google's
speech servers and an adblocker kills the request to Google.

To turn on auto-deploy, pick **one** of the two below. Running both means two
builds racing to alias the same domain.

#### Option A — Vercel GitHub App (recommended; no repo config)

1. Install the Vercel GitHub App for this repo: <https://github.com/apps/vercel>
2. Vercel project `law-saathi` → **Settings → Git** → connect
   `Kamal-Nayan-Kumar/law_saathi`, production branch `main`
3. Confirm **Root Directory** is `web`. It was `null` (repo root) until
   2026-10-14; left as-is, a git-triggered build looks for a Next.js app at the
   repo root, where there is none, and fails. Already set.

Then `.github/workflows/deploy-web.yml` should be **deleted**, so only one
thing deploys.

#### Option B — GitHub Actions (`.github/workflows/deploy-web.yml`)

Kept in the repo, manual-trigger by default so it cannot fight Option A. To make
it deploy on push instead, change its trigger to `on: push: branches: [main]`,
and do not connect the GitHub App.

Needs three repository secrets (Settings → Secrets and variables → Actions):

| Secret | Value |
| ------ | ----- |
| `VERCEL_TOKEN` | Vercel → Settings → Tokens → Create Token (scoped to this project) |
| `VERCEL_ORG_ID` | `team_IkaZrHgE3Fo0Z6TvAa5I5Z7o` |
| `VERCEL_PROJECT_ID` | `prj_D9WjsbU8cUQsezRjzslAfISH6CIN` |

It builds the app before deploying, so a commit that breaks the build fails in
GitHub instead of becoming a broken production alias — the advantage over
Option A.

#### Until one of them is set up

**Push, then verify**: `cd web && npx vercel ls`. If nothing new appeared within
a couple of minutes, deploy by hand with `npx vercel deploy --prod --yes`.

### Other deploy traps

- **Both API proxies set `maxDuration = 300`.** An agent run takes 60–90s. At
  Vercel's default function limit the `/api/stream` response is cut mid-answer,
  and the browser sees a stream that ends cleanly with no `done` event. Do not
  lower it, and do not remove the raised value from `/api/bff` either — that one
  surfaces as a bare "500" under the answer.

## Verify a deploy

Deploying is not the same as working. Both have shipped broken while the suite
was green, because the failures were in what the answer *said* and in what the
user *saw*, and neither is an assertion.

1. Sign in on the real site and ask something in ordinary words.
2. Read the whole answer, top to bottom. Cut-off passages, an empty numbered
   point, or a stray legal term are all defects the tests do not catch.
3. Ask one question and confirm you get one answer.
4. Collapse the chat history, and check what is left in the rail.

`bash scripts/dev.sh --observe` runs both servers locally and writes
`tmp/agent-runs.jsonl`; `EGO_SPACE=<id> .venv/bin/python scripts/shots.py chat
<tiny|phone|tablet|laptop|xl>` reports horizontal overflow per viewport.
