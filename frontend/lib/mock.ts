// Mock data shaped exactly like what the FastAPI backend will return -- this
// lets the dashboards work end-to-end before the API is wired up. Replace the
// loaders with fetch() calls when the backend is ready; component code does
// not need to change.

export type PairKPIs = {
  base: string;
  quote: string;
  cointJn: boolean;
  cointEG: boolean;
  hurst: number;
  halfLife: number;
  corr: number;
  hedgeRatio: number;
  ltBeta: number;
  mdd: number;
  returns: number;
  sharpe: number;
  periods: number;
  timeframe: string;
  market: "equity" | "crypto";
};

export type SeriesPoint = { t: string; base: number; quote: number };
export type ZScorePoint = { t: string; spread: number; zscore: number };
export type CorrPoint = { t: string; corr: number };
export type ScatterPoint = { x: number; y: number };

export type VECMRow = {
  term: string;
  baseCoef: number;
  basePValue: number;
  quoteCoef: number;
  quotePValue: number;
};

export type ImpulsePoint = {
  step: number;
  base: number;
  quote: number;
};

export type PairAnalysis = {
  kpis: PairKPIs;
  cumReturns: SeriesPoint[];
  zscore: ZScorePoint[];
  correlation: CorrPoint[];
  scatter: ScatterPoint[];
  vecm: VECMRow[];
  impulse: ImpulsePoint[];
};

// Deterministic-ish RNG so the mock looks the same on every render.
function mulberry32(seed: number) {
  let a = seed;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function mockSeries(n: number, seed: number): SeriesPoint[] {
  const rand = mulberry32(seed);
  const out: SeriesPoint[] = [];
  let b = 100;
  let q = 100;
  const start = new Date("2024-01-01").getTime();
  const day = 86_400_000;
  for (let i = 0; i < n; i++) {
    const shock = (rand() - 0.5) * 0.02;
    b *= 1 + shock + (rand() - 0.5) * 0.01;
    q *= 1 + shock * 0.85 + (rand() - 0.5) * 0.012;
    out.push({
      t: new Date(start + i * day).toISOString().slice(0, 10),
      base: +b.toFixed(2),
      quote: +q.toFixed(2),
    });
  }
  return out;
}

function mockZ(n: number, seed: number): ZScorePoint[] {
  const rand = mulberry32(seed);
  const out: ZScorePoint[] = [];
  let s = 0;
  const start = new Date("2024-01-01").getTime();
  for (let i = 0; i < n; i++) {
    s = 0.92 * s + (rand() - 0.5) * 0.5;
    out.push({
      t: new Date(start + i * 86_400_000).toISOString().slice(0, 10),
      spread: +s.toFixed(3),
      zscore: +(s / 0.6).toFixed(3),
    });
  }
  return out;
}

function mockCorr(n: number, seed: number): CorrPoint[] {
  const rand = mulberry32(seed);
  const out: CorrPoint[] = [];
  let c = 0.85;
  const start = new Date("2024-01-01").getTime();
  for (let i = 0; i < n; i++) {
    c = Math.max(0.1, Math.min(0.99, c + (rand() - 0.5) * 0.05));
    out.push({
      t: new Date(start + i * 86_400_000).toISOString().slice(0, 10),
      corr: +c.toFixed(3),
    });
  }
  return out;
}

function mockScatter(n: number, seed: number): ScatterPoint[] {
  const rand = mulberry32(seed);
  const out: ScatterPoint[] = [];
  for (let i = 0; i < n; i++) {
    const x = rand();
    const y = Math.max(0, Math.min(1, x + (rand() - 0.5) * 0.4));
    out.push({ x: +x.toFixed(3), y: +y.toFixed(3) });
  }
  return out;
}

function mockVECM(): VECMRow[] {
  return [
    { term: "lag1 (β₁)", baseCoef: 0.16, basePValue: 0.0, quoteCoef: 0.02, quotePValue: 0.77 },
    { term: "lag2 (β₂)", baseCoef: -0.07, basePValue: 0.21, quoteCoef: -0.06, quotePValue: 0.36 },
    { term: "lag1 (β₁)", baseCoef: -0.04, basePValue: 0.65, quoteCoef: 0.03, quotePValue: 0.69 },
    { term: "lag2 (β₂)", baseCoef: 0.13, basePValue: 0.12, quoteCoef: 0.06, quotePValue: 0.43 },
    { term: "spread lag1 (γ)", baseCoef: -0.02, basePValue: 0.54, quoteCoef: -0.08, quotePValue: 0.0 },
  ];
}

function mockImpulse(): ImpulsePoint[] {
  // Resembles the screenshot: both legs spike at t-1, then recover toward
  // -0.10 / -0.18 by t+9.
  return [
    { step: -2, base: 0.0, quote: 0.0 },
    { step: -1, base: -0.55, quote: -0.55 },
    { step: 0, base: 0.08, quote: -0.5 },
    { step: 1, base: 0.06, quote: -0.42 },
    { step: 2, base: 0.05, quote: -0.32 },
    { step: 3, base: 0.04, quote: -0.25 },
    { step: 4, base: 0.03, quote: -0.2 },
    { step: 5, base: 0.02, quote: -0.16 },
    { step: 6, base: 0.01, quote: -0.14 },
    { step: 7, base: 0.0, quote: -0.12 },
    { step: 8, base: 0.0, quote: -0.11 },
    { step: 9, base: 0.0, quote: -0.1 },
  ];
}

export function mockPairAnalysis(id: string): PairAnalysis {
  // Parse "BASE-QUOTE" out of the URL slug, default to EQR-MAA (our best
  // real-data pair from the discovery run).
  const [base, quote] = id.split("-").length === 2 ? id.split("-") : ["EQR", "MAA"];
  const seed = id.split("").reduce((a, c) => a + c.charCodeAt(0), 0);
  const n = 365;
  return {
    kpis: {
      base,
      quote,
      cointJn: true,
      cointEG: true,
      hurst: 1.08,
      halfLife: 7.5,
      corr: 0.805,
      hedgeRatio: 0.91,
      ltBeta: 0.89,
      mdd: -0.13,
      returns: 0.073,
      sharpe: 0.25,
      periods: n,
      timeframe: "Daily",
      market: "equity",
    },
    cumReturns: mockSeries(n, seed),
    zscore: mockZ(n, seed + 1),
    correlation: mockCorr(n, seed + 2),
    scatter: mockScatter(500, seed + 3),
    vecm: mockVECM(),
    impulse: mockImpulse(),
  };
}

export type PairListRow = {
  id: string;
  base: string;
  quote: string;
  market: "equity" | "crypto";
  industry?: string;
  cointPValue: number;
  halfLife: number;
  oosSharpe: number;
  trainSharpe: number;
  corr: number;
};

export const mockPairList: PairListRow[] = [
  { id: "EQR-MAA", base: "EQR", quote: "MAA", market: "equity", industry: "REIT (아파트)", cointPValue: 0.012, halfLife: 28.4, oosSharpe: 1.45, trainSharpe: 1.21, corr: 0.91 },
  { id: "BAC-COF", base: "BAC", quote: "COF", market: "equity", industry: "은행", cointPValue: 0.018, halfLife: 32.1, oosSharpe: 0.99, trainSharpe: 0.84, corr: 0.78 },
  { id: "AMH-INVH", base: "AMH", quote: "INVH", market: "equity", industry: "REIT (단독주택)", cointPValue: 0.022, halfLife: 36.7, oosSharpe: 0.96, trainSharpe: 0.81, corr: 0.88 },
  { id: "ITW-PH", base: "ITW", quote: "PH", market: "equity", industry: "기계", cointPValue: 0.031, halfLife: 41.2, oosSharpe: 0.85, trainSharpe: 0.72, corr: 0.74 },
  { id: "USB-ZION", base: "USB", quote: "ZION", market: "equity", industry: "은행", cointPValue: 0.041, halfLife: 38.5, oosSharpe: 0.84, trainSharpe: 0.69, corr: 0.71 },
  { id: "MTH-NVR", base: "MTH", quote: "NVR", market: "equity", industry: "주택건설", cointPValue: 0.048, halfLife: 44.8, oosSharpe: 0.78, trainSharpe: 0.63, corr: 0.82 },
  { id: "MAA-UDR", base: "MAA", quote: "UDR", market: "equity", industry: "REIT (아파트)", cointPValue: 0.052, halfLife: 31.9, oosSharpe: 0.75, trainSharpe: 0.61, corr: 0.85 },
  { id: "GS-WFC", base: "GS", quote: "WFC", market: "equity", industry: "은행", cointPValue: 0.061, halfLife: 47.3, oosSharpe: 0.72, trainSharpe: 0.55, corr: 0.69 },
];
