"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Image from "next/image";
import { authClient } from "@/lib/auth/client";
import Icon from "@/components/Icon";
import "./auth.css";

const PERKS = [
  "Ask in your own language, by voice or text",
  "Every answer cites the exact section of law",
  "Private, and free to try",
];

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState("");
  // A tap on a slow phone gave zero feedback while the request was in flight,
  // so it looked like the button was broken.
  const [busy, setBusy] = useState(false);

  // Nav links switch forms via ?mode=. Runs on every query change because a
  // same-page navigation does not remount the component.
  useEffect(() => {
    const q = searchParams.get("mode");
    if (q === "register" || q === "login") setMode(q);
  }, [searchParams]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setError("");
    setBusy(true);
    try {
      const { error } =
        mode === "register"
          ? await authClient.signUp.email({ email, password, name: name || email })
          : await authClient.signIn.email({ email, password });
      if (error) {
        setError(error.message || "Failed");
        return;
      }
      // No language is chosen or saved anywhere. The answer is written in
      // whatever script the question arrives in, so a stored preference would
      // only be able to contradict what the user just typed.
      router.push("/chat");
    } catch {
      setError("Could not sign you in. Check your connection and try again.");
    } finally {
      setBusy(false);
    }
  }

  const isRegister = mode === "register";

  return (
    <div className="auth-card">
      <div className="auth-art">
        <Image
          src="/images/auth-scene.png"
          alt="A woman asking a family law question from her phone"
          fill
          // Below 900px this is a short banner, above it the full art panel.
          sizes="(max-width: 900px) 100vw, 46vw"
          priority
        />
        <ul className="auth-perks">
          {PERKS.map((p) => (
            <li key={p}>
              <Icon name="checkCircle" size={18} />
              {p}
            </li>
          ))}
        </ul>
      </div>

      <div className="auth-panel">
        <Link href="/" className="auth-back">
          <Icon name="arrowRight" size={16} className="auth-back-icon" />
          Back to home
        </Link>

        <h1>{isRegister ? "Create your account." : "Welcome back."}</h1>
        <p className="auth-sub">
          {isRegister
            ? "One minute to set up. Then ask anything about family law."
            : "Pick up where you left off."}
        </p>

        <form onSubmit={submit} noValidate>
          {isRegister && (
            <label className="field">
              <span>Full name</span>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name"
                autoComplete="name"
                required
              />
            </label>
          )}

          <label className="field">
            <span>Email</span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
              required
            />
          </label>

          <label className="field">
            <span>Password</span>
            <span className="input-wrap">
              <input
                type={showPw ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 8 characters"
                autoComplete={isRegister ? "new-password" : "current-password"}
                minLength={8}
                required
              />
              <button
                type="button"
                className="input-icon-btn"
                onClick={() => setShowPw((v) => !v)}
                aria-label={showPw ? "Hide password" : "Show password"}
                title={showPw ? "Hide password" : "Show password"}
              >
                <Icon name={showPw ? "eyeOff" : "eye"} size={19} />
              </button>
            </span>
          </label>

          {error && (
            <p className="alert alert-error" role="alert">
              {error}
            </p>
          )}

          <button className="btn btn-primary auth-submit" type="submit" disabled={busy} aria-busy={busy}>
            {busy
              ? isRegister
                ? "Creating your account…"
                : "Signing you in…"
              : isRegister
                ? "Create account"
                : "Log in"}
            {!busy && <Icon name="arrowRight" size={17} />}
          </button>
        </form>

        <p className="auth-toggle">
          {isRegister ? "Already have an account?" : "New to Law Saathi?"}{" "}
          <button
            type="button"
            onClick={() => {
              setMode(isRegister ? "login" : "register");
              setError("");
            }}
          >
            {isRegister ? "Log in" : "Create an account"}
          </button>
        </p>

        <p className="auth-note">
          Legal information, not legal advice. Verify with a professional before
          you act.
        </p>
      </div>
    </div>
  );
}

export default function Login() {
  return (
    <div className="auth-wrap">
      <Suspense fallback={<div className="auth-card auth-card-skeleton" />}>
        <LoginForm />
      </Suspense>
    </div>
  );
}