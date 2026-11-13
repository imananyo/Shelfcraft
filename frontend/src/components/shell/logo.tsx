/** Original Shelfcraft mark: three stacked shelf bars with an offset spark. */
export function LogoMark({ size = 28 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden>
      <rect width="32" height="32" rx="9" fill="var(--primary)" />
      <rect x="7" y="9" width="14" height="3.2" rx="1.6" fill="var(--primary-foreground)" />
      <rect x="7" y="14.4" width="18" height="3.2" rx="1.6" fill="var(--primary-foreground)" opacity=".85" />
      <rect x="7" y="19.8" width="11" height="3.2" rx="1.6" fill="var(--primary-foreground)" opacity=".7" />
      <path d="M24.5 6.5l.9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9z" fill="oklch(0.82 0.09 292)" />
    </svg>
  );
}

export function Wordmark() {
  return (
    <span className="flex items-center gap-2">
      <LogoMark />
      <span className="font-display text-[17px] font-semibold tracking-tight">Shelfcraft</span>
    </span>
  );
}
