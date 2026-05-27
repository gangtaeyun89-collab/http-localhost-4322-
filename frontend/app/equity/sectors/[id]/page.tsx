import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft } from "lucide-react";
import { AppShell } from "@/components/layout/AppShell";
import { AlertHistory } from "@/components/dashboard/AlertHistory";
import { PairsWatchTable } from "@/components/dashboard/PairsWatchTable";
import { fetchSectorDetail } from "@/lib/api";
import type { PairListRow } from "@/lib/mock";
import { cn } from "@/lib/utils";

// Sector detail page: lists every cointegrated pair in one industry
// basket as a polling watch table, plus the ticker membership and the
// shared alert history panel. PairsWatchTable handles the polling +
// |z|-sorted re-ranking; we just feed it the seed rows for this sector.

export default async function SectorDetailPage({
  params,
}: {
  params: { id: string };
}) {
  let data;
  try {
    data = await fetchSectorDetail(params.id);
  } catch {
    notFound();
  }
  if (!data) notFound();

  // Adapt the sector pair rows to the PairListRow shape the watch table
  // expects. The dashboard already inherits the schema; this lets us
  // reuse the polling component as-is.
  const seedRows: PairListRow[] = data.pairs.map((p) => ({
    id: p.id,
    base: p.base,
    quote: p.quote,
    market: "equity",
    industry: data.label,
    cointPValue: p.cointPValue,
    halfLife: p.halfLife,
    oosSharpe: 0,
    trainSharpe: 0,
    corr: p.corr,
  }));

  return (
    <AppShell market="equity">
      <PageHeader
        label={data.label}
        tickerCount={data.tickerCount}
        tickerCountTotal={data.tickerCountTotal}
        pairCount={data.pairCount}
        source={data.source}
      />
      <TickerStrip tickers={data.tickers} />
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_280px]">
        <div>
          {seedRows.length === 0 ? (
            <EmptyState />
          ) : (
            <PairsWatchTable seedRows={seedRows} interval={5000} />
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
  label,
  tickerCount,
  tickerCountTotal,
  pairCount,
  source,
}: {
  label: string;
  tickerCount: number;
  tickerCountTotal: number;
  pairCount: number;
  source: "csv" | "synthetic";
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-subtle bg-bg-panel px-4 py-2">
      <div className="flex items-center gap-3">
        <Link
          href="/equity/dashboard"
          className="flex items-center gap-1.5 rounded border border-border-subtle px-2 py-0.5 text-2xs uppercase tracking-widest text-text-secondary hover:bg-bg-elevated"
        >
          <ArrowLeft className="h-3 w-3" />
          섹터 목록
        </Link>
        <span className="text-text-faint">/</span>
        <span className="text-xs font-semibold text-text-primary">{label}</span>
      </div>
      <div className="flex items-center gap-3 text-2xs uppercase tracking-widest text-text-muted">
        <span>
          tickers{" "}
          <span className="num text-text-primary">{tickerCount}</span>
          <span className="text-text-faint">/</span>
          <span className="num">{tickerCountTotal}</span>
        </span>
        <span>
          pairs <span className="num text-text-primary">{pairCount}</span>
        </span>
        <span
          className={cn(
            "rounded px-1.5 py-0.5",
            source === "csv"
              ? "bg-accent-green/15 text-accent-green"
              : "bg-accent-purple/15 text-accent-purple"
          )}
        >
          {source}
        </span>
      </div>
    </div>
  );
}

function TickerStrip({ tickers }: { tickers: string[] }) {
  if (tickers.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1 border-b border-border-subtle bg-bg-base/30 px-4 py-2">
      <span className="text-2xs uppercase tracking-widest text-text-muted">
        membership
      </span>
      <span className="text-text-faint">·</span>
      {tickers.map((t) => (
        <span
          key={t}
          className="num rounded bg-bg-elevated px-1.5 py-0.5 text-2xs text-text-secondary"
        >
          {t}
        </span>
      ))}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 py-24 text-center">
      <div className="text-sm text-text-secondary">
        이 섹터에는 공적분 페어가 없습니다.
      </div>
      <div className="mt-2 text-xs text-text-muted">
        필터를 완화하거나 데이터를 보강해 보세요.
      </div>
    </div>
  );
}
