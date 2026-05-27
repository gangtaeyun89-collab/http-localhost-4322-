import { Flag } from "lucide-react";
import { cn, fmtNum, fmtPct } from "@/lib/utils";
import { t } from "@/lib/i18n";
import type { PairKPIs } from "@/lib/mock";

// Bloomberg-style horizontal strip: 'label above, fat number below', colour
// only on values whose sign carries meaning (P&L, drawdown).
export function KPIBar({ kpis }: { kpis: PairKPIs }) {
  const items: {
    label: string;
    value: React.ReactNode;
    accent?: string;
  }[] = [
    {
      label: t("kpi.cointJn"),
      value: <FlagCell ok={kpis.cointJn} />,
    },
    {
      label: t("kpi.cointEG"),
      value: <FlagCell ok={kpis.cointEG} />,
    },
    {
      label: t("kpi.hurst"),
      value: <span className="num text-base">{fmtNum(kpis.hurst, 2)}</span>,
    },
    {
      label: t("kpi.halfLife"),
      value: <span className="num text-base">{fmtNum(kpis.halfLife, 1)}</span>,
    },
    {
      label: t("kpi.corr"),
      value: (
        <span className="num text-base text-accent-green">
          {fmtPct(kpis.corr, 1, false)}
        </span>
      ),
    },
    {
      label: t("kpi.hedgeRatio"),
      value: <span className="num text-base">{fmtNum(kpis.hedgeRatio, 2)}</span>,
    },
    {
      label: t("kpi.ltBeta"),
      value: <span className="num text-base">{fmtNum(kpis.ltBeta, 2)}</span>,
    },
    {
      label: t("kpi.mdd"),
      value: (
        <span className="num text-base text-accent-red">
          {fmtPct(kpis.mdd, 2, true)}
        </span>
      ),
    },
    {
      label: t("kpi.returns"),
      value: (
        <span
          className={cn(
            "num text-base",
            kpis.returns >= 0 ? "text-accent-green" : "text-accent-red"
          )}
        >
          {fmtPct(kpis.returns, 1, true)}
        </span>
      ),
    },
    {
      label: t("kpi.sharpe"),
      value: <span className="num text-base">{fmtNum(kpis.sharpe, 2)}</span>,
    },
    {
      label: t("kpi.periods"),
      value: <span className="num text-base">{kpis.periods}</span>,
    },
    {
      label: t("kpi.timeframe"),
      value: <span className="text-xs">{kpis.timeframe}</span>,
    },
  ];

  return (
    <div className="grid grid-cols-kpi gap-px border-y border-border-subtle bg-border-subtle">
      {items.map((item) => (
        <div
          key={item.label}
          className="flex flex-col gap-0.5 bg-bg-panel px-3 py-2"
        >
          <div className="text-2xs uppercase tracking-wide text-text-muted">
            {item.label}
          </div>
          <div className="leading-tight">{item.value}</div>
        </div>
      ))}
    </div>
  );
}

function FlagCell({ ok }: { ok: boolean }) {
  return (
    <div className="flex items-center gap-1.5">
      <Flag
        className={cn(
          "h-4 w-4",
          ok ? "text-accent-green" : "text-accent-red"
        )}
        fill="currentColor"
      />
      <span className="num text-xs text-text-secondary">
        {ok ? "PASS" : "FAIL"}
      </span>
    </div>
  );
}
