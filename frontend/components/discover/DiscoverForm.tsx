"use client";

import { useState } from "react";
import { CheckSquare, Loader2, Square } from "lucide-react";
import {
  postDiscoverBrowser,
  type DiscoverResult,
  type SectorSummary,
} from "@/lib/api";
import { cn, fmtNum } from "@/lib/utils";

// Form for POST /api/discover. The basket picker is the centrepiece --
// pair discovery is most useful when run on a narrow, economically
// coherent slice of the universe (e.g. just the apartment REITs), not
// the full 195-ticker book where the FDR correction crushes everything.

type FilterConfig = {
  fdr_level: number;
  distance_threshold: number;
  min_half_life: number;
  max_half_life: number;
};

const DEFAULTS: FilterConfig = {
  fdr_level: 0.10,
  distance_threshold: 0.7,
  min_half_life: 5,
  max_half_life: 200,
};

export function DiscoverForm({
  sectors,
  onResult,
}: {
  sectors: SectorSummary[];
  onResult: (r: DiscoverResult) => void;
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [config, setConfig] = useState<FilterConfig>(DEFAULTS);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function selectAll() {
    setSelected(new Set(sectors.map((s) => s.id)));
  }

  function clearAll() {
    setSelected(new Set());
  }

  async function submit() {
    if (selected.size === 0) {
      setError("바스켓을 한 개 이상 선택하세요.");
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await postDiscoverBrowser({
        baskets: Array.from(selected),
        ...config,
      });
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
        <div className="text-2xs uppercase tracking-widest text-text-muted">
          산업 바스켓
          <span className="ml-1 text-text-faint">
            · {selected.size} / {sectors.length} selected
          </span>
        </div>
        <div className="flex items-center gap-2 text-2xs">
          <button
            type="button"
            onClick={selectAll}
            className="rounded border border-border-subtle px-2 py-0.5 uppercase tracking-widest text-text-secondary hover:bg-bg-elevated"
          >
            전체 선택
          </button>
          <button
            type="button"
            onClick={clearAll}
            className="rounded border border-border-subtle px-2 py-0.5 uppercase tracking-widest text-text-secondary hover:bg-bg-elevated"
          >
            모두 해제
          </button>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-1 sm:grid-cols-3 lg:grid-cols-4 2xl:grid-cols-5">
        {sectors.map((s) => (
          <BasketChip
            key={s.id}
            sector={s}
            selected={selected.has(s.id)}
            onToggle={() => toggle(s.id)}
          />
        ))}
      </div>

      <div className="flex flex-wrap items-end gap-3 border-t border-border-subtle pt-2">
        <Field
          label="FDR level"
          hint="Benjamini-Hochberg"
          value={config.fdr_level}
          step={0.01}
          min={0.01}
          max={1}
          onChange={(v) => setConfig({ ...config, fdr_level: v })}
        />
        <Field
          label="distance"
          hint="cluster cutoff"
          value={config.distance_threshold}
          step={0.05}
          min={0.1}
          max={2}
          onChange={(v) => setConfig({ ...config, distance_threshold: v })}
        />
        <Field
          label="min half-life"
          hint="bars"
          value={config.min_half_life}
          step={1}
          min={1}
          onChange={(v) => setConfig({ ...config, min_half_life: v })}
        />
        <Field
          label="max half-life"
          hint="bars"
          value={config.max_half_life}
          step={5}
          min={1}
          onChange={(v) => setConfig({ ...config, max_half_life: v })}
        />

        <div className="ml-auto flex items-center gap-2">
          {error && (
            <span className="max-w-[320px] truncate text-2xs text-accent-red">
              {error}
            </span>
          )}
          <button
            type="button"
            onClick={submit}
            disabled={loading}
            className={cn(
              "flex items-center gap-1.5 rounded border px-3 py-1.5 text-xs uppercase tracking-widest",
              loading
                ? "cursor-not-allowed border-border-subtle bg-bg-elevated text-text-muted"
                : "border-accent-cyan/40 bg-accent-cyan/10 text-accent-cyan hover:bg-accent-cyan/20"
            )}
          >
            {loading && <Loader2 className="h-3 w-3 animate-spin" />}
            {loading ? "discovering" : "페어 발견 실행"}
          </button>
        </div>
      </div>
    </div>
  );
}

function BasketChip({
  sector,
  selected,
  onToggle,
}: {
  sector: SectorSummary;
  selected: boolean;
  onToggle: () => void;
}) {
  const hasData = sector.tickerCount >= 2;
  return (
    <button
      type="button"
      onClick={onToggle}
      className={cn(
        "flex items-center gap-2 rounded border px-2 py-1 text-left text-xs transition",
        selected
          ? "border-accent-cyan/40 bg-accent-cyan/10 text-accent-cyan"
          : hasData
          ? "border-border-subtle bg-bg-card text-text-primary hover:bg-bg-elevated"
          : "cursor-not-allowed border-border-subtle bg-bg-card/40 text-text-faint"
      )}
      disabled={!hasData}
      title={hasData ? sector.label : `${sector.label} (데이터 없음)`}
    >
      {selected ? (
        <CheckSquare className="h-3 w-3 shrink-0" />
      ) : (
        <Square className="h-3 w-3 shrink-0" />
      )}
      <span className="truncate">{sector.label}</span>
      <span className="ml-auto num text-2xs text-text-muted">
        {sector.tickerCount}
      </span>
    </button>
  );
}

function Field({
  label,
  hint,
  value,
  step,
  min,
  max,
  onChange,
}: {
  label: string;
  hint?: string;
  value: number;
  step: number;
  min?: number;
  max?: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="flex flex-col gap-1">
      <div className="text-2xs uppercase tracking-widest text-text-muted">
        {label}
        {hint && <span className="ml-1 text-text-faint">· {hint}</span>}
      </div>
      <input
        type="number"
        value={value}
        step={step}
        min={min}
        max={max}
        onChange={(e) => {
          const v = parseFloat(e.target.value);
          if (Number.isFinite(v)) onChange(v);
        }}
        className="num w-24 border border-border-subtle bg-bg-card px-2 py-1.5 text-xs text-text-primary focus:border-accent-cyan focus:outline-none"
      />
    </div>
  );
}

export const _fmtNumUsed = fmtNum;
