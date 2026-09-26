"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";

export default function Nav() {
  const pathname = usePathname();
  if (pathname.startsWith("/chat")) return null;
  return (
    <nav className="nav" aria-label="Main">
      <div className="nav-inner">
        <Link href="/" className="brand">
          <img src="/images/logo.png" alt="Law Saathi logo" className="brand-logo" />
          <span className="brand-word">
            Law <span>Saathi</span>
          </span>
        </Link>
        <div className="nav-links">
          <Link href="/#features">Features</Link>
          <Link href="/#how">How it works</Link>
          <Link href="/#acts">Acts covered</Link>
          <Link href="/chat">Chat</Link>
        </div>
        <div className="nav-cta">
          <Link href="/login" className="btn-ghost">
            Log in
          </Link>
          <Link href="/login?mode=register" className="btn-solid">
            Sign up
          </Link>
        </div>
      </div>
    </nav>
  );
}
