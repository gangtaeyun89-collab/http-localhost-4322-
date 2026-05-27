import Link from "next/link";
import { AppShell } from "@/components/layout/AppShell";
import { AlertHistory } from "@/components/dashboard/AlertHistory";
import { SectorGrid } from "@/components/dashboard/SectorGrid";
import { fetchSectors } from "@/lib/api";
import type { SectorSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

// Sector-grid dashboard. Each card is one homogeneous industry basket with
// its top-3 cointegrated pairs; click a card to drop into the sector's
// detail page. The single-table watch view that used to live here moved
// to /equity/pairs.

async function loadSectors(): Promise<{
  sectors: SectorSummary[];
  source: "csv" | "synthetic" | "mock";
}> {
  try {
    const data = await fetchSectors();
    return { sectors: data.sectors, source: data.source };
  } catch {
    return { sectors: [], source: "mock" };
  }
}

export default async function EquityDashboardPage() {
  const { sectors, source } = await loadSectors();

  const totals = sectors.reduce(
    (acc, s) => {
      acc.tickers += s.tickerCount;
      acc.pairs += s.pairCount;
      if (s.pairCount > 0) acc.active++;
      return acc;
    },
    { tickers: 0, pairs: 0, active: 0 }
  );

  return (
    <AppShell market="equity">
      <PageHeader source={source} totals={totals} sectorCount={sectors.length} />
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_280px]">
        <div>
          {sectors.length === 0 ? (
            <EmptyState />
          ) : (
            <SectorGrid sectors={sectors} interval={5000} />
          )}
        </div>
        <div className="hidden xl:block">
          <AlertHistory />
        </div>
      </div>
    </AppShell>
  );
}

function PageHeader({
  source,
  totals,
  sectorCount,
}: {
  source: "csv" | "synthetic" | "mock";
  totals: { tickers: number; pairs: number; active: number };
  sectorCount: number;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-subtle bg-bg-panel px-4 py-2">
      <div className="flex flex-wrap items-center gap-3">
        <div className="text-xs uppercase tracking-widest text-text-muted">
          대시보드 / Dashboard
        </div>
        <span className="text-text-faint">·</span>
        <span className="text-xs text-text-secondary">
          섹터별 공적분 페어 · 상위 3개 미리보기
        </span>
        <span className="text-text-faint">·</span>
        <SourceTag source={source} />
      </div>
      <div className="flex items-center gap-3 text-2xs uppercase tracking-widest text-text-muted">
        <span>
          sectors{" "}
          <span className="num text-text-primary">{sectorCount}</span>
        </span>
        <span>
          active{" "}
          <span className="num text-accent-green">{totals.active}</span>
        </span>
        <span>
          tickers <span className="num text-text-primary">{totals.tickers}</span>
        </span>
        <span>
          pairs <span className="num text-text-primary">{totals.pairs}</span>
        </span>
        <Link
          href="/equity/pairs"
          className="rounded border border-border-subtle px-2 py-0.5 text-text-secondary hover:bg-bg-elevated"
        >
          전체 페어 표
        </Link>
      </div>
    </div>
  );
}

function SourceTag({ source }: { source: "csv" | "synthetic" | "mock" }) {
  const colour =
    source === "csv"
      ? "bg-accent-green/15 text-accent-green"
      : source === "synthetic"
      ? "bg-accent-purple/15 text-accent-purple"
      : "bg-accent-yellow/15 text-accent-yellow";
  return (
    <span
      className={cn(
        "rounded px-1.5 py-0.5 text-2xs uppercase tracking-widest",
        colour
      )}
    >
      {source}
    </span>
  );
}

function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 py-24 text-center">
      <div className="text-sm text-text-secondary">
        섹터 데이터를 불러올 수 없습니다.
      </div>
      <div className="mt-2 text-xs text-text-muted">
        scripts/refresh_data.sh 를 실행해 데이터를 받으세요.
      </div>
    </div>
  );
}
