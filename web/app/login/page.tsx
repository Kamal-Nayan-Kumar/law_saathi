"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { authClient } from "@/lib/auth/client";

export default function Login() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    const { error } =
      mode === "register"
        ? await authClient.signUp.email({ email, password, name: name || email })
        : await authClient.signIn.email({ email, password });
    if (error) {
      setError(error.message || "Failed");
      return;
    }
    router.push("/chat");
  }

  return (
    <main>
      <div className="card">
        <h2 style={{ fontFamily: "var(--font-display)" }}>{mode === "login" ? "Login" : "Sign up"}</h2>
        <form onSubmit={submit}>
          {mode === "register" && (
            <input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required />
          )}
          <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <input type="password" placeholder="Password (8+ chars)" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} />
          <button className="primary" type="submit">{mode === "login" ? "Login" : "Create account"}</button>
        </form>
        {error && <p className="error">{error}</p>}
        <p style={{ marginTop: 12 }}>
          <button style={{ background: "none", border: "none", color: "var(--maroon)", cursor: "pointer", textDecoration: "underline", padding: 0 }} onClick={() => setMode(mode === "login" ? "register" : "login")}>
            {mode === "login" ? "New here? Create an account" : "Have an account? Login"}
          </button>
        </p>
      </div>
    </main>
  );
}
