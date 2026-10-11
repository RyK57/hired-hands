export type ArmRole = "left" | "head" | "right";

export const ARM_ROLES: ArmRole[] = ["left", "head", "right"];

export type ArmState =
  | "offline"
  | "idle"
  | "surveying"
  | "bidding"
  | "working"
  | "verifying"
  | "teleop";

export type CredentialStatus = "valid" | "pending" | "expired" | "revoked" | "none";

export type JobStatus =
  | "requested"
  | "paid"
  | "surveying"
  | "bidding"
  | "escrowed"
  | "working"
  | "verifying"
  | "done"
  | "failed"
  | "teleop"
  | "refunded";

export type EventKind =
  | "job.requested"
  | "job.paid"
  | "job.escrowed"
  | "survey"
  | "selection"
  | "bid"
  | "bid.won"
  | "pick"
  | "place"
  | "verify"
  | "escrow.release"
  | "settlement"
  | "loan.payment"
  | "loan.opened"
  | "credential.issued"
  | "credential.revoked"
  | "credential.renewed"
  | "channel.open"
  | "channel.claim"
  | "teleop.start"
  | "teleop.stop"
  | "vault.deposit"
  | "error";

export type Json = string | number | boolean | null | Json[] | { [key: string]: Json };

export interface Cell {
  id: string;
  network: string | null;
  network_id: string | null;
  explorer_url: string | null;
  api_url: string | null;
  operator_address: string | null;
  treasury_address: string | null;
  broker_address: string | null;
  vault_id: string | null;
  domain_id: string | null;
  accepts: Json[] | null;
  online: boolean | null;
  updated_at: string | null;
}

export interface Joints {
  shoulder_pan?: number;
  shoulder_lift?: number;
  elbow_flex?: number;
  wrist_flex?: number;
  wrist_roll?: number;
  gripper?: number;
}

export const JOINT_NAMES: (keyof Joints)[] = [
  "shoulder_pan",
  "shoulder_lift",
  "elbow_flex",
  "wrist_flex",
  "wrist_roll",
  "gripper",
];

export interface Health {
  score?: number;
  voltage?: number;
  temperature?: number;
  servos_ok?: number;
  fit?: boolean;
  reasons?: string[];
}

export interface Arm {
  role: ArmRole;
  board: string | null;
  address: string | null;
  did: string | null;
  state: ArmState | null;
  joints: Joints | null;
  health: Health | null;
  health_score: number | null;
  credential: CredentialStatus | null;
  balance_drops: number | null;
  debt_drops: number | null;
  jobs_done: number | null;
  earned_drops: number | null;
  updated_at: string | null;
}

export interface Spot {
  index?: number | null;
  colour?: string | null;
  table?: [number, number] | null;
}

export interface Verdict {
  ok?: boolean;
  reason?: string | null;
  distance_m?: number | null;
}

export interface Job {
  id: string;
  created_at: string | null;
  updated_at: string | null;
  instruction: string | null;
  requester: string | null;
  status: JobStatus | null;
  price_drops: number | null;
  payer_address: string | null;
  payment_tx: string | null;
  escrow_tx: string | null;
  escrow_sequence: number | null;
  condition: string | null;
  worker_role: ArmRole | null;
  target: Spot | null;
  destination: Spot | null;
  before_image_url: string | null;
  after_image_url: string | null;
  verdict: Verdict | null;
  release_tx: string | null;
  settlement_tx: string | null;
  teleop: boolean | null;
  error: string | null;
  finished_at: string | null;
}

export interface Bid {
  id: number;
  created_at: string | null;
  job_id: string | null;
  arm_role: ArmRole | null;
  price_drops: number | null;
  reach_m: number | null;
  health_score: number | null;
  feasible: boolean | null;
  reason: string | null;
  won: boolean | null;
}

export interface Event {
  id: number;
  created_at: string | null;
  job_id: string | null;
  arm_role: ArmRole | null;
  kind: EventKind | string | null;
  message: string | null;
  tx_hash: string | null;
  explorer_url: string | null;
  amount_drops: number | null;
  meta: Record<string, Json> | null;
}

export interface Channel {
  id: string;
  created_at: string | null;
  job_id: string | null;
  operator_address: string | null;
  amount_drops: number | null;
  claimed_drops: number | null;
  seconds_driven: number | null;
  status: "open" | "closed" | null;
  open_tx: string | null;
  close_tx: string | null;
  closed_at: string | null;
}

export interface Loan {
  id: string;
  created_at: string | null;
  arm_role: ArmRole | null;
  principal_drops: number | null;
  outstanding_drops: number | null;
  interest_bps: number | null;
  status: "active" | "repaid" | null;
  open_tx: string | null;
  last_payment_tx: string | null;
  closed_at: string | null;
}

export interface Depositor {
  address: string;
  created_at: string | null;
  name: string | null;
  domain: string | null;
  verified: boolean | null;
  credential_tx: string | null;
  deposited_drops: number | null;
  shares: string | null;
  deposit_tx: string | null;
}

export interface Tables {
  cell: Cell;
  arms: Arm;
  jobs: Job;
  bids: Bid;
  events: Event;
  channels: Channel;
  loans: Loan;
  depositors: Depositor;
}

export type TableName = keyof Tables;

export const PRIMARY_KEY: { [K in TableName]: keyof Tables[K] & string } = {
  cell: "id",
  arms: "role",
  jobs: "id",
  bids: "id",
  events: "id",
  channels: "id",
  loans: "id",
  depositors: "address",
};
