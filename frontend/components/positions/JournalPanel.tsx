"use client";

import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Download } from "lucide-react";
import {
  clearNavHistory,
  computeLiveStats,
  lotsFromPositions,
  meanBacktestSharpe,
  readNavHistory,
  type LiveStats,
  type NavSnapshot,
  type TaxLot,
} from "@/lib/journal";
import { type Position } from "@/lib/positions";
import { cn, fmtNum, fmtPct } from "@/lib/utils";

// Reads journal state out of localStorage and renders:
//   * NAV equity curve + live stats vs the recorded backtest reference
//   * Trade log (closed positions, latest first)
//   * Tax-lot ledger (CSV export)

export function JournalPanel({ positions }: { positions: Position[] }) {
  const [history, setHistory] = useState<NavSnapshot[]>([]);
  const [stats, setStats] = useState<LiveStats>({
    totalReturn: 0,
    cagr: 0,
    annualVol: 0,
    sharpe: 0,
    maxDrawdown: 0,
    nDays: 0,
  });
  const [backtestSharpe, setBacktestSharpe] = useState(0);

  useEffect(() => {
    const refresh = () => {
      setHistory(readNavHistory());
      setStats(computeLiveStats());
      setBacktestSharpe(meanBacktestSharpe());
    };
    refresh();
    window.addEventListener("storage", refresh);
    window.addEventListener("statarb.nav.update", refresh);
    window.addEventListener("statarb.positions.update", refresh);
    return () => {
      window.removeEventListener("storage", refresh);
      window.removeEventListener("statarb.nav.update", refresh);
      window.removeEventListener("statarb.positions.update", refresh);
    };
  }, []);

  const lots = lotsFromPositions(positions);
  const closed = positions.filter((p) => p.status === "closed");
  const sharpeGap = stats.sharpe - backtestSharpe;

  return (
    <div className="flex flex-col">
      <div className="flex items-center justify-between border-b border-border-subtle bg-bg-panel px-4 py-2">
        <div className="text-2xs uppercase tracking-widest text-text-secondary">
          회계 + 일지 / Journal
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => downloadCsv(lots)}
            className="flex items-center gap-1 rounded border border-border-subtle px-2 py-0.5 text-2xs uppercase tracking-widest text-text-secondary hover:bg-bg-elevated"
          >
            <Download className="h-3 w-3" />
            tax lots CSV
          </button>
          <button
            onClick={() => clearNavHistory()}
            className="rounded border border-border-subtle px-2 py-0.5 text-2xs uppercase tracking-widest text-text-secondary hover:bg-bg-elevated"
          >
            NAV 리셋
          </button>
        </div>
      </div>

      <StatsStrip stats={stats} backtestSharpe={backtestSharpe} sharpeGap={sharpeGap} />

      <div className="grid grid-cols-1 gap-px bg-border-subtle p-px lg:grid-cols-[3fr_2fr]">
        <Panel title="일일 NAV / Daily NAV" hint={`${history.length} day(s)`}>
          <NavChart history={history} />
        </Panel>
        <Panel title="live vs backtest Sharpe" hint="gap = live − backtest">
          <SharpeCompare
            live={stats.sharpe}
            backtest={backtestSharpe}
            gap={sharpeGap}
          />
        </Panel>
      </div>

      <Panel title={`거래 일지 / Trade log · ${closed.length}`}>
        <TradeLog positions={closed} />
      </Panel>

      <Panel title={`Tax lot ledger · ${lots.length}`}>
        <LotsTable lots={lots} />
      </Panel>
    </div>
  );
}

function Panel({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col border border-border-subtle bg-bg-panel">
      <div className="flex items-center justify-between border-b border-border-subtle px-3 py-1.5">
        <div className="text-2xs uppercase tracking-widest text-text-secondary">
          {title}
        </div>
        {hint && (
          <div className="text-2xs uppercase tracking-widest text-text-muted">
            {hint}
          </div>
        )}
      </div>
      <div className="flex-1 p-2">{children}</div>
    </div>
  );
}

function StatsStrip({
  stats,
  backtestSharpe,
  sharpeGap,
}: {
  stats: LiveStats;
  backtestSharpe: number;
  sharpeGap: number;
}) {
  const gapClass =
    Math.abs(sharpeGap) < 0.3
      ? "text-accent-green"
      : Math.abs(sharpeGap) < 0.7
      ? "text-accent-yellow"
      : "text-accent-red";
  return (
    <div className="grid grid-cols-2 gap-px border-y border-border-subtle bg-border-subtle md:grid-cols-7">
      <Cell label="days">
        <span className="num text-base">{stats.nDays}</span>
      </Cell>
      <Cell label="total return">
        <span
          className={cn(
            "num text-base",
            stats.totalReturn >= 0 ? "text-accent-green" : "text-accent-red"
          )}
        >
          {fmtPct(stats.totalReturn, 2, true)}
        </span>
      </Cell>
      <Cell label="CAGR">
        <span className="num text-base">{fmtPct(stats.cagr, 2, true)}</span>
      </Cell>
      <Cell label="annual vol">
        <span className="num text-base">
          {fmtPct(stats.annualVol, 2, false)}
        </span>
      </Cell>
      <Cell label="live Sharpe">
        <span className="num text-base">{fmtNum(stats.sharpe, 2, true)}</span>
      </Cell>
      <Cell label="backtest Sharpe (avg)">
        <span className="num text-base">
          {fmtNum(backtestSharpe, 2, true)}
        </span>
      </Cell>
      <Cell label="Sharpe gap">
        <span className={cn("num text-base font-semibold", gapClass)}>
          {fmtNum(sharpeGap, 2, true)}
        </span>
      </Cell>
    </div>
  );
}

function Cell({
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

function NavChart({ history }: { history: NavSnapshot[] }) {
  if (history.length < 2) {
    return (
      <div className="flex h-[220px] items-center justify-center text-2xs uppercase tracking-widest text-text-faint">
        NAV history는 폴링이 며칠 누적되어야 그려집니다.
      </div>
    );
  }
  const data = history.map((s) => ({
    t: s.date.slice(5),
    pnl: (s.nav / s.capital - 1) * 100,
  }));
  return (
    <div className="h-[220px] w-full">
      <ResponsiveContainer>
        <AreaChart
          data={data}
          margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
        >
          <CartesianGrid stroke="#1a1a1a" />
          <XAxis
            dataKey="t"
            stroke="#4b5563"
            fontSize={9}
            interval="preserveStartEnd"
            minTickGap={32}
          />
          <YAxis
            stroke="#4b5563"
            fontSize={9}
            width={40}
            tickFormatter={(v) => `${v.toFixed(1)}%`}
          />
          <Tooltip
            contentStyle={{
              background: "#000",
              border: "1px solid #2a2a2a",
              fontSize: 11,
            }}
            labelStyle={{ color: "#9ca3af" }}
            formatter={(v: number) => [`${v.toFixed(2)}%`, "NAV vs cap"]}
          />
          <ReferenceLine y={0} stroke="#4b5563" strokeWidth={0.6} />
          <Area
            type="monotone"
            dataKey="pnl"
            stroke="#00ff88"
            fill="url(#navfill)"
            strokeWidth={1.2}
            isAnimationActive={false}
          />
          <defs>
            <linearGradient id="navfill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#00ff88" stopOpacity={0.25} />
              <stop offset="100%" stopColor="#00ff88" stopOpacity={0} />
            </linearGradient>
          </defs>
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function SharpeCompare({
  live,
  backtest,
  gap,
}: {
  live: number;
  backtest: number;
  gap: number;
}) {
  return (
    <div className="flex h-[220px] flex-col justify-between gap-3 p-2">
      <Row label="live (NAV-based, 252)" value={live} />
      <Row label="backtest avg (recent 5)" value={backtest} />
      <Row label="gap" value={gap} bold />
      <p className="text-2xs text-text-muted">
        gap이 작을수록 백테스트가 실거래(가상)에서도 재현된다는 의미.{" "}
        <span className="text-accent-yellow">±0.3 ~ ±0.7</span> 사이면
        주의,{" "}
        <span className="text-accent-red">|gap| &gt; 0.7</span> 이면 모델 또는
        실행을 재검증.
      </p>
    </div>
  );
}

function Row({
  label,
  value,
  bold,
}: {
  label: string;
  value: number;
  bold?: boolean;
}) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs text-text-secondary">{label}</span>
      <span
        className={cn(
          "num text-lg",
          bold && "font-semibold",
          value > 0
            ? "text-accent-green"
            : value < 0
            ? "text-accent-red"
            : "text-text-primary"
        )}
      >
        {fmtNum(value, 2, true)}
      </span>
    </div>
  );
}

function TradeLog({ positions }: { positions: Position[] }) {
  if (positions.length === 0) {
    return (
      <div className="px-3 py-8 text-center text-2xs uppercase tracking-widest text-text-faint">
        종료된 거래가 없습니다.
      </div>
    );
  }
  return (
    <table className="w-full text-xs">
      <thead className="text-text-muted">
        <tr>
          <Th>opened</Th>
          <Th>closed</Th>
          <Th>pair</Th>
          <Th>side</Th>
          <Th right>entry z</Th>
          <Th right>exit z</Th>
          <Th right>reason</Th>
        </tr>
      </thead>
      <tbody>
        {positions
          .slice()
          .sort((a, b) => (b.closedAt ?? 0) - (a.closedAt ?? 0))
          .map((p) => (
            <tr key={p.id} className="border-t border-border-subtle">
              <Td>
                <span className="num text-2xs text-text-muted">
                  {new Date(p.openedAt).toISOString().slice(0, 19).replace("T", " ")}
                </span>
              </Td>
              <Td>
                <span className="num text-2xs text-text-muted">
                  {p.closedAt
                    ? new Date(p.closedAt).toISOString().slice(0, 19).replace("T", " ")
                    : "—"}
                </span>
              </Td>
              <Td>
                <span className="num text-accent-cyan">{p.base}</span>
                <span className="text-text-faint">/</span>
                <span className="num text-accent-magenta">{p.quote}</span>
              </Td>
              <Td>
                <span
                  className={cn(
                    "text-2xs font-semibold uppercase",
                    p.side === "long_spread"
                      ? "text-accent-green"
                      : "text-accent-red"
                  )}
                >
                  {p.side === "long_spread" ? "LONG" : "SHORT"}
                </span>
              </Td>
              <Td right>
                <span className="num">{fmtNum(p.entryZ, 2, true)}</span>
              </Td>
              <Td right>
                <span className="num">
                  {fmtNum(p.exitZ ?? 0, 2, true)}
                </span>
              </Td>
              <Td right>
                <span className="text-2xs uppercase tracking-widest text-text-secondary">
                  {p.closeReason ?? "—"}
                </span>
              </Td>
            </tr>
          ))}
      </tbody>
    </table>
  );
}

function LotsTable({ lots }: { lots: TaxLot[] }) {
  if (lots.length === 0) {
    return (
      <div className="px-3 py-8 text-center text-2xs uppercase tracking-widest text-text-faint">
        lot이 없습니다. 페어 청산 후 자동 등록됩니다.
      </div>
    );
  }
  return (
    <table className="w-full text-xs">
      <thead className="text-text-muted">
        <tr>
          <Th>closed</Th>
          <Th>pair</Th>
          <Th>side</Th>
          <Th right>base basis → proceeds (gain)</Th>
          <Th right>quote basis → proceeds (gain)</Th>
          <Th right>net</Th>
        </tr>
      </thead>
      <tbody>
        {lots.map((lot) => (
          <tr key={lot.id} className="border-t border-border-subtle">
            <Td>
              <span className="num text-2xs text-text-muted">
                {new Date(lot.closedAt).toISOString().slice(0, 19).replace("T", " ")}
              </span>
            </Td>
            <Td>
              <span className="num text-accent-cyan">{lot.base}</span>
              <span className="text-text-faint">/</span>
              <span className="num text-accent-magenta">{lot.quote}</span>
            </Td>
            <Td>
              <span
                className={cn(
                  "text-2xs font-semibold uppercase",
                  lot.side === "long_spread"
                    ? "text-accent-green"
                    : "text-accent-red"
                )}
              >
                {lot.side === "long_spread" ? "LONG" : "SHORT"}
              </span>
            </Td>
            <Td right>
              <span className="num text-text-secondary">
                ${lot.baseLeg.basis.toFixed(2)} → ${lot.baseLeg.proceeds.toFixed(2)} (
                <span
                  className={cn(
                    lot.baseLeg.gain >= 0
                      ? "text-accent-green"
                      : "text-accent-red"
                  )}
                >
                  {lot.baseLeg.gain >= 0 ? "+" : ""}
                  {lot.baseLeg.gain.toFixed(2)}
                </span>
                )
              </span>
            </Td>
            <Td right>
              <span className="num text-text-secondary">
                ${lot.quoteLeg.basis.toFixed(2)} → ${lot.quoteLeg.proceeds.toFixed(2)} (
                <span
                  className={cn(
                    lot.quoteLeg.gain >= 0
                      ? "text-accent-green"
                      : "text-accent-red"
                  )}
                >
                  {lot.quoteLeg.gain >= 0 ? "+" : ""}
                  {lot.quoteLeg.gain.toFixed(2)}
                </span>
                )
              </span>
            </Td>
            <Td right>
              <span
                className={cn(
                  "num font-semibold",
                  lot.netGain >= 0 ? "text-accent-green" : "text-accent-red"
                )}
              >
                ${lot.netGain >= 0 ? "+" : ""}
                {lot.netGain.toFixed(2)}
              </span>
            </Td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Th({
  children,
  right,
}: {
  children: React.ReactNode;
  right?: boolean;
}) {
  return (
    <th
      className={cn(
        "px-3 py-2 font-normal uppercase tracking-widest text-2xs",
        right ? "text-right" : "text-left"
      )}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  right,
}: {
  children: React.ReactNode;
  right?: boolean;
}) {
  return (
    <td className={cn("px-3 py-2", right ? "text-right" : "text-left")}>
      {children}
    </td>
  );
}

function downloadCsv(lots: TaxLot[]) {
  const header =
    "closed,pairId,base,quote,side,base_basis,base_proceeds,base_gain,quote_basis,quote_proceeds,quote_gain,net_gain";
  const rows = lots.map((l) =>
    [
      new Date(l.closedAt).toISOString(),
      l.pairId,
      l.base,
      l.quote,
      l.side,
      l.baseLeg.basis,
      l.baseLeg.proceeds,
      l.baseLeg.gain,
      l.quoteLeg.basis,
      l.quoteLeg.proceeds,
      l.quoteLeg.gain,
      l.netGain,
    ].join(",")
  );
  const csv = [header, ...rows].join("\n");
  const blob = new Blob([csv], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `statarb-tax-lots-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
