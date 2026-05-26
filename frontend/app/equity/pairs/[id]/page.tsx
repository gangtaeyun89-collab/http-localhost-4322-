import { AppShell } from "@/components/layout/AppShell";
import { KPIBar } from "@/components/pair/KPIBar";
import { Panel } from "@/components/pair/Panel";
import { CumReturnsChart } from "@/components/pair/CumReturnsChart";
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

function PairHeader({
  base,
  quote,
  timeframe,
  periods,
  source,
}: {
  base: string;
  quote: string;
  timeframe: string;
  periods: number;
  source: "api" | "mock";
}) {
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
        <span>
          <span className="num">{periods}</span> periods
        </span>
        <span className="text-text-faint">|</span>
        <span>{timeframe}</span>
        <span className="text-text-faint">|</span>
        <SourceBadge source={source} />
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
