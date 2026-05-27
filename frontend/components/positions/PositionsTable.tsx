"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { Trash2, X } from "lucide-react";
import { fetchPairQuotesBrowser, type PairQuote } from "@/lib/api";
import {
  barsElapsed,
  closePosition,
  EXIT_Z,
  expectedBarsToExit,
  listAll,
  positionPnl,
  removeClosed,
  shouldAutoClose,
  STOP_Z,
  type Position,
} from "@/lib/positions";
import { cn, fmtNum, fmtPct } from "@/lib/utils";

// Active + closed positions, hypothetical P&L computed against the latest
// bulk-quote tick. We poll the bulk endpoint with the union of every open
// pair's id, so adding pairs doesn't multiply the network load.
//
// Auto-close runs on every tick: revert past exit_z -> profit, blow out
// past stop_z -> stop, held longer than 3 half-lives -> time stop. Manual
// close is a button on each row.

export function PositionsTable() {
  const [tick, setTick] = useState(0); // forces re-render after each poll
  const [positions, setPositions] = useState<Position[]>([]);
  const [quotes, setQuotes] = useState<Record<string, PairQuote>>({});
  const [lastPoll, setLastPoll] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const closingRef = useRef<Set<string>>(new Set());

  // Mirror localStorage into React state. Updates from this tab fire a
  // custom event; updates from other tabs fire 'storage'.
  useEffect(() => {
    const refresh = () => setPositions(listAll());
    refresh();
    window.addEventListener("storage", refresh);
    window.addEventListener("statarb.positions.update", refresh);
    return () => {
      window.removeEventListener("storage", refresh);
      window.removeEventListener("statarb.positions.update", refresh);
    };
  }, []);

  const open = useMemo(
    () => positions.filter((p) => p.status === "open"),
    [positions]
  );
  const closed = useMemo(
    () =>
      positions
        .filter((p) => p.status === "closed")
        .sort((a, b) => (b.closedAt ?? 0) - (a.closedAt ?? 0)),
    [positions]
  );

  const openIds = useMemo(
    () => Array.from(new Set(open.map((p) => p.pairId))),
    [open]
  );

  useEffect(() => {
    if (openIds.length === 0) {
      setQuotes({});
      return;
    }
    let cancelled = false;

    async function poll() {
      try {
        const bulk = await fetchPairQuotesBrowser(openIds);
        if (cancelled) return;
        const map: Record<string, PairQuote> = {};
        bulk.quotes.forEach((q) => {
          map[`${q.base}-${q.quote}`] = q;
        });
        setQuotes(map);
        setLastPoll(bulk.asOf);
        setError(null);
        setTick((t) => t + 1);

        // Auto-close pass. Use a ref'd "currently closing" set so a slow
        // setPositions doesn't cause us to fire close twice on the same id.
        const current = listAll();
        for (const p of current) {
          if (p.status !== "open") continue;
          const q = map[p.pairId];
          if (!q) continue;
          if (closingRef.current.has(p.id)) continue;
          const reason = shouldAutoClose(p, q, q.lastBar.t);
          if (reason) {
            closingRef.current.add(p.id);
            closePosition(p.id, q, reason);
          }
        }
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      }
    }

    poll();
    const id = setInterval(poll, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [openIds]);

  return (
    <div className="flex flex-col">
      <SummaryBar
        open={open}
        closed={closed}
        quotes={quotes}
        lastPoll={lastPoll}
        error={error}
      />
      <Section title={`활성 포지션 / Open positions · ${open.length}`}>
        {open.length === 0 ? (
          <EmptyOpen />
        ) : (
          <OpenTable positions={open} quotes={quotes} />
        )}
      </Section>
      <Section
        title={`종료된 포지션 / Closed · ${closed.length}`}
        right={
          closed.length > 0 ? (
            <button
              onClick={() => removeClosed()}
              className="flex items-center gap-1 rounded border border-border-subtle px-2 py-0.5 text-2xs uppercase tracking-widest text-text-secondary hover:bg-bg-elevated"
            >
              <Trash2 className="h-3 w-3" />
              종료 기록 삭제
            </button>
          ) : null
        }
      >
        {closed.length === 0 ? (
          <EmptyClosed />
        ) : (
          <ClosedTable positions={closed} />
        )}
      </Section>
    </div>
  );
}

function SummaryBar({
  open,
  closed,
  quotes,
  lastPoll,
  error,
}: {
  open: Position[];
  closed: Position[];
  quotes: Record<string, PairQuote>;
  lastPoll: string | null;
  error: string | null;
}) {
  // Running totals across the journal.
  const livePnls = open.map((p) => {
    const q = quotes[p.pairId];
    return q ? positionPnl(p, q) : 0;
  });
  const openPnl = livePnls.reduce((a, b) => a + b, 0);
  const realisedPnl = closed.reduce((acc, p) => {
    if (p.exitBase == null || p.exitQuote == null) return acc;
    const baseRet = Math.log(p.exitBase / p.entryBase);
    const quoteRet = Math.log(p.exitQuote / p.entryQuote);
    const spreadRet = baseRet - p.hedgeRatio * quoteRet;
    const sign = p.side === "long_spread" ? 1 : -1;
    return acc + sign * spreadRet;
  }, 0);
  const wins = closed.filter((p) => {
    if (p.exitBase == null || p.exitQuote == null) return false;
    const baseRet = Math.log(p.exitBase / p.entryBase);
    const quoteRet = Math.log(p.exitQuote / p.entryQuote);
    const spreadRet = baseRet - p.hedgeRatio * quoteRet;
    const sign = p.side === "long_spread" ? 1 : -1;
    return sign * spreadRet > 0;
  }).length;
  const winRate = closed.length > 0 ? wins / closed.length : 0;

  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-1 border-b border-border-subtle bg-bg-panel px-4 py-2 text-2xs uppercase tracking-widest text-text-muted">
      <span>
        open <span className="num text-text-primary">{open.length}</span>
      </span>
      <span>
        closed <span className="num text-text-primary">{closed.length}</span>
      </span>
      <span>
        unrealised{" "}
        <span
          className={cn(
            "num font-semibold",
            openPnl >= 0 ? "text-accent-green" : "text-accent-red"
          )}
        >
          {fmtPct(openPnl, 2, true)}
        </span>
      </span>
      <span>
        realised{" "}
        <span
          className={cn(
            "num font-semibold",
            realisedPnl >= 0 ? "text-accent-green" : "text-accent-red"
          )}
        >
          {fmtPct(realisedPnl, 2, true)}
        </span>
      </span>
      <span>
        win rate{" "}
        <span className="num text-text-primary">
          {fmtPct(winRate, 1, false)}
        </span>
      </span>
      <span className="ml-auto">
        {error ? (
          <span className="text-accent-red">polling error</span>
        ) : lastPoll ? (
          <span>
            last tick{" "}
            <span className="num text-text-secondary">
              {lastPoll.replace("T", " ").slice(0, 19)}
            </span>{" "}
            UTC
          </span>
        ) : (
          <span>—</span>
        )}
      </span>
    </div>
  );
}

function Section({
  title,
  right,
  children,
}: {
  title: string;
  right?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col">
      <div className="flex items-center justify-between border-b border-border-subtle bg-bg-panel px-4 py-1.5">
        <div className="text-2xs uppercase tracking-widest text-text-secondary">
          {title}
        </div>
        {right}
      </div>
      <div className="bg-bg-panel">{children}</div>
    </div>
  );
}

function OpenTable({
  positions,
  quotes,
}: {
  positions: Position[];
  quotes: Record<string, PairQuote>;
}) {
  return (
    <table className="w-full text-xs">
      <thead className="text-text-muted">
        <tr>
          <Th>페어 / Pair</Th>
          <Th>side</Th>
          <Th right>entry z</Th>
          <Th right>cur z</Th>
          <Th right>z 진행</Th>
          <Th right>bars in</Th>
          <Th right>~exit bars</Th>
          <Th right>half-life</Th>
          <Th right>P&L (live)</Th>
          <Th right>action</Th>
        </tr>
      </thead>
      <tbody>
        {positions.map((p) => (
          <OpenRow key={p.id} pos={p} quote={quotes[p.pairId]} />
        ))}
      </tbody>
    </table>
  );
}

function OpenRow({ pos, quote }: { pos: Position; quote?: PairQuote }) {
  const z = quote?.lastZScore ?? pos.entryZ;
  const absZ = Math.abs(z);
  const zClass =
    absZ <= EXIT_Z
      ? "text-accent-green"
      : absZ >= STOP_Z
      ? "text-accent-red"
      : absZ >= 2
      ? "text-accent-yellow"
      : "text-text-primary";

  const bars = quote ? barsElapsed(pos, quote.lastBar.t) : 0;
  const etc = quote
    ? expectedBarsToExit(z, pos.halfLife, EXIT_Z)
    : null;
  const pnl = quote ? positionPnl(pos, quote) : 0;

  // Progress from entry z toward exit_z (with the right sign per side).
  // 0% = at entry, 100% = at exit threshold, >100% = past it.
  const target = pos.side === "long_spread" ? -EXIT_Z : EXIT_Z;
  const denom = pos.entryZ - target;
  const progress = denom !== 0 ? (pos.entryZ - z) / denom : 0;
  const progressClamped = Math.max(0, Math.min(1, progress));

  return (
    <tr className="border-t border-border-subtle hover:bg-bg-elevated">
      <Td>
        <Link
          href={`/equity/pairs/${pos.pairId}`}
          className="flex items-center gap-2"
        >
          <span className="num font-semibold text-accent-cyan">
            {pos.base}
          </span>
          <span className="text-text-faint">/</span>
          <span className="num font-semibold text-accent-magenta">
            {pos.quote}
          </span>
        </Link>
      </Td>
      <Td>
        <SideBadge side={pos.side} />
      </Td>
      <Td right>
        <span className="num text-text-secondary">
          {fmtNum(pos.entryZ, 2, true)}
        </span>
      </Td>
      <Td right>
        <span className={cn("num font-semibold", zClass)}>
          {quote ? fmtNum(z, 2, true) : "—"}
        </span>
      </Td>
      <Td right>
        <ProgressBar value={progressClamped} raw={progress} />
      </Td>
      <Td right>
        <span className="num">{bars}</span>
      </Td>
      <Td right>
        <span className="num text-text-secondary">
          {etc != null ? `~${etc.toFixed(0)}` : "—"}
        </span>
      </Td>
      <Td right>
        <span className="num text-text-muted">
          {fmtNum(pos.halfLife, 1)}
        </span>
      </Td>
      <Td right>
        <span
          className={cn(
            "num font-semibold",
            pnl >= 0 ? "text-accent-green" : "text-accent-red"
          )}
        >
          {fmtPct(pnl, 2, true)}
        </span>
      </Td>
      <Td right>
        <ManualCloseButton pos={pos} quote={quote} />
      </Td>
    </tr>
  );
}

function ManualCloseButton({
  pos,
  quote,
}: {
  pos: Position;
  quote?: PairQuote;
}) {
  if (!quote) {
    return <span className="text-2xs text-text-muted">—</span>;
  }
  return (
    <button
      onClick={() => closePosition(pos.id, quote, "manual")}
      className="flex items-center gap-1 rounded border border-border-subtle bg-bg-card px-1.5 py-0.5 text-2xs uppercase tracking-widest text-text-secondary hover:border-accent-red/40 hover:bg-accent-red/10 hover:text-accent-red"
    >
      <X className="h-3 w-3" />
      청산
    </button>
  );
}

function ClosedTable({ positions }: { positions: Position[] }) {
  return (
    <table className="w-full text-xs">
      <thead className="text-text-muted">
        <tr>
          <Th>페어 / Pair</Th>
          <Th>side</Th>
          <Th right>entry → exit z</Th>
          <Th right>bars held</Th>
          <Th right>realised P&L</Th>
          <Th right>reason</Th>
        </tr>
      </thead>
      <tbody>
        {positions.map((p) => (
          <ClosedRow key={p.id} pos={p} />
        ))}
      </tbody>
    </table>
  );
}

function ClosedRow({ pos }: { pos: Position }) {
  const baseRet =
    pos.exitBase != null ? Math.log(pos.exitBase / pos.entryBase) : 0;
  const quoteRet =
    pos.exitQuote != null
      ? Math.log(pos.exitQuote / pos.entryQuote)
      : 0;
  const spreadRet = baseRet - pos.hedgeRatio * quoteRet;
  const sign = pos.side === "long_spread" ? 1 : -1;
  const pnl = sign * spreadRet;

  const bars =
    pos.closedBar
      ? Math.max(
          0,
          Math.round(
            (new Date(pos.closedBar).getTime() -
              new Date(pos.openedBar).getTime()) /
              86_400_000
          )
        )
      : 0;

  return (
    <tr className="border-t border-border-subtle hover:bg-bg-elevated">
      <Td>
        <Link
          href={`/equity/pairs/${pos.pairId}`}
          className="flex items-center gap-2"
        >
          <span className="num font-semibold text-accent-cyan">
            {pos.base}
          </span>
          <span className="text-text-faint">/</span>
          <span className="num font-semibold text-accent-magenta">
            {pos.quote}
          </span>
        </Link>
      </Td>
      <Td>
        <SideBadge side={pos.side} />
      </Td>
      <Td right>
        <span className="num text-text-secondary">
          {fmtNum(pos.entryZ, 2, true)} →{" "}
          {fmtNum(pos.exitZ ?? 0, 2, true)}
        </span>
      </Td>
      <Td right>
        <span className="num">{bars}</span>
      </Td>
      <Td right>
        <span
          className={cn(
            "num font-semibold",
            pnl >= 0 ? "text-accent-green" : "text-accent-red"
          )}
        >
          {fmtPct(pnl, 2, true)}
        </span>
      </Td>
      <Td right>
        <ReasonBadge reason={pos.closeReason ?? "manual"} />
      </Td>
    </tr>
  );
}

function SideBadge({ side }: { side: Position["side"] }) {
  return side === "long_spread" ? (
    <span className="rounded bg-accent-green/15 px-1.5 py-0.5 text-2xs font-semibold uppercase tracking-widest text-accent-green">
      LONG SPREAD
    </span>
  ) : (
    <span className="rounded bg-accent-red/15 px-1.5 py-0.5 text-2xs font-semibold uppercase tracking-widest text-accent-red">
      SHORT SPREAD
    </span>
  );
}

function ReasonBadge({ reason }: { reason: NonNullable<Position["closeReason"]> }) {
  const map: Record<typeof reason, { label: string; cls: string }> = {
    profit: { label: "PROFIT", cls: "bg-accent-green/15 text-accent-green" },
    stop: { label: "STOP", cls: "bg-accent-red/15 text-accent-red" },
    time: { label: "TIME", cls: "bg-accent-yellow/15 text-accent-yellow" },
    manual: { label: "MANUAL", cls: "bg-text-muted/15 text-text-muted" },
  };
  const m = map[reason];
  return (
    <span
      className={cn(
        "rounded px-1.5 py-0.5 text-2xs font-semibold uppercase tracking-widest",
        m.cls
      )}
    >
      {m.label}
    </span>
  );
}

function ProgressBar({ value, raw }: { value: number; raw: number }) {
  // The clamped fill is visual; the raw number is the source of truth for
  // the small caption underneath.
  const pct = Math.round(value * 100);
  const overshoot = raw > 1;
  const negative = raw < 0;
  return (
    <div className="ml-auto flex w-24 flex-col items-end gap-0.5">
      <div className="relative h-1 w-full rounded bg-bg-elevated">
        <div
          className={cn(
            "absolute left-0 top-0 h-1 rounded",
            overshoot
              ? "bg-accent-green"
              : negative
              ? "bg-accent-red"
              : "bg-accent-cyan"
          )}
          style={{ width: `${Math.max(2, pct)}%` }}
        />
      </div>
      <span className="num text-2xs text-text-muted">
        {Math.round(raw * 100)}%
      </span>
    </div>
  );
}

function EmptyOpen() {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      <div className="text-sm text-text-secondary">
        활성 포지션이 없습니다.
      </div>
      <div className="mt-2 max-w-md text-xs text-text-muted">
        페어 워크벤치(/equity/pairs/[id])에 들어가서 헤더의{" "}
        <span className="text-accent-green">LONG SPREAD</span> /{" "}
        <span className="text-accent-red">SHORT SPREAD</span> 버튼으로
        가상 진입을 기록할 수 있습니다. 실제 IBKR 주문은 보내지 않습니다.
      </div>
    </div>
  );
}

function EmptyClosed() {
  return (
    <div className="px-4 py-8 text-center text-2xs uppercase tracking-widest text-text-faint">
      종료된 포지션이 없습니다.
    </div>
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
