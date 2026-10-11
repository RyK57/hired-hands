import type { ArmState, CredentialStatus, JobStatus } from "./types";

export type Tone = "neutral" | "accent" | "ok" | "bad" | "warn";

const ACTIVE_JOB: JobStatus[] = ["paid", "surveying", "bidding", "escrowed", "working", "verifying"];
const ACTIVE_ARM: ArmState[] = ["surveying", "bidding", "working", "verifying"];

export function jobTone(status: JobStatus | string | null | undefined): Tone {
  switch (status) {
    case "done":
      return "ok";
    case "failed":
      return "bad";
    case "teleop":
    case "refunded":
      return "warn";
    default:
      return ACTIVE_JOB.includes(status as JobStatus) ? "accent" : "neutral";
  }
}

export function jobIsLive(status: JobStatus | string | null | undefined): boolean {
  return ACTIVE_JOB.includes(status as JobStatus) || status === "teleop";
}

export function armTone(state: ArmState | string | null | undefined): Tone {
  if (state === "teleop") return "warn";
  return ACTIVE_ARM.includes(state as ArmState) ? "accent" : "neutral";
}

export function armIsLive(state: ArmState | string | null | undefined): boolean {
  return ACTIVE_ARM.includes(state as ArmState) || state === "teleop";
}

export function credentialTone(status: CredentialStatus | string | null | undefined): Tone {
  switch (status) {
    case "valid":
      return "ok";
    case "pending":
    case "expired":
      return "warn";
    case "revoked":
      return "bad";
    default:
      return "neutral";
  }
}

export function loanTone(status: string | null | undefined): Tone {
  if (status === "active") return "accent";
  if (status === "repaid") return "ok";
  return "neutral";
}

export function channelTone(status: string | null | undefined): Tone {
  return status === "open" ? "accent" : "neutral";
}

export function healthTone(score: number | null | undefined): Tone {
  if (score === null || score === undefined) return "neutral";
  if (score >= 0.8) return "ok";
  if (score >= 0.5) return "warn";
  return "bad";
}

export function eventTone(kind: string | null | undefined): Tone {
  switch (kind) {
    case "error":
    case "credential.revoked":
      return "bad";
    case "verify":
    case "settlement":
    case "escrow.release":
    case "credential.issued":
    case "credential.renewed":
    case "bid.won":
      return "ok";
    case "teleop.start":
    case "teleop.stop":
    case "channel.open":
    case "channel.claim":
      return "warn";
    case "pick":
    case "place":
    case "working":
      return "accent";
    default:
      return "neutral";
  }
}
