"use client";

import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
  CartesianGrid,
  ReferenceArea,
} from "recharts";
import type { ScatterPoint } from "@/lib/mock";

// Empirical copula scatter of base vs quote CDF ranks, with notional 5%
// rejection boundaries marked. The bottom-right + top-left tails are the
// 'mispricing' regions where a copula-based stat-arb strategy would enter.
export function CopulaChart({ data }: { data: ScatterPoint[] }) {
  return (
    <div className="h-[260px] w-full">
      <ResponsiveContainer>
        <ScatterChart margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#1a1a1a" />
          <XAxis
            type="number"
            dataKey="x"
            stroke="#4b5563"
            fontSize={9}
            domain={[0, 1]}
            ticks={[0, 0.25, 0.5, 0.75, 1]}
            width={28}
          />
          <YAxis
            type="number"
            dataKey="y"
            stroke="#4b5563"
            fontSize={9}
            domain={[0, 1]}
            ticks={[0, 0.25, 0.5, 0.75, 1]}
            width={28}
          />
          <Tooltip
            contentStyle={{
              background: "#000",
              border: "1px solid #2a2a2a",
              fontSize: 11,
            }}
            cursor={{ stroke: "#2a2a2a" }}
          />
          {/* Tail rejection zones -- where a copula model says the pair is
              mispriced and the strategy takes a position. */}
          <ReferenceArea
            x1={0.7}
            x2={1}
            y1={0}
            y2={0.3}
            fill="#ff2ad4"
            fillOpacity={0.06}
            stroke="#ff2ad4"
            strokeOpacity={0.4}
          />
          <ReferenceArea
            x1={0}
            x2={0.3}
            y1={0.7}
            y2={1}
            fill="#00d4ff"
            fillOpacity={0.06}
            stroke="#00d4ff"
            strokeOpacity={0.4}
          />
          <Scatter data={data} fill="#00d4ff" fillOpacity={0.7} />
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}
