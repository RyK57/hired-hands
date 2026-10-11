export function Card({
  title,
  aside,
  children,
  className = "",
  bodyClassName = "",
}: {
  title?: React.ReactNode;
  aside?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={`card flex min-w-0 flex-col ${className}`}>
      {(title || aside) && (
        <header className="flex min-h-[44px] items-center justify-between gap-3 border-b border-line px-4">
          <h2 className="label text-ink-muted">{title}</h2>
          {aside && <div className="flex items-center gap-2 text-xs text-ink-muted">{aside}</div>}
        </header>
      )}
      <div className={`min-w-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  );
}

export function Stat({
  label,
  value,
  sub,
  mono = true,
  className = "",
}: {
  label: React.ReactNode;
  value: React.ReactNode;
  sub?: React.ReactNode;
  mono?: boolean;
  className?: string;
}) {
  return (
    <div className={`flex min-w-0 flex-col gap-0.5 ${className}`}>
      <span className="label">{label}</span>
      <span className={`truncate text-sm text-ink ${mono ? "num" : ""}`}>{value}</span>
      {sub && <span className="truncate text-xs text-ink-faint">{sub}</span>}
    </div>
  );
}

export function KeyValue({ rows }: { rows: { key: React.ReactNode; value: React.ReactNode }[] }) {
  return (
    <dl className="divide-y divide-line">
      {rows.map((row, i) => (
        <div key={i} className="flex items-start justify-between gap-4 px-4 py-2.5 text-sm">
          <dt className="label pt-0.5">{row.key}</dt>
          <dd className="min-w-0 text-right text-ink">{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}
