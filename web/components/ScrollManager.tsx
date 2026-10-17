"use client";

import { useLayoutEffect } from "react";
import { usePathname } from "next/navigation";

export default function ScrollManager() {
  const pathname = usePathname();

  useLayoutEffect(() => {
    if (pathname !== "/") return;
    if (window.location.hash) return;

    // Browser back/forward navigation restores the previous scroll offset,
    // which is what left the homepage sitting on the features fold. Take
    // manual control so it cannot override our reset.
    const prevRestoration = window.history.scrollRestoration;
    window.history.scrollRestoration = "manual";

    const reset = () => {
      window.scrollTo({ top: 0, left: 0, behavior: "instant" as ScrollBehavior });
    };
    reset();
    const raf = requestAnimationFrame(reset);
    const t = window.setTimeout(reset, 150);

    return () => {
      cancelAnimationFrame(raf);
      window.clearTimeout(t);
      window.history.scrollRestoration = prevRestoration;
    };
  }, [pathname]);

  return null;
}
