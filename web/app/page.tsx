"use client";

import Link from "next/link";
import Image from "next/image";
import Icon from "@/components/Icon";
import IconDisc from "@/components/IconDisc";
import "./landing.css";

/* ---------- copy ------------------------------------------------------ */

const LANGS = [
  { code: "en", label: "English", native: "English" },
  { code: "hi", label: "Hindi", native: "हिन्दी" },
  { code: "kn", label: "Kannada", native: "ಕನ್ನಡ" },
];

const FEATURES = [
  {
    icon: "chat" as const,
    tint: "peach" as const,
    title: "Ask in Your Language",
    body: "Type or speak in English, Hindi, or Kannada.",
  },
  {
    icon: "document" as const,
    tint: "peach" as const,
    title: "Reliable Information",
    body: "Get answers grounded in authentic legal sources.",
  },
  {
    icon: "shield" as const,
    tint: "peach" as const,
    title: "Clear & Simple Answers",
    body: "Understand complex legal terms in easy language.",
  },
  {
    icon: "users" as const,
    tint: "peach" as const,
    title: "Accessible for Everyone",
    body: "Designed for individuals and families across India.",
  },
];

const STATS = [
  { icon: "users" as const, value: "7 Acts", label: "Family laws covered" },
  { icon: "book" as const, value: "424", label: "In-force sections" },
  { icon: "globe" as const, value: "3+", label: "Languages supported" },
  { icon: "shield" as const, value: "100%", label: "Cited answers" },
];

const STEPS = [
  {
    icon: "mic" as const,
    tint: "peach" as const,
    n: "1.",
    title: "Ask",
    body: "Type or speak your question in your preferred language.",
  },
  {
    icon: "document" as const,
    tint: "cream" as const,
    n: "2.",
    title: "Understand",
    body: "Our AI identifies the language and finds relevant legal information.",
  },
  {
    icon: "sparkle" as const,
    tint: "butter" as const,
    n: "3.",
    title: "Get Answer",
    body: "Receive clear, accurate and explainable responses with legal context.",
  },
  {
    icon: "users" as const,
    tint: "sage" as const,
    n: "4.",
    title: "Take Next Steps",
    body: "Understand your options and what you can do next.",
  },
];

const CHECKS = [
  "Multilingual support (English, Hindi, Kannada)",
  "Voice and text based interaction",
  "Context-aware and explainable responses",
];

const FAQS = [
  {
    q: "Is Law Saathi a lawyer?",
    a: "No. Law Saathi gives legal information, not legal advice. Every answer says so, and tells you when to consult a professional lawyer.",
  },
  {
    q: "Which family laws are covered?",
    a: "Marriage, divorce, custody, maintenance, adoption, succession and domestic violence — from seven in-force acts including the Hindu Marriage Act, PWDV Act and Guardians & Wards Act.",
  },
  {
    q: "Where do the answers come from?",
    a: "Every answer is retrieved from bare acts published on India Code and Open India Law, and each claim carries the section it came from.",
  },
  {
    q: "Can I use it in my own language?",
    a: "Yes. Ask in English, Hindi or Kannada by voice or text, and the answer comes back in the language you used.",
  },
];

/* ---------- floating question chips over the illustration -------------- */

const CHIPS = [
  { text: "Child custody rights?", style: { top: "6%", left: "0%" } },
  { text: "Maintenance rules?", style: { top: "30%", right: "0%" } },
  { text: "Divorce process?", style: { bottom: "16%", left: "0%" } },
  { text: "Property rights in family law?", style: { bottom: "0%", right: "0%" } },
];

/* ---------- page ------------------------------------------------------ */

export default function Landing() {
  return (
    <>
      {/* ============ HERO ============ */}
      <section className="hero">
        <div className="shell hero-grid">
          <div className="hero-copy">
            <span className="eyebrow-pill">Your Friendly Legal Companion</span>
            <h1>
              Clear Family Law Guidance,{" "}
              <span className="gold">In Your Language.</span>
            </h1>
            <p className="lede">
              Law Saathi is a multilingual, AI-powered legal support system that
              helps you understand family law in simple words — through text or
              voice.
            </p>

            <div className="lang-pills" role="list" aria-label="Supported languages">
              {LANGS.map((l, i) => (
                <span
                  key={l.code}
                  role="listitem"
                  className={`lang-pill${i === 0 ? " active" : ""}`}
                >
                  <Icon name="globe" size={16} />
                  {l.native}
                </span>
              ))}
            </div>

            <div className="hero-ctas">
              <Link href="/login?mode=register" className="btn btn-primary">
                Start a Conversation
                <Icon name="arrowRight" size={17} />
              </Link>
              <Link href="/login" className="btn btn-outline">
                <Icon name="play" size={16} />
                Watch Demo
              </Link>
            </div>
          </div>

          <div className="hero-art">
            <Image
              src="/images/hero-scene.png"
              alt="A woman asking a family law question by voice and getting an answer with citations"
              width={1000}
              height={1250}
              priority
              sizes="(max-width: 900px) 92vw, 44vw"
            />
          </div>
        </div>

        <div className="skyline" aria-hidden="true">
          <Image
            src="/images/skyline.png"
            alt=""
            width={1400}
            height={318}
            sizes="100vw"
          />
        </div>
      </section>

      {/* ============ FEATURES ============ */}
      <section className="section" id="features">
        <div className="shell">
          <div className="feature-grid">
            {FEATURES.map((f) => (
              <article className="feature" key={f.title}>
                <IconDisc name={f.icon} tint={f.tint} size={64} />
                <h3>{f.title}</h3>
                <p>{f.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ============ WHY ============ */}
      <section className="section why">
        <div className="shell why-grid">
          <div className="why-art">
            {/* The clip holds the image so the rounded corners stay clean; the
                chips are siblings so they can overlap the frame on desktop and
                drop into normal flow on a phone without being clipped. */}
            <div className="why-clip">
              <Image
                src="/images/family-scales.png"
                alt="A family standing together in front of scales of justice"
                width={1254}
                height={1254}
                sizes="(max-width: 900px) 88vw, 44vw"
              />
              {CHIPS.map((c) => (
                <span className="why-chip" key={c.text} style={c.style}>
                  {c.text}
                </span>
              ))}
            </div>
          </div>

          <div className="why-copy">
            <span className="eyebrow">Why Law Saathi</span>
            <h2>
              Making Family Law Information Accessible to Everyone
            </h2>
            <p className="lede">
              Family law can be confusing and overwhelming. Law Saathi helps you
              get clear, reliable, and easy-to-understand information so that you
              can make informed decisions for yourself and your family.
            </p>
            <ul className="check-list">
              {CHECKS.map((c) => (
                <li key={c}>
                  <Icon name="checkCircle" size={20} />
                  {c}
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      {/* ============ STATS ============ */}
      <section className="section-tight">
        <div className="shell">
          <div className="stats-strip">
            {STATS.map((s, i) => (
              <div className="stat" key={s.label}>
                <Icon name={s.icon} size={30} className="stat-icon" />
                <p>
                  <b>{s.value}</b>
                  <span>{s.label}</span>
                </p>
                {i < STATS.length - 1 && <span className="stat-div" aria-hidden="true" />}
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ============ HOW IT WORKS ============ */}
      <section className="section" id="how">
        <div className="shell">
          <div className="section-head">
            <span className="eyebrow">How it works</span>
            <h2>Get Answers in 4 Simple Steps</h2>
          </div>

          <ol className="steps">
            {STEPS.map((s, i) => (
              <li className="step" key={s.n}>
                <div className="step-disc-row">
                  {/* The connector is one line drawn on .steps, not per item. */}
                  <IconDisc name={s.icon} tint={s.tint} size={76} />
                </div>
                <h4>
                  <span>{s.n}</span> {s.title}
                </h4>
                <p>{s.body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      {/* ============ FAQ ============ */}
      <section className="section" id="faqs">
        <div className="shell">
          <div className="section-head">
            <span className="eyebrow">FAQs</span>
            <h2>Questions people ask us</h2>
          </div>
          <div className="faq-grid">
            {FAQS.map((f) => (
              <details className="faq" key={f.q}>
                <summary>
                  {f.q}
                  <Icon name="chevronDown" size={19} />
                </summary>
                <p>{f.a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* ============ CTA BAND ============ */}
      <section className="section-tight">
        <div className="shell">
          <div className="cta-band">
            <span className="cta-flourish cta-flourish-l" aria-hidden="true" />
            <span className="cta-flourish cta-flourish-r" aria-hidden="true" />
            <div className="cta-copy">
              <span className="eyebrow cta-eyebrow">Ready to get started?</span>
              <h2>Ask Your Question, Anytime.</h2>
              <p>
                Get trusted family law information in your language, with the
                help of AI.
              </p>
            </div>
            <Link href="/login?mode=register" className="btn btn-light cta-btn">
              Start a Conversation
              <Icon name="arrowRight" size={17} />
            </Link>
          </div>
        </div>
      </section>

      {/* ============ LEGAL ANCHORS ============ */}
      <div className="shell legal-anchors" id="privacy">
        <section id="terms">
          <h2>Terms &amp; disclaimer</h2>
          <p className="lede">
            Law Saathi provides legal information to help you understand your
            options. It is not a law firm and nothing here is legal advice. Every
            answer is generated from published bare acts and should be verified
            with a qualified lawyer before you act on it.
          </p>
        </section>
        <section id="contact">
          <h2>Contact</h2>
          <p className="lede">
            Found something wrong, or want to help? Write to{" "}
            <a href="mailto:hello@lawsaathi.in" className="link">
              hello@lawsaathi.in
            </a>
            .
          </p>
        </section>
      </div>
    </>
  );
}