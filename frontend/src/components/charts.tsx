"use client";

import React, { useMemo, useRef, useState } from "react";

import { cn } from "@/lib/cn";

/* Pure-SVG charts: zero dependencies, GPU-friendly, SkillUI tokens only. */

export interface TrendPoint {
  date: string;
  created: number;
  resolved: number;
  breached: number;
}

function niceMax(v: number): number {
  if (v <= 4) return 4;
  const pow = Math.pow(10, Math.floor(Math.log10(v)));
  const n = v / pow;
  const step = n <= 2 ? 2 : n <= 5 ? 5 : 10;
  return step * pow;
}

export function TrendChart({ data }: { data: TrendPoint[] }) {
  const W = 720;
  const H = 240;
  const padL = 32;
  const padR = 16;
  const padT = 16;
  const padB = 28;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  const [hover, setHover] = useState<number | null>(null);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  const { max, pts } = useMemo(() => {
    const m = niceMax(Math.max(1, ...data.map((d) => Math.max(d.created, d.resolved))));
    const n = data.length;
    const xAt = (i: number) => (n === 1 ? padL + innerW / 2 : padL + (i * innerW) / (n - 1));
    const yAt = (v: number) => padT + innerH * (1 - v / m);
    return {
      max: m,
      pts: data.map((d, i) => ({
        x: xAt(i),
        yC: yAt(d.created),
        yR: yAt(d.resolved),
        ...d,
      })),
    };
  }, [data, innerW, innerH]);

  if (data.length === 0) {
    return <p className="p-4 text-meta-faint">No ticket activity in selected range.</p>;
  }

  const line = (key: "yC" | "yR") =>
    pts.map((p, i) => `${i === 0 ? "M" : "L"}${p.x.toFixed(1)},${p[key].toFixed(1)}`).join(" ");
  const areaC = `${line("yC")} L${pts[pts.length - 1].x.toFixed(1)},${padT + innerH} L${pts[0].x.toFixed(1)},${padT + innerH} Z`;

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * W;
    let best = 0;
    let bestDist = Infinity;
    pts.forEach((p, i) => {
      const d = Math.abs(p.x - x);
      if (d < bestDist) {
        bestDist = d;
        best = i;
      }
    });
    setHover(best);
  };

  const hp = hover !== null ? pts[hover] : null;
  const gridLines = [0, 0.25, 0.5, 0.75, 1];
  const labelEvery = Math.ceil(data.length / 7);

  return (
    <div ref={wrapRef} className="relative px-2 py-3">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full h-auto"
        role="img"
        aria-label="Daily created and resolved tickets"
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
      >
        {gridLines.map((g) => {
          const y = padT + innerH * (1 - g);
          return (
            <g key={g}>
              <line
                x1={padL}
                x2={W - padR}
                y1={y}
                y2={y}
                stroke="var(--border-subtle)"
                strokeWidth={1}
              />
              <text
                x={padL - 8}
                y={y + 4}
                textAnchor="end"
                fontSize={11}
                fill="var(--ink-faint)"
                className="tabular-nums"
              >
                {Math.round(max * g)}
              </text>
            </g>
          );
        })}

        <path d={areaC} fill="var(--foreground)" opacity={0.06} className="anim-chart-fade" />
        <path
          d={line("yR")}
          fill="none"
          stroke="var(--muted-foreground)"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
          strokeDasharray="4 4"
          className="anim-chart-fade"
        />
        <path
          d={line("yC")}
          fill="none"
          stroke="var(--foreground)"
          strokeWidth={2.25}
          strokeLinejoin="round"
          strokeLinecap="round"
          pathLength={1}
          className="anim-chart-draw"
        />

        {pts.map((p, i) => (
          <g key={p.date}>
            {p.breached > 0 && (
              <circle cx={p.x} cy={padT + innerH + 10} r={3} fill="var(--destructive)" />
            )}
            {(i % labelEvery === 0 || i === pts.length - 1) && (
              <text
                x={p.x}
                y={H - 6}
                textAnchor="middle"
                fontSize={11}
                fill="var(--ink-faint)"
                className="tabular-nums"
              >
                {p.date.slice(5)}
              </text>
            )}
          </g>
        ))}

        {hp && (
          <g pointerEvents="none">
            <line
              x1={hp.x}
              x2={hp.x}
              y1={padT}
              y2={padT + innerH}
              stroke="var(--border)"
              strokeWidth={1}
            />
            <circle cx={hp.x} cy={hp.yC} r={4} fill="var(--card)" stroke="var(--foreground)" strokeWidth={2} />
            <circle
              cx={hp.x}
              cy={hp.yR}
              r={4}
              fill="var(--card)"
              stroke="var(--muted-foreground)"
              strokeWidth={2}
            />
          </g>
        )}
      </svg>

      {hp && (
        <div
          className="pointer-events-none absolute top-3 rounded-md border border-border bg-card px-2.5 py-1.5 shadow-popover text-[13px] leading-[18px] tabular-nums"
          style={{
            left: `${Math.min(Math.max((hp.x / W) * 100, 12), 82)}%`,
            transform: "translateX(-50%)",
          }}
        >
          <p className="text-meta">{hp.date}</p>
          <p className="text-foreground">
            <span className="inline-block size-2 rounded-[2px] bg-foreground mr-1.5" />
            {hp.created} created
          </p>
          <p className="text-foreground">
            <span className="inline-block size-2 rounded-[2px] bg-muted-foreground mr-1.5" />
            {hp.resolved} resolved
          </p>
          {hp.breached > 0 && (
            <p className="text-destructive">{hp.breached} SLA breached</p>
          )}
        </div>
      )}
    </div>
  );
}

export interface DonutSlice {
  label: string;
  value: number;
  color: string;
}

export function DonutChart({
  slices,
  centerLabel,
}: {
  slices: DonutSlice[];
  centerLabel: string;
}) {
  const total = slices.reduce((s, x) => s + x.value, 0);
  const R = 42;
  const C = 2 * Math.PI * R;
  const [active, setActive] = useState<number | null>(null);

  let offset = 0;
  const arcs = slices
    .filter((s) => s.value > 0)
    .map((s) => {
      const len = total ? (s.value / total) * C : 0;
      const arc = { ...s, len, offset };
      offset += len;
      return arc;
    });

  const activeSlice = active !== null ? arcs[active] : null;

  return (
    <div className="flex items-center gap-5 p-4">
      <div className="relative size-[132px] shrink-0">
        <svg viewBox="0 0 100 100" className="size-full -rotate-90">
          <circle cx={50} cy={50} r={R} fill="none" stroke="var(--muted)" strokeWidth={12} />
          {arcs.map((a, i) => (
            <circle
              key={a.label}
              cx={50}
              cy={50}
              r={R}
              fill="none"
              stroke={a.color}
              strokeWidth={active === i ? 14 : 12}
              strokeDasharray={`${Math.max(a.len - 1.2, 0)} ${C}`}
              strokeDashoffset={-a.offset}
              className="transition-[stroke-width] duration-150 ease-out"
              onMouseEnter={() => setActive(i)}
              onMouseLeave={() => setActive(null)}
            />
          ))}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
          <span className="text-[17px] font-medium text-foreground tabular-nums">
            {activeSlice ? activeSlice.value : total}
          </span>
          <span className="text-[12px] text-muted-foreground max-w-[80px] truncate">
            {activeSlice ? activeSlice.label : centerLabel}
          </span>
        </div>
      </div>

      <ul className="flex-1 min-w-0 space-y-1.5">
        {arcs.map((a, i) => (
          <li
            key={a.label}
            onMouseEnter={() => setActive(i)}
            onMouseLeave={() => setActive(null)}
            className={cn(
              "flex items-center justify-between gap-2 text-[13px] rounded-sm px-1.5 -mx-1.5 h-6 transition-colors duration-75",
              active === i && "bg-muted"
            )}
          >
            <span className="inline-flex items-center gap-2 min-w-0">
              <span
                className="size-2 rounded-[2px] shrink-0"
                style={{ backgroundColor: a.color }}
              />
              <span className="text-foreground truncate">{a.label}</span>
            </span>
            <span className="text-muted-foreground tabular-nums">
              {a.value}
              <span className="text-faint ml-1">
                {total ? Math.round((a.value / total) * 100) : 0}%
              </span>
            </span>
          </li>
        ))}
        {arcs.length === 0 && <li className="text-meta-faint">No data.</li>}
      </ul>
    </div>
  );
}

/* SLA compliance ring gauge */
export function GaugeRing({ pct, label }: { pct: number; label: string }) {
  const R = 42;
  const C = 2 * Math.PI * R;
  const clamped = Math.max(0, Math.min(100, pct));
  const tone =
    clamped >= 90 ? "var(--foreground)" : clamped >= 70 ? "var(--priority-high)" : "var(--destructive)";

  return (
    <div className="flex items-center gap-5 p-4">
      <div className="relative size-[132px] shrink-0">
        <svg viewBox="0 0 100 100" className="size-full -rotate-90">
          <circle cx={50} cy={50} r={R} fill="none" stroke="var(--muted)" strokeWidth={10} />
          <circle
            cx={50}
            cy={50}
            r={R}
            fill="none"
            stroke={tone}
            strokeWidth={10}
            strokeLinecap="round"
            strokeDasharray={`${(clamped / 100) * C} ${C}`}
            className="transition-[stroke-dasharray] duration-700 ease-out"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-[17px] font-medium text-foreground tabular-nums">{clamped}%</span>
          <span className="text-[12px] text-muted-foreground">{label}</span>
        </div>
      </div>
    </div>
  );
}
