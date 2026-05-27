"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { ArrowRight } from "lucide-react";
import {
  fetchPairQuotesBrowser,
  type PairQuote,
  type SectorSummary,
} from "@/lib/api";
import {
  alertSeverity,
  ensureNotificationPermission,
  notifyBrowser,
  playTone,
  pushHistory,
  shouldFire,
  type AlertEvent,
} from "@/lib/alerts";
import { cn, fmtNum, fmtPct } from "@/lib/utils";

// Sector card grid. Each card shows the top-3 cointegrated pairs in one
// industry basket, with a live z-score that polls in the background. Click
// the card to drop into the sector's detail page. Cross-card alert pipeline
// fires on |z| threshold crossings just like the watch table, so the same
// notifications work from either layout.

const SIGNAL_BADGE: Record<PairQuote["signal"], { label: string; cls: string }> = {
  flat: { label: "FLAT", cls: "bg-text-muted/15 text-text-muted" },
  long_spread: { label: "LONG", cls: "bg-accent-green/15 text-accent-green" },
  short_spread: { label: "SHORT", cls: "bg-accent-red/15 text-accent-red" },
};

export function SectorGrid({
  sectors,
  interval = 5000,
  alertsEnabled = true,
}: {
  sectors: SectorSummary[];
  interval?: number;
  alertsEnabled?: boolean;
}) {
  const [quotes, setQuotes] = useState<Record<string, PairQuote>>({});
  const [error, setError] = useState<string | null>(null);
  const prevAbsZ = useRef<Record<string, number>>({});

  // Flatten every top-3 pair across every sector into a single bulk-quote
  // request, so the grid uses one round-trip per tick.
  const ids = useMemo(
    () =>
      Array.from(
        new Set(
          sectors.flatMap((s) => s.topPairs.map((p) => p.id))
        )
      ),
    [sectors]
  );

  useEffect(() => {
    if (alertsEnabled) void ensureNotificationPermission();
  }, [alertsEnabled]);

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

        if (alertsEnabled) {
          for (const q of bulk.quotes) {
            if (q.source === "error") continue;
            const id = `${q.base}-${q.quote}`;
            const cur = Math.abs(q.lastZScore);
            const prev = prevAbsZ.current[id] ?? 0;
            const sev = alertSeverity(cur);
            if (sev && cur > prev && shouldFire(id, sev)) {
              const evt: AlertEvent = {
                id,
                base: q.base,
                quote: q.quote,
                zscore: q.lastZScore,
                signal: q.lastZScore >= 0 ? "short_spread" : "long_spread",
                severity: sev,
                ts: Date.now(),
              };
              pushHistory(evt);
              notifyBrowser(evt);
              playTone(sev);
            }
            prevAbsZ.current[id] = cur;
          }
        }

        setQuotes(map);
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
  }, [ids, interval, alertsEnabled]);

  return (
    <div className="grid grid-cols-1 gap-3 p-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4">
      {sectors.map((s) => (
        <SectorCard key={s.id} sector={s} quotes={quotes} />
      ))}
      {error && (
        <div className="col-span-full text-2xs text-accent-red">
          polling error: {error}
        </div>
      )}
    </div>
  );
}

function SectorCard({
  sector,
  quotes,
}: {
  sector: SectorSummary;
  quotes: Record<string, PairQuote>;
}) {
  const liveSignals = sector.topPairs.reduce((acc, p) => {
    const q = quotes[p.id];
    if (q && q.signal !== "flat") acc++;
    return acc;
  }, 0);

  const empty = sector.tickerCount < 2 || sector.pairCount === 0;
  const hot = liveSignals > 0;

  return (
    <Link
      href={`/equity/sectors/${sector.id}`}
      className={cn(
        "group flex flex-col gap-2 border border-border-subtle bg-bg-panel p-3 transition hover:border-accent-cyan/40",
        hot && "border-accent-red/40 shadow-[0_0_18px_-12px_#ff3355]"
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div
            className="truncate text-xs font-semibold text-text-primary"
            title={sector.label}
          >
            {sector.label}
          </div>
          <div className="mt-0.5 text-2xs uppercase tracking-widest text-text-muted">
            <span className="num">{sector.tickerCount}</span>
            <span className="text-text-faint">/</span>
            <span className="num">{sector.tickerCountTotal}</span>{" "}
            tickers · <span className="num">{sector.pairCount}</span> pair(s)
          </div>
        </div>
        <ArrowRight className="h-3.5 w-3.5 shrink-0 text-text-muted transition group-hover:translate-x-0.5 group-hover:text-accent-cyan" />
      </div>

      {liveSignals > 0 && (
        <div className="rounded bg-accent-red/10 px-2 py-1 text-2xs font-semibold uppercase tracking-widest text-accent-red">
          {liveSignals} active signal{liveSignals === 1 ? "" : "s"}
        </div>
      )}

      {empty ? (
        <div className="rounded border border-dashed border-border-muted bg-bg-base/40 px-2 py-3 text-center text-2xs uppercase tracking-widest text-text-faint">
          {sector.tickerCount < 2 ? "데이터 없음" : "공적분 페어 없음"}
        </div>
      ) : (
        <ul className="flex flex-col gap-1">
          {sector.topPairs.map((p) => (
            <SectorPairRow key={p.id} pair={p} quote={quotes[p.id]} />
          ))}
        </ul>
      )}
    </Link>
  );
}

function SectorPairRow({
  pair,
  quote,
}: {
  pair: { base: string; quote: string; cointPValue: number; halfLife: number; corr: number };
  quote?: PairQuote;
}) {
  const z = quote?.lastZScore;
  const absZ = z != null ? Math.abs(z) : 0;
  const zClass =
    absZ >= 2
      ? "text-accent-red"
      : absZ >= 1
      ? "text-accent-yellow"
      : z != null
      ? "text-text-primary"
      : "text-text-muted";

  return (
    <li className="flex items-center justify-between gap-2 rounded bg-bg-base/30 px-2 py-1">
      <div className="flex min-w-0 items-center gap-1.5 text-xs">
        <span className="num font-semibold text-accent-cyan">{pair.base}</span>
        <span className="text-text-faint">/</span>
        <span className="num font-semibold text-accent-magenta">{pair.quote}</span>
      </div>
      <div className="flex shrink-0 items-center gap-2 text-2xs">
        <span className="num text-text-muted" title="cointegration p-value">
          p={fmtNum(pair.cointPValue, 3)}
        </span>
        <span className={cn("num font-semibold tabular-nums", zClass)}>
          {z != null ? `z=${fmtNum(z, 2, true)}` : "—"}
        </span>
        {quote && quote.signal !== "flat" && (
          <span
            className={cn(
              "rounded px-1 py-0.5 text-2xs font-semibold uppercase",
              SIGNAL_BADGE[quote.signal].cls
            )}
          >
            {SIGNAL_BADGE[quote.signal].label}
          </span>
        )}
      </div>
    </li>
  );
}

// Suppress unused warnings while keeping the helpers around for the
// detail page that re-uses them.
export const _unused = { fmtPct };
