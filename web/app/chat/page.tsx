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

// A message as returned by GET /sessions/{id}/messages. The source fields were
// added after the first release, so older rows simply don't carry them.
type StoredMsg = Msg & {
  citations?: string[];
  citation_sources?: string[];
};

type ChatSession = {
  id: number;
  title: string;
};

type TraceStep = { node: string; detail: string };

type Answer = {
  answer: string;
  clarification: boolean;
  citations: string[];
  citation_sources: string[];
  provider: string;
  retries: number;
  trace: string[];
  trace_detail: TraceStep[];
};

const SUGGESTIONS = [
  "How do I get a mutual-consent divorce?",
  "पत्नी भरण-पोषण कैसे माँग सकती है?",
  "ಮಗುವಿನ ಕಸ್ಟಡಿ ಯಾರಿಗೆ ಸಿಗುತ್ತದೆ?",
];

const STAGES = ["Understanding intent…", "Planning…", "Retrieving bare acts…", "Verifying citations…", "Writing answer…"];

const TRACE_LABELS: Record<string, string> = {
  contextualize: "Intent — understood follow-up using chat history",
  intent: "Intent — detected topic and language",
  planner: "Planner — checked what's clear, what needs asking",
  tools: "Tools — retrieved bare-act sections",
  verifier: "Verifier — checked citations cover the answer",
  response: "Response — wrote the final answer",
};

const STEP_TITLES: Record<string, string> = {
  contextualize: "Follow-up",
  intent: "Intent",
  planner: "Planner",
  tools: "Tools",
  verifier: "Verifier",
  response: "Response",
};

function detectLang(text: string): "en" | "hi" | "kn" {
  if (/\u0C80-\u0CFF/.test(text)) return "kn";
  if (/\u0900-\u097F/.test(text)) return "hi";
  return "en";
}

type Meta = { trace: string[]; steps: TraceStep[]; citations: string[]; sources: string[] };

// Rebuild the per-message Meta map from a fetched message list so a reopened
// chat shows the same Sources block and inline markers as a live answer. The
// trace is not persisted, so `trace`/`steps` stay empty and Thinking stays hidden.
// Messages without stored citations simply get no entry.
function metaFromList(list: StoredMsg[]): Record<number, Meta> {
  const next: Record<number, Meta> = {};
  list.forEach((m) => {
    if (m.role !== "assistant") return;
    next[m.id] = {
      trace: [],
      steps: [],
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

// Turn each citation marker in the answer — `[1]` or `[1,2,3]` — into a small
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
  const text =
    m && m.citations.length ? linkCitationMarkers(msg.content, m.citations, msg.id) : msg.content;

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
      {m && m.trace.length > 0 && (
        <div className="think think-top">
          <button type="button" className="think-toggle" onClick={() => setShowThink((v) => !v)}>
            {showThink ? "▾ Thinking" : "▸ Thinking"}
          </button>
          {showThink && (
            <ol className="think-steps">
              {m.steps.length > 0
                ? m.steps.map((s, i) => (
                    <li key={`${s.node}-${i}`}>
                      <strong>{STEP_TITLES[s.node] || s.node}</strong>
                      <span className="step-detail">{s.detail}</span>
                      <span className="think-done"> — done</span>
                    </li>
                  ))
                : m.trace.map((t) => (
                    <li key={t}>
                      <strong>{TRACE_LABELS[t] || t}</strong>
                      <span className="think-done"> — done</span>
                    </li>
                  ))}
            </ol>
          )}
        </div>
      )}
      <div className="md" onClick={onCite}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
      </div>
      {m && m.citations.length > 0 && (
        <div className="src">
          <p className="src-head">Sources ({m.citations.length})</p>
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
  const [stage, setStage] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [sideOpen, setSideOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 860px)");
    const upd = () => setIsMobile(mq.matches);
    upd();
    mq.addEventListener("change", upd);
    return () => mq.removeEventListener("change", upd);
  }, []);

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
        steps: answerObj.trace_detail || [],
        citations: answerObj.citations || [],
        sources: answerObj.citation_sources || [],
      };
      const botId = Date.now() + 1;
      const botMsg: Msg = { id: botId, role: "assistant", content: answerObj.answer, lang: sendLang };
      setMsgs((prev) => [...prev, botMsg]);
      setMeta((prev) => ({ ...prev, [botId]: tmeta }));
      api(`/sessions/${sid}/messages`)
        .then((list: StoredMsg[]) => {
          if (!list.length) return;
          setMsgs(list);
          // Stored citations for the whole thread, then re-attach this answer's
          // live trace to its real server id (ids change on reload).
          const match = list.find((m) => m.role === "assistant" && m.content === answerObj.answer);
          const next = metaFromList(list);
          if (match) next[match.id] = tmeta;
          delete next[botId];
          setMeta(next);
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
        <div className="side-toprow">
          <button type="button" className="side-new" onClick={newChat}>
            ＋ New chat
          </button>
          <button type="button" className="side-hide" onClick={toggleSide} aria-label={collapsed ? "Show history" : "Hide history"} title={collapsed ? "Show history" : "Hide history"}>
            {collapsed ? "»" : "«"}
          </button>
        </div>
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
        <a className="side-home" href="/" title="Home">
          {collapsed ? "⌂" : "⌂ Home"}
        </a>
      </aside>

      <div className="chat-shell">
        {/* Chat header (replaces marketing nav on this page) */}
        <header className="chat-top">
          <div className="chat-top-inner">
            {isMobile && (
              <button type="button" className="side-toggle" onClick={toggleSide} aria-label="Show history" title="Show history">
                ☰
              </button>
            )}
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
                  <div className="live-head">
                    <span className="pulse" />
                    Thinking…
                  </div>
                  <ol className="live-steps">
                    {STAGES.map((s, i) => (
                      <li key={s} className={i === stage % STAGES.length ? "live-on" : ""}>
                        {s}
                      </li>
                    ))}
                  </ol>
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
