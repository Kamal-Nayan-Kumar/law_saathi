"use client";

/**
 * Voice input: record in the browser, transcribe on the server.
 *
 * Why we record instead of using the browser's speech API: `SpeechRecognition`
 * is not actually speech recognition, it is a client for Google's speech
 * servers. On Android Chrome it works. On desktop Chrome it fails with
 * `network`, because the part that breaks is the request to Google — an
 * adblocker, Brave Shields, or a filtered network kills it before a word is
 * recognised. That made voice input work on the phone and fail on the laptop
 * for the same user, which is the worst possible split for an accessibility
 * feature.
 *
 * So the browser only ever *captures* audio. Transcribing happens on our API,
 * where the network path is ours and nobody's extension can block it.
 *
 * On pauses: recording runs until the user presses stop, or 25 seconds pass.
 * A pause in the middle of a thought is just silence in the audio, and silence
 * does not end a recording. The transcript lands in the input box rather than
 * being sent, so a misheard word can be read and corrected before it becomes a
 * legal question. A client that sends on the first pause is the same as
 * sending the first half of every sentence.
 *
 * Everything degrades quietly. No microphone means the button is not shown,
 * rather than a control that silently does nothing.
 */
import { useCallback, useEffect, useRef, useState } from "react";

/** BCP-47 tags the agent recognises. */
export const SPEECH_LANG: Record<string, string> = {
  en: "en-IN",
  hi: "hi-IN",
  kn: "kn-IN",
};

/** Matches the server's cap. Recording stops on its own at the same number so
 *  the audio we refuse is never uploaded. */
export const MAX_RECORDING_SECONDS = 25;

export function canRecord(): boolean {
  if (typeof window === "undefined") return false;
  return (
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof window.MediaRecorder !== "undefined"
  );
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

/**
 * The voice to read this language aloud with.
 *
 * `utterance.lang` on its own is a request, not a choice. When the OS has no
 * voice for the language, Chrome and Safari fall back to the default voice,
 * and a Kannada answer is then read in English phonemes: it sounds like the
 * app is broken rather than like it is speaking Kannada. So the voice is
 * picked here, by language, and the caller can check that one exists.
 *
 * The list of voices is empty on the first call in Chrome and Safari, and
 * fills in later, so this is called again whenever the list changes.
 */
export function pickVoice(lang: string): SpeechSynthesisVoice | null {
  if (!canSpeak()) return null;
  const want = (SPEECH_LANG[lang] || "en-IN").slice(0, 2).toLowerCase();
  const voices = window.speechSynthesis.getVoices();
  const matching = voices.filter(
    (v) => v.lang.slice(0, 2).toLowerCase() === want,
  );
  if (!matching.length) return null;
  // An exact regional match reads better than a generic one: en-IN over
  // en-US, hi-IN over hi.
  const exact = matching.find(
    (v) => v.lang.toLowerCase() === (SPEECH_LANG[lang] || "en-IN").toLowerCase(),
  );
  return exact || matching[0];
}

/** Can the OS read this language aloud at all? */
export function canSpeakLang(lang: string): boolean {
  return pickVoice(lang) !== null;
}

/**
 * The text worth reading out loud.
 *
 * Markdown is stripped (speech synthesis reads "#" and "*" aloud), the
 * citation markers become "source 1", and the "what to do next" list and the
 * disclaimer are cut, because they are noise out loud. The heading is cut in
 * every language, not only the English one, or the list is read out in Hindi
 * and Kannada too.
 */
export function speakableText(text: string): string {
  const plain = text
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/[#*_>`]/g, "")
    .replace(/\[(\d+)\]/g, "source $1")
    .replace(/https?:\/\/\S+/g, "")
    .replace(/\s+/g, " ")
    .trim();
  return plain
    .split(/what to do next|आगे क्या करें|ಮುಂದಿನ ಏನು ಮಾಡಬೇಕು|ಮುಂದೆ ಏನು ಮಾಡಬೇಕು/i)[0]
    .trim();
}

export type ListenState = "idle" | "recording" | "transcribing" | "error";

/** Safari and Chrome disagree about which of these actually record speech.
 *  Anything else falls back to the browser default, which is the format the
 *  provider can decode anyway. */
function pickMimeType(): string | undefined {
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];
  if (typeof MediaRecorder === "undefined") return undefined;
  return candidates.find((t) => MediaRecorder.isTypeSupported(t));
}

export function useDictation(lang: string) {
  const [state, setState] = useState<ListenState>("idle");
  const [seconds, setSeconds] = useState(0);
  const [error, setError] = useState("");
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const supported = canRecord();

  /** Release the microphone. Missing this is how a page ends up with the
   *  recording dot still lit after the user believes they stopped. */
  const release = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    recorderRef.current = null;
    setSeconds(0);
  }, []);

  /** Hand the blob to the server and put the answer in the input box. */
  const upload = useCallback(
    async (blob: Blob, onText: (text: string) => void) => {
      setState("transcribing");
      try {
        const b64 = await new Promise<string>((resolve, reject) => {
          const fr = new FileReader();
          fr.onload = () => resolve(String(fr.result).split(",")[1] || "");
          fr.onerror = () => reject(new Error("Could not read the recording."));
          fr.readAsDataURL(blob);
        });
        const res = await fetch("/api/bff/voice/transcribe", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ audio_b64: b64, lang }),
        });
        if (res.status === 401) {
          setError("Log in to use voice input.");
          setState("error");
          return;
        }
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          setError(data?.detail || "Voice input failed. Please type instead.");
          setState("error");
          return;
        }
        if (data?.error) {
          setError(data.error);
          setState("error");
          return;
        }
        const text: string = (data?.transcript || "").trim();
        if (!text) {
          setError("Did not catch that. Try again, a little closer to the mic.");
          setState("error");
          return;
        }
        setError("");
        setState("idle");
        onText(text);
      } catch {
        setError("Voice input failed (network). Please type instead.");
        setState("error");
      }
    },
    [lang],
  );

  const stop = useCallback(
    (onText: (text: string) => void) => {
      const rec = recorderRef.current;
      if (!rec || rec.state === "inactive") {
        release();
        setState("idle");
        return;
      }
      // onstop assembles the chunks and uploads, so the microphone is only
      // released once there is audio in hand.
      rec.onstop = () => {
        const blob = new Blob(chunksRef.current, {
          type: rec.mimeType || "audio/webm",
        });
        chunksRef.current = [];
        release();
        if (blob.size > 0) void upload(blob, onText);
        else setState("idle");
      };
      try {
        rec.stop();
      } catch {
        release();
        setState("idle");
      }
    },
    [release, upload],
  );

  const start = useCallback(
    async (onText: (text: string) => void) => {
      if (!supported) {
        setError("This browser cannot record audio. Please type instead.");
        setState("error");
        return;
      }
      setError("");
      try {
        const stream = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true },
        });
        streamRef.current = stream;
        chunksRef.current = [];

        const mimeType = pickMimeType();
        const rec = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
        rec.ondataavailable = (e: BlobEvent) => {
          if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
        };
        recorderRef.current = rec;
        rec.start();
        setSeconds(0);
        setState("recording");

        // The cap is on recording, not on silence. Someone pausing to think is
        // still recording and still owns the clock.
        timerRef.current = setInterval(() => {
          setSeconds((s) => {
            if (s + 1 >= MAX_RECORDING_SECONDS) {
              stop(onText);
              return 0;
            }
            return s + 1;
          });
        }, 1000);
      } catch (e) {
        release();
        const name = e instanceof Error ? e.name : "";
        setError(
          name === "NotAllowedError" || name === "SecurityError"
            ? "Microphone access was blocked. Allow it in your browser settings."
            : "Could not open the microphone. Please type instead.",
        );
        setState("error");
      }
    },
    [release, stop, supported],
  );

  // A recorder left running when the component unmounts keeps the microphone
  // hot, which is the kind of thing a user notices as "the app is listening to
  // me" and must never happen.
  useEffect(
    () => () => {
      if (timerRef.current) clearInterval(timerRef.current);
      streamRef.current?.getTracks().forEach((t) => t.stop());
    },
    [],
  );

  return { supported, state, seconds, error, start, stop };
}

export function useSpeechSynthesis(lang: string) {
  const [speakingId, setSpeakingId] = useState<number | null>(null);
  const supported = canSpeak();
  // The OS may have no voice for the language being asked about. Chrome
  // fills the voice list in late, so this is re-checked whenever the list
  // changes rather than only on the first render.
  const [voice, setVoice] = useState<SpeechSynthesisVoice | null>(null);
  // The server can speak the answer in a language the device has no voice
  // for. It is asked for only when the browser cannot do it, so the common
  // case stays free and instant.
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (!supported) return;
    const refresh = () => setVoice(pickVoice(lang));
    refresh();
    window.speechSynthesis.addEventListener("voiceschanged", refresh);
    return () => {
      window.speechSynthesis.removeEventListener("voiceschanged", refresh);
    };
  }, [lang, supported]);

  /** Ask the server to speak it, for a language the device has no voice for. */
  const speakWithServer = useCallback(
    async (text: string, id: number, onFinished?: () => void): Promise<boolean> => {
      try {
        const res = await fetch("/api/bff/voice/speak", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text, lang }),
        });
        if (!res.ok) return false;
        const data = await res.json().catch(() => ({}));
        if (!data?.audio) return false;
        audioRef.current?.pause();
        const audio = new Audio(`data:audio/mpeg;base64,${data.audio}`);
        audioRef.current = audio;
        audio.onplay = () => setSpeakingId(id);
        audio.onended = () => {
          setSpeakingId((cur) => (cur === id ? null : cur));
          onFinished?.();
        };
        audio.onerror = () => {
          setSpeakingId((cur) => (cur === id ? null : cur));
          onFinished?.();
        };
        await audio.play();
        return true;
      } catch {
        return false;
      }
    },
    [lang],
  );

  const speak = useCallback(
    async (text: string, id: number, onFinished?: () => void) => {
      if (!supported || !text.trim()) return;
      const body = speakableText(text);
      if (!body) return;

      // No voice for this language on this device: the server speaks it
      // instead, in the language it was written in.
      if (!pickVoice(lang)) {
        const done = await speakWithServer(body, id, onFinished);
        if (done) return;
        // The server could not do it either. Fall through and let the browser
        // try: a wrong voice is better than no voice.
      }

      window.speechSynthesis.cancel();
      const utter = new SpeechSynthesisUtterance(body);
      utter.lang = SPEECH_LANG[lang] || "en-IN";
      // The voice itself, not just a request for one. Without this the
      // browser picks whatever it likes and a Kannada answer can be read in
      // English phonemes.
      const chosen = pickVoice(lang);
      if (chosen) utter.voice = chosen;
      utter.rate = 0.98; // slightly slower than default: this is dense legal text
      utter.onstart = () => setSpeakingId(id);
      utter.onend = () => {
        setSpeakingId((cur) => (cur === id ? null : cur));
        onFinished?.();
      };
      utter.onerror = () => {
        setSpeakingId((cur) => (cur === id ? null : cur));
        onFinished?.();
      };
      window.speechSynthesis.speak(utter);
    },
    [lang, speakWithServer, supported],
  );

  const stop = useCallback(() => {
    if (!supported) return;
    window.speechSynthesis.cancel();
    audioRef.current?.pause();
    audioRef.current = null;
    setSpeakingId(null);
  }, [supported]);

  useEffect(() => () => {
    if (typeof window !== "undefined" && "speechSynthesis" in window) {
      window.speechSynthesis.cancel();
    }
    audioRef.current?.pause();
  }, []);

  return { supported, speakingId, speak, stop };
}