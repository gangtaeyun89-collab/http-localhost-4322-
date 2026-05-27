"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Download, FileJson } from "lucide-react";
import {
  deriveTimeSeries,
  navHistoryToCsv,
  navHistoryToJson,
  summariseAnalytics,
  type DerivedPoint,
  type NavSnapshot,
} from "@/lib/journal";
import { cn, fmtNum, fmtPct } from "@/lib/utils";

// NAV time-series analytics + exports.
//
// Three small charts sit side by side: underwater (current drawdown
// over time), daily returns (positive/negative bar histogram on the
// time axis), and rolling 30-day annualised Sharpe. Plus a stats strip
// (best day, worst day, hit rate, ...) so the user gets the headline
// numbers without having to inspect the charts.
//
// CSV and JSON export buttons live in this panel because the same
// derived series feeds both.

export function NavAnalytics({ history }: { history: NavSnapshot[] }) {
  const series = deriveTimeSeries(history);
  const summary = summariseAnalytics(series);

  return (
    <div className="flex flex-col border border-border-subtle bg-bg-panel">
      <div className="flex items-center justify-between border-b border-border-subtle px-3 py-1.5">
        <div className="text-2xs uppercase tracking-widest text-text-secondary">
          NAV 시계열 분석 / Time-series analytics
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => downloadText(navHistoryToCsv(history), "csv")}
            disabled={history.length === 0}
            className={cn(
              "flex items-center gap-1 rounded border px-2 py-0.5 text-2xs uppercase tracking-widest",
              history.length === 0
                ? "cursor-not-allowed border-border-subtle text-text-faint"
                : "border-border-subtle text-text-secondary hover:bg-bg-elevated"
            )}
          >
            <Download className="h-3 w-3" />
            NAV CSV
          </button>
          <button
            onClick={() => downloadText(navHistoryToJson(history), "json")}
            disabled={history.length === 0}
            className={cn(
              "flex items-center gap-1 rounded border px-2 py-0.5 text-2xs uppercase tracking-widest",
              history.length === 0
                ? "cursor-not-allowed border-border-subtle text-text-faint"
                : "border-border-subtle text-text-secondary hover:bg-bg-elevated"
            )}
          >
            <FileJson className="h-3 w-3" />
            JSON
          </button>
        </div>
      </div>

      <StatsStrip
        summary={summary}
        history={history}
        series={series}
      />

      {history.length < 2 ? (
        <div className="flex h-[200px] items-center justify-center text-2xs uppercase tracking-widest text-text-faint">
          NAV 시계열은 며칠 누적되어야 분석이 의미가 있습니다.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-px bg-border-subtle p-px lg:grid-cols-3">
          <Mini title="underwater (drawdown 시계열)" hint="< 0 = 손실">
            <UnderwaterChart data={series} />
          </Mini>
          <Mini title="daily returns" hint="bar = 일별 P&L">
            <DailyReturnsChart data={series} />
          </Mini>
          <Mini title="rolling Sharpe (30일)" hint="annualised">
            <RollingSharpeChart data={series} />
          </Mini>
        </div>
      )}
    </div>
  );
}

function StatsStrip({
  summary,
  history,
  series,
}: {
  summary: ReturnType<typeof summariseAnalytics>;
  history: NavSnapshot[];
  series: DerivedPoint[];
}) {
  const currentDrawdown =
    series.length > 0 ? series[series.length - 1].drawdown : 0;
  return (
    <div className="grid grid-cols-2 gap-px border-b border-border-subtle bg-border-subtle md:grid-cols-7">
      <StatCell label="snapshots">
        <span className="num text-sm">{history.length}</span>
      </StatCell>
      <StatCell label="mean daily">
        <span className="num text-sm">
          {fmtPct(summary.meanDailyReturn, 3, true)}
        </span>
      </StatCell>
      <StatCell label="hit rate">
        <span className="num text-sm">
          {fmtPct(summary.hitRate, 1, false)}
        </span>
      </StatCell>
      <StatCell label="best day">
        <span
          className={cn(
            "num text-sm",
            summary.bestDay && summary.bestDay.ret >= 0
              ? "text-accent-green"
              : "text-text-primary"
          )}
        >
          {summary.bestDay
            ? fmtPct(summary.bestDay.ret, 2, true)
            : "—"}
        </span>
      </StatCell>
      <StatCell label="worst day">
        <span
          className={cn(
            "num text-sm",
            summary.worstDay && summary.worstDay.ret < 0
              ? "text-accent-red"
              : "text-text-primary"
          )}
        >
          {summary.worstDay
            ? fmtPct(summary.worstDay.ret, 2, true)
            : "—"}
        </span>
      </StatCell>
      <StatCell label="current DD streak">
        <span
          className={cn(
            "num text-sm",
            currentDrawdown < 0 ? "text-accent-red" : "text-text-primary"
          )}
        >
          {summary.currentDrawdownDays}d
        </span>
      </StatCell>
      <StatCell label="longest DD">
        <span className="num text-sm">
          {summary.longestDrawdownDays}d
        </span>
      </StatCell>
    </div>
  );
}

function StatCell({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5 bg-bg-panel px-3 py-2">
      <div className="text-2xs uppercase tracking-wide text-text-muted">
        {label}
      </div>
      <div className="leading-tight">{children}</div>
    </div>
  );
}

function Mini({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col bg-bg-panel">
      <div className="flex items-center justify-between border-b border-border-subtle px-2 py-1">
        <span className="text-2xs uppercase tracking-widest text-text-muted">
          {title}
        </span>
        {hint && (
          <span className="text-2xs uppercase tracking-widest text-text-faint">
            {hint}
          </span>
        )}
      </div>
      <div className="p-1">{children}</div>
    </div>
  );
}

function UnderwaterChart({ data }: { data: DerivedPoint[] }) {
  const chart = data.map((d) => ({ t: d.date.slice(5), dd: d.drawdown * 100 }));
  return (
    <div className="h-[160px] w-full">
      <ResponsiveContainer>
        <AreaChart
          data={chart}
          margin={{ top: 4, right: 4, left: 0, bottom: 0 }}
        >
          <CartesianGrid stroke="#1a1a1a" />
          <XAxis
            dataKey="t"
            stroke="#4b5563"
            fontSize={9}
            interval="preserveStartEnd"
            minTickGap={24}
          />
          <YAxis
            stroke="#4b5563"
            fontSize={9}
            width={32}
            tickFormatter={(v) => `${v.toFixed(0)}%`}
          />
          <Tooltip
            contentStyle={{
              background: "#000",
              border: "1px solid #2a2a2a",
              fontSize: 11,
            }}
            labelStyle={{ color: "#9ca3af" }}
            formatter={(v: number) => [`${v.toFixed(2)}%`, "drawdown"]}
          />
          <ReferenceLine y={0} stroke="#4b5563" strokeWidth={0.6} />
          <Area
            type="monotone"
            dataKey="dd"
            stroke="#ff3355"
            fill="url(#uwfill)"
            strokeWidth={1}
            isAnimationActive={false}
          />
          <defs>
            <linearGradient id="uwfill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#ff3355" stopOpacity={0.4} />
              <stop offset="100%" stopColor="#ff3355" stopOpacity={0} />
            </linearGradient>
          </defs>
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function DailyReturnsChart({ data }: { data: DerivedPoint[] }) {
  const chart = data
    .slice(1) // skip the seeded zero-return first day
    .map((d) => ({ t: d.date.slice(5), r: d.dailyReturn * 100 }));
  return (
    <div className="h-[160px] w-full">
      <ResponsiveContainer>
        <BarChart
          data={chart}
          margin={{ top: 4, right: 4, left: 0, bottom: 0 }}
        >
          <CartesianGrid stroke="#1a1a1a" />
          <XAxis
            dataKey="t"
            stroke="#4b5563"
            fontSize={9}
            interval="preserveStartEnd"
            minTickGap={24}
          />
          <YAxis
            stroke="#4b5563"
            fontSize={9}
            width={32}
            tickFormatter={(v) => `${v.toFixed(1)}%`}
          />
          <Tooltip
            contentStyle={{
              background: "#000",
              border: "1px solid #2a2a2a",
              fontSize: 11,
            }}
            labelStyle={{ color: "#9ca3af" }}
            formatter={(v: number) => [`${v.toFixed(3)}%`, "daily return"]}
          />
          <ReferenceLine y={0} stroke="#4b5563" strokeWidth={0.6} />
          <Bar dataKey="r" isAnimationActive={false}>
            {chart.map((d, i) => (
              <Cell key={i} fill={d.r >= 0 ? "#00ff88" : "#ff3355"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function RollingSharpeChart({ data }: { data: DerivedPoint[] }) {
  const chart = data.map((d) => ({
    t: d.date.slice(5),
    s: d.rollingSharpe,
  }));
  return (
    <div className="h-[160px] w-full">
      <ResponsiveContainer>
        <LineChart
          data={chart}
          margin={{ top: 4, right: 4, left: 0, bottom: 0 }}
        >
          <CartesianGrid stroke="#1a1a1a" />
          <XAxis
            dataKey="t"
            stroke="#4b5563"
            fontSize={9}
            interval="preserveStartEnd"
            minTickGap={24}
          />
          <YAxis stroke="#4b5563" fontSize={9} width={32} />
          <Tooltip
            contentStyle={{
              background: "#000",
              border: "1px solid #2a2a2a",
              fontSize: 11,
            }}
            labelStyle={{ color: "#9ca3af" }}
            formatter={(v: number) => [v.toFixed(2), "Sharpe (30d)"]}
          />
          <ReferenceLine y={0} stroke="#4b5563" strokeWidth={0.6} />
          <ReferenceLine
            y={1}
            stroke="#00d4ff"
            strokeDasharray="3 3"
            strokeWidth={0.6}
          />
          <Line
            type="monotone"
            dataKey="s"
            stroke="#a855f7"
            strokeWidth={1.2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function downloadText(text: string, kind: "csv" | "json") {
  const blob = new Blob([text], {
    type: kind === "csv" ? "text/csv" : "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `statarb-nav-${new Date()
    .toISOString()
    .slice(0, 10)}.${kind}`;
  a.click();
  URL.revokeObjectURL(url);
}

// Tell the bundler to leave fmtNum imported (used elsewhere when this
// module re-renders the parent stats strip).
export const _fmtNumUsed = fmtNum;
