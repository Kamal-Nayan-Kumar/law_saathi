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
            <Logo size={46} />
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
          <Social label="GitHub">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="M12 2a10 10 0 0 0-3.16 19.49c.5.09.68-.22.68-.48v-1.7c-2.78.6-3.37-1.34-3.37-1.34-.45-1.16-1.11-1.47-1.11-1.47-.91-.62.07-.61.07-.61 1 .07 1.53 1.03 1.53 1.03.9 1.53 2.34 1.09 2.91.83.09-.65.35-1.09.63-1.34-2.22-.25-4.56-1.11-4.56-4.94 0-1.09.39-1.98 1.03-2.68-.1-.25-.45-1.27.1-2.64 0 0 .84-.27 2.75 1.02a9.5 9.5 0 0 1 5 0c1.91-1.29 2.75-1.02 2.75-1.02.55 1.37.2 2.39.1 2.64.64.7 1.03 1.59 1.03 2.68 0 3.84-2.34 4.68-4.57 4.93.36.31.68.92.68 1.85v2.74c0 .27.18.58.69.48A10 10 0 0 0 12 2Z" />
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