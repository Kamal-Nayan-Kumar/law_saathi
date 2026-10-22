"use client";

import { useState, useCallback, useEffect } from "react";
import Link from "next/link";
import {
  LiveKitRoom,
  RoomAudioRenderer,
  BarVisualizer,
  useVoiceAssistant,
} from "@livekit/components-react";
import Logo from "@/components/Logo";
import Icon from "@/components/Icon";
import "./voice.css";

function VoiceAssistantUI({ onEndCall }: { onEndCall: () => void }) {
  const { state, audioTrack } = useVoiceAssistant();

  const isSpeaking = state === "speaking";
  const isListening = state === "listening" || state === "thinking";

  return (
    <div className="voice-card">
      <div className={`voice-orb ${isSpeaking ? "speaking" : isListening ? "listening" : ""}`}>
        <Icon name={isSpeaking ? "volume" : "mic"} size={48} />
      </div>

      <div className="voice-status">
        {state === "speaking" && "Law Saathi is speaking…"}
        {state === "listening" && "Listening to you…"}
        {state === "thinking" && "Consulting statutory bare acts…"}
        {state === "connecting" && "Connecting to secure voice room…"}
        {state === "idle" && "Connected — speak naturally"}
      </div>

      <div className="voice-substatus">
        Realtime Multilingual ASR & TTS via Sarvam AI & LiveKit
      </div>

      <div className="voice-badges">
        <span className="voice-badge">English</span>
        <span className="voice-badge">हिन्दी</span>
        <span className="voice-badge">ಕನ್ನಡ</span>
      </div>

      {audioTrack && (
        <div style={{ height: "40px", width: "200px", margin: "1rem 0" }}>
          <BarVisualizer
            trackRef={audioTrack}
            barCount={7}
            options={{ minHeight: 4, maxHeight: 36 }}
          />
        </div>
      )}

      <div className="voice-controls">
        <button type="button" className="voice-btn-end" onClick={onEndCall}>
          End Call
        </button>
      </div>

      <RoomAudioRenderer />
    </div>
  );
}

export default function VoicePage() {
  const [token, setToken] = useState<string | null>(null);
  const [url, setUrl] = useState<string | null>(null);
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startVoiceSession = useCallback(async () => {
    setConnecting(true);
    setError(null);
    try {
      const res = await fetch("/api/voice/token", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        throw new Error(`Token request failed: ${res.status}`);
      }
      const data = await res.json();
      setToken(data.token);
      setUrl(data.url);
    } catch (err: any) {
      setError(err?.message || "Failed to connect to voice server.");
    } finally {
      setConnecting(false);
    }
  }, []);

  const endVoiceSession = useCallback(() => {
    setToken(null);
    setUrl(null);
  }, []);

  return (
    <div className="voice-page">
      <header className="voice-nav">
        <div className="voice-nav-left">
          <Link href="/chat" className="voice-back-btn">
            <Icon name="chevronDown" size={16} className="flip-y" />
            Back to Chat
          </Link>
          <Logo />
        </div>
        <div>
          <span style={{ fontSize: "0.85rem", color: "var(--muted)" }}>
            Live Voice Mode (WebRTC)
          </span>
        </div>
      </header>

      <main className="voice-content">
        {!token ? (
          <div className="voice-card">
            <div className="voice-orb">
              <Icon name="mic" size={48} />
            </div>
            <h2 className="voice-status">Speak with Law Saathi</h2>
            <p className="voice-substatus">
              Ask your family law questions out loud in English, Hindi, or Kannada.
              Get grounded legal answers spoken back in real time.
            </p>

            <div className="voice-badges">
              <span className="voice-badge">English</span>
              <span className="voice-badge">हिन्दी</span>
              <span className="voice-badge">ಕನ್ನಡ</span>
            </div>

            {error && (
              <p style={{ color: "#c53030", fontSize: "0.88rem", marginBottom: "1rem" }}>
                {error}
              </p>
            )}

            <button
              type="button"
              className="voice-btn-start"
              onClick={startVoiceSession}
              disabled={connecting}
            >
              <Icon name="mic" size={18} />
              {connecting ? "Connecting…" : "Start Voice Call"}
            </button>
          </div>
        ) : (
          <LiveKitRoom
            serverUrl={url!}
            token={token!}
            connect={true}
            audio={true}
            video={false}
            onDisconnected={endVoiceSession}
          >
            <VoiceAssistantUI onEndCall={endVoiceSession} />
          </LiveKitRoom>
        )}
      </main>
    </div>
  );
}
