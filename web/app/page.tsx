import Link from "next/link";

const FEATURES = [
  {
    icon: "◉",
    title: "Speak or type your question",
    body: "Multilingual ASR + language ID at the edge. Ask about maintenance, custody, divorce — by voice or text.",
  },
  {
    icon: "§",
    title: "Grounded in bare acts",
    body: "RAG over 7 in-force family-law acts (1,132 chunks) from India Code. Every claim needs evidence.",
  },
  {
    icon: "◐",
    title: "Context-aware reasoning",
    body: "LLM agent plans, retrieves, verifies and answers in simple language with section + act citations.",
  },
  {
    icon: "♪",
    title: "Hear it back",
    body: "Multilingual TTS replies in English, Hindi and Kannada. Built for low-literacy and hands-free access.",
  },
  {
    icon: "✓",
    title: "Explainable by design",
    body: "Expandable tool-call steps (intent → retrieve → verify) and grouped bare-act vs web sources.",
  },
  {
    icon: "⬢",
    title: "Private & scoped",
    body: "Family law only. Secure session chat, saved language + tone, and a clear not-a-lawyer disclaimer.",
  },
];

const STEPS = [
  { n: "01 — Ask", h: "Ask naturally", p: "Speak or type in EN / HI / KN. We detect the language automatically." },
  { n: "02 — Retrieve", h: "We find the law", p: "Agentic RAG pulls exact sections from Hindu Marriage, PWDV, Guardians & Wards and more." },
  { n: "03 — Verify", h: "We check & reason", p: "The verifier rejects uncited claims, then drafts a simple, context-aware answer." },
  { n: "04 — Answer", h: "Read or listen", p: "Get text with citations — or press play and hear it in your language." },
];

const ACTS = [
  "Hindu Marriage Act 1955",
  "Special Marriage Act 1954",
  "Hindu Adoption & Maintenance 1956",
  "Hindu Succession Act 1956",
  "Guardians & Wards Act 1890",
  "PWDV Act 2005",
  "Indian Divorce Act 1869",
];

export default function Landing() {
  return (
    <main className="landing">
      {/* HERO */}
      <section className="hero">
        <div>
          <h1>
            Family law, <em>in your language.</em> Spoken or typed.
          </h1>
          <p className="lede">
            Law Saathi is a multilingual agentic AI that answers questions on marriage, divorce,
            custody, maintenance, adoption, succession and domestic violence — with real
            section citations, not guesses.
          </p>
          <div className="hero-ctas">
            <Link href="/chat" className="btn-maroon">
              Ask a question →
            </Link>
            <Link href="/login" className="btn-outline">
              Log in / Sign up
            </Link>
          </div>
        </div>

        {/* Signature element: voice → citation ticket */}
        <div className="voice-card" aria-label="Voice query demo">
          <div className="voice-top">
            <span className="live-dot" /> Listening · हिन्दी detected → answering in Hindi
          </div>
          <div className="wave" aria-hidden="true">
            {[
              14, 26, 38, 22, 34, 12, 30, 40, 18, 28, 36, 16, 24, 32, 20, 38, 14, 26, 30, 18,
            ].map((h, i) => (
              <span key={i} style={{ height: h, animationDelay: `${i * 0.08}s` }} />
            ))}
          </div>
          <div className="query-lines">
            <div>“आपसी सहमति से तलाक़ कैसे मिलता है?”</div>
            <div>“ಪರಸ್ಪರ ಒಪ್ಪಿಗೆಯ ವಿಚ್ಛೇದನ ಹೇಗೆ ಪಡೆಯುವುದು?”</div>
            <div>“How do I get a mutual-consent divorce?”</div>
          </div>
          <div className="answer-ticket">
            <b>Saathi answers:</b> Under <code>HMA Sec 13B</code>, both spouses can file a
            joint petition after living separately for a year… <br />
            <span style={{ color: "var(--muted)", fontSize: "0.8rem" }}>
              ▸ 2 bare-act citations · ⏵ Listen in Hindi / Kannada
            </span>
          </div>
        </div>
      </section>

      {/* LANGUAGES */}
      <section className="section" id="languages">
        <h2>One question, three tongues.</h2>
        <p className="sub">
          English-pivot pipeline: detect → retrieve + reason in English → answer back in your
          language. Extensible to more Indian languages.
        </p>
        <div className="lang-split">
          <img src="/images/voice-mic.png" alt="Elderly woman speaking into a phone in her language" className="lang-photo" />
          <div className="lang-strip">
          <span className="lang-pill">
            <b>EN</b> — “What are grounds for mutual-consent divorce?”
          </span>
          <span className="lang-pill">
            <b>HI</b> — “आपसी सहमति से तलाक़ कैसे होता है?”
          </span>
          <span className="lang-pill">
            <b>KN</b> — “ಪರಸ್ಪರ ಒಪ್ಪಿಗೆಯ ವಿಚ್ಛೇದನ ಹೇಗೆ?”
          </span>
          </div>
        </div>
      </section>

      {/* FEATURES */}
      <section className="section" id="features">
        <h2>What Law Saathi gives you</h2>
        <div className="feat-grid">
          {FEATURES.map((f) => (
            <div className="feat" key={f.title}>
              <div className="icon">{f.icon}</div>
              <h3>{f.title}</h3>
              <p>{f.body}</p>
            </div>
          ))}
        </div>
      </section>

      {/* HOW */}
      <section className="section" id="how">
        <h2>How it works</h2>
        <div className="steps">
          {STEPS.map((s) => (
            <div className="step" key={s.n}>
              <div className="n">{s.n}</div>
              <h4>{s.h}</h4>
              <p>{s.p}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ACTS */}
      <section className="section" id="acts">
        <h2>Grounded in real law</h2>
        <p className="sub">
          Retrieval over in-force sections only (repealed rows dropped). Sources: Open India Law
          corpus + India Code ground truth.
        </p>
        <div className="acts-banner">
          <img src="/images/bare-act-texture.png" alt="Open Hindu Marriage Act bare-act book with stacked law volumes" />
        </div>
        <div className="acts">
          {ACTS.map((a) => (
            <span className="act" key={a}>
              {a}
            </span>
          ))}
        </div>
      </section>

      {/* DEMO */}
      <section className="section" id="demo">
        <h2>Try it in your head first</h2>
        <p className="sub">Same question, same evidence — answered in the language you asked.</p>
        <div className="demo">
          <div className="demo-box">
            <b>You (Hindi, voice):</b>
            <p>“मुझे घरेलू हिंसा में क्या सुरक्षा मिल सकती है?”</p>
            <p style={{ color: "var(--muted)", fontSize: "0.85rem", marginTop: 8 }}>
              → Saathi replies in Hindi with PWDV Act Sections 17–22: protection order,
              residence order, monetary relief — plus where to get help.
            </p>
          </div>
          <div className="demo-box">
            <b>You (Kannada, typed):</b>
            <p>“ಮಗುವಿನ ಕಸ್ಟಡಿ ಯಾರಿಗೆ ಸಿಗುತ್ತದೆ?”</p>
            <p style={{ color: "var(--muted)", fontSize: "0.85rem", marginTop: 8 }}>
              → Saathi replies in Kannada with Guardians &amp; Wards Act + welfare-of-child
              principle, custody vs guardianship explained simply.
            </p>
          </div>
        </div>
        <div className="cta-band">
          <h2 style={{ fontFamily: "var(--font-display)" }}>Ask Saathi anything about family law.</h2>
          <p>Free to try. Answers cite the exact section — and say when to see a lawyer.</p>
          <Link href="/chat" className="btn-solid" style={{ display: "inline-block" }}>
            Start chatting →
          </Link>
        </div>
      </section>

      {/* FOOTER */}
      <footer className="footer">
        <div className="foot-brand">
          <img src="/images/logo.png" alt="Law Saathi logo" />
          <div>
            <b>Law Saathi</b>
            <p>Multilingual family-law information (EN / HI / KN).</p>
          </div>
        </div>
        <p className="foot-note">
          Legal information, not legal advice. Verify with a professional.
        </p>
      </footer>
    </main>
  );
}
