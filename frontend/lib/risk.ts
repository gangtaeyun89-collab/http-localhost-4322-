// Risk-limit engine and kill switch state.
//
// Three tiers of stops, all enforced on top of the existing z-score
// auto-close in lib/positions.ts:
//
//   * per-pair    max loss 1% of capital  -> force close that pair
//   * daily       max loss 2% of capital  -> block new entries
//   * cumulative  max drawdown 10%        -> KILL SWITCH:
//                                          close everything, block entries
//                                          until the user manually resets
//
// Capital and limit thresholds are user-editable from the positions page;
// the kill-switch and daily-stop *state* also lives here so any component
// can ask "can I open a new position right now?".
//
// Everything is localStorage-backed. When we wire a real broker the
// numbers stay the same -- we just compute capital from broker NAV.

import type { PairQuote } from "@/lib/api";
import { positionPnl, type Position } from "@/lib/positions";

const CONFIG_KEY = "statarb.risk.config.v1";
const KILL_KEY = "statarb.risk.kill.v1";

export type RiskConfig = {
  capital: number; // total paper capital
  perPairNotional: number; // fraction of capital allocated to each open pair
  maxLossPerPair: number; // fraction of capital -- per-pair forced stop
  maxLossDaily: number; // fraction of capital -- daily new-entry block
  maxDrawdownTotal: number; // fraction of capital -- kill switch
};

export const DEFAULT_RISK: RiskConfig = {
  capital: 100_000,
  perPairNotional: 0.05,
  maxLossPerPair: 0.01,
  maxLossDaily: 0.02,
  maxDrawdownTotal: 0.10,
};

export function getRiskConfig(): RiskConfig {
  if (typeof window === "undefined") return DEFAULT_RISK;
  try {
    const raw = window.localStorage.getItem(CONFIG_KEY);
    if (!raw) return DEFAULT_RISK;
    return { ...DEFAULT_RISK, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_RISK;
  }
}

export function setRiskConfig(patch: Partial<RiskConfig>) {
  if (typeof window === "undefined") return;
  const current = getRiskConfig();
  const next = { ...current, ...patch };
  try {
    window.localStorage.setItem(CONFIG_KEY, JSON.stringify(next));
    window.dispatchEvent(new CustomEvent("statarb.risk.update"));
  } catch {
    // ignore
  }
}

// -- Kill switch ------------------------------------------------------------

export type KillSwitchState = {
  active: boolean;
  triggeredAt?: number;
  reason?: string;
  navAtTrip?: number;
  peakNav?: number;
};

export function getKillSwitchState(): KillSwitchState {
  if (typeof window === "undefined") return { active: false };
  try {
    const raw = window.localStorage.getItem(KILL_KEY);
    return raw ? JSON.parse(raw) : { active: false };
  } catch {
    return { active: false };
  }
}

export function tripKillSwitch(reason: string, navAtTrip: number, peakNav: number) {
  if (typeof window === "undefined") return;
  const state: KillSwitchState = {
    active: true,
    triggeredAt: Date.now(),
    reason,
    navAtTrip,
    peakNav,
  };
  try {
    window.localStorage.setItem(KILL_KEY, JSON.stringify(state));
    window.dispatchEvent(new CustomEvent("statarb.risk.update"));
  } catch {
    // ignore
  }
}

export function resetKillSwitch() {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(KILL_KEY);
    window.dispatchEvent(new CustomEvent("statarb.risk.update"));
  } catch {
    // ignore
  }
}

// -- P&L aggregation --------------------------------------------------------

function todayUTC(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Realised P&L (fraction of capital) for positions closed today. */
export function dailyRealised(
  positions: Position[],
  config: RiskConfig
): number {
  const today = todayUTC();
  let pnlFraction = 0;
  for (const p of positions) {
    if (p.status !== "closed" || !p.closedAt) continue;
    const day = new Date(p.closedAt).toISOString().slice(0, 10);
    if (day !== today) continue;
    pnlFraction += closedPnlFraction(p, config);
  }
  return pnlFraction;
}

/** Cumulative realised P&L (fraction of capital) across all closed trades. */
export function cumulativeRealised(
  positions: Position[],
  config: RiskConfig
): number {
  let pnlFraction = 0;
  for (const p of positions) {
    if (p.status !== "closed") continue;
    pnlFraction += closedPnlFraction(p, config);
  }
  return pnlFraction;
}

/** Unrealised P&L on every open position (fraction of capital). */
export function unrealisedFraction(
  openPositions: Position[],
  quotes: Record<string, PairQuote>,
  config: RiskConfig
): number {
  let acc = 0;
  for (const p of openPositions) {
    const q = quotes[p.pairId];
    if (!q) continue;
    acc += positionPnl(p, q) * config.perPairNotional;
  }
  return acc;
}

/** Total NAV: capital + realised + unrealised. */
export function currentNav(
  allPositions: Position[],
  quotes: Record<string, PairQuote>,
  config: RiskConfig
): number {
  const open = allPositions.filter((p) => p.status === "open");
  const realised = cumulativeRealised(allPositions, config) * config.capital;
  const unrealised = unrealisedFraction(open, quotes, config) * config.capital;
  return config.capital + realised + unrealised;
}

/** Per-pair P&L as a fraction of capital (signed). */
export function perPairLossFraction(
  position: Position,
  quote: PairQuote | undefined,
  config: RiskConfig
): number {
  if (!quote) return 0;
  return positionPnl(position, quote) * config.perPairNotional;
}

function closedPnlFraction(p: Position, config: RiskConfig): number {
  if (p.exitBase == null || p.exitQuote == null) return 0;
  const baseRet = Math.log(p.exitBase / p.entryBase);
  const quoteRet = Math.log(p.exitQuote / p.entryQuote);
  const spreadRet = baseRet - p.hedgeRatio * quoteRet;
  const sign = p.side === "long_spread" ? 1 : -1;
  return sign * spreadRet * config.perPairNotional;
}

// -- Limit checks -----------------------------------------------------------

export type EntryGate = {
  allowed: boolean;
  reason?: string;
};

export function canEnter(
  allPositions: Position[],
  config: RiskConfig
): EntryGate {
  const kill = getKillSwitchState();
  if (kill.active) {
    return {
      allowed: false,
      reason: `Kill switch active (${kill.reason ?? "manual"})`,
    };
  }
  const daily = dailyRealised(allPositions, config);
  if (daily <= -config.maxLossDaily) {
    return {
      allowed: false,
      reason: `일일 손실 한도 도달 (${(daily * 100).toFixed(2)}%)`,
    };
  }
  return { allowed: true };
}

/** Pairs that have breached the per-pair stop -- caller forces close. */
export function pairsBreachingStop(
  open: Position[],
  quotes: Record<string, PairQuote>,
  config: RiskConfig
): Position[] {
  const out: Position[] = [];
  for (const p of open) {
    const loss = perPairLossFraction(p, quotes[p.pairId], config);
    if (loss <= -config.maxLossPerPair) out.push(p);
  }
  return out;
}
