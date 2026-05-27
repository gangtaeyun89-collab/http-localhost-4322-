"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  fetchPairQuotesBrowser,
  type PairQuote,
} from "@/lib/api";
import type { PairListRow } from "@/lib/mock";
import { cn, fmtNum, fmtPct } from "@/lib/utils";

// Live-polling watch table. Server-rendered with the static screen row
// (pair, half-life, p-value) and then a single browser-side poll fills in
// the moving columns (z-score, signal, last bar Δ) every `interval` ms.
//
// Sorts pairs by |z-score| so the tradeable ones float to the top -- the
// dashboard's whole point is "where should I be looking right now".

type Row = PairListRow & { tick?: PairQuote };

const SIGNAL_LABEL: Record<PairQuote["signal"], string> = {
  flat: "FLAT",
  long_spread: "LONG SPREAD",
  short_spread: "SHORT SPREAD",
};

const SIGNAL_COLOUR: Record<PairQuote["signal"], string> = {
  flat: "bg-text-muted/15 text-text-muted",
  long_spread: "bg-accent-green/15 text-accent-green",
  short_spread: "bg-accent-red/15 text-accent-red",
};

export function PairsWatchTable({
  seedRows,
  interval = 5000,
}: {
  seedRows: PairListRow[];
  interval?: number;
}) {
  const [quotes, setQuotes] = useState<Record<string, PairQuote>>({});
  const [lastTick, setLastTick] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const ids = useMemo(() => seedRows.map((r) => r.id), [seedRows]);

  useEffect(() => {
    if (ids.length === 0) return;
    let cancelled = false;

    async function poll() {
      try {
        const bulk = await fetchPairQuotesBrowser(ids);
        if (cancelled) return;
        const map: Record<string, PairQuote> = {};
        bulk.quotes.forEach((q) => {
          map[`${q.base}-${q.quote}`] = q;
        });
        setQuotes(map);
        setLastTick(bulk.asOf);
        setError(null);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      }
    }

    poll();
    const id = setInterval(poll, interval);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [ids, interval]);

  // Rows enriched with their latest quote, sorted by |z| so the action is
  // at the top of the page.
  const rows: Row[] = useMemo(() => {
    return seedRows
      .map((r) => ({ ...r, tick: quotes[r.id] }))
      .sort((a, b) => {
        const za = a.tick ? Math.abs(a.tick.lastZScore) : 0;
        const zb = b.tick ? Math.abs(b.tick.lastZScore) : 0;
        return zb - za;
      });
  }, [seedRows, quotes]);

  const counts = useMemo(() => {
    const c = { long: 0, short: 0, flat: 0, total: rows.length };
    rows.forEach((r) => {
      if (!r.tick) return;
      if (r.tick.signal === "long_spread") c.long++;
      else if (r.tick.signal === "short_spread") c.short++;
      else c.flat++;
    });
    return c;
  }, [rows]);

  return (
    <div className="flex flex-col">
      <SummaryBar counts={counts} lastTick={lastTick} error={error} />
      <div className="border-y border-border-subtle bg-bg-panel">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-text-muted">
              <Th>페어 / Pair</Th>
              <Th>산업</Th>
              <Th right>half-life</Th>
              <Th right>p-value</Th>
              <Th right>z-score</Th>
              <Th right>spread</Th>
              <Th right>Δbase</Th>
              <Th right>Δquote</Th>
              <Th right>signal</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <PairRow key={row.id} row={row} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PairRow({ row }: { row: Row }) {
  const q = row.tick;
  const z = q?.lastZScore ?? 0;
  const absZ = Math.abs(z);

  // Threshold backgrounds so the eye finds the actionable rows first.
  const rowHighlight =
    absZ >= 2
      ? "bg-accent-red/5"
      : absZ >= 1.5
      ? "bg-accent-yellow/5"
      : "";

  const zClass =
    absZ > 2
      ? "text-accent-red"
      : absZ > 1
      ? "text-accent-yellow"
      : "text-text-primary";

  return (
    <tr
      className={cn(
        "border-t border-border-subtle hover:bg-bg-elevated",
        rowHighlight
      )}
    >
      <Td>
        <Link href={`/equity/pairs/${row.id}`} className="flex items-center gap-2">
          <span className="num font-semibold text-accent-cyan">{row.base}</span>
          <span className="text-text-faint">/</span>
          <span className="num font-semibold text-accent-magenta">
            {row.quote}
          </span>
        </Link>
      </Td>
      <Td>
        <span className="text-text-secondary">{row.industry ?? "—"}</span>
      </Td>
      <Td right>
        <span className="num">{fmtNum(row.halfLife, 1)}</span>
      </Td>
      <Td right>
        <span className="num">{fmtNum(row.cointPValue, 4)}</span>
      </Td>
      <Td right>
        <span className={cn("num font-semibold", zClass)}>
          {q ? fmtNum(z, 2, true) : "—"}
        </span>
      </Td>
      <Td right>
        <span className="num">
          {q ? fmtNum(q.lastSpread, 4, true) : "—"}
        </span>
      </Td>
      <Td right>
        <span
          className={cn(
            "num",
            q && q.lastReturn.base >= 0
              ? "text-accent-green"
              : "text-accent-red"
          )}
        >
          {q ? fmtPct(q.lastReturn.base, 2, true) : "—"}
        </span>
      </Td>
      <Td right>
        <span
          className={cn(
            "num",
            q && q.lastReturn.quote >= 0
              ? "text-accent-green"
              : "text-accent-red"
          )}
        >
          {q ? fmtPct(q.lastReturn.quote, 2, true) : "—"}
        </span>
      </Td>
      <Td right>
        {q ? (
          <span
            className={cn(
              "rounded px-1.5 py-0.5 text-2xs font-semibold tracking-widest",
              SIGNAL_COLOUR[q.signal]
            )}
          >
            {SIGNAL_LABEL[q.signal]}
          </span>
        ) : (
          <span className="text-text-muted">—</span>
        )}
      </Td>
    </tr>
  );
}

function SummaryBar({
  counts,
  lastTick,
  error,
}: {
  counts: { long: number; short: number; flat: number; total: number };
  lastTick: string | null;
  error: string | null;
}) {
  const active = counts.long + counts.short;
  return (
    <div className="flex flex-wrap items-center gap-x-6 gap-y-1 border-b border-border-subtle bg-bg-panel px-4 py-2 text-2xs uppercase tracking-widest text-text-muted">
      <span>
        watching{" "}
        <span className="num text-text-primary">{counts.total}</span> pair(s)
      </span>
      <span>
        active signal{" "}
        <span
          className={cn(
            "num font-semibold",
            active > 0 ? "text-accent-red" : "text-text-muted"
          )}
        >
          {active}
        </span>
      </span>
      <span>
        long-spread{" "}
        <span className="num text-accent-green">{counts.long}</span>
      </span>
      <span>
        short-spread{" "}
        <span className="num text-accent-red">{counts.short}</span>
      </span>
      <span>
        flat <span className="num text-text-primary">{counts.flat}</span>
      </span>
      <span className="ml-auto">
        {error ? (
          <span className="text-accent-red">polling error</span>
        ) : lastTick ? (
          <span>
            last tick{" "}
            <span className="num text-text-secondary">
              {lastTick.replace("T", " ").slice(0, 19)}
            </span>{" "}
            UTC
          </span>
        ) : (
          <span>connecting…</span>
        )}
      </span>
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
