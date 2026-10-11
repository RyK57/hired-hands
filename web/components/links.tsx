"use client";

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { useCell } from "./cell-provider";
import { explorerAccount, explorerTx, shortAddress, shortHash } from "@/lib/format";

export function TxLink({
  hash,
  href,
  label,
  className = "",
}: {
  hash: string | null | undefined;
  href?: string | null;
  label?: string;
  className?: string;
}) {
  const { cell } = useCell();
  if (!hash) return <span className="text-ink-faint">—</span>;
  const url = explorerTx(cell, hash, href);
  const text = label ?? shortHash(hash);
  if (!url) return <span className={`num text-ink-muted ${className}`}>{text}</span>;
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      title={hash}
      className={`num inline-flex items-center gap-0.5 text-ink hover:text-accent ${className}`}
    >
      {text}
      <ArrowUpRight size={12} className="text-ink-faint" />
    </a>
  );
}

export function AddressLink({
  address,
  full = false,
  className = "",
}: {
  address: string | null | undefined;
  full?: boolean;
  className?: string;
}) {
  const { cell } = useCell();
  if (!address) return <span className="text-ink-faint">—</span>;
  const url = explorerAccount(cell, address);
  const text = full ? address : shortAddress(address);
  if (!url) return <span className={`num text-ink-muted ${className}`}>{text}</span>;
  return (
    <a
      href={url}
      target="_blank"
      rel="noreferrer"
      title={address}
      className={`num inline-flex items-center gap-0.5 break-all text-ink hover:text-accent ${className}`}
    >
      {text}
      <ArrowUpRight size={12} className="shrink-0 text-ink-faint" />
    </a>
  );
}

export function JobLink({ id, className = "" }: { id: string | null | undefined; className?: string }) {
  if (!id) return <span className="text-ink-faint">—</span>;
  return (
    <Link href={`/jobs/${id}`} className={`num text-ink hover:text-accent ${className}`} title={id}>
      {id.split("-")[0]}
    </Link>
  );
}

export function ArmLink({ role, className = "" }: { role: string | null | undefined; className?: string }) {
  if (!role) return <span className="text-ink-faint">—</span>;
  return (
    <Link href={`/arms/${role}`} className={`text-ink capitalize hover:text-accent ${className}`}>
      {role}
    </Link>
  );
}
