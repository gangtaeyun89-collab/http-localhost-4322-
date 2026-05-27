"use client";

import { useEffect } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { BacktestResult } from "@/lib/api";
import { recordBacktestSharpe } from "@/lib/journal";
import { cn, fmtNum, fmtPct } from "@/lib/utils";
import { Panel } from "@/components/pair/Panel";

// Walk-forward report card: KPI strip, OOS equity curve, per-window
// train-vs-test Sharpe bars, and a tidy windows table. The colour cues
// answer the only question that matters: "did the OOS Sharpe survive,
// and did the train Sharpe predict it?"

export function BacktestResults({ result }: { result: BacktestResult }) {
  const { stats, windows, equity } = result;
  const overfitVerdict = verdictForGap(result.overfitGap);

  // Record the OOS Sharpe so the journal's "live vs backtest" card has
  // something honest to compare against. Recorded per result (the same
  // backtest re-run will overwrite the head of the list).
  useEffect(() => {
    recordBacktestSharpe({
      sharpe: stats.sharpe,
      recordedAt: Date.now(),
      base: result.request.base,
      quote: result.request.quote,
    });
  }, [stats.sharpe, result.request.base, result.request.quote]);

  return (
    <div className="flex flex-col">
      <KPIStrip result={result} />

      <div className="grid grid-cols-1 gap-px bg-border-subtle p-px lg:grid-cols-[2fr_1fr]">
        <Panel
          title={`OOS equity · ${result.request.base} / ${result.request.quote}`}
          hint={`${result.barsPerYear} bars/yr · ${result.source}`}
        >
          <EquityCurve data={equity} />
        </Panel>
        <Panel
          title="train vs OOS Sharpe (per window)"
          hint={overfitVerdict.label}
        >
          <TrainTestBars windows={windows} />
        </Panel>
      </div>

      <Panel title="windows" hint={`${windows.length} window(s)`}>
        <WindowsTable windows={windows} />
      </Panel>
    </div>
  );
}

function KPIStrip({ result }: { result: BacktestResult }) {
  const { stats, meanTrainSharpe, meanTestSharpe, overfitGap } = result;
  const tradeable = stats.sharpe >= 0.8;
  return (
    <div className="grid grid-cols-kpi gap-px border-y border-border-subtle bg-border-subtle">
      <Cell label="OOS Sharpe" accent={tradeable ? "green" : "yellow"}>
        <span className="num text-base">{fmtNum(stats.sharpe, 2, true)}</span>
      </Cell>
      <Cell label="OOS CAGR" accent={stats.cagr >= 0 ? "green" : "red"}>
        <span className="num text-base">{fmtPct(stats.cagr, 2, true)}</span>
      </Cell>
      <Cell label="Max DD" accent="red">
        <span className="num text-base">
          {fmtPct(stats.maxDrawdown, 2, true)}
        </span>
      </Cell>
      <Cell label="Annual vol">
        <span className="num text-base">
          {fmtPct(stats.annualVolatility, 2, false)}
        </span>
      </Cell>
      <Cell label="Win rate">
        <span className="num text-base">
          {fmtPct(stats.winRate, 1, false)}
        </span>
      </Cell>
      <Cell label="Trades">
        <span className="num text-base">{stats.nTrades}</span>
      </Cell>
      <Cell label="Mean train Sharpe">
        <span className="num text-base">
          {fmtNum(meanTrainSharpe, 2, true)}
        </span>
      </Cell>
      <Cell label="Mean test Sharpe">
        <span className="num text-base">
          {fmtNum(meanTestSharpe, 2, true)}
        </span>
      </Cell>
      <Cell label="Overfit gap" accent={overfitVerdictColor(overfitGap)}>
        <span className="num text-base">{fmtNum(overfitGap, 2, true)}</span>
      </Cell>
      <Cell label="Half-life">
        <span className="num text-base">{fmtNum(result.halfLife, 1)}</span>
      </Cell>
      <Cell label="z lookback">
        <span className="num text-base">{result.lookbackUsed}</span>
      </Cell>
      <Cell label="OOS bars">
        <span className="num text-base">{stats.bars}</span>
      </Cell>
    </div>
  );
}

function Cell({
  label,
  children,
  accent,
}: {
  label: string;
  children: React.ReactNode;
  accent?: "green" | "red" | "yellow";
}) {
  const colour =
    accent === "green"
      ? "text-accent-green"
      : accent === "red"
      ? "text-accent-red"
      : accent === "yellow"
      ? "text-accent-yellow"
      : "text-text-primary";
  return (
    <div className="flex flex-col gap-0.5 bg-bg-panel px-3 py-2">
      <div className="text-2xs uppercase tracking-wide text-text-muted">
        {label}
      </div>
      <div className={cn("leading-tight", colour)}>{children}</div>
    </div>
  );
}

function EquityCurve({ data }: { data: BacktestResult["equity"] }) {
  // Normalise around the initial equity so the y-axis tells a returns
  // story rather than a $-units story.
  const start = data[0]?.equity ?? 1;
  const series = data.map((p) => ({
    t: p.t.slice(0, 10),
    pnl: (p.equity / start - 1) * 100,
  }));
  return (
    <div className="h-[260px] w-full">
      <ResponsiveContainer>
        <LineChart
          data={series}
          margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
        >
          <CartesianGrid stroke="#1a1a1a" />
          <XAxis
            dataKey="t"
            stroke="#4b5563"
            fontSize={9}
            interval="preserveStartEnd"
            minTickGap={40}
            tickFormatter={(v) => v.slice(5)}
          />
          <YAxis
            stroke="#4b5563"
            fontSize={9}
            width={40}
            tickFormatter={(v) => `${v.toFixed(0)}%`}
          />
          <Tooltip
            contentStyle={{
              background: "#000",
              border: "1px solid #2a2a2a",
              fontSize: 11,
            }}
            labelStyle={{ color: "#9ca3af" }}
            formatter={(v: number) => [`${v.toFixed(2)}%`, "OOS P&L"]}
          />
          <ReferenceLine y={0} stroke="#4b5563" strokeWidth={0.6} />
          <Line
            type="monotone"
            dataKey="pnl"
            stroke="#00ff88"
            strokeWidth={1.2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function TrainTestBars({
  windows,
}: {
  windows: BacktestResult["windows"];
}) {
  const data = windows.map((w, i) => ({
    label: `w${i + 1}`,
    train: w.train_sharpe,
    test: w.test_sharpe,
  }));
  return (
    <div className="h-[260px] w-full">
      <ResponsiveContainer>
        <BarChart
          data={data}
          margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
        >
          <CartesianGrid stroke="#1a1a1a" />
          <XAxis dataKey="label" stroke="#4b5563" fontSize={9} />
          <YAxis stroke="#4b5563" fontSize={9} width={32} />
          <Tooltip
            contentStyle={{
              background: "#000",
              border: "1px solid #2a2a2a",
              fontSize: 11,
            }}
            labelStyle={{ color: "#9ca3af" }}
          />
          <ReferenceLine y={0} stroke="#4b5563" strokeWidth={0.6} />
          <Bar dataKey="train" name="train" fill="#a855f7" />
          <Bar dataKey="test" name="test (OOS)" fill="#00d4ff" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function WindowsTable({
  windows,
}: {
  windows: BacktestResult["windows"];
}) {
  return (
    <table className="w-full text-xs">
      <thead className="text-text-muted">
        <tr>
          <th className="px-3 py-1.5 text-left font-normal uppercase tracking-widest text-2xs">
            window
          </th>
          <th className="px-3 py-1.5 text-left font-normal uppercase tracking-widest text-2xs">
            train
          </th>
          <th className="px-3 py-1.5 text-left font-normal uppercase tracking-widest text-2xs">
            test (OOS)
          </th>
          <th className="px-3 py-1.5 text-right font-normal uppercase tracking-widest text-2xs">
            train Sharpe
          </th>
          <th className="px-3 py-1.5 text-right font-normal uppercase tracking-widest text-2xs">
            test Sharpe
          </th>
          <th className="px-3 py-1.5 text-right font-normal uppercase tracking-widest text-2xs">
            Δ (overfit)
          </th>
        </tr>
      </thead>
      <tbody>
        {windows.map((w, i) => {
          const gap = w.train_sharpe - w.test_sharpe;
          const gapClass =
            gap > 1.0
              ? "text-accent-red"
              : gap > 0.5
              ? "text-accent-yellow"
              : "text-text-primary";
          return (
            <tr
              key={i}
              className="border-t border-border-subtle"
            >
              <td className="px-3 py-1.5 text-text-secondary">w{i + 1}</td>
              <td className="num px-3 py-1.5 text-text-secondary">
                {w.train_start.slice(0, 10)} → {w.train_end.slice(0, 10)}
              </td>
              <td className="num px-3 py-1.5 text-text-secondary">
                {w.test_start.slice(0, 10)} → {w.test_end.slice(0, 10)}
              </td>
              <td className="num px-3 py-1.5 text-right">
                {fmtNum(w.train_sharpe, 2, true)}
              </td>
              <td
                className={cn(
                  "num px-3 py-1.5 text-right font-semibold",
                  w.test_sharpe >= 0.5
                    ? "text-accent-green"
                    : w.test_sharpe < 0
                    ? "text-accent-red"
                    : "text-text-primary"
                )}
              >
                {fmtNum(w.test_sharpe, 2, true)}
              </td>
              <td className={cn("num px-3 py-1.5 text-right", gapClass)}>
                {fmtNum(gap, 2, true)}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function verdictForGap(gap: number): { label: string } {
  if (gap > 1.0) return { label: "likely overfit · train ≫ test" };
  if (gap > 0.5) return { label: "watch · train > test" };
  if (gap > -0.3) return { label: "consistent · train ≈ test" };
  return { label: "test > train · luck or regime shift" };
}

function overfitVerdictColor(
  gap: number
): "green" | "red" | "yellow" | undefined {
  if (gap > 1.0) return "red";
  if (gap > 0.5) return "yellow";
  return "green";
}
