# Voice Assistant

Voice Assistant verifies the realtime hands-free spoken interaction for Indian citizens who prefer speaking or hearing over reading text, powered by LiveKit WebRTC, Sarvam AI STT, and Sarvam Multilingual TTS across English, Hindi, and Kannada.

## Sub-features

- `voice-livekit-handshake` verifies LiveKit SFU server connection and room token issuance.
- `voice-sarvam-stt` verifies streaming speech-to-text with auto language detection.
- `voice-multilingual-tts` tests audio chunk synthesis across three regional Indian voices:
  - English: `shubh_en_narration_gentle` (en-IN)
  - Hindi: `aayan_hi_conversational` (hi-IN)
  - Kannada: `chaitra_kn_conversation` (kn-IN)
- `voice-llm-integration` asserts seamless piping between user spoken queries, Law Saathi FastAPI backend, and verbalized spoken summaries.

## How to get to it (user POV)

- Open `http://localhost:3000/voice` or click **"Live Voice"** in the top navigation of `/chat`.
- Allow microphone permissions.
- Speak in Hindi, Kannada, or English.
- Hear the spoken legal response in real time while reading the live transcript.

## Driving it with control-law-saathi

Preconditions:
- Backend running on `http://localhost:8000`.
- Sarvam API key and LiveKit server configured.

- **Run standalone voice flow verification.**
  Execute the end-to-end voice integration test:
  ```sh
  .venv/bin/python scripts/verify-law-saathi.py voice
  ```
  Expected result:
  - TTS audio chunks synthesized for all three languages:
    - `[EN] Selected speaker: shubh_en_narration_gentle`
    - `[HI] Selected speaker: aayan_hi_conversational`
    - `[KN] Selected speaker: chaitra_kn_conversation`
  - LawSaathiLLM retrieves verified answer from FastAPI backend.
  - Test exits with code 0 and `ALL LIVEKIT AGENT INTEGRATION TESTS PASSED!`.
- **Proof.** Confirm structured test results saved at `artifacts/verify-law-saathi/voice_proof.json`.

## Gotchas

- When testing in headless CI or server without physical microphones, always use `scripts/verify-law-saathi.py voice` which drives the complete software pipeline through simulated PCM audio streams.
- If TTS synthesis fails, check `SARVAM_API_KEY` validity in `api/.env`.
