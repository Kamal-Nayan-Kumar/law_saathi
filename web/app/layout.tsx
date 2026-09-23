import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "LawSaathi — Family Law Assistant",
  description: "Multilingual agentic AI legal support for family law (EN, HI, KN).",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="board">
          <div className="brand">LawSaathi</div>
        </header>
        {children}
      </body>
    </html>
  );
}
