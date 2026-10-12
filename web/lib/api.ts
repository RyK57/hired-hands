import type { Cell } from "./types";

const LOCAL_API = "http://127.0.0.1:8402";

/** The job API to talk to from this page: the cell on this machine when the page runs locally, else the published one. */
export function apiBase(cell: Cell | null): string | null {
  if (typeof window !== "undefined" && ["localhost", "127.0.0.1"].includes(window.location.hostname)) return LOCAL_API;
  return cell?.api_url?.replace(/\/$/, "") ?? null;
}

export function cameraUrl(cell: Cell | null): string | null {
  const base = apiBase(cell);
  if (!base) return null;
  return `${base}/camera.mjpg`;
}
