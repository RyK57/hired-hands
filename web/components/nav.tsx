"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Suspense } from "react";

const ITEMS = [
  { href: "/", label: "Overview" },
  { href: "/treasury", label: "Treasury" },
  { href: "/hire", label: "Hire" },
];

function isActive(pathname: string | null, href: string): boolean {
  if (!pathname) return false;
  return href === "/" ? pathname === "/" : pathname.startsWith(href);
}

function Links({ pathname }: { pathname: string | null }) {
  return (
    <>
      {ITEMS.map((item) => {
        const active = isActive(pathname, item.href);
        return (
          <Link
            key={item.href}
            href={item.href}
            className={`rounded px-2.5 py-1 text-sm whitespace-nowrap transition-colors ${
              active ? "bg-inset text-ink" : "text-ink-muted hover:text-ink"
            }`}
          >
            {item.label}
          </Link>
        );
      })}
    </>
  );
}

function CurrentLinks() {
  const pathname = usePathname();
  return <Links pathname={pathname} />;
}

export function Nav() {
  return (
    <Suspense fallback={<Links pathname={null} />}>
      <CurrentLinks />
    </Suspense>
  );
}
