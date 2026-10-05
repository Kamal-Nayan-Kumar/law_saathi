"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Image from "next/image";
import { authClient } from "@/lib/auth/client";
import { api } from "@/lib/api";
import Icon from "@/components/Icon";
import "./auth.css";

const LANGS = [
  { code: "en", label: "English", native: "English" },
  { code: "hi", label: "Hindi", native: "हिन्दी" },
  { code: "kn", label: "Kannada", native: "ಕನ್ನಡ" },
];

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
  const [lang, setLang] = useState("en");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState("");
  // Shown while a language preference is being saved after signup. The user is
  // already routed to /chat by then, so this never blocks the screen.
  const [savedHint, setSavedHint] = useState("");
  // A tap on a slow phone gave zero feedback while the request was in flight,
  // so it looked like the button was broken.
  const [busy, setBusy] = useState(false);

  // Nav links switch forms via ?mode=. Runs on every query change because a
  // same-page navigation does not remount the component.
  useEffect(() => {
    const q = searchParams.get("mode");
    if (q === "register" || q === "login") setMode(q);
    // The settings menu links here with ?lang= to change the answer language.
    const l = searchParams.get("lang");
    if (l === "en" || l === "hi" || l === "kn") setLang(l);
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
      // Route away first. Saving the language is a second round-trip and must
      // never be the reason the user waits on a spinner after signing in.
      router.push("/chat");
      if (mode === "register") {
        api("/me", { method: "PUT", body: JSON.stringify({ preferred_lang: lang }) })
          .catch(() => setSavedHint("We could not save your language. Pick it in chat instead."));
      }
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

          {isRegister && (
            <fieldset className="lang-pick">
              <legend>Preferred language</legend>
              <p className="field-hint">Answers come back in the language you ask in. This is your default.</p>
              <div className="chips-row">
                {LANGS.map((l) => (
                  <button
                    key={l.code}
                    type="button"
                    className="chip-btn"
                    aria-pressed={lang === l.code}
                    onClick={() => setLang(l.code)}
                  >
                    <Icon name="globe" size={15} />
                    {l.native}
                  </button>
                ))}
              </div>
            </fieldset>
          )}

          {error && (
            <p className="alert alert-error" role="alert">
              {error}
            </p>
          )}
          {savedHint && (
            <p className="alert alert-error" role="status">
              {savedHint}
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