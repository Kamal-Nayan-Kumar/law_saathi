"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Image from "next/image";
import Link from "next/link";
import { useRouter } from "next/navigation";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { authClient } from "@/lib/auth/client";
import { api } from "@/lib/api";
import { askStream, type AskResult, type StreamStep } from "@/lib/stream";
import {
  useDictation,
  useSpeechSynthesis,
  MAX_RECORDING_SECONDS,
  speakableText,
} from "@/lib/voice";
import Icon from "@/components/Icon";
import Logo from "@/components/Logo";
import "./chat.css";

type Msg = {
  id: number;
  role: string;
  content: string;
  lang: string;
};

// A message as returned by GET /sessions/{id}/messages. The source and trace
// fields were added after the first release, so older rows do not carry them.
type StoredMsg = Msg & {
  citations?: string[];
  citation_sources?: string[];
  trace?: string[];
  trace_detail?: TraceStep[];
  verified?: boolean | null;
  confidence?: number | null;
  created_at?: string | null;
};

type ChatSession = {
  id: number;
  title: string;
};

// One page of the history, as the API returns it.
type SessionPage = {
  items: ChatSession[];
  page: number;
  per_page: number;
  total: number;
  has_more: boolean;
};

// How many chats the sidebar asks for at a time. Twenty is about two
// screens of a narrow column.
const SESSION_PAGE_SIZE = 20;

type TraceStep = StreamStep;

/**
 * A table inside an answer gets its own sideways scroll.
 *
 * The agent writes comparison tables — "one year or two", "which court",
 * "what each section says". On a phone the table was squeezed into the card
 * width instead, so a three-column table turned into one word per line and the
 * headings wrapped into a ladder. The table now keeps its shape and the reader
 * swipes it, which is the one gesture that still works on a 320px screen.
 */
const MD_COMPONENTS: Components = {
  table: ({ node: _node, ...props }) => (
    <div className="md-table">
      <table {...props} />
    </div>
  ),
};

const SUGGESTIONS = [
  "How do I get a mutual-consent divorce?",
  "पत्नी भरण-पोषण कैसे माँग सकती है?",
  "ಮಗುವಿನ ಕಸ್ಟಡಿ ಯಾರಿಗೆ ಸಿಗುತ್ತದೆ?",
];

// The chat's own chrome, in the language of the answer. The agent already
// writes the answer, the step log and the trace in the reader's language; this
// is the last piece that was English — a Hindi reader was being told "How
// Saathi worked this out" and "Sources (5)" in a script they had not used.
//
// The answer's language is authoritative (`msg.lang`, which the server reports
// from the script of the question), so a stored answer stays in its own
// language forever, even if the user switches to English afterwards.
type UiKey =
  | "warmup1" | "warmup2" | "warmup3" | "warmup4" | "warmup5"
  | "thinking" | "steps" | "sources" | "readAloud" | "stop"
  | "working" | "starting" | "newChat" | "noChats" | "signOut"
  | "history" | "deleteChat" | "confirmDelete" | "askPlaceholder"
  | "sideLoading" | "sideError" | "loadMore" | "moreChats" | "sideLoadingMore"
  | "recording" | "transcribing" | "emptyTitle" | "emptyHint" | "checking"
  | "srcAct" | "srcWeb" | "srcDoc" | "srcOther";

const UI: Record<UiKey, { en: string; hi: string; kn: string }> = {
  warmup1: { en: "Understanding your question…", hi: "आपका प्रश्न समझ रहे हैं…", kn: "ನಿಮ್ಮ ಪ್ರಶ್ನೆಯನ್ನು ಅರ್ಥಮಾಡಿಕೊಳ್ಳುತ್ತಿದೆ…" },
  warmup2: { en: "Choosing which law applies…", hi: "कौन सा कानून लागू है, चुन रहे हैं…", kn: "ಯಾವ ಕಾನೂನು ಅನ್ವಯಿಸುತ್ತದೆ ಎಂದು ಆಯ್ಕೆ ಮಾಡುತ್ತಿದೆ…" },
  warmup3: { en: "Reading the bare acts…", hi: "कानूनों को पढ़ रहे हैं…", kn: "ಕಾಯ್ದೆಗಳನ್ನು ಓದುತ್ತಿದೆ…" },
  warmup4: { en: "Checking every claim…", hi: "हर बात जाँच रहे हैं…", kn: "ಪ್ರತಿ ಹೇಳಿಕೆ ಪರಿಶೀಲಿಸುತ್ತಿದೆ…" },
  warmup5: { en: "Writing the answer…", hi: "उत्तर लिभ रहे हैं…", kn: "ಉತ್ತರ ಬರೆಯುತ್ತಿದೆ…" },
  thinking: { en: "How Saathi worked this out", hi: "साथी ने यह कैसे निकाला", kn: "ಸಾಥಿ ಇದನ್ನು ಹೇಗೆ ಕಂಡುಕೊಂಡಿತ್ತು" },
  steps: { en: "steps", hi: "चरण", kn: "ಹಂತಗಳು" },
  sources: { en: "Sources", hi: "स्रोत", kn: "ಮೂಲಗಳು" },
  readAloud: { en: "Read aloud", hi: "पढ़कर सुनाएँ", kn: "ಓದಿ ಕೇಳಿಸಿ" },
  stop: { en: "Stop", hi: "रोकें", kn: "ನಿಲ್ಲಿಸಿ" },
  working: { en: "Working on it…", hi: "काम चल रहा है…", kn: "ಕೆಲಸ ನಡೆಯುತ್ತಿದೆ…" },
  starting: { en: "Getting to your question…", hi: "आपके प्रश्न तक पहुँच रहे हैं…", kn: "ನಿಮ್ಮ ಪ್ರಶ್ನೆಗೆ ತಲುಪುತ್ತಿದೆ…" },
  newChat: { en: "New chat", hi: "नई बातचीत", kn: "ಹೊಸ ಸಂಭಾಷಣೆ" },
  noChats: { en: "No chats yet — ask something to start.", hi: "अभी कोई बातचीत नहीं — कुछ पूछकर शुरू करें।", kn: "ಇನ್ನೂ ಸಂಭಾಷಣೆ ಇಲ್ಲ — ಏನಾದರೂ ಕೇಳಿ ಪ್ರಾರಂಭಿಸಿ." },
  // The sidebar used to say "no chats yet" for the whole time the list was on
  // its way, which told a user with twelve chats that they had none. Loading
  // and failed are their own states, and each says only what it knows.
  sideLoading: { en: "Loading your chats…", hi: "आपकी बातचीतें लोड हो रही हैं…", kn: "ನಿಮ್ಮ ಸಂಭಾಷಣೆಗಳು ಲೋಡ್ ಆಗುತ್ತಿವೆ…" },
  sideError: { en: "Couldn't load your chats.", hi: "आपकी बातचीतें लोड नहीं हो सकीं।", kn: "ನಿಮ್ಮ ಸಂಭಾಷಣೆಗಳನ್ನು ಲೋಡ್ ಮಾಡಲು ಸಾಧ್ಯವಾಗಲಿಲ್ಲ." },
  // The history arrives a page at a time. The button says how many are still
  // behind it, so the reader knows whether it is worth pressing.
  loadMore: { en: "Show older chats", hi: "पुरानी बातचीतें दिखाएँ", kn: "ಹಳೆಯ ಸಂಭಾಷಣೆಗಳನ್ನು ತೋರಿಸಿ" },
  moreChats: { en: "{n} more", hi: "{n} और", kn: "ಇನ್ನೂ {n}" },
  sideLoadingMore: { en: "Loading…", hi: "लोड हो रहा है…", kn: "ಲೋಡ್ ಆಗುತ್ತಿದೆ…" },
  signOut: { en: "Sign out", hi: "साइन आउट", kn: "ಸೈನ್ ಔಟ್" },
  history: { en: "Chat history", hi: "बातचीत का इतिहास", kn: "ಸಂಭಾಷಣೆ ಇತಿಹಾಸ" },
  deleteChat: { en: "Delete this chat?", hi: "यह बातचीत हटाएँ?", kn: "ಈ ಸಂಭಾಷಣೆಯನ್ನು ಅಳಿಸಬೇಕೆ?" },
  confirmDelete: { en: "Delete", hi: "हटाएँ", kn: "ಅಳಿಸಿ" },
  askPlaceholder: { en: "Ask a question about family law…", hi: "पारिवारिक कानून के बारे में पूछें…", kn: "ಕುಟುಂಬ ಕಾನೂನು ಬಗ್ಗೆ ಕೇಳಿ…" },
  recording: { en: "Recording — tap the mic to send it. Stops by itself at", hi: "रिकॉर्डिंग — भेजने के लिए माइक दबाएँ। खुद बंद होगी", kn: "ರೆಕಾರ್ಡಿಂಗ್ — ಕಳಿಸಲು ಮೈಕ್ ಒತ್ತಿ. ತಾನೇ ನಿಂತುಬಿಡುತ್ತದೆ" },
  transcribing: { en: "Turning your speech into text…", hi: "आपकी आवाज़ को लिखित बना रहे हैं…", kn: "ನಿಮ್ಮ ಧ್ವನಿಯನ್ನು ಪಠ್ಯವಾಗಿಸುತ್ತಿದೆ…" },
  emptyTitle: { en: "Ask about family law, in any language.", hi: "पारिवारिक कानून के बारे में पूछें, किसी भी भाषा में।", kn: "ಕುಟುಂಬ ಕಾನೂನು ಬಗ್ಗೆ ಕೇಳಿ, ಯಾವ ಭಾಷೆಯಲ್ಲಿಯೂ." },
  emptyHint: { en: "Try one of these to start:", hi: "शुरू करने के लिए एक कोशिश करें:", kn: "ಪ್ರಾರಂಭಿಸಲು ಇವುಗಳಲ್ಲಿ ಒಂದನ್ನು ಪ್ರಯತ್ನಿಸಿ:" },
  checking: { en: "Checking your sign-in…", hi: "आपके साइन-इन जाँच रहे हैं…", kn: "ನಿಮ್ಮ ಸೈನ್-ಇನ್ ಪರಿಶೀಲಿಸುತ್ತಿದೆ…" },
  srcAct: { en: "bare act", hi: "कानून", kn: "ಕಾಯ್ದೆ" },
  srcWeb: { en: "web source", hi: "वेब स्रोत", kn: "ಜಾಲ ಮೂಲ" },
  srcDoc: { en: "document", hi: "दस्तावेज़", kn: "ದಾಖಲೆ" },
  srcOther: { en: "source", hi: "स्रोत", kn: "ಮೂಲ" },
};

function t(lang: string, key: UiKey, vars?: Record<string, string | number>): string {
  const bank = UI[key];
  let out = lang === "hi" || lang === "kn" ? bank[lang] : bank.en;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      out = out.replace(new RegExp(`\\{${k}\\}`, "g"), String(v));
    }
  }
  return out;
}

// Shown before the first step arrives. The real steps replace this list as the
// agent reports them, so the user always sees what Saathi is actually doing
// rather than a fixed animation that could disagree with it.
const WARMUP_KEYS: UiKey[] = ["warmup1", "warmup2", "warmup3", "warmup4", "warmup5"];

/** Friendlier name for a node, matching what the step detail says. */
const NODE_LABEL: Record<string, Record<string, string>> = {
  contextualize: { en: "Reading the conversation", hi: "बातचीत पढ़ रहे हैं", kn: "ಸಂಭಾಷಣೆ ಓದುತ್ತಿದೆ" },
  intent: { en: "Understanding the question", hi: "प्रश्न समझ रहे हैं", kn: "ಪ್ರಶ್ನೆ ಅರ್ಥಮಾಡಿಕೊಳ್ಳುತ್ತಿದೆ" },
  planner: { en: "Choosing the law", hi: "कानून चुन रहे हैं", kn: "ಕಾನೂನು ಆಯ್ಕೆ ಮಾಡುತ್ತಿದೆ" },
  tools: { en: "Searching the bare acts", hi: "कानूनों में खोज", kn: "ಕಾಯ್ದೆಗಳಲ್ಲಿ ಹುಡುಕುತ್ತಿದೆ" },
  reason: { en: "Writing an explanation", hi: "समझाना लिख रहे हैं", kn: "ವಿವರಣೆ ಬರೆಯುತ್ತಿದೆ" },
  verifier: { en: "Checking the citations", hi: "संदर्भ जाँच रहे हैं", kn: "ಉಲ್ಲೇಖ ಪರಿಶೀಲಿಸುತ್ತಿದೆ" },
  response: { en: "Preparing your answer", hi: "उत्तर तैयार कर रहे हैं", kn: "ಉತ್ತರ ಸಿದ್ಧಪಡಿಸುತ್ತಿದೆ" },
};

function nodeLabel(node: string, lang: string): string {
  const bank = NODE_LABEL[node];
  if (!bank) return node;
  if (lang === "hi" || lang === "kn") return bank[lang];
  return bank.en;
}

/** The one sentence in the composer whose numbers sit mid-sentence. */
function recordingText(lang: string, maxSeconds: number, soFar: number): string {
  if (lang === "hi") {
    return `रिकॉर्डिंग चल रही है — भेजने के लिए माइक दबाएँ। यह ${maxSeconds} सेकंड पर खुद बंद हो जाएगी (अभी ${soFar} सेकंड)।`;
  }
  if (lang === "kn") {
    return `ರೆಕಾರ್ಡಿಂಗ್ ನಡೆಯುತ್ತಿದೆ — ಕಳಿಸಲು ಮೈಕ್ ಒತ್ತಿ. ಇದು ${maxSeconds} ಸೆಕೆಂಡ್‌ನಲ್ಲಿ ತಾನೇ ನಿಂತುಬಿಡುತ್ತದೆ (ಈಗ ${soFar} ಸೆಕೆಂಡ್).`;
  }
  return `Recording — tap the mic to send it. Stops by itself at ${maxSeconds} seconds (${soFar}s so far).`;
}

// No "answer language" setting any more. The language of the answer is decided
// by the language of the question, so there is nothing for the user to choose
// and nothing to get wrong.

function detectLang(text: string): "en" | "hi" | "kn" {
  if (/[ಀ-೿]/.test(text)) return "kn";
  if (/[ऀ-ॿ]/.test(text)) return "hi";
  return "en";
}

type Meta = { trace: string[]; steps: TraceStep[]; citations: string[]; sources: string[] };

// Rebuild the per-message Meta map from a fetched message list so a reopened
// chat shows the same Sources block, inline markers and Thinking log as a live
// answer. The trace is stored on the row, so unlike the old version the panel
// is still there after a reload. Rows written before it existed simply get no
// steps, and the toggle is hidden rather than shown empty.
function metaFromList(list: StoredMsg[]): Record<number, Meta> {
  const next: Record<number, Meta> = {};
  list.forEach((m) => {
    if (m.role !== "assistant") return;
    next[m.id] = {
      trace: m.trace || [],
      steps: m.trace_detail || [],
      citations: m.citations || [],
      sources: m.citation_sources || [],
    };
  });
  return next;
}

// How a source is labelled in the Sources list. `kind` picks the tag colour.
const SOURCE_TAGS: Record<string, { label: string; kind: string }> = {
  bare_act: { label: "bare act", kind: "act" },
  web: { label: "web source", kind: "web" },
  doc: { label: "document", kind: "doc" },
};

function sourceTag(type: string, lang: string): { label: string; kind: string } {
  const fallback: Record<string, UiKey> = {
    bare_act: "srcAct", web: "srcWeb", doc: "srcDoc",
  };
  const key = fallback[type];
  if (key) return { label: t(lang, key), kind: type };
  return { label: t(lang, "srcOther"), kind: "other" };
}

// Turn each citation marker in the answer — [1] or [1,2,3] — into a small
// link to the matching item in that answer's Sources list. Only markers whose
// number exists in `citations` are touched, so nothing else is rewritten.
function linkCitationMarkers(text: string, citations: string[], msgId: number): string {
  const count = citations.length;
  if (!count) return text;
  return text.replace(/\[(\d{1,2}(?:\s*,\s*\d{1,2})*)\](?!\()/g, (match, group: string) => {
    const nums = group.split(",").map((n) => Number(n.trim()));
    if (nums.some((n) => n < 1 || n > count)) return match;
    return nums.map((n) => `[${n}](#src-${msgId}-${n})`).join(", ");
  });
}

function AssistantBlock({ msg, m }: { msg: Msg; m?: Meta }) {
  const [showThink, setShowThink] = useState(false);
  const tts = useSpeechSynthesis(msg.lang || "en");
  const ulang = msg.lang || "en";
  const text =
    m && m.citations.length ? linkCitationMarkers(msg.content, m.citations, msg.id) : msg.content;
  const speaking = tts.speakingId === msg.id;

  // Sources are always on screen, so an inline marker only needs to scroll.
  function onCite(e: React.MouseEvent) {
    const a = (e.target as HTMLElement).closest('a[href^="#src-"]');
    if (!a) return;
    e.preventDefault();
    const id = (a.getAttribute("href") || "").slice(1);
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "center" });
  }

  return (
    <div className="ans-card">
      {/* Gate on steps, not trace: an older row has no stored trace, and an
          empty Thinking toggle is worse than none. */}
      {m && m.steps.length > 0 && (
        <div className="think" data-open={showThink}>
          <button
            type="button"
            className="think-toggle"
            onClick={() => setShowThink((v) => !v)}
            aria-expanded={showThink}
          >
            <Icon name="chevronDown" size={15} className="think-caret" />
            {t(ulang, "thinking")}
            <span className="think-count">{m.steps.length} {t(ulang, "steps")}</span>
          </button>
          {showThink && (
            <ol className="think-steps">
              {m.steps.map((s, i) => (
                <li key={`${s.node}-${i}`}>
                  <strong>{nodeLabel(s.node, ulang)}</strong>
                  <span className="step-detail">{s.detail}</span>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
      <div className="md" onClick={onCite}>
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>
          {text}
        </ReactMarkdown>
      </div>

      <div className="ans-foot">
        {tts.supported && (
          <button
            type="button"
            className={`ans-play${speaking ? " on" : ""}`}
            onClick={() => (speaking ? tts.stop() : tts.speak(msg.content, msg.id))}
            aria-label={speaking ? t(ulang, "stop") : t(ulang, "readAloud")}
          >
            <Icon name={speaking ? "close" : "volume"} size={16} />
            {speaking ? t(ulang, "stop") : t(ulang, "readAloud")}
          </button>
        )}
        {m && m.citations.length > 0 && (
          <span className="ans-foot-note">
            {m.citations.length} {t(ulang, "sources").toLowerCase()}
          </span>
        )}
      </div>

      {m && m.citations.length > 0 && (
        <div className="src">
          <p className="src-head">
            <Icon name="book" size={14} />
            {t(ulang, "sources")} ({m.citations.length})
          </p>
          <ol className="src-list">
            {m.citations.map((c, i) => {
              const tag = m.sources[i] ? sourceTag(m.sources[i], ulang) : null;
              return (
                <li key={i} id={`src-${msg.id}-${i + 1}`} className="src-item">
                  <span className="src-n">{i + 1}</span>
                  <span className="src-text">{c}</span>
                  {tag && <span className={`src-tag src-tag-${tag.kind}`}>{tag.label}</span>}
                </li>
              );
            })}
          </ol>
        </div>
      )}
    </div>
  );
}

/**
 * The answer as it is still arriving.
 *
 * Same card as a finished answer, minus the parts that only exist once the run
 * is over: no Sources block, no Read aloud, no Thinking toggle. Those arrive
 * with the `done` event and replace this card in one go, so the reader never
 * sees a source list for an answer that is not finished being written.
 */
function StreamingAnswer({ text }: { text: string }) {
  return (
    <div className="ans-card ans-card-live">
      <div className="md">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>
          {text}
        </ReactMarkdown>
        {/* A caret, so it is obvious the reply is still coming rather than
            simply short. */}
        <span className="caret" aria-hidden="true" />
      </div>
    </div>
  );
}

function LiveVoiceOverlay({
  state,
  userQuery,
  agentAnswer,
  isRecording,
  lang,
  onStopSpeaking,
  onEndCall,
}: {
  state: "greeting" | "listening" | "thinking" | "speaking" | "idle";
  userQuery: string;
  agentAnswer: string;
  isRecording: boolean;
  lang: string;
  onStopSpeaking: () => void;
  onEndCall: () => void;
}) {
  return (
    <div
      className="live-voice-overlay"
      role="dialog"
      aria-modal="true"
      aria-label="Live Voice Call"
    >
      <div className="live-voice-card">
        <button
          type="button"
          className="live-voice-close"
          onClick={onEndCall}
          aria-label="Close voice session"
          title="Close voice session"
        >
          <Icon name="close" size={20} />
        </button>

        <div className="live-voice-orb-wrapper">
          <div className={`live-voice-orb ${state}`}>
            <Icon name={state === "speaking" ? "volume" : "mic"} size={44} />
          </div>
        </div>

        <div className="live-voice-status">
          {state === "greeting" &&
            (lang === "hi"
              ? "लॉ साथी से जुड़ रहे हैं…"
              : lang === "kn"
                ? "ಲಾ ಸಾಥಿ ಜೊತೆ ಸಂಪರ್ಕಿಸಲಾಗುತ್ತಿದೆ…"
                : "Connecting to Law Saathi…")}
          {state === "listening" &&
            (lang === "hi"
              ? "सुन रहे हैं… अपना सवाल बोलिए"
              : lang === "kn"
                ? "ಕೇಳಿಸಿಕೊಳ್ಳುತ್ತಿದೆ… ಮಾತನಾಡಿ"
                : "Listening… speak naturally")}
          {state === "thinking" &&
            (lang === "hi"
              ? "कानूनों की जाँच कर रहे हैं…"
              : lang === "kn"
                ? "ಕಾಯ್ದೆಗಳನ್ನು ಪರಿಶೀಲಿಸುತ್ತಿದೆ…"
                : "Consulting statutory bare acts…")}
          {state === "speaking" &&
            (lang === "hi"
              ? "लॉ साथी बोल रहे हैं…"
              : lang === "kn"
                ? "ಲಾ ಸಾಥಿ ಮಾತನಾಡುತ್ತಿದೆ…"
                : "Law Saathi is speaking…")}
          {state === "idle" &&
            (lang === "hi"
              ? "तैयार — बोलने के लिए माइक दबाएँ"
              : lang === "kn"
                ? "ಸಿದ್ಧ — ಮಾತನಾಡಲು ಮೈಕ್ ಒತ್ತಿ"
                : "Ready — tap mic to speak")}
        </div>

        <div className="live-voice-hint">
          {lang === "hi"
            ? "हिन्दी, अंग्रेज़ी और कन्नड़ में बोलें"
            : lang === "kn"
              ? "ಕನ್ನಡ, ಇಂಗ್ಲಿಷ್ ಮತ್ತು ಹಿಂದಿಯಲ್ಲಿ ಮಾತನಾಡಿ"
              : "Speak naturally in English, Hindi, or Kannada"}
        </div>

        {(userQuery || agentAnswer) && (
          <div className="live-voice-captions">
            {userQuery && (
              <p className="live-voice-caption-user">
                <strong>You:</strong> {userQuery}
              </p>
            )}
            {agentAnswer && (
              <p className="live-voice-caption-agent">
                <strong>Law Saathi:</strong> {speakableText(agentAnswer)}
              </p>
            )}
          </div>
        )}

        <div className="live-voice-actions">
          {state === "listening" && (
            <button
              type="button"
              className={`live-voice-btn-mic ${isRecording ? "active" : ""}`}
              onClick={onStopSpeaking}
            >
              <Icon name="check" size={16} />
              <span>
                {lang === "hi"
                  ? "बोलना पूरा हुआ"
                  : lang === "kn"
                    ? "ಮಾತು ಮುಗಿದಿದೆ"
                    : "Done speaking"}
              </span>
            </button>
          )}
          <button
            type="button"
            className="live-voice-btn-end"
            onClick={onEndCall}
          >
            <Icon name="close" size={16} />
            <span>
              {lang === "hi"
                ? "कॉल समाप्त करें"
                : lang === "kn"
                  ? "ಕರೆ ಮುಕ್ತಾಯ"
                  : "End Call"}
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}

export default function Chat() {
  const router = useRouter();
  const { data: authSession, isPending: authPending } = authClient.useSession();
  // `null` means the list has not arrived yet — it is not the same as an empty
  // list. Starting at `[]` made the sidebar say "no chats yet" for the whole
  // time the list was on its way, and for a user with a long history that is
  // a false statement, not a loading state.
  const [sessions, setSessions] = useState<ChatSession[] | null>(null);
  // Set when the list could not be fetched at all. The sidebar then says
  // that, rather than claiming there are no chats.
  const [sessionsError, setSessionsError] = useState(false);
  // How much of the history is on screen, so "load more" knows where to
  // start and a delete can put the reader back where they were.
  const [sessionPage, setSessionPage] = useState(1);
  const [sessionTotal, setSessionTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const [lang, setLang] = useState("en");
  const [tone, setTone] = useState("simple");
  const [meta, setMeta] = useState<Record<number, Meta>>({});
  // The agent's real steps as they stream in, not a fixed animation. Empty
  // until the first one lands, and the warm-up list shows meanwhile.
  const [liveSteps, setLiveSteps] = useState<StreamStep[]>([]);
  // The verified answer, as it streams in. Null until the first piece arrives.
  // The steps and this are never both showing: once the text starts moving, the
  // step log has finished its job and would only compete for the same space.
  const [streaming, setStreaming] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [sideOpen, setSideOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const accountRef = useRef<HTMLDivElement>(null);

  // Voice. Both degrade quietly: no mic support hides the button, no TTS
  // support hides the speaker. A control that does nothing is worse than none.
  // The transcript lands in the input box, never straight into a question.
  const stt = useDictation(lang);
  const tts = useSpeechSynthesis(lang);
  const onTranscript = useCallback((text: string) => {
    setDraft((cur) => (cur.trim() ? `${cur.trim()} ${text}` : text));
    // The transcript goes to the end of whatever is already typed, so someone
    // who started a word and then reached for the mic does not lose it.
    inputRef.current?.focus();
    inputRef.current?.setSelectionRange(text.length, text.length);
  }, []);

  const busyMic = stt.state === "recording" || stt.state === "transcribing";

  // Real-time conversational Live Voice mode right inside the chat
  const [liveVoiceOpen, setLiveVoiceOpen] = useState(false);
  const [liveVoiceState, setLiveVoiceState] = useState<
    "greeting" | "listening" | "thinking" | "speaking" | "idle"
  >("idle");
  const [liveVoiceQuery, setLiveVoiceQuery] = useState("");
  const [liveVoiceReply, setLiveVoiceReply] = useState("");
  const liveVoiceActiveRef = useRef(false);

  const startListeningLoop = useCallback(() => {
    if (!liveVoiceActiveRef.current) return;
    setLiveVoiceState("listening");
    stt.start(async (text) => {
      if (!liveVoiceActiveRef.current) return;
      if (!text.trim()) {
        setLiveVoiceState("listening");
        return;
      }
      setLiveVoiceState("thinking");
      setLiveVoiceQuery(text);
      const res = await sendText(text);
      if (!liveVoiceActiveRef.current) return;
      if (res?.answer) {
        setLiveVoiceState("speaking");
        setLiveVoiceReply(res.answer);
        tts.speak(res.answer, Date.now(), () => {
          if (liveVoiceActiveRef.current) {
            startListeningLoop();
          }
        });
      } else {
        setLiveVoiceState("idle");
      }
    });
  }, [stt, tts]);

  const openLiveVoice = useCallback(() => {
    if (!authSession) {
      router.push("/login");
      return;
    }
    liveVoiceActiveRef.current = true;
    setLiveVoiceOpen(true);
    setLiveVoiceState("greeting");
    setLiveVoiceQuery("");
    setLiveVoiceReply("");

    const greetings = {
      hi: "नमस्ते, मैं लॉ साथी हूँ। पारिवारिक कानून के बारे में आप क्या पूछना चाहते हैं?",
      kn: "ನಮಸ್ಕಾರ, ನಾನು ಲಾ ಸಾಥಿ. ಕುಟುಂಬ ಕಾನೂನಿನ ಬಗ್ಗೆ ನಾನು ನಿಮಗೆ ಹೇಗೆ ಸಹಾಯ ಮಾಡಬಹುದು?",
      en: "Hello, I am Law Saathi. How can I help you with Indian family law today?",
    };
    const g = greetings[lang as keyof typeof greetings] || greetings.en;
    setLiveVoiceReply(g);
    tts.speak(g, 999999, () => {
      if (liveVoiceActiveRef.current) {
        startListeningLoop();
      }
    });
  }, [authSession, lang, router, startListeningLoop, tts]);

  const closeLiveVoice = useCallback(() => {
    liveVoiceActiveRef.current = false;
    stt.stop(() => {});
    tts.stop();
    setLiveVoiceOpen(false);
    setLiveVoiceState("idle");
  }, [stt, tts]);

  // Clicking anywhere else closes the account menu.
  useEffect(() => {
    if (!accountOpen) return;
    const onDown = (e: MouseEvent) => {
      if (!accountRef.current?.contains(e.target as Node)) setAccountOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [accountOpen]);

  const isNarrow = useCallback(() => {
    if (typeof window === "undefined") return false;
    return window.matchMedia("(max-width: 900px)").matches;
  }, []);

  // Redirect guests to login (middleware also guards /chat server-side)
  useEffect(() => {
    if (!authPending && !authSession) router.replace("/login");
  }, [authPending, authSession, router]);

  const refreshSessions = useCallback(async () => {
    try {
      const page = (await api(`/sessions?page=1&per_page=${SESSION_PAGE_SIZE}`)) as SessionPage;
      setSessions(page.items || []);
      setSessionPage(1);
      setSessionTotal(page.total || 0);
      setHasMore(!!page.has_more);
      setSessionsError(false);
    } catch {
      // A failed sidebar refresh is not worth interrupting the user over, but
      // the sidebar must not fall back to claiming there are no chats: "we
      // could not load them" and "you have none" are different facts.
      setSessionsError(true);
    }
  }, []);

  // The next page of history. Appended, not replaced, so the chats the
  // reader has already scrolled past stay where they were.
  const loadMoreSessions = useCallback(async () => {
    if (loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const next = sessionPage + 1;
      const page = (await api(
        `/sessions?page=${next}&per_page=${SESSION_PAGE_SIZE}`,
      )) as SessionPage;
      setSessions((cur) => {
        const seen = new Set((cur || []).map((s) => s.id));
        const added = (page.items || []).filter((s) => !seen.has(s.id));
        return [...(cur || []), ...added];
      });
      setSessionPage(next);
      setSessionTotal(page.total || 0);
      setHasMore(!!page.has_more);
    } catch {
      // The pages already on screen stay. The button stays, so the reader can
      // try again, and nothing pretends the list ended here.
      setSessionsError(true);
    } finally {
      setLoadingMore(false);
    }
  }, [hasMore, loadingMore, sessionPage]);

  // After a delete, the pages already on screen are fetched again so the
  // reader stays where they were, and the list does not suddenly shrink back
  // to one page.
  const reloadLoadedSessions = useCallback(async () => {
    const pages = Math.max(1, sessionPage);
    try {
      const fetched: ChatSession[] = [];
      let total = 0;
      let more = false;
      for (let p = 1; p <= pages; p++) {
        const page = (await api(
          `/sessions?page=${p}&per_page=${SESSION_PAGE_SIZE}`,
        )) as SessionPage;
        fetched.push(...(page.items || []));
        total = page.total || 0;
        more = !!page.has_more;
      }
      setSessions(fetched);
      setSessionTotal(total);
      setHasMore(more);
      setSessionsError(false);
    } catch {
      setSessionsError(true);
    }
  }, [sessionPage]);

  // The history is fetched on mount, in parallel with the session check
  // rather than after it. The session lives in an httpOnly cookie that the
  // browser sends with the request whether or not this code knows about the
  // session yet, so waiting for useSession() only put a round trip in front
  // of the list the user came to see.
  useEffect(() => {
    refreshSessions();
  }, [refreshSessions]);

  // Load the profile (no auto-create; new chat stays draft). The history is
  // not here: it is fetched on mount, above, so it is not waiting on this.
  useEffect(() => {
    if (authPending || !authSession) return;
    // Only tone is read. The saved language is deliberately ignored: the answer
    // follows the question, so loading a stored language would only put a
    // wrong value into the speech-synthesis voice until the user typed.
    api("/me")
      .then((u: { tone?: string }) => setTone(u.tone || "simple"))
      .catch(() => {});
    api("/me/memories")
      .then((m: { memories?: { key: string; value: string }[] }) => {
        const mem: Record<string, string> = {};
        (m.memories || []).forEach((item) => (mem[item.key] = item.value));
        if (mem.tone) setTone(mem.tone);
      })
      .catch(() => {});
  }, [authPending, authSession]);

  // Keep the reading voice in the language being typed, so "Read aloud" on a
  // Kannada answer is spoken by a Kannada voice rather than an English one.
  useEffect(() => {
    if (draft.trim().length > 1) {
      const d = detectLang(draft);
      if (d !== lang) setLang(d);
    }
  }, [draft, lang]);

  // Warm-up hint only. It never rotates on its own: the real step list replaces
// it as soon as the first one arrives, so what the user reads always matches
// what the agent actually did.
useEffect(() => {
  if (!loading) setLiveSteps([]);
  if (!loading) setStreaming(null);
}, [loading]);

function toggleSide() {
    if (isNarrow()) setSideOpen((v) => !v);
    else setCollapsed((v) => !v);
  }

  function openSession(id: number) {
    setSessionId(id);
    setMsgs([]);
    setMeta({});
    setError("");
    setSideOpen(false);
    api(`/sessions/${id}/messages`)
      .then((list: StoredMsg[]) => {
        setMsgs(list);
        setMeta(metaFromList(list));
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed"));
  }

  function newChat() {
    setSessionId(null);
    setMsgs([]);
    setMeta({});
    setError("");
    setSideOpen(false);
  }

  async function deleteSession(id: number) {
    if (!window.confirm(t(lang, "deleteChat"))) return;
    try {
      await api(`/sessions/${id}`, { method: "DELETE" });
      if (id === sessionId) newChat();
      // The list is refreshed either way. Deleting the chat that was open
      // used to leave it in the sidebar, because only the "another chat" case
      // refreshed the list.
      //
      // The pages already on screen are fetched again rather than the first
      // page alone, so a reader who had scrolled down to page three is not
      // thrown back to the top of the history by their own deletion.
      await reloadLoadedSessions();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed");
    }
  }

  async function sendText(text: string) {
    if (!text.trim() || loading) return;
    setError("");
    const query = text.trim();
    // The answer comes back in the language of the question. There is no
    // preference to consult and nothing for the user to have set wrong.
    const sendLang = detectLang(query);
    // Show the question immediately, even while the session is being created
    // on the first message of a chat. Otherwise loading starts (and the step
    // list renders) before the user's message has been appended, so the first
    // thing on screen is the process instead of the question.
    const userMsg: Msg = { id: Date.now(), role: "user", content: query, lang: sendLang };
    setMsgs((prev) => [...prev, userMsg]);
    setDraft("");
    setLoading(true);
    try {
      // Lazy-create the session on first message (keeps sidebar clean)
      let sid = sessionId;
      if (sid === null) {
        const s = (await api("/sessions", {
          method: "POST",
          body: JSON.stringify({ title: query.slice(0, 60) }),
        })) as ChatSession;
        sid = s.id;
        setSessionId(sid);
        // The chat exists from this moment. The sidebar used to wait for the
        // whole answer to finish streaming before it appeared, so for the
        // thirty to ninety seconds the answer takes the sidebar still said
        // there were no chats.
        refreshSessions();
      }
      // Streamed: each agent step lands as it happens, so the page shows real
      // progress instead of a fixed animation. If the stream is cut, askStream
      // reads the saved answer back rather than asking again — one question
      // never produces two answers.
      const answerObj = await askStream(
        `/sessions/${sid}/ask/stream`,
        { query, lang: sendLang, tone },
        {
          onStep: (s) => setLiveSteps((prev) => [...prev, s]),
          // Text the verifier has already approved. The steps stop here: from
          // this moment the useful thing on screen is the answer itself, not the
          // list of what produced it.
          onAnswerText: (chunk) => {
            setStreaming((cur) => (cur === null ? chunk : cur + chunk));
            setLiveSteps([]);
          },
        },
      );
      // The server reports the language it actually wrote in, which is not
      // always the guess we sent. Trust the server: it decides from the
      // question's script, and "Read aloud" needs the real one.
      const answerLang = answerObj.lang || sendLang;
      const tmeta: Meta = {
        trace: answerObj.trace || [],
        steps: answerObj.trace_detail || [],
        citations: answerObj.citations || [],
        sources: answerObj.citation_sources || [],
      };
      const botId = Date.now() + 1;
      const botMsg: Msg = {
        id: botId,
        role: "assistant",
        content: answerObj.answer,
        lang: answerLang,
      };
      // The streaming card has already shown this answer while it arrived. Drop
      // it now, in the same update as the final card, so the reader never sees
      // the reply twice (once live, once persisted).
      setStreaming(null);
      setLiveSteps([]);
      setMsgs((prev) => [...prev, botMsg]);
      setMeta((prev) => ({ ...prev, [botId]: tmeta }));
      // Re-read the thread so ids match the server. Guarded against a slow
      // response landing after a newer question: appending this list blindly
      // would throw away whatever the user has since asked.
      api(`/sessions/${sid}/messages`)
        .then((list: StoredMsg[]) => {
          if (!list.length) return;
          setMsgs((prev) => (list.length >= prev.length ? list : prev));
          const next = metaFromList(list);
          // Stored citations for the whole thread, then re-attach this answer's
          // live trace to its real server id (ids change on reload).
          const match = list.find(
            (m) => m.role === "assistant" && m.content === answerObj.answer,
          );
          if (match) next[match.id] = tmeta;
          setMeta(next);
        })
        .catch(() => {});
      refreshSessions();
      return answerObj;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
      return null;
    } finally {
      setLoading(false);
    }
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    await sendText(draft);
  }

  async function signOut() {
    try {
      await authClient.signOut();
    } catch {
      // Local sign-out is still correct if the network call fails.
    }
    router.push("/");
  }

  if (authPending || !authSession) {
    return (
      <div className="chat-layout">
        <div className="chat-gate">{t(lang, "checking")}</div>
      </div>
    );
  }

  const isEmpty = msgs.length === 0 && !loading;

  // The account menu shows a name; Neon Auth gives an email, so take the part
  // before the @ and capitalise it.
  const displayName =
    (authSession?.user?.name as string | undefined) ||
    ((authSession?.user?.email as string | undefined)?.split("@")[0] || "You");
  const initial = displayName.slice(0, 1).toUpperCase();

  return (
    <div className={`chat-layout${collapsed ? " side-hidden" : ""}`}>
      {sideOpen && <div className="side-backdrop" onClick={() => setSideOpen(false)} />}

      <aside className={`sidebar${sideOpen ? " open" : ""}`} aria-label={t(lang, "history")}>
        <div className="side-toprow">
          <button type="button" className="side-new" onClick={newChat}>
            <Icon name="plus" size={17} />
            {t(lang, "newChat")}
          </button>
          <button
            type="button"
            className="side-hide"
            onClick={toggleSide}
            aria-label={collapsed ? "Show history" : "Hide history"}
            title={collapsed ? "Show history" : "Hide history"}
          >
            <Icon name="chevronDown" size={18} className={collapsed ? "flip-x" : "flip-y"} />
          </button>
        </div>

        <div className="side-list">
          {(sessions ?? []).map((s) => (
            <div key={s.id} className={`side-item${s.id === sessionId ? " active" : ""}`}>
              <button
                type="button"
                className="side-open"
                onClick={() => openSession(s.id)}
                title={s.title}
              >
                <Icon name="chat" size={15} />
                <span>{s.title || t(lang, "newChat")}</span>
              </button>
              <button
                type="button"
                className="side-del"
                aria-label={t(lang, "confirmDelete")}
                onClick={() => deleteSession(s.id)}
              >
                <Icon name="close" size={15} />
              </button>
            </div>
          ))}
          {/* Three states, three different sentences. The list being on its way,
              the list having failed, and the list being empty are not the
              same thing, and the sidebar used to say "no chats yet" for all
              three. */}
          {sessions === null && !sessionsError && (
            <p className="side-empty side-pending" aria-live="polite">
              {t(lang, "sideLoading")}
            </p>
          )}
          {sessions === null && sessionsError && (
            <p className="side-empty" role="status">
              {t(lang, "sideError")}
            </p>
          )}
          {sessions !== null && sessions.length === 0 && (
            <p className="side-empty">{t(lang, "noChats")}</p>
          )}
          {/* More history. The count is in the label, so the reader knows how
              much is behind the button and not only that there is more. */}
          {sessions !== null && hasMore && (
            <button
              type="button"
              className="side-more"
              onClick={loadMoreSessions}
              disabled={loadingMore}
            >
              {loadingMore ? t(lang, "sideLoadingMore") : t(lang, "loadMore")}
              {sessionTotal > 0 && !loadingMore && (
                <span className="side-more-count">
                  {t(lang, "moreChats", { n: sessionTotal - sessions.length })}
                </span>
              )}
            </button>
          )}
        </div>

        {/* Account control. This replaces the old "Home" link, which pointed at
            a page that no longer existed and duplicated the nav anyway. */}
        <div className="side-account" ref={accountRef}>
          <button
            type="button"
            className="side-account-btn"
            onClick={() => setAccountOpen((v) => !v)}
            aria-expanded={accountOpen}
            aria-haspopup="menu"
          >
            <span className="side-avatar">{initial}</span>
            {/* Name only. The line under it used to read "English", which said
                two wrong things: that the user had chosen a language, and that
                the answer would arrive in it whatever they asked. The answer
                comes back in the language of the question. */}
            <span className="side-label side-account-text">
              <b>{displayName}</b>
            </span>
            <Icon name="chevronDown" size={15} className="side-account-caret" />
          </button>

          {/* Only sign out. The menu used to carry an answer-language picker, a
              simple/detailed toggle and a link back to the site. All three were
              removed on purpose: the answer already comes back in whatever
              language the question was asked in, so a language setting told the
              user their own question was in the "wrong" language; the tone
              toggle changed nothing they could see; and the site link duplicated
              the logo. What is left is the one thing this menu is for. */}
          {accountOpen && (
            <div className="side-menu" role="menu">
              <button
                type="button"
                role="menuitem"
                className="side-menu-lang side-menu-danger"
                onClick={signOut}
              >
                <Icon name="logout" size={15} />
                {t(lang, "signOut")}
              </button>
            </div>
          )}
        </div>
      </aside>

      <div className="chat-shell">
        <header className="chat-top">
          <div className="chat-top-inner">
            <button
              type="button"
              className="side-toggle"
              onClick={toggleSide}
              aria-label={t(lang, "history")}
              title={t(lang, "history")}
            >
              <Icon name="list" size={20} />
            </button>
            <Logo size={40} />
            <span className="chat-top-tag">Family Law, Explained in Simple Words.</span>
            <button
              type="button"
              className="chat-top-voice-btn"
              onClick={openLiveVoice}
              title="Start real-time voice call"
              aria-label="Start real-time voice call"
            >
              <Icon name="mic" size={14} />
              <span>Live Voice</span>
            </button>
          </div>
        </header>

        <div className="chat-main">
          {isEmpty ? (
            <div className="chat-empty">
              <Image
                src="/images/chat-empty.webp"
                alt="Scales of justice with two speech bubbles"
                width={400}
                height={400}
                // Drawn at up to 200px, so the browser is told to fetch half
                // that on a 1x screen. A plain `<img>` here was shipping the
                // 522 KB full-size PNG on every visit to an empty chat.
                sizes="(max-width: 640px) 140px, 200px"
                priority
              />
              <h2>{t(lang, "emptyTitle")}</h2>
              <p className="chat-empty-hint">{t(lang, "emptyHint")}</p>
              <div className="chips">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    type="button"
                    className="chip"
                    onClick={() => sendText(s)}
                    disabled={loading}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="thread">
              {msgs.map((m) =>
                m.role === "user" ? (
                  <div key={m.id} className="bubble-user">
                    {m.content}
                  </div>
                ) : (
                  <AssistantBlock key={m.id} msg={m} m={meta[m.id]} />
                ),
              )}
              {streaming !== null && <StreamingAnswer text={streaming} />}
              {/* The step log is hidden the moment the answer starts arriving:
                  the two together would push the text the user came for below
                  the fold, and by then the steps have nothing left to say. */}
              {loading && streaming === null && (
                <div className="thinking-live" aria-live="polite">
                  <div className="live-head">
                    <span className="pulse" />
                    {liveSteps.length
                      ? t(lang, "working")
                      : t(lang, "starting")}
                  </div>
                  {/* Real steps once they arrive; the warm-up list only covers
                      the first moment, before the agent has reported anything. */}
                  {liveSteps.length ? (
                    <ol className="live-steps">
                      {liveSteps.map((s, i) => (
                        <li
                          key={`${s.node}-${i}`}
                          className={i === liveSteps.length - 1 ? "live-on" : ""}
                        >
                          <strong>{nodeLabel(s.node, lang)}</strong>
                          <span className="step-detail">{s.detail}</span>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <ol className="live-steps">
                      {WARMUP_KEYS.map((k, i) => (
                        <li key={k} className={i === 0 ? "live-on" : ""}>
                          {t(lang, k)}
                        </li>
                      ))}
                    </ol>
                  )}
                </div>
              )}
            </div>
          )}
          {error && <p className="alert alert-error">{error}</p>}
        </div>

        <div className="composer">
          <form onSubmit={send} className="composer-row">
            <input
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={
                stt.state === "recording"
                  ? "Listening… tap the mic when you are done"
                  : t(lang, "askPlaceholder")
              }
              aria-label="Question"
            />
            {/* Mic sits inside the pill, immediately left of the send arrow.
                Someone who cannot type reaches for the same control they use to
                send, not for a separate labelled button across the page — and
                on a phone the two controls then share one row of thumb reach.

                One button, two states, and the second press is always "stop".
                Recording does not end when the speaker pauses to think, so
                there has to be an explicit end — silence is not consent to
                send half a question. */}
            {stt.supported && (
              <button
                type="button"
                className={`composer-mic${stt.state === "recording" ? " on" : ""}${
                  stt.state === "transcribing" ? " busy" : ""
                }`}
                onClick={() =>
                  stt.state === "recording" ? stt.stop(onTranscript) : stt.start(onTranscript)
                }
                disabled={loading || stt.state === "transcribing"}
                aria-label={
                  stt.state === "recording"
                    ? "Stop recording"
                    : stt.state === "transcribing"
                      ? "Transcribing"
                      : "Ask by voice"
                }
                title={
                  stt.state === "recording"
                    ? "Stop recording"
                    : stt.state === "transcribing"
                      ? t(lang, "transcribing")
                      : "Ask by voice"
                }
              >
                <Icon
                  name={
                    stt.state === "recording"
                      ? "close"
                      : stt.state === "transcribing"
                        ? "clock"
                        : "mic"
                  }
                  size={18}
                />
              </button>
            )}
            <button
              className="composer-send"
              type="submit"
              disabled={loading || !draft.trim()}
              aria-label="Send question"
              title="Send"
            >
              <Icon name="send" size={19} />
            </button>
          </form>

          {/* While recording, the only thing worth saying is that it is still on and
            how much is left before it stops by itself. The words come after. */}
          {stt.state === "recording" && (
            <p className="composer-transcript" aria-live="polite">
              <span className="rec-dot" aria-hidden="true" />
              {/* The number in the middle of the sentence does not move, but the
                  word order around it does: Hindi puts the verb last, Kannada
                  wants its postposition attached. So the whole sentence is
                  localised, not just the verb. */}
              {recordingText(lang, MAX_RECORDING_SECONDS, stt.seconds)}
            </p>
          )}
          {stt.state === "transcribing" && (
            <p className="composer-transcript" aria-live="polite">
              {t(lang, "transcribing")}
            </p>
          )}
          {stt.error && (
            <p className="composer-note" role="status">
              {stt.error}
            </p>
          )}
        </div>
      </div>

      {liveVoiceOpen && (
        <LiveVoiceOverlay
          state={liveVoiceState}
          userQuery={liveVoiceQuery}
          agentAnswer={liveVoiceReply}
          isRecording={stt.state === "recording"}
          lang={lang}
          onStopSpeaking={() => {
            stt.stop(async (text) => {
              if (!liveVoiceActiveRef.current) return;
              if (!text.trim()) return;
              setLiveVoiceState("thinking");
              setLiveVoiceQuery(text);
              const res = await sendText(text);
              if (!liveVoiceActiveRef.current) return;
              if (res?.answer) {
                setLiveVoiceState("speaking");
                setLiveVoiceReply(res.answer);
                tts.speak(res.answer, Date.now(), () => {
                  if (liveVoiceActiveRef.current) startListeningLoop();
                });
              }
            });
          }}
          onEndCall={closeLiveVoice}
        />
      )}
    </div>
  );
}