import type { LucideIcon } from "lucide-react";

export function Empty({
  icon: Icon,
  title,
  detail,
  compact = false,
}: {
  icon?: LucideIcon;
  title: string;
  detail?: string;
  compact?: boolean;
}) {
  return (
    <div className={`flex flex-col items-center justify-center text-center ${compact ? "px-4 py-8" : "px-6 py-14"}`}>
      {Icon && (
        <span className="mb-3 flex h-9 w-9 items-center justify-center rounded-full border border-line bg-inset text-ink-faint">
          <Icon size={16} strokeWidth={1.75} />
        </span>
      )}
      <p className="text-sm text-ink-muted">{title}</p>
      {detail && <p className="mt-1 max-w-xs text-xs text-ink-faint">{detail}</p>}
    </div>
  );
}

export function Loading({ rows = 3 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-2 px-4 py-4" aria-busy="true">
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="h-3 animate-pulse rounded bg-inset" style={{ width: `${88 - i * 14}%` }} />
      ))}
    </div>
  );
}
