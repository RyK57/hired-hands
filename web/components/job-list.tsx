"use client";

import Link from "next/link";
import { Boxes } from "lucide-react";
import { Pill } from "./pill";
import { Empty, Loading } from "./empty";
import { useNow } from "@/lib/clock";
import { relativeTime, xrp } from "@/lib/format";
import { jobIsLive, jobTone } from "@/lib/status";
import type { Job } from "@/lib/types";

export function JobList({
  jobs,
  loading,
  showWorker = true,
  emptyTitle = "No jobs yet.",
  emptyDetail = "Jobs appear here the moment a request is paid for.",
}: {
  jobs: Job[];
  loading: boolean;
  showWorker?: boolean;
  emptyTitle?: string;
  emptyDetail?: string;
}) {
  const now = useNow();
  if (loading && jobs.length === 0) return <Loading rows={4} />;
  if (jobs.length === 0) return <Empty icon={Boxes} title={emptyTitle} detail={emptyDetail} />;
  return (
    <ul className="divide-y divide-line">
      {jobs.map((job) => (
        <li key={job.id}>
          <Link
            href={`/jobs/${job.id}`}
            className="grid grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-1 px-4 py-2.5 transition-colors hover:bg-inset/60 sm:grid-cols-[110px_1fr_auto_auto_auto]"
          >
            <Pill tone={jobTone(job.status)} live={jobIsLive(job.status)}>
              {job.status ?? "requested"}
            </Pill>
            <span className="min-w-0 truncate text-sm text-ink">{job.instruction ?? "Untitled job"}</span>
            <span className="num text-right text-sm text-ink">{job.price_drops !== null ? `${xrp(job.price_drops)} XRP` : "—"}</span>
            {showWorker && (
              <span className="col-start-2 text-xs text-ink-muted capitalize sm:col-start-auto sm:w-12 sm:text-right">
                {job.worker_role ?? "—"}
              </span>
            )}
            <time
              dateTime={job.created_at ?? undefined}
              className="num col-start-3 text-right text-xs text-ink-faint sm:col-start-auto sm:w-16"
              title={job.created_at ?? undefined}
            >
              {relativeTime(job.created_at, now)}
            </time>
          </Link>
        </li>
      ))}
    </ul>
  );
}
