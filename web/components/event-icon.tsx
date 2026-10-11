import {
  Award,
  BadgeCheck,
  BadgeX,
  Banknote,
  Camera,
  Circle,
  CircleStop,
  Coins,
  Crosshair,
  Gamepad2,
  Gavel,
  Hand,
  HandCoins,
  Inbox,
  Landmark,
  Lock,
  LockOpen,
  PackageCheck,
  Radio,
  Receipt,
  RotateCw,
  ShieldCheck,
  TriangleAlert,
  Vault,
  type LucideIcon,
} from "lucide-react";
import { eventTone, type Tone } from "@/lib/status";

const ICONS: Record<string, LucideIcon> = {
  "job.requested": Inbox,
  "job.paid": Coins,
  "job.escrowed": Lock,
  survey: Camera,
  selection: Crosshair,
  bid: Gavel,
  "bid.won": Award,
  pick: Hand,
  place: PackageCheck,
  verify: ShieldCheck,
  "escrow.release": LockOpen,
  settlement: Receipt,
  "loan.payment": HandCoins,
  "loan.opened": Landmark,
  "credential.issued": BadgeCheck,
  "credential.revoked": BadgeX,
  "credential.renewed": RotateCw,
  "channel.open": Radio,
  "channel.claim": Banknote,
  "teleop.start": Gamepad2,
  "teleop.stop": CircleStop,
  "vault.deposit": Vault,
  error: TriangleAlert,
};

const TONE_TEXT: Record<Tone, string> = {
  neutral: "text-ink-muted",
  accent: "text-accent",
  ok: "text-ok",
  bad: "text-bad",
  warn: "text-warn",
};

const TONE_BG: Record<Tone, string> = {
  neutral: "bg-inset border-line",
  accent: "bg-accent-soft border-accent/30",
  ok: "bg-ok-soft border-ok/30",
  bad: "bg-bad-soft border-bad/30",
  warn: "bg-warn-soft border-warn/30",
};

export function EventIcon({ kind, size = 14 }: { kind: string | null | undefined; size?: number }) {
  const Icon = (kind && ICONS[kind]) || Circle;
  const tone = eventTone(kind);
  return (
    <span className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border ${TONE_BG[tone]} ${TONE_TEXT[tone]}`}>
      <Icon size={size} strokeWidth={1.75} />
    </span>
  );
}
