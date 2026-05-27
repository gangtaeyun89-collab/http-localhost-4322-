"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Loader2, X } from "lucide-react";
import { fetchPairQuoteBrowser, type PairQuote } from "@/lib/api";
import {
  closePosition,
  findOpenByPair,
  listAll,
  openPosition,
  positionPnl,
  type Position,
} from "@/lib/positions";
import { canEnter, getRiskConfig, type EntryGate } from "@/lib/risk";
import { cn, fmtPct } from "@/lib/utils";

// Pair-workbench affordance for opening / closing a paper-paper position.
// Polls /quote on its own so it can render the live z-score next to the
// buttons; LivePulse already does the same in the header, but having the
// numbers right next to the entry button removes the "do I click it now?"
// guess.

export function PositionToggle({ pairId }: { pairId: string }) {
  const [quote, setQuote] = useState<PairQuote | null>(null);
  const [position, setPosition] = useState<Position | undefined>(undefined);
  const [busy, setBusy] = useState(false);
  const [gate, setGate] = useState<EntryGate>({ allowed: true });

  // Mirror localStorage; refresh on cross-tab + in-tab events.
  useEffect(() => {
    const refresh = () => {
      setPosition(findOpenByPair(pairId));
      setGate(canEnter(listAll(), getRiskConfig()));
    };
    refresh();
    window.addEventListener("storage", refresh);
    window.addEventListener("statarb.positions.update", refresh);
    window.addEventListener("statarb.risk.update", refresh);
    return () => {
      window.removeEventListener("storage", refresh);
      window.removeEventListener("statarb.positions.update", refresh);
      window.removeEventListener("statarb.risk.update", refresh);
    };
  }, [pairId]);

  useEffect(() => {
    let cancelled = false;
    async function poll() {
      try {
        const q = await fetchPairQuoteBrowser(pairId);
        if (!cancelled) setQuote(q);
      } catch {
        // header LivePulse will surface polling errors -- stay silent.
      }
    }
    poll();
    const id = setInterval(poll, 5000);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [pairId]);

  async function enter(side: Position["side"]) {
    if (!quote) return;
    if (!gate.allowed) return;
    setBusy(true);
    try {
      openPosition({ pairId, side, quote });
    } finally {
      setBusy(false);
    }
  }

  function exit() {
    if (!quote || !position) return;
    closePosition(position.id, quote, "manual");
  }

  if (!quote) {
    return (
      <div className="flex items-center gap-1.5 px-3 py-1.5 text-2xs text-text-muted">
        <Loader2 className="h-3 w-3 animate-spin" />
        loading…
      </div>
    );
  }

  if (position) {
    const pnl = positionPnl(position, quote);
    return (
      <div className="flex items-center gap-2 border border-accent-yellow/30 bg-accent-yellow/5 px-3 py-1.5">
        <span className="text-2xs uppercase tracking-widest text-accent-yellow">
          가상 보유
        </span>
        <span
          className={cn(
            "num text-xs font-semibold",
            position.side === "long_spread"
              ? "text-accent-green"
              : "text-accent-red"
          )}
        >
          {position.side === "long_spread" ? "LONG" : "SHORT"} SPREAD
        </span>
        <span className="text-text-faint">·</span>
        <span className="num text-2xs text-text-secondary">
          entry z={position.entryZ.toFixed(2)}
        </span>
        <span className="text-text-faint">·</span>
        <span
          className={cn(
            "num text-xs font-semibold",
            pnl >= 0 ? "text-accent-green" : "text-accent-red"
          )}
        >
          {fmtPct(pnl, 2, true)}
        </span>
        <button
          onClick={exit}
          className="ml-1 flex items-center gap-1 rounded border border-border-subtle bg-bg-card px-2 py-0.5 text-2xs uppercase tracking-widest text-text-secondary hover:border-accent-red/40 hover:bg-accent-red/10 hover:text-accent-red"
        >
          <X className="h-3 w-3" />
          청산
        </button>
        <Link
          href="/equity/positions"
          className="text-2xs uppercase tracking-widest text-accent-cyan hover:underline"
        >
          → 포지션
        </Link>
      </div>
    );
  }

  const z = quote.lastZScore;
  // Suggested side: long when z is very negative, short when very positive.
  // We don't disable the other button -- the user can still take a counter
  // bet -- but the highlight nudges the right one.
  const longRecommended = z <= -2;
  const shortRecommended = z >= 2;
  const disabled = busy || !gate.allowed;

  return (
    <div className="flex flex-wrap items-center gap-2 px-3 py-1.5">
      <span className="text-2xs uppercase tracking-widest text-text-muted">
        가상 진입
      </span>
      <button
        onClick={() => enter("long_spread")}
        disabled={disabled}
        className={cn(
          "rounded border px-2 py-1 text-2xs uppercase tracking-widest",
          disabled
            ? "cursor-not-allowed border-border-subtle bg-bg-card/40 text-text-faint"
            : longRecommended
            ? "border-accent-green/60 bg-accent-green/15 text-accent-green hover:bg-accent-green/25"
            : "border-border-subtle bg-bg-card text-text-secondary hover:bg-bg-elevated"
        )}
        title="long base + short β·quote (z 음수에서 진입)"
      >
        LONG SPREAD
      </button>
      <button
        onClick={() => enter("short_spread")}
        disabled={disabled}
        className={cn(
          "rounded border px-2 py-1 text-2xs uppercase tracking-widest",
          disabled
            ? "cursor-not-allowed border-border-subtle bg-bg-card/40 text-text-faint"
            : shortRecommended
            ? "border-accent-red/60 bg-accent-red/15 text-accent-red hover:bg-accent-red/25"
            : "border-border-subtle bg-bg-card text-text-secondary hover:bg-bg-elevated"
        )}
        title="short base + long β·quote (z 양수에서 진입)"
      >
        SHORT SPREAD
      </button>
      {!gate.allowed && (
        <span className="text-2xs text-accent-red">
          진입 차단: {gate.reason}
        </span>
      )}
    </div>
  );
}
