import { AppShell } from "@/components/layout/AppShell";
import { KPIBar } from "@/components/pair/KPIBar";
import { LivePulse } from "@/components/pair/LivePulse";
import { Panel } from "@/components/pair/Panel";
import { CumReturnsChart } from "@/components/pair/CumReturnsChart";
import { LiveZScoreChart } from "@/components/pair/LiveZScoreChart";
import { ZScoreChart } from "@/components/pair/ZScoreChart";
import { CorrelationChart } from "@/components/pair/CorrelationChart";
import { CopulaChart } from "@/components/pair/CopulaChart";
import { VECMTable } from "@/components/pair/VECMTable";
import { ImpulseChart } from "@/components/pair/ImpulseChart";
import { fetchPairAnalysis } from "@/lib/api";
import { mockPairAnalysis, type PairAnalysis } from "@/lib/mock";
import { t } from "@/lib/i18n";

// Dense single-page workbench for one cointegrated pair, modelled on the
// reference screenshots. Fetches real analytics from the FastAPI backend;
// silently falls back to the mock fixtures when the backend is unreachable
// so the page never breaks during development.

async function loadAnalysis(id: string): Promise<{
  data: PairAnalysis;
  source: "api" | "mock";
}> {
  try {
    const data = await fetchPairAnalysis(id, "equity");
    return { data, source: "api" };
  } catch {
    return { data: mockPairAnalysis(id), source: "mock" };
  }
}

export default async function EquityPairAnalysisPage({
  params,
}: {
  params: { id: string };
}) {
  const { data, source } = await loadAnalysis(params.id);
  const { kpis } = data;

  return (
    <AppShell market="equity">
      <PairHeader
        base={kpis.base}
        quote={kpis.quote}
        timeframe={kpis.timeframe}
        periods={kpis.periods}
        source={source}
        pairId={params.id}
      />
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
        <Panel title={t("section.spreadZscore")} hint="rolling · live tick">
          {source === "api" ? (
            <LiveZScoreChart data={data.zscore} pairId={params.id} />
          ) : (
            <ZScoreChart data={data.zscore} />
          )}
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

function PairHeader({
  base,
  quote,
  timeframe,
  periods,
  source,
  pairId,
}: {
  base: string;
  quote: string;
  timeframe: string;
  periods: number;
  source: "api" | "mock";
  pairId: string;
}) {
  return (
    <div className="flex flex-col gap-2 border-b border-border-subtle bg-bg-panel px-4 py-2 lg:flex-row lg:items-center lg:justify-between">
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
        <span className="text-text-faint">|</span>
        <span className="text-2xs uppercase tracking-widest text-text-muted">
          SMART · USD
        </span>
        <span className="text-text-faint">|</span>
        <span className="text-2xs uppercase tracking-widest text-text-muted">
          <span className="num">{periods}</span> periods
        </span>
        <span className="text-text-faint">|</span>
        <span className="text-2xs uppercase tracking-widest text-text-muted">
          {timeframe}
        </span>
        <span className="text-text-faint">|</span>
        <SourceBadge source={source} />
      </div>
      <div className="flex items-center">
        {source === "api" && <LivePulse pairId={pairId} interval={5000} />}
      </div>
    </div>
  );
}

function SourceBadge({ source }: { source: "api" | "mock" }) {
  if (source === "api") {
    return (
      <span className="rounded bg-accent-green/15 px-1.5 py-0.5 text-accent-green">
        live
      </span>
    );
  }
  return (
    <span className="rounded bg-accent-yellow/15 px-1.5 py-0.5 text-accent-yellow">
      mock
    </span>
  );
}
