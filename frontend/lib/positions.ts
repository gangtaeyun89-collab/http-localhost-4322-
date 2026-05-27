// Paper trade journal stored entirely in localStorage.
//
// We don't have a real order pipeline yet, but we *do* want to answer
// "if I had entered this pair here, where would I be now?" To do that we
// snapshot the live quote at the moment the user hits the entry button --
// z-score, spread, both leg prices, hedge ratio, half-life -- and then
// the positions page re-polls every few seconds, computes hypothetical
// P&L, and auto-closes when the spread reverts past the exit threshold.
//
// Same shape will plug into a real broker layer later: replace
// openPosition / closePosition with IBKR combo-order calls and add a
// poll for fills.

import type { PairQuote } from "@/lib/api";

const STORAGE_KEY = "statarb.positions.v1";

export const EXIT_Z = 0.5;
export const STOP_Z = 4.0;

export type PositionSide = "long_spread" | "short_spread";

export type CloseReason = "profit" | "stop" | "manual" | "time";

export type Position = {
  id: string; // unique
  pairId: string; // "EQR-MAA"
  base: string;
  quote: string;
  side: PositionSide;
  // Snapshot at entry
  entryZ: number;
  entrySpread: number;
  entryBase: number;
  entryQuote: number;
  hedgeRatio: number;
  halfLife: number;
  openedAt: number; // epoch ms
  openedBar: string; // entry bar timestamp
  status: "open" | "closed";
  // Snapshot at close
  exitZ?: number;
  exitSpread?: number;
  exitBase?: number;
  exitQuote?: number;
  closedAt?: number;
  closedBar?: string;
  closeReason?: CloseReason;
};

function uid(): string {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

function readAll(): Position[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Position[]) : [];
  } catch {
    return [];
  }
}

function writeAll(positions: Position[]) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(positions));
    window.dispatchEvent(new CustomEvent("statarb.positions.update"));
  } catch {
    // private mode / quota -- silently degrade
  }
}

export function listOpen(): Position[] {
  return readAll().filter((p) => p.status === "open");
}

export function listClosed(): Position[] {
  return readAll().filter((p) => p.status === "closed");
}

export function listAll(): Position[] {
  return readAll();
}

export function openPosition(args: {
  pairId: string;
  side: PositionSide;
  quote: PairQuote;
}): Position {
  const all = readAll();
  const open = all.find(
    (p) => p.status === "open" && p.pairId === args.pairId
  );
  if (open) {
    // Idempotent: don't allow two open positions on the same pair.
    return open;
  }
  const q = args.quote;
  const pos: Position = {
    id: uid(),
    pairId: args.pairId,
    base: q.base,
    quote: q.quote,
    side: args.side,
    entryZ: q.lastZScore,
    entrySpread: q.lastSpread,
    entryBase: q.lastBar.base,
    entryQuote: q.lastBar.quote,
    hedgeRatio: q.hedgeRatio,
    halfLife: q.halfLife,
    openedAt: Date.now(),
    openedBar: q.lastBar.t,
    status: "open",
  };
  writeAll([pos, ...all]);
  return pos;
}

export function closePosition(
  id: string,
  quote: PairQuote,
  reason: CloseReason
) {
  const all = readAll();
  const idx = all.findIndex((p) => p.id === id);
  if (idx < 0) return;
  const p = all[idx];
  if (p.status === "closed") return;
  all[idx] = {
    ...p,
    status: "closed",
    exitZ: quote.lastZScore,
    exitSpread: quote.lastSpread,
    exitBase: quote.lastBar.base,
    exitQuote: quote.lastBar.quote,
    closedAt: Date.now(),
    closedBar: quote.lastBar.t,
    closeReason: reason,
  };
  writeAll(all);
}

export function findOpenByPair(pairId: string): Position | undefined {
  return readAll().find(
    (p) => p.status === "open" && p.pairId === pairId
  );
}

export function clearAll() {
  writeAll([]);
}

export function removeClosed() {
  writeAll(readAll().filter((p) => p.status === "open"));
}

// -- Live derived quantities ------------------------------------------------

/** Bars between entry and the current quote's lastBar timestamp. Crude --
 * counts calendar days for daily bars; good enough for the dashboard. */
export function barsElapsed(p: Position, currentBarTs: string): number {
  const entry = new Date(p.openedBar).getTime();
  const now = new Date(currentBarTs).getTime();
  if (!isFinite(entry) || !isFinite(now)) return 0;
  // Assume the typical bar is a day; if the deltas are smaller it scales
  // down proportionally. This is approximate but the dashboard only uses
  // it for "bars since entry" colouring, not for any financial math.
  const ONE_DAY = 86_400_000;
  return Math.max(0, Math.round((now - entry) / ONE_DAY));
}

/** OU-implied expected bars to reach |z| <= exit_z from the current z.
 * z_t = z_0 * exp(-t * ln(2) / half_life)
 * t = half_life * log2(|z_now| / exit_z)
 */
export function expectedBarsToExit(
  currentZ: number,
  halfLife: number,
  exitZ: number = EXIT_Z
): number | null {
  if (!isFinite(currentZ) || !isFinite(halfLife) || halfLife <= 0) return null;
  const absZ = Math.abs(currentZ);
  if (absZ <= exitZ) return 0;
  return Math.max(0, halfLife * Math.log2(absZ / exitZ));
}

/** P&L on a unit-notional spread position. Long spread = long base + short
 * hedgeRatio * quote (in log-price terms); short spread = the opposite.
 *
 * Returns the fractional return on the long-leg notional (i.e. 0.0123 = 1.23%).
 * Realistic enough for the paper-paper journal; the real-money path will
 * compute P&L from actual fills.
 */
export function positionPnl(p: Position, q: PairQuote): number {
  if (q.lastBar.base <= 0 || q.lastBar.quote <= 0) return 0;
  if (p.entryBase <= 0 || p.entryQuote <= 0) return 0;
  const baseRet = Math.log(q.lastBar.base / p.entryBase);
  const quoteRet = Math.log(q.lastBar.quote / p.entryQuote);
  const spreadRet = baseRet - p.hedgeRatio * quoteRet;
  const sign = p.side === "long_spread" ? 1 : -1;
  return sign * spreadRet;
}

/** Auto-close rule: profit on revert past exit_z, stop on extreme move,
 * time-stop after holding > 3 half-lives. Returns the reason or null. */
export function shouldAutoClose(
  p: Position,
  q: PairQuote,
  currentBarTs: string
): CloseReason | null {
  const z = q.lastZScore;
  if (!isFinite(z)) return null;
  // Profit: spread back to ±exit_z (inclusive of zero crossover)
  if (Math.abs(z) <= EXIT_Z) return "profit";
  // Stop: spread blown out further past the wrong side
  if (p.side === "long_spread" && z <= -STOP_Z) return "stop";
  if (p.side === "short_spread" && z >= STOP_Z) return "stop";
  // Time stop: held longer than 3 half-lives -- the mean-reversion thesis
  // is probably dead.
  const elapsed = barsElapsed(p, currentBarTs);
  if (p.halfLife > 0 && elapsed > 3 * p.halfLife) return "time";
  return null;
}
