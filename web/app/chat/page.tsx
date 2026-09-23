"use client";
import { useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";

type Msg = {
  id: number;
  role: string;
  content: string;
  lang: string;
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

function detectLang(text: string): "en" | "hi" | "kn" {
  if (/\u0C80-\u0CFF/.test(text)) return "kn";
  if (/\u0900-\u097F/.test(text)) return "hi";
  return "en";
}

export default function Chat() {
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [draft, setDraft] = useState("");
  const [lang, setLang] = useState("en");
  const [tone, setTone] = useState("simple");
  const [userPref, setUserPref] = useState({ preferred_lang: "en", tone: "simple" });
  const [expandedSteps, setExpandedSteps] = useState<Record<number, boolean>>({});
  const [latestTrace, setLatestTrace] = useState<string[]>([]);
  const [latestCitations, setLatestCitations] = useState<string[]>([]);
  const [latestSources, setLatestSources] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  // Load session + history + profile
  useEffect(() => {
    api("/me")
      .then((u: any) => {
        setUserPref({ preferred_lang: u.preferred_lang || "en", tone: u.tone || "simple" });
        setLang(u.preferred_lang || "en");
        setTone(u.tone || "simple");
      })
      .catch(() => {});
    api("/memories")
      .then((m: any) => {
        const mem: Record<string, string> = {};
        (m.memories || []).forEach((item: any) => (mem[item.key] = item.value));
        if (mem.tone) setTone(mem.tone);
        if (mem.preferred_lang) { setLang(mem.preferred_lang); setUserPref((p) => ({ ...p, preferred_lang: mem.preferred_lang })); }
      })
      .catch(() => {});
    api("/sessions", { method: "POST", body: JSON.stringify({ title: "New chat" }) })
      .then((s: any) => {
        setSessionId(s.id);
        // Load message history for this session
        api(`/sessions/${s.id}/messages`)
          .then((list: Msg[]) => setMsgs(list))
          .catch(() => {});
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed"));
  }, []);

  // Auto-detect on draft change
  useEffect(() => {
    if (draft.trim().length > 1) {
      const d = detectLang(draft);
      if (d !== lang) {
        // Soft switch only when clearly different script
        setLang(d);
      }
    }
  }, [draft, lang]);

  const toggleSteps = useCallback((msgId: number) => {
    setExpandedSteps((prev) => ({ ...prev, [msgId]: !prev[msgId] }));
  }, []);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!sessionId || !draft.trim()) return;
    setError("");
    setLoading(true);
    try {
      const detected = detectLang(draft);
      const sendLang = detected !== "en" ? detected : lang;
      const resp = await api(`/sessions/${sessionId}/ask`, {
        method: "POST",
        body: JSON.stringify({ query: draft, lang: sendLang, tone }),
      });
      const answerObj = resp as Answer;
      setLatestTrace(answerObj.trace || []);
      setLatestCitations(answerObj.citations || []);
      setLatestSources(answerObj.citation_sources || []);
      // Refresh messages from server (ask endpoint already persisted both turns)
      api(`/sessions/${sessionId}/messages`)
        .then((list: Msg[]) => setMsgs(list))
        .catch(() => {});
      setDraft("");
    } catch (err: any) {
      setError(err instanceof Error ? err.message : "Failed");
    } finally {
      setLoading(false);
    }
  }

  async function savePref(key: string, value: string) {
    try {
      await api("/me", { method: "PUT", body: JSON.stringify({ [key]: value }) });
      await api("/me/memories", {
        method: "PUT",
        body: JSON.stringify([{ key, value }]),
      });
      if (key === "preferred_lang") { setLang(value); setUserPref((p) => ({ ...p, preferred_lang: value })); }
      if (key === "tone") { setTone(value); setUserPref((p) => ({ ...p, tone: value })); }
    } catch (e) {}
  }

  return (
    <div className="dotgrid" style={{ flex: 1, padding: "24px" }}>
      <div className="thread" style={{ maxWidth: 720, margin: "0 auto" }}>
        {/* Brand / theme header */}
        <div style={{ fontFamily: "var(--font-display)", fontSize: "1.5rem", color: "var(--maroon-deep)", marginBottom: 12 }}>
          LawSaathi <span style={{ color: "var(--marigold)", fontSize: "0.9rem" }}>· Multilingual chat</span>
        </div>

        {/* Preferences row */}
        <div className="card" style={{ display: "flex", gap: 12, alignItems: "center", flexWrap: "wrap", marginBottom: 14 }}>
          <label style={{ fontFamily: "var(--font-display)", fontWeight: 700, color: "var(--maroon)" }}>Language</label>
          <select value={lang} onChange={(e) => { setLang(e.target.value); savePref("preferred_lang", e.target.value); }} style={{ width: 90 }}>
            <option value="en">EN</option>
            <option value="hi">HI</option>
            <option value="kn">KN</option>
          </select>
          <label style={{ fontFamily: "var(--font-display)", fontWeight: 700, color: "var(--maroon)", marginLeft: 8 }}>Tone</label>
          <select value={tone} onChange={(e) => { setTone(e.target.value); savePref("tone", e.target.value); }} style={{ width: 110 }}>
            <option value="simple">Simple</option>
            <option value="detailed">Detailed</option>
          </select>
          <span style={{ color: "var(--muted)", fontSize: "0.8rem", marginLeft: 6 }}>{userPref.preferred_lang} · {userPref.tone}</span>
        </div>

        {/* Messages */}
        {msgs.map((m) => (
          <div key={m.id} style={{ marginBottom: 10 }}>
            <div className={m.role === "user" ? "bubble-user" : "bubble-bot"} style={{ whiteSpace: "pre-wrap" }}>
              {m.content}
            </div>
            {m.role === "assistant" && (
              <div style={{ marginTop: 4 }}>
                {/* Step expansion — use last answer for steps; for simplicity link by index */}
                <button
                  onClick={() => toggleSteps(m.id)}
                  style={{ background: "var(--maroon-deep)", color: "var(--paper)", border: "none", borderRadius: 6, padding: "4px 10px", fontSize: "0.75rem", cursor: "pointer" }}
                >
                  {expandedSteps[m.id] ? "Hide steps" : "Show reasoning steps"}
                </button>
                {expandedSteps[m.id] && (
                  <div style={{ background: "#fff6e5", border: "1px solid var(--line)", borderRadius: 8, padding: 10, marginTop: 6, fontSize: "0.82rem" }}>
                    <div style={{ fontWeight: 700, color: "var(--maroon)", marginBottom: 4 }}>Agent steps</div>
                    <ol style={{ paddingLeft: 16, margin: 0 }}>
                      {(latestTrace.length ? latestTrace : ["intent", "planner", "tools", "verifier", "response"]).map((step) => (
                        <li key={step} style={{ marginBottom: 2 }}><strong>{step}</strong> — completed</li>
                      ))}
                    </ol>
                    {/* Citation grouping */}
                    <div style={{ marginTop: 6, paddingTop: 6, borderTop: "1px dashed var(--line)" }}>
                      <strong style={{ color: "var(--maroon)" }}>Sources</strong>
                      <div style={{ display: "flex", gap: 8, marginTop: 4, flexWrap: "wrap" }}>
                        <span style={{ background: "#eae2c8", padding: "2px 6px", borderRadius: 4, fontSize: "0.75rem" }}>Bare-act citations ({latestSources.filter(s => s === "bare_act").length || "0"})</span>
                        <span style={{ background: "#c8dde6", padding: "2px 6px", borderRadius: 4, fontSize: "0.75rem" }}>Web / evidence ({latestSources.filter(s => s === "web").length || "0"})</span>
                      </div>
                      {latestCitations.length > 0 && (
                        <ul style={{ margin: "4px 0 0 16px", padding: 0, fontSize: "0.78rem", color: "var(--ink)" }}>
                          {latestCitations.map((c, i) => (
                            <li key={i}>{c}</li>
                          ))}
                        </ul>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {loading && <p style={{ color: "var(--muted)", fontSize: 0.85 }}>Thinking…</p>}
        {error && <p className="error">{error}</p>}

        <form onSubmit={send} style={{ display: "flex", gap: 8, marginTop: 12, alignItems: "flex-end" }}>
          <select value={lang} onChange={(e) => setLang(e.target.value)} style={{ width: 90, marginTop: 0 }} aria-label="Chat language">
            <option value="en">EN</option>
            <option value="hi">HI</option>
            <option value="kn">KN</option>
          </select>
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Ask about family law… (English / Hindi / Kannada)"
            style={{ marginTop: 0, flex: 1, fontFamily: "var(--font-body)" }}
            aria-label="Question"
          />
          <button className="primary" style={{ marginTop: 0, whiteSpace: "nowrap" }} type="submit" disabled={loading || !draft.trim()}>
            Send
          </button>
        </form>

        <p style={{ color: "var(--muted)", fontSize: "0.8rem", marginTop: 12 }}>
          Answers cite bare-act sections (Indian family-law acts) and may include web sources. Use “Show reasoning steps” to see the agent pipeline (intent → planner → retrieve → verify → answer). Tone preference is saved to your profile.
        </p>
      </div>
    </div>
  );
}
