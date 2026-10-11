"use client";

import Link from "next/link";
import { ArrowLeft, Landmark } from "lucide-react";
import { healthScore, lowestVoltage, JointReadout } from "./arm-card";
import { Card, KeyValue, Stat } from "./card";
import { CopyButton } from "./copy-button";
import { Empty, Loading } from "./empty";
import { EventFeed } from "./event-feed";
import { JobList } from "./job-list";
import { AddressLink, TxLink } from "./links";
import { Meter } from "./meter";
import { Pill } from "./pill";
import { useLiveRow, useLiveTable } from "@/lib/live";
import { absoluteDate, basisPoints, celsius, percent, relativeTime, volts, xrp } from "@/lib/format";
import { armIsLive, armTone, credentialTone, loanTone } from "@/lib/status";
import { ARM_ROLES, type Loan } from "@/lib/types";
import { useNow } from "@/lib/clock";

function LoansTable({ loans, loading }: { loans: Loan[]; loading: boolean }) {
  const now = useNow();
  if (loading && loans.length === 0) return <Loading rows={2} />;
  if (loans.length === 0) return <Empty icon={Landmark} title="No loans." detail="This arm has not borrowed from the vault." compact />;
  return (
    <div className="overflow-x-auto">
      <table className="table-grid">
        <thead>
          <tr>
            <th>Loan</th>
            <th className="text-right">Principal</th>
            <th className="text-right">Outstanding</th>
            <th className="text-right">Interest</th>
            <th>Status</th>
            <th>Opened</th>
            <th>Last payment</th>
          </tr>
        </thead>
        <tbody>
          {loans.map((loan) => (
            <tr key={loan.id}>
              <td className="num" title={loan.id}>
                {loan.id.length > 14 ? `${loan.id.slice(0, 12)}…` : loan.id}
              </td>
              <td className="num text-right">{xrp(loan.principal_drops)} XRP</td>
              <td className="num text-right">{xrp(loan.outstanding_drops)} XRP</td>
              <td className="num text-right">{basisPoints(loan.interest_bps)}</td>
              <td>
                <Pill tone={loanTone(loan.status)}>{loan.status ?? "active"}</Pill>
              </td>
              <td>
                <span className="flex items-center gap-2">
                  <TxLink hash={loan.open_tx} />
                  <span className="text-xs text-ink-faint">{relativeTime(loan.created_at, now)}</span>
                </span>
              </td>
              <td>
                <TxLink hash={loan.last_payment_tx} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ArmDetail({ role }: { role: string }) {
  const valid = (ARM_ROLES as string[]).includes(role);
  const arm = useLiveRow("arms", valid ? role : null);
  const jobs = useLiveTable("jobs", { eq: ["worker_role", role], order: { column: "created_at" }, limit: 20, enabled: valid });
  const loans = useLiveTable("loans", { eq: ["arm_role", role], order: { column: "created_at" }, enabled: valid });
  const events = useLiveTable("events", { eq: ["arm_role", role], order: { column: "created_at" }, limit: 30, enabled: valid });

  if (!valid || (!arm.loading && !arm.row)) {
    return (
      <div className="card">
        <Empty title="No arm with this role." detail="The cell has a left, a head and a right arm." />
        <div className="border-t border-line px-4 py-3">
          <Link href="/" className="link text-sm">
            Back to the overview
          </Link>
        </div>
      </div>
    );
  }

  if (!arm.row) {
    return (
      <div className="card">
        <Loading rows={5} />
      </div>
    );
  }

  const row = arm.row;
  const score = healthScore(row);
  const health = row.health;
  const live = armIsLive(row.state);
  const fit =
    typeof health?.fit === "boolean"
      ? health.fit
      : score !== null && typeof health?.servos_ok === "number"
        ? score >= 0.5 && health.servos_ok === 6
        : null;
  const earnedNet = (row.earned_drops ?? 0) - (row.debt_drops ?? 0);

  return (
    <div className="flex flex-col gap-4">
      <Link href="/" className="inline-flex items-center gap-1 text-xs text-ink-muted hover:text-ink">
        <ArrowLeft size={12} /> Overview
      </Link>

      <header className="card flex flex-wrap items-center justify-between gap-3 px-4 py-4">
        <div className="flex items-center gap-3">
          <h1 className="text-lg font-semibold tracking-tight text-ink capitalize">{role} arm</h1>
          <Pill tone={armTone(row.state)} live={live}>
            {row.state ?? "offline"}
          </Pill>
        </div>
        <div className="flex items-center gap-4 text-xs text-ink-faint">
          {row.board && (
            <span>
              board <span className="num text-ink-muted">{row.board}</span>
            </span>
          )}
          <span>updated {relativeTime(row.updated_at)}</span>
        </div>
      </header>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card title="Identity">
          <KeyValue
            rows={[
              { key: "Address", value: <AddressLink address={row.address} /> },
              {
                key: "DID",
                value: row.did ? (
                  <span className="flex items-center justify-end gap-2">
                    <span className="num block max-w-[180px] truncate" title={row.did}>
                      {row.did}
                    </span>
                    <CopyButton text={row.did} label="Copy" className="h-6" />
                  </span>
                ) : (
                  <span className="text-ink-faint">not issued</span>
                ),
              },
              { key: "Credential", value: <Pill tone={credentialTone(row.credential)}>{row.credential ?? "none"}</Pill> },
              { key: "Role", value: <span className="capitalize">{row.role}</span> },
            ]}
          />
        </Card>

        <Card title="Health" aside={<span className="num">{percent(score)}</span>}>
          <div className="flex flex-col gap-4 px-4 py-4">
            <Meter value={score} />
            <div className="grid grid-cols-2 gap-x-4 gap-y-3">
              <Stat label="Lowest voltage" value={volts(lowestVoltage(health))} />
              <Stat label="Hottest servo" value={celsius(health?.temperature)} />
              <Stat label="Servos" value={typeof health?.servos_ok === "number" ? `${health.servos_ok} / 6` : "—"} />
              <Stat
                label="Fit for work"
                mono={false}
                value={
                  fit === null ? (
                    <span className="text-ink-faint">—</span>
                  ) : (
                    <Pill tone={fit ? "ok" : "bad"}>{fit ? "yes" : "no"}</Pill>
                  )
                }
              />
            </div>
            {health?.reasons && health.reasons.length > 0 && (
              <ul className="flex flex-col gap-1 rounded border border-warn/30 bg-warn-soft px-3 py-2 text-xs text-warn">
                {health.reasons.map((reason, i) => (
                  <li key={i}>{reason}</li>
                ))}
              </ul>
            )}
            <div className="flex flex-col gap-1.5">
              <span className="label">Joints</span>
              <JointReadout joints={row.joints} />
            </div>
          </div>
        </Card>

        <Card title="Earnings">
          <div className="grid grid-cols-2 gap-x-4 gap-y-3 px-4 py-4">
            <Stat label="Balance" value={`${xrp(row.balance_drops)} XRP`} />
            <Stat label="Debt" value={`${xrp(row.debt_drops ?? 0)} XRP`} />
            <Stat label="Jobs done" value={row.jobs_done ?? 0} />
            <Stat label="Earned" value={`${xrp(row.earned_drops ?? 0)} XRP`} />
            <Stat label="Net of debt" value={`${xrp(earnedNet)} XRP`} className="col-span-2" />
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="flex flex-col gap-4 lg:col-span-2">
          <Card title="Jobs" aside={jobs.rows.length > 0 ? <span className="num">{jobs.rows.length} recent</span> : null}>
            <JobList
              jobs={jobs.rows}
              loading={jobs.loading}
              showWorker={false}
              emptyTitle="No jobs worked yet."
              emptyDetail="Jobs this arm wins appear here."
            />
          </Card>
          <Card title="Loans">
            <LoansTable loans={loans.rows} loading={loans.loading} />
          </Card>
        </div>
        <Card title="Activity" bodyClassName="max-h-[720px] overflow-y-auto">
          <EventFeed
            events={events.rows}
            loading={events.loading}
            showArm={false}
            emptyTitle="No activity yet."
            emptyDetail={`Everything the ${role} arm does is written here.`}
          />
        </Card>
      </div>
      <p className="text-xs text-ink-faint">Readings as of {absoluteDate(row.updated_at)}.</p>
    </div>
  );
}
