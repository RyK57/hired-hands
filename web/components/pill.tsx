import type { Tone } from "@/lib/status";

const TONE_CLASS: Record<Tone, string> = {
  neutral: "border-line text-ink-muted bg-surface",
  accent: "border-accent/30 text-accent bg-accent-soft",
  ok: "border-ok/30 text-ok bg-ok-soft",
  bad: "border-bad/30 text-bad bg-bad-soft",
  warn: "border-warn/30 text-warn bg-warn-soft",
};

const DOT_CLASS: Record<Tone, string> = {
  neutral: "bg-ink-faint",
  accent: "bg-accent",
  ok: "bg-ok",
  bad: "bg-bad",
  warn: "bg-warn",
};

export function Pill({
  tone = "neutral",
  live = false,
  dot = true,
  children,
  className = "",
}: {
  tone?: Tone;
  live?: boolean;
  dot?: boolean;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex h-[22px] items-center gap-1.5 rounded-full border px-2 text-[11px] font-medium uppercase tracking-[0.06em] whitespace-nowrap ${TONE_CLASS[tone]} ${className}`}
    >
      {dot && <span className={`h-1.5 w-1.5 rounded-full ${DOT_CLASS[tone]} ${live ? "live-dot" : ""}`} />}
      {children}
    </span>
  );
}
