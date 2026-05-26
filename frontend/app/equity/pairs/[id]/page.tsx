import { AppShell } from "@/components/layout/AppShell";
import { KPIBar } from "@/components/pair/KPIBar";
import { Panel } from "@/components/pair/Panel";
import { CumReturnsChart } from "@/components/pair/CumReturnsChart";
import { ZScoreChart } from "@/components/pair/ZScoreChart";
import { CorrelationChart } from "@/components/pair/CorrelationChart";
import { CopulaChart } from "@/components/pair/CopulaChart";
import { VECMTable } from "@/components/pair/VECMTable";
import { ImpulseChart } from "@/components/pair/ImpulseChart";
import { mockPairAnalysis } from "@/lib/mock";
import { t } from "@/lib/i18n";

// Dense single-page workbench for one cointegrated pair, modelled on the
// reference screenshots:
//   - top: KPI strip (cointegration flags + Hurst, half-life, corr, ...)
//   - middle 2x2: cumulative returns | spread/z-score
//                 copula scatter      | rolling correlation
//   - bottom: VECM lag table + ECM impulse-response

export default function EquityPairAnalysisPage({
  params,
}: {
  params: { id: string };
}) {
  const data = mockPairAnalysis(params.id);
  const { kpis } = data;

  return (
    <AppShell market="equity">
      <PairHeader base={kpis.base} quote={kpis.quote} />
      <KPIBar kpis={kpis} />

      <div className="grid grid-cols-1 gap-px bg-border-subtle p-px lg:grid-cols-2">
        <Panel
          title={`${t("section.cumReturns")} · ${kpis.base} / ${kpis.quote}`}
          hint="normalised"
        >
          <CumReturnsChart
            data={data.cumReturns}
            base={kpis.base}
            quote={kpis.quote}
          />
        </Panel>
        <Panel title={t("section.spreadZscore")} hint="rolling · static">
          <ZScoreChart data={data.zscore} />
        </Panel>
        <Panel title={t("section.copula")} hint="prices · 5% boundary">
          <CopulaChart data={data.scatter} />
        </Panel>
        <Panel title={t("section.correlation")} hint="ρ window">
          <CorrelationChart data={data.correlation} />
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-px bg-border-subtle p-px lg:grid-cols-[1fr_1fr]">
        <Panel title={t("section.vecm")} hint="p < 0.05 = significant">
          <VECMTable rows={data.vecm} base={kpis.base} quote={kpis.quote} />
        </Panel>
        <Panel title={t("section.ecmImpulse")} hint="unit shock at t=0">
          <ImpulseChart data={data.impulse} />
        </Panel>
      </div>
    </AppShell>
  );
}

function PairHeader({ base, quote }: { base: string; quote: string }) {
  return (
    <div className="flex items-center justify-between border-b border-border-subtle bg-bg-panel px-4 py-2">
      <div className="flex items-center gap-3">
        <div className="text-xs uppercase tracking-widest text-text-muted">
          pair
        </div>
        <div className="flex items-center gap-2">
          <span className="num text-base font-semibold text-accent-cyan">
            {base}
          </span>
          <span className="text-text-muted">/</span>
          <span className="num text-base font-semibold text-accent-magenta">
            {quote}
          </span>
        </div>
      </div>
      <div className="flex items-center gap-3 text-2xs uppercase tracking-widest text-text-muted">
        <span>SMART · USD</span>
        <span className="text-text-faint">|</span>
        <span>365 periods</span>
        <span className="text-text-faint">|</span>
        <span>Daily</span>
      </div>
    </div>
  );
}
