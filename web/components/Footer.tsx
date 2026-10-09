"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import Logo from "./Logo";
import Icon from "./Icon";

const TOP = [
  { href: "/#features", label: "Features" },
  { href: "/#how", label: "How it Works" },
  { href: "/#acts", label: "Acts covered" },
  { href: "/#faqs", label: "FAQs" },
];

const LEGAL = [
  { href: "/#privacy", label: "Privacy" },
  { href: "/#terms", label: "Terms" },
  { href: "/#contact", label: "Contact" },
];

// Simple letterform marks so the social row needs no icon-font or SVG files.
function Social({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <a href="#" aria-label={label} title={label}>
      {children}
    </a>
  );
}

export default function Footer() {
  const pathname = usePathname();
  const hidden = ["/chat", "/admin"].some((p) => pathname.startsWith(p));
  if (hidden) return null;

  return (
    <footer className="footer">
      <div className="footer-main">
        <div className="footer-brand">
          {/* Logo already renders the wordmark, so only the tagline goes here. */}
          <div className="footer-brand-text">
            <Logo size={52} />
            <p>Legal information. In your language.</p>
          </div>
        </div>

        <nav className="footer-links" aria-label="Footer">
          {TOP.map((l) => (
            <Link key={l.href} href={l.href}>
              {l.label}
            </Link>
          ))}
        </nav>

        <div className="footer-social">
          <Social label="Instagram">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M12 2.2c3.2 0 3.6 0 4.9.07 1.2.05 1.8.26 2.2.42.6.22 1 .48 1.4.9.4.4.7.8.9 1.4.2.4.4 1 .4 2.2.1 1.3.1 1.7.1 4.9s0 3.6-.1 4.9c0 1.2-.2 1.8-.4 2.2-.2.6-.5 1-.9 1.4-.4.4-.8.7-1.4.9-.4.2-1 .4-2.2.4-1.3.1-1.7.1-4.9.1s-3.6 0-4.9-.1c-1.2 0-1.8-.2-2.2-.4-.6-.2-1-.5-1.4-.9-.4-.4-.7-.8-.9-1.4-.2-.4-.4-1-.4-2.2C2.2 15.6 2.2 15.2 2.2 12s0-3.6.1-4.9c0-1.2.2-1.8.4-2.2.2-.6.5-1 .9-1.4.4-.4.8-.7 1.4-.9.4-.2 1-.4 2.2-.4C8.4 2.2 8.8 2.2 12 2.2Zm0 1.8c-3.1 0-3.5 0-4.8.07-1.1.05-1.7.25-2.1.4-.5.2-.9.44-1.3.84-.4.4-.64.8-.84 1.3-.15.4-.35 1-.4 2.1C2.5 10 2.5 10.4 2.5 12s0 2 .07 3.3c.05 1.1.25 1.7.4 2.1.2.5.44.9.84 1.3.4.4.8.64 1.3.84.4.15 1 .35 2.1.4 1.3.06 1.7.07 4.8.07s3.5 0 4.8-.07c1.1-.05 1.7-.25 2.1-.4.5-.2.9-.44 1.3-.84.4-.4.64-.8.84-1.3.15-.4.35-1 .4-2.1.06-1.3.07-1.7.07-3.3s0-2-.07-3.3c-.05-1.1-.25-1.7-.4-2.1a3.5 3.5 0 0 0-.84-1.3 3.5 3.5 0 0 0-1.3-.84c-.4-.15-1-.35-2.1-.4C15.5 4 15.1 4 12 4Zm0 3.1a4.9 4.9 0 1 1 0 9.8 4.9 4.9 0 0 1 0-9.8Zm0 1.8a3.1 3.1 0 1 0 0 6.2 3.1 3.1 0 0 0 0-6.2Zm5.1-3.3a1.15 1.15 0 1 1 0 2.3 1.15 1.15 0 0 1 0-2.3Z" />
            </svg>
          </Social>
          <Social label="LinkedIn">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M4.98 3.5a2.5 2.5 0 1 1 0 5 2.5 2.5 0 0 1 0-5ZM3 9h4v12H3V9Zm7 0h3.8v1.7h.05c.53-.95 1.83-1.95 3.77-1.95 4.03 0 4.78 2.5 4.78 5.76V21h-4v-5.6c0-1.34-.03-3.07-1.9-3.07-1.9 0-2.2 1.46-2.2 2.97V21h-4V9Z" />
            </svg>
          </Social>
          <Social label="X">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M17.53 3h3.02l-6.6 7.55L21.75 21h-5.9l-4.62-6.04L5.94 21H2.9l7.06-8.08L2.5 3h6.05l4.18 5.52L17.53 3Zm-1.04 16.2h1.67L7.6 4.7H5.8l10.69 14.5Z" />
            </svg>
          </Social>
          <Social label="YouTube">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M21.6 7.2a2.5 2.5 0 0 0-1.76-1.77C18.25 5 12 5 12 5s-6.25 0-7.84.43A2.5 2.5 0 0 0 2.4 7.2 26 26 0 0 0 2 12a26 26 0 0 0 .4 4.8 2.5 2.5 0 0 0 1.76 1.77C5.75 19 12 19 12 19s6.25 0 7.84-.43a2.5 2.5 0 0 0 1.76-1.77A26 26 0 0 0 22 12a26 26 0 0 0-.4-4.8ZM10 15.02V8.98L15.2 12 10 15.02Z" />
            </svg>
          </Social>
        </div>
      </div>

      <div className="footer-bottom">
        <div className="footer-bottom-inner">
          <p>
            © {new Date().getFullYear()} Law Saathi. Legal information, not legal
            advice.
          </p>
          <nav className="footer-legal" aria-label="Legal">
            {LEGAL.map((l) => (
              <Link key={l.href} href={l.href}>
                {l.label}
              </Link>
            ))}
          </nav>
        </div>
      </div>
    </footer>
  );
}