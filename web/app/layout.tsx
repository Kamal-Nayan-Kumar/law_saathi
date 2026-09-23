import type { Metadata } from "next";
import { Suspense } from "react";
import { StackProvider, StackTheme } from "@stackframe/stack";
import { stackServerApp } from "@/stack";
import "./globals.css";

export const metadata: Metadata = {
  title: "LawSaathi — Family Law Assistant",
  description: "Multilingual agentic AI legal support for family law (EN, HI, KN).",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <StackProvider app={stackServerApp}>
          <StackTheme>
            <header className="board">
              <div className="brand">LawSaathi</div>
            </header>
            <Suspense>{children}</Suspense>
          </StackTheme>
        </StackProvider>
      </body>
    </html>
  );
}
