import Link from "next/link";

export default function Landing() {
  return (
    <main>
      <h1 style={{ fontFamily: "var(--font-display)" }}>Family law, in your language.</h1>
      <p style={{ color: "var(--muted)", marginTop: 8 }}>
        LawSaathi answers questions on marriage, divorce, custody, maintenance, adoption and
        succession — in English, Hindi and Kannada, with citations. Full landing page lands in T12.
      </p>
      <p style={{ marginTop: 16 }}>
        <Link href="/login">Login / Sign up →</Link>
        {" · "}
        <Link href="/chat">Chat →</Link>
      </p>
      <p style={{ color: "var(--muted)", marginTop: 24, fontSize: "0.85rem" }}>
        Not a lawyer. Answers are legal information, not legal advice.
      </p>
    </main>
  );
}
