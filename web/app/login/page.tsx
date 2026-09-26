"use client";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { authClient } from "@/lib/auth/client";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState("");

  // Nav links switch forms via ?mode=: /login = login, /login?mode=register = signup.
  // Runs on every query change (same-page navigation doesn't remount).
  useEffect(() => {
    const q = searchParams.get("mode");
    if (q === "register" || q === "login") setMode(q);
  }, [searchParams]);

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
    <div className="auth-card">
      <div className="auth-media">
        <img
          src="/images/auth-side.png"
          alt="Indian family with courthouse and scales of justice in maroon and marigold"
        />
      </div>
      <div className="auth-form">
        <h2>{mode === "login" ? "Welcome back." : "Create your account."}</h2>
        <p className="auth-sub">
          Ask in English, Hindi or Kannada — by voice or text.
        </p>
        <form onSubmit={submit}>
          {mode === "register" && (
            <input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required aria-label="Name" />
          )}
          <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required aria-label="Email" />
          <input type="password" placeholder="Password (8+ chars)" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} aria-label="Password" />
          <button className="primary auth-submit" type="submit">
            {mode === "login" ? "Login →" : "Create account →"}
          </button>
        </form>
        {error && <p className="error">{error}</p>}
        <p className="auth-toggle">
          <button type="button" onClick={() => setMode(mode === "login" ? "register" : "login")}>
            {mode === "login" ? "New here? Create an account" : "Have an account? Login"}
          </button>
        </p>
      </div>
    </div>
  );
}

export default function Login() {
  return (
    <main className="auth-wrap">
      <Suspense fallback={<div className="auth-card" />}>
        <LoginForm />
      </Suspense>
      <p className="auth-note">Legal information, not legal advice.</p>
    </main>
  );
}
