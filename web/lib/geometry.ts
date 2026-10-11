import type { ArmRole } from "./types";

export type Point = [number, number];

export const WORK_AREA = { x: [-0.085, 0.085] as Point, y: [-0.045, 0.045] as Point };

export const MARKERS: Point[] = [
  [-0.11, -0.07],
  [0.11, -0.07],
  [-0.11, 0.07],
  [0.11, 0.07],
];

export const MARKER_SIZE_M = 0.02;

export const ARM_BASES: Record<ArmRole, Point> = {
  left: [-0.25, -0.1],
  head: [0, -0.28],
  right: [0.25, -0.1],
};

export const REACH_M = 0.28;

export const SCENE = { x: [-0.56, 0.56] as Point, y: [-0.6, 0.2] as Point };

export const OBJECT_COLOURS: Record<string, string> = {
  red: "#d6453f",
  orange: "#e2802a",
  yellow: "#d4ab1b",
  green: "#3aa35a",
  cyan: "#2aa9bd",
  blue: "#3b6ed4",
  purple: "#8657d2",
  pink: "#dd62a6",
};

export function objectColour(name: string | null | undefined): string | null {
  if (!name) return null;
  return OBJECT_COLOURS[name.toLowerCase()] ?? null;
}

export function distance(a: Point, b: Point): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1]);
}
