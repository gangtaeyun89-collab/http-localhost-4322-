import { AppShell } from "@/components/layout/AppShell";
import { PositionsWorkbench } from "@/components/positions/PositionsWorkbench";

// Paper-paper journal. Stored entirely in the browser; no IBKR orders
// are placed. Wire to real fills in Phase 4 by swapping the lib/positions
// helpers for broker-backed ones.

export default function EquityPositionsPage() {
  return (
    <AppShell market="equity">
      <PageHeader />
      <PositionsWorkbench />
    </AppShell>
  );
}

function PageHeader() {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border-subtle bg-bg-panel px-4 py-2">
      <div className="flex items-center gap-3">
        <div className="text-xs uppercase tracking-widest text-text-muted">
          포지션 / Positions
        </div>
        <span className="text-text-faint">·</span>
        <span className="text-xs text-text-secondary">
          가상 진입 추적 · 자동 청산 · risk limits · 회계 일지
        </span>
      </div>
      <div className="text-2xs uppercase tracking-widest text-text-faint">
        paper-paper (no broker order)
      </div>
    </div>
  );
}
