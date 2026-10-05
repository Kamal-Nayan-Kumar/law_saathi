"use client";

/**
 * Voice input and output using the browser's own speech APIs.
 *
 * Why not the server: STT/TTS through Sarvam needs an API key we do not have,
 * and every word would leave the device. `SpeechRecognition` and
 * `speechSynthesis` are already in the browser, work offline for TTS on most
 * platforms, and support Hindi and Kannada where the OS has the voice pack.
 *
 * This is a genuine accessibility feature, not a nicety: many of the people who
 * need family-law help most cannot type, and several read in a second language.
 *
 * Everything degrades quietly. No speech API means the buttons are simply not
 * shown, rather than the user pressing a button that silently does nothing.
 */
import { useCallback, useEffect, useRef, useState } from "react";

/** Minimal shape of the vendor-prefixed and standard SpeechRecognition APIs. */
type SpeechRecognitionLike = {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }>; resultIndex: number }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  onstart: (() => void) | null;
};

type RecognitionCtor = new () => SpeechRecognitionLike;

function recognitionCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as {
    SpeechRecognition?: RecognitionCtor;
    webkitSpeechRecognition?: RecognitionCtor;
  };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

/** BCP-47 tags the agent recognises. */
export const SPEECH_LANG: Record<string, string> = {
  en: "en-IN",
  hi: "hi-IN",
  kn: "kn-IN",
};

export function canListen(): boolean {
  return recognitionCtor() !== null;
}

export function canSpeak(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

/** The languages the OS can actually read aloud, so we never offer silence. */
export function speakableLangs(): string[] {
  if (!canSpeak()) return [];
  const voices = window.speechSynthesis.getVoices();
  const found = new Set<string>();
  for (const v of voices) found.add(v.lang.slice(0, 2).toLowerCase());
  return [...found];
}

export type ListenState = "idle" | "starting" | "listening" | "error";

export function useSpeechToText(lang: string) {
  const [state, setState] = useState<ListenState>("idle");
  const [interim, setInterim] = useState("");
  const [error, setError] = useState("");
  const recRef = useRef<SpeechRecognitionLike | null>(null);
  const supported = canListen();

  const stop = useCallback(() => {
    recRef.current?.stop();
    recRef.current = null;
    setState("idle");
    setInterim("");
  }, []);

  const start = useCallback(
    (onFinal: (text: string) => void) => {
      const Ctor = recognitionCtor();
      if (!Ctor) {
        setError("This browser cannot take voice input. Please type instead.");
        setState("error");
        return;
      }
      setError("");
      setState("starting");
      const rec = new Ctor();
      rec.lang = SPEECH_LANG[lang] || "en-IN";
      // Interim results make the transcript update as they speak, which is what
      // makes it feel responsive rather than frozen.
      rec.interimResults = true;
      rec.continuous = false;
      rec.maxAlternatives = 1;
      rec.onresult = (e) => {
        let pending = "";
        let final = "";
        for (let i = e.resultIndex; i < e.results.length; i += 1) {
          const r = e.results[i];
          if (r.isFinal) final += r[0].transcript;
          else pending += r[0].transcript;
        }
        setInterim(pending);
        if (final.trim()) {
          setInterim("");
          onFinal(final.trim());
        }
      };
      rec.onerror = (e) => {
        // "no-speech" and "aborted" are normal, not failures worth reporting.
        if (e.error !== "no-speech" && e.error !== "aborted") {
          setError(
            e.error === "not-allowed"
              ? "Microphone access was blocked. Allow it in your browser settings."
              : `Voice input failed (${e.error}).`,
          );
          setState("error");
        } else {
          setState("idle");
        }
      };
      rec.onend = () => {
        setState((s) => (s === "error" ? s : "idle"));
        setInterim("");
      };
      recRef.current = rec;
      try {
        rec.start();
        setState("listening");
      } catch {
        // Chrome throws if start() is called twice in quick succession.
        setState("listening");
      }
    },
    [lang],
  );

  // A recogniser left running when the component unmounts keeps the microphone
  // hot, which is the kind of thing a user notices as "the app is listening to
  // me" and must never happen.
  useEffect(() => () => recRef.current?.abort(), []);

  return { supported, state, interim, error, start, stop };
}

export function useSpeechSynthesis(lang: string) {
  const [speakingId, setSpeakingId] = useState<number | null>(null);
  const supported = canSpeak();

  const speak = useCallback(
    (text: string, id: number) => {
      if (!supported || !text.trim()) return;
      // Strip markdown: speech synthesis reads "#" and "*" aloud.
      const plain = text
        .replace(/```[\s\S]*?```/g, " ")
        .replace(/[#*_>`]/g, "")
        .replace(/\[(\d+)\]/g, "source $1")
        .replace(/https?:\/\/\S+/g, "")
        .replace(/\s+/g, " ")
        .trim();
      // The citation list and disclaimer are noise out loud. Cut them.
      const body = plain.split(/What to do next/i)[0].trim();
      if (!body) return;

      window.speechSynthesis.cancel();
      const utter = new SpeechSynthesisUtterance(body);
      utter.lang = SPEECH_LANG[lang] || "en-IN";
      utter.rate = 0.98; // slightly slower than default: this is dense legal text
      utter.onstart = () => setSpeakingId(id);
      utter.onend = () => setSpeakingId((cur) => (cur === id ? null : cur));
      utter.onerror = () => setSpeakingId((cur) => (cur === id ? null : cur));
      window.speechSynthesis.speak(utter);
    },
    [lang, supported],
  );

  const stop = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.cancel();
    setSpeakingId(null);
  }, [supported]);

  useEffect(() => () => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
  }, []);

  return { supported, speakingId, speak, stop };
}