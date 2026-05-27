"use client";

import {
  ComposedChart,
  Area,
  Line,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from "recharts";
import type { ZScorePoint } from "@/lib/mock";

// Spread (or rolling z-score) with the +/- 2 sigma entry bands and the zero
// mean reference. Cyan for the spread itself; bands drawn as dashed
// reference lines so they don't compete visually with the series.
export function ZScoreChart({ data }: { data: ZScorePoint[] }) {
  return (
    <div className="h-[260px] w-full">
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#1a1a1a" />
          <XAxis
            dataKey="t"
            stroke="#4b5563"
            tickFormatter={(v) => v.slice(5)}
            fontSize={9}
            interval="preserveStartEnd"
            minTickGap={40}
          />
          <YAxis
            stroke="#4b5563"
            fontSize={9}
            domain={[-3, 3]}
            ticks={[-2, 0, 2]}
            width={28}
          />
          <Tooltip
            contentStyle={{
              background: "#000",
              border: "1px solid #2a2a2a",
              fontSize: 11,
            }}
            labelStyle={{ color: "#9ca3af" }}
          />
          <ReferenceLine y={2} stroke="#ff3355" strokeDasharray="3 3" strokeWidth={0.8} />
          <ReferenceLine y={-2} stroke="#ff3355" strokeDasharray="3 3" strokeWidth={0.8} />
          <ReferenceLine y={0} stroke="#4b5563" strokeWidth={0.6} />
          <Area
            type="monotone"
            dataKey="zscore"
            name="Z-Score"
            stroke="#00d4ff"
            fill="url(#zfill)"
            strokeWidth={1}
          />
          <Line type="monotone" dataKey="spread" name="Spread" stroke="#a855f7" strokeWidth={0.8} dot={false} />
          <defs>
            <linearGradient id="zfill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#00d4ff" stopOpacity={0.25} />
              <stop offset="100%" stopColor="#00d4ff" stopOpacity={0} />
            </linearGradient>
          </defs>
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
