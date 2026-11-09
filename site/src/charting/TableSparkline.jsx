import React from "react";

import { displayValue } from "./chart-theme.js";
import { tableSparklineGeometry } from "../ui/tables/table-data.js";

export function TableSparkline({ values, label }) {
  const geometry = tableSparklineGeometry(values);
  if (!geometry) return <span className="table-visual-empty">—</span>;
  const { segments, baseline, latest, direction } = geometry;
  return <svg className="table-sparkline" viewBox="0 0 88 28" role="img"
    aria-label={`${label}: latest ${latest ? displayValue(latest.value) : "—"}`} data-direction={direction}>
    <line x1="3" x2="85" y1={baseline} y2={baseline} stroke="var(--border)" strokeWidth="1" />
    {segments.map((segment, index) => segment.length === 1
      ? <circle key={index} cx={segment[0].x} cy={segment[0].y} r="1.75" fill="currentColor" />
      : <polyline key={index} points={segment.map(({ x, y }) => `${x},${y}`).join(" ")}
        fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" />)}
    {latest && <circle cx={latest.x} cy={latest.y} r="2.3" fill="currentColor" />}
  </svg>;
}
