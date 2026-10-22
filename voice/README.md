# LiveKit Realtime Voice Agent for Law Saathi

A low-latency, multilingual voice-to-voice agent for Indian family law.
Enables hands-free spoken interaction in **English**, **Hindi**, and **Kannada**.

---

## Architecture

```
User (Browser / WebRTC)
   │
   ▼
LiveKit Server (Local Dev / Cloud SFU)
   │
   ▼  Audio PCM (16kHz Mono)
LiveKit Agent Worker (Python 3.12, livekit-agents 1.8+)
   │
   ├──> 1. Speech-to-Text (STT):
   │       Sarvam AI STTRealtime (Streaming WebSocket, server-side VAD, auto language detect)
   │
   ├──> 2. Reasoning & Law Retrieval:
   │       Law Saathi FastAPI Backend (`http://localhost:8000/sessions/{id}/ask`)
   │       • Intent Classification
   │       • Qdrant Bare-Act Statutory Retrieval + Indian Kanoon Case Law
   │       • Fact Verification & Grounding
   │       • Native Language Script Rewriter
   │
   └──> 3. Text-to-Speech (TTS):
           Multilingual Sarvam TTS (`bulbul:v4-flash`)
           • Kannada -> `chaitra_kn_conversation`
           • Hindi   -> `aayan_hi_conversational`
           • English -> `shubh_en_narration_gentle`
```

---

## Quickstart

### 1. Start the LiveKit Server (Local Dev)

```bash
# Uses the installed local binary (port 7880)
livekit-server --dev
```

### 2. Start the Law Saathi API

```bash
export DATABASE_URL="sqlite:///./tmp/dev.db"
.venv/bin/uvicorn app.main:app --app-dir api --port 8000
```

### 3. Start the Voice Agent Worker

```bash
cd voice/agent
export LIVEKIT_URL="ws://127.0.0.1:7880"
export LIVEKIT_API_KEY="devkey"
export LIVEKIT_API_SECRET="secret"

# Run the agent in dev mode:
.venv/bin/python agent.py dev
```

### 4. Start the Web App & Join the Voice Call

```bash
cd web
npm run dev
```

Navigate to `http://localhost:3000/voice` or click **"Live Voice"** in the top navigation bar of `/chat`.

---

## Verifying the Worker Standalone

Run the automated integration test to verify TTS audio generation for all three languages and LLM connection to the Law Saathi backend:

```bash
voice/agent/.venv/bin/python voice/agent/test_agent_flow.py
```

Expected output:
```
--- 1. Testing MultilingualSarvamTTS ---
[EN] Selected speaker: shubh_en_narration_gentle (en-IN)
[EN] Synthesized audio chunks: 28
[HI] Selected speaker: aayan_hi_conversational (hi-IN)
[HI] Synthesized audio chunks: 23
[KN] Selected speaker: chaitra_kn_conversation (kn-IN)
[KN] Synthesized audio chunks: 26
TTS test PASSED!

--- 2. Testing LawSaathiLLM with FastAPI Backend ---
Received reply (264 chars):
आप अदालत में एक आवेदन कर सकती हैं जिसमें आप अपने पति से भरण‑पोषण माँगती हैं...
LLM integration test PASSED!

ALL LIVEKIT AGENT INTEGRATION TESTS PASSED!
```

---

## Known Gotchas & Production Notes

1. **Do not use Groq Whisper for STT in LiveKit:** Groq has no streaming ASR endpoint, forcing chunk buffering and latency spikes. Sarvam STTRealtime streams tokens with partial transcripts.
2. **Turn Detection:** Set `turn_detection="stt"` with `min_delay=0.07` so LiveKit uses Sarvam's native voice-activity detection without consuming LiveKit Cloud turn-detection quotas.
3. **Multi-speaker TTS:** Each Sarvam TTS language requires a distinct voice model and speaker ID. The `MultilingualSarvamTTS` class in `agent.py` automatically routes text by script.
4. **Self-Hosting vs Cloud:** On LiveKit Cloud free Build tier, agent containers idle and experience 10–20s cold starts. For live project demos, run the agent worker locally against your local server or Cloud project.
