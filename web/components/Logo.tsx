"use client";

import Image from "next/image";

/**
 * The logo lockup: the generated mark plus a two-tone wordmark.
 *
 * The wordmark is HTML, not baked into the image, so it stays crisp at any size
 * and the gold half can be recoloured. The mark is a transparent PNG keyed by
 * scripts/prep_assets.py.
 *
 * Props:
 *   size  — mark height in px; the wordmark scales off it
 *   tone  — "light" for a dark background (footer, maroon bands)
 */
export default function Logo({
  size = 36,
  tone = "dark",
}: {
  size?: number;
  tone?: "dark" | "light";
}) {
  const word = size * 0.355;
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: size * 0.3,
      }}
    >
      <Image
        src="/images/logo-mark.png"
        alt=""
        width={size}
        height={size}
        style={{ width: size, height: size, objectFit: "contain" }}
        priority
      />
      <span
        className={`brand-word${tone === "light" ? " brand-word-light" : ""}`}
        style={{ fontSize: word, lineHeight: 1 }}
      >
        Law <span>Saathi</span>
      </span>
    </span>
  );
}