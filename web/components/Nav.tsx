"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import Logo from "./Logo";
import Icon from "./Icon";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/#features", label: "Features" },
  { href: "/#how", label: "How it Works" },
  { href: "/#acts", label: "Acts covered" },
  { href: "/#faqs", label: "FAQs" },
];

export default function Nav() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);

  // /chat and /admin draw their own full-height header. Rendering this one as
  // well gave a phone two bars before any content and pushed the composer off
  // the bottom of the screen.
  const hidden = ["/chat", "/admin"].some((p) => pathname.startsWith(p));

  useEffect(() => {
    setOpen(false);
  }, []);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  if (hidden) return null;

  return (
    <header>
      <nav className="nav" aria-label="Main">
        <div className="nav-inner">
          <Link href="/" className="brand" aria-label="Law Saathi home">
            <Logo size={40} />
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