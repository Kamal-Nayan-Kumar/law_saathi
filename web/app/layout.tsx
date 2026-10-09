import type { Metadata } from "next";
import { Playfair_Display, Plus_Jakarta_Sans } from "next/font/google";
import Nav from "@/components/Nav";
import Footer from "@/components/Footer";
import "./globals.css";

// The reference pairs a transitional serif for headings with a humanist
// grotesque for body. Playfair Display + Plus Jakarta Sans is that pairing.
const playfair = Playfair_Display({
  subsets: ["latin"],
  weight: ["500", "600", "700"],
  display: "swap",
  variable: "--font-playfair",
});

// Devanagari and Kannada come from the system fallback: Plus Jakarta Sans has
// no Devanagari subset, and Hindi/Kannada answers must not render as tofu.
const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin", "latin-ext"],
  weight: ["400", "500", "600", "700"],
  display: "swap",
  variable: "--font-jakarta",
});

export const metadata: Metadata = {
  title: "Law Saathi — Family Law, Explained in Simple Words",
  description:
    "Law Saathi is a multilingual, AI-powered legal support system that helps you understand family law — through text or voice, in the language you use.",
  icons: { icon: "/images/logo-mark.png" },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${playfair.variable} ${jakarta.variable}`}
      suppressHydrationWarning
    >
      <body>
        <a href="#main" className="skip-link">
          Skip to content
        </a>
        <Nav />
        <main id="main">{children}</main>
        <Footer />
      </body>
    </html>
  );
}