// Typed fetch helpers for the FastAPI backend.
//
// In dev the browser hits /api/* and Next's rewrites() proxy forwards to the
// uvicorn process. Server components, however, run in Node and need an
// absolute URL -- they read API_URL (server-only) or fall back to
// 127.0.0.1:8000 for local development.

import type {
  PairAnalysis,
  PairListRow,
} from "@/lib/mock";

function serverBase(): string {
  return (
    process.env.API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://127.0.0.1:8000"
  );
}

async function getJSON<T>(path: string): Promise<T> {
  const base = serverBase();
  const url = path.startsWith("http") ? path : `${base}${path}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(
      `${path} -> ${res.status} ${res.statusText}: ${await res.text()}`
    );
  }
  return (await res.json()) as T;
}

export type PairListResponse = {
  rows: PairListRow[];
  n_tested: number;
  n_universe: number;
  source: "csv" | "synthetic";
};

export async function fetchPairList(
  market: "equity" | "crypto" = "equity",
  limit = 50
): Promise<PairListResponse> {
  return getJSON<PairListResponse>(
    `/api/pairs/list?market=${market}&limit=${limit}`
  );
}

export async function fetchPairAnalysis(
  id: string,
  market: "equity" | "crypto" = "equity"
): Promise<PairAnalysis> {
  return getJSON<PairAnalysis>(
    `/api/pairs/${encodeURIComponent(id)}/analysis?market=${market}`
  );
}

export type HealthResponse = {
  status: string;
  csv_dir: string;
  csv_available: boolean;
  ticker_count: number;
  asset_class: string;
};

export async function fetchHealth(): Promise<HealthResponse> {
  return getJSON<HealthResponse>("/api/health");
}

export type PairQuote = {
  base: string;
  quote: string;
  asOf: string;
  lastBar: { t: string; base: number; quote: number };
  lastZScore: number;
  lastSpread: number;
  lastReturn: { base: number; quote: number };
  halfLife: number;
  pvalue: number;
  signal: "flat" | "long_spread" | "short_spread";
  source: "csv" | "synthetic" | "error";
};

// Browser-side fetch -- hits the rewrites() proxy at /api/* so we never
// expose the FastAPI origin to the client. Server-side callers should go
// through fetchPairAnalysis instead.
export async function fetchPairQuoteBrowser(id: string): Promise<PairQuote> {
  const url = `/api/pairs/${encodeURIComponent(id)}/quote`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`${url} -> ${res.status}`);
  }
  return (await res.json()) as PairQuote;
}

export type PairQuoteBulk = {
  quotes: PairQuote[];
  asOf: string;
};

export async function fetchPairQuotesBrowser(
  ids: string[]
): Promise<PairQuoteBulk> {
  if (ids.length === 0) return { quotes: [], asOf: "" };
  const url = `/api/pairs/quotes?ids=${encodeURIComponent(ids.join(","))}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`${url} -> ${res.status}`);
  }
  return (await res.json()) as PairQuoteBulk;
}

// ---------------------------------------------------------------------------
// Backtest
// ---------------------------------------------------------------------------

export type BacktestRequest = {
  base: string;
  quote: string;
  train_size: number;
  test_size: number;
  asset_class: "equity" | "crypto";
  target_volatility: number;
  tune_lookback: boolean;
  hedge_method: "kalman" | "ols";
  entry_z: number;
  exit_z: number;
};

export type WindowReport = {
  train_start: string;
  train_end: string;
  test_start: string;
  test_end: string;
  train_sharpe: number;
  test_sharpe: number;
};

export type EquityPoint = {
  t: string;
  equity: number;
  netReturn: number;
  position: number;
};

export type BacktestStats = {
  sharpe: number;
  cagr: number;
  maxDrawdown: number;
  totalReturn: number;
  annualVolatility: number;
  winRate: number;
  nTrades: number;
  bars: number;
};

export type BacktestResult = {
  request: BacktestRequest;
  stats: BacktestStats;
  equity: EquityPoint[];
  windows: WindowReport[];
  meanTrainSharpe: number;
  meanTestSharpe: number;
  overfitGap: number;
  halfLife: number;
  pvalue: number;
  lookbackUsed: number;
  barsPerYear: number;
  source: "csv" | "synthetic";
};

export async function postBacktestBrowser(
  req: BacktestRequest
): Promise<BacktestResult> {
  const res = await fetch("/api/backtest", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`backtest -> ${res.status}: ${detail}`);
  }
  return (await res.json()) as BacktestResult;
}

// ---------------------------------------------------------------------------
// Sectors
// ---------------------------------------------------------------------------

export type SectorPair = {
  id: string;
  base: string;
  quote: string;
  cointPValue: number;
  halfLife: number;
  corr: number;
};

export type SectorSummary = {
  id: string;
  label: string;
  tickerCount: number;
  tickerCountTotal: number;
  pairCount: number;
  topPairs: SectorPair[];
};

export type SectorsResponse = {
  sectors: SectorSummary[];
  source: "csv" | "synthetic";
};

export type SectorDetail = {
  id: string;
  label: string;
  tickers: string[];
  tickerCount: number;
  tickerCountTotal: number;
  pairCount: number;
  pairs: SectorPair[];
  source: "csv" | "synthetic";
};

export async function fetchSectors(): Promise<SectorsResponse> {
  return getJSON<SectorsResponse>("/api/sectors");
}

export async function fetchSectorDetail(id: string): Promise<SectorDetail> {
  return getJSON<SectorDetail>(`/api/sectors/${encodeURIComponent(id)}`);
}

// ---------------------------------------------------------------------------
// Discovery
// ---------------------------------------------------------------------------

export type DiscoverRequest = {
  baskets: string[];
  fdr_level: number;
  distance_threshold: number;
  min_half_life: number;
  max_half_life: number;
};

export type DiscoveredPair = {
  id: string;
  base: string;
  quote: string;
  cointPValue: number;
  adfStatistic: number;
  halfLife: number;
  corr: number;
  basket: string | null;
  basketLabel: string | null;
};

export type DiscoverResult = {
  pairs: DiscoveredPair[];
  n_clusters: number;
  n_tested: number;
  n_universe: number;
  source: "csv" | "synthetic";
  baskets: { id: string; label: string }[];
};

export async function postDiscoverBrowser(
  req: DiscoverRequest
): Promise<DiscoverResult> {
  const res = await fetch("/api/discover", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`discover -> ${res.status}: ${detail}`);
  }
  return (await res.json()) as DiscoverResult;
}
