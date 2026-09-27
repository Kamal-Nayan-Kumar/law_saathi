"use client";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { authClient } from "@/lib/auth/client";

function EyeIcon({ off }: { off?: boolean }) {
  return off ? (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94" />
      <path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19" />
      <line x1="2" y1="2" x2="22" y2="22" />
      <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24" />
    </svg>
  ) : (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
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
          <div className="pw-wrap">
            <input type={showPw ? "text" : "password"} placeholder="Password (8+ chars)" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={8} aria-label="Password" />
            <button type="button" className="pw-eye" onClick={() => setShowPw((v) => !v)} aria-label={showPw ? "Hide password" : "Show password"} title={showPw ? "Hide password" : "Show password"}>
              <EyeIcon off={showPw} />
            </button>
          </div>
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
