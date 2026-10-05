"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import Logo from "./Logo";
import Icon, { type IconName } from "./Icon";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/#features", label: "Features" },
  { href: "/#how", label: "How it Works" },
  { href: "/#acts", label: "Acts covered" },
  { href: "/#faqs", label: "FAQs" },
];

// Language codes the agent answers in, and the label to show.
const LANGS: { code: string; label: string }[] = [
  { code: "en", label: "English" },
  { code: "hi", label: "Hindi" },
  { code: "kn", label: "Kannada" },
];

export default function Nav() {
  const [open, setOpen] = useState(false);
  const [account, setAccount] = useState(false);
  const accountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setOpen(false);
    setAccount(false);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  // Clicking anywhere else closes the account menu.
  useEffect(() => {
    if (!account) return;
    const onDown = (e: MouseEvent) => {
      if (!accountRef.current?.contains(e.target as Node)) setAccount(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAccount(false);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [account]);

  return (
    <header>
      <nav className="nav" aria-label="Main">
        <div className="nav-inner">
          <Link href="/" className="brand" aria-label="Law Saathi home">
            <Logo size={36} />
          </Link>

          <div className="nav-links">
            {LINKS.map((l) => (
              <Link key={l.href} href={l.href}>
                {l.label}
              </Link>
            ))}
          </div>

          <div className="nav-cta">
            <Link href="/login" className="btn btn-outline btn-sm">
              Log in
            </Link>
            <Link href="/login?mode=register" className="btn btn-primary btn-sm">
              Try Law Saathi
              <Icon name="arrowRight" size={16} />
            </Link>

            {/* The settings control replaces a dead "home" link: it is where a
                signed-in user changes language, sees what the app remembers and
                signs out. */}
            <div className="nav-account" ref={accountRef}>
              <button
                type="button"
                className="nav-icon-btn"
                onClick={() => setAccount((v) => !v)}
                aria-expanded={account}
                aria-haspopup="menu"
                aria-label="Settings and account"
                title="Settings"
              >
                <Icon name="sliders" size={19} />
              </button>

              {account && (
                <div className="menu" role="menu">
                  <p className="menu-head">Settings</p>

                  <div className="menu-group">
                    <span className="menu-label">Answer language</span>
                    <div className="menu-langs">
                      {LANGS.map((l) => (
                        <Link
                          key={l.code}
                          href={`/login?lang=${l.code}`}
                          role="menuitem"
                          className="menu-lang"
                        >
                          <Icon name="globe" size={15} />
                          {l.label}
                        </Link>
                      ))}
                    </div>
                    <p className="menu-hint">
                      You can also change this while chatting — Saathi replies in
                      the language you ask in.
                    </p>
                  </div>

                  <div className="menu-group">
                    <Link href="/chat" role="menuitem" className="menu-item">
                      <Icon name="chat" size={16} />
                      Go to chat
                    </Link>
                    <Link href="/login" role="menuitem" className="menu-item">
                      <Icon name="user" size={16} />
                      Switch account
                    </Link>
                  </div>
                </div>
              )}
            </div>
          </div>

          <button
            type="button"
            className="nav-toggle"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            aria-controls="nav-sheet"
            aria-label={open ? "Close menu" : "Open menu"}
          >
            <Icon name={open ? "close" : "menu"} size={22} />
          </button>
        </div>
      </nav>

      {open && (
        <div className="nav-sheet" id="nav-sheet">
          {LINKS.map((l) => (
            <Link key={l.href} href={l.href}>
              {l.label}
            </Link>
          ))}
          <Link href="/login?mode=register" className="btn btn-primary">
            Try Law Saathi free
            <Icon name="arrowRight" size={17} />
          </Link>
          <Link href="/login" className="btn btn-outline">
            Log in
          </Link>
        </div>
      )}
    </header>
  );
}