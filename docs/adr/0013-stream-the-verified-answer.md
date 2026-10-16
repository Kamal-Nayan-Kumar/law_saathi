# ADR-0013 — the answer streams, but only after the verifier has passed

Status: accepted (2026-10-16).

Narrows [ADR-0012](0012-readers-language-and-a-talking-answer.md) Decision 6,
which said token-level streaming was worth doing and not done.

## Context

The SSE endpoint streamed every agent step, and that worked: the intent line
lands in about 50 ms, so a reader knows the run has started. But the answer still
arrived as one `done` event after the last step. Measured on a real question,
the two were 17.8 s apart:

```
  1434ms  step  intent
  2469ms  step  planner
  7982ms  step  tools
  9662ms  step  reason
 10652ms  step  verifier   rejected the draft
 15597ms  step  tools      retry
 17816ms  step  response
 17825ms  done
```

So the screen sat still for eighteen seconds and then everything changed at
once. That is the same jolt step-level streaming was built to remove, happening
one act later.

## Decision 1 — model tokens are still not streamed, and the reason has not moved

ADR-0012's objection was that the verifier runs *after* the draft. A token stream
during `node_reason` would therefore show text that `node_verifier` may still
reject, and the user would watch legal hallucination arrive one word at a time
and then be withdrawn. Nothing has changed that. `LAWSAATHI_TOKEN_STREAM` does
not exist and this ADR does not add it.

## Decision 2 — the *verified* answer streams, in pieces

Once the verifier has passed and `node_response` has assembled the final text,
the answer goes out as `answer` events and fills the card on arrival.

Two things this buys. The reader starts following the answer a few hundred
milliseconds sooner, and the persistence — which opens its own session and
writes two rows — now happens *behind* text the user is already reading rather
than in front of it.

It is not a cosmetic trick: the chunking is a real transport decision, and the
text is fixed and approved before the first byte is sent.

## Decision 3 — the chunker is structural, and lossless

The one rule `chunk_answer` must never break is that **concatenating every
chunk returns the answer byte for byte.** The card fills from the pieces and is
then reconciled against `done`; if the two could differ, a reader would see one
answer and reopen the chat to find another.

So the split is on paragraph breaks, then line breaks, then words, and each
separator is emitted as its own chunk to rejoin in the right place. Splitting on
whitespace alone would cut `**bold` away from its closing `**` and leave the
reader watching literal asterisks for the length of a chunk.

Two tests hold this: one asserts the round-trip over a paragraph, a heading, a
bullet list and a blockquote; one asserts no chunk leaves a markdown marker
dangling. A third asserts the streamed text equals the persisted row.

## Decision 4 — the pacing is deliberate, and it is the weakest part

Chunks are emitted ~22 ms apart. Without that they all land in one frame and
there is nothing to see, which is the defect being fixed. It adds about half a
second to a typical answer.

This is the part to revisit first if anyone objects. It is presentation, not
information: `LAWSAATHI_ANSWER_CHUNK_DELAY_MS=0` removes it and the answer
simply arrives whole, as it did before. It should not be raised far above the
default — a paced stream that takes visibly longer than the unpaced one is
strictly worse than either.

## Consequences

- The step log is hidden once the text starts moving. Both together pushed the
  answer the user came for below the fold.
- The live card shows no Sources block, no "Read aloud" and no Thinking toggle.
  Those belong to the finished answer and arrive with `done`.
- Answer text is paced in wall-clock time, so it is slightly *slower* to be
  complete than it was. It is not slower to start being read, which is the thing
  that was wrong.

## What is still the slowest thing

Not the pages, and not the transport. The 17.8 s run above spent **7 s in a
verifier retry**, because the planner chose the Special Marriage Act and the
draft then cited section 17 of the Hindu Marriage Act — retrieval returned the
wrong Act, so the draft was guaranteed to fail. A second 5.5 s went to
`planner -> tools`.

Fixing the planner/retrieval mismatch is worth more than any of this ADR and is
not in it.