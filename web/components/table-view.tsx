"use client";

import Link from "next/link";
import { Pill } from "./pill";
import { ARM_BASES, MARKERS, MARKER_SIZE_M, REACH_M, SCENE, WORK_AREA, objectColour, type Point } from "@/lib/geometry";
import { armIsLive, jobIsLive, jobTone } from "@/lib/status";
import { ARM_ROLES, type Arm, type Job, type Spot } from "@/lib/types";

const S = 1000;
const px = (x: number) => x * S;
const py = (y: number) => -y * S;

const VIEW = {
  x: px(SCENE.x[0]),
  y: py(SCENE.y[1]),
  w: px(SCENE.x[1]) - px(SCENE.x[0]),
  h: py(SCENE.y[0]) - py(SCENE.y[1]),
};

function spotPoint(spot: Spot | null | undefined): Point | null {
  const t = spot?.table;
  if (!t || t.length < 2) return null;
  const [x, y] = t;
  if (typeof x !== "number" || typeof y !== "number") return null;
  return [x, y];
}

function gridLines() {
  const lines: React.ReactNode[] = [];
  for (let x = Math.ceil(SCENE.x[0] * 10) / 10; x <= SCENE.x[1] + 1e-9; x = Math.round((x + 0.1) * 10) / 10) {
    lines.push(<line key={`v${x}`} x1={px(x)} y1={VIEW.y} x2={px(x)} y2={VIEW.y + VIEW.h} stroke="var(--grid)" strokeWidth={1} />);
  }
  for (let y = Math.ceil(SCENE.y[0] * 10) / 10; y <= SCENE.y[1] + 1e-9; y = Math.round((y + 0.1) * 10) / 10) {
    lines.push(<line key={`h${y}`} x1={VIEW.x} y1={py(y)} x2={VIEW.x + VIEW.w} y2={py(y)} stroke="var(--grid)" strokeWidth={1} />);
  }
  return lines;
}

export function TableView({ arms, job }: { arms: Arm[]; job: Job | null }) {
  const stateOf = (role: string) => arms.find((a) => a.role === role)?.state ?? null;
  const target = spotPoint(job?.target);
  const destination = spotPoint(job?.destination);
  const targetColour = objectColour(job?.target?.colour) ?? "var(--ink)";
  const destinationColour = objectColour(job?.destination?.colour) ?? "var(--ink-muted)";
  const workerRole = job && jobIsLive(job.status) ? job.worker_role : null;
  const markerHalf = px(MARKER_SIZE_M) / 2;

  return (
    <div className="flex flex-col">
      <svg
        viewBox={`${VIEW.x} ${VIEW.y} ${VIEW.w} ${VIEW.h}`}
        className="block w-full"
        style={{ aspectRatio: `${VIEW.w} / ${VIEW.h}` }}
        role="img"
        aria-label="Top-down view of the table and the three arms"
      >
        <defs>
          <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--ink-muted)" />
          </marker>
        </defs>

        {gridLines()}

        {ARM_ROLES.map((role) => {
          const [bx, by] = ARM_BASES[role];
          const live = armIsLive(stateOf(role)) || workerRole === role;
          return (
            <g key={role}>
              <circle
                cx={px(bx)}
                cy={py(by)}
                r={px(REACH_M)}
                fill={live ? "var(--accent-soft)" : "none"}
                fillOpacity={live ? 0.5 : 0}
                stroke={live ? "var(--accent)" : "var(--line-strong)"}
                strokeOpacity={live ? 0.5 : 0.7}
                strokeWidth={1.5}
                strokeDasharray="6 8"
              />
            </g>
          );
        })}

        <rect
          x={px(WORK_AREA.x[0])}
          y={py(WORK_AREA.y[1])}
          width={px(WORK_AREA.x[1]) - px(WORK_AREA.x[0])}
          height={py(WORK_AREA.y[0]) - py(WORK_AREA.y[1])}
          fill="var(--inset)"
          stroke="var(--line-strong)"
          strokeWidth={1.5}
        />
        <line x1={-12} y1={0} x2={12} y2={0} stroke="var(--line-strong)" strokeWidth={1.5} />
        <line x1={0} y1={-12} x2={0} y2={12} stroke="var(--line-strong)" strokeWidth={1.5} />

        {MARKERS.map(([mx, my], i) => (
          <g key={i}>
            <rect
              x={px(mx) - markerHalf}
              y={py(my) - markerHalf}
              width={markerHalf * 2}
              height={markerHalf * 2}
              fill="var(--ink)"
              rx={1}
            />
            <rect x={px(mx) - markerHalf / 2.4} y={py(my) - markerHalf / 2.4} width={markerHalf / 1.2} height={markerHalf / 1.2} fill="var(--surface)" />
          </g>
        ))}

        {target && destination && (
          <line
            x1={px(target[0])}
            y1={py(target[1])}
            x2={px(destination[0])}
            y2={py(destination[1])}
            stroke="var(--ink-muted)"
            strokeWidth={2}
            strokeDasharray="5 5"
            markerEnd="url(#arrow)"
          />
        )}

        {destination && (
          <g>
            <circle
              cx={px(destination[0])}
              cy={py(destination[1])}
              r={16}
              fill="none"
              stroke={destinationColour}
              strokeWidth={2.5}
              strokeDasharray="4 4"
            />
            {typeof job?.destination?.index === "number" && (
              <text
                x={px(destination[0])}
                y={py(destination[1])}
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={15}
                fontFamily="var(--font-geist-mono)"
                fill={destinationColour}
              >
                {job.destination.index}
              </text>
            )}
          </g>
        )}

        {target && (
          <g>
            <circle cx={px(target[0])} cy={py(target[1])} r={14} fill={targetColour} stroke="var(--surface)" strokeWidth={2.5} />
            {typeof job?.target?.index === "number" && (
              <text
                x={px(target[0])}
                y={py(target[1])}
                textAnchor="middle"
                dominantBaseline="central"
                fontSize={15}
                fontWeight={600}
                fontFamily="var(--font-geist-mono)"
                fill="#ffffff"
              >
                {job.target.index}
              </text>
            )}
          </g>
        )}

        {ARM_ROLES.map((role) => {
          const [bx, by] = ARM_BASES[role];
          const live = armIsLive(stateOf(role)) || workerRole === role;
          return (
            <g key={role}>
              <circle
                cx={px(bx)}
                cy={py(by)}
                r={22}
                fill="var(--surface)"
                stroke={live ? "var(--accent)" : "var(--line-strong)"}
                strokeWidth={live ? 3 : 2}
              />
              <circle cx={px(bx)} cy={py(by)} r={5} fill={live ? "var(--accent)" : "var(--ink-faint)"} />
              <text
                x={px(bx)}
                y={py(by) + 44}
                textAnchor="middle"
                fontSize={20}
                letterSpacing={1.5}
                fontFamily="var(--font-geist-sans)"
                fill={live ? "var(--accent)" : "var(--ink-muted)"}
                style={{ textTransform: "uppercase" }}
              >
                {role}
              </text>
            </g>
          );
        })}

        <text x={VIEW.x + 16} y={VIEW.y + 26} fontSize={18} fontFamily="var(--font-geist-mono)" fill="var(--ink-faint)">
          table frame · metres
        </text>
        <text x={VIEW.x + VIEW.w - 16} y={VIEW.y + 26} textAnchor="end" fontSize={18} fontFamily="var(--font-geist-mono)" fill="var(--ink-faint)">
          reach {REACH_M.toFixed(2)} m
        </text>
      </svg>

      <div className="flex min-h-[52px] items-center gap-3 border-t border-line px-4 py-2.5 text-sm">
        {job ? (
          <>
            <Pill tone={jobTone(job.status)} live={jobIsLive(job.status)}>
              {job.status ?? "requested"}
            </Pill>
            <Link href={`/jobs/${job.id}`} className="min-w-0 flex-1 truncate text-ink hover:text-accent">
              {job.instruction ?? "Untitled job"}
            </Link>
            <span className="num hidden shrink-0 text-xs text-ink-faint sm:inline">
              {target ? `${target[0].toFixed(3)}, ${target[1].toFixed(3)}` : ""}
              {target && destination ? " → " : ""}
              {destination ? `${destination[0].toFixed(3)}, ${destination[1].toFixed(3)}` : ""}
            </span>
          </>
        ) : (
          <span className="text-ink-faint">Nothing on the table. The next job will be drawn here.</span>
        )}
      </div>
    </div>
  );
}
