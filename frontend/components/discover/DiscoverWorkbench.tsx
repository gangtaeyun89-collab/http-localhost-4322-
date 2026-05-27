"use client";

import { useState } from "react";
import { DiscoverForm } from "./DiscoverForm";
import { DiscoverResults } from "./DiscoverResults";
import type { DiscoverResult, SectorSummary } from "@/lib/api";

export function DiscoverWorkbench({ sectors }: { sectors: SectorSummary[] }) {
  const [result, setResult] = useState<DiscoverResult | null>(null);
  return (
    <div className="flex flex-col">
      <DiscoverForm sectors={sectors} onResult={setResult} />
      {result ? (
        <DiscoverResults result={result} />
      ) : (
        <EmptyHint hasSectors={sectors.length > 0} />
      )}
    </div>
  );
}

function EmptyHint({ hasSectors }: { hasSectors: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-24 text-center">
      <div className="text-sm text-text-secondary">
        {hasSectors
          ? "산업 바스켓을 선택하고 '페어 발견 실행' 버튼을 누르세요."
          : "섹터 데이터를 불러올 수 없습니다. scripts/refresh_data.sh 로 데이터를 보강하세요."}
      </div>
      <div className="mt-2 max-w-lg text-xs text-text-muted">
        Distance clustering → 클러스터 내 cointegration test → Benjamini-
        Hochberg FDR. 좁은 동질적 바스켓을 1-3개 선택할 때 FDR 보정이
        가장 친절하게 작동합니다 (테스트 수가 작을수록 임계값이 완화됨).
      </div>
    </div>
  );
}
