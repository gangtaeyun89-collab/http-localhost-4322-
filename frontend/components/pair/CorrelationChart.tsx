"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
  CartesianGrid,
} from "recharts";
import type { CorrPoint } from "@/lib/mock";

// Rolling correlation between the two legs -- the purple band on the bottom
// right of the screenshots. Useful as a regime-break early-warning indicator.
export function CorrelationChart({ data }: { data: CorrPoint[] }) {
  return (
    <div className="h-[260px] w-full">
      <ResponsiveContainer>
        <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#1a1a1a" />
          <XAxis
            dataKey="t"
            stroke="#4b5563"
            tickFormatter={(v) => v.slice(5)}
            fontSize={9}
            interval="preserveStartEnd"
            minTickGap={40}
          />
          <YAxis stroke="#4b5563" fontSize={9} domain={[0, 1]} ticks={[0, 0.25, 0.5, 0.75, 1]} width={28} />
          <Tooltip
            contentStyle={{
              background: "#000",
              border: "1px solid #2a2a2a",
              fontSize: 11,
            }}
            labelStyle={{ color: "#9ca3af" }}
          />
          <Area
            type="monotone"
            dataKey="corr"
            stroke="#a855f7"
            fill="url(#corrfill)"
            strokeWidth={1}
          />
          <defs>
            <linearGradient id="corrfill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#a855f7" stopOpacity={0.3} />
              <stop offset="100%" stopColor="#a855f7" stopOpacity={0} />
            </linearGradient>
          </defs>
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
