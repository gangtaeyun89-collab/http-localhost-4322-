"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
  CartesianGrid,
  ReferenceLine,
} from "recharts";
import type { ImpulsePoint } from "@/lib/mock";

// ECM impulse-response: how a unit shock to the spread propagates through
// both legs over the next several bars. Vertical reference at t=0 marks the
// shock; both legs should mean-revert back toward zero if the pair really
// is cointegrated.
export function ImpulseChart({ data }: { data: ImpulsePoint[] }) {
  return (
    <div className="h-[220px] w-full">
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="#1a1a1a" />
          <XAxis
            dataKey="step"
            stroke="#4b5563"
            fontSize={9}
            tickFormatter={(v) => (v === 0 ? "t" : v > 0 ? `t+${v}` : `t${v}`)}
          />
          <YAxis stroke="#4b5563" fontSize={9} width={32} />
          <Tooltip
            contentStyle={{
              background: "#000",
              border: "1px solid #2a2a2a",
              fontSize: 11,
            }}
            labelStyle={{ color: "#9ca3af" }}
          />
          <ReferenceLine x={0} stroke="#4b5563" strokeWidth={0.6} />
          <ReferenceLine y={0} stroke="#4b5563" strokeWidth={0.4} />
          <Line type="monotone" dataKey="base" stroke="#00d4ff" strokeWidth={1.4} dot={{ r: 1.5 }} />
          <Line type="monotone" dataKey="quote" stroke="#ff2ad4" strokeWidth={1.4} dot={{ r: 1.5 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
