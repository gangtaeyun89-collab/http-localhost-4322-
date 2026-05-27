"use client";

import { useState } from "react";
import type { PairQuote } from "@/lib/api";
import { type Position } from "@/lib/positions";
import { JournalPanel } from "./JournalPanel";
import { PositionsTable } from "./PositionsTable";
import { RiskPanel } from "./RiskPanel";

// Wraps the three position-related panels so they share the same
// (positions, quotes) state. PositionsTable owns the polling loop and
// pushes ticks up via onTick; the risk panel and the journal pull from
// localStorage the same way and re-render on the matching custom event,
// so even if the workbench unmounts the data is preserved.

export function PositionsWorkbench() {
  const [positions, setPositions] = useState<Position[]>([]);
  const [quotes, setQuotes] = useState<Record<string, PairQuote>>({});

  function handleTick(
    nextPositions: Position[],
    nextQuotes: Record<string, PairQuote>
  ) {
    setPositions(nextPositions);
    setQuotes(nextQuotes);
  }

  return (
    <div className="flex flex-col">
      <RiskPanel positions={positions} quotes={quotes} />
      <PositionsTable onTick={handleTick} />
      <JournalPanel positions={positions} />
    </div>
  );
}
