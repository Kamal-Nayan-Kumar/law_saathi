# ADR-0012 — the reader's language everywhere, and an answer that talks

Status: accepted (2026-10-15).

Amends [ADR-0009](0009-english-pivot-language-pipeline.md) and
[ADR-0011](0011-pivot-stays-native-rewrite.md). Re-measures nothing that those
already measured; it adds the decisions that came out of reading real Hindi and
Kannada answers on the deployed site.

## Context

The pipeline that existed on 2026-10-14 was: detect language → pivot the
question to English → retrieve and reason in English → **rewrite** the verified
answer natively (ADR-0011). Three complaints came from using it:

1. A non-English user could read the answer but not the *reasoning*. Every line
   under "How Saathi worked this out" was English, and so were the source tags.
   The person who asked cannot tell what was searched, which Act was chosen, or
   what was skipped.
2. Answers read as line-by-line translation in places — a clean English sentence
   with "maintenance pendente lite" arriving as a grammatical Hindi sentence
   containing it, or with `court`, `FIR`, `Act` left in Latin letters inside
   Devanagari text.
3. Length was fixed by a tone setting, not by the question. A one-line question
   ("what is the minimum age to marry?") got the same budget as a paragraph
   describing a marriage, a child and a beating.

And one hypothesis to settle: **"the embeddings are multilingual, so drop the
translation step."**

## Decision 1 — the pivot stays for search, and stops being the only search

The hypothesis is half right, and the half that is wrong is the half this
product lives in.

Measured on the live collection, 5 questions × 4 languages, scored on whether
the Act that actually governs the question came back in the top 8
(ADR-0011, unchanged):

| | in top 8 | at rank 1 |
| --- | --- | --- |
| reader's own words, no pivot | 15/20 | 7/20 |
| English pivot | 20/20 | 13/20 |

e5-small aligns *topics*, not *legal terms*. Nothing in a Kannada or Hinglish
string says "dowry", so those queries went to the Indian Christian Marriage Act
and the Indian Succession Act. Dropping the pivot would make the answer *wrong*,
not merely worse — the same class of error as citing a Bill.

What changed is that the pivot is no longer trusted alone. The reader's own
words are now searched as well, in the same retrieval round, and both result
sets are merged. So the multilingual model is doing real work — it is the
safety net for the exact case the pivot is bad at — while the pivot keeps the
precision the corpus needs. A translation that drops a term can no longer drop
the section with it.

## Decision 2 — the answer is written, never translated (restated, enforced)

Restated from ADR-0011 because the complaint that produced it came back. The
English draft is written, grounded and verified; the reader's answer is then
**rewritten** in their language against an everyday-word table
(`LANG_PLAIN_RULES`), not translated. This round adds four rules that were
missing:

- **Do not mirror.** The old instruction said "keep the structure", which is
  what produced line-by-line translation. The rewriter is now told to say it
  the way it would be said out loud, in whatever sentence order sounds natural,
  and is given one short worked example per language.
- **Right script.** Loanwords are fine in Hindi and Kannada; Latin letters
  inside Devanagari are not. `court` → कोर्ट, `FIR` → एफआईआर. This was the
  visible defect: Hindi answers carrying `court` and `Act` in the Latin
  alphabet.
- **Same citations, same facts.** Markers, Act names, section numbers, ages,
  periods and amounts stay exactly as the verified English draft has them.
- **Never worse than the fallback.** Empty, looping, mid-sentence, wrong script,
  or still English → the English answer ships instead. That was already true and
  stays true.

## Decision 3 — length follows the question, not a setting

`answer_length()` reads the question and returns one of `brief`, `normal`,
`full`:

- A question that asks for **one fact** — a number, a name, an age, a yes/no —
  gets a short answer. Padding it is what made a two-line question unreadable.
- A question that **describes a situation** with several facts (a marriage, a
  child, a beating, an amount) gets the fuller treatment: what the law says,
  what it means for them, what to do.
- Everything else gets the middle, which is what the old fixed budget was.

The tone setting still exists and still moves this; it no longer decides it
alone.

## Decision 4 — the reasoning is in the reader's language too

The step log, the "how it worked" detail and the source tags are localized:
`api/app/agent.py` now holds every trace line as a template with `en`/`hi`/`kn`
renderings, and the web client localises the panel's own chrome from the
language the server reported on the answer.

Two things deliberately stay in English:

- **Act names and section numbers.** They are the citation. "Hindu Marriage
  Act, Section 13B" is checkable; a translated version is not.
- **The passages themselves**, where they are quoted at all — same reason.

This is not localisation for its own sake. A Hindi speaker who cannot read the
step log cannot tell that a Bill was skipped, that the Acts had no answer, or
that the answer carries a caution. Those are the three things the panel exists
to say.

## Decision 5 — a follow-up is a continuation, not a new question

Follow-ups already carried history into retrieval (`carry_slots_from_history`,
`contextualize`). Two gaps are closed:

- The writing prompt is now told the question is a follow-up and must answer
  *this* question from the earlier turns **without restating them**, in one
  short acknowledgement at most. Repeating the whole previous answer is the
  failure mode a reader notices first.
- A vague follow-up is answered with what the conversation already established
  and ends with one targeted question. It never asks "what is this about?" to a
  person who has already explained themselves — the rule from ADR-0011
  Decision 4, now applied to the answer as well as the planner.

## Decision 6 — streaming is at step level; token level is not built

The SSE endpoint already streams every agent step as it happens, so a 10–20 s
run shows real progress instead of a spinner. The answer still arrives as one
`done` event, and that is deliberate: the answer is verified *after* it is
written, and streaming tokens that the verifier may then reject would mean
showing text we are about to withdraw. Token-level streaming is worth doing and
is not done — see `TO-DO.md`.

## Consequences

- One extra vector search per non-English act-search step. It is a server-side
  embedding call, no model tokens, no new vendor.
- Trace text now has a per-language table. A new trace line without a
  translation falls back to English rather than disappearing — the fallback is
  the old behaviour, so the cost of forgetting is the old defect, not a blank.
- More prompt text per run. The rewrite prompt carries a worked example per
  language; that is tokens, and it is the cheapest available fix for a
  line-by-line translation.
- The answer can still come back in English when every provider is in cooldown.
  That has always been true and is now stated in the step log in the reader's
  language, so it is visible instead of surprising.
