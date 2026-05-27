"use client";

import { useState } from "react";
import { BacktestForm } from "./BacktestForm";
import { BacktestResults } from "./BacktestResults";
import type { BacktestResult } from "@/lib/api";
import type { PairListRow } from "@/lib/mock";

// Top-level client wrapper for the backtest page: holds the latest result
// state so submitting the form replaces the report below in place.

export function BacktestWorkbench({ pairs }: { pairs: PairListRow[] }) {
  const [result, setResult] = useState<BacktestResult | null>(null);

  return (
    <div className="flex flex-col">
      <BacktestForm pairs={pairs} onResult={setResult} />
      {result ? (
        <BacktestResults result={result} />
      ) : (
        <EmptyHint hasPairs={pairs.length > 0} />
      )}
    </div>
  );
}

function EmptyHint({ hasPairs }: { hasPairs: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-24 text-center">
      <div className="text-sm text-text-secondary">
        {hasPairs
          ? "페어를 선택하고 '백테스트 실행' 버튼을 누르세요."
          : "screened 된 페어가 없습니다. scripts/refresh_data.sh 를 실행해 데이터를 받으세요."}
      </div>
      <div className="mt-2 max-w-md text-xs text-text-muted">
        walk-forward 는 train 윈도우에서 헤지/시그널을 학습하고 그
        직후 unseen test 윈도우에서만 평가합니다. mean train ≈ mean test
        라면 신호가 살아있음, train 이 훨씬 크면 overfit 입니다.
      </div>
    </div>
  );
}
