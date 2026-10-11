import type { Cell } from "./types";

const DROPS_PER_XRP = BigInt(1_000_000);
const ZERO = BigInt(0);

export function xrp(drops: number | string | bigint | null | undefined): string {
  if (drops === null || drops === undefined || drops === "") return "—";
  let value: bigint;
  try {
    value = typeof drops === "bigint" ? drops : BigInt(String(drops).split(".")[0]);
  } catch {
    return "—";
  }
  const negative = value < ZERO;
  if (negative) value = -value;
  const whole = value / DROPS_PER_XRP;
  const fraction = value % DROPS_PER_XRP;
  const wholeText = whole.toLocaleString("en-US");
  if (fraction === ZERO) return `${negative ? "-" : ""}${wholeText}`;
  const fractionText = fraction.toString().padStart(6, "0").replace(/0+$/, "");
  return `${negative ? "-" : ""}${wholeText}.${fractionText}`;
}

export function xrpSigned(drops: number | null | undefined): string {
  if (drops === null || drops === undefined) return "—";
  return drops > 0 ? `+${xrp(drops)}` : xrp(drops);
}

export function shortAddress(address: string | null | undefined, head = 6, tail = 4): string {
  if (!address) return "—";
  if (address.length <= head + tail + 1) return address;
  return `${address.slice(0, head)}…${address.slice(-tail)}`;
}

export function shortHash(hash: string | null | undefined): string {
  return shortAddress(hash, 8, 6);
}

export function shortId(id: string | null | undefined): string {
  if (!id) return "—";
  return id.split("-")[0];
}

export function percent(fraction: number | null | undefined, digits = 0): string {
  if (fraction === null || fraction === undefined || Number.isNaN(fraction)) return "—";
  return `${(fraction * 100).toFixed(digits)}%`;
}

export function degrees(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(digits)}°`;
}

export function volts(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(1)} V`;
}

export function celsius(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${Math.round(value)} °C`;
}

export function metres(value: number | null | undefined, digits = 3): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${value.toFixed(digits)} m`;
}

export function centimetres(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${(value * 100).toFixed(1)} cm`;
}

export function seconds(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  if (value < 60) return `${value.toFixed(value < 10 ? 1 : 0)} s`;
  const m = Math.floor(value / 60);
  const s = Math.round(value % 60);
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

export function basisPoints(bps: number | null | undefined): string {
  if (bps === null || bps === undefined) return "—";
  return `${(bps / 100).toFixed(2).replace(/\.?0+$/, "")}%`;
}

export function relativeTime(iso: string | null | undefined, now?: number): string {
  if (!iso) return "—";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "—";
  const reference = now && now > 0 ? now : Date.now();
  const delta = Math.round((reference - t) / 1000);
  if (delta < 5) return "now";
  if (delta < 60) return `${delta}s ago`;
  const minutes = Math.floor(delta / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return absoluteDate(iso);
}

export function absoluteTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-GB", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function absoluteDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-GB", { year: "numeric", month: "short", day: "2-digit" });
}

export function clockTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

export function duration(startIso: string | null | undefined, endIso: string | null | undefined): string {
  if (!startIso || !endIso) return "—";
  const ms = Date.parse(endIso) - Date.parse(startIso);
  if (Number.isNaN(ms) || ms < 0) return "—";
  return seconds(ms / 1000);
}

export function capitalise(value: string | null | undefined): string {
  if (!value) return "—";
  return value.charAt(0).toUpperCase() + value.slice(1);
}

export function networkLabel(cell: Cell | null | undefined): string {
  if (!cell?.network) return "XRPL";
  return `XRPL ${capitalise(cell.network)}`;
}

export function explorerTx(cell: Cell | null | undefined, hash: string | null | undefined, direct?: string | null) {
  if (direct) return direct;
  if (!hash || !cell?.explorer_url) return null;
  return `${cell.explorer_url.replace(/\/$/, "")}/transactions/${hash}`;
}

export function explorerAccount(cell: Cell | null | undefined, address: string | null | undefined) {
  if (!address || !cell?.explorer_url) return null;
  return `${cell.explorer_url.replace(/\/$/, "")}/accounts/${address}`;
}

export function kindLabel(kind: string | null | undefined): string {
  if (!kind) return "Event";
  return kind
    .split(".")
    .map((part) => capitalise(part))
    .join(" · ");
}
