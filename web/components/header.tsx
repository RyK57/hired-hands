"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCell } from "./cell-provider";
import { Pill } from "./pill";
import { networkLabel } from "@/lib/format";

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/treasury", label: "Treasury" },
  { href: "/hire", label: "Hire" },
];

export function Mark({ size = 20 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <path
        d="M12 7H8.5A1.5 1.5 0 0 0 7 8.5v15A1.5 1.5 0 0 0 8.5 25H12"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M20 7h3.5A1.5 1.5 0 0 1 25 8.5v15a1.5 1.5 0 0 1-1.5 1.5H20"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="16" cy="16" r="2.4" fill="var(--accent)" />
    </svg>
  );
}

export function Header() {
  const pathname = usePathname();
  const { cell, loading } = useCell();
  const online = Boolean(cell?.online);

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-surface/90 backdrop-blur">
      <div className="mx-auto flex h-14 w-full max-w-7xl items-center gap-4 px-4 sm:px-6 lg:px-8">
        <Link href="/" className="flex items-center gap-2 text-ink">
          <Mark />
          <span className="text-sm font-semibold tracking-tight">Hired Hands</span>
        </Link>
        <nav className="ml-2 hidden items-center gap-1 sm:flex">
          {NAV.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded px-2.5 py-1 text-sm transition-colors ${
                  active ? "bg-inset text-ink" : "text-ink-muted hover:text-ink"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="ml-auto flex items-center gap-3">
          <span className="num hidden text-xs text-ink-muted sm:inline">{networkLabel(cell)}</span>
          {loading ? (
            <Pill tone="neutral" dot={false}>
              Connecting
            </Pill>
          ) : online ? (
            <Pill tone="accent" live>
              Online
            </Pill>
          ) : (
            <Pill tone="neutral">Offline</Pill>
          )}
        </div>
      </div>
      <nav className="mx-auto flex w-full max-w-7xl items-center gap-1 overflow-x-auto px-4 pb-2 sm:hidden">
        {NAV.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`rounded px-2.5 py-1 text-sm whitespace-nowrap ${
                active ? "bg-inset text-ink" : "text-ink-muted"
              }`}
            >
              {item.label}
            </Link>
          );
        })}
      </nav>
    </header>
  );
}
