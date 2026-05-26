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
