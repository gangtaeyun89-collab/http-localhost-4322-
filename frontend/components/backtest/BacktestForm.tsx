"use client";

import { useState } from "react";
import { Loader2 } from "lucide-react";
import {
  postBacktestBrowser,
  type BacktestRequest,
  type BacktestResult,
} from "@/lib/api";
import type { PairListRow } from "@/lib/mock";
import { cn } from "@/lib/utils";

// Inputs for one walk-forward run. Defaults are tuned to the daily-equity
// regime (252 sessions/year, half-life ~ 30-50 bars); the UI keeps the
// less-common controls (entry_z, exit_z, hedge method) one toggle away so
// the common case is "pick a pair, hit run".

const DEFAULTS: Omit<BacktestRequest, "base" | "quote"> = {
  train_size: 800,
  test_size: 200,
  asset_class: "equity",
  target_volatility: 0.15,
  tune_lookback: true,
  hedge_method: "kalman",
  entry_z: 2.0,
  exit_z: 0.5,
};

export function BacktestForm({
  pairs,
  onResult,
}: {
  pairs: PairListRow[];
  onResult: (r: BacktestResult) => void;
}) {
  const [base, setBase] = useState(pairs[0]?.base ?? "");
  const [quote, setQuote] = useState(pairs[0]?.quote ?? "");
  const [config, setConfig] = useState(DEFAULTS);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function pickPair(id: string) {
    const row = pairs.find((p) => p.id === id);
    if (!row) return;
    setBase(row.base);
    setQuote(row.quote);
  }

  async function submit() {
    setLoading(true);
    setError(null);
    try {
      const result = await postBacktestBrowser({ base, quote, ...config });
      onResult(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 border-b border-border-subtle bg-bg-panel px-4 py-3">
      <div className="flex flex-wrap items-end gap-3">
        <Field label="페어 / Pair" hint="cointegration p < 0.10">
          <select
            value={`${base}-${quote}`}
            onChange={(e) => pickPair(e.target.value)}
            className="num min-w-[180px] border border-border-subtle bg-bg-card px-2 py-1.5 text-xs text-text-primary focus:border-accent-cyan focus:outline-none"
          >
            {pairs.length === 0 && <option value="">no pairs available</option>}
            {pairs.map((p) => (
              <option key={p.id} value={p.id}>
                {p.base} / {p.quote} — p={p.cointPValue.toFixed(4)}
              </option>
            ))}
          </select>
        </Field>

        <Field label="Train size" hint="bars">
          <NumberInput
            value={config.train_size}
            onChange={(v) =>
              setConfig({ ...config, train_size: Math.max(50, v) })
            }
            step={50}
          />
        </Field>

        <Field label="Test size" hint="bars">
          <NumberInput
            value={config.test_size}
            onChange={(v) =>
              setConfig({ ...config, test_size: Math.max(20, v) })
            }
            step={25}
          />
        </Field>

        <Field label="Target vol" hint="annual">
          <NumberInput
            value={config.target_volatility}
            onChange={(v) =>
              setConfig({ ...config, target_volatility: Math.max(0.01, v) })
            }
            step={0.05}
          />
        </Field>

        <Field label="Asset class">
          <select
            value={config.asset_class}
            onChange={(e) =>
              setConfig({
                ...config,
                asset_class: e.target.value as "equity" | "crypto",
              })
            }
            className="border border-border-subtle bg-bg-card px-2 py-1.5 text-xs"
          >
            <option value="equity">equity (252)</option>
            <option value="crypto">crypto (8760)</option>
          </select>
        </Field>

        <label className="flex items-center gap-1.5 text-xs text-text-secondary">
          <input
            type="checkbox"
            checked={config.tune_lookback}
            onChange={(e) =>
              setConfig({ ...config, tune_lookback: e.target.checked })
            }
            className="accent-accent-cyan"
          />
          tune lookback by half-life
        </label>

        <button
          type="button"
          onClick={() => setShowAdvanced((s) => !s)}
          className="text-2xs uppercase tracking-widest text-text-muted hover:text-text-primary"
        >
          {showAdvanced ? "− advanced" : "+ advanced"}
        </button>

        <div className="ml-auto flex items-center gap-2">
          {error && (
            <span className="max-w-[320px] truncate text-2xs text-accent-red">
              {error}
            </span>
          )}
          <button
            type="button"
            onClick={submit}
            disabled={loading || !base || !quote}
            className={cn(
              "flex items-center gap-1.5 rounded border px-3 py-1.5 text-xs uppercase tracking-widest",
              loading || !base
                ? "cursor-not-allowed border-border-subtle bg-bg-elevated text-text-muted"
                : "border-accent-cyan/40 bg-accent-cyan/10 text-accent-cyan hover:bg-accent-cyan/20"
            )}
          >
            {loading && <Loader2 className="h-3 w-3 animate-spin" />}
            {loading ? "running" : "백테스트 실행"}
          </button>
        </div>
      </div>

      {showAdvanced && (
        <div className="flex flex-wrap items-end gap-3 border-t border-border-subtle pt-2">
          <Field label="entry z" hint="|z| >= entry → trade">
            <NumberInput
              value={config.entry_z}
              onChange={(v) =>
                setConfig({ ...config, entry_z: Math.max(0.1, v) })
              }
              step={0.1}
            />
          </Field>
          <Field label="exit z" hint="|z| <= exit → flat">
            <NumberInput
              value={config.exit_z}
              onChange={(v) =>
                setConfig({ ...config, exit_z: Math.max(0, v) })
              }
              step={0.1}
            />
          </Field>
          <Field label="Hedge method">
            <select
              value={config.hedge_method}
              onChange={(e) =>
                setConfig({
                  ...config,
                  hedge_method: e.target.value as "kalman" | "ols",
                })
              }
              className="border border-border-subtle bg-bg-card px-2 py-1.5 text-xs"
            >
              <option value="kalman">Kalman (adaptive)</option>
              <option value="ols">OLS (static)</option>
            </select>
          </Field>
        </div>
      )}
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="text-2xs uppercase tracking-widest text-text-muted">
        {label}
        {hint && <span className="ml-1 text-text-faint">· {hint}</span>}
      </div>
      {children}
    </div>
  );
}

function NumberInput({
  value,
  onChange,
  step,
}: {
  value: number;
  onChange: (v: number) => void;
  step: number;
}) {
  return (
    <input
      type="number"
      value={value}
      step={step}
      onChange={(e) => {
        const v = parseFloat(e.target.value);
        if (Number.isFinite(v)) onChange(v);
      }}
      className="num w-24 border border-border-subtle bg-bg-card px-2 py-1.5 text-xs text-text-primary focus:border-accent-cyan focus:outline-none"
    />
  );
}
