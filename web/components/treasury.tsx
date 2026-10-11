"use client";

import { Landmark, Radio, Users } from "lucide-react";
import { useCell } from "./cell-provider";
import { Card, KeyValue, Stat } from "./card";
import { Empty, Loading } from "./empty";
import { AddressLink, ArmLink, JobLink, TxLink } from "./links";
import { Pill } from "./pill";
import { useNow } from "@/lib/clock";
import { useLiveTable } from "@/lib/live";
import { basisPoints, relativeTime, seconds, xrp } from "@/lib/format";
import { channelTone, loanTone } from "@/lib/status";

function sum(values: (number | null | undefined)[]): number {
  return values.reduce<number>((acc, v) => acc + (typeof v === "number" ? v : 0), 0);
}

export function Treasury() {
  const { cell, loading: cellLoading } = useCell();
  const depositors = useLiveTable("depositors", { order: { column: "created_at" } });
  const loans = useLiveTable("loans", { order: { column: "created_at" } });
  const channels = useLiveTable("channels", { order: { column: "created_at" } });
  const now = useNow();

  const deposited = sum(depositors.rows.map((d) => d.deposited_drops));
  const activeLoans = loans.rows.filter((l) => l.status === "active");
  const outstanding = sum(activeLoans.map((l) => l.outstanding_drops));
  const openChannels = channels.rows.filter((c) => c.status === "open");
  const streamed = sum(channels.rows.map((c) => c.claimed_drops));

  return (
    <div className="flex flex-col gap-4">
      <header className="flex flex-col gap-1">
        <h1 className="text-lg font-semibold tracking-tight">Treasury</h1>
        <p className="text-sm text-ink-muted">The vault the arms borrow from, who funds it, and the channels that pay human operators.</p>
      </header>

      <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <div className="card px-4 py-3">
          <Stat label="Deposited" value={`${xrp(deposited)} XRP`} sub={`${depositors.rows.length} depositor${depositors.rows.length === 1 ? "" : "s"}`} />
        </div>
        <div className="card px-4 py-3">
          <Stat label="Outstanding" value={`${xrp(outstanding)} XRP`} sub={`${activeLoans.length} active loan${activeLoans.length === 1 ? "" : "s"}`} />
        </div>
        <div className="card px-4 py-3">
          <Stat label="Streamed to operators" value={`${xrp(streamed)} XRP`} sub={`${channels.rows.length} channel${channels.rows.length === 1 ? "" : "s"}`} />
        </div>
        <div className="card px-4 py-3">
          <Stat label="Open channels" value={openChannels.length} sub={openChannels.length ? "operator driving" : "no operator connected"} />
        </div>
      </section>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Card title="Vault">
          {cellLoading && !cell ? (
            <Loading rows={4} />
          ) : (
            <KeyValue
              rows={[
                {
                  key: "Vault id",
                  value: cell?.vault_id ? (
                    <span className="num block max-w-[220px] truncate" title={cell.vault_id}>
                      {cell.vault_id}
                    </span>
                  ) : (
                    <span className="text-ink-faint">not created</span>
                  ),
                },
                { key: "Broker", value: <AddressLink address={cell?.broker_address} /> },
                {
                  key: "Domain id",
                  value: cell?.domain_id ? (
                    <span className="num block max-w-[220px] truncate" title={cell.domain_id}>
                      {cell.domain_id}
                    </span>
                  ) : (
                    <span className="text-ink-faint">not created</span>
                  ),
                },
                { key: "Treasury", value: <AddressLink address={cell?.treasury_address} /> },
                { key: "Operator", value: <AddressLink address={cell?.operator_address} /> },
              ]}
            />
          )}
        </Card>

        <Card title="Depositors" className="lg:col-span-2" aside={depositors.rows.length > 0 ? <span className="num">{depositors.rows.length}</span> : null}>
          {depositors.loading && depositors.rows.length === 0 ? (
            <Loading rows={3} />
          ) : depositors.rows.length === 0 ? (
            <Empty icon={Users} title="No depositors yet." detail="Verified lenders fund the vault and receive shares." compact />
          ) : (
            <div className="overflow-x-auto">
              <table className="table-grid">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Address</th>
                    <th>Domain</th>
                    <th>Verified</th>
                    <th className="text-right">Deposited</th>
                    <th className="text-right">Shares</th>
                    <th>Deposit</th>
                    <th>Credential</th>
                  </tr>
                </thead>
                <tbody>
                  {depositors.rows.map((d) => (
                    <tr key={d.address}>
                      <td className="font-medium">{d.name ?? "—"}</td>
                      <td>
                        <AddressLink address={d.address} />
                      </td>
                      <td className="text-ink-muted">{d.domain ?? "—"}</td>
                      <td>{d.verified ? <Pill tone="ok">verified</Pill> : <Pill tone="neutral">unverified</Pill>}</td>
                      <td className="num text-right">{xrp(d.deposited_drops)} XRP</td>
                      <td className="num text-right">{d.shares ?? "—"}</td>
                      <td>
                        <TxLink hash={d.deposit_tx} />
                      </td>
                      <td>
                        <TxLink hash={d.credential_tx} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      <Card title="Loans" aside={activeLoans.length > 0 ? <span className="num">{activeLoans.length} active</span> : null}>
        {loans.loading && loans.rows.length === 0 ? (
          <Loading rows={3} />
        ) : loans.rows.length === 0 ? (
          <Empty icon={Landmark} title="No loans yet." detail="An arm borrows when a job costs more than it holds." compact />
        ) : (
          <div className="overflow-x-auto">
            <table className="table-grid">
              <thead>
                <tr>
                  <th>Loan</th>
                  <th>Arm</th>
                  <th className="text-right">Principal</th>
                  <th className="text-right">Outstanding</th>
                  <th className="text-right">Interest</th>
                  <th>Status</th>
                  <th>Opened</th>
                  <th>Last payment</th>
                </tr>
              </thead>
              <tbody>
                {loans.rows.map((loan) => (
                  <tr key={loan.id}>
                    <td className="num" title={loan.id}>
                      {loan.id.length > 14 ? `${loan.id.slice(0, 12)}…` : loan.id}
                    </td>
                    <td>
                      <ArmLink role={loan.arm_role} />
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
        )}
      </Card>

      <Card title="Pay channels" aside={openChannels.length > 0 ? <span className="num">{openChannels.length} open</span> : null}>
        {channels.loading && channels.rows.length === 0 ? (
          <Loading rows={3} />
        ) : channels.rows.length === 0 ? (
          <Empty icon={Radio} title="No channels yet." detail="A channel opens when a human operator takes over a job and is paid per second." compact />
        ) : (
          <div className="overflow-x-auto">
            <table className="table-grid">
              <thead>
                <tr>
                  <th>Channel</th>
                  <th>Job</th>
                  <th>Operator</th>
                  <th className="text-right">Funded</th>
                  <th className="text-right">Claimed</th>
                  <th className="text-right">Driven</th>
                  <th>Status</th>
                  <th>Open</th>
                  <th>Close</th>
                </tr>
              </thead>
              <tbody>
                {channels.rows.map((c) => (
                  <tr key={c.id}>
                    <td className="num" title={c.id}>
                      {c.id.length > 14 ? `${c.id.slice(0, 12)}…` : c.id}
                    </td>
                    <td>
                      <JobLink id={c.job_id} />
                    </td>
                    <td>
                      <AddressLink address={c.operator_address} />
                    </td>
                    <td className="num text-right">{xrp(c.amount_drops)} XRP</td>
                    <td className="num text-right">{xrp(c.claimed_drops ?? 0)} XRP</td>
                    <td className="num text-right">{seconds(c.seconds_driven)}</td>
                    <td>
                      <Pill tone={channelTone(c.status)} live={c.status === "open"}>
                        {c.status ?? "open"}
                      </Pill>
                    </td>
                    <td>
                      <TxLink hash={c.open_tx} />
                    </td>
                    <td>
                      <TxLink hash={c.close_tx} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
