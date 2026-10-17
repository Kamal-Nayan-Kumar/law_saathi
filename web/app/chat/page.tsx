"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { authClient } from "@/lib/auth/client";
import { api } from "@/lib/api";
import { askStream, type AskResult, type StreamStep } from "@/lib/stream";
import { useDictation, useSpeechSynthesis, MAX_RECORDING_SECONDS } from "@/lib/voice";
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

type TraceStep = StreamStep;

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

function t(lang: string, key: UiKey): string {
  const bank = UI[key];
  if (lang === "hi" || lang === "kn") return bank[lang];
  return bank.en;
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
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
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
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        {/* A caret, so it is obvious the reply is still coming rather than
            simply short. */}
        <span className="caret" aria-hidden="true" />
      </div>
    </div>
  );
}

export default function Chat() {
  const router = useRouter();
  const { data: authSession, isPending: authPending } = authClient.useSession();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
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
      const list = (await api("/sessions")) as ChatSession[];
      setSessions([...list].reverse());
    } catch {
      // A failed sidebar refresh is not worth interrupting the user over.
    }
  }, []);

  // Load profile + sidebar history (no auto-create; new chat stays draft)
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
    refreshSessions();
  }, [authPending, authSession, refreshSessions]);

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
      else refreshSessions();
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
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
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
          {sessions.map((s) => (
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
          {sessions.length === 0 && (
            <p className="side-empty">{t(lang, "noChats")}</p>
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
    </div>
  );
}