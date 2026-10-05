"use client";

/**
 * The Law Saathi icon set.
 *
 * Every icon is hand-built on one 24x24 grid with a 1.8 stroke, round caps and
 * round joins, and inherits `currentColor`. That single spec is the point: the
 * reference design's icons all sit on a peach disc and recolour with context, and
 * a mixed-weight set (or raster icons) is what made the old ones look forced.
 *
 * Do not add an icon here with a different grid, stroke or cap style. Do not
 * pull icons from a generated image — they cannot be recoloured or scaled.
 *
 * Usage:  <Icon name="scales" size={28} />   or   <Icon name="scales" />
 */

export type IconName =
  // brand + legal
  | "scales"
  | "shield"
  | "document"
  | "gavel"
  | "book"
  | "landmark"
  // people + access
  | "users"
  | "user"
  | "mic"
  | "globe"
  | "chat"
  | "sparkle"
  // product surfaces
  | "chart"
  | "trend"
  | "target"
  | "folder"
  | "flame"
  | "clock"
  | "check"
  | "checkCircle"
  | "lock"
  | "mail"
  | "eye"
  | "eyeOff"
  | "play"
  | "send"
  | "arrowRight"
  | "arrowUp"
  | "menu"
  | "close"
  | "plus"
  | "chevronDown"
  | "logout"
  | "sliders"
  | "search"
  | "list"
  | "volume"
  | "language";

const PATHS: Record<IconName, React.ReactNode> = {
  // ---- brand + legal -------------------------------------------------
  scales: (
    <>
      <path d="M12 4v16" />
      <path d="M7 20h10" />
      <path d="M12 4.8 5 7.2" />
      <path d="M12 4.8l7 2.4" />
      <path d="M5 7.2 2.6 12.4a2.9 2.9 0 0 0 4.8 0L5 7.2Z" />
      <path d="M19 7.2l-2.4 5.2a2.9 2.9 0 0 0 4.8 0L19 7.2Z" />
      <path d="M9.6 4.6h4.8" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3.2 5 6v5.4c0 4.2 2.9 7.7 7 9.4 4.1-1.7 7-5.2 7-9.4V6l-7-2.8Z" />
      <path d="m9.2 12 2 2.1 3.6-4" />
    </>
  ),
  document: (
    <>
      <path d="M14 3.2H7.4A1.9 1.9 0 0 0 5.5 5v14a1.9 1.9 0 0 0 1.9 1.9h9.2a1.9 1.9 0 0 0 1.9-1.9V8l-4.5-4.8Z" />
      <path d="M13.8 3.4V8.4h4.5" />
      <path d="M8.8 12.4h6.4M8.8 16h4.4" />
    </>
  ),
  gavel: (
    <>
      <path d="m14.6 3.4 6 6-2.6 2.6-6-6 2.6-2.6Z" />
      <path d="m10.4 7.6-7 7 3 3 7-7" />
      <path d="m4.6 12.2 4.2 4.2" />
      <path d="M11.6 18.6h8" />
    </>
  ),
  book: (
    <>
      <path d="M4.6 5.2A1.8 1.8 0 0 1 6.4 3.4H12v17H6.4a1.8 1.8 0 0 1-1.8-1.8V5.2Z" />
      <path d="M19.4 5.2a1.8 1.8 0 0 0-1.8-1.8H12v17h5.6a1.8 1.8 0 0 0 1.8-1.8V5.2Z" />
    </>
  ),
  landmark: (
    <>
      <path d="M12 3.4 3.6 8h16.8L12 3.4Z" />
      <path d="M5.6 8v8.4M9.6 8v8.4M14.4 8v8.4M18.4 8v8.4" />
      <path d="M3.6 19.4h16.8" />
    </>
  ),

  // ---- people + access ----------------------------------------------
  users: (
    <>
      <circle cx="9.4" cy="8.6" r="3.2" />
      <path d="M3.8 19.4c0-3 2.5-5.2 5.6-5.2s5.6 2.2 5.6 5.2" />
      <path d="M16 5.6a3.2 3.2 0 0 1 0 5.9" />
      <path d="M17 14.4c2 .6 3.4 2.4 3.4 5" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8.4" r="3.4" />
      <path d="M5.4 20c0-3.3 3-5.6 6.6-5.6s6.6 2.3 6.6 5.6" />
    </>
  ),
  mic: (
    <>
      <rect x="9.2" y="3" width="5.6" height="10.4" rx="2.8" />
      <path d="M5.6 11.4a6.4 6.4 0 0 0 12.8 0" />
      <path d="M12 17.8V21M9 21h6" />
    </>
  ),
  globe: (
    <>
      <circle cx="12" cy="12" r="8.4" />
      <path d="M3.6 12h16.8" />
      <path d="M12 3.6c2.1 2.3 3.2 5.2 3.2 8.4s-1.1 6.1-3.2 8.4c-2.1-2.3-3.2-5.2-3.2-8.4S9.9 5.9 12 3.6Z" />
    </>
  ),
  chat: (
    <path d="M20.4 12.6c0 3.9-3.8 7-8.4 7-1 0-2-.1-2.9-.4l-5.1 1.4 1.5-4.3a6.6 6.6 0 0 1-1.9-4.7c0-3.9 3.8-7 8.4-7s8.4 3.1 8.4 7Z" />
  ),
  sparkle: (
    <>
      <path d="M12 3.4c.9 4.4 2.2 5.7 6.6 6.6-4.4.9-5.7 2.2-6.6 6.6-.9-4.4-2.2-5.7-6.6-6.6 4.4-.9 5.7-2.2 6.6-6.6Z" />
      <path d="M18.4 15.4c.4 1.9 1 2.5 2.9 2.9-1.9.4-2.5 1-2.9 2.9-.4-1.9-1-2.5-2.9-2.9 1.9-.4 2.5-1 2.9-2.9Z" />
    </>
  ),

  // ---- product surfaces ---------------------------------------------
  chart: (
    <>
      <path d="M4 20.2h16.4" />
      <path d="M7.4 20.2v-6.4M12 20.2V6.6M16.6 20.2v-9.4" />
    </>
  ),
  trend: (
    <>
      <path d="m3.8 16.6 5-5.4 3.6 3.2 6.8-7" />
      <path d="M15.4 7.4h4.8v4.8" />
    </>
  ),
  target: (
    <>
      <circle cx="12" cy="12" r="8.4" />
      <circle cx="12" cy="12" r="4.6" />
      <circle cx="12" cy="12" r="1" />
    </>
  ),
  folder: (
    <path d="M3.8 6.6a1.8 1.8 0 0 1 1.8-1.8h3.6l2 2.6h7.2a1.8 1.8 0 0 1 1.8 1.8v8.4a1.8 1.8 0 0 1-1.8 1.8H5.6a1.8 1.8 0 0 1-1.8-1.8V6.6Z" />
  ),
  flame: (
    <>
      <path d="M12 3.4c3.6 3 5.4 5.5 5.4 8.8A5.4 5.4 0 0 1 12 17.6a5.4 5.4 0 0 1-5.4-5.4c0-3.3 1.8-5.8 5.4-8.8Z" />
      <path d="M12 17.6c1.7-1.4 2.6-2.9 2.6-4.7 0-1.6-.7-3-2.6-4.9-1.9 1.9-2.6 3.3-2.6 4.9 0 1.8.9 3.3 2.6 4.7Z" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8.4" />
      <path d="M12 7.4V12l3.2 2.2" />
    </>
  ),
  check: <path d="m4.8 12.6 4.6 4.6L19.2 7" />,
  checkCircle: (
    <>
      <circle cx="12" cy="12" r="8.4" />
      <path d="m8.2 12.2 2.6 2.6 5-5.4" />
    </>
  ),
  lock: (
    <>
      <rect x="5.2" y="10.4" width="13.6" height="9.8" rx="2.2" />
      <path d="M8.4 10.4V8a3.6 3.6 0 0 1 7.2 0v2.4" />
    </>
  ),
  mail: (
    <>
      <rect x="3.6" y="5.6" width="16.8" height="12.8" rx="2.2" />
      <path d="m4.4 7.6 7.6 5.2 7.6-5.2" />
    </>
  ),
  eye: (
    <>
      <path d="M2.6 12S6.2 5.6 12 5.6 21.4 12 21.4 12 17.8 18.4 12 18.4 2.6 12 2.6 12Z" />
      <circle cx="12" cy="12" r="2.8" />
    </>
  ),
  eyeOff: (
    <>
      <path d="M17.9 17.9A10 10 0 0 1 12 19.6C6.2 19.6 2.6 12 2.6 12a18.5 18.5 0 0 1 5-5.9" />
      <path d="M9.9 5.3A9.3 9.3 0 0 1 12 5c5.8 0 9.4 7 9.4 7a18.6 18.6 0 0 1-2.2 3.2" />
      <path d="m3.6 3.6 16.8 16.8" />
      <path d="M9.9 9.9a2.8 2.8 0 0 0 3.9 3.9" />
    </>
  ),
  play: <path d="M8.4 5.4 18 12l-9.6 6.6V5.4Z" />,
  send: (
    <>
      <path d="M12 19.4V5.2" />
      <path d="m5.4 11.8 6.6-6.6 6.6 6.6" />
    </>
  ),
  arrowRight: (
    <>
      <path d="M4.6 12h14.2" />
      <path d="m13.4 6.6 5.4 5.4-5.4 5.4" />
    </>
  ),
  arrowUp: (
    <>
      <path d="M12 19.4V5.2" />
      <path d="m6.6 10.6 5.4-5.4 5.4 5.4" />
    </>
  ),
  menu: (
    <>
      <path d="M4 7h16" />
      <path d="M4 12h16" />
      <path d="M4 17h16" />
    </>
  ),
  close: (
    <>
      <path d="m6.4 6.4 11.2 11.2" />
      <path d="m17.6 6.4-11.2 11.2" />
    </>
  ),
  plus: (
    <>
      <path d="M12 5.4v13.2" />
      <path d="M5.4 12h13.2" />
    </>
  ),
  chevronDown: <path d="m6.6 9.4 5.4 5.4 5.4-5.4" />,
  logout: (
    <>
      <path d="M14.4 7.6V5.8a1.8 1.8 0 0 0-1.8-1.8H6.4a1.8 1.8 0 0 0-1.8 1.8v12.4a1.8 1.8 0 0 0 1.8 1.8h6.2a1.8 1.8 0 0 0 1.8-1.8v-1.8" />
      <path d="M9.8 12h9.4" />
      <path d="m16.4 8.8 3.2 3.2-3.2 3.2" />
    </>
  ),
  sliders: (
    <>
      <path d="M4 7.4h9M17.4 7.4H20" />
      <path d="M4 16.6h3.6M12 16.6h8" />
      <circle cx="15.2" cy="7.4" r="2.2" />
      <circle cx="9.8" cy="16.6" r="2.2" />
    </>
  ),
  search: (
    <>
      <circle cx="11" cy="11" r="6.6" />
      <path d="m15.8 15.8 4 4" />
    </>
  ),
  list: (
    <>
      <path d="M9 6.6h10.6M9 12h10.6M9 17.4h10.6" />
      <path d="M4.6 6.6h.01M4.6 12h.01M4.6 17.4h.01" />
    </>
  ),
  volume: (
    <>
      <path d="M4.6 9.4h3.2L12 5.8v12.4l-4.2-3.6H4.6V9.4Z" />
      <path d="M15.6 9.6a3.6 3.6 0 0 1 0 4.8" />
      <path d="M18.2 7.2a7 7 0 0 1 0 9.6" />
    </>
  ),
  language: (
    <>
      <path d="M3.8 6.6h7.4" />
      <path d="M7.5 4.4v2.2" />
      <path d="M9.8 6.6c0 3.4-2.6 6.4-6 7.4" />
      <path d="M5 9.8c.8 2 2.6 3.4 4.8 4" />
      <path d="m12.6 20 3.8-9.6 3.8 9.6" />
      <path d="M13.9 16.8h5" />
    </>
  ),
};

export type IconProps = {
  name: IconName;
  size?: number;
  strokeWidth?: number;
  className?: string;
  /** Provide when the icon is the only content of a control. */
  title?: string;
};

export default function Icon({
  name,
  size = 24,
  strokeWidth = 1.8,
  className,
  title,
}: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden={title ? undefined : true}
      role={title ? "img" : undefined}
      focusable="false"
    >
      {title ? <title>{title}</title> : null}
      {PATHS[name]}
    </svg>
  );
}