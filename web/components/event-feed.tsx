"use client";

import { Activity } from "lucide-react";
import { EventIcon } from "./event-icon";
import { Empty, Loading } from "./empty";
import { ArmLink, JobLink, TxLink } from "./links";
import { useNow } from "@/lib/clock";
import { kindLabel, relativeTime, xrp } from "@/lib/format";
import type { Event } from "@/lib/types";

export function EventRow({
  event,
  now,
  showJob = true,
  showArm = true,
}: {
  event: Event;
  now: number;
  showJob?: boolean;
  showArm?: boolean;
}) {
  return (
    <li className="flex items-start gap-3 px-4 py-2.5">
      <EventIcon kind={event.kind} />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <div className="flex items-baseline justify-between gap-3">
          <span className="truncate text-sm font-medium text-ink">{kindLabel(event.kind)}</span>
          <time dateTime={event.created_at ?? undefined} className="num shrink-0 text-xs text-ink-faint" title={event.created_at ?? undefined}>
            {relativeTime(event.created_at, now)}
          </time>
        </div>
        {event.message && <p className="line-clamp-2 text-sm text-ink-muted">{event.message}</p>}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-faint">
          {showArm && event.arm_role && <ArmLink role={event.arm_role} className="text-ink-muted" />}
          {showJob && event.job_id && (
            <span>
              job <JobLink id={event.job_id} className="text-ink-muted" />
            </span>
          )}
          {event.amount_drops !== null && event.amount_drops !== undefined && (
            <span className="num text-ink">{xrp(event.amount_drops)} XRP</span>
          )}
          {event.tx_hash && <TxLink hash={event.tx_hash} href={event.explorer_url} className="text-xs" />}
        </div>
      </div>
    </li>
  );
}

export function EventFeed({
  events,
  loading,
  showJob = true,
  showArm = true,
  emptyTitle = "No events yet.",
  emptyDetail = "Everything the cell does is written here as it happens.",
}: {
  events: Event[];
  loading: boolean;
  showJob?: boolean;
  showArm?: boolean;
  emptyTitle?: string;
  emptyDetail?: string;
}) {
  const now = useNow();
  if (loading && events.length === 0) return <Loading rows={4} />;
  if (events.length === 0) return <Empty icon={Activity} title={emptyTitle} detail={emptyDetail} />;
  return (
    <ul className="divide-y divide-line">
      {events.map((event) => (
        <EventRow key={event.id} event={event} now={now} showJob={showJob} showArm={showArm} />
      ))}
    </ul>
  );
}
