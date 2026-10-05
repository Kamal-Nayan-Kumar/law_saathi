"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { authClient } from "@/lib/auth/client";
import { api } from "@/lib/api";
import { askStream, type AskResult, type StreamStep } from "@/lib/stream";
import { useSpeechToText, useSpeechSynthesis } from "@/lib/voice";
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

// Shown before the first step arrives. The real steps replace this list as the
// agent reports them, so the user always sees what Saathi is actually doing
// rather than a fixed animation that could disagree with it.
const WARMUP = [
  "Understanding your question…",
  "Choosing which law applies…",
  "Reading the bare acts…",
  "Checking every claim…",
  "Writing the answer…",
];

/** Friendlier name for a node, matching what the step detail says. */
const NODE_LABEL: Record<string, string> = {
  contextualize: "Reading the conversation",
  intent: "Understanding the question",
  planner: "Choosing the law",
  tools: "Searching the bare acts",
  reason: "Writing an explanation",
  verifier: "Checking the citations",
  response: "Preparing your answer",
};

const LANG_NAMES: Record<string, string> = {
  en: "English",
  hi: "Hindi",
  kn: "Kannada",
};

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

function sourceTag(type: string): { label: string; kind: string } {
  return SOURCE_TAGS[type] || { label: "source", kind: "other" };
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
            How Saathi worked this out
            <span className="think-count">{m.steps.length} steps</span>
          </button>
          {showThink && (
            <ol className="think-steps">
              {m.steps.map((s, i) => (
                <li key={`${s.node}-${i}`}>
                  <strong>{NODE_LABEL[s.node] || s.node}</strong>
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
            aria-label={speaking ? "Stop reading this answer" : "Read this answer aloud"}
          >
            <Icon name={speaking ? "close" : "volume"} size={16} />
            {speaking ? "Stop" : "Read aloud"}
          </button>
        )}
        {m && m.citations.length > 0 && (
          <span className="ans-foot-note">
            {m.citations.length} source{m.citations.length === 1 ? "" : "s"}
          </span>
        )}
      </div>

      {m && m.citations.length > 0 && (
        <div className="src">
          <p className="src-head">
            <Icon name="book" size={14} />
            Sources ({m.citations.length})
          </p>
          <ol className="src-list">
            {m.citations.map((c, i) => {
              const tag = m.sources[i] ? sourceTag(m.sources[i]) : null;
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

export default function Chat() {
  const router = useRouter();
  const { data: authSession, isPending: authPending } = authClient.useSession();
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [draft, setDraft] = useState("");
  const [lang, setLang] = useState("en");
  const [tone, setTone] = useState("simple");
  const [meta, setMeta] = useState<Record<number, Meta>>({});
  // The agent's real steps as they stream in, not a fixed animation. Empty
  // until the first one lands, and the warm-up list shows meanwhile.
  const [liveSteps, setLiveSteps] = useState<StreamStep[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [sideOpen, setSideOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [accountOpen, setAccountOpen] = useState(false);
  const accountRef = useRef<HTMLDivElement>(null);

  // Voice. Both degrade quietly: no mic support hides the button, no TTS
  // support hides the speaker. A control that does nothing is worse than none.
  const stt = useSpeechToText(lang);
  const tts = useSpeechSynthesis(lang);

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
    api("/me")
      .then((u: { preferred_lang?: string; tone?: string }) => {
        setLang(u.preferred_lang || "en");
        setTone(u.tone || "simple");
      })
      .catch(() => {});
    // The API exposes memories under /me/memories; "/memories" 404s, which
    // silently dropped the saved language and tone on every load.
    api("/me/memories")
      .then((m: { memories?: { key: string; value: string }[] }) => {
        const mem: Record<string, string> = {};
        (m.memories || []).forEach((item) => (mem[item.key] = item.value));
        if (mem.tone) setTone(mem.tone);
        if (mem.preferred_lang) setLang(mem.preferred_lang);
      })
      .catch(() => {});
    refreshSessions();
  }, [authPending, authSession, refreshSessions]);

  // Auto-detect on draft change
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
    if (!window.confirm("Delete this chat?")) return;
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
    setLoading(true);
    const query = text.trim();
    const sendLang = detectLang(query) !== "en" ? detectLang(query) : lang;
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
      const userMsg: Msg = { id: Date.now(), role: "user", content: query, lang: sendLang };
      setMsgs((prev) => [...prev, userMsg]);
      setDraft("");
      // Streamed: each agent step lands as it happens, so the page can show
      // real progress instead of a fixed animation for the whole 15 seconds.
      // askStream falls back to the plain JSON endpoint by itself.
      const answerObj = await askStream(
        `/sessions/${sid}/ask/stream`,
        { query, lang: sendLang, tone },
        { onStep: (s) => setLiveSteps((prev) => [...prev, s]) },
      );
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
        lang: sendLang,
      };
      setMsgs((prev) => [...prev, botMsg]);
      setMeta((prev) => ({ ...prev, [botId]: tmeta }));
      api(`/sessions/${sid}/messages`)
        .then((list: StoredMsg[]) => {
          if (!list.length) return;
          setMsgs(list);
          // Stored citations for the whole thread, then re-attach this answer's
          // live trace to its real server id (ids change on reload).
          const match = list.find(
            (m) => m.role === "assistant" && m.content === answerObj.answer,
          );
          const next = metaFromList(list);
          if (match) next[match.id] = tmeta;
          delete next[botId];
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

  async function savePref(key: string, value: string) {
    try {
      await api("/me", { method: "PUT", body: JSON.stringify({ [key]: value }) });
      await api("/me/memories", {
        method: "PUT",
        body: JSON.stringify([{ key, value }]),
      });
      if (key === "preferred_lang") setLang(value);
      if (key === "tone") setTone(value);
    } catch {
      // A preference that fails to save is still applied for this session; the
      // user should not be interrupted for it.
    }
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
        <div className="chat-gate">Checking your sign-in…</div>
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

      <aside className={`sidebar${sideOpen ? " open" : ""}`} aria-label="Chat history">
        <div className="side-toprow">
          <button type="button" className="side-new" onClick={newChat}>
            <Icon name="plus" size={17} />
            New chat
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
                <span>{s.title || "New chat"}</span>
              </button>
              <button
                type="button"
                className="side-del"
                aria-label={`Delete ${s.title}`}
                onClick={() => deleteSession(s.id)}
              >
                <Icon name="close" size={15} />
              </button>
            </div>
          ))}
          {sessions.length === 0 && (
            <p className="side-empty">No chats yet — ask something to start.</p>
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
            <span className="side-label side-account-text">
              <b>{displayName}</b>
              <small>{LANG_NAMES[lang] ?? "English"}</small>
            </span>
            <Icon name="chevronDown" size={15} className="side-account-caret" />
          </button>

          {accountOpen && (
            <div className="side-menu" role="menu">
              <p className="side-menu-head">Answer language</p>
              <div className="side-menu-langs">
                {(["en", "hi", "kn"] as const).map((code) => (
                  <button
                    key={code}
                    type="button"
                    role="menuitemradio"
                    aria-checked={lang === code}
                    className="side-menu-lang"
                    onClick={() => {
                      setLang(code);
                      savePref("preferred_lang", code);
                    }}
                  >
                    <Icon name="globe" size={15} />
                    {LANG_NAMES[code]}
                    {lang === code && <Icon name="check" size={15} className="side-menu-tick" />}
                  </button>
                ))}
              </div>
              <button
                type="button"
                role="menuitem"
                className="side-menu-lang"
                onClick={() => setTone(tone === "simple" ? "detailed" : "simple")}
              >
                <Icon name="document" size={15} />
                {tone === "simple" ? "Simple answers" : "Detailed answers"}
              </button>
              <Link href="/" role="menuitem" className="side-menu-lang">
                <Icon name="arrowRight" size={15} className="flip-180" />
                Back to the site
              </Link>
              <button
                type="button"
                role="menuitem"
                className="side-menu-lang side-menu-danger"
                onClick={signOut}
              >
                <Icon name="logout" size={15} />
                Sign out
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
              aria-label="Toggle chat history"
              title="Chat history"
            >
              <Icon name="list" size={20} />
            </button>
            <Logo size={30} />
            {/* Voice sits in the header, not buried in the composer: for
                someone who cannot easily type, the mic is the way in. */}
            {stt.supported && (
              <button
                type="button"
                className={`chat-mic${stt.state === "listening" ? " on" : ""}`}
                onClick={() =>
                  stt.state === "listening" ? stt.stop() : stt.start(sendText)
                }
                disabled={loading}
                aria-label={
                  stt.state === "listening" ? "Stop listening" : "Ask by voice"
                }
              >
                <Icon
                  name={stt.state === "listening" ? "close" : "mic"}
                  size={17}
                />
                <span>
                  {stt.state === "listening" ? "Stop" : "Ask by voice"}
                </span>
              </button>
            )}
            <span className="chat-top-tag">Family law · EN / HI / KN</span>
          </div>
        </header>

        <div className="chat-main">
          {isEmpty ? (
            <div className="chat-empty">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src="/images/chat-empty.png"
                alt="Scales of justice with two speech bubbles"
                width={1254}
                height={1254}
              />
              <h2>Ask about family law, in any language.</h2>
              <p className="chat-empty-hint">Try one of these to start:</p>
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
              {loading && (
                <div className="thinking-live" aria-live="polite">
                  <div className="live-head">
                    <span className="pulse" />
                    {liveSteps.length
                      ? "Working on it…"
                      : "Getting to your question…"}
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
                          <strong>{NODE_LABEL[s.node] || s.node}</strong>
                          <span className="step-detail">{s.detail}</span>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <ol className="live-steps">
                      {WARMUP.map((s, i) => (
                        <li key={s} className={i === 0 ? "live-on" : ""}>
                          {s}
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
            {/* Mic lives in the header now; the composer stays a single pill. */}
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder={
                stt.state === "listening"
                  ? "Listening… speak now"
                  : "Ask a question about family law…"
              }
              aria-label="Question"
            />
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

          {/* Live transcript, so the user can see the mic is hearing them. */}
          {stt.state === "listening" && stt.interim && (
            <p className="composer-transcript" aria-live="polite">
              {stt.interim}
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