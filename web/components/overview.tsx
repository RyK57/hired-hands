"use client";

import { ArmCard, ArmCardSkeleton } from "./arm-card";
import { CameraView } from "./camera-view";
import { Card } from "./card";
import { EventFeed } from "./event-feed";
import { HireBox } from "./hire-box";
import { JobList } from "./job-list";
import { TableView } from "./table-view";
import { useLiveTable } from "@/lib/live";
import { ARM_ROLES, type Arm } from "@/lib/types";

export function Overview() {
  const arms = useLiveTable("arms");
  const jobs = useLiveTable("jobs", { order: { column: "created_at" }, limit: 12 });
  const events = useLiveTable("events", { order: { column: "created_at" }, limit: 60 });

  const armsByRole = new Map<string, Arm>(arms.rows.map((a) => [a.role, a]));
  const latestJob = jobs.rows.find((j) => j.target || j.destination) ?? jobs.rows[0] ?? null;
  const liveCount = events.rows.length;

  return (
    <div className="flex flex-col gap-4">
      <HireBox />

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <Card title="Camera" className="lg:col-span-3" aside={<span className="num">head</span>}>
          <CameraView />
        </Card>
        <Card
          title="Events"
          className="lg:col-span-2"
          aside={liveCount > 0 ? <span className="num">{liveCount} recent</span> : null}
          bodyClassName="max-h-[520px] overflow-y-auto"
        >
          <EventFeed events={events.rows} loading={events.loading} />
        </Card>
      </section>

      <section className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {ARM_ROLES.map((role) => {
          const arm = armsByRole.get(role);
          return arm ? <ArmCard key={role} arm={arm} /> : <ArmCardSkeleton key={role} role={role} />;
        })}
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <Card title="Recent jobs" className="lg:col-span-3" aside={jobs.rows.length > 0 ? <span className="num">{jobs.rows.length} shown</span> : null}>
          <JobList jobs={jobs.rows} loading={jobs.loading} />
        </Card>
        <Card title="Table" className="lg:col-span-2" aside={latestJob ? <span className="num">job {latestJob.id.split("-")[0]}</span> : null}>
          <TableView arms={arms.rows} job={latestJob} />
        </Card>
      </section>
    </div>
  );
}
