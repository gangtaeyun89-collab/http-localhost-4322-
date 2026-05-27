"use client";

import { useEffect, useState } from "react";
import { fetchPairQuoteBrowser, type PairQuote } from "@/lib/api";
import { cn, fmtNum, fmtPct } from "@/lib/utils";

// Browser-side polling tape that sits in the header of the pair workbench.
// Refetches /api/pairs/{id}/quote every `interval` ms; the backend caches
// for ~1s (CSV) or ~4s (IBKR) so this is cheap. Shows a blinking dot when
// a fresh tick has just landed, plus the latest z-score, spread, and the
// rule-derived signal so the user sees "what is the strategy saying right
// now" without leaving the page.

const SIGNAL_LABEL: Record<PairQuote["signal"], string> = {
  flat: "FLAT",
  long_spread: "LONG SPREAD",
  short_spread: "SHORT SPREAD",
};

const SIGNAL_COLOUR: Record<PairQuote["signal"], string> = {
  flat: "bg-text-muted/15 text-text-muted",
  long_spread: "bg-accent-green/15 text-accent-green",
  short_spread: "bg-accent-red/15 text-accent-red",
};

export function LivePulse({
  pairId,
  interval = 5000,
}: {
  pairId: string;
  interval?: number;
}) {
  const [quote, setQuote] = useState<PairQuote | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pulse, setPulse] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const q = await fetchPairQuoteBrowser(pairId);
        if (cancelled) return;
        setQuote(q);
        setError(null);
        // brief "I just updated" highlight, decays on its own
        setPulse(true);
        setTimeout(() => !cancelled && setPulse(false), 400);
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      }
    }

    poll();
    const id = setInterval(poll, interval);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [pairId, interval]);

  if (error && !quote) {
    return (
      <div className="flex items-center gap-2 text-2xs text-accent-red">
        <Dot colour="bg-accent-red" />
        polling error
      </div>
    );
  }

  if (!quote) {
    return (
      <div className="flex items-center gap-2 text-2xs text-text-muted">
        <Dot colour="bg-text-muted" />
        connecting…
      </div>
    );
  }

  const z = quote.lastZScore;
  const zClass =
    Math.abs(z) > 2
      ? "text-accent-red"
      : Math.abs(z) > 1
      ? "text-accent-yellow"
      : "text-text-primary";

  return (
    <div className="flex items-center gap-3 text-2xs uppercase tracking-widest text-text-muted">
      <div className="flex items-center gap-1.5">
        <Dot
          colour={
            quote.source === "csv"
              ? "bg-accent-cyan"
              : quote.source === "synthetic"
              ? "bg-accent-yellow"
              : "bg-accent-red"
          }
          pulsing={pulse}
        />
        <span>{quote.source}</span>
      </div>

      <Sep />

      <span>
        z:{" "}
        <span className={cn("num font-semibold", zClass)}>
          {fmtNum(z, 2, true)}
        </span>
      </span>

      <Sep />

      <span>
        spread:{" "}
        <span className="num text-text-primary">
          {fmtNum(quote.lastSpread, 4, true)}
        </span>
      </span>

      <Sep />

      <span
        className={cn(
          "rounded px-1.5 py-0.5 text-2xs font-semibold tracking-widest",
          SIGNAL_COLOUR[quote.signal]
        )}
      >
        {SIGNAL_LABEL[quote.signal]}
      </span>

      <Sep />

      <span>
        Δbase:{" "}
        <span
          className={cn(
            "num",
            quote.lastReturn.base >= 0
              ? "text-accent-green"
              : "text-accent-red"
          )}
        >
          {fmtPct(quote.lastReturn.base, 2, true)}
        </span>
      </span>
      <span>
        Δquote:{" "}
        <span
          className={cn(
            "num",
            quote.lastReturn.quote >= 0
              ? "text-accent-green"
              : "text-accent-red"
          )}
        >
          {fmtPct(quote.lastReturn.quote, 2, true)}
        </span>
      </span>
    </div>
  );
}

function Dot({
  colour,
  pulsing = false,
}: {
  colour: string;
  pulsing?: boolean;
}) {
  return (
    <span className="relative inline-flex h-2 w-2 items-center justify-center">
      <span
        className={cn(
          "h-2 w-2 rounded-full",
          colour,
          "shadow-[0_0_6px_currentColor]"
        )}
      />
      {pulsing && (
        <span
          className={cn(
            "absolute inline-flex h-2 w-2 animate-ping rounded-full opacity-75",
            colour
          )}
        />
      )}
    </span>
  );
}

function Sep() {
  return <span className="text-text-faint">|</span>;
}
