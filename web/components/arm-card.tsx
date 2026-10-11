"use client";

import Link from "next/link";
import { ArrowUpRight } from "lucide-react";
import { Pill } from "./pill";
import { Meter } from "./meter";
import { Stat } from "./card";
import { AddressLink } from "./links";
import { armIsLive, armTone, credentialTone } from "@/lib/status";
import { celsius, degrees, percent, volts, xrp } from "@/lib/format";
import { JOINT_NAMES, type Arm, type Health, type Joints } from "@/lib/types";

const JOINT_SHORT: Record<keyof Joints, string> = {
  shoulder_pan: "pan",
  shoulder_lift: "lift",
  elbow_flex: "elbow",
  wrist_flex: "w.flex",
  wrist_roll: "w.roll",
  gripper: "grip",
};

export function lowestVoltage(health: Health | null | undefined): number | null {
  const v = health?.voltage;
  if (typeof v === "number") return v;
  if (Array.isArray(v)) {
    const nums = (v as unknown[]).filter((x): x is number => typeof x === "number" && x > 0);
    return nums.length ? Math.min(...nums) : null;
  }
  return null;
}

export function healthScore(arm: Arm): number | null {
  if (typeof arm.health_score === "number") return arm.health_score;
  if (typeof arm.health?.score === "number") return arm.health.score;
  return null;
}

export function JointReadout({ joints }: { joints: Joints | null | undefined }) {
  return (
    <div className="grid grid-cols-3 gap-x-3 gap-y-1.5">
      {JOINT_NAMES.map((name) => (
        <div key={name} className="flex items-baseline justify-between gap-2 border-b border-line/70 pb-1">
          <span className="text-[10px] text-ink-faint">{JOINT_SHORT[name]}</span>
          <span className="num text-xs text-ink">{degrees(joints?.[name])}</span>
        </div>
      ))}
    </div>
  );
}

export function ArmCard({ arm }: { arm: Arm }) {
  const score = healthScore(arm);
  const voltage = lowestVoltage(arm.health);
  const live = armIsLive(arm.state);

  return (
    <article className={`card flex flex-col ${live ? "border-accent/50" : ""}`}>
      <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
        <Link href={`/arms/${arm.role}`} className="group flex items-center gap-1.5">
          <h3 className="text-sm font-semibold tracking-tight capitalize">{arm.role}</h3>
          <ArrowUpRight size={14} className="text-ink-faint transition-colors group-hover:text-accent" />
        </Link>
        <Pill tone={armTone(arm.state)} live={live}>
          {arm.state ?? "offline"}
        </Pill>
      </header>

      <div className="flex flex-col gap-4 px-4 py-4">
        <div className="flex flex-col gap-1.5">
          <div className="flex items-baseline justify-between">
            <span className="label">Health</span>
            <span className="num text-sm">{percent(score)}</span>
          </div>
          <Meter value={score} />
          <div className="flex items-center justify-between text-xs text-ink-muted">
            <span className="num">{volts(voltage)}</span>
            <span className="num">{celsius(arm.health?.temperature)}</span>
            <span className="num">
              {typeof arm.health?.servos_ok === "number" ? `${arm.health.servos_ok}/6 servos` : "— servos"}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-x-4 gap-y-3">
          <Stat label="Credential" mono={false} value={<Pill tone={credentialTone(arm.credential)}>{arm.credential ?? "none"}</Pill>} />
          <Stat label="Address" value={<AddressLink address={arm.address} />} />
          <Stat label="Balance" value={`${xrp(arm.balance_drops)} XRP`} />
          <Stat label="Debt" value={`${xrp(arm.debt_drops ?? 0)} XRP`} />
          <Stat label="Jobs done" value={arm.jobs_done ?? 0} />
          <Stat label="Earned" value={`${xrp(arm.earned_drops ?? 0)} XRP`} />
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="label">Joints</span>
          <JointReadout joints={arm.joints} />
        </div>
      </div>
    </article>
  );
}

export function ArmCardSkeleton({ role }: { role: string }) {
  return (
    <article className="card flex flex-col" aria-busy="true">
      <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3">
        <h3 className="text-sm font-semibold tracking-tight capitalize">{role}</h3>
        <Pill tone="neutral" dot={false}>
          Connecting
        </Pill>
      </header>
      <div className="flex flex-col gap-3 px-4 py-4">
        <div className="h-1.5 w-full rounded-full bg-inset" />
        <div className="h-3 w-2/3 animate-pulse rounded bg-inset" />
        <div className="h-3 w-1/2 animate-pulse rounded bg-inset" />
      </div>
    </article>
  );
}
