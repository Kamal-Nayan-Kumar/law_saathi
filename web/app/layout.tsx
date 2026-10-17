import type { Metadata } from "next";
import { Playfair_Display, Plus_Jakarta_Sans } from "next/font/google";
import Nav from "@/components/Nav";
import Footer from "@/components/Footer";
import ScrollManager from "@/components/ScrollManager";
import "./globals.css";

// The reference pairs a transitional serif for headings with a humanist
// grotesque for body. Playfair Display + Plus Jakarta Sans is that pairing.
//
// Both are loaded as *variable* fonts, with no `weight` list. The reason is not
// bytes: measured either way, Next serves three woff2 files totalling the same
// 86 KB, because it already folds named weights into one variable file. The
// reason is that `npm run build` did not work. Turbopack rejects a multi-weight
// `next/font/google` call with 28 "next/font/google queries have exactly one
// entry" errors, so the app could not be built for production at all without
// `--webpack`. `font-weight` in the CSS still picks the exact cut, because that
// is what the variable axis is for.
const playfair = Playfair_Display({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-playfair",
});

// Devanagari and Kannada come from the system fallback: Plus Jakarta Sans has
// no Devanagari subset, and Hindi/Kannada answers must not render as tofu.
const jakarta = Plus_Jakarta_Sans({
  subsets: ["latin", "latin-ext"],
  display: "swap",
  variable: "--font-jakarta",
});

export const metadata: Metadata = {
  title: "Law Saathi — Family Law, Explained in Simple Words",
  description:
    "Law Saathi is a multilingual, AI-powered legal support system that helps you understand family law — through text or voice, in the language you use.",
  // The 512px mark used to be the favicon, so every visit downloaded 120 KB for
  // a 16px square in the tab. These are the two sizes browsers actually ask for.
  icons: {
    icon: "/images/icon-32.png",
    apple: "/images/icon-180.png",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html
      lang="en"
      className={`${playfair.variable} ${jakarta.variable}`}
      suppressHydrationWarning
    >
      <body>
        <ScrollManager />
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