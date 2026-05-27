import { AppShell } from "@/components/layout/AppShell";
import { AlertHistory } from "@/components/dashboard/AlertHistory";
import { PairsWatchTable } from "@/components/dashboard/PairsWatchTable";
import { fetchPairList } from "@/lib/api";
import { mockPairList, type PairListRow } from "@/lib/mock";
import { cn } from "@/lib/utils";

// Live multi-pair watch screen -- the "trading desk" view. SSR fetches the
// pair list once (cointegration screen); the client component then polls
// /api/pairs/quotes in bulk every few seconds and re-sorts the table by
// |z-score| so the actionable rows surface to the top automatically.

async function loadList(): Promise<{
  rows: PairListRow[];
  source: "csv" | "synthetic" | "mock";
}> {
  try {
    const data = await fetchPairList("equity", 30);
    return { rows: data.rows, source: data.source };
  } catch {
    return { rows: mockPairList, source: "mock" };
  }
}

export default async function EquityDashboardPage() {
  const { rows, source } = await loadList();

  return (
    <AppShell market="equity">
      <PageHeader source={source} count={rows.length} />
      {rows.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="grid grid-cols-1 xl:grid-cols-[1fr_280px]">
          <PairsWatchTable seedRows={rows} interval={5000} />
          <div className="hidden xl:block">
            <AlertHistory />
          </div>
        </div>
      )}
    </AppShell>
  );
}

function PageHeader({
  source,
  count,
}: {
  source: "csv" | "synthetic" | "mock";
  count: number;
}) {
  return (
    <div className="flex items-center justify-between border-b border-border-subtle bg-bg-panel px-4 py-2">
      <div className="flex items-center gap-3">
        <div className="text-xs uppercase tracking-widest text-text-muted">
          대시보드 / Dashboard
        </div>
        <span className="text-text-faint">/</span>
        <span className="text-xs text-text-secondary">
          상위 {count} 페어 실시간 감시
        </span>
        <span className="text-text-faint">·</span>
        <SourceTag source={source} />
      </div>
      <div className="text-2xs uppercase tracking-widest text-text-muted">
        polling · 5s
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
        공적분 페어가 발견되지 않았습니다.
      </div>
      <div className="mt-2 text-xs text-text-muted">
        scripts/refresh_data.sh 를 실행해 데이터를 받거나 임계값을
        조정하세요.
      </div>
    </div>
  );
}
