import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  distDir: process.env.DIST_DIR || ".next",
  /**
   * The illustrations are already exported at the size the layout draws them by
   * `scripts/prep_assets.py`, as WebP. The optimiser is still on for the
   * responsive `srcset` — that is what lets a phone fetch the 140 px copy of a
   * chip row instead of the 400 px one — but it is restricted to the formats
   * worth having and told to hold its own cache.
   */
  images: {
    // WebP and AVIF are both supported everywhere this site is meant to reach.
    // Listing them makes the optimiser emit AVIF where the browser takes it and
    // WebP everywhere else, instead of serving the PNG that shipped by default.
    formats: ["image/avif", "image/webp"],
    // Small images are the ones this site is full of: a 96 px logo, a 400 px
    // empty-state mark. The default 16-device-size ladder spends a request on
    // candidates no screen will ever pick.
    deviceSizes: [640, 750, 828, 1080, 1200, 1400, 1920],
    imageSizes: [32, 64, 96, 128, 200, 256, 400],
    minimumCacheTTL: 60 * 60 * 24 * 30,
  },

  /**
   * Gzip/Brotli for the route handlers and pages. The streaming route sends
   * `X-Accel-Buffering: no` and its own content type; compression is skipped
   * for it because compressing an event stream buffers it, which is the exact
   * failure the header exists to prevent.
   */
  compress: true,

  /**
   * The chat is one long-lived route; prefetching its RSC payload on hover
   * spends the user's data and the browser's main thread on a page most
   * visitors only ever see after signing in.
   */
  experimental: {
    staleTimes: { dynamic: 0, static: 180 },
  },
};

export default nextConfig;