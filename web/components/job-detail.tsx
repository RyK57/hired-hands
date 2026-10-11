"use client";

import Image from "next/image";
import Link from "next/link";
import { ArrowLeft, Gavel, ImageOff } from "lucide-react";
import { Card, KeyValue, Stat } from "./card";
import { CopyButton } from "./copy-button";
import { Empty, Loading } from "./empty";
import { EventIcon } from "./event-icon";
import { AddressLink, ArmLink, TxLink } from "./links";
import { Pill } from "./pill";
import { useNow } from "@/lib/clock";
import { useLiveRow, useLiveTable } from "@/lib/live";
import { absoluteTime, centimetres, clockTime, duration, kindLabel, percent, relativeTime, seconds, xrp } from "@/lib/format";
import { channelTone, jobIsLive, jobTone } from "@/lib/status";
import { ARM_ROLES, type Bid, type Channel, type Event, type Job, type Spot } from "@/lib/types";

function spotText(spot: Spot | null | undefined): string {
  if (!spot) return "—";
  const parts: string[] = [];
  if (typeof spot.index === "number") parts.push(`#${spot.index}`);
  if (spot.colour) parts.push(spot.colour);
  if (spot.table && spot.table.length === 2) parts.push(`(${spot.table[0].toFixed(3)}, ${spot.table[1].toFixed(3)})`);
  return parts.length ? parts.join(" ") : "—";
}

function Timeline({ events, loading }: { events: Event[]; loading: boolean }) {
  const now = useNow();
  if (loading && events.length === 0) return <Loading rows={4} />;
  if (events.length === 0) return <Empty title="Nothing has happened yet." detail="Each step of the job is recorded here." compact />;
  return (
    <ol className="relative flex flex-col">
      {events.map((event, i) => (
        <li key={event.id} className="relative flex gap-3 px-4 py-2.5">
          {i < events.length - 1 && <span className="absolute top-9 bottom-0 left-[29px] w-px bg-line" aria-hidden="true" />}
          <EventIcon kind={event.kind} />
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <div className="flex items-baseline justify-between gap-3">
              <span className="text-sm font-medium text-ink">{kindLabel(event.kind)}</span>
              <time
                dateTime={event.created_at ?? undefined}
                title={absoluteTime(event.created_at)}
                className="num shrink-0 text-xs text-ink-faint"
              >
                {clockTime(event.created_at)} · {relativeTime(event.created_at, now)}
              </time>
            </div>
            {event.message && <p className="text-sm text-ink-muted">{event.message}</p>}
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-faint">
              {event.arm_role && <ArmLink role={event.arm_role} className="text-ink-muted" />}
              {event.amount_drops !== null && event.amount_drops !== undefined && (
                <span className="num text-ink">{xrp(event.amount_drops)} XRP</span>
              )}
              {event.tx_hash && <TxLink hash={event.tx_hash} href={event.explorer_url} className="text-xs" />}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}

function BidsTable({ bids, loading, job }: { bids: Bid[]; loading: boolean; job: Job }) {
  if (loading && bids.length === 0) return <Loading rows={3} />;
  if (bids.length === 0) {
    const waiting = job.status === "surveying" || job.status === "bidding" || job.status === "paid";
    return (
      <Empty
        icon={Gavel}
        title={waiting ? "Waiting for bids." : "No bids were placed."}
        detail={waiting ? "Each arm prices the job from its reach and health." : undefined}
        compact
      />
    );
  }
  const byRole = new Map(bids.map((b) => [b.arm_role, b]));
  return (
    <div className="overflow-x-auto">
      <table className="table-grid">
        <thead>
          <tr>
            <th>Arm</th>
            <th>Feasible</th>
            <th className="text-right">Price</th>
            <th className="text-right">Reach</th>
            <th className="text-right">Health</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          {ARM_ROLES.map((role) => {
            const bid = byRole.get(role);
            if (!bid) {
              return (
                <tr key={role} className="text-ink-faint">
                  <td className="capitalize">{role}</td>
                  <td colSpan={5}>No bid</td>
                </tr>
              );
            }
            const won = Boolean(bid.won);
            return (
              <tr key={role} className={won ? "bg-accent-soft/60" : ""}>
                <td>
                  <span className="flex items-center gap-2">
                    <ArmLink role={role} className="font-medium" />
                    {won && <Pill tone="accent">won</Pill>}
                  </span>
                </td>
                <td>
                  {bid.feasible ? <Pill tone="ok">feasible</Pill> : <Pill tone="bad">not feasible</Pill>}
                </td>
                <td className="num text-right">{bid.feasible && bid.price_drops ? `${xrp(bid.price_drops)} XRP` : "—"}</td>
                <td className="num text-right">{centimetres(bid.reach_m)}</td>
                <td className="num text-right">{percent(bid.health_score)}</td>
                <td className="max-w-xs text-ink-muted">{bid.reason ?? "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function Capture({ label, url }: { label: string; url: string | null }) {
  return (
    <figure className="flex min-w-0 flex-col gap-1.5">
      <figcaption className="label">{label}</figcaption>
      <div className="relative aspect-[4/3] w-full overflow-hidden rounded border border-line bg-inset">
        {url ? (
          <Image src={url} alt={`${label} image`} fill sizes="(min-width: 1024px) 33vw, 100vw" className="object-cover" unoptimized />
        ) : (
          <div className="flex h-full w-full items-center justify-center text-ink-faint">
            <ImageOff size={18} strokeWidth={1.5} />
          </div>
        )}
      </div>
    </figure>
  );
}

function ChannelCard({ channel }: { channel: Channel }) {
  return (
    <Card title="Pay channel" aside={<Pill tone={channelTone(channel.status)} live={channel.status === "open"}>{channel.status ?? "open"}</Pill>}>
      <KeyValue
        rows={[
          { key: "Channel", value: <span className="num break-all">{channel.id}</span> },
          { key: "Operator", value: <AddressLink address={channel.operator_address} /> },
          { key: "Funded", value: <span className="num">{xrp(channel.amount_drops)} XRP</span> },
          { key: "Claimed", value: <span className="num">{xrp(channel.claimed_drops ?? 0)} XRP</span> },
          { key: "Driven", value: <span className="num">{seconds(channel.seconds_driven)}</span> },
          { key: "Open tx", value: <TxLink hash={channel.open_tx} /> },
          { key: "Close tx", value: <TxLink hash={channel.close_tx} /> },
        ]}
      />
    </Card>
  );
}

export function JobDetail({ id }: { id: string }) {
  const job = useLiveRow("jobs", id);
  const events = useLiveTable("events", { eq: ["job_id", id], order: { column: "created_at", ascending: true } });
  const bids = useLiveTable("bids", { eq: ["job_id", id], order: { column: "created_at", ascending: true } });
  const channels = useLiveTable("channels", { eq: ["job_id", id], order: { column: "created_at" } });

  if (job.loading && !job.row) {
    return (
      <div className="card">
        <Loading rows={5} />
      </div>
    );
  }

  if (!job.row) {
    return (
      <div className="card">
        <Empty title="No job with this id." detail={job.error ?? id} />
        <div className="border-t border-line px-4 py-3">
          <Link href="/" className="link text-sm">
            Back to the overview
          </Link>
        </div>
      </div>
    );
  }

  const row = job.row;
  const verdict = row.verdict;

  return (
    <div className="flex flex-col gap-4">
      <Link href="/" className="inline-flex items-center gap-1 text-xs text-ink-muted hover:text-ink">
        <ArrowLeft size={12} /> Overview
      </Link>

      <header className="card px-4 py-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex min-w-0 flex-col gap-1">
            <h1 className="text-lg font-semibold tracking-tight text-ink">{row.instruction ?? "Untitled job"}</h1>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-faint">
              <span className="num">{row.id}</span>
              <CopyButton text={row.id} label="Copy id" className="h-6" />
              <span title={absoluteTime(row.created_at)}>Created {absoluteTime(row.created_at)}</span>
              {row.finished_at && <span>Finished {absoluteTime(row.finished_at)}</span>}
              {row.finished_at && <span className="num">{duration(row.created_at, row.finished_at)}</span>}
            </div>
          </div>
          <Pill tone={jobTone(row.status)} live={jobIsLive(row.status)}>
            {row.status ?? "requested"}
          </Pill>
        </div>
        <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
          <Stat label="Price" value={row.price_drops !== null ? `${xrp(row.price_drops)} XRP` : "—"} />
          <Stat label="Requester" value={row.requester ?? "—"} mono={false} />
          <Stat label="Payer" value={<AddressLink address={row.payer_address} />} />
          <Stat label="Worker" mono={false} value={row.worker_role ? <ArmLink role={row.worker_role} /> : "—"} />
        </div>
        {row.error && (
          <p className="mt-4 rounded border border-bad/30 bg-bad-soft px-3 py-2 text-sm text-bad">{row.error}</p>
        )}
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="flex flex-col gap-4 lg:col-span-2">
          <Card title="Timeline" aside={events.rows.length > 0 ? <span className="num">{events.rows.length} events</span> : null}>
            <Timeline events={events.rows} loading={events.loading} />
          </Card>

          <Card
            title="Verification"
            aside={
              verdict ? (
                verdict.ok ? (
                  <Pill tone="ok">verified</Pill>
                ) : (
                  <Pill tone="bad">rejected</Pill>
                )
              ) : row.status === "verifying" ? (
                <Pill tone="accent" live>
                  verifying
                </Pill>
              ) : null
            }
          >
            <div className="grid grid-cols-1 gap-4 px-4 py-4 sm:grid-cols-2">
              <Capture label="Before" url={row.before_image_url} />
              <Capture label="After" url={row.after_image_url} />
            </div>
            <div className="border-t border-line px-4 py-3 text-sm">
              {verdict ? (
                <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
                  <span className={verdict.ok ? "text-ok" : "text-bad"}>{verdict.reason ?? (verdict.ok ? "Placed where it was asked." : "Not placed as asked.")}</span>
                  {typeof verdict.distance_m === "number" && (
                    <span className="num text-ink-muted">{centimetres(verdict.distance_m)} from the destination</span>
                  )}
                </div>
              ) : (
                <span className="text-ink-faint">
                  {row.before_image_url || row.after_image_url
                    ? "The head camera compares both frames once the work is done."
                    : "Captures from the head camera appear here when the job starts."}
                </span>
              )}
            </div>
          </Card>

          <Card title="Bids">
            <BidsTable bids={bids.rows} loading={bids.loading} job={row} />
          </Card>
        </div>

        <div className="flex flex-col gap-4">
          <Card title="Plan">
            <KeyValue
              rows={[
                { key: "Target", value: <span className="num">{spotText(row.target)}</span> },
                { key: "Destination", value: <span className="num">{spotText(row.destination)}</span> },
                { key: "Teleop", value: row.teleop ? <Pill tone="warn">operator</Pill> : <span className="text-ink-muted">no</span> },
              ]}
            />
          </Card>

          <Card title="Ledger">
            <KeyValue
              rows={[
                { key: "Payment", value: <TxLink hash={row.payment_tx} /> },
                { key: "Escrow", value: <TxLink hash={row.escrow_tx} /> },
                {
                  key: "Sequence",
                  value: <span className="num">{row.escrow_sequence ?? "—"}</span>,
                },
                {
                  key: "Condition",
                  value: row.condition ? (
                    <span className="num block max-w-[200px] truncate" title={row.condition}>
                      {row.condition}
                    </span>
                  ) : (
                    <span className="text-ink-faint">—</span>
                  ),
                },
                { key: "Release", value: <TxLink hash={row.release_tx} /> },
                { key: "Settlement", value: <TxLink hash={row.settlement_tx} /> },
              ]}
            />
          </Card>

          {channels.rows.map((channel) => (
            <ChannelCard key={channel.id} channel={channel} />
          ))}
        </div>
      </div>
    </div>
  );
}
