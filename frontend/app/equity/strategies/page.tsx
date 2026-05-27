import { AppShell } from "@/components/layout/AppShell";
import { DiscoverWorkbench } from "@/components/discover/DiscoverWorkbench";
import { fetchSectors } from "@/lib/api";
import type { SectorSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

// Pair discovery workbench. SSR fetches the sector catalogue so the
// form can render the basket picker even when the backend later goes
// away (the button just won't submit). The client workbench handles
// form submit -> POST /api/discover -> render results.

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

export default async function EquityStrategiesPage() {
  const { sectors, source } = await loadSectors();

  return (
    <AppShell market="equity">
      <PageHeader source={source} count={sectors.length} />
      <DiscoverWorkbench sectors={sectors} />
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
          페어 발견 / Discovery
        </div>
        <span className="text-text-faint">·</span>
        <span className="text-xs text-text-secondary">
          산업 바스켓 → cointegration → FDR
        </span>
        <span className="text-text-faint">·</span>
        <SourceTag source={source} />
      </div>
      <div className="text-2xs uppercase tracking-widest text-text-muted">
        {count} basket(s) loaded
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
