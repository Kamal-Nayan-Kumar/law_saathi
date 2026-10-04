import Icon, { type IconName } from "./Icon";

/**
 * The reference design puts every feature icon on a soft peach disc. This is that
 * disc, in the four tints the reference actually uses: peach, cream, butter and
 * sage. Keeping it one component is what stops the discs drifting in size and
 * padding from card to card.
 */
export type DiscTint = "peach" | "cream" | "butter" | "sage" | "maroon";

const TINTS: Record<DiscTint, { bg: string; fg: string }> = {
  peach: { bg: "var(--peach)", fg: "var(--maroon)" },
  cream: { bg: "var(--cream-2)", fg: "var(--gold)" },
  butter: { bg: "var(--butter)", fg: "var(--gold)" },
  sage: { bg: "var(--sage)", fg: "var(--sage-ink)" },
  maroon: { bg: "var(--maroon)", fg: "var(--gold)" },
};

export type IconDiscProps = {
  name: IconName;
  tint?: DiscTint;
  /** Disc diameter in px. The reference uses 64 in cards, 76 in step rows. */
  size?: number;
  iconSize?: number;
  className?: string;
  title?: string;
};

export default function IconDisc({
  name,
  tint = "peach",
  size = 64,
  iconSize,
  className,
  title,
}: IconDiscProps) {
  const t = TINTS[tint];
  const px = iconSize || Math.round(size * 0.42);
  return (
    <span
      className={`icon-disc${className ? ` ${className}` : ""}`}
      style={{ width: size, height: size, background: t.bg, color: t.fg }}
      aria-hidden={title ? undefined : "true"}
    >
      <Icon name={name} size={px} title={title} />
    </span>
  );
}