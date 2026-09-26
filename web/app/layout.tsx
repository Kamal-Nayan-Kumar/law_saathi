import type { Metadata } from "next";
import { Poppins } from "next/font/google";
import Nav from "./Nav";
import "./globals.css";

const poppins = Poppins({
  subsets: ["latin", "latin-ext", "devanagari"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "Law Saathi — Family Law Assistant",
  description: "Multilingual agentic AI legal support for family law (EN, HI, KN).",
  icons: { icon: "/images/logo.png" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={poppins.className}>
      <body>
        <Nav />
        {children}
      </body>
    </html>
  );
}
