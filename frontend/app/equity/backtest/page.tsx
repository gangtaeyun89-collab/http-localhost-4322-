import { AppShell } from "@/components/layout/AppShell";
import { BacktestWorkbench } from "@/components/backtest/BacktestWorkbench";
import { fetchPairList } from "@/lib/api";
import { mockPairList, type PairListRow } from "@/lib/mock";
import { cn } from "@/lib/utils";

// Walk-forward backtest page. SSR fetches the screened pair list (so the
// form has something to select from), then the client component handles
// form submit -> POST /api/backtest -> render results.

async function loadPairs(): Promise<{
  pairs: PairListRow[];
  source: "csv" | "synthetic" | "mock";
}> {
  try {
    const data = await fetchPairList("equity", 50);
    return { pairs: data.rows, source: data.source };
  } catch {
    return { pairs: mockPairList, source: "mock" };
  }
}

export default async function EquityBacktestPage() {
  const { pairs, source } = await loadPairs();

  return (
    <AppShell market="equity">
      <PageHeader source={source} count={pairs.length} />
      <BacktestWorkbench pairs={pairs} />
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
          백테스트 / Backtest
        </div>
        <span className="text-text-faint">/</span>
        <span className="text-xs text-text-secondary">
          walk-forward OOS · {count} 페어 선택 가능
        </span>
        <span className="text-text-faint">·</span>
        <SourceTag source={source} />
      </div>
      <div className="text-2xs uppercase tracking-widest text-text-muted">
        train Sharpe vs test Sharpe · honest OOS
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
