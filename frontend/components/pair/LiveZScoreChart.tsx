"use client";

import { useEffect, useRef, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { fetchPairQuoteBrowser, type PairQuote } from "@/lib/api";
import type { ZScorePoint } from "@/lib/mock";
import { cn, fmtNum } from "@/lib/utils";

// Live-aware spread/z-score chart. Inherits the historical series from
// SSR -- recharts redraws are expensive, so we keep that bulk render --
// then appends a single "now" point on each poll. The new point gets a
// pulsing dot so the user can see the chart is alive without comparing
// pixel positions across ticks.

const MAX_LIVE_POINTS = 60; // ~5 minutes at 5s cadence

type LivePoint = {
  t: string;
  spread: number;
  zscore: number;
  isLive: true;
};

type Combined = (ZScorePoint & { isLive?: false }) | LivePoint;

export function LiveZScoreChart({
  data,
  pairId,
  interval = 5000,
}: {
  data: ZScorePoint[];
  pairId: string;
  interval?: number;
}) {
  const [live, setLive] = useState<LivePoint[]>([]);
  const [latest, setLatest] = useState<PairQuote | null>(null);
  const [pulse, setPulse] = useState(false);
  const lastTimestamp = useRef<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const q = await fetchPairQuoteBrowser(pairId);
        if (cancelled) return;
        setLatest(q);
        setPulse(true);
        setTimeout(() => !cancelled && setPulse(false), 400);

        // Only push a new live point when the backend reports a new bar
        // timestamp -- avoids stacking dozens of duplicate points at the
        // same x value while a daily bar hasn't rolled over yet.
        const ts = q.lastBar.t;
        if (ts !== lastTimestamp.current) {
          lastTimestamp.current = ts;
          setLive((prev) => {
            const next: LivePoint[] = [
              ...prev,
              {
                t: ts,
                spread: q.lastSpread,
                zscore: q.lastZScore,
                isLive: true,
              },
            ];
            return next.slice(-MAX_LIVE_POINTS);
          });
        }
      } catch {
        // Polling errors are surfaced via the header LivePulse component,
        // no need to double-report here.
      }
    }

    poll();
    const id = setInterval(poll, interval);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [pairId, interval]);

  const combined: Combined[] = [...data, ...live];
  const liveZ = latest?.lastZScore ?? null;

  return (
    <div className="relative">
      <div className="h-[260px] w-full">
        <ResponsiveContainer>
          <ComposedChart
            data={combined}
            margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
          >
            <CartesianGrid stroke="#1a1a1a" />
            <XAxis
              dataKey="t"
              stroke="#4b5563"
              tickFormatter={(v) => (v.length > 10 ? v.slice(5, 10) : v.slice(5))}
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
            {liveZ != null && (
              <ReferenceLine
                y={liveZ}
                stroke="#00ff88"
                strokeDasharray="2 4"
                strokeWidth={0.7}
              />
            )}
            <Area
              type="monotone"
              dataKey="zscore"
              name="Z-Score"
              stroke="#00d4ff"
              fill="url(#zfill-live)"
              strokeWidth={1}
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="spread"
              name="Spread"
              stroke="#a855f7"
              strokeWidth={0.8}
              dot={false}
              isAnimationActive={false}
            />
            <defs>
              <linearGradient id="zfill-live" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#00d4ff" stopOpacity={0.25} />
                <stop offset="100%" stopColor="#00d4ff" stopOpacity={0} />
              </linearGradient>
            </defs>
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* Live overlay: pulsing dot + current z label sits on top of the
          chart's right edge so the eye knows where to look. */}
      {liveZ != null && (
        <div className="pointer-events-none absolute right-3 top-3 flex items-center gap-1.5 rounded bg-black/60 px-2 py-1 text-2xs uppercase tracking-widest backdrop-blur">
          <span className="relative inline-flex h-2 w-2 items-center justify-center">
            <span className="h-2 w-2 rounded-full bg-accent-green shadow-[0_0_8px_currentColor] text-accent-green" />
            {pulse && (
              <span className="absolute inline-flex h-2 w-2 animate-ping rounded-full bg-accent-green opacity-75" />
            )}
          </span>
          <span className="text-text-muted">live</span>
          <span
            className={cn(
              "num",
              Math.abs(liveZ) >= 2
                ? "text-accent-red"
                : Math.abs(liveZ) >= 1
                ? "text-accent-yellow"
                : "text-text-primary"
            )}
          >
            z={fmtNum(liveZ, 2, true)}
          </span>
        </div>
      )}
    </div>
  );
}
