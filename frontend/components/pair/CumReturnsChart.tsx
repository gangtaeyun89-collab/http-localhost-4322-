"use client";

import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  ResponsiveContainer,
  Tooltip,
  CartesianGrid,
} from "recharts";
import type { SeriesPoint } from "@/lib/mock";

// Two-leg cumulative return chart, cyan for the base leg and magenta for
// the quote leg -- the colour pair the screenshots use throughout.
export function CumReturnsChart({
  data,
  base,
  quote,
}: {
  data: SeriesPoint[];
  base: string;
  quote: string;
}) {
  // Normalise each leg to its first observation so they're comparable; this
  // is what cumulative-return charts always show.
  const start = data[0];
  const normalised = data.map((p) => ({
    t: p.t,
    base: (p.base / start.base - 1) * 100,
    quote: (p.quote / start.quote - 1) * 100,
  }));

  return (
    <div className="h-[260px] w-full">
      <ResponsiveContainer>
        <LineChart data={normalised} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
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
            tickFormatter={(v) => `${v.toFixed(0)}%`}
            width={40}
          />
          <Tooltip
            contentStyle={{
              background: "#000",
              border: "1px solid #2a2a2a",
              fontSize: 11,
            }}
            labelStyle={{ color: "#9ca3af" }}
          />
          <Line
            type="monotone"
            dataKey="base"
            name={base}
            stroke="#00d4ff"
            strokeWidth={1.2}
            dot={false}
          />
          <Line
            type="monotone"
            dataKey="quote"
            name={quote}
            stroke="#ff2ad4"
            strokeWidth={1.2}
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
      <div className="mt-1 flex gap-4 text-2xs text-text-muted">
        <Legend swatch="#00d4ff" label={`${base} (base)`} />
        <Legend swatch="#ff2ad4" label={`${quote} (quote)`} />
      </div>
    </div>
  );
}

function Legend({ swatch, label }: { swatch: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span
        className="h-1.5 w-3 rounded-sm"
        style={{ background: swatch }}
      />
      <span>{label}</span>
    </div>
  );
}
