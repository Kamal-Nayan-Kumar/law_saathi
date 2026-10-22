# Voice Assistant

The Voice Assistant verifies realtime, low-latency spoken conversations in English, Hindi, and Kannada. Users speak into their microphone and receive verified spoken responses synthesized with native Indian voices.

## Sub-features

- `voice-webrtc-session` establishes audio track publishing and subscription over LiveKit SFU.
- `voice-stt-sarvam` transcribes incoming audio with language detection (Sarvam AI WebSocket STT).
- `voice-reasoning-bridge` passes transcribed speech through Law Saathi retrieval and verification pipeline.
- `voice-tts-multilingual` generates natural speech across three Indian languages (Kannada: `chaitra_kn_conversation`, Hindi: `aayan_hi_conversational`, English: `shubh_en_narration_gentle`).

## How to get to it (user POV)

- Open `http://localhost:3000/voice` or click **"Live Voice"** in the top navigation bar of `/chat`.
- Grant microphone permission.
- Speak in Hindi, Kannada, or English.
- Hear the assistant respond out loud in the same language.

## Driving it with control-law-saathi

Preconditions:
- Doctor check passes.
- Sarvam API key and LiveKit server credentials are set in environment.

- **Run Standalone Integration Flow.**
  Execute the automated worker verification script:
  ```sh
  .venv/bin/python scripts/verify-law-saathi.py voice
  ```
  Or run the agent integration test directly:
  ```sh
  voice/agent/.venv/bin/python voice/agent/test_agent_flow.py
  ```
  Observable result:
  - MultilingualSarvamTTS synthesizes audio chunks for English, Hindi, and Kannada.
  - LawSaathiLLM reaches the FastAPI backend and receives a grounded reply.
  - Test completes with `ALL LIVEKIT AGENT INTEGRATION TESTS PASSED!`.
- **Proof.** Confirm test results and generated transcripts are recorded in `artifacts/verify-law-saathi/voice_proof.json`.

## Gotchas

- Live voice testing requires `livekit-server --dev` running on port 7880 and the Python agent worker running in `voice/agent`.
- If Sarvam TTS fails, verify `SARVAM_API_KEY` validity.
- The voice assistant automatically switches speaker voices based on detected query language.
