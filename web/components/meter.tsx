import { healthTone } from "@/lib/status";

const FILL: Record<string, string> = {
  neutral: "bg-ink-faint",
  ok: "bg-ok",
  warn: "bg-warn",
  bad: "bg-bad",
  accent: "bg-accent",
};

export function Meter({ value, className = "" }: { value: number | null | undefined; className?: string }) {
  const fraction = value === null || value === undefined ? 0 : Math.max(0, Math.min(1, value));
  const tone = healthTone(value);
  return (
    <div
      className={`h-1.5 w-full overflow-hidden rounded-full bg-inset ${className}`}
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(fraction * 100)}
    >
      <div className={`h-full rounded-full transition-[width] duration-500 ${FILL[tone]}`} style={{ width: `${fraction * 100}%` }} />
    </div>
  );
}
