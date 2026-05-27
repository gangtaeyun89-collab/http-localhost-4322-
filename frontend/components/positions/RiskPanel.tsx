"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, Power, RefreshCcw, Settings2 } from "lucide-react";
import type { PairQuote } from "@/lib/api";
import { type Position } from "@/lib/positions";
import {
  cumulativeRealised,
  currentNav,
  dailyRealised,
  DEFAULT_RISK,
  getKillSwitchState,
  getRiskConfig,
  resetKillSwitch,
  setRiskConfig,
  unrealisedFraction,
  type RiskConfig,
} from "@/lib/risk";
import { cn, fmtPct } from "@/lib/utils";

// Capital + limit controls and the live risk dial. Subscribes to the
// 'statarb.risk.update' event so any other component editing limits or
// flipping the kill switch updates this panel immediately.

export function RiskPanel({
  positions,
  quotes,
}: {
  positions: Position[];
  quotes: Record<string, PairQuote>;
}) {
  const [config, setConfig] = useState<RiskConfig>(DEFAULT_RISK);
  const [kill, setKill] = useState(getKillSwitchState());
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    const refresh = () => {
      setConfig(getRiskConfig());
      setKill(getKillSwitchState());
    };
    refresh();
    window.addEventListener("storage", refresh);
    window.addEventListener("statarb.risk.update", refresh);
    return () => {
      window.removeEventListener("storage", refresh);
      window.removeEventListener("statarb.risk.update", refresh);
    };
  }, []);

  const open = positions.filter((p) => p.status === "open");
  const realisedToday = dailyRealised(positions, config);
  const realisedAll = cumulativeRealised(positions, config);
  const unrealised = unrealisedFraction(open, quotes, config);
  const nav = currentNav(positions, quotes, config);
  const drawdown = nav / config.capital - 1; // negative when underwater vs starting capital

  // Limit utilisation ratios -- values in [0, 1] feed the progress bars.
  const dailyUtil = Math.min(
    1,
    realisedToday < 0 ? -realisedToday / config.maxLossDaily : 0
  );
  const totalUtil = Math.min(
    1,
    drawdown < 0 ? -drawdown / config.maxDrawdownTotal : 0
  );

  return (
    <div className="flex flex-col gap-2 border-b border-border-subtle bg-bg-panel px-4 py-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3 text-2xs uppercase tracking-widest text-text-muted">
          <span>
            capital{" "}
            <span className="num text-text-primary">
              ${(config.capital).toLocaleString()}
            </span>
          </span>
          <span>
            NAV{" "}
            <span
              className={cn(
                "num font-semibold",
                drawdown >= 0 ? "text-accent-green" : "text-accent-red"
              )}
            >
              ${nav.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </span>{" "}
            ({fmtPct(drawdown, 2, true)})
          </span>
          <span>
            realised{" "}
            <span
              className={cn(
                "num",
                realisedAll >= 0 ? "text-accent-green" : "text-accent-red"
              )}
            >
              {fmtPct(realisedAll, 2, true)}
            </span>
          </span>
          <span>
            unrealised{" "}
            <span
              className={cn(
                "num",
                unrealised >= 0 ? "text-accent-green" : "text-accent-red"
              )}
            >
              {fmtPct(unrealised, 2, true)}
            </span>
          </span>
        </div>
        <div className="flex items-center gap-2">
          {kill.active && (
            <span className="flex items-center gap-1 rounded bg-accent-red/20 px-2 py-0.5 text-2xs font-semibold uppercase tracking-widest text-accent-red">
              <Power className="h-3 w-3" />
              KILL SWITCH
            </span>
          )}
          <button
            onClick={() => setEditing((v) => !v)}
            className="flex items-center gap-1 rounded border border-border-subtle px-2 py-0.5 text-2xs uppercase tracking-widest text-text-secondary hover:bg-bg-elevated"
          >
            <Settings2 className="h-3 w-3" />
            {editing ? "닫기" : "설정"}
          </button>
        </div>
      </div>

      {/* Limit-utilisation bars */}
      <div className="grid grid-cols-1 gap-2 md:grid-cols-2">
        <LimitBar
          label={`일일 손실 한도 (${(config.maxLossDaily * 100).toFixed(1)}%)`}
          util={dailyUtil}
          current={realisedToday}
          limit={config.maxLossDaily}
          tripped={realisedToday <= -config.maxLossDaily}
          trippedNote="신규 진입 정지"
        />
        <LimitBar
          label={`전체 drawdown (${(config.maxDrawdownTotal * 100).toFixed(1)}%)`}
          util={totalUtil}
          current={drawdown}
          limit={config.maxDrawdownTotal}
          tripped={drawdown <= -config.maxDrawdownTotal}
          trippedNote="KILL SWITCH"
        />
      </div>

      {/* Kill switch banner */}
      {kill.active && (
        <div className="flex items-start justify-between gap-3 rounded border border-accent-red/40 bg-accent-red/10 px-3 py-2">
          <div className="flex items-start gap-2">
            <AlertTriangle className="h-4 w-4 shrink-0 text-accent-red" />
            <div className="flex flex-col gap-0.5">
              <div className="text-xs font-semibold text-accent-red">
                Kill switch 발동: {kill.reason ?? "manual"}
              </div>
              <div className="text-2xs text-text-secondary">
                NAV at trip:{" "}
                <span className="num">
                  ${(kill.navAtTrip ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </span>{" "}
                · peak:{" "}
                <span className="num">
                  ${(kill.peakNav ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </span>{" "}
                · 모든 신규 진입 차단됨. 수동 reset 필요.
              </div>
            </div>
          </div>
          <button
            onClick={resetKillSwitch}
            className="flex items-center gap-1 rounded border border-accent-yellow/40 bg-accent-yellow/10 px-2 py-1 text-2xs uppercase tracking-widest text-accent-yellow hover:bg-accent-yellow/20"
          >
            <RefreshCcw className="h-3 w-3" />
            reset
          </button>
        </div>
      )}

      {editing && <Editor config={config} onApply={(c) => setRiskConfig(c)} />}
    </div>
  );
}

function LimitBar({
  label,
  util,
  current,
  limit,
  tripped,
  trippedNote,
}: {
  label: string;
  util: number; // 0..1
  current: number;
  limit: number;
  tripped: boolean;
  trippedNote: string;
}) {
  const pct = Math.max(2, Math.round(util * 100));
  const colour =
    tripped
      ? "bg-accent-red"
      : util >= 0.66
      ? "bg-accent-yellow"
      : "bg-accent-cyan";
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-2xs">
        <span className="uppercase tracking-widest text-text-muted">{label}</span>
        <span className="num text-text-secondary">
          {fmtPct(current, 2, true)} / {fmtPct(-limit, 2, true)}
          {tripped && (
            <span className="ml-2 text-accent-red font-semibold">
              · {trippedNote}
            </span>
          )}
        </span>
      </div>
      <div className="relative h-1 w-full rounded bg-bg-elevated">
        <div
          className={cn("absolute left-0 top-0 h-1 rounded", colour)}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function Editor({
  config,
  onApply,
}: {
  config: RiskConfig;
  onApply: (c: Partial<RiskConfig>) => void;
}) {
  const [draft, setDraft] = useState(config);
  return (
    <div className="flex flex-wrap items-end gap-3 border-t border-border-subtle pt-2">
      <Field
        label="자본 / Capital ($)"
        value={draft.capital}
        step={1000}
        onChange={(v) => setDraft({ ...draft, capital: Math.max(1, v) })}
      />
      <Field
        label="페어당 노출 (%)"
        value={draft.perPairNotional * 100}
        step={0.5}
        onChange={(v) =>
          setDraft({
            ...draft,
            perPairNotional: Math.max(0.001, Math.min(1, v / 100)),
          })
        }
      />
      <Field
        label="페어당 max loss (%)"
        value={draft.maxLossPerPair * 100}
        step={0.1}
        onChange={(v) =>
          setDraft({
            ...draft,
            maxLossPerPair: Math.max(0.0001, Math.min(1, v / 100)),
          })
        }
      />
      <Field
        label="일일 max loss (%)"
        value={draft.maxLossDaily * 100}
        step={0.1}
        onChange={(v) =>
          setDraft({
            ...draft,
            maxLossDaily: Math.max(0.0001, Math.min(1, v / 100)),
          })
        }
      />
      <Field
        label="전체 drawdown (%)"
        value={draft.maxDrawdownTotal * 100}
        step={0.5}
        onChange={(v) =>
          setDraft({
            ...draft,
            maxDrawdownTotal: Math.max(0.0001, Math.min(1, v / 100)),
          })
        }
      />
      <button
        onClick={() => onApply(draft)}
        className="rounded border border-accent-cyan/40 bg-accent-cyan/10 px-3 py-1.5 text-2xs uppercase tracking-widest text-accent-cyan hover:bg-accent-cyan/20"
      >
        적용
      </button>
    </div>
  );
}

function Field({
  label,
  value,
  step,
  onChange,
}: {
  label: string;
  value: number;
  step: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="text-2xs uppercase tracking-widest text-text-muted">
        {label}
      </div>
      <input
        type="number"
        value={value}
        step={step}
        onChange={(e) => {
          const v = parseFloat(e.target.value);
          if (Number.isFinite(v)) onChange(v);
        }}
        className="num w-32 border border-border-subtle bg-bg-card px-2 py-1.5 text-xs text-text-primary focus:border-accent-cyan focus:outline-none"
      />
    </div>
  );
}
