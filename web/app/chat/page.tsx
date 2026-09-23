"use client";
import { useEffect, useState } from "react";
import { useStackApp, useUser } from "@stackframe/stack";
import { api, stackTokenOf } from "@/lib/api";

type Msg = { id: number; role: string; content: string; lang: string };

export default function Chat() {
  useUser({ or: "redirect" });
  const app = useStackApp();
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [draft, setDraft] = useState("");
  const [lang, setLang] = useState("en");
  const [error, setError] = useState("");

  useEffect(() => {
    stackTokenOf(app)
      .then((tok) => api("/sessions", { stackToken: tok, init: { method: "POST", body: JSON.stringify({ title: "New chat" }) } }))
      .then((s) => setSessionId(s.id))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed"));
  }, [app]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!sessionId || !draft.trim()) return;
    setError("");
    try {
      const tok = await stackTokenOf(app);
      const saved = await api(`/sessions/${sessionId}/messages`, {
        stackToken: tok,
        init: { method: "POST", body: JSON.stringify({ role: "user", content: draft, lang }) },
      });
      setMsgs((m) => [...m, saved]);
      setDraft("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed");
    }
  }

  return (
    <div className="dotgrid" style={{ flex: 1, padding: "24px" }}>
      <div className="thread" style={{ maxWidth: 720, margin: "0 auto" }}>
        {msgs.map((m) => (
          <div key={m.id} className={m.role === "user" ? "bubble-user" : "bubble-bot"}>{m.content}</div>
        ))}
        <form onSubmit={send} style={{ display: "flex", gap: 8, marginTop: 12 }}>
          <select value={lang} onChange={(e) => setLang(e.target.value)} style={{ width: 90, marginTop: 0 }}>
            <option value="en">EN</option>
            <option value="hi">HI</option>
            <option value="kn">KN</option>
          </select>
          <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Ask about family law…" style={{ marginTop: 0 }} />
          <button className="primary" style={{ marginTop: 0 }} type="submit">Send</button>
        </form>
        {error && <p className="error">{error}</p>}
        <p style={{ color: "var(--muted)", fontSize: "0.8rem", marginTop: 12 }}>
          Agentic answers stream here in T4. This scaffold stores your messages per user.
        </p>
      </div>
    </div>
  );
}
