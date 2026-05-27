"use client";

import Link from "next/link";
import { useMemo } from "react";
import { ArrowRight } from "lucide-react";
import type { DiscoverResult, DiscoveredPair } from "@/lib/api";
import { cn, fmtNum, fmtPct } from "@/lib/utils";

// Discovery report. Groups survivors back by sector so the user can see
// where the discovery actually paid off (apartment REITs five hits,
// homebuilders one, semiconductors zero -- the gap is the signal).

export function DiscoverResults({ result }: { result: DiscoverResult }) {
  const { grouped, ungrouped } = useMemo(() => {
    const g = new Map<string, { label: string; pairs: DiscoveredPair[] }>();
    const u: DiscoveredPair[] = [];
    for (const p of result.pairs) {
      if (!p.basket) {
        u.push(p);
        continue;
      }
      const bucket = g.get(p.basket) ?? {
        label: p.basketLabel ?? p.basket,
        pairs: [],
      };
      bucket.pairs.push(p);
      g.set(p.basket, bucket);
    }
    return { grouped: g, ungrouped: u };
  }, [result.pairs]);

  return (
    <div className="flex flex-col">
      <SummaryBar result={result} />
      {result.pairs.length === 0 ? (
        <EmptyState
          tested={result.n_tested}
          universeSize={result.n_universe}
        />
      ) : (
        <div className="flex flex-col gap-px bg-border-subtle">
          {Array.from(grouped.entries()).map(([basket, { label, pairs }]) => (
            <BasketBlock
              key={basket}
              basketId={basket}
              label={label}
              pairs={pairs}
            />
          ))}
          {ungrouped.length > 0 && (
            <BasketBlock
              basketId="unmapped"
              label="기타 / Unmapped"
              pairs={ungrouped}
            />
          )}
        </div>
      )}
    </div>
  );
}

function SummaryBar({ result }: { result: DiscoverResult }) {
  return (
    <div className="grid grid-cols-2 gap-px border-y border-border-subtle bg-border-subtle sm:grid-cols-4 lg:grid-cols-6">
      <Stat label="발견된 페어">
        <span
          className={cn(
            "num text-base font-semibold",
            result.pairs.length > 0
              ? "text-accent-green"
              : "text-text-muted"
          )}
        >
          {result.pairs.length}
        </span>
      </Stat>
      <Stat label="테스트 수">
        <span className="num text-base">{result.n_tested}</span>
      </Stat>
      <Stat label="클러스터">
        <span className="num text-base">{result.n_clusters}</span>
      </Stat>
      <Stat label="universe">
        <span className="num text-base">{result.n_universe}</span>
      </Stat>
      <Stat label="baskets">
        <span className="num text-base">{result.baskets.length}</span>
      </Stat>
      <Stat label="source">
        <span
          className={cn(
            "rounded px-1.5 py-0.5 text-2xs uppercase tracking-widest",
            result.source === "csv"
              ? "bg-accent-green/15 text-accent-green"
              : "bg-accent-purple/15 text-accent-purple"
          )}
        >
          {result.source}
        </span>
      </Stat>
    </div>
  );
}

function BasketBlock({
  basketId,
  label,
  pairs,
}: {
  basketId: string;
  label: string;
  pairs: DiscoveredPair[];
}) {
  return (
    <div className="bg-bg-panel">
      <div className="flex items-center justify-between border-b border-border-subtle px-4 py-2">
        <div className="flex items-center gap-2">
          <span className="text-2xs uppercase tracking-widest text-text-muted">
            basket
          </span>
          <span className="text-xs font-semibold text-text-primary">
            {label}
          </span>
          <span className="text-text-faint">·</span>
          <span className="num text-2xs text-text-secondary">
            {pairs.length} pair(s)
          </span>
        </div>
        {basketId !== "unmapped" && (
          <Link
            href={`/equity/sectors/${basketId}`}
            className="flex items-center gap-1 text-2xs uppercase tracking-widest text-accent-cyan hover:underline"
          >
            섹터 상세 <ArrowRight className="h-3 w-3" />
          </Link>
        )}
      </div>
      <table className="w-full text-xs">
        <thead className="text-text-muted">
          <tr>
            <Th>페어 / Pair</Th>
            <Th right>p-value</Th>
            <Th right>ADF stat</Th>
            <Th right>half-life</Th>
            <Th right>corr</Th>
            <Th right>워크벤치</Th>
          </tr>
        </thead>
        <tbody>
          {pairs.map((p) => (
            <PairRow key={p.id} pair={p} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PairRow({ pair }: { pair: DiscoveredPair }) {
  const strong = pair.cointPValue < 0.05;
  return (
    <tr className="border-t border-border-subtle hover:bg-bg-elevated">
      <Td>
        <Link
          href={`/equity/pairs/${pair.id}`}
          className="flex items-center gap-2"
        >
          <span className="num font-semibold text-accent-cyan">
            {pair.base}
          </span>
          <span className="text-text-faint">/</span>
          <span className="num font-semibold text-accent-magenta">
            {pair.quote}
          </span>
        </Link>
      </Td>
      <Td right>
        <span
          className={cn(
            "num",
            strong ? "text-accent-green font-semibold" : "text-text-primary"
          )}
        >
          {fmtNum(pair.cointPValue, 4)}
        </span>
      </Td>
      <Td right>
        <span className="num text-text-primary">
          {fmtNum(pair.adfStatistic, 2)}
        </span>
      </Td>
      <Td right>
        <span className="num">{fmtNum(pair.halfLife, 1)}</span>
      </Td>
      <Td right>
        <span
          className={cn(
            "num",
            pair.corr > 0.8 ? "text-accent-green" : "text-text-primary"
          )}
        >
          {fmtPct(pair.corr, 1, false)}
        </span>
      </Td>
      <Td right>
        <Link
          href={`/equity/pairs/${pair.id}`}
          className="text-2xs uppercase tracking-widest text-accent-cyan hover:underline"
        >
          열기 →
        </Link>
      </Td>
    </tr>
  );
}

function EmptyState({
  tested,
  universeSize,
}: {
  tested: number;
  universeSize: number;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
      <div className="text-sm text-text-secondary">
        FDR을 통과한 페어가 없습니다.
      </div>
      <div className="mt-2 max-w-md text-xs text-text-muted">
        {tested === 0
          ? "선택한 바스켓에서 universe로 매칭된 종목이 부족합니다 (scripts/refresh_data.sh 로 데이터 보강)."
          : `${universeSize}개 종목에서 ${tested}개 클러스터 내 테스트를 수행했지만 FDR 임계값을 통과하지 못했습니다. FDR을 0.20~0.30으로 완화하거나 더 좁은 산업 바스켓을 시도해 보세요.`}
      </div>
    </div>
  );
}

function Stat({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-0.5 bg-bg-panel px-3 py-2">
      <div className="text-2xs uppercase tracking-wide text-text-muted">
        {label}
      </div>
      <div className="leading-tight">{children}</div>
    </div>
  );
}

function Th({
  children,
  right,
}: {
  children: React.ReactNode;
  right?: boolean;
}) {
  return (
    <th
      className={cn(
        "px-3 py-2 font-normal uppercase tracking-widest text-2xs",
        right ? "text-right" : "text-left"
      )}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  right,
}: {
  children: React.ReactNode;
  right?: boolean;
}) {
  return (
    <td className={cn("px-3 py-2", right ? "text-right" : "text-left")}>
      {children}
    </td>
  );
}
