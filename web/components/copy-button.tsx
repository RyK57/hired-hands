"use client";

import { useEffect, useState } from "react";
import { Check, Copy } from "lucide-react";

export function CopyButton({ text, label = "Copy", className = "" }: { text: string; label?: string; className?: string }) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const id = window.setTimeout(() => setCopied(false), 1600);
    return () => window.clearTimeout(id);
  }, [copied]);

  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
        } catch {
          setCopied(false);
        }
      }}
      className={`inline-flex h-7 items-center gap-1.5 rounded border border-line bg-surface px-2 text-xs text-ink-muted transition-colors hover:border-line-strong hover:text-ink ${className}`}
      aria-label={label}
    >
      {copied ? <Check size={12} className="text-ok" /> : <Copy size={12} />}
      {copied ? "Copied" : label}
    </button>
  );
}
