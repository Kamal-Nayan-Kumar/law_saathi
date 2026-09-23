"use client";
import { useState, useEffect } from "react";

export default function AdminPortal() {
  const [docs, setDocs] = useState<any[]>([]);
  const [title, setTitle] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    // Minimal T13 admin view — list from upload router stub
    fetch("/api/admin/docs").catch(() => {});
  }, []);

  async function upload(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    if (title) form.append("doc_title", title);
    try {
      const res = await fetch("/api/upload/pdf", { method: "POST", body: form });
      const data = await res.json();
      setMessage(`Uploaded: ${data.title || file.name} (${data.chunks || 0} chunks)`);
      setFile(null);
      setTitle("");
    } catch (err: any) {
      setMessage(err.message || "Upload failed");
    }
  }

  return (
    <main style={{ maxWidth: 800, margin: "40px auto", padding: 24, fontFamily: "var(--font-body)" }}>
      <h1 style={{ fontFamily: "var(--font-display)", color: "var(--maroon-deep)" }}>Admin Portal — Document Ingestion</h1>
      <p style={{ color: "var(--muted)", fontSize: "0.85rem" }}>T13: upload PDFs, view chunk counts, manage ingestion (MVP minimal).</p>
      <form onSubmit={upload} style={{ marginTop: 16, display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
        <input type="text" placeholder="Document title" value={title} onChange={(e) => setTitle(e.target.value)} style={{ padding: 8, flex: 1, minWidth: 200 }} />
        <input type="file" accept=".pdf" onChange={(e) => setFile(e.target.files?.[0] || null)} style={{ padding: 8 }} />
        <button type="submit" disabled={!file} style={{ padding: "8px 14px", background: "var(--maroon)", color: "white", border: "none", borderRadius: 6, fontWeight: 700 }}>Upload PDF</button>
      </form>
      {message && <p style={{ marginTop: 12, fontSize: "0.85rem", color: message.includes("Uploaded") ? "green" : "red" }}>{message}</p>}
      <hr style={{ margin: "24px 0", borderColor: "var(--line)" }} />
      <h2 style={{ fontSize: "1.1rem", color: "var(--maroon)" }}>Ingested Documents</h2>
      <p style={{ color: "var(--muted)", fontSize: "0.8rem" }}>Connects to <code>/upload/pdf</code> and admin list endpoint (stub for demo).</p>
      <table style={{ width: "100%", borderCollapse: "collapse", marginTop: 12, fontSize: "0.85rem" }}>
        <thead><tr style={{ background: "var(--maroon-deep)", color: "white" }}><th style={{ padding: 8, textAlign: "left" }}>Title</th><th>Chunks</th><th>Source</th></tr></thead>
        <tbody>
          <tr><td style={{ padding: 8, borderBottom: "1px solid var(--line)" }}>Sample Judgment</td><td>12</td><td>upload</td></tr>
        </tbody>
      </table>
    </main>
  );
}
