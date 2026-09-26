"use client";
import { useEffect, useState, useCallback } from "react";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { authClient } from "@/lib/auth/client";
import { api } from "@/lib/api";

type Msg = {
  id: number;
  role: string;
  content: string;
  lang: string;
};

type ChatSession = {
  id: number;
  title: string;
};

type Answer = {
  answer: string;
  clarification: boolean;
  citations: string[];
  citation_sources: string[];
  provider: string;
  retries: number;
  trace: string[];
};

const SUGGESTIONS = [
  "How do I get a mutual-consent divorce?",
  "पत्नी भरण-पोषण कैसे माँग सकती है?",
  "ಮಗುವಿನ ಕಸ್ಟಡಿ ಯಾರಿಗೆ ಸಿಗುತ್ತದೆ?",
];

const STAGES = ["Planning…", "Retrieving law…", "Verifying…", "Writing answer…"];

function detectLang(text: string): "en" | "hi" | "kn" {
  if (/\u0C80-\u0CFF/.test(text)) return "kn";
  if (/\u0900-\u097F/.test(text)) return "hi";
  return "en";
}

type Meta = { trace: string[]; citations: string[]; sources: string[] };

// Turn each known citation string in the answer into a numbered anchor
// link that jumps to the matching item in that answer's Sources list.
function linkifyCitations(text: string, citations: string[], msgId: number): string {
  let out = text;
  citations.forEach((c, i) => {
    if (!c || c.length > 80 || /[\[\]]/.test(c)) return;
    const esc = c.replace(/[.*+?^${}()|\\]/g, "\\$&");
    out = out.replace(new RegExp(esc), `[${c}](#src-${msgId}-${i + 1})`);
  });
  return out;
}

function AssistantBlock({ msg, m }: { msg: Msg; m?: Meta }) {
  const [showThink, setShowThink] = useState(false);
  const [showSrc, setShowSrc] = useState(false);
  const text =
    m && m.citations.length ? linkifyCitations(msg.content, m.citations, msg.id) : msg.content;

  function onCite(e: React.MouseEvent) {
    const a = (e.target as HTMLElement).closest('a[href^="#src-"]');
    if (!a) return;
    e.preventDefault();
    setShowSrc(true);
    const id = (a.getAttribute("href") || "").slice(1);
    setTimeout(() => {
      document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "center" });
    }, 60);
  }

  return (
    <div className="ans-card">
      <div className="md" onClick={onCite}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
      </div>
      {m && m.trace.length > 0 && (
        <div className="think">
          <button type="button" className="think-toggle" onClick={() => setShowThink((v) => !v)}>
            {showThink ? "▾ Thinking" : "▸ Thinking"}
          </button>
          {showThink && (
            <ol className="think-steps">
              {m.trace.map((t) => (
                <li key={t}>
                  <strong>{t}</strong> — completed
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
      {m && m.citations.length > 0 && (
        <div className="src">
          <button type="button" className="src-toggle" onClick={() => setShowSrc((v) => !v)}>
            {showSrc ? `▾ Sources (${m.citations.length})` : `▸ Sources (${m.citations.length})`}
          </button>
          {showSrc && (
            <ol className="src-list">
              {m.citations.map((c, i) => (
                <li key={i} id={`src-${msg.id}-${i + 1}`} className="src-item">
                  <span className="src-n">{i + 1}</span>
                  <span>{c}</span>
                  {m.sources[i] && (
                    <span className="src-tag">{m.sources[i] === "bare_act" ? "bare act" : "web"}</span>
                  )}
                </li>
              ))}
            </ol>
          )}
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
  const [stage, setStage] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [sideOpen, setSideOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  function toggleSide() {
    if (window.matchMedia("(max-width: 860px)").matches) setSideOpen((v) => !v);
    else setCollapsed((v) => !v);
  }

  // Redirect guests to login (middleware also guards /chat server-side)
  useEffect(() => {
    if (!authPending && !authSession) router.replace("/login");
  }, [authPending, authSession, router]);

  const refreshSessions = useCallback(async () => {
    try {
      const list = (await api("/sessions")) as ChatSession[];
      setSessions([...list].reverse());
    } catch (e) {}
  }, []);

  // Load profile + sidebar history (no auto-create; new chat stays draft)
  useEffect(() => {
    if (authPending || !authSession) return;
    api("/me")
      .then((u: any) => {
        setLang(u.preferred_lang || "en");
        setTone(u.tone || "simple");
      })
      .catch(() => {});
    api("/memories")
      .then((m: any) => {
        const mem: Record<string, string> = {};
        (m.memories || []).forEach((item: any) => (mem[item.key] = item.value));
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
      if (d !== lang) {
        setLang(d);
      }
    }
  }, [draft, lang]);

  // Rotate the "working…" stage label while an answer is being generated.
  // Stages are a client-side progress hint; the real node trace lands in Thinking after.
  useEffect(() => {
    if (!loading) return;
    setStage(0);
    const t = setInterval(() => setStage((s) => (s + 1) % STAGES.length), 1800);
    return () => clearInterval(t);
  }, [loading]);

  function openSession(id: number) {
    setSessionId(id);
    setMsgs([]);
    setError("");
    setSideOpen(false);
    api(`/sessions/${id}/messages`)
      .then((list: Msg[]) => setMsgs(list))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed"));
  }

  function newChat() {
    setSessionId(null);
    setMsgs([]);
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
          body: JSON.stringify({ title: "New chat" }),
        })) as ChatSession;
        sid = s.id;
        setSessionId(sid);
      }
      const userMsg: Msg = { id: Date.now(), role: "user", content: query, lang: sendLang };
      setMsgs((prev) => [...prev, userMsg]);
      setDraft("");
      const resp = await api(`/sessions/${sid}/ask`, {
        method: "POST",
        body: JSON.stringify({ query, lang: sendLang, tone }),
      });
      const answerObj = resp as Answer;
      const tmeta: Meta = {
        trace: answerObj.trace || [],
        citations: answerObj.citations || [],
        sources: answerObj.citation_sources || [],
      };
      const botId = Date.now() + 1;
      const botMsg: Msg = { id: botId, role: "assistant", content: answerObj.answer, lang: sendLang };
      setMsgs((prev) => [...prev, botMsg]);
      setMeta((prev) => ({ ...prev, [botId]: tmeta }));
      api(`/sessions/${sid}/messages`)
        .then((list: Msg[]) => {
          if (!list.length) return;
          setMsgs(list);
          // Re-attach this answer's trace/sources to its real server id
          const match = list.find((m) => m.role === "assistant" && m.content === answerObj.answer);
          if (match) {
            setMeta((prev) => {
              const next = { ...prev, [match.id]: tmeta };
              delete next[botId];
              return next;
            });
          }
        })
        .catch(() => {});
      refreshSessions();
    } catch (err: any) {
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
    } catch (e) {}
  }

  async function signOut() {
    try {
      await authClient.signOut();
    } catch (e) {}
    router.push("/");
  }

  if (authPending || !authSession) {
    return (
      <main>
        <div className="card">
          <p style={{ color: "var(--muted)" }}>Checking sign-in… redirecting to login.</p>
        </div>
      </main>
    );
  }

  const isEmpty = msgs.length === 0 && !loading;

  return (
    <div className={`chat-layout${collapsed ? " side-hidden" : ""}`}>
      {sideOpen && <div className="side-backdrop" onClick={() => setSideOpen(false)} />}
      {/* History sidebar */}
      <aside className={`sidebar${sideOpen ? " open" : ""}`} aria-label="Chat history">
        <button type="button" className="side-new" onClick={newChat}>
          ＋ New chat
        </button>
        <p className="side-label">Recents</p>
        <div className="side-list">
          {sessions.map((s) => (
            <div key={s.id} className={`side-item${s.id === sessionId ? " active" : ""}`}>
              <button type="button" className="side-open" onClick={() => openSession(s.id)} title={s.title}>
                {s.title || "New chat"}
              </button>
              <button
                type="button"
                className="side-del"
                aria-label={`Delete ${s.title}`}
                onClick={() => deleteSession(s.id)}
              >
                ×
              </button>
            </div>
          ))}
          {sessions.length === 0 && (
            <p className="side-empty">No chats yet — ask something to start.</p>
          )}
        </div>
        <a className="side-home" href="/">
          ⌂ Home
        </a>
      </aside>

      <div className="chat-shell">
        {/* Chat header (replaces marketing nav on this page) */}
        <header className="chat-top">
          <div className="chat-top-inner">
            <button type="button" className="side-toggle" onClick={toggleSide} aria-label="Toggle history">
              ☰
            </button>
            <img src="/images/logo.png" alt="Law Saathi logo" className="chat-logo" />
            <div className="chat-title">
              <b>
                Law <span>Saathi</span>
              </b>
              <p>Ask about family law — in any language.</p>
            </div>
            <div className="chat-controls">
              <select value={lang} onChange={(e) => { setLang(e.target.value); savePref("preferred_lang", e.target.value); }} aria-label="Chat language">
                <option value="en">EN</option>
                <option value="hi">HI</option>
                <option value="kn">KN</option>
              </select>
              <select value={tone} onChange={(e) => { setTone(e.target.value); savePref("tone", e.target.value); }} aria-label="Answer tone">
                <option value="simple">Simple</option>
                <option value="detailed">Detailed</option>
              </select>
              <button type="button" className="chat-signout" onClick={signOut}>
                Sign out
              </button>
            </div>
          </div>
        </header>

        {/* Thread */}
        <div className="chat-main">
          {isEmpty ? (
            <div className="chat-empty">
              <img
                src="/images/chat-empty.png"
                alt="Law Saathi assistant answering family-law questions in three languages"
              />
              <p className="chat-empty-hint">Ask your first question — try one of these:</p>
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
                  <div key={m.id} className="bubble-user" style={{ whiteSpace: "pre-wrap" }}>
                    {m.content}
                  </div>
                ) : (
                  <AssistantBlock key={m.id} msg={m} m={meta[m.id]} />
                )
              )}
              {loading && (
                <div className="thinking-live" aria-live="polite">
                  <span className="pulse" />
                  {STAGES[stage]}
                </div>
              )}
            </div>
          )}
          {error && <p className="error">{error}</p>}
        </div>

        {/* Composer */}
        <div className="composer">
          <form onSubmit={send} className="composer-row">
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Ask a question…"
              aria-label="Question"
            />
            <button className="primary" type="submit" disabled={loading || !draft.trim()}>
              Send
            </button>
          </form>
          <p className="composer-note">Answers cite bare-act sections of Indian family law</p>
        </div>
      </div>
    </div>
  );
}
