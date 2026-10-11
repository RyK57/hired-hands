"use client";

import { Coins, ShieldCheck, Terminal } from "lucide-react";
import { useCell } from "./cell-provider";
import { Card } from "./card";
import { CopyButton } from "./copy-button";
import { Empty, Loading } from "./empty";
import { Pill } from "./pill";
import type { Json } from "@/lib/types";

const PRIMARY_KEYS = ["scheme", "network", "asset", "currency", "amount", "maxAmountRequired", "payTo", "description"] as const;

function titleOf(option: Record<string, Json>, index: number): string {
  const scheme = typeof option.scheme === "string" ? option.scheme : null;
  const asset = typeof option.asset === "string" ? option.asset : typeof option.currency === "string" ? option.currency : null;
  const network = typeof option.network === "string" ? option.network : null;
  const parts = [scheme, asset, network].filter(Boolean);
  return parts.length ? parts.join(" · ") : `Option ${index + 1}`;
}

function valueText(value: Json): string {
  if (value === null) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function AcceptCard({ option, index }: { option: Json; index: number }) {
  if (typeof option === "string") {
    return (
      <div className="card px-4 py-3">
        <span className="text-sm font-medium">{option}</span>
      </div>
    );
  }
  if (!option || typeof option !== "object" || Array.isArray(option)) {
    return (
      <div className="card px-4 py-3">
        <span className="num text-sm">{valueText(option)}</span>
      </div>
    );
  }
  const record = option as Record<string, Json>;
  const known = PRIMARY_KEYS.filter((k) => k in record && k !== "scheme" && k !== "description");
  const extra = Object.keys(record).filter((k) => !(PRIMARY_KEYS as readonly string[]).includes(k));
  return (
    <div className="card flex flex-col gap-3 px-4 py-3">
      <div className="flex items-start justify-between gap-3">
        <span className="text-sm font-medium">{titleOf(record, index)}</span>
        <Pill tone="accent">accepted</Pill>
      </div>
      {typeof record.description === "string" && <p className="text-sm text-ink-muted">{record.description}</p>}
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
        {[...known, ...extra].map((k) => (
          <div key={k} className="contents">
            <dt className="label">{k}</dt>
            <dd className="num min-w-0 break-all text-ink">{valueText(record[k])}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function Hire() {
  const { cell, loading } = useCell();
  const api = cell?.api_url?.replace(/\/$/, "") ?? null;
  const base = api ?? "$API";
  const request = `curl -X POST ${base}/jobs \\
  -H 'Content-Type: application/json' \\
  -d '{"instruction":"put the red block in the blue cup"}'`;
  const accepts = Array.isArray(cell?.accepts) ? cell.accepts : [];

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-col gap-1">
        <h1 className="text-lg font-semibold tracking-tight">Hire the cell</h1>
        <p className="text-sm text-ink-muted">Send an instruction, pay for the job, get a verified result. People and agents use the same door.</p>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card title="API" className="lg:col-span-2" aside={loading && !cell ? null : api ? <Pill tone="accent" live>taking jobs</Pill> : <Pill tone="neutral">offline</Pill>}>
          {loading && !cell ? (
            <Loading rows={2} />
          ) : api ? (
            <div className="flex flex-col gap-3 px-4 py-4">
              <div className="flex flex-wrap items-center gap-3">
                <code className="num rounded border border-line bg-inset px-2.5 py-1.5 text-sm text-ink">{api}</code>
                <CopyButton text={api} label="Copy URL" />
              </div>
              <p className="text-sm text-ink-muted">
                One endpoint: <code className="num text-ink">POST /jobs</code>. Each job is priced by the arms and paid for before any motor moves.
              </p>
            </div>
          ) : (
            <Empty icon={Terminal} title="The cell is not taking jobs right now." detail="The API address is published here when the cell comes online." compact />
          )}
        </Card>

        <Card title="Payment" aside={accepts.length > 0 ? <span className="num">{accepts.length} option{accepts.length === 1 ? "" : "s"}</span> : null}>
          {loading && !cell ? (
            <Loading rows={2} />
          ) : accepts.length === 0 ? (
            <Empty icon={Coins} title="No payment options published." detail="The accepted assets and networks are listed here once the cell is online." compact />
          ) : (
            <div className="flex flex-col gap-3 px-4 py-4">
              {accepts.map((option, i) => (
                <AcceptCard key={i} option={option} index={i} />
              ))}
            </div>
          )}
        </Card>
      </div>

      <Card title="Request" aside={<CopyButton text={request} label="Copy" />}>
        <pre className="num overflow-x-auto px-4 py-4 text-[13px] leading-6 text-ink">
          <code>{request}</code>
        </pre>
        <div className="grid grid-cols-1 gap-4 border-t border-line px-4 py-4 sm:grid-cols-3">
          <div className="flex flex-col gap-1">
            <span className="label">1 · Ask</span>
            <p className="text-sm text-ink-muted">
              Post the instruction in plain language. The head camera surveys the table and the arms bid on the job.
            </p>
          </div>
          <div className="flex flex-col gap-1">
            <span className="label">2 · 402 Payment Required</span>
            <p className="text-sm text-ink-muted">
              The first response is <code className="num text-ink">402</code> with x402 payment requirements: asset, amount and the address to pay.
            </p>
          </div>
          <div className="flex flex-col gap-1">
            <span className="label">3 · Pay and retry</span>
            <p className="text-sm text-ink-muted">
              An x402 client pays and retries the same request with the <code className="num text-ink">PAYMENT-SIGNATURE</code> header. The reply carries the job id.
            </p>
          </div>
        </div>
        <div className="flex items-start gap-2 border-t border-line px-4 py-3 text-sm text-ink-muted">
          <ShieldCheck size={16} className="mt-0.5 shrink-0 text-ok" />
          <span>
            Payment sits in a conditional escrow on the XRP Ledger until the head camera verifies the result. A failed job refunds the escrow; a finished one releases it to the arm that did the work.
          </span>
        </div>
      </Card>
    </div>
  );
}
