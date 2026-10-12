"use client";

import { ArrowRight, Loader2 } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useCell } from "./cell-provider";
import { Pill } from "./pill";
import { VoiceWidget } from "./voice-widget";
import { apiBase } from "@/lib/api";

type Placed = { id: string; status: string; price_drops: number };

export function HireBox() {
  const { cell } = useCell();
  const [instruction, setInstruction] = useState("put the white drone in the orange container");
  const [busy, setBusy] = useState(false);
  const [placed, setPlaced] = useState<Placed | null>(null);
  const [error, setError] = useState<string | null>(null);
  const base = apiBase(cell);
  const online = Boolean(cell?.online && base);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!base || busy) return;
    setBusy(true);
    setError(null);
    setPlaced(null);
    try {
      const res = await fetch(`${base}/jobs/house`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ instruction: instruction.trim(), requester: "dashboard" }),
      });
      if (!res.ok) throw new Error((await res.text()).slice(0, 160) || `HTTP ${res.status}`);
      setPlaced((await res.json()) as Placed);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card flex flex-col gap-3 px-4 py-4">
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-sm font-semibold tracking-tight">Hire the cell</h2>
        {online ? <Pill tone="accent" live>taking jobs</Pill> : <Pill tone="neutral">offline</Pill>}
      </div>
      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row">
        <input
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          disabled={!online || busy}
          placeholder="what should the arms do?"
          className="num min-w-0 flex-1 rounded border border-line bg-inset px-3 py-2 text-sm text-ink outline-none focus:border-accent"
        />
        <button
          type="submit"
          disabled={!online || busy || instruction.trim().length < 3}
          className="inline-flex items-center justify-center gap-2 rounded bg-accent px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? <Loader2 size={16} className="animate-spin" /> : <ArrowRight size={16} />}
          {busy ? "paying" : "hire"}
        </button>
      </form>
      <p className="text-xs text-ink-muted">
        Type it or say it. The house account pays the 402 and the job runs like any other: survey, bids, escrow, work, verification, settlement.
      </p>
      {placed && (
        <p className="text-sm">
          Paid {(placed.price_drops / 1_000_000).toFixed(2)} XRP · job{" "}
          <Link href={`/jobs/${placed.id}`} className="num text-accent underline-offset-2 hover:underline">
            {placed.id.split("-")[0]}
          </Link>{" "}
          is {placed.status}.
        </p>
      )}
      {error && <p className="text-sm text-bad">{error}</p>}
      {cell?.voice_agent_id && <VoiceWidget agentId={cell.voice_agent_id} />}
    </section>
  );
}
