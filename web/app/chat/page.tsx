"use client";

import { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { authClient } from "@/lib/auth/client";
import { api } from "@/lib/api";
import Icon from "@/components/Icon";
import Logo from "@/components/Logo";
import "./chat.css";

type Msg = {
  id: number;
  role: string;
  content: string;
  lang: string;
};

// A message as returned by GET /sessions/{id}/messages. The source fields were
// added after the first release, so older rows simply do not carry them.
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

const STAGES = [
  "Understanding intent…",
  "Planning…",
  "Retrieving bare acts…",
  "Verifying citations…",
  "Writing answer…",
];

const STEP_TITLES: Record<string, string> = {
  contextualize: "Follow-up",
  intent: "Intent",
  planner: "Planner",
  tools: "Tools",
  verifier: "Verifier",
  response: "Response",
};

function detectLang(text: string): "en" | "hi" | "kn" {
  if (/[ಀ-೿]/.test(text)) return "kn";
  if (/[ऀ-ॿ]/.test(text)) return "hi";
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
      {/* Gate on steps, not trace: a reopened session restores citations but has
          no stored trace, which would render an empty Thinking toggle. */}
      {m && m.steps.length > 0 && (
        <div className="think think-top">
          <button type="button" className="think-toggle" onClick={() => setShowThink((v) => !v)}>
            <Icon name={showThink ? "chevronDown" : "chevronDown"} size={15} className="think-caret" />
            Thinking
            <span className="think-count">{m.steps.length}</span>
          </button>
          {showThink && (
            <ol className="think-steps">
              {m.steps.map((s, i) => (
                <li key={`${s.node}-${i}`}>
                  <strong>{STEP_TITLES[s.node] || s.node}</strong>
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
  const [stage, setStage] = useState(0);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [sideOpen, setSideOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

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

  // Rotate the "working…" stage label while an answer is being generated.
  useEffect(() => {
    if (!loading) return;
    setStage(0);
    const t = setInterval(() => setStage((s) => (s + 1) % STAGES.length), 1800);
    return () => clearInterval(t);
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

        <nav className="side-nav">
          <Link href="/dashboard">
            <Icon name="chart" size={17} />
            <span className="side-label">Dashboard</span>
          </Link>
          <Link href="/cases">
            <Icon name="folder" size={17} />
            <span className="side-label">Practice cases</span>
          </Link>
          <Link href="/">
            <Icon name="arrowRight" size={17} className="flip-180" />
            <span className="side-label">Home</span>
          </Link>
          <button type="button" className="side-signout" onClick={signOut}>
            <Icon name="logout" size={17} />
            <span className="side-label">Sign out</span>
          </button>
        </nav>
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
            <Link href="/cases" className="chat-practice">
              <Icon name="gavel" size={16} />
              Practice a case
            </Link>
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
                    Working on it…
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
          {error && <p className="alert alert-error">{error}</p>}
        </div>

        <div className="composer">
          <form onSubmit={send} className="composer-row">
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Ask a question about family law…"
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
        </div>
      </div>
    </div>
  );
}