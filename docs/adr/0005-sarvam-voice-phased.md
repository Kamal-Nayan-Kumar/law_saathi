# ADR-0005 — Sarvam voice now, LiveKit live-talk Phase 2

Status: **superseded** — see "What actually shipped" below.

Context: Solo build; both dictation + realtime in one go is high risk; ElevenLabs weak on Kannada + costly.

Decision: MVP = Sarvam STT/TTS push-to-talk only; LiveKit realtime behind a flag as Phase 2; ElevenLabs dropped.

Consequences: Viva demos dictation mode; live-talk is a tracked follow-up, not a broken half-feature.

## What actually shipped

Superseded by browser Web Speech in `web/lib/voice.ts`. No Sarvam key was
available, and `SpeechRecognition` / `speechSynthesis` already cover the MVP:
no API key, nothing leaving the device, and Hindi and Kannada work where the OS
has a voice pack.

Consequences to be aware of:

- `api/app/voice.py` and `POST /sessions/{id}/voice` still exist but the
  frontend never calls them. That path is dead, not merely unused.
- `SARVAM_API_KEY` is still declared in `render.yaml`. It is not read.
- Dictation shipped. **Live talk did not.** No provider supports the low-latency
  streaming that F8 needs, so it is still open in `TO-DO.md`.
- Nothing degrades silently: when a browser has no speech API the buttons are
  hidden rather than shown broken.

Keeping the browser approach also means the access argument in the original
context got stronger, not weaker — a browser that can already read the page can
already dictate to it.
