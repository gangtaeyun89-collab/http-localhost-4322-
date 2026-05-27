// Trading journal + NAV history.
//
// Two stores in localStorage:
//   * navHistory  -- one snapshot per UTC day; written on every poll tick
//                    (the writer dedupes by date so repeated polls are
//                    free). Used to draw the equity curve and compute
//                    live Sharpe.
//   * tradeLog    -- append-only entry/exit/close events. Today the
//                    closed-positions list is the source of truth; the
//                    journal layer adds derived stats on top.
//
// Sharpe is computed on daily NAV-fraction returns and annualised to 252
// (US equity calendar), so it matches the backtest's annualisation and
// the two can be compared honestly. The Sharpe-gap card on the journal
// page is the "live vs backtest" sanity check.

import type { PairQuote } from "@/lib/api";
import { type Position } from "@/lib/positions";
import {
  cumulativeRealised,
  currentNav,
  getRiskConfig,
  unrealisedFraction,
} from "@/lib/risk";

const NAV_KEY = "statarb.nav.history.v1";
const BACKTEST_REF_KEY = "statarb.backtest.refSharpe.v1";

export type NavSnapshot = {
  date: string; // YYYY-MM-DD UTC
  nav: number;
  capital: number;
  realised: number; // fraction of capital
  unrealised: number; // fraction of capital
  openPairs: number;
};

function readNav(): NavSnapshot[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(NAV_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function writeNav(history: NavSnapshot[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(NAV_KEY, JSON.stringify(history));
    window.dispatchEvent(new CustomEvent("statarb.nav.update"));
  } catch {
    // ignore
  }
}

export function readNavHistory(): NavSnapshot[] {
  return readNav();
}

export function clearNavHistory() {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(NAV_KEY);
    window.dispatchEvent(new CustomEvent("statarb.nav.update"));
  } catch {
    // ignore
  }
}

/** Idempotent: writes today's snapshot, overwriting any previous one for
 * the same UTC date. Called from the positions page on every poll. */
export function recordSnapshot(
  positions: Position[],
  quotes: Record<string, PairQuote>
) {
  const config = getRiskConfig();
  const today = new Date().toISOString().slice(0, 10);
  const open = positions.filter((p) => p.status === "open");
  const realised = cumulativeRealised(positions, config);
  const unrealised = unrealisedFraction(open, quotes, config);
  const nav = currentNav(positions, quotes, config);

  const snap: NavSnapshot = {
    date: today,
    nav,
    capital: config.capital,
    realised,
    unrealised,
    openPairs: open.length,
  };

  const history = readNav();
  const idx = history.findIndex((s) => s.date === today);
  if (idx >= 0) {
    history[idx] = snap;
  } else {
    history.push(snap);
  }
  // Cap to ~2 years of dailies so localStorage doesn't grow unbounded.
  const trimmed = history.slice(-730);
  writeNav(trimmed);
}

// -- Live statistics --------------------------------------------------------

export type LiveStats = {
  totalReturn: number; // (NAV/capital) - 1
  cagr: number;
  annualVol: number;
  sharpe: number;
  maxDrawdown: number;
  nDays: number;
};

const TRADING_DAYS = 252;

export function computeLiveStats(): LiveStats {
  const history = readNav();
  const n = history.length;
  if (n < 2) {
    return {
      totalReturn: 0,
      cagr: 0,
      annualVol: 0,
      sharpe: 0,
      maxDrawdown: 0,
      nDays: n,
    };
  }

  const navs = history.map((s) => s.nav);
  const capital = history[0].capital;
  const totalReturn = navs[n - 1] / capital - 1;

  // Day-over-day returns of the NAV series.
  const returns: number[] = [];
  for (let i = 1; i < n; i++) {
    if (navs[i - 1] <= 0) continue;
    returns.push(navs[i] / navs[i - 1] - 1);
  }
  const mean =
    returns.length > 0
      ? returns.reduce((a, b) => a + b, 0) / returns.length
      : 0;
  const variance =
    returns.length > 1
      ? returns.reduce((a, b) => a + (b - mean) ** 2, 0) / (returns.length - 1)
      : 0;
  const std = Math.sqrt(variance);
  const annualVol = std * Math.sqrt(TRADING_DAYS);
  const sharpe = std > 0 ? (mean / std) * Math.sqrt(TRADING_DAYS) : 0;

  // CAGR from the calendar span between first and last snapshot.
  const days =
    (new Date(history[n - 1].date).getTime() -
      new Date(history[0].date).getTime()) /
      86_400_000 || 1;
  const years = days / 365.25;
  const cagr =
    years > 0 && navs[0] > 0
      ? Math.pow(navs[n - 1] / navs[0], 1 / years) - 1
      : 0;

  // Peak-to-trough max drawdown.
  let peak = navs[0];
  let mdd = 0;
  for (const v of navs) {
    if (v > peak) peak = v;
    if (peak > 0) {
      const dd = v / peak - 1;
      if (dd < mdd) mdd = dd;
    }
  }

  return {
    totalReturn,
    cagr,
    annualVol,
    sharpe,
    maxDrawdown: mdd,
    nDays: n,
  };
}

// -- Backtest reference (for the live-vs-backtest gap card) -----------------

export type BacktestRef = {
  sharpe: number;
  recordedAt: number;
  base: string;
  quote: string;
};

export function recordBacktestSharpe(ref: BacktestRef) {
  if (typeof window === "undefined") return;
  try {
    const raw = window.localStorage.getItem(BACKTEST_REF_KEY);
    const list: BacktestRef[] = raw ? JSON.parse(raw) : [];
    list.unshift(ref);
    window.localStorage.setItem(
      BACKTEST_REF_KEY,
      JSON.stringify(list.slice(0, 20))
    );
  } catch {
    // ignore
  }
}

export function readBacktestRefs(): BacktestRef[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(BACKTEST_REF_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

/** Mean OOS Sharpe across the last K recorded backtests. Used as the
 * reference value the live Sharpe is compared against. */
export function meanBacktestSharpe(k: number = 5): number {
  const refs = readBacktestRefs().slice(0, k);
  if (refs.length === 0) return 0;
  return refs.reduce((a, b) => a + b.sharpe, 0) / refs.length;
}

// -- Tax lot ledger ---------------------------------------------------------
//
// Paper-paper has no real tax lots, but the structure already exists --
// each closed Position is one round-trip "lot" with cost basis (entry
// prices) and proceeds (exit prices). We expose the per-leg basis /
// proceeds / gain so an export to CSV is straightforward.

export type TaxLot = {
  id: string;
  pairId: string;
  base: string;
  quote: string;
  side: Position["side"];
  openedAt: number;
  closedAt: number;
  baseLeg: { basis: number; proceeds: number; gain: number };
  quoteLeg: { basis: number; proceeds: number; gain: number };
  netGain: number;
};

export function lotsFromPositions(positions: Position[]): TaxLot[] {
  const out: TaxLot[] = [];
  for (const p of positions) {
    if (p.status !== "closed") continue;
    if (p.exitBase == null || p.exitQuote == null || p.closedAt == null)
      continue;
    // Per the long-spread convention: long 1 base unit + short hedgeRatio
    // quote units; sign flips for short spread.
    const sign = p.side === "long_spread" ? 1 : -1;
    const baseGain = sign * (p.exitBase - p.entryBase);
    const quoteGain = -sign * p.hedgeRatio * (p.exitQuote - p.entryQuote);
    out.push({
      id: p.id,
      pairId: p.pairId,
      base: p.base,
      quote: p.quote,
      side: p.side,
      openedAt: p.openedAt,
      closedAt: p.closedAt,
      baseLeg: {
        basis: p.entryBase,
        proceeds: p.exitBase,
        gain: baseGain,
      },
      quoteLeg: {
        basis: p.entryQuote * p.hedgeRatio,
        proceeds: p.exitQuote * p.hedgeRatio,
        gain: quoteGain,
      },
      netGain: baseGain + quoteGain,
    });
  }
  return out.sort((a, b) => b.closedAt - a.closedAt);
}
