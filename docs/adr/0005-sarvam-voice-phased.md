# ADR-0005 — Sarvam voice now, LiveKit live-talk Phase 2

Status: **superseded twice.** The original push-to-talk plan was replaced by
browser Web Speech, which was then replaced by server-side transcription — see
"What actually shipped" and "What shipped instead" below.

Context: Solo build; both dictation + realtime in one go is high risk; ElevenLabs weak on Kannada + costly.

Decision: MVP = Sarvam STT/TTS push-to-talk only; LiveKit realtime behind a flag as Phase 2; ElevenLabs dropped.

Consequences: Viva demos dictation mode; live-talk is a tracked follow-up, not a broken half-feature.

## What actually shipped

Browser Web Speech in `web/lib/voice.ts`. No Sarvam key was available, and
`SpeechRecognition` / `speechSynthesis` seemed to cover the MVP: no API key,
nothing leaving the device.

This was wrong, and the reason is worth recording so it is not repeated:

- `SpeechRecognition` is not speech recognition. It is a client for Google's
  speech servers. That works on Android Chrome and fails on desktop Chrome
  with `network`, because the request to Google is exactly what an adblocker,
  Brave Shields or a filtered network kills. Voice input worked on a phone and
  failed on a laptop for the same user — the worst split for an accessibility
  feature.
- It also ended an utterance on silence. Pausing to think was indistinguishable
  from finishing, so the first clause of a sentence was dispatched as the
  question.
- "Nothing leaves the device" was true only for TTS. STT audio was being sent
  to Google on every utterance, which is the more sensitive half.

## What shipped instead

The browser only records (`MediaRecorder`); transcription happens on our API.
**Sarvam SAAR first, Groq Whisper as fallback** — `api/app/voice.py`,
`POST /voice/transcribe`. Read-aloud stayed on `speechSynthesis`, which was
never the problem.

Language is auto-detected by both providers rather than pinned.

Consequences to be aware of:

- Audio now leaves the device to a transcription provider. That is a real
  change in the privacy posture the browser approach was chosen for, and it is
  the cost of voice working at all on a desktop.
- The round-trip endpoint `POST /sessions/{id}/voice` is gone. It answered
  from a spoken clip with no chance to correct a misheard word; the transcript
  now lands in the input box and the user sends it.
- `SARVAM_API_KEY` in `render.yaml` is now genuinely read. It was declared but
  dead before. **`GROQ_API_KEY` is load-bearing too** — it is the STT fallback,
  not only an LLM provider.
- Dictation shipped. **Live talk did not.** F8 needs Sarvam's WebSocket
  streaming API; the REST path returns the whole clip at once.
- Nothing degrades silently: with no microphone the button is hidden, and a
  failed clip returns a sentence the user can act on rather than a 500.

The original access argument survives, but for a different reason: a browser
that can already read the page could not reliably dictate to it.
